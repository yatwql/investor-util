# 变更日志归档 — v0.11.x

> 归档时间：2026-09-15（v0.11.0 发布当日并入）；2026-09-18 增补（v0.11.1 发布当日并入）；2026-09-24 增补（v0.11.2、v0.11.3 发布当日并入）
> 原始文件：`docs-stm/managements/changelog.md`
> 涵盖版本：v0.11.0（2026-09-15）/ v0.11.1（2026-09-18）/ v0.11.2（2026-09-24）/ v0.11.3（2026-09-24）
> 归档内容：v0.11.x 已发布版本变更记录（含 v0.11.3：需求 ID 追溯链全量打通（276 条/34 域映射表 + 门禁脚本）、手册 thinking 章节补 Kimi 与矩阵守卫、测试全量审计、归档索引与分区纪律断言；含 v0.11.2：Kimi 主节点接入与 Extended Thinking、穿透占比与 Endpoint 主备两处缺陷修复、景气度框架②④维扩展、巨潮财报备源、两轮技术债与文档审计；含 v0.11.1：同花顺 key 在报告中的可见性、新闻去重校准体系修整、48 小时技术债整改；开发版本记录仍保留在原文件 changelog.md 的 [0.11.2-dev] 段）

---
## [0.11.1] - 2026-09-18

### 过去 48 小时实现的技术债整改（2026-09-18，plan-54 / rf-393、rf-399~rf-401）

**触发**：用户要求排查并修复近 48 小时实现中的技术债。扫描面：`git log --since=50h`（22 个 commit）与未提交工作区；判据：体积硬上限、静默吞异常、债务标记、无引用定义、重复实现、文档与代码同步、约束合规。

**四类债务已整改**：
- **文件超 800 行硬上限**：`providers/news_dedup.py` 931 行（阈值/模板词表/归一化/实体提取/指纹 + 锚点采集与主循环）→ 拆为 `news_dedup_rules.py`（650 行：规则数据与纯原语）+ `news_dedup.py`（327 行：锚点与比较循环，原面 re-export 全部规则名）；拆分后同批样标题的 ratio/overlap/掩码/指纹与拆分前**逐值一致**（rf-399）
- **实验挂载点约束不一致（rf-393 结项）**：景气度框架诊断（实验组开关）在两条 HTML 生成路径内联 try/except（full 路径还是双重守护）→ 新增挂载点 `_experimental_seams.record_prosperity_diagnosis`（开关判定 + 契约注入，重依赖按需导入），两路径改调挂载点、删除内联守护；该约束的适用范围与工序顺序同步；新增 4 例挂载点用例。市场情绪为报告组开关（非实验组），不属该约束范围
- **文档与代码脱钩（rf-400）**：`market_sentiment` 接入后计数未同步——`how-to-config.md`/`technical.md`/`requirements.md`/`README.md` 四份仍写 29 项（实 30）、报告章节与增强 8 项（实 9，漏列市场情绪）、实验组 4 项（实 5）；另修正 `technical.md` 目录 2.7 锚点（标题含空格 + 反引号时 GitHub 锚点会插入 `-`）与 `changelog.md` 新增文档的相对链接层级
- **判据重复（rf-401）**：`analysis/financial_indicator._num` 与 `core.num_utils.safe_num` 各自实现「解析 + 有限性校验」→ `_num` 改为 `safe_num(value, default=None)` 的 float 投影，删除已无用的 `import math`

**未整改（已登记、非阻塞）**：rf-395 遗留面——其余 `data/state/*` 写入方（perf/health/silence）同样面临「后台线程越过用例级补丁」，当前无实测泄露；彻底治本需把状态目录改为可注入的单一来源。

**核对范围与验证**：20 份管理/用户文档 + README 全量核对（版本头 13/13 一致、changelog 时间序无逆序、目录锚点与跨文件链接除上表已修两项外全一致）；拆分后同批样标题的判定输出逐值比对（防拆分引入口径漂移）；新增/更新回归用例（去重 24 + 挂载点 4 + 矩阵 3）。**门禁**：`dev-verify` 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 新闻去重锚点校准体系修整：规则指纹 + 当前口径重算 + 锚点压缩（2026-09-18，plan-53 / rf-396~rf-398）

**背景**（用户贴回校准输出触发复核）：`calibrate-dedup-threshold.py` 的「校准建议」给出三条动作，复核结论为**不可照做**——两条已实现或已过时，且报告数字混了规则时代。复核证据与逐条结论见 [`plan/dedup-anchor-calibration.md`](../plan/dedup-anchor-calibration.md)。

**变更**：
- **口径对齐**：`news_dedup` 新增 `_pair_similarity` / `_ratio_of_norms` / `_overlap_of_norms`（相似度与实体重叠的唯一实现，链路内判定与校准工具共用），阈值全部常量化（`_CROSS_CANDIDATE_RATIO` / `_CROSS_BIGRAM_MIN` / `_SAME_SRC_BIGRAM_MIN` 等）；校准工具不再自写一份数字（此前正文 0.30 vs 代码 0.35 长期不一致）
- **规则时代可区分**：锚点记录新增 `anchor_rules_version` 字段，值由 `_rules_fingerprint()` 自动派生（阈值 + 模板词表 + 方向词对 + 归一化正则 + 行为探针的 SHA1 前 10 位）——规则一改指纹即变，不靠人工维护；校准工具用当前代码重算 ratio/bg 并按当前阈值重判，历史时代样本单列不参与结论
- **规则微调**：`_TOKEN_LIKE` 要求英数 token 含至少一个字母（纯数字不再算专名证据，翻转 24 对共享数字的误合并）；补 5 组价格方向对（站稳/跌破、走高/走低、上探/下探、回升/回落、走软/走强）。**已评估未采纳**：方向防护扩到安全区（实测 6 对里 4 对是真重复）
- **锚点体积治理**：加载超 32 MB 告警指向压缩入口；新增 `--compact`（每标题对保留最新一条，两遍扫描 + 原子替换，实测 **152 MB / 456,546 行 → 17 MB / 51,718 行，2.5 s，幂等**）；静态注释里的过期体积数字（~110k 行/35MB）同步修正
- **工具输出重建**：删除「让 `_normalize_title` 剥离年份」这类已实现建议（其举例实为板块指数骨架），补充真实原因与「少数同主体多篇报道属有意保守」说明；规则摘要从常量打印；死代码（`--dry-run` 的 `default=True` 使提示永不可达）与重复空行清除；修正 `cross_safe` 标题、`data/cache/` 过期路径
- **测试**：`test_news_sources.py` 新增 4 个测试类（数字 token 不算专名、方向对扩充、规则指纹随阈值/词对变化、`_pair_similarity` 与链路判定等价）；新增 `src/test/unit/scripts/test_calibrate_dedup_threshold.py`（分支重判、压缩幂等与 dry-run、加载去重、报告口径与过时建议回归）

### 数据源可用性矩阵：新增 provider 级「命中源」列 + 说明表补齐同花顺兜底槽位（2026-09-18，plan-52 / rf-394）

**背景**（用户反馈）：「已提供同花顺 key，但报告的数据源可用性矩阵没提到用了这个数据源」。排查确认**并非 key 未生效**——同一次运行的 `data/cache/sentiment_*` 由同花顺接口刷新（`logs/app.log` 有 `正在获取市场情绪（龙虎榜 / 连板梯队）...` → `[market_sentiment] 命中 0 条`），而是报告口径缺失。

**根因三条**：① 矩阵只按**数据类别**聚合，其 tracker 事件键（`price_price_stock_600900`）只含代码不含 provider → 从未、也无法点名某个源；② 说明表「实际数据源（链路）」是硬编码文案，未随同花顺接入同步（`datasource.md` 已登记、`data_source_matrix.py` 未更新）；③ 市场情绪（同花顺**唯一源**）的取用标记键 `sentiment` 不匹配任何类别前缀 → 落入「其他数据源」桶，连类别名都不显示。

**变更**：
- **provider 级归属登记**：`report/data_status.py` 新增 `mark_provider_used` / `get_provider_usage` / `reset_provider_usage`（存放于模块级登记表而非 DegradationTracker——归属是纯观测事实，不参与降级计数、不在 `.degradation_state.json` 堆积 provider 键）；`fetcher/chain.py` 的 `fetch_with_fallback` 与 `_try_providers` 两处成功分支登记（历史链路经 `_history_provider_label` 解析展示名），`report/market_sentiment.py`、`fetcher/financial_indicator.py`（多期序列支路）同步登记
- **矩阵**：行新增 `providers` / `providers_text`（按命中次数降序渲染为 `名称 ×次数`，无归属显示 `—`）；类别新增 `history`（历史走势）与 `sentiment`（市场情绪）并声明各链路 `data_types` 映射（链路 data_type 全覆盖由不变式用例强制，`UNMAPPED_CHAIN_DATA_TYPES` 登记有意不进矩阵者如 `bond_yield`）；`MATRIX_HEADERS` 作为 Excel 两处渲染的列头单一来源；历史日 K 等无类别事件的类别由 provider 归属单独成行
- **渲染**：HTML 模板与 Excel（数据质量仪表盘页签 + 旧样式页签）矩阵表新增「命中源（本次取数）」列
- **说明表**：price / fund_hold / history / financial_indicator 四行补「→ 同花顺金融数据（…，需 key）」；新增「市场情绪」行（同花顺唯一源 + key 就绪态 + 所需开关 `market_sentiment`）；财报全文行注明「同花顺不含公告原文，故无兜底源」；计费解析泛化为「行内显式 → provider 动态套餐 → 免费」；`used` 判定对无类别级标记的类别（历史走势）以 provider 归属为补充正面证据
- **测试**：矩阵/说明表 12 例新用例（provider 归属、市场情绪行、兜底槽位文案、`data_types` 全覆盖不变式）+ Excel 渲染 3 例；`conftest.py` 新增 `reset_provider_usage` autouse 隔离
- **测试隔离修复**（验证过程中发现）：`src/test/unit/report/` 全量运行会改写真实的 `data/state/.degradation_state.json`——`fetcher/industry.py` 的**后台批量线程活过用例 teardown**，路径 monkeypatch 已还原后线程内 `get_tracker()` 新建实例落到真实路径写盘。`conftest.py` 新增会话级兜底隔离（`_install_session_state_fallback_isolation`，在 `pytest_configure` 调用）：默认降级状态路径改为会话级临时目录，用例内仍被 `tmp_path` 覆盖、teardown 后回落到兜底值；`testplan.md` §5.8 补该条。验证 3/3 次不再触碰真实状态文件
- **文档**：`datasource.md`（同花顺「已接入域」补市场情绪开关口径 + 新增「在报告里怎么看同花顺有没被用上」段）、`technical.md`（功能语义命名表新增 3 行 + 命中源机制说明）、`requirements.md` §6.4.15 字段表（6 列 + 状态规则）、`reports-instruction.md` 章节说明

### 归档：plan-51（同花顺官方金融数据接入）设计文档随完成态归档（2026-09-17）

**背景**：plan-51 五个阶段全部落地——provider 层（凭据/qps 限速/信封错误码）、财务指标第三链路（三张合并报表派生）、基金披露持仓两源链（备源 + 联接基金直返目标 ETF）、行情与历史日 K 第三槽与交易日历官方兜底、市场情绪章内区块（开关默认关）。

**归档动作**：
- `docs-stm/plan/hithink-financial-data-design.md` → `docs-stm/archive/v0.11.x/hithink-data-source/`（`git mv`，头部改为「已实现，2026-09-17 归档」并列出三项收尾项）
- `archive/v0.11.x/archived_plan.0.11.x.md`：新增 plan-51 完成态段落（交付摘要 + 设计文档索引 + 收尾项），头部涵盖版本/归档内容/索引同步
- `managements/plan.md`：plan-51 移出在办区（在办＝plan-47/48/49/50），概述行与归档清单更新（v0.11.x 已完成项含 plan-51）
- `folders.md`：`plan/` 回到「当前为空」；归档树新增 `hithink-data-source/`；`archived_plan.0.11.x.md` 说明行同步

**收尾项（不影响已交付能力，登记在 plan 与 review-findings）**：① 复权因子事件流的消费方「分红流水漏记校验」；② 情绪事件注入 LLM 信号预消化（可选）；③ `rf-393` 实验挂载点约定与现状的一致性收敛。

### 技术债：provider 端点收口（rf-389）+ 两处 800 行硬上限拆分（rf-390）（2026-09-17）

**一、同花顺 provider 端点收口（rf-389 结项）**
- **已接线 12 个**：行情快照、历史日 K、交易日历、三张合并报表、估值快照、基金披露持仓、龙虎榜、连板梯队
- **删除 3 个无消费者端点**（按「有定义无消费者即死代码」先例并同步删单测）：`fetch_financial_indicators`（阶段 2 改用报表派生后无消费者）、`fetch_fund_nav`（净值已有两条链路）、`fetch_index_constituents`（实测 429 且无消费者）
- **保留 2 个有明确计划者**：`fetch_adjustment_factors`（分红流水漏记校验）、`fetch_fund_stock_history`（全量穿透，plan-47 前置）

**二、两处 800 行硬上限拆分（rf-390 结项）**
- `analysis/prosperity_framework.py` 934 → **254 行**：配置默认值 + 权重常量 + 六维打分器移入 `analysis/prosperity_scoring.py`（731 行）；轴=「配置打分 vs 视图装配」，装配侧显式 re-export 全部迁移名（含私有常量/打分器），既有测试与报告层 import 面不变
- `report/_report_generation.py` 843 → **763 行**：full 路径 Excel 输出包装移入 `report/_report_output.py`（87 行）；接缝守卫测试扫描范围同步扩到新模块
- 顺带修掉该文件内**重复插入两份的市场情绪装配块**；过程记录：一次性机械拆分失败（再导出不完整 + 脚本语法错误）→ 改「逐文件逐符号核对 + 每步跑测试」完成

**三、新登记**：`rf-393`（实验挂载点约定与现状不一致，需择一收敛），`rf-next → 394`。

文档：review-findings（rf-389/390 结项 + rf-393）、folders（新模块与统计）、technical（数据流指向拆分后模块）、changelog 本条。

### 新增：市场情绪与持仓热点（行动建议章内嵌块，plan-51 阶段 5）（2026-09-17）

**能力**：把同花顺官方市场级情绪数据收敛为「与我有关」的事件行——**仅保留命中持仓/穿透标的代码**的条目，渲染为行动建议章内嵌块「市场情绪与持仓热点」（开关 `market_sentiment`，报告组，默认关，菜单 E/B/L 均可输出）。

**实现**：
- `analysis/market_sentiment.py`（纯装配）：龙虎榜命中行（净买额/游资净买额/机构净买额/上榜原因/概念，金额换算亿元、概念取前三）+ 连板梯队命中行（取**最新交易日**、板位标签、次日封板）；**只按代码精确匹配，不做概念联想**（两侧概念口径不一，按名匹配会大量假命中）
- `report/market_sentiment.py`：开关门禁（关闭返回 None，零网络开销）+ 缺凭据降级契约 + 取数带 1h 缓存（`sentiment_dragon_tiger` / `sentiment_ladder`）+ 数据源使用标记
- **零命中语义**：只要一源可用就出契约（`available=True`、`rows` 可空 + 明确说明 + 保留市场概览：龙虎榜只数、连板各板位家数）——价值型组合常年不涨停/不上榜，若零命中即降级会让章节恒空、读者分不清「无事件」与「取数失败」
- 渲染：Excel `report/action_sheet.py::_write_market_sentiment_block` + HTML `partials/action_section.html` ⑦（双端口径说明同源）；接线镜像既有「景气度框架」模式：`_report_aux_metrics.compute_market_sentiment_data` → `pipeline_data["market_sentiment_data"]`（full/both 由编排层注入、basic 由 `excel_generator` 就地兜底）→ 行动建议章
- 契约台账：`market_sentiment_data` 登记附录 H（表行 + 逐键说明）与功能语义命名表；缓存模块 `sentiment_`（1h）登记注册表
- 回归 26 例：`unit/analysis/test_market_sentiment.py`（命中过滤/亿元换算/概念截断/最新交易日/概览/零命中与降级契约/脏值）、`unit/report/test_market_sentiment.py`（开关与凭据门禁/取数缓存/命中装配/开关注册/缓存模块登记）、`unit/report/test_market_sentiment_wiring.py`（编排门禁与异常兜底/Excel 区块三种形态/HTML 同源）

**形态收敛（相对设计初稿）**：初稿为「新数据域 + 独立章节」，实现改为**章内区块**——一个表不值得新增章节与页签（与景气度框架同构），且情绪数据是市场级（无 per-code 语义），套 per-code 链路域模型反而错位；已在设计文档 §3 记录偏离与理由。**未做**：把情绪事件注入 LLM 信号预消化（可选增强，待该机制扩展时评估）。

文档：plan.md 阶段 5 完成（含收敛说明）、设计文档 §3、technical（附录 H 契约行 + 逐键说明 + 语义命名表 4 行 + 数据流）、requirements（数据源表）、reports-instruction（章内区块说明）、how-to-config（开关行）、datasource / datasource-reliability（已接入域）、testplan（回归行）、folders（目录树与统计）、changelog 本条。

### 新增：行情/历史日 K 第三链路 + 交易日历官方兜底（plan-51 阶段 4）（2026-09-17）

**实现**：
- **行情第三槽**：`price_stock` = 腾讯 → 新浪 → **同花顺**；新增 `fetch_price(code)`（形态对齐既有 provider）与 `HithinkQuoteAdapter`（`last_price`→`price`、`prev_price`→`yesterday_close`、不提供总市值→`None`）。实测 600900：价 28.44 / 昨收 28.46 / 价格日 2026-09-17
- **历史日 K 第三槽**：`history_stock` 同序，`_HISTORY_PROVIDER_MAP` 注册 `src.python.providers.hithink`；`fetch_kline(code, days, start_from)`取**前复权**日 K、对齐既有 provider 形态（`{date, open, close, high, low, volume}` 升序，支持增量起点）。**实测坑**：上游历史 K 线日期字段是 `date_ms`（行情快照才是 `timestamp`），混用会解析出 0 条——已在模块文档串注明
- **交易日历官方兜底**：akshare 失败后尝试 `calendar/trading-days`（惰性导入 providers，避免 core→providers 层次反转），再失败才走简易周度判断；实测官方序列 243 个交易日
- 回归 20 例：`unit/providers/test_hithink.py`（行情映射/非 A 股跳过/`date_ms` 解析与排序/增量过滤/前复权参数）、`unit/fetcher/test_quote_adapter_hithink.py`（别名归一/契约自检/行情与历史链路段言/`_HISTORY_PROVIDER_MAP`/场外链不受影响）、`unit/core/test_trading_calendar.py`（官方兜底写入缓存、两源皆失败返回空集合）；既有断言同步（行情域四源、history_stock 三段）

**收尾项（未做）**：`adjustment_factors` 复权因子事件流暂无消费者——计划用于**分红流水漏记校验**（官方除权除息事件 × 用户「分红流水」页签交叉核对），已登记在 rf-389 待接线清单与 plan.md 阶段 4 收尾项。

文档：`plan.md`（阶段 4 完成 + 收尾项）、设计文档 §3、`datasource.md`（行情/历史行 + 已接入域 + 质量说明 + 第三链路口径）、`datasource-reliability.md`（§3.1/§3.2/§3.8 降级目标 + §3.10 已接入域）、`technical.md`（语义命名表 3 行）、`requirements.md`（数据源表）、`testplan.md`（回归行）、`folders.md`（统计）、`changelog` 本条。

### 修复：分阶段测试报告互相覆盖（详细报告丢失 Phase A）+ PE/PB 官方口径（rf-386）（2026-09-17）

**一、分阶段报告覆盖（自审发现，rf-392）**

现场：按 `test-reports/latest/` 核对详细报告时发现 `dev-verify/report.html` **只有 152 个用例**（Phase B 场景），Phase A 的 2700+ 核心单元用例全丢——两阶段共用同一报告路径，后跑的 Phase B 覆盖了 Phase A，真实失败明细（若 Phase A 红）在报告里看不到。

修改：
- `scripts/test-runner.py` 抽出 `_phase_report_path(mode_key, phase_tag)`：分阶段模式每阶段一个报告文件（`report_phase_<tag>.html`），非分阶段模式维持 `report.html`（既有约定与 CI artifact 不变）
- 汇总页新增 `_report_links_html(mode)`：逐阶段列出报告链接（实测汇总页出现「📄 Phase A」「📄 Phase B」两个链接）
- 回归 `src/test/unit/scripts/test_test_runner_reports.py`（6 例）：分阶段/非分阶段路径、构建参数使用阶段路径、汇总页逐阶段链接 / 单 report.html 链接 / 无报告占位

**二、PE/PB 改用官方 TTM/MRQ 口径（rf-386 关闭）**

现场：项目「当前 PE」用**报告期 EPS** 自算，与官方 TTM 口径差约 2.5 倍（实测长江电力 自算 47.19 vs 官方 19.17），在同一列里混用会误导估值判断。

修改：
- 财务指标契约新增 `pe_ttm`（TTM 市盈率）与 `pb_mrq`（MRQ 市净率）两字段（`schemas/datasource_fields.py`）
- `analysis/financial_statement_derive.derive_indicator_records` 支持传入官方估值快照并**只写最新一期**（历史期不倒填——估值只有「当下」一个快照，倒填等于造假）；`HithinkIndicatorAdapter` 抓取估值快照并注入
- `analysis/financial_indicator.current_valuation` 改为**官方口径优先**（`pe_ttm`/`pb_mrq`），缺失时逐字段回退自算`现价 ÷ EPS / BVPS`；官方口径不依赖现价，无价时也能给出
- 回归 11 例（派生注入只落最新期/无估值恒 None/脏值忽略；`current_valuation` 官方优先、部分缺失逐字段回退、无价仍可报、脏值忽略）

实测（长江电力 600900，真实 key）：记录携带 `pe_ttm` 19.19 / `pb_mrq` 3.21，`current_valuation` 返回 (19.19, 3.21)（此前自算为 46.4）；无官方值记录仍按自算回退（20.0, 2.0）。

文档：`developer-guide.md`（测试报告布局含分阶段说明）、`technical.md`（附录 H 契约补两字段）、`requirements.md`（R-FIN-15）、`reports-instruction.md`（PE/PB 列口径）、`changelog` 本条；`review-findings.md` 记 rf-392（已解决）、rf-386 关闭（`rf-next → 393`）。

### 新增：财务指标域第三链路 —— 同花顺官方合并报表派生（plan-51 阶段 2）（2026-09-17）

**目标**：主源 akshare（第三方封装，接口漂移风险）失效时，除 DataSinking 章节解析支路外再有一条**官方结构化**链路，并保住多期趋势能力。

**实现**：
- 新增 `analysis/financial_statement_derive.py::derive_indicator_records`（纯函数）：三张合并报表 → 标准字段记录——营收=营业收入、归母净利=归属于母公司股东的净利润（缺失回退合并净利）、经营现金流=经营活动现金流净额、EPS=基本每股收益；毛利率=(营业收入−营业成本)/营业收入、负债率=负债合计/资产合计、ROE=归母净利/归母权益（期末口径）；同比与**上年同期**比较（同文种、报告期减一年），基数为 0 或缺失即 `None`
- 新增 `fetcher/financial_indicator_adapters.py::HithinkIndicatorAdapter`（链路第三槽，单期）+ `fetcher/financial_indicator.py::fetch_hithink_indicator_series`（**多期**回退：三张报表各一次请求即得近若干期，优于链路单期兜底）；链路顺序 `akshare_financial → datasink_indicator → hithink`（可用 `preferred_provider.financial_indicator` 调换）
- **报告期口径修正（实测发现）**：上游季度条目的 `period_end_ms` 是**披露窗口起点**（2026Q1 = 04-01）而非报告期末 → 改用 `fiscal_year`+`fiscal_period` 归一到标准季末（03-31/06-30/09-30/12-31），与主源报告期完全对齐（否则同报告期错位、同比与趋势比较失真）
- 回归测试 27 例：`unit/analysis/test_financial_statement_derive.py`（口径算术/同比对齐/文种推断/季末归一/缺表即空/脏值兜底/降序限流）+ `unit/fetcher/test_financial_indicator_hithink.py`（适配器抓取与标准字段集/非 A 股跳过/契约自检/链路顺序/主源优先与备源回退/使用标记）

**实测（长江电力 600900，真实 key）**：派生序列报告期（2026-06-30 / 2026-03-31 / 2025-12-31 / 2025-09-30）与主源一致；2026-06-30 各项数值一致（营收 379.29 亿、归母 147.56 亿、毛利率 57.89%、负债率 59.36%、经营现金流 241.28 亿、EPS 0.6031、营收同比 0.033562）；差异仅 ROE（期末 6.47% vs 加权 6.55%）与 `bvps` 恒缺失（官方不给总股本，该源不产 PB）。

**待办**：PE/PB 口径修正（`rf-386`）需为指标契约新增 `pe_ttm`/`pb_mrq` 字段并同步附录 H 与双端渲染，本次未做；同花顺估值快照接口已实测可取。

**文档**：`plan.md`（阶段 2 完成）、设计文档 §3、`datasource.md`/`datasource-reliability.md`（财务指标降级链与已接入域）、`technical.md`（契约注记 + 语义命名表 2 行）、`requirements.md`（R-FIN-14 + 5.9 概述）、`testplan.md`（回归行）、`folders.md`（新文件与统计）。

### 修复：CI 时区缺陷（日期换算按北京时间固定，附时区无关性守卫）（2026-09-17）

**现场**：GitHub Actions（ubuntu-latest，UTC）在 commit `2d934682` 上 **P0（dev-verify）三个 Python 版本全红**，本地（CST）全绿——失败用例为本次新增的 `TestHithinkHoldingsNormalization::test_maps_items_to_canonical_holdings`：`AssertionError: 2026-06-29 != 2026-06-30`。

**根因**：新抽出的「毫秒戳 → YYYY-MM-DD」共享原语用了 `datetime.fromtimestamp(...)`（**本机时区**）。`1782748800000` = 2026-06-30 00:00 CST = 2026-06-29 16:00 UTC → CI 上少一天。同类内联写法仓库内还有 11 处（`core/market_hours.py`、`core/trading_calendar.py`、`llm/prompts_action.py`×4、`providers/akshare_news.py`×3、`providers/_utils.py`），任一漏改都会让报告日期/交易日边界随运行环境漂移。

**修改**：
- 新增 `core.constants.BEIJING_TZ`（UTC+8 固定偏移，无 DST）作为**项目统一自然日口径**的唯一事实来源
- `core/num_utils.py::ms_to_date_str` 按 `BEIJING_TZ` 解释为北京自然日（不再用本机时区）
- 11 处内联 `timezone(timedelta(hours=8))` 全部收敛到该常量（`market_hours` 保留 `_BJ_TZ` 别名以维持模块内可读性）
- 新增回归守卫 `test_independent_of_process_timezone`：Unix 下依次切 `UTC` / `Asia/Shanghai` / `America/New_York` 三次，断言换算结果恒等
- 自审：`review-findings.md` 记 rf-391（已解决），`rf-next → 392`

**验证**：CST 与 UTC 双时区复跑——dev-verify 2891 / verify 4856 / regression 249 / scenario+integration 317 全绿；ruff 全绿。

### 技术债整改（近 48h 实现复核）+ plan/设计文档状态核对（2026-09-17）

**一、技术债复核（近 48h：131 个源文件、+13k/−4k 行）**

审查维度：死代码（无生产引用）、同一语义多处实现（DRY/单一事实来源）、已改名符号残留、文件体积硬上限、测试标记与隔离、TODO/待实测标记。

**已修复**：
- **DRY ①「密钥文件默认路径」双份定义**：`providers/datasink.py` 与 `providers/hithink.py` 各写一份 `data/config/data_key.json` 字面量 → 收敛到 `core/datasource_credential.py::DEFAULT_DATA_KEY_FILE`（该模块本就是「通用密钥文件以 provider 为节」机制的归属地），两 provider 保留同名别名以维持既有引用面（含测试与配置校验）
- **DRY ②「毫秒戳 → YYYY-MM-DD」三处重复**：`fetcher/fund.py::_ms_to_date` 与 `report/financial_report_digest.py::_announcement_date` 为同一逻辑（宽容口径 + 越界兜底）→ 收敛为 `core/num_utils.py::ms_to_date_str`（该原语模块的既定口径：只保证返回值可安全展示、绝不抛），两处调用点改为复用；新增边界用例（0/负数/NaN/inf/超范围/数值字符串），测试改指共享原语

**新登记（未修）**：
- `rf-389` **provider API 面暂时大于消费面**：同花顺 provider 16 个端点仅 2 个已接线，其余属已批准的 plan-51 阶段 2/4/5 既定 API 面（已逐个实测字段）→ **保留并跟踪**，阶段收尾时复核；若阶段取消则按 rf-358 先例删除
- `rf-390` **两主程序文件越过 800 行硬上限**：`analysis/prosperity_framework.py` 934 行、`report/_report_generation.py` 828 行 → 记为待拆分（含拆分轴与影响面）。**本次按 ① 轴做过一次机械拆分尝试，首轮 34 例失败**（再导出清单不完整导致装配层 `NameError` + 脚本生成的 re-export 块语法错误），已**回退不提交**，并在条目内记下失败原因，拆分改由人工逐符号核对引用闭包后实施

