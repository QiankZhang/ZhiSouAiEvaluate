"""组织与账号登录系统：单默认组织「智搜产品」+ 账号密码登录 + 服务端会话。

设计见仓库根 `组织与账号系统设计.md`。只用标准库，状态随 db.py 快照一起持久化。

可见性规则（本期只有一个组织，故不做逐条记录的 org_id 归属）：
- 有会话且在组织内 → 可访问全部业务接口；
- 有会话但已退出组织（孤立账号）→ 只能登录 / 改密 / 等待被邀请；
- 无会话 → 401。
入口鉴权在 main.py 的中间件里统一做，不逐个路由加依赖。
"""

import contextvars
import hashlib
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

DEFAULT_ORG = {"id": "ORG-1", "name": "智搜产品"}
INITIAL_PASSWORD = "12345678"
COOKIE_NAME = "zs_session"
SESSION_TTL_SEC = 14 * 24 * 3600
_ACCOUNT_RE = re.compile(r"^[a-z0-9_]{2,32}$")

# 首批默认账号：姓名 -> 小写拼音账号，统一初始密码 INITIAL_PASSWORD，全部加入默认组织
_SEED = [
    ("王烁", "wangshuo"),
    ("王婧雅", "wangjingya"),
    ("杨声璐", "yangshenglu"),
    ("荆欣芮", "jingxinrui"),
    ("高帅", "gaoshuai"),
    ("黄巍", "huangwei"),
    ("韩旭", "hanxu"),
    ("陈斯睿", "chensirui"),
    ("赵云鹏", "zhaoyunpeng"),
    ("刘思怡", "liusiyi"),
    ("张乾坤", "zhangqiankun"),
]

# account 同时用作主键（全局唯一、创建后不可改）
_accounts: list[dict] = []
_sessions: dict[str, dict] = {}  # token -> {"account": str, "last_seen": float}
_current: contextvars.ContextVar = contextvars.ContextVar("current_account", default=None)

router = APIRouter(prefix="/api")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


# ---- 密码哈希（pbkdf2-sha256，标准库）----

def _hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2_sha256$200000${salt}${digest}"


def _verify(password: str, stored: str) -> bool:
    try:
        _, _, salt, _ = stored.split("$")
    except ValueError:
        return False
    return secrets.compare_digest(_hash(password, salt), stored)


# ---- 持久化桥接（main.py 调用）----

def restore(accounts: list, sessions: dict) -> None:
    _accounts.clear()
    _accounts.extend(accounts or [])
    _sessions.clear()
    _sessions.update(sessions or {})


def snapshot() -> tuple[list, dict]:
    return _accounts, _sessions


def seed_and_migrate(*collections: list) -> None:
    """首次启动写入种子账号；历史业务数据的创建人「孙颖」统一改归属到「张乾坤」。"""
    if not _accounts:
        for name, account in _SEED:
            _accounts.append(
                {
                    "account": account,
                    "name": name,
                    "password_hash": _hash(INITIAL_PASSWORD),
                    "org_id": DEFAULT_ORG["id"],
                    "pwd_changed": False,
                    "created_at": _now(),
                    "created_by": "系统",
                }
            )
    for coll in collections:
        for record in coll:
            if record.get("created_by") == "孙颖":
                record["created_by"] = "张乾坤"


# ---- 会话 ----

def _find(account: str) -> dict | None:
    return next((a for a in _accounts if a["account"] == account), None)


def _prune_sessions() -> None:
    cutoff = time.time() - SESSION_TTL_SEC
    for token in [t for t, s in _sessions.items() if s["last_seen"] < cutoff]:
        _sessions.pop(token, None)


def _drop_sessions(account: str, keep: str | None = None) -> None:
    for token in [t for t, s in _sessions.items() if s["account"] == account and t != keep]:
        _sessions.pop(token, None)


def resolve(request: Request) -> dict | None:
    """按 Cookie 里的会话 token 返回当前账号，顺带刷新滑动过期。"""
    token = request.cookies.get(COOKIE_NAME)
    session = _sessions.get(token or "")
    if not session:
        return None
    if time.time() - session["last_seen"] > SESSION_TTL_SEC:
        _sessions.pop(token, None)
        return None
    session["last_seen"] = time.time()
    return _find(session["account"])


def current() -> dict | None:
    return _current.get()


def creator_name() -> str:
    """业务对象的创建人展示名，由中间件在请求上下文里注入。"""
    account = _current.get()
    return account["name"] if account else "系统"


