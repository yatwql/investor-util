"""行动建议 Excel 写入模块 —「行动建议」页签。

决策闭环的核心产出页签，展示四个行动子块：
  1. 再平衡信号 — 单品占比超警戒线（复用 simple_rebalance 计算）
  2. 交易纪律   — 止盈/止损/回撤触发（analysis/trade_discipline 计算）
  3. 调仓建议   — 可行化调仓清单（analysis/rebalance_advisor 计算，份额取整/费用/现金）
  4. 收益归因   — 品种收益贡献占比（TOP5 正负分列 + 净额合计摘要）

数据源为 `action_data` 契约（`analysis/action_advisor.build_action_data` 组装、
orchestrator 注入 pipeline_data）。子块为空时写「暂无」占位——收益归因无可归因
数据（Σ|profit|=0 / 无持仓）时写「待生成」占位，报告结构保持稳定。

数据不可用（available=False）时写入占位文本（§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from src.python.core.registry import get_report_sheet_name
from src.python.report.excel_writer import (
    auto_width,
    write_data_row,
    write_header_row,
    write_title_row,
)

logger = logging.getLogger("invest")

_FONT_ACCENT = Font(size=12, bold=True, color="2E75B6")
_FONT_SUB_BLOCK = Font(bold=True, color="404040")
_FONT_WARN = Font(color="CC0000")

# 空子块占位（框架先行，后续轮次填充时被真实数据替换）
_PLACEHOLDER_EMPTY = "暂无触发"
_PLACEHOLDER_UNAVAILABLE = "无持仓数据，行动建议无法生成"


def _write_sub_block(
    ws: Worksheet,
    row: int,
    title: str,
    items: list[dict[str, Any]],
    headers: list[str],
    ncols: int,
    row_values,
    placeholder: str = _PLACEHOLDER_EMPTY,
) -> int:
    """写入一个行动子块（标题 + 表头 + 数据行，空时写占位）。

    Args:
        ws: worksheet
        row: 起始行号
        title: 子块标题
        items: 子块数据行列表
        headers: 表头
        ncols: 表格列数
        row_values: 数据行取值函数（item → list）
        placeholder: 空数据占位文本

    Returns:
        子块结束行号
    """
    row += 1
    cell = ws.cell(row=row, column=1, value=title)
    cell.font = _FONT_SUB_BLOCK
    row += 1
    if not items:
        row = write_data_row(ws, row, [placeholder] + [""] * (ncols - 1))
        return row
    row = write_header_row(ws, row, headers[:ncols])
    for item in items:
        row = write_data_row(ws, row, row_values(item))
    return row


def write_action_sheet(
    ws: Worksheet,
    action_data: dict[str, Any] | None,
    decision_review_data: dict[str, Any] | None = None,
    prosperity_framework_data: dict[str, Any] | None = None,
    market_sentiment_data: dict[str, Any] | None = None,
) -> None:
    """写入行动建议页签（行动板块 + 可选章内块）。

    Args:
        ws: openpyxl Worksheet 对象
        action_data: `action_data` 契约 dict；None 或 available=False 时写占位。
        decision_review_data: 「历史决策复盘」契约 dict（决策跨期反思闭环，
            默认关闭）；None 时行动页签保持既有输出。
        prosperity_framework_data: 「景气度框架诊断」契约 dict（实验性功能
            `prosperity_framework`，默认关闭）；None 时页签保持既有输出。
        market_sentiment_data: 「市场情绪与持仓热点」契约 dict（报告增强开关
            `market_sentiment`，默认关闭）；None 时页签保持既有输出。
    """
    _name = get_report_sheet_name("action")
    _ncols = 5
    write_title_row(ws, 1, _name, ncols=_ncols)
    row = 2

    if not action_data or not action_data.get("available"):
        row = write_data_row(ws, row, [_PLACEHOLDER_UNAVAILABLE, "", "", "", ""])
        if decision_review_data and decision_review_data.get("available"):
            _row = row + 1
            _write_review_block(ws, _row, decision_review_data, _ncols)
        if prosperity_framework_data and prosperity_framework_data.get("available"):
            _write_prosperity_block(ws, row + 1, prosperity_framework_data, _ncols)
        if market_sentiment_data is not None:
            _write_market_sentiment_block(ws, row + 1, market_sentiment_data, _ncols)
        auto_width(ws)
        logger.info("行动建议：无持仓数据，写入占位")
        return

    # 行动摘要行
    _summary = (action_data.get("summary") or "").strip()
    if _summary:
        ws.cell(row=row, column=1, value=_summary).font = _FONT_ACCENT
        row += 1

    # 子块 1：再平衡信号（单品超限）
    row = _write_sub_block(
        ws,
        row,
        "再平衡信号（单品占比超警戒线）",
        action_data.get("rebalance_signals") or [],
        ["代码", "名称", "占比", "警戒线", "建议动作"],
        _ncols,
        lambda s: [
            s.get("code", ""),
            s.get("name", ""),
            f"{s.get('weight', 0) * 100:.1f}%",
            f"{s.get('threshold', 0) * 100:.0f}%",
            s.get("action", ""),
        ],
        placeholder="组合分散度良好，无品种超警戒线",
    )

    # 子块 2：交易纪律（框架，后续轮次填充）
    row = _write_sub_block(
        ws,
        row,
        "交易纪律（止盈/止损/回撤）",
        action_data.get("discipline_signals") or [],
        ["代码", "名称", "规则", "当前值", "触发状态"],
        _ncols,
        lambda s: [
            s.get("code", ""),
            s.get("name", ""),
            s.get("rule", ""),
            s.get("value", ""),
            s.get("status_label", ""),
        ],
    )

    # 子块 3：调仓建议（可行化清单：份额取整一手/费用估算/现金缓冲）
    row = _write_sub_block(
        ws,
        row,
        "调仓建议清单",
        action_data.get("rebalance_advice") or [],
        ["代码", "名称", "操作", "份额", "金额", "预估费用", "调仓后现金"],
        7,
        lambda s: [
            s.get("code", ""),
            s.get("name", ""),
            s.get("operation", ""),
            s.get("shares", ""),
            s.get("amount", ""),
            s.get("fee", ""),
            s.get("cash_after", ""),
        ],
        placeholder="无再平衡/纪律触发信号，暂无调仓建议",
    )

    # 子块 4：收益归因（TOP5 贡献占比，正负分列 + 净额合计）
    _attr = action_data.get("attribution")
    row += 1
    ws.cell(row=row, column=1, value="收益归因（品种贡献占比）").font = _FONT_SUB_BLOCK
    row += 1
    if not _attr or not _attr.get("available"):
        row = write_data_row(ws, row, ["待生成", "", "", "", ""])
    else:
        row = write_header_row(ws, row, ["来源", "品种", "贡献占比", "盈亏金额", ""])
        for src in ("盈利来源", "亏损来源"):
            for item in _attr.get(src) or []:
                _pp = item.get("contribution_pp", 0) or 0
                _profit = item.get("profit", 0) or 0
                row = write_data_row(
                    ws,
                    row,
                    [src, item.get("name", ""), f"{_pp:+.1f}pp", f"{_profit:+,.2f}", ""],
                )
        _summary = (_attr.get("summary") or "").strip()
        if _summary:
            ws.cell(row=row, column=1, value=f"净额合计：{_summary}").font = _FONT_SUB_BLOCK
            row += 1

    # 子块 5：历史决策复盘（决策跨期反思闭环，非回测）
    if decision_review_data and decision_review_data.get("available"):
        row += 1
        row = _write_review_block(ws, row, decision_review_data, _ncols)

    # 子块 6：景气度框架诊断（实验性功能 prosperity_framework，默认关闭）
    if prosperity_framework_data and prosperity_framework_data.get("available"):
        row += 1
        row = _write_prosperity_block(ws, row, prosperity_framework_data, _ncols)
    if market_sentiment_data is not None and action_data and action_data.get("available"):
        row = _write_market_sentiment_block(ws, row, market_sentiment_data, _ncols)

    auto_width(ws)
    logger.info("行动建议页签已写入")


def _write_review_block(
    ws: Worksheet,
    row: int,
    review_data: dict[str, Any],
    ncols: int,
) -> int:
    """写入行动页签内的「历史决策复盘」子块。

    Args:
        review_data: `decision_review_data` 契约 dict（available=True 已保证）
    """
    row += 1
    ws.cell(row=row, column=1, value="历史决策复盘（非回测，仅供反思参考）").font = _FONT_SUB_BLOCK
    row += 1
    disclaimer = (review_data.get("disclaimer") or "").strip()
    if disclaimer:
        ws.cell(row=row, column=1, value=disclaimer).font = Font(italic=True, color="808080")
        row += 1

    row = write_header_row(ws, row, ["代码", "名称", "判断方向", "结果", "区间涨跌"])
    _outcome_label = {"hit": "兑现", "miss": "未兑现", "flat": "平盘", "gap": "缺数据"}
    for s in review_data.get("recent_settled") or []:
        raw = s.get("raw_return")
        ret_text = f"{raw:+.1%}" if isinstance(raw, (int, float)) else ""
        row = write_data_row(
            ws,
            row,
            [
                s.get("code", ""),
                s.get("name", ""),
                s.get("direction", ""),
                _outcome_label.get(s.get("outcome"), s.get("outcome", "")),
                ret_text,
            ],
        )
    for p in review_data.get("recent_pending") or []:
        row = write_data_row(
            ws,
            row,
            [p.get("code", ""), p.get("name", ""), p.get("direction", ""), "待结算", ""],
        )
    if review_data.get("settled_count", 0) > 0:
        if review_data.get("sample_sufficient"):
            _acc = review_data.get("direction_accuracy")
            _acc_text = f"{_acc:.0%}" if isinstance(_acc, (int, float)) else ""
            _alpha = review_data.get("alpha_mean")
            _alpha_text = f" · 超额均值 {_alpha:+.2%}" if isinstance(_alpha, (int, float)) else ""
            row = write_data_row(ws, row, [f"方向命中 {_acc_text}{_alpha_text}", "", "", "", ""])
        else:
            row = write_data_row(
                ws,
                row,
                [f"已结算 {review_data.get('settled_count', 0)} 条（样本不足，仅计数参考）", "", "", "", ""],
            )
    elif review_data.get("pending_count", 0) > 0:
        row = write_data_row(
            ws,
            row,
            [f"待结算 {review_data.get('pending_count', 0)} 条（决策满 5 个交易日后用真实行情对账）", "", "", "", ""],
        )
    return row


def _write_market_sentiment_block(ws, row: int, data: dict[str, Any], ncols: int) -> int:
    """写入「市场情绪与持仓热点」块（报告增强开关 `market_sentiment`，默认关）。

    只列**命中持仓/穿透标的代码**的当日事件：上榜龙虎榜（净买额/上榜原因）与
    进入连板梯队（板位/次日封板）；不可用时写降级原因，不阻断行动建议章其余内容。
    """
    row = write_title_row(ws, row, "市场情绪与持仓热点", ncols=ncols)
    if not data.get("available"):
        row = write_data_row(ws, row, [f"（{data.get('reason') or '暂无可用情绪数据'}）", "", "", "", ""])
        for f in data.get("failures") or []:
            row = write_data_row(ws, row, [f"⚠ {f.get('source', '')}：{f.get('reason', '')}", "", "", "", ""])
        return row

    summary = data.get("summary") or {}
    caps = "；".join(f"{k} {v} 家" for k, v in (summary.get("board_caps") or {}).items() if v) or "—"
    row = write_data_row(
        ws,
        row,
        [
            f"交易日 {data.get('trade_date') or '未知'}｜龙虎榜上榜 {summary.get('lhb_stock_count') or '—'} 只"
            f"｜连板梯队（{summary.get('ladder_date') or '未知'}）：{caps}",
            "",
            "",
            "",
            "",
        ],
    )
    if not (data.get("rows") or []):
        row = write_data_row(ws, row, [f"（{data.get('reason') or '当日无命中事件'}）", "", "", "", ""])
    row = write_header_row(ws, row, ["名称", "代码", "标的来源", "事件", "说明"])
    for item in data.get("rows") or []:
        if item.get("event_type") == "龙虎榜":
            parts = [f"净买额 {item.get('net_value_yi')} 亿"]
            if item.get("hot_money_net_value_yi") is not None:
                parts.append(f"游资 {item.get('hot_money_net_value_yi')} 亿")
            if item.get("org_net_value_yi") is not None:
                parts.append(f"机构 {item.get('org_net_value_yi')} 亿")
            if item.get("range_days"):
                parts.append(f"{item.get('range_days')} 日榜")
            if item.get("limit_reason"):
                parts.append(str(item.get("limit_reason")))
            if item.get("concepts"):
                parts.append(f"概念 {item.get('concepts')}")
        else:
            parts = [f"{item.get('board_label') or ''}", f"日期 {item.get('event_date') or ''}"]
            if item.get("seal_nextday"):
                parts.append("次日封板")
        row = write_data_row(
            ws,
            row,
            [
                item.get("name") or "",
                item.get("code") or "",
                item.get("holding_kind") or "",
                item.get("event_type") or "",
                "｜".join(p for p in parts if p),
            ],
        )
    for f in data.get("failures") or []:
        row = write_data_row(ws, row, [f"⚠ {f.get('source', '')}：{f.get('reason', '')}", "", "", "", ""])
    row += 1
    return write_data_row(
        ws,
        row,
        [
            "说明：仅列持仓/穿透标的命中当日龙虎榜或连板梯队的事件（按代码精确匹配，不做概念联想）；非投资建议",
            "",
            "",
            "",
            "",
        ],
    )


def _write_prosperity_block(ws, row: int, data: dict[str, Any], ncols: int) -> int:
    """写入「景气度框架诊断」块（实验性功能，六维评分卡）。

    含总分/评级、六维明细（依据行）、持仓视角与「需核实」清单；结尾固定免责句
    （契合度而非优劣判断，非投资建议）。
    """
    row = write_title_row(ws, row, "景气度框架诊断（实验性）", ncols=ncols)
    row = write_data_row(
        ws,
        row,
        [
            f"总分 {data.get('total_score', 0)}/{data.get('scored_weight', 0)}"
            f"（{data.get('total_score_pct', 0)}%）—— 评级：{data.get('rating_label', '')}",
            "",
            "",
            "",
            "",
        ],
    )
    row = write_header_row(ws, row, ["维度", "得分", "满分", "依据", ""])
    for dim in data.get("dimensions", []):
        evidence = "；".join(dim.get("evidence") or []) or "-"
        status = dim.get("status")
        if status == "unverified":
            evidence = "；".join(dim.get("unverified") or []) or "数据缺失，未计分"
        row = write_data_row(ws, row, [dim.get("name", ""), dim.get("score", 0), dim.get("max_score", 0), evidence, ""])
    for item in data.get("holdings_view", [])[:10]:
        notes = "；".join(item.get("notes") or []) or "-"
        roe = item.get("roe")
        roe_text = f"{roe:.2%}" if isinstance(roe, (int, float)) else "需核实"
        row = write_data_row(
            ws,
            row,
            [
                f"{item.get('name', '')}（{item.get('code', '')}）",
                f"{item.get('weight_pct', 0)}%",
                f"板块 {item.get('sector', '')}",
                f"ROE {roe_text}｜{notes}",
                "",
            ],
        )
    for text in (data.get("unverified") or []) + (data.get("notes") or []):
        row = write_data_row(ws, row, [f"* {text}", "", "", "", ""])
    return row