**二、plan.md 与设计文件状态核对（归档判定）**

- `docs-stm/plan/`：仅 `hithink-financial-data-design.md`（plan-51 设计层）。**不归档**——5 个阶段中阶段 1 / 阶段 3 已完成，阶段 2 / 4 / 5 在办；已在文档头部写死归档去向（全部完成后 → `docs-stm/archive/v0.11.x/hithink-data-source/`，与 plan-45 / plan-46 先例一致）并标注当前进度
- `plan.md`：概述行补在办集合（plan-47/48/49/50/51）与 v0.11.x 归档引用（44/45/46）；**plan-47** 补前置条件更新（阶段 3 已提供官方披露持仓 top10，全量穿透仍待历史持仓接口）；**plan-50** 补「不可被 plan-51 替代」实测结论（同花顺官方不含公告原文）；plan-51 阶段表状态复核
- 归档区核对：`archive/v0.11.x/` 结构（archived_plan + archived_changelog + section-consolidation/ + prosperity-framework/）与 `plan.md` 归档清单一致；无已完成但未归档的迭代设计文件
- 编号源复核：`plan-next = 52`、`rf-next = 391`

### 新增：基金披露持仓两源链（同花顺官方源接入 `fund_hold`）（2026-09-16）

**目标**：把「基金底层持仓」从单一天天基金爬虫链路升级为**双源链**——天天基金（主）不可用时由同花顺官方披露持仓接管，提升穿透与基金业绩的数据可用性，并为后续「基金持仓 ROE 加权（需全量穿透）」打数据基础。

**落地**：
- **链路**：`fetcher/chain.py::_DEFAULT_CHAINS["fund_hold"] = ["tiantian", "hithink"]`，provider 表 `fetcher/fund.py::_FUND_HOLD_PROVIDERS` 同序（天天基金主 → 同花顺官方备，需 key；未配置 key 时由既有凭据预检自动跳过，不计熔断）。顺序可用 `config.json` 的 `preferred_provider.fund_hold` 调换（已加入校验白名单）
- **载荷归一**：`_stamp_hold_schema` 升级为 `_normalize_hold_payload`（按载荷形状识别源）——天天基金形态**原样透传**（主源可用时输出逐字不变）；同花顺形态映射为统一契约 `code/name/date/holdings`：只取 `asset_type=stock`（债券/基金资产不进股票层，避免污染占比分母）、`hold_ratio`→`ratio`（与天天基金同口径的百分数原值）、报告期取 `end_date_ms`（回退 `publish_date_ms`）→ `YYYY-MM-DD`（供报告层时效闸门判定）
- **联接基金信号**：`providers/hithink.py::fetch_fund_holdings`（项目代码入口）在「持仓仅一只 `fund` 型资产」时直接带回 `feeder_target_code`（实测 `016055.OF` → `513390.SH` 博时纳斯达克100ETF），既有 `feeder_penetration` 链路据此穿透，省去 HTML 锚点探测
- **代码候选解析**：新增 `fund_thscode_candidates`（4/5 位补零 + 场内/场外后缀，逐个试到命中）——实测 `16055.OF` 报 `code=3001`、`016055.OF` 命中（仓库读取层本就补零，此处为防御性一致）
- **不递增 `hold_schema`**：缓存写入前必经归一，载荷恒为同一形态、旧条目不会被误读；递增只会让全体用户的白缓存失效（判据是「旧载荷是否会被误读」）——该决策已写入语义版本字段的文档串
- 回归测试：`unit/fetcher/test_fund.py`（同花顺形态归一/主源形态透传/链路顺序/备源接管/语义版本）+ `unit/providers/test_hithink.py`（候选解析/联接信号/取数入口）共 20+ 例

**实测（真实 key）**：股票型 `011506.OF`、QDII `017730.OF`（返回 AMD/MU/KLAC 等境外持仓）、场内 ETF `561910.SH` 均返回 10 项股票持仓；联接基金 `016055.OF` 返回单只 `fund` 型目标 ETF；债券型 `012325.OF` 仅 `bond` 持仓 → 股票层正确为空（与天天基金「股票表为空」同口径）。

**文档**：`technical.md`（架构图链路、目录树、取数阶梯段新增「两源链与载荷归一」、语义命名表新增 3 行）、`requirements.md`（数据源清单 + 三跳阶梯段补备源规则）、`datasource.md` / `datasource-reliability.md`（基金持仓降级目标与同花顺已接入域）、`testplan.md`（回归清单新增两源链行）、`folders.md`、设计文档阶段 3 完成态。

### 文档：全量管理文档 + 用户文档一致性审计与修订（2026-09-16）

**背景**：本轮连续改动（LLM 上限、财报摘要、同花顺接入、阶段 3）后，对 10 份管理文档 + 10 份用户手册 + README 做了一次逐项核对（版本头/目录锚点/陈旧表述/计数/凭据清单）。

**发现问题与处置**：
- **`technical.md` 引用已改名的函数**（`_stamp_hold_schema` → `_normalize_hold_payload`）：文档与实现脱钩 → 已改正并补两源链说明（记为 rf-387）
- **用户手册 7 处目录链接锚点失效**（`reports-instruction.md`「页面/章节分组」标题为 `### ① 基础核心（type=always）`，目录却按 `#基础核心typealways` 链接，带圈数字的锚点归属不确定）：7 个标题各补显式 HTML 锚点，保留带圈编号与目录文本，链接确定性可用（记为 rf-388）
- **需凭据源清单缺同花顺**：`README.md`（数据源与凭据段）、`how-to-config.md`（示例注释 / `data_key_file` 字段说明 / `datasource_credential_ready` 开关描述两处）已补 `hithink` 节与 `HITHINK_FINANCE_API_KEY`
- **计数漂移**：`folders.md` 统计（主程序 281→282 文件 / 71,674→72,729 行、测试 375→379 / 109,928→112,135、用例 7,285→7,395、用户文档 5,159→5,184 行）；`test-coverage.md` unit 子标记按 `collect-test-coverage.py` 实时收集刷新（providers 315→380、fetcher 408→427、report 1847→1929、analysis 788→874、core 1215→1213、config 358→362、llm 968→969）
- **顺序与结构核对**：章节编号/分组顺序、目录与标题对应、provider 链路示意宽度对齐、管理文档「编号源」标记（plan-next 52 / rf-next 389）均已复核；`模式对应测试量` 表为 bench 派生产物，按既有约定留待发布前 `--mode bench --update-docs` 回填（文档内已有该说明）

**自审**：`review-findings.md` 记 rf-387、rf-388（均为已解决），`rf-next → 389`。

### 同花顺数据服务：key 配置 + provider 实测通过（11 端点 10 通）（2026-09-16）

**落地**：
- `data/config/data_key.json` 新增 `hithink` 节（key 由用户申领；文件已被 `.gitignore` 忽略，凭据不入库、不落日志/报告/缓存）
- provider 实测（11 端点）：交易日历、财务指标、利润表、估值快照、行情快照、复权因子、基金披露持仓、基金净值、龙虎榜、连板天梯 **全部连通**；仅 `/api/a-share-index/constituents/ths-stock-list`（指数/板块成分股）两次 429（其余端点正常）→ 判定该接口限流更严或需更高权限，阶段 4 接入前复核
- 默认限速按实测由 3 qps **下调为 2.0**（3 时连续拉 11 个端点即被 429）；新增「配置覆盖 qps / 非法值回落默认」回归用例 3 例（累计 55 例）
- 设计文档新增 §4.1「实测结果」：逐端点字段结构（可直接用于阶段 2/3 映射）、限流观察、口径差异发现；`plan.md` 阶段 1 标注实测通过、阶段 2 前置就绪

**实测关键发现**：
- 财务指标为 `abilities[5]`（growth/profitability/solvency/operation/cash-flow）+ `indicators[{index_id, value}]`，首批 `index_id` 已取到（如 `calculate_operating_income_yoy_growth_ratio`、`total_assets_net_ratio`）
- 基金披露持仓含逐项 `hold_ratio`/`investment_rank`/`start_date_ms` 与汇总（`total_stock_ratio_pct`/`main_industry`/`concentration_ratio`）；实测建信高端装备(011506.OF) 10 项、报告期 2026Q1 —— 阶段 3/全量穿透的数据基础已确认存在
- **口径差异**：官方估值为 TTM/MRQ，项目自算 PE 用报告期 EPS → 长江电力 47.19 vs 19.17（PB 一致 3.22 vs 3.21）；记为 `rf-386`（待处理），阶段 2 改为以官方为准

### 新增：pi 模型采样配置（DeepSeek 编程档，`.pi/models.json`）（2026-09-16）

**背景**：pi 支持 `samplingParams`（自由采样参数字典，逐字合并进请求体、覆盖 pi 自身字段），可用它固定 DeepSeek 的采样；但 pi CLI 只读 `~/.pi/agent/models.json`，项目级 `.pi/` 只支持 settings/扩展/技能/主题。

**落地**：
- 新增 `.pi/models.json`（版本受控的模型配置）：`deepseek-v4-flash` 与 `deepseek-v4-pro` 两个内置模型覆盖 `samplingParams.temperature = 0.0`（DeepSeek 官方参数建议：代码生成/数学解题 0.0；通用对话 1.3、创意写作 1.5）+ `maxTokens = 65536`（内置 384K 对编程偏大，收窄为单次响应设成本上限；思考与正文共享该预算）
- 未改动 `thinkingLevelMap` / `compat` / `contextWindow` / `input`，`pi --list-models` 复核覆盖生效且无加载告警（`max-out` 显示 65.5K）
- 生效方式：仓库文件为唯一事实来源，软链到全局路径（`ln -sf "$PWD/.pi/models.json" ~/.pi/agent/models.json`）；`developer-guide.md` 新增「pi 模型采样配置（DeepSeek 编程档）」小节说明理由、验证与排查；`folders.md` 目录树同步

**实测依据**：用项目 DeepSeek key 直连 OpenAI 兼容端点验证 `temperature`/`top_p` 被接受（HTTP 200，响应含 `reasoning_content`）；`pi --list-models` 确认覆盖生效。

### 新增：同花顺官方金融数据服务 provider（阶段 1）（2026-09-16）

**背景**：现有链路多处依赖非官方爬虫源（穿透基金持仓走天天基金 HTML、财务指标走 akshare），行情只有腾讯/新浪两条非官方链路，市场情绪（涨跌停/连板/龙虎榜）完全空白。同花顺官方数据服务（<https://fuyao.aicubes.cn>）为官方源、**不限累计调用次数**、字段级契约明确。

**官方覆盖边界（不可误用）**：不含分钟 K/tick、**海外行情**、**宏观数据**、**新闻公告原文与研报** → **不能**替代 DataSinking 的财报全文链路（区块② 缺口仍由财报第二数据源待办承接）。

**本次落地（阶段 1：provider 层）**：
- 新增 `providers/hithink.py`：凭据声明（`CredentialSpec`，密钥文件 `data/config/data_key.json` 的 `hithink` 节 / 环境变量 `HITHINK_FINANCE_API_KEY` 优先）、qps 限速器（默认 3，可经 `config.json` 的 `hithink.qps` 覆盖）、响应信封解析与错误码语义表（`2001` 凭据无效 / `2003` 权限不足 / `4001` 频率超限 / `5003` 数据源不可用…）、**触发限流不立即重试**（遵循官方指引，与 datasink 的退避重试策略相反）、`to_thscode()` 代码映射（`.SH/.SZ/.BJ/.OF`，场外基金由调用方给语义以区分 `00` 重叠区）
- 16 个域接口封装（只取原始响应，不做字段归一）：财务指标、利润表/资产负债表/现金流量表（`limit` 与 `start+end` 互斥）、估值快照、行情快照、历史日 K（含前/后复权）、交易日历、复权因子事件流、指数成分股、连板天梯、龙虎榜、基金披露持仓 / 历史股票持仓 / 净值
- 回归测试 52 例（`src/test/unit/providers/test_hithink.py`）：凭据门禁（缺 key 零请求）、限速先于请求、信封成功/业务错误码/非 JSON/结构异常、HTTP 分支（429 不重试）、thscode 映射（含 `002943` 的股票/场外基金双语义）、各域路径与参数拼装
- 测试隔离：限速器单例新增 `reset_hithink_limiter()` 与 `conftest.py` 的 autouse 重置 fixture（遵循单例重置强制要求）
- 设计文档：`docs-stm/plan/hithink-financial-data-design.md`（语义命名表 / 五阶段划分 / 覆盖边界 / 验证计划 / 架构约束自查）；`plan.md` 立项 `plan-51`（阶段 2~5 待办）
- 文档：`datasource.md`（清单 + 需凭据源说明）、`datasource-reliability.md` §3.10（可靠度 ★★★★★ 与已知限制）、`folders.md` 目录树

**待办（阶段 2~5，需 API key 实测校准字段）**：财务指标域第三链路（`index_id` 清单需实测）、基金披露持仓两源链（对齐全量穿透需求）、行情第三链路与交易日历/复权因子、情绪面新章节（开关默认关）。

### 修复：穿透来源键名读错（标的来源列只剩「穿透」）+ 探测性 404 日志噪音（2026-09-16）

**现场**（用户运行报告后反馈「datasinks 报错 404」）：日志出现 7 条 `[datasink] 请求 /documents/xxxxx 返回 HTTP 404`；报告「16.持仓基本面」的**标的来源**列只能显示「穿透」，看不到来源基金；工行摘要显示为 `--- stock_code: ...`（文档头）。

**三处根因与处置**：
1. **探测性 404 被记成 WARNING（日志噪音）**：章节接口在部分文档上缺失/残缺时，程序按 `datasink.sections` 偏好章节名逐个探名，不存在即 404——属**预期内落空**，随后由「切下一章节名 / 回溯上一份报告 / 全文兜底」接住。改为：**带 `section` 的探测与 `/sections` 清单探测的 404 记 DEBUG**，文档级 404（`/documents/{id}` 无 section、`/documents` 列表）仍是 WARNING（回归用例 3 例）。本次运行实测：7 条 404 全部为探测落空，**`[financial_report_digest] 取到 8/8 只 A 股财报摘要`、0 条 ERROR**。
2. **来源键名读错（真实缺陷）**：穿透 top10 契约由 `_build_penetration_result` 归一，来源键为 `sources`（合并层的 `funds` 已改名）；`_penetrated_targets` 只读 `funds` → 来源基金标签全丢。改为读 `sources`（保留 `funds` 兼容），标的来源列恢复为「穿透：[ETF] 招商中证电池主题ETF(561910)…」。
3. **目录行判定过宽**：上一版按「关键词后 90 字里出现点线/省略号」判目录，正文段落里的省略号会误伤 → 所有命中被跳过 → 退回文档开头（`--- stock_code: ...`）。改为**行内**判定（只看关键词到行尾这一行）。

**实测（真实持仓 + 真实 top10 穿透）**：区块② **8/8 行 0 失败**；标的来源逐行带出基金标签（如「穿透：[ETF] 招商中证电池主题ETF(561910)；[权益] 广发多因子灵活配置混合(002943)…」）；工行摘要恢复为「董事会报告/主要业务…」正文段。

**自审**：`review-findings.md` 记 rf-385（已解决），`rf-next → 386`。

### 增强：财报摘要两阶取数（章节阶 + 全文兜底）与年报优先回溯（2026-09-16）

**背景**：上一轮修复后区块② 仍缺工商银行——直查源侧确认：工行 **2026 半年报未被 DataSinking 收录**（索引最新为一季报），2025 年报的 `/sections` 只解析出「附件/标题」两节、裸章节名直取全 404；但**整篇正文可下**（40.1 万字 / 2.5 秒），且一季报全文里**确实含**「主要财务数据」。

**修改**：

- **章节阶**（原路径）：`_order_report_candidates` 稳定分组——**年报/半年报优先于季报**（季报无「管理层讨论与分析」，仅作最后兜底），并跳过标题含「公告」的信息披露条目（与财报混排在索引里）
- **全文阶**（新增降级）：章节阶全失败时整篇下载（`_locate_from_fulltext`，最多 `_FULLTEXT_FALLBACK_LIMIT=2` 篇）→ 在正文里按 `datasink.sections` 偏好关键词定位 `max_chars` 片段；**跳过目录行**（`_is_toc_line` 只判关键词到行尾这一行内的点线引导/省略号，避免把「利润及股息分配……」这类正文省略号误判为目录）
- 记录新增 `section_source`（`sections` / `fulltext`），排查时能区分取用方式；契约字段与展示层列不变
- 自审：`review-findings.md` 的 rf-384 转入已解决（含实现期发现的目录行定位问题）
- `plan.md`：新增 **plan-50**「财报取数第二数据源（巨潮 cninfo 备用链路）」（源侧**完全未收录**的报告无法靠降级弥补），`plan-next → 51`
- 文档：`requirements.md` R-FRD-03、`technical.md` §4.19、`datasource.md`、`datasource-reliability.md`、`reports-instruction.md`

**实测（真实持仓 + 真实穿透）**：区块② **8/8 行、0 失败**——工商银行由「目标章节缺失」变为取到 **2025 年报「董事会报告」正文段**（`section_source=fulltext`），建设银行仍为 2025 年报（章节阶命中），其余 6 只为 2026 半年报；季报未被误用为经营讨论来源。

### 修复：持仓基本面财报摘要四处缺陷（穿透名称/来源、基金撞号、章节残缺回退、报告期回溯）（2026-09-16）

**现场**（用户问询）：报告「16.持仓基本面」区块②「持仓个股财报摘要」只有 6 只 A 股，且名称列出现 `300274.SZ`、`300502.SZ` 等代码，无法判断是持仓还是穿透；查询中另发现「广发多因子灵活配置混合」行配的是深市 002943.SZ 宇晶股份的半年报。

**根因（四处）**：
1. **穿透名称/来源未带入契约**：穿透层（`penetration.py`）一直带 `name` 与 `funds`（来源基金），但标的清单只取代码 → 展示层回退 symbol、无来源信息
2. **场外基金代码撞号**：`002943` 既是场外基金也是深市股票代码，`to_fmp_symbol` 按前缀判 A 股即命中（`is_otc_fund_by_name` 早已能区分，两区块都没用）
3. **章节清单非空但残缺时不回退**：建行半年报被 DataSinking 只解析出 2 个无关章节 → 匹配为空且仅在「清单不可得」时才回退偏好名直取 → 整篇白丢
4. **最新一期缺章节即判失败**：半年报缺「管理层讨论与分析」时不回溯上年年报；失败原因统一写「未取到财报」

**修改**：
- `fetcher/financial_report.py`：`collect_a_share_targets` 持仓侧过 `is_otc_fund_by_name` 剔除场外基金、穿透侧带 `name`/`sources`（兼容裸代码）、直接持仓优先；新增 `target_source_label`（直接持有 / 穿透：来源基金…）；抽出 `_collect_doc_sections`（清单不可得**或残缺**均回退偏好名直取）；新增 `fetch_symbol_report_detailed`（按报告期回溯最多 3 篇 + 失败原因），`fetch_symbol_report` 变薄包装
- `report/financial_report_digest.py`：契约行新增 `target_source`，失败项带 `kind`/`target_source`/细化原因；穿透名称回填（缺名仍回退 symbol）
- `report/financial_indicator.py` + `report/orchestrator.py`：`_penetrated_codes` → `_penetrated_targets`（名称 + 来源基金），区块① 同步享受名称回填与来源标注
- `report/fundamental_snapshot_sheet.py`：区块①、区块② 各增「标的来源」列（19→20 列 / 9→10 列），说明区补标的来源与报告期回溯口径
- 文档：`requirements.md`（R-FRD-01/03/05、章节表与两区块列数）、`technical.md` §4.19、`reports-instruction.md`、`datasource.md`、`datasource-reliability.md`
- 自审：`review-findings.md` 记 rf-380~rf-383（已解决）、rf-384（源侧未解析章节是否加全文兜底，待评估），`rf-next → 385`

**实测（真实持仓 + 真实穿透，2026-09-16）**：行数 6 → 7；穿透标的显示中文名（阳光电源/中际旭创/新易盛/宁德时代/华峰测控）并标注来源基金；场外基金 002943 不再入列；建设银行由「未取到」变为取到 2025 年报（回溯生效）；工商银行仍缺（源侧未解析章节），失败原因写明「目标章节缺失（已试报告期：2026-03-31、2025-12-31、2025-09-30）」。

### 修复：思考耗尽 max_tokens —— 全模块 token 上限整体上调 50%（2026-09-16）

**现场**：`logs/app.log` 出现 `LLM 输出思考部分耗尽 max_tokens 预算，未生成最终文本（建议增大对应 max_tokens 配置或降低 reasoning_effort）` + `Extended Thinking 思考部分耗尽 max_tokens 预算（无正文），关闭 thinking 重试一次`。

**根因**：`max_tokens_{module}` 是 **thinking + 正文共享预算**。预算偏紧时思考先吃满预算、响应仅含 thinking block 无正文 → 只能关闭 thinking 重试一次（多一次调用，且本次深度下降）。

**修改（按 +50% 整体上调，模板 + 用户配置文件同步）**：

| 配置项 | 旧 → 新 |
|---|---|
| `max_tokens_global_macro` | 2048 → **3072** |
| `thinking_budget_global_macro` | 4000 → **6000** |
| `max_tokens_expert_review` | 24000 → **36000** |
| `thinking_budget_expert_review` | 16000 → **24000** |
| `max_tokens_health_check` | 16000 → **24000** |
| `thinking_budget_health_check` | 12000 → **18000** |
| `max_tokens_penetration_deep` | 8192 → **12288** |
| `thinking_budget_penetration_deep` | 8000 → **12000** |
| `max_tokens_news_correlation` | 2000 → **3000** |
| `thinking_budget_news_correlation` | 4000 → **6000** |
| `debate.procon.per_call_max_tokens` | 12288 → **18432** |
| `debate.max_total_tokens_per_report` | 48000 → **72000** |

- 代码兜底：`llm/generators.py::generate_debate_procon` 的 `_max_tokens` 兜底 12288 → **18432**（三段 3×18432 = 55296 < 72000，预算守卫不会被提前触发）
- 模板：`config/_llm_settings_defaults.py` 同步全部新值（用户可见可调）
- 用户配置：`data/config/llm_settings.json` 同步全部新值
- 文档同步：`how-to-config-llm.md`（示例 JSON / 模块参数表 / `thinking_budget` 与 `max_tokens` 关系 / 调参建议）、`llm-technical.md`（各模块默认 max_tokens 表）、`requirements.md`（辩论 per-call 与总预算两行）
- 回归测试：`test_llm_settings.py::TestTokenCapHeadroom`（基线值 + 「thinking 模块 max_tokens > thinking_budget」正文余量不变量 + 辩论三段预算关系）；`test_debate_generators.py` 兜底值同步为 18432

注：caps 是**上限**而非固定用量，正常输出不会因此变长；只在被截断/耗尽场景才多消耗预算，从而省掉一次多余的「关闭 thinking 重试」调用。

### 修复：辩论模式每阶段输出上限 8192 → 12288（智囊团复盘截断）（2026-09-16）

**现场**：`logs/app.log` 反复出现 `LLM 输出被截断 [Claude]: max_tokens_expert_review=8192, 实际输出=8192 tokens`，随后自动以 12288 重生成（一次多余调用 + ERROR 噪音）。

**根因**：用户开启了**辩论模式**（`llm_debate_procon`），智囊团复盘走 `generate_debate_procon` 三段式路径，其每阶段上限取 `debate.procon.per_call_max_tokens`（**不看**模块级 `max_tokens_expert_review=24000`）；而模板默认与用户配置该键均为 `null` → 落到代码兜底 **8192**，pro 段即被截断。

**修改（按 +50%）**：
- 代码兜底：`llm/generators.py::generate_debate_procon` 的 `_max_tokens` 兜底 **8192 → 12288**
- 模板默认：`config/_llm_settings_defaults.py` 的 `debate.procon.per_call_max_tokens` **null → 12288**（并在模板中补该键语义注释，用户可见可调）
- 用户配置：`data/config/llm_settings.json` 的 `debate.procon.per_call_max_tokens` **null → 12288**
- 文档同步：`requirements.md`（R-LLM-DB-PROCON-06 与配置矩阵行）、`technical.md`（Token 预算守卫表）、`how-to-config-llm.md`（辩论段说明与示例）
- 回归测试：`test_debate_generators.py::test_per_call_max_tokens_fallback_is_12288`（配置缺省/为 null 两种情形下，三段调用的 `max_tokens_override` 必须为 12288，不得回退 8192）

注：模块级 `max_tokens_expert_review`（24000，非辩论路径使用）未改动；辩论总预算 `max_total_tokens_per_report`（48000）与单次超时（90s）亦不变。

门禁：四个 `--ci` + `--mode verify,regression` + ruff 全绿。

### plan-46 设计文档归档（docs-stm/plan → archive/v0.11.x/prosperity-framework）（2026-09-16）

plan-46（景气度框架诊断，实验性功能）已实施完成，按「中间设计文件随完成态归档」惯例把设计文档从 `docs-stm/plan/` 归档到 `docs-stm/archive/v0.11.x/prosperity-framework/`（`git mv` 保留历史）：

- `prosperity-framework-design.md` — 头部状态改为「**已实现，2026-09-16 归档**」并补归档位置、后续项指引（`plan-47`/`plan-48`/`plan-49`）与实施记录指向
- `archived_plan.0.11.x.md`：新增「P1 — 已完成（plan-46 完成态）」条目（动机 / 方案（六项落地）/ 不做 / 口径要点（含两轮修订）/ **5 处实施期缺陷修复**（rf-373~377）/ 降级矩阵结论 / 后续项 / 设计文档索引），头部涵盖版本与归档内容同步
- `plan.md`：plan-46 详细条目移出（完成态转入归档），P1 待办区保留 `plan-47`/`plan-48`/`plan-49`；待办说明与归档清单更新为 plan-44 / plan-45 / plan-46
- `folders.md`：`plan/` 目录树与统计改为「当前为空」；`archive/v0.11.x/` 树新增 `prosperity-framework/`（含设计文档说明）；archive 统计与项目文档合计同步（138 → 139 文件）
- 归档后 `docs-stm/plan/` 为空（后续新设计文档仍放此处）

门禁：四个 `--ci` + `dev-verify` + ruff 全绿。

### 景气度框架诊断：降级矩阵复核（6 场景）+ 剩余问题登记（plan-47~49）（2026-09-16）

按「先验证稳定性、再谈扩展与转正」的结论执行：**隔离目录**下（`docs-stm/tmp/pf-sweep`，跑完清理；不改真实 `reports/`、不写用户配置）复跑 6 个场景，验证实验功能的降级行为。

**降级矩阵（全部符合预期）**

| 场景 | 报告/块 | 六维表现 |
|:--|:--|:--|
| 0 交易日基线 | ✅ / ✅ | 42/80（52%）部分契合；① 9/25、③ 15/15、④ 10/10(partial)、⑤ 4/15、⑥ 4/15；② unverified（仅 A 股个股有 ROE） |
| 1 非交易日（行情全零） | ✅ / ✅ **不崩** | 总分 1/55；①③→0（市值口径失效）、④ unverified、⑤ 仅换手子项；**验证 rf-373 修复**（原为合并单元格崩溃） |
| 2 `history` 关闭 | ✅ / ✅ | 总分 38/65；⑥ `unverified` 并给出可读原因（不崩、不臆造） |
| 3 基本面契约缺失 | ✅ / ✅ | ② `unverified` + 提示开启 `financial_indicator` |
| 4 关基金深度分析 | ✅ / ✅ | ① 仍计分（退化为纯持仓类型口径）、③④⑤ 不受影响 |
| 5 快照 <2 期 | ✅ / ✅ | ⑤ `partial`（换手子项不计分，41/80），集中度仍计分 |

**剩余问题登记（`plan.md`）**：
- `plan-47` 基金持仓 ROE 加权（扩展 ② 覆盖率：21.9% → 60~80%；依赖全量穿透；属推演须标「按框架推演」）
- `plan-48` 场外流动性补齐（④ 维：`redemption_limits` 配置化 或 场外类型默认档）
- `plan-49` 转正评估（判据：降级矩阵全绿 ✅ + 真实使用 ≥2 周 + 口径认可 + 门禁全绿；**当前结论：暂不转正**，保持实验组默认关）
- `plan-46` 设计文档归档随 **v0.11.1 发布**进行（不在开发期归档）

说明：本矩阵由隔离脚本执行，未修改任何生产代码（本轮无新缺陷，故未新增 review-findings 条目）。

门禁：四个 `--ci` 全绿。

### 景气度框架诊断：基金类型兜底补齐 + 两视角叠加口径（2026-09-16）

用户确认为「A = 保持方法原意」后，补齐维度①的数据可得性（不改评分标准、不动阈值）：

