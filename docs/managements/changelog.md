# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.7]**（2026-10-09）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.8-dev] - 开发中（未发布）

- **样式/Web**：**Web 配置页 375px 横向滚动修复（rf-644，解除 rf-257 ④ 阻塞）**——`style.css` 三层钳制：路径文案 `overflow-wrap:anywhere` + `.generate-form > *` 行线宽按列封顶（flex 行线宽取 fit-content 不受列宽封顶是机制性根因）+ select/file input `min-width:0; max-width:100%`；真机 CDP 复验 375px 断言 35/0/2（修前 4.1/4.3 不过）、五页签×十二视口扫描 60/60、新旧 A/B scroll 404→375；新增 `test_web_responsive.py` 5 用例回归；另补标签页 favicon（Web 侧 `favicon.svg` + `link` 声明消除 `/favicon.ico` 404；报告与 What-if 模板内联 data URI 同款图标、单文件零外链，whatif 关态 golden 基线经复核更新）。
- **修复/报告侧**：**调试页窄视口溢出与打印 display 还原修复（rf-645，rf-113 附带发现）**——`test-chart.html` grid 列下限改 `minmax(min(420px,100%),1fr)`；`chart-print.js` beforeprint 记录 canvas 原内联 display、afterprint 按记录还原（未记录回退 block、周期末清空），替代置空串导致的 computed display 漂移；`test_feature_interactive.py` 补 4 回归用例。
- **文档/需求**：**事件窗量化对照需求登记补齐（rf-646）**——`requirements.md` §6.16 + `R-EW-01..06` 六条需求行（先读实现后如实登记），`testplan.md` §2.1 补 6 行载体映射，`check-requirement-trace` 纳入 R-EW 域（38/38 域全量双向一致，后续新增不再漏报）。
- **文档/结构**：**设计语言契约 DESIGN.md 迁入管理文档目录**——自仓库根移至 `docs/managements/DESIGN.md`（设计约束类文档归属管理文档区）；路径性引用同步（`check-style-guardrails.py` 真值路径、4 处契约测试路径、CLAUDE.md 设计契约入口与管理文档清单、developer-guide 设计契约链接、folders.md 目录树与统计口径；样式/模板中的注释性提及按文件名寻址，无需改动）。
- **修复/LLM**：**provider 链路 429 长冷却与全挂延迟重试（rf-647，72h 日志分析立账）**——429 重试耗尽后以 `cooldown=600s + force=True` 立即熔断（`circuit_breaker` 新增参数，非 429 保持阈值语义），消除 kimi-main 每次调用白试 1~3 次的无效先试；`_execute_llm_with_finalize` 对瞬时类失败（network/timeout/api_error）延迟 `llm_full_fail_retry_delay`（默认 30s）整链重试 1 次，配额/熔断终态不重试；回归 7 用例（circuit force/cooldown 2 + 429 分支 2 + skeleton 重试 3）。
- **修复/日志**：**实验横幅级别纠正（rf-649）**——`log_experimental_features` 横幅（`====` + `⚗` 各行）`ERROR` → `INFO`，72h 内 68 条 ERROR 中 65 条为该横幅的统计污染消除；回归用例断言横幅行全 INFO、零 ERROR。
- **修复/数据**：**东财 push2 请求节流与穿透写入空数据降级（rf-650）**——push2 每次请求前随机间隔 0.05~0.2s 防同速批量触发反爬断连；`write_penetration_sheet` 空数据分支改 `.get("top10")` 消除 KeyError 整表写入失败（降级占位空 dict 路径），edge 用例回归「暂无穿透数据」优雅降级。
- **修复/数据**：**财报链路 source_hint 命名空间碰撞（rf-648，根因经真实探测确认）**——主源索引条目自带自由文本 `source="巨潮资讯网 (cninfo)"` 直传 `source_hint` 致两适配器双双静默拒服务（主源整条 7 天无命中，靠巨潮备源+缓存兜底；13 次 HTTP 探测两源全 200，排除网络/反爬/报告期）；修复：`_candidate_source` 来源归一（仅精确 cninfo 判备源，使用点归一兼容旧缓存）+ `_index_source_of` 精确匹配、sections/全文两阶段透传 source（备源候选不再打主源 sections，消除单次生成 10 次 404 与历史挂起）、异源拒服务写 `last_reason` + DEBUG（不再伪装成源返回空）；同批：chain 失败日志补 doc_id 定位标识（`_tag_key = code or doc_id`），定性修正（标的全为 A 股个股，原「基金噪音」判断错误）。回归用例 8 项（归一 6 + 拒服务原因 2）。
- **修复/LLM**：**429 首试即熔断（零退避重试）+ kimi 端点节流调大**——429 属配额/风控终态，`_attempt_api_call` 归入 `quota` 不再进退避表，首试即 `force` 600s 熔断，撞限首波代价 10~35s→<1s（503/超时保留重试；失败原因归 `quota_exceeded`，全挂延迟重试不空转）；配套 kimi 双端点 `pacing.min_interval` 1s→5s（`llm_providers.json`，改前备份）降低 RPM 撞限频率。回归：429 单次请求/首试熔断/失败原因 3 处改写 + 底层 kind 断言。
- **测试/门禁**：**crosscheck 真实仓库用例零写副作用（rf-651）**——`test_real_repo_sync_idempotent` 落点改为 tmp 副本承载真实 `folders.md` 内容：消除与并行一致性冒烟用例的 read/write 竞争（原先漂移时会把真实文件「顺手改好」，致双方偶发假红并掩盖漂移），真实实测与幂等断言语义不变。


（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.7（2026-10-03 ~ 2026-10-09）
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
