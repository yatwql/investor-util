"""财务指标域适配器 — akshare 结构化财务指标（指标域主源）。

抓取委托 ``providers/akshare_financial.py``；该 provider 已直接输出标准字段名，
故无需 alias 改名（``transform_data`` 走默认声明式归一，字段集与类型由标准字段
记录类驱动）。备用支路「从 DataSinking 全文解析指标」在后续阶段接入本注册表。
"""

from __future__ import annotations

from typing import Any, ClassVar

from src.python.fetcher.source_adapter import SourceAdapter, register_adapter
from src.python.providers import akshare_financial
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_INDICATOR


class AkshareFinancialAdapter(SourceAdapter):
    """akshare 财务指标适配器（单只股票的最新报告期记录）。"""

    domain: ClassVar[str] = DOMAIN_FINANCIAL_INDICATOR
    source_id: ClassVar[str] = akshare_financial.SOURCE_ID
    display_name: ClassVar[str] = akshare_financial.DISPLAY_NAME

    def extract_data(self, query: dict[str, Any]) -> Any:
        """按 ``code`` 取最新报告期标准指标记录。"""
        return akshare_financial.fetch_financial_indicators(query.get("code"))


register_adapter(AkshareFinancialAdapter())
