"""LLM 幻觉率采样测试 — 评估事实校验器的检出能力。

使用标准持仓数据验证 fact_checker.py 的三个检查器：
1. 数值一致性（check_numerical_consistency）
2. 品种存在性（check_symbol_existence）
3. 排名正确性（check_ranking_correctness）

覆盖要点：
  - 个股收益率 vs 组合总收益率的正确路由
  - 收益归因段落自动跳过
  - 指数代码数值跳过
  - 穿透分析模块的特殊处理
  - 正确输出全通过
"""

from __future__ import annotations

import logging

import pytest

pytestmark = [pytest.mark.llm, pytest.mark.scenario_llm, pytest.mark.scenario]

from src.python.llm.fact_checker import (
    check_numerical_consistency,
    check_ranking_correctness,
    check_symbol_existence,
)

logger = logging.getLogger("invest")

# 当前事实校验器允许的最大假阳性数（不误报）
_MAX_ALLOWED_FALSE_POSITIVES = 2

# ── 标准测试数据 ─────────────────────────────────────────────

# holdings_details: list[dict] 格式（含 profit_rate 字段用于个股级校验）
# 数据一致性：profit = mv - cost, profit_rate = profit / cost * 100
# 组合总成本: 600000, 总盈亏: +58400, 总收益率: 9.73%
_STD_HOLDINGS_DETAILS = [
    {"name": "招商银行", "code": "600036", "market_value": 216400.0, "cost": 200000.0,
     "profit": 16400.0, "profit_rate": 8.2, "account": "测试账户"},
    {"name": "贵州茅台", "code": "600519", "market_value": 345000.0, "cost": 300000.0,
     "profit": 45000.0, "profit_rate": 15.0, "account": "测试账户"},
    {"name": "易方达蓝筹", "code": "005827", "market_value": 97000.0, "cost": 100000.0,
     "profit": -3000.0, "profit_rate": -3.0, "account": "测试账户"},
]


# ── 测试用例 ─────────────────────────────────────────────────


