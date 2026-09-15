# 持仓个股基本面数据源主备与财务指标提取 — 设计文档

> 文档类型：中间设计文件（实现落地后随迭代归档）
> 关联：DataSinking 财报接入（`docs-stm/plan/datasink-financial-report-digest-design.md`）
> 状态：设计完成，待实施

---

## 1. 背景与动机

DataSinking 接入后，本项目首次获得**上市公司财报全文**，产出「持仓个股财报摘要」章节。但当前只用了其中一小部分价值，且分析层仍有明确缺口：

| 现状 | 缺口 |
|---|---|
| 财报全文只取「管理层讨论与分析」单章节、只到摘要 | 多文种（季报）与多章节未用 |
| 估值分位以**价格分位代理**近似历史估值 | 无真实历史 PE/PB（缺 EPS/每股净资产序列） |
| 风格与因子分析只有价量因子 | 无**质量因子**（盈利质量/杠杆/现金流） |
| LLM 复盘上下文以新闻为主 | 缺**权威经营叙事与风险因素** |
| 上市公司财报全文为**单源** | 无主备，单点故障即整章缺失 |

本设计把 DataSinking 从「全文摘要」扩展为「基本面数据源」，并为其配置**结构化指标互补源**，形成可降级的主备结构。

---

## 2. 已核实的数据源事实

### 2.1 DataSinking（全文本财报）

| 项 | 值 |
|---|---|
| 覆盖 | 中国（SSE/SZSE/BSE）· 日本（TSE）· 韩国（KOSPI/KOSDAQ/KONEX）· 台湾（TWSE/TPEx） |
| 文种 | `annual` / `semiannual` / `q1` / `q3` / `amendment` |
| 格式 | 章节化全文本 Markdown，正文以 YAML frontmatter 开头，数字处标注单位（如 `> 单位：元`） |
| 端点 | `/exchanges` · `/stocks` · `/documents` · `/documents/{id}` · `/documents/{id}/sections` · `/documents/batch` |
| 段落取用 | `/documents/{id}?section=<章节标题>`（模糊标题匹配） |
| 元数据字段 | `id` `symbol` `exchange` `stock_code` `stock_name` `report_period` `doc_type` `title` `word_count` `announcement_time` `source` `adjunct_url` `parser_version` |
| 额度 | 免费 3 req/s、8,191 篇/日；付费 31 req/s、131,071 篇/日；两档均受 **31 天滚动 524,287 篇**上限（免费档共享池） |
| 批量 | 免费档**不可用** → 逐篇请求 |

### 2.2 结构化财务指标源（拟接入）

akshare 提供结构化财务指标（无需凭据），可作本设计的指标主源：

- `stock_financial_abstract` — 关键指标摘要（营收/净利/ROE/每股指标等）
- `stock_financial_analysis_indicator` — 财务分析指标（成长/盈利/偿债/营运）
- `stock_financial_report_sina` — 三表（资产负债/利润/现金流）

同为字段化数字，适合直接落标准字段契约，无需 Markdown 解析。

---

## 3. 数据域与主备结构

新增一个数据域，与既有 `financial_report`（全文/叙事）并列：

| 数据域 | 内容 | 主源 | 备用源 | 说明 |
|---|---|---|---|---|
| `financial_report` | 财报全文 Markdown（叙事） | `datasink` | 预留（官方公告平台原始页） | 已实现，仅补主备位 |
| `financial_indicator` | 结构化财务指标（数字） | `akshare_financial` | `datasink_indicator` | 本设计新增 |

**主备是双向互补而非简单替代**：

- akshare 指标取不到（接口变更/该股无数据）→ 从已缓存的 DataSinking 全文**解析**指标兜底；
- DataSinking 全文取不到（配额耗尽/无 key）→ akshare 指标仍可支撑估值与质量因子；
- 两者都不可得 → 指标列落占位，不阻断报告。

链路定义沿用既有 Provider Chain 机制：

```
financial_indicator: ["akshare_financial", "datasink_indicator"]
```

- 链路顺序、缓存键、熔断、降级复用 `fetcher/chain.fetch_with_fallback`，不新造获取路径；
- `datasink_indicator` 是一层**解析适配器**：经既有财报链取回指标章节正文（复用其缓存/限速/配额/熔断，**不另建 HTTP 通道**），输出为标准指标字段；缓存命中时零新增请求，仅主源失败时才补取 1 次章节。

---

## 4. 标准字段契约（`financial_indicator` 域）

新增记录类 `FinancialIndicatorFields`，登记 `schemas/datasource_fields.py` 的域注册表，由适配器反射驱动（不存在第二份手抄清单）：

