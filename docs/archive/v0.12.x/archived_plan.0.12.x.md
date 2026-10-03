# 实现计划归档 — v0.12.x

> 归档时间：2026-10-03（v0.12.2-dev 迭代内完成，plan-72；本文件为 0.12 系列首份计划归档）
> 原始文件：`docs/managements/plan.md（当前迭代部分）`
> 涵盖版本：v0.12.2-dev（2026-10-03：plan-72 基金申购限购信息接入·持仓展示面）
> 归档内容：plan-72 完成态记录（数据链路 → 展示集成 → 文档登记三迭代，P0 门禁十项全绿）
> 设计文档索引：plan-72 的设计文档 [`fund-purchase-limit-design.md`](../../../plan/fund-purchase-limit-design.md) **保留在在办区**——plan-74（迭代 4 合并/调仓联动）仍消费其 §6 方案与 §8 验收，随 plan-74 完成一并归档；plan-73 的 LLM 上下文设计见 `../../../plan/fund-purchase-limit-llm-context-design.md`（待评审）

---

### P3 — 已完成（plan-72 完成态，2026-10-03 归档）

#### ✅ `plan-72` 基金申购限购信息接入（持仓展示）— 已完成（2026-10-03）

**动机**：QDII 等基金大量处于「限大额 / 暂停申购」状态（实测 QDII/海外股票类 738 只中 445 只限购），持仓界面无从得知；限购也直接影响「同类持仓合并」可行性——目标基金限购时申购合并路径不成立。数据源已实测可用（天天基金申购状态总表，27,695 行，含申购状态与日累计限定金额）。

**动作**：按 [`fund-purchase-limit-design.md`](../../../plan/fund-purchase-limit-design.md) 实施——**本期 = 迭代 1~3**（数据链路 → 展示集成 → 文档登记，每迭代验收标准见设计文档 §8）；合并/调仓分析联动为**迭代 4（二期）**（设计文档 §6），已另立 `plan-74`。**评审前提**：稳定性优先（「数据需要稳定，才有意义」），四层保障（§3.4）为硬约束。

**完成态（2026-10-03）**：

- **迭代 1 数据链路**：`providers/tiantian_purchase.py`（直连解析 + akshare 备链 + `purchase_schema` 载荷准入 + 值域体检）+ `fetcher/fund_purchase.py`（四级降级 + 会话复用单次经链 + `data_status` 记录）+ `_DEFAULT_CHAINS["fund_purchase"]` 注册 + reliability §4.2 表同步；48 个单测绿；手工真实抓取验收 HTTP 200 / 27,695 行 / `purchase_schema=1`（唯一出网项，测试套件全程无网）。
- **迭代 2 展示集成**：`purchase_status_data` 契约注入 pipeline（full 路径经 `prepare_report_data`、both 路径就地构建）+ Excel 市值明细末列「申购状态」条件列（cost_lots 先例）+ HTML 持仓页条件列 + 双端口径脚注（天天基金渠道口径）+ 陈旧阶梯（≤3 / 4~7 / >7 交易日按交易日历计，长假不计）+ 展示单源 `report/purchase_status.py`（文案/判据/脚注 Excel 与 HTML 共用）；开关 `fund_purchase_limit` 入注册表报告组（默认开，数据不可用静默隐列，逐字节回退既有输出）。
- **迭代 3 文档登记**：`datasource.md` 新源行、`datasource-reliability.md` §3.11 详表节、`testplan.md` 用例登记、`technical.md` 附录 H 契约 + 功能语义命名表登记、`changelog.md` 条目、`folders.md`/`test-coverage.md` 快照刷新；**P0 门禁十项全绿**（`test-runner.py --mode dev-verify` 3,612 通过 + 9 个 `--ci` 脚本），全量单测 8,115 通过，`ruff check`/`format --check` 零告警。

**遗留**：迭代 4（合并/调仓联动）→ `plan-74`（前置已满足，方案与验收见设计文档 §6/§8）。

---

## plan-74 基金申购限购合并/调仓联动（plan-72 迭代 4）— ✅ 已完成（2026-10-03）

> 设计文档：[`docs/plan/fund-purchase-limit-advice-design.md`](../../plan/fund-purchase-limit-advice-design.md)（设计 + 已实施）。

**完成摘要**（四迭代，每迭代独立可回滚）：

