# 工作任务分解

> **说明**：基于 `discussion-better-investment-advice.md` 全量 6 层改进方向、7 个交付批次的细粒度任务分解。  
> **原则**：每个任务独立完备、可测试、可分配，依赖关系显式标注。  
> **估时基准**：h = 工时（8h = 1 天），按 2 人团队估算。  
> **依赖标记**：`← [T-XXX]` = 此任务被 T-XXX 阻塞；`→ [T-XXX]` = 此任务为 T-XXX 的前提。

---

## 图例

| 字段 | 说明 |
|------|------|
| **ID** | `PRE-`(专项测试) / `T0-`(Tier 0) / `MVP-`(MVP) / `P1-`(Phase 1) / `P2-`(Phase 2) / `P3-`(Phase 3) / `P4-`(Phase 4) / `P5-`(Phase 5) / `PD-`(Phase D：**D = Discretionary/独立决策**——不属于主路线图序列，需单独评估 ROI 后决定是否投入) |
| **估时** | 工时（h），8h = 1 天 |
| **文件** | 需新增/修改的代码文件（已知代码行号用 Lxxx 标注） |
| **阻塞** | 此任务是否被外部数据源验证阻塞（是/否） |
| **依赖** | 前置依赖任务 ID 列表（无=无依赖） |

> **测试策略说明（R5-05）**：每个任务标注了推荐的测试验证方式。原则是**每次只跑合适的测试案例**，不必每次都跑全量 regression/verify：  
> - *prompt-only* → 只跑 `pytest src/test/unit/llm/test_prompts.py -x -q`（~5s）  
> - *unit* → 跑 `pytest src/test/unit/` 对应模块测试（~10-30s）  
> - *dev-verify* → `python scripts/test_runner.py --mode dev-verify`（~2min）  
> - *regression* → `python scripts/test_runner.py --mode regression`（~10min，P0 门禁）  
> - *all* → `python scripts/test_runner.py --mode all`（~30min+，P2 发布门禁）  
> ⚠ 注意：`--mode regression` 与 `--mode scenario` 当前配置完全相同（功能冗余），建议后续合并。

---

## PRE — 立项前专项测试

> ✅ **全部完成（2026-07-20）**。4 项 PRE 任务均已完成测试与决策：
> - PRE-01/PRE-01-D：东财 API 不可用 → `bond_zh_us_rate` 替代，P1-01/P1-02 取消
> - PRE-02/PRE-02-D：885005 不可获取 → 沪深300+自定义基金池降级
> - 详见测试报告 `rf-and-885005-test-report.md`

### PRE-01: Rf 国债收益率数据源可用性测试
- **估时**: 8h（1 天）
- **文件**: 无代码改动，纯手工测试
- **阻塞**: 否（独立）
- **依赖**: 无
- **状态**: ✅ 已完成（2026-07-20）
- **描述**: 验证 Rf（无风险利率）数据源的可用性。测试 3 个候选源：(1) 东方财富 `datacenter-web` API（原规划主源，**已失效**——所有 `RPTBOND_*` report name 均返回"参数配置不对"）；(2) `worldgovernmentbonds.com`（JS 渲染，不可直接抓取）；(3) **`bond_zh_us_rate`（akshare 封装的 Sina 财经数据）——已验证稳定可用**（详见测试报告 `rf-and-885005-test-report.md`）。⚠ **决策影响**：原规划 P1-01（东方财富 API fetcher, 12h）和 P1-02（备用源, 8h）取消，P1-03（手动配置, 2h）改为 `bond_zh_us_rate` 自动源 + 手动兜底双模式。

### PRE-01-D: PRE-01 决策门（0h）
- **估时**: 0h
- **文件**: 无
- **阻塞**: 否
- **依赖**: PRE-01
- **状态**: ✅ 已决策（2026-07-20）
- **描述**: **PRE-01 测试结论：东方财富 datacenter API 已不可用，`bond_zh_us_rate`（akshare/Sina）为可行替代。** 决策：(1) P1-01（东方财富 API fetcher, 12h）和 P1-02（备用源 fetcher, 8h）**取消**；(2) P1-03（手动配置, 2h）**保留**，但扩展为双模式——`bond_zh_us_rate` 自动获取（主）+ 用户手动配置（兜底）；(3) P1-15（Rf 测试, 8h）缩减为 `bond_zh_us_rate` 集成测试（4h）；(4) 合计释放 **~20h** 重新分配给 P1-11（功能开关）、P1-12（断路包装器）、P1-04（数据质量增强）。详见测试报告 `rf-and-885005-test-report.md`。

### PRE-02: 偏股基金指数 885005 可用性测试
- **估时**: 4h（含 akshare+东方财富+新浪/腾讯 多源测试）
- **文件**: 无代码改动，纯手工测试
- **阻塞**: 否
- **依赖**: 无
- **状态**: ✅ 已完成（2026-07-20）
- **描述**: 测试 885005（中证偏股基金指数）的可用性。测试覆盖 akshare（`index_zh_a_hist`/`stock_zh_index_daily`/`fund_info_index_em`）、东方财富（push2his/push2 全部市场码 0~19、基金 index API/performance API）、新浪、腾讯、CSI 中证指数官网。**结论：885005 是 Wind（万得）专属代码，所有免费公开 API 均不可获取。** CSI 替代代码（930950/932055/931255）同样不可用。详见测试报告 `rf-and-885005-test-report.md`。**P3-07 强制降级为沪深300+自定义基金池**。

### PRE-02-D: PRE-02 决策门（0h，决策已落地 → 实现归入 P3-07）
- **估时**: 2h（决策 0h + P3-07 内实现 2h）
- **文件**: 决策阶段无代码改动；prompt 降级说明实现归入 `src/python/llm/prompts.py`（P3-07）
- **阻塞**: 否
- **依赖**: PRE-02
- **状态**: ✅ 已决策并落地（2026-07-20）——决策结论已更新至 design docs，prompt 代码实现归入 P3-07
- **描述**: **PRE-02 结论：885005（Wind 专属代码）不可获取，CSI 替代代码同样不可用。** 决策已生效：P3-07 不扩展 `index.py` 增加 885005，竞争语境只使用沪深300+自定义基金池。`prompts.py` 降级说明段落"偏股基金指数暂不可用，以下对比仅基于沪深300"的实现归类到 P3-07 执行。

---

## T0 — Tier 0 基础设施（超优先，~12h）

### T0-01-A: DegradationTracker get_log() 查询接口封装 + record() 注入 + 单例工厂（前置）
- **估时**: 5h（修正：2h→5h，含 fetcher 层 6 处注入 + 三实例统一为单例 + 测试）
- **文件**: `src/python/report/data_status.py`（扩展 DegradationTracker + 新增 `get_tracker()`）、`src/python/report/fund_performance.py`、`src/python/report/penetration_sheet.py`、`src/python/report/summary.py`（各改 1 行 import）
- **阻塞**: 否
- **依赖**: 无
- **已知降级调用点（需注入 record()）**: `src/python/fetcher/price.py`(L184, L200 — 2处), `src/python/fetcher/fund.py`(L47, L73 — 2处), `src/python/fetcher/industry.py`(L64 — 1处), `src/python/fetcher/index.py`(L240 — `fetch_with_incremental_fallback`, 1处)。共 6 处 fetcher 层降级点。
- **描述**: 当前 DegradationTracker 在 fund_performance.py/penetration_sheet.py/summary.py 中已实例化且 **report/ 层已有 6 处 record() 调用**（`fund_performance.py:345` 的 perf_rank、`penetration_sheet.py:143/160/174` 的 industry/profit_forecast/dividend、`summary.py:285/306` 的 index_a/index_us）——但这些全是数据状态构建阶段的消费侧记录。**fetcher/ 层的 6 处降级点（price.py×2、fund.py×2、industry.py×1、index.py×1）仍然缺失 record()**，导致真正触发降级时的原始错误（全链路不可用/fallback 降级）未被捕获。这是一个架构性缺陷——fetcher 层降级事件丢失，data_degradation 内容不完整。需完成：(1) 在 DegradationTracker 上封装 get_log() → list[dict] 方法，汇总当日所有降级记录；(2) 在以上 6 处 `fetch_with_fallback()` / `fetch_with_incremental_fallback()` 调用点注入 DegradationTracker.record() 调用，区分"全链路不可用"和"fallback 降级"两种场景；(3) 在 `data_status.py` 中新增模块级单例工厂 `get_tracker()`，将 `fund_performance.py`/`penetration_sheet.py`/`summary.py` 三个文件级独立实例统一为单例（各改 1 行 `_tracker = DegradationTracker()` → `_tracker = get_tracker()`），消除降级状态碎片化，统一持久化路径；(4) 确保 orchestrator.py 的 data_degradation 键仅在记录非空时聚合并注入，空列表时注入空列表而非 None。注：此任务为 T0-01 的前置，发现记录为零时不应阻塞报告生成，降级段落显示"今日无降级记录"。
- **测试隔离要求**: 新增 `get_tracker()` 单例后，**必须**在 `src/test/conftest.py` 中增加一个 `autouse` fixture 在每次测试前重置此单例（参考 `_auto_reset_provider_registry` 模式——调用 `get_tracker().reset()` 或新增 `_reset_tracker()` 函数），否则模块级单例状态会在测试间泄漏。受影响测试包括本任务的 record() 注入测试和 T0-01 的接线测试。

### T0-01-B: f_context Pre-Schema 文档 + 死键清理（现有管线键定义 + 类型断言，前置）
- **估时**: 2h
- **文件**: `docs-stm/plan/better-investment-advice/f_context-schema.md`（新建，Pre-Schema 部分）、`src/python/report/orchestrator.py`（初始断言 + 清理 f_context 死键）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 在 T0-01（DegradationTracker 接线）和 P1-06-A（f_context_builder 预重构）之前，先定义当前生产管线已有数据键的 Schema（Pre-Schema），**并清理 f_context 中的死键**。**注意：当前架构中"管线数据"分为两个独立通道——(A) `capture_snapshot()` 返回的 `f_context` 字典仅含 3 个键（`diff`、`diff_trimmed`、`days_since_last`），其中 `diff` 含 9 个子键（is_first_check、total_value_diff、total_value_diff_pct、total_pnl_diff、days_since_last_report、added/removed/increased/decreased）用于快照对比——这是 LLM 直接消费的唯一 f_context； (B) `prepare_report_data()` 返回的 `prep` 字典含 13 个键（details、total_mv、total_cost、total_profit、total_today_profit、categories、a_indices、us_indices、penetrated_assets、holdings_details、today_str、output_dir、news_top_count），以独立参数形式传入 `generate_all_llm()` 而非通过 f_context。Pre-Schema 文档必须同时覆盖两个通道的键定义，避免后续混淆。** 每个键标注：类型、所属通道（f_context / prep）、必选/可选标记、写入模块、消费模块、写入管线阶段。
- **死键清理（追加）**: 代码审计确认 `f_context["diff_trimmed"]`（L246, bool 值）和 `f_context["days_since_last"]`（L247, 与 `diff.days_since_last_report` 完全重复）在 f_context 注入后**没有任何下游 LLM generator 或 prompt 消费**，属于纯代码噪音。在 Pre-Schema 实施时直接删除这两个死键，保持 f_context 最小化。删除后 f_context 顶层仅保留 `"diff"` 一个键，与 Pre-Schema 文档的键定义一致，无向后兼容问题（下游 0 引用）。
- **类型断言（扩展）**: 同时在 orchestrator.py 各管线阶段之间插入初始类型断言 checkpoint（assert isinstance / .get() 类型守卫），开发期捕获类型不匹配。⚠ **生产环境运行时**：断言仅在 `__debug__` 模式下生效，但类型不匹配在生产中可能静默通过直到下游报错。措施：断言失败时额外通过 `logger.warning()` 记录结构化的类型不匹配日志（键名、期望类型、实际类型），确保即使生产环境无崩溃也可追踪到类型漂移。**时序要求**：必须在 T0-01 之前完成，使 T0-01 注入 data_degradation 键时已有类型校验框架。P1-21 的 Full Schema（Phase 1 新增键定义 + 全量校验扩展）在 Phase 1 补充。

### T0-01: DegradationTracker→LLM 接线
- **估时**: 4h
- **文件**: `src/python/report/orchestrator.py`（L198-248 `capture_snapshot` 构建 f_context 处注入）、`src/python/report/data_status.py`（L95 已实例化但未接）
- **阻塞**: 否
- **依赖**: T0-01-A（get_log 接口已就绪）、T0-01-B（Pre-Schema 已定义，f_context 键类型校验框架就绪）
- **描述**: `data_status.py` 的 `DegradationTracker` 已在 `fund_performance.py`/`penetration_sheet.py`/`summary.py` 中实例化并写入降级日志，但 `orchestrator.py` 的 `capture_snapshot()` 返回的 `f_context` 字典中**没有降级状态键**。新增 `f_context["data_degradation"]`，将当天所有 `DegradationTracker.log()` 记录汇总为结构化列表（数据源、降级级别、降级时间、原始错误摘要），使 LLM prompt 可以引用。

### T0-02: 数据质量告警注入 LLM（扩展校验项 3→5，移除缓存遍历项）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`（数据质量段落）`、`src/python/report/orchestrator.py`（数据质量统计字段）
- **阻塞**: 否
- **依赖**: T0-01（降级状态数据已进入 f_context）
- **描述**: 当前 LLM "健康检查" prompt 中只有 3 类数据质量提示（数据缺失、收益率异常、基准不一致）。扩展为 5 类（移除"缓存过期时间接近阈值"，因其需要遍历数百缓存文件解析 `_ts`，复杂度远超 prompt 修改范围，推迟至 Phase 4 缓存雪崩修复合并实现）：(1) 收盘价异常断点，(2) T2/T3 降级发生频次，(3) 基金净值更新延迟，(4) 分红数据状态，(5) 个别品种数据缺失时长。每类附带当前状态摘要（正常/警告/异常）。格式化为易读的一段，注入 health_check 系统提示语。同时修改 `orchestrator.py` 中的 `prepare_report_data()` 确保数据质量统计字段在管线中传递。

---

## MVP — 快速可见（零新数据源，~40h→+4h 条件推理，~44h）

### MVP-01: 收益归因计算与注入（Layer 2a）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`（新增收益归因段落）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 已有每品种 `profit`（盈亏金额），直接计算 `profit_contribution_i = profit_i / Σ|profit_j|`。按贡献降序排列，TOP 5 品种+占比格式化一段文本。注入 `expert_review` 和 `health_check` 两个 LLM prompt 的"收益来源"小节。格式示例："收益主要由 3 只品种贡献：贵州茅台(+32.5%)、腾讯控股(+18.2%)、招商银行(+12.1%)，合计占总收益 62.8%。" 注意正负号处理（亏损品种独立列出）。⚠ **边界处理**：当 Σ|profit_j| = 0（所有品种盈亏均为零）时返回空段落，LLM 显示"暂无收益归因数据"而非 ZeroDivisionError。

