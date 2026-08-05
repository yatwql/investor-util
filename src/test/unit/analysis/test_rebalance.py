"""再平衡信号计算模块测试。

测试策略：
  - 单元测试验证各函数独立逻辑，mock config 隔离真实配置
  - edge 场景放入独立 _edge.py 文件
  - 使用 monkeypatch 隔离 get_config()
"""

from __future__ import annotations

import datetime
import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

from src.python.analysis.rebalance import (
    _categorize_holdings,
    _calc_category_weights,
    _CATEGORY_ORDER,
    _compute_confidence,
    _REBALANCE_PROFILES,
    _filter_silenced_signals,
    _load_silence_state,
    _save_silence_state,
    classify_holding,
    compute_target_deviation,
    equity_fixed_income_deviation,
    compute_rebalance_signals,
    resolve_rebalance_config,
)

from src.python.analysis.simple_rebalance import compute_simple_rebalance_signals


# ── 极简再平衡信号（配置化阈值 + 静默期） ─────────────────────


def _mk_holding(code: str, market_value: float, name: str = "") -> dict:
    """构造极简再平衡信号所需的持仓行。"""
    return {"code": code, "name": name or code, "market_value": market_value}


class TestSimpleRebalanceConfigThreshold:
    """compute_simple_rebalance_signals 配置化阈值。"""

    def test_explicit_threshold_lower_triggers_more(self):
        """显式收紧阈值 → 更多品种触发（10% 阈值下 12% 品种触发）。"""
        # 600001 占 12%、600002 占 8%：默认 15% 均合规，10% 阈值下 600001 触发
        holdings = [
            _mk_holding("600001", 1200.0),
            _mk_holding("600002", 800.0),
        ]
        signals = compute_simple_rebalance_signals(holdings, 10000.0, threshold=0.10)
        assert [s["code"] for s in signals] == ["600001"]

    def _single_overweight(self, code: str, mv: float, n_compliant: int = 7) -> list[dict]:
        """构造「1 只超重 + N 只合规」持仓集，总市值 10000。"""
        holdings = [_mk_holding(code, mv)]
        holdings.extend(_mk_holding(f"6000{n:02d}", 1000.0) for n in range(2, 2 + n_compliant))
        return holdings

    def test_explicit_threshold_higher_suppresses(self):
        """显式放宽阈值 → 原触发品种不再触发（25% 阈值下 20% 品种合规）。"""
        # 600001 占 20%（超 15%），其余各 10%（合规）：25% 阈值下全部合规
        holdings = self._single_overweight("600001", 2000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0, threshold=0.25)
        assert signals == []

    def test_threshold_value_in_signal(self):
        """信号携带实际生效的 threshold 值（显式 0.12）。"""
        # 600001 占 20%（超 15%），其余各 10%：12% 阈值下 600001 触发
        holdings = self._single_overweight("600001", 2000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0, threshold=0.12)
        assert signals[0]["threshold"] == 0.12
        assert {s["code"] for s in signals} == {"600001"}

    def test_default_threshold_still_15(self, monkeypatch):
        """未显式传阈值 → 默认 15%（0.15），20% 触发。"""
        holdings = self._single_overweight("600001", 2000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0)
        assert signals[0]["threshold"] == 0.15
        assert {s["code"] for s in signals} == {"600001"}

    def test_default_uses_config_silence(self, tmp_path):
        """未显式传静默期 → 默认读配置（30 天），静默期内品种被过滤。"""
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state({"600001": datetime.date.today().isoformat()}, f)
        holdings = self._single_overweight("600001", 2000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0, silence_file=f)
        assert signals == []


