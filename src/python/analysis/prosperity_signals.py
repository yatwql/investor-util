"""景气度框架 —— 本地信号提取原语（零网络）。

职责：把**已经在本地可用**的输入（持仓明细、历史快照、基准收益）折算为打分器
需要的数值信号，不含任何打分与视图逻辑；打分与装配见 ``prosperity_scoring`` /
``prosperity_framework``。拆分轴与既有「打分内核 vs 视图装配」一致（评分内核与
信号提取各自内聚，避免单文件越界）。

本模块不含网络请求：快照读取、基准收益读取均为既有本地产物。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.num_utils import finite_or

logger = logging.getLogger("invest")


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole > 0 else 0.0


def _top10_concentration_pct(holdings_details: list[dict[str, Any]]) -> float | None:
    total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details)
    if total <= 0:
        return None
    values = sorted((finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details), reverse=True)
    return _pct(sum(values[:10]), total)


def _snapshot_holding_codes(snap: Any) -> set[str]:
    """从一期快照中提取持仓代码集合。

    兼容两种形态（快照来源经 `history_snapshot.load_all()`，返回**冻结 dataclass**）：

      - `SnapshotData` 对象：`snap.accounts[*].holdings[*].code`（生产形态）
      - dict 形态：`{"accounts": [{"holdings": [{"code": ...}]}]}` 或
        `{"holdings"/"details": [{"code": ...}]}`（测试/外部注入形态）

    任何字段缺失/类型异常一律按「无该字段」处理（返回值可能为空集），
    由调用方判定该期不可用 —— 本函数**不得抛异常**（诊断功能不拖垮主报告）。
    """
    codes: set[str] = set()

    def _harvest(items: Any) -> None:
        for item in items or []:
            if isinstance(item, dict):
                code = item.get("code")
            else:
                code = getattr(item, "code", None)
            if code:
                codes.add(str(code))

    accounts = getattr(snap, "accounts", None)
    if accounts is None and isinstance(snap, dict):
        accounts = snap.get("accounts")
    for account in accounts or []:
        holdings = getattr(account, "holdings", None)
        if holdings is None and isinstance(account, dict):
            holdings = account.get("holdings")
        _harvest(holdings)

    if not codes and isinstance(snap, dict):
        _harvest(snap.get("holdings") or snap.get("details"))
    return codes


def _turnover_proxy_pct(snapshots: list[Any] | None) -> float | None:
    """换手代理（周期拼接）：最近两期快照持仓集合的变动率（1 - Jaccard）。

    Args:
        snapshots: 按时间升序的快照序列（`SnapshotData` 对象或 dict 形态）。

    Returns:
        变动率百分比；不足两期 / 任一期无持仓 / 形态不可解析时返回 None
        （该子项标记未验证，不计分）。
    """
    if not snapshots or len(snapshots) < 2:
        return None
    try:
        prev, cur = _snapshot_holding_codes(snapshots[-2]), _snapshot_holding_codes(snapshots[-1])
    except Exception:  # 形态异常 → 该子项未验证（不得冒泡）
        logger.warning("[prosperity_framework] 快照形态不可解析，换手代理标记未验证", exc_info=True)
        return None
    if not prev or not cur:
        return None
    union = prev | cur
    if not union:
        return None
    return round((1 - len(prev & cur) / len(union)) * 100, 2)


def _benchmark_returns(benchmarks: Any) -> list[tuple[str, float]]:
    """提取对比基准的区间收益率，返回 [(名称, 收益率%), ...]。

    兼容两种形态（**生产为 list**，见 `PortfolioHistoryCalculator.get_combined_timeseries`
    的 `benchmarks` 契约：`[{code, name, bars, total_return_pct, ...}, ...]`）：

      - list/tuple[dict]：生产形态
      - dict[str, dict]：测试/外部注入形态

    非 dict 元素、缺 `total_return_pct`、非有限数值一律跳过（**不得抛异常**）。
    """
    if isinstance(benchmarks, dict):
        items: list[Any] = list(benchmarks.values())
    elif isinstance(benchmarks, (list, tuple)):
        items = list(benchmarks)
    else:
        return []

    out: list[tuple[str, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get("total_return_pct")
        # bool 是 int 子类但语义上不是收益率；仅接受 int/float（字符串一律跳过，
        # 且不可用 finite_or(None) —— 其内部 float(None) 会抛 TypeError）
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        value = finite_or(raw, None)
        if value is None:
            continue
        name = str(item.get("name") or item.get("code") or "基准")
        out.append((name, float(value)))
    return out
