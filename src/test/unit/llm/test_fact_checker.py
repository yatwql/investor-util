"""测试：LLM 事实锚定校验器 — fact_checker.py

覆盖：
  - check_numerical_consistency: 数值一致性校验（含各种收益率上下文）
  - check_symbol_existence: 品种存在性校验（持仓代码 vs 指数代码）
  - check_ranking_correctness: 排名正确性校验（最大持仓声称）
  - run_fact_check: 统一入口 + HTML 摘要格式
  - 边界场景：空输入、None 入参、无匹配、全通过
"""

from __future__ import annotations

import pytest

from src.python.llm.fact_checker import (
    check_numerical_consistency,
    check_ranking_correctness,
    check_symbol_existence,
    run_fact_check,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
]


# ── 辅助 fixture ──────────────────────────────────────────────


@pytest.fixture
def sample_holdings() -> list[dict]:
    """一个含 5 只品种的模拟持仓。"""
    return [
        {"name": "贵州茅台", "code": "600519", "market_value": 2000000.0, "cost": 1500000.0},
        {"name": "招商银行", "code": "600036", "market_value": 800000.0, "cost": 600000.0},
        {"name": "宁德时代", "code": "300750", "market_value": 500000.0, "cost": 400000.0},
        {"name": "长江电力", "code": "600900", "market_value": 300000.0, "cost": 250000.0},
        {"name": "沪深300ETF", "code": "510300", "market_value": 100000.0, "cost": 90000.0},
    ]


@pytest.fixture
def holdings_with_rates() -> list[dict]:
    """含 profit_rate（百分单位，orchestrator 已 ×100）与 change_pct（单日涨跌）的持仓。

    用于百分单位契约与单日涨跌语境校验：数值须按百分单位比较，
    单日涨跌语境按 change_pct 校验（不当作收益率修正）。
    """
    return [
        {"name": "建设银行", "code": "601939", "market_value": 287120.0, "cost": 100000.0,
         "profit_rate": 187.12, "change_pct": -3.41},
        {"name": "贵州茅台", "code": "600519", "market_value": 2000000.0, "cost": 1500000.0,
         "profit_rate": 33.33, "change_pct": 1.25},
    ]


@pytest.fixture
def portfolio_mixed_holdings() -> list[dict]:
    """组合级+个股级收益同句场景的持仓：组合总收益率≈9.9%，招商银行 8.0%，茅台 15.0%。

    组合累计收益与个股涨跌同句时，组合收益归组合总收益率、
    个股收益归各自代码。
    """
    return [
        {"name": "工商银行", "code": "601398", "market_value": 200000.0, "cost": 185000.0, "profit_rate": 8.11},
        {"name": "招商银行", "code": "600036", "market_value": 108000.0, "cost": 100000.0, "profit_rate": 8.0},
        {"name": "贵州茅台", "code": "600519", "market_value": 115000.0, "cost": 100000.0, "profit_rate": 15.0},
    ]


# ── check_numerical_consistency ───────────────────────────────


