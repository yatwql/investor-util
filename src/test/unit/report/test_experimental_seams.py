"""报告管线实验挂载点（seam）单元测试 — 守护语义与开关判定。

三个实验功能挂载点共享同一契约：**实验功能自身的异常绝不中断报告主链路**。
抽取为 ``report/_experimental_seams`` 之前，四个挂载点各自内联
``try/except``，只能靠驱动整条报告管线间接覆盖 —— 开关判定与数据注入因此
长期无任何直接断言。本模块按开关组合直接断言三类契约：

  1. **开关关闭 → 完全无感**：不读不写账本、不触碰 ``pipeline_data``、不调用下游。
  2. **开关开启 → 动作生效**：结算/登记被调用，复盘区块按契约注入 ``pipeline_data``。
  3. **下游异常 → 只告警不外抛**：``reporter.warn`` 出现「执行异常，已跳过」，
     需要返回值的一侧（质量横幅）返回**入参原值**。

另含一项**接线顺序守卫**（``TestFacadeWiringOrder``）：顺序约束由调用方
``_generate_report_full`` 保证，静态解析其函数体断言四个挂载点的相对次序 ——
调换即破坏语义（结算须先于 LLM 拉取、横幅须晚于决策登记、信号沉淀须晚于 LLM 生成）。

运行：
  pytest src/test/unit/report/test_experimental_seams.py -v
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from src.python.core.constants import PROJECT_ROOT
from src.python.report import _experimental_seams as seams
from src.python.report.progress import ProgressReporter

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

# 四个挂载点按调用方保证的语义顺序（与模块文档字符串「顺序约束」一致）
_SEAM_ORDER = [
    "record_deterministic_decisions",
    "record_llm_decisions_and_review_block",
    "apply_module_quality_banners",
    "record_deterministic_signals",
]

_SKIPPED_HINT = "执行异常，已跳过"

# 挂载点读取的最小 prep 契约（today_str 供报告日期，holdings_details 供基线）
_PREP = {"today_str": "2026-09-10", "holdings_details": {"600900": {"name": "长江电力"}}}


class _RecordingReporter(ProgressReporter):
    """记录各级消息的进度报告器（默认 ProgressReporter 各方法为空实现）。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[tuple[str, str]] = []

    def info(self, msg: str) -> None:
        self.messages.append(("info", msg))

    def ok(self, msg: str) -> None:
        self.messages.append(("ok", msg))

    def warn(self, msg: str) -> None:
        self.messages.append(("warn", msg))

    def error(self, msg: str) -> None:
        self.messages.append(("error", msg))

    def warns(self) -> list[str]:
        return [msg for level, msg in self.messages if level == "warn"]


@pytest.fixture
def reporter() -> _RecordingReporter:
    return _RecordingReporter()


def _patch_active(module: str, active: bool):
    """替换账本模块的 ``is_active`` 开关判定（挂载点内按模块属性解析）。"""
    return patch(f"src.python.core.{module}.is_active", return_value=active)


# ── ① 确定性结算/登记 ────────────────────────────────────────


class TestDeterministicDecisions:
    """决策跨期反思闭环（确定性侧）挂载点。"""

    def test_flag_off_is_inert(self, reporter, tmp_path):
        """开关关闭 → 结算与登记均不被调用（不读不写账本）。"""
        with (
            _patch_active("decision_ledger", False),
            patch("src.python.report.decision_settlement.settle_pending_decisions") as settle,
            patch("src.python.report.decision_record.register_action_decisions") as register,
        ):
            seams.record_deterministic_decisions(_PREP, {"sell": []}, reporter)

        settle.assert_not_called()
        register.assert_not_called()
        assert reporter.messages == []

    def test_flag_on_settles_then_registers(self, reporter):
        """开关开启 → 先结算到期决策、再登记本报告确定性建议。"""
        with (
            _patch_active("decision_ledger", True),
            patch(
                "src.python.report.decision_settlement.settle_pending_decisions",
                return_value={"settled": 2},
            ) as settle,
            patch(
                "src.python.report.decision_record.register_action_decisions",
                return_value={"registered": 1},
            ) as register,
        ):
            seams.record_deterministic_decisions(_PREP, {"sell": []}, reporter)

        settle.assert_called_once_with(report_date="2026-09-10")
        register.assert_called_once()
        assert register.call_args.kwargs["report_date"] == "2026-09-10"
        ok_messages = [msg for level, msg in reporter.messages if level == "ok"]
        assert any("已结算 2 条" in msg for msg in ok_messages)
        assert any("登记 1 条确定性建议" in msg for msg in ok_messages)
        assert reporter.warns() == []

    def test_downstream_exception_warns_only(self, reporter, caplog):
        """结算抛异常 → 只告警 + 异常日志，不外抛，且不再继续登记。"""
        with (
            _patch_active("decision_ledger", True),
            patch(
                "src.python.report.decision_settlement.settle_pending_decisions",
                side_effect=RuntimeError("boom"),
            ),
            patch("src.python.report.decision_record.register_action_decisions") as register,
            caplog.at_level(logging.ERROR, logger="invest"),
        ):
            # 不外抛即通过（挂载点异常不得中断报告主链路）
            seams.record_deterministic_decisions(_PREP, {"sell": []}, reporter)

        register.assert_not_called()
        assert len(reporter.warns()) == 1
        assert "决策复盘（确定性结算/登记）" in reporter.warns()[0]
        assert _SKIPPED_HINT in reporter.warns()[0]
        assert any("[decision_reflection]" in record.message for record in caplog.records)


