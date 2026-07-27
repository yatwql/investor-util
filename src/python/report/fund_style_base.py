"""基金风格判定 — 公共常量与基础工具。

包含六宫格风格定义、市值/PE 阈值、快照管理、低层分类助手。
由 fund_style_classify / fund_style_report 共享使用。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.code_utils import estimate_market_cap_by_prefix

logger = logging.getLogger("invest")

_SNAPSHOT_KEY = "fund_style_snapshot"
_SNAPSHOT_TTL = 365 * 86400

# ── 六宫格风格定义 ──────────────────────────────────────────

_SIZE_ORDER = ["大盘", "中盘", "小盘"]
_STYLE_ORDER = ["价值", "混合", "成长"]

# 所有有效风格组合
_STYLE_BOXES: set[str] = {f"{size}{style}" for size in _SIZE_ORDER for style in _STYLE_ORDER}


# ── 市值 / PE 阈值 ────────────────────────────────────────

_MARKET_CAP_LARGE = 500e8  # 500 亿
_MARKET_CAP_MID = 100e8  # 100 亿

# PE 相对行业平均的乘数阈值
_PE_VALUE_THRESHOLD = 0.7  # PE < 行业均值的 70% → 价值型
_PE_GROWTH_THRESHOLD = 1.3  # PE > 行业均值的 130% → 成长型


# ═══════════════════════════════════════════════════════════
#  快照管理
# ═══════════════════════════════════════════════════════════


_tencent_registered: bool = False


def _ensure_tencent_provider_registered() -> None:
    """惰性注册 Tencent 风格数据 Provider（避免模块导入时副作用）。"""
    global _tencent_registered
    if _tencent_registered:
        return
    from src.python.provider_registry import get_registry

    get_registry().register_provider("tencent_style", tier=4, timeout=15.0)
    _tencent_registered = True


def _load_snapshot() -> dict[str, Any] | None:
    """读取风格快照（固定键 fund_style_snapshot）。

    Returns:
        {code: {style, check_date, ...}} 或 None
    """
    return cache_get(_SNAPSHOT_KEY, _SNAPSHOT_TTL)


def _update_snapshot(current: dict[str, Any]) -> None:
    """更新风格快照（覆写）。

    快照格式：{code: {style: str, check_date: str}, ...}
    """
    cache_set(_SNAPSHOT_KEY, current)


# ═══════════════════════════════════════════════════════════
#  单只股票风格判定助手
# ═══════════════════════════════════════════════════════════


def _market_cap_to_size(market_cap: float) -> str:
    """根据总市值判断规模标签。"""
    if market_cap >= _MARKET_CAP_LARGE:
        return "大盘"
    elif market_cap >= _MARKET_CAP_MID:
        return "中盘"
    elif market_cap > 0:
        return "小盘"
    return "未知"


def _pe_to_style(pe: float, industry_avg_pe: float | None = None) -> str:
    """根据 PE 判断估值倾向。

    Args:
        pe: 个股动态市盈率（PE TTM）
        industry_avg_pe: 行业平均 PE，无行业数据时使用绝对值判定

    Returns:
        "价值" / "成长" / "混合"
    """
    if pe <= 0:
        return "混合"  # 负 PE 不参与方向判定

    if industry_avg_pe and industry_avg_pe > 0:
        ratio = pe / industry_avg_pe
        if ratio <= _PE_VALUE_THRESHOLD:
            return "价值"
        elif ratio >= _PE_GROWTH_THRESHOLD:
            return "成长"
        return "混合"
    else:
        # 无行业平均 PE 时，使用绝对值粗略判断
        if pe < 15:
            return "价值"
        elif pe > 30:
            return "成长"
        return "混合"


def _estimate_style_by_code(code: str) -> str:
    """按代码前缀粗略估算规模（降级方案 C，委托 code_utils 原语）。"""
    return estimate_market_cap_by_prefix(code)


def _get_size_from_code(code: str) -> str:
    """从代码前缀提取规模类别（用于降级）。"""
    est = _estimate_style_by_code(code)
    # 标准化
    if est in ("大盘", "中大盘"):
        return "大盘"
    elif est in ("中盘",):
        return "中盘"
    elif est in ("中小盘", "小盘"):
        return "小盘"
    return "其他"
