"""按名最小间隔节流原语 — 所有「两次请求之间至少隔多久」的唯一实现。

放在 ``core/`` 而非某个上层模块，是因为它被**三个层次**共用：
数据层（``providers/*`` 的 qps 限速）、批量调度层（``fetcher/batch.py`` 的
``batch_rate_limit``）、LLM 层（``llm/pacing.py`` 的端点级节流）。
语义只有一条：**同一 key（provider/端点）的相邻两次放行间隔 ≥ 给定值**；
key 之间互不阻塞（per-key 锁），抖动可选（避免固定节奏的机器特征）。

用法::

    limiter = RateLimiter({"tiantian": 0.5, "eastmoney": 0.1})
    limiter.acquire("tiantian")            # 按构造期配置的间隔
    limiter.acquire_interval("ep", 20.0, jitter_ratio=0.2)   # 按显式间隔 + 抖动
"""

from __future__ import annotations

import random
import threading
import time

#: 抖动上界相对间隔的比例（0 = 无抖动）
DEFAULT_JITTER_RATIO = 0.0


def interval_delay(interval: float, jitter_ratio: float = DEFAULT_JITTER_RATIO) -> float:
    """间隔 + 抖动的**唯一算式**：``interval + uniform(0, interval × jitter_ratio)``。

    ``interval <= 0`` 返回 0（不等待）；``jitter_ratio`` 在 [0, 1] 外按端点钳制。
    """
    if interval <= 0:
        return 0.0
    ratio = min(1.0, max(0.0, float(jitter_ratio)))
    if ratio <= 0:
        return float(interval)
    return float(interval) + random.uniform(0.0, interval * ratio)


class RateLimiter:
    """Provider/端点级别请求间隔控制器。

    防止并发操作对同一 Provider 造成请求压力（反爬/限频/风控）。
    不同 Provider 配置独立的请求间隔；相同 Provider 的所有请求间隔确保 ≥ 配置值。

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
        """从配置字典加载限速规则（非数值或 <=0 的条目忽略）。"""
        for provider, interval in config.items():
            if isinstance(interval, (int, float)) and interval > 0:
                self._limits[provider] = float(interval)

    def acquire(self, provider: str) -> None:
        """按构造期配置的间隔获取请求许可，必要时阻塞。"""
        interval = self._limits.get(provider, 0.0)
        if interval <= 0:
            return
        self.acquire_interval(provider, interval)

    def acquire_interval(
        self,
        provider: str,
        interval: float,
        jitter_ratio: float = DEFAULT_JITTER_RATIO,
    ) -> float:
        """按**显式间隔**获取许可（不受构造时配置约束），返回实际等待秒数。

        与 :meth:`acquire` 的区别：间隔由调用方逐次给出而非构造时固定——LLM 端点节流
        需要按策略动态计算（含随机抖动），且同一 provider 的策略可在运行期刷新。

        Args:
            provider: 端点/源标识（作为间隔计量的键）
            interval: 本次要求的最小间隔（秒）；<= 0 不等待
            jitter_ratio: 抖动比例（0~1），叠加 ``uniform(0, interval × ratio)``
        """
        target = interval_delay(interval, jitter_ratio)
        if target <= 0:
            return 0.0

        # per-provider 锁，不同 provider 不互相阻塞
        if provider not in self._locks:
            self._locks[provider] = threading.Lock()

        with self._locks[provider]:
            last = self._last_call.get(provider, 0.0)
            elapsed = time.monotonic() - last
            waited = 0.0
            if elapsed < target:
                waited = target - elapsed
                time.sleep(waited)
            self._last_call[provider] = time.monotonic()
            return waited

    def reset(self, provider: str) -> None:
        """重置 Provider 的最后调用时间。"""
        self._last_call.pop(provider, None)
