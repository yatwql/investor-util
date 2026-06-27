# 投资分析报告生成系统

个人投资者辅助工具：读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 Excel/HTML 格式的投资分析报告。

---

## 功能特性

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 对接腾讯财经（场内实时价）、东方财富（场外基金净值）
- **智能缓存** — API 响应按指定频率缓存，减少网络请求
- **Excel 报告** — 模块 1-5 核心报告 + 模块 6（财经新闻关联）增补功能（通过菜单 N/B/L 触发）
- **HTML 报告** — 模块 1-6 单页 HTML 渲染（含响应式 CSS、盈亏着色、新闻关联）；模块 7-8（全球政经、智囊团复盘）为 LLM 增补项目，通过菜单 L 触发
- **价格盈亏标识** — 正数红色、负数绿色（Excel/HTML 内自动着色）

> **当前版本**: 0.2.3（迭代开发中，详见 [changelog](managements/changelog.md)）
>
> **Iter 3.1 — HTML 报告引擎** ✅ 已完成 (2026-06-27)
> **Iter 3.2 — 财经新闻关联模块** ✅ 已完成 (2026-06-27)

---

## 快速开始

### 方式一：启动脚本（推荐）

```bash
# Windows PowerShell
.\scripts\launch.ps1

# Linux
./scripts/launch.sh
```

启动脚本自动完成：Python 检测 → 虚拟环境创建 → 依赖安装 → 目录创建 → 运行主程序。

### 方式二：手动运行

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

# 4. 启动
python src/main.py
```

---

## 持仓文件格式

支持 `.xlsx` 格式，每页工作表为一个独立账户：

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| 名称 | 文本 | 股票/基金名称 | 长江电力 |
| 代码 | 文本 | 证券代码 | 600900 |
| 持仓份额 | 数值 | 持有股数/份额 | 800 |
| 每份成本 | 数值 | 单位成本价 | 17.65 |

**格式要求**:
- 列名必须完全匹配（**名称、代码、持仓份额、每份成本**）
- 每份成本 > 0，持仓份额 > 0
- 暂无数据的行留空即可，程序自动跳过
- **注意**: 最新价和昨收盘价由程序自动从 API 获取，无需填入表格

### 示例数据

`data/holdings/` 目录下附带示例文件 `个人投资持仓信息.xlsx`，包含 4 个账户：
- **证券账户** — 场内股票/ETF（6 条）
- **支付宝-基金投资账户** — 场外基金（7 条）
- **微信-基金投资账户** — 债券基金（1 条）
- **银行-基金投资账户** — QDII 基金（1 条）

---

## 菜单操作

```
  > [E] 生成 EXCEL 分析报告
    [N] 生成包含新闻的 EXCEL 分析报告
    [H] 生成基础的HTML 分析报告
    [B] 生成全系列包含新闻的报告 (Excel + HTML)
    [L] 生成全系列完整版报告 (Excel+HTML)
    [C] 配置持仓信息目录
    [F] 配置持仓信息文件名
    [R] 配置报告输出目录
    [1] 更新基础缓存信息
    [2] 更新持仓相关缓存信息
    [X] 退出
