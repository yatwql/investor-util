"""BatchDispatcher 单元测试。

测试目标：
  - execute() — 基础并行执行、结果顺序、空列表退化、异常处理
  - 辅助方法 — successful / failures / all_successful / any_failed
  - 上下文管理器 — with 块自动 shutdown
  - execute() 系统级异常（KeyboardInterrupt/SystemExit）不吞没
  - BatchResult — unwrap 成功/失败路径

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/fetcher/test_batch.py -v --tb=short
"""

from __future__ import annotations

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from src.python.fetcher.batch import BatchDispatcher, BatchError, BatchResult

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


# ═══════════════════════════════════════════════════════════════
#  BatchResult
# ═══════════════════════════════════════════════════════════════


class TestBatchResult(unittest.TestCase):
    """BatchResult 数据类 + unwrap 测试。"""

    def test_unwrap_success(self):
        """成功结果 → unwrap 返回值。"""
        r = BatchResult(index=0, success=True, result=42)
        self.assertEqual(r.unwrap(), 42)

    def test_unwrap_failure(self):
        """失败结果 → unwrap 抛 BatchError。"""
        r = BatchResult(index=0, success=False, error="网络超时")
        with self.assertRaises(BatchError) as ctx:
            r.unwrap()
        self.assertIn("网络超时", str(ctx.exception))

    def test_unwrap_skipped(self):
        """跳过结果 → unwrap 抛 BatchError。"""
        r = BatchResult(index=0, success=False, skipped=True)
        with self.assertRaises(BatchError) as ctx:
            r.unwrap()
        self.assertIn("skipped", str(ctx.exception))

    def test_unwrap_default_error(self):
        """失败且无 error 描述 → unwrap 抛含 unknown 的异常。"""
        r = BatchResult(index=0, success=False)
        with self.assertRaises(BatchError):
            r.unwrap()


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 基础执行
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherExecute(unittest.TestCase):
    """BatchDispatcher.execute() 基础并行执行测试。"""

    def setUp(self):
        self.dispatcher = BatchDispatcher(max_workers=4, thread_name_prefix="test_batch")

    def tearDown(self):
        self.dispatcher.shutdown(wait=False)

    def test_execute_returns_in_order(self):
        """3 个不同耗时任务 → 返回结果按输入顺序排列。"""
        def task(val: int, delay: float):
            time.sleep(delay)
            return val

        tasks = [
            lambda: task(1, 0.15),
            lambda: task(2, 0.05),
            lambda: task(3, 0.10),
        ]
        results = self.dispatcher.execute(tasks)
        values = [r.result for r in results]
        self.assertEqual(values, [1, 2, 3])

    def test_execute_empty(self):
        """空列表 → 返回空列表。"""
        self.assertEqual(self.dispatcher.execute([]), [])

    def test_execute_all_successful(self):
        """全部任务成功 → 所有 BatchResult.success=True。"""
        results = self.dispatcher.execute([lambda: "ok", lambda: "ok"])
        self.assertTrue(all(r.success for r in results))

    def test_execute_with_failures(self):
        """部分任务失败 → 对应 BatchResult.success=False，其他正常。"""

        def fail():
            raise ValueError("模拟异常")

        results = self.dispatcher.execute([fail, lambda: 42])
        self.assertFalse(results[0].success)
        self.assertIn("模拟异常", results[0].error or "")
        self.assertTrue(results[1].success)
        self.assertEqual(results[1].result, 42)

    def test_execute_max_workers_one_is_serial(self):
        """max_workers=1 → 串行执行（按输入顺序完成）。"""
        order: list[int] = []

        def task(idx: int, delay: float):
            time.sleep(delay)
            order.append(idx)
            return idx

        disp = BatchDispatcher(max_workers=1, thread_name_prefix="test_serial")
        try:
            tasks = [
                lambda: task(1, 0.08),
                lambda: task(2, 0.03),
                lambda: task(3, 0.01),
            ]
            disp.execute(tasks)
            # 串行时先提交的先完成
            self.assertEqual(order, [1, 2, 3])
        finally:
            disp.shutdown()

    def test_execute_thread_name_prefix(self):
        """线程名前缀包含指定名称。"""
        import threading

        captured_names: list[str] = []

        def capture():
            captured_names.append(threading.current_thread().name)
            return None

        disp = BatchDispatcher(max_workers=2, thread_name_prefix="batch_price")
        try:
            disp.execute([capture, capture])
            for name in captured_names:
                self.assertIn("batch_price", name)
        finally:
            disp.shutdown()


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: KeyboardInterrupt 传播
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherBaseException(unittest.TestCase):
    """系统级异常不吞没。"""

    def test_keyboard_interrupt_propagates(self):
        """KeyboardInterrupt → 不转成 BatchResult，直接传播。"""
        disp = BatchDispatcher(max_workers=2)
        try:
            with self.assertRaises(KeyboardInterrupt):
                disp.execute([lambda: (_ for _ in ()).throw(KeyboardInterrupt())])
        finally:
            disp.shutdown(wait=False)

    def test_system_exit_propagates(self):
        """SystemExit → 直接传播。"""
        disp = BatchDispatcher(max_workers=2)
        try:
            with self.assertRaises(SystemExit):
                disp.execute([lambda: (_ for _ in ()).throw(SystemExit())])
        finally:
            disp.shutdown(wait=False)


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 辅助方法
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherHelpers(unittest.TestCase):
    """辅助方法（successful / failures / all_successful / any_failed）。"""

    def setUp(self):
        self.all_ok = [
            BatchResult(0, True, result=10),
            BatchResult(1, True, result=20),
        ]
        self.mixed = [
            BatchResult(0, True, result=10),
            BatchResult(1, False, error="失败"),
            BatchResult(2, True, result=30),
        ]
        self.all_failed = [
            BatchResult(0, False, error="e1"),
            BatchResult(1, False, error="e2"),
        ]

    def test_successful_all_ok(self):
        """全部成功 → successful 返回全部结果。"""
        self.assertEqual(BatchDispatcher.successful(self.all_ok), [10, 20])

    def test_successful_mixed(self):
        """混合成功 → successful 仅返回成功结果。"""
        self.assertEqual(BatchDispatcher.successful(self.mixed), [10, 30])

    def test_successful_all_failed(self):
        """全部失败 → successful 返回空列表。"""
        self.assertEqual(BatchDispatcher.successful(self.all_failed), [])

    def test_failures_mixed(self):
        """混合 → failures 返回失败项 (index, error)。"""
        fails = BatchDispatcher.failures(self.mixed)
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0], (1, "失败"))

    def test_failures_all_ok(self):
        """全部成功 → failures 返回空列表。"""
        self.assertEqual(BatchDispatcher.failures(self.all_ok), [])

    def test_all_successful_yes(self):
        """全部成功 → True。"""
        self.assertTrue(BatchDispatcher.all_successful(self.all_ok))

    def test_all_successful_no(self):
        """部分失败 → False。"""
        self.assertFalse(BatchDispatcher.all_successful(self.mixed))

    def test_any_failed_yes(self):
        """至少一个失败 → True。"""
        self.assertTrue(BatchDispatcher.any_failed(self.mixed))

    def test_any_failed_no(self):
        """全部成功 → False。"""
        self.assertFalse(BatchDispatcher.any_failed(self.all_ok))


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 上下文管理器
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherContextManager(unittest.TestCase):
    """上下文管理器 __enter__ / __exit__。"""

    def test_context_manager_shutdown_on_exit(self):
        """with 块退出后 → executor 已 shutdown。"""
        dispatcher = BatchDispatcher(max_workers=2)
        with dispatcher as d:
            self.assertIs(d, dispatcher)
            d.execute([lambda: 1, lambda: 2])
        # 退出 with 块后 shutdown 被调用
        self.assertTrue(dispatcher._executor._shutdown)

    def test_context_manager_shutdown_on_exception(self):
        """with 块内异常 → 仍 shutdown，异常传播。"""
        dispatcher = BatchDispatcher(max_workers=2)
        with self.assertRaises(RuntimeError):
            with dispatcher as d:
                d.execute([lambda: 1])
                raise RuntimeError("模拟异常")
        # 异常路径也调用了 shutdown
        self.assertTrue(dispatcher._executor._shutdown)


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 线程安全相关
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherThreadSafety(unittest.TestCase):
    """_registry 初始状态。"""

    def test_registry_defaults_to_none(self):
        """_registry 默认初始化为 None。"""
        disp = BatchDispatcher()
        try:
            self.assertIsNone(disp._registry)
        finally:
            disp.shutdown(wait=False)


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 缓存优先执行
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherCacheCheck(unittest.TestCase):
    """execute_with_cache_check 缓存优先执行。"""

    def setUp(self):
        self.dispatcher = BatchDispatcher(max_workers=4, thread_name_prefix="test_cache")

    def tearDown(self):
        self.dispatcher.shutdown(wait=False)

    def test_all_cache_hit(self):
        """全部缓存命中 → 0 次线程池执行（无 pending 任务）。"""
        items = [
            ("code_a", lambda: "slow_a"),
            ("code_b", lambda: "slow_b"),
        ]

        def check(cache_id: str):
            return {f"data_{cache_id}"}

        results = self.dispatcher.execute_with_cache_check(items, check)
        self.assertTrue(all(r.success for r in results))
        self.assertEqual(results[0].result, {"data_code_a"})
        self.assertEqual(results[1].result, {"data_code_b"})

    def test_partial_cache_hit(self):
        """部分缓存命中 → 仅未命中部分执行线程。"""
        call_count = 0

        def slow_task():
            nonlocal call_count
            call_count += 1
            return 42

        items = [
            ("hit_1", slow_task),
            ("miss_1", slow_task),
            ("hit_2", slow_task),
            ("miss_2", slow_task),
        ]

        def check(cache_id: str):
            if cache_id.startswith("hit_"):
                return f"cached_{cache_id}"
            return None

        results = self.dispatcher.execute_with_cache_check(items, check)
        # 2 个命中，2 个未命中 → 仅 2 次调用
        self.assertEqual(call_count, 2)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, "cached_hit_1")
        self.assertTrue(results[1].success)
        self.assertEqual(results[1].result, 42)

    def test_no_cache_hit(self):
        """无缓存命中 → 全部执行。"""
        call_count = 0

        def task():
            nonlocal call_count
            call_count += 1
            return 1

        items = [
            ("a", task),
            ("b", task),
        ]

        def check(_cache_id: str):
            return None

        results = self.dispatcher.execute_with_cache_check(items, check)
        self.assertEqual(call_count, 2)
        self.assertTrue(all(r.success for r in results))

    def test_cache_check_fn_raises(self):
        """cache_check_fn 抛异常 → fail-open，降级为执行。"""
        call_count = 0

        def task():
            nonlocal call_count
            call_count += 1
            return "fallback"

        items = [("err", task)]

        def check(_cache_id: str):
            raise OSError("缓存文件损坏")

        results = self.dispatcher.execute_with_cache_check(items, check)
        self.assertEqual(call_count, 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, "fallback")

    def test_empty_items(self):
        """空列表 → 返回空列表。"""
        results = self.dispatcher.execute_with_cache_check([], lambda x: None)
        self.assertEqual(results, [])

    def test_strict_none_default_preserves_none(self):
        """strict_none=False（默认）→ None 结果保持 success=True。"""
        items = [("a", lambda: None)]
        results = self.dispatcher.execute_with_cache_check(
            items, lambda x: None,
        )
        self.assertTrue(results[0].success)
        self.assertIsNone(results[0].result)

    def test_strict_none_marks_none_as_failure(self):
        """strict_none=True → None 结果标记为失败。"""
        items = [("a", lambda: 42), ("b", lambda: None)]
        results = self.dispatcher.execute_with_cache_check(
            items, lambda x: None, strict_none=True,
        )
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, 42)
        self.assertFalse(results[1].success)
        self.assertIn("None", results[1].error or "")


