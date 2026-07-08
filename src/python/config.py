"""配置管理模块 — 读写 data/config/config.json。

支持：
- 基础配置（持仓目录/文件名/输出目录等）
- 缓存 TTL 自定义
- LLM 外部配置文件引用（API Key 不直接存储在 config.json 中）
- config.json / llm_settings.json / llm_key.json 支持 ``//`` 单行注释和 ``/* */`` 多行注释
  （自动剥离后解析），方便按业务场景分组管理配置项。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from typing import Any

from src.python.constants import MODEL_PRICING
from src.python.registry import (
    get_cache_ttl_defaults,
    get_known_llm_settings_keys,
    get_report_section_keys,
)

logger = logging.getLogger("invest")

# 配置文件路径
_CONFIG_FILE = "data/config/config.json"

# 默认配置（按业务分组排列顺序，与模板 _get_default_config_template() 一致）
_DEFAULT_CONFIG = {
    # ── A. 路径与文件 ──
    "holdings_dir": "data/holdings",
    "holdings_filename": "个人投资持仓信息.xlsx",
    "output_dir": "reports",
    "llm_key_file": "data/config/llm_key.json",
    "llm_settings_file": "data/config/llm_settings.json",
    # ── B. 数据源与提供商 ──
    "news_top_count": 300,
    "news_sources": {
        "sina": True,
        "eastmoney": True,
        "cls": False,
        "wallstreetcn": True,
        "akshare": True,
    },
    "preferred_provider": {},
    # ── C. 市场时段与缓存 ──
    "market_hour_aware": ["price", "index"],
    "market_hour_ttl": 30,
    "market_hours": {
        "start": "09:30",
        "end": "15:00",
        "official_source": True,
    },
    "cache_ttl": get_cache_ttl_defaults(),
    # ── D. 行为调优 ──
    "default_menu_key": "L",
    "report_section_order": {},
    "early_warning": {
        "sector_alert_threshold_warning": -50_000_000,
        "sector_alert_threshold_danger": -200_000_000,
        "sentiment_top_n": 10,
    },
    "degradation": {
        "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},
        "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},
        "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14},
    },
    # ── E. 业绩基准 ──
    "user_fund_benchmarks": {},
}


# ── 配置缓存（线程安全，按 mtime 自动失效） ─────────────


def _get_default_config_template() -> str:
    """返回带分组注释的默认 config.json 模板字符串。

    与 _DEFAULT_CONFIG 保持语义一致，首次创建 config.json 时写入。
    使用 ``//`` 注释分组，由 _strip_json_comments() 剥离后解析。
    """
    ttl_json = json.dumps(get_cache_ttl_defaults(), ensure_ascii=False, indent=2)
    lines = ttl_json.split("\n")
    indented_ttl = "\n".join([lines[0]] + ["  " + line for line in lines[1:]])
    return (
        '{\n'
        '  // ── A. 路径与文件 ──\n'
        '  "holdings_dir": "data/holdings",\n'
        '  "holdings_filename": "个人投资持仓信息.xlsx",\n'
        '  "output_dir": "reports",\n'
        '  "llm_key_file": "data/config/llm_key.json",\n'
        '  "llm_settings_file": "data/config/llm_settings.json",\n'
        '\n'
        '  // ── B. 数据源与提供商 ──\n'
        '  "news_top_count": 300,\n'
        '  "news_sources": {\n'
        '    "sina": true,\n'
        '    "eastmoney": true,\n'
        '    "cls": false,\n'
        '    "wallstreetcn": true,\n'
        '    "akshare": true\n'
        '  },\n'
        '  "preferred_provider": {},\n'
        '\n'
        '  // ── C. 市场时段与缓存 ──\n'
        '  "market_hour_aware": ["price", "index"],\n'
        '  "market_hour_ttl": 30,\n'
        '  "market_hours": {\n'
        '    "start": "09:30",\n'
        '    "end": "15:00",\n'
        '    "official_source": true\n'
        '  },\n'
        f'  "cache_ttl": {indented_ttl},\n'
        '\n'
        '  // ── D. 行为调优 ──\n'
        '  "default_menu_key": "L",\n'
        '  "report_section_order": {},\n'
        '  "early_warning": {\n'
        '    "sector_alert_threshold_warning": -50000000,\n'
        '    "sector_alert_threshold_danger": -200000000,\n'
        '    "sentiment_top_n": 10\n'
        '  },\n'
        '  "degradation": {\n'
        '    "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},\n'
        '    "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},\n'
        '    "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14}\n'
        '  },\n'
        '\n'
        '  // ── E. 业绩基准 ──\n'
        '  "user_fund_benchmarks": {}\n'
        '}\n'
    )

_config_cache: dict | None = None
_config_mtime: float = 0
_config_size: int = 0
_config_lock = threading.Lock()


def get_config_path() -> str:
    """返回配置文件路径。"""
    return _CONFIG_FILE


def _clear_config_cache() -> None:
    """清空配置内存缓存（测试隔离用）。"""
    global _config_cache
    _config_cache = None


def get_config() -> dict:
    """
    读取配置文件并返回配置字典（带线程安全缓存）。

    缓存按文件修改时间自动失效。若配置文件不存在或内容损坏，返回默认配置。
    """
    global _config_cache, _config_mtime, _config_size

    config_path = get_config_path()
    if not os.path.exists(config_path):
        _config_cache = None
        return dict(_DEFAULT_CONFIG)

    with _config_lock:
        try:
            current_mtime = os.path.getmtime(config_path)
            current_size = os.path.getsize(config_path)
            if (_config_cache is not None
                    and current_mtime <= _config_mtime
                    and current_size == _config_size):
                return _config_cache
        except OSError:
            pass

        try:
            with open(config_path, encoding="utf-8-sig") as f:
                raw = f.read()
                cleaned = _strip_json_comments(raw)
                config = json.loads(cleaned)
            merged = dict(_DEFAULT_CONFIG)
            # 过滤 null 值：不允许 config.json 中的 null 覆盖默认值
            for key, val in config.items():
                if val is None and key in _DEFAULT_CONFIG:
                    continue
                merged[key] = val
            _config_cache = merged
            try:
                _config_mtime = os.path.getmtime(config_path)
                _config_size = os.path.getsize(config_path)
            except OSError:
                _config_mtime = 0
                _config_size = 0
            return merged
        except (OSError, json.JSONDecodeError):
            _config_cache = None
            logger.warning("配置文件 %s 读取失败，已回退到默认配置", config_path)
            return dict(_DEFAULT_CONFIG)


def set_config(key: str, value: Any) -> None:
    """
    更新配置项并持久化到文件。

    写入后自动失效配置缓存，确保后续 get_config() 读取最新内容。

    Args:
        key: 配置键名
        value: 配置值
    """
    global _config_cache, _config_mtime, _config_size

    config = get_config()
    config[key] = value

    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)

    # 确保父目录存在
    os.makedirs(config_dir, exist_ok=True)

    # 原子写入：先写临时文件再 os.replace，防止断电半写导致 config.json 截断
    fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, config_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise

    # 清除缓存，使下次 get_config() 重新读取
    _config_cache = None
    _config_mtime = 0
    _config_size = 0


# ── 已知的配置项枚举（用于配置校验） ──────────────────

_KNOWN_NEWS_SOURCES: set[str] = {"sina", "eastmoney", "cls", "wallstreetcn", "akshare"}

_KNOWN_PROVIDER_TYPES: set[str] = {"price", "fund_rank", "fund_hold", "industry"}

_KNOWN_PROVIDER_NAMES: set[str] = {"tencent", "eastmoney", "sina", "tiantian", "eastmoney_industry", "eastmoney_industry_rest"}

_STRING_CONFIG_KEYS: set[str] = {"holdings_dir", "holdings_filename", "output_dir",
                                  "llm_key_file", "llm_settings_file"}


# ── 配置校验辅助函数 ────────────────────────────────────────

_MISSING = object()


def _section(config: dict, key: str, expected_type: type, warn_msg: str,
             issues: int = 0) -> tuple[Any, int]:
    """读取配置段，校验类型，不存在/类型不匹配时返回 (_MISSING, issues)。

    封装所有校验函数重复的"get → None 检查 → isinstance → 日志"模式。
    调用方::

        val, issues = _section(config, "cache_ttl", dict, "消息")
        if val is _MISSING:
            return issues
    """
    val = config.get(key)
    if val is None:
        return _MISSING, issues
    if not isinstance(val, expected_type):
        logger.warning("config.json %s = %r 不是 %s，%s", key, val, expected_type.__name__, warn_msg)
        return _MISSING, issues + 1
    return val, issues


def _validate_string_configs(config: dict, issues: int) -> int:
    """校验字符串类型配置项。"""
    for key in _STRING_CONFIG_KEYS:
        val = config.get(key)
        if val is not None and not isinstance(val, str):
            logger.warning("config.json %s = %r 不是字符串类型，可能导致运行时 TypeError", key, val)
            issues += 1
    # holdings_filename 为空字符串时会导致 os.path.join 返回目录路径
    fn = config.get("holdings_filename")
    if isinstance(fn, str) and fn.strip() == "":
        logger.warning("config.json holdings_filename 为空字符串，将使用默认文件名")
        issues += 1
    return issues


def _validate_news_top_count(config: dict, issues: int) -> int:
    """校验 news_top_count 配置项。"""
    ntc = config.get("news_top_count")
    if ntc is None:
        return issues
    try:
        n_int = int(ntc)
        if n_int <= 0:
            logger.warning("config.json news_top_count = %r 不是正数，将使用默认值 100", ntc)
            issues += 1
    except (ValueError, TypeError):
        logger.warning("config.json news_top_count = %r 不是有效整数，将使用默认值 100", ntc)
        issues += 1
    return issues


def _validate_cache_ttl(config: dict, issues: int) -> int:
    """校验 cache_ttl 配置段。"""
    cache_ttl, issues = _section(config, "cache_ttl", dict, "所有缓存 TTL 将使用默认值", issues)
    if cache_ttl is _MISSING:
        return issues
    for k, v in cache_ttl.items():
        try:
            val = float(v)
            if val <= 0:
                logger.warning("config.json cache_ttl.%s = %s 不是正数，将使用默认值", k, v)
                issues += 1
        except (ValueError, TypeError):  # noqa: PERF203
            logger.warning("config.json cache_ttl.%s = %s 不是有效数字，将使用默认值", k, v)
            issues += 1
    return issues


def _validate_news_sources(config: dict, issues: int) -> int:
    """校验 news_sources 配置段。"""
    news_src, issues = _section(config, "news_sources", dict, "所有源将使用默认开关状态", issues)
    if news_src is _MISSING:
        return issues
    for key, val in news_src.items():
        if key not in _KNOWN_NEWS_SOURCES:
            logger.warning("config.json news_sources 中存在未知的源 %r，将被忽略", key)
            issues += 1
        if not isinstance(val, bool):
            logger.warning("config.json news_sources.%s = %r 不是布尔值，"
                           "非空字符串/数字会被当作 True 处理", key, val)
            issues += 1
    return issues


def _validate_preferred_provider(config: dict, issues: int) -> int:
    """校验 preferred_provider 配置段。"""
    pref, issues = _section(config, "preferred_provider", dict, "配置无效", issues)
    if pref is _MISSING:
        return issues
    for data_type, provider in pref.items():
        if data_type not in _KNOWN_PROVIDER_TYPES:
            logger.warning("config.json preferred_provider 中存在未知的数据类型 %r，"
                           "有效值: %s", data_type, ", ".join(sorted(_KNOWN_PROVIDER_TYPES)))
            issues += 1
        if provider not in _KNOWN_PROVIDER_NAMES:
            logger.warning("config.json preferred_provider.%s = %r 不是已知的 provider，"
                           "有效值: %s", data_type, provider,
                           ", ".join(sorted(_KNOWN_PROVIDER_NAMES)))
            issues += 1
    return issues


def _validate_user_fund_benchmarks(config: dict, issues: int) -> int:
    """校验 user_fund_benchmarks 配置段。"""
    ufb, issues = _section(config, "user_fund_benchmarks", dict, "自定义基准将忽略", issues)
    if ufb is _MISSING:
        return issues
    # 存在且类型正确 = 不需要进一步校验
    return issues


def _validate_early_warning(config: dict, issues: int) -> int:
    """校验 early_warning 配置段。"""
    ew, issues = _section(config, "early_warning", dict, "智能预警阈值将使用默认值", issues)
    if ew is _MISSING:
        return issues
    for ew_key in ("sector_alert_threshold_warning", "sector_alert_threshold_danger"):
        ew_val = ew.get(ew_key)
        if ew_val is not None:
            try:
                fv = float(ew_val)
                if fv >= 0:
                    logger.warning("config.json early_warning.%s = %s 应为负值（净流出阈值），当前值为正", ew_key, ew_val)
                    issues += 1
            except (ValueError, TypeError):
                logger.warning("config.json early_warning.%s = %s 不是有效数字", ew_key, ew_val)
                issues += 1
    sentiment_n = ew.get("sentiment_top_n")
    if sentiment_n is None:
        return issues
    try:
        sn = int(sentiment_n)
        if sn <= 0:
            logger.warning("config.json early_warning.sentiment_top_n = %s 不是正数", sentiment_n)
            issues += 1
    except (ValueError, TypeError):
        logger.warning("config.json early_warning.sentiment_top_n = %s 不是有效整数", sentiment_n)
        issues += 1
    return issues


def _validate_market_hours(config: dict, issues: int) -> int:
    """校验 market_hour_aware / market_hour_ttl / market_hours 配置段。"""
    # market_hour_aware：必须为列表，元素为字符串
    mha = config.get("market_hour_aware")
    if mha is not None and (not isinstance(mha, list) or not all(isinstance(x, str) for x in mha)):
        logger.warning("config.json market_hour_aware = %r 不是字符串列表，将使用默认值 [\"price\", \"index\"]", mha)
        issues += 1
    # market_hour_ttl：必须为正整数
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
    # market_hours：必须为 dict，含有效 start/end 时间
    mh = config.get("market_hours")
    if mh is not None:
        if not isinstance(mh, dict):
            logger.warning("config.json market_hours = %r 不是对象(dict)，将使用内置默认时段", mh)
            issues += 1
        else:
            for time_key in ("start", "end"):
                tv = mh.get(time_key)
                if tv is not None and not isinstance(tv, str):
                    logger.warning("config.json market_hours.%s = %r 不是字符串，将使用默认值", time_key, tv)
                    issues += 1
    return issues


def _validate_report_section_order(config: dict, issues: int) -> int:
    """校验 report_section_order 配置段。

    检查项：
      - report_section_order 是否为 dict
      - 模块标识是否合法（在 _REPORT_SECTION_DEFAULT 中）
      - 配置的序号是否为正整数
      - 序号是否重复
      - llm_usage 不应出现在配置中（强制末尾）
    """
    order, issues = _section(config, "report_section_order", dict, "将使用默认顺序", issues)
    if order is _MISSING:
        return issues

    valid_keys = get_report_section_keys()
    seen_numbers: set[int] = set()

    for key, num in order.items():
        # 检查 llm_usage（设计上它不参与配置）
        if key == "llm_usage":
            logger.warning("config.json report_section_order 中不应包含 llm_usage，"
                           "该模块固定为最后一位，配置将被忽略")
            issues += 1
            continue
        # 检查未知标识
        if key not in valid_keys:
            logger.warning("config.json report_section_order 中存在未知的模块标识 %r，将被忽略", key)
            issues += 1
            continue
        # 检查非整数 / 负值
        try:
            n = int(num)
            if n < 1:
                logger.warning("config.json report_section_order.%s = %s 不是正数，将使用默认序号", key, num)
                issues += 1
                continue
        except (ValueError, TypeError):
            logger.warning("config.json report_section_order.%s = %s 不是有效整数，将使用默认序号", key, num)
            issues += 1
            continue
        # 检查重复序号
        if n in seen_numbers:
            logger.warning("config.json report_section_order 中存在重复序号 %s（%s），请检查", n, key)
            issues += 1
        else:
            seen_numbers.add(n)

    return issues


def validate_config(config: dict | None = None) -> int:
    """校验 config.json 中的常见配置错误，输出 WARNING 日志。

    Args:
        config: 已合并的配置字典。为 None 时自动调用 get_config()。

    Returns:
        发现的问题数量（方便测试断言）。
    """
    if config is None:
        config = get_config()
    issues = 0

    issues = _validate_string_configs(config, issues)
    issues = _validate_news_top_count(config, issues)
    issues = _validate_cache_ttl(config, issues)
    issues = _validate_news_sources(config, issues)
    issues = _validate_preferred_provider(config, issues)
    issues = _validate_user_fund_benchmarks(config, issues)
    issues = _validate_early_warning(config, issues)
    issues = _validate_market_hours(config, issues)
    issues = _validate_report_section_order(config, issues)

    if issues:
        logger.warning("config.json 共检测到 %d 个配置问题，请检查上述警告项", issues)
    return issues


def init_config() -> None:
    """初始化配置文件。

    若 config.json 不存在，则自动用默认配置创建并写入磁盘。
    若文件已存在，不做任何操作。
    """
    global _config_cache, _config_mtime, _config_size

    config_path = get_config_path()
    if os.path.exists(config_path):
        config = get_config()
        validate_config(config)  # 全面校验配置
        return
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(_get_default_config_template())
    # 清除缓存，使后续 get_config() 从新文件读取
    _config_cache = None
    _config_mtime = 0
    _config_size = 0
    logger.info("配置文件已自动生成: %s", config_path)

    # 同时初始化 llm_settings.json
    _ensure_llm_settings_file()


def _get_default_llm_settings_template() -> str:
    """返回带分组注释的默认 llm_settings.json 模板字符串。

    模块按业务分组：全局设置 → 模块开关 → 各 LLM 模块 → 计价配置。
    使用 ``//`` 注释分组，由 _strip_json_comments() 剥离后解析。
    """
    pricing_json = json.dumps({"currency": "CNY", **MODEL_PRICING}, ensure_ascii=False, indent=4)
    pricing_lines = pricing_json.split("\n")
    indented_pricing = "\n".join([pricing_lines[0]] + ["    " + line for line in pricing_lines[1:]])
    return (
        '{\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 全局设置\n'
        '  // ═══════════════════════════════════════════\n'
        '  "max_retries": 2,\n'
        '  "llm_max_concurrency": 3,\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 模块开关 — 控制各 LLM 分析功能的启用/停用\n'
        '  // ═══════════════════════════════════════════\n'
        '  "enabled_llm": {\n'
        '    "global_macro": true,\n'
        '    "expert_review": true,\n'
        '    "health_check": true,\n'
        '    "penetration_deep": true,\n'
        '    "news_correlation": false\n'
        '  },\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 全球政经局势 — global_macro\n'
        '  // ═══════════════════════════════════════════\n'
        '  "system_prompt_global_macro": null,\n'
        '  "model_global_macro": null,\n'
        '  "temperature_global_macro": 0.3,\n'
        '  "max_tokens_global_macro": 1024,\n'
        '  "timeout_global_macro": 60,\n'
        '  "cache_enabled_global_macro": true,\n'
        '  "output_brief_global_macro": false,\n'
        '  "thinking_enabled_global_macro": false,\n'
        '  "thinking_budget_global_macro": 4000,\n'
        '  "reasoning_effort_global_macro": "high",\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 智囊团深度复盘 — expert_review\n'
        '  // ═══════════════════════════════════════════\n'
        '  "system_prompt_expert_review": null,\n'
        '  "model_expert_review": null,\n'
        '  "temperature_expert_review": 0.8,\n'
        '  "max_tokens_expert_review": 8192,\n'
        '  "timeout_expert_review": 120,\n'
        '  "cache_enabled_expert_review": true,\n'
        '  "output_brief_expert_review": false,\n'
        '  "thinking_enabled_expert_review": true,\n'
        '  "thinking_budget_expert_review": 16000,\n'
        '  "reasoning_effort_expert_review": "high",\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 持仓体检报告 — health_check\n'
        '  // ═══════════════════════════════════════════\n'
        '  "system_prompt_health_check": null,\n'
        '  "model_health_check": null,\n'
        '  "temperature_health_check": 0.5,\n'
        '  "max_tokens_health_check": 4096,\n'
        '  "timeout_health_check": 120,\n'
        '  "cache_enabled_health_check": true,\n'
        '  "output_brief_health_check": false,\n'
        '  "thinking_enabled_health_check": true,\n'
        '  "thinking_budget_health_check": 12000,\n'
        '  "reasoning_effort_health_check": "high",\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 穿透深度分析 — penetration_deep\n'
        '  // ═══════════════════════════════════════════\n'
        '  "system_prompt_penetration_deep": null,\n'
        '  "model_penetration_deep": null,\n'
        '  "temperature_penetration_deep": 0.4,\n'
        '  "max_tokens_penetration_deep": 4096,\n'
        '  "timeout_penetration_deep": 90,\n'
        '  "cache_enabled_penetration_deep": true,\n'
        '  "output_brief_penetration_deep": false,\n'
        '  "thinking_enabled_penetration_deep": false,\n'
        '  "thinking_budget_penetration_deep": 8000,\n'
        '  "reasoning_effort_penetration_deep": "high",\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 财经新闻热点与持仓关联分析 — news_correlation\n'
        '  // （注：news_correlation 不支持 output_brief 模式）\n'
        '  // ═══════════════════════════════════════════\n'
        '  "system_prompt_news_correlation": null,\n'
        '  "model_news_correlation": null,\n'
        '  "temperature_news_correlation": 0.1,\n'
        '  "max_tokens_news_correlation": 2000,\n'
        '  "timeout_news_correlation": 60,\n'
        '  "cache_enabled_news_correlation": true,\n'
        '  "thinking_enabled_news_correlation": false,\n'
        '  "thinking_budget_news_correlation": 4000,\n'
        '  "reasoning_effort_news_correlation": "high",\n'
        '\n'
        '  // ═══════════════════════════════════════════\n'
        '  // 计价配置\n'
        '  // ═══════════════════════════════════════════\n'
        f'  "pricing": {indented_pricing}\n'
        '}\n'
    )


def _ensure_llm_settings_file() -> None:
    """若 llm_settings.json 不存在，用默认值自动创建。"""
    settings_path = get_llm_settings_path()
    if os.path.exists(settings_path):
        return
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(_get_default_llm_settings_template())
        logger.info("LLM 设置文件已自动生成: %s", settings_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM 设置文件: %s", e)


# ── LLM 配置读取（外部文件） ─────────────────────────────────


def get_llm_key_path() -> str:
    """返回 LLM 密钥配置文件的路径 (llm_key.json)。

    从 data/config/config.json 中的 llm_key_file 字段读取，
    若未配置则默认返回 "data/config/llm_key.json"。
    """
    config = get_config()
    return config.get("llm_key_file", "data/config/llm_key.json")


def get_llm_settings_path() -> str:
    """返回 LLM 非敏感配置文件的路径 (llm_settings.json)。

    从 data/config/config.json 中的 llm_settings_file 字段读取，
    若未配置则默认返回 "data/config/llm_settings.json"。
    """
    config = get_config()
    return config.get("llm_settings_file", "data/config/llm_settings.json")


# ── LLM 配置缓存（按文件修改时间自动失效） ──────────────────

# 已知的 llm_settings.json 合法键名集合，用于启动时未知键名告警
# 由中央注册表 registry.py 自动派生，不再硬编码
_KNOWN_LLM_SETTINGS_KEYS: set[str] = get_known_llm_settings_keys()


def _check_unknown_llm_keys(settings: dict) -> None:
    """检查 llm_settings.json 中是否存在未知键名，若有则输出 WARNING。

    Args:
        settings: 从 llm_settings.json 读取的配置字典
    """
    unknown = [key for key in settings if key not in _KNOWN_LLM_SETTINGS_KEYS]
    if unknown:
        logger.warning(
            "llm_settings.json 中检测到 %d 个未知配置项，可能是拼写错误或已废弃的配置: %s。"
            "请核对后删除，避免混淆。",
            len(unknown), ", ".join(repr(k) for k in sorted(unknown)),
        )

_llm_config_cache: dict | None = None
_llm_config_mtime: float = 0
_llm_config_size: int = 0
_llm_config_lock = threading.Lock()


# ── JSON 注释剥离（用于 llm_settings.json / llm_key.json） ──


def _strip_json_comments(text: str) -> str:
    """剥离 JSON 中的 ``//`` 单行注释和 ``/* */`` 多行注释。

    正确处理字符串中的转义引号，不会将字符串内的 ``//`` / ``/*`` 误伤。

    Args:
        text: 可能包含注释的 JSON 文本

    Returns:
        不含注释的纯 JSON 文本
    """
    # 逐个字符扫描，仅在字符串外识别注释
    result: list[str] = []
    i = 0
    length = len(text)
    in_string = False
    in_single_line_comment = False
    in_multi_line_comment = False

    while i < length:
        ch = text[i]

        # ── 字符串内：只处理转义引号 ────────────────────────
        if in_string:
            result.append(ch)
            if ch == '\\':
                i += 1
                if i < length:
                    result.append(text[i])
            elif ch == '"':
                in_string = False
            i += 1
            continue

        # ── 多行注释内 ──────────────────────────────────────
        if in_multi_line_comment:
            if ch == '*' and i + 1 < length and text[i + 1] == '/':
                i += 2  # 跳过 */
                in_multi_line_comment = False
            else:
                i += 1
            continue

        # ── 单行注释内 ──────────────────────────────────────
        if in_single_line_comment:
            if ch == '\n':
                in_single_line_comment = False
                result.append(ch)
            i += 1
            continue

        # ── 注释起始检测（仅在字符串外） ─────────────────────
        if ch == '/' and i + 1 < length:
            nxt = text[i + 1]
            if nxt == '/':
                in_single_line_comment = True
                i += 2
                continue
            if nxt == '*':
                in_multi_line_comment = True
                i += 2
                continue

        # ── 字符串起始 ────────────────────────────────────
        if ch == '"':
            in_string = True

        result.append(ch)
        i += 1

    return "".join(result)


def get_llm_config() -> dict | None:
    """读取 LLM 配置（合并 llm_settings.json + llm_key.json）。

    配置优先级（高 → 低）：
      1. llm_key.json 中的字段（provider, api_key, model, endpoint）
      2. llm_settings.json 中的字段（其余所有非敏感配置）
      3. 代码内置默认值（_ensure_llm_settings_file() 自动创建时写入）

    缓存按 llm_settings.json 和 llm_key.json 的修改时间联合失效。
    """
    global _llm_config_cache, _llm_config_mtime, _llm_config_size

    with _llm_config_lock:
        # ── 基础层：llm_settings.json ──
        base_settings: dict = {}
        settings_mtime: float = 0
        settings_path = get_llm_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, encoding="utf-8-sig") as f:
                    raw = f.read()
                    cleaned = _strip_json_comments(raw)
                    base_settings = json.loads(cleaned)
                settings_mtime = os.path.getmtime(settings_path)
                # 首次加载时检测未知键名（仅在 cache 未初始化时告警一次）
                if _llm_config_cache is None and base_settings:
                    _check_unknown_llm_keys(base_settings)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("LLM 设置文件读取失败: %s", e)

        # ── 覆盖层：llm_key.json ──
        key_path = get_llm_key_path()
        if not os.path.exists(key_path):
            logger.warning("LLM 密钥文件不存在: %s", key_path)
            if base_settings.get("api_key"):
                base_settings["api_key"] = base_settings["api_key"].strip()
                _llm_config_cache = base_settings
                _llm_config_mtime = 0
                _llm_config_size = 0
                return base_settings
            _llm_config_cache = None
            return None

        try:
            key_mtime = os.path.getmtime(key_path)
            key_size = os.path.getsize(key_path)
            settings_size = os.path.getsize(settings_path) if os.path.exists(settings_path) else 0
            combined_mtime = max(key_mtime, settings_mtime)
            combined_size = key_size + settings_size

            if (_llm_config_cache is not None
                    and combined_mtime <= _llm_config_mtime
                    and combined_size == _llm_config_size):
                return _llm_config_cache

            with open(key_path, encoding="utf-8-sig") as f:
                key_raw = f.read()
                key_config = json.loads(_strip_json_comments(key_raw))

            # 校验配置
            provider = key_config.get("provider", "")
            endpoint = key_config.get("endpoint", "")
            if provider and provider not in ("claude", "openai"):
                logger.warning("llm_key.json provider = '%s' 不是有效值（应为 'claude' 或 'openai'）", provider)
            if endpoint and not endpoint.startswith("http"):
                logger.warning("llm_key.json endpoint = '%s' 不是有效 URL（应以 http 开头）", endpoint)

            # 合并：base_settings 为基础，key_config 覆盖（仅敏感字段）
            merged = dict(base_settings)
            merged.update(key_config)
            # 去除 api_key 首尾空格，避免因配置文件误含空格导致认证失败
            if merged.get("api_key"):
                merged["api_key"] = merged["api_key"].strip()

            _llm_config_cache = merged
            _llm_config_mtime = combined_mtime
            _llm_config_size = combined_size
            return merged
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("LLM 密钥文件读取失败: %s", e)
            _llm_config_cache = None
            return None
