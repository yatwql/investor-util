"""申购可行性判定测试 — 判定矩阵逐分支（限大额已知/未知、暂停、无判定、阈值两侧）。

对应设计文档 docs/plan/fund-purchase-limit-advice-design.md §3.2 判定矩阵；
异常/极端样本（负金额、0 限额、非有限数、超大额）见 test_purchase_feasibility_edge.py。
全程无网（索引为纯数据结构）。
"""

from __future__ import annotations

import pytest

from src.python.analysis.purchase_feasibility import (
    FEASIBILITY_MAX_DAYS,
    evaluate_purchase_feasibility,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _index(limit: float | None = 100.0, status: str = "限大额", **over) -> dict:
    """受限索引 fixture（与 build_restricted_index 字段同构）。"""
    entry = {
        "code": "519674",
        "status": status,
        "limit": limit,
        "limit_text": "限额未知" if limit is None else "100",
        "next_open_text": "",
        "level": "fresh",
    }
    entry.update(over)
    return {"519674": entry}


class TestNoDecision:
    """无判定即现网行为（零回归）的三种入口。"""

    def test_none_index_returns_none(self):
        assert evaluate_purchase_feasibility("519674", 1000.0, None) is None

    def test_empty_index_returns_none(self):
        assert evaluate_purchase_feasibility("519674", 1000.0, {}) is None

    def test_code_not_in_index_returns_none(self):
        """场内/查无此码：索引不含该 code → 无判定。"""
        assert evaluate_purchase_feasibility("600900", 1000.0, _index()) is None


class TestLimited:
    """限大额分支：天数估算与阈值判定。"""

    def test_known_amount_gives_days(self):
        result = evaluate_purchase_feasibility("519674", 1000.0, _index(limit=100.0))
        assert result is not None
        assert result["kind"] == "limited"
        assert result["days"] == 10
        assert result["feasible"] is True
        assert result["amount"] == pytest.approx(1000.0)
        # 预格式化字段值透传（消费方拼静态模板，不重算数值）
        assert result["limit_text"] == "100"
        assert result["status"] == "限大额"

    @pytest.mark.parametrize("amount", [59, 60, 61])
    def test_threshold_sides(self, amount: int):
        """阈值两侧：days ≤ 60 可行、> 60 不可行（阈值为业务常量非集合条数）。"""
        result = evaluate_purchase_feasibility("519674", float(amount), _index(limit=1.0))
        assert result is not None
        assert result["days"] == amount
        assert result["feasible"] is (amount <= FEASIBILITY_MAX_DAYS)

    def test_unknown_amount_no_days(self):
        """金额未知 → 只提示限购、不给天数（宁缺毋错）。"""
        result = evaluate_purchase_feasibility("519674", None, _index())
        assert result is not None
        assert result["kind"] == "limited"
        assert result["days"] is None
        assert result["feasible"] is None
        assert result["limit_text"] == "100"

    def test_unknown_limit_no_days(self):
        """限额未知（0 元限额解析层已转 None）→ 不给天数。"""
        result = evaluate_purchase_feasibility("519674", 1000.0, _index(limit=None))
        assert result is not None
        assert result["kind"] == "limited"
        assert result["days"] is None
        assert result["feasible"] is None
        assert result["limit_text"] == "限额未知"

    def test_days_relationship(self):
        """days 为 amount/limit 上取整（结构性关系，不依赖具体数值）。"""
        limit = 300.0
        amount = 750.0
        result = evaluate_purchase_feasibility("519674", amount, _index(limit=limit))
        assert result is not None
        days = result["days"]
        assert days * limit >= amount
        assert (days - 1) * limit < amount


class TestSuspended:
    """暂停申购分支：提示下一开放日、不给天数。"""

    def test_suspended_next_open(self):
        result = evaluate_purchase_feasibility("519674", None, _index(status="暂停申购", next_open_text="10月15日"))
        assert result is not None
        assert result["kind"] == "suspended"
        assert result["next_open_text"] == "10月15日"
        assert result["days"] is None
        assert result["feasible"] is None

    def test_suspended_ignores_amount(self):
        """暂停分支无金额语义（amount 归一为 None）。"""
        result = evaluate_purchase_feasibility("519674", 9999.0, _index(status="暂停申购", next_open_text="10月15日"))
        assert result is not None
        assert result["amount"] is None


class TestDefensive:
    """防御分支：脏索引无判定。"""

    def test_non_restricted_status_returns_none(self):
        """非受限状态混入索引（脏数据）→ 无判定（与准入同判据）。"""
        assert evaluate_purchase_feasibility("519674", 100.0, _index(status="开放申购")) is None

    def test_entry_not_dict_returns_none(self):
        assert evaluate_purchase_feasibility("519674", 100.0, {"519674": "dirty"}) is None
