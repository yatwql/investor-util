"""申购可行性判定边缘样本 — 负金额 / 0 限额 / 非有限数 / 超大额 / 极小金额。

设计文档 docs/plan/fund-purchase-limit-advice-design.md §3.2 防御规则：
amount <= 0 或 limit 非正一律视为未知（days=None）——宁缺毋错。
"""

from __future__ import annotations

import pytest

from src.python.analysis.purchase_feasibility import (
    FEASIBILITY_MAX_DAYS,
    evaluate_purchase_feasibility,
)

pytestmark = [pytest.mark.edge, pytest.mark.unit, pytest.mark.unit_analysis]


def _index(limit: float | None = 100.0, status: str = "限大额") -> dict:
    return {
        "519674": {
            "code": "519674",
            "status": status,
            "limit": limit,
            "limit_text": "限额未知" if limit is None else "100",
            "next_open_text": "",
            "level": "fresh",
        }
    }


class TestNonPositiveInputs:
    """非正输入 → 视为未知，不给天数。"""

    @pytest.mark.parametrize("amount", [0, -1, -0.01])
    def test_non_positive_amount_no_days(self, amount: float):
        result = evaluate_purchase_feasibility("519674", float(amount), _index())
        assert result is not None
        assert result["kind"] == "limited"
        assert result["days"] is None
        assert result["feasible"] is None

    @pytest.mark.parametrize("limit", [0, -100])
    def test_non_positive_limit_no_days(self, limit: float):
        result = evaluate_purchase_feasibility("519674", 1000.0, _index(limit=float(limit)))
        assert result is not None
        assert result["days"] is None
        assert result["feasible"] is None


class TestNonFiniteAmount:
    """非有限金额（NaN/Inf）→ 防御为未知，不产生垃圾天数。"""

    @pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_amount_no_days(self, amount: float):
        result = evaluate_purchase_feasibility("519674", amount, _index())
        assert result is not None
        assert result["days"] is None
        assert result["feasible"] is None


class TestExtremeMagnitude:
    """极端金额量级。"""

    def test_huge_amount_infeasible(self):
        """超大额（100 亿元 ÷ 100 元/日）→ 天数远超阈值 → 不可行。"""
        result = evaluate_purchase_feasibility("519674", 10_000_000_000.0, _index(limit=100.0))
        assert result is not None
        assert result["days"] == 100_000_000
        assert result["feasible"] is False
        assert result["days"] > FEASIBILITY_MAX_DAYS

    def test_tiny_amount_one_day(self):
        """极小金额（0.01 元 ÷ 100 元/日）→ 上取整 1 个交易日。"""
        result = evaluate_purchase_feasibility("519674", 0.01, _index(limit=100.0))
        assert result is not None
        assert result["days"] == 1
        assert result["feasible"] is True
