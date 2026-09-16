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
from src.python.core.code_utils import is_otc_fund_by_name, to_fmp_symbol
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

#: 优先文种：经营讨论/管理层讨论章节只存在于年报与半年报，季报仅有财务数据段，
#: 故回溯时年报/半年报优先，季报仅作最后兜底（减少无效请求、优先拿有内容的报告）
_PREFERRED_DOC_TYPES = ("annual", "semiannual")

#: 标题含下列词的条目与财报混排在索引里但非财报正文（如「关于变更…报告预约披露时间的公告」），跳过
_NOTICE_TITLE_KEYWORDS = ("公告",)

#: 全文兜底最多尝试的候选篇数：单篇可达 40 万字（银行年报），比章节路径更保守
_FULLTEXT_FALLBACK_LIMIT = 2

#: 取用方式（写入记录，供排查区分「章节命中」与「全文定位」）
SECTION_SOURCE_SECTIONS = "sections"
SECTION_SOURCE_FULLTEXT = "fulltext"

#: 单标的候选报告篇数：最新一篇缺目标章节时向前回溯（半年报 → 一季报 → 上年年报），
#: 命中即止。上限 3 篇兼顾覆盖率与请求配额（每篇 1 次章节清单 + 若干次正文请求）：
#: 银行股半年报在 DataSinking 侧常缺「管理层讨论与分析」章节，回溯到上年年报即可取到。
_REPORT_CANDIDATE_LIMIT = 3

#: 未取到财报的原因文案（写入契约 failures，展示层原样透出）
REASON_INDEX_EMPTY = "索引无该标的报告"
REASON_SECTIONS_MISSING = "目标章节缺失（已试报告期：{periods}）"

#: 标的来源标签（直接持仓 / 穿透自基金）
_TARGET_SOURCE_HOLDING = "直接持有"

#: 穿透来源基金最大展示个数（超出以「…」略去，避免单元格过长）
_TARGET_SOURCE_LIMIT = 2


def target_source_label(target: dict[str, Any]) -> str:
    """标的来源标签：直接持仓写「直接持有」，穿透写「穿透：来源基金…」。"""
    if str(target.get("kind") or "") != "penetrated":
        return _TARGET_SOURCE_HOLDING
    sources = [str(s).strip() for s in (target.get("sources") or []) if str(s).strip()]
    if not sources:
        return "穿透"
    shown = "；".join(sources[:_TARGET_SOURCE_LIMIT])
    return f"穿透：{shown}" + ("…" if len(sources) > _TARGET_SOURCE_LIMIT else "")


def collect_a_share_targets(
    holdings: list,
    penetrated_targets: list[dict[str, Any] | str] | None = None,
) -> list[dict[str, Any]]:
    """持仓 + 穿透资产中的 A 股**个股**标的（去重、按代码升序）。

    两类排除/合并规则：
      - 持仓中的**场外基金**不取个股财报：基金代码与深市股票在 ``00`` 前缀重叠
        （如 ``002943`` 既是场外基金「广发多因子灵活配置混合」也是深市股票
        「宇晶股份」），只按代码判 A 股会让基金名配到股票财报（张冠李戴）。
        判定复用 ``is_otc_fund_by_name``（名称 + 代码双维度，仅 00 重叠区生效）。
      - 穿透标的带**中文名与来源基金**（来自穿透层的 ``name`` / ``funds``），
        用于展示层回填名称并标注「穿透：XX 基金」，避免只显示 ``300274.SZ``。
        兼容裸代码字符串（无名称时展示层回退 symbol）。

    Args:
        holdings: 持仓对象列表（具备 ``code`` / ``name`` 属性）
        penetrated_targets: 穿透标的（``{"code", "name", "sources"}`` 或裸代码，可空）

    Returns:
        ``[{"code", "name", "symbol", "kind", "sources"}]``；非 A 股代码被过滤。
        ``kind`` 取 ``holding`` / ``penetrated``；同代码时直接持仓优先（来源记「直接持有」）。
    """
    targets: dict[str, dict[str, Any]] = {}
    for h in holdings:
        code = str(getattr(h, "code", "") or "").strip()
        name = str(getattr(h, "name", "") or "")
        symbol = to_fmp_symbol(code)
        if not symbol or code in targets or is_otc_fund_by_name(name, code):
            continue
        targets[code] = {
            "code": code,
            "name": name,
            "symbol": symbol,
            "kind": "holding",
            "sources": [_TARGET_SOURCE_HOLDING],
        }
    for raw in penetrated_targets or []:
        if isinstance(raw, str):
            code, name, sources = raw.strip(), "", []
        else:
            code = str(raw.get("code") or "").strip()
            name = str(raw.get("name") or "")
            sources = [str(s).strip() for s in (raw.get("sources") or []) if str(s).strip()]
        symbol = to_fmp_symbol(code)
        if not symbol or code in targets:
            continue
        targets[code] = {
            "code": code,
            "name": name,
            "symbol": symbol,
            "kind": "penetrated",
            "sources": sources,
        }
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


