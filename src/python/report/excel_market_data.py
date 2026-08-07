"""行情市值与指数数据解析模块。

职责：市场行情数据获取/复用 + 指数数据获取/复用。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from src.python.core.logger import setup_logger
from src.python.core.registry import get_report_sheet_name
from src.python.report.progress import ProgressReporter, Timer

logger = setup_logger()


def _resolve_holdings_start_date() -> _dt.date | None:
    """读取可选的组合建仓日期（config.json → holdings_start_date，YYYY-MM-DD）。

    仅用于成本流水子模块的快照近似（单笔建仓假设的年化计算）。未配置或
    格式无效返回 None（近似年化不计算，仅输出成本分档）。

    Returns:
        建仓日期，或 None（未配置 / 空 / 格式无效）
    """
    from src.python.config import get_config

    raw = get_config().get("holdings_start_date") or ""
    text = str(raw).strip()
    if not text:
        return None
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        logger.warning("holdings_start_date 配置格式无效（应为 YYYY-MM-DD）: %r，忽略近似年化", text)
        return None


def _build_flow_data(
    enable_cost_lots: bool,
    transactions: list | None,
    dividends: list | None,
    holdings: list,
    details: list,
) -> dict | None:
    """组装成本流水数据（fund_flow_data）。

    仅当开关开启时计算（成本分档 + XIRR + 分红累计）；开关关闭时返回
    None（汇总/市值/分类页签保持既有输出）。市价取自身份验证后的行情明细。

    Args:
        enable_cost_lots: 成本流水子模块开关
        transactions: 交易流水记录（无则 None）
        dividends: 分红流水记录（无则 None）
        holdings: 当前持仓
        details: 市值核算明细（提供品种代码 → 当前市价）

    Returns:
        fund_flow_data dict（无流水时为快照近似契约 approximate=True；
        有流水时为真实契约 approximate=False），或 None（开关关闭）
    """
    if not enable_cost_lots:
        return None
    from src.python.analysis.cost_flow import build_approximate_fund_flow_data, build_fund_flow_data

    current_prices = {d.code: d.price for d in details if getattr(d, "price", None)}
    if not transactions and not dividends:
        # 无流水页签：返回快照近似契约（成本分档单档判断 + 可选近似年化），
        # 供渲染层写「可选进阶增强」说明；开关开启但零持仓时近似也仅占位契约。
        start_date = _resolve_holdings_start_date()
        return build_approximate_fund_flow_data(holdings, current_prices, start_date=start_date)
    return build_fund_flow_data(transactions or [], dividends or [], holdings, current_prices)


def resolve_market_data(
    holdings: list,
    details: list | None,
    modules: dict[str, Any],
    ws2: Any,
    prog: ProgressReporter,
    enable_cost_lots: bool = False,
    transactions: list | None = None,
    dividends: list | None = None,
) -> dict[str, Any]:
    """行情市值页写入，返回核心数据字典。"""
    mvs = modules.get("write_market_value_sheet")
    classify = modules.get("classify_holdings")

    if mvs is None:
        data = {
            "total_mv": 0.0,
            "total_cost": 0.0,
            "total_profit": 0.0,
            "today_profit": 0.0,
            "details": details or [],
            "categories": {},
            "update_status": (0, 0, True),
            "fund_flow_data": None,
        }
        prog.add_error("行情市值模块缺失，跳过 Sheet 2")
    elif details is not None:
        logger.info("复用外部传入的市值核算数据，共 %d 条", len(details))
        data = {
            "total_mv": sum(d.market_value for d in details),
            "total_cost": sum(d.cost for d in details),
            "total_profit": sum(d.profit for d in details),
            "today_profit": sum(d.today_profit for d in details),
            "details": details,
        }
        fund_flow_data = _build_flow_data(enable_cost_lots, transactions, dividends, holdings, details)
        data["fund_flow_data"] = fund_flow_data
        with Timer(get_report_sheet_name("market_value")):
            mvs(ws2, holdings, details=details, fund_flow_data=fund_flow_data)
    else:
        with Timer("行情数据获取 (" + get_report_sheet_name("market_value") + ")"):
            prog.info("正在获取行情数据（首次耗时较长，后续使用缓存）...")
            gen_details = modules.get("_generate_details")
            details = gen_details(holdings) if gen_details else []
            total_mv = sum(d.market_value for d in details)
            total_cost = sum(d.cost for d in details)
            total_profit = sum(d.profit for d in details)
            today_profit = sum(d.today_profit for d in details)
            fund_flow_data = _build_flow_data(enable_cost_lots, transactions, dividends, holdings, details)
            mvs(ws2, holdings, details=details, fund_flow_data=fund_flow_data)
            data = {
                "total_mv": total_mv,
                "total_cost": total_cost,
                "total_profit": total_profit,
                "today_profit": today_profit,
                "details": details,
                "fund_flow_data": fund_flow_data,
            }
        prog.ok("行情数据获取完成")

    data["categories"] = classify(holdings) if classify else {}

    _mkt_all_zero = data["total_mv"] == 0 and data["total_cost"] > 0
    if _mkt_all_zero:
        prog.add_error("行情数据全部不可用（非交易时段/网络异常），报告部分数据为占位显示")
    _price_fn = modules.get("price_update_status")
    _last_trading_fn = modules.get("get_last_trading_day")
    if _price_fn is not None and _last_trading_fn is not None:
        data["update_status"] = _price_fn(data["details"], _last_trading_fn())
    else:
        data["update_status"] = (0, 0, True)
    return data


def resolve_indices(
    a_indices: dict | None,
    us_indices: dict | None,
    modules: dict[str, Any],
    prog: ProgressReporter,
) -> tuple[dict, dict]:
    """获取市场指数（外部传入时复用）。"""
    if a_indices is not None:
        return a_indices, us_indices if us_indices is not None else {}
    with Timer("市场指数 (" + get_report_sheet_name("summary") + ")"):
        prog.info("正在获取市场指数...")
        a_idx = modules.get("fetch_indices", lambda: {})()
        us_idx = modules.get("fetch_us_indices", lambda: {})() if us_indices is None else (us_indices or {})
        prog.ok("市场指数获取完成")
    return a_idx, us_idx
