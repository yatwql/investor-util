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

线程安全：间隔控制复用 ``core.throttle.RateLimiter``（per-key 锁，不同端点互不阻塞）；
在途并发用 per-endpoint ``BoundedSemaphore``。
"""

from __future__ import annotations

import logging
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
    """惰性装载（供未显式调用 register_policies 的入口，如单测/脚本）。

    策略与 ``_provider_list`` 同源：生产路径在 ``get_llm_config`` 组装时已调用
    :func:`register_policies`，此处只兑底未经过配置加载的入口，故直接读同一份
    ``_provider_list``（引用不存在的访问器会 ImportError → 静默按无约束处理）。
    """
    if _LOADED:
        return
    try:
        from src.python.config import get_llm_config

        register_policies((get_llm_config() or {}).get("_provider_list"))
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
    """惰性构造共享 RateLimiter（唯一实现见 core/throttle.py，此处只做单例缓存）。"""
    global _LIMITER
    if _LIMITER is None:
        with _LIMITER_LOCK:
            if _LIMITER is None:
                from src.python.core.throttle import RateLimiter

                _LIMITER = RateLimiter()
    return _LIMITER


def _acquire_interval(endpoint_key: str, policy: PacingPolicy) -> None:
    """按策略等待到允许发请求的时刻（间隔 + 抖动算式由 core.throttle 统一提供）。"""
    _get_limiter().acquire_interval(endpoint_key, policy.min_interval, jitter_ratio=policy.jitter)


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


# ── 429 诊断：两级并发配置回显与生效并发建议（供 api_base 重试骨架调用） ──


def _concurrency_hint(endpoint_key: str = "") -> str:
    """429 诊断：回显当前两级并发配置，并按「生效并发还有没有下降空间」给可执行建议。

    判定基准是**生效并发 = min(全局 llm_max_concurrency, 端点 pacing.max_concurrency)**
    （端点未配置时即全局值）——只有绑定项（等于生效并发的那一级）调低才立即使该端点
    在途并发下降：端点已配到 1 时生效并发恒为 1，再建议「调低全局」永远不会有效果
    （对端点=1/全局=3 的实测场景，这类空话会让诊断日志失信），此时除回显外只推
    ``pacing.min_interval``（改请求速率）与配额/风控判断；生效并发 ≥ 2 时只列绑定项，
    非绑定项注明「须低于对方现值才生效」，避免叫人调一个不咬合的旋钮。

    Args:
        endpoint_key: provider 条目名（端点策略键）；空串表示本次调用未绑定条目。

    Returns:
        拼接好的日志片段（配置回显 + 建议）；读取配置失败时回退为默认文案。
    """
    try:
        from src.python.config import get_llm_config

        global_limit = int((get_llm_config() or {}).get("llm_max_concurrency", 3))
    except Exception:  # 配置层不可用不应阻断诊断日志
        global_limit = 3

    endpoint_limit = 0
    min_interval = 0.0
    policy = None
    if endpoint_key:
        try:
            policy = get_policy(endpoint_key)
            if policy is not None:
                endpoint_limit = policy.max_concurrency
                min_interval = policy.min_interval
        except Exception:  # 策略装载失败按「无约束」提示，不影响重试链路
            endpoint_limit = 0

    if endpoint_limit > 0:
        endpoint_text = str(endpoint_limit)
    else:
        endpoint_text = "未配置（不限流）"
    interval_text = f"{min_interval:g}s" if policy is not None else "未配置"
    shown = f"当前配置：全局 llm_max_concurrency={global_limit}"
    if endpoint_key:
        shown += (
            f"；provider[{endpoint_key}] pacing.max_concurrency={endpoint_text}、pacing.min_interval={interval_text}"
        )

    # 生效并发：该端点实际可能的在途并发上限 = min(全局, 端点)；端点未配置时即全局值。
    # 建议只针对绑定项——非绑定项调低不改变 min()，端点已到底时调低全局更是恒无效。
    effective = min(global_limit, endpoint_limit) if endpoint_limit > 0 else global_limit

    if effective > 1:
        if endpoint_limit <= 0:
            advice = "建议调低 llm_max_concurrency（当前并发可能过高），或为该 provider 条目配置 pacing.max_concurrency 按端点限流"
        elif endpoint_limit == global_limit:
            advice = (
                f"建议调低 provider[{endpoint_key}] 的 pacing.max_concurrency（当前 {endpoint_limit}，最低 1）"
                f"或全局 llm_max_concurrency（当前 {global_limit}）——两级相等均为绑定项，调低任一生效并发即降"
            )
        elif endpoint_limit < global_limit:
            advice = (
                f"建议调低 provider[{endpoint_key}] 的 pacing.max_concurrency（当前 {endpoint_limit}，最低 1）"
                f"——生效并发 = min(全局, 端点) = {effective} 由端点绑定，调低全局（当前 {global_limit}）须低于端点值才生效"
            )
        else:  # global_limit < endpoint_limit：全局绑定
            advice = (
                f"建议调低全局 llm_max_concurrency（当前 {global_limit}）"
                f"——生效并发 = min(全局, 端点) = {effective} 由全局绑定，调低端点（当前 {endpoint_limit}）须低于全局值才生效"
            )
    elif endpoint_limit > 0 and global_limit > 1:
        # 端点=1 绑定：生效并发恒为 1，调低全局对「该端点」的在途并发毫无影响——
        # 不再给无效建议，改推请求速率（min_interval）与配额/风控判断。
        advice = (
            f"该端点 pacing.max_concurrency 已为最低 1、无可再降；生效并发 = min(全局, 端点) = 1，"
            f"调低全局（当前 {global_limit}）不减少该端点在途并发、再调低并发已无益——"
            f"429 更可能来自请求速率或配额（RPM/TPM）/风控：建议加大 pacing.min_interval（当前 {min_interval:g}s），"
            "或切换 provider（退避重试会自动生效）"
        )
    elif endpoint_limit > 0:
        advice = (
            f"生效并发已压至下限（全局 {global_limit} / 端点 {endpoint_limit}），再调低并发已无益——"
            f"429 更可能来自配额（RPM/TPM）或风控而非并发：建议加大 pacing.min_interval（当前 {min_interval:g}s），"
            "或切换 provider（退避重试会自动生效）"
        )
    else:
        advice = (
            f"全局 llm_max_concurrency 已为下限（当前 {global_limit}）、该端点未配置 pacing，再调低并发已无益——"
            "429 更可能来自配额（RPM/TPM）或风控：建议为该 provider 条目配置 pacing.min_interval 加大请求间隔，"
            "或切换 provider（退避重试会自动生效）"
        )
    return f"{shown}；{advice}"
