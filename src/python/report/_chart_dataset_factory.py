"""Chart.js 数据集构建辅助子模块。

自 `_report_generation.py` 拆出（超限文件拆分重构），承载 Chart.js 交互图表的
数据集构建入口：Feature Flag 总开关判定 + 雷达图指标子开关收集 +
调用 `chart_data_builder.build_chart_datasets` + 顶层异常兜底。

被 `_report_generation.py`（门面）re-export，保持
`from _report_generation import ...` 引用不变。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("invest")


# ── Chart.js 数据集构建辅助 ───────────────────────────────


def _build_chart_datasets_for_report(
    *,
    history_data: dict | None,
    details: list | None = None,
    risk_metrics: dict | None = None,
    all_metrics: dict | None = None,
    enable_interactive: bool = True,
) -> dict | None:
    """构建 Chart.js 数据集（Flag 关闭或数据缺失时返回 None/空 dict）。

       - Flag 关闭 → None（模板不渲染 Chart.js，回退旧 Canvas）
    - Flag 开启 → build_chart_datasets（内部对单图失败独立 try/except，）

       metrics_* 功能开关（Flag）：收集雷达子开关值传给预处理器，
       关闭的指标在 radar 数据集输出 "N/A"。注：metrics_risk_contribution
       是指标级熔断开关（circuit_breaker_wrapper 消费），非雷达轴，不在此收集。
    """
    if not enable_interactive:
        return None
    try:
        from src.python.config.features import is_feature_enabled
        from src.python.report.chart_data_builder import build_chart_datasets

        _metric_flag_names = (
            "metrics_sharpe",
            "metrics_calmar",
            "metrics_hhi",
            "metrics_winrate",
            "metrics_turnover",
            "metrics_beta",
        )
        metric_flags = {n: is_feature_enabled(n) for n in _metric_flag_names}

        return build_chart_datasets(
            history_data=history_data,
            details=details,
            risk_metrics=risk_metrics,
            all_metrics=all_metrics,
            metric_flags=metric_flags,
        )
    except Exception:
        # 预处理器顶层兜底：任何异常 → 返回空 dict（报告仍有表格/占位）
        logger.warning("[chart] 数据集构建失败，图表整体跳过（报告仍正常）", exc_info=True)
        return {}
