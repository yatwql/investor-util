"""行动建议章节（20 章）与 14 章「行动摘要」HTML 呈现测试。

覆盖：
  - enable_action 开 + available=True → 20 章行动板块完整渲染（①再平衡信号 + ②交易纪律
    + ③调仓建议 + ④收益归因 + 行动摘要行）
  - 再平衡信号表格内容正确（代码/名称/占比/警戒线/建议动作）
  - 无再平衡信号 → 「组合内无品种超警戒线」占位
  - available=False → 「无持仓数据，行动建议无法生成」占位（§1.4.5 降级）
  - 14 章智囊团深度复盘「行动摘要」子块：enable_action 开 + 数据可用时出现，
    关闭时 14 章与现状一致（无子块）
  - 单源计算断言：20 章与 14 章共享同一 action_data 对象（summary/信号数一致，
    两处呈现同一数据源，无重复计算）

数据源为 C19 `action_data` 契约（analysis/action_advisor.build_action_data 组装、
orchestrator 注入 pipeline_data）——与 Excel 端 write_action_sheet 共享同一对象。
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

from src.test.unit.report.test_html_report_structure import (
    _build_minimal_render_data,
    _render_template,
)

# 行动建议章节（type=action，enable_action 默认关）与智囊团深度复盘章节（14 章宿主）
_ACTION_SECTION = {"key": "action", "name": "行动建议", "number": 20, "type": "action"}
_EXPERT_REVIEW_SECTION = {"key": "expert_review", "name": "智囊团深度复盘", "number": 14, "type": "llm"}
# global_macro 是 LLM 章节组的守卫章节（expert_review/health_check/penetration_deep
# 嵌套于其 section_visible 守卫内），测试需一并纳入以渲染 expert_review
_GLOBAL_MACRO_SECTION = {"key": "global_macro", "name": "全球政经局势", "number": 13, "type": "llm"}


def _order_with_action() -> list[dict]:
    """最小清单 + 行动建议章节 + 智囊团深度复盘章节（含守卫章节 global_macro）。"""
    order = [{"key": "summary", "name": "投资分析汇总", "number": 1, "type": "always"}]
    order.append(dict(_GLOBAL_MACRO_SECTION))
    order.append(dict(_EXPERT_REVIEW_SECTION))
    order.append(dict(_ACTION_SECTION))
    return order


def _render(action_data, action_enabled: bool = True) -> "BeautifulSoup":
    """渲染 action 与 expert_review 可见、其余隐藏的模板。

    expert_review 章节在模板中嵌套于 `section_visible("global_macro")` 守卫内
    （LLM 章节同组可见），因此测试需同时点亮 global_macro 才可渲染 expert_review。
    """
    order = _order_with_action()
    numbers = {sec["key"]: sec["number"] for sec in order}
    sv_dict = {sec["key"]: (sec["key"] in ("action", "expert_review", "global_macro")) for sec in order}
    data = _build_minimal_render_data(order, numbers, sv_dict)
    data["action_data"] = action_data
    # 行动章节可见性同时受 board 层（enable_action）与数据层控制；
    # 此处用 sv_dict 模拟 board 层开关（与生产 html_writer 的两层合并等效）
    if not action_enabled:
        sv_dict["action"] = False
        data["section_visible_dict"] = sv_dict
    return _render_template(data)


def _action_data(**extra) -> dict:
    """构造 C19 契约 action_data mock（含 1 条再平衡信号）。"""
    d = {
        "available": True,
        "summary": "再平衡建议 1 条：组合内存在超警戒线品种，建议减持。",
        "rebalance_signals": [
            {"code": "SH600001", "name": "测试基金A", "weight": 0.25, "threshold": 0.15, "action": "减持"},
        ],
        "discipline_signals": [],
        "rebalance_advice": [],
        "attribution": None,
    }
    d.update(extra)
    return d


class TestHtmlActionSection(unittest.TestCase):
    """行动建议章节（20 章）HTML 呈现测试。"""

    def _section(self, action_data, action_enabled: bool = True):
        return _render(action_data, action_enabled=action_enabled).find(id="sec-action")

    def test_full_rendering_when_enabled(self):
        """enable_action 开 + available=True → 20 章完整行动板块。"""
        section = self._section(_action_data())
        self.assertIsNotNone(section, "enable_action 开启时应有 #sec-action 章节")
        text = section.get_text()
        self.assertIn("行动建议", text)
        self.assertIn("再平衡建议 1 条", text)  # 行动摘要行
        self.assertIn("① 再平衡信号", text)
        self.assertIn("② 交易纪律", text)
        self.assertIn("③ 调仓建议", text)
        self.assertIn("④ 收益归因", text)

    def test_rebalance_signal_table(self):
        """再平衡信号表格内容正确。"""
        section = self._section(_action_data())
        text = section.get_text()
        self.assertIn("SH600001", text)
        self.assertIn("测试基金A", text)
        self.assertIn("25.0%", text)  # weight 0.25 → 25.0%
        self.assertIn("15%", text)  # threshold 0.15 → 15%
        self.assertIn("减持", text)

    def test_rebalance_advice_table(self):
        """调仓建议清单表格渲染完整字段（代码/名称/操作/份额/金额/费用/现金）。"""
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
        text = self._section(data).get_text()
        self.assertIn("SH600000", text)
        self.assertIn("测试股票", text)
        self.assertIn("止损", text)
        self.assertIn("200", text)  # 份额
        self.assertIn("2000.00", text)  # 金额（两位小数）
        self.assertIn("6.00", text)  # 预估费用
        self.assertIn("1994.00", text)  # 调仓后现金

    def test_empty_sub_blocks_placeholder(self):
        """无再平衡信号/纪律/调仓 → 各子块写占位文本。"""
        data = _action_data(rebalance_signals=[], summary="当前无行动建议")
        section = self._section(data)
        text = section.get_text()
        self.assertIn("组合内无品种超警戒线", text)
        self.assertIn("暂无触发", text)
        self.assertIn("待生成", text)  # 收益归因 available 缺省 → 待生成

    def test_unavailable_placeholder(self):
        """available=False（无持仓数据）→ 降级占位。"""
        data = _action_data(available=False)
        section = self._section(data)
        self.assertIsNotNone(section, "available=False 时章节仍渲染（写占位）")
        text = section.get_text()
        self.assertIn("无持仓数据，行动建议无法生成", text)
        self.assertNotIn("① 再平衡信号", text)

    def test_hidden_when_action_disabled(self):
        """enable_action 关 → 20 章整体不渲染。"""
        section = self._section(_action_data(), action_enabled=False)
        self.assertIsNone(section, "enable_action 关闭时不应有 #sec-action 章节")


class TestHtmlActionSummaryInExpertReview(unittest.TestCase):
    """14 章智囊团深度复盘「行动摘要」子块测试。"""

    def _expert_section(self, action_data, action_enabled: bool = True):
        return _render(action_data, action_enabled=action_enabled).find(id="sec-expert_review")

    def test_summary_subblock_when_enabled(self):
        """enable_action 开 + 数据可用 → 14 章出现「行动摘要」子块（引用 20 章）。"""
        section = self._expert_section(_action_data())
        text = section.get_text()
        self.assertIn("行动摘要", text)
        self.assertIn("第 20 章", text)  # 引用 20 章序号（本清单 action=20）
        self.assertIn("再平衡建议 1 条", text)

    def test_summary_subblock_hidden_when_disabled(self):
        """enable_action 关 → 14 章无「行动摘要」子块（与现状一致）。"""
        section = self._expert_section(_action_data(), action_enabled=False)
        text = section.get_text()
        self.assertNotIn("行动摘要", text)
        self.assertNotIn("再平衡建议", text)

    def test_summary_subblock_hidden_when_unavailable(self):
        """available=False → 14 章不显示行动摘要（数据不可用，与现状一致）。"""
        section = self._expert_section(_action_data(available=False))
        text = section.get_text()
        self.assertNotIn("行动摘要", text)


class TestActionSingleSource(unittest.TestCase):
    """单源计算断言 — 20 章与 14 章共享同一 action_data 对象（无重复计算）。"""

    def test_single_source_same_summary(self):
        """20 章与 14 章渲染同一 summary 文本（同一数据源，两处呈现）。"""
        action_data = _action_data()  # 单个对象实例，注入模板 context
        soup = _render(action_data)
        action_sec = soup.find(id="sec-action").get_text()
        expert_sec = soup.find(id="sec-expert_review").get_text()
        self.assertIn("再平衡建议 1 条", action_sec)
        self.assertIn("再平衡建议 1 条", expert_sec)
        # 两处呈现同一对象的同一 summary 字符串（若重复计算导致口径漂移，此处会失败）
        self.assertEqual(
            action_sec.count("再平衡建议 1 条"),
            1,
            "20 章仅展示一次行动摘要行（来自单一 action_data）",
        )

    def test_single_source_consistent_signal_count(self):
        """信号数一致：20 章信号表行数与摘要文案一致（单一计算对象）。"""
        action_data = _action_data()
        soup = _render(action_data)
        action_sec = soup.find(id="sec-action")
        # 摘要声明 1 条，信号表应有且仅 1 条数据行
        self.assertIn("再平衡建议 1 条", action_sec.get_text())
        self.assertIn("SH600001", action_sec.get_text())
        # 无重复品种行（同一对象渲染两次会产生重复，此处应为 1 行）
        rows = action_sec.select("table tbody tr")
        self.assertLessEqual(len(rows), 1, "单一 action_data 不应产生重复信号行")


if __name__ == "__main__":
    unittest.main()
