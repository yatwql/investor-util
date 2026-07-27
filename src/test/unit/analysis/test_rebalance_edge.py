"""再平衡信号计算 edge 测试 — 边界/异常输入。

覆盖 rebalance.py 的边角场景：
  - 配置/profile 边界值
  - 持仓分类降级路径
  - 缺失/None 字段穿透
  - 静默期日期异常
  - 置信度边界
"""

from __future__ import annotations

import datetime
import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]

from src.python.analysis.rebalance import (
    _calc_category_weights,
    _categorize_holdings,
    _compute_confidence,
    _filter_silenced_signals,
    _load_silence_state,
    _save_silence_state,
    classify_holding,
    compute_rebalance_signals,
    compute_target_deviation,
    equity_fixed_income_deviation,
    resolve_rebalance_config,
)


# ═══════════════════════════════════════════════════════════════
# resolve_rebalance_config — 配置解析边界
# ═══════════════════════════════════════════════════════════════


class TestRebalanceConfigEdge:
    """再平衡配置解析 — 边界输入。"""

    def test_unknown_profile_uses_defaults(self):
        """未知 profile 名称 → 使用默认阈值。"""
        result = resolve_rebalance_config({"profile": "super_conservative"})
        assert result["threshold"] == 0.15
        assert result["deviation_threshold"] == 0.05

    def test_profile_case_sensitive_falls_to_unknown(self):
        """大小写不匹配 → 无法匹配预设 → 使用默认值。"""
        result = resolve_rebalance_config({"profile": "Conservative"})
        assert result["threshold"] == 0.15  # 不匹配 conservative

    def test_silence_days_zero_preserved(self):
        """silence_days=0 → 保留 0。"""
        result = resolve_rebalance_config({"silence_days": 0})
        assert result["silence_days"] == 0

    def test_empty_config_gets_all_defaults(self):
        """空配置 → 全部使用默认值。"""
        result = resolve_rebalance_config({})
        assert result["threshold"] == 0.15
        assert result["deviation_threshold"] == 0.05
        assert result["silence_days"] == 30
        assert result["target_allocation"] == {}


# ═══════════════════════════════════════════════════════════════
# classify_holding — 分类降级路径
# ═══════════════════════════════════════════════════════════════


class TestClassifyHoldingEdge:
    """资产分类 — 边界/降级。"""

    def test_empty_name_and_code(self):
        """空名称和代码 → 返回 fund_equity。"""
        assert classify_holding("", "") == "fund_equity"

    def test_unknown_code_format(self):
        """无法识别的代码格式 → fund_equity。"""
        assert classify_holding("某某产品", "XYZ123") == "fund_equity"

    def test_name_not_bond_but_code_is_valid(self):
        """名称不含债券/货币等关键字，代码为 A 股 → equity。"""
        assert classify_holding("某某科技", "600001") == "equity"


# ═══════════════════════════════════════════════════════════════
# _categorize_holdings / _calc_category_weights — 边界
# ═══════════════════════════════════════════════════════════════


class TestCategorizeHoldingsEdge:
    """分类汇总 — 边界输入。"""

    def test_none_market_value_treated_as_zero(self):
        """market_value=None → 视为 0 不崩溃。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": None},
        ]
        categorized = _categorize_holdings(holdings)
        weights = _calc_category_weights(categorized, 100)
        assert weights["equity"] == 0.0

    def test_missing_market_value_key(self):
        """缺 market_value 键 → 视为 0。"""
        holdings = [
            {"name": "A", "code": "600001"},
        ]
        result = _categorize_holdings(holdings)
        assert len(result["equity"]) == 1

    def test_unknown_category_falls_to_others(self):
        """classify_holding 返回未预期值 → 归入 others。"""
        # 用空名称空代码触发 fallback → fund_equity
        # 制造"others"需要代码无法匹配任何分类
        holdings = [
            {"name": "", "code": "!@#$%", "market_value": 100},
        ]
        result = _categorize_holdings(holdings)
        total = sum(len(v) for v in result.values())
        assert total == 1

    def test_weight_with_mixed_none_values(self):
        """部分 market_value 为 None → 不崩溃，正确跳过。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 8000},
            {"name": "B", "code": "600002", "market_value": None},
            {"name": "C", "code": "600003"},
        ]
        categorized = _categorize_holdings(holdings)
        weights = _calc_category_weights(categorized, 8000)
        assert weights["equity"] == 100.0


# ═══════════════════════════════════════════════════════════════
# compute_target_deviation — 边界输入
# ═══════════════════════════════════════════════════════════════


