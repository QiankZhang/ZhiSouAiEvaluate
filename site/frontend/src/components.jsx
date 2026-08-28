import React, { useEffect, useRef, useState } from "react";
import { subscribe } from "./toast.js";

const ICON_PATHS = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  list: (
    <>
      <path d="M8 6h13" />
      <path d="M8 12h13" />
      <path d="M8 18h13" />
      <path d="M3.5 6h.01" />
      <path d="M3.5 12h.01" />
      <path d="M3.5 18h.01" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
      <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.35-4.35" />
    </>
  ),
  back: <path d="M19 12H5M12 19l-7-7 7-7" />,
  download: <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />,
  more: (
    <>
      <circle cx="5" cy="12" r="1.3" />
      <circle cx="12" cy="12" r="1.3" />
      <circle cx="19" cy="12" r="1.3" />
    </>
  ),
  close: <path d="M18 6 6 18M6 6l12 12" />,
  play: <path d="M8 5v14l11-7z" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="1" />,
  edit: <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 3 21l.5-4.5z" />,
  copy: (
    <>
      <rect x="9" y="9" width="11" height="11" rx="1.5" />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </>
  ),
  trash: <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />,
  chart: <path d="M3 3v18h18M7 16v3M12 11v8M17 6v13" />,
  check: <path d="M20 6 9 17l-5-5" />,
  refresh: (
    <>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
    </>
  ),
  upload: <path d="M12 21V8M7 13l5-5 5 5M4 21h16" />,
  warning: (
    <>
      <path d="M12 9v4M12 17h.01" />
      <path d="M10.29 3.86 1.82 18a1.5 1.5 0 0 0 1.29 2.25h17.78A1.5 1.5 0 0 0 22.18 18L13.71 3.86a1.5 1.5 0 0 0-2.42 0Z" />
    </>
  ),
  expand: <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />,
  collapse: <path d="M3 8V3h5M21 8V3h-5M3 16v5h5M21 16v5h-5" />,
  file: (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </>
  ),
  eye: (
    <>
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
};

export function Icon({ name, size = 18, ...props }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {ICON_PATHS[name] || null}
    </svg>
  );
}

export function Badge({ tone = "neutral", dot = false, children }) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot ? <span className="badge-dot" /> : null}
      {children}
    </span>
  );
}

export function Button({ variant = "secondary", size, icon, children, ...props }) {
  return (
    <button className={`btn btn-${variant}${size ? ` btn-${size}` : ""}`} {...props}>
      {icon ? <Icon name={icon} size={16} /> : null}
      {children}
    </button>
  );
}

export function IconButton({ icon, label, ...props }) {
  return (
    <button className="icon-btn" aria-label={label} title={label} {...props}>
      <Icon name={icon} size={18} />
    </button>
  );
}

export function Modal({ title, open, onClose, children, footer, width }) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={width ? { width: `min(${width}px, 100%)` } : undefined}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <span className="modal-title">{title}</span>
          <IconButton icon="close" label="关闭" onClick={onClose} />
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>
  );
}

export function Field({ label, required, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">
        {label}
        {required ? <span className="field-required">*</span> : null}
      </span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

export function StatCard({ label, value, unit, hint }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value}
        {unit ? <span className="metric-unit">{unit}</span> : null}
      </div>
      {hint ? <div className="text-tertiary" style={{ fontSize: 12, marginTop: 4 }}>{hint}</div> : null}
    </div>
  );
}

export function EmptyState({ title = "暂无数据", hint }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {hint ? <div>{hint}</div> : null}
    </div>
  );
}

