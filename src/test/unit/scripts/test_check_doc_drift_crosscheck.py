"""测试：check-doc-drift.py — 文档↔代码交叉校验（分片）。

覆盖：
  - 数据源链路表 §4.2（Provider Chain 降级表 ↔ `_DEFAULT_CHAINS` 逐链双向一致）
  - Extended Thinking 支持矩阵（手册对比表/「仅」式措辞 ↔ 代码前缀名单）
  - 测试收集快照解析与编码降级（`_collect_test_snapshot` cp936 回归）
  - 生成产物列表（*.egg-info 等构建/缓存产物不触发目录树误报）
  - 真实仓库冒烟（`run_checks()` 为空）与项目统计表回写同步（`sync_project_stats`）
  - 守护清单同源（五处权威源 + pre-commit 钩子执行体两两一致）

运行：
  pytest src/test/unit/scripts/test_check_doc_drift_crosscheck.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from . import test_check_doc_drift as _base
from .test_check_doc_drift import _documented_test_count

# fixture 经模块属性注入：用例参数名 drift/drift_parts 由 pytest 按模块命名空间解析；
# 赋值形态避免「参数遮蔽 import」触发 F811
drift = _base.drift
drift_parts = _base.drift_parts

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
    pytest.mark.usefixtures("offline_external_sources"),
]


# ═══ Thinking 支持矩阵 ═══


class TestChainTable:
    """§4.2 Provider Chain 降级表 ↔ `_DEFAULT_CHAINS` 逐链双向一致（「降级表缺链」类缺口守卫）。

    历史缺口：该表声称枚举全部链路，实际只列 5 行——`financial_report` 接入巨潮
    备源后仍缺席，另有 7 条链从未登记；表与代码无断言绑定，漂移长期无人发现。
    """

    def test_real_repo_consistent(self, drift):
        assert drift.check_chain_table(drift._RELIABILITY_MD.read_text(encoding="utf-8")) == []

    def test_missing_chain_reported(self, drift):
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        broken = text.replace("| `fund_hold` |", "| `不是链` |", 1)
        findings = drift.check_chain_table(broken)
        assert any("缺少链路 `fund_hold`" in f for f in findings)

    def test_ghost_chain_reported(self, drift):
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        broken = text + "\n| `ghost_chain` | 主 | 备 | 条件 |\n"
        findings = drift.check_chain_table(broken)
        assert any("幽灵行" in f and "ghost_chain" in f for f in findings)

    def test_missing_table_reported(self, drift):
        findings = drift.check_chain_table("# 无表文档\n")
        assert any("未找到 §4.2" in f for f in findings)

    def test_slot_missing_reported(self, drift):
        """槽位漏登记（本轮真实缺陷形态）：文档 id 列少一个槽即报。"""
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        broken = text.replace("| `datasink` → `cninfo` |", "| `datasink` |", 1)
        findings = drift.check_chain_table(broken)
        assert any("`financial_report`" in f and "漏槽" in f and "cninfo" in f for f in findings)

    def test_slot_extra_reported(self, drift):
        """文档多写一个槽（代码没有）同样报。"""
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        broken = text.replace("| `datasink` → `cninfo` |", "| `datasink` → `cninfo` → `sina` |", 1)
        findings = drift.check_chain_table(broken)
        assert any("多槽" in f and "sina" in f for f in findings)

    def test_slot_order_mismatch_reported(self, drift):
        """槽位顺序即回退优先级：顺序不一致要报（不是只看集合相等）。"""
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        broken = text.replace("| `datasink` → `cninfo` |", "| `cninfo` → `datasink` |", 1)
        findings = drift.check_chain_table(broken)
        assert any("顺序不一致" in f for f in findings)

    def test_column_reorder_still_parsed(self, drift):
        """列序调整（provider id 换到第 2 列）仍能正确解析——按表头定位而非硬编码下标。"""
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        out = []
        for line in text.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if line.startswith("|") and len(cells) == 5:
                line = "| " + " | ".join([cells[0], cells[3], cells[1], cells[2], cells[4]]) + " |"
            out.append(line)
        assert drift.check_chain_table(chr(10).join(out)) == []

    def test_missing_id_column_reported(self, drift):
        """旧格式（无 id 列）必须报缺列，否则门禁会静默放过槽位漂移。"""
        text = drift._RELIABILITY_MD.read_text(encoding="utf-8")
        broken = text.replace(
            "| `fund_rank` | 天天基金 | —（单源） | `tiantian` | 不可用时基金业绩排名域标记降级 |",
            "| `fund_rank` | 天天基金 | —（单源） | 不可用时基金业绩排名域标记降级 |",
            1,
        )
        findings = drift.check_chain_table(broken)
        assert any("`fund_rank`" in f and "provider id 列" in f for f in findings)


class TestThinkingSupportMatrix:
    """手册 Extended Thinking 矩阵与代码前缀名单一致。

    历史缺口：手册支持 bullet 已含 Kimi，但「模型差异」对比表与「仅 Claude / Gemini」
    措辞未同步 → 同一章节自相矛盾（无断言覆盖）；本类即该缺口的回归守卫。
    """

    _TABLE_OK = (
        "| 维度 | Anthropic Claude | DeepSeek V4+ | Google Gemini 2.5 | Kimi（月之暗面） |\n"
        "|------|------|------|------|------|\n"
        "| 控制参数 | `thinking.budget_tokens` | `output_config.effort` | `thinkingBudget` | `thinking.budget_tokens` |\n"
        "**仅在使用 Claude / Gemini / Kimi 模型时 `thinking_budget_{模块}` 有意义**。\n"
        "**DeepSeek 默认开思考**；**Kimi 默认开思考**。\n"
    )

    def test_passes_on_real_repo(self, drift):
        assert drift.check_thinking_support_matrix() == []

    def test_detects_missing_family_column(self, drift):
        """对比表缺厂商列 → 报 finding（捕获「矩阵漏族」类缺口）。"""
        broken = self._TABLE_OK.replace("| Kimi（月之暗面） |", "|")
        findings = drift.check_thinking_support_matrix(broken)
        assert any("缺少厂商列 `kimi`" in f for f in findings)

    def test_detects_closed_enumeration_missing_family(self, drift):
        """「仅 A / B」式措辞漏族 → 报 finding。"""
        broken = self._TABLE_OK.replace(
            "**仅在使用 Claude / Gemini / Kimi 模型时 `thinking_budget_{模块}` 有意义**。",
            "**仅在使用 Claude 或 Gemini 模型时 `thinking_budget_{模块}` 有意义**。",
        )
        findings = drift.check_thinking_support_matrix(broken)
        assert any("budget_tokens 族厂商" in f and "kimi" in f for f in findings)

    def test_ignores_unrelated_jinyi_lines(self, drift):
        """无 budget 概念词的「仅」句（如强制推理说明/定价行）不误报。"""
        text = (
            self._TABLE_OK
            + "**DeepSeek V4 强制推理说明**：`max_tokens` 是 thinking + 最终文本的共享预算（而非仅最终输出）。\n"
            + "- **已停用模型名**：`deepseek-chat` 是 flash 系列非思考模式的兼容别名。\n"
        )
        assert drift.check_thinking_support_matrix(text) == []

    def test_missing_table_reports(self, drift):
        findings = drift.check_thinking_support_matrix("# 无表章节\n正文\n")
        assert any("未找到" in f for f in findings)

    def test_default_on_family_requires_hint(self, drift):
        """默认开思考族缺提示 → 报 finding。"""
        text = self._TABLE_OK.replace("**DeepSeek 默认开思考**；**Kimi 默认开思考**。\n", "")
        findings = drift.check_thinking_support_matrix(text)
        assert any("默认开思考族" in f for f in findings)

    def test_empty_text_is_noop(self, drift):
        assert drift.check_thinking_support_matrix("") == []


class TestCollectTestSnapshot:
    """`_collect_test_snapshot` 子进程快照解析与编码降级（回归：Windows cp936 下快照崩溃）。

    背景：`collect-test-coverage.py` 曾在中文 Windows 上按 GBK 写出中文分组名，
    消费方按 UTF-8 解码 → reader 线程 `UnicodeDecodeError` → `proc.stdout` 为 None
    → `re.search(..., None)` 抛 `TypeError`，`check-doc-drift.py --sync` 直接堆栈退出。
    """

    def test_parses_counts(self, drift_parts, monkeypatch):
        """正常 UTF-8 输出 → 解析出总收集与各分组计数。"""

        class _Proc:
            stdout = "\n总收集: 8167 项\n\n### 模式对应测试量\nunit: 7846\nedge: 949\n"

        monkeypatch.setattr(drift_parts._shared.subprocess, "run", lambda *a, **k: _Proc())
        snap = drift_parts._shared._collect_test_snapshot()
        assert snap["_总收集"] == 8167
        assert snap["unit"] == 7846
        assert snap["edge"] == 949

    def test_none_stdout_degrades_without_crash(self, drift_parts, monkeypatch):
        """stdout 为 None（reader 线程解码异常兑底）→ 返回空快照，不得抛 TypeError。"""

        class _Proc:
            stdout = None

        monkeypatch.setattr(drift_parts._shared.subprocess, "run", lambda *a, **k: _Proc())
        assert drift_parts._shared._collect_test_snapshot() == {}

    def test_empty_stdout_degrades_without_crash(self, drift_parts, monkeypatch):
        """stdout 为空字符串 → 返回空快照。"""

        class _Proc:
            stdout = "   \n"

        monkeypatch.setattr(drift_parts._shared.subprocess, "run", lambda *a, **k: _Proc())
        assert drift_parts._shared._collect_test_snapshot() == {}

    def test_subprocess_run_uses_error_tolerant_encoding(self, drift_parts, monkeypatch):
        """回归：调用 subprocess.run 必须带 errors="replace"（不因个别非法字节在 reader 线程崩）。"""
        captured: dict = {}

        class _Proc:
            stdout = "总收集: 1 项\n"

        def _fake_run(*args, **kwargs):
            captured.update(kwargs)
            return _Proc()

        monkeypatch.setattr(drift_parts._shared.subprocess, "run", _fake_run)
        drift_parts._shared._collect_test_snapshot()
        assert captured.get("encoding") == "utf-8"
        assert captured.get("errors") == "replace"


class TestGeneratedArtifacts:
    """构建/缓存产物不得触发目录树误报（CI 的 `pip install -e` 会在 src/ 下生成 *.egg-info）。"""

    @pytest.mark.parametrize(
        ("rel", "expected"),
        [
            ("src/investor_util.egg-info/PKG-INFO", True),
            ("src/investor_util.egg-info/SOURCES.txt", True),
            ("src/python/__pycache__/mod.cpython-313.pyc", True),
            ("build/lib/python/mod.py", True),
            ("pkg/investor_util.dist-info/METADATA", True),
            (".coverage", True),
            ("docs/tmp/scratch.py", True),
            # test-reports 规范位置在仓库根（不在受检根内）→ 受检目录下出现属误落，须报出
            ("test-reports/latest/index.html", False),
            ("scripts/test-reports/index.html", False),
            ("src/python/core/atomic_write.py", False),
            ("src/test/unit/scripts/test_check_doc_drift.py", False),
        ],
    )
    def test_is_generated(self, drift, rel, expected):
        assert drift._is_generated(rel) is expected

    def test_misplaced_test_reports_reported(self, drift, monkeypatch, tmp_path, drift_parts):
        """受检目录下出现 test-reports/（入口把项目根算错等误落）→ 必须报「目录树缺少」。"""
        (tmp_path / "scripts/test-reports").mkdir(parents=True)
        (tmp_path / "scripts/test-reports/index.html").write_text("<html/>", encoding="utf-8")
        real_rel = drift.rel

        def _fake_rel(path):
            try:
                return Path(path).relative_to(tmp_path).as_posix()
            except ValueError:
                return real_rel(path)

        monkeypatch.setattr(drift_parts._tree, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(drift_parts._tree, "rel", _fake_rel)
        monkeypatch.setattr(drift_parts._tree, "_TREE_ROOTS", ("scripts",))
        findings = drift.check_dir_tree("```\ninvestor-util/\n```\n")
        assert len(findings) == 1 and "scripts/test-reports/index.html" in findings[0]

    def test_tree_check_ignores_generated(self, drift, monkeypatch, tmp_path, drift_parts):
        """忽略产物后：真实文件缺条目仍要报，产物不报。"""
        (tmp_path / "src/pkg").mkdir(parents=True)
        (tmp_path / "src/pkg/mod.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "src/pkg/mod.egg-info").mkdir()
        (tmp_path / "src/pkg/mod.egg-info/PKG-INFO").write_text("x\n", encoding="utf-8")
        monkeypatch.setattr(drift_parts._tree, "REPO_ROOT", tmp_path)
        # rel() 来自共享模块 _checklib，须一并替身到临时仓库根
        real_rel = drift.rel

        def _fake_rel(path):
            try:
                return Path(path).relative_to(tmp_path).as_posix()
            except ValueError:
                return real_rel(path)

        monkeypatch.setattr(drift_parts._tree, "rel", _fake_rel)
        monkeypatch.setattr(drift_parts._tree, "_TREE_ROOTS", ("src",))
        doc = "```\ninvestor-util/\n├── src/              # 源代码\n│   └── pkg/\n│       └── mod.py  # 模块\n```\n"
        assert drift.check_dir_tree(doc) == []

        (tmp_path / "src/pkg/extra.py").write_text("y = 1\n", encoding="utf-8")
        findings = drift.check_dir_tree(doc)
        assert len(findings) == 1 and "extra.py" in findings[0]


# ═══ 真实仓库冒烟 ═══


class TestRealRepoSmoke:
    def test_current_repo_consistent(self, drift):
        findings = drift.run_checks()
        assert findings == []


# ═══ 统计快照自动同步（--sync） ═══


class TestProjectStatsSync:
    """sync_project_stats —— 实测数字自动回写 folders.md 统计表。

    治理「统计登记数字 vs 实测」类漂移（CI 最高频红源）：changelog/自审
    每补一行、用例每增删，实测行数即变；人工同步必漏，故提供 --sync
    由钩子自动回写并暂存。
    """

    _DOC = """# 标题

