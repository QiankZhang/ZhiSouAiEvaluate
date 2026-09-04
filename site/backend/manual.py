"""人工评估中心：上传数据 → 逐条人工标注 → 自动汇总 → 主动触发 AI 报告。

与 AI 评估中心（main.py 的 _tasks）完全独立：独立集合、独立路由前缀 /api/manual-tasks、
独立 ID 前缀 MT。数据随 db.py 快照持久化（main._persist_state 已把 _manual_tasks 一并落盘）。

本模块不 import main（避免 import 环）；main.py 在自身初始化完成后调用 init() 注入所需句柄：
_manual_tasks 列表、应用级锁、_next_id、_persist_state、_parse_upload_rows、_MODELS、_report_templates。

设计见仓库根「人工评估中心设计.md」。
"""

import csv
import io
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from . import accounts, config, llm, report, weibo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manual-tasks", tags=["manual"])

ANNOTATE_TYPES = {"GSB", "MULTI_DIM", "CONVERSATION", "INTENT"}
ANNOTATE_TYPE_LABELS = {
    "GSB": "GSB 标注",
    "MULTI_DIM": "多维度评估标注",
    "CONVERSATION": "多轮对话标注",
    "INTENT": "意图准确率标注",
}
INTENT_JUDGMENTS = ("correct", "partial", "wrong")
INTENT_JUDGMENT_LABELS = {"correct": "识别正确", "partial": "部分正确", "wrong": "识别错误"}

# 意图准确率上传列名与别名（大小写不敏感，取第一个命中的列）
_INTENT_COL_ALIASES = {
    "query": ("query", "问题", "用户输入", "输入", "q", "question", "用户query"),
    "predicted_intent": ("predicted_intent", "predicted", "predict_intent", "intent", "识别意图", "预测意图", "系统意图", "意图"),
    "expected_intent": ("expected_intent", "expected", "gold", "gold_intent", "期望意图", "标准意图", "正确意图", "真实意图"),
    "scene": ("scene", "场景", "渠道", "channel", "来源"),
}

MAX_ROWS = 500          # GSB / 多维度：样本条数上限
MAX_SESSIONS = 200      # 多轮对话：会话数上限
LOW_SCORE_THRESHOLD = 3.0
DIM_LOW_MARK = 2

# 角色归一：把上传数据里五花八门的说法收敛到 user / assistant
_USER_ROLES = {"user", "用户", "human", "客户", "提问", "question", "q"}
_ASSISTANT_ROLES = {"assistant", "助手", "ai", "bot", "model", "模型", "机器人", "回答", "answer", "response", "a"}

# main.py 注入的运行时句柄（见 init）
_ctx: dict[str, Any] = {}


def init(
    *,
    tasks: list,
    lock: threading.Lock,
    next_id,
    persist,
    parse_rows,
    models: list,
    report_templates: list,
    parse_weibo_rows=None,
) -> None:
    _ctx.update(
        tasks=tasks,
        lock=lock,
        next_id=next_id,
        persist=persist,
        parse_rows=parse_rows,
        parse_weibo_rows=parse_weibo_rows,
        models=models,
        report_templates=report_templates,
    )


def _tasks() -> list:
    return _ctx["tasks"]


def _lock() -> threading.Lock:
    return _ctx["lock"]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


DEFAULT_REPORT_MODEL = "deepseek-v4-flash"


def _default_report_model() -> str:
    live = {m["id"] for m in _ctx["models"] if m.get("live")}
    if DEFAULT_REPORT_MODEL in live:
        return DEFAULT_REPORT_MODEL
    return next(iter(live), DEFAULT_REPORT_MODEL)


# ---------- 查找 ----------

def _find(mt_id: str) -> dict[str, Any]:
    for mt in _tasks():
        if mt["id"] == mt_id:
            return mt
    raise HTTPException(status_code=404, detail="标注任务不存在")


def _find_report_template(rt_id: Optional[str]) -> Optional[dict[str, Any]]:
    if not rt_id:
        return None
    return next((r for r in _ctx["report_templates"] if r["id"] == rt_id), None)


# ---------- 上传解析 ----------

def _normalize_role(raw: Any) -> str:
    v = str(raw or "").strip().lower()
    if v in _USER_ROLES:
        return "user"
    if v in _ASSISTANT_ROLES:
        return "assistant"
    # 兜底：未知角色按助手处理，避免整份数据卡住
    return "assistant"