- **基金类型兜底标签** `_fund_type_fallback_label`：板块识别失败（`classify_sector` 返回 `--`）时按基金类型补保守标签 —— 固收/货币 → `债券现金`（防御侧）、QDII/海外 → `境外资产`（中性）、宽基/指数/ETF 联接 → `宽基指数`（中性）、其余 → `未分类资产`（中性）；**判定只用 `core/code_utils`**（类型判定中心化），且**ETF/指数判定优先于货币**（`is_money_fund_by_name` 对「国证自由现金流 ETF」会误判为货基，若先判货币会把场内权益 ETF 误标成固收）；兜底项**只按类型标签参与关键词匹配**（不带名称，防「现金」类误命中）
- **两视角叠加口径**：视角一 = 穿透底层（`ratio_pct`）；视角二 = 每个直接持仓按自身权重（板块或类型标签）；**去重范围收窄为仅直接持有的证券** —— 原实现把出现在穿透 `sources` 里的基金整只跳过（只由 top10 底层代表），实测覆盖率仅 **48.47%**（8 只 QDII/联接/债基/宽基 ETF = 51.28% 权重无板块信息）；现两者叠加后归一，证据披露「穿透项 X% / 叠加合计 Y% / 兜底 N 只」
- **回归测试**：新增 `TestFundTypeFallback` 6 例（固收→防御、ETF 不被货币误判为防御、QDII→境外中性、主动权益→未分类、已有板块不被覆盖、基金为主组合覆盖达标且景气+防御=归一后的确定值）；并同步并集/去重相关 4 例期望

**真实持仓复核对比**

| | 改前（仅穿透视角） | 改后（兜底 + 两视角） |
|:--|:--|:--|
| 维度① 可判定权重 | 48.47%（8 只 / 51.28% 权重无信息） | **115.62% 叠加后归一**，兜底 8 只全部接入 |
| ① 得分 | 0/25（景气 14.71%） | **9/25**（景气 31.92%、防御 34.65%） |
| **总分** | 42/100（部分契合） | **51/100（部分契合）** |

门禁：四个 `--ci` + `--mode verify,regression` + ruff 全绿。

### 修复：景气度框架诊断持仓视角 ROE 文案重复（2026-09-16）

渲染后出现「ROE 需核实｜ROE 需核实（未取到基本面）」重复：契约 `holdings_view[*].notes` 与渲染层 ROE 列各自表达同一事实。现由**渲染层 ROE 列**唯一表达「需核实」，契约不再重复备注（保留「命中景气/防御关键词」「低 ROE（x%）→ 存在修复弹性」等增量信息）。

门禁：四个 `--ci` + `--mode verify,regression` + ruff 全绿。

### 景气度框架诊断：口径修订（并集归一 + 互斥归类 + 关键词补词）与配置同步（2026-09-16）

按用户真实持仓复核，修订第①②③维的统计口径与默认词表（原口径只覆盖 34.6% 市值、且同一标的可被景气/防御重复计数）：

- **并集覆盖 + 归一**（`_sector_weight_items`）：穿透重仓各底层标的（含基金拆解，按 `codes` 与 `sources` 里的基金代码标记已覆盖）+ **未被穿透覆盖的其余直接持仓**（QDII/联接/债基等，按 `classify_sector` 板块）合并后按已覆盖市值归一；证据披露覆盖率（如「覆盖 48.47% 市值…按已覆盖部分归一」），读者可见评分分母
- **互斥归类（防御优先）**：同一标的命中多类词时只计防御类，避免景气+防御之和 >100%
- **关键词补词（配置层单一事实来源）**：景气词加「电池/光伏/高端装备/制造/能源资源/电力/石油/煤炭」，全球优势词加「电池/高端装备/制造/电力」，防御词加「债/货币/现金」；模块默认值改为**从 `config/_config_defaults` 派生**（避免两处词表漂移），`config.json` 同步重生成（校验 0 问题）
- **回归测试**：并集覆盖计入未穿透持仓、已覆盖基金不重复计入、互斥归类（重叠词只计防御）、无重叠时正常计分；`tests` 全绿

**真实持仓复核对比**（同一份报告，改前 → 改后）

| 维度 | 改前 | 改后 |
|:--|:--|:--|
| ① 景气方向/通胀属性 | 0/25（口径仅覆盖 34.6% 市值） | 0/25（并集覆盖 48.47%；景气 14.71%、防御 77.10%） |
| ③ 全球视野/比较优势 | 5/15 | **15/15**（全球优势环节 25.64% + 境外占比 78.10%） |
| ⑥ 业绩与回撤印证 | 缺失（基准结构假设错误） | 4/15（组合 -18.11% / 沪深300 -10.36% / 回撤 22.42%） |
| **总分** | 32/100（不契合） | **42/100（部分契合）** |

门禁：四个 `--ci` + `--mode verify,regression` 5001 passed / 0 failed + ruff 全绿。

### 修复：维度⑥「业绩与回撤印证」误报缺失（基准结构假设错误）（2026-09-16）

用户复核报障「业绩与回撤印证说缺失，但组合历史走势与回撤章节明明有数据」→ 定位为**结构假设错误**：`PortfolioHistoryCalculator.get_combined_timeseries()` 的 `benchmarks` 契约是 **`list[dict]`**（`[{code, name, bars, total_return_pct, max_drawdown_pct, …}]`），而实现按 `dict[str, dict]` 调 `.values()` → `AttributeError` 被维度守卫吞成「需核实」。真实数据（用户持仓）：组合区间收益 **-18.11%**、最大回撤 **-22.42%**、沪深300 **-10.36%**，数据齐全却未计分。

- **修正确性**：新增 `_benchmark_returns()` 同时兼容 `list[dict]`（生产形态）与 `dict[str, dict]`（注入形态）；非 dict 元素/缺字段/`bool`/非数值一律跳过且**不抛异常**（注意 `finite_or(None)` 内部 `float(None)` 会抛 TypeError，故先做类型判定）；证据文案带基准名（如「未跑赢最强对比基准（沪深300 -10.36%）」）
- **修降级语义**：`drawdown_available=False`（历史样本 <60 交易日）时**只降级回撤子项**（收益仍计分，标 `partial` 并列入未验证），不再整维判为缺失；`status=degraded` 也计分但标注口径可能不完整；仅 `status=unavailable`/无收益字段才 `unverified`
- **回归测试**：`TestPerformanceDimensionBenchmarkShapes` 8 例（list 形态计分且证据含基准名、未跑赢场景 4 分档、dict 形态兼容、畸形基准 5 种输入不抛异常、degraded 计分带注记、unavailable 未验证、回撤样本不足 partial、真实形态经契约端到端 scored）
- **真实管线复核**：both 路径实际块输出「总分 32/100（32%）」，六维全部可计分——景气 0/25、ROE 9/20、全球 5/15、流动性 10/10、集中度与周期拼接 4/15、业绩与回撤印证 **4/15**（组合 -18.11% / 沪深300 -10.36% / 回撤 22.42%）

门禁：四个 `--ci` + `--mode verify,regression` 4997 passed / 0 failed + ruff 全绿。

### 修复：full 路径（菜单 L）HTML 未转发景气度框架契约（2026-09-16）

用户复核报障「开关已开、运行后行动建议章后没有新增内容」→ 定位为**接缝缺口**：`_generate_full_html_report`（full 路径 HTML 包装函数）既未声明也未转发 `prosperity_framework_data`，而 both 路径已转发——`count=1` 的批量替换只覆盖了其中一条调用链。**Excel 侧不受影响**（`generate_excel_report` 自行就地构建契约），故 both/full 的 Excel 一直有块，HTML 仅在 both 路径有块。

- 修复：`_generate_full_html_report` 补参数声明与转发（→ `write_html_report`），full 路径调用点补传 `pipeline_data` 中的契约
- 守卫（防再漏）：`test_prosperity_framework_wiring.py::TestHtmlCallSiteSeam` 3 例——① 源码级断言 `_report_generation.py` 中**每处** `write_html_report(...)` 调用都带该参数（新增其它 HTML 调用链忘记转发即失败）；② 包装函数签名含该参数且函数体内转发；③ full 路径调用点从 `pipeline_data` 取契约传入
- 真实数据复核（用户真实持仓 + 真实配置，输出到 `docs-stm/tmp/` 并清理）：both 与 full 两路径的 HTML 均含「⑥ 景气度框架诊断（实验性）」块与免责句；Excel「7.行动建议」页签含块（本次实测「总分 28/85（33%）—— 评级：不契合」）

门禁：四个 `--ci` + `--mode verify,regression` 4989 passed / 0 failed + ruff 全绿。

### 修复：景气度框架诊断拖垮整份报告 + 行情全零 Excel 崩溃（2026-09-16）

**缺陷①（P0，用户报障「运行后有数据处理异常」）**：`logs/app.log` 显示 `AttributeError: 'SnapshotData' object has no attribute 'get'` → **整份 full 报告生成失败**。根因：`analysis/prosperity_framework.py::_turnover_proxy_pct` 按 dict 取快照字段，而 `report/history_snapshot.load_all()` 返回的是 **`SnapshotData` 冻结 dataclass**（`.accounts[*].holdings[*].code`）；异常自实验功能冒泡，违反「实验功能不得影响主报告」与数据降级治理纪律。

- **修正确性**：新增 `_snapshot_holding_codes()` 同时兼容 `SnapshotData` 对象（生产形态）与 dict 形态（`accounts`/`holdings`/`details` 键），缺失字段按空集处理且**不抛异常**
- **修韧性**（三道防线）：① 单维计算经 `_guard_dimension()` 包裹 → 单维异常降级为「未验证」，不影响其余维度与契约；② 组装辅助 `compute_prosperity_framework_data` 整体 try/except → 警告 + 返回 None（等价开关关闭，块不渲染）；③ 三个调用点（`_report_generation` 的 both/full、`excel_generator` basic 兜底）各自再加一层兜底
- **回归测试**：`test_prosperity_framework_edge.py` 新增快照形态回归 5 例（dataclass 可算换手代理 66.67%、端到端契约 scored、dict 形态兼容、畸形对象降级、缺 holdings 属性）；`test_prosperity_framework_wiring.py` 新增韧性隔离 4 例（build 抛异常 → 返回 None、坏快照不崩、单维异常隔离、真实 `SnapshotData` 全链路）；新增场景测试 `test_scenario_prosperity_framework.py` 4 例（真实 dataclass 快照 + 隔离输出目录驱动 `generate_excel_report`：功能开/关、坏快照、构建抛异常四种情形**报告均须生成成功**）

**缺陷②（既有缺陷，被本轮场景测试暴露）**：行情全零（非交易时段/网络异常）时，「持仓明细与分类」页签先写**整行合并**的提示行，随后仍以该行为数据起点写入明细 → `AttributeError: 'MergedCell' object attribute 'value' is read-only`，Excel 报告生成失败。该缺陷源自合并前的 `market_value_sheet.py`（批次② 原样带入），既有单测因用 MagicMock 工作表而漏检。

- **修复**：`holdings_detail_sheet._write_market_value_block` 中提示行之后显式重置 `data_start = row`（分类区块同样显式化数据起点语义）
- **回归测试**：`test_holdings_detail_sheet.py::TestAllZeroPriceRegression` 2 例（真实 openpyxl：全零场景不崩溃 + 提示行在数据行之前）

**验证**：用户真实快照（73 期 `SnapshotData`）只读复算 → 换手代理与契约均正常；四个 `--ci` + `--mode verify,regression` 4989 passed / 0 failed + `dev-verify` 2779 passed + ruff check/format 全绿。

### plan-46 景气度框架诊断（实验性功能）实施（2026-09-16）

借鉴开源项目 **zhengxi-views**（郑希观点库，MIT；<https://github.com/lyra81604/zhengxi-views>）从公开采访蒸馏的景气度投资方法骨架，落地为本仓的**实验性功能 `prosperity_framework`**（默认关）：把「全球视野找变化 → 顺产业链找通胀环节 → 落到中国比较优势环节 → 选流动性够 + ROE 低位有弹性的标的 → 多维跟踪与周期拼接 → 组合分散 + 行业比例 + 退出纪律」转成对**本仓持仓组合**的可计算诊断。**只借鉴可计算骨架与评分口径**（不引入其语料库、基金快照、全市场检索）。

**六维评分卡（满分 100）**：景气方向/通胀属性 25 + ROE 低位弹性 20 + 全球视野/中国比较优势 15 + 流动性 10 + 集中度与周期拼接 15 + 业绩与回撤印证 15；输入全部取自既有能力（穿透重仓板块/概念、`financial_indicator_data` 的 ROE、`check_liquidity` 变现天数、历史快照换手代理、`history_data` 收益与回撤），**不新增外部数据源与 LLM 调用**。

**实现**
- 新增 `analysis/prosperity_framework.py`（纯计算；市价读取经 `finite_or` 归一）；配置新增顶层键 `prosperity_framework`（景气/全球比较优势/防御关键词 + 集中度目标，手动编辑）并重生成 `config.json`
- 实验开关 `prosperity_framework`（实验组、默认关、`affects_report=True`）；实验块由 4 项增至 5 项（追加在组末，既有编号不变）
- 契约 `prosperity_framework_data` 进数据契约台账（pipeline_data 键 + 类型映射）与附录 H（键表 + 逐键契约说明）
- 组装辅助 `report/_report_aux_metrics.py::compute_prosperity_framework_data`：开关关闭返回 None；穿透优先取 `prep.penetrated_assets`（缺失按需计算）；流动性/快照取数失败降级为该维未验证
- 接线：`_report_generation` 的 both 与 full 两路径注入契约；`excel_generator` 在 basic 路径就绪后就地兜底
- 渲染：行动建议章内嵌块——HTML `partials/action_section.html` ⑥ 块（总分/评级 + 六维明细 + 持仓视角 + 需核实清单 + 免责句）、Excel `report/action_sheet.py::_write_prosperity_block`

**降级与诚信口径（红线）**：数据缺失维度一律 `unverified`（**不计分、不臆造**）并给出可读原因；总分只按已计分维度折算（`scored_weight` / `total_score_pct`），界面同时显示未验证清单；渲染固定带免责句（衡量「组合与框架的契合度」，非组合优劣、非投资建议）；每条得分在 `evidence` 中给出可追溯口径。

**测试**：`unit/analysis/test_prosperity_framework.py`（27 例：六维计分/缺数据降级/总分口径/持仓视角/评级边界/配置覆盖）+ `test_prosperity_framework_edge.py`（13 例：空/None/零/异常类型/全防御/未知板块/极端集中度/快照缺失/负收益深回撤）+ `unit/report/test_prosperity_framework_wiring.py`（7 例：开关门控、prep 穿透口径、Excel/HTML 双端块显隐）；TUI 面板编号断言与文档串同步。

**文档同步**：设计文档 `docs-stm/plan/prosperity-framework-design.md`（含上游归属与许可、数据映射、六维口径、契约结构、约束对照、验收标准）；`technical.md`（§4.20 叙述 + 语义表 3 行 + 附录 H + 附录 I 段号）；`requirements.md`（§5.11 R-PF-01~08 + 配置键）；`how-to-config.md`（开关表 + 配置键 + 实验组计数 4→5）；`reports-instruction.md`（行动建议章块）；`README.md`；`testplan.md`（§4 回归行）；`folders.md`（树 + 统计）；`plan.md`（plan-46 已实施）。

**实施期自查**：`rf-372` —— 新增实验开关触发三处跨接缝漂移（TUI 面板编号断言、附录 H 台账一致性用例、both 路径无 `prep` 变量），均已修正并同步测试与文档。

门禁：四个 `--ci` + `--mode verify,regression` 4980 passed / 0 failed + `dev-verify` + ruff + 版本一致性全绿。

### 管理/用户文档二次核对与整改（rf-371）（2026-09-16）

技术债整改（rf-370）后逐份复核 10 份管理文档 + 11 份用户文档的「顺序/编号、清单完整性、示例与计数、章归属表述」，整改 6 类：

- **`technical.md`**：Web 配置编辑接口表的可编辑面分组名改用 surface 实际键（`report_switches`）；白名单段落去掉已不存在的 `submodule` writer、「增强子模块开关 6」「功能开关 20」改为「报告章节与增强 8（`report_switches` 独立视图）+ 功能开关 28（实验 4 + 常规 16 + 报告 8）」并补记 43 条白名单；契约注记序号随章节合并更新（`portfolio_evolution` number=14、`action` number=7、「报告顺序完整 16 项」）；`features.json` 行改「28 项声明 / 三组（实验 4 + 常规 16 + 报告 8）」
- **`requirements.md`**：P 菜单条目删除已随 plan-44 移除的「报告增强子模块配置（8 项）」入口（改指菜单 `[S]`「报告章节与增强」块）；R-WEB-08 可编辑面清单改用 `report_switches`；features.json 章节改「28 项 / 三块（实验 4 + 常规 16 + 报告 8）」
- **`how-to-config.md`**：配置样例中「报告子模块开关」注释改为指向 `features.json`（功能开关注册表，菜单 `[S]`）；`report_section_order` 行的「默认顺序（20 项）」改 17 项
- **统计快照刷新**：`test-coverage.md` 按 `collect-test-coverage.py` 实测更新模式计数（unit 6900→6905、standard 5903→5908、report 1902→1907、all 7213→7218）、`unit_report` 与「报告生成」功能域计数；`folders.md` 更新测试代码（372 文件 / 109,295 行）、测试用例（7,218 个）、管理文档（10 / 10,085 行）与项目文档合计（52,549 行）

校验：章节表编号与注册表逐一比对（requirements §6.3 / how-to-config / reports-instruction 全 OK）、§6.4 编号 1..18 连续、README 分组合计 17、语义表 97 slug 覆盖全部 28 个开关、目录树全量比对无遗漏、陈旧表述扫描零命中。

门禁：四个 `--ci` + `--mode verify,regression` + `dev-verify` + ruff + 版本一致性全绿。

### 过去 96 小时实现技术债整改（plan-42~45，rf-370）（2026-09-16）

审计窗口内 67 次提交（plan-42~45 及发布/文档收尾）的代码、配置与测试，整改 7 类技术债：

**① 语义索引正向校验失效（最重要）**：`scripts/check-semantic-index.py` 的正向项仍在解析 `_config_defaults.py` 的 `report_submodules` 字典——该机制已随「报告增强子模块并入功能开关注册表」移除，校验恒为空集，**新增开关可绕过「功能语义命名表」登记**。
- 改为 AST 解析 `src/python/config/features.py::feature_switch_registry`，校验「每个功能开关都已在语义表登记」（表外键报错）；脚本 docstring、`-v` 输出、`--ci` 摘要与单测（`TestReportSubmodulesKeys` → `TestFeatureSwitchKeys`、run_checks 夹具改 features.py 形态）同步
- 新校验立刻暴露 **12 个开关未登记** → `technical.md` 功能语义命名表补 12 行：`llm_debate_procon`/`llm_debate_conditional`/`llm_debate_qa_concentration`、7 个 `metrics_*`（夏普/卡玛/HHI/胜率/换手率/风险贡献/Beta）、`enable_interactive_charts`、`datasource_adapter`

**② data 层可用性字典双份实现**：`excel_generator` 内联构造 + integration 一致性测试手写镜像，章节合并每批需改两处（rf-367 即此类漂移）。
- 下沉为 `report/excel_sheet_factory.build_data_availability()`（合并章契约 OR、契约 None、news/llm 口径集中一处），生成器与集成测试镜像改用同一函数；新增 5 例口径守卫（fund_deep 开/关、单契约注入、两财报契约随开关、news/llm 随 include）

**③ 死代码 / 死认知**：删除 `html_writer_nav` 的 `manager_data` data_flag（章节移除后无消费方；集成测试镜像同步删）；`registry.py` docstring 示例键 `fund_manager` → `position_structure`。

**④ Web 面旧机制命名**：surface 键 `submodules` → `report_switches`（`web/config_edit.py` + `static/web/main.js` 渲染调用同步）；删除前端 `CONFIG_LABELS.submodules` 陈旧字典（漏列两个开关且与服务端 `features.labels` 同源下发设计矛盾）。

**⑤ 测试用例陈旧 / 失效断言**：`test_excel_report_structure` 夹具改用当前注册表切片（删 `fund_manager`/`position_relationship`/`fund_concentration`，序号与页签计数同步 16/9 → 14/7）；`test_config` 的「重复序号」「多问题累加」用例改用现存键（此前误走「未知键」分支，断言通过但未测目标行为）；`test_orchestrator`/`test_excel_market_data`/`test_holdings_detail_sheet` 注释去掉 `report_submodules.*` 旧表述；`test_financial_indicator` 的「旧配置不再生效」守护样本改为中性旧键名；plan-45 新增用例的**恒真断言**（先按值过滤再断言不存在）改为「占位文案存在 + 无集中度数据行」正向断言。

**⑥ 配置与模板漂移**：`data/config/config.json` 按当前模板重生成（补 plan-43 引入的 `holdings_start_date`，其余键值保持仓库现值：相对路径、显式 `cache_ttl`、显式 `report_section_order` 16 项），`validate_config()` 0 问题。

门禁：四个 `--ci`（含改造后的语义索引）+ `--mode verify,regression` + ruff check/format + 版本一致性全绿。

### plan-45 设计与实施层文档归档（docs-stm/plan → archive/v0.11.x）（2026-09-16）

plan-45（报告章节整合，注册表 21 → 17）四批全部实施完成，按「中间设计文件随完成态归档」惯例把两份文档从 `docs-stm/plan/` 归档到 `docs-stm/archive/v0.11.x/section-consolidation/`：

- `section-consolidation-design.md` — 设计层（四项合并方案 / 可见性模型扩展 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）；头部状态改为「**已实现**（2026-09-16 归档）」并补归档位置与实施记录指引
- `section-consolidation-iteration.md` — 实施层施工单（命名统一总表 / 接缝地图 / 逐批施工步骤与量化验收 / 十轮复盘记录 / 守卫清单与基线方法 / 领域层与章节层边界 / 文档同步清单）；头部状态改为「**✅ 四批全部实施完成**」并列出四批提交号，批次②③④ 小节标题标注「✅ 已实施」
- `docs-stm/archive/v0.11.x/archived_plan.0.11.x.md`：新增「P1 — 已完成（plan-45 完成态，2026-09-16 归档）」条目（动机/决定/方案/四批实施记录与提交号/十轮复盘/验收达成/实施记录指引 + 设计文档索引），头部涵盖版本与归档内容同步更新
- `plan.md`：P1 待办区移除 plan-45 条目（恢复「无待办项」），待办说明与归档清单改为 plan-44 / plan-45 并指向新设计文档目录；`plan-next` 保持 46
- `folders.md`：`plan/` 目录树改为空目录说明、统计行 2 文件/373 行 → 0；`archive/v0.11.x/` 树新增 `section-consolidation/`（含两份文档）；archive 统计 129/42,429 → 131/42,802（md 125→127），项目文档合计行同步

门禁：四个 `--ci` + `dev-verify` 全绿。

### plan-45 四批后管理/用户文档一致性与顺序整改（rf-369）（2026-09-16）

对 10 份管理文档 + 11 份用户文档逐份核对「章节表顺序/编号、清单完整性、示例与计数、章归属表述」，按注册表现状（17 条）整改：

- **requirements.md**：§6.3 补 `fundamental_snapshot` 行（16）并把 `llm_usage` 归位 17；§6.4 小节编号重排为连续 1..18（17 个报告章节 + 成本流水子模块），补 6.4.16 持仓基本面（两条区块字段表，指向 §5.9/§6.12），经理变更块降为「基金业绩分析」章内 h5 子标题
- **how-to-config.md**：表头 15→17、补 `fundamental_snapshot` 行与 `llm_usage`=17；示例 JSON 的已删键（`fund_manager`/`position_relationship`/`fund_concentration`）→ `position_structure`/`fundamental_snapshot`；「19 项默认顺序」「完整 18 项」及示例序号全部按现状改写
- **reports-instruction.md**：类型分组表编号错位（基金业绩 3→4、数据源 14→15、LLM 用量 16→17）、基金深度分析「共 4 个」→2、删除基金评价表重复的「持仓集中度」行、菜单快速索引与「19 个页签/7 组」→「17 个页签/8 组」
- **folders.md**：HTML 模板行 partial 清单换为 `fundamental_snapshot_section.html`（并修正文件数/行数）、目录树删三个已删模块行并补 `test_section_visibility.py` 与新 partial、把 `fundamental_snapshot_sheet.py` 归入财报装配组、统计快照按实测刷新（主程序 280/70,669、测试 372/109,257、用例 7,213、源代码合计 310/82,270、项目文档 138/52,459、用户文档 11/5,159、managements 10/10,040）
- **technical.md**：三处「19 个模块」→17（含注册表约束条目与模块分布行：always×5 / fund_deep×2 / fundamental_snapshot×1 等）、注册表结构示例改用 `position_structure`（含 `data_flag_any`）、基金深度块图与「基金经理变更监控」小节标题改为章内区块、TOC 条目随 §4.19 改题同步
- **test-coverage.md**：按 `scripts/collect-test-coverage.py` 实测刷新模式计数（unit 6900 / standard 5903 / verify 4696 / report 1902 / data 68 / all 7213）、unit 子标记（unit_report 1902 / unit_config 359 / unit_core 1213 / unit_analysis 811 / unit_web 212）与跨类标记（edge 931 / data 68）；报告域测试清单补三个合并章测试文件
- **testplan.md**：§4 新增 P1「报告章节合并」回归行（三个合并章的逐格等价 + OR 可见性 + type/board_flags/装配键守卫 + 两侧一致性 + 经理块门控）
- **用户文档**：README（页签 21→17、分组七→八、「全部 20 项开关」→28）、how-to-use-tui-menu（基金深度分析 3→2 章 + 经理块说明、features.json 开关计数表述）、how-to-use-web-mode（报告增强子模块清单补财务指标、菜单归属 `[S]`）、faq（示例 JSON 与 19→17 项）、datasource / datasource-reliability（数据源用途归属改「持仓基本面章·区块①/②」）、developer-guide（示例键与 17 个模块键）

门禁：四个 `--ci` + `dev-verify`（2748 passed）全绿。

### plan-45 章节整合·批次④ `fundamental_snapshot` + 经理变更并入（plan-45 完成）（2026-09-16）

**目标**：把「财务指标」与「持仓个股财报摘要」两章合并为同页签两区块的新章 `fundamental_snapshot`「持仓基本面」，并把「基金经理变更监控」章并入「基金业绩分析」章末尾区块（注册表条目 19 → 17，零 alias）。**四批全部完成：21 → 17 条**。

**注册表与可见性**
- 删除 `fund_manager` 条目（其内容成为基金业绩章的块）；`financial_report_digest` + `financial_indicator` 两条 → 一条 `fundamental_snapshot`（`type=fundamental_snapshot`、`data_flag=None`、`data_flag_any=("financial_indicator_data","financial_report_digest_data")`、序号 16）；条目总数 17（序号连续 1..17）；`_REPORT_SHEET_NAMES` 同步（新增 `fundamental_snapshot: 持仓基本面`，删除 `fund_manager`/两条旧财报页签名）
- board 层参数合并：两侧 `board_flags` 删除 `"financial_report"`、`"financial_indicator"` → `"fundamental_snapshot"`（`enable_fundamental_snapshot` = 两功能开关任一开启）；`enable_financial_report_digest` 形参链全量删除（`html_writer` / `excel_generator` / `_report_generation` 包装函数与两处调用点）；`html_writer_nav._SECTION_NAV_GROUP_MAP` 同步（删 `fund_manager`，两条旧财报章键 → `fundamental_snapshot: basic`）
- `excel_generator` 的 `data_availability` 保持登记两契约 flag（`data_flag_any` 乐观/悲观口径与 HTML 侧一致）

**Excel / HTML 渲染**
- 新增 `report/fundamental_snapshot_sheet.py::write_fundamental_snapshot_sheet`（区块① 财务指标 19 列 + 区块② 财报摘要 9 列；契约 None = 该功能开关关闭 → 该块整体不写，含小节标题）；删除 `financial_indicator_sheet.py` / `financial_report_sheet.py`（`financial_indicator.py` 装配层与 `financial_report_digest.py` 保持不动）
- `report/fund_performance.py` 吸收经理变更块：`write_fund_performance_sheet(..., manager_data=None)` + `_write_manager_block`（8 列 + 预警着色 + 占位）；删除 `fund_manager_sheet.py`
- 经理数据改在内容阶段组装（`write_content_sheets` 新增 `enable_fund_deep_analysis` 参数，开启时 `detect_manager_changes` 注入），`excel_fund_deep_analysis` 不再单独写经理页签；`excel_module_loader` 装配键改 `write_fundamental_snapshot_sheet`（删除三个旧键）
- HTML：新增 `partials/fundamental_snapshot_section.html`（一章两区块，块级开关 `financial_indicator_data` / `financial_report_digest_data` 非空才渲染该块），删除两个旧 partial；`report_template.html` 删除独立经理章节、内容并入 `sec-fund_performance` 末尾（块门禁 `manager_analysis` 非空 = 基金深度分析开启）
- `data/config/config.json` 的 `report_section_order` 重生成（删除 `fund_manager`，新增 `fundamental_snapshot`=16）

**测试（新增/同步）**
- `test_financial_indicator_sheet.py` + `test_financial_report_sheet.py` → `test_fundamental_snapshot_sheet.py`（区块写入器用例 + 新增合并写入器：两区块小节标题同页签、契约 None 的块级门控两侧、两契约皆 None 仅剩章标题、**内容等价**）
- `test_fund_manager_sheet.py` → `test_fund_performance_manager_block.py`（改调 `_write_manager_block`）；`test_fund_performance.py` 新增经理块门控两例（`manager_data=None` 不渲染经理块且主表照常 / 传入时渲染）
- 章节键断言同步：条目数 19→17、HTML 容器 19→17、导航/目录 14→13、Excel 页签数 15→14（全开）；type 集合 `financial_report`/`financial_indicator` → `fundamental_snapshot`；`fund_deep_analysis` 计数 3→2；配置模板与注册表同序新增一致性用例

