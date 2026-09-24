"""财报全文域适配器 — DataSinking（主源）+ 巨潮资讯（备源）。

抓取委托各 provider 模块的取数函数（不复制 HTTP 与解析逻辑）；「上游字段 → 标准字段」
的映射以声明式表达（``aliases``）。上游文档对象用 ``id`` 表示文档号，标准字段统一叫
``doc_id``，映射在此一处声明。

两源经 ``adapter_chain_slots(DOMAIN_FINANCIAL_REPORT)`` 构成链路主/备：
主源（DataSinking）无该标的/无可用章节时，编排层把候选切到巨潮源
（``source_hint`` 命名空间隔离，异源 doc_id 互不服务），缓存键/熔断/降级
全部复用 ``fetcher/chain.fetch_with_fallback``。
"""

from __future__ import annotations

from typing import Any, ClassVar

from src.python.fetcher.report_locate import locate_keyword_excerpt
from src.python.fetcher.source_adapter import SourceAdapter, register_adapter
from src.python.providers import cninfo, datasink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_REPORT


class DataSinkReportAdapter(SourceAdapter):
    """DataSinking 财报适配器（单篇文档：全文或单章节）。"""

    domain: ClassVar[str] = DOMAIN_FINANCIAL_REPORT
    source_id: ClassVar[str] = datasink.SOURCE_ID
    display_name: ClassVar[str] = datasink.DISPLAY_NAME
    #: 上游文档号字段名为 ``id``，标准字段统一为 ``doc_id``
    aliases: ClassVar[dict[str, str]] = {"id": "doc_id"}

    def extract_data(self, query: dict[str, Any]) -> Any:
        """按 ``doc_id``（可选 ``section``）取单篇正文。

        命名空间隔离：``source_hint`` 指向异源（巨潮）时立即返回 None——
        巨潮候选的 doc_id 是公告 ID，对主源无意义，不发起无效请求。
        """
        hint = query.get("source_hint")
        if hint not in (None, "", datasink.SOURCE_ID):
            return None
        return datasink.fetch_report_document(query.get("doc_id"), query.get("section"))


class CninfoReportAdapter(SourceAdapter):
    """巨潮资讯财报适配器（备源）：公告 PDF → 关键词定位章节切片。

    章节切片规则与全文兜底共用 ``fetcher/report_locate``（跳过目录行），
    与主源的章节偏好语义一致（同一 ``DEFAULT_SECTIONS`` 偏好串传入）。
    """

    domain: ClassVar[str] = DOMAIN_FINANCIAL_REPORT
    source_id: ClassVar[str] = cninfo.SOURCE_ID
    display_name: ClassVar[str] = cninfo.DISPLAY_NAME

    def extract_data(self, query: dict[str, Any]) -> Any:
        """按公告 ID（+ 候选元数据）取正文切片；异源/缺件返回 None。

        ``query`` 由编排层注入：``source_hint``（命名空间，非本源即拒）、
        ``doc_id``（公告 ID）、``section``（章节偏好串，空 = 全文）、
        ``meta``（候选元数据：标题/报告期/文种/披露时间/下载路径）。
        """
        if query.get("source_hint") != cninfo.SOURCE_ID:
            return None
        announcement_id = str(query.get("doc_id") or "").strip()
        if not announcement_id:
            return None
        meta = query.get("meta") or {}
        text = cninfo.fetch_report_text(announcement_id, str(meta.get("adjunct_url") or ""))
        if not text.strip():
            return None
        section = str(query.get("section") or "").strip()
        if section:
            excerpt, _matched = locate_keyword_excerpt(text, [section], cninfo.SECTION_TEXT_CAP)
            if not excerpt:
                # 该章节偏好未在正文命中：链路继续（下一偏好/下一候选/全文兜底）
                return None
            content = excerpt
        else:
            content = text[: cninfo.FULLTEXT_CAP]
        return {
            "doc_id": announcement_id,
            "symbol": meta.get("symbol") or "",
            "stock_code": meta.get("stock_code") or "",
            "stock_name": meta.get("stock_name") or "",
            "doc_type": meta.get("doc_type") or "",
            "report_period": meta.get("report_period") or "",
            "title": meta.get("title") or "",
            "announcement_time": meta.get("announcement_time") or 0,
            "content": content,
            "word_count": len(text),
            "adjunct_url": meta.get("adjunct_url") or "",
        }


register_adapter(DataSinkReportAdapter())
register_adapter(CninfoReportAdapter())