export function Progress({ value }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin="0" aria-valuemax="100">
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function StepBar({ current }) {
  const steps = ["数据准备", "AI评测", "人工复核", "报告"];
  return (
    <div className="steps">
      {steps.map((label, index) => (
        <React.Fragment key={label}>
          <div className={`step${index === current ? " active" : index < current ? " done" : ""}`}>
            <span className="step-dot">{index < current ? <Icon name="check" size={14} /> : index + 1}</span>
            <span>{label}</span>
          </div>
          {index < steps.length - 1 ? <span className="step-line" /> : null}
        </React.Fragment>
      ))}
    </div>
  );
}

/* ---------------- Toast ---------------- */

export function ToastHost() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    return subscribe((item) => {
      setItems((prev) => [...prev, item]);
      setTimeout(() => {
        setItems((prev) => prev.filter((i) => i.id !== item.id));
      }, 3200);
    });
  }, []);

  if (items.length === 0) return null;
  return (
    <div className="toast-host">
      {items.map((item) => (
        <div key={item.id} className={`toast toast-${item.tone}`}>
          <Icon name={item.tone === "success" ? "check" : "warning"} size={16} />
          <span>{item.message}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------------- Pagination ---------------- */

export function Pagination({ page, totalPages, total, onChange, pageSize }) {
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="pagination">
      <span className="pagination-info">
        共 {total} 条 · 第 {from}-{to} 条
      </span>
      <div className="pagination-controls">
        <IconButton icon="back" label="上一页" disabled={page <= 1} onClick={() => onChange(page - 1)} />
        <span className="pagination-page">
          {page} / {totalPages}
        </span>
        <button className="icon-btn pagination-next" aria-label="下一页" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          <Icon name="back" size={18} style={{ transform: "rotate(180deg)" }} />
        </button>
      </div>
    </div>
  );
}

/* ---------------- Dropdown menu (「···」操作菜单) ---------------- */

export function Menu({ items }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const visible = items.filter(Boolean);
  if (visible.length === 0) return null;

  return (
    <div className="menu-wrap" ref={ref} onClick={(e) => e.stopPropagation()}>
      <IconButton icon="more" label="更多操作" onClick={() => setOpen((v) => !v)} />
      {open ? (
        <div className="menu-pop" role="menu">
          {visible.map((item) => (
            <button
              key={item.label}
              className={`menu-item${item.danger ? " danger" : ""}`}
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
            >
              {item.icon ? <Icon name={item.icon} size={15} /> : null}
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ---------------- Confirm dialog ---------------- */

export function ConfirmDialog({ open, title = "确认操作", message, confirmText = "确定", danger, onConfirm, onCancel, loading }) {
  if (!open) return null;
  return (
    <Modal
      title={title}
      open={open}
      onClose={onCancel}
      width={360}
      footer={
        <>
          <Button onClick={onCancel}>取消</Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} disabled={loading}>
            {loading ? "处理中…" : confirmText}
          </Button>
        </>
      }
    >
      <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 14 }}>{message}</p>
    </Modal>
  );
}

/* ---------------- 2 步向导指示器 ---------------- */

export function WizardSteps({ steps, current }) {
  return (
    <div className="wizard-steps">
      {steps.map((label, index) => (
        <React.Fragment key={label}>
          <div className={`wizard-step${index === current ? " active" : index < current ? " done" : ""}`}>
            <span className="wizard-step-dot">{index < current ? <Icon name="check" size={13} /> : index + 1}</span>
            <span>{label}</span>
          </div>
          {index < steps.length - 1 ? <span className="wizard-step-line" /> : null}
        </React.Fragment>
      ))}
    </div>
  );
}

/* ---------------- 提示词编辑器：变量高亮 + 变量面板 + 全屏 + 字数统计 ---------------- */

export function PromptEditor({ value, onChange, variables = [] }) {
  const [fullscreen, setFullscreen] = useState(false);
  const textareaRef = useRef(null);
  const highlightRef = useRef(null);

  function insertVariable(token) {
    const el = textareaRef.current;
    if (!el) {
      onChange(value + token);
      return;
    }
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    const next = value.slice(0, start) + token + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + token.length;
      el.setSelectionRange(pos, pos);
    });
  }

  function syncScroll() {
    if (highlightRef.current && textareaRef.current) {
      highlightRef.current.scrollTop = textareaRef.current.scrollTop;
      highlightRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  }

  const highlighted = escapeHtml(value || "").replace(/\{[^{}]+\}/g, (m) => `<mark>${m}</mark>`) + "\n";

  return (
    <div className={`prompt-editor${fullscreen ? " fullscreen" : ""}`}>
      <div className="prompt-editor-toolbar">
        <div className="prompt-editor-vars">
          {variables.map((v) => (
            <button type="button" key={v} className="var-chip" onClick={() => insertVariable(v)}>
              {v}
            </button>
          ))}
        </div>
        <div className="inline" style={{ gap: 4 }}>
          <span className="text-tertiary" style={{ fontSize: 12 }}>{(value || "").length} 字</span>
          <IconButton icon={fullscreen ? "collapse" : "expand"} label={fullscreen ? "退出全屏" : "全屏编辑"} onClick={() => setFullscreen((v) => !v)} />
        </div>
      </div>
      <div className="prompt-editor-area">
        <div className="prompt-editor-highlight" ref={highlightRef} dangerouslySetInnerHTML={{ __html: highlighted }} />
        <textarea
          ref={textareaRef}
          className="prompt-editor-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onScroll={syncScroll}
          spellCheck={false}
          placeholder="在此编写完整提示词：维度、权重、评分标准、判定规则请直接写在提示词内。可点击上方变量插入 {query} 等占位符。"
        />
      </div>
    </div>
  );
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* ---------------- 文件拖拽上传区 ---------------- */

export function Dropzone({ accept, onFile, hint }) {
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState("");
  const inputRef = useRef(null);

  function handleFiles(files) {
    const file = files?.[0];
    if (!file) return;
    setFileName(file.name);
    onFile(file);
  }

  return (
    <div
      className={`dropzone${dragOver ? " drag-over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={(e) => handleFiles(e.target.files)}
      />
      <Icon name="upload" size={24} />
      {fileName ? (
        <div className="dropzone-file">
          <Icon name="file" size={14} /> {fileName}
        </div>
      ) : (
        <>
          <div className="dropzone-title">点击选择文件，或将文件拖拽到此处</div>
          {hint ? <div className="dropzone-hint">{hint}</div> : null}
        </>
      )}
    </div>
  );
}

/* ---------------- 可关闭横幅（关闭状态记忆在 localStorage） ---------------- */

export function DismissibleBanner({ storageKey, icon = "target", children }) {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(storageKey) === "1";
    } catch {
      return false;
    }
  });

  if (dismissed) return null;

  function close() {
    setDismissed(true);
    try {
      localStorage.setItem(storageKey, "1");
    } catch {
      /* ignore storage errors (e.g. private mode) */
    }
  }

  return (
    <div className="banner banner-dismissible">
      <Icon name={icon} size={18} />
      <span style={{ flex: 1 }}>{children}</span>
      <button className="banner-close" aria-label="关闭提示" onClick={close}>
        <Icon name="close" size={14} />
      </button>
    </div>
  );
}

export function Table({ columns, data, empty = <EmptyState />, onRowClick, rowKey = "id" }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={col.width ? { width: col.width } : undefined}>
                {col.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>{empty}</td>
            </tr>
          ) : (
            data.map((row) => (
              <tr
                key={row[rowKey]}
                className={onRowClick ? "clickable" : ""}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key}>{col.render ? col.render(row) : row[col.key]}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