def bind(account: dict):
    return _current.set(account)


def unbind(token) -> None:
    _current.reset(token)


# ---- 视图 ----

def _me(account: dict) -> dict:
    return {
        "account": account["account"],
        "name": account["name"],
        "org": DEFAULT_ORG if account.get("org_id") else None,
        "pwd_changed": account.get("pwd_changed", True),
    }


def _member_view(account: dict) -> dict:
    return {
        "account": account["account"],
        "name": account["name"],
        "pwd_changed": account.get("pwd_changed", True),
        "created_at": account.get("created_at", ""),
        "created_by": account.get("created_by", ""),
    }


def _require_org() -> dict:
    account = _current.get()
    if not account or not account.get("org_id"):
        raise HTTPException(status_code=403, detail="你尚未加入任何组织")
    return account


# ---- 认证接口 ----

class LoginBody(BaseModel):
    account: str
    password: str


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


class MemberBody(BaseModel):
    name: str = ""
    account: str


@router.post("/auth/login")
def login(body: LoginBody, response: Response) -> dict:
    account = _find(body.account.strip().lower())
    if not account or not _verify(body.password, account["password_hash"]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    _prune_sessions()
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"account": account["account"], "last_seen": time.time()}
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_TTL_SEC, httponly=True, samesite="lax", path="/"
    )
    return _me(account)


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    _sessions.pop(request.cookies.get(COOKIE_NAME) or "", None)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me() -> dict:
    return _me(_current.get())


@router.post("/auth/change-password")
def change_password(body: PasswordBody, request: Request) -> dict:
    account = _current.get()
    if not _verify(body.old_password, account["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if not 8 <= len(body.new_password) <= 64:
        raise HTTPException(status_code=400, detail="新密码长度需为 8-64 位")
    account["password_hash"] = _hash(body.new_password)
    account["pwd_changed"] = True
    _drop_sessions(account["account"], keep=request.cookies.get(COOKIE_NAME))
    return {"ok": True}


# ---- 组织接口 ----

@router.get("/org/members")
def list_members() -> dict:
    _require_org()
    members = [a for a in _accounts if a.get("org_id") == DEFAULT_ORG["id"]]
    members.sort(key=lambda a: a.get("created_at", ""))
    return {"org": DEFAULT_ORG, "items": [_member_view(a) for a in members]}


@router.post("/org/members")
def add_member(body: MemberBody) -> dict:
    _require_org()
    account = body.account.strip().lower()
    if not _ACCOUNT_RE.match(account):
        raise HTTPException(status_code=400, detail="账号需为 2-32 位小写字母、数字或下划线")
    existing = _find(account)
    if existing:
        if existing.get("org_id") == DEFAULT_ORG["id"]:
            raise HTTPException(status_code=409, detail="该账号已在组织中")
        if existing.get("org_id"):
            raise HTTPException(status_code=409, detail="该账号已属于其它组织")
        existing["org_id"] = DEFAULT_ORG["id"]
        return {"joined": True, **_member_view(existing)}
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写姓名")
    account_obj = {
        "account": account,
        "name": name,
        "password_hash": _hash(INITIAL_PASSWORD),
        "org_id": DEFAULT_ORG["id"],
        "pwd_changed": False,
        "created_at": _now(),
        "created_by": creator_name(),
    }
    _accounts.append(account_obj)
    return {"joined": False, **_member_view(account_obj)}


@router.post("/org/members/{account}/reset-password")
def reset_member_password(account: str) -> dict:
    _require_org()
    target = _find(account)
    if not target or target.get("org_id") != DEFAULT_ORG["id"]:
        raise HTTPException(status_code=404, detail="成员不存在")
    target["password_hash"] = _hash(INITIAL_PASSWORD)
    target["pwd_changed"] = False
    _drop_sessions(account)
    return {"ok": True}


@router.delete("/org/members/{account}")
def remove_member(account: str) -> dict:
    me_account = _require_org()
    if account == me_account["account"]:
        raise HTTPException(status_code=400, detail="不能移出自己，请使用「退出组织」")
    target = _find(account)
    if not target or target.get("org_id") != DEFAULT_ORG["id"]:
        raise HTTPException(status_code=404, detail="成员不存在")
    target["org_id"] = None
    _drop_sessions(account)
    return {"ok": True}


@router.post("/org/leave")
def leave_org() -> dict:
    account = _require_org()
    account["org_id"] = None
    return {"ok": True}
