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

    用于回归：百分单位契约（1.9% 是旧小数误读，应修正为 187.1%）与
    单日涨跌语境按 change_pct 校验（今日下跌 3.41% 不再被误修正为收益率）。
    """
    return [
        {"name": "建设银行", "code": "601939", "market_value": 287120.0, "cost": 100000.0,
         "profit_rate": 187.12, "change_pct": -3.41},
        {"name": "贵州茅台", "code": "600519", "market_value": 2000000.0, "cost": 1500000.0,
         "profit_rate": 33.33, "change_pct": 1.25},
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

    # ── 第N大 / 前N大 / 主要持仓 声称（回归） ──────────────

    def test_second_largest_correct_pass(self, sample_holdings):
        """声称"第二大持仓"且名次正确（600036 实际第2）→ 通过（回归）。"""
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
        """声称"第三大持仓"且名次正确（300750 实际第3）→ 通过（回归）。"""
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
        """声称"前三大持仓"且品种在 top3 内但非第一（600036 实际第2）→ 通过（回归）。"""
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
        """ "主要持仓"是模糊声称（不断言精确名次）→ 不校验不告警（回归）。"""
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

    # ── 表格句就近归因（回归：核心误报场景） ────────────────

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
        """ "最大单项亏损品种" 是非持仓排名语境 → 不误判为排名声称（回归）。"""
        text = "561910 是组合最大单项亏损品种，需关注回撤风险。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_contributed_main_profit_not_flagged(self, sample_holdings):
        """ "贡献了主要利润" 是非持仓排名语境 → 不误判为排名声称（回归）。"""
        text = "601939 本季度贡献了主要利润，表现突出。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_max_loss_source_not_flagged(self, sample_holdings):
        """ "最大亏损来源" 是非持仓排名语境 → 不误判为排名声称（回归）。"""
        text = "600900 是组合最大亏损来源，拖累整体表现。"
        issues, checked, passed = check_ranking_correctness(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_max_feature_not_flagged(self, sample_holdings):
        """排名词 + 非持仓名词（特点/风险）→ 不误判为排名声称（回归）。"""
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
        """缓存命中内容含过期排名声称：skip_ranking_check=True → 不报排名误报（回归）。

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


# ── 回归：百分单位契约 + 单日涨跌语境 + 表格行归因（rf-159 批次修复） ──


class TestRegressionProfitRateUnitAndDailyChange:
    """回归：profit_rate 百分单位契约 + 单日涨跌语境按 change_pct 校验。

    真实报告曾把小数 profit_rate（1.8712=187.12%）当百分数使用，导致
    建设银行"今日下跌3.41%"被误修正为 1.9%（3.41 与 1.9 的偏差仅 1.5pp 在
    容差内）。修复后 orchestrator 源头 ×100、单日涨跌语境按 change_pct 校验。
    """

    def test_profit_rate_percent_unit_matches(self, holdings_with_rates):
        """百分单位：实际收益率 187.12% 时声称 187.1% → 通过，不再误修正。"""
        text = "建设银行（601939）持仓收益率为 187.1%。"
        issues, checked, passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert checked == 1
        assert passed == 1
        assert issues == []
        assert corrections == []

    def test_profit_rate_decimal_legacy_corrected(self, holdings_with_rates):
        """百分单位：旧小数误读 1.9%（≈1.8712 被当百分数）→ 修正为 187.1%。

        回归断言 1.9 → 187.1（而非旧实现把 3.41/4.43 修正成 1.9）。
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

        回归场景：建设银行"今日下跌3.41%"曾被误修正为 1.9%（误当收益率）。
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


class TestRegressionTableRowRankAttribution:
    """回归：表格行内排名声称归因到品种名列，而非行内后出现的比较对象。

    真实报告 LLM 调仓表行："...|| 🔴 高 | 040046 华安纳斯达克100ETF联接A |
    减仓1/3 | 当前占比11.3%为第一重仓，与016055高度同质；...||"。
    "第一重仓"声称指向品种名列 040046，但行内同单元格的比较对象 016055
    离声称词更近。旧实现"整句最近"误归因到 016055 → 误报"016055 为最大持仓"。
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
        assert issues == []  # 旧实现会误报"016055 为最大持仓"

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


# ── 回归：非收益率语境不被误修正 + 亏损品种符号保留（rf-205） ──


class TestRegressionFalseCorrectionContexts:
    """回归：胜率/权重/相对指数差等非收益率百分比不误判为收益率；
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
        确保数值校验不会因组合 profit_rate<0.01 被整体跳过（复现真实报告场景）。
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


# ── 回归：句中明确主体优先于全局最近邻（漏检） ──


class TestRegressionExplicitSubjectBeatsGlobalNearest:
    """回归：句中明确指代某品种（代码/名称）时，按该品种实际收益率校验，
    不得落入全局最近邻——否则句中已写明确主体、数值却接近无关品种时漏检。

    复现场景：601939 实际 1.87%、240012 实际 2.24%（两品种差 0.37 < 2×容差），
    「建设银行收益率 3.2%」：3.2 与 240012 差 0.96≤容差（旧实现按全局最近邻误判
    通过），但与句中主体 601939 差 1.33>容差 → 应修正为 601939 的 1.9%。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_llm,
        pytest.mark.llm,
    ]

    @staticmethod
    def _close_pair_holdings() -> list[dict]:
        """两品种收益率差 0.37（<2×容差），能复现"接近无关品种"的漏检场景。"""
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
        """句中无任何持仓主体 → 保留全局最近邻行为（历史语义不变）。"""
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
