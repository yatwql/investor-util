"""pipeline_data 组装构建器 — 统一数据合并点 + 类型断言。

职责：
  1. 接收来自各数据准备阶段的结构化数据
  2. 合并到统一的 pipeline_data 字典
  3. 执行类型断言（C19 契约）
  4. 为下游（LLM prompt / Excel 摘要）提供稳定的入口

A 通道（pipeline_data）流向：
  capture_snapshot() → pipeline_data_builder.build() → Excel / LLM

B 通道（prep）流向：
  prepare_report_data() → pipeline_data_builder.build_prep() → LLM / Excel

C19 约束：所有键必须先在 data-channels-schema.md 中注册。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("invest")

# ── 已知 pipeline_data 顶层键（用于 build() 类型校验） ──

_PIPELINE_DATA_KNOWN_KEYS: set[str] = {
    "diff",
    "data_degradation",
    "risk_metrics",
    "portfolio_daily_returns",
    "factor_exposure",
    "correlation_data",
    "evolution_data",
}

# ── 已知 prep 顶层键（用于 build_prep() 类型校验） ──

_PREP_KNOWN_KEYS: set[str] = {
    "details",
    "total_mv",
    "total_cost",
    "total_profit",
    "total_today_profit",
    "categories",
    "a_indices",
    "us_indices",
    "penetrated_assets",
    "holdings_details",
    "today_str",
    "output_dir",
    "news_top_count",
    "risk_metrics",
}

# ── 类型映射（用于自动类型断言） ──

_PIPELINE_DATA_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "diff": (dict, type(None)),
    "data_degradation": list,
    "risk_metrics": dict,
    "portfolio_daily_returns": list,
    "factor_exposure": (dict, type(None)),
    "correlation_data": (dict, type(None)),
    "evolution_data": (dict, type(None)),
}

_PREP_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "details": list,
    "total_mv": (int, float),
    "total_cost": (int, float),
    "total_profit": (int, float),
    "total_today_profit": (int, float),
    "categories": dict,
    "a_indices": dict,
    "us_indices": dict,
    "penetrated_assets": list,
    "holdings_details": list,
    "today_str": str,
    "output_dir": str,
    "news_top_count": int,
    "risk_metrics": dict,
}


# ═══════════════════════════════════════════════════════════════
#  构建器函数
# ═══════════════════════════════════════════════════════════════


def _validate_keys(data: dict, known_keys: set[str], label: str) -> None:
    """校验字典键是否在已知范围内，记录未知键警告。

    Args:
        data: 待校验字典
        known_keys: 已知合法键集合
        label: 日志标签（如 "pipeline_data" / "prep"）
    """
    for k in data:
        if k not in known_keys:
            logger.warning("[pipeline_data] %s 包含未知键 '%s'，请先在 data-channels-schema.md 注册", label, k)


def _assert_type(value: Any, expected: type | tuple[type, ...], key: str) -> None:
    """类型断言，失败时记录警告但不抛出异常（生产环境容错）。"""
    if value is not None and not isinstance(value, expected):
        actual = type(value).__name__
        expected_name = getattr(expected, "__name__", str(expected))
        logger.warning(
            "[checkpoint] pipeline_data.%s 类型异常: 期望 %s, 实际 %s",
            key,
            expected_name,
            actual,
        )


def build(
    diff: dict | None = None,
    data_degradation: list | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """构建 A 通道 pipeline_data 字典。

    从各数据准备阶段接收结构化数据，合并并校验类型后返回。

    Args:
        diff: HistoryDiff 计算的环比差异字典
        data_degradation: DegradationTracker.get_log() 降级事件列表
        extra: 额外扩展键值对

    Returns:
        统一的 pipeline_data 字典，始终包含所有已知键（值可能为 None/空列表）
    """
    result: dict[str, Any] = {
        "diff": diff,
        "data_degradation": data_degradation or [],
    }

    # 合并额外键
    for k, v in extra.items():
        result[k] = v
        if k not in _PIPELINE_DATA_KNOWN_KEYS:
            logger.warning("[pipeline_data] 未注册键 '%s' 通过 extra 注入，请先在 Schema 定义中注册", k)
            _PIPELINE_DATA_KNOWN_KEYS.add(k)

    # 类型校验
    for key, expected in _PIPELINE_DATA_TYPE_MAP.items():
        _assert_type(result.get(key), expected, key)

    # 校验已知键范围
    _validate_keys(result, _PIPELINE_DATA_KNOWN_KEYS, "pipeline_data")

    # diff 子键深层校验
    if diff is not None and isinstance(diff, dict):
        _validate_diff(diff)

    return result


def build_prep(
    details: list | None = None,
    total_mv: float = 0.0,
    total_cost: float = 0.0,
    total_profit: float = 0.0,
    total_today_profit: float = 0.0,
    categories: dict | None = None,
    a_indices: dict | None = None,
    us_indices: dict | None = None,
    penetrated_assets: list | None = None,
    holdings_details: list | None = None,
    today_str: str | None = None,
    output_dir: str = "reports",
    news_top_count: int = 100,
    **extra: Any,
) -> dict[str, Any]:
    """构建 B 通道 prep 字典。

    从数据准备阶段接收行情/指数/穿透等数据，校验类型后返回。

    Args:
        details: 行情明细（DetailRow 列表）
        total_mv: 持仓总市值
        total_cost: 持仓总成本
        total_profit: 持仓总盈亏
        total_today_profit: 今日总盈亏
        categories: 品种分类计数
        a_indices: A 股指数行情
        us_indices: 美股指数行情
        penetrated_assets: 穿透 TOP10 资产列表
        holdings_details: 持仓明细字典列表
        today_str: 当前日期 YYYY-MM-DD
        output_dir: 报告输出目录
        news_top_count: 新闻最大返回条数
        extra: 额外扩展键值对

    Returns:
        合并后的 prep 字典
    """
    result: dict[str, Any] = {
        "details": details or [],
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_today_profit": total_today_profit,
        "categories": categories or {},
        "a_indices": a_indices or {},
        "us_indices": us_indices or {},
        "penetrated_assets": penetrated_assets or [],
        "holdings_details": holdings_details or [],
        "today_str": today_str or datetime.now().strftime("%Y-%m-%d"),
        "output_dir": output_dir,
        "news_top_count": news_top_count,
    }

    # 合并额外键
    for k, v in extra.items():
        result[k] = v
        _PREP_KNOWN_KEYS.add(k)

    # 类型校验
    for key, expected in _PREP_TYPE_MAP.items():
        _assert_type(result.get(key), expected, f"prep.{key}")

    # 校验已知键范围
    _validate_keys(result, _PREP_KNOWN_KEYS, "prep")

    return result


def _validate_diff(diff: dict) -> None:
    """深层校验 diff 子键的类型。"""
    _diff_type_map: dict[str, type | tuple[type, ...]] = {
        "is_first_check": bool,
        "days_since_last_report": (int, float),
        "total_value_diff": (int, float),
        "total_value_diff_pct": (int, float),
        "total_pnl_diff": (int, float),
        "added": list,
        "removed": list,
        "increased": list,
        "decreased": list,
    }
    for key, expected in _diff_type_map.items():
        if key in diff:
            _assert_type(diff[key], expected, f"diff.{key}")


# ── orchestrator.py 兼容入口（合并 capture_snapshot 返回值 + 可选扩展）──


def merge_pipeline_data(
    base_pipeline_data: dict | None,
    **extra: Any,
) -> dict | None:
    """合并基础 pipeline_data 与扩展字段。

    用于在 capture_snapshot 返回后向 pipeline_data 追加扩展字段。

    Args:
        base_pipeline_data: capture_snapshot 返回的原始 pipeline_data（可能为 None）
        extra: 需合并到 pipeline_data 的扩展字段

    Returns:
        合并后的 pipeline_data，或 None（base_pipeline_data 为 None 且 extra 为空时）
    """
    if base_pipeline_data is None and not extra:
        return None
    if base_pipeline_data is None:
        # 首次运行无基础 pipeline_data，以 extra 构建
        return build(**extra)
    if not extra:
        return base_pipeline_data

    # 合并 extra 到已有 pipeline_data
    merged = dict(base_pipeline_data)
    for k, v in extra.items():
        if k in merged:
            logger.debug("[pipeline_data] 覆盖已有键 '%s'", k)
        merged[k] = v
        if k not in _PIPELINE_DATA_KNOWN_KEYS:
            logger.warning("[pipeline_data] 未注册键 '%s' 通过 merge 注入，请先在 Schema 定义中注册", k)
            _PIPELINE_DATA_KNOWN_KEYS.add(k)
    return merged
