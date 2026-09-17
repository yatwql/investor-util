"""信号预消化模块边缘场景测试 — 畸形输入、极端值、类型越界。

正常路径见 test_prompts_signals.py；本文件只覆盖异常输入，且验证的核心语义是
**不抛异常 + 退化为无信号**（数据降级已在数据源侧披露，此处不重复告警）。

运行：
  pytest src/test/unit/llm/test_prompts_signals_edge.py -v
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.edge]


class TestSectorFlowBlockEdge:
    """_build_sector_flow_block：畸形行业行与极端净额。"""

    def test_non_dict_rows_ignored(self):
        """列表里混入非 dict 项 → 跳过，其余正常输出。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([None, "银行", 123, {"name": "医药", "main_net_inflow": -1e6}])

        assert "医药" in text
        assert "主力净流出100.0万" in text

    def test_all_non_dict_returns_empty(self):
        """全部为非 dict → 空串。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        assert _build_sector_flow_block([None, "x", 1]) == ""

    def test_bool_net_amount_treated_as_no_direction(self):
        """bool 是 int 的子类，但不应被当作净额（True 会被误读为 +1 元）。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([{"name": "银行", "main_net_inflow": True}])

        assert "银行" in text
        assert "主力净流入1元" not in text
        assert "True" not in text

    def test_zero_and_missing_net_fall_back_to_source_order(self):
        """全为 0 / 缺失净额 → 无方向可分，退回原始顺序前 N 行。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        rows = [{"name": f"行业{i}", "main_net_inflow": 0} for i in range(5)]
        text = _build_sector_flow_block(rows)

        assert "净流入前列：" not in text
        assert "净流出前列：" not in text
        assert text.index("行业0") < text.index("行业1") < text.index("行业2")
        assert "行业3" not in text

    def test_missing_net_key_falls_back(self):
        """完全缺失 main_net_inflow 键 → 同样走无方向回退。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([{"name": "银行", "change_pct": 1.0}])

        assert "银行" in text
        assert "主力净流入" not in text

    def test_extreme_negative_net_amount(self):
        """极端净额（-99 亿）仍以「净流出 99.00亿」表述，无负号溢出。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([{"name": "全市场", "main_net_inflow": -9.9e9}])

        assert "主力净流出99.00亿" in text
        assert "-" not in text.split("净流出")[1]

    def test_nan_net_amount_is_neutral(self):
        """NaN 净额不参与方向判定（NaN 的比较全为假 → 中性）。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([{"name": "银行", "main_net_inflow": float("nan")}])

        assert "银行" in text
        assert "主力净流入" not in text and "主力净流出" not in text

    def test_non_numeric_change_pct_omitted(self):
        """涨跌幅为字符串 → 省略该字段而非格式化报错。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([{"name": "银行", "change_pct": "--", "main_net_inflow": 1e6}])

        assert "银行" in text
        assert "涨跌" not in text


class TestSignalDigestBlockEdge:
    """_build_signal_digest_block：pipeline_data 结构畸形与数值越界。"""

    def test_non_dict_pipeline_data(self):
        """pipeline_data 非 dict → 空串，不抛异常。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        assert _build_signal_digest_block([]) == ""
        assert _build_signal_digest_block("数据") == ""

    def test_source_value_wrong_type(self):
        """数据源键存在但值非 dict → 跳过该项。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        assert _build_signal_digest_block({"market_temperature_data": "低估"}) == ""
        assert _build_signal_digest_block({"tail_risk_data": [1.0]}) == ""

    def test_temperature_missing_tier_skipped(self):
        """available 为真但缺 tier → 跳过（无档位即无从判方向）。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        assert _build_signal_digest_block({"market_temperature_data": {"available": True, "score": 30.0}}) == ""

    def test_temperature_unknown_tier_is_neutral(self):
        """未知档位词 → 中性，不误判为看多。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block(
            {"market_temperature_data": {"available": True, "tier": "未知档", "index_name": "沪深300"}}
        )

        assert "中性" in text
        assert "（未知档）" in text

    def test_temperature_non_numeric_score(self):
        """温度分为非数值 → 括号内只留档位词，不格式化报错。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block(
            {"market_temperature_data": {"available": True, "tier": "低估", "score": "--"}}
        )

        assert "信号：市场温度" in text
        assert "（低估）" in text

    def test_valuation_ignores_non_dict_entries_and_unknown_tiers(self):
        """by_code 内非 dict 项与未知档位不计入统计。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        by_code = {"A": {"tier": "低估"}, "B": None, "C": {"tier": "未知"}, "D": "低估"}
        text = _build_signal_digest_block({"valuation_data": {"available": True, "by_code": by_code}})

        assert "低估1只" in text
        assert "未知" not in text

    def test_valuation_empty_by_code_skipped(self):
        """by_code 为空 dict → 跳过。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        assert _build_signal_digest_block({"valuation_data": {"available": True, "by_code": {}}}) == ""

    def test_tail_risk_non_numeric_var95_skipped(self):
        """VaR95 非数值 → 跳过（其余字段不足以定档）。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        assert _build_signal_digest_block({"tail_risk_data": {"available": True, "var95": None}}) == ""

    def test_tail_risk_negative_var95_low_band(self):
        """VaR95 为负（理论上不应出现）→ 落入风险低档，不报错。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block({"tail_risk_data": {"available": True, "var95": -1.0}})

        assert "风险低" in text

    def test_tail_risk_missing_optional_fields(self):
        """只有 VaR95 时括号内只剩一项，无多余分隔符。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block({"tail_risk_data": {"available": True, "var95": 1.0}})

        assert text.splitlines()[-1].endswith("（VaR95 1.00%）")
        assert "，" not in text.splitlines()[-1]


class TestSignalDigestCacheSuffixEdge:
    """_signal_digest_cache_suffix：开关关闭时即使数据畸形也无感。"""

    def test_disabled_with_malformed_data(self):
        """开关关闭 → 直接空串，不触碰畸形数据。"""
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        assert _signal_digest_cache_suffix({"tail_risk_data": object()}) == ""

    def test_enabled_with_malformed_data(self):
        """开关开启 + 畸形数据 → 退化为空串，不抛异常。"""
        from src.python.config.features import FEATURE_FLAGS
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        FEATURE_FLAGS["signal_pre_digest"] = True
        assert _signal_digest_cache_suffix({"tail_risk_data": object()}) == ""
        assert _signal_digest_cache_suffix([1, 2]) == ""

    def test_enabled_with_unserializable_extra_keys(self):
        """pipeline_data 含不可 JSON 序列化的兄弟键 → 指纹仍可算出（只取信号文本）。"""
        from src.python.config.features import FEATURE_FLAGS
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        FEATURE_FLAGS["signal_pre_digest"] = True
        suffix = _signal_digest_cache_suffix({"tail_risk_data": {"available": True, "var95": 1.0}, "other": object()})

        assert suffix.startswith("_") and len(suffix) == 13
