"""候选基金比较增强模块单元测试。

覆盖：
  - resolve_candidates 代码校验/去重/超上限截断
  - build_candidate_compare_data 开关门控 / 无候选降级 / 行构建 / 单候选失败降级
  - 与现有持仓重合度复用 compute_overlap_matrix
全部 fetcher / 风格判定 / 重合度均为 mock，禁止真实网络请求。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

import pytest

from src.python.report import fund_candidate as fc

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _rankings(code: str, name: str | None = None) -> dict:
    """构造 fetch_fund_rankings_cached 返回的排名数据。"""
    return {
        "code": code,
        "name": name or f"候选基金{code}",
        "rankings": {
            "近1月": {"return": 0.0123},
            "近3月": {"return": 0.0567},
            "近6月": {"return": 0.1101},
            "近1年": {"return": -0.0201},
            "同类排名": {"rank": "159", "total": "358", "percentile": "55.59"},
        },
        "rating": "优秀",
        "risk_analysis": {"年化波动率": 15.2, "最大回撤": -18.5},
    }


class TestResolveCandidates(unittest.TestCase):
    """候选代码校验与上限。"""

    def test_accepts_valid_six_digit_codes(self):
        valid, invalid, exceeded = fc.resolve_candidates(["000001", "161725", "110022"])
        self.assertEqual(valid, ["000001", "161725", "110022"])
        self.assertEqual(invalid, [])
        self.assertFalse(exceeded)

    def test_filters_invalid_entries(self):
        valid, invalid, exceeded = fc.resolve_candidates(["000001", "abc123", "123", "", "110022"])
        self.assertEqual(valid, ["000001", "110022"])
        self.assertEqual(invalid, ["abc123", "123", ""])
        self.assertFalse(exceeded)

    def test_dedupes_keeping_first_order(self):
        valid, _invalid, _exceeded = fc.resolve_candidates(["000001", "110022", "000001", "110022"])
        self.assertEqual(valid, ["000001", "110022"])

    def test_truncates_over_limit_and_flags(self):
        codes = [f"{i:06d}" for i in range(1, 13)]  # 12 只，超 10 上限
        valid, _invalid, exceeded = fc.resolve_candidates(codes)
        self.assertTrue(exceeded)
        self.assertEqual(len(valid), 10)
        self.assertEqual(valid[0], "000001")
        self.assertEqual(valid[-1], "000010")

    def test_empty_input(self):
        valid, invalid, exceeded = fc.resolve_candidates([])
        self.assertEqual(valid, [])
        self.assertEqual(invalid, [])
        self.assertFalse(exceeded)


class TestBuildCandidateCompareData(unittest.TestCase):
    """候选比较数据构建与开关门控。"""

    def _mock_config(self, enabled: bool = True, candidates: list[str] | None = None):
        cfg = MagicMock()
        return cfg, enabled, candidates or []

    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_switch_off_returns_none(self, mock_get, mock_enable):
        """行为断言：开关默认关时 5 章不渲染比较子表（build 返回 None）。"""
        mock_enable.return_value = False
        result = fc.build_candidate_compare_data([], config={})
        self.assertIsNone(result)
        mock_get.assert_not_called()

    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_switch_on_no_candidates_degrades(self, mock_get, mock_enable):
        """开关开但无候选 → available=False 降级。"""
        mock_enable.return_value = True
        mock_get.return_value = []
        result = fc.build_candidate_compare_data([], config={})
        self.assertIsNotNone(result)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_valid_candidate")
        self.assertEqual(result["rows"], [])

    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_invalid_only_candidates_degrades(self, mock_get, mock_enable):
        mock_enable.return_value = True
        mock_get.return_value = ["not-a-code", "123"]
        result = fc.build_candidate_compare_data([], config={})
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_valid_candidate")
        self.assertEqual(result["invalid"], ["not-a-code", "123"])

    @patch("src.python.report.fund_candidate._collect_existing_fund_holdings")
    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_builds_rows_with_full_dimensions(self, mock_get, mock_enable, mock_rank, mock_hold, mock_collect):
        """候选行包含全部比较维度（收益/排名/评级/回撤/风格/重合度）。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.side_effect = lambda code: _rankings(code)
        mock_hold.return_value = [
            {"name": "贵州茅台", "code": "600519", "ratio": 10.0},
            {"name": "宁德时代", "code": "300750", "ratio": 8.0},
        ]
        mock_collect.return_value = {"600519": [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]}
        with patch("src.python.report.fund_candidate.classify_fund_style") as mock_style:
            mock_style.return_value = {"code": "000001", "style": "大盘成长", "is_estimated": False, "details": []}
            with patch("src.python.report.fund_candidate.compute_overlap_matrix") as mock_overlap:
                mock_overlap.return_value = {
                    "fund_names": {"000001": "候选基金000001", "600519": "现有基金X"},
                    "pairs": [
                        {
                            "fund_a": "000001",
                            "fund_b": "600519",
                            "common_count": 2,
                            "jaccard": 0.5,
                            "overlap_mv_pct": None,
                            "common_stocks": [],
                        }
                    ],
                }
                result = fc.build_candidate_compare_data([], config={})

        self.assertTrue(result["available"])
        self.assertFalse(result["exceed_limit"])
        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertTrue(row["available"])
        self.assertEqual(row["name"], "候选基金000001")
        self.assertEqual(row["rating"], "优秀")
        self.assertEqual(row["rank_text"], "159/358")
        self.assertAlmostEqual(row["syl_近1年_raw"], -0.0201)
        self.assertEqual(row["syl_近1年"], "-2.01%")
        self.assertAlmostEqual(row["max_drawdown_raw"], -0.185)
        self.assertEqual(row["max_drawdown"], "-18.50%")
        self.assertEqual(row["style"], "大盘成长")
        self.assertEqual(row["overlap_name"], "现有基金X")
        self.assertAlmostEqual(row["overlap_jaccard_raw"], 0.5)
        self.assertEqual(row["overlap_jaccard"], "50.00%")

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_rank_fetch_failure_degrades_row(self, mock_get, mock_enable, mock_rank, mock_hold):
        """单候选排名获取失败 → 该行 available=False，不影响整体。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001", "110022"]
        mock_rank.side_effect = lambda code: _rankings(code) if code == "000001" else None
        mock_hold.return_value = None
        result = fc.build_candidate_compare_data([], config={})

        self.assertTrue(result["available"])
        rows = {r["code"]: r for r in result["rows"]}
        self.assertTrue(rows["000001"]["available"])
        self.assertFalse(rows["110022"]["available"])
        self.assertEqual(rows["110022"]["reason"], "rank_unavailable")
        # 仅成功候选触发持仓获取；排名失败候选短路，不触发持仓/风格/重合
        self.assertEqual(mock_hold.call_args_list, [call("000001")])

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_over_limit_truncates_and_flags(self, mock_get, mock_enable, mock_rank, mock_hold):
        """候选 >10 只 → 拒绝（截断）并标记 exceed_limit。"""
        mock_enable.return_value = True
        codes = [f"{i:06d}" for i in range(1, 13)]
        mock_get.return_value = codes
        mock_rank.side_effect = lambda code: _rankings(code)
        mock_hold.return_value = None
        result = fc.build_candidate_compare_data([], config={})

        self.assertTrue(result["available"])
        self.assertTrue(result["exceed_limit"])
        self.assertEqual(len(result["rows"]), 10)

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_no_existing_funds_overlap_is_dash(self, mock_get, mock_enable, mock_rank, mock_hold):
        """无现有持仓基金 → 重合度列显示 '--'（不调用重合度矩阵）。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.side_effect = lambda code: _rankings(code)
        mock_hold.return_value = []
        with patch("src.python.report.fund_candidate.classify_fund_style") as mock_style:
            mock_style.return_value = {"code": "000001", "style": "--", "is_estimated": False, "details": []}
            with patch("src.python.report.fund_candidate.compute_overlap_matrix") as mock_overlap:
                result = fc.build_candidate_compare_data([], config={})

        row = result["rows"][0]
        self.assertEqual(row["overlap_jaccard"], "--")
        self.assertIsNone(row["overlap_jaccard_raw"])
        mock_overlap.assert_not_called()

    @patch("src.python.report.fund_candidate._collect_existing_fund_holdings")
    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_existing_holdings_reused_for_overlap(self, mock_get, mock_enable, mock_rank, mock_hold, mock_collect):
        """与现有持仓重合度复用 compute_overlap_matrix（传现有持仓映射）。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.side_effect = lambda code: _rankings(code)
        mock_hold.return_value = [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]
        mock_collect.return_value = {"600519": [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]}
        with patch("src.python.report.fund_candidate.classify_fund_style") as mock_style:
            mock_style.return_value = {"code": "000001", "style": "--", "is_estimated": False, "details": []}
            with patch("src.python.report.fund_candidate.compute_overlap_matrix") as mock_overlap:
                mock_overlap.return_value = {
                    "fund_names": {"000001": "候选", "600519": "现有"},
                    "pairs": [
                        {
                            "fund_a": "000001",
                            "fund_b": "600519",
                            "common_count": 1,
                            "jaccard": 0.2,
                            "overlap_mv_pct": None,
                            "common_stocks": [],
                        }
                    ],
                }
                fc.build_candidate_compare_data([], config={})

        mock_collect.assert_called_once()
        args = mock_overlap.call_args[0][0]
        self.assertIn("000001", args)
        self.assertIn("600519", args)

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_cli_codes_merged_with_config(self, mock_get, mock_enable, mock_rank, mock_hold):
        """CLI 候选代码与 config 候选合并（去重保序）。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.side_effect = lambda code: _rankings(code)
        mock_hold.return_value = None
        result = fc.build_candidate_compare_data([], config={}, cli_codes=["110022", "000001"])
        rows = {r["code"]: r for r in result["rows"]}
        self.assertEqual(set(rows), {"000001", "110022"})
        self.assertTrue(rows["000001"]["available"])
        self.assertEqual(mock_hold.call_args_list, [call("000001"), call("110022")])

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_partial_period_and_bad_values(self, mock_get, mock_enable, mock_rank, mock_hold):
        """缺失期间/非法数值 → 该维度显示 '--'，不崩溃。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_hold.return_value = []
        bad_rank = {
            "code": "000001",
            "name": "候选A",
            "rankings": {
                "近1月": {"return": "not-a-number"},  # 非法数值 → 该期 '--'
                "近3月": None,  # 缺失期间 → '--'
                "同类排名": {"rank": "1", "total": "10"},
            },
            "risk_analysis": {"最大回撤": "bad"},  # 非法回撤 → '--'
        }
        mock_rank.return_value = bad_rank
        result = fc.build_candidate_compare_data([], config={})
        row = result["rows"][0]
        self.assertEqual(row["syl_近1月"], "--")
        self.assertEqual(row["syl_近3月"], "--")
        self.assertEqual(row["syl_近6月"], "--")
        self.assertEqual(row["syl_近1年"], "--")
        self.assertEqual(row["max_drawdown"], "--")
        self.assertTrue(row["available"])

    @patch("src.python.report.fund_candidate._collect_existing_fund_holdings")
    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_style_classify_failure_degrades(self, mock_get, mock_enable, mock_rank, mock_hold, mock_collect):
        """风格判定失败 → style 显示 '--'，不阻塞候选行。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.return_value = _rankings("000001")
        mock_hold.return_value = [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]
        mock_collect.return_value = {"600519": [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]}
        with patch("src.python.report.fund_candidate.classify_fund_style", side_effect=RuntimeError("boom")):
            with patch("src.python.report.fund_candidate.compute_overlap_matrix") as mock_overlap:
                mock_overlap.return_value = {
                    "fund_names": {"110022": "其他基金"},
                    "pairs": [
                        {
                            "fund_a": "110022",
                            "fund_b": "600519",
                            "common_count": 1,
                            "jaccard": 0.1,
                            "overlap_mv_pct": None,
                            "common_stocks": [],
                        }
                    ],
                }
                result = fc.build_candidate_compare_data([], config={})
        row = result["rows"][0]
        self.assertEqual(row["style"], "--")
        self.assertEqual(row["overlap_jaccard"], "--")
        self.assertTrue(row["available"])

    @patch("src.python.report.fund_candidate._collect_existing_fund_holdings")
    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_overlap_matrix_failure_degrades(self, mock_get, mock_enable, mock_rank, mock_hold, mock_collect):
        """重合度矩阵计算失败 → 重合度列 '--'，不阻塞候选行。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.return_value = _rankings("000001")
        mock_hold.return_value = [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]
        mock_collect.return_value = {"600519": [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]}
        with patch("src.python.report.fund_candidate.classify_fund_style") as mock_style:
            mock_style.return_value = {"code": "000001", "style": "--", "is_estimated": False, "details": []}
            with patch(
                "src.python.report.fund_candidate.compute_overlap_matrix",
                side_effect=RuntimeError("boom"),
            ):
                result = fc.build_candidate_compare_data([], config={})
        row = result["rows"][0]
        self.assertEqual(row["overlap_jaccard"], "--")
        self.assertTrue(row["available"])

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    @patch("src.python.report.fund_candidate.fetch_fund_rankings_cached")
    @patch("src.python.report.fund_candidate.is_enable_candidate_compare")
    @patch("src.python.report.fund_candidate.get_comparison_candidates")
    def test_overlap_with_no_existing_funds(self, mock_get, mock_enable, mock_rank, mock_hold):
        """候选有持仓但无现有持仓基金 → 重合度列 '--'（不调矩阵）。"""
        mock_enable.return_value = True
        mock_get.return_value = ["000001"]
        mock_rank.return_value = _rankings("000001")
        mock_hold.return_value = [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]
        with patch("src.python.report.fund_candidate.classify_fund_style") as mock_style:
            mock_style.return_value = {"code": "000001", "style": "--", "is_estimated": False, "details": []}
            with patch("src.python.report.fund_candidate.compute_overlap_matrix") as mock_overlap:
                result = fc.build_candidate_compare_data([], config={})
        row = result["rows"][0]
        self.assertEqual(row["overlap_jaccard"], "--")
        mock_overlap.assert_not_called()

    def test_pct_str_none_and_bad_value(self):
        """百分数格式化：None/非法值 → '--'。"""
        self.assertEqual(fc._pct_str(None), "--")
        self.assertEqual(fc._pct_str("not-a-number"), "--")


class TestCollectExistingFundHoldings(unittest.TestCase):
    """现有持仓基金持仓明细收集。"""

    def _holding(self, name: str, code: str, account: str = "账户A"):
        class _H:
            def __init__(self, n, c, a):
                self.name = n
                self.code = c
                self.account = a

        return _H(name, code, account)

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    def test_collects_only_fund_holdings(self, mock_hold):
        """仅收集基金持仓；股票持仓安全跳过。"""
        mock_hold.return_value = [{"name": "贵州茅台", "code": "600519", "ratio": 10.0}]
        holdings = [
            self._holding("贵州茅台", "600519"),  # 股票，跳过
            self._holding("沪深300指数基金", "110020"),  # 基金，收集
        ]
        with patch(
            "src.python.report.fund_candidate.is_fund_holding",
            side_effect=lambda n, c, a: c == "110020",
        ):
            result = fc._collect_existing_fund_holdings(holdings)
        self.assertEqual(list(result.keys()), ["110020"])

    @patch("src.python.report.fund_candidate.fetch_fund_holdings_cached")
    def test_fetch_failure_skipped(self, mock_hold):
        """单基金持仓获取失败 → 跳过，不阻塞其余。"""
        mock_hold.side_effect = RuntimeError("network down")
        with patch("src.python.report.fund_candidate.is_fund_holding", return_value=True):
            result = fc._collect_existing_fund_holdings([self._holding("基金A", "110020")])
        self.assertEqual(result, {})

    def test_missing_attributes_skipped(self):
        """持仓对象缺属性 → 安全跳过。"""

        class _H:
            pass

        result = fc._collect_existing_fund_holdings([_H()])
        self.assertEqual(result, {})

    def test_empty_holdings(self):
        """空持仓 → 空映射。"""
        self.assertEqual(fc._collect_existing_fund_holdings([]), {})


if __name__ == "__main__":
    unittest.main()
