"""口径修正因子计算 — 组合与基准对标前的三项修正。

为使组合收益与基准指数实现公平对比，需对组合口径进行三项修正：
  1. 组合综合费率估算（portfolio_fee_estimation）：加权平均管理费 + 托管费
  2. 现金剥离（cash_stripping）：分离货币基金/现金管理品种，仅对比权益部分
  3. TWR 计算（true_time_weighted_return）：时间加权收益率，消除现金流干扰

严格保持与 report/ 层无依赖（analysis 层约束）。
纯函数设计 — 无 I/O、无配置读取、无报告层导入。
"""

from __future__ import annotations

import math
from typing import Any

# ── 费率估算经验值 ──────────────────────────────
# 各类别年化费率（管理费 + 托管费，粗略估算）
_STOCK_FEE_RATE = 0.001      # 股票 ~0.1%
_BOND_FUND_FEE_RATE = 0.007  # 债券基金 ~0.7%
_MONEY_MARKET_FEE_RATE = 0.003  # 货币基金 ~0.3%
_EQUITY_FUND_FEE_RATE = 0.015   # 偏股基金 ~1.5%

# 基金类型关键词规则（用于 match_fund_type）
_FUND_TYPE_RULES: list[tuple[tuple[str, ...], str, float]] = [
    (("货币", "现金管理", "短债", "理财", "余额宝"), "money_market", _MONEY_MARKET_FEE_RATE),
    (("纯债", "债券", "中短债", "利率债", "信用债"), "bond", _BOND_FUND_FEE_RATE),
    (("指数", "ETF联接", "增强", "沪深300", "中证500", "科创50"), "equity_index", _EQUITY_FUND_FEE_RATE),
    (("股票", "混合", "成长", "价值", "精选", "优质"), "equity", _EQUITY_FUND_FEE_RATE),
    (("医药", "医疗", "消费", "科技", "新能源", "半导体", "军工"), "equity_sector", _EQUITY_FUND_FEE_RATE),
    (("QDII", "海外", "全球", "美股", "港股", "纳斯达克", "标普"), "equity_qdii", _EQUITY_FUND_FEE_RATE),
]

# 未知类型默认费率
_DEFAULT_FEE_RATE = 0.010  # 默认 1.0%

# 费率估算数据充分性阈值（持仓品种数低于此值视为"品种过少"）
_MIN_HOLDINGS_FOR_FEE_ESTIMATION = 1

# ── TWR 计算常量 ────────────────────────────────
_TRADING_DAYS_PER_YEAR = 252


def _classify_fund_type(name: str, code: str) -> tuple[str, float]:
    """根据品种名称和代码判断基金类型，返回 (类型标签, 估算费率)。

    Args:
        name: 品种名称
        code: 品种代码

    Returns:
        (type_label, fee_rate) 元组
    """
    # 规则匹配：按名称关键词
    for keywords, type_label, fee_rate in _FUND_TYPE_RULES:
        if any(kw in name for kw in keywords):
            return type_label, fee_rate

    # 代码特征识别
    code = code.strip().upper()
    # 股票代码：6 位纯数字且不以 00/60/30 且非基金代码
    # A 股股票
    if code.startswith(("SH", "SZ", "BJ")):
        code_stripped = code[2:]
        if code_stripped.isdigit() and len(code_stripped) == 6:
            return "stock", _STOCK_FEE_RATE
    # 纯数字 6 位 A 股代码
    if code.isdigit() and len(code) == 6 and not code.startswith(("00", "60", "30")):
        return "stock", _STOCK_FEE_RATE

    # 港股 5 位数字
    if code.isdigit() and len(code) == 5:
        return "stock", _STOCK_FEE_RATE

    # 美股：字母为主
    if code.isalpha() or (code.isalnum() and not code.isdigit()):
        return "stock", _STOCK_FEE_RATE

    # 无法识别 → 默认
    return "unknown", _DEFAULT_FEE_RATE


