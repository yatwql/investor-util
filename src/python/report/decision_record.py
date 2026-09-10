"""决策跨期反思闭环 — 确定性载体登记。

从 report seam 已算好的 ``action_data``（最终含组合峰值重建版）中抽取卖出向
确定性建议（再平衡触发 / 交易纪律触发信号）登记为 pending 决策，供日后用真实
行情结算。

数据源选择：
  - 以「纪律/再平衡触发信号」为登记源——它们是纯触发推荐，反映"建议减仓"的
    判断本身；``rebalance_advice`` 是二者派生、经份额取整与现金守卫裁剪的可执行
    清单，不产生新的判断语义，故不单独登记，避免同 code 重复。
  - 纪律信号中含组合级回撤信号（code 为空，无法按标的结算）→ 跳过。
  - 同 code 纪律与再平衡同时触发时，纪律规则（止盈/止损，更为紧迫）优先。
  - **入账必可结算**：登记时须带 baseline_close（取持仓明细 price，即登记日最新
    已知价，作结算基线）——结算服务仅对带基线的决策可结，无基线决策将永久滞留
    pending 污染统计 → 无可解析基线的 code 登记跳过（与 decision_llm_capture 同纪律）。

约束：
  - 本模块属 report 层（消费 report seam 传入的 action_data），单向依赖
    ``core.decision_ledger``；不反向 import analysis/report 内部实现细节。
  - 开关关闭时全链路无感（不读不写，直接返回空结果）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.python.core import decision_ledger as dl
from src.python.core.num_utils import finite_or

logger = logging.getLogger("invest")

# 纪律信号 action → 强度近似（供 magnitude）
_DISCIPLINE_ACTION_MAGNITUDE: dict[str, str] = {
    "部分止盈": "mid",
    "止损/减仓": "high",
    "减仓控回撤": "high",
}

# 6 位代码抽取：匹配「前后非数字」的连续 6 位（同 decision_llm_capture，用于持仓
# 代码含 sh600000 前缀时的裸 6 位对账）
_CODE_RE = re.compile(r"(?<!\d)([0-9]{6})(?!\d)")


def _holdings_price_map(holdings_details: list[dict[str, Any]] | None) -> dict[str, float]:
    """持仓明细 → {code: price}（price 即登记日最新已知价，作结算基线）。

    非裸 6 位持仓代码（sh600000 等）补挂裸 6 位别名，便于按信号 code 对账。
    """
    price_map: dict[str, float] = {}
    for holding in holdings_details or []:
        code = str(holding.get("code") or "").strip()
        if not code:
            continue
        try:
            price = finite_or(holding.get("price"))
        except (TypeError, ValueError):
            price = 0.0
        price_map[code] = price
        m = _CODE_RE.search(code)
        if m and m.group(1) != code:
            price_map.setdefault(m.group(1), price)
    return price_map


def is_active() -> bool:
    return dl.is_active()


def _discipline_magnitude(sig: dict[str, Any]) -> str:
    return _DISCIPLINE_ACTION_MAGNITUDE.get(str(sig.get("action") or ""), "mid")


def _discipline_detail(sig: dict[str, Any]) -> str:
    # 状态文案含规则与触发信息，如「触发（超线 2.1%，建议部分止盈）」
    status = str(sig.get("status_label") or "").strip()
    if status:
        return status
    action = str(sig.get("action") or "").strip()
    rule = str(sig.get("rule") or "").strip()
    return f"{rule} 建议{action}" if rule and action else (action or rule)


def extract_deterministic_decisions(
    action_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """从 action_data 抽取卖出向确定性决策行（按 code 去重，纪律优先）。

    Args:
        holdings_details: 持仓明细（提供 code → price 结算基线）；缺省仅返回不带
            baseline_close 的行（无 price 仍返回，由登记侧据是否带基线决定是否落账）。

    Returns:
        [{code, name, direction=DIRECTION_SHORT, magnitude, carrier, detail,
          baseline_close}, ...]；无可用数据返回空列表。
    """
    if not action_data or not action_data.get("available"):
        return []

    price_map = _holdings_price_map(holdings_details) if holdings_details else {}
    rows: dict[str, dict[str, Any]] = {}

    def _add(code: str, row: dict[str, Any]) -> None:
        baseline = price_map.get(code)
        if baseline is not None and baseline > 0:
            row["baseline_close"] = baseline
        rows[code] = row

    # ① 纪律信号（紧迫性更高；组合级回撤空 code 跳过）
    for sig in action_data.get("discipline_signals") or []:
        code = str(sig.get("code") or "").strip()
        if not code:
            continue
        _add(
            code,
            {
                "code": code,
                "name": str(sig.get("name") or "").strip(),
                "direction": dl.DIRECTION_SHORT,
                "magnitude": _discipline_magnitude(sig),
                "carrier": dl.CARRIER_DISCIPLINE,
                "detail": _discipline_detail(sig),
            },
        )

    # ② 再平衡触发信号（仅当纪律未覆盖该 code 时补充）
    for sig in action_data.get("rebalance_signals") or []:
        code = str(sig.get("code") or "").strip()
        if not code or code in rows:
            continue
        _add(
            code,
            {
                "code": code,
                "name": str(sig.get("name") or "").strip(),
                "direction": dl.DIRECTION_SHORT,
                "magnitude": "mid",
                "carrier": dl.CARRIER_REBALANCE,
                "detail": str(sig.get("action") or "建议减仓").strip(),
            },
        )

    return list(rows.values())


def register_action_decisions(
    action_data: dict[str, Any] | None,
    *,
    holdings_details: list[dict[str, Any]] | None = None,
    report_date: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """登记 action_data 中的确定性卖出建议为 pending 决策。

    Args:
        holdings_details: 持仓明细（供结算基线 price 解析）。无该参数时逐行无基线
            → 全部跳过不落账（保证「入账必可结算」，不留永久 pending 债务）。

    Returns:
        {"registered": int, "ids": [decision_id, ...]}
    """
    if not is_active():
        return {"registered": 0, "ids": []}
    rows = extract_deterministic_decisions(action_data, holdings_details)
    ids: list[str] = []
    skipped_dup = 0
    for r in rows:
        baseline = r.get("baseline_close")
        if baseline is None or baseline <= 0:
            logger.info(
                "[decision_record] 无可用基线跳过确定性决策登记: %s %s",
                r["code"],
                r.get("name") or "",
            )
            continue
        # 同日重复登记防重：append-only 账本避免同(报告日, code, carrier) pending
        # 累积（报告重生成/缓存命中路径）。跨日运行 report_date 不同不误伤。
        if dl.same_day_pending_exists(
            code=r["code"],
            carrier=r["carrier"],
            report_date=report_date,
            path=path,
        ):
            skipped_dup += 1
            continue
        did = dl.append_decision(
            code=r["code"],
            name=r["name"],
            direction=r["direction"],
            carrier=r["carrier"],
            magnitude=r["magnitude"],
            detail=r["detail"],
            report_date=report_date,
            baseline_close=baseline,
            path=path,
        )
        ids.append(did)
    if skipped_dup:
        logger.info("[decision_record] 同日重复确定性决策跳过: %d 条", skipped_dup)
    return {"registered": len(ids), "ids": ids}
