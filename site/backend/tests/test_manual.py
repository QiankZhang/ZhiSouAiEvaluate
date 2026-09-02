"""人工评估中心：核心逻辑单测（不起 HTTP，直接调 manual 模块的路由函数）。

manual.py 的运行时句柄由 main.py 注入，这里用 init() 注入测试替身，避免真实 DB / 网络。
"""

import asyncio
import csv
import io
import json
import threading
import time

import pytest
from fastapi import HTTPException

from backend import accounts, manual


def _fake_parse_rows(raw: bytes, filename: str, eval_method: str):
    """把 CSV 文本解析成 [{query, content, baseline}]，模拟 main._parse_upload_rows。"""
    rows = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        rows.append({"query": r.get("query", ""), "content": r.get("content", ""), "baseline": r.get("baseline", "")})
    return rows, []


@pytest.fixture(autouse=True)
def wired():
    tasks: list = []
    seq = {"MT": 1000}

    def next_id(prefix):
        seq[prefix] += 1
        return f"{prefix}-{seq[prefix]}"

    manual.init(
        tasks=tasks,
        lock=threading.Lock(),
        next_id=next_id,
        persist=lambda: None,
        parse_rows=_fake_parse_rows,
        models=[{"id": "deepseek-v4-flash", "live": True}, {"id": "gpt-4.1", "live": False}],
        report_templates=[],
    )
    accounts._current.set({"account": "t", "name": "测试员", "org_id": "ORG-1"})
    yield tasks
    accounts._current.set(None)


class _File:
    def __init__(self, text, filename="d.csv"):
        self._text = text
        self.filename = filename

    async def read(self):
        return self._text.encode("utf-8")


def _upload(annotate_type, text, dimensions=None, name="任务A", filename="d.csv", model="gpt-4.1"):
    return asyncio.run(
        manual.upload_manual_task(
            name=name,
            description="",
            annotate_type=annotate_type,
            dimensions=json.dumps(dimensions or []),
            gsb_swap_sides="false",
            report_template_id="",
            report_model=model,  # 默认非 live → 报告走确定性模板，不联网
            file=_File(text, filename),
        )
    )


def test_gsb_upload_and_summary():
    mt = _upload("GSB", "query,content,baseline\nq1,c1,b1\nq2,c2,b2\nq3,c3,b3\n")
    assert mt["annotate_type"] == "GSB"
    assert mt["progress_total"] == 3
    assert mt["progress_done"] == 0
    mid = mt["id"]

    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="G"))
    manual.annotate(mid, manual.AnnotateBody(unit_key="2", judgment="B"))
    out = manual.annotate(mid, manual.AnnotateBody(unit_key="3", judgment="G", note="第三条备注"))

    assert out["status"] == "COMPLETED"
    s = out["summary"]
    assert (s["good"], s["same"], s["bad"]) == (2, 0, 1)
    assert s["win_rate"] == pytest.approx(66.7, abs=0.1)
    assert s["net_win_rate"] == pytest.approx(33.3, abs=0.1)


def test_gsb_skip_excluded_from_summary():
    mt = _upload("GSB", "query,content,baseline\nq1,c1,b1\nq2,c2,b2\n")
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="G"))
    out = manual.annotate(mid, manual.AnnotateBody(unit_key="2", skipped=True))
    assert out["status"] == "COMPLETED"
    assert out["summary"]["skipped"] == 1
    assert out["summary"]["scored"] == 1
    assert out["summary"]["win_rate"] == 100.0


def test_multi_dim_weighted_total():
    dims = [{"key": "rel", "name": "相关性", "weight": 60}, {"key": "qual", "name": "质量", "weight": 40}]
    mt = _upload("MULTI_DIM", "query,content\nq1,c1\n", dimensions=dims)
    mid = mt["id"]
    out = manual.annotate(mid, manual.AnnotateBody(unit_key="1", dim_scores={"rel": 5, "qual": 2}))
    unit = out["units"][0]
    assert unit["total"] == pytest.approx((5 * 60 + 2 * 40) / 100)  # 3.8
    assert out["status"] == "COMPLETED"
    assert out["summary"]["avg_total"] == pytest.approx(3.8)
    assert out["summary"]["weakest_dim"] == "质量"


