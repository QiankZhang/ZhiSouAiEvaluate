# 后端（智搜策略效果评估）

FastAPI 服务，业务状态跑在内存字典里（`_tasks`/`_benchmarks`/`_datasets`），但会写穿到本地 SQLite，
进程重启会自动从库里恢复——不是纯内存服务了，见下方「持久化」。评测引擎支持**真实调用 DeepSeek** 与
**确定性模拟**两条路径。

## 模块

| 文件 | 职责 |
| --- | --- |
| `main.py` | 路由与编排（任务状态机、并发调度、降级熔断、持久化触发） |
| `db.py` | SQLite 持久化层：整份状态 JSON 快照，进程重启自动恢复 |
| `config.py` | 环境变量集中注入 + `.env` 加载 |
| `llm.py` | OpenAI 兼容协议客户端（标准库 urllib，重试/退避） |
| `engine.py` | Judge Agent：提示词 / 技能两条路径，结构化输出校验，后端重算加权总分与 GSB 裁决 |
| `skills_registry.py` | 技能包解析 + 内置技能注册表（`skills/` 目录） |
| `report.py` | 内置报告器（evaluation-report skill）：五段式 Markdown + Excel |

## 持久化

`_tasks`/`_benchmarks`/`_datasets`/`_id_seq` 仍然是业务逻辑直接读写的内存结构，但会自动写穿到
`backend/data/app.db`（SQLite，仅标准库 `sqlite3`，无新依赖）：

- 每次 `POST`/`PUT`/`DELETE /api/*` 请求返回后，立即整体落盘一次（HTTP 中间件触发）。
- 另有一个每 2 秒的后台线程做兜底快照——评测执行是后台线程异步跑的（进度/结果/报告的写入
  不发生在请求-响应周期内），靠这个定时快照兜住。
- 进程启动时从库里整份读回内存（`db.load_state()`），`_id_seq` 也一起持久化，重启后新建的
  ID 不会跟旧数据撞号。

不做关系型规范化拆表：三个集合各自整体序列化成一份 JSON snapshot 存表，改动面最小。数据量是
单进程本地工具的规模（几十到几百条记录），这个方案足够；要多进程/多副本部署再考虑换真正的
关系型 schema。删除 `backend/data/app.db*` 即可清空所有数据重新开始（不会被 git 提交，见 `.gitignore`）。

## 配置

复制 `.env.example` 为 `.env` 并填入 `DEEPSEEK_API_KEY`。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | — | 必填才能走真实调用 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | |
| `JUDGE_ENGINE` | `auto` | `auto`（配了 Key 且模型为 DeepSeek 时真实调用）/ `simulated` / `agent`（强制真实） |
| `JUDGE_CONCURRENCY` | `4` | 真实调用并发度 |

失败率熔断：真实调用下已完成 ≥10 条且 FAILED 占比 >20% 时，剩余条目自动降级为模拟，任务不整体失败。

## 运行

```bash
python -m venv .venv && .venv/bin/pip install -r ../requirements.txt
.venv/bin/uvicorn backend.main:app --port 8000   # cwd = site/
```

## 测试

```bash
.venv/bin/pip install -r ../requirements-dev.txt
.venv/bin/python -m pytest backend/tests -q      # cwd = site/
```