def _parse_conversation(raw: bytes, filename: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析多轮对话上传：返回 (sessions, errors)。
    支持 .jsonl（逐行 turn 对象）、.json（扁平 turn 列表 或 [{session_id,title,turns:[...]}]）、
    .csv（列 session_id/turn/role/content，可选 title）。"""
    lower = filename.lower()
    errors: list[dict[str, Any]] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [{"line": 0, "message": "文件编码不支持，请使用 UTF-8 编码的文件"}]

    # session_id -> {"title": str, "turns": [(turn_no, role, content)]}
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def add_turn(sid: Any, turn_no: Any, role: Any, content: Any, title: Any = "", line: int = 0) -> None:
        sid = str(sid or "").strip()
        content = str(content or "").strip()
        if not sid:
            errors.append({"line": line, "message": "缺少 session_id"})
            return
        if not content:
            return
        if sid not in grouped:
            grouped[sid] = {"title": str(title or "").strip(), "turns": []}
            order.append(sid)
        elif title and not grouped[sid]["title"]:
            grouped[sid]["title"] = str(title).strip()
        try:
            seq = int(turn_no)
        except (TypeError, ValueError):
            seq = len(grouped[sid]["turns"]) + 1
        grouped[sid]["turns"].append((seq, _normalize_role(role), content))

    if lower.endswith(".jsonl"):
        for i, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append({"line": i, "message": f"JSON 解析失败：{exc.msg}"})
                continue
            add_turn(obj.get("session_id"), obj.get("turn"), obj.get("role"), obj.get("content"), obj.get("title"), i)
    elif lower.endswith(".json"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return [], [{"line": exc.lineno, "message": f"JSON 解析失败：{exc.msg}"}]
        if not isinstance(payload, list):
            return [], [{"line": 1, "message": "JSON 根节点必须是数组"}]
        nested = payload and isinstance(payload[0], dict) and isinstance(payload[0].get("turns"), list)
        if nested:
            for i, sess in enumerate(payload, start=1):
                if not isinstance(sess, dict):
                    errors.append({"line": i, "message": "元素必须是对象"})
                    continue
                for j, turn in enumerate(sess.get("turns") or [], start=1):
                    add_turn(sess.get("session_id") or f"session-{i}", turn.get("turn") or j,
                             turn.get("role"), turn.get("content"), sess.get("title"), i)
        else:
            for i, obj in enumerate(payload, start=1):
                if not isinstance(obj, dict):
                    errors.append({"line": i, "message": "元素必须是对象"})
                    continue
                add_turn(obj.get("session_id"), obj.get("turn"), obj.get("role"), obj.get("content"), obj.get("title"), i)
    elif lower.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], [{"line": 1, "message": "未识别到表头，请使用模板中的列名"}]
        fields = {f.strip().lower(): f for f in reader.fieldnames}
        col = lambda *names: next((fields[n] for n in names if n in fields), None)  # noqa: E731
        c_sid, c_turn, c_role, c_content, c_title = (
            col("session_id", "session", "会话id", "会话"),
            col("turn", "轮次", "序号", "index"),
            col("role", "角色", "speaker"),
            col("content", "内容", "text", "message", "回复"),
            col("title", "标题", "主题"),
        )
        if not (c_sid and c_role and c_content):
            return [], [{"line": 1, "message": "多轮对话 CSV 需包含列：session_id、role、content"}]
        for i, row in enumerate(reader, start=2):
            add_turn(row.get(c_sid), row.get(c_turn) if c_turn else None,
                     row.get(c_role), row.get(c_content), row.get(c_title) if c_title else "", i)
    else:
        return [], [{"line": 0, "message": "多轮对话仅支持 JSONL / JSON / CSV 格式"}]

    sessions: list[dict[str, Any]] = []
    for sid in order:
        turns_sorted = sorted(grouped[sid]["turns"], key=lambda t: t[0])
        turns = [{"turn": idx + 1, "role": r, "content": c} for idx, (_, r, c) in enumerate(turns_sorted)]
        if not turns:
            continue
        sessions.append({"session_id": sid, "title": grouped[sid]["title"] or f"会话 {sid}", "turns": turns})
    if not sessions and not errors:
        errors.append({"line": 0, "message": "文件中没有可用的对话数据"})
    return sessions, errors


def _parse_intent(raw: bytes, filename: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析意图准确率上传：返回 (rows, errors)。支持 .csv / .json / .jsonl。
    必填列 query、predicted_intent；可选 expected_intent（金标准）、scene（场景备注）。"""
    lower = filename.lower()
    errors: list[dict[str, Any]] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [{"line": 0, "message": "文件编码不支持，请使用 UTF-8 编码的文件"}]

    records: list[tuple[int, dict[str, Any]]] = []
    if lower.endswith(".jsonl"):
        for i, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append({"line": i, "message": f"JSON 解析失败：{exc.msg}"})
                continue
            if isinstance(obj, dict):
                records.append((i, obj))
            else:
                errors.append({"line": i, "message": "每行必须是 JSON 对象"})
    elif lower.endswith(".json"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return [], [{"line": exc.lineno, "message": f"JSON 解析失败：{exc.msg}"}]
        if not isinstance(payload, list):
            return [], [{"line": 1, "message": "JSON 根节点必须是数组"}]
        for i, obj in enumerate(payload, start=1):
            if isinstance(obj, dict):
                records.append((i, obj))
            else:
                errors.append({"line": i, "message": "元素必须是对象"})
    elif lower.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], [{"line": 1, "message": "未识别到表头，请使用模板中的列名"}]
        fields = {f.strip().lower(): f for f in reader.fieldnames}
        colmap: dict[str, str] = {}
        for canon, aliases in _INTENT_COL_ALIASES.items():
            src = next((fields[a] for a in aliases if a in fields), None)
            if src:
                colmap[canon] = src
        if "query" not in colmap or "predicted_intent" not in colmap:
            return [], [{"line": 1, "message": "意图准确率 CSV 需包含列：query、predicted_intent"}]
        for i, row in enumerate(reader, start=2):
            records.append((i, {c: row.get(src, "") for c, src in colmap.items()}))
    else:
        return [], [{"line": 0, "message": "意图准确率标注仅支持 CSV / JSON / JSONL 格式"}]

    def _pick(obj: dict[str, Any], canon: str) -> str:
        for k in (canon, *_INTENT_COL_ALIASES[canon]):
            if k in obj and str(obj[k]).strip():
                return str(obj[k]).strip()
        return ""

    rows: list[dict[str, Any]] = []
    for line, obj in records:
        q = _pick(obj, "query")
        pi = _pick(obj, "predicted_intent")
        if not q or not pi:
            errors.append({"line": line, "message": "缺少必填字段：query / predicted_intent"})
            continue
        rows.append(
            {
                "query": q,
                "predicted_intent": pi,
                "expected_intent": _pick(obj, "expected_intent"),
                "scene": _pick(obj, "scene"),
            }
        )
    if not rows and not errors:
        errors.append({"line": 0, "message": "文件中没有可用数据行"})
    return rows, errors


def _build_units(annotate_type: str, raw: bytes, filename: str) -> list[dict[str, Any]]:
    if annotate_type == "INTENT":
        rows, errors = _parse_intent(raw, filename)
        if errors:
            raise HTTPException(status_code=422, detail={"message": "文件校验未通过，请修正后重新上传", "errors": errors[:50]})
        if len(rows) > MAX_ROWS:
            raise HTTPException(status_code=422, detail={"message": f"样本条数超过上限（{MAX_ROWS} 条）", "errors": []})
        return [
            {
                "key": str(i),
                "index": i,
                "query": r["query"],
                "predicted_intent": r["predicted_intent"],
                "expected_intent": r["expected_intent"],
                "scene": r["scene"],
                "judgment": None,
                "corrected_intent": "",
                "skipped": False,
                "note": "",
                "annotated_by": None,
                "annotated_at": None,
            }
            for i, r in enumerate(rows, start=1)
        ]

    if annotate_type == "CONVERSATION":
        sessions, errors = _parse_conversation(raw, filename)
        if errors:
            raise HTTPException(status_code=422, detail={"message": "文件校验未通过，请修正后重新上传", "errors": errors[:50]})
        if len(sessions) > MAX_SESSIONS:
            raise HTTPException(status_code=422, detail={"message": f"会话数超过上限（{MAX_SESSIONS} 个）", "errors": []})
        return [
            {
                "key": s["session_id"],
                "session_id": s["session_id"],
                "title": s["title"],
                "turns": s["turns"],
                "dim_scores": {},
                "overridden_total": None,
                "total": None,
                "skipped": False,
                "note": "",
                "annotated_by": None,
                "annotated_at": None,
            }
            for s in sessions
        ]

    eval_method = "GSB" if annotate_type == "GSB" else "MULTI_DIM"
    rows, errors = _ctx["parse_rows"](raw, filename, eval_method)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "文件校验未通过，请修正后重新上传", "errors": errors[:50]})
    if not rows:
        raise HTTPException(status_code=422, detail={"message": "文件中没有可用数据行", "errors": []})
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=422, detail={"message": f"样本条数超过上限（{MAX_ROWS} 条）", "errors": []})

    units: list[dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        unit = {
            "key": str(i),
            "index": i,
            "query": r["query"],
            "content": r["content"],
            "skipped": False,
            "note": "",
            "annotated_by": None,
            "annotated_at": None,
        }
        if annotate_type == "GSB":
            unit["baseline"] = r.get("baseline", "")
            unit["judgment"] = None
        else:
            unit["dim_scores"] = {}
            unit["overridden_total"] = None
            unit["total"] = None
        units.append(unit)
    return units


# ---------- 打分 / 进度 / 汇总 ----------

def _recompute_total(unit: dict[str, Any], dims: list[dict[str, Any]]) -> None:
    if unit.get("overridden_total") is not None:
        unit["total"] = round(float(unit["overridden_total"]), 2)
        return
    scores = unit.get("dim_scores") or {}
    if dims and all(d["key"] in scores for d in dims):
        unit["total"] = round(sum(scores[d["key"]] * d["weight"] for d in dims) / 100, 2)
    else:
        unit["total"] = None


def _unit_done(unit: dict[str, Any], mt: dict[str, Any]) -> bool:
    if unit.get("skipped"):
        return True
    if mt["annotate_type"] == "GSB":
        return unit.get("judgment") in ("G", "S", "B")
    if mt["annotate_type"] == "INTENT":
        return unit.get("judgment") in INTENT_JUDGMENTS
    return unit.get("total") is not None


def _compute_summary(mt: dict[str, Any]) -> dict[str, Any]:
    units = mt["units"]
    total = len(units)
    skipped = sum(1 for u in units if u.get("skipped"))

    if mt["annotate_type"] == "GSB":
        judged = [u for u in units if not u.get("skipped") and u.get("judgment") in ("G", "S", "B")]
        good = sum(1 for u in judged if u["judgment"] == "G")
        same = sum(1 for u in judged if u["judgment"] == "S")
        bad = sum(1 for u in judged if u["judgment"] == "B")
        denom = good + same + bad
        return {
            "eval_method": "GSB",
            "total": total,
            "scored": len(judged),
            "skipped": skipped,
            "good": good,
            "same": same,
            "bad": bad,
            "win_rate": round(good / denom * 100, 1) if denom else 0.0,
            "net_win_rate": round((good - bad) / denom * 100, 1) if denom else 0.0,
        }

    if mt["annotate_type"] == "INTENT":
        graded = [u for u in units if not u.get("skipped") and u.get("judgment") in INTENT_JUDGMENTS]
        correct = sum(1 for u in graded if u["judgment"] == "correct")
        partial = sum(1 for u in graded if u["judgment"] == "partial")
        wrong = sum(1 for u in graded if u["judgment"] == "wrong")
        n = correct + partial + wrong

        agg: dict[str, dict[str, Any]] = {}
        for u in graded:
            key = u.get("predicted_intent") or "（空）"
            a = agg.setdefault(key, {"intent": key, "total": 0, "correct": 0, "wrong": 0})
            a["total"] += 1
            if u["judgment"] == "correct":
                a["correct"] += 1
            elif u["judgment"] == "wrong":
                a["wrong"] += 1
        intents = []
        for a in agg.values():
            a["accuracy"] = round(a["correct"] / a["total"] * 100, 1) if a["total"] else 0.0
            intents.append(a)
        intents.sort(key=lambda x: (-x["total"], x["accuracy"]))

        conf: dict[tuple[str, str], int] = {}
        for u in graded:
            if u["judgment"] in ("wrong", "partial"):
                pair = (
                    u.get("predicted_intent") or "—",
                    u.get("corrected_intent") or u.get("expected_intent") or "—",
                )
                conf[pair] = conf.get(pair, 0) + 1
        confusions = [
            {"predicted": p, "corrected": c, "count": k}
            for (p, c), k in sorted(conf.items(), key=lambda x: -x[1])[:8]
        ]
        weakest = min(intents, key=lambda x: x["accuracy"]) if intents else None
        strongest = max(intents, key=lambda x: x["accuracy"]) if intents else None
        return {
            "eval_method": "INTENT",
            "total": total,
            "scored": n,
            "skipped": skipped,
            "correct": correct,
            "partial": partial,
            "wrong": wrong,
            "accuracy": round(correct / n * 100, 1) if n else 0.0,
            "lenient_accuracy": round((correct + 0.5 * partial) / n * 100, 1) if n else 0.0,
            "intents": intents,
            "confusions": confusions,
            "weakest_intent": weakest["intent"] if weakest else None,
            "strongest_intent": strongest["intent"] if strongest else None,
        }

    dims = mt.get("dimensions") or []
    scored = [u for u in units if not u.get("skipped") and u.get("total") is not None]
    dim_stats = []
    for d in dims:
        vals = [u["dim_scores"][d["key"]] for u in scored if d["key"] in (u.get("dim_scores") or {})]
        lows = sum(1 for v in vals if v <= DIM_LOW_MARK)
        avg = round(sum(vals) / len(vals), 2) if vals else 0.0
        dim_stats.append(
            {
                "key": d["key"],
                "name": d["name"],
                "weight": d["weight"],
                "avg": avg,
                "low_count": lows,
                "low_ratio": round(lows / len(scored) * 100, 1) if scored else 0.0,
            }
        )
    totals = [u["total"] for u in scored]
    weakest = min(dim_stats, key=lambda x: x["avg"]) if dim_stats else None
    strongest = max(dim_stats, key=lambda x: x["avg"]) if dim_stats else None
    return {
        "eval_method": "MULTI_DIM",
        "total": total,
        "scored": len(scored),
        "skipped": skipped,
        "avg_total": round(sum(totals) / len(totals), 2) if totals else 0.0,
        "low_count": sum(1 for t in totals if t < LOW_SCORE_THRESHOLD),
        "low_ratio": round(sum(1 for t in totals if t < LOW_SCORE_THRESHOLD) / len(scored) * 100, 1) if scored else 0.0,
        "dimensions": dim_stats,
        "distribution": {str(s): sum(1 for t in totals if round(t) == s) for s in range(1, 6)},
        "weakest_dim": weakest["name"] if weakest else None,
        "strongest_dim": strongest["name"] if strongest else None,
    }


def _refresh_progress(mt: dict[str, Any]) -> None:
    if mt.get("convert_status") == "CONVERTING":
        mt["status"] = "CONVERTING"
        return
    done = sum(1 for u in mt["units"] if _unit_done(u, mt))
    mt["progress_done"] = done
    mt["status"] = "COMPLETED" if (mt["progress_total"] > 0 and done >= mt["progress_total"]) else "ANNOTATING"
    mt["summary"] = _compute_summary(mt)


# ---------- 博文数据：mid → 物料 ----------

def _build_weibo_units(raw: bytes, filename: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """解析 mid + 智搜结果 → 占位多维度标注单元 + 待转换 mid 行。物料由后台线程回填 query。"""
    parse = _ctx.get("parse_weibo_rows")
    if not parse:
        raise HTTPException(status_code=500, detail="博文解析未就绪")
    rows, errors = parse(raw, filename)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "文件校验未通过，请修正后重新上传", "errors": errors[:50]})
    valid, invalid = weibo.normalize_mids([r["mid"] for r in rows])
    if invalid:
        raise HTTPException(status_code=422, detail={
            "message": f"存在 {len(invalid)} 个非法 mid（应为纯数字）",
            "errors": [{"line": 0, "message": m} for m in invalid[:50]],
        })
    if not valid:
        raise HTTPException(status_code=422, detail={"message": "文件中没有可用的 mid", "errors": []})
    if len(valid) > MAX_ROWS:
        raise HTTPException(status_code=422, detail={"message": f"mid 数超过上限（{MAX_ROWS} 条）", "errors": []})

    content_by_mid: dict[str, str] = {}
    for r in rows:
        content_by_mid.setdefault(r["mid"], r.get("content", ""))
    mids_rows = [{"mid": m, "content": content_by_mid.get(m, "")} for m in valid]

    units = [
        {
            "key": str(i),
            "index": i,
            "mid": m["mid"],
            "query": "",
            "content": m["content"],
            "material_status": "PENDING",
            "skipped": False,
            "note": "",
            "annotated_by": None,
            "annotated_at": None,
            "dim_scores": {},
            "overridden_total": None,
            "total": None,
        }
        for i, m in enumerate(mids_rows, start=1)
    ]
    return units, mids_rows


