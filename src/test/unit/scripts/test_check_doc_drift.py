"""测试：check-doc-drift.py — 文档与实现一致性（章节/开关/默认值/面板编号/目录树/统计表）

覆盖：
  - 章节表解析与比对（行数不符 / 序号或名称漂移）
  - 章节数量断言扫描（`页签编号 1~N`、`默认顺序（N 项`、`返回 result（N 项`、`N 个报告章节`）
  - 功能开关表区段提取（其它表格不误取）与成员/默认值比对
  - 开关分组计数断言（三组连写 / 单组 / 合计 三种写法）
  - 开关默认值断言（`flag` + 默认开/关）与「不跨到下一个开关」的守卫
  - 配置标量默认值表的等价判定（bool / None / 数字 / 路径 / 引号差异）
  - LLM 默认参数表（max_tokens / timeout / TTL 三方比对）
  - TUI [S] 面板编号连续性、分组边界与报告块编号枚举
  - 目录树解析（按缩进还原仓库相对路径）
  - 项目统计表比对（文件数 / 行数）
  - 归档索引完整性（管理文档 ↔ `docs-stm/archive/` 双向对齐）
  - 管理文档分区纪律（未完成/已解决/已归档错置、现行 changelog 只允许开发段头）
  - Extended Thinking 支持矩阵（手册对比表/「仅」式措辞/默认开思考提示 ↔ 代码前缀名单）
  - 真实仓库冒烟：当前文档与代码一致（run_checks() 为空）

测试通过脚本 import 方式直接复用解析/校验函数，不运行真实 CLI（`run_checks` 的 pytest 收集项
默认不跑，故冒烟测试只读文件、不触发 pytest 子进程）。
"""

from __future__ import annotations

