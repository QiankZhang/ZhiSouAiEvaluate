import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  downloadFile,
  STATUS_LABELS,
  METHOD_LABELS,
  DEFAULT_TASK_TYPES,
  DEFAULT_REPORT_SECTIONS,
  DEFAULT_REPORT_PROMPT,
  REVIEW_LABELS,
  RESULT_REVIEW_LABELS,
  SOURCE_LABELS,
  PAGE_SIZE,
  paginate,
  statusTone,
  scoreTone,
} from "./api.js";
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
  IconButton,
  Menu,
  Modal,
  Pagination,
  Progress,
  PromptEditor,
  StatCard,
  StepBar,
  Table,
  WizardSteps,
} from "./components.jsx";

// 评估方式的底层机制永远只有这两种（决定必需列与打分规则），但显示名称可以自定义——
// 见 CreateDatasetModal 里"评估方式"下拉的「+ 新增评估方式」。
const BASE_METHOD_OPTIONS = [
  { mechanism: "MULTI_DIM", label: "多维度" },
  { mechanism: "GSB", label: "GSB 对比" },
];

// 全平台统一默认维度：相关性 / 全面性 / 准确性 / 可读性 / 时效性，各 20%
const DEFAULT_DIMS = [
  { key: "relevance", name: "相关性", weight: 20 },
  { key: "comprehensiveness", name: "全面性", weight: 20 },
  { key: "accuracy", name: "准确性", weight: 20 },
  { key: "readability", name: "可读性", weight: 20 },
  { key: "timeliness", name: "时效性", weight: 20 },
];

const DEFAULT_PROMPT =
  "你是评测裁判。请依据以下维度与评分标准，对给定内容进行评测。\n{维度}\n{评分标准}\n\n查询：{query}\n待评内容：{待评内容}\n{基线内容}";

const DEFAULT_GSB_RULES = "实验优于基线为 Good，持平为 Same，劣于基线为 Bad";

// 裁判员模型默认值 / 推荐项：全平台统一默认走 DeepSeek V4 Flash，真实调用（见 API.md）
const DEFAULT_JUDGE_MODEL = "deepseek-v4-flash";

const MULTI_OUTPUT_SAMPLE = `{
  "维度评分": [
    { "维度": "相关性", "分值": 4, "理由": "……" }
  ],
  "总分": 4.2,
  "置信度": 0.86
}`;

const GSB_OUTPUT_SAMPLE = `{
  "判定": "Good",
  "理由": "……",
  "置信度": 0.82
}`;

function StatusBadge({ status }) {
  return (
    <Badge tone={statusTone(status)} dot>
      {STATUS_LABELS[status] || status}
    </Badge>
  );
}

function MethodBadge({ method, label }) {
  return <Badge tone="outline">{label || METHOD_LABELS[method] || method}</Badge>;
}

function Score({ value }) {
  return <span className={`score-pill ${scoreTone(value)}`}>{value}</span>;
}

function useLoad(loader, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    let alive = true;
    setLoading(true);
    setError("");
    loader()
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((err) => {
        if (alive) setError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    return reload();
  }, [reload]);

  return { data, loading, error, reload, setData };
}

function Loading() {
  return <div className="loading">正在加载…</div>;
}

function ErrorBox({ message }) {
  return (
    <div className="empty">
      <div className="empty-title">加载失败</div>
      <div>{message}</div>
    </div>
  );
}

/* ---------------- 数据概览 ---------------- */

const RANGE_OPTIONS = [
  { key: "today", label: "今日" },
  { key: "7d", label: "近7天" },
  { key: "30d", label: "近30天" },
  { key: "custom", label: "自定义" },
];

