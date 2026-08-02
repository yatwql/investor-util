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
from dataclasses import dataclass
from typing import Any, TypedDict

from src.python.cache import get_cache_dir
from src.python.config import get_config

logger = logging.getLogger("invest")

# ── 类型定义 ──────────────────────────────────


class DataStatusItem(TypedDict):
    available: bool
    tier: str  # "T2" / "T3" / "T4"
    message: str  # 最终展示文本，直接渲染不拼接


DataStatus = dict[str, DataStatusItem]


# ── 降级事件类型（get_log() 返回值结构）───


@dataclass
class DegradationEvent:
    """单次降级记录事件。

    每次 record() 或 record_aggregated() 调用产生一个事件，
    供 get_log() 汇总为 LLM 可消费的结构化列表。

    detail 字段为可选字典，用于承载 record_aggregated() 的聚合信息
    （failed_count / total_count / ratio / severity / message）。
    纯 record() 调用不设 detail。
    """

    source_key: str
    tier: str
    success: bool
    failure_type: str
    degraded: bool
    count: int
    effective_threshold: int
    timestamp: float
    detail: dict | None = None  # 聚合降级扩展信息


# ── 消息常量 ──────────────────────────────────
# Excel 和 HTML 两端共享引用，保证消息一致

STATUS_MESSAGES: dict[str, str] = {
    "rank_unavailable": "基金业绩排名数据不可用，排名列显示 --",
    "benchmark_unavailable": "业绩基准数据不可用",
    "industry_unavailable": "行业分类数据暂不可用（数据源 push2 不稳定）",
    "holdings_unavailable": "穿透持仓数据暂不可用",
    "profit_forecast_unavailable": "盈利预测数据不可用，EPS 列显示 --",
    "dividend_unavailable": "分红数据暂不可用",
    "index_degraded": "指数数据来自降级链路",
    # 基金深度分析占位文本
    "manager_unavailable": "基金经理数据暂不可用",
    "overlap_unavailable": "持仓数据不足，无法计算重合度",
    "concentration_unavailable": "持仓集中度数据暂不可用",
    "style_unavailable": "基金风格数据暂不可用",
    "factor_exposure_unavailable": "因子暴露数据暂不可用",
    # 新闻 / 预警
    "news_all_failed": "新闻数据暂不可用，请检查网络连接",
    "warning_unavailable": "预警数据暂不可用",
    # 组合历史走势
    "history_price_unavailable": "个股历史行情获取失败，部分股票走势不可用",
    "history_nav_unavailable": "基金历史净值获取失败，部分基金走势不可用",
    "history_degraded": "历史走势部分数据来自降级链路，精度可能降低",
    "history_correction": "检测到历史数据修正（重叠覆盖），走势可能已重新计算",
    "history_zero_value": "部分交易日存在零收盘价，可能涉及停牌或节假日数据",
}

# 按层级的前缀符号：T2 → ⚠（橙色警告），T3/T4 → ℹ（蓝色提示）
TIER_PREFIX: dict[str, str] = {"T2": "⚠", "T3": "ℹ", "T4": "ℹ"}


# ── 默认阈值 ──────────────────────────────────
# 硬编码兜底值，config.json 未配置时使用

_DEFAULT_UNREACHABLE: dict[str, int] = {"t2": 2, "t3": 2, "t4": 1}
_DEFAULT_EMPTY: dict[str, int] = {"t2": 3, "t3": 3, "t4": 1}
_DEFAULT_STALE_DAYS: dict[str, int] = {"t2": 3, "t3": 14, "t4": 7}


def _default_persist_path() -> str:
    """返回默认持久化文件路径（延迟求值，避免模块导入时的 cwd 依赖）。

    存放于 data/state/ 目录而非 data/cache/，因为 DegradationTracker
    的持久化文件是跨会话状态数据而非可清理的缓存数据，
    避免 cache.cleanup_expired() 误清理。
    """
    cache_dir = get_cache_dir()
    state_dir = os.path.join(os.path.dirname(cache_dir), "state")
    return os.path.join(state_dir, ".degradation_state.json")


# ── 单例工厂 ──────────────────────────────────

_tracker_instance: DegradationTracker | None = None
_tracker_instance_lock = threading.Lock()


