"""HTML 报告·基金深度分析数据构建器的报告期时效处置测试。

测试目标：
  - _fetch_fund_holdings_with_period：持仓一并透出报告期判定
  - _split_stale_funds：陈旧基金与可用基金分列
  - _render_overlap_matrix：陈旧基金剔除出矩阵并在产物中留痕
  - _render_concentration / _render_style_analysis：保留全部基金并透出报告期

HTML 与 Excel 两侧口径必须一致：重合度按市值加权故剔除陈旧者，
集中度与风格保留但标注报告期。全部 fetcher 均为 mock，禁止真实网络请求。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.report import html_renderers as hr
from src.python.report.holdings_freshness import evaluate_report_period
from src.test.helpers import recent_holdings_period

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class _Holding:
    """最小持仓替身（is_fund 只看 name/code/account）。"""

    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name
        self.account = "主账户"


def _prog() -> object:
    return type(
        "_P",
        (),
        {
            "info": lambda self, m: None,
            "ok": lambda self, m: None,
            "add_error": lambda self, m: None,
        },
    )()


def _fh(code_name: str, date: str | None) -> dict:
    payload = {"name": code_name, "holdings": [{"name": "贵州茅台", "code": "600519", "ratio": 9.0}]}
    if date:
        payload["date"] = date
    return payload


class TestFetchWithPeriod:
    """_fetch_fund_holdings_with_period：报告期随持仓透出。"""

    def test_attaches_period_info(self):
        period = recent_holdings_period()
        with patch.object(hr, "fetch_fund_holdings_cached", return_value=_fh("当代基金", period)):
            result = hr._fetch_fund_holdings_with_period(["110020"])

        assert result["110020"]["period_info"].period == period
        assert result["110020"]["period_info"].stale is False
        assert result["110020"]["holdings"][0]["code"] == "600519"

    def test_skips_funds_without_holdings(self):
        with patch.object(hr, "fetch_fund_holdings_cached", return_value={"name": "空基金", "holdings": []}):
            assert hr._fetch_fund_holdings_with_period(["110020"]) == {}


class TestSplitStaleFunds:
    """_split_stale_funds：陈旧与可用分列。"""

    def test_excludes_stale_and_notes_period(self):
        fresh, names, stale_notes = hr._split_stale_funds(
            {
                "110020": {
                    "name": "当代基金",
                    "holdings": [{"code": "600519", "ratio": 9.0}],
                    "period_info": evaluate_report_period(recent_holdings_period()),
                },
                "040046": {
                    "name": "陈年基金",
                    "holdings": [{"code": "000858", "ratio": 7.0}],
                    "period_info": evaluate_report_period("2022-12-08"),
                },
            }
        )

        assert list(fresh) == ["110020"]
        assert names == {"110020": "当代基金"}
        assert len(stale_notes) == 1
        assert "陈年基金" in stale_notes[0]
        assert "2022-12-08" in stale_notes[0]
        assert "完整季度" in stale_notes[0]


class TestRenderOverlapMatrix:
    """_render_overlap_matrix：陈旧基金剔除出矩阵并留痕。"""

    _HOLDINGS = [_Holding("000001", "沪深300指数基金"), _Holding("110020", "中证500指数基金")]

    def test_returns_none_when_disabled(self):
        assert hr._render_overlap_matrix(self._HOLDINGS, [], False, _prog()) is None

    def test_stale_fund_excluded_from_matrix(self):
        """陈旧基金不入矩阵，且剔除清单随结果透出（供产物标注）。"""
        mapping = {
            "000001": {
                "name": "当代基金",
                "holdings": [{"code": "600519", "ratio": 9.0}],
                "period_info": evaluate_report_period(recent_holdings_period()),
            },
            "110020": {
                "name": "陈年基金",
                "holdings": [{"code": "000858", "ratio": 7.0}],
                "period_info": evaluate_report_period("2022-12-08"),
            },
        }
        with patch.object(hr, "_fetch_fund_holdings_with_period", return_value=mapping):
            result = hr._render_overlap_matrix(self._HOLDINGS, [], True, _prog())

        assert result["funds"] == []  # 仅剩 1 只，凑不成矩阵
        assert len(result["stale_fund_notes"]) == 1
        assert "陈年基金" in result["stale_fund_notes"][0]

    def test_two_fresh_funds_still_computed(self):
        """两只新鲜基金照常出矩阵（闸门不可误伤正常路径）。"""
        period = recent_holdings_period()
        mapping = {
            "000001": {
                "name": "基金甲",
                "holdings": [{"code": "600519", "ratio": 9.0}, {"code": "000858", "ratio": 7.0}],
                "period_info": evaluate_report_period(period),
            },
            "110020": {
                "name": "基金乙",
                "holdings": [{"code": "600519", "ratio": 8.0}, {"code": "002415", "ratio": 5.0}],
                "period_info": evaluate_report_period(period),
            },
        }
        with patch.object(hr, "_fetch_fund_holdings_with_period", return_value=mapping):
            result = hr._render_overlap_matrix(self._HOLDINGS, [], True, _prog())

        assert sorted(result["funds"]) == ["000001", "110020"]
        assert result["stale_fund_notes"] == []


class TestRenderConcentrationAndStyle:
    """_render_concentration / _render_style_analysis：保留并透出报告期。"""

    _HOLDINGS = [_Holding("000001", "沪深300指数基金")]

    def _mapping(self) -> dict:
        return {
            "000001": {
                "name": "该基金",
                "holdings": [{"code": "600519", "ratio": 9.0}],
                "period_info": evaluate_report_period(recent_holdings_period()),
            }
        }

    def test_concentration_receives_period_info(self):
        with patch.object(hr, "_fetch_fund_holdings_with_period", return_value=self._mapping()):
            with patch.object(hr, "compute_concentration", return_value=[]) as mock_conc:
                hr._render_concentration(self._HOLDINGS, True, _prog())

        passed = mock_conc.call_args[0][0]
        assert passed["000001"]["period_info"].period == recent_holdings_period()

    def test_style_receives_period_info(self):
        with patch.object(hr, "_fetch_fund_holdings_with_period", return_value=self._mapping()):
            with patch.object(hr, "analyze_style_for_all_funds", return_value={"results": []}) as mock_style:
                hr._render_style_analysis(self._HOLDINGS, True, _prog())

        passed = mock_style.call_args[0][0]
        assert passed["000001"]["period_info"].period == recent_holdings_period()

    def test_disabled_returns_none(self):
        assert hr._render_concentration(self._HOLDINGS, False, _prog()) is None
        assert hr._render_style_analysis(self._HOLDINGS, False, _prog()) is None
