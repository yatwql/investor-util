# 实现计划归档 — v0.12.x

> 归档时间：2026-10-03（v0.12.2-dev 迭代内完成，plan-72；本文件为 0.12 系列首份计划归档）
> 原始文件：`docs/managements/plan.md（当前迭代部分）`
> 涵盖版本：v0.12.2-dev（2026-10-03：plan-72 基金申购限购信息接入·持仓展示面）
> 归档内容：plan-72 完成态记录（数据链路 → 展示集成 → 文档登记三迭代，P0 门禁十项全绿）
> 追加归档：2026-10-05 plan-76 持仓变动复盘（快照事件级）四迭代完成（见文末章节）
> 追加归档：2026-10-05 plan-77 What-if 回放交易成本建模与基准对比（whatif_trade_cost）四迭代完成（见文末章节）
> 追加归档：2026-10-06 plan-78 因子动物园目录评测（factor_zoo_catalog）先决门槛三指标评测判定转正立项（见文末章节）
> 追加归档：2026-10-06 plan-79 事件窗量化对照（event_window_impact）先决门槛三段通过并四迭代完成（见文末章节）
> 设计文档索引：plan-72 的设计文档 [`fund-purchase-limit-design.md`](fund-purchase-limit/fund-purchase-limit-design.md) **已随 plan-74 完成一并归档**（本目录 `fund-purchase-limit/`）；plan-73 的 LLM 上下文设计同在 `fund-purchase-limit/fund-purchase-limit-llm-context-design.md`（设计 + 已实施）；plan-76 的快照事件级设计在本目录 `holding-change-review/holding-change-review-design.md`（已实施，§15 实施与验收记录）；plan-77 的 What-if 成本与基准设计在本目录 `whatif-cost-benchmark/whatif-cost-benchmark-design.md`（已实施，§14 门槛与验收记录）；plan-78 的因子目录评测设计在本目录 `factor-zoo-catalog/factor-zoo-catalog-design.md`（已评测·判定转正立项，§13 判定记录）；plan-79 的事件窗设计在本目录 `event-window-impact/event-window-impact-design.md`（已实施，§14 判定记录）

---

### P3 — 已完成（plan-72 完成态，2026-10-03 归档）

#### ✅ `plan-72` 基金申购限购信息接入（持仓展示）— 已完成（2026-10-03）

**动机**：QDII 等基金大量处于「限大额 / 暂停申购」状态（实测 QDII/海外股票类 738 只中 445 只限购），持仓界面无从得知；限购也直接影响「同类持仓合并」可行性——目标基金限购时申购合并路径不成立。数据源已实测可用（天天基金申购状态总表，27,695 行，含申购状态与日累计限定金额）。

**动作**：按 [`fund-purchase-limit-design.md`](fund-purchase-limit/fund-purchase-limit-design.md) 实施——**本期 = 迭代 1~3**（数据链路 → 展示集成 → 文档登记，每迭代验收标准见设计文档 §8）；合并/调仓分析联动为**迭代 4（二期）**（设计文档 §6），已另立 `plan-74`。**评审前提**：稳定性优先（「数据需要稳定，才有意义」），四层保障（§3.4）为硬约束。

**完成态（2026-10-03）**：

- **迭代 1 数据链路**：`providers/tiantian_purchase.py`（直连解析 + akshare 备链 + `purchase_schema` 载荷准入 + 值域体检）+ `fetcher/fund_purchase.py`（四级降级 + 会话复用单次经链 + `data_status` 记录）+ `_DEFAULT_CHAINS["fund_purchase"]` 注册 + reliability §4.2 表同步；48 个单测绿；手工真实抓取验收 HTTP 200 / 27,695 行 / `purchase_schema=1`（唯一出网项，测试套件全程无网）。
- **迭代 2 展示集成**：`purchase_status_data` 契约注入 pipeline（full 路径经 `prepare_report_data`、both 路径就地构建）+ Excel 市值明细末列「申购状态」条件列（cost_lots 先例）+ HTML 持仓页条件列 + 双端口径脚注（天天基金渠道口径）+ 陈旧阶梯（≤3 / 4~7 / >7 交易日按交易日历计，长假不计）+ 展示单源 `report/purchase_status.py`（文案/判据/脚注 Excel 与 HTML 共用）；开关 `fund_purchase_limit` 入注册表报告组（默认开，数据不可用静默隐列，逐字节回退既有输出）。
- **迭代 3 文档登记**：`datasource.md` 新源行、`datasource-reliability.md` §3.11 详表节、`testplan.md` 用例登记、`technical.md` 附录 H 契约 + 功能语义命名表登记、`changelog.md` 条目、`folders.md`/`test-coverage.md` 快照刷新；**P0 门禁十项全绿**（`test-runner.py --mode dev-verify` 3,612 通过 + 9 个 `--ci` 脚本），全量单测 8,115 通过，`ruff check`/`format --check` 零告警。