class TestCheckNumericalConsistency:
    """数值一致性校验测试。"""

    def test_empty_text(self):
        """空文本 → 无检查项。"""
        issues, checked, passed, corrections = check_numerical_consistency("", None)
        assert issues == []
        assert checked == 0
        assert passed == 0
        assert corrections == []

    def test_no_percentage_values(self, sample_holdings):
        """无百分比数值的文本 → 无检查项。"""
        text = "本季度组合运行平稳，持仓结构保持合理分散。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0
        assert corrections == []

    def test_profit_percentage_matches(self, sample_holdings):
        """收益率数值与实际一致 → 通过。"""
        # 总收益率 = (200+80+50+30+10 - (150+60+40+25+9)) / (150+60+40+25+9) * 100
        # total_mv = 3700000, total_cost = 2840000, profit_rate ≈ 30.28%
        text = "本季度组合累计收益率为 30.5%，表现稳健。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []
        assert corrections == []

    def test_profit_percentage_mismatch(self, sample_holdings):
        """收益率数值与实际偏差大 → 告警。"""
        text = "本季度组合累计收益率为 5.0%，表现不及预期。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "偏差超过容差" in issues[0]
        assert len(corrections) == 1  # 返回修正信息
        assert corrections[0][0] == "5.0"  # wrong value
        assert corrections[0][1] == "30.3"  # correct value

    def test_non_profit_context_skipped(self, sample_holdings):
        """非收益上下文中的百分比不检查（如仓位比例）。"""
        text = "股票仓位占比 70%，债券仓位占比 30%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        # 百分比 30 在文本中出现但无收益关键词，跳过
        # 70% 也是无收益关键词
        assert checked >= 2
        assert passed == checked  # 全部跳过=全部通过
        assert issues == []
        assert corrections == []

    def test_deduplicate_same_value(self, sample_holdings):
        """同一数值多次出现只检一次。"""
        text = "累计收益率为 30.3%。表现不错，收益率 30.3%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert checked == 1  # 只检一次
        assert passed == 1
        assert corrections == []

    def test_negative_profit_rate(self, sample_holdings):
        """亏损场景 — 绝对值比较。"""
        # 模拟亏损持仓: cost > mv
        loss_holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 100000.0, "cost": 200000.0},
            {"name": "招商银行", "code": "600036", "market_value": 50000.0, "cost": 100000.0},
        ]
        # 总亏损率 ≈ -50%
        text = "组合累计亏损 50.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, loss_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []
        assert corrections == []

    def test_zero_cost_edge(self):
        """零成本持仓 — 不产生 NaN 错误。"""
        holdings = [{"name": "测试", "code": "000001", "market_value": 1000.0, "cost": 0.0}]
        text = "累计收益率为 10.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        # 零成本导致 profit_rate=0，与 10% 偏差超过容差
        assert isinstance(checked, int)
        assert isinstance(passed, int)
        assert isinstance(corrections, list)
        # profit_rate 为 0，但文本是 10%，应该不匹配
        assert checked >= 0

    def test_missing_market_value(self):
        """市值缺失 — 不影响函数运行。"""
        holdings = [{"name": "测试", "code": "000001", "cost": 1000.0}]
        text = "累计收益率为 5.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert isinstance(issues, list)
        assert isinstance(checked, int)
        assert isinstance(passed, int)
        assert isinstance(corrections, list)

    def test_multiple_values_with_mixed_context(self, sample_holdings):
        """混合上下文中的多个百分比 — 只检收益相关的。"""
        text = "本季度组合累计收益率为 30.3%。股票仓位 75%，债券仓位 25%。最大回撤 3.5%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        # 30.3% → 收益上下文 → 检查通过
        # 75%, 25% → 仓位上下文 → 跳过
        # 3.5% → 回撤上下文 → 跳过
        assert checked >= 1
        assert passed == checked
        assert corrections == []

    def test_portfolio_level_plus_stock_level_same_sentence(self, portfolio_mixed_holdings):
        """组合级收益与个股级收益同句：组合收益归组合、个股收益归各自代码。

        组合累计收益 10.0% 归组合总收益率，不因邻近个股数值而产生假阳性。
        """
        text = "组合累计收益约10.0%，招商银行(600036)上涨8.0%，贵州茅台(600519)上涨15.0%"
        issues, checked, passed, corrections = check_numerical_consistency(text, portfolio_mixed_holdings)
        assert issues == []
        assert checked == 3
        assert passed == 3
        assert corrections == []

    def test_portfolio_level_mismatch_attributed_to_portfolio(self, portfolio_mixed_holdings):
        """组合级收益数值错误时归因到组合总收益率而非个股。"""
        text = "组合累计收益约20.0%，招商银行(600036)上涨8.0%，贵州茅台(600519)上涨15.0%"
        issues, checked, passed, corrections = check_numerical_consistency(text, portfolio_mixed_holdings)
        assert checked == 3
        assert passed == 2
        assert len(issues) == 1
        # 归因到组合总收益率（"实际累计收益率"为组合级专用消息），不写成某个个股的收益率
        assert "实际累计收益率" in issues[0]
        assert len(corrections) == 1
        assert corrections[0][3] == "组合实际收益率9.9%"

    def test_pp_vs_rate_confusion_detected(self):
        """LLM 混淆贡献占比 pp 与个股收益率 → 检测并修正。"""
        holdings = [
            {
                "name": "建设银行",
                "code": "601939",
                "market_value": 500000.0,
                "cost": 490000.0,
                "profit": 10000.0,
                "profit_rate": 2.0,
            },
            {
                "name": "贵州茅台",
                "code": "600519",
                "market_value": 2000000.0,
                "cost": 1500000.0,
                "profit": 500000.0,
                "profit_rate": 33.3,
            },
        ]
        # LLM 误将 11.0pp 贡献占比当作收益率 11.0%
        text = "建设银行（601939）本季度收益率为 11.0%，表现稳健。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "601939" in issues[0]
        assert "11.0" in issues[0]
        assert "2.0" in issues[0]  # 实际收益率
        assert len(corrections) == 1
        assert corrections[0][0] == "11.0"  # wrong value
        assert corrections[0][1] == "2.0"  # correct value
        assert "601939" in corrections[0][2]  # sentence context

    def test_contribution_sentence_skips_pp_values(self):
        """贡献归因句中的 pp 数值不触发告警（策略 3）。"""
        holdings = [
            {
                "name": "建设银行",
                "code": "601939",
                "market_value": 500000.0,
                "cost": 490000.0,
                "profit": 10000.0,
                "profit_rate": 2.0,
            },
        ]
        # 收益归因句中的 pp 数值应跳过
        text = "主要盈利来源中，建设银行(+11.0pp)为组合贡献了重要收益。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings)
        # 收益归因句整体跳过，无检查项
        assert issues == []
        assert passed == 0
        assert corrections == []

    def test_change_rate_context_skipped(self, sample_holdings):
        """环比/同比变化率语境数值不误判为收益率。

        持仓体检的"环比对比：总市值变化-96.02%"是相对上期的变化率，
        与收益率（相对成本）维度不同。句子含"下跌"等收益关键词时，
        变化率必须跳过，否则会被误修正为最近个股/组合收益率。
        """
        text = "与上月环比对比，组合总市值大幅下跌96.02%，总盈亏变化+3,263，主要受到重仓个股回调影响。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert checked == 1  # 96.02% 被识别为变化率语境
        assert passed == 1  # 跳过 = 通过
        assert issues == []
        assert corrections == []  # 不被误修正

    def test_change_rate_uses_nearby_not_whole_sentence(self, sample_holdings):
        """变化率语境用数值邻近关键词判断，同句首部的真实收益率仍被校验。

        同句"环比总市值变化-96.02%，其中贵州茅台收益率为5.0%"：
        96.02% 跳过（邻近"变化"），5.0% 仍与茅台 33.3% 比较 → 被修正。
        """
        text = "环比上月总市值变化-96.02%，其中贵州茅台收益率为5.0%，表现不佳。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert checked == 2  # 96.02% + 5.0%
        assert passed == 1  # 只有变化率通过
        assert len(corrections) == 1  # 5.0% 被修正
        assert corrections[0][0] == "5.0"
        assert corrections[0][1] == "30.3"  # 最接近参考值（组合总收益率）

    def test_change_rate_with_volume_keywords(self, sample_holdings):
        """变化率语境覆盖"同比/较上期/总市值变化"等关键词组合。"""
        text = "同比总市值变化-96.02%，较上期总盈亏变化+3,263。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert issues == []
        assert corrections == []

    def test_tolerance_override_looser(self, sample_holdings):
        """宽松容差下偏差较小的数值通过。"""
        text = "组合收益率为 31.5%。"  # 实际≈30.28%，偏差1.22pp
        issues, checked, passed, corrections = check_numerical_consistency(
            text,
            sample_holdings,
            tolerance_pct=2.0,
        )
        assert checked == 1
        assert passed == 1  # 容差 ±2% 已覆盖
        assert issues == []
        assert corrections == []

    def test_drawdown_value_within_tolerance(self, sample_holdings):
        """回撤语境数值与实际最大回撤在容差内 → 通过。"""
        text = "组合历史最大回撤为 19.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(
            text,
            sample_holdings,
            max_drawdown_pct=18.97,
        )
        assert checked == 1
        assert passed == 1  # 19.0 vs 18.97, diff=0.03 <= 1.0
        assert issues == []
        assert corrections == []

    def test_drawdown_value_out_of_tolerance(self, sample_holdings):
        """回撤语境数值与实际偏差大 → 告警。"""
        text = "组合历史最大回撤为 5.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(
            text,
            sample_holdings,
            max_drawdown_pct=18.97,
        )
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "回撤相关数值" in issues[0]
        assert "18.97" in issues[0] or "19.0" in issues[0]
        assert len(corrections) == 1

    def test_drawdown_value_no_data_skips(self, sample_holdings):
        """回撤语境但无回撤数据 → 跳过（无法校验）。"""
        text = "组合最大回撤为 19.0%。"
        issues, checked, passed, corrections = check_numerical_consistency(
            text,
            sample_holdings,
            max_drawdown_pct=None,
        )
        assert checked == 1  # % found
        assert passed == 1  # skipped (no drawdown data, no profit context)
        assert issues == []

    def test_drawdown_mixed_with_profit_in_sentence(self, sample_holdings):
        """同一句中同时含回撤和收益数值 → 分别校验。"""
        text = "最大回撤 19.0%，累计收益 30.3%。"
        issues, checked, passed, corrections = check_numerical_consistency(
            text,
            sample_holdings,
            max_drawdown_pct=18.97,
        )
        # 19.0% → drawdown context, matches 18.97 within tolerance
        # 30.3% → profit context, matches 30.28 within tolerance
        assert checked == 2
        assert passed == 2
        assert issues == []

    def test_issue_message_contains_sentence_snippet(self, sample_holdings):
        """告警消息包含句段上下文摘要。"""
        text = "本季度组合累计收益率为 5.0%，表现不及预期。"
        issues, checked, passed, corrections = check_numerical_consistency(text, sample_holdings)
        assert len(issues) == 1
        assert "句段：" in issues[0]
        assert "本季度组合累计收益率" in issues[0]

    def test_run_fact_check_corrected_values_not_in_warnings(self, sample_holdings):
        """run_fact_check 中已自动修正的数值不在告警明细列出。"""
        text = "<p>组合累计收益率为 5.0%，历史最大回撤 19.0%。</p>"
        from src.python.llm.fact_checker import run_fact_check

        corrected, summary = run_fact_check(
            text,
            sample_holdings,
            module_label="测试",
            history_data={"max_drawdown_pct": 18.97},
        )
        # 5.0% → will be auto-corrected, not in warning details
        # 19.0% → drawdown within tolerance, no issue
        assert "自动修正 1 处数值" in summary
        # The corrected 5.0 should NOT appear as a ⚠ warning
        assert "⚠" not in summary


