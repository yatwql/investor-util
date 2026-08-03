"""调仓 What-if 模拟操作共享层 — TUI 和 CLI 共用。

抽象出 CLI/TUI 共同的调仓模拟业务链：
  build_whatif_data → 校验 available → write_whatif_report

CLI（_handle_whatif）与 TUI（_cmd_whatif）仅保留入口渠道差异化逻辑：
文件来源解析、错误呈现、退出码/路径输出（设计边界见 technical.md §4.13）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.python.analysis.whatif import build_whatif_data
from src.python.core.models import Holding
from src.python.report.whatif_writer import write_whatif_report


@dataclass
class WhatifRunResult:
    """调仓模拟运行结果（CLI/TUI 共用）。

    Attributes:
        ok: 是否成功生成报告
        excel: 成功时最新 Excel 绝对路径
        html: 成功时最新 HTML 绝对路径
        reason: 失败原因（ok=False 时，如"调仓对比数据不可用"）
    """

    ok: bool
    excel: str = ""
    html: str = ""
    reason: str = ""


def run_whatif_simulation(
    base_holdings: list[Holding],
    candidate_holdings: list[Holding],
    base_file: str,
    candidate_file: str,
    output_dir: str = "reports",
    reporter=None,
) -> WhatifRunResult:
    """调仓模拟业务核心：build_whatif_data → 校验 available → write_whatif_report。

    CLI/TUI 共用；持仓由调用方加载（文件来源不同：CLI 参数 / TUI 交互选择）。

    Args:
        base_holdings: 基准持仓（调仓前）
        candidate_holdings: 目标持仓（调仓后/假设）
        base_file: 基准文件路径（仅用于展示文件名）
        candidate_file: 目标文件路径（仅用于展示文件名）
        output_dir: 输出目录
        reporter: 进度输出（CliProgressReporter/TuiProgressReporter），None 时静默

    Returns:
        WhatifRunResult — 成功时 ok=True 且携带 excel/html 路径；
        数据不可用（两侧均为空）时 ok=False 且携带原因。
    """
    data = build_whatif_data(
        base_holdings,
        candidate_holdings,
        base_file=os.path.basename(base_file),
        candidate_file=os.path.basename(candidate_file),
    )
    if not data.get("available"):
        return WhatifRunResult(
            ok=False,
            reason=data.get("reason", "调仓对比数据不可用"),
        )
    paths = write_whatif_report(data, output_dir=output_dir, reporter=reporter)
    return WhatifRunResult(ok=True, excel=paths["excel"], html=paths["html"])
