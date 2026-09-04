"""集中管理运行时配置：所有可调项通过环境变量注入，避免散落在业务代码里硬编码
（技术方案 §7.2 / §10）。import 时自动加载 backend/.env（不引入 python-dotenv，手写解析）。"""

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent.parent

# 内置技能包所在目录（仓库根 skills/）
SKILLS_DIR = _REPO_ROOT / "skills"


def _load_dotenv(path: Path) -> None:
    """极简 KEY=VALUE 解析：忽略空行与 # 注释，去掉包裹的引号；不覆盖已存在的进程环境变量。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(_BACKEND_DIR / ".env")


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _get_any(names: list[str], default: str) -> str:
    """按优先级读取多个环境变量名，取第一个非空值（兼容历史 DEEPSEEK_* 命名）。"""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# ---- 模型网关（效果评估平台大模型接口，OpenAI Chat Completions 兼容，见 API.md）----
# 网关自身按 API Key（可选，内网部署可留空）鉴权，并做日调用次数 / 日预算 / QPS 限流。
LLM_BASE_URL = _get_any(["LLM_BASE_URL", "DEEPSEEK_BASE_URL"], "http://10.37.254.124:8010/v1").rstrip("/")
LLM_API_KEY = _get_any(["LLM_API_KEY", "DEEPSEEK_API_KEY"], "")
LLM_MODEL = _get_any(["LLM_MODEL", "DEEPSEEK_MODEL"], "deepseek-v4-flash")
LLM_TIMEOUT_SEC = _get_int("LLM_TIMEOUT_SEC", 45)
LLM_MAX_RETRIES = _get_int("LLM_MAX_RETRIES", 3)
# 网关侧日调用次数上限（API.md「额度」：默认 1000 次/天）。仅用于前端额度提示与本地兜底计数，
# 真正的限流以网关 /v1/quota 与 429 响应为准。
LLM_DAILY_CALL_LIMIT = _get_int("LLM_DAILY_CALL_LIMIT", 1000)

# 网关提供的可用模型（API.md「可用模型」）。命中这些标识即走真实调用，其余走确定性模拟引擎。
LIVE_MODELS = {
    "qwen3.5-plus-online",
    "qwen3.5-plus",
    "qwen3.5-plus-offline",
    "deepseek-v4-flash",
    "deepseek-v4-flash-online",
    "Qwen3-235B-A22B-Instruct-2507",
}

# ---- 评测引擎 ----
# auto: 配了 Key 且裁判员模型在 LIVE_MODELS 时走真实调用，否则模拟；失败率过高自动降级
# simulated: 始终走确定性模拟打分（原实现）
# agent: 强制真实调用，缺 Key / 非 live 模型直接报错
JUDGE_ENGINE = _get("JUDGE_ENGINE", "auto").lower()
JUDGE_CONCURRENCY = max(1, _get_int("JUDGE_CONCURRENCY", 4))
# 熔断：已完成样本数达到阈值且失败占比超过比例时，剩余条目降级为模拟
DOWNGRADE_MIN_SAMPLES = _get_int("JUDGE_DOWNGRADE_MIN_SAMPLES", 10)
DOWNGRADE_FAIL_RATIO = _get_float("JUDGE_DOWNGRADE_FAIL_RATIO", 0.2)

# ---- 费用 / 耗时预估参数（技术方案 §7.2，均可配置）----
CHARS_PER_TOKEN = _get_float("CHARS_PER_TOKEN", 1.5)
OUTPUT_CHARS_PER_DIM = _get_int("OUTPUT_CHARS_PER_DIM", 24)
REQ_PER_SEC = _get_float("REQ_PER_SEC", 8.0)

# ---- 持久化（SQLite，进程重启不丢数据，见 db.py）----
DB_PATH = Path(_get("DB_PATH", str(_BACKEND_DIR / "data" / "app.db")))

# ---- 博文数据集：mid → 原始物料（qinglong 流水线，见 weibo.py）----
# 后端把 mid 列表写临时 txt，子进程调 qinglong 的 bin.make_data / bin.process_data，
# 回读逐行追加的 jsonl 感知进度。qinglong 依赖新浪内网（hbase/redis/内容接口），
# 与后端刻意精简的依赖隔离在各自的 Python 环境里。
WEIBO_QINGLONG_DIR = _get("WEIBO_QINGLONG_DIR", str(_REPO_ROOT.parent / "qinglong"))
WEIBO_QINGLONG_PYTHON = _get("WEIBO_QINGLONG_PYTHON", "python3")
WEIBO_QINGLONG_BASE_PATH = _get("WEIBO_QINGLONG_BASE_PATH", "")  # 传给 qinglong 的 QINGLONG_BASE_PATH，空则用其自带默认
WEIBO_CONVERT_CONCURRENCY = max(1, _get_int("WEIBO_CONVERT_CONCURRENCY", 10))
WEIBO_CONVERT_TIMEOUT_SEC = _get_int("WEIBO_CONVERT_TIMEOUT_SEC", 3600)
WEIBO_MID_MAX = _get_int("WEIBO_MID_MAX", 2000)  # 单个博文数据集最多 mid 数
# 关闭真实转换、直接用占位物料（本地/无内网联调用）
WEIBO_CONVERT_STUB = _get("WEIBO_CONVERT_STUB", "").lower() in {"1", "true", "yes"}


def engine_for(model: str) -> str:
    """返回该裁判员模型实际应使用的引擎：'agent' 或 'simulated'。
    网关无需 API Key 即可调用，因此只按模型标识是否在网关可用列表内判断。"""
    live = model in LIVE_MODELS
    if JUDGE_ENGINE == "simulated":
        return "simulated"
    if JUDGE_ENGINE == "agent":
        return "agent"  # 由调用方在缺 Key 时报错
    return "agent" if live else "simulated"