# ── check_symbol_existence ────────────────────────────────────


class TestCheckSymbolExistence:
    """品种存在性校验测试。"""

    def test_empty_text(self):
        """空文本 → 无检查项。"""
        issues, checked, passed, suggestions = check_symbol_existence("", None)
        assert issues == []
        assert checked == 0
        assert passed == 0
        assert suggestions == []

    def test_no_codes_mentioned(self, sample_holdings):
        """无代码提及 → 无检查项。"""
        text = "本季度组合以消费和金融板块为主。"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0
        assert suggestions == []

    def test_all_codes_in_holdings(self, sample_holdings):
        """提及的代码全部在持仓中 → 全部通过。"""
        text = "贵州茅台（600519）本季度表现突出。招商银行（600036）保持稳定。"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert checked == 2
        assert passed == 2
        assert issues == []
        assert suggestions == []

    def test_index_code_skipped(self, sample_holdings):
        """常见指数代码（沪深300:000300）跳过大盘指数。"""
        text = "组合收益在本季度跑赢沪深300（000300）指数。"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_code_not_in_holdings(self, sample_holdings):
        """提及的代码不在持仓中 → 告警。"""
        text = "中国平安（601318）作为金融龙头值得关注。"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "601318" in issues[0]
        assert "不在当前持仓" in issues[0]
        assert suggestions == []

    def test_suggestion_context_does_not_alert(self, sample_holdings):
        """建议语境提及的非持仓代码 → 归入 suggestion 而非 issues。"""
        text = "建议关注511010国债ETF作为配置补充"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert issues == [], "建议语境不应进入幻觉告警"
        assert len(suggestions) == 1
        assert "511010" in suggestions[0]

    def test_suggestion_keywords_disabled(self, sample_holdings):
        """suggestion_keywords=None 时建议语境也告警。"""
        text = "建议关注511010国债ETF"
        issues, checked, passed, suggestions = check_symbol_existence(
            text,
            sample_holdings,
            suggestion_keywords=None,
        )
        assert len(issues) == 1, "关闭建议检测后应正常告警"
        assert suggestions == []

    def test_mixed_valid_and_invalid(self, sample_holdings):
        """混合持仓中和非持仓代码。"""
        text = "贵州茅台（600519）和宁德时代（300750）表现良好。恒瑞医药（600276）需关注。"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert checked == 3
        assert passed == 2
        assert len(issues) == 1
        assert "600276" in issues[0]
        assert suggestions == []

    def test_penetration_codes_as_extra_valid(self, sample_holdings):
        """穿透 TOP10 代码作为 extra_valid_codes → 不报"不在当前持仓中"。

        阳光电源（300274）非直接持仓但属组合穿透范围，智囊团/持仓体检引用
        其代码时传入 extra_valid_codes 视为有效。
        """
        text = "宁德时代（300750）与阳光电源（300274）是组合穿透中的新能源核心持仓。"
        issues, checked, passed, suggestions = check_symbol_existence(
            text,
            sample_holdings,
            extra_valid_codes={"300274"},
        )
        assert checked == 2
        assert passed == 2  # 300750 持仓 + 300274 穿透有效
        assert issues == []
        assert suggestions == []

    def test_penetration_code_alerts_without_extra(self, sample_holdings):
        """未传 extra_valid_codes 时穿透代码仍告警（参数是唯一豁免来源）。"""
        text = "阳光电源（300274）作为组合穿透核心持仓值得关注。"
        issues, checked, passed, suggestions = check_symbol_existence(text, sample_holdings)
        assert len(issues) == 1
        assert "300274" in issues[0]

    def test_holdings_none(self):
        """holdings_details 为 None → 直接返回。"""
        issues, checked, passed, suggestions = check_symbol_existence("代码 600519 表现良好", None)
        assert issues == []
        assert checked == 0
        assert passed == 0
        assert suggestions == []

    def test_holdings_empty_list(self):
        """holdings_details 为空列表 → 直接返回。"""
        issues, checked, passed, suggestions = check_symbol_existence("代码 600519 表现良好", [])
        assert issues == []
        assert checked == 0
        assert passed == 0
        assert suggestions == []


