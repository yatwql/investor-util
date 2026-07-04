"""智能预警测试 — 行业资金流向联动 + 新闻情绪聚合。"""

from __future__ import annotations

from unittest.mock import patch



from src.python.report.early_warning import (
    _compute_sector_alerts,
    _compute_sentiment_alerts,
    _fmt_money,
    compute_early_warnings,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class FakeHolding:
    """模拟 Holding 对象（仅提供所需属性）。"""
    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name


class TestComputeEarlyWarnings:
    """集成测试：compute_early_warnings 整体功能。"""

    def test_all_data_present(self):
        """正常数据应产生预警结果。"""
        holdings = [FakeHolding("600519", "贵州茅台"), FakeHolding("300750", "宁德时代")]
        pen_top10 = [
            {"name": "贵州茅台", "codes": ["600519"], "mv": 50000, "ratio_pct": 15,
             "sector": "消费", "concepts": ["白酒"]},
            {"name": "宁德时代", "codes": ["300750"], "mv": 30000, "ratio_pct": 10,
             "sector": "新能源", "concepts": ["电池"]},
        ]
        sector_flow = [
            {"name": "电池", "main_net_inflow": -500_000_000, "main_net_inflow_pct": -5.21,
             "change_pct": -2.35, "top_stock": "宁德时代"},
            {"name": "证券", "main_net_inflow": 100_000_000, "main_net_inflow_pct": 2.0,
             "change_pct": 1.5, "top_stock": "中信证券"},
        ]
        news_data = [
            {"title": "茅台利好", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "利好", "analysis": ""}},
        ]
        meta = {"llm_enabled": True}

        result = compute_early_warnings(holdings, pen_top10, sector_flow, news_data, meta)
        assert result["has_warnings"] is True
        assert len(result["sector_alerts"]) == 1  # 电池（净流出），证券被过滤
        assert result["sector_alerts"][0]["sector_name"] == "电池"
        assert result["sector_alerts"][0]["alert_level"] == "danger"
        assert len(result["sentiment_alerts"]) == 1
        assert result["sentiment_alerts"][0]["code"] == "600519"

    def test_no_sector_data(self):
        """无行业资金流向数据应返回空预警。"""
        holdings = [FakeHolding("600519", "贵州茅台")]
        pen_top10 = [{"name": "贵州茅台", "codes": ["600519"], "concepts": ["白酒"]}]
        result = compute_early_warnings(holdings, pen_top10, sector_flow=None)
        assert result["sector_alerts"] == []
        assert result["has_sector_data"] is False

    def test_no_penetration_data(self):
        """无穿透数据应返回空预警。"""
        holdings = [FakeHolding("600519", "贵州茅台")]
        sector_flow = [{"name": "电池", "main_net_inflow": -100_000_000}]
        result = compute_early_warnings(holdings, sector_flow=sector_flow)
        assert result["sector_alerts"] == []

    def test_no_llm_news(self):
        """LLM 未启用应返回空情绪聚合。"""
        holdings = [FakeHolding("600519", "贵州茅台")]
        news_data = [{"title": "test", "matched_keywords": ["600519"]}]
        meta = {"llm_enabled": False}
        result = compute_early_warnings(holdings, news_data=news_data, news_llm_meta=meta)
        assert result["sentiment_alerts"] == []
        assert result["has_llm_news"] is False

    def test_all_positive_inflow_no_warning(self):
        """所有行业净流入不应产生预警。"""
        holdings = [FakeHolding("300750", "宁德时代")]
        pen_top10 = [{"name": "宁德时代", "codes": ["300750"], "concepts": ["电池"]}]
        sector_flow = [{"name": "电池", "main_net_inflow": 500_000_000}]
        result = compute_early_warnings(holdings, pen_top10, sector_flow)
        assert result["sector_alerts"] == []
        assert result["has_warnings"] is False

    def test_no_news_data(self):
        """无新闻数据应返回空情绪聚合。"""
        holdings = [FakeHolding("600519", "贵州茅台")]
        meta = {"llm_enabled": True}
        result = compute_early_warnings(holdings, news_llm_meta=meta)
        assert result["sentiment_alerts"] == []