class TestSimpleRebalanceSilence:
    """compute_simple_rebalance_signals 静默期过滤。"""

    def _single_overweight(self, code: str, mv: float, n_compliant: int = 7) -> list[dict]:
        """构造「1 只超重 + N 只合规」持仓集，总市值 10000。"""
        holdings = [_mk_holding(code, mv)]
        holdings.extend(_mk_holding(f"6000{n:02d}", 1000.0) for n in range(2, 2 + n_compliant))
        return holdings

    def test_signal_suppressed_within_silence(self, tmp_path):
        """静默期内品种被过滤（今天触发）。"""
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state({"600001": datetime.date.today().isoformat()}, f)
        # 600001 占 30%（超 15% 触发），其余各 10%（合规）
        holdings = self._single_overweight("600001", 3000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0, silence_days=30, silence_file=f)
        assert signals == []

    def test_signal_passes_after_silence(self, tmp_path):
        """静默期到期后品种重新触发。"""
        past = datetime.date.today() - datetime.timedelta(days=31)
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state({"600001": past.isoformat()}, f)
        holdings = self._single_overweight("600001", 3000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0, silence_days=30, silence_file=f)
        assert {s["code"] for s in signals} == {"600001"}

    def test_silence_zero_disables(self, tmp_path):
        """silence_days=0 → 不过滤、不写文件。"""
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state({"600001": datetime.date.today().isoformat()}, f)
        holdings = self._single_overweight("600001", 3000.0)
        signals = compute_simple_rebalance_signals(holdings, 10000.0, silence_days=0, silence_file=f)
        assert {s["code"] for s in signals} == {"600001"}

    def test_silence_writes_state(self, tmp_path):
        """触发信号写入静默状态（下次同品种被抑制）。"""
        f = str(tmp_path / "rebalance_silence.json")
        holdings = self._single_overweight("600001", 3000.0)
        compute_simple_rebalance_signals(holdings, 10000.0, silence_days=30, silence_file=f)
        state = _load_silence_state(f)
        # 触发品种写入静默状态（600001 占 30% 超 15%）
        assert "600001" in state

    def test_silence_carries_summary_passthrough(self, tmp_path):
        """汇总信号不受静默期影响（未触发单品时汇总直接返回）。"""
        f = str(tmp_path / "rebalance_silence.json")
        # 5 只各占 22%：超过 _MAX_DETAILED=3 → 汇总；默认 15% 阈值
        holdings = [_mk_holding(f"60000{n}", 1100.0) for n in range(1, 6)]
        signals = compute_simple_rebalance_signals(holdings, 5000.0, silence_days=30, silence_file=f)
        assert signals == [
            {
                "summary": True,
                "count": 5,
                "message": "您的组合集中度较高，有 5 个品种超过 15% 警戒线，建议整体考虑适度分散",
            }
        ]


# ── classify_holding 测试 ─────────────────────────────────────


class TestClassifyHolding:
    """资产分类函数测试。"""

    def test_a_share_stock(self):
        assert classify_holding("贵州茅台", "600519") == "equity"

    def test_hk_stock(self):
        assert classify_holding("腾讯控股", "00700") == "equity"

    def test_bond_fund(self):
        assert classify_holding("XX纯债债券A", "008123") == "fixed_income"

    def test_money_fund(self):
        assert classify_holding("余额宝货币", "000001") == "money_market"

    def test_qdii(self):
        assert classify_holding("纳斯达克100QDII", "513100") == "qdii"

    def test_convertible_bond(self):
        assert classify_holding("XX转债", "123456") == "alternative"

    def test_etf_equity(self):
        assert classify_holding("沪深300ETF", "510300") == "equity"

    def test_etf_bond(self):
        assert classify_holding("XX国债ETF", "511000") == "fixed_income"

    def test_index_fund(self):
        assert classify_holding("XX沪深300指数", "001234") == "fund_equity"

    def test_money_etf(self):
        assert classify_holding("华宝添益ETF", "511990") == "money_market"

    def test_otc_equity_fund(self):
        assert classify_holding("XX灵活配置混合", "002345") == "fund_equity"


# ── _categorize_holdings / _calc_category_weights 测试 ────────


class TestCategorizeHoldings:
    """分类汇总逻辑测试。"""

    def test_categorize_single_type(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 10000},
            {"name": "腾讯控股", "code": "00700", "market_value": 5000},
        ]
        result = _categorize_holdings(holdings)
        assert len(result["equity"]) == 2
        assert sum(1 for items in result.values() for _ in items) == 2

    def test_categorize_mixed(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 10000},
            {"name": "XX纯债债券A", "code": "008123", "market_value": 5000},
            {"name": "余额宝货币", "code": "000001", "market_value": 3000},
        ]
        result = _categorize_holdings(holdings)
        assert len(result["equity"]) == 1
        assert len(result["fixed_income"]) == 1
        assert len(result["money_market"]) == 1

    def test_empty_input(self):
        result = _categorize_holdings([])
        assert all(len(items) == 0 for items in result.values())

    def test_weight_calculation(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 10000},
            {"name": "XX纯债债券A", "code": "008123", "market_value": 5000},
        ]
        categorized = _categorize_holdings(holdings)
        weights = _calc_category_weights(categorized, 15000)
        assert weights["equity"] == pytest.approx(66.67, rel=0.01)
        assert weights["fixed_income"] == pytest.approx(33.33, rel=0.01)

    def test_weight_zero_total(self):
        weights = _calc_category_weights({}, 0)
        assert all(w == 0.0 for w in weights.values())


