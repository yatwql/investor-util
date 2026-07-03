"""通用 JSON 文件缓存。

每个缓存项对应 `data/cache/{key}.json` 一个文件。
支持按秒级过期时间自动失效，写入时自动创建目录。
"""

from __future__ import annotations

import builtins
import gzip
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from typing import Any

from datetime import datetime, timezone, timedelta

from src.python.constants import CACHE_DAILY, CACHE_WEEKLY, CACHE_MONTHLY
from src.python.registry import get_cache_ttl_defaults, get_prefix_type_map, get_exact_type_map, get_registry
from src.python.market_hours import is_market_open as _is_market_open

_CACHE_DIR = "data/cache"
_GZIP_THRESHOLD = 100 * 1024  # 100KB 以上的缓存自动 gzip
_GZIP_SUFFIX = ".gz"

logger = logging.getLogger("invest")

_cache_lock = threading.Lock()

# ── 缓存命中率统计（线程安全） ───────────────────────────────
_cache_stats_lock = threading.Lock()
_cache_hits: int = 0
_cache_misses: int = 0


def _record_cache_hit() -> None:
    """记录一次缓存命中（线程安全）。"""
    global _cache_hits
    with _cache_stats_lock:
        _cache_hits += 1


def _record_cache_miss() -> None:
    """记录一次缓存未命中（线程安全）。"""
    global _cache_misses
    with _cache_stats_lock:
        _cache_misses += 1


def get_cache_hit_rate() -> dict[str, int | float]:
    """返回缓存命中率统计。

    Returns:
        {hits, misses, total, rate}
        rate 为 0.0~1.0 的浮点数，无可观测数据时返回 0.0
    """
    with _cache_stats_lock:
        hits = _cache_hits
        misses = _cache_misses
    total = hits + misses
    rate = round(hits / total, 4) if total > 0 else 0.0
    return {"hits": hits, "misses": misses, "total": total, "rate": rate}


def reset_cache_stats() -> None:
    """重置缓存命中率计数器。"""
    global _cache_hits, _cache_misses
    with _cache_stats_lock:
        _cache_hits = 0
        _cache_misses = 0


def _cache_path(key: str) -> str:
    """返回缓存文件完整路径（始终带 .json 后缀，由 get/set 决定是否追加 .gz）。"""
    # 防止目录穿越
    safe_name = key.replace("/", "_").replace("\\", "_").replace("..", "_")
    return os.path.join(_CACHE_DIR, f"{safe_name}.json")