class TestSectorAlerts:
    """行业资金流向联动预警单元测试。"""

    def test_alert_level_danger(self):
        """巨量净流出应标记为 danger。"""
        pen = [{"name": "A", "codes": ["1"], "concepts": ["电池"]}]
        flow = [{"name": "电池", "main_net_inflow": -500_000_000}]
        alerts = _compute_sector_alerts(pen, flow)
        assert len(alerts) == 1
        assert alerts[0]["alert_level"] == "danger"

    def test_alert_level_warning(self):
        """中等净流出应标记为 warning。"""
        pen = [{"name": "A", "codes": ["1"], "concepts": ["白酒"]}]
        flow = [{"name": "白酒", "main_net_inflow": -100_000_000}]
        alerts = _compute_sector_alerts(pen, flow)
        assert len(alerts) == 1
        assert alerts[0]["alert_level"] == "warning"

    def test_alert_level_info(self):
        """小额净流出应标记为 info。"""
        pen = [{"name": "A", "codes": ["1"], "concepts": ["白酒"]}]
        flow = [{"name": "白酒", "main_net_inflow": -10_000_000}]
        alerts = _compute_sector_alerts(pen, flow)
        assert len(alerts) == 1
        assert alerts[0]["alert_level"] == "info"

    def test_concept_not_matched(self):
        """无概念匹配不产生预警。"""
        pen = [{"name": "茅台", "codes": ["600519"], "concepts": ["白酒"]}]
        flow = [{"name": "电池", "main_net_inflow": -500_000_000}]
        alerts = _compute_sector_alerts(pen, flow)
        assert alerts == []

    def test_empty_inputs(self):
        """None 或空输入返回空列表。"""
        assert _compute_sector_alerts(None, [{"name": "a", "main_net_inflow": -1}]) == []
        assert _compute_sector_alerts([{"name": "a", "concepts": ["x"]}], None) == []
        assert _compute_sector_alerts([], []) == []

    def test_sorted_by_outflow(self):
        """预警应按净流出金额降序（最危险在前）。"""
        pen = [{"name": "A", "codes": ["1"], "concepts": ["电池", "白酒"]}]
        flow = [
            {"name": "白酒", "main_net_inflow": -10_000_000},
            {"name": "电池", "main_net_inflow": -500_000_000},
        ]
        alerts = _compute_sector_alerts(pen, flow)
        assert alerts[0]["sector_name"] == "电池"  # 净流出更大
        assert alerts[1]["sector_name"] == "白酒"


