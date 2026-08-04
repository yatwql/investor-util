"""数据新鲜度与异常跳变检测单元测试 — 数据质量仪表盘「可信度」区块。

覆盖：
  - classify_freshness — 单品种新鲜度分类（实时/缓存/过期/降级）
  - detect_price_jumps — 单日 ±20% 异常跳变检测（含阈值边界 / 非交易日不误报）
  - build_freshness_summary — 可信度摘要数据契约（abnormal_count / summary / 跳变标注）

运行：
  python -m pytest src/test/unit/core/test_data_freshness.py -v
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import pytest

from src.python.core import data_freshness as df
from src.python.core.models import Holding

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

# 固定交易日 fixture（2026-08-04 周二，前一交易日 2026-08-03 周一）
_T = "2026-08-04"
_PREV = "2026-08-03"


def _holding(name: str, code: str, account: str = "证券") -> Holding:
    return Holding(account=account, name=name, code=code, shares=100, cost_price=10.0)


def _detail(
    code: str,
    name: str,
    price: float = 10.0,
    yesterday_close: float = 10.0,
    nav_date: str | None = _T,
    price_type: str = "场内收盘价(T)",
) -> SimpleNamespace:
    """构造最小行情明细（鸭子类型，仅含新鲜度判定所需属性）。"""
    return SimpleNamespace(
        code=code,
        name=name,
        price=price,
        yesterday_close=yesterday_close,
        nav_date=nav_date,
        price_type=price_type,
    )


# ═════════════════════════════════════════════════════════════
#  classify_freshness
# ═════════════════════════════════════════════════════════════


class TestClassifyFreshness(unittest.TestCase):
    """单品种新鲜度分类。"""

    def test_fresh_when_nav_today(self):
        """净值日期等于交易日 → 实时（fresh）。"""
        d = _detail("600900", "长江电力", nav_date=_T)
        self.assertEqual(df.classify_freshness(d, _T, _PREV), df.FRESHNESS_FRESH)

    def test_cached_when_nav_prev_day(self):
        """净值日期等于前一交易日 → 缓存（cached，正常 T-1）。"""
        d = _detail("005827", "易方达蓝筹精选", nav_date=_PREV)
        self.assertEqual(df.classify_freshness(d, _T, _PREV), df.FRESHNESS_CACHED)

    def test_stale_when_nav_before_prev(self):
        """净值日期早于前一交易日 → 过期（stale）。"""
        d = _detail("600900", "长江电力", nav_date="2026-07-31")
        self.assertEqual(df.classify_freshness(d, _T, _PREV), df.FRESHNESS_STALE)

    def test_stale_when_nav_missing(self):
        """净值日期缺失/不可解析 → 过期（stale）。"""
        d = _detail("600900", "长江电力", nav_date=None)
        self.assertEqual(df.classify_freshness(d, _T, _PREV), df.FRESHNESS_STALE)
        d2 = _detail("600900", "长江电力", nav_date="非日期")
        self.assertEqual(df.classify_freshness(d2, _T, _PREV), df.FRESHNESS_STALE)

    def test_degraded_when_zero_price(self):
        """price <= 0 → 降级（degraded）。"""
        d = _detail("600900", "长江电力", price=0.0)
        self.assertEqual(df.classify_freshness(d, _T, _PREV), df.FRESHNESS_DEGRADED)

    def test_degraded_when_no_quote_type(self):
        """price_type 为「暂无行情」→ 降级（degraded）。"""
        d = _detail("600900", "长江电力", price_type="暂无行情")
        self.assertEqual(df.classify_freshness(d, _T, _PREV), df.FRESHNESS_DEGRADED)


# ═════════════════════════════════════════════════════════════
#  detect_price_jumps
# ═════════════════════════════════════════════════════════════


class TestDetectPriceJumps(unittest.TestCase):
    """单日 ±20% 异常跳变检测。"""

    def test_jump_up_over_threshold(self):
        """单日 +25% 突变 → 标记疑似数据错误（行为断言）。"""
        d = _detail("600900", "长江电力", price=12.5, yesterday_close=10.0)
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(len(jumps), 1)
        j = jumps[0]
        self.assertEqual(j["code"], "600900")
        self.assertEqual(j["direction"], "up")
        self.assertIn("疑似数据错误", j["label"])
        self.assertGreaterEqual(j["change_pct"], 20.0)

    def test_jump_down_over_threshold(self):
        """单日 -25% 突变 → 标记疑似数据错误（下跌方向）。"""
        d = _detail("600900", "长江电力", price=7.5, yesterday_close=10.0)
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(len(jumps), 1)
        self.assertEqual(jumps[0]["direction"], "down")
        self.assertIn("疑似数据错误", jumps[0]["label"])

    def test_below_threshold_not_jump(self):
        """单日 +19% 变化 → 未达阈值，不标记。"""
        d = _detail("600900", "长江电力", price=11.9, yesterday_close=10.0)
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(jumps, [])

    def test_threshold_boundary_exact(self):
        """恰为 ±20% → 达到阈值，标记跳变（边界含等号）。"""
        d = _detail("600900", "长江电力", price=12.0, yesterday_close=10.0)
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(len(jumps), 1)

    def test_stale_not_jump_cross_days(self):
        """数据过期（净值早于前一交易日）→ 不做单日跳变判定（跨非交易日不误报）。"""
        d = _detail("600900", "长江电力", price=13.0, yesterday_close=10.0, nav_date="2026-07-29")
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(jumps, [])

    def test_degraded_not_jump(self):
        """降级（无有效行情）→ 不做跳变判定。"""
        d = _detail("600900", "长江电力", price=0.0, yesterday_close=10.0)
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(jumps, [])

    def test_zero_yesterday_close_no_division(self):
        """昨收为 0/缺失 → 跳过（避免除零），不报错。"""
        d = _detail("600900", "长江电力", price=12.0, yesterday_close=0.0)
        jumps = df.detect_price_jumps([d], _T, _PREV)
        self.assertEqual(jumps, [])

    def test_custom_threshold(self):
        """自定义阈值（如 10%）→ 按传入阈值判定。"""
        d = _detail("600900", "长江电力", price=11.0, yesterday_close=10.0)
        jumps = df.detect_price_jumps([d], _T, _PREV, threshold=0.10)
        self.assertEqual(len(jumps), 1)


# ═════════════════════════════════════════════════════════════
#  build_freshness_summary
# ═════════════════════════════════════════════════════════════


class TestBuildFreshnessSummary(unittest.TestCase):
    """可信度摘要数据契约。"""

    def test_abnormal_count_includes_jump_and_stale(self):
        """异常品种计数 = 跳变 + 过期/降级品种。"""
        holdings = [
            _holding("长江电力", "600900"),
            _holding("易方达蓝筹精选", "005827", account="支付宝"),
            _holding("贵州茅台", "600519"),
        ]
        details = [
            _detail("600900", "长江电力", price=12.5, yesterday_close=10.0),  # +25% 跳变
            _detail("005827", "易方达蓝筹精选", nav_date="2026-07-31"),  # 过期
            _detail("600519", "贵州茅台", price=1700.0, yesterday_close=1699.0),  # 正常
        ]
        summary = df.build_freshness_summary(holdings, details, _T, _PREV)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["abnormal_count"], 2)
        by_code = {i["code"]: i for i in summary["items"]}
        self.assertEqual(by_code["600900"]["freshness"], df.FRESHNESS_FRESH)
        self.assertTrue(by_code["600900"]["jump"])
        self.assertEqual(by_code["005827"]["freshness"], df.FRESHNESS_STALE)
        self.assertFalse(by_code["600519"]["jump"])

    def test_summary_text_counts_abnormal(self):
        """摘要文本正确计数（行为断言：摘要行计数）。"""
        holdings = [
            _holding("长江电力", "600900"),
            _holding("贵州茅台", "600519"),
        ]
        details = [
            _detail("600900", "长江电力", price=12.5, yesterday_close=10.0),
            _detail("600519", "贵州茅台", price=1700.0, yesterday_close=1699.0),
        ]
        summary = df.build_freshness_summary(holdings, details, _T, _PREV)
        self.assertIn("2", summary["summary"])
        self.assertIn("1", summary["summary"])

    def test_all_normal_zero_abnormal(self):
        """全部品种正常 → abnormal_count=0，无跳变。"""
        holdings = [_holding("长江电力", "600900")]
        details = [_detail("600900", "长江电力", price=10.1, yesterday_close=10.0)]
        summary = df.build_freshness_summary(holdings, details, _T, _PREV)
        self.assertEqual(summary["abnormal_count"], 0)
        self.assertFalse(summary["items"][0]["jump"])

    def test_empty_holdings(self):
        """无持仓 → available=False，不报错。"""
        summary = df.build_freshness_summary([], [], _T, _PREV)
        self.assertFalse(summary["available"])
        self.assertEqual(summary["items"], [])
        self.assertEqual(summary["abnormal_count"], 0)

    def test_behavioral_plus25_marked_and_counted(self):
        """行为断言：构造净值单日 +25% 突变 → 标注疑似数据错误，摘要行正确计数。"""
        holdings = [
            _holding("长江电力", "600900"),
            _holding("易方达蓝筹精选", "005827", account="支付宝"),
        ]
        details = [
            _detail("005827", "易方达蓝筹精选", price=1.25, yesterday_close=1.0),
            _detail("600900", "长江电力", price=25.0, yesterday_close=25.1),
        ]
        summary = df.build_freshness_summary(holdings, details, _T, _PREV)
        by_code = {i["code"]: i for i in summary["items"]}
        self.assertTrue(by_code["005827"]["jump"])
        self.assertIn("疑似数据错误", by_code["005827"]["jump_label"])
        self.assertEqual(summary["abnormal_count"], 1)


if __name__ == "__main__":
    unittest.main()