# ── ③④ LLM 登记 / 复盘区块装配 ───────────────────────────────


class TestLlmDecisionsAndReviewBlock:
    """决策跨期反思闭环（LLM 侧）挂载点。"""

    def test_flag_off_does_not_touch_pipeline_data(self, reporter):
        """开关关闭 → 不写 pipeline_data、不调用下游。"""
        pipeline_data: dict = {}

        with (
            _patch_active("decision_ledger", False),
            patch("src.python.report.decision_llm_capture.register_llm_decisions") as register,
            patch("src.python.report.decision_review_block.build_review_block") as build,
        ):
            seams.record_llm_decisions_and_review_block(_PREP, (None, "专家复盘内容"), True, pipeline_data, reporter)

        register.assert_not_called()
        build.assert_not_called()
        assert pipeline_data == {}
        assert reporter.messages == []

    def test_flag_on_injects_review_block(self, reporter):
        """开关开启 → 登记 LLM 操作建议，并把复盘区块注入 pipeline_data。"""
        pipeline_data: dict = {}
        block = {"available": True, "pending_count": 1}

        with (
            _patch_active("decision_ledger", True),
            patch(
                "src.python.report.decision_llm_capture.register_llm_decisions",
                return_value={"registered": 3},
            ) as register,
            patch(
                "src.python.report.decision_review_block.build_review_block",
                return_value=block,
            ),
        ):
            seams.record_llm_decisions_and_review_block(_PREP, (None, "专家复盘内容"), True, pipeline_data, reporter)

        assert register.call_args.args[0] == "专家复盘内容"
        assert pipeline_data["decision_review_data"] is block
        ok_messages = [msg for level, msg in reporter.messages if level == "ok"]
        assert any("登记 3 条 LLM 操作建议" in msg for msg in ok_messages)

    def test_flag_on_without_llm_skips_registration_but_builds_block(self, reporter):
        """LLM 关闭 → 不登记（回退占位非真实意见），复盘区块仍装配。"""
        pipeline_data: dict = {}
        block = {"available": True}

        with (
            _patch_active("decision_ledger", True),
            patch("src.python.report.decision_llm_capture.register_llm_decisions") as register,
            patch(
                "src.python.report.decision_review_block.build_review_block",
                return_value=block,
            ),
        ):
            seams.record_llm_decisions_and_review_block(_PREP, (None, None), False, pipeline_data, reporter)

        register.assert_not_called()
        assert pipeline_data["decision_review_data"] is block

    def test_none_pipeline_data_does_not_raise(self, reporter):
        """pipeline_data 为 None → 区块不注入，但不得抛异常。"""
        with (
            _patch_active("decision_ledger", True),
            patch("src.python.report.decision_llm_capture.register_llm_decisions"),
            patch(
                "src.python.report.decision_review_block.build_review_block",
                return_value={"available": True},
            ),
        ):
            seams.record_llm_decisions_and_review_block(_PREP, (None, None), False, None, reporter)

        assert reporter.warns() == []

    def test_downstream_exception_warns_only(self, reporter):
        """下游异常 → 只告警，不外抛，pipeline_data 保持未注入。"""
        pipeline_data: dict = {}

        with (
            _patch_active("decision_ledger", True),
            patch(
                "src.python.report.decision_llm_capture.register_llm_decisions",
                side_effect=RuntimeError("boom"),
            ),
        ):
            seams.record_llm_decisions_and_review_block(_PREP, (None, "专家复盘内容"), True, pipeline_data, reporter)

        assert pipeline_data == {}
        assert len(reporter.warns()) == 1
        assert "决策复盘（LLM 登记/复盘装配）" in reporter.warns()[0]


# ── 模块级质量分级 ───────────────────────────────────────────