**文档同步**：`technical.md`（模块数 20→17、可见性旗标表、`data_flag` 表、§4.19 改为「持仓基本面」、契约叙述的注册表注册点与消费方、功能语义命名表（僵尸条目 `financial_indicator_sheet` → `fundamental_snapshot_sheet` + 新增合并章行）、合并章注）、`requirements.md`（§6.3 表与 §6.4 小节合并重排、§5.9/§6.12 章节合并说明）、`testplan.md`、用户文档 5 份、`folders.md` 目录树、`plan.md`（批次④ 已实施，plan-45 完成）

**实施期自查**：`rf-368` —— board 层参数链比施工单预估更长（实际 5 处调用点），首改即由 `--mode verify` 的 `unexpected keyword argument` 捕获并改净；`technical.md` 语义命名表僵尸条目由 `check-semantic-index` 捕获。

**门禁**：`--mode verify,regression` 4939 passed / 0 failed；`dev-verify` 2748 passed；四个 `--ci` + 版本一致性 + ruff check/format 全绿。

### plan-45 章节整合·批次③ `position_structure` 实施（2026-09-16）

**目标**：把「持仓关系矩阵」与「持仓集中度监控」两章合并为同页签三区块的新章 `position_structure`「持仓结构与集中度」（注册表条目 20 → 19，零 alias）。

**注册表与可见性（多契约 OR）**
- 删除 `position_relationship`/`fund_concentration` 两条，新增 `position_structure`（`type=fund_deep_analysis`、`data_flag=None`、`data_flag_any=("position_relationship_data","concentration_data")`、序号 6），其后序号整体 −1（19 条连续 1..19）；`_REPORT_SHEET_NAMES` 同步；docstring 计数 20 → 19
- `html_writer_nav._SECTION_NAV_GROUP_MAP` → `position_structure: fund_deep`（可见性 OR 复用批次①的 `data_flag_any` 模型）
- **Excel 侧契约 flag 同步登记**（rf-367）：`excel_generator` 按与 HTML 同口径写入 `position_relationship_data`/`concentration_data`——否则 `data_flag_any` 的悲观口径会使页签恒不创建

**Excel / HTML 渲染**
- 新增 `report/position_structure_sheet.py::write_position_structure_sheet`（区块① 持仓重合度矩阵 + 配对明细；区块② 持仓相关性矩阵（下三角 + 配对 + 说明）；区块③ 持仓集中度监控（11 列 + 预警着色）），供数入参 `concentration_data` 新增；删除 `report/position_relationship_sheet.py` 与 `report/fund_concentration_sheet.py`（领域计算 `position_overlap.py`/`fund_concentration.py` 保持不动）
- `excel_fund_deep_analysis` 两处分派合并为 `sheets.get("position_structure")` 一次调用（两契约数据独立组装、各自异常隔离、区块级降级），`excel_module_loader` 装配键改 `write_position_structure_sheet`
- `report_template.html`：两个 `div.section` 合并为 `sec-position_structure`，区块小节标题改 `.block-title`（一、持仓重合度矩阵 / 二、持仓相关性矩阵 / 三、持仓集中度监控）；进入章节先归一 `overlap_matrix`（`or {}`），集中度数据在缺失时按空列表降级
- `data/config/config.json` 的 `report_section_order` 重生成（`position_structure`=6，其余 −1，共 16 项显式列出 + llm_usage 末位）

**测试（新增/同步）**
- `test_correlation_sheet.py` → `test_position_structure_sheet.py`（区块二用例改调 orchestrator；集中度区块用例自 `test_fund_concentration_sheet.py` 迁入并改调 `_write_concentration_block`）；新增 `TestWritePositionStructureSheet`：首行章名 + 三区块小节标题同页签、**内容等价**（各区块行值与独立写入逐一相等）、仅有关系数据/仅有集中度数据两侧的 OR 降级
- `test_section_visibility.py` 增合并章 OR 三例（仅 `position_relationship_data` 就绪可见 / 仅 `concentration_data` 就绪可见 / 两者皆无隐藏）；`test_registry` 放宽「非 always 类型须有 data_flag」为「data_flag 或 data_flag_any」（多契约模型）
- 章节键断言同步：条目数 20→19、HTML 容器/导航/目录 15→14、Excel 页签数 16→15；集成一致性测试镜像补两契约 flag

**文档同步**：`technical.md`（可见性旗标表改三区块 + `data_flag_any` 行、§4.x 章节叙述、缓存表注、合并章注同步为四个合并章、功能语义命名表新增 2 行、基金深度块图）、`requirements.md`（§6.3 表与 §6.4 章节定义合并 + 小节序号 −1）、`testplan.md`、用户文档 5 份（章节表与计数）、`folders.md`（目录树）、`plan.md`（批次③ 已实施）

**实施期自查**：`rf-367` —— 合并章 `data_flag_any` 与 Excel 侧 `data_availability` 未登记的组合会使页签被悲观判定隐藏（integration 两侧一致性测试捕获），已修并补守卫。

**门禁**：`--mode verify,regression` 全绿；四个 `--ci` + 版本一致性 + ruff check/format 全绿。

### plan-45 章节整合·批次② `holdings_detail` 实施（2026-09-16）

**目标**：把「市值核算明细表」与「持仓分类表」两章合并为同页签两区块的新章 `holdings_detail`「持仓明细与分类」（注册表条目 21 → 20，零 alias）。

**注册表与可见性**
- `_REPORT_SECTION_DEFAULT`：删除 `market_value`/`category` 两条，新增 `holdings_detail`（`type=always`、`data_flag=None`、序号 2），其后条目序号整体 −1（20 条连续 1..20）；`_REPORT_SHEET_NAMES` 同步；docstring 计数 21 → 20
- 两侧导航/分组映射同步（`html_writer_nav._SECTION_NAV_GROUP_MAP` → `holdings_detail: basic`）；无需改前端标签字典与 TUI 面板（均按注册表派生）

**Excel / HTML 渲染**
- 新增 `report/holdings_detail_sheet.py::write_holdings_detail_sheet`（区块① 市值明细 15/16 列 + 账户小计 + 总计；区块② 分类汇总 10/12 列 + 分类小计 + 总计），`_weighted_avg_cost` 随之迁移；删除纯章节写入器 `report/market_value_sheet.py`，`report/category.py` 仅保留分类领域函数（`_categorize_holding`/`_tier_label`/`build_category_data_status`/`calc_yield_text`/`_load_dividend_data`）——**领域层不改名不删除**
- `resolve_market_data` 退化为纯数据解析（不再写页签），页签由 `write_content_sheets` 一次调用写入；`excel_module_loader` 装配键 `write_holdings_detail_sheet`（删除 `write_market_value_sheet`/`write_category_sheet`）；`html_writer_display` 反向依赖改指新模块
- `report_template.html`：两个 `div.section` 合并为 `sec-holdings_detail`（含「一、市值核算明细」「二、持仓分类汇总」两个 `.block-title` 区块小节标题，分类区块的资产构成环形图与数据状态脚随区块保留）
- `data/config/config.json` 的 `report_section_order` 重生成（`holdings_detail`=2，其余 −1，共 17 项显式列出 + llm_usage 末位）

