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
_init_venv_if_needed() {
    local target="$1"
    if [ ! -f "$target/pyvenv.cfg" ] && [ ! -f "$target/bin/activate" ] && [ ! -f "$target/Scripts/activate" ]; then
        echo "虚拟环境目录为空，正在创建: $target"
        $PYTHON_CMD -m venv "$target"
        if [ $? -ne 0 ]; then
            echo "错误: 创建虚拟环境失败: $target" >&2
            exit 1
        fi
        echo "虚拟环境创建完成: $target"
    fi
}

if [ -d ".venv" ] || [ -L ".venv" ]; then
    if [ -L ".venv" ]; then
        VENV_TARGET=$(readlink .venv)
        echo "检测到外部虚拟环境链接: $VENV_TARGET"
        _init_venv_if_needed "$VENV_TARGET"
    else
        echo "检测到本地虚拟环境。"
        _init_venv_if_needed ".venv"
    fi
elif [ -n "$VENV_PATH" ]; then
    # VENV_PATH 环境变量指向外部管理的 .venv 目录
    echo "正在链接外部虚拟环境: $VENV_PATH"
    if [ ! -d "$VENV_PATH" ]; then
        echo "外部虚拟环境目录不存在，正在创建: $VENV_PATH"
        $PYTHON_CMD -m venv "$VENV_PATH"
        if [ ! -d "$VENV_PATH" ]; then
            echo "错误: 创建外部虚拟环境失败。" >&2
            exit 1
        fi
    fi
    _init_venv_if_needed "$VENV_PATH"
    ln -s "$VENV_PATH" .venv
    echo "已创建链接: .venv → $VENV_PATH"
else
    echo "正在创建本地虚拟环境 ..."
    echo "(提示: 设置 VENV_PATH 环境变量可将 .venv 管理在项目外部。)"
    $PYTHON_CMD -m venv .venv
    if [ ! -d ".venv" ]; then
        echo "错误: 创建虚拟环境失败。" >&2
        exit 1
    fi
fi

# 3. 激活虚拟环境（兼容 Linux bin/activate 和 Windows Git Bash Scripts/activate）
echo "正在激活虚拟环境 ..."
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "错误: 未找到虚拟环境激活脚本（.venv/bin/activate 或 .venv/Scripts/activate）。" >&2
    exit 1
fi
if [ $? -ne 0 ]; then
    echo "错误: 激活虚拟环境失败。" >&2
    exit 1
fi

# 3.5. 检查 Python 版本（要求 >= 3.10）
echo "正在检查 Python 版本 ..."
PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || [ "$PY_MAJOR" -eq 3 -a "$PY_MINOR" -lt 10 ]; then
    echo "错误: 需要 Python >= 3.10，当前版本: $PY_VER" >&2
    exit 1
fi
echo "Python 版本: $PY_VER（满足要求）"

# 4. 安装依赖（检查 requirements.txt 是否变更，未变更则跳过）
DEPS_MARKER=".venv/.deps_installed"
REQ_HASH=$(sha256sum requirements.txt | awk '{print $1}')
SKIP_INSTALL=false
if [ -f "$DEPS_MARKER" ]; then
    OLD_HASH=$(cat "$DEPS_MARKER")
    if [ "$OLD_HASH" = "$REQ_HASH" ]; then
        SKIP_INSTALL=true
    fi
fi
if [ "$SKIP_INSTALL" = false ]; then
    echo "正在安装依赖 ..."
    # -qq 级静默：抑制 pip 版本通知和下载进度条
    pip install -qq -r requirements.txt
    if [ $? -eq 0 ]; then
        echo "$REQ_HASH" > "$DEPS_MARKER"
    else
        echo "错误: 安装依赖失败。" >&2
        exit 1
    fi
else
    echo "依赖已安装，跳过 pip install（requirements.txt 未变更）"
fi

# 5. 创建所需目录
echo "正在创建数据目录 ..."
mkdir -p data/holdings data/cache data/config docs-stm/tmp logs

# 6. 启动主程序
# 注册退出处理：TUI 退出后自动退出虚拟环境（覆盖 Ctrl+C / 正常退出 / 错误）
trap 'deactivate 2>/dev/null; echo "虚拟环境已退出。"' EXIT

echo "正在启动主程序 ..."
$PYTHON_CMD src/python/tui/tui.py
if [ $? -ne 0 ]; then
    echo "错误: 程序运行失败。" >&2
    exit 1
fi
