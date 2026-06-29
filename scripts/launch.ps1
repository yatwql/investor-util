# scripts/launch.ps1 - 投资分析 TUI 启动脚本 (Windows)
# Encoding: UTF-8 with BOM (PowerShell requires BOM for Chinese chars)

# 获取项目根目录（使脚本可以从任意目录运行）
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

Write-Host "正在启动投资分析系统 ..."
Write-Host "项目目录: $projectRoot"

# 1. 检查 Python 是否安装
$pythonCmd = $null
try {
    $null = Get-Command "python" -ErrorAction Stop
    $pythonCmd = "python"
} catch {
    try {
        $null = Get-Command "python3" -ErrorAction Stop
        $pythonCmd = "python3"
    } catch {
        Write-Host "错误: 未找到 Python，请先安装 Python 环境。" -ForegroundColor Red
        exit 1
    }
}

Write-Host "检测到 Python: $($pythonCmd)"

# 2. 检查/创建虚拟环境
if (-not (Test-Path ".venv")) {
    Write-Host "正在创建虚拟环境 ..."
    & $pythonCmd -m venv .venv
    if (-not (Test-Path ".venv")) {
        Write-Host "错误: 创建虚拟环境失败。" -ForegroundColor Red
        exit 1
    }
}

# 3. 激活虚拟环境
Write-Host "正在激活虚拟环境 ..."
try {
    . .\.venv\Scripts\Activate.ps1
} catch {
    Write-Host "错误: 激活虚拟环境失败。请检查执行策略: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Red
    exit 1
}

# 4. 安装依赖
Write-Host "正在安装依赖 ..."
try {
    pip install -q -r requirements.txt
} catch {
    Write-Host "错误: 安装依赖失败。" -ForegroundColor Red
    exit 1
}

# 5. 创建所需目录
Write-Host "正在创建数据目录 ..."
New-Item -ItemType Directory -Force -Path "data\holdings" | Out-Null
New-Item -ItemType Directory -Force -Path "data\cache" | Out-Null
New-Item -ItemType Directory -Force -Path "data\config" | Out-Null
New-Item -ItemType Directory -Force -Path "docs-stm\tmp" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

# 6. 启动主程序
Write-Host "正在启动主程序 ..."
try {
    & $pythonCmd src\python\main.py
} catch {
    Write-Host "错误: 程序运行失败: $_" -ForegroundColor Red
} finally {
    # TUI 退出后自动退出虚拟环境
    if (Get-Command deactivate -ErrorAction SilentlyContinue) {
        deactivate
        Write-Host "虚拟环境已退出。"
    }
}
