"""check-code-traces 扫描域配置（仓库根/扫描目录/跳过文件/工具自身识别）。"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [
    REPO_ROOT / "src" / "python",
    REPO_ROOT / "src" / "test",
    REPO_ROOT / "src" / "static",
    REPO_ROOT / "scripts",
]
# 跳过文件名（编译产物）。本工具自身（check-*.traces.py）由 _is_tool_self()
# 模式豁免——见下方说明，不在此硬编码文件名。
SKIP_FILES = {"chart.min.js"}


def _is_tool_self(name: str) -> bool:
    """检查工具自身识别：check-*.traces.py。

    本工具（check-code-traces.py / check-doc-traces.py）的模式定义区
    （PATTERNS / EXCLUDE_LINE）与 docstring 必然包含被检测类别的特征字面量
    （版本号正则、任务编号正则、迁移/重命名描述词等）。这些是"检查规则
    的元描述"，不是被查对象的历史痕迹；用本工具规则自查本工具自身，
    与"用尺子量尺子"无异。故整文件豁免，且按模式识别而非硬编码文件名，
    使未来新增同类工具（check-xml-traces.py 等）自动豁免。
    """
    return name.startswith("check-") and name.endswith("traces.py")
