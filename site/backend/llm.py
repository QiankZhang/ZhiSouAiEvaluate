"""LLM 适配层：统一走效果评估平台大模型网关（OpenAI Chat Completions 兼容，见 API.md），
用标准库 urllib 发请求，不引入 httpx / openai SDK。Worker 在线程内同步调用，无需 async。"""

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import date

from . import config


class LlmError(RuntimeError):
    """模型调用失败（重试耗尽 / 协议错误）。"""


class QuotaExceededError(LlmError):
    """网关返回日调用次数 / 日预算超限（HTTP 429，code=quota_exceeded），不应重试。"""


# 本地当日调用计数：网关 /v1/quota 不可达时给前端额度提示兜底。以网关返回为准。
_calls_lock = threading.Lock()
_calls = {"date": "", "count": 0}


def _record_call() -> None:
    today = date.today().isoformat()
    with _calls_lock:
        if _calls["date"] != today:
            _calls["date"], _calls["count"] = today, 0
        _calls["count"] += 1


def local_calls_today() -> int:
    today = date.today().isoformat()
    with _calls_lock:
        return _calls["count"] if _calls["date"] == today else 0


def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"
    return headers


def is_live(model: str) -> bool:
    """该模型是否会真正打到网关（在网关可用模型列表内）。网关无需 API Key。"""
    return model in config.LIVE_MODELS


def fetch_quota(timeout: float | None = None) -> dict:
    """查询网关当日用量（API.md：GET /v1/quota）。失败抛 LlmError。"""
    req = urllib.request.Request(
        f"{config.LLM_BASE_URL}/quota", method="GET", headers=_auth_headers()
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.LLM_TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LlmError(f"额度查询失败：{exc}") from exc


def _post(payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{config.LLM_BASE_URL}/chat/completions",
        data=data,
        method="POST",
        headers=_auth_headers(),
    )
    with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_SEC) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    _record_call()
    return body


def _is_quota_error(body: str) -> bool:
    try:
        return (json.loads(body).get("error") or {}).get("code") == "quota_exceeded"
    except (json.JSONDecodeError, AttributeError):
        return False


def chat_completion(
    messages: list[dict],
    *,
    model: str | None = None,
    response_format: dict | None = None,
    temperature: float = 0.0,
) -> dict:
    """返回原始响应 dict。对 429 / 5xx / 网络超时做指数退避重试（≤ LLM_MAX_RETRIES）。
    网关不支持 function calling，结构化输出统一走 response_format=json_object。
    密钥只在 header 出现，任何异常信息里都不回显。"""
    payload: dict = {
        "model": model or config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    last_err: Exception | None = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            return _post(payload)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")[:500]
            except Exception:  # noqa: BLE001 - 诊断信息尽力而为
                pass
            if exc.code == 429 and _is_quota_error(body):
                raise QuotaExceededError(
                    f"今日模型调用额度已达上限（{config.LLM_DAILY_CALL_LIMIT} 次/天），请明日再试"
                ) from exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < config.LLM_MAX_RETRIES - 1:
                last_err = LlmError(f"HTTP {exc.code}")
                time.sleep(2 ** attempt)
                continue
            raise LlmError(f"模型返回 HTTP {exc.code}：{body}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < config.LLM_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise LlmError(f"模型调用失败：{exc}") from exc
    raise LlmError(f"模型调用失败：{last_err}")


def parse_json_response(response: dict) -> dict:
    """解析模型返回的 JSON 结果对象。网关不支持 function calling，统一走
    response_format=json_object，结果写在 message.content 里；同时兼容早期
    tool_calls 形态（历史响应 / 单测桩）。"""
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        if fn.get("arguments"):
            return json.loads(fn["arguments"])
    content = (message.get("content") or "").strip()
    if content:
        # 去掉可能的 ```json 包裹
        if content.startswith("```"):
            content = content.strip("`")
            content = content[content.find("\n") + 1 :] if "\n" in content else content
        return json.loads(content)
    raise LlmError("响应中没有可解析的 JSON 内容")


def usage_of(response: dict) -> dict:
    u = response.get("usage") or {}
    return {
        "input_tokens": int(u.get("prompt_tokens") or 0),
        "output_tokens": int(u.get("completion_tokens") or 0),
    }