def _run_manual_mid_conversion(mt_id: str, mids_rows: list[dict[str, str]]) -> None:
    def progress_cb(done: int, phase: str) -> None:
        with _lock():
            mt = next((m for m in _tasks() if m["id"] == mt_id), None)
            if mt:
                mt["convert_done"] = done
                mt["convert_phase"] = phase

    def run() -> None:
        try:
            samples, failed = weibo.convert_rows(mids_rows, progress_cb=progress_cb, log=logger)
        except Exception as exc:  # noqa: BLE001
            logger.exception("人工任务 %s mid 转换失败", mt_id)
            with _lock():
                mt = next((m for m in _tasks() if m["id"] == mt_id), None)
                if mt:
                    mt["convert_status"] = "FAILED"
                    mt["status"] = "CONVERTING"
                    mt["convert_error"] = str(exc)
            return
        by_mid = {s["mid"]: s for s in samples}
        with _lock():
            mt = next((m for m in _tasks() if m["id"] == mt_id), None)
            if not mt:
                return
            for u in mt["units"]:
                got = by_mid.get(u.get("mid"))
                if got:
                    u["query"] = got["query"]
                    u["material_status"] = got["material_status"]
            mt["convert_failed"] = failed
            mt["convert_done"] = mt.get("convert_total", len(mids_rows))
            mt["convert_status"] = "PARTIAL" if failed else "READY"
            mt["convert_error"] = ""
            _refresh_progress(mt)

    threading.Thread(target=run, daemon=True).start()


