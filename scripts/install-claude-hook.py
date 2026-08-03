#!/usr/bin/env python3
"""安装/卸载 Claude Code PostToolUse hook（任务编号一致性自动校验）。

`.claude/settings.json` 被 `.gitignore` 排除、不随仓库同步，新机器 clone 后
需要本脚本写入一次 hook 接线（脚本本体 `check-task-numbering-hook.py` 随
仓库同步）。

用法:
  python scripts/install-claude-hook.py            # 安装（幂等：已存在则更新）
  python scripts/install-claude-hook.py --uninstall # 卸载（移除本 hook，保留其他配置）

写入的 hook：编辑 plan.md / review-findings.md 后自动运行
`scripts/check-task-numbering-hook.py` 校验编号一致性（失败中断编辑）。

说明：
  - 幂等：settings.json 已含本 hook 时跳过写入
  - 合并式：保留 settings.json 中已有的其他配置（权限/hooks），仅合并本 hook
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SETTINGS_PATH = _REPO_ROOT / ".claude" / "settings.json"

# 与 check-task-numbering-hook.py 同名的 hook 条目（match_tool + match_type + command）
_HOOK_CMD = "python scripts/check-task-numbering-hook.py \"$__INJECTED_OBJECT__\""


def _build_hook_block() -> dict:
    """构造本脚本管理的 PostToolUse hook 块。"""
    return {
        "matcher": "Edit|Write",
        "hooks": [
            {
                "type": "command",
                "command": _HOOK_CMD,
            }
        ],
    }


def _load_existing() -> dict:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_settings(data: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _block_matches(existing: dict) -> bool:
    """判断已存在的 hooks 中是否含本脚本管理的 block（按 command 识别）。"""
    for hook in existing.get("hooks", {}).get("PostToolUse", []):
        for h in hook.get("hooks", []):
            if h.get("type") == "command" and h.get("command") == _HOOK_CMD:
                return True
    return False


def install() -> int:
    existing = _load_existing()
    if _block_matches(existing):
        print("[OK] hook 已安装（幂等跳过）")
        return 0

    block = _build_hook_block()
    existing.setdefault("hooks", {}).setdefault("PostToolUse", []).append(block)
    _write_settings(existing)
    print("[OK] 已写入 .claude/settings.json PostToolUse hook")
    return 0


def uninstall() -> int:
    existing = _load_existing()
    if not _block_matches(existing):
        print("[OK] 未发现本 hook（无需卸载）")
        return 0

    post = existing.get("hooks", {}).get("PostToolUse", [])
    remaining = [
        hook
        for hook in post
        if not any(
            h.get("type") == "command" and h.get("command") == _HOOK_CMD
            for h in hook.get("hooks", [])
        )
    ]
    existing["hooks"]["PostToolUse"] = remaining
    if not remaining:
        existing["hooks"].pop("PostToolUse", None)
    if not existing.get("hooks"):
        existing.pop("hooks", None)
    _write_settings(existing)
    print("[OK] 已移除 PostToolUse hook")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="安装/卸载 Claude Code 任务编号校验 hook")
    parser.add_argument("--uninstall", action="store_true", help="卸载而非安装")
    args = parser.parse_args()
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    sys.exit(main())
