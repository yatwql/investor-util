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
        # 章节已拆分到 partials：拼接主模板与全部 partial（标记查找与 if/endif 配平不受拆分影响）
        _partial_dir = os.path.join(os.path.dirname(tmpl_path), "partials")
        for _name in sorted(os.listdir(_partial_dir)):
            if _name.endswith(".html"):
                with open(os.path.join(_partial_dir, _name), encoding="utf-8") as f:
                    self.html += "\n" + f.read()

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


class TestConstraintBlock:
    """申购限购约束块渲染（constraint_block 契约字段，进 LLM 分析章提示词）。

    准入四条（契约非 None / available / 非 expired / 存在受限持仓）+ 块内容
    逐项 + 行序 = 持仓序 + 展示层零泄露。日历以 monkeypatch 注入（无网可复现）；
    阶梯分档本身由陈旧阶梯既有用例锁定，此处不重测（只测准入三态）。
    """

    def _holdings(self, *pairs: tuple[str, str]) -> list[dict]:
        return [{"code": c, "name": n} for c, n in pairs]

    @pytest.fixture(autouse=True)
    def _pin_level(self, monkeypatch):
        """默认钉 fresh（确定性）；个别用例自行改钉。"""
        level = {"value": "fresh"}
        monkeypatch.setattr(ps, "stale_level", lambda *_a, **_k: level["value"])
        return level

    def test_admission_contract_none(self):
        """准入①：契约 None（开关关）→ 块缺席。"""
        assert ps.build_purchase_constraint_block(None, self._holdings(("110022", "安心债券"))) == ""

    def test_admission_unavailable(self):
        """准入②：available=False 降级契约 → 块缺席。"""
        holdings = self._holdings(("110022", "安心债券"))
        assert ps.build_purchase_constraint_block(_contract(available=False), holdings) == ""

    def test_admission_expired(self, _pin_level):
        """准入③：时效 expired → 块缺席（宁缺毋错，过时限购信息不误导模型）。"""
        _pin_level["value"] = "expired"
        holdings = self._holdings(("110022", "安心债券"))
        assert ps.build_purchase_constraint_block(_contract(), holdings) == ""

    def test_admission_no_holdings(self):
        """准入④：持仓明细为空/None → 块缺席（降级矩阵同款）。"""
        assert ps.build_purchase_constraint_block(_contract(), None) == ""
        assert ps.build_purchase_constraint_block(_contract(), []) == ""

    def test_admission_all_open_no_restricted(self):
        """准入④：持仓全部「开放申购」→ 块缺席（正向信息不占 token）。"""
        holdings = self._holdings(("600900", "长江电力"))
        assert ps.build_purchase_constraint_block(_contract(), holdings) == ""

    def test_block_content_fields_and_order(self):
        """块内容逐项：头行口径与抓取日期、字段值同源、开放不列、行序=持仓序。"""
        holdings = self._holdings(
            ("110022", "易方达安心回馈债券"),
            ("600900", "长江电力"),
            ("161725", "景顺长城新兴成长混合"),
        )
        block = ps.build_purchase_constraint_block(_contract(fetched_at="2026-10-09T08:00:00+08:00"), holdings)
        lines = block.split("\n")
        assert lines[0].startswith("【申购限购约束】")
        assert "天天基金渠道口径" in lines[0]
        assert "数据抓取于 2026-10-09" in lines[0]
        assert "⚠ 数据陈旧" not in lines[0]  # fresh 档无陈旧注
        # 开放申购不入块；受限两行字段值与单元格同一数值解释
        assert "- 110022 易方达安心回馈债券 限大额：单账户单日限购 100 元" in block
        assert "- 161725 景顺长城新兴成长混合 暂停申购：下一开放日 10月9日" in block
        assert "600900" not in block
        # 行序 = 持仓明细顺序（110022 在 161725 前，与持仓序一致）
        assert block.index("- 110022") < block.index("- 161725")
        # 尾行硬约束声明
        assert "申购可执行性硬约束" in lines[-1]
        assert "场内标的无申购语义不列" in lines[-1]

    def test_order_follows_holdings_not_sorted_codes(self, monkeypatch):
        """行序取持仓明细顺序而非代码升序（筛选单源内部 sorted 不外泄）。"""
        holdings = self._holdings(("161725", "景顺长城"), ("110022", "易方达"))
        block = ps.build_purchase_constraint_block(_contract(), holdings)
        assert block.index("- 161725") < block.index("- 110022")

    def test_limit_thousand_separator(self):
        """日限额千分位与单元格同源（10000 → 10,000）。"""
        holdings = self._holdings(("000198", "国投瑞银"))
        block = ps.build_purchase_constraint_block(_contract(), holdings)
        assert "单账户单日限购 10,000 元" in block

    def test_stale_level_renders_with_warning(self, _pin_level):
        """stale 档（4~7 交易日）→ 仍出块 + 头行附「⚠ 数据陈旧」（与展示层同语义）。"""
        _pin_level["value"] = "stale"
        holdings = self._holdings(("110022", "安心债券"))
        block = ps.build_purchase_constraint_block(_contract(), holdings)
        assert "限大额" in block
        assert "⚠ 数据陈旧" in block.split("\n")[0]

    def test_contract_field_produced(self, monkeypatch, _pin_level):
        """契约字段 constraint_block：传持仓且存在受限 → 非空 str；不传持仓 → ""。"""
        payload = {"rows": _rows(), "fetched_at": _fresh_ts(), "source": "天天基金"}
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", lambda: payload)
        holdings = self._holdings(("110022", "安心债券"))
        data = ps.build_purchase_status_data({}, holdings_details=holdings)
        assert isinstance(data["constraint_block"], str)
        assert "【申购限购约束】" in data["constraint_block"]
        data_no_holding = ps.build_purchase_status_data({})
        assert data_no_holding["constraint_block"] == ""

    def test_contract_field_degraded_to_empty(self, monkeypatch):
        """降级契约（available=False）→ constraint_block 恒为空串（字段在、值空）。"""
        monkeypatch.setattr("src.python.fetcher.fund_purchase.fetch_fund_purchase_status_cached", lambda: None)
        data = ps.build_purchase_status_data({}, holdings_details=self._holdings(("110022", "安心债券")))
        assert data["available"] is False
        assert data["constraint_block"] == ""

    def test_display_layer_never_leaks_block(self):
        """展示层零影响：单元格与脚注输出绝不含提示词块内容（展示只读既有字段）。"""
        holdings = self._holdings(("110022", "安心债券"))
        contract = _contract()
        contract["constraint_block"] = ps.build_purchase_constraint_block(contract, holdings)
        assert "【申购限购约束】" in contract["constraint_block"]
        cell = ps.format_purchase_status_cell(contract, "110022")
        footnote = ps.purchase_status_footnote(contract)
        assert "【申购限购约束】" not in cell
        assert "申购可执行性硬约束" not in cell
        assert "【申购限购约束】" not in footnote
        assert "申购可执行性硬约束" not in footnote


