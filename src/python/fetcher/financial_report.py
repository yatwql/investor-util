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
SECTIONS_PREFIX = "report_datasink_sections_"

#: 文种白名单（**空 = 不限文种**）：默认取**最新报告期**——半年报/季报通常比年报新，
#: 故不再按「年报优先、命中即止」排序，而是跨文种按报告期取最新一篇。
DEFAULT_DOC_TYPES: tuple[str, ...] = ()

#: 章节**偏好**列表（按顺序在文档实际章节名中做子串匹配）：年报/半年报取「管理层讨论
#: 与分析」，季报多为「主要财务数据/主要会计数据」，旧格式用「董事会报告」。
DEFAULT_SECTIONS: tuple[str, ...] = (
    "管理层讨论与分析",
    "经营情况讨论与分析",
    "主要财务数据",
    "主要会计数据",
    "董事会报告",
)
DEFAULT_MAX_CHARS = 2000

#: 索引一次取回的候选篇数（本地按报告期排序后取最新一篇）
_INDEX_SCAN_SIZE = 10


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


def _fetch_index(symbol: str, doc_types: tuple[str, ...] = ()) -> list[dict[str, Any]] | None:
    """取某符号的报告元数据（**跨文种取最新报告期**，按报告期倒序），带缓存。

    一次请求取回最近若干篇（不带 ``doc_type`` 过滤），本地按「报告期 → 披露时间」
    倒序，故半年报/季报（通常比年报新）自然排在年报之前；``doc_types`` 非空时仅作为
    文种白名单过滤。
    """
    cache_key = f"{INDEX_PREFIX}{symbol}"
    cached = cache_get(cache_key, get_ttl("report", cache_key))
    if cached is not None:
        _mark_used(f"{INDEX_PREFIX.rstrip('_')}")
        return cached if isinstance(cached, list) else None

    items = datasink.fetch_report_documents(symbol, order="desc", size=_INDEX_SCAN_SIZE)
    if not items:
        return None
    wanted = {str(t).strip().lower() for t in (doc_types or ()) if str(t).strip()}
    picked = [i for i in items if not wanted or str(i.get("doc_type") or "").lower() in wanted]
    if not picked:
        return None
    picked.sort(
        key=lambda i: (str(i.get("report_period") or ""), int(i.get("announcement_time") or 0)),
        reverse=True,
    )
    cache_set(cache_key, picked)
    _mark_used(f"{INDEX_PREFIX.rstrip('_')}")
    return picked


def _fetch_sections(doc_id: int | str) -> list[str] | None:
    """取该文档的**实际章节名清单**（带缓存）；不可得时返回 None（调用方回退偏好名直取）。"""
    cache_key = f"{SECTIONS_PREFIX}{doc_id}"
    cached = cache_get(cache_key, get_ttl("report", cache_key))
    if isinstance(cached, list):
        return cached
    sections = datasink.fetch_report_sections(doc_id)
    if sections:
        cache_set(cache_key, sections)
        return sections
    return None


def _pick_sections(available: list[str] | None, preferences: tuple[str, ...]) -> list[str]:
    """按偏好顺序在**实际章节名**中做子串匹配，返回精确章节名（去重保序）。

    每个偏好只取首个匹配项，避免同一章节被多个偏好重复拼接；``available`` 不可得时
    回退为偏好名直取（服务端 fuzzy 匹配）。
    """
    if not available:
        return [str(p) for p in preferences if str(p).strip()]
    picked: list[str] = []
    for pref in preferences:
        key = str(pref).strip()
        if not key:
            continue
        for name in available:
            if key in name and name not in picked:
                picked.append(name)
                break
    return picked


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
        doc_types: 文种白名单（**空 = 不限文种**；跨文种取最新报告期）
        sections: 章节**偏好**列表（在文档实际章节名中按顺序子串匹配，命中者拼接）
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

    # 先取该文档的实际章节名清单（1 次请求，带缓存），再按偏好匹配**精确章节名**；
    # 清单不可得时回退偏好名直取（服务端 fuzzy 匹配）——避免裸章节名 404 被误判为
    # 「该标的未取到财报」（此前多数「未取到财报」正是该原因）
    resolved = _pick_sections(_fetch_sections(doc_id), sections)
    record: dict[str, Any] | None = None
    contents: list[str] = []
    for section in resolved:
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
