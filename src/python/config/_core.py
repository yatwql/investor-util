"""config.json 读写缓存中枢 — 读取 / 写入 / 章节开关协调。

解析协调者而非独占解析器：注释剥离委托 `_comments`、路径绝对化委托 `_validation`、
顶层键 patch 引擎委托 `_json_patch`（本模块只保留 config.json 专用胶水与调用）。
其余配置文件（llm_settings / llm_key / llm_providers / features）各有独立解析器，
本模块仅触发文件存在性（`_ensure_llm_settings_file()` / `_ensure_llm_providers_file()`）。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from typing import Any

from src.python.config import _comments, _config_defaults, _llm_providers
from src.python.config._json_patch import (
    _find_top_level_value_span,
    _patch_config_key,
    _remove_top_level_key,
)
from src.python.config._llm_providers_defaults import _get_default_llm_providers_template
from src.python.config._validation import (
    _PATH_CONFIG_KEYS,
    _absolutize_paths,
    _deabsolutize_paths,
    _is_abs,
    validate_config,
)

# 从 _llm_providers 模块再导出（保持向后兼容，供测试导入）
from src.python.config._llm_providers import (
    _inject_provider_chain_data,
    _load_llm_providers,
    _parse_providers_list,
    _validate_provider_entry,
)

# 从 _llm_settings 模块再导出（保持向后兼容，供外部/测试从 _core 导入）
from src.python.config._llm_settings import (
    _KNOWN_LLM_SETTINGS_KEYS,
    _check_unknown_llm_keys,
    _ensure_llm_settings_file,
    _llm_config_cache,
    _llm_config_lock,
    _llm_config_mtime,
    _llm_config_size,
    _merge_llm_defaults,
    get_llm_config,
    get_llm_settings_path,
    invalidate_llm_config_cache,
    is_enable_llm,
)

logger = logging.getLogger("invest")


def _atomic_write(filepath: str, content: str) -> None:
    """原子写入文件：先写临时文件再 os.replace。

    Args:
        filepath: 目标文件路径
        content: 要写入的字符串内容
    """
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


# ═══════════════════════════════════════════════════════════════
# 配置缓存（线程安全，按 mtime 自动失效）
# ═══════════════════════════════════════════════════════════════

_config_cache: dict | None = None
_config_mtime: float = 0
_config_size: int = 0
_config_lock = threading.RLock()


def _clear_config_cache() -> None:
    """清空配置内存缓存（测试隔离用）。"""
    global _config_cache
    _config_cache = None


def invalidate_config_cache() -> None:
    """使 config.json 缓存失效，下次 get_config() 自动重读。"""
    global _config_cache, _config_mtime, _config_size
    with _config_lock:
        _config_cache = None
        _config_mtime = 0
        _config_size = 0


def get_config(_strict: bool = False) -> dict:
    """
    读取配置文件并返回配置字典（带线程安全缓存）。

    缓存按文件修改时间自动失效。若配置文件不存在或内容损坏，返回默认配置。

    Args:
        _strict: 内部参数。True 时若文件存在但读取失败则抛异常（供 set_config
                 使用，避免基于损坏/读取失败的默认配置覆盖写入丢失已有配置项）。
                 普通读取（get_config() 缺省调用）仍保持静默回退降级策略。
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
            if _config_cache is not None and current_mtime <= _config_mtime and current_size == _config_size:
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
            # 嵌套 dict 合并：允许用户只覆盖部分子键（如 history.fetch_mode）而不丢失默认值
            for key, val in config.items():
                if val is None and key in _config_defaults._DEFAULT_CONFIG:
                    continue
                if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
                    merged[key] = {**merged[key], **val}
                else:
                    merged[key] = val
            # 兼容旧配置键：history.analysis 自动迁移为 history.fetch_mode
            # 依据原始用户配置判断（合并后 history 始终含默认 fetch_mode，无法区分来源）
            _raw_history = config.get("history")
            if isinstance(_raw_history, dict) and "analysis" in _raw_history:
                _hist = merged.setdefault("history", {})
                if "fetch_mode" not in _raw_history:
                    _hist["fetch_mode"] = _raw_history["analysis"]
                _hist.pop("analysis", None)
                logger.warning("config.json history.analysis 已更名为 history.fetch_mode，已自动迁移")
            # 绝对化路径键：用户 config.json 中可使用相对路径，运行时统一转为绝对路径
            _absolutize_paths(merged)
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
            if _strict and os.path.exists(config_path):
                logger.warning("配置文件 %s 读取失败，中止配置写入", config_path)
                raise
            logger.warning("配置文件 %s 读取失败，已回退到默认配置", config_path)
            return dict(_config_defaults._DEFAULT_CONFIG)


