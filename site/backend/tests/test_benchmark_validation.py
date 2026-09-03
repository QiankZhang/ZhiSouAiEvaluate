"""评估基准维度分制 / 聚合配置的入口校验（main._validate_benchmark_scoring）。"""

import pytest
from fastapi import HTTPException

from backend import main, scoring


def _sc(**kw):
    return scoring.normalize_scoring({"scoring": kw})


def test_accepts_custom_scale_with_veto():
    dims = [
        {"key": "fact", "name": "事实", "weight": 50, "veto_below": 2,
         "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
        {"key": "concision", "name": "去冗", "weight": 50,
         "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
    ]
    main._validate_benchmark_scoring(dims, _sc(mode="weighted_normalized"))  # 不抛


def test_rejects_weight_sum_not_100():
    dims = [{"key": "a", "name": "A", "weight": 30, "scale": {"type": "integer", "min": 1, "max": 5, "levels": []}}]
    with pytest.raises(HTTPException) as e:
        main._validate_benchmark_scoring(dims, _sc(mode="weighted_normalized"))
    assert e.value.status_code == 422


def test_allows_equal_weight_zero_sum():
    dims = [
        {"key": "a", "name": "A", "weight": 0, "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
        {"key": "b", "name": "B", "weight": 0, "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
    ]
    main._validate_benchmark_scoring(dims, _sc(mode="weighted_normalized"))


def test_weighted_raw_rejects_mixed_scale():
    dims = [
        {"key": "a", "name": "A", "weight": 50, "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}},
        {"key": "b", "name": "B", "weight": 50, "scale": {"type": "integer", "min": 1, "max": 5, "levels": []}},
    ]
    with pytest.raises(HTTPException):
        main._validate_benchmark_scoring(dims, _sc(mode="weighted_raw"))


def test_rejects_bad_veto_threshold():
    dims = [{"key": "a", "name": "A", "weight": 100, "veto_below": 9,
             "scale": {"type": "integer", "min": 0, "max": 3, "levels": []}}]
    with pytest.raises(HTTPException):
        main._validate_benchmark_scoring(dims, _sc(mode="weighted_normalized"))


def test_rejects_enum_with_one_value():
    dims = [{"key": "a", "name": "A", "weight": 100,
             "scale": {"type": "enum", "levels": [{"value": "G"}]}}]
    with pytest.raises(HTTPException):
        main._validate_benchmark_scoring(dims, _sc(mode="weighted_normalized"))
