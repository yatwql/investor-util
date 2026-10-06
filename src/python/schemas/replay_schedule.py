"""回放规则契约（replay_schedule）——调仓纪律回放的规则解析与校验。

契约要点（设计 docs/plan/rebalance-schedule-replay-design.md）：
  - 纯校验零 I/O：cadence（定期）/ threshold（阈值）/ 目标权重语义在此唯一定义；
  - 版本化（``version``）：规则语义变更时旧序列按未命中丢弃，不静默沿用旧回放；
  - 非法输入一律 ``ValueError``（中文可读消息），未知键拒绝（防拼写静默失效）。

目标权重语义：
  - ``target_weights=None`` → 回放入口按「当前持仓归一（窗口末日市值）」取默认目标；
  - 显式给定时必须逐项 ≥0、有限、总和为 1（容差 1e-6），缺失的在持仓品种按 0
    （清仓该品种）解释——目标权重是一份完整配置。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

#: 契约版本：规则语义变更（触发口径/单位/目标定义）时 +1，旧序列按未命中丢弃
SCHEDULE_VERSION = 1
RULE_TYPES = frozenset({"cadence", "threshold"})
CADENCES = frozenset({"monthly", "quarterly"})
#: 阈值单位：百分点（5.0 = 偏离 5pp）；上下限防手滑（0pp 必触、>50pp 无意义）
MIN_THRESHOLD_PP = 0.0  # 开区间下界
MAX_THRESHOLD_PP = 50.0  # 闭区间上界
_WEIGHT_SUM_TOL = 1e-6
_KNOWN_KEYS = frozenset({"rule_type", "cadence", "threshold_pp", "target_weights", "version"})


@dataclass(frozen=True)
class ReplaySchedule:
    """已校验的回放规则（不可变）。

    Attributes:
        rule_type: ``cadence``（定期触发）或 ``threshold``（偏离阈值触发）。
        cadence: 定期档位 ``monthly``/``quarterly``；threshold 规则下仅存默认值不参与触发。
        threshold_pp: 阈值规则的偏离阈值（百分点，如 5.0）；cadence 规则下为 None。
        target_weights: 用户指定目标权重 {code: w}；None = 窗口末日持仓归一（回放入口解析）。
        version: 契约版本（见 ``SCHEDULE_VERSION``）。
    """

    rule_type: str
    cadence: str
    threshold_pp: float | None
    target_weights: dict[str, float] | None
    version: int

    @property
    def threshold(self) -> float | None:
        """阈值规则的偏离阈值（小数，如 0.05）；cadence 规则返回 None。"""
        if self.threshold_pp is None:
            return None
        return self.threshold_pp / 100.0


def _fail(msg: str) -> ValueError:
    return ValueError(f"回放规则非法：{msg}")


def _validate_target_weights(raw: Any) -> dict[str, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise _fail(f"target_weights 须为映射（{{代码: 权重}}），实际 {type(raw).__name__}")
    weights: dict[str, float] = {}
    for key, value in raw.items():
        code = str(key).strip()
        if not code:
            raise _fail("target_weights 存在空代码键")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _fail(f"target_weights[{code}] 须为数值，实际 {type(value).__name__}")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise _fail(f"target_weights[{code}] 须为有限非负数，实际 {value!r}")
        weights[code] = number
    if not weights:
        raise _fail("target_weights 不可为空映射")
    total = sum(weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOL:
        raise _fail(f"target_weights 之和须为 1（容差 {_WEIGHT_SUM_TOL}），实际 {total}")
    return weights


def parse_replay_schedule(raw: Mapping[str, Any] | None) -> ReplaySchedule:
    """解析并校验回放规则。

    Args:
        raw: 原始规则映射；None/空映射 → 默认规则（月度定期）。

    Returns:
        已校验的不可变 ``ReplaySchedule``。

    Raises:
        ValueError: 任一字段非法（未知键/枚举外值/阈值越界/权重和不为 1/版本不符）。
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise _fail(f"规则须为映射，实际 {type(raw).__name__}")
    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise _fail(f"存在未知键 {sorted(unknown)}（允许：{sorted(_KNOWN_KEYS)}）")

    rule_type = raw.get("rule_type", "cadence")
    if not isinstance(rule_type, str) or rule_type not in RULE_TYPES:
        raise _fail(f"rule_type 须为 {sorted(RULE_TYPES)} 之一，实际 {rule_type!r}")

    cadence = raw.get("cadence", "monthly")
    if not isinstance(cadence, str) or cadence not in CADENCES:
        raise _fail(f"cadence 须为 {sorted(CADENCES)} 之一，实际 {cadence!r}")

    threshold_pp: float | None = None
    if rule_type == "threshold":
        value = raw.get("threshold_pp", 5.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _fail(f"threshold_pp 须为数值（百分点），实际 {type(value).__name__}")
        number = float(value)
        if not math.isfinite(number) or not (MIN_THRESHOLD_PP < number <= MAX_THRESHOLD_PP):
            raise _fail(f"threshold_pp 须落在 ({MIN_THRESHOLD_PP}, {MAX_THRESHOLD_PP}] 百分点，实际 {value!r}")
        threshold_pp = number
    elif "threshold_pp" in raw:
        raise _fail("threshold_pp 仅适用于 rule_type='threshold'（定期规则不应携带阈值）")

    target_weights = _validate_target_weights(raw.get("target_weights"))

    version = raw.get("version", SCHEDULE_VERSION)
    if isinstance(version, bool) or not isinstance(version, int) or version != SCHEDULE_VERSION:
        raise _fail(f"version 须为当前契约版本 {SCHEDULE_VERSION}（旧版本规则序列按未命中丢弃），实际 {version!r}")

    return ReplaySchedule(
        rule_type=rule_type,
        cadence=cadence,
        threshold_pp=threshold_pp,
        target_weights=target_weights,
        version=version,
    )


def schedule_fingerprint(schedule: ReplaySchedule) -> str:
    """规则指纹（缓存键 / 回放载荷去重用）：契约任一字段变化即换键。"""
    payload = {
        "rule_type": schedule.rule_type,
        "cadence": schedule.cadence,
        "threshold_pp": schedule.threshold_pp,
        "target_weights": schedule.target_weights,
        "version": schedule.version,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "CADENCES",
    "MAX_THRESHOLD_PP",
    "MIN_THRESHOLD_PP",
    "RULE_TYPES",
    "SCHEDULE_VERSION",
    "ReplaySchedule",
    "parse_replay_schedule",
    "schedule_fingerprint",
]