**测试（新增/同步）**
- `test_market_value_sheet.py` → `test_holdings_detail_sheet.py`（区块①用例改调 `_write_market_value_block`，分类写入器用例自 `test_category.py` 迁入并改调 `_write_category_block`）；新增 `TestWriteHoldingsDetailSheet`：首行章名/两区块小节标题同页签/**内容等价**（两区块行值与独立写入逐一相等）/返回值契约/流水子列两区块各生效
- 新增正面守卫 `unit/report/test_section_type_flag_consistency.py`：注册表 `type` ↔ 两侧 `board_flags` 键一致、两侧键集合一致、无残留废弃 type、分派层写入器模块键均已装配
- 章节键断言同步：条目数 21→20、HTML 容器/导航/目录 16→15、Excel 页签数 8→7，配置样本与自定义顺序夹具改 `holdings_detail`；`total_value` 等领域字段（100+ 处）**不批量替换**

**文档同步**：`technical.md`（模块数 19→20 两处、架构图与 always 类型清单、成本流水消费方章名、`holdings_detail_sheet` 契约路径、功能语义命名表新增 2 行）、`requirements.md`（§6.3 表与 §6.4 章节定义合并 + 后续小节序号 −1）、`testplan.md`（测试文件名）、`reports-instruction.md`/`how-to-config.md`/`how-to-use-tui-menu.md`/`faq.md`/`README.md`（章节表与计数）、`folders.md`（目录树 + 统计）、`plan.md`（批次② 已实施）

**实施期自查**：`rf-366` —— 施工单 §3.2 把 `config/_validation.py::_KNOWN_PROVIDER_TYPES`（数据源类别 id）误判为注册表章节 `type` 的允许集合，已更正该行并补正面守卫（注册表 type ↔ 两侧 board_flags 一致）。

**门禁**：`--mode dev-verify` 2748 passed / 0 failed；四个 `--ci` + 版本一致性 + ruff 全绿。

### plan-45 设计文档十轮复盘（第 9~10 轮：跨文档同步与自洽终检）—— 十轮完成（2026-09-15）

- **第 9 轮（跨文档同步面）**：审计发现同步面远大于计划所列——`technical.md`（章节名 + **两处陈旧的「报告 19 个模块」** + 「功能语义命名表」需新增三行）、`requirements.md`、`testplan.md`（§4 回归清单）、`folders.md`（**26 处 `financial_indicator` 命中需甄别**：fetcher/analysis 保留 vs report 章节模块改名/删除）、`test-coverage.md`，以及 4 份用户文档（`README.md`/`reports-instruction.md`/`how-to-config.md`/`faq.md`）。**处置**：新增 §6.8「文档同步清单」（管理文档 / 用户文档 / 门禁脚本与索引 / 纪律四类）。
- **第 10 轮（文档自洽与命名索引）**：新增 §6.9「文档自洽终检」——两文档命名表逐字一致、条目数在施工单/守卫表/验收三处一致（21→20→19→17）、「共 N 项」表述三处一致、分层面术语无矛盾、确认十轮整改**未触碰任何生产代码**；并明确 `check-semantic-index.py` 正反向校验要求「先改表再改码」。

### plan-45 设计文档十轮复盘（第 7~8 轮：批次依赖与计数硬伤）（2026-09-15）

- **第 7 轮（批次依赖与可回退性）**：②③④ 共改 7 个文件（注册表 / 两侧可见性 / Excel 三处分派 / 模板 / 配置模板），**无法任意顺序单独回退**；新增 §6.4b「批次依赖与回退矩阵」——依赖链 ①→②→③→④（③④ 均改 `_compute_section_visibility` 与 fund 深度分组，④ 建立在 ③ 之后）、共享文件表、**逆序回退纪律**（④→③→②，每批一次提交）、版本身份（四批同属 0.11.1-dev）。
- **第 8 轮（计数一致性与非目标边界）——修正硬伤**：批次④ 实际含**两处合并**（财报两章合一 + `fund_manager` 并入 `fund_performance`），但 ④-1 未声明删除 `fund_manager` 条目、④-7/验收/§6.6b 仍写「条目数 18」。已修正为 **17**（21→20→19→17），④-1 显式删除 `fund_manager` 条目、④-2 补删除其页签名映射。非目标边界（LLM 条目不合并）经与注册表现状核对一致，予以保留。

### plan-45 设计文档十轮复盘（第 5~6 轮：接缝完整性与守卫）（2026-09-15）

- **第 5 轮（接缝完整性）**：新增 4 处漏登接缝——`excel_module_loader.py` 的模块表键与错误文案、`html_writer_display.py` 对 `market_value_sheet._weighted_avg_cost` 的**反向依赖**（删模块将 ImportError，须迁移保位）、partial 实况（全仓仅 4 个 partial，**只有 M3 需合并 partial**）、`chart_data_builder` 六图键不变但图归属章节变化；`features.py` 两个 `FeatureSwitchDef` 开关名保留。**处置**：接缝地图补 6 行、批次② 补 ②-4b/②-4c、批次④ 修正 partial 步骤、新增 §7.5 风险补充 3 条。
- **第 6 轮（守卫与可验证性）**：7 项既有守卫均在位但**无守卫清单**、**缺合并前基线方法**、「注册表 type 三处严格一致」缺正面自动化守卫。**处置**：新增 §6.6b「守卫清单与基线方法」——既有守卫表（标注每批变化处 21→20→19→18）、每批新增守卫（`test_section_type_flag_consistency`、模块加载器一致性、区块门禁、内容等价）、基线方法（批次② 前存 `docs-stm/tmp/` 快照，不入库；比对落成单测）。

### plan-45 设计文档十轮复盘（第 3~4 轮：测试面与配置面）（2026-09-15）

- **第 3 轮（测试与守卫）**：发现**同名混淆风险**——`market_value`/`category` 在 100+ 测试中属**领域层**（`DetailRow.market_value` 字段、`report/market_value.py` 市值计算、`report/category.py` 分类函数），而施工单原写「删除 `report/category.py`」会破坏领域层。修正：只迁移**纯章节写入器**，领域模块保留；新增 §6.7「领域层 vs 章节层边界」（含缓存类型域 `get_exact_type_map()` 的 `fund_manager_snapshot`/`fund_concentration_snapshot` 不改）；测试同步清单改为区分「章节键断言（逐文件行）」与「领域词（不在范围）」。
- **第 4 轮（配置与校验面）**：`_validation.py` 允许类型集合与 `config_edit.py` 硬编码处已列入 §3.2 下游清单；发现注册表 docstring「共 21 项」与架构约束表「报告 19 个模块」表述陈旧 → 收尾步骤新增「条目数表述同步」；确认 `_config_defaults.py` 的 `report_section_order` 模板随注册表自动派生（无需手改）。

### plan-45 设计文档十轮复盘（第 1~2 轮：命名链与架构约束）（2026-09-15）

- **第 1 轮（命名统一性）**：设计层新增 §3.2「命名统一的下游影响清单」——把注册表 `type` 的语义化、两侧 `board_flags` 映射键、`enable_*` 形参链、`config/_validation.py` 允许类型集合、Web 硬编码面列入同一张表，明确「三处严格一致」纪律；施工单补 ④-1b 步骤。
- **第 2 轮（架构约束符合性）**：核实代码侧接缝——两侧 `board_flags` 与 `_validation.py` 允许集合仍含旧 `type`，Web 面有硬编码；前端标签字典与 TUI 面板已按注册表派生（无需改）。**关键补充**：`enable_financial_report_digest` 形参在章节合并后必须删除（该章不再存在），涉及 `html_writer`/`excel_generator`/`_report_generation` 三处调用链。
- 施工单新增「允许保留的旧名白名单」（契约键 / 功能开关名 / 缓存前缀 / 数据源类别 / 历史记录）与「复盘记录」表。

### plan-45 实施层文档（迭代施工单）落地（2026-09-15）

- 新增 `docs-stm/plan/section-consolidation-iteration.md`（实施层，与设计层 `section-consolidation-design.md` 配套）：**命名统一总表**（旧名→新语义名，旧名全部删除留零 alias；契约层不改名）、**接缝地图**（注册表/页签名表/两侧可见性判定/Excel 分派点行号/HTML 锚点行号/页签写入器/契约写入点）、**批次②③④ 逐条施工步骤**（含命名 grep 检查、测试与文档同步清单）、收尾与门禁、风险与回退。
- `plan.md` 的 plan-45 条目补实施层文档引用并标注批次①已实施。

### 立项：报告章节整合（plan-45，重生成配置模板）（2026-09-15）

- 注册表条目 21 → 17 的四项合并（市值核算明细+持仓分类 / 持仓关系矩阵+持仓集中度 / 财报摘要并入持仓基本面 / 基金经理变更并入基金业绩），**保留吸收方主键**以免迁移 `report_section_order` pin 与开关名；按用户决定**重生成 `config.json` 与配置模板**（不做兼容）。
- **统一语义命名**（用户要求）：合并后一律用新语义名——新条目键 `holdings_detail` / `position_structure` / `fundamental_snapshot`（`fund_performance` 语义未变），页签名、页签写入器模块与函数、HTML 锚点与 partial 文件名同步改名；旧键/旧页签名/旧写入器/旧 partial **全部删除不留 alias**，配置模板与 `config.json` 重生成。**契约层保留各区块自己的契约键**（不造伪契约键）。
- 架构要点：可见性模型最小扩展——注册表可选字段 `data_flag_any`（多契约 OR，未声明时行为不变）；序号/显示名/页签名一律经注册表驱动；区块级门禁沿用「基金业绩分析章内候选比较子表」既有先例。
- 批次①（可见性模型扩展）已完成并提交：注册表字段契约注释 + Excel（`should_create_sheet`）与 HTML（`_compute_section_visibility`）两侧 OR 支持（悲观判定）+ 新增 `test_section_visibility.py` 12 例守卫；既有条目零变更、行为零变化。
- 设计文档 `docs-stm/plan/section-consolidation-design.md`（现状核实 / 四项合并方案 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）；`plan-next` 45 → 46。

### 发布 v0.11.0 及已发布记录归档（2026-09-15）

- **发布**：`0.10.20-dev` → **v0.11.0**（本次跨越未发布的 0.10.20 编号，直接进入 0.11 系列）：`APP_VERSION`/`pyproject.toml`/README/9 份管理文档版本头/新版 changelog 段头全链同步（`check-version-consistency` [OK]）；发布数据文档按 `collect-test-coverage` 实时快照刷新（`test-coverage.md` 子表、`folders.md` 项目统计、`datasource.md` + `datasource-reliability.md` 逐类核对）；发布门禁（P2）`--mode verify,regression` 4,939 通过 / 0 失败 + 四个 `--ci` + ruff 全绿；打标签 `v0.11.0` 并推送。
- **归档（0.11 系列首份）**：`[0.11.0]` 已发布变更记录整体迁入新建的 `docs-stm/archive/v0.11.x/archived_changelog.0.11.x.md`；`plan.md` 的 plan-44 完成态迁入 `docs-stm/archive/v0.11.x/archived_plan.0.11.x.md`（P1 区自此仅保留「无待办项」与归档引用，概述补 v0.11.x 已完成项指向）；`folders.md` 目录树新增 `archive/v0.11.x/` 并刷新归档/项目文档统计；changelog 与 plan 的「归档」段各补一条链接。
- **开发版本**：打 tag 后即切换至 **0.11.1-dev**（`APP_VERSION` 与全部文档版本头），changelog 新增本轮开发段。

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。


## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0（2026-09-15，0.11 系列首份）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

## [0.11.0] - 2026-09-15

### 明确 TUI 菜单 [P] 与 [S] 的分工（2026-09-15）

- **问题**：plan-44 后「报告章节」被拆到两个菜单（基础章节组在 `[P]`，报告章节与增强在 `[S]`），但**没有任何一处说明这两者的边界**——手册只解释了 `[S]` 面板内部三块的区别，用户无从判断某个章节开关该去哪个菜单。
- **补齐**：① `how-to-use-tui-menu.md` 新增「P 与 S 的分工（配置入口边界）」对照表——按**配置归属文件**划分，简记 **`[P]` = 整章组的开关（`config.json` 顶层 `enable_*`）；`[S]` = 能力开关与细粒度开关（`features.json` / `llm_settings.json`）**；② `[P]` 菜单描述明确为「配置基础报告章节组（…5 项）」；③ 两个面板底部互相给出跳转提示（`[P]` 提示「报告章节与增强、LLM 分析章节请在菜单 [S] 配置」；`[S]` 提示「基础报告章节组在菜单 [P] 配置」）。

### how-to-config 补齐功能开关分组计数（20 项/两组 → 28 项/三组）（2026-09-15）

- 修正 plan-44 后遗留的三处陈旧表述：「全部 20 项开关分两组」→ **28 项 / 三组**（⚗实验 4 / 常规 16 / 报告章节与增强 8）；「功能开关的三个入口」段补报告块（TUI 与 Web 均按三块描述）；面板布局注的「两块功能开关」→ 三块，并注明分组顺序取 `GROUP_ORDER`。

### 测试套件冗余审计 + TUI 菜单 [S] 描述修正（2026-09-15）

**测试套件审计**（AST + 收集器双口径，347 个测试文件）：
- 同文件同体冗余 10 对 → **真冗余 1 对**：`test_tiantian` 的 `test_percentile_only_fallback` 与
  `test_excellent_top_10pct` 同体同义 → 改为 `test_rank_takes_precedence_over_percentile`
  （percentile=90 + rank 5/100 → 优秀），既消除同体又**新增「rank/total 优先于 percentile」覆盖**（依
  `tiantian_ranking` 的矛盾时以排名为准语义）
- 恒真断言 1 处：`test_logger` 的 `assert True` → 改为捕获 stderr 断言无 `Logging error`（可观测结果）
- **判定为非冗余（保留）**：跨文件同体 8 组为并行契约（新浪/腾讯各自归一化、各模块缓存后缀开关），
  每条独立可失败；零断言 37 例经抽样为 `self._assert_*` 辅助断言（检测器假阳性）与 rf-365 已判定的
  有意 no-op/no-crash 边界覆盖；空体用例 0、不可收集测试 0、同类重名 0

**TUI 菜单 `[S]` 描述**：原「配置LLM分析章节」不能概括该菜单（面板实为「配置 LLM 报告章节与功能开关」，
含标准 LLM 模块 + 实验性功能 + 常规开关 + 报告章节与增强共 28 项功能开关）→ 描述改为
「配置功能开关（LLM 分析章节 + 实验性/常规/报告章节与增强开关）」；手册 `how-to-start`（菜单速览）与
`how-to-use-tui-menu`（主菜单总览 + 该菜单项小节标题）同步。

### 管理/用户文档结构与内容核对修正（零断链）（2026-09-15）

- 核对 10 份管理文档 + 10 份手册 + README：提取章节骨架、校验全部相对链接（**断链 0**）、扫描陈旧计数并与代码事实对照。
- 代码侧用户可见文案：`[P]` 主菜单描述去掉已迁走的「报告增强子模块」；`README` 页签计数 20 → **21**（与报告模块注册表的条目数一致）并补「财务指标」提及。
- 用户文档：`how-to-use-tui-menu` 的 `S` 面板「三块 → 四块」并移除写死的块内编号（编号随注册表顺序变化，属易漂移内容）；`how-to-config` 新增「## 目录」、`B` 节补指向 `[S]` 报告块、把「与菜单命令的对应关系」移到文末（恢复 A~P 字母序列连续）。
- 管理文档：`requirements` 修掉机械替换留下的「开关 功能开关」重复 3 处、`R-WEB-08` 功能开关面板块数改三块；`folders` 补「## 项目统计」标题并把文档标题改为「目录结构与项目统计」。

### plan-44 技术债清理（残留引用 / 悬空链接 / 硬编码分组）（2026-09-15）

- 审计 plan-44 落地后的 5 类残留，逐项修复：
  1. **残留引用**：16 个源码文件的注释/docstring 中的 `report_submodules.*` 统一改为「功能开关 `name`」；其中 `crisis_annotation` / `tail_risk` / `snapshot_diff` 三个**并不存在**的开关名属笔误（分别由 `build_crisis_annotation(history_data)` 组装与数据契约名），改为真实表述
  2. **悬空链接**：`plan.md` 中指向未创建设计文档的链接改为指向实施记录
  3. **硬编码分组清单**：TUI `S` 面板由硬编码三元组改为 `GROUP_ORDER` 派生（对齐「渠道层不得另写清单」纪律），并新增 Web 覆盖守卫（面板渲染的开关集合须覆盖注册表全部开关）
  4. **清单同步**：Web 测试白名单清单改裸开关名并补齐 `financial_indicator`（此前缺失）
  5. **陈旧文案**：`technical` 语义命名纪律句与 `data_source_matrix` 说明表备注（用户可见）去掉键名写法

### 报告增强子模块并入功能开关注册表（plan-44 完成，不做兼容）（2026-09-15）

- **决定**：按用户要求**不做 config.json 兼容**——注册表成为唯一真源，config.json 重生成，相关程序同步改。
- **注册表**：新增分组 `GROUP_REPORT`「报告章节与增强」+ 8 条声明（`data_quality` / `market_temperature` 默认开，`industry_beta` / `candidate_compare` / `cost_lots` / `valuation_percentile` / `financial_report_digest` / `financial_indicator` 默认关；`affects_report=True`），注册表 20 → **28 项**；`GROUP_LABELS` / `GROUP_ORDER` / 契约注释同步。
- **真源切换**：`_core.py` 8 个 `is_enable_*` 访问器改为 `is_feature_enabled(<flag>)`（`config` 形参保留但不再参与取值）；`_config_defaults.py` 删除 `report_submodules` 段与模板行；重生成 `data/config/config.json`；**把用户原有非默认取值搬入 `data/config/features.json`**（`valuation_percentile` / `financial_report_digest` / `financial_indicator` = true），8 项行为逐项保持。
- **TUI**：`S` 面板新增「报告章节与增强」块（面板三块 → 四块）；顶层 `P` 面板收敛为 5 个基础报告章节（第 6 项改为「报告增强子模块 / LLM 分析章节 — 请在菜单 S 配置」，输入范围 (0-6)）；删除 `P` 子面板 `_cmd_config_report_submodules` 与其清单常量（面板编号漂移类问题随之消失）。
- **Web**：`config_edit_whitelist` 删除 7 条 `report_submodules.*` 与 `submodule` 写原语；surface `submodules` 改由注册表 `GROUP_REPORT` 派生（键为裸开关名、写入走 `save_feature_overrides`）；前端该块改用注册表 labels 与「影响报告」标记（原 `report_submodules.` 前缀移除）。
- **功能性修复**：`report/_report_factor_metrics.py` 的 `industry_beta` 判定原读 `config.report_submodules`（单源切换后会**永远判关**）→ 改读 `is_enable_industry_beta(config)`。
- **测试**：删除旧的 config 驱动用例，新增注册表真源守卫——组内键集合与默认值、访问器 == 注册表默认、运行时覆盖即时生效、config.json 不再携带该段、Web 白名单无旧路径、写报告开关落 features、`S` 面板含报告块、`P` 子面板已移除；dev-verify 2747/0。
- **文档**：`how-to-config`（删旧 8 行表项、功能开关表 20 → 28 项含新增 8 行、面板布局三块 → 四块、菜单索引改 `[S]` 报告块、配置示例移除该段）、`how-to-use-tui-menu`/`how-to-start`/`faq`/`reports-instruction`、`requirements` 配置表、`technical`（Web 写入分派与说明表口径）、`developer-guide`（语义登记正向校验对象改 `GROUP_REPORT`）、`plan.md`（plan-44 完成，`plan-next` 45）。

### 修复：报告增强子模块面板编号漂移（提示范围写死 + 手册编号错乱）（2026-09-15）

- **现象（用户报障）**：按手册「菜单 P → 7」想开「财务指标」，实际开的是第 7 项「持仓个股财报摘要」；且面板提示写死 `输入编号切换 (0-7)` 而清单已 8 项。
- **缺陷一（手册编号漂移）**：`how-to-config` 开关表里 8 项中有 7 项都写着「菜单 P → 6」（历史遗留：早期清单较短时统一写的编号，后续新增项未同步），仅 `market_temperature` 恰好为第 6 项而正确；新加的 `financial_indicator` 又被写成 7（实为 8）。
- **修复**：手册改为**按名称定位**（「菜单 P → 「财务指标」」）——编号随清单增删漂移、名称不漂移，从根上消掉这一类缺陷。
- **缺陷二（面板提示写死）**：报告增强子模块面板的输入提示 `(0-7)` 硬编码，清单已增至 8 项 → 改为由清单长度派生 `(0-{len(SUBMODULES)})`；同时把该面板清单提升为模块级常量 `REPORT_SUBMODULE_ITEMS`（面板、提示范围与守卫测试共用同一处事实来源）。
- **顺带**：可选章节面板第 6 项原枚举「数据质量/行业Beta/候选比较/成本流水/估值分位/市场温度/财报摘要」漏了财务指标且会继续漂移 → 改为不枚举的概述文案。
- **回归护栏**：新增 `test_handlers_config.py::TestReportSubmodulePanelCoversSwitches` 三例——① 面板清单键集合 == `_DEFAULT_CONFIG["report_submodules"]`（新增开关未补面板即报红）；② 该面板提示范围不得写死、须由清单长度派生；③ 手册须对每个面板项给出「菜单 P → 「名称」」定位（编号漂移即报红）。
- **文档**：how-to-config 开关表 8 行改按名称定位。

### 修复：市场温度缺键回落与默认值不一致（转正遗漏）+ 一致性护栏（2026-09-15）

- **缺陷**：市场温度转正只改了 `_DEFAULT_CONFIG`，未同步访问器 `is_enable_market_temperature` 的**缺键回落值**（仍硬编码 false）——`report_submodules` 八项里唯一一处「默认开但缺键判关」的错位。运行时因 `get_config()` 会与默认值做嵌套合并而不显现，但部分 config 传入的路径（面板/编排部分字典）会出现「配置写明默认开、实际判关」。
- **修复**：`is_enable_market_temperature` 缺键与 `report_submodules` 非 dict 时回落 **True**（与 `data_quality` 同口径），docstring 与 debug 日志文案同步。
- **回归护栏**：新增 `test_config.py::TestReportSubmoduleDefaultConsistency`——逐项断言每个 `report_submodules` 开关的「默认值 == 访问器缺键回落」，并要求存在同名访问器；今后任何开关转正若只改默认值就会立刻报红。
- **测试**：既有「缺键回落为关」的断言改为「回落为开」，另补 `report_submodules: {}` 两态。dev-verify 2757/0。

### 市场温度转正（默认开启，无数据静默省略）（2026-09-15）

- **转正口径**：`report_submodules.market_temperature` 由默认关改为**默认开**。判据取本仓库「读侧增强类开关」纪律——开启的代价基本只在读侧：只在既有产物流水线（「投资分析汇总」章）追加一段由**已算出**数据派生的内容，不新增 LLM 调用次数、不写新的持久化文件；**例外与已知代价**照实记录于下。
- **降噪改动（配套）**：不可用时该行**静默省略**——Excel `summary._write_market_temperature` 与 HTML 汇总章同判据改为「不可用即不渲染」（此前写 `--（数据不足，暂不显示）` 占位）。理由：转正后该行对所有用户默认出现，用户未主动要求的功能不应出现降级痕迹；可用性仍由日志与 `market_temperature_data` 契约（`available=False`）披露。
- **已知代价（照实记录）**：① 该行取数走 `fetch_index_history("sh000300", 750)`，通常命中会话缓存/文件缓存（`index_history_*`）→ **0 次额外请求**；但若本次运行未取过沪深300 且文件缓存冷（如 `enable_history=false`）则 **+1 次指数 K 线请求**。② 该数据进入「信号预消化」块（`信号：市场温度…`）→ `_signal_digest_cache_suffix()` 随之变化 → **升级后首次运行 `expert_review` 与 `health_check` 各重生成一次**（一次性 LLM 费用与耗时，属纪律条文说的预期行为）。
- **顺带修复（会话缓存窗口缩水）**：`fetch_index_history` 的会话缓存条目改为 `(days, bars)`，**仅在缓存窗口不小于本次需求时复用**，否则重取——修掉「某调用者先用短窗口取过，后续要长窗口的调用者（如市场温度 750 天）拿到更短序列」的窗口缩水；旧形态（裸列表）视为窗口未知、沿用既有行为。
- **关闭杠杆保留**：菜单 `P → 6` 或 `report_submodules.market_temperature=false` 仍可回到引入前的报告形态。
- **测试**：+5 例 —— 默认值转正与显式关闭杠杆、不可用静默省略（Excel 两态：`available=False` 与 `None` 均不写行）、会话缓存「窗口足够则复用 / 窗口不足则重取」；既有 3 处会话缓存条目形态断言同步为 `(days, bars)`。
- **文档**：how-to-config（配置示例 + 开关表 + 菜单索引三处）、requirements 配置表（`data_quality` 与 `market_temperature` 默认开、其余 6 项默认关）。

### 配置模板对齐：config.json 补 `data_key_file` 与 `datasink` 段（2026-09-15）

- 显式写入 `data_key_file`（通用密钥文件路径，以 provider 名为节）与 `datasink` 段（`enabled` / `plan` / `requests_per_second` / `daily_quota` / `sections` / `max_chars` / `doc_types: []`），并把 `batch.datasink_workers` 设为 **2**（免费档 3 请求/秒；每标的为索引 + 章节清单 + 正文三次请求）。
- `doc_types` 空数组表示**不限文种**、取最新报告期；密钥文件与持仓文件仍为 git 忽略状态，不入库。

### 修复：财报摘要只取到部分标的且只取年报（章节名 404 + 年报优先）（2026-09-15）

- **现象（用户报障）**：开启「持仓个股财报摘要」后，9 只 A 股标的只拿到 2 只（建设银行 601939、华峰测控 688200），其余含持仓的长江电力 600900 与工商银行 601398 均为「未取到财报」；且拿到的都是**年报**，看不到更新的半年报/季报。
- **根因（日志与实测定位）**：
  * **章节名硬编码裸名**：请求 `/documents/{id}?section=管理层讨论与分析` 对多数文档返回 **HTTP 404**（各公司/文种的实际章节名为「第三节管理层讨论与分析」「五、主要会计数据和财务指标」等，服务端 fuzzy 匹配不一致）——我们据此把**整只标的**判为「未取到财报」（日志：`请求 /documents/27483 返回 HTTP 404`）。
  * **年报优先、命中即止**：索引按 `doc_types` 顺序试取（`annual` 在前），只要有年报就永远不会取半年报/季报；实测同一标的（600900）不限文种取回的**最新一期为 2026-06-30 半年报**（`semiannual`），却被年报遮蔽。
  * **限速 429**：免费档 3 请求/秒，而并发取数（默认 3 worker）叠加索引+正文请求触顶（日志：`触发限速（HTTP 429）`），丢失个别标的。
- **修复**：① **跨文种取最新报告期**——索引改为一次取回最近若干篇（不带 `doc_type`）后本地按「报告期 → 披露时间」倒序取最新一篇；`datasink.doc_types` 语义改为**文种白名单**（默认空数组 = 不限文种）；② **章节按实际清单匹配**——恢复 `/documents/{id}/sections` 端点（`providers/datasink.py::fetch_report_sections`，缓存前缀 `report_datasink_sections_` 并入财报索引模块），按 `datasink.sections` **偏好顺序子串匹配**出精确章节名再取正文；**首选项 404 时继续试下一候选**（不再据此判整只失败）；清单不可得时回退偏好名直取。默认偏好扩为「管理层讨论与分析 → 经营情况讨论与分析 → 主要财务数据 → 主要会计数据 → 董事会报告」，使季报自动落到财务数据章节；③ **限速友好**——429 时退避 1s **自动重试一次**；财报取数并发默认 **3 → 2**。
- **测试**：+13 例——最新报告期优先于年报（半年报/一季报排序）、文种白名单过滤与不匹配返回 None、`_pick_sections` 子串匹配/去重保序/回退、按精确章节名请求、首选项 404 落到下一候选、章节清单缓存、`fetch_report_sections` 端点解析与异常形态；既有「年报优先」断言同步改写。
- **文档**：requirements R-FRD-03（取数口径改写）、how-to-config（`doc_types` 空=不限、`sections` 偏好子串匹配、429 退避）、datasource（数据质量说明：取最新报告期跨文种）、technical §4.19（取数链路）。
- **后续可选项**（未做）：失败原因细分（「无索引」vs「章节不可用」）目前仍统一显示「未取到财报」，可从章节解析结果细化。

### 修复：数据源说明表误报「未使用」（财务指标/财报全文取用标记缺失）（2026-09-15）

- **现象（用户报障）**：运行最新程序后「数据源可用性矩阵」章的「数据源说明（实际使用清单）」表仍把 DataSinking 标为 `○ 未使用`。
- **根因一（配置，非缺陷）**：DataSinking 相关能力**均为默认关的 opt-in**——用户 `config.json` 的 `report_submodules` 只有 `data_quality` / `market_temperature` 为真，`financial_report_digest`、`financial_indicator`、`valuation_percentile` 均为关（前两者甚至未出现在该段，走默认关），因此本次运行**根本没有任何代码路径去调用 DataSinking**，`未使用` 属实。
- **根因二（真实缺陷）**：说明表的 `used` 取自 `DegradationTracker` 事件前缀（`report_datasink_`），而**该域的取数链路从未写任何 tracker 事件**（`providers/datasink.py`、`fetcher/financial_report.py` 均无记录点，与 price/fund/index/industry 各自在 fetcher 层记事件的惯例不一致）——即使用户开启开关并成功取数，也永远显示 `未使用`；同时 `financial_indicator` 域（缓存前缀 `fin_indicator_`）**根本没有类别行**，在说明表中完全缺席。
- **修复**：① 新增 `report/data_status.py::mark_data_used(source_key)`——「本次取用」标记，**只记成功事件、不参与降级计数**（章节名 fuzzy 未命中等预期内空结果若按失败计入 T2 阈值会把预期内空结果误报为源故障；失败与降级仍由 provider 日志、章节失败清单、链路诊断披露），自身不抛异常；② `fetcher/financial_report.py` 在索引与正文**取得数据时**（含缓存命中）标记 `report_datasink_index` / `report_datasink_doc`（`_fetch_index` 的缓存命中、provider 命中与 `_fetch_document` 的链路返回三处）；③ `fetcher/financial_indicator.py` 标记 `fin_indicator_{source_api}`（主源 akshare 与解析支路 datasink_indicator 分别标记）；④ `report/data_source_matrix.py` 新增 `financial_indicator` 类别行（`_SOURCE_CATEGORIES` 与说明表清单同源）并补 `财报全文` / `财务指标` 行的「需开启哪些开关才会取用」备注，同时修订 `used` 语义说明（「取得过该类别数据（含缓存命中）；`未使用` ≠ 源故障」）。
- **测试**：+17 例——`mark_data_used`（记成功事件/不推进降级计数/异常不抛）+ 说明表（新类别行与备注、按前缀判定 used、无关类别不受影响）+ 财报域（索引与正文的取用标记、缓存命中亦标记、未取到不标记）+ 指标域（主源标记、解析支路按 `source_api` 标记、链路段标记、无数据不标记）。

### 设计文档归档与计划状态收口（plan-42 / plan-43）（2026-09-15）

- **计划状态**：`plan-43`（持仓个股基本面数据源主备与财务指标提取）由「设计完成，待实施」转为**已完成**（阶段①②③a③b④ + DataSinking 数据底座门禁；阶段⑤ 文档与门禁收尾随发布执行）；`plan.md` 的 P1 / P4 两区自此均为「无待办项」，编号源 `plan-next = 44` 不变。
- **七次归档**：`docs-stm/plan/` 两份已实现设计文档迁入 `docs-stm/archive/v0.10.x/`——`datasink-financial-report-digest/datasink-financial-report-digest-design.md`（plan-42）与 `financial-indicator-source/financial-indicator-source-design.md`（plan-43）；文档头部状态行改为已实现态，文档间交叉引用、`plan.md` 与 changelog 内的设计文档引用一并改指归档路径，`docs-stm/plan/` 再次成为空目录。
- **归档台账**：`archived_plan.0.10.x.md` 头部「归档时间/涵盖版本/归档内容」三行同步（涵盖范围扩至 v0.10.19），新增小节「P1 — 已完成（plan-42 / plan-43 完成态，2026-09-15 七次合并迁入）」并补「归档说明」条目；`folders.md` 目录树与统计（plan/ 归零、归档 127 文件 / 42,147 行）按实测刷新。

### LLM 侧注入：基本面信号与叙事-数字背离检测（plan-43 阶段④）（2026-09-15）

- **五路确定性信号**：在既有 `signal_pre_digest`（默认开、注入专家复盘与持仓体检、**不新增 LLM 调用**）中新增两路——
  * **持仓基本面**：只读 `financial_indicator_data`，把逐只质量档（优/良/弱）与年度趋势（增长/下滑）聚合成分布；两侧**同向才给方向**，矛盾或无判据判中性（不硬造方向），同行给出平均 ROE；
  * **叙事与数字背离**：`financial_report_digest_data`（管理层讨论与分析摘要）按代码与 `financial_indicator_data` 配对，对摘要做**词频语气**判定（乐观/悲观词表，词表集中为模块常量，不做语义理解）× 指标方向（年度趋势优先，其次归母净利/营收同比，±3% 内持平）；仅在「叙事乐观而数字走弱」或反之时产信号，**列出依据但不下结论**（结论留给模型），最多列 3 只。
- **背离要求行按需追加**：块内出现背离项时追加 `（存在「叙事与数字背离」项：请在结论中显式指出背离点，说明你以哪一侧为准及核实方向）`；**无背离项时该行不出现**（提示词与未引入该项时逐字节一致）。
- **门禁联动**：两路新信号依赖 DataSinking 数据底座（`datasink.enabled` + 凭据）；未就绪时对应契约缺席 → 信号自动缺席（不注入即无感）。
- **缓存同源**：信号块内容进 `_signal_digest_cache_suffix()` 指纹——新增信号即换键，避免「提示词带新信号、缓存还是旧内容」的错配；写侧与预检侧无条件调用同一构建器（开关判定仍收敛在该函数内）。未改写 pipeline_data 契约（附录 H 不变）。
- **测试**：+16 例 —— 基本面信号（分布与方向/弱质下滑看空/矛盾判中性/门禁缺席）+ 背离检测（双向命中并列依据/同向与中性与持平皆静默/仅配对标的不单侧判断/上限截断/契约缺席）+ 块与缓存（合流与要求行、无背离不得出现要求行、指纹随信号变化）。
- **状态**：plan-43 阶段①②③a③b④ 全部完成（结构化指标主源 → 全文解析备用支路 → 财务指标报告章 → 真实 PE/PB 分位（TTM）与数据底座门禁 → LLM 侧信号注入与背离检测）；阶段⑤（文档与门禁收尾）随发布执行。

### DataSinking 数据底座门禁（静默回原样，plan-43 门禁）（2026-09-15）

- **新增门禁**：`config.datasink_feature_ready()` —— 配置位 `datasink.enabled`（默认开）**且**凭据就绪；纯本地判定（零网络请求、零延迟），供依赖该数据底座的分析能力前置检查；新增 `config.is_enable_datasink()` 读配置位。
- **覆盖范围**：财务指标章 + 真实历史估值分位（持仓个股财报摘要本已需 key，形态不变）。
- **未就绪即静默回原样**：财务指标章 `build_financial_indicator` **门禁先于任何取数**（零网络开销）并返回 `None` → 章节整体隐藏、**不写占位**；真实分位 `_fetch_valuation_for_code` 不取指标不算分位，`compute_valuation_data` 置 `basis_mode="proxy_only"` → 估值列文案回到 `分位 45%（合理）`、免责语回到原单口径句（Excel 与 HTML 同一判据，抽取 `penetration_sheet.valuation_footer_note` 单一来源）。
- **就绪时**：财务指标章正常装配；真实分位生效为 `basis_mode="real_ttm"`，估值列标注口径（`真实分位 …（…，PE-TTM）` / 无基本面覆盖回落 `价格分位 …（…，代理）`）。
- **测试**：+9 例 —— 门禁判定（配置位缺省/关闭/凭据缺失组合）、门禁先于取数（零调用断言）、装配层与编排层未就绪返回 None、真实分位未就绪不取数且 `basis_mode=proxy_only`、免责语回原样与双口径两态。
- **文档**：requirements R-FIN-13 / R-VAL-04、how-to-config（`datasink.enabled` 与财务指标章开关行）、technical（门禁判据与 `basis_mode` 契约位、语义表 +1 行）。

### 真实历史估值分位（TTM 口径，plan-43 阶段③b）（2026-09-15）

- **口径升级**：把「价格自身分位」升级为「真实估值分位」——历史 PE/PB 序列衡量贵不贵；无基本面覆盖时回落价格代理并标注口径，**两种口径不得混展示**。
- **TTM 每股收益**（`analysis/valuation_percentile.py`）：年报直取当年 EPS；一季报/半年报/三季报按「上年年报 + 本期累计 − 去年同期累计」差分；所需期数不全 → 该期不产 TTM（不猜）。
- **生效日 = 法定披露截止日**（年报/一季报 4-30、半年报 8-31、三季报 10-31；年报为次年）——**避免前视偏差**：某期数据仅在该日之后的历史价格上生效，绝不用未来财报解释过去价格；同日生效（年报与一季报同在 4-30）按报告期新者胜（否则退化为输入顺序，可能取到更旧口径）。
- **序列与分位**：逐交易日取「该日已生效最新一期基本面」→ PE = 收盘价 ÷ TTM EPS（TTM ≤ 0 即亏损不产）、PB = 收盘价 ÷ 该期每股净资产（非正不产）；分位 = 历史值 ≤ 当前值占比，样本 < 60 判数据不足；**PE 优先、PB 兜底**，`basis` 如实标注。
- **接线**：编排层 `_fetch_valuation_for_code` 增取指标序列（取数/计算异常各自收敛降级，不影响估值行）→ `by_code[code].real` + `real_available`；`penetration_sheet._get_valuation_text` 优先真实分位（`真实分位 45%（合理，PE-TTM）`），回落标 `价格分位 …（…，代理）`；Excel 表尾与 HTML 页脚免责语同步为双口径说明。
- **测试**：+28 例 —— 派生层（TTM 差分四类/披露生效日/排序与同日并列/无前视对齐/PB 时点取值/亏损剔除/分位与档位/各类降级）+ 边缘（脏值基本面/非正与不可解析价格/生效日含边界/空序列）+ 接线（真实分位注入 by_code、无基本面回落、取数异常收敛）+ 既有文案断言同步。

### 财务指标报告章（plan-43 阶段③a）（2026-09-15）

- **新增「财务指标」独立章**：持仓 + 穿透 A 股基本面（Excel 页签 + HTML `partials/financial_indicator_section.html` + 导航「基础信息」组），开关 `report_submodules.financial_indicator` 默认关、数据驱动（无数据隐藏/写占位），不改变既有章节输出。
- **取数**：`fetcher/financial_indicator.py` —— 多期序列**主源一次调用**（akshare），主源不可用时**退化为链路单期**（解析支路只能给最新一期，**不伪造历史期**）；缓存前缀 `fin_indicator_hist_` 归入 `fin_indicator` 模块；非 A 股不发请求。现价经 `collect_price_map` 取自行情明细。
- **派生（纯计算层）**：`analysis/financial_indicator.py` —— 质量档（ROE/毛利率/资产负债率/经营现金流对净利覆盖 四维阈值各 0~3 分后均值分档 优/良/中/弱；**缺维度跳过而非按 0 分**、脏值不参与、**非投资建议/非评级**）、年度趋势（仅比较相邻两个**年报**，避免把季报累计值当年度值；±3% 内为持平；两指标方向不一致记「波动」）、当前 PE/PB（亏损或净资产非正留空）、趋势点截取。
- **装配与呈现**：`report/financial_indicator.py::build_financial_indicator`（管线契约 5 键；全部失败时保留失败清单）+ `report/financial_indicator_sheet.py`（金额亿元、比率百分数、缺失写「—」）。
- **接线（与「持仓个股财报摘要」同构）**：config 开关与访问器、章节注册（type=`financial_indicator`、data_flag=`financial_indicator_data`、number 20；llm_usage 顺延 21）、`pipeline_data` 键表/类型表/附录 H、Excel 工厂与写页签、HTML 导航分组与模板 partial、编排层（`prepare_report_data` 与 both 路径各自构建）、TUI 配置菜单（8 项子模块）。
- **测试**：新增 70 例 —— 分析层派生（`test_financial_indicator.py` 26 例）+ 边缘（`test_financial_indicator_edge.py` 20 例，`*_edge.py` 隔离）+ 装配/开关/接线（`test_financial_indicator.py` 报告层 17 例）+ 页签（`test_financial_indicator_sheet.py` 4 例）+ 多期取数层（`test_financial_indicator.py` 取数层 7 例）；同步更新既有断言（注册表 21 项、类型集合、HTML 章节数 21、双端章节一致性夹具、场景全类型集合）。
- **口径声明**：质量档为**启发式通用阈值分档**（不区分行业），PE/PB 为**当前值**；历史 PE/PB 分位（TTM 口径）属阶段③b。

### 财务指标全文解析备用支路（`datasink_indicator`，plan-43 阶段②）（2026-09-15）

- **实测推翻原设计前提**：DataSinking 的 Markdown **不保留表格**（PDF 报表被压平为「标签紧连数字」的整段正文，如 `...营业收入86,241,940,222.2084,491,870,566.52...`），且不存在 `主要会计数据与财务指标` 章节（该名 404）；指标实际在**第二节「公司简介和主要财务指标」**（别名 `主要财务指标` 命中共章），季报为「主要财务数据」。据此**修订设计文档 §5**（新增 §5.0 前提修订）：解析策略由「读表格」改为「锚点 + 前若干数值」，并把解析**收窄到该章节**（报表正文存在附注编号与金额粘连的误读风险，收益低于风险）。
- **纯解析层**：新增 `analysis/financial_indicator_extract.py` —— 锚点表（营收/归母净利/经营现金流/基本每股收益/加权 ROE，含「归属于母公司股东」旧式行文）+ 否定环视排除「扣除非经常性损益后的…」同口径干扰 + 有限取值窗口（超窗判为跨行、弃用）+ 按报告期精度选数值模式（金额两位小数、每股四位、比率两位，避免 `1.41011.3281` 无分隔连写误切）+ 金额单位换算（取锚点前最近「单位：X」，**无声明即不产金额**）+ 逐字段幅度/区间校验；同比由本期/上年**同口径**两值算术派生。报告期/文种一律由元数据给出。
- **解析适配器**：`fetcher/financial_indicator_adapters.py` 新增 `DataSinkIndicatorAdapter`（`datasink_indicator`），**逐章节试取、命中即止**（避免同一章节被多个别名重复取回白耗配额）；取数经既有 `fetcher/financial_report.py` 链（复用其缓存/限速/配额/熔断，**不另建 HTTP 通道**）。
- **链路**：`financial_indicator: [akshare_financial, datasink_indicator]`（主源失败落解析支路）；配置校验放行新源名 `datasink_indicator`。
- **覆盖面（诚实边界）**：解析支路提供营收/归母净利/营收同比/净利同比/经营现金流净额/基本每股收益/ROE 共 7 项；毛利率、资产负债率、每股净资产**不在该章节**，恒为 `None`（由主源 akshare 提供）。
- **实测复核**：新增真实正文夹具 `src/test/data/fixtures/datasink_indicator_section_600900.md`（长江电力 600900.SS 2025 年报该章节全文，附 `README.md` 记来源与核对值），逐字段复现披露值——营收 86,241,940,222.20 元、归母净利 34,502,809,176.39 元、经营现金流 60,562,925,570.41 元、EPS 1.4101 元/股、ROE 15.90%、同比 2.07% / 6.17%。
- **测试**：`test_financial_indicator_extract.py`（真实夹具回归 + 行文变体/单位/精度/扣非排除/降级）+ `test_financial_indicator_extract_edge.py`（窗口边界/异常幅度/越界比率/零基数同比/截断正文，`*_edge.py` 隔离）+ `test_financial_indicator.py` 扩充（链路顺序、落解析支路且源身份为 `datasink_indicator`、逐章节试取、非 A 股不发请求、双源皆失败返回 None）。

### 结构化财务指标数据域（`financial_indicator`，plan-43 阶段①）（2026-09-15）

- **新增数据域与契约**：`financial_indicator` 域 + `FinancialIndicatorFields`（营收/净利/同比/毛利率/ROE/负债率/经营现金流/EPS/每股净资产；金额单位元、比率为小数比例、可选数值缺失取 `None`），登记 `DOMAIN_RECORDS` 并纳入适配器契约自检。
- **主源 provider**：`providers/akshare_financial.py` —— 一次 `stock_financial_abstract` 取回宽表（指标 × 报告期），归一为每报告期一条标准记录；百分数（ROE/毛利率/负债率/同比）换算为小数比例；同名指标多分组按表格顺序首个非空为准；非 A 股/未安装/超时/空表返回空。
- **适配器与链路**：`fetcher/financial_indicator_adapters.py::AkshareFinancialAdapter`（标准字段直出，无需 alias）+ 新链 `financial_indicator: [akshare_financial]`；取数复用 `fetch_with_fallback`（缓存/熔断/降级），缓存前缀 `fin_indicator_`（一月 TTL、基础类）；配置校验放行新数据类型/源名。
- **共享原语收敛（去重）**：A 股→FMP 符号映射统一为 `core/code_utils.py::to_fmp_symbol`（原在 datasink 内，现两个数据源共用）；akshare 取数超时封装统一为 `providers/_utils.py::run_with_timeout`（由 `akshare_extras` 抽出，避免第二份副本）。
- **测试**：新增 `test_akshare_financial.py`（宽表归一/百分数换算/同名指标优先与逐期补齐/文种映射/各类降级，15 例）与 `test_financial_indicator.py`（适配器登记与自检/标准字段集/链注册/链路取回与降级，5 例）；`TestFmpSymbol` 随函数迁移至 `test_code_utils.py`（unit_core）。
- **口径**：本阶段仅数据层（无报告消费）；真实 PE/PB 估值分位、质量因子与 LLM 注入属后续阶段（见 `docs-stm/archive/v0.10.x/financial-indicator-source/financial-indicator-source-design.md` §13）。

### DataSinking 财报接入·数据层（plan-42 阶段①②③）（2026-09-14）

- **凭据**：`CredentialSpec` 扩展 `key_file` / `key_field` / `key_section` / `key_file_setting`，就绪判定支持「环境变量或密钥文件」（环境变量优先）；新增 `credential_value()` 取值接口，就绪矩阵增「来源类型」与密钥文件路径，**值永不回显**。密钥文件通用化：新增顶层路径键 `data_key_file`（默认 `data/config/data_key.json`），文件**以 provider（source_id）为节**（如 `{"datasink": {"api_key": "..."}}`），一个文件容纳多个数据源的 key；纳入绝对化与测试隔离。
- **provider**：新增 `providers/datasink.py` —— DataSinking 全文本财报（`/documents`、`/documents/{id}`、`/documents/{id}/sections`）；A 股 6 位代码 → FMP 符号映射；**计划感知限速**（间隔 = 1/每秒上限，免费 3 请求/秒、付费 31，由 `datasink.plan` / `requests_per_second` 派生）在**每次 HTTP 请求前** `RateLimiter.acquire`（免费档无批量端点、必然逐篇请求，限速必须落在本层）+ **日配额护栏**（`data/state/datasink_quota.json`，免费 8,191 篇/日，超限即停）；401/429/非 200/网络不可达均返回空并按代码级降级（不计传输级熔断）；凭据值不落日志。
- **契约与链路**：新增数据域 `financial_report` 与标准字段记录 `FinancialReportFields`（登记 `DOMAIN_RECORDS`）；新增 `fetcher/report_adapters.py::DataSinkReportAdapter`（上游 `id` → 标准 `doc_id`，契约自检通过），登记 `ADAPTER_MODULES`；新增默认链 `financial_report: ["datasink"]`；缓存注册 `report_datasink_index_`（两周）/ `report_datasink_doc_`（一月）；数据源可用性矩阵新增「财报全文」类别；配置校验已知类型/名称放行 `financial_report` / `datasink`。
- **测试**：新增 `test_datasink.py`（26 例：符号映射/套餐限额派生/凭据缺失跳过/请求前限速与配额护栏/401·429·非 200·非 JSON/取数原语）；`test_datasource_credential.py` 增密钥文件 8 例（就绪/环境变量覆盖/空值与损坏/配置路径覆盖/取值不回显）；适配器自检用例改为断言域覆盖而非写死总数。dev-verify 2602 passed / 0 failed。
- **章节装配（阶段④a）**：新增 `fetcher/financial_report.py`（A 股标的收集含去重与穿透合并；元数据按年报→半年报顺序取最新一篇并缓存；单篇正文经链路 + 财报域适配器归一；摘要按 `datasink.max_chars` 截断）与 `report/financial_report_digest.py`（`financial_report_digest_data` 契约：`available`/`rows`/`failures`/`entry_count`，含文种中文标签与披露日换算；缺凭据/无 A 股标的/全部无覆盖均降级不抛异常）。新增 `datasink` 配置段（plan / requests_per_second / daily_quota / sections / max_chars / doc_types）与 `batch.datasink_workers`。新增测试 14 例。
- **渲染接线（阶段④b）**：注册表新增章节 `financial_report_digest`（type=`financial_report`、data_flag=`financial_report_digest_data`、页签名「持仓个股财报摘要」）；新增开关 `report_submodules.financial_report_digest`（默认关）与 `is_enable_financial_report_digest`；pipeline_data 契台登记（`pipeline_data_builder` 三处 + technical.md 附录 H）；Excel 自动建页签与写盘（`report/financial_report_sheet.py`）、HTML 章节 partial（`partials/financial_report_section.html`）与目录分组；both/full 双路径均按开关注入契约。新增页签测试 3 例；同步更新写死章节数/类型/分组/契约的既有用例（注册表 20 项 + 新 type）。
- **配置与入口补全**：`report_submodules.financial_report_digest` 接入 TUI 菜单 P 子菜单（第 7 项）与 Web 配置面板白名单，用户无需手改 config.json 即可开启；`batch.datasink_workers` 由财报摘要装配层消费（`ThreadPoolExecutor` 并发取数，默认 3，免费档批量上限 ≤3；每秒速率仍由 provider 限速器逐请求兜底）。
- **数据源说明表**：「数据源可用性矩阵」章在健康度表后新增「数据源说明（实际使用清单）」表——逐数据类别列出实际链路（如财报全文=DataSinking）、用途、计费（免费/免费档/付费档，财报全文随 `datasink.plan` 动态展示）与凭据要求（是否需 key + 就绪状态），并标注本次运行是否实际使用（观测到 DegradationTracker 事件即为已使用）。Excel（旧样式页签与数据质量仪表盘两路）与 HTML 同步渲染，`build_data_source_catalog()` 输出契约。
- **状态**：plan-42 全部完成——数据层（①②③）+ 章节装配（④a）+ 渲染接线（④b）+ 文档同步（⑤：requirements §6.12 R-FRD-01~07、technical 附录 H 与 §4.9/§6.7、datasource 两册、how-to-config、folders）。

### 测试用例审计与修复（rf-365）（2026-09-14）

- **审计口径**：333 个测试文件（`src/test/unit|scenario|integration`，`live/` 为 opt-in 排除）AST + 收集器全量扫描，按「无效（名实不符且无断言）/ 死（空体、同类重名、未收集）/ 冗余（AST 完全相同、同类同函数号）/ 目录语义（导入包 vs 目录期望）/ 命名与内容」五维盘点。
- **官方门禁**：`check-test-markers.py --ci` 通过（无漏标、无 `_edge.py` 混放、无失效标记）；无无条件 `skip`；无同类重名；`live/` 未收集属 opt-in 设计而非死用例。
- **修复（rf-365）**：6 例无效用例补真断言（`test_set_write_error_logged` 断言告警内容；`test_llm_api_base::TestLogTokenUsage` 4 例改 `assertLogs/assertNoLogs` 断言输入/输出/缓存命中并补 empty 分支；`test_handlers_cache::TestCmdCleanupCache` 2 例断言委托调用与等待按键；`test_html_report_structure_edge` 断言 2 处导航锚点模板）；删 1 例空体死用例；删 `test_llm_utils::TestLogTokenUsage` 冗余类（与 api_base 重复）；`git mv` 分类测试至 `unit/core/` 并改标 `unit_core`。新增回归守护 `test_test_quality_regression.py`（静态禁止空测试体）。
- **保留（有意）**：18 例「不抛异常/no-op」弱断言测试（如 `SilentProgressReporter` 四个 no-op、空范围 no-crash、live 录制辅助）经逐例审阅为有意边界覆盖，不强制补断言；`unit/core` 与 `unit/cache` 的缓存测试拆分、`unit/analysis/test_bond_yield*` 走 fetcher 网关两处目录语义为历史布局，已记录待后续评估。
- **统计刷新**：`folders.md`（测试代码 364/106,414、测试用例 6,991）与 `test-coverage.md`（bench 回填模式表 + 收集分组：报告生成 1828、核心基础设施 1210、unit_llm 954、unit_scripts 204、跨类 llm 750）同步。

### bench 全量计时与 integration 契约修复（rf-364）（2026-09-14）

- **bench 全量跑**：`test-runner.py --mode bench --update-docs` 依次跑 14 个模式并回填 `test-coverage.md`（模式对应测试量 + 采集环境属性 + 各模式耗时对照，dragonball 采集日期 2026-09-14）。本机各模式耗时（worker=8）：unit ~17s / standard ~18s / scenario ~20s / dev-verify ~27s / verify ~15s / integration ~19s / edge ~14s / all ~26s。
- **暴露并修复真实回归（rf-364）**：bench 的 `all` / `all_no_unit` 报 2 例失败——`test_report_chapter_consistency.py` 的「全开」镜像未带新章节 `financial_report_digest` 的 board/data 参数（Excel 少一页签、HTML 该章节不可见）。该套件为 `integration` 标记、不在 dev-verify 门禁内，故此前未暴露。修复：为 `_excel_visible` / `_html_visible_keys` 与两个 all-enabled 用例补 `financial_report` 开关与 `financial_report_digest_data` 参数，并在「全开」场景显式启用。
- **复跑**：`--mode all` **6982 passed / 0 failed**（含 12 skipped）；`test-coverage.md` 散文字面日期（两处采集说明与示例耗时）同步为 2026-09-14。

### 数据源与统计快照刷新（datasource.md / folders.md / test-coverage.md）（2026-09-14）

- **datasource.md**：DataSinking 行补两级缓存前缀（`report_datasink_index_` 两周 / `report_datasink_doc_` 一月）；新增「财报全文（DataSinking）」路由小节（鉴权/取数/限速配额/仅 A 股符号映射）；数据质量说明与常见问题各增一行。
- **folders.md**：统计表按实测刷新（主程序 276 文件/68,852 行、HTML 模板 5/3,999、测试代码 363/106,356、测试用例 6,994、用户文档 11/5,114、项目文档 133/51,292、代码合计 305/80,340），主程序说明补 5 个新模块；目录树经校已含全部新文件。
- **test-coverage.md**：收集快照同步（功能域与单元分组：数据源 Provider 303 / 数据获取调度 371 / 报告生成 1861 / 核心基础设施 1178 / unit 父标记 6681 / unit_scripts 203；报告测试文件 89），源模块清单补 `datasink` / `financial_report` / `report_adapters` / `financial_report_digest` / `financial_report_sheet`。计数以 `scripts/collect-test-coverage.py` 实时输出为准。

### 过去 96 小时实现审计整改（技术债 + 文档漂移，rf-358~rf-362）（2026-09-14）

- **代码债**：删除 `providers/datasink.py` 的两个新增即死函数（`fetch_report_sections` / `quota_remaining`，仅定义+单测、无生产消费者）；`datasink.sections` 由「列表只取首项」改为**多章节顺序拼接**（逐章节取正文、每节独立缓存、空行分隔）；数据源说明表的前缀改从 `_SOURCE_CATEGORIES` 派生（`_CATEGORY_PREFIXES`）、计费文案改由 provider 新增 `billing_description(plan)` 生成（数字同源 `_PLAN_LIMITS`），消除前缀/套餐数字两处重复。
- **文档漂移**：DataSinking 接入后「全部数据源免费、声明表为空」描述已过时——同步修正 `core/datasource_credential.py` 模块 docstring 与注释、`config/features.py` 开关注释/描述、`core/doctor.py` 与 `core/check_sources.py` 回退文案、`technical.md` §2.7（标题由「实验：默认关」改「常规开关默认开」+ 正文补密钥文件/节名）、`requirements.md` §5.8（R-CRD-01/02/03/06/07 补 `key_file`/`key_field`/`key_section` 与解析顺序）、`how-to-config.md` 两处；对应 3 个测试断言文案同步。
- **用户文档与覆盖**：`README.md`「最多 19 个条件页签」→ 20 并补「财报摘要（可选）」与 DataSinking key 说明；`testplan.md` §4 增财报取数 P1 回归行；`technical.md` 增 §4.19「持仓个股财报摘要」叙述章节。
- **门禁**：dev-verify 全绿；四个 `--ci` 检查 exit 0；ruff check + format 零告警。自审记录 rf-358~rf-362（`rf-next` 363）。
- **任务编号纪律收紧（rf-363）**：`check-code-traces.py` 原先在 `src/test/` 对「回归…」整行与「rf-N 修复」两条予以豁免，使测试注释/docstring 可残留任务编号（共 7 处）。现改为 **任务编号硬禁止且先于整行豁免判定**（`scan_file` 用 `_TASK_ID_RE` 检出 rf-/plan-/R- 编号即报 CODE），删除 `TEST_META_EXCLUDE` 的 `rf-…修复` 条；7 处测试注释/docstring 清理为纯回归语义措辞；检查器测试同步（+2 例硬检出、改写 1 例豁免断言）；CLAUDE.md 补注「测试元描述豁免不适用于任务编号」。

### 修复：QDII 联接穿透被旧缓存遮蔽 — 持仓缓存载荷语义版本（rf-357）（2026-09-14）

- **背景（用户报障）**：另一台机器运行报告仍报 `016055` / `040046` 持仓报告期陈旧（`2023-09-30` / `2022-12-08`）、已按持仓不可用处理、未计入穿透 TOP10。定位于 v0.10.18 的 QDII 联接穿透修复（`d02e32e0`）**只改代码、未让旧缓存失效**：修复前写下的 `fund_hold_*` 条目无 `feeder_target_code`，新代码读到时无法穿透，旧载荷「有持仓 + 早期报告期」直接撞上时效闸门——`hold` TTL 为 7 天，旧条目过期前修复被全程遮蔽（提交当时已注明「需立即见效时 `--clear-cache`」，但该依赖用户手动，属真实缺口）。
- **修复（语义版本 + 读侧准入）**：provider 产出经 `fetcher/fund.py::_stamp_hold_schema` 盖 `hold_schema` 版本字段；读取侧以 `_is_current_hold_payload` 为准入判据，版本不符视为未命中。判据接在**两处**读缓存接缝：① `fetcher/chain.py::fetch_with_fallback` 新增 `cache_validate` 参数（覆盖新鲜命中与过期降级条目，不符即清缓存重取）；② 批量预检回调 `_hold_cache_check`（`execute_with_cache_check` 命中会跳过任务，判据若只挂在链路内则热缓存下失效）。顺带移除 `fetch_fund_holdings_batch` 内冗余的局部 `cache_get`/`get_ttl` 导入（模块顶部已有，局部导入使与 `fetch_with_fallback` 的 `cache_validate` 无法在测试中一致打桩）。
- **效果**：此类「改变载荷含义、不变键结构」的修复从此自失效，不再依赖用户手动清缓存；另一台机器 `git pull` 后首次运行即自动丢弃旧条目并重取。
- **回归测试**：`test_chain.py` 增 3 例（准入判据放行/拒收旧载荷并清缓存重取/拒收旧语义过期降级条目）；`test_fund.py` 增 `TestHoldPayloadSchema` 5 例（盖章、判据准入、旧载荷重取并盖章、当前载荷命中不重取、批量预检拒收旧载荷）。fetcher 两文件 89 passed / 0 failed。
- **文档**：`technical.md` §4.9 补「持仓缓存载荷语义版本」机制、§6.7 语义命名表增 `hold_schema` / `cache_validate` 两行、§8.2 补「缓存载荷语义版本」词条外设计规则；本 changelog 与 `review-findings.md` rf-357。

### 项目级 pi 配置入库（`.pi/settings.json`）（2026-09-14）

- 新增 `.pi/settings.json` 并纳入版本控制，压掉更新日志面板的启动期闪屏：`collapseChangelog: true`（What's New 面板折叠为一行）、`quietStartup: true`（隐藏启动 header）、`tuiMode: "fullscreen"`（viewport 由 pi 自持，避免终端 scrollback 大段重排）、`terminal.clearOnShrink: false`（保留默认；文档标注其可致闪屏）。
- **生效前提**：`.pi/` 属「需信任的项目资源」——首次启动会要求信任该项目，未信任时整份项目设置被忽略（回退全局）；`/settings` 面板切换写的是全局设置，仅本文件为项目级。`--tui-mode` 启动参数优先级最高，会盖掉本设置。
- `folders.md` 目录树同步新增 `.pi/settings.json` 条目。

### 发布后自查整改：多币种换算口径校正 + 脚本约定守护（rf-354 ~ rf-356）（2026-09-13）

- **背景**：发布 v0.10.19 后复盘近 96 小时的实现，发现三处遗留债——一处是 rf-350 明确标记「待用户确认」的能力口径失配，两处是脚本约定只写在文档、无任何校验环节。
- **rf-354 多币种换算口径校正（按实现改写文档与测试，不新增汇率功能）**：`faq.md` 原称「港股通和非 A 股品种的汇率换算由数据源接口自动处理」；`testplan.md` 的 T8 场景列「美元份额币种转换」、T19 场景为「汇率中间价故障」、数据正确性验证表列「多币种转换正确：美元份额 × 汇率中间价 = 人民币市值 ✅」；测试侧 `test_data_integrity.py` 第 4 项与 `TestMultiCurrencyConversion`、`test_market_value.py::TestCurrencyConversion` 亦按汇率换算命名。核对实现：**全仓无任何汇率取数或换算**——`get_currency_by_code` 只做币种分类（5 位纯数字→HKD、QDII/海外基金/美股指数→USD、其余→CNY），`fx_exposure.py` 只按币种汇总市值与占比，`market_value.py` 无汇率分支，QDII/场外基金的净值本身即以人民币计值（相关断言为 100 份 × 2.5 = 250.0），情景分析的「汇率情景」是假设 ±5% 对非人民币占比的估算。处置：四处口径按实现改写（`faq.md` 明确「程序不做汇率换算」并补币种分类规则与港股通换汇成本提示；`testplan.md` T8 删跨境币种换算、T19 改为真实且已覆盖的「场外品种净值日期非 T 日」场景、数据正确性表该行改为「非人民币计价品种市值核算（价格 × 份额，不做汇率折算）」并补 `test_market_value.py` 载体；两个测试类更名为 `TestForeignDenominatedMarketValue`，docstring 改述实现，**断言不变**）。需求 §6.10 只承诺「币种判定 + 市值占比 + 标注 + 注入」，与实现一致，未改。
- **rf-355 `scripts/*.ps1` 行尾归一 + 回归守护**：`cli.ps1`、`launch.ps1` 为 UTF-8 with BOM 但**通体 LF**，与 `.editorconfig` 的 `[*.ps1] end_of_line = crlf` 及 CLAUDE.md 的「BOM + CRLF」约定不符（新写的 `llm.ps1` 反而合规）——两文件行尾归一为 CRLF（BOM 保留）。
- **rf-356 `scripts/*.sh` 可执行位入索引 + 回归守护**：仓库 `core.fileMode = false`，工作区权限不被跟踪，`cli.sh` / `launch.sh` / `llm.sh` 在索引中均为 `100644`——新克隆的仓库里 `./scripts/llm.sh` 报 permission denied，而 CLI 手册 / 开发者指南 / 变更记录均按可执行方式调用（且声称「llm.sh 置可执行位」）。处置：`git update-index --chmod=+x` 将三个 `.sh` 的索引权限置为 `100755`，`llm.sh` 工作区权限由 777 归为 755。
- **回归测试**：新增 `src/test/unit/scripts/test_script_encoding.py`（`unit_scripts` 标记，4 例）——`scripts/*.ps1` 逐文件断言以 BOM 开头且不含裸 LF（无 BOM 时 Windows PowerShell 5.1 按 GBK 误读中文注释而解析崩溃）；`scripts/*.sh` 断言 git 索引权限为 `100755` 且工作区可执行（非 git 工作区 / Windows 自动跳过）。

### 开发版本切换（2026-09-13）

- 发布 v0.10.19 后，按既定流程将 `APP_VERSION` 与全部管理文档版本头切换至 v0.10.20-dev，`check-version-consistency.py` 全链 [OK]。

### 已发布版本变更记录归档（v0.10.19 → archived_changelog）（2026-09-13）

- **归档**：发布 v0.10.19 后，按「已完成即归档」口径将本文件 [0.10.19] 已发布版本变更记录整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（接于 [0.10.18] 之后，保持版本升序）；本文件自此仅保留在开发版本 [0.10.20-dev] 的章节与归档引用。
- **同步**：归档文件头部「涵盖版本」扩至 v0.10.1 ~ v0.10.19、「归档内容」改指开发版本 [0.10.20-dev]；`folders.md` 项目文档/归档统计按实测刷新。
- **口径**：发布版本与开发版本分开存放——已发布版本的完整变更记录只在归档文件，本文件只描述尚未发布的工作。

---

## [0.11.2] - 2026-09-24

### 本轮交付汇总（v0.11.2-dev，2026-09-24）

**范围**：LLM 多链接入扩展（Kimi）→ 两个报告缺陷修复 → 两个景气度框架计划项（plan-47/48）→ 两轮技术债与文档审计。共 11 条详细记录（下方按时间倒序）。

**功能与能力**
- **Kimi 开放平台接入**（主节点，Anthropic 兼容端点）：`llm_key.json`/`llm_providers.json` 链切换、`MODEL_PRICING` 补 `kimi-k2.6`/`kimi-k3`、**Extended Thinking 支持**（budget_tokens 路径 + 默认开思考的显式禁用安全网，模型名单双维度解耦）、手册新增接入示例（含 Kimi Code 订阅 Key 不通用警示）
- **plan-47** 景气度框架②维基金层扩展：基金前十大重仓股 ROE 加权推演（阶段一，`basis` 字段预留全量口径升级位），无直接 ROE 的权益类基金入分，三处标「按框架推演」
- **plan-48** 景气度框架④维场外流动性补齐：场外赎回天数类型默认档（货币/短债 T+1、纯债 T+2、其他 T+3、QDII T+7），配置口径优先、默认档标「非实测」

**缺陷修复**
- 穿透 TOP10 占比字段名不一致（`ratio_pct` 被误读为 `ratio`）导致穿透深度分析误判「占比为 0%」（rf-415），并连带修复缓存指纹对占比变化不敏感
- LLM 用量汇总 Endpoint 主备混用时无法区分主备（rf-416）——改按链优先级排序并标注主/备，HTML/Excel 共用

**技术债与文档治理**
- 48 小时实施技术债 6 项清理（rf-419）：ROE 解析/推演集合判定收敛为唯一事实来源、去未用形参、并发键语义对齐、穿透占比严格读契约并告警、端点解析复用
- `batch.akshare_workers` 配置漏声明修复（rf-420）+ 新增「代码引用 ⊆ 默认值」不变式用例
- 两轮全量文档核对（rf-421 / rf-422）：失效锚点、待处理分区错位、R-PF-09 扩展口径入库、公开入口登记、语义命名表补登 3 个收敛原语

**回归测试**：本轮净增 ~40 例（计价锁定 / thinking 安全网 / 估值推演与默认档 / 配置不变式 / 契约漂移告警）。

**门禁**：dev-verify 3120 passed、六个 `--ci` 脚本、`ruff check` + `ruff format --check` 全绿。

**未完成／待办**：plan-50（cninfo 财报备用链路，已定引入 PDF 解析依赖方案）、plan-49（景气度框架转正，待用户确认样本与口径）、rf-113 / rf-257（浏览器人工验收）、rf-420 遗留项无（已闭环）。

### 文档核对（第三轮）：语义命名表补登 3 项（2026-09-24，rf-422）

**背景**（用户要求核对全部管理/用户文档）：结构层全清白（368+ 条内部链接 0 断链、0 失效锚点、README 手册索引 10 份完整、管理文档互引无悬空、分组配置项均有专节），但**语义命名表漏登本轮收敛出的 3 个原语**。

**变更**（`technical.md` 功能语义命名表）：补登 `roe_by_code_from_rows`（ROE 行解析唯一事实来源）/ `estimated_fund_codes`（推演集合判定唯一事实来源）/ `otc_redemption_days_default`（场外赎回天数类型默认档）——三者均为跨模块共用的收敛原语（内部助手确有入表先例，如 `_normalize_hold_payload`），不入表则「代码标识符 = 文档中文描述」一致性链断开。

**验证**：`check-semantic-index --ci` 正反向校验通过；六个 `--ci` + ruff + dev-verify 全绿。

### plan-50 财报取数第二数据源（巨潮 cninfo 备用链路）（2026-09-24）

**背景**：区块② 财报摘要单一依赖 DataSinking，报告完整性受该源「收录 + 章节解析」质量决定——实测工行 2026 半年报**未被收录**（源侧没有的报告无法用季报替代经营讨论内容）。

**变更**：
- 新增 `providers/cninfo.py`（公开免费无需凭据）：`topSearch` 解析 orgId → `hisAnnouncement` 公告列表 → `static` 站 PDF 下载 + pdfplumber 解析；公告元数据归一为与主源索引**同一形状**；文种归类（半年度先于年度、剔除摘要/英文版）+ 报告期推导；固定 1 秒礼貌限速 + 429 退避重试一次；失败返回空不抛异常
- `fetcher/report_adapters.py`：新增 `CninfoReportAdapter` 作财报域**第二槽**；两源以 `source_hint` **命名空间隔离**（异源 doc_id 互不服务、备源独立缓存键段），缓存/熔断/降级复用 `fetch_with_fallback`
- `fetcher/financial_report.py`：**主源索引为空时**切备源重建索引（候选回溯零改动）；源/元数据随查询透传；新增 `fetcher/report_locate.py`（目录行判定与关键词定位**收敛为单一实现**，全文兜底与备源切片共用）
- `core/registry.py`：登记备源缓存前缀（`report_cninfo_index_` / `report_cninfo_text_` / `report_cninfo_orgid_`）
- 依赖：新增 `pdfplumber`（主依赖；镜像实测最新 0.11.10，取 `>=0.11,<1.0`）；**惰性导入**，缺库时该源解析环节降级为空文本
- 文档：`datasource.md`（源清单/两级缓存/主备接管说明）、`datasource-reliability.md`（可靠度表由「唯一链路」改为主备、新增备源接管小节）、`technical.md`（取数链路 + 语义命名表 4 行）、`folders.md`

**回归测试 +47**：新增 `unit/providers/test_cninfo.py`（20 例：orgId 解析与缓存/文种归类与报告期推导/摘要剔除/列表缓存/PDF 解析接缝与缺库降级/限速与 429 退避/非 JSON 与网络异常分支）+ `unit/fetcher/test_report_backup_source.py`（16 例：适配器登记与契约自检/命名空间双向隔离/备源章节定位与目录行跳过/全文中止降级/主源空→备源接管/**主源可用时备源零调用**/主源缓存键不变）；另既有财报夹具适配新签名（14 例）。