def _read_cache_data(fpath: str, key: str, dry_run: bool = False) -> dict | None:
    """读取并解析单个缓存文件，返回载荷字典（含 _ts 和 _data 键）。

    自动识别 .json.gz（gzip 压缩）和 .json（纯文本）格式。
    文件损坏时自动删除并返回 None。

    Args:
        fpath: 缓存文件路径
        key: 缓存键名（仅用于日志）
        dry_run: True 时仅记录不删除损坏文件（用于 cleanup_expired 预览）

    Returns:
        解析后的字典载荷，文件不存在/损坏返回 None
    """
    if not os.path.exists(fpath):
        return None
    is_gz = fpath.endswith(_GZIP_SUFFIX)
    try:
        if is_gz:
            with open(fpath, "rb") as f:
                return json.loads(gzip.decompress(f.read()).decode("utf-8"))
        with open(fpath, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        if dry_run:
            logger.info("缓存清理(预览): 损坏文件 %s", os.path.basename(fpath))
        else:
            logger.warning("缓存文件 %s 损坏，自动删除: %s", key, e)
            try:
                os.remove(fpath)
                logger.info("已删除损坏的缓存文件: %s", key)
            except OSError:
                pass
        return None


def get(key: str, max_age_seconds: float) -> Any | None:
    """读取缓存，过期或不存在时返回 None。

    Args:
        key: 缓存键名（对应文件名，不含扩展名）
        max_age_seconds: 最大有效期（秒）

    Returns:
        缓存的数据（反序列化后的 Python 对象），过期/不存在返回 None
    """
    path = _cache_path(key)
    gz_path = path + _GZIP_SUFFIX

    # 优先读取 .json.gz，不存在则回退到 .json
    for fpath in (gz_path, path):
        data = _read_cache_data(fpath, key)
        if data is None:
            continue

        timestamp = data.get("_ts", 0)
        age = time.time() - timestamp
        if age > max_age_seconds:
            logger.debug("缓存 %s 已过期 (%.1fs > %.1fs)", key, age, max_age_seconds)
            _record_cache_miss()
            return None

        logger.debug("缓存命中: %s (age=%.1fs, max=%.1fs)", key, age, max_age_seconds)
        _record_cache_hit()
        return data.get("_data")

    _record_cache_miss()
    return None


def _write_atomic(
    fd: int, tmp_path: str, final_path: str,
    path: str, json_str: str, raw_bytes: bytes, use_gzip: bool,
) -> None:
    """原子写入：写临时文件 → os.replace 替换 → 清理旧格式。

    Args:
        fd: tempfile.mkstemp 返回的文件描述符
        tmp_path: 临时文件路径
        final_path: 最终目标文件路径（含 .json 或 .json.gz）
        path: 原始缓存路径（用于清理另一格式文件）
        json_str: JSON 序列化字符串
        raw_bytes: UTF-8 编码字节
        use_gzip: 是否 gzip 压缩

    Raises:
        OSError: IO 写入或替换失败
        FileNotFoundError: 临时文件所在目录被删除
    """
    if use_gzip:
        compressed = gzip.compress(raw_bytes)
        with os.fdopen(fd, "wb") as f:
            f.write(compressed)
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json_str)
    try:
        os.replace(tmp_path, final_path)
    except PermissionError:
        # Windows: replace 目标文件可能被锁，先删除再 rename
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(tmp_path, final_path)

    # 清理旧格式文件（防止 .json 和 .json.gz 同时存在）
    other_path = path if use_gzip else (path + _GZIP_SUFFIX)
    if os.path.exists(other_path):
        try:
            os.remove(other_path)
        except OSError:
            pass


