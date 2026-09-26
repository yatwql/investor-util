# 实现计划归档 — v0.11.x

> 归档时间：2026-09-15（v0.11.0 发布当日并入，plan-44）；2026-09-16 增补（plan-45、plan-46）；2026-09-18 增补（plan-52、plan-53、plan-54，v0.11.1 发布当日并入）；2026-09-23 增补（plan-47、plan-48）；2026-09-24 增补（plan-50，v0.11.3 发布当日并入）；2026-09-24 增补（plan-50，v0.11.2-dev 迭代内完成）
> 原始文件：`docs-stm/managements/plan.md（当前迭代部分）`
> 涵盖版本：v0.11.0（2026-09-15）/ v0.11.1（2026-09-18：plan-52 矩阵命中源列 / plan-53 去重校准体系修整 / plan-54 48 小时技术债整改）/ v0.11.2（2026-09-24：plan-47 基金重仓 ROE 加权 / plan-48 场外流动性类型默认档）/ v0.11.3（2026-09-24：plan-50 巨潮 cninfo 财报备源）
> 归档内容：本迭代已实现的计划项完成态记录（plan-44 报告增强子模块并入功能开关注册表；plan-45 报告章节整合；plan-46 景气度框架诊断；plan-51 同花顺官方金融数据接入五阶段；plan-47 景气度框架②维基金 ROE 加权 / plan-48 ④维场外流动性类型默认档 / plan-50 财报域巨潮备源）；
> plan-42 / plan-43 摘要见 `../v0.10.x/archived_plan.0.10.x.md`
> 设计文档索引：plan-45 的设计层与实施层文档归档于 `section-consolidation/`；plan-46 的设计文档归档于 `prosperity-framework/`；plan-51 的设计文档归档于 `hithink-data-source/`（均见文末）

---
### P1 — 已完成（plan-44 完成态，2026-09-15 归档）

#### ✅ `plan-44` 报告增强子模块并入功能开关注册表（面板统一，不做兼容）— 已完成（2026-09-15）

**动机**：`P` 面板（`report_submodules`，存 `config.json`）与 `S` 面板（`features.json` 注册表，20 项）是两套并列机制，两处都用裸数字编号 → 用户跨面板记编号（本次已因手册编号漂移误开错项）。统一为单一事实来源与单一面板。

**已核实现状（开工依据）**：
- 注册表：`config/features.py` — `FeatureSwitchDef(label, desc, group, default, affects_report)`、`GROUP_EXPERIMENTAL`/`GROUP_STANDARD`、`GROUP_LABELS`、`GROUP_ORDER=(EXPERIMENTAL, STANDARD)`、`switches_in_group()`/`is_feature_enabled()`/`set_feature_enabled()`/`save_feature_overrides()`；注册表 docstring 显式写着「各报告章节与增强子模块 → config.json 的 enable_* 键」，需同步改写。
- 默认值：`_config_defaults.py::_DEFAULT_CONFIG["report_submodules"]`（8 项：data_quality=True、market_temperature=True，其余 6 项 False）+ 配置模板 `_get_default_config_template()`。
- 访问器：`_core.py` 8 个 `is_enable_*`（各自硬编码缺键回落，须与默认值一致）。
- TUI：`handlers_config.py` — `S` 面板 `_cmd_config_llm_modules` **硬编码两组** `(GROUP_EXPERIMENTAL, GROUP_STANDARD)`；`P` 面板 `_cmd_config_report_boards` 第 6 项进子面板 `_cmd_config_report_submodules`（8 项，`REPORT_SUBMODULE_ITEMS` 模块级常量，写路径 `set_config("report_submodules", ...)`）。
- Web：`web/config_edit.py` — surface `features`（两组派生）与 `submodules`（现取 config.json 值）+ `_EDITABLE` 8 条 `report_submodules.*` → `writer: "submodule"`；前端 `static/web/main.js` 已有 `renderBoolGroup('submodules', '报告增强子模块', …, {prefix: 'report_submodules.'})`（**块已存在，可直接复用**）。

**不做兼容（用户决定）**：不读旧 `config.json` 的 `report_submodules` 段、不写迁移层；重新生成 config.json（删除该段）。

