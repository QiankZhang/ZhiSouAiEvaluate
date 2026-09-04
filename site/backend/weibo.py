"""博文数据集：mid → 原始物料。

后端刻意不直接碰新浪内网。流程是：把 mid 列表写到临时 txt → 子进程调用 qinglong
流水线（`bin.make_data` 抓物料 → `bin.process_data` 补图片分析）→ 回读逐行追加的
jsonl。qinglong 的重依赖（aiohttp / redis / pandas / tqdm）和内网访问隔离在它自己的
Python 环境里，不污染后端。

对外只暴露 `convert_rows()`：入参是 `[{"mid","content"}]`（content = 智搜结果原文），
出参是可直接塞进数据集 / 人工任务的样本列表 + 失败明细。AI 评估中心与人工评估中心共用。
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import config

# 微博 mid：纯数字，长度按历史与当前形态放宽到 6~25 位
_MID_RE = re.compile(r"^\d{6,25}$")


class WeiboConvertError(RuntimeError):
    """qinglong 子进程执行失败（非零退出 / 超时 / 目录缺失）。"""


ProgressCb = Callable[[int, str], None]  # (done, phase)


def normalize_mids(raw_mids: list[str]) -> tuple[list[str], list[str]]:
    """去空、去重（保序）、按 mid 形态校验；返回 (合法 mid, 非法条目)。"""
    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[str] = []
    for item in raw_mids:
        mid = str(item or "").strip()
        if not mid:
            continue
        if not _MID_RE.match(mid):
            invalid.append(mid)
            continue
        if mid in seen:
            continue
        seen.add(mid)
        valid.append(mid)
    return valid, invalid


# ---------------------------------------------------------------------------
# 物料拼接：分段标题块（用户确认的组织方式）
# ---------------------------------------------------------------------------

def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text.strip()


def _section(title: str, body: str) -> str:
    body = body.strip()
    return f"【{title}】\n{body}" if body else ""


def _flatten_pic_analysis(items: Any) -> str:
    lines: list[str] = []
    for i, it in enumerate(items or [], start=1):
        if not isinstance(it, dict):
            continue
        desc = _clean(it.get("desc"))
        analysis = _clean(it.get("analysis"))
        piece = " ".join(p for p in (desc, analysis) if p)
        if piece:
            lines.append(f"图{i}：{piece}")
    return "\n".join(lines)


def _flatten_reposted(items: Any) -> str:
    blocks: list[str] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        parts = [
            _clean(it.get("content")),
            _clean(it.get("voice2text")),
            _clean(it.get("pic_ocr_info")),
            _clean(it.get("video_info")),
        ]
        joined = "\n".join(p for p in parts if p)
        if joined:
            blocks.append(joined)
    return "\n---\n".join(blocks)


def _flatten_user_behaviour(items: Any) -> str:
    out: list[str] = []
    for it in items or []:
        if isinstance(it, dict) and it.get("next_query"):
            cnt = it.get("count")
            out.append(f"{it['next_query']}（{cnt}）" if cnt is not None else str(it["next_query"]))
        elif isinstance(it, str) and it.strip():
            out.append(it.strip())
    return "、".join(out)


def _flatten_related_blogs(items: Any) -> str:
    lines: list[str] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        content = _clean(it.get("content"))
        if content:
            lines.append(f"- {content}")
    return "\n".join(lines)


def flatten_material(record: dict[str, Any]) -> str:
    """把 qinglong 输出的一条结构化物料拼成一段带小标题的文本（非空字段按固定顺序）。"""
    if not isinstance(record, dict):
        return ""

    nick = _clean(record.get("nick"))
    p_time = _clean(record.get("p_time"))
    post_info = " · ".join(p for p in (nick, p_time) if p)

    sections = [
        _section("博文正文", _clean(record.get("mid_content"))),
        _section("发博信息", post_info),
        _section("类别标签", _clean(record.get("sence_tag")) if record.get("sence_tag") not in (None, "", "其他") else ""),
        _section("博文总结", _clean(record.get("blog_summary"))),
        _section("视频总结", _clean(record.get("video_info")) or _clean(record.get("video_summary"))),
        _section("音转文", _clean(record.get("voice2text"))),
        _section("图片OCR", _clean(record.get("pic_info")) or _clean(record.get("pic_ocr_info"))),
        _section("图片分析", _flatten_pic_analysis(record.get("pid_desc_analysis_order"))),
        _section("评论总结", _clean(record.get("comment_summary"))),
        _section("智汇总结", _clean(record.get("aigc_abstract"))),
        _section("博文视频/图片及评论概要", _clean(record.get("blog_video_pic_comment"))),
        _section("转发原博", _flatten_reposted(record.get("reposted_blog"))),
        _section("人物智搜结果", _clean(record.get("user_zhisou"))),
        _section("热搜Query", _clean(record.get("hot_mid_query"))),
        _section("热搜智搜结果", _clean(record.get("hot_mid_search_zhisou"))),
        _section("相关博文", _flatten_related_blogs(record.get("tag_blog")) or _flatten_related_blogs(record.get("m3_blog"))),
        _section("用户追问行为", _flatten_user_behaviour(record.get("user_behaviour"))),
    ]
    return "\n\n".join(s for s in sections if s).strip()


def _material_meta(record: dict[str, Any]) -> dict[str, Any]:
    """详情页展示用的小字段子集，避免把整条大 JSON 塞进快照。"""
    return {
        "nick": _clean(record.get("nick")),
        "p_time": _clean(record.get("p_time")),
        "sence_tag": _clean(record.get("sence_tag")),
        "has_video": bool(_clean(record.get("video_info")) or _clean(record.get("video_summary"))),
        "pic_count": len(record.get("pid_desc_analysis_order") or []),
        "reposted": bool(record.get("reposted_blog")),
    }


# ---------------------------------------------------------------------------
# qinglong 子进程编排
# ---------------------------------------------------------------------------

def _count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _run_step(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    watch: Path,
    total: int,
    phase: str,
    progress_cb: Optional[ProgressCb],
    log,
) -> None:
    """跑一段 qinglong 子进程；跑的过程中按 watch 文件行数回报进度。"""
    deadline = time.monotonic() + config.WEIBO_CONVERT_TIMEOUT_SEC
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    tail: list[str] = []

    def _drain() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            tail.append(line.rstrip())
            del tail[:-40]

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()

    while proc.poll() is None:
        if progress_cb:
            progress_cb(min(total, _count_lines(watch)), phase)
        if time.monotonic() > deadline:
            proc.kill()
            raise WeiboConvertError(f"{phase} 超时（>{config.WEIBO_CONVERT_TIMEOUT_SEC}s）")
        time.sleep(2)

    reader.join(timeout=5)
    if proc.returncode != 0:
        raise WeiboConvertError(f"{phase} 子进程退出码 {proc.returncode}：{' / '.join(tail[-8:])}")
    if progress_cb:
        progress_cb(min(total, _count_lines(watch)), phase)
    if log:
        log.info("qinglong %s done: %s 行", phase, _count_lines(watch))


def _pipeline(mids: list[str], progress_cb: Optional[ProgressCb], log) -> dict[str, dict[str, Any]]:
    """跑完整 qinglong 流水线，返回 {mid: 结构化物料记录}。"""
    qinglong_dir = config.WEIBO_QINGLONG_DIR
    if not (Path(qinglong_dir) / "bin" / "make_data.py").is_file():
        raise WeiboConvertError(f"未找到 qinglong 流水线目录：{qinglong_dir}（配置 WEIBO_QINGLONG_DIR）")

    workdir = Path(tempfile.mkdtemp(prefix="weibo-convert-"))
    try:
        src = workdir / "mids.txt"
        src.write_text("\n".join(mids), encoding="utf-8")
        stage1 = workdir / "stage1.jsonl"
        stage2 = workdir / "stage2.jsonl"

        base_env = {
            **os.environ,
            "QINGLONG_SOURCE": str(src),
            "QINGLONG_TARGET": str(stage1),
            "QINGLONG_CONCURRENCY": str(config.WEIBO_CONVERT_CONCURRENCY),
            "PYTHONUNBUFFERED": "1",
        }
        if config.WEIBO_QINGLONG_BASE_PATH:
            base_env["QINGLONG_BASE_PATH"] = config.WEIBO_QINGLONG_BASE_PATH

        py = config.WEIBO_QINGLONG_PYTHON
        _run_step(
            [py, "-m", "bin.make_data"], cwd=qinglong_dir, env=base_env,
            watch=stage1, total=len(mids), phase="抓取物料", progress_cb=progress_cb, log=log,
        )
        _run_step(
            [py, "-m", "bin.process_data"], cwd=qinglong_dir,
            env={**base_env, "QINGLONG_INPUT": str(stage1), "QINGLONG_OUTPUT": str(stage2)},
            watch=stage2, total=len(mids), phase="图片分析", progress_cb=progress_cb, log=log,
        )

        out = stage2 if stage2.is_file() else stage1
        records: dict[str, dict[str, Any]] = {}
        with out.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mid = str(rec.get("mid") or "").strip()
                if mid:
                    records[mid] = rec
        return records
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _stub_records(mids: list[str]) -> dict[str, dict[str, Any]]:
    return {
        mid: {"mid": mid, "mid_content": f"(占位物料 mid={mid}，WEIBO_CONVERT_STUB 已开启)"}
        for mid in mids
    }


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

def convert_rows(
    rows: list[dict[str, str]],
    *,
    progress_cb: Optional[ProgressCb] = None,
    log=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """mid 行 → 样本。

    rows: [{"mid": "...", "content": "智搜结果原文"}]（按上传顺序）
    返回 (samples, failed)：
      samples[i] = {id,row_index,mid,query(物料文本),content(智搜结果),material_status,material_meta}
      failed[i]  = {mid,row_index,error}
    失败项以空 query 占位保留（用户确认策略）。
    """
    mids = [r["mid"] for r in rows]
    if config.WEIBO_CONVERT_STUB:
        records = _stub_records(mids)
    else:
        records = _pipeline(mids, progress_cb, log)

    samples: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        mid = row["mid"]
        rec = records.get(mid)
        err = (rec or {}).get("_error") if rec else "未返回该 mid 的物料"
        material = flatten_material(rec) if rec and not rec.get("_error") else ""
        if not material and not err:
            err = "物料为空"
        status = "OK" if material else "FAILED"
        if status == "FAILED":
            failed.append({"mid": mid, "row_index": i, "error": str(err or "解析失败")})
        samples.append(
            {
                "id": f"item-{i}",
                "row_index": i,
                "mid": mid,
                "query": material,
                "content": row.get("content", ""),
                "baseline": "",
                "material_status": status,
                "material_meta": _material_meta(rec) if rec else {},
            }
        )
    return samples, failed
