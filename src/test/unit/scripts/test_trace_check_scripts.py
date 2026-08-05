"""测试：历史痕迹检查脚本 — check-code-traces.py / check-doc-traces.py

覆盖：
  - 工具自身豁免（_is_tool_self 模式识别，重命名/新增同类工具不失效）
  - 补强模式能检出真实历史痕迹（此前/曾经/原始/历史实现/旧逻辑/迁移到新/重构前）
  - 合法运行时/当前状态描述不被误伤（历史数据/当前版本/此前已配置/之前缓存过）
  - 文档「工具说明」元描述行豁免
  - 测试文件回归场景元描述豁免（仅 src/test/：旧实现/修复前/回归场景/rf-xxx 批次修复）
  - 版本号/任务编号等既有模式仍工作
  - 章节编号暗号（"N 章"/"第 N 章"指代报告具体章节）检出，计数表述（共 N 章等）豁免
  - 迭代轮次暗号（"第 N 轮"/"轮N"指代开发迭代轮次）检出，计数/运行时表述（共 N 轮/
    轮询/轮动等）豁免
  - 架构约束代号（C1~C20，technical.md 定义）在注释/文档正文属暗号须检出；约束定义处
    （technical.md / llm-technical.md）豁免；非约束 C+数字（色值 C00000、C21+、内嵌
    AB14/MC19）不误伤

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

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录（src/test/unit/scripts 向上 4 级）
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
    """返回 check-code-traces 命中的 desc；未命中返回 None。

    与 scan_file 行为一致：对 CHAPTER/ROUND 应用计数/序数豁免，
    对 DASHTASK/UNDERSCORE 应用合法领域值豁免，对 MAGIC 逐 token 应用
    合法领域值豁免（"共 19 章"/"T-1 交易日"/"S1 场景"等合法表述不误报）。
    """
    if mod._is_excluded(line):
        return None
    for pat, cat, desc in mod.PATTERNS:
        if cat == "CHAPTER" and mod._is_chapter_excluded(line):
            continue
        if cat == "ROUND" and mod._is_round_excluded(line):
            continue
        if cat == "DASHTASK" and mod._is_dash_excluded(line):
            continue
        if cat == "UNDERSCORE" and mod._is_under_excluded(line):
            continue
        if cat == "MAGIC":
            for m in __import__("re").finditer(pat, line):
                if not mod._is_magic_match_excluded(line, m.start(), m.end()):
                    return desc
            continue
        if __import__("re").search(pat, line):
            return desc
    return None


def _doc_hit(mod, line: str) -> str | None:
    """返回 check-doc-traces 命中的 desc；未命中返回 None。

    对 CHAPTER（章节编号）模式先应用 _is_chapter_excluded 计数/序数豁免，
    对 ROUND（迭代轮次）模式先应用 _is_round_excluded 计数/运行时豁免，
    与 scan_file 行为一致（"共 19 章"/"共 12 轮"等计数表述不误报）。
    """
    if mod._is_excluded(line):
        return None
    for pat, cat, desc in mod._DOC_PATTERNS:
        if cat == "CHAPTER" and mod._is_chapter_excluded(line):
            continue
        if cat == "ROUND" and mod._is_round_excluded(line):
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

    def test_self_file_scan_clean(self, code_traces):
        """工具自身文件（含新增强模式特征字面量——合并历史与中文数字章节/轮次字样）应
        整文件豁免——扫描 check-code-traces.py 自身不命中任何痕迹，防模式增强自伤。"""
        hits = code_traces.scan_file(Path(code_traces.__file__), verbose=False)
        assert hits == [], f"工具自身文件应豁免，实际命中: {hits}"


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

    def test_original_contract_migration_flagged(self, code_traces):
        """契约改名叙述（历史主键名变迁）须检出，当前只描述 style_factor_data。"""
        flagged = [
            "原 factor_exposure 契约迁移为主键",
            "原 factor_exposure 迁移为 style_factor_data 主键",
            "原 factor_exposure dict 迁移为 style_factor_data 主键",
            "原 contract_a 改称 contract_b",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"契约改名叙述未检出: {line}"

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
            "原始数据迁移至新库是运行时功能",
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

    def test_original_contract_migration_flagged(self, doc_traces):
        """文档正文契约改名叙述（历史主键名变迁）须检出。"""
        flagged = [
            "原 factor_exposure 契约迁移为主键",
            "原 factor_exposure 迁移为 style_factor_data 主键",
            "原 factor_exposure dict 迁移为 style_factor_data 主键",
            "原 contract_a 改称 contract_b",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"契约改名叙述未检出: {line}"

    # ── 合法当前状态/工具说明应豁免 ──

    def test_runtime_descriptions_not_flagged(self, doc_traces):
        legit = [
            "当前版本为 1.0",
            "保留了历史数据",
            "回测使用历史序列",
            "此前已配置",
            "之前缓存过",
            "原始数据迁移至新库是运行时功能",
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
        assert _doc_hit(doc_traces, "P1 优先级") is None
        assert _doc_hit(doc_traces, "R17 兼容") is None

    def test_arch_constraint_cipher_flagged(self, doc_traces):
        """文档正文架构约束代号（C1~C20）属暗号须检出（须改写为语义描述）。"""
        flagged = [
            "C19 契约",
            "C20 图下说明",
            "C1 约束：代码类型判定复用 code_utils",
            "C14 合规，不写 _ENV.globals",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"架构约束代号未检出: {line}"

    def test_arch_constraint_cipher_false_positives(self, doc_traces):
        """非约束的 C+数字组合不得误伤：十六进制色值、C21+、内嵌命中。"""
        legit = [
            "色值 C00000 不随版本变",
            "C21 方案不在约束表",
            "AB14 协议对接",
            "MC19 型号",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"非约束 C+数字被误伤: {line}"


class TestDocCipherExemptFiles:
    """架构约束代号豁免文件：约束定义处（technical.md / llm-technical.md）
    正文大量引用 C1~C20（技术名称表）属定义载体，豁免；其余文档（含
    trace-exempt 的计划/变更记录文档）正文一律禁。"""

    def _scan(self, doc_traces, name: str, content: str, chapter_only: bool) -> list:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fpath = Path(tmp) / name
            fpath.write_text(content, encoding="utf-8")
            return doc_traces.scan_file(fpath, verbose=False, chapter_only=chapter_only)

    def _cipher_hits(self, doc_traces, name: str, content: str, chapter_only: bool) -> list:
        return [
            h for h in self._scan(doc_traces, name, content, chapter_only)
            if h[1] == "CIPHER"
        ]

    def test_regular_doc_flagged_both_modes(self, doc_traces):
        """普通文档（含 trace-exempt 的计划/变更记录）正文出现 C1~C20 一律检出。"""
        content = "C19 契约注入 pipeline_data\n"
        for chapter_only in (False, True):
            hits = self._cipher_hits(doc_traces, "other.md", content, chapter_only)
            assert len(hits) == 1, f"chapter_only={chapter_only} 应检出 CIPHER: {hits}"

    def test_technical_md_exempt_both_modes(self, doc_traces):
        """technical.md（约束定义处）正文引用 C1~C20 属定义载体，豁免。"""
        content = "C19 契约 / C20 图下说明 / C1 约束\n"
        for chapter_only in (False, True):
            hits = self._cipher_hits(doc_traces, "technical.md", content, chapter_only)
            assert hits == [], f"chapter_only={chapter_only} technical.md 应豁免: {hits}"

    def test_llm_technical_md_exempt(self, doc_traces):
        """llm-technical.md（约束定义处）同样豁免。"""
        content = "C17 约束 / C4 约束\n"
        hits = self._cipher_hits(doc_traces, "llm-technical.md", content, chapter_only=False)
        assert hits == [], f"llm-technical.md 应豁免: {hits}"


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

    def test_chapter_codes_chinese_flagged(self, doc_traces):
        """中文数字章节编号（第X章 / 裸X章式）指代报告具体章节须检出。"""
        flagged = [
            "三章渲染成本分档",
            "第五章估值分位",
            "第二章合并",
            "第四章摘要引用",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"中文数字章节暗号未检出: {line}"

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

    def test_chapter_count_chinese_exempted(self, doc_traces):
        """中文数字计数表述（共X章 / 减至X章 / 一章三区块式计数）应豁免。"""
        legit = [
            "共 二十 章",
            "总数 二十一章 减至 十九章",
            "减至 十九章",
            "「十九章」",
            "一章三区块",
            "一章两区块",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"中文数字章节计数表述被误伤: {line}"

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


# ── check-doc-traces：迭代轮次暗号检测（ROUND） ────────────


class TestDocRoundDetection:
    """正文用数字轮次（"第 N 轮"/"经 N 轮"/"N 轮"/"轮 N"）指代开发迭代历史须检出
    （迭代轮次是开发痕迹，正文须改用语义描述）；轮次数量/运行时表述（共 N 轮 /
    N 轮每轮 / 计划分 N 轮 / 轮询 / 轮动 / 第 N 轮循环）是合法计数或业务/运行时
    概念，豁免。changelog/plan/review-findings 与 docs-stm/plan/ 不查本条
    （ROUND 不进 _CHAPTER_PATTERNS，trace-exempt 文档仅章节编号扫描）。"""

    def test_round_codes_flagged(self, doc_traces):
        flagged = [
            "第 14 轮",
            "第4轮",
            "经 8 轮",
            "轮 8",
            "12 轮迭代",
            "轮13 验收标准",
            "对应轮4/轮5",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"迭代轮次暗号未检出: {line}"

    def test_round_codes_chinese_flagged(self, doc_traces):
        """中文数字迭代轮次（第 X 轮式——X 为中文数字三及以上；及"轮 X"式）指代
        开发迭代历史须检出；唯第一轮/第二轮为运行时序数（LLM 圆桌会两轮辩论等），
        不纳入。"""
        flagged = [
            "第三轮落地",
            "第 三 轮验收标准",
            "轮三 落地",
            "对应轮四/轮五",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"中文数字轮次暗号未检出: {line}"

    def test_round_count_exempted(self, doc_traces):
        legit = [
            "共 12 轮",
            "目标 8 轮",
            "21 轮每轮量化验收",
            "计划分 5 轮推进",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"轮次计数表述被误伤: {line}"

    def test_round_runtime_exempted(self, doc_traces):
        legit = [
            "轮询超时重试",
            "第 3 轮循环",
            "行业轮动判断",
            "轮换到下一品种",
            "板块轮涨轮跌",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"轮次运行时表述被误伤: {line}"

    def test_round_runtime_chinese_exempted(self, doc_traces):
        """中文数字运行时序数/计数表述应豁免：LLM 圆桌会两轮辩论、第一轮/第二轮
        增量抓取等为正常行为，非开发迭代痕迹。"""
        legit = [
            "第一轮增量获取",
            "第二轮互相反驳聚焦调仓",
            "圆桌会两轮辩论",
            "共 二十 轮迭代实施",
            "一轮行情",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"中文数字轮次运行时表述被误伤: {line}"

    def test_round_non_patterns_clean(self, doc_traces):
        legit = [
            "一轮行情",
            "每轮循环",
            "本轮上涨",
            "首轮筛选",
            "两个回合",
        ]
        for line in legit:
            assert _doc_hit(doc_traces, line) is None, f"合法表述被误伤: {line}"

    def test_physical_merge_flagged(self, doc_traces):
        """章节/模块合并历史痕迹（类似迁移，合并写法见下方 flagged 用例）须检出。"""
        flagged = [
            "物理合并「基金风格分析」+「因子暴露分析」",
            "已物理合并为单模块",
            "两页签已物理合并为统一渲染模块",
        ]
        for line in flagged:
            assert _doc_hit(doc_traces, line) is not None, f"物理合并痕迹未检出: {line}"


# ── check-code-traces：章节编号暗号检测（CHAPTER） ─────────


class TestCodeChapterDetection:
    """代码注释用数字章节号（"N 章"/"第 N 章"）指代报告具体章节须检出（语义命名
    纪律：章节合并/重排后数字即失效，须改用语义章节名「X」章）；章节数量/序数
    表述（共 N 章 / N 章基线 / 减至 N 章 / 出现第 N 章 / N→M 章 / 引号内"N 章"）
    是合法计数，豁免（与 check-doc-traces 的 CHAPTER 检测行为一致）。"""

    def test_chapter_codes_flagged(self, code_traces):
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
            assert _code_hit(code_traces, line) is not None, f"章节编号暗号未检出: {line}"

    def test_chapter_codes_chinese_flagged(self, code_traces):
        """中文数字章节编号（第X章 / 裸X章式）指代报告具体章节须检出。"""
        flagged = [
            "三章渲染成本分档",
            "第五章估值分位",
            "第二章合并",
            "第四章摘要引用",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"中文数字章节暗号未检出: {line}"

    def test_chapter_count_exempted(self, code_traces):
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
            assert _code_hit(code_traces, line) is None, f"章节计数表述被误伤: {line}"

    def test_chapter_count_chinese_exempted(self, code_traces):
        """中文数字计数表述（共X章 / 减至X章 / 一章三区块式计数）应豁免。"""
        legit = [
            "共 二十 章",
            "总数 二十一章 减至 十九章",
            "减至 十九章",
            "「十九章」",
            "一章三区块",
            "一章两区块",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"中文数字章节计数表述被误伤: {line}"

    def test_non_patterns_clean(self, code_traces):
        legit = [
            "一章三区块",
            "4.2 章节归并对照表",
            "19 个章节",
            "章节",
            "21 轮每轮量化验收",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法表述被误伤: {line}"


# ── check-code-traces：迭代轮次暗号检测（ROUND） ────────────


class TestCodeRoundDetection:
    """代码注释用"第 N 轮"/"轮N"指代开发迭代轮次须检出（语义命名纪律：
    迭代轮次是开发痕迹，代码注释须改用语义描述）；轮次数量/运行时表述
    （共 N 轮 / N 轮每轮 / 轮询 / 轮动 / 第 N 轮循环）是合法计数或业务/
    运行时概念，豁免（与 CHAPTER 检测的计数豁免行为一致）。"""

    def test_round_codes_flagged(self, code_traces):
        flagged = [
            "第 4 轮",
            "第4轮",
            "第 12 轮",
            "12 轮迭代",
            "经 8 轮",
            "轮5 落地",
            "轮 4 落地",
            "轮13 验收标准",
            "对应轮6/轮7",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"迭代轮次暗号未检出: {line}"

    def test_round_codes_chinese_flagged(self, code_traces):
        """中文数字迭代轮次（第 X 轮式——X 为中文数字三及以上；及"轮 X"式）指代
        开发迭代历史须检出；唯第一轮/第二轮为运行时序数（LLM 圆桌会两轮辩论等），
        不纳入。"""
        flagged = [
            "第三轮落地",
            "第 三 轮验收标准",
            "轮三 落地",
            "对应轮四/轮五",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"中文数字轮次暗号未检出: {line}"

    def test_round_count_exempted(self, code_traces):
        legit = [
            "共 12 轮",
            "目标 8 轮",
            "21 轮每轮量化验收",
            "计划分 5 轮推进",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"轮次计数表述被误伤: {line}"

    def test_round_runtime_exempted(self, code_traces):
        legit = [
            "轮询超时重试",
            "第 3 轮循环",
            "行业轮动判断",
            "轮换到下一品种",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"轮次运行时表述被误伤: {line}"

    def test_round_runtime_chinese_exempted(self, code_traces):
        """中文数字运行时序数/计数表述应豁免：LLM 圆桌会两轮辩论、第一轮/第二轮
        增量抓取等为正常行为，非开发迭代痕迹。"""
        legit = [
            "第一轮增量获取",
            "第二轮互相反驳聚焦调仓",
            "圆桌会两轮辩论",
            "共 二十 轮迭代实施",
            "一轮行情",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"中文数字轮次运行时表述被误伤: {line}"

    def test_round_non_patterns_clean(self, code_traces):
        legit = [
            "一轮行情",
            "每轮循环",
            "本轮上涨",
            "首轮筛选",
            "两个回合",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法表述被误伤: {line}"

    def test_physical_merge_flagged(self, code_traces):
        """章节/模块合并历史痕迹（类似迁移，合并写法见下方 flagged 用例）须检出。"""
        flagged = [
            "物理合并「基金风格分析」+「因子暴露分析」",
            "已物理合并为单模块",
            "两页签已物理合并为统一渲染模块",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"物理合并痕迹未检出: {line}"


# ── 注释提取：多行 docstring 状态不泄漏 ─────────────────────


class TestCommentExtraction:
    """_py_comment_lines 对多行 docstring 的 in_docstring 状态必须正确开关，
    否则 docstring 后的 assert/代码行会被误当作 docstring 提取（泄漏误报）。"""

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
        """合法领域值不误伤：场景标签（S-P1）、小写缩写（f9）、Excel 单元格/范围。"""
        legit = [
            "S-P1 场景",
            "f9=市盈率",
            "合并 A1:B1",
            "数据在 B2~B5",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法字母+数字被误伤: {line}"

    def test_magic_number_letter_digit_flagged(self, code_traces):
        """MAGIC：注释中"字母+数字/连续字母+数字"（R11/P1/C21/AB14/HH6）属魔法编号须检出。"""
        flagged = [
            "P1 优先级",
            "R17 兼容",
            "C21 兼容",      # 超出 C1~C20 范围仍是字母+数字，属魔法编号
            "AB14 兼容",     # 连续字母+数字（内嵌命中也是魔法编号）
            "MC19 协议",
            "D8 数据",
            "HH6 组合",
            "C19 契约",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"魔法编号未检出: {line}"

    def test_dashtask_letter_digit_flagged(self, code_traces):
        """DASHTASK：注释中"字母-数字/连续字母-数字"（F-1/G-1/TASK-22/D-8）疑似任务编号须检出。"""
        flagged = [
            "F-1 方案",
            "G-1 批次",
            "TASK-22 编号",
            "D-8 数据",
            "I-02 配置",
            "CONCENTRATION-03 阈值",  # 非 requirements.md 需求 ID 形态的裸字母-数字
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"疑似任务编号未检出: {line}"

    def test_dashtask_legit_not_flagged(self, code_traces):
        """DASHTASK 合法领域值不误伤：交易日（T-1）、小写下标/编码（i-1/utf-8）、计数算术（N-2 项）。"""
        legit = [
            "T-1 交易日",
            "i-1 下标",
            "utf-8 编码",
            "N-2 项",
            "R-LLM-DB-QA-CONCENTRATION-03/04：需求",  # requirements.md 定义的需求 ID
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法字母-数字被误伤: {line}"

    def test_underscore_letter_digit_flagged(self, code_traces):
        """UNDERSCORE：注释中"字母_数字/连续字母_数字"（F_1/H_1/MINE_22）疑似无意义代码须检出。"""
        flagged = [
            "F_1 变量",
            "H_1 命名",
            "MINE_22 编号",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"疑似无意义代码未检出: {line}"

    def test_underscore_legit_not_flagged(self, code_traces):
        """UNDERSCORE 合法领域值不误伤：小写语义短名（changed_1m/syl_1y）。"""
        legit = [
            "changed_1m 周期",
            "syl_1y 跨度",
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"合法字母_数字被误伤: {line}"

    def test_arch_constraint_codes_flagged(self, code_traces):
        """架构约束代号（C1~C20，technical.md 定义）在注释中属暗号须检出。"""
        flagged = [
            "C1 约束：代码类型判定复用 code_utils",
            "C3 原子写入",
            "C8 日志统一",
            "C14 合规，不写 _ENV.globals",
            "C20 图下说明",
        ]
        for line in flagged:
            assert _code_hit(code_traces, line) is not None, f"架构约束代号未检出: {line}"

    def test_arch_constraint_code_false_positives(self, code_traces):
        """非约束 C+数字不误伤：十六进制色值（#C00000）、标识符内嵌（x_c20_style）。"""
        legit = [
            "#C00000",      # 十六进制色值（# 前缀且 5 位数字，MAGIC/CODE 均不命中）
            "x_c20_style",   # 标识符内嵌（_c20 前为小写字母，MAGIC 需大写开头）
        ]
        for line in legit:
            assert _code_hit(code_traces, line) is None, f"非约束 C+数字被误伤: {line}"


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
