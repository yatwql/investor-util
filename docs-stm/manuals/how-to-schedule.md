# 定时任务配置指南

CLI 命令行模式支持通过 Windows 任务计划程序或 Linux cron 定时自动驱动报告生成，无需人工操作 TUI 菜单。

---

## 1. 概述

CLI 入口：`.venv/bin/python -m src.python.cli [全局参数] <子命令> [子命令参数]`

### 常用命令速查

> CLI 完整参数列表见[快速开始](how-to-start.md#cli-命令参考)。以下为定时任务场景的常用命令。

| 用途 | 命令 |
|:-----|:-----|
| 生成基础 Excel 报告 | `.venv/bin/python -m src.python.cli report --type basic` |
| 生成全系列报告（不含 LLM） | `.venv/bin/python -m src.python.cli report --type both --history auto` |
| 生成全量完整报告 | `.venv/bin/python -m src.python.cli report --type full --history auto` |
| 更新全部缓存 | `.venv/bin/python -m src.python.cli cache --update all` |
| 更新基础类缓存 | `.venv/bin/python -m src.python.cli cache --update basic` |
| 更新持仓类缓存 | `.venv/bin/python -m src.python.cli cache --update position` |
| 清理过期缓存 | `.venv/bin/python -m src.python.cli cache --clean` |
| 查看缓存状态 | `.venv/bin/python -m src.python.cli cache --stats` |
| 查看性能历史趋势 | `.venv/bin/python scripts/perf_view.py` |

### 退出码含义

| 退出码 | 含义 | 说明 |
|:------:|:-----|:-----|
| 0 | 成功 | 报告生成或缓存操作全部成功 |
| 1 | 部分失败 | 部分模块失败（如 LLM key 缺失降级），主任务完成 |
| 2 | 严重错误 | 任务无法执行（如持仓文件不存在、配置格式错误） |
| 130 | 用户中断 | Ctrl+C 手动终止 |

---

## 2. Windows 任务计划程序

### 2.1 基础配置

使用 `schtasks` 命令创建定时任务，需指定 Python 解释器完整路径。

```batch
:: 每日 16:00 生成全量报告（盘后）
schtasks /CREATE /SC DAILY /TN "InvestReport" /TR "D:\path\to\investor-util\.venv\Scripts\python.exe D:\path\to\investor-util\src\python\cli\cli.py report --type full --history auto" /ST 16:00 /F

:: 每周一早 9:00 更新全部缓存
schtasks /CREATE /SC WEEKLY /D MON /TN "InvestCacheUpdate" /TR "D:\path\to\investor-util\.venv\Scripts\python.exe D:\path\to\investor-util\src\python\cli\cli.py cache --update all" /ST 09:00 /F
```

### 2.2 PowerShell 包装脚本（推荐）

推荐使用 PowerShell 包装脚本，方便日志记录和错误处理：

以下为自行创建的定时包装脚本示例（保存为 `scripts/scheduled_report.ps1`）：

```powershell
param(
    [string]$ReportType = "full",
    [string]$OutputDir = "reports"
)

$ProjectRoot = "D:\path\to\investor-util"
$LogFile = Join-Path $ProjectRoot "logs\cron.log"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    $env:PYTHONUNBUFFERED = "1"
    $result = & "$ProjectRoot\.venv\Scripts\python.exe" -m src.python.cli --output $OutputDir report --type $ReportType --history auto 2>&1
    $exitCode = $LASTEXITCODE

    "$Timestamp [exit=$exitCode] $result" | Out-File $LogFile -Append -Encoding UTF8

    if ($exitCode -gt 1) {
        exit $exitCode  # 严重错误时任务计划程序可配置重试
    }
} catch {
    "$Timestamp [ERR] $_" | Out-File $LogFile -Append -Encoding UTF8
    exit 2
}
```

### 2.3 防重入

任务计划程序本身提供防重入（上一个实例未完成时不启动新实例），但建议配合锁文件：

```batch
:: 锁文件 + 超时退避
schtasks /CREATE /SC DAILY /TN "InvestReport" /TR "powershell -NoProfile -Command \"if (-not (Test-Path '$env:TEMP\invest.lock')) { New-Item '$env:TEMP\invest.lock' -Force | Out-Null; try { D:\path\to\investor-util\.venv\Scripts\python.exe -m src.python.cli report --type full --history auto } finally { Remove-Item '$env:TEMP\invest.lock' -ErrorAction SilentlyContinue } }\"" /ST 16:00
```

---

## 3. Linux crontab

### 3.1 基础配置

```bash
# 编辑 crontab
crontab -e

# 每日 16:00 生成全量报告
0 16 * * * cd /home/user/investor-util && .venv/bin/python -m src.python.cli report --type full --history auto >> logs/cron.log 2>&1

# 每周一早 9:00 更新全部缓存
0 9 * * 1 cd /home/user/investor-util && .venv/bin/python -m src.python.cli cache --update all >> logs/cron.log 2>&1

# 每月 1 号清理缓存
0 10 1 * * cd /home/user/investor-util && .venv/bin/python -m src.python.cli cache --clean >> logs/cron.log 2>&1
```

### 3.2 flock 防重入

对于耗时较长的 `report --type full`，使用 `flock` 防止并发：

```bash
# 使用 flock 锁文件防重入
0 16 * * * cd /home/user/investor-util && flock -n /tmp/invest.lock .venv/bin/python -m src.python.cli report --type full --history auto >> logs/cron.log 2>&1
```

---

## 4. 最佳实践

### 4.1 日志轮转

应用日志已自动轮转（`logs/app.log`，单文件最大 10 MB，保留 5 份备份），**无需额外配置**。

cron/stderr 日志建议自行配置 logrotate：

```bash
# /etc/logrotate.d/investor-util
/home/user/investor-util/logs/cron.log {
    monthly
    rotate 6
    compress
    missingok
    notifempty
}
```

### 4.2 缓存预热策略

首次运行或新增持仓后，建议先预热缓存再生成报告：

```bash
# 先更新缓存，再生成报告
.venv/bin/python -m src.python.cli cache --update all
.venv/bin/python -m src.python.cli --output ./reports report --type basic

# 或者使用 --warm 在报告生成时预热
.venv/bin/python -m src.python.cli report --type full --warm --history auto
```

### 4.3 报告输出路径

通过 `--output DIR` 全局参数指定报告输出目录，覆盖 `config.json` 中的 `output_dir` 配置。输出目录支持绝对路径和相对路径：

```bash
# 输出到默认 reports/ 目录（使用 config.json 配置）
.venv/bin/python -m src.python.cli report --type full --history auto

# 输出到指定目录
.venv/bin/python -m src.python.cli --output D:/backup/reports report --type basic

# 输出到网络共享目录（需确保程序有写入权限）
.venv/bin/python -m src.python.cli --output \\NAS\invest\reports report --type basic
```

> 输出目录不存在时程序会自动创建。定时任务中建议使用绝对路径，避免因工作目录不确定导致的路径问题。

### 4.4 网络退避策略

Provider Chain 已内置三次重试 + 熔断机制，网络临时故障时自动降级使用过期缓存。

- 短时网络抖动 → 自动重试（3 次）
- 数据源持续不可用 → 熔断器开启 → 使用过期缓存
- 报告在无网络环境下降级生成（exit=1，部分数据为空）

### 4.5 性能历史自动收集

每次 CLI 报告生成时，系统自动记录两方面的性能数据到 `data/state/` 目录：

| 文件 | 内容 | 查看方式 |
|:-----|:------|:---------|
| `perf_history.jsonl` | 各阶段耗时（行情/数据准备/HTML/Excel/LLM 等），含版本号和持仓数量 | `.venv/bin/python scripts/perf_view.py` |
| `datasource_health.jsonl` | 全量数据源 HTTP 连通性检查结果 + 延迟 | 同上命令（同文件含来源格式） |

这些记录自动积累，可用于跨版本性能退化检测和异常波动排查，无需手动触发。

### 4.6 退出码速查

| 场景 | 退出码 | 处理建议 |
|:-----|:------:|:---------|
| 正常完成 | 0 | 无需处理 |
| LLM key 缺失降级 | 1 | 如需 LLM 内容，配置 `llm_key.json` |
| 部分数据源失败 | 1 | 检查网络，下次调度自动恢复 |
| 持仓文件不存在 | 2 | 检查 `config.json` 中 `holdings_dir` / `holdings_filename` 配置 |
| 配置格式错误 | 2 | 运行 `.venv/bin/python -c "import json; json.load(open('data/config/config.json'))"` 检查 |
| 用户中断 | 130 | 手动终止，无需处理 |

---

## 5. 故障排查

### 5.1 检查日志

```bash
# 查看应用日志（最近 20 行）
tail -20 logs/app.log

# 查看 cron 输出
tail -20 logs/cron.log
```

### 5.2 手动测试

先手动执行确认命令正常工作：

```bash
# 快速验证
.venv/bin/python -m src.python.cli cache --stats
.venv/bin/python -m src.python.cli report --type basic
```

### 5.3 常见问题

| 问题 | 排查 |
|:-----|:-----|
| 定时任务未执行 | 检查任务计划程序历史记录 / cron 服务状态 |
| 报告为空 | 检查持仓文件路径和格式 |
| 缓存未更新 | 检查网络连接，`cache --stats` 查看缓存状态 |
| Python 找不到模块 | 确保工作目录为项目根目录（`cd` 到 `investor-util/`） |