**改动清单（按批次，每批独立可验证）**：
1. **批次① 注册表与真源**：`features.py` 新增 `GROUP_REPORT`（标签「报告章节与增强」）+ `GROUP_ORDER` 追加 + 8 条 `FeatureSwitchDef`（default 同现状、`affects_report=True`）；`_core.py` 8 个访问器改为 `is_feature_enabled(<key>)`（保留 `config` 形参但不再读它）；`_config_defaults.py` 删除 `report_submodules` 段与模板行；重生成 `data/config/config.json`。
2. **批次② TUI**：`S` 面板加入 `GROUP_REPORT` 块（并考虑 P 子面板保留为薄壳或删除、`P` 顶层面板第 6 项文案调整）；`P` 子面板写路径改 `set_feature_enabled` + `save_feature_overrides`。
3. **批次③ Web/CLI**：`config_edit.py` 的 `submodules` 负载改为注册表派生、8 条 `_EDITABLE` 改走 feature writer（键名可保留 `report_submodules.*` 以减少前端改动）、前端补 `labels: surface.features.labels`；CLI `--feature` 自动放行 8 个新名（验证）。
4. **批次④ 文档与守卫**：`how-to-config`（两张开关表合并、删除全部「菜单 P → …」引用）、`requirements` 配置表、`technical`（注册表约束适用范围与语义表）、`reports-instruction`/README/`folders`/`testplan`/`changelog`；测试同步（`test_config`/`test_handlers_config`/`test_config_edit`/`test_features`/`test_check_semantic_index` 等 11 处）+ 新增「注册表 8 项默认值与访问器一致」「面板清单覆盖全部开关」「features.json 覆写生效、config.json 段不再被读」三条守卫。

**验收标准**：`report_submodules` 在代码与文档中**零残留**（`grep -r report_submodules src/ docs-stm/` 仅剩历史 changelog/归档）；`S` 面板与 Web 面板各出现「报告章节与增强」一块共 8 项、可开关且落 `features.json`；8 个开关行为与现状逐项等价；四个 `--ci` + `--mode verify` + ruff 全绿。

实施记录：见 `changelog.md`「报告增强子模块并入功能开关注册表（plan-44 完成，不做兼容）」条（本条目即设计记录；不再另建设计文档）。


---
### P1 — 已完成（plan-45 完成态，2026-09-16 归档）

#### ✅ `plan-45` 报告章节整合（注册表条目 21 → 17，重生成配置模板）— 已完成（2026-09-16）

**动机**：注册表条目已有 21 个，其中若干同族/体量很薄/本是另一条目的子视图（市值核算明细与持仓分类同源；持仓关系矩阵与持仓集中度同属「持仓结构」；财报摘要是持仓基本面的叙事层；基金经理变更是基金业绩的子视图）。

**决定（用户）**：不做配置兼容，**重生成 `config.json` 与配置模板**；设计与实施逐条对照 `technical.md` §8 架构约束。

**方案（统一新语义命名：旧键/旧页签名/旧写入器/旧 partial 全部删除，不留 alias）**：
1. 新条目 `holdings_detail`「持仓明细与分类」（= 市值核算明细 + 持仓分类；两区块，均 `always`）
2. 新条目 `position_structure`「持仓结构与集中度」（= 持仓关系矩阵 + 持仓集中度；同 `type=fund_deep_analysis`；可见性取 OR）
3. 新条目 `fundamental_snapshot`「持仓基本面」（= 财务指标 + 财报摘要；两区块；两个功能开关各控一块）
4. `fund_performance`「基金业绩分析」吸收基金经理变更为章末尾区块（键与显示名语义未变；块门禁 `enable_fund_deep_analysis`；先例 `candidate_compare`）

**架构要点**：不新增 pipeline_data 键（pipeline_data 契约台账不动）；可见性模型最小扩展——注册表可选字段 `data_flag_any`（多契约 OR，未声明时行为不变）；序号/显示名/页签名一律经注册表（注册表驱动）。

**已实施（四批，每批一次提交、每批门禁）**：
- 批次① 可见性模型扩展 + 守卫（`data_flag_any` 注册表字段 + Excel/HTML 两侧 OR 判定 + 12 例守卫，零行为变化）— `bce98ee2`
- 批次② M1 `holdings_detail`：注册表 21 → 20 条；市值明细与分类汇总合为同页签两区块（`holdings_detail_sheet.py`），领域层（`market_value.py` / `category.py` 分类函数）不改名不删除；新增合并页签测试与「章节 type ↔ board_flags ↔ 装配键」一致性守卫 — `a11db932`
- 批次③ M2 `position_structure`：注册表 20 → 19 条；重合度 + 相关性 + 集中度三区块合一同页签（`position_structure_sheet.py`），可见性 `data_flag_any` OR（Excel 侧同步登记两契约 flag，修正悲观判定吞页签缺陷 rf-367）— `b8c0d862`
- 批次④ M3 `fundamental_snapshot` + M4：注册表 19 → 17 条；财务指标与财报摘要合为同页签两区块（`fundamental_snapshot_sheet.py` + `partials/fundamental_snapshot_section.html`，两功能开关各控一块）；`fund_manager` 章节并入「基金业绩分析」章末尾区块（`fund_performance._write_manager_block`）；board 参数合并为 `enable_fundamental_snapshot` — `f2c1a23a`
- 收尾：统计快照刷新（`567c2273`）+ 管理/用户文档一致性与顺序整改（`317b4e48`，自查 rf-369）

