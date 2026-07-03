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
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
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

        # 至少部分线程写入成功（Windows 锁竞争允许部分失败）
        ok_count = sum(1 for i in range(n_threads) if results[i] == "ok")
        self.assertGreater(ok_count, 0, f"至少一个线程应成功写入 ({results})")

        # 初始 key 保持完整
        self.assertEqual(final.get("base"), 0, "初始 key 不应被覆盖")

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


# ── Y5: 配置/环境纵深 ─────────────────────────────────────────────


@pytest.mark.edge
class TestConfigEnvEdgeY5(unittest.TestCase):
    """Y5 配置/环境纵深测试：BOM/CRLF/api_key 空格/缺失嵌套键/并发 init_config。"""

    def setUp(self):
        self._orig_config = None
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        if self._orig_config is not None:
            import src.python.config as cfg
            cfg._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    # ── BOM 头 JSON ──

    def test_bom_config_json_readable(self):
        """含 UTF-8 BOM 的 config.json → 能被 get_config() 正常解析。"""
        import src.python.config as cfg
        self._orig_config = cfg._CONFIG_FILE
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

        # 用 utf-8-sig 写入（自动添加 BOM），内容不含
        raw = '{"holdings_dir": "data/holdings", "holdings_filename": "test.xlsx"}'
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8-sig") as f:
            f.write(raw)

        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "data/holdings")
        self.assertEqual(result["holdings_filename"], "test.xlsx")

    def test_bom_llm_settings_readable(self):
        """含 UTF-8 BOM 的 llm_settings.json → 能被 get_llm_config() 正常解析。"""
        import src.python.config as cfg
        settings_path = os.path.join(self.tmp.name, "llm_settings.json")
        key_path = os.path.join(self.tmp.name, "llm_key.json")

        # 用 utf-8-sig 写（自动添加 BOM），内容不含
        settings_raw = '{"temperature": 0.7, "max_tokens": 2048}'
        with open(settings_path, "w", encoding="utf-8-sig") as f:
            f.write(settings_raw)
        # llm_key.json 无 BOM
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"api_key": "sk-test", "provider": "claude"}, f)

        with patch("src.python.config.get_llm_settings_path", return_value=settings_path), \
             patch("src.python.config.get_llm_key_path", return_value=key_path):
            # 清缓存
            cfg._llm_config_cache = None
            result = cfg.get_llm_config()

        self.assertIsNotNone(result)
        self.assertEqual(result.get("temperature"), 0.7)

    # ── CRLF 行尾 ──

    def test_crlf_llm_settings_with_comments(self):
        """CRLF 行尾 + 注释的 llm_settings.json → 正常解析。"""
        import src.python.config as cfg
        settings_path = os.path.join(self.tmp.name, "llm_settings.json")
        key_path = os.path.join(self.tmp.name, "llm_key.json")

        # CRLF 行尾 + 注释
        settings_raw = (
            "{\r\n"
            '  // 温度参数\r\n'
            '  "temperature": 0.7,\r\n'
            '  /* 注释块 */\r\n'
            '  "max_tokens": 2048\r\n'
            "}\r\n"
        )
        with open(settings_path, "w", encoding="utf-8", newline="") as f:
            f.write(settings_raw)
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"api_key": "sk-test", "provider": "claude"}, f)

        with patch("src.python.config.get_llm_settings_path", return_value=settings_path), \
             patch("src.python.config.get_llm_key_path", return_value=key_path):
            cfg._llm_config_cache = None
            result = cfg.get_llm_config()

        self.assertIsNotNone(result)
        self.assertEqual(result.get("temperature"), 0.7)
        self.assertEqual(result.get("max_tokens"), 2048)

    # ── api_key 空格 ──

    def test_api_key_whitespace_stripped(self):
        """api_key 含首尾空格 → 被 strip 后再用于 API 调用。"""
        import src.python.config as cfg
        settings_path = os.path.join(self.tmp.name, "llm_settings.json")
        key_path = os.path.join(self.tmp.name, "llm_key.json")

        # 写带空格的 api_key
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"temperature": 0.7}, f)
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"api_key": "  sk-test-with-spaces  ", "provider": "claude"}, f)

        with patch("src.python.config.get_llm_settings_path", return_value=settings_path), \
             patch("src.python.config.get_llm_key_path", return_value=key_path):
            cfg._llm_config_cache = None
            result = cfg.get_llm_config()

        self.assertIsNotNone(result)
        self.assertEqual(result["api_key"], "sk-test-with-spaces",
                         "api_key 首尾空格应被去除")

    def test_api_key_whitespace_in_settings_only(self):
        """仅 llm_settings.json 含 api_key 且有空格 → 被 strip。"""
        import src.python.config as cfg
        settings_path = os.path.join(self.tmp.name, "llm_settings.json")

        # 仅 llm_settings.json 有 api_key（无 llm_key.json）
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"api_key": "\t sk-ant-from-settings \n", "temperature": 0.7}, f)

        with patch("src.python.config.get_llm_settings_path", return_value=settings_path), \
             patch("src.python.config.get_llm_key_path", return_value=os.path.join(self.tmp.name, "llm_key_not_exists.json")):
            cfg._llm_config_cache = None
            result = cfg.get_llm_config()

        self.assertIsNotNone(result)
        self.assertEqual(result["api_key"], "sk-ant-from-settings",
                         "settings 中的 api_key 也应被 strip")

    # ── 缺失嵌套键 ──

    def test_missing_pricing_still_returns_config(self):
        """llm_settings.json 缺失 pricing 段 → get_llm_config() 仍返回有效配置。"""
        import src.python.config as cfg
        settings_path = os.path.join(self.tmp.name, "llm_settings.json")
        key_path = os.path.join(self.tmp.name, "llm_key.json")

        # 无 pricing 段
        min_settings = {"temperature": 0.5, "max_tokens": 1024}
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(min_settings, f)
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"api_key": "sk-test", "provider": "openai"}, f)

        with patch("src.python.config.get_llm_settings_path", return_value=settings_path), \
             patch("src.python.config.get_llm_key_path", return_value=key_path):
            cfg._llm_config_cache = None
            result = cfg.get_llm_config()

        self.assertIsNotNone(result)
        self.assertEqual(result.get("temperature"), 0.5)
        # pricing 缺失不应导致异常
        self.assertNotIn("pricing", result)

    def test_missing_system_prompt_still_works(self):
        """llm_settings.json 缺失所有 system_prompt_* → 生成时回退内置默认值。"""
        import src.python.config as cfg
        settings_path = os.path.join(self.tmp.name, "llm_settings.json")
        key_path = os.path.join(self.tmp.name, "llm_key.json")

        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"temperature": 0.7}, f)
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"api_key": "sk-test", "provider": "claude"}, f)

        with patch("src.python.config.get_llm_settings_path", return_value=settings_path), \
             patch("src.python.config.get_llm_key_path", return_value=key_path):
            cfg._llm_config_cache = None
            result = cfg.get_llm_config()

        self.assertIsNotNone(result)
        # system_prompt_* 不应在配置中
        self.assertNotIn("system_prompt_global_macro", result)

    # ── 并发 init_config ──

    def test_concurrent_init_config_no_crash(self):
        """config.json 缺失时双线程同时 init_config() → 不崩溃。"""
        import src.python.config as cfg
        self._orig_config = cfg._CONFIG_FILE
        config_path = os.path.join(self.tmp.name, "config.json")
        cfg._CONFIG_FILE = config_path

        import threading
        errors = []

        def _init():
            try:
                cfg.init_config()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_init) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发 init_config 不应抛出异常: {errors}")
        self.assertTrue(os.path.exists(config_path), "配置文件应被创建")

        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("holdings_dir"), "data/holdings")

    # ── 终端无颜色 ──

    def test_no_color_env_suppresses_ansi(self):
        """NO_COLOR 环境变量设置时，_show_llm_config_status 输出不含 ANSI 转义。"""
        import src.python.tui_menu as tui

        # 模拟非 TTY stdout + NO_COLOR
        with patch("sys.stdout.isatty", return_value=False), \
             patch.dict(os.environ, {"NO_COLOR": "1"}), \
             patch("src.python.tui_menu.get_llm_config",
                   return_value={"api_key": "sk-test", "provider": "claude"}):
            with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
                tui._show_llm_config_status()
                for call_args, _ in mock_stdout.write.call_args_list:
                    text = call_args[0] if isinstance(call_args[0], str) else str(call_args[0])
                    self.assertNotIn("\033[", text,
                                     f"NO_COLOR 下输出不应含 ANSI 转义: {text[:50]!r}")

    def test_no_color_env_unconfigured_ansi_suppressed(self):
        """NO_COLOR + 未配置 LLM → 输出不含 ANSI 转义。"""
        import src.python.tui_menu as tui

        with patch("sys.stdout.isatty", return_value=False), \
             patch.dict(os.environ, {"NO_COLOR": "1"}), \
             patch("src.python.tui_menu.get_llm_config", return_value=None):
            with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
                tui._show_llm_config_status()
                for call_args, _ in mock_stdout.write.call_args_list:
                    text = call_args[0] if isinstance(call_args[0], str) else str(call_args[0])
                    self.assertNotIn("\033[", text,
                                     f"NO_COLOR + 未配置应无 ANSI: {text[:50]!r}")


if __name__ == "__main__":
    unittest.main()