# ════════════════════════════════════════════════════════════
#  模板条件渲染（report_template.html 持仓分类汇总区块）
# ════════════════════════════════════════════════════════════


class TestCategoryPurchaseTemplate:
    """真实模板分类表片段在 purchase_status_display 开/关下的渲染结果。

    与区块①（市值明细）共用同一 display 对象——列可见性、单元格文案
    与 Excel 端全部单源于 report/purchase_status.py，两端一致。
    """

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
        # 章节已拆分到 partials：拼接主模板与全部 partial（标记查找与 if/endif 配平不受拆分影响）
        _partial_dir = os.path.join(os.path.dirname(tmpl_path), "partials")
        for _name in sorted(os.listdir(_partial_dir)):
            if _name.endswith(".html"):
                with open(os.path.join(_partial_dir, _name), encoding="utf-8") as f:
                    self.html += "\n" + f.read()

    def _row(self, marker: str) -> str:
        """截取 marker 所在的整行 <tr>…</tr> 片段。"""
        pos = self.html.find(marker)
        assert pos != -1, f"模板中未找到标记: {marker}"
        start = self.html.rfind("<tr", 0, pos)
        assert start != -1, "标记不在任何 <tr> 行内"
        end = self.html.find("</tr>", pos)
        assert end != -1, "行未闭合"
        return self.html[start : end + len("</tr>")]

    @staticmethod
    def _render(env, fragment: str, **ctx) -> str:
        return env.from_string(fragment).render(**ctx)

    def test_category_header_column_appended(self):
        """分类表头：display 存在 → 追加「申购状态」th；缺席 → 整列隐。"""
        frag = self._row("<th>年均股息率</th>")
        assert "<th>申购状态</th>" in self._render(self.env, frag, purchase_status_display={"cells": {}})
        assert "<th>申购状态</th>" not in self._render(self.env, frag, purchase_status_display=None)

    def test_category_detail_cell_from_cells_map(self):
        """分类明细行单元格取自同一 cells 映射（与 Excel 同一文案函数产出）。"""
        frag = self._row('{{ group["property"] }}')
        group = {"property": "基金", "sub_category": "被动"}
        item = {
            "name": "电池ETF",
            "code": "561910",
            "market_value": 1000.0,
            "cost": 100.0,
            "profit": 900.0,
            "profit_rate": 9.0,
            "today_profit": 50.0,
            "yield_text": "--",
        }
        display = {"cells": {"561910": "🟡 限大额 日限 100 元"}}
        html = self._render(self.env, frag, purchase_status_display=display, group=group, item=item)
        assert "🟡 限大额 日限 100 元" in html
        html_off = self._render(self.env, frag, purchase_status_display=None, group=group, item=item)
        assert "🟡 限大额" not in html_off

    def test_category_subtotal_row_has_blank_cell(self):
        """分类小计行：display 存在 → 比缺席多一个空 td（非可聚合指标）。"""
        frag = self._row('- {{ group["sub_category"] }} 小计')
        group = {
            "property": "基金",
            "sub_category": "被动",
            "sub_mv": 1.0,
            "sub_cost": 1.0,
            "sub_profit": 0.0,
            "sub_rate": 0.0,
            "sub_today": 0.0,
        }
        on = self._render(self.env, frag, purchase_status_display={"cells": {}}, group=group)
        off = self._render(self.env, frag, purchase_status_display=None, group=group)
        assert on.count("<td") == off.count("<td") + 1

    def test_category_grand_total_row_has_blank_cell(self):
        """分类总计行：片段在 flow 条件后含申购状态空 td 条件块（结构断言）。"""
        frag = self._row("{{ cat_grand_today.v | money }}")  # 分类表总计行独有（区块①总计行不含 cat_grand_*）
        block = "{% if purchase_status_display %}<td></td>{% endif %}"
        flow_block = "{% if flow_display %}<td></td><td></td>{% endif %}"
        assert block in frag
        assert frag.index(flow_block) < frag.index(block)
