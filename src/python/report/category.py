"""持仓分类模块。

按资产属性（股票/基金/债券/现金）和投资分类（主动/被动/固收等）分组，
统计各类的数量、市值、成本、盈亏、收益率和本日盈亏。
"""

from __future__ import annotations

import logging


from src.python.core.code_utils import (
    is_a_share_code,
    is_a_share_stock,
    is_bond_fund_by_name,
    is_etf_by_name_or_code,
    is_hk_stock_code,
    is_index_fund_by_name,
    is_money_fund_by_name,
    is_offsite_fund,
    is_otc_fund_by_name,
    is_qdii_extended,
)
from src.python.core.models import Holding
from src.python.core.num_utils import finite_or
from src.python.report.data_status import STATUS_MESSAGES, DataStatus, DataStatusItem

logger = logging.getLogger("invest")

_NCOLS = 10
_HEADERS = [
    "资产属性",
    "投资分类",
    "名称",
    "代码",
    "市值",
    "成本",
    "盈亏",
    "收益率",
    "本日盈亏",
    "年均股息率",
]
# 成本流水子列（功能开关 `cost_lots` 开启时追加，默认关不渲染）
_EXTRA_HEADERS = ["成本分档", "分红累计"]
_NCOLS_WITH_FLOW = _NCOLS + len(_EXTRA_HEADERS)


def _tier_label(buckets: dict | None) -> str:
    """成本分档标签：低成本/高成本/混合/未分档。

    档位口径同 analysis/cost_flow.compute_cost_tiers：批次成本价 ≤ 市价 →
    低成本档；> 市价 → 高成本档；无市价品种单列「未分档」。持仓批次横跨
    多档时按份额取主导档位（低==高 → 「混合」）。

    Args:
        buckets: cost_tiers.per_code 中某代码的分档桶 dict，缺码时为 None

    Returns:
        档位中文标签（无数据返回 "--"）
    """
    if not isinstance(buckets, dict):
        return "--"
    low = finite_or(buckets.get("low", {}).get("shares", 0.0))
    high = finite_or(buckets.get("high", {}).get("shares", 0.0))
    unpriced = finite_or(buckets.get("unpriced", {}).get("shares", 0.0))
    if unpriced > 0 and low == 0 and high == 0:
        return "未分档"
    if low == 0 and high == 0:
        return "--"
    if high > low:
        return "高成本"
    if low > high:
        return "低成本"
    return "混合"


# ── 分类映射规则 ──────────────────────────────────────────

# 分类关键词统一定义于 code_utils.py：


def _categorize_holding(h: Holding) -> tuple[str, str]:
    """将单条持仓映射到 (资产属性, 投资分类)。

    分类逻辑（按优先级）：
      1. QDII（名称含 QDII）→ 基金 / QDII
      2. 名称含固收关键词 → 债券 / 纯债
      3. 名称含货币关键词 → 现金 / 货币
      4. 场外渠道且名称含指数关键词 → 基金 / 被动
      5. 场外渠道 → 基金 / 主动
      6. 场内ETF（名称含ETF或代码5/1开头）→ 基金 / 指数
      7. 场内股票（代码6/0/3开头）→ 股票 / A股
      8. 其余 → 基金 / 混合

    Args:
        h: 持仓记录

    Returns:
        (资产属性, 投资分类)
    """
    name = h.name.strip()
    code = h.code.strip()
    account = h.account.strip()

    # 1) QDII
    if is_qdii_extended(name):
        return ("基金", "QDII")

    # 2) 固收类
    if is_bond_fund_by_name(name):
        return ("债券", "纯债")

    # 3) 货币类
    if is_money_fund_by_name(name):
        return ("现金", "货币")

    # 4) 场外渠道
    if is_offsite_fund(account):
        if is_index_fund_by_name(name):
            return ("基金", "被动")
        return ("基金", "主动")

    # 5) 场内 ETF（名称含ETF或代码5/1开头）
    if is_etf_by_name_or_code(name, code):
        return ("基金", "指数")

    # 5b) 00 代码场外基金（名称匹配基金特征，与 A 股 00 前缀重叠区）
    if is_otc_fund_by_name(name, code):
        return ("基金", "混合")

    # 6) 场内股票（A股或港股通）
    if is_a_share_code(code) or is_hk_stock_code(code):
        return ("股票", "A股")

    # 7) 其余归为基金/混合
    return ("基金", "混合")