**十轮复盘**：实施前对两份设计文档做十轮复盘（命名链/架构约束/测试面/配置面 → 接缝完整性/守卫与可验证性 → 批次依赖与计数硬伤 → 跨文档同步与自洽终检），逐轮整改并提交（`2453690c` / `a95312a7` / `da3e2e77` / `7db80963`）；复盘记录见设计文档索引项的实施层文档 §6.6。

**验收标准（达成）**：注册表条目 **17**、序号连续 1~17；被并章节的页签/章节各减 3；契约键（`position_relationship_data` / `concentration_data` / `manager_data` / `financial_indicator_data` / `financial_report_digest_data`）全部保留；`--mode verify,regression` 4939 passed / 0 failed；`dev-verify` 2748 passed；四个 `--ci` + ruff + 版本一致性全绿。

**实施记录**：见 `../../managements/changelog.md`「plan-45 章节整合·批次②/③/④ 实施」「plan-45 设计文档十轮复盘（第 1~4 / 5~6 / 7~8 / 9~10 轮）」「plan-45 四批后管理/用户文档一致性与顺序整改」条；设计文档索引见下。

**设计文档索引**（归档于 `section-consolidation/`）：
- `section-consolidation-design.md` — 报告章节整合设计（设计层：四项合并方案 / 可见性模型扩展 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）
- `section-consolidation-iteration.md` — 报告章节整合实施层（迭代施工单：命名统一总表 / 接缝地图 / 逐批施工步骤与量化验收 / 十轮复盘记录 / 守卫清单与基线方法 / 领域层与章节层边界 / 文档同步清单）


---
### P1 — 已完成（plan-46 完成态，2026-09-16 归档）

#### ✅ `plan-46` 景气度框架诊断（借鉴 zhengxi-views 的投资分析方法，实验性功能）— 已实施（2026-09-16）

**动机**：上游 `zhengxi-views`（郑希观点库，MIT）把一位主动权益基金经理公开表述的方法蒸馏为「可操作流程 + 六维评分卡」。本项目只借鉴其**可计算骨架与评分口径**，转成对本仓持仓组合的诊断（不引入其语料/快照/检索）。

**方案（已落地）**：
1. 实验性功能开关 `prosperity_framework`（实验组、默认关、`affects_report=True`）
2. 纯计算模块 `report/analysis/prosperity_framework.py`：六维评分卡 = 景气方向/通胀属性 25 + ROE 低位弹性 20 + 全球视野/中国比较优势 15 + 流动性 10 + 集中度与周期拼接 15 + 业绩与回撤印证 15
3. 数据契约 `prosperity_framework_data`（数据契约台账 + 附录 H + 双端一致性）
4. 渲染：行动建议章内嵌块（HTML ⑥ 块 / Excel `_write_prosperity_block`），不新增章节
5. 配置：顶层键 `prosperity_framework`（景气/全球优势/防御关键词 + 集中度目标），配置层单一事实来源
6. 组装辅助 `_report_aux_metrics.compute_prosperity_framework_data`（开关关闭返回 None；穿透/流动性/快照取数失败一概降级为「未验证」）

**不做**：不引入上游语料与基金快照、不做全市场基金检索/对比、不新增 LLM 调用、不新增外部数据源、不改变既有章节输出。

**口径要点（经两轮真实持仓修订）**：① 两视角叠加（穿透底层 + 持仓自身板块/类型兜底标签）后归一，基金类型兜底只进防御侧或中性；② 缺数据维度一律 `unverified` 不计分（不臆造）；③ 防御优先的互斥归类；④ 总分只按已计分维度折算并显示未验证清单；⑤ 渲染固定带免责句（契合度而非优劣判断，非投资建议）。

