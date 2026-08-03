# 快速开始

## 方式一：启动脚本（推荐）

```bash
# Windows PowerShell
.\scripts\launch.ps1

# Linux
./scripts/launch.sh
```

启动脚本自动完成：Python 检测 → 虚拟环境创建 → 依赖安装 → 目录创建 → 运行主程序。

> **安装验证**：启动脚本执行后首次运行菜单 **E** 生成基础报告。如报告成功生成到 `reports/` 目录，则安装正确。如遇报错，检查 `logs/app.log` 中最近的 ERROR 行。

> **💡 外部虚拟环境管理：** 设置环境变量 `VENV_PATH` 可将 `.venv` 放在项目目录外部，
> 方便多个项目共享或集中管理虚拟环境：
> ```bash
> # Windows PowerShell
> $env:VENV_PATH = "D:\shared\venvs\investor-util"
> .\scripts\launch.ps1
>
> # Linux
> VENV_PATH=/opt/venvs/investor-util ./scripts/launch.sh
> ```
> 首次运行自动创建并链接，再次运行直接复用。

## 方式二：手动运行

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
# Windows:
.venv\Scripts\Activate.ps1
# Linux:
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动 TUI 交互模式
python -m src.python.tui
```

## 方式三：CLI 命令行模式

CLI 模式无需 TUI 界面，通过参数驱动，适合定时任务和脚本化使用：

```bash
# 查看帮助
python -m src.python.cli --help

# 基础 Excel 报告
python -m src.python.cli report --type basic

# 全量报告（含 LLM）
python -m src.python.cli report --type full --history auto

# 更新缓存
python -m src.python.cli cache --update all

# 查看缓存状态
python -m src.python.cli cache --stats

# 调仓 What-if 模拟（对比两份持仓，生成独立 diff 报告）
python -m src.python.cli whatif --base data/holdings/调仓前.xlsx --candidate data/holdings/调仓后.xlsx

# 详细模式（终端显示彩色进度前缀）
python -m src.python.cli --verbose report --type basic
```

> CLI 模式与 TUI 模式共享同一套缓存和配置文件，两种模式可交替使用。

### CLI 命令参考

**全局参数**（位于子命令之前）：

| 参数 | 说明 |
|:-----|:-----|
| `--config PATH` | 配置文件路径，默认 `data/config/config.json` |
| `--output DIR` | 报告输出目录，覆盖 `config.json` 中的 `output_dir` |
| `--verbose` | 详细日志输出到 stderr（默认仅写入 `logs/app.log`） |
| `--version` | 显示版本号并退出 |

**`report` 子命令**：

| 参数 | 说明 |
|:-----|:-----|
| `--type {basic,both,full}` | `basic`=仅 Excel 报告（约 1 分钟，默认）；`both`=Excel+HTML（不含 LLM，约 2 分钟）；`full`=全量含 LLM（约 5 分钟，需 LLM 配置） |
| `--history {auto,off}` | 是否获取组合历史走势：`auto`=获取，`off`=跳过（默认）。仅 `--type both` / `full` 时有效 |
| `--force-llm` | 强制重新调用 LLM API（忽略缓存），生成最新 LLM 内容 |
| `--warm` | 报告生成前预热缓存（首次使用或新增持仓时推荐） |

**`cache` 子命令**：

| 参数 | 说明 |
|:-----|:-----|
| `--update {basic,position,all}` | `basic`=更新基础类缓存（基金业绩、行业分类、新闻等）；`position`=更新持仓类缓存（价格行情、指数）；`all`=全部更新 |
| `--clean` | 按 TTL 删除过期缓存文件 |
| `--stats` | 查看缓存状态统计（文件数、总大小、过期文件预览等） |

**`whatif` 子命令**（调仓 What-if 模拟，独立报告）：

| 参数 | 说明 |
|:-----|:-----|
| `--base PATH` | 基准持仓文件（调仓前）。缺省使用 `config.json` 的 `holdings_dir` + `holdings_filename` |
| `--candidate PATH` | 目标持仓文件（调仓后/假设），**必填** |

对比两份持仓生成独立调仓 diff 报告（Excel 3 页签 + HTML 双栏对比页），产物命名 `调仓模拟_{时间戳}` 输出到报告输出目录。全程本地计算、零网络请求，不并入主报告管线。

**使用示例**：

```bash
# 生成全量报告，预热缓存，强制重新调用 LLM
python -m src.python.cli --verbose report --type full --history auto --warm --force-llm

# 基础 Excel 报告，输出到指定目录
python -m src.python.cli --output D:/my_reports report --type basic

# 使用自定义配置文件
python -m src.python.cli --config D:/config/my_config.json cache --stats

