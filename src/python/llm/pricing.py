"""LLM 定价模块 — 模型费用估算与定价配置管理。

支持峰谷定价（DeepSeek 官方方案）：含 ``peak`` 高峰价子段的模型，在工作日高峰
时段（默认北京时间 9:00–12:00、14:00–18:00）按高峰价计费，其余时段（闲时）按
base 价计费；周末（周六/周日）全天一律按闲时价计费，不区分峰谷（2026-08-23
起 DeepSeek 官方方案）。时段、时区与周末规则可由 ``llm_settings.json → pricing``
段覆盖。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.core.constants import (
    MODEL_PRICING,
    PRICING_IDLE_PERIODS as _DEFAULT_IDLE_PERIODS,
    PRICING_PEAK_PERIODS as _DEFAULT_PEAK_PERIODS,
    PRICING_TIMEZONE as _DEFAULT_TIMEZONE,
    PRICING_WEEKEND_ALWAYS_IDLE as _DEFAULT_WEEKEND_ALWAYS_IDLE,
)

logger = logging.getLogger("invest")

__all__ = [
    "PRICING_MERGED",
    "PRICING_CURRENCY",
    "CURRENCY_SYMBOLS",
    "PRICING_PEAK_PERIODS",
    "PRICING_IDLE_PERIODS",
    "PRICING_TIMEZONE_NAME",
    "PRICING_WEEKEND_ALWAYS_IDLE",
    "reload_pricing",
    "estimate_cost",
]


def _load_timezone(name: str) -> Any:
    """编译 IANA 时区；失败返回 None（回落系统本地时间）。

    zoneinfo 依赖系统 tzdata（Linux 一般自带）；缺失或名称非法时不影响计价，
    仅退化为按本地时间判定峰谷。
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — 时区加载失败属非致命降级，任意异常均可接受
        return None


def _parse_clock(text: str) -> int | None:
    """解析 "HH:MM"（24 小时制）为当日分钟数 [0, 1440)；失败返回 None。"""
    text = text.strip()
    try:
        hh, mm = text.split(":", 1)
        hh_i, mm_i = int(hh), int(mm)
    except (ValueError, IndexError):
        return None
    if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
        return hh_i * 60 + mm_i
    return None


def _parse_periods(value: Any) -> list[tuple[int, int]] | None:
    """解析 "HH:MM-HH:MM" 时段列表为 (start, end) 分钟闭区间。

    任意一项格式非法返回 None（调用方保留既有时段）；空列表合法返回 []。
    """
    if not isinstance(value, list):
        return None
    periods: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, str):
            return None
        parts = item.split("-")
        if len(parts) != 2:
            return None
        start = _parse_clock(parts[0])
        end = _parse_clock(parts[1])
        if start is None or end is None:
            return None
        periods.append((start, end))
    return periods


# ── 运行时合并定价表：硬编码 + llm_settings.json 覆盖
# 定价条目结构：base 价（input/output/input_cache_hit，float）+ 可选高峰价子段
# "peak"（dict[str, float]）。无 "peak" 的模型始终按 base 价计费。
PriceEntry = dict[str, float | dict[str, float]]
PRICING_MERGED: dict[str, PriceEntry] = {model: dict(prices) for model, prices in MODEL_PRICING.items()}

# 定价货币标识，默认 CNY；可通过 llm_settings.json → pricing.currency 覆盖
PRICING_CURRENCY: str = "CNY"

# 货币符号映射
CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "CNY": "¥",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
}

# 峰谷时段（分钟起算闭区间）——默认取 constants.py；可通过 llm_settings.json →
# pricing.peak_periods / idle_periods 覆盖
PRICING_PEAK_PERIODS: list[tuple[int, int]] = list(_DEFAULT_PEAK_PERIODS)
PRICING_IDLE_PERIODS: list[tuple[int, int]] = list(_DEFAULT_IDLE_PERIODS)

# 周末全天按闲时价计费（周六/周日不再区分峰谷）——默认取 constants.py，可通过
# llm_settings.json → pricing.weekend_always_idle 覆盖
PRICING_WEEKEND_ALWAYS_IDLE: bool = bool(_DEFAULT_WEEKEND_ALWAYS_IDLE)

# 峰谷判定时区（IANA 名称）与编译后的 ZoneInfo 对象；加载失败回落本地时间
PRICING_TIMEZONE_NAME: str = _DEFAULT_TIMEZONE
PRICING_TZ: Any = _load_timezone(PRICING_TIMEZONE_NAME)

