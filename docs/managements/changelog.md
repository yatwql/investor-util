# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.1]**（2026-10-03）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.2-dev] - 开发中（未发布）

### Added

- **基金申购限购信息接入（`plan-72` 迭代 1~3）**：天天基金申购状态总表全量取数（直连解析 + akshare 备链 + `purchase_schema` 载荷准入 + 会话复用单次经链），持仓明细市值明细末列「申购状态」条件列（限大额日限额/暂停申购下一开放日，Excel 与 HTML 单源文案）+ 双端口径脚注（天天基金渠道口径）与按交易日历的 ≤3 / 4~7 / >7 交易日三档时效标注；功能开关 `fund_purchase_limit`（默认开，注册表报告组），数据全链失败 `available=False` 时静默隐列、四层降级不阻断报告生成（设计文档 `docs/plan/fund-purchase-limit-design.md`）
- **申购限购约束块接入全部 LLM 分析章（`plan-73` 四迭代）**：单源渲染器 `build_purchase_constraint_block`（契约条件字段 `constraint_block`，准入四条任一不过 → 空串，行序 = 持仓序、字段值与单元格同源）→ `generate_all_llm` 提取同一实例交标准模式四模块统一 prompt 附录第 4 段（`_build_prompt_appendix` 组装守卫「任一段非空即返回」，缺省与空块逐字节一致）+ 指纹输入字段 `purchase_block` 条件并入（进提示词必进指纹，接线前录制四模块基线防分隔符换哈希）+ 辩论 pro/con/synthesis、生成后自检、新闻批量 hooks（批量提示词拼块 + `holdings_fp` 指纹并入逐级影响逐条缓存键）同源接线，6 函数透传链单测覆盖；both/basic/What-if 取契约路径块恒空零开销，降级态提示词与缓存键双不变（设计文档 `docs/plan/fund-purchase-limit-llm-context-design.md`）
- **What-if 目标持仓申购受限提示（`plan-74` 四迭代）**：受限标的预格式化索引 `restricted_index`（契约条件字段，与单元格同源格式化，编排层注入 + What-if 路径单点挂载）+ 申购可行性判定 `evaluate_purchase_feasibility`（限大额 `ceil(金额÷日限额)` 交易日估算、超 60 交易日判不可行、暂停引用下一开放日、金额/限额未知不给天数）+ 目标持仓新增/加仓腿提示注入 `build_whatif_data(restricted_index=…)`（卖出腿不判定；条件键 `feasibility`，Excel 持仓变动明细尾部 + HTML⑦申购受限提示节）；降级态（开关关/不可用/时效超限/取契约异常）契约与输出逐字节回退现网行为，调仓建议与行动摘要零改动（设计文档 `docs/plan/fund-purchase-limit-advice-design.md`）

### Changed

- **管理/用户文档补齐 plan-73 限购约束块消费方（rf-569，全量核对）**：`llm-technical.md` 补注入链四处（§3.2 附录图第 4 段、§4.1 提示词覆盖表 `purchase_constraint_block` 行、§4.4 `extract_purchase_constraint_block` 唯一提取点、§8.2 统一附录四段与组装守卫）；`how-to-config.md` `fund_purchase_limit` 消费方补 What-if 提示与 LLM 约束上下文（关＝三者同时失效）；`datasource-reliability` §3.11 用途句补 LLM 消费方；`how-to-config-llm.md` 模块启停节补约束上下文联动；`reports-instruction` ④节与 `README` 智囊团行补可执行性约束说明；核对结论：其余管理/用户文档与实现一致（`datasource.md` 路由表无消费方列、testplan 计数外置 test-coverage、developer-guide 现状描述准确，均无须改）
- **P0/P1 门禁并入 `unit_report` 域（rf-564 / rf-565）**：报告生成域（98 文件 / 2,120 用例）此前不在 `dev-verify`、`verify`、`verify,regression` 任何档（modes.py `report` 专用模式零调用方），What-if 页面级测试「⑦/⑧ 说明」编号漂移因此带病提交——`dev-verify`（3,638→5,454）与 `verify`（5,796→7,917）marker 并入 `unit_report`，`test-runner modes.py` 与 `collect-test-coverage.py` 双处 marker 定义同步并互注防漂移；`test_whatif_html.py` 断言与 `whatif_template.html` 编号同步（「⑦ 说明」→「⑧ 说明」+ ⑦受限节缺席断言）
- **`constraint_block` 提取收敛单源 helper（rf-567）**：编排层与新闻链两处相同的字典路径表达式收敛为 `llm.extract_purchase_constraint_block(pipeline_data)`（唯一提取点，契约键/嵌套调整只改此处，防漏改一处致块静默缺席），两侧调用同一实现并补三态单测
- 限购总表缓存显式注册进数据模块注册表（data_type `fund_purchase` + 精确键 `fund_purchase_status_table`，TTL 与官方净值同源 `CACHE_DAILY` 24h）：此前未注册、靠 `get_ttl` 回退巧合与净值同档，回退逻辑或常量一变即无声漂移；仍不入菜单刷新组（大表不随菜单强抓），`datasource.md` 脚注同步
- **限购线文档一致性核对修正**：`reports-instruction.md` 持仓市值明细 15→16 列（申购状态条件列 + 脚注/时效/降级说明）与 What-if 申购受限提示块（页签表/产物/设计边界/功能对照表 4 处）；`requirements.md` R-WIF-05 输出描述与 R-WIF-06 网络语义（what-if 默认本地计算，提示经缓存链读限购总表：命中零联网/未命中现场取一次/失败静默兜底）；TUI/CLI 手册 What-if 段同源修正；FAQ 新增「申购状态」列问答；`datasource-reliability.md` 3.11 用途行补 What-if 消费方；README What-if 特性行补受限提示

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1（2026-10-03）
- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12 + v0.12.0（2026-09-15 ~ 2026-10-03）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12)
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
