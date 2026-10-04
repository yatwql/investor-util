# 自我审查问题记录归档 — v0.12.x

> 归档时间：2026-10-03（v0.12.1 发布当日并入，0.12 系列首份）
> 原始文件：`docs/managements/review-findings.md`
> 涵盖版本：v0.12.1（2026-10-03）
> 归档内容：本迭代已修复的 rf 记录摘要行（v0.12.1 批次 rf-557 ~ rf-562；v0.12.2 批次 rf-563 ~ rf-570（限购线文档一致性、48h 技术债、plan-73 消费方补齐、CI 口径分叉根治）：报告目录分组线性投影与附录组、LLM 章级门控整章隐藏、JS 资产单源与打印断言、发布列与 changelog 发布指针一致性断言、跨组交错线性段拆块、实现与文档过期残留整改；v0.12.3 批次 rf-568、rf-571 ~ rf-578（测试有效性整改、pacing 端点节流生效与惰性装载修复、日志回显当前值纪律、密钥权限基线补漏、HTML 正文大块折叠扩展））

---

## 已修复问题

- rf-560 版本演进「最新发布」列（表头 + 说明行）无一致性断言，发版后靠人工记忆刷新——已完成（`release_tag` 断言：发布列全部出现处 == changelog 头部「最近发布 [X.Y.Z]（日期）」发布指针单源，`--fix` 自动同步）
- rf-561 目录语义分组跨组交错边界（跨组插号时组聚合与正文线性序不一致）——已完成（分组投影按线性连续段分块：组在号序断点拆块、同组可多块，展开恒等于正文线性序）
- rf-557 报告目录分组固定组序 + 组成员跨号段，目录展开序与正文线性序不一致（「3→15→4」跳号回跳）——已完成（组间动态排序 + 「附录」组，展开严格 1..N）
- rf-558 `enabled_llm` 禁用模块后 HTML 章节仍显示「待生成」占位（与用户手册「报告中不出现该页签」承诺漂移）——已完成（章级可见性：`LLM_MODULE_GATED_SECTIONS` 两端同口径整章隐藏）
- rf-559 测试/实现质量杂项：`_JS_ASSETS` 两函数各持副本、打印隐藏断言取「第一个 @media print 块」的脆弱定位——已完成（模块级 `JS_ASSETS` 单一来源 + 跨块查找断言）
- rf-562 实现残留过期描述与计数快照：「五组」注释×4（导航已六组）、technical.md JS 资产段旧名旧计数（`_JS_ASSETS`/8 个）、test-coverage 计数 6 处未随新增 13 用例刷新——已完成（注释改六组 / `JS_ASSETS` 9 个 / collect 全量回填）
- rf-563 已修复（2026-10-03）：限购线文档一致性核对——`reports-instruction` 列数 15→16 与 What-if 提示块、`requirements` R-WIF-05/06 输出与网络语义、TUI/CLI 手册零网络表述、FAQ/README/`datasource-reliability` 补述（变更见 changelog「限购线文档一致性核对修正」）。

- rf-564 ~ rf-567 已修复（2026-10-03）：48 小时实现技术债自查批次——What-if 页面级断言编号同步（plan-74 改模板漏改）、P0/P1 门禁并入 `unit_report` 域（98 文件首次进门禁，modes/collect 双处 marker 同步）、changelog「兔底」错字、`constraint_block` 提取收敛单源 helper（变更见 changelog「门禁并入」「单源」两更）。

- rf-569 已修复（2026-10-03）：全量文档核对补齐 plan-73 消费方——`llm-technical.md` 四处（§3.2 附录图第 4 段 / §4.1 提示词覆盖表 `purchase_constraint_block` 行 / §4.4 唯一提取点暴露段 / §8.2 统一附录四段）、`how-to-config.md` 开关消费方三合一、`datasource-reliability.md` 3.11 用途句 LLM 消费方、`how-to-config-llm.md` 约束上下文联动、`reports-instruction` ④节与 `README` 智囊团行（变更见 changelog「文档补齐」条）。

