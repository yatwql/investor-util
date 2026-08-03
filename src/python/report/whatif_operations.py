"""调仓 What-if 模拟操作共享层 — TUI 和 CLI 共用。

抽象出 CLI/TUI 共同的调仓模拟业务链：
  build_whatif_data → 校验 available → write_whatif_report

指定**调仓生效日**时（opt-in）额外构建时序回测（build_whatif_backtest）：
联网取生效日后行情，用 as-if 市值对比基准/目标组合曲线。回测失败/数据不足
→ 降级 available:False，不阻塞主报告。

CLI（_handle_whatif）与 TUI（_cmd_whatif）仅保留入口渠道差异化逻辑：
文件来源解析、错误呈现、退出码/路径输出（设计边界见 technical.md §4.13）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from src.python.analysis.whatif import _merge_holdings, build_whatif_data
from src.python.analysis.whatif_backtest import compute_backtest_days, compute_backtest_metrics
from src.python.core.models import Holding
from src.python.report.portfolio_history import PortfolioHistoryCalculator
from src.python.report.whatif_writer import write_whatif_report

logger = logging.getLogger("invest")


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


def build_whatif_backtest(
    base: list[Holding],
    candidate: list[Holding],
    effective_date: str | None = None,
    session_cache: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """按生效日构建时序回测数据（opt-in 联网取历史）。

    未指定生效日 → 返回 None（主 whatif 维持纯截面比较，不加 backtest 键）。
    指定生效日 → 折算请求天数，取两侧组合 as-if 时序并计算回测指标；
    生效日无效 / 任一测无品种 / 数据不足 → 返回 available:False 契约，不抛出。

    Args:
        base: 基准持仓（调仓前）
        candidate: 目标持仓（调仓后/假设）
        effective_date: 调仓生效日（YYYY-MM-DD）；None/空 → 不联网、返回 None
        session_cache: 会话缓存（复用主流程已拉取的行情）

    Returns:
        whatif_data["backtest"] 契约 dict，或 None（未启用）。
    """
    if not effective_date:
        return None

    days = compute_backtest_days(effective_date)
    if days is None:
        return {
            "available": False,
            "status": "unavailable",
            "reason": f"生效日格式无效或不是过去日期：{effective_date}",
            "effective_date": effective_date,
        }

    base_idx = _merge_holdings(base)
    cand_idx = _merge_holdings(candidate)
    if not base_idx or not cand_idx:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "生效日回测需要两侧持仓均有品种",
            "effective_date": effective_date,
        }

    calc = PortfolioHistoryCalculator(session_cache=session_cache, benchmark_indices={})
    base_series = calc.get_combined_timeseries(
        [(code, e["name"], e["shares"]) for code, e in base_idx.items()],
        days=days,
    )
    cand_series = calc.get_combined_timeseries(
        [(code, e["name"], e["shares"]) for code, e in cand_idx.items()],
        days=days,
    )
    return compute_backtest_metrics(
        base_series.get("bars", []),
        cand_series.get("bars", []),
        effective_date,
        base_status=base_series.get("status", "unavailable"),
        cand_status=cand_series.get("status", "unavailable"),
    )


def run_whatif_simulation(
    base_holdings: list[Holding],
    candidate_holdings: list[Holding],
    base_file: str,
    candidate_file: str,
    output_dir: str = "reports",
    reporter=None,
    effective_date: str | None = None,
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
        effective_date: 调仓生效日（YYYY-MM-DD）；None/空 → 不启用时序回测。
            指定时 opt-in 联网取历史，回测失败/数据不足降级为 available:False，
            不阻塞主报告生成。

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

    if effective_date:
        try:
            backtest = build_whatif_backtest(
                base_holdings,
                candidate_holdings,
                effective_date=effective_date,
                session_cache=None,
            )
        except Exception as exc:  # noqa: BLE001 — 回测失败降级，不阻塞主报告
            logger.exception("时序回测计算异常（生效日 %s）", effective_date)
            backtest = {
                "available": False,
                "status": "unavailable",
                "reason": f"时序回测计算失败：{exc}",
                "effective_date": effective_date,
            }
        if backtest is not None:
            data = {**data, "backtest": backtest}

    paths = write_whatif_report(data, output_dir=output_dir, reporter=reporter)
    return WhatifRunResult(ok=True, excel=paths["excel"], html=paths["html"])
