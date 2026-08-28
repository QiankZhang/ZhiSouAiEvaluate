import pytest

from backend import config


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """每个用例指向独立的临时 SQLite 文件，避免污染开发环境自己的 backend/data/app.db。"""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    from backend import db as db_mod

    db_mod._conn = None  # 强制下次 _get_conn() 用新的 DB_PATH 重新建连接
    yield db_mod
    if db_mod._conn is not None:
        db_mod._conn.close()
        db_mod._conn = None


def test_load_state_empty_returns_defaults(fresh_db):
    state = fresh_db.load_state()
    assert state == {
        "tasks": [],
        "benchmarks": [],
        "datasets": [],
        "id_seq": {"DS": 1000, "BM": 1000, "TK": 1000},
    }


def test_save_then_load_roundtrip(fresh_db):
    tasks = [{"id": "TK-1001", "name": "任务A"}]
    benchmarks = [{"id": "BM-1001", "name": "基准A"}]
    datasets = [{"id": "DS-1001", "name": "数据集A"}]
    id_seq = {"DS": 1001, "BM": 1001, "TK": 1001}

    fresh_db.save_state(tasks, benchmarks, datasets, id_seq)
    state = fresh_db.load_state()

    assert state["tasks"] == tasks
    assert state["benchmarks"] == benchmarks
    assert state["datasets"] == datasets
    assert state["id_seq"] == id_seq


def test_save_state_overwrites_previous_snapshot(fresh_db):
    fresh_db.save_state([{"id": "TK-1"}], [], [], {"DS": 1000, "BM": 1000, "TK": 1000})
    fresh_db.save_state([{"id": "TK-2"}], [], [], {"DS": 1000, "BM": 1000, "TK": 1001})

    state = fresh_db.load_state()
    assert state["tasks"] == [{"id": "TK-2"}]
    assert state["id_seq"]["TK"] == 1001


def test_load_state_survives_reconnect(tmp_path, monkeypatch):
    """模拟进程重启：关掉旧连接、清空模块级缓存后重新连接同一个库文件，数据应该还在
    ——这是本次改造要解决的核心问题（原来的纯内存实现进程一重启数据就没了）。"""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "restart.db")
    from backend import db as db_mod

    db_mod._conn = None
    try:
        db_mod.save_state([{"id": "TK-1"}], [{"id": "BM-1"}], [{"id": "DS-1"}], {"DS": 1001, "BM": 1001, "TK": 1001})

        db_mod._conn.close()
        db_mod._conn = None  # 下一次 _get_conn() 会重新打开同一个文件，模拟进程重启

        state = db_mod.load_state()
        assert [t["id"] for t in state["tasks"]] == ["TK-1"]
        assert state["id_seq"] == {"DS": 1001, "BM": 1001, "TK": 1001}
    finally:
        if db_mod._conn is not None:
            db_mod._conn.close()
            db_mod._conn = None