# ---------- 视图 ----------

def _public(mt: dict[str, Any], *, with_units: bool = False) -> dict[str, Any]:
    out = {k: v for k, v in mt.items() if k not in ("units",)}
    out["annotate_type_label"] = ANNOTATE_TYPE_LABELS.get(mt["annotate_type"], mt["annotate_type"])
    if with_units:
        out["units"] = mt["units"]
    return out


# ---------- API ----------

class ManualTaskPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    report_template_id: Optional[str] = None
    report_model: Optional[str] = None


class AnnotateBody(BaseModel):
    unit_key: str
    judgment: Optional[str] = None            # GSB: G / S / B；INTENT: correct / partial / wrong
    dim_scores: Optional[dict[str, int]] = None
    overridden_total: Optional[float] = None  # 传 -1 表示清除覆盖
    corrected_intent: Optional[str] = None    # INTENT: 判错 / 部分正确时填写的正确意图
    skipped: Optional[bool] = None
    note: Optional[str] = None


@router.get("")
def list_manual_tasks(annotate_type: str = "", status: str = "", created_by: str = "", q: str = "") -> dict[str, Any]:
    items = list(_tasks())
    if annotate_type:
        items = [m for m in items if m["annotate_type"] == annotate_type]
    if status:
        items = [m for m in items if m["status"] == status]
    if created_by:
        items = [m for m in items if m["created_by"] == created_by]
    if q:
        ql = q.lower()
        items = [m for m in items if ql in m["name"].lower() or ql in m["id"].lower()]
    items = sorted(items, key=lambda m: m["created_at"], reverse=True)
    return {"items": [_public(m) for m in items]}


