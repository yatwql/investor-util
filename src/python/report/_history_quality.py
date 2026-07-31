"""历史走势数据质量校验 — 异常检测与收益率诊断。

提取自 ``report/portfolio_history.py``。
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger("invest")


def _validate_bars(bars: list[dict]) -> list[str]:
    """检查走势数据质量，返回警告列表。

    检查项：
      - 收盘价为 0
      - 未来日期
      - 明显的异常跳变（单日涨跌 > 50%）

    Args:
        bars: 走势数据列表

    Returns:
        警告消息列表，无问题时为空列表
    """
    warnings: list[str] = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for i, b in enumerate(bars):
        close = b.get("close") or b.get("total_value", 0)
        if close == 0:
            warnings.append(f"{b['date']}: 收盘价为 0（可能停牌或数据异常）")
        if b.get("date", "") > today_str:
            warnings.append(f"{b['date']}: 日期为未来")

        # 检查异常跳变
        if i > 0:
            prev = bars[i - 1].get("close") or bars[i - 1].get("total_value", 0)
            if prev > 0 and close > 0:
                change_pct = abs(close - prev) / prev
                if change_pct > 0.5:
                    warnings.append(f"{b['date']}: 单日变化 {change_pct * 100:.1f}%（可能异常）")

    return warnings


def _diagnose_return(
    bars: list[dict],
    sorted_dates: list[str],
    valid_start_idx: int,
    fund_count_on_date: dict[str, int],
    total_return_pct: float,
    total_series: int,
) -> None:
    """诊断收益率异常：输出起止日市值、覆盖标的数、每日明细快照。"""
    if not bars:
        return

    first_bar = bars[valid_start_idx]
    last_bar = bars[-1]

    # 取起止日 + 中间等间隔抽 3 个样本
    step = max(1, (len(bars) - 1) // 4)
    sample_idxs = [valid_start_idx] + [valid_start_idx + step * i for i in range(1, 4)] + [len(bars) - 1]
    sample_idxs = sorted(set(i for i in sample_idxs if i < len(bars)))

    lines = [
        "[history] ═══ 累计收益率诊断 ═══",
        f"[history]  起算日: {first_bar['date']}  total_value={first_bar['total_value']:.2f}  "
        f"覆盖 {fund_count_on_date.get(first_bar['date'], 0)}/{total_series} 只",
        f"[history]  终止日: {last_bar['date']}  total_value={last_bar['total_value']:.2f}  "
        f"覆盖 {fund_count_on_date.get(last_bar['date'], 0)}/{total_series} 只",
        f"[history]  收益率: {total_return_pct:.2f}%",
        f"[history]  期间: {first_bar['date']} → {last_bar['date']} 共 {len(bars) - valid_start_idx} 个交易日",
    ]

    # 每日明细快照
    lines.append(f"[history]  中轴抽样（{len(sample_idxs)} 点）:")
    for idx in sample_idxs:
        b = bars[idx]
        coverage = fund_count_on_date.get(b["date"], 0)
        lines.append(
            f"[history]    {b['date']}  tv={b['total_value']:.2f}  "
            f"dd={b['drawdown']:.2f}  dd%={b['drawdown_pct']:.2f}%  "
            f"覆盖={coverage}/{total_series}"
        )

    for line in lines:
        logger.info(line)
