"""TUI 调仓 What-if 模拟命令处理器。

对比基准（调仓前）与目标（调仓后/假设）两份持仓，生成独立调仓 diff 报告
（Excel + HTML，命名 `调仓模拟_{时间戳}`）。全程本地计算、零网络请求，
不并入主报告管线（独立产物，设计边界见 technical.md §4.13）。
"""

from __future__ import annotations

import os
from datetime import datetime

from src.python.core.logger import setup_logger
from src.python.core.reader import get_xlsx_info, list_xlsx_files, read_holdings
from src.python.report.progress import TuiProgressReporter
from src.python.tui.tui_handlers import print_error_with_hint, select_holdings_file
from src.python.tui.tui_menu import get_config_cache, press_any_key

logger = setup_logger()


def _select_candidate_file(base_file: str) -> str | None:
    """选择目标持仓文件（调仓后/假设），返回绝对路径；未找到时返回 None。

    列出持仓目录下除基准文件外的 xlsx 文件供用户选择，避免自对比。
    """
    config = get_config_cache() or {}
    dir_path = config.get("holdings_dir", "")
    base_abs = os.path.abspath(base_file)
    files = [f for f in list_xlsx_files(dir_path) if os.path.abspath(f) != base_abs]
    if not files:
        print("  [ERR] 持仓目录下未找到基准之外的 xlsx 文件")
        print("     请先放置一份目标持仓文件（调仓后/假设）到持仓目录")
        return None
    if len(files) == 1:
        print(f"  使用唯一找到的目标文件: {os.path.basename(files[0])}")
        return files[0]
    print("  找到多个目标持仓文件，请选择:")
    print(f"  {'':8s}{'文件名':40s}{'大小':>10s}{'修改日期':>22s}{'账户数':>8s}")
    print(f"  {'':-^8s}{'':-^40s}{'':->10s}{'':->22s}{'':->8s}")
    for i, f in enumerate(files, 1):
        basename = os.path.basename(f)
        name_disp = basename if len(basename) <= 38 else basename[:35] + "..."
        size = os.path.getsize(f)
        size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
        mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
        info = get_xlsx_info(f)
        acct_str = f"{info.get('accounts', '?')}" if "error" not in info else "err"
        print(f"  [{i}]  {name_disp:38s} {size_str:>10s} {mtime:>22s} {acct_str:>8s}")
    try:
        choice = input("  请输入编号: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            return files[idx]
        print("  [ERR] 无效编号")
    except (ValueError, EOFError, KeyboardInterrupt):
        print()
        print("  [ERR] 无效输入")
    return None


def _cmd_whatif() -> None:
    """调仓 What-if 模拟：对比基准与目标持仓，生成独立 diff 报告。"""
    from src.python.analysis.whatif import build_whatif_data
    from src.python.report.whatif_writer import write_whatif_report

    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    output_dir = config.get("output_dir", "reports")

    print("  [..] 调仓 What-if 模拟：先选择基准持仓（调仓前）")
    base_file = select_holdings_file()
    if not base_file:
        return

    print("  [..] 选择目标持仓文件（调仓后/假设）")
    cand_file = _select_candidate_file(base_file)
    if not cand_file:
        return

    try:
        print("  [..] 正在读取两份持仓数据...")
        base = read_holdings(base_file)
        cand = read_holdings(cand_file)
        if not base:
            print(f"  [ERR] 基准持仓读取失败或为空: {base_file}")
            press_any_key()
            return
        if not cand:
            print(f"  [ERR] 目标持仓读取失败或为空: {cand_file}")
            press_any_key()
            return
        print(f"  [OK] 基准 {len(base)} 条 / 目标 {len(cand)} 条持仓")
        data = build_whatif_data(
            base,
            cand,
            base_file=os.path.basename(base_file),
            candidate_file=os.path.basename(cand_file),
        )
        if not data.get("available"):
            print(f"  [ERR] 调仓对比数据不可用: {data.get('reason', '未知原因')}")
            press_any_key()
            return
        paths = write_whatif_report(data, output_dir=output_dir, reporter=reporter)
        print("  [OK] 调仓模拟报告已生成（独立产物，不并入主报告）")
        print(f"       Excel: {paths['excel']}")
        print(f"       HTML:  {paths['html']}")
    except Exception as e:
        logger.exception("调仓 What-if 模拟失败")
        print_error_with_hint(e, "调仓 What-if 模拟失败")
    press_any_key()
