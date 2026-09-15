"""数据源标准字段契约 — 各数据域的规范化字段定义（唯一事实来源）。

与 ``providers/*`` 的关系：provider 负责「拿到上游原始响应」，本模块定义
「本项目统一字段长什么样」。字段集在此**可执行地**声明为 frozen dataclass，
而非散落在各转换函数的 ``dict`` 字面量里——新增数据源时字段名写错会在
契约自检与单元测试期报错，而不是运行期静默丢字段。

设计要点：

- 记录类即契约：``dataclass`` 的字段名就是标准字段名（由
  ``fetcher/source_adapter.py`` 反射得到，不存在第二份手抄清单）。
- 数值字段由类型注解区分：``float`` = 必有数值（缺失取 0.0），
  ``float | None`` = 可缺（缺失取 ``None``，表示「该源不提供此字段」）。
  ``str`` 字段缺失取空串。该规则与既有手写转换函数的取值语义一一对应。
- ``to_dict()`` 输出**全部**标准字段：同一域的不同源产出同键同构的 dict，
  下游无需为「某源少两个键」写分支。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ═══════════════════════════════════════════════════════════════
#  行情域（price/nav）
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class QuoteFields:
    """行情域标准字段 —— 个股/ETF 实时价与场外基金净值共用的统一格式。

    场外基金净值以「净值即价格」的换算接入（``nav → price``），使下游
    行情消费方无需区分「场内价格」与「场外净值」。

    Attributes:
        name: 证券名称（上游提供，用于代码重叠时的名称校验）
        code: 6 位证券代码
        price: 最新价（场外基金为最新单位净值）
        yesterday_close: 昨日收盘价（场外基金为昨日净值）
        price_date: 价格/净值日期（YYYY-MM-DD）
        source_api: 数据源标识（tencent/sina/eastmoney）
        source: 数据源展示名（腾讯财经/新浪财经/东方财富）
        market_cap: 总市值（单位：亿元；不提供该字段的源为 None）
        pe: 市盈率（不提供该字段的源为 None）
    """

    name: str = ""
    code: str = ""
    price: float = 0.0
    yesterday_close: float = 0.0
    price_date: str = ""
    source_api: str = ""
    source: str = ""
    market_cap: float | None = None
    pe: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为标准字段 dict（全部字段均出现，字段序与声明序一致）。"""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
#  域注册
# ═══════════════════════════════════════════════════════════════


DOMAIN_QUOTE = "quote"
DOMAIN_FINANCIAL_REPORT = "financial_report"
DOMAIN_FINANCIAL_INDICATOR = "financial_indicator"


@dataclass(frozen=True)
class FinancialReportFields:
    """财报全文域标准字段 —— 全文本财报（DataSinking）的统一格式。

    ``content`` 为章节正文（单篇取全文时为全文）；下游按需截断。``doc_id``
    对应上游 ``id``（经 adapter 的 aliases 归一）。

    Attributes:
        doc_id: 文档 ID（上游 ``id``，用于 ``/documents/{id}``）
        symbol: FMP 风格符号（如 ``600519.SS``）
        exchange: 交易所（``sse`` / ``szse`` / ``bj`` …）
        stock_code: 交易所本地代码（6 位）
        stock_name: 公司名称（本地语言）
        doc_type: 文种（``annual`` / ``semiannual`` / ``q1`` / ``q3`` / ``amendment``）
        report_period: 报告期（YYYY-MM-DD，财报覆盖的财季）
        title: 公告标题
        word_count: 正文词数
        announcement_time: 披露时间（毫秒 Unix 时间戳）
        content: 正文 Markdown（章节正文或全文）
        adjunct_url: 原披露链接（不可用时为空串）
        source_api: 数据源标识（datasink）
        source: 披露平台归属（合规要求再分发时保留）
    """

    doc_id: int = 0
    symbol: str = ""
    exchange: str = ""
    stock_code: str = ""
    stock_name: str = ""
    doc_type: str = ""
    report_period: str = ""
    title: str = ""
    word_count: int = 0
    announcement_time: int = 0
    content: str = ""
    adjunct_url: str = ""
    source_api: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转为标准字段 dict（全部字段均出现，字段序与声明序一致）。"""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
#  财务指标域（financial_indicator）
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FinancialIndicatorFields:
    """财务指标域标准字段 —— 上市公司**单报告期**结构化财务指标。

    金额类字段单位为元；比率类字段（同比/毛利率/ROE/资产负债率）为
    **小数比例**（0.1675 = 16.75%）。报告期以元数据为准，不从正文猜。

    Attributes:
        code: 6 位证券代码
        symbol: FMP 风格符号
        report_period: 报告期（YYYY-MM-DD）
        doc_type: 文种（annual/semiannual/q1/q3）
        revenue: 营业总收入（元）
        net_profit: 归母净利润（元）
        revenue_yoy: 营业总收入同比（小数）
        net_profit_yoy: 归母净利润同比（小数）
        gross_margin: 毛利率（小数）
        roe: 净资产收益率（小数）
        debt_ratio: 资产负债率（小数）
        operating_cash_flow: 经营活动现金流净额（元）
        eps: 基本每股收益（元）
        bvps: 每股净资产（元）
        source_api: 数据源标识（akshare_financial）
        source: 数据源展示名
    """

    code: str = ""
    symbol: str = ""
    report_period: str = ""
    doc_type: str = ""
    revenue: float | None = None
    net_profit: float | None = None
    revenue_yoy: float | None = None
    net_profit_yoy: float | None = None
    gross_margin: float | None = None
    roe: float | None = None
    debt_ratio: float | None = None
    operating_cash_flow: float | None = None
    eps: float | None = None
    bvps: float | None = None
    source_api: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转为标准字段 dict（全部字段均出现，字段序与声明序一致）。"""
        return asdict(self)


# 数据域 → 标准字段记录类（新增域时在此登记，契约自检据此校验适配器）
DOMAIN_RECORDS: dict[str, type] = {
    DOMAIN_QUOTE: QuoteFields,
    DOMAIN_FINANCIAL_REPORT: FinancialReportFields,
    DOMAIN_FINANCIAL_INDICATOR: FinancialIndicatorFields,
}