def get_tracker(persist_path: str | None = None) -> DegradationTracker:
    """获取 DegradationTracker 单例。

    模块级懒加载单例工厂，消除 fund_performance.py / penetration_sheet.py /
    summary.py 的独立实例碎片化，统一降级状态管理与持久化路径。

    Args:
        persist_path: 持久化文件路径，None 使用默认路径

    Returns:
        DegradationTracker 单例
    """
    global _tracker_instance
    if _tracker_instance is None:
        with _tracker_instance_lock:
            if _tracker_instance is None:
                _tracker_instance = DegradationTracker(persist_path=persist_path)
    return _tracker_instance


def reset_tracker() -> None:
    """重置 DegradationTracker 单例（测试用）。

    清空所有计数器和事件日志，销毁当前实例。
    下次 get_tracker() 调用时重新创建。
    """
    global _tracker_instance
    with _tracker_instance_lock:
        _tracker_instance = None


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
        self._persist_path = persist_path or _default_persist_path()
        self._last_success: dict[str, float] = self._load_persisted_state()

        # 降级配置缓存（在构造时加载一次，避免每次 record() 重复读配置文件）
        self._degradation_config: dict[str, Any] = self._load_degradation_config()

        # 持久化写节流
        self._last_persist_ts: float = 0.0
        self._persist_dirty: bool = False

        # 事件日志（get_log() 数据源）
        self._events: list[DegradationEvent] = []

    # ── 持久化 ─────────────────────────────────

    def _load_persisted_state(self) -> dict[str, float]:
        """从 JSON 文件加载保存的上次成功时间戳。"""
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
        except Exception:
            logger.debug("[degradation] 持久化状态加载失败，使用空状态", exc_info=True)
        return {}

    _PERSIST_INTERVAL = 5.0  # 连续写磁盘的最小间隔（秒）
    _VALID_TIERS: frozenset = frozenset({"T2", "T3", "T4", "t2", "t3", "t4"})

    def _persist_state(self, force: bool = False) -> None:
        """将当前 last_success 写入 JSON 文件（带节流）。

        高频 record(success=True) 调用时跳过中间写，仅当距离上次写入
        超过 _PERSIST_INTERVAL 秒才实际写盘。force=True 强制立即写入。

        Args:
            force: 是否强制立即写入（reset() 时使用）
        """
        now = time.time()
        if not force and self._persist_dirty and now - self._last_persist_ts < self._PERSIST_INTERVAL:
            return  # 节流：距上次写入不足间隔，跳过
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(self._last_success, f, ensure_ascii=False)
            self._last_persist_ts = now
            self._persist_dirty = False
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
            (是否降级, 当前最大失败计数, 最低有效阈值)
            注意：最低有效阈值 = min(unreachable_eff, empty_eff)，
            实际降级由对应的单类型阈值触发（OR 条件），
            该值仅反映最先可能被触发的阈值下限。

            成功时返回 (False, 0, 0)。
        """
        if tier not in self._VALID_TIERS:
            raise ValueError(f"无效的 tier 参数: {tier!r}，必须为 T2/T3/T4")
        with self._lock:
            return self._record_unsafe(
                source_key,
                tier,
                success,
                failure_type,
                cache_age_hours,
                cache_ttl_hours,
            )

    def reset(self, source_key: str) -> None:
        """手动重置指定数据源的计数器和持久化记录。"""
        with self._lock:
            self._counts.pop(source_key, None)
            self._last_success.pop(source_key, None)
            self._persist_state(force=True)

    def get_counts(self, source_key: str) -> dict[str, int]:
        """读取当前失败计数（线程安全）。"""
        with self._lock:
            return dict(self._counts.get(source_key, {}))

    def get_log(self) -> list[dict]:
        """返回会话内所有降级记录事件（线程安全）。

        Returns:
            事件字典列表，每条含 source_key / tier / success / failure_type /
            degraded / count / effective_threshold / timestamp。
            按 record() 调用顺序排列。
        """
        with self._lock:
            return [
                {
                    "source_key": e.source_key,
                    "tier": e.tier,
                    "success": e.success,
                    "failure_type": e.failure_type,
                    "degraded": e.degraded,
                    "count": e.count,
                    "effective_threshold": e.effective_threshold,
                    "timestamp": e.timestamp,
                    "detail": e.detail,
                }
                for e in self._events
            ]

    def clear_log(self) -> None:
        """清空事件日志（测试用）。"""
        with self._lock:
            self._events.clear()

    # ── 聚合降级记录 ──

    def record_aggregated(
        self,
        source_key: str,
        tier: str,
        *,
        failed_count: int,
        total_count: int,
        codes: list[str],
        message: str,
    ) -> None:
        """记录一条聚合降级记录。

        将批量操作中的多条失败压缩为单条降级记录，避免 N 条噪声。
        通过 ratio + severity 区分小故障（3/15）和大故障（15/15）。
        同 (source_key, tier) 的后续调用替换前一条，不追加。

        Args:
            source_key: 数据源标识（如 "batch_fund_rank"）。
            tier: 层级 "T2" / "T3" / "T4"。
            failed_count: 失败资产数。
            total_count: 总资产数。
            codes: 失败资产代码列表。
            message: 人类可读的描述（如 "3/10 个基金排名数据不可用"）。
        """
        ratio = failed_count / total_count if total_count > 0 else 0.0
        severity = "high" if ratio >= 0.5 else "low"

        with self._lock:
            # 同 (source_key, tier) 去重——替换而非追加
            for i, ev in enumerate(self._events):
                if ev.source_key == source_key and ev.tier == tier and ev.failure_type == "aggregated":
                    self._events[i] = DegradationEvent(
                        source_key=source_key,
                        tier=tier,
                        success=False,
                        failure_type="aggregated",
                        degraded=True,
                        count=failed_count,
                        effective_threshold=1,
                        timestamp=time.time(),
                        detail={
                            "failed_count": failed_count,
                            "total_count": total_count,
                            "ratio": round(ratio, 2),
                            "severity": severity,
                            "message": message,
                        },
                    )
                    self._persist_dirty = True
                    return

            self._events.append(
                DegradationEvent(
                    source_key=source_key,
                    tier=tier,
                    success=False,
                    failure_type="aggregated",
                    degraded=True,
                    count=failed_count,
                    effective_threshold=1,
                    timestamp=time.time(),
                    detail={
                        "failed_count": failed_count,
                        "total_count": total_count,
                        "ratio": round(ratio, 2),
                        "severity": severity,
                        "message": message,
                    },
                )
            )
            self._persist_dirty = True

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
        # 成功 → 全部归零 + 更新持久化时间戳（带写节流）
        if success:
            self._counts.pop(source_key, None)
            self._last_success[source_key] = time.time()
            self._persist_dirty = True
            self._persist_state()
            self._events.append(
                DegradationEvent(
                    source_key=source_key,
                    tier=tier,
                    success=True,
                    failure_type=failure_type,
                    degraded=False,
                    count=0,
                    effective_threshold=0,
                    timestamp=time.time(),
                )
            )
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
        signal1 = counts["unreachable"] >= unreachable_eff or counts["empty"] >= empty_eff

        # 信号2：缓存陈旧度 or 持久化跨会话陈旧度
        signal2 = self._check_stale(tier, cfg, cache_age_hours, source_key)

        degraded = signal1 or signal2
        max_count = max(counts.values())
        min_eff = min(unreachable_eff, empty_eff)

        self._events.append(
            DegradationEvent(
                source_key=source_key,
                tier=tier,
                success=False,
                failure_type=failure_type,
                degraded=degraded,
                count=max_count,
                effective_threshold=min_eff,
                timestamp=time.time(),
            )
        )
        return degraded, max_count, min_eff

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
        两者均无时返回 False（全新数据源，由信号1自适应调节处理）。
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
        # （首次运行 count=1 + 无缓存 −1 = 阈=1 → 信号1快速触发）
        return False

    @staticmethod
    def _load_degradation_config() -> dict[str, Any]:
        """从 config.json 加载完整的 degradation 配置段。"""
        cfg = get_config()
        raw = cfg.get("degradation", {}) if isinstance(cfg, dict) else {}
        return raw if isinstance(raw, dict) else {}

    def _get_tier_config(self, tier: str) -> dict[str, Any]:
        """从实例缓存的 degradation 配置中读取单层级降级配置。

        配置在构造时通过 _load_degradation_config() 一次性加载，
        避免每次 record() 重复读配置文件。
        """
        tier_key = tier.lower()
        result = self._degradation_config.get(tier_key, {})
        if not isinstance(result, dict):
            result = {}
        # 合理性校验：≤0 的值会被夹紧逻辑静默限制，记警告让用户自查
        for k, v in result.items():
            if isinstance(v, (int, float)) and v <= 0:
                logger.warning("[degradation] %s.%s=%s 配置值异常（≤0），使用默认值", tier, k, v)
        return result