# ── compute_target_deviation 测试 ─────────────────────────────


class TestComputeTargetDeviation:
    """目标配置偏离度计算测试。"""

    def test_no_target_allocation_returns_empty(self):
        result = compute_target_deviation(
            [{"name": "茅台", "code": "600519", "market_value": 10000}],
            10000,
            {},
        )
        assert result == []

    def test_within_target_range(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 5000},
            {"name": "XX纯债债券", "code": "008123", "market_value": 5000},
        ]
        target = {
            "equity": {"min": 30, "max": 70, "target": 50},
            "fixed_income": {"min": 20, "max": 50, "target": 35},
        }
        result = compute_target_deviation(holdings, 10000, target)
        # 权益 50%、固收 50% — 权益在范围内，固收超上限 50>50? 等于 max 不超出
        # deviation = 50 - 35 = 15 > 5 → 有信号
        assert len(result) >= 1
        # 固收 50% = max 50%，在范围内
        dev_types = [r["type"] for r in result]
        assert "category" in dev_types

    def test_equity_overweight(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 8000},
            {"name": "XX纯债债券", "code": "008123", "market_value": 2000},
        ]
        target = {
            "equity": {"min": 30, "max": 60, "target": 50},
        }
        result = compute_target_deviation(holdings, 10000, target)
        assert len(result) >= 1
        r = result[0]
        assert r["type"] == "category"
        assert r["current_weight"] == 80.0
        assert r["deviation"] > 0

    def test_security_level_target(self):
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 20000},
            {"name": "XX债券", "code": "008123", "market_value": 8000},
        ]
        target = {
            "600519": {"min": 5, "max": 15, "target": 10},
        }
        result = compute_target_deviation(holdings, 28000, target)
        assert len(result) >= 1
        r = result[0]
        assert r["type"] == "security"
        assert r["code"] == "600519"

    def test_empty_holdings(self):
        result = compute_target_deviation(None, 0, {"equity": {"min": 0, "max": 100}})
        assert result == []


# ── compute_rebalance_signals（入口集成测试） ──────────────────


