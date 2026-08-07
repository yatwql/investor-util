"""报告管线辅助函数子模块 — 轻量行情 / 数据注入 / 完整性校验。

承载管线各阶段的辅助实现：
  - 轻量级行情获取（both 路径，无指数/穿透/分类）
  - 组合演进 / 快照差异数据注入（pipeline_data 键）
  - 校验函数（prepare_report_data / capture_snapshot 完整性断言）
  - both 路径持仓明细 → 行动建议消费字段子集

由 `_report_generation.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")


# ── 轻量级行情获取（无指数/穿透/分类）──


def _compute_details(holdings: list, config: dict, reporter: ProgressReporter) -> list:
    """轻量级行情获取，供 both 路径使用。

    仅获取行情明细，不获取指数/穿透/分类数据（与 _cmd_generate_both 语义对齐）。
    """
    from src.python.report.market_value import _generate_details

    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings)
    reporter.ok(f"行情数据获取完成，共 {len(details)} 条")
    return details


# ── 组合演进数据（多快照趋势聚合）──


def _inject_evolution_data(
    pipeline_data: dict | None,
    *,
    snapshot_namespace: str | None = None,
) -> dict:
    """计算组合演进数据并注入 pipeline_data（`evolution_data` 键）。

       聚合 `data/history/snapshots/` 多期快照，供 HTML「组合演进」章节与
       Excel 页签消费。计算失败或数据不足时注入 available=False 的降级 dict，
    展示层写占位文本（§1.4.5），不阻断报告生成（隔离）。

       Args:
           pipeline_data: capture_snapshot 返回的 A 通道数据（可能为 None）
           snapshot_namespace: 快照隔离域（None=共享主目录；如 "web"=web 试算域）

       Returns:
           注入 evolution_data 后的 pipeline_data（None 时新建字典）
    """
    if pipeline_data is None:
        pipeline_data = {}
    try:
        from src.python.analysis.portfolio_evolution import build_evolution_data

        pipeline_data["evolution_data"] = build_evolution_data(snapshot_namespace=snapshot_namespace)
    except Exception:
        logger.warning("[evolution] 组合演进数据构建失败（非关键）", exc_info=True)
        pipeline_data["evolution_data"] = {"available": False, "reason": "组合演进数据构建失败"}
    return pipeline_data


def _inject_snapshot_diff_data(
    pipeline_data: dict | None,
    *,
    snapshot_namespace: str | None = None,
) -> dict:
    """计算快照差异摘要并注入 pipeline_data（`snapshot_diff_data` 键）。

       对比 `data/history/snapshots/` 去重后最近两次快照，输出组合演进章顶部
       「自上次快照变化摘要」（新增/移除品种 + 集中度 HHI 变化 + 超警戒线品种）。
       有效快照 < 2 期时返回 available=False 的降级 dict，展示层写占位
    （§1.4.5），不阻断报告生成（隔离）。

       Args:
           pipeline_data: capture_snapshot 返回的 A 通道数据（可能为 None）
           snapshot_namespace: 快照隔离域（None=共享主目录；如 "web"=web 试算域）

       Returns:
           注入 snapshot_diff_data 后的 pipeline_data（None 时新建字典）
    """
    if pipeline_data is None:
        pipeline_data = {}
    try:
        from src.python.analysis.snapshot_diff import build_snapshot_diff

        pipeline_data["snapshot_diff_data"] = build_snapshot_diff(snapshot_namespace=snapshot_namespace)
    except Exception:
        logger.warning("[snapshot_diff] 快照差异摘要构建失败（非关键）", exc_info=True)
        pipeline_data["snapshot_diff_data"] = {"available": False, "reason": "快照差异摘要构建失败"}
    return pipeline_data


# ── 校验函数 ──


def _validate_prep_completeness(prep: dict) -> None:
    """校验 prepare_report_data 返回数据的完整性。"""
    assert isinstance(prep, dict), "prepare_report_data 返回类型异常"
    for _ck in (
        "total_mv",
        "total_cost",
        "total_profit",
        "total_today_profit",
        "categories",
        "a_indices",
        "holdings_details",
        "today_str",
        "output_dir",
        "news_top_count",
        "risk_metrics",
    ):
        if _ck not in prep:
            logger.warning("[checkpoint] prep 缺失必选键: %s", _ck)
        elif not isinstance(prep.get(_ck), (int, float, dict, list, str, type(None))):
            logger.warning("[checkpoint] prep.%s 类型异常: %s", _ck, type(prep.get(_ck)).__name__)


def _validate_pipeline_snapshot(pipeline_data: dict | None) -> None:
    """校验 capture_snapshot 返回数据的完整性。"""
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None:
            if not isinstance(_diff, dict):
                logger.warning("[checkpoint] pipeline_data.diff 类型异常: %s", type(_diff).__name__)


# ── both 路径持仓明细 → 行动建议消费字段子集 ──


def _both_action_holdings_details(details: list) -> list[dict]:
    """both 路径持仓明细 → 行动建议消费的字段子集（数据契约同 orchestrator 组装）。

    交易纪律依赖收益率数据（profit_rate），统一换算为百分数（小数 ×100）；
    shares/price 供调仓建议可行化层计算可执行卖出份额与金额；
    channel 为场内/场外渠道上下文（按账户关键词判定），供可行化层按渠道
    计算份额取整与费用（场外整数份 + 赎回费）。
    """
    from src.python.core.code_utils import is_offsite_fund

    return [
        {
            "name": d.name,
            "code": d.code,
            "market_value": d.market_value,
            "cost": d.cost,
            "profit": d.profit,
            "profit_rate": (d.profit_rate * 100) if d.profit_rate is not None else None,
            "shares": d.shares,
            "price": d.price,
            # getattr 兼容缺 account 的 detail 对象（测试 fixture 简化版）
            "channel": "场外" if is_offsite_fund(getattr(d, "account", "")) else "场内",
        }
        for d in details
    ]