def _load_dividend_data(holdings: list) -> tuple[dict, bool]:
    """加载分红数据（非关键，失败时返回空字典）。

    Returns:
        (dividend_data, success) — success=False 表示 API 调用异常。
    """
    try:
        from src.python.fetcher.akshare import get_dividend_data
        from src.python.providers.akshare_extras import _DIVIDEND_FAILURE

        stock_codes = [h.code for h in holdings if is_a_share_stock(h.name, h.code.strip())]
        if not stock_codes:
            return {}, True
        data = get_dividend_data(stock_codes)
        if data:
            _record_dividend_status(True)
        elif _DIVIDEND_FAILURE:
            # 源不可达/无返回 → 登记失败，使「分红」在数据源说明表与健康矩阵中如实可见；
            # 「本无分红」（``empty`` 且无故障）不登记，避免正常空结果被误报为源故障。
            _record_dividend_status(False, _dividend_failure_hint(_DIVIDEND_FAILURE))
        return data, True
    except Exception:
        logger.warning("[category] 分红数据加载失败（非关键），年均股息率列显示 --", exc_info=True)
        _record_dividend_status(False, "分红数据加载异常")
        return {}, False


#: 分红数据类别级取用标记的 source_key（说明表「本次使用」按前缀 ``dividend_`` 归属）
_DIVIDEND_SOURCE_KEY = "dividend_data"


def _record_dividend_status(success: bool, message: str = "") -> None:
    """登记分红数据的取用/失败状态（供数据源说明表与健康矩阵；观测失败不影响主链路）。

    与 ``industry_*`` 的类别级事件同口径：取到数据记成功（「本次使用」= 是），
    源不可达记失败（附可读原因）。
    """
    try:
        from src.python.report.data_status import get_tracker

        tracker = get_tracker()
        if success:
            tracker.record(_DIVIDEND_SOURCE_KEY, "T3", success=True)
        else:
            tracker.record(_DIVIDEND_SOURCE_KEY, "T3", success=False, failure_type="unreachable", message=message)
    except Exception:  # 观测失败不影响主链路
        logger.debug("[category] 分红状态登记失败（非关键）", exc_info=True)


def _dividend_failure_hint(reason: str) -> str:
    """分红失败类型 → 可读原因（与 ``cache/operations._sector_flow_hint`` 同文案口径）。"""
    return "连接失败" if reason == "connection" else "暂无数据"


def build_category_data_status(dividend_success: bool) -> DataStatus:
    """构建持仓分类表的数据源状态摘要。

    Args:
        dividend_success: 分红 API 是否成功

    Returns:
        DataStatus 字典；全部成功时返回空 dict。
    """
    status: DataStatus = {}
    if not dividend_success:
        status["dividend"] = DataStatusItem(
            available=False,
            tier="T4",
            message=STATUS_MESSAGES["dividend_unavailable"],
        )
    return status


def calc_yield_text(code: str, d, dividend_data: dict) -> str:
    """计算单条持仓的年均股息率文本（非关键，失败返回"--"）。

    合并 category 和 html_builders 两处的重复实现，统一此公共函数。
    """
    try:
        info = dividend_data.get(code)
        if not info:
            return "--"
        avg_div = info.get("avg_dividend")
        if avg_div is None:
            return "--"
        price = d.price if d and d.price > 0 else 0.0
        if price <= 0:
            return "--"
        return f"{avg_div / price * 100:.2f}%"
    except Exception:
        logger.warning("[category] 股息率计算异常", exc_info=True)
        return "--"