1. **受限索引与判定原语**：`report/purchase_status.py` 新增 `_filter_restricted_rows`（共享筛选单源，与单元格同源格式化）+ `build_restricted_index`（契约条件字段 `restricted_index`，编排层注入，准入四条 → 空索引回退）；`analysis/purchase_feasibility.py`（`evaluate_purchase_feasibility` + `FEASIBILITY_MAX_DAYS=60` 交易日 + `describe_feasibility` 单源话术）；单元测试与边缘样本（非正输入/NaN/Inf/极端量级）。
2. **What-if 接线（唯一注入面）**：`whatif_operations._purchase_restricted_index` 单点挂载（经缓存链取契约、异常兜底空索引、debug 观测）→ `build_whatif_data(restricted_index=…)` 买入腿判定（新增 = 目标成本全额 / 加仓 = 成本增量；卖出腿不判定）→ 契约条件键 `feasibility`（仅命中追加，降级逐字节回退）→ Excel 持仓变动明细尾部提示块（含不可行标红）+ HTML ⑦申购受限提示节（缺席整节不出现）。
3. **回归网与零改动断言**：既有回归网（action/rebalance/whatif 双端/handlers/cli/web）全绿；`test_action_advisor.py::TestPurchaseRestrictionOutOfScope` 结构性断言两面签名与输出零限购字段渗入。
4. **文档登记**：`technical.md` §6.7 语义表 10 行 + 附录 H `purchase_status_data` 6 键与 What-if 消费方；`testplan.md` §1.1 模块行；`folders.md` 目录树（3 新文件）；`test-coverage.md` 计数刷新；`changelog.md` Added 条目；设计文档改完成态。

**范围决策**：调仓建议与行动摘要**不在范围**（三种候选操作全为卖出，申购限购不约束卖出；摘要是计数拼接无注入落点）；what-if 目标持仓为唯一注入面。

## plan-73 限购信息接入 LLM 分析维度（智囊团复盘 / 穿透深析提示词扩展）— ✅ 已完成（2026-10-03）

> 设计文档：[`docs/plan/fund-purchase-limit-llm-context-design.md`](../../plan/fund-purchase-limit-llm-context-design.md)（设计 + 已实施）。

**完成摘要**（四迭代，每迭代独立可回滚）：

1. **单源渲染器与契约字段**：`report/purchase_status.py::build_purchase_constraint_block`（准入四条任一不过 → 空串；行序 = 持仓序、缺名回退代码、陈旧附标、尾行硬约束声明）+ 契约条件字段 `constraint_block`（`build_purchase_status_data(holdings_details=…)` 装配；both/basic/What-if 取契约路径不传 → 恒空零开销）；编排层调用点传持仓名/码列表。
2. **主路径接线与指纹**：`generate_all_llm` 提取同一实例 → 预检侧 `_compute_module_cache_info` 与写侧 `_dispatch_llm_workers` → 四模块 `generate_*` → `generate_llm_module` → `skeleton` 统一附录第 4 段（`_build_prompt_appendix` 组装守卫「任一段非空即返回」，缺省 ≡ 空块逐字节）；`ModuleFingerprintInputs.purchase_block` 条件并入四个 builder（空块 part 不追加），接线前录制四模块基线并断言空块 == 黄金值（防分隔符换哈希）；注入/缺席各留 debug 观测。
3. **覆盖面核验（辩论 / 自检 / 新闻批量）**：辩论 pro/con/synthesis 三处调用传块 + `_fp_inputs` 并入（synthesis 走组装守卫块独立成段）；`run_self_review`/`generate_self_review` 形参链 + `self_review_fingerprint(purchase_block=…)` 条件并入；新闻批量 6 函数透传（`_fetch_llm_and_news` 同源提取 → `build_news_data` → `_apply_llm_enhancement` → `run_news_correlation_safe` → `enhance_news_correlation` → `_build_news_hooks`：批量提示词拼块 + `holdings_fp` 条件并入逐级影响逐条缓存键）；核验清单 1~5 实跑——9 个 `generate_llm_module` 调用点全归族、附录唯一注入点无旁路、`call_llm` 零直调、实验缝不构造分析 prompt（天然排除）。
4. **测试与文档登记**：`test_purchase_constraint_injection.py` 18 用例（四模块/辩论三章/自检/新闻批量「完备含块 vs 降级不含」成对、提取单源 6 函数透传、指纹三态）+ 指纹基线与预检/写同源 + 附录组装守卫与缺省等价 + 渲染器契约与边缘样本；`technical.md` §6.7 语义表 4 行与附录 H 消费方锚、`testplan.md` §1.1 模块行、`folders.md`/`test-coverage.md` 计数、`changelog.md` 条目。

**范围决策**：both/basic 路径无 LLM 章（契约路径块恒空零开销）；实验缝与规则层/数值层不构造分析 prompt（按分派规则排除）；新闻批量接线不裁剪（§3.2 预留裁剪项未启用，无须用户确认缩减）。