def test_multi_dim_weight_must_sum_100():
    with pytest.raises(HTTPException) as ei:
        _upload("MULTI_DIM", "query,content\nq1,c1\n", dimensions=[{"key": "a", "name": "A", "weight": 30}])
    assert ei.value.status_code == 400


def test_multi_dim_override_total():
    dims = [{"key": "a", "name": "A", "weight": 100}]
    mt = _upload("MULTI_DIM", "query,content\nq1,c1\n", dimensions=dims)
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", dim_scores={"a": 3}))
    out = manual.annotate(mid, manual.AnnotateBody(unit_key="1", overridden_total=4.5))
    assert out["units"][0]["total"] == 4.5
    out2 = manual.annotate(mid, manual.AnnotateBody(unit_key="1", overridden_total=-1))
    assert out2["units"][0]["total"] == 3.0


def test_conversation_jsonl_grouping_and_roles():
    lines = "\n".join(
        json.dumps(x, ensure_ascii=False)
        for x in [
            {"session_id": "s1", "turn": 1, "role": "用户", "content": "你好"},
            {"session_id": "s1", "turn": 2, "role": "助手", "content": "在的"},
            {"session_id": "s2", "turn": 1, "role": "user", "content": "hi"},
        ]
    )
    mt = asyncio.run(
        manual.upload_manual_task(
            name="会话任务", description="", annotate_type="CONVERSATION",
            dimensions=json.dumps([{"key": "a", "name": "A", "weight": 100}]),
            gsb_swap_sides="false", report_template_id="", report_model="gpt-4.1",
            file=_File(lines, "c.jsonl"),
        )
    )
    assert mt["progress_total"] == 2
    u1 = next(u for u in mt["units"] if u["session_id"] == "s1")
    assert [t["role"] for t in u1["turns"]] == ["user", "assistant"]
    assert u1["key"] == "s1"


def test_conversation_nested_json():
    payload = [{"session_id": "x", "title": "退款", "turns": [
        {"role": "user", "content": "要退款"}, {"role": "assistant", "content": "已受理"},
    ]}]
    mt = asyncio.run(
        manual.upload_manual_task(
            name="嵌套会话", description="", annotate_type="CONVERSATION",
            dimensions=json.dumps([{"key": "a", "name": "A", "weight": 100}]),
            gsb_swap_sides="false", report_template_id="", report_model="gpt-4.1",
            file=_File(json.dumps(payload), "c.json"),
        )
    )
    assert mt["units"][0]["title"] == "退款"
    assert len(mt["units"][0]["turns"]) == 2


def test_report_generation_deterministic():
    mt = _upload("GSB", "query,content,baseline\nq1,c1,b1\nq2,c2,b2\n")
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="G"))
    manual.annotate(mid, manual.AnnotateBody(unit_key="2", judgment="B", note="事实错误"))

    manual.trigger_report(mid)
    for _ in range(60):
        if manual.get_report(mid).get("status") in ("READY", "FAILED"):
            break
        time.sleep(0.05)
    rp = manual.get_report(mid)
    assert rp["status"] == "READY"
    assert "评估报告" in rp["markdown"]


def test_report_requires_completed():
    mt = _upload("GSB", "query,content,baseline\nq1,c1,b1\nq2,c2,b2\n")
    with pytest.raises(HTTPException) as ei:
        manual.trigger_report(mt["id"])
    assert ei.value.status_code == 400


def test_export_csv_multi():
    dims = [{"key": "a", "name": "维度甲", "weight": 100}]
    mt = _upload("MULTI_DIM", "query,content\nq1,c1\n", dimensions=dims)
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", dim_scores={"a": 4}))
    body = manual.export_manual_task(mid).body.decode("utf-8")
    assert "维度甲" in body and "total" in body