class TestApplyModuleQualityBanners:
    """模块级质量分级挂载点（唯一带返回值 —— 异常须回退入参原值）。"""

    def test_success_passes_through_downstream_result(self, reporter):
        """成功 → 原样返回下游结果（挂载点不做二次加工）。"""
        incoming = ("a", "b", "c", "d")
        injected = ("A", "b", "c", "d")

        with patch("src.python.report.llm_quality.apply_quality_banners", return_value=injected):
            result = seams.apply_module_quality_banners(incoming, reporter)

        assert result == injected

    def test_downstream_exception_returns_input_unchanged(self, reporter):
        """分级异常 → 返回**入参原值**（同一对象），报告保持既有输出。"""
        incoming = ("a", "b", "c", "d")

        with patch(
            "src.python.report.llm_quality.apply_quality_banners",
            side_effect=RuntimeError("boom"),
        ):
            result = seams.apply_module_quality_banners(incoming, reporter)

        assert result is incoming
        assert len(reporter.warns()) == 1
        assert "模块级质量分级" in reporter.warns()[0]
        assert _SKIPPED_HINT in reporter.warns()[0]

    def test_missing_downstream_symbol_returns_input_unchanged(self, reporter):
        """下游符号缺失 → 同样回退入参原值。

        按需导入使「模块存在但符号改名」这类故障与下游逻辑异常落在同一 ``try``
        块（导入语句本身就在守护内），此处以属性缺失代表该故障面。
        """
        incoming = ("a", "b", "c", "d")

        with patch("src.python.report.llm_quality.apply_quality_banners", new=None):
            # new=None 使符号存在但不可调用 → 解析期 AttributeError，落入同一守护
            result = seams.apply_module_quality_banners(incoming, reporter)

        assert result is incoming
        assert len(reporter.warns()) == 1


# ── 确定性数值信号沉淀 ───────────────────────────────────────


class TestDeterministicSignals:
    """确定性数值信号沉淀挂载点。"""

    def test_flag_off_is_inert(self, reporter):
        """开关关闭 → 登记函数不被调用。"""
        pipeline_data: dict = {"risk_metrics": {"max_drawdown_pct": -0.1}}

        with (
            _patch_active("signal_ledger", False),
            patch("src.python.report.signal_record.register_deterministic_signals") as register,
        ):
            seams.record_deterministic_signals(pipeline_data, _PREP, reporter)

        register.assert_not_called()
        assert reporter.messages == []

    def test_flag_on_registers_signals(self, reporter):
        """开关开启 → 登记确定性评级并上报条数。"""
        pipeline_data: dict = {"risk_metrics": {"max_drawdown_pct": -0.1}}

        with (
            _patch_active("signal_ledger", True),
            patch(
                "src.python.report.signal_record.register_deterministic_signals",
                return_value={"registered": 5},
            ) as register,
        ):
            seams.record_deterministic_signals(pipeline_data, _PREP, reporter)

        assert register.call_args.args[0] is pipeline_data
        assert register.call_args.kwargs["report_date"] == "2026-09-10"
        ok_messages = [msg for level, msg in reporter.messages if level == "ok"]
        assert any("登记 5 条确定性评级" in msg for msg in ok_messages)

    def test_downstream_exception_warns_only(self, reporter):
        """下游异常 → 只告警，不外抛。"""
        with (
            _patch_active("signal_ledger", True),
            patch(
                "src.python.report.signal_record.register_deterministic_signals",
                side_effect=RuntimeError("boom"),
            ),
        ):
            seams.record_deterministic_signals({}, _PREP, reporter)

        assert len(reporter.warns()) == 1
        assert "确定性信号沉淀" in reporter.warns()[0]


# ── 接线守卫 ─────────────────────────────────────────────────


class TestFacadeWiringOrder:
    """挂载点接线守卫 —— 四个挂载点被调用，且相对次序与顺序约束一致。"""

    def _seam_call_order(self) -> list[str]:
        source = (Path(PROJECT_ROOT) / "src" / "python" / "report" / "_report_generation.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        fn = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_generate_report_full"
        )
        calls = [
            (node.lineno, node.func.id)
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SEAM_ORDER
        ]
        calls.sort()
        return [name for _, name in calls]

    def test_all_seams_wired_in_documented_order(self):
        """四个挂载点均已接线，且次序满足「结算先于 LLM 拉取」等三条顺序约束。"""
        assert self._seam_call_order() == _SEAM_ORDER

    def test_functional_submodules_are_imported_lazily(self):
        """report 功能子模块一律按需导入 —— 开关关闭时不付出导入成本。

        例外仅 ``report.progress``（``ProgressReporter`` 接口，供模块级类型标注）。
        """
        source = Path(seams.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        eagerly_imported = {
            node.module.split(".")[-1]
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("src.python.report.")
        }
        assert eagerly_imported == {"progress"}

    def test_top_level_project_imports_are_exactly_documented_set(self):
        """顶层 ``src.python.*`` 导入集合恰为文档声明的白名单。

        上一个用例只筛 ``src.python.report.`` 前缀，core 前缀的急切导入不入其视野
        ——守卫留有盲区时，「零导入成本」的文档承诺可被悄悄推翻而不转红。本用例改
        为枚举**全部**顶层项目内导入，双方任一漂移（新增急切导入，或注释声明的例外
        名被改动）都会失败。
        """
        source = Path(seams.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        eager_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("src.python.")
        }
        assert eager_modules == {"src.python.core", "src.python.report.progress"}
        core_symbols = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "src.python.core"
            for alias in node.names
        }
        assert core_symbols == {"decision_ledger", "signal_ledger"}
