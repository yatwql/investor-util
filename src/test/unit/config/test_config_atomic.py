"""Config 原子写入断电恢复测试 — R-085。

测试目标：
  - set_config 使用 tempfile + os.replace 原子写入模式
  - 写入中途崩溃（模拟）→ 临时文件被清理，目标文件不受影响
  - Windows PermissionError → 降级 remove + rename 成功
  - 父目录自动创建
  - 写入内容与 JSON 格式正确

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_config_atomic -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_config]



class TestConfigAtomicWrite(unittest.TestCase):
    """测试 config.set() 的原子写入模式。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.python.config.get_config_path")
    def test_atomic_write_creates_config(self, mock_get_path):
        """set_config → 目标文件被原子写入。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config, get_config

        set_config("test_key", "hello")

        self.assertTrue(os.path.exists(self.config_path))
        with open(self.config_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["test_key"], "hello")

    @patch("src.python.config.get_config_path")
    def test_tmp_file_cleaned_after_write(self, mock_get_path):
        """写入完成后临时文件被清理。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config

        set_config("cleanup_key", 123)

        tmp_files = [f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0, "临时文件应在写入后被清理")

    @patch("src.python.config.get_config_path")
    def test_atomic_write_overwrites_existing(self, mock_get_path):
        """多次写入 → 内容被覆盖更新，config 文件不变。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config, get_config

        set_config("key_a", "first")
        set_config("key_b", "second")
        # 第二次写入不应丢失 key_a
        config = get_config()
        self.assertEqual(config.get("key_a"), "first")
        self.assertEqual(config.get("key_b"), "second")

    @patch("src.python.config.get_config_path")
    def test_atomic_write_preserves_other_keys(self, mock_get_path):
        """set_config 仅更新单个键，其他键不受影响。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config, get_config

        set_config("keep_me", "preserved")
        set_config("new_key", "added")
        config = get_config()
        self.assertEqual(config.get("keep_me"), "preserved")

    @patch("src.python.config.get_config_path")
    @patch("src.python.config.os.replace")
    def test_windows_permission_error_raises(self, mock_replace, mock_get_path):
        """Windows PermissionError → config.set_config 向上抛（异常由外层处理）。

        config.py 的 set_config 本身无 PermissionError 降级逻辑，
        异常被捕获后清理临时文件然后重新抛出。
        """
        mock_get_path.return_value = self.config_path
        # 先正常写入一个文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"original": True}, f)

        config_path = self.config_path

        # 模拟 os.replace 抛出 PermissionError
        def _replace_side_effect(src, dst):
            if dst == config_path:
                raise PermissionError("被其他进程锁定")
            return None

        mock_replace.side_effect = _replace_side_effect

        from src.python.config import set_config

        # 应抛出异常（PermissionError 被 except Exception 捕获后重新抛）
        with self.assertRaises(Exception):
            set_config("key_after_lock", "recovered")

        # 验证临时文件被清理，原文件不受影响
        tmp_files = [f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0, "失败后临时文件应被清理")
        self.assertTrue(os.path.exists(self.config_path), "原文件应保留")
        with open(self.config_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload.get("original"), True)

    @patch("src.python.config.get_config_path")
    def test_set_config_valid_json(self, mock_get_path):
        """写入的 config.json 格式合法（ensure_ascii=False, indent=2）。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config

        set_config("中文键", "中文值")
        set_config("number", 42)

        with open(self.config_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 验证中文未转义
        self.assertIn("中文键", content)
        self.assertIn("中文值", content)
        # 验证缩进
        self.assertIn("  ", content)  # indent=2
        # 验证可解析
        payload = json.loads(content)
        self.assertEqual(payload["中文键"], "中文值")
        self.assertEqual(payload["number"], 42)


class TestConfigAtomicWriteFailure(unittest.TestCase):
    """set_config 写入失败场景测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.python.config.get_config_path")
    @patch("src.python.config.tempfile.mkstemp")
    def test_mkstemp_failure_raised(self, mock_mkstemp, mock_get_path):
        """tempfile.mkstemp 失败 → 异常向外传播。"""
        mock_get_path.return_value = self.config_path
        mock_mkstemp.side_effect = OSError("磁盘空间不足")
        from src.python.config import set_config

        with self.assertRaises(OSError):
            set_config("fail_key", "value")

    @patch("src.python.config.get_config_path")
    @patch("src.python.config.tempfile.mkstemp")
    def test_temp_file_cleaned_on_exception(self, mock_mkstemp, mock_get_path):
        """mkstemp 成功但后续写入失败 → 临时文件被清理。"""
        mock_get_path.return_value = self.config_path
        # mkstemp 返回一个不存在的 fd → 后续写入失败
        mock_mkstemp.return_value = (999, os.path.join(self.tmp.name, "bad.tmp"))

        from src.python.config import set_config, _config_cache

        _config_cache = None
        with self.assertRaises(Exception):
            set_config("partial", "data")

        # 临时文件应被清理
        tmp_files = [f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0, "失败后临时文件应被清理")

    @patch("src.python.config.get_config_path")
    def test_empty_config_dir_created(self, mock_get_path):
        """config 父目录不存在 → 自动创建。"""
        nested_path = os.path.join(self.tmp.name, "subdir", "nested", "config.json")
        mock_get_path.return_value = nested_path
        from src.python.config import set_config

        set_config("nested_key", "created")

        self.assertTrue(os.path.exists(nested_path))
        with open(nested_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["nested_key"], "created")