| 标准字段 | 类型 | 含义 |
|---|---|---|
| `code` | `str` | 6 位证券代码 |
| `symbol` | `str` | FMP 风格符号 |
| `report_period` | `str` | 报告期（YYYY-MM-DD） |
| `doc_type` | `str` | 文种 |
| `revenue` | `float \| None` | 营业收入（元） |
| `net_profit` | `float \| None` | 归母净利润（元） |
| `revenue_yoy` | `float \| None` | 营收同比（小数） |
| `net_profit_yoy` | `float \| None` | 净利同比（小数） |
| `gross_margin` | `float \| None` | 毛利率（小数） |
| `roe` | `float \| None` | 净资产收益率（小数） |
| `debt_ratio` | `float \| None` | 资产负债率（小数） |
| `operating_cash_flow` | `float \| None` | 经营活动现金流净额（元） |
| `eps` | `float \| None` | 每股收益（元） |
| `bvps` | `float \| None` | 每股净资产（元） |
| `source_api` | `str` | 数据源标识 |
| `source` | `str` | 源展示名 |

可选数值字段统一用 `float | None`：缺失取 `None`（「该源不提供」），合法的 `0.0` 不被覆盖。数值一律经 `core/num_utils.safe_num` 归一。

---

## 5. 全文解析设计（`datasink_indicator` 适配器）

### 5.0 前提修订（对真实年报实测后）

原设计假定「DataSinking 输出 Markdown 表格，可读表头 + 数据行」，实测**不成立**：

- **无表格**：PDF→Markdown 转换把报表压平为「标签紧连数字」的整段正文，例如
  `...营业收入86,241,940,222.2084,491,870,566.522.0778,143,535,736.10利润总额41,739...`；
- **无「主要会计数据与财务指标」章节名**：`?section=主要会计数据与财务指标` 返回 404；
  指标实际在**第二节「公司简介和主要财务指标」**（别名 `主要财务指标` 命中共章），
  季报为「主要财务数据」；
- 该章节含标准披露表：营业收入 / 归母净利润 / 扣非净利润 / 经营活动现金流量净额 /
  归母净资产 / 总资产 / 基本每股收益 / 稀释每股收益 / 加权平均净资产收益率（含同比列）。

因此解析策略由「读表格」改为「**锚点 + 前若干数值**」，并**收窄到这一章节**：
不解析报表正文——正文存在附注编号（如 `七、61`）与金额粘连的误读风险，
而该章节能覆盖的指标已足够支撑指标列，收益低于风险。

### 5.1 取用章节

按优先级**逐个试取、命中即止**（避免同一章节被多个别名重复取回、白耗配额）：

1. `公司简介和主要财务指标`（年报/半年报标准章节）
2. `主要财务数据`（季报）

### 5.2 解析护栏

| 护栏 | 做法 |
|---|---|
| 锚点 | 只用标准披露行文（如「归属于上市公司股东的净利润」）；对「扣除非经常性损益后的…」加否定环视，避免误取扣非口径 |
| 窗口 | 数值只在锚点后**有限字符窗口**内取，超窗判为跨行、弃用 |
| 精度 | 金额两位小数、每股收益四位小数、比率两位小数——避免「1.41011.3281」无分隔连写被误切 |
| 单位 | 取锚点前**最近一处**「单位：X」声明换算到元；**无声明即不产金额**（宁缺勿错） |
| 校验 | 逐字段幅度/区间校验（金额 < 1e15、比率 ∈ [-100,100]、每股 < 1e4），不通过即 `None` |
| 同比 | 由本期/上年**同口径**两值算术派生（只做算术，不做口径推断）；无上年或上年为 0 → `None` |
| 报告期 | 一律**由元数据给出**，不从正文猜 |

### 5.3 覆盖面（诚实边界）

解析支路可提供：营业收入、归母净利润、营收同比、净利同比、经营活动现金流净额、
基本每股收益、净资产收益率。**毛利率 / 资产负债率 / 每股净资产不在该章节**，
解析支路恒取 `None`，由主源 akshare 提供（字段契约允许缺失，上层按缺失占位）。

### 5.4 实测复核

长江电力（600900.SS）2025 年报夹具 `src/test/data/fixtures/datasink_indicator_section_600900.md`
逐字段复现披露值：营收 86,241,940,222.20 元；归母净利 34,502,809,176.39 元；
经营活动现金流净额 60,562,925,570.41 元；基本每股收益 1.4101 元/股；
加权平均净资产收益率 15.90%；同比 2.07% / 6.17%。

---

## 6. 派生分析（指标 → 报告价值）

