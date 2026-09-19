"""测试驱动（`scripts/test-runner.py`）内部实现包。

拆分动因：单文件超过 800 行后按职责切分为 paths / modes / pytest_env / machine_info /
doc_writer / report_html / runner 七个子模块，入口仅保留 CLI 解析与编排调用（原面符号
由入口模块 re-export，既有测试与调用方无需改动）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根（`scripts/_test_runner/` 上溯两级）加入 sys.path：子模块需 `from src.python… import …`
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
