# 效果评估平台 · 大模型接口文档

## 接入信息

| 项 | 值 |
|----|-----|
| Base URL | `http://10.37.254.124:8010` |
| 协议 | OpenAI Chat Completions 兼容 |
| 模型类型 | 均为自部署 `type=weibo` |

---

## 可用模型

| model | 说明 |
|-------|------|
| `qwen3.5-plus-online` | 默认 |
| `qwen3.5-plus` | |
| `qwen3.5-plus-offline` | |
| `deepseek-v4-flash` | |
| `deepseek-v4-flash-online` | |
| `Qwen3-235B-A22B-Instruct-2507` | |

---

## 额度

| 限制项 | 默认值 |
|--------|--------|
| 日调用次数 | 1000 次/天 |
| 日预算 | 50 元/天（按 input/output token 折算） |
| QPS | 5 次/秒 |

超限返回 **HTTP 429**：

```json
{
  "error": {
    "message": "日调用次数已达上限（1000 次/天）",
    "type": "rate_limit_error",
    "code": "quota_exceeded"
  }
}
```

查询当日用量：

```
GET /v1/quota
```

```json
{
  "calls": 12,
  "remaining_calls": 988,
  "cost_yuan": 0.214,
  "remaining_budget_yuan": 49.786,
  "qps_limit": 5
}
```

---

## 对话接口

```
POST /v1/chat/completions
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | 见「可用模型」 |
| messages | array | 是 | `[{"role":"user","content":"..."}]`，role 支持 system / user / assistant |
| stream | boolean | 否 | `false` 非流式（默认），`true` 流式 |
| temperature | float | 否 | 默认 0.7 |
| max_tokens | int | 否 | 默认 4096 |
| thinking | boolean | 否 | 默认 false |

### 非流式

请求：`"stream": false`（或不传 stream）

```bash
curl -X POST "http://10.37.254.124:8010/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-plus-online",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'
```

响应：一次性返回完整结果

```json
{
  "id": "eval-a1b2c3d4e5f67890",
  "model": "qwen3.5-plus-online",
  "choices": [
    {
      "message": {"role": "assistant", "content": "你好！……"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 42,
    "total_tokens": 57
  }
}
```

### 流式

请求：`"stream": true`

```bash
curl -X POST "http://10.37.254.124:8010/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-plus-online",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

响应：SSE 逐段返回，`Content-Type: text/event-stream`

```
data: {"choices":[{"delta":{"content":"你"},"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}

data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}}

data: [DONE]
```

解析：逐行读取 `data: ` 后的 JSON，取 `choices[0].delta.content` 拼接；最后一包带 `usage` 和 `finish_reason: stop`，遇到 `data: [DONE]` 结束。
