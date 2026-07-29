"""组合综合费率估算 — 从 alignment_correction.py 提取的子模块。

根据持仓明细中的品种名称和代码，通过关键词规则识别基金类型，
按经验费率估算加权平均组合费率及年化费用金额。

保持纯函数设计 — 无 I/O、无配置读取、无报告层导入。
"""

from __future__ import annotations

from typing import Any


# ── 费率估算经验值 ──────────────────────────────
# 各类别年化费率（管理费 + 托管费，粗略估算）
_STOCK_FEE_RATE = 0.001  # 股票 ~0.1%
_BOND_FUND_FEE_RATE = 0.007  # 债券基金 ~0.7%
_MONEY_MARKET_FEE_RATE = 0.003  # 货币基金 ~0.3%
_EQUITY_FUND_FEE_RATE = 0.015  # 偏股基金 ~1.5%

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

    # 代码特征识别（通过 code_utils 中心化函数判断）
    code = code.strip().upper()
    from src.python.code_utils import is_a_share_code, is_hk_stock_code

    # A 股股票
    if is_a_share_code(code.lower()):
        return "stock", _STOCK_FEE_RATE
    # 港股 5 位数字
    if is_hk_stock_code(code):
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

        fee_breakdown.append(
            {
                "品种名称": name or code,
                "fee_rate": fee_rate,
                "weight": round(weight, 6),
                "contribution": round(contribution, 6),
            }
        )

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
    unknown_count = sum(1 for fd in fee_breakdown if fd.get("fee_rate") == _DEFAULT_FEE_RATE)
    warning = None
    if unknown_count > 0:
        warning = (
            f"有 {unknown_count} 个品种未能识别具体类型，使用默认费率 {_DEFAULT_FEE_RATE * 100:.1f}%，"
            "估算结果可能偏差较大"
        )

    return {
        "has_data": True,
        "fee_rate": round(fee_rate, 6),
        "annual_fee": round(annual_fee, 2),
        "fee_breakdown": fee_breakdown,
        "warning": warning,
    }
