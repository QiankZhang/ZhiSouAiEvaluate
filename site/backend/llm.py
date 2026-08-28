"""LLM 适配层：统一走 OpenAI 兼容协议（DeepSeek 即兼容），用标准库 urllib 发请求，
不引入 httpx / openai SDK。Worker 在线程内同步调用，无需 async。"""

import json
import time
import urllib.error
import urllib.request

from . import config


class LlmError(RuntimeError):
    """模型调用失败（重试耗尽 / 协议错误）。"""


def is_live(model: str) -> bool:
    """该模型是否会真正打到远端（在 LIVE_MODELS 且配置了 Key）。"""
    return bool(config.DEEPSEEK_API_KEY) and model in config.LIVE_MODELS


def _post(payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat_completion(
    messages: list[dict],
    *,
    model: str | None = None,
    tools: list[dict] | None = None,
    tool_choice: dict | str | None = None,
    response_format: dict | None = None,
    temperature: float = 0.0,
) -> dict:
    """返回原始响应 dict。对 429 / 5xx / 网络超时做指数退避重试（≤ LLM_MAX_RETRIES）。
    密钥只在 header 出现，任何异常信息里都不回显。"""
    if not config.DEEPSEEK_API_KEY:
        raise LlmError("未配置 DEEPSEEK_API_KEY，无法调用模型")

    payload: dict = {
        "model": model or config.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
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


def extract_tool_arguments(response: dict, tool_name: str) -> dict:
    """从响应里取出指定 function 的 arguments（JSON 解析）。
    模型若没走 tool call 而是把 JSON 写在 content 里，则兜底从 content 解析。"""
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        if fn.get("name") == tool_name:
            return json.loads(fn.get("arguments") or "{}")
    content = (message.get("content") or "").strip()
    if content:
        # 去掉可能的 ```json 包裹
        if content.startswith("```"):
            content = content.strip("`")
            content = content[content.find("\n") + 1 :] if "\n" in content else content
        return json.loads(content)
    raise LlmError(f"响应中未找到 {tool_name} 工具调用，也无法从 content 解析 JSON")


def usage_of(response: dict) -> dict:
    u = response.get("usage") or {}
    return {
        "input_tokens": int(u.get("prompt_tokens") or 0),
        "output_tokens": int(u.get("completion_tokens") or 0),
    }
