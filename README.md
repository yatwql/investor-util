# 个人投资分析报告生成小助手

读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.9.9-dev

## 环境要求

- **Python ≥ 3.11**（3.10 将于 2026‑10 终止支持，不再兼容）
- **操作系统**：Windows 10/11、Linux、macOS

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
- **Excel 报告** — 最多 19 个条件页签，分五组：
  - **基础核算**（6 个）：投资分析汇总、市值核算明细表、持仓分类表、资产穿透TOP10、基金业绩分析、数据源可用性矩阵——每次生成必有
  - **基金深度分析**（5 个）：基金经理变更监控、持仓重合度矩阵、持仓集中度监控、基金风格分析、因子暴露分析——有基金持仓时自动显示
  - **新闻**（1 个）：财经新闻热点与持仓关联分析——启用新闻源时生成
  - **历史走势**（2 个）：组合历史走势、回撤分析——始终可见，数据不可用时占位
  - **LLM 分析**（5 个）：全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析、LLM API 用量——启用 LLM 时生成
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、财经新闻热点与持仓关联分析、6 张 Chart.js 交互图表——悬停/缩放，全部页面顺序展示）

### 新闻与数据增强

- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 + 华尔街见闻 + akshare（财新网/CCTV）5 源并行获取，去重后与持仓关键词关联
- **行业/概念关键词** — 自动获取东方财富三级行业分类和概念板块，扩展新闻匹配关键词
- **机构盈利预测** — 调用 akshare 获取全量股票的研报覆盖、预测 EPS、机构评级，穿透 TOP10 与基金业绩页签同步显示
- **分红历史分析** — 个股历年分红自动汇总，显示年均股息率（持仓分类表）和年均股息金额（穿透TOP10）

### LLM 分析

- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek / Google Gemini API，结果按策略缓存（1h~24h），持仓变更时通过缓存指纹自动失效
- **多 Provider 链式分发** — `llm_providers.json` 支持 priority（顺序递补）/ weighted（加权随机）/ cost_first（低成本优先）/ fallback_only（仅故障降级）四种策略，任一 Provider 失败自动递补
- **Extended Thinking** — 支持 Claude、DeepSeek（Anthropic 兼容端点）和 Gemini 2.5 的扩展思考模式，按模块独立开启
- **每模块独立控制** — 菜单 `S` 交互切换 5 个 LLM 模块的启停，立即生效无需重启
- **LLM 幻觉率评估** — `scripts/llm_hallucination_sampler.py` 对 10 组标准化持仓数据采样，事实校验器自动验证数值/品种/排名正确性

#### LLM 报告实际输出

菜单 L 生成的报告中，以下段落由 LLM 实时生成：

- **全球政经局势** — 注入指数行情 + 行业资金流向（主力净流入/涨跌幅），助你判断短期板块轮动方向
- **智囊团深度复盘** — 三阶段圆桌会议（召集令→辩论→定音锤）；可选辩论模式（菜单 [S] 开启）：正反辩论（pro 绿/con 红/synthesis 金三段式）、条件推理（情景化分析）、集中度问答。末尾自动附上：
  - 📈 **情景分析**：上涨 + 下跌两种情景的具体行动建议（如"若大盘再跌 10%，建议在 XX 位置补仓"），每项标注置信度
  - 🔄 **再平衡信号**：单品种超限告警（如"长江电力 22.5% > 15% 警戒线，建议部分止盈"）+ 大类偏离检测
  - 📊 **竞争语境对比**："组合今日 +2.31% vs 沪深300 +1.05%，跑赢 1.26 个百分点"，附带区间累计对比和夏普/波动率/最大回撤指标
- **持仓体检报告** — 从风险分散度、流动性、收益合理性、成本结构、数据质量五维度量化评分（满分100），附改进建议
- **穿透深度分析** — 行业集中度 + 国别/币种暴露（如"A股 72%/港股 18%/美股 10%"），含外汇风险敞口判断

### 投资分析与风控

- **Beta 置信区间 + 统计检验** — 95% 置信区间、t-统计量、p 值，数据不足时标注"可靠性有限"；置信区间传播（Beta CI→情景回撤 CI、年化波动 CI→夏普 CI）
- **情景分析** — ±1σ/±2σ 共 6 种涨跌情景下组合预期回撤/收益，含市场/行业/汇率三张情景表，LLM 报告中据此给出具体调仓建议
- **口径修正因子** — 综合费率估算/现金剥离/TWR 计算，数据不足时回退纯说明版本，影响报告中累计收益率精度
- **再平衡监控** — 单品种市值超限告警 + 权益/固收大类偏离检测，置信度分级（high/medium/low）。阈值三档预设（保守15%/5%/稳健25%/8%/进取8%/3%）或自定义，`silence_days` 可设静默期避免重复告警
- **流动性风险分析** — 场内品种自动计算"变现天数"（持仓市值 ÷ 日均成交额），场外基金需配置单日赎回上限后显示"需 N 日赎回"
- **竞争语境对比** — 智囊团复盘中自动对比组合 vs 沪深300/中证500/中证全债等多指数的今日涨跌幅、区间累计收益和夏普/波动率/最大回撤，指数池通过 `config.json` 自定义
- **币种敞口分布** — 穿透深度分析中展示 A股/港股/美股 按市值加权占比，非人民币资产>0% 时附加汇率波动风险提示