```

| 操作 | 说明 |
|------|------|
| **↑ ↓** | 方向键上下移动选择项 |
| **Enter** | 确认执行当前选中项 |
| **E / N / H / B / L / C / F / R / 1 / 2 / X** | 字母/数字键直达功能 |
| **Ctrl+C** | 退出程序（任意界面） |

---

## 配置说明

配置文件存储在 `data/config/config.json`，默认内容：

```json
{
  "holdings_dir": "data/holdings",
  "holdings_filename": "个人投资持仓信息.xlsx",
  "output_dir": "reports",
  "news_top_count": 100,
  "preferred_provider": {},
  "cache_ttl": {
    "price": 86400,
    "index": 86400,
    "rank": 86400,
    "hold": 604800,
    "news": 86400,
    "benchmark": 2592000
  }
}
```

- **持仓文件目录 (C)** — 设置存放 xlsx 文件的目录路径
- **持仓文件名 (F)** — 设置要读取的文件名；目录下有多个 xlsx 文件时提供列表选择
- **报告输出目录 (R)** — 设置报告文件的输出目录（默认 `reports`），支持相对路径和绝对路径
- **新闻 TOP N (R)** — 配置 `data/config/config.json` 中的 `news_top_count` 字段（默认 100），控制财经新闻关联模块的输出条数
- 配置修改后自动持久化，下次启动自动读取

---

## 缓存文件说明

所有缓存文件存放于 `data/cache/` 目录，JSON 格式，自动管理过期时间。

缓存分为两层：**单条缓存**（`fetcher.py` 日常自动读写）和 **合并缓存**（菜单 [1]/[2] 手动刷新时的全量快照）。价格和基金业绩数据**不**再写入合并文件，直接存于 `price_{code}.json` / `fund_perf_{code}.json`。

### 合并缓存文件（菜单手动生成）

| 文件名 | 用途 | 更新频率 | 来源 |
|---|---|---|---|
| `fund_benchmarks.json` | 业绩比较基准对照表 | 每月 | 自动 + [1] 刷新 |
| `portfolio_latest.json` | 持仓主数据（含最新价/净值） | 持仓更新时 | [2] 更新持仓缓存 |
| `penetration_cache.json` | 穿透 TOP10 计算结果 | 每日 | [2] 更新持仓缓存 |

### 单条缓存文件（引擎自动管理）

| 文件名模式 | 用途 | 有效期 |
|---|---|---|
| `price_{code}.json` | 单只股票/基金的最新价、昨收、净值日期 | 24 小时 |
| `index_{code}.json` | A股/美股市场指数行情 | 24 小时 |
| `fund_perf_{code}.json` | 单只基金的同类排名和区间收益率 | 24 小时 |
| `fund_hold_{code}.json` | 单只基金的前 10 持仓明细 | 7 天 |
| `news_*.json` | 财经新闻数据 | 24 小时 |

> 通过 TUI 菜单 [1] 更新基础缓存、[2] 更新持仓相关缓存可主动刷新合并缓存及对应的单条缓存。菜单 [2] 会先清除所有 `price_{code}.json`，再重新调用 API 获取最新行情，确保单条价格缓存为最新数据。

---

## 输出报告

### Excel 报告（已实现，含 5+1 个页签）

| 页签 | 内容 | 触发方式 |
|------|------|---------|
| 汇总 | 日期、指数、总市值/成本/盈亏/本日盈亏 | E / N |
| 市值核算 | 15 列明细（账户/名称/代码/最新价/净值日期/昨日价/取价方式/溢价率/份额/市值/成本/盈亏/收益率/本日盈亏/取价渠道）| E / N |
| 分类汇总 | 按资产属性 + 投资分类分组统计 | E / N |
| 资产穿透 TOP10 | 合并基金底层持仓，全仓 TOP10 | E / N |
| 基金业绩分析 | 11 列明细（基金/代码/类型/近3月/近6月/近12月/持仓累计盈亏(¥)/持仓收益率/业绩基准/业绩评价/同类排名），类型按穿透规则自动标注 | E / N |
| 财经新闻热点 | 财经新闻与持仓关联分析（关键词匹配） | N 仅限 |

### HTML 报告（迭代 3.2 已完成）

基于 Jinja2 模板引擎将 6 个报告模块完整渲染至单页 HTML：
- 汇总、市值核算、分类汇总、资产穿透 TOP10、基金业绩分析
- **财经新闻热点与持仓关联分析**（关键词匹配、关联度排序）
- 响应式 CSS（移动端/桌面端自适应），正数红色/负数绿色盈亏着色，新闻来源点击跳转
- 页脚标注生成时间与版本号

> 模块 7-8（全球政经、智囊团复盘）为 LLM 增补项目，计划在 Iter 3.3+ 中实现，通过菜单 L 触发（Excel + HTML）

---

## 目录结构

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── main.py            # TUI 入口
│   ├── config.py          # 配置管理
│   ├── models.py          # 数据模型
│   ├── reader.py          # Excel 解析器
│   ├── cache.py           # API 缓存
│   ├── fetcher.py         # 数据获取
│   ├── logger.py          # 日志模块
│   ├── tui.py             # 键盘输入封装
│   ├── test_penetration.py
│   ├── providers/         # API 供应商
│   │   ├── __init__.py
│   │   ├── tencent.py     # 腾讯财经（实时价、指数）
│   │   ├── eastmoney.py   # 东方财富（基金净值）
│   │   ├── tiantian.py    # 天天基金（业绩排名、持仓）
│   │   ├── sina.py        # 新浪财经（美股指数）
│   │   └── sina_news.py   # 新浪财经（新闻获取 + 关联分析）
│   └── report/            # 报告生成
│       ├── __init__.py
│       ├── excel_writer.py
│       ├── styles.py
│       ├── summary.py
│       ├── market_value.py
│       ├── category.py
│       ├── penetration.py
│       └── fund_performance.py
├── data/
│   ├── holdings/          # 持仓 xlsx 文件
│   ├── cache/             # API 缓存 JSON
│   └── config/            # 配置文件
├── reports/               # 生成的报告
├── logs/                  # 程序日志 (app.log)
├── docs-stm/
│   ├── README.md          # <-- 本文件
│   ├── managements/       # 项目管理文档
│   │   ├── plan.md
│   │   ├── requirements.md
│   │   ├── testplan.md
│   │   ├── changelog.md
│   │   └── review-findings.md
│   ├── plan/
│   └── tmp/
├── scripts/
│   ├── launch.ps1         # Windows 启动脚本
│   └── launch.sh          # Linux 启动脚本
├── requirements.txt
└── CLAUDE.md
```

---

## 日志

- 日志文件: `logs/app.log`
- 日志级别: `INFO`（控制台 + 文件）、`DEBUG`（仅文件）
- 日志格式: `2026-06-26 22:37:27,738 [INFO] 正在读取持仓文件: xxx.xlsx`
- 关键信息: 数据读取、API 切换警告、错误追踪

---

## 常见问题

**Q: 启动后菜单显示乱码？**
A: Windows 终端请使用支持 UTF-8 的终端（Windows Terminal 或 VS Code 终端），或运行 `chcp 65001` 切换代码页。

**Q: 提示"文件未找到"？**
A: 菜单选项 C 配置正确的持仓目录，或选项 F 选择正确的文件名。

**Q: 后续如何升级？**
A: 拉取最新代码后，重新运行启动脚本即可自动更新依赖。

---

## 相关文档

- [迭代计划](managements/plan.md)
- [需求文档](managements/requirements.md)
- [测试计划](managements/testplan.md)
- [变更日志](managements/changelog.md)
- [自我审查记录](managements/review-findings.md)
