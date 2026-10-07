"""链路失败诊断与命中归属登记 —— `FailureDiagnostics` 失败载荷、原因短句截断、provider 归属观测。

供 ``fetcher/chain.py``（fallback 路由执行）与 ``fetcher/chain_incremental.py``（历史增量合并）
共用：链路失败时把「哪个 provider、为什么失败」沉淀为可读短句供降级事件上屏；命中归属经
延迟导入 ``report.data_status`` 登记，链路层不依赖报告层观测设施。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


logger = logging.getLogger("invest")


# ── 通用带缓存的 Fallback 调用 ──────────────────────────────

# 失败原因短句截断长度（诊断可读性优先，不追求完整 traceback）
_REASON_MAX_LEN = 60


def _brief_reason(text: str) -> str:
    """把异常信息压成一行短原因（诊断展示用）。"""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= _REASON_MAX_LEN else flat[: _REASON_MAX_LEN - 1] + "…"


@dataclass
class FailureDiagnostics:
    """单次链路调用的失败原因收集器（「错误即 UX」）。

    链路失败时，调用方拿到的只有 ``None``／``[]``，失败原因此前只存在于
    logger 输出里、用户可见面见不到。本对象把「哪个 provider、为什么失败」
    沉淀为可读短句，供调用方写入降级事件、由报告的数据源可用性矩阵上屏。

    可选出参：不传时链路零采集、零开销（保持既有行为逐字不变）。
    """

    attempts: list[tuple[str, str]] = field(default_factory=list)

    def add(self, provider: str, reason: str) -> None:
        """记录一次 provider 失败（provider 为展示名，reason 为可读短句）。"""
        self.attempts.append((provider, reason))

    @property
    def has_failure(self) -> bool:
        return bool(self.attempts)

    def summary(self) -> str:
        """人类可读的失败原因汇总，如 ``腾讯财经(连接超时)；新浪财经(返回空)``。"""
        return "；".join(f"{name}({reason})" for name, reason in self.attempts)


def _mark_provider_used(data_type: str, provider_name: str, display_name: str) -> None:
    """登记「本次该数据类别由此 provider 服务」（矩阵「命中源」列的归属来源）。

    延迟导入 ``report.data_status``：链路层不依赖报告层观测设施（避免模块级循环），
    观测失败也不得影响取数。
    """
    try:
        from src.python.report.data_status import mark_provider_used

        mark_provider_used(data_type, provider_name, display_name)
    except Exception:  # 观测失败不影响主链路
        logger.debug("[chain] provider 归属登记失败（非关键）: %s/%s", data_type, provider_name, exc_info=True)
