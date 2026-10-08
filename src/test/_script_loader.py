"""测试域共享的脚本加载器 — `scripts/` 下脚本按文件名动态加载的唯一实现。

`scripts/` 不在 import 路径上，`check-*` 这类连字符文件名也不是合法模块名，
测试只能按文件路径动态加载。同一套 `importlib.util.spec_from_file_location` 样板
过去散落在各测试文件（约 30 处、4 种变体），改造加载面（sys.modules 注册、模块名
派生规则）时需逐文件同步。此处收敛为单一实现：

    from src.test._script_loader import load_script
    mod = load_script("check-svg.py")

新测试一律复用本模块，不再自带样板（样板唯一性由
`src/test/unit/scripts/test_script_loader.py` 机检）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

#: 仓库根 `scripts/` 目录（本文件位于 `src/test/`，向上 2 级即仓库根）
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def load_script(name: str, *, module_name: str | None = None) -> ModuleType:
    """加载 `scripts/` 下的脚本为模块。

    Args:
        name: 相对 `scripts/` 的脚本路径，如 ``"check-svg.py"``、
            ``"_test_runner/modes.py"``。
        module_name: 注册进 ``sys.modules`` 的模块名。缺省由文件名派生
            （``check-svg.py`` → ``check_svg``）；需与真实模块名区隔
            （测试期补丁不外溢到同名真实导入）时显式指定。

    Returns:
        执行完毕的模块对象。每次调用都**重新执行**脚本、返回新实例，
        保证用例之间模块状态互不串扰。
    """
    fpath = SCRIPTS_DIR / name
    resolved = module_name or Path(name).stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(resolved, fpath)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为脚本创建模块 spec：{fpath}")
    module = importlib.util.module_from_spec(spec)
    # 注册进 sys.modules：`@dataclass` 解析类命名空间时按 cls.__module__ 回查模块
    sys.modules[resolved] = module
    spec.loader.exec_module(module)
    return module
