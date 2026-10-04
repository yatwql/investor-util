# 自我审查问题记录归档 — v0.12.x

> 归档时间：2026-10-03（v0.12.1 发布当日并入，0.12 系列首份）
> 原始文件：`docs/managements/review-findings.md`
> 涵盖版本：v0.12.1（2026-10-03）
> 归档内容：本迭代已修复的 rf 记录摘要行（v0.12.1 批次 rf-557 ~ rf-562；v0.12.2 批次 rf-563 ~ rf-570（限购线文档一致性、48h 技术债、plan-73 消费方补齐、CI 口径分叉根治）：报告目录分组线性投影与附录组、LLM 章级门控整章隐藏、JS 资产单源与打印断言、发布列与 changelog 发布指针一致性断言、跨组交错线性段拆块、实现与文档过期残留整改）

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

