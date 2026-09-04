# 后端（智搜策略效果评估）

FastAPI 服务，业务状态跑在内存字典里（`_tasks`/`_benchmarks`/`_datasets`），但会写穿到本地 SQLite，
进程重启会自动从库里恢复——不是纯内存服务了，见下方「持久化」。评测引擎支持**真实调用效果评估平台
大模型网关**（OpenAI 兼容，见仓库根 `API.md`）与**确定性模拟**两条路径。

## 模块

| 文件 | 职责 |
| --- | --- |
| `main.py` | 路由与编排（任务状态机、并发调度、降级熔断、持久化触发） |
| `db.py` | SQLite 持久化层：整份状态 JSON 快照，进程重启自动恢复 |
| `accounts.py` | 组织与账号登录：单默认组织「智搜产品」+ 账号密码 + 会话；鉴权在 `main.py` 中间件统一做 |
| `config.py` | 环境变量集中注入 + `.env` 加载 |
| `llm.py` | 大模型网关客户端（OpenAI 兼容，标准库 urllib，重试/退避，当日调用计数，`/v1/quota` 查询） |
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

复制 `.env.example` 为 `.env`。大模型接口见仓库根 `API.md`；网关为内网自部署，默认无需 API Key。
历史 `DEEPSEEK_*` 变量名仍作兼容回退。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://10.37.254.124:8010/v1` | 网关地址（OpenAI 兼容，含 `/v1`） |
| `LLM_API_KEY` | — | 可选，网关需要鉴权时填 |
| `LLM_MODEL` | `deepseek-v4-flash` | 默认裁判员模型（前端标「推荐」） |
| `LLM_DAILY_CALL_LIMIT` | `1000` | 网关日调用次数上限，用于额度提示与本地兜底计数 |
| `JUDGE_ENGINE` | `auto` | `auto`（模型在网关可用列表内则真实调用）/ `simulated` / `agent`（强制真实） |
| `JUDGE_CONCURRENCY` | `4` | 真实调用并发度 |
| `WEIBO_QINGLONG_DIR` | `/data1/minisearch/upload/qinglong` | 博文数据集：qinglong 流水线仓库目录（见 `weibo.py`） |
| `WEIBO_QINGLONG_PYTHON` | `python3` | qinglong 用的 Python 解释器（需装 aiohttp/redis/pandas/tqdm，能访问新浪内网） |
| `WEIBO_CONVERT_CONCURRENCY` | `10` | mid → 物料抓取并发度 |
| `WEIBO_CONVERT_TIMEOUT_SEC` | `3600` | 单阶段子进程超时 |
| `WEIBO_MID_MAX` | `2000` | 单个博文数据集最多 mid 数 |
| `WEIBO_CONVERT_STUB` | — | 置 `1` 跳过真实转换、用占位物料（无内网联调用） |

前端顶部导航栏展示当日调用额度（`GET /api/quota`，优先取网关 `/v1/quota`，不可达回退本地计数）。

## 博文数据集（mid → 原始物料）

创建数据集 / 人工标注任务时勾选「博文数据」，上传两列 `mid,智搜结果`。后端把 mid 写临时 txt，
子进程调 `qinglong` 流水线（`bin.make_data` 抓物料 → `bin.process_data` 补图片分析），回读逐行
追加的 jsonl 感知进度；物料按分段标题块拼进样本 `query`，`智搜结果` 落 `content`，评估方式固定
`MULTI_DIM`。转换期间数据集 `status=CONVERTING`，`GET /api/datasets/{id}/convert-progress` 查进度；
部分失败以空物料占位保留（`convert_status=PARTIAL`），`POST .../retry-conversion` 仅重试失败 mid，
`GET .../failed-mids` 下载失败清单。qinglong 依赖隔离在它自己的 Python 环境里，见 `weibo.py`。

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