def portfolio_fee_estimation(
    holdings_details: list[dict],
    total_mv: float,
) -> dict[str, Any]:
    """组合综合费率估算。

    根据持仓明细中的品种名称和代码，通过关键词规则识别基金类型，
    按经验费率估算加权平均组合费率及年化费用金额。

    Args:
        holdings_details: 持仓明细列表，每项为 dict，至少包含：
            - name: 品种名称
            - code: 品种代码
            - market_value: 市值（元）
            可选字段：cost（成本）、份额、类型等，不影响费率估算。
        total_mv: 组合总市值（元）

    Returns:
        {
            "has_data": bool,         # 持仓数据是否充分
            "fee_rate": float | None, # 加权平均费率（如 0.0123 表示 1.23%）
            "annual_fee": float | None, # 年化费用金额（元）
            "fee_breakdown": [        # 各品种费率明细
                {
                    "品种名称": str,
                    "fee_rate": float,
                    "weight": float,   # 该品种在组合中权重（0~1）
                    "contribution": float, # 该品种对总费率的贡献占比（0~1）
                },
                ...
            ],
            "warning": str | None,    # 数据不足提示
        }
    """
    if not holdings_details or total_mv <= 0:
        return {
            "has_data": False,
            "fee_rate": None,
            "annual_fee": None,
            "fee_breakdown": [],
            "warning": "持仓数据不足，无法估算组合综合费率",
        }

    if len(holdings_details) < _MIN_HOLDINGS_FOR_FEE_ESTIMATION:
        return {
            "has_data": False,
            "fee_rate": None,
            "annual_fee": None,
            "fee_breakdown": [],
            "warning": f"持仓品种数过少（{len(holdings_details)} 个），费率估算参考价值有限",
        }

    fee_breakdown: list[dict[str, Any]] = []
    total_weighted_fee = 0.0

    for h in holdings_details:
        name = h.get("name", "")
        code = h.get("code", "")
        mv = h.get("market_value", 0.0)

        if mv is None or mv <= 0:
            continue

        type_label, fee_rate = _classify_fund_type(name, code)
        weight = mv / total_mv
        contribution = weight * fee_rate
        total_weighted_fee += contribution

        fee_breakdown.append({
            "品种名称": name or code,
            "fee_rate": fee_rate,
            "weight": round(weight, 6),
            "contribution": round(contribution, 6),
        })

    if not fee_breakdown or total_mv <= 0:
        return {
            "has_data": False,
            "fee_rate": None,
            "annual_fee": None,
            "fee_breakdown": [],
            "warning": "所有品种市值均为零，无法估算费率",
        }

    fee_rate = total_weighted_fee
    annual_fee = total_mv * fee_rate

    # 检查是否有较多未知类型品种
    unknown_count = sum(
        1 for fd in fee_breakdown
        if fd.get("fee_rate") == _DEFAULT_FEE_RATE
    )
    warning = None
    if unknown_count > 0:
        warning = (
            f"有 {unknown_count} 个品种未能识别具体类型，使用默认费率 {_DEFAULT_FEE_RATE*100:.1f}%，"
            "估算结果可能偏差较大"
        )

    return {
        "has_data": True,
        "fee_rate": round(fee_rate, 6),
        "annual_fee": round(annual_fee, 2),
        "fee_breakdown": fee_breakdown,
        "warning": warning,
    }


