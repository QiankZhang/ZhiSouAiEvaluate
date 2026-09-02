import React, { useEffect, useMemo, useState } from "react";
import { api, downloadFile, ANNOTATE_TYPE_LABELS, MANUAL_STATUS_LABELS } from "./api.js";
import { toast } from "./toast.js";
import { Markdown } from "./markdown.jsx";
import {
  Badge,
  Button,
  ConfirmDialog,
  DismissibleBanner,
  Dropzone,
  EmptyState,
  Field,
  Icon,
  Menu,
  Modal,
  Progress,
  StatCard,
} from "./components.jsx";

const TYPE_OPTIONS = [
  { value: "GSB", icon: "⚖", label: "GSB 标注", desc: "左右对比基线与实验，判定 G / S / B。字段：query / content / baseline" },
  { value: "MULTI_DIM", icon: "📊", label: "多维度评估标注", desc: "单条内容按维度打分。字段：query / content" },
  { value: "CONVERSATION", icon: "💬", label: "多轮对话标注", desc: "按 session 组织为一段对话整体打分。字段：session_id / turn / role / content" },
  { value: "INTENT", icon: "🎯", label: "意图准确率标注", desc: "判断系统识别的意图是否正确。字段：query / predicted_intent（可选 expected_intent）" },
];

const INTENT_JUDGE_OPTIONS = [
  ["correct", "g", "✓ 识别正确"],
  ["partial", "s", "~ 部分正确"],
  ["wrong", "b", "✗ 识别错误"],
];

// 全平台统一默认维度：相关性 / 全面性 / 准确性 / 可读性 / 时效性，各 20%
const RECOMMENDED_DIMS = [
  { key: "relevance", name: "相关性", weight: 20 },
  { key: "comprehensiveness", name: "全面性", weight: 20 },
  { key: "accuracy", name: "准确性", weight: 20 },
  { key: "readability", name: "可读性", weight: 20 },
  { key: "timeliness", name: "时效性", weight: 20 },
];

// 报告生成默认走 DeepSeek V4 Flash（与全站裁判员模型默认一致）
const DEFAULT_REPORT_MODEL = "deepseek-v4-flash";

function TypeBadge({ type }) {
  return <Badge tone="outline">{ANNOTATE_TYPE_LABELS[type] || type}</Badge>;
}

function unitDone(unit, type) {
  if (unit.skipped) return true;
  if (type === "GSB") return ["G", "S", "B"].includes(unit.judgment);
  if (type === "INTENT") return ["correct", "partial", "wrong"].includes(unit.judgment);
  return unit.total != null;
}

function unitTitle(unit) {
  return unit.query || unit.title || `会话 ${unit.session_id || unit.key}`;
}

/* ==================== 列表页 ==================== */

