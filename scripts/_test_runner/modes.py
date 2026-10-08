"""测试模式注册表与模式解析（MODES / 基准模式 / 文档表序 / 帮助文本）。"""

from __future__ import annotations

import sys
from collections.abc import Callable, Collection


MODES: dict[str, dict] = {
    "unit": {
        "marker": "unit",
        "desc": "全量单元测试（含 edge/data）",
        "timeout_sec": 720,
        "order": 1,
        "parallel": True,
    },
    "standard": {
        "marker": "unit and not (edge or data)",
        "desc": "常规单元测试（排除 edge/data 标记）",
        "timeout_sec": 720,
        "order": 2,
        "parallel": True,
    },
    "scenario": {
        "marker": "scenario",
        "desc": "业务场景集成测试（S0-S33 + T1-T21）",
        "timeout_sec": 600,
        "order": 3,
        "parallel": False,
    },
    "regression": {
        "marker": "scenario",
        "desc": "回归测试（场景模式，提交前快速验证）",
        "timeout_sec": 1200,
        "order": 4,
        "parallel": False,
    },
    "dev-verify": {
        "desc": "开发期快速验证（core/providers/fetcher/analysis/report 单元 + 基础场景；耗时参考 docs/managements/test-coverage.md 环境耗时对照）",
        "order": 5,
        # 预检只留 <100ms 的编号快检（fail-fast）；重量守护（check-doc-drift /
        # check-test-redundancy）不入预检——它们由 pre-commit 钩子对同一待提交树
        # 唯一执行、CI guards job 全量兜底，入预检会造成同树重复调用。
        "preflight": [
            [sys.executable, "scripts/check-task-numbering.py", "--ci"],
        ],
        # 双阶段合一：原「核心单元 ∪ 基础场景」两轮 pytest 收敛为单轮（并集 marker），
        # 省一整轮全量收集 + worker 启动 + conftest 装配；合并前后 --collect-only 对拍
        # 用例集合精确一致（零重叠零遗漏）。timeout = 原两阶段 300s×2 预算总和不变。
        "phases": [
            {
                "marker": "((unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts or unit_web or unit_report) and not (edge or data)) or scenario_basic",
                "desc": "核心模块单元 + 基础业务场景（单轮；耗时参考 docs/managements/test-coverage.md 环境耗时对照）",
                "timeout_sec": 600,
                "parallel": True,
            },
        ],
    },
    "verify": {
        "marker": "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web or unit_report",
        "desc": "合入验证（核心/配置/新闻/LLM/报告模块单元测试，不含场景——场景由 P0+P2 覆盖）",
        "timeout_sec": 300,
        "order": 6,
        "parallel": True,
    },
    "integration": {
        "marker": "scenario or integration",
        "desc": "集成测试（场景+模块契约/缓存/TUI 路由）",
        "timeout_sec": 600,
        "order": 7,
        "parallel": True,
    },
    "edge": {
        "marker": "edge",
        "desc": "边缘/异常场景测试",
        "timeout_sec": 600,
        "order": 8,
        "parallel": False,
    },
    "data": {
        "marker": "data",
        "desc": "数据正确性验证测试",
        "timeout_sec": 120,
        "order": 9,
        "parallel": False,
    },
    "all": {
        "marker": "",
        "desc": "全量测试",
        "timeout_sec": 1200,
        "order": 10,
        "parallel": True,
    },
    "all_no_unit": {
        "marker": "not unit and not live",
        "desc": "全量测试（排除单元测试）",
        "timeout_sec": 1200,
        "order": 10,
        "parallel": True,
    },
    "smoke": {
        "marker": "smoke",
        "desc": "冒烟测试（快速验证核心通路；耗时参考 docs/managements/test-coverage.md 环境耗时对照）",
        "timeout_sec": 60,
        "order": 11,
        "parallel": False,
    },
    "report": {
        "marker": "unit_report",
        "desc": "仅报告模块测试（开发期快速验证报告变更）",
        "timeout_sec": 600,
        "order": 12,
        "parallel": True,
    },
    "scenario_extreme": {
        "marker": "scenario_extreme",
        "desc": "极限场景测试（S0c 超多持仓 + S10 极端值，手工触发；耗时参考 docs/managements/test-coverage.md 环境耗时对照）",
        "timeout_sec": 600,
        "order": 13,
        "parallel": False,
    },
    "perf": {
        "marker": "scenario_perf",
        "desc": "端到端性能基准（scenario_perf 独立标记，手工/发布前运行；不入门禁、不进 bench）",
        "timeout_sec": 600,
        "order": 14,
        "parallel": False,
    },
    "security": {
        "marker": "scenario_security",
        "desc": "安全基线测试（scenario_security 独立标记，手工/发布前运行；不入门禁、不进 bench）",
        "timeout_sec": 600,
        "order": 15,
        "parallel": False,
    },
    "live": {
        "marker": "live",
        "desc": "真实网络验证套件（opt-in，仅 `--mode live` 手工运行；不入门禁）",
        "timeout_sec": 300,
        "order": 16,
        "parallel": False,
    },
}


