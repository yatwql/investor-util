# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.2]**（2026-10-04）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.3-dev] - 开发中（未发布）

### Added

- **HTML**：正文大块默认折叠从「组合历史走势与回撤」扩展到「财经新闻热点与持仓关联分析」「组合演进」「持仓基本面」——章标题常显、内容默认收起，提示条带该章关键摘要（新闻条数 / 快照数与观察日数 / 财务指标与财报摘标的数），点击展开/收起；原生 `<details>` 键盘可达，锚点定位与打印展开复用 `fold.js`（对全部 `details.section-fold` 生效），「回到顶部」留在折叠块外（收起态仍可点）；新增结构回归用例（默认收起 / summary 首子元素 / 标题与回顶在折叠块外 / 提示条带摘要）

### Changed

- **LLM/日志**：「要求调整配置值」的提示一律回显当前值（**rf-577**）——思考耗尽提示回显 `<config_field>=<值>`（配置上下文由 `_process_success_response` 经线程局部注入，未注入时给通用建议、不编造数值）、Thinking 安全网日志回显 `max_tokens` 与思考配置现值、截断重试耗尽回显「当前 X → 已试 Y」与配置项名；429 并发/间隔、截断检测、worker 钳位、阈值超限等既有提示本已合规，密钥类仍只给文件名/条目名（不回显本体）；排查口径与覆盖点固化到 developer-guide「日志回显纪律」节
- **LLM**：429 诊断回显补 `pacing.min_interval` 现值——「当前配置」行同时列出 `pacing.max_concurrency` 与 `pacing.min_interval`（未声明标「未配置」），凡建议「加大 pacing.min_interval」处均带当前值，读者不必翻配置即可知道要从多少调到多少
- **LLM**：429 限速日志回显**当前实际并发配置**（全局 `llm_max_concurrency=…` + `provider[条目] pacing.max_concurrency=…`），并按「还有没有下降空间」给建议——端点已配到最低 1（如 kimi-main）时不再叫用户「调低端点并发」，改为提示调低全局值或加大 `min_interval`；两级并发均到底时明确「再调低并发已无益，429 更可能来自配额（RPM/TPM）或风控」（`api_base._concurrency_hint`，新增 3 个用例覆盖三种分支）
- **LLM**：429 限速日志提示增强——除「调低 `llm_max_concurrency`」外补「或为该 provider 条目配置 `pacing.max_concurrency` 按端点限流」，把用户引到正确的并发旋钮（新增用例断言两提示同时出现）
- **文档**：`llm-technical.md` §4.2.1 补「429 诊断回显」（含 `min_interval` 与「未配置」口径）与「策略惰性装载兜底」两行；`how-to-config-llm.md` 端点级节流补 429 回显性质、思考耗尽调参建议注明「日志直接回显字段名与当前值」；`faq.md` 429 问答改按日志诊断 + 三类旋钮作答（并点明单纯增大 `timeout_{模块}` 对 429 无效）；`testplan.md` R-LLM-10 载体补 `test_llm_api_multi.py`（endpoint_key 逐层下传）与惰性装载；数据快照同步——`test-coverage.md` 经 `--mode bench --update-docs` 回填（模式对应测试量 + 环境耗时对照表 + 采集日期 2026-10-04），`folders.md` 版本演进对照「当前开发版」列按**工作区**重跑（主程序 307/80,564、测试 430/128,389、代码行合计 224,759、测试用例 8,191、仓库 1,015 文件/296,973 行，口径说明同步为工作区读数）

### Fixed

- **安全**：密钥权限基线补漏（**rf-578**、**rf-574**）——`_SECRET_FILES` 只列 `llm_key.json`，漏掉同样持密钥本体的 `data_key.json`（datasink/hithink 内联明文 `api_key`、未跟踪且实测 644 world-readable），已补入清单；两密钥文件均 `chmod 600`（`llm_key.json` 即 rf-574 待执行项，执行后基线用例转绿）；该基线在本机 bench 汇总中报失败（文件不存在时仍跳过，CI 干净检出不受影响）
- **LLM**：修复端点节流（pacing）**从未生效**（**rf-575**）——多链调用 `_call_provider_entry` 漏传 `endpoint_key`，下游 `PacingGate("")` 恒空转，`llm_providers.json` 里 provider 条目声明的 `pacing.max_concurrency`（kimi-main/kimi-code/opencode-go）全部未落到调用路径，429 提示也回显不出端点配置（只见「全局 llm_max_concurrency=3」+泛化建议）；补传条目名后，同一端点的 429 提示改推「全局/间隔旋钮」而非叫用户配一个已经配好的参数；新增 api 层下传 + 重试骨架到达两级回归用例（去掉透传即红）
- **LLM**：修复 pacing 惰性装载静默失效（**rf-576**）——`_ensure_loaded()` 引用不存在的 `src.python.config.get_llm_providers`（必然 ImportError 被 debug 吞掉、按无约束处理），改读与生产装载同源的 `get_llm_config()._provider_list`；未经配置加载的入口（单测/脚本/doctor 概览）此前一律拿不到策略
- **测试**：条件推理死测试整改（**rf-568**）——原 `test_system_debate_conditional_scenario_exists` 瞄准一个全仓不存在的预留常量 `_SYSTEM_DEBATE_CONDITIONAL_SCENARIO`，十余轮条件 skip 全绿零覆盖；经确认该预留非计划功能后，改为 `TestConditionalScenarioInjection` 4 例断言真实行为（情景 name/desc 渲染进综合/标准两条 user prompt、scenarios 为空回退基线、开关门控、`skip_scenarios` 跳过），模块 docstring 同步更正；两处注入点变异实测均拦截
- **测试**：测试有效性自查修复（**rf-571** ~ **rf-573**）——① rf-571 补 429 并发回显的 `endpoint_key` 透传接线用例（原缺口：去掉透传后 7 个 429 用例全过）；② rf-572 `test_capture_snapshot_holdings_lookup` 断言落到 `save()` 快照对象，验「无匹配时 `shares/cost_price == 0.0`」；③ rf-573 `test_capture_snapshot_data_creation` 验 `total_value/total_cost/total_pnl` 多明细求和与账户持仓清单（原均只 `assert compute.called`，与 docstring 目标不符）——三者均经变异实测确认能拦截对应回归

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
