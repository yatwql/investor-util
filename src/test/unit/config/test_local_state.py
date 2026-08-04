"""本地机器状态（data/state/local_state.json）读写测试。

测试策略：
  - get_flag / set_flag — 布尔标志读写（_LOCAL_STATE_FILE 被
    _isolate_sensitive_paths 重定向到 tmp_path）
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]

from src.python.config._local_state import get_flag, set_flag


# ── 读写 ─────────────────────────────────────────────────────


class TestFlagReadWrite:
    """get_flag / set_flag 读写测试。"""

    def test_default_false_when_no_file(self):
        """无 local_state 文件 → 标志默认 False。"""
        assert get_flag("_startup_wizard_shown") is False

    def test_set_then_get(self):
        """set_flag 写入后 get_flag 读回。"""
        set_flag("_startup_wizard_shown", True)
        assert get_flag("_startup_wizard_shown") is True

    def test_overwrite_value(self):
        """重复写入覆盖旧值。"""
        set_flag("_startup_wizard_shown", True)
        set_flag("_startup_wizard_shown", False)
        assert get_flag("_startup_wizard_shown") is False

    def test_different_keys_isolated(self):
        """不同标志键互不影响。"""
        set_flag("_startup_wizard_shown", True)
        assert get_flag("_privacy_notice_shown") is False
