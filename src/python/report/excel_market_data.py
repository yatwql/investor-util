"""行情市值与指数数据解析模块。

职责：市场行情数据获取/复用 + 指数数据获取/复用。
提取自 excel_generator.py 的 _resolve_market_data + _resolve_indices。
"""

from __future__ import annotations

from typing import Any

from src.python.logger import setup_logger
from src.python.registry import get_report_sheet_name
from src.python.report.progress import ProgressReporter, _Timer

logger = setup_logger()


def resolve_market_data(
    holdings: list, details: list | None,
    modules: dict[str, Any], ws2: Any, prog: ProgressReporter,
) -> dict[str, Any]:
    """行情市值页写入，返回核心数据字典。"""
    mvs = modules.get("write_market_value_sheet")
    classify = modules.get("classify_holdings")

    if mvs is None:
        data = {"total_mv": 0.0, "total_cost": 0.0, "total_profit": 0.0,
                "today_profit": 0.0, "details": details or [],
                "categories": {}, "update_status": (0, 0, True)}
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
        with _Timer(get_report_sheet_name("market_value")):
            mvs(ws2, holdings, details=details)
    else:
        with _Timer("行情数据获取 (" + get_report_sheet_name("market_value") + ")"):
            prog.info("正在获取行情数据（首次耗时较长，后续使用缓存）...")
            gen_details = modules.get("_generate_details")
            details = gen_details(holdings) if gen_details else []
            total_mv = sum(d.market_value for d in details)
            total_cost = sum(d.cost for d in details)
            total_profit = sum(d.profit for d in details)
            today_profit = sum(d.today_profit for d in details)
            mvs(ws2, holdings, details=details)
            data = {
                "total_mv": total_mv, "total_cost": total_cost,
                "total_profit": total_profit, "today_profit": today_profit,
                "details": details,
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
    a_indices: dict | None, us_indices: dict | None,
    modules: dict[str, Any], prog: ProgressReporter,
) -> tuple[dict, dict]:
    """获取市场指数（外部传入时复用）。"""
    if a_indices is not None:
        return a_indices, us_indices if us_indices is not None else {}
    with _Timer("市场指数 (" + get_report_sheet_name("summary") + ")"):
        prog.info("正在获取市场指数...")
        a_idx = modules.get("fetch_indices", lambda: {})()
        us_idx = modules.get("fetch_us_indices", lambda: {})() if us_indices is None else (us_indices or {})
        prog.ok("市场指数获取完成")
    return a_idx, us_idx
