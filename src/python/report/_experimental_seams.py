"""报告管线实验功能挂载点（seam）—— 同一守护语义只实现一次。

三个实验功能（决策跨期反思闭环 / 模块级质量分级 / 确定性数值信号沉淀）在
``_report_generation._generate_report_full`` 的固定工序位置插入挂载点。它们共享
同一契约：**实验功能自身的异常绝不中断报告主链路**——单条实验逻辑出错只降级为
一条告警，报告按既有输出继续生成。

抽出本模块的两个理由：

  - **守护语义只有一份**：此前四个挂载点各自内联 ``try/except Exception`` +
    ``reporter.warn`` + ``logger.exception``，告警文案与日志标签逐处重写；改一处
    必漏三处，与缓存指纹「读写两份拼接」属同一病根（判据复制即漂移温床）。
  - **挂载点可单测**：内联在管线函数中时只能靠驱动整条报告管线覆盖，故开关判定
    与数据注入此前无任何直接断言；抽为独立函数后可按开关组合直接断言「开关关 →
    无副作用」「下游异常 → 只告警不外抛」。

顺序约束（由调用方 ``_generate_report_full`` 保证，不得调换）：

  1. **结算先于 LLM 拉取**：否则当次教训（含本批结算结果）在 LLM 注入前未落档，
     提示词读不到新结算。
  2. **质量横幅晚于决策登记**：横幅会改写模块内容文本，须避开操作建议表解析。
  3. **信号沉淀晚于 LLM 生成**：尾部风险等 A 通道键在 LLM 生成阶段才注入
     ``pipeline_data``，过早登记会漏采（适配器对缺失键逐项跳过，不构成硬依赖）。

依赖：本模块属 report 层，只调用 ``core`` 与 report 各子模块的公开入口。导入时机
分两类，按「开关关闭时是否值得付出成本」判定：

  - **report 功能子模块在挂载点内按需导入**——这些子模块牵动 analysis/report 的大
    片依赖，开关关闭时不应为其付出导入成本；导入期异常也落入同一守护（与下游逻辑
    异常一视同仁）。
  - **core 账本模块（``decision_ledger`` / ``signal_ledger``）顶层导入**——两者只
    依赖 stdlib + 同层 core，且 ``is_active()`` 开关判定本身就要落在它们上；顶层
    导入不构成启动负担。

该分界由 ``test_experimental_seams`` 的接线守卫逐项锁定：顶层 ``src.python.*``
导入集合必须恰为上述 core 模块 + ``report.progress``（接口，供模块级类型标注）。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from src.python.core import decision_ledger, signal_ledger
from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")

_T = TypeVar("_T")


def _guarded(
    seam: str,
    tag: str,
    reporter: ProgressReporter,
    action: Callable[[], _T],
    on_error: _T,
) -> _T:
    """执行单个挂载点动作：异常 → 告警 + 异常日志 + 兜底值，绝不外抛。

    Args:
        seam: 挂载点中文名（进用户可见的告警文案，如 "决策复盘（确定性结算/登记）"）
        tag: 日志标签（如 "decision_reflection"），供故障定位按实验功能检索
        reporter: 进度上报器
        action: 实际动作，其返回值原样透传
        on_error: 动作异常时的兜底返回值

    Returns:
        ``action()`` 的返回值；动作抛异常时返回 ``on_error``。
    """
    try:
        return action()
    except Exception:
        reporter.warn(f"{seam}执行异常，已跳过")
        logger.exception("[%s] %s 挂载点异常", tag, seam)
        return on_error


def record_deterministic_decisions(prep: dict, action_data: Any, reporter: ProgressReporter) -> None:
    """决策跨期反思闭环（确定性侧）：先结旧、再入新。

    ① 用真实后续行情结算到期 pending 决策；② 登记本报告最终 ``action_data``
    （含组合峰值重建版）中的确定性卖出建议为 pending。

    结算必须先于 LLM 拉取，故本挂载点置于管线 3.6 段（LLM 生成之前）。
    开关关闭 → ``decision_ledger.is_active()`` 为假 → 不读不写直接返回。
    """
    if not decision_ledger.is_active():
        return

    def _action() -> None:
        from src.python.report import decision_record, decision_settlement

        _report_date = prep["today_str"]
        # ① 结算到期 pending 决策（幂等：同 decision 只结一次；未到期/行情
        #    不可得保持 pending；无基线的早期登记暂缓不结）。
        _settle = decision_settlement.settle_pending_decisions(report_date=_report_date)
        if _settle.get("settled"):
            reporter.ok(f"决策复盘：已结算 {_settle['settled']} 条到期决策")
        elif _settle.get("deferred") or _settle.get("skipped"):
            reporter.info("决策复盘：无到期可结算决策")
        # ② 登记确定性卖出建议（入账必可结算：仅带持仓基线的 code 落账；
        #    同日重复运行由账本 pending 防重，不累积重复 pending）
        _reg = decision_record.register_action_decisions(
            action_data,
            holdings_details=prep.get("holdings_details"),
            report_date=_report_date,
        )
        if _reg.get("registered"):
            reporter.ok(f"决策复盘：登记 {_reg['registered']} 条确定性建议")
        else:
            logger.info("[decision_reflection] 确定性建议登记为空（无卖出信号或无基线）")

    _guarded("决策复盘（确定性结算/登记）", "decision_reflection", reporter, _action, None)


def record_llm_decisions_and_review_block(
    prep: dict,
    llm_content: tuple,
    enable_llm: bool,
    pipeline_data: dict | None,
    reporter: ProgressReporter,
) -> None:
    """决策跨期反思闭环（LLM 侧）：③ 登记 LLM 操作建议 ④ 装配复盘区块。

    ③ 解析 expert_review 操作建议表 → 逐 code 方向登记。完整可解析路径才执行：
    ``enable_llm`` 关 / expert_review 为空 / 降级回退占位均无「|」数据行，解析
    自然跳过——回退内容不是真实意见，不登记。
    ④ 复盘区块数据契约装配 → 注入 ``pipeline_data``，供 HTML/Excel 行动章内嵌块
    消费（缺席时两条输出路径均保持既有输出）。
    """
    if not decision_ledger.is_active():
        return

    def _action() -> None:
        from src.python.report import decision_llm_capture, decision_review_block

        if enable_llm and llm_content and len(llm_content) > 1 and llm_content[1]:
            _llm_reg = decision_llm_capture.register_llm_decisions(
                llm_content[1],
                prep.get("holdings_details"),
                report_date=prep["today_str"],
            )
            if _llm_reg.get("registered"):
                reporter.ok(f"决策复盘：登记 {_llm_reg['registered']} 条 LLM 操作建议")
            else:
                logger.info("[decision_reflection] LLM 操作建议登记为空（无方向建议或同日已登记）")
        _review_block = decision_review_block.build_review_block(report_date=prep["today_str"])
        if _review_block and pipeline_data is not None:
            pipeline_data["decision_review_data"] = _review_block
            reporter.info("决策复盘：行动章复盘区块数据已装配")

    _guarded("决策复盘（LLM 登记/复盘装配）", "decision_reflection", reporter, _action, None)


def apply_module_quality_banners(llm_content: tuple, reporter: ProgressReporter) -> tuple:
    """模块级质量分级：给 4 个 LLM 模块输出评级，低评级内容头部注入质量横幅。

    只标注不阻断、不重试、不写回缓存。置于决策登记之后：横幅改写内容文本，须
    避开操作建议表解析。开关判定在 ``llm_quality`` 内部（关闭时原样返回入参）。

    Returns:
        注入横幅后的 ``llm_content``；分级异常时返回**入参原值**，报告保持既有输出。
    """

    def _action() -> tuple:
        from src.python.report import llm_quality

        return llm_quality.apply_quality_banners(llm_content, reporter)

    return _guarded("模块级质量分级", "llm_quality", reporter, _action, llm_content)


def record_deterministic_signals(pipeline_data: dict | None, prep: dict, reporter: ProgressReporter) -> None:
    """确定性数值信号沉淀：抽取五类确定性评级并打来源标签后入账。

    五类为市场温度 / 估值分位 / 尾部风险 / 风格因子 / 再平衡超限；幂等（同日同
    类型同标的只记一次）。开关关闭 → ``signal_ledger.is_active()`` 为假 → 不读不写。
    """
    if not signal_ledger.is_active():
        return

    def _action() -> None:
        from src.python.report import signal_record

        _sig = signal_record.register_deterministic_signals(
            pipeline_data,
            report_date=prep["today_str"],
        )
        if _sig.get("registered"):
            reporter.ok(f"确定性信号沉淀：登记 {_sig['registered']} 条确定性评级")
        else:
            logger.info("[signal_ledger] 确定性信号登记为空（无可登记评级或同日已登记）")

    _guarded("确定性信号沉淀", "signal_ledger", reporter, _action, None)


__all__ = [
    "apply_module_quality_banners",
    "record_deterministic_decisions",
    "record_deterministic_signals",
    "record_llm_decisions_and_review_block",
]
