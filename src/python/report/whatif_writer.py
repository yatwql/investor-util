"""调仓 What-if 模拟报告输出。

编排双产物输出：
  - Excel 调仓模拟工作簿（调仓摘要 / 分类配置对比 / 持仓变动明细）
  - HTML 双栏对比页（含资产配置对比环形图，复用 Chart.js 本地 bundle）

报告以独立产物命名 `调仓模拟_{时间戳}` 输出到 output_dir（与主报告分离），
并复制 Chart.js 前端资产到同目录（离线自包含，R21 约束）。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.python.report.excel_writer import _ensure_reports_dir
from src.python.report.html_writer import _copy_js_assets
from src.python.report.whatif_sheet import (
    write_whatif_category_sheet,
    write_whatif_changes_sheet,
    write_whatif_summary_sheet,
)

logger = logging.getLogger("invest")


def _timestamp() -> str:
    """紧凑时间戳（文件命名用）。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_whatif_excel(whatif_data: dict[str, Any], output_dir: str = "reports") -> str:
    """输出调仓模拟 Excel 工作簿（最新版 + 存档版），返回最新文件路径。

    Args:
        whatif_data: C19 契约 dict
        output_dir: 输出目录

    Returns:
        最新版 Excel 绝对路径
    """
    from openpyxl import Workbook

    _ensure_reports_dir(output_dir)
    wb = Workbook()
    ws_sum = wb.active
    ws_sum.title = "调仓摘要"
    write_whatif_summary_sheet(ws_sum, whatif_data)
    ws_cat = wb.create_sheet("分类配置对比")
    write_whatif_category_sheet(ws_cat, whatif_data)
    ws_chg = wb.create_sheet("持仓变动明细")
    write_whatif_changes_sheet(ws_chg, whatif_data)

    ts = _timestamp()
    latest = os.path.join(output_dir, f"调仓模拟_{ts}.xlsx")
    archive_dir = os.path.join(output_dir, datetime.now().strftime("%Y%m%d"))
    os.makedirs(archive_dir, exist_ok=True)
    archive = os.path.join(archive_dir, f"调仓模拟-{ts}.xlsx")
    try:
        wb.save(latest)
    except PermissionError:
        logger.error("文件被占用: %s", latest)
        raise
    try:
        wb.save(archive)
    except (PermissionError, OSError) as e:
        logger.warning("存档 Excel 写入失败（非关键）: %s", e)
    logger.info("调仓模拟 Excel 已保存: %s", latest)
    return os.path.abspath(latest)


def render_whatif_html(whatif_data: dict[str, Any], now_str: str) -> str:
    """渲染 whatif_template.html，返回完整 HTML 字符串。

    Args:
        whatif_data: C19 契约 dict
        now_str: 展示用时间字符串

    Returns:
        HTML 字符串
    """
    from src.python.report.html_jinja_env import _ENV

    return _ENV.get_template("whatif_template.html").render(whatif_data=whatif_data, now=now_str)


def write_whatif_html(whatif_data: dict[str, Any], output_dir: str = "reports") -> str:
    """输出调仓模拟 HTML 页面（含 Chart.js 资产复制），返回最新文件路径。

    Args:
        whatif_data: C19 契约 dict
        output_dir: 输出目录

    Returns:
        最新版 HTML 绝对路径
    """
    _ensure_reports_dir(output_dir)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = render_whatif_html(whatif_data, now_str)
    _copy_js_assets(output_dir)

    ts = _timestamp()
    latest = os.path.join(output_dir, f"调仓模拟_{ts}.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("调仓模拟 HTML 已保存: %s", latest)
    return os.path.abspath(latest)


def write_whatif_report(
    whatif_data: dict[str, Any],
    output_dir: str = "reports",
    reporter=None,
) -> dict[str, str]:
    """同时输出 Excel + HTML 调仓模拟报告。

    Args:
        whatif_data: C19 契约 dict
        output_dir: 输出目录
        reporter: 进度输出（CliProgressReporter），None 时静默

    Returns:
        {"excel": 最新 Excel 绝对路径, "html": 最新 HTML 绝对路径}
    """
    if reporter is not None:
        reporter.info("正在输出调仓 What-if 模拟报告...")
    excel_path = write_whatif_excel(whatif_data, output_dir)
    html_path = write_whatif_html(whatif_data, output_dir)
    if reporter is not None:
        reporter.ok(f"调仓模拟报告生成完成: Excel {excel_path} / HTML {html_path}")
    return {"excel": excel_path, "html": html_path}
