"""持仓基本面 — Excel 写入层（一章两区块）。

职责：把「财务指标」与「持仓个股财报摘要」两张表写入同一个工作表，分两个区块：

  区块① 财务指标（A 股基本面：营收/净利/同比/毛利率/ROE/负债率/现金流/EPS/每股净资产
        + 质量档 + 年度趋势 + 当前 PE/PB），19 列
  区块② 持仓个股财报摘要（DataSinking 全文本财报章节正文摘要），9 列

两个区块各由**独立功能开关**驱动（`financial_indicator` / `financial_report_digest`）：
契约 dict 为 None 表示该开关关闭 → 该区块整体不写；契约非 None 但 `available=False`
（开关开启但数据不可用）→ 该区块写占位与失败清单（§1.4.5 数据降级治理）。
章节整体按注册表 `data_flag_any` 的 OR 口径显示（两契约任一就绪即显示）。
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from src.python.core.registry import get_report_sheet_name
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)

logger = logging.getLogger("invest")

# ── 区块① 财务指标 ──────────────────────────────────────────
_INDICATOR_COLUMNS = [
    "名称",
    "代码",
    "报告期",
    "文种",
    "营收(亿)",
    "归母净利(亿)",
    "营收同比",
    "净利同比",
    "毛利率",
    "ROE",
    "负债率",
    "经营现金流(亿)",
    "每股收益",
    "每股净资产",
    "PE",
    "PB",
    "质量档",
    "年度趋势",
    "来源",
]

# ── 区块② 持仓个股财报摘要 ──────────────────────────────────
_DIGEST_COLUMNS = ["名称", "代码", "报告期", "文种", "标题", "披露日", "摘要", "来源", "原文链接"]

_DASH = "—"

_BLOCK_TITLE_INDICATOR = "一、财务指标"
_BLOCK_TITLE_DIGEST = "二、持仓个股财报摘要"


def _yi(value: Any) -> str:
    """金额（元）→ 亿元字符串；缺失写「—」。"""
    if not isinstance(value, (int, float)):
        return _DASH
    return f"{value / 1e8:,.2f}"


def _pct(value: Any) -> str:
    """小数比例 → 百分数字符串（保留 2 位）；缺失写「—」。"""
    if not isinstance(value, (int, float)):
        return _DASH
    return f"{value * 100:.2f}%"


def _plain(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return _DASH
    return f"{value:.{digits}f}"


def _write_indicator_block(ws: Worksheet, row: int, indicator_data: dict[str, Any] | None) -> int:
    """写入区块①「财务指标」，返回下一可用行号。"""
    ncols = len(_INDICATOR_COLUMNS)
    write_title_row(ws, row, _BLOCK_TITLE_INDICATOR, ncols=ncols)
    body = row + 2  # 区块标题下一行留空（与原独立页签布局一致）

    if not indicator_data or not indicator_data.get("available"):
        reason = (indicator_data or {}).get("reason") or "暂无可用财务指标数据"
        body = write_data_row(ws, body, [reason] + [""] * (ncols - 1))
        for _f in (indicator_data or {}).get("failures", []) or []:
            body = write_data_row(
                ws,
                body,
                [f"{_f.get('name') or _f.get('code')}（{_f.get('code')}）：{_f.get('reason')}"] + [""] * (ncols - 1),
            )
        logger.info("[fundamental_snapshot] 区块①写占位：%s", reason)
        return body

    body = write_header_row(ws, body, _INDICATOR_COLUMNS)
    for r in indicator_data.get("rows", []):
        body = write_data_row(
            ws,
            body,
            [
                r.get("name") or "",
                r.get("code") or "",
                r.get("report_period") or "",
                r.get("doc_type_label") or r.get("doc_type") or "",
                _yi(r.get("revenue")),
                _yi(r.get("net_profit")),
                _pct(r.get("revenue_yoy")),
                _pct(r.get("net_profit_yoy")),
                _pct(r.get("gross_margin")),
                _pct(r.get("roe")),
                _pct(r.get("debt_ratio")),
                _yi(r.get("operating_cash_flow")),
                _plain(r.get("eps"), 4),
                _plain(r.get("bvps")),
                _plain(r.get("pe")),
                _plain(r.get("pb")),
                r.get("quality_grade") or _DASH,
                r.get("trend") or _DASH,
                r.get("source") or "",
            ],
        )

    for _f in indicator_data.get("failures", []) or []:
        body = write_data_row(
            ws,
            body,
            [f"{_f.get('name') or _f.get('code')}（{_f.get('code')}）：{_f.get('reason')}"] + [""] * (ncols - 1),
        )

    logger.info("[fundamental_snapshot] 区块①写入完成 %d 行", len(indicator_data.get("rows", [])))
    return body


def _write_digest_block(ws: Worksheet, row: int, digest_data: dict[str, Any] | None) -> int:
    """写入区块②「持仓个股财报摘要」，返回下一可用行号。"""
    ncols = len(_DIGEST_COLUMNS)
    write_title_row(ws, row, _BLOCK_TITLE_DIGEST, ncols=ncols)
    body = row + 1

    if not digest_data or not digest_data.get("available"):
        reason = (digest_data or {}).get("reason") or "暂无可用财报数据"
        body = write_data_row(ws, body, [reason] + [""] * (ncols - 1))
        for _f in (digest_data or {}).get("failures", []) or []:
            body = write_data_row(
                ws,
                body,
                [f"{_f.get('name') or _f.get('code')}（{_f.get('code')}）：{_f.get('reason')}"] + [""] * (ncols - 1),
            )
        logger.info("[fundamental_snapshot] 区块②写占位：%s", reason)
        return body

    rows = digest_data.get("rows", []) or []
    body = write_header_row(ws, body, _DIGEST_COLUMNS)
    for item in rows:
        body = write_data_row(
            ws,
            body,
            [
                item.get("name", ""),
                item.get("code", ""),
                item.get("report_period", ""),
                item.get("doc_type", ""),
                item.get("title", ""),
                item.get("announcement_date", ""),
                item.get("summary", ""),
                item.get("source", ""),
                item.get("adjunct_url", ""),
            ],
        )

    failures = digest_data.get("failures", []) or []
    if failures:
        body += 1
        body = write_title_row(ws, body, "未取到财报的标的", ncols=ncols)
        for item in failures:
            body = write_data_row(
                ws,
                body,
                [f"{item.get('name') or item.get('code')}（{item.get('code')}）：{item.get('reason')}"]
                + [""] * (ncols - 1),
            )

    body += 1
    body = write_title_row(ws, body, "说明", ncols=ncols)
    for note in (
        "数据来源：DataSinking 全文本财报（请保留披露平台归属）；仅覆盖 A 股（沪深京）",
        "摘要为报告章节正文截断，完整内容见原文链接；具体取用章节与截断长度见 config.json 的 datasink 段",
    ):
        body = write_data_row(ws, body, [note] + [""] * (ncols - 1))

    logger.info("[fundamental_snapshot] 区块②写入完成 %d 只标的（失败 %d）", len(rows), len(failures))
    return body


def write_fundamental_snapshot_sheet(
    ws: Worksheet,
    indicator_data: dict[str, Any] | None = None,
    digest_data: dict[str, Any] | None = None,
) -> None:
    """写入「持仓基本面」工作表（区块①财务指标 + 区块②财报摘要）。

    Args:
        ws: openpyxl Worksheet 对象
        indicator_data: ``financial_indicator_data`` 契约 dict；None 表示功能开关
            `financial_indicator` 关闭（区块①整体不写）。
        digest_data: ``financial_report_digest_data`` 契约 dict；None 表示功能开关
            `financial_report_digest` 关闭（区块②整体不写）。
    """
    write_title_row(ws, 1, get_report_sheet_name("fundamental_snapshot"), ncols=len(_INDICATOR_COLUMNS))

    # 两区块顺序固定：区块① 自第 3 行起（区块小节标题 + 标题下留空），区块② 紧随其后；
    # 契约 None 表示该功能开关关闭 → 该区块整体不写（不留标题/分隔）
    row = 3
    if indicator_data is not None:
        row = _write_indicator_block(ws, row, indicator_data) + 2
    if digest_data is not None:
        _write_digest_block(ws, row, digest_data)

    freeze_header(ws, row=2)
    auto_width(ws, min_width=10, max_width=48)
    logger.info("持仓基本面页签写入完成")
