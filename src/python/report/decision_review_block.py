"""决策跨期反思闭环 — 报告「历史决策复盘」区块数据装配。

从当前账本 fold 结果组装一份报告展示数据契约，供 HTML/Excel writer 渲染
「历史决策复盘」区块（非回测、仅供反思参考）。

装配纪律：
  - 本模块属 report 层（仅 report 消费），单向依赖 ``core.decision_ledger``。
  - 开关关闭或无任何决策记录时返回 None（writer 保持既有输出不变，对齐
    snapshot_diff_data 等可选数据契约模式）。
  - 展示口径与账本 fold 一致：命中率仅在有效样本（≥MEANINGFUL_SAMPLE）时给出
    结论值；样本不足时仅给计数（accuracy=None + sample_sufficient=False）。
  - 免责声明由本层统一给出，杜绝渲染层各写各的免责口径。
"""

from __future__ import annotations

from typing import Any

from src.python.core import decision_ledger as dl

_DISCLAIMER = "本复盘基于历史判断与真实行情的滞后对账，仅供反思参考，不构成任何投资建议。"

# 各分列表展示条数上界
_RECENT_LIMIT = 5


def is_active() -> bool:
    return dl.is_active()


def _direction_label(direction: int) -> str:
    if direction == dl.DIRECTION_LONG:
        return "看多（加仓建议）"
    if direction == dl.DIRECTION_SHORT:
        return "看空（减仓/卖出建议）"
    return "中性"


def _pending_row(decision: dict[str, Any]) -> dict[str, Any]:
    """pending 决策 → 展示行（新登记待后续行情结算）。"""
    return {
        "code": decision.get("code"),
        "name": decision.get("name"),
        "direction": _direction_label(int(decision.get("direction") or 0)),
        "magnitude": decision.get("magnitude") or "",
        "detail": decision.get("detail") or "",
        "report_date": decision.get("report_date") or "",
    }


def _settled_row(decision: dict[str, Any]) -> dict[str, Any]:
    """settled 决策 → 展示行（含结算结果）。"""
    s = decision.get("settlement") or {}
    return {
        "code": decision.get("code"),
        "name": decision.get("name"),
        "direction": _direction_label(int(decision.get("direction") or 0)),
        "detail": decision.get("detail") or "",
        "outcome": s.get("outcome") or "",
        "raw_return": s.get("raw_return"),
        "settle_date": s.get("settle_date") or "",
        "horizon_bars": s.get("horizon_bars") or 0,
    }


def build_review_block(
    *,
    report_date: str | None = None,
    ledger_path: str | None = None,
) -> dict[str, Any] | None:
    """装配「历史决策复盘」报告数据契约。

    Args:
        report_date: 本次报告交易日（展示用；供扩展，未直接参与折叠）。
        ledger_path: 账本路径（测试隔离用）；缺省走 conftest 重定向默认路径。

    Returns:
        None（开关关闭或账本无任何记录时）；否则数据契约 dict：
            available / disclaimer / pending_count / settled_count /
            direction_accuracy（仅样本足够给值）/ sample_sufficient /
            alpha_mean / recent_pending[≤5] / recent_settled[≤5]
    """
    if not is_active():
        return None
    stats = dl.fold_ledger(path=ledger_path)
    if not stats["decisions"]:
        return None

    decisions = stats["decisions"]
    pending = [d for d in decisions if d.get("status") != "settled"]
    settled = [d for d in decisions if d.get("status") == "settled"]

    # 最近展示：settled 按结算日期降序；pending 保持登记顺序（倒序取新）
    settled_sorted = sorted(
        settled,
        key=lambda r: str((r.get("settlement") or {}).get("settle_date") or r.get("created_at") or ""),
        reverse=True,
    )

    return {
        "available": True,
        "report_date": report_date or "",
        "disclaimer": _DISCLAIMER,
        "pending_count": stats["pending_count"],
        "settled_count": stats["settled_count"],
        "sample_sufficient": stats["sample_sufficient"],
        "direction_accuracy": stats["direction_accuracy"] if stats["sample_sufficient"] else None,
        "alpha_mean": stats["alpha_mean"],
        "recent_pending": [_pending_row(d) for d in pending[-_RECENT_LIMIT:]],
        "recent_settled": [_settled_row(d) for d in settled_sorted[:_RECENT_LIMIT]],
    }