# 非模型键：pricing 段中不作模型合并的元字段
_NON_MODEL_PRICING_KEYS: frozenset[str] = frozenset(
    {"currency", "timezone", "peak_periods", "idle_periods", "weekend_always_idle"}
)

# 延迟加载标记 — reload_pricing() 首次调用 estimate_cost() 时执行
_PRICING_LOADED: bool = False


def _effective_minute(at_time: datetime | None) -> int:
    """换算待判定时刻为「定价时区」下的当日分钟数。

    at_time 缺省取当前时间；aware datetime 先换算到定价时区，naive datetime
    视为已在定价时区（便于测试传入固定时刻）。
    """
    tz = PRICING_TZ
    if at_time is None:
        now = datetime.now(tz) if tz else datetime.now()
        return now.hour * 60 + now.minute
    if at_time.tzinfo is not None and tz is not None:
        at_time = at_time.astimezone(tz)
    return at_time.hour * 60 + at_time.minute


def _is_weekend(at_time: datetime | None) -> bool:
    """待判定时刻（定价时区）是否周末（周六/周日）。

    naive datetime 视为已在定价时区（与 _effective_minute 一致，便于测试）。
    """
    tz = PRICING_TZ
    if at_time is None:
        now = datetime.now(tz) if tz else datetime.now()
        return now.weekday() >= 5
    if at_time.tzinfo is not None and tz is not None:
        at_time = at_time.astimezone(tz)
    return at_time.weekday() >= 5


def _is_peak_minute(minute: int, weekend: bool = False) -> bool:
    """分钟是否属于高峰时段（仅工作日；周末恒为闲时）。

    高峰时段仅在工作日（周一至周五）生效：peak_periods 非空时，高峰 = 这些时段，
    闲时 = 其余时间（官方方案「其余为空闲时段」）；peak_periods 为空、仅
    idle_periods 非空时，闲时 = 这些时段，高峰 = 其余时间；两者均空 → 无峰谷定价，
    始终按 base 价。PRICING_WEEKEND_ALWAYS_IDLE 为真且为周末时，无论时段一律返回
    False（闲时价）。
    """
    if PRICING_WEEKEND_ALWAYS_IDLE and weekend:
        return False
    if not PRICING_PEAK_PERIODS and not PRICING_IDLE_PERIODS:
        return False
    if PRICING_PEAK_PERIODS:
        return any(start <= minute <= end for start, end in PRICING_PEAK_PERIODS)
    return not any(start <= minute <= end for start, end in PRICING_IDLE_PERIODS)