@router.get("/template")
def manual_template(annotate_type: str = "MULTI_DIM") -> Response:
    if annotate_type == "CONVERSATION":
        content = "session_id,turn,role,content,title\ns-1,1,user,示例：帮我查下明天的天气,天气查询\ns-1,2,assistant,示例：明天多云转晴，气温 18-26℃。,天气查询\n"
        name = "多轮对话模板.csv"
    elif annotate_type == "GSB":
        content = "query,content,baseline\n示例：某地天气预报,示例：待评策略的输出,示例：基线策略的输出\n"
        name = "GSB标注模板.csv"
    elif annotate_type == "INTENT":
        content = (
            "query,predicted_intent,expected_intent,scene\n"
            "示例：帮我查下明天上海的天气,天气查询,天气查询,APP首页\n"
            "示例：这个订单怎么还没发货,物流查询,售后咨询,客服会话\n"
        )
        name = "意图准确率标注模板.csv"
    else:
        content = "query,content\n示例：某产品最新报价,示例：待评策略的输出\n"
        name = "多维度标注模板.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.post("/upload")
async def upload_manual_task(
    name: str = Form(...),
    description: str = Form(""),
    annotate_type: str = Form(...),
    dimensions: str = Form("[]"),
    gsb_swap_sides: str = Form("false"),
    intent_labels: str = Form(""),
    report_template_id: str = Form(""),
    report_model: str = Form(""),
    is_weibo: str = Form("false"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写任务名称")
    if annotate_type not in ANNOTATE_TYPES:
        raise HTTPException(status_code=400, detail="不支持的标注类型")
    if any(m["name"] == name for m in _tasks()):
        raise HTTPException(status_code=400, detail="同名标注任务已存在，请更换名称")
    weibo_mode = str(is_weibo).lower() == "true"
    if weibo_mode and annotate_type != "MULTI_DIM":
        raise HTTPException(status_code=400, detail="博文数据目前仅支持多维度评估标注")

    dims: list[dict[str, Any]] = []
    if annotate_type in ("MULTI_DIM", "CONVERSATION"):
        try:
            parsed = json.loads(dimensions or "[]")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="评分维度格式错误")
        for i, d in enumerate(parsed or []):
            dname = str(d.get("name", "")).strip()
            if not dname:
                raise HTTPException(status_code=400, detail=f"第 {i + 1} 个维度未填写名称")
            dims.append({"key": d.get("key") or f"dim_{i + 1}", "name": dname, "weight": int(d.get("weight") or 0)})
        if not dims:
            raise HTTPException(status_code=400, detail="请至少配置一个评分维度")
        if sum(d["weight"] for d in dims) != 100:
            raise HTTPException(status_code=400, detail="维度权重合计需为 100%")

    labels: list[str] = []
    if annotate_type == "INTENT" and intent_labels.strip():
        try:
            parsed_labels = json.loads(intent_labels)
            raw_labels = parsed_labels if isinstance(parsed_labels, list) else []
        except json.JSONDecodeError:
            raw_labels = intent_labels.replace("，", ",").replace("\n", ",").split(",")
        seen: set[str] = set()
        for x in raw_labels:
            v = str(x).strip()[:100]
            if v and v not in seen:
                seen.add(v)
                labels.append(v)
            if len(labels) >= 200:
                break

    rt = _find_report_template(report_template_id or None)
    model = report_model.strip() or _default_report_model()

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 50MB 限制")

    weibo_rows: list[dict[str, str]] = []
    if weibo_mode:
        units, weibo_rows = _build_weibo_units(raw, file.filename or "")
    else:
        units = _build_units(annotate_type, raw, file.filename or "")

    mt = {
        "id": _ctx["next_id"]("MT"),
        "name": name,
        "description": description,
        "annotate_type": annotate_type,
        "annotate_type_label": ANNOTATE_TYPE_LABELS[annotate_type],
        "gsb_swap_sides": str(gsb_swap_sides).lower() == "true",
        "dimensions": dims,
        "intent_labels": labels,
        "report_template_id": rt["id"] if rt else None,
        "report_template_name": rt["name"] if rt else None,
        "report_model": model,
        "status": "ANNOTATING",
        "progress_done": 0,
        "progress_total": len(units),
        "source_filename": file.filename or "",
        "created_by": accounts.creator_name(),
        "created_at": _now(),
        "units": units,
        "summary": None,
        "report": None,
    }
    if weibo_mode:
        mt.update(
            is_weibo=True,
            convert_status="CONVERTING",
            convert_total=len(weibo_rows),
            convert_done=0,
            convert_phase="抓取物料",
            convert_failed=[],
            convert_error="",
        )
        mt["status"] = "CONVERTING"
        with _lock():
            _tasks().insert(0, mt)
        _run_manual_mid_conversion(mt["id"], weibo_rows)
        return _public(mt, with_units=True)

    _refresh_progress(mt)
    with _lock():
        _tasks().insert(0, mt)
    return _public(mt, with_units=True)


@router.get("/{mt_id}")
def get_manual_task(mt_id: str) -> dict[str, Any]:
    return _public(_find(mt_id), with_units=True)


@router.get("/{mt_id}/convert-progress")
def manual_convert_progress(mt_id: str) -> dict[str, Any]:
    mt = _find(mt_id)
    if not mt.get("is_weibo"):
        raise HTTPException(status_code=400, detail="非博文标注任务")
    return {
        "status": mt.get("status"),
        "convert_status": mt.get("convert_status"),
        "done": mt.get("convert_done", 0),
        "total": mt.get("convert_total", 0),
        "phase": mt.get("convert_phase", ""),
        "failed_count": len(mt.get("convert_failed") or []),
        "error": mt.get("convert_error", ""),
    }


@router.post("/{mt_id}/retry-conversion")
def manual_retry_conversion(mt_id: str) -> dict[str, Any]:
    mt = _find(mt_id)
    if not mt.get("is_weibo"):
        raise HTTPException(status_code=400, detail="非博文标注任务")
    if mt.get("convert_status") not in ("PARTIAL", "FAILED"):
        raise HTTPException(status_code=400, detail="仅部分失败 / 转换失败的任务可重试")
    if mt.get("convert_status") == "FAILED":
        retry = [{"mid": u["mid"], "content": u.get("content", "")} for u in mt["units"]]
    else:
        retry = [{"mid": u["mid"], "content": u.get("content", "")} for u in mt["units"] if u.get("material_status") != "OK"]
    if not retry:
        raise HTTPException(status_code=400, detail="没有需要重试的 mid")
    with _lock():
        mt["convert_status"] = "CONVERTING"
        mt["status"] = "CONVERTING"
        mt["convert_phase"] = "抓取物料"
        mt["convert_error"] = ""
    _run_manual_mid_conversion(mt_id, retry)
    return _public(mt, with_units=True)


@router.put("/{mt_id}")
def update_manual_task(mt_id: str, body: ManualTaskPatch) -> dict[str, Any]:
    mt = _find(mt_id)
    with _lock():
        if body.name is not None:
            new_name = body.name.strip()
            if not new_name:
                raise HTTPException(status_code=400, detail="请填写任务名称")
            if any(m["name"] == new_name and m["id"] != mt_id for m in _tasks()):
                raise HTTPException(status_code=400, detail="同名标注任务已存在")
            mt["name"] = new_name
        if body.description is not None:
            mt["description"] = body.description
        if body.report_template_id is not None:
            rt = _find_report_template(body.report_template_id or None)
            mt["report_template_id"] = rt["id"] if rt else None
            mt["report_template_name"] = rt["name"] if rt else None
        if body.report_model is not None and body.report_model.strip():
            mt["report_model"] = body.report_model.strip()
    return _public(mt, with_units=True)


@router.delete("/{mt_id}")
def delete_manual_task(mt_id: str) -> dict[str, Any]:
    mt = _find(mt_id)
    with _lock():
        _tasks().remove(mt)
    return {"ok": True}


@router.put("/{mt_id}/annotate")
def annotate(mt_id: str, body: AnnotateBody) -> dict[str, Any]:
    mt = _find(mt_id)
    unit = next((u for u in mt["units"] if u["key"] == body.unit_key), None)
    if unit is None:
        raise HTTPException(status_code=404, detail="标注单元不存在")

    with _lock():
        if body.skipped is not None:
            unit["skipped"] = bool(body.skipped)
        if body.note is not None:
            unit["note"] = body.note.strip()[:1000]

        if mt["annotate_type"] == "GSB":
            if body.judgment is not None:
                if body.judgment not in ("G", "S", "B", ""):
                    raise HTTPException(status_code=400, detail="judgment 只能是 G / S / B")
                unit["judgment"] = body.judgment or None
                if unit["judgment"]:
                    unit["skipped"] = False
        elif mt["annotate_type"] == "INTENT":
            if body.judgment is not None:
                if body.judgment not in (*INTENT_JUDGMENTS, ""):
                    raise HTTPException(status_code=400, detail="judgment 只能是 correct / partial / wrong")
                unit["judgment"] = body.judgment or None
                if unit["judgment"]:
                    unit["skipped"] = False
                if unit["judgment"] == "correct":
                    unit["corrected_intent"] = ""
            if body.corrected_intent is not None:
                unit["corrected_intent"] = body.corrected_intent.strip()[:100]
        else:
            dims = mt.get("dimensions") or []
            valid_keys = {d["key"] for d in dims}
            if body.dim_scores is not None:
                for k, v in body.dim_scores.items():
                    if k not in valid_keys:
                        continue
                    unit.setdefault("dim_scores", {})[k] = max(1, min(5, int(v)))
                if body.dim_scores:
                    unit["skipped"] = False
            if body.overridden_total is not None:
                unit["overridden_total"] = None if body.overridden_total < 0 else round(float(body.overridden_total), 2)
            _recompute_total(unit, dims)

        if _unit_done(unit, mt) and not unit.get("skipped"):
            unit["annotated_by"] = accounts.creator_name()
            unit["annotated_at"] = _now()

        _refresh_progress(mt)

    return _public(mt, with_units=True)


# ---------- AI 报告 ----------

def _judgment_reason(j: Optional[str]) -> str:
    return {"G": "人工判定：实验优于基线", "S": "人工判定：实验与基线持平", "B": "人工判定：实验劣于基线"}.get(j or "", "")


def _transcript(unit: dict[str, Any], limit: int = 1500) -> str:
    lines = [f"{t['role']}：{t['content']}" for t in unit.get("turns", [])]
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit] + "…"