### MVP-02: 概念板块占比注入 LLM（Layer 2b）
- **估时**: 4h（MVP 阶段先做 Top 10 单品概念标注；聚合板块占比推迟到 Phase 2）
- **文件**: `src/python/llm/prompts.py`（新增概念板块段落）
- **阻塞**: 否（但隐式依赖 penetration 管线执行成功，若管线未执行则概念数据为空）
- **依赖**: 无（但隐式依赖 penetration.py 管线已执行——概念数据来自 push2 API，空数据时 prompt 应显示兜底文本而非空白段落）
- **描述**: `penetration.py` L700-701 已从东方财富 push2 行业 API 缓存了 `industry.concepts` 数据（概念板块分类），L747 已有 `concepts[:3]` 用于 Top 3 板块展示。但 LLM prompt 完全不提及板块分布。在 `expert_review` prompt 中新增段落：(1) 穿透后 Top 5 概念板块及持仓市值占比；(2) 集中度定性判断（高/中/低）；(3) 与常见市场风格（大盘/小盘/价值/成长）的对应关系。注意：(a) 非 A 股穿透资产（港股通/美股）天然无概念数据，需在 prompt 中标注"部分品种无概念分类"；(b) 概念数据不可用时显示"暂无概念板块数据"兜底文本，而非跳过整段导致 LLM 误以为无板块信息。MVP 阶段仅做穿透 Top 10 单品的概念标注（现有数据已够），聚合板块占比推迟到 Phase 2。如果概念 API（push2）熔断或返回空数据，LLM prompt 段落必须区分**三种状态**（R4-02 修正：原计划仅列 2 态，但代码实况验证发现 architecture 实际有 3 态——详见 discussion.md 风险表）：(1) API 不可达（熔断/网络错误）→ 显示'概念板块 API 暂时不可用，板块分析暂缺'，引用 DegradationTracker；(2) API 正常返回但数据为空（push2 返回了有效响应但某品种无概念条目）→ 显示'部分品种无概念分类'，**此态与状态 3 在架构上不可区分**——`batch_fetch_industry_data()` 会将全部非 A 股代码静默过滤（`industry.py L97` `a_codes = [c for c in valid_codes if _is_a_share_code(c)]`），返回空字典与 API 熔断返回空字典结果是相同的 `{}`，`penetration_sheet.py` 的 `build_penetration_data_status()` 始终硬编码 `failure_type="unreachable"` 写入 DegradationTracker（忽略 `result["industry_failure_type"]` 中的正确值 `"empty"`/`"unreachable"`）；(3) 港股通/美股穿透资产无概念数据（非 A 股代码被 `batch_fetch_industry_data()` 过滤——批次中全部为非 A 股时返回 `{}` 不可与状态 2b 区分）→ 显示'部分境外品种无概念分类'。引用 f_context['data_degradation'] 中的实时降级状态。港股通/美股穿透资产无概念数据的覆盖度说明也须在此段落标注。⚠ **额外发现**：`penetration_sheet.py` L148 的 `failure_type="unreachable"` 硬编码是一个独立缺陷——即使 push2 API 正常返回但概念数据为空（应触发 `empty_data_threshold=3`），也会被错误记为 `unreachable_threshold=2` 阈值。不属于 MVP-02 prompt 范围，应在 T0-01-A 或 Phase 1 时顺手修复。

### MVP-03: 再平衡极简版——单品种超阈值（Layer 3A 硬编码）
- **估时**: 6h（修正：原 16h 高估，纯计算+去重+测试 6h 合理）
- **文件**: `src/python/analysis/simple_rebalance.py`（新增）、`src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: 无
- **架构约束**: ⚠️ `simple_rebalance.py` 禁止导入 `report/` 包下的任何模块（仅消费 f_context 传入的数据），遵守 P1-22 的 `analysis/` 层定位——业务计算层只消费数据、不依赖报告层。新增模块必须 `from src.python.code_utils import ...` 而非 `from src.python.report.category import ...`。
- **描述**: 实现一个极简再平衡信号计算模块。规则：对每品种 `weight = market_value / total_value`，如果 `weight > 0.15`（硬编码阈值），输出建议："XX 持仓占比 23%，超出建议上限 15%，建议部分止盈至 10-15% 区间。" 无需配置系统、无需 Schema、无需用户画像。输出格式化为结构化列表 `[{code, name, weight, threshold, action}]`。注入 `expert_review` prompt 的"调仓建议"小节。包含三项低成本防护（不改 15% 硬编码阈值）：(1) 建议去重聚合——当超过 3 个品种同时触发时，输出一条汇总"您的组合集中度较高，有 N 个品种超过 15% 警戒线，建议整体考虑适度分散"，而非逐条列出；(2) 优先排序——按偏离幅度从大到小排序，仅输出 Top 3；(3) 单元测试包含基础断言（正常品种不触发、超阈值触发、极端情况）**以及"5 个品种均超过 15% 时只输出 1 条汇总建议"的断言**。测试用例标注 `@pytest.mark.unit_providers`，在 `conftest.py` 的 `pytest_configure` 中注册此 marker。

### MVP-04: 竞争语境极简版——组合 vs 沪深 300 收益对比（Layer 5 极简）
- **估时**: 8h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: 无
- **描述**: 已有 `benchmark.py` 计算的基准指数对比数据（含沪深300收益率序列）。在 `summary` prompt 中新增段落：(1) "年初至今 组合 +8.2% vs 沪深300 +5.1%"；(2) "近 1 年 组合 ... vs 沪深300 ..."；(3) 简单定性判断（跑赢/跑输/持平）。格式化为两列对比表。零新数据源、零后端改动。如果基准数据不可用（新账户无历史），显示"暂无足够历史数据"。

### MVP-05: LLM Prompt 整合串联
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: MVP-01、MVP-02、MVP-03、MVP-04
- **描述**: 将上述 4 个新增段落集中整合到 `prompts.py` 的对应 system prompt 常量中（`_SYSTEM_*`），确保：(1) 各段落间的逻辑顺序流畅（收益来源→板块分布→调仓建议→基准对比）；(2) 只有数据就绪的段落才输出（无数据时整段隐藏而非显示"--"）；(3) 不破坏现有 prompt 结构；(4) 数据质量降级段落（T0-02）如有内容，放在首段。运行一次全量集成测试（`python scripts/test_runner.py --mode regression`）确认不破坏现有报告。注：MVP-06（条件推理）的段落也纳入此轮整合，逻辑上放在所有段落的最后（情景分析章节）。

### MVP-06: 条件推理场景块（原 PD-01 提前）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: MVP-05（prompt 整合框架就绪后追加条件推理段落）
- **描述**: 在当前 prompt 末尾追加条件推理场景块，引导 LLM 输出两个情景分支的简要建议。不需对话架构，仅通过 prompt 指令实现。
- **验收标准**（R5-03 补充）: (1) 在 `expert_review` system prompt 末尾追加一段固定指令，明确要求 LLM 在回复末尾增加"### 情景分析"二级标题；(2) 该标题下必须包含两个子段落——"📈 上涨情景：如果未来市场上涨 20%，建议..."和"📉 下跌情景：如果未来市场下跌 20%，建议..."；(3) 每个子段落至少 2 句具体行动建议（非模板话术）；(4) 运行 `pytest src/test/ -m "unit" -x --tb=short -q` 确认不破坏现有 prompt 单元测试；(5) 手动验证方法：对同一个持仓数据，比较修改前后两次 LLM 回复——改前无情景分析段落，改后末尾应有上述结构的情景块。修改范围限制在 `prompts.py` 的 `_SYSTEM_EXPERT_REVIEW` 常量末尾追加内容，不修改任何 Python 逻辑代码，不修改其他 system prompt 常量。

---

## Phase 1 — 管线基础设施 + prompts.py 拆分（~164h）

### P1-01: Rf fetcher 主实现——东方财富 datacenter API
- **估时**: 12h
- **文件**: `src/python/fetcher/bond_yield.py`（新增）、`src/python/fetcher/chain.py`（L25 注册 `"bond_yield"` 链）
- **阻塞**: 是 ← PRE-01（API 可用）
- **依赖**: PRE-01
- **状态**: ❌ **已取消（PRE-01 验证 API 不可用）**
- **描述**: ~~新建 `bond_yield.py`，实现 `fetch_rf() → float` 从 `datacenter-web.eastmoney.com RPTBOND_BOND_YIELD_AND_SPREAD` 获取中国 10 年期国债收益率。配置参数：`RF_SOURCE="eastmoney"`，请求频率限制 1 次/小时（债券收益率日频足够）。返回年化收益率浮点数（如 0.0168）。包含：(1) 网络请求 + JSON 解析；(2) `provider_registry.py` 熔断器注册（T2）；(3) 缓存机制（TTL 日级+文件缓存）；(4) 错误处理（返回 None 触发降级）。`chain.py` 新增 `"bond_yield": ["eastmoney"]` 默认链。~~ **PRE-01（2026-07-20）验证：东方财富 datacenter API 所有 `RPTBOND_*` 报告名均返回"参数配置不对"，该 API 已不可用。取消本任务，工时释放。**

### P1-02: Rf fetcher 备用源——worldgovernmentbonds.com
- **估时**: 8h
- **文件**: `src/python/fetcher/bond_yield.py`
- **阻塞**: 是 ← PRE-01（备用源可联通性确认）
- **依赖**: P1-01（同一文件扩展）
- **状态**: ❌ **已取消（PRE-01 验证 JS 渲染不可解析）**
- **描述**: ~~在 `bond_yield.py` 中增加备用数据源 `worldgovernmentbonds.com`。当东方财富 API 失败时自动降级到该源。备用源返回格式不同，需单独解析逻辑。`chain.py` 中 `"bond_yield"` 链扩展为 `["eastmoney", "worldgovernmentbonds"]`。包含：(1) 备用源请求逻辑；(2) 返回格式对齐（统一为年化收益率浮点数）；(3) 降级日志（`DegradationTracker.log()`）；(4) **双源一致性仲裁规则**：偏差 ≤ 1.0% 时取均值，偏差 > 1.0% 时优先主源并记录降级至 DegradationTracker，偏差 > 2.0% 时回退到用户手动配置。~~ **PRE-01（2026-07-20）验证：`worldgovernmentbonds.com` 为 JS 动态渲染，不可直接抓取。取消本任务，工时释放。**

### P1-03: Rf 获取——`bond_zh_us_rate`（akshare/Sina）自动获取 + 用户手动配置兜底
- **估时**: 6h
- **文件**: `src/python/fetcher/bond_yield.py`（新增）、`src/python/config/_config_defaults.py`（新增 `risk_free_rate` 键）、`src/python/fetcher/chain.py`（L25 注册 `"bond_yield"` 链）
- **阻塞**: 是 ← PRE-01（数据源可用性确认）
- **依赖**: PRE-01
- **描述**: **替代已取消的 P1-01/P1-02**。新建 `bond_yield.py`，实现 `fetch_rf() → float` 通过 akshare `bond_zh_us_rate()` 获取中国 10 年期国债收益率（已验证 50/50 稳定性 100%）。配置参数：`RF_SOURCE="auto"`（默认自动，设为 `"manual"` 或提供浮点数则跳过 fetcher）。返回年化收益率浮点数（如 0.017404）。`chain.py` 新增 `"bond_yield": ["sina_bond_zh_us"]` 默认链。⚠ **C6 合规要求**：`bond_yield.py` 必须通过 `fetch_with_fallback()` 调用而非直接调用 akshare。需在 `src/python/providers/` 下新增 provider 模块（如 `sina_bond.py`）封装 akshare 调用，然后在 `bond_yield.py` 中通过 chain 路由。包含：(1) akshare 调用 + 数据提取（取 `中国国债收益率10年` 列最新值）；(2) `provider_registry.py` 熔断器注册（T2）；(3) 缓存机制（TTL 日级+文件缓存）；(4) 错误处理（连续 3 次失败触发手动配置兜底）；(5) 用户手动配置：修改 `_DEFAULT_CONFIG` 新增 `"risk_free_rate": None`（None 自动获取，设浮点数如 0.015 手动指定）；(6) DegradationTracker 降级日志注入；(7) registry.py _MODULE_REGISTRY 注册 `data_type="bond_yield"`，`cache_prefixes=("bond_yield_",)`。

### P1-04: 个股日收益率管线暴露
- **估时**: 8h
- **文件**: `src/python/report/portfolio_history.py`（L307-312 daily_returns 从局部变量→返回值）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 当前 `_compute_annualized_volatility()`（或等价函数）在 L307-312 计算 `daily_returns` 后仅用于计算年化波动率，计算结束后丢弃。修改：(1) 将 `daily_returns` 作为命名元组或字典字段加入返回值；(2) 同时在 `get_combined_timeseries()` L142 的返回字典中新增 `"daily_returns_individual": dict[str, list[float]]`（按品种代码索引的日收益率列表）；(3) 保证返回格式与下游消费一致（列表与日期序列对齐）；(4) 向后兼容：原有键不变，新键为 optional。
- **数据质量自检（验收标准）**: P1-04 是被 10 个下游任务依赖的"致死率最高"模块——P1-05, P2-05, P2-06, P2-10, P2-11, P2-12, P2-13, P4-02, PD-02 均依赖个股日收益率数据。交付前必须手动校验至少 10 个品种的 `daily_returns` 计算结果：随机选取 10 个品种，验证最近交易日收益率 = (今收 - 昨收) / 昨收，确认日期对齐无误。校验记录附在代码注释或 PR 描述中。验收标准从"代码编译通过"提升为"pass 数据质量校验"。
- **⚠ K-line API 降级一致性修复（R4-03 修正——验证后决定简化）**：当前腾讯 K 线 API（web.ifzq.gtimg.cn）使用 `fetch_with_incremental_fallback`（过期缓存兜底），新浪 K 线（money.finance.sina.cn）使用 `fetch_with_fallback`（空列表降级）。二者在"数据过期"场景下的行为不一致——腾讯返回过期数据 + 日志告警，新浪返回空列表。日收益率管线消费的成交额和收盘价字段需要统一降级语义。**但代码实况验证（2026-07-20）发现**：(1) 两个 provider 的 `fetch_kline` 输出格式已统一（均返回 `[{date, open, close, high, low, volume}]` 格式），无需额外适配器归一化格式；(2) `_unify_kline_fallback()` 作为全新函数名不存在于代码库中——该名称为计划假设，是否需要创建取决于实现期对 `fetch_with_incremental_fallback` 和 `fetch_with_fallback` 在"最新数据 vs 过期兜底"语义差异的实际测试。**建议**：P1-04 实现时先验证两种 fallback 函数在测试中的实际行为差异。如果 `fetch_with_incremental_fallback` 在腾讯 K 线过期时确实返回过期数据而 `fetch_with_fallback` 返回空列表，则仅在 `portfolio_history.py` 的消费点做一行 `if not data: data = stale_fallback` 即可，无需专用 `_unify_kline_fallback()` 函数。将原估算的 2h 适配器专项缩减为 0.5h 验证+简单处理。

### P1-05: 组合日收益率暴露
- **估时**: 4h
- **文件**: `src/python/report/portfolio_history.py`（`get_combined_timeseries` 返回字典 L350-366 附近）
- **阻塞**: 否
- **依赖**: P1-04（个股日收益率已暴露，组合日收益率 = 市值加权平均）
- **描述**: 在 `get_combined_timeseries()` 返回字典中新增 `"daily_returns_portfolio": list[float]`（组合每日收益率序列）。计算方式：(1) 每交易日各品种日收益率 × 前日市值权重 → 加权和；(2) 注意无数据日（停牌、休市）用前值填充或标记 NaN；(3) 与 `"daily_returns_individual"` 共享相同日期对齐索引。

### P1-06-A: orchestrator.py f_context 组装逻辑抽取（预重构）
- **估时**: 8h
- **文件**: `src/python/report/orchestrator.py`（拆分）、`src/python/report/f_context_builder.py`（新增）
- **阻塞**: 否
- **依赖**: 无
- **描述**: orchestrator.py 当前 ~778 行，P1-06~P1-09 四个阻断点修复将使其超过 900 行。新增的 f_context 键（risk_metrics、portfolio_daily_returns、data_degradation 等）同时被多个消费方使用，需要统一的数据合并点和类型断言。实施：(1) 将 f_context 字段组装逻辑从 orchestrator.py 抽取到独立的 f_context_builder.py 模块，定义 `build_f_context(...) → dict` 和 `_merge_f_context(...) → dict` 函数作为所有管线数据的统一注入点；(2) 在每个管线阶段之间增加类型断言 checkpoint（assert isinstance），开发期捕获类型不匹配；(3) 断言失败时记录结构化日志而非直接崩溃（携带期望类型、实际类型、键名），方便调试。此任务完成后，orchestrator.py 仅保留管线调度（调用顺序编排），不再直接处理数据组装。

### P1-06: 管线阻断点 1——prepare_report_data 加 risk_metrics 键
- **估时**: 4h
- **文件**: `src/python/report/f_context_builder.py`（P1-06-A 已拆分至此）
- **阻塞**: 否
- **依赖**: P1-06-A（f_context_builder 已存在）
- **描述**: `prepare_report_data()` 当前返回 12 个字段（含 market_data、fund_data、summary 等），但没有 `risk_metrics` 键。新增 `"risk_metrics": {}` 空字典占位，供 Phase 2 的 `metrics.py` 填充。此步骤只保证键存在、管线不报 KeyError，值为空字典。同时修改下游消费方（`capture_snapshot`、Excel writer、HTML writer），在读取 `risk_metrics` 时用 `.get("risk_metrics", {})` 确保兼容。

### P1-07: 管线阻断点 2——capture_snapshot f_context 加风险字段
- **估时**: 4h
- **文件**: `src/python/report/orchestrator.py`（L140 `capture_snapshot` 构建 f_context）
- **阻塞**: 否
- **依赖**: P1-06（prepare_report_data 已有 risk_metrics）
- **描述**: `capture_snapshot()` 的 `f_context` 字典新增风险指标相关键：(1) `"risk_metrics"` 从 `prepare_report_data` 透传；(2) `"portfolio_daily_returns"` 从 `portfolio_history.get_combined_timeseries["daily_returns_portfolio"]` 透传（P1-05）；(3) `"data_degradation"` 汇总（T0-02 已完成）；(4) 保险：所有新键 `.get()` 兜底，不因数据缺失阻塞报告生成。
- **⚠ 双路径覆盖（R4-06）**：`orchestrator.py` 有两条报告生成路径——`_generate_report_full`（L650, 含 LLM）和 `_generate_report_both`（L394, 仅 HTML+Excel）。前者调用 `prepare_report_data()` 获取完整数据，后者调用轻量的 `_compute_details()`（L378）。P1-06 修改 `prepare_report_data` 只覆盖 full 路径。P1-07 修改 `capture_snapshot` 返回的 f_context 则同时覆盖两路径（两条路径都调用 `capture_snapshot`）。需确保：(a) `capture_snapshot` 注入的新键（risk_metrics 等）在 both 路径下也能正确初始化（来自 prep dict 的字段在 both 路径中不可用，需降级为空字典）；(b) 测试用例同时覆盖 both 和 full 路径。

### P1-08: 管线阻断点 3——generate_all_llm 暴露 history_data
- **估时**: 4h
- **文件**: `src/python/llm/generators_orchestrator.py`（L470 `generate_all_llm`）
- **阻塞**: 否
- **依赖**: P1-07（f_context 已含风险字段）
- **描述**: `generate_all_llm()` 目前接收 `f_context` 但不把 `history_data` 传给 prompt 构建函数。修改调用链：(1) 确保 `portfolio_history` 数据作为 `f_context["portfolio_history"]` 传递；(2) 包含 `daily_returns_individual`、`daily_returns_portfolio`、`drawdown`、`benchmark_comparison` 等时序字段；(3) 修改 `prompts.py` 的 `build_system_prompt()` 签名，增加 `history_data` 形参（当前没有）。

### P1-08-B: prompts.py 拆分为三文件（从 Phase 3 提前，避免被 18 个任务反复修改冲突）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py` → 拆分为 `prompts_core.py`（角色定义+安全约束）、`prompts_tables.py`（数据表格格式化）、`prompts_action.py`（行动建议模板）
- **阻塞**: 否
- **依赖**: P1-08（build_system_prompt 签名已变更，拆分时一并处理新签名）
- **描述**: `prompts.py` 当前单文件约 200 行，承载 5 个 system prompt + 所有数据格式化逻辑。拆分为三个文件，保持统一导入入口（`prompts.py` re-export）。拆分标准：(1) 角色定义、安全约束、回复格式 → `prompts_core.py`；(2) 所有数据表格格式化函数 → `prompts_tables.py`；(3) 行动建议模板、信号置信度段落 → `prompts_action.py`。不改变现有调用方接口。此任务将 P3-14（原 Phase 3 的拆分任务）提前到 Phase 1 紧接 P1-08，避免 Phase 2/3/4 共 18 个任务在单一大文件上反复冲突。

