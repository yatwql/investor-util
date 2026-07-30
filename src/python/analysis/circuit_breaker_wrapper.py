"""指标级断路包装器 — 为每个风险指标计算函数包裹断路逻辑。

设计目标：
  单个指标连续失败 N 次后静默 24h，不阻塞其他指标计算，
  避免一次波动性失败污染全管线。

与 provider_registry 的边界：
  provider_registry（传输层熔断）：
    管 HTTP 层面的快速跳过（超时/断连/5xx），per-provider 粒度。
  IndicatorBreaker（指标层断路）：
    管指标计算层面的异常（除零/空数据/置信度不足），per-indicator 粒度。
    不关心底层是哪个数据源——只关心指标算不算得出来。

C20 联动（Feature Flag ↔ Circuit Breaker）：
  - Feature Flag 关闭期间不计断路失败次数
  - Feature Flag 打开时自动重置断路器状态
  - Feature Flag 变更事件记录到 DegradationTracker
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

__all__ = [
    "IndicatorBreaker",
    "get_indicator_breaker",
    "reset_indicator_breaker",
]

# ── 常量 ────────────────────────────────────────────────

_METRICS_BREAKER_FILE = os.path.join(PROJECT_ROOT, "data/cache/metrics_breaker.json")
"""指标断路状态持久化文件路径。"""

_DEFAULT_MAX_FAILURES = 3
"""单个指标连续失败多少次后触发断路。"""

_DEFAULT_COOLDOWN_SECS = 86400
"""断路后冷却时间（秒，默认 24h）。"""

_CIRCUIT_BREAKER_TTL = 86400 * 7
"""持久化记录的超时 TTL（秒，默认 7 天），超过此时间的条目在加载时自动清理。"""


class IndicatorBreaker:
    """指标级断路器 — 为单个指标计算函数提供断路保护。

    用法：
        breaker = IndicatorBreaker()
        result = breaker.guard("sharpe_ratio", compute_fn, *args, **kwargs)

    或者显式调用：
        if breaker.is_broken("sharpe_ratio"):
            return None
        try:
            result = compute_fn(...)
            breaker.record_success("sharpe_ratio")
            return result
        except Exception:
            breaker.record_failure("sharpe_ratio")
            return None
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._persist_path = persist_path or _METRICS_BREAKER_FILE
        # {indicator_name: {"consecutive_failures": int, "broken_until": float, ...}}
        self._state: dict[str, dict[str, Any]] = {}
        self._load_state()

    # ── 持久化 ──────────────────────────────────────

    def _state_path(self) -> str:
        return self._persist_path

    def _load_state(self) -> None:
        """从 JSON 加载持久化的断路状态，超过 TTL 的条目自动清理。"""
        path = self._state_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.debug("[breaker] 状态文件损坏，跳过加载")
            return

        now = time.time()
        loaded = 0
        expired = 0
        for name, st in data.items():
            saved_at = st.get("_saved_at", 0)
            if now - saved_at > _CIRCUIT_BREAKER_TTL:
                expired += 1
                continue
            self._state[name] = st
            loaded += 1
        if loaded:
            logger.debug("[breaker] 已加载 %d 个指标断路状态（%d 条已过期）", loaded, expired)

    def _save_state(self) -> None:
        """持久化当前断路状态到 JSON。"""
        path = self._state_path()
        now = time.time()
        # 清理过期条目，并添加时间戳
        clean: dict[str, dict[str, Any]] = {}
        for name, st in self._state.items():
            saved_at = st.get("_saved_at", 0)
            if now - saved_at > _CIRCUIT_BREAKER_TTL:
                continue
            st["_saved_at"] = now
            clean[name] = st
        self._state = clean
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("[breaker] 持久化失败: %s", e)

    # ── 断路判定 ────────────────────────────────────

    def is_broken(self, indicator_name: str) -> bool:
        """检查指定指标是否处于断路状态。

        冷却期满时自动解除断路（返回 False 并允许一次试探）。
        """
        st = self._state.get(indicator_name)
        if st is None:
            return False
        broken_until = st.get("broken_until", 0)
        if time.time() >= broken_until:
            # 冷却期满 → 解除断路
            if st.get("is_broken", False):
                logger.info("[breaker] %s 冷却期满，解除断路", indicator_name)
            self._state.pop(indicator_name, None)
            self._save_state()
            return False
        return st.get("is_broken", False)

    def _check_feature_flag(self, indicator_name: str) -> bool:
        """检查 Feature Flag 状态，联动断路器。

        C20 联动：
          - Feature Flag 关闭期间不计断路失败次数
          - Feature Flag 打开时自动重置断路器状态
          - Feature Flag 变更事件记录到 DegradationTracker
        """
        from src.python.config.features import FEATURE_FLAGS, is_feature_enabled

        # 映射指标名称到 Feature Flag 名称
        flag_map: dict[str, str] = {
            "sharpe_ratio": "metrics_sharpe",
            "calmar_ratio": "metrics_calmar",
            "hhi": "metrics_hhi",
            "win_rate": "metrics_winrate",
            "turnover_rate": "metrics_turnover",
            "risk_contribution": "metrics_risk_contribution",
            "beta": "metrics_beta",
        }
        flag_name = flag_map.get(indicator_name)
        if flag_name is None:
            return True  # 没有对应 Feature Flag 的指标默认可用

        if not is_feature_enabled(flag_name):
            # C20(a): Feature Flag 关闭期间不计断路失败次数
            st = self._state.get(indicator_name)
            if st and st.get("is_broken", False):
                # 若已经断路，但 FF 关闭，自动解除断路（不计为失败）
                self._state.pop(indicator_name, None)
                self._save_state()
                # C20(c): 记录到 DegradationTracker
                self._log_ff_event(indicator_name, flag_name, False)

            # 从 FEATURE_FLAGS 检查是否发生了状态变化
            return False

        # C20(b): Feature Flag 从 false 切换到 true 时，重置断路器
        # 从元数据检查：之前的状态是 false
        last_ff_state = FEATURE_FLAGS.get(flag_name, True)
        if last_ff_state:  # 当前是 true
            st = self._state.get(indicator_name)
            if st and st.get("_ff_was_off", False):
                # 之前 FF 关闭过，现在打开了 → 清空历史失败
                self._state.pop(indicator_name, None)
                self._save_state()
                # C20(c): 记录到 DegradationTracker
                self._log_ff_event(indicator_name, flag_name, True)

        return True

    @staticmethod
    def _log_ff_event(indicator_name: str, flag_name: str, now_enabled: bool) -> None:
        """C20(c): Feature Flag 变更事件记录到 DegradationTracker。"""
        try:
            from src.python.report.data_status import get_tracker

            tracker = get_tracker()
            tracker.record(
                source_key=f"ff_{indicator_name}",
                tier="T3",
                success=True,
                failure_type="unreachable",
            )
            logger.info(
                "[breaker] C20 %s: Feature Flag %s → %s",
                indicator_name,
                flag_name,
                "启用" if now_enabled else "关闭",
            )
        except Exception:
            logger.debug(
                "[breaker] DegradationTracker 不可用，跳过 Feature Flag 记录", exc_info=True
            )  # DegradationTracker 不可用时不阻塞

    # ── 记录成功/失败 ────────────────────────────────

    def record_success(self, indicator_name: str) -> None:
        """记录一次指标计算成功，重置该指标的所有计数。"""
        old = self._state.pop(indicator_name, None)
        if old is not None:
            logger.debug("[breaker] %s 计算成功，重置断路状态", indicator_name)
            self._save_state()

    def record_failure(self, indicator_name: str, context: str = "") -> None:
        """记录一次指标计算失败，达到阈值时触发断路。

        feature_flag 关闭时不计失败次数（C20-a）。
        """
        # 先检查 Feature Flag
        from src.python.config.features import is_feature_enabled

        flag_map: dict[str, str] = {
            "sharpe_ratio": "metrics_sharpe",
            "calmar_ratio": "metrics_calmar",
            "hhi": "metrics_hhi",
            "win_rate": "metrics_winrate",
            "turnover_rate": "metrics_turnover",
            "risk_contribution": "metrics_risk_contribution",
            "beta": "metrics_beta",
        }
        flag_name = flag_map.get(indicator_name)
        if flag_name and not is_feature_enabled(flag_name):
            # C20(a): FF 关闭，不计失败
            logger.debug("[breaker] %s FF 关闭（%s），不计失败", indicator_name, flag_name)
            return

        st = self._state.setdefault(
            indicator_name,
            {
                "consecutive_failures": 0,
                "is_broken": False,
                "broken_until": 0,
                "last_context": "",
                "_saved_at": time.time(),
            },
        )

        st["consecutive_failures"] = st.get("consecutive_failures", 0) + 1
        st["last_context"] = context

        if st["consecutive_failures"] >= _DEFAULT_MAX_FAILURES and not st.get("is_broken", False):
            st["is_broken"] = True
            st["broken_until"] = time.time() + _DEFAULT_COOLDOWN_SECS
            logger.warning(
                "[breaker] %s 连续 %d 次失败（最新: %s），断路 %ds（~24h）",
                indicator_name,
                st["consecutive_failures"],
                context or "未知错误",
                _DEFAULT_COOLDOWN_SECS,
            )
            # 记录到 DegradationTracker
            try:
                from src.python.report.data_status import get_tracker

                tracker = get_tracker()
                tracker.record(
                    source_key=f"breaker_{indicator_name}",
                    tier="T2",
                    success=False,
                    failure_type="unreachable",
                )
            except Exception:
                logger.debug("[breaker] DegradationTracker 不可用，跳过失败记录", exc_info=True)

        self._save_state()

    def get_breaker_status(self, indicator_name: str) -> dict[str, Any]:
        """查询指定指标的断路状态。"""
        st = self._state.get(indicator_name, {})
        is_broken = self.is_broken(indicator_name)
        if not is_broken:
            return {"indicator": indicator_name, "circuit_broken": False, "consecutive_failures": 0}
        return {
            "indicator": indicator_name,
            "circuit_broken": True,
            "consecutive_failures": st.get("consecutive_failures", 0),
            "cooldown_remaining": round(max(0, st.get("broken_until", 0) - time.time()), 1),
            "last_context": st.get("last_context", ""),
        }

    def summary(self) -> dict[str, dict[str, Any]]:
        """返回所有指标的断路状态摘要。"""
        result: dict[str, dict[str, Any]] = {}
        for name in list(self._state.keys()):
            result[name] = self.get_breaker_status(name)
        return result

    def guard(
        self,
        indicator_name: str,
        compute_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """包裹执行：先查断路 → 查 Feature Flag → 执行 → 记录结果。

        Args:
            indicator_name: 指标名称（用于断路状态跟踪）
            compute_fn: 指标计算函数
            *args, **kwargs: 传给 compute_fn 的参数

        Returns:
            compute_fn 的返回值，或 None（断路/FF 关闭/异常）
        """
        # 1. 检查 Feature Flag
        if not self._check_feature_flag(indicator_name):
            logger.debug("[breaker] %s Feature Flag 关闭，跳过", indicator_name)
            return None

        # 2. 检查断路状态
        if self.is_broken(indicator_name):
            logger.debug("[breaker] %s 断路中，跳过计算", indicator_name)
            return None

        # 3. 执行计算
        try:
            result = compute_fn(*args, **kwargs)
            self.record_success(indicator_name)
            return result
        except Exception as e:
            context = f"{type(e).__name__}: {e}"
            self.record_failure(indicator_name, context)
            return None

    def reset(self) -> None:
        """清空全部断路状态（测试用）。"""
        self._state.clear()
        if os.path.exists(self._state_path()):
            try:
                os.remove(self._state_path())
            except OSError:
                pass


# ── 单例工厂 ────────────────────────────────────────────

_breaker_instance: IndicatorBreaker | None = None
_breaker_instance_lock = __import__("threading").Lock()


def get_indicator_breaker() -> IndicatorBreaker:
    """获取全局单例。"""
    global _breaker_instance
    if _breaker_instance is None:
        with _breaker_instance_lock:
            if _breaker_instance is None:
                _breaker_instance = IndicatorBreaker()
    return _breaker_instance


def reset_indicator_breaker() -> None:
    """重置单例（测试用）。"""
    global _breaker_instance
    with _breaker_instance_lock:
        if _breaker_instance is not None:
            _breaker_instance.reset()
        _breaker_instance = None
