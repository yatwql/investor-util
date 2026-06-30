# 个人投资分析报告生成小助手

读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.2.44

---

## 功能特性

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 腾讯财经（场内实时价）、东方财富（场外基金净值）等多源备线
- **智能缓存** — API 响应按指定频率缓存，减少网络请求，支持手动刷新和缓存管理
- **Excel 报告** — 11 个功能页签 + LLM API 用量统计：投资分析汇总、市值核算明细表、持仓分类表、资产穿透TOP10、基金业绩分析、财经新闻热点与持仓关联分析、智能预警、全球政经局势（LLM）、智囊团深度复盘（LLM）、持仓体检报告（LLM）、穿透深度分析（LLM）
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、财经新闻热点与持仓关联分析，全部页面顺序展示）
- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 + 华尔街见闻 + akshare（财新网/CCTV）5 源并行获取，去重后与持仓关键词关联
- **行业/概念关键词** — 自动获取东方财富三级行业分类和概念板块，扩展新闻匹配关键词
- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek API，结果按策略缓存（全球政经局势/穿透深度分析 24h / 智囊团深度复盘/持仓体检报告 2h / 财经新闻热点与持仓关联分析 1h），持仓变更时主动失效
- **机构盈利预测** — 调用 akshare 获取全量股票的研报覆盖、预测 EPS、机构评级，穿透 TOP10 与基金业绩页签同步显示
- **分红历史分析** — 个股历年分红自动汇总，计算年均股息率（持仓分类表 + 穿透TOP10 双列展示）
- **行业资金流向** — LLM 全球政经局势注入实时行业资金流向数据（主力净流入/涨跌幅），辅助判断板块轮动
- **智能预警** — 行业资金流向联动预警 + 新闻情绪聚合，基于已有数据自动计算，不依赖 LLM（菜单 B/L 自动附带）
- **基金业绩评价** — 同类排名百分位 + 超额收益修正，自动标注优秀/良好/稳定/偏差
- **TUI 智能摘要** — LLM 分析报告生成后终端直接展示核心观点（全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析），无需打开文件即可快速了解 LLM 输出重点

---

## 快速开始

快速启动指南、持仓文件格式说明、菜单操作说明，请参见：
- [快速开始 & 持仓文件格式 & 菜单操作](docs-stm/manuals/how-to-start.md)

---

## 常规配置指引

`config.json` 完整配置说明（字段说明、数据源开关、首选提供商、自定义基准、缓存 TTL），请参见：
- [常规配置指引](docs-stm/manuals/how-to-config.md)

---

## LLM 配置指引

LLM 密钥配置、参数调优、provider 选择、Extended Thinking、Prompt Caching、token 消耗参考等，请参见：
- [LLM 配置指引](docs-stm/manuals/how-to-config-llm.md)

---

## 中央注册表使用说明

数据模块注册、缓存 TTL 配置、LLM Settings 键名管理、新增模块流程，请参见：
- [中央注册表（registry）使用说明](docs-stm/manuals/how-to-use-registry.md)

---

## 报告文件结构 & 基金业绩评价标准

Excel 报告各页签说明、HTML 报告特性、基金业绩三层评价标准，请参见：
- [报告文件结构 & 基金业绩评价标准](docs-stm/manuals/reports-instruction.md)


---

## 数据源一览 & 目录结构

数据源（行情、新闻、指数、行业分类等）和项目目录结构说明，请参见：
- [数据源一览 & 目录结构](docs-stm/manuals/datasource-and-folders.md)

---

## 常见问题

**Q: 启动后菜单显示乱码？**
A: 请使用支持 UTF-8 的终端（Windows Terminal 或 VS Code 终端），或运行 `chcp 65001` 切换代码页。

**Q: 提示"文件未找到"？**
A: 菜单 `C` 配置正确的持仓目录，或菜单 `F` 选择正确的文件名。

**Q: 如何强制刷新 LLM 内容？**
A: 菜单 `L` 会先检查缓存，缓存过期（默认全球政经局势/穿透深度分析 24h / 智囊团深度复盘/持仓体检报告 2h / 财经新闻热点与持仓关联分析 1h）或持仓/指数数据变更时才重新调用 LLM。如需强制刷新，先执行菜单 `[2]` 更新持仓缓存即可清除关联 LLM 缓存（智囊团深度复盘、全球政经局势、持仓体检报告、穿透深度分析均被清除）。

**Q: 报告数据感觉不完整？**
A: 先试菜单 `[1]` 更新基础缓存，再试 `[2]` 更新持仓缓存，最后重试生成报告。

**Q: 后续如何升级？**
A: 拉取最新代码后，重新运行启动脚本即可自动更新依赖。

**Q: 能否不配置 LLM 使用程序？**
A: 可以。菜单 E / H / B 全部不依赖 LLM，仅菜单 L 需要 LLM 配置。

**Q: 如何开启财经新闻热点与持仓关联分析 LLM 关联分析？**
A: 菜单 `S` 可交互切换各 LLM 模块的启停状态（立即生效），或将 `data/config/llm_settings.json` 中的 `enabled_llm.news_correlation` 设为 `true`。开启后菜单 B / L 生成的报告增加"LLM 关联分析"列，每条新闻获得 LLM 判定的关联度（高/中/低/无关）和原因分析。默认关闭以节省费用。

**Q: 修改配置文件后如何生效？**
A: 菜单 `R` 刷新配置可重新加载 `config.json`、`llm_settings.json` 及 `llm_key.json`，立即生效无需重启程序。

---

## 用户文档

| 文档 | 说明 |
|------|------|
| [快速开始 & 菜单操作](docs-stm/manuals/how-to-start.md) | 启动指南、持仓格式、菜单功能 |
| [配置指引](docs-stm/manuals/how-to-config.md) | config.json 字段说明、数据源、缓存 TTL |
| [LLM 配置指引](docs-stm/manuals/how-to-config-llm.md) | LLM 密钥、参数调优、provider 选择 |
| [中央注册表（registry）使用说明](docs-stm/manuals/how-to-use-registry.md) | 数据模块注册、缓存 TTL、新增模块流程 |
| [报告文件结构 & 基金业绩评价标准](docs-stm/manuals/reports-instruction.md) | Excel/HTML 报告说明、业绩三层评价 |
| [数据源一览 & 目录结构](docs-stm/manuals/datasource-and-folders.md) | 数据源说明、项目目录结构 |

## 管理文档

| 文档 | 说明 |
|------|------|
| [实现计划](docs-stm/managements/plan.md) | 迭代计划 |
| [需求文档](docs-stm/managements/requirements.md) | 完整需求定义 |
| [技术设计](docs-stm/managements/technical.md) | 技术设计 |
| [质量控制与测试标准](docs-stm/managements/testplan.md) | 质量控制与测试标准 |
| [变更日志](docs-stm/managements/changelog.md) | 版本更新记录 |
| [自审记录](docs-stm/managements/review-findings.md) | 自我审查问题记录 |
| [CLAUDE.md](CLAUDE.md) | AI 编程助手指引 |