class TestBatchDispatcherStrategyHook(unittest.TestCase):
    """execute_with_cache_check strategy_hook 策略预检。"""

    def setUp(self):
        self.dispatcher = BatchDispatcher(max_workers=4, thread_name_prefix="test_strategy")

    def tearDown(self):
        self.dispatcher.shutdown(wait=False)

    def test_strategy_cache_only_uses_cache(self):
        """strategy_hook 返回 'cache' → 全量走缓存，0 次线程池。"""
        call_count = 0

        def task():
            nonlocal call_count
            call_count += 1
            return "live"

        items = [("a", task), ("b", task)]

        def check(cache_id: str):
            return f"cached_{cache_id}" if cache_id == "a" else None

        def hook():
            return "cache"

        results = self.dispatcher.execute_with_cache_check(
            items, check, strategy_hook=hook,
        )
        # 0 次线程池调用
        self.assertEqual(call_count, 0)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, "cached_a")
        # "b" 缓存未命中 → success=False
        self.assertFalse(results[1].success)

    def test_strategy_live_fetch(self):
        """strategy_hook 返回 'live' → 正常执行。"""
        def task():
            return "live_data"

        items = [("a", task)]

        def check(_cache_id: str):
            return None

        def hook():
            return "live"

        results = self.dispatcher.execute_with_cache_check(
            items, check, strategy_hook=hook,
        )
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, "live_data")

    def test_strategy_hook_raises(self):
        """strategy_hook 抛异常 → fail-open，回退正常执行。"""
        call_count = 0

        def task():
            nonlocal call_count
            call_count += 1
            return "fallback"

        items = [("a", task)]

        def check(_cache_id: str):
            return None

        def hook():
            raise RuntimeError("策略判断失败")

        results = self.dispatcher.execute_with_cache_check(
            items, check, strategy_hook=hook,
        )
        self.assertEqual(call_count, 1)
        self.assertTrue(results[0].success)

    def test_no_strategy_hook(self):
        """不传 strategy_hook → 与原有缓存优先行为一致。"""
        call_count = 0

        def task():
            nonlocal call_count
            call_count += 1
            return "ok"

        items = [("cached", task)]

        def check(cache_id: str):
            return "from_cache" if cache_id == "cached" else None

        results = self.dispatcher.execute_with_cache_check(items, check)
        self.assertEqual(call_count, 0)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, "from_cache")