export function OverviewPage() {
  const [range, setRange] = useState("30d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const query = useMemo(() => {
    const params = new URLSearchParams({ range_: range });
    if (range === "custom" && customStart && customEnd) {
      params.set("start", customStart);
      params.set("end", customEnd);
    }
    return params.toString();
  }, [range, customStart, customEnd]);

  const ready = range !== "custom" || Boolean(customStart && customEnd);
  const { data, loading, error } = useLoad(
    () => (ready ? api.get(`/api/overview/metrics?${query}`) : Promise.resolve(null)),
    [query, ready]
  );

  const maxTrend = data ? Math.max(...data.trend.map((t) => t.value), 1) : 1;

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="page-title">数据概览</div>
          <div className="page-desc">智搜策略效果评估 · 核心指标与任务分布</div>
        </div>
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              className={`btn btn-sm ${range === opt.key ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setRange(opt.key)}
            >
              {opt.label}
            </button>
          ))}
          {range === "custom" ? (
            <>
              <input className="date-input" type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
              <span className="text-tertiary">至</span>
              <input className="date-input" type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
            </>
          ) : null}
        </div>
      </div>

      {!ready ? (
        <div className="empty">
          <div className="empty-title">请选择自定义时间范围</div>
        </div>
      ) : loading || !data ? (
        <Loading />
      ) : error ? (
        <ErrorBox message={error} />
      ) : (
        <>
          <div className="metric-grid">
            {data.metrics.map((m) => (
              <StatCard key={m.key} label={m.label} value={m.value} unit={m.unit} />
            ))}
          </div>

          <div className="grid-2">
            <section className="card">
              <h3 className="card-title">评估量趋势</h3>
              <p className="card-sub">
                按样本条数统计 · {data.start} ~ {data.end}
              </p>
              <div className="bar-chart mt-16">
                {data.trend.map((item, i) => (
                  <div className="bar-col" key={`${item.label}-${i}`}>
                    <span className="bar-value">{item.value}</span>
                    <div className="bar" style={{ height: `${Math.max(4, (item.value / maxTrend) * 100)}%` }} />
                    <span className="bar-label">{item.label}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="card">
              <h3 className="card-title">任务类型分布</h3>
              <p className="card-sub">通用评估 / 博文分析</p>
              <div className="dim-list mt-16">
                {data.by_type.map((item) => {
                  const total = data.by_type.reduce((sum, t) => sum + t.value, 0) || 1;
                  return (
                    <div className="dim-row" key={item.name}>
                      <span className="dim-name">{item.name}</span>
                      <div className="dim-track">
                        <div className="dim-fill" style={{ width: `${(item.value / total) * 100}%` }} />
                      </div>
                      <span className="dim-score">{item.value}</span>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
/* ---------------- 评估中心 ---------------- */

function CreateTaskModal({
  open,
  task,
  onClose,
  benchmarks,
  datasets,
  models,
  reportTemplates = [],
  taskTypeOptions,
  onSaved,
  onDatasetsChanged,
  onReportTemplatesChanged,
}) {
  const isEdit = Boolean(task);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [taskType, setTaskType] = useState(DEFAULT_TASK_TYPES[0]);
  const [benchmarkId, setBenchmarkId] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [modelId, setModelId] = useState(DEFAULT_JUDGE_MODEL);
  const [reportTemplateId, setReportTemplateId] = useState("");
  const [showCreateTemplate, setShowCreateTemplate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [localDatasets, setLocalDatasets] = useState(datasets);
  const [showCreateDataset, setShowCreateDataset] = useState(false);

  useEffect(() => {
    setLocalDatasets(datasets);
  }, [datasets]);

  useEffect(() => {
    if (!open) return;
    setMessage("");
    if (task) {
      setName(task.name);
      setDescription(task.description || "");
      setTaskType(task.task_type || DEFAULT_TASK_TYPES[0]);
      setBenchmarkId(task.benchmark_id);
      setDatasetId(task.dataset_id);
      setModelId(task.judge_model);
      setReportTemplateId(task.report_template_id || "");
    } else {
      setName("");
      setDescription("");
      setTaskType(DEFAULT_TASK_TYPES[0]);
      setBenchmarkId("");
      setDatasetId("");
      setModelId(DEFAULT_JUDGE_MODEL);
      setReportTemplateId(reportTemplates[0]?.id || "");
    }
  }, [open, task]); // eslint-disable-line react-hooks/exhaustive-deps

  // 报告模板列表就绪 / 新建后：新建任务默认选第一个
  useEffect(() => {
    if (open && !task && !reportTemplateId && reportTemplates.length) {
      setReportTemplateId(reportTemplates[0].id);
    }
  }, [open, task, reportTemplates, reportTemplateId]);

  // 模型列表就绪后，若当前选择不在列表内则回落到默认（DeepSeek V4 Flash）
  useEffect(() => {
    if (!models.length) return;
    if (!models.some((m) => m.id === modelId)) {
      setModelId(models.some((m) => m.id === DEFAULT_JUDGE_MODEL) ? DEFAULT_JUDGE_MODEL : models[0].id);
    }
  }, [models, modelId]);

  const benchmark = benchmarks.find((b) => b.id === benchmarkId);
  const dataset = localDatasets.find((d) => d.id === datasetId);
  // 评估方式不再单独选择，由选中的评估基准隐式决定，再据此过滤可选数据集
  const evalMethod = benchmark?.eval_method || "";
  const datasetsForMethod = evalMethod ? localDatasets.filter((d) => d.eval_method === evalMethod) : localDatasets;

  const reportTemplate = reportTemplates.find((r) => r.id === reportTemplateId) || null;

  function handleTemplateCreated(rt) {
    onReportTemplatesChanged?.();
    setReportTemplateId(rt.id);
    setShowCreateTemplate(false);
  }

  const datasetMethodOptions = useMemo(() => {
    const map = new Map();
    BASE_METHOD_OPTIONS.forEach((o) => map.set(o.label, o));
    localDatasets.forEach((d) => {
      const label = d.eval_method_display || d.eval_method_label || METHOD_LABELS[d.eval_method] || d.eval_method;
      if (!map.has(label)) map.set(label, { mechanism: d.eval_method, label });
    });
    return Array.from(map.values());
  }, [localDatasets]);

  const estimate = useMemo(() => {
    if (!benchmark || !dataset) return null;
    const dims = benchmark.config?.dimensions || [];
    const avgChars = dataset.total_items ? Math.round(dataset.total_chars / dataset.total_items) : 0;
    const estimatedChars = dataset.total_items * avgChars * Math.max(1, dims.length);
    const inputTokens = Math.ceil(estimatedChars / 1.5);
    const outputTokens = dataset.total_items * Math.max(1, dims.length) * 24;
    const price = models.find((m) => m.id === modelId) || { input_price: 0.02, output_price: 0.08 };
    const cost = (inputTokens / 1000) * price.input_price + (outputTokens / 1000) * price.output_price;
    const duration = Math.max(1, Math.round((dataset.total_items * Math.max(1, dims.length)) / 8));
    return { estimatedChars, tokens: inputTokens + outputTokens, cost, duration };
  }, [benchmark, dataset, modelId, models]);

  function handleBenchmarkChange(id) {
    setBenchmarkId(id);
    const nextBenchmark = benchmarks.find((b) => b.id === id);
    if (nextBenchmark && dataset && dataset.eval_method !== nextBenchmark.eval_method) {
      setDatasetId("");
    }
  }

  function handleDatasetCreated(newDs) {
    setLocalDatasets((prev) => [newDs, ...prev]);
    setDatasetId(newDs.id);
    setShowCreateDataset(false);
    onDatasetsChanged?.();
  }

  async function submit() {
    if (!name.trim()) {
      setMessage("请填写任务名称");
      return;
    }
    if (!benchmarkId || !datasetId || !modelId) {
      setMessage("请完整选择评估基准、评测数据与裁判员模型");
      return;
    }
    setSaving(true);
    setMessage("");
    const payload = {
      name: name.trim(),
      description,
      task_type: taskType,
      benchmark_id: benchmarkId,
      dataset_id: datasetId,
      judge_model: modelId,
      report_template_id: reportTemplateId || null,
    };
    try {
      const saved = isEdit ? await api.put(`/api/tasks/${task.id}`, payload) : await api.post("/api/tasks", payload);
      if (isEdit) {
        toast.success("任务已更新");
      } else {
        // 创建后自动开始评测，无需再手动点「执行评测」
        try {
          await api.post(`/api/tasks/${saved.id}/execute`);
          saved.status = "RUNNING";
          toast.success("任务已创建并开始执行");
        } catch (execErr) {
          toast.error(`任务已创建，但自动开始失败：${execErr.message}，可在列表中手动执行`);
        }
      }
      onSaved(saved);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={isEdit ? "编辑评测任务" : "创建评测任务"}
      open={open}
      onClose={onClose}
      width={760}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={submit} disabled={saving}>
            {saving ? "保存中…" : isEdit ? "保存修改" : "创建任务"}
          </Button>
        </>
      }
    >
      <Field label="任务名称" required>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如：智搜通用评估-0821回归" maxLength={50} />
      </Field>
      <Field label="任务描述" hint={`非必填，最多 50 字 · ${description.length}/50`}>
        <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="说明本次评测的目的与范围" maxLength={50} />
      </Field>

      <Field label="任务类型" hint="用于数据概览的类型统计，可直接输入新类型，输入过的会出现在联想里">
        <input
          className="input"
          list="task-type-options"
          value={taskType}
          onChange={(e) => setTaskType(e.target.value)}
          placeholder="如：通用评估"
          maxLength={20}
        />
        <datalist id="task-type-options">
          {Array.from(new Set([...DEFAULT_TASK_TYPES, ...(taskTypeOptions || [])])).map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
      </Field>

      <Field label="评估基准" required hint="评估方式（多维度 / GSB）由所选基准决定">
        <select className="select" value={benchmarkId} onChange={(e) => handleBenchmarkChange(e.target.value)}>
          <option value="">请选择评估基准</option>
          {benchmarks.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}（{METHOD_LABELS[b.eval_method]}）
            </option>
          ))}
        </select>
        {benchmark ? (
          <div className="card" style={{ padding: 12, marginTop: 8 }}>
            {benchmark.eval_method === "MULTI_DIM" ? (
              <div className="dim-list">
                {(benchmark.config?.dimensions || []).map((d) => (
                  <div key={d.key} className="inline" style={{ justifyContent: "space-between", fontSize: 12 }}>
                    <span className="text-secondary">
                      {d.name}（{d.weight}%）
                    </span>
                    <span className="text-tertiary">{d.criteria}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{benchmark.config?.gsb?.rules}</div>
            )}
          </div>
        ) : null}
      </Field>

      <Field label="评测数据" required>
        <div className="inline" style={{ gap: 8, width: "100%" }}>
          <select className="select" style={{ flex: 1 }} value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
            <option value="">{evalMethod ? `请选择数据集（${METHOD_LABELS[evalMethod]}）` : "请选择数据集"}</option>
            {datasetsForMethod.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}（{d.total_items}条 / {Math.round(d.total_chars / 10000)}万字）
              </option>
            ))}
          </select>
          <Button icon="plus" onClick={() => setShowCreateDataset(true)}>
            创建新数据集
          </Button>
        </div>
      </Field>

      <Field label="AI 裁判员模型" required hint="默认 DeepSeek V4 Flash（推荐）">
        <select className="select" value={modelId} onChange={(e) => setModelId(e.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}（上下文 {Math.round(m.context / 1000)}k · 输入 ¥{m.input_price}/1k tokens）
              {m.id === DEFAULT_JUDGE_MODEL ? " · 推荐（默认）" : m.live ? "" : " · 走模拟引擎"}
            </option>
          ))}
        </select>
      </Field>

      <Field label="评估报告模板" hint="在「评估报告模板」模块维护；任务完成时按此模板生成 Markdown 报告">
        <div className="inline" style={{ gap: 8, width: "100%" }}>
          <select className="select" style={{ flex: 1 }} value={reportTemplateId} onChange={(e) => setReportTemplateId(e.target.value)}>
            <option value="">不生成智能报告（用内置固定模板）</option>
            {reportTemplates.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}（{r.type === "SKILL" ? "技能" : "提示词"}）
              </option>
            ))}
          </select>
          <Button icon="plus" onClick={() => setShowCreateTemplate(true)}>
            新建报告模板
          </Button>
        </div>
        {reportTemplate ? (
          <div className="card" style={{ padding: 12, marginTop: 8, fontSize: 12, color: "var(--text-secondary)" }}>
            {reportTemplate.description || "（无描述）"}
            {reportTemplate.type === "PROMPT" && reportTemplate.config?.sections?.length ? (
              <div className="mt-8">章节：{reportTemplate.config.sections.join(" · ")}</div>
            ) : null}
            {reportTemplate.type === "SKILL" && reportTemplate.config?.skill?.name ? (
              <div className="mt-8">技能：{reportTemplate.config.skill.name}</div>
            ) : null}
          </div>
        ) : null}
      </Field>

      {estimate ? (
        <div className="banner">
          <Icon name="chart" size={18} />
          <span>
            预估字数 <strong>{estimate.estimatedChars.toLocaleString()}</strong> 字 · 预估 token{" "}
            <strong>{estimate.tokens.toLocaleString()}</strong> · 预估耗时约 <strong>{estimate.duration} 秒</strong> · 预估成本约{" "}
            <strong>¥{estimate.cost.toFixed(4)}</strong>
          </span>
        </div>
      ) : null}

      {message ? <div style={{ color: "var(--warning)" }}>{message}</div> : null}

      <CreateDatasetModal
        open={showCreateDataset}
        onClose={() => setShowCreateDataset(false)}
        onCreated={handleDatasetCreated}
        methodOptions={datasetMethodOptions}
      />
      <CreateReportTemplateModal
        open={showCreateTemplate}
        template={null}
        onClose={() => setShowCreateTemplate(false)}
        onSaved={handleTemplateCreated}
      />
    </Modal>
  );
}

export function TasksPage({ navigate }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [taskType, setTaskType] = useState("");
  const [judgeModel, setJudgeModel] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [formTask, setFormTask] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const tasks = useLoad(() => api.get("/api/tasks"), []);
  const benchmarks = useLoad(() => api.get("/api/benchmarks"), []);
  const datasets = useLoad(() => api.get("/api/datasets"), []);
  const models = useLoad(() => api.get("/api/models"), []);
  const reportTemplates = useLoad(() => api.get("/api/report-templates"), []);

  const allTasks = tasks.data?.items || [];
  const taskTypes = useMemo(
    () => Array.from(new Set([...DEFAULT_TASK_TYPES, ...allTasks.map((t) => t.task_type).filter(Boolean)])),
    [allTasks]
  );
  const creators = useMemo(
    () => Array.from(new Set(allTasks.map((t) => t.created_by).filter(Boolean))),
    [allTasks]
  );

  const filtered = useMemo(() => {
    return allTasks.filter((t) => {
      const q = search.trim().toLowerCase();
      if (
        q &&
        !t.name.toLowerCase().includes(q) &&
        !t.id.toLowerCase().includes(q) &&
        !(t.created_by || "").toLowerCase().includes(q)
      )
        return false;
      if (status && t.status !== status) return false;
      if (method && t.eval_method !== method) return false;
      if (taskType && t.task_type !== taskType) return false;
      if (judgeModel && t.judge_model !== judgeModel) return false;
      if (createdBy && t.created_by !== createdBy) return false;
      return true;
    });
  }, [allTasks, search, status, method, taskType, judgeModel, createdBy]);

  useEffect(() => {
    setPage(1);
  }, [search, status, method, taskType, judgeModel, createdBy]);

  // 有任务在执行中时轮询刷新列表，状态/进度自动更新，无需手动刷新
  const hasRunning = allTasks.some((t) => t.status === "RUNNING");
  useEffect(() => {
    if (!hasRunning) return undefined;
    const timer = setInterval(() => tasks.reload(), 2000);
    return () => clearInterval(timer);
  }, [hasRunning, tasks.reload]);

  const { pageItems, total, totalPages } = paginate(filtered, page);

  async function execute(t) {
    try {
      await api.post(`/api/tasks/${t.id}/execute`);
      toast.success("已开始执行");
      tasks.reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function stop(t) {
    try {
      await api.post(`/api/tasks/${t.id}/stop`);
      toast.success("已停止");
      tasks.reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function copyTask(t) {
    try {
      await api.post(`/api/tasks/${t.id}/copy`);
      toast.success("已复制为新任务");
      tasks.reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await api.delete(`/api/tasks/${confirmDelete.id}`);
      toast.success("已删除");
      tasks.reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }
  async function downloadTestSet(t) {
    try {
      await downloadFile(`/api/tasks/${t.id}/export`, `${t.name}-评测结果.csv`);
    } catch (err) {
      toast.error(err.message);
    }
  }

  function menuFor(t) {
    if (t.status === "COMPLETED") {
      return [
        t.review_status === "COMPLETED"
          ? { label: "人工审核", icon: "check", onClick: () => navigate(`/tasks/${t.id}`) }
          : { label: "查看报告", icon: "chart", onClick: () => navigate(`/tasks/${t.id}/report`) },
        { label: "复制任务", icon: "copy", onClick: () => copyTask(t) },
        { label: "下载测试集", icon: "download", onClick: () => downloadTestSet(t) },
        { label: "删除任务", icon: "trash", danger: true, onClick: () => setConfirmDelete(t) },
      ];
    }
    if (t.status === "STOPPED" || t.status === "CREATED") {
      return [
        { label: "编辑任务", icon: "edit", onClick: () => { setFormTask(t); setFormOpen(true); } },
        { label: "复制任务", icon: "copy", onClick: () => copyTask(t) },
        { label: "删除任务", icon: "trash", danger: true, onClick: () => setConfirmDelete(t) },
      ];
    }
    if (t.status === "FAILED") {
      return [
        { label: "编辑任务", icon: "edit", onClick: () => { setFormTask(t); setFormOpen(true); } },
        { label: "查看失败原因", icon: "warning", onClick: () => navigate(`/tasks/${t.id}`) },
      ];
    }
    return [];
  }

  const columns = [
    { key: "id", title: "任务ID", render: (t) => <span className="mono">{t.id}</span> },
    { key: "name", title: "任务名称", render: (t) => <span className="cell-primary">{t.name}</span> },
    { key: "task_type", title: "任务类型", render: (t) => <Badge tone="outline">{t.task_type}</Badge> },
    { key: "status", title: "状态", render: (t) => <StatusBadge status={t.status} /> },
    { key: "eval_method", title: "评估方式", render: (t) => <MethodBadge method={t.eval_method} /> },
    { key: "benchmark_name", title: "评估基准", render: (t) => <span className="cell-secondary">{t.benchmark_name}</span> },
    { key: "progress_total", title: "样本量", render: (t) => <span>{t.progress_total}</span> },
    {
      key: "progress",
      title: "进度",
      render: (t) =>
        t.status === "RUNNING" ? (
          <span className="cell-secondary">
            {t.progress_done}/{t.progress_total}
          </span>
        ) : (
          <span className="cell-tertiary">—</span>
        ),
    },
    { key: "created_at", title: "创建时间", render: (t) => <span className="cell-secondary">{t.created_at}</span> },
    { key: "created_by", title: "创建人", render: (t) => <span>{t.created_by}</span> },
    {
      key: "actions",
      title: "操作",
      width: 200,
      render: (t) => (
        <div className="inline" onClick={(e) => e.stopPropagation()}>
          {t.status === "COMPLETED" ? (
            t.review_status === "COMPLETED" ? (
              <Button size="sm" variant="primary" onClick={() => navigate(`/tasks/${t.id}/report`)}>
                查看报告
              </Button>
            ) : (
              <Button size="sm" variant="primary" onClick={() => navigate(`/tasks/${t.id}`)}>
                人工审核
              </Button>
            )
          ) : null}
          {t.status === "RUNNING" ? (
            <Button size="sm" onClick={() => stop(t)}>
              停止
            </Button>
          ) : null}
          {t.status === "CREATED" || t.status === "STOPPED" ? (
            <Button size="sm" variant="primary" onClick={() => execute(t)}>
              执行评测
            </Button>
          ) : null}
          {t.status === "FAILED" ? (
            <Button size="sm" variant="primary" onClick={() => execute(t)}>
              重试
            </Button>
          ) : null}
          <Menu items={menuFor(t)} />
        </div>
      ),
    },
  ];

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="page-title">智搜策略效果评估</div>
          <div className="page-desc">AI评估中心 · 任务管理</div>
        </div>
        <Button variant="primary" icon="plus" onClick={() => { setFormTask(null); setFormOpen(true); }}>
          创建评测任务
        </Button>
      </div>

      <DismissibleBanner storageKey="tasks-guide-banner" icon="target">
        三步引导：<strong>数据准备</strong> → <strong>AI评测</strong> → <strong>人工复核</strong> → <strong>报告</strong>。建议先配置评估基准与数据集。
      </DismissibleBanner>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar filter-bar" style={{ padding: "16px 20px" }}>
          <div className="search-input">
            <Icon name="search" size={16} />
            <input className="input" placeholder="搜索任务名 / ID / 创建人" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="select" style={{ width: 120 }} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 130 }} value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="">全部评估方式</option>
            <option value="MULTI_DIM">多维度</option>
            <option value="GSB">GSB</option>
          </select>
          <select className="select" style={{ width: 130 }} value={taskType} onChange={(e) => setTaskType(e.target.value)}>
            <option value="">全部任务类型</option>
            {taskTypes.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 150 }} value={judgeModel} onChange={(e) => setJudgeModel(e.target.value)}>
            <option value="">全部裁判员模型</option>
            {(models.data?.items || []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 130 }} value={createdBy} onChange={(e) => setCreatedBy(e.target.value)}>
            <option value="">全部创建人</option>
            {creators.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <span className="spacer" />
          <span className="text-tertiary" style={{ fontSize: 12 }}>
            共 {total} 个任务
          </span>
        </div>
        {tasks.loading && !tasks.data ? (
          <Loading />
        ) : tasks.error && !tasks.data ? (
          <ErrorBox message={tasks.error} />
        ) : (
          <Table columns={columns} data={pageItems} onRowClick={(t) => navigate(`/tasks/${t.id}`)} />
        )}
        <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onChange={setPage} />
      </section>

      <CreateTaskModal
        open={formOpen}
        task={formTask}
        onClose={() => setFormOpen(false)}
        benchmarks={benchmarks.data?.items || []}
        datasets={datasets.data?.items || []}
        models={models.data?.items || []}
        reportTemplates={reportTemplates.data?.items || []}
        taskTypeOptions={taskTypes}
        onSaved={() => { setFormOpen(false); tasks.reload(); }}
        onDatasetsChanged={() => datasets.reload()}
        onReportTemplatesChanged={() => reportTemplates.reload()}
      />

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="删除任务"
        message={confirmDelete ? `确定删除任务「${confirmDelete.name}」吗？此操作不可撤销。` : ""}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
/* ---------------- 任务详情 ---------------- */

function GsbProportionBar({ good, same, bad }) {
  const total = good + same + bad;
  if (!total) return null;
  const pct = (n) => (n / total) * 100;
  return (
    <div className="mt-16">
      <div className="gsb-bar">
        <div className="gsb-bar-seg" style={{ width: `${pct(good)}%`, background: "var(--success)" }} />
        <div className="gsb-bar-seg" style={{ width: `${pct(same)}%`, background: "var(--brand)" }} />
        <div className="gsb-bar-seg" style={{ width: `${pct(bad)}%`, background: "var(--warning)" }} />
      </div>
      <div className="gsb-legend mt-8">
        <span><span className="gsb-legend-dot" style={{ background: "var(--success)" }} />Good {good}</span>
        <span><span className="gsb-legend-dot" style={{ background: "var(--brand)" }} />Same {same}</span>
        <span><span className="gsb-legend-dot" style={{ background: "var(--warning)" }} />Bad {bad}</span>
      </div>
    </div>
  );
}

// 报告顶部指标卡：结构化速览数据；下钻分析、错误 case、建议等由模型生成的 Markdown 正文承载
function ReportView({ report }) {
  const content = report?.content || {};
  const summary = content.summary || {};
  // eval_method 由后端显式携带，不再靠猜测字段是否存在来判断分支（历史 bug：曾用
  // `content.good !== undefined` 判断，但 good 实际嵌在 summary 里，导致 GSB 报告一律走错分支）。
  const isGSB = report?.eval_method === "GSB";

  if (isGSB) {
    const good = summary.good || 0;
    const same = summary.same || 0;
    const bad = summary.bad || 0;
    const netWinRate = summary.net_win_rate || 0;
    return (
      <section className="card report-hero mt-16">
        <div className="metric-grid" style={{ gridTemplateColumns: "repeat(5, 1fr)" }}>
          <div className="metric-card">
            <div className="metric-label">Good</div>
            <div className="metric-value" style={{ color: "var(--success)" }}>{good}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Same</div>
            <div className="metric-value" style={{ color: "var(--brand-dark)" }}>{same}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Bad</div>
            <div className="metric-value" style={{ color: "var(--warning)" }}>{bad}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">胜率</div>
            <div className="metric-value">{summary.win_rate}<span className="metric-unit">%</span></div>
          </div>
          <div className="metric-card">
            <div className="metric-label">净胜率</div>
            <div className="metric-value" style={{ color: netWinRate < 0 ? "var(--warning)" : "var(--success)" }}>
              {netWinRate}<span className="metric-unit">%</span>
            </div>
          </div>
        </div>
        <GsbProportionBar good={good} same={same} bad={bad} />
        <p className="card-sub mt-8">净胜率 = (G − B) / (G + S + B)</p>
      </section>
    );
  }

  return (
    <section className="card report-hero mt-16">
      <div className="metric-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <div className="metric-card">
          <div className="metric-label">样本量</div>
          <div className="metric-value">{summary.total}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">平均总分</div>
          <div className="metric-value">{summary.avg_total}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">低分样本</div>
          <div className="metric-value" style={{ color: summary.low_count ? "var(--warning)" : undefined }}>
            {summary.low_count}
            <span className="metric-unit">（{summary.low_ratio}%）</span>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">平均置信度</div>
          <div className="metric-value">{summary.avg_confidence ?? "—"}</div>
        </div>
      </div>
    </section>
  );
}

function ResultScores({ item }) {
  const base = item.scores || {};
  const adjusted = Boolean(item.adjusted_scores);
  const scores = adjusted ? { ...base, ...item.adjusted_scores } : base;
  if (scores.judgment) {
    const tone = scores.judgment === "Good" ? "success" : scores.judgment === "Bad" ? "warning" : "brand";
    return (
      <div className="inline">
        {adjusted ? <Badge tone="brand">已调整</Badge> : null}
        <Badge tone={tone} dot>
          {scores.judgment}
        </Badge>
        {!adjusted ? <span className="cell-secondary">{scores.total} vs {scores.baseline_total}</span> : null}
      </div>
    );
  }
  return (
    <div className="inline gap-8 wrap">
      {adjusted ? <Badge tone="brand">已调整</Badge> : null}
      <Score value={scores.total} />
      {(scores.dimensions || []).map((d) => (
        <span className="text-tertiary" style={{ fontSize: 12 }} key={d.key}>
          {d.name} {d.score}
        </span>
      ))}
    </div>
  );
}

function ReviewAdjustModal({ open, row, benchmark, saving, onClose, onSubmit }) {
  const isGSB = benchmark?.eval_method === "GSB";
  const [dimScores, setDimScores] = useState([]);
  const [judgment, setJudgment] = useState("Same");
  const [comment, setComment] = useState("");

  useEffect(() => {
    if (!open || !row) return;
    if (isGSB) {
      setJudgment(row.adjusted_scores?.judgment || row.scores.judgment);
    } else {
      const base = row.adjusted_scores?.dimensions || row.scores.dimensions || [];
      setDimScores(base.map((d) => ({ ...d })));
    }
    const defaultComment = row.review_comment && row.review_comment !== "人工标记为待调整" ? row.review_comment : "";
    setComment(defaultComment);
  }, [open, row, isGSB]);

  if (!open || !row) return null;

  function setScore(i, value) {
    const v = Math.max(1, Math.min(5, Number(value) || 1));
    setDimScores((prev) => prev.map((d, idx) => (idx === i ? { ...d, score: v } : d)));
  }

  function submit() {
    if (isGSB) {
      onSubmit({ judgment }, comment);
      return;
    }
    const dims = benchmark?.config?.dimensions || [];
    const total = Math.round(dimScores.reduce((s, d, i) => s + d.score * (dims[i]?.weight || 0), 0)) / 100;
    onSubmit({ dimensions: dimScores, total }, comment);
  }

  return (
    <Modal
      title="调整评分"
      open={open}
      onClose={onClose}
      width={460}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={submit} disabled={saving || !benchmark}>
            {saving ? "保存中…" : "保存调整"}
          </Button>
        </>
      }
    >
      <p className="card-sub" style={{ margin: 0 }}>{row.query}</p>
      {!benchmark ? (
        <Loading />
      ) : isGSB ? (
        <Field label="判定结果">
          <select className="select" value={judgment} onChange={(e) => setJudgment(e.target.value)}>
            <option value="Good">Good</option>
            <option value="Same">Same</option>
            <option value="Bad">Bad</option>
          </select>
        </Field>
      ) : (
        <div className="dim-list">
          {dimScores.map((d, i) => (
            <div className="inline" key={d.key} style={{ justifyContent: "space-between" }}>
              <span className="text-secondary">{d.name}</span>
              <input className="input" style={{ width: 80 }} type="number" min="1" max="5" value={d.score} onChange={(e) => setScore(i, e.target.value)} />
            </div>
          ))}
        </div>
      )}
      <Field label="复核说明" hint="非必填，说明调整原因">
        <textarea className="textarea" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={200} />
      </Field>
    </Modal>
  );
}

export function TaskDetailPage({ id, navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get(`/api/tasks/${id}`), [id]);
  const benchmarkId = data?.benchmark_id;
  const benchmarkLoad = useLoad(() => (benchmarkId ? api.get(`/api/benchmarks/${benchmarkId}`) : Promise.resolve(null)), [benchmarkId]);
  const benchmarks = useLoad(() => api.get("/api/benchmarks"), []);
  const datasets = useLoad(() => api.get("/api/datasets"), []);
  const models = useLoad(() => api.get("/api/models"), []);
  const reportTemplates = useLoad(() => api.get("/api/report-templates"), []);

  const [formOpen, setFormOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [adjustRow, setAdjustRow] = useState(null);
  const [adjustSaving, setAdjustSaving] = useState(false);
  const [approvingAll, setApprovingAll] = useState(false);

  useEffect(() => {
    // 执行中持续轮询；已完成但报告仍在生成时也继续轮询，直到报告就绪
    const pending = data?.status === "RUNNING" || (data?.status === "COMPLETED" && !data?.report);
    if (!pending) return undefined;
    const timer = setInterval(() => reload(), 1500);
    return () => clearInterval(timer);
  }, [data, reload]);

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox message={error} />;
  if (!data) return null;

  const task = data;
  const results = task.results || [];
  const pendingCount = results.filter((r) => r.review_status === "PENDING").length;
  let stepIndex = 0;
  if (task.status === "RUNNING") stepIndex = 1;
  else if (task.status === "FAILED" || (task.status === "STOPPED" && task.progress_done > 0)) stepIndex = 1;
  else if (task.status === "COMPLETED") stepIndex = task.review_status === "COMPLETED" ? 3 : 2;

  async function execute() {
    try {
      await api.post(`/api/tasks/${id}/execute`);
      toast.success("已开始执行");
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function stop() {
    try {
      await api.post(`/api/tasks/${id}/stop`);
      toast.success("已停止");
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function copyTask() {
    try {
      const clone = await api.post(`/api/tasks/${id}/copy`);
      toast.success("已复制为新任务");
      navigate(`/tasks/${clone.id}`);
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    setBusy(true);
    try {
      await api.delete(`/api/tasks/${id}`);
      toast.success("任务已删除");
      navigate("/tasks");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }
  async function downloadTestSet() {
    try {
      await downloadFile(`/api/tasks/${id}/export`, `${task.name}-评测结果.csv`);
    } catch (err) {
      toast.error(err.message);
    }
  }
  // 人工复核全部完成后（review_status 变为 COMPLETED），直接跳转到独立的评估报告页，
  // 不用再让用户自己点"查看完整报告"。/api/tasks/{id}/review 的响应本身就带最新 review_status，
  // 不需要额外再拉一次任务详情来判断。
  async function approve(row) {
    try {
      const updated = await api.put(`/api/tasks/${id}/review`, { row_index: row.row_index, review_status: "APPROVED", review_comment: "人工复核通过" });
      if (updated.review_status === "COMPLETED") {
        toast.success("人工复核已全部完成，已跳转至评估报告");
        navigate(`/tasks/${id}/report`);
      } else {
        reload();
      }
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function approveAll() {
    const pending = results.filter((r) => r.review_status === "PENDING");
    if (pending.length === 0) return;
    setApprovingAll(true);
    try {
      let updated;
      for (const row of pending) {
        updated = await api.put(`/api/tasks/${id}/review`, { row_index: row.row_index, review_status: "APPROVED", review_comment: "人工复核通过" });
      }
      toast.success(`已通过 ${pending.length} 条`);
      if (updated?.review_status === "COMPLETED") {
        navigate(`/tasks/${id}/report`);
      } else {
        reload();
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setApprovingAll(false);
    }
  }
  async function submitAdjust(adjustedScores, comment) {
    setAdjustSaving(true);
    try {
      const updated = await api.put(`/api/tasks/${id}/review`, {
        row_index: adjustRow.row_index,
        review_status: "ADJUSTED",
        adjusted_scores: adjustedScores,
        review_comment: comment || "人工调整评分",
      });
      setAdjustRow(null);
      if (updated.review_status === "COMPLETED") {
        toast.success("人工复核已全部完成，已跳转至评估报告");
        navigate(`/tasks/${id}/report`);
      } else {
        toast.success("已保存调整");
        reload();
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAdjustSaving(false);
    }
  }

  const canEdit = task.status === "CREATED" || task.status === "STOPPED" || task.status === "FAILED";
  const canCopy = task.status === "CREATED" || task.status === "STOPPED" || task.status === "COMPLETED";
  const canDelete = task.status === "CREATED" || task.status === "STOPPED" || task.status === "COMPLETED";

  const resultColumns = [
    { key: "row_index", title: "#", width: 52, render: (r) => <span className="cell-tertiary">{r.row_index}</span> },
    { key: "query", title: "样本 Query", render: (r) => <span className="cell-primary">{r.query}</span> },
    { key: "scores", title: "评分", render: (r) => <ResultScores item={r} /> },
    { key: "reason", title: "理由", render: (r) => <span className="cell-secondary">{r.reason}</span> },
    {
      key: "review",
      title: "复核",
      render: (r) =>
        r.review_status === "PENDING" ? (
          <div className="inline">
            <Button size="sm" variant="primary" onClick={() => approve(r)}>
              通过
            </Button>
            <Button size="sm" onClick={() => setAdjustRow(r)} disabled={!benchmarkLoad.data}>
              调整
            </Button>
          </div>
        ) : (
          <div className="inline">
            <Badge tone={r.review_status === "APPROVED" ? "success" : "brand"}>{RESULT_REVIEW_LABELS[r.review_status] || r.review_status}</Badge>
            {r.review_status === "ADJUSTED" ? (
              <IconButton icon="edit" label="重新调整" onClick={() => setAdjustRow(r)} />
            ) : null}
          </div>
        ),
    },
  ];

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate("/tasks")}>
        <Icon name="back" size={16} />
        返回AI评估中心
      </button>

      <div className="page-head">
        <div>
          <div className="page-title inline">
            {task.name}
            <StatusBadge status={task.status} />
          </div>
          <div className="page-desc">
            <span className="mono">{task.id}</span> · {task.task_type} · {task.benchmark_name} · {task.dataset_name} · {task.judge_model}
          </div>
        </div>
        <div className="inline">
          {task.status === "RUNNING" ? <Button icon="stop" onClick={stop}>停止任务</Button> : null}
          {task.status === "CREATED" || task.status === "STOPPED" ? (
            <Button variant="primary" icon="play" onClick={execute}>
              执行评测
            </Button>
          ) : null}
          {task.status === "FAILED" ? (
            <Button variant="primary" icon="play" onClick={execute}>
              重试
            </Button>
          ) : null}
          <Menu
            items={[
              canEdit && { label: "编辑任务", icon: "edit", onClick: () => setFormOpen(true) },
              canCopy && { label: "复制任务", icon: "copy", onClick: copyTask },
              task.status === "COMPLETED" && { label: "下载测试集", icon: "download", onClick: downloadTestSet },
              canDelete && { label: "删除任务", icon: "trash", danger: true, onClick: () => setConfirmDelete(true) },
            ]}
          />
        </div>
      </div>

      <section className="card">
        <StepBar current={stepIndex} />
        <div className="stat-row mt-16">
          <div className="stat-item">
            <span className="k">样本量</span>
            <span className="v">{task.progress_total}</span>
          </div>
          <div className="stat-item">
            <span className="k">预估字数</span>
            <span className="v">{task.estimated_chars?.toLocaleString()}</span>
          </div>
          <div className="stat-item">
            <span className="k">{task.actual_cost ? "实际成本" : "预估成本"}</span>
            <span className="v">¥{task.actual_cost ? Number(task.actual_cost).toFixed(4) : task.estimated_cost}</span>
          </div>
          <div className="stat-item">
            <span className="k">预估耗时</span>
            <span className="v">{task.estimated_duration_sec}s</span>
          </div>
          <div className="stat-item">
            <span className="k">评测引擎</span>
            <span className="v" style={{ fontSize: 14 }}>
              {task.engine === "agent" ? "真实调用" : "模拟"}
              {task.engine_downgraded ? "（部分降级）" : ""}
            </span>
          </div>
          <div className="stat-item">
            <span className="k">复核进度</span>
            <span className="v" style={{ fontSize: 14 }}>{REVIEW_LABELS[task.review_status] || task.review_status}</span>
          </div>
        </div>

        {task.status === "RUNNING" ? (
          <div className="mt-16">
            <div className="inline" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <span className="text-secondary">评测进度</span>
              <span className="text-secondary">
                {task.progress_done}/{task.progress_total}
              </span>
            </div>
            <Progress value={(task.progress_done / Math.max(1, task.progress_total)) * 100} />
          </div>
        ) : null}

        {task.status === "FAILED" ? (
          <div className="banner mt-16" style={{ background: "var(--warning-10)", borderColor: "var(--warning)" }}>
            <Icon name="warning" size={18} />
            <span>
              失败原因：<strong>{task.error || "执行失败"}</strong>
            </span>
          </div>
        ) : null}
      </section>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar" style={{ padding: "16px 20px", justifyContent: "space-between" }}>
          <h3 className="card-title" style={{ margin: 0 }}>
            评测结果
          </h3>
          <div className="inline">
            <Button size="sm" variant="primary" icon="check" onClick={approveAll} disabled={pendingCount === 0 || approvingAll}>
              {approvingAll ? "处理中…" : `全部通过${pendingCount ? `（${pendingCount}）` : ""}`}
            </Button>
            <Button size="sm" icon="download" onClick={downloadTestSet} disabled={results.length === 0}>
              下载评估测试集
            </Button>
          </div>
        </div>
        {results.length === 0 ? (
          <EmptyState title="暂无结果" hint="执行评测后，评分结果将在此展示" />
        ) : (
          <Table columns={resultColumns} data={results} rowKey="row_index" />
        )}
      </section>

      {task.status === "COMPLETED" && task.report ? (
        <section className="card report-cta">
          <div>
            <h3 className="card-title">评估报告已生成</h3>
            <p className="card-sub">
              {task.review_status !== "COMPLETED"
                ? "人工复核尚未完成，报告为初步统计，复核结果确认后会同步更新。"
                : "汇总指标、Badcase 聚类与逐样本明细已整理为独立报告页，支持复制 / 下载 Markdown。"}
            </p>
          </div>
          <Button variant="primary" icon="chart" onClick={() => navigate(`/tasks/${id}/report`)}>
            查看完整报告
          </Button>
        </section>
      ) : null}

      <CreateTaskModal
        open={formOpen}
        task={task}
        onClose={() => setFormOpen(false)}
        benchmarks={benchmarks.data?.items || []}
        datasets={datasets.data?.items || []}
        models={models.data?.items || []}
        reportTemplates={reportTemplates.data?.items || []}
        onSaved={() => { setFormOpen(false); reload(); }}
        onDatasetsChanged={() => datasets.reload()}
        onReportTemplatesChanged={() => reportTemplates.reload()}
      />

      <ReviewAdjustModal
        open={Boolean(adjustRow)}
        row={adjustRow}
        benchmark={benchmarkLoad.data}
        saving={adjustSaving}
        onClose={() => setAdjustRow(null)}
        onSubmit={submitAdjust}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="删除任务"
        message={`确定删除任务「${task.name}」吗？此操作不可撤销。`}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
/* ---------------- 评估报告（独立页面） ---------------- */

export function TaskReportPage({ id, navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get(`/api/tasks/${id}`), [id]);
  const [markdown, setMarkdown] = useState("");
  const [mdLoading, setMdLoading] = useState(false);
  const [showSource, setShowSource] = useState(false);

  const task = data;
  const report = task?.report;
  const reportReady = task?.status === "COMPLETED" && Boolean(report);

  // 任务已完成但报告还在生成时轮询，报告就绪后自动渲染
  useEffect(() => {
    if (!task || reportReady || task.status !== "COMPLETED") return undefined;
    const timer = setInterval(() => reload(), 2000);
    return () => clearInterval(timer);
  }, [task, reportReady, reload]);

  useEffect(() => {
    if (!reportReady) return;
    setMdLoading(true);
    fetch(`/api/tasks/${id}/report/markdown`)
      .then((res) => {
        if (!res.ok) throw new Error(`Markdown 加载失败（HTTP ${res.status}）`);
        return res.text();
      })
      .then(setMarkdown)
      .catch((err) => toast.error(err.message))
      .finally(() => setMdLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, reportReady]);

  async function copyMarkdown() {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      toast.success("已复制为 Markdown，可直接粘贴到文档 / IM 工具");
    } catch {
      toast.error("复制失败（浏览器拒绝了剪贴板权限），请展开下方源码手动复制");
      setShowSource(true);
    }
  }

  async function downloadMarkdown() {
    try {
      await downloadFile(`/api/tasks/${id}/report/markdown`, `${task.name}-评估报告.md`);
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function downloadXlsx() {
    try {
      await downloadFile(`/api/tasks/${id}/report/xlsx`, `${task.name}-原始打分表.xlsx`);
    } catch (err) {
      toast.error(err.message);
    }
  }

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox message={error} />;
  if (!task) return null;

  if (!reportReady) {
    return (
      <div className="content">
        <button className="back-link" onClick={() => navigate(`/tasks/${id}`)}>
          <Icon name="back" size={16} />
          返回任务详情
        </button>
        <EmptyState
          title={task.status === "COMPLETED" ? "报告生成中…" : "报告尚未生成"}
          hint={task.status === "COMPLETED" ? "评测已完成，正在生成评估报告，稍候会自动展示" : "任务完成评测后会自动生成评估报告"}
        />
      </div>
    );
  }

  const results = task.results || [];
  const isGSB = report.eval_method === "GSB";
  const detailColumns = [
    { key: "row_index", title: "#", width: 52, render: (r) => <span className="cell-tertiary">{r.row_index}</span> },
    { key: "query", title: "样本 Query", render: (r) => <span className="cell-primary">{r.query}</span> },
    { key: "scores", title: "评分", render: (r) => <ResultScores item={r} /> },
    { key: "reason", title: "理由", render: (r) => <span className="cell-secondary">{r.reason}</span> },
    {
      key: "review",
      title: "复核状态",
      render: (r) => <Badge tone={r.review_status === "APPROVED" ? "success" : r.review_status === "ADJUSTED" ? "brand" : "neutral"}>{RESULT_REVIEW_LABELS[r.review_status] || r.review_status}</Badge>,
    },
  ];

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate(`/tasks/${id}`)}>
        <Icon name="back" size={16} />
        返回任务详情
      </button>

      <div className="page-head">
        <div>
          <div className="page-title">{task.name} · 评估报告</div>
          <div className="page-desc">
            <span className="mono">{task.id}</span> · {isGSB ? "GSB 对比" : "多维度"} · {task.benchmark_name} · {task.dataset_name} · {task.judge_model} ·{" "}
            引擎 {task.engine === "agent" ? "真实调用" : "模拟"}
            {task.engine_downgraded ? "（部分降级）" : ""} · 复核状态：{REVIEW_LABELS[task.review_status] || task.review_status}
          </div>
        </div>
        <div className="inline">
          <Button icon="copy" onClick={copyMarkdown} disabled={!markdown || mdLoading}>
            复制 Markdown
          </Button>
          <Button icon="download" onClick={downloadMarkdown}>
            下载 Markdown
          </Button>
          <Button icon="download" onClick={downloadXlsx}>
            下载 Excel
          </Button>
        </div>
      </div>

      {task.review_status !== "COMPLETED" ? (
        <div className="banner">
          <Icon name="target" size={18} />
          <span>人工复核尚未完成，以下为初步统计，复核结果确认后会同步更新。</span>
        </div>
      ) : null}

      <ReportView report={report} />

      <section className="card mt-16">
        {mdLoading ? (
          <Loading />
        ) : markdown ? (
          <Markdown source={markdown} />
        ) : (
          <EmptyState title="报告正文尚未生成" hint="任务完成时会自动生成报告，稍后刷新重试" />
        )}
      </section>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar" style={{ padding: "16px 20px" }}>
          <h3 className="card-title" style={{ margin: 0 }}>
            逐样本明细
          </h3>
        </div>
        <Table columns={detailColumns} data={results} rowKey="row_index" />
      </section>

      <section className="card">
        <div className="toolbar" style={{ justifyContent: "space-between" }}>
          <h3 className="card-title" style={{ margin: 0 }}>
            Markdown 源码
          </h3>
          <Button size="sm" icon={showSource ? "collapse" : "expand"} onClick={() => setShowSource((v) => !v)}>
            {showSource ? "收起" : "展开查看 / 手动复制"}
          </Button>
        </div>
        {showSource ? (
          <div className="code-block mt-16" style={{ maxHeight: 420, overflow: "auto" }}>
            {mdLoading ? "加载中…" : markdown}
          </div>
        ) : null}
      </section>
    </div>
  );
}

/* ---------------- 数据集 ---------------- */

function ExamplePreview({ rows, evalMethod }) {
  if (!rows) return null;
  return (
    <div className="table-wrap mt-8">
      <table className="table">
        <thead>
          <tr>
            <th>query</th>
            <th>content</th>
            {evalMethod === "GSB" ? <th>baseline</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.query}</td>
              <td>{r.content}</td>
              {evalMethod === "GSB" ? <td>{r.baseline}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreateDatasetModal({ open, onClose, onCreated, methodOptions }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mechanism, setMechanism] = useState("MULTI_DIM");
  const [methodLabel, setMethodLabel] = useState(BASE_METHOD_OPTIONS[0].label);
  const [addingMethod, setAddingMethod] = useState(false);
  const [newMethodName, setNewMethodName] = useState("");
  const [newMethodMechanism, setNewMethodMechanism] = useState("MULTI_DIM");
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState([]);
  const [exampleRows, setExampleRows] = useState(null);
  const [showExample, setShowExample] = useState(false);

  const allMethodOptions = useMemo(() => {
    const map = new Map();
    BASE_METHOD_OPTIONS.forEach((o) => map.set(o.label, o));
    (methodOptions || []).forEach((o) => map.set(o.label, o));
    // 当前选中的（可能是刚新增、还没被任何已存在数据集用过的）方式必须始终出现在选项里，
    // 否则 <select> 找不到匹配的 <option>，会静默回退显示成列表第一项，用户会以为新增失败。
    map.set(methodLabel, { mechanism, label: methodLabel });
    return Array.from(map.values());
  }, [methodOptions, methodLabel, mechanism]);

  useEffect(() => {
    if (!open) return;
    setName("");
    setDescription("");
    setMechanism("MULTI_DIM");
    setMethodLabel(BASE_METHOD_OPTIONS[0].label);
    setAddingMethod(false);
    setNewMethodName("");
    setNewMethodMechanism("MULTI_DIM");
    setFile(null);
    setMessage("");
    setErrors([]);
    setExampleRows(null);
    setShowExample(false);
  }, [open]);

  useEffect(() => {
    setExampleRows(null);
    setShowExample(false);
    setFile(null);
    setErrors([]);
  }, [mechanism]);

  function selectMethod(value) {
    if (value === "__add__") {
      setAddingMethod(true);
      return;
    }
    const opt = allMethodOptions.find((o) => o.label === value);
    if (!opt) return;
    setMethodLabel(opt.label);
    setMechanism(opt.mechanism);
  }

  function confirmAddMethod() {
    if (!newMethodName.trim()) {
      toast.error("请填写新评估方式的名称");
      return;
    }
    setMethodLabel(newMethodName.trim());
    setMechanism(newMethodMechanism);
    setAddingMethod(false);
    setNewMethodName("");
  }

  async function toggleExample() {
    if (exampleRows) {
      setShowExample((v) => !v);
      return;
    }
    try {
      const res = await fetch(`/api/datasets/template?eval_method=${mechanism}`);
      const text = await res.text();
      const lines = text.trim().split("\n");
      const header = lines[0].split(",");
      const rows = lines.slice(1).map((line) => {
        const cells = line.split(",");
        return header.reduce((acc, h, i) => ({ ...acc, [h]: cells[i] }), {});
      });
      setExampleRows(rows);
      setShowExample(true);
    } catch {
      toast.error("样例加载失败");
    }
  }

  function downloadTemplate() {
    downloadFile(`/api/datasets/template?eval_method=${mechanism}`, "数据集模板.csv").catch((err) => toast.error(err.message));
  }

  async function submit() {
    if (!name.trim()) {
      setMessage("请填写数据集名称");
      return;
    }
    if (!file) {
      setMessage("请上传数据文件");
      return;
    }
    setSaving(true);
    setMessage("");
    setErrors([]);
    try {
      const defaultLabel = BASE_METHOD_OPTIONS.find((o) => o.mechanism === mechanism)?.label;
      const fd = new FormData();
      fd.append("name", name.trim());
      fd.append("description", description);
      fd.append("eval_method", mechanism);
      fd.append("eval_method_label", methodLabel === defaultLabel ? "" : methodLabel);
      fd.append("file", file);
      const created = await api.upload("/api/datasets/upload", fd);
      toast.success("数据集已创建");
      onCreated(created);
    } catch (err) {
      if (err.detail && typeof err.detail === "object" && err.detail.errors) {
        setErrors(err.detail.errors);
        setMessage(err.detail.message || err.message);
      } else {
        setMessage(err.message);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title="创建数据集"
      open={open}
      onClose={onClose}
      width={680}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={submit} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </Button>
        </>
      }
    >
      <Field label="数据集名称" required>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如：智搜-通用评估样本集" maxLength={50} />
      </Field>
      <Field label="数据集描述" hint={`非必填，最多 200 字 · ${description.length}/200`}>
        <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="说明数据集用途与范围" maxLength={200} />
      </Field>
      <Field label="评估方式" required hint="决定数据集必需列：多维度机制需要 query/content；GSB 机制额外需要 baseline">
        <select className="select" value={methodLabel} onChange={(e) => selectMethod(e.target.value)}>
          {allMethodOptions.map((o) => (
            <option key={o.label} value={o.label}>
              {o.label}（{o.mechanism === "GSB" ? "GSB 机制" : "多维度机制"}）
            </option>
          ))}
          <option value="__add__">+ 新增评估方式…</option>
        </select>
      </Field>

      {addingMethod ? (
        <div className="card" style={{ padding: 14 }}>
          <Field label="新评估方式名称" required>
            <input className="input" value={newMethodName} onChange={(e) => setNewMethodName(e.target.value)} placeholder="如：语义相似度评估" maxLength={20} />
          </Field>
          <Field label="底层机制" required hint="仅决定必需列与打分规则，不影响展示名称">
            <div className="option-cards">
              <div className={`option-card${newMethodMechanism === "MULTI_DIM" ? " selected" : ""}`} onClick={() => setNewMethodMechanism("MULTI_DIM")}>
                <div className="option-card-title">📊 多维度机制</div>
                <div className="option-card-desc">字段：query、content</div>
              </div>
              <div className={`option-card${newMethodMechanism === "GSB" ? " selected" : ""}`} onClick={() => setNewMethodMechanism("GSB")}>
                <div className="option-card-title">⚖ GSB 机制</div>
                <div className="option-card-desc">额外字段：baseline</div>
              </div>
            </div>
          </Field>
          <div className="inline" style={{ gap: 8, marginTop: 4 }}>
            <Button size="sm" onClick={() => setAddingMethod(false)}>
              取消
            </Button>
            <Button size="sm" variant="primary" onClick={confirmAddMethod}>
              确定新增
            </Button>
          </div>
        </div>
      ) : null}

      <div className="inline" style={{ gap: 8 }}>
        <Button size="sm" icon="download" onClick={downloadTemplate}>
          下载标准模板
        </Button>
        <Button size="sm" icon="eye" onClick={toggleExample}>
          {showExample ? "收起样例" : "查看数据集样例"}
        </Button>
      </div>
      {showExample ? <ExamplePreview rows={exampleRows} evalMethod={mechanism} /> : null}
      <Dropzone
        accept=".csv,.json,.jsonl,.xlsx"
        onFile={(f) => {
          setFile(f);
          setErrors([]);
          setMessage("");
        }}
        hint="支持 CSV / JSON / JSONL / XLSX，单文件 ≤ 50MB"
      />
      {errors.length > 0 ? (
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

export function DatasetsPage({ navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get("/api/datasets"), []);
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const all = data?.items || [];
  const creators = useMemo(() => Array.from(new Set(all.map((d) => d.created_by))), [all]);
  const methodOptions = useMemo(() => {
    const map = new Map();
    BASE_METHOD_OPTIONS.forEach((o) => map.set(o.label, o));
    all.forEach((d) => {
      const label = d.eval_method_display || d.eval_method_label || METHOD_LABELS[d.eval_method] || d.eval_method;
      if (!map.has(label)) map.set(label, { mechanism: d.eval_method, label });
    });
    return Array.from(map.values());
  }, [all]);

  const filtered = useMemo(() => {
    return all.filter((d) => {
      const q = search.trim().toLowerCase();
      if (q && !d.name.toLowerCase().includes(q) && !d.id.toLowerCase().includes(q)) return false;
      if (source && d.source !== source) return false;
      if (createdBy && d.created_by !== createdBy) return false;
      if (dateStart && d.created_at.slice(0, 10) < dateStart) return false;
      if (dateEnd && d.created_at.slice(0, 10) > dateEnd) return false;
      return true;
    });
  }, [all, search, source, createdBy, dateStart, dateEnd]);

  useEffect(() => {
    setPage(1);
  }, [search, source, createdBy, dateStart, dateEnd]);

  const { pageItems, total, totalPages } = paginate(filtered, page);

  async function handleDownload(d) {
    try {
      await downloadFile(`/api/datasets/${d.id}/download`, `${d.name}.csv`);
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await api.delete(`/api/datasets/${confirmDelete.id}`);
      toast.success("已删除");
      reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }

  const columns = [
    {
      key: "name",
      title: "数据集名称",
      render: (d) => (
        <span className="cell-primary" style={{ cursor: "pointer" }} onClick={() => navigate(`/datasets/${d.id}`)}>
          {d.name}
        </span>
      ),
    },
    { key: "eval_method", title: "评估方式", render: (d) => <MethodBadge method={d.eval_method} label={d.eval_method_display} /> },
    { key: "source", title: "来源", render: (d) => <Badge tone="outline">{SOURCE_LABELS[d.source] || d.source}</Badge> },
    { key: "total_chars", title: "字数数量", render: (d) => <span>{d.total_chars.toLocaleString()}</span> },
    { key: "total_items", title: "数据条数", render: (d) => <span>{d.total_items}</span> },
    { key: "created_at", title: "创建时间", render: (d) => <span className="cell-secondary">{d.created_at}</span> },
    { key: "created_by", title: "创建人", render: (d) => <span>{d.created_by}</span> },
    {
      key: "actions",
      title: "操作",
      width: 100,
      render: (d) => (
        <div className="inline" onClick={(e) => e.stopPropagation()}>
          <IconButton icon="download" label="下载" onClick={() => handleDownload(d)} />
          <IconButton
            icon="trash"
            label={d.used_by_tasks > 0 ? "被任务引用中，无法删除" : "删除"}
            disabled={d.used_by_tasks > 0}
            onClick={() => setConfirmDelete(d)}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="page-title">数据集</div>
          <div className="page-desc">数据集管理 · 自助拉数与样本维护</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" icon="database" disabled title="待开发">
            数据源连接
            <span style={{ fontSize: 11, marginLeft: 4 }}>待开发</span>
          </Button>
          <Button variant="primary" icon="plus" onClick={() => setShowCreate(true)}>
            创建数据集
          </Button>
        </div>
      </div>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar filter-bar" style={{ padding: "16px 20px" }}>
          <div className="search-input">
            <Icon name="search" size={16} />
            <input className="input" placeholder="搜索数据集名称 / ID" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="select" style={{ width: 130 }} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">全部来源</option>
            {Object.entries(SOURCE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 130 }} value={createdBy} onChange={(e) => setCreatedBy(e.target.value)}>
            <option value="">全部创建人</option>
            {creators.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <input className="date-input" type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)} />
          <span className="text-tertiary">至</span>
          <input className="date-input" type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)} />
          <span className="spacer" />
          <span className="text-tertiary" style={{ fontSize: 12 }}>
            共 {total} 个数据集
          </span>
        </div>
        {loading ? <Loading /> : error ? <ErrorBox message={error} /> : <Table columns={columns} data={pageItems} />}
        <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onChange={setPage} />
      </section>

      <CreateDatasetModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => {
          setShowCreate(false);
          reload();
        }}
        methodOptions={methodOptions}
      />

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="删除数据集"
        message={confirmDelete ? `确定删除数据集「${confirmDelete.name}」吗？此操作不可撤销。` : ""}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

export function DatasetDetailPage({ id, navigate }) {
  const { data, loading, error } = useLoad(() => api.get(`/api/datasets/${id}`), [id]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const d = data;
  const usedBy = d.used_by || [];

  async function handleDelete() {
    setBusy(true);
    try {
      await api.delete(`/api/datasets/${id}`);
      toast.success("数据集已删除");
      navigate("/datasets");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  async function handleDownload() {
    try {
      await downloadFile(`/api/datasets/${id}/download`, `${d.name}.csv`);
    } catch (err) {
      toast.error(err.message);
    }
  }

  const sampleColumns = [
    { key: "row_index", title: "#", width: 52 },
    { key: "query", title: "Query" },
    { key: "content", title: "待评内容" },
    ...(d.eval_method === "GSB" ? [{ key: "baseline", title: "基线内容" }] : []),
  ];

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate("/datasets")}>
        <Icon name="back" size={16} />
        返回数据集
      </button>

      <div className="page-head">
        <div>
          <div className="page-title">{d.name}</div>
          <div className="page-desc">
            <span className="mono">{d.id}</span> · <MethodBadge method={d.eval_method} label={d.eval_method_display} /> · {SOURCE_LABELS[d.source] || d.source}
          </div>
        </div>
        <div className="inline">
          <Button icon="download" onClick={handleDownload}>
            下载
          </Button>
          <Button
            icon="trash"
            disabled={usedBy.length > 0}
            title={usedBy.length > 0 ? "数据集正被任务引用，无法删除" : undefined}
            onClick={() => setConfirmDelete(true)}
          >
            删除
          </Button>
        </div>
      </div>

      <div className="grid-2">
        <section className="card">
          <h3 className="card-title">基本信息</h3>
          <div className="detail-meta mt-16">
            <div className="stat-item">
              <span className="k">数据条数</span>
              <span className="v">{d.total_items}</span>
            </div>
            <div className="stat-item">
              <span className="k">字数数量</span>
              <span className="v">{d.total_chars.toLocaleString()}</span>
            </div>
            <div className="stat-item">
              <span className="k">创建人</span>
              <span className="v" style={{ fontSize: 14 }}>{d.created_by}</span>
            </div>
            <div className="stat-item">
              <span className="k">创建时间</span>
              <span className="v" style={{ fontSize: 13 }}>{d.created_at}</span>
            </div>
          </div>
          {d.description ? <p className="card-sub mt-16">{d.description}</p> : null}
        </section>
        <section className="card">
          <h3 className="card-title">被引用任务</h3>
          <p className="card-sub">共 {usedBy.length} 个任务引用该数据集</p>
          {usedBy.length === 0 ? (
            <EmptyState title="暂无任务引用" />
          ) : (
            <div className="used-by-list mt-16">
              {usedBy.map((t) => (
                <div className="used-by-item" key={t.id}>
                  <span className="cell-primary" style={{ cursor: "pointer" }} onClick={() => navigate(`/tasks/${t.id}`)}>
                    {t.name}
                  </span>
                  <StatusBadge status={t.status} />
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar" style={{ padding: "16px 20px" }}>
          <h3 className="card-title" style={{ margin: 0 }}>
            样本预览
          </h3>
          <span className="spacer" />
          <span className="text-tertiary" style={{ fontSize: 12 }}>
            仅展示前 {d.samples.length} 条
          </span>
        </div>
        <Table columns={sampleColumns} data={d.samples} rowKey="row_index" />
      </section>

      <ConfirmDialog
        open={confirmDelete}
        title="删除数据集"
        message={`确定删除数据集「${d.name}」吗？此操作不可撤销。`}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
/* ---------------- 评估基准 ---------------- */

function CreateBenchmarkModal({ open, benchmark, onClose, onSaved, methodOptions }) {
  const isEdit = Boolean(benchmark);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [evalType, setEvalType] = useState("PROMPT");
  const [skillInfo, setSkillInfo] = useState(null);
  const [skillUploading, setSkillUploading] = useState(false);
  const [skillError, setSkillError] = useState("");
  const [skillSource, setSkillSource] = useState("builtin"); // builtin | upload
  const [builtinSkills, setBuiltinSkills] = useState([]);
  const [builtinId, setBuiltinId] = useState("");
  const [mechanism, setMechanism] = useState("MULTI_DIM");
  const [methodLabel, setMethodLabel] = useState(BASE_METHOD_OPTIONS[0].label);
  const [addingMethod, setAddingMethod] = useState(false);
  const [newMethodName, setNewMethodName] = useState("");
  const [newMethodMechanism, setNewMethodMechanism] = useState("MULTI_DIM");
  const [dims, setDims] = useState(DEFAULT_DIMS);
  const [promptTemplate, setPromptTemplate] = useState(DEFAULT_PROMPT);
  const [confidenceEnabled, setConfidenceEnabled] = useState(true);
  const [gsbRules, setGsbRules] = useState(DEFAULT_GSB_RULES);
  const [gsbDim, setGsbDim] = useState("overall");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const allMethodOptions = useMemo(() => {
    const map = new Map();
    BASE_METHOD_OPTIONS.forEach((o) => map.set(o.label, o));
    (methodOptions || []).forEach((o) => map.set(o.label, o));
    // 当前选中的（可能是刚新增、还没被任何已存在基准用过的）方式必须始终出现在选项里
    map.set(methodLabel, { mechanism, label: methodLabel });
    return Array.from(map.values());
  }, [methodOptions, methodLabel, mechanism]);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setMessage("");
    setAddingMethod(false);
    setNewMethodName("");
    setNewMethodMechanism("MULTI_DIM");
    setSkillUploading(false);
    setSkillError("");
    api.get("/api/skills/builtin").then((r) => setBuiltinSkills(r.items || [])).catch(() => setBuiltinSkills([]));
    if (benchmark) {
      const ref = benchmark.config?.skill_ref;
      setSkillSource(ref?.source === "custom" ? "upload" : "builtin");
      setBuiltinId(ref?.source === "builtin" ? ref.skill_id : "");
      setName(benchmark.name);
      setDescription(benchmark.description || "");
      setEvalType(benchmark.type || "PROMPT");
      setSkillInfo(benchmark.config?.skill || null);
      setMechanism(benchmark.eval_method);
      setMethodLabel(benchmark.eval_method_display || benchmark.eval_method_label || BASE_METHOD_OPTIONS.find((o) => o.mechanism === benchmark.eval_method)?.label);
      setDims((benchmark.config?.dimensions || DEFAULT_DIMS).map((d) => ({ key: d.key, name: d.name, weight: d.weight })));
      setPromptTemplate(benchmark.config?.prompt_template || DEFAULT_PROMPT);
      setConfidenceEnabled(benchmark.config?.confidence_enabled ?? true);
      setGsbRules(benchmark.config?.gsb?.rules || DEFAULT_GSB_RULES);
      setGsbDim(benchmark.config?.gsb?.adjudication_dimension || "overall");
    } else {
      setName("");
      setDescription("");
      setEvalType("PROMPT");
      setSkillInfo(null);
      setSkillSource("builtin");
      setBuiltinId("");
      setMechanism("MULTI_DIM");
      setMethodLabel(BASE_METHOD_OPTIONS[0].label);
      setDims(DEFAULT_DIMS);
      setPromptTemplate(DEFAULT_PROMPT);
      setConfidenceEnabled(true);
      setGsbRules(DEFAULT_GSB_RULES);
      setGsbDim("overall");
    }
  }, [open, benchmark]);

  async function handleSkillFile(file) {
    setSkillUploading(true);
    setSkillError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const parsed = await api.upload("/api/benchmarks/parse-skill", fd);
      setSkillInfo(parsed);
      toast.success("技能包解析成功");
    } catch (err) {
      setSkillInfo(null);
      setSkillError(err.message);
    } finally {
      setSkillUploading(false);
    }
  }

  function selectMethod(value) {
    if (value === "__add__") {
      setAddingMethod(true);
      return;
    }
    const opt = allMethodOptions.find((o) => o.label === value);
    if (!opt) return;
    setMethodLabel(opt.label);
    setMechanism(opt.mechanism);
  }

  function confirmAddMethod() {
    if (!newMethodName.trim()) {
      toast.error("请填写新评估方式的名称");
      return;
    }
    setMethodLabel(newMethodName.trim());
    setMechanism(newMethodMechanism);
    setAddingMethod(false);
    setNewMethodName("");
  }

  function setWeight(index, value) {
    setDims((prev) => prev.map((d, i) => (i === index ? { ...d, weight: Number(value) || 0 } : d)));
  }
  function addDim() {
    setDims((prev) => [...prev, { key: `dim_${prev.length + 1}`, name: "", weight: 0 }]);
  }
  function removeDim(index) {
    setDims((prev) => prev.filter((_, i) => i !== index));
  }

  const totalWeight = dims.reduce((s, d) => s + (Number(d.weight) || 0), 0);

  function next() {
    if (!name.trim()) {
      setMessage("请填写基准名称");
      return;
    }
    setMessage("");
    setStep(1);
  }

  async function submit() {
    if (mechanism === "MULTI_DIM" && totalWeight !== 100) {
      setMessage(`维度权重合计需为 100%（当前 ${totalWeight}%）`);
      return;
    }
    if (evalType === "SKILL") {
      if (skillSource === "builtin" && !builtinId) {
        setMessage("请选择一个内置技能");
        return;
      }
      if (skillSource === "upload" && !skillInfo) {
        setMessage("请上传并成功解析技能包");
        return;
      }
    } else if (!promptTemplate.trim()) {
      setMessage("请填写提示词内容");
      return;
    }
    setSaving(true);
    setMessage("");
    const defaultLabel = BASE_METHOD_OPTIONS.find((o) => o.mechanism === mechanism)?.label;
    const payload = {
      name: name.trim(),
      description,
      eval_type: evalType,
      eval_method: mechanism,
      eval_method_label: methodLabel === defaultLabel ? "" : methodLabel,
      dimensions: mechanism === "MULTI_DIM" ? dims.map(({ key, name: dName, weight }) => ({ key, name: dName || key, weight: Number(weight) || 0 })) : [],
      prompt_template: evalType === "PROMPT" ? promptTemplate : undefined,
      skill: evalType === "SKILL" && skillSource === "upload" ? skillInfo : undefined,
      skill_ref:
        evalType === "SKILL"
          ? skillSource === "builtin"
            ? { source: "builtin", skill_id: builtinId }
            : { source: "custom", skill_id: skillInfo?.name }
          : undefined,
      confidence_enabled: confidenceEnabled,
      gsb_rules: mechanism === "GSB" ? gsbRules : undefined,
      gsb_adjudication_dimension: mechanism === "GSB" ? gsbDim : undefined,
    };
    try {
      const saved = isEdit ? await api.put(`/api/benchmarks/${benchmark.id}`, payload) : await api.post("/api/benchmarks", payload);
      toast.success(isEdit ? "评估基准已更新" : "评估基准已创建");
      onSaved(saved);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setSaving(false);
    }
  }

  const variables = mechanism === "GSB" ? ["{query}", "{待评内容}", "{基线内容}", "{维度}", "{评分标准}"] : ["{query}", "{待评内容}", "{维度}", "{评分标准}"];

  const builtinById = Object.fromEntries(builtinSkills.map((s) => [s.skill_id, s]));

  function selectBuiltin(id) {
    setBuiltinId(id);
    setSkillError("");
    setSkillInfo(id ? builtinById[id] || null : null);
  }

  // 技能来源为「内置」时按当前评估方式自动预选推荐技能
  useEffect(() => {
    if (evalType !== "SKILL" || skillSource !== "builtin" || !builtinSkills.length) return;
    const rec = builtinSkills.find((s) => s.recommended_for === mechanism);
    if (rec && rec.skill_id !== builtinId) selectBuiltin(rec.skill_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evalType, skillSource, mechanism, builtinSkills]);

  return (
    <Modal
      title={isEdit ? "编辑评估基准" : "创建评估基准"}
      open={open}
      onClose={onClose}
      width={860}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          {step === 1 ? <Button onClick={() => setStep(0)}>上一步</Button> : null}
          {step === 0 ? (
            <Button variant="primary" onClick={next}>
              下一步
            </Button>
          ) : (
            <Button variant="primary" onClick={submit} disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </Button>
          )}
        </>
      }
    >
      <WizardSteps steps={["基础信息", "指令配置"]} current={step} />

      {step === 0 ? (
        <>
          <Field label="基准名称" required>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如：通用评估-三维度基准" maxLength={50} />
          </Field>
          <Field label="基准描述" hint={`非必填，最多 200 字 · ${description.length}/200`}>
            <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="说明适用场景" maxLength={200} />
          </Field>
          <Field label="评估类型" required>
            <div className="option-cards">
              <div className={`option-card${evalType === "PROMPT" ? " selected" : ""}`} onClick={() => setEvalType("PROMPT")}>
                <div className="option-card-title">✍ 提示词类型</div>
                <div className="option-card-desc">提示词编辑器 + 变量面板</div>
              </div>
              <div className={`option-card${evalType === "SKILL" ? " selected" : ""}`} onClick={() => setEvalType("SKILL")}>
                <div className="option-card-title">🧩 技能 Skill</div>
                <div className="option-card-desc">上传符合 Anthropic Agent Skills 规范的技能包</div>
              </div>
            </div>
          </Field>
          <Field label="评估方式" required hint="决定打分规则：多维度机制走加权维度打分；GSB 机制走实验vs基线判定">
            <select className="select" value={methodLabel} onChange={(e) => selectMethod(e.target.value)}>
              {allMethodOptions.map((o) => (
                <option key={o.label} value={o.label}>
                  {o.label}（{o.mechanism === "GSB" ? "GSB 机制" : "多维度机制"}）
                </option>
              ))}
              <option value="__add__">+ 新增评估方式…</option>
            </select>
          </Field>

          {addingMethod ? (
            <div className="card" style={{ padding: 14 }}>
              <Field label="新评估方式名称" required>
                <input className="input" value={newMethodName} onChange={(e) => setNewMethodName(e.target.value)} placeholder="如：语义相似度评估" maxLength={20} />
              </Field>
              <Field label="底层机制" required hint="仅决定打分规则，不影响展示名称">
                <div className="option-cards">
                  <div className={`option-card${newMethodMechanism === "MULTI_DIM" ? " selected" : ""}`} onClick={() => setNewMethodMechanism("MULTI_DIM")}>
                    <div className="option-card-title">📊 多维度机制</div>
                    <div className="option-card-desc">维度增删、权重合计 100%</div>
                  </div>
                  <div className={`option-card${newMethodMechanism === "GSB" ? " selected" : ""}`} onClick={() => setNewMethodMechanism("GSB")}>
                    <div className="option-card-title">⚖ GSB 机制</div>
                    <div className="option-card-desc">实验 vs 基线，Good/Same/Bad</div>
                  </div>
                </div>
              </Field>
              <div className="inline" style={{ gap: 8, marginTop: 4 }}>
                <Button size="sm" onClick={() => setAddingMethod(false)}>
                  取消
                </Button>
                <Button size="sm" variant="primary" onClick={confirmAddMethod}>
                  确定新增
                </Button>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <>
          {evalType === "SKILL" ? (
            <Field label="技能来源" required hint="内置技能随平台维护；也可上传自定义技能包（Anthropic Agent Skills 规范）">
              <div className="option-cards">
                <div className={`option-card${skillSource === "builtin" ? " selected" : ""}`} onClick={() => setSkillSource("builtin")}>
                  <div className="option-card-title">🏷 内置技能</div>
                  <div className="option-card-desc">multi-dimension-evaluation / gsb-evaluation</div>
                </div>
                <div className={`option-card${skillSource === "upload" ? " selected" : ""}`} onClick={() => { setSkillSource("upload"); setSkillInfo(null); }}>
                  <div className="option-card-title">📤 上传技能包</div>
                  <div className="option-card-desc">.zip（根目录含 SKILL.md）或 SKILL.md</div>
                </div>
              </div>

              {skillSource === "builtin" ? (
                <select className="select mt-8" value={builtinId} onChange={(e) => selectBuiltin(e.target.value)}>
                  <option value="">请选择内置技能</option>
                  {builtinSkills
                    .filter((s) => s.skill_id !== "evaluation-report")
                    .map((s) => (
                      <option key={s.skill_id} value={s.skill_id}>
                        {s.skill_id}（v{s.version}）{s.recommended_for === mechanism ? " · 推荐" : ""}
                      </option>
                    ))}
                </select>
              ) : (
                <Dropzone
                  accept=".zip,.md"
                  onFile={handleSkillFile}
                  hint={skillUploading ? "解析中…" : "支持 .zip 技能包或 SKILL.md，单文件 ≤ 10MB"}
                />
              )}
              {skillError ? (
                <div className="error-list mt-8">
                  <div className="error-list-item">{skillError}</div>
                </div>
              ) : null}
              {skillInfo ? (
                <div className="card mt-8" style={{ padding: 14 }}>
                  <div className="detail-meta">
                    <div className="stat-item">
                      <span className="k">技能名称</span>
                      <span className="v mono" style={{ fontSize: 14 }}>{skillInfo.name}</span>
                    </div>
                    {skillInfo.version ? (
                      <div className="stat-item">
                        <span className="k">版本</span>
                        <span className="v" style={{ fontSize: 14 }}>{skillInfo.version}</span>
                      </div>
                    ) : null}
                    {skillInfo.license ? (
                      <div className="stat-item">
                        <span className="k">许可证</span>
                        <span className="v" style={{ fontSize: 14 }}>{skillInfo.license}</span>
                      </div>
                    ) : null}
                    {skillInfo.files?.length ? (
                      <div className="stat-item">
                        <span className="k">附带文件</span>
                        <span className="v" style={{ fontSize: 14 }}>{skillInfo.files.length} 个</span>
                      </div>
                    ) : null}
                  </div>
                  <p className="card-sub mt-8">{skillInfo.description}</p>
                  <div className="code-block mt-8" style={{ maxHeight: 220, overflow: "auto" }}>
                    {skillInfo.instructions}
                  </div>
                </div>
              ) : null}
            </Field>
          ) : (
            <>
              <Field label="提示词编辑框" required hint="维度、权重、评分标准、判定规则请直接写在提示词内">
                <PromptEditor value={promptTemplate} onChange={setPromptTemplate} variables={variables} />
              </Field>

              <Field label="标准输出格式" hint="裁判员模型应按以下 JSON 结构输出">
                <div className="code-block">{mechanism === "GSB" ? GSB_OUTPUT_SAMPLE : MULTI_OUTPUT_SAMPLE}</div>
              </Field>
            </>
          )}

          <label className="inline" style={{ gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={confidenceEnabled} onChange={(e) => setConfidenceEnabled(e.target.checked)} />
            输出结果附带置信度字段
          </label>

          {mechanism === "MULTI_DIM" ? (
            <Field label="维度与权重" required hint={`权重合计：${totalWeight}%（需等于 100%）`}>
              <div className="dim-list">
                {dims.map((d, i) => (
                  <div className="inline" key={i} style={{ gap: 8 }}>
                    <input
                      className="input"
                      style={{ flex: 1 }}
                      value={d.name}
                      placeholder="维度名称"
                      onChange={(e) => setDims((prev) => prev.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                    />
                    <input className="input" style={{ width: 90 }} type="number" value={d.weight} onChange={(e) => setWeight(i, e.target.value)} />
                    <span className="text-tertiary">%</span>
                    <IconButton icon="trash" label="删除维度" onClick={() => removeDim(i)} />
                  </div>
                ))}
                <Button size="sm" icon="plus" onClick={addDim}>
                  添加维度
                </Button>
              </div>
            </Field>
          ) : (
            <>
              <div className="banner">
                <Icon name="target" size={18} />
                <span>
                  GSB 判定：数据集中的 <strong>baseline</strong> 字段作为基线对象，与待评内容（实验对象）比较后输出 Good / Same / Bad。
                </span>
              </div>
              <Field label="判定规则" required>
                <textarea className="textarea" value={gsbRules} onChange={(e) => setGsbRules(e.target.value)} maxLength={200} />
              </Field>
              <Field label="裁决维度" required hint="用于裁决 Good/Same/Bad 的核心维度标识，如 overall / relevance">
                <input className="input" value={gsbDim} onChange={(e) => setGsbDim(e.target.value)} />
              </Field>
            </>
          )}
        </>
      )}

      {message ? <div style={{ color: "var(--warning)" }}>{message}</div> : null}
    </Modal>
  );
}

export function BenchmarksPage({ navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get("/api/benchmarks"), []);
  const [search, setSearch] = useState("");
  const [evalType, setEvalType] = useState("");
  const [evalMethod, setEvalMethod] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [formBenchmark, setFormBenchmark] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const all = data?.items || [];
  const creators = useMemo(() => Array.from(new Set(all.map((b) => b.created_by))), [all]);
  const methodOptions = useMemo(() => {
    const map = new Map();
    BASE_METHOD_OPTIONS.forEach((o) => map.set(o.label, o));
    all.forEach((b) => {
      const label = b.eval_method_display || b.eval_method_label || METHOD_LABELS[b.eval_method] || b.eval_method;
      if (!map.has(label)) map.set(label, { mechanism: b.eval_method, label });
    });
    return Array.from(map.values());
  }, [all]);

  const filtered = useMemo(() => {
    return all.filter((b) => {
      const q = search.trim().toLowerCase();
      if (q && !b.name.toLowerCase().includes(q) && !b.id.toLowerCase().includes(q)) return false;
      if (evalType && b.type !== evalType) return false;
      if (evalMethod && b.eval_method !== evalMethod) return false;
      if (createdBy && b.created_by !== createdBy) return false;
      return true;
    });
  }, [all, search, evalType, evalMethod, createdBy]);

  useEffect(() => {
    setPage(1);
  }, [search, evalType, evalMethod, createdBy]);

  const { pageItems, total, totalPages } = paginate(filtered, page);

  async function handleCopy(b) {
    try {
      await api.post(`/api/benchmarks/${b.id}/copy`);
      toast.success("已复制");
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await api.delete(`/api/benchmarks/${confirmDelete.id}`);
      toast.success("已删除");
      reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }

  const columns = [
    {
      key: "name",
      title: "基准名称",
      render: (b) => (
        <span className="cell-primary" style={{ cursor: "pointer" }} onClick={() => navigate(`/benchmarks/${b.id}`)}>
          {b.name}
        </span>
      ),
    },
    { key: "type", title: "评估类型", render: (b) => <Badge tone="outline">{b.type === "PROMPT" ? "提示词类型" : "技能 Skill"}</Badge> },
    { key: "eval_method", title: "评估方式", render: (b) => <MethodBadge method={b.eval_method} label={b.eval_method_display} /> },
    { key: "version", title: "版本", render: (b) => <span className="mono">{b.version}</span> },
    { key: "status", title: "状态", render: (b) => <Badge tone={b.status === "VERIFIED" ? "success" : "neutral"}>{b.status === "VERIFIED" ? "已验证" : "未验证"}</Badge> },
    { key: "use_count", title: "使用次数", render: (b) => <span>{b.use_count}</span> },
    { key: "updated_at", title: "更新时间", render: (b) => <span className="cell-secondary">{b.updated_at}</span> },
    { key: "created_by", title: "创建人", render: (b) => <span>{b.created_by}</span> },
    {
      key: "actions",
      title: "操作",
      width: 170,
      render: (b) => (
        <div className="inline" onClick={(e) => e.stopPropagation()}>
          <IconButton icon="eye" label="查看详情" onClick={() => navigate(`/benchmarks/${b.id}`)} />
          <IconButton icon="edit" label="编辑" onClick={() => { setFormBenchmark(b); setFormOpen(true); }} />
          <IconButton icon="copy" label="复制" onClick={() => handleCopy(b)} />
          <IconButton
            icon="trash"
            label={b.use_count > 0 ? "被任务引用中，无法删除" : "删除"}
            disabled={b.use_count > 0}
            onClick={() => setConfirmDelete(b)}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="page-title">评估基准管理</div>
          <div className="page-desc">提示词 / 技能 Skill · 多维度 / GSB</div>
        </div>
        <Button variant="primary" icon="plus" onClick={() => { setFormBenchmark(null); setFormOpen(true); }}>
          创建评估基准
        </Button>
      </div>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar filter-bar" style={{ padding: "16px 20px" }}>
          <div className="search-input">
            <Icon name="search" size={16} />
            <input className="input" placeholder="搜索基准名称 / ID" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="select" style={{ width: 150 }} value={evalType} onChange={(e) => setEvalType(e.target.value)}>
            <option value="">全部评估类型</option>
            <option value="PROMPT">提示词类型</option>
            <option value="SKILL">技能 Skill</option>
          </select>
          <select className="select" style={{ width: 140 }} value={evalMethod} onChange={(e) => setEvalMethod(e.target.value)}>
            <option value="">全部评估方式</option>
            <option value="MULTI_DIM">多维度</option>
            <option value="GSB">GSB</option>
          </select>
          <select className="select" style={{ width: 130 }} value={createdBy} onChange={(e) => setCreatedBy(e.target.value)}>
            <option value="">全部创建人</option>
            {creators.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <span className="spacer" />
          <span className="text-tertiary" style={{ fontSize: 12 }}>
            共 {total} 个基准
          </span>
        </div>
        {loading ? <Loading /> : error ? <ErrorBox message={error} /> : <Table columns={columns} data={pageItems} />}
        <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onChange={setPage} />
      </section>

      <CreateBenchmarkModal
        open={formOpen}
        benchmark={formBenchmark}
        onClose={() => setFormOpen(false)}
        onSaved={() => { setFormOpen(false); reload(); }}
        methodOptions={methodOptions}
      />

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="删除评估基准"
        message={confirmDelete ? `确定删除评估基准「${confirmDelete.name}」吗？此操作不可撤销。` : ""}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

export function BenchmarkDetailPage({ id, navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get(`/api/benchmarks/${id}`), [id]);
  const [showEdit, setShowEdit] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const b = data;
  const usedBy = b.used_by || [];
  const dims = b.config?.dimensions || [];
  const gsb = b.config?.gsb;
  const skill = b.config?.skill;

  async function handleCopy() {
    try {
      const clone = await api.post(`/api/benchmarks/${id}/copy`);
      toast.success("已复制为新基准");
      navigate(`/benchmarks/${clone.id}`);
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    setBusy(true);
    try {
      await api.delete(`/api/benchmarks/${id}`);
      toast.success("评估基准已删除");
      navigate("/benchmarks");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate("/benchmarks")}>
        <Icon name="back" size={16} />
        返回评估基准
      </button>

      <div className="page-head">
        <div>
          <div className="page-title inline">
            {b.name}
            <Badge tone={b.status === "VERIFIED" ? "success" : "neutral"}>{b.status === "VERIFIED" ? "已验证" : "未验证"}</Badge>
          </div>
          <div className="page-desc">
            <span className="mono">{b.id}</span> · {b.type === "PROMPT" ? "提示词类型" : "技能 Skill"} · <MethodBadge method={b.eval_method} label={b.eval_method_display} /> · 版本 {b.version} · 使用 {b.use_count} 次
          </div>
        </div>
        <div className="inline">
          <Button icon="edit" onClick={() => setShowEdit(true)}>
            编辑
          </Button>
          <Button icon="copy" onClick={handleCopy}>
            复制
          </Button>
          <Button
            icon="trash"
            disabled={usedBy.length > 0}
            title={usedBy.length > 0 ? "评估基准正被任务引用，无法删除" : undefined}
            onClick={() => setConfirmDelete(true)}
          >
            删除
          </Button>
        </div>
      </div>

      {b.description ? <p className="card-sub">{b.description}</p> : null}

      {dims.length > 0 ? (
        <section className="card">
          <h3 className="card-title">维度与权重</h3>
          <div className="dim-list mt-16">
            {dims.map((d) => (
              <div className="dim-row" key={d.key}>
                <span className="dim-name">{d.name}</span>
                <div className="dim-track">
                  <div className="dim-fill" style={{ width: `${d.weight}%` }} />
                </div>
                <span className="dim-score">{d.weight}%</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {gsb ? (
        <section className="card">
          <h3 className="card-title">GSB 判定规则</h3>
          <p className="card-sub mt-8">裁决维度：{gsb.adjudication_dimension}</p>
          <p className="mt-8" style={{ fontSize: 14 }}>
            {gsb.rules}
          </p>
        </section>
      ) : null}

      {skill ? (
        <section className="card">
          <h3 className="card-title">技能 Skill</h3>
          <div className="detail-meta mt-16">
            <div className="stat-item">
              <span className="k">技能名称</span>
              <span className="v mono" style={{ fontSize: 14 }}>{skill.name}</span>
            </div>
            {skill.version ? (
              <div className="stat-item">
                <span className="k">版本</span>
                <span className="v" style={{ fontSize: 14 }}>{skill.version}</span>
              </div>
            ) : null}
            {skill.license ? (
              <div className="stat-item">
                <span className="k">许可证</span>
                <span className="v" style={{ fontSize: 14 }}>{skill.license}</span>
              </div>
            ) : null}
            {skill.source_filename ? (
              <div className="stat-item">
                <span className="k">来源文件</span>
                <span className="v" style={{ fontSize: 14 }}>{skill.source_filename}</span>
              </div>
            ) : null}
          </div>
          <p className="card-sub mt-8">{skill.description}</p>
          {skill.allowed_tools?.length ? (
            <p className="mt-8" style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
              允许工具：{skill.allowed_tools.join("、")}
            </p>
          ) : null}
          {skill.files?.length ? (
            <p className="mt-8" style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
              附带文件：{skill.files.join("、")}
            </p>
          ) : null}
          <div className="code-block mt-16">{skill.instructions}</div>
        </section>
      ) : (
        <section className="card">
          <h3 className="card-title">提示词全文</h3>
          <div className="code-block mt-16">{b.config?.prompt_template}</div>
        </section>
      )}

      <section className="card">
        <h3 className="card-title">被引用任务</h3>
        <p className="card-sub">共 {usedBy.length} 个任务引用该基准</p>
        {usedBy.length === 0 ? (
          <EmptyState title="暂无任务引用" />
        ) : (
          <div className="used-by-list mt-16">
            {usedBy.map((t) => (
              <div className="used-by-item" key={t.id}>
                <span className="cell-primary" style={{ cursor: "pointer" }} onClick={() => navigate(`/tasks/${t.id}`)}>
                  {t.name}
                </span>
                <StatusBadge status={t.status} />
              </div>
            ))}
          </div>
        )}
      </section>

      <CreateBenchmarkModal
        open={showEdit}
        benchmark={b}
        onClose={() => setShowEdit(false)}
        onSaved={() => { setShowEdit(false); reload(); }}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="删除评估基准"
        message={`确定删除评估基准「${b.name}」吗？此操作不可撤销。`}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

/* ---------------- 评估报告模板 ---------------- */

function ReportSectionPicker({ sections, onChange }) {
  const [custom, setCustom] = useState("");
  const visible = [...DEFAULT_REPORT_SECTIONS];
  sections.forEach((s) => {
    if (!visible.includes(s)) visible.push(s);
  });
  const toggle = (s) => onChange(sections.includes(s) ? sections.filter((x) => x !== s) : [...sections, s]);
  const add = () => {
    const v = custom.trim();
    if (v && !visible.includes(v)) onChange([...sections, v]);
    setCustom("");
  };
  return (
    <>
      <div className="section-picker">
        {visible.map((s) => {
          const on = sections.includes(s);
          const isCustom = !DEFAULT_REPORT_SECTIONS.includes(s);
          return (
            <label key={s} className={`section-chip${on ? " is-on" : ""}`}>
              <input type="checkbox" checked={on} onChange={() => toggle(s)} />
              <span>{s}</span>
              {isCustom ? (
                <button
                  type="button"
                  className="section-chip-x"
                  title="删除该自定义章节"
                  onClick={(e) => {
                    e.preventDefault();
                    onChange(sections.filter((x) => x !== s));
                  }}
                >
                  ×
                </button>
              ) : null}
            </label>
          );
        })}
      </div>
      <div className="inline" style={{ gap: 8, marginTop: 8 }}>
        <input
          className="input"
          style={{ flex: 1 }}
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="新增自定义章节，如：竞品对比洞察"
          maxLength={20}
        />
        <Button icon="plus" onClick={add}>
          新增章节
        </Button>
      </div>
      <span className="field-hint">「GSB 专项评估」仅当任务为 GSB 对比时才会写入报告</span>
    </>
  );
}

export function CreateReportTemplateModal({ open, template, onClose, onSaved }) {
  const isEdit = Boolean(template);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tplType, setTplType] = useState("SKILL");
  const [promptTemplate, setPromptTemplate] = useState(DEFAULT_REPORT_PROMPT);
  const [sections, setSections] = useState(DEFAULT_REPORT_SECTIONS);
  const [skillSource, setSkillSource] = useState("builtin"); // builtin | upload
  const [builtinSkills, setBuiltinSkills] = useState([]);
  const [builtinId, setBuiltinId] = useState("evaluation-report");
  const [skillInfo, setSkillInfo] = useState(null);
  const [skillUploading, setSkillUploading] = useState(false);
  const [skillError, setSkillError] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setMessage("");
    setSkillError("");
    setSkillUploading(false);
    api.get("/api/skills/builtin").then((r) => setBuiltinSkills(r.items || [])).catch(() => setBuiltinSkills([]));
    if (template) {
      const ref = template.config?.skill_ref;
      setName(template.name);
      setDescription(template.description || "");
      setTplType(template.type || "SKILL");
      setPromptTemplate(template.config?.prompt_template || DEFAULT_REPORT_PROMPT);
      setSections(template.config?.sections?.length ? template.config.sections : DEFAULT_REPORT_SECTIONS);
      setSkillSource(ref?.source === "custom" ? "upload" : "builtin");
      setBuiltinId(ref?.source === "builtin" ? ref.skill_id : "evaluation-report");
      setSkillInfo(template.config?.skill || null);
    } else {
      setName("");
      setDescription("");
      setTplType("SKILL");
      setPromptTemplate(DEFAULT_REPORT_PROMPT);
      setSections(DEFAULT_REPORT_SECTIONS);
      setSkillSource("builtin");
      setBuiltinId("evaluation-report");
      setSkillInfo(null);
    }
  }, [open, template]);

  const builtinById = Object.fromEntries(builtinSkills.map((s) => [s.skill_id, s]));

  useEffect(() => {
    if (tplType === "SKILL" && skillSource === "builtin" && builtinId) {
      setSkillInfo(builtinById[builtinId] || null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tplType, skillSource, builtinId, builtinSkills]);

  async function handleSkillFile(file) {
    setSkillUploading(true);
    setSkillError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const parsed = await api.upload("/api/benchmarks/parse-skill", fd);
      setSkillInfo(parsed);
      toast.success("技能包解析成功");
    } catch (err) {
      setSkillInfo(null);
      setSkillError(err.message);
    } finally {
      setSkillUploading(false);
    }
  }

  function next() {
    if (!name.trim()) {
      setMessage("请填写报告模板名称");
      return;
    }
    setMessage("");
    setStep(1);
  }

  async function submit() {
    if (tplType === "SKILL") {
      if (skillSource === "builtin" && !builtinId) {
        setMessage("请选择一个内置技能");
        return;
      }
      if (skillSource === "upload" && !skillInfo) {
        setMessage("请上传并成功解析技能包");
        return;
      }
    } else if (!promptTemplate.trim()) {
      setMessage("请填写报告提示词");
      return;
    }
    setSaving(true);
    setMessage("");
    const payload = {
      name: name.trim(),
      description,
      tpl_type: tplType,
      prompt_template: tplType === "PROMPT" ? promptTemplate : undefined,
      sections: tplType === "PROMPT" ? sections : [],
      skill: tplType === "SKILL" && skillSource === "upload" ? skillInfo : undefined,
      skill_ref:
        tplType === "SKILL"
          ? skillSource === "builtin"
            ? { source: "builtin", skill_id: builtinId }
            : { source: "custom", skill_id: skillInfo?.name }
          : undefined,
    };
    try {
      const saved = isEdit
        ? await api.put(`/api/report-templates/${template.id}`, payload)
        : await api.post("/api/report-templates", payload);
      toast.success(isEdit ? "报告模板已更新" : "报告模板已创建");
      onSaved(saved);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={isEdit ? "编辑评估报告模板" : "创建评估报告模板"}
      open={open}
      onClose={onClose}
      width={860}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          {step === 1 ? <Button onClick={() => setStep(0)}>上一步</Button> : null}
          {step === 0 ? (
            <Button variant="primary" onClick={next}>
              下一步
            </Button>
          ) : (
            <Button variant="primary" onClick={submit} disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </Button>
          )}
        </>
      }
    >
      <WizardSteps steps={["基础信息", "报告配置"]} current={step} />

      {step === 0 ? (
        <>
          <Field label="模板名称" required>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如：五段式评估报告" maxLength={50} />
          </Field>
          <Field label="模板描述" hint={`非必填，最多 200 字 · ${description.length}/200`}>
            <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="说明报告风格与适用场景" maxLength={200} />
          </Field>
          <Field label="模板类型" required>
            <div className="option-cards">
              <div className={`option-card${tplType === "SKILL" ? " selected" : ""}`} onClick={() => setTplType("SKILL")}>
                <div className="option-card-title">🧩 技能 Skill</div>
                <div className="option-card-desc">内置 evaluation-report 或上传自定义技能包</div>
              </div>
              <div className={`option-card${tplType === "PROMPT" ? " selected" : ""}`} onClick={() => setTplType("PROMPT")}>
                <div className="option-card-title">✍ 提示词类型</div>
                <div className="option-card-desc">提示词 + 章节清单，模型据此产出 Markdown</div>
              </div>
            </div>
          </Field>
        </>
      ) : tplType === "SKILL" ? (
        <Field label="技能来源" required hint="内置技能随平台维护；也可上传自定义技能包（Anthropic Agent Skills 规范）">
          <div className="option-cards">
            <div className={`option-card${skillSource === "builtin" ? " selected" : ""}`} onClick={() => setSkillSource("builtin")}>
              <div className="option-card-title">🏷 内置技能</div>
              <div className="option-card-desc">evaluation-report（评估总报告）</div>
            </div>
            <div className={`option-card${skillSource === "upload" ? " selected" : ""}`} onClick={() => { setSkillSource("upload"); setSkillInfo(null); }}>
              <div className="option-card-title">📤 上传技能包</div>
              <div className="option-card-desc">.zip（根目录含 SKILL.md）或 SKILL.md</div>
            </div>
          </div>

          {skillSource === "builtin" ? (
            <select className="select mt-8" value={builtinId} onChange={(e) => setBuiltinId(e.target.value)}>
              <option value="">请选择内置技能</option>
              {builtinSkills.map((s) => (
                <option key={s.skill_id} value={s.skill_id}>
                  {s.skill_id}（v{s.version}）
                </option>
              ))}
            </select>
          ) : (
            <Dropzone accept=".zip,.md" onFile={handleSkillFile} hint={skillUploading ? "解析中…" : "支持 .zip 技能包或 SKILL.md，单文件 ≤ 10MB"} />
          )}
          {skillError ? (
            <div className="error-list mt-8">
              <div className="error-list-item">{skillError}</div>
            </div>
          ) : null}
          {skillInfo ? (
            <div className="card mt-8" style={{ padding: 14 }}>
              <div className="detail-meta">
                <div className="stat-item">
                  <span className="k">技能名称</span>
                  <span className="v mono" style={{ fontSize: 14 }}>{skillInfo.name}</span>
                </div>
                {skillInfo.version ? (
                  <div className="stat-item">
                    <span className="k">版本</span>
                    <span className="v" style={{ fontSize: 14 }}>{skillInfo.version}</span>
                  </div>
                ) : null}
              </div>
              <p className="card-sub mt-8">{skillInfo.description}</p>
              <div className="code-block mt-8" style={{ maxHeight: 220, overflow: "auto" }}>{skillInfo.instructions}</div>
            </div>
          ) : null}
        </Field>
      ) : (
        <>
          <Field label="报告提示词" required hint="变量 {章节} 会被替换为下方勾选的章节清单">
            <PromptEditor value={promptTemplate} onChange={setPromptTemplate} variables={["{章节}"]} />
          </Field>
          <Field label="报告章节">
            <ReportSectionPicker sections={sections} onChange={setSections} />
          </Field>
        </>
      )}

      {message ? <div style={{ color: "var(--warning)" }}>{message}</div> : null}
    </Modal>
  );
}

export function ReportTemplatesPage({ navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get("/api/report-templates"), []);
  const [search, setSearch] = useState("");
  const [tplType, setTplType] = useState("");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [formTemplate, setFormTemplate] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const all = data?.items || [];
  const filtered = useMemo(() => {
    return all.filter((r) => {
      const q = search.trim().toLowerCase();
      if (q && !r.name.toLowerCase().includes(q) && !r.id.toLowerCase().includes(q)) return false;
      if (tplType && r.type !== tplType) return false;
      return true;
    });
  }, [all, search, tplType]);

  useEffect(() => {
    setPage(1);
  }, [search, tplType]);

  const { pageItems, total, totalPages } = paginate(filtered, page);

  async function handleCopy(r) {
    try {
      await api.post(`/api/report-templates/${r.id}/copy`);
      toast.success("已复制");
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await api.delete(`/api/report-templates/${confirmDelete.id}`);
      toast.success("已删除");
      reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }

  const columns = [
    {
      key: "name",
      title: "模板名称",
      render: (r) => (
        <span className="cell-primary" style={{ cursor: "pointer" }} onClick={() => navigate(`/report-templates/${r.id}`)}>
          {r.name}
        </span>
      ),
    },
    { key: "type", title: "类型", render: (r) => <Badge tone="outline">{r.type === "SKILL" ? "技能 Skill" : "提示词类型"}</Badge> },
    {
      key: "config",
      title: "内容",
      render: (r) =>
        r.type === "SKILL" ? (
          <span className="cell-secondary mono">{r.config?.skill?.name || "—"}</span>
        ) : (
          <span className="cell-secondary">{(r.config?.sections || []).length} 个章节</span>
        ),
    },
    { key: "version", title: "版本", render: (r) => <span className="mono">{r.version}</span> },
    { key: "use_count", title: "使用次数", render: (r) => <span>{r.use_count}</span> },
    { key: "updated_at", title: "更新时间", render: (r) => <span className="cell-secondary">{r.updated_at}</span> },
    { key: "created_by", title: "创建人", render: (r) => <span>{r.created_by}</span> },
    {
      key: "actions",
      title: "操作",
      width: 170,
      render: (r) => (
        <div className="inline" onClick={(e) => e.stopPropagation()}>
          <IconButton icon="eye" label="查看详情" onClick={() => navigate(`/report-templates/${r.id}`)} />
          <IconButton icon="edit" label="编辑" onClick={() => { setFormTemplate(r); setFormOpen(true); }} />
          <IconButton icon="copy" label="复制" onClick={() => handleCopy(r)} />
          <IconButton
            icon="trash"
            label={r.use_count > 0 ? "被任务引用中，无法删除" : "删除"}
            disabled={r.use_count > 0}
            onClick={() => setConfirmDelete(r)}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="page-title">评估报告模板</div>
          <div className="page-desc">提示词 / 技能 Skill · 驱动任务完成时的 Markdown 报告生成</div>
        </div>
        <Button variant="primary" icon="plus" onClick={() => { setFormTemplate(null); setFormOpen(true); }}>
          创建报告模板
        </Button>
      </div>

      <section className="card" style={{ padding: 0 }}>
        <div className="toolbar filter-bar" style={{ padding: "16px 20px" }}>
          <div className="search-input">
            <Icon name="search" size={16} />
            <input className="input" placeholder="搜索模板名称 / ID" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="select" style={{ width: 150 }} value={tplType} onChange={(e) => setTplType(e.target.value)}>
            <option value="">全部类型</option>
            <option value="PROMPT">提示词类型</option>
            <option value="SKILL">技能 Skill</option>
          </select>
          <span className="spacer" />
          <span className="text-tertiary" style={{ fontSize: 12 }}>
            共 {total} 个模板
          </span>
        </div>
        {loading && !data ? <Loading /> : error && !data ? <ErrorBox message={error} /> : <Table columns={columns} data={pageItems} />}
        <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onChange={setPage} />
      </section>

      <CreateReportTemplateModal
        open={formOpen}
        template={formTemplate}
        onClose={() => setFormOpen(false)}
        onSaved={() => { setFormOpen(false); reload(); }}
      />

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="删除评估报告模板"
        message={confirmDelete ? `确定删除「${confirmDelete.name}」吗？此操作不可撤销。` : ""}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

export function ReportTemplateDetailPage({ id, navigate }) {
  const { data, loading, error, reload } = useLoad(() => api.get(`/api/report-templates/${id}`), [id]);
  const [showEdit, setShowEdit] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox message={error} />;
  if (!data) return null;

  const r = data;
  const usedBy = r.used_by || [];
  const skill = r.config?.skill;

  async function handleCopy() {
    try {
      const clone = await api.post(`/api/report-templates/${id}/copy`);
      toast.success("已复制为新模板");
      navigate(`/report-templates/${clone.id}`);
    } catch (err) {
      toast.error(err.message);
    }
  }
  async function handleDelete() {
    setBusy(true);
    try {
      await api.delete(`/api/report-templates/${id}`);
      toast.success("报告模板已删除");
      navigate("/report-templates");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="content">
      <button className="back-link" onClick={() => navigate("/report-templates")}>
        <Icon name="back" size={16} />
        返回评估报告模板
      </button>

      <div className="page-head">
        <div>
          <div className="page-title">{r.name}</div>
          <div className="page-desc">
            <span className="mono">{r.id}</span> · {r.type === "SKILL" ? "技能 Skill" : "提示词类型"} · 版本 {r.version} · 使用 {r.use_count} 次
          </div>
        </div>
        <div className="inline">
          <Button icon="edit" onClick={() => setShowEdit(true)}>编辑</Button>
          <Button icon="copy" onClick={handleCopy}>复制</Button>
          <Button
            icon="trash"
            disabled={usedBy.length > 0}
            title={usedBy.length > 0 ? "报告模板正被任务引用，无法删除" : undefined}
            onClick={() => setConfirmDelete(true)}
          >
            删除
          </Button>
        </div>
      </div>

      {r.description ? <p className="card-sub">{r.description}</p> : null}

      {skill ? (
        <section className="card">
          <h3 className="card-title">技能 Skill</h3>
          <div className="detail-meta mt-16">
            <div className="stat-item">
              <span className="k">技能名称</span>
              <span className="v mono" style={{ fontSize: 14 }}>{skill.name}</span>
            </div>
            {skill.version ? (
              <div className="stat-item">
                <span className="k">版本</span>
                <span className="v" style={{ fontSize: 14 }}>{skill.version}</span>
              </div>
            ) : null}
            {skill.source_filename ? (
              <div className="stat-item">
                <span className="k">来源文件</span>
                <span className="v" style={{ fontSize: 14 }}>{skill.source_filename}</span>
              </div>
            ) : null}
          </div>
          <p className="card-sub mt-8">{skill.description}</p>
          <div className="code-block mt-16">{skill.instructions}</div>
        </section>
      ) : (
        <>
          <section className="card">
            <h3 className="card-title">报告章节</h3>
            <div className="section-picker mt-16">
              {(r.config?.sections || []).map((s) => (
                <span className="section-chip is-on" key={s} style={{ cursor: "default" }}>
                  <span>{s}</span>
                </span>
              ))}
            </div>
          </section>
          <section className="card">
            <h3 className="card-title">报告提示词</h3>
            <div className="code-block mt-16">{r.config?.prompt_template}</div>
          </section>
        </>
      )}

      <section className="card">
        <h3 className="card-title">被引用任务</h3>
        <p className="card-sub">共 {usedBy.length} 个任务引用该模板</p>
        {usedBy.length === 0 ? (
          <EmptyState title="暂无任务引用" />
        ) : (
          <div className="used-by-list mt-16">
            {usedBy.map((t) => (
              <div className="used-by-item" key={t.id}>
                <span className="cell-primary" style={{ cursor: "pointer" }} onClick={() => navigate(`/tasks/${t.id}`)}>
                  {t.name}
                </span>
                <StatusBadge status={t.status} />
              </div>
            ))}
          </div>
        )}
      </section>

      <CreateReportTemplateModal
        open={showEdit}
        template={r}
        onClose={() => setShowEdit(false)}
        onSaved={() => { setShowEdit(false); reload(); }}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="删除评估报告模板"
        message={`确定删除「${r.name}」吗？此操作不可撤销。`}
        danger
        loading={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

/* 人工评估中心的页面在 manual.jsx（ManualEvalPage / ManualAnnotatePage / ManualSummaryPage）。 */
