# 个人投资分析报告生成小助手

读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.2.86

```bash
.\scripts\launch.ps1   # Windows
./scripts/launch.sh     # Linux
```

---

## 功能特性

### 基础报告与行情

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 腾讯财经（场内实时价）、东方财富（场外基金净值）等多源备线
- **智能缓存** — API 响应按指定频率缓存，减少网络请求，支持手动刷新和缓存管理
- **Excel 报告** — 最多 16 个页签（含条件显示）：投资分析汇总、市值核算明细表、持仓分类表、资产穿透TOP10、基金业绩分析、基金经理变更监控、持仓重合度矩阵、持仓集中度监控、基金风格分析、财经新闻热点与持仓关联分析、智能预警、全球政经局势（LLM）、智囊团深度复盘（LLM）、持仓体检报告（LLM）、穿透深度分析（LLM）、LLM API 用量
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、财经新闻热点与持仓关联分析，全部页面顺序展示）

### 新闻与数据增强

- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 + 华尔街见闻 + akshare（财新网/CCTV）5 源并行获取，去重后与持仓关键词关联
- **行业/概念关键词** — 自动获取东方财富三级行业分类和概念板块，扩展新闻匹配关键词
- **机构盈利预测** — 调用 akshare 获取全量股票的研报覆盖、预测 EPS、机构评级，穿透 TOP10 与基金业绩页签同步显示
- **分红历史分析** — 个股历年分红自动汇总，计算年均股息率（持仓分类表 + 穿透TOP10 双列展示）

### LLM 分析

- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek API，结果按策略缓存（全球政经局势/穿透深度分析/持仓体检报告 24h / 智囊团深度复盘 2h / 财经新闻热点与持仓关联分析 1h），持仓变更时主动失效
- **TUI 智能摘要** — LLM 分析报告生成后终端直接展示核心观点（全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析），无需打开文件即可快速了解 LLM 输出重点

### 资金监控与评级

- **行业资金流向** — LLM 全球政经局势注入实时行业资金流向数据（主力净流入/涨跌幅），辅助判断板块轮动
- **智能预警** — 行业资金流向联动预警 + 新闻情绪聚合，基于已有数据自动计算，不依赖 LLM（菜单 B/L 自动附带）
- **基金业绩评价** — 同类排名百分位 5 级评级 + 类型差异化阈值 + 超额收益修正，自动标注优秀/良好/稳定/偏差/较差

---

## 用户文档&使用指南

| 文档 | 说明 |
|------|------|
| [快速开始 & 菜单操作](docs-stm/manuals/how-to-start.md) | 启动指南、持仓格式、菜单功能 |
| [常见问题解答](docs-stm/manuals/faq.md) | 使用中的高频问题，按类别组织 |
| [常规配置指引](docs-stm/manuals/how-to-config.md) | config.json 字段说明、数据源、缓存 TTL |
| [LLM 配置指引](docs-stm/manuals/how-to-config-llm.md) | llm_key.json 字段说明、llm_settings.json 字段说明、LLM 密钥、参数调优、provider 选择 |
| [报告文件结构 & 基金业绩评价标准](docs-stm/manuals/reports-instruction.md) | Excel/HTML 报告说明、基金业绩评价模型 |
| [数据源一览 & 目录结构](docs-stm/manuals/datasource-and-folders.md) | 数据源说明、项目目录结构 |
| [中央注册表（registry）使用说明](docs-stm/manuals/how-to-use-registry.md) | 数据模块注册、缓存 TTL、新增模块流程 |
| [如何测试我的代码](docs-stm/manuals/how-to-test-my-code.md) | 本地运行测试、测试报告、新增测试指南 |

## 管理文档&设计概要

| 文档 | 说明 |
|------|------|
| [迭代计划](docs-stm/managements/plan.md) | 迭代计划 |
| [需求文档](docs-stm/managements/requirements.md) | 完整需求定义 |
| [技术设计](docs-stm/managements/technical.md) | 技术设计 |
| [质量控制与测试标准](docs-stm/managements/testplan.md) | 质量控制与测试标准 |
| [测试覆盖情况](docs-stm/managements/test-coverage.md) | 测试覆盖情况 |
| [自审记录](docs-stm/managements/review-findings.md) | 自我审查问题记录 |
| [变更日志](docs-stm/managements/changelog.md) | 版本更新记录 |
| [CLAUDE.md](CLAUDE.md) | AI 编程助手指引 |
