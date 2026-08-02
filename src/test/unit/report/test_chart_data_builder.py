"""Chart.js 数据预处理器单元测试 — chart_data_builder.py。

覆盖交互图表模块的验收标准：
  - 6 图固定键契约（§4.11 O2）：portfolio_line / drawdown / category_doughnut /
    industry_bar / penetration_bar / radar
  - 输出 schema（§4.12）：{"labels", "datasets", "degraded"}
  - R11：单图脏数据隔离——一个图失败仅跳过该图
  - R12：radar 三级降级独立构建
  - R9：数据最小化——资产构成只传市值，不含份额/成本
  - 空值语义：键缺失→占位；空数组→无数据；degraded→虚线

运行：
  cd /lzcapp/document/working/codebase/investor-util
  .venv/bin/python -m pytest src/test/unit/report/test_chart_data_builder.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.python.report.chart_data_builder import (
    DATASET_KEYS,
    build_chart_datasets,
    build_evolution_chart_data,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ═══════════════════════════════════════════════════════════════
#  辅助构造
# ═══════════════════════════════════════════════════════════════


def _history_ok(bars=None) -> dict:
    """构造 status=ok 的 history_data。"""
    return {
        "status": "ok",
        "bars": bars
        or [
            {"date": "2026-01-01", "total_value": 100.0, "drawdown_pct": 0.0},
            {"date": "2026-02-01", "total_value": 110.0, "drawdown_pct": -0.02},
        ],
        "benchmarks": [{"name": "沪深300", "bars": [{"value": 100.0}, {"value": 105.0}]}],
    }


def _history_unavailable() -> dict:
    """构造 status=unavailable 的 history_data（不可用）。"""
    return {"status": "unavailable"}


def _details() -> list[SimpleNamespace]:
    """构造含 property 属性的最小持仓明细。"""
    return [
        SimpleNamespace(property="股票", code="600000", name="浦发银行", market_value=10000.0),
        SimpleNamespace(property="基金", code="510300", name="沪深300ETF", market_value=5000.0),
        SimpleNamespace(property="现金", code="CASH", name="货币基金", market_value=2000.0),
    ]


def _penetration(top10=None) -> dict:
    """构造穿透数据。"""
    return {
        "top10": top10
        or [
            {"rank": 1, "name": "贵州茅台", "sector": "白酒", "mv": 3000.0},
            {"rank": 2, "name": "宁德时代", "sector": "新能源", "mv": 2000.0},
            {"rank": 3, "name": "未分类标的", "mv": 1000.0},
        ]
    }


def _gen_bars(n: int, start: str = "2024-01-01") -> list[dict]:
    """生成 n 个连续交易日 bars（2024-01-01 为周一，跳过周末）。"""
    from datetime import date, timedelta

    bars: list[dict] = []
    d = date.fromisoformat(start)
    i = 0
    while len(bars) < n:
        if d.weekday() < 5:
            bars.append(
                {
                    "date": d.isoformat(),
                    "total_value": 100.0 + i,
                    "drawdown_pct": -0.01 * (i % 10) / 10,
                }
            )
            i += 1
        d += timedelta(days=1)
    return bars


# ═══════════════════════════════════════════════════════════════
#  固定键契约（§4.11 O2）
# ═══════════════════════════════════════════════════════════════


class TestKeysContract:
    def test_output_contains_all_six_keys(self) -> None:
        """正常输入下，输出包含全部 6 个固定键。"""
        ds = build_chart_datasets(
            history_data=_history_ok(),
            details=_details(),
            penetration=_penetration(),
            perf_data=[],
        )
        assert set(DATASET_KEYS) == set(ds.keys())

    def test_key_contract_matches_constant(self) -> None:
        """固定键顺序与 DATASET_KEYS 常量一致（§4.11 O2 契约）。"""
        assert list(DATASET_KEYS) == [
            "portfolio_line",
            "drawdown",
            "category_doughnut",
            "industry_bar",
            "penetration_bar",
            "radar",
        ]

    def test_dataset_schema_shape(self) -> None:
        """每张图均遵循通用 schema：labels + datasets[0].degraded。"""
        ds = build_chart_datasets(
            history_data=_history_ok(),
            details=_details(),
            penetration=_penetration(),
            all_metrics={  # 使 radar 非空（否则为空占位）
                "sharpe_ratio": 1.2,
                "calmar_ratio": 0.8,
                "win_rate": {"win_rate": 0.55},
                "turnover_rate": 0.3,
                "portfolio_beta": 0.9,
                "hhi": 0.2,
            },
        )
        for key in DATASET_KEYS:
            chart = ds[key]
            assert "labels" in chart, f"{key} 缺 labels"
            assert isinstance(chart["datasets"], list), f"{key} datasets 应为 list"
            assert chart["datasets"], f"{key} datasets 不应为空"
            assert "degraded" in chart["datasets"][0], f"{key} dataset 缺 degraded"


# ═══════════════════════════════════════════════════════════════
#  净值曲线 + 回撤
# ═══════════════════════════════════════════════════════════════


class TestPortfolioLineAndDrawdown:
    def test_portfolio_line_normalized_to_100(self) -> None:
        """净值曲线归一化至 100 基点（与模板口径一致）。"""
        ds = build_chart_datasets(history_data=_history_ok())
        chart = ds["portfolio_line"]
        assert chart["labels"] == ["2026-01-01", "2026-02-01"]
        assert chart["datasets"][0]["data"] == [100.0, 110.0]  # 110/100*100

    def test_portfolio_line_degraded_flag(self) -> None:
        """status=degraded 时净值曲线标记 degraded=true（→ 虚线）。"""
        hd = _history_ok()
        hd["status"] = "degraded"
        ds = build_chart_datasets(history_data=hd)
        assert ds["portfolio_line"]["datasets"][0]["degraded"] is True

    def test_drawdown_scaled_to_percent(self) -> None:
        """回撤数据 ×100 展示百分比（drawdown_pct 0.02 → 2.0）。"""
        ds = build_chart_datasets(history_data=_history_ok())
        chart = ds["drawdown"]
        assert chart["datasets"][0]["data"] == [0.0, -2.0]

    def test_benchmark_datasets_emitted(self) -> None:
        """基准指数转换为顶层 benchmarks 列表（JS 端单独渲染虚线）。"""
        ds = build_chart_datasets(history_data=_history_ok())
        chart = ds["portfolio_line"]
        labels = [d["label"] for d in chart["datasets"]]
        assert "组合 (as-if)" in labels
        bm_labels = [b["label"] for b in chart["benchmarks"]]
        assert "沪深300" in bm_labels

    def test_history_unavailable_skips_line_and_drawdown(self) -> None:
        """history unavailable 时无净值/回撤图，但其余图仍构建。"""
        ds = build_chart_datasets(
            history_data=_history_unavailable(),
            details=_details(),
            penetration=_penetration(),
        )
        assert "portfolio_line" not in ds
        assert "drawdown" not in ds
        assert "category_doughnut" in ds


# ═══════════════════════════════════════════════════════════════
#  P1 服务端下采样
# ═══════════════════════════════════════════════════════════════


class TestDownsampling:
    def test_le_500_keeps_daily(self) -> None:
        """len(bars) ≤ 500 → 保留日频原样，点数不变。"""
        bars = _gen_bars(500)
        hd = _history_ok(bars)
        ds = build_chart_datasets(history_data=hd)
        assert len(ds["portfolio_line"]["labels"]) == 500
        # 日频首点保留（未聚合）
        assert ds["portfolio_line"]["labels"][0] == "2024-01-01"
        assert len(ds["drawdown"]["labels"]) == 500

    def test_over_500_weekly_aggregate(self) -> None:
        """len(bars) > 500 → 周聚合（取每周最后一条），点数 ≤ ceil(500/5)。"""
        bars = _gen_bars(501)
        hd = _history_ok(bars)
        ds = build_chart_datasets(history_data=hd)
        n = len(ds["portfolio_line"]["labels"])
        assert n < 500
        assert n <= 500 // 5 + 1  # ceil(500/5) = 100 + 1
        # 净值与回撤使用同一聚合结果，X 轴点数一致
        assert len(ds["drawdown"]["labels"]) == n
        assert ds["portfolio_line"]["labels"] == ds["drawdown"]["labels"]

    def test_weekly_aggregate_takes_last_of_week(self) -> None:
        """周聚合取每周最后一条（2024-01-01 周一 → 该周末 01-05 为聚合点）。"""
        bars = _gen_bars(501)
        hd = _history_ok(bars)
        ds = build_chart_datasets(history_data=hd)
        labels = ds["portfolio_line"]["labels"]
        assert labels[0] == "2024-01-05"  # 第 1 周周五（末条）
        # 末点保留：周聚合不清除最后一条真实值
        assert labels[-1] == bars[-1]["date"]

    def test_weekly_too_many_falls_to_monthly(self) -> None:
        """周聚合后点数仍 > 200 → 降级为月聚合（点数 ≤ 200）。"""
        bars = _gen_bars(2000)
        hd = _history_ok(bars)
        ds = build_chart_datasets(history_data=hd)
        n = len(ds["portfolio_line"]["labels"])
        assert n <= 200
        assert n < len(bars) // 4  # 2000 交易日 ≈ 8 年 → 月聚合约 92 点
        assert ds["portfolio_line"]["labels"][0] == "2024-01-31"  # 每月末条

    def test_downsample_does_not_mutate_source(self) -> None:
        """下采样仅改变 Chart.js 数据集，history_data.bars 原值不变。"""
        bars = _gen_bars(501)
        original = [dict(b) for b in bars]  # 深拷贝内容用于比对
        hd = _history_ok(bars)
        build_chart_datasets(history_data=hd)
        assert hd["bars"] == original  # 原 bars 列表元素内容未被改动

    def test_benchmarks_not_downsampled(self) -> None:
        """基准指数不做下采样（保持原样，仅主曲线下采样）。"""
        bars = _gen_bars(501)
        hd = _history_ok(bars)
        ds = build_chart_datasets(history_data=hd)
        chart = ds["portfolio_line"]
        bm = chart["benchmarks"][0]
        assert bm["data"] == [100.0, 105.0]  # 基准原值未聚合


# ═══════════════════════════════════════════════════════════════
#  资产构成 Doughnut（R9 数据最小化）
# ═══════════════════════════════════════════════════════════════


class TestCategoryDoughnut:
    def test_aggregates_by_property(self) -> None:
        """按资产属性聚合市值，只保留有值的类别。"""
        ds = build_chart_datasets(history_data=None, details=_details())
        chart = ds["category_doughnut"]
        assert chart["labels"] == ["股票", "基金", "现金"]
        assert chart["datasets"][0]["data"] == [10000.0, 5000.0, 2000.0]

    def test_r9_privacy_no_cost_shares(self) -> None:
        """R9：只传市值，不含份额/成本等敏感字段。"""
        ds = build_chart_datasets(history_data=None, details=_details())
        import json

        raw = json.dumps(ds["category_doughnut"], ensure_ascii=False)
        assert "cost" not in raw.lower()
        assert "shares" not in raw.lower()

    def test_colors_delegated_to_js_theme(self) -> None:
        """A3（§4.8）：扇区颜色不在 Python 侧硬编码，由 JS ChartTheme.doughnutColors 提供。

        避免 Python/JS 调色板漂移；色盲安全 palette 单一来源在 chart-config.js。
        """
        ds = build_chart_datasets(history_data=None, details=_details())
        dataset = ds["category_doughnut"]["datasets"][0]
        assert "backgroundColor" not in dataset

    def test_infer_property_fallback(self) -> None:
        """DetailRow 无 property 属性时，按代码首字符推断股票/其他。"""
        details = [
            SimpleNamespace(code="600000", name="", market_value=1000.0),  # 股票
            SimpleNamespace(code="CASH", name="货基", market_value=500.0),  # 其他
        ]
        ds = build_chart_datasets(history_data=None, details=details)
        chart = ds["category_doughnut"]
        assert chart["labels"] == ["股票", "其他"]

    def test_infer_property_named_stock_classified_by_code(self) -> None:
        """真实 DetailRow（含名称）按代码前缀分类，股票/基金不落入"其他"。

        _infer_property 仅按代码前缀分类，不依赖 name 是否为空——含名称的
        真实明细行同样正确归类；CASH 等无匹配前缀的代码仍归"其他"（兜底语义，
        见 test_infer_property_fallback）。
        """
        details = [
            SimpleNamespace(code="600000", name="浦发银行", market_value=10000.0),
            SimpleNamespace(code="510300", name="沪深300ETF", market_value=5000.0),
            SimpleNamespace(code="CASH", name="货币基金", market_value=2000.0),
        ]
        ds = build_chart_datasets(history_data=None, details=details)
        chart = ds["category_doughnut"]
        assert chart["labels"] == ["股票", "基金", "其他"]
        assert chart["datasets"][0]["data"] == [10000.0, 5000.0, 2000.0]

    def test_category_doughnut_prefers_cat_data(self) -> None:
        """回归：传入 cat_data（持仓分类表权威数据）时，饼图优先取 cat_data。

        cat_data 与持仓分类表同源（_categorize_holding），避免 details 兜底
        分类偏差导致饼图与表格不一致。
        """
        cat_data = [
            {"property": "股票", "sub_mv": 8000.0},
            {"property": "基金", "sub_mv": 4000.0},
        ]
        ds = build_chart_datasets(
            history_data=None,
            cat_data=cat_data,
            details=[SimpleNamespace(code="600000", name="浦发银行", market_value=99999.0)],
        )
        chart = ds["category_doughnut"]
        assert chart["labels"] == ["股票", "基金"]
        assert chart["datasets"][0]["data"] == [8000.0, 4000.0]

    def test_category_doughnut_from_cat_data_aggregation(self) -> None:
        """cat_data 内同 property 多组聚合 sub_mv，按 _CATEGORY_ORDER 排序。"""
        from src.python.report.chart_data_builder import _build_category_doughnut_dataset

        cat_data = [
            {"property": "基金", "sub_mv": 3000.0},
            {"property": "股票", "sub_mv": 5000.0},
            {"property": "基金", "sub_mv": 2000.0},  # 同 property 第二组 → 聚合
            {"property": "现金", "sub_mv": 1000.0},
        ]
        chart = _build_category_doughnut_dataset(None, cat_data)
        assert chart["labels"] == ["股票", "基金", "现金"]
        assert chart["datasets"][0]["data"] == [5000.0, 5000.0, 1000.0]

    def test_category_doughnut_from_cat_data_empty(self) -> None:
        """cat_data 为空/None → 空数据集（不崩溃，图表显示"无数据"）。"""
        from src.python.report.chart_data_builder import _build_category_doughnut_dataset

        assert _build_category_doughnut_dataset(None, None) == {"labels": [], "datasets": []}
        assert _build_category_doughnut_dataset(None, []) == {"labels": [], "datasets": []}

    def test_empty_details_returns_empty(self) -> None:
        """无明细时返回空数据集（空数组→无数据）。"""
        ds = build_chart_datasets(history_data=None, details=None)
        assert ds["category_doughnut"] == {"labels": [], "datasets": []}


# ═══════════════════════════════════════════════════════════════
#  行业分布 + 穿透 TOP10
# ═══════════════════════════════════════════════════════════════


class TestIndustryAndPenetration:
    def test_industry_bar_top10_aggregate(self) -> None:
        """行业分布按 sector 聚合市值，未分类归"其他"。"""
        ds = build_chart_datasets(history_data=None, penetration=_penetration())
        chart = ds["industry_bar"]
        assert chart["labels"] == ["白酒", "新能源", "其他"]
        assert chart["datasets"][0]["data"] == [3000.0, 2000.0, 1000.0]

    def test_penetration_bar_ranked_order(self) -> None:
        """穿透 TOP10 按原排名顺序展示市值。"""
        ds = build_chart_datasets(history_data=None, penetration=_penetration())
        chart = ds["penetration_bar"]
        assert chart["labels"] == ["贵州茅台", "宁德时代", "未分类标的"]
        assert chart["datasets"][0]["data"] == [3000.0, 2000.0, 1000.0]

    def test_penetration_none_returns_empty(self) -> None:
        """penetration 缺失时两图均返回空数据集（penetration=None → 占位）。"""
        ds = build_chart_datasets(history_data=None, penetration=None)
        assert ds["industry_bar"] == {"labels": [], "datasets": []}
        assert ds["penetration_bar"] == {"labels": [], "datasets": []}

    def test_industry_bar_total_matches_penetration_mv(self) -> None:
        """行业市值占比与穿透模块计算结果一致。

        行业聚合后各行业市值之和 == 穿透 top10 总市值，保证图表口径与穿透模块一致。
        """
        ds = build_chart_datasets(history_data=None, penetration=_penetration())
        chart = ds["industry_bar"]
        total = sum(chart["datasets"][0]["data"])
        pen_total = sum(float(e["mv"]) for e in _penetration()["top10"])
        assert total == pytest.approx(pen_total)

    def test_industry_bar_max_10_sectors(self) -> None:
        """行业分布最多展示 10 个行业（按市值降序截断）。"""
        top10 = [{"rank": i, "name": f"标的{i}", "sector": f"行业{i}", "mv": float(i)} for i in range(1, 15)]
        ds = build_chart_datasets(history_data=None, penetration=_penetration(top10))
        chart = ds["industry_bar"]
        assert len(chart["labels"]) == 10
        assert chart["labels"][0] == "行业14", "市值最大的行业应排在首位"
        assert chart["labels"][-1] == "行业5", "超过 10 个行业时应截断尾部"

    def test_penetration_bar_lt3_entries_still_renders(self) -> None:
        """穿透品种 < 3 时仍渲染图表（品种不足不阻断渲染）。"""
        small = _penetration(
            [
                {"rank": 1, "name": "贵州茅台", "sector": "白酒", "mv": 5000.0},
                {"rank": 2, "name": "宁德时代", "sector": "新能源", "mv": 2000.0},
            ]
        )
        ds = build_chart_datasets(history_data=None, penetration=small)
        chart = ds["penetration_bar"]
        assert chart["labels"] == ["贵州茅台", "宁德时代"]
        assert chart["datasets"][0]["data"] == [5000.0, 2000.0]


# ═══════════════════════════════════════════════════════════════
#  量化指标 Radar（R12 三级降级）
# ═══════════════════════════════════════════════════════════════


class TestRadar:
    _ALL_METRICS = {
        "sharpe_ratio": 1.2,
        "calmar_ratio": 0.8,
        "win_rate": {"win_rate": 0.55},
        "turnover_rate": 0.3,
        "portfolio_beta": 0.9,
        "hhi": 0.2,
    }

    def test_radar_priority_all_metrics(self) -> None:
        """优先级 1：all_metrics 提供 6 个指标轴。"""
        ds = build_chart_datasets(history_data=_history_ok(), all_metrics=self._ALL_METRICS)
        chart = ds["radar"]
        assert chart["labels"] == ["夏普比率", "卡玛比率", "胜率", "换手率", "组合 Beta", "集中度 HHI"]
        # win_rate dict → 提取 0.55
        assert chart["datasets"][0]["data"][2] == 0.55

    def test_radar_fallback_risk_metrics(self) -> None:
        """优先级 2：无 all_metrics 时退回 risk_metrics 3 基本字段。"""
        rm = {"annualized_volatility": 0.18, "max_drawdown_pct": -0.05, "total_return_pct": 0.1}
        ds = build_chart_datasets(history_data=_history_ok(), risk_metrics=rm)
        chart = ds["radar"]
        assert chart["labels"] == ["年化波动率", "最大回撤", "累计收益"]
        assert chart["datasets"][0]["data"] == [0.18, -0.05, 0.1]

    def test_radar_fallback_history(self) -> None:
        """优先级 3：双路径均可从 history_data 提取 3 基本轴。"""
        hd = _history_ok()
        hd["annualized_volatility"] = 0.18
        hd["max_drawdown_pct"] = -0.05
        hd["total_return_pct"] = 0.1
        ds = build_chart_datasets(history_data=hd)
        chart = ds["radar"]
        assert chart["labels"] == ["年化波动率", "最大回撤", "累计收益"]
        assert chart["datasets"][0]["data"] == [0.18, -0.05, 0.1]

    def test_radar_history_without_metrics_empty(self) -> None:
        """history_data 无指标字段且无其他源时，radar 返回空。"""
        ds = build_chart_datasets(history_data=_history_ok())
        assert ds["radar"] == {"labels": [], "datasets": []}

    def test_radar_none_to_na_not_zero(self) -> None:
        """None 指标 → "N/A"（非 0），Flag 关闭或缺失显示 N/A。"""
        am = dict(self._ALL_METRICS)
        am["hhi"] = None  # 关闭的指标
        ds = build_chart_datasets(history_data=None, all_metrics=am)
        chart = ds["radar"]
        assert chart["datasets"][0]["data"][-1] == "N/A"

    def test_radar_independent_of_history(self) -> None:
        """R12：history unavailable 但 all_metrics 有值时 radar 仍渲染。"""
        ds = build_chart_datasets(
            history_data=_history_unavailable(),
            all_metrics=self._ALL_METRICS,
        )
        assert "portfolio_line" not in ds
        assert "radar" in ds
        assert ds["radar"]["labels"] == [
            "夏普比率",
            "卡玛比率",
            "胜率",
            "换手率",
            "组合 Beta",
            "集中度 HHI",
        ]

    def test_radar_flag_off_shows_na(self) -> None:
        """§6.6 F1：metrics_sharpe=False → 该指标输出 "N/A"（非 0）。"""
        ds = build_chart_datasets(
            history_data=None,
            all_metrics=self._ALL_METRICS,
            metric_flags={"metrics_sharpe": False},
        )
        chart = ds["radar"]
        assert chart["labels"][0] == "夏普比率"
        assert chart["datasets"][0]["data"][0] == "N/A"
        # 其余轴不受影响
        assert chart["datasets"][0]["data"][1] == 0.8

    def test_radar_flag_map_all_axes(self) -> None:
        """§6.6 F1：6 个雷达轴均被 metrics_* Flag 覆盖（映射完整）。"""
        flags = {
            "metrics_sharpe": False,
            "metrics_calmar": False,
            "metrics_winrate": False,
            "metrics_turnover": False,
            "metrics_beta": False,
            "metrics_hhi": False,
        }
        ds = build_chart_datasets(
            history_data=None,
            all_metrics=self._ALL_METRICS,
            metric_flags=flags,
        )
        chart = ds["radar"]
        assert chart["datasets"][0]["data"] == ["N/A"] * 6

    def test_radar_all_na_placeholder_axes_kept(self) -> None:
        """全 N/A → 轴保留，数据 "N/A"（§6.6：Flag 全关仍显示轴标签）。"""
        flags = {
            f: False
            for f in (
                "metrics_sharpe",
                "metrics_calmar",
                "metrics_winrate",
                "metrics_turnover",
                "metrics_beta",
                "metrics_hhi",
            )
        }
        ds = build_chart_datasets(
            history_data=_history_ok(),
            all_metrics=self._ALL_METRICS,
            metric_flags=flags,
        )
        chart = ds["radar"]
        assert chart["labels"] == ["夏普比率", "卡玛比率", "胜率", "换手率", "组合 Beta", "集中度 HHI"]
        assert chart["datasets"][0]["data"] == ["N/A"] * 6

    def test_radar_degraded_note_risk_metrics(self) -> None:
        """降级标注：仅 risk_metrics 可用时 note="仅限基础指标" + degraded=True。"""
        rm = {"annualized_volatility": 0.18, "max_drawdown_pct": -0.05, "total_return_pct": 0.1}
        ds = build_chart_datasets(history_data=_history_ok(), risk_metrics=rm)
        chart = ds["radar"]
        assert chart["datasets"][0]["degraded"] is True
        assert chart["datasets"][0]["note"] == "仅限基础指标"

    def test_radar_degraded_note_history(self) -> None:
        """降级标注：仅 history_data 兜底时 note="仅限基础指标"（both 路径）。"""
        hd = _history_ok()
        hd["annualized_volatility"] = 0.18
        hd["max_drawdown_pct"] = -0.05
        hd["total_return_pct"] = 0.1
        ds = build_chart_datasets(history_data=hd)
        chart = ds["radar"]
        assert chart["datasets"][0]["degraded"] is True
        assert chart["datasets"][0]["note"] == "仅限基础指标"

    def test_radar_full_no_note(self) -> None:
        """all_metrics 全量路径无降级标注（degraded=False 且无 note）。"""
        ds = build_chart_datasets(
            history_data=_history_ok(),
            all_metrics=self._ALL_METRICS,
        )
        chart = ds["radar"]
        assert chart["datasets"][0]["degraded"] is False
        assert "note" not in chart["datasets"][0]


# ═══════════════════════════════════════════════════════════════
#  R11 单图脏数据隔离
# ═══════════════════════════════════════════════════════════════


class TestR11Isolation:
    def test_dirty_history_skips_only_line(self) -> None:
        """净值 bars 缺 total_value 键 → 仅 portfolio_line 被跳过，其余图正常。"""
        hd = _history_ok()
        hd["bars"] = [{"date": "2026-01-01"}]  # 缺 total_value → KeyError
        ds = build_chart_datasets(
            history_data=hd,
            details=_details(),
            penetration=_penetration(),
        )
        assert "portfolio_line" not in ds  # 单图被隔离跳过
        assert "drawdown" in ds  # drawdown 用 .get() 不受影响
        assert "category_doughnut" in ds
        assert "industry_bar" in ds
        assert "penetration_bar" in ds

    def test_dirty_penetration_skips_only_bars(self) -> None:
        """penetration top10 含 None 条目 → 两个穿透图被隔离跳过，其余正常。"""
        top10 = [None]  # entry.get → AttributeError（穿透图特有脏数据）
        ds = build_chart_datasets(
            history_data=_history_ok(),
            details=_details(),
            penetration={"top10": top10},
        )
        assert "industry_bar" not in ds
        assert "penetration_bar" not in ds
        assert "portfolio_line" in ds
        assert "drawdown" in ds
        assert "category_doughnut" in ds

    def test_radar_all_invalid_keeps_axes_with_na(self) -> None:
        """指标值全部无效 → 轴保留，数据标记 "N/A"（§6.6：缺失显示 N/A 而非跳过）。"""
        rm = {"annualized_volatility": "bad", "max_drawdown_pct": "bad", "total_return_pct": "bad"}
        ds = build_chart_datasets(history_data=_history_ok(), risk_metrics=rm)
        chart = ds["radar"]
        assert chart["labels"] == ["年化波动率", "最大回撤", "累计收益"]
        assert chart["datasets"][0]["data"] == ["N/A", "N/A", "N/A"]


# ═══════════════════════════════════════════════════════════════
#  组合演进图表数据裁剪（避免整包序列化）
# ═══════════════════════════════════════════════════════════════


class TestEvolutionChartData:
    """build_evolution_chart_data 专用裁剪测试。"""

    def _evo(self, **extra) -> dict:
        d = {
            "available": True,
            "snapshot_count": 5,
            "min_snapshots": 3,
            "periods": ["07-01", "07-02"],
            "total_value": [100000.0, 110000.0],
            "total_cost": [90000.0, 90000.0],
            "total_pnl": [10000.0, 20000.0],
            "holding_counts": [2, 3],
            "account_flows": {"账户A": [60.0, 50.0]},
            "hhi": [0.52, 0.58],
            "top_holdings": [
                {"code": "a", "name": "资产A", "weights": [60.0, 70.0], "present_count": 2},
                {"code": "b", "name": "资产B", "weights": [40.0, 30.0], "present_count": 2},
            ],
            "reason": "",
        }
        d.update(extra)
        return d

    def test_trim_only_chart_keys(self) -> None:
        """available=True → 仅保留图表消费字段，剔除表格字段。"""
        payload = build_evolution_chart_data(self._evo())
        assert set(payload.keys()) == {"periods", "total_value", "total_pnl", "hhi", "top_holdings"}
        assert payload["periods"] == ["07-01", "07-02"]
        assert "total_cost" not in payload
        assert "holding_counts" not in payload
        assert "account_flows" not in payload
        assert "reason" not in payload

    def test_top_holdings_trimmed_to_name_code_weights(self) -> None:
        """top_holdings 每项仅保留 name/code/weights（图表 JS 消费字段）。"""
        payload = build_evolution_chart_data(self._evo())
        assert payload["top_holdings"] == [
            {"code": "a", "name": "资产A", "weights": [60.0, 70.0]},
            {"code": "b", "name": "资产B", "weights": [40.0, 30.0]},
        ]
        assert "present_count" not in payload["top_holdings"][0]

    def test_none_returns_none(self) -> None:
        """evolution_data=None → None（章节不可见，模板不输出数据段）。"""
        assert build_evolution_chart_data(None) is None

    def test_unavailable_returns_none(self) -> None:
        """available=False → None（降级占位，模板不输出数据段）。"""
        assert build_evolution_chart_data(self._evo(available=False, reason="快照不足")) is None

    def test_does_not_mutate_source(self) -> None:
        """裁剪不改动原始 evolution_data（不可变）。"""
        src = self._evo()
        before = dict(src)
        build_evolution_chart_data(src)
        assert src == before
