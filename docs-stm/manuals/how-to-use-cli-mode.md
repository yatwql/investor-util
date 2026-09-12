# CLI 命令行模式使用指南

CLI 命令行模式无需 TUI 菜单界面，通过命令行参数驱动，适合**定时任务、脚本化批量生成、服务器 / 无桌面环境**使用。本文从用户角度完整介绍 CLI 模式的命令结构、子命令参数与使用技巧。

> **入口**：`.venv/bin/python -m src.python.cli [全局参数] <子命令> [子命令参数]`
> **定时任务**：配合 Windows 任务计划程序 / Linux cron 自动运行，见本文 [§13 定时任务](#13-定时任务)。

---

## 1. 命令结构

CLI 命令分两层：**全局参数**（位于子命令之前）+ **子命令**（`report` / `cache` / `whatif` / `check-sources` / `view-logs` / `doctor` / `cassettes`）。

> 其中 `cassettes` 是**开发维护命令**（列出/校验已录制的数据源真实响应，供离线回归使用），日常使用报告功能不需要它——详见 [开发者指南](../managements/developer-guide.md) → CLI 子命令。

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
| `--experiment NAME` | 启用**实验组**功能（只开不关的简写），**仅本次运行生效（不写入 features.json）**。可重复指定；`NAME` 取开关名（如 `signal_pre_digest`）或显示名（如 `信号预消化`），`all` = 全部启用 |
| `--feature NAME=VALUE` | 切换**任意**功能开关（实验组与常规组均可），**双向**（可开可关）、**仅本次运行生效（不写入 features.json）**。可重复指定；`NAME` 取开关名（如 `doctor_check`），`VALUE` 取 `on`/`off`（也接受 `true`/`false`/`1`/`0`，大小写不敏感）。同名后写覆盖先写 |
| `--version` | 显示版本号并退出 |

> **`--experiment` 说明**：等价于在 TUI 菜单 **[S]** / Web 配置面板中临时勾选实验开关，但**只作用于当前这一次命令、不改动持久化配置**——CI / 定时任务可在不污染用户配置的前提下试用实验功能；反之，用户配置里已开启的实验开关不会被本参数关闭。
>
> ```bash
> # 单次运行启用信号预消化
> .venv/bin/python -m src.python.cli --experiment signal_pre_digest report --type full
>
> # 用显示名指定、可重复叠加
> .venv/bin/python -m src.python.cli --experiment 决策跨期反思闭环 --experiment 模块级质量分级 report --type full
>
> # 单次启用决策头结构化（受控 JSON 决策头，抽取侧优先读结构化、失败回落表格解析）
> .venv/bin/python -m src.python.cli --experiment decision_header_parse report --type full
>
> # 单次启用确定性信号沉淀（五类确定性评级入账，附实时/非实时标签）
> .venv/bin/python -m src.python.cli --experiment signal_ledger report --type full
>
> # 本次运行启用全部实验功能
> .venv/bin/python -m src.python.cli --experiment all report --type full
> ```
>
> 取值写错会立即报错并列出全部可选值，不会静默忽略。当前可选实验功能清单见[配置指引-功能开关 §M](how-to-config.md#m-功能开关featuresjson)（与 TUI 菜单 [S] 实验块同源，由 `features.feature_switch_registry` 注册表驱动）。

> **`--feature` 说明**：`--experiment` 的补集——它面向**全部**开关而非仅实验组，且**双向**（既能开也能关）。常用来在不动持久化配置的前提下临时关闭某个默认开启的常规开关，或复现「关掉某开关后报告长什么样」：
>
> ```bash
> # 本次运行关闭系统自检的界面入口（CLI 的 doctor 子命令本就不受该开关约束）
> .venv/bin/python -m src.python.cli --feature doctor_check=off doctor
>
> # 一次运行关掉两个量化指标 + 关闭交互图表（HTML 回退静态渲染）
> .venv/bin/python -m src.python.cli --feature metrics_hhi=off --feature metrics_beta=off --feature enable_interactive_charts=off report --type full
> ```
>
> 两个参数可同时使用：`--feature` 在 `--experiment` 之后应用，故 `--experiment all --feature module_quality_gate=off` 表示「其余实验功能全开、只关掉质量分级」。

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

## 8. `doctor` 子命令（系统自检）

一键盘点运行环境，分组报告 **环境 / 配置 / 目录 / 功能开关 / 数据源适配 / 数据源凭据 / 数据源** 七类检查结果，**失败项附可执行修复建议**。适合新机部署、报告跑不起来、怀疑配置损坏时先跑一遍。

```bash
.venv/bin/python -m src.python.cli doctor
```

| 参数 | 说明 |
|:-----|:-----|
| `--offline` | 跳过联网检查（数据源连通性），纯本地自检、秒级返回 |
| `--timeout SECONDS` | **网络检查整体**的耗时预算（默认 8 秒；对全部联网检查共用一个预算，防止慢速数据源拖住自检） |

```bash
# 纯本地自检（不联网）
.venv/bin/python -m src.python.cli doctor --offline

# 放宽联网检查预算到 20 秒
.venv/bin/python -m src.python.cli doctor --timeout 20
```

**与其它子命令的两点不同**：

1. **无需配置**——自检在加载配置**之前**执行。配置损坏正是它要诊断的场景，因此不会因配置读不出来而拒绝运行。
2. **不受开关约束**——`doctor` 子命令始终可用，无需任何开关。`doctor_check` 开关（默认开启）只控制 TUI 菜单项与 Web 自检卡片这两个日常入口的可见性（同理：若 CLI 也被开关拦住，就会陷入「开开关要先读配置、读配置失败又要开开关」的死锁）。

**退出码**：`0` = 全部检查通过；`1` = 自检跑完了但**存在失败项**（注意：这不是「命令失败」，而是一条诊断结论，脚本可用它判定环境是否可用）。

> 日常也可从 TUI 菜单 **[D]** 或 Web「系统自检」卡片触发同一套检查，三端共用 `core/doctor.py`。

---

## 9. 使用示例

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

## 10. 常用命令速查

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
| 系统自检（一键体检） | `.venv/bin/python -m src.python.cli doctor --offline` |
| 查看性能历史趋势 | `.venv/bin/python scripts/perf-view.py` |

### 10.1 TUI 菜单 → CLI 命令对照

TUI 菜单与 CLI 子命令落到**同一个业务编排函数**（`report/orchestrator.py::generate_report` 等），差别只在入参从哪来：TUI 在菜单里问，CLI 用参数传。下表按菜单项逐项对照。

| TUI 菜单 | CLI 等价命令 |
|:---------|:-------------|
| **[E]** 生成基础版 Excel 分析报告 | `report --type basic` |
| **[B]** 生成标准报告（Excel+HTML） | `report --type both --history auto` |
| **[L]** 生成完整报告（Excel+HTML，含 LLM） | `report --type full --history auto` |
| **[W]** 调仓 What-if 模拟 | `whatif --base <调仓前.xlsx> --candidate <调仓后.xlsx>` |

以 `[L]` 为例，逐项拆开看更直观：

| `[L]` 触发时 TUI 的行为 | CLI 对应参数 | 说明 |
|:------------------------|:-------------|:-----|
| 生成类型固定为 `full` | `--type full` | 报告类型默认是 `basic`，务必显式指定 |
| 询问「是否获取组合历史走势数据」 | `--history auto` / `--history off` | 省略 `--history` 时按 `config.json` 的 `history.fetch_mode` 解析（`off` 跳过，`auto`/`prompt` 均视为获取） |
| 询问「是否强制重新生成 LLM 内容」 | `--force-llm` | 不加则复用 LLM 缓存 |
| 首次运行交互式引导 | `--non-interactive` | 跳过引导，定时任务/脚本建议带上 |
| 结束打印 LLM 会话用量 | —（打印耗时汇总） | 两条路径的收尾输出不同，不影响产物 |

所以 `[L]` 的完整等价命令是：

```bash
.venv/bin/python -m src.python.cli --non-interactive report --type full --history auto
# 若要连同「强制重生成 LLM」一起答上（等价于询问时答 y）：
.venv/bin/python -m src.python.cli --non-interactive report --type full --history auto --force-llm
```

两点需要留意（TUI 与 CLI 在这些情况下的行为差异，均不影响报告内容）：

1. **`history.fetch_mode = "prompt"` 时**：TUI 会停下来问；CLI 省略 `--history` 时按「获取」处理（非交互场景无从询问）。
2. **`enable_history = false` 时**：历史走势整体不获取，此时加 `--history auto` 也不会生效——外层开关优先于本参数。TUI 与 CLI 行为一致。

### 10.2 一键快捷入口

若只想要 `[L]` 这一件事，`scripts/llm.sh`（Linux/macOS）与 `scripts/llm.ps1`（Windows）把子命令与报告类型写死在脚本里，免去每次敲 `report --type full`：

```bash
./scripts/llm.sh                  # 生成完整报告（含 LLM）
./scripts/llm.sh --force-llm      # 强制重新调用 LLM，跳过缓存
./scripts/llm.sh --history off    # 本次不获取组合历史走势
```

追加的参数即 `report` 的报告级参数。需要全局参数（`--config` / `--output` / `--experiment` / `--feature`）时仍走 `cli.sh` / `cli.ps1`——它们必须写在子命令之前。

其余菜单项（配置类、缓存类、日志/健康/自检）在 CLI 侧均有独立子命令，见上方速查表与各节说明。

---

## 11. 退出码含义

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
| 配置格式错误 | 2 | 运行 `.venv/bin/python -c "import json; json.load(open('data/config/config.json'))"` 检查；或先跑 `doctor`（无需配置即可运行）定位 |
| 自检有失败项 | 1 | `doctor` 子命令专用：命令跑完了但检查未全过，按失败项附带的修复建议处理 |
| 用户中断 | 130 | 手动终止，无需处理 |

---

## 12. 最佳实践

### 12.1 缓存预热

首次运行或新增持仓后，建议先更新缓存再生成报告：

```bash
# 先更新缓存，再生成报告
.venv/bin/python -m src.python.cli cache --update all
.venv/bin/python -m src.python.cli --output ./reports report --type basic
```

### 12.2 报告输出路径

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

### 12.3 网络退避策略

Provider Chain 已内置三次重试 + 熔断机制，网络临时故障时自动降级使用过期缓存：

- 短时网络抖动 → 自动重试（3 次）
- 数据源持续不可用 → 熔断器开启 → 使用过期缓存
- 报告在无网络环境下降级生成（exit=1，部分数据为空）

### 12.4 性能历史自动收集

每次 CLI 报告生成时，系统自动记录性能数据到 `data/state/` 目录：

| 文件 | 内容 | 查看方式 |
|:-----|:------|:---------|
| `perf_history.jsonl` | 各阶段耗时（行情/数据准备/HTML/Excel/LLM 等），含版本号和持仓数量 | `.venv/bin/python scripts/perf-view.py` |
| `datasource_health.jsonl` | 全量数据源 HTTP 连通性检查结果 + 延迟 | 同上命令 |

这些记录自动积累，可用于跨版本性能退化检测和异常波动排查，无需手动触发。

### 12.5 日志轮转

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

## 13. 定时任务

CLI 模式配合操作系统定时任务可实现无人值守的自动报告生成（定时驱动报告 / 更新缓存），无需人工操作 TUI 菜单。定时任务中建议使用**绝对路径**（避免工作目录不确定）与 `--non-interactive`（跳过首次运行引导）。

### 13.1 Windows 任务计划程序

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

### 13.2 Linux crontab

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

### 13.3 定时任务排障

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

## 14. 更多参考

- [快速开始](how-to-start.md)「方式三」—— CLI 启动简介
- [TUI 菜单操作手册](how-to-use-tui-menu.md) —— TUI 等效操作（各菜单详解）
- [常规配置指引](how-to-config.md) —— 全部配置项语义与默认值
