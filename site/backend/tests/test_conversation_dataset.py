"""AI 评估中心：多轮会话数据集（session_id 分组 + query类型=mid 自动解析）。"""

import time

import pytest
from fastapi import HTTPException

from backend import engine, main, weibo

_HEADER = "session_id,conversation_id,会话时间,query类型,query,回答,会话轮数\n"


def _csv(rows: str) -> bytes:
    return (_HEADER + rows).encode("utf-8")


def test_parse_conversation_turn_rows_basic():
    raw = _csv(
        "s1,c1,2026-09-09 12:08:16,mid,5340208260189424,关于这条微博你需要我帮你做什么？,2\n"
        "s1,c2,2026-09-09 12:10:48,,详细总结这篇微博的评论内容,评论区整体呈现哀悼与祈福基调,2\n"
    )
    rows, errors = main._parse_conversation_turn_rows(raw, "d.csv")
    assert errors == []
    assert len(rows) == 2
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["is_mid"] is True
    assert rows[0]["query"] == "5340208260189424"
    assert rows[1]["is_mid"] is False


def test_parse_conversation_turn_rows_missing_required_column():
    raw = "session_id,query\ns1,hi\n".encode("utf-8")
    rows, errors = main._parse_conversation_turn_rows(raw, "d.csv")
    assert not rows
    assert errors and "回答" in errors[0]["message"]


def test_parse_conversation_turn_rows_missing_required_field_in_row():
    raw = _csv("s1,c1,2026-09-09 12:08:16,,,这是回答,1\n")  # 缺 query
    rows, errors = main._parse_conversation_turn_rows(raw, "d.csv")
    assert not rows
    assert errors and "缺少必填字段" in errors[0]["message"]


def test_parse_conversation_turn_rows_rejects_bad_mid():
    raw = _csv("s1,c1,2026-09-09 12:08:16,mid,不是mid,回答,1\n")
    rows, errors = main._parse_conversation_turn_rows(raw, "d.csv")
    assert not rows
    assert errors and "mid" in errors[0]["message"]


def test_group_conversation_sessions_orders_by_time_and_builds_turns():
    raw = _csv(
        # 故意把后一轮放在文件里的前面，验证按会话时间重新排序
        "s1,c2,2026-09-09 12:10:48,,详细总结这篇微博的评论内容,评论区整体呈现哀悼与祈福基调,2\n"
        "s1,c1,2026-09-09 12:08:16,mid,5340208260189424,关于这条微博你需要我帮你做什么？,2\n"
    )
    rows, errors = main._parse_conversation_turn_rows(raw, "d.csv")
    assert errors == []
    sessions = main._group_conversation_sessions(rows)
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess["session_id"] == "s1"
    # 4 turns: user(mid占位)/assistant/user/assistant，且 mid 轮在最前（时间更早）
    assert [t["role"] for t in sess["turns"]] == ["user", "assistant", "user", "assistant"]
    assert sess["turns"][0]["is_mid"] is True
    assert sess["turns"][0]["mid"] == "5340208260189424"
    assert sess["turns"][2]["content"] == "详细总结这篇微博的评论内容"
    assert len(sess["mid_turns"]) == 1


def test_create_conversation_dataset_without_mid_is_ready_synchronously():
    raw = _csv(
        "s1,c1,2026-09-09 12:08:16,,你好,你好，有什么可以帮你？,2\n"
    )
    ds = main._create_conversation_dataset("会话集A", "", "CSV", raw, "d.csv")
    assert ds["is_conversation"] is True
    assert ds["eval_method"] == "MULTI_DIM"
    assert ds["convert_status"] == "READY"
    d = main._find_dataset(ds["id"])
    sample = d["samples"][0]
    assert sample["session_id"] == "s1"
    assert "User：你好" in sample["query"]
    assert "Assistant：你好，有什么可以帮你？" in sample["query"]


def test_create_conversation_dataset_resolves_mid_and_replaces_query(monkeypatch):
    monkeypatch.setattr(weibo.config, "WEIBO_CONVERT_STUB", True)
    raw = _csv(
        "s1,c1,2026-09-09 12:08:16,mid,5340208260189424,关于这条微博你需要我帮你做什么？,2\n"
        "s1,c2,2026-09-09 12:10:48,,详细总结这篇微博的评论内容,评论区整体呈现哀悼与祈福基调,2\n"
    )
    ds = main._create_conversation_dataset("会话集B", "", "CSV", raw, "d.csv")
    assert ds["convert_status"] in ("CONVERTING", "READY")  # stub 转换极快，可能在返回前已跑完

    did = ds["id"]
    for _ in range(40):
        d = main._find_dataset(did)
        if d["convert_status"] != "CONVERTING":
            break
        time.sleep(0.05)
    d = main._find_dataset(did)
    assert d["convert_status"] == "READY"
    sample = d["samples"][0]
    mid_turn = sample["turns"][0]
    assert mid_turn["is_mid"] is True
    assert "占位物料" in mid_turn["content"]
    assert sample["mid_turns"][0]["status"] == "OK"
    assert "占位物料" in sample["query"]
    assert "详细总结这篇微博的评论内容" in sample["query"]


def test_create_conversation_dataset_rejects_no_sessions():
    with pytest.raises(HTTPException) as ei:
        main._create_conversation_dataset("空集", "", "CSV", _HEADER.encode("utf-8"), "d.csv")
    assert ei.value.status_code == 422


def test_engine_user_message_renders_conversation_turns():
    item = {
        "turns": [
            {"turn": 1, "role": "user", "content": "你好"},
            {"turn": 2, "role": "assistant", "content": "你好，有什么可以帮你？"},
        ]
    }
    msg = engine._user_message(item, is_gsb=False)
    assert "多轮对话" in msg
    assert "User：你好" in msg
    assert "Assistant：你好，有什么可以帮你？" in msg
