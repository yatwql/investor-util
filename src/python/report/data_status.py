"""数据源状态追踪与降级阈值基础设施。

职责边界 —— 与 html_writer.py 中 raw_data_flags 的关系：
  raw_data_flags: 控制 section 可见性（"这个模块该不该显示？"）
                  值 = 数据是否为空（bool）
  _data_status:   控制数据源状态反馈（"数据拿到了吗？"）
                  值 = 每个数据源的可用详情（dict）

两者正交互补：
  - raw_data_flags = False → 模块隐藏（不占位）
  - raw_data_flags = True 且 _data_status 有失败项 → 页签底部显示状态摘要
  - raw_data_flags = True 且 _data_status 全成功 → 一切正常，不渲染摘要
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, TypedDict

from src.python.config import get_config

logger = logging.getLogger("invest")

# ── 类型定义 ──────────────────────────────────


class DataStatusItem(TypedDict):
    available: bool
    tier: str       # "T2" / "T3" / "T4"
    message: str    # 最终展示文本，直接渲染不拼接


DataStatus = dict[str, DataStatusItem]


# ── 消息常量 ──────────────────────────────────
# Excel 和 HTML 两端共享引用，保证消息一致

STATUS_MESSAGES: dict[str, str] = {
    "rank_unavailable":       "基金业绩排名数据不可用，排名列显示 --",
    "benchmark_unavailable":  "业绩基准数据不可用",
    "industry_unavailable":   "行业分类数据暂不可用（数据源 push2 不稳定）",
    "holdings_unavailable":   "穿透持仓数据暂不可用",
    "profit_forecast_unavailable": "盈利预测数据不可用，EPS 列显示 --",
    "dividend_unavailable":   "分红数据暂不可用",
    "index_degraded":         "指数数据来自降级链路",

    # B 系列占位文本
    "manager_unavailable":    "基金经理数据暂不可用",
    "overlap_unavailable":    "持仓数据不足，无法计算重合度",
    "concentration_unavailable": "持仓集中度数据暂不可用",
    "style_unavailable":      "基金风格数据暂不可用",

    # 新闻 / 预警
    "news_all_failed":        "新闻数据暂不可用，请检查网络连接",
    "warning_unavailable":    "预警数据暂不可用",
}

# 按层级的前缀符号：T2 → ⚠（橙色警告），T3/T4 → ℹ（蓝色提示）
TIER_PREFIX: dict[str, str] = {"T2": "⚠", "T3": "ℹ", "T4": "ℹ"}


# ── 默认阈值 ──────────────────────────────────
# 硬编码兜底值，config.json 未配置时使用

_DEFAULT_UNREACHABLE: dict[str, int] = {"t2": 3, "t3": 4, "t4": 1}
_DEFAULT_EMPTY: dict[str, int] = {"t2": 5, "t3": 6, "t4": 2}
_DEFAULT_STALE_DAYS: dict[str, int] = {"t2": 1, "t3": 14, "t4": 14}

# 持久化文件路径
_DEGRADATION_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache", ".degradation_state.json",
)


# ── 降级阈值控制 ──────────────────────────────


class DegradationTracker:
    """双信号降级阈值控制器 + 跨会话持久化。

    信号1（连续失败）：
      会话内同一数据源按失败类型分别计数，成功后全部归零。
      两种失败类型各有独立阈值（从 config.json 读取）：
        - unreachable（连接不上/超时）→ 低阈值，快速确认故障
        - empty（API 返回了但数据为空）→ 高阈值，容忍瞬态空响应

    信号2（缓存陈旧 / 持久化陈旧）：
      缓存最后成功写入距今超过层级容忍天数。
      无缓存但持久化有上次成功时间戳时也用此天数判断。
      无缓存且无持久化记录（全新数据源）时不触发——由信号1自适应调节处理。

    自适应调节：
      新鲜缓存（≤TTL）→ 阈值 +1（更宽容）
      无缓存 / 严重过期（>3×TTL）→ 阈值 -1，最小为 1（更敏感）

    跨会话持久化：
      每次成功 record() 将时间戳写入 ``.degradation_state.json``。
      下次会话启动时加载，令信号 2 在无缓存源（如 push2）上仍可跨会话触发。

    线程安全：计数器操作使用 threading.Lock。
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._lock = threading.Lock()
        # _counts[source_key] = {"unreachable": int, "empty": int}
        self._counts: dict[str, dict[str, int]] = {}

        # 跨会话持久化：{source_key: last_success_unix_ts}
        self._persist_path = persist_path or _DEGRADATION_STATE_FILE
        self._last_success: dict[str, float] = self._load_persisted_state()

    # ── 持久化 ─────────────────────────────────

    def _load_persisted_state(self) -> dict[str, float]:
        """从 JSON 文件加载保存的上次成功时间戳。"""
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
        except Exception:
            logger.debug("[degradation] 持久化状态加载失败，使用空状态", exc_info=True)
        return {}

    def _persist_state(self) -> None:
        """将当前 last_success 写入 JSON 文件。"""
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(self._last_success, f, ensure_ascii=False)
        except Exception:
            logger.debug("[degradation] 持久化状态保存失败（非关键）", exc_info=True)

    # ── 公开 API ──────────────────────────────

    def record(
        self,
        source_key: str,
        tier: str,
        success: bool,
        failure_type: str = "unreachable",
        cache_age_hours: float | None = None,
        cache_ttl_hours: float | None = None,
    ) -> tuple[bool, int, int]:
        """记录一次数据获取结果，判断是否应降级。

        Args:
            source_key: 数据源标识（如 ``"industry"``、``"rank"``）
            tier: 层级 ``"T2"`` / ``"T3"`` / ``"T4"``
            success: 本次获取是否成功
            failure_type: 失败类型 —— ``"unreachable"``（连接不上）
                          或 ``"empty"``（数据为空）
            cache_age_hours: 缓存数据年龄（小时），用于信号2
            cache_ttl_hours: 缓存标准 TTL（小时），用于自适应调节

        Returns:
            (是否降级, 当前最大失败计数, 有效阈值)

            成功时返回 (False, 0, 0)。
        """
        with self._lock:
            return self._record_unsafe(
                source_key, tier, success, failure_type,
                cache_age_hours, cache_ttl_hours,
            )

    def reset(self, source_key: str) -> None:
        """手动重置指定数据源的计数器和持久化记录。"""
        with self._lock:
            self._counts.pop(source_key, None)
            self._last_success.pop(source_key, None)
            self._persist_state()

    def get_counts(self, source_key: str) -> dict[str, int]:
        """读取当前失败计数（线程安全）。"""
        with self._lock:
            return dict(self._counts.get(source_key, {}))

    # ── 内部实现 ──────────────────────────────

    def _record_unsafe(
        self,
        source_key: str,
        tier: str,
        success: bool,
        failure_type: str,
        cache_age_hours: float | None,
        cache_ttl_hours: float | None,
    ) -> tuple[bool, int, int]:
        # 成功 → 全部归零 + 更新持久化时间戳
        if success:
            self._counts.pop(source_key, None)
            self._last_success[source_key] = time.time()
            self._persist_state()
            return False, 0, 0

        # 读取层级配置
        cfg = self._get_tier_config(tier)

        # 递增对应失败类型的计数器
        counts = self._counts.setdefault(source_key, {"unreachable": 0, "empty": 0})
        counts[failure_type] += 1

        # 从配置读取基础阈值
        base_unreachable = cfg.get("unreachable_threshold", _DEFAULT_UNREACHABLE[tier.lower()])
        base_empty = cfg.get("empty_data_threshold", _DEFAULT_EMPTY[tier.lower()])

        # 自适应调节
        unreachable_eff = self._adjust(base_unreachable, cache_age_hours, cache_ttl_hours)
        empty_eff = self._adjust(base_empty, cache_age_hours, cache_ttl_hours)

        # 信号1：任一失败类型超过其有效阈值
        signal1 = (
            counts["unreachable"] >= unreachable_eff
            or counts["empty"] >= empty_eff
        )

        # 信号2：缓存陈旧度 or 持久化跨会话陈旧度
        signal2 = self._check_stale(tier, cfg, cache_age_hours, source_key)

        return signal1 or signal2, max(counts.values()), min(unreachable_eff, empty_eff)

    @staticmethod
    def _adjust(base: int, cache_age_hours: float | None, cache_ttl_hours: float | None) -> int:
        """自适应调节阈值。"""
        if cache_age_hours is not None and cache_ttl_hours is not None:
            if cache_age_hours <= cache_ttl_hours:
                return base + 1  # 新鲜缓存 → 更宽容
            if cache_age_hours > cache_ttl_hours * 3:
                return max(1, base - 1)  # 严重过期 → 更敏感
            return base  # 正常过期
        # 无缓存 → 更敏感
        return max(1, base - 1)

    def _check_stale(
        self,
        tier: str,
        cfg: dict[str, Any],
        cache_age_hours: float | None,
        source_key: str,
    ) -> bool:
        """信号2：检查数据是否超过容忍期限。

        优先用缓存年龄判断；无缓存时用持久化上次成功时间判断。
        两者均无时返回 False（全新数据源，由信号1处理）。
        """
        stale_days = cfg.get("stale_days", _DEFAULT_STALE_DAYS.get(tier.lower(), 3))
        stale_hours = stale_days * 24

        # 有缓存 → 用缓存年龄
        if cache_age_hours is not None:
            return cache_age_hours > stale_hours

        # 无缓存但有跨会话持久化记录 → 用 persistence age
        last_ts = self._last_success.get(source_key)
        if last_ts is not None:
            age_hours = (time.time() - last_ts) / 3600
            return age_hours > stale_hours

        # 两者均无 → 全新数据源，由信号1自适应调节处理
        return False

    @staticmethod
    def _get_tier_config(tier: str) -> dict[str, Any]:
        """从 config.json 读取单层级降级配置（懒加载，每次调用均重读）。"""
        cfg = get_config()
        degradation = cfg.get("degradation", {}) if isinstance(cfg, dict) else {}
        tier_key = tier.lower()
        if not isinstance(degradation, dict):
            return {}
        return degradation.get(tier_key, {}) if isinstance(degradation.get(tier_key), dict) else {}