**实施期缺陷修复（5 处，均由真实数据/路径暴露）**：
- `rf-373` 快照形态假设错误（`SnapshotData` 非 dict）→ 曾导致**整份报告生成失败**；同时修出既有缺陷「行情全零时合并单元格崩溃」
- `rf-374` full 路径（菜单 L）HTML 未转发契约（同一契约多条调用链只补一条）
- `rf-375` 维度⑥ 基准结构假设错误（`benchmarks` 为 `list[dict]`）→ 误报缺失
- `rf-376` 口径只覆盖 34.6% 市值 + 词表两份 + 重复计数
- `rf-377` 基金类持仓整只被跳过（51.28% 权重无信息）+ 货币基金判定优先级陷阱

**降级矩阵（2026-09-16 复核）**：6 场景（交易日基线 / 非交易日行情全零 / `history` 关闭 / 基本面契约缺失 / 关基金深度分析 / 快照 <2 期）**报告均生成成功、块始终渲染、降级语义正确**。

**后续项（另行登记于 `plan.md`）**：`plan-47` 基金持仓 ROE 加权、`plan-48` 场外流动性补齐、`plan-49` 转正评估（当前结论：暂不转正）。

**设计文档索引**（归档于 `prosperity-framework/`）：
- `prosperity-framework-design.md` — 景气度框架诊断设计（上游归属与许可 / 数据可得性映射 / 六维口径（含两轮修订记录）/ 契约结构 / 架构约束对照 / 测试与文档同步清单 / 验收标准）

#### ✅ `plan-51` 同花顺官方金融数据接入（四域：财务指标 / 基金持仓 / 行情·日历·公司行动 / 情绪面）——**已完成（2026-09-17）**

**动机**：现有链路多处依赖非官方爬虫源（穿透基金持仓走天天基金 HTML、财务指标走 akshare），长期有降级与漂移风险；行情缺第三条正交链路；市场情绪（涨跌停/连板/龙虎榜）完全空白。同花顺官方 API（<https://fuyao.aicubes.cn>）为官方源、不限累计调用次数、字段级契约明确。

**覆盖边界（官方声明，不可误用）**：不含分钟 K/tick、**海外行情**、**宏观数据**、**新闻公告原文与研报** → **不能**替代 DataSinking 财报全文（区块② 缺口仍由 plan-50 承接）。

**阶段与进度**：

| 阶段 | 内容 | 状态 |
|---|---|---|
| 阶段 1 | provider 层：`providers/hithink.py`（凭据声明 / qps 限速器 / 信封与错误码 / 触发限流不重试 / 16 个域接口 / `to_thscode` 映射）+ 55 例单测 | ✅ **已实现并实测通过**：key 已配置，11 端点真实连通 10 通（指数成分股接口 429，阶段 4 复核）；默认 qps 按实测由 3 降为 2。实测字段结构见设计文档 §4.1 |
| 阶段 2 | 财务指标域第三链路 | ✅ **已实现**：`analysis/financial_statement_derive.py`（三张合并报表纯派生为标准字段）+ `HithinkIndicatorAdapter`（链路第三槽）+ `fetch_hithink_indicator_series`（主源不可用时的**多期**回退，优于单期兜底）。**实测与主源完全对齐**：报告期（2026-06-30/03-31/2025-12-31/09-30）与营收/归母净利/毛利率/负债率/现金流/EPS 全一致，同比 0.033562 相同；差异仅 ROE（期末口径 6.47% vs 加权 6.55%）与 `bvps`（官方不给总股本 → 恒缺失）。PE/PB 口径修正（rf-386）待契约字段落地，见该项 |
| 阶段 3 | 基金披露持仓两源链 | ✅ **已实现**：`_FUND_HOLD_PROVIDERS` = 天天基金（主，三跳阶梯）→ 同花顺官方披露持仓（备，需 key）；两侧形态经 `_normalize_hold_payload` 归一（同花顺只取 `asset_type=stock`、报告期取披露结束日、联接基金由 `fund` 型资产直返目标 ETF）；**不递增 `hold_schema`**（归一后形态不变、旧条目不被误读）；顺序可用 `preferred_provider.fund_hold` 调换。实测 `016055.OF`→`513390.SH`、`012325.OF` 全债券被过滤 |
| 阶段 4 | 行情/日历/复权 | ✅ **已实现**：① 行情第三槽（`price_stock` = 腾讯 → 新浪 → 同花顺，新增 `HithinkQuoteAdapter`；实测 600900 价 28.44/昨收 28.46，**官方 `pe_ttm` 一并带入**）；② 历史日 K 第三槽（`history_stock` 同序 + `_HISTORY_PROVIDER_MAP` 注册，`fetch_kline` 前复权、支持 `start_from` 增量；**实测踩坑：上游历史 K 线日期字段是 `date_ms` 而非快照的 `timestamp`**）；③ 交易日历官方兜底（akshare 失败 → `calendar/trading-days`，实测 243 个交易日）。**收尾项**：复权因子事件流（`adjustment_factors`）尚无消费者——计划用于「分红流水漏记校验」（与成本流水的分红累计交叉核对），待阶段收尾接入，暂记 rf-389 |
| 阶段 5 | 情绪面能力 | ✅ **已实现（形态收敛）**：龙虎榜 + 连板梯队 → 只保留**命中持仓/穿透标的代码**的事件行，渲染为**行动建议章内嵌块**（与景气度框架同一模式，开关 `market_sentiment` 默认关），未新开独立章——理由：一个表不值得新增章节+页签，且与既有「报告增强子模组内嵌章内区块」模式一致。零命中时仍给市场概览（避免价值型组合恒空、分不清「空」与「坏」）。**未做**：注入 LLM 信号预消化（可选增强，随信号预消化机制后续评估） |

