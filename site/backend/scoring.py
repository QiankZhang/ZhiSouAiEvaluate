"""维度分制与聚合的统一实现（多维度评估基准自由度优化，见仓库根 `多维度评估基准优化设计.md`）。

一处收敛「维度分制、每档标准、聚合方式、一票否决」的换算规则，供三方共用：
- `engine.py`：真实裁判员的提示词组装、分值校验、总分重算
- `main.py::_evaluate_item`：无 Key 时的确定性模拟引擎
- `report.py` / 前端：结果展示与统计（经由结果里冗余存下的 total_ratio）

设计要点：
- **超集 + 读时兼容**：旧维度（无 `scale`）按 1~5 整数处理；旧 `config`（无 `scoring`）
  按 `weighted_raw` 逐位还原当前 `Σ(score×weight)/100` 行为。
- 裁判员输出结构不变：`dimensions[].score` + 整体 `reason`，只是 `score` 取值域随维度声明变化。
"""

from typing import Any, Optional

# ---- 默认值（读时 shim 用）----

DEFAULT_SCALE: dict[str, Any] = {"type": "integer", "min": 1, "max": 5, "levels": []}

# 旧基准没有 config.scoring：weighted_raw 完全还原 `Σ(score×weight)/100`，展示满分 5，
# 低分阈值得分率 0.6（等价于旧的「总分 < 3.0」在 1~5 量纲上的位置）。
DEFAULT_SCORING: dict[str, Any] = {
    "mode": "weighted_raw",
    "display_scale": 5,
    "low_score_ratio": 0.6,
}

# GSB 判定的默认阈值：weighted_raw 沿用 1~5 量纲的 0.18；归一化模式用 0~1 量纲的 0.05。
_GSB_THRESHOLD_RAW = 0.18
_GSB_THRESHOLD_NORMALIZED = 0.05

VALID_MODES = {"weighted_raw", "weighted_normalized", "threshold"}


# ---- 维度归一化 ----

def normalize_dimension(dim: dict[str, Any]) -> dict[str, Any]:
    """补全维度的 `scale` 字段，不改动调用方原对象。"""
    d = dict(dim)
    scale = d.get("scale")
    if not isinstance(scale, dict) or not scale.get("type"):
        # 旧维度：1~5 整数，用一句 criteria 生成「满分档」说明
        crit = str(d.get("criteria") or "").strip()
        levels = [{"value": 5, "label": "", "criteria": crit}] if crit else []
        d["scale"] = {"type": "integer", "min": 1, "max": 5, "levels": levels}
        return d

    stype = scale.get("type")
    if stype == "integer":
        lo = int(scale.get("min", 1))
        hi = int(scale.get("max", 5))
        if hi <= lo:
            hi = lo + 1
        levels = [
            {"value": int(lv["value"]), "label": str(lv.get("label", "")), "criteria": str(lv.get("criteria", ""))}
            for lv in (scale.get("levels") or [])
            if isinstance(lv, dict) and "value" in lv
        ]
        d["scale"] = {"type": "integer", "min": lo, "max": hi, "levels": levels}
    elif stype == "enum":
        levels = []
        for lv in scale.get("levels") or []:
            if not isinstance(lv, dict) or "value" not in lv:
                continue
            entry = {"value": str(lv["value"]), "label": str(lv.get("label", "")), "criteria": str(lv.get("criteria", ""))}
            if lv.get("score") is not None:
                try:
                    entry["score"] = float(lv["score"])
                except (TypeError, ValueError):
                    pass
            levels.append(entry)
        d["scale"] = {"type": "enum", "levels": levels}
    else:
        d["scale"] = dict(DEFAULT_SCALE)
    return d


def normalize_scoring(config: dict[str, Any]) -> dict[str, Any]:
    """补全 `config.scoring`。"""
    raw = config.get("scoring") if isinstance(config.get("scoring"), dict) else {}
    scoring = {**DEFAULT_SCORING, **raw}
    if scoring.get("mode") not in VALID_MODES:
        scoring["mode"] = DEFAULT_SCORING["mode"]
    try:
        scoring["display_scale"] = scoring.get("display_scale") or 5
    except Exception:
        scoring["display_scale"] = 5
    try:
        scoring["low_score_ratio"] = float(scoring.get("low_score_ratio", 0.6))
    except (TypeError, ValueError):
        scoring["low_score_ratio"] = 0.6
    if scoring.get("gsb_good_threshold") is None:
        scoring["gsb_good_threshold"] = (
            _GSB_THRESHOLD_RAW if scoring["mode"] == "weighted_raw" else _GSB_THRESHOLD_NORMALIZED
        )
    if not isinstance(scoring.get("grade_thresholds"), list):
        scoring["grade_thresholds"] = []
    return scoring


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """就地补全 `config`：每个维度补 `scale`，补 `scoring`。返回同一对象。"""
    dims = config.get("dimensions") or []
    config["dimensions"] = [normalize_dimension(d) for d in dims]
    config["scoring"] = normalize_scoring(config)
    return config


# ---- 单维度换算 ----

def scale_of(dim: dict[str, Any]) -> dict[str, Any]:
    return normalize_dimension(dim)["scale"]


def allowed_values(dim: dict[str, Any]) -> list[Any]:
    s = scale_of(dim)
    if s["type"] == "enum":
        return [lv["value"] for lv in s["levels"]]
    return list(range(s["min"], s["max"] + 1))


def score_domain_text(dim: dict[str, Any]) -> str:
    """给裁判员提示词用的取值域说明。"""
    s = scale_of(dim)
    if s["type"] == "enum":
        return "、".join(f'"{v}"' for v in allowed_values(dim)) + " 之一"
    return f"{s['min']}~{s['max']} 的整数"


