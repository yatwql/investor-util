"""天天基金 F10 交易费率页 — 直连抓取、轻量解析、备链路（akshare 封装）与载荷准入。

数据源：F10 基金档案·交易费率页（``fund.eastmoney.com/f10/jjfl_{code}.html``）——
**申购费率（天天基金优惠档）与赎回费阶梯两张表同页**，一次抓取两侧俱得。

  - 主链路：直连页面 + 本模块正则表格解析（表头定位：赎回表「适用期限+赎回费率」；
    申购表在「适用金额」表中**优先取带「优惠」的天天基金优惠表**，无优惠表退原生
    「适用金额+费率」表；管理费/托管费等其余表不匹配表头、自动跳过）
  - 备链路：akshare ``fund_fee_em`` 封装（h4 标题 + pandas 解析，与主链路解析器
    冗余、上游页面族相同，host 略异 fundf10 子域；**仅覆盖赎回阶梯**——申购档位
    由全量申购状态表单档（table_single）/配置兜底承接，如实降级不冒充）
  - 兜底：过期缓存（``fetch_with_fallback`` 统一路径，见 ``fetcher/fund_fee.py``）

原始行契约（与 ``analysis/trade_cost_model.py`` 解析器输入逐一对齐）：

  - ``redemption_rows``: ``[[适用期限标签, 费率文本], ...]``（**非空**——准入硬条件；
    场内基金/股票页无赎回阶梯表 → 整载荷判失败走降级，费用按未知标注）
  - ``purchase_rows``: ``[[适用金额标签, 费率单元格], ...]``（单元格可含
    ``1.50% &nbsp;|&nbsp; 0.15%`` 原|优惠双值；可为空——C 类/无优惠档如实为空）

载荷语义版本 ``fee_schema``（写入缓存时随载荷同存，读侧
:func:`fee_payload_is_valid` 为准入判据：版本不符即视为未命中丢弃重取）。
"""

from __future__ import annotations

import html as _html
import logging
import re
from datetime import datetime
from typing import Any

from src.python.core.constants import BEIJING_TZ
from src.python.core.http_client import make_http_client

logger = logging.getLogger("invest")

# ── 端点与请求头（与 tiantian_purchase 同口径：免鉴权，Referer + UA） ──────

_FEE_URL = "https://fund.eastmoney.com/f10/jjfl_{code}.html"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_TIMEOUT = 15.0

#: 载荷语义版本——费率口径/行结构变更即递增，旧缓存按未命中丢弃（同 purchase_schema 习语）
FEE_SCHEMA_FIELD = "fee_schema"
FEE_SCHEMA = 1

_RE_TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.DOTALL | re.IGNORECASE)
_RE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_RE_CELL = re.compile(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", re.DOTALL | re.IGNORECASE)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_SPACE = re.compile(r"\s+")


# ═══════════════════════════════════════════════════════════════
#  载荷组装与准入校验（直连/备链路共用）
# ═══════════════════════════════════════════════════════════════


def stamp_fee_payload(redemption_rows: list[list[str]], purchase_rows: list[list[str]]) -> dict[str, Any]:
    """原始行 → 带语义版本与抓取时间的载荷（直连与 akshare 备链路共用单点）。"""
    return {
        "redemption_rows": redemption_rows,
        "purchase_rows": purchase_rows,
        "fetched_at": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
        FEE_SCHEMA_FIELD: FEE_SCHEMA,
    }


def _rows_shape_ok(rows: object) -> bool:
    """行结构体检：非空由调用方判定；此处只管每行 ≥2 列且前两格为非空字符串。"""
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return False
        if not all(isinstance(cell, str) and cell.strip() for cell in row[:2]):
            return False
    return True


def fee_payload_is_valid(payload: object) -> bool:
    """载荷准入校验（``cache_validate`` 与写侧 ``validate`` 共用同一判据）。

    校验项：
      1. 语义版本字段 ``fee_schema`` 等于当前版本（旧结构缓存一律作废）；
      2. ``fetched_at`` 非空时间串；
      3. ``redemption_rows`` 非空且逐行结构合法（**赎回阶梯是本数据类型的核心**，
         缺失即整载荷失败——场内基金页/解析漂移均落此，走备链路与配置兜底）；
      4. ``purchase_rows`` 为列表（可为空）且非空时逐行结构合法。
    """
    if not isinstance(payload, dict):
        return False
    if payload.get(FEE_SCHEMA_FIELD) != FEE_SCHEMA:
        return False
    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, str) or not fetched_at.strip():
        return False
    redemption = payload.get("redemption_rows")
    if not redemption or not _rows_shape_ok(redemption):
        return False
    purchase = payload.get("purchase_rows")
    if purchase is None:
        return False
    if purchase and not _rows_shape_ok(purchase):
        return False
    return True


# ═══════════════════════════════════════════════════════════════
#  主链路：直连页面 + 正则表格解析
# ═══════════════════════════════════════════════════════════════


