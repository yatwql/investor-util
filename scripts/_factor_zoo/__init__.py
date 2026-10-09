"""因子动物园目录评测内部实现包（评测核心 / 阶段编排 / 判定书）。

拆分动因：单文件超 scripts 行数红线后按职责切分，入口 `factor_zoo_eval.py`
仅保留 CLI 与原面 re-export（既有测试与调用方无需改动）。
"""

from __future__ import annotations

from pathlib import Path

#: 仓库根单一来源：`scripts/_factor_zoo/__init__.py` → `parents[2]`。层级固定勿改浅
#: （改浅会静默扫错目录）；包内各模块统一从本模块取用，避免多处各算一次。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