# ── check_ranking_correctness ────────────────────────────────


class TestCheckRankingCorrectness:
    """排名正确性校验测试。"""

    def test_empty_text(self):
        """空文本 → 无检查项。"""
        issues, checked, passed = check_ranking_correctness("", None)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_no_ranking_claims(self, sample_holdings):
        """无排名声称 → 无检查项。"""
        text = "本季度组合各品种均有较好表现。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_largest_holding_correct(self, sample_holdings):
        """声称最大持仓 = 实际最大（600519）→ 通过。"""
        text = "贵州茅台（600519）是本季度组合最大持仓，市值占比过半。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_largest_holding_wrong(self, sample_holdings):
        """声称的"最大持仓"不是实际最大 → 告警。"""
        text = "招商银行（600036）是组合最大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "600036" in issues[0]
        assert "最大持仓" in issues[0]
        assert "600519" in issues[0]  # 提示实际最大是 600519

    def test_first_major_holding_wrong(self, sample_holdings):
        """声称"第一重仓"不是实际第一 → 告警。"""
        text = "宁德时代（300750）是第一重仓股。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "300750" in issues[0]
        assert "600519" in issues[0]

    def test_code_not_in_rank_map(self, sample_holdings):
        """排名语句中的代码不在持仓排名中 → 告警。"""
        text = "中国平安（601318）是组合最大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "601318" in issues[0]
        assert "无法在持仓市值排名中找到" in issues[0]

    def test_no_code_in_ranking_sentence(self, sample_holdings):
        """排名句子中无代码 → 跳过。"""
        text = "组合最大持仓品种本季度表现优异。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_mixed_ranking_claims(self, sample_holdings):
        """混合正确和错误的排名声称。"""
        text = "贵州茅台（600519）是组合最大持仓。宁德时代（300750）是第一重仓股。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 2
        assert passed == 1
        assert len(issues) == 1  # 只有宁德时代的有问题

    def test_holdings_none(self):
        """holdings_details 为 None → 直接返回。"""
        issues, checked, passed = check_ranking_correctness("600519 是最大持仓。", None)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_holdings_empty_list(self):
        """holdings_details 为空列表 → 直接返回。"""
        issues, checked, passed = check_ranking_correctness("600519 是最大持仓。", [])
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_no_market_value_data(self):
        """持仓市值全部缺失 → 无检查项。"""
        holdings = [
            {"name": "测试A", "code": "000001"},
            {"name": "测试B", "code": "000002"},
        ]
        text = "测试A（000001）是最大持仓。"
        issues, checked, passed = check_ranking_correctness(text, holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_rank_tie(self, sample_holdings):
        """第一和第二并列 — 仅检查严重偏离的情况。"""
        # 添加一个市值与最大接近的品种
        holdings = sample_holdings + [
            {"name": "竞争品种", "code": "000888", "market_value": 1990000.0, "cost": 1800000.0},
        ]
        text = "竞争品种（000888）是组合最大持仓。"
        issues, checked, passed = check_ranking_correctness(text, holdings)
        # 000888 排第2（市值 199万 vs 600519 市值 200万）
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1

    # ── 第N大 / 前N大 / 主要持仓 声称 ──────────────

    def test_second_largest_correct_pass(self, sample_holdings):
        """声称"第二大持仓"且名次正确（600036 实际第2）→ 通过。"""
        text = "招商银行（600036）是组合第二大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_second_largest_wrong_flagged(self, sample_holdings):
        """声称"第二大持仓"但名次错误（300750 实际第3）→ 告警且指名实际第2。"""
        text = "宁德时代（300750）是组合第二大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "300750" in issues[0]
        assert "第2大持仓" in issues[0]
        assert "600036" in issues[0]  # 实际第二大是招商银行

    def test_third_largest_correct_pass(self, sample_holdings):
        """声称"第三大持仓"且名次正确（300750 实际第3）→ 通过。"""
        text = "宁德时代（300750）是组合第三大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_third_largest_wrong_flagged(self, sample_holdings):
        """声称"第三大持仓"但名次错误（600900 实际第4）→ 告警且指名实际第3。"""
        text = "长江电力（600900）是组合第三大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "600900" in issues[0]
        assert "第3大持仓" in issues[0]
        assert "300750" in issues[0]  # 实际第三大是宁德时代

    def test_top3_non_first_rank_pass(self, sample_holdings):
        """声称"前三大持仓"且品种在 top3 内但非第一（600036 实际第2）→ 通过。"""
        text = "招商银行（600036）属于组合前三大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_top3_outside_rank_flagged(self, sample_holdings):
        """声称"前三大持仓"但品种不在 top3（510300 实际第5）→ 告警。"""
        text = "沪深300ETF（510300）属于组合前三大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "510300" in issues[0]
        assert "前3大持仓" in issues[0]

    def test_major_holding_vague_claim_skipped(self, sample_holdings):
        """ "主要持仓"是模糊声称（不断言精确名次）→ 不校验不告警。"""
        text = "招商银行（600036）是组合主要持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0

    def test_ordinal_beyond_holdings_count(self, sample_holdings):
        """声称"第十大持仓"但持仓不足 10 只 → 告警说明品种不足。"""
        text = "长江电力（600900）是组合第十大持仓。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "持仓品种不足" in issues[0]

    # ── 表格句就近归因 ────────────────

    @pytest.fixture
    def table_holdings(self) -> list[dict]:
        """模拟真实组合：华安纳斯达克100 为第一、电池ETF 为第三。"""
        return [
            {"name": "华安纳斯达克100ETF联接A", "code": "040046", "market_value": 100000.0, "cost": 80000.0},
            {"name": "建信高端装备股票A", "code": "011506", "market_value": 50000.0, "cost": 45000.0},
            {"name": "招商中证电池主题ETF", "code": "561910", "market_value": 30000.0, "cost": 30010.0},
            {"name": "长江电力", "code": "600900", "market_value": 20000.0, "cost": 19000.0},
        ]

    def test_table_sentence_nearest_code_attribution(self, table_holdings):
        """表格句中的合法排名声称按所在行就近归因，不误报。

        LLM 以表格输出调仓方案，句中含多个代码：
        - "561910 ... 已是组合第三大持仓"（561910 实际第3，正确）
        - "040046 ... 组合第一大重仓"（040046 实际第1，正确）
        两处声称分别指向各自所在行内的品种，均通过校验。
        """
        text = (
            "操作建议|优先级|品种|建议操作|理由|| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | "
            "市场占比10.6%，已是组合第三大持仓却贡献负收益 || 🟢 低 | 040046 华安纳斯达克100ETF联接基金A | "
            "持有 | 收益率+1.16%，组合第一大重仓，继续持有"
        )
        issues, checked, passed = check_ranking_correctness(text, table_holdings)
        assert checked == 2  # 两处排名声称均被校验
        assert passed == 2
        assert issues == [], f"合法排名声称不应告警: {issues}"

    def test_table_sentence_wrong_claim_still_detected(self, table_holdings):
        """表格句中的错误排名声称 → 仍能检测（不因就近归因而漏检）。"""
        text = (
            "操作建议|优先级|品种|建议操作|理由|| 🔴 高 | 600900 长江电力 | 减仓 | "
            "已是组合第三大持仓却贡献负收益 || 🟢 低 | 561910 招商中证电池主题ETF | 持有 | "
            "收益率+1.16%，组合第一大重仓，继续持有"
        )
        issues, checked, passed = check_ranking_correctness(text, table_holdings)
        assert checked == 2
        assert passed == 0
        assert len(issues) == 2
        # 600900 实际第4，被声称"第三大持仓" → 告警
        assert any("600900" in i and "第3大持仓" in i for i in issues)
        # 561910 实际第3，被声称"第一大重仓" → 告警
        assert any("561910" in i and "最大持仓" in i for i in issues)

    # ── 非持仓排名语境不误判 ──────────────────────────────

    def test_max_single_loss_item_not_flagged(self, sample_holdings):
        """ "最大单项亏损品种" 是非持仓排名语境 → 不误判为排名声称。"""
        text = "561910 是组合最大单项亏损品种，需关注回撤风险。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_contributed_main_profit_not_flagged(self, sample_holdings):
        """ "贡献了主要利润" 是非持仓排名语境 → 不误判为排名声称。"""
        text = "601939 本季度贡献了主要利润，表现突出。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_max_loss_source_not_flagged(self, sample_holdings):
        """ "最大亏损来源" 是非持仓排名语境 → 不误判为排名声称。"""
        text = "600900 是组合最大亏损来源，拖累整体表现。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_max_feature_not_flagged(self, sample_holdings):
        """排名词 + 非持仓名词（特点/风险）→ 不误判为排名声称。"""
        text = "600900 最大特点是高股息，适合防守配置。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_top3_holding_claim_still_detected(self, sample_holdings):
        """前三大持仓（合法排名声称）→ 仍被检测且正确通过（不破坏既有功能）。"""
        text = "组合前三大持仓依次为 600519、600036、300750。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert checked == 1
        assert passed == 1  # 600519 是实际第一
        assert issues == []


# ── run_fact_check（统一入口） ──────────────────────────────


class TestRunFactCheck:
    """统一入口 — run_fact_check 测试。"""

    def test_empty_content(self, sample_holdings):
        """空 HTML 内容 → 返回(原内容, 空字符串)。"""
        corr, summ = run_fact_check("", sample_holdings, "测试模块")
        assert corr == ""
        assert summ == ""

    def test_none_content(self, sample_holdings):
        """None 内容（空字符串） → 返回(原内容, 空字符串)。"""
        corr, summ = run_fact_check("", sample_holdings, "测试模块")
        assert corr == ""
        assert summ == ""

    def test_all_checks_pass(self, sample_holdings):
        """所有检查通过 → 绿色摘要。"""
        html = """<p>贵州茅台（600519）是组合最大持仓。</p>
<p>组合累计收益率为 30.3%。</p>"""
        corr, summ = run_fact_check(html, sample_holdings, "智囊团深度复盘")
        assert summ != ""
        assert "事实校验通过" in summ
        assert "color:#4a4" in summ  # 绿色
        assert "智囊团深度复盘" in summ

    def test_with_issues(self, sample_holdings):
        """存在不一致 → 黄色告警摘要 + 自动修正。"""
        html = """<p>招商银行（600036）是组合最大持仓。</p>
<p>组合累计收益率为 5.0%。</p>"""
        corr, summ = run_fact_check(html, sample_holdings, "持仓体检报告")
        assert summ != ""
        assert "事实校验" in summ
        assert "项通过" in summ
        assert "color:#a40" in summ  # 黄色
        assert "持仓体检报告" in summ
        assert "600036" in summ
        # 自动修正：5.0% → 30.3%
        assert "30.3%" in corr
        assert "5.0%" not in corr

    def test_no_module_label(self, sample_holdings):
        """无 module_label 时摘要不包含标签前缀。"""
        html = "<p>贵州茅台（600519）是组合最大持仓。</p>"
        corr, summ = run_fact_check(html, sample_holdings)
        assert summ != ""
        assert "[贵州茅台" not in summ  # 模块标签标记不出现
        assert "事实校验通过" in summ

    def test_holdings_none(self):
        """holdings_details 为 None → 跳过品种和排名检查，只检数值。"""
        # 纯文本不含百分比 → 0 checks
        html = "<p>贵州茅台是组合最大持仓。</p>"
        corr, summ = run_fact_check(html, None, "测试")
        assert corr == html  # 内容不变
        assert summ == ""  # 没有代码可检（纯中文）也没百分比

    def test_integration_full_html(self, sample_holdings):
        """模拟真实 LLM HTML 内容做完整端到端校验。"""
        html = """<h2>组合回顾</h2>
<p>本季度贵州茅台（600519）作为组合最大持仓继续领跑，白酒板块整体向好。</p>
<p>招商银行（600036）表现稳健，宁德时代（300750）受新能源政策提振。</p>
<p>组合累计收益率为 30.3%，跑赢沪深300指数（000300）。</p>"""
        corr, summ = run_fact_check(html, sample_holdings, "智囊团深度复盘")
        assert summ != ""
        # 代码检查：600519✓, 600036✓, 300750✓, 000300(指数跳过) — 全部通过
        # 排名检查：600519 是最大持仓 ✓
        # 数值检查：30.3% ≈ 30.28% ✓
        assert "事实校验通过" in summ

    def test_empty_holdings_edge(self):
        """空持仓列表 — 品种和排名检查跳过，数值检查至少不崩溃。"""
        html = "<p>组合累计收益率为 5.0%。</p>"
        corr, summ = run_fact_check(html, [], "测试")
        # 空持仓时 profit_rate=0，"5.0%" 不匹配但上下文不含收益关键词，跳过
        # 无论是否通过，不应崩溃
        assert isinstance(corr, str)
        assert isinstance(summ, str)

    # ── 缓存命中跳过排名校验 ──────────────────────────────

    def test_skip_ranking_check_skips_stale_rank_claim(self, sample_holdings):
        """缓存命中内容含过期排名声称：skip_ranking_check=True → 不报排名误报。

        600036 是实际第 2 大持仓，声称其为最大持仓在默认校验下会告警；
        但缓存内容基于生成时价格快照，当前排名可能已翻转 → 缓存命中场景应跳过排名校验。
        数值/品种校验仍执行。
        """
        html = "<p>招商银行（600036）是组合最大持仓。</p>"
        corr, summ = run_fact_check(
            html,
            sample_holdings,
            "智囊团深度复盘",
            skip_ranking_check=True,
        )
        # 排名校验被跳过 → 无"声称最大持仓"误报
        assert "最大持仓" not in summ
        # 600036 为真实持仓 → 品种存在性通过，无其他告警 → 全部通过
        assert "事实校验通过" in summ

    def test_skip_ranking_check_still_corrects_numbers(self, sample_holdings):
        """缓存命中跳过排名校验但数值自动修正仍生效（保留数值修正）。"""
        html = """<p>招商银行（600036）是组合最大持仓。</p>
<p>组合累计收益率为 5.0%。</p>"""
        corr, summ = run_fact_check(
            html,
            sample_holdings,
            "持仓体检报告",
            skip_ranking_check=True,
        )
        # 排名误报不出现
        assert "最大持仓" not in summ
        # 数值修正仍生效：5.0% → 30.3%
        assert "30.3%" in corr
        assert "5.0%" not in corr
        assert "自动修正 1 处数值" in summ

    def test_ranking_check_active_by_default(self, sample_holdings):
        """默认（skip_ranking_check=False）：过期排名声称仍被检出（不破坏既有功能）。"""
        html = "<p>招商银行（600036）是组合最大持仓。</p>"
        corr, summ = run_fact_check(html, sample_holdings, "智囊团深度复盘")
        assert "600036" in summ
        assert "最大持仓" in summ

    def test_corrections_detail_in_summary(self, sample_holdings):
        """自动修正后摘要列出修正明细（wrong%→correct% + 语义 reason），供用户直接查看。"""
        html = """<p>招商银行（600036）是组合最大持仓。</p>
<p>组合累计收益率为 5.0%。</p>"""
        corr, summ = run_fact_check(html, sample_holdings, "智囊团深度复盘")
        # 内容中 5.0% 已被替换为 30.3%
        assert "30.3%" in corr
        assert "5.0%" not in corr
        # 摘要追加灰色「已修正明细」行，含 wrong→correct 与语义 reason
        # （语义 reason 替代原截断句段，说明修正的是哪个数字的含义）
        assert "已修正明细" in summ
        assert "5.0%→30.3%" in summ
        assert "组合实际收益率30.3%" in summ

    def test_run_fact_check_change_rate_not_corrected(self, sample_holdings):
        """run_fact_check 整链路：环比变化率不被自动修正。

        持仓体检"环比对比中总市值变化-96.02%"是相对上期的变化率，与收益率
        维度不同，直接比较会误修正。环比变化率跳过数值校验，内容不被篡改，
        摘要无修正明细。
        """
        html = (
            "<p>组合整体稳健。与上月环比对比，组合总市值大幅下跌96.02%，"
            "总盈亏变化+3,263，主要受到重仓个股回调影响。</p>"
        )
        corr, summ = run_fact_check(html, sample_holdings, "持仓体检报告")
        assert corr == html  # 内容不被篡改（96.02% 保留）
        assert "96.02%" in corr
        assert "已修正明细" not in summ  # 无修正明细
        assert "事实校验通过" in summ

    def test_corrections_logged(self, sample_holdings, caplog):
        """自动修正明细写入日志（含模块标签 + wrong→correct 明细）。"""
        import logging

        html = """<p>招商银行（600036）是组合最大持仓。</p>
<p>组合累计收益率为 5.0%。</p>"""
        with caplog.at_level(logging.INFO, logger="invest"):
            run_fact_check(html, sample_holdings, "智囊团深度复盘")
        joined = caplog.text
        assert "智囊团深度复盘" in joined
        assert "自动修正 1 处数值" in joined
        assert "5.0%→30.3%" in joined


# ── 百分单位契约 + 单日涨跌语境 + 表格行归因 ──


class TestProfitRateUnitAndDailyChange:
    """profit_rate 百分单位契约 + 单日涨跌语境按 change_pct 校验。

    profit_rate 为百分单位（187.12 表示 187.12%），数值校验须按百分单位比较；
    单日涨跌语境按 change_pct 校验，不得把 3.41% 当作收益率修正。
    """

    def test_profit_rate_percent_unit_matches(self, holdings_with_rates):
        """百分单位：实际收益率 187.12% 时声称 187.1% → 通过，不再误修正。"""
        text = "建设银行（601939）持仓收益率为 187.1%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert checked == 1
        assert passed == 1
        assert issues == []
        assert corrections == []

    def test_profit_rate_decimal_value_corrected(self, holdings_with_rates):
        """百分单位：数值 1.9%（与 187.12 偏差超容差）→ 修正为 187.1%。

        百分单位契约下 1.9 与 187.12 偏差超容差，应修正为 187.1。
        """
        text = "建设银行（601939）持仓收益率为 1.9%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert checked == 1
        assert passed == 0
        assert len(corrections) == 1
        assert corrections[0][0] == "1.9"
        assert corrections[0][1] == "187.1"
        assert "187.1%" in corrections[0][3]  # 语义 reason 指明实际收益率

    def test_daily_change_matching_change_pct_not_corrected(self, holdings_with_rates):
        """单日涨跌语境：今日下跌 3.41% 与 601939 change_pct=-3.41 一致 → 不修正。

        单日涨跌按 change_pct 校验，不当作收益率修正。
        """
        text = "建设银行（601939）今日下跌3.41%，表现弱于大盘。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert checked == 1
        assert passed == 1
        assert issues == []
        assert corrections == []

    def test_daily_change_mismatch_corrected(self, holdings_with_rates):
        """单日涨跌语境：声称下跌 1.0% 与实际 -3.41% 偏差大 → 修正为 -3.4%。"""
        text = "建设银行（601939）今日下跌1.0%，跌幅较大。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert checked == 1
        assert passed == 0
        assert len(corrections) == 1
        assert corrections[0][0] == "1.0"
        assert corrections[0][1] == "-3.4"

    def test_daily_change_without_subject_skipped(self, holdings_with_rates):
        """单日涨跌语境无持仓主体（指数）→ 无可用校验数据，跳过不修正。"""
        text = "上证指数今日下跌0.5%，市场整体偏弱。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert checked == 1
        assert passed == 1
        assert corrections == []

    def test_run_fact_check_daily_change_not_corrected(self, holdings_with_rates):
        """run_fact_check 整链路：单日涨跌不被自动修正，摘要无修正明细。"""
        html = "<p>建设银行（601939）今日下跌3.41%，表现弱于大盘。</p>"
        corr, summ = run_fact_check(html, holdings_with_rates, "持仓体检报告")
        assert corr == html  # 内容不被篡改
        assert "3.41%" in corr
        assert "已修正明细" not in summ


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
            {"name": "华安纳斯达克100ETF联接A", "code": "040046",
             "market_value": 50000.0, "cost": 40000.0},
            {"name": "博时纳斯达克100ETF联接A", "code": "016055",
             "market_value": 30000.0, "cost": 25000.0},
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
            {"name": "华安纳斯达克100ETF联接A", "code": "040046",
             "market_value": 30000.0, "cost": 25000.0},
            {"name": "博时纳斯达克100ETF联接A", "code": "016055",
             "market_value": 50000.0, "cost": 40000.0},
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
        text = (
            "组合今日跑输沪深300达1.10%，主要受低波动红利资产拖累，"
            "而夏普比率仅0.09显示风险调整后收益平平。"
        )
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
        text = (
            "锁定银行板块部分利润：建设银行（+171.23%）建议止盈约30-40%持仓，"
            "工商银行（+70.18%）止盈约20-30%。"
        )
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
            "<p>锁定银行板块部分利润：建设银行（+171.23%）建议止盈约30-40%持仓，"
            "工商银行（+70.18%）止盈约20-30%。</p>"
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
            {"name": "易方达国证自由现金流 ETF", "code": "159222",
             "market_value": 14976.4, "cost": 16980.0, "profit_rate": -11.8},
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
