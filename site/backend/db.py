"""SQLite 持久化层：进程重启后自动恢复 _tasks / _benchmarks / _datasets / _id_seq，
替代此前"纯内存、进程一重启就清空"的存储方式。

设计取舍：不做关系型规范化拆表。main.py / report.py / engine.py 里的业务逻辑全部直接
读写这几个内存列表里的字典（嵌套着 samples / results / config / report 等结构），
拆成多张关系表要重写这些代码、收益却有限——这是单进程本地工具，数据量是几十到几百条
记录级别。改为"整份状态 JSON 快照"落盘：结构不变、改动面最小，足以满足"重启不丢数据"。

只用标准库 sqlite3，不引入 SQLAlchemy 等第三方依赖。
"""

import json
import sqlite3
import threading
from typing import Any

from . import config

_conn: sqlite3.Connection | None = None
_write_lock = threading.Lock()

_DEFAULT_ID_SEQ = {"DS": 1000, "BM": 1000, "TK": 1000, "RT": 1000, "MT": 1000}


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("CREATE TABLE IF NOT EXISTS snapshot (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        _conn.commit()
    return _conn


def load_state() -> dict[str, Any]:
    """启动时调用一次；首次运行（表里还没有快照）时返回空集合与默认 ID 序号。"""
    conn = _get_conn()
    rows = dict(conn.execute("SELECT key, value FROM snapshot").fetchall())
    return {
        "tasks": json.loads(rows["tasks"]) if "tasks" in rows else [],
        "benchmarks": json.loads(rows["benchmarks"]) if "benchmarks" in rows else [],
        "datasets": json.loads(rows["datasets"]) if "datasets" in rows else [],
        "report_templates": json.loads(rows["report_templates"]) if "report_templates" in rows else [],
        "id_seq": json.loads(rows["id_seq"]) if "id_seq" in rows else dict(_DEFAULT_ID_SEQ),
        "accounts": json.loads(rows["accounts"]) if "accounts" in rows else [],
        "sessions": json.loads(rows["sessions"]) if "sessions" in rows else {},
        "manual_tasks": json.loads(rows["manual_tasks"]) if "manual_tasks" in rows else [],
    }


def save_state(
    tasks: list,
    benchmarks: list,
    datasets: list,
    id_seq: dict,
    report_templates: list | None = None,
    accounts: list | None = None,
    sessions: dict | None = None,
    manual_tasks: list | None = None,
) -> None:
    """整份快照落盘。调用方需保证传入时这几个列表/字典不会被其它线程并发修改
    （main.py 里在持有应用级 _lock 的情况下调用，序列化期间数据是稳定的）。"""
    payload = {
        "tasks": json.dumps(tasks, ensure_ascii=False),
        "benchmarks": json.dumps(benchmarks, ensure_ascii=False),
        "datasets": json.dumps(datasets, ensure_ascii=False),
        "report_templates": json.dumps(report_templates or [], ensure_ascii=False),
        "id_seq": json.dumps(id_seq),
        "accounts": json.dumps(accounts or [], ensure_ascii=False),
        "sessions": json.dumps(sessions or {}),
        "manual_tasks": json.dumps(manual_tasks or [], ensure_ascii=False),
    }
    conn = _get_conn()
    with _write_lock:
        conn.executemany(
            "INSERT INTO snapshot (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            list(payload.items()),
        )
        conn.commit()