| 类别 | 开发语言 | 文件数 | 代码行数 | 说明 |
|---|---|---|---|---|
| 主程序代码 | Python | **10** | **1,000** | src 代码 |
| **测试用例** | — | — | **55 个** | collect 快照 |
| **版本对照** | — | — | — | 固定基准不触碰 |
"""

    def test_syncs_drifted_numbers(self, drift, drift_parts, tmp_path):
        doc = tmp_path / "folders.md"
        doc.write_text(self._DOC, encoding="utf-8")
        actual = {"主程序代码": (11, 1024)}
        applied = drift_parts._tree.sync_project_stats(doc, actual=actual, test_count=60)
        assert any("「主程序代码」文件数" in line for line in applied)
        out = doc.read_text(encoding="utf-8")
        # 数字已回写且千分位风格保留
        assert "| 主程序代码 | Python | **11** | **1,024** |" in out.replace("\n", "").join([]) or "**11**" in out
        assert "**1,024**" in out
        # 用例数行同步回写
        assert "**60 个**" in out
        # 版本对照行不触碰（标签口径不同，不精确匹配实测键）
        assert "**版本对照**" in out and "| — |" in out

    def test_noop_when_consistent(self, drift, drift_parts, tmp_path):
        doc = tmp_path / "folders.md"
        doc.write_text(self._DOC, encoding="utf-8")
        doc.write_text(doc.read_text(encoding="utf-8"), encoding="utf-8")
        actual = {"主程序代码": (10, 1000)}  # 与登记一致
        applied = drift_parts._tree.sync_project_stats(doc, actual=actual, test_count=55)
        assert applied == []
        assert doc.read_text(encoding="utf-8") == self._DOC

    def test_missing_file_is_noop(self, drift, drift_parts, tmp_path):
        applied = drift_parts._tree.sync_project_stats(tmp_path / "nope.md", actual={}, test_count=1)
        assert applied == []

    def test_real_repo_sync_idempotent(self, drift, drift_parts):
        """真实仓库：同步是幂等的（当前一致 → 无应用项、文件零改动）。

        test_count 显式注入（从 folders.md 「测试用例」行读当前登记值），**不触发
        嵌套全量 pytest 收集**——测试运行在 xdist worker 内，嵌套收集会与并行套件
        争用资源而采到不完整集合（实测 7964 vs 完整 8173），使幂等断言假失败。
        真实 `_stats_actual()` 仍照常实测，故同步逻辑的真实仓库幂等性照旧被覆盖。
        """
        from _doc_drift._tree import _FOLDERS_MD, sync_project_stats as _sync

        original = Path(_FOLDERS_MD).read_text(encoding="utf-8")
        documented = _documented_test_count(original)
        assert documented is not None, "folders.md 「测试用例」行缺少数量"
        applied = _sync(test_count=documented)
        after = Path(_FOLDERS_MD).read_text(encoding="utf-8")
        assert applied == [] and after == original


# ═══ 守护清单同源 ═══


class TestGuardParity:
    """`find_guard_parity` / `check_guard_parity`（五处守护清单脚本集合两两一致）。"""

    @staticmethod
    def _good(*names: str) -> str:
        return "\n".join(f"run: python scripts/{n} --ci" for n in names)

    def test_identical_sets_pass(self, drift):
        src = {
            "A": self._good("check-x.py", "check-y.py"),
            "B": self._good("check-y.py", "check-x.py"),
        }
        assert drift.find_guard_parity(src) == []

    def test_missing_script_reported(self, drift):
        src = {
            "A": self._good("check-x.py", "check-y.py"),
            "B": self._good("check-x.py"),
        }
        findings = drift.find_guard_parity(src)
        assert any("缺少" in f and "check-y.py" in f for f in findings)

    def test_extra_script_reported(self, drift):
        src = {
            "A": self._good("check-x.py"),
            "B": self._good("check-x.py", "check-extra.py"),
        }
        findings = drift.find_guard_parity(src)
        assert any("多出" in f and "check-extra.py" in f for f in findings)

    def test_unmatched_region_reported(self, drift):
        src = {"A": self._good("check-x.py"), "B": None}
        findings = drift.find_guard_parity(src)
        assert any("未匹配到守护清单区域" in f for f in findings)

    def test_empty_region_reported(self, drift):
        src = {"A": self._good("check-x.py"), "B": "标题在但没有任何脚本引用"}
        findings = drift.find_guard_parity(src)
        assert any("未提取到" in f for f in findings)

    def test_single_source_needs_no_comparison(self, drift):
        # 单一成功来源不构成比较，但截取失败仍须单独报出
        assert drift.find_guard_parity({"A": self._good("check-x.py")}) == []
        assert drift.find_guard_parity({"A": None}) != []

    def test_real_sources_include_precommit_hook(self, drift):
        """真实源集合必须包含 pre-commit 钩子——锚点失配会截出 None 并被报出。"""
        sources = drift.guard_parity_sources()
        assert any(label.endswith(".githooks/pre-commit 守护清单") for label in sources)

    def test_real_sources_guard_sets_match(self, drift):
        """五份真实源（含钩子执行体）的守护集合两两一致——真实仓库断言。"""
        assert drift.find_guard_parity(drift.guard_parity_sources()) == []
