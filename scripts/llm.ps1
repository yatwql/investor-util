# scripts/llm.ps1 - 一键生成完整报告（含 LLM 分析章节）(Windows)
# Encoding: UTF-8 with BOM (PowerShell requires BOM for Chinese chars)
#
# 固定使用 report --type full，等价于 TUI 菜单的「生成完整报告(Excel+HTML)
# [含LLM，按章节配置]」——省去每次敲子命令与报告类型。
#
# 组合历史走势不写死 --history，由配置 history.fetch_mode 决定（与 TUI 菜单
# 一致：off 跳过、auto 获取）；需要本地覆盖时追加 --history auto / --history off。
#
# 用法:
#   .\scripts\llm.ps1                        # 生成完整报告（含 LLM）
#   .\scripts\llm.ps1 --force-llm            # 强制重新调用 LLM，跳过缓存
#   .\scripts\llm.ps1 --history off          # 本次不获取组合历史走势
#
# 需要全局参数（--config / --output / --experiment / --feature 等）时用
# .\scripts\cli.ps1，它们必须写在 report 子命令之前。

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

# 4. 完整报告 + 追加参数（报告级参数如 --force-llm / --history 追加在后）
& $pythonBin -m src.python.cli report --type full @args
exit $LASTEXITCODE