def _patch_value_for_write(key: str, value: Any) -> str:
    """将 set_config 的目标值序列化为写盘文本（路径键反绝对化）。"""
    if key in _PATH_CONFIG_KEYS and isinstance(value, str) and _is_abs(value):
        one = {key: value}
        _deabsolutize_paths(one)
        value = one[key]
    return json.dumps(value, ensure_ascii=False)


def _persist_config_patch(new_raw: str, op: str) -> None:
    """校验 patch/删除后的 JSON 合法性并原子写盘 + 失效缓存（set/del 共用收尾）。

    防御：patch/删除结果必须仍是合法 JSON（定位/清理异常时拒绝落盘坏文件）。

    Args:
        new_raw: patch 或删除后的完整文本（须为合法 JSON）
        op: 操作名（如 "单键 patch"/"删除键"），仅用于错误日志
    """
    global _config_cache, _config_mtime, _config_size
    try:
        json.loads(_comments._strip_json_comments(new_raw))
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("config.json %s 后结果非法，拒绝写入: %s", op, e)
        raise
    config_path = _config_defaults.get_config_path()
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    _atomic_write(config_path, new_raw)
    _config_cache = None
    _config_mtime = 0
    _config_size = 0


def set_config(key: str, value: Any) -> None:
    """更新配置项并持久化到文件。

    写入策略：**基于磁盘原始文本做单键 patch**——仅替换目标键的 value，
    保留 config.json 的分组注释、行尾注释、其他键与相对路径（不再全量
    json.dumps 重写，避免剥掉用户可读的注释分组）。键不存在时追加到对象末尾。
    写入后自动失效配置缓存，确保后续 get_config() 读取最新内容。

    Args:
        key: 配置键名
        value: 配置值
    """
    global _config_cache, _config_mtime, _config_size

    config_path = _config_defaults.get_config_path()
    # 整个 读-改-写 纳入锁内串行化，避免并发线程基于旧快照覆盖写丢失已有配置项
    # （RLock 可重入，内部 get_config 再次获取同一锁不冲突）
    with _config_lock:
        # 读取磁盘原始文本（保留注释）；文件不存在/空白 → 用默认模板打底，
        # 使首次 set_config 创建的文件同样带完整分组注释。
        raw: str | None = None
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8-sig") as f:
                raw = f.read()
        if raw is None or not raw.strip():
            raw = _config_defaults._get_default_config_template()

        # 校验原文件可解析（保持 _strict 语义：损坏则中止，避免基于损坏文件覆盖写）
        try:
            json.loads(_comments._strip_json_comments(raw))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("config.json 内容损坏，中止写入: %s", e)
            raise

        # 目标键反绝对化后序列化，单键 patch（顶层键引擎在 _json_patch）
        value_text = _patch_value_for_write(key, value)
        new_raw = _patch_config_key(raw, key, value_text)
        _persist_config_patch(new_raw, "单键 patch")


