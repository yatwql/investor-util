"""测试：scripts/_checklib.py 与 scripts/_traces_common.py — 检查脚本共享设施

覆盖：
  - `rel()`：仓库内路径取相对、仓库外路径原样返回
  - `report()`：通过返回 0 + `[OK]`；失败返回 2 + 逐条输出；`--ci` 只输出裸描述；`{n}` 占位
  - `extract_region()` / `replace_region()`：标记齐全取/替换、标记缺失返回 None
  - `extract_table_region()`：正常表格、marker 缺失、区域非表格、夹非表格行、缺分隔行
  - `replace_table_region()`：替换表体、标记缺失抛 ValueError
  - `_traces_common`：章节/轮次合法计数表述豁免命中、非法引用不误豁免、编译缓存与函数一致
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录（src/test/unit/scripts 向上 4 级）
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


def _load_script(name: str):
    """按文件名加载 scripts/ 下的模块（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def checklib():
    return _load_script("_checklib.py")


@pytest.fixture(scope="module")
def traces_common():
    return _load_script("_traces_common.py")


# ═══ rel ═══


class TestRel:
    def test_repo_path_is_relative(self, checklib):
        assert checklib.rel(_REPO_ROOT / "README.md") == "README.md"

    def test_outside_path_returned_as_is(self, checklib, tmp_path):
        outside = tmp_path / "outside.md"
        outside.write_text("x", encoding="utf-8")
        assert checklib.rel(outside) == str(outside)


# ═══ report ═══


class TestReport:
    def test_passing_returns_zero(self, checklib, capsys):
        assert checklib.report([], "[OK] 全通过") == 0
        assert "[OK] 全通过" in capsys.readouterr().out

    def test_findings_return_two_with_err_prefix(self, checklib, capsys):
        assert checklib.report(["a.py: 问题一", "b.py: 问题二"], "[OK]") == 2
        out = capsys.readouterr().out
        assert "[ERR] a.py: 问题一" in out
        assert "[!] 发现 2 处问题" in out

    def test_ci_mode_prints_bare_lines_only(self, checklib, capsys):
        assert checklib.report(["a.py: 问题一"], "[OK]", ci=True) == 2
        out = capsys.readouterr().out
        assert out.strip() == "a.py: 问题一"

    def test_custom_fail_message_supports_count_placeholder(self, checklib, capsys):
        checklib.report(["x"], "[OK]", fail_message="[!] 发现 {n} 处 SVG 问题")
        assert "[!] 发现 1 处 SVG 问题" in capsys.readouterr().out


# ═══ 区间与表格解析 ═══


class TestRegions:
    def test_extract_region(self, checklib):
        text = "头\n<!--s-->\n正文\n<!--e-->\n尾"
        assert checklib.extract_region(text, "<!--s-->", "<!--e-->") == "\n正文\n"

    @pytest.mark.parametrize("text", ["无标记", "<!--s-->\n只有开始", "只有结束\n<!--e-->"])
    def test_extract_region_missing_marker(self, checklib, text):
        assert checklib.extract_region(text, "<!--s-->", "<!--e-->") is None

    def test_replace_region(self, checklib):
        text = "头<!--s-->旧<!--e-->尾"
        assert checklib.replace_region(text, "<!--s-->", "<!--e-->", "新") == "头<!--s-->新<!--e-->尾"

    def test_replace_region_missing_marker(self, checklib):
        assert checklib.replace_region("无标记", "<!--s-->", "<!--e-->", "新") is None

    def test_extract_table_region(self, checklib):
        text = "<!--t:start-->\n| A | B |\n|---|---|\n| 1 | 2 |\n<!--t:end-->"
        lines = checklib.extract_table_region(text, ("<!--t:start-->", "<!--t:end-->"))
        assert lines == ["| A | B |", "|---|---|", "| 1 | 2 |"]

    @pytest.mark.parametrize(
        "body",
        [
            "没有 marker",
            "<!--t:start-->\n非表格文本\n<!--t:end-->",
            "<!--t:start-->\n| A |\n说明夹在中间\n| B |\n<!--t:end-->",
            "<!--t:start-->\n| A |\n| B |\n<!--t:end-->",
        ],
    )
    def test_extract_table_region_rejects_bad_shape(self, checklib, body):
        with pytest.raises(ValueError):
            checklib.extract_table_region(body, ("<!--t:start-->", "<!--t:end-->"))

    def test_replace_table_region(self, checklib):
        text = "前\n<!--t:start-->\n| A |\n|---|\n| 1 |\n<!--t:end-->\n后"
        updated = checklib.replace_table_region(text, ("<!--t:start-->", "<!--t:end-->"), ["| A |", "|---|", "| 9 |"])
        assert "| 9 |" in updated and "| 1 |" not in updated
        assert updated.startswith("前\n") and updated.endswith("\n后")

    def test_replace_table_region_missing_marker(self, checklib):
        with pytest.raises(ValueError):
            checklib.replace_table_region("无标记", ("<!--t:start-->", "<!--t:end-->"), ["| A |"])


# ═══ 共享排除模式 ═══


class TestTracesCommon:
    @pytest.mark.parametrize(
        "line",
        [
            "共 18 章",
            "章节数 17 章",
            "减至 16 章",
            "由 19 章精简至 17 章",
            "「18 章」",
            "出现第 3 章",
            "共 二十 章",
        ],
    )
    def test_chapter_counts_are_exempt(self, traces_common, line):
        assert traces_common._is_chapter_excluded(line) is True

    @pytest.mark.parametrize("line", ["见 5 章的实现", "第 3 章讲了数据源", "参考 12 章"])
    def test_chapter_references_not_exempt(self, traces_common, line):
        assert traces_common._is_chapter_excluded(line) is False

    @pytest.mark.parametrize(
        "line",
        ["共 21 轮", "21 轮每轮量化验收", "轮询超时", "行业轮动", "第 3 轮循环", "计划分 三 轮"],
    )
    def test_round_counts_and_runtime_terms_are_exempt(self, traces_common, line):
        assert traces_common._is_round_excluded(line) is True

    @pytest.mark.parametrize("line", ["第 5 轮迭代新增", "本轮完成 3 项"])
    def test_round_history_not_exempt(self, traces_common, line):
        assert traces_common._is_round_excluded(line) is False

    def test_compiled_lists_match_builders(self, traces_common):
        """模块级编译缓存须与构造函数结果一致（防两处漂移）。"""
        assert [p.pattern for p in traces_common._COMPILED_CHAPTER_EXCLUDE] == [
            p.pattern for p in traces_common._chapter_excludes()
        ]
        assert [p.pattern for p in traces_common._COMPILED_ROUND_EXCLUDE] == [
            p.pattern for p in traces_common._round_excludes()
        ]