def coerce_score(dim: dict[str, Any], raw: Any) -> Any:
    """把裁判员给的原始分收敛到合法取值；非法则抛 ValueError（触发引擎轻量重试）。"""
    s = scale_of(dim)
    if s["type"] == "enum":
        raw_str = str(raw).strip()
        valid = allowed_values(dim)
        if raw_str in valid:
            return raw_str
        # 容错：大小写不敏感命中
        for v in valid:
            if raw_str.lower() == str(v).lower():
                return v
        raise ValueError(f"维度 {dim.get('key')} 枚举值非法：{raw!r}（合法：{valid}）")
    try:
        val = int(round(float(raw)))
    except (TypeError, ValueError):
        raise ValueError(f"维度 {dim.get('key')} 分值非数字：{raw!r}")
    return max(s["min"], min(s["max"], val))


def numeric_score(dim: dict[str, Any], value: Any) -> Optional[float]:
    """维度得分 → 数值分（用于加权 / 否决判断）。枚举型无 `score` 映射时返回 None（不参与总分）。"""
    s = scale_of(dim)
    if s["type"] == "enum":
        for lv in s["levels"]:
            if str(lv["value"]) == str(value):
                return lv.get("score")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enum_score_span(dim: dict[str, Any]) -> Optional[tuple[float, float]]:
    scores = [lv["score"] for lv in scale_of(dim)["levels"] if lv.get("score") is not None]
    if len(scores) < 2:
        return None
    return min(scores), max(scores)


def ratio_of(dim: dict[str, Any], value: Any) -> Optional[float]:
    """维度得分归一到 0~1。无法归一（枚举缺 score）时返回 None。"""
    s = scale_of(dim)
    num = numeric_score(dim, value)
    if num is None:
        return None
    if s["type"] == "enum":
        span = _enum_score_span(dim)
        if not span:
            return None
        lo, hi = span
    else:
        lo, hi = float(s["min"]), float(s["max"])
    if hi <= lo:
        return 1.0
    return max(0.0, min(1.0, (num - lo) / (hi - lo)))


def _weight(dim: dict[str, Any]) -> float:
    try:
        return float(dim.get("weight") or 0)
    except (TypeError, ValueError):
        return 0.0


# ---- 一票否决 ----

def veto_dimension(dims: list[dict[str, Any]], scores_by_key: dict[str, Any]) -> Optional[str]:
    """返回第一个触发一票否决的维度 name；没有则 None。"""
    for d in dims:
        thr = d.get("veto_below")
        if thr is None or d["key"] not in scores_by_key:
            continue
        num = numeric_score(d, scores_by_key[d["key"]])
        if num is not None and num < float(thr):
            return d.get("name", d["key"])
    return None


# ---- 聚合 ----

def grade_label(total_ratio: float, scoring: dict[str, Any]) -> Optional[str]:
    """按 grade_thresholds（min_ratio 从高到低）给出档位名。"""
    thresholds = sorted(scoring.get("grade_thresholds") or [], key=lambda t: -float(t.get("min_ratio", 0)))
    for t in thresholds:
        if total_ratio >= float(t.get("min_ratio", 0)):
            return str(t.get("label", ""))
    return None


def aggregate(
    dims: list[dict[str, Any]],
    scores_by_key: dict[str, Any],
    scoring: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """把逐维度得分聚合成整体结果。

    返回 `{total, total_ratio, vetoed, grade_label}`：
    - `total`：对外展示的总分（量纲由 mode / display_scale 决定）
    - `total_ratio`：0~1 的归一总分（报告统计、GSB 判定用）
    - `vetoed`：触发一票否决的维度 name 或 None
    - `grade_label`：命中的档位名或 None
    """
    scoring = scoring or dict(DEFAULT_SCORING)
    mode = scoring.get("mode", "weighted_raw")
    display_scale = float(scoring.get("display_scale") or 5)

    # 归一化加权（所有模式都算，供报告与档位判定）
    num, den = 0.0, 0.0
    equal_weight = all(_weight(d) == 0 for d in dims)
    for d in dims:
        if d["key"] not in scores_by_key:
            continue
        r = ratio_of(d, scores_by_key[d["key"]])
        if r is None:
            continue
        w = 1.0 if equal_weight else _weight(d)
        num += r * w
        den += w
    total_ratio = round(num / den, 4) if den else 0.0

    vetoed = veto_dimension(dims, scores_by_key)
    if vetoed:
        total_ratio = 0.0

    if mode == "weighted_raw":
        # 旧公式逐位还原：Σ(score × weight) / 100
        raw = sum(
            (numeric_score(d, scores_by_key[d["key"]]) or 0) * _weight(d)
            for d in dims
            if d["key"] in scores_by_key
        )
        total = round(raw / 100.0, 2)
        if vetoed:
            total = round(
                sum(float(scale_of(d)["min"]) * _weight(d) for d in dims if scale_of(d)["type"] == "integer") / 100.0,
                2,
            )
    else:
        total = round(total_ratio * display_scale, 2)

    return {
        "total": total,
        "total_ratio": total_ratio,
        "vetoed": vetoed,
        "grade_label": grade_label(total_ratio, scoring),
    }


def gsb_judgment(exp: dict[str, Any], base: dict[str, Any], scoring: dict[str, Any]) -> tuple[str, float]:
    """按聚合结果判 Good / Same / Bad。返回 (判定, diff)。"""
    threshold = float(scoring.get("gsb_good_threshold", _GSB_THRESHOLD_NORMALIZED))
    if scoring.get("mode") == "weighted_raw":
        diff = round(exp["total"] - base["total"], 2)
    else:
        diff = round(exp["total_ratio"] - base["total_ratio"], 4)
    if diff > threshold:
        return "Good", diff
    if diff < -threshold:
        return "Bad", diff
    return "Same", diff