**验证**：财报域相关 91 例全过；全量门禁（dev-verify + 六 `--ci` + ruff）全绿。

### 修复配置漏声明：`batch.akshare_workers` 补入默认值与文档（2026-09-24，rf-420）

**背景**（文档审计中发现）：`report/financial_indicator.py`（财务指标章多期取数）与 `report/fund_roe_estimate.py`（景气度框架②维基金重仓 ROE 推演）均调 `get_batch_worker_count("akshare_workers", 2)`，但 `_config_defaults.py` 的 `batch` 段未声明该键（模板与 `how-to-config.md` 字段表也无）——用户无法通过配置调整 akshare 财务指标取数并发，只能吃代码兜底值 2。

**变更**：
- `config/_config_defaults.py`：`batch` 段新增 `akshare_workers: 2`（注释标明服务对象：财务指标章 + 基金重仓 ROE 推演）+ 模板生成同步（尾项逗号重排）
- `how-to-config.md`：`batch` 字段表与两处示例 JSON 补齐（连带补上原本也漏列的 `batch.datasink_workers`，字段表现含 5 键）
- `test_config.py`：新增不变式用例 `TestBatchWorkerKeysDeclared`——扫描 `src/python` 下全部 `get_batch_worker_count("<key>")` 引用并断言 ⊆ `_DEFAULT_CONFIG["batch"]`，堵住「代码引用但未声明」这一类漏洞（既有模板用例只覆盖「模板 ≡ 默认值」）；含防正则失效的断言，已实证移除该键即报错

**验证**：`pytest src/test/unit/config/test_config.py` → 89 passed；全量门禁（dev-verify + 6 个 `--ci` + ruff）全绿。

### 全量文档审计与 5 处组织/内容修正（2026-09-24，rf-421）

**背景**（用户要求）：对 10 份管理文档 + 11 份用户手册 + README 做组织顺序与内容核对。

**修正 5 处**：
- `manuals/faq.md`：为「as-if 与 What-if 区别」问答加显式 `<a id>`（问答为粗体行非标题，原锚点不可达）——修复 `reports-instruction.md` 的失效跳转
- `review-findings.md`：`rf-420`（待处理）从「已解决待归档」表移入新建待处理分区「P2C — 文档与配置口径」（分区纪律纠正）
- `requirements.md`：§5.11 新增 R-PF-09——两项扩展（②维基金层 ROE 重仓加权推演 / ④维场外赎回类型默认档）必标口径，不得冒充披露/实测
- `llm-technical.md`：§5.3 补登公开入口 `resolve_provider_endpoint`（外部模块应复用，不得重写凭据→端点遍历）
- `how-to-config.md`：景气度框架开关描述补「推演/默认档」上屏标识说明

**审计方法**：自建锚点/链接校验（GitHub slug 算法 + 显式 `<a id>` 识别，覆盖 368 条内部链接）+ 目录/索引对照 + 旧口径残留搜索 + 与本轮实现逐项比对。**清白项**：0 断链（修正后）、README 手册索引 10 份完整、标题层级正常。

**验证**：锚点校验剩余失效 0；六个 `--ci` 脚本 + ruff 全绿。

### 过去 48 小时实施技术债清理（2026-09-24，rf-419）

**背景**（用户要求）：对最近 48 小时提交（Kimi 接入 / 穿透占比修复 / Endpoint 主备 / plan-47 / plan-48）做技术债审计，逐 diff 核查后确认 6 项并修复。

**变更**：
- `analysis/prosperity_scoring.py`：新增 `roe_by_code_from_rows`（ROE 行解析唯一事实来源，三处复用：`_score_roe` / 直接 ROE 集合 / 编排层 `known_roe`）与 `estimated_fund_codes`（推演集合判定唯一事实来源，评分侧与标注侧共用）；抽出 `_is_scored_otc` / `_is_otc_default_tier` 助手替代长内联布尔式
- `report/fund_roe_estimate.py`：删除无外部调用方的 `dispatcher` 形参（公开函数与私有批取助手各一处）；股票 ROE 并发改用 `batch.akshare_workers`（与财务指标章同口径，原 `fund_workers` 为语义错配）
- `llm/prompts_action.py` / `llm/fingerprint.py`：穿透占比严格读契约字段 `ratio_pct`，不再兼容遗留 `ratio`；提示词侧缺失时按 0 上屏并**记一次契约漂移告警**（消除「静默归零」——与 rf-415 同型风险）
- `llm/api.py`：新增公开入口 `resolve_provider_endpoint`（链条目 → endpoint 解析唯一入口），`report/llm_module_info.py` 的端点优先级映射改为复用，不再重写 `credentials_ref → endpoint` 遍历
- `technical.md`：§4.20 数据流补首次取数成本与缓存口径说明

**回归测试 +4**（净增）：`test_prosperity_framework.py::TestRoeHelperPrimitives`（ROE 解析过滤非法值 / 推演集合排除直接 ROE）、`test_llm_prompt_builders.py`（契约漂移告警 + 占比按 0 上屏）、`test_fingerprint.py`（遗留 `ratio` 键不再被兼容），另有 2 处旧夹具按生产契约键更正。

**验证**：受影响套件 226 passed；全量门禁（dev-verify + 6 个 `--ci` + ruff）全绿。

### plan-48 景气度框架④维场外流动性补齐（类型默认档）（2026-09-23）

**背景**：④ 流动性此前只算场内变现天数——场外品种未配置 `redemption_limits` 时一律标「需手动确认赎回上限」不计分（用户组合 4 只场外 + 6 只数据缺失），场外为主的组合该维无区分度。

**变更**：
- `core/code_utils.py`：新增 `otc_redemption_days_default`（走类型判定中心化，满足约束「类型分级须走 code_utils」）与四档常量——货币/短债 T+1、纯债 T+2、其他场外基金（主动权益/混合/指数/联接）T+3、QDII T+7（保守上沿）；无法识别返回 None
- `analysis/liquidity.py`：场外未配置赎回上限时改落类型默认档，输出新增 `estimate_basis="type_default"` 与标签「约 T+N 日赎回（类型默认档，非实测）」；配置口径优先，类型未识别才保留「需手动确认赎回上限」降级
- `analysis/prosperity_scoring._score_liquidity`：计分池扩为「场内 + 场外配置赎回上限（用户口径）+ 场外类型默认档（非实测）」，最差天数统一分档；默认档参与时 status=partial 且证据明标非实测；配置/默认档/未计入三类计数分列证据
- 文档：`technical.md`（§4.20 ④维口径）、`requirements.md`（R-LIQ-03 按实现更新）、`how-to-config.md`（字段表 + J 节）、`faq.md`（流动性问答）

**回归测试 +13**：`test_code_utils.py::TestOtcRedemptionDaysDefault`（6 例：货币/短债先于纯债/纯债/QDII/通用场外/未识别返回 None）、`test_liquidity_otc.py`（新增 `TestLiquidityOtcTypeDefaultTier` 4 例 + 既有 3 例改按新行为断言）、`test_liquidity.py` 与 `test_liquidity_otc_edge.py` 旧行为断言更新、`test_prosperity_framework.py::TestLiquidityDimension`（+3 例：默认档计入并标非实测/配置口径计入/无天数仍不计分）。

**验证**：`pytest src/test/unit/analysis src/test/unit/core/test_code_utils*.py src/test/unit/report/test_prosperity_framework_wiring.py src/test/scenario/basic/test_scenario_prosperity_framework.py` → 1011 passed。

### plan-47 基金重仓股 ROE 加权（景气度框架②维基金层扩展，阶段一）（2026-09-23）

**背景**：② ROE 低位弹性此前只覆盖 A 股直接持仓，基金/ETF/QDII 无个股 ROE 只能标「需核实」不计分（用户组合实测仅 ~22% 权重被覆盖）。按用户确认的两阶段方案，本项交付阶段一（前十大重仓口径）；阶段二（全量持仓）待 plan-51 阶段 3 收尾后升级，契约以 `basis` 字段区分口径。

**变更**：
- 新增 `report/fund_roe_estimate.py`：`estimate_fund_roe_batch`（基金持仓批量取数复用 `fetch_fund_holdings_batch`、个股 ROE 复用 `fetch_latest_indicator` 链路含缓存/降级，不新增 HTTP 通道；报告期陈旧闸门与穿透层同口径）+ `weighted_roe` 纯计算；`known_roe` 命中免取数
- `analysis/prosperity_scoring._score_roe`：新增可选入参 `fund_roe_estimates`，无直接 ROE 的权益类基金以推演值计分；证据/持仓视角备注/契约 notes 三处标「按框架推演」（红线②）；直接 ROE 优先不被覆盖
- `analysis/prosperity_framework.build_prosperity_framework_data`：新增 `fund_roe_estimates` 关键字入参与持仓视角推演标注（`_holdings_view` 增 `estimated_codes`）
- `report/_report_aux_metrics.compute_prosperity_framework_data`：编排层按 `classify_penetration` 预筛权益类基金后估算，失败降级为 None（②维退回个股口径）
- 文档：`technical.md`（§4.20 维度表与数据流 + 附录 H 契约 + 语义命名表新增 `estimate_fund_roe_batch`/`fund_roe_estimates`）、`folders.md` 目录树