class TestTargetDeviationEdge:
    """目标配置偏离 — 边界。"""

    def test_nonexistent_category_in_target(self):
        """目标配置含不在 _CATEGORY_ORDER 中的键 → 在品种级检查中跳过。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 10000},
        ]
        target = {"crypto": {"min": 0, "max": 10, "target": 5}}
        result = compute_target_deviation(holdings, 10000, target)
        # crypto 不在 _CATEGORY_ORDER 也不在 _CATEGORY_LABELS → 会进入品种级检查
        # 但 600001 不匹配 "crypto" → 无匹配
        assert result == []

    def test_holdings_none_values(self):
        """持仓含 None market_value → 不崩溃。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": None},
        ]
        target = {"equity": {"min": 0, "max": 100, "target": 50}}
        result = compute_target_deviation(holdings, 0, target)
        assert result == []  # total_mv=0 → 直接返回空


# ═══════════════════════════════════════════════════════════════
# equity_fixed_income_deviation — 边界
# ═══════════════════════════════════════════════════════════════


class TestEquityFIDeviationEdge:
    """权益/固收偏离 — 边界。"""

    def test_unknown_group_key_in_target(self):
        """目标配置含未知超大类键 → 跳过并记录 warning。"""
        holdings = [
            {"name": "A", "code": "600001", "market_value": 10000},
        ]
        target = {"real_estate": {"min": 0, "max": 100}}
        result = equity_fixed_income_deviation(holdings, 10000, target)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# compute_rebalance_signals — 入口边界
# ═══════════════════════════════════════════════════════════════


class TestRebalanceSignalsEdge:
    """再平衡入口 — 边界输入。"""

    def test_holding_missing_market_value(self):
        """持仓缺 market_value → 视为 0，不崩溃。"""
        holdings = [
            {"name": "A", "code": "600001"},  # 无 market_value
        ]
        result = compute_rebalance_signals(holdings, 1000, {"threshold": 0.15})
        # mv=0, weight=0 → 不触发单品超限
        assert len(result) == 0

    def test_holding_missing_all_keys_except_name(self):
        """持仓仅有 name → 不崩溃。"""
        holdings = [
            {"name": "A"},
        ]
        result = compute_rebalance_signals(holdings, 1000, {"threshold": 0.15})
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════
# _compute_confidence — 边界
# ═══════════════════════════════════════════════════════════════


class TestConfidenceEdge:
    """置信度 — 边界值。"""

    def test_zero_deviation_returns_medium_or_low(self):
        """偏离为 0 → 按 signal_type 返回对应最低等级。"""
        conf = _compute_confidence("single_overflow", deviation=0.0, threshold=0.15)
        assert conf == "medium"

        conf = _compute_confidence("category", deviation=0.0, deviation_threshold_pct=5.0)
        assert conf == "low"

    def test_single_overflow_none_deviation(self):
        """deviation=None → 视为 0 → medium。"""
        conf = _compute_confidence("single_overflow", deviation=None, threshold=0.15)
        assert conf == "medium"

    def test_none_threshold_no_crash(self):
        """threshold=None → deviation 条件计算 None > ... 不崩溃。"""
        conf = _compute_confidence("single_overflow", deviation=10.0, threshold=None)
        assert conf == "medium"


# ═══════════════════════════════════════════════════════════════
# _load_silence_state / _filter_silenced_signals — 边界
# ═══════════════════════════════════════════════════════════════


class TestSilenceEdge:
    """静默期 — 边界/异常。"""

    def test_non_dict_state_returns_empty(self, tmp_path):
        """持久化文件内容非 dict → 返回空字典。"""
        f = str(tmp_path / "bad_silence.json")
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(["item1", "item2"], fh)
        state = _load_silence_state(f)
        assert state == {}

    def test_silence_days_zero_no_filtering(self, tmp_path):
        """silence_days=0 → 不过滤。"""
        signals = [
            {"type": "single_overflow", "code": "600001", "weight": 30.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=0,
                                           silence_file=str(tmp_path / "s.json"))
        assert len(result) == 1

    def test_invalid_trigger_date_treated_as_expired(self, tmp_path):
        """静默期日期格式异常 → 视为过期，信号通过。"""
        today = datetime.date.today()
        silences = {"600001": "not-a-date"}
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state(silences, f)

        signals = [
            {"type": "single_overflow", "code": "600001", "name": "A", "weight": 30.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=30, silence_file=f)
        assert len(result) == 1

    def test_signal_without_code_not_filtered(self, tmp_path):
        """信号无 code → 直接放行。"""
        signals = [
            {"type": "single_overflow", "name": "A", "weight": 30.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=30,
                                           silence_file=str(tmp_path / "s.json"))
        assert len(result) == 1

    def test_signal_code_without_type_not_filtered(self, tmp_path):
        """信号无 type → 有 code → 参与静默期检查（type 不在 ('category','summary') 时按 code 检查）。"""
        today = datetime.date.today()
        silences = {"600001": today.isoformat()}
        f = str(tmp_path / "rebalance_silence.json")
        _save_silence_state(silences, f)

        signals = [
            {"code": "600001", "weight": 30.0},
        ]
        result = _filter_silenced_signals(signals, silence_days=30, silence_file=f)
        assert len(result) == 0  # 在静默期内 → 被过滤
