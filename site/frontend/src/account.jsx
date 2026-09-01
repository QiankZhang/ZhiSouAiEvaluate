import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { toast } from "./toast.js";
import { Button, ConfirmDialog, Field, Icon, Modal, Table } from "./components.jsx";

/* ---------------- 登录页 ---------------- */

export function LoginView({ onLogin }) {
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const me = await api.post("/api/auth/login", { account: account.trim(), password });
      onLogin(me);
    } catch (err) {
      toast.error(err.message || "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <span className="brand-mark">
            <Icon name="chart" size={18} />
          </span>
          智搜评估
        </div>
        <div className="login-sub">策略效果评估平台</div>
        <input
          className="input"
          placeholder="账号"
          autoFocus
          value={account}
          onChange={(e) => setAccount(e.target.value)}
        />
        <input
          className="input"
          type="password"
          placeholder="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="btn btn-primary" disabled={busy || !account.trim() || !password}>
          {busy ? "登录中…" : "登录"}
        </button>
        <p className="login-hint">
          默认账号为姓名的小写拼音，初始密码 <b>12345678</b>，登录后请尽快在「修改密码」中更新。
        </p>
      </form>
    </div>
  );
}

/* ---------------- 顶部：组织标识 + 账号菜单 ---------------- */

export function AccountBar({ me, onChange, navigate }) {
  const [open, setOpen] = useState(false);
  const [pwdOpen, setPwdOpen] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const ref = useRef(null);
  const inOrg = Boolean(me.org);

  useEffect(() => {
    if (!open) return undefined;
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  async function logout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      /* 忽略：即便请求失败也让前端回到登录页 */
    }
    onChange(null);
  }

  async function leave() {
    try {
      await api.post("/api/org/leave");
      toast.success("已退出组织");
      onChange({ ...me, org: null });
      setLeaveOpen(false);
      navigate("/overview");
    } catch (err) {
      toast.error(err.message);
    }
  }

  return (
    <div className="topbar-user" ref={ref}>
      <span className={`org-chip${inOrg ? "" : " org-chip-warn"}`}>
        <Icon name={inOrg ? "target" : "warning"} size={13} />
        {inOrg ? me.org.name : "未加入组织"}
      </span>
      <button className="account-trigger" onClick={() => setOpen((v) => !v)}>
        <span className="avatar">{me.name.slice(0, 1)}</span>
        <span>{me.name}</span>
      </button>

      {open ? (
        <div className="menu-pop" role="menu">
          <div className="account-meta">
            {me.name} · {me.account}
          </div>
          <button className="menu-item" onClick={() => { setOpen(false); setPwdOpen(true); }}>
            <Icon name="edit" size={15} /> 修改密码
          </button>
          {inOrg ? (
            <button className="menu-item" onClick={() => { setOpen(false); navigate("/members"); }}>
              <Icon name="list" size={15} /> 成员管理
            </button>
          ) : null}
          {inOrg ? (
            <button className="menu-item" onClick={() => { setOpen(false); setLeaveOpen(true); }}>
              <Icon name="back" size={15} /> 退出组织
            </button>
          ) : null}
          <button className="menu-item danger" onClick={logout}>
            <Icon name="close" size={15} /> 退出登录
          </button>
        </div>
      ) : null}

      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
      <ConfirmDialog
        open={leaveOpen}
        title="退出组织"
        message="退出后将成为孤立账号，看不到「智搜产品」下的任何数据集、评估基准与任务，需由组织成员重新邀请。确定退出？"
        confirmText="退出组织"
        danger
        onConfirm={leave}
        onCancel={() => setLeaveOpen(false)}
      />
    </div>
  );
}

function ChangePasswordModal({ open, onClose }) {
  const [form, setForm] = useState({ old_password: "", new_password: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setForm({ old_password: "", new_password: "", confirm: "" });
  }, [open]);

  async function submit() {
    if (form.new_password.length < 8 || form.new_password.length > 64) {
      toast.error("新密码长度需为 8-64 位");
      return;
    }
    if (form.new_password !== form.confirm) {
      toast.error("两次输入的新密码不一致");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/auth/change-password", {
        old_password: form.old_password,
        new_password: form.new_password,
      });
      toast.success("密码已修改，其它设备需重新登录");
      onClose();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Modal
      title="修改密码"
      open={open}
      onClose={onClose}
      width={380}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={submit} disabled={busy}>
            {busy ? "提交中…" : "确认修改"}
          </Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field label="原密码" required>
          <input className="input" type="password" value={form.old_password} onChange={set("old_password")} />
        </Field>
        <Field label="新密码" required hint="8-64 位">
          <input className="input" type="password" value={form.new_password} onChange={set("new_password")} />
        </Field>
        <Field label="确认新密码" required>
          <input className="input" type="password" value={form.confirm} onChange={set("confirm")} />
        </Field>
      </div>
    </Modal>
  );
}

