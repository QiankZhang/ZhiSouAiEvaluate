import csv
import hashlib
import io
import json
import logging
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import (
    accounts,
    config,
    db as db_mod,
    engine as engine_mod,
    llm,
    report as report_mod,
    scoring,
    skills_registry,
)

# 技能包解析实现迁移到 skills_registry，这里保留别名兼容既有调用点
_parse_skill_frontmatter = skills_registry.parse_skill_frontmatter
_validate_skill_meta = skills_registry.validate_skill_meta
_parse_skill_package = skills_registry.parse_skill_package

app = FastAPI(title="智搜策略效果评估", version="0.1.0")

_lock = threading.Lock()

# 自增序号而非 len(list)，避免删除后再新建/复制时 ID 复用冲突
_id_seq = {"DS": 1000, "BM": 1000, "TK": 1000, "RT": 1000, "MT": 1000}


def _next_id(prefix: str) -> str:
    _id_seq[prefix] += 1
    return f"{prefix}-{_id_seq[prefix]}"

# 数据集 / 评测结果的必需列，按评估方式区分
REQUIRED_COLUMNS = {
    "MULTI_DIM": ["query", "content"],
    "GSB": ["query", "content", "baseline"],
}
COLUMN_LABELS = {"query": "query（查询）", "content": "content（待评内容）", "baseline": "baseline（基线内容）"}

# 上传文件不强制要求列名严格等于 query/content/baseline，按常见别名自动识别，
# 识别不到再按列顺序兜底映射——取消"缺少必需列"硬校验，改为尽力兼容（见下方 _resolve_field_map）。
COLUMN_ALIASES = {
    "query": {"query", "问题", "查询", "prompt", "输入", "question", "q"},
    "content": {"content", "待评内容", "回答", "答案", "response", "answer", "output", "结果", "生成内容", "新答案"},
    "baseline": {"baseline", "基线", "基线内容", "基线答案", "参考答案", "reference", "对照", "旧答案", "旧回答"},
}


def _normalize_col(name: Any) -> str:
    return re.sub(r"[\s（）()【】\-_:：]", "", str(name)).strip().lower()


def _resolve_field_map(keys: list[str], required: list[str]) -> dict[str, str]:
    """把源文件里的原始列名/字段名映射到标准字段(query/content/baseline)：
    先按别名匹配，剩余列按出现顺序依次兜底对应剩余的必需字段。"""
    normalized_alias = {canon: {_normalize_col(a) for a in aliases} for canon, aliases in COLUMN_ALIASES.items()}
    field_map: dict[str, str] = {}
    used_keys: set[str] = set()
    for key in keys:
        norm = _normalize_col(key)
        for canon in required:
            if canon in field_map:
                continue
            if norm == canon or norm in normalized_alias.get(canon, set()):
                field_map[canon] = key
                used_keys.add(key)
                break
    leftover = [k for k in keys if k not in used_keys]
    for canon in required:
        if canon in field_map:
            continue
        if leftover:
            field_map[canon] = leftover.pop(0)
    return field_map


def _remap_rows(raw_rows: list[tuple[int, dict[str, Any]]], required: list[str]) -> list[tuple[int, dict[str, Any]]]:
    """按第一行的字段类型/列名自动识别 query/content/baseline，再把所有行统一改写为标准字段名。"""
    if not raw_rows:
        return raw_rows
    keys = list(raw_rows[0][1].keys())
    field_map = _resolve_field_map(keys, required)
    return [
        (line_no, {canon: str(row.get(src, "") or "") for canon, src in field_map.items()})
        for line_no, row in raw_rows
    ]


def now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _stable_noise(*parts: str) -> float:
    h = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _chars(items: list[dict[str, str]]) -> int:
    total = 0
    for item in items:
        total += len(item.get("query", "")) + len(item.get("content", "")) + len(item.get("baseline", ""))
    return total


# 仅用于「下载模板 CSV」的示例行与提示词预校验试跑，不作为任何数据集/任务的种子数据
_TEMPLATE_EXAMPLES = [
    {
        "query": "示例：某地天气预报",
        "content": "示例：这里填写需要评测的待评内容（实验对象）。",
        "baseline": "示例：这里填写对照的基线内容（仅 GSB 方式需要）。",
    },
    {
        "query": "示例：某产品最新报价",
        "content": "示例：第二条待评内容。",
        "baseline": "示例：第二条基线内容。",
    },
]


# ---- 评测基准配置 ----

# 全平台统一的默认评分维度：相关性 / 全面性 / 准确性 / 可读性 / 时效性，各 20%。
# AI 评估（评估基准）与人工评估（人工评估中心）共用同一套默认，可在各自表单里改。
DEFAULT_DIMENSIONS = [
    {"key": "relevance", "name": "相关性", "weight": 20, "criteria": "结果是否直接命中用户查询意图"},
    {"key": "comprehensiveness", "name": "全面性", "weight": 20, "criteria": "是否覆盖问题涉及的关键方面，信息是否完整"},
    {"key": "accuracy", "name": "准确性", "weight": 20, "criteria": "事实、数据与结论是否准确无误"},
    {"key": "readability", "name": "可读性", "weight": 20, "criteria": "排版、结构与表达是否清晰易读"},
    {"key": "timeliness", "name": "时效性", "weight": 20, "criteria": "信息是否为最新，是否存在过时内容"},
]

_DIMENSIONS_MULTI = DEFAULT_DIMENSIONS
_DIMENSIONS_GENERAL = DEFAULT_DIMENSIONS


def _new_benchmark(
    bid: str,
    name: str,
    description: str,
    eval_method: str,
    dimensions: list[dict[str, Any]],
    version: str = "v1.0",
    status: str = "VERIFIED",
    use_count: int = 0,
    eval_method_label: str = "",
) -> dict[str, Any]:
    return {
        "id": bid,
        "name": name,
        "description": description,
        "type": "PROMPT",
        "eval_method": eval_method,
        "eval_method_label": eval_method_label,
        "version": version,
        "status": status,
        "use_count": use_count,
        "created_by": accounts.creator_name(),
        "created_at": "2026-08-10 10:00",
        "updated_at": "2026-08-18 15:00",
        "config": {
            "prompt_template": "你是评测裁判。请依据以下维度与评分标准，对给定内容进行评测。\n{维度}\n{评分标准}\n\n查询：{query}\n待评内容：{待评内容}\n{基线内容}",
            "variables": ["{query}", "{待评内容}", "{基线内容}", "{维度}", "{评分标准}"],
            "dimensions": dimensions,
            "scoring": dict(scoring.DEFAULT_SCORING),
            "gsb": {
                "baseline_field": "baseline",
                "rules": "实验优于基线为 Good，持平为 Same，劣于基线为 Bad",
                "adjudication_dimension": "overall",
            }
            if eval_method == "GSB"
            else None,
            "confidence_enabled": True,
        },
    }


# 平台不预置任何评估基准，全部由用户创建
_benchmarks: list[dict[str, Any]] = []

# 评估报告模板：驱动任务完成时的报告生成（提示词 / 技能两类，参考评估基准的设计）。
# 首次启动播种一份内置模板（evaluation-report 技能），之后为普通数据，用户可增删改。
_report_templates: list[dict[str, Any]] = []


# ---- 数据集 ----

# 平台不预置任何数据集，全部由用户上传（CSV/JSON/JSONL）或手动录入
_datasets: list[dict[str, Any]] = []


# ---- 评测结果模拟 ----

_REASON_HIGH = ["与查询意图高度相关，信息准确且完整。", "内容贴合主题，结构清晰，可读性良好。", "整体质量较好，细节处理到位。"]
_REASON_MID = ["基本命中主题，但部分信息不够完整。", "内容相关性一般，存在少量冗余。", "信息可用，但表述略显平淡。"]
_REASON_LOW = ["与查询意图偏差较大，信息不完整。", "关键信息缺失，参考价值有限。", "内容零散，结构不清，需进一步优化。"]


def _reason_for(ratio: float) -> str:
    """入参是 0~1 的归一得分率（旧签名传 1~5 分时也能兼容：>1 视为按 5 折算）。"""
    if ratio > 1:
        ratio = ratio / 5.0
    if ratio >= 0.85:
        return _REASON_HIGH[round(ratio * 10) % len(_REASON_HIGH)]
    if ratio >= 0.5:
        return _REASON_MID[round(ratio * 10) % len(_REASON_MID)]
    return _REASON_LOW[round(ratio * 10) % len(_REASON_LOW)]


def _dim_score(query: str, content: str, dim: dict[str, Any]) -> Any:
    """确定性模拟：给出落在该维度取值域内的一个分值（整数区间取整数，枚举取枚举值）。"""
    d = scoring.normalize_dimension(dim)
    n = _stable_noise(query, content, d["key"])
    values = scoring.allowed_values(d)
    if not values:
        return 3
    # 偏向中高分：把 [0,1) 噪声映射到偏后段的下标
    idx = min(len(values) - 1, int((0.55 + n * 0.4) * len(values)))
    return values[idx]


