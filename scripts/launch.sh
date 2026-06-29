#!/bin/bash
# scripts/launch.sh - 投资分析 TUI 启动脚本 (Linux)
# Encoding: UTF-8 (no BOM)

echo "正在启动投资分析系统 ..."

# 1. 检查 Python 是否安装
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "错误: 未找到 Python，请先安装 Python 环境。" >&2
    exit 1
fi

echo "检测到 Python: $PYTHON_CMD"

# 2. 检查/创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "正在创建虚拟环境 ..."
    $PYTHON_CMD -m venv .venv
    if [ ! -d ".venv" ]; then
        echo "错误: 创建虚拟环境失败。" >&2
        exit 1
    fi
fi

# 3. 激活虚拟环境
echo "正在激活虚拟环境 ..."
source .venv/bin/activate
if [ $? -ne 0 ]; then
    echo "错误: 激活虚拟环境失败。" >&2
    exit 1
fi

# 4. 安装依赖
echo "正在安装依赖 ..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "错误: 安装依赖失败。" >&2
    exit 1
fi

# 5. 创建所需目录
echo "正在创建数据目录 ..."
mkdir -p data/holdings data/cache data/config docs-stm/tmp logs

# 6. 启动主程序
# 注册退出处理：TUI 退出后自动退出虚拟环境（覆盖 Ctrl+C / 正常退出 / 错误）
trap 'deactivate 2>/dev/null; echo "虚拟环境已退出。"' EXIT

echo "正在启动主程序 ..."
$PYTHON_CMD src/python/main.py
if [ $? -ne 0 ]; then
    echo "错误: 程序运行失败。" >&2
    exit 1
fi
