"""三渠道薄壳层纪律扫描：渠道不持业务规则、不直写配置、不散落默认值字面量。

对应三渠道架构巡检（配置编辑共享、路径解析单源、状态组装单源、缓存编排下沉）。
扫描 src/python/ 下 web / tui / cli 三渠道源码（AST 导入面 + 文本字面量），发现即红——
防止「薄壳重新长出业务」的回退。渠道包内部互相引用（dispatcher / 包 re-export）
不计入。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

_SRC_ROOT = Path(__file__).resolve().parents[2] / "python"

# 禁止渠道直引的私有配置模块（公开替代：config.get_local_flag / config.get_default）
_BANNED_PRIVATE_MODULES = frozenset(
    {
        "src.python.config._local_state",
        "src.python.config._config_defaults",
    }
)

# 禁止渠道直接导入的配置写原语（业务写入必须经 config.edit_ops.apply_config_edit）
_BANNED_WRITERS = frozenset(
    {
        "set_config",
        "set_anonymization_mode",
        "save_feature_overrides",
        "write_llm_settings",
    }
)

# 禁止散落的默认值字面量（真值来源：config.get_default / resolve_holdings_path）。
# 模式带引号：只命中配置回退形态，不误伤文档中对目录的描述性提及
_BANNED_LITERALS = (
    '"data/holdings"',
    "'data/holdings'",
    '"个人投资持仓信息"',
    "'个人投资持仓信息'",
    'get("output_dir", "reports")',
    "get('output_dir', 'reports')",
)


def _channels() -> list[tuple[str, list[Path]]]:
    return [(chan, sorted((_SRC_ROOT / chan).rglob("*.py"))) for chan in ("web", "tui", "cli")]


def _from_imports(tree: ast.AST):
    """产出 (lineno, module, imported_name)；纯 import 产出 module=None。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                yield node.lineno, node.module, alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, None


class TestImportHygiene:
    def test_no_cross_channel_private_symbol_imports(self):
        violations: list[str] = []
        for chan, files in _channels():
            for path in files:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for lineno, module, name in _from_imports(tree):
                    if name is None or not name.startswith("_"):
                        continue
                    if module.startswith(f"src.python.{chan}."):
                        continue  # 渠道包内部互相引用
                    violations.append(f"{path.relative_to(_SRC_ROOT)}:{lineno} from {module} import {name}")
        assert violations == []

    def test_no_banned_private_config_modules(self):
        violations: list[str] = []
        for _, files in _channels():
            for path in files:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for lineno, module, _name in _from_imports(tree):
                    if module in _BANNED_PRIVATE_MODULES:
                        violations.append(f"{path.relative_to(_SRC_ROOT)}:{lineno} import {module}")
        assert violations == []

    def test_no_direct_config_writers(self):
        violations: list[str] = []
        for _, files in _channels():
            for path in files:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for lineno, _module, name in _from_imports(tree):
                    if name in _BANNED_WRITERS:
                        violations.append(f"{path.relative_to(_SRC_ROOT)}:{lineno} import {name}")
        assert violations == []


class TestLiteralHygiene:
    def test_no_scattered_default_literals(self):
        violations: list[str] = []
        for _, files in _channels():
            for path in files:
                for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    for snippet in _BANNED_LITERALS:
                        if snippet in line:
                            violations.append(f"{path.relative_to(_SRC_ROOT)}:{lineno} 含字面量 {snippet!r}")
        assert violations == []


class TestSharedLayerRouting:
    """结构断言：配置写入的两端（Web/TUI）都接在共享编辑层上。"""

    @pytest.mark.parametrize("rel", ["web/handlers.py", "tui/handlers_config.py"])
    def test_write_entrypoints_reference_shared_edit_layer(self, rel):
        text = (_SRC_ROOT / rel).read_text(encoding="utf-8")
        assert "apply_config_edit" in text

    @pytest.mark.parametrize("rel", ["web/config_edit.py"])
    def test_web_edit_module_is_thin_facade(self, rel):
        """Web 配置编辑模块只做呈现面组装——规则实现引用共享层符号。"""
        text = (_SRC_ROOT / rel).read_text(encoding="utf-8")
        assert "apply_config_edit" in text
        assert "config_edit_whitelist" in text
        # 不在 Web 层重建规则字典
        assert "配置键不在白名单" not in text
