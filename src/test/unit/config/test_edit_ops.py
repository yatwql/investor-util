"""共享编辑层 config.edit_ops：白名单校验、值规则与写入分派（Web/TUI 同一函数）。

覆盖：白名单结构（与注册表派生一致）/ 非法键与类型 / holdings_filename 路径分隔符 /
对比指数 action 规则 / 匿名化枚举 / 成功写入与写前 .bak 备份。
"""

from __future__ import annotations

import json
import os

import pytest

from src.python.config.edit_ops import (
    ANON_MODES,
    ConfigEditError,
    apply_config_edit,
    config_edit_whitelist,
)
from src.python.config.features import feature_switch_registry
from src.python.core.registry import visible_llm_module_names

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


def _config_path() -> str:
    from src.python.config._config_defaults import get_config_path

    return get_config_path()


def _read_config_json() -> dict:
    with open(_config_path(), encoding="utf-8") as f:
        return json.load(f)


class TestWhitelistStructure:
    """白名单 = 唯一事实来源：与注册表派生的结构关系（不写死条数）。"""

    def test_llm_module_keys_match_visible_registry(self):
        expected = {f"enabled_llm.{m}" for m in visible_llm_module_names()}
        actual = {k for k in config_edit_whitelist if k.startswith("enabled_llm.")}
        assert actual == expected

    def test_feature_keys_match_registry(self):
        actual = {k for k, v in config_edit_whitelist.items() if v["writer"] == "features"}
        assert actual == set(feature_switch_registry)

    def test_core_paths_whitelisted(self):
        for key in ("holdings_dir", "holdings_filename", "output_dir"):
            assert key in config_edit_whitelist

    def test_anon_options_match_mode_enum(self):
        assert set(config_edit_whitelist["anonymization.mode"]["options"]) == set(ANON_MODES)


class TestValidationRules:
    """值规则集中在共享层：非法输入一律 ConfigEditError（渠道呈现 400/提示行）。"""

    def test_unknown_key_rejected(self):
        with pytest.raises(ConfigEditError, match="白名单"):
            apply_config_edit({"key": "not_a_key", "value": "x"})

    def test_path_value_must_be_non_empty_string(self):
        with pytest.raises(ConfigEditError):
            apply_config_edit({"key": "output_dir", "value": 123})
        with pytest.raises(ConfigEditError):
            apply_config_edit({"key": "output_dir", "value": "   "})

    def test_holdings_filename_rejects_path_separators(self):
        for bad in ("dir/file.xlsx", "dir\\file.xlsx"):
            with pytest.raises(ConfigEditError, match="路径分隔符"):
                apply_config_edit({"key": "holdings_filename", "value": bad})

    def test_bool_value_type_enforced(self):
        with pytest.raises(ConfigEditError, match="布尔"):
            apply_config_edit({"key": "enable_news", "value": "yes"})

    def test_anon_mode_enum_enforced(self):
        with pytest.raises(ConfigEditError, match="允许范围"):
            apply_config_edit({"key": "anonymization.mode", "value": "bogus"})

    def test_unknown_llm_module_key_rejected(self):
        with pytest.raises(ConfigEditError, match="白名单"):
            apply_config_edit({"key": "enabled_llm.not_a_module", "value": True})

    def test_comparison_action_enforced(self):
        with pytest.raises(ConfigEditError, match="action"):
            apply_config_edit({"key": "comparison_indices", "action": "destroy"})

    def test_comparison_add_rules(self):
        with pytest.raises(ConfigEditError, match="不能为空"):
            apply_config_edit({"key": "comparison_indices", "action": "add", "code": "", "name": "x"})
        with pytest.raises(ConfigEditError, match="长度"):
            apply_config_edit({"key": "comparison_indices", "action": "add", "code": "ab", "name": "x"})
        with pytest.raises(ConfigEditError, match="非法字符"):
            apply_config_edit({"key": "comparison_indices", "action": "add", "code": "a/b", "name": "x"})
        with pytest.raises(ConfigEditError, match="名称"):
            apply_config_edit({"key": "comparison_indices", "action": "add", "code": "TESTCODE", "name": " "})

    def test_comparison_add_duplicate_default_code(self):
        from src.python.config import get_default

        default_code = next(iter(get_default("comparison_indices") or {}))
        with pytest.raises(ConfigEditError, match="已在对比池"):
            apply_config_edit({"key": "comparison_indices", "action": "add", "code": default_code, "name": "x"})

    def test_comparison_remove_unknown_code(self):
        with pytest.raises(ConfigEditError, match="不在对比池"):
            apply_config_edit({"key": "comparison_indices", "action": "remove", "code": "NOSUCH1"})


class TestApplyAndBackup:
    """成功路径：写前单槽备份 → 分派写入 → 返回新值与备份路径。"""

    def _seed_config(self) -> str:
        path = _config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"output_dir": "old_out"}, f, ensure_ascii=False)
        return path

    def test_scalar_write_creates_backup_and_updates_file(self):
        path = self._seed_config()
        result = apply_config_edit({"key": "output_dir", "value": "new_out"})
        assert result["key"] == "output_dir"
        assert result["value"] == "new_out"
        assert result["backup"] == path + ".bak"
        assert os.path.exists(path + ".bak")
        assert _read_config_json()["output_dir"] == "new_out"

    def test_comparison_add_then_remove_roundtrip(self):
        self._seed_config()
        apply_config_edit({"key": "comparison_indices", "action": "add", "code": "TESTIDX", "name": "测试指数"})
        assert _read_config_json()["comparison_indices"]["TESTIDX"] == "测试指数"
        apply_config_edit({"key": "comparison_indices", "action": "remove", "code": "TESTIDX"})
        assert "TESTIDX" not in _read_config_json()["comparison_indices"]

    def test_comparison_reset_restores_defaults(self):
        from src.python.config import get_default

        self._seed_config()
        apply_config_edit({"key": "comparison_indices", "action": "reset"})
        assert _read_config_json()["comparison_indices"] == get_default("comparison_indices")
