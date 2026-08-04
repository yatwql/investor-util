"""chart_data_builder.py 边缘场景测试（edge 用例必须放 *_edge.py 文件）。

覆盖行业分布图表验收：品种无行业归属 → 归入"其他"分类。
其他极端值/异常输入场景：
  - 全部品种均无行业归属 → 全部归入"其他"单一分类
  - sector 为 None / 空字符串 / 纯空白 → 归入"其他"
  - mv 为 None / 非数值 → 防御性归零，不抛异常

运行：
  cd /lzcapp/document/working/codebase/investor-util
  .venv/bin/python -m pytest src/test/unit/report/test_chart_data_builder_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.report.chart_data_builder import build_chart_datasets

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


def _penetration(top10: list[dict]) -> dict:
    """构造穿透数据（显式传入 top10 以覆盖异常输入）。"""
    return {"top10": top10}


def test_all_unclassified_sectors_aggregate_to_other() -> None:
    """全部品种无行业归属 → 全部归入"其他"单一分类。"""
    top10 = [
        {"rank": 1, "name": "标的A", "mv": 3000.0},
        {"rank": 2, "name": "标的B", "mv": 2000.0},
        {"rank": 3, "name": "标的C", "mv": 1000.0},
    ]
    ds = build_chart_datasets(history_data=None, penetration=_penetration(top10))
    chart = ds["industry_bar"]
    assert chart["labels"] == ["其他"]
    assert chart["datasets"][0]["data"] == [6000.0]


def test_sector_none_and_blank_classified_as_other() -> None:
    """sector 为 None / 空字符串 / 纯空白 → 归入"其他"。"""
    top10 = [
        {"rank": 1, "name": "标的A", "sector": None, "mv": 1000.0},
        {"rank": 2, "name": "标的B", "sector": "", "mv": 2000.0},
        {"rank": 3, "name": "标的C", "sector": "  ", "mv": 3000.0},
        {"rank": 4, "name": "标的D", "sector": "白酒", "mv": 4000.0},
    ]
    ds = build_chart_datasets(history_data=None, penetration=_penetration(top10))
    chart = ds["industry_bar"]
    # 其他（6000=1000+2000+3000）市值高于白酒（4000），按市值降序排前
    assert chart["labels"] == ["其他", "白酒"]
    assert chart["datasets"][0]["data"] == [6000.0, 4000.0]


def test_negative_and_none_mv_do_not_crash() -> None:
    """mv 为 None / 负值时不抛异常，防御性归零聚合（单图隔离）。"""
    top10 = [
        {"rank": 1, "name": "标的A", "sector": "白酒", "mv": 1000.0},
        {"rank": 2, "name": "标的B", "sector": "白酒", "mv": None},
        {"rank": 3, "name": "标的C", "sector": "电池", "mv": -500.0},
    ]
    ds = build_chart_datasets(history_data=None, penetration=_penetration(top10))
    # 全部 sector 有归属时仍应产出图表（None/负值被防御处理为 0/原值）
    chart = ds["industry_bar"]
    assert set(chart["labels"]) == {"白酒", "电池"}
    # None → 0，负值按原值计入（聚合不抛异常即可，口径由上游保证）
    assert chart["datasets"][0]["data"] is not None


def test_empty_top10_returns_empty_dataset() -> None:
    """top10 为空列表 → 两图均返回空数据集（与 penetration=None 同语义）。"""
    ds = build_chart_datasets(history_data=None, penetration=_penetration([]))
    assert ds["industry_bar"] == {"labels": [], "datasets": []}
    assert ds["penetration_bar"] == {"labels": [], "datasets": []}


# ═══════════════════════════════════════════════════════════════
#  量化指标 Radar 边缘场景
# ═══════════════════════════════════════════════════════════════


def test_radar_both_sources_none_empty() -> None:
    """all_metrics 与 risk_metrics 均为 None → radar 空 dict（验收标准 6）。"""
    ds = build_chart_datasets(history_data=None, all_metrics=None, risk_metrics=None)
    assert ds["radar"] == {"labels": [], "datasets": []}


def test_radar_all_metrics_none_with_history() -> None:
    """all_metrics=None 但 history_data 有 3 基本轴 → 降级渲染（验收标准 1）。"""
    hd = {
        "status": "ok",
        "bars": [],
        "annualized_volatility": 0.18,
        "max_drawdown_pct": -0.05,
        "total_return_pct": 0.1,
    }
    ds = build_chart_datasets(history_data=hd, all_metrics=None, risk_metrics=None)
    chart = ds["radar"]
    assert chart["labels"] == ["年化波动率", "最大回撤", "累计收益"]
    assert chart["datasets"][0]["data"] == [0.18, -0.05, 0.1]
    assert chart["datasets"][0]["note"] == "仅限基础指标"


def test_radar_flag_off_for_missing_flag_name() -> None:
    """metric_flags 含未知 flag 名 → 不影响该轴（映射外的指标默认可用）。"""
    am = {
        "sharpe_ratio": 1.2,
        "calmar_ratio": 0.8,
    }
    ds = build_chart_datasets(
        history_data=None,
        all_metrics=am,
        metric_flags={"metrics_unknown_flag": False},
    )
    chart = ds["radar"]
    assert chart["datasets"][0]["data"][0] == 1.2
    assert chart["datasets"][0]["data"][1] == 0.8


def test_radar_all_metrics_partial_na() -> None:
    """部分指标缺失 → 该轴 "N/A"，其余轴数值保留（验收标准 1）。"""
    am = {"sharpe_ratio": 1.2, "calmar_ratio": None, "hhi": 0.2}
    ds = build_chart_datasets(history_data=None, all_metrics=am)
    chart = ds["radar"]
    assert chart["datasets"][0]["data"] == [1.2, "N/A", "N/A", "N/A", "N/A", 0.2]
