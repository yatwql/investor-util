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
        功能开关 `market_temperature` 关闭时返回 None（行隐藏）；
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


def compute_market_sentiment_data(
    holdings,
    prep: dict | None,
    config: dict,
    reporter: ProgressReporter | None = None,
) -> dict | None:
    """编排市场情绪契约（``market_sentiment_data``，报告增强开关默认关）。

    数据来源：同花顺官方（龙虎榜 + 连板梯队），只保留**命中持仓/穿透标的代码**的事件行；
    开关关闭返回 ``None``（零行为变化），缺凭据/两源不可用返回 ``available=False`` 降级契约。

    Args:
        holdings: 原始持仓列表
        prep: prep 字典（读 ``penetrated_assets`` 作为穿透标的来源）
        config: 完整配置（只读）
        reporter: 可选进度上报
    """
    from src.python.config import is_enable_market_sentiment

    if not is_enable_market_sentiment(config):
        return None
    from src.python.report.market_sentiment import build_market_sentiment_data

    if reporter is not None:
        reporter.info("正在获取市场情绪（龙虎榜 / 连板梯队）...")
    penetrated = (prep or {}).get("penetrated_assets") or []
    try:
        return build_market_sentiment_data(holdings, penetrated, config)
    except Exception:  # 增强模块异常不得中断主报告
        logger.warning("[market_sentiment] 市场情绪装配异常，本次跳过（主报告不受影响）", exc_info=True)
        return None


def compute_prosperity_framework_data(
    holdings,
    details,
    prep: dict | None,
    config: dict,
    reporter: ProgressReporter | None = None,
    *,
    financial_indicator_data: dict | None = None,
    history_data: dict | None = None,
    pipeline_data: dict | None = None,
) -> dict | None:
    """编排景气度框架诊断契约（`prosperity_framework_data`，实验性功能）。

    数据来源全部为既有能力：穿透重仓（`prep["penetrated_assets"]`，缺失时现算）提供
    板块/概念，`financial_indicator_data` 提供个股 ROE，`check_liquidity` 提供场内变现
    天数（失败即降级为 None → 该维标记未验证），历史快照提供换手代理，
    `history_data` 提供区间收益与最大回撤。

    Args:
        holdings: 原始持仓列表
        details: 市值明细行（DetailRow）
        prep: `prepare_report_data` 的 prep 字典（读 `penetrated_assets`）
        config: 完整配置（只读）
        reporter: 可选进度上报
        financial_indicator_data: 基本面契约（可来自 pipeline_data）
        history_data: 组合历史走势数据
        pipeline_data: 已组装契约（读 `financial_indicator_data` 作为缺省来源）

    Returns:
        契约 dict；功能开关 `prosperity_framework` 关闭时返回 None（零行为变化）。
    """
    from src.python.config.features import is_feature_enabled
    from src.python.analysis.prosperity_framework import build_prosperity_framework_data

    if not is_feature_enabled("prosperity_framework"):
        return None

    if reporter is not None:
        reporter.info("正在评估景气度框架契合度（实验性）...")

    details = list(details or [])
    penetration_data = None
    if prep and prep.get("penetrated_assets"):
        penetration_data = {"top10": prep["penetrated_assets"]}
    elif details:
        try:
            from src.python.report.penetration import compute_penetration_top10

            penetration_data = compute_penetration_top10(holdings, details) or None
        except Exception:  # 穿透失败不影响诊断其余维度
            logger.debug("[prosperity_framework] 穿透数据不可用，退回直接持仓板块口径", exc_info=True)

    liquidity_signals = None
    try:
        from src.python.analysis.liquidity import check_liquidity

        liquidity_signals = (
            check_liquidity(
                [
                    {
                        "code": getattr(d, "code", ""),
                        "name": getattr(d, "name", ""),
                        "market_value": getattr(d, "market_value", 0.0),
                    }
                    for d in details
                ],
                sum(float(getattr(d, "market_value", 0.0) or 0.0) for d in details),
                (config or {}).get("redemption_limits"),
            )
            or None
        )
    except Exception:  # 流动性取数失败 → 该维标记未验证
        logger.debug("[prosperity_framework] 流动性信号不可用，该维标记未验证", exc_info=True)

    snapshots = None
    try:
        from src.python.report import history_snapshot

        snapshots = history_snapshot.load_all() or None
    except Exception:
        logger.debug("[prosperity_framework] 历史快照不可用，换手代理标记未验证", exc_info=True)

    if financial_indicator_data is None and pipeline_data:
        financial_indicator_data = pipeline_data.get("financial_indicator_data")

    try:
        data = build_prosperity_framework_data(
            details,
            penetration_data=penetration_data,
            financial_indicator_data=financial_indicator_data,
            liquidity_signals=liquidity_signals,
            snapshots=snapshots,
            history_data=history_data,
            config=config,
        )
    except Exception:
        # 实验性诊断**不得拖垮主报告**：任何异常降级为「本契约缺席」（等价于开关关闭），
        # 记录完整堆栈便于定位；契约缺席时渲染层不出现该块、其余章节零影响。
        logger.warning("[prosperity_framework] 诊断计算失败，本次跳过该模块（主报告不受影响）", exc_info=True)
        return None
    if reporter is not None and data.get("available"):
        reporter.ok(
            f"景气度框架诊断完成：{data['total_score']}/{data['scored_weight']}（{data['total_score_pct']}%，{data['rating_label']}）"
        )
    return data
