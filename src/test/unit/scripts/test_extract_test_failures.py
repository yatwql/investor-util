"""测试：失败用例提取脚本 — extract-test-failures.py

覆盖：
  - `_find_json_blob` 对含 HTML 实体引号的 data-jsonblob 能完整提取（回归场景：
    pytest-html 把 JSON 内引号编码为 ``&#34;``、日志内嵌 HTML 花括号，旧扫描器
    在 ``}`` 处提前截断导致 json.loads 报 "Extra data"）
  - 解码后 JSON 可解析，tests 条目可枚举
  - 报告无 data-jsonblob 时返回 None
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
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
def extract_script():
    return _load_script("extract-test-failures.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


class TestFindJsonBlob:
    """data-jsonblob 属性提取（rf-281 回归场景：HTML 实体引号导致 Extra data）。"""

    def test_extracts_blob_with_html_entities(self, extract_script):
        """含 &#34; 实体引号与内嵌 HTML 的 blob 能完整提取且 JSON 可解析。

        回归：旧实现用手工花括号扫描器，日志内嵌 HTML 的 ``}`` 会提前
        触发 depth==0 截断，json.loads 报 "Extra data"。
        """
        html = (
            '<div id="data-container" data-jsonblob="{&#34;tests&#34;: {'
            '&#34;a::t&#34;: [{ &#34;result&#34;: &#34;Failed&#34;, '
            '&#34;log&#34;: &#34;<pre>assert False</pre>&#34; }]}}"></div>'
        )
        blob = extract_script._find_json_blob(html)
        assert blob is not None
        data = json.loads(blob)  # 不应抛 Extra data
        tests = data.get("tests", {})
        assert "a::t" in tests
        assert tests["a::t"][0]["result"] == "Failed"
        assert "<pre>assert False</pre>" in tests["a::t"][0]["log"]

    def test_extracts_blob_with_nested_braces_in_log(self, extract_script):
        """日志内嵌花括号不干扰 JSON 提取（depth 逻辑废弃后自然通过）。"""
        html = (
            '<div data-jsonblob="{&#34;tests&#34;: {&#34;t&#34;: ['
            '{ &#34;result&#34;: &#34;Passed&#34;, '
            '&#34;log&#34;: &#34;{a: 1} {b: 2}&#34; }]}}"></div>'
        )
        blob = extract_script._find_json_blob(html)
        assert blob is not None
        data = json.loads(blob)
        assert data["tests"]["t"][0]["result"] == "Passed"

    def test_extracts_blob_with_nonexistent_blob_returns_none(self, extract_script):
        """报告无 data-jsonblob 属性时返回 None。"""
        assert extract_script._find_json_blob("<html>no blob</html>") is None

    def test_extracts_blob_with_unterminated_attribute_returns_none(self, extract_script):
        """data-jsonblob 属性无结束引号时返回 None（不崩溃）。"""
        # 正常情况：属性结束引号存在 → 可提取
        html_ok = '<div data-jsonblob="{&#34;a&#34;: 1}"></div>'
        blob_ok = extract_script._find_json_blob(html_ok)
        assert blob_ok is not None
        json.loads(blob_ok)
        # 缺失结束引号（data-jsonblob= 后无任何引号）→ 返回 None，不崩溃
        html_bad = '<div data-jsonblob="unterminated'
        assert extract_script._find_json_blob(html_bad) is None