**交付摘要**：五阶段全部落地——provider 层（凭据/qps 限速/信封错误码/16 端点）+ 财务指标第三链路（三张合并报表派生，与主源口径一致）+ 基金披露持仓两源链（备源，联接基金直返目标 ETF）+ 行情与历史日 K 第三槽与交易日历官方兜底 + 市场情绪章内区块（开关默认关）。**设计文档**：`../archive/v0.11.x/hithink-data-source/hithink-financial-data-design.md`（已归档）。**收尾项**（不影响已交付能力，见 `review-findings.md`）：复权因子事件流的消费方「分红流水漏记校验」、情绪事件注入 LLM 信号预消化、实验挂载点约定与现状的一致性收敛。

**前置条件**：API key 已写入 `data/config/data_key.json` 的 `hithink` 节（文件由 `.gitignore` 忽略，不入库）。

**约束与红线**：① provider 只取原始响应，字段归一交 `source_adapter`、缓存/熔断/降级交 `fetch_with_fallback`（不新造取数路径）；② 新数据域须登记 `DOMAIN_RECORDS` + 附录 H + 双端一致性测试；③ 新章节挂 Feature Flag 且默认关（关闭时输出逐字节一致）；④ 凭据值永不落日志/报告/缓存。

**预估成本**：阶段 2 低、阶段 3 中、阶段 4 中、阶段 5 中高；**价值**：高（把三条爬虫主源换成/补上官方源，并新增情绪面能力）。

### P1 — 已完成（plan-52 / plan-53 / plan-54 完成态，2026-09-18 归档）

#### ✅ `plan-52` 数据源可用性矩阵：provider 级「命中源」列（已完成 2026-09-18）

> 用户反馈触发：「已提供同花顺 key，但报告的数据源可用性矩阵没提到用了这个数据源」。排查确认**属于报告口径缺失，而非 key 未生效**——同一次运行的 `data/cache/sentiment_*` 由同花顺接口刷新（`logs/app.log` 有 `正在获取市场情绪…` → `[market_sentiment] 命中 0 条`），证明 key 在用。

**根因三条**：① 矩阵只按**数据类别**聚合，其 tracker 事件键（`price_price_stock_600900`）只含代码不含 provider → 从未、也无法点名某个源；② 说明表「实际数据源（链路）」是硬编码文案，未随同花顺接入同步（`datasource.md` 已登记、`data_source_matrix.py` 未更新）；③ 市场情绪（同花顺**唯一源**）的取用标记键 `sentiment` 不匹配任何类别前缀 → 落入「其他数据源」桶，连类别名都不显示。

**交付**：`report/data_status.py` 新增 provider 级归属登记（`mark_provider_used` / `get_provider_usage` / `reset_provider_usage`；模块级登记表，不参与降级计数、不在 `.degradation_state.json` 堆积 provider 键）；`fetcher/chain.py` 两处成功分支 + `report/market_sentiment.py` + `fetcher/financial_indicator.py` 多期序列支路登记归属；矩阵新增「命中源（本次取数）」列（HTML + Excel 两处渲染）与 `history`（历史走势）/ `sentiment`（市场情绪）两个类别及 `data_types` 映射（链路 data_type 全覆盖由不变式用例强制，`UNMAPPED_CHAIN_DATA_TYPES` 登记有意缺席者）；说明表补齐同花顺兜底槽位与市场情绪行（含 key 就绪态与所需开关），计费解析泛化为「行内显式 → provider 动态套餐 → 免费」。详细变更见 `changelog.md`。

#### ✅ `plan-53` 新闻去重锚点校准体系修整（已完成 2026-09-18）

