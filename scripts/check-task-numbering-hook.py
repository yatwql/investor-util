#!/usr/bin/env python3
"""Claude Code PostToolUse hook — 编辑任务编号管理文档后自动校验编号一致性。

在 .claude/settings.json 中配置为 PostToolUse 钩子调用本脚本：

    { "hooks": { "PostToolUse": [ { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "command": "python scripts/check-task-numbering-hook.py"
          "__INJECTED_OBJECT__" } ] } ] }

钩子仅在编辑 plan.md / review-findings.md 时触发全量编号校验（plan/rf 两条
序列），其余文件直接放行。校验失败以非零退出码返回，Claude Code 会中断
当前编辑操作并提示用户修正「编号源」标记。

无参数运行；若子进程调用失败或脚本自身异常，一律放行（hook 不应阻断
与编号无关的正常编辑，仅负责在相关文档变更时提示冲突）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TARGET_DOCS = {"plan.md", "review-findings.md"}
_CHECK_SCRIPT = _REPO_ROOT / "scripts" / "check-task-numbering.py"


def _is_target_doc(tool_input: dict) -> bool:
    """判断当前编辑的文件是否为任务编号管理文档。"""
    file_path = tool_input.get("file_path", "")
    return Path(file_path).name in _TARGET_DOCS


def main() -> int:
    # __INJECTED_OBJECT__ 可能经环境变量或命令行参数传入，两者兼容
    inject = os.environ.get("__INJECTED_OBJECT__", "") or (sys.argv[1] if len(sys.argv) > 1 else "")
    try:
        payload = json.loads(inject)
    except json.JSONDecodeError:
        return 0  # 无 hook 上下文，放行

    tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}
    if not _is_target_doc(tool_input):
        return 0

    try:
        proc = subprocess.run(
            [sys.executable, str(_CHECK_SCRIPT), "--ci"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_REPO_ROOT,
        )
    except OSError:
        return 0  # 校验脚本不可运行，放行（不阻断编辑）

    if proc.returncode != 0:
        output = (proc.stdout or "") + (proc.stderr or "")
        print(f"[ERR] 任务编号一致性检查失败（{Path(tool_input.get('file_path', '')).name}）：")
        for line in output.splitlines():
            print(f"  {line}")
        print("请修正编号源标记（plan-next / rf-next）后重试。")
        return 1

    print("[OK] 任务编号一致性检查通过（plan / rf 与历史归档无冲突）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
