# 个人投资分析报告生成小助手

读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.6.7

## 启动方式

### TUI 交互模式（菜单操作）

```bash
.\scripts\launch.ps1   # Windows
./scripts/launch.sh     # Linux
```

### CLI 命令行模式（定时任务驱动）

```bash
# 生成基础 Excel 报告
python -m src.python.cli report --type basic

# 生成全量报告（含 LLM）
python -m src.python.cli report --type full --history auto

# 更新缓存
python -m src.python.cli cache --update all

# 查看缓存状态
python -m src.python.cli cache --stats
```

详见[定时任务配置指南](docs-stm/manuals/how-to-schedule.md)。

---

## 功能特性

### 基础报告与行情

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **CLI 命令行模式** — argparse 参数驱动，支持定时任务自动生成报告（Windows 任务计划程序 / Linux cron）
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 腾讯财经（场内实时价）、东方财富（场外基金净值），多数据源自动 fallback
- **智能缓存** — API 响应按指定频率缓存，减少网络请求，支持手动刷新和缓存管理
- **Excel 报告** — 最多 17 个条件页签，分五组：
  - **基础核算**（5 个）：投资分析汇总、市值核算明细表、持仓分类表、资产穿透TOP10、基金业绩分析——每次生成必有
  - **基金深度分析**（4 个）：基金经理变更监控、持仓重合度矩阵、持仓集中度监控、基金风格分析——有基金持仓时自动显示
  - **新闻**（1 个）：财经新闻热点与持仓关联分析——启用新闻源时生成
  - **历史走势**（2 个）：组合历史走势、回撤分析——始终可见，数据不可用时占位
  - **LLM 分析**（5 个）：全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析、LLM API 用量——启用 LLM 时生成
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、财经新闻热点与持仓关联分析，全部页面顺序展示）

### 新闻与数据增强

- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 + 华尔街见闻 + akshare（财新网/CCTV）5 源并行获取，去重后与持仓关键词关联
- **行业/概念关键词** — 自动获取东方财富三级行业分类和概念板块，扩展新闻匹配关键词
- **机构盈利预测** — 调用 akshare 获取全量股票的研报覆盖、预测 EPS、机构评级，穿透 TOP10 与基金业绩页签同步显示
- **分红历史分析** — 个股历年分红自动汇总，显示年均股息率（持仓分类表）和年均股息金额（穿透TOP10）

### LLM 分析

- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek API，结果按策略缓存（2h~24h），持仓变更时主动失效

### 资金监控与评级

- **行业资金流向** — LLM 全球政经局势注入实时行业资金流向数据（主力净流入/涨跌幅），辅助判断板块轮动
- **基金业绩评价** — 同类排名百分位 5 级评级 + 类型差异化阈值 + 超额收益修正，自动标注优秀/良好/稳定/偏差/较差

---

## 📖 用户指南

建议按以下顺序阅读：

| # | 文档 | 说明 |
|:-:|:-----|:------|
| 1 | [快速开始](docs-stm/manuals/how-to-start.md) | 启动方式、持仓格式、首次使用指引 |
| 2 | [菜单操作手册](docs-stm/manuals/how-to-menu.md) | 各菜单详解、报告内容对照、缓存管理 |
| 3 | [常规配置指引](docs-stm/manuals/how-to-config.md) | config.json 字段说明、数据源、缓存 TTL、板块可见性 |
| 4 | [LLM 配置指引](docs-stm/manuals/how-to-config-llm.md) | 接入 LLM 分析、参数调优、provider 选择、定价 |
| 5 | [报告文件结构](docs-stm/manuals/reports-instruction.md) | Excel/HTML 报告说明、基金业绩评价、投资知识点 |
| 6 | [数据源一览](docs-stm/manuals/datasource.md) | 数据源说明 |
| 7 | [常见问题解答](docs-stm/manuals/faq.md) | 使用中的高频问题，按类别组织 |
| 8 | [定时任务配置指南](docs-stm/manuals/how-to-schedule.md) | CLI 命令行模式 & Windows/Linux 定时任务设置 |

## 🔧 开发者参考

| 文档 | 说明 |
|:-----|:------|
| [中央注册表（registry）使用说明](docs-stm/manuals/how-to-use-registry.md) | 数据模块注册、缓存 TTL、新增模块（含 LLM）检查清单 |
| [如何测试我的代码](docs-stm/manuals/how-to-test-my-code.md) | 本地运行测试、测试模式、新增测试指南 |

## 管理文档&设计概要

| 文档 | 说明 |
|------|------|
| [迭代计划](docs-stm/managements/plan.md) | 迭代计划 |
| [需求文档](docs-stm/managements/requirements.md) | 完整需求定义 |
| [技术设计](docs-stm/managements/technical.md) | 技术设计 |
| [LLM 技术要点](docs-stm/managements/llm-technical.md) | LLM 客户端架构与技术细节 |
| [质量控制与测试标准](docs-stm/managements/testplan.md) | 质量控制与测试标准 |
| [测试覆盖情况](docs-stm/managements/test-coverage.md) | 测试覆盖情况 |
| [自审记录](docs-stm/managements/review-findings.md) | 自我审查问题记录 |
| [变更日志](docs-stm/managements/changelog.md) | 版本更新记录 |
| [目录结构及文件概览](docs-stm/managements/folders.md) | 目录结构及文件概览 |
| [CLAUDE.md](CLAUDE.md) | AI 编程助手指引 |
