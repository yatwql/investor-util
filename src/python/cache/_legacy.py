"""通用 JSON 文件缓存 — 过渡聚合模块。

I-01~I-06 过渡期：从各子模块 re-export 所有 name，维持向后兼容。
I-07 将删除本文件，改为 __init__.py 直连导入。
"""

from __future__ import annotations

from src.python.constants import CACHE_DAILY

from ._cleanup import _process_cache_file, cleanup_expired
from ._groups import clear_by_group, clear_by_prefix
from ._io import _read_cache_data, _write_atomic
from ._paths import _CACHE_DIR, _GZIP_THRESHOLD, _GZIP_SUFFIX, _cache_path, get_cache_dir
from ._stats import (
    _record_cache_hit, _record_cache_miss,
    get_cache_hit_rate, get_cache_stats, reset_cache_stats,
)
from ._store import _cache_lock, clear, get, set
from ._ttl import get_cache_age, get_cache_age_by_data_type, get_ttl
from .services.holdings_tracker import (
    _clear_holdings_related_caches, _read_holdings_tracking,
    check_and_refresh_caches, compute_holdings_codes, compute_holdings_fingerprint,
)
