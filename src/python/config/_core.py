"""核心配置逻辑 — 配置读写缓存 / 校验 / LLM 配置合并。"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from typing import Any

from src.python.config import _comments
from src.python.config import _config_defaults
from src.python.config._llm_defaults import _get_default_llm_settings_template
from src.python.registry import get_known_enabled_llm_keys, get_known_llm_settings_keys, get_report_section_keys

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
# 配置缓存（线程安全，按 mtime 自动失效）
# ═══════════════════════════════════════════════════════════════

_config_cache: dict | None = None
_config_mtime: float = 0
_config_size: int = 0
_config_lock = threading.Lock()


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

    config_path = _config_defaults.get_config_path()
    if not os.path.exists(config_path):
        _config_cache = None
        return dict(_config_defaults._DEFAULT_CONFIG)

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
                cleaned = _comments._strip_json_comments(raw)
                config = json.loads(cleaned)
            merged = dict(_config_defaults._DEFAULT_CONFIG)
            # 过滤 null 值：不允许 config.json 中的 null 覆盖默认值
            # 嵌套 dict 合并：允许用户只覆盖部分子键（如 history.analysis）而不丢失默认值
            for key, val in config.items():
                if val is None and key in _config_defaults._DEFAULT_CONFIG:
                    continue
                if (key in merged and isinstance(merged[key], dict)
                        and isinstance(val, dict)):
                    merged[key] = {**merged[key], **val}
                else:
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
            return dict(_config_defaults._DEFAULT_CONFIG)


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

    config_path = _config_defaults.get_config_path()
    config_dir = os.path.dirname(config_path)

    os.makedirs(config_dir, exist_ok=True)

    # 原子写入：先写临时文件再 os.replace
    fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, config_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise

    _config_cache = None
    _config_mtime = 0
    _config_size = 0


def init_config(config_path: str | None = None) -> None:
    """初始化配置文件。

    若 config.json 不存在，则自动用默认配置创建并写入磁盘。
    若文件已存在，不做任何操作。

    Args:
        config_path: 可选配置文件路径覆写（CLI --config 使用）。
                     为 None 时使用默认路径 data/config/config.json。
    """
    global _config_cache, _config_mtime, _config_size

    if config_path is not None:
        _config_defaults.set_config_path_override(config_path)

    config_path = _config_defaults.get_config_path()
    if os.path.exists(config_path):
        config = get_config()
        validate_config(config)
        return
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(_config_defaults._get_default_config_template())
    _config_cache = None
    _config_mtime = 0
    _config_size = 0
    logger.info("配置文件已自动生成: %s", config_path)

    _ensure_llm_settings_file()


# ═══════════════════════════════════════════════════════════════
# 配置校验
# ═══════════════════════════════════════════════════════════════

_KNOWN_NEWS_SOURCES: set[str] = {"sina", "eastmoney", "cls", "wallstreetcn", "akshare"}

_KNOWN_PROVIDER_TYPES: set[str] = {"price", "fund_rank", "fund_hold", "industry"}

_KNOWN_PROVIDER_NAMES: set[str] = {
    "tencent", "eastmoney", "sina", "tiantian",
    "eastmoney_industry", "eastmoney_industry_rest",
}

_STRING_CONFIG_KEYS: set[str] = {
    "holdings_dir", "holdings_filename", "output_dir",
    "llm_key_file", "llm_settings_file",
}

_MISSING = object()


def _section(config: dict, key: str, expected_type: type, warn_msg: str,
             issues: int = 0) -> tuple[Any, int]:
    """读取配置段，校验类型。"""
    val = config.get(key)
    if val is None:
        return _MISSING, issues
    if not isinstance(val, expected_type):
        logger.warning("config.json %s = %r 不是 %s，%s", key, val, expected_type.__name__, warn_msg)
        return _MISSING, issues + 1
    return val, issues


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
            logger.warning("config.json news_top_count = %r 不是正数，将使用默认值 100", ntc)
            issues += 1
    except (ValueError, TypeError):
        logger.warning("config.json news_top_count = %r 不是有效整数，将使用默认值 100", ntc)
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
            logger.warning("config.json news_sources.%s = %r 不是布尔值，"
                           "非空字符串/数字会被当作 True 处理", key, val)
            issues += 1
    return issues


def _validate_preferred_provider(config: dict, issues: int) -> int:
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
    ufb, issues = _section(config, "user_fund_benchmarks", dict, "自定义基准将忽略", issues)
    if ufb is _MISSING:
        return issues
    for code, benchmark in ufb.items():
        if not isinstance(code, str) or not code.strip():
            logger.warning("config.json user_fund_benchmarks 中存在非字符串或空字符串的基金代码 %r，该项将被忽略", code)
            issues += 1
            continue
        if not isinstance(benchmark, str) or not benchmark.strip():
            logger.warning("config.json user_fund_benchmarks.%s = %r 不是有效的基准名称（应为字符串），该项将被忽略", code, benchmark)
            issues += 1
    return issues


def _validate_enable_boards(config: dict, issues: int) -> int:
    """验证板块可见性配置（enable_b_series / enable_news / enable_history）。"""
    for key in ("enable_b_series", "enable_news", "enable_history"):
        val = config.get(key)
        if val is None:
            continue  # 缺失视为 True（向后兼容）
        if not isinstance(val, bool):
            logger.warning("config.json %s = %r 不是布尔值，将使用默认值 true", key, val)
            issues += 1
    return issues


def _validate_enable_llm(issues: int) -> int:
    """验证 llm_settings.json 中 enabled_llm 字典的子键。

    仅检查格式/拼写错误，不判断业务语义（全关正常——可能是用户主动关闭
    所有 LLM 报告模块但仍需 news_correlation）。缺失视为正常（向后兼容）。
    """
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
        logger.warning(
            "llm_settings.json enabled_llm 中存在未知模块 %s，请检查拼写", unknown
        )
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
    issues = _validate_enable_boards(config, issues)
    issues = _validate_market_hours(config, issues)
    issues = _validate_report_section_order(config, issues)
    issues = _validate_benchmark_indices(config, issues)
    issues = _validate_enable_llm(issues)
    if issues:
        logger.warning("config.json 共检测到 %d 个配置问题，请检查上述警告项", issues)
    return issues


# ═══════════════════════════════════════════════════════════════
# 板块可见性读取函数
# ═══════════════════════════════════════════════════════════════


def is_enable_b_series(config: dict | None = None) -> bool:
    """B 系列基金深度分析（#6~9）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_b_series")
    if val is None:
        logger.debug("config.json 缺少 enable_b_series，使用默认值 true")
        return True
    return bool(val)


