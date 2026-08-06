# scripts/cli.ps1 - 投资分析 CLI 命令行模式 (Windows)
# Encoding: UTF-8 with BOM (PowerShell requires BOM for Chinese chars)
#
# 无参数调用时默认生成报告（report 子命令，--type both，Excel+HTML 不含 LLM）；
# 传入参数时原样透传给 CLI，等价于 .venv\Scripts\python.exe -m src.python.cli <args>。
#
# 用法:
#   .\scripts\cli.ps1                        # 无参数 -> 默认生成报告（both）
#   .\scripts\cli.ps1 report --type full     # 生成全量报告（含 LLM）
#   .\scripts\cli.ps1 cache --stats          # 查看缓存状态
#   .\scripts\cli.ps1 --help                 # 查看 CLI 帮助

# 1. 定位项目根目录（脚本可从任意目录运行）
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

# 2. 使用项目虚拟环境解释器（禁止裸 python/python3）
$pythonBin = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonBin)) {
    Write-Host "[ERR] 未找到虚拟环境解释器: $pythonBin" -ForegroundColor Red
    Write-Host "[!]   请先运行 .\scripts\launch.ps1 完成虚拟环境初始化。" -ForegroundColor Yellow
    exit 1
}

# 3. 创建所需数据目录（与 launch.ps1 保持一致，非破坏性）
New-Item -ItemType Directory -Force -Path "data\holdings" | Out-Null
New-Item -ItemType Directory -Force -Path "data\cache" | Out-Null
New-Item -ItemType Directory -Force -Path "data\config" | Out-Null
New-Item -ItemType Directory -Force -Path "docs-stm\tmp" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

# 4. 无参数 -> 默认生成报告（both，Excel+HTML 不含 LLM）；否则原样透传
if ($args.Count -eq 0) {
    & $pythonBin -m src.python.cli report --type both
} else {
    & $pythonBin -m src.python.cli @args
}
exit $LASTEXITCODE
