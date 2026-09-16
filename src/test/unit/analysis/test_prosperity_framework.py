"""景气度框架诊断单元测试（实验性功能 `prosperity_framework`）。

覆盖：
  - 六维计分口径（景气方向 / ROE 低位弹性 / 全球视野 / 流动性 / 集中度与周期拼接 / 业绩回撤印证）
  - 数据缺失降级（unverified 不计分、不臆造）+ 总分口径（scored_weight / total_score_pct / 评级）
  - 持仓视角清单与免责句
运行：pytest src/test/unit/analysis/test_prosperity_framework.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.prosperity_framework import (
    DEFAULT_CONFIG,
    build_prosperity_framework_data,
)
from src.python.report.market_value import DetailRow

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _row(code: str, name: str, mv: float, account: str = "A") -> DetailRow:
    return DetailRow(account=account, name=name, code=code, market_value=mv, cost=mv * 0.9, profit=mv * 0.1)


def _details() -> list[DetailRow]:
    # 光通信/半导体（景气 + 全球比较优势）60 万 + 白酒（防御）30 万 + 银行 10 万
    return [
        _row("300308", "中际旭创", 300_000.0),
        _row("688981", "中芯国际", 300_000.0),
        _row("600519", "贵州茅台", 300_000.0),
        _row("601398", "工商银行", 100_000.0),
    ]


def _penetration() -> dict:
    return {
        "top10": [
            {"name": "中际旭创", "sector": "科技", "concepts": ["光通信", "算力"], "ratio_pct": 30.0},
            {"name": "中芯国际", "sector": "科技", "concepts": ["半导体", "芯片"], "ratio_pct": 30.0},
            {"name": "贵州茅台", "sector": "消费", "concepts": ["白酒"], "ratio_pct": 30.0},
            {"name": "工商银行", "sector": "金融", "concepts": ["银行"], "ratio_pct": 10.0},
        ]
    }


def _indicator_data() -> dict:
    return {
        "available": True,
        "rows": [
            {"code": "300308", "roe": 0.06, "trend": "改善"},
            {"code": "688981", "roe": 0.08, "trend": "持平"},
            {"code": "600519", "roe": 0.31, "trend": "持平"},
            {"code": "601398", "roe": 0.11, "trend": "持平"},
        ],
    }


def _liquidity() -> list[dict]:
    return [
        {"code": "300308", "name": "中际旭创", "type": "stock", "liquidation_days": 0.5},
        {"code": "688981", "name": "中芯国际", "type": "stock", "liquidation_days": 2.0},
        {"code": "600519", "name": "贵州茅台", "type": "otc"},
    ]


def _snapshots() -> list[dict]:
    return [
        {"holdings": [{"code": "300308"}, {"code": "688981"}, {"code": "600519"}]},
        {"holdings": [{"code": "300308"}, {"code": "601398"}]},
    ]


def _history() -> dict:
    """生产形态 history_data（`benchmarks` 为 **list[dict]**，见
    `PortfolioHistoryCalculator.get_combined_timeseries` 契约）。"""
    return {
        "status": "ok",
        "drawdown_available": True,
        "total_return_pct": 18.5,
        "max_drawdown_pct": -12.0,
        "benchmarks": [
            {"code": "sh000300", "name": "沪深300", "total_return_pct": 6.0},
            {"code": "sh000905", "name": "中证500", "total_return_pct": 9.0},
        ],
    }


def _history_legacy_dict_benchmarks() -> dict:
    """旧/注入形态：benchmarks 为 dict[str, dict]（兼容性用例）。"""
    return {
        "status": "ok",
        "drawdown_available": True,
        "total_return_pct": 18.5,
        "max_drawdown_pct": 12.0,
        "benchmarks": {"sh000300": {"total_return_pct": 6.0}, "sh000905": {"total_return_pct": 9.0}},
    }


class TestBoomDimension:
    def test_keyword_hit_and_defensive_penalty(self):
        data = build_prosperity_framework_data(_details(), penetration_data=_penetration())
        boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
        assert boom["status"] == "scored"
        # 景气 60% → 满分档；防御 30% 触发反向扣减
        assert 0 < boom["score"] < boom["max_score"]
        assert any("命中景气关键词" in e for e in boom["evidence"])
        assert any("防御/红利" in e for e in boom["evidence"])

    def test_bonus_none_hit_scores_zero(self):
        details = [_row("601398", "工商银行", 100_000.0)]
        data = build_prosperity_framework_data(
            details,
            penetration_data={
                "top10": [{"name": "工商银行", "sector": "金融", "concepts": ["银行"], "ratio_pct": 100.0}]
            },
        )
        boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
        assert boom["score"] == 0

    def test_falls_back_to_direct_holdings_without_penetration(self):
        data = build_prosperity_framework_data(_details())
        boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
        assert any("直接持仓板块分布" in e for e in boom["evidence"])


class TestRoeDimension:
    def test_unverified_without_contract(self):
        data = build_prosperity_framework_data(_details(), penetration_data=_penetration())
        roe = next(d for d in data["dimensions"] if d["key"] == "roe_elasticity")
        assert roe["status"] == "unverified"
        assert roe["score"] == 0
        assert roe["unverified"], "缺数据必须给出可读的未验证说明"
        assert any("ROE 低位弹性" in u for u in data["unverified"])

    def test_scored_with_low_roe_and_trend_bonus(self):
        data = build_prosperity_framework_data(
            _details(), penetration_data=_penetration(), financial_indicator_data=_indicator_data()
        )
        roe = next(d for d in data["dimensions"] if d["key"] == "roe_elasticity")
        assert roe["status"] == "scored"
        assert roe["score"] > 0
        assert any("低 ROE" in e for e in roe["evidence"])
        assert any("趋势改善" in e for e in roe["evidence"])

    def test_partial_status_when_some_codes_missing_roe(self):
        data = build_prosperity_framework_data(
            _details(), financial_indicator_data={"available": True, "rows": [{"code": "300308", "roe": 0.05}]}
        )
        roe = next(d for d in data["dimensions"] if d["key"] == "roe_elasticity")
        assert roe["status"] == "partial"
        assert any("未取到 ROE" in u for u in roe["unverified"])


class TestGlobalEdgeDimension:
    def test_edge_and_offshore_bonus(self):
        details = _details() + [_row("AAPL", "苹果", 100_000.0)]
        data = build_prosperity_framework_data(details, penetration_data=_penetration())
        dim = next(d for d in data["dimensions"] if d["key"] == "global_edge")
        assert dim["score"] > 0
        assert any("境外" in e or "港股" in e for e in dim["evidence"])


class TestLiquidityDimension:
    def test_tier_by_worst_days(self):
        data = build_prosperity_framework_data(_details(), liquidity_signals=_liquidity())
        dim = next(d for d in data["dimensions"] if d["key"] == "liquidity")
        # 最差 2.0 日 → <3 日档（7 分）；场外 1 只 → partial
        assert dim["score"] == 7
        assert dim["status"] == "partial"
        assert any("场外" in u for u in dim["unverified"])

    def test_unverified_when_all_otc(self):
        data = build_prosperity_framework_data(_details(), liquidity_signals=[{"code": "040046", "type": "otc"}])
        dim = next(d for d in data["dimensions"] if d["key"] == "liquidity")
        assert dim["status"] == "unverified"
        assert dim["score"] == 0

    def test_unverified_without_signals(self):
        data = build_prosperity_framework_data(_details())
        dim = next(d for d in data["dimensions"] if d["key"] == "liquidity")
        assert dim["status"] == "unverified"


class TestConcentrationDimension:
    def test_concentration_and_turnover_scored(self):
        data = build_prosperity_framework_data(_details(), snapshots=_snapshots())
        dim = next(d for d in data["dimensions"] if d["key"] == "concentration_cycle")
        assert dim["status"] == "scored"
        assert dim["score"] > 0
        assert data["concentration_pct"] is not None and data["turnover_proxy_pct"] is not None
        assert any("换手代理" in e for e in dim["evidence"])

    def test_partial_when_no_snapshots(self):
        data = build_prosperity_framework_data(_details())
        dim = next(d for d in data["dimensions"] if d["key"] == "concentration_cycle")
        assert dim["status"] == "partial"
        # 该夹具仅 4 只持仓（全部落入前十 → 集中度 100% > 1.4×50% → 高集中度档 3 分）
        assert dim["score"] == 3
        assert any("无历史快照" in u for u in dim["unverified"])


class TestPerformanceDimension:
    def test_scored_with_history(self):
        data = build_prosperity_framework_data(_details(), history_data=_history())
        dim = next(d for d in data["dimensions"] if d["key"] == "performance")
        assert dim["status"] == "scored"
        assert dim["score"] == dim["max_score"]  # 收益为正 + 跑赢最强基准 + 回撤 ≤15% → 满档
        assert any("跑赢最强对比基准" in e for e in dim["evidence"])

    def test_unverified_without_history(self):
        data = build_prosperity_framework_data(_details())
        dim = next(d for d in data["dimensions"] if d["key"] == "performance")
        assert dim["status"] == "unverified"
        assert dim["score"] == 0


class TestTotalsAndOutput:
    def test_totals_exclude_unverified_dimensions(self):
        data = build_prosperity_framework_data(
            _details(),
            penetration_data=_penetration(),
            financial_indicator_data=_indicator_data(),
            liquidity_signals=_liquidity(),
            snapshots=_snapshots(),
            history_data=_history(),
        )
        # 全部六维可计分
        assert data["scored_weight"] == data["max_score"] == 100
        assert 0 <= data["total_score"] <= 100
        assert data["total_score_pct"] == round(data["total_score"] / data["scored_weight"] * 100)
        assert data["rating_label"] in ("高度契合", "较契合", "部分契合", "不契合")

    def test_partial_inputs_reduce_scored_weight(self):
        data = build_prosperity_framework_data(_details(), penetration_data=_penetration())
        # ROE(20)/流动性(10)/业绩(15) 未验证 → scored_weight = 25+15+15 = 55
        assert data["scored_weight"] == 55
        assert data["total_score_pct"] == round(data["total_score"] / 55 * 100)
        assert len(data["unverified"]) == 3

    def test_holdings_view_and_disclaimer(self):
        data = build_prosperity_framework_data(_details(), penetration_data=_penetration())
        view = data["holdings_view"]
        assert view and view[0]["weight_pct"] >= view[-1]["weight_pct"]
        assert any("命中景气方向关键词" in n for n in [n for item in view for n in item["notes"]])
        assert any("非投资建议" in n for n in data["notes"])

    def test_unavailable_on_empty_holdings(self):
        data = build_prosperity_framework_data([])
        assert data["available"] is False
        assert data["reason"]

    def test_custom_config_overrides_keywords(self):
        cfg = {"prosperity_framework": {**DEFAULT_CONFIG, "boom_keywords": ["白酒"], "defensive_keywords": []}}
        data = build_prosperity_framework_data(_details(), penetration_data=_penetration(), config=cfg)
        boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
        assert any("命中景气关键词" in e for e in boom["evidence"])


class TestRatingBoundaries:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (100, "高度契合"),
            (80, "高度契合"),
            (79, "较契合"),
            (60, "较契合"),
            (59, "部分契合"),
            (40, "部分契合"),
            (39, "不契合"),
            (0, "不契合"),
        ],
    )
    def test_rating_label_thresholds(self, score, expected):
        from src.python.analysis.prosperity_framework import _rating

        assert _rating(score)[1] == expected


class TestPerformanceDimensionBenchmarkShapes:
    """基准形态回归：`benchmarks` 生产为 list[dict]（原先按 dict 取值 → AttributeError
    被维度守卫吞成「需核实」，用户报障「组合历史走势与回撤章节有数据、但该维显示缺失」）。"""

    def _details(self):
        return [DetailRow(account="A", name="某标的", code="300308", market_value=100_000.0, cost=90_000.0)]

    def test_list_benchmarks_scored_with_name(self):
        """list[dict] 生产形态 → 该维可计分，证据含基准名与收益率。"""
        from src.python.analysis.prosperity_framework import _score_performance

        dim = _score_performance(_history())
        assert dim["status"] == "scored"
        assert dim["score"] == dim["max_score"]  # 收益正 + 跑赢最强 + 回撤 ≤15%
        assert any("中证500 +9.00%" in e for e in dim["evidence"])

    def test_underperform_benchmark_scores_base_plus_drawdown(self):
        """未跑赢最强基准 + 回撤 >15% → 不得加分（真实数据形态复核口径）。"""
        from src.python.analysis.prosperity_framework import _score_performance

        dim = _score_performance(
            {
                "status": "ok",
                "drawdown_available": True,
                "total_return_pct": -18.11,
                "max_drawdown_pct": -22.42,
                "benchmarks": [{"code": "sh000300", "name": "沪深300", "total_return_pct": -10.36}],
            }
        )
        assert dim["status"] == "scored"
        assert dim["score"] == 4  # 收益非正 3 分 + 回撤 ≤25% 加 1 分
        assert any("未跑赢最强对比基准（沪深300 -10.36%）" in e for e in dim["evidence"])
        assert any("最大回撤 22.42%" in e for e in dim["evidence"])

    def test_legacy_dict_benchmarks_still_supported(self):
        from src.python.analysis.prosperity_framework import _score_performance

        dim = _score_performance(_history_legacy_dict_benchmarks())
        assert dim["status"] == "scored"

    def test_malformed_benchmarks_do_not_raise(self):
        """畸形基准（非 dict 元素/缺字段/非数值）→ 不抛异常，仅按自身收益回撤计分。"""
        from src.python.analysis.prosperity_framework import _score_performance

        for bad in (["oops", 3, None], [{"code": "x"}], [{"total_return_pct": "n/a"}], "not-a-list", 42):
            dim = _score_performance(
                {
                    "status": "ok",
                    "drawdown_available": True,
                    "total_return_pct": 5.0,
                    "max_drawdown_pct": -8.0,
                    "benchmarks": bad,
                }
            )
            assert dim["status"] == "scored", bad
            assert 0 <= dim["score"] <= dim["max_score"], bad

    def test_status_degraded_scored_with_note(self):
        """status=degraded（部分持仓缺历史）→ 仍计分，但标注口径可能不完整。"""
        from src.python.analysis.prosperity_framework import _score_performance

        dim = _score_performance(
            {"status": "degraded", "drawdown_available": True, "total_return_pct": 3.0, "max_drawdown_pct": -9.0}
        )
        assert dim["status"] == "partial"
        assert dim["score"] > 0
        assert any("degraded" in u for u in dim["unverified"])

    def test_status_unavailable_unverified(self):
        from src.python.analysis.prosperity_framework import _score_performance

        dim = _score_performance({"status": "unavailable", "total_return_pct": None})
        assert dim["status"] == "unverified"
        assert dim["score"] == 0

    def test_drawdown_unavailable_partial(self):
        from src.python.analysis.prosperity_framework import _score_performance

        dim = _score_performance(
            {"status": "ok", "drawdown_available": False, "total_return_pct": 4.0, "max_drawdown_pct": 0.0}
        )
        assert dim["status"] == "partial"
        assert any("样本不足" in u for u in dim["unverified"])

    def test_contract_through_builder_with_real_shape(self):
        """端到端：真实形态 history_data（含 bars/benchmarks 列表）→ 维度⑥ scored。"""
        data = build_prosperity_framework_data(self._details(), history_data=_history())
        dim = next(d for d in data["dimensions"] if d["key"] == "performance")
        assert dim["status"] == "scored"
        assert "业绩与回撤印证" not in " ".join(data["unverified"])
