"""Web 入口 — ``python -m src.python.web``（对齐 cli/tui 模块入口）。"""

from __future__ import annotations

import sys

from src.python.web.server import main

if __name__ == "__main__":
    sys.exit(main())
