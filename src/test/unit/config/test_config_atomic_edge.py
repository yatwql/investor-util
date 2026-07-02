"""Config 原子写入并发与断电恢复测试 — edge 专项。

从 test_config_atomic.py 提取的 edge 场景：
  - 多线程并发写入文件完整性
  - os.replace 断电模拟
  - 部分写入后恢复旧文件

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/config/test_config_atomic_edge.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_config, pytest.mark.edge]


@pytest.mark.edge
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