def _collect_doc_sections(doc_id: int | str, preferences: list[str]) -> tuple[dict[str, Any] | None, list[str]]:
    """取单篇文档的目标章节正文（多节按偏好顺序拼接）。

    先取该文档的实际章节名清单（1 次请求，带缓存），按偏好做**精确章节名**匹配；
    匹配为空时回退偏好名直取（服务端 fuzzy）。两种清单异常都要兜住：
      - 清单不可得（None）
      - 清单**非空但残缺**（DataSinking 解析异常，如某银行半年报只解析出
        「一、有限售条件股份/二、无限售条件股份」两节）——此时按清单匹配必然为空，
        不回退等于白白丢掉整篇报告

    Returns:
        ``(首个非空正文记录 | None, 正文列表)``
    """
    resolved = _pick_sections(_fetch_sections(doc_id), tuple(preferences)) or list(preferences)
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
    return record, contents


def _assemble_record(
    record: dict[str, Any],
    meta: dict[str, Any],
    symbol: str,
    content: str,
    max_chars: int,
    section_source: str = SECTION_SOURCE_SECTIONS,
) -> dict[str, Any]:
    """正文 + 元数据 → 单标的财报记录契约。"""
    return {
        "doc_id": record.get("doc_id") or meta.get("id"),
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
        "section_source": section_source,
    }


def _is_notice(meta: dict[str, Any]) -> bool:
    """标题是否信息披露公告（非财报正文）——索引把两者混排在一起。"""
    title = str(meta.get("title") or "")
    return any(k in title for k in _NOTICE_TITLE_KEYWORDS)