class TestGetStrategyHook(unittest.TestCase):
    """get_strategy_hook 工厂函数。"""

    def test_unknown_type_always_constructable(self):
        """未知 code_type → 构造成功，不会抛异常。"""
        from src.python.fetcher.batch import get_strategy_hook

        hook = get_strategy_hook("nonexistent_type")
        self.assertIsNotNone(hook)
        # 构造后可调用，返回 "live" 或 "cache"
        result = hook()
        self.assertIn(result, ("live", "cache"))


# ═══════════════════════════════════════════════════════════════
#  RateLimiter
# ═══════════════════════════════════════════════════════════════


class TestRateLimiter(unittest.TestCase):
    """Provider 级别请求间隔控制。"""

    def test_no_limit_no_wait(self):
        """未配置的 provider → 无等待。"""
        from src.python.fetcher.batch import RateLimiter

        limiter = RateLimiter()
        t0 = time.monotonic()
        limiter.acquire("unknown_provider")
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.05)  # 几乎无等待

    def test_zero_interval_no_wait(self):
        """interval=0 → 无等待。"""
        from src.python.fetcher.batch import RateLimiter

        limiter = RateLimiter({"tiantian": 0.0})
        t0 = time.monotonic()
        limiter.acquire("tiantian")
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.05)

    def test_interval_enforced(self):
        """同一 provider 两次 acquire 间隔 >= 配置值。"""
        from src.python.fetcher.batch import RateLimiter

        limiter = RateLimiter({"test_provider": 0.1})
        limiter.acquire("test_provider")
        t0 = time.monotonic()
        limiter.acquire("test_provider")
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, 0.08)  # 允许微小误差

    def test_different_providers_no_block(self):
        """不同 provider → 互不阻塞。"""
        from src.python.fetcher.batch import RateLimiter

        limiter = RateLimiter({"p1": 1.0, "p2": 0.0})
        limiter.acquire("p1")
        t0 = time.monotonic()
        limiter.acquire("p2")  # p2 无限制，不受 p1 影响
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.05)

    def test_reset_clears_last_call(self):
        """reset 后 acquire 无需等待。"""
        from src.python.fetcher.batch import RateLimiter

        limiter = RateLimiter({"p": 1.0})
        limiter.acquire("p")
        limiter.reset("p")
        t0 = time.monotonic()
        limiter.acquire("p")
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.05)


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 熔断器感知
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherChainPrecheck(unittest.TestCase):
    """execute_with_chain_precheck 熔断预检。"""

    def _make_mock_registry(self, chain, broken):
        reg = MagicMock()
        reg.get_chain.return_value = chain
        reg.is_chain_broken.return_value = broken
        return reg

    def setUp(self):
        self.dispatcher = BatchDispatcher(max_workers=2, thread_name_prefix="test_chain")

    def tearDown(self):
        self.dispatcher.shutdown(wait=False)

    def test_chain_broken_all_skipped(self):
        """全链熔断 → 全部 skipped，0 次执行。"""
        mock_reg = self._make_mock_registry(["tiantian"], True)
        self.dispatcher._registry = mock_reg

        call_count = 0

        def task():
            nonlocal call_count
            call_count += 1
        items = [("a", task), ("b", task)]
        results = self.dispatcher.execute_with_chain_precheck(items, "fund_rank")

        self.assertEqual(call_count, 0)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.skipped for r in results))
        self.assertFalse(any(r.success for r in results))
        self.assertIn("全链熔断", results[0].error or "")

    def test_chain_normal_exeuctes(self):
        """链正常 → execute 正常执行。"""
        mock_reg = self._make_mock_registry(["tiantian"], False)

        self.dispatcher._registry = mock_reg
        items = [("a", lambda: "ok"), ("b", lambda: "data")]
        results = self.dispatcher.execute_with_chain_precheck(items, "fund_rank")

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))

    def test_chain_unknown_type(self):
        """未知 data_type → 返回空 chain，仍执行。"""
        mock_reg = self._make_mock_registry([], False)

        self.dispatcher._registry = mock_reg
        items = [("a", lambda: "ok")]
        results = self.dispatcher.execute_with_chain_precheck(items, "unknown")

        self.assertTrue(results[0].success)
        self.assertEqual(results[0].result, "ok")

    def test_chain_no_registry_fallback(self):
        """registry 未初始化 → 惰性加载失败时仍执行。"""
        items = [("a", lambda: "ok")]
        results = self.dispatcher.execute_with_chain_precheck(items, "test")
        # registry 为 None，跳过预检直接执行
        self.assertTrue(results[0].success)

    def test_chain_broken_logs_warning(self):
        """全链熔断 -> skipped 结果含错误信息（日志在代码内部已 WARNING）。"""
        mock_reg = self._make_mock_registry(["tencent", "sina"], True)
        self.dispatcher._registry = mock_reg
        results = self.dispatcher.execute_with_chain_precheck([("a", lambda: 1)], "price_stock")
        self.assertTrue(results[0].skipped)
        self.assertIn("全链熔断", results[0].error or "")