**遗留**：迭代 4（合并/调仓联动）→ `plan-74`（前置已满足，方案与验收见设计文档 §6/§8）。

---

## plan-74 基金申购限购合并/调仓联动（plan-72 迭代 4）— ✅ 已完成（2026-10-03）

> 设计文档：[`docs/archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-advice-design.md`](fund-purchase-limit/fund-purchase-limit-advice-design.md)（设计 + 已实施）。

**完成摘要**（四迭代，每迭代独立可回滚）：

1. **受限索引与判定原语**：`report/purchase_status.py` 新增 `_filter_restricted_rows`（共享筛选单源，与单元格同源格式化）+ `build_restricted_index`（契约条件字段 `restricted_index`，编排层注入，准入四条 → 空索引回退）；`analysis/purchase_feasibility.py`（`evaluate_purchase_feasibility` + `FEASIBILITY_MAX_DAYS=60` 交易日 + `describe_feasibility` 单源话术）；单元测试与边缘样本（非正输入/NaN/Inf/极端量级）。
2. **What-if 接线（唯一注入面）**：`whatif_operations._purchase_restricted_index` 单点挂载（经缓存链取契约、异常兜底空索引、debug 观测）→ `build_whatif_data(restricted_index=…)` 买入腿判定（新增 = 目标成本全额 / 加仓 = 成本增量；卖出腿不判定）→ 契约条件键 `feasibility`（仅命中追加，降级逐字节回退）→ Excel 持仓变动明细尾部提示块（含不可行标红）+ HTML ⑦申购受限提示节（缺席整节不出现）。
3. **回归网与零改动断言**：既有回归网（action/rebalance/whatif 双端/handlers/cli/web）全绿；`test_action_advisor.py::TestPurchaseRestrictionOutOfScope` 结构性断言两面签名与输出零限购字段渗入。
4. **文档登记**：`technical.md` §6.7 语义表 10 行 + 附录 H `purchase_status_data` 6 键与 What-if 消费方；`testplan.md` §1.1 模块行；`folders.md` 目录树（3 新文件）；`test-coverage.md` 计数刷新；`changelog.md` Added 条目；设计文档改完成态。

**范围决策**：调仓建议与行动摘要**不在范围**（三种候选操作全为卖出，申购限购不约束卖出；摘要是计数拼接无注入落点）；what-if 目标持仓为唯一注入面。

## plan-73 限购信息接入 LLM 分析维度（智囊团复盘 / 穿透深析提示词扩展）— ✅ 已完成（2026-10-03）

## plan-75 持仓分类汇总区块追加申购状态列 — ✅ 已完成（2026-10-03）

**动机**：区块①（市值核算明细）在 plan-72 已有申购状态列，区块②（持仓分类汇总）分类视角缺可申购性。

**完成摘要**：两端一致交付——`report/holdings_detail_sheet.py` 区块②末列追加「申购状态」（`_CAT_PURCHASE_HEADERS`，与 `cost_lots` 可选列组合保持末列次序）+ `report_template.html` 持仓分类表表头/明细行/小计/总计四处条件块（复用同一 `purchase_status_display`，cells 文案与 Excel 逐字一致）；明细行经 `format_purchase_status_cell` 单源渲染、分组小计/总计行留空（非可聚合指标，与区块①同语义）；判据 `purchase_column_visible` 单源，开关复用 `fund_purchase_limit` 不新增；降级（关 / `available=False`）列缺席逐字节回退；口径脚注复用区块①②之间既有那一行（位置天然覆盖两块）；HTML 持仓分类表不在本次范围。新增 `test_holdings_detail_sheet.py::TestCategoryPurchaseColumn` 6 用例 + `test_purchase_status.py::TestCategoryPurchaseTemplate` 4 用例（表头/明细文案/小计空格/总计结构）；文档同步（reports-instruction 特性行 / how-to-config 开关行 / technical 附录 H 两处 / faq 问答）。