def _cell_text(raw: str) -> str:
    """HTML 单元格 → 纯文本（剥标签、解实体、含 ``&nbsp;``/不换行空格的空白归一）。"""
    text = _RE_TAG.sub(" ", raw)
    text = _html.unescape(text)
    text = text.replace("\xa0", " ")
    return _RE_SPACE.sub(" ", text).strip()


def _extract_tables(html_text: str) -> list[list[list[str]]]:
    """页面 HTML → ``[表][行][格]`` 纯文本结构（格已归一，供表头识别与取行）。"""
    tables: list[list[list[str]]] = []
    for tbl in _RE_TABLE.findall(html_text):
        rows: list[list[str]] = []
        for row in _RE_ROW.findall(tbl):
            rows.append([_cell_text(cell) for cell in _RE_CELL.findall(row)])
        tables.append(rows)
    return tables


def parse_fee_page(html_text: object) -> dict[str, Any] | None:
    """F10 交易费率页 HTML → 载荷（纯解析，无 I/O；失败返回 None）。

    表头识别（实测页面共 9 表，仅认下列表头，其余——申购状态/起点/运作费用等
    ——自动跳过）：

      - 赎回阶梯：表头含「适用期限」与「赎回费率」（取首个匹配表，页面仅一张）
      - 申购档位：表头含「适用金额」；带「优惠」者优先（天天基金优惠档），
        否则取首个原生「费率」表

    无赎回阶梯表（场内基金/股票页）→ 判失败返回 None（走备链路与配置兜底），
    **不返回缺侧载荷冒充成功**。
    """
    if not isinstance(html_text, str) or not html_text.strip():
        return None

    redemption_rows: list[list[str]] | None = None
    purchase_rows: list[list[str]] = []
    purchase_is_discount = False
    for rows in _extract_tables(html_text):
        if not rows or not rows[0]:
            continue
        head = " ".join(rows[0])
        if "适用期限" in head and "赎回费率" in head:
            if redemption_rows is None:
                redemption_rows = [list(r[:2]) for r in rows[1:] if len(r) >= 2 and r[0] and r[1]]
            continue
        if "适用金额" in head:
            candidate = [list(r[:2]) for r in rows[1:] if len(r) >= 2 and r[0] and r[1]]
            if not candidate:
                continue
            is_discount = "优惠" in head
            if is_discount and not purchase_is_discount:
                purchase_rows, purchase_is_discount = candidate, True
            elif not purchase_rows and not purchase_is_discount:
                purchase_rows = candidate

    if not redemption_rows:
        logger.info("[基金费率] 页面无赎回费阶梯表（场内/结构变更），判解析失败")
        return None
    return stamp_fee_payload(redemption_rows, purchase_rows)


def fetch_fund_fee_page(code: str) -> dict[str, Any] | None:
    """直连抓取 F10 交易费率页并解析（主链路）。

    传输级异常（超时/断连/非 2xx）**向上抛出**——由 ``fetch_with_fallback``
    统一计为传输失败并累计熔断计数；解析失败返回 None（代码级空结果，不计熔断）。
    """
    url = _FEE_URL.format(code=code.strip())
    with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, headers=_HEADERS)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        text = resp.text
    return parse_fee_page(text)


# ═══════════════════════════════════════════════════════════════
#  备链路：akshare 封装（解析器冗余，仅赎回阶梯）
# ═══════════════════════════════════════════════════════════════


def fetch_fund_fee_page_via_akshare(code: str) -> dict[str, Any] | None:
    """备链路：``akshare.fund_fee_em(indicator="赎回费率")`` 封装解析。

    **冗余性质如实声明**：与主链路同一上游页面族（fundf10 子域），提供的是
    **解析器冗余**（正则表头定位 vs h4 标题 + pandas 读表），主解析器被改版
    击穿时另一条可能仍活；页面整体不可用时真正的可用性兜底是最外层过期缓存。
    本备链路**仅覆盖赎回阶梯**——申购档位由全量申购状态表单档/配置兜底承接。

    Returns:
        载荷（``purchase_rows`` 恒为空列表）；页面无赎回表（KeyError）/空表/
        结构不符 → None。akshare 内部网络异常向上抛出（按传输失败计熔断）。
    """
    import akshare as ak

    try:
        df = ak.fund_fee_em(symbol=code.strip(), indicator="赎回费率")
    except KeyError:
        logger.info("[基金费率] akshare 页面无赎回费率表 [%s]，判取不到", code)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    columns = list(getattr(df, "columns", []))
    if len(columns) < 2:
        return None
    redemption_rows: list[list[str]] = []
    for record in df.to_dict("records"):
        label = str(record.get(columns[0]) or "").strip()
        rate = str(record.get(columns[1]) or "").strip()
        if label and rate:
            redemption_rows.append([label, rate])
    if not redemption_rows:
        return None
    return stamp_fee_payload(redemption_rows, [])