> 用户贴回 `scripts/calibrate-dedup-threshold.py` 输出触发复核。结论：原「校准建议」不可照做——两条已实现/已过时，且报告数字混了规则时代。复核证据、修正后分布与逐条结论见 [`../plan/dedup-anchor-calibration.md`](../plan/dedup-anchor-calibration.md)。

**根因**：① 锚点文件 append-only 且**无规则版本字段**，收紧前的旧样本与新样本混在一起（实测 `cross_skip` 中 46% 的 ratio 低于当前候选区入口、`cross_safe` 中 508 条 `merged` 但 `bg=0`），使「需审查 N 条」类结论失真；② 工具**自写一份硬编码阈值**（正文 0.30 vs 代码 0.35）且建议文本引用了早已实现的年份剥离，输出误导性动作；③ `_TOKEN_LIKE` 把纯数字当专名证据（24 对共享数字的无关标题被 bg=2 梯度误合并）；④ 锚点文件 152 MB / 456,546 行中仅 51,718 个唯一对（重复行 89%），而 flush 与加载都是全文成本。

**交付**：新校准工具（阈值与相似度口径均取自 `news_dedup`：`_pair_similarity` / `_CROSS_*` 常量；用当前代码重算并按当前阈值重判分支；历史时代单列；`--compact` 压缩 152 MB → 17 MB）；锚点新增 `anchor_rules_version`（`_rules_fingerprint()` 自动派生）+ 超 32 MB 加载告警；`_TOKEN_LIKE` 收紧 + 5 组价格方向对；回归用例 24 例（含 scripts 工具新测试文件）。

#### ✅ `plan-54` 过去 48 小时实现的技术债整改（已完成 2026-09-18）

> 触发：用户提出「过去 48 小时的实现有没有技术债，有就修」。扫描范围：`git log --since=50h`（22 commit）+ 未提交工作区；判据含体积硬上限/静默吞异常/债务标记/无引用定义/重复实现/文档与代码同步。

**发现的四类债务与处置**（逐条见 `review-findings.md` rf-393 / rf-399~rf-401）：

| 类别 | 实况 | 处置 |
|:--|:--|:--|
| 文件超 800 行硬上限 | `providers/news_dedup.py` 改动后 931 行（规则数据 + 主流程混居） | 拆为 `news_dedup_rules.py`（650 行，规则原语）+ `news_dedup.py`（327 行，锚点与主循环，原面 re-export）；拆分后同批样标题 ratio/overlap/掩码/指纹**逐值一致** |
| 实验挂载点约束不一致 | 景气度框架诊断两条生成路径内联 try/except（full 路径双重守护），未过实验挂载点 | 新增 `_experimental_seams.record_prosperity_diagnosis`，两路径改调挂载点并删内联守护；该约束的适用面与工序顺序同步；新增 4 例挂载点用例（rf-393 收敛） |
| 文档与代码脱钩 | 功能开关计数 4 份文档停在 29/8/4（实为 30/9/5）且报告组漏列市场情绪；`technical.md` 目录 2.7 锚点失效；新增文档相对链接少一层 | 4 份文档计数按注册表更正 + 补列表项；锚点补连字符；相对链接改 `../plan/…`（rf-400） |
| 判据重复 | `analysis/financial_indicator._num` 与 `core.num_utils.safe_num` 各自实现「解析 + 有限性校验」 | `_num` 改为 `safe_num(value, default=None)` 的 float 投影，删除已无用的 `import math`（rf-401） |

**未列入本次整改（已登记、非阻塞）**：rf-395 的遗留面——其余 `data/state/*` 写入方（perf/health/silence）同样面临「后台线程越过用例级补丁」，当前无实测泄露，彻底治本需把状态目录改为可注入的单一来源。

### P1 — 已完成（plan-47 完成态，2026-09-23 归档）

#### ✅ `plan-47` 景气度框架诊断：基金持仓 ROE 加权（② 维基金层扩展，阶段一）— 已完成（2026-09-23）

**范围决策（2026-09-23 用户确认）**：两阶段方案——阶段一按基金**前十大重仓股** ROE 加权（本项），阶段二（全量持仓口径）待 plan-51 阶段 3（同花顺历史持仓接口）收尾后升级；估算记录契约以 `basis` 字段区分口径（`top10_holdings`），阶段二落地时替换取数来源、契约不变。

