"""Web server.py 启动防护测试 — output_dir 写锁检测。

覆盖：锁文件路径定位 / 存在性判断 / 原子抢占（O_EXCL 排他）/ 释放 /
入口级 ensure_output_dir_lock 的获取与「被其他入口占用则警告」语义。
"""

from __future__ import annotations

import logging
import os

import pytest

from src.python.web import server

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _touch(path: str) -> None:
    """创建空文件（模拟已存在的锁文件）。"""
    with open(path, "w", encoding="utf-8"):
        pass


class TestOutputDirLockPath:
    """锁文件路径定位：点文件名挂在 output_dir 下。"""

    def test_path_is_dotfile_under_output_dir(self, tmp_path):
        expected = str(tmp_path / server.OUTPUT_DIR_LOCK_FILE)
        assert server._output_dir_lock_path(str(tmp_path)) == expected


class TestIsOutputDirLocked:
    """存在性判断：无锁文件 False，有锁文件 True。"""

    def test_not_locked_without_lock_file(self, tmp_path):
        assert server._is_output_dir_locked(str(tmp_path)) is False

    def test_locked_when_lock_file_present(self, tmp_path):
        _touch(str(tmp_path / server.OUTPUT_DIR_LOCK_FILE))
        assert server._is_output_dir_locked(str(tmp_path)) is True


class TestAcquireRelease:
    """原子抢占与释放。"""

    def test_acquire_creates_lock_file_and_returns_path(self, tmp_path):
        lock_path = server._acquire_output_dir_lock(str(tmp_path))
        assert lock_path is not None
        assert os.path.basename(lock_path) == server.OUTPUT_DIR_LOCK_FILE
        assert os.path.exists(lock_path)

    def test_acquire_is_exclusive_second_call_returns_none(self, tmp_path):
        first = server._acquire_output_dir_lock(str(tmp_path))
        assert first is not None
        second = server._acquire_output_dir_lock(str(tmp_path))
        assert second is None
        # 既有锁文件未被覆盖/改动
        assert os.path.exists(first)

    def test_release_removes_lock_file(self, tmp_path):
        lock_path = server._acquire_output_dir_lock(str(tmp_path))
        assert lock_path is not None
        server._release_output_dir_lock(lock_path)
        assert not os.path.exists(lock_path)

    def test_release_missing_file_is_noop(self, tmp_path):
        # 删除不存在的锁文件不抛异常（崩溃残留/已手动清理场景）
        server._release_output_dir_lock(str(tmp_path / server.OUTPUT_DIR_LOCK_FILE))

    def test_acquire_blocked_by_undir_file_returns_none(self, tmp_path):
        # output_dir 位置被普通文件占据（os.makedirs 抛 FileExistsError）→ 返回 None 不抛
        blocker = tmp_path / "blocked"
        blocker.write_text("", encoding="utf-8")
        assert server._acquire_output_dir_lock(str(blocker)) is None


class TestEnsureOutputDirLock:
    """入口级锁获取：空闲获取 / 被占用告警（不阻塞启动）。"""

    def test_acquires_when_free_and_releases(self, tmp_path):
        lock_path = server.ensure_output_dir_lock(str(tmp_path))
        assert lock_path is not None
        assert os.path.exists(lock_path)
        server._release_output_dir_lock(lock_path)
        assert not os.path.exists(lock_path)

    def test_warns_when_lock_held_by_other_entry(self, tmp_path, caplog):
        lock_file = str(tmp_path / server.OUTPUT_DIR_LOCK_FILE)
        _touch(lock_file)
        with caplog.at_level(logging.WARNING, logger="invest"):
            lock_path = server.ensure_output_dir_lock(str(tmp_path))
        assert lock_path is None
        assert "该输出目录可能正被其他入口占用，产物可能互相覆盖" in caplog.text
        # 不阻塞启动：既有锁文件保持原样
        assert os.path.exists(lock_file)

    def test_warns_when_output_dir_not_writable(self, tmp_path, caplog):
        # output_dir 不可创建（位置被文件占据）→ 告警但不阻塞启动
        blocker = tmp_path / "blocked"
        blocker.write_text("", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="invest"):
            lock_path = server.ensure_output_dir_lock(str(blocker))
        assert lock_path is None
        assert "写锁创建失败" in caplog.text
