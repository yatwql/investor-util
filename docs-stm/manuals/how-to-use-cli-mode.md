# CLI 命令行模式使用指南

CLI 命令行模式无需 TUI 菜单界面，通过命令行参数驱动，适合**定时任务、脚本化批量生成、服务器 / 无桌面环境**使用。本文从用户角度完整介绍 CLI 模式的命令结构、子命令参数与使用技巧。

> **入口**：`.venv/bin/python -m src.python.cli [全局参数] <子命令> [子命令参数]`
> **定时任务**：配合 Windows 任务计划程序 / Linux cron 自动运行，见本文 [§12 定时任务](#12-定时任务)。

---

## 1. 命令结构

CLI 命令分两层：**全局参数**（位于子命令之前）+ **子命令**（`report` / `cache` / `whatif` / `check-sources` / `view-logs`）。

```bash
# 查看帮助
.venv/bin/python -m src.python.cli --help

# 查看子命令帮助
.venv/bin/python -m src.python.cli report --help
```

CLI 与 TUI 共享同一套缓存、配置与报告管线，可交替使用。

---

## 2. 全局参数

| 参数 | 说明 |
|:-----|:-----|
| `--config PATH` | 配置文件路径，默认 `data/config/config.json` |
| `--output DIR` | 报告输出目录，覆盖 `config.json` 中的 `output_dir`（不存在时自动创建；支持绝对 / 相对路径） |
| `--verbose` | 详细日志输出到 stderr（默认仅写入 `logs/app.log`） |
| `--non-interactive` | 跳过首次运行交互式引导（定时任务 / 脚本使用） |
| `--version` | 显示版本号并退出 |

---

## 3. `report` 子命令（生成报告）

| 参数 | 说明 |
|:-----|:-----|
| `--type {basic,both,full}` | `basic`=仅 Excel 报告（约 1 分钟，默认）；`both`=Excel+HTML（不含 LLM，约 2 分钟）；`full`=全量含 LLM（约 5 分钟，需 LLM 配置） |
| `--history {auto,off}` | 是否获取组合历史走势：`auto`=获取，`off`=跳过。未指定时按配置 `history.fetch_mode`（默认 `auto`）。仅 `--type both` / `full` 时有效 |
| `--force-llm` | 强制重新调用 LLM API（忽略缓存），生成最新 LLM 内容 |

---

## 4. `cache` 子命令（缓存管理）

| 参数 | 说明 |
|:-----|:-----|
| `--update {basic,position,all}` | `basic`=更新基础类缓存（基金业绩、行业分类、新闻等）；`position`=更新持仓类缓存（价格行情、指数）；`all`=全部更新 |
| `--clean` | 按 TTL 删除过期缓存文件 |
| `--stats` | 查看缓存状态统计（文件数、总大小、过期文件预览等） |

---

## 5. `whatif` 子命令（调仓 What-if 模拟）

对比两份持仓生成独立调仓 diff 报告（Excel 3 页签 + 指定生效日时第 4 页签「时序回测」+ HTML 双栏对比页），产物输出到报告输出目录：最新版固定名 `调仓模拟.xlsx` / `调仓模拟.html`（每次覆盖为最新对比），历史归档至 `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx/.html` 日期子目录（超 180 天自动清理）。默认全程本地计算、零网络请求，不并入主报告管线。

| 参数 | 说明 |
|:-----|:-----|
| `--base PATH` | 基准持仓文件（调仓前）。缺省使用 `config.json` 的 `holdings_dir` + `holdings_filename` |
| `--candidate PATH` | 目标持仓文件（调仓后/假设），**必填** |
| `--effective-date YYYY-MM-DD` | 调仓生效日（可选）。指定后 opt-in 联网取生效日后行情，追加时序回测（区间/年化收益、波动率、夏普、最大回撤） |

> 指定 `--effective-date` 时联网取历史做假设推演（不构成收益承诺），数据不足时回测降级不阻塞主报告。

---

## 6. `check-sources` 子命令（数据源健康检查）

测试各行情数据源联通性并报告延迟，无需生成报告：

```bash
.venv/bin/python -m src.python.cli check-sources
```

---

## 7. `view-logs` 子命令（结构化日志查看）

按级别/行数/时间范围查看最近运行日志，无需生成报告，也**无需配置**（读取逻辑不依赖 config——配置损坏时仍可查日志诊断）。日志路径取自运行期 `logs/app.log`。

| 参数 | 说明 |
|:-----|:-----|
| `--level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` | 最小级别阈值，只显示该级别及以上的日志 |
| `--lines N` | 读取末尾行数上限（默认 5000） |
| `--since PREFIX` | 只显示时间前缀 >= 该值的记录（如 `2026-08-16 12:00`） |
| `--until PREFIX` | 只显示时间前缀 <= 该值的记录 |

```bash
# 查看最近 200 行
.venv/bin/python -m src.python.cli view-logs --lines 200

# 只看 ERROR 及以上
.venv/bin/python -m src.python.cli view-logs --level ERROR

# 查看指定时间段
.venv/bin/python -m src.python.cli view-logs --since "2026-08-16 12:00" --until "2026-08-16 13:00"
```

每条输出格式：`time [LEVEL] message`，多行正文（如 traceback）缩进展示。

---

## 8. 使用示例

```bash
# 生成全量报告，强制重新调用 LLM
.venv/bin/python -m src.python.cli --verbose report --type full --history auto --force-llm

# 基础 Excel 报告，输出到指定目录
.venv/bin/python -m src.python.cli --output D:/my_reports report --type basic

# 使用自定义配置文件
.venv/bin/python -m src.python.cli --config D:/config/my_config.json cache --stats

# 调仓 What-if：基准用配置默认持仓，目标指定另一份文件
.venv/bin/python -m src.python.cli whatif --candidate D:/holdings/调仓方案.xlsx

# 调仓 What-if：显式指定两份持仓
.venv/bin/python -m src.python.cli whatif --base D:/holdings/当前.xlsx --candidate D:/holdings/方案B.xlsx

# 调仓 What-if：指定生效日，追加时序回测
.venv/bin/python -m src.python.cli whatif --base D:/holdings/当前.xlsx --candidate D:/holdings/方案B.xlsx --effective-date 2026-07-01

# 更新全部缓存
.venv/bin/python -m src.python.cli cache --update all

# 查看缓存状态
.venv/bin/python -m src.python.cli cache --stats

# 查看最近 200 行运行日志（只看 ERROR）
.venv/bin/python -m src.python.cli view-logs --lines 200 --level ERROR

# 查看性能历史趋势
.venv/bin/python scripts/perf-view.py
```

---

## 9. 常用命令速查

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
| 数据源健康检查 | `.venv/bin/python -m src.python.cli check-sources` |
| 查看最近运行日志 | `.venv/bin/python -m src.python.cli view-logs --level WARNING` |
| 查看性能历史趋势 | `.venv/bin/python scripts/perf-view.py` |

---

## 10. 退出码含义

| 退出码 | 含义 | 说明 |
|:------:|:-----|:-----|
| 0 | 成功 | 报告生成或缓存操作全部成功 |
| 1 | 部分失败 | 部分模块失败（如 LLM key 缺失降级），主任务完成 |
| 2 | 严重错误 | 任务无法执行（如持仓文件不存在、配置格式错误） |
| 130 | 用户中断 | Ctrl+C 手动终止 |

| 场景 | 退出码 | 处理建议 |
|:-----|:------:|:---------|
| 正常完成 | 0 | 无需处理 |
| LLM key 缺失降级 | 1 | 如需 LLM 内容，配置 `llm_key.json` |
| 部分数据源失败 | 1 | 检查网络，下次调度自动恢复 |
| 持仓文件不存在 | 2 | 检查 `config.json` 中 `holdings_dir` / `holdings_filename` 配置 |
| 配置格式错误 | 2 | 运行 `.venv/bin/python -c "import json; json.load(open('data/config/config.json'))"` 检查 |
| 用户中断 | 130 | 手动终止，无需处理 |

---

## 11. 最佳实践

### 11.1 缓存预热

首次运行或新增持仓后，建议先更新缓存再生成报告：

```bash
# 先更新缓存，再生成报告
.venv/bin/python -m src.python.cli cache --update all
.venv/bin/python -m src.python.cli --output ./reports report --type basic
```

### 11.2 报告输出路径

通过 `--output DIR` 全局参数指定报告输出目录，覆盖 `config.json` 中的 `output_dir` 配置：

```bash
# 输出到默认 reports/ 目录（使用 config.json 配置）
.venv/bin/python -m src.python.cli report --type full --history auto

# 输出到指定目录
.venv/bin/python -m src.python.cli --output D:/backup/reports report --type basic

# 输出到网络共享目录（需确保程序有写入权限）
.venv/bin/python -m src.python.cli --output \\NAS\invest\reports report --type basic
```

> 定时任务中建议使用绝对路径，避免因工作目录不确定导致的路径问题。

### 11.3 网络退避策略

Provider Chain 已内置三次重试 + 熔断机制，网络临时故障时自动降级使用过期缓存：

- 短时网络抖动 → 自动重试（3 次）
- 数据源持续不可用 → 熔断器开启 → 使用过期缓存
- 报告在无网络环境下降级生成（exit=1，部分数据为空）

### 11.4 性能历史自动收集

每次 CLI 报告生成时，系统自动记录性能数据到 `data/state/` 目录：

| 文件 | 内容 | 查看方式 |
|:-----|:------|:---------|
| `perf_history.jsonl` | 各阶段耗时（行情/数据准备/HTML/Excel/LLM 等），含版本号和持仓数量 | `.venv/bin/python scripts/perf-view.py` |
| `datasource_health.jsonl` | 全量数据源 HTTP 连通性检查结果 + 延迟 | 同上命令 |

这些记录自动积累，可用于跨版本性能退化检测和异常波动排查，无需手动触发。

### 11.5 日志轮转

应用日志已自动轮转（`logs/app.log`，单文件最大 10 MB，保留 5 份备份），**无需额外配置**。

定时任务的 cron/stderr 日志建议自行配置 logrotate：

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

---

## 12. 定时任务

CLI 模式配合操作系统定时任务可实现无人值守的自动报告生成（定时驱动报告 / 更新缓存），无需人工操作 TUI 菜单。定时任务中建议使用**绝对路径**（避免工作目录不确定）与 `--non-interactive`（跳过首次运行引导）。

### 12.1 Windows 任务计划程序

#### 基础配置

使用 `schtasks` 命令创建定时任务，需指定 Python 解释器完整路径：

```batch
:: 每日 16:00 生成全量报告（盘后）
schtasks /CREATE /SC DAILY /TN "InvestReport" /TR "D:\path\to\investor-util\.venv\Scripts\python.exe D:\path\to\investor-util\src\python\cli\cli.py report --type full --history auto" /ST 16:00 /F

:: 每周一早 9:00 更新全部缓存
schtasks /CREATE /SC WEEKLY /D MON /TN "InvestCacheUpdate" /TR "D:\path\to\investor-util\.venv\Scripts\python.exe D:\path\to\investor-util\src\python\cli\cli.py cache --update all" /ST 09:00 /F
```

#### PowerShell 包装脚本（推荐）

推荐使用 PowerShell 包装脚本，方便日志记录和错误处理（自行创建 `scripts/scheduled_report.ps1`）：

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

#### 防重入

任务计划程序本身提供防重入（上一个实例未完成时不启动新实例），但建议配合锁文件：

```batch
:: 锁文件 + 超时退避
schtasks /CREATE /SC DAILY /TN "InvestReport" /TR "powershell -NoProfile -Command \"if (-not (Test-Path '$env:TEMP\invest.lock')) { New-Item '$env:TEMP\invest.lock' -Force | Out-Null; try { D:\path\to\investor-util\.venv\Scripts\python.exe -m src.python.cli report --type full --history auto } finally { Remove-Item '$env:TEMP\invest.lock' -ErrorAction SilentlyContinue } }\"" /ST 16:00
```

### 12.2 Linux crontab

#### 基础配置

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

#### flock 防重入

对于耗时较长的 `report --type full`，使用 `flock` 防止并发：

```bash
# 使用 flock 锁文件防重入
0 16 * * * cd /home/user/investor-util && flock -n /tmp/invest.lock .venv/bin/python -m src.python.cli report --type full --history auto >> logs/cron.log 2>&1
```

### 12.3 定时任务排障

**检查日志**：

```bash
# 查看应用日志（最近 20 行）
tail -20 logs/app.log

# 查看 cron 输出
tail -20 logs/cron.log
```

**手动测试**：先手动执行确认命令正常工作：

```bash
# 快速验证
.venv/bin/python -m src.python.cli cache --stats
.venv/bin/python -m src.python.cli report --type basic
```

**常见问题**：

| 问题 | 排查 |
|:-----|:-----|
| 定时任务未执行 | 检查任务计划程序历史记录 / cron 服务状态 |
| 报告为空 | 检查持仓文件路径和格式 |
| 缓存未更新 | 检查网络连接，`cache --stats` 查看缓存状态 |
| Python 找不到模块 | 确保工作目录为项目根目录（`cd` 到 `investor-util/`） |

---

## 13. 更多参考

- [快速开始](how-to-start.md)「方式三」—— CLI 启动简介
- [TUI 菜单操作手册](how-to-use-tui-menu.md) —— TUI 等效操作（各菜单详解）
- [常规配置指引](how-to-config.md) —— 全部配置项语义与默认值
