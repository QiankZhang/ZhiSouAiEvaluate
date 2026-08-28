#!/usr/bin/env python3
"""weighted_score.py — 多维度评估加权总分计算器。

用法：
    python3 weighted_score.py < input.json
    echo '[{"key":"relevance","score":4,"weight":30}]' | python3 weighted_score.py

stdin 传入 JSON 数组，每项形如 {"key": str, "score": 1~5, "weight": number}。
输出：加权总分，保留 2 位小数（恒除以 100，不做归一化；
权重合计不等于 100 时向 stderr 输出警告，仍按原权重计算）。
"""

import json
import sys

SCORE_MIN, SCORE_MAX = 1, 5


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: empty stdin", file=sys.stderr)
        return 1

    try:
        dims = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(dims, list) or not dims:
        print("ERROR: expected non-empty JSON array", file=sys.stderr)
        return 1

    acc = 0.0
    total_weight = 0.0
    for i, item in enumerate(dims):
        if not isinstance(item, dict):
            print(f"ERROR: item {i} is not an object", file=sys.stderr)
            return 1
        try:
            score = int(item["score"])
            weight = float(item["weight"])
        except (KeyError, TypeError, ValueError):
            print(f"ERROR: item {i} missing/invalid 'score' or 'weight'", file=sys.stderr)
            return 1
        if not SCORE_MIN <= score <= SCORE_MAX:
            print(f"ERROR: item {i} score {score} out of range {SCORE_MIN}-{SCORE_MAX}", file=sys.stderr)
            return 1
        acc += score * weight
        total_weight += weight

    if total_weight == 0:
        print("ERROR: total weight is 0", file=sys.stderr)
        return 1

    if abs(total_weight - 100.0) > 1e-9:
        print(f"WARNING: total weight {total_weight:g} != 100, result not normalized", file=sys.stderr)

    print(f"{acc / 100.0:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
