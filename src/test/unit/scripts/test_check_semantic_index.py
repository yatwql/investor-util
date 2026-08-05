"""测试：check-semantic-index.py — 功能语义命名表双向校验

覆盖：
  - 标记区间提取：start/end 标记存在返回正文、缺失返回 None
  - 表行解析：仅取第一列反引号 slug，开关列 enable_portfolio_evolution 不误取
  - 合并章 key 解析：仅取「合并章代码标识符」注，并入说明注（dividend_flow）不误取
  - 权威源 ast 解析：report_submodules 字典键、registry._REPORT_SECTION_DEFAULT key
    （Assign 与 AnnAssign 两种赋值形态）
  - 注释剔除：tokenize 剔除注释、字符串字面量保留
  - 反向存在性：代码中出现为 True、仅注释提及为 False、__pycache__ 跳过
  - run_checks 三向校验：全通过 / 正向表外键 / 反向僵尸条目 / 合并章 key 缺失 / 标记缺失
  - 真实仓库冒烟：当前 technical.md + _config_defaults.py + registry.py 一致

测试通过脚本 import 方式直接复用解析函数，不运行真实 CLI。
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
def sem_index():
    return _load_script("check-semantic-index.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


# ═══ 标记区间提取 ═══


class TestMarkerRegion:
    def test_returns_body_between_markers(self, sem_index):
        doc = "头\n<!-- semantic-index:start -->\n表正文\n<!-- semantic-index:end -->\n尾"
        assert sem_index.extract_marker_region(doc) == "\n表正文\n"

    def test_none_when_start_missing(self, sem_index):
        doc = "无开始标记\n<!-- semantic-index:end -->\n"
        assert sem_index.extract_marker_region(doc) is None

    def test_none_when_end_missing(self, sem_index):
        doc = "<!-- semantic-index:start -->\n无结束标记\n"
        assert sem_index.extract_marker_region(doc) is None


# ═══ 表行解析 ═══


class TestParseTableSlugs:
    def test_extracts_only_first_cell_slug(self, sem_index):
        doc = (
            "<!-- semantic-index:start -->\n"
            "| 语义 slug | 中文名 | config 开关 |\n"
            "|:--|:--|:--|\n"
            "| `snapshot_diff` | 快照差异 | 随 `enable_portfolio_evolution` |\n"
            "| `cost_lots` | 成本流水 | `report_submodules.cost_lots`（默认关） |\n"
            "<!-- semantic-index:end -->"
        )
        assert sem_index.parse_table_slugs(doc) == ["snapshot_diff", "cost_lots"]

    def test_returns_empty_without_markers(self, sem_index):
        doc = "| `candidate_compare` | 候选基金比较 |\n"
        assert sem_index.parse_table_slugs(doc) == []


# ═══ 合并章 key 解析 ═══


class TestParseMergedSheetKeys:
    def test_only_merged_note_ignores_merged_into_note(self, sem_index):
        doc = (
            "<!-- semantic-index:start -->\n"
            "| `candidate_compare` | 候选基金比较 |\n"
            "\n"
            "> **子功能并入说明**：`dividend_flow`（分红现金流，并入 `fund_flow`）、"
            "`holding_diagnosis`（品种覆盖诊断，并入 `data_quality`）。\n"
            "\n"
            "> **合并章代码标识符**：`position_relationship`（持仓关系矩阵，合并 "
            "`fund_overlap` + `correlation_analysis`）、`portfolio_history_drawdown`（组合历史走势与回撤）。\n"
            "<!-- semantic-index:end -->"
        )
        assert sem_index.parse_merged_sheet_keys(doc) == [
            "position_relationship",
            "portfolio_history_drawdown",
        ]


# ═══ 权威源 ast 解析 ═══


class TestReportSubmodulesKeys:
    def test_parses_nested_dict(self, sem_index):
        source = (
            '_DEFAULT_CONFIG = {\n'
            '    "enable_action": False,\n'
            '    "report_submodules": {\n'
            '        "data_quality": False,\n'
            '        "cost_lots": False,\n'
            '    },\n'
            '}\n'
        )
        assert sem_index.report_submodules_keys(source) == ["data_quality", "cost_lots"]

    def test_missing_key_returns_empty(self, sem_index):
        source = '_DEFAULT_CONFIG = {"enable_action": True}\n'
        assert sem_index.report_submodules_keys(source) == []


class TestRegistrySectionKeys:
    def test_annassign_form(self, sem_index):
        source = (
            "_REPORT_SECTION_DEFAULT: list[dict] = [\n"
            '    {"key": "summary", "name": "投资分析汇总", "number": 1},\n'
            '    {"key": "position_relationship", "name": "持仓关系矩阵", "number": 7},\n'
            "]\n"
        )
        assert sem_index.registry_section_keys(source) == ["summary", "position_relationship"]

    def test_plain_assign_form(self, sem_index):
        source = '_REPORT_SECTION_DEFAULT = [{"key": "action", "name": "行动建议", "number": 17}]\n'
        assert sem_index.registry_section_keys(source) == ["action"]

    def test_other_assign_ignored(self, sem_index):
        source = '_OTHER = [{"key": "x"}]\n'
        assert sem_index.registry_section_keys(source) == []


# ═══ 注释剔除与反向存在性 ═══


class TestCodeWithoutComments:
    def test_strips_comments_keeps_strings(self, sem_index):
        source = (
            "# 顶部注释\n"
            'x = 1  # 行尾注释\n'
            'y = "rebalance_advice"  # 字符串保留\n'
        )
        stripped = sem_index._code_without_comments(source)
        assert "顶部注释" not in stripped
        assert "行尾注释" not in stripped
        assert "rebalance_advice" in stripped
        assert "x" in stripped and "y" in stripped

    def test_comment_only_file_yields_empty(self, sem_index):
        source = "# rebalance_advice 已删除，仅注释提及\n"
        assert sem_index._code_without_comments(source) == ""


class TestSlugExistsInCode:
    def test_true_when_substring_in_identifier(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text("def build_rebalance_advice(): pass\n", encoding="utf-8")
        assert sem_index.slug_exists_in_code(tmp_path, "rebalance_advice") is True

    def test_true_when_string_literal(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text('data = {"rebalance_advice": []}\n', encoding="utf-8")
        assert sem_index.slug_exists_in_code(tmp_path, "rebalance_advice") is True

    def test_false_when_comment_only(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text("# rebalance_advice 已删除\n", encoding="utf-8")
        assert sem_index.slug_exists_in_code(tmp_path, "rebalance_advice") is False

    def test_false_when_missing(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert sem_index.slug_exists_in_code(tmp_path, "ghost_slug") is False

    def test_skips_pycache(self, sem_index, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "a.py").write_text("zombie_slug = 1\n", encoding="utf-8")
        assert sem_index.slug_exists_in_code(tmp_path, "zombie_slug") is False


# ═══ run_checks 三向校验 ═══


def _valid_doc() -> str:
    return (
        "<!-- semantic-index:start -->\n"
        "| 语义 slug | 中文名 |\n"
        "|:--|:--|\n"
        "| `candidate_compare` | 候选基金比较 |\n"
        "| `cost_lots` | 成本流水 |\n"
        "\n"
        "> **合并章代码标识符**：`position_relationship`（持仓关系矩阵，合并 `fund_overlap`）。\n"
        "<!-- semantic-index:end -->\n"
    )


def _valid_defaults() -> str:
    return (
        '_DEFAULT_CONFIG = {\n'
        '    "report_submodules": {\n'
        '        "candidate_compare": False,\n'
        '        "cost_lots": False,\n'
        '    },\n'
        '}\n'
    )


def _valid_registry() -> str:
    return (
        "_REPORT_SECTION_DEFAULT: list[dict] = [\n"
        '    {"key": "summary", "name": "投资分析汇总", "number": 1},\n'
        '    {"key": "position_relationship", "name": "持仓关系矩阵", "number": 7},\n'
        "]\n"
    )


class TestRunChecks:
    def test_all_pass(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text(
            "def build_candidate_compare(): pass\n"
            'd = {"cost_lots": False}\n'
            'def build_position_relationship(): pass\n',
            encoding="utf-8",
        )
        assert (
            sem_index.run_checks(_valid_doc(), _valid_defaults(), _valid_registry(), tmp_path)
            == []
        )

    def test_forward_finds_unregistered_key(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        defaults = (
            '_DEFAULT_CONFIG = {\n'
            '    "report_submodules": {\n'
            '        "market_temperature": False,\n'
            '    },\n'
            '}\n'
        )
        findings = sem_index.run_checks(_valid_doc(), defaults, _valid_registry(), tmp_path)
        assert any("report_submodules.market_temperature" in f for f in findings)

    def test_reverse_finds_zombie(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        doc = (
            "<!-- semantic-index:start -->\n"
            "| 语义 slug | 中文名 |\n"
            "|:--|:--|\n"
            "| `ghost_slug` | 幽灵条目 |\n"
            "<!-- semantic-index:end -->\n"
        )
        findings = sem_index.run_checks(doc, _valid_defaults(), _valid_registry(), tmp_path)
        assert any("`ghost_slug`" in f for f in findings)

    def test_merged_key_missing_from_registry(self, sem_index, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        doc = (
            "<!-- semantic-index:start -->\n"
            "| `candidate_compare` | 候选基金比较 |\n"
            "\n"
            "> **合并章代码标识符**：`ghost_sheet`（幽灵合并章，合并 `old_key`）。\n"
            "<!-- semantic-index:end -->\n"
        )
        findings = sem_index.run_checks(doc, _valid_defaults(), _valid_registry(), tmp_path)
        assert any("`ghost_sheet`" in f for f in findings)

    def test_missing_markers_short_circuits(self, sem_index, tmp_path):
        doc = "| `candidate_compare` | 候选基金比较 |\n"
        findings = sem_index.run_checks(doc, _valid_defaults(), _valid_registry(), tmp_path)
        assert len(findings) == 1
        assert "semantic-index" in findings[0]


# ═══ 真实仓库冒烟 ═══


class TestRealRepoSmoke:
    def test_current_repo_passes(self, sem_index):
        doc_text = sem_index._TECHNICAL_MD.read_text(encoding="utf-8")
        defaults_source = sem_index._CONFIG_DEFAULTS.read_text(encoding="utf-8")
        registry_source = sem_index._REGISTRY_PY.read_text(encoding="utf-8")
        findings = sem_index.run_checks(
            doc_text, defaults_source, registry_source, sem_index._CODE_ROOT
        )
        assert findings == []
