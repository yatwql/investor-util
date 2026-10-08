"""申赎费率表模型（fee_schedule_model）— 来源文本解析 / 费率表构建 / 档位选取。

:mod:`trade_cost_model` 的费率表子域（纯计算、零 I/O）：天天基金 F10 费用表
文本解析（原生/优惠双列与「每笔N元」固定费识别）、单档与配置兜底构建、
按金额与交易日持有期的档位选取。两模块共用的来源标记（``SRC_*``）与
「N年」折算常数（``TRADING_DAYS_PER_YEAR``）定义于此，``trade_cost_model``
反向导入复用——依赖方向单向（本模块不依赖 trade_cost_model，无循环）。

口径与红线（持有期按交易日解释、N年 × 250 交易日、≥100% 费率文本拒绝、
档位自 0 起连续覆盖全轴、配置兜底 0≤r<1 与上界严格递增）详见各函数
docstring 与 :mod:`trade_cost_model` 模块口径清单；设计文档为唯一依据。
"""

from __future__ import annotations

import math
import re
from typing import Any

# ── 常量 ────────────────────────────────────────────────

TRADING_DAYS_PER_YEAR = 250
"""费率表「N年」标签 → 交易日边界的折算常数（约 250 交易日/年）。"""

# 费率来源标记（报告层展示与测试断言的唯一取值；与腿侧别 SIDE_* 同为唯一枚举）
SRC_F10 = "f10_tier"
SRC_TABLE_SINGLE = "table_single"
SRC_CONFIG = "config"
SRC_UNKNOWN = "unknown"
SRC_UNMODELED = "unmodeled"

# ── 来源文本解析 ────────────────────────────────────────

_RE_BOUND = re.compile(r"(小于等于|小于|大于等于|大于)\s*([0-9]+(?:\.[0-9]+)?)\s*(天|年)")
_RE_AMOUNT_BOUND = re.compile(r"(小于等于|小于|大于等于|大于)\s*([0-9]+(?:\.[0-9]+)?)\s*(万元|元)")
_RE_PCT = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")
_RE_FLAT = re.compile(r"每笔\s*([0-9]+(?:\.[0-9]+)?)\s*元")


def parse_fee_percent(text: str) -> float | None:
    """「1.50%」→ 0.015；来源为 `---`/空/无法解析 → None（未知）。

    Args:
        text: 费率文本（允许内嵌 ``&nbsp;``/不换行空格等空白）

    Returns:
        小数费率；``0.00%`` 合法返回 0.0（**已知 0**，与未知 None 严格区分）。
    """
    t = (text or "").replace("&nbsp;", " ").replace("\xa0", " ").strip()
    if not t or t.lstrip("-").startswith("---") or t == "---":
        return None
    m = _RE_PCT.search(t)
    if not m:
        return None
    try:
        value = float(m.group(1)) / 100.0
    except ValueError:
        return None
    # ≥100% 的费率不合理（录入错误/单位错位）→ 判未知，不带进成本计算
    if value >= 1.0:
        return None
    return round(value, 6)


def _unit_days(value: float, unit: str) -> int:
    """天/年 → 交易日边界（年按 TRADING_DAYS_PER_YEAR 折算）。"""
    if unit == "年":
        return int(round(value * TRADING_DAYS_PER_YEAR))
    return int(round(value))


def _label_bounds(label: str) -> tuple[int | None, int | None] | None:
    """赎回费档位标签 → (下界含, 上界不含) 交易日边界；``---`` → (None, None)。

    支持来源实测形态：``小于7天`` / ``小于等于6天`` / ``大于等于7天，小于30天`` /
    ``大于等于30天，小于等于364天`` / ``大于等于7天`` / ``大于等于7天，小于1年`` /
    ``大于等于1年，小于2年`` / ``---``。整数交易日计数下「小于等于X」→ 上界 X+1，
    「小于X」→ 上界 X（两者整数语义等价：上界取 X 减 1，或严格小于 X）。
    """
    t = (label or "").strip()
    if t.startswith("---"):
        return None, None
    lower: int | None = None
    upper: int | None = None
    for m in _RE_BOUND.finditer(t):
        op, num, unit = m.group(1), float(m.group(2)), m.group(3)
        days = _unit_days(num, unit)
        if op in ("大于等于", "大于"):
            lower = days  # 来源语义：整数档位连续，「大于」与「大于等于」同边界
        elif op == "小于等于":
            upper = days + 1
        else:  # 小于
            upper = days
    if lower is None and upper is None:
        return None
    if lower is not None and upper is not None and lower >= upper:
        return None  # 来源异常（交叠/倒置）→ 该行不可解析
    return lower, upper


def _amount_bounds(label: str) -> tuple[float | None, float | None] | None:
    """申购费档位标签 → (下界含, 上界不含) 金额边界（万元/元 → 元）。"""
    t = (label or "").strip()
    if t.startswith("---"):
        return None, None
    lower: float | None = None
    upper: float | None = None
    for m in _RE_AMOUNT_BOUND.finditer(t):
        op, num, unit = m.group(1), float(m.group(2)), m.group(3)
        amount = num * 10000.0 if unit == "万元" else num
        if op in ("大于等于", "大于"):
            lower = amount
        elif op == "小于等于":
            upper = amount + 0.01  # 含端点 → 半开区间右扩一厘
        else:  # 小于
            upper = amount
    if lower is None and upper is None:
        return None
    if lower is not None and upper is not None and lower >= upper:
        return None
    return lower, upper


