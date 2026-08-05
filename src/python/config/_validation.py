"""配置校验模块 — config.json 配置校验函数集。

集中管理所有配置校验逻辑。
每个 _validate_* 函数接收 (config, issues) 并返回 issues 计数。
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.python.core.constants import PROJECT_ROOT
from src.python.core.registry import get_known_enabled_llm_keys, get_report_section_keys
from src.python.analysis.drawdown_events import MIN_SPAN

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════════
# 配置校验常量
# ═══════════════════════════════════════════════════════════════════

_KNOWN_NEWS_SOURCES: set[str] = {"sina", "eastmoney", "cls", "wallstreetcn", "akshare"}

_KNOWN_PROVIDER_TYPES: set[str] = {"price", "fund_rank", "fund_hold", "industry"}

_KNOWN_PROVIDER_NAMES: set[str] = {
    "tencent",
    "eastmoney",
    "sina",
    "tiantian",
    "eastmoney_industry",
    "eastmoney_industry_rest",
}

_STRING_CONFIG_KEYS: set[str] = {
    "holdings_dir",
    "holdings_filename",
    "output_dir",
    "llm_key_file",
    "llm_settings_file",
    "llm_providers_file",
}

# 需要绝对化的路径型配置键（不包含纯文件名 holdings_filename）
_PATH_CONFIG_KEYS: set[str] = {
    "holdings_dir",
    "output_dir",
    "llm_key_file",
    "llm_settings_file",
    "llm_providers_file",
}

_MISSING = object()


def _is_abs(path: str) -> bool:
    """增强的绝对路径判断，兼容 Windows 下 Unix 风格 /path 的识别。"""
    return os.path.isabs(path) or (len(path) > 0 and path[0] in ("/", "\\"))


def _absolutize_paths(config: dict) -> dict:
    """将配置中路径型键转为绝对路径（若为相对路径则拼接 PROJECT_ROOT）。

    使用户 config.json 中可继续使用友好的相对路径，运行时所有消费者
    拿到的均为绝对路径，彻底消除 CWD 依赖。
    """
    for key in _PATH_CONFIG_KEYS:
        val = config.get(key)
        if isinstance(val, str) and not _is_abs(val):
            config[key] = os.path.join(PROJECT_ROOT, val)
    return config


def _deabsolutize_paths(config: dict) -> dict:
    """将配置中位于项目根目录下的绝对路径键还原为相对路径（写盘前调用）。

    与 _absolutize_paths 相对：运行时内存中使用绝对路径，落盘时还原为
    相对路径，避免把本机绝对路径写入 config.json 导致跨机器不可移植。
    仅处理 PROJECT_ROOT 之下的路径；外部绝对路径（不同盘符/项目外目录）
    无法相对化或相对化会越出根目录，保持原样不变。

    Args:
        config: 待写盘的配置字典（就地修改路径型键）

    Returns:
        传入的同一 dict（便于链式调用）
    """
    for key in _PATH_CONFIG_KEYS:
        val = config.get(key)
        if not isinstance(val, str) or not _is_abs(val):
            continue
        try:
            rel = os.path.relpath(val, PROJECT_ROOT)
        except ValueError:
            # 不同盘符（Windows）无法计算相对路径，保持绝对路径
            continue
        # 位于 PROJECT_ROOT 之外（relpath 越出根目录），保持绝对路径
        if not rel or rel.startswith(".."):
            continue
        config[key] = rel.replace(os.sep, "/")
    return config


# ═══════════════════════════════════════════════════════════════════
# 校验辅助函数
# ═══════════════════════════════════════════════════════════════════


def _section(config: dict, key: str, expected_type: type, warn_msg: str, issues: int = 0) -> tuple[Any, int]:
    """读取配置段，校验类型。"""
    val = config.get(key)
    if val is None:
        return _MISSING, issues
    if not isinstance(val, expected_type):
        logger.warning("config.json %s = %r 不是 %s，%s", key, val, expected_type.__name__, warn_msg)
        return _MISSING, issues + 1
    return val, issues


# ═══════════════════════════════════════════════════════════════════
# 各配置段的校验函数
# ═══════════════════════════════════════════════════════════════════


def _validate_string_configs(config: dict, issues: int) -> int:
    for key in _STRING_CONFIG_KEYS:
        val = config.get(key)
        if val is not None and not isinstance(val, str):
            logger.warning("config.json %s = %r 不是字符串类型，可能导致运行时 TypeError", key, val)
            issues += 1
    fn = config.get("holdings_filename")
    if isinstance(fn, str) and fn.strip() == "":
        logger.warning("config.json holdings_filename 为空字符串，将使用默认文件名")
        issues += 1
    return issues


def _validate_news_top_count(config: dict, issues: int) -> int:
    ntc = config.get("news_top_count")
    if ntc is None:
        return issues
    try:
        n_int = int(ntc)
        if n_int <= 0:
            logger.warning("config.json news_top_count = %r 不是正数，将使用默认值 300", ntc)
            issues += 1
    except (ValueError, TypeError):
        logger.warning("config.json news_top_count = %r 不是有效整数，将使用默认值 300", ntc)
        issues += 1
    return issues


def _validate_cache_ttl(config: dict, issues: int) -> int:
    cache_ttl, issues = _section(config, "cache_ttl", dict, "所有缓存 TTL 将使用默认值", issues)
    if cache_ttl is _MISSING:
        return issues
    for k, v in cache_ttl.items():
        try:
            val = float(v)
            if val <= 0:
                logger.warning("config.json cache_ttl.%s = %s 不是正数，将使用默认值", k, v)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json cache_ttl.%s = %s 不是有效数字，将使用默认值", k, v)
            issues += 1
    return issues


def _validate_news_sources(config: dict, issues: int) -> int:
    news_src, issues = _section(config, "news_sources", dict, "所有源将使用默认开关状态", issues)
    if news_src is _MISSING:
        return issues
    for key, val in news_src.items():
        if key not in _KNOWN_NEWS_SOURCES:
            logger.warning("config.json news_sources 中存在未知的源 %r，将被忽略", key)
            issues += 1
        if not isinstance(val, bool):
            logger.warning("config.json news_sources.%s = %r 不是布尔值，非空字符串/数字会被当作 True 处理", key, val)
            issues += 1
    return issues


def _validate_preferred_provider(config: dict, issues: int) -> int:
    pref, issues = _section(config, "preferred_provider", dict, "配置无效", issues)
    if pref is _MISSING:
        return issues
    for data_type, provider in pref.items():
        if data_type not in _KNOWN_PROVIDER_TYPES:
            logger.warning(
                "config.json preferred_provider 中存在未知的数据类型 %r，有效值: %s",
                data_type,
                ", ".join(sorted(_KNOWN_PROVIDER_TYPES)),
            )
            issues += 1
        if provider not in _KNOWN_PROVIDER_NAMES:
            logger.warning(
                "config.json preferred_provider.%s = %r 不是已知的 provider，有效值: %s",
                data_type,
                provider,
                ", ".join(sorted(_KNOWN_PROVIDER_NAMES)),
            )
            issues += 1
    return issues


def _validate_user_fund_benchmarks(config: dict, issues: int) -> int:
    ufb, issues = _section(config, "user_fund_benchmarks", dict, "自定义基准将忽略", issues)
    if ufb is _MISSING:
        return issues
    for code, benchmark in ufb.items():
        if not isinstance(code, str) or not code.strip():
            logger.warning("config.json user_fund_benchmarks 中存在非字符串或空字符串的基金代码 %r，该项将被忽略", code)
            issues += 1
            continue
        if not isinstance(benchmark, str) or not benchmark.strip():
            logger.warning(
                "config.json user_fund_benchmarks.%s = %r 不是有效的基准名称（应为字符串），该项将被忽略",
                code,
                benchmark,
            )
            issues += 1
    return issues


def _validate_enable_boards(config: dict, issues: int) -> int:
    """验证章节可见性配置（enable_fund_deep_analysis / enable_news / enable_history /
    enable_portfolio_evolution / enable_action）。

    enable_action（行动建议独立章）默认开，缺失视为 True（沿用默认值），
    类型校验逻辑与其余 enable_xxx 一致。
    """
    for key in (
        "enable_fund_deep_analysis",
        "enable_news",
        "enable_history",
        "enable_portfolio_evolution",
        "enable_action",
    ):
        val = config.get(key)
        if val is None:
            continue  # 缺失视为默认值（各章节可见性开关默认 True）
        if not isinstance(val, bool):
            logger.warning("config.json %s = %r 不是布尔值，将使用默认值", key, val)
            issues += 1
    return issues


def _validate_enable_llm(issues: int) -> int:
    """验证 llm_settings.json 中 enabled_llm 字典的子键。

    仅检查格式/拼写错误，不判断业务语义（全关正常——可能是用户主动关闭
    所有 LLM 报告模块但仍需 news_correlation）。缺失视为正常（默认启用）。
    """
    from src.python.config._llm_settings import get_llm_config

    llm_config = get_llm_config()
    if not llm_config:
        return issues
    enabled_map = llm_config.get("enabled_llm")
    if enabled_map is None:
        return issues  # 缺失正常
    if not isinstance(enabled_map, dict):
        logger.warning("llm_settings.json enabled_llm = %r 不是字典", enabled_map)
        return issues + 1

    known_keys = get_known_enabled_llm_keys()
    unknown = [k for k in enabled_map if k not in known_keys]
    if unknown:
        logger.warning("llm_settings.json enabled_llm 中存在未知模块 %s，请检查拼写", unknown)
        issues += 1
    return issues


def _validate_market_hours(config: dict, issues: int) -> int:
    mha = config.get("market_hour_aware")
    if mha is not None and (not isinstance(mha, list) or not all(isinstance(x, str) for x in mha)):
        logger.warning("config.json market_hour_aware = %r 不是字符串列表", mha)
        issues += 1
    mht = config.get("market_hour_ttl")
    if mht is not None:
        try:
            mht_int = int(mht)
            if mht_int < 30:
                logger.warning("config.json market_hour_ttl = %s 小于 30 秒，将被钳制到 30 秒", mht)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json market_hour_ttl = %r 不是有效整数，将使用默认值 30", mht)
            issues += 1
    mh = config.get("market_hours")
    if mh is not None:
        if not isinstance(mh, dict):
            logger.warning("config.json market_hours = %r 不是对象(dict)，将使用内置默认时段", mh)
            issues += 1
        else:
            for time_key in ("start", "end"):
                tv = mh.get(time_key)
                if tv is not None and not isinstance(tv, str):
                    logger.warning("config.json market_hours.%s = %r 不是字符串", time_key, tv)
                    issues += 1
    return issues


def _validate_report_section_order(config: dict, issues: int) -> int:
    order, issues = _section(config, "report_section_order", dict, "将使用默认顺序", issues)
    if order is _MISSING:
        return issues
    valid_keys = get_report_section_keys()
    seen_numbers: set[int] = set()
    for key, num in order.items():
        if key == "llm_usage":
            logger.warning("config.json report_section_order 中不应包含 llm_usage")
            issues += 1
            continue
        if key not in valid_keys:
            logger.warning("config.json report_section_order 中存在未知的模块标识 %r", key)
            issues += 1
            continue
        try:
            n = int(num)
            if n < 1:
                logger.warning("config.json report_section_order.%s = %s 不是正数", key, num)
                issues += 1
                continue
        except (ValueError, TypeError):
            logger.warning("config.json report_section_order.%s = %s 不是有效整数", key, num)
            issues += 1
            continue
        if n in seen_numbers:
            logger.warning("config.json report_section_order 中存在重复序号 %s（%s）", n, key)
            issues += 1
        else:
            seen_numbers.add(n)
    return issues


def _validate_benchmark_indices(config: dict, issues: int) -> int:
    """验证 history.benchmark_indices 配置。"""
    history = config.get("history", {})
    if not isinstance(history, dict):
        return issues
    bm = history.get("benchmark_indices")
    if bm is None:
        return issues  # 缺失时使用默认值，正常
    if not isinstance(bm, dict):
        logger.warning("config.json history.benchmark_indices = %r 不是对象(dict)，将使用默认值", bm)
        return issues + 1
    for key, val in bm.items():
        if not isinstance(key, str) or len(key) < 3:
            logger.warning("config.json history.benchmark_indices 中存在无效键 %r，将被忽略", key)
            issues += 1
        if not isinstance(val, str):
            logger.warning("config.json history.benchmark_indices.%s = %r 不是字符串", key, val)
            issues += 1
    return issues


_FETCH_MODES = frozenset({"off", "prompt", "auto"})  # history.fetch_mode 合法取值


def _validate_history_fetch_mode(config: dict, issues: int) -> int:
    """验证 history.fetch_mode 配置（历史走势获取模式三态）。"""
    history = config.get("history", {})
    if not isinstance(history, dict):
        return issues
    mode = history.get("fetch_mode")
    if mode is None:
        return issues  # 缺失时使用默认值，正常
    if not isinstance(mode, str) or mode not in _FETCH_MODES:
        logger.warning(
            "config.json history.fetch_mode = %r 非法（应为 off/prompt/auto），将使用默认值 auto",
            mode,
        )
        return issues + 1
    return issues


def _validate_history_lookback_days(config: dict, issues: int) -> int:
    """验证 history.lookback_days 配置（历史走势取数窗口天数）。

    下限绑定 MIN_SPAN（回撤分析所需最少交易日），低于下限时回撤分析
    将判定数据不足；上限 365 对齐历史 K 线数据源最多返回条数。
    """
    history = config.get("history", {})
    if not isinstance(history, dict):
        return issues
    lookback = history.get("lookback_days")
    if lookback is None:
        return issues  # 缺失时使用默认值 90，正常
    try:
        days = int(lookback)
    except (ValueError, TypeError):
        logger.warning("config.json history.lookback_days = %r 不是有效整数，将使用默认值 90", lookback)
        return issues + 1
    if days < MIN_SPAN:
        logger.warning(
            "config.json history.lookback_days = %s 低于回撤分析所需最少 %d 个交易日，回撤分析将判定数据不足",
            days,
            MIN_SPAN,
        )
        issues += 1
    if days > 365:
        logger.warning("config.json history.lookback_days = %s 超过上限 365，历史 K 线数据源最多返回 365 条", days)
        issues += 1
    return issues


def _validate_comparison_indices(config: dict, issues: int) -> int:
    """验证 comparison_indices 配置。"""
    ci, issues = _section(config, "comparison_indices", dict, "对比指数池将使用默认值", issues)
    if ci is _MISSING:
        return issues
    for key, val in ci.items():
        if not isinstance(key, str) or len(key) < 3:
            logger.warning("config.json comparison_indices 中存在无效键 %r，将被忽略", key)
            issues += 1
        if not isinstance(val, str):
            logger.warning("config.json comparison_indices.%s = %r 不是字符串", key, val)
            issues += 1
    return issues


def _validate_comparison_candidates(config: dict, issues: int) -> int:
    """验证 comparison_candidates 候选基金代码列表。

    - 非列表 → 告警（候选比较子表按空处理）
    - 项非 6 位数字 → 告警（该项忽略）
    - 超过 10 只 → 告警（运行期截断前 10）
    """
    raw = config.get("comparison_candidates")
    if raw is None:
        return issues
    if not isinstance(raw, list):
        logger.warning("config.json comparison_candidates = %r 不是列表，将按空处理", raw)
        return issues + 1
    code_re = re.compile(r"^\d{6}$")
    for idx, item in enumerate(raw):
        if isinstance(item, str) and code_re.match(item.strip()):
            continue
        if isinstance(item, (int, float)):
            continue  # 数值型可经 get_comparison_candidates 归一化为 6 位码
        logger.warning("config.json comparison_candidates[%d] = %r 非法（应为 6 位基金代码），忽略", idx, item)
        issues += 1
    if len(raw) > 10:
        logger.warning("config.json comparison_candidates 超过 10 只上限，运行期仅比较前 10 只")
        issues += 1
    return issues


def _validate_rebalance_config(config: dict, issues: int) -> int:
    """验证 rebalance 配置段。"""
    rb, issues = _section(config, "rebalance", dict, "再平衡配置无效，将使用默认值", issues)
    if rb is _MISSING:
        return issues
    threshold = rb.get("threshold")
    if threshold is not None:
        try:
            t = float(threshold)
            if t <= 0 or t >= 1:
                logger.warning("config.json rebalance.threshold = %s 应在 0~1 之间，将使用默认值 0.15", t)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json rebalance.threshold = %r 不是有效数字，将使用默认值 0.15", threshold)
            issues += 1
    deviation = rb.get("deviation_threshold")
    if deviation is not None:
        try:
            d = float(deviation)
            if d <= 0 or d >= 1:
                logger.warning("config.json rebalance.deviation_threshold = %s 应在 0~1 之间，将使用默认值 0.05", d)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json rebalance.deviation_threshold = %r 不是有效数字，将使用默认值 0.05", deviation)
            issues += 1
    profile = rb.get("profile")
    if profile is not None:
        valid_profiles = ("conservative", "moderate", "aggressive", "custom")
        if profile not in valid_profiles:
            logger.warning(
                "config.json rebalance.profile = %r 无效，有效值: %s，将使用 moderate", profile, valid_profiles
            )
            issues += 1
    silence = rb.get("silence_days")
    if silence is not None:
        try:
            s = int(silence)
            if s < 0:
                logger.warning("config.json rebalance.silence_days = %s 不能为负数，将使用默认值 30", s)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json rebalance.silence_days = %r 不是有效整数，将使用默认值 30", silence)
            issues += 1
    target = rb.get("target_allocation")
    if target is not None:
        if not isinstance(target, dict):
            logger.warning("config.json rebalance.target_allocation = %r 不是对象(dict)，将忽略", target)
            issues += 1
        else:
            for key, val in target.items():
                if not isinstance(val, dict):
                    logger.warning("config.json rebalance.target_allocation.%s 不是对象，将忽略该项", key)
                    issues += 1
                    continue
                for f in ("min", "max", "target"):
                    fv = val.get(f)
                    if fv is not None and not isinstance(fv, (int, float)):
                        logger.warning("config.json rebalance.target_allocation.%s.%s = %r 不是数字", key, f, fv)
                        issues += 1
    efi = rb.get("equity_fixed_income")
    if efi is not None:
        if not isinstance(efi, dict):
            logger.warning("config.json rebalance.equity_fixed_income = %r 不是对象(dict)，将忽略", efi)
            issues += 1
        else:
            for key, val in efi.items():
                if key not in ("equity", "fixed_income"):
                    logger.warning(
                        "config.json rebalance.equity_fixed_income.%s 未知，有效键: equity, fixed_income", key
                    )
                    issues += 1
                if not isinstance(val, dict):
                    logger.warning("config.json rebalance.equity_fixed_income.%s 不是对象，将忽略该项", key)
                    issues += 1
                    continue
                for f in ("min", "max", "target"):
                    fv = val.get(f)
                    if fv is not None and not isinstance(fv, (int, float)):
                        logger.warning("config.json rebalance.equity_fixed_income.%s.%s = %r 不是数字", key, f, fv)
                        issues += 1
    return issues


def _validate_discipline_config(config: dict, issues: int) -> int:
    """验证 discipline 配置段（交易纪律：止盈/止损/回撤线 + 静默期）。

    数值语义约束：
      - 三类阈值必须为数字
      - 止盈线应为正数、止损线应为负数（符号约束同时保证「止盈线 > 止损线」，
        杜绝同一品种同时触发止盈与止损的误配）
    """
    ds, issues = _section(config, "discipline", dict, "交易纪律配置无效，将使用默认值", issues)
    if ds is _MISSING:
        return issues
    pcts: dict[str, float] = {}
    for key, default in (("take_profit_pct", 20.0), ("stop_loss_pct", -15.0), ("drawdown_pct", -10.0)):
        val = ds.get(key)
        if val is None:
            continue
        try:
            pcts[key] = float(val)
        except (ValueError, TypeError):
            logger.warning("config.json discipline.%s = %r 不是数字，将使用默认值 %s", key, val, default)
            issues += 1
    take_profit = pcts.get("take_profit_pct")
    if take_profit is not None and take_profit <= 0:
        logger.warning("config.json discipline.take_profit_pct = %s 应为正数，将使用默认值 20.0", take_profit)
        issues += 1
    stop_loss = pcts.get("stop_loss_pct")
    if stop_loss is not None and stop_loss >= 0:
        logger.warning("config.json discipline.stop_loss_pct = %s 应为负数，将使用默认值 -15.0", stop_loss)
        issues += 1
    # 符号约束（take_profit > 0 且 stop_loss < 0）已自动保证 take_profit > stop_loss，
    # 无需单独交叉校验，避免同一误配重复告警。
    silence = ds.get("silence_days")
    if silence is not None:
        try:
            s = int(silence)
            if s < 0:
                logger.warning("config.json discipline.silence_days = %s 不能为负数，将使用默认值 30", s)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json discipline.silence_days = %r 不是有效整数，将使用默认值 30", silence)
            issues += 1
    return issues


# ═══════════════════════════════════════════════════════════════════
# 配置校验入口
# ═══════════════════════════════════════════════════════════════════


def validate_config(config: dict | None = None) -> int:
    """校验 config.json 中的常见配置错误，输出 WARNING 日志。

    Args:
        config: 已合并的配置字典。为 None 时自动调用 get_config()。

    Returns:
        发现的问题数量（方便测试断言）。
    """
    if config is None:
        from src.python.config._core import get_config

        config = get_config()
    issues = 0
    issues = _validate_string_configs(config, issues)
    issues = _validate_news_top_count(config, issues)
    issues = _validate_cache_ttl(config, issues)
    issues = _validate_news_sources(config, issues)
    issues = _validate_preferred_provider(config, issues)
    issues = _validate_user_fund_benchmarks(config, issues)
    issues = _validate_enable_boards(config, issues)
    issues = _validate_market_hours(config, issues)
    issues = _validate_report_section_order(config, issues)
    issues = _validate_benchmark_indices(config, issues)
    issues = _validate_history_fetch_mode(config, issues)
    issues = _validate_history_lookback_days(config, issues)
    issues = _validate_comparison_indices(config, issues)
    issues = _validate_comparison_candidates(config, issues)
    issues = _validate_rebalance_config(config, issues)
    issues = _validate_discipline_config(config, issues)
    issues = _validate_enable_llm(issues)
    if issues:
        logger.warning("config.json 共检测到 %d 个配置问题，请检查上述警告项", issues)
    return issues
