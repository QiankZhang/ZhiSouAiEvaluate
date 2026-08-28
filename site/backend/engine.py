"""真实评测引擎（Judge Agent）：把「数据集样本 + 评估基准」交给 DeepSeek，产出与模拟
引擎 _evaluate_item 完全一致结构的评分结果（技术方案 §6.4 / §8.5）。

两条路径（提示词类型 / 技能 Skill 类型）在这里汇合：都组装 system prompt + 强制
submit_evaluation 工具调用 + 后端重算加权总分/GSB 裁决，保证可复现。
"""

import json
from typing import Any, Optional

from . import config, llm

GSB_GOOD_THRESHOLD = 0.18  # 与模拟引擎 _evaluate_item 保持一致

_SYSTEM_SHELL = """你是"智搜策略效果评估"平台的评测裁判员（Judge Agent）。你正在执行一个自动化评测任务，
唯一职责是依据下面加载的说明，对被评估内容打分，并通过 submit_evaluation 工具提交结果。

硬性规则：
1. 你不与用户对话，也不会收到进一步澄清；下面提供的信息就是全部上下文。
2. 你必须调用 submit_evaluation 工具提交最终结果；工具调用之外不要输出任何文字。
3. 维度评分为 1~5 的整数，禁止小数、禁止越界。
4. 本次任务会连续调用你很多次（每次一条样本）；本段与下面的说明、维度配置在任务全程不变。

{skill_or_prompt_block}

本次任务的维度定义（来自评估基准配置，以此为准，覆盖说明中的示例维度）：
{dimensions_block}
{gsb_block}"""


def _dimensions_block(dims: list[dict[str, Any]]) -> str:
    lines = []
    for d in dims:
        crit = d.get("criteria") or "（无额外说明，按维度名称常识判断）"
        lines.append(f"- {d['key']} / {d.get('name', d['key'])}（权重 {d.get('weight', 0)}）：{crit}")
    return "\n".join(lines)


def build_system_prompt(benchmark: dict[str, Any], skill: Optional[dict[str, Any]]) -> str:
    cfg = benchmark["config"]
    dims = cfg["dimensions"]
    if skill:
        block = f"已加载技能：{skill['name']}（v{skill.get('version') or '—'}）\n\n{skill['instructions']}"
    else:
        template = cfg.get("prompt_template") or ""
        block = f"评测说明（提示词基准）：\n\n{template}"

    gsb_block = ""
    if benchmark["eval_method"] == "GSB":
        gsb = cfg.get("gsb") or {}
        gsb_block = (
            "\nGSB 判定规则（实验=待评内容，基线=基线内容）：\n"
            f"{gsb.get('rules', '实验优于基线为 Good，持平为 Same，劣于基线为 Bad')}\n"
            f"裁决维度：{gsb.get('adjudication_dimension', 'overall')}\n"
            "对每个维度分别给实验对象与基线对象打 1~5 分，平台会按权重换算总分并裁决 Good/Same/Bad。"
        )

    return _SYSTEM_SHELL.format(
        skill_or_prompt_block=block,
        dimensions_block=_dimensions_block(dims),
        gsb_block=gsb_block,
    )


