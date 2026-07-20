"""缓存引擎 — TTL / 缓存年龄子模块。

职责：TTL 查询（交易时段感知）、缓存年龄查询。
"""

from __future__ import annotations

import hashlib
import logging
import time

from src.python.constants import CACHE_DAILY
from src.python.market_hours import is_market_open as _is_market_open
from src.python.registry import get_cache_ttl_defaults

from ._io import _read_cache_data
from ._paths import _GZIP_SUFFIX, _cache_path

logger = logging.getLogger("invest")

# 缓存雪崩防护：TTL 随机偏移范围 (±15%)
_TTL_JITTER_RANGE = 0.15
_TTL_JITTER_RESOLUTION = 301  # 步数，使偏移值在 [0.85, 1.15] 范围内有 301 个可能值


def _ttl_jitter_factor(key: str) -> float:
    """基于 key 哈希的确定性 TTL 偏移因子 [0.85, 1.15]。

    相同 key 始终返回相同因子（跨进程稳定），确保缓存过期时间分散，
    防止大量同类缓存同时过期导致缓存雪崩。

    Args:
        key: 缓存键名

    Returns:
        [0.85, 1.15] 范围内的偏移因子
    """
    h = int(hashlib.md5(key.encode()).hexdigest()[:4], 16)
    offset = h % _TTL_JITTER_RESOLUTION  # 0 .. 300
    return 1.0 + _TTL_JITTER_RANGE * (offset - _TTL_JITTER_RESOLUTION // 2) / (_TTL_JITTER_RESOLUTION // 2)


def get_cache_age(key: str) -> float | None:
    """返回缓存数据年龄（秒），无缓存或损坏时返回 None。

    同时检查 .json 和 .json.gz 变体，返回最先找到的有效缓存年龄。

    Args:
        key: 缓存键名

    Returns:
        缓存数据距今的秒数，缓存不存在/损坏时返回 None
    """
    path = _cache_path(key)
    gz_path = path + _GZIP_SUFFIX

    for fpath in (gz_path, path):
        data = _read_cache_data(fpath, key)
        if data is not None:
            ts = data.get("_ts", 0)
            if isinstance(ts, (int, float)) and ts > 0:
                return time.time() - ts
    return None


def get_cache_age_by_data_type(
    data_type: str,
    identifier: str | None = None,
) -> float | None:
    """按 registry 数据类型获取缓存年龄，替换硬编码 get_cache_age() 调用。

    从 registry 查找数据类型的缓存前缀，拼接 identifier 组成完整键名。
    适用于前缀+代码/标识符结构的缓存键（如 ``"index_sh000001"``）。

    特殊处理：
      - ``"profit_forecast"``：缓存键含动态指数指纹，无需 identifier，
        内部委托给 :func:`get_profit_forecast_cache_key` 获取键名。

    Args:
        data_type: registry 中注册的数据类型，如 ``"index"``
        identifier: 拼接在缓存前缀后的标识符，
                    如 ``"sh000001"`` → 完整键名 ``"index_sh000001"``

    Returns:
        缓存年龄（秒），无缓存或类型未注册时返回 None
    """
    # 特殊处理：profit_forecast 使用动态指纹，不走 prefix+identifier 模式
    if data_type == "profit_forecast":
        from src.python.fetcher.akshare import get_profit_forecast_cache_key

        return get_cache_age(get_profit_forecast_cache_key())
    # 标准路径：prefix + identifier
    from src.python.registry import get_registry  # 延迟导入避免循环依赖

    for module in get_registry():
        if module.data_type == data_type and identifier is not None and module.cache_prefixes:
            key = f"{module.cache_prefixes[0]}{identifier}"
            return get_cache_age(key)
    return None


def get_ttl(data_type: str, key: str | None = None) -> float:
    """获取指定数据类型的缓存过期时间（秒）。

    交易时段内，对 market_hour_aware 声明过的数据类型使用短 TTL（默认 30s）
    确保实时性，优先于静态 cache_ttl 配置。

    当传入 key 参数时，对 TTL 增加 ±15% 的确定性随机偏移（基于 key 哈希），
    用于防止大量同类缓存同时过期导致的缓存雪崩。

    Args:
        data_type: 数据类型键名，如 "price"、"rank"、"hold"
        key: 缓存键名，传入时启用 TTL 随机偏移（缓存雪崩防护）

    Returns:
        过期时间（秒）
    """
    try:
        from src.python.config import get_config  # lazy import

        config = get_config()
        # ── 交易时段内：配置声明的数据类型用短 TTL 确保实时性 ──
        market_hour_aware: list = config.get("market_hour_aware") or []
        if _is_market_open() and data_type in market_hour_aware:
            market_ttl = config.get("market_hour_ttl", 30)
            try:
                market_ttl_val = float(market_ttl)
                ttl = max(30, min(86400, market_ttl_val))
            except (ValueError, TypeError):
                ttl = 30
        else:
            # ── 非交易时段或非感知类型：用静态配置或默认值 ──
            ttl_config = config.get("cache_ttl") or {}
            if data_type in ttl_config:
                val = float(ttl_config[data_type])
                if val > 0:
                    ttl = val
                else:
                    ttl = get_cache_ttl_defaults().get(data_type, CACHE_DAILY)
            else:
                ttl = get_cache_ttl_defaults().get(data_type, CACHE_DAILY)
    except (ImportError, TypeError, ValueError, KeyError, AttributeError, RuntimeError):
        logger.debug("get_ttl: 配置读取失败，使用默认值")
        ttl = get_cache_ttl_defaults().get(data_type, CACHE_DAILY)

    # 缓存雪崩防护：基于 key 哈希的确定性 TTL 偏移
    if key is not None:
        ttl *= _ttl_jitter_factor(key)
    return ttl
