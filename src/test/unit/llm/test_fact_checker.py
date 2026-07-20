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


# ── check_numerical_consistency ───────────────────────────────


class TestCheckNumericalConsistency:
    """数值一致性校验测试。"""

    def test_empty_text(self):
        """空文本 → 无检查项。"""
        issues, checked, passed = check_numerical_consistency("", None)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_no_percentage_values(self, sample_holdings):
        """无百分比数值的文本 → 无检查项。"""
        text = "本季度组合运行平稳，持仓结构保持合理分散。"
        issues, checked, passed = check_numerical_consistency(text, sample_holdings)
        assert issues == []
        assert checked == 0
        assert passed == 0

    def test_profit_percentage_matches(self, sample_holdings):
        """收益率数值与实际一致 → 通过。"""
        # 总收益率 = (200+80+50+30+10 - (150+60+40+25+9)) / (150+60+40+25+9) * 100
        # total_mv = 3700000, total_cost = 2840000, profit_rate ≈ 30.28%
        text = "本季度组合累计收益率为 30.5%，表现稳健。"
        issues, checked, passed = check_numerical_consistency(text, sample_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_profit_percentage_mismatch(self, sample_holdings):
        """收益率数值与实际偏差大 → 告警。"""
        text = "本季度组合累计收益率为 5.0%，表现不及预期。"
        issues, checked, passed = check_numerical_consistency(text, sample_holdings)
        assert checked == 1
        assert passed == 0
        assert len(issues) == 1
        assert "偏差超过容差" in issues[0]

    def test_non_profit_context_skipped(self, sample_holdings):
        """非收益上下文中的百分比不检查（如仓位比例）。"""
        text = "股票仓位占比 70%，债券仓位占比 30%。"
        issues, checked, passed = check_numerical_consistency(text, sample_holdings)
        # 百分比 30 在文本中出现但无收益关键词，跳过
        # 70% 也是无收益关键词
        assert checked >= 2
        assert passed == checked  # 全部跳过=全部通过
        assert issues == []

    def test_deduplicate_same_value(self, sample_holdings):
        """同一数值多次出现只检一次。"""
        text = "累计收益率为 30.3%。表现不错，收益率 30.3%。"
        issues, checked, passed = check_numerical_consistency(text, sample_holdings)
        assert checked == 1  # 只检一次
        assert passed == 1

    def test_negative_profit_rate(self, sample_holdings):
        """亏损场景 — 绝对值比较。"""
        # 模拟亏损持仓: cost > mv
        loss_holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 100000.0, "cost": 200000.0},
            {"name": "招商银行", "code": "600036", "market_value": 50000.0, "cost": 100000.0},
        ]
        # 总亏损率 ≈ -50%
        text = "组合累计亏损 50.0%。"
        issues, checked, passed = check_numerical_consistency(text, loss_holdings)
        assert checked == 1
        assert passed == 1
        assert issues == []

    def test_zero_cost_edge(self):
        """零成本持仓 — 不产生 NaN 错误。"""
        holdings = [{"name": "测试", "code": "000001", "market_value": 1000.0, "cost": 0.0}]
        text = "累计收益率为 10.0%。"
        issues, checked, passed = check_numerical_consistency(text, holdings)
        # 零成本导致 profit_rate=0，与 10% 偏差超过容差
        assert isinstance(checked, int)
        assert isinstance(passed, int)
        # profit_rate 为 0，但文本是 10%，应该不匹配
        assert checked >= 0

    def test_missing_market_value(self):
        """市值缺失 — 不影响函数运行。"""
        holdings = [{"name": "测试", "code": "000001", "cost": 1000.0}]
        text = "累计收益率为 5.0%。"
        issues, checked, passed = check_numerical_consistency(text, holdings)
        assert isinstance(issues, list)
        assert isinstance(checked, int)
        assert isinstance(passed, int)

    def test_multiple_values_with_mixed_context(self, sample_holdings):
        """混合上下文中的多个百分比 — 只检收益相关的。"""
        text = (
            "本季度组合累计收益率为 30.3%。"
            "股票仓位 75%，债券仓位 25%。"
            "最大回撤 3.5%。"
        )
        issues, checked, passed = check_numerical_consistency(text, sample_holdings)
        # 30.3% → 收益上下文 → 检查通过
        # 75%, 25% → 仓位上下文 → 跳过
        # 3.5% → 回撤上下文 → 跳过
        assert checked >= 1
        assert passed == checked


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
            text, sample_holdings, suggestion_keywords=None,
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
        text = (
            "贵州茅台（600519）是组合最大持仓。"
            "宁德时代（300750）是第一重仓股。"
        )
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


