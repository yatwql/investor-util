"""LLM 端点级节流与并发治理 —— 单一事实来源。

**为什么需要端点级（而非全局）策略**：同一次报告生成的 LLM 调用会落在不同端点上，
而各端点背后的服务约束截然不同——

  - 订阅制编码端点（如 Kimi Code，``api.kimi.com/coding/``）：按会员额度计费，
    带 5 小时滚动窗口与「风险控制」型并发上限，既有条款要求**交互式**使用；
    批量调用应以低频次串行、固定间隔的方式发出，避免触发风控。
  - 按量付费端点（如开放平台 ``api.moonshot.cn/anthropic``）：有明确的分级
    RPM / TPM 与按量账单，可放心用较高并发。

**架构约束**：全局常量（如 ``llm_max_concurrency``）无法表达「同一程序、不同端点
不同策略」，故本模块把节流与并发**声明化**——由 ``llm_providers.json`` 的每个
provider 条目自带 ``pacing`` 段，缺省即表示「无额外约束」（行为与未引入本机制时
逐字节一致，满足「新增机制默认零影响」的既有纪律）。

配置形态（``llm_providers.json`` 的单个 provider 条目）::

    {
      "name": "kimi-code",
      "provider": "claude",
      "credentials_ref": "kimi-code",
      "priority": 10,
      "pacing": {
        "min_interval": 20,       // 同一端点上两次请求的最小间隔（秒）
        "jitter": 0.2,            // 间隔随机抖动比例（0~1），避免固定节奏的机器特征
        "max_concurrency": 1      // 该端点同时在途请求上限
      }
    }

字段全部可选：``pacing`` 缺失 / 为 null / 全零 ⇒ 该端点不受本机制约束。

线程安全：间隔控制复用 ``fetcher.batch.RateLimiter``（per-key 锁，不同端点互不阻塞）；
在途并发用 per-endpoint ``BoundedSemaphore``。
"""

from __future__ import annotations

import logging
import random
import threading
from typing import Any

logger = logging.getLogger("invest")

#: 端点标识 → PacingPolicy。以 provider name 为键（与 llm_providers.json 条目名对齐）。
_POLICIES: dict[str, "PacingPolicy"] = {}
_POLICY_LOCK = threading.Lock()
_LOADED = False


class PacingPolicy:
    """单个端点的节流与并发策略（不可变值对象）。"""

    __slots__ = ("min_interval", "jitter", "max_concurrency")

    def __init__(self, min_interval: float = 0.0, jitter: float = 0.0, max_concurrency: int = 0) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self.jitter = min(1.0, max(0.0, float(jitter)))
        self.max_concurrency = max(0, int(max_concurrency))

    @property
    def is_noop(self) -> bool:
        """无任何约束（默认态）——调用方据此走零开销路径。"""
        return self.min_interval <= 0 and self.max_concurrency <= 0

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        return (
            f"PacingPolicy(min_interval={self.min_interval}, jitter={self.jitter}, "
            f"max_concurrency={self.max_concurrency})"
        )


def parse_policy(raw: Any) -> PacingPolicy | None:
    """把配置段解析为策略；无效/缺失返回 None（表示「无约束」）。

    容错原则与其它配置项一致：字段类型错误**逐字段忽略**（记 WARNING），
    不因单个坏字段使整条 provider 校验失败——避免节流配置笔误导致端点不可用。
    """
    if not isinstance(raw, dict):
        return None
    try:
        min_interval = float(raw.get("min_interval") or 0)
    except (TypeError, ValueError):
        logger.warning("[llm/pacing] min_interval 非数值 %r，按 0 处理", raw.get("min_interval"))
        min_interval = 0.0
    try:
        jitter = float(raw.get("jitter") or 0)
    except (TypeError, ValueError):
        logger.warning("[llm/pacing] jitter 非数值 %r，按 0 处理", raw.get("jitter"))
        jitter = 0.0
    try:
        max_concurrency = int(raw.get("max_concurrency") or 0)
    except (TypeError, ValueError):
        logger.warning("[llm/pacing] max_concurrency 非整数 %r，按 0 处理", raw.get("max_concurrency"))
        max_concurrency = 0
    policy = PacingPolicy(min_interval=min_interval, jitter=jitter, max_concurrency=max_concurrency)
    return None if policy.is_noop else policy


def register_policies(providers: list[dict[str, Any]] | None) -> None:
    """由 provider 列表装载端点策略（幂等；同一进程内按需刷新）。

    在 ``_parse_providers_list`` 之后调用，使配置成为**唯一事实来源**。
    """
    global _LOADED
    parsed: dict[str, PacingPolicy] = {}
    for entry in providers or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        policy = parse_policy(entry.get("pacing"))
        if policy is not None:
            parsed[name] = policy
    with _POLICY_LOCK:
        _POLICIES.clear()
        _POLICIES.update(parsed)
        _LOADED = True
    if parsed:
        logger.info("[llm/pacing] 已装载端点节流策略: %s", {k: repr(v) for k, v in parsed.items()})