- rf-570 已修复（2026-10-03）：CI 五 job 同根因红（`--sync` 按工作区口径写 folders、CI 按 committed 树实测，受检文件长期游离修改致分叉）——根治靠提交游离修改（jev 两文件 `43d2d4d5`），机制防御采用**纪律条款**处置：`developer-guide.md` P0 门禁节补「`--sync` 统计快照口径（CI 分叉坑）」警示段（变更见 changelog「文档补齐」条）。


- rf-575 多链调用漏传 `endpoint_key` → provider 条目声明的 `pacing`（kimi-main 等在途并发上限）全链空转、429 提示也回显不出端点配置 —— 已修复 2026-10-04（`_call_provider_entry` 补传条目名 + api 层下传/重试骨架到达两级回归用例，变异实测拦截）
- rf-576 `pacing._ensure_loaded()` 惰性装载引用不存在的访问器 `src.python.config.get_llm_providers` → 必然 ImportError 被 debug 吞掉，未经配置加载的入口（单测/脚本/doctor 概览）拿不到策略、静默按无约束 —— 已修复 2026-10-04（改读 `get_llm_config()._provider_list`，与生产装载同源；两条惰性装载回归用例，变异实测拦截）
- rf-577 全仓「要求调整配置值」日志排查：思考耗尽提示（`api_base._extract_content`）、Thinking 安全网日志（`_api_claude`）、截断重试耗尽（`skeleton._handle_truncation`）三处只说「请增大 max_tokens/降 effort」却不给当前值，读者要翻配置才知道基数 —— 已修复 2026-10-04（三处回显 `<config_field>=<值>`/思考配置现值/「当前 X → 已试 Y」，密钥类保持只给文件名；新增 4 条回归用例均变异实测拦截；口径固化到 developer-guide「日志回显纪律」节）
- rf-578 安全基线密钥权限清单 `scenario/security/test_security.py::_SECRET_FILES` 只列 `llm_key.json`，漏掉同样持有密钥本体的 `data/config/data_key.json`（datasink/hithink 内联明文 `api_key`、未跟踪、实测 644 world-readable）；同时本机 `llm_key.json` 已被外部改写为 644，基线用例在 bench 汇总中报 4 处失败（末轮 summary 定位到本用例，该基线随 scenario/regression/verify/all 多轮重复执行） —— 已修复 2026-10-04（两密钥文件 chmod 600；`_SECRET_FILES` 补 `data_key.json` 并同步注释；文件不存在时用例仍跳过，CI 干净检出不受影响；变异实测：把 `data_key.json` 改回 644 即红）
- rf-574 `data/config/llm_key.json` 实际权限 644（other 可读），安全基线 `test_key_file_permissions_unix` 本机红（与代码改动无关，已 stash 验证） —— 已修复 2026-10-04（随密钥权限基线整改一并 `chmod 600`，用例转绿；与 rf-578 同批）
- rf-568 `test_debate_prompts.py::test_system_debate_conditional_scenario_exists` 条件 skip 十余次跑全空过：其瞄准的预留常量 `_SYSTEM_DEBATE_CONDITIONAL_SCENARIO` 全仓不存在，而条件推理实际实现是「情景注入 user prompt（`debate.conditional.scenarios` 的 name/desc 渲染）+ `_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL` 切换 system prompt」——测试验证目标与实现失配，形同虚设 —— 已修复 2026-10-04（经确认该预留常量非计划功能，改为断言真实行为的 `TestConditionalScenarioInjection` 4 例：name/desc 渲染进综合与标准两条路径、空配置回退、开关门控、`skip_scenarios` 跳过；删除死用例与 docstring 引用，两处注入点变异实测均拦截）
- rf-571 429 并发回显缺 `endpoint_key` 透传接线用例（去掉透传无人发现） —— 已修复 2026-10-04（补 `test_429_log_carries_endpoint_key_to_attempt`，变异 M4 拦截）
- rf-572 `test_capture_snapshot_holdings_lookup` 断言与用例目标不符（只 `assert compute.called`） —— 已修复 2026-10-04（断言落到快照对象：未匹配 `shares/cost_price == 0.0`，变异 M5 拦截）
- rf-573 `test_capture_snapshot_data_creation` 断言与用例目标不符（只 `assert compute.called`） —— 已修复 2026-10-04（断言聚合三字段求和 + 账户持仓清单，变异 M6 拦截）
