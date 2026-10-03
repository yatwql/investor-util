"""调仓 What-if 模拟纯计算测试。

覆盖：
  - 变动类型：新增/清仓/加仓/减仓/不变
  - 份额容差（|Δ|<1e-3 → 不变）
  - 成本口径权重 / HHI
  - 汇总指标 delta + 箭头（↑↓→）
  - 分类配置对比（成本口径权重 %）
  - 多账户合并（同一 code 跨账户累加）
  - 任一侧为空 → available=False 降级
"""

from __future__ import annotations

import pytest

from src.python.analysis.whatif import _arrow, _merge_holdings, build_whatif_data
from src.python.core.models import Holding

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _h(code: str, name: str, shares: float, cost_price: float, account: str = "a") -> Holding:
    return Holding(account=account, name=name, code=code, shares=shares, cost_price=cost_price)


# ── 变动类型 ──────────────────────────────────────────────


def test_actions_detected():
    """新增/清仓/加仓/减仓/不变 全部识别。"""
    base = [
        _h("600900", "长江电力", 1000, 20.0),
        _h("510300", "沪深300ETF", 2000, 3.0),
        _h("511010", "国债ETF", 5000, 10.0),
        _h("511990", "华宝添益", 3000, 1.0),
    ]
    cand = [
        _h("600900", "长江电力", 1200, 20.0),  # 加仓
        _h("511010", "国债ETF", 4000, 10.0),  # 减仓
        _h("511990", "华宝添益", 3000, 1.0),  # 不变
        _h("511880", "货币ETF", 8000, 1.0),  # 新增
    ]
    d = build_whatif_data(base, cand)
    by_code = {c["code"]: c for c in d["changes"]}
    assert by_code["600900"]["action"] == "加仓"
    assert by_code["510300"]["action"] == "清仓"
    assert by_code["511010"]["action"] == "减仓"
    assert by_code["511990"]["action"] == "不变"
    assert by_code["511880"]["action"] == "新增"
    assert d["stats"] == {"added": 1, "removed": 1, "increased": 1, "decreased": 1, "unchanged": 1}


def test_shares_epsilon_treated_unchanged():
    """|Δ份额| < 1e-3 → 不变。"""
    base = [_h("600900", "长江电力", 1000.0004, 20.0)]
    cand = [_h("600900", "长江电力", 1000.0001, 20.0)]
    d = build_whatif_data(base, cand)
    assert d["changes"][0]["action"] == "不变"


def test_changes_sorted_by_action_priority():
    """变动明细按 新增→清仓→加仓→减仓→不变 排序。"""
    base = [
        _h("600900", "长江电力", 1000, 20.0),
        _h("510300", "沪深300ETF", 2000, 3.0),
        _h("511010", "国债ETF", 5000, 10.0),
    ]
    cand = [
        _h("600900", "长江电力", 1200, 20.0),
        _h("511010", "国债ETF", 4000, 10.0),
        _h("511880", "货币ETF", 8000, 1.0),
    ]
    d = build_whatif_data(base, cand)
    actions = [c["action"] for c in d["changes"]]
    assert actions == ["新增", "清仓", "加仓", "减仓"]


# ── 权重 / HHI / 汇总 ─────────────────────────────────────


def test_cost_weight_and_hhi():
    """成本口径权重 + HHI。"""
    base = [_h("600900", "长江电力", 1000, 20.0), _h("510300", "沪深300ETF", 2000, 3.0)]
    d = build_whatif_data(base, [])
    assert d["base"]["total_cost"] == 26000.0  # 20000 + 6000
    assert d["base"]["holding_count"] == 2
    # 权重：600900 = 20000/26000 ≈ 76.92%，510300 = 23.08%
    w600 = next(c for c in d["changes"] if c["code"] == "600900")
    assert w600["base_weight"] == pytest.approx(76.92)
    # HHI ≈ 0.7692² + 0.2308²
    assert d["base"]["hhi"] == pytest.approx(0.7692**2 + 0.2308**2, abs=1e-4)


