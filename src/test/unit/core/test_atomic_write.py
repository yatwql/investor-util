"""原子写入原语 — 单元测试。

覆盖：文本/JSON 原子写入（新建、覆盖、父目录自动创建、缩进形态）、
失败语义（**不抛出**、如实返回布尔、旧内容原样保留、临时文件不残留）、
序列化失败、以及 Windows 占用回退路径 `_replace`。

本原语是缓存原子写入约束的唯一实现，各调用点（jsonl_store / 熔断状态 /
持仓快照 / 静默期 / 断路状态 / 降级状态 / 功能开关覆写）以返回布尔判定后续
动作，故「失败返回 False 且不抛」是契约的一部分，需单独锁定。

运行：
  pytest src/test/unit/core/test_atomic_write.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from src.python.core import atomic_write as aw
from src.python.core.atomic_write import write_json_atomic, write_text_atomic

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestWriteTextAtomic:
    """write_text_atomic 正常路径。"""

    def test_creates_file_with_content(self, tmp_path):
        """目标文件不存在 → 创建并写入内容。"""
        target = tmp_path / "state.json"

        assert write_text_atomic(str(target), '{"a": 1}') is True
        assert target.read_text(encoding="utf-8") == '{"a": 1}'

    def test_creates_parent_dirs(self, tmp_path):
        """父目录不存在 → 自动逐层创建。"""
        target = tmp_path / "nested" / "deep" / "state.json"

        assert write_text_atomic(str(target), "x") is True
        assert target.read_text(encoding="utf-8") == "x"

    def test_overwrites_existing_content(self, tmp_path):
        """已存在文件 → 整份替换（非追加）。"""
        target = tmp_path / "state.json"
        target.write_text("old", encoding="utf-8")

        assert write_text_atomic(str(target), "new") is True
        assert target.read_text(encoding="utf-8") == "new"

    def test_no_temp_file_left_behind(self, tmp_path):
        """成功路径不留临时文件（同目录仅剩目标文件）。"""
        target = tmp_path / "state.json"

        write_text_atomic(str(target), "x", prefix=".probe_")

        assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


class TestWriteTextAtomicFailure:
    """write_text_atomic 失败路径 — 不抛出、返回 False、旧内容保留。"""

    def test_mkstemp_failure_returns_false(self, tmp_path):
        """临时文件创建失败 → 返回 False，不向上抛。"""
        target = tmp_path / "state.json"

        with patch.object(tempfile, "mkstemp", side_effect=OSError("boom")):
            assert write_text_atomic(str(target), "x") is False

        assert not target.exists()

    def test_write_failure_returns_false_and_keeps_old_content(self, tmp_path):
        """写临时文件失败 → 返回 False，目标文件保持旧内容（无半写态）。"""
        target = tmp_path / "state.json"
        target.write_text("old", encoding="utf-8")

        with patch("os.replace", side_effect=OSError("boom")):
            assert write_text_atomic(str(target), "new") is False

        assert target.read_text(encoding="utf-8") == "old"

    def test_temp_file_cleaned_on_failure(self, tmp_path):
        """失败路径清理临时文件，不留残骸。"""
        target = tmp_path / "state.json"

        with patch("os.replace", side_effect=OSError("boom")):
            assert write_text_atomic(str(target), "new", prefix=".probe_") is False

        assert not [p for p in tmp_path.iterdir() if p.name.startswith(".probe_")]


class TestWriteJsonAtomic:
    """write_json_atomic — 序列化 + 委托文本写入。"""

    def test_writes_json_with_indent(self, tmp_path):
        """默认 indent=2：落盘为多行 JSON。"""
        target = tmp_path / "state.json"

        assert write_json_atomic(str(target), {"a": 1, "b": [2]}) is True
        assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": [2]}
        assert target.read_text(encoding="utf-8").count("\n") > 1

    def test_compact_mode_keeps_single_line(self, tmp_path):
        """indent=None → 紧凑单行（降级状态等高频写盘用）。"""
        target = tmp_path / "state.json"

        assert write_json_atomic(str(target), {"a": 1}, indent=None) is True
        assert target.read_text(encoding="utf-8").count("\n") == 0

    def test_non_serializable_returns_false(self, tmp_path):
        """不可序列化对象 → 返回 False，不抛 TypeError。"""
        target = tmp_path / "state.json"

        assert write_json_atomic(str(target), {"a": object()}) is False

        assert not target.exists()

    def test_keeps_existing_file_on_replace_failure(self, tmp_path):
        """替换失败 → 返回 False，旧 JSON 原样可读。"""
        target = tmp_path / "state.json"
        target.write_text('{"old": true}', encoding="utf-8")

        with patch("os.replace", side_effect=OSError("boom")):
            assert write_json_atomic(str(target), {"new": True}) is False

        assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}


class TestReplaceWindowsFallback:
    """_replace 的 Windows 占用回退（PermissionError → 删除后改名）。"""

    def test_permission_error_falls_back_to_rename(self, tmp_path):
        """os.replace 抛 PermissionError 且目标存在 → 删目标后 os.rename 成功。"""
        target = tmp_path / "state.json"
        target.write_text("old", encoding="utf-8")

        real_replace = os.replace
        calls = {"n": 0}

        def _fake_replace(src, dst):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("被占用")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=_fake_replace):
            assert write_text_atomic(str(target), "new") is True

        assert target.read_text(encoding="utf-8") == "new"
        assert calls["n"] == 1  # 回退走 os.rename，未二次调用 os.replace


class TestWriteBytesAtomic:
    """write_bytes_atomic —— 二进制原子写（rf：原子写唯一原语补齐后注册用例）。"""

    def test_writes_bytes_and_creates_parents(self, tmp_path):
        target = tmp_path / "dir" / "a.bin"
        assert aw.write_bytes_atomic(str(target), b"\x00\xff\x01") is True
        assert target.read_bytes() == b"\x00\xff\x01"

    def test_mode_applied(self, tmp_path):
        target = tmp_path / "a.bin"
        assert aw.write_bytes_atomic(str(target), b"x", mode=0o644) is True
        assert os.stat(target).st_mode & 0o777 == 0o644

    def test_no_mode_keeps_mkstemp_default(self, tmp_path):
        target = tmp_path / "a.bin"
        assert aw.write_bytes_atomic(str(target), b"x") is True
        assert os.stat(target).st_mode & 0o777 == 0o600  # mkstemp 默认

    def test_keeps_old_content_on_write_failure(self, tmp_path):
        target = tmp_path / "a.bin"
        target.write_bytes(b"old")
        import unittest.mock as mock

        with mock.patch.object(aw, "_replace", side_effect=RuntimeError("boom")):
            assert aw.write_bytes_atomic(str(target), b"new") is False
        assert target.read_bytes() == b"old"
        # 无 .tmp 残留
        assert list(tmp_path.glob("*.tmp")) == []


class TestCopyFileAtomic:
    """copy_file_atomic —— 原子复制（rf：4 处旁路收编为唯一原语）。"""

    def test_copies_content_and_metadata(self, tmp_path):
        src = tmp_path / "a.bin"
        src.write_bytes(b"payload")
        dst = tmp_path / "sub" / "b.bin"
        aw.copy_file_atomic(str(src), str(dst))
        assert dst.read_bytes() == b"payload"

    def test_temp_lives_in_dst_dir_and_cleaned(self, tmp_path, monkeypatch):
        src = tmp_path / "a.bin"
        src.write_bytes(b"payload")
        dst = tmp_path / "b.bin"
        seen: dict = {}

        import shutil as _sh

        real = _sh.copy2

        def spy_copy2(s, d, **kw):
            seen["tmp_dir"] = os.path.dirname(d)
            return real(s, d, **kw)

        # copy_file_atomic 内部经 module 级 shutil（自测点在其模块属性）
        monkeypatch.setattr(aw.shutil, "copy2", spy_copy2)
        aw.copy_file_atomic(str(src), str(dst))
        assert seen["tmp_dir"] == str(tmp_path)
        assert list(tmp_path.glob("*.tmp")) == []

    def test_failure_cleans_tmp_and_raises(self, tmp_path, monkeypatch):
        src = tmp_path / "a.bin"
        src.write_bytes(b"payload")
        dst = tmp_path / "b.bin"
        monkeypatch.setattr(aw.shutil, "copy2", lambda s, d, **kw: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError):
            aw.copy_file_atomic(str(src), str(dst))
        assert not dst.exists()
        assert list(tmp_path.glob("*.tmp")) == []
