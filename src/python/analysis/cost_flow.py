"""成本流水分析 — 资金加权收益（XIRR）与分笔成本分档、分红累计。

输入：持仓 Excel 可选「交易流水」「分红流水」页签的解析结果
（core.models.TradeRecord / DividendRecord）+ 当前持仓（Holding）+
当前市价（dict[code, float]）。纯本地计算，零新增外部依赖。

模块职责（纯计算层，禁止导入 report/ 包；依赖方向 analysis ← core.models）：
  1. XIRR 资金加权收益：现金流时点加权内部收益率（Newton-Raphson + 二分兜底）。
     现金流口径（投资者视角）：买入/申购为负（资金流出），卖出/赎回与分红
     到账为正（资金流入），期末市值为正（资金收回）。分红按登记日份额纳入时点效应。
  2. 成本分档：交易流水按代码 FIFO 合并成本批次（lot），相对当前市价分
     低成本/高成本档（支持分档止盈与「是否追高加仓」判断）；无市价品种单列。
  3. 分红累计：按代码汇总分红金额（每份分红×登记日份额，份额未知回退当前持仓）。

数据契约 `fund_flow_data`（pipeline_data 键，`build_fund_flow_data` 输出）：
  {
    "available": bool,      # 任一子数据可用
    "xirr": {"rate": float, "cashflow_count": int, "end_date": str} | None,
    "cost_tiers": {"available": bool, "per_code": {...}, "totals": {...}, "high_cost_ratio": float},
    "dividends": {"available": bool, "per_code": {code: 金额}, "total": float},
  }
  渲染层消费该契约，分档/累计列与 XIRR 汇总行均在此取数。

  快照近似模式（无流水页签时由 `build_approximate_fund_flow_data` 输出）额外带
  `"approximate": true` 键——渲染层据此写「可选进阶增强」说明，替代「必须录入
  流水」的压力文案；真实流水模式无此键（消费方统一用 `.get("approximate")` 判空，
  缺省按 False 处理）。
"""

from __future__ import annotations

import datetime as _dt
import logging
import math
from typing import Any

from src.python.core.models import DividendRecord, Holding, TradeRecord

logger = logging.getLogger("invest")

__all__ = [
    "solve_xirr",
    "build_xirr_cashflows",
    "build_cost_lots",
    "compute_cost_tiers",
    "compute_dividend_totals",
    "build_fund_flow_data",
    "build_approximate_fund_flow_data",
]