# 调仓 What-if：基准用配置默认持仓，目标指定另一份文件
python -m src.python.cli whatif --candidate D:/holdings/调仓方案.xlsx

# 调仓 What-if：显式指定两份持仓
python -m src.python.cli whatif --base D:/holdings/当前.xlsx --candidate D:/holdings/方案B.xlsx
```

**数据源健康检查**（直接通过主程序运行，无需 TUI 界面）：

```bash
# 测试各数据源联通性并报告延迟
python -m src.python.cli check-sources
```

定时任务配置详见[定时任务配置指南](how-to-schedule.md)。

---

## 持仓文件格式

支持 `.xlsx` 格式，每页工作表为一个独立账户（页签名即账户名）：

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| 名称 | 文本 | 股票/基金名称 | 长江电力 |
| 代码 | 文本 | 证券代码 | 600900 |
| 持仓份额 | 数值 | 持有股数/份额 | 800 |
| 每份成本 | 数值 | 单位成本价 | 17.65 |

**格式要求：**
- 列名必须完全匹配 **名称、代码、持仓份额、每份成本**
- 每份成本 ≥ 0（允许零成本，如赠股），持仓份额 > 0
- 暂无数据的行留空即可，程序自动跳过
- 最新价和昨收盘价由程序自动从 API 获取，无需填入表格

### 持仓数据处理流程

每次执行 **任何菜单命令**（E / B / L）时：

1. **读取 Excel** — 程序调用 `openpyxl` 重新打开持仓文件，解析每页工作表中的持仓明细
2. **内存中转** — 读取后的持仓数据仅以 Python 对象形式驻留在本次操作的内存中，操作完成后即释放
3. **不落盘缓存** — 持仓原始数据**不会**写入 `data/cache/`，也不存储到任何数据库文件
4. **缓存的是 API 响应** — `data/cache/` 中缓存的是外部数据源返回的价格行情、行业分类、基金业绩、新闻、LLM 分析结果，而非持仓本身

**这意味着：你每次更新 `个人投资持仓信息.xlsx` 后，程序总能读到最新数据**，无需手动刷新或同步。

当持仓文件新增了代码（如新买了一只股票），程序会自动触发该代码的行情预热缓存（首次使用时自动获取并缓存行情数据），后续操作即复用缓存。

> 提示：如果需要同时维护多份不同的持仓方案，可在 `holdings_dir` 目录下放置多个 `.xlsx` 文件，程序会列出所有文件供选择。典型的方案包含以下账户示例：**证券账户**（场内股票/ETF）、**支付宝-基金投资账户**（场外基金）、**微信-基金投资账户**（债券基金）、**银行-基金投资账户**（QDII 基金）。

---

## 菜单操作速览

```
  > [E] 生成基础版Excel分析报告
    [B] 生成标准报告(Excel+HTML) [按章节配置]
    [L] 生成完整报告(Excel+HTML) [含LLM，按章节配置]
    [W] 调仓 What-if 模拟（对比两份持仓，独立报告）
    [C] 配置持仓信息目录    [F] 配置持仓信息文件名
    [O] 配置报告输出目录
    [1] 更新基础类缓存        [2] 更新行情类缓存
    [3] 清理过期缓存文件     [4] 查看缓存/状态统计
    [P] 配置报告可选章节    [I] 管理对比指数池
    [A] 配置持仓匿名化        [S] 配置LLM分析章节
    [R] 刷新配置               [X] 退出
```

各报告生成菜单的范围差异：

| 内容 | E | B | L |
|:-----|:-:|:-:|:-:|
| 核心报告（投资分析汇总/市值/分类/穿透/基金业绩/数据源可用性矩阵） | ✅ | ✅ | ✅ |
| 财经新闻与关联分析 | — | ✅ | ✅ |
| 基金深度分析 | — | ☆ | ☆ |
| 组合历史走势 + 回撤分析 | — | ☆ | ☆ |
| LLM 全模块分析 | — | — | ☆ |

> ☆ 表示受章节可见性配置控制。各菜单的详细说明参见 [菜单操作手册](how-to-menu.md)。
>
> **W（调仓 What-if 模拟）** 不在此表中：它对比两份持仓生成独立 diff 报告（Excel + HTML），不并入主报告管线。

> 建议首次使用直接按 **L** 生成全量报告。

---

## 下一步

- [菜单操作详解](how-to-menu.md) — 各菜单完整说明
- [配置指南](how-to-config.md) — 调整数据源、缓存、预警等参数
- [LLM 配置指引](how-to-config-llm.md) — 接入 LLM 分析
- [常见问题解答](faq.md) — 使用中的高频问题