import importlib.util
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
def drift():
    return _load_script("check-doc-drift.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


# ═══ 章节表 ═══


class TestSectionTable:
    def test_parses_rows(self, drift):
        doc = "| 1 | **1.投资分析汇总**（始终显示） |\n| 2 | **2.持仓明细与分类** |\n"
        assert drift.parse_section_rows(doc) == [(1, 1, "投资分析汇总"), (2, 2, "持仓明细与分类")]

    def test_row_count_mismatch(self, drift):
        findings = drift.check_section_table("| 1 | **1.投资分析汇总** |\n")
        assert any("章节表 1 行" in f for f in findings)

    def test_name_drift_detected(self, drift, monkeypatch):
        doc = "| 1 | **1.投资分析汇总** |\n| 2 | **2.持仓明细** |\n"
        full = [dict(s) for s in drift._REPORT_SECTION_DEFAULT[:2]]
        monkeypatch.setattr(drift, "_REPORT_SECTION_DEFAULT", full)
        findings = drift.check_section_table(doc)
        assert any("`2.持仓明细`" in f for f in findings)


# ═══ 章节数量断言 ═══


class TestSectionCounts:
    @pytest.mark.parametrize(
        "line",
        [
            "| R-OUT-05 | Excel 格式：页签编号 1~19，数字前缀保证排序 |",
            "> 空对象使用默认顺序（19 项）",
            "返回 result（19 项，key/number/type/data_flag）",
            "报告章节表（19 个报告章节）",
        ],
    )
    def test_stale_count_flagged(self, drift, line):
        findings = drift.check_section_counts({Path("manual.md"): line})
        assert len(findings) == 1 and "章节数量断言" in findings[0]

    def test_correct_count_passes(self, drift):
        total = len(drift._REPORT_SECTION_DEFAULT)
        assert drift.check_section_counts({Path("manual.md"): f"页签编号 1~{total}；返回 result（{total} 项）"}) == []

    def test_other_numbers_ignored(self, drift):
        assert drift.check_section_counts({Path("manual.md"): "共 30 项功能开关、19 个指标"}) == []


# ═══ 功能开关表 ═══


def drift_marker() -> str:
    return "**⚗ 实验组（5 项，默认关）**：\n\n| 开关名 | 默认值 | 说明 |\n|:--|:--|:--|"


class TestSwitchTable:
    def test_extract_stops_at_next_heading(self, drift):
        doc = drift_marker() + "\n| `data_quality` | `true` | 说明 |\n\n## 下一节\n\n| `sina` | `true` | 非开关表 |\n"
        assert drift.extract_switch_table(doc) == {"data_quality": True}

    def test_missing_section_reported(self, drift):
        findings = drift.check_switch_table("没有开关表\n")
        assert len(findings) == 1 and "未找到功能开关表区段" in findings[0]

    def test_missing_flag_and_unknown_flag_reported(self, drift, monkeypatch):
        registry = {"data_quality": drift.feature_switch_registry["data_quality"]}
        monkeypatch.setattr(drift, "feature_switch_registry", registry)
        doc = drift_marker() + "\n| `ghost_switch` | `true` | 说明 |\n"
        findings = drift.check_switch_table(doc)
        assert any("`data_quality` 未列入开关表" in f for f in findings)
        assert any("未登记开关 `ghost_switch`" in f for f in findings)

    def test_default_mismatch_reported(self, drift, monkeypatch):
        registry = {"data_quality": drift.feature_switch_registry["data_quality"]}
        monkeypatch.setattr(drift, "feature_switch_registry", registry)
        doc = drift_marker() + "\n| `data_quality` | `false` | 说明 |\n"
        findings = drift.check_switch_table(doc)
        assert any("默认值 False 与注册表 True" in f for f in findings)


# ═══ 开关分组计数与默认值断言 ═══


class TestSwitchCounts:
    def test_triple_form_mismatch(self, drift):
        findings = drift.check_switch_counts(
            {Path("m.md"): "全部 30 项开关分三组（⚗实验 5 / 常规 16 / 报告章节与增强 8）"}
        )
        assert len(findings) == 1 and "⚗实验 5 / 常规 16 / 报告章节与增强 8" in findings[0]

    def test_report_group_form_mismatch(self, drift):
        findings = drift.check_switch_counts({Path("m.md"): "报告组（后 8 项）= 报告块"})
        assert len(findings) == 1 and "报告组（后 8 项" in findings[0]

    def test_single_group_and_total_forms(self, drift):
        counts = drift._group_counts()
        text = (
            f"**⚗ 实验组（{counts['experimental']} 项，默认关）**\n"
            f"**常规组（{counts['standard']} 项，默认开）**\n"
            f"全部 {len(drift.feature_switch_registry)} 项开关\n"
        )
        assert drift.check_switch_counts({Path("m.md"): text}) == []

    def test_total_mismatch(self, drift):
        findings = drift.check_switch_counts({Path("m.md"): "提供 **29 项功能开关**的运行时覆写"})
        assert len(findings) == 1 and "29 项功能开关" in findings[0]


class TestDefaultClaims:
    def test_stale_default_flagged(self, drift):
        findings = drift.check_switch_default_claims({Path("m.md"): "`data_quality`（默认关）"})
        assert len(findings) == 1 and "`data_quality`" in findings[0]

    def test_correct_default_passes(self, drift):
        assert drift.check_switch_default_claims({Path("m.md"): "`data_quality`（默认开）"}) == []

    def test_does_not_cross_to_next_switch(self, drift):
        """相邻开关的默认值不得算到前一个开关头上。"""
        text = "`market_sentiment`（默认关）/ `data_quality`（默认开）"
        assert drift.check_switch_default_claims({Path("m.md"): text}) == []

    def test_suffixed_identifier_not_matched(self, drift):
        assert drift.check_switch_default_claims({Path("m.md"): "`market_temperature_data` 默认关的键"}) == []

    def test_unknown_flag_ignored(self, drift):
        assert drift.check_switch_default_claims({Path("m.md"): "`not_a_switch`（默认关）"}) == []


# ═══ 配置标量默认值表 ═══


class TestConfigDefaults:
    @pytest.mark.parametrize(
        ("shown", "code", "expected"),
        [
            ("true", True, True),
            ("false", False, True),
            ("null", None, True),
            ("None", None, True),
            ("300", 300, True),
            ("300", 299, False),
            ('""', "", True),
            ("data/holdings", "/abs/path/data/holdings", True),
            ("reports", "/abs/path/other", False),
        ],
    )
    def test_values_equal(self, drift, shown, code, expected):
        assert drift._values_equal(shown, code) is expected

    def test_table_mismatch_reported(self, drift):
        doc = "| `news_top_count` | `999` | 新闻条数 |\n"
        findings = drift.check_config_defaults(doc)
        assert len(findings) == 1 and "`news_top_count`" in findings[0]

    def test_structured_and_unknown_keys_skipped(self, drift):
        doc = "| `report_section_order` | `{}` | 结构型 |\n| `not_a_key` | `x` | 未登记 |\n"
        assert drift.check_config_defaults(doc) == []


# ═══ LLM 默认参数表 ═══


class TestLlmDefaults:
    def test_correct_row_passes(self, drift):
        doc = "| `expert_review` | 智囊团深度复盘 | 36000 | 120s | 2h（7200s） | 三阶段 |\n"
        assert drift.check_llm_defaults(doc) == []

    def test_max_tokens_and_timeout_mismatch(self, drift):
        doc = "| `expert_review` | 智囊团深度复盘 | 999 | 30s | 2h（7200s） | 三阶段 |\n"
        findings = drift.check_llm_defaults(doc)
        assert any("max_tokens 文档 999" in f for f in findings)
        assert any("timeout 文档 30s" in f for f in findings)

    def test_ttl_table_mismatch(self, drift):
        doc = "| `news_correlation` | 60s (1m) | 说明 |\n"
        findings = drift.check_llm_defaults(doc)
        assert any("TTL 表 60s" in f for f in findings)


# ═══ TUI 面板编号 ═══


def _panel_doc(numbers: list[int], report_range: tuple[int, int] | None, report_items: list[str]) -> str:
    rows = "\n".join(f"| {n} | 开关 {n} | 效果 |" for n in numbers)
    tail = ""
    if report_range:
        items = " / ".join(
            f"{i} `{flag}`" for i, flag in zip(range(report_range[0], report_range[1] + 1), report_items)
        )
        tail = f"\n\n**报告章节与增强（面板编号 {report_range[0]}-{report_range[1]}）**：{items}。\n"
    return f"交互式子菜单（面板标题「配置 LLM 报告章节与功能开关」）\n{rows}\n{tail}"


class TestPanelNumbering:
    def _expected(self, drift) -> tuple[list[int], list[str]]:
        counts = drift._group_counts()
        llm = len(drift.filter_menu_llm_modules(drift.get_llm_module_names()))
        numbers = list(range(llm + 1, llm + 1 + counts["experimental"] + counts["standard"]))
        report_flags = [flag for flag, _d in drift.switches_in_group("report")]
        return numbers, report_flags

    def test_correct_panel_passes(self, drift):
        numbers, report_flags = self._expected(drift)
        last = numbers[-1]
        doc = _panel_doc(numbers, (last + 1, last + len(report_flags)), report_flags)
        assert drift.check_panel_numbering(doc) == []

    def test_missing_number_reported(self, drift):
        numbers, report_flags = self._expected(drift)
        last = numbers[-1]
        doc = _panel_doc(numbers[:-1], (last + 1, last + len(report_flags)), report_flags)
        findings = drift.check_panel_numbering(doc)
        assert any("编号序列" in f for f in findings)

    def test_report_range_and_items_reported(self, drift):
        numbers, report_flags = self._expected(drift)
        last = numbers[-1]
        doc = _panel_doc(numbers, (last + 1, last + len(report_flags)), list(reversed(report_flags)))
        findings = drift.check_panel_numbering(doc)
        assert any("报告块开关编号/顺序" in f for f in findings)

    def test_missing_section_reported(self, drift):
        findings = drift.check_panel_numbering("无面板表\n")
        assert len(findings) == 1 and "未找到 [S] 面板编号表区段" in findings[0]


# ═══ 目录树 / 统计表 ═══


class TestTreeParsing:
    def test_reconstructs_nested_paths(self, drift):
        doc = (
            "```\n"
            "investor-util/\n"
            "├── src/                              # 源代码\n"
            "│   ├── __init__.py                   #   包标记\n"
            "│   └── python/                       # 主程序\n"
            "│       └── cache.py                  #   缓存\n"
            "└── scripts/                          # 脚本\n"
            "    └── test-runner.py                #   测试驱动\n"
            "```\n"
        )
        paths = drift.parse_tree_paths(doc)
        assert "src/__init__.py" in paths
        assert "src/python/cache.py" in paths
        assert "scripts/test-runner.py" in paths

    def test_outside_code_fence_ignored(self, drift):
        assert drift.parse_tree_paths("├── ghost.py  # 不在代码块内\n") == set()


class TestProjectStats:
    def test_stats_rows_parsed(self, drift):
        actual = drift._stats_actual()
        files, lines = actual["辅助脚本"]
        doc = f"| 辅助脚本 | Python | {files} | {lines} | 脚本 |\n"
        assert drift.check_project_stats(doc) == []

    def test_stale_stats_reported(self, drift):
        doc = "| 辅助脚本 | Python | 3 | 10 | 脚本 |\n"
        findings = drift.check_project_stats(doc)
        assert any("「辅助脚本」文件数 3" in f for f in findings)
        assert any("「辅助脚本」行数 10" in f for f in findings)

    def test_bold_label_parsed(self, drift):
        """加粗标签行（`| **测试代码** | …`）也须参与比对。"""
        findings = drift.check_project_stats("| **测试代码** | Python | 1 | 2 | 说明 |\n")
        assert any("「测试代码」" in f for f in findings)

    def test_test_count_row_parsed(self, drift, monkeypatch):
        """「测试用例」行的形状（`| — | — | **N 个** |`）须能解析并核对。"""
        monkeypatch.setattr(drift, "_collect_test_count", lambda: 12345)
        findings = drift.check_project_stats("| **测试用例** | — | — | **7,579 个** | 说明 |", with_test_count=True)
        assert any("测试用例数 7579 与 collect-test-coverage 快照 12345" in f for f in findings)

    def test_test_count_skipped_without_flag(self, drift):
        assert drift.check_project_stats("| **测试用例** | — | — | **1 个** | 说明 |") == []

    def test_unknown_label_ignored(self, drift):
        assert drift.check_project_stats("| 不存在的行 | Python | 1 | 1 | — |\n") == []


# ═══ 测试覆盖计数表 ═══


class TestTestCoverageCounts:
    def test_matching_row_passes(self, drift):
        assert drift.check_test_coverage_counts("| `unit` | **100** | ~18s |\n", {"unit": 100}) == []

    def test_mismatch_reported(self, drift):
        findings = drift.check_test_coverage_counts("| `unit` | **99** | ~18s |\n", {"unit": 100})
        assert len(findings) == 1 and "标记 `unit` 覆盖项数 99" in findings[0]

    def test_all_alias_maps_to_total(self, drift):
        findings = drift.check_test_coverage_counts("| `all` | **7532** | ~29s |\n", {"_总收集": 7581})
        assert len(findings) == 1 and "覆盖项数 7532" in findings[0]

    def test_description_cell_number_not_mistaken_for_count(self, drift):
        """「12 子组合计」这类以数字开头的描述列不得当成计数列。"""
        assert (
            drift.check_test_coverage_counts("| `unit`（父标记） | 12 子组合计 | **7,264** |\n", {"unit": 7264}) == []
        )

    def test_annotated_count_cell_parsed(self, drift):
        row = "| `llm` | 全部 LLM 相关（全部为 mock） | **750**（2026-09-16 复核：收集快照 750，未变） |\n"
        assert drift.check_test_coverage_counts(row, {"llm": 750}) == []

    def test_unknown_name_skipped(self, drift):
        assert drift.check_test_coverage_counts("| `ghost_marker` | **1** |\n", {"unit": 1}) == []


# ═══ 构建产物排除 ═══


# ═══ 归档索引 ═══


class TestArchiveIndex:
    """归档索引完整性：管理文档须列全 ``docs-stm/archive/`` 下对应归档文件。

    历史缺口：changelog 的 `## 归档` 索引曾因「发布切换时整段重写已发布段」被一并删除，
    当时无任何断言拦住；本类即该缺口的回归守卫。
    """

    def test_passes_on_real_repo(self, drift):
        """真实仓库：当前三份管理文档的归档索引与磁盘双向一致。"""
        assert drift.check_archive_index() == []

    def test_detects_real_repo_violation(self, drift, tmp_path, monkeypatch):
        """回归：索引被删时能报出（不依赖 `_scan_docs`——changelog 属历史记录类被其排除）。"""
        doc = drift._MANAGEMENTS / "changelog.md"
        broken = tmp_path / "changelog.md"
        broken.write_text(
            doc.read_text(encoding="utf-8").replace("archived_changelog.0.10.x.md", "（已删）"), encoding="utf-8"
        )
        monkeypatch.setattr(drift, "_ARCHIVE_INDEX_PAIRS", ((broken, "archived_changelog."),))
        findings = drift.check_archive_index()
        assert any("archived_changelog.0.10.x.md" in f and "缺少" in f for f in findings)

    def test_reports_missing_index_entry(self, drift, tmp_path, monkeypatch):
        """索引缺失某归档文件 → 报 finding（正向）。"""
        doc = drift._MANAGEMENTS / "changelog.md"
        broken = tmp_path / "changelog.md"
        broken.write_text(
            doc.read_text(encoding="utf-8").replace("archived_changelog.0.10.x.md", "（已删）"), encoding="utf-8"
        )
        monkeypatch.setattr(drift, "_ARCHIVE_INDEX_PAIRS", ((broken, "archived_changelog."),))
        assert any("缺少" in f for f in drift.check_archive_index())

    def test_reports_ghost_index_entry(self, drift, tmp_path, monkeypatch):
        """索引引用了不存在的归档文件 → 报 finding（反向）。"""
        doc = drift._MANAGEMENTS / "changelog.md"
        ghost = tmp_path / "changelog.md"
        ghost.write_text(
            doc.read_text(encoding="utf-8") + "\n[x](docs-stm/archive/v9.9.x/archived_changelog.9.9.x.md)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(drift, "_ARCHIVE_INDEX_PAIRS", ((ghost, "archived_changelog."),))
        assert any("archived_changelog.9.9.x.md" in f and "不存在" in f for f in drift.check_archive_index())

    def test_covers_three_management_docs(self, drift):
        """三份带归档的管理文档均在被检面内（changelog / plan / review-findings）。"""
        names = {p.name for p, _ in drift._ARCHIVE_INDEX_PAIRS}
        assert names == {"changelog.md", "plan.md", "review-findings.md"}


class TestManagementPartitions:
    """管理文档分区纪律：未完成/已解决/已归档不得错置（含历史失误的可检特征）。"""

    _CHANGELOG_OK = "## [0.11.3-dev] - 开发中（未发布）\n"

    def test_passes_on_real_repo(self, drift):
        """真实仓库：三份管理文档分区纪律无违规。"""
        assert drift.check_management_partitions() == []

    def test_pending_item_in_resolved_section(self, drift):
        """未完成项被误置已解决区（无 changelog 修复记录）→ 报 finding。"""
        rf = (
            "## 当前待处理问题\n\n### P2C\n\n| # | 问题 |\n| **rf-999** | x |\n\n"
            "## 已解决问题\n\n| # | 问题 |\n| **rf-999** | y |\n\n### 归档档案\n"
        )
        findings = drift.audit_management_partitions(review_findings=rf, plan="", changelog=self._CHANGELOG_OK)
        assert any("分区互斥" in f for f in findings)
        assert any("无修复记录" in f for f in findings)

    def test_resolved_item_without_changelog_record(self, drift):
        """仅已解决区一条、但 changelog 无记录 → 报 finding（对应「未完成项误置已解决区」类失误）。"""
        rf = "## 已解决问题\n\n| # | 问题 |\n| **rf-998** | y |\n\n### 归档档案\n"
        findings = drift.audit_management_partitions(review_findings=rf, plan="", changelog=self._CHANGELOG_OK)
        assert any("rf-998" in f and "无修复记录" in f for f in findings)

    def test_resolved_item_backed_by_archived_changelog(self, drift):
        """修复记录在归档 changelog 中亦算有记录（不误报）。"""
        rf = "## 已解决问题\n\n| # | 问题 |\n| **rf-997** | y |\n\n### 归档档案\n"
        findings = drift.audit_management_partitions(
            review_findings=rf,
            plan="",
            changelog=self._CHANGELOG_OK,
            archived_changelogs=["### 修复 rf-997\n"],
        )
        assert findings == []

    def test_completed_plan_left_in_todo(self, drift):
        """未完成区出现 ✅ 已完成项 → 报 finding。"""
        plan = "## 当前迭代待办\n\n#### ✅ `plan-9` 已做完\n\n## 归档\n"
        findings = drift.audit_management_partitions(review_findings="", plan=plan, changelog=self._CHANGELOG_OK)
        assert any("plan-9" in f and "已完成项须移入归档" in f for f in findings)

    def test_archived_plan_still_in_todo(self, drift):
        """已归档项仍在未完成区 → 报 finding（分区互斥）。"""
        plan = "## 当前迭代待办\n\n#### 🔲 `plan-9` 待做\n\n## 归档\n"
        findings = drift.audit_management_partitions(
            review_findings="",
            plan=plan,
            changelog=self._CHANGELOG_OK,
            archived_plans=["#### ✅ `plan-9` 已完成\n"],
        )
        assert any("分区互斥" in f for f in findings)

    def test_archive_prose_mention_is_not_archived_item(self, drift):
        """归档文件正文里的提及不算已归档项（防误报：如「后续项：某某计划项 …」）。"""
        plan = "## 当前迭代待办\n\n#### 🔲 `plan-49` 待做\n\n## 归档\n"
        findings = drift.audit_management_partitions(
            review_findings="",
            plan=plan,
            changelog=self._CHANGELOG_OK,
            archived_plans=["**后续项（另行登记）**：`plan-47`、`plan-49` 转正评估。\n"],
        )
        assert findings == []

    def test_released_section_still_in_live_changelog(self, drift):
        """现行 changelog 段头非开发版本 → 报 finding（已发布段须归归档）。"""
        findings = drift.audit_management_partitions(
            review_findings="", plan="", changelog="## [0.11.2] - 2026-09-24\n"
        )
        assert any("非开发版本" in f for f in findings)

    def test_multiple_version_headers_in_live_changelog(self, drift):
        """现行 changelog 含多个版本段头 → 报 finding。"""
        findings = drift.audit_management_partitions(
            review_findings="", plan="", changelog="## [0.11.3-dev] - x\n\n## [0.11.2] - 2026-09-24\n"
        )
        assert any("个版本段头" in f for f in findings)

    def test_missing_files_do_not_crash(self, drift):
        """空文本（文件缺失）不抛异常，也不臆造 finding。"""
        assert drift.audit_management_partitions(review_findings="", plan="", changelog="") == []


# ═══ Thinking 支持矩阵 ═══


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
            ("docs-stm/tmp/scratch.py", True),
            # test-reports 规范位置在仓库根（不在受检根内）→ 受检目录下出现属误落，须报出
            ("test-reports/latest/index.html", False),
            ("scripts/test-reports/index.html", False),
            ("src/python/core/atomic_write.py", False),
            ("src/test/unit/scripts/test_check_doc_drift.py", False),
        ],
    )
    def test_is_generated(self, drift, rel, expected):
        assert drift._is_generated(rel) is expected

    def test_misplaced_test_reports_reported(self, drift, monkeypatch, tmp_path):
        """受检目录下出现 test-reports/（入口把项目根算错等误落）→ 必须报「目录树缺少」。"""
        (tmp_path / "scripts/test-reports").mkdir(parents=True)
        (tmp_path / "scripts/test-reports/index.html").write_text("<html/>", encoding="utf-8")
        real_rel = drift.rel

        def _fake_rel(path):
            try:
                return str(Path(path).relative_to(tmp_path))
            except ValueError:
                return real_rel(path)

        monkeypatch.setattr(drift, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(drift, "rel", _fake_rel)
        monkeypatch.setattr(drift, "_TREE_ROOTS", ("scripts",))
        findings = drift.check_dir_tree("```\ninvestor-util/\n```\n")
        assert len(findings) == 1 and "scripts/test-reports/index.html" in findings[0]

    def test_tree_check_ignores_generated(self, drift, monkeypatch, tmp_path):
        """忽略产物后：真实文件缺条目仍要报，产物不报。"""
        (tmp_path / "src/pkg").mkdir(parents=True)
        (tmp_path / "src/pkg/mod.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "src/pkg/mod.egg-info").mkdir()
        (tmp_path / "src/pkg/mod.egg-info/PKG-INFO").write_text("x\n", encoding="utf-8")
        monkeypatch.setattr(drift, "REPO_ROOT", tmp_path)
        # rel() 来自共享模块 _checklib，须一并替身到临时仓库根
        real_rel = drift.rel

        def _fake_rel(path):
            try:
                return str(Path(path).relative_to(tmp_path))
            except ValueError:
                return real_rel(path)

        monkeypatch.setattr(drift, "rel", _fake_rel)
        monkeypatch.setattr(drift, "_TREE_ROOTS", ("src",))
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
