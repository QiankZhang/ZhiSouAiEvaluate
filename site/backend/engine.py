"""真实评测引擎（Judge Agent）：把「数据集样本 + 评估基准」交给大模型网关，产出与模拟
引擎 _evaluate_item 完全一致结构的评分结果（技术方案 §6.4 / §8.5）。

两条路径（提示词类型 / 技能 Skill 类型）在这里汇合：都组装 system prompt +
response_format=json_object 结构化输出 + 后端重算加权总分/GSB 裁决，保证可复现。
（网关不支持 OpenAI function calling，故用 JSON 输出而非工具调用。）

维度分制/每档标准/聚合方式/一票否决统一走 `scoring.py`（见 `多维度评估基准优化设计.md`）。
"""

import json
from typing import Any, Optional

from . import config, llm, scoring

_SYSTEM_SHELL = """你是"智搜策略效果评估"平台的评测裁判员（Judge Agent）。你正在执行一个自动化评测任务，
唯一职责是依据下面加载的说明，对被评估内容打分，并以 JSON 形式输出结果。

硬性规则：
1. 你不与用户对话，也不会收到进一步澄清；下面提供的信息就是全部上下文。
2. 你必须且只能输出一个 JSON 对象作为最终结果，不要输出任何解释、前言、结束语或 Markdown 代码块。
3. 每个维度严格按它声明的取值域打分（整数区间给整数、枚举给枚举值之一），禁止越界、禁止小数（除非该维度是枚举）。
4. 本次任务会连续调用你很多次（每次一条样本）；本段与下面的说明、维度配置在任务全程不变。

{skill_or_prompt_block}

本次任务的维度定义（来自评估基准配置，以此为准，覆盖说明中的示例维度）：
{dimensions_block}
{gsb_block}

{output_spec_block}"""


def _dimensions_block(dims: list[dict[str, Any]]) -> str:
    lines = []
    for raw in dims:
        d = scoring.normalize_dimension(raw)
        s = d["scale"]
        head = f"- {d['key']} / {d.get('name', d['key'])}（权重 {d.get('weight', 0)}，取值 {scoring.score_domain_text(d)}）"
        desc = str(d.get("description") or d.get("criteria") or "").strip()
        if desc:
            head += f"：{desc}"
        lines.append(head)
        for lv in s.get("levels", []):
            crit = str(lv.get("criteria") or "").strip()
            if not crit and not lv.get("label"):
                continue
            label = f"（{lv['label']}）" if lv.get("label") else ""
            lines.append(f"    · {lv['value']}{label}：{crit or '（未提供标准，按档位名判断）'}")
        thr = d.get("veto_below")
        if thr is not None:
            lines.append(f"    · ⚠ 一票否决：该维度得分低于 {thr} 时，整体判为最低档")
    return "\n".join(lines)


def _output_spec_block(dims: list[dict[str, Any]], is_gsb: bool) -> str:
    """把期望的 JSON 输出结构写进 system prompt。网关不支持 function calling，
    改用 response_format=json_object + 明确的结构说明来拿结构化结果。"""
    ndims = [scoring.normalize_dimension(d) for d in dims]
    keys = "、".join(d["key"] for d in ndims)
    if is_gsb:
        rows = ",\n".join(
            f'    {{"key": "{d["key"]}", "exp_score": <{scoring.score_domain_text(d)}>, '
            f'"base_score": <{scoring.score_domain_text(d)}>, "reason": "<该维度点评，≤120字>"}}'
            for d in ndims
        )
        return (
            "最终只输出如下 JSON 对象（不要包裹代码块）。dimensions 必须且只能包含这些 key："
            f"{keys}；exp_score 为实验对象得分，base_score 为基线对象得分：\n"
            "{\n"
            '  "dimensions": [\n'
            f"{rows}\n"
            "  ],\n"
            '  "reason": "<一句话整体对比结论，≤120字>",\n'
            '  "confidence": <0~1 之间的小数>\n'
            "}"
        )
    rows = ",\n".join(
        f'    {{"key": "{d["key"]}", "score": <{scoring.score_domain_text(d)}>, "reason": "<该维度点评，≤120字>"}}'
        for d in ndims
    )
    return (
        "最终只输出如下 JSON 对象（不要包裹代码块）。dimensions 必须且只能包含这些 key："
        f"{keys}：\n"
        "{\n"
        '  "dimensions": [\n'
        f"{rows}\n"
        "  ],\n"
        '  "reason": "<一句话整体点评，≤120字>",\n'
        '  "confidence": <0~1 之间的小数>\n'
        "}"
    )