# 迭代求解参数（XIRR 收敛）
_DEFAULT_GUESS = 0.10
_TOLERANCE = 1e-7
_MAX_ITER = 100
_BISECT_STEPS = 200
# 二分兜底扫描区间（跨越常见年化收益范围：-99.99% ~ +1600%）
_BISECT_SCAN = (-0.9999, -0.5, 0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
# 自然日年化基准
_DAYS_PER_YEAR = 365.0
# 份额比较容差（FIFO 扣减）
_EPS = 1e-9


# ─────────────────────────────────────────────────────────────
#  XIRR 求解
# ─────────────────────────────────────────────────────────────


def _as_date(value: Any) -> _dt.date | None:
    """解析日期（datetime.date / datetime / YYYY-MM-DD 字符串），失败返回 None。"""
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for sep in ("-", "/"):
            parts = text.split(sep)
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                try:
                    return _dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
                except ValueError:
                    return None
    return None


def _npv(rate: float, amounts: list[float], ts: list[float]) -> float:
    """现金流净现值 NPV(r) = Σ amount_i / (1+r)^t_i。"""
    return sum(a / (1.0 + rate) ** t for a, t in zip(amounts, ts))


def _bisect_root(amounts: list[float], ts: list[float], tolerance: float) -> float | None:
    """二分兜底：在扫描区间内找 NPV 变号点并收敛。"""
    lo: float | None = None
    hi: float | None = None
    f_lo = 0.0
    for i in range(len(_BISECT_SCAN) - 1):
        a = _BISECT_SCAN[i]
        b = _BISECT_SCAN[i + 1]
        fa = _npv(a, amounts, ts)
        fb = _npv(b, amounts, ts)
        if fa == 0.0:
            return a
        if fb == 0.0:
            return b
        if fa * fb < 0.0:
            lo, hi, f_lo = a, b, fa
            break
    if lo is None or hi is None:
        return None
    for _ in range(_BISECT_STEPS):
        mid = (lo + hi) / 2.0
        fm = _npv(mid, amounts, ts)
        if abs(fm) < tolerance:
            return mid
        if f_lo * fm < 0.0:
            hi = mid
        else:
            lo = mid
            f_lo = fm
    return (lo + hi) / 2.0


def solve_xirr(
    amounts: list[float],
    dates: list[Any],
    guess: float = _DEFAULT_GUESS,
    tolerance: float = _TOLERANCE,
    max_iter: int = _MAX_ITER,
) -> float | None:
    """求解资金加权收益率（XIRR）。

    时点权重 t_i = (date_i - 基准日).days / 365（自然日年化）。求解
    NPV(r) = Σ amount_i / (1+r)^t_i = 0，Newton-Raphson 迭代主解，
    收敛判据 |NPV| < tolerance；发散或域外时降级二分兜底。

    Args:
        amounts: 现金流金额（投资者视角：投入为负，收回/分红为正）
        dates:   对应时点（须与 amounts 等长；首笔为基准日 t=0）
        guess:   初始猜测年化收益率（默认 10%）
        tolerance: 收敛阈值（|NPV| 绝对误差）
        max_iter: 最大迭代次数

    Returns:
        年化收益率浮点（如 0.102 表示 10.2%）；现金流缺乏可解性时返回 None
        （空输入 / 长度不一致 / 日期非法 / 全部现金流同一天 / 求解域外）。
    """
    if not amounts or not dates or len(amounts) != len(dates):
        return None
    parsed = [_as_date(d) for d in dates]
    if any(d is None for d in parsed):
        return None
    base = parsed[0]
    ts = [(d - base).days / _DAYS_PER_YEAR for d in parsed]
    if all(abs(t) < _EPS for t in ts):
        return None

    rate = guess
    for _ in range(max_iter):
        if 1.0 + rate <= 0.0 or not math.isfinite(rate):
            break
        f = _npv(rate, amounts, ts)
        if abs(f) < tolerance:
            return rate
        # NPV 关于 r 的导数：-Σ t_i·amount_i/(1+r)^(t_i+1)
        df = sum(-t * a / (1.0 + rate) ** (t + 1.0) for a, t in zip(amounts, ts))
        if abs(df) < _EPS:
            break
        step = f / df
        nxt = rate - step
        if not math.isfinite(nxt):
            break
        if abs(step) < tolerance * max(1.0, abs(rate)):
            return nxt
        rate = nxt
    return _bisect_root(amounts, ts, tolerance)


# ─────────────────────────────────────────────────────────────
#  现金流构造（交易 + 分红 + 期末市值）
# ─────────────────────────────────────────────────────────────


def build_xirr_cashflows(
    transactions: list[TradeRecord],
    dividends: list[DividendRecord],
    holdings: list[Holding],
    current_prices: dict[str, float] | None,
    end_date: _dt.date | None = None,
) -> list[tuple[_dt.date, float]] | None:
    """构造投资者视角现金流序列（XIRR 输入）。

    买入/申购 → 负现金流 -(价格×份额 + 费用)；卖出/赎回 → 正现金流
    +(价格×份额 - 费用)；分红到账 → 正现金流 +每份分红×登记日份额
    （登记日份额未知时回退当前持仓份额）；期末市值 → 正现金流
    +Σ 份额×当前市价（估值日为 end_date 或最后一条流水的日期）。

    Args:
        transactions: 交易流水记录
        dividends:    分红流水记录
        holdings:     当前持仓（分红份额回退与期末市值取数）
        current_prices: 代码 → 当前市价（期末市值；缺码按 0 不计）
        end_date:      期末估值日（缺省取最后一条流水的日期）

    Returns:
        按日期升序的 (日期, 金额) 列表；无任何可计流水时返回 None。
    """
    flows: list[tuple[_dt.date, float]] = []
    for t in transactions:
        d = _as_date(t.date)
        if d is None:
            continue
        if t.action == "buy":
            flows.append((d, -(t.price * t.shares + t.fee)))
        elif t.action == "sell":
            flows.append((d, t.price * t.shares - t.fee))

    current_shares = {h.code: h.shares for h in holdings}
    for div in dividends:
        d = _as_date(div.date)
        if d is None:
            continue
        shares = div.shares if div.shares > 0 else current_shares.get(div.code, 0.0)
        if shares <= 0:
            continue
        flows.append((d, div.amount * shares))

    if not flows:
        return None

    prices = current_prices or {}
    final_value = sum(h.shares * prices[h.code] for h in holdings if h.code in prices)
    if final_value > 0:
        valuation = end_date or max(d for d, _ in flows)
        flows.append((valuation, final_value))

    flows.sort(key=lambda x: x[0])
    return flows


# ─────────────────────────────────────────────────────────────
#  成本分档（FIFO 批次）
# ─────────────────────────────────────────────────────────────


def build_cost_lots(transactions: list[TradeRecord]) -> dict[str, Any]:
    """交易流水按代码 FIFO 合并成本批次（lot）。

    买入流水生成批次（成本价 = 价格 + 费用/份额摊薄）；卖出流水按
    FIFO 扣减批次份额。返回剩余批次即当前持仓的成本结构（供分档用）。

    Args:
        transactions: 交易流水记录

    Returns:
        {"available": bool, "lots": {code: [{"date", "shares", "cost_price"}]}}
        无买入流水或全部批次被卖出清空时 available=False。
    """
    lots: dict[str, list[dict[str, Any]]] = {}
    has_buy = False
    for t in sorted(transactions, key=lambda x: (_as_date(x.date) or _dt.date.min, x.code)):
        if t.action == "buy":
            has_buy = True
            cost_price = t.price + (t.fee / t.shares if t.shares > 0 else 0.0)
            lots.setdefault(t.code, []).append(
                {
                    "date": (_as_date(t.date) or _dt.date.min).isoformat(),
                    "shares": t.shares,
                    "cost_price": cost_price,
                }
            )
        elif t.action == "sell":
            queue = lots.get(t.code)
            if not queue:
                continue
            remaining = t.shares
            while remaining > _EPS and queue:
                lot = queue[0]
                if lot["shares"] <= remaining:
                    remaining -= lot["shares"]
                    queue.pop(0)
                else:
                    lot["shares"] -= remaining
                    remaining = 0.0
    has_lots = has_buy and any(queue for queue in lots.values())
    return {"available": has_lots, "lots": lots}


def compute_cost_tiers(
    transactions: list[TradeRecord],
    current_prices: dict[str, float] | None,
) -> dict[str, Any]:
    """成本分档（低成本/高成本档，相对当前市价）。

    档位口径：批次成本价 ≤ 当前市价 → 低成本档（盈利在握，可止盈）；
    > 当前市价 → 高成本档（浮亏，追高加仓）；无市价品种单列「未分档」，
    不计入档位占比。

    Args:
        transactions: 交易流水记录
        current_prices: 代码 → 当前市价

    Returns:
        {
          "available": bool,
          "per_code": {code: {"low": {...}, "high": {...}, "unpriced": {...}}},
          "totals": {"low": {...}, "high": {...}, "unpriced": {...}},
          "high_cost_ratio": float,   # 高成本档份额 / (低+高) 档份额，无定价份额为 0
        }
        每档含 shares / cost / market_value；unpriced 无 market_value。
    """
    empty = {
        "available": False,
        "per_code": {},
        "totals": {"low": _tier_zero(), "high": _tier_zero(), "unpriced": _tier_zero()},
        "high_cost_ratio": 0.0,
    }
    lots_data = build_cost_lots(transactions)
    if not lots_data["available"]:
        return empty

    prices = current_prices or {}
    per_code: dict[str, dict[str, Any]] = {}
    totals = {"low": _tier_zero(), "high": _tier_zero(), "unpriced": _tier_zero()}

    for code, lots in lots_data["lots"].items():
        price = prices.get(code)
        buckets = {"low": _tier_zero(), "high": _tier_zero(), "unpriced": _tier_zero()}
        for lot in lots:
            shares = lot["shares"]
            cost = lot["cost_price"] * shares
            market = shares * price if price is not None else 0.0
            if price is None:
                bucket = "unpriced"
            elif lot["cost_price"] <= price:
                bucket = "low"
            else:
                bucket = "high"
            b = buckets[bucket]
            b["shares"] += shares
            b["cost"] += cost
            b["market_value"] += market
        per_code[code] = buckets
        for bucket in ("low", "high", "unpriced"):
            _merge_tier(totals[bucket], buckets[bucket])

    low = totals["low"]["shares"]
    high = totals["high"]["shares"]
    priced = low + high
    high_ratio = high / priced if priced > 0 else 0.0
    return {
        "available": True,
        "per_code": per_code,
        "totals": totals,
        "high_cost_ratio": high_ratio,
    }


def _tier_zero() -> dict[str, float]:
    """分档空桶（份额/成本/市值全 0）。"""
    return {"shares": 0.0, "cost": 0.0, "market_value": 0.0}


def _merge_tier(target: dict[str, float], src: dict[str, float]) -> None:
    """把 src 档位累加进 target（不可变更新——新建累加结果）。"""
    target["shares"] += src["shares"]
    target["cost"] += src["cost"]
    target["market_value"] += src["market_value"]


# ─────────────────────────────────────────────────────────────
#  分红累计
# ─────────────────────────────────────────────────────────────


def compute_dividend_totals(
    dividends: list[DividendRecord],
    holdings: list[Holding],
) -> dict[str, Any]:
    """分红累计：按代码汇总分红金额。

    每份分红 × 登记日份额（登记日份额未知时回退当前持仓份额；无持仓份额
    可回退的品种跳过）。

    Args:
        dividends: 分红流水记录
        holdings:  当前持仓（份额回退取数）

    Returns:
        {"available": bool, "per_code": {code: 金额}, "total": float}
    """
    current_shares = {h.code: h.shares for h in holdings}
    per_code: dict[str, float] = {}
    for div in dividends:
        shares = div.shares if div.shares > 0 else current_shares.get(div.code, 0.0)
        if shares <= 0:
            continue
        per_code[div.code] = per_code.get(div.code, 0.0) + div.amount * shares
    return {
        "available": bool(per_code),
        "per_code": per_code,
        "total": sum(per_code.values()),
    }


# ─────────────────────────────────────────────────────────────
#  数据契约组装
# ─────────────────────────────────────────────────────────────


def build_fund_flow_data(
    transactions: list[TradeRecord],
    dividends: list[DividendRecord],
    holdings: list[Holding],
    current_prices: dict[str, float] | None,
    end_date: _dt.date | None = None,
) -> dict[str, Any]:
    """组装数据契约 `fund_flow_data`（渲染层消费的完整数据结构）。

    Args:
        transactions: 交易流水记录
        dividends:    分红流水记录
        holdings:     当前持仓
        current_prices: 代码 → 当前市价
        end_date:      期末估值日（XIRR 用）

    Returns:
        契约 dict（结构见模块 docstring）；无任一子数据时 available=False，
        渲染层据此决定分档/XIRR 行是否展示。
    """
    xirr_data: dict[str, Any] | None = None
    cashflows = build_xirr_cashflows(transactions, dividends, holdings, current_prices, end_date)
    if cashflows:
        amounts = [a for _, a in cashflows]
        dates = [d for d, _ in cashflows]
        rate = solve_xirr(amounts, dates)
        if rate is not None:
            xirr_data = {
                "rate": rate,
                "cashflow_count": len(cashflows),
                "end_date": max(dates).isoformat(),
            }

    tiers = compute_cost_tiers(transactions, current_prices)
    div_totals = compute_dividend_totals(dividends, holdings)
    available = xirr_data is not None or tiers["available"] or div_totals["available"]
    return {
        "available": available,
        "xirr": xirr_data,
        "cost_tiers": tiers,
        "dividends": div_totals,
    }


def build_approximate_fund_flow_data(
    holdings: list[Holding],
    current_prices: dict[str, float] | None,
    start_date: _dt.date | None = None,
    end_date: _dt.date | None = None,
) -> dict[str, Any]:
    """从持仓快照合成近似成本流水数据（零流水输入出价值）。

    单笔建仓假设：每个品种视为建仓日一次性买入当前持仓份额（价格 = 每份成本），
    据此合成交易流水 → 复用 build_fund_flow_data 产出成本分档（单档判断：
    低成本/高成本，相对市价）与近似年化收益（一次性投入的内部收益率）。
    分红累计不可由快照推导，保持 available=False（说明文案中已交代）。

    Args:
        holdings: 当前持仓（份额 + 每份成本）
        current_prices: 代码 → 当前市价
        start_date: 可选组合建仓日；None 时买入日取期末日 → XIRR 因同日
            现金流无解而返回 None（仅产出成本分档）
        end_date: 期末估值日（缺省取今日）

    Returns:
        fund_flow_data 契约，且带 approximate=True（渲染层据此写
        「可选进阶增强」说明，替代「必须录入流水」的压力文案）。
    """
    end = end_date or _dt.date.today()
    synthetic: list[TradeRecord] = []
    for h in holdings:
        if h.shares <= 0 or h.cost_price <= 0:
            continue
        synthetic.append(
            TradeRecord(
                date=start_date or end,
                code=h.code,
                action="buy",
                shares=h.shares,
                price=h.cost_price,
                fee=0.0,
            )
        )
    data = build_fund_flow_data(synthetic, [], holdings, current_prices, end_date=end)
    data["approximate"] = True
    return data