def _evaluate_item(item: dict[str, str], benchmark: dict[str, Any]) -> dict[str, Any]:
    cfg = scoring.normalize_config(benchmark["config"])
    dims = cfg["dimensions"]
    scoring_cfg = cfg["scoring"]
    conf = round(0.66 + _stable_noise(item["query"], item["content"], "conf") * 0.32, 2)

    if benchmark["eval_method"] == "GSB":
        exp_by_key = {d["key"]: _dim_score(item["query"], item["content"], d) for d in dims}
        base_src = item.get("baseline") or item["content"]
        base_by_key = {d["key"]: _dim_score(item["query"], base_src, d) for d in dims}
        exp_agg = scoring.aggregate(dims, exp_by_key, scoring_cfg)
        base_agg = scoring.aggregate(dims, base_by_key, scoring_cfg)
        judgment, _diff = scoring.gsb_judgment(exp_agg, base_agg, scoring_cfg)
        dim_scores = [
            {"key": d["key"], "name": d["name"], "score": exp_by_key[d["key"]], "baseline_score": base_by_key[d["key"]]}
            for d in dims
        ]
        scores = {
            "judgment": judgment,
            "dimensions": dim_scores,
            "total": exp_agg["total"],
            "baseline_total": base_agg["total"],
            "total_ratio": exp_agg["total_ratio"],
            "baseline_total_ratio": base_agg["total_ratio"],
            "confidence": conf,
        }
        reason = "实验策略结果" + ("优于" if judgment == "Good" else "持平于" if judgment == "Same" else "劣于") + "基线策略。"
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
        }

    scores_by_key: dict[str, Any] = {}
    dim_scores = []
    for d in dims:
        s = _dim_score(item["query"], item["content"], d)
        scores_by_key[d["key"]] = s
        dim_scores.append(
            {"key": d["key"], "name": d["name"], "score": s, "reason": _reason_for(scoring.ratio_of(d, s) or 0.0)}
        )
    agg = scoring.aggregate(dims, scores_by_key, scoring_cfg)
    scores: dict[str, Any] = {"dimensions": dim_scores, "total": agg["total"], "total_ratio": agg["total_ratio"], "confidence": conf}
    if agg["grade_label"]:
        scores["grade_label"] = agg["grade_label"]
    if agg["vetoed"]:
        scores["vetoed"] = agg["vetoed"]
    reason = _reason_for(agg["total_ratio"])
    if agg["vetoed"]:
        reason = f"[否决] {agg['vetoed']} 触发拦截。" + reason
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
    }