def is_enable_news(config: dict | None = None) -> bool:
    """新闻（#10）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_news")
    if val is None:
        logger.debug("config.json 缺少 enable_news，使用默认值 true")
        return True
    return bool(val)


def is_enable_history(config: dict | None = None) -> bool:
    """组合历史走势+回撤分析（#16~17）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_history")
    if val is None:
        logger.debug("config.json 缺少 enable_history，使用默认值 true")
        return True
    return bool(val)


# ── LLM 板块可见性（来自 llm_settings.json enabled_llm） ──────

_REPORT_LLM_MODULES = frozenset({
    "global_macro", "expert_review", "health_check", "penetration_deep",
})


def is_enable_llm(config: dict | None = None) -> bool:
    """LLM 报告板块是否启用。

    检查 llm_settings.json 中 4 个 LLM 报告模块（global_macro /
    expert_review / health_check / penetration_deep）是否有任一启用。
    缺失时返回 True（向后兼容）。

    注意：news_correlation 仅用于新闻关联分析，不影响 LLM 板块整体可见性。
    """
    llm_config = get_llm_config()
    enabled_map = (llm_config or {}).get("enabled_llm", {})
    if not enabled_map:
        return True  # 缺失时默认启用
    return any(enabled_map.get(k, False) for k in _REPORT_LLM_MODULES)


# ═══════════════════════════════════════════════════════════════
# LLM 配置
# ═══════════════════════════════════════════════════════════════

_KNOWN_LLM_SETTINGS_KEYS: set[str] = get_known_llm_settings_keys()
_llm_config_cache: dict | None = None
_llm_config_mtime: float = 0
_llm_config_size: int = 0
_llm_config_lock = threading.Lock()


def _check_unknown_llm_keys(settings: dict) -> None:
    """检查 llm_settings.json 中是否存在未知键名。"""
    unknown = [key for key in settings if key not in _KNOWN_LLM_SETTINGS_KEYS]
    if unknown:
        logger.warning(
            "llm_settings.json 中检测到 %d 个未知配置项，可能是拼写错误或已废弃的配置: %s。"
            "请核对后删除，避免混淆。",
            len(unknown), ", ".join(repr(k) for k in sorted(unknown)),
        )



def _ensure_llm_settings_file() -> None:
    """若 llm_settings.json 不存在，用默认值自动创建。"""
    config = get_config()
    settings_path = config.get("llm_settings_file", "data/config/llm_settings.json")
    if os.path.exists(settings_path):
        return
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(_get_default_llm_settings_template())
        logger.info("LLM 设置文件已自动生成: %s", settings_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM 设置文件: %s", e)


def get_llm_key_path() -> str:
    """返回 LLM 密钥配置文件路径 (llm_key.json)。"""
    config = get_config()
    return config.get("llm_key_file", "data/config/llm_key.json")


def get_llm_settings_path() -> str:
    """返回 LLM 非敏感配置文件的路径 (llm_settings.json)。"""
    config = get_config()
    return config.get("llm_settings_file", "data/config/llm_settings.json")


def get_llm_config() -> dict | None:
    """读取 LLM 配置（合并 llm_settings.json + llm_key.json）。"""
    global _llm_config_cache, _llm_config_mtime, _llm_config_size

    with _llm_config_lock:
        base_settings: dict = {}
        settings_mtime: float = 0
        settings_path = get_llm_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, encoding="utf-8-sig") as f:
                    raw = f.read()
                    cleaned = _comments._strip_json_comments(raw)
                    base_settings = json.loads(cleaned)
                settings_mtime = os.path.getmtime(settings_path)
                if _llm_config_cache is None and base_settings:
                    _check_unknown_llm_keys(base_settings)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("LLM 设置文件读取失败: %s", e)

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
                key_config = json.loads(_comments._strip_json_comments(key_raw))

            provider = key_config.get("provider", "")
            endpoint = key_config.get("endpoint", "")
            if provider and provider not in ("claude", "openai"):
                logger.warning("llm_key.json provider = '%s' 不是有效值", provider)
            if endpoint and not endpoint.startswith("http"):
                logger.warning("llm_key.json endpoint = '%s' 不是有效 URL", endpoint)

            merged = dict(base_settings)
            merged.update(key_config)
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