class TestComputeRebalanceSignals:
    """再平衡信号入口函数测试。"""

    def test_no_holdings_returns_empty(self):
        assert compute_rebalance_signals(None, 0) == []
        assert compute_rebalance_signals([], 0) == []

    def test_single_overflow_within_threshold(self):
        holdings = [
            {"name": "A", "code": "600001", "market_value": 100},
            {"name": "B", "code": "600002", "market_value": 900},
        ]
        config = {"threshold": 0.9}
        result = compute_rebalance_signals(holdings, 1000, config)
        assert len(result) == 0  # 无品种超 90%

    def test_single_overflow(self):
        holdings = [
            {"name": "A", "code": "600001", "market_value": 300},
            {"name": "B", "code": "600002", "market_value": 700},
        ]
        config = {"threshold": 0.15}
        # B: 700/1000 = 70%, 超 15% 阈值
        result = compute_rebalance_signals(holdings, 1000, config)
        assert len(result) >= 1
        assert result[0]["type"] == "single_overflow"
        assert result[0]["code"] == "600002"

    def test_multiple_overflow_summary(self):
        """超过 3 个品种触发时聚合为一条汇总建议。"""
        holdings = [{"name": f"品种{i}", "code": f"60000{i}", "market_value": 250} for i in range(5)]
        # total = 1250, 每品种 250/1250 = 20%, 全部超 15%
        config = {"threshold": 0.15}
        result = compute_rebalance_signals(holdings, 1250, config)
        assert len(result) == 1
        assert result[0]["type"] == "summary"
        assert result[0]["summary"] is True
        assert result[0]["count"] == 5

    def test_rebalance_with_target_config(self):
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 8000},
            {"name": "债券A", "code": "008123", "market_value": 2000},
        ]
        config = {
            "threshold": 0.15,
            "target_allocation": {
                "equity": {"min": 30, "max": 60, "target": 50},
            },
        }
        result = compute_rebalance_signals(holdings, 10000, config)
        # 应有单品超限信号 (8000/10000=80% > 15%) + 目标偏离信号
        types = {r["type"] for r in result}
        assert "single_overflow" in types
        assert "category" in types

    def test_empty_config_defaults(self):
        """target_allocation 为空字典 → 无目标偏离信号，但单品超限仍独立触发。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 1000},
        ]
        result = compute_rebalance_signals(holdings, 1000, {"threshold": 0.5, "target_allocation": {}})
        # 单品超限独立于 target_allocation：1000/1000=100% > 50% → 触发
        assert len(result) == 1
        assert result[0]["type"] == "single_overflow"

    def test_rebalance_with_equity_fixed_income_config(self):
        """compute_rebalance_signals 集成 equity_fixed_income 配置。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 8000},
            {"name": "债券A", "code": "008123", "market_value": 2000},
        ]
        config = {
            "threshold": 0.15,
            "equity_fixed_income": {
                "equity": {"min": 30, "max": 70, "target": 60},
            },
        }
        result = compute_rebalance_signals(holdings, 10000, config)
        # 应有单品超限 (80%) + 权益/固收偏离 (equity=80% > 70%)
        types = {r["type"] for r in result}
        assert "single_overflow" in types
        assert "equity_fixed_income" in types

    def test_equity_fixed_income_empty_config_no_extra_signal(self):
        """equity_fixed_income 为空时无额外信号，其他信号不受影响。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 5100},
        ]
        config = {"threshold": 0.5, "equity_fixed_income": {}}
        result = compute_rebalance_signals(holdings, 10000, config)
        # 单品超限仍独立触发 (51% > 50%)
        assert len(result) == 1
        assert result[0]["type"] == "single_overflow"


# ── resolve_rebalance_config 测试 ──────────────────────────────


class TestResolveRebalanceConfig:
    """预设阈值集解析测试。"""

    def test_none_config_uses_defaults(self):
        result = resolve_rebalance_config(None)
        assert result["threshold"] == 0.15
        assert result["deviation_threshold"] == 0.05

    def test_conservative_profile(self):
        result = resolve_rebalance_config({"profile": "conservative"})
        assert result["threshold"] == _REBALANCE_PROFILES["conservative"]["threshold"]
        assert result["deviation_threshold"] == _REBALANCE_PROFILES["conservative"]["deviation_threshold"]

    def test_aggressive_profile(self):
        result = resolve_rebalance_config({"profile": "aggressive"})
        assert result["threshold"] == _REBALANCE_PROFILES["aggressive"]["threshold"]
        assert result["deviation_threshold"] == _REBALANCE_PROFILES["aggressive"]["deviation_threshold"]

    def test_custom_profile_no_override(self):
        """custom 模式不使用 preset，使用 config 中的值或默认值。"""
        result = resolve_rebalance_config({"profile": "custom", "threshold": 0.20})
        assert result["threshold"] == 0.20
        assert result["deviation_threshold"] == 0.05  # 默认值

    def test_explicit_values_override_preset(self):
        """显式指定的值优先于预设。"""
        result = resolve_rebalance_config(
            {
                "profile": "conservative",
                "threshold": 0.12,  # 覆盖 conservative 的 0.10
            }
        )
        assert result["threshold"] == 0.12
        # deviation_threshold 未显式指定 → 使用 preset
        assert result["deviation_threshold"] == _REBALANCE_PROFILES["conservative"]["deviation_threshold"]

    def test_moderate_profile_default(self):
        """默认 profile 为 moderate。"""
        result = resolve_rebalance_config({})
        assert result["threshold"] == _REBALANCE_PROFILES["moderate"]["threshold"]
        assert result["deviation_threshold"] == _REBALANCE_PROFILES["moderate"]["deviation_threshold"]

    def test_target_allocation_preserved(self):
        result = resolve_rebalance_config(
            {
                "profile": "aggressive",
                "target_allocation": {"equity": {"min": 20, "max": 80}},
            }
        )
        assert "equity" in result["target_allocation"]


# ── compute_target_deviation 阈值测试 ──────────────────────────


class TestComputeTargetDeviationThreshold:
    """偏离度阈值配置测试。"""

    def test_tight_threshold_detects_small_deviation(self):
        """严格阈值（1%）能检测到小偏离。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 5500},
            {"name": "B", "code": "600002", "market_value": 4500},
        ]
        target = {"equity": {"min": 0, "max": 100, "target": 50}}
        # 偏离 = 5% > 1% 阈值 → 应有信号
        result = compute_target_deviation(holdings, 10000, target, deviation_threshold=0.01)
        assert len(result) >= 1
        assert result[0]["type"] == "category"

    def test_loose_threshold_suppresses_small_deviation(self):
        """宽松阈值（10%）忽略 2% 的小偏离。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 5200},
            {"name": "债券A", "code": "008123", "market_value": 4800},
        ]
        target = {"equity": {"min": 0, "max": 100, "target": 50}}
        # equity=52%, deviation=2%, 2% < 10% 阈值且在范围 0-100 内 → 无信号
        result = compute_target_deviation(holdings, 10000, target, deviation_threshold=0.10)
        assert result == []

    def test_security_level_tight_threshold(self):
        """品种级偏离也受 deviation_threshold 控制。"""
        holdings = [
            {"name": "茅台", "code": "600519", "market_value": 6000},
            {"name": "B", "code": "600002", "market_value": 4000},
        ]
        target = {"600519": {"min": 0, "max": 100, "target": 50}}
        # 偏离 = 10% > 8% 阈值 → 信号
        result = compute_target_deviation(holdings, 10000, target, deviation_threshold=0.08)
        assert len(result) >= 1
        assert result[0]["type"] == "security"

    def test_security_level_loose_threshold(self):
        holdings = [
            {"name": "茅台", "code": "600519", "market_value": 6000},
            {"name": "B", "code": "600002", "market_value": 4000},
        ]
        target = {"600519": {"min": 0, "max": 100, "target": 50}}
        # 偏离 = 10% < 15% 阈值 → 无信号
        result = compute_target_deviation(holdings, 10000, target, deviation_threshold=0.15)
        assert result == []


# ── compute_rebalance_signals profile 集成测试 ─────────────────


class TestComputeRebalanceSignalsProfile:
    """再平衡入口函数与预设阈值集集成测试。"""

    def test_conservative_profile_triggers_at_11pct(self):
        """保守预设（10% 阈值）对 11% 品种触发单品超限。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 220},
        ]
        # 220/2000 = 11% > 10% → 触发
        result = compute_rebalance_signals(holdings, 2000, {"profile": "conservative"})
        assert len(result) >= 1
        assert result[0]["type"] == "single_overflow"

    def test_moderate_profile_not_triggers_at_14pct(self):
        """稳健预设（15% 阈值）不触发 14% 的品种。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 280},
        ]
        # 280/2000 = 14% < 15% → 不触发
        result = compute_rebalance_signals(holdings, 2000, {"profile": "moderate"})
        assert len(result) == 0

    def test_moderate_profile_triggers_at_16pct(self):
        """稳健预设（15% 阈值）触发 16% 的品种。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 320},
        ]
        # 320/2000 = 16% > 15% → 触发
        result = compute_rebalance_signals(holdings, 2000, {"profile": "moderate"})
        assert len(result) >= 1
        assert result[0]["type"] == "single_overflow"

    def test_aggressive_profile_not_triggers_at_20pct(self):
        """进取预设（25% 阈值）不触发 20% 的品种。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 400},
        ]
        # 400/2000 = 20% < 25% → 不触发
        result = compute_rebalance_signals(holdings, 2000, {"profile": "aggressive"})
        assert len(result) == 0

    def test_aggressive_profile_triggers_at_30pct(self):
        """进取预设（25% 阈值）对 30% 品种触发。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 600},
        ]
        # 600/2000 = 30% > 25% → 触发
        result = compute_rebalance_signals(holdings, 2000, {"profile": "aggressive"})
        assert len(result) >= 1
        assert result[0]["type"] == "single_overflow"