| 派生 | 输入 | 用途 | 对应章节 |
|---|---|---|---|
| 真实历史 PE/PB 分位 | `eps`/`bvps` 多期 + 历史收盘价 | 替代或补充现有**价格分位代理**，给出真实估值分位 | 资产穿透 TOP10 | ✅ 已实现（阶段③b，**TTM 口径**：年报直取 / 季报累计差分；生效日取法定披露截止日以避免前视偏差；PE 优先 PB 兜底；无基本面覆盖回落价格代理并标注口径） |
| 质量因子 | `roe`/`gross_margin`/`debt_ratio`/`operating_cash_flow` | 盈利质量与财务健康度 | 风格与因子分析·持仓体检 |
| 基本面趋势 | 多期 `revenue`/`net_profit` 序列 | 增长趋势与拐点 | 持仓个股财报摘要 |
| 财报风险信号 | `amendment` 文种、审计意见章节、披露延迟（`announcement_time` − `report_period`） | 治理风险预警 | 持仓体检·数据质量仪表盘 |

约定：所有派生值必须随附 `report_period` 与来源；口径为「报告期快照」而非「当季实时」，展示层复用既有持仓时效口径标注。

---

## 7. LLM 侧注入（阶段三）

在指标之外，把**叙事章节**注入 LLM 上下文：

- `管理层讨论与分析` — 经营变化、指引
- `风险因素` / `重要事项` — 风险与诉讼担保
- `审计报告` — 审计意见类型与事务所变更

注入方式复用既有提示词管线（不新增调用次数）：摘要以「信号 + 依据」行进入体检与智囊团提示词，并要求模型做**数字与叙事背离检测**（叙事乐观而指标走弱时显式提示）。

---

## 8. 配置与开关

| 配置 | 默认 | 说明 |
|---|---|---|
| `report_submodules.financial_indicator` | 关 | 新增基本面章节/列的总开关（数据驱动型：无数据即隐藏） |
| `datasink.sections` | 现有值 | 扩展为多章节列表；指标提取使用其中与财务指标相关的章节 |
| `datasink.plan` / `requests_per_second` / `daily_quota` | 免费档 | 复用既有计划感知限速与日配额护栏 |
| 指标源优先级 | akshare 优先 | 经链路定义表达；用户可用 `preferred_provider.financial_indicator` 覆盖 |

akshare 指标源无需凭据；DataSinking 解析支路不新增请求，仅消费已缓存全文。

---

## 9. 配额与降级

### 9.1 请求量估算

- 全文主路：每标的每章节 1 次（现有）。
- 指标主路：akshare 一次调用可取多股（全量拉取后按代码过滤），请求量近似 **O(1)**，与持仓数无关。
- 解析支路：**0~1 次章节请求** —— 经既有财报链取数，缓存命中即 0；仅当主源失败时才补取 1 次指标章节（复用财报链的限速/配额/熔断，不另建 HTTP 通道）。

因此指标能力对 DataSinking 免费档配额的增量近似为零；主要成本是 akshare 的调用与解析计算。

### 9.2 降级矩阵

| 场景 | 处置 |
|---|---|
| akshare 指标不可用 | 链路落 `datasink_indicator`，从缓存全文解析 |
| DataSinking 无 key / 配额耗尽 | 指标仍由 akshare 提供；全文摘要章节写占位 |
| 某股在其源无覆盖 | 该股指标列 `None`，标注「无覆盖」，不消失 |
| 解析失败 | 指标列 `None`，记录失败原因，不猜测数值 |
| 两者均不可用 | 指标列整体占位，不阻断报告主链路 |

---

## 10. 语义命名表（新增标识符）

| 语义 slug | 中文名 | 说明 |
|:--|:--|:--|
| `financial_indicator` | 财务指标 | 新数据域标识；同名 `report_submodules` 键 |
| `FinancialIndicatorFields` | 财务指标标准字段记录 | 数据域标准字段契约 |
| `akshare_financial` | akshare 财务指标 | 结构化指标主源（provider 名） |
| `datasink_indicator` | DataSinking 指标解析 | 从财报章节解析指标的备用支路（provider / 适配器名） |
| `financial_indicator_extract` | 财务指标提取 | 压平正文 → 标准指标的纯解析模块（锚点 + 取值窗口 + 精度模式） |
| `financial_indicator_sheet` | 财务指标呈现 | 指标列/基本面章节的报告层装配 |
| `report_datasink_indicator_` | 财报指标缓存前缀 | 指标记录缓存（一月） |

> 命名纪律：上述标识符即代码名；任务编号不进入实现层。

---

## 11. 文件级落点（预估）

