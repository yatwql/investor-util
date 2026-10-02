"""巨潮资讯网（cninfo）— 财报全文域第二 provider（财报主源不可用时的接管源）。

定位：DataSinking（主源）**无该标的/无可用章节时的接管源**——公开免费、无需凭据。
只在主源索引落空时由 ``fetcher/financial_report.py`` 的编排层调用；主源可用时
本模块完全不参与（「主源可用时输出逐字不变」红线）。

取数三段（HTTP 仅经 ``core/http_client`` 工厂，与全仓 HTTP 构造点纪律一致）：
  1) ``resolve_org_id``：topSearch 按证券代码解析 orgId（cninfo 列表查询的必需参数，
     每股一次，按代码缓存）
  2) ``fetch_report_listings``：hisAnnouncement/query 取公告元数据，本地归类为
     标准文种（年报/半年报/季报），归一为与主源索引**同一形状**的元数据 dict
  3) ``fetch_report_text``：static 站下载公告 PDF → pdfplumber 解析为纯文本
     （按公告缓存，同一份 PDF 只下载解析一次；章节切片在链路逐节缓存之上）

护栏（参照 ``providers/datasink.py`` 模式）：
  - 模块级 :class:`RateLimiter` 礼貌间隔（公开 API，默认 1 秒/请求）；HTTP 429 退避重试一次
  - 全部失败路径返回 None/空（不抛异常），交由链路/编排按空结果降级

依赖：``pdfplumber``（主依赖已声明）。**惰性导入**：环境缺库时解析环节返回空文本，
该源优雅降级（不拖垮链路）；与 check-svg 的 Pillow 先例同模式。
"""

from __future__ import annotations

import io
import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any


from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.cache import set as cache_set
from src.python.core.code_utils import get_exchange_category
from src.python.core.http_client import make_http_client
from src.python.core.retry import STRATEGY_FIXED, RetryPolicy
from src.python.core.throttle import interval_delay  # 间隔+抖动唯一算式
from src.python.providers._utils import set_last_reason, with_connect_retry

logger = logging.getLogger("invest")

SOURCE_ID = "cninfo"
DISPLAY_NAME = "巨潮资讯"

_BASE = "http://www.cninfo.com.cn"
_STATIC_BASE = "http://static.cninfo.com.cn"
#: 元数据类接口（orgId 搜索 / 公告列表）的超时预算
_TIMEOUT = 20.0
#: 公告 PDF 下载的超时预算。年报原文动辄几十 MB，与元数据接口共用 20s 必然在
#: 慢链路下触发「挂起 → 不重试 → 失败」，且**从未成功过**（白等 N × 超时）。
#: 单独放宽到 60s，配合下方「本会话主机不可达短路」避免反复白等。
_PDF_TIMEOUT = 60.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; investor-util)"}
#: 公开 API 礼貌间隔（秒）：限速器单例的固定档（数据源免费且无配置套餐，不引入配置键）
_MIN_INTERVAL = 1.0
#: 429 限速退避策略（重试一次）
_RATE_LIMIT_POLICY = RetryPolicy(attempts=2, strategy=STRATEGY_FIXED, base_backoff=2.0)

INDEX_PREFIX = "report_cninfo_index_"
ORGID_PREFIX = "report_cninfo_orgid_"
TEXT_PREFIX = "report_cninfo_text_"

#: 列表一次取回的公告条数（本地归类/过滤后由编排层再按报告期排序回溯）
_LIST_PAGE_SIZE = 30
#: 财报类目白名单（年度报告/半年度报告/一季报/三季报）。**必须只查财报类目**：
#: 按全部类目（``category_szsh;``）查时第 1 页（30 条）可能全是普通公告——实测
#: 工商银行即如此，而本函数只取第 1 页 → 候选为空 → 巨潮备源对该标的**静默失效**
#: （其余标的因财报恰好在首页而看不出问题）。与 ``_DOC_TYPE_RULES`` 一一对应。
_FINANCIAL_CATEGORIES = (
    "category_ndbg_szsh;"  # 年度报告
    "category_bndbg_szsh;"  # 半年度报告
    "category_yjdbg_szsh;"  # 第一季度报告
    "category_sjdbg_szsh;"  # 第三季度报告
)
#: 列表查询的披露日期窗口：覆盖候选回溯（最新 → 半年报 → 上年年报）
_LIST_WINDOW_DAYS = 900
#: PDF 解析页数上限（防异常超大文件撑爆内存；年报通常 < 300 页）
_PDF_MAX_PAGES = 300