def _ensure_loaded() -> None:
    """惰性装载（供未显式调用 register_policies 的入口，如单测/脚本）。"""
    if _LOADED:
        return
    try:
        from src.python.config import get_llm_providers

        register_policies(get_llm_providers())
    except Exception as e:  # 配置层不可用不应影响调用主链路
        logger.debug("[llm/pacing] 策略惰性装载失败，按无约束处理: %s", e)


def get_policy(endpoint_key: str) -> PacingPolicy | None:
    """返回端点策略；无约束返回 None（调用方走零开销路径）。"""
    _ensure_loaded()
    return _POLICIES.get(endpoint_key)


def describe() -> dict[str, str]:
    """端点 → 策略的可读描述（供 ``doctor`` / 自检展示）。"""
    _ensure_loaded()
    return {k: repr(v) for k, v in _POLICIES.items()}


def reset_policies() -> None:
    """清空策略缓存（测试隔离用；生产不调用）。"""
    global _LOADED
    with _POLICY_LOCK:
        _POLICIES.clear()
        _LOADED = False


# ── 运行时执行器 ─────────────────────────────────────────────


class PacingGate:
    """把 ``PacingPolicy`` 施加到实际调用上的执行器（线程安全）。

    用法::

        with gate:
            resp = client.post(...)

    无约束时 ``__enter__`` 近乎零开销（仅一次 dict 查空）。
    """

    def __init__(self, endpoint_key: str) -> None:
        self._key = endpoint_key
        self._policy = get_policy(endpoint_key)
        self._sem: threading.BoundedSemaphore | None = None
        if self._policy is not None and self._policy.max_concurrency > 0:
            self._sem = _get_semaphore(endpoint_key, self._policy.max_concurrency)

    @property
    def is_noop(self) -> bool:
        return self._policy is None

    def __enter__(self) -> "PacingGate":
        if self._policy is None:
            return self
        if self._sem is not None:
            self._sem.acquire()
        # 间隔控制（含抖动）：在拿到并发许可之后执行，使间隔真正约束「请求发出」时刻
        if self._policy.min_interval > 0:
            _acquire_interval(self._key, self._policy)
        return self

    def __exit__(self, *exc: Any) -> bool:
        if self._sem is not None:
            self._sem.release()
        return False


# ── 内部：共享 RateLimiter / 信号量池 ────────────────────────

_LIMITER: Any = None
_LIMITER_LOCK = threading.Lock()
_SEMS: dict[str, threading.BoundedSemaphore] = {}


def _get_limiter() -> Any:
    """惰性构造共享 RateLimiter（复用 fetcher.batch 的既有实现，避免重复造）。"""
    global _LIMITER
    if _LIMITER is None:
        with _LIMITER_LOCK:
            if _LIMITER is None:
                from src.python.fetcher.batch import RateLimiter

                _LIMITER = RateLimiter()
    return _LIMITER


def _acquire_interval(endpoint_key: str, policy: PacingPolicy) -> None:
    """按策略等待到允许发请求的时刻（带抖动）。"""
    limiter = _get_limiter()
    if policy.jitter > 0:
        spread = policy.min_interval * policy.jitter
        limiter.acquire_interval(endpoint_key, policy.min_interval + random.uniform(0, spread))
    else:
        limiter.acquire_interval(endpoint_key, policy.min_interval)


def _get_semaphore(endpoint_key: str, limit: int) -> threading.BoundedSemaphore:
    with _LIMITER_LOCK:
        sem = _SEMS.get(endpoint_key)
        if sem is None:
            sem = threading.BoundedSemaphore(limit)
            _SEMS[endpoint_key] = sem
        return sem


#: 协议默认端点（``endpoint`` 未配置时按 provider 类型回落到官方默认）。
#: 用于把「运行时 URL」映射回配置里的 provider 名，从而取到其 pacing 策略。
_DEFAULT_ENDPOINTS: dict[str, str] = {
    "claude": "api.anthropic.com",
    "openai": "api.openai.com",
}


def endpoint_key_for(provider_name: str, endpoint: str | None, provider_type: str = "") -> str:
    """返回用于查策略的键——**provider 名**（配置里的条目名）。

    传 ``endpoint`` 仅用于日志与将来「按域名而非条目名」的扩展；当前策略以
    provider 条目名为准，保证与 ``llm_providers.json`` 一一对应、无歧义。
    """
    return provider_name or provider_type
