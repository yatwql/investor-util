"""测试驱动的路径常量（项目根 / 报告目录 / 归档目录 / 源码目录）。

导入本模块即把项目根加入 `sys.path`，供 `from src.python... import …` 使用（独立脚本默认不在）。
"""

from __future__ import annotations

import os
import sys

# ── 路径常量 ─────────────────────────────────────────────────

# 本文件位于 scripts/_test_runner/ → 上溯三级为仓库根
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPORTS_DIR = os.path.join(_PROJECT_ROOT, "test-reports")
_LATEST_DIR = os.path.join(_REPORTS_DIR, "latest")
_ARCHIVES_DIR = os.path.join(_REPORTS_DIR, "archives")
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src", "test")

# 引用项目常量（APP_NAME 等）需将项目根加入 sys.path（独立脚本默认不在）
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
