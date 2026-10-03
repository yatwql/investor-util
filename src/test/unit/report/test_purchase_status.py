"""申购限购状态展示层测试 — 数据契约 / 陈旧阶梯 / 单元格文案 / 口径脚注 / 渲染上下文。

对应设计文档 docs/plan/fund-purchase-limit-design.md §4.4 单源清单与 §5 展示规则：

  - 陈旧阶梯三档（≤3 / 4~7 / >7 交易日，按交易日历计，长假不计入）
  - 单元格文案与口径脚注为 Excel/HTML 唯一实现（单源，不发散）
  - 契约装配三态：开关关 → None；取数失败 → available=False（静默隐列）；成功 → available=True
  - 渲染层列可见性判据统一（purchase_column_visible）

网络：fetcher 层全部 mock，套件全程无网。
异常样本（0 元限额、时间不可解析等）见 test_purchase_status_edge.py。
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.python.core.constants import BEIJING_TZ
from src.python.report import purchase_status as ps

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── 测试数据 ──────────────────────────────────────────────────


def _fresh_ts() -> str:
    """当前北京时区时间（距今 0 交易日 → fresh 档）。"""
    return datetime.now(BEIJING_TZ).isoformat()


def _rows() -> dict:
    """四类代表状态行（与真实源字段同构）。"""
    return {
        "600900": {
            "purchase_status": "开放申购",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": None,
            "min_purchase": 10.0,
        },
        "110022": {
            "purchase_status": "限大额",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": 100.0,
            "min_purchase": 10.0,
        },
        "000198": {
            "purchase_status": "限大额",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": 10000.0,
            "min_purchase": 10.0,
        },
        "161725": {
            "purchase_status": "暂停申购",
            "redemption_status": "暂停赎回",
            "next_open_date": "2026-10-09",
            "daily_limit": None,
            "min_purchase": 10.0,
        },
        "161005": {
            "purchase_status": "暂停申购",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": None,
            "min_purchase": 10.0,
        },
        "512880": {
            "purchase_status": "场内交易",
            "redemption_status": "开放赎回",
            "next_open_date": "",
            "daily_limit": None,
            "min_purchase": 10.0,
        },
    }


def _contract(rows: dict | None = None, available: bool = True, fetched_at: str | None = None) -> dict:
    return {
        "available": available,
        "reason": None if available else "全链路失败",
        "rows": _rows() if rows is None else rows,
        "fetched_at": _fresh_ts() if fetched_at is None else fetched_at,
        "source": "天天基金",
    }


# ════════════════════════════════════════════════════════════
#  陈旧阶梯（stale_level，按交易日历计）
# ════════════════════════════════════════════════════════════


class TestStaleLadder:
    """≤3 / 4~7 / >7 交易日三档分支（含长假不计陈旧）。"""

    @pytest.fixture(autouse=True)
    def _fallback_calendar(self, monkeypatch):
        """默认用「仅排除周末」回退口径，保证用例日期可复算。

        长假用例单独注入假日日历（见 test_long_holiday_not_counted）。
        """
        monkeypatch.setattr("src.python.core.trading_calendar._get_trading_calendar", lambda: None)

    def test_fresh_within_three_trading_days(self):
        """距抓取 ≤3 个交易日 → fresh（正常展示）。"""
        assert ps.stale_level("2026-10-06", today="2026-10-09") == "fresh"

    def test_stale_four_to_seven_trading_days(self):
        """距抓取 4~7 个交易日 → stale（展示 + 数据陈旧标）。"""
        assert ps.stale_level("2026-10-01", today="2026-10-09") == "stale"

    def test_expired_beyond_seven_trading_days(self):
        """距抓取 >7 个交易日 → expired（显示「—」，宁缺毋错）。"""
        assert ps.stale_level("2026-09-25", today="2026-10-09") == "expired"

    def test_long_holiday_not_counted(self, monkeypatch):
        """长假不计陈旧：按交易日历精确计数（国庆前后自然日跨度大但交易日仅 1）。"""
        monkeypatch.setattr(
            "src.python.core.trading_calendar._get_trading_calendar",
            lambda: {"2026-10-09"},
        )
        assert ps.stale_level("2026-09-28", today="2026-10-09") == "fresh"

    def test_missing_fetched_at_expired(self):
        """无抓取时间 → expired（不展示无法判定时效的数据）。"""
        assert ps.stale_level(None) == "expired"


# ════════════════════════════════════════════════════════════
#  单元格文案（format_purchase_status_cell，Excel/HTML 单源）
# ════════════════════════════════════════════════════════════


class TestFormatCell:
    """各真实状态 → 单元格文案；失效态一律「—」。"""

    def test_open_purchase(self):
        assert ps.format_purchase_status_cell(_contract(), "600900", "fresh") == "🟢 开放"

    def test_limited_with_daily_limit(self):
        assert ps.format_purchase_status_cell(_contract(), "110022", "fresh") == "🟡 限大额 日限 100 元"

    def test_limited_daily_limit_thousands(self):
        assert ps.format_purchase_status_cell(_contract(), "000198", "fresh") == "🟡 限大额 日限 10,000 元"

    def test_suspended_with_next_open_date(self):
        assert ps.format_purchase_status_cell(_contract(), "161725", "fresh") == "🔴 暂停 10月9日 开放"

    def test_suspended_without_next_open_date(self):
        assert ps.format_purchase_status_cell(_contract(), "161005", "fresh") == "🔴 暂停"

    def test_venue_trading_shows_dash(self):
        """场内交易无申购语义 → 「—」。"""
        assert ps.format_purchase_status_cell(_contract(), "512880", "fresh") == "—"

    def test_unknown_code_shows_dash(self):
        """查无此码（场内份额/新基金）→ 「—」，绝不默认开放申购。"""
        assert ps.format_purchase_status_cell(_contract(), "999999", "fresh") == "—"

    def test_stale_level_still_renders(self):
        """4~7 交易日档仍展示状态（陈旧标由脚注承载）。"""
        assert ps.format_purchase_status_cell(_contract(), "600900", "stale") == "🟢 开放"

    def test_expired_level_shows_dash(self):
        """>7 交易日 → 一律「—」（过时的限购信息比缺失更误导）。"""
        assert ps.format_purchase_status_cell(_contract(), "600900", "expired") == "—"

    def test_unavailable_contract_shows_dash(self):
        """available=False（全链失败）→ 全部「—」。"""
        data = _contract(available=False)
        assert ps.format_purchase_status_cell(data, "600900", "fresh") == "—"

    def test_switch_off_contract_none_shows_dash(self):
        """契约缺席（开关关）→ 全部「—」。"""
        assert ps.format_purchase_status_cell(None, "600900", "fresh") == "—"

    def test_level_derived_from_fetched_at_when_not_given(self):
        """未显式给档位时按 fetched_at 自行推档（fresh 现值 → 正常展示）。"""
        assert ps.format_purchase_status_cell(_contract(), "600900") == "🟢 开放"


# ════════════════════════════════════════════════════════════
#  口径脚注（purchase_status_footnote，Excel/HTML 同源文案）
# ════════════════════════════════════════════════════════════


class TestFootnote:
    @pytest.fixture(autouse=True)
    def _pin_level(self, monkeypatch):
        """钉住档位分支：陈旧阶梯本身由 TestStaleLadder 覆盖，
        此处只验证脚注对三档的文案分支（避免依赖真实时钟）。"""
        monkeypatch.setattr(ps, "stale_level", lambda *_args, **_kw: "fresh")

    def test_fresh_footnote_contains_channel_caveat_and_fetch_date(self):
        """fresh 档：固定渠道口径文案 + 抓取日期（设计 §5.3 / §5.4 ≤3 档）。"""
        text = ps.purchase_status_footnote(_contract(fetched_at="2026-10-09T08:00:00+08:00"))
        assert ps.PURCHASE_STATUS_FOOTNOTE in text
        assert "数据抓取于 2026-10-09" in text

    def test_stale_footnote_marks_stale(self, monkeypatch):
        """stale 档：⚠ 数据陈旧标 + 抓取日期。"""
        monkeypatch.setattr(ps, "stale_level", lambda *_args, **_kw: "stale")
        text = ps.purchase_status_footnote(_contract(fetched_at="2026-10-01T08:00:00+08:00"))
        assert ps.PURCHASE_STATUS_FOOTNOTE in text
        assert "⚠ 数据陈旧（2026-10-01 抓取）" in text

    def test_expired_footnote_explains_hidden_state(self, monkeypatch):
        """expired 档：说明已隐去 + 宁缺毋错，仍附渠道口径。"""
        monkeypatch.setattr(ps, "stale_level", lambda *_args, **_kw: "expired")
        text = ps.purchase_status_footnote(_contract(fetched_at="2026-09-01T08:00:00+08:00"))
        assert ps.PURCHASE_STATUS_FOOTNOTE in text
        assert "宁缺毋错" in text

    def test_unavailable_contract_returns_base_text_only(self):
        """契约不可用（列不渲染时的兜底）→ 仅基础口径文案。"""
        assert ps.purchase_status_footnote(None) == ps.PURCHASE_STATUS_FOOTNOTE
        assert ps.purchase_status_footnote(_contract(available=False)) == ps.PURCHASE_STATUS_FOOTNOTE


# ════════════════════════════════════════════════════════════
#  数据契约装配（build_purchase_status_data）
# ════════════════════════════════════════════════════════════


class TestContractBuilder:
    def test_switch_off_returns_none_without_fetching(self, monkeypatch):
        """开关 `fund_purchase_limit` 关闭 → None 且不触碰取数（保持既有输出）。"""
        from src.python.config.features import set_feature_enabled

        def _boom():
            raise AssertionError("开关关闭时不得取数")

        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", _boom)
        set_feature_enabled("fund_purchase_limit", False)
        assert ps.build_purchase_status_data({}) is None

    def test_fetch_success_builds_available_contract(self, monkeypatch):
        """取数成功 → available=True 契约（rows/fetched_at/source 透传）。"""
        payload = {
            "rows": _rows(),
            "fetched_at": "2026-10-09T08:00:00+08:00",
            "purchase_schema": "1",
            "source": "天天基金",
        }
        monkeypatch.setattr(
            "src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached",
            lambda: payload,
        )
        data = ps.build_purchase_status_data({})
        assert data["available"] is True
        assert data["rows"] == _rows()
        assert data["fetched_at"] == "2026-10-09T08:00:00+08:00"
        assert data["source"] == "天天基金"

    def test_fetch_failure_builds_degraded_contract(self, monkeypatch):
        """全链失败（None）→ available=False 降级契约（静默隐列、不抛异常）。"""
        monkeypatch.setattr(
            "src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached",
            lambda: None,
        )
        data = ps.build_purchase_status_data({})
        assert data["available"] is False
        assert data["rows"] == {}
        assert data["fetched_at"] is None
        assert data["reason"]

    def test_fetch_exception_builds_degraded_contract(self, monkeypatch):
        """取数层抛 Exception → available=False（四层降级末层，绝不阻断报告主链路）。"""

        def _boom():
            raise RuntimeError("传输层意外异常")

        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", _boom)
        data = ps.build_purchase_status_data({})
        assert data["available"] is False
        assert data["rows"] == {}


# ════════════════════════════════════════════════════════════
#  列可见性与行查询（渲染层判据）
# ════════════════════════════════════════════════════════════


class TestVisibility:
    def test_column_visible_only_when_available(self):
        assert ps.purchase_column_visible(_contract()) is True
        assert ps.purchase_column_visible(_contract(available=False)) is False
        assert ps.purchase_column_visible(None) is False

    def test_get_purchase_status_row(self):
        row = ps.get_purchase_status(_contract(), "110022")
        assert row is not None
        assert row["purchase_status"] == "限大额"

    def test_get_purchase_status_returns_none_for_unavailable(self):
        assert ps.get_purchase_status(_contract(available=False), "110022") is None
        assert ps.get_purchase_status(None, "110022") is None
        assert ps.get_purchase_status(_contract(), "999999") is None


# ════════════════════════════════════════════════════════════
#  HTML 渲染上下文装配（_build_purchase_status_display）
# ════════════════════════════════════════════════════════════


class TestHtmlDisplayBuilder:
    def _accounts(self):
        return {
            "证券账户": [SimpleNamespace(code="600900"), SimpleNamespace(code="110022")],
            "基金账户": [SimpleNamespace(code="999999")],
        }

    def test_build_cells_footnote_and_level(self):
        from src.python.report.html_writer_display import _build_purchase_status_display

        data = _contract()
        display = _build_purchase_status_display(data, self._accounts())
        assert display is not None
        # 每个持仓代码都有单元格（查无此码 → 「—」）
        assert display["cells"]["600900"] == "🟢 开放"
        assert display["cells"]["110022"] == "🟡 限大额 日限 100 元"
        assert display["cells"]["999999"] == "—"
        assert display["level"] == "fresh"
        assert display["footnote"] == ps.purchase_status_footnote(data)

    def test_unavailable_returns_none_column_hidden(self):
        from src.python.report.html_writer_display import _build_purchase_status_display

        assert _build_purchase_status_display(_contract(available=False), self._accounts()) is None
        assert _build_purchase_status_display(None, self._accounts()) is None

    def test_no_accounts_returns_none(self):
        from src.python.report.html_writer_display import _build_purchase_status_display

        assert _build_purchase_status_display(_contract(), {}) is None
        assert _build_purchase_status_display(_contract(), None) is None

    def test_dict_form_details_supported(self):
        """明细行既支持属性对象也支持 dict（两端渲染上下文同构）。"""
        from src.python.report.html_writer_display import _build_purchase_status_display

        accounts = {"证券账户": [{"code": "600900"}]}
        display = _build_purchase_status_display(_contract(), accounts)
        assert display["cells"]["600900"] == "🟢 开放"


# ════════════════════════════════════════════════════════════
#  模板条件渲染（report_template.html 持仓市值明细区块）
# ════════════════════════════════════════════════════════════


class TestPurchaseStatusTemplate:
    """真实模板片段在 purchase_status_display 开/关下的渲染结果。"""

    def setup_method(self):
        from jinja2 import Environment

        from src.python.report.html_jinja_env import (
            _jinja_money,
            _jinja_pct,
            _jinja_price,
            _jinja_profit_color,
        )

        self.env = Environment(autoescape=True)
        self.env.filters.update(
            {
                "money": _jinja_money,
                "pct": _jinja_pct,
                "price": _jinja_price,
                "profit_color": _jinja_profit_color,
            }
        )
        tmpl_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "tmpl", "report_template.html")
        )
        with open(tmpl_path, encoding="utf-8") as f:
            self.html = f.read()

    def _extract_balanced_from(self, start: int) -> str:
        """按 if/endif 配平从 start 起截取一段（含起点标记本身）。"""
        depth = 0
        pos = start
        while True:
            nxt_if = self.html.find("{% if", pos)
            nxt_endif = self.html.find("{% endif %}", pos)
            assert nxt_endif != -1, "模板中该区块未闭合（if/endif 不配平）"
            if nxt_if != -1 and nxt_if < nxt_endif:
                depth += 1
                pos = nxt_if + len("{% if")
            else:
                depth -= 1
                pos = nxt_endif + len("{% endif %}")
                if depth == 0:
                    return self.html[start:pos]

    def _extract(self, start_marker: str) -> str:
        start = self.html.find(start_marker)
        assert start != -1, f"模板中未找到起点: {start_marker}"
        return self._extract_balanced_from(start)

    def _render(self, fragment: str, **ctx):
        return self.env.from_string(fragment).render(**ctx)

    def test_header_hidden_when_display_none(self):
        """purchase_status_display=None → 无「申购状态」表头列（开关关/取数失败）。"""
        frag = self._extract("{% if purchase_status_display %}<th>申购状态</th>")
        assert self._render(frag, purchase_status_display=None).strip() == ""

    def test_header_rendered_when_display_present(self):
        frag = self._extract("{% if purchase_status_display %}<th>申购状态</th>")
        html = self._render(frag, purchase_status_display={"cells": {}})
        assert "<th>申购状态</th>" in html

    def test_cell_renders_status_text(self):
        """明细行单元格取自 cells 映射（与 Excel 同一文案函数产出）。"""
        frag = self._extract(
            "{% if purchase_status_display %}\n"
            '                            <td class="text-left">{{ purchase_status_display.cells.get'
        )
        display = {"cells": {"600900": "🟡 限大额 日限 100 元"}}
        html = self._render(frag, purchase_status_display=display, d={"code": "600900"})
        assert "🟡 限大额 日限 100 元" in html

    def test_cell_defaults_to_dash_for_missing_code(self):
        frag = self._extract(
            "{% if purchase_status_display %}\n"
            '                            <td class="text-left">{{ purchase_status_display.cells.get'
        )
        html = self._render(frag, purchase_status_display={"cells": {}}, d={"code": "000001"})
        assert "—" in html

    def test_cell_block_hidden_when_display_none(self):
        frag = self._extract(
            "{% if purchase_status_display %}\n"
            '                            <td class="text-left">{{ purchase_status_display.cells.get'
        )
        assert self._render(frag, purchase_status_display=None, d={"code": "600900"}).strip() == ""

    def test_subtotal_and_total_pad_cell_conditional(self):
        """小计/总计行随列可见性补空单元格（列对齐）。"""
        frag = self._extract("{% if purchase_status_display %}<td></td>")
        assert self._render(frag, purchase_status_display=None).strip() == ""
        assert "<td></td>" in self._render(frag, purchase_status_display={"cells": {}})

    def test_footnote_rendered_with_channel_caveat(self):
        """脚注区块：列展示时恒在，文案与 Excel 同源（单源函数产出）。"""
        frag = self._extract(
            '{% if purchase_status_display %}\n            <div style="padding: 4px 8px; font-size: 12px; color:'
        )
        data = _contract()
        display = {"footnote": ps.purchase_status_footnote(data), "level": "fresh"}
        html = self._render(frag, purchase_status_display=display)
        assert ps.PURCHASE_STATUS_FOOTNOTE in html
        assert self._render(frag, purchase_status_display=None).strip() == ""

    def test_footnote_stale_level_uses_warning_style(self):
        """stale 档脚注用告警色（黄标；文案本身仍为单源同一条）。"""
        frag = self._extract(
            '{% if purchase_status_display %}\n            <div style="padding: 4px 8px; font-size: 12px; color:'
        )
        html = self._render(frag, purchase_status_display={"footnote": "x", "level": "stale"})
        assert "#B8860B" in html


class TestRestrictedIndex:
    """受限标的预格式化索引（restricted_index 契约字段）。

    准入四条（设计 §3.1）：契约非 None / available=True / 时效非 expired /
    持仓∩行集存在受限标的；字段值与单元格文案同源（单源数值解释）。
    """

    def _restricted_rows(self) -> dict:
        """四类代表状态行（限大额已知/未知、暂停、开放）。"""
        return {
            "519674": {
                "purchase_status": "限大额",
                "redemption_status": "开放赎回",
                "next_open_date": "",
                "daily_limit": 100.0,
                "min_purchase": None,
            },
            "000043": {
                "purchase_status": "限大额",
                "redemption_status": "开放赎回",
                "next_open_date": "",
                "daily_limit": None,  # 0 元/缺失 → 解析层已转 None（限额未知）
                "min_purchase": None,
            },
            "270042": {
                "purchase_status": "暂停申购",
                "redemption_status": "开放赎回",
                "next_open_date": "2026-10-15",
                "daily_limit": None,
                "min_purchase": None,
            },
            "600900": {
                "purchase_status": "开放申购",
                "redemption_status": "开放赎回",
                "next_open_date": "",
                "daily_limit": None,
                "min_purchase": None,
            },
        }

    def test_contract_none_returns_empty(self):
        """准入①：开关关（契约 None）→ 空索引（消费方逐字节回退）。"""
        assert ps.build_restricted_index(None, ["519674"]) == {}

    def test_unavailable_returns_empty(self):
        """准入②：available=False 降级契约 → 空索引。"""
        assert ps.build_restricted_index(_contract(available=False), ["519674"]) == {}

    def test_expired_returns_empty(self, monkeypatch):
        """准入③：时效 expired → 空索引（阶梯判据由既有阶梯用例锁定，此处只测准入分支）。"""
        monkeypatch.setattr(ps, "stale_level", lambda fetched_at=None, today=None: "expired")
        contract = _contract(self._restricted_rows(), fetched_at="2020-01-01T08:00:00+08:00")
        assert ps.build_restricted_index(contract, ["519674"]) == {}

    def test_no_restricted_holding_returns_empty(self):
        """准入④：持仓 ∩ 行集无受限标的（仅开放/查无/空 codes）→ 空索引。"""
        contract = _contract(self._restricted_rows())
        assert ps.build_restricted_index(contract, ["600900"]) == {}
        assert ps.build_restricted_index(contract, ["999999"]) == {}
        assert ps.build_restricted_index(contract, []) == {}
        assert ps.build_restricted_index(contract, None) == {}

    def test_restricted_fields_and_source_alignment(self):
        """索引字段值与单元格文案同源（同一千分位串、同一日期格式）。"""
        contract = _contract(self._restricted_rows())
        codes = ["519674", "000043", "270042", "600900"]
        index = ps.build_restricted_index(contract, codes)
        # 开放申购不入索引（受限状态集 = 单元格 🟡/🔴 同判据）
        assert set(index) == {"519674", "000043", "270042"}
        assert index["519674"]["status"] == "限大额"
        assert index["519674"]["limit"] == pytest.approx(100.0)
        assert index["519674"]["limit_text"] == "100"
        assert index["000043"]["limit"] is None
        assert index["000043"]["limit_text"] == "限额未知"
        assert index["270042"]["status"] == "暂停申购"
        assert index["270042"]["next_open_text"] == "10月15日"
        assert index["519674"]["level"] == "fresh"
        # 同源断言：单元格文案包含同一 limit_text（单源数值解释，非两份拼写）
        cell = ps.format_purchase_status_cell(contract, "519674", level="fresh")
        assert f"日限 {index['519674']['limit_text']} 元" in cell

    def test_stale_level_still_admitted(self, monkeypatch):
        """stale 档（4~7 交易日）仍产索引——准入只排 expired，level 字段透传。"""
        monkeypatch.setattr(ps, "stale_level", lambda fetched_at=None, today=None: "stale")
        contract = _contract(self._restricted_rows())
        index = ps.build_restricted_index(contract, ["519674"])
        assert index["519674"]["level"] == "stale"