def build_system_prompt(benchmark: dict[str, Any], skill: Optional[dict[str, Any]]) -> str:
    cfg = scoring.normalize_config(benchmark["config"])
    dims = cfg["dimensions"]
    is_gsb = benchmark["eval_method"] == "GSB"
    if skill:
        block = f"已加载技能：{skill['name']}（v{skill.get('version') or '—'}）\n\n{skill['instructions']}"
    else:
        template = cfg.get("prompt_template") or ""
        block = f"评测说明（提示词基准）：\n\n{template}"

    gsb_block = ""
    if is_gsb:
        gsb = cfg.get("gsb") or {}
        gsb_block = (
            "\nGSB 判定规则（实验=待评内容，基线=基线内容）：\n"
            f"{gsb.get('rules', '实验优于基线为 Good，持平为 Same，劣于基线为 Bad')}\n"
            f"裁决维度：{gsb.get('adjudication_dimension', 'overall')}\n"
            "对每个维度分别给实验对象与基线对象打分（按各维度声明的取值域），平台会按配置的聚合方式换算总分并裁决 Good/Same/Bad。"
        )

    return _SYSTEM_SHELL.format(
        skill_or_prompt_block=block,
        dimensions_block=_dimensions_block(dims),
        gsb_block=gsb_block,
        output_spec_block=_output_spec_block(dims, is_gsb),
    )


def _user_message(item: dict[str, Any], is_gsb: bool) -> str:
    parts = [f"查询（query）：\n{item.get('query', '')}", f"\n待评内容（实验对象）：\n{item.get('content', '')}"]
    if is_gsb:
        parts.append(f"\n基线内容（基线对象）：\n{item.get('baseline', '')}")
    parts.append("\n请依据已加载的说明完成本条评估，只输出约定的 JSON 对象。")
    return "\n".join(parts)


def _weighted_total(scores_by_key: dict[str, Any], dims: list[dict[str, Any]]) -> float:
    """兼容旧签名：按 weighted_raw（`Σ(score×weight)/100`）算总分。"""
    return scoring.aggregate(dims, scores_by_key, scoring.normalize_scoring({}))["total"]


def _parse_confidence(raw: Any, enabled: bool) -> Optional[float]:
    if not enabled:
        return None
    try:
        return round(max(0.0, min(1.0, float(raw))), 2)
    except (TypeError, ValueError):
        return None


def _evaluate_multi(item, benchmark, model, skill, system_prompt):
    cfg = scoring.normalize_config(benchmark["config"])
    dims = cfg["dimensions"]
    scoring_cfg = cfg["scoring"]
    expected = {d["key"] for d in dims}
    resp = llm.chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _user_message(item, is_gsb=False)},
        ],
        model=model,
        response_format={"type": "json_object"},
    )
    args = llm.parse_json_response(resp)
    raw_dims = args.get("dimensions") or []
    got = {d.get("key") for d in raw_dims}
    if got != expected:
        raise ValueError(f"维度 key 不匹配：期望 {sorted(expected)}，实际 {sorted(k for k in got if k)}")

    dim_by_key = {d["key"]: d for d in dims}
    dim_scores = []
    scores_by_key: dict[str, Any] = {}
    for rd in raw_dims:
        d = dim_by_key[rd["key"]]
        s = scoring.coerce_score(d, rd.get("score"))
        scores_by_key[d["key"]] = s
        dim_scores.append(
            {"key": d["key"], "name": d.get("name", d["key"]), "score": s, "reason": (rd.get("reason") or "").strip()}
        )
    agg = scoring.aggregate(dims, scores_by_key, scoring_cfg)
    conf = _parse_confidence(args.get("confidence"), cfg.get("confidence_enabled", True))
    reason = (args.get("reason") or "").strip() or _fallback_reason(dim_scores, dims)
    if agg["vetoed"]:
        reason = f"[否决] {agg['vetoed']} 触发拦截。" + reason
    scores: dict[str, Any] = {"dimensions": dim_scores, "total": agg["total"], "total_ratio": agg["total_ratio"]}
    if agg["grade_label"]:
        scores["grade_label"] = agg["grade_label"]
    if agg["vetoed"]:
        scores["vetoed"] = agg["vetoed"]
    if conf is not None:
        scores["confidence"] = conf
    return {
        "row_index": item["row_index"],
        "query": item["query"],
        "content": item["content"],
        "baseline": "",
        "status": "SUCCESS",
        "scores": scores,
        "reason": reason,
        "confidence": conf,
        "review_status": "PENDING",
        "engine": "agent",
        "raw_output": args,
        "_usage": llm.usage_of(resp),
    }


