async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    // 会话失效 / 未登录：广播给 App 切回登录页，各调用处无需单独处理
    if (response.status === 401) window.dispatchEvent(new Event("auth:required"));
    let message = `请求失败（HTTP ${response.status}）`;
    let detail = null;
    try {
      const body = await response.json();
      detail = body.detail;
      if (typeof detail === "string") message = detail;
      else if (detail && typeof detail === "object" && detail.message) message = detail.message;
      else if (body.error?.message) message = body.error.message;
    } catch {
      /* ignore parse errors */
    }
    const err = new Error(message);
    err.detail = detail;
    throw err;
  }
  return response.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: (path, body) => request(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: "DELETE" }),
  upload: (path, formData) => request(path, { method: "POST", body: formData }),
};

// 触发浏览器下载后端返回的文件（CSV 导出 / 模板 / 数据集下载等），复用同一份鉴权 fetch，
// 而不是直接 <a href> 跳转（避免相对路径在生产反代下失效，也便于统一处理失败提示）。
export async function downloadFile(path, fallbackName = "download") {
  const response = await fetch(path);
  if (!response.ok) {
    let message = `下载失败（HTTP ${response.status}）`;
    try {
      const body = await response.json();
      message = (typeof body.detail === "string" && body.detail) || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const filename = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const STATUS_LABELS = {
  CREATED: "未开始",
  RUNNING: "执行中",
  COMPLETED: "已完成",
  STOPPED: "已停止",
  FAILED: "执行失败",
};

export const METHOD_LABELS = {
  MULTI_DIM: "多维度",
  GSB: "GSB",
};

// 人工评估中心：标注类型与任务状态的中文标签（与后端 manual.py 一致）
export const ANNOTATE_TYPE_LABELS = {
  GSB: "GSB 标注",
  MULTI_DIM: "多维度评估标注",
  CONVERSATION: "多轮对话标注",
};

export const MANUAL_STATUS_LABELS = {
  ANNOTATING: "标注中",
  COMPLETED: "已完成",
};

// 任务类型现在是自由文本（带历史记录联想），这里只保留初始建议值，不再是固定枚举。
export const DEFAULT_TASK_TYPES = ["通用评估", "博文分析"];

// 评估报告模板：「提示词」类型模板的默认章节与默认提示词，与后端 report.py 保持一致。
// GSB_REPORT_SECTION 仅在任务为 GSB 时由后端纳入。
export const GSB_REPORT_SECTION = "GSB 专项评估";
export const DEFAULT_REPORT_SECTIONS = [
  "整体结论",
  GSB_REPORT_SECTION,
  "分维度问题分析",
  "典型错误 case 分析",
  "改进建议",
];
export const DEFAULT_REPORT_PROMPT =
  "你是「智搜策略效果评估」平台的评估报告撰写助手。基于用户提供的评测统计与样本数据，撰写一份 Markdown 格式的评估总报告。\n\n" +
  "报告需覆盖以下章节（先后顺序、标题措辞可自行安排，但每一项内容都要覆盖到）：\n{章节}\n\n" +
  "要求：结论先行；每个论断都用具体数字或样本 query 佐证，不写空泛套话；层次清晰；开头用一级标题「# <任务名> · 评估报告」并列出关键元信息。";

export const REVIEW_LABELS = {
  NOT_STARTED: "未开始",
  IN_PROGRESS: "复核中",
  COMPLETED: "已复核",
};

export const RESULT_REVIEW_LABELS = {
  PENDING: "待复核",
  APPROVED: "已通过",
  ADJUSTED: "已调整",
};

export const SOURCE_LABELS = {
  UPLOAD: "文件上传",
  SAMPLE: "示例生成",
  DB: "数据库直连",
};

export function statusTone(status) {
  switch (status) {
    case "COMPLETED":
      return "success";
    case "RUNNING":
      return "brand";
    case "FAILED":
      return "warning";
    case "STOPPED":
      return "neutral";
    default:
      return "neutral";
  }
}

export function scoreTone(score) {
  if (score >= 4) return "score-high";
  if (score >= 3) return "score-mid";
  return "score-low";
}

export const PAGE_SIZE = 10;

export function paginate(items, page, pageSize = PAGE_SIZE) {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  return { pageItems: items.slice(start, start + pageSize), total, totalPages, page: safePage };
}