**实施摘要**：新增 `report/fund_roe_estimate.py::estimate_fund_roe_batch`（复用 `fetch_fund_holdings_batch` 基金持仓链路 + `fetch_latest_indicator` 个股财务指标链路，不新增 HTTP 通道；报告期陈旧闸门与穿透层同口径；`known_roe` 命中免取数）；`analysis/prosperity_scoring._score_roe` 新增可选入参 `fund_roe_estimates`——无直接 ROE 的权益类基金（QDII/ETF/联接/主动权益，类型判定走 `classify_penetration`）以推演值计分，证据/持仓视角/契约 notes 三处均标「按框架推演」（红线②）；直接 ROE 优先、推演值不覆盖；开关关闭时零变化（红线③）。新语义名 `estimate_fund_roe_batch` / `fund_roe_estimates` 已入语义命名表，契约口径已入附录 H。

**实施记录**：见 `../../managements/changelog.md`「plan-47 基金重仓股 ROE 加权（② 维基金层扩展，阶段一）」条。

#### ✅ `plan-48` 景气度框架诊断：场外流动性补齐（④ 维，类型默认档）— 已完成（2026-09-23）

**方案选择（2026-09-23）**：采用 plan 内的方案②（类型分级默认档），配置项 `redemption_limits`（方案①）优先；类型判定按约束走 `core/code_utils`（C1 类型判定中心化）。

**实施摘要**：`core/code_utils.otc_redemption_days_default` 四档——货币/短债 T+1、纯债 T+2、其他场外基金（主动权益/混合/指数/联接）T+3、QDII T+7（保守上沿），无法识别返回 None；`analysis/liquidity.check_liquidity` 场外未配置赎回上限时落默认档并输出 `estimate_basis="type_default"` + 「约 T+N 日赎回（类型默认档，非实测）」标签；`_score_liquidity` 计分池扩为「场内 + 场外配置口径 + 场外默认档（非实测）」，默认档参与时 `status=partial` 且证据明标非实测（满足约束「默认档须标注非实测」）。

**实施记录**：见 `../../managements/changelog.md`「plan-48 景气度框架④维场外流动性补齐（类型默认档）」条。

### P1 — 已完成（plan-57 LLM 端点级节流与并发治理，2026-09-25）

**触发**：用户计划将订阅制编码端点（Kimi Code）接入程序，要求「从整体架构出发、考虑架构约束、不留技术债务」，并质疑「非该端点时并发约束能否放开」。

**背景（实测）**：每次报告生成 8~9 次 LLM 调用、41k~56k token，集中在 2~8 分钟内以 3 路并发发出——对「要求交互式使用」的订阅制端点属高风险形态。全局键 `llm_max_concurrency` 无法表达「同一程序、不同端点不同策略」。

**实施**：
- 新增 `llm/pacing.py`：`PacingPolicy` / `parse_policy` / `register_policies` / `PacingGate`——把节流与并发**声明化到 provider 条目**（`llm_providers.json` 的 `pacing` 段：`min_interval` / `jitter` / `max_concurrency`），缺省即无约束（零开销直通，行为与未引入时逐字节一致）
- 配置层接入：`_parse_providers_list` 透传 `pacing`；`_inject_provider_chain_data` 装载策略（配置为唯一事实来源）；模板补注释
- 调用链接线：`endpoint_key` 由 provider 条目名逐层透传（`api.py` → `call_single_provider` → 三协议 `call_claude/openai/gemini` → `call_llm_with_retry`），在**唯一调用缝**施加 `PacingGate`（先取并发许可再等间隔，使间隔真正约束请求发出时刻）
- 复用既有原语：`fetcher/batch.py::RateLimiter` 新增 `acquire_interval(key, interval)`（逐次显式间隔），不重复实现限速器
- **403 配额/风控不重试**：新增 `FAIL_REASON_QUOTA_EXCEEDED`，`_attempt_api_call` 将 403 归为 `("quota", 403)`，重试骨架直接降级到下一 provider（窗口按时间滚动，重试无益且加剧风控画像）；429/503 仍按 `max_retries` 重试。报告侧差异化文案同步（`llm_content` / `llm_module_info`）
- 文档：手册新增「端点级节流（`pacing`）」章节（与全局并发的关系、403 语义）；技术设计新增 §4.2.1（含调用链图与性质表）

**测试**：+19 例（`test_llm_pacing.py` 16：解析/容错/注册/零开销/间隔/抖动/并发上限/异常释放/失败原因；`test_config_llm_multi.py` +3：pacing 透传/缺省不注入/非对象忽略）。真实调用路径实测：无约束端点 3 次调用 0.002s；`min_interval=0.2` 端点间隔稳定 0.200s；403 在 `max_retries=2` 下仅 1 次请求且失败原因 `quota_exceeded`

