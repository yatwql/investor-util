"""LLM 事实锚定校验器 — 回放语境豁免 / 回撤紧邻窗口 / 近并列排名注记。

覆盖场景（均为实盘误报/误修正的回归）：
  - 策略回放句（回放/回测/买入持有）整句跳过，模拟指标不被误修正为持仓收益率
  - 回撤词紧邻数值时优先判回撤语境，不受同句远端收益词干扰
  - 排名声称与实际名次市值近乎并列时，告警文案附加差距注记
  - 历史（已清仓/已变动）代码并入有效集，不再误报"不在当前持仓中"

运行：
  pytest src/test/unit/llm/test_fact_checker_replay_context.py -v
"""

from __future__ import annotations

import pytest

from src.python.llm.fact_checker import (
    check_numerical_consistency,
    check_ranking_correctness,
    check_symbol_existence,
    run_fact_check,
)
from src.python.llm.fact_checker._context import _is_drawdown_context, _is_replay_context
from src.python.llm.generators_orchestrator import extract_historical_codes

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
]


@pytest.fixture
def holdings_with_rates() -> list[dict]:
    """含 profit_rate（百分单位）的持仓，用于回放句误修正回归。

    096001 实际收益率 9.16%——实盘事故中回放句的「买入持有 -7.16%」被
    全局最近邻兜底归因到该品种并被自动"修正"为 9.2%。
    """
    return [
        {
            "name": "华宝中证100ETF联接A",
            "code": "096001",
            "market_value": 30000.0,
            "cost": 27480.0,
            "profit_rate": 9.16,
        },
        {
            "name": "招商中证电池主题ETF",
            "code": "561910",
            "market_value": 34320.0,
            "cost": 41130.0,
            "profit_rate": -16.56,
        },
        {
            "name": "国泰中证全指家电ETF联接A",
            "code": "012325",
            "market_value": 34173.0,
            "cost": 32700.0,
            "profit_rate": 4.48,
        },
    ]


class TestReplayContextExemption:
    """策略回放/回测语境整句跳过（模拟指标与实际收益率不同源）。"""

    def test_replay_keywords_detected(self) -> None:
        """回放/回测/买入持有/What-if/as-if 均判为回放语境。"""
        for sentence in (
            "回放显示规则A在回放窗口内收益 -5.35%。",
            "回测结果显示最大回撤 10.28%。",
            "区间收益 -5.35% 优于买入持有 -7.16%。",
            "What-if 情景下收益为 -3.2%。",
            "as-if 模拟（历史净值 × 当前份额）收益 -7.16%。",
        ):
            assert _is_replay_context(sentence), sentence

    def test_non_replay_sentence_not_exempt(self) -> None:
        """普通收益句不判为回放语境（豁免不得泛化）。"""
        assert not _is_replay_context("096001 实际收益率 9.16%，为组合正贡献。")

    def test_replay_sentence_values_not_corrected(self, holdings_with_rates) -> None:
        """回放句中的模拟指标不产生告警、不被自动修正。

        实盘事故：回放句「区间收益 -5.35% 优于买入持有 -7.16%」中的 -7.16%
        被归因到 096001（实际 9.16%）并被自动"修正"为 9.2%，把正确的回放数据改错。
        """
        text = (
            "回放显示规则A（月度定期）在回放窗口内收益 -5.35%、最大回撤 10.28%、"
            "夏普 -0.80，全面优于买入持有（-7.16% / 11.77% / -1.04）。"
        )
        issues, _checked, _passed, corrections = check_numerical_consistency(
            text, holdings_with_rates, max_drawdown_pct=11.77
        )
        assert issues == []
        assert corrections == []

    def test_replay_sentence_with_holding_code_still_exempt(self, holdings_with_rates) -> None:
        """回放句即使含持仓代码也整句跳过（模拟口径与持仓口径不同源）。"""
        text = "据【调仓纪律回放】，规则A区间收益 -5.35% 优于买入持有 -7.16%，561910 未参与回放。"
        issues, _checked, _passed, corrections = check_numerical_consistency(
            text, holdings_with_rates, max_drawdown_pct=11.77
        )
        assert issues == []
        assert corrections == []

    def test_non_replay_value_still_checked(self, holdings_with_rates) -> None:
        """非回放句的数值仍正常校验（豁免不削弱既有能力）。"""
        text = "561910 实际收益率为 -3.0%，与成本相比仍处亏损。"
        issues, _checked, _passed, corrections = check_numerical_consistency(text, holdings_with_rates)
        assert issues, "非回放句的错误数值应被检出"
        assert corrections

    def test_run_fact_check_keeps_replay_values(self, holdings_with_rates) -> None:
        """端到端：run_fact_check 不改写回放句中的模拟指标。"""
        html = "<p>回放显示规则A在回放窗口内收益 -5.35%、最大回撤 10.28%，全面优于买入持有（-7.16% / 11.77%）。</p>"
        corrected, _summary = run_fact_check(
            html,
            holdings_with_rates,
            module_label="持仓体检报告",
            history_data={"max_drawdown_pct": 11.77},
        )
        assert "-7.16%" in corrected
        assert "10.28%" in corrected
        assert "9.2%" not in corrected


