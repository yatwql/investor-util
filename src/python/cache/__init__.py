"""缓存引擎子包。

I-07 最终形态：从各子模块直连导入，精简 __all__ 移除文件系统级内部接口（对齐 C2 约束）。
"""

from src.python.constants import CACHE_DAILY

from ._cleanup import _process_cache_file, cleanup_expired
from ._groups import clear_by_group, clear_by_prefix
from ._io import _read_cache_data, _write_atomic
from ._paths import _CACHE_DIR, _GZIP_SUFFIX, _GZIP_THRESHOLD, _cache_path, get_cache_dir
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
    "clear_by_prefix",
    "clear_by_group",
    "check_and_refresh_caches",
    "compute_holdings_fingerprint",
    "compute_holdings_codes",
    "get_cache_dir",
    # ── 公共常量（test_cache.py 有 3 处 from cache import CACHE_DAILY）──
    "CACHE_DAILY",
    # ── 内部接口（_cache_lock 被市场时段等模块使用）──
    "_cache_lock",
]