> 设计文档：[`docs/archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-llm-context-design.md`](fund-purchase-limit/fund-purchase-limit-llm-context-design.md)（设计 + 已实施）。

**完成摘要**（四迭代，每迭代独立可回滚）：

1. **单源渲染器与契约字段**：`report/purchase_status.py::build_purchase_constraint_block`（准入四条任一不过 → 空串；行序 = 持仓序、缺名回退代码、陈旧附标、尾行硬约束声明）+ 契约条件字段 `constraint_block`（`build_purchase_status_data(holdings_details=…)` 装配；both/basic/What-if 取契约路径不传 → 恒空零开销）；编排层调用点传持仓名/码列表。
2. **主路径接线与指纹**：`generate_all_llm` 提取同一实例 → 预检侧 `_compute_module_cache_info` 与写侧 `_dispatch_llm_workers` → 四模块 `generate_*` → `generate_llm_module` → `skeleton` 统一附录第 4 段（`_build_prompt_appendix` 组装守卫「任一段非空即返回」，缺省 ≡ 空块逐字节）；`ModuleFingerprintInputs.purchase_block` 条件并入四个 builder（空块 part 不追加），接线前录制四模块基线并断言空块 == 黄金值（防分隔符换哈希）；注入/缺席各留 debug 观测。
3. **覆盖面核验（辩论 / 自检 / 新闻批量）**：辩论 pro/con/synthesis 三处调用传块 + `_fp_inputs` 并入（synthesis 走组装守卫块独立成段）；`run_self_review`/`generate_self_review` 形参链 + `self_review_fingerprint(purchase_block=…)` 条件并入；新闻批量 6 函数透传（`_fetch_llm_and_news` 同源提取 → `build_news_data` → `_apply_llm_enhancement` → `run_news_correlation_safe` → `enhance_news_correlation` → `_build_news_hooks`：批量提示词拼块 + `holdings_fp` 条件并入逐级影响逐条缓存键）；核验清单 1~5 实跑——9 个 `generate_llm_module` 调用点全归族、附录唯一注入点无旁路、`call_llm` 零直调、实验缝不构造分析 prompt（天然排除）。
4. **测试与文档登记**：`test_purchase_constraint_injection.py` 18 用例（四模块/辩论三章/自检/新闻批量「完备含块 vs 降级不含」成对、提取单源 6 函数透传、指纹三态）+ 指纹基线与预检/写同源 + 附录组装守卫与缺省等价 + 渲染器契约与边缘样本；`technical.md` §6.7 语义表 4 行与附录 H 消费方锚、`testplan.md` §1.1 模块行、`folders.md`/`test-coverage.md` 计数、`changelog.md` 条目。

**范围决策**：both/basic 路径无 LLM 章（契约路径块恒空零开销）；实验缝与规则层/数值层不构造分析 prompt（按分派规则排除）；新闻批量接线不裁剪（§3.2 预留裁剪项未启用，无须用户确认缩减）。

## plan-76 持仓变动复盘（holding_change_review，快照事件级）— ✅ 已完成（2026-10-05）

> 设计文档：[`docs/archive/v0.12.x/holding-change-review/holding-change-review-design.md`](holding-change-review/holding-change-review-design.md)（已实施，含 §15 实施与验收记录）。

**先决门槛（三段全过）**：① 复盘窗口 28 个有效期（≥12）/ 71 个变动事件（≥10）真实快照实测；② 「区间净额推断、非逐笔」局限标注与事件表在 Excel/HTML 两端同源常驻（测试锁定）；③ 结论经人工认可有启发——10-02 全量清仓→10-03 同名新增（13 代码、净市值≈原组合）判定为**疑似账户结构/数据结构变更**，不作交易结论，已固化 `detect_account_reorder` 双形态识别（清仓→新增优先，≥5 代码阈值）。

**完成摘要**（四迭代）：

