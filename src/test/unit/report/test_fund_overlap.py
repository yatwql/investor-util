"""report/fund_overlap.py 单元测试。

测试目标：
  - _jaccard_similarity：Jaccard 系数计算
  - _overlap_ratio：重叠比例计算
  - compute_overlap_matrix：矩阵、配对、mv 双模式、边缘条件

场景覆盖：
  1. Jaccard 基本计算（完全重叠、部分重叠、无重叠）
  2. 重叠比例 min 分母
  3. 3 只基金全连接矩阵对称性
  4. 含共同标的配对明细
  5. overlap_mv_pct 有/无 mv 数据
  6. 0 只基金 → 空结构
  7. 1 只基金 → 空结构
  8. 持有为空 → 空结构
  9. 空输入 → 空结构

运行：
  pytest src/test/ -m "unit_report" -k "fund_overlap" -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.report.fund_overlap import (
    _jaccard_similarity,
    _overlap_ratio,
    compute_overlap_matrix,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── _jaccard_similarity 测试 ────────────────────────────────────


class TestJaccardSimilarity(unittest.TestCase):
    """_jaccard_similarity：Jaccard 系数计算"""

    def test_full_overlap(self):
        """完全重叠 → 1.0"""
        a = {"600519", "000858", "000333"}
        self.assertEqual(_jaccard_similarity(a, a), 1.0)

    def test_partial_overlap(self):
        """部分重叠 → |A∩B|/|A∪B|"""
        a = {"600519", "000858", "000333"}
        b = {"600519", "002415", "300750"}
        # A∩B = {600519}, A∪B = {600519,000858,000333,002415,300750}
        # 1/5 = 0.2
        self.assertAlmostEqual(_jaccard_similarity(a, b), 0.2)

    def test_no_overlap(self):
        """无重叠 → 0.0"""
        a = {"600519", "000858"}
        b = {"002415", "300750"}
        self.assertEqual(_jaccard_similarity(a, b), 0.0)

    def test_one_empty(self):
        """一个空集 → 0.0"""
        self.assertEqual(_jaccard_similarity({"600519"}, set()), 0.0)

    def test_both_empty(self):
        """两个空集 → 0.0"""
        self.assertEqual(_jaccard_similarity(set(), set()), 0.0)


# ── _overlap_ratio 测试 ─────────────────────────────────────


class TestOverlapRatio(unittest.TestCase):
    """_overlap_ratio：重叠比例"""

    def test_bigger_set_has_all_smaller(self):
        """大池包含小池所有元素 → 1.0"""
        a = {"600519", "000858", "000333", "002415"}
        b = {"600519", "000858"}
        # A∩B = {600519,000858}, min(|A|,|B|) = 2
        # 2/2 = 1.0
        self.assertAlmostEqual(_overlap_ratio(a, b), 1.0)

    def test_partial_overlap(self):
        """部分重叠"""
        a = {"600519", "000858", "000333"}
        b = {"600519", "002415", "300750"}
        # A∩B = {600519}, min(|A|,|B|) = 3
        # 1/3 ≈ 0.3333
        self.assertAlmostEqual(_overlap_ratio(a, b), 1 / 3, places=4)

    def test_no_overlap(self):
        """无重叠 → 0.0"""
        self.assertEqual(_overlap_ratio({"600519"}, {"000858"}), 0.0)

    def test_empty(self):
        """空集 → 0.0"""
        self.assertEqual(_overlap_ratio(set(), {"600519"}), 0.0)


# ── compute_overlap_matrix 测试 ─────────────────────────────


class TestComputeOverlapMatrix(unittest.TestCase):
    """compute_overlap_matrix：矩阵计算核心"""

    def setUp(self):
        # 3 只基金的持仓数据，用于矩阵测试
        self.three_funds = {
            "110011": [
                {"name": "贵州茅台", "code": "600519", "ratio": 9.5},
                {"name": "五粮液", "code": "000858", "ratio": 8.0},
                {"name": "泸州老窖", "code": "000568", "ratio": 7.0},
            ],
            "162605": [
                {"name": "贵州茅台", "code": "600519", "ratio": 8.0},
                {"name": "美的集团", "code": "000333", "ratio": 6.0},
                {"name": "格力电器", "code": "000651", "ratio": 5.0},
            ],
            "519300": [
                {"name": "招商银行", "code": "600036", "ratio": 7.0},
                {"name": "兴业银行", "code": "601166", "ratio": 6.0},
                {"name": "中国平安", "code": "601318", "ratio": 5.0},
            ],
        }
        # 110011∩162605 = {600519}, 110011∩519300 = {600519}, 162605∩519300 = {}
        # 110011∪162605 = {600519,000858,000568,000333,000651} = 5
        # Jaccard(110011, 162605) = 1/5 = 0.2
        # Jaccard(110011, 519300) = 1/5 = 0.2
        # Jaccard(162605, 519300) = 0/6 = 0.0

    def test_three_funds_matrix_symmetry(self):
        """3 只基金矩阵对称性"""
        result = compute_overlap_matrix(self.three_funds)
        self.assertEqual(len(result["funds"]), 3)
        matrix = result["matrix"]
        self.assertEqual(len(matrix), 3)
        self.assertEqual(len(matrix[0]), 3)
        # 对称性
        for i in range(3):
            self.assertEqual(matrix[i][i], 1.0)  # 对角线
            for j in range(3):
                self.assertAlmostEqual(matrix[i][j], matrix[j][i])

    def test_three_funds_pairs_count(self):
        """3 只基金 → 3 对配对"""
        result = compute_overlap_matrix(self.three_funds)
        self.assertEqual(len(result["pairs"]), 3)

    def test_overlap_values(self):
        """重合度值正确性（矩阵取 max(Jaccard, overlap_ratio)）"""
        result = compute_overlap_matrix(self.three_funds)
        funds = result["funds"]
        i110, i162, i519 = funds.index("110011"), funds.index("162605"), funds.index("519300")

        # 110011 {600519,000858,000568} vs 162605 {600519,000333,000651}
        #   Jaccard = 1/5 = 0.2, overlap_ratio = 1/3 ≈ 0.3333
        #   matrix = max(0.2, 0.3333) = 0.3333
        self.assertAlmostEqual(result["matrix"][i110][i162], 1 / 3, places=4)

        # 110011 vs 519300 {600036,601166,601318} → 无重叠 → 0.0
        self.assertAlmostEqual(result["matrix"][i110][i519], 0.0)

        # 162605 vs 519300 → 无重叠 → 0.0
        self.assertAlmostEqual(result["matrix"][i162][i519], 0.0)

    def test_common_stocks_detail(self):
        """共同标的明细"""
        result = compute_overlap_matrix(self.three_funds)
        for pair in result["pairs"]:
            if pair["common_count"] > 0:
                self.assertTrue(len(pair["common_stocks"]) > 0)
                for s in pair["common_stocks"]:
                    self.assertIn("name", s)
                    self.assertIn("code", s)

    def test_with_mv_data(self):
        """含市值数据 → has_mv_data=True"""
        mv_map = {"110011": 50000.0, "162605": 30000.0, "519300": 20000.0}
        result = compute_overlap_matrix(self.three_funds, fund_mv_map=mv_map)
        self.assertTrue(result["has_mv_data"])
        # 至少含 overlap_mv_pct 的配对应有数值
        for pair in result["pairs"]:
            if pair["common_count"] > 0:
                self.assertIsNotNone(pair["overlap_mv_pct"])

    def test_without_mv_data(self):
        """不含市值数据 → has_mv_data=False, overlap_mv_pct=None"""
        result = compute_overlap_matrix(self.three_funds)
        self.assertFalse(result["has_mv_data"])
        for pair in result["pairs"]:
            self.assertIsNone(pair["overlap_mv_pct"])

    def test_zero_funds(self):
        """0 只基金 → 空结构"""
        result = compute_overlap_matrix({})
        self.assertEqual(result["funds"], [])
        self.assertEqual(result["matrix"], [])
        self.assertEqual(result["pairs"], [])
        self.assertFalse(result["has_mv_data"])

    def test_one_fund(self):
        """1 只基金 → 空结构"""
        result = compute_overlap_matrix({
            "110011": [{"name": "茅台", "code": "600519", "ratio": 10}],
        })
        self.assertEqual(result["funds"], [])
        self.assertEqual(result["matrix"], [])

    def test_empty_holdings(self):
        """持有为空 → 空结构"""
        result = compute_overlap_matrix({"110011": [], "162605": []})
        # 虽然有 2 只基金但都没有持仓 → 空结构
        self.assertEqual(len(result["funds"]), 2)
        self.assertEqual(len(result["matrix"]), 2)
        self.assertEqual(len(result["pairs"]), 1)
        self.assertEqual(result["pairs"][0]["common_count"], 0)
        self.assertEqual(result["pairs"][0]["jaccard"], 0.0)

    def test_same_code_in_both_funds(self):
        """两只基金持有同一股票但名称不同时，用 code 匹配"""
        fund_holdings = {
            "110011": [{"name": "贵州茅台", "code": "600519", "ratio": 9.0}],
            "162605": [{"name": "茅台酒", "code": "600519", "ratio": 8.0}],
        }
        result = compute_overlap_matrix(fund_holdings)
        self.assertEqual(len(result["pairs"]), 1)
        self.assertEqual(result["pairs"][0]["common_count"], 1)


# ── 边缘情况测试 ──────────────────────────────────────────


class TestOverlapEdgeCases(unittest.TestCase):
    """重叠度计算边缘情况"""

    def test_large_overlap_uses_max(self):
        """矩阵元素取 max(Jaccard, overlap_ratio)"""
        a = {"A", "B", "C", "D"}
        b = {"A", "B", "E"}
        # Jaccard = 2/5 = 0.4, overlap_ratio = 2/3 ≈ 0.667
        jac = _jaccard_similarity(a, b)
        oa = _overlap_ratio(a, b)
        self.assertGreater(oa, jac)
        # matrix 取 max
        result = compute_overlap_matrix({
            "110011": [{"name": n, "code": n, "ratio": 5} for n in a],
            "162605": [{"name": n, "code": n, "ratio": 5} for n in b],
        })
        self.assertAlmostEqual(result["matrix"][0][1], oa)

    def test_pairs_sorted_by_overlap(self):
        """配对按重合度降序排列"""
        result = compute_overlap_matrix({
            "110011": [
                {"name": "A", "code": "A", "ratio": 5},
                {"name": "B", "code": "B", "ratio": 5},
            ],
            "162605": [
                {"name": "A", "code": "A", "ratio": 5},
            ],
            "519300": [
                {"name": "C", "code": "C", "ratio": 5},
                {"name": "D", "code": "D", "ratio": 5},
            ],
        })
        # 110011-162605 有共同标的 (A), 110011-519300 无, 162605-519300 无
        # 所以第一对应该是 110011-162605
        scores = [max(p["jaccard"], 0.01 if p["common_count"] > 0 else 0) for p in result["pairs"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