def set(key: str, data: Any) -> None:
    """写入缓存。使用临时文件 + 原子替换保证线程安全。

    Args:
        key: 缓存键名
        data: 任意可 JSON 序列化的数据
    """
    path = _cache_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    payload = {"_ts": time.time(), "_data": data}
    try:
        json_str = json.dumps(payload, ensure_ascii=False, indent=2)
        raw_bytes = json_str.encode("utf-8")
        use_gzip = len(raw_bytes) > _GZIP_THRESHOLD
        final_path = path + _GZIP_SUFFIX if use_gzip else path
    except (TypeError, ValueError, OverflowError):
        logger.warning("缓存序列化失败 %s: 数据无法 JSON 序列化", key)
        return

    # 先写临时文件，再 os.replace 原子替换，防止并发读取时读到不完整的 JSON
    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    except (IOError, OSError):
        # tempfile.mkstemp 失败（如磁盘满、权限不足），直接返回
        logger.warning("缓存写入失败 %s: 无法创建临时文件", key)
        return

    try:
        _write_atomic(fd, tmp_path, final_path, path, json_str, raw_bytes, use_gzip)
        logger.debug("缓存已写入: %s", key)
    except FileNotFoundError:
        # 目录可能在 makedirs 后被外部删除，重试一次
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd2, tmp_path2 = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            try:
                _write_atomic(fd2, tmp_path2, final_path, path, json_str, raw_bytes, use_gzip)
                logger.debug("缓存已写入(重试成功): %s", key)
            except (IOError, OSError) as e2:
                logger.warning("缓存写入失败(重试后) %s: %s", key, e2)
                try:
                    os.remove(tmp_path2)
                except OSError:
                    pass
        except (IOError, OSError) as e2:
            logger.warning("缓存写入失败(重试后) %s: %s", key, e2)
    except (IOError, OSError) as e:
        logger.warning("缓存写入失败 %s: %s", key, e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def clear(key: str) -> None:
    """删除指定缓存文件（同时处理 .json 和 .json.gz）。"""
    with _cache_lock:
        path = _cache_path(key)
        gz_path = path + _GZIP_SUFFIX
        for p in (path, gz_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
                    logger.debug("缓存已清除: %s", key)
            except OSError as e:
                logger.warning("缓存清除失败 %s: %s", key, e)


def clear_by_prefix(key_prefix: str) -> int:
    """清除所有键名以指定前缀开头的缓存文件（同时处理 .json 和 .json.gz）。

    Args:
        key_prefix: 缓存键名前缀，如 ``"fund_perf_"``

    Returns:
        已清除的文件数量
    """
    with _cache_lock:
        count = 0
        if not os.path.isdir(_CACHE_DIR):
            return 0
        for fname in os.listdir(_CACHE_DIR):
            # 识别 .json 和 .json.gz
            if fname.endswith(".json.gz"):
                fkey = fname[:-8]  # 去掉 .json.gz
            elif fname.endswith(".json"):
                fkey = fname[:-5]  # 去掉 .json
            else:
                continue
            if fkey.startswith(key_prefix):
                try:
                    os.remove(os.path.join(_CACHE_DIR, fname))
                    count += 1
                    logger.debug("缓存已清除: %s", fkey)
                except OSError as e:
                    logger.warning("缓存清除失败 %s: %s", fkey, e)
    return count


def clear_by_group(group_name: str) -> dict[str, int]:
    """清除指定缓存组的所有缓存文件。

    从 registry 自动推导该组包含的所有模块的缓存前缀和精确键名，
    逐一调用 clear_by_prefix / clear。

    Args:
        group_name: 缓存组名，对应 DataModuleDef.cache_groups 中的值

    Returns:
        {模块名: 清除的文件数} 字典，方便日志/UI 展示
    """
    result: dict[str, int] = {}
    for m in get_registry():
        if group_name not in m.cache_groups:
            continue
        total = 0
        for prefix in m.cache_prefixes:
            total += clear_by_prefix(prefix)
        for exact_key in m.exact_cache_keys:
            path = _cache_path(exact_key)
            gz_path = path + _GZIP_SUFFIX
            file_exists = os.path.exists(path) or os.path.exists(gz_path)
            clear(exact_key)
            if file_exists:
                total += 1
        if total > 0:
            result[m.name] = total
    return result


def get_cache_dir() -> str:
    """返回缓存目录绝对路径。"""
    return os.path.abspath(_CACHE_DIR)


def get_cache_stats() -> dict:
    """统计缓存目录：文件总数、总大小、按前缀分组数量、最大文件 TOP 10。

    同时统计 .json 和 .json.gz 文件。

    Returns:
        {total_files, total_size_bytes, by_prefix: {prefix: count},
         top_by_size: [(key, size_bytes), ...]}
    """
    stats: dict = {"total_files": 0, "total_size_bytes": 0, "by_prefix": {}, "top_by_size": []}
    if not os.path.isdir(_CACHE_DIR):
        return stats
    _sized_items: list[tuple[str, int]] = []
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith(".json.gz"):
            stem = fname[:-8]  # 去掉 .json.gz
        elif fname.endswith(".json"):
            stem = fname[:-5]  # 去掉 .json
        else:
            continue
        fpath = os.path.join(_CACHE_DIR, fname)
        try:
            size = os.path.getsize(fpath)
            stats["total_files"] += 1
            stats["total_size_bytes"] += size
            prefix = stem.split("_", 1)[0] if "_" in stem else "other"
            stats["by_prefix"][prefix] = stats["by_prefix"].get(prefix, 0) + 1
            _sized_items.append((stem, size))
        except OSError:
            pass
    _sized_items.sort(key=lambda x: -x[1])
    stats["top_by_size"] = _sized_items[:10]
    return stats


def _process_cache_file(
    fname: str,
    dry_run: bool,
    prefix_type_map: dict[str, str],
    exact_map: dict[str, str],
) -> int:
    """处理单个缓存文件：判断类型、检查过期、删除。returns 是否删除（0/1）。"""
    if fname.endswith(".json.gz"):
        fkey = fname[:-8]
    elif fname.endswith(".json"):
        fkey = fname[:-5]
    else:
        return 0
    fpath = os.path.join(_CACHE_DIR, fname)

    data_type = "default"
    if fkey in exact_map:
        data_type = exact_map[fkey]
    else:
        for pfx, dtype in prefix_type_map.items():
            if fkey.startswith(pfx):
                data_type = dtype
                break

    ttl = get_ttl(data_type)
    payload = _read_cache_data(fpath, fkey, dry_run=dry_run)
    if payload is None:
        return 1  # 损坏也算清理

    now = time.time()
    age = now - payload.get("_ts", 0)
    if age <= ttl:
        return 0

    if not dry_run:
        try:
            os.remove(fpath)
        except OSError:
            return 0
    logger.info("缓存清理: %s %s (age=%.1fh > ttl=%.1fh)",
                "预览" if dry_run else "删除", fname, age / 3600, ttl / 3600)
    return 1


def cleanup_expired(dry_run: bool = False) -> int:
    """扫描缓存目录，删除已过期的缓存文件。

    每个缓存文件内含 _ts 时间戳，读取后与当前时间比对，
    根据文件名的类型前缀查表确定 TTL，过期则删除。
    同时处理 .json 和 .json.gz 文件。

    Args:
        dry_run: True 时仅打印不删除；False 时实际删除

    Returns:
        已删除（或待删除）的文件数
    """
    with _cache_lock:
        prefix_type_map: dict[str, str] = get_prefix_type_map()
        exact_map: dict[str, str] = get_exact_type_map()

        if not os.path.isdir(_CACHE_DIR):
            logger.info("缓存目录不存在，跳过清理")
            return 0

        removed = 0
        for fname in sorted(os.listdir(_CACHE_DIR)):
            removed += _process_cache_file(fname, dry_run, prefix_type_map, exact_map)

        logger.info("缓存清理%s: 共 %d 个文件",
                    "预览" if dry_run else "完成", removed)
        return removed


# ── 持仓指纹检测（用于持仓变更时自动刷新关联缓存） ─────────


def compute_holdings_fingerprint(holdings: list) -> str:
    """计算持仓指纹，用于检测持仓是否发生变更。

    基于 (代码, 账户, 份额, 每份成本) 的四元组生成 MD5 指纹。
    持仓变更（新增/清仓/改仓位）会改变指纹，触发关联缓存刷新。

    Args:
        holdings: 持仓记录列表，每项需有 code/account/shares/cost_price 属性

    Returns:
        MD5 十六进制字符串
    """
    items = sorted(
        (h.code, h.account, h.shares, h.cost_price) for h in holdings
    )
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def compute_holdings_codes(holdings: list) -> set[str]:
    """提取持仓中的证券代码集合。

    Args:
        holdings: 持仓记录列表，每项需有 code 属性

    Returns:
        全部代码的集合
    """
    return {h.code for h in holdings}


def _read_holdings_tracking(tracking_key: str) -> dict | None:
    """读取上次存储的持仓跟踪数据。

    Returns:
        跟踪数据字典（含 fingerprint / codes），文件不存在或损坏时返回 None
    """
    track_path = _cache_path(tracking_key)
    if not os.path.exists(track_path):
        return None
    try:
        with open(track_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("_data")
    except (json.JSONDecodeError, OSError, KeyError):
        logger.warning("读取持仓跟踪缓存数据失败，将重新生成")
        return None


def _clear_holdings_related_caches() -> list[str]:
    """清除与持仓关联的缓存（fund_benchmarks + industry_*）。

    Returns:
        已清除的缓存项描述列表
    """
    cleared: list[str] = []
    bm_path = _cache_path("fund_benchmarks")
    if os.path.exists(bm_path):
        clear("fund_benchmarks")
        cleared.append("fund_benchmarks")
    ind_count = clear_by_prefix("industry_")
    if ind_count > 0:
        cleared.append(f"industry_({ind_count}条)")
    if cleared:
        logger.info("已清除过期缓存: %s", ", ".join(cleared))
    else:
        logger.info("关联缓存尚未生成，无需清除")
    return cleared


def check_and_refresh_caches(holdings: list) -> list[str]:
    """检查持仓是否发生变化，若有变更则自动刷新关联缓存并返回新增资产代码。

    比较当前持仓指纹与上次存储的指纹。若不同：
      - 清除 fund_benchmarks.json（触发重新获取业绩基准）
      - 更新存储的指纹和代码集合
      - 返回新增的资产代码列表（用于主流程主动取数填充单条缓存）

    Args:
        holdings: 当前持仓列表（每项需有 code/account/shares/cost_price）

    Returns:
        新持仓相比上次新增的资产代码列表；无变化时返回空列表。
    """
    tracking_key = "holdings_tracking"

    current_fp = compute_holdings_fingerprint(holdings)
    current_codes = compute_holdings_codes(holdings)

    prev_data = _read_holdings_tracking(tracking_key)

    if prev_data is not None:
        prev_fp = prev_data.get("fingerprint")
        if prev_fp == current_fp:
            return []  # 持仓未变，无需刷新

    # 指纹不同 → 清除关联缓存
    prev_codes = builtins.set(prev_data.get("codes", [])) if prev_data else builtins.set()
    new_codes = current_codes - prev_codes

    logger.info("持仓已变更，自动刷新关联缓存...")
    _clear_holdings_related_caches()

    # 存储新跟踪数据（指纹 + 代码集合）
    set(tracking_key, {
        "fingerprint": current_fp,
        "codes": sorted(current_codes),
    })

    if new_codes:
        logger.info("检测到新增资产代码: %s", ", ".join(sorted(new_codes)))
        return sorted(new_codes)
    return []


# ── 从 config.json 读取缓存 TTL ──────────────────────────
# （A 股交易时段判断已提取至 market_hours.py）


def get_ttl(data_type: str) -> float:
    """获取指定数据类型的缓存过期时间（秒）。

    交易时段内，对 market_hour_aware 声明过的数据类型使用短 TTL（默认 30s）
    确保实时性，优先于静态 cache_ttl 配置。

    Args:
        data_type: 数据类型键名，如 "price"、"rank"、"hold"

    Returns:
        过期时间（秒）
    """
    try:
        from src.python.config import get_config
        config = get_config()
        # ── 交易时段内：配置声明的数据类型用短 TTL 确保实时性 ──
        market_hour_aware: list = config.get("market_hour_aware") or []
        if _is_market_open() and data_type in market_hour_aware:
            market_ttl = config.get("market_hour_ttl", 30)
            try:
                market_ttl_val = float(market_ttl)
                return max(30, min(86400, market_ttl_val))
            except (ValueError, TypeError):
                return 30
        # ── 非交易时段或非感知类型：用静态配置或默认值 ──
        ttl_config = config.get("cache_ttl") or {}
        if data_type in ttl_config:
            val = float(ttl_config[data_type])
            if val > 0:
                return val
    except (ImportError, TypeError, ValueError, KeyError, AttributeError, RuntimeError):
        logger.debug("get_ttl: 配置读取失败，使用默认值")
    return get_cache_ttl_defaults().get(data_type, CACHE_DAILY)