export function ManualEvalPage({ navigate }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState("");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reportTemplates, setReportTemplates] = useState([]);
  const [models, setModels] = useState([]);

  function reload() {
    setErr("");
    api
      .get("/api/manual-tasks")
      .then((r) => setItems(r.items))
      .catch((e) => setErr(e.message));
  }

  useEffect(() => {
    reload();
    api.get("/api/report-templates").then((r) => setReportTemplates(r.items || [])).catch(() => {});
    api.get("/api/models").then((r) => setModels(r.items || [])).catch(() => {});
  }, []);

  const filtered = useMemo(() => {
    let list = items || [];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((m) => m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q));
    }
    if (type) list = list.filter((m) => m.annotate_type === type);
    if (status) list = list.filter((m) => m.status === status);
    return list;
  }, [items, search, type, status]);

  async function handleDelete() {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await api.delete(`/api/manual-tasks/${confirmDelete.id}`);
      toast.success("已删除");
      reload();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="page-title">人工评估中心</div>
          <div className="page-desc">人工标注 · 逐条判读</div>
        </div>
        <Button variant="primary" icon="plus" onClick={() => setCreateOpen(true)}>
          创建标注任务
        </Button>
      </div>

      <DismissibleBanner storageKey="manual-guide-banner" icon="target">
        四步：<strong>上传数据</strong> → <strong>逐条标注</strong> → <strong>自动汇总</strong> → <strong>AI 报告</strong>。
      </DismissibleBanner>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar" style={{ padding: "16px 20px" }}>
          <div className="search-input">
            <Icon name="search" size={16} />
            <input className="input" placeholder="搜索任务名 / ID" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="select" style={{ width: 150 }} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">全部标注类型</option>
            {Object.entries(ANNOTATE_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 120 }} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">全部状态</option>
            {Object.entries(MANUAL_STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <span className="spacer" />
          <span className="text-tertiary" style={{ fontSize: 12 }}>
            共 {filtered.length} 个任务
          </span>
        </div>

        {err ? (
          <EmptyState title="加载失败" hint={err} />
        ) : !items ? (
          <div className="loading">正在加载…</div>
        ) : filtered.length === 0 ? (
          <EmptyState title="还没有标注任务" hint="点右上角「创建标注任务」，上传数据开始人工标注" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>任务ID</th>
                  <th>名称</th>
                  <th>标注类型</th>
                  <th>进度</th>
                  <th>状态</th>
                  <th>创建人</th>
                  <th>创建时间</th>
                  <th style={{ width: 200 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => {
                  const pct = m.progress_total ? (m.progress_done / m.progress_total) * 100 : 0;
                  return (
                    <tr key={m.id} className="clickable" onClick={() => navigate(`/manual-eval/${m.id}`)}>
                      <td>
                        <span className="mono">{m.id}</span>
                      </td>
                      <td>
                        <span className="cell-primary">{m.name}</span>
                      </td>
                      <td>
                        <TypeBadge type={m.annotate_type} />
                      </td>
                      <td style={{ minWidth: 150 }}>
                        <div className="inline" style={{ gap: 8 }}>
                          <Progress value={pct} />
                          <span className="cell-tertiary" style={{ whiteSpace: "nowrap" }}>
                            {m.progress_done}/{m.progress_total}
                          </span>
                        </div>
                      </td>
                      <td>
                        <Badge tone={m.status === "COMPLETED" ? "success" : "brand"} dot>
                          {MANUAL_STATUS_LABELS[m.status] || m.status}
                        </Badge>
                      </td>
                      <td>{m.created_by}</td>
                      <td>
                        <span className="cell-secondary">{m.created_at}</span>
                      </td>
                      <td>
                        <div className="inline" onClick={(e) => e.stopPropagation()}>
                          {m.status === "COMPLETED" ? (
                            <Button size="sm" variant="primary" onClick={() => navigate(`/manual-eval/${m.id}/summary`)}>
                              查看汇总
                            </Button>
                          ) : (
                            <Button size="sm" variant="primary" onClick={() => navigate(`/manual-eval/${m.id}`)}>
                              继续标注
                            </Button>
                          )}
                          <Menu
                            items={[
                              { label: "去标注", icon: "edit", onClick: () => navigate(`/manual-eval/${m.id}`) },
                              m.status === "COMPLETED" && {
                                label: "查看汇总",
                                icon: "chart",
                                onClick: () => navigate(`/manual-eval/${m.id}/summary`),
                              },
                              { label: "删除任务", icon: "trash", danger: true, onClick: () => setConfirmDelete(m) },
                            ]}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <CreateManualTaskModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        reportTemplates={reportTemplates}
        models={models}
        onCreated={(mt) => {
          setCreateOpen(false);
          navigate(`/manual-eval/${mt.id}`);
        }}
      />

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="删除标注任务"
        message={confirmDelete ? `确定删除「${confirmDelete.name}」吗？标注数据将一并删除，不可撤销。` : ""}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

/* ==================== 创建标注任务 ==================== */

function CreateManualTaskModal({ open, onClose, onCreated, reportTemplates, models }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("GSB");
  const [swapSides, setSwapSides] = useState(false);
  const [dims, setDims] = useState(RECOMMENDED_DIMS);
  const [intentLabels, setIntentLabels] = useState("");
  const [reportTemplateId, setReportTemplateId] = useState("");
  const [reportModel, setReportModel] = useState("");
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState([]);

  const liveModels = (models || []).filter((m) => m.live);

  useEffect(() => {
    if (!open) return;
    setName("");
    setDescription("");
    setType("GSB");
    setSwapSides(false);
    setDims(RECOMMENDED_DIMS);
    setIntentLabels("");
    setReportTemplateId(reportTemplates[0]?.id || "");
    setReportModel(
      liveModels.some((m) => m.id === DEFAULT_REPORT_MODEL) ? DEFAULT_REPORT_MODEL : liveModels[0]?.id || ""
    );
    setFile(null);
    setSaving(false);
    setMessage("");
    setErrors([]);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const needsDims = type === "MULTI_DIM" || type === "CONVERSATION";
  const totalWeight = dims.reduce((s, d) => s + (Number(d.weight) || 0), 0);
  const accept =
    type === "CONVERSATION" ? ".jsonl,.json,.csv" : type === "INTENT" ? ".csv,.json,.jsonl" : ".csv,.xlsx";

  function setDim(i, patch) {
    setDims((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  }

  function downloadTemplate() {
    downloadFile(`/api/manual-tasks/template?annotate_type=${type}`, "标注模板.csv").catch((e) => toast.error(e.message));
  }

  async function submit() {
    if (!name.trim()) return setMessage("请填写任务名称");
    if (!file) return setMessage("请上传数据文件");
    if (needsDims) {
      if (dims.some((d) => !d.name.trim())) return setMessage("请填写所有维度名称");
      if (totalWeight !== 100) return setMessage(`维度权重合计需为 100%（当前 ${totalWeight}%）`);
    }
    if (!reportTemplateId) return setMessage("请选择评估报告模板");
    setSaving(true);
    setMessage("");
    setErrors([]);
    try {
      const fd = new FormData();
      fd.append("name", name.trim());
      fd.append("description", description);
      fd.append("annotate_type", type);
      fd.append("dimensions", JSON.stringify(needsDims ? dims : []));
      fd.append("gsb_swap_sides", String(swapSides));
      fd.append("intent_labels", type === "INTENT" ? intentLabels : "");
      fd.append("report_template_id", reportTemplateId);
      fd.append("report_model", reportModel);
      fd.append("file", file);
      const created = await api.upload("/api/manual-tasks/upload", fd);
      toast.success("标注任务已创建");
      onCreated(created);
    } catch (e) {
      if (e.detail && typeof e.detail === "object" && e.detail.errors) {
        setErrors(e.detail.errors);
        setMessage(e.detail.message || e.message);
      } else {
        setMessage(e.message);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title="创建标注任务"
      open={open}
      onClose={onClose}
      width={680}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={submit} disabled={saving}>
            {saving ? "创建中…" : "创建并开始标注"}
          </Button>
        </>
      }
    >
      <Field label="任务名称" required>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={50} placeholder="如：9月改版-通用查询人工验收" />
      </Field>
      <Field label="任务描述" hint={`非必填 · ${description.length}/200`}>
        <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} />
      </Field>

      <Field label="标注类型" required hint="创建后不可修改">
        <div className="option-cards">
          {TYPE_OPTIONS.map((o) => (
            <div key={o.value} className={`option-card${type === o.value ? " selected" : ""}`} onClick={() => setType(o.value)}>
              <div className="option-card-title">
                {o.icon} {o.label}
              </div>
              <div className="option-card-desc">{o.desc}</div>
            </div>
          ))}
        </div>
      </Field>

      {type === "GSB" ? (
        <Field label="左右布局" hint="决定标注工作台里两栏内容的位置">
          <select className="select" value={String(swapSides)} onChange={(e) => setSwapSides(e.target.value === "true")}>
            <option value="false">左：基线（baseline） ／ 右：实验（content）</option>
            <option value="true">左：实验（content） ／ 右：基线（baseline）</option>
          </select>
        </Field>
      ) : null}

      {type === "INTENT" ? (
        <Field
          label="意图类别清单"
          hint="选填 · 每行一个或用逗号分隔。填写后标注「正确意图」时可从下拉选择，留空则手动输入"
        >
          <textarea
            className="textarea"
            value={intentLabels}
            onChange={(e) => setIntentLabels(e.target.value)}
            placeholder={"天气查询\n物流查询\n售后咨询\n闲聊"}
            rows={4}
          />
        </Field>
      ) : null}

      <Field
        label="数据文件"
        required
        hint={
          type === "CONVERSATION"
            ? "JSONL / JSON / CSV，按 session_id 分组"
            : type === "INTENT"
              ? "CSV / JSON / JSONL，含 query、predicted_intent 列"
              : "CSV / XLSX"
        }
      >
        <div className="inline" style={{ gap: 8, marginBottom: 8 }}>
          <Button size="sm" icon="download" onClick={downloadTemplate}>
            下载 {ANNOTATE_TYPE_LABELS[type]} 模板
          </Button>
        </div>
        <Dropzone accept={accept} onFile={setFile} hint={file ? "" : "点击选择或拖拽文件"} />
      </Field>

      {needsDims ? (
        <Field label="评分维度" required hint={`每个维度 1–5 分，权重合计需为 100%（当前 ${totalWeight}%）`}>
          <div>
            {dims.map((d, i) => (
              <div key={i} className="inline" style={{ gap: 8, marginBottom: 6 }}>
                <input
                  className="input"
                  style={{ flex: 1 }}
                  placeholder="维度名"
                  value={d.name}
                  onChange={(e) => setDim(i, { name: e.target.value })}
                />
                <input
                  className="input"
                  style={{ width: 90 }}
                  type="number"
                  min={0}
                  max={100}
                  value={d.weight}
                  onChange={(e) => setDim(i, { weight: Number(e.target.value) || 0 })}
                />
                <span className="text-tertiary">%</span>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => setDims((prev) => prev.filter((_, idx) => idx !== i))}
                  disabled={dims.length <= 1}
                >
                  <Icon name="trash" size={15} />
                </button>
              </div>
            ))}
            <div className="inline" style={{ gap: 8 }}>
              <Button size="sm" onClick={() => setDims((prev) => [...prev, { key: `dim_${prev.length + 1}`, name: "", weight: 0 }])}>
                + 维度
              </Button>
              <Button size="sm" onClick={() => setDims(RECOMMENDED_DIMS)}>
                恢复默认维度
              </Button>
            </div>
          </div>
        </Field>
      ) : null}

      <Field label="评估报告模板" required hint="标注完成后由 AI 依据此模板撰写报告">
        <select className="select" value={reportTemplateId} onChange={(e) => setReportTemplateId(e.target.value)}>
          <option value="">请选择…</option>
          {reportTemplates.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="报告生成模型">
        <select className="select" value={reportModel} onChange={(e) => setReportModel(e.target.value)}>
          {liveModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </Field>

      {errors.length ? (
        <div className="error-list">
          {errors.map((e, i) => (
            <div className="error-list-item" key={i}>
              第 {e.line} 行：{e.message}
            </div>
          ))}
        </div>
      ) : null}
      {message ? <div style={{ color: "var(--warning)" }}>{message}</div> : null}
    </Modal>
  );
}

/* ==================== 标注工作台 ==================== */

export function ManualAnnotatePage({ id, navigate }) {
  const [task, setTask] = useState(null);
  const [err, setErr] = useState("");
  const [currentKey, setCurrentKey] = useState(null);
  const [filter, setFilter] = useState("all");
  const [note, setNote] = useState("");

  function load() {
    setErr("");
    api
      .get(`/api/manual-tasks/${id}`)
      .then((t) => {
        setTask(t);
        // 切换任务后旧的 currentKey 可能不属于新任务的任何单元，回落到第一条
        setCurrentKey((k) => (t.units.some((u) => u.key === k) ? k : t.units[0]?.key || null));
      })
      .catch((e) => setErr(e.message));
  }

  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = task?.units.find((u) => u.key === currentKey) || null;

  useEffect(() => {
    setNote(current?.note || "");
  }, [currentKey, current?.note]);

  if (err) return <div className="content"><EmptyState title="加载失败" hint={err} /></div>;
  if (!task) return <div className="content"><div className="loading">正在加载…</div></div>;

  const type = task.annotate_type;
  const pct = task.progress_total ? (task.progress_done / task.progress_total) * 100 : 0;

  const visibleUnits = task.units.filter((u) => {
    if (filter === "todo") return !unitDone(u, type);
    if (filter === "done") return unitDone(u, type) && !u.skipped;
    if (filter === "skipped") return u.skipped;
    return true;
  });

  async function save(patch, { advance = false } = {}) {
    const wasDone = current ? unitDone(current, type) : false;
    try {
      const updated = await api.put(`/api/manual-tasks/${id}/annotate`, { unit_key: currentKey, ...patch });
      setTask(updated);
      // 仅当「本条从未完成 → 现在完成」时才自动跳到下一条未标注项。
      // 多维度/会话需所有维度都打分才算完成，避免打一个维度就跳走。
      const nowUnit = updated.units.find((u) => u.key === currentKey);
      const nowDone = nowUnit ? unitDone(nowUnit, type) : false;
      if (advance && !wasDone && nowDone) {
        const next = updated.units.find((u) => !unitDone(u, type) && u.key !== currentKey);
        if (next) setCurrentKey(next.key);
      }
    } catch (e) {
      toast.error(e.message);
    }
  }

  function saveNote() {
    if ((current?.note || "") !== note) save({ note });
  }

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate("/manual-eval")}>
        <Icon name="back" size={16} />
        返回列表
      </button>

      <div className="page-head">
        <div>
          <div className="page-title">{task.name}</div>
          <div className="page-desc">
            <span className="mono">{task.id}</span> · <TypeBadge type={type} /> · 已标 {task.progress_done} / 共 {task.progress_total}
          </div>
        </div>
        <Button
          variant={task.status === "COMPLETED" ? "primary" : "secondary"}
          onClick={() => navigate(`/manual-eval/${id}/summary`)}
        >
          {task.status === "COMPLETED" ? "查看汇总与报告" : "查看初步汇总"}
        </Button>
      </div>

      <Progress value={pct} />

      <div className="annotate-shell">
        <aside className="unit-list">
          <div className="unit-list-filter">
            {[
              ["all", "全部"],
              ["todo", "未标注"],
              ["done", "已标注"],
              ["skipped", "已跳过"],
            ].map(([k, label]) => (
              <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>
                {label}
              </button>
            ))}
          </div>
          <div className="unit-list-scroll">
            {visibleUnits.map((u, i) => (
              <button
                key={u.key}
                className={`unit-item${u.key === currentKey ? " active" : ""}`}
                onClick={() => setCurrentKey(u.key)}
              >
                <span className={`unit-dot${u.skipped ? " skipped" : unitDone(u, type) ? " done" : ""}`} />
                <span className="unit-index">{u.index || i + 1}</span>
                <span className="unit-text">{unitTitle(u)}</span>
              </button>
            ))}
          </div>
        </aside>

        <div className="annotate-main">
          {!current ? (
            <EmptyState title="没有可标注的单元" />
          ) : (
            <>
              {type === "GSB" ? (
                <GsbPanel unit={current} swap={task.gsb_swap_sides} onJudge={(j) => save({ judgment: j }, { advance: true })} />
              ) : type === "CONVERSATION" ? (
                <ConversationPanel unit={current} />
              ) : type === "INTENT" ? (
                <IntentPanel
                  unit={current}
                  labels={task.intent_labels || []}
                  onJudge={(j) => save({ judgment: j }, { advance: j === "correct" })}
                  onCorrect={(v) => save({ corrected_intent: v })}
                />
              ) : (
                <MultiContentPanel unit={current} />
              )}

              {type !== "GSB" && type !== "INTENT" ? (
                <DimScoreEditor
                  dimensions={task.dimensions}
                  unit={current}
                  onScore={(key, n) => save({ dim_scores: { [key]: n } }, { advance: true })}
                  onOverride={(v) => save({ overridden_total: v })}
                />
              ) : null}

              <div className="annotate-note">
                <Field label="备注">
                  <textarea
                    className="textarea"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    onBlur={saveNote}
                    placeholder="记录判断依据、问题点（可选）"
                    maxLength={1000}
                  />
                </Field>
                <div className="inline" style={{ gap: 8 }}>
                  <Button
                    size="sm"
                    variant={current.skipped ? "primary" : "secondary"}
                    onClick={() => save({ skipped: !current.skipped }, { advance: !current.skipped })}
                  >
                    {current.skipped ? "取消跳过" : "跳过 / 无法判断"}
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function GsbPanel({ unit, swap, onJudge }) {
  const left = swap ? { head: "实验（content）", body: unit.content } : { head: "基线（baseline）", body: unit.baseline };
  const right = swap ? { head: "基线（baseline）", body: unit.baseline } : { head: "实验（content）", body: unit.content };
  return (
    <>
      <div className="annotate-query">{unit.query}</div>
      <div className="gsb-split">
        {[left, right].map((c, i) => (
          <div className="gsb-col" key={i}>
            <div className="gsb-col-head">{c.head}</div>
            <div className="gsb-col-body">
              <Markdown source={c.body || "（空）"} />
            </div>
          </div>
        ))}
      </div>
      <div className="annotate-actions">
        {[
          ["G", "g", "G · 实验更好"],
          ["S", "s", "S · 持平"],
          ["B", "b", "B · 实验更差"],
        ].map(([val, cls, label]) => (
          <button key={val} className={`gsb-btn ${cls}${unit.judgment === val ? " active" : ""}`} onClick={() => onJudge(val)}>
            {label}
          </button>
        ))}
      </div>
    </>
  );
}

function MultiContentPanel({ unit }) {
  return (
    <>
      <div className="annotate-query">{unit.query}</div>
      <div className="gsb-col-body" style={{ border: "1px solid var(--border-light)", borderRadius: "var(--radius-md)", maxHeight: "46vh" }}>
        <Markdown source={unit.content || "（空）"} />
      </div>
    </>
  );
}

function ConversationPanel({ unit }) {
  return (
    <>
      <div className="annotate-query">
        {unit.title || `会话 ${unit.session_id}`} · {unit.turns.length} 轮
      </div>
      <div className="chat-thread">
        {unit.turns.map((t, i) => (
          <div key={i} className={`chat-msg ${t.role === "user" ? "user" : "assistant"}`}>
            <div className="chat-role">{t.role === "user" ? "用户" : "模型"}</div>
            <Markdown source={t.content} />
          </div>
        ))}
      </div>
    </>
  );
}

function IntentPanel({ unit, labels, onJudge, onCorrect }) {
  const predicted = unit.predicted_intent || "（空）";
  const expected = (unit.expected_intent || "").trim();
  const match = expected && expected.toLowerCase() === (unit.predicted_intent || "").trim().toLowerCase();
  const needCorrect = unit.judgment === "wrong" || unit.judgment === "partial";
  return (
    <>
      <div className="annotate-query">{unit.query}</div>
      <div className="intent-facts">
        <div className="intent-fact">
          <span className="intent-fact-label">系统识别意图</span>
          <span className="intent-chip predicted">{predicted}</span>
        </div>
        {expected ? (
          <div className="intent-fact">
            <span className="intent-fact-label">期望意图（金标准）</span>
            <span className="intent-chip expected">{expected}</span>
            <span className={`intent-match-hint${match ? "" : " diff"}`}>
              {match ? "与识别一致" : "与识别不一致"}
            </span>
          </div>
        ) : null}
        {unit.scene ? (
          <div className="intent-fact">
            <span className="intent-fact-label">场景</span>
            <span className="text-secondary">{unit.scene}</span>
          </div>
        ) : null}
      </div>

      <div className="annotate-actions">
        {INTENT_JUDGE_OPTIONS.map(([val, cls, label]) => (
          <button
            key={val}
            className={`gsb-btn ${cls}${unit.judgment === val ? " active" : ""}`}
            onClick={() => onJudge(val)}
          >
            {label}
          </button>
        ))}
      </div>

      {needCorrect ? (
        <div className="intent-correct">
          <Field
            label="正确意图"
            hint={labels.length ? "从意图类别清单中选择" : "填写该 query 实际应归属的意图"}
          >
            {labels.length ? (
              <select className="select" value={unit.corrected_intent || ""} onChange={(e) => onCorrect(e.target.value)}>
                <option value="">请选择…</option>
                {labels.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className="input"
                key={unit.key}
                defaultValue={unit.corrected_intent || ""}
                placeholder="如：售后咨询"
                maxLength={100}
                onBlur={(e) => {
                  const v = e.target.value.trim();
                  if (v !== (unit.corrected_intent || "")) onCorrect(v);
                }}
              />
            )}
          </Field>
        </div>
      ) : null}
    </>
  );
}

function DimScoreEditor({ dimensions, unit, onScore, onOverride }) {
  const scores = unit.dim_scores || {};
  const overridden = unit.overridden_total != null;
  return (
    <div className="dim-score-block">
      {dimensions.map((d) => (
        <div className="dim-score-row" key={d.key}>
          <span className="dim-score-name">{d.name}</span>
          <span className="dim-score-weight">{d.weight}%</span>
          <div className="score-seg">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={scores[d.key] === n ? "active" : ""} onClick={() => onScore(d.key, n)}>
                {n}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="annotate-total">
        <span>总分</span>
        <b>{unit.total != null ? unit.total : "—"}</b>
        <label className="inline" style={{ gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          <input
            type="checkbox"
            checked={overridden}
            onChange={(e) => onOverride(e.target.checked ? unit.total || 3 : -1)}
          />
          手动指定总分
        </label>
        {overridden ? (
          <input
            className="input"
            style={{ width: 90 }}
            type="number"
            step="0.1"
            min="1"
            max="5"
            defaultValue={unit.overridden_total}
            onBlur={(e) => onOverride(Number(e.target.value))}
          />
        ) : null}
      </div>
    </div>
  );
}

/* ==================== 汇总 + AI 报告 ==================== */

export function ManualSummaryPage({ id, navigate }) {
  const [task, setTask] = useState(null);
  const [err, setErr] = useState("");
  const [report, setReport] = useState(null);
  const [generating, setGenerating] = useState(false);

  function load() {
    api
      .get(`/api/manual-tasks/${id}`)
      .then((t) => {
        setTask(t);
        setReport(t.report);
      })
      .catch((e) => setErr(e.message));
  }

  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (report?.status !== "GENERATING") return undefined;
    const timer = setInterval(() => {
      api.get(`/api/manual-tasks/${id}/report`).then((r) => {
        setReport(r);
        if (r.status !== "GENERATING") {
          setGenerating(false);
          clearInterval(timer);
        }
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [report?.status, id]);

  if (err) return <div className="content"><EmptyState title="加载失败" hint={err} /></div>;
  if (!task) return <div className="content"><div className="loading">正在加载…</div></div>;

  const s = task.summary || {};
  const isGSB = s.eval_method === "GSB";
  const isIntent = s.eval_method === "INTENT";
  const completed = task.status === "COMPLETED";

  async function generate() {
    setGenerating(true);
    try {
      await api.post(`/api/manual-tasks/${id}/report`);
      setReport({ status: "GENERATING" });
    } catch (e) {
      toast.error(e.message);
      setGenerating(false);
    }
  }

  const badUnits = (task.units || []).filter((u) => {
    if (u.skipped) return false;
    if (isGSB) return u.judgment === "B";
    if (isIntent) return u.judgment === "wrong";
    return u.total != null && u.total < 3;
  });

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate(`/manual-eval/${id}`)}>
        <Icon name="back" size={16} />
        返回标注
      </button>

      <div className="page-head">
        <div>
          <div className="page-title">{task.name} · 标注汇总</div>
          <div className="page-desc">
            <span className="mono">{task.id}</span> · <TypeBadge type={task.annotate_type} /> ·{" "}
            {completed ? "标注已完成" : `标注中（${task.progress_done}/${task.progress_total}）`}
          </div>
        </div>
        <div className="inline">
          {report?.status === "READY" ? (
            <Button icon="download" onClick={() => downloadFile(`/api/manual-tasks/${id}/report/markdown`, `${task.name}-人工评估报告.md`).catch((e) => toast.error(e.message))}>
              下载报告
            </Button>
          ) : null}
          <Button icon="download" onClick={() => downloadFile(`/api/manual-tasks/${id}/export`, `${task.name}-标注明细.csv`).catch((e) => toast.error(e.message))}>
            导出明细
          </Button>
          <Button variant="primary" icon="chart" onClick={generate} disabled={!completed || generating || report?.status === "GENERATING"}>
            {report?.status === "GENERATING" || generating ? "报告生成中…" : report?.status === "READY" ? "重新生成报告" : "AI 生成评估报告"}
          </Button>
        </div>
      </div>

      {!completed ? (
        <div className="banner">
          <Icon name="target" size={18} />
          <span>标注尚未全部完成，以下为初步汇总；完成后可生成 AI 报告。</span>
        </div>
      ) : null}

      <div className="metric-grid">
        <StatCard label="样本总量" value={s.total ?? task.progress_total} unit="条" />
        <StatCard label="已标注" value={s.scored ?? 0} unit="条" />
        <StatCard label="已跳过" value={s.skipped ?? 0} unit="条" />
        <StatCard label="完成率" value={task.progress_total ? Math.round((task.progress_done / task.progress_total) * 100) : 0} unit="%" />
      </div>

      <section className="card">
        <div className="card-title">{isIntent ? "意图准确率汇总" : "分数汇总"}</div>
        {isIntent ? <IntentSummary s={s} /> : isGSB ? <GsbSummary s={s} /> : <MultiSummary s={s} />}
      </section>

      {badUnits.length ? (
        <section className="card">
          <div className="card-title">
            {isGSB ? "被判 B 的样本" : isIntent ? "识别错误的样本" : "低分样本（总分 < 3）"}（{badUnits.length}）
          </div>
          <div className="bad-list">
            {badUnits.map((u) => (
              <div key={u.key} className="bad-item">
                <div className="cell-primary">{unitTitle(u)}</div>
                {isIntent ? (
                  <div className="cell-secondary">
                    识别为「{u.predicted_intent || "—"}」
                    {u.corrected_intent || u.expected_intent
                      ? ` ／ 应为「${u.corrected_intent || u.expected_intent}」`
                      : ""}
                  </div>
                ) : null}
                {u.note ? <div className="cell-secondary">{u.note}</div> : <div className="cell-tertiary">（未填备注）</div>}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="card">
        <div className="card-title">AI 评估报告</div>
        {report?.status === "READY" ? (
          <Markdown source={report.markdown} />
        ) : report?.status === "GENERATING" ? (
          <div className="loading">AI 正在依据标注结果撰写报告，请稍候…</div>
        ) : report?.status === "FAILED" ? (
          <EmptyState title="报告生成失败" hint={report.error || "请重试"} />
        ) : (
          <EmptyState
            title="尚未生成报告"
            hint={completed ? "点击右上角「AI 生成评估报告」，由 AI 依据标注结果撰写" : "完成全部标注后可生成"}
          />
        )}
      </section>
    </div>
  );
}

function IntentSummary({ s }) {
  const n = (s.correct || 0) + (s.partial || 0) + (s.wrong || 0);
  const pct = (x) => (n ? (x / n) * 100 : 0);
  return (
    <div className="mt-16">
      <div className="inline" style={{ gap: 24, marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          意图准确率 <b style={{ fontSize: 22 }}>{s.accuracy ?? 0}%</b>
        </div>
        <div className="text-tertiary">
          宽松口径 {s.lenient_accuracy ?? 0}%（部分正确计 0.5）
        </div>
        <div className="text-tertiary">
          最弱：{s.weakest_intent || "—"} ／ 最强：{s.strongest_intent || "—"}
        </div>
      </div>

      <div className="gsb-bar">
        <div className="gsb-bar-seg" style={{ width: `${pct(s.correct)}%`, background: "var(--success)" }} />
        <div className="gsb-bar-seg" style={{ width: `${pct(s.partial)}%`, background: "var(--brand)" }} />
        <div className="gsb-bar-seg" style={{ width: `${pct(s.wrong)}%`, background: "var(--warning)" }} />
      </div>
      <div className="gsb-legend mt-8">
        <span>
          <span className="gsb-legend-dot" style={{ background: "var(--success)" }} />正确 {s.correct || 0}
        </span>
        <span>
          <span className="gsb-legend-dot" style={{ background: "var(--brand)" }} />部分正确 {s.partial || 0}
        </span>
        <span>
          <span className="gsb-legend-dot" style={{ background: "var(--warning)" }} />错误 {s.wrong || 0}
        </span>
      </div>

      {(s.intents || []).length ? (
        <div style={{ marginTop: 18 }}>
          <div className="text-tertiary" style={{ fontSize: 12, marginBottom: 6 }}>按识别意图</div>
          {s.intents.map((a) => (
            <div className="msum-dim" key={a.intent}>
              <div className="inline" style={{ justifyContent: "space-between" }}>
                <span>{a.intent}</span>
                <span>
                  {a.accuracy}% · {a.correct}/{a.total}
                </span>
              </div>
              <div className="msum-bar">
                <div className="msum-bar-fill" style={{ width: `${a.accuracy}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {(s.confusions || []).length ? (
        <div style={{ marginTop: 18 }}>
          <div className="text-tertiary" style={{ fontSize: 12, marginBottom: 6 }}>高频混淆意图对</div>
          <div className="bad-list">
            {s.confusions.map((c, i) => (
              <div key={i} className="bad-item inline" style={{ gap: 8, alignItems: "center" }}>
                <span className="intent-chip predicted">{c.predicted}</span>
                <span className="text-tertiary">→</span>
                <span className="intent-chip expected">{c.corrected}</span>
                <span className="text-tertiary" style={{ marginLeft: "auto" }}>×{c.count}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function GsbSummary({ s }) {
  const total = (s.good || 0) + (s.same || 0) + (s.bad || 0);
  const pct = (n) => (total ? (n / total) * 100 : 0);
  return (
    <div className="mt-16">
      <div className="gsb-bar">
        <div className="gsb-bar-seg" style={{ width: `${pct(s.good)}%`, background: "var(--success)" }} />
        <div className="gsb-bar-seg" style={{ width: `${pct(s.same)}%`, background: "var(--brand)" }} />
        <div className="gsb-bar-seg" style={{ width: `${pct(s.bad)}%`, background: "var(--warning)" }} />
      </div>
      <div className="gsb-legend mt-8">
        <span>
          <span className="gsb-legend-dot" style={{ background: "var(--success)" }} />G {s.good || 0}
        </span>
        <span>
          <span className="gsb-legend-dot" style={{ background: "var(--brand)" }} />S {s.same || 0}
        </span>
        <span>
          <span className="gsb-legend-dot" style={{ background: "var(--warning)" }} />B {s.bad || 0}
        </span>
      </div>
      <div className="inline" style={{ gap: 24, marginTop: 12 }}>
        <div>
          胜率 <b>{s.win_rate ?? 0}%</b>
        </div>
        <div>
          净胜率 <b>{s.net_win_rate ?? 0}%</b>
        </div>
        <div className="text-tertiary" style={{ fontSize: 12 }}>
          净胜率 = (G − B) / (G + S + B)
        </div>
      </div>
    </div>
  );
}

function MultiSummary({ s }) {
  const dims = s.dimensions || [];
  const maxAvg = 5;
  return (
    <div className="mt-16">
      <div className="inline" style={{ gap: 24, marginBottom: 16 }}>
        <div>
          平均总分 <b style={{ fontSize: 22 }}>{s.avg_total ?? "—"}</b>
        </div>
        <div className="text-tertiary">
          最强：{s.strongest_dim || "—"} ／ 最弱：{s.weakest_dim || "—"}
        </div>
      </div>
      {dims.map((d) => (
        <div className="msum-dim" key={d.key}>
          <div className="inline" style={{ justifyContent: "space-between" }}>
            <span>
              {d.name} <span className="text-tertiary">（{d.weight}%）</span>
            </span>
            <span>
              {d.avg} · 低分 {d.low_count}
            </span>
          </div>
          <div className="msum-bar">
            <div className="msum-bar-fill" style={{ width: `${(d.avg / maxAvg) * 100}%` }} />
          </div>
        </div>
      ))}
      {s.distribution ? (
        <div className="inline" style={{ gap: 12, marginTop: 12 }}>
          {Object.entries(s.distribution).map(([k, v]) => (
            <span key={k} className="text-tertiary" style={{ fontSize: 12 }}>
              {k} 分：{v}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
