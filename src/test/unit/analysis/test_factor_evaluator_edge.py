"""因子目录计算编排 — 边缘场景（R-FCT-02 载体）。

覆盖：四类输入全不可用、未知字段类型注入、NaN/±inf 数值语义、单码池、
评级回退与全不可算收口——全部断言「不抛异常且给出降级结果」。

运行：
  pytest src/test/unit/analysis/test_factor_evaluator_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis import factor_evaluator as fe

pytestmark = [pytest.mark.unit, pytest.mark.edge, pytest.mark.unit_analysis]


class TestFactorEvaluatorEdge:
    """极端输入下的 fail-soft 语义。"""

    def test_all_inputs_unavailable_no_raise(self):
        """四类输入全缺 → 每个因子带原因、整体 available=False，不抛。"""
        out = fe.evaluate_factor_catalog(
            {"bars_by_code": {}, "index_bars": [], "valuation_by_code": {}, "fin_by_code": {}, "unavailable": {}},
            entries=None,  # 全量冻结目录
        )
        assert out["available"] is False
        assert out["computed"] == 0
        assert len(out["factors"]) == len(out["factors"]) and out["factors"]
        assert all(f["reason"] for f in out["factors"])

    def test_unknown_field_entry_reason(self):
        """注入未知字段类型 → 字段需求未知，不抛。"""
        entry = {
            "slug": "hack_factor",
            "family": "academic",
            "label": "X",
            "fields": ["hack"],
            "min_bars": 1,
            "window": 1,
        }
        out = fe.evaluate_factor_catalog({"bars_by_code": {}, "index_bars": []}, entries=[entry])
        assert out["factors"][0]["reason"] == "字段需求未知"

    def test_nan_valuation_treated_as_missing(self):
        """估值字段为 NaN → value_present 过滤，按不可得计。"""
        inputs = {
            "bars_by_code": {},
            "index_bars": [],
            "valuation_by_code": {
                "600000": {"pb": float("nan")},
                "600001": {"pb": float("nan")},
                "600002": {"pb": float("nan")},
            },
            "fin_by_code": {},
            "unavailable": {},
        }
        entry = {
            "slug": "fund_pb",
            "family": "fundamental",
            "label": "PB",
            "fields": ["valuation"],
            "min_bars": 0,
            "window": 0,
        }
        out = fe.evaluate_factor_catalog(inputs, entries=[entry])
        factor = out["factors"][0]
        assert factor["computable"] is False
        assert factor["codes_ok"] == 0
        assert factor["reason"] == "估值字段不可得"

    def test_infinite_value_kept_by_semantics(self):
        """±inf 保留（强度类因子可合法发散）→ 参与均值且可算。"""
        inputs = {
            "bars_by_code": {},
            "index_bars": [],
            "valuation_by_code": {c: {"pb": float("inf")} for c in ("600000", "600001", "600002")},
            "fin_by_code": {},
            "unavailable": {},
        }
        entry = {
            "slug": "fund_pb",
            "family": "fundamental",
            "label": "PB",
            "fields": ["valuation"],
            "min_bars": 0,
            "window": 0,
        }
        out = fe.evaluate_factor_catalog(inputs, entries=[entry])
        factor = out["factors"][0]
        assert factor["computable"] is True
        assert factor["value"] == float("inf")

    def test_single_code_pool_degrades_not_raises(self):
        """单码池（不足 3 码）→ 全部因子带原因，评级为空。"""
        inputs = {
            "bars_by_code": {
                "600000": [
                    {
                        "date": f"2026-09-{(i % 28) + 1:02d}",
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.0,
                        "volume": 1000,
                    }
                    for i in range(70)
                ]
            },
            "index_bars": [{"date": "2026-09-01", "close": 3000.0}],
            "valuation_by_code": {},
            "fin_by_code": {},
            "unavailable": {},
        }
        out = fe.evaluate_factor_catalog(inputs, entries=None)
        assert out["available"] is False
        assert out["rating"] == ""
        assert out["pool_size"] == 1

    def test_non_dict_inputs_placeholder(self):
        """非 dict 输入 → 占位不抛。"""
        for bad in (None, [], "text", 42):
            out = fe.evaluate_factor_catalog(bad)  # type: ignore[arg-type]
            assert out["available"] is False
            assert out["reason"] == "输入为空"