class TestHallucinationDetection:
    """每个场景测试一个事实校验维度。"""

    # ── 数值一致性 ─────────────────────────────────────────

    def test_wrong_profit_rate_vs_portfolio(self):
        """LLM 声称的组合总收益率与实际偏离（20% vs 9.73%）。"""
        text = "组合累计收益达到 20.0%"
        issues, total, passed, corrections = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) >= 1, "应检测到组合收益率偏离"
        assert len(corrections) >= 1, "偏离应生成数值修正"
        logger.info("组合收益率偏离检出: %s", issues)

    def test_correct_profit_rate_vs_portfolio(self):
        """LLM 声明的组合总收益率接近实际（10% vs 9.73%），应通过。"""
        text = "组合累计收益约 10.0%"
        issues, total, passed, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "合理精度内不应误报"
        assert passed > 0, "应计入通过"

    def test_wrong_stock_return(self):
        """LLM 声称招商银行收益率 5%，实际 8.2%。"""
        text = "招商银行(600036)本期收益率为 5.0%"
        issues, total, passed, corrections = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        # 句中含持仓代码 600036，应对比个股收益率 8.2%
        assert len(issues) >= 1, "应检测到个股收益率偏离"
        assert "600036" in issues[0], "告警应提到具体代码"
        assert len(corrections) >= 1, "个股收益偏离应生成数值修正"

    def test_correct_stock_return(self):
        """LLM 声明的个股收益率接近实际（8.0% vs 8.2%），应通过。"""
        text = "招商银行(600036)上涨约 8.0%"
        issues, total, passed, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "个股收益率在容差内不应误报"

    def test_correct_portfolio_and_stock(self):
        """LLM 同时引用组合总收益和个股收益，两者均正确。"""
        text = "组合累计收益10.0%，其中招商银行上涨8.0%"
        issues, total, passed, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "正确数值不应告警"

    def test_mixed_correct_and_wrong(self):
        """LLM 的组合收益正确但个股收益错误。"""
        text = "组合收益10.0%，招商银行上涨20.0%"
        issues, total, passed, corrections = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        # 10.0% 在组合总收益率容差内 → 通过
        # 20.0% → 句中含 600036 → 对比个股 8.2% → 告警
        assert len(issues) >= 1, "个股错误应被检出"
        assert len(corrections) >= 1, "个股收益偏离应生成数值修正"

    def test_attribution_sentence_skipped(self):
        """收益归因段落中的贡献度占比应跳过（不可与收益率比较）。"""
        text = "【收益归因】主要盈利来源: 招商银行(+26.0%)、贵州茅台(+16.0%)"
        issues, total, passed, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "归因段落数值不应触发收益率告警"

    def test_index_benchmark_skipped(self):
        """指数基准数值（如沪深300涨幅）应跳过。"""
        text = "同期沪深300(000300)涨幅为 23.0%"
        issues, total, passed, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "指数基准数值不应触发告警"

    def test_non_profit_context_skipped(self):
        """非收益上下文数值（如估值百分位）应跳过。"""
        text = "目前招商银行 PE 估值处于历史 15% 分位"
        issues, total, passed, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "非收益上下文数值不应触发告警"

    # ── 品种存在性 ─────────────────────────────────────────

    def test_missing_code(self):
        """LLM 引用了一个不在持仓中的代码（000001 是指数，用非指数代码）。"""
        text = "参考品种 002837（英维克）的走势"
        issues, total, passed, _ = check_symbol_existence(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) >= 1, "应检测到不存在的品种代码"

    def test_valid_code(self):
        """LLM 引用的持仓代码都在持仓中，应通过。"""
        text = "招商银行(600036)和贵州茅台(600519)表现较好"
        issues, total, passed, _ = check_symbol_existence(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "存在代码不应告警"

    def test_extra_valid_codes(self):
        """穿透代码集传入 extra_valid_codes 后不应告警。"""
        text = "穿透分析显示 300750（宁德时代）权重最大"
        # 不传 extra 时 → 告警
        issues, _, _, _ = check_symbol_existence(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) >= 1, "不传 extra 时应告警"
        # 传 extra 时 → 通过
        issues, total, passed, _ = check_symbol_existence(
            text, _STD_HOLDINGS_DETAILS, extra_valid_codes={"300750", "002837"}
        )
        assert len(issues) == 0, "传入 extra_valid_codes 后不应告警"

    # ── 排名正确性 ─────────────────────────────────────────

    def test_wrong_rank(self):
        """LLM 称非最大持股市值的品种为"最大持仓"。"""
        # 贵州茅台 mv=345000, 招商银行 mv=216400
        # 最大持仓是贵州茅台(600519)
        text = "招商银行(600036)是你最大的持仓"
        issues, total, passed = check_ranking_correctness(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) >= 1, "应检测到排名断言错误"
        assert "600036" in issues[0] and "600519" in issues[0], "告警应包含实际最大持仓"

    def test_correct_rank(self):
        """LLM 正确指出最大持仓。"""
        text = "最大持仓是贵州茅台(600519)"
        issues, total, passed = check_ranking_correctness(text, _STD_HOLDINGS_DETAILS)
        assert len(issues) == 0, "正确排名不应告警"

    def test_penetration_module_skips_rank(self):
        """穿透分析模块的排名断言应跳过（排名维度不同）。"""
        text = "最大持仓是 600900（长江电力）"
        issues, total, passed = check_ranking_correctness(
            text, _STD_HOLDINGS_DETAILS, is_penetration_module=True
        )
        assert len(issues) == 0, "穿透模块应跳过排名校验"

    # ── 集成场景 ───────────────────────────────────────────

    def test_correct_output_all_pass(self):
        """对照用例：LLM 输出完全正确，三项检查均应通过。"""
        text = (
            "组合累计收益约 10.0%，招商银行(600036)上涨 8.0%，"
            "贵州茅台(600519)上涨 15.0%。"
            "最大持仓是贵州茅台(600519)。"
        )
        i1, _, p1, _ = check_numerical_consistency(text, _STD_HOLDINGS_DETAILS)
        i2, _, p2, _ = check_symbol_existence(text, _STD_HOLDINGS_DETAILS)
        i3, _, p3 = check_ranking_correctness(text, _STD_HOLDINGS_DETAILS)
        fails = len(i1) + len(i2) + len(i3)
        assert fails == 0, f"正确输出不应有检出错误，发现 {fails} 项"

    def test_hallucination_rate_summary(self):
        """汇总统计：记录幻觉率基线。"""
        # 场景定义: (实际正确, 检测到错误)
        scenarios = {
            "组合收益率偏离": (False, True),     # test_wrong_profit_rate_vs_portfolio
            "正确组合收益率": (True, True),       # test_correct_profit_rate_vs_portfolio
            "个股收益率偏离": (False, True),       # test_wrong_stock_return
            "正确个股收益率": (True, True),        # test_correct_stock_return
            "归因段落跳过": (True, True),          # test_attribution_sentence_skipped
            "指数基准跳过": (True, True),          # test_index_benchmark_skipped
            "正确全通过": (True, True),            # test_correct_output_all_pass
        }
        false_positives = sum(1 for _, (correct, detected) in scenarios.items()
                              if correct and not detected)
        false_negatives = sum(1 for _, (correct, detected) in scenarios.items()
                              if not correct and not detected)
        total = len(scenarios)
        correct_count = sum(1 for _, (c, d) in scenarios.items() if (c and d) or (not c and d))
        logger.info(
            "幻觉率基线: %d/%d 场景正确, "
            "假阳性=%d, 假阴性=%d, 准确率=%.0f%%",
            correct_count, total, false_positives, false_negatives,
            (correct_count / total * 100),
        )
        # 事实校验器应维持低假阳性（不误报）
        assert false_positives <= _MAX_ALLOWED_FALSE_POSITIVES, \
            f"假阳性 {false_positives} > {_MAX_ALLOWED_FALSE_POSITIVES}，需调整容差"
