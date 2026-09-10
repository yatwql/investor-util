"""决策跨期反思闭环 — 结算服务。

对账本中已到期的 pending 决策，用**真实后续行情**结算：以决策登记时落库的
baseline_close 为基线，取当前可得的最新行情 close 计算区间涨跌，按决策方向
判定 hit/miss/flat/gap，并尽量附沪深300 区间基准涨跌（供超额 alpha 统计）。

约束与口径（承接 augur 纪律，见 design §1.2/§5）：
  - 本模块属 report 层（消费历史行情能力），单向依赖 ``core.decision_ledger``。
  - 只在结算服务的 report seam 中、于 LLM 拉取之前调用（先结旧 → 教训可用）。
  - 结算是**幂等**的：同一 decision 只结一次（账本已带 settlement 的跳过），
    重复调用不产生重复结算事件。
  - 开关关闭时无感（返回空结果、不触碰行情）。
  - 非回测：结算仅录入账本，统计与教训输出均带免责声明。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core import decision_ledger as dl

logger = logging.getLogger("invest")

# 结算目标视界：决策满 MIN_SETTLE_BARS 个交易日后才结算（账本常量）
# 沪深300 指数代码（基准；历史文件缓存走 history_index chain）
_BENCHMARK_INDEX = "sh000300"
_BENCHMARK_NAME = "沪深300"

# 拉取窗口（交易日 bar 数）上界，防止一次结算请求过长历史
_FETCH_DAYS_CAP = 120


def _latest_close(series: list[dict[str, Any]] | None) -> float | None:
    """取按日期升序序列的最近一个有效 close。"""
    if not series:
        return None
    for bar in reversed(series):
        close = bar.get("close") or bar.get("nav")
        if close is not None and close > 0:
            return float(close)
    return None


def _series_at_date(
    series: list[dict[str, Any]] | None,
    target_date: str,
) -> float | None:
    """取某日（或之前最近一日，last-close 对齐）的 close；无则 None。"""
    if not series:
        return None
    best: float | None = None
    for bar in series:
        if bar.get("date", "") > target_date:
            break
        close = bar.get("close") or bar.get("nav")
        if close is not None and close > 0:
            best = float(close)
    return best


def fetch_price_series(
    holding_code: str,
    holding_name: str,
    days: int,
) -> list[dict[str, Any]] | None:
    """拉取单标的近 N 个交易日的行情序列（对齐 portfolio_history 路由）。

    走 ``PortfolioHistoryCalculator`` 的 as-if 市值序列（内含 kline/nav 统一与
    代码类型路由 + 降级），无需 shares——将 shares=1 得纯价格 close 序列。
    全链路失败/不支持类型返回 None。
    """
    from src.python.report.portfolio_history import PortfolioHistoryCalculator

    calc = PortfolioHistoryCalculator()
    try:
        return calc.calculate_for_holding(
            holding_code=holding_code,
            holding_name=holding_name,
            shares=1.0,
            days=days,
        )
    except Exception:
        logger.warning("[decision_settlement] 行情序列获取异常: %s %s", holding_code, holding_name, exc_info=True)
        return None


def fetch_index_series(index_code: str, days: int) -> list[dict[str, Any]] | None:
    """拉取指数近 N 个交易日 close 序列（走 history_index chain）。"""
    from src.python.fetcher.index import fetch_index_history

    try:
        return fetch_index_history(index_code, days=days) or None
    except Exception:
        logger.warning("[decision_settlement] 基准指数获取异常: %s", index_code, exc_info=True)
        return None


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("date") or "")


def settle_pending_decisions(
    *,
    report_date: str,
    horizon_bars: int = dl.MIN_SETTLE_BARS,
    ledger_path: str | None = None,
    benchmark_index: str | None = None,
    price_series_fn: Any = None,
    index_series_fn: Any = None,
    threshold: float = dl.DIRECTION_THRESHOLD,
) -> dict[str, Any]:
    """结算账本中到期的 pending 决策。

    仅结算 report_date 之前满 horizon_bars 个交易日、且账本无 settlement 的决策。

    Args:
        price_series_fn / index_series_fn: 依赖注入（测试用 mock）；
            缺省走真实行情（fetch_price_series / fetch_index_series）。
        horizon_bars: 结算视界（账本常量 5）；此处用 max 防御低位。

    Returns:
        {"settled": N, "ids": [...], "deferred": M, "skipped": K, "summary": [...]}
    """
    if not dl.is_active():
        return {"settled": 0, "ids": [], "deferred": 0, "skipped": 0, "summary": []}

    horizon = max(horizon_bars, dl.MIN_SETTLE_BARS)
    bench = benchmark_index or _BENCHMARK_INDEX
    _price_fn = price_series_fn or fetch_price_series
    _index_fn = index_series_fn or fetch_index_series

    stats = dl.fold_ledger(path=ledger_path)
    pending = [d for d in stats["decisions"] if d.get("status") != "settled"]

    ids: list[str] = []
    deferred = 0
    skipped = 0
    summary: list[dict[str, Any]] = []

    for d in pending:
        code = str(d.get("code") or "").strip()
        did = str(d.get("decision_id") or "")
        direction = int(d.get("direction") or 0)
        # 持有/中性无方向语义，不结算（保持 pending，由统计剔除）
        if direction not in (dl.DIRECTION_LONG, dl.DIRECTION_SHORT):
            skipped += 1
            continue
        baseline = d.get("baseline_close")
        if baseline is None or baseline <= 0:
            deferred += 1  # 无基线（早期无 baseline 的登记）→ 无法可靠结算，暂缓
            continue
        baseline = float(baseline)
        rep_date = str(d.get("report_date") or "")
        # 幂等性由账本 fold 保证：结算落档后该 decision 转 settled，下次不在 pending。
        # 成熟度（是否满 horizon 个交易日）由 _settle_one 内按 bar 数判定，此处不做日期预判。
        outcome, hit, raw, bench_ret, horizon_used = _settle_one(
            code=code,
            name=str(d.get("name") or ""),
            direction=direction,
            baseline=baseline,
            rep_date=rep_date,
            horizon=horizon,
            bench=bench,
            price_series_fn=_price_fn,
            index_series_fn=_index_fn,
            threshold=threshold,
        )
        if outcome is None:
            deferred += 1
            continue
        dl.append_settlement(
            decision_id=did,
            raw_return=raw,
            outcome=outcome,
            direction_hit=hit,
            settle_date=report_date,
            horizon_bars=horizon_used,
            bench_return=bench_ret,
            path=ledger_path,
        )
        ids.append(did)
        summary.append(
            {
                "code": code,
                "decision_id": did,
                "outcome": outcome,
                "raw_return": raw,
                "bench_return": bench_ret,
                "horizon_bars": horizon_used,
            }
        )

    return {
        "settled": len(ids),
        "ids": ids,
        "deferred": deferred,
        "skipped": skipped,
        "summary": summary,
    }


def _settle_one(
    *,
    code: str,
    name: str,
    direction: int,
    baseline: float,
    rep_date: str,
    horizon: int,
    bench: str,
    price_series_fn: Any,
    index_series_fn: Any,
    threshold: float,
) -> tuple[str | None, bool | None, float, float | None, int]:
    """单条结算：拉最新行情 close → 算区间涨跌 → 判定 + 基准。

    Returns:
        (outcome, hit, raw, bench_ret, horizon_used)；
        行情不可得/未到期等不可判定 → (None, None, 0.0, None, 0)。
    """
    # 抓取窗口：目标 horizon + 冗余余量（保证至少含 horizon 个交易日 bar）
    fetch_days = min(max(horizon + 30, 30), _FETCH_DAYS_CAP)
    series = price_series_fn(code, name, fetch_days)
    latest = _latest_close(series)
    if latest is None:
        return None, None, 0.0, None, 0

    # 成熟度门槛：统计决策日（rep_date）之后出现的交易日 bar 数，
    # 需 ≥ horizon 才算已到结算视界。rep_date 缺失视为可结（取 horizon 计）。
    if rep_date:
        bars_after = sum(1 for b in series if _bar_date(b) > rep_date)
        if bars_after < horizon:
            return None, None, 0.0, None, 0  # 尚未满 horizon 个交易日
        horizon_used = bars_after
    else:
        horizon_used = horizon
    raw = latest / baseline - 1.0

    # 基准区间涨跌：决策日与最新收盘日两点的指数 close 比值
    bench_ret: float | None = None
    index_series = index_series_fn(bench, fetch_days)
    if index_series:
        if rep_date and _bar_date(index_series[-1]):
            idx_base = _series_at_date(index_series, rep_date)
            idx_last = _latest_close(index_series)
            if idx_base and idx_last and idx_base > 0:
                bench_ret = idx_last / idx_base - 1.0

    outcome, hit = dl.classify_direction_outcome(raw, direction, threshold=threshold)
    return outcome, hit, raw, bench_ret, horizon_used
