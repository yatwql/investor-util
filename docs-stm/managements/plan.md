# 投资复盘助手 — 实现计划
> 文档版本：0.11.1-dev
> **编号源**：`plan-next = 52`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-51，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前在办 **plan-47 / plan-48 / plan-49**（均源自 plan-46 真实持仓复核与降级矩阵的剩余项，非阻塞）；P1 区已完成 plan-42 / plan-43 / plan-44 / plan-45 / plan-46（plan-46 完成态与设计文档索引见归档）；仅保留待办登记区与归档引用；v0.10.x 已完成项（plan-8、plan-17~plan-43）见 `archived_plan.0.10.x.md`，v0.11.x 已完成项（plan-44 / plan-45）见 `archived_plan.0.11.x.md`。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P1 — 当前待办

> 无待办项（plan-42 / plan-43 摘要见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)；plan-44 / plan-45 摘要见 [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md)，plan-45 的设计与实施层文档见 [`archive/v0.11.x/section-consolidation/`](../archive/v0.11.x/section-consolidation/)）。


#### 🔲 `plan-47` 景气度框架诊断：基金持仓 ROE 加权（扩展 ② 维覆盖率）

**动机**：② ROE 低位弹性当前只覆盖 **A 股个股**（用户组合实测 21.91% 权重：长江电力/工行/建行/广发多因子），基金/ETF/QDII/债基无个股 ROE → 其余权重标「需核实」不计分。

**方案**：对基金持仓按其**重仓股 ROE 加权**（需先具备**全量穿透**能力：现穿透层仅保留 top10 底层，需扩展为按基金聚合全量持仓或新增独立取数路径），再对底层股票批量取基本面（`providers/akshare_financial` 支持一条调用多股）。

**约束与红线**：① 新契约字段须进数据契约台账 + 附录 H + 双端一致性测试；② 属**推演**而非方法原话（框架原意是选股层面的 ROE 弹性）→ 渲染文案必须标「按框架推演」；③ 不得因该扩展影响既有章节输出（开关关闭时零变化）。

**预估成本**：中高（穿透层扩展 + 新契约 + 报告耗时 +几秒）；**价值**中（②覆盖 21.9% → 60~80%）。

#### 🟡 `plan-51` 同花顺官方金融数据接入（四域：财务指标 / 基金持仓 / 行情·日历·公司行动 / 情绪面）

**动机**：现有链路多处依赖非官方爬虫源（穿透基金持仓走天天基金 HTML、财务指标走 akshare），长期有降级与漂移风险；行情缺第三条正交链路；市场情绪（涨跌停/连板/龙虎榜）完全空白。同花顺官方 API（<https://fuyao.aicubes.cn>）为官方源、不限累计调用次数、字段级契约明确。

**覆盖边界（官方声明，不可误用）**：不含分钟 K/tick、**海外行情**、**宏观数据**、**新闻公告原文与研报** → **不能**替代 DataSinking 财报全文（区块② 缺口仍由 plan-50 承接）。

**阶段与进度**：

| 阶段 | 内容 | 状态 |
|---|---|---|
| 阶段 1 | provider 层：`providers/hithink.py`（凭据声明 / qps 限速器 / 信封与错误码 / 触发限流不重试 / 16 个域接口 / `to_thscode` 映射）+ 55 例单测 | ✅ **已实现并实测通过**：key 已配置，11 端点真实连通 10 通（指数成分股接口 429，阶段 4 复核）；默认 qps 按实测由 3 降为 2。实测字段结构见设计文档 §4.1 |
| 阶段 2 | 财务指标域第三链路：`HithinkIndicatorAdapter` → `FinancialIndicatorFields`（五类 `ability` 与首批 `index_id` 已实测取到，全量清单需落表；**顺带以官方 `pe_ttm`/`pb_mrq` 修正项目自算 PE 口径**——实测长江电力 47.19 vs 官方 19.17） | ⬜ 待办 |
| 阶段 3 | 基金披露持仓：穿透链路改两源链（hithink 官方披露持仓 ⇄ 天天基金），缓存归 `fund_hold_` + `hold_schema` 语义版本闸门；交叉校验后评估 `plan-47` 全量穿透 | ⬜ 待办 |
| 阶段 4 | 行情第三链路（腾讯→新浪→同花顺）+ 历史日 K 前/后复权 + `fetch_trading_days` 校准 `core/trading_calendar.py` + 复权因子事件流 | ⬜ 待办 |
| 阶段 5 | 情绪面新能力：新数据域 `market_sentiment`（涨跌停池/连板天梯/龙虎榜）+ 报告章节（开关默认关）+ 可选注入 LLM 信号预消化 | ⬜ 待办 |

