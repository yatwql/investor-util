"""Chart.js 数据集构建辅助子模块。

承载 Chart.js 交互图表的数据集构建入口：Feature Flag 总开关判定 +
量化指标总开关取值传递 + 调用 `chart_data_builder.build_chart_datasets` +
顶层异常兜底。

由 `_report_generation.py`（聚合门面）re-export 对外提供。
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

       量化指标总开关（``metrics_enabled``）：关闭时 radar 数据集各轴输出
       "N/A"（含降级 3 轴路径）；开启或未传时按数据原值渲染。
    """
    if not enable_interactive:
        return None
    try:
        from src.python.config.features import is_feature_enabled
        from src.python.report.chart_data_builder import build_chart_datasets

        return build_chart_datasets(
            history_data=history_data,
            details=details,
            risk_metrics=risk_metrics,
            all_metrics=all_metrics,
            metrics_enabled=is_feature_enabled("metrics_enabled"),
        )
    except Exception:
        # 预处理器顶层兜底：任何异常 → 返回空 dict（报告仍有表格/占位）
        logger.warning("[chart] 数据集构建失败，图表整体跳过（报告仍正常）", exc_info=True)
        return {}