**回归测试 +14**：`unit/report/test_fund_roe_estimate.py`（11 例：加权纯计算 3 + 编排 8——正常估算/known_roe 免取数/陈旧闸门/持仓缺失/非 A 股过滤/无效占比过滤/ROE 全缺不臆造/空清单）+ `test_prosperity_framework.py::TestRoeDimension` +3 例（推演值补上基金 ROE 且三处标注推演/直接 ROE 不被覆盖/无推演值仍按缺失降级）。

**验证**：景气度相关 91 用例全过；`ruff check` + `ruff format` 干净。

### Kimi Extended Thinking 支持 + Kimi 文档全链同步（2026-09-23，rf-417 / rf-418）

**背景**（文档审计暴露）：接入 Kimi 后审计发现两层缺口——① thinking 模型名单未覆盖 Kimi：`_THINKING_SUPPORTED_PREFIXES` 无 `kimi-` 前缀，配置开启 thinking 的模块走 Kimi 时静默降级；且 Kimi K2.6 Anthropic 兼容端点**默认开思考**（实测不传参即返回 thinking 块），而「未开启时显式禁用」安全网只看 DeepSeek effort 族名单，Kimi 不在其中——关闭 thinking 的模块会白烧思考 token，极端时占满 max_tokens 无正文；② Kimi 定价/接入文档未随计价代码同步。

**变更**：
- `llm/api_base.py`：把「控制方式」（budget_tokens/effort）与「默认行为」（默认开/关思考）两个维度拆开——新增 `_THINKING_DEFAULT_ON_PREFIXES`（独立于 effort 名单显式声明）+ `_is_default_thinking_on()`；`_THINKING_SUPPORTED_PREFIXES` 加 `kimi-`
- `llm/api.py`：禁用安全网改按 default-on 判定（Kimi 开启时走 budget_tokens 路径，不进 effort 族）
- Kimi 端点三态实测验证：默认（thinking 块）/ 显式 `disabled`（HTTP 200 纯正文）/ `enabled+budget_tokens`（HTTP 200 生效）
- 文档同步五处：`llm-technical.md` 附录 B 定价表 + thinking 注入流程图（补默认开思考禁用分支与 Kimi budget 归属）、`how-to-config-llm.md` 定价表 + thinking 支持矩阵 + 新增 Kimi 接入示例（含与 Kimi Code 订阅 Key 不通用的警示）、`faq.md`/`README.md` 支持列表

**回归测试 +7**：`test_llm_utils.py`（kimi 支持判定 / kimi 非 effort / 新增 `TestIsDefaultThinkingOn` 三例）、`test_llm_api.py`（payload 级：kimi 开启注入 budget_tokens 且不发 effort / 未开启显式 disabled）、`test_llm_api_base.py`（支持名单/effort 名单 kimi 断言）。

**验证**：`pytest test_llm_utils.py test_llm_api.py test_llm_api_base.py` → 189 passed；`ruff check` + `ruff format --check` 零告警。

### LLM 用量汇总 Endpoint 主备混用标注（2026-09-23，rf-416）

**背景**（用户反馈）：切换 Kimi 为主节点后，报告「LLM API 用量」汇总的 Endpoint 仍显示 DeepSeek 端点，疑似配置未生效。排查确认配置已生效（模型列表含 kimi-k2.6），但缓存模块保留了切换前 DeepSeek 时代的调用元数据，而汇总行只显示**第一个**有值模块的端点——主备混用时无法看出谁是主。

**变更**：
- `report/llm_module_info.py`：新增 `build_llm_endpoint_display`——多端点时按 provider 链 priority 升序、主在前并标注（`https://主端点（主） / https://备端点（备）`）；端点无法映射链路时保持模块出现顺序且不标注（防误标）；`llm_config=None` 时惰性加载全局配置
- `html_renderers.py` / `excel_llm_usage.py`：两处 `next(...)` 取首端点改为复用该函数（HTML/Excel 口径一致）
- `reports-instruction.md`：用量页签 Endpoint 字段说明同步主备标注行为

**回归测试 +7**（新增 `unit/report/test_llm_module_info.py`）：空/单端点原样、主备标注、模块乱序仍主在前、未映射不标注、惰性加载不崩、重复端点去重。

**验证**：`pytest test_llm_module_info.py test_html_writer.py test_llm_session_usage.py` → 122 passed；`ruff check` + `ruff format --check` 零告警。

### 修复穿透 TOP10 占比字段名不一致导致穿透深度分析误判「占比为 0%」（2026-09-23，rf-415）

**背景**（用户报告）：报告中「资产穿透 TOP10」表格数据正常，但「穿透深度分析」章节的 LLM 文本称穿透占比为 0%。

**根因**：`report/penetration.py::_build_penetration_result` 的 top10 产出字段为 `ratio_pct`，而两处消费方误读 `ratio`（`.get("ratio", 0)` 恒为 0）：
- `llm/prompts_action.py::_build_penetration_deep_prompt`——提示词中每条穿透资产「占比0.0%」，LLM 忠实复述为穿透占比 0%（用户可见症状）
- `llm/fingerprint.py::extract_stable_penetration`——full 模式指纹的占比分量恒为 0，缓存指纹对穿透占比变化不敏感（隐性缺陷）

Excel 穿透页签与景气度评分读 `ratio_pct`，不受影响。既有测试夹具恰好也传 `ratio` 键，形成自证掩盖。

**修复**：两处改为 `a.get("ratio_pct", a.get("ratio", 0))`（契约字段优先，`ratio` 作兼容兜底）。

**回归测试 +2**（净增）：`test_llm_prompt_builders.py` 穿透明细用例夹具改为生产形状 `ratio_pct` 并断言「占比25.0%」（对修复前代码必失败）；`test_fingerprint.py` 新增 2 例——full 模式按 `ratio_pct` 提取契约 / 占比变化必须改变提取结果。

**验证**：`pytest test_llm_prompt_builders.py test_fingerprint.py` → 54 passed；`ruff check` + `ruff format --check` 零告警。

### 接入 Kimi（月之暗面）开放平台为 LLM 主节点，下架 Gemini（2026-09-23）

**背景**（部署调整）：本机部署的 LLM provider 链从「DeepSeek 主 + Gemini 辅」切换为「Kimi K2.6 主 + DeepSeek 备」，不再使用 Gemini。Kimi 走开放平台按量付费 + Anthropic 兼容端点（与 DeepSeek 主节点同一套调用路径），代码零改动即可接入；仅计价表需补充新模型费率。

**变更**：
- `core/constants.py`：`MODEL_PRICING` 新增 `kimi-k2.6`（输入 ¥6.5 / 输出 ¥27.0 / 缓存命中 ¥1.10 每百万 token）与 `kimi-k3`（¥20.0 / ¥100.0 / ¥2.00）官方费率，无峰谷子段
- `data/config/llm_providers.json`（本机部署配置）：`kimi-main`（priority 10，主）→ `deepseek-main`（priority 20，备）；移除 `gemini-fallback`
- `data/config/llm_key.json`（gitignore 不入库）：新增 `kimi-main` 凭据（endpoint `https://api.moonshot.cn/anthropic/v1/messages`），移除 `gemini-fb`
- Gemini 的 `MODEL_PRICING` 条目保留——历史报告成本渲染仍依赖其为旧调用记录估价
- 文档同步：`test-coverage.md`（unit_llm 计数与覆盖描述）、`folders.md`（统计表）

**回归测试 +3**（`test_llm_utils.py::TestPricing`）：Kimi k2.6/k3 单价锁定（1M 输入 + 1M 输出金额断言）/ 缓存命中价锁定（防止缺 `input_cache_hit` 字段回落为 input 价）/ 无峰谷加成（高峰钟点与闲时同价，与 DeepSeek 行为区分）。

**验证**：`pytest src/test/unit/llm/test_llm_utils.py::TestPricing` → 31 passed；`get_llm_config()` 链解析 `kimi-main → deepseek-main` 凭据全部可解析零告警；Kimi 端点实测 HTTP 200（`kimi-k2.6` 正常返回，thinking 模式可用）；费用估算冒烟（10 万输入 + 1.5 万输出 → ¥1.055）。

### 新增 Jev 新闻关联判定评测方案与接入设计草案（2026-09-22，plan-55）

**背景**（能力评估）：TypeSafe 发布 System One 评估模型 Jev——与语言模型不同，它不生成文本，而是接收 `state` + 类型化问项（是否概率 / 单选带分布 / 档位打分）并回结构化答案与校准置信度。经查证，其四条对外路由均无对话补全兼容面，故**不可作为对话模型接入**，仅适用于「窄判断」场景；本项目的新闻关联判定正是此类场景。

**预检结论**（回收 `data/cache/` 中 48 条既有判定得出）：
- `relevance` 已饱和——**77% 标「高」、0% 标「无关」**，无法区分对照方案；`sentiment` 才有区分度（利好 48% / 中性 40% / 利空 12%）
- 「无关」占比 0% → 关键词预筛已承担相关性闸门，**「先用判定预筛、再削减生成侧输入」的动机被证伪**
- 理由文本中位 **23 字**且全为「主体 + 方向」型 → 可由确定性模板渲染，无须为它保留生成调用

**变更**（仅文档与计划，无运行时行为改动）：
- 新增 `docs-stm/plan/jev-news-correlation-evaluation.md`——三方对照评测方案（关键词确定性 / 现网生成 / Jev），含语料构造（现场快照冻结；既有缓存因单向指纹无法回收原文）、盲标协议、指标（主指标取 `sentiment`，含 Brier 与期望校准误差）、预注册判定阈值、脚本落点与复现步骤
- 新增 `docs-stm/plan/jev-news-correlation-design.md`——接入设计草案：独立于对话链的类型化判定通道、问项版本参与缓存指纹、类型化通道下五个无意义配置键不读取、失败降级矩阵、模板理由渲染
- `plan.md` 登记 `plan-55`（含三条预检约束与五条红线），`plan-next` 递增至 56
- `folders.md` 同步目录树与统计表

**未决**：评测本身尚未开跑，前置为 Jev 凭据（直连为 waitlist，可经聚合网关复用既有凭据）与 40~60 条人工标注金标准。未达预注册阈值则归档为「已评估未采纳」。

**口径确认**：`docs-stm/plan/` 的在办设计文档为**扁平文件**（目录树统计以 `glob` 而非 `rglob` 口径核对），完成后才移入归档的主题子目录。

**验证**：`check-doc-drift` / `check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-test-redundancy` 六个 `--ci` 脚本全 [OK]；`ruff check` + `ruff format --check` 全绿。

### 跟进 DeepSeek 计费规则调整：法定节假日全天闲时 + V4 Pro 继续服务（2026-09-20）

**背景**（外部规则变化）：DeepSeek 官方 2026-09-10 定价页更新峰谷计价口径——高峰时段为北京时间周一至周五（**不含中国法定节假日**）9:00–12:00、14:00–18:00；其余时段（含周末与**法定节假日全天**）均为空闲时段。同批 change log 还宣布 V4 Pro 在 2026-09-14 之后**继续提供 API 服务**（此前曾计划下线）。项目原先只实现了「周末全天闲时」，且注释误记 V4 Pro 下线。

**变更**：
- `core/constants.py`：新增 `PRICING_HOLIDAY_ALWAYS_IDLE`（默认 True）；峰谷时段注释更新为「高峰日 = 周一至周五且非法定节假日」；更正 V4 Pro 注释为继续服务、计费不变
- `llm/pricing.py`：新增 `_is_holiday`（复用 `core/trading_calendar._is_trading_day` 判定工作日但非 A 股交易日）、`_is_idle_day`（周末/法定节假日，各受 `weekend_always_idle` / `holiday_always_idle` 开关控制）；`_is_peak_minute` 参数由 `weekend` 改为 `idle_day`；`reload_pricing` 增加 `holiday_always_idle` 解析
- `config/_llm_settings_defaults.py`：pricing 段新增 `holiday_always_idle: true` 及注释
- 文档同步：`llm-technical.md`（§10.4 峰谷定价 + 附录 B 定价表与说明）、`how-to-config-llm.md`（pricing 字段说明 + DeepSeek 注意事项 + 峰谷定价说明 + 费用估算示例）

**回归测试 +5**（`test_llm_utils.py::TestPricing`）：法定节假日闲时默认开 / 高峰钟点按闲时价 / 缓存命中按闲时价 / 普通工作日（交易日）仍按高峰价 / `holiday_always_idle=false` 恢复峰谷——法定节假日判定 mock `trading_calendar._is_trading_day`，不触发真实网络。

**验证**：`.venv/bin/python -m pytest src/test/unit/llm/test_llm_utils.py::TestPricing` → 28 passed / 0 failed；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-doc-drift` / `check-test-redundancy` 六个 `--ci` 脚本全 [OK]；`ruff check` + `ruff format --check` 全绿。

### 修复 LLM thinking 预算兜底方向写反（2026-09-20，rf-379）

**背景（自审待核类问题，已解决）**：`_resolve_thinking_budget` 的兜底方向存疑——旧实现把「budget 不足 `max_tokens + 1024`」视为不足并**提升到 `max_tokens + 4096`**，导致实际发送 `budget_tokens > max_tokens`。本次查证 Anthropic / Gemini 官方约束后确认方向写反。

**官方约束**：
- **Anthropic**：`budget_tokens` 须 **< `max_tokens`**（思考 token 计入 max_tokens 共享预算，须为最终回答留空间），且最小值 1024（仅 interleaved thinking 可例外，本项目不用）。
- **Gemini**：`thinkingBudget` 为软上限，但 `maxOutputTokens`（= max_tokens）是硬截止，思考 token 计入；若 `thinkingBudget ≥ maxOutputTokens`，推理时触发 `finish_reason=MAX_TOKENS` 且正文为空。
- **DeepSeek（主用）**：走 `reasoning_effort` effort 档（`deepseek-flash` / `deepseek-v4-` / `deepseek-chat` 命中 `_THINKING_EFFORT_MODEL_PREFIXES`），**不发送 budget_tokens**，故本缺陷不影响 DeepSeek 主路径。

**变更**：
- `src/python/llm/api.py::_resolve_thinking_budget`：兜底条件由 `budget < max_tokens + 1024` 改为 `budget ≥ max_tokens`（含缺失），兜底值由 `max_tokens + 4096` 改为 `max(1024, max_tokens − 2048)`（保证 ≥1024 且 ≤ max_tokens − 2048，正文留 2048 余量）
- 同步 `docs-stm/manuals/how-to-config-llm.md`（参数表 + 「thinking_budget 与 max_tokens 的关系」章节）与 `docs-stm/managements/llm-technical.md`（Claude/Gemini 两处注入流程）
- 回归测试 +5：`test_llm_api.py` Claude 3 例（兜底 1024 / ≥max_tokens 回落 / 合法值保留）+ Gemini 2 例（≥max_tokens 回落 / 合法值保留）

**验证**：`.venv/bin/python -m pytest src/test/unit/llm/test_llm_api.py` → 32 passed / 0 failed。

### 补充 rf-113 / rf-257 浏览器人工验收清单（2026-09-20）

**背景**：rf-113（Chart.js 图表浏览器验证）与 rf-257（Web 模式浏览器验收）是两项**只能真实浏览器/真机人工走查**的遗留待办（均无法用自动化脚本替代）。rf-113 已有旧清单但存在与当前实现的偏差；rf-257 长期只有模糊的「对照 plan-web-ui.md 验收标准」而无落地勾选清单。本次补齐二者载体并勘误。

**变更**：
- **rf-257 新增勾选清单**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`——从实际 `index.html` 七卡结构（①上传 ②生成 ③配置编辑 ④进度 ⑤结果 ⑥运行状态 ⑦日志）+ `how-to-use-web-mode.md` 手册 + `plan-web-ui-implementation.md` §10/§6.5/§6.6 验收标准导出 ①~⑤ 五类 UX 项（页面渲染 / 上传表单 / 进度可视化 / 375px 响应式 / 按钮态），每项含可勾选细项 + 逐步操作步骤 + 明确判定标准；`review-findings.md` rf-257 条目补指向该清单的引用，验收标准源由笼统的 `plan-web-ui.md` 修正为 `plan-web-ui-implementation.md`
- **rf-113 清单勘误**：`iter7-verification-checklist.md` 的 5 处场景参数名错误——`test-chart.html?场景=ok` / `?场景=离线` 修正为 `?s=ok` / `?s=offline`。根因：`test-chart.html` 的 `getScenario()` 只读 `?s=` 参数（合法值 ok/degraded/empty/offline），中文字参数不报错但实际无效（非法值 fallback 到 ok），其中 `?场景=离线` 会让用户验证不到离线守卫逻辑，属必须修复的误导

**其余核对**：rf-113 清单的其它断言仍与当前实现一致——`enable_interactive_charts` 默认开（`True`）、6 图清单（`portfolio_line/drawdown/category_doughnut/industry_bar/penetration_bar/radar`）、回撤图 span ≥ 60 交易日（`DRAW_DOWN_MIN_SPAN`=60）才渲染、7 JS 资产 + chart-common.js 依赖、`drawSimpleChart` + Canvas 回退路径仍在（对应 rf-114「先验 rf-113 再删旧路径」的待办）。

### 修复 full 路径 HTML 漏接市场情绪契约（2026-09-18，rf-402）

**背景**（用户反馈）：「同花顺，市场情绪没开启么？我看数据可用性矩阵没提到它」。排查确认**开关与 key 均无问题**（`features.json` 已开 `market_sentiment`、hithink key 就绪、`data/cache/sentiment_*` 本次已由同花顺接口刷新），而是 full 路径的 HTML 端接线遗漏。

**现象**：同一次运行的两份产物自相矛盾——xlsx「15.数据源可用性矩阵」有 `市场情绪 | ✅ 正常 | 同花顺金融数据 ×2`、说明表「✅ 已使用」；HTML 两者皆无（矩阵缺该行、说明表「○ 未使用」），情绪区块也不渲染。

**根因**：`report/_report_generation.py::_generate_report_full` 未取数/未注入 `market_sentiment_data`，且 `_generate_full_html_report` 无该形参、其 `write_html_report` 调用未传参；Excel 侧靠 `report/excel_generator.py` 的「就地兜底」在 **HTML 落盘之后**才触发取数（`logs/app.log`：HTML 20.126 → 情绪取数 20.419/20.799 → Excel 21.032）。矩阵只列**本次取用过的类别**，故取数前生成的 HTML 自然缺行。

**变更**：
- 编排层在写 HTML 之前取数并注入 `pipeline_data`（位置与 both 路径一致：`record_prosperity_diagnosis` 之后、`# ── 6. HTML 报告 ──` 之前），并透传 `prep` 以带出穿透标的（与该路径 Excel 的穿透口径一致）
- `_generate_full_html_report` 新增 `market_sentiment_data` 形参并透传 `write_html_report`（HTML 与 Excel 从此同源同序）
- Excel 就地兜底保留（basic 路径不经编排层；注释「full/both 由编排层注入」自此属实）
- 回归用例 2 例（`test_market_sentiment_wiring.py::TestFullPathInjection`：编排注入 / HTML 生成器透传），已实测对修复前代码两者均失败

**验证**：修复前后各跑一次两例（修复前 `assert None is {...}` / `TypeError: unexpected keyword argument` 失败，修复后通过）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 四个 `--ci` 脚本全 [OK]。

### 文案与实现对齐：市场情绪块的描述口径 + 报告组开关计数（2026-09-19，rf-403、rf-404）

**触发**：用户追问「情绪价值会出现在报告的哪个部分？我没看到」。实测确认区块已正常出现（HTML 行动建议章 ⑦ 号内嵌块 / Excel「7.行动建议」页签），只是当日 0 命中——而两份手册恰好把这种情况写反了，所以先修文档。

**两类文案与实现不符**：
- **位置**：`features.py` 的 `market_sentiment` 开关描述写「**新增独立章**」（初稿形态），实际是行动建议章内嵌块——该偏离在设计文档归档里已记录，只是开关描述未随之更新；它恰是功能开关面板/菜单里展示给用户的文字
- **零命中行为**：`data_source_matrix.py` 说明表、`how-to-config.md`、`datasource.md` 三处写「**无命中时该区块不显示/不渲染**」，而实现是**零命中仍渲染**（标题 + 市场概览 + 「（当日无持仓/穿透标的命中龙虎榜或连板梯队）」+ 口径脚注）——两句话叠加，正好把“功能正常、只是无事件”误读成“没开启”
- **报告组开关计数**（rf-400 同类漏改）：`how-to-use-tui-menu.md`（共 29 项 / 报告组 8 项 + 两处清单漏 `market_sentiment`）、`how-to-config.md`（子模块枚举漏）、`folders.md`（28 项 / 8 项）——实况 **30 项（⚗5 / 常规 16 / 报告组 9）**

**变更**：四处描述口径按实现改正（并把“怎么排查是否已取到数”写进手册：矩阵「市场情绪」行 + 说明表「本次使用」+ `logs/app.log` 的 `[market_sentiment] 命中 N 条`）；四处计数/清单按 `feature_switch_registry` 实况更正并补 `market_sentiment`。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 文档与实现全量核对：4 类共 28 处不一致修订（2026-09-19，rf-405~rf-408）

**触发**：用户要求「核对管理文档和用户文档，比对程序和配置文件，查看有没有不一致的地方，要修订」。

**核对口径**：以注册表（`feature_switch_registry` / 章节注册表 `_REPORT_SECTION_DEFAULT` / 数据模块缓存注册表）、`data/config/config.json` + `_DEFAULT_CONFIG`、文件系统、`pytest --collect-only`（`scripts/collect-test-coverage.py`）为事实源，逐条比对 11 份用户文档（README + manuals 10）+ 10 份管理文档。审计脚本（`docs-stm/tmp/audit_phase{1..7}.py`，gitignore）按「提取代码侧事实 → 反向扫文档断言」两面跑。

**修订四类**：
- **统计快照过期（rf-405，12 处）**：`test-coverage.md` 的 unit/standard/all/report/unit 父标记/unit_report/功能域「报告生成」与实测差 2（rf-402 新增的回归用例未回填）；`folders.md` 的主程序与测试代码行数、测试用例数、managements/项目文档行数未随代码与文档变动刷新（含「源代码合计」联动）
- **目录树漏登 9 个文件（rf-406）**：`folders.md` 未随新增文件同步（`fetcher/financial_indicator.py` + 8 个测试文件）→ 按所属子包位置补条目并附职责说明（取自各文件 docstring）；补后重核「实际有而树内缺 0 / 树内有而磁盘无 0」
- **TUI `[S]` 面板编号表与分组实况脱节（rf-407）**：实验块只列 4 项（缺 ⚗ 景气度框架诊断）、常规块 10-25 未随实验组扩容后移、报告块未编号、三处「第 23 项」位置引用失准、`how-to-use-web-mode.md` 实验清单缺项——而编号本是 `handlers_config.py` 从分组与注册表顺序**派生**（设计上非硬编码）→ 按实况重编（实验 6-10 / 常规 11-26 / 报告 27-35）
- **零星数值/表述（rf-408，3 处）**：`requirements.md` 页签编号 1~19 与默认顺序 19 项（实况 17 个报告章节）；`technical.md` 功能语义命名表中 `market_temperature` 标为默认关（实况默认开）；`testplan.md` 「白名单 7 组」→「7 个可编辑面（功能开关面拆两块）」

**核对为一致（未改）**：30 项开关分组计数与清单、报告章节表（17 项）与 Excel sheet 名、13 份版本头（`check-version-consistency`）、`how-to-config.md` 标量默认值表与 `_DEFAULT_CONFIG`、缓存 TTL 表与 LLM 默认 `max_tokens`/`timeout`、CLI 7 个子命令、`providers/` 与数据源清单路由、测试标记与 conftest；另有 2 类扫描报警经核实为误报（`market_temperature_data` 契约名被前缀匹配、`how-to-config.md` 中非开关表被当成开关表），未改。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 新增文档与实现一致性检查脚本（check-doc-drift.py）并纳入门禁（2026-09-19，rf-409）

**背景**：前一条全量核对用的是临时脚本（`docs-stm/tmp/audit_phase*.py`），用户问「是否有价值留存」。结论：值得——这类「文档里写死的事实」属**易漂移断言**，人工穷举写法必定漏检（本次就把「返回 result（N 项）」与「`market_temperature_data` 同行内的开关默认值」漏掉了，见 rf-409），而每次漂移都直接误导读者。故常驻化为门禁脚本。

**新增 `scripts/check-doc-drift.py`（十一项检查，权威源 → 受检文档）**：
- 章节：报告章节表（`reports-instruction.md` ↔ 章节注册表，行数/序号/名称）+ 章节数量断言（`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`）
- 开关：功能开关表（`how-to-config.md` 三组区段 ↔ 注册表，含表外键与缺项）+ 分组计数断言（三组连写/单组/合计三种写法）+ 默认值断言（`` `flag` `` 后紧随「默认开/关」，不跨到相邻开关、不误匹配 `xxx_data` 形态）
- 默认值：配置标量默认值表（↔ `_DEFAULT_CONFIG`，含 bool/None/数字/路径/引号归一）+ LLM 默认参数表（↔ `_DEFAULT_LLM_SETTINGS` 与缓存 TTL 注册表）
- 结构：TUI `[S]` 面板编号连续性与分组边界（↔ `handlers_config.py` 的派生规则）+ 目录树双向比对（↔ 文件系统）+ 项目统计表（↔ 实测文件数/行数，`--with-test-count` 时再核「测试用例」行）+ 测试覆盖计数表（`test-coverage.md` ↔ collect-test-coverage 快照，同一开关）

**集成**：纳入 P0 提交前门禁与 P2 发布门禁（`CLAUDE.md` / `developer-guide.md` / `testplan.md` §6.3 同步）、`test-runner.py` 的 dev-verify preflight（与编号校验并列，约 1s）；`pyproject.toml` 补 E402 豁免（先注入项目根到 `sys.path`）；`technical.md` 的「约束外参照」新增「文档与实现一致性纪律」条；`folders.md` 目录树与统计表同步。

**测试**：`src/test/unit/scripts/test_check_doc_drift.py`（55 例，`unit_scripts`）——逐项纯函数单测（含误报守卫：相邻开关不串号、`xxx_data` 不误匹配、历史记录类文档豁免）+ 真实仓库冒烟（`run_checks()` 为空）。

**豁免面（设计声明）**：`changelog.md` / `review-findings.md`（如实引用旧数字作为变更记录）与 `docs-stm/archive/**`（版本快照）不参与计数与默认值扫描；结构型默认值（dict/list）与菜单类位置引用（「第 N 项」）不比对（前者文档以「见下节」描述，后者随分组变动属预期）。

**修正**：rf-409 两处（`technical.md` 19→17 项、`market_temperature` 默认关→默认开）；`folders.md` 新增脚本与测试文件树条目与统计刷新。

**验证**：`.venv/bin/python scripts/check-doc-drift.py --ci` → [OK]（`--with-test-count` 连 test-coverage.md 计数一并核对）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 3026 passed / 0 failed（较上次 +55，即本脚本的用例数）；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 全 [OK]。

### 修复一致性检查在 CI 上误报构建产物（2026-09-19，rf-410）

**背景**：提交 `122694d3` 推送后 GitHub Actions 的 `test` job 在 3.11/3.12/3.13 三版本全红（`format` job 通过），失败步骤为新纳入的 P0 门禁（dev-verify）。

**根因**：CI 的 P0 步骤在 `pip install -e ".[test]"` 之后运行，而 editable 安装会在 `src/` 下生成 `*.egg-info/`（该目录本就在 `.gitignore` 中）。一致性检查的目录树/统计比对把工作区所有文件都视为「应被 `folders.md` 登记的源文件」，于是把生成物报成「目录树缺条目」→ preflight 失败。本地未做 editable 安装，故「干净克隆 + 现有 venv」验证无法暴露该差异。

**变更**：新增产物判定 `_is_generated()`——按目录名（`__pycache__` / `.eggs` / `build` / `dist` / `.pytest_cache` / `.ruff_cache` / `.mypy_cache` / `htmlcov` / `test-reports`）、后缀（`*.egg-info` / `*.dist-info`）、文件名（`.coverage`）与路径前缀（`docs-stm/tmp/`）识别构建/缓存产物；目录树比对与项目统计两条路径统一排除。

**回归用例（+11）**：产物判定表（egg-info / pycache / build / dist-info / .coverage / tmp / test-reports 为产物；`core/atomic_write.py`、测试文件不是）+ 含产物的合成仓库用例（构造成员被忽略、真实文件缺条目仍报）。定位于 `TestGeneratedArtifacts`。

**本地复现方式**（供后续同类排查）：在仓库根执行 `mkdir -p src/investor_util.egg-info && echo x > src/investor_util.egg-info/PKG-INFO`，即可复现「目录树缺条目」误报；修复后同一状态下检查通过。