def reload_pricing() -> None:
    """从 llm_settings.json 重新加载定价配置。

    - "currency" 字段（可选，默认 "CNY"）设定货币类型，影响费用显示的符号。
    - "timezone" 字段（可选，默认 "Asia/Shanghai"）设定峰谷判定时区。
    - "peak_periods" / "idle_periods" 字段（可选，"HH:MM-HH:MM" 列表）设定
      高峰/闲时段，缺省沿用 constants.py 内置时段。
    - "weekend_always_idle" 字段（可选，默认 True）设定周末（周六/周日）是否
      全天按闲时价计费、不区分峰谷（DeepSeek 官方方案）。
    - 其余字段按模型名合并到 PRICING_MERGED（文件配置优先级高于内置默认）。
      文件中的 input_cache_hit 为可选字段，缺失时继承内置默认值（如内置也无则等于 input）。
      含 "peak" 子段的模型支持峰谷定价：工作日高峰时段按 peak 子段价格，
      其余时段（含周末全天）按 base 价。
    """
    global PRICING_CURRENCY
    global PRICING_PEAK_PERIODS, PRICING_IDLE_PERIODS
    global PRICING_TIMEZONE_NAME, PRICING_TZ, PRICING_WEEKEND_ALWAYS_IDLE
    try:
        from src.python.config import get_llm_config

        cfg = get_llm_config()
        if cfg and "pricing" in cfg:
            file_pricing = cfg["pricing"]
            if isinstance(file_pricing, dict):
                # 货币标识
                if "currency" in file_pricing:
                    PRICING_CURRENCY = str(file_pricing["currency"]).upper().strip()
                # 峰谷时段 / 时区
                tz_name = file_pricing.get("timezone")
                if isinstance(tz_name, str) and tz_name.strip():
                    PRICING_TIMEZONE_NAME = tz_name.strip()
                    PRICING_TZ = _load_timezone(PRICING_TIMEZONE_NAME)
                parsed_peak = _parse_periods(file_pricing.get("peak_periods"))
                if parsed_peak is not None:
                    # 就地替换（[:]），保持列表对象身份稳定——外部已持有的引用
                    # （模块直接导入/测试恢复）不失效
                    PRICING_PEAK_PERIODS[:] = parsed_peak
                parsed_idle = _parse_periods(file_pricing.get("idle_periods"))
                if parsed_idle is not None:
                    PRICING_IDLE_PERIODS[:] = parsed_idle
                # 周末全天按闲时价（可选，默认 True）
                weekend_flag = file_pricing.get("weekend_always_idle")
                if isinstance(weekend_flag, bool):
                    PRICING_WEEKEND_ALWAYS_IDLE = weekend_flag
                # 模型定价合并（含高峰价子段 peak）
                for model, prices in file_pricing.items():
                    if model in _NON_MODEL_PRICING_KEYS or not isinstance(prices, dict):
                        continue
                    existing = dict(PRICING_MERGED.get(model, {"input": 0.0, "output": 0.0, "input_cache_hit": 0.0}))
                    if "input" in prices:
                        existing["input"] = float(prices["input"])
                    if "output" in prices:
                        existing["output"] = float(prices["output"])
                    if "input_cache_hit" in prices:
                        existing["input_cache_hit"] = float(prices["input_cache_hit"])
                    peak = prices.get("peak")
                    if isinstance(peak, dict):
                        peak_input = float(peak.get("input", existing["input"]))
                        peak_output = float(peak.get("output", existing["output"]))
                        peak_cache_hit = float(peak.get("input_cache_hit", existing.get("input_cache_hit", peak_input)))
                        existing["peak"] = {
                            "input": peak_input,
                            "output": peak_output,
                            "input_cache_hit": peak_cache_hit,
                        }
                    # 文件未提供 peak 时保留已有（继承内置默认或用户上次覆盖）
                    PRICING_MERGED[model] = existing
    except Exception:
        logger.debug("加载定价配置失败，使用默认定价", exc_info=True)


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit_input_tokens: int = 0,
    at_time: datetime | None = None,
) -> str:
    """估算 LLM API 调用的费用。

    基于已知模型定价（每百万 token 价格）。
    未知模型返回 "-"。
    货币符号由 PRICING_CURRENCY 决定（自 llm_settings.json → pricing.currency）。
    若存在缓存命中 token，按 input_cache_hit 费率计算（通常为 input 的 10%）。
    含 "peak" 高峰价子段的模型，在工作日高峰时段按 peak 价计费，其余时段按
    base（闲时）价；周末全天一律按 base（闲时）价（PRICING_WEEKEND_ALWAYS_IDLE）。

    Args:
        model: 模型名称
        input_tokens: 总输入 token 数（含缓存命中+缓存未命中）
        output_tokens: 输出 token 数
        cache_hit_input_tokens: 其中属于缓存命中的 token 数（默认 0）
        at_time: 计费时刻（默认当前时间；naive 视为已在定价时区，便于测试固定时刻）

    Returns:
        格式化费用字符串，如 "$0.008"、"¥0.06" 或 "-"
    """
    global _PRICING_LOADED
    if not _PRICING_LOADED:
        reload_pricing()
        _PRICING_LOADED = True
    if not input_tokens and not output_tokens:
        return "-"
    model_lower = model.lower().strip()
    pricing = PRICING_MERGED.get(model_lower)
    if not pricing:
        for known, price in PRICING_MERGED.items():
            if model_lower.startswith(known):
                pricing = price
                break
    if not pricing:
        return "-"
    # 峰谷定价：工作日命中高峰时段（周末恒闲时）时切换到高峰价子段
    effective: dict[str, float | dict[str, float]] = pricing
    peak = pricing.get("peak")
    if isinstance(peak, dict) and _is_peak_minute(_effective_minute(at_time), _is_weekend(at_time)):
        effective = peak
    cache_miss = input_tokens - cache_hit_input_tokens
    cost = cache_miss / 1_000_000 * float(effective["input"]) + output_tokens / 1_000_000 * float(effective["output"])
    if cache_hit_input_tokens > 0:
        cache_rate = effective.get("input_cache_hit", effective["input"])
        cost += cache_hit_input_tokens / 1_000_000 * float(cache_rate)
    symbol = CURRENCY_SYMBOLS.get(PRICING_CURRENCY, "$")
    if cost < 0.01:
        return f"{symbol}{cost:.4f}"
    return f"{symbol}{cost:.3f}"
