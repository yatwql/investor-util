"""akshare 结构化财务指标 —— 上市公司关键财务指标（指标域主源）。

数据来源：akshare ``stock_financial_abstract``（东方财富关键指标，宽表：

    选项 | 指标 | 20260630 | 20260331 | ...（列名即报告期 YYYYMMDD，降序）

本模块把宽表归一为**每报告期一条标准字段记录**（口径见
``schemas/datasource_fields.py::FinancialIndicatorFields``）：

  - 金额字段（营收/净利/经营现金流）单位即元，原样保留；
  - 比率字段（ROE/毛利率/资产负债率/同比）上游为百分数（如 16.75），
    统一换算为**小数比例**（0.1675），与标准字段契约一致；
  - 同名指标出现在多个分组（如 ROE 同时在「常用指标」「盈利能力」）时，
    按表格出现顺序**首个非空**为准（「常用指标」在前）。

边界：非 A 股代码、akshare 未安装、调用超时/异常、宽表为空 → 返回空列表；
调用方按「不可用」降级，不阻断报告主链路。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.code_utils import is_a_share_code, to_fmp_symbol
from src.python.core.num_utils import safe_num
from src.python.providers._utils import run_with_timeout

logger = logging.getLogger("invest")

SOURCE_ID = "akshare_financial"
DISPLAY_NAME = "akshare 财务指标"

_TIMEOUT = 20.0
#: 默认取用最近多少个报告期（覆盖同比与趋势）
MAX_PERIODS = 8

#: 指标名 → (标准字段, 是否百分数)
INDICATOR_MAP: dict[str, tuple[str, bool]] = {
    "营业总收入": ("revenue", False),
    "归母净利润": ("net_profit", False),
    "经营现金流量净额": ("operating_cash_flow", False),
    "基本每股收益": ("eps", False),
    "每股净资产": ("bvps", False),
    "净资产收益率(ROE)": ("roe", True),
    "毛利率": ("gross_margin", True),
    "资产负债率": ("debt_ratio", True),
    "营业总收入增长率": ("revenue_yoy", True),
    "归属母公司净利润增长率": ("net_profit_yoy", True),
}

_DOC_TYPE_BY_MONTH_DAY: dict[str, str] = {
    "0331": "q1",
    "0630": "semiannual",
    "0930": "q3",
    "1231": "annual",
}


def _import_akshare() -> Any:
    """惰性导入 akshare（可选依赖）；不可用时返回 None。"""
    try:
        import akshare as ak

        return ak
    except ImportError:
        logger.info("akshare 模块未安装，财务指标取数跳过")
        return None


def _period_columns(columns: Any) -> list[str]:
    """报告期列（列名为 8 位数字 YYYYMMDD），按时间降序。"""
    return sorted(
        (str(c) for c in columns if str(c).isdigit() and len(str(c)) == 8),
        reverse=True,
    )


def _format_period(period: str) -> str:
    return f"{period[:4]}-{period[4:6]}-{period[6:]}"


def _doc_type(period: str) -> str:
    return _DOC_TYPE_BY_MONTH_DAY.get(period[4:], "")


def _indicator_values(abstract: Any, periods: list[str]) -> dict[str, dict[str, float]]:
    """指标名 → {报告期: 数值}；同名多分组时按表格顺序首个非空为准。"""
    values: dict[str, dict[str, float]] = {}
    for _, row in abstract.iterrows():
        name = str(row.get("指标", "")).strip()
        if not name:
            continue
        bucket = values.setdefault(name, {})
        for period in periods:
            if period in bucket:
                continue
            num = safe_num(row.get(period), default=None)
            if num is not None:
                bucket[period] = float(num)
    return values


def _records(code: str, abstract: Any, periods: list[str]) -> list[dict[str, Any]]:
    """按报告期装配标准字段记录（全部字段恒出现，缺失取 None）。"""
    values = _indicator_values(abstract, periods)
    symbol = to_fmp_symbol(code)
    records: list[dict[str, Any]] = []
    for period in periods:
        record: dict[str, Any] = {
            "code": code,
            "symbol": symbol,
            "report_period": _format_period(period),
            "doc_type": _doc_type(period),
            "source_api": SOURCE_ID,
            "source": DISPLAY_NAME,
        }
        has_metric = False
        for indicator, (field, is_percent) in INDICATOR_MAP.items():
            raw = values.get(indicator, {}).get(period)
            if raw is None:
                record[field] = None
                continue
            record[field] = round(raw / 100.0, 6) if is_percent else raw
            has_metric = True
        if has_metric:
            records.append(record)
    return records


def fetch_financial_indicator_history(code: str, limit: int = MAX_PERIODS) -> list[dict[str, Any]]:
    """取多期财务指标记录（按报告期降序）；无覆盖/失败返回空列表。

    一次 akshare 调用即得全部报告期，调用方可按需截取；不缓存（缓存归链路）。
    """
    code = (code or "").strip()
    if not is_a_share_code(code):
        logger.debug("[akshare_financial] 非 A 股代码，跳过: %s", code)
        return []
    ak = _import_akshare()
    if ak is None:
        return []

    abstract = run_with_timeout(lambda: ak.stock_financial_abstract(symbol=code), timeout=_TIMEOUT)
    if abstract is None or getattr(abstract, "empty", True):
        logger.info("[akshare_financial] %s 无财务指标数据", code)
        return []

    periods = _period_columns(getattr(abstract, "columns", []))[: max(1, int(limit))]
    if not periods:
        logger.warning("[akshare_financial] %s 宽表无报告期列", code)
        return []
    return _records(code, abstract, periods)


def fetch_financial_indicators(code: str) -> dict[str, Any] | None:
    """取**最新报告期**的标准指标记录；无覆盖/失败返回 None。

    链路（``fetcher/chain.fetch_with_fallback``）的 provider 槽。
    """
    records = fetch_financial_indicator_history(code, limit=1)
    return records[0] if records else None