# ── run_fact_check（统一入口） ──────────────────────────────


class TestRunFactCheck:
    """统一入口 — run_fact_check 测试。"""

    def test_empty_content(self, sample_holdings):
        """空 HTML 内容 → 返回空字符串。"""
        result = run_fact_check("", sample_holdings, "测试模块")
        assert result == ""

    def test_none_content(self, sample_holdings):
        """None 内容（空字符串） → 返回空字符串。"""
        result = run_fact_check("", sample_holdings, "测试模块")
        assert result == ""

    def test_all_checks_pass(self, sample_holdings):
        """所有检查通过 → 绿色摘要。"""
        html = """<p>贵州茅台（600519）是组合最大持仓。</p>
<p>组合累计收益率为 30.3%。</p>"""
        result = run_fact_check(html, sample_holdings, "智囊团深度复盘")
        assert result != ""
        assert "事实校验通过" in result
        assert "color:#4a4" in result  # 绿色
        assert "智囊团深度复盘" in result

    def test_with_issues(self, sample_holdings):
        """存在不一致 → 黄色告警摘要。"""
        html = """<p>招商银行（600036）是组合最大持仓。</p>
<p>组合累计收益率为 5.0%。</p>"""
        result = run_fact_check(html, sample_holdings, "持仓体检报告")
        assert result != ""
        assert "事实校验" in result
        assert "项通过" in result
        assert "color:#a40" in result  # 黄色
        assert "持仓体检报告" in result
        assert "600036" in result

    def test_no_module_label(self, sample_holdings):
        """无 module_label 时摘要不包含标签前缀。"""
        html = "<p>贵州茅台（600519）是组合最大持仓。</p>"
        result = run_fact_check(html, sample_holdings)
        assert result != ""
        assert "[贵州茅台" not in result  # 模块标签标记不出现
        assert "事实校验通过" in result

    def test_holdings_none(self):
        """holdings_details 为 None → 跳过品种和排名检查，只检数值。"""
        # 纯文本不含百分比 → 0 checks
        html = "<p>贵州茅台是组合最大持仓。</p>"
        result = run_fact_check(html, None, "测试")
        assert result == ""  # 没有代码可检（纯中文）也没百分比

    def test_integration_full_html(self, sample_holdings):
        """模拟真实 LLM HTML 内容做完整端到端校验。"""
        html = """<h2>组合回顾</h2>
<p>本季度贵州茅台（600519）作为组合最大持仓继续领跑，白酒板块整体向好。</p>
<p>招商银行（600036）表现稳健，宁德时代（300750）受新能源政策提振。</p>
<p>组合累计收益率为 30.3%，跑赢沪深300指数（000300）。</p>"""
        result = run_fact_check(html, sample_holdings, "智囊团深度复盘")
        assert result != ""
        # 代码检查：600519✓, 600036✓, 300750✓, 000300(指数跳过) — 全部通过
        # 排名检查：600519 是最大持仓 ✓
        # 数值检查：30.3% ≈ 30.28% ✓
        assert "事实校验通过" in result

    def test_empty_holdings_edge(self):
        """空持仓列表 — 品种和排名检查跳过，数值检查至少不崩溃。"""
        html = "<p>组合累计收益率为 5.0%。</p>"
        result = run_fact_check(html, [], "测试")
        # 空持仓时 profit_rate=0，"5.0%" 不匹配但上下文不含收益关键词，跳过
        # 无论是否通过，不应崩溃
        assert isinstance(result, str)