1. **事件抽取与契约**：`analysis/holding_change_events.py`（`extract_change_events`/`build_holding_change_events`，快照按日去重 + 逐对差分 + 份额净变动分类 + 缺字段降级不虚构，`change_event` 契约字段）；**快照保留 60 → 180 天**（`core/constants.py`/`config/_config_defaults.py`/`report/_snapshot.py`/`data/config/config.json` 四处同步）。
2. **指标纯计算**：`analysis/holding_change_metrics.py`（变动频率/加减清仓结构/意图对账 `build_intent_reconciliation`/交易日模式 + `detect_account_reorder` 账户重排双形态识别）。
3. **双端报告接线**：`report/holding_change_panel.py`（契约装配 → view → Excel sheet + HTML partial 单源渲染，章默认序在数据源可用性矩阵/基本面快照/LLM 用量面板之前，`LIMITATIONS_NOTE` 两端常驻，关态逐字节不变）+ 管线缝 `inject_holding_change_data`（both/full）+ 章节可见性/目录/TOC/注册表测试同步。
4. **LLM 归因（双轨）**：附录**第 5 段** `holding_change_block`（prompt_block 与展示文本同源渲染）随四模块 + 辩论 pro/con/synthesis + 生成后自检携带，`ModuleFingerprintInputs.holding_change_block` 按段条件并入（空块逐字节不变）；注册表串行模块 `holding_change_review`（`llm/holding_change_review.py`：准入闸门 → 信号窗 top10 → `holding_change_review_fingerprint` 内容寻址 → 结果写 `holding_change_data.llm_review`，失败登记不外抛），`enabled_llm.holding_change` 默认开（章由实验开关门控）。

**测试与文档**：测试 88 项（events 9+edge 7 / metrics 15 / injection 23 / panel 26+edge 8）；需求 **R-HCR-01~06**（requirements §6.13）、reports-instruction 18 页签 9 组、TUI 菜单 8-11 号、technical 语义命名与附录 H、testplan 批 7 映射、folders/test-coverage 快照同步；P0 `dev-verify` + 十守护 `--ci` 全绿。


## plan-77 What-if 回放交易成本建模与基准对比（whatif_trade_cost）— ✅ 已完成（2026-10-05）

> 设计文档：[`docs/archive/v0.12.x/whatif-cost-benchmark/whatif-cost-benchmark-design.md`](whatif-cost-benchmark/whatif-cost-benchmark-design.md)（已实施，含 §14 门槛与验收记录）。

**先决门槛（三段全过）**：① 20 只样本（10 持仓 + 10 随机种子 20261006）经真实管线 `fetch_fee_index` 复测两费率侧均 **95% ≥ 80%**（唯一未覆盖 561910 为场内 ETF 无申赎费，归入未建模口径）；② 交易日持有期（「N年」×250 保守）/ FIFO 首见日下界 / 场内腿不建模三项口径经用户拍板；③ 换手 30% × ≈19.5bp 成本翻转案例（成本前 100.55>100.40 → 成本后 100.35<100.40）人工复核入网。

**完成摘要**（四迭代）：

1. **成本模型**：`analysis/trade_cost_model.py`（快照事件 FIFO 批次重放：期初批首见日下界 + 逐批判档加权 + 腿级费用聚合 → `trade_cost` 契约，纯计算零 I/O；未建模腿显式标注、未知 `fees_complete=False` 不冒充 0）；费率表选档与文本解析下沉 `analysis/fee_schedule_model.py`（金额分档/交易日持有期阶梯/单档与配置构建，边界左闭右开）。
2. **费率数据三级可得性**：`providers/tiantian_fund_fee.py`（F10 费用页直连 + `FEE_SCHEMA` 载荷准入）→ `fetcher/fund_fee.py::fetch_fee_index`（链注册 `fund_fee` = `tiantian_f10` → `akshare_fee` 备链 + 过期缓存，`refresh` 缓存组）→ 申购侧 F10 优惠档与申购状态全量表「手续费」列（`table_single`/`table_multi`）→ `fund_fee_fallback` 配置兜底（仅补在线不可得侧，不覆盖）。
3. **基准映射与双端面板**：`analysis/benchmark_index_resolver.py`（config `whatif_benchmark_index` → 目标持仓基准文本反查 `comparison_indices` → 默认 sh000300，源标注零 I/O）+ `report/whatif_cost_panel.py`（成本汇总/逐腿 11 列 + t0 一次性扣费成本前/后差对原 100 基线 + 基准曲线 LOCF 对齐归一，分阶段降级）；Excel 第 5 页签「交易成本对比」+ HTML⑧ 区（图表负载裁剪契约、说明区条件重编号⑨/⑧）；开关 `whatif_trade_cost` 实验组默认关。
4. **回归网与文档**：关态 sha256 黄金断言（与产出前 `git HEAD` 模板同数据渲染逐字节一致）+ 换手翻转回归 + Excel/HTML 双端数值一致；`trade_cost_model.py` 835 行超红线按拆分纪律下沉 `fee_schedule_model.py`（`EXEMPTIONS` 不新增）。

