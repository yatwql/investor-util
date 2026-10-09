"""check-code-traces 扫描域配置（仓库根/扫描目录/跳过文件/工具自身识别）。"""

from __future__ import annotations

from pathlib import Path

# 本文件位于 scripts/_traces_code/ 下，故深度取三级（仓库根），不得用
# parent.parent——那样会落在 scripts/ 下，SCAN_DIRS 变成不存在的
# scripts/src/... 而令整轮扫描静默跳过（扫不到即「永远通过」）。
REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [
    REPO_ROOT / "src" / "python",
    REPO_ROOT / "src" / "test",
    REPO_ROOT / "src" / "static",
    REPO_ROOT / "scripts",
]
# 跳过文件名（编译产物）。本工具自身（check-*.traces.py）由 _is_tool_self()
# 模式豁免——见下方说明，不在此硬编码文件名。
SKIP_FILES = {"chart.min.js"}

#: 规则定义载体目录：模式/豁免正则与描述字面量（R11/F-1/F_1/第X章…）住在
#: 本包内，属“尺子本身”而非被查对象（拆包前它们在 check-code-traces.py
#: 文件体内，由 _is_tool_self() 结构性豁免）。按目录识别，文件名无关。
RULE_CARRIER_DIRS = frozenset({"_traces_code"})


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