### P1-09: 管线阻断点 4——generators.py _fingerprint 含风险信号 Hash
- **估时**: 4h
- **文件**: `src/python/llm/generators.py`（L53/89/143/196 四个 `_fingerprint` 方法）
- **阻塞**: 否
- **依赖**: P1-06（risk_metrics 键存在）
- **描述**: LLM 请求去重依赖 `_fingerprint()` 哈希。当前 fingerprint 只覆盖基础数据字段，不等同数据变更时不会触发重新生成。在各 `_fingerprint()` 的哈希输入中增加：(1) `risk_metrics` 的 JSON 摘要；(2) `data_degradation` 状态摘要；(3) `portfolio_daily_returns[-1]`（最近一日收益率，轻量级变更检测）。字段不存在时静默跳过（向后兼容）。⚠ **额外发现（R3-04）**：当前 expert_review 和 health_check 的 `_fingerprint()` 不包含 `f_context["diff"]`——持仓快照对比数据变化（added/removed/increased/decreased）不会触发重新生成，新一期报告的 LLM 回复可能仍引用旧的持仓变动数据。本任务也应将 `f_context["diff"]` 的 JSON 摘要纳入 expert_review 和 health_check 的 fingerprint 哈希输入。

### P1-10: 数据模块注册——registry.py 注册新模块 + _COMPUTATION_REGISTRY 创建
- **估时**: 8h
- **文件**: `src/python/registry.py`
- **阻塞**: 否
- **依赖**: P1-03（bond_yield 模块存在）、P1-04（日收益率管线存在，但注册本身不依赖内容）
- **测试**: unit（`pytest src/test/unit/test_registry.py -x -q`）
- **描述**: 为 bond_yield 数据模块在 _MODULE_REGISTRY 中注册 DataModuleDef（data_type='bond_yield', cache_prefixes=('bond_yield_',), cache_ttl=CACHE_DAILY, cache_groups=('preload',)）。**同时创建 _COMPUTATION_REGISTRY（计算模块注册表）**——定义 ComputModuleDef 结构（name、settings_key、dependencies 等字段，不含缓存属性），用于后续无缓存需求的算法模块（如 P3-16 事实校验器纯算法层、P4-01 情景分析、P5-01 画像推断）的注册。在 technical.md §6.2 中追加 _COMPUTATION_REGISTRY 说明。写测试验证 ComputModuleDef 的正确性和唯一性约束。
- **⚠ C17 注册缺口（R5-04 补充）**: 以下 6 个分析模块在任务分解中**没有对应注册任务**，它们的 ComputModuleDef 注册应在此任务中预留位置，各模块实际创建时补充注册代码：
  1. metrics.py（P2-01~P2-11 共 8 个指标）— 注册名 `analytics_metrics`
  2. liquidity.py（P3-11~P3-12）— 注册名 `analytics_liquidity`
  3. fx_exposure.py（P3-13）— 注册名 `analytics_fx_exposure`
  4. scenario.py（P4-01~P4-03）— 注册名 `analytics_scenario`
  5. alignment_correction.py（P3-09b）— 注册名 `analytics_alignment`
  6. inferrer.py（P5-01）— 注册名 `analytics_inferrer`
  这些模块的任务描述中已标注"包含 registry.py _COMPUTATION_REGISTRY 注册"。

### P1-11: 功能开关注册 JSON Schema（18 开关）
- **估时**: 12h
- **文件**: `src/python/config/_config_defaults.py`（扩展）、`src/python/config/config_manager.py`（添加校验）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 新建 Feature Flag 体系：在 `config.json` 中新增 `"feature_flags"` 对象，包含 18 个布尔开关（每个 Layer/功能一个）。开关列表：(1) rf_auto_fetch, (2) daily_return_pipeline, (3) risk_metrics, (4) metrics_sharpe, (5) metrics_calmar, (6) metrics_hhi, (7) metrics_winrate, (8) metrics_turnover, (9) metrics_risk_contribution, (10) metrics_beta, (11) drawdown_warning, (12) rebalance_simple, (13) rebalance_full, (14) competitive_context, (15) liquidity_warning, (16) fx_exposure, (17) user_profile, (18) llm_fact_check。每个开关有默认值 + 简短说明。提供 `is_feature_enabled(name) → bool` 函数。开关关闭时，对应数据字段传空值而非阻断管线。

### P1-12: 指标级断路包装器
- **估时**: 12h
- **文件**: `src/python/analysis/circuit_breaker_wrapper.py`（新增）
- **阻塞**: 否
- **依赖**: P1-11（feature_flags 系统已就绪）
- **描述**: 为每个风险指标计算函数包裹断路逻辑（指标级断路器，非网络请求级）。包装器行为：(1) 单指标连续失败 3 次 → 该指标静默 24h（返回 None）；(2) 失败计数存文件（`data/cache/metrics_breaker.json`），跨会话持久；(3) 成功调用重置计数；(4) 结合 Feature Flag：如果 `feature_flags.metrics_sharpe == false`，直接返回 None 不走计算；(5) 所有断路事件记录到 `DegradationTracker`。
- **测试隔离要求**: `metrics_breaker.json` 持久化路径必须设计为可注入（通过构造函数参数或 config），以便测试时通过 `monkeypatch.setattr` 重定向到 `tmp_path`。《=无需新增 conftest.py 的 autouse，但在编写测试时必须手动确保使用了临时路径。
- **C20 约束（Feature Flag ↔ Circuit Breaker 交互）**：在 P1-12 实施时强制增加以下联动逻辑——(a) **Feature Flag 关闭期间不计断路失败次数**：`metrics_sharpe = false` 时该指标不参与熔断计数，避免"开关关闭期间指标未运行"被误计入失败；(b) **Feature Flag 打开时自动重置断路器状态**：当 `metrics_sharpe` 从 false 切为 true 时，清空该指标的历史失败计数和冷却剩余时间，以"干净状态"重新开始计算——防止旧失败记录导致新开关打开后指标立即进入冷却期；(c) **Feature Flag 变更事件记录到 DegradationTracker**：每次 Feature Flag 发生状态变更时（无论 open→close 或 close→open）记录变更日志，方便运维排查"为何某指标突然可算/不可算"。三条规则统一封装在 `is_feature_enabled()` 函数中，由该函数触发断路检查和状态重置，调用方透明。

### P1-13: 持仓匿名化最小版
- **估时**: 8h
- **文件**: `src/python/anonymizer.py`（新增）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 实现最小可行匿名化模块：(1) 选项 A：将品种名称替换为"品种 A/B/C..."（保留代码和盈亏数据）；(2) 选项 B：保留名称但模糊持仓数量（乘以 ±5% 随机扰动）；(3) 选项 C：关闭（默认）。在 CLI/TUI 中增加 `--anonymize` 参数或配置项。匿名化仅在报告生成阶段生效，不修改原始持仓文件。出口：`anonymize(holdings_data, mode: str) → holdings_data`。

### P1-14: 缓存文件权限保护
- **估时**: 4h
- **文件**: `src/python/cache.py`（写缓存时设置权限）
- **阻塞**: 否
- **依赖**: 无
- **描述**: `cache.py` 写文件缓存时设置 `0o600`（仅所有者读写）。Windows 上用 `os.chmod` 模拟最小权限。启动时检查 `data/cache/` 目录权限，不符合则告警。注意不影响程序正常读写（仅防其他系统用户读取缓存中的持仓/净值数据）。

### P1-15: Rf fetcher 测试用例
- **估时**: 4h（缩减，因 P1-01/P1-02 取消、链路简化）
- **文件**: `src/test/unit/test_bond_yield.py`（新建）
- **阻塞**: 否（数据源已验证可用，可直接写测试）
- **依赖**: P1-03（bond_yield 模块存在）
- **描述**: 为 `bond_yield.py` 编写测试用例：(1) mock `bond_zh_us_rate()` 正常返回包含中国 10Y 收益率的数据帧 → 断言提取值为 0.017404；(2) mock akshare 异常 → 断言降级到用户配置；(3) mock 用户配置 Rf=0.02 → 断言跳过 fetcher 直接返回 0.02；(4) 缓存命中测试（第二次调用不触发网络请求）。标注 `@pytest.mark.unit_providers` 并注册 marker。

