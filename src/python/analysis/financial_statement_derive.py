"""合并报表 → 标准财务指标记录（纯派生，无网络、无缓存）。

用途：把同花顺官方三张合并报表（利润表 / 资产负债表 / 现金流量表）归一为
``schemas.datasource_fields.FinancialIndicatorFields`` 的标准字段记录，作为财务指标
域的**第三条链路**（主源 akshare；备用 DataSinking 章节解析），使主源失效时仍有
官方结构化数据可用。

口径（与主源对齐，便于同一序列内比较）：
  - 金额单位**元**；比率一律**小数**（0.5789 = 57.89%）
  - 毛利率 = (营业收入 − 营业成本) ÷ 营业收入
  - 资产负债率 = 负债合计 ÷ 资产合计
  - ROE = 归母净利润 ÷ 归母权益（**期末口径**；主源 akshare 为加权口径，实测差
    0.1 个百分点量级，同源序列内可比）
  - 同比 = 与**上年同期**比较（一季度对一季度、年报对年报）；上年同期缺失或基数为
    非正/非数值时返回 ``None``（宁缺勿错，不臆造）
  - 文种由报告期月份推断（03-31→q1、06-30→semiannual、09-30→q3、12-31→annual）

不适用的字段（主源有、官方报表不直接给）：``bvps`` 恒 ``None``（官方资产负债表不提供
总股本，无法折算每股净资产）——PB 类派生在该源上不可用，故本模块不产 PB。

纯函数：入参是上游原始响应（``{"item": [...]}``），出参是标准记录列表（报告期降序）。
字段归一复用 ``core.num_utils``（脏值一律 ``None``），不抛异常。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.python.core.num_utils import ms_to_date_str, safe_num

#: 报告期月份 → 文种（法定披露节奏）
_MONTH_TO_DOC_TYPE: dict[int, str] = {3: "q1", 6: "semiannual", 9: "q3", 12: "annual"}

SOURCE_API = "hithink"
SOURCE_NAME = "同花顺金融数据"


def _items(raw: Any) -> list[dict[str, Any]]:
    """取 ``{"item": [...]}`` 的条目列表；结构异常返回空列表。"""
    if not isinstance(raw, dict):
        return []
    items = raw.get("item")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


#: 财季 → 标准报告期末（**不能用上游时间戳**：实测同花顺季度条目的 ``period_end_ms``
#: 给的是披露窗口起点，如 2026Q1 为 04-01 而非 03-31；主源 akshare 用的是标准季末，
#: 两侧混用会让同报告期对不上——同比对齐与趋势比较都会错位）
_FISCAL_PERIOD_END: dict[str, str] = {"Q1": "-03-31", "Q2": "-06-30", "Q3": "-09-30", "Q4": "-12-31"}


def _period_end(entry: dict[str, Any]) -> str:
    """条目的**标准报告期**（``YYYY-MM-DD``，季末口径）。

    优先 ``fiscal_year``+``fiscal_period``（Q1→03-31 / Q2→06-30 / Q3→09-30 / Q4→12-31）；
    缺该组合时回退时间戳（``period_end_ms`` → ``report_date_ms`` → ``publish_date_ms``），
    再回退 ``period`` 字段；均不可得返回空串（调用方跳过该期）。
    """
    year = str(entry.get("fiscal_year") or "").strip()
    fiscal_period = str(entry.get("fiscal_period") or "").strip().upper()
    if year.isdigit() and fiscal_period in _FISCAL_PERIOD_END:
        return f"{int(year)}{_FISCAL_PERIOD_END[fiscal_period]}"
    for key in ("period_end_ms", "report_date_ms", "publish_date_ms"):
        value = ms_to_date_str(entry.get(key))
        if value:
            return value
    period = str(entry.get("period") or "").strip()
    return period if period.count("-") == 2 else ""


def _doc_type(report_period: str) -> str:
    """报告期 → 文种（无法判定返回空串）。"""
    try:
        month = datetime.strptime(report_period, "%Y-%m-%d").month
    except (TypeError, ValueError):
        return ""
    return _MONTH_TO_DOC_TYPE.get(month, "")


def _ratio(numerator: Any, denominator: Any) -> float | None:
    """比率（分母须为有限正数，否则 ``None``）。"""
    num, den = safe_num(numerator), safe_num(denominator)
    if num is None or den is None or den <= 0:
        return None
    return num / den


def _yoy(current: Any, previous: Any) -> float | None:
    """同比 = (本期 − 上年同期) ÷ |上年同期|；上年同期缺失或为 0 时 ``None``。"""
    cur, prev = safe_num(current), safe_num(previous)
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def _key(entry: dict[str, Any]) -> tuple[str, str]:
    """同报告期的对齐键：``(报告期, 文种)``。"""
    period = _period_end(entry)
    return period, _doc_type(period)


def derive_indicator_records(
    income: Any,
    balance: Any,
    cashflow: Any,
    *,
    code: str,
    symbol: str,
    valuation: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """三张合并报表 → 标准财务指标记录（报告期降序）。

    Args:
        income: 利润表原始响应（``financials/income-statements``）
        balance: 资产负债表原始响应
        cashflow: 现金流量表原始响应
        code: 6 位证券代码
        symbol: thscode（如 ``600900.SH``）
        valuation: 官方估值快照（``{"pe_ttm": …, "pb_mrq": …}``；仅写入**最新一期**）
        limit: 最多返回期数（``None`` = 全部）

    Returns:
        标准字段记录列表；任一张表为空则返回空列表（链路据此降级，不产半份数据）。
    """
    incomes = _items(income)
    balances = _items(balance)
    cashflows = _items(cashflow)
    if not incomes or not balances or not cashflows:
        return []

    balance_by_key = {_key(e): e for e in balances}
    cashflow_by_key = {_key(e): e for e in cashflows}
    # 同比需要「上年同期」：按 (文种, 报告期) 索引全部利润表条目
    income_by_key = {_key(e): e for e in incomes}

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in incomes:
        period, doc_type = _key(entry)
        if not period:
            continue
        row = _build_row(
            entry,
            balance_by_key.get((period, doc_type)),
            cashflow_by_key.get((period, doc_type)),
            income_by_key,
            period=period,
            doc_type=doc_type,
            code=code,
            symbol=symbol,
        )
        by_key[(period, doc_type)] = row

    records = [by_key[k] for k in sorted(by_key, key=lambda k: k[0], reverse=True)]
    if valuation and records:
        # 官方估值只有「当下」一个快照 → 只挂到最新一期（历史期不能倒填，否则等于造假）
        records[0]["pe_ttm"] = safe_num(valuation.get("pe_ttm"))
        records[0]["pb_mrq"] = safe_num(valuation.get("pb_mrq"))
    return records[: int(limit)] if limit else records


def _build_row(
    income: dict[str, Any],
    balance: dict[str, Any] | None,
    cashflow: dict[str, Any] | None,
    income_by_key: dict[tuple[str, str], dict[str, Any]],
    *,
    period: str,
    doc_type: str,
    code: str,
    symbol: str,
) -> dict[str, Any]:
    """单期记录（缺表/缺字段一律 ``None``，不猜）。"""
    revenue = safe_num(income.get("operating_income"))
    net_profit = safe_num(income.get("parent_holder_net_profit"))
    if net_profit is None:
        net_profit = safe_num(income.get("net_profit"))
    cost = safe_num(income.get("operating_costs"))
    gross_margin = (revenue - cost) / revenue if revenue and cost is not None and revenue > 0 else None

    assets = safe_num((balance or {}).get("assets_total"))
    debt = safe_num((balance or {}).get("total_debt"))
    equity = safe_num((balance or {}).get("holder_equity_total"))
    debt_ratio = _ratio(debt, assets)
    roe = _ratio(net_profit, equity)

    prior = _prior_year_entry(income_by_key, period=period, doc_type=doc_type)
    revenue_yoy = _yoy(revenue, safe_num((prior or {}).get("operating_income")))
    prior_net = safe_num((prior or {}).get("parent_holder_net_profit"))
    if prior_net is None:
        prior_net = safe_num((prior or {}).get("net_profit"))
    net_profit_yoy = _yoy(net_profit, prior_net)

    return {
        "code": code,
        "symbol": symbol,
        "report_period": period,
        "doc_type": doc_type,
        "revenue": revenue,
        "net_profit": net_profit,
        "revenue_yoy": revenue_yoy,
        "net_profit_yoy": net_profit_yoy,
        "gross_margin": gross_margin,
        "roe": roe,
        "debt_ratio": debt_ratio,
        "operating_cash_flow": safe_num((cashflow or {}).get("act_cash_flow_net")),
        "eps": safe_num(income.get("basic_eps")),
        # 官方资产负债表不提供总股本 → 无法折算每股净资产（该源不产 PB）
        "bvps": None,
        # 官方估值（TTM/MRQ）只有当下快照，由调用方在最新一期上覆盖；历史期恒 None
        "pe_ttm": None,
        "pb_mrq": None,
        "source_api": SOURCE_API,
        "source": SOURCE_NAME,
    }


def _prior_year_entry(
    income_by_key: dict[tuple[str, str], dict[str, Any]], *, period: str, doc_type: str
) -> dict[str, Any] | None:
    """上年同期条目（同文种、报告期减一年）；不可得返回 ``None``。"""
    try:
        year, rest = period.split("-", 1)
        prior_period = f"{int(year) - 1}-{rest}"
    except (ValueError, AttributeError):
        return None
    return income_by_key.get((prior_period, doc_type))


__all__ = ["SOURCE_API", "SOURCE_NAME", "derive_indicator_records"]