def _cell_rates(cell: str) -> tuple[float | None, float | None, float | None]:
    """申购费率单元格 → (原费率, 优惠费率, 每笔固定费)。

    来源实测形态：``1.50%  |  0.15%``（原 | 天天基金优惠，取优惠）、``0.15%``
    （单值）、``每笔1000元``（固定费档）。
    """
    text = (cell or "").replace("&nbsp;", " ").replace("\xa0", " ").strip()
    flat_m = _RE_FLAT.search(text)
    flat = float(flat_m.group(1)) if flat_m else None
    pcts = [m.group(1) for m in _RE_PCT.finditer(text)]
    if not pcts:
        return None, None, flat
    rates = [round(float(p) / 100.0, 6) for p in pcts]
    orig = rates[0]
    discount = rates[-1] if len(rates) > 1 else None
    return orig, discount, flat


# ── 费率表契约（redemption_fee_schedule / purchase） ──────


def parse_redemption_fee_schedule(rows: list[list[str]], source: str = SRC_F10) -> dict[str, Any] | None:
    """赎回费率表原始行 → ``redemption_fee_schedule`` 契约（解析失败 → None）。

    Args:
        rows: ``[[档位标签, 费率], ...]``（provider 已剥标签；顺序 = 来源升序）
        source: 来源标记（f10_tier / config）

    Returns:
        ``{"tiers": [{"min_days", "max_days", "rate"}], "source": str}``；
        任一行无法解析、区间倒置或覆盖率不连续 → None（费率未知，不猜）。
    """
    if not rows:
        return None
    tiers: list[dict[str, Any]] = []
    for row in rows:
        if not row or len(row) < 2:
            return None
        bounds = _label_bounds(str(row[0]))
        rate = parse_fee_percent(str(row[1]))
        if bounds is None or rate is None:
            return None
        lower, upper = bounds
        tiers.append({"min_days": lower, "max_days": upper, "rate": rate})
    if not _tiers_contiguous(tiers, "min_days", "max_days"):
        return None
    return {"tiers": tiers, "source": source}


def parse_purchase_fee_schedule(rows: list[list[str]], source: str = SRC_F10) -> dict[str, Any] | None:
    """申购费率表原始行 → 费率表契约（解析失败 → None）。

    Args:
        rows: ``[[金额档位标签, 费率单元格], ...]``（单元格可含「原 | 优惠」双值）

    Returns:
        ``{"tiers": [{"min_amount", "max_amount", "rate", "flat_fee"}], "source": str}``
        （``rate`` 与 ``flat_fee`` 二选一：``每笔X元`` 为固定费档）；解析失败 → None。
    """
    if not rows:
        return None
    tiers: list[dict[str, Any]] = []
    for row in rows:
        if not row or len(row) < 2:
            return None
        bounds = _amount_bounds(str(row[0]))
        orig, discount, flat = _cell_rates(str(row[1]))
        if bounds is None or (flat is None and discount is None and orig is None):
            return None
        lower, upper = bounds
        tiers.append(
            {
                "min_amount": lower,
                "max_amount": upper,
                "rate": discount if discount is not None else orig,
                "flat_fee": flat,
            }
        )
    if not _tiers_contiguous(tiers, "min_amount", "max_amount"):
        return None
    return {"tiers": tiers, "source": source}


def build_single_purchase_schedule(rate: float, source: str = SRC_TABLE_SINGLE) -> dict[str, Any] | None:
    """单档申购费率（全量表「手续费」列）→ 覆盖全区间的单档契约。

    仅首档近似的来源（无金额分档）用此形态；``rate`` 非有限/负数/≥1（100%）
    → None（费率不合理判未知，不冒充）。
    """
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not math.isfinite(rate):
        return None
    if rate < 0 or rate >= 1:
        return None
    return {
        "tiers": [{"min_amount": None, "max_amount": None, "rate": round(float(rate), 6), "flat_fee": None}],
        "source": source,
    }


def _tiers_contiguous(tiers: list[dict[str, Any]], lo_key: str, hi_key: str) -> bool:
    """档位区间是否自 0 起连续覆盖全轴（无缺口、无交叠，顺序 = 来源顺序）。"""
    cursor: float | None = None  # None = 未覆盖起点
    for t in tiers:
        lo, hi = t.get(lo_key), t.get(hi_key)
        if cursor is None:
            if lo is not None and abs(float(lo)) > 1e-9:
                return False  # 首档未从 0 起 → 起始缺口
        else:
            if lo is None or abs(float(lo) - cursor) > 1e-9:
                return False  # 与上一档不衔接
        if hi is None:
            return True  # 末档开区间 → 覆盖到无穷（调用方保证其为最后判定）
        cursor = float(hi)
    return False  # 无开区间末档 → 右端缺口


