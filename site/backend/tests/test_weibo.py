"""博文数据集：mid → 原始物料（backend/weibo.py）。不起子进程，用 STUB / monkeypatch。"""

import pytest

from backend import weibo


def test_normalize_mids_dedup_and_validate():
    valid, invalid = weibo.normalize_mids(["5031234567890", " 5031234567890 ", "", "abc", "509999"])
    assert valid == ["5031234567890", "509999"]
    assert invalid == ["abc"]


def test_flatten_material_segments_non_empty_in_order():
    record = {
        "mid": "5031234567890",
        "mid_content": "正文内容",
        "nick": "博主A",
        "p_time": "2026-09-01",
        "blog_summary": "博文总结内容",
        "video_info": "",
        "voice2text": "音转文内容",
        "pid_desc_analysis_order": [{"pid": "p1", "desc": "图descA", "analysis": "分析A"}],
        "comment_summary": "",
        "user_behaviour": [{"next_query": "追问1", "count": 3}],
        "sence_tag": "其他",
    }
    text = weibo.flatten_material(record)
    assert text.index("【博文正文】") < text.index("【发博信息】") < text.index("【博文总结】")
    assert "博主A · 2026-09-01" in text
    assert "【视频总结】" not in text  # 空字段跳过
    assert "【类别标签】" not in text  # "其他" 视为无标签
    assert "图1：图descA 分析A" in text
    assert "追问1（3）" in text


def test_convert_rows_stub(monkeypatch):
    monkeypatch.setattr(weibo.config, "WEIBO_CONVERT_STUB", True)
    rows = [{"mid": "5031234567890", "content": "智搜结果1"}, {"mid": "509999", "content": "智搜结果2"}]
    samples, failed = weibo.convert_rows(rows)
    assert failed == []
    assert samples[0]["mid"] == "5031234567890"
    assert samples[0]["content"] == "智搜结果1"
    assert "占位物料" in samples[0]["query"]
    assert samples[0]["material_status"] == "OK"


def test_convert_rows_partial_failure(monkeypatch):
    monkeypatch.setattr(weibo.config, "WEIBO_CONVERT_STUB", False)

    def fake_pipeline(mids, progress_cb, log):
        if progress_cb:
            progress_cb(len(mids), "抓取物料")
        return {
            "5031234567890": {"mid": "5031234567890", "mid_content": "正文A"},
            "509999": {"mid": "509999", "_error": "hbase 超时"},
        }

    monkeypatch.setattr(weibo, "_pipeline", fake_pipeline)
    rows = [{"mid": "5031234567890", "content": "r1"}, {"mid": "509999", "content": "r2"}, {"mid": "508888", "content": "r3"}]
    samples, failed = weibo.convert_rows(rows)
    assert {f["mid"] for f in failed} == {"509999", "508888"}
    assert samples[0]["material_status"] == "OK"
    assert samples[1]["material_status"] == "FAILED"
    assert samples[1]["query"] == ""
    assert "未返回" in failed[1]["error"]  # 508888 pipeline 未返回


def test_pipeline_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(weibo.config, "WEIBO_CONVERT_STUB", False)
    monkeypatch.setattr(weibo.config, "WEIBO_QINGLONG_DIR", str(tmp_path / "nope"))
    with pytest.raises(weibo.WeiboConvertError):
        weibo._pipeline(["5031234567890"], None, None)