def cash_stripping(
    holdings_details: list[dict],
    portfolio_daily_returns: list[float] | None = None,
    total_mv: float = 0.0,
) -> dict[str, Any]:
    """现金剥离：识别并分离货币基金/现金管理品种贡献。

    货币基金/现金管理品种的波动特征与权益类资产差异极大，
    在组合与基准对标时，有必要将其从权益部分剥离，以反映
    真实的权益投资表现。

    Args:
        holdings_details: 持仓明细列表，每项为 dict，至少包含：
            - name: 品种名称
            - code: 品种代码
            - market_value: 市值（元）
        portfolio_daily_returns: 组合日收益率序列（可选），
            用于计算剥离后的权益部分收益率。为 None 时不计算收益率。
        total_mv: 组合总市值（元）。若为 0 或未提供，则从 holdings_details 求和。

    Returns:
        {
            "has_data": bool,               # 持仓数据是否充分
            "cash_allocation_pct": float,   # 现金管理品种占比（0~1）
            "equity_allocation_pct": float, # 权益部分占比（0~1）
            "cash_holdings": [              # 识别出的现金管理品种列表
                {"name": str, "code": str, "market_value": float},
                ...
            ],
            "stripped_return_pct": float | None, # 剥离后权益部分收益率（%），
                                                  # 无日收益数据时为 None
            "warning": str | None,
        }
    """
    if not holdings_details:
        return {
            "has_data": False,
            "cash_allocation_pct": 0.0,
            "equity_allocation_pct": 0.0,
            "cash_holdings": [],
            "stripped_return_pct": None,
            "warning": "持仓数据不足，无法进行现金剥离分析",
        }

    # 确定组合总市值
    if total_mv <= 0:
        total_mv = sum(h.get("market_value", 0.0) or 0.0 for h in holdings_details)

    if total_mv <= 0:
        return {
            "has_data": False,
            "cash_allocation_pct": 0.0,
            "equity_allocation_pct": 0.0,
            "cash_holdings": [],
            "stripped_return_pct": None,
            "warning": "组合总市值为零，无法进行现金剥离分析",
        }

    # 识别现金管理品种
    cash_keywords = ("货币", "现金管理", "短债", "理财", "余额宝", "银华日利", "华宝添益")
    cash_holdings: list[dict[str, Any]] = []
    equity_mv = 0.0
    cash_mv = 0.0

    for h in holdings_details:
        name = h.get("name", "")
        code = str(h.get("code", ""))
        mv = h.get("market_value", 0.0) or 0.0

        is_cash = any(kw in name for kw in cash_keywords)
        # 额外按基金类型规则中的货币基金判定
        if not is_cash:
            type_label, _ = _classify_fund_type(name, code)
            if type_label == "money_market":
                is_cash = True

        if is_cash:
            cash_mv += mv
            cash_holdings.append({
                "name": name or code,
                "code": code,
                "market_value": round(mv, 2),
            })
        else:
            equity_mv += mv

    cash_allocation_pct = cash_mv / total_mv if total_mv > 0 else 0.0
    equity_allocation_pct = equity_mv / total_mv if total_mv > 0 else 0.0

    # 计算剥离后权益部分收益率（若有日收益数据）
    # 简化模型：组合收益率 = w_cash × r_cash + w_equity × r_equity
    # 从而：r_equity = (组合收益率 - w_cash × r_cash) / w_equity
    stripped_return_pct = None
    if portfolio_daily_returns is not None and len(portfolio_daily_returns) > 0:
        if equity_allocation_pct > 0 and cash_allocation_pct > 0:
            # 假设现金管理品种日收益率 ≈ 0
            # 则：剥离后收益 ≈ 组合收益 / equity_allocation_pct
            # 为防止除零，先计算累计组合收益率
            cum_portfolio_return = 1.0
            for r in portfolio_daily_returns:
                cum_portfolio_return *= (1.0 + r)
            total_return_pct = cum_portfolio_return - 1.0
            stripped_return_pct = total_return_pct / equity_allocation_pct if equity_allocation_pct > 0 else None
        elif equity_allocation_pct == 1.0:
            # 无现金品种，直接使用组合收益率
            cum_return = 1.0
            for r in portfolio_daily_returns:
                cum_return *= (1.0 + r)
            stripped_return_pct = cum_return - 1.0

    warning = None
    if cash_allocation_pct == 0:
        warning = "未识别出现金管理品种，无需现金剥离"
    elif cash_allocation_pct < 0.05:
        warning = f"现金管理品种占比仅 {cash_allocation_pct*100:.1f}%，剥离影响有限"
    if portfolio_daily_returns is None or len(portfolio_daily_returns) == 0:
        warning = (
            (warning + "；" if warning else "")
            + "无日收益率数据，无法计算剥离后收益率"
        )
        stripped_return_pct = None

    return {
        "has_data": True,
        "cash_allocation_pct": round(cash_allocation_pct, 6),
        "equity_allocation_pct": round(equity_allocation_pct, 6),
        "cash_holdings": cash_holdings,
        "stripped_return_pct": round(stripped_return_pct, 6) if stripped_return_pct is not None else None,
        "warning": warning or None,
    }