**前置条件已完成**：API key 已写入 `data/config/data_key.json` 的 `hithink` 节（文件由 `.gitignore` 忽略，不入库）。

**约束与红线**：① provider 只取原始响应，字段归一交 `source_adapter`、缓存/熔断/降级交 `fetch_with_fallback`（不新造取数路径）；② 新数据域须登记 `DOMAIN_RECORDS` + 附录 H + 双端一致性测试；③ 新章节挂 Feature Flag 且默认关（关闭时输出逐字节一致）；④ 凭据值永不落日志/报告/缓存。

**预估成本**：阶段 2 低、阶段 3 中、阶段 4 中、阶段 5 中高；**价值**：高（把三条爬虫主源换成/补上官方源，并新增情绪面能力）。

#### 🔲 `plan-50` 财报取数第二数据源（巨潮 cninfo 备用链路）

**动机**：区块② 财报摘要目前**单一依赖 DataSinking**，报告完整性受该源「收录 + 章节解析」质量决定——实测工商银行 `601398` 的 2026 半年报**未被收录**，2025 年报/季报的 `/sections` 残缺（年报只解析出「附件/标题」两节）且裸章节名直取 404；本次已加「全文兜底 + 关键词定位」救回 2025 年报「董事会报告」段，但**源侧根本没有的报告**（如工行 2026 半年报）仍取不到，季报也只能补财务数据段（季报本身不写经营讨论）。

**方案**：接巨潮资讯网（cninfo）公告库作为 `financial_report` 域的**第二 provider**——走既有 Provider Chain 槽位（`fetcher/source_adapter.adapter_chain_slots(DOMAIN_FINANCIAL_REPORT)`），主源无该标的/无可用章节时自动接管：按 stock_code 取公告列表 → 定位年报/半年报 → 解析公告正文（PDF/HTML）→ 归一为同一记录契约（`doc_type`/`report_period`/`title`/`announcement_time`/`content`/`source`/`adjunct_url`/`section_source`）。

**约束与红线**：① **不新造取数路径**，必须落在既有域适配器两槽上（主/备），缓存键与降级由 `fetch_with_fallback` 统一处理；② 限速与失败处理走 provider 层护栏（参照 `providers/datasink` 的 RateLimiter/配额模式），不得绕过；③ 记录契约字段不变（新 provider 只填同一字段，展示层零改动）；④ **主源可用时输出必须逐字不变**（备源只在主源失败时生效）。

**预估成本**：中高（PDF/公告正文解析 + 限速与缓存复用 + 两 provider 契约一致性测试）；**价值**：高（消除「单一数据源解析质量决定报告完整性」的结构性依赖）。

#### 🔲 `plan-48` 景气度框架诊断：场外流动性补齐（④ 维）

**动机**：④ 流动性当前只有场内 4 只可算（`check_liquidity` 近 20 日成交额），场外 4 只因未配 `redemption_limits` 标「场外基金」、6 只成交额缺失按「流动充足」假设降级。

**方案**：① 在 `config.json` 的 `redemption_limits` 提供用户可填的单日赎回上限（文档已述，属配置项）；② 或对场外品种给出**类型分级默认档**（货基/短债 T+0~T+1、纯债 T+2、QDII T+3~T+7），使该维在场外为主时有区分度。

**约束**：类型分级须走 `core/code_utils`（类型判定中心化），且默认档位须在证据中标注为「类型默认档（非实测）」。

#### 🔲 `plan-49` 景气度框架诊断：转正评估（默认开启）

**前置条件（全部满足才转正）**：
1. 降级矩阵全绿（2026-09-16 已达成：6 场景无崩溃、块始终渲染、降级语义正确）；
2. 真实使用样本 ≥2 周，覆盖跨月快照（换手代理）、一次调仓、一次数据降级；
3. 用户确认「评分口径认可」（① 关键词表与 ⑤ 集中度目标 `concentration_target_pct` 是否按自身风格校准）；
4. 四个 `--ci` + `--mode verify,regression` + ruff + 版本一致性全绿。

**转正动作**：`features.py` 声明从 `GROUP_EXPERIMENTAL` 改 `GROUP_STANDARD` 且 `default=True`（`affects_report` 照实 `True`）；同步 `requirements.md`/`how-to-config.md`（分组计数）、`test_features.py` 转正用例、changelog；**不改评分口径**。

**当前结论**：**暂不转正**（保持实验组默认关；用户 `features.json` 已手工开启，功能可用）。

### P4 — 实验功能

> 无待办项（plan-30 ~ plan-41 全部完成，完成项摘要见归档）。

## 归档

- [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md) — v0.11.x 已完成项（plan-44 / plan-45 / plan-46，含 plan-45 与 plan-46 设计文档索引）
- [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md) — v0.10.x 已完成项
- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