_INTENT_JUDGE_SCORE = {"correct": "Correct", "partial": "Partial", "wrong": "Wrong"}


def _units_to_results(mt: dict[str, Any]) -> list[dict[str, Any]]:
    """把人工标注单元整形成 report.build_report / report_to_markdown 期望的 results 结构。"""
    at = mt["annotate_type"]
    is_gsb = at == "GSB"
    dims = mt.get("dimensions") or []
    results: list[dict[str, Any]] = []
    for i, u in enumerate((x for x in mt["units"] if not x.get("skipped")), start=1):
        if at == "INTENT":
            j = u.get("judgment")
            if j not in INTENT_JUDGMENTS:
                continue
            corrected = u.get("corrected_intent") or u.get("expected_intent") or ""
            auto_reason = "" if j == "correct" else (
                f"识别为「{u.get('predicted_intent', '')}」，应为「{corrected or '未知'}」"
            )
            body = f"系统识别意图：{u.get('predicted_intent', '')}"
            if u.get("expected_intent"):
                body += f"｜期望意图：{u['expected_intent']}"
            results.append(
                {
                    "row_index": i,
                    "query": u.get("query", ""),
                    "content": body,
                    "baseline": "",
                    "status": "SUCCESS",
                    "reason": u.get("note") or auto_reason,
                    "confidence": None,
                    "review_status": "APPROVED",
                    "scores": {
                        "judgment": _INTENT_JUDGE_SCORE[j],
                        "predicted_intent": u.get("predicted_intent", ""),
                        "corrected_intent": corrected,
                    },
                }
            )
        elif is_gsb:
            if u.get("judgment") not in ("G", "S", "B"):
                continue
            results.append(
                {
                    "row_index": i,
                    "query": u.get("query", ""),
                    "content": u.get("content", ""),
                    "baseline": u.get("baseline", ""),
                    "status": "SUCCESS",
                    "reason": u.get("note") or _judgment_reason(u.get("judgment")),
                    "confidence": None,
                    "review_status": "APPROVED",
                    "scores": {"judgment": {"G": "Good", "S": "Same", "B": "Bad"}[u["judgment"]]},
                }
            )
        else:
            if u.get("total") is None:
                continue
            body = _transcript(u) if mt["annotate_type"] == "CONVERSATION" else u.get("content", "")
            results.append(
                {
                    "row_index": i,
                    "query": u.get("query") or u.get("title") or u.get("key"),
                    "content": body,
                    "baseline": "",
                    "status": "SUCCESS",
                    "reason": u.get("note") or "",
                    "confidence": None,
                    "review_status": "APPROVED",
                    "scores": {
                        "dimensions": [
                            {"key": d["key"], "name": d["name"], "score": u["dim_scores"].get(d["key"])}
                            for d in dims
                            if d["key"] in (u.get("dim_scores") or {})
                        ],
                        "total": u["total"],
                    },
                }
            )
    return results


