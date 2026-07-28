"""批量并行抽象层 — BatchDispatcher 核心实现。

BatchDispatcher 封装 ThreadPoolExecutor，提供链级并行执行、缓存优先过滤、
熔断器感知、限速控制、降级追踪聚合等能力。

线程安全契约：
  - BatchDispatcher 本身**非线程安全**（executor 应被单线程拥有）。
  - execute() 内部通过 Future 天然隔离各任务。
  - 共享对象锁保护验证：
    ✅ DataSourceRegistry — `_provider_lock`(RLock) + `_cache_lock`(RLock)，双锁隔离
    ✅ DegradationTracker — `_lock`(Lock)，所有公共方法（record/get_log/clear/reset）均上锁
    ✅ cache.get/set — 文件级隔离（不同 cache key 不同文件），set() 使用 tempfile.mkstemp + os.replace 原子写，
                      get() 只读无锁，_read_cache_data 对文件不存在/file not found 优雅返回 None
    ✅ get_registry() — `_singleton_lock` 双检锁模式
    ✅ get_tracker() — `_tracker_instance_lock` 双检锁模式
    ✅ session_cache — DataSourceRegistry.session_cache_get/set 均使用 _cache_lock 保护
    ⚠️  cache.clear() 与 get() 之间的 TOCTOU 窗口（clear() 删除文件时 get() 正读），
        _read_cache_data 以 OSError catch 优雅处理（等价于缓存未命中），无实际危害
  - 各辅助方法（successful / failures 等）为纯函数无副作用，天然线程安全。
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("invest")


@dataclass
class BatchResult:
    """单个批量任务执行结果。

    Attributes:
        index: 任务在输入列表中的序号（用于保持结果顺序）。
        success: 任务是否成功完成。
        result: 成功时的返回值。
        error: 失败时的错误描述。
        skipped: 任务是否被跳过（全链熔断等场景）。
    """

    index: int
    success: bool
    result: Any = None
    error: str | None = None
    skipped: bool = False

    def unwrap(self) -> Any:
        """返回结果或抛出 BatchError（失败/跳过时）。"""
        if not self.success:
            reason = self.error or "skipped"
            raise BatchError(f"任务 {self.index} 失败: {reason}")
        return self.result


class BatchError(Exception):
    """批量任务执行错误。"""
    pass


class BatchDispatcher:
    """批量并行调度器 — ThreadPoolExecutor 封装。

    Usage:
        dispatcher = BatchDispatcher(max_workers=3, thread_name_prefix="batch_fund")
        results = dispatcher.execute([task1, task2, task3])
        dispatcher.shutdown()

    或使用上下文管理器（推荐，异常路径自动 shutdown）：
        with BatchDispatcher(max_workers=3) as dispatcher:
            results = dispatcher.execute([task1, task2, task3])
    """

    def __init__(self, max_workers: int = 4, thread_name_prefix: str = "batch"):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        # _registry 初始化为 None，execute_with_chain_precheck 中惰性加载
        self._registry: Any = None

    # ── 上下文管理器 ──

    def __enter__(self) -> BatchDispatcher:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """退出时自动 shutdown，不抑制异常。"""
        self.shutdown(wait=True)
        return False  # 不抑制 with 块内异常

    # ── 基础并行执行 ──

    def execute(self, tasks: list[Callable[[], Any]]) -> list[BatchResult]:
        """并行执行任务列表，返回按输入顺序排列的结果。

        参数按输入顺序返回（通过 futures 完成时的 index 映射）。
        每个异常任务产生一个 success=False 的 BatchResult，不会中断
        其他任务的执行（系统级异常除外）。
        """
        if not tasks:
            return []

        futures = {self._executor.submit(task): i for i, task in enumerate(tasks)}
        results: list[BatchResult | None] = [None] * len(tasks)

        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = BatchResult(index=idx, success=True, result=future.result())
            except BaseException as e:
                # 系统级异常不吞没，立即传播
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                results[idx] = BatchResult(index=idx, success=False, error=str(e))
                # 单资产失败降级为 DEBUG，聚合报告用 WARNING
                logger.debug("[batch:%s] 任务 %d 异常: %s", self._executor._thread_name_prefix, idx, e)

        # 类型安全：execute 保证所有 results 槽位都被填充
        return results  # type: ignore[return-value]

    def shutdown(self, wait: bool = True) -> None:
        """关闭线程池。shutdown 后调用 execute 抛 RuntimeError。"""
        self._executor.shutdown(wait=wait)

    # ── 辅助方法 ──

    @staticmethod
    def successful(results: list[BatchResult]) -> list[Any]:
        """获取所有成功任务的结果。"""
        return [r.result for r in results if r.success]

    @staticmethod
    def failures(results: list[BatchResult]) -> list[tuple[int, str]]:
        """获取所有失败任务的 (index, error) 列表。"""
        return [(r.index, r.error) for r in results if not r.success and r.error]

    @staticmethod
    def all_successful(results: list[BatchResult]) -> bool:
        """所有任务均成功？"""
        return all(r.success for r in results)

    @staticmethod
    def any_failed(results: list[BatchResult]) -> bool:
        """至少一个任务失败？"""
        return any(not r.success for r in results)

    # ── 熔断器感知执行 ──

    def execute_with_chain_precheck(
        self,
        items: list[tuple[str, Callable[[], Any]]],
        data_type: str,
    ) -> list[BatchResult]:
        """熔断器感知执行：批前预检 Provider Chain 状态。

        全链熔断时直接跳过所有任务，避免无意义 HTTP 请求。
        部分熔断时正常执行（fetch_with_fallback 内部跳过已熔断 provider）。

        Args:
            items: (cache_id, task) 列表。
            data_type: 数据类型键，用于查 Provider Chain（如 "price_stock"）。

        Returns:
            全链熔断时所有结果 skipped=True，否则正常执行。
        """
        if not self._registry:
            try:
                from src.python.provider_registry import get_registry
                self._registry = get_registry()
            except Exception:
                logger.debug("[batch] registry 加载失败，跳过熔断预检")
                return self.execute([task for _, task in items])

        chain = self._registry.get_chain(data_type)
        if not chain:
            # 未知 data_type → 无 chain 定义，直接执行
            return self.execute([task for _, task in items])

        if self._registry.is_chain_broken(chain):
            logger.warning(
                "[batch:%s] 全链熔断，跳过 %d 个（chain=%s）",
                data_type, len(items), chain,
            )
            return [
                BatchResult(i, False, skipped=True, error=f"全链熔断:{data_type}")
                for i in range(len(items))
            ]

        return self.execute([task for _, task in items])

    # ── 重试接口 ──

    def retry_failed(
        self,
        results: list[BatchResult],
        task_factory: Callable[[int], Callable[[], Any]],
        max_retries: int = 1,
        delay: float = 0.8,
        jitter: float = 0.4,
    ) -> list[BatchResult]:
        """对失败任务重试（复用主 executor，避免线程泄漏）。

        Args:
            results: 上一次 execute() 返回的结果列表。
            task_factory: 接收失败任务 index，返回新的可执行任务。
            max_retries: 最大重试次数（当前仅支持 1 次）。
            delay: 重试前基础等待时间（秒）。
            jitter: 随机抖动范围（秒）。

        Returns:
            重试后更新过的 results 列表（原地更新成功项）。

        线程安全：
          - 复用 self._executor，不新建 TPE
          - 重试前 sleep 等待，不持有锁
          - self._executor 已 shutdown 时抛 RuntimeError
        """
        import random
        import time

        failed_indices = [r.index for r in results if not r.success and not r.skipped]
        if not failed_indices:
            return results

        actual_delay = delay + random.uniform(0, jitter)
        logger.info(
            "[batch] 重试 %d 个失败任务（delay=%.1fs）",
            len(failed_indices), actual_delay,
        )
        time.sleep(actual_delay)

        for attempt in range(max_retries):
            retry_tasks = [task_factory(idx) for idx in failed_indices]
            retry_results = self.execute(retry_tasks)

            still_failed: list[int] = []
            for orig_idx, rr in zip(failed_indices, retry_results):
                if rr.success:
                    results[orig_idx] = rr
                else:
                    still_failed.append(orig_idx)

            if not still_failed or attempt >= max_retries - 1:
                break
            # 还有失败且还有重试次数 → 继续
            failed_indices = still_failed
            time.sleep(delay * (attempt + 2))  # 退避递增

        return results

    # ── 缓存优先执行 ──

    def execute_with_cache_check(
        self,
        items: list[tuple[str, Callable[[], Any]]],
        cache_check_fn: Callable[[str], Any],
        *,
        strategy_hook: Callable[[], str] | None = None,
        strict_none: bool = False,
    ) -> list[BatchResult]:
        """缓存优先执行：批前先检查缓存，已缓存资产跳过线程池调度。

        双层缓存设计：
          - 批前预检层（此方法）：在 TPE 调度前逐资产检查缓存，
            命中则跳过线程池，减少调度开销。
          - 批内保底层（fetch_with_fallback 内部 cache_get）：TPE 任务
            执行时的第二层缓存检查，处理批前预检到执行之间的窗口期竞争。

        Args:
            items: (cache_id, task) 列表。cache_id 传入 cache_check_fn 检查缓存，
                   task 为无参 Callable，仅当缓存未命中时执行。
            cache_check_fn: 接收 cache_id，返回缓存值（未命中返回 None）。
            strategy_hook: 可选策略预检闭包，返回 "cache" 时全量走缓存。
                           由 get_strategy_hook() 工厂函数构造。
                           不传则退化为普通缓存优先。
            strict_none: 为 True 时，执行结果为 None 的项标记为失败而非成功。
                         适用于业务层以 None 表示"获取失败"的语义（如 industry.py）。

        Returns:
            按 items 顺序排列的结果列表。

        异常安全：
          - strategy_hook 抛异常 → 回退正常执行（fail-open）
          - cache_check_fn 抛异常 → 回退到执行（fail-open）
        """
        # ── 策略预检（仅限传入钩子的数据类型，如行情 CACHE_ONLY）──
        if strategy_hook is not None:
            try:
                strategy = strategy_hook()
                if strategy == "cache":
                    logger.info("[batch] 策略预检=CACHE_ONLY，全量走缓存")
                    cache_results: list[BatchResult] = []
                    for i, (cache_id, _) in enumerate(items):
                        try:
                            cached = cache_check_fn(cache_id)
                            cache_results.append(BatchResult(
                                index=i, success=cached is not None,
                                result=cached,
                            ))
                        except Exception as e:
                            cache_results.append(BatchResult(
                                index=i, success=False, error=str(e),
                            ))
                    return cache_results
            except Exception:
                logger.warning("[batch] 策略预检异常，回退正常执行", exc_info=True)

        # ── 缓存预检 ──
        results: list[BatchResult | None] = [None] * len(items)
        pending_indices: list[int] = []
        pending_tasks: list[Callable[[], Any]] = []

        for i, (cache_id, task) in enumerate(items):
            try:
                cached_value = cache_check_fn(cache_id)
                if cached_value is not None:
                    results[i] = BatchResult(index=i, success=True, result=cached_value)
                    logger.debug("[batch] 缓存命中: %s", cache_id)
                    continue
            except Exception as e:
                # cache_check_fn 抛异常 → fail-open，降级为执行
                logger.debug("[batch] 缓存检查异常(%s), 降级执行: %s", cache_id, e)
            pending_indices.append(i)
            pending_tasks.append(task)

        # ── 执行未命中部分 ──
        if pending_tasks:
            p_results = self.execute(pending_tasks)
            for orig_idx, pr in zip(pending_indices, p_results):
                results[orig_idx] = pr

        # ── strict_none：业务层以 None 表示失败（如 industry.py fetch 返回 None）──
        if strict_none:
            for r in results:
                if r is not None and r.success and r.result is None:
                    r.success = False
                    r.error = "task returned None"

        return results  # type: ignore[return-value]


class RateLimiter:
    """Provider 级别请求间隔控制器。

    防止并发批量操作对同一 Provider 造成请求压力（反爬/限频）。
    不同 Provider 配置独立的请求间隔。
    相同 Provider 的所有请求间隔确保 ≥ 配置值。

    线程安全：使用 per-provider 锁，不同 provider 互不阻塞。

    Usage:
        limiter = RateLimiter({"tiantian": 0.5, "eastmoney": 0.1})
        limiter.acquire("tiantian")
        # 发起 HTTP 请求...
    """

    def __init__(self, config: dict | None = None) -> None:
        self._limits: dict[str, float] = {}
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._load_config(config or {})

    def _load_config(self, config: dict) -> None:
        """从配置字典加载限速规则。"""
        for provider, interval in config.items():
            if isinstance(interval, (int, float)) and interval > 0:
                self._limits[provider] = float(interval)

    def acquire(self, provider: str) -> None:
        """获取请求许可，必要时阻塞直到间隔满足。"""
        interval = self._limits.get(provider, 0.0)
        if interval <= 0:
            return

        # O-4: per-provider 锁，不同 provider 不互相阻塞
        if provider not in self._locks:
            self._locks[provider] = threading.Lock()

        with self._locks[provider]:
            last = self._last_call.get(provider, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < interval:
                time.sleep(interval - elapsed)
            self._last_call[provider] = time.monotonic()

    def reset(self, provider: str) -> None:
        """重置 Provider 的最后调用时间。"""
        self._last_call.pop(provider, None)


def get_batch_worker_count(config_key: str, default: int = 3) -> int:
    """读取 batch 池配置并校验全局线程上限。

    从 config.json 的 batch 段读取指定池的 worker 数，
    确保不超过 batch.max_total_workers 硬上限。

    Args:
        config_key: batch 配置子键（如 "fund_workers"、"industry_workers"）。
        default: 配置缺失时的默认回退值。

    Returns:
        满足上限约束的 worker 数。
    """
    try:
        from src.python.config import get_config

        cfg = get_config()
        batch_cfg = cfg.get("batch", {})
        requested = batch_cfg.get(config_key, default)
        max_total = batch_cfg.get("max_total_workers", 15)

        if not isinstance(requested, (int, float)) or requested < 1:
            requested = default
        if not isinstance(max_total, (int, float)) or max_total < 1:
            max_total = 15

        clamped = min(int(requested), int(max_total))
        if clamped != int(requested):
            logger.warning(
                "[batch] %s 请求 %d workers 超过上限 %d，已钳位至 %d",
                config_key, int(requested), int(max_total), clamped,
            )
        return clamped
    except Exception:
        logger.debug("[batch] 读取 %s 配置失败，回退默认 %d", config_key, default)
        return default


def get_strategy_hook(
    code_type: str,
    chain: list[str] | None = None,
    market_open: bool | None = None,
) -> Callable[[], str] | None:
    """构造策略预检闭包。

    工厂函数，仅在传入数据类型有策略定义时生效。
    当前仅 price_stock/price_index 等行情数据类型有 CACHE_ONLY 策略，
    基金排名/行业/持仓传 None 退化为普通缓存优先。

    使用方式（在行情调用方中）：
        >>> hook = get_strategy_hook("a_share")
        >>> dispatcher.execute_with_cache_check(items, cache_check_fn, strategy_hook=hook)

    内部使用惰性 import 避免循环依赖（provider_registry → fetcher/batch）。
    """
    try:
        from src.python.provider_registry import get_registry

        registry = get_registry()
        # 验证 code_type 是否存在有效策略定义，不存在则返回 None
        if not hasattr(registry, "get_effective_strategy"):
            return None

        def _hook() -> str:
            strategy = registry.get_effective_strategy(code_type, chain, market_open)
            return strategy.value  # "cache" 或 "live"

        return _hook
    except Exception:
        logger.debug("[batch] 策略钩子构造失败，返回 None", exc_info=True)
        return None