def del_config(key: str) -> None:
    """删除配置项并持久化到文件（保留分组注释与其他键）。

    与 set_config 同构：基于磁盘原始文本定位键的 value 区间，删除整个键条目
    （含行尾注释与分隔逗号）。键不存在时静默返回，不触发写入。
    写入后自动失效配置缓存。

    Args:
        key: 要删除的配置键名
    """
    global _config_cache, _config_mtime, _config_size

    config_path = _config_defaults.get_config_path()
    with _config_lock:
        if not os.path.exists(config_path):
            return
        with open(config_path, encoding="utf-8-sig") as f:
            raw = f.read()
        # 校验原文件可解析（保持 _strict 语义：损坏则中止）
        try:
            json.loads(_comments._strip_json_comments(raw))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("config.json 内容损坏，中止删除: %s", e)
            raise
        span = _find_top_level_value_span(raw, key)
        if span is None:
            return  # 键不存在，无需删除
        vs, ve = span
        new_raw = _remove_top_level_key(raw, key, vs, ve)
        _persist_config_patch(new_raw, "删除键")


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
    try:
        _atomic_write(config_path, _config_defaults._get_default_config_template())
    except PermissionError:
        # Windows 并发场景：另一线程/进程已创建文件，清理自身临时文件后继续
        if os.path.exists(config_path):
            config = get_config()
            validate_config(config)
            return
        raise  # 文件确实不存在，重新抛出
    _config_cache = None
    _config_mtime = 0
    _config_size = 0
    logger.info("配置文件已自动生成: %s", config_path)

    _ensure_llm_settings_file()
    _ensure_llm_providers_file()


# ═══════════════════════════════════════════════════════════════
# 章节可见性读取函数
# ═══════════════════════════════════════════════════════════════


def is_enable_fund_deep_analysis(config: dict | None = None) -> bool:
    """基金深度分析章节（基金业绩分析、基金经理变更监控等）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_fund_deep_analysis")
    if val is None:
        logger.debug("config.json 缺少 enable_fund_deep_analysis，使用默认值 true")
        return True
    return bool(val)


def is_enable_portfolio_evolution(config: dict | None = None) -> bool:
    """组合演进章节是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_portfolio_evolution")
    if val is None:
        logger.debug("config.json 缺少 enable_portfolio_evolution，使用默认值 true")
        return True
    return bool(val)


def is_enable_action(config: dict | None = None) -> bool:
    """行动建议独立章（决策行动）是否启用。缺失时返回 False（默认关）。

    行动建议章是新增能力，默认关闭——不开时报告维持现状（无此章），
    开启才出现行动板块与智囊团深度复盘行动摘要。
    """
    if config is None:
        config = get_config()
    val = config.get("enable_action")
    if val is None:
        logger.debug("config.json 缺少 enable_action，使用默认值 false")
        return False
    return bool(val)


def is_enable_news(config: dict | None = None) -> bool:
    """市场新闻（财经新闻热点与持仓关联分析）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_news")
    if val is None:
        logger.debug("config.json 缺少 enable_news，使用默认值 true")
        return True
    return bool(val)


def is_enable_history(config: dict | None = None) -> bool:
    """组合历史走势+回撤分析（组合历史走势与回撤）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_history")
    if val is None:
        logger.debug("config.json 缺少 enable_history，使用默认值 true")
        return True
    return bool(val)


def is_enable_data_quality(config: dict | None = None) -> bool:
    """数据质量仪表盘子模块是否启用。

    读取 `report_submodules.data_quality`，默认关（向后兼容，既有
    「数据源可用性矩阵」输出不变）。

    Args:
        config: 完整配置字典，为 None 时读取全局配置
    """
    if config is None:
        config = get_config()
    submodules = config.get("report_submodules")
    if not isinstance(submodules, dict):
        return False
    val = submodules.get("data_quality")
    if val is None:
        logger.debug("config.json 缺少 report_submodules.data_quality，使用默认值 false")
        return False
    return bool(val)