def _pseudo_task(mt: dict[str, Any]) -> dict[str, Any]:
    label = ANNOTATE_TYPE_LABELS.get(mt["annotate_type"], mt["annotate_type"])
    return {
        "id": mt["id"],
        "name": mt["name"],
        "task_type": "人工标注",
        "judge_model": mt["report_model"],
        "benchmark_name": f"人工标注（{label}）",
        "dataset_name": mt.get("source_filename") or "人工上传",
        "progress_total": mt["progress_total"],
        "review_status": "COMPLETED",
        "created_at": mt["created_at"],
        "engine": config.engine_for(mt["report_model"]),
        "engine_downgraded": False,
    }


def _pseudo_benchmark(mt: dict[str, Any]) -> dict[str, Any]:
    at = mt["annotate_type"]
    if at == "INTENT":
        return {
            "eval_method": "INTENT",
            "type": "PROMPT",
            "config": {"dimensions": [], "intent_labels": mt.get("intent_labels") or []},
        }
    dims = mt.get("dimensions") or [{"key": "overall", "name": "总体", "weight": 100}]
    return {"eval_method": "GSB" if at == "GSB" else "MULTI_DIM", "type": "PROMPT", "config": {"dimensions": dims}}


def _generate_report(mt_id: str) -> None:
    def run() -> None:
        try:
            mt = _find(mt_id)
        except HTTPException:
            return
        pseudo_task = _pseudo_task(mt)
        pseudo_bm = _pseudo_benchmark(mt)
        results = _units_to_results(mt)
        template = _find_report_template(mt.get("report_template_id"))
        try:
            content = report.build_report(pseudo_task, results, pseudo_bm)
            markdown = report.generate_report_markdown(pseudo_task, content, results, template)
        except Exception as exc:  # noqa: BLE001 - 报告失败不影响任务本身
            logger.exception("人工评估任务 %s 报告生成失败", mt_id)
            with _lock():
                mt["report"] = {"status": "FAILED", "error": str(exc), "generated_at": _now()}
            return
        with _lock():
            mt["report"] = {"status": "READY", "markdown": markdown, "generated_at": _now()}

    threading.Thread(target=run, daemon=True).start()


