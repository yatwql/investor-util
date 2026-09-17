"""JSONL 事件存储原语 — 单元测试。

覆盖：原子追加（新建/续写/多行载荷）、容错读取（缺失文件/空档/损坏行/非对象行）、
目录自动创建、临时文件不残留、以及原语抽取后 `perf` / `decision_ledger` 委托路径
行为逐字不变（前缀与日志标签由调用方保持原值）。

运行：
  pytest src/test/unit/core/test_jsonl_store.py -v
"""

from __future__ import annotations

import json
import os

import pytest

from src.python.core.jsonl_store import append_jsonl_atomic, read_jsonl

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestAppendJsonlAtomic:
    """原子追加。"""

    def test_creates_parent_dirs_and_file(self, tmp_path):
        target = tmp_path / "nested" / "deep" / "events.jsonl"

        append_jsonl_atomic(str(target), '{"a": 1}\n')

        assert target.is_file()
        assert read_jsonl(str(target)) == [{"a": 1}]

    def test_appends_without_truncating_existing(self, tmp_path):
        target = tmp_path / "events.jsonl"
        append_jsonl_atomic(str(target), '{"a": 1}\n')
        append_jsonl_atomic(str(target), '{"a": 2}\n')

        assert read_jsonl(str(target)) == [{"a": 1}, {"a": 2}]

    def test_multi_line_payload_appends_all_lines(self, tmp_path):
        """批量写入：一次调用追加多行（signal_ledger 批量入账依赖此能力）。"""
        target = tmp_path / "events.jsonl"
        payload = '{"a": 1}\n{"a": 2}\n{"a": 3}\n'

        append_jsonl_atomic(str(target), payload)

        assert read_jsonl(str(target)) == [{"a": 1}, {"a": 2}, {"a": 3}]

    def test_bare_filename_without_dirname(self, tmp_path, monkeypatch):
        """无目录成分的裸文件名路径亦可正常写入（父目录为空时不建目录）。"""
        monkeypatch.chdir(tmp_path)

        append_jsonl_atomic("events.jsonl", '{"a": 1}\n')

        assert read_jsonl("events.jsonl") == [{"a": 1}]

    def test_no_tmp_file_left_behind(self, tmp_path):
        target = tmp_path / "events.jsonl"

        append_jsonl_atomic(str(target), '{"a": 1}\n', prefix=".probe_")

        leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".probe_")]
        assert leftovers == []

    def test_returns_true_on_success(self, tmp_path):
        assert append_jsonl_atomic(str(tmp_path / "events.jsonl"), '{"a": 1}\n') is True

    def test_returns_false_and_keeps_file_intact_when_replace_fails(self, tmp_path, monkeypatch):
        """原子替换失败 → 返回 False 且旧内容原样保留（不抛异常）。"""
        target = tmp_path / "events.jsonl"
        append_jsonl_atomic(str(target), '{"a": 1}\n')

        def _boom(*_args, **_kwargs):
            raise OSError("磁盘满")

        monkeypatch.setattr(os, "replace", _boom)

        assert append_jsonl_atomic(str(target), '{"a": 2}\n') is False
        assert read_jsonl(str(target)) == [{"a": 1}]

    def test_returns_false_when_tempfile_creation_fails(self, tmp_path, monkeypatch):
        """临时文件都建不出来（目录只读/磁盘满）→ 返回 False，不抛异常。

        此路径曾因 `mkstemp` 失败后仍去 `os.remove(tmp_path)` 而抛 NameError。
        """
        import tempfile as _tempfile

        def _boom(*_args, **_kwargs):
            raise OSError("磁盘满")

        monkeypatch.setattr(_tempfile, "mkstemp", _boom)

        assert append_jsonl_atomic(str(tmp_path / "events.jsonl"), '{"a": 1}\n') is False


class TestReadJsonl:
    """容错读取。"""

    def test_missing_file_returns_empty(self, tmp_path):
        assert read_jsonl(str(tmp_path / "absent.jsonl")) == []

    def test_blank_lines_skipped(self, tmp_path):
        target = tmp_path / "events.jsonl"
        target.write_text('\n{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")

        assert read_jsonl(str(target)) == [{"a": 1}, {"a": 2}]

    def test_corrupt_line_skipped_without_losing_neighbours(self, tmp_path):
        target = tmp_path / "events.jsonl"
        target.write_text('{"a": 1}\n{not json\n{"a": 2}\n', encoding="utf-8")

        assert read_jsonl(str(target)) == [{"a": 1}, {"a": 2}]

    def test_non_object_line_skipped(self, tmp_path):
        """合法 JSON 但非对象（裸数组/标量）不算账本记录。"""
        target = tmp_path / "events.jsonl"
        target.write_text('[1, 2]\n"scalar"\n42\n{"a": 1}\n', encoding="utf-8")

        assert read_jsonl(str(target)) == [{"a": 1}]


class TestDelegationPreservesBehaviour:
    """原语抽取后，既有调用点委托路径行为不变。"""

    def test_perf_helper_delegates(self, tmp_path):
        from src.python.core import perf

        target = tmp_path / "perf_history.jsonl"
        line = json.dumps({"version": "x"}, ensure_ascii=False) + "\n"

        perf._append_jsonl_atomic(str(target), line)

        assert json.loads(target.read_text(encoding="utf-8").strip()) == {"version": "x"}

    def test_decision_ledger_roundtrip_delegates(self, tmp_path):
        from src.python.core import decision_ledger as dl

        target = tmp_path / "decision_ledger.jsonl"
        dl._append_event_atomic({"event": "decision", "code": "600000"}, path=str(target))

        assert dl.load_events(path=str(target)) == [{"event": "decision", "code": "600000"}]

    def test_decision_ledger_serialization_still_sorted_and_unquoted(self, tmp_path):
        """委托不改序列化口径：键排序 + ensure_ascii=False（中文原样落盘）。"""
        from src.python.core import decision_ledger as dl

        target = tmp_path / "decision_ledger.jsonl"
        dl._append_event_atomic({"z": 1, "a": "减仓"}, path=str(target))

        raw = target.read_text(encoding="utf-8").strip()
        assert raw == '{"a": "减仓", "z": 1}'