# ── 配置兕底构建 ────────────────────────────────────────


def build_config_fee_schedules(entry: Any) -> dict[str, Any] | None:
    """配置兕底条目（``config.json fund_fee_fallback`` 值）→ 两侧费率表。

    条目形态（不合法侧置 None，两侧全非法 → None，由调用方告警）：

      - ``purchase_rate``：单档申购费率（小数 0 ≤ r < 1）→ ``table_single``
        同构契约，来源标 ``config``
      - ``redemption_tiers``：``[{"max_days": 上界交易日|None, "rate": 费率}, ...]``
        按**交易日**边界升序；首档从 0 起（由构建器隐含）、末档上界必须为
        ``None``（开区间覆盖到无穷）、中间档上界严格递增正整数；rate 小数
        0 ≤ r < 1

    Returns:
        ``{"purchase": 费率表|None, "redemption": 费率表|None}``（至少一侧非空）
    """
    if not isinstance(entry, dict):
        return None
    purchase: dict[str, Any] | None = None
    redemption: dict[str, Any] | None = None

    rate = entry.get("purchase_rate")
    if rate is not None:
        purchase = build_single_purchase_schedule(rate, SRC_CONFIG)

    tiers = entry.get("redemption_tiers")
    if isinstance(tiers, list) and tiers:
        built = _tiers_from_config(tiers)
        if built is not None:
            redemption = {"tiers": built, "source": SRC_CONFIG}

    if purchase is None and redemption is None:
        return None
    return {"purchase": purchase, "redemption": redemption}


def _tiers_from_config(tiers: list[Any]) -> list[dict[str, Any]] | None:
    """配置档位列表 → 契约 tiers（首档从 0 起、上界严格递增、末档开区间）。

    区间连续性由构建保证（每档 ``min_days`` = 上一档 ``max_days``），
    任一条目非法 → None（整侧放弃，不猜半张表）。
    """
    built: list[dict[str, Any]] = []
    prev_max = 0
    for i, item in enumerate(tiers):
        if not isinstance(item, dict):
            return None
        max_days = item.get("max_days")
        rate = item.get("rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate):
            return None
        if not 0 <= rate < 1:
            return None
        is_last = i == len(tiers) - 1
        if is_last:
            if max_days is not None:
                return None  # 末档必须开区间（覆盖到无穷，无右端缺口）
        else:
            if isinstance(max_days, bool) or not isinstance(max_days, int) or max_days <= prev_max:
                return None  # 上界须为严格递增正整数交易日
        built.append(
            {
                "min_days": None if i == 0 else prev_max,
                "max_days": None if is_last else max_days,
                "rate": round(float(rate), 6),
            }
        )
        if not is_last:
            prev_max = max_days
    return built


def select_redemption_tier(schedule: dict[str, Any] | None, holding_days: int | None) -> dict[str, Any] | None:
    """按交易日持有期选赎回费档位；未知费率表 / 未知持有期 / 无命中 → None。"""
    if not schedule or holding_days is None or holding_days < 0:
        return None
    tiers = schedule.get("tiers")
    if not isinstance(tiers, list):
        return None
    for tier in tiers:
        if not isinstance(tier, dict):
            return None
        lo = tier.get("min_days")
        hi = tier.get("max_days")
        if (lo is None or holding_days >= lo) and (hi is None or holding_days < hi):
            return tier
    return None


def select_purchase_tier(schedule: dict[str, Any] | None, amount: float) -> dict[str, Any] | None:
    """按金额选申购费档位；未知费率表 / 无命中 → None（NaN 恒无命中）。"""
    if not schedule or not isinstance(amount, (int, float)) or not math.isfinite(amount):
        return None
    tiers = schedule.get("tiers")
    if not isinstance(tiers, list):
        return None
    for tier in tiers:
        if not isinstance(tier, dict):
            return None
        lo = tier.get("min_amount")
        hi = tier.get("max_amount")
        if (lo is None or amount >= lo) and (hi is None or amount < hi):
            return tier
    return None


def purchase_fee(amount: float, schedule: dict[str, Any] | None) -> tuple[float | None, dict[str, Any] | None]:
    """申购费（元）：命中档位按比例或每笔固定费；未知 → (None, None)。

    Returns:
        (fee, tier) — fee 保留 2 位小数；tier 为命中的档位（供展示）。
    """
    tier = select_purchase_tier(schedule, amount)
    if tier is None:
        return None, None
    if tier.get("flat_fee") is not None:
        return round(float(tier["flat_fee"]), 2), tier
    rate = tier.get("rate")
    if rate is None:
        return None, None
    return round(max(amount, 0.0) * float(rate), 2), tier


__all__ = [
    "SRC_CONFIG",
    "SRC_F10",
    "SRC_TABLE_SINGLE",
    "SRC_UNKNOWN",
    "SRC_UNMODELED",
    "TRADING_DAYS_PER_YEAR",
    "build_config_fee_schedules",
    "build_single_purchase_schedule",
    "parse_fee_percent",
    "parse_purchase_fee_schedule",
    "parse_redemption_fee_schedule",
    "purchase_fee",
    "select_purchase_tier",
    "select_redemption_tier",
]