### P1-16: 管线集成测试——4 个阻断点冒烟测试
- **估时**: 8h
- **文件**: `src/test/scenario/test_pipeline_blocking_points.py`（新建）
- **阻塞**: 否
- **依赖**: P1-06、P1-07、P1-08、P1-09（所有阻断点已修复）
- **描述**: 新增冒烟测试覆盖 4 个阻断点：(1) `prepare_report_data` 返回字典含 `risk_metrics` 键；(2) `capture_snapshot` f_context 含风险字段且 `.get()` 安全；(3) `generate_all_llm` 不因缺失 `history_data` 崩溃；(4) `_fingerprint` 哈希输入含风险摘要且旧版本无此字段时不报错。使用最小持仓 fixture（2-3 品种），快速执行（<30s）。运行 `--mode regression` 确认通过。标注 `@pytest.mark.scenario_basic`。
- **测试隔离要求**: (a) **输出目录隔离**——必须将 `reports/` 输出目录重定向到 `tmp_path`（使用 `monkeypatch.setattr` 或 fixture），避免测试报告残留在生产 `reports/` 目录；(b) **LLM 调用 mock**——`generate_all_llm` 的测试必须 mock LLM API 调用（`unittest.mock.patch`），防止真实调用产生费用和 API 依赖；(c) **输入数据隔离**——持仓数据必须使用 fixture 构造（2-3 品种的简单持仓），不得依赖 `data/holdings/` 的真实文件；(d) **单例重置**——测试涉及 DegradationTracker 的，需调用 `get_tracker().reset()` 清理状态。

### P1-17: 熔断器改进——指数退避
- **估时**: 4h
- **文件**: `src/python/llm/circuit_breaker.py`（L24-25 固定 60s → 指数退避）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 当前 `circuit_breaker.py` 熔断策略：3 次失败 → 冷却 60s → 半开 → 重试。改为指数退避：第 1 次 60s、第 2 次 300s、第 3 次 900s、第 4+ 次 3600s（上限）。成功调用立即重置退避指数。修改 `CircuitBreaker` 类新增 `_backoff` 属性和 `_next_cooldown()` 方法。

### P1-18: 熔断器改进——持久化
- **估时**: 4h
- **文件**: `src/python/llm/circuit_breaker.py`（新增文件持久化）
- **阻塞**: 否
- **依赖**: P1-17（指数退避已实现）
- **描述**: 当前 `circuit_breaker.py` 熔断状态在内存（L27-28 `_breakers: dict`），程序重启后丢失。新增：(1) 状态持久化到 `data/cache/circuit_breaker.json`；(2) 启动时反序列化恢复；(3) 每次状态变更（熔断/半开/关闭）写回；(4) TTL 清理：超过 24h 的熔断记录视为过期移除。保证读写安全（文件锁或原子写入）。
- **测试隔离要求**: `circuit_breaker.json` 持久化路径必须作为 `CircuitBreaker` 的可选构造参数（默认值 `data/cache/circuit_breaker.json`，测试时注入 `tmp_path` 路径），或在 `_isolate_sensitive_paths` 中通过 `monkeypatch.setattr` 重定向。必须编写测试验证：持久化写入后可恢复、TTL 过期后恢复为空、并发写入不损坏文件。

### P1-19: 双熔断器统一网关
- **估时**: 4h
- **文件**: `src/python/circuit_breaker_gateway.py`（新增，统一 `circuit_breaker.py` 和 `provider_registry.py`）
- **阻塞**: 否
- **依赖**: P1-18（持久化熔断器已实现）
- **描述**: 当前 `circuit_breaker.py`（LLM 请求，60s 冷却）和 `provider_registry.py`（数据源请求，300s 冷却）各自独立，运维复杂度高。新增统一网关层：(1) 定义 `BreakerConfig(max_failures, cooldown_seconds, backoff_factor)` 两种预设；(2) `CircuitBreakerGateway.get("llm")` 和 `.get("data_source")` 返回各自实例；(3) 统一监控接口 `gateway.summary()` 输出所有断路器状态表格；(4) 向后兼容：旧导入路径不变（`from src.python.llm.circuit_breaker import circuit_breaker` 仍可用，委派给网关）。

### P1-20: LLM 失败自动降级模板（P0 优先级，堵塞管线断裂风险）
- **估时**: 8h（1天）
- **文件**: src/python/report/orchestrator.py（LLM 生成流程）、src/python/report/progress.py
- **阻塞**: 否
- **依赖**: 无（独立于其他 P1 任务，可并行）
- **描述**: 实施 LLM 完全不可用时的报告降级机制：(1) 在 orchestrator.py 的 generate_all_llm() 中捕获 LLM 异常，所有 4+1 个 LLM 模块均失败时自动终止 LLM 生成流程，不阻塞报告管线；(2) 在 info 字典中增加 llm_status 键（success/failed/degraded），下游 HTML/Excel 生成器据此决定是否显示 LLM 板块；(3) full 路径中 LLM 失败时自动转为 both 路径产出（含 LLM 占位文本"智能分析暂时不可用，请稍后重试"）；(4) 将 LLM circuit_breaker 状态暴露到 DegradationTracker，在报告页脚展示 LLM 状态摘要（正常/熔断中/冷却剩余时间）；(5) 验证 LLM 预检：每次生成前做一次轻量连通性测试。验收标准：mock LLM API 全部返回 503，验证 full 报告正常生成（HTML 含 LLM 占位文本，Excel 跳过 LLM 页签）。
- **⚠ 遗留路径覆盖（R4-07）**：`html_renderers.py` L496-508 有一段遗留回退代码，在 `llm_content` 未预先计算时直接调用 `generate_all_llm`——**此路径不传递 `f_context`**。当前 TUI 已通过 `orchestrator.generate_report()` 路由，正常情况下不触发此遗留路径。P1-20 应检查并清理此遗留路径，确保所有 LLM 调用都经过 `orchestrator.py` 的统一降级逻辑。否则降级机制覆盖不全。

### P1-21: f_context Schema 文档——Phase 1 Full Schema 补充 + 校验层扩展
- **估时**: 6h（Pre-Schema 2h 已由 T0-01-B 完成，此处仅补充 Phase 1 新增键的 Full Schema 定义）
- **文件**: `docs-stm/plan/better-investment-advice/f_context-schema.md`（扩展 Full Schema 章节）、`src/python/report/orchestrator.py`（校验层扩展）
- **阻塞**: 否
- **依赖**: P1-06, P1-07, P1-08
- **描述**: T0-01-B 已完成 Pre-Schema（现有管线键的定义 + 初始类型断言）。本任务在 Pre-Schema 基础上补充 Full Schema：(1) 在 f_context-schema.md 中追加 Phase 1 新增键的定义（risk_metrics、portfolio_daily_returns、data_degradation、feature_flags 等约 8 个键），与 Pre-Schema 合并在同一文档中，用"Phase"列区分归属；(2) 扩展 orchestrator 中的类型断言 checkpoint 覆盖这些新键；(3) f_context-schema.md 纳入项目文档，每次新增 f_context 键时必须同步更新。

### P1-22: analysis/ 层定位与模块依赖规范
- **估时**: 12h（含 8h category.py 提取到 code_utils.py + 2h technical.md/folders.md 更新 + 2h 验证所有消费点导入路径变更）
- **文件**: `src/python/code_utils.py`（扩展）、`src/python/report/category.py`（削减）、`docs-stm/managements/technical.md`（§模块依赖关系）、`docs-stm/managements/folders.md`
- **阻塞**: 否
- **依赖**: 无（但 P3-06、P3-13 均需此任务完成后才能正确导入 code_utils.py 而非 category.py）
- **描述**: (1) 在 technical.md 中明确定义 analysis/ 为"业务计算层"——消费 report/ 的输出（资产分类等）做分析计算，不得反向修改 report/ 的内部逻辑；(2) 将 report/category.py 中的 `_categorize_holding()`（第 62-116 行，7 条规则的组合分类器）提取到 code_utils.py 作为公开函数 `categorize_holding()`（符合 C1 中心化原则），使 analysis/ 和 report/ 均从 code_utils.py 导入分类函数，消除 analysis→report 的逆向依赖。注意 code_utils.py 已包含所有底层谓词（is_bond_fund_by_name、is_otc_fund_by_name、is_money_fund_by_name 等，无需重复提取），`_categorize_holding` 是唯一缺失的分类组合逻辑。同时币种分类（CNY/HKD/USD）也应提取到 code_utils.py 新增 is_hkd_denominated()、is_usd_denominated() 函数；(3) 确认所有消费点的导入路径变更（grep 所有 import category.py 的模块）并更新；(4) 在 folders.md 中更新 analysis/ 目录描述说明其分层定位；(5) 更新 registry.py _MODULE_REGISTRY 的注释说明该表仅用于有缓存的数据模块，计算模块不注册于此。

---

## Phase 2 — 量化信号全面激活（~140h）

> **说明**: P2-11 拆分为 P2-11a（Beta 点估计 16h 留 Phase 2）和 P2-11b（置信区间 24h 移至 Phase 4）。新增 P2-14-B 集成测试（8h）验证 Phase 2 指标在 Phase 1 管线中的完整流转。

### P2-01: 夏普比率算法
- **估时**: 8h
- **文件**: `src/python/analysis/metrics.py`（新增，~500-700 行，含截断保护、置信区间、边界处理）
- **阻塞**: 是 ← P1-03（Rf fetcher） + P1-05（组合日收益率）
- **依赖**: P1-03、P1-05
- **描述**: 实现 `sharpe_ratio(portfolio_daily_returns, rf_annual) → float | None`。公式：`(年化组合收益率 - 无风险利率) / 年化波动率`。年化因子 √252。Rf 不可用时返回 None（输出"--"）。边界处理：(1) 年化波动率趋近 0 → 返回 None；(2) 不足 20 个交易日 → 返回 None（统计意义不足）；(3) 负夏普正常返回（选告风险调整后为负）。

### P2-02: 卡玛比率算法
- **估时**: 4h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: P1-05（组合日收益率，用于计算最大回撤）
- **描述**: 实现 `calmar_ratio(portfolio_daily_returns) → float | None`。公式：`年化收益率 / 最大回撤`。最大回撤同期间（1 年 / 全部历史）。边界处理：最大回撤 < 0.1% → None（分母太小无意义）。

### P2-03: HHI 集中度指数算法
- **估时**: 4h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: 无（现有 market_value 直接可算）
- **描述**: 实现 `hhi(weights: list[float]) → float`。公式：`Σ(w_i)²`，其中 `w_i = market_value_i / total_value`。范围 [0, 1]（1=完全集中)。附加输出：等效集中品种数 `1/HHI`（如 HHI=0.25 等效=4 只）。LLM 可据此判断："组合等效持有 N 只不相关品种"。

### P2-04: 持仓胜率算法
- **估时**: 4h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: 无（现有 profit 直接可算）
- **描述**: 实现 `win_rate(holdings) → float`。公式：`盈利品种数 / 总持仓品种数`。边界：空持仓 → None。附加：盈利/亏损品种列表（用于 LLM 逐只点评）。

### P2-05: 换手率算法
- **估时**: 4h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: P1-04（个股日收益率，用于日均市值计算）
- **描述**: 实现 `turnover_rate(holdings, period_changes) → float`。公式：`期间买入+卖出总额 / 期间平均总市值`。期间对应报告区间（快照间隔）。如果期间变动明细不可用，返回 None。

### P2-06: 持仓风险贡献算法
- **估时**: 6h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: P1-04（个股日收益率，用于 σ 计算）
- **描述**: 实现 `risk_contribution(weights, volatilities) → list[tuple[str, float]]`。公式：`RC_i = w_i × σ_i / Σ(w_j × σ_j)`（简化版，非 Euler 分解）。返回按贡献降序排列。个股 σ 用日收益率 std×√252。如果个股日收益率不可用，降级为权重等比例分配（仅告警不报错）。LLM 使用："组合最大风险源是 XX，贡献了 YY% 的波动风险。"

### P2-07: 分红历史数据接入 fund_performance + LLM prompt
- **估时**: 4h
- **文件**: `src/python/report/fund_performance.py`（扩展，接入分红数据）、`src/python/llm/prompts.py`（提及分红信息）
- **阻塞**: 否
- **依赖**: 无（分红数据已在 `registry.py` 注册但未在生成管线中传递）
- **描述**: 原文 §1.2 指出"分红历史已注册但未接入生成管线"。实施：(1) 在 `fund_performance.py` 的汇总字段中追加 `dividend_yield`（股息率 = Σ分红 / 当前市值）；(2) 在 `expert_review` prompt 中增加一则提示："当前持仓综合股息率 X.X%，其中高分红品种（>3%）为：列表"；(3) 注：分红数据来自 AkShare，T4 级别（失败显示"--"），此接入不应依赖分红数据完整可用。

### P2-08: metrics.py 整合与接口定义
- **估时**: 2h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: P2-01、P2-02、P2-03、P2-04、P2-05、P2-06（所有单指标函数已实现）
- **描述**: 在 `metrics.py` 中编写统一入口函数 `compute_all_metrics(f_context) → dict[str, Any]`，依次调用各指标函数，组装为一个扁平字典。key 命名规范：`sharpe_ratio`、`calmar_ratio`、`hhi`、`win_rate`、`turnover_rate`、`risk_contributions`、`beta`。不可计算的指标 key 值为 None。统一入口供 `orchestrator.py` 单点调用。**⚠ 注册要求**：包含 `registry.py _COMPUTATION_REGISTRY` 注册（注册名 `analytics_metrics`，由 P1-10 预留位置）。

### P2-09: 截断保护与极端值处理
- **估时**: 8h
- **文件**: `src/python/analysis/metrics.py`
- **阻塞**: 否
- **依赖**: P2-08（metrics.py 已有完整接口）
- **描述**: 为 `compute_all_metrics()` 添加全局截断保护层：(1) NaN/Inf 静默过滤为 None；(2) 极端值截断（夏普绝对值 > 10、HHI > 1.0 等物理不可能值强制设为 None）；(3) 疑似数据错误的品种标记（如单日收益率 > 20% 无分红/拆股记录时告警）；(4) 各指标输出均包含 `confidence` 字段（high/medium/low，基于数据天数和缺失率判断）。

### P2-10: 个股波动率计算
- **估时**: 8h
- **文件**: `src/python/analysis/metrics.py`（新增函数）
- **阻塞**: 否
- **依赖**: P1-04（个股日收益率已在管线中）
- **描述**: 实现 `individual_volatility(individual_daily_returns) → dict[str, float]`。对每品种计算 `年化波动率 = std(daily_returns) × √252`。输出 `{code: annualized_vol}` 字典。不足 20 个交易日的品种返回 None。为风险贡献（P2-06）、Beta（P2-11）、回撤预警（P2-12）提供基础数据。

