"""缓存引擎子包 — 提供 get/set/clear 及 TTL 管理等统一接口。"""

import logging

from src.python.core.constants import CACHE_DAILY

from ._cleanup import _process_cache_file, cleanup_expired, clean_sensitive
from ._groups import clear_by_group, clear_by_prefix
from ._io import _read_cache_data, _write_atomic
from ._paths import _CACHE_DIR, _GZIP_SUFFIX, _GZIP_THRESHOLD, _cache_path, check_cache_dir_permissions, get_cache_dir
from ._stats import (
    _record_cache_hit,
    _record_cache_miss,
    get_cache_hit_rate,
    get_cache_stats,
    reset_cache_stats,
)
from ._store import _cache_lock, clear, get, set
from ._ttl import get_cache_age, get_cache_age_by_data_type, get_ttl
from .services.holdings_tracker import (
    _clear_holdings_related_caches,
    _read_holdings_tracking,
    check_and_refresh_caches,
    compute_holdings_codes,
    compute_holdings_fingerprint,
)

__all__ = [
    "get",
    "set",
    "clear",
    "get_cache_hit_rate",
    "reset_cache_stats",
    "get_cache_stats",
    "get_ttl",
    "get_cache_age",
    "get_cache_age_by_data_type",
    "cleanup_expired",
    "clean_sensitive",
    "clear_by_prefix",
    "clear_by_group",
    "check_and_refresh_caches",
    "compute_holdings_fingerprint",
    "compute_holdings_codes",
    "get_cache_dir",
    "check_cache_dir_permissions",
    # ── 公共常量（test_cache.py 有 3 处 from cache import CACHE_DAILY）──
    "CACHE_DAILY",
    # ── 内部接口（_cache_lock 被市场时段等模块使用）──
    "_cache_lock",
    # ── 内部接口（re-export，供缓存子模块 / 外部直接引用）──
    "_read_cache_data",
    "_write_atomic",
    "_CACHE_DIR",
    "_GZIP_SUFFIX",
    "_GZIP_THRESHOLD",
    "_cache_path",
    "_process_cache_file",
    "_record_cache_hit",
    "_record_cache_miss",
    "_clear_holdings_related_caches",
    "_read_holdings_tracking",
]


# ── 启动时自动清理过期敏感缓存（静默执行，仅日志记录）──
_logger = logging.getLogger("invest")
try:
    _cleaned = clean_sensitive(older_than_days=90, dry_run=False)
    if _cleaned > 0:
        _logger.info("[cache] 启动清理: 移除 %d 个过期敏感缓存文件", _cleaned)
except Exception:
    _logger.debug("[cache] 启动敏感缓存清理失败（非关键）", exc_info=True)
del _logger, _cleaned