def test_summary_delta_and_arrow():
    """汇总指标 delta + 箭头方向。"""
    base = [_h("600900", "长江电力", 1000, 20.0), _h("510300", "沪深300ETF", 2000, 3.0)]
    cand = [_h("600900", "长江电力", 1200, 20.0)]
    d = build_whatif_data(base, cand)
    summary = {s["key"]: s for s in d["summary"]}
    assert summary["total_cost"]["delta"] == pytest.approx(-2000.0)  # 26000 → 24000
    assert summary["total_cost"]["arrow"] == "↓"
    assert summary["total_shares"]["delta"] == pytest.approx(-1800.0)
    assert summary["total_shares"]["arrow"] == "↓"
    assert summary["holding_count"]["delta"] == -1
    assert summary["holding_count"]["arrow"] == "↓"
    # HHI 上升 → ↑
    assert summary["hhi"]["delta"] > 0
    assert summary["hhi"]["arrow"] == "↑"


def test_hhi_arrow_flat_when_unchanged():
    """无变化 → 箭头 →。"""
    base = [_h("600900", "长江电力", 1000, 20.0)]
    cand = [_h("600900", "长江电力", 1000, 20.0)]
    d = build_whatif_data(base, cand)
    summary = {s["key"]: s for s in d["summary"]}
    assert summary["total_cost"]["arrow"] == "→"
    assert summary["hhi"]["arrow"] == "→"


# ── 分类配置 ──────────────────────────────────────────────


def test_category_distribution():
    """分类配置对比（成本口径权重 %）+ delta。"""
    base = [_h("600900", "长江电力", 1000, 20.0), _h("511010", "国债ETF", 5000, 10.0)]
    cand = [_h("600900", "长江电力", 1000, 20.0), _h("511880", "货币ETF", 8000, 1.0)]
    d = build_whatif_data(base, cand)
    cats = {c["key"]: c for c in d["categories"]}
    # base: equity 20000/70000=28.57%, fixed_income 50000/70000=71.43%
    assert cats["equity"]["base_weight"] == pytest.approx(28.57)
    assert cats["fixed_income"]["base_weight"] == pytest.approx(71.43)
    # cand: equity 20000/28000=71.43%, money_market 8000/28000=28.57%
    assert cats["equity"]["cand_weight"] == pytest.approx(71.43)
    assert cats["money_market"]["cand_weight"] == pytest.approx(28.57)
    assert cats["fixed_income"]["cand_weight"] == 0.0  # 清仓国债ETF
    assert cats["equity"]["delta_pct"] == pytest.approx(71.43 - 28.57, abs=0.01)


# ── 多账户合并 / 降级 ─────────────────────────────────────


def test_merge_across_accounts():
    """同一 code 跨账户 → 份额/成本累加。"""
    base = [
        _h("600900", "长江电力", 1000, 20.0, account="A"),
        _h("600900", "长江电力", 500, 10.0, account="B"),
    ]
    idx = _merge_holdings(base)
    assert idx["600900"]["shares"] == 1500
    assert idx["600900"]["cost"] == pytest.approx(20000 + 5000)


def test_empty_both_sides_unavailable():
    """两侧均为空 → available=False + reason。"""
    d = build_whatif_data([], [])
    assert d["available"] is False
    assert d["status"] == "empty"
    assert "为空" in d["reason"]


def test_empty_candidate_still_computable():
    """目标为空（清仓全部）→ 仍可计算，全部记为清仓。"""
    base = [_h("600900", "长江电力", 1000, 20.0)]
    d = build_whatif_data(base, [])
    assert d["available"] is True
    assert len(d["changes"]) == 1
    assert d["changes"][0]["action"] == "清仓"
    assert d["stats"]["removed"] == 1


def test_file_labels_preserved():
    """base_file / candidate_file 传入展示。"""
    d = build_whatif_data(
        [_h("600900", "长江电力", 1, 1.0)],
        [_h("600900", "长江电力", 2, 1.0)],
        base_file="before.xlsx",
        candidate_file="after.xlsx",
    )
    assert d["base_file"] == "before.xlsx"
    assert d["candidate_file"] == "after.xlsx"


# ── 工具函数 ──────────────────────────────────────────────


def test_arrow_helper():
    """箭头方向：↑ / ↓ / →。"""
    assert _arrow(1.0) == "↑"
    assert _arrow(-1.0) == "↓"
    assert _arrow(0.0001) == "→"


# ── 受限提示注入（restricted_index）──────────────────────────