#: 章节切片上限（字符）：年报全文可达 40 万字，切片须截断（下游摘要再按 max_chars 截）
SECTION_TEXT_CAP = 30_000
#: 全文兜底取数上限（字符）：仅正文定位用，超出部分不进入缓存记录
FULLTEXT_CAP = 100_000

#: 标题归类规则（按序命中即返回）：(关键词, 标准 doc_type, 期末月日)。
#: 「半年度」必须先于「年度」判定——「半年度报告」含「年度报告」子串。
_DOC_TYPE_RULES: tuple[tuple[str, str, str], ...] = (
    ("半年度报告", "semiannual", "06-30"),
    ("第一季度报告", "q1", "03-31"),
    ("第三季度报告", "q3", "09-30"),
    ("年度报告", "annual", "12-31"),
)
#: 非正文条目（摘要/英文版/已取消）——与财报混排在列表里，剔除
_SKIP_TITLE_KEYWORDS = ("摘要", "英文版", "已取消", "已撤回")
_YEAR_RE = re.compile(r"(20\d{2})\s*年")

_limiter: Any = None
_limiter_lock = threading.Lock()

#: 本会话内判定为「主机不可达」的主机名集合（如本机到 cninfo 网络路径被阻断时）。
#: 挂起型失败（单次尝试耗时 ≥ 超时预算一半）已被 ``with_connect_retry`` 判为不可达，
#: 但 **cninfo 是直连调用（不经链路）**，没有会话级熔断——不短路的话，同一轮报告里
#: 每篇文档都会重新发起请求、重新白等一个超时预算（实测 601939 连试 4 次共 160s）。
#: 记下主机名后，后续请求**直接失败**（不发请求、不等超时），日志给出一次可读原因。
_unreachable_hosts: set[str] = set()
_unreachable_lock = threading.Lock()


def _host_of(url: str) -> str:
    """从 URL 取出主机名（无 scheme 时按路径处理，返回空串）。"""
    if "://" not in url:
        return ""
    return url.split("://", 1)[1].split("/", 1)[0]


def _mark_host_unreachable(url: str) -> None:
    """标记本会话该主机不可达（挂起型失败后调用）。"""
    host = _host_of(url)
    if not host:
        return
    with _unreachable_lock:
        if host not in _unreachable_hosts:
            _unreachable_hosts.add(host)
            logger.warning("[cninfo] 主机 %s 本会话判定不可达，后续请求直接跳过（不再逐次白等超时）", host)


def _is_host_unreachable(url: str) -> bool:
    """该主机是否已被本会话标记为不可达。"""
    host = _host_of(url)
    if not host:
        return False
    with _unreachable_lock:
        return host in _unreachable_hosts


def reset_cninfo_unreachable() -> None:
    """清空「主机不可达」会话标记（测试隔离 / 用户手动重试用）。"""
    with _unreachable_lock:
        _unreachable_hosts.clear()


def _get_limiter() -> Any:
    """模块级限速器（惰性构建单例）。"""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                from src.python.core.throttle import RateLimiter

                _limiter = RateLimiter({SOURCE_ID: _MIN_INTERVAL})
    return _limiter


def reset_cninfo_limiter() -> None:
    """丢弃限速器单例（测试隔离用）。"""
    global _limiter
    with _limiter_lock:
        _limiter = None
    reset_cninfo_unreachable()


# ═══════════════════════════════════════════════════════════════
#  HTTP（带限速；失败返回 None，不抛异常）
# ═══════════════════════════════════════════════════════════════


