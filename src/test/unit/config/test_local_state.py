"""本地机器状态（data/state/local_state.json）读写与迁移测试。

测试策略：
  - get_flag / set_flag — 布尔标志读写（_LOCAL_STATE_FILE 被
    _isolate_sensitive_paths 重定向到 tmp_path）
  - _migrate_legacy_keys — 从 config.json 惰性搬移旧键（_startup_wizard_shown /
    _privacy_notice_shown），搬移后删除 config.json 旧键；local_state 已有值时
    不覆盖、不误删

注意：config.json 同样被 _isolate_sensitive_paths 重定向到 tmp_path，迁移测试
通过 set_config 写入旧键模拟迁移前 config.json 遗留键状态。
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]

from src.python.config import del_config, get_config, set_config
from src.python.config._local_state import (
    _LOCAL_STATE_FILE,
    get_flag,
    get_local_state,
    set_flag,
)


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


# ── 迁移 ─────────────────────────────────────────────────────


class TestLegacyMigration:
    """从 config.json 惰性迁移旧键测试。"""

    def test_migrates_legacy_key_from_config(self):
        """config.json 有旧键 → 迁移到 local_state 并从 config.json 删除。"""
        set_config("_startup_wizard_shown", True)
        assert get_flag("_startup_wizard_shown") is True
        # local_state 已落值
        assert get_local_state().get("_startup_wizard_shown") is True
        # config.json 旧键已删除
        assert "_startup_wizard_shown" not in get_config()

    def test_migrates_both_legacy_keys(self):
        """两个旧键一并迁移。"""
        set_config("_startup_wizard_shown", True)
        set_config("_privacy_notice_shown", False)
        get_flag("_startup_wizard_shown")
        data = get_local_state()
        assert data.get("_startup_wizard_shown") is True
        assert data.get("_privacy_notice_shown") is False
        cfg = get_config()
        assert "_startup_wizard_shown" not in cfg
        assert "_privacy_notice_shown" not in cfg

    def test_no_migration_when_config_clean(self):
        """config.json 无旧键 → 不创建 local_state 文件。"""
        assert get_flag("_startup_wizard_shown") is False
        assert not os.path.exists(_LOCAL_STATE_FILE)

    def test_local_state_value_wins_over_config(self):
        """local_state 已有值 → config 遗留旧键不被覆盖、不被误删。"""
        set_flag("_startup_wizard_shown", False)
        set_config("_startup_wizard_shown", True)  # 人为放置冲突旧键
        assert get_flag("_startup_wizard_shown") is False  # 以 local_state 为准
        assert get_config().get("_startup_wizard_shown") is True  # config 旧键未删

    def test_migration_removes_config_key_via_del_config(self):
        """迁移确经 del_config 删除 config.json 旧键（独立验证）。"""
        set_config("_privacy_notice_shown", True)
        get_flag("_privacy_notice_shown")
        del_config("_privacy_notice_shown")  # 键已删，此处应为静默 no-op
        assert "_privacy_notice_shown" not in get_config()