@router.post("/{mt_id}/report")
def trigger_report(mt_id: str) -> dict[str, Any]:
    mt = _find(mt_id)
    if mt["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="请先完成全部标注再生成报告")
    if (mt.get("report") or {}).get("status") == "GENERATING":
        raise HTTPException(status_code=409, detail="报告正在生成中")
    if not _units_to_results(mt):
        raise HTTPException(status_code=400, detail="没有可用于生成报告的标注结果（全部被跳过？）")

    if config.engine_for(mt["report_model"]) == "agent":
        try:
            remaining = int(llm.fetch_quota(timeout=5).get("remaining_calls", 1))
        except (llm.LlmError, ValueError, TypeError):
            remaining = 1
        if remaining <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"今日模型调用额度已用完（{config.LLM_DAILY_CALL_LIMIT} 次/天），请明日再试",
            )

    with _lock():
        mt["report"] = {"status": "GENERATING", "generated_at": _now()}
    _generate_report(mt_id)
    return {"status": "GENERATING"}


@router.get("/{mt_id}/report")
def get_report(mt_id: str) -> dict[str, Any]:
    mt = _find(mt_id)
    return mt.get("report") or {"status": "NONE"}


@router.get("/{mt_id}/report/markdown")
def download_report_markdown(mt_id: str) -> Response:
    mt = _find(mt_id)
    rp = mt.get("report") or {}
    if rp.get("status") != "READY" or not rp.get("markdown"):
        raise HTTPException(status_code=404, detail="报告尚未生成")
    return Response(
        content=rp["markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(mt['name'] + '-人工评估报告.md')}"},
    )


@router.get("/{mt_id}/export")
def export_manual_task(mt_id: str) -> Response:
    mt = _find(mt_id)
    buf = io.StringIO()
    at = mt["annotate_type"]
    if at == "GSB":
        fields = ["index", "query", "judgment", "note", "annotated_by", "annotated_at"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for u in mt["units"]:
            writer.writerow(
                {
                    "index": u["index"],
                    "query": u["query"],
                    "judgment": "跳过" if u.get("skipped") else (u.get("judgment") or ""),
                    "note": u.get("note", ""),
                    "annotated_by": u.get("annotated_by") or "",
                    "annotated_at": u.get("annotated_at") or "",
                }
            )
    elif at == "INTENT":
        fields = [
            "index", "query", "predicted_intent", "expected_intent",
            "judgment", "corrected_intent", "note", "annotated_by", "annotated_at",
        ]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for u in mt["units"]:
            writer.writerow(
                {
                    "index": u["index"],
                    "query": u["query"],
                    "predicted_intent": u.get("predicted_intent", ""),
                    "expected_intent": u.get("expected_intent", ""),
                    "judgment": "跳过" if u.get("skipped") else INTENT_JUDGMENT_LABELS.get(u.get("judgment"), ""),
                    "corrected_intent": u.get("corrected_intent", ""),
                    "note": u.get("note", ""),
                    "annotated_by": u.get("annotated_by") or "",
                    "annotated_at": u.get("annotated_at") or "",
                }
            )
    else:
        dims = mt.get("dimensions") or []
        dim_names = [d["name"] for d in dims]
        head_key = "session_id" if at == "CONVERSATION" else "index"
        fields = [head_key, "query", *dim_names, "total", "note", "annotated_by", "annotated_at"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for u in mt["units"]:
            row = {
                head_key: u.get("session_id") if at == "CONVERSATION" else u["index"],
                "query": u.get("query") or u.get("title") or "",
                "total": "跳过" if u.get("skipped") else (u.get("total") if u.get("total") is not None else ""),
                "note": u.get("note", ""),
                "annotated_by": u.get("annotated_by") or "",
                "annotated_at": u.get("annotated_at") or "",
            }
            for d in dims:
                row[d["name"]] = (u.get("dim_scores") or {}).get(d["key"], "")
            writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(mt['name'] + '-标注明细.csv')}"},
    )