def _with_transient_retry(
    label: str, do_request: Callable[[], Any], *, url: str = "", timeout: float | None = None
) -> Any:
    """执行一次 HTTP 请求；**连接级瞬时失败**按策略退避重试（限速每次尝试前生效）。

    背景（本机实测）：到 cninfo 的**首个连接**常被丢弃（http/https 均见 8s 超时，
    随后立即 200）——若直连取数不做重试，冷启动抖动即让整只标的丢掉备源候选
    （orgId 解析失败 → 公告列表为空 → 备源不可用）；而这三条直接调用路径
    （orgId / 公告列表 / PDF 下载）都**不经 Provider Chain**，拿不到链路的同源重试。

    连接级重试脚手架（策略/挂起判据/重试日志/尝试计数）收敛于
    ``providers/_utils.with_connect_retry``；本函数只保留**直连调用方的降级契约**：
    重试耗尽 / 挂起 / 非瞬时失败 → 记日志并返回 ``None``（cninfo 三条路径无链路承接上抛，
    故在此吞掉异常）。

    Args:
        label: 日志中的请求标识（路径或完整 URL）。
        do_request: 实际执行一次的请求（无参闭包）。
        url: 该请求的 URL；提供时参与「主机不可达短路」与挂起标记。
        timeout: 单次请求超时预算；None 取 ``_TIMEOUT``（元数据类接口），
            PDF 下载传入 ``_PDF_TIMEOUT``。
    """
    if url and _is_host_unreachable(url):
        logger.debug("[cninfo] 主机本会话不可达，跳过：%s", label)
        set_last_reason("巨潮主机本会话不可达")
        return None

    limiter = _get_limiter()
    tried = {"n": 0}
    _timeout = _TIMEOUT if timeout is None else timeout

    def _before_attempt() -> None:
        tried["n"] += 1
        limiter.acquire(SOURCE_ID)

    try:
        return with_connect_retry(
            do_request,
            timeout=_timeout,
            log_tag="cninfo",
            label=label,
            before_attempt=_before_attempt,
        )
    except Exception as e:  # 瞬时重试耗尽 / 非瞬时失败：降级为 None（不计熔断）
        suffix = f"（已试 {tried['n']} 次）" if tried["n"] > 1 else ""
        logger.warning("[cninfo] 请求失败 %s: %s%s", label, e, suffix)
        if url and _looks_like_hang(e, _timeout):
            _mark_host_unreachable(url)
            set_last_reason("巨潮连接超时（主机不可达）")
        return None


def _looks_like_hang(exc: BaseException, timeout: float) -> bool:
    """该异常是否属「挂起型」：连接/读超时（与 ``with_connect_retry`` 的判据同源）。"""
    from src.python.core.retry import is_transient_exception

    if not is_transient_exception(exc):
        return False
    return "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower()


def _post_once(url: str, data: dict[str, Any]) -> Any:
    """单次限速 POST（限速在调用方统一获取）。"""
    with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
        return client.post(url, data=data, headers=_HEADERS)


def _get_once(url: str, timeout: float | None = None) -> Any:
    """单次限速 GET（限速在调用方统一获取）。"""
    with make_http_client(timeout=_TIMEOUT if timeout is None else timeout, follow_redirects=True) as client:
        return client.get(url, headers=_HEADERS)