/* ---------------- 成员管理 ---------------- */

export function MembersPage({ me }) {
  const [members, setMembers] = useState([]);
  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState(null);

  const load = useCallback(() => {
    api
      .get("/api/org/members")
      .then((data) => setMembers(data.items))
      .catch((err) => toast.error(err.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function resetPassword(account) {
    try {
      await api.post(`/api/org/members/${account}/reset-password`);
      toast.success("密码已重置为 12345678");
      load();
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function remove() {
    try {
      await api.delete(`/api/org/members/${removeTarget.account}`);
      toast.success("已移出组织");
      setRemoveTarget(null);
      load();
    } catch (err) {
      toast.error(err.message);
    }
  }

  const columns = [
    { key: "name", title: "姓名", render: (m) => <span>{m.name}</span> },
    { key: "account", title: "账号", render: (m) => <span>{m.account}</span> },
    {
      key: "pwd_changed",
      title: "密码状态",
      render: (m) => (
        <span className={m.pwd_changed ? "text-tertiary" : "badge badge-warning"}>
          {m.pwd_changed ? "已修改" : "初始密码"}
        </span>
      ),
    },
    { key: "created_at", title: "加入时间", render: (m) => <span>{m.created_at}</span> },
    { key: "created_by", title: "添加人", render: (m) => <span>{m.created_by}</span> },
    {
      key: "ops",
      title: "操作",
      render: (m) => (
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => resetPassword(m.account)}>
            重置密码
          </button>
          {m.account === me.account ? null : (
            <button className="btn btn-ghost btn-sm" onClick={() => setRemoveTarget(m)}>
              移出组织
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="content">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ margin: 0 }}>成员管理</h2>
          <p className="text-tertiary" style={{ margin: "4px 0 0" }}>
            智搜产品 · {members.length} 名成员 · 组织内成员均可添加或移出成员
          </p>
        </div>
        <Button variant="primary" icon="plus" onClick={() => setAddOpen(true)}>
          添加成员
        </Button>
      </div>

      <Table columns={columns} data={members} rowKey="account" />

      <AddMemberModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onDone={() => {
          setAddOpen(false);
          load();
        }}
      />
      <ConfirmDialog
        open={Boolean(removeTarget)}
        title="移出组织"
        message={
          removeTarget
            ? `将 ${removeTarget.name}（${removeTarget.account}）移出智搜产品？该账号会变为孤立账号。`
            : ""
        }
        confirmText="移出"
        danger
        onConfirm={remove}
        onCancel={() => setRemoveTarget(null)}
      />
    </div>
  );
}

function AddMemberModal({ open, onClose, onDone }) {
  const [form, setForm] = useState({ name: "", account: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setForm({ name: "", account: "" });
  }, [open]);

  async function submit() {
    const account = form.account.trim().toLowerCase();
    if (!/^[a-z0-9_]{2,32}$/.test(account)) {
      toast.error("账号需为 2-32 位小写字母、数字或下划线");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post("/api/org/members", { name: form.name.trim(), account });
      toast.success(res.joined ? "已邀请该账号加入组织" : `已新增成员，初始密码 12345678`);
      onDone();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="添加成员"
      open={open}
      onClose={onClose}
      width={400}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={submit} disabled={busy}>
            {busy ? "提交中…" : "确定"}
          </Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field label="姓名" required hint="若账号已存在（孤立账号），将直接邀请其加入，可不填姓名">
          <input
            className="input"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </Field>
        <Field label="账号" required hint="小写字母 / 数字 / 下划线，建议用姓名拼音；初始密码 12345678">
          <input
            className="input"
            value={form.account}
            onChange={(e) => setForm((f) => ({ ...f, account: e.target.value }))}
          />
        </Field>
      </div>
    </Modal>
  );
}