# ── 权益/固收超大类偏离测试 ──────────────────────────────────


class TestEquityFixedIncomeDeviation:
    """权益/固收超大类偏离信号计算测试。"""

    def test_empty_holdings_returns_empty(self):
        """空持仓返回空列表。"""
        assert equity_fixed_income_deviation(None, 0, {"equity": {"min": 0, "max": 100}}) == []
        assert equity_fixed_income_deviation([], 0, {"equity": {"min": 0, "max": 100}}) == []

    def test_no_target_returns_empty(self):
        """目标配置为空字典时返回空列表。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 8000},
            {"name": "债券A", "code": "008123", "market_value": 2000},
        ]
        assert equity_fixed_income_deviation(holdings, 10000, {}) == []

    def test_equity_above_max_triggers_signal(self):
        """权益类超上限时触发信号。"""
        # 纯权益类持仓：全部归入 equity (equity + fund_equity + qdii)
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 8000},
            {"name": "混合基金", "code": "001234", "market_value": 2000},
        ]
        target = {"equity": {"min": 30, "max": 70, "target": 60}}
        # equity 聚合 = 100% (8000 + 2000) / 10000 → 超出 max 70%
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert result[0]["type"] == "equity_fixed_income"
        assert result[0]["group"] == "equity"
        assert result[0]["current_weight"] == 100.0
        assert result[0]["deviation"] > 0  # 超配

    def test_equity_below_min_triggers_signal(self):
        """权益类低于下限时触发信号。"""
        # 大部分是固收，小部分是权益
        holdings = [
            {"name": "债券A", "code": "008123", "market_value": 9000},
            {"name": "A股", "code": "600001", "market_value": 1000},
        ]
        target = {"equity": {"min": 30, "max": 80, "target": 50}}
        # equity = 1000/10000 = 10% < 30% 下限
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert result[0]["group"] == "equity"
        assert result[0]["deviation"] < 0  # 低配

    def test_fixed_income_above_max_triggers_signal(self):
        """固收类超上限时触发信号。"""
        holdings = [
            {"name": "XX纯债债券A", "code": "008123", "market_value": 7000},
            {"name": "XX货币A", "code": "000001", "market_value": 2000},
            {"name": "A股", "code": "600001", "market_value": 1000},
        ]
        target = {"fixed_income": {"min": 20, "max": 60, "target": 40}}
        # fixed_income = fixed_income(7000) + money_market(2000) = 9000/10000 = 90%
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert result[0]["group"] == "fixed_income"
        assert result[0]["current_weight"] == 90.0
        assert result[0]["deviation"] > 0

    def test_both_groups_within_target_no_signal(self):
        """权益和固收均在目标范围内时无信号。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 3000},
            {"name": "XX纯债债券A", "code": "008123", "market_value": 5000},
            {"name": "XX货币A", "code": "000001", "market_value": 2000},
        ]
        target = {
            "equity": {"min": 20, "max": 50, "target": 30},
            "fixed_income": {"min": 50, "max": 80, "target": 70},
        }
        # equity = 30%, fixed_income = 70%, 均在范围内
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert result == []

    def test_deviation_below_threshold_suppressed(self):
        """偏离低于阈值且未超限时不输出信号。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 5200},
            {"name": "债券A", "code": "008123", "market_value": 4800},
        ]
        target = {"equity": {"min": 0, "max": 100, "target": 50}}
        # equity = 52%, deviation = 2% < 5% threshold
        result = equity_fixed_income_deviation(holdings, 10000, target, deviation_threshold=0.05)
        assert result == []

    def test_mixed_holdings_correct_aggregation(self):
        """混合持仓正确汇总权益和固收大类。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 4000},  # equity
            {"name": "XX混合A", "code": "001234", "market_value": 1000},  # fund_equity
            {"name": "标普QDII", "code": "513100", "market_value": 1000},  # qdii
            {"name": "XX纯债债券A", "code": "008123", "market_value": 2000},  # fixed_income
            {"name": "XX货币A", "code": "000001", "market_value": 1000},  # money_market
            {"name": "XX转债", "code": "123456", "market_value": 1000},  # alternative
        ]
        total = 10000
        # equity 聚合 = 4000+1000+1000 = 6000 → 60%
        # fixed_income 聚合 = 2000+1000+1000 = 4000 → 40%
        target = {
            "equity": {"min": 40, "max": 80, "target": 60},
            "fixed_income": {"min": 20, "max": 60, "target": 40},
        }
        result = equity_fixed_income_deviation(holdings, total, target)
        # 60% / 40% 均在范围内 → 无信号
        assert result == []

    def test_mixed_aggregation_detects_deviation(self):
        """混合持仓正确检测权益/固收偏离。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 5000},  # equity
            {"name": "XX混合A", "code": "001234", "market_value": 2000},  # fund_equity
            {"name": "XX纯债债券A", "code": "008123", "market_value": 2000},  # fixed_income
            {"name": "XX货币A", "code": "000001", "market_value": 1000},  # money_market
        ]
        total = 10000
        # equity 聚合 = 5000+2000 = 7000 → 70%
        # fixed_income 聚合 = 2000+1000 = 3000 → 30%
        target = {
            "equity": {"min": 30, "max": 60, "target": 50},  # 70% > 60%
            "fixed_income": {"min": 40, "max": 70, "target": 50},  # 30% < 40%
        }
        result = equity_fixed_income_deviation(holdings, total, target)
        # 两个大类均偏离 → 应有 2 个信号
        assert len(result) == 2
        types = {r["group"] for r in result}
        assert types == {"equity", "fixed_income"}

    def test_signal_format(self):
        """信号包含完整字段。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 8000},
            {"name": "XX纯债债券A", "code": "008123", "market_value": 1000},
            {"name": "XX货币A", "code": "000001", "market_value": 1000},
        ]
        target = {"equity": {"min": 30, "max": 60, "target": 50}}
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        sig = result[0]
        assert "type" in sig
        assert "group" in sig
        assert "group_label" in sig
        assert "current_weight" in sig
        assert "target_weight" in sig
        assert "min" in sig
        assert "max" in sig
        assert "deviation" in sig
        assert "confidence" in sig
        assert "action" in sig

    def test_equity_only_target(self):
        """仅配置 equity 目标时，只检查权益类偏离。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 5000},
            {"name": "债券A", "code": "008123", "market_value": 5000},
        ]
        target = {"equity": {"min": 40, "max": 60, "target": 50}}
        # equity = 50%, 在范围内 → 无信号
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert result == []

    def test_only_fixed_income_target(self):
        """仅配置 fixed_income 目标时，只检查固收类偏离。"""
        holdings = [
            {"name": "债券A", "code": "008123", "market_value": 9000},
            {"name": "A股", "code": "600001", "market_value": 1000},
        ]
        target = {"fixed_income": {"min": 30, "max": 60, "target": 50}}
        # fixed_income = 90% > 60% → 触发
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert result[0]["group"] == "fixed_income"
        assert result[0]["current_weight"] == 90.0

    def test_tight_threshold_detects_small_deviation(self):
        """严格阈值（1%）检测小偏离。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 5100},
            {"name": "债券A", "code": "008123", "market_value": 4900},
        ]
        target = {"equity": {"min": 0, "max": 100, "target": 50}}
        # equity = 51%, deviation = 1% > 1% → 触发（未超限但偏离超阈值）
        result = equity_fixed_income_deviation(holdings, 10000, target, deviation_threshold=0.01)
        assert len(result) >= 1
        assert result[0]["group"] == "equity"
        assert abs(result[0]["deviation"]) == 1.0

    def test_confidence_high_for_large_deviation(self):
        """大偏离 → 高置信度。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 9000},
            {"name": "债券A", "code": "008123", "market_value": 1000},
        ]
        target = {"equity": {"min": 30, "max": 60, "target": 50}}
        # equity = 90%, deviation = 40% > 10% (2×5% threshold) → high
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert result[0]["confidence"] == "high"

    def test_action_text_for_overweight(self):
        """超配时 action 包含降配建议。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 8000},
            {"name": "债券A", "code": "008123", "market_value": 2000},
        ]
        target = {"equity": {"min": 30, "max": 70, "target": 60}}
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert "超过目标上限" in result[0]["action"]

    def test_action_text_for_underweight(self):
        """低配时 action 包含增配建议。"""
        holdings = [
            {"name": "A股", "code": "600001", "market_value": 1000},
            {"name": "债券A", "code": "008123", "market_value": 9000},
        ]
        target = {"equity": {"min": 30, "max": 70, "target": 60}}
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert len(result) >= 1
        assert "低于目标下限" in result[0]["action"]


