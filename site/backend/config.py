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


# ---- DeepSeek / 模型网关（OpenAI 兼容协议）----
DEEPSEEK_API_KEY = _get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = _get("DEEPSEEK_MODEL", "deepseek-v4-flash")
LLM_TIMEOUT_SEC = _get_int("LLM_TIMEOUT_SEC", 45)
LLM_MAX_RETRIES = _get_int("LLM_MAX_RETRIES", 3)

# 真实调用会命中的裁判员模型（其余模型标识只做展示 / 走模拟引擎）
LIVE_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"}

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


def engine_for(model: str) -> str:
    """返回该裁判员模型实际应使用的引擎：'agent' 或 'simulated'。"""
    live = bool(DEEPSEEK_API_KEY) and model in LIVE_MODELS
    if JUDGE_ENGINE == "simulated":
        return "simulated"
    if JUDGE_ENGINE == "agent":
        return "agent"  # 由调用方在缺 Key 时报错
    return "agent" if live else "simulated"
