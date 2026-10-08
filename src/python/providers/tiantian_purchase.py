"""天天基金申购状态总表 — 直连抓取、轻量解析、备链路（akshare 封装）与载荷准入。

数据源：天天基金官方数据页（``fund.eastmoney.com/Fund_sgzt_bzdm.html``）后端全量接口

  GET https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx
      ?t=8&page=1,50000&js=reData&sort=fcode,asc
  响应：``var reData={datas:[[...],...], ...}`` —— JS 对象字面量（裸 key），
  剥前缀后给裸 key 补引号即可 ``json.loads``（不引 demjson）。

原始行按位置解析（无键数组，13 列）：

  [0]基金代码 [1]基金简称 [2]基金类型 [3]最新净值 [4]净值报告日 [5]申购状态
  [6]赎回状态 [7]下一开放日 [8]购买起点 [9]日累计限定金额 [10]- [11]- [12]手续费

  - [12] 手续费 = **单档申购费率（天天基金优惠）**，如 ``0.15%`` → 载荷
    ``purchase_fee_rate``（小数 0.0015；``0.00%`` 为已知 0，空/不可解析为未知
    None）。它是 whatif 交易成本申购腿在 F10 优惠档不可得时的单档来源
    （``table_single``），语义与准入随 :data:`PURCHASE_SCHEMA` 一同演进。

稳定性四层保障（设计文档 §3.4，硬约束）中的「载荷准入校验」由
:func:`purchase_status_payload_is_valid` 承担——写侧（provider 成功后、入缓存前）
与读侧（含过期缓存展示）同用一份判据；值域体检（代码 6 位数字 / 申购状态枚举 /
限额非负数值 / 下一开放日日期格式）防上游插列导致的**位置错位整体误过**。
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from typing import Any


from src.python.core.constants import BEIJING_TZ
from src.python.core.http_client import make_http_client

logger = logging.getLogger("invest")

# ── 端点与请求头（与 tiantian_base 同口径：免鉴权，Referer + UA） ──────────

_ENDPOINT_URL = "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx"
_ENDPOINT_PARAMS = {
    "t": "8",
    "page": "1,50000",
    "js": "reData",
    "sort": "fcode,asc",
}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_TIMEOUT = 15.0

#: 载荷语义版本——写入缓存时随载荷同存，读侧以 :func:`purchase_status_payload_is_valid`
#: 为准入判据：版本不符即视为未命中、丢弃重取（与 ``rank_schema``/``hold_schema`` 同习语）。
#: v2（2026-10-06）：新增 ``purchase_fee_rate``（col12 手续费，小数）；v1 旧缓存自动作废。
PURCHASE_SCHEMA_FIELD = "purchase_schema"
PURCHASE_SCHEMA = 2

#: 载荷准入的最少行数（实测全量约 2.7 万行，骤降即异常——行数不足判失败走降级）
MIN_ACCEPT_ROWS = 20_000

#: 原始行最少列数（位置解析的结构下限；上游插入列不左移既有位置，追加列不拦截）
_ROW_MIN_FIELDS = 13

#: 响应前缀（剥掉后为 JS 对象字面量）
_PAYLOAD_PREFIX = "var reData="

#: 已知申购状态值域（2026-10-03 全量实测枚举；空串为上游合法空值）
KNOWN_PURCHASE_STATUSES = frozenset({"开放申购", "限大额", "暂停申购", "场内交易", "封闭期", "认购期", ""})
#: 已知赎回状态值域（同上实测）
KNOWN_REDEMPTION_STATUSES = frozenset({"开放赎回", "暂停赎回", "场内交易", "封闭期", "认购期", ""})

_RE_NEXT_OPEN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_BARE_KEY = re.compile(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")

# 原始行位置索引（0-based，见模块 docstring 列序）
_COL_CODE, _COL_NAME, _COL_STATUS, _COL_REDEMPTION = 0, 1, 5, 6
_COL_NEXT_OPEN, _COL_MIN_PURCHASE, _COL_DAILY_LIMIT = 7, 8, 9
_COL_FEE = 12


# ═══════════════════════════════════════════════════════════════
#  载荷组装与准入校验（直连/备链路共用）
# ═══════════════════════════════════════════════════════════════


def stamp_purchase_payload(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """解析产物 → 带语义版本与抓取时间的载荷（直连与 akshare 备链路共用单点）。

    Args:
        rows: ``{基金代码: {"purchase_status", "redemption_status",
            "next_open_date", "daily_limit", "min_purchase",
            "purchase_fee_rate"}}``（``purchase_fee_rate`` 小数，None=未知）

    Returns:
        ``{"rows", "fetched_at", purchase_schema}``；``fetched_at`` 为北京时区
        ISO 时间串（陈旧阶梯按其与交易日历的距离判定）。
    """
    return {
        "rows": rows,
        "fetched_at": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
        PURCHASE_SCHEMA_FIELD: PURCHASE_SCHEMA,
    }


def _limit_to_float(raw: Any) -> float | None:
    """日累计限定金额 → float；空/0/缺失 → None（「限额未知」的解析层单点转换）。

    非空且不可解析、或为负数时抛 :class:`ValueError`——这类值域异常意味着
    上游列结构变了（位置错位），本函数的调用方应判整次解析失败走降级，
    绝不把垃圾值带进缓存。
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"日累计限定金额不可解析: {text!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"日累计限定金额非负性异常: {text!r}")
    return None if value == 0 else value


