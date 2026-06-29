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

from src.python.constants import CACHE_DAILY, CACHE_WEEKLY, CACHE_MONTHLY, CACHE_TTL_DEFAULTS

_CACHE_DIR = "data/cache"
_GZIP_THRESHOLD = 100 * 1024  # 100KB 以上的缓存自动 gzip
_GZIP_SUFFIX = ".gz"

logger = logging.getLogger("invest")

_cache_lock = threading.Lock()


def _cache_path(key: str) -> str:
    """返回缓存文件完整路径（始终带 .json 后缀，由 get/set 决定是否追加 .gz）。"""
    # 防止目录穿越
    safe_name = key.replace("/", "_").replace("\\", "_").replace("..", "_")
    return os.path.join(_CACHE_DIR, f"{safe_name}.json")


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
    if os.path.exists(gz_path):
        try:
            with open(gz_path, "rb") as f:
                compressed = f.read()
            data = json.loads(gzip.decompress(compressed).decode("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("缓存文件 %s 损坏，自动删除: %s", key, e)
            try:
                os.remove(gz_path)
                logger.info("已删除损坏的缓存文件: %s", key)
            except OSError:
                pass
            return None

        timestamp = data.get("_ts", 0)
        age = time.time() - timestamp
        if age > max_age_seconds:
            logger.debug("缓存 %s 已过期 (%.1fs > %.1fs)", key, age, max_age_seconds)
            return None

        logger.debug("缓存命中: %s (age=%.1fs, max=%.1fs)", key, age, max_age_seconds)
        return data.get("_data")

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("缓存文件 %s 损坏，自动删除: %s", key, e)
        try:
            os.remove(path)
            logger.info("已删除损坏的缓存文件: %s", key)
        except OSError:
            pass
        return None

    timestamp = data.get("_ts", 0)
    age = time.time() - timestamp
    if age > max_age_seconds:
        logger.debug("缓存 %s 已过期 (%.1fs > %.1fs)", key, age, max_age_seconds)
        return None

    logger.debug("缓存命中: %s (age=%.1fs, max=%.1fs)", key, age, max_age_seconds)
    return data.get("_data")


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
                if use_gzip:
                    compressed = gzip.compress(raw_bytes)
                    with os.fdopen(fd2, "wb") as f:
                        f.write(compressed)
                else:
                    with os.fdopen(fd2, "w", encoding="utf-8") as f:
                        f.write(json_str)
                try:
                    os.replace(tmp_path2, final_path)
                except PermissionError:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.rename(tmp_path2, final_path)

                # 清理旧格式文件
                other_path = path if use_gzip else (path + _GZIP_SUFFIX)
                if os.path.exists(other_path):
                    try:
                        os.remove(other_path)
                    except OSError:
                        pass

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
        from collections import defaultdict

        # 文件名前缀 → 数据类型键名
        # 注意：具体前缀需在通用前缀之前（如 "llm_global_macro" 在 "llm_" 之前）
        prefix_type_map: dict[str, str] = {
            "price": "price",
            "index": "index",
            "fund_perf": "rank",
            "fund_hold": "hold",
            "industry": "industry",
            "news": "news",
            "llm_global_macro": "llm_global_macro",   # 全球政经局势：24h TTL
            "llm_expert_review": "llm_expert_review", # 智囊团深度复盘：2h TTL
            "llm_news_correlation": "llm_news_correlation",     # LLM 新闻关联分析：1h TTL
            "llm_news_item": "llm_news_correlation",            # LLM 新闻逐条缓存：1h TTL（同 news_correlation）
            "llm_health_check": "llm_health_check",             # 持仓体检报告：2h TTL
            "llm_penetration_deep": "llm_penetration_deep",     # 穿透深度分析：24h TTL
            "profit_forecast": "profit_forecast",
            "sector_flow": "sector_flow",
            "dividend": "dividend",
        }
        exact_map: dict[str, str] = {
            "fund_benchmarks": "benchmark",
            "holdings_tracking": "benchmark",  # 持仓跟踪数据：30天 TTL，防误删导致重复预热
        }

        if not os.path.isdir(_CACHE_DIR):
            logger.info("缓存目录不存在，跳过清理")
            return 0

        now = time.time()
        removed = 0
        ttl_used: dict[str, int] = defaultdict(int)

        for fname in sorted(os.listdir(_CACHE_DIR)):
            if fname.endswith(".json.gz"):
                fkey = fname[:-8]  # 去掉 .json.gz
                is_gz = True
            elif fname.endswith(".json"):
                fkey = fname[:-5]  # 去掉 .json
                is_gz = False
            else:
                continue
            fpath = os.path.join(_CACHE_DIR, fname)

            # 确定数据类型
            data_type = "news"  # 默认给较短的 TTL
            if fkey in exact_map:
                data_type = exact_map[fkey]
            else:
                for pfx, dtype in prefix_type_map.items():
                    if fkey.startswith(pfx):
                        data_type = dtype
                        break

            ttl = get_ttl(data_type)

            try:
                if is_gz:
                    with open(fpath, "rb") as f:
                        payload = json.loads(gzip.decompress(f.read()).decode("utf-8"))
                else:
                    with open(fpath, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                ts = payload.get("_ts", 0)
            except (json.JSONDecodeError, OSError):
                # 文件损坏，直接删除
                if not dry_run:
                    try:
                        os.remove(fpath)
                        removed += 1
                        logger.info("缓存清理: 删除损坏文件 %s", fname)
                    except OSError:
                        pass
                else:
                    logger.info("缓存清理(预览): 损坏文件 %s", fname)
                    removed += 1
                continue

            age = now - ts
            if age > ttl:
                if not dry_run:
                    try:
                        os.remove(fpath)
                        removed += 1
                        logger.info("缓存清理: 删除过期 %s (age=%.1fh > ttl=%.1fh)",
                                    fname, age / 3600, ttl / 3600)
                    except OSError:
                        pass
                else:
                    logger.info("缓存清理(预览): 过期 %s (age=%.1fh > ttl=%.1fh)",
                                fname, age / 3600, ttl / 3600)
                    removed += 1
                ttl_used[data_type] += 1

        if dry_run:
            logger.info("缓存清理预览: 共 %d 个文件待清理", removed)
        else:
            logger.info("缓存清理完成: 共删除 %d 个过期文件", removed)
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

    # 读取上次存储的跟踪数据
    track_path = _cache_path(tracking_key)
    prev_data: dict | None = None
    if os.path.exists(track_path):
        try:
            with open(track_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            prev_data = payload.get("_data")
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    if prev_data is not None:
        prev_fp = prev_data.get("fingerprint")
        if prev_fp == current_fp:
            return []  # 持仓未变，无需刷新

    # 指纹不同 → 清除关联缓存
    prev_codes = builtins.set(prev_data.get("codes", [])) if prev_data else builtins.set()
    new_codes = current_codes - prev_codes

    logger.info("持仓已变更，自动刷新关联缓存...")

    cleared: list[str] = []
    bm_path = _cache_path("fund_benchmarks")
    if os.path.exists(bm_path):
        clear("fund_benchmarks")
        cleared.append("fund_benchmarks")

    # 持仓变更 → 行业分类缓存可能变化（新品种代码不同，行业不同）
    ind_count = clear_by_prefix("industry_")
    if ind_count > 0:
        cleared.append(f"industry_({ind_count}条)")

    if cleared:
        logger.info("已清除过期缓存: %s", ", ".join(cleared))
    else:
        logger.info("关联缓存尚未生成，无需清除")

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


def get_ttl(data_type: str) -> float:
    """获取指定数据类型的缓存过期时间（秒）。

    优先读取 data/config/config.json 中的 cache_ttl.<data_type>，
    未配置时返回预定义默认值。

    Args:
        data_type: 数据类型键名，如 "price"、"rank"、"hold"

    Returns:
        过期时间（秒）
    """
    try:
        from src.python.config import get_config
        config = get_config()
        ttl_config = config.get("cache_ttl") or {}
        if data_type in ttl_config:
            val = float(ttl_config[data_type])
            if val > 0:
                return val
    except (ImportError, TypeError, ValueError, KeyError, AttributeError, RuntimeError):
        logger.debug("get_ttl: 配置读取失败，使用默认值")
    return CACHE_TTL_DEFAULTS.get(data_type, CACHE_DAILY)