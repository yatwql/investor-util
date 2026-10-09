"""测试：三守护结论缓存（doc-traces / semantic-index / doc-links）— 输入未变复用结论。

设计边界（质量前提：本地降频不降级）：
  - 通过与发现都缓存——输入字节未变 ⇒ 结论必然相同；
  - 失效方向永远偏向全量：逻辑版本 / 文件集 / 逐文件指纹任一失配即重算；
  - 缓存只作加速不是真值：损坏按未命中处理、写入失败静默。

核心回归：--ci 模式下「冷（全量）」与「热（回放）」的 stdout 与退出码必须
逐字一致——结论缓存只是省重复计算，不得改变任何检查结论。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from src.test._script_loader import load_script

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]

#: 参与结论缓存的守护（脚本名，不含 .py）
_CACHED_GUARDS = ("check-doc-traces", "check-semantic-index", "check-doc-links")


def _run_guard(name: str, cache_dir: Path) -> tuple[int, str]:
    """以 --ci 运行守护（缓存目录显式指向 cache_dir），返回 (退出码, stdout)。"""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / f"{name}.py"), "--ci"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=_REPO_ROOT,
        env={**os.environ, "CHECK_CONCLUSION_CACHE_DIR": str(cache_dir)},
    )
    return proc.returncode, proc.stdout


class TestGuardConclusionReplay:
    """冷（全量）与热（回放）输出逐字一致——结论缓存不改变任何检查结论。"""

    @pytest.mark.parametrize("guard", _CACHED_GUARDS)
    def test_ci_output_identical_between_full_and_cache_hit(self, tmp_path, guard):
        """两次运行（首跑冷全量建缓存、二跑命中回放）stdout 与退出码必须完全相同。"""
        cache_dir = tmp_path / "guard_conclusions"
        rc_full, out_full = _run_guard(guard, cache_dir)
        rc_hit, out_hit = _run_guard(guard, cache_dir)
        assert list(cache_dir.glob("*.json")), "首跑必须写出结论缓存文件"
        assert rc_hit == rc_full, "缓存命中不得改变退出码（结论同源）"
        assert out_hit == out_full, "缓存命中输出必须与全量逐字一致"


class TestConclusionCacheHelper:
    """结论缓存原语：命中/失配矩阵 + 通过与发现都缓存 + 隔离重定向。"""

    @staticmethod
    def _inputs(tmp_path: Path) -> tuple[Path, Path]:
        doc = tmp_path / "doc.md"
        doc.write_text("正文\n", encoding="utf-8")
        logic = tmp_path / "guard_logic.py"
        logic.write_text("# v1\n", encoding="utf-8")
        return doc, logic

    def test_roundtrip_pass_conclusion_cached(self, monkeypatch, tmp_path):
        """空 findings（通过结论）保存后可原样回放。"""
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        monkeypatch.setenv("CHECK_CONCLUSION_CACHE_DIR", str(tmp_path / "cache"))
        doc, logic = self._inputs(tmp_path)
        mod.conclusion_cache_save("ns_pass", [logic], [doc], {"findings": []})
        assert mod.conclusion_cache_load("ns_pass", [logic], [doc]) == {"findings": []}

    def test_roundtrip_findings_conclusion_cached(self, monkeypatch, tmp_path):
        """非空 findings（发现结论）与附带回放字段同样缓存——不只缓存通过。"""
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        monkeypatch.setenv("CHECK_CONCLUSION_CACHE_DIR", str(tmp_path / "cache"))
        doc, logic = self._inputs(tmp_path)
        mod.conclusion_cache_save("ns_fail", [logic], [doc], {"findings": ["a.md:1 痕迹", "b.md:2 痕迹"], "total": 2})
        got = mod.conclusion_cache_load("ns_fail", [logic], [doc])
        assert got is not None
        assert got["findings"] == ["a.md:1 痕迹", "b.md:2 痕迹"]
        assert got["total"] == 2

    def test_input_content_change_misses(self, monkeypatch, tmp_path):
        """输入文件时间戳/内容变化 → 必失配（全量重算）。"""
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        monkeypatch.setenv("CHECK_CONCLUSION_CACHE_DIR", str(tmp_path / "cache"))
        doc, logic = self._inputs(tmp_path)
        mod.conclusion_cache_save("ns_a", [logic], [doc], {"findings": []})
        assert mod.conclusion_cache_load("ns_a", [logic], [doc]) is not None
        os.utime(doc, ns=(1, 1))
        assert mod.conclusion_cache_load("ns_a", [logic], [doc]) is None

    def test_input_file_set_change_misses(self, monkeypatch, tmp_path):
        """输入文件集增删 → 必失配（新增/删除文件改变扫描面）。"""
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        monkeypatch.setenv("CHECK_CONCLUSION_CACHE_DIR", str(tmp_path / "cache"))
        doc, logic = self._inputs(tmp_path)
        mod.conclusion_cache_save("ns_b", [logic], [doc], {"findings": []})
        extra = tmp_path / "extra.md"
        extra.write_text("新文档\n", encoding="utf-8")
        assert mod.conclusion_cache_load("ns_b", [logic], [doc, extra]) is None
        assert mod.conclusion_cache_load("ns_b", [logic], []) is None

    def test_logic_change_misses(self, monkeypatch, tmp_path):
        """收集逻辑（脚本字节）变化 → 必失配（结论随逻辑版本失效）。"""
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        monkeypatch.setenv("CHECK_CONCLUSION_CACHE_DIR", str(tmp_path / "cache"))
        doc, logic = self._inputs(tmp_path)
        mod.conclusion_cache_save("ns_c", [logic], [doc], {"findings": []})
        logic.write_text("# v2 changed\n", encoding="utf-8")
        assert mod.conclusion_cache_load("ns_c", [logic], [doc]) is None

    def test_corrupt_cache_is_miss(self, monkeypatch, tmp_path):
        """缓存文件损坏/结构非法 → 按未命中处理（全量重算），不得抛异常。"""
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        monkeypatch.setenv("CHECK_CONCLUSION_CACHE_DIR", str(tmp_path / "cache"))
        doc, logic = self._inputs(tmp_path)
        path = mod.conclusion_cache_dir() / "ns_d.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json", encoding="utf-8")
        assert mod.conclusion_cache_load("ns_d", [logic], [doc]) is None
        # 结构合法但 findings 非列表 → 同样拒收
        payload = {
            "logic": mod._logic_fingerprint([logic]),
            "inputs": mod._input_fingerprint([doc]),
            "conclusion": {"findings": "not-a-list"},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        assert mod.conclusion_cache_load("ns_d", [logic], [doc]) is None

    def test_isolation_fixture_redirects_cache_dir(self, tmp_path):
        """测试隔离：结论缓存目录必须被 autouse 夹具重定向到 tmp_path。"""
        env = os.environ.get("CHECK_CONCLUSION_CACHE_DIR", "")
        assert env.startswith(str(tmp_path))
        assert "guard_conclusions" in env
