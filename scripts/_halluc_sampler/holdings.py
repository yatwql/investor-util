"""持仓侧派生（品种分类 / 组合核心数值 / 标准数据集加载）。"""

from __future__ import annotations


# ── 基金代码白名单（用于分类） ──────────────────────────────────
_FUND_CODES: set[str] = {"005827", "006113", "110011", "008286", "007207"}


def _compute_categories(holdings_details: list[dict]) -> dict[str, int]:
    """从持仓明细计算品种分类计数。"""
    cat_counts: dict[str, int] = {}
    for h in holdings_details:
        code = h.get("code", "")
        if code in _FUND_CODES:
            cat = "基金"
        elif code.startswith(("51", "15", "16")):
            cat = "ETF"
        elif code.startswith(("00", "30", "60", "68", "002", "003")):
            cat = "股票"
        else:
            cat = "其他"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    return cat_counts


def _compute_portfolio_values(holdings_details: list[dict]) -> dict[str, float]:
    """计算组合核心数值，委托给 fact_checker 保持一致。"""
    from src.python.llm.fact_checker._utils import _calc_portfolio_values

    vals = _calc_portfolio_values(holdings_details)
    vals["total_today_profit"] = 0.0
    return vals


def _load_datasets(dataset_filter: list[int] | None = None) -> list[dict]:
    """加载数据集，可选按序号过滤。"""
    from src.test.data.hallucination.datasets import HALLUCINATION_DATASETS

    datasets = list(HALLUCINATION_DATASETS)
    if dataset_filter:
        datasets = [ds for i, ds in enumerate(datasets, 1) if i in dataset_filter]
    return datasets