### P2-11a: 组合 Beta 算法——Beta 点估计（协方差法）
- **估时**: 16h（2 天——高复杂度指标，含协方差计算、日期对齐、边界处理）
- **文件**: `src/python/analysis/metrics.py`（新增 `portfolio_beta` 函数）
- **阻塞**: 是 ← P1-05（组合日收益率就绪）
- **依赖**: P1-04、P1-05、P2-10（个股/组合日收益率 + 基准收益率）
- **描述**: 实现 `portfolio_beta(portfolio_returns, benchmark_returns) → float | None`。方法：协方差法 `β = Cov(Rp, Rb) / Var(Rb)`。窗口期默认为最近 252 个交易日（约 1 年），可配置。流程：(1) 获取组合日收益率序列；(2) 获取基准指数日收益率序列（沪深300已存在）；(3) 对齐日期索引（取交集）；(4) 计算协方差/方差。边界：(1) 不足 20 个对齐交易日 → None；(2) 基准收益率全为零（休市/停牌）→ None。Beta 解读注入 LLM："组合 Beta = 1.2，意味着市场每涨跌 1%，组合平均波动 1.2%。" **注意：此任务仅做点估计，95% 置信区间移至 P2-11b（P4-01 前置）。**

### P2-12: 回撤历史分位预警——滚动 1 年（Layer 3B）
- **估时**: 18h
- **文件**: `src/python/analysis/metrics.py`（新增 `drawdown_percentile` 函数）
- **阻塞**: 否
- **依赖**: P1-04（个股日收益率管线就绪）
- **描述**: 实现滚动 1 年回撤历史分位计算：(1) 对每品种，取近 252 个交易日的每日净值（收盘价×份额+累计分红）；(2) 计算该窗口内的滚动最大回撤序列；(3) 当前回撤值 ÷ 历史最大回撤 = 分位数；(4) 输出 `{code: {current_drawdown, max_drawdown, percentile, days_in_drawdown}}`。LLM 使用："XX 品种当前回撤处于近 1 年最大回撤的 85% 分位，接近历史极限区域。"

### P2-13: 回撤历史分位预警——全历史（Layer 3B）
- **估时**: 18h
- **文件**: `src/python/analysis/metrics.py`（扩展 drawdown_percentile）
- **阻塞**: 否
- **依赖**: P2-12（1 年版本已实现）
- **描述**: 在 P2-12 基础上扩展到全历史窗口：(1) 对每品种，取全部可用历史数据；(2) 如果全历史 > 3 年，同时计算 1 年 + 3 年 + 全历史三个时间窗口的分位数；(3) 输出增加窗口标记。LLM 使用综合判断："XX 品种当前回撤处于全历史最大回撤的 72% 分位（近 1 年 85% 分位），提示短期压力大于长期。"

### P2-14: LLM Prompt 注入——指标表
- **估时**: 8h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P2-08（metrics.py 统一接口就绪）、P1-08（history_data 已暴露）
- **描述**: 在 `expert_review` 系统提示语中插入结构化指标表段。格式：三列表格（指标名、组合值、基准值/参考范围）。包含字段：夏普比率、卡玛比率、组合 Beta、HHI、持仓胜率、换手率、年化波动率、最大回撤。基准值来自沪深300对应周期计算。无对应基准的字段（如 HHI）标注"——"或给出参考解释。指标值 None 时显示"--"。

### P2-14-B: Phase 2 → Phase 1 管线集成测试（验证指标数据全链路流转）
- **估时**: 8h
- **文件**: `src/test/scenario/test_pipeline_metrics_flow.py`（新建）
- **阻塞**: 否
- **依赖**: P2-14（LLM 注入就绪）、P1-08（history_data 管线就绪）、P2-08（metrics.py compute_all_metrics 就绪）
- **描述**: 模拟完整管线执行，验证 Phase 2 指标数据在 Phase 1 管线中正确流转：(1) 创建最小持仓 fixture（3 品种 + 模拟日收益率序列）；(2) 执行完整管线：`prepare_report_data` → `capture_snapshot` → `compute_all_metrics` → `build_system_prompt`（含指标表）；(3) 断言 `compute_all_metrics()` 返回值中的每个指标（sharpe_ratio、calmar_ratio、hhi、win_rate、turnover_rate、risk_contributions、beta）在 `f_context["risk_metrics"]` 中存在且类型正确；(4) 断言指标表出现在 LLM prompt 输出字符串中（验证 inject 成功）；(5) 验证空数据场景——当 `daily_returns` 不足 20 天时，相关指标返回 None 且 prompt 显示"--"而非崩溃。标注 `@pytest.mark.scenario_basic`。
- **测试隔离要求**: (a) **输出目录隔离**——`reports/` 输出目录必须重定向到 `tmp_path`；(b) **LLM 调用 mock**——`build_system_prompt` 的测试只验证 prompt 字符串输出，不调用 `call_llm()`；若测试触发完整 LLM 管线，必须 mock `call_llm()`；(c) **输入数据隔离**——持仓 fixture 构造 3 品种简单数据，不依赖 `data/holdings/` 真实文件；(d) **Rf 依赖 mock**——若使用 `bond_yield` 获取 Rf 计算夏普，需 mock `bond_zh_us_rate()` 返回已知值，避免外部 API 依赖。

### P2-15: LLM Prompt 注入——数据质量段落
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P2-14、T0-02（数据质量已在管线中）
- **描述**: 在 `health_check` prompt 中展开数据质量段落（T0-03 预留位置），格式化为项目符号列表。每条包含：检查项名称、状态图标（🟢/🟡/🔴）、简要说明。当所有检查项正常时，合并为一行"所有数据源状态正常"。

### P2-16: LLM Prompt 注入——信号置信度
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P2-09（截断保护为各指标输出 confidence 字段）
- **描述**: 在 prompt 中增加"信号置信度"段落，LLM 据此调整建议的口吻。规则：(1) 所有指标均为 high → "数据充分，建议可信度较高"；(2) 部分指标 medium → "部分数据有限，仅供参考"；(3) 有 low 指标 → "数据不完整，建议谨慎参考"；(4) 大部分指标 None → "当前数据不足以生成可靠建议"。
- **验收标准**（R5-03 补充）: (1) 在 `expert_review` prompt 的"信号置信度"段落中插入结构化标记 `{{confidence_level}}`，值为以下枚举之一：`"high"`（所有 8 指标 confidence 均为 high）、`"medium"`（任意指标为 medium 且无 low）、`"low"`（任意指标为 low）、`"insufficient"`（≥5 指标为 None）；(2) 在 `prompts.py` 中编写一个纯 Python 函数 `_get_confidence_level(metrics_dict) → str`（不含 LLM 调用），实现上述枚举逻辑，该函数有完整单元测试（mock 各指标 confidence 值，验证 4 种枚举输出）；(3) 运行 `python -m pytest src/test/unit/llm/test_prompts.py -x -q` 确认新增函数测试通过；(4) `{{confidence_level}}` 对应的引导话术固定为 `{"high":"数据充分，建议可信度较高","medium":"部分数据有限，仅供参考","low":"数据不完整，建议谨慎参考","insufficient":"当前数据不足以生成可靠建议"}`。

### P2-17: LLM Prompt 注入——行动模板
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P2-14、P2-16
- **描述**: 在 `expert_review` prompt 结尾增加标准化行动模板段，引导 LLM 输出结构化建议。
- **验收标准**（R5-03 补充）: (1) 在 `expert_review` system prompt 末尾插入格式指令，要求 LLM 在回复末尾以 Markdown 表格格式输出行动建议（列：建议类型、涉及品种、建议理由、优先级）；(2) 建议类型枚举值固定为 `["持有","增持","减持","止盈","止损"]`，优先级枚举值固定为 `["高","中","低"]`，非枚举值不在表格中出现；(3) 每次 LLM 回复必须至少包含 1 行动建议行（即使为"持有全部品种"），不得空表；(4) 在 `prompts.py` 中编写纯 Python 验证函数 `_validate_action_template(llm_output: str) → bool`，解析 LLM 回复末尾的 Markdown 表格，检查列数=4、枚举值合法性、非空——该函数有完整单元测试（mock 合法回复→True、非法回复→False、空回复→False）；(5) 运行 `python -m pytest src/test/unit/llm/test_prompts.py -x -q` 确认新增函数测试通过；(6) 运行 `python -m pytest src/test/ -m "unit" -x --tb=short -q` 确认不破坏现有单元测试。

### P2-18: 指标集成测试（8 指标各 1-2 断言）
- **估时**: 8h
- **文件**: `src/test/unit/test_metrics.py`（新建）
- **阻塞**: 否
- **依赖**: P2-08（metrics.py 统一接口就绪）
- **描述**: 为 8 个指标编写单元测试：(1) 夏普——已知收益率序列 + 已知 Rf → 已知值校验；(2) 卡玛——已知回撤系列 → 已知值；(3) HHI——均匀权重 → 1/N；(4) 胜率——3 盈 2 亏 → 0.6；(5) 换手率——已知变动额 → 已知值；(6) 风险贡献——等权等σ → 均等；(7) Beta——组合=基准 → 1.0；(8) 回撤分位——已知回撤窗口 → 分位值校验。标注 `@pytest.mark.unit_providers`。每个指标至少包含正常和边界两种情况。

---

## Phase 3 — 执行信号与竞争语境 + 画像问卷 + 事实校验器（~206h）

> **说明**: P3-15（TUI 画像问卷，原 P5-04）和 P3-16（事实校验器，原 P4-07）从 Phase 4/5 提前到 Phase 3 尾期并行执行，两者均无依赖，可与其他 Phase 3 任务并行。P3-14（prompts.py 拆分）已提前到 Phase 1（P1-08-B）。P3-09b（口径修正因子）推迟到 Phase 4。

### P3-01: 再平衡完整版——目标配置 Schema
- **估时**: 16h
- **文件**: `src/python/config/_config_defaults.py`（新增 `target_allocation` 配置）、`src/python/analysis/rebalance.py`（新建，替代 MVP 的 `simple_rebalance.py`）
- **阻塞**: 否
- **依赖**: MVP-03（硬编码版已交付，完整版在其基础上扩展）
- **描述**: 设计目标配置 Schema：`{"equity": {"min": 30, "max": 70, "target": 50}, "bond": ...}`（百分比）。支持大类配置 + 品种级配置。Config 默认值为空（=不启用目标配置检查）。`rebalance.py` 实现：(1) 读取目标配置；(2) 计算当前大类/品种偏离度；(3) 输出 `{type, code, current_weight, target_weight, deviation, action}`。

### P3-02: 再平衡完整版——阈值可配
- **估时**: 8h
- **文件**: `src/python/config/_config_defaults.py`、`src/python/analysis/rebalance.py`
- **阻塞**: 否
- **依赖**: P3-01（Schema 已定义）
- **描述**: MVP 版 15% 为硬编码。完整版从 config 读取 `rebalance.threshold`：(1) 单品种超限阈值（默认 15%，可配）；(2) 大类配置偏离阈值（默认 5%，可配）；(3) 保守/稳健/进取三套预设阈值（Phase 4 用户画像接入后自动切换）。

### P3-03: 再平衡完整版——静默期
- **估时**: 8h
- **文件**: `src/python/analysis/rebalance.py`
- **阻塞**: 否
- **依赖**: P3-02（阈值系统已就绪）
- **测试**: unit（`pytest src/test/unit/test_rebalance.py -x -q`）
- **描述**: 引入静默期机制：同一品种触发再平衡信号后，N 天内不再重复告警（默认 30 天，可配）。静默期状态持久化到 `data/cache/rebalance_silence.json`。LLM 输出时注明："上次建议减持 XX 在 30 天静默期内，本次不再重复。"
- **测试隔离要求**: `rebalance_silence.json` 路径必须可注入（构造参数或 config），测试时通过 `monkeypatch.setattr` 或 fixture 注入 `tmp_path` 下路径。测试应验证：写入后可恢复读取、静默期内不重复告警、静默期过期后重新告警。

### P3-04: 再平衡完整版——信号置信度
- **估时**: 8h
- **文件**: `src/python/analysis/rebalance.py`
- **阻塞**: 否
- **依赖**: P3-02（阈值系统）
- **描述**: 为每条再平衡信号计算置信度：(1) 偏离幅度（偏离越大置信度越高）；(2) 偏离持续时间（持续 > 30 天的高偏离为高置信度）；(3) 数据质量（对应品种的数据状态，降级中则置信度降低）。输出 `confidence: high/medium/low`，LLM 据此调整建议强度。

### P3-05: 再平衡完整版——三类误报防护
- **估时**: 8h
- **文件**: `src/python/analysis/rebalance.py`
- **阻塞**: 否
- **依赖**: P3-02（阈值系统）
- **描述**: 再平衡信号的误报防护逻辑：(1) 分红/拆股导致的市值跳变 → 检查品种份额是否变化，排除纯价格波动超过阈值但持有量未变的"假超限"；(2) 新买入品种短期波动 → 持仓不足 20 个交易日不触发再平衡；(3) 临近行权/到期品种 → 标注剩余期限，LLM 可据此判断是否等待自然到期。每条误报防护规则记录触发情况。

### P3-06: 再平衡完整版——权益/固收偏离
- **估时**: 18h（含 2-4h 前置任务用于基金实际权益比例获取/估算）
- **文件**: `src/python/analysis/rebalance.py`（新增 `equity_fixed_income_deviation`）
- **阻塞**: 否
- **依赖**: P3-01（目标配置 Schema）、P1-22（已从 report/category.py 提取到 code_utils.py，防止逆向依赖）
- **描述**: 基于 `category.py` 的 8 类资产分类，汇总为权益类（股票/股票型基金/混合基）和固收类（债券/货基/现金）。对照目标配置（P3-01）计算偏离度。输出："权益仓位从 70% 升至 78%（目标上限 70%），建议部分止盈权益类品种，增配债券类。" 偏离 < 阈值（默认 5%）时不输出。
- **前置注意**: `code_utils.py`（来自 P1-22 提取）的资产分类对权益/固收偏离可能存在以下偏差——(1) 混合型基金若在 code_utils.py 中被统一归入"基金/混合"，但实际权益比例从 0% 到 95% 不等，汇总到权益类时必然失真；(2) `is_bond_fund_by_name` 使用宽松匹配含单字"债"，可能误配可转债等非纯债品种为固收类；(3) `is_otc_fund_by_name` 依赖名称关键词，"00"代码重叠区存在误判风险。本任务需额外增加 2-4h 用于评估是否需要新数据源获取持仓基金的实际权益比例（如天天基金持仓穿透或基金类型注册信息），或在不做数据源改进时增加免责声明"混合基金权益比例为估算值"并在 LLM prompt 中降低该信号的置信度权重。

