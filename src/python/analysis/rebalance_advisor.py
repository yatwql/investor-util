"""调仓建议可行化层 — 将再平衡/纪律触发信号落地为可执行调仓清单。

纯计算层：仅消费调用方传入的信号与持仓明细，禁止导入 report/ 包，
保持与报告层的完全解耦。

把「触发建议」转成「能照做的方案」：每条建议输出
代码 / 名称 / 操作 / 份额（A 股取整一手 100 股）/ 金额 / 预估费用 / 调仓后现金余额。

渠道上下文：持仓明细可携带 channel（"场外"/"场内"），由报告层按账户关键词
判定填充（如"基金账户/支付宝"判为场外渠道）。本层消费渠道时：
  - channel="场外" → 场外基金处理（整数份取整 + 计收赎回费），覆盖 16/11 开头
    代码命中场内前缀而被误判的场外持有场景（LOF/开放式指数基金）
  - 非场外 → 回退证券类型判定（A 股印花税 / 场内基金仅佣金 / 100 份取整），
    避免用单一渠道覆盖 A 股印花税等差异化费率
  显式 channel 优先，其次按 account 关键词判定（is_offsite_fund），
  两者皆无时保持既有代码/名称判定（向后兼容）。

份额取整的证券类型判定复用 core/code_utils.py（代码类型判定中心化）
（is_a_share_code / is_exchange_fund_code / is_otc_fund_by_name），
本模块不自建证券类型判定逻辑。

费用估算（本地静态费率表，单位：元）：
  - 佣金：max(金额 × 佣金费率, 最低佣金)（按笔收取）
  - 印花税：仅 A 股卖出计收（金额 × 印花税率）
  - 赎回费：仅场外基金卖出计收（金额 × 赎回费率）
  费率表可通过 fee_table 覆盖（测试用固定 fixture 断言计算精度），
  生产环境使用默认静态费率。

现金缓冲：从 available_cash 起按执行顺序逐条累计卖出净额（金额 - 费用），
任一条建议执行后现金为负则剔除该条（现金负值防护，避免透支调仓）。

优先级：止损 > 部分止盈 > 卖出减仓；同一品种触发多条时保留优先级最高的一条。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.code_utils import (
    is_a_share_code,
    is_exchange_fund_code,
    is_offsite_fund,
    is_otc_fund_by_name,
)

logger = logging.getLogger("invest")

__all__ = ["build_rebalance_advice", "estimate_fee"]

# 默认静态费率表（估算用）
_DEFAULT_FEE_TABLE: dict[str, float] = {
    "commission_rate": 0.00025,  # 佣金费率（万 2.5，按笔收取）
    "min_commission": 5.0,  # 最低佣金（元/笔）
    "stamp_duty_rate": 0.0005,  # 印花税（仅 A 股卖出，0.05%）
    "redemption_rate": 0.005,  # 场外基金赎回费（0.5%）
}

# 纪律触发后的卖出比例：止盈部分了结（1/3）、止损清仓（全部）
_TAKE_PROFIT_SELL_RATIO = 1 / 3
_STOP_LOSS_SELL_RATIO = 1.0

# 操作优先级：数值越小越优先执行
_PRIORITY: dict[str, int] = {
    "止损": 1,
    "部分止盈": 2,
    "卖出减仓": 3,
}

# 调仓建议支持的卖出方向操作（当前阶段仅卖出，费用估算按卖出口径计收印花税/赎回费）
_SELL_OPERATIONS = frozenset(_PRIORITY)


def _channel_of_holding(holding: dict[str, Any]) -> str:
    """持仓明细 → 渠道（"场外" / 空串）。

    显式 channel 字段优先（报告层契约已按账户判定填充）；兼容直接携带
    account 的调用（按场外账户关键词判定）；两者皆无返回空串，由取整/
    费用估算回退证券类型判定（向后兼容）。

    返回值语义："场外" = 按场外基金处理（整数份取整 + 赎回费）；非场外
    仍需区分 A 股（印花税）与场内基金（仅佣金），故此处不返回"场内"。

    Args:
        holding: 持仓明细单行（含可选 channel/account）

    Returns:
        "场外" 表示场外渠道，空串表示无渠道上下文。
    """
    ch = (holding.get("channel") or "").strip()
    if ch == "场外":
        return "场外"
    account = (holding.get("account") or "").strip()
    if account and is_offsite_fund(account):
        return "场外"
    return ""


def _round_to_lot(raw_shares: float, code: str, name: str, channel: str = "") -> int:
    """份额取整到一手（证券类型判定复用 core/code_utils.py）。

    A 股与场内基金/ETF 按一手 100 份向下取整；场外基金与港股按整数份取整
    （一手股数随标的不同，取整到整数份）。channel="场外" 时强制按整数份
    取整，覆盖 16/11 开头代码命中场内前缀的场外持有场景。

    Args:
        raw_shares: 未取整的目标卖出份额
        code: 证券代码
        name: 证券名称（场外基金判定需要）
        channel: 渠道上下文（"场外" 强制整数份取整；空串回退证券类型判定）

    Returns:
        取整后的可执行份额；不足一手时为 0。
    """
    name = name or ""  # 名称缺失时按非场外基金处理，避免 None 匹配异常
    raw = int(raw_shares)
    if raw <= 0:
        return 0
    if channel == "场外":
        return raw
    # 场外基金判定优先：00 代码与深市主板区间重叠，需先经名称关键词排除
    if is_otc_fund_by_name(name, code):
        return raw
    if is_a_share_code(code) or is_exchange_fund_code(code):
        return (raw // 100) * 100
    return raw


def estimate_fee(
    operation: str,
    amount: float,
    code: str,
    name: str = "",
    fee_table: dict[str, float] | None = None,
    channel: str = "",
) -> float:
    """估算调仓交易费用（佣金 + 印花税/赎回费，本地静态费率表）。

    Args:
        operation: 操作（卖出减仓 / 部分止盈 / 止损，当前调仓建议均为卖出方向）
        amount: 交易金额（元）
        code: 证券代码
        name: 证券名称（场外基金判定需要）
        fee_table: 费率表覆盖（测试用固定 fixture；None 用默认静态费率）
        channel: 渠道上下文（"场外" 计收赎回费，覆盖 16/11 开头代码的前缀误判；
            空串回退证券类型判定）

    Returns:
        预估费用（元，两位小数）。印花税仅 A 股卖出计收、赎回费仅场外基金卖出计收，
        场内基金/ETF 与港股仅计佣金。
    """
    if operation not in _SELL_OPERATIONS:
        raise ValueError(f"调仓建议仅支持卖出方向操作，收到未知操作：{operation}")
    name = name or ""  # 名称缺失时按非场外基金处理，避免 None 匹配异常
    fees = {**_DEFAULT_FEE_TABLE, **(fee_table or {})}
    commission = max(amount * fees["commission_rate"], fees["min_commission"])
    total = commission
    # 场外渠道优先：覆盖 16/11 开头代码命中场内前缀的场外持有场景（如 161725/110022）
    if channel == "场外":
        total += amount * fees["redemption_rate"]
    # 场外基金判定优先：00 代码与深市主板区间重叠，需先经名称关键词排除
    elif is_otc_fund_by_name(name, code):
        total += amount * fees["redemption_rate"]
    elif is_a_share_code(code):
        total += amount * fees["stamp_duty_rate"]
    return round(total, 2)


def _candidate_from_rebalance(
    signal: dict[str, Any],
    holding: dict[str, Any],
    total_mv: float,
) -> dict[str, Any] | None:
    """再平衡信号 → 待执行候选（卖出超出警戒线部分市值对应的份额）。

    Args:
        signal: 再平衡信号（含 code/name/weight/threshold）
        holding: 对应持仓明细（含 price/market_value）
        total_mv: 持仓总市值

    Returns:
        候选 dict（含 raw_shares/price/operation），无可执行部分或数据缺失时返回 None。
    """
    code = signal.get("code") or ""
    if not code:
        return None
    price = holding.get("price", 0) or 0
    if price <= 0:
        return None
    threshold = signal.get("threshold", 0) or 0
    excess_mv = holding.get("market_value", 0) - threshold * total_mv
    if excess_mv <= 0:
        return None
    return {
        "code": code,
        "name": signal.get("name") or holding.get("name", ""),
        "operation": "卖出减仓",
        "raw_shares": excess_mv / price,
        "price": price,
        "channel": _channel_of_holding(holding),
    }


def _candidate_from_discipline(
    signal: dict[str, Any],
    holding: dict[str, Any],
) -> dict[str, Any] | None:
    """纪律触发信号 → 待执行候选（止盈部分了结、止损清仓）。

    Args:
        signal: 纪律信号（含 code/name/action）
        holding: 对应持仓明细（含 shares/price）

    Returns:
        候选 dict，组合级信号（code 为空）或数据缺失时返回 None。
    """
    code = signal.get("code") or ""
    if not code:
        # 组合级信号（如回撤）无可对应的单品订单，跳过
        return None
    price = holding.get("price", 0) or 0
    if price <= 0:
        return None
    action = signal.get("action") or ""
    shares = holding.get("shares", 0) or 0
    if "止损" in action:
        operation, ratio = "止损", _STOP_LOSS_SELL_RATIO
    elif "止盈" in action:
        operation, ratio = "部分止盈", _TAKE_PROFIT_SELL_RATIO
    else:
        return None
    return {
        "code": code,
        "name": signal.get("name") or holding.get("name", ""),
        "operation": operation,
        "raw_shares": shares * ratio,
        "price": price,
        "channel": _channel_of_holding(holding),
    }


def _upsert_candidate(candidates: dict[str, dict[str, Any]], cand: dict[str, Any]) -> None:
    """按代码去重：同一品种触发多条时保留优先级最高（数值最小）的一条。"""
    code = cand["code"]
    prev = candidates.get(code)
    if prev is None or _PRIORITY[cand["operation"]] < _PRIORITY[prev["operation"]]:
        candidates[code] = cand


def build_rebalance_advice(
    rebalance_signals: list[dict[str, Any]] | None,
    discipline_signals: list[dict[str, Any]] | None,
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    fee_table: dict[str, float] | None = None,
    available_cash: float = 0.0,
) -> list[dict[str, Any]]:
    """构建调仓建议清单（数据契约 `rebalance_advice`）。

    Args:
        rebalance_signals: 再平衡信号（单品占比超警戒线）
        discipline_signals: 交易纪律触发信号（止盈/止损）
        holdings_details: 持仓明细（含 shares/price/market_value/name/code；
            可选 channel 为场内/场外渠道上下文，由报告层按账户判定填充）
        total_mv: 持仓总市值
        fee_table: 费率表覆盖（None 用默认静态费率）
        available_cash: 调仓前可用现金（默认 0）

    Returns:
        建议清单，每条含 code/name/operation/shares/amount/fee/cash_after。
        按执行优先级排序；无触发或全部被守卫剔除时返回空列表。
    """
    if not holdings_details:
        return []
    holdings_by_code = {h.get("code", ""): h for h in holdings_details if h.get("code")}

    candidates: dict[str, dict[str, Any]] = {}
    for sig in rebalance_signals or []:
        cand = _candidate_from_rebalance(sig, holdings_by_code.get(sig.get("code", ""), {}), total_mv)
        if cand:
            _upsert_candidate(candidates, cand)
    for sig in discipline_signals or []:
        cand = _candidate_from_discipline(sig, holdings_by_code.get(sig.get("code", ""), {}))
        if cand:
            _upsert_candidate(candidates, cand)

    # 按优先级 + 卖出量降序确定执行顺序，再按该顺序逐条累计现金
    ordered = sorted(
        candidates.values(),
        key=lambda c: (_PRIORITY[c["operation"]], -c["raw_shares"]),
    )

    advice: list[dict[str, Any]] = []
    cash = available_cash
    for cand in ordered:
        shares = _round_to_lot(cand["raw_shares"], cand["code"], cand["name"], cand.get("channel", ""))
        if shares <= 0:
            continue
        amount = round(shares * cand["price"], 2)
        fee = estimate_fee(
            cand["operation"], amount, cand["code"], cand["name"], fee_table, channel=cand.get("channel", "")
        )
        cash_after = cash + amount - fee
        if cash_after < 0:
            # 现金负值防护：执行后现金为负的订单剔除，避免透支调仓
            continue
        cash = cash_after
        advice.append(
            {
                "code": cand["code"],
                "name": cand["name"],
                "operation": cand["operation"],
                "shares": shares,
                "amount": amount,
                "fee": fee,
                "cash_after": round(cash_after, 2),
            }
        )
    return advice