class TestConfigCacheInvalidation(unittest.TestCase):
    """set_config 后缓存失效测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.python.config.get_config_path")
    def test_get_config_reflects_latest_set(self, mock_get_path):
        """set_config 后 get_config 返回最新值。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config, get_config

        set_config("key", "initial")
        self.assertEqual(get_config().get("key"), "initial")

        set_config("key", "updated")
        self.assertEqual(get_config().get("key"), "updated")

    @patch("src.python.config.get_config_path")
    def test_config_mtime_change_detected(self, mock_get_path):
        """外部修改 config.json → get_config 重新读取。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config, get_config


        set_config("ext", "original")
        self.assertEqual(get_config().get("ext"), "original")

        # 模拟外部直接写文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"ext": "external_modified"}, f)

        # 缓存 mtime 变化 → 重新读取
        config = get_config()
        self.assertEqual(config.get("ext"), "external_modified")


class TestConfigAtomicWriteConcurrency(unittest.TestCase):
    """set_config 并发安全与断电恢复场景。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.python.config.get_config_path")
    def test_concurrent_set_config_thread_safe(self, mock_get_path):
        """多个线程同时 set_config → 不损坏文件（Windows 允许部分线程失败）。"""
        mock_get_path.return_value = self.config_path
        from src.python.config import set_config
        import threading
        import json

        # 先初始化一个有效配置
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"base": 0}, f)

        n_threads = 10
        results = {}
        lock = threading.Lock()

        def _writer(idx):
            try:
                set_config(f"thread_{idx}", idx)
                with lock:
                    results[idx] = "ok"
            except Exception as e:
                with lock:
                    results[idx] = str(e)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 最终文件必须为有效 JSON（核心断言）
        with open(self.config_path, "r", encoding="utf-8") as f:
            final = json.load(f)

        # 无临时文件残留
        tmp_files = [f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0, "并发写入后无临时文件残留")

        # 成功写入的 key 均可在文件中找到
        for i in range(n_threads):
            if results[i] == "ok":
                self.assertEqual(final.get(f"thread_{i}"), i,
                                 f"成功写入的线程 {i} 的值应持久化到文件")
            else:
                # Windows 上部分线程可能因 PermissionError 失败——属正常竞争而非文件损坏
                self.assertIn("WinError", results[i],  # noqa: SIM300  # Windows specific
                              f"失败应为权限错误而非文件损坏: {results[i]}")

    @patch("src.python.config.get_config_path")
    def test_power_failure_during_replace(self, mock_get_path):
        """模拟断电：os.replace 抛出异常 → 原文件完整，无临时文件残留。"""
        mock_get_path.return_value = self.config_path
        import json

        # 先创建原始配置
        from src.python.config import set_config
        set_config("original_key", "original_value")

        with open(self.config_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        # 模拟 os.replace 断电失败
        with patch("src.python.config.os.replace",
                   side_effect=OSError("Power failure simulated")):
            with self.assertRaises(OSError):
                set_config("new_key", "new_value")

        # 临时文件已被清理
        tmp_files = [f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0, "断电后临时文件应被清理")

        # 磁盘文件完好不变（验证文件内容，非 get_config 缓存——缓存可能已被内存修改）
        with open(self.config_path, "r", encoding="utf-8") as f:
            after_content = f.read()
        self.assertEqual(after_content, original_content, "磁盘文件应在断电后保持不变")
        self.assertNotIn("new_key", after_content, "断电后磁盘文件不应含新数据")

    @patch("src.python.config.get_config_path")
    def test_partial_write_after_replace_failure(self, mock_get_path):
        """os.replace 写入失败（如磁盘满）→ 恢复旧文件内容。"""
        mock_get_path.return_value = self.config_path
        import json

        from src.python.config import set_config, get_config
        # 建立初始状态
        set_config("key_a", "value_a")
        set_config("key_b", "value_b")

        # json.dump 写入临时文件成功，但 os.replace 失败
        replace_attempts = [0]

        def _failing_replace(src, dst):
            replace_attempts[0] += 1
            raise OSError("Disk full")

        with patch("src.python.config.os.replace", side_effect=_failing_replace):
            with self.assertRaises(OSError):
                set_config("key_a", "overwritten")

        # 原文件应仍为旧值
        with open(self.config_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        self.assertEqual(content.get("key_a"), "value_a")
        self.assertEqual(content.get("key_b"), "value_b")
        self.assertEqual(replace_attempts[0], 1)


if __name__ == "__main__":
    unittest.main()
