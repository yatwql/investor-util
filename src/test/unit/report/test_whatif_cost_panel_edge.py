"""What-if 交易成本对比面板（whatif_cost_panel）边缘/降级测试 — 异常路径不外溢。

覆盖（极端输入与降级矩阵）：
  - 无变动腿 → available=False + reason
  - 快照缺失 / 快照加载异常 / 计数不可判 → 卖出腿费率未知（不冒充 0）
  - 指数行情取数抛异常 → status=unavailable（面板其余环节照常）
  - 配置读取异常 → 基准环节整体缺席（None），成本块不受影响
  - 费用/成本比 ≥ 1（荒谬输入）→ 不出成本后数字

标记：@pytest.mark.edge（隔离规则：edge 用例必须落 *_edge.py 文件）。

运行：
  cd <项目根目录>
  pytest src/test/unit/report/test_whatif_cost_panel_edge.py -v
"""

from __future__ import annotations

import pytest

from src.test.unit.report.test_whatif_cost_panel import _build, _whatif

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestCostPanelDegradation:
    """降级矩阵：任一环节失败只降级本环节，不抛出、不污染其余契约。"""

    def test_empty_changes_unavailable_with_reason(self) -> None:
        """无变动腿 → available=False 且给出 reason，impact/benchmark/chart 缺席。"""
        data = _whatif()
        data["changes"] = []
        panel = _build(data=data)
        assert panel["available"] is False
        assert panel["reason"], "不可用时必须给出原因"
        assert panel["impact"] is None
        assert panel["benchmark"] is None
        assert panel["chart"] is None

    def test_empty_snapshots_sell_leg_unknown(self) -> None:
        """无快照 → 卖出腿批次缺失判未知（买入腿照常），fees_complete=False。"""
        panel = _build(snapshots=[])
        tc = panel["trade_cost"]
        assert tc["unknown_legs"] == 1
        assert tc["fees_complete"] is False
        assert tc["purchase_total"] == 15.0  # 买入腿不受影响
        assert panel["impact"] is None

    def test_counter_returning_none_sell_unknown(self) -> None:
        """交易日计数返回 None → 卖出腿持有期未知 → 费率未知。"""
        panel = _build(count_trading_days=lambda start, end: None)
        tc = panel["trade_cost"]
        assert tc["unknown_legs"] == 1
        assert tc["fees_complete"] is False
        assert panel["impact"] is None

    def test_snapshot_loader_failure_degrades_to_empty(self, monkeypatch) -> None:
        """快照加载抛异常 → 按空快照降级（卖出腿未知），装配不中断。"""

        def _boom():
            raise RuntimeError("snapshot store unavailable")

        monkeypatch.setattr("src.python.report.history_snapshot.load_all", _boom)
        panel = _build(snapshots=None)
        assert panel["available"] is True
        assert panel["trade_cost"]["unknown_legs"] == 1

    def test_index_history_exception_status_unavailable(self) -> None:
        """指数行情取数抛异常 → 基准 status=unavailable、values=None，成本块照常。"""

        def _boom(code, days):
            raise RuntimeError("index unreachable")

        panel = _build(index_history_getter=_boom)
        bench = panel["benchmark"]
        assert bench is not None
        assert bench["status"] == "unavailable"
        assert bench["values"] is None
        assert panel["chart"] is not None
        assert panel["chart"]["benchmark"] is None
        assert panel["trade_cost"]["total_cost"] == 115.0

    def test_config_read_exception_benchmark_absent(self, monkeypatch) -> None:
        """配置读取抛异常 → 基准环节整体缺席（None），成本块不受影响。"""

        def _boom():
            raise RuntimeError("config unavailable")

        monkeypatch.setattr("src.python.config.get_config", _boom)
        panel = _build(
            benchmark_override=None,
            comparison_indices=None,
            benchmark_text_getter=None,
            index_history_getter=lambda code, days: [],
        )
        assert panel["benchmark"] is None
        assert panel["chart"] is not None
        assert panel["chart"]["benchmark"] is None
        assert panel["impact"] is not None

    def test_ratio_ge_one_no_post_cost_numbers(self) -> None:
        """费用 ≥ 目标组合成本（荒谬输入）→ 不出成本后数字，不出伪精度。"""
        data = _whatif()
        data["candidate"]["total_cost"] = 50.0  # 费用 115 > 50 → ratio ≥ 1
        panel = _build(data=data)
        assert panel["impact"] is None
        assert panel["chart"]["candidate_after"] is None
        assert panel["chart"]["candidate_before"] == [100.0, 105.0]

    def test_empty_fee_index_total_zero(self) -> None:
        """纯注入路径下空费率索引 → 总成本 0（未知腿计数而非冒充费率）。"""
        panel = _build(data=_whatif(with_backtest=False), fee_index={})
        tc = panel["trade_cost"]
        assert tc["total_cost"] == 0.0
        assert tc["unknown_legs"] == 2
