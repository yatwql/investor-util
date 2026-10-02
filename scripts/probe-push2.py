#!/usr/bin/env python3
"""push2 连通性探测 — 薄委托垫片（实现与用法见 scripts/probe.py/probes/push2.py）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probes  # noqa: E402

sys.exit(probes.get("push2").run(probes.get("push2").build_parser().parse_args(sys.argv[1:])))
