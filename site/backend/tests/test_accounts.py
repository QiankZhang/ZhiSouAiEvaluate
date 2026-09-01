"""组织与账号：核心逻辑单测（不起 HTTP，直接调 accounts 模块）。"""

import pytest
from fastapi import HTTPException

from backend import accounts


@pytest.fixture(autouse=True)
def clean_state():
    accounts.restore([], {})
    accounts._current.set(None)
    yield
    accounts.restore([], {})


def _login_as(account: str):
    accounts._current.set(accounts._find(account))


def test_password_hash_roundtrip():
    stored = accounts._hash("12345678")
    assert accounts._verify("12345678", stored)
    assert not accounts._verify("wrong", stored)


def test_seed_creates_batch_and_migrates_owner():
    datasets = [{"id": "DS-1", "created_by": "孙颖"}, {"id": "DS-2", "created_by": "王烁"}]
    accounts.seed_and_migrate(datasets)

    seeded = {a["account"]: a for a in accounts._accounts}
    assert len(seeded) == 11
    assert seeded["zhangqiankun"]["name"] == "张乾坤"
    assert all(a["org_id"] == accounts.DEFAULT_ORG["id"] for a in accounts._accounts)
    assert all(accounts._verify("12345678", a["password_hash"]) for a in accounts._accounts)
    assert datasets[0]["created_by"] == "张乾坤"
    assert datasets[1]["created_by"] == "王烁"


def test_seed_is_idempotent():
    accounts.seed_and_migrate()
    accounts._accounts[0]["password_hash"] = accounts._hash("changed-pw")
    accounts.seed_and_migrate()
    assert accounts._verify("changed-pw", accounts._accounts[0]["password_hash"])


def test_change_password_requires_correct_old(monkeypatch):
    accounts.seed_and_migrate()
    _login_as("wangshuo")
    req = type("R", (), {"cookies": {}})()

    with pytest.raises(HTTPException):
        accounts.change_password(accounts.PasswordBody(old_password="nope", new_password="abcd1234"), req)

    accounts.change_password(accounts.PasswordBody(old_password="12345678", new_password="abcd1234"), req)
    assert accounts._verify("abcd1234", accounts._find("wangshuo")["password_hash"])


def test_add_member_new_invite_and_duplicate():
    accounts.seed_and_migrate()
    _login_as("wangshuo")

    created = accounts.add_member(accounts.MemberBody(name="新人", account="xinren"))
    assert created["joined"] is False
    assert accounts._find("xinren")["org_id"] == accounts.DEFAULT_ORG["id"]

    accounts._find("xinren")["org_id"] = None  # 模拟该账号退出组织
    invited = accounts.add_member(accounts.MemberBody(account="xinren"))
    assert invited["joined"] is True

    with pytest.raises(HTTPException):
        accounts.add_member(accounts.MemberBody(account="xinren"))


def test_leave_and_reinvite_flow():
    accounts.seed_and_migrate()
    _login_as("hanxu")
    accounts.leave_org()
    assert accounts._find("hanxu")["org_id"] is None

    _login_as("wangshuo")
    with pytest.raises(HTTPException):
        accounts.remove_member("wangshuo")  # 不能移出自己

    res = accounts.add_member(accounts.MemberBody(account="hanxu"))
    assert res["joined"] is True
