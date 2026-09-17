"""博文数据集 AI 评估中心侧：main.py 的 weibo_mode=qa 解析 + 建数据集流程。"""

import time

import pytest
from fastapi import HTTPException

from backend import main, weibo


def test_parse_weibo_rows_material_mode_two_columns():
    raw = "mid,智搜结果\n5031234567890,结果A\n".encode("utf-8")
    rows, errors = main._parse_weibo_upload_rows(raw, "d.csv", with_query=False)
    assert errors == []
    assert rows == [{"mid": "5031234567890", "content": "结果A"}]


def test_parse_weibo_rows_qa_mode_three_columns_matches_real_header():
    """真实文件表头就是 mid,query,内容（内容引导及回答.xlsx）。"""
    raw = "mid,query,内容\n5031234567890,这些角色出自哪部作品,来自XX剧\n".encode("utf-8")
    rows, errors = main._parse_weibo_upload_rows(raw, "d.csv", with_query=True)
    assert errors == []
    assert rows == [{"mid": "5031234567890", "query": "这些角色出自哪部作品", "content": "来自XX剧"}]


def test_parse_weibo_rows_qa_mode_requires_query_column():
    raw = "mid,智搜结果\n5031234567890,结果A\n".encode("utf-8")
    rows, errors = main._parse_weibo_upload_rows(raw, "d.csv", with_query=True)
    assert not rows
    assert errors and "query" in errors[0]["message"]


def test_create_weibo_dataset_qa_mode_end_to_end(monkeypatch):
    monkeypatch.setattr(weibo.config, "WEIBO_CONVERT_STUB", True)
    raw = "mid,query,内容\n5031234567890,这些角色出自哪部作品,来自XX剧\n".encode("utf-8")

    ds = main._create_weibo_dataset("问答集A", "", "CSV", raw, "d.csv", weibo_mode="qa")
    assert ds["weibo_mode"] == "qa"
    assert ds["eval_method"] == "MULTI_DIM"

    did = ds["id"]
    for _ in range(40):
        d = main._find_dataset(did)
        if d["convert_status"] != "CONVERTING":
            break
        time.sleep(0.05)
    d = main._find_dataset(did)
    assert d["convert_status"] == "READY"
    sample = d["samples"][0]
    assert sample["asked_query"] == "这些角色出自哪部作品"
    assert sample["content"] == "来自XX剧"
    assert "占位物料" in sample["query"]
    assert sample["query"].endswith("【用户问题】这些角色出自哪部作品")


def test_create_weibo_dataset_rejects_bad_mode():
    with pytest.raises(HTTPException) as ei:
        main._create_weibo_dataset("x", "", "CSV", b"mid,content\n1,a\n", "d.csv", weibo_mode="bogus")
    assert ei.value.status_code == 400
