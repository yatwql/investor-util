#!/usr/bin/env python3
"""CSI 指数可用性探测 — 薄委托垫片（实现与用法见 scripts/probe.py/probes/csi.py）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probes  # noqa: E402

sys.exit(probes.get("csi").run(probes.get("csi").build_parser().parse_args(sys.argv[1:])))
