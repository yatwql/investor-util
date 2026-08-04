"""持仓重合度矩阵计算引擎 —「持仓关系矩阵」章重合度区块。

对任意两只基金，计算其底层持仓的 Jaccard 相似系数、
重叠比例、共同标的数。结果以对称矩阵 + 排序配对列表输出。

设计要点：
  - fund_holdings 参数复用 fetch_fund_holdings 的缓存，无额外 HTTP
  - fund_mv_map 可选，不提供时仅输出 Jaccard + 共同标的数
  - 仅 >= 2 只基金时返回矩阵，否则返回空结构
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard 相似系数：|A∩B| / |A∪B|"""
    if not set_a or not set_b:
        return 0.0
    denominator = len(set_a | set_b)
    if denominator == 0:
        return 0.0
    return round(len(set_a & set_b) / denominator, 4)


def _overlap_ratio(set_a: set, set_b: set) -> float:
    """重叠比例：|A∩B| / min(|A|, |B|)

    反映"较小池中有多少被共享"，比 Jaccard 对大池差异更敏感。
    """
    if not set_a or not set_b:
        return 0.0
    denominator = min(len(set_a), len(set_b))
    if denominator == 0:
        return 0.0
    return round(len(set_a & set_b) / denominator, 4)


def compute_overlap_matrix(
    fund_holdings: dict[str, list[dict[str, Any]]],
    fund_mv_map: dict[str, float] | None = None,
) -> dict[str, Any]:
    """计算持有基金两两之间的持仓重合度矩阵。

    Args:
        fund_holdings: {fund_code: [{name, code, ratio}, ...]}
            取自 fetch_fund_holdings（已缓存），
            其中 fund_code 为 6 位基金代码，
            [{name, code, ratio}] 为该基金的前 N 大持仓列表。
        fund_mv_map: {fund_code: fund_mv} 可选，
            用于计算 overlap_mv_pct。
            fund_mv 来自 DetailRow.market_value（份额×最新价）。
            不提供时仅输出 Jaccard + 共同标的数。

    Returns:
        {
            "funds": [fund_code, ...],          # 基金代码列表（矩阵行列）
            "fund_names": {code: name, ...},    # 基金名称映射
            "matrix": [[overlap_pct, ...], ...], # n×n 对称矩阵
            "pairs": [                           # 所有配对（按 overlap_pct 降序）
                {"fund_a": code, "fund_b": code,
                 "common_count": int,            # 共同标的数
                 "jaccard": float,               # Jaccard 系数
                 "overlap_mv_pct": float | None, # 共同标的穿透市值占比
                 "common_stocks": [{"name", "code"}, ...]},  # 共同标的列表
                ...
            ],
            "has_mv_data": bool,                # 是否包含市值占比数据
        }
        当 fund_holdings 包含少于 2 只基金时，返回空结构：
        {"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False}
    """
    # 过滤：至少需要 2 只基金
    funds = sorted(fund_holdings.keys())
    if len(funds) < 2:
        logger.info("重合度矩阵：基金数 < 2（%d），跳过矩阵计算", len(funds))
        return {"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False}

    # 提取每只基金的持仓代码集 + 名称映射
    fund_stock_sets: dict[str, set[str]] = {}
    fund_stock_details: dict[str, list[dict[str, Any]]] = {}
    fund_names: dict[str, str] = {}

    for code in funds:
        holdings = fund_holdings.get(code, [])
        stock_set: set[str] = set()
        details: list[dict[str, Any]] = []
        for item in holdings:
            stock_code = (item.get("code") or "").strip()
            stock_name = (item.get("name") or "").strip()
            ratio = item.get("ratio", 0)
            if not stock_code and not stock_name:
                continue
            key = stock_code or stock_name  # 优先用代码做唯一标识
            stock_set.add(key)
            details.append({"name": stock_name, "code": stock_code, "ratio": ratio})
        fund_stock_sets[code] = stock_set
        fund_stock_details[code] = details
        # 名称：取第一条有名称的持仓记录的 fund 名字
        # 实际上 fund_holdings 外侧结构可能已经有 name 字段
        # 这里从第一项持仓的 fund 上下文中获取（由调用方保证 fund_holdings 有 fund_holdings_meta）
        fund_names[code] = code  # 默认，调用方可覆盖

    n = len(funds)
    matrix = [[0.0] * n for _ in range(n)]
    overlap_map: dict[tuple[str, str], float] = {}  # 用于排序

    # 计算所有配对
    pairs: list[dict[str, Any]] = []
    has_mv_data = bool(fund_mv_map and len(fund_mv_map) > 0)

    for i in range(n):
        matrix[i][i] = 1.0  # 对角线 = 100%
        code_i = funds[i]
        set_i = fund_stock_sets.get(code_i, set())

        for j in range(i + 1, n):
            code_j = funds[j]
            set_j = fund_stock_sets.get(code_j, set())

            common_stock_keys = set_i & set_j
            common_count = len(common_stock_keys)

            if common_count == 0:
                matrix[i][j] = 0.0
                matrix[j][i] = 0.0
                pairs.append(
                    {
                        "fund_a": code_i,
                        "fund_b": code_j,
                        "common_count": 0,
                        "jaccard": 0.0,
                        "overlap_mv_pct": None,
                        "common_stocks": [],
                    }
                )
                continue

            jaccard = _jaccard_similarity(set_i, set_j)
            overlap = _overlap_ratio(set_i, set_j)
            overlap_pct = max(jaccard, overlap)

            matrix[i][j] = overlap_pct
            matrix[j][i] = overlap_pct
            overlap_map[(code_i, code_j)] = overlap_pct

            # 共同标的详情
            details_i = {s["code"] or s["name"]: s for s in fund_stock_details.get(code_i, [])}
            details_j = {s["code"] or s["name"]: s for s in fund_stock_details.get(code_j, [])}
            common_stocks: list[dict[str, str]] = []
            for sk in sorted(common_stock_keys):
                di = details_i.get(sk, {})
                dj = details_j.get(sk, {})
                common_stocks.append(
                    {
                        "name": (di.get("name") or dj.get("name") or sk),
                        "code": (di.get("code") or dj.get("code") or ""),
                    }
                )

            # overlap_mv_pct：共同标的穿透市值占比
            overlap_mv_pct = None
            if has_mv_data and fund_mv_map:
                mv_i = fund_mv_map.get(code_i, 0.0)
                mv_j = fund_mv_map.get(code_j, 0.0)
                total_mv = mv_i + mv_j
                if total_mv > 0:
                    common_mv = 0.0
                    for sk in common_stock_keys:
                        di_ratio = details_i.get(sk, {}).get("ratio", 0) or 0
                        dj_ratio = details_j.get(sk, {}).get("ratio", 0) or 0
                        common_mv += mv_i * (di_ratio / 100.0) + mv_j * (dj_ratio / 100.0)
                    overlap_mv_pct = round(common_mv / total_mv * 100, 2)

            pairs.append(
                {
                    "fund_a": code_i,
                    "fund_b": code_j,
                    "common_count": common_count,
                    "jaccard": jaccard,
                    "overlap_mv_pct": overlap_mv_pct,
                    "common_stocks": common_stocks,
                }
            )

    # 按重合度（max Jaccard/overlap_ratio）降序排列
    pairs.sort(key=lambda p: overlap_map.get((p["fund_a"], p["fund_b"]), 0.0), reverse=True)

    return {
        "funds": funds,
        "fund_names": fund_names,
        "matrix": matrix,
        "pairs": pairs,
        "has_mv_data": has_mv_data,
    }