def _upload_intent(text, filename="i.csv", labels="", name="意图任务"):
    return asyncio.run(
        manual.upload_manual_task(
            name=name, description="", annotate_type="INTENT",
            dimensions="[]", gsb_swap_sides="false", intent_labels=labels,
            report_template_id="", report_model="gpt-4.1", file=_File(text, filename),
        )
    )


def test_intent_upload_and_accuracy_summary():
    mt = _upload_intent(
        "query,predicted_intent,expected_intent\n"
        "q1,天气查询,天气查询\nq2,物流查询,售后咨询\nq3,闲聊,闲聊\nq4,天气查询,股票查询\n"
    )
    assert mt["annotate_type"] == "INTENT"
    assert mt["progress_total"] == 4
    mid = mt["id"]

    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="correct"))
    manual.annotate(mid, manual.AnnotateBody(unit_key="2", judgment="wrong", corrected_intent="售后咨询"))
    manual.annotate(mid, manual.AnnotateBody(unit_key="3", judgment="correct"))
    out = manual.annotate(mid, manual.AnnotateBody(unit_key="4", judgment="partial", corrected_intent="股票查询"))

    assert out["status"] == "COMPLETED"
    s = out["summary"]
    assert (s["correct"], s["partial"], s["wrong"]) == (2, 1, 1)
    assert s["accuracy"] == pytest.approx(50.0)
    assert s["lenient_accuracy"] == pytest.approx(62.5)
    weather = next(i for i in s["intents"] if i["intent"] == "天气查询")
    assert (weather["total"], weather["correct"]) == (2, 1)
    assert {(c["predicted"], c["corrected"]) for c in s["confusions"]} == {
        ("物流查询", "售后咨询"),
        ("天气查询", "股票查询"),
    }


def test_intent_correct_clears_corrected_intent():
    mt = _upload_intent("query,predicted_intent\nq1,天气查询\n")
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="wrong", corrected_intent="股票查询"))
    out = manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="correct"))
    assert out["units"][0]["corrected_intent"] == ""


def test_intent_missing_required_column_rejected():
    with pytest.raises(HTTPException) as ei:
        _upload_intent("query,foo\nq1,bar\n")
    assert ei.value.status_code == 422


def test_intent_labels_parsed_from_freeform():
    mt = _upload_intent("query,predicted_intent\nq1,天气查询\n", labels="天气查询，物流查询\n售后咨询")
    assert mt["intent_labels"] == ["天气查询", "物流查询", "售后咨询"]


def test_intent_report_deterministic():
    mt = _upload_intent("query,predicted_intent\nq1,天气查询\nq2,物流查询\n")
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="correct"))
    manual.annotate(mid, manual.AnnotateBody(unit_key="2", judgment="wrong", corrected_intent="售后咨询", note="应识别为售后"))
    manual.trigger_report(mid)
    for _ in range(60):
        if manual.get_report(mid).get("status") in ("READY", "FAILED"):
            break
        time.sleep(0.05)
    rp = manual.get_report(mid)
    assert rp["status"] == "READY"
    assert "意图准确率" in rp["markdown"]


def test_intent_export_columns():
    mt = _upload_intent("query,predicted_intent,expected_intent\nq1,天气查询,天气查询\n")
    mid = mt["id"]
    manual.annotate(mid, manual.AnnotateBody(unit_key="1", judgment="correct"))
    body = manual.export_manual_task(mid).body.decode("utf-8")
    assert "predicted_intent" in body and "corrected_intent" in body and "识别正确" in body


def test_duplicate_name_rejected():
    _upload("GSB", "query,content,baseline\nq1,c1,b1\n", name="重名")
    with pytest.raises(HTTPException) as ei:
        _upload("GSB", "query,content,baseline\nq1,c1,b1\n", name="重名")
    assert ei.value.status_code == 400