# ── 信号置信度测试 ──────────────────────────────────────────────


class TestConfidence:
    """再平衡信号置信度计算测试。"""

    def test_single_overflow_high_confidence(self):
        """weight 超过 2× threshold → high。"""
        conf = _compute_confidence("single_overflow", deviation=45.0, threshold=0.15)
        # 45% > 30% (2×15%) → high
        assert conf == "high"

    def test_single_overflow_medium_confidence(self):
        """weight 超过 threshold 但未达 2× → medium。"""
        conf = _compute_confidence("single_overflow", deviation=20.0, threshold=0.15)
        # 20% > 15% but 20% < 30% (2×15%) → medium
        assert conf == "medium"

    def test_category_high_confidence(self):
        """偏离 > 2× deviation_threshold → high。"""
        conf = _compute_confidence("category", deviation=15.0, deviation_threshold_pct=5.0)
        # 15% > 10% (2×5%) → high
        assert conf == "high"

    def test_category_medium_confidence(self):
        """偏离 > threshold < 2× threshold → medium。"""
        conf = _compute_confidence("category", deviation=8.0, deviation_threshold_pct=5.0)
        # 8% > 5% but 8% < 10% → medium
        assert conf == "medium"

    def test_category_low_confidence(self):
        """偏离 < threshold → low。"""
        conf = _compute_confidence("category", deviation=3.0, deviation_threshold_pct=5.0)
        assert conf == "low"


