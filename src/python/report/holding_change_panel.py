"""持仓变动复盘章装配（holding_change_panel）—— Excel/HTML 双端单源。

职责（快照事件级持仓变动复盘）：
- **契约装配**：`build_holding_change_panel` 只读加载持仓快照（+ 可选决策账本事件），
  产出 `pipeline_data["holding_change_data"]` 契约（事件清单 + 指标 + 复盘窗口 +
  局限标注；开关关闭时经 `_experimental_seams.inject_holding_change_data` 缺席）。
- **展示单源**：`build_holding_change_view` 把契约渲染成**预格式化文本行 / 表格行**，
  Excel 页签与 HTML partial 共用同一份字符串 → 双端逐字节同文，不发散。
- **Excel 写出**：`write_holding_change_sheet`（openpyxl 惰性导入，HTML 路径不付导入成本）。

不变量：
- 「区间净额推断、非逐笔」标注（`LIMITATIONS_NOTE`）随事件表同现——两端渲染分支
  成对出现，缺失即红（由双端一致性测试锁定）。
- 对快照目录 / 决策账本**零写入**；对 `pipeline_data` 仅经 seam 整键注入。
- 开关关闭时本模块不被导入（seam 不调用 → 章隐藏 → 两条输出路径既有输出）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from src.python.analysis.holding_change_events import (
    MIN_REVIEW_EVENTS,
    MIN_REVIEW_PERIODS,
    build_holding_change_events,
)
from src.python.analysis.holding_change_metrics import (
    REORDER_MIN_CODES,
    compute_holding_change_metrics,
    detect_account_reorder,
)
from src.python.core.constants import HISTORY_SNAPSHOT_RETENTION_DAYS
from src.python.core.registry import get_report_sheet_name
from src.python.report.data_status import STATUS_MESSAGES

logger = logging.getLogger(__name__)

# 「区间净额推断、非逐笔」口径标注——随事件表同现（单源常量，双端共用）
LIMITATIONS_NOTE = (
    "口径说明：事件为区间净额推断（非逐笔成交）——快照只含期初期末份额与市值，"
    "不含成交日期/单价/费用/出场价；同区间多笔买卖折叠为一条净额事件，净额≈0 的对敲不可见，"
    "分红再投与份额折算会混入份额变动。全部结论限定结构级，不构成逐笔胜率或持有期结论。"
)

# 窗口截断判定余量：起点距今 ≥ 保留期 − 余量 即视为窗口曾被滚动清理
TRUNCATION_SLACK_DAYS = 3

EVENT_HEADER = ["区间起", "区间止", "品种", "代码", "方向", "份额变动", "市值变动(元)"]
INTENT_HEADER = ["区间起", "区间止", "品种", "实际变动", "意图", "账本决策(区间内)", "对照"]
# 预格式化行中右对齐的列下标（HTML 端仅样式差异，字符串双端同源）
EVENT_RIGHT_ALIGN_FROM = 5
LLM_BLOCK_TITLE = "变动动因 LLM 归因"

_DIRECTION_TEXT = {1: "看多", -1: "看空", 0: "持平"}


# ── 契约装配 ─────────────────────────────────────────────


def build_holding_change_panel(
    config: dict[str, Any] | None = None,
    *,
    snapshot_namespace: str | None = None,
    ledger_events: list[dict[str, Any]] | None = None,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    """装配「持仓变动复盘」数据契约（只读，绝不回写快照/账本）。

    Args:
        config: 合并后应用配置 dict（读 ``history.snapshot_retention_days``，
            None 时回退 ``HISTORY_SNAPSHOT_RETENTION_DAYS`` 常量）
        snapshot_namespace: 快照命名空间（测试隔离；None = core.constants 单一来源）
        ledger_events: 决策账本事件（``core/decision_ledger.load_events()`` 注入；
            None/空 = 账本无记录，对账全部落「无意图记录」）
        reference_time: 截断判定参考时间（默认 now；测试注入保证确定性）

    Returns:
        契约 dict（`pipeline_data["holding_change_data"]` 形状）：
          - available / reason / snapshot_count / period_count
          - window_start / window_end / window_span_days（自然日）
          - retention_days / truncated / truncation_note（滚动保留截断标注）
          - sample（复盘样本门槛回显：≥12 期且 ≥10 事件）
          - events / event_count / indeterminate_count / metrics
          - limitations_note（「区间净额推断、非逐笔」常驻标注）
          - llm_review（LLM 归因文本占位；迭代 4 经 LLM 阶段注入，None=缺席）
    """
    raw = build_holding_change_events(snapshot_namespace=snapshot_namespace)
    retention_days = _resolve_retention_days(config)
    now = reference_time or datetime.now()

    contract: dict[str, Any] = {
        "available": False,
        "reason": raw.get("reason") or "",
        "snapshot_count": raw.get("snapshot_count", 0),
        "period_count": raw.get("period_count", 0),
        "window_start": raw.get("window_start"),
        "window_end": raw.get("window_end"),
        "window_span_days": 0,
        "retention_days": retention_days,
        "truncated": False,
        "truncation_note": "",
        "sample": {
            "min_periods": MIN_REVIEW_PERIODS,
            "min_events": MIN_REVIEW_EVENTS,
            "periods_ok": False,
            "events_ok": False,
            "sufficient": False,
        },
        "events": raw.get("events", []),
        "event_count": raw.get("event_count", 0),
        "indeterminate_count": raw.get("indeterminate_count", 0),
        "metrics": None,
        "limitations_note": LIMITATIONS_NOTE,
        "reorder": None,
        "reorder_note": "",
        "prompt_block": "",
        "llm_review": None,
    }

    window_start = contract["window_start"]
    window_end = contract["window_end"]
    start_day = _ts_date(window_start)
    end_day = _ts_date(window_end)
    if start_day and end_day:
        contract["window_span_days"] = max(0, (end_day - start_day).days)
        # 滚动保留截断：窗口起点龄期 ≥ 保留期（留余量）→ 标注更早历史已随清理丢失
        age_days = max(0, (now.date() - start_day).days)
        if age_days >= retention_days - TRUNCATION_SLACK_DAYS:
            contract["truncated"] = True
            contract["truncation_note"] = (
                f"窗口起点距今 {age_days} 天（滚动保留 {retention_days} 天）："
                "更早快照已按保留策略清理，此之前的变动历史不可见（截断标注）"
            )

    if not raw.get("available"):
        contract["reason"] = contract["reason"] or STATUS_MESSAGES["holding_change_unavailable"]
        return contract

    contract["available"] = True
    contract["reason"] = ""
    contract["metrics"] = compute_holding_change_metrics(
        contract["events"],
        period_count=contract["period_count"],
        window_start=window_start or "",
        window_end=window_end or "",
        ledger_events=ledger_events,
    )
    sample = contract["sample"]
    sample["periods_ok"] = contract["period_count"] >= MIN_REVIEW_PERIODS
    sample["events_ok"] = contract["event_count"] >= MIN_REVIEW_EVENTS
    sample["sufficient"] = bool(sample["periods_ok"] and sample["events_ok"])

    # 跨品种同日重排识别（账户/数据结构变更签名，归因时排除出调仓解读）
    reorder = detect_account_reorder(contract["events"])
    contract["reorder"] = reorder
    if reorder:
        contract["reorder_note"] = (
            f"疑似账户结构重排：{_ymd_label(reorder['date'])} → {_ymd_label(reorder['next_date'])} 间 "
            f"{reorder['count']} 个品种「{reorder['direction']}」同名联动（≥{REORDER_MIN_CODES} 品种同日重排）"
            "——按账户/数据结构变更解读，不计入调仓归因"
        )

    # 提示词块：经展示视图同源渲染（报告展示与 LLM 提示词共用同一份字符串，
    # 单次渲染同时进提示词与缓存指纹——见 llm/generators_orchestrator.extract_holding_change_block）
    view = build_holding_change_view(contract)
    contract["prompt_block"] = _build_events_prompt_block(view)

    logger.info(
        "[holding_change_panel] 复盘契约装配完成：%s 期 / %s 事件（%s），样本建议满足=%s",
        contract["period_count"],
        contract["event_count"],
        contract["reason"] or "ok",
        sample["sufficient"],
    )
    return contract


def _resolve_retention_days(config: dict[str, Any] | None) -> int:
    """读 ``history.snapshot_retention_days``（缺省回退常量，防两端口径漂移）。"""
    try:
        value = ((config or {}).get("history") or {}).get("snapshot_retention_days")
        if value:
            return int(value)
    except (AttributeError, TypeError, ValueError):
        pass
    return int(HISTORY_SNAPSHOT_RETENTION_DAYS)


# ── 展示单源（Excel 与 HTML 共用同一份预格式化文本） ─────────


def build_holding_change_view(data: dict[str, Any] | None) -> dict[str, Any]:
    """契约 → 双端共用展示视图（全部字段为预格式化字符串，双端逐字节同文）。

    Returns:
        {"available", "reason", "title_summary", "window_lines",
         "event_header", "event_rows", "limitations_note",
         "metrics_lines", "intent_header", "intent_rows", "intent_lines",
         "llm_review_paragraphs"}
    """
    view: dict[str, Any] = {
        "available": False,
        "reason": "",
        "title_summary": "持仓变动复盘数据不足",
        "window_lines": [],
        "event_header": list(EVENT_HEADER),
        "event_rows": [],
        "limitations_note": LIMITATIONS_NOTE,
        "metrics_lines": [],
        "intent_header": list(INTENT_HEADER),
        "intent_rows": [],
        "intent_lines": [],
        "llm_review_paragraphs": None,
        "hint_line": (
            "每次生成报告会自动保存一份本地快照；积累 ≥2 个不同日期的快照后即可差分出变动事件，"
            f"复盘样本建议 ≥{MIN_REVIEW_PERIODS} 期且 ≥{MIN_REVIEW_EVENTS} 事件（不足时结论仅供参考）"
        ),
    }
    if not data or not data.get("available"):
        view["reason"] = (data or {}).get("reason") or STATUS_MESSAGES["holding_change_unavailable"]
        return view

    view["available"] = True
    period_count = int(data.get("period_count", 0))
    event_count = int(data.get("event_count", 0))
    start_label = _ts_label(data.get("window_start"))
    end_label = _ts_label(data.get("window_end"))
    sample = data.get("sample") or {}

    view["title_summary"] = f"{period_count} 期 / {event_count} 个变动事件（{start_label} → {end_label}）"

    window_lines = [
        f"复盘窗口 {start_label} → {end_label}：{period_count} 个观察期 / {event_count} 个变动事件"
        f"（{data.get('snapshot_count', 0)} 份快照按日去重，滚动保留 {data.get('retention_days', 0)} 天）",
        (
            f"复盘样本：{period_count} 期 / {event_count} 事件"
            f"（建议 ≥{sample.get('min_periods', MIN_REVIEW_PERIODS)} 期且 "
            f"≥{sample.get('min_events', MIN_REVIEW_EVENTS)} 事件"
            + ("" if sample.get("sufficient") else "，当前低于建议，结论仅供参考")
            + "）"
        ),
    ]
    if data.get("truncated") and data.get("truncation_note"):
        window_lines.append(str(data["truncation_note"]))
    if data.get("reorder_note"):
        window_lines.append(str(data["reorder_note"]))
    view["window_lines"] = window_lines

    for ev in data.get("events", []):
        view["event_rows"].append(
            [
                _ts_label(ev.get("period_from")),
                _ts_label(ev.get("period_to")),
                str(ev.get("name") or ""),
                str(ev.get("code") or ""),
                str(ev.get("action") or ""),
                _fmt_signed(ev.get("shares_diff")),
                _fmt_signed(ev.get("value_diff")),
            ]
        )

    metrics = data.get("metrics") or {}
    if metrics:
        view["metrics_lines"] = _metrics_lines(metrics)
        view["intent_rows"], view["intent_lines"] = _intent_view(metrics)

    llm_review = data.get("llm_review")
    if isinstance(llm_review, str) and llm_review.strip():
        view["llm_review_paragraphs"] = [p.strip() for p in llm_review.split("\n\n") if p.strip()]
    return view


def _metrics_lines(metrics: dict[str, Any]) -> list[str]:
    """频率 / 结构 / 贡献分解的预格式化行（口径同演进章脚注）。"""
    mode = metrics.get("trading_day_mode", "trading")
    trading_days = metrics.get("trading_days", 0)
    if mode == "trading":
        freq = (
            f"变动频率：{metrics.get('events_per_period', 0)} 事件/观察期；"
            f"窗口 {trading_days} 个交易日（交易日历口径），"
            f"日均 {metrics.get('events_per_trading_day', 0)} 事件"
        )
    else:
        freq = (
            f"变动频率：{metrics.get('events_per_period', 0)} 事件/观察期；"
            f"交易日历不可用，按自然日 {trading_days} 天计，"
            f"日均 {metrics.get('events_per_trading_day', 0)} 事件"
        )

    counts = metrics.get("action_counts") or {}
    indeterminate = int(metrics.get("event_count", 0)) - sum(int(v) for k, v in counts.items() if k != "不可判定")
    # 五类动作键恒齐全（含「不可判定」），逐项直接回显，不隐藏稀疏类
    structure = (
        f"结构计数：新增 {counts.get('新增', 0)} · 加仓 {counts.get('加仓', 0)} · "
        f"减仓 {counts.get('减仓', 0)} · 清仓 {counts.get('清仓', 0)}"
        f"（不可判定 {counts.get('不可判定', indeterminate)}）；"
        f"触及品种 {metrics.get('distinct_codes', 0)} 个"
    )

    contribution = metrics.get("contribution") or {}
    shares_part = float(contribution.get("shares_part", 0.0))
    price_part = float(contribution.get("price_part", 0.0))
    change = float(contribution.get("market_value_change", 0.0))
    breakdown = (
        f"区间市值贡献分解：份额变动贡献 {shares_part:+,.2f} 元 + 价格变动贡献 {price_part:+,.2f} 元 "
        f"≈ 区间市值变化 {change:+,.2f} 元"
        "（Σ[(S₁−S₀)×P₀ + S₁×(P₁−P₀)]，不计现金流出入，≈ 为四舍五入容差）"
    )

    lines = [freq, structure, breakdown]
    skipped = int(contribution.get("skipped_count", 0))
    if skipped:
        lines.append(f"贡献分解覆盖：{skipped} 条事件缺份额或价格快照，未参与分解（只呈现可判定部分）")
    return lines


def _intent_view(metrics: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    """意图对账 → (表格行, 汇总说明行)。口径：只读列表对照，非绩效归因。"""
    intent = metrics.get("intent") or {}
    rows = intent.get("rows") or []
    table_rows: list[list[str]] = []
    for row in rows:
        decisions = row.get("decisions") or []
        decisions_text = "；".join(
            f"{_ts_label(d.get('report_date'))} {_DIRECTION_TEXT.get(int(d.get('direction', 0)), '?')}"
            + (f"·{d['magnitude']}" if d.get("magnitude") else "")
            for d in decisions
        )
        table_rows.append(
            [
                _ts_label(row.get("period_from")),
                _ts_label(row.get("period_to")),
                f"{row.get('name', '')}({row.get('code', '')})",
                str(row.get("action") or ""),
                str(row.get("intent") or ""),
                decisions_text or "—",
                str(row.get("alignment") or ""),
            ]
        )

    with_intent = int(intent.get("with_intent", 0))
    aligned = int(intent.get("aligned", 0))
    divergent = int(intent.get("divergent", 0))
    total = len(rows)
    lines = [
        f"意图对账：{total} 条变动事件中 {with_intent} 条区间内有决策登记 — "
        f"一致 {aligned} · 分歧 {divergent}（混合/不可判定 {with_intent - aligned - divergent}）；"
        f"其余 {total - with_intent} 条无意图记录",
        "对账口径：意图与实际变动的只读并列对照（非绩效归因，不给出命中率结论）；结算事件不入账。",
    ]
    if not intent.get("ledger_available", False):
        lines.insert(
            0,
            "决策账本暂无 decision 记录（决策跨期反思闭环未启用或窗口内无登记）——全部事件按「无意图记录」呈现。",
        )
    return table_rows, lines


# ── Excel 写出（openpyxl 惰性导入：HTML 路径不付成本） ─────────


def write_holding_change_sheet(ws: Any, holding_change_data: dict[str, Any] | None) -> None:
    """写入「持仓变动复盘」页签（与 HTML partial 消费同一份 view 字符串）。"""
    from src.python.report.excel_writer import (
        _write_placeholder,
        auto_width,
        freeze_header,
        write_data_row,
        write_header_row,
        write_title_row,
    )

    view = build_holding_change_view(holding_change_data)
    _name = get_report_sheet_name("holding_change")
    _ncols = len(EVENT_HEADER)
    write_title_row(ws, 1, _name, ncols=_ncols)

    if not view["available"]:
        _write_placeholder(ws, view["reason"], row=3, max_cols=_ncols)
        freeze_header(ws, row=2)
        auto_width(ws)
        logger.info("持仓变动复盘：数据不足，写入占位")
        return

    row = 2
    # ── 1. 复盘窗口汇总 ──
    for line in view["window_lines"]:
        row = write_data_row(ws, row, [line] + [""] * (_ncols - 1))

    # ── 2. 变动事件清单 + 「区间净额推断、非逐笔」标注（同现） ──
    row += 1
    row = write_title_row(ws, row, "变动事件清单（区间净额推断）", ncols=_ncols)
    row = write_header_row(ws, row, view["event_header"])
    for cells in view["event_rows"]:
        row = write_data_row(ws, row, cells)
    row = write_data_row(ws, row, [view["limitations_note"]] + [""] * (_ncols - 1))

    # ── 3. 频率与结构演变 ──
    if view["metrics_lines"]:
        row += 1
        row = write_title_row(ws, row, "频率与结构演变", ncols=_ncols)
        for line in view["metrics_lines"]:
            row = write_data_row(ws, row, [line] + [""] * (_ncols - 1))

    # ── 4. 意图对账（决策账本只读对照） ──
    if view["intent_rows"] or view["intent_lines"]:
        row += 1
        row = write_title_row(ws, row, "意图对账（决策账本只读对照）", ncols=_ncols)
        if view["intent_rows"]:
            row = write_header_row(ws, row, view["intent_header"])
            for cells in view["intent_rows"]:
                row = write_data_row(ws, row, cells)
        for line in view["intent_lines"]:
            row = write_data_row(ws, row, [line] + [""] * (_ncols - 1))

    # ── 5. LLM 归因块（迭代 4 注入 llm_review 后出现；缺席 = 分支隐藏） ──
    if view["llm_review_paragraphs"]:
        row += 1
        row = write_title_row(ws, row, LLM_BLOCK_TITLE, ncols=_ncols)
        for paragraph in view["llm_review_paragraphs"]:
            row = write_data_row(ws, row, [paragraph] + [""] * (_ncols - 1))

    freeze_header(ws, row=2)
    auto_width(ws)


# ── 格式化辅助（双端共用） ─────────────────────────────


def _build_events_prompt_block(view: dict[str, Any]) -> str:
    """事件清单提示词块（契约构建期渲染一次，报告与 LLM 双端同源）。

    全部行取自展示视图（同一次渲染）——进 LLM 提示词的文本与报告展示文本
    逐字节一致，指纹直接对本块取哈希即可满足「进提示词必进指纹」。

    Returns:
        块文本；契约不可用时为空串（附录零贡献，逐字节回退）。
    """
    if not view.get("available"):
        return ""
    lines = ["【持仓变动复盘·变动事件清单（区间净额推断，非逐笔）】"]
    lines.extend(view.get("window_lines") or [])
    lines.extend(view.get("metrics_lines") or [])
    intent_lines = view.get("intent_lines") or []
    if intent_lines:
        lines.append(intent_lines[0])
    rows = view.get("event_rows") or []
    detail = list(reversed(rows[-20:]))
    lines.append(f"最近变动事件（{len(detail)}/{len(rows)} 条，时间倒序）：")
    for row in detail:
        lines.append(f"  {row[0]}→{row[1]} {row[2]}({row[3]}) {row[4]} 份额 {row[5]} / 市值 {row[6]} 元")
    lines.append(LIMITATIONS_NOTE)
    return "\n".join(lines)


def _fmt_signed(value: Any) -> str:
    """带符号千分位两位小数；None → 「—」（缺失事实不虚构）。"""
    if value is None:
        return "—"
    try:
        return f"{float(value):+,.2f}"
    except (TypeError, ValueError):
        return "—"


def _ts_label(ts: Any) -> str:
    """任意时间戳形态 → MM-DD（YYYYMMDDTHHMMSS / YYYY-MM-DD / YYYYMMDD）。"""
    s = str(ts or "").strip()
    if len(s) >= 8 and s[4] != "-" and s[:8].isdigit():
        return f"{s[4:6]}-{s[6:8]}"
    if len(s) >= 10 and s[4] == "-":
        return s[5:10]
    return "—"


def _ts_date(ts: Any) -> date | None:
    """任意时间戳形态 → date；无法解析返回 None。"""
    s = str(ts or "").strip()
    try:
        if len(s) >= 8 and s[4] != "-" and s[:8].isdigit():
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        if len(s) >= 10 and s[4] == "-":
            return date.fromisoformat(s[:10])
    except ValueError:
        return None
    return None


def _ymd_label(day: str) -> str:
    """YYYYMMDD → MM-DD（无法解析原样返回）。"""
    s = str(day or "")
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[4:6]}-{s[6:8]}"
    return s
