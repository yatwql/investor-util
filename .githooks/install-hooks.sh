#!/bin/sh
# 启用 git pre-commit hook（任务编号一致性校验）
#
# .git/hooks 默认路径下的 hook 不随仓库同步，而 core.hooksPath 是本地 git
# 配置（不同步）。clone 到新机器后执行一次本脚本即可激活 pre-commit。
#
#   sh .githooks/install-hooks.sh        # 启用
#   sh .githooks/install-hooks.sh --off  # 停用（恢复 git 默认 hooks 路径）

set -e

TARGET=".githooks"

if [ "$1" = "--off" ]; then
    git config --unset core.hooksPath 2>/dev/null || true
    echo "[OK] 已停用自定义 hooks 路径（恢复 .git/hooks 默认）"
    exit 0
fi

git config core.hooksPath "$TARGET"
echo "[OK] 已启用 git hooks 路径: $TARGET"
echo "    pre-commit 将在提交涉及 plan.md / review-findings.md 时自动校验编号一致性"
echo "    停用: sh $TARGET/install-hooks.sh --off"
exit 0
