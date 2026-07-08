"""数据源注册中心 — 集中管理熔断状态、会话缓存、获取策略。

取代：
  - chain.py 的 4 个全局变量（_PROVIDER_SKIP / _SKIP_TIME / _CONSECUTIVE_FAILURES / _LOCK）
  - fund_style_analysis._ext_memo / eastmoney_industry._ext_memo / eastmoney_industry_rest._ext_memo
  - fund_style_analysis._tencent_failures

与 data_status.py DegradationTracker 边界：
  DataSourceRegistry（熔断层）:
    管"这个 Provider 能不能调用"（HTTP 层面的快速跳过）
    per-provider 粒度，3 次/300s 固定阈值，自动冷却恢复

  DegradationTracker（降级决策层）:
    管"这批数据能不能信任"（数据质量层面的占位/降级）
    per-data_source 粒度，双信号（失败计数+缓存陈旧），配置可调阈值
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("invest")

# ── 常量 ────────────────────────────────────────────────

_PROVIDER_SKIP_THRESHOLD = 3
"""单个 Provider 连续失败多少次后熔断。"""

_PROVIDER_COOLDOWN_SECS = 300
"""熔断后多少秒自动放行一次试探。"""

_SESSION_CACHE_MAX_ENTRIES = 2000
"""每 domain 最多缓存条目数，超限时淘汰最旧条目。"""

# ── Sentinel ─────────────────────────────────────────────

_TRANSPORT_FAILURE: object = object()
"""传输级异常 sentinel：超时/断连/DNS/SSL/5xx。
   _fetch_with_fallback 通过此 sentinel 区分『网络挂了』和『代码级空结果』。"""

_NOT_FOUND: object = object()
"""会话缓存未命中的返回值 sentinel，区分『缓存存了 None』和『没查过』。"""


# ── 策略枚举 ────────────────────────────────────────────


class FetchStrategy(Enum):
    """数据获取策略。

    LIVE_FETCH:
        盘中实时获取（走 Provider Chain + HTTP）。
        适用于交易时段或 QDII/港股等不受 A 股交易时段限制的数据。

    CACHE_ONLY:
        盘后只读缓存（不发起 HTTP）。
        非交易时段 A 股数据从此策略受益。

    PLACEHOLDER:
        所有路径都不可用 → 使用占位（暂无行情等）。
        当前未在 get_effective_strategy 中主动返回，预留。
    """
    LIVE_FETCH = "live"
    CACHE_ONLY = "cache"
    PLACEHOLDER = "placeholder"


# ── 数据类型 ────────────────────────────────────────────


@dataclass
class ProviderState:
    """Provider 运行时状态（熔断器数据）。"""
    name: str
    tier: int
    fallback: str | None
    timeout: float
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_failure_context: str = ""
    is_skipped: bool = False
    total_failures: int = 0
    total_successes: int = 0


@dataclass
class SessionCacheEntry:
    """会话缓存条目。"""
    value: Any
    fetched_at: float
    source: str


# ── 单例类 ──────────────────────────────────────────────


class DataSourceRegistry:
    """数据源注册中心（单例，线程安全）。

    职责：
      1. Provider 熔断器（注册/记成功/记失败/查熔断）
      2. 会话级内存缓存（同一股票跨模块复用）
      3. 获取策略选择（交易时段/熔断状态/代码类型感知）
      4. 审计报告（generate_status_report）
    """

    _instance: DataSourceRegistry | None = None
    _singleton_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> DataSourceRegistry:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        # 双锁：熔断操作和缓存操作不互相阻塞
        self._provider_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._providers: dict[str, ProviderState] = {}
        self._session_cache: dict[str, dict[str, SessionCacheEntry]] = {}
        self._chains: dict[str, list[str]] = {}
        self._initialized = True

    # ── Provider 注册 ─────────────────────────────────

    def register_provider(
        self,
        name: str,
        tier: int = 4,
        fallback: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """注册一个 Provider（幂等）。

        首次注册创建 ProviderState，重复注册只更新 tier/fallback/timeout，
        不影响熔断计数器。
        """
        with self._provider_lock:
            if name in self._providers:
                old = self._providers[name]
                old.tier = tier
                old.fallback = fallback
                old.timeout = timeout
            else:
                self._providers[name] = ProviderState(
                    name=name, tier=tier, fallback=fallback, timeout=timeout,
                )

    def register_default_chains(self) -> None:
        """注册默认 Provider Chain（从 _DEFAULT_CHAINS 派生）。

        可在模块导入时调用一次，消除分散在各文件中的 register_provider 调用。
        """
        from src.python.fetcher.chain import _DEFAULT_CHAINS

        for _data_type, provider_list in _DEFAULT_CHAINS.items():
            for name in provider_list:
                tier = 2 if name in ("tencent", "eastmoney") else 3
                timeout = 10.0 if name in ("tencent", "eastmoney_industry") else 20.0
                self.register_provider(name, tier, None, timeout)
            self._chains[_data_type] = list(provider_list)

    # ── 熔断器（Provider 级） ───────────────────────────

    def record_success(self, provider: str) -> None:
        """记录一次 Provider 调用成功，重置熔断计数。"""
        with self._provider_lock:
            state = self._providers.get(provider)
            if state is None:
                return
            state.consecutive_failures = 0
            state.is_skipped = False
            state.total_successes += 1

    def record_failure(self, provider: str, context: str = "") -> None:
        """记录一次 Provider 传输级失败，达到阈值时触发熔断。

        调用方应仅在『传输级异常』（超时/断连/DNS/SSL/5xx）时调用此方法。
        代码级空结果（API 正常响应但无匹配数据）不计入熔断。
        """
        with self._provider_lock:
            state = self._providers.get(provider)
            if state is None:
                return
            now = time.time()
            state.consecutive_failures += 1
            state.last_failure_time = now
            state.last_failure_context = context
            state.total_failures += 1
            if state.consecutive_failures >= _PROVIDER_SKIP_THRESHOLD:
                state.is_skipped = True
                logger.warning(
                    "[registry] %s 连续 %d 次失败（最新: %s），熔断 %ds",
                    provider, state.consecutive_failures, context,
                    _PROVIDER_COOLDOWN_SECS,
                )

    def is_circuit_broken(self, provider: str) -> bool:
        """检查 Provider 是否在熔断中。

        冷却期满时自动移除熔断标记并放行一次试探。
        """
        with self._provider_lock:
            state = self._providers.get(provider)
            if state is None or not state.is_skipped:
                return False
            elapsed = time.time() - state.last_failure_time
            if elapsed >= _PROVIDER_COOLDOWN_SECS:
                state.is_skipped = False
                logger.info(
                    "[registry] %s 冷却期满（%.0fs），解除熔断",
                    provider, elapsed,
                )
                return False
            return True

    def is_chain_broken(self, chain: list[str]) -> bool:
        """检查 Chain 中所有 Provider 是否都在熔断中。

        只要有一个可用就返回 False。全链熔断时调用方可跳过批量请求。
        """
        with self._provider_lock:
            now = time.time()
            # 检查全链熔断
            for p in chain:
                state = self._providers.get(p)
                if state is None or not state.is_skipped:
                    return False
            # 全链熔断 → 检查是否有冷却期满的（解除所有冷却期满的 provider）
            any_recovered = False
            for p in chain:
                state = self._providers[p]
                if now - state.last_failure_time >= _PROVIDER_COOLDOWN_SECS:
                    state.is_skipped = False
                    any_recovered = True
                    logger.info(
                        "[registry] %s 冷却期满（链式检查，%.0fs），解除熔断",
                        p, now - state.last_failure_time,
                    )
            if any_recovered:
                return False
            return True

    def get_available_providers(self, chain: list[str]) -> list[str]:
        """返回 Chain 中当前未熔断的 Provider 列表。"""
        return [p for p in chain if not self.is_circuit_broken(p)]

    @staticmethod
    def is_transport_failure(result: Any) -> bool:
        """判断结果是否为传输级失败的 sentinel。"""
        return result is _TRANSPORT_FAILURE

    # ── 会话级缓存 ─────────────────────────────────────

    def session_cache_get(self, domain: str, code: str) -> Any:
        """从会话缓存读取，未命中时返回 _NOT_FOUND sentinel。

        NOTE: 调用方应通过 `is session_cache_get(...) is _NOT_FOUND` 区分
        『未缓存』和『缓存值为 None』。
        """
        with self._cache_lock:
            entry = self._session_cache.get(domain, {}).get(code)
            if entry is None:
                return _NOT_FOUND
            return entry.value

    def session_cache_set(
        self,
        domain: str,
        code: str,
        value: Any,
        source: str = "api",
    ) -> None:
        """写入会话缓存（支持 value=None）。"""
        with self._cache_lock:
            if domain not in self._session_cache:
                self._session_cache[domain] = {}
            dc = self._session_cache[domain]
            if len(dc) >= _SESSION_CACHE_MAX_ENTRIES:
                self._evict_one(dc)
            dc[code] = SessionCacheEntry(
                value=value, fetched_at=time.time(), source=source,
            )

    def session_cache_contains(self, domain: str, code: str) -> bool:
        """检查某 key 是否在会话缓存中（无视值是否为 None）。"""
        with self._cache_lock:
            return code in self._session_cache.get(domain, {})

    def session_cache_clear(self, domain: str | None = None) -> None:
        """清空会话缓存。domain=None 时清空全部。"""
        with self._cache_lock:
            if domain is not None:
                self._session_cache.pop(domain, None)
            else:
                self._session_cache.clear()

    @staticmethod
    def _evict_one(dc: dict[str, SessionCacheEntry]) -> None:
        """O(1) 淘汰最旧条目（不排序，直接弹出第一个）。"""
        try:
            dc.pop(next(iter(dc)))
        except (StopIteration, KeyError):
            pass

    # ── 策略选择 ───────────────────────────────────────

    def get_effective_strategy(
        self,
        code_type: str,
        chain: list[str] | None = None,
        market_open: bool | None = None,
    ) -> FetchStrategy:
        """根据代码类型、熔断状态、市场时段选择获取策略。

        Args:
            code_type: "a_share" / "hk_stock" / "qdii"
            chain: 可选的 provider chain 列表，用于熔断感知降级
            market_open: 强制指定市场是否开放，不指定时自动检测

        Returns:
            LIVE_FETCH / CACHE_ONLY / PLACEHOLDER
        """
        # QDII/港股不受 A 股交易时段限制
        if code_type in ("qdii", "hk_stock"):
            return FetchStrategy.LIVE_FETCH

        # 检测交易时段
        if market_open is None:
            from src.python.market_hours import is_market_open
            try:
                market_open = is_market_open()
            except Exception:
                market_open = False

        if not market_open:
            return FetchStrategy.CACHE_ONLY

        # 熔断状态感知：全链熔断 → 降级 CACHE_ONLY
        if chain and self.is_chain_broken(chain):
            logger.info(
                "[registry] 策略降级: %s 链已熔断，LIVE_FETCH → CACHE_ONLY",
                chain,
            )
            return FetchStrategy.CACHE_ONLY

        return FetchStrategy.LIVE_FETCH

    # ── 统一获取入口 ───────────────────────────────────

    def fetch_or_cached(
        self,
        code: str,
        code_type: str,
        fetch_fn: Callable[[str], Any],
        chain: list[str] | None = None,
        cache_domain: str = "price",
        cache_key_fn: Callable[[str], str] | None = None,
    ) -> Any:
        """策略感知的数据获取：根据策略决定走 HTTP 还是缓存。

        Args:
            code: 证券代码
            code_type: "a_share" / "hk_stock" / "qdii"
            fetch_fn: 实际 HTTP 获取函数，签名 (code) → result
            chain: provider chain 列表（用于熔断感知）
            cache_domain: 会话缓存域
            cache_key_fn: 文件缓存 key 生成函数（为 CACHE_ONLY 提供文件缓存 fallback）

        Returns:
            获取到的数据，或 None（所有路径不可用）
        """
        strategy = self.get_effective_strategy(code_type, chain)

        if strategy == FetchStrategy.CACHE_ONLY:
            return self._fetch_cached_only(code, cache_domain, cache_key_fn)

        # LIVE_FETCH：执行实际获取
        result = fetch_fn(code)
        if result is not None:
            self.session_cache_set(cache_domain, code, result, source="api")
        return result

    def _fetch_cached_only(
        self,
        code: str,
        cache_domain: str = "price",
        cache_key_fn: Callable[[str], str] | None = None,
    ) -> Any | None:
        """仅从缓存读取，不发起 HTTP。session_cache → file_cache 两级 fallback。

        文件缓存中的 price_date 若非当天数据，在返回数据中设置
        _cache_date_mismatch=True 标记，供详情行显示处理。
        """
        # 1) session cache
        cached = self.session_cache_get(cache_domain, code)
        if cached is not _NOT_FOUND:
            return cached

        # 2) file cache
        if cache_key_fn is not None:
            from src.python import cache as _cache

            key = cache_key_fn(code)
            data = _cache.get(key, 86400 * 7)
            if data is not None:
                # 检查 price_date 是否匹配今天
                data["_cache_date_mismatch"] = True  # 默认标记（文件缓存总是旧数据）
                price_date = data.get("price_date", "")
                today = time.strftime("%Y-%m-%d")
                if price_date == today:
                    data["_cache_date_mismatch"] = False
                # 写入 session cache 加速后续读取
                self.session_cache_set(cache_domain, code, data, source="file")
                return data

        return None

    # ── 审计报告 ───────────────────────────────────────

    def generate_status_report(self) -> dict[str, dict[str, Any]]:
        """生成所有 Provider 的可用状态报告。"""
        with self._provider_lock:
            now = time.time()
            report: dict[str, dict[str, Any]] = {}
            for name, state in self._providers.items():
                cooldown_remaining = 0.0
                if state.is_skipped:
                    cooldown_remaining = max(
                        0.0,
                        _PROVIDER_COOLDOWN_SECS - (now - state.last_failure_time),
                    )
                report[name] = {
                    "available": not state.is_skipped,
                    "tier": state.tier,
                    "consecutive_failures": state.consecutive_failures,
                    "circuit_broken": state.is_skipped,
                    "cooldown_remaining": round(cooldown_remaining, 1),
                    "total_failures": state.total_failures,
                    "total_successes": state.total_successes,
                    "last_failure_context": state.last_failure_context,
                }
            return report

    def get_chain(self, data_type: str) -> list[str]:
        """获取指定数据类型的 provider chain 列表。"""
        return list(self._chains.get(data_type, []))

    # ── 测试辅助 ───────────────────────────────────────

    def reset(self) -> None:
        """清空全部状态（测试用）。"""
        with self._provider_lock:
            self._providers.clear()
            self._chains.clear()
        with self._cache_lock:
            self._session_cache.clear()

    def get_skip_set_copy(self) -> set[str]:
        """兼容旧测试接口：返回熔断中 provider 的集合。"""
        with self._provider_lock:
            return {n for n, s in self._providers.items() if s.is_skipped}

    def get_skip_time_copy(self) -> dict[str, float]:
        """兼容旧测试接口：返回熔断时间戳字典。"""
        with self._provider_lock:
            return {
                n: s.last_failure_time
                for n, s in self._providers.items()
                if s.is_skipped
            }


# ── 工厂函数 ────────────────────────────────────────────


def get_registry() -> DataSourceRegistry:
    """获取 DataSourceRegistry 单例。"""
    return DataSourceRegistry()


# ── PhaseTimeout（全局超时上下文管理器） ─────────────────


_phase_timer: threading.Timer | None = None
_phase_expired = False
_phase_timeout_lock = threading.Lock()
_phase_timer_name: str = ""


@contextmanager
def phase_timeout(seconds: float, phase_name: str = "data_fetch"):
    """数据获取阶段全局超时上下文管理器。

    超时后已获取的数据保留，未完成的以占位处理。
    超时不影响正在运行的 HTTP 线程（Python 无法 kill 线程），但结果被丢弃。

    不支持嵌套——检测到嵌套时抛出 RuntimeError。

    Args:
        seconds: 超时秒数
        phase_name: 阶段名称（日志用）

    Yields:
        _PhaseTimeoutContext 实例，供调用方检查过期/剩余时间
    """
    global _phase_timer, _phase_expired, _phase_timer_name

    if _phase_timer is not None:
        raise RuntimeError(
            f"phase_timeout 不支持嵌套：已有 '{_phase_timer_name}' 在运行，"
            f"不能开启 '{phase_name}'"
        )

    start = time.time()
    _phase_expired = False
    _phase_timer_name = phase_name

    def _expire():
        global _phase_expired
        with _phase_timeout_lock:
            _phase_expired = True
        logger.warning(
            "[phase_timeout] %s 超时（%.0fs），继续使用已获取数据",
            phase_name, seconds,
        )

    timer = threading.Timer(seconds, _expire)
    timer.daemon = True
    timer.start()
    _phase_timer = timer

    try:
        yield _PhaseTimeoutContext(start, seconds)
    finally:
        timer.cancel()
        with _phase_timeout_lock:
            _phase_expired = False
        _phase_timer = None
        _phase_timer_name = ""


class _PhaseTimeoutContext:
    """超时上下文，供调用方检查超时状态。"""

    def __init__(self, start: float, total: float):
        self._start = start
        self._total = total

    @property
    def expired(self) -> bool:
        with _phase_timeout_lock:
            return _phase_expired

    @property
    def elapsed(self) -> float:
        return time.time() - self._start

    @property
    def remaining(self) -> float:
        return max(0.0, self._total - self.elapsed)

    def check(self) -> None:
        """检查超时，超时时抛出 TimeoutError。"""
        if self.expired:
            raise TimeoutError(f"数据获取阶段超时（{self._total:.0f}s）")
