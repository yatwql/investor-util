"""report/financial_indicator.py（财务指标章装配）单元测试。

覆盖：契约键与管线契约类型台账登记、无标的/全无覆盖的降级、成功行的派生值
（质量档/趋势/当前 PE/PB）与明细、失败清单不吞、开关访问器默认值与
章节注册/导航分组/模板接线。

运行：
  pytest src/test/unit/report/test_financial_indicator.py -v
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.python.report import financial_indicator as fi

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_CONTRACT_KEYS = {"available", "reason", "rows", "failures", "entry_count"}


@pytest.fixture(autouse=True)
def _datasink_ready(monkeypatch):
    """本文件默认在「DataSinking 数据底座就绪」下验证装配逻辑；门禁用例自行关闭。"""
    import src.python.config as cfg

    monkeypatch.setattr(cfg, "datasink_feature_ready", lambda config=None: True)


def _holding(code="600900", name="长江电力"):
    return SimpleNamespace(code=code, name=name)


def _record(period="2025-12-31", revenue=100.0, net_profit=10.0, **extra) -> dict:
    record = {
        "code": "600900",
        "symbol": "600900.SS",
        "report_period": period,
        "doc_type": "annual",
        "revenue": revenue,
        "net_profit": net_profit,
        "revenue_yoy": None,
        "net_profit_yoy": None,
        "gross_margin": 0.55,
        "roe": 0.20,
        "debt_ratio": 0.25,
        "operating_cash_flow": 12.0,
        "eps": 2.0,
        "bvps": 10.0,
        "source_api": "akshare_financial",
        "source": "akshare 财务指标",
    }
    record.update(extra)
    return record


class TestDegradedContracts:
    def test_no_a_share_targets(self):
        result = fi.build_financial_indicator([_holding(code="016055", name="某联接基金")])
        assert set(result) == _CONTRACT_KEYS
        assert result["available"] is False
        assert "无 A 股" in result["reason"]

    def test_all_uncovered_lists_failures(self, monkeypatch):
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: [])
        result = fi.build_financial_indicator([_holding()])
        assert result["available"] is False
        assert result["entry_count"] == 0
        assert [f["code"] for f in result["failures"]] == ["600900"]
        assert "无指标数据" in result["failures"][0]["reason"]


class TestAssembly:
    def test_row_carries_indicators_quality_trend_and_valuation(self, monkeypatch):
        series = [
            _record("2025-12-31", revenue=130.0, net_profit=13.0),
            _record("2024-12-31", revenue=100.0, net_profit=10.0),
        ]
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: series)
        result = fi.build_financial_indicator([_holding()], prices={"600900": 40.0})

        assert result["available"] is True
        assert result["entry_count"] == 1
        row = result["rows"][0]
        assert row["code"] == "600900"
        assert row["name"] == "长江电力"
        assert row["report_period"] == "2025-12-31"
        assert row["doc_type_label"] == "年报"
        assert row["source_api"] == "akshare_financial"
        assert row["revenue"] == pytest.approx(130.0)
        assert row["quality_grade"] == "优"
        # 四维：ROE 3 + 毛利率 3 + 负债率 3 + 现金流覆盖（12/13=0.92）2 → 均值 2.75
        assert row["quality_score"] == pytest.approx(2.75)
        assert row["trend"] == "增长"
        assert row["pe"] == pytest.approx(20.0)
        assert row["pb"] == pytest.approx(4.0)
        assert row["period_count"] == 2
        assert len(row["series"]) == 2

    def test_both_growth_required_for_growth_label(self, monkeypatch):
        """相邻年报营收/净利增速不一致（一增一平）→ 波动，不强行贴「增长」。"""
        series = [
            _record("2025-12-31", revenue=102.0, net_profit=13.0),
            _record("2024-12-31", revenue=100.0, net_profit=10.0),
        ]
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: series)
        row = fi.build_financial_indicator([_holding()])["rows"][0]
        assert row["trend"] == "波动"

    def test_missing_price_leaves_valuation_empty(self, monkeypatch):
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: [_record()])
        row = fi.build_financial_indicator([_holding()])["rows"][0]
        assert row["pe"] is None
        assert row["pb"] is None
        assert row["quality_grade"] != ""

    def test_partial_failures_kept(self, monkeypatch):
        def _series(code, limit=8):
            return [_record()] if code == "600900" else []

        monkeypatch.setattr(fi, "fetch_indicator_series", _series)
        holdings = [_holding("600900", "长江电力"), _holding("000001", "平安银行")]
        result = fi.build_financial_indicator(holdings)
        assert result["entry_count"] == 1
        assert [f["code"] for f in result["failures"]] == ["000001"]

    def test_penetrated_targets_included_with_name_and_source(self, monkeypatch):
        """穿透标的名回填 + 来源标注（区块①不再只剩代码、无名称）。"""
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: [_record()])
        result = fi.build_financial_indicator(
            [],
            penetrated_targets=[{"code": "600519", "name": "贵州茅台", "sources": ["[ETF] 某ETF(561910)"]}],
        )
        assert result["entry_count"] == 1
        assert result["rows"][0]["code"] == "600519"
        assert result["rows"][0]["name"] == "贵州茅台"
        assert result["rows"][0]["target_source"] == "穿透：[ETF] 某ETF(561910)"


class TestOrchestration:
    """编排接缝：开关关闭返回 None；开启时用行情现价算 PE/PB。"""

    def test_switch_off_returns_none(self):
        from src.python.report.orchestrator import compute_financial_indicator_data

        assert compute_financial_indicator_data([_holding()], None, {}, None) is None

    def test_switch_on_builds_with_prices_from_details(self, monkeypatch):
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: [_record()])
        from src.python.report.orchestrator import compute_financial_indicator_data

        details = [SimpleNamespace(code="600900", price=40.0)]
        from src.python.config.features import set_feature_enabled

        set_feature_enabled("financial_indicator", True)
        out = compute_financial_indicator_data([_holding()], None, {}, None, details=details)
        assert out is not None and out["available"] is True
        assert out["rows"][0]["pe"] == pytest.approx(20.0)

    def test_penetrated_assets_names_are_forwarded(self, monkeypatch):
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: [_record()])
        from src.python.report.orchestrator import compute_financial_indicator_data

        from src.python.config.features import set_feature_enabled

        set_feature_enabled("financial_indicator", True)
        out = compute_financial_indicator_data(
            [],
            [
                {"name": "贵州茅台", "codes": ["600519"], "funds": ["[ETF] 某ETF(561910)"]},
                {"name": "平安银行", "codes": ["000001", "600036"], "funds": ["直接持有"]},
            ],
            {},
            None,
        )
        assert {r["code"] for r in out["rows"]} == {"600519", "000001", "600036"}
        by_code = {r["code"]: r for r in out["rows"]}
        assert by_code["600519"]["name"] == "贵州茅台"
        assert by_code["600519"]["target_source"] == "穿透：[ETF] 某ETF(561910)"
        # 穿透层里记「直接持有」的来源被剔除（该标的以持仓身份入列）
        assert by_code["000001"]["target_source"] == "穿透"


class TestDatasinkGate:
    """DataSinking 数据底座门禁：未就绪时章节整体静默隐藏（返回 None，不写占位）。"""

    def test_not_ready_returns_none(self, monkeypatch):
        import src.python.config as cfg

        monkeypatch.setattr(cfg, "datasink_feature_ready", lambda config=None: False)
        monkeypatch.setattr(fi, "fetch_indicator_series", lambda code, limit=8: [_record()])
        assert fi.build_financial_indicator([_holding()]) is None

    def test_gate_checked_before_any_fetch(self, monkeypatch):
        """门禁不通过时不得发起取数（零网络、零延迟）。"""
        import src.python.config as cfg

        monkeypatch.setattr(cfg, "datasink_feature_ready", lambda config=None: False)
        called = {"n": 0}

        def _series(code, limit=8):
            called["n"] += 1
            return []

        monkeypatch.setattr(fi, "fetch_indicator_series", _series)
        assert fi.build_financial_indicator([_holding()]) is None
        assert called["n"] == 0

    def test_orchestrator_returns_none_when_not_ready(self, monkeypatch):
        import src.python.config as cfg

        monkeypatch.setattr(cfg, "datasink_feature_ready", lambda config=None: False)
        from src.python.report.orchestrator import compute_financial_indicator_data

        out = compute_financial_indicator_data(
            [_holding()], None, {"legacy_removed_key": {"financial_indicator": True}}, None
        )
        assert out is None


class TestSwitchAndWiring:
    def test_switch_accessor_follows_registry(self):
        """取值来自功能开关注册表（config 形参已不参与取值）。"""
        from src.python.config import is_enable_financial_indicator
        from src.python.config.features import set_feature_enabled

        assert is_enable_financial_indicator() is False
        set_feature_enabled("financial_indicator", True)
        assert is_enable_financial_indicator() is True

    def test_default_config_has_switch_off(self):
        """默认关的事实来源 = 功能开关注册表（GROUP_REPORT）。"""
        from src.python.config.features import feature_switch_registry

        assert feature_switch_registry["financial_indicator"].default is False

    def test_registry_section_registered(self):
        from src.python.core.registry import _REPORT_SECTION_DEFAULT, get_report_section_keys, get_report_sheet_name

        section = next(s for s in _REPORT_SECTION_DEFAULT if s["key"] == "fundamental_snapshot")
        assert section["type"] == "fundamental_snapshot"
        assert section["data_flag"] is None
        assert section["data_flag_any"] == ("financial_indicator_data", "financial_report_digest_data")
        assert "fundamental_snapshot" in get_report_section_keys()
        assert get_report_sheet_name("fundamental_snapshot") == "持仓基本面"

    def test_pipeline_contract_registered_with_optional_type(self):
        from src.python.report.pipeline_data_builder import (
            _PIPELINE_DATA_KNOWN_KEYS,
            _PIPELINE_DATA_TYPE_MAP,
            _PREP_KNOWN_KEYS,
        )

        assert "financial_indicator_data" in _PIPELINE_DATA_KNOWN_KEYS
        assert "financial_indicator_data" in _PREP_KNOWN_KEYS
        assert _PIPELINE_DATA_TYPE_MAP["financial_indicator_data"] == (dict, type(None))

    def test_nav_group_and_template_include(self):
        from src.python.report.html_writer_nav import _SECTION_NAV_GROUP_MAP

        assert _SECTION_NAV_GROUP_MAP["fundamental_snapshot"] == "basic"

        tmpl_dir = Path(__file__).resolve().parents[3] / "static" / "tmpl"
        template = (tmpl_dir / "report_template.html").read_text(encoding="utf-8")
        partial = (tmpl_dir / "partials" / "fundamental_snapshot_section.html").read_text(encoding="utf-8")
        assert 'include "partials/fundamental_snapshot_section.html"' in template
        assert 'section_visible("fundamental_snapshot")' in partial
        assert "financial_indicator_data" in partial
