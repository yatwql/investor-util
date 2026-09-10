"""信号预消化模块单元测试 — 资金流方向标注、算法评级信号块、缓存后缀与开关接线。

覆盖：
  - _build_sector_flow_block：方向词 + 非负量（裸值歧义缺陷回归）、分方向排名、
    每方向 TOP N 截断、空输入
  - _build_signal_digest_block：市场温度 / 估值分位 / 尾部风险三路信号与降级跳过
  - _signal_digest_cache_suffix：开关关闭无感、内容变化换键、确定性
  - _build_expert_review_prompt / _build_health_check_prompt 的 enable_signal_digest 注入
  - generate_expert_review / generate_health_check 的指纹后缀接线

运行：
  pytest src/test/unit/llm/test_prompts_signals.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]

_SECTOR_FLOW = [
    {"name": "银行", "change_pct": 1.2, "main_net_inflow": 5_000_000, "main_net_inflow_pct": 2.5},
    {"name": "医药", "change_pct": -1.1, "main_net_inflow": -120_000_000, "main_net_inflow_pct": -6.0},
    {"name": "白酒", "change_pct": -3.4, "main_net_inflow": -8_200_000, "main_net_inflow_pct": -4.1},
    {"name": "半导体", "change_pct": 0.3, "main_net_inflow": 300, "main_net_inflow_pct": 0.01},
    {"name": "地产", "change_pct": 2.0, "main_net_inflow": 9_000, "main_net_inflow_pct": 0.9},
]


# ═══════════════════════════════════════════════════════════════
#  行业资金流向：方向词 + 分方向排名
# ═══════════════════════════════════════════════════════════════


class TestSectorFlowBlock:
    """_build_sector_flow_block：方向由词承担、数值非负、按净额排名。"""

    def test_net_outflow_uses_word_not_negative_number(self):
        """回归：净流出行业表述为「主力净流出 1.20亿」，不再出现「主力净流入-120000000」。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block(_SECTOR_FLOW)

        assert "主力净流出1.20亿" in text
        # 旧缺陷表述：固定 label + 负号数值
        assert "主力净流入-" not in text
        assert "-120,000,000" not in text

    def test_net_inflow_keeps_positive_magnitude(self):
        """净流入行业保留「主力净流入」词与正量。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block(_SECTOR_FLOW)

        assert "银行" in text
        assert "主力净流入500.0万" in text

    def test_each_direction_sorted_by_net_amount(self):
        """净流入组按净额降序、净流出组按净额升序（数据源本身无序）。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block(_SECTOR_FLOW)
        inflow_part, outflow_part = text.split("净流出前列：")

        # 净流入降序：银行 500万 > 地产 9,000 > 半导体 300
        assert inflow_part.index("银行") < inflow_part.index("地产") < inflow_part.index("半导体")
        # 净流出升序（最弱在前）：医药 1.2亿 > 白酒 820万
        assert outflow_part.index("医药") < outflow_part.index("白酒")

    def test_both_directions_shown_on_all_outflow_day(self):
        """全市场净流出时仍能看到净流出前列（不因只取降序前 N 而丢掉风险侧）。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        rows = [{"name": f"行业{i}", "main_net_inflow": -float(i + 1) * 1e6} for i in range(6)]
        text = _build_sector_flow_block(rows)

        assert "净流出前列：" in text
        assert "净流入前列：" not in text
        # 净额最负（行业5，-600万）排最前，截断后行业0/1/2 不展示
        assert text.index("行业5") < text.index("行业4") < text.index("行业3")
        assert "行业0" not in text

    def test_top_n_per_direction(self):
        """每方向最多展示 SECTOR_FLOW_TOP_N 个行业。"""
        from src.python.llm.prompts_signals import SECTOR_FLOW_TOP_N, _build_sector_flow_block

        rows = [{"name": f"入{i}", "main_net_inflow": float(i + 1) * 1e6} for i in range(6)]
        rows += [{"name": f"出{i}", "main_net_inflow": -float(i + 1) * 1e6} for i in range(6)]
        text = _build_sector_flow_block(rows)

        assert text.count("主力净流入") == SECTOR_FLOW_TOP_N
        assert text.count("主力净流出") == SECTOR_FLOW_TOP_N

    def test_empty_input_returns_empty_string(self):
        """空 / None 输入返回空串（调用方据此跳过拼接）。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        assert _build_sector_flow_block(None) == ""
        assert _build_sector_flow_block([]) == ""

    def test_missing_change_pct_omitted(self):
        """涨跌幅缺失时不输出「涨跌None%」，其余字段照常。"""
        from src.python.llm.prompts_signals import _build_sector_flow_block

        text = _build_sector_flow_block([{"name": "银行", "main_net_inflow": 5_000_000}])

        assert "银行" in text
        assert "涨跌" not in text
        assert "None" not in text


