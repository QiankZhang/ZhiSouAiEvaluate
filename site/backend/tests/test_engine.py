import pytest

from backend import engine, llm

MULTI_BENCHMARK = {
    "eval_method": "MULTI_DIM",
    "type": "PROMPT",
    "config": {
        "prompt_template": "评测：{query} / {待评内容}",
        "dimensions": [
            {"key": "relevance", "name": "相关性", "weight": 40, "criteria": "命中意图"},
            {"key": "quality", "name": "质量", "weight": 30, "criteria": "准确完整"},
            {"key": "format", "name": "格式", "weight": 30, "criteria": "排版"},
        ],
        "confidence_enabled": True,
    },
}

GSB_BENCHMARK = {
    "eval_method": "GSB",
    "type": "PROMPT",
    "config": {
        "prompt_template": "对比：{query}",
        "dimensions": [
            {"key": "relevance", "name": "相关性", "weight": 50},
            {"key": "quality", "name": "质量", "weight": 50},
        ],
        "gsb": {"rules": "优于基线为 Good", "adjudication_dimension": "overall"},
        "confidence_enabled": True,
    },
}

SAMPLE = {"row_index": 1, "query": "世界杯赛程", "content": "最新赛程...", "baseline": "旧赛程..."}


def test_weighted_total_matches_skill_formula():
    # 4*40 + 3*30 + 5*30 = 160 + 90 + 150 = 400 → /100 = 4.0
    total = engine._weighted_total({"relevance": 4, "quality": 3, "format": 5}, MULTI_BENCHMARK["config"]["dimensions"])
    assert total == 4.0


def test_multi_evaluation_parsed_and_recomputed(monkeypatch, make_tool_response):
    monkeypatch.setattr(
        llm,
        "chat_completion",
        lambda *a, **k: make_tool_response(
            "submit_evaluation",
            {
                "dimensions": [
                    {"key": "relevance", "score": 4, "reason": "命中"},
                    {"key": "quality", "score": 3, "reason": "尚可"},
                    {"key": "format", "score": 5, "reason": "清晰"},
                ],
                "confidence": 0.9,
                "reason": "整体不错",
            },
        ),
    )
    r = engine.evaluate_item_llm(SAMPLE, MULTI_BENCHMARK, "deepseek-v4-flash")
    assert r["status"] == "SUCCESS"
    assert r["scores"]["total"] == 4.0
    assert {d["key"] for d in r["scores"]["dimensions"]} == {"relevance", "quality", "format"}
    assert r["confidence"] == 0.9
    assert r["_usage"]["input_tokens"] == 100


def test_multi_evaluation_rejects_dimension_key_mismatch(monkeypatch, make_tool_response):
    monkeypatch.setattr(
        llm,
        "chat_completion",
        lambda *a, **k: make_tool_response(
            "submit_evaluation",
            {"dimensions": [{"key": "relevance", "score": 4, "reason": "x"}], "confidence": 0.8},
        ),
    )
    with pytest.raises(llm.LlmError):
        engine.evaluate_item_llm(SAMPLE, MULTI_BENCHMARK, "deepseek-v4-flash")


@pytest.mark.parametrize(
    "exp,base,expected",
    [
        ([5, 5], [3, 3], "Good"),   # diff 2.0
        ([3, 3], [5, 5], "Bad"),    # diff -2.0
        ([4, 4], [4, 4], "Same"),   # diff 0
    ],
)
def test_gsb_threshold_decision(monkeypatch, make_tool_response, exp, base, expected):
    monkeypatch.setattr(
        llm,
        "chat_completion",
        lambda *a, **k: make_tool_response(
            "submit_evaluation",
            {
                "dimensions": [
                    {"key": "relevance", "exp_score": exp[0], "base_score": base[0]},
                    {"key": "quality", "exp_score": exp[1], "base_score": base[1]},
                ],
                "reason": "对比结论",
                "confidence": 0.85,
            },
        ),
    )
    r = engine.evaluate_item_llm(SAMPLE, GSB_BENCHMARK, "deepseek-v4-flash")
    assert r["scores"]["judgment"] == expected
    assert r["baseline"] == "旧赛程..."


def test_invalid_json_content_raises(monkeypatch):
    monkeypatch.setattr(
        llm,
        "chat_completion",
        lambda *a, **k: {"choices": [{"message": {"content": "not json at all"}}], "usage": {}},
    )
    with pytest.raises(llm.LlmError):
        engine.evaluate_item_llm(SAMPLE, MULTI_BENCHMARK, "deepseek-v4-flash")


def test_system_prompt_includes_dimensions_and_skill():
    skill = {"name": "multi-dimension-evaluation", "version": "1.1.0", "instructions": "打分说明正文"}
    sp = engine.build_system_prompt(MULTI_BENCHMARK, skill)
    assert "multi-dimension-evaluation" in sp
    assert "打分说明正文" in sp
    assert "relevance" in sp and "相关性" in sp