class TestFeasibilityInject:
    """what-if 目标持仓受限提示：缺省等价、命中分支、降级无键。"""

    def _pair(self):
        """一对基础持仓（加仓腿：1000 → 3000 份 × 2.0 元）。"""
        base = [_h("519674", "易方达蓝筹", 1000, 2.0)]
        cand = [_h("519674", "易方达蓝筹", 3000, 2.0)]
        return base, cand

    def _index(self, status: str = "限大额", limit: float | None = 100.0, **over) -> dict:
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

    def test_default_equals_empty_index(self):
        """缺省 ≡ restricted_index={}：降级态输出逐字节一致（零回归）。"""
        base, cand = self._pair()
        assert build_whatif_data(base, cand) == build_whatif_data(base, cand, restricted_index={})
        assert "feasibility" not in build_whatif_data(base, cand)

    def test_added_restricted_target_note(self):
        """目标新增受限标的 → 提示条目（金额 = 目标成本全额，天数正确）。"""
        base = [_h("600900", "长江电力", 1000, 20.0)]
        cand = [_h("519674", "易方达蓝筹", 500, 2.0)]  # 新增，cand_cost = 1000
        d = build_whatif_data(base, cand, restricted_index=self._index())
        notes = d["feasibility"]
        assert len(notes) == 1
        n = notes[0]
        assert n["action"] == "新增"
        assert n["kind"] == "limited"
        assert n["amount"] == pytest.approx(1000.0)
        assert n["days"] == 10
        assert n["feasible"] is True
        assert n["name"] == "易方达蓝筹"
        assert "日限 100 元" in n["note_text"]
        assert "估算" in n["note_text"]

    def test_increased_amount_is_cost_diff(self):
        """加仓腿金额口径 = 成本增量（cost_diff）。"""
        base, cand = self._pair()  # +2000 份 × 2.0 → cost_diff 4000
        d = build_whatif_data(base, cand, restricted_index=self._index(limit=1000.0))
        n = d["feasibility"][0]
        assert n["action"] == "加仓"
        assert n["amount"] == pytest.approx(4000.0)
        assert n["days"] == 4

    def test_sell_side_not_judged(self):
        """清仓为卖出腿 → 不判定（申购限购不约束卖出，零额外提示）。"""
        base = [_h("519674", "易方达蓝筹", 3000, 2.0), _h("600900", "长江电力", 100, 20.0)]
        cand = [_h("600900", "长江电力", 10, 20.0)]
        d = build_whatif_data(base, cand, restricted_index=self._index())
        assert "feasibility" not in d

    def test_reduced_and_unchanged_not_judged(self):
        """减仓/不变不动仓 → 不判定。"""
        base, cand = self._pair()
        cand = [_h("519674", "易方达蓝筹", 500, 2.0)]  # 减仓
        d = build_whatif_data(base, cand, restricted_index=self._index())
        assert "feasibility" not in d
        d2 = build_whatif_data(base, [_h("519674", "易方达蓝筹", 1000, 2.0)], restricted_index=self._index())
        assert "feasibility" not in d2

    def test_base_restricted_target_free_no_note(self):
        """基准受限、目标不含该标的 → 无提示。"""
        base = [_h("600900", "长江电力", 100, 20.0)]
        cand = [_h("600900", "长江电力", 100, 20.0), _h("511010", "国债ETF", 10, 11.0)]
        d = build_whatif_data(base, cand, restricted_index=self._index())
        assert "feasibility" not in d

    def test_suspended_note_next_open(self):
        """暂停申购 → 提示下一开放日。"""
        base = [_h("600900", "长江电力", 100, 20.0)]
        cand = [_h("519674", "易方达蓝筹", 500, 2.0)]
        d = build_whatif_data(
            base, cand, restricted_index=self._index(status="暂停申购", limit=None, next_open_text="10月15日")
        )
        n = d["feasibility"][0]
        assert n["kind"] == "suspended"
        assert "10月15日" in n["note_text"]

    def test_unknown_limit_note_without_days(self):
        """限额未知 → 提示存在但不给天数（宁缺毋错）。"""
        base = [_h("600900", "长江电力", 100, 20.0)]
        cand = [_h("519674", "易方达蓝筹", 500, 2.0)]
        d = build_whatif_data(base, cand, restricted_index=self._index(limit=None))
        n = d["feasibility"][0]
        assert n["days"] is None
        assert n["feasible"] is None
        assert "无法估算" in n["note_text"]
