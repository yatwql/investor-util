"""确定性数值信号沉淀 — 信号账本核心 + live/demo 标签纪律（语义名 signal_ledger）。

把项目已有的确定性算法评级（市场温度低估/合理/高估、估值分位 tier、尾部风险
VaR、风格因子、再平衡超限）逐次沉淀为可回溯的记录，并给每条记录打**来源标签**，
使统计口径默认只算「本次实时可得」的记录，防非实时记录冒充真实战绩
（承接 augur `backtest.py` 的 `data_source` 标签 + 排行榜默认 live_only 纪律）。

设计约束遵从（详见 docs-stm/plan/signal-ledger-implementation.md）：
    分层约束  — 本模块属 core 层，只依赖 stdlib + 同层 core，禁止 import
                report/llm/analysis 下的任何模块。因此**不含**评级词汇表
                （低估/高估/超限等）：评级 → 方向的映射由 report 层适配器
                `report/signal_record.py` 完成（它可 import analysis 常量），
                本模块只认「评级字符串 + 方向整数」这一通用形状。
    持久化    — data/state/signal_ledger.jsonl，纯追加事件型 JSONL，原子写入
                （委托 core/jsonl_store.append_jsonl_atomic）
    无单例    — 本模块为无状态函数集：读档 → fold 统计 / 原子追加。
                不设 get_signal_ledger()/reset_signal_ledger()，避免跨测试状态泄漏
    幂等      — 同一 (report_date, signal_type, subject) 当日重复运行不重复入账，
                对齐 decision_ledger 的同日防重纪律
    统计现算  — 统计/摘要/指纹后缀在调用时按需读档现算，不驻留模块全局

数据流：
    build_signal()           构造规范化记录（由 report 层适配器调用）
    append_signal(s)()       原子追加（按 id 幂等去重）
    load_signals()           读全量记录（损坏行容错）
    fold_signals()           折叠统计（默认 live_only=True）
    summary_block()          注入提示词的统计摘要文本（样本不足返回 ""）
    summary_cache_suffix()   摘要文本的缓存指纹后缀（同源现算）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Iterable

from src.python.core.constants import PROJECT_ROOT
from src.python.core.data_freshness import FRESHNESS_FRESH, FRESHNESS_LABELS
from src.python.core.decision_ledger import DIRECTION_FLAT
from src.python.core.jsonl_store import append_jsonl_atomic, read_jsonl
from src.python.core.num_utils import strict_num

logger = logging.getLogger("invest")

__all__ = [
    "FEATURE_FLAG",
    "DATA_SOURCE_LIVE",
    "DATA_SOURCE_DEMO",
    "DATA_SOURCE_LABELS",
    "SIGNAL_MARKET_TEMPERATURE",
    "SIGNAL_VALUATION",
    "SIGNAL_TAIL_RISK",
    "SIGNAL_STYLE_FACTOR",
    "SIGNAL_REBALANCE_OVERFLOW",
    "SIGNAL_TYPE_LABELS",
    "SIGNAL_TYPE_ORDER",
    "MIN_SUMMARY_SAMPLE",
    "is_active",
    "resolve_data_source",
    "build_signal",
    "append_signal",
    "append_signals",
    "load_signals",
    "fold_signals",
    "summary_block",
    "summary_cache_suffix",
]


# ── 特性开关名 ──────────────────────────────────────────
# 全链路（report seam / llm 注入 / 指纹后缀 / config.features 注册）收敛于此旗标
FEATURE_FLAG = "signal_ledger"

# ── 持久化路径 ──────────────────────────────────────────
# module-level 变量，测试时可通过 monkeypatch.setattr 重定向（测试隔离模式）。
# data/state 而非 data/cache：避开 cache.cleanup_expired() 清扫（理由同
# src/python/report/data_status.py _default_persist_path）。
_SIGNAL_LEDGER_FILE = os.path.join(PROJECT_ROOT, "data", "state", "signal_ledger.jsonl")

# ── 事件类型 ────────────────────────────────────────────
EVENT_SIGNAL = "signal"

# ── 来源标签（live/demo 纪律，承接 augur backtest.py）────
DATA_SOURCE_LIVE = "live"  # 本次运行实时可得
DATA_SOURCE_DEMO = "demo"  # 非本次实时（缓存/过期/降级）
DATA_SOURCE_LABELS: dict[str, str] = {
    DATA_SOURCE_LIVE: "实时",
    DATA_SOURCE_DEMO: "非实时",
}

REASON_DEGRADED = "依赖数据源本次降级"
REASON_LIVE_FRESH = "本次实时行情"
REASON_LIVE_NO_FRESHNESS = "组合级/指数级信号，无逐品种新鲜度条目"

# ── 信号类型枚举（一条确定性算法评级 = 一类信号）────────
SIGNAL_MARKET_TEMPERATURE = "market_temperature"
SIGNAL_VALUATION = "valuation_percentile"
SIGNAL_TAIL_RISK = "tail_risk"
SIGNAL_STYLE_FACTOR = "style_factor"
SIGNAL_REBALANCE_OVERFLOW = "rebalance_overflow"

SIGNAL_TYPE_LABELS: dict[str, str] = {
    SIGNAL_MARKET_TEMPERATURE: "市场温度",
    SIGNAL_VALUATION: "估值分位",
    SIGNAL_TAIL_RISK: "尾部风险",
    SIGNAL_STYLE_FACTOR: "风格因子",
    SIGNAL_REBALANCE_OVERFLOW: "再平衡超限",
}

# 摘要块/统计的稳定输出顺序（增删信号类型时同步维护，保证输出可预期）
SIGNAL_TYPE_ORDER: tuple[str, ...] = (
    SIGNAL_MARKET_TEMPERATURE,
    SIGNAL_VALUATION,
    SIGNAL_TAIL_RISK,
    SIGNAL_STYLE_FACTOR,
    SIGNAL_REBALANCE_OVERFLOW,
)

# 摘要注入的 live 样本门槛（低于该值不产出摘要块，防噪声误导——
# 对齐 decision_ledger.MIN_LESSON_SAMPLE 的同一纪律）
MIN_SUMMARY_SAMPLE = 3


def is_active() -> bool:
    """特性开关是否开启（收敛判定）。开关关闭时全链路无感。"""
    from src.python.config.features import is_feature_enabled

    return is_feature_enabled(FEATURE_FLAG)


# ── 来源标签判定（收敛于单一函数，禁止调用点自行拼字符串）────


def resolve_data_source(
    *,
    freshness: str | None = None,
    degraded: bool = False,
) -> tuple[str, str]:
    """由既有数据质量事实推导来源标签，返回 ``(data_source, source_reason)``。

    判据（判定顺序即优先级）：
      1. ``degraded=True``         → demo（依赖数据源本次降级）
      2. ``freshness`` 为 None      → live（组合级/指数级信号，无逐品种条目）
      3. ``freshness == "fresh"``  → live（本次实时行情）
      4. 其余任意 freshness 取值     → demo（缓存 T-1 / 过期 / 降级 / 未识别）

    **保守缺省**：第 4 条对**未识别**的新鲜度取值也判 demo——只有可证明为实时
    （``fresh``）的记录才算 live。这强化了 label 纪律的本意：非实时记录不得
    冒充真实战绩，宁可少算不可错算。新增新鲜度枚举时无需改本模块。

    **边界纪律**：第 2 条的乐观缺省**仅**适用于组合级（风格因子、尾部风险）与
    指数级（市场温度）信号——它们没有 data_freshness.items 条目。**持仓级**信号
    （估值分位、再平衡超限）必须由调用方传入该 code 的 freshness，不得省参。

    Args:
        freshness: core/data_freshness 的逐品种新鲜度取值（fresh/cached/stale/degraded）
        degraded: 该信号依赖的数据源本次是否降级

    Returns:
        ``(DATA_SOURCE_LIVE | DATA_SOURCE_DEMO, 可读理由)``
    """
    if degraded:
        return DATA_SOURCE_DEMO, REASON_DEGRADED
    if freshness is None:
        return DATA_SOURCE_LIVE, REASON_LIVE_NO_FRESHNESS
    if freshness == FRESHNESS_FRESH:
        return DATA_SOURCE_LIVE, REASON_LIVE_FRESH
    return DATA_SOURCE_DEMO, f"行情{FRESHNESS_LABELS.get(freshness, freshness)}"


# ── 记录构造 ────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_number(value: Any) -> float | int | None:
    """数值归一：非数值/±inf/NaN → None。

    账本要求严格合法 JSON——Python ``json.dumps`` 会把 inf/nan 写成
    ``Infinity``/``NaN``，那是**非法 JSON**，会让下游解析器整行丢弃。

    归一口径（含拒绝数值字符串、拒绝 bool）收敛于
    :func:`core.num_utils.strict_num`，全项目单一实现。
    """
    return strict_num(value)


def build_signal(
    *,
    signal_type: str,
    report_date: str,
    rating: str,
    value: Any = None,
    subject: str = "",
    name: str = "",
    direction: int | None = None,
    data_source: str = DATA_SOURCE_LIVE,
    source_reason: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造规范化信号记录（不落盘）。

    Args:
        signal_type: SIGNAL_* 枚举之一
        report_date: 报告日期（YYYY-MM-DD），参与幂等键
        rating: 确定性评级原文（如 低估/合理/高估/超限/风格名）
        value: 关键数值（分位/温度分/VaR/超限百分点等），非有限数归 None
        subject: 标的（指数代码/持仓代码/portfolio）
        name: 标的中文名
        direction: DIRECTION_LONG/SHORT/FLAT；None → FLAT
        data_source: resolve_data_source() 的返回值
        source_reason: resolve_data_source() 的返回值（可读理由）
        detail: 该信号特有的附加字段
    """
    subject_key = subject or "portfolio"
    return {
        "event": EVENT_SIGNAL,
        "id": f"{report_date}|{signal_type}|{subject_key}",
        "report_date": report_date,
        "signal_type": signal_type,
        "subject": subject_key,
        "name": name,
        "rating": rating,
        "value": _safe_number(value),
        "direction": DIRECTION_FLAT if direction is None else direction,
        "data_source": data_source,
        "source_reason": source_reason,
        "detail": detail or {},
        "recorded_at": _now_iso(),
    }