### P3-07: 竞争语境完整版——偏股基金指数 885005 获取 + 自定义基金池维护入口
- **估时**: 10h（8h 原有 + 2h 用户维护路径）
- **文件**: `src/python/fetcher/index.py`（L24 `_A_INDICES` 增加 885005）、`src/python/tui/fund_pool_manager.py`（新增菜单页）
- **阻塞**: 是 ← PRE-02（885005 可用性测试通过）、PRE-02-D（prompt 分支已实现）
- **依赖**: PRE-02、PRE-02-D
- **描述**: 如果 PRE-02 确认可获取，在 `index.py` 中增加偏股基金指数 885005：(1) 在 `_A_INDICES` 添加 `"sz885005": "偏股基金指数"`；(2) 实现对应 provider 请求（akshare/东方财富）；(3) 回退机制：源不可用时静默失败，不阻断其他指数获取。如果 PRE-02 确认不可获取，此任务降级为在 `competitive_context` prompt 中添加说明："偏股基金指数暂不可用，以下对比仅基于沪深300。" 同时增加自定义基金池用户维护路径：(1) 在 TUI 中新增"管理对比基金池"菜单，允许用户添加/删除基金代码（用于 885005 不可用时的三列对比兜底）；(2) 在配置文件中提供预设池（如"沪深300+中证500+中证全债"）作为 885005 不可用时的默认三列对比方案，无需用户手动维护即可获得有意义的对比。降级预案：如 885005 不可获取且 P5-04（UI 基金池管理）未实现，使用 config.json 中硬编码的默认预设池（沪深300+中证500+中证全债）。预设池内单指数获取失败时，该指数从对比表中移除，剩余指数正常显示，LLM prompt 说明'XX 指数暂不可用'。PRE-02 执行时机改为 Phase 2 启动前以确保 Phase 3 技术方案不受延期决策影响。

### P3-08: 竞争语境完整版——夏普对比
- **估时**: 8h
- **文件**: `src/python/llm/prompts.py`（竞争语境段落扩展）
- **阻塞**: 是（依赖链 7 步硬串行：PRE-01→P1-03→P2-01→P3-08 及 PRE-02→P3-07→P3-08，任一环节失败均导致夏普对比列显示"--"或仅剩两列）
- **依赖**: P2-01（夏普比率可用）、P3-07（885005 或降级说明）
- **描述**: 扩展竞争语境段落为三列（组合、沪深300、偏股基金指数）。字段：(1) 年初至今收益；(2) 近 1 年收益；(3) 最大回撤；(4) 夏普比率（如有）；(5) 年化波动率。偏股基金指数不可用时仅显示两列。最后 LLM 综合判断："你的组合在牛市中略跑赢指数，且回撤控制优于平均水平，偏防御型配置。" **依赖链风险备注**：此任务依赖 7 步硬串行链（PRE-01→P1-01→P2-01→P2-08→P2-14→P2-14-B→P3-08 及 PRE-02→P3-07→P3-08），环节总数超过 15 个节点（含隐藏扇入），单点故障概率叠加后 P3-08 按设计完整交付的概率显著高估。(1) 在 PRE-01 测试报告中增加 PASS/FAIL 对 P3-08 影响分析——API 不可用则提前决定夏普对比不可行，P3-08 砍掉夏普维度（仅保留收益对比，等同于现有 MVP-04 内容）；(2) 建立依赖链健康检查脚本，在 Phase 2 收尾时自动验证 P1-01→P2-01 管线数据流是否产生有效夏普值，若为 None 则 P3-08 自动降级为"收益对比扩展"而非"夏普对比新增"。
- **正式降级验收标准（CRITICAL）**：P3-08 的 15+ 节点硬串行链意味着全链按设计交付的概率极低，必须建立每个环节的正式降级验收标准：(a) **PRE-01 FAIL** → Rf API 不可用 → P1-01/P1-02 砍掉（释放 28h），P1-03 手动配置兜底（2h），P3-08 夏普列显示"--"，不影响收益对比列；(b) **P1-01 交付后夏普值为 None**（Rf 虽可用但数据不稳定超过 1 个月）→ P2-01 显示"--"，P3-08 自动移除夏普维度，LLM prompt 中增加"风险调整后收益数据暂不可用"说明；(c) **PRE-02 FAIL** → 885005 不可获取 → P3-07 降级为自定义基金池，P3-08 显示两列（组合+沪深300）或三列（组合+沪深300+预设池均值），LLM prompt 标注"偏股基金指数暂不可用"；(d) **多重 FAIL**（Rf 和 885005 均不可用）→ P3-08 退化为 MVP-04 级别（仅收益对比两列），无夏普无偏股基金，相当于非功能交付——此级别在项目排期中应当被标记为"非功能交付"而非"部分交付"，决策权归属项目经理。每个降级场景的验收代码随 P3-08 同时交付（场景枚举 + 降级路径注释）。

### P3-09a: 竞争语境完整版——口径对齐与说明（prompt 级，快速上线）
- **估时**: 2h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P3-08
- **描述**: 在竞争语境段落脚注位置加入口径说明：(1) 组合收益为费后净收益，指数为价格指数（非全收益）；(2) 组合含现金管理品种，指数不含；(3) 对比期间可能存在持仓变动（非静态组合）。**强制约束**：LLM 不得做出"跑赢/跑输"的明确结论性判断，仅输出"组合收益 X%，指数收益 Y%，差异 Z 个百分点"的数据陈述。口径限制作为用户可见的脚注而非仅 LLM 内部指令。如果数据不支持精确对比，以数据陈述代替结论判断的兜底指令。

### P3-10: 竞争语境完整版——幸存者偏差说明
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P3-08
- **描述**: 在竞争语境 prompt 中增加幸存者偏差提醒。LLM 输出末尾自动追加："注：偏股基金指数成分基金会定期调整，表现差的基金可能被剔除，因此指数本身存在幸存者偏差。你的组合对比可能略偏保守。"

### P3-11: 流动性风险——场内品种自动计算（Layer 3B）
- **估时**: 12h
- **文件**: `src/python/analysis/liquidity.py`（新增）
- **阻塞**: 否
- **依赖**: 腾讯/新浪 K 线 API（个股/ETF 的日均成交额数据已有，但依赖该 API 正常返回成交量字段；历史上空数据返回记录——若 API 降级或格式变更，流动性计算完全失效）
- **描述**: 实现 `check_liquidity(holdings) → list[dict]`。场内品种（股票/ETF）：`市值 / 近 20 日日均成交额`，计算变现天数。输出：(1) 各品种变现天数；(2) 累计变现总天数（若需全部卖出）；(3) 标记"当日可卖出" vs "需多日卖出"。场外基金标记为 OTC 类型交由 P3-12。注入 LLM prompt："XX 品种持仓 500 万，日均成交额 1000 万，约 0.5 日可完成变现。" **降级方案**：成交额数据失败时默认假设流动性充足，不告警。**⚠ 注册要求**：包含 `registry.py _COMPUTATION_REGISTRY` 注册（注册名 `analytics_liquidity`，由 P1-10 预留位置）。

### P3-11-T: 流动性风险测试（场内）
- **估时**: 4h
- **文件**: `src/test/unit/test_liquidity.py`（新建）、`src/test/unit/test_liquidity_edge.py`（新增——极端场景隔离）
- **阻塞**: 否
- **依赖**: P3-11
- **描述**: 为场内流动性计算编写测试用例：(1) 正常计算——给定市值+成交额，验证变现天数正确；(2) **极端大持仓（放入 test_liquidity_edge.py）**——市值远超日均成交额，验证变现天数为合理值；(3) 所有品种均为 OTC——返回空列表；(4) 空成交额——成交额列表为空时返回 None 而非崩溃。标注 `@pytest.mark.unit_providers`（普通测试）、`@pytest.mark.edge`（极端场景放入 `test_liquidity_edge.py`）。**C12 合规**：极端场景必须与普通测试文件分离。

### P3-12: 流动性风险——场外品种手动配置入口（Layer 3B）
- **估时**: 12h
- **文件**: `src/python/config/_config_defaults.py`（新增 `redemption_limits`）、`src/python/analysis/liquidity.py`（扩展）
- **阻塞**: 否
- **依赖**: P3-11（流动性分析框架已就绪）
- **描述**: 场外基金实际赎回上限（如"单日上限 10 万"）无法自动获取，需用户配置。在 `_DEFAULT_CONFIG` 中新增 `redemption_limits: dict[str, float]`（code → 单日赎回上限金额）。`liquidity.py` 读取该配置，计算场外品种全量赎回所需天数。未配置的品种显示"需手动确认赎回上限"。⚠ 并发约束：P3-12 和 P3-15 均修改 _config_defaults.py，必须由同一开发者按序执行（先 P3-12 后 P3-15 或反之），禁止两人并行修改同一文件。

### P3-12-T: 流动性风险测试（场外）
- **估时**: 4h
- **文件**: `src/test/unit/test_liquidity_otc.py`（新建）、`src/test/unit/test_liquidity_otc_edge.py`（新增——极端场景隔离）
- **阻塞**: 否
- **依赖**: P3-12
- **描述**: 为场外赎回天数计算编写测试用例：(1) 配置赎回上限——给定持仓市值+单日上限，验证天数正确；(2) 未配置品种——返回"需手动确认"标记；(3) 无 OTC 品种——返回空列表；(4) **巨额赎回（放入 test_liquidity_otc_edge.py）**——市值远超单日上限，验证天数为合理值。标注 `@pytest.mark.unit_providers`（普通测试）、`@pytest.mark.edge`（极端场景放入 `test_liquidity_otc_edge.py`）。**C12 合规**：极端场景必须与普通测试文件分离。

### P3-13: 汇率敞口——货币分类修复（Layer 3C）
- **估时**: 12h
- **文件**: `src/python/code_utils.py`（新增币种判定 is_hkd_denominated/is_usd_denominated）、`src/python/analysis/fx_exposure.py`（新增）
- **阻塞**: 否
- **依赖**: P1-22（code_utils.py 已扩展为统一判定入口）
- **描述**: 实现 `fx_exposure(holdings) → dict`。依据上市地 + 币种字段判断：(1) 人民币计价；(2) 港币计价（港股通）；(3) 美元计价（美股/美元债）；(4) 其他。汇总各币种占比（市值加权）。LLM 输出："约 30% 资产为美元计价，人民币近期升值 / 贬值影响约 -2%。" 注意：港股通品种为港币计价但实际换汇成本是隐含的，需标注说明。注入 `expert_review` prompt。**⚠ 注册要求**：包含 `registry.py _COMPUTATION_REGISTRY` 注册（注册名 `analytics_fx_exposure`，由 P1-10 预留位置）。

### P3-15: TUI 完整画像问卷（从 Phase 5 提前，无依赖可并行执行）
- **估时**: 40h（5 天）
- **文件**: `src/python/tui/profile_questionnaire.py`（新增）、`src/python/config/_config_defaults.py`（新增 `user_profile` 段）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 风险承受能力/投资期限/投资目标/定投金额/税务身份/经验水平 6 字段问卷，结果持久化到 config。支持"跳过"（用中性通用投资建议垫底（无推断时可用的默认值））。Phase 5（P5-01~03）未实现时，跳过问卷直接使用中性通用建议。提前到 Phase 3 尾期执行（与 P3-11/12/13 等无依赖任务并行）。⚠ 并发约束：P3-12 和 P3-15 均修改 _config_defaults.py，必须由同一开发者按序执行（先 P3-12 后 P3-15 或反之），禁止两人并行修改同一文件。

### P3-16: LLM 事实锚定校验器（从 Phase 4 提前，无依赖可并行执行）
- **估时**: 24h（3 天）
- **文件**: `src/python/llm/fact_checker.py`（新增）
- **阻塞**: 否
- **依赖**: 无
- **描述**: LLM 生成报告后做事实校验：(1) 定义可自动验证的事实类型：数值一致性（LLM 引用的收益率/波动率与实际数据匹配）、品种存在性（LLM 提及的品种确实在持仓中）、排名正确性（LLM 说的"最大持仓"确实市值最大）；(2) 校验器提取 LLM 回复中的数值和品种名，对照已知数据做一致性检查；(3) 不一致项标注并修正（数值纠正 / 删除错误陈述）；(4) 在报告末尾追加校验摘要："报告经自动事实校验：4/5 项数据准确，1 项数值偏差已修正。" 提前到 Phase 3 执行（与再平衡完整版等任务并行），使 Phase 4 幻觉率采样测试（P4-08）可尽早启动。- **注册要求（已决策）**：实施两层分层方案——(a) 数值一致性检查（纯算法层，验证收益率匹配、品种存在性、排名正确性），注册到 registry.py 新增的 _COMPUTATION_REGISTRY（由 P1-10 负责创建 ComputModuleDef 结构，不含缓存属性），在 generators_orchestrator 中用串行调用；(b) 复杂事实声明验证（LLM API 层，需额外 token），在 _MODULE_FNS 注册并通过 call_llm() 路由（C17 合规）。优先实现纯算法层（8h），LLM 增强版作为 Phase 后评估选项（+16h）。两层可共存。总估时 24h 含 4h _COMPUTATION_REGISTRY 适配+管线注册。

### P3-17: LLM Token 成本追踪与预算机制
- **估时**: 8h（1天）
- **文件**: src/python/llm/api.py（调用记录扩展）、src/python/llm/cost_tracker.py（新增）
- **阻塞**: 否
- **依赖**: P2-14（prompt 注入架构确定后，token 结构基本定型）
- **描述**: (1) 在每次 call_llm() 返回时记录模块名称、token 数（输入/输出）、模型名称、耗时；(2) 创建 cost_tracker.py 提供会话级累计统计（总 token、预估费用、按模块分布）；(3) 在报告末尾（或 -v verbose 模式）输出成本摘要；(4) 定义每份报告的 token 预算上限（默认 8K 输入 token），超出时告警而非截断——为后续模型分层（便宜模型做结构性内容）提供基线数据。

---

## Phase 4 — 质量与安全（~176h）

> **硬性前置条件**：端到端性能测试（P4-14）、链韧性测试（P4-15）、安全测试（P4-16）的通过标准为 Phase 4 的**硬性前置条件**，不允许为赶进度而压缩或跳过。任意一项测试失败则 Phase 4 不可视为完成。
> **估时说明**：原文风险表标注 Phase 4 估时低估 1.5-2 倍。当前任务分解 176h（约 22 天单人），但考虑依赖链风险和画像部分的高复杂度，保守估计需 52 天（单人）、悲观 68 天（单人）。1 人团队建议按 1.6x 系数估算约 55-90 天。建议 Phase 3 完成后重新评估 ROI 决定是否进入 Phase 4。

### P2-11b: 组合 Beta 算法——置信区间 + 统计检验（从 Phase 2 移入，与敏感性分析合并）
- **估时**: 24h（3 天——含 t-统计量、协方差矩阵推导、蒙特卡洛置信区间）
- **文件**: `src/python/analysis/metrics.py`（扩展 `portfolio_beta` 增加置信区间）
- **阻塞**: 否
- **依赖**: P2-11a（Beta 点估计已就绪）
- **描述**: 在 P2-11a 的点估计基础上增加统计检验：(1) 95% 置信区间——基于协方差矩阵的 t-统计量方法；(2) t-统计量 + p 值（判断 Beta 是否显著 ≠ 0）；(3) 置信区间过宽（宽度 > 1.5）时标注"数据不足，Beta 估计可靠性有限"；(4) 输出格式：`{beta: float, ci_lower: float, ci_upper: float, t_stat: float, p_value: float, reliable: bool}`。为 P4-01 情景模拟提供置信区间输入。

