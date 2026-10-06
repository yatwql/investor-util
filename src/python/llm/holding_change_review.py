"""持仓变动复盘归因（章内 LLM 归因块）——编排层串行后置调用入口。

形态与 ``llm/self_review.py`` 同构（用户拍板的双轨方案之轨 2）：

  - 模块在 ``core/registry.py`` 登记（显示名/缓存前缀/TTL/用量统计/失败原因
    载体全部复用既有机制），**刻意不进** ``generators_orchestrator._MODULE_FNS``
    ——无独立并行调度语义，由 ``generate_all_llm`` 在四个分析模块 + 生成后自检
    之后**串行**调用本模块入口 ``run_holding_change_review``。
  - 输入不是其余模块的产出，而是报告 seam 注入的契约 ``holding_change_data``
    （构建期已渲染的事实块 ``prompt_block``——报告展示与 LLM 提示词同源）。
    契约缺席（feature ``holding_change_review`` 关闭 / 快照准入未过）时本函数
    **零行为**：不进 LLM、不写载体，报告归因块保持隐藏（双端同构）。
  - 结果写回 ``pipeline_data["holding_change_data"]["llm_review"]``——章内渲染
    就地读取，不设全局运行作用域载体（免 conftest 单例重置，天然随管线生命周期）。

守护契约与 seam 一致：异常只登记失败原因 + WARNING，不外抛——归因失败不影响
四个 LLM 分析模块的既有产出（报告照常生成，归因块隐藏）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.llm.skeleton import generate_llm_module

logger = logging.getLogger("invest")

HOLDING_CHANGE_MODULE_KEY = "holding_change"

# ── 运行作用域载体：结果写回契约字段，不设模块级全局 ────────────
# llm_review 由 build_holding_change_panel 初始化为 None；本模块成功后覆写为
# Markdown 文本。报告双端渲染按「非空才显示归因块」分支（与自检块同构）。
REVIEW_FIELD = "llm_review"


def run_holding_change_review(
    pipeline_data: dict | None,
    llm_config: dict | None,
    force: bool = False,
    holdings_details: list[dict] | None = None,
    purchase_constraint_block: str = "",
) -> bool:
    """生成持仓变动复盘归因并写回契约（编排层唯一入口）。

    Args:
        pipeline_data: 管线数据字典（含 seam 注入的 ``holding_change_data`` 契约）。
        llm_config: llm_settings 配置字典。
        force: 强制重算（跳过缓存）。
        holdings_details: 持仓明细（附录与指纹摘要）。
        purchase_constraint_block: 申购限购约束块（附录与指纹，与四模块同源实例）。

    Returns:
        是否产出了归因内容（契约缺席、开关关闭、调用失败均返回 ``False``）。
    """
    contract = (pipeline_data or {}).get("holding_change_data")
    if not isinstance(contract, dict) or not contract.get("available"):
        logger.debug("持仓变动复盘归因跳过：契约缺席（feature 关闭或快照准入未过）")
        return False

    from src.python.llm.skeleton import is_llm_module_enabled

    if not is_llm_module_enabled(llm_config or {}, HOLDING_CHANGE_MODULE_KEY):
        logger.debug(
            "持仓变动复盘归因已禁用（enabled_llm.%s = false），跳过",
            HOLDING_CHANGE_MODULE_KEY,
        )
        return False

    context_block = str(contract.get("prompt_block") or "")
    if not context_block:
        _register_skip_reason("事实块缺席（契约字段 prompt_block 为空）")
        logger.info("持仓变动复盘归因跳过：事实块缺席")
        return False

    signal_block = _build_signal_window_block(contract)

    from src.python.llm.generators import generate_holding_change_review

    try:
        content, _from_cache = generate_holding_change_review(
            context_block,
            signal_block=signal_block,
            holdings_details=holdings_details,
            force=force,
            llm_config=llm_config,
            purchase_constraint_block=purchase_constraint_block,
        )
    except Exception as e:  # noqa: BLE001 — 归因失败不得影响主内容（报告照常产出）
        logger.warning("持仓变动复盘归因调用异常（不影响主内容）: %s", e)
        _register_skip_reason(f"归因调用异常：{e}")
        return False

    if not content:
        _register_skip_reason("归因未产出有效内容")
        logger.warning("持仓变动复盘归因未产出有效内容（不影响主内容）")
        return False

    contract[REVIEW_FIELD] = content
    return True


def _build_signal_window_block(contract: dict[str, Any]) -> str:
    """窗口内历史信号清单（与变动事实对账用；信号功能关闭或无记录 → ``""``）。

    进提示词的同一实例由调用方一并传入指纹（进提示词必进指纹）。
    """
    try:
        from src.python.core import signal_ledger

        if not signal_ledger.is_active():
            return ""
        signals = signal_ledger.load_signals() or []
    except Exception:  # noqa: BLE001 — 信号块缺席不影响归因主体
        logger.debug("窗口信号块构建失败（忽略）", exc_info=True)
        return ""

    window_start = _ymd(contract.get("window_start"))
    window_end = _ymd(contract.get("window_end"))
    if not window_start or not window_end:
        return ""

    rows: set[tuple[str, str, str, str, str]] = set()
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        report_date = str(sig.get("report_date") or "")
        day = report_date.replace("-", "")[:8]
        if not day or not (window_start <= day <= window_end):
            continue
        direction = sig.get("direction")
        dir_text = {1: "看多", -1: "看空"}.get(direction, "中性")
        rows.add(
            (
                report_date,
                str(sig.get("subject") or "portfolio"),
                str(sig.get("signal_type") or ""),
                str(sig.get("rating") or ""),
                dir_text,
            )
        )
    if not rows:
        return ""

    ordered = sorted(rows, reverse=True)[:10]
    lines = ["【窗口内历史信号（确定性信号账本，与变动事实对账用，最多 10 条）】"]
    for report_date, subject, signal_type, rating, dir_text in ordered:
        lines.append(f"  {report_date} {subject} {signal_type} 评级={rating} 方向={dir_text}")
    return "\n".join(lines)


def _ymd(value: Any) -> str:
    """任意时间戳形态 → YYYYMMDD（无法解析返回 ``""``）。"""
    s = str(value or "").strip().replace("-", "")
    return s[:8] if len(s) >= 8 and s[:8].isdigit() else ""


def _register_skip_reason(reason: str) -> None:
    """把「未产出」原因登记到失败原因载体（与其余模块同源，供报告层展示）。"""
    try:
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        LLM_MODULE_FAILURE[HOLDING_CHANGE_MODULE_KEY] = reason
    except Exception:  # noqa: BLE001 — 登记失败不影响主流程
        logger.debug("[holding_change_review] 失败原因登记失败", exc_info=True)


__all__ = [
    "HOLDING_CHANGE_MODULE_KEY",
    "REVIEW_FIELD",
    "run_holding_change_review",
]


# ── 提示词侧生成器（自 llm/generators.py 迁入，re-export 见彼处） ──


def generate_holding_change_review(
    context_block: str,
    signal_block: str = "",
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: Any = None,
    llm_config: dict | None = None,
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
) -> tuple[str | None, bool]:
    """生成持仓变动复盘归因（章内 LLM 归因块）。

    走与其余模块相同的骨架（``generate_llm_module``）——缓存键、TTL、尾部标识行、
    失败原因登记全部复用既有机制；档位/开关判定在调用侧
    （``llm/holding_change_review.py``）。输入是报告契约渲染好的事实块，
    内容寻址由 ``holding_change_review_fingerprint`` 保证（进提示词必进指纹）。

    实现自 ``llm/generators.py`` 迁入（串行归因入口与实现同居一模块；
    ``generators`` 保留 re-export，既有 import 面与测试 patch 面不变）。
    """
    from src.python.llm.module_fingerprint import holding_change_review_fingerprint
    from src.python.llm.prompts import _SYSTEM_HOLDING_CHANGE_REVIEW, _build_holding_change_review_prompt

    def _fingerprint():
        return holding_change_review_fingerprint(
            context_block,
            signal_block=signal_block,
            holdings_details=holdings_details,
            purchase_block=purchase_constraint_block or "",
        )

    def _prompt():
        return _build_holding_change_review_prompt(context_block, signal_block)

    return generate_llm_module(
        llm_config,
        "holding_change",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_HOLDING_CHANGE_REVIEW,
        prompt_builder=_prompt,
        max_tokens_default=2048,
        timeout_default=90.0,
        output_brief_limit=200,
        holdings_details=holdings_details,
        purchase_constraint_block=purchase_constraint_block,
        holding_change_block=holding_change_block,
        event_impact_block=event_impact_block,
    )