---

### P1 — 已完成（plan-56 数据源健壮性加固，2026-09-24）

**触发**：用户报「`price_price_fund_otc` 与 `report_datasink` 高频连接失败」，建议增加备用通道 / 优化重试 / 延长刷新窗口。

**诊断**（实测）：高发「失败」主要是**健康探针误报**（见 `archived_review-findings` 的 rf-428）；另有结构性单源风险与第三方配额压力。

**实施**：
- **场外净值跨厂商备源**：`providers/sina.py::fetch_fund_nav`（`hq.sinajs.cn/list=f_{code}` 解析 名称/单位净值/累计净值/前一日净值/净值日期）+ `quote_adapters.SinaFundQuoteAdapter` + 手写转换 `_price_transform_sina_fund`；链路 `price_fund_otc` 由**单源 `["eastmoney"]` → `["eastmoney", "sina_fund"]`**（故障域独立，非东财系）；适配器开关两条路径同时接线，回归锁定「主源可用时备源零调用」
- **传输级同源重试**：`fetcher/chain.fetch_with_fallback` 落槽前对传输级失败（超时/断连/远端断开）同源退避重试一次（0.6s 指数退避 + 抖动），**不重试代码级空结果**（防白耗 DataSinking 日配额 8191 篇）
- **财报正文备源**：`fetcher/financial_report.py` 抽出 `_attempt_candidates`（章节阶 → 全文阶）并把**正文级**巨潮接管接入（`_backup_candidates`）——此前备源只在「索引为空」时触发；主源可用时备源仍零调用
- **延长刷新窗口**：财报索引/章节清单 TTL 两周 → **30 天**（与正文同档），降低第三方配额与限速压力（R-FRD-07 语义同步）

**测试**：+26 例（探针 9 / 新浪 provider 4 / 适配器等价 2 / 链路重试 3 / 场外备源端到端 5 / 正文备源接管 3）

**验证**：健康检查实测 10/10 可用；场外净值主源故障时由新浪交付（数值与东财一致）；行业分类主源不可达时由行情页备源交付

---

### P1 — 已完成（plan-50 完成态，2026-09-24 归档）

#### ✅ `plan-50` 财报取数第二数据源（巨潮 cninfo 备用链路）— 已完成（2026-09-24）

**背景**：区块② 财报摘要此前单一依赖 DataSinking，报告完整性受该源「收录 + 章节解析」质量决定——实测工商银行 `601398` 的 2026 半年报未被收录（源侧根本没有的报告无法用季报替代经营讨论内容）。

**实施摘要**：
- 新增 `providers/cninfo.py`：公开免费无需凭据；三段取数（`topSearch` 解析 orgId → `hisAnnouncement` 公告列表 → `static` 站 PDF 下载 + pdfplumber 解析），公告元数据**归一为与主源索引同一形状**（`id/doc_type/report_period/title/announcement_time/adjunct_url/source`），文种归类含「半年度先于年度」的判定顺序与摘要/英文版剔除；护栏为固定 1 秒/请求礼貌限速 + 429 退避重试一次，全部失败路径返回空（不抛异常）
- `fetcher/report_adapters.py`：新增 `CninfoReportAdapter` 作财报域**第二槽**（备源）；主源适配器与备源适配器以 `source_hint` 做**命名空间隔离**（异源 doc_id 互不服务、备源进独立缓存键段），缓存/熔断/降级全部复用既有 `fetch_with_fallback`
- `fetcher/financial_report.py`：主源索引为空/失败时切备源重建索引（候选回溯逻辑零改动复用）；源与元数据随查询透传
- `fetcher/report_locate.py`（新增）：目录行判定与关键词定位收敛为单一实现，**全文兜底与备源章节切片共用**（消除重复）
- `core/registry.py`：登记备源缓存前缀（索引/正文/orgId）
- 依赖：`pdfplumber`（主依赖；实测镜像最新为 0.11.10，故取 `>=0.11,<1.0` 而非计划书中的 `>=1.0`——该版本号尚不存在）；**惰性导入**，缺失时解析环节降级为空文本（仅该源失效）

**红线达成**：① 未新造取数路径（备源走既有域适配器两槽 + 既有缓存/熔断）；② 限速与失败处理在 provider 层护栏；③ 记录契约字段不变（适配器归一为标准字段）；④ **主源可用时备源零调用**（有专项用例锁定），主源候选的缓存键与输出逐字不变。

**实施记录**：见 `../../managements/changelog.md`「plan-50 财报取数第二数据源（巨潮 cninfo 备用链路）」条。