**测试与文档**：需求 **R-WIF-12~14**（requirements §6.11）、testplan 批 8 载体、reports-instruction 条件页签与产物描述、TUI 菜单 12-28 号与开关 31 项（实验 5）、datasource(-reliability) `fund_fee` 链/缓存行、how-to-config 两个配置键、technical 语义命名表 7 条、folders/test-coverage 快照同步；P0 `dev-verify` + 十守护 `--ci` 全绿。

## plan-78 因子动物园目录评测（factor_zoo_catalog）— ✅ 已完成（2026-10-06）

> 设计文档：[`docs/archive/v0.12.x/factor-zoo-catalog/factor-zoo-catalog-design.md`](factor-zoo-catalog/factor-zoo-catalog-design.md)（已评测·判定转正立项，含 §13 判定记录）。

**先决门槛（即评测本体，三指标全过）**：A 字段可得率 **23/25 = 92% ≥ 80%**（未过 2 项 `fund_pb`/`fund_size_log_cap` 因 push2 扩展字段空值判源侧暂不可用，挂 rf-592 可复评）；B 低相关占比 **19/23 = 82.6% ≥ 30%**（分母 23 ≥ 10，`rebalance_overflow` 族按设计降级；高相关 4 项均为市场方向类因子 vs 市场温度族：vwma_dev_20 0.61 / bias_60 0.61 / ma_cross 0.60 / rsv_9 0.54）；C 冷启动估算 **12.831s ÷ 报告基线 446.255s = 2.9% ≤ 20%**（池外冷样本均延迟 × 请求数，温态 0.217s 不作判据；基线 = perf 近 5 次 full 中位数）。**判定：转正立项** → 实施转 plan-81。

**完成摘要**：

1. **评测脚本**：`scripts/factor_zoo_eval.py`（阶段 `catalog|fields|signals|timing|verdict|all`；25 因子五来源族目录冻结、门槛口径预注册入判定书；生产代码零改动、无 report/llm 导入、字段取数仅经既有链路、相关性复用 `analysis/correlation._pearson_pvalue`、产物只落 `docs/tmp/factor-zoo/`）。
2. **股票池只读复用**：穿透 `compute_penetration_top10` 按 `codes` 列表形状递归抽取 ∪ 直接 A 股持仓（`is_a_share_stock` 名称+代码双维排除 00 前缀重叠场外基金）——实测直接 3 + 穿透 9 = 9 只。
3. **相关性口径**：Δ 一阶差分去趋势 Pearson；季频/阶跃信号（Δ 非零占比 <5%）按结构性不相关 ρ=0；不可评估 fail-closed 不计低相关；族对齐对数 <30 剔除。
4. **回归网**：40 项脚本单测（A/B/C 阈值恰等边界、判定三态、基线读取、相关性口径、注入探针全离线；edge 空输入/退化数据/极端值 fail-closed）。

**测试与文档**：folders 目录树/统计、test-coverage 快照、vibe 研究文档与归档索引链接同步；评测期自审 rf-591（对数市值非有限值）修复入网、rf-592（push2 扩展字段空值）挂待处理；P0 `dev-verify` + 十守护 `--ci` 全绿。

## plan-79 事件窗量化对照（event_window_impact）— ✅ 已完成（2026-10-06）

> 设计文档：[`docs/archive/v0.12.x/event-window-impact/event-window-impact-design.md`](event-window-impact/event-window-impact-design.md)（已实施，含 §14 判定记录）。

