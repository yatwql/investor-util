# 实现计划归档 — v0.12.x

> 归档时间：2026-10-03（v0.12.2-dev 迭代内完成，plan-72；本文件为 0.12 系列首份计划归档）
> 原始文件：`docs/managements/plan.md（当前迭代部分）`
> 涵盖版本：v0.12.2-dev（2026-10-03：plan-72 基金申购限购信息接入·持仓展示面）
> 归档内容：plan-72 完成态记录（数据链路 → 展示集成 → 文档登记三迭代，P0 门禁十项全绿）
> 追加归档：2026-10-05 plan-76 持仓变动复盘（快照事件级）四迭代完成（见文末章节）
> 设计文档索引：plan-72 的设计文档 [`fund-purchase-limit-design.md`](fund-purchase-limit/fund-purchase-limit-design.md) **已随 plan-74 完成一并归档**（本目录 `fund-purchase-limit/`）；plan-73 的 LLM 上下文设计同在 `fund-purchase-limit/fund-purchase-limit-llm-context-design.md`（设计 + 已实施）；plan-76 的快照事件级设计在本目录 `holding-change-review/holding-change-review-design.md`（已实施，§15 实施与验收记录）

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