def is_enable_candidate_compare(config: dict | None = None) -> bool:
    """候选基金比较子表是否启用。

    读取 `report_submodules.candidate_compare`，默认关（向后兼容，既有
    「基金业绩分析」章输出不变）。

    Args:
        config: 完整配置字典，为 None 时读取全局配置
    """
    if config is None:
        config = get_config()
    submodules = config.get("report_submodules")
    if not isinstance(submodules, dict):
        return False
    val = submodules.get("candidate_compare")
    if val is None:
        logger.debug("config.json 缺少 report_submodules.candidate_compare，使用默认值 false")
        return False
    return bool(val)


def is_enable_cost_lots(config: dict | None = None) -> bool:
    """成本流水子模块是否启用（成本分档 + XIRR + 分红累计渲染）。

    读取 `report_submodules.cost_lots`，默认关（向后兼容，既有
    「投资分析汇总」/「市值核算明细表」/「持仓分类表」输出不变）。
    持仓 Excel 含「交易流水」「分红流水」页签时才建议开启。

    Args:
        config: 完整配置字典，为 None 时读取全局配置
    """
    if config is None:
        config = get_config()
    submodules = config.get("report_submodules")
    if not isinstance(submodules, dict):
        return False
    val = submodules.get("cost_lots")
    if val is None:
        logger.debug("config.json 缺少 report_submodules.cost_lots，使用默认值 false")
        return False
    return bool(val)


def is_enable_valuation_percentile(config: dict | None = None) -> bool:
    """估值分位子模块是否启用（「资产穿透TOP10」章估值分位列）。

    读取 `report_submodules.valuation_percentile`，默认关（向后兼容，
    「资产穿透TOP10」章既有输出不变）。

    Args:
        config: 完整配置字典，为 None 时读取全局配置
    """
    if config is None:
        config = get_config()
    submodules = config.get("report_submodules")
    if not isinstance(submodules, dict):
        return False
    val = submodules.get("valuation_percentile")
    if val is None:
        logger.debug("config.json 缺少 report_submodules.valuation_percentile，使用默认值 false")
        return False
    return bool(val)


def is_enable_market_temperature(config: dict | None = None) -> bool:
    """市场温度子模块是否启用（「投资分析汇总」章市场温度刻度行）。

    读取 `report_submodules.market_temperature`，默认关（向后兼容，
    「投资分析汇总」章既有输出不变）。

    Args:
        config: 完整配置字典，为 None 时读取全局配置
    """
    if config is None:
        config = get_config()
    submodules = config.get("report_submodules")
    if not isinstance(submodules, dict):
        return False
    val = submodules.get("market_temperature")
    if val is None:
        logger.debug("config.json 缺少 report_submodules.market_temperature，使用默认值 false")
        return False
    return bool(val)


def get_comparison_candidates(config: dict | None = None) -> list[str]:
    """候选基金比较子表候选基金代码列表。

    读取 `comparison_candidates`，返回 6 位基金代码字符串列表；
    缺失或非法类型返回空列表（安全降级，不抛错）。

    Args:
        config: 完整配置字典，为 None 时读取全局配置
    """
    if config is None:
        config = get_config()
    raw = config.get("comparison_candidates")
    if not isinstance(raw, list):
        if raw not in (None, ""):
            logger.warning("config.json comparison_candidates 非法（应为列表），忽略")
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item.strip())
        elif isinstance(item, (int, float)):
            result.append(str(int(item)).zfill(6))
        else:
            logger.warning("config.json comparison_candidates 含非法项 %r，忽略", item)
    return [c for c in result if c]


def _ensure_llm_providers_file() -> None:
    """若 llm_providers.json 不存在，用默认值自动创建。"""
    providers_path = _llm_providers._get_llm_providers_path()
    if os.path.exists(providers_path):
        return
    try:
        os.makedirs(os.path.dirname(providers_path), exist_ok=True)
        _atomic_write(providers_path, _get_default_llm_providers_template())
        logger.info("LLM Provider 配置文件已自动生成: %s", providers_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM Provider 配置文件: %s", e)
