"""财报全文域适配器 — DataSinking。

抓取委托 ``providers/datasink.py`` 的取数函数（不复制 HTTP 与解析逻辑）；
「上游字段 → 标准字段」的映射以声明式表达（``aliases``）。上游文档对象用
``id`` 表示文档号，标准字段统一叫 ``doc_id``，映射在此一处声明。
"""

from __future__ import annotations

from typing import Any, ClassVar

from src.python.fetcher.source_adapter import SourceAdapter, register_adapter
from src.python.providers import datasink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_REPORT


class DataSinkReportAdapter(SourceAdapter):
    """DataSinking 财报适配器（单篇文档：全文或单章节）。"""

    domain: ClassVar[str] = DOMAIN_FINANCIAL_REPORT
    source_id: ClassVar[str] = datasink.SOURCE_ID
    display_name: ClassVar[str] = datasink.DISPLAY_NAME
    #: 上游文档号字段名为 ``id``，标准字段统一为 ``doc_id``
    aliases: ClassVar[dict[str, str]] = {"id": "doc_id"}

    def extract_data(self, query: dict[str, Any]) -> Any:
        """按 ``doc_id``（可选 ``section``）取单篇正文。"""
        return datasink.fetch_report_document(query.get("doc_id"), query.get("section"))


register_adapter(DataSinkReportAdapter())
