"""Provider Chain 通用 Fallback 路由执行（对外门面）。

每类数据（price/index/rank/holding）对应一个 Provider Chain，chain 中按优先级列出 provider，
主链路失败后自动递补；传输级瞬时失败先同源重试一次再落槽。

职责拆分（本文件只保留「路由执行」，其余职责下沉子模块并经本模块 re-export 对外，
既有 ``from ...fetcher.chain import X`` 调用方零改动）：

  - 链定义与覆盖、链健康判定 → ``fetcher/chain_config.py``
  - 失败诊断与命中归属登记   → ``fetcher/chain_diagnostics.py``
  - 历史序列增量合并         → ``fetcher/chain_incremental.py``
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from src.python.cache import clear as cache_clear
from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.core.constants import CACHE_WEEKLY
from src.python.core.datasource_credential import (
    credential_hint,
    credential_ready_enabled,
    missing_credential,
)
from src.python.core.provider_registry import TRANSPORT_FAILURE, get_registry
from src.python.core.retry import STRATEGY_EXPONENTIAL, RetryPolicy, retry_transient
from src.python.fetcher.chain_config import (
    _DEFAULT_CHAINS,
    _get_chain,
    chain_overrides,
    is_provider_chain_broken,
    known_provider_names,
    reset_chain_overrides,
    reset_provider_skip,
)
from src.python.fetcher.chain_diagnostics import FailureDiagnostics, _brief_reason, _mark_provider_used
from src.python.fetcher.chain_incremental import (
    _CACHE_PAYLOAD_FIELD,
    _HISTORY_PROVIDER_MAP,
    _call_history_provider,
    _try_providers,
    fetch_with_incremental_fallback,
    payload_version_current,
    write_stale_with_version,
)


# ── 传输级瞬时失败的同源重试 ────────────────────────────────
# 仅对**传输级**失败（超时/断连/远端断开/5xx）重试：这类错误多为瞬时抖动，
# 同源重试一次往往即成功，可避免过早落到下一槽或触发熔断（行业分类 push2
# 的 `Server disconnected` 与 DataSinking 的偶发断连即属此类）。代码级空结果
# （API 不识别该代码）不重试——同一请求会得到同一答案，且会白耗配额
# （DataSinking 免费档日配额仅 8191 篇）。
_TRANSIENT_RETRY_ATTEMPTS = 1  # 同源额外重试次数
_TRANSIENT_RETRY_BACKOFF = 0.6  # 首次重试基础退避（秒），指数增长 + 抖动


logger = logging.getLogger("invest")

_ProviderFunc = Callable[..., dict[str, Any] | None]


def _try_provider_fetch(
    data_type: str,
    provider_name: str,
    source_label: str,
    fetch_fn: _ProviderFunc,
    kwargs: dict,
    validate: Callable[[dict[str, Any], str], bool] | None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None]
    | dict[str, Callable[[dict[str, Any], str], dict[str, Any] | None]]
    | None,
) -> tuple[dict[str, Any] | None, str]:
    """尝试调用单个 provider 的 fetch 函数。

    Returns:
        ``(结果, 失败原因)``。成功时原因为空串；失败时结果为 ``None`` 或
        ``TRANSPORT_FAILURE``，原因是一行可读短句（供诊断上屏，不再只进日志）。
    """
    _code_tag = f" [{kwargs.get('code', '')}]" if kwargs.get("code") else ""
    # 尝试前先清「失败原因」载体：该载体只在 provider 返回 None 时被消费，若上一次
    # 调用的原因未经消费就残留（直连调用/缓存命中直接返回），会把「上一条命令的失败
    # 原因」串到本次诊断上。先清后调即保证本次读到的只可能是本次 provider 写的。
    from src.python.providers._utils import clear_last_reason as _clear_reason

    _clear_reason()
    try:
        raw = fetch_fn(**kwargs)
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str or "rate" in err_str.lower():
            logger.warning("[%s]%s %s API 限速(429): %s", data_type, _code_tag, provider_name, err_str)
            reason = "API 限速(429)"
        else:
            logger.warning("[%s]%s %s 调用异常: %s", data_type, _code_tag, provider_name, err_str)
            reason = _brief_reason(f"{type(e).__name__}: {err_str}")
        # 传输级异常 → 应计入熔断
        return cast("dict[str, Any] | None", TRANSPORT_FAILURE), reason

    if raw is None:
        # provider 可把「为什么空」写在 _utils 的 last-reason 里（如「该文档无目标章节」）；
        # 取到就用它替换笼统的「返回空」——「源故障」与「该文档确实没这一节」在运维上
        # 是完全不同的信号（前者要排查网络/凭据）。
        from src.python.providers._utils import take_last_reason

        reason = take_last_reason("返回空")
        logger.info("[%s]%s %s 返回空（%s），尝试下一链路", data_type, _code_tag, provider_name, reason)
        return None, reason

    # 数据验证
    if validate:
        try:
            if not validate(raw, provider_name):
                logger.info("[%s]%s %s 数据验证未通过，尝试下一链路", data_type, _code_tag, provider_name)
                return None, "数据校验未通过"
        except Exception as e:
            logger.warning("[%s]%s %s 数据验证异常: %s", data_type, _code_tag, provider_name, e)
            return None, _brief_reason(f"数据校验异常: {e}")

    # 应用数据转换
    try:
        if isinstance(transform, dict):
            fn = transform.get(provider_name)
            result = fn(raw, source_label) if fn else raw
        elif transform:
            result = transform(raw, source_label)
        else:
            result = raw
    except Exception as e:
        logger.warning("[%s] %s 数据转换失败: %s", data_type, provider_name, e)
        return None, _brief_reason(f"数据转换失败: {e}")

    if result is not None:
        logger.info("[%s]%s %s 成功", data_type, _code_tag, provider_name)
    return result, ""


def fetch_with_fallback(
    data_type: str,
    provider_fn_map: dict[str, tuple[str, _ProviderFunc]],
    cache_key: str,
    cache_ttl: float,
    fn_kwargs: dict[str, Any] | None = None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None]
    | dict[str, Callable[[dict[str, Any], str], dict[str, Any] | None]]
    | None = None,
    validate: Callable[[dict[str, Any], str], bool] | None = None,
    diagnostics: FailureDiagnostics | None = None,
    cache_validate: Callable[[Any], bool] | None = None,
) -> dict[str, Any] | None:
    """通用 Fallback 获取器。

    对于指定数据类型，依次尝试 chain 中的每个 provider，
    第一个成功的返回结果，全部失败返回 None。

    熔断逻辑委托 DataSourceRegistry 统一管理。

    Args:
        diagnostics: 可选的失败原因收集器。传入时逐 provider 记录可读失败原因，
            供调用方写入降级事件（「错误即 UX」）；不传则零采集、零开销。
        cache_validate: 可选的缓存载荷准入判据。缓存条目（含过期降级条目）
            未通过判据时视为未命中、丢弃重取。用于「载荷语义已变更」的修复：
            旧条目结构未变但含义已变，仅靠 TTL 会在过期前持续遮蔽修复。
    """
    chain = _get_chain(data_type)
    kwargs = fn_kwargs or {}
    _code_tag = f" [{kwargs.get('code', '')}]" if kwargs.get("code") else ""

    # 1) 读缓存（准入判据不符 → 丢弃重取，避免旧语义载荷遮蔽修复）
    cached = cache_get(cache_key, cache_ttl)
    if cached is not None:
        if cache_validate is None or cache_validate(cached):
            return cached
        logger.info("[%s]%s 缓存载荷语义版本过期，丢弃并重取", data_type, _code_tag)
        cache_clear(cache_key)

    # 2) 遍历 chain 尝试（熔断委托 registry）
    reg = get_registry()
    for provider_name in chain:
        entry = provider_fn_map.get(provider_name)
        # 展示名优先（用户看得懂「腾讯财经」而非 "tencent"）
        label = entry[0] if entry else provider_name

        # 熔断检查（含自动冷却恢复）
        if reg.is_circuit_broken(provider_name):
            logger.debug("[%s]%s %s 已被熔断，跳过", data_type, _code_tag, provider_name)
            if diagnostics is not None:
                diagnostics.add(label, "已被熔断跳过")
            continue

        if not entry:
            logger.warning("[%s]%s 未知 Provider '%s'，跳过", data_type, _code_tag, provider_name)
            if diagnostics is not None:
                diagnostics.add(label, "未注册")
            continue

        # 凭据就绪预检（开关 datasource_credential_ready）：
        # 配置级问题（用户没配 key），**不计入熔断计数器**——混入可用性统计
        # 会污染数据源可用性矩阵的语义；仅以可读原因进入「错误即 UX」通道。
        # 开关关闭 / 无声明凭据 → 该分支恒不触发，行为与未引入本机制时逐字一致。
        _spec = missing_credential(provider_name) if credential_ready_enabled() else None
        if _spec is not None:
            logger.info("[%s]%s %s 缺少凭据，跳过（%s）", data_type, _code_tag, label, _spec.env_var)
            if diagnostics is not None:
                diagnostics.add(label, credential_hint(_spec))
            continue

        source_label, fetch_fn = entry
        logger.info("[%s]%s 尝试 %s (%s)", data_type, _code_tag, source_label, provider_name)

        if fetch_fn is None:
            logger.warning("[%s] %s 没有注册的 fetch 函数", data_type, provider_name)
            if diagnostics is not None:
                diagnostics.add(source_label or provider_name, "无 fetch 函数")
            continue

        reason_box: dict[str, str] = {"reason": ""}

        def _attempt() -> Any:
            result, reason_box["reason"] = _try_provider_fetch(
                data_type, provider_name, source_label, fetch_fn, kwargs, validate, transform
            )
            return result

        def _on_transient_retry(failed_attempt: int, delay: float, _exc: BaseException | None) -> None:
            logger.info(
                "[%s]%s %s 传输级失败（%s），%.1fs 后同源重试 %d/%d",
                data_type,
                _code_tag,
                source_label,
                reason_box["reason"],
                delay,
                failed_attempt,
                _TRANSIENT_RETRY_ATTEMPTS,
            )

        # 传输级瞬时失败 → 同源退避重试（仍失败才落下一槽）；退避算式与次数由 core/retry 统一
        result = retry_transient(
            _attempt,
            policy=RetryPolicy(
                attempts=1 + _TRANSIENT_RETRY_ATTEMPTS,
                strategy=STRATEGY_EXPONENTIAL,
                base_backoff=_TRANSIENT_RETRY_BACKOFF,
                factor=2.0,
                jitter=0.2,
            ),
            retry_if_result=lambda r: r is TRANSPORT_FAILURE,
            on_retry=_on_transient_retry,
        )
        reason = reason_box["reason"]

        if result is not None and result is not TRANSPORT_FAILURE:
            # 成功 → 恢复熔断计数器 + 登记 provider 级归属（矩阵「命中源」列的数据来源）
            reg.record_success(provider_name)
            _mark_provider_used(data_type, provider_name, source_label)
            cache_set(cache_key, result)
            return result

        if diagnostics is not None:
            diagnostics.add(source_label or provider_name, reason or "无结果")

        if result is TRANSPORT_FAILURE:
            # 传输级异常（超时/断连/DNS/5xx）→ 累计连续失败计数
            # 原因带上可读短句，让 DataSourceRegistry.last_failure_context 首次有实义
            reg.record_failure(provider_name, f"{data_type}: {reason}")
            if reg.is_circuit_broken(provider_name):
                logger.warning("[%s]%s %s 连续失败，本会话后续请求跳过", data_type, _code_tag, provider_name)
        # else: 代码级空结果（API 不识别该代码）→ 不计入熔断计数器

    # 3) 降级：全部 Provider 失败时尝试过期缓存（同样须过准入判据）
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None and (cache_validate is None or cache_validate(stale)):
        logger.info("[%s]%s 全部 Provider 不可用，降级使用过期缓存", data_type, _code_tag)
        return stale

    logger.warning("[%s]%s 全链路失败（无过期缓存可用），数据不可用", data_type, _code_tag)
    return None


# ── 对外门面：链定义 / 诊断 / 增量合并三子模块的符号经此 re-export ──
__all__ = [
    # 路由执行（本模块）
    "FailureDiagnostics",
    "fetch_with_fallback",
    # 链定义与覆盖（chain_config）
    "_DEFAULT_CHAINS",
    "_get_chain",
    "chain_overrides",
    "is_provider_chain_broken",
    "known_provider_names",
    "reset_chain_overrides",
    "reset_provider_skip",
    # 增量合并（chain_incremental）
    "_CACHE_PAYLOAD_FIELD",
    "_HISTORY_PROVIDER_MAP",
    "_call_history_provider",
    "_try_providers",
    "fetch_with_incremental_fallback",
    "payload_version_current",
    "write_stale_with_version",
]
