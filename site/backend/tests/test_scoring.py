"""维度分制与聚合（scoring.py）。"""

import pytest

from backend import scoring

# 旧维度（无 scale）→ 1~5 整数
LEGACY_DIMS = [
    {"key": "relevance", "name": "相关性", "weight": 60, "criteria": "命中意图"},
    {"key": "quality", "name": "质量", "weight": 40},
]

# 博文总结式：0~3 四档 + 一票否决
BLOG_DIMS = [
    {
        "key": "fact", "name": "事实一致性", "weight": 30, "veto_below": 2,
        "scale": {"type": "integer", "min": 0, "max": 3, "levels": [
            {"value": 3, "label": "无损", "criteria": "完美"},
            {"value": 0, "label": "指鹿为马", "criteria": "跑题"},
        ]},
    },
    {"key": "concision", "name": "极简去冗", "weight": 40, "veto_below": 1,
     "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
    {"key": "scan", "name": "结构扫读", "weight": 30, "veto_below": 1,
     "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
]

ENUM_DIMS = [
    {"key": "verdict", "name": "判定", "weight": 100, "scale": {"type": "enum", "levels": [
        {"value": "G", "label": "更好", "score": 5},
        {"value": "S", "label": "持平", "score": 3},
        {"value": "B", "label": "更差", "score": 1},
    ]}},
]


def test_normalize_legacy_dimension_defaults_to_1_5():
    d = scoring.normalize_dimension(LEGACY_DIMS[0])
    assert d["scale"] == {"type": "integer", "min": 1, "max": 5,
                          "levels": [{"value": 5, "label": "", "criteria": "命中意图"}]}


def test_weighted_raw_matches_legacy_formula():
    # 4*60 + 3*40 = 360 → /100 = 3.6，与旧 Σ(score×weight)/100 一致
    agg = scoring.aggregate(LEGACY_DIMS, {"relevance": 4, "quality": 3}, scoring.normalize_scoring({}))
    assert agg["total"] == 3.6
    assert agg["vetoed"] is None


def test_weighted_normalized_mixed_scale():
    dims = [
        {"key": "a", "name": "A", "weight": 50, "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
        {"key": "b", "name": "B", "weight": 50, "scale": {"type": "integer", "min": 1, "max": 5, "levels": []}},
    ]
    sc = scoring.normalize_scoring({"scoring": {"mode": "weighted_normalized", "display_scale": 100}})
    # a=3 → ratio 1.0；b=3 → ratio 0.5 → 加权 0.75 → 展示 75
    agg = scoring.aggregate(dims, {"a": 3, "b": 3}, sc)
    assert agg["total_ratio"] == 0.75
    assert agg["total"] == 75.0


def test_veto_forces_zero():
    sc = scoring.normalize_scoring({"scoring": {"mode": "weighted_normalized", "display_scale": 3}})
    agg = scoring.aggregate(BLOG_DIMS, {"fact": 1, "concision": 3, "scan": 3}, sc)  # fact=1 < veto 2
    assert agg["vetoed"] == "事实一致性"
    assert agg["total_ratio"] == 0.0
    assert agg["total"] == 0.0


def test_no_veto_when_above_threshold():
    sc = scoring.normalize_scoring({"scoring": {"mode": "weighted_normalized"}})
    agg = scoring.aggregate(BLOG_DIMS, {"fact": 2, "concision": 2, "scan": 2}, sc)
    assert agg["vetoed"] is None
    assert agg["total_ratio"] == pytest.approx(2 / 3, abs=1e-3)


def test_grade_thresholds():
    sc = scoring.normalize_scoring({"scoring": {
        "mode": "threshold",
        "grade_thresholds": [
            {"min_ratio": 0.9, "label": "3档"},
            {"min_ratio": 0.6, "label": "2档"},
            {"min_ratio": 0.0, "label": "1档"},
        ],
    }})
    assert scoring.aggregate(BLOG_DIMS, {"fact": 3, "concision": 3, "scan": 3}, sc)["grade_label"] == "3档"
    assert scoring.aggregate(BLOG_DIMS, {"fact": 2, "concision": 2, "scan": 2}, sc)["grade_label"] == "2档"
    assert scoring.aggregate(BLOG_DIMS, {"fact": 3, "concision": 0, "scan": 3}, sc)["grade_label"] == "1档"  # veto → 0.0


def test_coerce_score_integer_clamps():
    d = scoring.normalize_dimension(BLOG_DIMS[0])
    assert scoring.coerce_score(d, 9) == 3
    assert scoring.coerce_score(d, -1) == 0
    assert scoring.coerce_score(d, "2") == 2


def test_coerce_score_enum_validates():
    d = scoring.normalize_dimension(ENUM_DIMS[0])
    assert scoring.coerce_score(d, "g") == "G"
    with pytest.raises(ValueError):
        scoring.coerce_score(d, "X")


def test_enum_aggregation_uses_score_map():
    sc = scoring.normalize_scoring({"scoring": {"mode": "weighted_normalized", "display_scale": 5}})
    agg = scoring.aggregate(ENUM_DIMS, {"verdict": "G"}, sc)
    assert agg["total_ratio"] == 1.0 and agg["total"] == 5.0
    agg2 = scoring.aggregate(ENUM_DIMS, {"verdict": "S"}, sc)
    assert agg2["total_ratio"] == 0.5


def test_gsb_judgment_weighted_raw_backcompat():
    sc = scoring.normalize_scoring({})  # weighted_raw, threshold 0.18 on total
    exp = scoring.aggregate(LEGACY_DIMS, {"relevance": 5, "quality": 5}, sc)
    base = scoring.aggregate(LEGACY_DIMS, {"relevance": 3, "quality": 3}, sc)
    assert scoring.gsb_judgment(exp, base, sc)[0] == "Good"
    same = scoring.aggregate(LEGACY_DIMS, {"relevance": 4, "quality": 4}, sc)
    assert scoring.gsb_judgment(same, same, sc)[0] == "Same"


def test_equal_weight_when_all_zero():
    dims = [
        {"key": "a", "name": "A", "scale": {"type": "integer", "min": 0, "max": 2, "levels": []}},
        {"key": "b", "name": "B", "scale": {"type": "integer", "min": 0, "max": 2, "levels": []}},
    ]
    sc = scoring.normalize_scoring({"scoring": {"mode": "weighted_normalized"}})
    agg = scoring.aggregate(dims, {"a": 2, "b": 0}, sc)
    assert agg["total_ratio"] == 0.5  # 等权
