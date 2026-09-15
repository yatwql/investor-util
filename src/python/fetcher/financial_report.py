"""全文本财报域取数编排 — 符号集合 → 元数据 → 章节正文。

复用既有两条通路，不新造获取路径：
  - 元数据（``/documents``）与单篇内容（``/documents/{id}``）的 HTTP、限速、
    配额护栏均在 ``providers/datasink.py``；本模块只做「取哪一篇、取哪一节、
    怎么缓存」
  - 单篇正文经 ``fetcher/chain.fetch_with_fallback`` + 财报域适配器两槽，
    复用缓存键、熔断与降级（缓存前缀见 ``core/registry``）

报告层消费者见 ``report/financial_report_digest.py``。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.cache import set as cache_set
from src.python.core.code_utils import to_fmp_symbol
from src.python.fetcher.source_adapter import adapter_chain_slots
from src.python.providers import datasink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_REPORT

logger = logging.getLogger("invest")

INDEX_PREFIX = "report_datasink_index_"
DOC_PREFIX = "report_datasink_doc_"

DEFAULT_DOC_TYPES: tuple[str, ...] = ("annual", "semiannual")
DEFAULT_SECTIONS: tuple[str, ...] = ("管理层讨论与分析",)
DEFAULT_MAX_CHARS = 2000


def collect_a_share_targets(
    holdings: list,
    penetrated_codes: list[str] | None = None,
) -> list[dict[str, str]]:
    """持仓 + 穿透资产中的 A 股标的（去重、按代码升序）。

    Args:
        holdings: 持仓对象列表（具备 ``code`` / ``name`` 属性）
        penetrated_codes: 穿透底层的证券代码（可空）

    Returns:
        ``[{"code", "name", "symbol"}]``；非 A 股代码被过滤
    """
    targets: dict[str, dict[str, str]] = {}
    for h in holdings:
        code = str(getattr(h, "code", "") or "").strip()
        symbol = to_fmp_symbol(code)
        if symbol and code not in targets:
            targets[code] = {"code": code, "name": str(getattr(h, "name", "") or ""), "symbol": symbol}
    for raw in penetrated_codes or []:
        code = str(raw or "").strip()
        symbol = to_fmp_symbol(code)
        if symbol and code not in targets:
            targets[code] = {"code": code, "name": "", "symbol": symbol}
    return [targets[k] for k in sorted(targets)]


def _mark_used(source_key: str) -> None:
    """标记「本次取用了 DataSinking 数据」——供数据源说明表的「本次使用」列。

    只记成功事件（含缓存命中返回），不参与降级计数：章节名 fuzzy 未命中等
    预期内空结果不应被计为源故障（详见 ``data_status.mark_data_used``）。
    """
    from src.python.report.data_status import mark_data_used

    mark_data_used(source_key)


def _fetch_index(symbol: str, doc_types: tuple[str, ...]) -> list[dict[str, Any]] | None:
    """取某符号的报告元数据（按文种顺序试取最新一篇），带缓存。"""
    cache_key = f"{INDEX_PREFIX}{symbol}"
    cached = cache_get(cache_key, get_ttl("report", cache_key))
    if cached is not None:
        _mark_used(f"{INDEX_PREFIX.rstrip('_')}")
        return cached if isinstance(cached, list) else None
    for doc_type in doc_types:
        items = datasink.fetch_report_documents(symbol, doc_type=doc_type, order="desc", size=1)
        if items:
            cache_set(cache_key, items)
            _mark_used(f"{INDEX_PREFIX.rstrip('_')}")
            return items
    return None


def _fetch_document(doc_id: int | str, section: str) -> dict[str, Any] | None:
    """取单篇正文（经链路缓存/熔断/降级 + 财报域适配器归一）。"""
    from src.python.fetcher.chain import fetch_with_fallback

    provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_REPORT)
    cache_key = f"{DOC_PREFIX}{doc_id}_{section or 'full'}"
    record = fetch_with_fallback(
        "financial_report",
        provider_map,
        cache_key,
        get_ttl("report_doc", cache_key),
        fn_kwargs={"doc_id": doc_id, "section": section or None},
        transform=transform_map,
    )
    if record:
        _mark_used(DOC_PREFIX.rstrip("_"))
    return record


def fetch_symbol_report(
    symbol: str,
    doc_types: tuple[str, ...] = DEFAULT_DOC_TYPES,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any] | None:
    """取单只 A 股的最新财报章节记录（支持多章节拼接）。

    Args:
        symbol: FMP 风格符号（``600519.SS``）
        doc_types: 文种优先级（默认先年报、后半年报）
        sections: 章节标题列表（fuzzy 匹配；按顺序取，命中者拼接）
        max_chars: 正文截断长度（报告内摘要）

    Returns:
        ``{doc_id, symbol, report_period, doc_type, title, announcement_time,
        content, summary, source, adjunct_url, word_count}``；无覆盖时 None
    """
    items = _fetch_index(symbol, doc_types)
    if not items:
        return None
    meta = items[0]
    doc_id = meta.get("id")
    if doc_id is None:
        return None

    # 逐章节取正文（每节独立缓存），命中者按声明顺序拼接；元数据取首个非空记录
    record: dict[str, Any] | None = None
    contents: list[str] = []
    for section in sections:
        got = _fetch_document(doc_id, section)
        if not got:
            continue
        if record is None:
            record = got
        text = str(got.get("content") or "").strip()
        if text:
            contents.append(text)
    if record is None or not contents:
        return None

    content = "\n\n".join(contents)
    return {
        "doc_id": record.get("doc_id") or doc_id,
        "symbol": record.get("symbol") or symbol,
        "report_period": record.get("report_period") or meta.get("report_period", ""),
        "doc_type": record.get("doc_type") or meta.get("doc_type", ""),
        "title": record.get("title") or meta.get("title", ""),
        "announcement_time": record.get("announcement_time") or meta.get("announcement_time", 0),
        "content": content,
        "summary": content[:max_chars],
        "word_count": record.get("word_count") or meta.get("word_count", 0),
        "source": record.get("source", ""),
        "adjunct_url": record.get("adjunct_url", ""),
    }