def twr_calculation(
    snapshots: list[dict],
) -> dict[str, Any]:
    """时间加权收益率计算。

    使用链接公式：(1+r1)×(1+r2)×...−1 计算时间加权收益率（TWR），
    消除现金流进出对收益率计算的影响。

    Args:
        snapshots: 快照序列，每项为 dict，至少包含：
            - value: 期末市值（元）
            - cash_flow: 期内现金流（正=流入，负=流出，0=无现金流）
            快照应按时间顺序排列。

    Returns:
        {
            "has_data": bool,
            "twr": float | None,         # TWR 比率（如 0.05 表示 5%）
            "n_periods": int,            # 期间数
            "annualized_twr": float | None, # 年化 TWR（<1 年则 None）
            "warning": str | None,
        }
    """
    if not snapshots or len(snapshots) < 1:
        return {
            "has_data": False,
            "twr": None,
            "n_periods": 0,
            "annualized_twr": None,
            "warning": "快照数据不足，无法计算时间加权收益率",
        }

    # 单个快照：无法计算期间收益率，回退为简单收益率
    if len(snapshots) == 1:
        s = snapshots[0]
        value = s.get("value", 0.0)
        cash_flow = s.get("cash_flow", 0.0)
        # 简单收益率 = (期末市值 - 期初市值 - 现金流) / 期初市值
        # 但仅有一个快照时，无期初值，只能回退为 0
        return {
            "has_data": True,
            "twr": 0.0,
            "n_periods": 1,
            "annualized_twr": None,
            "warning": "仅有单个快照，无法计算时间加权收益率，返回 0",
        }

    # 逐期计算子期间收益率：r_i = (V_i - CF_i) / V_{i-1} - 1
    # 其中 V_i 为期末市值，CF_i 为期内现金流，V_{i-1} 为前期期末市值
    twr_product = 1.0
    valid_periods = 0

    for i in range(1, len(snapshots)):
        prev_value = snapshots[i - 1].get("value", 0.0)
        curr_value = snapshots[i].get("value", 0.0)
        cash_flow = snapshots[i].get("cash_flow", 0.0)

        if prev_value <= 0 or curr_value is None or curr_value <= 0:
            # 跳过无效期间
            continue

        # 子期间收益率 = (期末市值 - 现金流) / 期初市值 - 1
        sub_period_return = (curr_value - cash_flow) / prev_value - 1.0
        twr_product *= (1.0 + sub_period_return)
        valid_periods += 1

    if valid_periods == 0:
        return {
            "has_data": False,
            "twr": None,
            "n_periods": 0,
            "annualized_twr": None,
            "warning": "无有效期间用于计算时间加权收益率（市值数据无效）",
        }

    twr = twr_product - 1.0

    # 年化 TWR：仅当期间数 >= 252（约一年日数据）时计算
    annualized_twr = None
    if valid_periods >= _TRADING_DAYS_PER_YEAR:
        annualized_twr = twr_product ** (_TRADING_DAYS_PER_YEAR / valid_periods) - 1.0

    warning = None
    if valid_periods < 2:
        warning = "有效期间数过少，TWR 可能不稳定"
    elif valid_periods < _TRADING_DAYS_PER_YEAR:
        warning = (
            f"数据覆盖 {valid_periods} 个交易日（不足一年），"
            "未计算年化 TWR"
        )

    return {
        "has_data": True,
        "twr": round(twr, 6),
        "n_periods": valid_periods,
        "annualized_twr": round(annualized_twr, 6) if annualized_twr is not None else None,
        "warning": warning,
    }


