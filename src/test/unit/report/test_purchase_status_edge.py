"""申购限购状态展示层边缘场景（0 元限额 / 时间不可解析 / 过期档）。

普通路径见 test_purchase_status.py。设计文档 §7 载体纪律：
0 元限额等异常样本用例属 edge 场景，标 `@pytest.mark.edge` 并置于 `*_edge.py`。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.python.core.constants import BEIJING_TZ
from src.python.report import purchase_status as ps

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_report,
    pytest.mark.edge,
    pytest.mark.usefixtures("offline_external_sources"),
]


def _contract(rows: dict, fetched_at: str | None = None) -> dict:
    return {
        "available": True,
        "reason": None,
        "rows": rows,
        "fetched_at": fetched_at or datetime.now(BEIJING_TZ).isoformat(),
        "source": "天天基金",
    }


class TestLimitEdgeCases:
    """限额缺失态（0 元限额在解析层已单点转 None，展示层沿用不重判）。"""

    @pytest.mark.edge
    def test_zero_limit_shows_unknown_limit(self):
        """0 元/缺失日限额 → 「限额未知」，绝不显示「日限 0 元」（风险 R4 回归）。"""
        rows = {
            "000216": {
                "purchase_status": "限大额",
                "redemption_status": "开放赎回",
                "next_open_date": "",
                "daily_limit": None,
                "min_purchase": 10.0,
            }
        }
        assert ps.format_purchase_status_cell(_contract(rows), "000216", "fresh") == "🟡 限大额 限额未知"

    @pytest.mark.edge
    def test_zero_limit_excel_cell_shows_unknown_limit(self):
        """Excel 端同一文案函数（0 元限额 → 限额未知端到端）。"""
        from openpyxl import Workbook

        from src.python.core.models import Holding
        from src.python.report.holdings_detail_sheet import DetailRow, write_holdings_detail_sheet

        detail = DetailRow(
            account="证券账户",
            name="测试基金",
            code="000216",
            price=1.0,
            nav_date="2026-10-09",
            yesterday_close=1.0,
            price_type="净值",
            premium="--",
            shares=100.0,
            market_value=100.0,
            cost=100.0,
            profit=0.0,
            profit_rate=0.0,
            today_profit=0.0,
            source="mock",
            source_api="mock",
        )
        rows = {
            "000216": {
                "purchase_status": "限大额",
                "redemption_status": "开放赎回",
                "next_open_date": "",
                "daily_limit": None,
                "min_purchase": 10.0,
            }
        }
        wb = Workbook()
        ws = wb.active
        holding = Holding(account="证券账户", name="测试基金", code="000216", shares=100, cost_price=1.0)
        write_holdings_detail_sheet(ws, [holding], [detail], None, _contract(rows))
        # 区块①表头第 16 列为「申购状态」（行1=页签标题，行2=区块①标题，行3=表头，行4=明细）
        assert ws.cell(row=3, column=16).value == "申购状态"
        assert ws.cell(row=4, column=16).value == "🟡 限大额 限额未知"


class TestTimestampEdgeCases:
    """抓取时间异常 / 过期档。"""

    @pytest.mark.edge
    def test_unparseable_fetched_at_is_expired(self):
        """fetched_at 不可解析 → expired（无法判定时效即不展示）。"""
        assert ps.stale_level("not-a-timestamp") == "expired"

    @pytest.mark.edge
    def test_invalid_today_param_is_expired(self):
        """基准日非法 → expired（宁可隐列不可误判新鲜）。"""
        assert ps.stale_level("2026-10-06", today="bad-date") == "expired"

    @pytest.mark.edge
    def test_expired_footnote_and_cells_both_degrade(self, monkeypatch):
        """过期档：脚注解释隐去原因，单元格全部「—」。"""
        data = _contract(
            {
                "600900": {
                    "purchase_status": "开放申购",
                    "redemption_status": "开放赎回",
                    "next_open_date": "",
                    "daily_limit": None,
                    "min_purchase": 10.0,
                }
            },
            fetched_at="2026-09-01T08:00:00+08:00",
        )
        # 档位 → 文案分支：档位阶梯本身由 TestStaleLadder 按显式基准日覆盖
        monkeypatch.setattr(ps, "stale_level", lambda *_args, **_kw: "expired")
        assert ps.format_purchase_status_cell(data, "600900") == "—"
        assert "宁缺毋错" in ps.purchase_status_footnote(data)
