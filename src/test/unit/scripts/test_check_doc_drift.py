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


# ═══ 真实仓库冒烟 ═══


class TestRealRepoSmoke:
    def test_current_repo_consistent(self, drift):
        findings = drift.run_checks()
        assert findings == []