def compute_alignment_factors(
    holdings_details: list[dict],
    total_mv: float,
    portfolio_daily_returns: list[float] | None = None,
    snapshots: list[dict] | None = None,
) -> dict[str, Any]:
    """组合校准因子入口函数。

    整合费率估算、现金剥离、TWR 计算三项修正因子为统一输出，
    并生成供 LLM 使用的文本摘要。

    Args:
        holdings_details: 持仓明细列表
        total_mv: 组合总市值（元）
        portfolio_daily_returns: 组合日收益率序列（可选）
        snapshots: 组合市值快照序列（可选）

    Returns:
        {
            "has_data": bool,
            "fee_estimation": dict,  # portfolio_fee_estimation 输出
            "cash_stripping": dict,  # cash_stripping 输出
            "twr": dict,             # twr_calculation 输出
            "has_any_data": bool,    # 至少有一项有数据
            "summary_text": str,     # 供 LLM 使用的文本描述
        }
    """
    fee_result = portfolio_fee_estimation(holdings_details, total_mv)
    cash_result = cash_stripping(holdings_details, portfolio_daily_returns, total_mv)

    twr_result: dict[str, Any]
    if snapshots is not None and len(snapshots) > 0:
        twr_result = twr_calculation(snapshots)
    else:
        twr_result = {
            "has_data": False,
            "twr": None,
            "n_periods": 0,
            "annualized_twr": None,
            "warning": "未提供快照数据，未计算 TWR",
        }

    has_any_data = fee_result.get("has_data", False) or cash_result.get("has_data", False) or twr_result.get("has_data", False)

    # 构建摘要文本
    parts: list[str] = []
    parts.append("【组合校准修正因子】")

    # 费率摘要
    if fee_result.get("has_data"):
        fee_rate = fee_result["fee_rate"]
        annual_fee = fee_result["annual_fee"]
        parts.append(
            f"综合费率估算：加权平均费率 {fee_rate*100:.2f}%，"
            f"年化费用约 {annual_fee:.2f} 元"
        )
    else:
        fee_warn = fee_result.get("warning", "数据不足")
        parts.append(f"费率估算：{fee_warn}")

    # 现金剥离摘要
    if cash_result.get("has_data"):
        cash_pct = cash_result.get("cash_allocation_pct", 0.0) * 100
        equity_pct = cash_result.get("equity_allocation_pct", 0.0) * 100
        stripped_ret = cash_result.get("stripped_return_pct")
        parts.append(
            f"现金剥离：现金管理品种占比 {cash_pct:.2f}%，"
            f"权益部分占比 {equity_pct:.2f}%"
        )
        if stripped_ret is not None:
            parts.append(f"剥离后权益收益率：{stripped_ret*100:.2f}%")
    else:
        cash_warn = cash_result.get("warning", "数据不足")
        parts.append(f"现金剥离：{cash_warn}")

    # TWR 摘要
    if twr_result.get("has_data"):
        twr = twr_result.get("twr", 0.0)
        n_periods = twr_result.get("n_periods", 0)
        annualized = twr_result.get("annualized_twr")
        parts.append(
            f"时间加权收益率（TWR）：{twr*100:.2f}%（{n_periods} 个期间）"
        )
        if annualized is not None:
            parts.append(f"年化 TWR：{annualized*100:.2f}%")
    else:
        twr_warn = twr_result.get("warning", "未计算")
        parts.append(f"时间加权收益率：{twr_warn}")

    summary_text = "\n".join(parts)

    return {
        "has_data": has_any_data,
        "fee_estimation": fee_result,
        "cash_stripping": cash_result,
        "twr": twr_result,
        "has_any_data": has_any_data,
        "summary_text": summary_text,
    }


__all__ = [
    "portfolio_fee_estimation",
    "cash_stripping",
    "twr_calculation",
    "compute_alignment_factors",
]
