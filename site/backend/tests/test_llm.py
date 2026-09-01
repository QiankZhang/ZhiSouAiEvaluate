import urllib.error

import pytest

from backend import config, llm


def test_is_live_matches_gateway_models():
    assert llm.is_live("qwen3.5-plus-online")
    assert llm.is_live("deepseek-v4-flash")
    assert not llm.is_live("gpt-4.1")


def test_local_call_counter_increments_and_is_date_scoped(monkeypatch):
    monkeypatch.setattr(llm, "_calls", {"date": "", "count": 0})
    assert llm.local_calls_today() == 0
    llm._record_call()
    llm._record_call()
    assert llm.local_calls_today() == 2


def test_is_quota_error_detects_gateway_code():
    body = '{"error": {"message": "日调用次数已达上限", "type": "rate_limit_error", "code": "quota_exceeded"}}'
    assert llm._is_quota_error(body)
    assert not llm._is_quota_error('{"error": {"code": "server_error"}}')
    assert not llm._is_quota_error("not json")


def test_quota_exceeded_raises_without_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(_payload):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            "u", 429, "Too Many Requests", {},
            _FakeBody('{"error": {"code": "quota_exceeded"}}'),
        )

    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(llm.QuotaExceededError):
        llm.chat_completion([{"role": "user", "content": "hi"}], model="qwen3.5-plus-online")
    assert calls["n"] == 1  # 配额超限不重试


def test_daily_call_limit_default_is_1000():
    assert config.LLM_DAILY_CALL_LIMIT == 1000


class _FakeBody:
    def __init__(self, text):
        self._text = text.encode("utf-8")

    def read(self):
        return self._text

    def close(self):
        pass
