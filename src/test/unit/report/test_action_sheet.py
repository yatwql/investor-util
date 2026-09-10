"""行动建议页签 Excel 呈现测试。

覆盖：
  - available=True → 行动摘要 + ① 再平衡信号 + ② 交易纪律 + ③ 调仓建议 + ④ 收益归因
  - 再平衡信号表格内容正确（代码/名称/占比/警戒线/建议动作）
  - 空子块 → 「组合内无品种超警戒线」/「暂无触发」占位
  - 收益归因 available=False / None → 「待生成」占位；可用时渲染 盈利来源/亏损来源
  - available=False（无持仓数据）→ 整页占位
  - action_data=None → 整页占位（§1.4.5 降级）

数据源为 `action_data` 契约（analysis/action_advisor.build_action_data 组装、
orchestrator 注入 pipeline_data）——与 HTML 端 partials/action_section.html 共享同一对象。
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _action_data(**extra) -> dict:
    """构造数据契约 action_data mock（含 1 条再平衡信号 + 收益归因）。"""
    d = {
        "available": True,
        "summary": "再平衡建议 1 条：组合内存在超警戒线品种，建议减持。",
        "rebalance_signals": [
            {"code": "SH600001", "name": "测试基金A", "weight": 0.25, "threshold": 0.15, "action": "减持"},
        ],
        "discipline_signals": [],
        "rebalance_advice": [],
        "attribution": {
            "available": True,
            "盈利来源": [{"name": "测试基金A", "contribution_pp": 12.3, "profit": 1000.0}],
            "亏损来源": [{"name": "测试基金B", "contribution_pp": -3.5, "profit": -200.0}],
            "summary": "盈利品种合计 +1,000.00，亏损品种合计 -200.00（净+800.00）",
        },
    }
    d.update(extra)
    return d


class _ExcelSheetAssertHelpers:
    """Excel 呈现测试共享断言助手（写页签 / 取全部文本 / 展平）。"""

    def _write(self, action_data, decision_review_data=None) -> "object":
        from openpyxl import Workbook

        from src.python.report.action_sheet import write_action_sheet

        wb = Workbook()
        ws = wb.active
        write_action_sheet(ws, action_data, decision_review_data=decision_review_data)
        return ws

    def _all_text(self, ws) -> list[list[str]]:
        return [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]

    def _flat(self, ws) -> list[str]:
        return [v for row in self._all_text(ws) for v in row]


class TestExcelActionSheet(_ExcelSheetAssertHelpers, unittest.TestCase):
    """行动建议页签 Excel 呈现测试。"""

    def test_full_rendering_when_available(self):
        """available=True → 标题 + 行动摘要 + 四个子块齐全。"""
        ws = self._write(_action_data())
        flat = self._flat(ws)
        self.assertTrue(any("行动建议" in v for v in flat), "应含行动建议标题")
        self.assertTrue(any("再平衡建议 1 条" in v for v in flat), "行动摘要行")
        self.assertTrue(any("再平衡信号" in v for v in flat), "子块 ① 应存在")
        self.assertTrue(any("交易纪律" in v for v in flat), "子块 ② 应存在")
        self.assertTrue(any("调仓建议清单" in v for v in flat), "子块 ③ 应存在")
        self.assertTrue(any("收益归因" in v for v in flat), "子块 ④ 应存在")

    def test_rebalance_signal_row(self):
        """再平衡信号行内容正确（代码/名称/占比/警戒线/建议动作）。"""
        ws = self._write(_action_data())
        flat = self._flat(ws)
        self.assertIn("SH600001", flat)
        self.assertIn("测试基金A", flat)
        self.assertIn("25.0%", flat)  # weight 0.25 → 25.0%
        self.assertIn("15%", flat)  # threshold 0.15 → 15%
        self.assertIn("减持", flat)

    def test_rebalance_advice_row(self):
        """调仓建议行内容正确（代码/名称/操作/份额/金额/费用/调仓后现金）。"""
        data = _action_data(
            rebalance_advice=[
                {
                    "code": "SH600000",
                    "name": "测试股票",
                    "operation": "止损",
                    "shares": 200,
                    "amount": 2000.0,
                    "fee": 6.0,
                    "cash_after": 1994.0,
                },
            ]
        )
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertIn("SH600000", flat)
        self.assertIn("测试股票", flat)
        self.assertIn("止损", flat)
        self.assertIn("200", flat)  # 份额
        self.assertIn("2000.0", flat)  # 金额
        self.assertIn("6.0", flat)  # 预估费用
        self.assertIn("1994.0", flat)  # 调仓后现金

    def test_empty_sub_blocks_placeholder(self):
        """无再平衡信号/纪律/调仓 → 各子块写占位文本（说明组合分散/无触发原因）。"""
        data = _action_data(rebalance_signals=[], discipline_signals=[], rebalance_advice=[], summary="")
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertIn("组合分散度良好，无品种超警戒线", flat)
        self.assertIn("暂无触发", flat)
        self.assertIn("无再平衡/纪律触发信号，暂无调仓建议", flat)

    def test_attribution_unavailable_placeholder(self):
        """收益归因 available=False / None → 「待生成」占位。"""
        data = _action_data(attribution={"available": False})
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertIn("待生成", flat)

    def test_attribution_render_when_available(self):
        """收益归因可用 → 盈利/亏损来源明细（贡献占比 +pp、盈亏金额 +,、净额合计摘要）。"""
        ws = self._write(_action_data())
        flat = self._flat(ws)
        self.assertIn("盈利来源", flat)
        self.assertIn("亏损来源", flat)
        self.assertIn("+12.3pp", flat)
        self.assertIn("-3.5pp", flat)
        self.assertIn("+1,000.00", flat)
        self.assertIn("-200.00", flat)
        self.assertTrue(any("净额合计" in v for v in flat), "净额合计摘要行")
        self.assertTrue(any("净+800.00" in v for v in flat), "净额合计摘要含净额")

    def test_unavailable_placeholder(self):
        """available=False（无持仓数据）→ 整页占位。"""
        data = _action_data(available=False)
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertIn("无持仓数据，行动建议无法生成", flat)
        self.assertNotIn("再平衡信号", flat)

    def test_none_placeholder(self):
        """action_data=None → 整页占位。"""
        ws = self._write(None)
        flat = self._flat(ws)
        self.assertIn("无持仓数据，行动建议无法生成", flat)


class TestExcelDecisionReviewBlock(_ExcelSheetAssertHelpers, unittest.TestCase):
    """行动页签内嵌「历史决策复盘」子块（decision_review_data）Excel 呈现测试。"""

    @staticmethod
    def _review_data(**extra) -> dict:
        """构造 decision_review_data 契约 mock（1 条 settled + 1 条 pending）。"""
        d = {
            "available": True,
            "disclaimer": "本复盘基于历史判断与真实行情的滞后对账，仅供反思参考，不构成任何投资建议。",
            "pending_count": 1,
            "settled_count": 1,
            "sample_sufficient": False,
            "direction_accuracy": None,
            "alpha_mean": None,
            "recent_pending": [
                {"code": "600519", "name": "贵州茅台", "direction": "看空（减仓/卖出建议）", "detail": "止盈线 +20%"},
            ],
            "recent_settled": [
                {
                    "code": "159915",
                    "name": "创业板ETF",
                    "direction": "看多（加仓建议）",
                    "outcome": "miss",
                    "raw_return": -0.03,
                    "settle_date": "2026-09-08",
                    "horizon_bars": 7,
                },
            ],
        }
        d.update(extra)
        return d

    @staticmethod
    def _contains(flat: list[str], text: str) -> bool:
        """单元格整体或单元格内含 text 均算命中（Excel 单元格常为长文案）。"""
        return any(text in v for v in flat)

    def test_no_review_block_without_data(self):
        """decision_review_data 缺省（None）→ 页签无⑤复盘子块（既有输出不变）。"""
        flat = self._flat(self._write(_action_data()))
        self.assertNotIn("历史决策复盘", flat)
        self.assertNotIn("待结算", flat)

    def test_settled_and_pending_rows(self):
        """复盘子块渲染 settled（结果列+区间涨跌）与 pending（待结算）行。"""
        flat = self._flat(self._write(_action_data(), self._review_data()))
        self.assertTrue(self._contains(flat, "历史决策复盘"), "应含复盘子块标题")
        self.assertTrue(self._contains(flat, "仅供反思参考"), "应含免责声明")
        self.assertIn("159915", flat)
        self.assertIn("未兑现", flat)  # outcome=miss
        self.assertIn("-3.0%", flat)  # raw_return -0.03 → -3.0%
        self.assertIn("600519", flat)
        self.assertIn("待结算", flat)
        # settled_count>0 且样本不足 → 计数提示行（不给命中率结论）
        self.assertTrue(self._contains(flat, "已结算 1 条"))
        self.assertFalse(self._contains(flat, "方向命中"))

    def test_accuracy_summary_when_sample_sufficient(self):
        """样本充足 → 命中率 + 超额均值摘要行。"""
        data = self._review_data(
            settled_count=21,
            sample_sufficient=True,
            direction_accuracy=0.6,
            alpha_mean=0.012,
        )
        flat = self._flat(self._write(_action_data(), data))
        self.assertTrue(self._contains(flat, "方向命中 60%"))
        self.assertTrue(self._contains(flat, "超额均值 +1.20%"))

    def test_pending_only_summary(self):
        """仅 pending（无 settled）→ 待结算计数提示行。"""
        data = self._review_data(settled_count=0, recent_settled=[])
        flat = self._flat(self._write(_action_data(), data))
        self.assertTrue(self._contains(flat, "待结算 1 条"))

    def test_review_block_in_unavailable_action(self):
        """action 数据不可用（available=False）→ 复盘子块仍渲染（历史账本独立于当日行动）。"""
        ws = self._write(_action_data(available=False), self._review_data())
        flat = self._flat(ws)
        self.assertIn("无持仓数据，行动建议无法生成", flat)
        self.assertTrue(self._contains(flat, "历史决策复盘"))
        self.assertIn("待结算", flat)


if __name__ == "__main__":
    unittest.main()