def _order_report_candidates(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """候选报告排序：**年报/半年报优先**，其余（季报）按报告期倒序在后。

    索引本身已按「报告期 → 披露时间」倒序，故这里只做**稳定**分组，不改变组内顺序。
    季报不含「管理层讨论与分析」，把它排后面可避免「最新一季报无目标章节 → 回溯」的
    无谓请求；信息披露公告（标题含「公告」）直接剔除。
    """
    usable = [m for m in items if m.get("id") is not None and not _is_notice(m)]
    preferred_ids = {id(m) for m in usable if str(m.get("doc_type") or "") in _PREFERRED_DOC_TYPES}
    preferred = [m for m in usable if id(m) in preferred_ids]
    others = [m for m in usable if id(m) not in preferred_ids]
    return (preferred + others)[: max(1, int(limit))]


#: 判定「目录行」的探测窗口与点线特征：目录条目形如「董事会报告 ......」，
#: 关键词首个命中常落在目录里，取到目录行等于摘要无内容
_TOC_PROBE_CHARS = 90


def _is_toc_line(content: str, pos: int) -> bool:
    """该位置是否是目录行（**同一行内**出现点线引导/省略号）。

    只看关键词到行尾这一行：正文段落里出现省略号（「利润及股息分配……」）不应被误判为目录。
    """
    line_end = content.find("\n", pos)
    line = content[pos : line_end if line_end >= 0 else pos + _TOC_PROBE_CHARS][:_TOC_PROBE_CHARS]
    return ("...." in line) or ("…" in line) or (".." in line)


def _locate_from_fulltext(doc_id: int | str, preferences: list[str], max_chars: int) -> tuple[str, str]:
    """整篇正文中按偏好关键词**定位片段**（章节接口与偏好名直取都失败时的兜底）。

    部分标的（如银行股）在源侧章节未被解析出来（``/sections`` 残缺 + 裸章节名 404），
    但**整篇正文可得**，且正文里含关键词（季报的「主要财务数据」往往就在正文里）。
    取关键词所在位置起的 ``max_chars`` 字，避免把封面/目录/公司简介当摘要；
    **跳过目录行**——部分报告（如银行年报）里关键词首个命中落在目录（「董事会报告 ……」），
    只出现在目录里的关键词会被跳过、继续试下一个偏好。

    Returns:
        ``(片段, 命中的偏好关键词)``；未取到全文时 ``("", "")``；
        全文里没有任一偏好关键词时退化为正文开头片段（关键词为空串）。
    """
    doc = _fetch_document(doc_id, "")
    content = str((doc or {}).get("content") or "")
    if not content.strip():
        return "", ""
    for pref in preferences:
        pos = content.find(pref)
        while pos >= 0 and _is_toc_line(content, pos):
            pos = content.find(pref, pos + 1)  # 跳过目录行，找正文里那一次
        if pos >= 0:
            return content[pos : pos + max_chars], pref
    return content[:max_chars], ""


def fetch_symbol_report_detailed(
    symbol: str,
    doc_types: tuple[str, ...] = DEFAULT_DOC_TYPES,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_candidates: int = _REPORT_CANDIDATE_LIMIT,
) -> tuple[dict[str, Any] | None, str]:
    """取单只 A 股的目标章节记录，并返回未取到的原因（供契约失败清单展示）。

    报告期回溯：最多试 ``max_candidates`` 篇（命中即止），且**年报/半年报优先于季报**
    （季报无「管理层讨论与分析」，仅作最后兜底）。银行股半年报在 DataSinking 侧常缺
    「管理层讨论与分析」（或章节清单残缺且直取 404），回溯到上年年报即可取到；报告期
    与文种如实写入记录，展示层不会误标。

    两阶取数（逐阶降级，不新造请求路径）：
      ① **章节阶**：章节清单匹配（含残缺回退）→ 逐个取章节正文
      ② **全文阶**：章节阶全失败时整篇下载后按偏好关键词定位片段（最多
         ``_FULLTEXT_FALLBACK_LIMIT`` 篇）

    Returns:
        ``(记录 | None, 原因文案)``；成功时原因为空串。
    """
    items = _fetch_index(symbol, doc_types)
    if not items:
        return None, REASON_INDEX_EMPTY
    preferences = [str(p).strip() for p in sections if str(p).strip()]
    candidates = _order_report_candidates(items, max_candidates)
    tried: list[str] = []
    for meta in candidates:
        doc_id = meta.get("id")
        tried.append(str(meta.get("report_period") or meta.get("title") or doc_id))
        record, contents = _collect_doc_sections(doc_id, preferences)
        if record is None or not contents:
            continue
        return _assemble_record(record, meta, symbol, "\n\n".join(contents), max_chars), ""

    # ② 全文阶：源侧章节未解析出来时，整篇下载后按关键词定位片段
    for meta in candidates[:_FULLTEXT_FALLBACK_LIMIT]:
        doc_id = meta.get("id")
        excerpt, matched = _locate_from_fulltext(doc_id, preferences, max_chars)
        if not excerpt.strip():
            continue
        logger.info("[financial_report] %s 走全文兜底（doc=%s，命中关键词=%s）", symbol, doc_id, matched or "无")
        full_record = _fetch_document(doc_id, "") or meta
        return (
            _assemble_record(full_record, meta, symbol, excerpt, max_chars, section_source=SECTION_SOURCE_FULLTEXT),
            "",
        )

    return None, REASON_SECTIONS_MISSING.format(periods="、".join(tried) or "无")


def fetch_symbol_report(
    symbol: str,
    doc_types: tuple[str, ...] = DEFAULT_DOC_TYPES,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any] | None:
    """取单只 A 股的目标章节记录（支持多章节拼接与报告期回溯）。

    Args:
        symbol: FMP 风格符号（``600519.SS``）
        doc_types: 文种白名单（**空 = 不限文种**；跨文种取最新报告期）
        sections: 章节**偏好**列表（在文档实际章节名中按顺序子串匹配，命中者拼接）
        max_chars: 正文截断长度（报告内摘要）

    Returns:
        ``{doc_id, symbol, report_period, doc_type, title, announcement_time,
        content, summary, source, adjunct_url, word_count}``；无覆盖时 None
    """
    record, _reason = fetch_symbol_report_detailed(symbol, doc_types, sections, max_chars)
    return record