### P4-01: 敏感性分析——Beta 推导（Layer 1 情景模拟）
- **估时**: 12h
- **文件**: `src/python/analysis/scenario.py`（新增）
- **阻塞**: 否
- **依赖**: P2-11a（组合 Beta 点估计可用）、P2-11b（置信区间可用）
- **描述**: 实现 `scenario_analysis(beta, portfolio_value) → dict`。基于组合 Beta 的线性推导：(1) 市场 -10%、-20%、-30% 三种跌幅情景下的组合预期回撤；(2) 市场 +10%、+20%、+30% 三种涨幅情景下的组合预期收益；(3) 置信区间（假设收益率正态分布，±1σ/±2σ 区间）。输出格式：表格（情景、预期变动、置信区间）。注入 LLM prompt 的"情景模拟"段落。**⚠ 注册要求**：包含 `registry.py _COMPUTATION_REGISTRY` 注册（注册名 `analytics_scenario`，由 P1-10 预留位置）。

### P4-02: 敏感性分析——3 情景表
- **估时**: 8h
- **文件**: `src/python/analysis/scenario.py`
- **阻塞**: 否
- **依赖**: P4-01（基础推导已实现）
- **描述**: 扩展情景表，覆盖更多因素：(1) 权益/固收不同情景下的表现差异；(2) 行业集中度影响（如全仓白酒 vs 市场下跌情景）；(3) 汇率变动情景（人民币 ±5% 对组合的影响）。输出三张情景表：市场情景、行业情景、汇率情景。

### P4-03: 敏感性分析——置信区间传播
- **估时**: 12h
- **文件**: `src/python/analysis/scenario.py`
- **阻塞**: 否
- **依赖**: P4-02、P2-09（截断保护机制）
- **描述**: 对各个指标的不确定性做置信区间传播：(1) Beta 置信区间 → 情景回撤置信区间；(2) 年化波动率置信区间 → 夏普比率置信区间；(3) 在 LLM prompt 中表述为："若市场下跌 20%，组合预计回撤 -16% 至 -24%（95% 置信区间）。" 置信区间过宽时（宽度 > 15%）标注"数据不足，预测可靠性有限"。

### P3-09b: 竞争语境——口径修正因子计算（从 Phase 3 移入，与敏感性分析并行）
- **估时**: 16h
- **文件**: `src/python/analysis/alignment_correction.py`（新增）
- **阻塞**: 否
- **依赖**: P3-09a、P2-08（metrics 完备）
- **描述**: 实现实质性口径修正因子计算，解决 P3-09a 无法量化的三个差异：(1) 组合综合费率估算——使用品种级别费率（管理费+托管费+申赎费）加权估算组合年化费率，用于调整费前收益对比；(2) 现金剥离——从组合收益中识别并剥离货币基金/现金管理品种的贡献，使权益部分与纯权益指数可比；(3) TWR 计算——实现时间加权收益率（True Time-Weighted Return）而非简单累计对比，消除持仓变动对收益率的影响。输出修正因子字典，LLM 据此做数据级修正而非仅口头提示。如果数据不足以计算修正因子（如费率数据不可获取），回退到 P3-09a 纯说明版本并显示"费率和现金比例数据不足，对比结果仅供参考"。**⚠ 注册要求**：包含 `registry.py _COMPUTATION_REGISTRY` 注册（注册名 `analytics_alignment`，由 P1-10 预留位置）。

### P4-04: 隐私安全——匿名化 4 模式
- **估时**: 12h
- **文件**: `src/python/anonymizer.py`（扩展 P1-13 的最小版）
- **阻塞**: 否
- **依赖**: P1-13（匿名化最小版已交付）
- **描述**: 扩展匿名化为 4 种模式：(1) 关闭（显示真实名称代码）；(2) 代码显示（名称→"品种X"，保留代码和盈亏）；(3) 完全匿名（名称→"品种X"，代码→"000XXX"，盈亏→±XX%）；(4) 汇总模式（仅显示大类汇总，不显示单品种）。在 TUI 菜单增加匿名化模式设置。持久化到 `config.json anonymization.mode`。

### P4-05: 隐私安全——隐私提示
- **估时**: 4h
- **文件**: `src/python/tui/privacy_notice.py`（新增）、`src/python/cli.py`（首屏提示）
- **阻塞**: 否
- **依赖**: P4-04（匿名化选项完整）
- **描述**: (1) 首次运行程序时显示隐私提示："本程序数据仅供本地处理，所有数据保存在当前设备。LLM 请求经由 API 发送到 {provider}，不会用于训练。" (2) 每次生成报告时在 HTML/Excel 脚注自动追加上述提示；(3) TUI 新增"隐私与安全"页面展示当前安全状态（密钥加密✅ / 缓存保护✅ / 匿名化关闭🔴）。

### P4-06: 隐私安全——缓存审查
- **估时**: 8h
- **文件**: `src/python/cache.py`（扩展清理逻辑）
- **阻塞**: 否
- **依赖**: P1-14（缓存权限已保护）
- **描述**: 缓存数据可能包含敏感持仓信息。新增：(1) `cache.clean_sensitive(older_than_days=90)` 定期清理过期缓存；(2) 缓存内容审查：标注哪些 key 可能含敏感信息（如 `holding_*`、`penetration_*`）；(3) 启动时自动清理超过 90 天的敏感缓存；(4) 敏感缓存在加密存储（可选）。

### P4-08: LLM 幻觉率采样测试
- **估时**: 16h
- **文件**: `src/test/scenario/test_llm_hallucination.py`（新建）
- **阻塞**: 否
- **依赖**: P3-16（原 P4-07，事实校验器已移至 Phase 3）
- **描述**: 建立幻觉率评估流程：(1) 准备 10 组标准持仓数据 + 对应正确事实表；(2) 每组数据让 LLM 生成报告（使用当前 prompt）；(3) 事实校验器 + 人工复核对比；(4) 统计幻觉率（错误事实 ÷ 总事实提及次数）；(5) 目标：<5%。生成幻觉率报告（`docs-stm/tmp/hallucination-report.md`）。每次 prompt 重大修改后重新采样。标注 `@pytest.mark.scenario_llm`，在 `conftest.py` 注册此 marker。

### P4-09: 缓存雪崩随机 TTL 修复
- **估时**: 4h
- **文件**: `src/python/cache.py`（TTL 设置逻辑）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 当前同类缓存同时过期（如同为 `index_*` 前缀的缓存 TTL 相同），大量缓存同时失效时会产生缓存雪崩。修复：(1) 为每种 TTL 类别增加随机偏移（±15%）；(2) `get_cache_ttl_defaults()` 返回值乘以 `random.uniform(0.85, 1.15)`；(3) 偏移种子基于缓存 key 哈希（相同 key 每次一致，避免偏移导致每次读到的 TTL 不同）。

### P4-10: metrics 测试用例（标记注册+增量）
- **估时**: 8h
- **文件**: `src/test/unit/test_metrics.py`（扩展 P2-18）
- **阻塞**: 否
- **依赖**: P2-18（已有基础测试）、P2-09（截断保护）
- **描述**: 扩展 metrics 测试覆盖边界：(1) 全 None 输入 → 各指标输出 None；(2) 空列表 → 不崩溃；(3) 极端值（一天 +50% "数据错误"）→ 被截断为 None 并告警；(4) 仅 5 个交易日 → 置信度 low；(5) 正常数据 → 置信度 high。添加截断保护专用测试。标注新 marker `@pytest.mark.edge`（极端值测试，需放入 `test_metrics_edge.py`）。

### P4-11: bond_yield 测试用例完善（edge 场景）
- **估时**: 4h
- **文件**: `src/test/unit/test_bond_yield_edge.py`（新建）
- **阻塞**: 否
- **依赖**: P1-15（已有基础测试）
- **描述**: 为 Rf fetcher 添加 edge 场景测试：(1) 返回负数收益率（数据异常）；(2) 返回字符串 NaN；(3) 两个数据源返回差异 > 0.5%；(4) 连续 10 次 API 失败 → 进入长期熔断。标注 `@pytest.mark.edge`。

### P4-12: 再平衡测试用例完善
- **估时**: 8h
- **文件**: `src/test/unit/test_rebalance.py`（新建）、`src/test/unit/test_rebalance_edge.py`（新建）
- **阻塞**: 否
- **依赖**: P3-06（再平衡完整版就绪）
- **描述**: (1) 无超限品种 → 空列表；(2) 单品种超 15% → 触发建议；(3) 权益偏离 → 大类配置建议；(4) 分红导致的"假超限" → 误报防护；(5) 静默期测试 → 同品种 30 天内不重复；(6) 所有阈值可配 → 不同配置不同输出。标注 `@pytest.mark.unit_rebalance`（普通测试）、`@pytest.mark.edge`（极端值测试放入独立 `test_rebalance_edge.py` 文件）。在 `conftest.py` 注册 `unit_rebalance` marker。

### P4-13: 测试标记注册与集成门禁
- **估时**: 4h
- **文件**: `src/test/conftest.py`（`pytest_configure` 注册新 marker）
- **阻塞**: 否
- **依赖**: P4-10、P4-11、P4-12（新测试已存在）
- **描述**: (1) 注册 Phase 2-4 新增测试模块的 marker（如 `unit_profile`、`unit_rebalance`、`unit_metrics_ext`、`scenario_llm`）；(2) 在 `conftest.py` 的 `pytest_collection_modifyitems` 中校验 edge 测试文件隔离（P4-10/11/12 的 `_edge.py` 文件必须包含对应 edge 测试，不能混入普通测试）；(3) 更新 `docs-stm/managements/testplan.md` 新增模块行。

### P4-14: 端到端性能测试
- **估时**: 12h（含 4h 20 品种+3 年历史 fixture 搭建 + 8h 多轮采样与阈值校准）
- **文件**: `src/test/scenario/test_e2e_perf.py`（新建）
- **阻塞**: 否
- **依赖**: P2-08（metrics 完备）、P3-06（再平衡完备）、P4-03（情景分析完备）
- **描述**: 模拟 20 品种 + 3 年历史的完整持仓，运行全量报告生成（Excel + HTML + LLM），计时并记录：(1) 总耗时（目标 < 60s）；(2) 各阶段耗时分布；(3) 缓存命中率；(4) LLM Token 消耗（计数）。失败条件：总耗时 > 120s。结果输出到 `docs-stm/tmp/perf-report.md`。

### P4-15: 链韧性测试
- **估时**: 12h（含 6h 级联故障/长时间恢复/持久化恢复三种测试场景 + 4h 跨会话熔断恢复验证 + 2h 报告生成）
- **文件**: `src/test/scenario/test_chain_resilience.py`（新建）
- **阻塞**: 否
- **依赖**: P1-19（统一熔断器网关）
- **描述**: 模拟数据源故障场景，验证链韧性：(1) 主链路全部返回 503 → 验证备用链路切换；(2) 备用链路也故障 → 验证过期缓存降级；(3) 熔断器触发 → 验证冷却期正常；(4) 所有数据源同时故障 → 验证报告仍能生成（显示"--"）。每种场景至少一个断言。扩展覆盖场景：(1) 多数据源同时故障级联测试——东财全系 API 503、腾讯全系 API 超时、所有外部 API 同时不可用；(2) 长时间不可用后恢复测试——API 中断 30 分钟后恢复，验证熔断器冷却期试探策略的正确性；(3) 熔断器持久化恢复测试——跨会话加载熔断状态，验证冷却剩余时间计算正确。

### P4-16: 安全测试
- **估时**: 12h（含 6h 5 项安全基线自动化 + 2h 人工评审 + 4h 修复验证迭代）
- **文件**: `src/test/scenario/test_security.py`（新建）
- **阻塞**: 否
- **依赖**: P4-06（隐私安全实施完成）
- **描述**: 安全基线验证：(1) 密钥文件不可读（权限检查）；(2) 缓存文件不含明文密钥；(3) 匿名化模式下报告不含真实名称/代码；(4) LLM API 请求日志不记录完整密钥（仅记录 `***{last4}`）；(5) HTML 报告不泄露文件系统路径。

---

## Phase D — 独立决策（~16h）

> **D = Discretionary（独立决策）**，不是 P6。Phase 1~5 是按序交付的主路线图（每一阶段依赖或承接前一阶段），而 Phase D 不属于主序列——此任务需单独评估 ROI 后决定是否投入。PD-01（条件推理）已提前至 MVP-06。

### PD-02: CAPM α 计算 ⚠ 建议砍项（保留 4h 做评估，砍掉 12h 实现）
- **估时**: 16h（2 天——精简版，仅输出 α 值，无 t-统计量，解释工作交给 LLM 用自然语言描述）→ **建议保留 4h 做快速验证 + 12h 实现留作按需扩展**
- **文件**: `src/python/analysis/metrics.py`（新增 `capm_alpha` 函数）
- **阻塞**: 是 ← P1-03（Rf 就绪）+ P1-05（组合日收益率就绪）+ P2-11a（Beta 点估计就绪）
- **依赖**: P1-03、P1-05、P2-11a
- **描述**: 实现 `capm_alpha(portfolio_returns, benchmark_returns, rf_annual) → float | None`。公式：`α = Rp_annual - [Rf + β × (Rm_annual - Rf)]`。流程：(1) 从 P2-11a 获取组合 Beta（点估计）；(2) 年化组合收益率；(3) 年化基准收益率；(4) 从 P1-01 获取 Rf。输出为单值（α 百分比），不输出 t-统计量，将解释工作交给 LLM 用自然语言描述。注入 `expert_review` prompt："你的组合 α = +2.3%，表明扣除市场因素后仍有超额收益。" None 时显示"--"。包含单元测试（已知 β=1 → α=0；β>1 且跑输 → α 为负）。**用户教育说明**：α 是专业量化指标，对个人投资者的实用价值有限：(1) α 衡量选股能力，个人持仓频繁变动+样本量小(5-20品种)+含非股票资产，使 α 的统计效力和适用性存疑；(2) α 的解释成本高——即使显著也需要大量解释；(3) 此精简版不输出统计显著性，LLM 应避免对 α 值做过度解读。
- **⚠ 砍项建议**：本轮架构审查建议将 PD-02 从原估时 16h（含实现）砍至 4h（仅做用户验证评估）：(a) **前置 4h 快速验证**——制作 5 份含 α 的报告片段，找真实用户（非项目成员）确认：(i) 是否理解 α 含义；(ii) 是否认为 α 有价值；(iii) 是否因为看到 α 而改变组合行为。如果三分之二以上用户的回答是"不理解"或"无价值"，直接砍掉 PD-02 的 12h 实现剩余时间，将其 4h 可重分配给 P4-08（幻觉率采样）+ P3-09b（口径修正因子计算）。(b) **砍项理由**——(i) α 对个人投资组合的统计效力和适用性存疑（持仓频繁变动+样本量小+含非股票资产）；(ii) 即使精简版，其 3 个前置依赖（P1-01、P1-05、P2-11a）均为高估时模块，任一延迟都导致 PD-02 开工遥遥无期；(iii) Phase D 本身即为"独立决策"阶段，PD-02 是全路线中唯一没有默认实施方案、需要额外验证才能决定是否建设的任务。(c) **实施建议**：4h 快速验证在 Phase 3 尾期执行（P2-11a 就绪后），验证结果记录到 `docs-stm/tmp/alpha-feasibility.md`。