| 文件 | 改动 |
|:--|:--|
| `src/python/fetcher/financial_indicator.py` | **不需要**：取数编排已由「适配器 + 链路」承担，不再另建模块（避免第二份获取路径） |
| `src/python/providers/akshare_financial.py` | 新增。akshare 财务指标封装（超时保护、字段命名） |
| `src/python/analysis/financial_indicator_extract.py` | 新增。压平正文 → 标准指标的纯解析层（锚点 + 取值窗口 + 精度模式 + 校验） |
| `src/test/data/fixtures/` | 新增。上游真实正文夹具（DataSinking 指标章节），供解析层回归 |
| `src/python/fetcher/financial_indicator_adapters.py` | 新增。两个适配器（akshare / 解析）三段式实现 |
| `src/python/schemas/datasource_fields.py` | 新增 `DOMAIN_FINANCIAL_INDICATOR` + `FinancialIndicatorFields` |
| `src/python/fetcher/chain.py` | 新增链 `financial_indicator` |
| `src/python/core/registry.py` | 缓存前缀 + 报告章节/页签（若为独立章节） |
| `src/python/report/financial_indicator_sheet.py` | 新增。指标呈现（Excel + HTML） |
| `src/python/report/valuation_percentile.py` | 消费真实 PE/PB 序列（替代价格分位代理分支） |
| `src/python/analysis/style_factor_regression.py` | 接入质量因子 |
| `src/python/config/_config_defaults.py` | `report_submodules.financial_indicator` 默认关 |
| 文档 | `datasource.md` / `datasource-reliability.md` / `technical.md` / `requirements.md` / `testplan.md` / `folders.md` / `changelog.md` |

---

## 12. 测试计划（要点）

| 层 | 用例 |
|:--|:--|
| 解析层 | 真实年报夹具逐字段复现；合成样本覆盖行文变体、单位换算（元/万元/亿元）、精度切分（每股四位小数连写）、易混行（扣非）排除、字段缺失取 `None`；边缘场景（取值窗口边界、异常幅度、越界比率、零基数同比、截断正文）单独成 `*_edge.py` |
| 适配器 | 三段式契约自检、alias/defaults 指向真实字段、输出恰为标准字段集、解析适配器逐章节试取与源身份注入 |
| 链路 | 链路顺序（主源 → 解析支路）、akshare 失败落解析支路且源身份为 `datasink_indicator`、两者皆失败返回空、凭据/接口异常不计熔断 |
| 派生 | 真实 PE/PB 与代理分位的一致性边界、质量因子缺失容错 |
| 章节 | 开关关闭零影响、无数据隐藏、部分覆盖失败清单不消失 |
| 隔离 | akshare 全量接口 mock（禁真实网络）、缓存与状态文件重定向到临时目录 |

---

## 13. 实施顺序

1. **结构化指标主路**：`akshare_financial` 适配器 + `financial_indicator` 链 + 标准字段 + 缓存注册 + 测试（快、无解析风险）。
2. **全文解析支路**：`financial_indicator_extract` + `datasink_indicator` 适配器 + 备用降级 + 测试（成本最高，单独一轮）。
3. **报告消费**：真实 PE/PB 估值分位 + 质量因子 + 指标呈现章节/列 + 开关。
4. **LLM 注入**：叙事章节摘要进提示词 + 数字与叙事背离检测。
5. **文档与门禁**：手册/技术/需求/测试计划/目录树/变更记录；跑 P0/P1 门禁。

---

## 14. 非目标

- 不接入日/韩/台市场（本期仍仅 A 股）。
- 不做财报全文结构化入库（指标按需提取，全文仅缓存与截断展示）。
- 不做审计报告全文语义分析（仅取审计意见类型与换所信号）。
- 不引入付费 DataSinking 套餐作为前提（免费档足以支撑指标场景；批量端点仅在付费档可用，非必需）。

---

## 15. 风险

| 风险 | 缓解 |
|:--|:--|
| akshare 财务接口签名/格式变动 | 作为主源但可降级到全文解析；cassette 录制回归 |
| 上游无表格（压平正文）致数字误读 | 解析收窄到「公司简介和主要财务指标」章节；锚点 + 有限取值窗口 + 精度模式 + 逐字段合理性校验，不通过取 `None`；真实年报夹具回归锁定 |
| 历史 PE/PB 与价格分位代理口径切换引起读者混淆 | 展示层显式标注「真实估值分位」与样本区间；保留代理作为兜底 |
| 披露延迟（QDII 更晚） | 复用持仓时效口径标注报告期与已过季度数 |
| 免费档 31 天滚动上限 | 指标主路 O(1) 请求、解析支路零新增请求，增量可忽略 |
