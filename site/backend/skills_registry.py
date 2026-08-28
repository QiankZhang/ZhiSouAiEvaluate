"""技能包解析 + 内置技能注册表。

技能遵循 Anthropic Agent Skills 规范：SKILL.md 为入口，文件头是 --- 包裹的 YAML
frontmatter（必须含 name 与 description），其后为 Markdown 正文，包内可带附加脚本。

平台内置三个技能（随代码库分发，非运行时上传）：
- multi-dimension-evaluation：多维度加权打分
- gsb-evaluation：GSB 对比判定
- evaluation-report：评估总报告生成（作为内置报告器使用，见 report.py）
"""

import io
import re
import zipfile
from typing import Any, Optional

from . import config

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

BUILTIN_SKILL_IDS = ["multi-dimension-evaluation", "gsb-evaluation", "evaluation-report"]

# 评估方式（底层机制）→ 推荐内置技能
METHOD_TO_SKILL = {
    "MULTI_DIM": "multi-dimension-evaluation",
    "GSB": "gsb-evaluation",
}


def parse_skill_frontmatter(text: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """只支持扁平 key: value（含简单 [a, b] 列表），足以覆盖 SKILL.md 实际字段。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "SKILL.md 缺少 YAML frontmatter（文件需以 --- 开头）"
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, "SKILL.md 的 frontmatter 未正确闭合（缺少结尾的 ---）"

    meta: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value.strip("'\"")
    meta["_body"] = "\n".join(lines[end + 1 :]).strip()
    return meta, None


def validate_skill_meta(meta: dict[str, Any]) -> Optional[str]:
    name = str(meta.get("name", "")).strip()
    description = str(meta.get("description", "")).strip()
    if not name:
        return "SKILL.md frontmatter 缺少必需字段 name"
    if not SKILL_NAME_RE.match(name):
        return f"name 必须只包含小写字母/数字/连字符（如 my-skill），当前为「{name}」"
    if len(name) > 64:
        return "name 长度不能超过 64 个字符"
    if not description:
        return "SKILL.md frontmatter 缺少必需字段 description"
    if len(description) > 1024:
        return "description 长度不能超过 1024 个字符"
    return None


def _skill_from_meta(meta: dict[str, Any], *, files: list[str], source_filename: str) -> dict[str, Any]:
    return {
        "name": meta["name"],
        "description": meta["description"],
        "instructions": meta["_body"],
        "license": meta.get("license", ""),
        "version": meta.get("version", ""),
        "allowed_tools": meta.get("allowed-tools", []),
        "files": files,
        "source_filename": source_filename,
    }


def parse_skill_package(raw: bytes, filename: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """解析上传的技能包：.zip（根目录含 SKILL.md）或单个 SKILL.md / .md 文件。"""
    lower = filename.lower()
    if lower.endswith(".zip"):
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            return None, "文件损坏：不是有效的 zip 压缩包"
        names = zf.namelist()
        skill_entry = next((n for n in names if n.rstrip("/").split("/")[-1] == "SKILL.md"), None)
        if not skill_entry:
            return None, "压缩包中未找到 SKILL.md（Anthropic Skill 规范要求包内必须有 SKILL.md）"
        try:
            text = zf.read(skill_entry).decode("utf-8")
        except UnicodeDecodeError:
            return None, "SKILL.md 编码不支持，请使用 UTF-8"
        meta, err = parse_skill_frontmatter(text)
        if err:
            return None, err
        err = validate_skill_meta(meta)
        if err:
            return None, err
        files = sorted(n for n in names if not n.endswith("/") and n != skill_entry)
        return _skill_from_meta(meta, files=files, source_filename=filename), None

    if lower.endswith(".md"):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None, "文件编码不支持，请使用 UTF-8"
        meta, err = parse_skill_frontmatter(text)
        if err:
            return None, err
        err = validate_skill_meta(meta)
        if err:
            return None, err
        return _skill_from_meta(meta, files=[], source_filename=filename), None

    return None, "不支持的文件格式，请上传技能包 .zip 或 SKILL.md 文件"


def load_builtin_skill(skill_id: str) -> dict[str, Any]:
    """从仓库 skills/<id>/SKILL.md 读取内置技能，返回与 parse_skill_package 同构的 dict，
    额外带 source='builtin' 与 skill_dir（脚本执行时定位用）。"""
    if skill_id not in BUILTIN_SKILL_IDS:
        raise KeyError(f"未知内置技能：{skill_id}")
    skill_dir = config.SKILLS_DIR / skill_id
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"内置技能文件缺失：{skill_md}")
    meta, err = parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"))
    if err or (err := validate_skill_meta(meta)):
        raise ValueError(f"内置技能 {skill_id} 解析失败：{err}")
    files = sorted(
        str(p.relative_to(skill_dir))
        for p in skill_dir.rglob("*")
        if p.is_file() and p.name != "SKILL.md" and not p.name.startswith(".")
    )
    skill = _skill_from_meta(meta, files=files, source_filename=f"{skill_id}/SKILL.md")
    skill["source"] = "builtin"
    skill["skill_dir"] = str(skill_dir)
    skill["skill_id"] = skill_id
    return skill


def list_builtin() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid in BUILTIN_SKILL_IDS:
        try:
            s = load_builtin_skill(sid)
        except (KeyError, FileNotFoundError, ValueError):
            continue
        out.append(
            {
                "skill_id": sid,
                "name": s["name"],
                "description": s["description"],
                "version": s["version"],
                "license": s["license"],
                "allowed_tools": s["allowed_tools"],
                "files": s["files"],
                "instructions": s["instructions"],
                "recommended_for": next((m for m, v in METHOD_TO_SKILL.items() if v == sid), None),
            }
        )
    return out