# ── 追加（按 id 幂等去重）───────────────────────────────


def load_signals(path: str | None = None) -> list[dict[str, Any]]:
    """读取全量信号记录（按写入顺序）。损坏行跳过并告警，不中断后续行。"""
    return read_jsonl(path or _SIGNAL_LEDGER_FILE, log_tag="signal_ledger", noun="账本")


def append_signals(
    signals: Iterable[dict[str, Any]],
    path: str | None = None,
) -> list[dict[str, Any]]:
    """批量原子追加信号记录，返回**实际新增**的记录列表。

    幂等：已在账本中的 ``id``（= ``报告日|信号类型|标的``）跳过；同一批内
    重复 ``id`` 亦只取首条。去重后一次性写入（读一次 + 一次原子替换），
    避免逐条追加减写放大。

    空输入或全部命中幂等 → 不触碰账本文件（返回空列表）。

    **落盘失败同样返回空列表**（写盘异常已由 :mod:`core.jsonl_store` 记日志）。
    本函数对外承诺的是「实际入账条数」，调用方据此上报「登记 N 条」；若失败仍
    返回去重后的 ``fresh``，磁盘满/无写权限时会报出绿色成功而账本零新增，且下次
    运行因读不到这些 id 而重复登记——静默失败 + 跨期沉淀失效。
    """
    incoming = [s for s in signals if isinstance(s, dict) and s.get("id")]
    if not incoming:
        return []
    target = path or _SIGNAL_LEDGER_FILE
    seen = {s.get("id") for s in load_signals(target)}
    fresh: list[dict[str, Any]] = []
    for record in incoming:
        sid = record["id"]
        if sid in seen:
            logger.debug("[signal_ledger] 幂等跳过已存在记录: %s", sid)
            continue
        seen.add(sid)
        fresh.append(record)
    if not fresh:
        return []
    payload = "".join(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n" for s in fresh)
    written = append_jsonl_atomic(target, payload, prefix=".signal_ledger_", log_tag="signal_ledger", noun="账本")
    # 写盘失败 → 未入账，不返回乐观结果（详见 docstring）
    return fresh if written else []


def append_signal(**kwargs: Any) -> dict[str, Any] | None:
    """构造并追加单条信号记录，返回落账记录（幂等跳过时返回 None）。"""
    path = kwargs.pop("path", None)
    appended = append_signals([build_signal(**kwargs)], path=path)
    return appended[0] if appended else None


# ── 折叠统计（默认只算 live）────────────────────────────


def fold_signals(
    signals: Iterable[dict[str, Any]] | None = None,
    *,
    live_only: bool = True,
    path: str | None = None,
) -> dict[str, Any]:
    """折叠账本统计。

    Args:
        signals: 记录集合；None → 现读账本
        live_only: True（默认）时 ``records`` 只计 data_source=="live" 的记录；
            ``live_count``/``demo_count`` 恒为全量计数，供对比展示
        path: 账本路径（仅 signals 为 None 时生效）

    Returns:
        ``{records, live_count, demo_count, by_type, dates, first_date,
        last_date, live_only, sample_sufficient}``
    """
    raw = list(signals) if signals is not None else load_signals(path)
    # 只认对象记录：显式传入的集合可能夹带 None/字符串（调用方拼接失误），
    # 逐项过滤而非整体崩，与 load_signals 的容错口径一致。
    items = [s for s in raw if isinstance(s, dict)]
    live = [s for s in items if s.get("data_source") == DATA_SOURCE_LIVE]
    demo = [s for s in items if s.get("data_source") == DATA_SOURCE_DEMO]
    counted = live if live_only else items

    by_type: dict[str, dict[str, Any]] = {}
    for signal_type in SIGNAL_TYPE_ORDER:
        subset = [s for s in counted if s.get("signal_type") == signal_type]
        if not subset:
            continue
        latest = subset[-1]  # 账本按写入顺序追加，末条即最新
        by_type[signal_type] = {
            "label": SIGNAL_TYPE_LABELS.get(signal_type, signal_type),
            "records": len(subset),
            "live": sum(1 for s in live if s.get("signal_type") == signal_type),
            "demo": sum(1 for s in demo if s.get("signal_type") == signal_type),
            "latest_date": latest.get("report_date", ""),
            "latest_rating": latest.get("rating", ""),
            "latest_value": latest.get("value"),
        }

    dates = sorted({s.get("report_date", "") for s in counted if s.get("report_date")})
    return {
        "records": len(counted),
        "live_count": len(live),
        "demo_count": len(demo),
        "by_type": by_type,
        "dates": dates,
        "first_date": dates[0] if dates else "",
        "last_date": dates[-1] if dates else "",
        "live_only": live_only,
        "sample_sufficient": len(live) >= MIN_SUMMARY_SAMPLE,
    }


# ── 提示词注入（摘要文本 + 缓存指纹后缀）────────────────


def summary_block(
    signals: Iterable[dict[str, Any]] | None = None,
    *,
    live_only: bool = True,
    path: str | None = None,
) -> str:
    """生成注入提示词的确定性信号统计摘要；开关关闭或样本不足返回 ""。

    **开关判定收敛在本函数内**（不在调用点判）——缓存指纹后缀经本函数取文本，
    从而写侧指纹闭包与预检闭包天然同源，不会因两侧开关判定写法不同而漂移。
    开关判定**无条件生效**（传显式 signals 亦不绕过），保证「开关关闭 → 全链路无感」
    在注入路径上恒成立。
    """
    if not is_active():
        return ""
    folded = fold_signals(signals, live_only=live_only, path=path)
    if not folded["sample_sufficient"]:
        return ""

    scope = "仅实时记录" if live_only else "含非实时记录"
    lines = [f"【确定性信号沉淀（{scope}）】"]
    for signal_type in SIGNAL_TYPE_ORDER:
        info = folded["by_type"].get(signal_type)
        if not info:
            continue
        value = info.get("latest_value")
        value_text = f"，{value}" if value is not None else ""
        lines.append(
            f"- {info['label']}：最近 {info['latest_date']} 判「{info['latest_rating']}」"
            f"{value_text}（{info['records']} 条）"
        )
    if folded["demo_count"]:
        lines.append(
            f"（实时 {folded['live_count']} 条 / 非实时 {folded['demo_count']} 条"
            f"{'已剔除' if live_only else '已计入'}，勿与非实时记录混算真实战绩）"
        )
    return "\n".join(lines)


def summary_cache_suffix(
    signals: Iterable[dict[str, Any]] | None = None,
    *,
    live_only: bool = True,
    path: str | None = None,
) -> str:
    """摘要文本的缓存指纹后缀。

    摘要文本变化（新信号落账 / live→demo 标签变化）→ 后缀变化 → LLM 缓存键同变
    → 携带新摘要重新生成；开关关闭或样本不足 → 空串（缓存键与未注入时完全一致，
    不误伤既有缓存）。写侧指纹闭包与 orchestrator 预检闭包同调本函数，保证读写键同源。
    """
    block = summary_block(signals, live_only=live_only, path=path)
    if not block:
        return ""
    digest = hashlib.md5(block.encode("utf-8")).hexdigest()[:12]
    return f"_sg{digest}"