## Phase 5 — 用户画像（最低优先级，按需实施）（~108h，P5-04 TUI 问卷已提前到 Phase 3 尾期）

> **说明**：个人画像原属 Phase 4，调整为**最低优先级**——Phase 1~4 全部就绪后再评估是否需要启动。
> **前提条件**：推断版画像（P5-01~03）技术依赖少，但其价值在 Phase 3 再平衡和 Phase 4 LLM 质量完成后才最大化。
> **默认策略**：Phase 1~4 期间始终使用中性通用投资建议，画像缺失不影响其他功能。

### P5-01: 从持仓推断画像——风险级别（Layer 4a）
- **估时**: 16h
- **文件**: `src/python/profile/inferrer.py`（新增）
- **阻塞**: 否
- **依赖**: P1-06, P1-07, P1-08, P4-14, P4-15, P4-16, P1-21
- **描述**: 实现 `infer_risk_level(holdings) → str`。依据：(1) 权益类占比；(2) 单品种集中度；(3) 历史换手率；(4) 持仓品种波动率均值。输出 4 级：保守/稳健/进取/激进。标注"推断结果仅供参考，建议通过问卷确认"。**⚠ 注册要求**：包含 `registry.py _COMPUTATION_REGISTRY` 注册（注册名 `analytics_inferrer`，由 P1-10 预留位置）。

### P5-02: 从持仓推断画像——持有期估算（Layer 4a）
- **估时**: 12h
- **文件**: `src/python/profile/inferrer.py`
- **阻塞**: 否
- **依赖**: P1-04, P5-01
- **描述**: ⚠ 执行约束：Phase 4 全部就绪前不可启动（画像安全门禁未到位）。实现 `infer_holding_period(holdings, history) → str`。依据持仓持有时长分布+换手率+品种类型，输出短期/中期/长期。

### P5-03: 从持仓推断画像——矛盾处理（Layer 4a）
- **估时**: 16h
- **文件**: `src/python/profile/inferrer.py`
- **阻塞**: 否
- **依赖**: P5-01、P5-02
- **描述**: 处理推断中的矛盾信号（如高权益+全 OTC 基金），输出双重标签并建议用户通过问卷确认真实偏好。

### P5-05: 衰减模型——画像随时间衰减（Layer 4b）
- **估时**: 20h
- **文件**: `src/python/profile/decay.py`（新增）
- **阻塞**: 否
- **依赖**: P3-15（原 P5-04，TUI 问卷画像已持久化——已提前至 Phase 3 尾期）
- **描述**: 180 天后提示重评；持仓行为与画像持续矛盾时自动降低置信度。

### P5-06: 自适应阈值——画像联动再平衡（Layer 4b）
- **估时**: 28h（24h 原有 + 4h 安全哨兵机制）
- **文件**: `src/python/analysis/rebalance.py`（扩展）、`src/python/profile/inferrer.py`
- **阻塞**: 否
- **依赖**: P3-15（原 P5-04，画像问卷已提前到 Phase 3）、P3-06（再平衡完整版）
- **描述**: 基于画像自动调整再平衡阈值（保守 10%/3%、稳健 15%/5%、进取 20%/8%、激进 25%/10%）。无画像时使用中性预设（15%/5%）。
- **安全哨兵（CRITICAL）**：自适应阈值联动存在安全设计缺陷——如果推断错误（实际保守型用户被标为激进），再平衡阈值从 10% 放宽到 25%，系统对 25% 的超集中持仓不再预警。必须实施以下三重防护：(1) **置信度门控**——推断置信度为 low 时，即使推断为激进，阈值锁定在稳健预设（15%/5%）；(2) **非问卷用户上限锁定**——非问卷用户（仅推断来源）的阈值上限硬编码为 15%（稳健），不可被画像覆盖；(3) **安全哨兵**——阈值偏离稳健默认值（15%/5%）超过 ±10% 时，在 LLM prompt 中追加风险声明："当前自适应阈值已调整至 {value}，请注意该调整基于推断画像，建议通过问卷确认真实风险偏好。"

### P5-07: LLM 画像注入——提示语个性化
- **估时**: 8h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: P5-01（至少推断版可用）、P3-15（原 P5-04，问卷版更准确——已提前至 Phase 3 尾期）
- **描述**: 在 prompt 首段注入画像摘要，LLM 据此调整建议口吻。无画像时使用中性通用投资建议。当推断置信度为 LOW 时，机械切换为无画像中性 prompt，不由 LLM 自行判断。**安全约束**：(1) prompt 段落必须附带置信度声明，例如"根据您的持仓行为推断，您的风格倾向于{风险级别}（置信度：中）。建议通过问卷确认。"——不允许 LLM 将推断结果视为事实采信；(2) 在 P5-03 的矛盾场景下，LLM prompt 应输出双重标签而非单一风险级别（如"您的持仓行为显示双重标签：高权益偏好（进取型倾向）+ 长持有期（保守型倾向），建议通过问卷确认"）；(3) 增加推断准确率的离线验证计划——用模拟持仓+已知画像做离线校验，设定准确率基线（如 <70% 则不上线推断自动模式）。

### P5-08: 用户画像测试用例
- **估时**: 8h
- **文件**: `src/test/unit/test_profile.py`（新建）、`src/test/unit/test_profile_edge.py`（新建）
- **阻塞**: 否
- **依赖**: P5-03（推断器完整）
- **描述**: 全权益→进取/激进、全货基→保守、矛盾持仓→双重标签等。标注 `@pytest.mark.unit_profile`（普通测试）、`@pytest.mark.edge`（极端值测试放入独立 `test_profile_edge.py` 文件）。在 `conftest.py` 注册 `unit_profile` marker。


---

## 附录：依赖关系图

```
T0-01-A ─→ T0-01 ─→ T0-02
T0-01-B ─→ T0-01      (Pre-Schema 定义, T0-01 接线前就绪)
T0-02 ─→ P2-15

PRE-01 ─→ PRE-01-D (决策门) ─→ P1-03 (bond_zh_us_rate 自动+手动兜底, 6h)
  │                                   └→ P1-10 → P1-15
  │ (P1-01/P1-02 已取消: 东财 API 失效 + wgb JS 渲染不可解析)
  │
  │ 释放 ~20h → 建议重分配给 P1-11(功能开关)/P1-12(断路包装器)/P1-04(数据质量增强)

PRE-02 ─→ PRE-02-D ─→ P3-07

MVP-01 ─┐
MVP-02 ─┤
MVP-03 ─┼→ MVP-05 → MVP-06    (条件推理: prompt 整合后追加)
MVP-04 ─┘

P1-04 ─→ P1-05 ─→ P2-01(P1-03+Rf), P2-02    (组合日收益率→夏普前置+卡玛)
  │              │
  │              ├→ P2-11a → P2-11b(Phase 4) → P4-01 → P4-02 → P4-03
  │              │         └→ PD-02
  │              ├→ P2-12 → P2-13               (回撤预警, 需组合日收益率)
  │              └→ P2-14-B (集成测试)
  ├→ P2-05, P2-06, P2-10    (个股日收益率→换手率/风险贡献/波动率)
  └→ (P1-04 数据质量自检为验收标准)

P1-08 → (history_data 暴露给 prompts → P2-14)  (history_data 不属于 P2-01 前置)

P1-06 ─→ P1-07 ─→ P1-08 ─→ P2-14 → P2-15 → P2-16 → P2-17
  │       │        │
  │       │        └→ P1-09
  │       └→ P1-16
  └→ P1-16

P1-08 → P1-08-B (prompts.py 拆分, 原 Phase 3 提前)
P1-11 ─→ P1-12
P1-17 ─→ P1-18 ─→ P1-19 ─→ P4-15
P1-13 ─→ P4-04 ─→ P4-05
P1-14 ─→ P4-06 ─→ P4-16
P1-22 ─→ (下游: P3-06, P3-13)  (code_utils.py 提取后消除逆向依赖)

P2-01(P1-03+P1-05) → P2-08 → P2-09 → P2-14 → P2-18 ─→ P4-10
P2-02(P1-05) ──────┘  │               │       └→ P2-14-B → P4-13
P2-03(无) ────────────┘               └→ P2-15 → P2-16 → P2-17
                                          │         │
                                          └→ P3-17  └→ (P2-17 无下游)
P2-04(无) ────────────┘
P2-05(P1-04) ────────┘
P2-06(P1-04) ────────┘

P3-01(MVP-03) → P3-02 → P3-03 → P3-04 → P3-05 → P3-06 → P4-12
                     │        │           │       │
                     └→ P5-06           └→ P5-06 └→ (依赖 P1-22)
P3-07(PRE-02-D) → P3-08 → P3-09a ──→ P3-09b(Phase 4)
                                │       ↑
                                └→ P3-10│
                                         └→ P2-08
                                       (口径修正因子, 从 Phase 3 移入)
P3-11 → P3-11-T     (流动性测试)
P3-12 → P3-12-T     (场外流动性测试)

P3-15 (原 P5-04, 无依赖) ─── (提前至 Phase 3 并行)
P3-16 (原 P4-07, 无依赖) ─── (提前至 Phase 3 并行, _COMPUTATION_REGISTRY + 纯算法层)
P3-17(P2-14) → (LLM Token 成本追踪, 新增)

(Phase 4 — 质量与安全, 硬性前置: 性能/韧性/安全测试不可跳过)
P2-11b → P4-01 → P4-02 → P4-03          (情景分析链: Beta→置信区间→3情景→传播)
P3-09b(P3-09a+P2-08) → (口径修正因子, 从 Phase 3 移入, 见 Phase 3 依赖图)
P4-04 → P4-05                              (隐私安全: 匿名化→提示)
P4-06 ← P1-14                              (缓存审查, 与 P4-04/P4-05 并行)
P4-08 → (依赖 P3-16 事实校验器)            (LLM质量: 幻觉测试)
P4-10 ─┐
P4-11 ─┼→ P4-13              (测试用例完善+标记注册)
P4-12 ─┘
P4-14(性能) ─┐
P4-15(韧性) ─┼─ (Phase 4 硬性通过标准, 不可跳过)
P4-16(安全) ─┘

(Phase 5 画像 — 最低优先级)
P5-01 → P5-02 → P5-03 → P5-07  (推断: 风险→期限→矛盾→LLM注入)
          P3-15 → P5-05 → P5-06          (问卷→衰减→自适应阈值)
P5-08                           (画像测试)

PD-02 ← P1-03, P1-05, P2-11a  (精简版, 约16h)
```

---

## 汇总统计

| 阶段 | 任务数 | 估时(h) | 实际天数(1人) | 实际天数(2人) |
|------|:-----:|:-------:|:------------:|:------------:|
| PRE | 4 | 14 | 1.75 | 0.9 |
| T0 | 4 | 12 | 1.5 | 0.75 |
| MVP | 6 | 40 | 5 | 2.5 |
| Phase 1 | 24 | 164 | 20.5 | 10.25 |
| Phase 2 | 19 | 140 | 17.5 | 8.75 |
| Phase 3 | 18 | 206 | 25.75 | 12.9 |
| Phase 4 | 17 | 176 | 22 | 11 |
| Phase 5 | 7 | 108 | 13.5 | 6.75 |
| Phase D | 1 | 16 | 2 | 1 |
| **总计** | **100** | **876** | **109.5** | **~54.75** |

**估时偏差说明（加粗为 Round 1+2 修复修正项）：**
- PRE: 12h → 1.5d（无变化）
- **T0: 8h → 12h（Round 1 新增 T0-01-A DegradationTracker get_log 封装 + Round 2 新增 T0-01-B Pre-Schema 定义。两个前置均不可省略，因 T0-01 需要降级记录非空且有类型校验框架才可靠接线）**
- **MVP: 36h→40h（+4h: PD-01 条件推理提前纳入，使 MVP 首次交付即可看到分情景建议。实际合计 40h=5d）**
- **Phase 1: 124h→164h（+40h: 新增 P1-06-A f_context_builder.py 预重构 8h、P1-22 category.py→code_utils.py 提取扩展 4h→12h +8h；P1-08-B prompts.py 拆分从 Phase 3 提前 4h；原标 124h 即不等于任务实际合计 148h，Round 1 修复后实际为 164h）**
- Phase 2: 140h → 17.5d（P2-11 拆分，点估计 16h 留 Phase 2；置信区间 +24h 移至 Phase 4；新增集成测试 P2-14-B +8h）
- **Phase 3: 198h→206h（+8h: 新增 P3-11-T +4h、P3-12-T +4h；P3-14 拆分移至 Phase 1 -4h；P3-09 拆为 P3-09a 2h + P3-09b 16h 移至 Phase 4；P3-15 TUI 问卷 +40h 和 P3-16 事实校验器 +24h 从 Phase 4/5 提前。原标 198 即不等于任务实际合计）**
- **Phase 4: 158h→176h（+18h: P2-11b 置信区间 +24h、P3-09b 口径修正 +16h；P4-07 事实校验器移至 Phase 3 -24h；P4-14/15/16 各从 6h→12h +18h。原标 158 即不等于任务实际合计）**
- Phase 5: 108h → 13.5d（P5-04 TUI 问卷提前至 Phase 3，减少 40h；P5-06 安全哨兵增加 4h）
- **Phase D: 20h→16h（PD-01 已提前至 MVP-06，剩余 PD-02 精简至 16h 含砍项建议）**

**关键依赖链：**
- **最长串行链：PRE-01 → P1-03 → P2-01 → P2-08 → P2-14 → P2-14-B → P3-08 → P3-09a → P3-10 = 8 步硬串行（实际 15+ 节点含隐藏扇入。降级验收标准见 P3-08）**
- 第二长链：P1-04 → P1-05 → P2-11a → P2-11b(Phase 4) → P4-01 → P4-02 → P4-03 = **6 步**
- 完全独立无依赖：MVP-01、MVP-02、MVP-04、P1-11、P4-09(缓存TTL)、P3-15(TUI 问卷)、P3-16(事实校验器)
