"""组合演进 Excel 写入模块 — 多快照趋势追踪页签。

输出内容：
  1. 汇总：快照数 / 有效观察日数
  2. 总市值趋势表（观察日 × 总市值 / 总成本 / 总盈亏 / 持仓数）
  3. 集中度 HHI 趋势表（观察日 × HHI）
  4. TOP 持仓占比变迁表（品种 × 观察日，市值口径权重 %）
  5. 账户配置流（多账户时展示，市值占比 %）
  6. 口径说明

数据不足或聚合失败时写入占位文本（available=False，§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from src.python.core.registry import get_report_section_number, get_report_sheet_name
from src.python.report.data_status import STATUS_MESSAGES
from src.python.report.excel_writer import (
    _write_placeholder,
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.styles import FMT_MONEY

logger = logging.getLogger("invest")

_FONT_POS = Font(color="CC0000")
_FONT_NEG = Font(color="009900")


def write_evolution_sheet(ws: Worksheet, evolution_data: dict[str, Any] | None) -> None:
    """写入组合演进页签。

    Args:
        ws: openpyxl Worksheet 对象
        evolution_data: C19 契约 dict；None 或 available=False 时写入占位。
    """
    _name = get_report_sheet_name("portfolio_evolution")
    _ncols = 8
    write_title_row(ws, 1, f"{get_report_section_number('portfolio_evolution')}. {_name}", ncols=_ncols)

    if not evolution_data or not evolution_data.get("available"):
        _write_placeholder(ws, STATUS_MESSAGES["evolution_unavailable"], row=3, max_cols=_ncols)
        freeze_header(ws, row=2)
        auto_width(ws)
        logger.info("组合演进：数据不足，写入占位")
        return

    periods = evolution_data.get("periods", [])
    n_periods = len(periods)
    row = 2

    # ── 1. 汇总 ──
    row = write_data_row(
        ws,
        row,
        [
            f"已聚合 {evolution_data.get('snapshot_count', 0)} 份快照，"
            f"{n_periods} 个有效观察日（每日取最后一次快照；数据来自本地，无需联网）",
        ]
        + [""] * (_ncols - 1),
    )

    # ── 2. 总市值趋势表 ──
    row += 1
    row = write_title_row(ws, row, "总市值趋势", ncols=5)
    row = write_header_row(ws, row, ["观察日", "总市值(元)", "总成本(元)", "总盈亏(元)", "持仓数量"])
    tv = evolution_data.get("total_value", [])
    tc = evolution_data.get("total_cost", [])
    tp = evolution_data.get("total_pnl", [])
    hc = evolution_data.get("holding_counts", [])
    for i in range(n_periods):
        _vals = [
            periods[i],
            tv[i] if i < len(tv) else 0,
            tc[i] if i < len(tc) else 0,
            tp[i] if i < len(tp) else 0,
            hc[i] if i < len(hc) else 0,
        ]
        _fmts: list[str | None] = [None, FMT_MONEY, FMT_MONEY, FMT_MONEY, None]
        row = write_data_row(ws, row, _vals, formats=_fmts)
        _pnl = _vals[3]
        if _pnl:
            ws.cell(row=row - 1, column=4).font = _FONT_POS if _pnl >= 0 else _FONT_NEG

    # ── 3. HHI 趋势表（观察日横向） ──
    hhi = evolution_data.get("hhi", [])
    row += 1
    row = write_title_row(ws, row, "持仓集中度（HHI）趋势", ncols=n_periods + 1)
    row = write_header_row(ws, row, ["指标"] + list(periods))
    row = write_data_row(ws, row, ["HHI 集中度"] + ["%.4f" % h if h is not None else "-" for h in hhi])

    # ── 4. TOP 持仓占比变迁表（品种横向） ──
    top = evolution_data.get("top_holdings", [])
    if top:
        row += 1
        row = write_title_row(ws, row, f"TOP {len(top)} 持仓占比变迁（%）", ncols=n_periods + 2)
        row = write_header_row(ws, row, ["排名", "品种"] + list(periods) + ["出现期数"])
        for idx, th in enumerate(top, start=1):
            _weights = th.get("weights", [])
            _cells = [idx, f"{th.get('name', th.get('code', ''))} ({th.get('code', '')})"]
            _cells += ["%.2f" % w for w in _weights]
            _cells.append(f"{th.get('present_count', 0)} / {n_periods}")
            row = write_data_row(ws, row, _cells)

    # ── 5. 账户配置流（多账户时展示） ──
    flows = evolution_data.get("account_flows", {}) or {}
    if len(flows) > 1:
        row += 1
        row = write_title_row(ws, row, "账户配置流（市值占比 %）", ncols=n_periods + 1)
        row = write_header_row(ws, row, ["账户"] + list(periods))
        for aname, shares in flows.items():
            row = write_data_row(ws, row, [aname] + ["%.2f" % s for s in shares])

    # ── 6. 口径说明 ──
    row += 1
    row = write_title_row(ws, row, "说明", ncols=_ncols)
    notes = [
        "权重口径：优先使用持仓市值，市值为 0 的旧快照回退成本口径；单期无有效权重时该期 HHI 记 '-'",
        "快照格式限制：行业配置流、穿透 TOP10 变迁、量化指标（夏普/波动率）趋势需快照字段扩展，暂未纳入",
        "每次生成报告自动保存一份本地快照，积累不同日期快照后趋势数据自动丰富",
    ]
    for n in notes:
        row = write_data_row(ws, row, [n] + [""] * (_ncols - 1))

    freeze_header(ws, row=2)
    auto_width(ws, min_width=10, max_width=28)
    logger.info("组合演进页签写入完成: %d 个观察日, TOP %d 持仓", n_periods, len(top))
