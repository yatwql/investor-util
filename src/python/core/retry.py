"""重试与退避的唯一原语 — 瞬时失败的重试策略、判据与执行器。

三件套（缺一不可，避免退避算式与瞬时判据在 N 处各自实现）：

1. :class:`RetryPolicy` —— **策略**：总尝试次数、退避算式（固定 / 线性 / 指数 / 显式序列）、
   抖动、上限；
   :meth:`RetryPolicy.delay_for` 是退避数值的**唯一算式来源**。
2. :func:`is_transient_exception` —— **判据**：「值得重试」的传输级瞬时失败
   （连接超时 / 连接错误等）统一定义在此，语义为「换一次时机可能成功」。
3. :func:`retry_transient` —— **执行器**：按策略重试，支持两类触发条件——
   异常触发（``retry_on``）与结果哨兵触发（``retry_if_result``，供 Provider Chain 的
   ``TRANSPORT_FAILURE`` 语义使用）；重试日志与睡眠经回调注入，便于测试注入零等待。

使用约束：网络请求本身仍必须经 ``core/http_client.py`` 工厂（HTTP 客户端统一约定）；
本模块只决定「何时再试一次」，不构造客户端、不碰缓存。
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("invest")

#: 「值得重试」的传输级瞬时异常：连接超时、连接错误、远端中断等
TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.RequestError,
)

#: 退避算式标识
STRATEGY_FIXED = "fixed"
STRATEGY_LINEAR = "linear"
STRATEGY_EXPONENTIAL = "exponential"
STRATEGY_TABLE = "table"
_STRATEGIES = frozenset({STRATEGY_FIXED, STRATEGY_LINEAR, STRATEGY_EXPONENTIAL, STRATEGY_TABLE})


def is_transient_exception(exc: BaseException) -> bool:
    """是否属于「值得重试」的传输级瞬时失败。"""
    return isinstance(exc, TRANSIENT_EXCEPTIONS)


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略：次数 + 退避算式 + 抖动。

    Attributes:
        attempts: **总尝试次数**（含首次）；``1`` 表示不重试。``<1`` 时按 1 处理。
        strategy: 退避算式——``fixed``（每次相同）/ ``linear``（基础值 × 第几次）/
            ``exponential``（基础值 × factor^(第几次-1)）/ ``table``（显式序列，见 ``delays``）。
        base_backoff: 退避基础值（秒）。``<= 0`` 表示**不等待**（立即重试）；
            ``table`` 算式不使用本项。
        factor: 指数算式的倍率。
        jitter: 抖动上界（秒），每次退避叠加 ``uniform(0, jitter)``。
        max_backoff: 单次退避上限（秒）；None 表示不设上限。
        delays: ``table`` 算式的显式退避序列（秒）：第 N 次失败取第 N 项，**超出序列末位
            锁定末位值**（不报错、不退化为 0）。供「手工调优的非等比退避表」使用——
            固定/线性/指数三种算式表达不了这类序列。
    """

    attempts: int = 2
    strategy: str = STRATEGY_EXPONENTIAL
    base_backoff: float = 0.6
    factor: float = 2.0
    jitter: float = 0.0
    max_backoff: float | None = None
    delays: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.attempts < 1:
            object.__setattr__(self, "attempts", 1)
        if self.delays and not isinstance(self.delays, tuple):
            object.__setattr__(self, "delays", tuple(self.delays))
        if self.strategy not in _STRATEGIES:
            logger.warning("[retry] 未知退避算式 %r，按指数处理", self.strategy)
            object.__setattr__(self, "strategy", STRATEGY_EXPONENTIAL)
        elif self.strategy == STRATEGY_TABLE and not self.delays:
            logger.warning("[retry] 显式退避序列为空，按指数处理")
            object.__setattr__(self, "strategy", STRATEGY_EXPONENTIAL)

    @property
    def retry_count(self) -> int:
        """额外重试次数（总尝试次数 - 1）。"""
        return self.attempts - 1

    def delay_for(self, failed_attempt: int) -> float:
        """第 ``failed_attempt`` 次尝试失败后应等待的秒数（1-based）；0 表示不等待。"""
        if self.strategy == STRATEGY_TABLE and self.delays:
            base = self.delays[min(max(failed_attempt, 1), len(self.delays)) - 1]
            if self.max_backoff is not None:
                base = min(base, self.max_backoff)
            if base <= 0:
                return 0.0
            return base + (random.uniform(0, self.jitter) if self.jitter > 0 else 0.0)
        if self.base_backoff <= 0:
            return 0.0
        if self.strategy == STRATEGY_LINEAR:
            base = self.base_backoff * failed_attempt
        elif self.strategy == STRATEGY_FIXED:
            base = self.base_backoff
        else:
            base = self.base_backoff * (self.factor ** (failed_attempt - 1))
        if self.max_backoff is not None:
            base = min(base, self.max_backoff)
        return base + (random.uniform(0, self.jitter) if self.jitter > 0 else 0.0)


def retry_transient(
    fn: Callable[[], Any],
    *,
    policy: RetryPolicy,
    retry_on: Callable[[BaseException], bool] | None = None,
    retry_if_result: Callable[[Any], bool] | None = None,
    on_retry: Callable[[int, float, BaseException | None], None] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Any:
    """按策略执行 ``fn``，遇到「可重试」情形则退避后重试，全部耗尽即返回最后一次结果。

    可重试情形（二者可同时给出，任一命中即重试）：
      - ``retry_on(exc)`` 为真（默认 :func:`is_transient_exception`）；未给出
        ``retry_if_result`` 时，重试耗尽会**抛出最后一次异常**，由调用方决定如何降级；
      - ``retry_if_result(result)`` 为真（结果哨兵，如 Provider Chain 的
        ``TRANSPORT_FAILURE``）——此时返回该结果而非抛异常。

    Args:
        fn: 无参取数函数（调用方用闭包传参）。
        policy: 重试策略。
        retry_on: 异常判定；``None`` = 默认瞬时判据；恒 False 可关闭异常触发。
        retry_if_result: 结果判定；``None`` = 不按结果重试。
        on_retry: 每次重试前的回调 ``(已失败次数, 本次退避秒数, 异常或 None)``，
            供各调用方写自己的日志文案。
        sleep: 睡眠函数（测试注入零等待实现）。
    """
    _sleep = sleep or time.sleep
    judge = retry_on if retry_on is not None else is_transient_exception
    last_exc: BaseException | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            result = fn()
        except BaseException as exc:  # noqa: BLE001 — 判据决定是否可重试，非瞬时异常原样抛出
            last_exc = exc
            if not judge(exc) or attempt >= policy.attempts:
                raise
            delay = policy.delay_for(attempt)
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            if delay > 0:
                _sleep(delay)
            continue
        last_exc = None
        if retry_if_result is None or not retry_if_result(result) or attempt >= policy.attempts:
            return result
        delay = policy.delay_for(attempt)
        if on_retry is not None:
            on_retry(attempt, delay, None)
        if delay > 0:
            _sleep(delay)
    if last_exc is not None:  # pragma: no cover - 上面的分支已穷尽策略
        raise last_exc
    return None