class TestDrawdownTightWindow:
    """回撤词紧邻数值时优先判回撤语境，不受同句远端收益词干扰。"""

    def test_tight_drawdown_keyword_wins_over_distant_profit(self) -> None:
        """「收益 -5.35%、最大回撤 10.28%」中 10.28 判为回撤语境。

        10.28 前 15 字符窗口含"收益"（属前一个数值的修饰词），若据此排除回撤
        语境，数值会掉入收益率路径被误修正。
        """
        sentence = "组合近一年收益 -5.35%、最大回撤 10.28%，风险收益比尚可。"
        idx = sentence.index("10.28")
        assert _is_drawdown_context(sentence, idx)

    def test_tight_profit_keyword_still_profit(self) -> None:
        """紧邻收益词的数值仍判为非回撤语境（不误伤）。"""
        sentence = "组合历史最大回撤 19.0%，累计收益 30.3%。"
        idx = sentence.index("30.3")
        assert not _is_drawdown_context(sentence, idx)

    def test_drawdown_value_compared_with_actual_drawdown(self, holdings_with_rates) -> None:
        """回撤语境数值与实际最大回撤比较，不按个股收益率修正。"""
        text = "组合近一年收益 -5.35%、最大回撤 10.28%，风险收益比尚可。"
        issues, _checked, _passed, corrections = check_numerical_consistency(
            text, holdings_with_rates, max_drawdown_pct=10.28
        )
        # 10.28 与回撤数据一致 → 通过；-5.35 无匹配收益率 → 允许告警但不得修正为回撤值
        assert all("回撤" not in c[3] or "10.3" not in c[1] for c in corrections)
        assert not any("回撤相关数值 10.28%" in i for i in issues)


class TestNearTieRankingNote:
    """排名声称与实际名次市值近乎并列时附加差距注记。"""

    @staticmethod
    def _holdings() -> list[dict]:
        """构造近并列持仓：第2名与第3名市值差 147 元（占组合约 0.05%）。"""
        return [
            {"name": "甲", "code": "011506", "market_value": 35960.90},
            {"name": "乙", "code": "561910", "market_value": 34320.0},
            {"name": "丙", "code": "012325", "market_value": 34173.0},
            {"name": "丁", "code": "096001", "market_value": 30000.0},
        ]

    def test_near_tie_issue_carries_gap_note(self) -> None:
        """声称 561910 为第三大持仓（实际第二）→ 告警附近并列注记。"""
        text = "561910 已是组合第三大持仓，建议继续持有。"
        issues, checked, _passed = check_ranking_correctness(text, self._holdings())
        assert checked == 1
        assert len(issues) == 1
        assert "近并列" in issues[0]
        assert "561910" in issues[0]

    def test_clear_gap_issue_has_no_note(self) -> None:
        """市值差距显著时告警不带近并列注记。"""
        holdings = [
            {"name": "甲", "code": "011506", "market_value": 100000.0},
            {"name": "乙", "code": "561910", "market_value": 50000.0},
            {"name": "丙", "code": "012325", "market_value": 10000.0},
        ]
        text = "561910 已是组合第三大持仓，建议继续持有。"
        issues, checked, _passed = check_ranking_correctness(text, holdings)
        assert checked == 1
        assert len(issues) == 1
        assert "近并列" not in issues[0]

    def test_correct_claim_passes_without_issue(self) -> None:
        """声称与实际名次一致时不产生告警（注记逻辑不引入误报）。"""
        text = "561910 已是组合第二大持仓，建议继续持有。"
        issues, checked, passed = check_ranking_correctness(text, self._holdings())
        assert checked == 1
        assert passed == 1
        assert issues == []


class TestHistoricalCodesValid:
    """历史（已清仓/已变动）代码并入有效集，不再误报"不在当前持仓中"。"""

    def test_extract_historical_codes_from_diff_and_events(self) -> None:
        """从 diff.removed/added 与 holding_change_data.events 动态提取代码。"""
        pipeline_data = {
            "diff": {
                "removed": [{"name": "易方达国证自由现金流ETF", "code": "159222"}],
                "added": [{"name": "新进品种", "code": "588000"}],
            },
            "holding_change_data": {
                "events": [{"code": "159222", "action": "清仓"}, {"code": "512880", "action": "减仓"}]
            },
        }
        codes = extract_historical_codes(pipeline_data)
        assert codes == {"159222", "588000", "512880"}

    def test_extract_historical_codes_empty_without_pipeline(self) -> None:
        """无管线数据时返回空集（不引入隐式白名单）。"""
        assert extract_historical_codes(None) == set()
        assert extract_historical_codes({}) == set()

    def test_cleared_code_not_reported_when_in_valid_set(self) -> None:
        """已清仓代码并入有效集后不再报"不在当前持仓中"。"""
        holdings = [{"name": "甲", "code": "011506", "market_value": 1000.0}]
        text = "环比看，清仓易方达国证自由现金流ETF(159222) 后，组合集中度提升。"
        issues, _checked, _passed, _suggestions = check_symbol_existence(text, holdings)
        assert any("159222" in i for i in issues), "未并入有效集时应报出（前置条件）"

        issues2, _c2, _p2, _s2 = check_symbol_existence(text, holdings, extra_valid_codes={"159222"})
        assert not any("159222" in i for i in issues2)

    def test_run_fact_check_with_historical_codes(self) -> None:
        """端到端：extra_valid_codes 含历史代码时，清仓语境引用不产生告警。"""
        holdings = [{"name": "甲", "code": "011506", "market_value": 1000.0, "cost": 900.0}]
        html = "<p>环比看，清仓易方达国证自由现金流ETF(159222) 后，组合集中度提升。</p>"
        _corrected, summary = run_fact_check(html, holdings, module_label="持仓体检报告", extra_valid_codes={"159222"})
        assert "159222" not in summary
