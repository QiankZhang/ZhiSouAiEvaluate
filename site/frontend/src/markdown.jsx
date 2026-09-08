import React from "react";

// 轻量 Markdown 渲染器：评估报告由模型自由生成，格式不固定，这里只覆盖报告会用到的语法
// （标题 / 段落 / 有序无序列表 / 表格 / 引用 / 分隔线 / 代码块 + 行内 加粗 / 斜体 / 代码 / 链接）。
// 刻意不引第三方依赖（见 CLAUDE.md：优先标准能力、控制依赖）。

// 智搜结果 / 标注内容里常见的媒体标记：整行 `[图片] <url>` 或 `[视频]：<url>`。
// URL 多为新浪图床（无扩展名），[视频] 给的往往是封面帧而非可播放文件，故默认按图片渲染。
const MEDIA_RE = /^\s*\[\s*(图片|图|图像|视频|image|img|video)\s*\]\s*[:：]?\s*(https?:\/\/\S+?)\s*$/i;
const VIDEO_FILE_RE = /\.(mp4|m3u8|mov|webm)(\?|#|$)/i;

function isVideoMarker(label) {
  return /视频|video/i.test(label);
}

function MediaItem({ item }) {
  const [failed, setFailed] = React.useState(false);
  if (failed) {
    return (
      <a className="md-media-fallback" href={item.url} target="_blank" rel="noreferrer noopener">
        {item.kind === "video" ? "🎬 视频" : "🖼 图片"}：{item.url}
      </a>
    );
  }
  if (item.kind === "video" && VIDEO_FILE_RE.test(item.url)) {
    return (
      <video className="md-media-el" src={item.url} controls preload="metadata" onError={() => setFailed(true)} />
    );
  }
  return (
    <a
      className={`md-media-item${item.kind === "video" ? " is-video" : ""}`}
      href={item.url}
      target="_blank"
      rel="noreferrer noopener"
      title={item.kind === "video" ? "视频封面，点击打开原链接" : "点击查看大图"}
    >
      <img
        className="md-media-el"
        src={item.url}
        alt={item.kind === "video" ? "视频封面" : "图片"}
        loading="lazy"
        onError={() => setFailed(true)}
      />
      {item.kind === "video" ? <span className="md-media-badge">▶ 视频</span> : null}
    </a>
  );
}

function MediaBlock({ items }) {
  return (
    <div className={`md-media${items.length === 1 ? " is-single" : ""}`}>
      {items.map((it, idx) => (
        <MediaItem key={idx} item={it} />
      ))}
    </div>
  );
}

function renderInline(text, keyPrefix) {
  // 依次匹配：行内代码 `x`、加粗 **x**、斜体 *x* / _x_、链接 [t](u)
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\n]+\*|_[^_\n]+_|\[[^\]]+\]\([^)\s]+\))/g;
  const nodes = [];
  let last = 0;
  let match;
  let i = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-i${i++}`;
    if (token.startsWith("`")) {
      nodes.push(<code key={key} className="md-code">{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*") || token.startsWith("_")) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else {
      const m = /\[([^\]]+)\]\(([^)\s]+)\)/.exec(token);
      nodes.push(
        <a key={key} href={m[2]} target="_blank" rel="noreferrer noopener">
          {m[1]}
        </a>
      );
    }
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function splitRow(line) {
  return line
    .replace(/^\||\|$/g, "")
    .split(/(?<!\\)\|/)
    .map((c) => c.replace(/\\\|/g, "|").trim());
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$/.test(line);
}

export function Markdown({ source }) {
  const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    // 代码块 ```
    if (line.trim().startsWith("```")) {
      const buf = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        buf.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push(<pre key={k++} className="md-pre"><code>{buf.join("\n")}</code></pre>);
      continue;
    }

    // 媒体标记：连续的 [图片]/[视频] 行合并成一个媒体块
    if (MEDIA_RE.test(line)) {
      const items = [];
      while (i < lines.length) {
        const m = MEDIA_RE.exec(lines[i]);
        if (!m) break;
        items.push({ kind: isVideoMarker(m[1]) ? "video" : "image", url: m[2] });
        i += 1;
      }
      blocks.push(<MediaBlock key={k++} items={items} />);
      continue;
    }

    // 分隔线
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
      blocks.push(<hr key={k++} className="md-hr" />);
      i += 1;
      continue;
    }

    // 标题
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const Tag = `h${Math.min(level + 1, 6)}`;
      blocks.push(
        <Tag key={k++} className={`md-h md-h${level}`}>
          {renderInline(heading[2].replace(/\s+#+\s*$/, ""), `h${k}`)}
        </Tag>
      );
      i += 1;
      continue;
    }

    // 表格：当前行含 | 且下一行是分隔行
    if (line.includes("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push(
        <div key={k++} className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>{header.map((c, ci) => <th key={ci}>{renderInline(c, `th${k}-${ci}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {header.map((_, ci) => <td key={ci}>{renderInline(r[ci] || "", `td${k}-${ri}-${ci}`)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // 引用
    if (/^\s*>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push(
        <blockquote key={k++} className="md-quote">
          {renderInline(buf.join(" "), `q${k}`)}
        </blockquote>
      );
      continue;
    }

    // 列表（单层，连续的 - / * / + 或 1. ）
    const listMatch = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (listMatch) {
      const ordered = /\d/.test(listMatch[2]);
      const items = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (!m) break;
        items.push(m[3]);
        i += 1;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag key={k++} className="md-list">
          {items.map((it, ii) => <li key={ii}>{renderInline(it, `li${k}-${ii}`)}</li>)}
        </ListTag>
      );
      continue;
    }

    // 普通段落：吸收到下一个空行 / 结构行
    const buf = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6}\s|\s*>\s?|\s*([-*+]|\d+[.)])\s|```)/.test(lines[i]) &&
      !MEDIA_RE.test(lines[i]) &&
      !(lines[i].includes("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1]))
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    blocks.push(
      <p key={k++} className="md-p">
        {renderInline(buf.join("\n"), `p${k}`)}
      </p>
    );
  }

  return <div className="markdown-body">{blocks}</div>;
}