### 性能追踪与运维

- **自动阶段计时** — 每次报告生成自动记录各阶段耗时（行情获取/数据准备/快照对比/历史走势/HTML 生成/Excel 生成/LLM+新闻），持久化到 `data/state/perf_history.jsonl`
- **数据源健康检查** — 每次报告生成时后台并行执行全量数据源 HTTP 连通性检测，结果存入 `data/state/datasource_health.jsonl` 并实时反映在报告 #18 数据源可用性矩阵章节
- **趋势查看工具** — `scripts/perf_view.py` 读取历史记录，输出版本间耗时对比 Markdown 表格，用于多版本间性能退化检测

### 基金评价

- **基金业绩 5 级评级** — 基于天天基金同类排名百分位，按类型使用差异化阈值（债券型/QDII 更宽松，指数型更严格），再经超额收益评分修正，自动标注优秀/良好/稳定/偏差/较差，带颜色标识
- **基金经理变更监控** — 快照式变更检测，1/3/6 月多窗口对比，变更信息预警着色，支持 ETF 和场外基金
- **持仓重合度矩阵** — Jaccard + Overlap Ratio 双指标，基金两两配对，识别伪分散风险
- **集中度监控+风格漂移** — TOP3/5/10 三级预警 + 市值/PE 加权风格六宫格 + 曼哈顿距离漂移评分
- **因子暴露分析** — 价值/成长/质量 3 因子时间序列 OLS 回归，输出 β 系数、显著性、风格归属占比，含基准对照

### 隐私与安全

- **匿名化 4 模式** — TUI 菜单 `[A]` 切换：off（关闭）/ code_display（代码可见，名称脱敏）/ full_anonymous（完全匿名）/ summary（仅展示汇总数据），持久化到配置
- **隐私提示脚注** — Excel 报告所有页签底部添加匿名化状态说明行，告知数据脱敏级别
- **缓存审查** — `cache.clean_sensitive()` 可清理含敏感持仓名称的缓存条目
- **安全测试覆盖** — 缓存目录穿越、配置注入、LLM 凭据泄露、路径遍历等安全场景测试

---

## 📖 用户指南

建议按以下顺序阅读：

| # | 文档 | 说明 |
|:-:|:-----|:------|
| 1 | [快速开始](docs-stm/manuals/how-to-start.md) | 启动方式、持仓格式、首次使用指引 |
| 2 | [菜单操作手册](docs-stm/manuals/how-to-menu.md) | 各菜单详解、报告内容对照、缓存管理 |
| 3 | [常规配置指引](docs-stm/manuals/how-to-config.md) | config.json 字段说明、数据源、缓存 TTL、章节可见性 |
| 4 | [LLM 配置指引](docs-stm/manuals/how-to-config-llm.md) | 接入 LLM 分析、参数调优、provider 选择、定价 |
| 5 | [报告文件结构](docs-stm/manuals/reports-instruction.md) | Excel/HTML 报告说明、基金业绩评价、投资知识点 |
| 6 | [数据源一览](docs-stm/manuals/datasource.md) | 数据源、缓存前缀、数据质量与常见问题 |
| 7 | [数据源可靠性文档](docs-stm/manuals/datasource-reliability.md) | 运维视角：可靠度评级、降级策略、限流规则、已知问题 |
| 8 | [常见问题解答](docs-stm/manuals/faq.md) | 使用中的高频问题，按类别组织 |
| 9 | [定时任务配置指南](docs-stm/manuals/how-to-schedule.md) | CLI 命令行模式 & Windows/Linux 定时任务设置 |

## 🔧 开发者参考

| 文档 | 说明 |
|:-----|:------|
| [中央注册表（registry）使用说明](docs-stm/manuals/how-to-use-registry.md) | 数据模块注册、缓存 TTL、新增模块（含 LLM）检查清单 |
| [如何测试我的代码](docs-stm/manuals/how-to-test-my-code.md) | 本地运行测试、测试模式、新增测试指南 |
| [辅助脚本参考](docs-stm/manuals/scripts-reference.md) | scripts/ 目录全部工具脚本用法速查 |
| [性能历史趋势查看](scripts/perf_view.py) | 查看每次报告生成的各阶段耗时记录（`python scripts/perf_view.py`） |

## 📋 项目内部文档

以下为项目管理和技术设计文档，供项目维护者和开发者参考，普通用户无需阅读：

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
