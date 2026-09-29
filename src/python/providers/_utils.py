"""提供商模块共享工具函数。

包含跨多个新闻/数据 API 提供商模块共用的辅助函数。
"""

from __future__ import annotations

import logging
import time

from src.python.core.constants import BEIJING_TZ
from src.python.core.retry import STRATEGY_FIXED, STRATEGY_LINEAR, RetryPolicy, is_transient_exception, retry_transient
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from typing import Any, Callable

from src.python.core.num_utils import safe_num

logger = logging.getLogger("invest")

#: 「挂起型」失败判定比例：单次尝试耗时 ≥ 超时预算 × 该比例，视为**主机不可达/连接被丢**
#: （而非瞬时抖动）——此时重试只会把等待放大成 N × 超时（实测：20s 预算 × 3 次 = 63s），
#: 故不再重试、直接上抛，由链路计入熔断并让后续请求快速跳过。
#: 「快速失败」（连接被拒/重置/DNS 立即失败）仍按策略正常重试。
HANG_ELAPSED_RATIO = 0.5


#: 连接级瞬时失败重试策略（线性退避 1s、2s；总尝试 3 次）—— datasink / hithink / cninfo
#: 三处连接级重试**共用同一策略实例**（差异只用 ``with_connect_retry`` 的 log_tag/label 表达）。
#: 瞬时常量判据与退避算式取自 ``core/retry``（重试与退避唯一原语）。
CONNECT_RETRY_POLICY = RetryPolicy(attempts=3, strategy=STRATEGY_LINEAR, base_backoff=1.0)


def build_transient_retry_judge(elapsed: float, timeout: float) -> Callable[[BaseException], bool]:
    """构造「瞬时 **且非挂起**」的重试判据（供各 provider 的连接级重试共用）。

    Args:
        elapsed: 本次（刚失败的）尝试耗时秒数。
        timeout: 该请求的超时预算秒数（比例阈值为 ``timeout * HANG_ELAPSED_RATIO``）。

    Returns:
        判据函数：瞬时异常且未挂起→True（可重试）；否则 False（不再重试）。
    """
    threshold = timeout * HANG_ELAPSED_RATIO

    def _judge(exc: BaseException) -> bool:
        return is_transient_exception(exc) and elapsed < threshold

    return _judge


def with_connect_retry(
    request_fn: Callable[[], Any],
    *,
    timeout: float,
    log_tag: str,
    label: str,
    before_attempt: Callable[[], None] | None = None,
) -> Any:
    """执行一次请求；连接级瞬时失败按 ``CONNECT_RETRY_POLICY`` 退避重试，**耗尽后上抛**。

    统一 datasink / hithink / cninfo 三处的连接级重试**脚手架**（策略、耗时统计、挂起判据、
    重试/挂起日志、每次尝试前的限速许可）—— 各来源差异只用 ``log_tag`` / ``label`` /
    ``before_attempt`` 表达，避免同一约束各写一份（改一处漏两处）。

    上抛是刻意设计：链路（``fetcher/chain``）的传输级判据**只认异常**，若在此吞成 None，
    链路会把它当成「代码级空结果」——同源重试不触发、熔断与可用性统计不计、诊断文案误导。
    经链路的 provider 槽由链路承接上抛；**不经链路的直连调用方自行决定降级**（见 cninfo）。

    Args:
        request_fn: 实际执行一次的请求（无参闭包，返回响应对象）。
        timeout: 单次请求超时预算（挂起判据阈值 = ``timeout * HANG_ELAPSED_RATIO``）。
        log_tag: 日志来源标识（如 ``"datasink"``，输出形如 ``[datasink] 连接挂起 …``）。
        label: 日志中的请求标识（路径 / URL）。
        before_attempt: 每次尝试前的钩子（如获取限速许可）；None 表示无需。

    Returns:
        最后一次尝试的返回值；失败按策略上抛。
    """
    elapsed = {"s": 0.0}

    def _attempt() -> Any:
        # 限速许可等待不计入「本次尝试耗时」——只有请求本身接近超时才算「挂起」
        # （否则用户把 qps 调得很低时，等待会被误判为主机不可达而放弃重试）
        if before_attempt is not None:
            before_attempt()
        started = time.monotonic()
        try:
            return request_fn()
        finally:
            elapsed["s"] = time.monotonic() - started

    def _on_retry(failed_attempt: int, delay: float, exc: BaseException | None) -> None:
        logger.warning(
            "[%s] 连接失败 %s（%s），%.1fs 后重试（第 %d/%d 次尝试）",
            log_tag,
            label,
            exc,
            delay,
            failed_attempt,
            CONNECT_RETRY_POLICY.attempts,
        )

    def _should_retry(exc: BaseException) -> bool:
        """挂起型（耗时接近超时预算）不重试：再试只会线性放大等待。"""
        if not build_transient_retry_judge(elapsed["s"], timeout)(exc):
            if elapsed["s"] >= timeout * HANG_ELAPSED_RATIO:
                logger.warning(
                    "[%s] 连接挂起 %.1fs（≥超时预算一半），判定主机不可达，不再重试：%s",
                    log_tag,
                    elapsed["s"],
                    label,
                )
            return False
        return True

    return retry_transient(
        _attempt,
        policy=CONNECT_RETRY_POLICY,
        retry_on=_should_retry,
        on_retry=_on_retry,
        sleep=time.sleep,
    )