class TestFmtAmount:
    """_fmt_amount：万/亿 沿用，未达万级补「元」防止裸数字无单位。"""

    def test_wan_and_yi_units(self):
        from src.python.llm.prompts_signals import _fmt_amount

        assert _fmt_amount(500_000) == "50.0万"
        assert _fmt_amount(120_000_000) == "1.20亿"

    def test_below_wan_gets_yuan_unit(self):
        from src.python.llm.prompts_signals import _fmt_amount

        assert _fmt_amount(9000) == "9,000元"


# ═══════════════════════════════════════════════════════════════
#  算法评级信号块
# ═══════════════════════════════════════════════════════════════


class TestSignalDigestBlock:
    """_build_signal_digest_block：三路信号的方向词与降级跳过。"""

    def test_no_signal_returns_empty_string(self):
        """无可用数据 → 空串（不注入即无感）。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        assert _build_signal_digest_block(None) == ""
        assert _build_signal_digest_block({}) == ""
        assert _build_signal_digest_block({"market_temperature_data": {"available": False}}) == ""

    def test_market_temperature_tier_maps_to_direction(self):
        """低估→看多 / 合理→中性 / 高估→看空。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        def _block(tier):
            return _build_signal_digest_block(
                {"market_temperature_data": {"available": True, "tier": tier, "score": 30.0, "index_name": "沪深300"}}
            )

        assert "市场温度（沪深300） 看多" in _block("低估")
        assert "市场温度（沪深300） 中性" in _block("合理")
        assert "市场温度（沪深300） 看空" in _block("高估")

    def test_valuation_majority_determines_direction(self):
        """估值分位按档位数量多数决；并给出「几只低估」分布。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        by_code = {
            "A": {"tier": "低估"},
            "B": {"tier": "低估"},
            "C": {"tier": "合理"},
            "D": {"tier": "高估"},
        }
        text = _build_signal_digest_block({"valuation_data": {"available": True, "by_code": by_code}})

        assert "持仓估值分位 看多" in text
        assert "低估2只" in text and "合理1只" in text and "高估1只" in text

    def test_valuation_tie_is_neutral(self):
        """低估与高估数量并列 → 中性（不硬造方向）。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        by_code = {"A": {"tier": "低估"}, "B": {"tier": "高估"}}
        text = _build_signal_digest_block({"valuation_data": {"available": True, "by_code": by_code}})

        assert "持仓估值分位 中性" in text

    def test_tail_risk_uses_risk_axis_not_direction_axis(self):
        """尾部风险用风险高/中/低，不套「看空」（方向与幅度正交）。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block(
            {"tail_risk_data": {"available": True, "var95": 3.5, "max_single_day_drop": -4.2, "consecutive_down_days": 3}}
        )

        assert "尾部风险 风险高" in text
        assert "看空" not in text
        assert "VaR95 3.50%" in text

    def test_tail_risk_bands(self):
        """VaR95 分档：<1.5 低 / 1.5~3.0 中 / >=3.0 高。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        def _verdict(var95):
            text = _build_signal_digest_block({"tail_risk_data": {"available": True, "var95": var95}})
            return text.splitlines()[-1].split(" ")[1].split("（")[0]

        assert _verdict(1.49) == "风险低"
        assert _verdict(1.5) == "风险中"
        assert _verdict(2.99) == "风险中"
        assert _verdict(3.0) == "风险高"

    def test_multiple_signals_joined_under_one_header(self):
        """多路信号共用一个「【确定性信号】」头，逐行列出。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block(
            {
                "market_temperature_data": {"available": True, "tier": "低估", "score": 20.0, "index_name": "沪深300"},
                "tail_risk_data": {"available": True, "var95": 1.0},
            }
        )
        lines = text.splitlines()

        assert text.count("【确定性信号】") == 1
        assert len(lines) == 3
        assert all(line.startswith("信号：") for line in lines[1:])

    def test_unavailable_source_skipped_others_kept(self):
        """单路不可用只跳过该路，不阻断其余信号。"""
        from src.python.llm.prompts_signals import _build_signal_digest_block

        text = _build_signal_digest_block(
            {
                "market_temperature_data": {"available": False},
                "tail_risk_data": {"available": True, "var95": 1.0},
            }
        )

        assert "市场温度" not in text
        assert "尾部风险" in text


# ═══════════════════════════════════════════════════════════════
#  缓存指纹后缀
# ═══════════════════════════════════════════════════════════════


class TestSignalDigestCacheSuffix:
    """_signal_digest_cache_suffix：开关关闭无感、内容变则键变、确定性。"""

    _SIGNAL_DATA = {"market_temperature_data": {"available": True, "tier": "低估", "score": 20.0}}

    def test_disabled_returns_empty(self):
        """开关关闭 → 空后缀（缓存键与未注入信号时逐字节一致）。"""
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        assert _signal_digest_cache_suffix(self._SIGNAL_DATA) == ""

    def test_enabled_without_signal_returns_empty(self):
        """开关开启但无可用信号 → 仍是空后缀（不误伤旧缓存）。"""
        from src.python.config.features import FEATURE_FLAGS
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        FEATURE_FLAGS["signal_pre_digest"] = True
        assert _signal_digest_cache_suffix({}) == ""

    def test_enabled_with_signal_returns_deterministic_suffix(self):
        """开关开启且有信号 → 定长后缀，同输入同输出。"""
        from src.python.config.features import FEATURE_FLAGS
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        FEATURE_FLAGS["signal_pre_digest"] = True
        first = _signal_digest_cache_suffix(self._SIGNAL_DATA)
        second = _signal_digest_cache_suffix(self._SIGNAL_DATA)

        assert first == second
        assert first.startswith("_")
        assert len(first) == 13

    def test_signal_change_changes_suffix(self):
        """信号内容变化 → 后缀变化（提示词变了缓存键必须跟着变）。"""
        from src.python.config.features import FEATURE_FLAGS
        from src.python.llm.prompts_signals import _signal_digest_cache_suffix

        FEATURE_FLAGS["signal_pre_digest"] = True
        other = {"market_temperature_data": {"available": True, "tier": "高估", "score": 80.0}}

        assert _signal_digest_cache_suffix(self._SIGNAL_DATA) != _signal_digest_cache_suffix(other)


# ═══════════════════════════════════════════════════════════════
#  提示词注入（enable_signal_digest）
# ═══════════════════════════════════════════════════════════════

_SIGNAL_PIPELINE_DATA = {"tail_risk_data": {"available": True, "var95": 3.5}}


class TestPromptSignalInjection:
    """两个承接模块的提示词在开关开启时才携带信号块。"""

    @staticmethod
    def _expert_review(**kwargs):
        from src.python.llm.prompts_action import _build_expert_review_prompt

        return _build_expert_review_prompt(
            100000.0,
            90000.0,
            10000.0,
            500.0,
            2,
            {"股票": 2},
            None,
            holdings_details=[{"name": "示例", "code": "600519", "cost": 100.0}],
            pipeline_data=_SIGNAL_PIPELINE_DATA,
            **kwargs,
        )

    @staticmethod
    def _health_check(**kwargs):
        from src.python.llm.prompts_action import _build_health_check_prompt

        return _build_health_check_prompt(
            100000.0,
            90000.0,
            10000.0,
            500.0,
            2,
            {"股票": 2},
            None,
            holdings_details=[{"name": "示例", "code": "600519", "cost": 100.0}],
            pipeline_data=_SIGNAL_PIPELINE_DATA,
            **kwargs,
        )

    def test_expert_review_default_has_no_signal_block(self):
        """默认关闭：提示词不含【确定性信号】（与既有内容逐字节一致）。"""
        assert "【确定性信号】" not in self._expert_review()

    def test_expert_review_with_flag_on_injects_block(self):
        """开启：提示词含信号块，且位于持仓明细之前（先结论后明细）。"""
        text = self._expert_review(enable_signal_digest=True)

        assert "信号：尾部风险 风险高" in text
        assert text.index("【确定性信号】") < text.index("【持仓明细】")

    def test_health_check_default_has_no_signal_block(self):
        assert "【确定性信号】" not in self._health_check()

    def test_health_check_with_flag_on_injects_block(self):
        assert "信号：尾部风险 风险高" in self._health_check(enable_signal_digest=True)

    def test_global_macro_prompt_carries_flow_direction_words(self):
        """全球政经局势提示词的资金流段输出方向词（无开关，属缺陷修复）。"""
        from src.python.llm.prompts_action import _build_global_macro_prompt

        text = _build_global_macro_prompt(
            {"000001": {"name": "上证", "price": 3000, "change_pct": 0.5}},
            {"DJI": {"name": "道指", "price": 40000, "change_pct": -0.2}},
            100000.0,
            10000.0,
            90000.0,
            {"股票": 2},
            sector_flow=_SECTOR_FLOW,
        )

        assert "主力净流出1.20亿" in text
        assert "主力净流入-" not in text


# ═══════════════════════════════════════════════════════════════
#  生成层接线：指纹后缀
# ═══════════════════════════════════════════════════════════════


class TestGeneratorFingerprintWiring:
    """generate_expert_review / generate_health_check 的指纹随信号块变化。"""

    _BASE_KWARGS = {
        "total_mv": 100000.0,
        "total_cost": 90000.0,
        "total_profit": 10000.0,
        "total_today_profit": 500.0,
        "holdings_count": 2,
        "categories": {"股票": 2},
        "penetrated_assets": None,
        "holdings_details": [{"name": "示例", "code": "600519", "cost": 100.0}],
    }

    @staticmethod
    def _captured_fingerprints(generator_name, **extra):
        """调用生成函数并返回其传给 skeleton 的指纹闭包输出。"""
        from src.python.llm import generators

        with patch.object(generators, "generate_llm_module") as mock_gen:
            mock_gen.return_value = ("内容", False)
            getattr(generators, generator_name)(**{**TestGeneratorFingerprintWiring._BASE_KWARGS, **extra})
            return mock_gen.call_args.kwargs["fingerprint_fn"]()

    @pytest.mark.parametrize("generator_name", ["generate_expert_review", "generate_health_check"])
    def test_flag_off_fingerprint_unchanged(self, generator_name):
        """开关关闭：有无信号数据都不进指纹（键不变、不误伤旧缓存）。"""
        without_signal = self._captured_fingerprints(generator_name, pipeline_data=None)
        with_signal = self._captured_fingerprints(generator_name, pipeline_data=_SIGNAL_PIPELINE_DATA)

        assert without_signal == with_signal

    @pytest.mark.parametrize("generator_name", ["generate_expert_review", "generate_health_check"])
    def test_flag_on_fingerprint_follows_signal(self, generator_name):
        """开关开启：信号内容变 → 指纹变（提示词变了缓存键必须跟着变）。"""
        from src.python.config.features import FEATURE_FLAGS

        FEATURE_FLAGS["signal_pre_digest"] = True
        high_risk = self._captured_fingerprints(generator_name, pipeline_data=_SIGNAL_PIPELINE_DATA)
        low_risk = self._captured_fingerprints(
            generator_name, pipeline_data={"tail_risk_data": {"available": True, "var95": 0.5}}
        )

        assert high_risk != low_risk

    def test_orchestrator_precheck_applies_same_suffix(self):
        """预检侧与写侧同调同一后缀函数（读写键同源的表达一致）。"""
        from src.python.config.features import FEATURE_FLAGS
        from src.python.llm.generators_orchestrator import _compute_module_cache_info

        FEATURE_FLAGS["signal_pre_digest"] = True
        high = _compute_module_cache_info(
            {},
            {},
            {},
            100000.0,
            90000.0,
            10000.0,
            500.0,
            2,
            {"股票": 2},
            None,
            self._BASE_KWARGS["holdings_details"],
            False,
            pipeline_data=_SIGNAL_PIPELINE_DATA,
        )
        low = _compute_module_cache_info(
            {},
            {},
            {},
            100000.0,
            90000.0,
            10000.0,
            500.0,
            2,
            {"股票": 2},
            None,
            self._BASE_KWARGS["holdings_details"],
            False,
            pipeline_data={"tail_risk_data": {"available": True, "var95": 0.5}},
        )

        assert high["expert_review"]["key"] != low["expert_review"]["key"]
        assert high["health_check"]["key"] != low["health_check"]["key"]
        # 穿透深度分析不承接信号块 → 键不受影响
        assert high["penetration_deep"]["key"] == low["penetration_deep"]["key"]