**先决门槛（三段全过）**：① 新闻日期字段结构化可用率 **100%（22/22）≥ 80%**（`ctime` 全可解析；`llm_news_item_*` 极性资产 22 条三元组：利好 14 / 中性 7 / 利空 1）；② 窗口口径唯一可判定——严格 ±5 单源经 8 例「窗口超出行情范围」降级实证，半窗截断评估后否决（维持设计唯一口径，23 条严格可用事件已足门槛 3）；③ 真实链路采样（4 份既有报告新闻 × 当前持仓穿透 × 真实行情/基准，零 LLM 调用）10 例人工比对 **9/10 ≥ 7**（一致 3 + 分歧可解释 6 + 中性不判 1 不入分子），用户判定「通过」，采样产物 `docs/tmp/event_gate3_sample.json`。

**完成摘要**：

1. **纯计算**：`analysis/event_window_impact.py`（事件日→交易日映射、±5 交易日切窗 LOCF 对齐、超额与方向比对，零 I/O）；手算对照与边界用例入网。
2. **事件表编排**：`report/event_impact_panel.py`（新闻→事件行组装、品种关键词索引、注入式行情/基准取数、逐事件降级计数不截断、`available=false` 传导、分歧例 `prompt_block` 只收「比对=分歧」行、view 与页签同文写入）。
3. **报告双端 + LLM 注入**：开关 `event_window_impact`（实验组第 6 项，默认关）；注册表新增 `event_impact` 章（附录三项顺延）；seam `inject_event_impact_data` 经**新闻先行串行段**注入（新闻 collect → 注入事件表 → 提交 LLM，解决「极性由 LLM 产出、分歧例须同轮进 LLM」的鸡生蛋）；分歧例块进**统一 prompt 附录**随四模块+辩论+自检携带，指纹非空条件并入、空块逐字节不变；HTML partial + Excel 页签双端消费同一 view；关态走原并行路径逐字节不变。
4. **回归网**：纯计算 33 + 编排 25 + 注入链路/接线 39 项新用例（关态回退哈希、双端单元格同文、新闻先行串行时序、分歧例召回 100%、章隐藏不消耗编号、日历 fixture 装配栈序）全绿。

**测试与文档**：开关 32 项（实验 6）、TUI 实验段 8~13；手册章节表/可见性总览/语义命名表/附录 H/目录树与统计同步；自审 rf-594（Web 面板配置项表实验行缺 whatif 与编号段陈旧）修复入网、rf-593（辩论指纹未并入统一附录块，pre-existing）挂待处理；P0 `dev-verify` + 十守护 `--ci` 全绿。

## plan-82 流程耗时优化（执行纪律 + 收尾触点清单 + 顺序依赖二分工具）— ✅ 已完成（2026-10-06）

**动机**：plan-76~79 实测单任务墙钟 97~214 分钟，而门禁机器时间仅 3~4 分钟（<3%）——耗时主因是「触点数 × 往返轮次」：文档触点靠守护报错被动驱动（每轮一次完整往返）、顺序依赖缺陷手工二分 10+ 轮、提交前与 pre-commit 钩子重复跑十守护。

**落地**：

1. `CLAUDE.md` 执行纪律修订：便宜红线（`ruff`/`check-file-length`）随每批代码改动跑；编辑与 `--sync`/检查类脚本永不同批（防竞态）；提交前免重复十守护（pre-commit 钩子内含 `--sync`+十守护，失败即中止）；收尾一次性枚举全量 finding 批量修；修正旧文案「四个 `--ci` 脚本」与现行十守护不符。
2. `developer-guide.md` 新增「计划收尾：文档触点清单与一次性枚举」——按任务类型（新报告章节/新开关/新文件/新测试/LLM 模块/seam/通用收尾）列必同步触点全集 + 三步工作流（一次枚举 → 批量修复 → 单次复核）。
3. `scripts/find-order-dependent-test.py`：顺序依赖污染源二分定位（单跑确认 → 收集参考顺序 → 复现门 → 最小失败前缀二分（记忆化）→ 单文件配对确认/预算内精简 → 最小复现命令；`--candidates`/`--dry-run`/`--max-runs`），22 项单测含临时目录端到端泄漏复现。
4. guard 类测试写死派生量全仓审计：「断言+关键词+数字」扫描命中 12 处逐一核验均为合成夹具/固定内容/结构不变量，无遗留。

**结果**：门禁强度不变（十守护/测试门禁/pre-commit 一并保留），只收敛往返次数；触点清单见 `developer-guide.md`，纪律见 `CLAUDE.md`「执行效率（合并往返）」，变更记录见 `changelog.md` 同日条目。