def _post_json(path: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """限速 POST 取 JSON；失败返回 None（不计熔断，交链路/编排降级）。

    连接级瞬时失败由 ``_with_transient_retry`` 退避重试一次；HTTP 429 另有自己的退避分支。
    """
    url = f"{_BASE}{path}"
    resp = _with_transient_retry(path, lambda: _post_once(url, data), url=url)
    if resp is None:
        return None  # 失败原因已由 _with_transient_retry 写入 last-reason
    if resp.status_code == 429:
        delay = interval_delay(_RATE_LIMIT_POLICY.delay_for(1))  # 等待算式统一走 interval 原语
        logger.warning("[cninfo] 触发限速（HTTP 429），%.1fs 后重试一次", delay)
        time.sleep(delay)
        resp = _with_transient_retry(path, lambda: _post_once(url, data), url=url)
        if resp is None:
            return None
    if resp.status_code != 200:
        logger.warning("[cninfo] 请求 %s 返回 HTTP %d", path, resp.status_code)
        set_last_reason(f"HTTP {resp.status_code}")
        return None
    try:
        payload = resp.json()
    except ValueError:
        logger.warning("[cninfo] 响应非 JSON（%s）", path)
        set_last_reason("响应非 JSON")
        return None
    # 同一接口的两种合法形状都放行：``hisAnnouncement/query`` 返回 dict
    # （``announcements``），而 ``information/topSearch/query`` 返回**数组**
    # （[{"code", "orgId", ...}]）——早期只放行 dict，导致 orgId 解析恒失败。
    return payload if isinstance(payload, (dict, list)) else None


def _get_bytes(url: str) -> bytes | None:
    """限速 GET 取二进制（公告 PDF）；失败返回 None。

    PDF 原文动辄几十 MB，与元数据接口共用 20s 预算必然在慢链路下失败——单独用
    ``_PDF_TIMEOUT``（60s），使「链路慢但仍可达」的年报能真正下下来。
    """
    resp = _with_transient_retry(url, lambda: _get_once(url, _PDF_TIMEOUT), url=url, timeout=_PDF_TIMEOUT)
    if resp is None:
        return None
    if resp.status_code != 200:
        logger.warning("[cninfo] 下载 %s 返回 HTTP %d", url, resp.status_code)
        return None
    content = resp.content
    return bytes(content) if content else None


# ═══════════════════════════════════════════════════════════════
#  取数原语
# ═══════════════════════════════════════════════════════════════


def _column_for_code(code: str) -> str:
    """cninfo 查询的栏目参数（映射收敛到 code_utils，与其余判定同表维护）。"""
    return get_exchange_category(code)


def resolve_org_id(code: str) -> str | None:
    """按证券代码解析 cninfo orgId（列表查询的必需参数）；按代码缓存。

    Returns:
        ``"{code},{orgId}"`` 组合串；解析失败返回 None。
    """
    code = str(code or "").strip()
    if not code:
        return None
    cache_key = f"{ORGID_PREFIX}{code}"
    cached = cache_get(cache_key, get_ttl("report", cache_key))
    if isinstance(cached, str) and cached:
        return cached
    payload = _post_json(
        "/new/information/topSearch/query",
        {"keyWord": code, "maxSecNum": 10, "maxListNum": 10},
    )
    # 该接口返回**数组**（实测：[{"code": "600900", "orgId": "gssh0600900", ...}]）；
    # 保留 dict 形状兼容（历史/其他部署可能包一层）。
    if isinstance(payload, list):
        items: Any = payload
    else:
        items = (payload or {}).get("keyBoardList") or (payload or {}).get("list") or []
    org_id = ""
    for item in items if isinstance(items, list) else []:
        if str(item.get("code") or "") != code:
            continue
        org_id = str(item.get("orgId") or "")
        break
    if not org_id and isinstance(items, list) and items:
        org_id = str(items[0].get("orgId") or "")
    if not org_id:
        logger.info("[cninfo] 代码 %s 未解析到 orgId", code)
        set_last_reason("未解析到 orgId（源侧无该代码档案或连接失败）")
        return None
    resolved = f"{code},{org_id}"
    cache_set(cache_key, resolved)
    return resolved


def _classify_title(title: str) -> tuple[str, str]:
    """公告标题 → (标准 doc_type, 期末月日)；非财报正文返回 ("", "")。"""
    if any(k in title for k in _SKIP_TITLE_KEYWORDS):
        return "", ""
    for keyword, doc_type, mmdd in _DOC_TYPE_RULES:
        if keyword in title:
            return doc_type, mmdd
    return "", ""


def fetch_report_listings(code: str) -> list[dict[str, Any]] | None:
    """取某 A 股代码的公告列表，归一为**与主源索引同一形状**的元数据。

    元数据形状对齐 ``providers/datasink.fetch_report_documents`` 的条目：
    ``{id, doc_type, report_period, title, announcement_time, word_count,
    adjunct_url, source}``——编排层候选排序/报告期回溯逻辑因此零改动复用。

    Returns:
        元数据列表（财报正文条目，按披露时间倒序）；无命中/失败返回 None。
    """
    code = str(code or "").strip()
    if not code:
        return None
    cache_key = f"{INDEX_PREFIX}{code}"
    cached = cache_get(cache_key, get_ttl("report", cache_key))
    if cached is not None:
        return cached if isinstance(cached, list) else None

    stock = resolve_org_id(code)
    if not stock:
        return None
    end = date.today()
    start = end - timedelta(days=_LIST_WINDOW_DAYS)
    payload = _post_json(
        "/new/hisAnnouncement/query",
        {
            "pageNum": 1,
            "pageSize": _LIST_PAGE_SIZE,
            "column": _column_for_code(code),
            "tabName": "fulltext",
            "plate": "",
            "stock": stock,
            "searchkey": "",
            "secid": "",
            "category": _FINANCIAL_CATEGORIES,
            "trade": "",
            "seDate": f"{start.isoformat()}~{end.isoformat()}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        },
    )
    announcements = (payload or {}).get("announcements")
    if not isinstance(announcements, list) or not announcements:
        return None
    items: list[dict[str, Any]] = []
    for ann in announcements:
        title = str(ann.get("announcementTitle") or "").strip()
        doc_type, mmdd = _classify_title(title)
        if not doc_type:
            continue
        year_match = _YEAR_RE.search(title)
        if not year_match:
            continue
        adjunct_url = str(ann.get("adjunctUrl") or "").strip()
        if not adjunct_url:
            continue
        items.append(
            {
                "id": str(ann.get("announcementId") or ""),
                "doc_type": doc_type,
                "report_period": f"{year_match.group(1)}-{mmdd}",
                "title": title,
                "announcement_time": int(ann.get("announcementTime") or 0),
                "word_count": 0,
                "adjunct_url": adjunct_url,
                "source": SOURCE_ID,
            }
        )
    if not items:
        return None
    items.sort(key=lambda i: (str(i.get("report_period") or ""), int(i.get("announcement_time") or 0)), reverse=True)
    cache_set(cache_key, items)
    logger.info("[cninfo] %s 公告索引：%d 篇财报正文候选", code, len(items))
    return items


def _parse_pdf_text(pdf_bytes: bytes) -> str:
    """PDF 字节 → 纯文本（pdfplumber；惰性导入，缺库/解析失败返回空串）。

    页数设上限防异常文件撑爆内存；逐页提取后以换行拼接（保留段落边界，
    供关键词定位与目录行判定使用）。
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("[cninfo] 未安装 pdfplumber，无法解析公告 PDF（pip install 'pdfplumber>=0.11,<1.0'），本次跳过")
        return ""
    try:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:_PDF_MAX_PAGES]:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)
        return "\n".join(pages)
    except Exception as e:  # 损坏/加密/非标准 PDF：返回空，交链路降级
        logger.warning("[cninfo] PDF 解析失败：%s", e)
        return ""


def fetch_report_text(announcement_id: str, adjunct_url: str) -> str:
    """取公告正文纯文本（下载 + 解析，按公告缓存）。

    Args:
        announcement_id: 公告 ID（缓存键）。
        adjunct_url: 相对下载路径（拼到 static 站）。

    Returns:
        纯文本；下载/解析失败返回空串（调用方按无正文降级）。
    """
    announcement_id = str(announcement_id or "").strip()
    if not announcement_id or not adjunct_url:
        return ""
    cache_key = f"{TEXT_PREFIX}{announcement_id}"
    cached = cache_get(cache_key, get_ttl("report", cache_key))
    if isinstance(cached, str):
        return cached
    url = adjunct_url if adjunct_url.startswith("http") else f"{_STATIC_BASE}/{adjunct_url.lstrip('/')}"
    pdf_bytes = _get_bytes(url)
    if not pdf_bytes:
        return ""
    text = _parse_pdf_text(pdf_bytes)
    if text:
        cache_set(cache_key, text)
    return text