def _make_report(task: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """委托给内置报告器（report.py，即 evaluation-report skill 的平台内置实现）。
    只统计 SUCCESS 条目，FAILED 条目不参与打分汇总（evaluation-report SKILL.md：跳过列表）。"""
    benchmark = next(b for b in _benchmarks if b["id"] == task["benchmark_id"])
    ok = [r for r in results if r.get("status") == "SUCCESS"]
    report = report_mod.build_report(task, ok, benchmark)
    if report.get("status") == "READY":
        # 报告 Markdown 在任务完成时一次性生成并缓存：按任务所选「评估报告模板」驱动，失败回退确定性模板
        template = next((r for r in _report_templates if r["id"] == task.get("report_template_id")), None)
        report["markdown"] = report_mod.generate_report_markdown(task, report, ok, template)
    return report


# ---- 任务 ----

# 任务类型是自由文本（前端带历史联想输入），这里只是新建任务时的默认建议值，不是枚举约束
DEFAULT_TASK_TYPE = "通用评估"

# 报告 Markdown 导出用的中文标签（现定义在 report.py，这里保留别名兼容既有引用）
REVIEW_STATUS_LABELS = report_mod.REVIEW_STATUS_LABELS
RESULT_REVIEW_STATUS_LABELS = report_mod.RESULT_REVIEW_STATUS_LABELS

# eval_method 是驱动打分引擎/必需列校验的底层机制代码，永远只有这两种，不可自定义扩展；
# 数据集/基准可以在此基础上另起一个自定义显示名（eval_method_label），二者是分开的两个概念——
# 自定义名称只影响展示，不改变底层打分规则与列校验。
METHOD_LABELS = {"MULTI_DIM": "多维度", "GSB": "GSB 对比"}

# 裁判员模型注册表。live=True 的模型走效果评估平台大模型网关真实调用（OpenAI 兼容协议，见 API.md，
# 网关无需 API Key）；其余为历史/占位标识，仅用于展示与老任务，评测时走确定性模拟引擎。
# 单价为每 1k token（人民币元，估算，用于任务费用预估）。
_MODELS = [
    {"id": "qwen3.5-plus-online", "name": "Qwen3.5 Plus（联网）", "context": 262144, "input_price": 0.004, "output_price": 0.012, "live": True},
    {"id": "qwen3.5-plus", "name": "Qwen3.5 Plus", "context": 262144, "input_price": 0.004, "output_price": 0.012, "live": True},
    {"id": "qwen3.5-plus-offline", "name": "Qwen3.5 Plus（离线）", "context": 262144, "input_price": 0.004, "output_price": 0.012, "live": True},
    {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "context": 1_000_000, "input_price": 0.001, "output_price": 0.006, "live": True},
    {"id": "deepseek-v4-flash-online", "name": "DeepSeek V4 Flash（联网）", "context": 1_000_000, "input_price": 0.001, "output_price": 0.006, "live": True},
    {"id": "Qwen3-235B-A22B-Instruct-2507", "name": "Qwen3-235B-A22B-Instruct", "context": 262144, "input_price": 0.006, "output_price": 0.018, "live": True},
    {"id": "gpt-4.1", "name": "GPT-4.1（模拟）", "context": 128000, "input_price": 0.02, "output_price": 0.08, "live": False},
]


def _model_price(model_id: str) -> dict[str, float]:
    for m in _MODELS:
        if m["id"] == model_id:
            return {"input": m["input_price"], "output": m["output_price"]}
    return {"input": 0.02, "output": 0.08}


def _method_display(record: dict[str, Any]) -> str:
    return record.get("eval_method_label") or METHOD_LABELS.get(record["eval_method"], record["eval_method"])

# 任务的可编辑 / 可复制 / 可删除状态集合，与 PRD「状态与操作逻辑」表一一对应：
# 已完成→查看报告/复制/删除；已停止→编辑/执行/复制/删除；未开始→编辑/执行/复制/删除；
# 执行中→仅可停止；执行失败→查看失败原因/重试/编辑。
EDITABLE_STATUSES = {"CREATED", "STOPPED", "FAILED"}
COPYABLE_STATUSES = {"CREATED", "STOPPED", "COMPLETED"}
DELETABLE_STATUSES = {"CREATED", "STOPPED", "COMPLETED"}


def _new_task(
    tid: str,
    name: str,
    description: str,
    benchmark_id: str,
    dataset_id: str,
    judge_model: str,
    status: str,
    progress_done: int = 0,
    review_status: str = "NOT_STARTED",
    task_type: str = DEFAULT_TASK_TYPE,
    created_at: Optional[str] = None,
    report_template_id: Optional[str] = None,
) -> dict[str, Any]:
    dataset = next(d for d in _datasets if d["id"] == dataset_id)
    benchmark = next(b for b in _benchmarks if b["id"] == benchmark_id)
    rt = next((r for r in _report_templates if r["id"] == report_template_id), None)
    dims = benchmark["config"]["dimensions"]
    total_items = dataset["total_items"]
    avg_chars = round(dataset["total_chars"] / total_items) if total_items else 0
    estimated_chars = total_items * avg_chars * len(dims)
    input_tokens = math.ceil(estimated_chars / config.CHARS_PER_TOKEN)
    output_tokens = total_items * len(dims) * config.OUTPUT_CHARS_PER_DIM
    price = _model_price(judge_model)
    cost = round(input_tokens / 1000 * price["input"] + output_tokens / 1000 * price["output"], 2)
    duration = max(1, round(total_items * len(dims) / config.REQ_PER_SEC))
    return {
        "id": tid,
        "name": name,
        "description": description,
        "task_type": task_type,
        "benchmark_id": benchmark_id,
        "benchmark_name": benchmark["name"],
        "eval_method": benchmark["eval_method"],
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "judge_model": judge_model,
        "status": status,
        "progress_done": progress_done,
        "progress_total": total_items,
        "review_status": review_status,
        "estimated_chars": estimated_chars,
        "estimated_tokens": input_tokens + output_tokens,
        "estimated_cost": cost,
        "estimated_duration_sec": duration,
        "created_by": accounts.creator_name(),
        "created_at": created_at or now(),
        "error": None,
        "cancel": False,
        "engine": config.engine_for(judge_model),
        "engine_downgraded": False,
        "actual_tokens": 0,
        "actual_cost": 0.0,
        "report_template_id": rt["id"] if rt else None,
        "report_template_name": rt["name"] if rt else None,
        "results": [],
    }


# 平台不预置任何评测任务，全部由用户创建
_tasks: list[dict[str, Any]] = []

# 人工评估中心的标注任务（manual.py 的业务逻辑读写这个列表，与 _tasks 完全并行）。
_manual_tasks: list[dict[str, Any]] = []

# 启动时从 SQLite 恢复上次的状态（db.py）；原来这四个集合纯内存、进程一重启就清空，
# 现在改成"重启读盘恢复"。.extend()/.update() 原地写入而不是重新赋值变量名，
# 这样文件里所有 `_tasks`/`_benchmarks`/`_datasets`/`_id_seq` 的既有引用不用改。
_state = db_mod.load_state()
_id_seq.update(_state["id_seq"])
_benchmarks.extend(_state["benchmarks"])
_datasets.extend(_state["datasets"])
_report_templates.extend(_state["report_templates"])
_tasks.extend(_state["tasks"])
_manual_tasks.extend(_state["manual_tasks"])
accounts.restore(_state["accounts"], _state["sessions"])
accounts.seed_and_migrate(_datasets, _benchmarks, _tasks)
del _state


def _seed_builtin_report_template() -> None:
    """首次启动（RT 序号未动过且无任何模板）时播种一份内置报告模板：evaluation-report 技能。
    之后即使用户把它删光，也不再自动补回——就是一份初始数据。"""
    if _report_templates or _id_seq["RT"] != 1000:
        return
    try:
        skill = skills_registry.load_builtin_skill("evaluation-report")
    except (KeyError, FileNotFoundError, ValueError):
        return
    skill.pop("skill_dir", None)
    _report_templates.append(
        {
            "id": _next_id("RT"),
            "name": "默认评估报告",
            "description": "平台内置的评估总报告技能（evaluation-report）：整体结论→GSB 专项→分维度问题→典型错误 case→改进建议。",
            "type": "SKILL",
            "version": "v1.0",
            "status": "VERIFIED",
            "created_by": "系统内置",
            "created_at": now(),
            "updated_at": now(),
            "config": {
                "prompt_template": None,
                "sections": [],
                "skill": skill,
                "skill_ref": {"source": "builtin", "skill_id": "evaluation-report", "skill_version": skill.get("version", "")},
            },
        }
    )


_seed_builtin_report_template()

app.include_router(accounts.router)


def _persist_state() -> None:
    """把当前内存状态整体落盘。调用方必须已持有 _lock——db.save_state 在锁内做
    json 序列化，避免快照期间被其它线程（比如后台评测线程）改到一半。"""
    db_mod.save_state(
        _tasks, _benchmarks, _datasets, _id_seq, _report_templates, *accounts.snapshot(),
        manual_tasks=_manual_tasks,
    )


def _persist_loop() -> None:
    """兜底：后台评测线程会在请求-响应周期之外持续修改 task 状态（进度/结果/报告），
    定时快照能兜住这段时间的变更，不用在评测循环内部每条样本都手动加一次持久化调用。"""
    while True:
        time.sleep(2)
        try:
            with _lock:
                _persist_state()
        except Exception:  # noqa: BLE001 - 持久化失败不应该打断服务，下一轮重试
            pass


threading.Thread(target=_persist_loop, daemon=True).start()


@app.middleware("http")
async def _persist_after_mutation(request, call_next):
    """请求触发的即时持久化：写请求响应后立刻落盘一次，不用等定时快照，
    也不用在每个 POST/PUT/DELETE handler 里手动补一行持久化调用。"""
    response = await call_next(request)
    if request.method in ("POST", "PUT", "DELETE") and request.url.path.startswith("/api/"):
        try:
            with _lock:
                _persist_state()
        except Exception:  # noqa: BLE001 - 持久化失败不应该影响本次请求已经返回的响应
            pass
    return response


# 需要登录才能访问的接口前缀里，这些子路径豁免（登录本身 + 非 /api 的静态资源/健康检查）
_AUTH_EXEMPT = {"/api/auth/login"}


@app.middleware("http")
async def _require_auth(request: Request, call_next):
    """统一入口鉴权：/api/* 一律需要有效会话；除 /api/auth/* 外还需在组织内。
    在一处集中处理，避免给每个业务路由挂 Depends。"""
    path = request.url.path
    if not path.startswith("/api/") or path in _AUTH_EXEMPT:
        return await call_next(request)
    account = accounts.resolve(request)
    if not account:
        return JSONResponse({"detail": "请先登录"}, status_code=401)
    if not path.startswith("/api/auth/") and not account.get("org_id"):
        return JSONResponse({"detail": "你尚未加入任何组织，请联系组织成员邀请你加入"}, status_code=403)
    token = accounts.bind(account)
    try:
        return await call_next(request)
    finally:
        accounts.unbind(token)


# ---- API 模型 ----

class DatasetCreate(BaseModel):
    name: str
    description: str = ""
    eval_method: str = "MULTI_DIM"
    eval_method_label: str = ""
    mode: str = "manual"
    rows: Optional[list[dict[str, str]]] = None


class BenchmarkCreate(BaseModel):
    name: str
    description: str = ""
    eval_type: str = "PROMPT"
    eval_method: str = "MULTI_DIM"
    eval_method_label: str = ""
    dimensions: list[dict[str, Any]] = []
    prompt_template: Optional[str] = None
    skill: Optional[dict[str, Any]] = None
    # 技能来源：{"source": "builtin"|"custom", "skill_id": str}。source=builtin 时后端按 skill_id
    # 从仓库 skills/ 加载并填充 config.skill，同时记录版本快照（技术方案 §8.5.3）。
    skill_ref: Optional[dict[str, Any]] = None
    gsb_rules: Optional[str] = None
    gsb_adjudication_dimension: Optional[str] = None
    confidence_enabled: bool = True
    # 聚合配置：{mode, display_scale, low_score_ratio, gsb_good_threshold, grade_thresholds}
    # 见 scoring.py / 多维度评估基准优化设计.md；缺省走 weighted_raw（还原旧的 Σ(score×weight)/100）。
    scoring: Optional[dict[str, Any]] = None


class BenchmarkUpdate(BenchmarkCreate):
    pass


class ReportTemplateCreate(BaseModel):
    name: str
    description: str = ""
    tpl_type: str = "PROMPT"  # PROMPT | SKILL
    prompt_template: Optional[str] = None
    sections: list[str] = []
    skill: Optional[dict[str, Any]] = None
    skill_ref: Optional[dict[str, Any]] = None


class ReportTemplateUpdate(ReportTemplateCreate):
    pass


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    task_type: str = DEFAULT_TASK_TYPE
    benchmark_id: str
    dataset_id: str
    judge_model: str = "deepseek-v4-flash"
    # 评估报告模板 ID（在「评估报告模板」模块维护）；None / 不存在时任务完成回退确定性五段式模板
    report_template_id: Optional[str] = None


class TaskUpdate(TaskCreate):
    pass


class ReviewUpdate(BaseModel):
    row_index: int
    review_status: str
    adjusted_scores: Optional[dict[str, Any]] = None
    review_comment: str = ""


# ---- 工具函数 ----

def _find_dataset(dataset_id: str) -> dict[str, Any]:
    for d in _datasets:
        if d["id"] == dataset_id:
            return d
    raise HTTPException(status_code=404, detail="数据集不存在")


def _find_benchmark(benchmark_id: str) -> dict[str, Any]:
    for b in _benchmarks:
        if b["id"] == benchmark_id:
            return b
    raise HTTPException(status_code=404, detail="评估基准不存在")


def _find_task(task_id: str) -> dict[str, Any]:
    for t in _tasks:
        if t["id"] == task_id:
            return t
    raise HTTPException(status_code=404, detail="任务不存在")


def _public_dataset(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != "samples"}


def _public_task(t: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in t.items() if k != "results"}


def _tasks_using_dataset(dataset_id: str) -> list[dict[str, Any]]:
    return [t for t in _tasks if t["dataset_id"] == dataset_id]


def _tasks_using_benchmark(benchmark_id: str) -> list[dict[str, Any]]:
    return [t for t in _tasks if t["benchmark_id"] == benchmark_id]


def _dataset_to_csv(dataset: dict[str, Any]) -> str:
    fieldnames = ["row_index", "query", "content"] + (["baseline"] if dataset["eval_method"] == "GSB" else [])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in dataset["samples"]:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def _template_csv(eval_method: str) -> str:
    fieldnames = REQUIRED_COLUMNS.get(eval_method, REQUIRED_COLUMNS["MULTI_DIM"])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in _TEMPLATE_EXAMPLES:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def _parse_xlsx_rows(raw: bytes) -> tuple[list[str], list[list[Any]]]:
    """读取 xlsx 第一个工作表，返回 (表头, 数据行列表)；用 openpyxl（report.py 已依赖，无需新增）。"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return [], []
        header = [str(h).strip() if h is not None else "" for h in header_row]
        data_rows = [
            list(row) for row in rows_iter if any(cell is not None and str(cell).strip() for cell in row)
        ]
        return header, data_rows
    finally:
        wb.close()


def _parse_upload_rows(raw: bytes, filename: str, eval_method: str) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """解析上传文件为标准行，返回 (有效行, 逐行错误列表)。错误定位到源文件行号（含表头）。
    xlsx 是二进制格式，必须在文本解码之前单独分支处理，不能走下面的 utf-8 解码路径。"""
    required = REQUIRED_COLUMNS.get(eval_method, REQUIRED_COLUMNS["MULTI_DIM"])
    lower = filename.lower()
    errors: list[dict[str, Any]] = []
    raw_rows: list[tuple[int, dict[str, Any]]] = []

    if lower.endswith(".xlsx"):
        try:
            header, data_rows = _parse_xlsx_rows(raw)
        except Exception as exc:  # openpyxl 对损坏/非 xlsx 文件会抛出多种异常，统一兜底
            return [], [{"line": 0, "message": f"Excel 文件解析失败，请确认文件未损坏且为 .xlsx 格式（{exc}）"}]
        if not header:
            return [], [{"line": 1, "message": "未识别到表头，请使用模板中的列名"}]
        for i, row in enumerate(data_rows, start=2):
            row_dict = {header[j]: ("" if j >= len(row) or row[j] is None else str(row[j])) for j in range(len(header))}
            raw_rows.append((i, row_dict))
        raw_rows = _remap_rows(raw_rows, required)
        valid_rows: list[dict[str, str]] = []
        for line_no, row in raw_rows:
            missing = [c for c in required if not str(row.get(c, "")).strip()]
            if missing:
                labels = "、".join(COLUMN_LABELS.get(c, c) for c in missing)
                errors.append({"line": line_no, "message": f"缺少必填字段：{labels}"})
                continue
            valid_rows.append({c: str(row.get(c, "")).strip() for c in ["query", "content", "baseline"]})
        return valid_rows, errors

    if lower.endswith(".xls"):
        return [], [{"line": 0, "message": "暂不支持旧版 .xls 二进制格式，请另存为 .xlsx 或 .csv 后上传"}]

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [{"line": 0, "message": "文件编码不支持，请使用 UTF-8 编码的文件"}]

    if lower.endswith(".jsonl"):
        for i, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw_rows.append((i, json.loads(line)))
            except json.JSONDecodeError as exc:
                errors.append({"line": i, "message": f"JSON 解析失败：{exc.msg}"})
    elif lower.endswith(".json"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return [], [{"line": exc.lineno, "message": f"JSON 解析失败：{exc.msg}"}]
        if not isinstance(payload, list):
            return [], [{"line": 1, "message": "JSON 文件根节点必须是数组"}]
        for i, item in enumerate(payload, start=1):
            raw_rows.append((i + 1, item if isinstance(item, dict) else {}))
            if not isinstance(item, dict):
                errors.append({"line": i + 1, "message": "元素必须是对象（{query, content, ...}）"})
    elif lower.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], [{"line": 1, "message": "未识别到表头，请使用模板中的列名"}]
        for i, row in enumerate(reader, start=2):
            raw_rows.append((i, row))
    else:
        return [], [{"line": 0, "message": "不支持的文件格式，请上传 CSV / JSON / JSONL / XLSX"}]

    raw_rows = _remap_rows(raw_rows, required)
    valid_rows: list[dict[str, str]] = []
    for line_no, row in raw_rows:
        missing = [c for c in required if not str(row.get(c, "")).strip()]
        if missing:
            labels = "、".join(COLUMN_LABELS.get(c, c) for c in missing)
            errors.append({"line": line_no, "message": f"缺少必填字段：{labels}"})
            continue
        valid_rows.append({c: str(row.get(c, "")).strip() for c in ["query", "content", "baseline"]})

    return valid_rows, errors


def _failed_result(sample: dict[str, Any], benchmark: dict[str, Any], err: str) -> dict[str, Any]:
    return {
        "row_index": sample["row_index"],
        "query": sample["query"],
        "content": sample["content"],
        "baseline": sample.get("baseline", "") if benchmark["eval_method"] == "GSB" else "",
        "status": "FAILED",
        "scores": {},
        "reason": "",
        "confidence": None,
        "review_status": "PENDING",
        "engine": "agent",
        "error": err,
    }


def _run_evaluation(task_id: str) -> None:
    """异步执行评测：按 config.engine_for 决定走大模型网关真实调用还是确定性模拟；
    真实调用用线程池并发，失败率过高时对剩余条目自动降级为模拟（技术方案 §7.3 / §8.5.6）。"""

    def run() -> None:
        time.sleep(0.3)
        with _lock:
            task = _find_task(task_id)
            benchmark = _find_benchmark(task["benchmark_id"])
            dataset = _find_dataset(task["dataset_id"])
            samples = list(dataset["samples"])
            model = task["judge_model"]
            eng = config.engine_for(model)
            task["status"] = "RUNNING"
            task["error"] = None
            task["cancel"] = False
            task["results"] = []
            task["progress_done"] = 0
            task["engine"] = eng
            task["engine_downgraded"] = False
            task["actual_tokens"] = 0
            task["actual_cost"] = 0.0

        skill = benchmark["config"].get("skill") if benchmark["type"] == "SKILL" else None

        if eng == "agent" and not llm.is_live(model):
            with _lock:
                t = _find_task(task_id)
                t["status"] = "FAILED"
                t["error"] = f"评测引擎为 agent，但裁判员模型「{model}」不在大模型网关可用列表内"
            return

        price = _model_price(model)
        state = {"downgraded": False, "fail": 0, "done": 0, "tokens": 0, "cost": 0.0}

        def eval_one(sample: dict[str, Any]) -> dict[str, Any]:
            if eng == "simulated" or state["downgraded"]:
                return _evaluate_item(sample, benchmark)
            try:
                return engine_mod.evaluate_item_llm(sample, benchmark, model, skill)
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻塞整体，落 FAILED 并记录
                return _failed_result(sample, benchmark, str(exc))

        workers = config.JUDGE_CONCURRENCY if eng == "agent" else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(samples), workers):
                with _lock:
                    if _find_task(task_id).get("cancel"):
                        _find_task(task_id)["status"] = "STOPPED"
                        return
                batch = samples[start : start + workers]
                batch_results = list(pool.map(eval_one, batch))
                with _lock:
                    task = _find_task(task_id)
                    for r in batch_results:
                        usage = r.pop("_usage", None)
                        if usage:
                            state["tokens"] += usage["input_tokens"] + usage["output_tokens"]
                            state["cost"] += (
                                usage["input_tokens"] / 1000 * price["input"]
                                + usage["output_tokens"] / 1000 * price["output"]
                            )
                        state["fail"] += 1 if r["status"] == "FAILED" else 0
                        state["done"] += 1
                        task["results"].append(r)
                    task["progress_done"] = state["done"]
                    task["actual_tokens"] = state["tokens"]
                    task["actual_cost"] = round(state["cost"], 4)
                    if (
                        eng == "agent"
                        and not state["downgraded"]
                        and state["done"] >= config.DOWNGRADE_MIN_SAMPLES
                        and state["fail"] / state["done"] > config.DOWNGRADE_FAIL_RATIO
                    ):
                        state["downgraded"] = True
                        task["engine_downgraded"] = True
                if eng == "simulated":
                    time.sleep(0.02)

        # 全部样本都失败（例如网关不可用 / 结构化输出持续不合规）时，标记任务为执行失败，
        # 让用户能直接「重试」，而不是拿到一份空报告。
        task = _find_task(task_id)
        results = task.get("results", [])
        if results and all(r.get("status") == "FAILED" for r in results):
            first_err = next((r.get("error") for r in results if r.get("error")), "")
            with _lock:
                task["status"] = "FAILED"
                task["error"] = f"全部 {len(results)} 条样本评测失败：{first_err}"
                task["report"] = None
            return

        # 评测跑完先把任务标记为已完成，让列表/详情页的状态与进度立即到位；
        # 报告生成含一次裁判员模型调用（自由格式 Markdown），耗时可达数十秒，
        # 放在标记完成之后、锁之外单独做，报告没好之前 report 为 None（前端展示"生成中"）。
        with _lock:
            task["status"] = "COMPLETED"
            task["review_status"] = "NOT_STARTED"
            task["report"] = None
        try:
            report = _make_report(task, task["results"])
        except Exception:  # noqa: BLE001 - 报告失败不影响任务完成
            logging.getLogger(__name__).exception("任务 %s 报告生成失败", task_id)
            report = None
        with _lock:
            task["report"] = report

    threading.Thread(target=run, daemon=True).start()


# ---- 路由 ----


@app.get("/health", tags=["platform"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview/metrics")
def overview_metrics(range_: str = "30d", start: str = "", end: str = "") -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc).astimezone().replace(tzinfo=None)
    bucket = "day"
    if range_ == "today":
        start_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now_dt
        label = "今日评估量"
        bucket = "hour"
    elif range_ == "7d":
        start_dt = (now_dt - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now_dt
        label = "近7天评估量"
    elif range_ == "custom" and start and end:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            raise HTTPException(status_code=400, detail="自定义时间范围格式应为 YYYY-MM-DD")
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
        label = "自定义时段评估量"
        range_ = "custom"
    else:
        range_ = "30d"
        start_dt = (now_dt - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now_dt
        label = "近30天评估量"

    def created_at(t: dict[str, Any]) -> Optional[datetime]:
        try:
            return datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    scoped = [t for t in _tasks if (c := created_at(t)) and start_dt <= c <= end_dt]
    completed = [t for t in scoped if t["status"] == "COMPLETED"]
    running = [t for t in _tasks if t["status"] == "RUNNING"]  # 执行中任务是实时状态，不受时间范围筛选影响
    total_items = sum(t["progress_total"] for t in scoped)
    evaluated = sum(t["progress_done"] for t in scoped)

    # 任务类型是自由文本，这里按实际出现过的类型动态分组统计，而不是写死两个枚举桶
    type_counts: dict[str, int] = {}
    for t in scoped:
        key = t["task_type"] or "未分类"
        type_counts[key] = type_counts.get(key, 0) + 1
    by_type = [{"name": k, "value": v} for k, v in sorted(type_counts.items(), key=lambda kv: -kv[1])]

    trend: list[dict[str, Any]] = []
    if bucket == "hour":
        for h in range(0, 24, 2):
            slot_start = start_dt.replace(hour=h)
            slot_end = slot_start + timedelta(hours=2)
            value = sum(t["progress_done"] for t in scoped if (c := created_at(t)) and slot_start <= c < slot_end)
            trend.append({"label": f"{h:02d}:00", "value": value})
    else:
        cur = start_dt
        while cur.date() <= end_dt.date():
            slot_end = cur + timedelta(days=1)
            value = sum(t["progress_done"] for t in scoped if (c := created_at(t)) and cur <= c < slot_end)
            trend.append({"label": cur.strftime("%m-%d"), "value": value})
            cur += timedelta(days=1)

    return {
        "range": range_,
        "start": start_dt.strftime("%Y-%m-%d"),
        "end": end_dt.strftime("%Y-%m-%d"),
        "metrics": [
            {"key": "range_total", "label": label, "value": total_items, "unit": "条"},
            {"key": "completed", "label": "已完成任务", "value": len(completed), "unit": "个"},
            {"key": "running", "label": "执行中任务", "value": len(running), "unit": "个"},
            {"key": "evaluated", "label": "已评测样本", "value": evaluated, "unit": "条"},
        ],
        "by_type": by_type,
        "trend": trend,
    }


def _dataset_out(d: dict[str, Any]) -> dict[str, Any]:
    out = _public_dataset(d)
    out["used_by_tasks"] = len(_tasks_using_dataset(d["id"]))
    out["eval_method_display"] = _method_display(d)
    return out


@app.get("/api/datasets")
def list_datasets(source: str = "", created_by: str = "", q: str = "", start: str = "", end: str = "") -> dict[str, Any]:
    items = list(_datasets)
    if source:
        items = [d for d in items if d["source"] == source]
    if created_by:
        items = [d for d in items if d["created_by"] == created_by]
    if q:
        items = [d for d in items if q.lower() in d["name"].lower() or q.lower() in d["id"].lower()]
    if start:
        items = [d for d in items if d["created_at"][:10] >= start]
    if end:
        items = [d for d in items if d["created_at"][:10] <= end]
    return {"items": [_dataset_out(d) for d in items]}


@app.post("/api/datasets")
def create_dataset(body: DatasetCreate) -> dict[str, Any]:
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="请填写数据集名称")
    if not body.rows:
        raise HTTPException(status_code=400, detail="请至少录入一条数据，或改用文件上传")
    if any(d["name"] == body.name.strip() for d in _datasets):
        raise HTTPException(status_code=400, detail="同名数据集已存在，请更换名称")
    required = REQUIRED_COLUMNS.get(body.eval_method, REQUIRED_COLUMNS["MULTI_DIM"])
    did = _next_id("DS")
    samples = []
    for i, row in enumerate(body.rows):
        missing = [c for c in required if not str(row.get(c, "")).strip()]
        if missing:
            labels = "、".join(COLUMN_LABELS.get(c, c) for c in missing)
            raise HTTPException(status_code=422, detail=f"第 {i + 1} 行缺少必填字段：{labels}")
        samples.append(
            {
                "id": f"item-{i + 1}",
                "row_index": i + 1,
                "query": row.get("query", "").strip(),
                "content": row.get("content", "").strip(),
                "baseline": row.get("baseline", "").strip(),
            }
        )
    dataset = {
        "id": did,
        "name": body.name.strip(),
        "description": body.description,
        "source": "UPLOAD",
        "eval_method": body.eval_method,
        "eval_method_label": body.eval_method_label,
        "format": "JSON",
        "total_items": len(samples),
        "total_chars": _chars(samples),
        "status": "READY",
        "created_by": accounts.creator_name(),
        "created_at": now(),
        "samples": samples,
    }
    with _lock:
        _datasets.append(dataset)
    return _dataset_out(dataset)


@app.get("/api/datasets/template")
def dataset_template(eval_method: str = "MULTI_DIM") -> Response:
    csv_text = _template_csv(eval_method)
    filename = "多维度模板.csv" if eval_method == "MULTI_DIM" else "GSB模板.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.post("/api/datasets/upload")
async def upload_dataset(
    name: str = Form(...),
    description: str = Form(""),
    eval_method: str = Form("MULTI_DIM"),
    eval_method_label: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not name.strip():
        raise HTTPException(status_code=400, detail="请填写数据集名称")
    if any(d["name"] == name.strip() for d in _datasets):
        raise HTTPException(status_code=400, detail="同名数据集已存在，请更换名称")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 50MB 限制")
    rows, errors = _parse_upload_rows(raw, file.filename or "", eval_method)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "文件校验未通过，请修正后重新上传", "errors": errors[:50]})
    if not rows:
        raise HTTPException(status_code=422, detail={"message": "文件中没有可用数据行", "errors": []})

    samples = [
        {"id": f"item-{i + 1}", "row_index": i + 1, "query": r["query"], "content": r["content"], "baseline": r.get("baseline", "")}
        for i, r in enumerate(rows)
    ]
    did = _next_id("DS")
    fmt = (file.filename or "").rsplit(".", 1)[-1].upper() if "." in (file.filename or "") else "CSV"
    dataset = {
        "id": did,
        "name": name.strip(),
        "description": description,
        "source": "UPLOAD",
        "eval_method": eval_method,
        "eval_method_label": eval_method_label,
        "format": fmt,
        "total_items": len(samples),
        "total_chars": _chars(samples),
        "status": "READY",
        "created_by": accounts.creator_name(),
        "created_at": now(),
        "samples": samples,
    }
    with _lock:
        _datasets.append(dataset)
    return _dataset_out(dataset)


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = _find_dataset(dataset_id)
    result = _dataset_out(dataset)
    result["samples"] = dataset["samples"][:10]
    result["used_by"] = [{"id": t["id"], "name": t["name"], "status": t["status"]} for t in _tasks_using_dataset(dataset_id)]
    return result


@app.get("/api/datasets/{dataset_id}/download")
def download_dataset(dataset_id: str) -> Response:
    dataset = _find_dataset(dataset_id)
    csv_text = _dataset_to_csv(dataset)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(dataset['name'] + '.csv')}"},
    )


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = _find_dataset(dataset_id)
    using = _tasks_using_dataset(dataset_id)
    if using:
        names = "、".join(t["name"] for t in using[:3])
        raise HTTPException(status_code=400, detail=f"数据集正被任务引用（{names} 等），无法删除")
    with _lock:
        _datasets.remove(dataset)
    return {"ok": True}


def _benchmark_out(b: dict[str, Any]) -> dict[str, Any]:
    out = dict(b)
    out["use_count"] = len(_tasks_using_benchmark(b["id"]))
    out["eval_method_display"] = _method_display(b)
    return out


@app.get("/api/benchmarks")
def list_benchmarks(eval_type: str = "", eval_method: str = "", created_by: str = "", q: str = "") -> dict[str, Any]:
    items = list(_benchmarks)
    if eval_type:
        items = [b for b in items if b["type"] == eval_type]
    if eval_method:
        items = [b for b in items if b["eval_method"] == eval_method]
    if created_by:
        items = [b for b in items if b["created_by"] == created_by]
    if q:
        items = [b for b in items if q.lower() in b["name"].lower() or q.lower() in b["id"].lower()]
    return {"items": [_benchmark_out(b) for b in items]}


def _resolve_skill(
    skill_ref: Optional[dict[str, Any]], uploaded: Optional[dict[str, Any]]
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """返回 (skill_config, skill_ref)。source=builtin 时按 skill_id 从仓库 skills/ 加载并记录
    版本快照（技术方案 §8.5.3）；source=custom 沿用上传解析结果。评估基准 / 评估报告模板共用。"""
    ref = skill_ref or {}
    if ref.get("source") == "builtin":
        sid = str(ref.get("skill_id") or "")
        try:
            skill = skills_registry.load_builtin_skill(sid)
        except (KeyError, FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"内置技能加载失败：{exc}")
        skill.pop("skill_dir", None)  # 不向前端暴露服务器绝对路径
        return skill, {"source": "builtin", "skill_id": sid, "skill_version": skill.get("version", "")}
    if uploaded:
        return uploaded, {"source": "custom", "skill_id": uploaded.get("name", "")}
    return None, None


def _validate_benchmark_scoring(dimensions: list[dict[str, Any]], scoring_cfg: dict[str, Any]) -> None:
    """维度分制 / 聚合配置校验；不合法抛 422（技术方案：入口层校验）。"""
    if not dimensions:
        raise HTTPException(status_code=422, detail="至少需要 1 个评估维度")
    seen_keys: set[str] = set()
    for d in dimensions:
        key = str(d.get("key") or "").strip()
        name = str(d.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="维度名称不能为空")
        if key and key in seen_keys:
            raise HTTPException(status_code=422, detail=f"维度 key 重复：{key}")
        seen_keys.add(key)
        scale = d.get("scale") or {}
        stype = scale.get("type", "integer")
        if stype == "integer":
            lo, hi = scale.get("min", 1), scale.get("max", 5)
            try:
                lo, hi = int(lo), int(hi)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"维度「{name}」的 min/max 非整数")
            if hi <= lo:
                raise HTTPException(status_code=422, detail=f"维度「{name}」的 max 必须大于 min")
            values = [lv.get("value") for lv in (scale.get("levels") or [])]
        elif stype == "enum":
            values = [str(lv.get("value")) for lv in (scale.get("levels") or [])]
            if len(values) < 2:
                raise HTTPException(status_code=422, detail=f"枚举维度「{name}」至少需要 2 个取值")
        else:
            raise HTTPException(status_code=422, detail=f"维度「{name}」的分制类型不支持：{stype}")
        if len(values) != len(set(values)):
            raise HTTPException(status_code=422, detail=f"维度「{name}」的档位取值重复")
        thr = d.get("veto_below")
        if thr is not None and stype == "integer" and not (lo < int(thr) <= hi):
            raise HTTPException(status_code=422, detail=f"维度「{name}」的一票否决阈值需在 ({lo}, {hi}] 内")

    mode = scoring_cfg.get("mode", "weighted_raw")
    if mode in ("weighted_raw", "weighted_normalized"):
        weights = [float(d.get("weight") or 0) for d in dimensions]
        wsum = round(sum(weights), 2)
        if wsum not in (0.0, 100.0):
            raise HTTPException(status_code=422, detail=f"加权模式下维度权重合计需为 100%（当前 {wsum}%）或全部留空表示等权")
    if mode == "weighted_raw":
        types = {(d.get("scale") or {}).get("type", "integer") for d in dimensions}
        ranges = {((d.get("scale") or {}).get("min", 1), (d.get("scale") or {}).get("max", 5)) for d in dimensions}
        if types != {"integer"} or len(ranges) > 1:
            raise HTTPException(
                status_code=422, detail="「加权求和」要求所有维度同为一致的整数分制；混合分制请改用「加权归一」"
            )


def _apply_benchmark_body(benchmark: dict[str, Any], body: BenchmarkCreate) -> None:
    dimensions = body.dimensions or (
        [dict(d) for d in _DIMENSIONS_MULTI] if body.eval_method == "MULTI_DIM" else [dict(d) for d in _DIMENSIONS_GENERAL]
    )
    scoring_cfg = scoring.normalize_scoring({"scoring": body.scoring or {}})
    if body.eval_type != "SKILL":
        _validate_benchmark_scoring(dimensions, scoring_cfg)
    benchmark["name"] = body.name
    benchmark["description"] = body.description
    benchmark["type"] = body.eval_type
    benchmark["eval_method"] = body.eval_method
    benchmark["eval_method_label"] = body.eval_method_label
    benchmark["config"]["dimensions"] = [scoring.normalize_dimension(d) for d in dimensions]
    benchmark["config"]["scoring"] = scoring_cfg
    if body.eval_type == "SKILL":
        skill, skill_ref = _resolve_skill(body.skill_ref, body.skill)
        if skill:
            benchmark["config"]["skill"] = skill
            benchmark["config"]["skill_ref"] = skill_ref
        benchmark["config"]["prompt_template"] = None
    else:
        if body.prompt_template:
            benchmark["config"]["prompt_template"] = body.prompt_template
        benchmark["config"]["skill"] = None
        benchmark["config"].pop("skill_ref", None)
    benchmark["config"]["confidence_enabled"] = body.confidence_enabled
    if body.eval_method == "GSB":
        benchmark["config"]["gsb"] = {
            "baseline_field": "baseline",
            "rules": body.gsb_rules or "实验优于基线为 Good，持平为 Same，劣于基线为 Bad",
            "adjudication_dimension": body.gsb_adjudication_dimension or "overall",
        }
    else:
        benchmark["config"]["gsb"] = None


@app.post("/api/benchmarks")
def create_benchmark(body: BenchmarkCreate) -> dict[str, Any]:
    if any(b["name"] == body.name and b["type"] == body.eval_type for b in _benchmarks):
        raise HTTPException(status_code=400, detail="同评估类型下已存在同名基准")
    dimensions = body.dimensions or (
        [dict(d) for d in _DIMENSIONS_MULTI] if body.eval_method == "MULTI_DIM" else [dict(d) for d in _DIMENSIONS_GENERAL]
    )
    benchmark = _new_benchmark(
        _next_id("BM"),
        body.name,
        body.description,
        body.eval_method,
        dimensions,
        status="DRAFT",
        use_count=0,
        eval_method_label=body.eval_method_label,
    )
    benchmark["created_by"] = accounts.creator_name()
    benchmark["created_at"] = now()
    benchmark["updated_at"] = now()
    _apply_benchmark_body(benchmark, body)
    with _lock:
        _benchmarks.append(benchmark)
    return _benchmark_out(benchmark)


@app.post("/api/benchmarks/parse-skill")
async def parse_skill(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="技能包超过 10MB 限制")
    skill, err = _parse_skill_package(raw, file.filename or "")
    if err:
        raise HTTPException(status_code=422, detail=err)
    return skill


@app.get("/api/skills/builtin")
def builtin_skills() -> dict[str, Any]:
    """平台内置技能：创建「技能 Skill」类型基准时可直接选用（multi-dimension-evaluation /
    gsb-evaluation）；evaluation-report 作为内置报告器，随任务完成自动产出报告。"""
    return {"items": skills_registry.list_builtin()}


class PromptValidateBody(BaseModel):
    prompt_template: str
    eval_method: str = "MULTI_DIM"
    dimensions: list[dict[str, Any]] = []
    dry_run: bool = False
    judge_model: str = "deepseek-v4-flash"


_PROMPT_VARS = {"{query}", "{待评内容}", "{基线内容}", "{维度}", "{评分标准}"}


@app.post("/api/benchmarks/validate-prompt")
def validate_prompt(body: PromptValidateBody) -> dict[str, Any]:
    """校验提示词模板：变量白名单 + 必备变量；dry_run=true 时用一条示例样本真实跑一次
    裁判员模型，返回结构化结果供预览（技术方案 §9）。"""
    used = set(re.findall(r"\{[^}]+\}", body.prompt_template))
    unknown = sorted(v for v in used if v not in _PROMPT_VARS)
    warnings: list[str] = []
    if unknown:
        warnings.append(f"存在未知变量：{'、'.join(unknown)}（仅支持 {'、'.join(sorted(_PROMPT_VARS))}）")
    if "{待评内容}" not in used and "{query}" not in used:
        warnings.append("建议至少包含 {query} 或 {待评内容} 变量")
    if body.eval_method == "GSB" and "{基线内容}" not in used:
        warnings.append("GSB 方式建议包含 {基线内容} 变量")

    result: dict[str, Any] = {"valid": not unknown, "warnings": warnings, "variables_used": sorted(used)}

    if body.dry_run:
        if not llm.is_live(body.judge_model):
            raise HTTPException(status_code=400, detail=f"模型「{body.judge_model}」不可用或未配置 API Key，无法试跑")
        dims = body.dimensions or (_DIMENSIONS_MULTI if body.eval_method == "MULTI_DIM" else _DIMENSIONS_GENERAL)
        fake_benchmark = {
            "eval_method": body.eval_method,
            "type": "PROMPT",
            "config": {
                "prompt_template": body.prompt_template,
                "dimensions": [dict(d) for d in dims],
                "gsb": {"rules": "实验优于基线为 Good", "adjudication_dimension": "overall"} if body.eval_method == "GSB" else None,
                "confidence_enabled": True,
            },
        }
        ex = _TEMPLATE_EXAMPLES[0]
        sample = {
            "row_index": 1,
            "query": ex["query"],
            "content": ex["content"],
            "baseline": ex["baseline"] if body.eval_method == "GSB" else "",
        }
        try:
            preview = engine_mod.evaluate_item_llm(sample, fake_benchmark, body.judge_model, None)
        except llm.LlmError as exc:
            raise HTTPException(status_code=502, detail=f"试跑失败：{exc}")
        preview.pop("_usage", None)
        result["dry_run_result"] = preview

    return result


@app.get("/api/benchmarks/{benchmark_id}")
def get_benchmark(benchmark_id: str) -> dict[str, Any]:
    benchmark = _find_benchmark(benchmark_id)
    out = _benchmark_out(benchmark)
    out["used_by"] = [{"id": t["id"], "name": t["name"], "status": t["status"]} for t in _tasks_using_benchmark(benchmark_id)]
    return out


@app.put("/api/benchmarks/{benchmark_id}")
def update_benchmark(benchmark_id: str, body: BenchmarkUpdate) -> dict[str, Any]:
    benchmark = _find_benchmark(benchmark_id)
    if any(b["name"] == body.name and b["type"] == body.eval_type and b["id"] != benchmark_id for b in _benchmarks):
        raise HTTPException(status_code=400, detail="同评估类型下已存在同名基准")
    with _lock:
        _apply_benchmark_body(benchmark, body)
        benchmark["status"] = "DRAFT"  # 内容变更后需要重新验证
        benchmark["updated_at"] = now()
    return _benchmark_out(benchmark)


@app.post("/api/benchmarks/{benchmark_id}/copy")
def copy_benchmark(benchmark_id: str) -> dict[str, Any]:
    source = _find_benchmark(benchmark_id)
    clone = json.loads(json.dumps(source))
    clone["id"] = _next_id("BM")
    clone["name"] = f"{source['name']}_副本"
    clone["version"] = "v1.0"
    clone["status"] = "DRAFT"
    clone["use_count"] = 0
    clone["created_by"] = accounts.creator_name()
    clone["created_at"] = now()
    clone["updated_at"] = now()
    with _lock:
        _benchmarks.append(clone)
    return _benchmark_out(clone)


@app.delete("/api/benchmarks/{benchmark_id}")
def delete_benchmark(benchmark_id: str) -> dict[str, Any]:
    benchmark = _find_benchmark(benchmark_id)
    using = _tasks_using_benchmark(benchmark_id)
    if using:
        names = "、".join(t["name"] for t in using[:3])
        raise HTTPException(status_code=400, detail=f"评估基准正被任务引用（{names} 等），无法删除")
    with _lock:
        _benchmarks.remove(benchmark)
    return {"ok": True}


# ---- 评估报告模板 ----


def _find_report_template(rt_id: str) -> dict[str, Any]:
    for r in _report_templates:
        if r["id"] == rt_id:
            return r
    raise HTTPException(status_code=404, detail="评估报告模板不存在")


def _tasks_using_report_template(rt_id: str) -> list[dict[str, Any]]:
    return [t for t in _tasks if t.get("report_template_id") == rt_id]


def _report_template_out(r: dict[str, Any]) -> dict[str, Any]:
    out = dict(r)
    out["use_count"] = len(_tasks_using_report_template(r["id"]))
    return out


def _apply_report_template_body(rt: dict[str, Any], body: ReportTemplateCreate) -> None:
    rt["name"] = body.name.strip()
    rt["description"] = body.description
    rt["type"] = body.tpl_type
    cfg = rt.setdefault("config", {})
    if body.tpl_type == "SKILL":
        skill, skill_ref = _resolve_skill(body.skill_ref, body.skill)
        if not skill:
            raise HTTPException(status_code=422, detail="技能类型报告模板需要选择内置技能或上传技能包")
        cfg["skill"] = skill
        cfg["skill_ref"] = skill_ref
        cfg["prompt_template"] = None
        cfg["sections"] = []
    else:
        cfg["prompt_template"] = (body.prompt_template or "").strip() or report_mod.DEFAULT_REPORT_PROMPT
        sections = [s.strip() for s in body.sections if s and s.strip()]
        cfg["sections"] = sections or list(report_mod.DEFAULT_REPORT_SECTIONS)
        cfg["skill"] = None
        cfg.pop("skill_ref", None)


@app.get("/api/report-templates")
def list_report_templates(tpl_type: str = "", created_by: str = "", q: str = "") -> dict[str, Any]:
    items = list(_report_templates)
    if tpl_type:
        items = [r for r in items if r["type"] == tpl_type]
    if created_by:
        items = [r for r in items if r["created_by"] == created_by]
    if q:
        items = [r for r in items if q.lower() in r["name"].lower() or q.lower() in r["id"].lower()]
    return {"items": [_report_template_out(r) for r in items]}


@app.post("/api/report-templates")
def create_report_template(body: ReportTemplateCreate) -> dict[str, Any]:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="请填写报告模板名称")
    if any(r["name"] == body.name.strip() for r in _report_templates):
        raise HTTPException(status_code=400, detail="已存在同名评估报告模板")
    rt = {
        "id": _next_id("RT"),
        "name": body.name.strip(),
        "description": body.description,
        "type": body.tpl_type,
        "version": "v1.0",
        "status": "VERIFIED",
        "created_by": accounts.creator_name(),
        "created_at": now(),
        "updated_at": now(),
        "config": {},
    }
    _apply_report_template_body(rt, body)
    with _lock:
        _report_templates.append(rt)
    return _report_template_out(rt)


@app.get("/api/report-templates/{rt_id}")
def get_report_template(rt_id: str) -> dict[str, Any]:
    rt = _find_report_template(rt_id)
    out = _report_template_out(rt)
    out["used_by"] = [{"id": t["id"], "name": t["name"], "status": t["status"]} for t in _tasks_using_report_template(rt_id)]
    return out


@app.put("/api/report-templates/{rt_id}")
def update_report_template(rt_id: str, body: ReportTemplateUpdate) -> dict[str, Any]:
    rt = _find_report_template(rt_id)
    if any(r["name"] == body.name.strip() and r["id"] != rt_id for r in _report_templates):
        raise HTTPException(status_code=400, detail="已存在同名评估报告模板")
    with _lock:
        _apply_report_template_body(rt, body)
        rt["updated_at"] = now()
    return _report_template_out(rt)


@app.post("/api/report-templates/{rt_id}/copy")
def copy_report_template(rt_id: str) -> dict[str, Any]:
    source = _find_report_template(rt_id)
    clone = json.loads(json.dumps(source))
    clone["id"] = _next_id("RT")
    clone["name"] = f"{source['name']}_副本"
    clone["version"] = "v1.0"
    clone["created_by"] = accounts.creator_name()
    clone["created_at"] = now()
    clone["updated_at"] = now()
    with _lock:
        _report_templates.append(clone)
    return _report_template_out(clone)


@app.delete("/api/report-templates/{rt_id}")
def delete_report_template(rt_id: str) -> dict[str, Any]:
    rt = _find_report_template(rt_id)
    using = _tasks_using_report_template(rt_id)
    if using:
        names = "、".join(t["name"] for t in using[:3])
        raise HTTPException(status_code=400, detail=f"评估报告模板正被任务引用（{names} 等），无法删除")
    with _lock:
        _report_templates.remove(rt)
    return {"ok": True}


@app.get("/api/tasks")
def list_tasks(
    status: str = "",
    eval_method: str = "",
    task_type: str = "",
    judge_model: str = "",
    start: str = "",
    end: str = "",
    q: str = "",
) -> dict[str, Any]:
    items = list(_tasks)
    if status:
        items = [t for t in items if t["status"] == status]
    if eval_method:
        items = [t for t in items if t["eval_method"] == eval_method]
    if task_type:
        items = [t for t in items if t["task_type"] == task_type]
    if judge_model:
        items = [t for t in items if t["judge_model"] == judge_model]
    if start:
        items = [t for t in items if t["created_at"][:10] >= start]
    if end:
        items = [t for t in items if t["created_at"][:10] <= end]
    if q:
        items = [t for t in items if q.lower() in t["name"].lower() or q.lower() in t["id"].lower()]
    return {"items": [_public_task(t) for t in items]}


@app.post("/api/tasks")
def create_task(body: TaskCreate) -> dict[str, Any]:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="请填写任务名称")
    benchmark = _find_benchmark(body.benchmark_id)
    dataset = _find_dataset(body.dataset_id)
    if benchmark["eval_method"] != dataset["eval_method"]:
        raise HTTPException(status_code=400, detail="评估基准与数据集的评估方式不一致")
    task = _new_task(
        _next_id("TK"),
        body.name.strip(),
        body.description,
        body.benchmark_id,
        body.dataset_id,
        body.judge_model,
        "CREATED",
        0,
        task_type=body.task_type,
        report_template_id=body.report_template_id,
    )
    with _lock:
        _tasks.insert(0, task)
    return _public_task(task)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = _find_task(task_id)
    result = _public_task(task)
    result["results"] = task.get("results", [])
    result["report"] = task.get("report")
    return result


@app.get("/api/tasks/{task_id}/progress")
def task_progress(task_id: str) -> dict[str, Any]:
    """轻量轮询端点：只回进度与引擎状态，不带结果明细（技术方案 §9）。"""
    task = _find_task(task_id)
    results = task.get("results", [])
    return {
        "status": task["status"],
        "done": task["progress_done"],
        "total": task["progress_total"],
        "failed": sum(1 for r in results if r.get("status") == "FAILED"),
        "engine": task.get("engine", "simulated"),
        "engine_downgraded": task.get("engine_downgraded", False),
        "actual_tokens": task.get("actual_tokens", 0),
        "actual_cost": task.get("actual_cost", 0.0),
        "error": task.get("error"),
    }


@app.put("/api/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate) -> dict[str, Any]:
    task = _find_task(task_id)
    if task["status"] not in EDITABLE_STATUSES:
        raise HTTPException(status_code=400, detail="当前状态不可编辑")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="请填写任务名称")
    benchmark = _find_benchmark(body.benchmark_id)
    dataset = _find_dataset(body.dataset_id)
    if benchmark["eval_method"] != dataset["eval_method"]:
        raise HTTPException(status_code=400, detail="评估基准与数据集的评估方式不一致")
    with _lock:
        rebuilt = _new_task(
            task_id,
            body.name.strip(),
            body.description,
            body.benchmark_id,
            body.dataset_id,
            body.judge_model,
            task["status"],
            0,
            task["review_status"],
            task_type=body.task_type,
            created_at=task["created_at"],
            report_template_id=body.report_template_id,
        )
        rebuilt["created_by"] = task["created_by"]
        rebuilt["error"] = None
        task.clear()
        task.update(rebuilt)
    return _public_task(task)


@app.post("/api/tasks/{task_id}/copy")
def copy_task(task_id: str) -> dict[str, Any]:
    source = _find_task(task_id)
    if source["status"] not in COPYABLE_STATUSES:
        raise HTTPException(status_code=400, detail="当前状态不可复制")
    clone = _new_task(
        _next_id("TK"),
        f"{source['name']}_副本",
        source["description"],
        source["benchmark_id"],
        source["dataset_id"],
        source["judge_model"],
        "CREATED",
        0,
        task_type=source["task_type"],
        report_template_id=source.get("report_template_id"),
    )
    with _lock:
        _tasks.insert(0, clone)
    return _public_task(clone)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    task = _find_task(task_id)
    if task["status"] not in DELETABLE_STATUSES:
        raise HTTPException(status_code=400, detail="当前状态不可删除")
    with _lock:
        _tasks.remove(task)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/execute")
def execute_task(task_id: str) -> dict[str, Any]:
    task = _find_task(task_id)
    if task["status"] not in ("CREATED", "STOPPED", "FAILED"):
        raise HTTPException(status_code=400, detail="当前状态不可执行")
    if config.JUDGE_ENGINE == "agent" and not llm.is_live(task["judge_model"]):
        raise HTTPException(
            status_code=400,
            detail=f"评测引擎为 agent，但裁判员模型「{task['judge_model']}」不在大模型网关可用列表内",
        )
    if config.engine_for(task["judge_model"]) == "agent":
        try:
            remaining = int(llm.fetch_quota(timeout=5).get("remaining_calls", 1))
        except (llm.LlmError, ValueError, TypeError):
            remaining = 1  # 网关额度查询失败不阻断执行，交由评测过程中的失败熔断兜底
        if remaining <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"今日模型调用额度已用完（{config.LLM_DAILY_CALL_LIMIT} 次/天），请明日再执行",
            )
    with _lock:
        task["results"] = []
        task["progress_done"] = 0
        task["status"] = "RUNNING"
        task["error"] = None
    _run_evaluation(task_id)
    return _public_task(task)


@app.post("/api/tasks/{task_id}/stop")
def stop_task(task_id: str) -> dict[str, Any]:
    task = _find_task(task_id)
    if task["status"] != "RUNNING":
        raise HTTPException(status_code=400, detail="仅执行中的任务可停止")
    with _lock:
        task["cancel"] = True
        task["status"] = "STOPPED"
    return _public_task(task)


@app.get("/api/tasks/{task_id}/results")
def task_results(task_id: str) -> dict[str, Any]:
    task = _find_task(task_id)
    return {"items": task.get("results", [])}


@app.get("/api/tasks/{task_id}/report")
def task_report(task_id: str) -> dict[str, Any]:
    task = _find_task(task_id)
    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="任务尚未完成，无报告")
    return task.get("report") or {"status": "GENERATING", "content": {}}


@app.get("/api/tasks/{task_id}/report/markdown")
def task_report_markdown(task_id: str) -> Response:
    task = _find_task(task_id)
    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="任务尚未完成，无报告")
    report = task.get("report")
    if not report:
        raise HTTPException(status_code=404, detail="报告尚未生成")
    ok = [r for r in task.get("results", []) if r.get("status") == "SUCCESS"]
    markdown = report.get("markdown") or report_mod.report_to_markdown(task, report, ok)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(task['name'] + '-评估报告.md')}"},
    )


@app.get("/api/tasks/{task_id}/report/xlsx")
def task_report_xlsx(task_id: str) -> Response:
    task = _find_task(task_id)
    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="任务尚未完成，无报告")
    ok = [r for r in task.get("results", []) if r.get("status") == "SUCCESS"]
    if not ok:
        raise HTTPException(status_code=404, detail="暂无成功的评测结果可导出")
    benchmark = _find_benchmark(task["benchmark_id"])
    data = report_mod.report_to_xlsx(task, ok, benchmark)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(task['name'] + '-原始打分表.xlsx')}"},
    )


@app.get("/api/tasks/{task_id}/export")
def export_task(task_id: str) -> Response:
    task = _find_task(task_id)
    results = [r for r in task.get("results", []) if r.get("status") == "SUCCESS"]
    if not results:
        raise HTTPException(status_code=404, detail="暂无评测结果可导出")
    is_gsb = task["eval_method"] == "GSB"
    buf = io.StringIO()
    if is_gsb:
        fieldnames = ["row_index", "query", "content", "baseline", "judgment", "total", "baseline_total", "reason", "confidence", "review_status"]
    else:
        dim_names = [d["name"] for d in results[0]["scores"]["dimensions"]]
        fieldnames = ["row_index", "query", "content"] + dim_names + ["total", "reason", "confidence", "review_status"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        row: dict[str, Any] = {
            "row_index": r["row_index"],
            "query": r["query"],
            "content": r["content"],
            "reason": r["reason"],
            "confidence": r["confidence"],
            "review_status": r["review_status"],
        }
        if is_gsb:
            row.update({"baseline": r.get("baseline", ""), "judgment": r["scores"]["judgment"], "total": r["scores"]["total"], "baseline_total": r["scores"]["baseline_total"]})
        else:
            row["total"] = r["scores"]["total"]
            for d in r["scores"]["dimensions"]:
                row[d["name"]] = d["score"]
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(task['name'] + '-评测结果.csv')}"},
    )


def _recompute_adjusted(task: dict[str, Any], adjusted: dict[str, Any]) -> dict[str, Any]:
    """人工调整维度分后，由后端按基准的聚合配置重算总分（前端不再自算，避免分制不一致时对不上）。"""
    if task["eval_method"] == "GSB" or not adjusted.get("dimensions"):
        return adjusted
    benchmark = next((b for b in _benchmarks if b["id"] == task["benchmark_id"]), None)
    if not benchmark:
        return adjusted
    cfg = scoring.normalize_config(benchmark["config"])
    dims = cfg["dimensions"]
    dim_by_key = {d["key"]: d for d in dims}
    scores_by_key: dict[str, Any] = {}
    for sd in adjusted["dimensions"]:
        d = dim_by_key.get(sd.get("key"))
        if d is not None:
            scores_by_key[d["key"]] = scoring.coerce_score(d, sd.get("score"))
    agg = scoring.aggregate(dims, scores_by_key, cfg["scoring"])
    out = dict(adjusted)
    out["total"] = agg["total"]
    out["total_ratio"] = agg["total_ratio"]
    if agg["grade_label"]:
        out["grade_label"] = agg["grade_label"]
    if agg["vetoed"]:
        out["vetoed"] = agg["vetoed"]
    else:
        out.pop("vetoed", None)
    return out


@app.put("/api/tasks/{task_id}/review")
def review_task(task_id: str, body: ReviewUpdate) -> dict[str, Any]:
    task = _find_task(task_id)
    if task["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="任务尚未完成评测，无法复核")
    found = False
    for r in task.get("results", []):
        if r["row_index"] == body.row_index:
            r["review_status"] = body.review_status
            if body.adjusted_scores is not None:
                r["adjusted_scores"] = _recompute_adjusted(task, body.adjusted_scores)
            r["review_comment"] = body.review_comment
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="未找到对应样本")
    reviewed = sum(1 for r in task.get("results", []) if r.get("review_status") != "PENDING")
    total = len(task.get("results", []))
    if total and reviewed >= total:
        task["review_status"] = "COMPLETED"
    elif reviewed > 0:
        task["review_status"] = "IN_PROGRESS"
    else:
        task["review_status"] = "NOT_STARTED"
    return _public_task(task)


@app.get("/api/models")
def list_models() -> dict[str, Any]:
    # 网关无需 API Key，live 模型即视为可用。
    items = [{**m, "available": m["live"]} for m in _MODELS]
    return {"items": items, "engine": config.JUDGE_ENGINE, "key_configured": True}


@app.get("/api/quota")
def model_quota() -> dict[str, Any]:
    """当日大模型调用额度（供顶部导航栏展示）。优先取网关 /v1/quota，不可达时回退本地计数。"""
    limit = config.LLM_DAILY_CALL_LIMIT
    try:
        q = llm.fetch_quota(timeout=8)
        calls = int(q.get("calls") or 0)
        remaining = q.get("remaining_calls")
        return {
            "calls": calls,
            "limit": limit,
            "remaining_calls": int(remaining) if remaining is not None else max(0, limit - calls),
            "cost_yuan": q.get("cost_yuan"),
            "remaining_budget_yuan": q.get("remaining_budget_yuan"),
            "source": "gateway",
        }
    except (llm.LlmError, ValueError, TypeError):
        calls = llm.local_calls_today()
        return {
            "calls": calls,
            "limit": limit,
            "remaining_calls": max(0, limit - calls),
            "cost_yuan": None,
            "remaining_budget_yuan": None,
            "source": "local",
        }


# ---- 人工评估中心 ----
# manual.py 不 import main（避免 import 环），改由这里在 main 自身初始化完成后注入所需句柄。
from . import manual as _manual  # noqa: E402

_manual.init(
    tasks=_manual_tasks,
    lock=_lock,
    next_id=_next_id,
    persist=_persist_state,
    parse_rows=_parse_upload_rows,
    models=_MODELS,
    report_templates=_report_templates,
)
app.include_router(_manual.router)


# ---- 前端静态资源托管（单容器 / 无 nginx 部署时启用）----
# nginx 方案下前端由 nginx 托管、本段不生效（dist 不在后端可见路径也无妨）；
# 当构建产物随后端一起部署（Docker 单容器）时，由 FastAPI 直接对外提供前端。
# 放在所有 API 路由与 include_router 之后注册，确保 /api 与 /health 优先匹配。
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST_DIR = config._REPO_ROOT / "site" / "frontend" / "dist"
if (_DIST_DIR / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    def _spa_index() -> FileResponse:
        return FileResponse(_DIST_DIR / "index.html")

    @app.get("/{spa_path:path}", include_in_schema=False)
    def _spa_fallback(spa_path: str) -> Response:
        # 未知的 /api、/health 路径仍返回 404，不吞成前端首页
        if spa_path.startswith(("api/", "health")):
            raise HTTPException(status_code=404, detail="Not Found")
        target = _DIST_DIR / spa_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(_DIST_DIR / "index.html")  # SPA 前端路由回退