def _evaluate_gsb(item, benchmark, model, skill, system_prompt):
    cfg = scoring.normalize_config(benchmark["config"])
    dims = cfg["dimensions"]
    scoring_cfg = cfg["scoring"]
    expected = {d["key"] for d in dims}
    resp = llm.chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _user_message(item, is_gsb=True)},
        ],
        model=model,
        response_format={"type": "json_object"},
    )
    args = llm.parse_json_response(resp)
    raw_dims = args.get("dimensions") or []
    got = {d.get("key") for d in raw_dims}
    if got != expected:
        raise ValueError(f"维度 key 不匹配：期望 {sorted(expected)}，实际 {sorted(k for k in got if k)}")

    dim_by_key = {d["key"]: d for d in dims}
    exp_by_key: dict[str, Any] = {}
    base_by_key: dict[str, Any] = {}
    dim_scores = []
    for rd in raw_dims:
        d = dim_by_key[rd["key"]]
        e = scoring.coerce_score(d, rd.get("exp_score"))
        b = scoring.coerce_score(d, rd.get("base_score"))
        exp_by_key[d["key"]] = e
        base_by_key[d["key"]] = b
        dim_scores.append({"key": d["key"], "name": d.get("name", d["key"]), "score": e, "baseline_score": b})

    exp_agg = scoring.aggregate(dims, exp_by_key, scoring_cfg)
    base_agg = scoring.aggregate(dims, base_by_key, scoring_cfg)
    judgment, _diff = scoring.gsb_judgment(exp_agg, base_agg, scoring_cfg)
    conf = _parse_confidence(args.get("confidence"), cfg.get("confidence_enabled", True))
    reason = (args.get("reason") or "").strip() or (
        "实验策略结果" + ("优于" if judgment == "Good" else "持平于" if judgment == "Same" else "劣于") + "基线策略。"
    )
    scores: dict[str, Any] = {
        "judgment": judgment,
        "dimensions": dim_scores,
        "total": exp_agg["total"],
        "baseline_total": base_agg["total"],
        "total_ratio": exp_agg["total_ratio"],
        "baseline_total_ratio": base_agg["total_ratio"],
    }
    if conf is not None:
        scores["confidence"] = conf
    return {
        "row_index": item["row_index"],
        "query": item["query"],
        "content": item["content"],
        "baseline": item.get("baseline", ""),
        "status": "SUCCESS",
        "scores": scores,
        "reason": reason,
        "confidence": conf,
        "review_status": "PENDING",
        "engine": "agent",
        "raw_output": args,
        "_usage": llm.usage_of(resp),
    }


def _fallback_reason(dim_scores: list[dict[str, Any]], dims: list[dict[str, Any]]) -> str:
    """按归一得分率找最弱维度。"""
    dim_by_key = {d["key"]: d for d in dims}

    def _r(ds):
        return scoring.ratio_of(dim_by_key[ds["key"]], ds["score"]) or 0.0

    if not dim_scores:
        return "未获得有效维度评分。"
    weakest = min(dim_scores, key=_r)
    if _r(weakest) >= 0.75:
        return "各维度表现良好，内容贴合查询意图。"
    return f"{weakest['name']}偏弱：{weakest.get('reason') or '存在明显短板'}"


def evaluate_item_llm(
    item: dict[str, Any],
    benchmark: dict[str, Any],
    model: str,
    skill: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """真实调用大模型网关评一条样本。schema 校验失败轻量重试 ≤2；仍失败抛异常给调用方。"""
    system_prompt = build_system_prompt(benchmark, skill)
    is_gsb = benchmark["eval_method"] == "GSB"
    fn = _evaluate_gsb if is_gsb else _evaluate_multi
    last_err: Exception | None = None
    for _ in range(3):
        try:
            return fn(item, benchmark, model, skill, system_prompt)
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            last_err = exc
    raise llm.LlmError(f"结构化输出校验失败：{last_err}")
