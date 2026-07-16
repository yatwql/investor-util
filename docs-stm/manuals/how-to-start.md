# 快速开始

## 方式一：启动脚本（推荐）

```bash
# Windows PowerShell
.\scripts\launch.ps1

# Linux
./scripts/launch.sh
```

启动脚本自动完成：Python 检测 → 虚拟环境创建 → 依赖安装 → 目录创建 → 运行主程序。

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

# （可选）Windows 用户若需终端彩色输出：
pip install colorama

# 4. 启动 TUI 交互模式
python src/python/main.py
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

# 详细模式（终端显示彩色进度前缀）
python -m src.python.cli --verbose report --type basic
```

> CLI 模式与 TUI 模式共享同一套缓存和配置文件，两种模式可交替使用。

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

> 提示：如果需要同时维护多份不同的持仓方案，可在 `holdings_dir` 目录下放置多个 `.xlsx` 文件，程序会列出所有文件供选择。

### 示例数据
- **证券账户** — 场内股票/ETF
- **支付宝-基金投资账户** — 场外基金
- **微信-基金投资账户** — 债券基金
- **银行-基金投资账户** — QDII 基金

---

## 菜单操作速览

```
  > [E] 生成基础版Excel分析报告
    [B] 生成全系列包含新闻的报告(Excel+HTML)
    [L] 生成全系列完整版报告(Excel+HTML)
    [C] 配置持仓信息目录    [F] 配置持仓信息文件名
    [O] 配置报告输出目录
    [1] 更新基础类缓存        [2] 更新持仓类缓存
    [3] 清理过期缓存文件     [4] 查看缓存/状态统计
    [P] 配置报告板块可见性    [S] 配置支持LLM的章节
    [R] 刷新配置               [X] 退出
```

各报告生成菜单的范围差异：

| 内容 | E | B | L |
|:-----|:-:|:-:|:-:|
| 核心报告（投资分析汇总/市值/分类/穿透/基金业绩） | ✅ | ✅ | ✅ |
| 财经新闻与关联分析 | — | ✅ | ✅ |
| B 系列基金深度分析 | — | ☆ | ☆ |
| 智能预警（完整内容） | — | — | ✅ |
| 组合历史走势 + 回撤分析 | — | ☆ | ☆ |
| LLM 全模块分析 | — | — | ☆ |

> ☆ 表示受板块可见性配置控制。各菜单的详细说明参见 [菜单操作手册](how-to-menu.md)。

> 建议首次使用直接按 **L** 生成全量报告。

---

## 下一步

- [菜单操作详解](how-to-menu.md) — 各菜单完整说明
- [配置指南](how-to-config.md) — 调整数据源、缓存、预警等参数
- [LLM 配置指引](how-to-config-llm.md) — 接入 LLM 分析
- [常见问题解答](faq.md) — 使用中的高频问题
