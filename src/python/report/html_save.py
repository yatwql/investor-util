"""HTML 报告文件 I/O — 写入最新版 + 归档版。"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from src.python.report.excel_writer import _cleanup_old_archives, _ensure_reports_dir
from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")


def _save_html_report(
    html: str, output_dir: str,
    total_mv: float, total_profit: float,
    prog: ProgressReporter,
) -> str:
    """将 HTML 写入文件（最新版 + 归档版）。

    Returns:
        最新版报告的绝对路径
    """
    prog.info("正在保存报告文件...")
    _ensure_reports_dir(output_dir)

    # 最新版
    latest_path = os.path.join(output_dir, "个人投资分析报告.html")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("最新 HTML 报告已保存: %s", latest_path)
    prog.ok(f"最新版报告: {latest_path}")

    # 归档版
    archive_dir = os.path.join(output_dir, datetime.now().strftime("%Y%m%d"))
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(
        archive_dir,
        f"个人投资分析报告-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html",
    )
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("归档 HTML 报告已保存: %s", archive_path)
    prog.ok(f"归档版报告: {archive_path}")

    # 清理过期归档（非关键），避免目录无限增长
    _cleanup_old_archives(output_dir)

    prog.ok(f"HTML 报告生成完成！总市值: {total_mv:,.2f}元, 总盈亏: {total_profit:,.2f}元")
    return os.path.abspath(latest_path)
