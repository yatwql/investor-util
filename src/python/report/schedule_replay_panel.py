"""调仓纪律回放面板（schedule_replay_panel）：报告层装配 + 双端单源视图 + Excel 页签。

分层（设计 docs/plan/rebalance-schedule-replay-design.md §7）：
  - 取数在报告层：历史净值经 ``PortfolioHistoryCalculator``（多源链 + 缓存）、
    费率经 ``fetch_fee_index``、场内判定经 ``is_unmodeled_cost_code``（同源出口）；
  - 纯回放计算在 ``analysis/schedule_replay``（零 I/O）；成本单源消费
    ``trade_cost_model`` 口径，费率缺席 → ``cost_note="未计成本"`` 两态回显；
  - 双端同文：``build_schedule_replay_view`` 产出全部预格式化行，HTML partial 与
    Excel 页签消费同一份 view（与 event_impact / holding_change 同构）。

面板同时回放两条纪律：规则 A = 月度定期（主双线），规则 B = 阈值 5pp（指标行 +
触发提示）；目标权重 = 当前持仓归一（回看口径，limitations 常驻标注）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.schedule_replay import (
    DEFAULT_WINDOW_DAYS,
    run_schedule_replay,
)
from src.python.core.registry import get_report_sheet_name

logger = logging.getLogger("invest")

#: 规则 B 默认阈值（百分点）；与门槛评测样例同参
THRESHOLD_PP_DEFAULT = 5.0
LIMITATIONS_NOTE = (
    "口径：目标权重 = 当前持仓归一（窗口内固定，回看口径）；期初批次建仓日 = 回放窗口起点"
    "（持有期下界 → 赎回费率档偏高、成本偏保守）；成本单源 trade_cost_model（申购按金额分档、"
    "赎回按 FIFO 批次持有期逐批判档），场内品种不建模；净值 LOCF 对齐、归一 100 基点（与 What-if 同源）。"
)
_METRIC_HEADER = ["策略", "区间收益", "年化", "最大回撤", "夏普", "累计成本(元)", "调仓次数", "累计换手"]
_PERIOD_HEADER = ["调仓日", "交易笔数", "换手率", "成本(元)", "成本口径"]


def _coerce_rows(holdings: list[Any]) -> list[dict[str, Any]]:
    """持仓（Holding 对象或 dict）→ 回放输入行（code/name/shares/cost）。"""
    rows: list[dict[str, Any]] = []
    for h in holdings or []:
        if isinstance(h, dict):
            code = str(h.get("code") or "").strip()
            name = str(h.get("name") or code)
            shares = float(h.get("shares") or 0.0)
            cost = float(h.get("cost") or h.get("cost_price") or 0.0)
        else:
            code = str(getattr(h, "code", "") or "").strip()
            name = str(getattr(h, "name", "") or code)
            shares = float(getattr(h, "shares", 0.0) or 0.0)
            cost = float(getattr(h, "cost_price", 0.0) or 0.0)
        if code and shares > 0:
            rows.append({"code": code, "name": name, "shares": shares, "cost": cost})
    return rows


def _fetch_nav_series(rows: list[dict[str, Any]], window_days: int) -> tuple[dict[str, dict[str, float]], list[str]]:
    """{code: {date: 单位净值}} 与取数失败清单（报告层取数，多源链 + 缓存）。"""
    from src.python.report.portfolio_history import PortfolioHistoryCalculator

    calc = PortfolioHistoryCalculator(coverage_threshold=0.8)
    navs: dict[str, dict[str, float]] = {}
    failed: list[str] = []
    for row in rows:
        try:
            bars = calc.calculate_for_holding(row["code"], row["name"], row["shares"], window_days)
        except Exception:
            logger.info("[纪律回放] %s 历史净值获取异常", row["code"], exc_info=True)
            bars = None
        if not bars:
            failed.append(f"{row['name']}({row['code']})")
            continue
        series = {
            str(b["date"])[:10]: float(b["close"])
            for b in bars
            if b.get("date") and isinstance(b.get("close"), (int, float)) and b["close"] > 0
        }
        if series:
            navs[row["code"]] = series
        else:
            failed.append(f"{row['name']}({row['code']})(空序列)")
    return navs, failed


def build_schedule_replay_panel(
    holdings: list[Any],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """装配调仓纪律回放契约（开关开启时经实验挂载点注入 pipeline_data）。

    Returns:
        恒返回 dict（含 ``available=False`` 占位态，与事件窗同构——开关开启即出章，
        数据不足写占位而非隐藏）：``available``/``reason``/``window``/``gap_pct``/
        ``cost_note``/``rules``（``monthly``/``threshold`` 两条 ``run_schedule_replay``
        结果）/``fetch_failed``/``prompt_block``（回放引用提示词块，构建期渲染一次）。
    """
    from src.python.config.features import is_feature_enabled
    from src.python.fetcher.fund_fee import fetch_fee_index
    from src.python.report.whatif_cost_panel import is_unmodeled_cost_code

    def _placeholder(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "reason": reason,
            "window": None,
            "gap_pct": None,
            "cost_note": "",
            "rules": {},
            "fetch_failed": [],
            "prompt_block": "",
        }

    if not is_feature_enabled("rebalance_schedule_replay"):
        return _placeholder("实验开关 rebalance_schedule_replay 已关闭")
    rows = _coerce_rows(holdings)
    if not rows:
        return _placeholder("无可回放持仓（持仓为空）")

    navs, failed = _fetch_nav_series(rows, window_days)
    if not navs:
        return _placeholder("历史净值获取失败（全部品种无行情），回放不可用")

    unmodeled = {r["code"] for r in rows if is_unmodeled_cost_code(r["name"], r["code"])}
    fee_index: dict[str, dict[str, Any]] | None = None
    fund_codes = [r["code"] for r in rows if r["code"] not in unmodeled]
    if fund_codes:
        try:
            fee_index = fetch_fee_index(fund_codes) or None
        except Exception:
            logger.warning("[纪律回放] 费率索引获取失败，按未计成本回显", exc_info=True)
            fee_index = None

    common = {
        "fee_index": fee_index,
        "unmodeled_codes": unmodeled,
        "window_days": window_days,
    }
    monthly = run_schedule_replay(rows, navs, None, **common)
    threshold = run_schedule_replay(
        rows,
        navs,
        {"rule_type": "threshold", "threshold_pp": THRESHOLD_PP_DEFAULT},
        **common,
    )
    if failed:
        logger.info("[纪律回放] %d 只品种取数失败（缺口判定兜底）：%s", len(failed), "、".join(failed))
    contract = {
        "available": bool(monthly.get("available")),
        "reason": str(monthly.get("reason") or ""),
        "window": monthly.get("window"),
        "gap_pct": monthly.get("gap_pct"),
        "cost_note": str(monthly.get("cost_note") or ""),
        "rules": {"monthly": monthly, "threshold": threshold},
        "fetch_failed": failed,
        "prompt_block": "",
    }
    # 引用块构建期渲染一次（与报告视图同源）——LLM 统一附录与缓存指纹消费同一实例
    contract["prompt_block"] = _build_prompt_block(build_schedule_replay_view(contract))
    return contract


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.2f}"


def _rule_metric_row(label: str, run: dict[str, Any]) -> list[str]:
    """单条规则 → 指标对照表行（预格式化，双端逐字节同文）。"""
    metrics = (run.get("metrics") or {}).get("replay") or {}
    periods = run.get("periods") or []
    cost = sum(float(p.get("cost") or 0.0) for p in periods)
    turnover = sum(float(p.get("turnover") or 0.0) for p in periods)
    return [
        label,
        _fmt_pct(metrics.get("total_return")),
        _fmt_pct(metrics.get("annualized")),
        _fmt_pct(metrics.get("max_drawdown")),
        _fmt_num(metrics.get("sharpe")),
        _fmt_num(cost),
        str(len(periods)),
        _fmt_pct(turnover),
    ]


def _build_prompt_block(view: dict[str, Any]) -> str:
    """回放引用提示词块（契约构建期渲染一次，报告展示与 LLM 提示词同源）。

    行动建议/智囊团可在结论中引用回放事实（纪律 vs 放任指标、最近调仓）——只读
    单源，不得改写报告数值。不可用 → 空串（附录零贡献，逐字节回退，指纹条件并入）。
    """
    if not view.get("available"):
        return ""
    lines = ["【调仓纪律回放·纪律 vs 放任（与报告回放章同源，只读引用）】"]
    lines.extend(str(line) for line in (view.get("summary_lines") or []) if line)
    metric_header = view.get("metric_header") or []
    metric_rows = view.get("metric_rows") or []
    if metric_header and metric_rows:
        lines.append("指标对照：")
        lines.append("  " + "｜".join(str(cell) for cell in metric_header))
        for row in metric_rows:
            lines.append("  " + "｜".join(str(cell) for cell in row))
    period_rows = view.get("period_rows") or []
    if period_rows:
        recent = period_rows[-3:]
        lines.append(f"逐期调仓（规则 A，最近 {len(recent)} 期）：")
        for row in recent:
            lines.append("  " + "｜".join(str(cell) for cell in row))
    for line in view.get("trigger_lines") or []:
        if line:
            lines.append(str(line))
    lines.append(str(view.get("limitations_note") or ""))
    return "\n".join(lines)


def build_schedule_replay_view(panel: dict[str, Any] | None) -> dict[str, Any]:
    """契约 → 双端共用展示视图（全部字段为预格式化字符串，双端逐字节同文）。

    Returns:
        ``{"available", "reason", "title_summary", "summary_lines",
        "metric_header", "metric_rows", "period_header", "period_rows",
        "trigger_lines", "chart", "notes", "cost_note", "limitations_note"}``
    """
    view: dict[str, Any] = {
        "available": False,
        "reason": "",
        "title_summary": "调仓纪律回放数据不足",
        "summary_lines": [],
        "metric_header": list(_METRIC_HEADER),
        "metric_rows": [],
        "period_header": list(_PERIOD_HEADER),
        "period_rows": [],
        "trigger_lines": [],
        "chart": None,
        "notes": [],
        "cost_note": "",
        "limitations_note": LIMITATIONS_NOTE,
    }
    if not panel or not panel.get("available"):
        view["reason"] = (panel or {}).get("reason") or "调仓纪律回放数据不足"
        return view

    rules = panel.get("rules") or {}
    monthly = rules.get("monthly") or {}
    threshold = rules.get("threshold") or {}
    window = panel.get("window") or {}
    cost_note = str(panel.get("cost_note") or "")
    view["available"] = True
    view["cost_note"] = cost_note
    monthly_count = len(monthly.get("periods") or [])
    threshold_trigger = threshold.get("trigger") or {}
    threshold_count = int(threshold_trigger.get("count") or 0)
    view["title_summary"] = (
        f"{window.get('start', '')} ~ {window.get('end', '')}"
        f"（{window.get('points', 0)} 个净值日）：月度定期 {monthly_count} 次 / "
        f"阈值 {THRESHOLD_PP_DEFAULT:g}pp 触发 {threshold_count} 次"
    )
    gap_pct = panel.get("gap_pct")
    view["summary_lines"] = [
        (
            f"回放窗口 {window.get('start', '')} ~ {window.get('end', '')}"
            f"（{window.get('points', 0)} 个净值日，行情缺口 {_fmt_pct(gap_pct)}）；"
            "规则 A = 每月首个净值日回归目标权重，"
            f"规则 B = 任一持仓偏离 ≥{THRESHOLD_PP_DEFAULT:g}pp 触发全量回归"
        ),
        (
            f"成本态：{cost_note or '已逐笔计入（单源 trade_cost_model）'}；"
            "双线图 = 规则 A 纪律回放 vs 买入持有（100 基点归一，同 What-if 约定）"
        ),
    ]

    # 指标对照：买入持有 + 两条规则
    bh = ((monthly.get("metrics") or {}).get("buyhold")) or {}
    view["metric_rows"] = [
        [
            "买入持有",
            _fmt_pct(bh.get("total_return")),
            _fmt_pct(bh.get("annualized")),
            _fmt_pct(bh.get("max_drawdown")),
            _fmt_num(bh.get("sharpe")),
            "0.00",
            "0",
            "0.00%",
        ],
        _rule_metric_row("规则 A 月度定期", monthly),
        _rule_metric_row(f"规则 B 阈值{THRESHOLD_PP_DEFAULT:g}pp", threshold),
    ]

    # 逐期表（规则 A）
    for period in monthly.get("periods") or []:
        known = bool(period.get("cost_known"))
        view["period_rows"].append(
            [
                str(period.get("date") or ""),
                str(period.get("trades") or 0),
                _fmt_pct(period.get("turnover")),
                _fmt_num(period.get("cost")) if known else "—",
                "已计（申赎费）" if known else (cost_note or "部分费率未知"),
            ]
        )

    # 触发提示（规则 B）
    monthly_fired = (monthly.get("trigger") or {}).get("fired") or []
    if monthly_fired:
        view["trigger_lines"].append(
            f"规则 A 到点 {len(monthly_fired)} 次（首次 {monthly_fired[0]}、末次 {monthly_fired[-1]}）"
        )
    threshold_fired = threshold_trigger.get("fired") or []
    if threshold_count:
        dates_shown = "、".join(threshold_fired[:5])
        more = f" 等共 {threshold_count} 次" if threshold_count > 5 else ""
        view["trigger_lines"].append(f"规则 B 触发 {threshold_count} 次（{dates_shown}{more}）")
    else:
        view["trigger_lines"].append(f"规则 B 窗口内未触发（偏离始终小于 {THRESHOLD_PP_DEFAULT:g}pp）——无调仓期行")

    # 双线图数据（规则 A，Chart.js 消费；labels 截短为 MM-DD）
    series = monthly.get("series") or {}
    if series.get("dates"):
        view["chart"] = {
            "dates": [str(d)[5:] for d in series.get("dates") or []],
            "replay": list(series.get("replay") or []),
            "buyhold": list(series.get("buyhold") or []),
        }

    # notes：去重合并两条规则 + 取数失败
    seen: set[str] = set()
    for source in (monthly, threshold):
        for note in source.get("notes") or []:
            if note not in seen:
                seen.add(note)
                view["notes"].append(note)
    if panel.get("fetch_failed"):
        view["notes"].append(f"取数失败品种（仅影响其可得性，缺口判定兜底）：{'、'.join(panel['fetch_failed'])}")
    return view


def write_schedule_replay_sheet(ws: Any, schedule_replay_data: dict[str, Any] | None) -> None:
    """写入「调仓纪律回放」页签（与 HTML partial 消费同一份 view 字符串）。"""
    from src.python.report.excel_writer import (
        write_block_title,
        _write_placeholder,
        auto_width,
        freeze_header,
        write_data_row,
        write_header_row,
        write_title_row,
    )

    view = build_schedule_replay_view(schedule_replay_data)
    name = get_report_sheet_name("schedule_replay")
    ncols = len(_METRIC_HEADER)
    write_title_row(ws, 1, name, ncols=ncols)

    if not view["available"]:
        _write_placeholder(ws, view["reason"], row=3, max_cols=ncols)
        freeze_header(ws, row=2)
        auto_width(ws)
        logger.info("调仓纪律回放：数据不足，写入占位")
        return

    row = 2
    for line in view["summary_lines"]:
        row = write_data_row(ws, row, [line] + [""] * (ncols - 1))

    row += 1
    row = write_block_title(ws, row, "纪律回放 vs 买入持有（指标对照）", ncols=ncols)
    row = write_header_row(ws, row, view["metric_header"])
    for cells in view["metric_rows"]:
        row = write_data_row(ws, row, cells)

    row += 1
    row = write_block_title(ws, row, "规则 A 逐期调仓与成本", ncols=ncols)
    row = write_header_row(ws, row, view["period_header"])
    if view["period_rows"]:
        for cells in view["period_rows"]:
            row = write_data_row(ws, row, cells)
    else:
        row = write_data_row(ws, row, ["窗口内无调仓期行"] + [""] * (len(_PERIOD_HEADER) - 1))

    row += 1
    for line in view["trigger_lines"]:
        row = write_data_row(ws, row, [line] + [""] * (ncols - 1))
    for line in view["notes"]:
        row = write_data_row(ws, row, [line] + [""] * (ncols - 1))
    row = write_data_row(ws, row, [view["limitations_note"]] + [""] * (ncols - 1))

    freeze_header(ws, row=2)
    auto_width(ws)


__all__ = [
    "LIMITATIONS_NOTE",
    "THRESHOLD_PP_DEFAULT",
    "build_schedule_replay_panel",
    "build_schedule_replay_view",
    "write_schedule_replay_sheet",
]
