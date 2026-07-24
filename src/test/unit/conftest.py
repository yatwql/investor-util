"""unit/conftest.py — 单元测试标记完整性强制验证。

已有 62 个测试文件均通过 pytestmark 显式标注 unit + unit_* 标记。
新文件如果漏标，本 conftest 将报错提醒开发者手动添加，避免标记体系退化。

在 conftest.py 的标记注册列表中可见所有 unit_* 标记名：
  - unit_providers / unit_fetcher / unit_llm / unit_news
  - unit_report / unit_config / unit_core / unit_analysis
	  - unit_ui / unit_cli

用法：
  pytest src/test/unit/ -m "unit_core"    # 仅 core 子模块
  pytest src/test/unit/ -m "not unit_llm" # 排除 LLM 子模块
"""

from __future__ import annotations

from pathlib import Path

import pytest

# 本 conftest 所在目录（src/test/unit/），用于过滤仅属于 unit/ 的测试项
_UNIT_ROOT = Path(__file__).resolve().parent

# 子目录名 → unit_* 标记名
_DIR_TO_MARKER: dict[str, str] = {
    "analysis": "unit_analysis",
    "cli": "unit_cli",
    "config": "unit_config",
    "core": "unit_core",
    "fetcher": "unit_fetcher",
    "handlers": "unit_core",
    "llm": "unit_llm",
    "news": "unit_news",
    "providers": "unit_providers",
    "report": "unit_report",
    "ui": "unit_ui",
}


def pytest_collection_modifyitems(config, items):
    """收集后验证每个测试项都有 unit_* 子标记，缺失则报错。

    注意：pytest 9.x 中此 hook 可能收到父级范围的全部 items，
    因此先按文件路径过滤，只处理属于 unit/ 目录的测试项，
    避免干扰顶层（src/test/）的 marker 过滤。"""
    unit_items = [it for it in items if _is_under_unit(it)]
    for item in unit_items:
        if not _has_subunit_marker(item):
            parent_dir = item.fspath.dirpath().basename
            expected = _DIR_TO_MARKER.get(parent_dir, "unit_<未知模块>")
            raise pytest.UsageError(
                f"\n\n[!] 测试文件缺少 unit_* 标记（pytestmark 缺失）：\n"
                f"    文件：{item.fspath}\n"
                f"    预期标记：{expected}（根据子目录名推断）\n"
                f"    请在文件模块级添加：\n"
                f"        pytestmark = [pytest.mark.unit, pytest.mark.{expected}]\n"
                f"    如该文件还需 edge/llm 等横切标记，一并加入列表。\n"
            )


def _is_under_unit(item) -> bool:
    """判断测试项文件路径是否在 unit/ 目录下。"""
    try:
        return _UNIT_ROOT in Path(item.fspath).resolve().parents
    except (OSError, TypeError):
        return False


def _has_subunit_marker(item) -> bool:
    """检查测试项是否已有 unit_* 子标记（排除 unit 父标记本身）。"""
    return any(
        m.name.startswith("unit_") and m.name != "unit"
        for m in item.iter_markers()
    )
