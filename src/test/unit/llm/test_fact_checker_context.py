"""LLM 事实锚定校验器 — 上下文归属与自动纠错场景。

覆盖场景：
  - 表格行排名归因、纠错上下文截断、显式主体优先于全局就近
  - 名称主体就近、别名归一化、描述性尾部匹配、多主体归因
  - 代码错字自动纠错与告警阈值上下文

运行：
  pytest src/test/unit/llm/test_fact_checker_context.py -v
"""

from __future__ import annotations

import pytest

from src.python.llm.fact_checker import (
    check_numerical_consistency,
    check_ranking_correctness,
    run_fact_check,
)
from src.python.llm.fact_checker._corrections import (
    apply_code_corrections,
    detect_code_corrections,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
]


class TestTableRowRankAttribution:
    """表格行内排名声称归因到品种名列，而非行内后出现的比较对象。

    LLM 调仓表行："...|| 🔴 高 | 040046 华安纳斯达克100ETF联接A |
    减仓1/3 | 当前占比11.3%为第一重仓，与016055高度同质；...||"。
    "第一重仓"声称指向品种名列 040046，行内同单元格的比较对象 016055
    虽离声称词更近，仍应归因到品种名列。
    """

    # 用真实句段：|| 触发 _ROW_SEP_PATTERN 表格分支，行段内 040046 在声称词前
    TABLE_ROW = (
        ":--------:|------|| 🔴 高 | 040046 华安纳斯达克100ETF联接A | "
        "减仓1/3（约1.3万） | 当前占比11.3%为第一重仓，与016055高度同质；"
        "锁定QDII盈利 || 🔴 高 | 016055 博时纳斯达克100ETF联接A"
    )

    def _make_holdings(self) -> list[dict]:
        return [
            {"name": "华安纳斯达克100ETF联接A", "code": "040046", "market_value": 50000.0, "cost": 40000.0},
            {"name": "博时纳斯达克100ETF联接A", "code": "016055", "market_value": 30000.0, "cost": 25000.0},
        ]

    def test_claimed_to_prior_cell_code(self):
        """声称"第一重仓"归因 040046（品种名列，实际第一）→ 通过，无误报 016055。"""
        issues, checked, passed = check_ranking_correctness(self.TABLE_ROW, self._make_holdings())
        assert checked == 1
        assert passed == 1
        assert issues == []  # 归因到品种名列，无误报"016055 为最大持仓"

    def test_wrong_claim_references_subject_code(self):
        """声称主体不在第一时，告警引用品种名列（声称主体），而非比较对象。"""
        holdings = [
            {"name": "华安纳斯达克100ETF联接A", "code": "040046", "market_value": 30000.0, "cost": 25000.0},
            {"name": "博时纳斯达克100ETF联接A", "code": "016055", "market_value": 50000.0, "cost": 40000.0},
        ]
        issues, checked, passed = check_ranking_correctness(self.TABLE_ROW, holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        # 告警应指向声称主体 040046，并提示实际第一为 016055
        assert "040046" in issues[0]
        assert "016055" in issues[0]
        assert "040046" in issues[0] and issues[0].startswith("声称 040046")


# ── 非收益率语境不被误修正 + 亏损品种符号保留 ──


class TestFalseCorrectionContexts:
    """胜率/权重/相对指数差等非收益率百分比不误判为收益率；
    亏损品种修正时保留负号。

    胜率/评分权重/相对指数差均非收益率，不得与持仓收益率比较；
    亏损品种（如 518880 实际 -8.86%）修正时必须保留负号，不得输出 +8.9%。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @pytest.fixture
    def real_holdings(self) -> list[dict]:
        """真实组合子集：各品种 profit_rate 为百分单位（含正负），含市值/成本。

        market_value = cost × (1 + profit_rate/100)，组合整体盈利，
        确保数值校验不会因组合 profit_rate<0.01 被整体跳过。
        """
        return [
            {"name": "长江电力", "code": "600900", "market_value": 160.62, "cost": 100.0, "profit_rate": 60.62},
            {"name": "工商银行", "code": "601398", "market_value": 173.81, "cost": 100.0, "profit_rate": 73.81},
            {"name": "建设银行", "code": "601939", "market_value": 278.36, "cost": 100.0, "profit_rate": 178.36},
            {"name": "黄金ETF华安", "code": "518880", "market_value": 91.14, "cost": 100.0, "profit_rate": -8.86},
            {"name": "华宝增强债券A", "code": "240012", "market_value": 102.24, "cost": 100.0, "profit_rate": 2.24},
            {"name": "永赢科技智选C", "code": "022365", "market_value": 116.64, "cost": 100.0, "profit_rate": 16.64},
        ]

    def test_win_rate_not_corrected(self, real_holdings):
        """「持仓胜率80%」是品种盈利比例（非收益率）→ 不修正。

        句子含「盈利」会触发收益语境，但数值本身是胜率。
        """
        text = "双方一致认可组合整体盈利能力和分散化结构（胜率80%、HHI仅0.0792）。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"胜率不应被误修正: {corrections}"

    def test_score_weight_not_corrected(self, real_holdings):
        """「风险分散度权重20%」是评分权重（非收益率）→ 不修正。"""
        text = "风险分散度权重20%、收益合理性权重25%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"权重不应被误修正: {corrections}"

    def test_underperform_index_not_corrected(self, real_holdings):
        """「跑输沪深300达1.10%」是相对指数的表现差（非收益率）→ 不修正。

        句子尾部「收益平平」会触发收益语境，但开头的 1.10% 是相对基准差。
        """
        text = "组合今日跑输沪深300达1.10%，主要受低波动红利资产拖累，而夏普比率仅0.09显示风险调整后收益平平。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"跑输指数差不应被误修正: {corrections}"

    def test_losing_position_correction_keeps_sign(self, real_holdings):
        """亏损品种（518880 实际 -8.86%）被修正时输出带负号。

        修正输出用带符号收益率，不得把亏损写成盈利（+8.9%）。
        """
        text = "华安黄金ETF（518880）收益率为 80%，表现突出。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert len(corrections) == 1
        assert corrections[0][0] == "80"
        assert corrections[0][1] == "-8.9"
        assert "518880" in corrections[0][3]

    def test_win_rate_run_fact_check_not_rewritten(self, real_holdings):
        """run_fact_check 整链路：胜率不被自动修正，摘要无修正明细。

        胜率是盈利品种占比，不应被改写为任何品种收益率。
        """
        html = "<p>双方一致认可组合整体盈利能力和分散化结构（胜率80%、HHI仅0.0792）。</p>"
        corr, summ = run_fact_check(html, real_holdings, "智囊团深度复盘")
        assert "80%" in corr
        assert "8.9%" not in corr
        assert "已修正明细" not in summ


# ── 句中明确主体优先于全局最近邻 ──


class TestExplicitSubjectBeatsGlobalNearest:
    """句中明确指代某品种（代码/名称）时，按该品种实际收益率校验，
    不落入全局最近邻——否则句中已写明确主体、数值却接近无关品种时漏检。

    场景：601939 实际 1.87%、240012 实际 2.24%（两品种差 0.37 < 2×容差），
    「建设银行收益率 3.2%」：3.2 与 240012 差 0.96≤容差（全局最近邻判定通过），
    但与句中主体 601939 差 1.33>容差 → 应修正为 601939 的 1.9%。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @staticmethod
    def _close_pair_holdings() -> list[dict]:
        """两品种收益率差 0.37（<2×容差），用于"接近无关品种"的场景。"""
        return [
            {"name": "建设银行", "code": "601939", "market_value": 101.87, "cost": 100.0, "profit_rate": 1.87},
            {"name": "华宝增强债券A", "code": "240012", "market_value": 102.24, "cost": 100.0, "profit_rate": 2.24},
        ]

    def test_explicit_name_wrong_value_corrected_to_subject(self):
        """句中以名称指代主体且数值偏离 → 按主体收益率修正，而非按无关品种通过。"""
        holdings = self._close_pair_holdings()
        text = "建设银行收益率为 3.2%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert len(corrections) == 1, f"句中主体 601939 偏差超容差，应被检出: {corrections}"
        assert corrections[0][0] == "3.2"
        assert corrections[0][1] == "1.9"
        assert "601939" in corrections[0][3]

    def test_explicit_code_wrong_value_corrected_to_subject(self):
        """句中以代码指代主体且数值偏离 → 按主体收益率修正。"""
        holdings = self._close_pair_holdings()
        text = "华宝增强债券A（240012）收益率为 3.9%。"
        # 3.9 与 601939 的 1.87 差 2.03、与组合 2.055 差 1.845，均 > 容差；
        # 与主体 240012 的 2.24 差 1.66 > 容差 → 应按 240012 修正。
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert len(corrections) == 1
        assert corrections[0][1] == "2.2"
        assert "240012" in corrections[0][3]

    def test_explicit_name_right_value_passes(self):
        """句中主体数值与主体实际一致（容差内）→ 通过，不误修。"""
        holdings = self._close_pair_holdings()
        text = "建设银行收益率为 1.8%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"主体数值本就接近实际，不应修正: {corrections}"

    def test_no_subject_falls_back_to_global_nearest(self):
        """句中无任何持仓主体 → 按全局最近邻判定。"""
        holdings = self._close_pair_holdings()
        # 组合收益率 (101.87+102.24-200)/200*100 = 2.055；2.2 与组合差 0.145≤容差 → 通过
        text = "组合当前收益率为 2.2%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"无主体时全局最近邻应判定一致: {corrections}"

    def test_subject_without_rate_data_falls_back(self):
        """句中主体在持仓中但无收益率数据 → 回退全局最近邻，不崩溃。"""
        holdings = self._close_pair_holdings() + [
            {"name": "永赢科技智选C", "code": "022365", "market_value": 100.0, "cost": 100.0},
        ]
        # 022365 无 profit_rate → 不在 stock_rates_abs；句子提到它但无法校验，
        # 全局最近邻（2.4 与组合 1.87~2.05 区间接近）不误报。
        text = "永赢科技智选C（022365）收益率为 2.4%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert not any("022365" in c[3] for c in corrections), f"无数据主体不应被修正: {corrections}"


# ── 止盈/减仓目标比例不被误修正 ──


class TestTrimTargetContext:
    """止盈/减仓/止损等调仓目标比例（非收益率）不被误修正。

    调仓建议中"建议止盈约30%持仓""减仓约20%该持仓"等数值是相对当前持仓的
    目标调仓比例，与收益率（相对成本）维度不同。句子常含"利润/盈利/收益"
    等词触发收益语境，本识别将此类比例归为目标调仓比例、与收益率区分，
    避免与品种收益率混淆。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @pytest.fixture
    def real_holdings(self) -> list[dict]:
        """真实组合子集：601398/601939/600900 收益率与真实持仓一致（百分单位）。"""
        return [
            {"name": "长江电力", "code": "600900", "market_value": 22140.0, "cost": 14120.0, "profit_rate": 56.83},
            {"name": "工商银行", "code": "601398", "market_value": 15000.0, "cost": 8814.0, "profit_rate": 70.18},
            {"name": "建设银行", "code": "601939", "market_value": 19800.0, "cost": 7300.0, "profit_rate": 171.23},
        ]

    def test_trim_target_range_not_corrected(self, real_holdings):
        """真实报告复现：止盈约30-40%/20-30%不误修正。

        原缺陷触发句：整段无句号合成一句，含"利润"触发收益语境，
        30%/40% 被当收益率修正为最近邻 601398 的 70.2%。
        """
        text = "锁定银行板块部分利润：建设银行（+171.23%）建议止盈约30-40%持仓，工商银行（+70.18%）止盈约20-30%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"止盈目标比例不应被修正: {corrections}"

    def test_trim_target_single_expression(self, real_holdings):
        """单句「建议止盈约30%持仓」→ 目标比例，不修正。"""
        text = "建议止盈约30%持仓。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"止盈目标比例不应被修正: {corrections}"

    def test_reduce_position_expression(self, real_holdings):
        """「建议减仓约20%该持仓」→ 目标比例，不修正。"""
        text = "建议减仓约20%该持仓。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"减仓目标比例不应被修正: {corrections}"

    def test_trim_synonym_expressions(self, real_holdings):
        """「加仓/止损/清仓」等同类调仓动作词后的比例 → 不修正。"""
        text = "建议加仓至40%、止损线设为10%、分批止盈约15%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"调仓目标比例不应被修正: {corrections}"

    def test_run_fact_check_trim_not_rewritten(self, real_holdings):
        """run_fact_check 整链路：止盈比例不被自动修正，摘要无修正明细。"""
        html = (
            "<p>锁定银行板块部分利润：建设银行（+171.23%）建议止盈约30-40%持仓，工商银行（+70.18%）止盈约20-30%。</p>"
        )
        corr, summ = run_fact_check(html, real_holdings, "智囊团深度复盘")
        assert "30-40%" in corr  # 内容不被篡改
        assert "20-30%" in corr
        assert "已修正明细" not in summ

    def test_real_profit_rate_still_checked(self, real_holdings):
        """真实收益率仍正常校验（修复不过度）：组合累计收益率 5.0% 仍被修正。"""
        text = "组合累计收益率为 5.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert len(corrections) == 1
        assert corrections[0][0] == "5.0"
        assert "实际收益率" in corrections[0][3]

    def test_condition_threshold_over_pct_not_corrected(self, real_holdings):
        """「收益率超过200%后可考虑部分止盈」→ 条件阈值，不误修正。

        穿透深度分析原文含「收益率超过 200% 后可考虑部分止盈锁定利润」：
        其中 200% 是止盈目标阈值，非对 600900 当前收益率的陈述。"止盈"距数值
        较远（超出 _TRIM_TARGET_KEYWORDS 的 [-15,+5] 邻近窗口）时，该阈值
        不做收益率修正，保持原值、无修正项。
        """
        text = (
            "建设银行收益率+171.23%、长江电力+56.83%，建议继续持有以平滑组合波动，"
            "但在收益率超过 200% 后可考虑部分止盈锁定利润。"
        )
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"200% 是止盈目标阈值，不应被误修正: {corrections}"

    def test_condition_threshold_no_action_word_still_checked(self, real_holdings):
        """触发词后无调仓动作词 → 仍按收益率校验（不过度跳过）。

        「收益率超过200%，风险很大」中 200% 无后置"止盈/减仓"等动作词，
        仍作为收益率陈述处理（偏离真实值会告警），避免修复过度掩盖真错误。
        """
        text = "该组合收益率超过 200%，风险很大。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert len(corrections) == 1, f"无动作词的夸张收益率仍应被校验: {corrections}"
        assert corrections[0][0] == "200"


# ── 名称指代主体定位：最近边距离（修复平局误路由） ──


class TestNameSubjectNearestEdge:
    """名称指代主体定位按最近边距离（与代码分支一致）。

    真实报告「止盈纪律」句：建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%。
    171.23 指代建设银行（601939）：名称分支以最近边距离
    min(abs(idx-anchor), abs(idx+len(name)-anchor)) 定位——建设银行(idx=0,len=4,anchor=8)
    最近边 4，优于工商银行(idx=16)最近边 8，路由到 601939 与 171.23% 实际一致，不产生修正。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @pytest.fixture
    def real_holdings(self) -> list[dict]:
        """真实组合子集：工商银行在建设银行前（与持仓 xlsx 顺序一致）。"""
        return [
            {"name": "长江电力", "code": "600900", "market_value": 22140.0, "cost": 14120.0, "profit_rate": 56.83},
            {"name": "工商银行", "code": "601398", "market_value": 15000.0, "cost": 8814.0, "profit_rate": 70.18},
            {"name": "建设银行", "code": "601939", "market_value": 19800.0, "cost": 7300.0, "profit_rate": 171.23},
        ]

    def test_adjacent_names_tie_not_miscorrected(self, real_holdings):
        """止盈纪律句：建设银行+171.23% 保持原值，不产生修正。"""
        text = "止盈纪律缺失。建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%，这些品种累积丰厚浮盈。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"171.23%（601939 正确收益率）不应被误修正: {corrections}"

    def test_three_real_rates_all_pass(self, real_holdings):
        """三个真实收益率均正确路由到各自品种，全部通过。"""
        text = "建设银行收益率+171.23%、工商银行收益率+70.18%、长江电力收益率+56.83%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, real_holdings)
        assert corrections == [], f"正确收益率均不应被误修正: {corrections}"

    def test_run_fact_check_no_correction(self, real_holdings):
        """run_fact_check 整链路：止盈纪律句 171.23% 保持原值。"""
        html = "<p>止盈纪律缺失。建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%。</p>"
        corr, summ = run_fact_check(html, real_holdings, "智囊团深度复盘")
        assert "171.23%" in corr
        assert "已修正明细" not in summ


# ── 风险警戒阈值（非收益率）不被误修正 ──


class TestWarningThresholdContext:
    """风险警戒阈值（"回调20%的警戒区域"）不属于收益率，不产生修正。

    真实报告：易方达国证自由现金流ETF（159222）设立止损线：当前亏损-11.80%，
    已接近回调20%的警戒区域。"回调20%的警戒区域"是止损警戒阈值，不是对收益率
    20% 的声称；实际收益率 -11.80% 已同句另述且与 159222 一致，全文不产生数值修正。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @pytest.fixture
    def cashflow_holdings(self) -> list[dict]:
        """易方达国证自由现金流 ETF（159222），真实收益率 -11.8%。"""
        return [
            {
                "name": "易方达国证自由现金流 ETF",
                "code": "159222",
                "market_value": 14976.4,
                "cost": 16980.0,
                "profit_rate": -11.8,
            },
        ]

    def test_warning_threshold_not_corrected(self, cashflow_holdings):
        """「已接近回调20%的警戒区域」→ 警戒阈值，20% 保持原值。"""
        text = "易方达国证自由现金流ETF（159222）设立止损线：当前亏损-11.80%，已接近回调20%的警戒区域。"
        issues, checked, passed, corrections = check_numerical_consistency(text, cashflow_holdings)
        assert corrections == [], f"警戒阈值 20% 不应被误修正: {corrections}"

    def test_run_fact_check_warning_threshold_not_rewritten(self, cashflow_holdings):
        """run_fact_check 整链路：警戒阈值保持原值，实际收益率 -11.8% 保留。"""
        html = "<p>易方达国证自由现金流ETF（159222）设立止损线：当前亏损-11.80%，已接近回调20%的警戒区域。</p>"
        corr, summ = run_fact_check(html, cashflow_holdings, "智囊团深度复盘")
        assert "回调20%的警戒区域" in corr
        assert "-11.80%" in corr
        assert "已修正明细" not in summ

    def test_actual_loss_still_checked(self, cashflow_holdings):
        """同句的真实亏损声明 -11.80% 与 159222 一致，不产生修正。"""
        text = "该品种当前亏损-11.80%，已接近回调20%的警戒区域。"
        issues, checked, passed, corrections = check_numerical_consistency(text, cashflow_holdings)
        assert corrections == [], f"-11.80% 与 159222 实际一致，不应修正: {corrections}"


# ── 自动修正只替换判定处一次 ──


class TestApplyCorrectionSingleReplace:
    """数值自动修正只替换判定处一次，不连带替换同值异义的其他出现处。

    apply_numerical_corrections 用 re.sub 全局替换，一处修正会误伤 HTML 中
    同数值的其他语义出现处（如"止盈约30%"与"收益率30%"并存时，只应修被
    判定为错误的收益率处）。count=1 限制为只替换一处。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    def test_same_value_multiple_contexts_replaces_only_once(self):
        """HTML 中同值出现在两个语境 → 只替换一处，另一处保留。"""
        from src.python.llm.fact_checker._corrections import apply_numerical_corrections

        html = "<p>止盈约30%持仓，收益率30%。</p>"
        out = apply_numerical_corrections(
            html,
            [("30", "70.2", "止盈约30%持仓，收益率30%。", "601398实际收益率70.2%")],
        )
        assert out.count("70.2%") == 1  # 只替换一处
        assert out.count("30%") == 1  # 另一处同值数字保留

    def test_no_corrections_returns_original(self):
        """无修正列表 → 原样返回。"""
        from src.python.llm.fact_checker._corrections import apply_numerical_corrections

        html = "<p>止盈约30%持仓。</p>"
        assert apply_numerical_corrections(html, []) == html


# ── 持仓简称/别名归一化匹配 ──


class TestNameAliasNormalized:
    """句中用「机构名+指数简称」缩略指代持仓（如"华安纳指"→040046）可被归因。

    辩论综合 LLM 输出以「华安纳指+180.5%」缩略指代华安纳斯达克100ETF联接
    （040046，实际收益率 130.61%）。名称归一化（_NAME_ALIAS_MAP + 核心名
    前缀匹配）将"华安纳指"解析回 040046 并按其真实持仓校验收益率，不回退
    全局最近邻误命中其他代码。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @staticmethod
    def _alias_holdings() -> list[dict]:
        """华安纳指（040046）+ 建设银行（601939），收益率与真实持仓一致。"""
        return [
            {
                "name": "华安纳斯达克100ETF联接基金A",
                "code": "040046",
                "market_value": 41928.0,
                "cost": 18181.5,
                "profit_rate": 130.61,
            },
            {
                "name": "建设银行",
                "code": "601939",
                "market_value": 20480.0,
                "cost": 7300.0,
                "profit_rate": 180.55,
            },
        ]

    def test_alias_shortname_wrong_value_corrected(self):
        """「华安纳指+180.5%」→ 归因 040046，按实际 130.61% 修正。"""
        holdings = self._alias_holdings()
        text = "如何处理已实现的巨额浮盈（华安纳指+180.5%、建设银行+180.55%）"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert len(corrections) == 1, f"华安纳指被写成 180.5%，应被检出修正: {corrections}"
        assert corrections[0][0] == "180.5"
        assert corrections[0][1] == "130.6"
        assert "040046" in corrections[0][3]

    def test_alias_shortname_right_value_passes(self):
        """「华安纳指+130.61%」正确值 → 通过，不产生修正。"""
        holdings = self._alias_holdings()
        text = "华安纳指收益率+130.61%，为核心仓位。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"华安纳指正确收益率不应被修正: {corrections}"

    def test_bank_shortname_not_corrected(self):
        """「建行」等机构简称归一化匹配不误伤：句中建行真实收益率保持原值。"""
        holdings = self._alias_holdings()
        text = "建行收益率+180.55%，价值重估持续。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"建行(601939)正确收益率不应被修正: {corrections}"

    def test_alias_run_fact_check_corrects_html(self):
        """run_fact_check 整链路：华安纳指 180.5% 被自动修正为 130.6%。"""
        holdings = self._alias_holdings()
        html = "<p>本质分歧在于如何处理已实现的巨额浮盈（华安纳指+180.5%、建设银行+180.55%）。</p>"
        corr, summ = run_fact_check(html, holdings, "智囊团深度复盘")
        assert "华安纳指+130.6%" in corr
        assert "建设银行+180.55%" in corr  # 建设银行正确值不被连带修改


# ── 描述性尾名匹配（省略基金公司前缀） ──


class TestDescriptiveTailMatch:
    """句中用「描述词+产品后缀」缩略指代持仓（如"电池主题ETF"→561910）可被归因。

    2026-08-17 报告中 LLM 正确写出"电池主题ETF（收益率-3.92%）"（561910 实际
    -3.92%），但 _locate_subject_code 无法解析省略基金公司前缀的缩写，回退
    同句最近邻把 3.92 误路由到 022365（永赢科技智选混合C，实际 +36.29%），
    自动修正为 -36.3%。正确行为：归因 561910 且 3.92 在容差内通过。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @staticmethod
    def _tail_holdings() -> list[dict]:
        """招商中证电池主题ETF（561910）+ 永赢科技智选混合C（022365）+ 建信高端装备（011506）。"""
        return [
            {
                "name": "招商中证电池主题ETF",
                "code": "561910",
                "market_value": 9610.0,
                "cost": 10000.0,
                "profit_rate": -3.92,
            },
            {
                "name": "永赢科技智选混合C",
                "code": "022365",
                "market_value": 13629.0,
                "cost": 10000.0,
                "profit_rate": 36.29,
            },
            {
                "name": "建信高端装备股票A",
                "code": "011506",
                "market_value": 16635.0,
                "cost": 10000.0,
                "profit_rate": 66.35,
            },
        ]

    def test_tail_abbrev_correct_value_passes(self):
        """报告回归：「电池主题ETF（收益率-3.92%）」真实值 → 归因 561910，不产生修正。"""
        holdings = self._tail_holdings()
        text = (
            "建信高端装备股票A（收益率+66.35%）与永赢科技智选混合C（收益率+36.29%）"
            "及电池主题ETF（收益率-3.92%）同属成长赛道"
        )
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"电池主题ETF(561910)正确收益率 -3.92% 不应被修正: {corrections}"

    def test_tail_abbrev_wrong_value_corrected(self):
        """「电池主题ETF（收益率+5.0%）」→ 归因 561910，按实际 -3.9% 修正（保留盈亏方向）。"""
        holdings = self._tail_holdings()
        text = "电池主题ETF（收益率+5.0%），短期承压但估值已处低位。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert len(corrections) == 1, f"电池主题ETF 被写成 5.0%，应被检出修正: {corrections}"
        assert corrections[0][0] == "5.0"
        assert corrections[0][1] == "-3.9"
        assert "561910" in corrections[0][3]

    def test_locate_tail_abbrev(self):
        """_locate_subject_code 直测：省略品牌前缀的尾名缩写解析到正确代码。"""
        from src.python.llm.fact_checker._utils import _locate_subject_code

        holdings = self._tail_holdings()
        name_to_code = {d["name"]: d["code"] for d in holdings}
        codes = {d["code"] for d in holdings}
        sent = "及电池主题ETF（收益率-3.92%）同属成长赛道"
        anchor = sent.find("3.92")
        assert _locate_subject_code(sent, codes, name_to_code, anchor) == "561910"

    def test_locate_generic_term_not_misrouted(self):
        """泛词（电池板块/科技赛道）不被误路由到持仓，防新误修正。"""
        from src.python.llm.fact_checker._utils import _locate_subject_code

        holdings = self._tail_holdings()
        name_to_code = {d["name"]: d["code"] for d in holdings}
        codes = {d["code"] for d in holdings}
        for sent, val in (
            ("电池板块整体承压，建议关注新能源方向（收益率+8.8%）", "8.8"),
            ("科技赛道表现分化，但估值消化仍需时间（收益率+12.3%）", "12.3"),
        ):
            anchor = sent.find(val)
            assert _locate_subject_code(sent, codes, name_to_code, anchor) is None, sent

    def test_run_fact_check_keeps_correct_tail_value(self):
        """run_fact_check 整链路：电池主题ETF 正确 -3.92% 不被改写为 -36.3%。"""
        holdings = self._tail_holdings()
        html = (
            "<p>建信高端装备股票A（收益率+66.35%）与永赢科技智选混合C（收益率+36.29%）"
            "及电池主题ETF（收益率-3.92%）同属成长赛道。</p>"
        )
        corr, summ = run_fact_check(html, holdings, "全球政经局势")
        assert "电池主题ETF（收益率-3.92%）" in corr
        assert "-36.3%" not in corr


# ── 多主体同句就近归因：单代码钉扎 / 部分简称 / 组合当日收益 ──


class TestSubjectAttributionMulti:
    """同句含多个持仓主体（代码/名称/简称）时各数值就近归因，不做单一主体钉扎。

    2026-08-17 报告误修正三连（智囊团深度复盘 + 持仓体检）根因均为主体育位缺陷：
      - 体检「040046 收益率 +130.61%、建设银行收益率 +181.37%」：句内唯一代码 040046
        钉扎全句，把建设银行主体的 181.37% 误修正为 040046 的 130.6%；
      - 智囊团「华安纳斯达克100 +130.61%、建设银行 +181.37%」：华安纳指用部分简称
        （缺"ETF联接基金A"类型尾缀），全名/别名/长尾均不命中 → 两个数值都误归 601939；
      - 智囊团「今日组合 +0.21%」：组合当日收益被误路由到最近邻 561910 修正为 -2.3%。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @staticmethod
    def _holdings() -> list[dict]:
        """2026-08-17 报告持仓子集：040046 华安纳指 +130.61%、601939 建行 +181.37%、561910 电池 -2.28%。"""
        return [
            {
                "name": "华安纳斯达克100ETF联接基金A",
                "code": "040046",
                "market_value": 41928.0,
                "cost": 18181.5,
                "profit_rate": 130.61,
            },
            {
                "name": "建设银行",
                "code": "601939",
                "market_value": 20540.0,
                "cost": 7300.0,
                "profit_rate": 181.37,
            },
            {
                "name": "招商中证电池主题ETF",
                "code": "561910",
                "market_value": 9610.0,
                "cost": 10000.0,
                "profit_rate": -2.28,
            },
        ]

    def test_health_check_single_code_not_pinning_all(self):
        """体检句：代码 040046 + 建设银行名称同句 → 两个数值各自就近归因，不误修正。"""
        holdings = self._holdings()
        text = "异常说明：040046 收益率 +130.61%、建设银行收益率 +181.37% 较高"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"130.61% 属040046、181.37% 属建设银行，均正确不应被误修正: {corrections}"

    def test_thinktank_partial_name_short_tail(self):
        """智囊团分歧焦点句：华安纳斯达克100（部分简称）+ 建设银行 → 各自就近归因。"""
        holdings = self._holdings()
        text = "分歧焦点：围绕高浮盈品种（华安纳斯达克100 +130.61%、建设银行 +181.37%）的处理策略"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"华安纳斯达克100=130.61%、建设银行=181.37% 均正确，不应被误修正: {corrections}"

    def test_portfolio_daily_return_not_corrected(self):
        """智囊团综合评估句：今日组合 +0.21% 是组合当日收益（非个股收益率）→ 不修正。"""
        holdings = self._holdings()
        text = (
            "组合在进攻方向（科技/成长）和防御方向（银行/电力/债券）的配比，"
            "导致其收益弹性有限——今日组合 +0.21% 对沪深300 +1.34% 的跑输已现端倪"
        )
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"组合当日收益 0.21% 不应被误修正为个股收益率: {corrections}"

    def test_thinktank_action_item_130_not_misrouted_to_far_tail(self):
        """华安行动项：+130% 以上浮盈 归同句代码 040046，不被远距"博时纳斯达克100"尾名误路由。

        单代码钉扎修复若简化为"纯距离最近"会让 +130% 误归距其 17 字符的博时纳斯达克100
        （016055），把正确值改错——须保持代码对远距尾名的优先级（仅紧邻主体可覆盖）。
        """
        holdings = self._holdings() + [
            {
                "name": "博时纳斯达克100ETF联接(QDII)A",
                "code": "016055",
                "market_value": 20000.0,
                "cost": 17000.0,
                "profit_rate": 17.65,
            },
        ]
        text = (
            "华安纳斯达克100ETF联接基金A（040046）— 分批止盈，锁定盈利总额50%～60%（置信度：高）"
            "保留核心敞口（如剩余5%仓位）以延续全球科技长期配置，但 +130% 以上浮盈必须兑现一部分；"
            "与博时纳斯达克100合计17.4%的暴露需整体降下来"
        )
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert corrections == [], f"+130% 应归 040046（实际 130.61%）通过，不应被远距尾名误路由: {corrections}"


# ── 品种代码笔误自动纠正 ──


class TestCodeTypoAutoCorrection:
    """品种代码近似纠正通道：detect/apply_code_corrections + run_fact_check 整链路。

    实盘穿透深度模块复现——LLM 把持仓 561910（招商中证电池主题ETF）易位一位数字
    写成 161910，后紧跟"规模达10.2%"权重声称。纠正在品种存在性告警基础上，仅当
    非合法有效 / 唯一近邻（编辑距离≤1）/ 权重声称吻合三个条件全满足时才执行；
    歧义、建议语境、指数/穿透代码、权重不吻合等边界一律不自动纠正。
    """

    @staticmethod
    def _battery_holdings() -> list[dict]:
        """组合市值 100 万，561910 权重恰为 10.2%（实盘穿透误码场景比例 35516/347197≈10.2%）。"""
        return [
            {
                "name": "招商中证电池主题ETF",
                "code": "561910",
                "market_value": 102000.0,
                "cost": 90000.0,
            },
            {
                "name": "华安纳斯达克100ETF联接A",
                "code": "040046",
                "market_value": 898000.0,
                "cost": 700000.0,
            },
        ]

    def test_detect_real_transposed_code_with_weight_corroboration(self):
        """实盘场景：161910（561910 易位一位）后跟"规模达10.2%" → 检出纠正，reason 带候选权重。"""
        text = "该 ETF 161910 规模达10.2%，负收益持续性需跟踪。"
        corrections = detect_code_corrections(text, self._battery_holdings())
        assert len(corrections) == 1
        bad, good, _sentence, reason = corrections[0]
        assert bad == "161910"
        assert good == "561910"
        assert "561910" in reason and "招商中证电池主题ETF" in reason and "10.2%" in reason

    def test_apply_code_corrections_full_text_replace(self):
        """apply 全文替换错码为候选（错码是单一所指，残留即隐藏缺陷 → 不做 count=1）。"""
        html = "<table><tr><td>161910 规模达10.2%</td></tr><tr><td>另见 561910 的持续性</td></tr></table>"
        corrected = apply_code_corrections(html, [("161910", "561910", "", "")])
        assert "161910" not in corrected
        assert corrected.count("561910") == 2  # 原真实码 + 替换后的错码位置

    def test_no_correction_when_weight_claim_mismatch(self):
        """权重声称与实际权重偏差超容差 → 不自动纠正（30.0% vs 10.2%）。"""
        text = "该 ETF 161910 规模达 30.0%，需关注。"
        assert detect_code_corrections(text, self._battery_holdings()) == []

    def test_no_correction_when_multiple_near_neighbors(self):
        """唯一近邻被破坏（两个持仓代码均在编辑距离≤1）→ 歧义，保持告警不自动纠正。"""
        holdings = [
            {"name": "电池A", "code": "561910", "market_value": 50000.0},
            {"name": "电池B", "code": "561930", "market_value": 50000.0},
        ]
        text = "该 ETF 561920 规模达 50%，需关注。"
        assert detect_code_corrections(text, holdings) == []

    def test_no_correction_in_suggestion_context(self):
        """建议语境引用非持仓代码（合法推荐）→ 不自动纠正。"""
        text = "若看好电池方向，建议关注 161910 的配置机会（非持仓）。"
        assert detect_code_corrections(text, self._battery_holdings()) == []

    def test_no_correction_when_bad_in_extra_valid_codes(self):
        """错码属于穿透分析等额外有效代码 → 排除，不自动纠正。"""
        text = "161910 规模达10.2%，穿透标的存在。"
        extra = {"161910"}
        assert detect_code_corrections(text, self._battery_holdings(), extra_valid_codes=extra) == []

    def test_no_correction_for_index_code(self):
        """常见指数代码 → 属合法有效代码，不自动纠正。"""
        text = "跟踪沪深300（000300），规模占比10.2%。"
        assert detect_code_corrections(text, self._battery_holdings()) == []

    def test_run_fact_check_real_scenario_auto_correct(self):
        """run_fact_check 整链路：实盘 161910/561910 场景自动纠正并纳入已修正明细。

        用"占比"作权重声称词（数值检查器的 _is_position_weight_context 亦认可，
        10.2% 不会走数值修正路径），使整链路聚焦代码笔误纠正通道——
        修正后错码从内容与 ⚠ 告警中消失，摘要标注"自动修正 1 处代码"。
        """
        html = "<p>该基金 161910 占比10.2%，负收益持续性需跟踪。</p>"
        corr, summ = run_fact_check(html, self._battery_holdings(), "穿透深度分析")
        assert "161910" not in corr  # 内容中错码已替换为 561910
        assert "561910" in corr
        assert "已修正明细" in summ
        assert "161910→561910" in summ  # 修正明细列出纠正（供用户查看）
        assert "自动修正 1 处代码" in summ
        assert "品种代码 161910 不在当前持仓中" not in summ  # ⚠ 不再重复列出已修正码