def run_with_timeout(
    fn: Callable[[], Any], timeout: float = 15.0, retries: int = 1, raise_on_failure: bool = False
) -> Any:
    """在线程中执行函数，超时或异常时重试，全部失败返回 None（或按需上抛）。

    供 akshare 等**同步且无超时参数**的第三方取数函数使用：在独立线程中执行
    并设上限，避免单个调用挂死整条报告链路。

    Args:
        fn: 要执行的函数（无参，调用方用闭包传入参数）
        timeout: 每次调用的超时秒数
        retries: 失败后的重试次数（默认 1 次）
        raise_on_failure: 重试耗尽后**上抛最后一次异常**而非返回 None。仅**链路消费方**
            （``fetcher/chain`` 的 provider 槽）设为 True——链路的传输级判据只认异常，
            上抛才能得到同源重试 + 熔断计数 + 诚实诊断文案；无链路承装的直连调用方
            保持 False（维持 None 降级契约，不得让异常穿到报告层）。

    Returns:
        函数返回值；每次均超时/异常时返回 None（``raise_on_failure=True`` 时上抛）
    """
    policy = RetryPolicy(attempts=1 + retries, strategy=STRATEGY_FIXED, base_backoff=1.0)

    def _attempt() -> Any:
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(fn)
            try:
                return fut.result(timeout=timeout)
            except BaseException:
                fut.cancel()
                raise
        finally:
            pool.shutdown(wait=False)

    def _on_retry(failed_attempt: int, _delay: float, exc: BaseException | None) -> None:
        if isinstance(exc, TimeoutError):
            logger.warning("akshare 调用超时 (%.1fs, 第 %d/%d 次)", timeout, failed_attempt, policy.attempts)
        else:
            logger.warning("akshare 调用异常 (第 %d/%d 次): %s", failed_attempt, policy.attempts, exc)

    try:
        return retry_transient(
            _attempt,
            policy=policy,
            retry_on=lambda _e: True,  # akshare 异常种类不可枚举：一律重试（与原行为一致）
            on_retry=_on_retry,
            sleep=time.sleep,
        )
    except BaseException:  # noqa: BLE001 — 默认吞异常返回 None（与原行为一致）
        if raise_on_failure:
            raise  # 链路消费方：只有异常才能被识别为传输级失败（同源重试 + 熔断计数）
        return None


def ts_to_str(ts: int) -> str:
    """将 Unix 时间戳（秒）转换为北京时间的格式化日期字符串。

    Args:
        ts: Unix 时间戳（秒）

    Returns:
        "YYYY-MM-DD HH:MM" 格式的字符串，转换失败返回 ""
    """
    try:
        bj_tz = BEIJING_TZ
        dt = datetime.fromtimestamp(ts, tz=bj_tz)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


def safe_float(s: Any) -> float:
    """安全地将输入转换为浮点数。

    转换失败返回 0.0。NaN/±inf 一并归一为 0.0——它们不抛异常、能一路
    穿透到市值/收益聚合链污染聚合结果，故必须在此显式拦下，而非依赖
    后续调用方逐处判空。

    Args:
        s: 输入值

    Returns:
        有限的 float，转换失败返回 0.0
    """
    result = safe_num(s, default=0.0)
    return float(result)  # type: ignore[arg-type]
