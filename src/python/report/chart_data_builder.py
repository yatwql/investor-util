"""Chart.js 数据预处理器 — 将原始数据转换为 Chart.js 数据集格式。

该模块在 Python 侧完成 6 张图表的数据格式转换，使 JS 端（chart-init.js）
只需渲染已格式化数据。数据经 template context 传递（`chart_datasets`），
**不写 `_ENV.globals`**（C14 合规，不新增 Schema — C19 豁免）。

契约（§4.11 O2/§4.12）：6 固定键 portfolio_line/drawdown/category_doughnut/
industry_bar/penetration_bar/radar；空 labels/datasets → "无数据"；degraded → 虚线；
行数预算 ≤400 行（O4）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.report.downsample import downsample_bars

logger = logging.getLogger("invest")

# ── 固定键契约（§4.11 O2）────────────────────────────────
DATASET_KEYS = (
    "portfolio_line",
    "drawdown",
    "category_doughnut",
    "industry_bar",
    "penetration_bar",
    "radar",
)

# ── 资产构成 Doughnut 键序（与 category.py _PROP_ORDER 一致）─
# 扇区颜色不在 Python 侧硬编码——由 chart-config.js ChartTheme.doughnutColors
# 统一提供（A3 色盲安全 palette，§4.8），避免 Python/JS 调色板漂移。
_CATEGORY_ORDER = ("股票", "基金", "债券", "现金", "其他")

# ── 雷达轴 → metrics_* Feature Flag 映射（§6.6 F1）──────
# 子开关逐个过滤雷达轴：Flag 关闭 → 该轴值转为 "N/A"（非 0）。
_RADAR_FLAG_MAP = {
    "sharpe_ratio": "metrics_sharpe",
    "calmar_ratio": "metrics_calmar",
    "win_rate": "metrics_winrate",
    "turnover_rate": "metrics_turnover",
    "portfolio_beta": "metrics_beta",
    "hhi": "metrics_hhi",
}

# 降级雷达的 3 个基本轴（risk_metrics / history_data 兜底共用）
_BASIC_RADAR_AXES = (
    ("annualized_volatility", "年化波动率"),
    ("max_drawdown_pct", "最大回撤"),
    ("total_return_pct", "累计收益"),
)


def build_chart_datasets(
    history_data: dict | None,
    cat_data: list | None = None,
    penetration: dict | None = None,
    perf_data: list | None = None,
    details: list | None = None,
    risk_metrics: dict | None = None,
    all_metrics: dict | None = None,
    metric_flags: dict | None = None,
) -> dict:
    """构建 6 张图的数据集，返回 dict → template context（C14 合规）。

    关键数据源：risk_metrics（5 基本字段，full）/ all_metrics（14 项全量，full）/
    metric_flags（§6.6 F1，关闭 → "N/A"）；both 路径传入 None 时，radar 从
    history_data 提取 3 个基本轴兜底。
    ⚠ R11：每个 dataset 独立 try/except——单图脏数据失败仅跳过该图，不影响整份报告。
    """
    datasets: dict[str, Any] = {}

    # portfolio_line + drawdown 依赖 history_data（ok/degraded）
    if history_data and history_data.get("status") != "unavailable":
        try:
            datasets["portfolio_line"] = _build_portfolio_line_dataset(history_data)
        except Exception as e:  # R11：捕获一切异常，单图失败仅跳过该图
            logger.warning("[chart] portfolio_line 构建失败，跳过该图: %s", e)
        try:
            datasets["drawdown"] = _build_drawdown_dataset(history_data)
        except Exception as e:  # R11：捕获一切异常，单图失败仅跳过该图
            logger.warning("[chart] drawdown 构建失败，跳过该图: %s", e)

    # category_doughnut + industry_bar + penetration_bar
    try:
        datasets["category_doughnut"] = _build_category_doughnut_dataset(details, cat_data)
    except Exception as e:  # R11：捕获一切异常，单图失败仅跳过该图
        logger.warning("[chart] category_doughnut 构建失败，跳过该图: %s", e)
    try:
        datasets["industry_bar"] = _build_industry_bar_dataset(penetration)
    except Exception as e:  # R11：捕获一切异常，单图失败仅跳过该图
        logger.warning("[chart] industry_bar 构建失败，跳过该图: %s", e)
    try:
        datasets["penetration_bar"] = _build_penetration_bar_dataset(penetration)
    except Exception as e:  # R11：捕获一切异常，单图失败仅跳过该图
        logger.warning("[chart] penetration_bar 构建失败，跳过该图: %s", e)

    # ⚠ R12：radar 放在所有条件之外，仅依赖 all_metrics / risk_metrics / history_data
    # 三源独立判断——history_data 不可用但 all_metrics 有值时，radar 仍应渲染。
    try:
        datasets["radar"] = _build_radar_dataset(history_data, all_metrics, risk_metrics, metric_flags)
    except Exception as e:  # R11：radar 失败 → 空占位，不影响其他图
        logger.warning("[chart] radar 构建失败，跳过该图: %s", e)
        datasets["radar"] = _empty_dataset()

    return datasets


def _empty_dataset() -> dict:
    """空数据集占位（§4.12 空值语义：空 labels/datasets → "无数据"）。"""
    return {"labels": [], "datasets": []}


def _build_portfolio_line_dataset(history_data: dict) -> dict:
    """净值趋势 Line：主曲线 + 基准线（P1 服务端下采样）。"""
    bars = downsample_bars(history_data.get("bars") or [])
    status = history_data.get("status")
    labels = [b["date"] for b in bars]
    # 归一化组合至 100 基点，与基准指数同量纲比较（与模板口径一致）
    values = [b["total_value"] for b in bars]
    if values:
        first = values[0]
        if first:
            values = [round(v / first * 100, 2) for v in values]
    dataset = {
        "label": "组合 (as-if)",
        "data": values,
        "borderColor": "var(--chart-primary)",
        "degraded": status == "degraded",
    }
    return {
        "labels": labels,
        "datasets": [dataset],
        "benchmarks": _build_benchmark_datasets(history_data.get("benchmarks") or []),
    }


def _build_benchmark_datasets(benchmarks: list) -> list:
    """基准指数数据集（归一化至 100，虚线）。"""
    result: list[dict] = []
    colors = ("#CC0000", "#E68A00", "#2E7D32")
    for i, bm in enumerate(benchmarks):
        bm_bars = bm.get("bars") or []
        if not bm_bars:
            continue
        values = [b["value"] for b in bm_bars if "value" in b]
        if not values:
            continue
        result.append(
            {
                "label": bm.get("name", f"基准{i + 1}"),
                "data": values,
                "borderColor": colors[i % len(colors)],
                "degraded": False,
            }
        )
    return result


def _build_drawdown_dataset(history_data: dict) -> dict:
    """最大回撤 Line：回撤百分比（已 ×100），透明红填充 + 基准回撤。

    复用净值数据源，使用同一下采样结果（与净值图 X 轴点数一致，§4.9）。
    """
    bars = downsample_bars(history_data.get("bars") or [])
    status = history_data.get("status")
    labels = [b["date"] for b in bars]
    # bars 字段为 drawdown_pct，模板以 b.drawdown_pct ×100 展示为百分比
    values = [b.get("drawdown_pct", 0) * 100 for b in bars]
    dataset = {
        "label": "组合回撤",
        "data": values,
        "borderColor": "var(--chart-danger)",
        "backgroundColor": "var(--chart-danger-transparent)",
        "degraded": status == "degraded",
    }
    return {
        "labels": labels,
        "datasets": [dataset],
        "benchmarks": _build_benchmark_drawdowns(history_data.get("benchmarks") or []),
    }


def _build_benchmark_drawdowns(benchmarks: list) -> list:
    """基准回撤数据集（从归一化值计算逐日回撤，与模板口径一致）。"""
    result: list[dict] = []
    colors = ("#9CA3AF", "#B0BEC5", "#90A4AE")
    for i, bm in enumerate(benchmarks):
        bm_bars = bm.get("bars") or []
        if not bm_bars:
            continue
        values = []
        peak = None
        for b in bm_bars:
            v = b.get("value")
            if v is None:
                continue
            if peak is None or v > peak:
                peak = v
            if peak:
                values.append(round(-(peak - v) / peak * 100, 2))
        if not values:
            continue
        result.append(
            {
                "label": bm.get("name", f"基准{i + 1}"),
                "data": values,
                "borderColor": colors[i % len(colors)],
                "degraded": False,
            }
        )
    return result


def _build_category_doughnut_dataset(details: list | None, cat_data: list | None = None) -> dict:
    """资产构成 Doughnut：按资产属性（property）聚合市值。

    双数据源：
    - cat_data（持仓分类表数据，_categorize_holding 权威分类，优先）
      → 按 property 聚合 sub_mv，保证饼图与表格完全一致（DetailRow 无 property 字段）。
    - details（市值明细兜底）→ 按 property 属性聚合 market_value，无则 _infer_property。
    数据最小化（R9 S4）：只传市值，不含份额/成本等敏感字段。
    扇区颜色由 JS 端 ChartTheme.doughnutColors 提供（A3 色盲安全 palette，§4.8）。
    """
    total_by_prop: dict[str, float] = {}
    if cat_data is not None:
        for group in cat_data:
            prop = str(group.get("property") or "其他")
            total_by_prop[prop] = total_by_prop.get(prop, 0.0) + float(group.get("sub_mv", 0) or 0)
    elif details:
        for d in details:
            prop = getattr(d, "property", None) or _infer_property(d)
            total_by_prop[prop] = total_by_prop.get(prop, 0.0) + float(getattr(d, "market_value", 0) or 0)
    else:
        return _empty_dataset()

    labels = [p for p in _CATEGORY_ORDER if total_by_prop.get(p, 0) > 0]
    values = [round(total_by_prop[p], 2) for p in labels]
    if not labels:
        return _empty_dataset()

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "资产市值",
                "data": values,
                "degraded": False,
            }
        ],
    }


def _infer_property(d: Any) -> str:
    """兜底：DetailRow 无 property 属性时，按代码前缀推断资产属性（尽力而为）。"""
    code = str(getattr(d, "code", "") or "").strip()
    if code[:1] in ("6", "0", "3"):
        return "股票"
    if code[:1] in ("5", "1"):
        return "基金"
    return "其他"


def _build_industry_bar_dataset(penetration: dict | None) -> dict:
    """行业分布 Horizontal Bar：penetration top10 → 按 sector 聚合市值。

    聚合键 = penetration entry.sector（classify_sector/sector_api，无归属归"其他"）。
    """
    top10 = (penetration or {}).get("top10") or []
    if not top10:
        return _empty_dataset()

    sector_mv: dict[str, float] = {}
    for entry in top10:
        # None / 空字符串 / 纯空白 → 归入"其他"（边缘场景，见 test_chart_data_builder_edge.py）
        sector = (entry.get("sector") or "").strip() or "其他"
        mv = float(entry.get("mv", 0) or 0)
        sector_mv[sector] = sector_mv.get(sector, 0.0) + mv

    # 按市值降序，最多 10 个行业
    ordered = sorted(sector_mv.items(), key=lambda x: x[1], reverse=True)[:10]
    labels = [s for s, _ in ordered]
    values = [round(v, 2) for _, v in ordered]

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "行业市值",
                "data": values,
                "borderColor": "var(--chart-primary)",
                "degraded": False,
            }
        ],
    }


def _build_penetration_bar_dataset(penetration: dict | None) -> dict:
    """穿透 TOP10 Bar：penetration top10 → 市值（按排名顺序，最多 10 个）。"""
    top10 = (penetration or {}).get("top10") or []
    if not top10:
        return _empty_dataset()

    labels = [e.get("name", f"标的{i + 1}") for i, e in enumerate(top10)]
    values = [round(float(e.get("mv", 0) or 0), 2) for e in top10]

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "穿透市值",
                "data": values,
                # 颜色单一来源在 JS/CSS 层：穿透柱状图用橙（--chart-bar-2），
                # 与行业分布柱状图（--chart-primary 蓝）明显区分。
                "borderColor": "var(--chart-bar-2)",
                "degraded": False,
            }
        ],
    }


def _build_radar_dataset(
    history_data: dict | None,
    all_metrics: dict | None,
    risk_metrics: dict | None,
    metric_flags: dict | None = None,
) -> dict:
    """量化指标 Radar — 三级降级优先级（R12）：

    1. all_metrics（14 项全量，仅 full 路径）
    2. risk_metrics（5 基本字段，仅 full 路径）
    3. history_data 内部提取（annualized_volatility / max_drawdown_pct / total_return_pct，
       双路径均有——确保 both 路径也能显示 3 个基本轴）

    数据最小化（R9）：只传指标数值，不含内部明细。
    Flag 过滤（§6.6 F1）：metrics_* 关闭 → 该轴值转为 "N/A"（非 0）。
    降级标注：risk_metrics / history_data 兜底时 datasets[0]["note"]="仅限基础指标"。
    """
    degraded = False
    if all_metrics:
        # all_metrics 全量轴，逐轴应用 metrics_* Flag 过滤
        axes = []
        for key, name in (
            ("sharpe_ratio", "夏普比率"),
            ("calmar_ratio", "卡玛比率"),
            ("win_rate", "胜率"),
            ("turnover_rate", "换手率"),
            ("portfolio_beta", "组合 Beta"),
            ("hhi", "集中度 HHI"),
        ):
            value = all_metrics.get(key)
            if key == "win_rate":
                value = _extract_rate(value)
            flag = _RADAR_FLAG_MAP.get(key)
            if flag and metric_flags is not None and not metric_flags.get(flag, True):
                value = None  # Flag 关闭 → N/A
            axes.append((key, name, value))
    else:
        # risk_metrics / history_data 兜底 → 3 个基本轴（降级标注）
        source = risk_metrics or history_data
        if not source:
            return _empty_dataset()
        axes = [(key, name, source.get(key)) for key, name in _BASIC_RADAR_AXES]
        if not any(v is not None for _, _, v in axes):
            return _empty_dataset()
        degraded = True

    # 保留全部轴；None → "N/A"（非 0，§4.12 / §6.6 契约：Flag 关闭或缺失显示 N/A）
    labels = [name for _, name, _ in axes]
    values = [float(value) if _is_valid_metric(value) else "N/A" for _, _, value in axes]

    if not labels:
        return _empty_dataset()

    dataset: dict[str, Any] = {
        "label": "量化指标",
        "data": values,
        "borderColor": "var(--chart-primary)",
        "degraded": degraded,
    }
    if degraded:
        dataset["note"] = "仅限基础指标"

    return {"labels": labels, "datasets": [dataset]}


def _extract_rate(win_rate: Any) -> float | None:
    """从 win_rate() 返回的 dict 提取 win_rate 值（0~1）。"""
    if isinstance(win_rate, dict):
        return win_rate.get("win_rate")
    return win_rate


def _is_valid_metric(value: Any) -> bool:
    """指标值是否有效（float/int 且非 None）。"""
    return isinstance(value, (int, float)) and value is not None
