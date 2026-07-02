"""unit/conftest.py — 单元测试标记完整性强制验证。

已有 62 个测试文件均通过 pytestmark 显式标注 unit + unit_* 标记。
新文件如果漏标，本 conftest 将报错提醒开发者手动添加，避免标记体系退化。

在 conftest.py 的标记注册列表中可见所有 unit_* 标记名：
  - unit_providers / unit_fetcher / unit_llm / unit_news
  - unit_report / unit_config / unit_core / unit_ui

用法：
  pytest src/test/unit/ -m "unit_core"    # 仅 core 子模块
  pytest src/test/unit/ -m "not unit_llm" # 排除 LLM 子模块
"""

from __future__ import annotations

import pytest

# 子目录名 → unit_* 标记名
_DIR_TO_MARKER: dict[str, str] = {
    "config": "unit_config",
    "core": "unit_core",
    "fetcher": "unit_fetcher",
    "llm": "unit_llm",
    "news": "unit_news",
    "providers": "unit_providers",
    "report": "unit_report",
    "ui": "unit_ui",
}


def pytest_collection_modifyitems(config, items):
    """收集后验证每个测试项都有 unit_* 子标记，缺失则报错。"""
    for item in items:
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


def _has_subunit_marker(item) -> bool:
    """检查测试项是否已有 unit_* 子标记（排除 unit 父标记本身）。"""
    return any(
        m.name.startswith("unit_") and m.name != "unit"
        for m in item.iter_markers()
    )