**验证**：`check-doc-drift --ci` → [OK]（`--with-test-count` 连 test-coverage.md 计数一并核对）；`dev-verify` → 3037 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；五个 `--ci` 脚本全 [OK]；统计快照同步刷新（folders.md / test-coverage.md）。

### 测试用例冗余与有效性整备 + 新增 check-test-redundancy.py（2026-09-19，rf-411）

**触发**：用户问询「有没有冗余的测试用例，无效的测试用例」。对 381 个测试文件 / 7,245 个用例做 AST 静态审计（并与 `pytest --collect-only` 节点比对），结论与处置：

**四类问题**：
- **完全重复 20 组**：14 组为同一被测对象同一断言（跨文件或同文件），6 组是不同 provider 解析器（`_safe_float` vs `_parse_float` 等）的**并行覆盖，保留**
- **自证用例 6 个**：`test_cache_edge.py` 的 `get_ttl` 系列把被测函数本身 patch 掉，再断言自己设的 `return_value`——断言恒真、等于没测
- **名实不符 7 例**：`test_default_true`（实际设了 `SSL_VERIFY=true`，默认分支从未被测）、`test_none_content`（传 `""`）、`test_none_returns_low`（传 `[]`）、`test_midday_145959_still_midday`（时间由 patch 决定，与 11:30 用例完全同分支）、`test_afternoon_closed_uses_long_ttl`（与午休同义）、`test_capture_snapshot_first_run`/`holding_mapping`（两者同体同断言，且后者名字声称验字段映射却只断言返回 `None`）
- **无断言 16 个**：仅「调用不抛异常」，未断言任何可观测结果

**负面结论（同样是有效信息）**：**无死用例**（无同名覆盖 / 无非 `Test` 类的 `test_*` / 无 `Test` 类 `__init__`）、**无空测试体**（既有守护生效）、**parametrize 无重复参数集**、20 个 `test/live/*` 是 `pytest.ini` 刻意排除的 opt-in 套件（非死用例）。

**处置**：跨文件重复删其一；同文件重复合并（`test_html_builders_edge` 价格变体 4→1 用 `subTest`、`test_cache_edge` 午休/收盘合并、`test_market_hours` 09:30 重复删一、`test_news_sources` 字母 token 重复删一）；6 个自证用例改为真实断言（patch 依赖、断言真 `get_ttl`）；7 例名实不符改为真跑其声称场景（含 `capture_snapshot` 映射用例改为断言传给 `save()` 的快照字段）；16 处补可观测断言（stdout 静默、错误列表、删除尝试次数、`assert_not_called`、产出文件存在等）。

**新增 `scripts/check-test-redundancy.py`（四类检查 + 误报守卫）**：死用例（不可收集/被覆盖）／无断言（含「断言落在同类辅助方法」的解析）／完全重复（去 docstring 后函数体+参数+装饰器 AST 归一化；**无法解析的 `self.<attr>` 间接调用跳过比对**，避免把并行覆盖误判为重复）／自证用例（patch 被测函数 + `return_value` 断言回原值）。纳入 P0/P2 门禁与 `test-runner.py` 的 dev-verify preflight；`developer-guide.md`（工具表 + 专门章节）、`testplan.md` §6.3、`technical.md`「约束外参照（测试有效性纪律）」、`CLAUDE.md`（P0/P2 + 独立性条目）同步；`folders.md` 目录树与统计刷新。

**验证**：`check-test-redundancy --ci` → [OK]（0 死用例 / 0 无断言 / 0 完全重复 / 0 自证）；`dev-verify` 全绿；`ruff check` + `ruff format --check` 全绿；`check-doc-drift --with-test-count` 连计数一并核对通过。

### scripts/ 优化：性能修复 + 共享模块抽取 + test-runner 拆包（2026-09-19，rf-412 / rf-413）

**触发**：用户问询「scripts 目录下的脚本有没有可优化的空间」。审计 23 个脚本（AST 克隆检测 + 真实计时 + cProfile + 调用方引用统计）。

**① 性能（P0 门禁合计 15.7s → 4.0s）**
- `check-semantic-index.py` **7.15s → 0.25s（≈29×）**：`slug_exists_in_code()` 曾对**每个 slug** 遍历全部 `.py` 并 tokenize 一次（116 slug × ~88 文件 ≈ 10,176 次全文件 tokenize；cProfile 显示 `tokenize` 占其 95% 耗时）。改为 `collect_code_texts()` 每次检查只收集一次、所有 slug 复用
- `check-code-traces.py` **4.53s → 3.32s（−27%）**：89 个模式逐行逐一匹配（3.8 万注释行 × 89 ≈ 345 万次 regex）→ 加模式编译缓存 + **并集预筛**（单次扫描判定该行是否可能命中，未命中即跳过逐一匹配；命中后仍走精确分支，判定结果不变）；标识符模式同样改为预编译

**② 共享模块（消除重复与漂移面）**
- 新增 **`scripts/_checklib.py`**：统一 CLI 契约（`add_common_args()` 的 `-v/--verbose` + `--ci`）、统一输出与退出码（`report()`：通过 0 / 发现 finding 2，`--ci` 仅输出裸描述）、`REPO_ROOT`/`rel()`、文档标记区间与表区域解析（`extract_region`/`replace_region`/`extract_table_region`/`replace_table_region`）
- 新增 **`scripts/_traces_common.py`**：两个历史痕迹检查脚本 4 个逐字节相同的函数（章节计数豁免 / 迭代轮次豁免）收拢一处；两脚本以原面 re-export + `__all__` 暴露同名符号，既有测试与调用方无需改动
- 语义命名索引、文档一致性、测试冗余、版本一致性、编号一致性、测试标记等脚本改为复用 `_checklib`

**③ 契约统一**：`check-version-consistency.py` 补 `--ci`（仅报失败、退出 2）；`check-task-numbering.py` / `check-test-markers.py` 发现违规退出 2（原为 1）；`check-svg-geom/pixel/text-overflow` 三件套合并为 **`check-svg.py`**（子命令 `geom` / `pixel` / `text-overflow`，带 `--ci` 与退出码 0/1/2）

**④ `test-runner.py` 拆包（1,600 → 246 行入口 + 7 模块）**：`scripts/_test_runner/` 按职责拆分 `paths` / `modes` / `pytest_env` / `machine_info` / `doc_writer` / `report_html` / `runner`（最大 345 行）；入口保留 CLI 与主流程并 **原面 re-export 49 个符号**，既有测试与调用方零改动（受影响测试的 monkeypatch 改指向持有状态的子模块，如 `_test_runner.report_html._LATEST_DIR`）

**⑤ 清理**：2 处死代码（`_ratio_band`、`_check_exact`）；新增 `src/test/unit/scripts/test_checklib.py`（38 例）覆盖共享设施与共享排除模式

**⑥ 顺带修正 rf-413**：`check-svg` 的像素子命令依赖 Pillow 但依赖清单未声明（干净环境必 `ModuleNotFoundError`）→ 改为按需导入 + 可读指引 + `[svg]` 可选依赖组（`pyproject.toml` / `requirements.txt` 同步）

**验证**：`check-semantic-index --ci` / `check-code-traces --ci` / `check-doc-drift --ci`（含 `--with-test-count`）/ `check-test-redundancy --ci` 全 [OK]；`dev-verify` 3098 passed / 0 failed；`ruff check` + `format --check` 全绿；统计快照（folders.md / test-coverage.md）同步刷新。

### README 架构图卡片加宽：消除 4 处文本贴边（2026-09-19，rf-412 收尾，commit `32b3766c`）

**触发**：`check-svg.py` 三合一后首次具备退出码（0/1/2），随即暴露 4 处「文本贴边」——卡片内文本右余量仅 1~4px（`_PADDING_WARN = 6px` 阈值，按字符宽度估算模型）。此前三个 svg 脚本各自无退出码、恒为"通过"，这类版式风险不会出现在任何门禁输出里。

**变更（只加宽卡片，不位移任何元素）**：
- `src/static/architecture.svg`：左侧渠道列三卡 210 → **220**（+10px）——`全键盘菜单 · 方向键+字母` 右余量 1.9 → 11.9px；中间双列六卡统一 172 → **180**（+8px）——`实时行情 · 多源回退` 3.5 → 11.5px、`风险 · 情景 · 再平衡` 2.0 → 10.0px（两列保持等宽，列间距 16 → 8px；右列右缘 686 仍在引擎面板 700 内）
- `src/static/llm-chain.svg`：顶部四个 Provider 卡片统一 200 → **210**（+10px）——`Anthropic · Opus/Sonnet` 右余量 1.4 → 11.4px（右缘 934 距容器 960 仍余 26px）
- **安全性核对**：卡片右缘（240/490/678/276）**零引用**（无连接线/箭头锚定其上），卡内文本均为左锚定或 middle 锚定在卡片外的坐标 → 仅变宽、不移动任何元素
- 矩形底部不齐降为**提示项**（流程图同列卡片高度本就允许不同，原判定会误报），已在 `developer-guide.md` 记明

**结果**：三张 SVG 均通过 `geom`，卡片内文本右余量 ≥10px（`capabilities.svg` ≥19px）。

**验证**：`check-svg.py --ci geom src/static/*.svg` → [OK]；`dev-verify` 3098 passed / 0 failed；`ruff check` + `format --check` 全绿；八个 `--ci` 检查脚本 + `check-doc-drift --with-test-count` 全 [OK]；folders.md 统计同步刷新。

### 修复 test-runner 拆包期的报告误落位置 + 检查器漏检（2026-09-19，rf-414）

**触发**：用户发现「scripts 目录下有 test-reports 目录」。

**成因**：`test-runner.py` 拆包时，迁移把入口的项目根算式 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 原样搬进 `_test_runner/paths.py`——但该文件比入口深一级，于是 `_PROJECT_ROOT` 算成 `scripts/`，22:51 的两次 `dev-verify` 校验把归档与汇总页落到 `scripts/test-reports/`（内含 `archives/20260919/225126`、`225129`）。同一根因也让 preflight 路径拼成 `scripts/scripts/check-task-numbering.py` 而报错，因此在修复前已暴露；修好 `_PROJECT_ROOT` 后（22:51:35）随后几次运行（`225139` 起）即落回仓库根 `test-reports/`。

**为何此前没被拦住**：产物本身在 `.gitignore` 内、从未入库；但**检查器漏检**——`check-doc-drift._is_generated()` 把任意层级的 `test-reports` 一律豁免，受检目录下的误落不会被报出。

**变更**：
- 删除误落目录（仓库根 `test-reports/` 为规范位置，未受影响）
- `check-doc-drift._is_generated()` 不再豁免 `test-reports`：其规范位置在仓库根、本不在受检范围内，故受检目录（`src/`、`scripts/`、`docs-stm/{managements,manuals,plan}`）下出现必属误落；文档串写明该例外与成因
- 回归用例：`check-doc-drift` 补「`scripts/test-reports/index.html` 须报目录树缺少」；`test-runner` 补 `TestProjectRoot`（`_PROJECT_ROOT` 必须等于仓库根、`_LATEST_DIR`/`_ARCHIVES_DIR` 不得含 `scripts` 段）
- `CLAUDE.md`（目录结构同步条）与 `folders.md`（目录树条目）注明「`test-reports/` 只应在仓库根」

**验证**：`check-doc-drift --with-test-count` → [OK]（含误落检测用例）；`dev-verify` 3098+ passed / 0 failed；`ruff check` + `format --check` 全绿；八个 `--ci` 检查脚本全 [OK]；复跑 `test-runner` 确认不再于 `scripts/` 下生成 test-reports。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.1（2026-09-15 ~ 2026-09-18）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

---

## [0.11.3] - 2026-09-24

### 需求 ID 追溯链（rf-426）：批 2~6 完成 —— 276 条需求全量映射 + 门禁转全量断言（2026-09-24）

**批 2（38 条）**：`R-ERR` 错误与降级可视化（备用链路/过期缓存/占位文本两态区分/快照无历史）、`R-DIAG` 诊断三面（CLI `view-logs`+`doctor` / TUI `[V]`/`[H]`/`[D]` / Web `/api/logs`+`/api/health/history`+`/api/doctor`）、`R-BRK` 熔断治理（单股 3 次/批量 6 次·120s、空数据不计、LLM 独立熔断、会话缓存 2000、指数退避、`data/state` 持久化、网关统一双熔断器）、`R-CRD` 凭据声明式（`CredentialSpec`/就绪判定/可读指引/链路跳过不进熔断/跳过态/体检分组/值不外泄/开关逐字节等价）

**批 3（37 条）**：`R-FIN` 财务指标域（标准字段契约/akshare 主源/链路接入/`to_fmp_symbol` 收敛/底座门禁/降级不阻断/PE-PB 官方口径/报表派生/全文解析支路/解析护栏/双端区块/多期序列/管线契约/真实形态夹具）、`R-FRD` 财报摘要（开关/密钥文件/最新报告期/限速与日配额/占位与失败清单/合规来源/缓存分级）、`R-NWS` 新闻（5 源独立取数/关联度排序/关键词来源/颜色分型/独立启停/LLM 二次关联）、`R-DATA` 数据治理（备用链路/静默降级/会话复用/盘中 30s TTL/收盘 `price_date` 校验/00 代码判定）、`R-IDX` 指数双链路（A 股腾讯→新浪、美股新浪→腾讯、降级过期缓存）

**批 4（71 条）**：`R-OUT` 产物路径与格式（根/存档目录、文件名、页签 1~17、单页 HTML+TOC、`report_section_order`、LLM 用量页签固定末位、条件渲染两层、深浅主题）、`R-PERF` 性能（5 源并行、LLM 并发、批量异步取价、配置 mtime 缓存、提示词精简、会话复用、历史增量、阶段超时、耗时记录、后台健康检查）、`R-WIF` 调仓模拟（CLI/TUI 入口、变动类型、成本截面、分类对比、双产物、零网络默认、生效日回测 5 指标、降级）、`R-ACT` 行动建议（章节与开关、`action_data` 契约、再平衡信号、占位、关闭不渲染）、`R-RBL` 再平衡（阈值与预设、静默期持久化、置信度、三类误报防护、注入 LLM）、`R-VAL` 估值分位（TTM EPS 构造、披露截止日、分位口径、底座门禁）、`R-TAIL` 尾部风险、`R-EVO` 组合演进、`R-SNP` 快照（自动创建/隔离/保留策略/对比）、`R-CFL` 成本流水（XIRR/快照近似/开关/列）、`R-DIFF` 快照差异摘要

**批 5（25 条）**：`R-LLM`（L 菜单触发、模块独立启停、三类协议 + 厂商路由、递补降级、用量统计、4 切换策略、凭据分离、失败原因追踪、信号预消化含叙事-数字背离）、`R-PF` 景气度框架（实验开关逐字节等价、六维评分卡、客观化口径、两项扩展标口径、缺失标 `unverified`、评级口径、双端呈现位置、`evidence` 可核对、配置）、`R-CTX` 竞争语境（`comparison_indices`、收益/风险对比、口径脚注、幸存者偏差提示、LLM 仅陈述、基金池 TUI 管理）

**批 6（66 条）**：`R-WEB`（回环启动、上传校验、格式选择、事件流进度、预览下载、单 worker 队列、生命周期、配置编辑面板、试算/正式隔离）、`R-TUI`（标题、20 选项、缺省选中 `[L]`、选择器、进度提示）、`R-ENV`（Python 实现、双平台启动脚本、双平台 Web、`cli.sh`/`cli.ps1`——启动脚本项含手工验收）、`R-HLD` 持仓格式（页签=账户、4 列、列名/顺序固定、代码去前缀）、`R-DIS` 交易纪律（止盈/止损/回撤三线、静默期复用、配置段）、`R-LIQ` 流动性（变现天数、场外赎回上限与类型默认档、数据缺失默认充足、注入 LLM、场内分级、OTC/非 A 股标记）、`R-FX` 汇率敞口、`R-CON` 健壮性（key 未配置/config 损坏/格式异常/无权限/空持仓/模块独立降级/断网降级/降级可视化）、`R-ADP` 适配器三段式契约（声明式归一、输出恒为全字段、链路接入、试点等价性、开关逐字节、离线自检）、`R-HST` 历史数据（双链路、增量合并、修正全量刷新、模式 off/prompt/auto、00 代码降级、基准指数链）

**收尾**：`_COVERED_DOMAINS` 扩至 **34 域**（与 `_ALL_DOMAINS` 一致，R-PEN 为不存在的域已移除），门禁由「已补域全覆盖」转为**全量断言**；测试新增真实仓库全量对照（需求侧 276 条 ID ↔ 映射表 276 行逐条相等）；`review-findings.md` 的 rf-426 由「待处理」迁入「已解决」。

### 需求 ID 追溯链（rf-426）：批 1 R-CCH 缓存域完成 + 新增追溯断言脚本并入门禁（2026-09-24）

**背景**：`requirements.md` 定义 276 个需求 ID（34 域），但 testplan / technical / llm-technical 对其引用数为 0——无法机器回答「某需求是否有测试覆盖」。交付形态定稿为「映射表落 `testplan.md` §2.1」（按需求 ID 组织、含验证载体列、`<!-- requirement-trace:start/end -->` 标记区间）。

**批 1（R-CCH 缓存域 38 条）**：
- §2.1 新增 38 行映射，覆盖：缓存机制（01 磁盘缓存 / 02 gzip 100KB 阈值 / 03 目录穿越防护 / 04 原子写 / 05 损坏自愈）、缓存键清单（06~33 各数据域 TTL 与前缀分组）、输入摘要与依赖失效（34 确定性摘要 / 35 指数行情→预测与资金流向 / 36 持仓+穿透代码→分红 / 37 新闻源+关键词→新闻 / 38 持仓份额成本→LLM）
- 载体精确到用例级（如 `test_cache_format.py::test_large_file_auto_gzipped`、`test_holdings_tracker.py::test_different_shares_different_fingerprint`）

**新增 `scripts/check-requirement-trace.py`（复用 `_checklib`）**：五项断言——① 映射表标记与表头齐备（防整表误删）；② 映射 ID 均存在于 requirements.md（防臆造/拼错）；③ ID 唯一（防两行矛盾）；④ 已补全域 ID 全覆盖（防「补了 37 条漏 1 条」）；⑤ 载体列中的 `src/test/**/*.py` 路径真实存在（防测试改名后文档悬空）。**分批推进**：常量 `_COVERED_DOMAINS` 记录已补全域，每批追加一项即扩大断言范围；`_ALL_DOMAINS`（34 域）用于进度显示。已并入 P0 + P2 门禁（CLAUDE.md / testplan §6 / developer-guide）。

**测试**：`src/test/unit/scripts/test_check_requirement_trace.py` +16 例（解析 4 / 断言 8 / 真实仓库 3 / 空输入）；真实仓库冒烟断言 38/38 已映射且载体文件全部存在。
**顺带修正**：testplan §6 门禁行早前追加枚举时多出一个右括号。

### 用户文档 vs 管理文档比对：修手册 thinking 章节漏 Kimi + 新增矩阵守卫（2026-09-24，rf-427）

**背景**（用户要求）：比对 `requirements.md` + `technical.md` + `llm-technical.md` 与用户文档（README + 10 份手册），冲突处回查代码。

**判定为冲突（已修）**：`how-to-config-llm.md` 的 Extended Thinking 章节**内部自相矛盾**——支持矩阵 bullet 已含 Kimi，但「模型差异」对比表只有 3 列、且 601/608 行写「**仅**在使用 Claude 或 Gemini 模型时 `thinking_budget` 有意义」；而代码（`_THINKING_SUPPORTED_PREFIXES` 含 `kimi-`，且 kimi 不在 effort 族 → 走 `budget_tokens`）与 `llm-technical.md` 均确认 Kimi 属 budget 族。

**变更**：
- 对比表补 **Kimi 列**（控制参数 `thinking.budget_tokens` / 与 temperature 互斥 / 兼容端点 `api.moonshot.cn/anthropic` / 推荐场景），并新增「**默认思考行为**」行（DeepSeek 与 Kimi 默认开思考）
- 601/608/610 行措辞改为「Claude / Gemini / Kimi（`budget_tokens` 族）」
- 新增「默认开思考的厂商需注意（DeepSeek / Kimi）」说明段：未开启 thinking 时工具自动显式发 `disabled` 兜底，避免思考占满 `max_tokens` 致正文为空
- **新增断言（check-doc-drift 第 13 项）** `check_thinking_support_matrix()`：从 `api_base` 前缀名单派生「支持族 / effort 族 / 默认开思考族」，三项校验——① 对比表列须覆盖全部支持族；② 含「仅」且带 budget 概念词的句子须枚举全部 budget 族（防「仅 A / B」式漏族）；③ 默认开思考族须在手册中有「默认开思考」提示。**实现上先过滤掉无 budget 概念词的「仅」句**（如实测 /定价行），避免误报——已在真实仓库验证零误报
- 回归测试 +7（真实仓库一致 / 缺厂商列 / 封闭枚举漏族 / 无关「仅」句不误报 / 整表缺失 / 默认开思考缺提示 / 空文本）
- 检查项枚举同步 6 处

**判定一致、无冲突（已回查代码）**：17 章节 / 8 个 type 组；定价表 18 行逐值一致；缓存 TTL 可映射 19 条零不一致；datasink 速率与配额（3/31 请求每秒、8,191/131,071 篇每日）；batch 键含 `akshare_workers`；provider 类型定义（协议三类）；场外默认档 T+1/T+2/T+3/T+7；LLM 用量 Endpoint 主备标注；巨潮备源描述；thinking 兜底公式。

### 四文档一致性核对：修正 2 处冲突 + 补齐 2 处缺口 + 建需求追溯任务（2026-09-24，rf-426）

**背景**（用户要求）：交叉比对 `requirements.md` / `technical.md` / `llm-technical.md` / `testplan.md`，冲突处回查代码，形成待决策清单（Q1~Q4，用户已定调）。

**判定为冲突（已修）**：
- **`datasink_workers` 默认值**：`technical.md` 写「默认 3」，代码与默认模板均为 **2**（`_config_defaults.py`、`financial_report_digest.py` 同值），且原句把「请求速率 3 请求/秒」与「并发 worker 数」混为一谈 → 改为「默认 2，免费档批量上限 ≤3」
- **Provider 厂商枚举未含 Kimi**：`requirements.md` R-LLM-03 与 `technical.md` 模块表仍按「Claude/OpenAI/Gemini 三厂商 + claude 兼容端点只归 DeepSeek」表述，而 `llm-technical.md`（定价表/thinking 名单）与代码均已含 Kimi → 按用户决策 **A 改枚举范式**：协议层固定三类（claude / openai / gemini），**厂商与模型由 `model` 指定**并显式列举兼容端点厂商（DeepSeek、Kimi），新增厂商零代码接入

**判定为缺口（已补）**：
- **testplan 覆盖表未随 v0.11.2 扩展更新**：景气度框架行补挂本轮新载体（`test_fund_roe_estimate.py` ②维 ROE 推演；`test_liquidity_otc.py` 与 `test_code_utils.py::TestOtcRedemptionDaysDefault` ④维场外默认档）
- **口径重复维护点**：R-PF-09 的④维档位串与 `R-LIQ-03` 逐字重复 → R-PF-09 改为引用 `R-LIQ-03`（单一维护点），仅保留②维推演口径原文

**新建待办任务（用户决策 Q3-B：分批映射）**：`review-findings.md` 新增 **rf-426**「需求 ID 追溯链断裂」——276 个需求 ID 在 testplan/technical/llm-technical 中引用数为 0；按 6 批（38/39/37/57/25/61 条）分批建立「需求 ID → 验证载体」映射，批 1 启动时先定稿交付形态（testplan 加列 vs requirements 加列），配套双向断言脚本入 `--ci`。

**另修**：`testplan.md` 两处 `管理文档分区纪律)）` 括号错配（上轮批量替换枚举时引入的笔误）。

**判定一致、无需改动**（已回查代码）：报告章节 17 项 / 开关 30 项（实验 5·常规 16·报告 9）/ P 面板 5 个章节 / LLM 模块 5 个 / datasink 速率配额（3·31 请求/秒、8191·131071 篇/日）/ thinking 兜底 `max(1024, max_tokens−2048)` / plan-47·48 档位三方一致。

**验证**：六项 `--ci` + ruff + 版本一致性全绿（本轮为纯文档修正，无代码变更）。

### 测试用例全量审计：去冗余 + 26 处名实相符重命名 + 弱断言强化（2026-09-24，rf-425）

**背景**（用户要求）：核对全部测试用例的冗余、无效与命名语义。门禁 `check-test-redundancy`（死用例/无断言/完全重复/自证）零告警；另建 AST 级增强扫描（7,378 用例）核查门禁未覆盖的三类。

**变更**：
- **去冗余**：`TestSupportsExtendedThinking` / `TestIsEffortModel` 在 `test_llm_utils.py` 与 `test_llm_api_base.py` 重复存在且后者为严格子集——唯一独有断言（`gpt-4o → False`）迁入 utils 版新增 `test_non_llm_family_not_supported`，删除两个子集类（-5 例，零覆盖损失）
- **重命名 26 处**：`test_success` / `test_normal` / `test_basic` 等不承载内容的命名，逐例读函数体后按 docstring 语义改为描述性命名（`test_returns_standard_quote_record` / `test_parses_roll_data_items` / `test_parses_three_us_indices` / `test_formats_dividend_yield_percent` 等）
- **弱断言强化 1 处**：`test_missing_code_still_processes` 改为精确断言（`turnover_rate == 1.0`，由两期权重不相交可推导），消除「仅非空」在实现假化时仍通过的空间
- 数据快照同步：`test-coverage.md`（unit/standard/verify/all/unit_llm）、`folders.md`（测试用例 7,760、行数）

**判定为合规、不改的部分**（避免制造「名实不符」新缺陷）：跨文件同体对 1 组（`test_no_quotes` —— sina/tencent 两家解析器并行覆盖，符合既定口径）；输入条件式命名 26 处（`TestParseFloat::test_zero` 等，类上下文已带语义）；抽样 7 例「仅非空断言」中 6 例判别性充分（warning 字段被填充 / lookup 命中 / 映射存在 / 回调已绑定）。

**验证**：受影响模块 4,632 passed；`check-test-redundancy --ci` 零告警；六项 `--ci` + ruff + 版本一致性全绿。

### 新增管理文档分区纪律断言（2026-09-24，rf-424）

**背景**：本轮两次自审失误同源——待处理项被误置已解决区（rf-421）、发布时误删归档索引（rf-423），本质都是「管理文档分区/索引纪律无机器断言」，门禁全绿也拦不住。在 rf-423 已补「归档索引完整性」之后，本轮补齐「分区纪律」。

**变更**（`scripts/check-doc-drift.py` 第 12 项）：
- 新增纯函数 `audit_management_partitions()`（读文件薄封装为 `check_management_partitions()`），三条规则：
  - **A. review-findings 分区互斥 + 已解决须有据**：同一 rf 不得同时出现在「待处理」与「已解决」；且每个已解决项必须在 changelog（现行 + 归档）中出现——待处理项被误置已解决表时必然无修复记录，正是该类失误的可检特征
  - **B. plan 待办区纯度**：不得出现 ✅ 已完成项，也不得列已归档项（已归档项只认 `#### ✅ \`plan-N\`` 条目标题，归档文件正文提及——如「后续项：plan-49 转正评估」——不误判）
  - **C. changelog 段头纪律**：现行文件只允许一个版本段头且必须为 `-dev`（已发布版本段须随发布移入 `archived_changelog.*.md`）
- 检查项枚举同步 6 处：脚本 OK 文案与 argparse 描述、`folders.md` ×2、`developer-guide.md`、`testplan.md` ×2、`CLAUDE.md` ×2（门禁条目）

**回归 +10**：真实仓库一致、三类历史失误各自检出、归档 changelog 中的记录不误报、归档文件正文提及不误报、空文件不崩。

**验证**：`pytest src/test/unit/scripts/test_check_doc_drift.py` → 83 passed；六项 `--ci` + ruff + 版本一致性全绿。

### 修复归档索引被误删 + 新增归档索引完整性守卫（2026-09-24，rf-423）

**背景**（用户指出）：发布 v0.11.2 的版本切换提交把 changelog「已发布段至文件末尾」整段重写，而 `## 归档` 索引段位于文件末尾 → 11 条历史归档索引被一并删除。当时没有任何断言覆盖「管理文档归档索引 ↔ `docs-stm/archive/` 实际文件」的一致性，故门禁全绿也未拦下。

**变更**：
- `changelog.md`：从发布前版本取回 `## 归档` 索引段（11 条，0.11.x 条目更新为 v0.11.0 ~ v0.11.2），移除发布时临时添加的单条指针
- `scripts/check-doc-drift.py`：新增第 11 项**归档索引完整性**检查 `check_archive_index()`——changelog / plan / review-findings 三份管理文档的归档索引与 `docs-stm/archive/` 下对应 `archived_*` 文件**双向**比对（漏列 → 「缺少」；幽灵引用 → 「不存在」）；实现上**直接读文件**，不走 `_scan_docs()`（该扫描面排除历史记录类，changelog 正在其中——正是本次缺口的成因）
- 回归测试 +5：真实仓库一致、正反两向检出、被检面覆盖三份文档、以及一条端到端「真实仓库索引被删即报」用例

**验证**：`pytest src/test/unit/scripts/test_check_doc_drift.py` 73 passed；六项 `--ci` + ruff + 版本一致性全绿。