def mode_marker_expr(mode: str) -> str:
    """模式的 pytest `-m` 表达式（顶层 ``marker`` 缺省时回落到首个阶段的 marker）。

    多阶段合一后（``phases``），首阶段 marker 就是该模式实际的过滤条件；
    空字符串表示不过滤（与 ``pytest_env``「空 marker 不传 ``-m``」同一口径）。

    Args:
        mode: ``MODES`` 中的模式名

    Returns:
        marker 表达式；模式既无 ``marker`` 也无 ``phases`` 时为空字符串

    Raises:
        KeyError: 模式名不在 ``MODES`` 中
    """
    cfg = MODES[mode]
    if "marker" in cfg:
        return str(cfg["marker"])
    phases = cfg.get("phases") or []
    return str(phases[0].get("marker", "")) if phases else ""


def compile_marker_expr(expr: str) -> Callable[[Collection[str]], bool]:
    """把 pytest `-m` 表达式编译成「对 marker 名集合」的谓词。

    复用 pytest 自带的表达式求值器（``_pytest.mark.expression``，即 ``-m``
    过滤走的同一实现），使「收集侧按集合计数」与「test-runner 按 ``-m``
    实跑」两侧共用一份语义——表达式本身只在 ``MODES`` 定义一处，其它地方
    （如 ``collect-test-coverage.py``）一律由本函数现场编译，不再抄写。

    Args:
        expr: pytest `-m` 布尔表达式（``and`` / ``or`` / ``not`` / 括号 / 标识符）

    Returns:
        谓词：输入已收集项的 marker 名集合，返回是否命中该表达式；空表达式恒真

    Raises:
        SyntaxError: 表达式语法错误（编译期即暴露，不带病进入计数）
    """
    if not expr.strip():
        return lambda _markers: True
    from _pytest.mark.expression import Expression  # 延迟导入：仅计数/收集路径付费

    compiled = Expression.compile(expr)

    def matches(markers: Collection[str]) -> bool:
        names = frozenset(markers)
        return bool(compiled.evaluate(lambda name, /, **kwargs: name in names))

    return matches


_HELP_TEXT = """测试驱动脚本 — 统一运行 pytest 并输出结构化 HTML 报告。

用法:
  python scripts/test-runner.py                          # 全量测试
  python scripts/test-runner.py --mode unit              # 仅单元测试
  python scripts/test-runner.py --mode edge              # 仅边缘测试
  python scripts/test-runner.py --mode scenario,edge     # 多模式组合
  python scripts/test-runner.py --coverage               # 全量 + 覆盖率报告
  python scripts/test-runner.py --mode bench --machine-info  # 跨机器耗时采集（环境 + 各模式实测表格）
  python scripts/test-runner.py --mode bench --update-docs   # 采集并自动回填环境耗时对照表
  python scripts/test-runner.py --help                   # 本帮助

模式说明:
"""


_MODE_TABLE_ORDER: tuple[str, ...] = (
    "unit",
    "standard",
    "scenario",
    "regression",
    "dev-verify",
    "verify",
    "integration",
    "edge",
    "data",
    "all",
    "smoke",
    "report",
    "all_no_unit",
    "scenario_extreme",
)


_BENCH_MODES: tuple[str, ...] = tuple(m for m in _MODE_TABLE_ORDER if m != "all") + ("all",)


def _resolve_modes(modes_to_run: list[str]) -> list[str]:
    """展开模式列表：将 bench 别名替换为基准模式序列，按首次出现去重保序。

    Args:
        modes_to_run: 用户输入的模式列表（可含 bench）

    Returns:
        展开去重后的模式列表（仅含 MODES 键）
    """
    seen: set[str] = set()
    resolved: list[str] = []
    for mode in modes_to_run:
        candidates = list(_BENCH_MODES) if mode == "bench" else [mode]
        for cand in candidates:
            if cand not in seen:
                seen.add(cand)
                resolved.append(cand)
    return resolved