# ── 误报防护测试 ──────────────────────────────────────────────


class TestFalsePositiveProtection:
    """再平衡信号误报防护测试。"""

    def test_new_holding_filtered(self):
        """持仓不足 20 天的品种被过滤。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 5000, "holding_days": 5},
        ]
        result = compute_rebalance_signals(holdings, 10000, {"threshold": 0.15})
        # 50% > 15% 但持有仅 5 天 → 被过滤
        assert len(result) == 0

    def test_established_holding_not_filtered(self):
        """持仓超过 20 天时正常触发。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 5000, "holding_days": 30},
        ]
        result = compute_rebalance_signals(holdings, 10000, {"threshold": 0.15})
        assert len(result) >= 1
        assert result[0]["type"] == "single_overflow"

    def test_convertible_bond_near_maturity_annotated(self):
        """可转债触发时标注 near_maturity。"""
        holdings = [
            {"name": "XX转债", "code": "123456", "market_value": 5000},
        ]
        result = compute_rebalance_signals(holdings, 10000, {"threshold": 0.15})
        assert len(result) >= 1
        assert result[0].get("near_maturity") is True

    def test_false_positive_flag_structure(self):
        """信号包含 shares_available 字段。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 5000},
        ]
        result = compute_rebalance_signals(holdings, 10000, {"threshold": 0.15})
        assert len(result) >= 1
        assert "shares_available" in result[0]
        assert result[0]["shares_available"] is False  # 测试中没有 shares 字段

    def test_shares_available_flag(self):
        """有 shares 字段时标记为 True。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 5000, "shares": 100},
        ]
        result = compute_rebalance_signals(holdings, 10000, {"threshold": 0.15})
        assert len(result) >= 1
        assert result[0]["shares_available"] is True


