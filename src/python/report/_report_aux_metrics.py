"""报告编排辅助指标子模块 — 市场温度 + 持仓相关性矩阵。

承载数据准备族中的辅助指标编排：市场温度（三因子温度计）数据契约装配、
持仓相关性矩阵（持仓关系矩阵相关性区块）数据契约装配。

由 `orchestrator.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")


# ── 市场温度 编排 ──


def compute_market_temperature_data(
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排市场温度数据（`market_temperature_data` 数据契约）。

    流程：沪深300 指数历史 K 线（Chain + session_cache，腾讯→新浪自动降级，
    复用既有 history_index 降级链）→ 三因子合成温度计（价格分位+均线偏离+波动率）。

    Args:
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据子契约 dict（含 available/status/score/tier/disclaimer）；
        report_submodules.market_temperature 关闭时返回 None（行隐藏）；
        指数 K 线不足时 available=False（占位，§1.4.5）。
    """
    from src.python.config import is_enable_market_temperature

    if not is_enable_market_temperature(config):
        return None

    from src.python.analysis.market_temperature import (
        DEFAULT_INDEX_CODE,
        DEFAULT_INDEX_NAME,
        DEFAULT_LOOKBACK_DAYS,
        TEMPERATURE_DISCLAIMER,
        compute_temperature,
        unavailable_temperature,
    )
    from src.python.fetcher.index import fetch_index_history

    try:
        reporter.info("正在计算市场温度...")
        bars = fetch_index_history(DEFAULT_INDEX_CODE, DEFAULT_LOOKBACK_DAYS) or []
        result = compute_temperature(bars)
        if not result.get("available"):
            reporter.warn("市场温度：指数 K 线不足，写入占位")
            return unavailable_temperature("insufficient")

        result["status"] = "ok"
        result["index_code"] = DEFAULT_INDEX_CODE
        result["index_name"] = DEFAULT_INDEX_NAME
        result["disclaimer"] = TEMPERATURE_DISCLAIMER
        reporter.ok("市场温度计算完成")
        return result
    except Exception:
        logger.exception("[temperature] 市场温度编排异常，章节降级")
        return unavailable_temperature("source_failed")


# ── 持仓相关性矩阵 编排 ──


def compute_correlation_data(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排持仓相关性矩阵并返回数据契约 dict（持仓关系矩阵相关性区块）。

    流程：并行拉取各品种历史 K 线（days=90）→ 转日收益 → 纯计算相关矩阵。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据契约 dict；基金深度分析关闭时返回 None（章节隐藏）。
        数据不足/故障时 available=False（章节显示降级占位，不阻塞主报告，§1.4.5）。
    """
    from src.python.config import is_enable_fund_deep_analysis

    if not is_enable_fund_deep_analysis(config):
        return None

    from concurrent.futures import ThreadPoolExecutor

    from src.python.analysis.correlation import (
        DEFAULT_WINDOW,
        FETCH_DAYS,
        MIN_HOLDINGS,
        MIN_SAMPLES,
        compute_correlation_matrix,
        unavailable_result,
    )
    from src.python.analysis.style_factor_regression import klines_to_returns
    from src.python.report._report_factor_metrics import _fetch_holding_bars

    try:
        reporter.info("正在计算持仓相关性矩阵...")
        returns_by_code: dict[str, list[dict]] = {}
        _n = len(holdings)
        with ThreadPoolExecutor(max_workers=min(6, max(1, _n)), thread_name_prefix="orch_corr") as _pool:
            _futs = {_pool.submit(_fetch_holding_bars, h.code, h.name, FETCH_DAYS): h for h in holdings}
            for _fut in _futs:
                h = _futs[_fut]
                try:
                    _bars = _fut.result()
                except Exception:
                    _bars = None
                if _bars:
                    _rets = klines_to_returns(_bars)
                    if _rets:
                        returns_by_code[h.code] = _rets

        if len(returns_by_code) < MIN_HOLDINGS:
            logger.warning(
                "[correlation] 有效持仓不足 %d（%d 只），数据不足",
                MIN_HOLDINGS,
                len(returns_by_code),
            )
            return unavailable_result(
                "insufficient",
                sample_count=0,
                insufficient_codes=sorted(returns_by_code.keys()),
            )

        names_by_code = {h.code: h.name for h in holdings}
        result = compute_correlation_matrix(
            returns_by_code,
            names_by_code,
            window=DEFAULT_WINDOW,
            min_samples=MIN_SAMPLES,
        )
        if result.get("available"):
            reporter.ok("持仓相关性矩阵计算完成")
        else:
            reporter.warn(f"持仓相关性数据不足（有效样本 {result.get('sample_count', 0)}）")
        return result
    except Exception:
        logger.exception("[correlation] 相关性矩阵计算异常，章节降级")
        return unavailable_result("source_failed")
