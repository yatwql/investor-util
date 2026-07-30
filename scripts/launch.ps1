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
function _Ensure-VenvInitialized {
    param([string]$Path)
    $activateScript = Join-Path $Path "Scripts\Activate.ps1"
    $pyvenvCfg = Join-Path $Path "pyvenv.cfg"
    if (-not (Test-Path $activateScript) -and -not (Test-Path $pyvenvCfg)) {
        Write-Host "虚拟环境目录为空，正在创建: $Path" -ForegroundColor Yellow
        & $pythonCmd -m venv $Path
        if (-not (Test-Path $Path)) {
            Write-Host "错误: 创建虚拟环境失败: $Path" -ForegroundColor Red
            exit 1
        }
        Write-Host "虚拟环境创建完成: $Path" -ForegroundColor Cyan
    }
}

if (Test-Path ".venv") {
    $item = Get-Item ".venv"
    if ($item.LinkType -eq "Junction") {
        $venvTarget = $item.Target
        Write-Host "检测到外部虚拟环境链接: $venvTarget" -ForegroundColor Cyan
        _Ensure-VenvInitialized -Path $venvTarget
    } else {
        Write-Host "检测到本地虚拟环境。" -ForegroundColor Cyan
        _Ensure-VenvInitialized -Path ".venv"
    }
} elseif ($env:VENV_PATH) {
    # VENV_PATH 环境变量指向外部管理的 .venv 目录
    $externalVenv = $env:VENV_PATH
    Write-Host "正在链接外部虚拟环境: $externalVenv" -ForegroundColor Cyan
    if (-not (Test-Path $externalVenv)) {
        Write-Host "外部虚拟环境目录不存在，正在创建: $externalVenv" -ForegroundColor Yellow
        & $pythonCmd -m venv $externalVenv
        if (-not (Test-Path $externalVenv)) {
            Write-Host "错误: 创建外部虚拟环境失败。" -ForegroundColor Red
            exit 1
        }
    }
    _Ensure-VenvInitialized -Path $externalVenv
    New-Item -ItemType Junction -Path ".venv" -Target $externalVenv | Out-Null
    Write-Host "已创建链接: .venv → $externalVenv" -ForegroundColor Cyan
} else {
    Write-Host "正在创建本地虚拟环境 ..."
    Write-Host "提示: 设置 VENV_PATH 环境变量可将 .venv 管理在项目外部。" -ForegroundColor DarkGray
    & $pythonCmd -m venv .venv
    if (-not (Test-Path ".venv")) {
        Write-Host "错误: 创建虚拟环境失败。" -ForegroundColor Red
        exit 1
    }
}

# 3. 激活虚拟环境
Write-Host "正在激活虚拟环境 ..."
$activateScript = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Host "错误: 未找到虚拟环境激活脚本 ($activateScript)。" -ForegroundColor Red
    exit 1
}
try {
    . $activateScript
} catch {
    Write-Host "错误: 激活虚拟环境失败。请检查执行策略: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Red
    exit 1
}

# 3.5. 检查 Python 版本（要求 >= 3.10）
$pyVer = & $pythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$verParts = $pyVer.Split('.')
$major = [int]$verParts[0]
$minor = [int]$verParts[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Host "错误: 需要 Python >= 3.10，当前版本: $pyVer" -ForegroundColor Red
    exit 1
}
Write-Host "Python 版本: $pyVer（满足要求）" -ForegroundColor Cyan

# 4. 安装依赖（检查 requirements.txt 是否变更，未变更则跳过）
$depsMarker = ".venv\.deps_installed"
$reqHash = (Get-FileHash "requirements.txt" -Algorithm SHA256).Hash
$skipInstall = $false
if (Test-Path $depsMarker) {
    $oldHash = (Get-Content $depsMarker -Raw).Trim()
    if ($oldHash -eq $reqHash) {
        $skipInstall = $true
    }
}
if (-not $skipInstall) {
    Write-Host "正在安装依赖 ..."
    try {
        # -qq 级静默：抑制 pip 版本通知和下载进度条
        pip install -qq -r requirements.txt
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path $depsMarker -Value $reqHash
        }
    } catch {
        Write-Host "错误: 安装依赖失败。" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "依赖已安装，跳过 pip install（requirements.txt 未变更）" -ForegroundColor DarkGray
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
    & $pythonCmd src\python\tui\tui.py
} catch {
    Write-Host "错误: 程序运行失败: $_" -ForegroundColor Red
}