# ── 静默期测试 ──────────────────────────────────────────────────


class TestSilencePeriod:
    """再平衡信号静默期机制测试。"""

    def test_load_empty_state(self):
        """无静默期文件时返回空字典。"""
        state = _load_silence_state("/tmp/nonexistent_silence_test.json")
        assert state == {}

    def test_save_and_load(self, tmp_path):
        """写入后可恢复读取。"""
        f = str(tmp_path / "rebalance_silence.json")
        state = {"600001": "2026-07-01", "600002": "2026-07-15"}
        _save_silence_state(state, f)
        loaded = _load_silence_state(f)
        assert loaded == state

    def test_save_corrupted_file_returns_empty(self, tmp_path):
        """损坏的 JSON 文件返回空字典。"""
        f = str(tmp_path / "rebalance_silence.json")
        with open(f, "w") as fh:
            fh.write("not json")
        state = _load_silence_state(f)
        assert state == {}

    def test_filter_within_silence(self, tmp_path):
        """静默期内的品种被过滤。"""
        today = datetime.date.today()
        silences = {"600001": today.isoformat()}  # 今天触发 → 静默期内
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state(silences, f)

        signals = [
            {"type": "single_overflow", "code": "600001", "name": "A", "weight": 30.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=30, silence_file=f)
        assert result == []

    def test_filter_category_not_silenced(self, tmp_path):
        """大类偏离信号不受静默期影响。"""
        today = datetime.date.today()
        silences = {"equity": today.isoformat()}
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state(silences, f)

        signals = [
            {"type": "category", "category": "equity", "deviation": 5.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=30, silence_file=f)
        # category signals pass through regardless of silence state
        assert len(result) == 1

    def test_summary_not_silenced(self, tmp_path):
        """汇总信号不受静默期影响。"""
        signals = [
            {"type": "summary", "summary": True, "count": 3},
        ]
        result = _filter_silenced_signals(signals, silence_days=30, silence_file=str(tmp_path / "s.json"))
        assert len(result) == 1

    def test_expired_silence_allows_through(self, tmp_path):
        """静默期到期后品种重新触发，过期条目被清理。"""
        past = datetime.date.today() - datetime.timedelta(days=31)
        silences = {"600001": past.isoformat()}  # 31 天前 → 已过期
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state(silences, f)

        signals = [
            {"type": "single_overflow", "code": "600001", "name": "A", "weight": 30.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=30, silence_file=f)
        assert len(result) == 1
        # 过期条目应从状态中清理
        remaining = _load_silence_state(f)
        assert "600001" not in remaining

    def test_update_silence_state_records_new(self, tmp_path):
        """新触发的信号写入静默期状态后再触发被过滤。"""
        f = str(tmp_path / "rebalance_silence.json")
        config = {"profile": "moderate", "_silence_file": f}
        holdings = [{"name": "A", "code": "600001", "market_value": 500}]
        # 第一次应触发
        result = compute_rebalance_signals(holdings, 1000, config)
        assert len(result) == 1
        # 第二次应被静默过滤
        result2 = compute_rebalance_signals(holdings, 1000, config)
        assert len(result2) == 0
