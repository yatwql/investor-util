"""申购状态（限购）展示装配与展示单源 — 契约构建 / 时效分档 / 单元格文案 / 口径脚注。

数据契约 ``purchase_status_data``（与 ``financial_indicator_data`` 同形）::

    {"available": bool, "reason": str | None, "rows": dict,
     "fetched_at": str | None, "source": str | None,
     "constraint_block": str,     # 构建期渲染：申购限购约束块
                                  # （准入不满足 → ""；不传持仓 → ""）
     "restricted_index": dict}   # 编排层注入：受限标的预格式化索引
                                 # （准入不满足 → {}；开关关时契约整体 None）

  - 开关 ``fund_purchase_limit`` 关闭 → 构建函数返回 None（渲染层保持既有输出）
  - 全链路取数失败 → ``available=False``（渲染层静默隐列，``reason`` 供排查）

设计文档 ``docs/plan/fund-purchase-limit-design.md`` §4.4 单源清单的落地——
下述逻辑出现第二份实现即为新增技术债：

  - 陈旧阶梯（≤3 / 4~7 / >7 交易日，按交易日历计、长假不计入）
    → :func:`stale_level`（Excel / HTML 共用同一判定）
  - 0 元 / 缺失限额 → 「限额未知」：解析层已单点转换（providers/tiantian_purchase
    的 ``_limit_to_float``），本层沿用 ``daily_limit is None`` 判据，不重写数值解释
  - 口径脚注文案 → :func:`purchase_status_footnote`（两套渲染同源取文案）
  - 代码 → 状态查询 → :func:`get_purchase_status`（渲染层不直接碰 rows 字典）
  - 单元格文案 → :func:`format_purchase_status_cell`（两套渲染共用）
  - 受限行筛选与索引 → :func:`_filter_restricted_rows` /
    :func:`build_restricted_index`（受限状态集与字段值与单元格同源，
    建议层判定只读消费预格式化字段，不复制数值解释）

展示语义（设计文档 §5.2 / §5.4）：宁可缺不可错——数据时效超限、查无此码、
场内交易一律显示「—」，**绝不猜测「开放申购」**。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("invest")

__all__ = [
    "STALE_FRESH_MAX_DAYS",
    "STALE_EXPIRE_MAX_DAYS",
    "PURCHASE_STATUS_FOOTNOTE",
    "build_purchase_status_data",
    "stale_level",
    "get_purchase_status",
    "format_purchase_status_cell",
    "purchase_status_footnote",
    "purchase_column_visible",
    "build_restricted_index",
    "build_purchase_constraint_block",
]

#: 时效第一档上限（交易日）：距抓取 ≤3 个交易日 → 正常展示
STALE_FRESH_MAX_DAYS = 3
#: 时效第二档上限（交易日）：4 ~ 7 个交易日 → 展示并标「数据陈旧」；>7 → 显示「—」
STALE_EXPIRE_MAX_DAYS = 7

#: 口径脚注（设计文档 §5.3，唯一文案来源；Excel 与 HTML 同源引用）
PURCHASE_STATUS_FOOTNOTE = (
    "申购状态与日限额为天天基金渠道口径，每日更新；"
    "其他渠道（基金公司直销、银行等）限额可能不同，实际以下单渠道显示为准。"
)


def build_purchase_status_data(
    config: dict | None = None,
    holdings_details: list[dict] | None = None,
) -> dict | None:
    """构建申购状态数据契约（``purchase_status_data``）。

    流程：功能开关 ``fund_purchase_limit`` 关闭 → None（渲染层保持既有输出）；
    开启 → 经会话缓存单次取全量表（chain + 载荷准入 + 过期缓存兜底），
    成功返回 ``available=True`` 契约，全链失败返回 ``available=False`` 降级契约
    （不抛异常、不阻断报告主链路）。

    契约字段 ``constraint_block`` 在构建期由
    :func:`build_purchase_constraint_block` 渲染一次（准入不过 → ""）。

    Args:
        config: 完整配置字典（开关读注册表，形参为与同类装配函数一致的签名兼容）
        holdings_details: 持仓明细（渲染约束块用的最小形态，至少含 name/code；
            缺省/空 → ``constraint_block=""``——无 LLM 消费方的路径
            （both/basic/What-if 取契约）可不传，块缺席零开销）

    Returns:
        ``{available, reason, rows, fetched_at, source, constraint_block}`` 或 None
        （开关关闭）
    """
    from src.python.config import is_enable_fund_purchase_limit

    if not is_enable_fund_purchase_limit(config):
        return None

    from src.python.fetcher.fund_purchase import fetch_fund_purchase_status_cached

    try:
        payload = fetch_fund_purchase_status_cached()
    except Exception:  # noqa: BLE001 — 取数层任何异常都不得阻断报告主链路（四层降级末层）
        logger.warning("申购状态取数异常，本列静默隐列", exc_info=True)
        payload = None
    if not payload:
        contract: dict = {
            "available": False,
            "reason": "申购状态全链路取数失败且无可用缓存",
            "rows": {},
            "fetched_at": None,
            "source": None,
        }
    else:
        contract = {
            "available": True,
            "reason": None,
            "rows": payload.get("rows") or {},
            "fetched_at": payload.get("fetched_at"),
            "source": payload.get("source"),
        }
    contract["constraint_block"] = build_purchase_constraint_block(contract, holdings_details)
    return contract


def purchase_column_visible(purchase_status_data: dict | None) -> bool:
    """「申购状态」列是否渲染（开关关闭 / 取数失败 → False，渲染层静默隐列）。"""
    return bool(purchase_status_data) and bool(purchase_status_data.get("available"))


def stale_level(fetched_at: str | None, today: str | None = None) -> str:
    """数据时效分档（陈旧阶梯，按**交易日**计；长假不计入，数据源本就不更新）。

    Args:
        fetched_at: 抓取时间（北京时区 ISO 串，契约 ``fetched_at`` 字段）
        today: 判定基准日 ``YYYY-MM-DD``（缺省取当前北京时区日期；测试可注入）

    Returns:
        ``"fresh"``（≤3 交易日，正常展示）/ ``"stale"``（4~7 交易日，展示并标
        数据陈旧）/ ``"expired"``（>7 交易日或时间不可解析——一律显示「—」，
        过时的限购信息比缺失更误导）
    """
    from src.python.core.constants import BEIJING_TZ
    from src.python.core.trading_calendar import count_trading_days_elapsed

    if not fetched_at:
        return "expired"
    try:
        start = datetime.fromisoformat(str(fetched_at)).date()
    except ValueError:
        return "expired"
    if today is None:
        end = datetime.now(BEIJING_TZ).date()
    else:
        try:
            end = date.fromisoformat(today)
        except ValueError:
            return "expired"
    elapsed = count_trading_days_elapsed(start.isoformat(), end.isoformat())
    if elapsed is None:
        return "expired"
    if elapsed <= STALE_FRESH_MAX_DAYS:
        return "fresh"
    if elapsed <= STALE_EXPIRE_MAX_DAYS:
        return "stale"
    return "expired"


def get_purchase_status(purchase_status_data: dict | None, code: str) -> dict[str, Any] | None:
    """按代码查询申购状态行（渲染层唯一入口，不直接触碰 rows 字典）。"""
    if not purchase_column_visible(purchase_status_data):
        return None
    rows = (purchase_status_data or {}).get("rows") or {}
    row = rows.get(str(code))
    return row if isinstance(row, dict) else None


def _fmt_limit(limit: float) -> str:
    """日限额 → 千分位展示（整数不补小数位）。"""
    value = float(limit)
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _fmt_next_open(next_open: str) -> str:
    """``YYYY-MM-DD`` → 「M月D日」（无法解析时原样返回调用方兜底）。"""
    try:
        d = date.fromisoformat(next_open)
    except ValueError:
        return next_open
    return f"{d.month}月{d.day}日"


def format_purchase_status_cell(
    purchase_status_data: dict | None,
    code: str,
    level: str | None = None,
) -> str:
    """单元格文案（Excel 与 HTML 共用的唯一实现）。

    规则（设计文档 §5.2 / §5.4）：
      - 时效 ``expired`` / 契约不可用 → 「—」（宁缺毋错）
      - 查无此码（场内份额、新基金未入库）→ 「—」，绝不默认「开放申购」
      - 开放申购 → 🟢 开放；限大额 → 🟡 限大额 + 日限 X 元
        （限额缺失 → 「限额未知」，风险 R4）；暂停申购 → 🔴 暂停 + 下一开放日
      - 场内交易 / 空状态 → 「—」（场内持仓无申购语义）；其余真实状态原样展示（⚪ 前缀）
    """
    if level is None:
        level = stale_level((purchase_status_data or {}).get("fetched_at"))
    if level == "expired" or not purchase_column_visible(purchase_status_data):
        return "—"
    row = get_purchase_status(purchase_status_data, code)
    if row is None:
        return "—"
    status = str(row.get("purchase_status") or "")
    if status == "开放申购":
        return "🟢 开放"
    if status == "限大额":
        limit = row.get("daily_limit")
        if limit is None:
            return "🟡 限大额 限额未知"
        return f"🟡 限大额 日限 {_fmt_limit(limit)} 元"
    if status == "暂停申购":
        next_open = str(row.get("next_open_date") or "")
        if next_open:
            return f"🔴 暂停 {_fmt_next_open(next_open)} 开放"
        return "🔴 暂停"
    if status in ("", "场内交易"):
        return "—"
    return f"⚪ {status}"


def purchase_status_footnote(purchase_status_data: dict | None) -> str:
    """口径脚注全文（列展示时恒在；时效告警并入同一条文案，两套渲染同源）。"""
    base = PURCHASE_STATUS_FOOTNOTE
    if not purchase_column_visible(purchase_status_data):
        return base
    level = stale_level((purchase_status_data or {}).get("fetched_at"))
    fetched_date = str((purchase_status_data or {}).get("fetched_at") or "")[:10]
    if level == "stale":
        return f"⚠ 数据陈旧（{fetched_date} 抓取）：{base}"
    if level == "expired":
        return f"数据已超过 {STALE_EXPIRE_MAX_DAYS} 个交易日未更新，申购状态暂不显示（宁缺毋错）。{base}"
    return f"{base}（数据抓取于 {fetched_date}）"


#: 受限申购状态集（与单元格 🟡/🔴 展示同判据——受限判定的唯一状态源）
RESTRICTED_PURCHASE_STATUSES = ("限大额", "暂停申购")


def _filter_restricted_rows(
    purchase_status_data: dict | None,
    holding_codes: list[str] | None,
) -> list[dict[str, Any]]:
    """受限行筛选（共享单源）：持仓 ∩ 行集 ∩ 受限状态 → 预格式化行列表。

    准入（任一不满足 → ``[]``）：契约可见（开关开 + available=True）、
    时效非 ``expired``（同模块 :func:`stale_level` 判据）、持仓 codes 非空
    且与行集存在受限交集。

    字段值复用同模块格式化原语（``_fmt_limit`` / ``_fmt_next_open``）——
    与单元格文案同一数值解释，出现第二份实现即为技术债。
    """
    if not purchase_column_visible(purchase_status_data):
        return []
    level = stale_level((purchase_status_data or {}).get("fetched_at"))
    if level == "expired":
        return []
    codes = {str(c).strip() for c in holding_codes or [] if str(c).strip()}
    if not codes:
        return []
    rows = (purchase_status_data or {}).get("rows") or {}
    out: list[dict[str, Any]] = []
    for code in sorted(codes):
        row = rows.get(code)
        if not isinstance(row, dict):
            continue
        status = str(row.get("purchase_status") or "")
        if status not in RESTRICTED_PURCHASE_STATUSES:
            continue
        limit = row.get("daily_limit")
        next_open = str(row.get("next_open_date") or "")
        out.append(
            {
                "code": code,
                "status": status,
                # limit：日限额数值（供可行性天数估算的纯算术输入）；
                # limit_text/next_open_text：预格式化字段值（消费方只拼静态模板）
                "limit": float(limit) if isinstance(limit, (int, float)) else None,
                "limit_text": "限额未知" if limit is None else _fmt_limit(float(limit)),
                "next_open_text": _fmt_next_open(next_open) if next_open else "",
                "level": level,
            }
        )
    return out


def build_restricted_index(
    purchase_status_data: dict | None,
    holding_codes: list[str] | None,
) -> dict[str, dict[str, Any]]:
    """受限标的预格式化索引：code → {status, limit, limit_text, next_open_text, level}。

    准入（任一不满足 → ``{}``）：契约非 None（开关关时上游返 None）、
    available=True、时效非 ``expired``、持仓 ∩ 行集内存在受限
    （限大额/暂停申购）标的。降级态返回空索引 = 消费方逐字节回退现网行为。
    """
    filtered = _filter_restricted_rows(purchase_status_data, holding_codes)
    if not filtered:
        return {}
    return {row["code"]: row for row in filtered}


def build_purchase_constraint_block(
    purchase_status_data: dict | None,
    holdings_details: list[dict] | None,
) -> str:
    """申购限购约束块（进全部 LLM 分析章提示词的唯一渲染实现）。

    准入（任一不满足 → ``""``，消费侧提示词逐字节回退）：

    1. 契约非 None（开关 ``fund_purchase_limit`` 关闭时上游直接返 None）；
    2. 契约 ``available=True``；
    3. 时效非 ``expired``（同模块 :func:`stale_level`，与展示层同一判据）；
    4. 持仓明细非空且持仓 ∩ 行集内存在受限标的（开放申购不入块——正向信息
       不占 token；场内标的只以「总表查无此码」排除，不做代码前缀类型推测）。

    纯函数——不触网、不触盘、不打日志。字段值经 :func:`_filter_restricted_rows`
    与单元格文案同一数值解释（状态词 / 日限额千分位 / 下一开放日，单源）；
    行序 = 持仓明细顺序（确定性）；缺名回退显示代码；stale 档附「⚠ 数据陈旧」注
    （与展示层同语义）。
    """
    if not purchase_status_data or not holdings_details:
        return ""
    if not purchase_column_visible(purchase_status_data):
        return ""
    level = stale_level(purchase_status_data.get("fetched_at"))
    if level == "expired":
        return ""
    codes = [str(h.get("code") or "").strip() for h in holdings_details]
    restricted = {row["code"]: row for row in _filter_restricted_rows(purchase_status_data, codes)}
    if not restricted:
        return ""
    lines: list[str] = []
    for holding in holdings_details:
        code = str(holding.get("code") or "").strip()
        row = restricted.get(code)
        if row is None:
            continue
        name = str(holding.get("name") or "").strip() or code  # 缺名回退代码
        if row["status"] == "限大额":
            detail = (
                "限额未知（以实际下单渠道显示为准）"
                if row["limit_text"] == "限额未知"
                else f"单账户单日限购 {row['limit_text']} 元"
            )
        else:  # 暂停申购（RESTRICTED_PURCHASE_STATUSES 仅两态，未知状态已被筛选）
            detail = f"下一开放日 {row['next_open_text']}" if row["next_open_text"] else "下一开放日未知"
        lines.append(f"- {code} {name} {row['status']}：{detail}")
    if not lines:
        return ""
    fetched_date = str(purchase_status_data.get("fetched_at") or "")[:10]
    head = (
        f"【申购限购约束】（天天基金渠道口径，数据抓取于 {fetched_date}；其他渠道限额可能不同，实际以下单渠道显示为准"
    )
    if level == "stale":
        head += "；⚠ 数据陈旧"
    head += "）"
    return "\n".join(
        [
            head,
            *lines,
            "（以上为申购可执行性硬约束：给出加仓、申购、合并类建议时必须先核对本表；场内标的无申购语义不列。）",
        ]
    )
