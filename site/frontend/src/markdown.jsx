import React from "react";

// 轻量 Markdown 渲染器：评估报告由模型自由生成，格式不固定，这里只覆盖报告会用到的语法
// （标题 / 段落 / 有序无序列表 / 表格 / 引用 / 分隔线 / 代码块 + 行内 加粗 / 斜体 / 代码 / 链接）。
// 刻意不引第三方依赖（见 CLAUDE.md：优先标准能力、控制依赖）。

// 智搜结果 / 标注内容里常见的媒体标记：整行 `[图片] <url>` 或 `[视频]：<url>`，
// 也常见夹在段落文字中间/末尾（同一行前面还有其他文字），非独占一行。
// URL 多为新浪图床（无扩展名），[视频] 给的往往是封面帧而非可播放文件，故默认按图片渲染。
const MEDIA_RE = /^\s*\[\s*(图片|图|图像|视频|image|img|video)\s*\]\s*[:：]?\s*(https?:\/\/\S+?)\s*$/i;
const INLINE_MEDIA_RE = /\[\s*(图片|图|图像|视频|image|img|video)\s*\]\s*[:：]?\s*(https?:\/\/\S+)/gi;
// 部分数据源（如 GSB 基线/实验列）图片链接没有 [图片] 标记也没有协议前缀，逗号分隔平铺在正文里，
// 例如 `bj.service.t.sinaimg.cn/middle/xxx, wx1.sinaimg.cn/middle/yyy`。这类统一按图片渲染。
const BARE_SINAIMG_RE = /[,，]?\s*(https?:\/\/)?((?:[a-z0-9-]+\.)*sinaimg\.cn\/[^\s,，]+)\s*[,，]?/gi;
const VIDEO_FILE_RE = /\.(mp4|m3u8|mov|webm)(\?|#|$)/i;

function isVideoMarker(label) {
  return /视频|video/i.test(label);
}

// 从一行文字中摘出所有图片/视频标记（不要求独占整行，也不要求带 [图片] 标记或协议前缀），
// 返回剩余文字 + 摘出的媒体项
function extractInlineMedia(line) {
  const items = [];
  const text = line
    .replace(INLINE_MEDIA_RE, (_full, label, url) => {
      items.push({ kind: isVideoMarker(label) ? "video" : "image", url });
      return " ";
    })
    .replace(BARE_SINAIMG_RE, (_full, scheme, hostAndPath) => {
      // 没写协议时优先试 https，失败（如 bj.service.t.sinaimg.cn 证书问题）再退回 http 重试一次
      const url = scheme ? `${scheme}${hostAndPath}` : `https://${hostAndPath}`;
      const altUrl = scheme ? undefined : `http://${hostAndPath}`;
      items.push({ kind: "image", url, altUrl });
      return " ";
    })
    .replace(/[ \t]{2,}/g, " ")
    .trim();
  return { text, items };
}

// 有些图床（如 sinaimg）直接跳转打开原图会被拒绝（只允许当"图片"嵌入，不允许当"网页"打开，
// 不管带不带 Referer 都一样），所以新标签页不能直接跳原图 URL，而是开一个我们自己的空白页，
// 在里面用 <img>/<video> 把原图嵌进去——这样请求方式对图床来说还是"图片"，不是"网页"。
// 用 DOM API 而不是拼 HTML 字符串写入，避免 URL 里混进恶意内容时被当成标签解析。
function openMediaViewer(e, item) {
  e.preventDefault();
  const win = window.open("", "_blank", "noopener");
  if (!win) return;
  const isVideo = item.kind === "video" && VIDEO_FILE_RE.test(item.url);
  win.document.title = isVideo ? "视频预览" : "图片预览";
  const style = win.document.createElement("style");
  style.textContent =
    "body{margin:0;background:#111;display:flex;align-items:center;justify-content:center;min-height:100vh}" +
    "img,video{max-width:100%;max-height:100vh}";
  win.document.head.appendChild(style);
  const el = win.document.createElement(isVideo ? "video" : "img");
  el.src = item.url;
  if (isVideo) {
    el.controls = true;
    el.autoplay = true;
  }
  win.document.body.appendChild(el);
}

function MediaItem({ item }) {
  const [src, setSrc] = React.useState(item.url);
  const [failed, setFailed] = React.useState(false);

  const handleError = () => {
    // 没写协议的链接先试 https，失败了（比如证书有问题的服务域名）再退回 http 试一次
    if (item.altUrl && src !== item.altUrl) {
      setSrc(item.altUrl);
    } else {
      setFailed(true);
    }
  };

  if (failed) {
    // 加载失败多是微博防盗链/登录验证拦截，前端无法绕过，保留原链接点击跳转即可，
    // 不把一长串带签名参数的 URL 直接铺满页面。
    // rel 只留 noopener：这类图床很多靠 Referer 做防盗链，noreferrer 会让新标签页直接 403。
    return (
      <a className="md-media-fallback" href={item.url} target="_blank" rel="noopener" title={item.url}>
        {item.kind === "video" ? "🎬 视频加载失败，点击查看原视频" : "🖼 图片加载失败，点击查看原图"}
      </a>
    );
  }
  if (item.kind === "video" && VIDEO_FILE_RE.test(src)) {
    return <video className="md-media-el" src={src} controls preload="metadata" onError={handleError} />;
  }
  return (
    <a
      className={`md-media-item${item.kind === "video" ? " is-video" : ""}`}
      href={item.url}
      target="_blank"
      rel="noopener"
      title={item.kind === "video" ? "视频封面，点击打开原链接" : "点击查看大图"}
      onClick={(e) => openMediaViewer(e, item)}
    >
      <img
        className="md-media-el"
        src={src}
        alt={item.kind === "video" ? "视频封面" : "图片"}
        loading="lazy"
        onError={handleError}
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
          {items.map((it, ii) => {
            const { text, items: media } = extractInlineMedia(it);
            return (
              <li key={ii}>
                {renderInline(text, `li${k}-${ii}`)}
                {media.length ? <MediaBlock items={media} /> : null}
              </li>
            );
          })}
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
    const mediaItems = [];
    const textLines = [];
    for (const ln of buf) {
      const { text, items } = extractInlineMedia(ln);
      if (items.length) mediaItems.push(...items);
      if (text) textLines.push(text);
    }
    if (textLines.length) {
      blocks.push(
        <p key={k++} className="md-p">
          {renderInline(textLines.join("\n"), `p${k}`)}
        </p>
      );
    }
    if (mediaItems.length) {
      blocks.push(<MediaBlock key={k++} items={mediaItems} />);
    }
  }

  return <div className="markdown-body">{blocks}</div>;
}
