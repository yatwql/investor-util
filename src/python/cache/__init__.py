"""缓存引擎子包。

I-01~I-06 过渡期：从 _legacy.py 统一 re-export 所有需保持兼容的 name。
I-07 切换为从各子模块直连导入，并精简 __all__（移除文件系统级内部接口对齐 C2 约束）。
"""

from ._legacy import (
    # ── 公共 API ──
    get, set, clear,
    get_cache_hit_rate, reset_cache_stats, get_cache_stats,
    get_ttl, get_cache_age, get_cache_age_by_data_type,
    cleanup_expired,
    clear_by_prefix, clear_by_group,
    check_and_refresh_caches, compute_holdings_fingerprint, compute_holdings_codes,
    get_cache_dir,
    # ── 公共常量（保持 from cache import CACHE_DAILY 兼容）──
    CACHE_DAILY,
    # ── 内部接口（被子模块或外部引用）──
    _cache_lock, _cache_path, _CACHE_DIR, _GZIP_THRESHOLD, _GZIP_SUFFIX,
    _read_cache_data, _write_atomic,
    _record_cache_hit, _record_cache_miss,
)

__all__ = [
    "get", "set", "clear",
    "get_cache_hit_rate", "reset_cache_stats", "get_cache_stats",
    "get_ttl", "get_cache_age", "get_cache_age_by_data_type",
    "cleanup_expired",
    "clear_by_prefix", "clear_by_group",
    "check_and_refresh_caches", "compute_holdings_fingerprint", "compute_holdings_codes",
    "get_cache_dir",
    # ── 公共常量（test_cache.py 有 3 处 from cache import CACHE_DAILY）──
    "CACHE_DAILY",
    # ── 内部接口（外部消费者不应依赖，但已有测试使用）──
    "_cache_lock", "_cache_path",
]
