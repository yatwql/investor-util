#!/bin/bash
# scripts/cli.sh - 投资分析 CLI 命令行模式 (Linux/macOS)
# Encoding: UTF-8 (no BOM)
#
# 无参数调用时默认生成报告（report 子命令，--type basic，仅 Excel）；
# 传入参数时原样透传给 CLI，等价于 .venv/bin/python -m src.python.cli <args>。
#
# 用法:
#   ./scripts/cli.sh                        # 无参数 -> 默认生成报告
#   ./scripts/cli.sh report --type full     # 生成全量报告（含 LLM）
#   ./scripts/cli.sh cache --stats          # 查看缓存状态
#   ./scripts/cli.sh --help                 # 查看 CLI 帮助

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

# 4. 无参数 -> 默认生成报告；否则原样透传
if [ $# -eq 0 ]; then
    set -- report
fi

exec "$PYTHON_BIN" -m src.python.cli "$@"
