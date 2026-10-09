"""调仓 What-if 模拟操作共享层 — TUI 和 CLI 共用。

抽象出 CLI/TUI 共同的调仓模拟业务链：
  build_whatif_data → 校验 available → write_whatif_report

指定**调仓生效日**时（opt-in）额外构建时序回测（build_whatif_backtest）：
联网取生效日后行情，用 as-if 市值对比基准/目标组合曲线。回测失败/数据不足
→ 降级 available:False，不阻塞主报告。

开关 ``whatif_trade_cost``（报告章节与增强组，出厂关）开启时追加 whatif_data["cost"]
（whatif_cost_panel 装配：成本本体 + 成本前/后差 + 业绩基准三线）；关闭 →
键缺席 → whatif 双端输出与开关引入前逐字节一致（零变更红线）。

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
from src.python.config.features import is_feature_enabled
from src.python.core.models import Holding
from src.python.report.portfolio_history import PortfolioHistoryCalculator
from src.python.report.whatif_cost_panel import build_whatif_cost_panel
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


def normalize_effective_date(value: str | None) -> str | None:
    """归一化调仓生效日（YYYY-MM-DD）——三渠道共用的唯一格式校验。

    None / 空白 → None（不启用时序回测）。
    非法格式（含 ``20260701`` 等紧凑式）→ 抛 ``ValueError``，调用方映射各自契约
    （Web 400 / TUI 重新询问 / CLI argparse 类型错误）。

    Raises:
        ValueError: 不是严格的 YYYY-MM-DD 日期。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    from datetime import date

    try:
        parsed = date.fromisoformat(text)
    except ValueError as e:
        raise ValueError("生效日格式应为 YYYY-MM-DD") from e
    # 3.11 起 fromisoformat 宽容接受 20260701 等紧凑式，回写归一化严格格式
    if parsed.isoformat() != text:
        raise ValueError("生效日格式应为 YYYY-MM-DD")
    return parsed.isoformat()


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


def _purchase_restricted_index(candidate_holdings: list[Holding]) -> dict[str, Any]:
    """目标持仓申购受限索引（what-if 路径单点挂载：契约经缓存链取，异常兜底 → {}）。

    取数语义（设计 §2.3）：经限购表缓存（TTL 24h）——命中零网络；未命中经
    既有链一次；取契约异常兜底空索引，不阻断模拟（降级矩阵末行）。
    观测：命中数/降级以统一 logger 打 debug（单点）。
    """
    from src.python.config import get_config
    from src.python.report.orchestrator import compute_purchase_status_data
    from src.python.report.purchase_status import build_restricted_index

    try:
        contract = compute_purchase_status_data(get_config())
        index = build_restricted_index(contract, [h.code for h in candidate_holdings])
    except Exception:  # noqa: BLE001 — 取契约异常不得阻断模拟（仅兜底 Exception，不吞 BaseException）
        logger.debug("申购受限索引获取失败，what-if 提示降级缺席", exc_info=True)
        return {}
    logger.debug("what-if 申购受限索引命中 %d 个目标持仓标的", len(index))
    return index


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
        restricted_index=_purchase_restricted_index(candidate_holdings),
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

    # ── 交易成本对比面板（开关 whatif_trade_cost，出厂关；关闭 → 无 cost 键 →
    #    whatif 双端输出与开关引入前逐字节一致）──
    if is_feature_enabled("whatif_trade_cost"):
        try:
            data = {**data, "cost": build_whatif_cost_panel(data, effective_date=effective_date)}
        except Exception:  # noqa: BLE001 — 面板装配异常降级缺席，不阻断主报告（不吞 BaseException）
            logger.warning("交易成本对比面板装配失败（面板缺席）", exc_info=True)

    paths = write_whatif_report(data, output_dir=output_dir, reporter=reporter)
    return WhatifRunResult(ok=True, excel=paths["excel"], html=paths["html"])
