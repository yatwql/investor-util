"""行情域适配器 — 腾讯财经 / 新浪财经 / 东方财富（含场外净值备源）。

这三个适配器是「数据源适配契约」的首个试点：它们与 ``fetcher/price.py`` 中既有的
手写转换函数 ``_price_transform_*`` **等价**（由 ``test_quote_adapter_parity.py``
逐源断言），差别只在于「上游字段 → 标准字段」的映射以**声明式**表达
（``aliases`` / ``defaults``），而非手写 dict 字面量。

抓取一律委托既有 provider 函数（``extract_data``），不复制任何 HTTP 与解析逻辑。
"""

from __future__ import annotations

from typing import Any, ClassVar

from src.python.core.num_utils import safe_num
from src.python.fetcher.source_adapter import SourceAdapter, register_adapter
from src.python.providers import eastmoney, tencent, hithink
from src.python.providers import sina as sina_provider
from src.python.schemas.datasource_fields import DOMAIN_QUOTE


class TencentQuoteAdapter(SourceAdapter):
    """腾讯财经行情适配器。"""

    domain: ClassVar[str] = DOMAIN_QUOTE
    source_id: ClassVar[str] = "tencent"
    display_name: ClassVar[str] = "腾讯财经"
    # 腾讯源自报的市值/市盈率缺失时按 0.0 处理（与既有转换函数一致）
    defaults: ClassVar[dict[str, Any]] = {"market_cap": 0.0, "pe": 0.0}

    def extract_data(self, query: dict[str, Any]) -> Any:
        return tencent.fetch_price(**query)


class SinaQuoteAdapter(SourceAdapter):
    """新浪财经行情适配器。

    新浪源不提供市值/市盈率，字段值恒为 ``None``（下游使用前需判 None）。
    """

    domain: ClassVar[str] = DOMAIN_QUOTE
    source_id: ClassVar[str] = "sina"
    display_name: ClassVar[str] = "新浪财经"
    defaults: ClassVar[dict[str, Any]] = {"market_cap": None, "pe": None}

    def extract_data(self, query: dict[str, Any]) -> Any:
        return sina_provider.fetch_price(**query)


class EastMoneyQuoteAdapter(SourceAdapter):
    """东方财富（场外基金净值）适配器。

    净值源以「净值即价格」的换算接入标准字段：``nav → price``、
    ``yesterday_nav → yesterday_close``、``nav_date → price_date``。
    """

    domain: ClassVar[str] = DOMAIN_QUOTE
    source_id: ClassVar[str] = "eastmoney"
    display_name: ClassVar[str] = "东方财富"
    aliases: ClassVar[dict[str, str]] = {
        "nav": "price",
        "yesterday_nav": "yesterday_close",
        "nav_date": "price_date",
    }

    def extract_data(self, query: dict[str, Any]) -> Any:
        return eastmoney.fetch_nav(**query)

    def transform_data(self, raw: Any, source: str = "") -> dict[str, Any] | None:
        """净值无效（缺失或 <= 0）视为无数据，交由链路尝试下一个源。"""
        if not isinstance(raw, dict) or safe_num(raw.get("nav"), default=0.0) <= 0:
            return None
        return super().transform_data(raw, source)


class SinaFundQuoteAdapter(SourceAdapter):
    """新浪财经场外基金净值适配器（`price_fund_otc` 链第二槽，跨厂商备源）。

    与 ``EastMoneyQuoteAdapter`` 同口径：``nav → price``、``yesterday_nav →
    yesterday_close``、``nav_date → price_date``；净值无效（<= 0）视为无数据。
    """

    domain: ClassVar[str] = DOMAIN_QUOTE
    source_id: ClassVar[str] = "sina_fund"
    display_name: ClassVar[str] = "新浪财经（场外净值）"
    aliases: ClassVar[dict[str, str]] = {
        "nav": "price",
        "yesterday_nav": "yesterday_close",
        "nav_date": "price_date",
    }

    def extract_data(self, query: dict[str, Any]) -> Any:
        return sina_provider.fetch_fund_nav(**query)

    def transform_data(self, raw: Any, source: str = "") -> dict[str, Any] | None:
        """净值无效（缺失或 <= 0）视为无数据，交由链路尝试下一个源。"""
        if not isinstance(raw, dict) or safe_num(raw.get("nav"), default=0.0) <= 0:
            return None
        return super().transform_data(raw, source)


class HithinkQuoteAdapter(SourceAdapter):
    """同花顺官方行情适配器（行情域第三槽，需凭据）。

    官方快照字段与标准字段异名，按 alias 归一；不提供总市值 → ``None``。
    """

    domain: ClassVar[str] = DOMAIN_QUOTE
    source_id: ClassVar[str] = "hithink"
    display_name: ClassVar[str] = hithink.DISPLAY_NAME
    aliases: ClassVar[dict[str, str]] = {
        "last_price": "price",
        "prev_price": "yesterday_close",
    }
    defaults: ClassVar[dict[str, Any]] = {"market_cap": None, "pe": None}

    def extract_data(self, query: dict[str, Any]) -> Any:
        return hithink.fetch_price(query.get("code"))


register_adapter(TencentQuoteAdapter())
register_adapter(SinaQuoteAdapter())
register_adapter(EastMoneyQuoteAdapter())
register_adapter(SinaFundQuoteAdapter())
register_adapter(HithinkQuoteAdapter())