def _submit_tool_multi(dims: list[dict[str, Any]]) -> dict:
    keys = [d["key"] for d in dims]
    return {
        "type": "function",
        "function": {
            "name": "submit_evaluation",
            "description": "提交本条样本的多维度评分结果",
            "parameters": {
                "type": "object",
                "required": ["dimensions", "confidence"],
                "properties": {
                    "dimensions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["key", "score", "reason"],
                            "properties": {
                                "key": {"type": "string", "enum": keys},
                                "score": {"type": "integer", "minimum": 1, "maximum": 5},
                                "reason": {"type": "string", "maxLength": 120},
                            },
                        },
                    },
                    "reason": {"type": "string", "maxLength": 120, "description": "一句话整体点评"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    }


def _submit_tool_gsb(dims: list[dict[str, Any]]) -> dict:
    keys = [d["key"] for d in dims]
    return {
        "type": "function",
        "function": {
            "name": "submit_evaluation",
            "description": "提交本条样本的 GSB 对比评估结果：对每个维度分别给实验对象和基线对象打分",
            "parameters": {
                "type": "object",
                "required": ["dimensions", "reason", "confidence"],
                "properties": {
                    "dimensions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["key", "exp_score", "base_score"],
                            "properties": {
                                "key": {"type": "string", "enum": keys},
                                "exp_score": {"type": "integer", "minimum": 1, "maximum": 5},
                                "base_score": {"type": "integer", "minimum": 1, "maximum": 5},
                                "reason": {"type": "string", "maxLength": 120},
                            },
                        },
                    },
                    "reason": {"type": "string", "maxLength": 120},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    }


def _user_message(item: dict[str, Any], is_gsb: bool) -> str:
    parts = [f"查询（query）：\n{item.get('query', '')}", f"\n待评内容（实验对象）：\n{item.get('content', '')}"]
    if is_gsb:
        parts.append(f"\n基线内容（基线对象）：\n{item.get('baseline', '')}")
    parts.append("\n请依据已加载的说明完成本条评估，调用 submit_evaluation 提交结果。")
    return "\n".join(parts)


def _weighted_total(scores_by_key: dict[str, int], dims: list[dict[str, Any]]) -> float:
    """复刻 skills/multi-dimension-evaluation/scripts/weighted_score.py：恒除以 100，不归一化。"""
    acc = sum(scores_by_key.get(d["key"], 0) * float(d.get("weight", 0)) for d in dims)
    return round(acc / 100.0, 2)


def _clamp_score(value: Any) -> int:
    try:
        return max(1, min(5, int(round(float(value)))))
    except (TypeError, ValueError):
        raise ValueError(f"维度分值非法：{value!r}")


def _parse_confidence(raw: Any, enabled: bool) -> Optional[float]:
    if not enabled:
        return None
    try:
        return round(max(0.0, min(1.0, float(raw))), 2)
    except (TypeError, ValueError):
        return None


def _evaluate_multi(item, benchmark, model, skill, system_prompt):
    dims = benchmark["config"]["dimensions"]
    expected = {d["key"] for d in dims}
    resp = llm.chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _user_message(item, is_gsb=False)},
        ],
        model=model,
        tools=[_submit_tool_multi(dims)],
        tool_choice="auto",  # deepseek-v4-flash 思考模式不支持强制指定函数，用 auto + 强提示
    )
    args = llm.extract_tool_arguments(resp, "submit_evaluation")
    raw_dims = args.get("dimensions") or []
    got = {d.get("key") for d in raw_dims}
    if got != expected:
        raise ValueError(f"维度 key 不匹配：期望 {sorted(expected)}，实际 {sorted(k for k in got if k)}")

    name_by_key = {d["key"]: d.get("name", d["key"]) for d in dims}
    dim_scores = []
    scores_by_key: dict[str, int] = {}
    for d in raw_dims:
        s = _clamp_score(d.get("score"))
        scores_by_key[d["key"]] = s
        dim_scores.append(
            {"key": d["key"], "name": name_by_key[d["key"]], "score": s, "reason": (d.get("reason") or "").strip()}
        )
    total = _weighted_total(scores_by_key, dims)
    conf = _parse_confidence(args.get("confidence"), benchmark["config"].get("confidence_enabled", True))
    reason = (args.get("reason") or "").strip() or _fallback_reason(dim_scores)
    scores: dict[str, Any] = {"dimensions": dim_scores, "total": total}
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
    dims = benchmark["config"]["dimensions"]
    expected = {d["key"] for d in dims}
    resp = llm.chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _user_message(item, is_gsb=True)},
        ],
        model=model,
        tools=[_submit_tool_gsb(dims)],
        tool_choice="auto",  # deepseek-v4-flash 思考模式不支持强制指定函数，用 auto + 强提示
    )
    args = llm.extract_tool_arguments(resp, "submit_evaluation")
    raw_dims = args.get("dimensions") or []
    got = {d.get("key") for d in raw_dims}
    if got != expected:
        raise ValueError(f"维度 key 不匹配：期望 {sorted(expected)}，实际 {sorted(k for k in got if k)}")

    name_by_key = {d["key"]: d.get("name", d["key"]) for d in dims}
    exp_by_key: dict[str, int] = {}
    base_by_key: dict[str, int] = {}
    dim_scores = []
    for d in raw_dims:
        e = _clamp_score(d.get("exp_score"))
        b = _clamp_score(d.get("base_score"))
        exp_by_key[d["key"]] = e
        base_by_key[d["key"]] = b
        dim_scores.append({"key": d["key"], "name": name_by_key[d["key"]], "score": e, "baseline_score": b})

    exp_total = _weighted_total(exp_by_key, dims)
    base_total = _weighted_total(base_by_key, dims)
    diff = round(exp_total - base_total, 2)
    if diff > GSB_GOOD_THRESHOLD:
        judgment = "Good"
    elif diff < -GSB_GOOD_THRESHOLD:
        judgment = "Bad"
    else:
        judgment = "Same"
    conf = _parse_confidence(args.get("confidence"), benchmark["config"].get("confidence_enabled", True))
    reason = (args.get("reason") or "").strip() or (
        "实验策略结果" + ("优于" if judgment == "Good" else "持平于" if judgment == "Same" else "劣于") + "基线策略。"
    )
    scores: dict[str, Any] = {
        "judgment": judgment,
        "dimensions": dim_scores,
        "total": exp_total,
        "baseline_total": base_total,
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


def _fallback_reason(dim_scores: list[dict[str, Any]]) -> str:
    weakest = min(dim_scores, key=lambda d: d["score"])
    if weakest["score"] >= 4:
        return "各维度表现良好，内容贴合查询意图。"
    return f"{weakest['name']}偏弱：{weakest.get('reason') or '存在明显短板'}"


def evaluate_item_llm(
    item: dict[str, Any],
    benchmark: dict[str, Any],
    model: str,
    skill: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """真实调用 DeepSeek 评一条样本。schema 校验失败轻量重试 ≤2；仍失败抛异常给调用方。"""
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
