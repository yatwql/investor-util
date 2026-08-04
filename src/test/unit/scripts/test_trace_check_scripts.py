"""测试：历史痕迹检查脚本 — check-code-traces.py / check-doc-traces.py

覆盖：
  - 工具自身豁免（_is_tool_self 模式识别，重命名/新增同类工具不失效）
  - 补强模式能检出真实历史痕迹（此前/曾经/原始/历史实现/旧逻辑/迁移到新/重构前）
  - 合法运行时/当前状态描述不被误伤（历史数据/当前版本/此前已配置/之前缓存过）
  - 文档「工具说明」元描述行豁免
  - 测试文件回归场景元描述豁免（仅 src/test/：旧实现/修复前/回归场景/rf-xxx 批次修复）
  - 版本号/任务编号等既有模式仍工作

测试通过脚本 import 方式直接复用 PATTERNS / EXCLUDE_LINE / 各扫描函数，
不运行真实 CLI（避免扫描全仓、受控制台 GBK 编码影响）。
"""

from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # D:/codebase/zoo/investor-util
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的检查脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def code_traces():
    return _load_script("check-code-traces.py")


@pytest.fixture(scope="module")
def doc_traces():
    return _load_script("check-doc-traces.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


def _code_hit(mod, line: str) -> str | None:
    """返回 check-code-traces 命中的 desc；未命中返回 None。"""
    if mod._is_excluded(line):
        return None
    for pat, cat, desc in mod.PATTERNS:
        if __import__("re").search(pat, line):
            return desc
    return None


def _doc_hit(mod, line: str) -> str | None:
    """返回 check-doc-traces 命中的 desc；未命中返回 None。

    对 CHAPTER（章节编号）模式先应用 _is_chapter_excluded 计数/序数豁免，
    与 scan_file 行为一致（"共 19 章"等计数表述不误报）。
    """
    if mod._is_excluded(line):
        return None
    for pat, cat, desc in mod._DOC_PATTERNS:
        if cat == "CHAPTER" and mod._is_chapter_excluded(line):
            continue
        if __import__("re").search(pat, line):
            return desc
    return None


# ── 工具自身豁免 ─────────────────────────────────────────────


class TestToolSelfExemption:
    def test_recognizes_self(self, code_traces):
        assert code_traces._is_tool_self("check-code-traces.py") is True
        assert code_traces._is_tool_self("check-doc-traces.py") is True

    def test_recognizes_future_sibling(self, code_traces):
        """未来新增同类工具（check-xml-traces.py）自动豁免，无需改豁免列表。"""
        assert code_traces._is_tool_self("check-xml-traces.py") is True

    def test_does_not_exempt_other_scripts(self, code_traces):
        assert code_traces._is_tool_self("test_runner.py") is False
        assert code_traces._is_tool_self("check-version-consistency.py") is False
        assert code_traces._is_tool_self("chart.min.js") is False


# ── check-code-traces：补强模式能检出历史痕迹 ──────────────


class TestCodeTraceDetection:
    """补强后 check-code-traces 应能检出此前/曾经/原始/历史/旧逻辑/迁移等痕迹。"""

    def test_prior_state_narrative(self, code_traces):
        assert _code_hit(code_traces, "之前是直接读取文件") is not None

    def test_prior_noun(self, code_traces):
        assert _code_hit(code_traces, "此前的判断逻辑") is not None
        assert _code_hit(code_traces, "以前的实现方案") is not None

    def test_once_implemented(self, code_traces):
        assert _code_hit(code_traces, "曾经的实现逻辑") is not None

    def test_considered_alternative(self, code_traces):
        assert _code_hit(code_traces, "曾考虑过A方案") is not None

    def test_original_version(self, code_traces):
        assert _code_hit(code_traces, "原始版本") is not None

    def test_historical_implementation(self, code_traces):
        assert _code_hit(code_traces, "历史实现") is not None

    def test_old_logic(self, code_traces):
        assert _code_hit(code_traces, "旧逻辑") is not None

    def test_refactored_before(self, code_traces):
        assert _code_hit(code_traces, "重构前逻辑") is not None

    def test_migrated_to_new(self, code_traces):
        assert _code_hit(code_traces, "迁移到新模块") is not None

    def test_replaced_old(self, code_traces):
        assert _code_hit(code_traces, "替代了旧方案") is not None

    # ── 合法运行时/当前状态描述不应误伤 ──

    def test_runtime_descriptions_not_flagged(self, code_traces):
        legit = [
            "当前版本为 1.0",
            "保留了历史数据",
            "该字段为历史值",
            "回测使用历史序列",
            "此前已配置",
            "之前缓存过",
            "回退到默认配置",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法描述被误伤: {line}"

    # ── 既有模式仍工作 ──

    def test_version_marker(self, code_traces):
        assert _code_hit(code_traces, "该功能在 v0.9.9 引入") is not None

    def test_task_id(self, code_traces):
        assert _code_hit(code_traces, "见 rf-117 修复") is not None

    def test_source_narrative(self, code_traces):
        assert _code_hit(code_traces, "从 utils.py 拆分而来") is not None


# ── 测试文件回归场景元描述豁免（仅 src/test/ 生效） ─────────


class TestTestFileMetaExemption:
    """回归测试 docstring/注释描述"旧实现做错什么、修复后如何"属测试元数据，
    test_file=True 时豁免；非测试文件（test_file=False）不受影响仍检出。"""

    def test_regression_scene_exempted_in_test_file(self, code_traces):
        """含"回归场景/回归断言/回归："的回归测试说明行应豁免。"""
        legit = [
            "回归场景：建设银行'今日下跌3.41%'曾被误修正为 1.9%（误当收益率）。",
            "回归断言 1.9 → 187.1（而非旧实现把 3.41/4.43 修正成 1.9）。",
            "# ── 回归：百分单位契约 + 单日涨跌语境 + 表格行归因（rf-159 批次修复） ──",
        ]
        for line in legit:
            assert code_traces._is_excluded(line, test_file=True) is True, f"回归元描述未豁免: {line}"

    def test_old_behavior_narrative_exempted_in_test_file(self, code_traces):
        """测试注释描述旧实现错误行为（旧实现+误/把/会）应豁免。"""
        legit = [
            "旧实现'整句最近'误归因到 016055",
            "旧实现会误报'016055 为最大持仓'",
            "修复后 orchestrator 源头 ×100、单日涨跌语境按 change_pct 校验。",
        ]
        for line in legit:
            assert code_traces._is_excluded(line, test_file=True) is True, f"旧行为描述未豁免: {line}"

    def test_rf_task_id_batch_note_exempted_in_test_file(self, code_traces):
        """引用历史任务编号的修复批次说明（rf-xxx 批次修复）在测试文件应豁免。"""
        assert code_traces._is_excluded("表格行归因（rf-159 批次修复）", test_file=True) is True
        assert code_traces._is_excluded("表格行归因（rf-159 批次修复）", test_file=False) is False

    def test_not_exempted_outside_test_file(self, code_traces):
        """同样的旧实现叙述在非测试文件（test_file=False）仍应被检出——工具应检出此历史痕迹，源码侧不削弱。"""
        assert code_traces._is_excluded("旧实现把 3.41/4.43 修正成 1.9", test_file=False) is False
        assert _code_hit(code_traces, "旧实现把 3.41/4.43 修正成 1.9") is not None


# ── check-doc-traces：补强模式能检出文档历史痕迹 ───────────


class TestDocTraceDetection:
    def test_prior_state_narrative(self, doc_traces):
        assert _doc_hit(doc_traces, "之前是直接读取文件") is not None

    def test_prior_noun(self, doc_traces):
        assert _doc_hit(doc_traces, "此前的判断逻辑") is not None
        assert _doc_hit(doc_traces, "以前的实现方案") is not None

    def test_once_implemented(self, doc_traces):
        assert _doc_hit(doc_traces, "曾经的实现逻辑") is not None

    def test_original_version(self, doc_traces):
        assert _doc_hit(doc_traces, "原始版本") is not None

    def test_historical_implementation(self, doc_traces):
        assert _doc_hit(doc_traces, "历史实现") is not None

    def test_old_logic(self, doc_traces):
        assert _doc_hit(doc_traces, "旧逻辑") is not None

    def test_migrated_to_new(self, doc_traces):
        assert _doc_hit(doc_traces, "迁移到新模块") is not None

    def test_refactored_before(self, doc_traces):
        assert _doc_hit(doc_traces, "重构前逻辑") is not None

    def test_replaced_old(self, doc_traces):
        assert _doc_hit(doc_traces, "替代了旧方案") is not None

    def test_considered_alternative(self, doc_traces):
        assert _doc_hit(doc_traces, "曾考虑过A方案") is not None

    # ── 合法当前状态/工具说明应豁免 ──

    def test_runtime_descriptions_not_flagged(self, doc_traces):
        legit = [
            "当前版本为 1.0",
            "保留了历史数据",
            "回测使用历史序列",
            "此前已配置",
            "之前缓存过",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"合法描述被误伤: {line}"

    def test_tool_description_exempted(self, doc_traces):
        """描述"检查哪些历史痕迹"的工具说明行（元描述）应豁免，而非视为痕迹。"""
        legit = [
            "检查历史痕迹的规则说明",
            "文档正文不得带历史痕迹，只反映当前状态",
            "文档不得包含来源叙述、原/旧实现、迁移/重命名",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"工具说明被误伤: {line}"

    def test_version_header_exempted(self, doc_traces):
        """文档版本头（行首锚定）应豁免。"""
        assert doc_traces._is_excluded("> 文档版本：0.9.10-dev") is True
        assert doc_traces._is_excluded("## 文档版本：v0.9.10") is True

    # ── 既有模式仍工作 ──

    def test_archive_reference(self, doc_traces):
        assert _doc_hit(doc_traces, "见 docs-stm/archive/ 归档") is not None

    def test_task_id(self, doc_traces):
        assert _doc_hit(doc_traces, "见 rf-117 修复") is not None

    def test_series_alias(self, doc_traces):
        assert _doc_hit(doc_traces, "G系列 方案") is not None
        assert _doc_hit(doc_traces, "b_series 说明") is not None

    def test_legit_letter_digit_not_flagged(self, doc_traces):
        assert _doc_hit(doc_traces, "全系列报告") is None
        assert _doc_hit(doc_traces, "C20 约束") is None


# ── check-doc-traces：章节编号暗号检测（CHAPTER） ───────────


class TestDocChapterDetection:
    """正文用数字章节号（"N 章"/"第 N 章"）指代报告具体章节须检出（可读性暗号，
    须改用语义章节名「X」章）；章节数量/序数表述（共 N 章 / N 章基线 / 减至
    N 章 / 出现第 N 章 / N→M 章 / 引号内"N 章"）是合法计数，豁免。"""

    def test_chapter_codes_flagged(self, doc_traces):
        flagged = [
            "改造 5 章",
            "合并 9 章",
            "9章加X",
            "第 5 章加估值分位",
            "输出到 20 章行动建议",
            "14 章摘要引用",
            "1/2/3 章渲染",
            "4 章估值分位",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"章节编号暗号未检出: {line}"

    def test_chapter_count_exempted(self, doc_traces):
        legit = [
            "共 19 章",
            "目标 19 章",
            "合并后 18 章基线",
            "总数 21 章减至 19 章",
            "减至 19 章",
            "20→19 章",
            "「19 章」",
            "开启才出现第 19 章",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"章节计数表述被误伤: {line}"

    def test_non_patterns_clean(self, doc_traces):
        legit = [
            "一章三区块",
            "4.2 章节归并对照表",
            "19 个章节",
            "章节",
            "21 轮每轮量化验收",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"合法表述被误伤: {line}"


# ── 注释提取：多行 docstring 状态不泄漏 ─────────────────────


class TestCommentExtraction:
    """_py_comment_lines 对多行 docstring 的 in_docstring 状态必须正确开关，
    否则 docstring 后的 assert/代码行会被误当作 docstring 提取（泄漏误报）。"""

    def test_triple_quote_close_line_with_trailing_text(self, code_traces):
        """内容结尾的关闭三引号行（…内容\"\"\"，不以三引号开头）应识别为仅关闭行。"""
        is_oc, is_open = code_traces._is_triple_quote_line('test_file=True 时豁免；不受影响仍检出。"""')
        assert (is_oc, is_open) == (False, True)

    def test_close_line_with_trailing_text_no_leak(self, code_traces):
        """关闭行含内容（…内容\"\"\"）时正确关闭，docstring 后的 assert 不泄漏。"""
        sample = 'x = 1\n"""这是说明，\n第二行内容。"""\nassert _doc_hit(doc_traces, "此前直接读取文件") is not None\n'
        extracted = [txt for _, txt in code_traces._py_comment_lines(sample)]
        assert "此前直接读取文件" not in "".join(extracted), "docstring 状态泄漏到 assert 行"

    def test_plain_close_line_no_leak(self, code_traces):
        """单独一行的关闭三引号（\"\"\"）正常关闭，后续代码不泄漏。"""
        sample = (
            '"""回归场景：旧实现把 3.41/4.43 修正成 1.9（描述被测行为）。\n'
            "这是 docstring 第二行。\n"
            '"""\n'
            'assert _doc_hit(doc_traces, "历史实现") is not None\n'
        )
        extracted = [txt for _, txt in code_traces._py_comment_lines(sample)]
        assert '历史实现" is not None' not in "".join(extracted), "docstring 状态泄漏到 assert 行"


# ── check-code-traces：任务编号标识符/注释检查 ─────────────


def _ident_hit(code_traces, source: str) -> str | None:
    """返回 _scan_identifiers 对临时 .py 代码片段的命中 desc；未命中返回 None。

    每次调用生成唯一临时文件，避免并行 worker 写同一路径冲突。
    """
    fd, path = tempfile.mkstemp(suffix=".py", prefix="trace_ident_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    try:
        hits = code_traces._scan_identifiers(Path(path))
        return hits[0][2] if hits else None
    finally:
        os.remove(path)


class TestTaskCodeCommentPatterns:
    """注释 CODE 模式应检出任务编号/系列代号，不误伤合法字母+数字引用。"""

    def test_series_alias_english(self, code_traces):
        assert _code_hit(code_traces, "b_series 说明") is not None

    def test_series_alias_chinese(self, code_traces):
        assert _code_hit(code_traces, "G系列 方案") is not None
        assert _code_hit(code_traces, "B系列 批次") is not None

    def test_existing_task_id_patterns_still_work(self, code_traces):
        assert _code_hit(code_traces, "见 rf-117 修复") is not None
        assert _code_hit(code_traces, "plan-18 任务") is not None

    def test_legit_series_words_not_flagged(self, code_traces):
        legit = [
            "drawdown_series 列表",
            "holding_series",
            "全系列报告",
            "中证指数系列",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法系列词被误伤: {line}"

    def test_legit_letter_digit_not_flagged(self, code_traces):
        legit = [
            "C20 约束",
            "P1 优先级",
            "S-P1 场景",
            "f9=市盈率",
            "合并 A1:B1",
            "数据在 B2~B5",
            "R17 兼容",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法字母+数字被误伤: {line}"


class TestTaskCodeIdentifierCheck:
    """代码标识符不得使用任务编号/系列代号（IDENT 扫描）。"""

    def test_task_code_identifiers_flagged(self, code_traces):
        flagged = [
            "F4 = 1",
            "b_series = []",
            "G系列 = 1",
            "rf_205_fix = 1",
            "plan18_hack = 1",
            "def rf_100_helper():\n    pass",
        ]
        for src in flagged:
            assert _ident_hit(code_traces, src) is not None, f"应命中: {src}"

    def test_legit_short_locals_not_flagged(self, code_traces):
        legit = [
            "h1 = 1",
            "f1 = 1",
            "x0 = 0.0",
            "p50 = 1",
            "drawdown_series = []",
            "def test_provider(x1, y1):\n    pass",
        ]
        for src in legit:
            assert _ident_hit(code_traces, src) is None, f"不应命中: {src}"


class TestIdentifierExtraction:
    """_iter_identifiers 应从代码中提取到预期标识符名。"""

    def test_py_ast_extracts_names(self, code_traces):
        src = (
            "import math as m\n"
            "class PortfolioModel:\n"
            "    def compute(self, data):\n"
            "        result = data + 1\n"
            "        return result\n"
        )
        names = {n for _, n in code_traces._py_identifier_names(ast.parse(src))}
        assert {"PortfolioModel", "compute", "data", "result", "m"} <= names

    def test_js_decl_extracts_names(self, code_traces):
        src = "var B6 = 1;\nconst chart = new Chart();\nfunction draw() {}\n"
        names = sorted(n for _, n in code_traces._js_identifier_names(src))
        assert "B6" in names
        assert "chart" in names
        assert "draw" in names
