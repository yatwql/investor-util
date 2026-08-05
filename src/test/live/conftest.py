"""live/ 子目录 conftest — 仅收集 live 真实网络套件。

默认排除：本子目录的测试全部带 @pytest.mark.live，由顶层 conftest 的
`_skip_live_unless_requested` 自动跳过（除非 `--run-live` 或 `-m live`）。

本文件存在以确保 pytest 将该目录识别为测试包并正常收集。
"""

from __future__ import annotations

pytestmark = []