# ═══════════════════════════════════════════════════════════════
#  BatchDispatcher: 重试接口
# ═══════════════════════════════════════════════════════════════


class TestBatchDispatcherRetry(unittest.TestCase):
    """retry_failed 重试逻辑。"""

    def setUp(self):
        self.dispatcher = BatchDispatcher(max_workers=4, thread_name_prefix="test_retry")

    def tearDown(self):
        self.dispatcher.shutdown(wait=False)

    def test_retry_no_failures_returns_immediately(self):
        """无失败任务 → 立即返回，无等待。"""
        results = [
            BatchResult(0, True, result=10),
            BatchResult(1, True, result=20),
        ]
        t0 = time.monotonic()
        updated = self.dispatcher.retry_failed(results, lambda i: lambda: 0)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.05)  # 几乎无等待
        self.assertIs(updated, results)  # 返回相同列表对象

    def test_retry_fixes_failures(self):
        """失败任务重试成功 → results 被更新。"""
        call_count = [0]  # 用列表实现闭包写入

        def task_factory(idx: int):
            def _task():
                call_count[0] += 1
                return f"fixed_{idx}"
            return _task

        results = [
            BatchResult(0, True, result="ok"),
            BatchResult(1, False, error="临时异常"),
        ]
        updated = self.dispatcher.retry_failed(results, task_factory, delay=0.01, jitter=0.01)
        self.assertTrue(updated[1].success)
        self.assertEqual(updated[1].result, "fixed_1")

    def test_retry_preserves_successful(self):
        """成功任务不受重试影响。"""
        def task_factory(idx: int):
            return lambda: f"retry_{idx}"

        results = [
            BatchResult(0, True, result="original"),
            BatchResult(1, False, error="err"),
        ]
        updated = self.dispatcher.retry_failed(results, task_factory, delay=0.01, jitter=0.01)
        self.assertEqual(updated[0].result, "original")  # 未被覆盖

    def test_retry_skips_skipped(self):
        """skipped=True 的任务不重试。"""
        call_count = [0]

        def task_factory(idx: int):
            def _task():
                call_count[0] += 1
                return "retried"
            return _task

        results = [
            BatchResult(0, False, skipped=True, error="全链熔断"),
            BatchResult(1, False, error="真实失败"),
        ]
        updated = self.dispatcher.retry_failed(results, task_factory, delay=0.01, jitter=0.01)
        # skipped 的不重试
        self.assertTrue(updated[0].skipped)
        self.assertTrue(updated[0].error == "全链熔断")