def _optional_float(raw: Any) -> float | None:
    """可选数值字段（购买起点等）宽松解析：空/不可解析 → None（非准入关键字段）。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _fee_percent(text: str) -> float | None:
    """col12 手续费文本（``0.15%``）→ 小数费率；空/``---``/不合理 → None（未知）。

    单档来源复用 ``trade_cost_model.parse_fee_percent`` 单源（含 ≥100% 拒绝）——
    ``0.00%`` 合法返回 0.0（**已知 0**，与未知 None 严格区分）。
    """
    from src.python.analysis.fee_schedule_model import parse_fee_percent

    return parse_fee_percent(text)


def purchase_status_payload_is_valid(payload: object) -> bool:
    """载荷准入校验（``cache_validate`` 与写侧 ``validate`` 共用同一判据）。

    校验项（设计文档 §3.4-3）：
      1. 可解析且行数 ≥ :data:`MIN_ACCEPT_ROWS`（正常 2.7 万，骤降即异常）；
      2. 载荷携带语义版本字段 ``purchase_schema`` 且等于当前版本；
      3. 必需字段齐全（每行六键契约）；
      4. 值域体检（防位置错位整体误过）：基金代码 100% 为 6 位数字、
         申购/赎回状态 ∈ 已知枚举、日累计限定金额为 None 或非负有限数值、
         下一开放日为空或 ``YYYY-MM-DD``、申购费率为 None 或 [0,1) 有限小数。

    任一不满足 → 本次抓取/缓存读取判定失败（走降级，旧缓存不被污染；
    损坏/截断的缓存体不得流入展示层）。
    """
    if not isinstance(payload, dict):
        return False
    if payload.get(PURCHASE_SCHEMA_FIELD) != PURCHASE_SCHEMA:
        return False
    rows = payload.get("rows")
    if not isinstance(rows, dict) or len(rows) < MIN_ACCEPT_ROWS:
        return False
    required = (
        "purchase_status",
        "redemption_status",
        "next_open_date",
        "daily_limit",
        "min_purchase",
        "purchase_fee_rate",
    )
    for code, row in rows.items():
        if not (isinstance(code, str) and len(code) == 6 and code.isdigit()):
            return False
        if not isinstance(row, dict) or any(k not in row for k in required):
            return False
        if row["purchase_status"] not in KNOWN_PURCHASE_STATUSES:
            return False
        if row["redemption_status"] not in KNOWN_REDEMPTION_STATUSES:
            return False
        limit = row["daily_limit"]
        if limit is not None and not (isinstance(limit, (int, float)) and math.isfinite(limit) and limit >= 0):
            return False
        fee = row["purchase_fee_rate"]
        if fee is not None and not (
            isinstance(fee, (int, float)) and not isinstance(fee, bool) and math.isfinite(fee) and 0 <= fee < 1
        ):
            return False
        next_open = row["next_open_date"]
        if not isinstance(next_open, str) or (next_open and not _RE_NEXT_OPEN.match(next_open)):
            return False
    return True


# ═══════════════════════════════════════════════════════════════
#  主链路：直连端点
# ═══════════════════════════════════════════════════════════════


def parse_purchase_table(text: str) -> dict[str, Any] | None:
    """响应文本 → 载荷（纯解析，无 I/O）。

    解析失败（前缀/JSON 结构/行宽/数值异常）返回 None——调用方据此走备链路，
    垃圾载荷绝不入缓存。值域体检（枚举/代码格式）在
    :func:`purchase_status_payload_is_valid` 中统一执行，此处只管结构与数值。
    """
    if not isinstance(text, str):
        return None
    body = text.strip()
    if body.startswith(_PAYLOAD_PREFIX):
        body = body[len(_PAYLOAD_PREFIX) :].strip()
    if not body.startswith("{"):
        logger.warning("[申购状态] 响应缺少 var reData= 前缀或对象体（格式疑似变更）")
        return None
    try:
        parsed = json.loads(_RE_BARE_KEY.sub(r'\1"\2":', body))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("[申购状态] 响应 JSON 解析失败: %s", exc)
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("datas"), list) or not parsed["datas"]:
        logger.warning("[申购状态] 响应缺少 datas 数组（格式疑似变更）")
        return None

    rows: dict[str, dict[str, Any]] = {}
    for raw_row in parsed["datas"]:
        if not isinstance(raw_row, (list, tuple)) or len(raw_row) < _ROW_MIN_FIELDS:
            logger.warning("[申购状态] 行结构异常（列数不足 %d），判定解析失败", _ROW_MIN_FIELDS)
            return None
        try:
            daily_limit = _limit_to_float(raw_row[_COL_DAILY_LIMIT])
        except ValueError as exc:
            logger.warning("[申购状态] %s", exc)
            return None
        code = str(raw_row[_COL_CODE]).strip()
        rows[code] = {
            "purchase_status": str(raw_row[_COL_STATUS]).strip(),
            "redemption_status": str(raw_row[_COL_REDEMPTION]).strip(),
            "next_open_date": str(raw_row[_COL_NEXT_OPEN]).strip(),
            "daily_limit": daily_limit,
            "min_purchase": _optional_float(raw_row[_COL_MIN_PURCHASE]),
            "purchase_fee_rate": _fee_percent(str(raw_row[_COL_FEE])),
        }
    return stamp_purchase_payload(rows)


def fetch_fund_purchase_table() -> dict[str, Any] | None:
    """直连端点抓取全量申购状态表（主链路，每日 1 次全量的使用模式）。

    传输级异常（超时/断连/非 2xx）**向上抛出**——由 ``fetch_with_fallback``
    统一计为传输失败并累计天天基金熔断计数（传输失败同样计入）；解析失败返回 None
    （代码级空结果，不计入熔断）。
    """
    with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(_ENDPOINT_URL, params=_ENDPOINT_PARAMS, headers=_HEADERS)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        text = resp.text
    return parse_purchase_table(text)


# ═══════════════════════════════════════════════════════════════
#  备链路：akshare 封装（解析器冗余，与主链路共享上游端点）
# ═══════════════════════════════════════════════════════════════


def fetch_fund_purchase_table_via_akshare() -> dict[str, Any] | None:
    """备链路：``akshare.fund_purchase_em()`` 封装解析（应对主端点格式变更）。

    **冗余性质如实声明**：与主链路共享同一上游端点，提供的是**解析器冗余**
    （直连解析器 vs akshare 封装，任一被格式变更击穿时另一条可能仍活）而非
    源冗余；端点整体不可用时两链同时失败，真正的可用性兜底是最外层过期缓存。

    akshare 侧 ``errors="coerce"`` 把不可解析数值归为 NaN，此处归 None
    （限额未知），故备链路对数值脏数据更宽松；空 DataFrame/None 视为取不到。
    ``手续费`` 列 akshare 已剥 ``%`` 并转数值（百分数，如 0.15），此处折为小数；
    NaN/缺列/不可解析 → None（未知）。
    """
    import akshare as ak

    df = ak.fund_purchase_em()
    if df is None or getattr(df, "empty", True):
        return None
    rows: dict[str, dict[str, Any]] = {}
    for record in df.to_dict("records"):
        code = str(record.get("基金代码") or "").strip()
        if not code:
            continue
        limit = record.get("日累计限定金额")
        try:
            limit_val = float(limit)
            limit_val = None if (math.isnan(limit_val) or limit_val == 0) else limit_val
        except (TypeError, ValueError):
            limit_val = None
        next_open = record.get("下一开放日")
        rows[code] = {
            "purchase_status": str(record.get("申购状态") or "").strip(),
            "redemption_status": str(record.get("赎回状态") or "").strip(),
            "next_open_date": str(next_open or "")[:10],
            "daily_limit": limit_val,
            "min_purchase": _optional_float(record.get("购买起点")),
            "purchase_fee_rate": _percent_number_to_rate(record.get("手续费")),
        }
    return stamp_purchase_payload(rows)


def _percent_number_to_rate(raw: Any) -> float | None:
    """akshare 百分数数值（0.15）→ 小数费率 0.0015；NaN/不可解析 → None。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0 or value >= 100:
        return None
    return round(value / 100.0, 6)