class TestSentimentAlerts:
    """新闻情绪聚合单元测试。"""

    def test_basic_aggregation(self):
        """多条新闻应按持仓代码正确聚合。"""
        holdings = [FakeHolding("600519", "贵州茅台"), FakeHolding("300750", "宁德时代")]
        news = [
            {"title": "n1", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "利好"}},
            {"title": "n2", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "利空"}},
            {"title": "n3", "matched_keywords": ["300750"],
             "llm_analysis": {"relevance": "高", "sentiment": "利空"}},
        ]
        meta = {"llm_enabled": True}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert len(alerts) == 2

        moutai = next(a for a in alerts if a["code"] == "600519")
        assert moutai["name"] == "贵州茅台"
        assert moutai["total_mentions"] == 2
        assert moutai["positive"] == 1
        assert moutai["negative"] == 1
        assert moutai["neutral"] == 0
        assert moutai["sentiment_score"] == 0.0  # (1-1)/2

    def test_filter_low_relevance(self):
        """低关联度或无关的新闻应被过滤。"""
        holdings = [FakeHolding("600519", "茅台")]
        news = [
            {"title": "n1", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "低", "sentiment": "利空"}},
            {"title": "n2", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "无关", "sentiment": "中性"}},
        ]
        meta = {"llm_enabled": True}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert alerts == []

    def test_llm_disabled(self):
        """LLM 未启用应返回空。"""
        holdings = [FakeHolding("600519", "茅台")]
        news = [{"title": "n1", "matched_keywords": ["600519"],
                 "llm_analysis": {"relevance": "高", "sentiment": "利好"}}]
        meta = {"llm_enabled": False}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert alerts == []

    def test_no_llm_analysis_field(self):
        """无 llm_analysis 字段的新闻应被忽略。"""
        holdings = [FakeHolding("600519", "茅台")]
        news = [{"title": "n1", "matched_keywords": ["600519"]}]
        meta = {"llm_enabled": True}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert alerts == []

    def test_sentiment_label(self):
        """情绪标签应与得分一致。"""
        holdings = [FakeHolding("600519", "贵州茅台")]
        news = [
            {"title": "n1", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "利好"}},
            {"title": "n2", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "利好"}},
            {"title": "n3", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "中性"}},
        ]
        meta = {"llm_enabled": True}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert alerts[0]["sentiment_score"] >= 0.3  # (2-0)/3 = 0.67
        assert alerts[0]["sentiment_label"] == "偏利好"

    def test_holdings_without_code(self):
        """持仓无代码不崩溃。"""
        holdings = [FakeHolding("", "无代码")]
        news = [{"title": "n1", "matched_keywords": ["无代码"],
                 "llm_analysis": {"relevance": "高", "sentiment": "利好"}}]
        meta = {"llm_enabled": True}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert alerts == []

    def test_top_stories_limit(self):
        """最多保留前 3 条要闻。"""
        holdings = [FakeHolding("600519", "茅台")]
        news = [
            {"title": f"新闻{i}", "matched_keywords": ["600519"],
             "llm_analysis": {"relevance": "高", "sentiment": "利好"}}
            for i in range(5)
        ]
        meta = {"llm_enabled": True}
        alerts = _compute_sentiment_alerts(holdings, news, meta)
        assert len(alerts[0]["top_stories"]) <= 3


class TestFmtMoney:
    """金额格式化测试。"""

    def test_yi(self):
        assert _fmt_money(-500_000_000) == "-5.00亿"

    def test_wan(self):
        assert _fmt_money(30_000) == "3.00万"

    def test_small(self):
        assert _fmt_money(999) == "999"

    def test_zero(self):
        assert _fmt_money(0) == "0"


class TestWriteEarlyWarningSheet:
    """Excel 写入测试（mock openpyxl）。"""

    def test_write_with_data(self):
        """正常数据下写入不抛出异常。"""
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        from src.python.report.early_warning import write_early_warning_sheet

        early_warnings = {
            "sector_alerts": [
                {"sector_name": "电池", "main_net_inflow": -500_000_000,
                 "main_net_inflow_pct": -5.21, "change_pct": -2.35, "top_stock": "宁德时代",
                 "matched_assets": [{"name": "宁德时代", "codes": ["300750"]}],
                 "alert_level": "danger"},
            ],
            "sentiment_alerts": [
                {"code": "600519", "name": "贵州茅台", "total_mentions": 3,
                 "positive": 2, "negative": 1, "neutral": 0,
                 "sentiment_score": 0.33, "sentiment_label": "偏利好", "top_stories": []},
            ],
            "has_warnings": True,
            "has_sector_data": True,
            "has_llm_news": True,
        }
        write_early_warning_sheet(ws, early_warnings)
        assert ws.title == "11.智能预警"

    def test_write_empty(self):
        """无数据写入不抛出异常。"""
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        from src.python.report.early_warning import write_early_warning_sheet


        write_early_warning_sheet(ws, {
            "sector_alerts": [], "sentiment_alerts": [],
            "has_warnings": False, "has_sector_data": False, "has_llm_news": False,
        })
        assert ws.title == "11.智能预警"
