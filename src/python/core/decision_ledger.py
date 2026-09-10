"""决策跨期反思闭环 — 事件型决策账本核心（语义名 decision_reflection）。

对判断（含 LLM 看多看空 与 确定性再平衡/行动建议）不即时评判——当次记作
pending 决策；同标的再现时用真实后续行情结算（方向正确率、超额 alpha），
产出教训回灌后续分析提示词。

设计约束遵从（详见 docs-stm/archive/v0.10.x/tradingagents-borrowing/decision-reflection-implementation.md）：
    分层约束  — 本模块属 core 层，只依赖 stdlib + PROJECT_ROOT，
                禁止 import report/llm/analysis 下的任何模块
    （对齐 src/python/core/perf.py 位于 core 的先例）
    持久化    — data/state/decision_ledger.jsonl，事件型 JSONL（decision /
                settlement 两种事件），原子追加（tempfile.mkstemp + os.replace）
    无单例    — 本模块为无状态函数集：读档 → fold 统计 / 原子追加。
                不设 get_ledger()/reset_ledger()，避免跨测试状态泄漏
    教训现算  — 教训文本/指纹后缀在调用时按需读档现算，不驻留模块全局，
                因此「注册→结算→教训→注入」因果链天然闭环（见设计 §6）

数据流：
    append_decision()/append_settlement()  追加事件（report 层 seam 调用）
    load_events()                          读全量事件（损坏行容错）
    fold_ledger()                          合并 decision+settlement → 统计
    lessons_block()/lessons_cache_suffix() 当前账本的教训文本/指纹后缀
                                           （llm 注入侧调用；现算）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Iterable

from src.python.core.constants import PROJECT_ROOT
from src.python.core.jsonl_store import append_jsonl_atomic, read_jsonl

logger = logging.getLogger("invest")

# ── 特性开关名 ──────────────────────────────────────────
# 全链路（report seam / llm 注入 / 指纹后缀 / config.features 注册）收敛于此旗标
FEATURE_FLAG = "decision_reflection"

# ── 持久化路径 ──────────────────────────────────────────
# module-level 变量，测试时可通过 monkeypatch.setattr 重定向（测试隔离模式）。
# data/state 而非 data/cache：避开 cache.cleanup_expired() 清扫（理由同
# src/python/report/data_status.py _default_persist_path）。
_DECISION_LEDGER_FILE = os.path.join(PROJECT_ROOT, "data", "state", "decision_ledger.jsonl")

# ── 结算/统计口径常量（承接 augur 纪律 + 设计文档 §1.2）──
# 方向：+1 加仓/看多；-1 减仓/看空；0 持有/中性
DIRECTION_LONG = 1
DIRECTION_SHORT = -1
DIRECTION_FLAT = 0

MIN_SETTLE_BARS = 5  # 决策后至少 N 个交易日后才允许结算
DIRECTION_THRESHOLD = 0.015  # |区间涨跌| 低于该值判「平盘不判定」，防噪声计为命中
MEANINGFUL_SAMPLE = 20  # 有效样本 ≥ 该值才给出正式命中率结论
MIN_LESSON_SAMPLE = 3  # 方向判定样本低于该值不产出教训块（防噪声误导）

# 结算结果枚举
OUTCOME_HIT = "hit"
OUTCOME_MISS = "miss"
OUTCOME_FLAT = "flat"
OUTCOME_GAP = "gap"

# 事件类型
EVENT_DECISION = "decision"
EVENT_SETTLEMENT = "settlement"

# 载体枚举（对应决策来源模块）
CARRIER_EXPERT_REVIEW = "expert_review"  # LLM 智囊团操作建议表
CARRIER_REBALANCE = "rebalance"  # 极简再平衡信号（行动章）
CARRIER_DISCIPLINE = "discipline"  # 交易纪律信号
CARRIER_REBALANCE_ADVICE = "rebalance_advice"  # 再平衡建议清单
CARRIER_GENERIC = "generic"  # 未细分载体（低层 API 默认值）


def is_active() -> bool:
    """特性开关是否开启（收敛判定）。开关关闭时全链路无感。"""
    from src.python.config.features import is_feature_enabled

    return is_feature_enabled(FEATURE_FLAG)


# ── 原子 JSONL 追加（对齐 src/python/core/perf.py _append_jsonl_atomic）──────


def _append_event_atomic(event: dict[str, Any], path: str | None = None) -> None:
    """向事件账本原子追加一行 JSON（原语见 `core/jsonl_store.py`）。

    策略：读全部现有内容 → 追加新行 → tempfile.mkstemp + os.replace 写回，
    防断电/崩溃产生半写损坏档。
    """
    target = path or _DECISION_LEDGER_FILE
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    append_jsonl_atomic(target, line, prefix=".decision_ledger_", log_tag="decision_ledger", noun="账本")


def load_events(path: str | None = None) -> list[dict[str, Any]]:
    """读取全量事件（按写入顺序）。损坏行跳过并告警，不中断后续行。"""
    return read_jsonl(path or _DECISION_LEDGER_FILE, log_tag="decision_ledger", noun="账本")


# ── 事件构建与登记 ──────────────────────────────────────


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def append_decision(
    *,
    code: str,
    name: str,
    direction: int,
    carrier: str = CARRIER_GENERIC,
    detail: str = "",
    magnitude: str = "mid",
    report_date: str | None = None,
    baseline_close: float | None = None,
    path: str | None = None,
) -> str:
    """登记一条 pending 决策，返回 decision_id。

    Args:
        direction: DIRECTION_LONG(+1)/DIRECTION_SHORT(-1)/DIRECTION_FLAT(0)
        carrier: 来源载体（CARRIER_*）
        magnitude: 强度/优先级（high/mid/low）
        report_date: 登记运行所在交易日（缺省取本地当日）
        baseline_close: 登记日收盘（结算基线，由 report 层拉取当日行情给出）
    """
    decision_id = uuid.uuid4().hex[:12]
    event: dict[str, Any] = {
        "event": EVENT_DECISION,
        "decision_id": decision_id,
        "report_date": report_date or datetime.now().strftime("%Y-%m-%d"),
        "code": code,
        "name": name,
        "direction": direction,
        "magnitude": magnitude,
        "carrier": carrier,
        "detail": detail,
        "created_at": _now_iso(),
        "status": "pending",
    }
    if baseline_close is not None:
        event["baseline_close"] = baseline_close
    _append_event_atomic(event, path=path)
    return decision_id


def append_settlement(
    *,
    decision_id: str,
    raw_return: float,
    outcome: str,
    direction_hit: bool | None = None,
    settle_date: str | None = None,
    horizon_bars: int = 0,
    bench_return: float | None = None,
    path: str | None = None,
) -> None:
    """为某条 pending 决策追加结算事件（事后不可变，仅追加）。

    Args:
        outcome: OUTCOME_HIT/MISS/FLAT/GAP
        direction_hit: 方向是否命中（flat/gap 为 None）
        settle_date: 结算运行所在交易日
    """
    event: dict[str, Any] = {
        "event": EVENT_SETTLEMENT,
        "decision_id": decision_id,
        "settle_date": settle_date or datetime.now().strftime("%Y-%m-%d"),
        "horizon_bars": horizon_bars,
        "raw_return": raw_return,
        "outcome": outcome,
        "created_at": _now_iso(),
    }
    if direction_hit is not None:
        event["direction_hit"] = direction_hit
    if bench_return is not None:
        event["bench_return"] = bench_return
    _append_event_atomic(event, path=path)


def same_day_pending_exists(
    code: str,
    carrier: str,
    report_date: str | None,
    path: str | None = None,
) -> bool:
    """账本中是否已存在同(报告日, code, carrier)的未结算决策。

    报告 seam 同日重复运行（缓存命中/用户重生成）防重登记用：同报告日内同载体
    同 code 的 pending 决策已存在 → 不再重复入账（append-only 账本避免累积
    重复 pending 污染统计）。跨日运行 report_date 不同 → 不误伤新判断登记。

    settlement 是独立追加事件（decision 事件自身 status 恒为 pending），故须按
    decision_id 归并 settlement 判定是否已结。
    """
    if not report_date:
        return False
    target = str(report_date)
    events = load_events(path=path)
    settled_ids = {ev.get("decision_id") for ev in events if ev.get("event") == EVENT_SETTLEMENT}
    for ev in events:
        if (
            ev.get("event") == EVENT_DECISION
            and ev.get("decision_id") not in settled_ids
            and str(ev.get("code") or "") == str(code)
            and str(ev.get("carrier") or "") == carrier
            and str(ev.get("report_date") or "") == target
        ):
            return True
    return False


def classify_direction_outcome(
    raw_return: float | None,
    direction: int,
    *,
    threshold: float = DIRECTION_THRESHOLD,
) -> tuple[str, bool | None]:
    """纯判定：区间涨跌 × 方向 → 结算结果。

    Returns:
        (outcome, direction_hit)；方向判定仅在 ±1 方向上有意义；
        raw_return 缺失 → (gap, None)；|涨跌| 低于阈值 → (flat, None)。
    """
    if raw_return is None:
        return OUTCOME_GAP, None
    if direction == DIRECTION_FLAT:
        return OUTCOME_FLAT, None
    if abs(raw_return) < threshold:
        return OUTCOME_FLAT, None
    hit = (direction == DIRECTION_SHORT and raw_return < 0) or (direction == DIRECTION_LONG and raw_return > 0)
    return (OUTCOME_HIT if hit else OUTCOME_MISS), hit


# ── fold：decision + settlement 合并统计（不可变聚合）───


def fold_ledger(
    events: Iterable[dict[str, Any]] | None = None,
    *,
    path: str | None = None,
) -> dict[str, Any]:
    """合并账本事件 → 统计摘要。

    以 decision_id 关联 settlement；未结算决策保持 pending。
    返回新字典，不修改入参。结构：
        decisions     已解析决策列表（含 settlement 字段，未结为 None）
        pending_count / settled_count
        counts        {hit, miss, flat, gap}（仅方向性决策计数）
        directional_total / direction_accuracy / sample_sufficient
        alpha_mean    方向性相对基准超额均值（(raw−bench)×方向，可判 alpha 样本）
        by_carrier    {carrier: {...分项}}
    """
    if events is None:
        events = load_events(path=path)

    decisions: list[dict[str, Any]] = []
    settlements: dict[str, dict[str, Any]] = {}
    for ev in events:
        kind = ev.get("event")
        if kind == EVENT_DECISION:
            decisions.append(dict(ev))
        elif kind == EVENT_SETTLEMENT:
            settlements[ev.get("decision_id")] = dict(ev)

    resolved: list[dict[str, Any]] = []
    for d in decisions:
        item: dict[str, Any] = dict(d)
        s = settlements.get(d.get("decision_id"))
        if s is not None:
            item["status"] = "settled"
            item["settlement"] = s
        resolved.append(item)

    # 计数（仅方向性决策参与方向判定统计）
    counts = {OUTCOME_HIT: 0, OUTCOME_MISS: 0, OUTCOME_FLAT: 0, OUTCOME_GAP: 0}
    alpha_sum = 0.0
    alpha_n = 0
    by_carrier: dict[str, dict[str, Any]] = {}
    for r in resolved:
        direction = r.get("direction")
        if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
            continue  # 持有/中性不参与判定统计
        s = r.get("settlement")
        if s is None:
            continue
        outcome = s.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
        carrier = str(r.get("carrier") or "unknown")
        agg = by_carrier.setdefault(carrier, {OUTCOME_HIT: 0, OUTCOME_MISS: 0, OUTCOME_FLAT: 0, OUTCOME_GAP: 0})
        if outcome in agg:
            agg[outcome] += 1
        # 方向性超额 alpha = (区间涨跌 − 基准涨跌) × 方向符号：
        # 看空正确(涨跌<0 且跑赢基准) 或 看多正确(涨跌>0 且跑赢基准) → 正值。
        raw = s.get("raw_return")
        bench = s.get("bench_return")
        if outcome in (OUTCOME_HIT, OUTCOME_MISS) and raw is not None and bench is not None:
            sign = 1 if direction == DIRECTION_LONG else -1
            alpha_sum += (float(raw) - float(bench)) * sign
            alpha_n += 1

    directional_total = counts[OUTCOME_HIT] + counts[OUTCOME_MISS]
    accuracy: float | None = counts[OUTCOME_HIT] / directional_total if directional_total else None

    per_carrier: dict[str, dict[str, Any]] = {}
    for carrier, agg in sorted(by_carrier.items()):
        d_total = agg[OUTCOME_HIT] + agg[OUTCOME_MISS]
        per_carrier[carrier] = {
            "settled": sum(agg.values()),
            "directional": d_total,
            "hit": agg[OUTCOME_HIT],
            "miss": agg[OUTCOME_MISS],
            "flat": agg[OUTCOME_FLAT],
            "gap": agg[OUTCOME_GAP],
            "accuracy": agg[OUTCOME_HIT] / d_total if d_total else None,
        }

    return {
        "decisions": resolved,
        "pending_count": sum(1 for r in resolved if r.get("status") != "settled"),
        "settled_count": sum(1 for r in resolved if r.get("status") == "settled"),
        "counts": dict(counts),
        "directional_total": directional_total,
        "direction_accuracy": accuracy,
        "sample_sufficient": directional_total >= MEANINGFUL_SAMPLE,
        "alpha_mean": alpha_sum / alpha_n if alpha_n else None,
        "by_carrier": per_carrier,
    }


# ── 方向/结论措辞（教训文本用）──


def _direction_verb(direction: int) -> str:
    if direction == DIRECTION_SHORT:
        return "看空（减仓/卖出建议）"
    if direction == DIRECTION_LONG:
        return "看多（加仓建议）"
    return "中性"


def _conclusion(outcome: str) -> str:
    return "判断兑现" if outcome == OUTCOME_HIT else "判断未兑现"


# ── 教训文本 / 指纹后缀（llm 注入侧现算，无驻留全局）──


def _short_examples(resolved: list[dict[str, Any]], limit: int = 2) -> list[str]:
    """取最近若干条可解读的兑现/未兑现案例（供教训注入，控制 token 长度）。"""
    directional = [
        r
        for r in resolved
        if r.get("direction") in (DIRECTION_LONG, DIRECTION_SHORT)
        and r.get("settlement") is not None
        and r.get("settlement", {}).get("outcome") in (OUTCOME_HIT, OUTCOME_MISS)
    ]
    directional.sort(key=lambda r: str(r.get("settlement", {}).get("settle_date") or r.get("created_at") or ""))
    lines: list[str] = []
    for r in directional[-limit:]:
        s = r["settlement"]
        ret = s.get("raw_return")
        if ret is None:
            continue
        horizon = s.get("horizon_bars") or "?"
        lines.append(
            f"- {r.get('name')}({r.get('code')}) {_direction_verb(r.get('direction'))}后"
            f"{horizon}个交易日累计 {ret:+.1%} → {_conclusion(s.get('outcome'))}"
        )
    return lines


def lessons_block(events: Iterable[dict[str, Any]] | None = None, *, path: str | None = None) -> str:
    """基于当前账本 fold 产出一段紧凑教训文本（非回测声明 + 命中统计 + 案例）。

    方向判定样本 < MIN_LESSON_SAMPLE 时返回空串（防噪声误导）；
    未达 MEANINGFUL_SAMPLE 时命中率仅以「命中/总数」形式给出并附样本不足提示。
    """
    stats = fold_ledger(events, path=path)
    counts = stats["counts"]
    directional = stats["directional_total"]
    if directional < MIN_LESSON_SAMPLE:
        return ""

    hit = counts[OUTCOME_HIT]
    block = ["【历史决策复盘 · 非回测，仅供反思参考】"]
    if stats["sample_sufficient"]:
        block.append(f"近 {directional} 次方向性决策方向命中 {hit} 次（命中率 {stats['direction_accuracy']:.0%}）。")
    else:
        block.append(
            f"近 {directional} 次方向性决策方向命中 {hit}/{directional}（样本不足 {MEANINGFUL_SAMPLE}，结论仅参考）。"
        )
    alpha = stats["alpha_mean"]
    if alpha is not None:
        block.append(f"方向性相对基准超额均值 {alpha:+.2%}（>0 表示方向判断整体跑赢基准）。")
    examples = _short_examples(stats["decisions"])
    if examples:
        block.append("近期案例：")
        block.extend(examples)
    block.append("请结合上述复盘审视本轮回调/持有/买卖判断，避免重复同类失误。")
    return "\n".join(block)


def lessons_cache_suffix(events: Iterable[dict[str, Any]] | None = None, *, path: str | None = None) -> str:
    """当前可注入教训文本的定长指纹后缀。

    教训文本变化（如新结算落档）→ 后缀变化 → LLM 缓存键同变 → 携带新教训
    重新生成；无教训文本/开关关闭 → 空串（缓存键与未注入时完全一致，不误伤
    既有缓存）。写侧指纹闭包与 orchestrator 预检闭包同调本函数，保证读写键同源。
    """
    block = lessons_block(events, path=path)
    if not block:
        return ""
    digest = hashlib.md5(block.encode("utf-8")).hexdigest()[:12]
    return f"_lr{digest}"
