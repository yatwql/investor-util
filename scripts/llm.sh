#!/bin/bash
# scripts/llm.sh - 一键生成完整报告（含 LLM 分析章节）(Linux/macOS)
# Encoding: UTF-8 (no BOM)
#
# 固定使用 report --type full，等价于 TUI 菜单的「生成完整报告(Excel+HTML)
# [含LLM，按章节配置]」——省去每次敲子命令与报告类型。
#
# 组合历史走势不写死 --history，由配置 history.fetch_mode 决定（与 TUI 菜单
# 一致：off 跳过、auto 获取）；需要本地覆盖时追加 --history auto / --history off。
#
# 用法:
#   ./scripts/llm.sh                        # 生成完整报告（含 LLM）
#   ./scripts/llm.sh --force-llm            # 强制重新调用 LLM，跳过缓存
#   ./scripts/llm.sh --history off          # 本次不获取组合历史走势
#
# 需要全局参数（--config / --output / --experiment / --feature 等）时用
# ./scripts/cli.sh，它们必须写在 report 子命令之前。

# 1. 定位项目根目录（脚本可从任意目录运行）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# 2. 使用项目虚拟环境解释器（禁止裸 python3/python）
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    echo "[ERR] 未找到虚拟环境解释器: $PYTHON_BIN" >&2
    echo "[!]   请先运行 ./scripts/launch.sh 完成虚拟环境初始化。" >&2
    exit 1
fi

# 3. 创建所需数据目录（与 launch.sh 保持一致，非破坏性）
mkdir -p data/holdings data/cache data/config docs-stm/tmp logs

# 4. 完整报告 + 追加参数（报告级参数如 --force-llm / --history 追加在后）
exec "$PYTHON_BIN" -m src.python.cli report --type full "$@"
