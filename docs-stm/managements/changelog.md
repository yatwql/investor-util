# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.4]**（2026-09-25）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.5-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### LLM 端点级节流与并发治理：把速率/并发约束声明化到 provider 条目（2026-09-25，plan-57）

**背景**：用户计划把订阅制编码端点（Kimi Code，`api.kimi.com/coding/`）接入程序，要求从整体架构出发、不留技术债，并提出「非该端点时并发约束能否放开」。

**实测现状**（日志统计 10 次运行）：每次报告 **8~9 次 LLM 调用**、输入 22~27k + 输出 19~34k = **41k~56k token**，在 **2~8 分钟**内以 3 路并发发出。全局键 `llm_max_concurrency` 只能表达「所有模块合起来最多几个线程」，**无法表达「同一程序、不同端点不同策略」**——这正是「想收紧订阅制端点、同时放开按量端点」的架构缺口。

**变更**：
- **新增 `llm/pacing.py`**：把节流与并发**声明化到 provider 条目**（`llm_providers.json` 的 `pacing` 段）——
  - `min_interval`（两次请求最小间隔秒）、`jitter`（间隔随机抖动比例，避免固定节奏的机器特征）、`max_concurrency`（该端点同时在途上限）
  - **缺省即无约束**：不写 `pacing` 的端点零开销直通，行为与未引入本机制时**逐字节一致**；因此同一份配置可对订阅制端点收紧、对按量端点放开
  - 与全局 `llm_max_concurrency` **两级叠加**（全局线程池 + 每端点信号量）
  - 先取并发许可再等间隔，使间隔真正约束「请求发出」时刻；`PacingGate` 为 context manager，异常路径无条件释放
- **配置层**：`_parse_providers_list` 透传 `pacing`（坏字段逐字段忽略，不因笔误使整条 provider 失效）；`_inject_provider_chain_data` 装载策略（配置为唯一事实来源）；默认模板补注释
- **调用链接线**：`endpoint_key`（provider 条目名）逐层透传 `api.py` → `call_single_provider` → `call_claude`/`call_openai`/`call_gemini` → `call_llm_with_retry`，在**唯一调用缝**施加 `PacingGate`
- **复用既有原语**：`fetcher/batch.py::RateLimiter` 新增 `acquire_interval(key, interval)`（逐次显式间隔），不重复实现限速器
- **403 配额/风控拒绝改为不重试**：新增 `FAIL_REASON_QUOTA_EXCEEDED`；`_attempt_api_call` 将 403 归为 `("quota", 403)`，重试骨架直接降级到下一 provider——这类限制按时间窗口滚动（如 5 小时窗口、并发上限），**重试无益且高频重试会加剧风控画像**；**429 / 503 仍按 `max_retries` 重试**。报告侧差异化文案同步（`llm_content` / `llm_module_info`）
- **文档**：手册新增「端点级节流（`pacing`）」章节（字段表、与全局并发的关系、403 语义）；技术设计新增 §4.2.1（调用链图 + 性质表）

**测试**：+19 例（`test_llm_pacing.py` 16 + `test_config_llm_multi.py` 3）。**真实调用路径实测**（MockTransport）：无约束端点 3 次调用 0.002s；`min_interval=0.2` 端点相邻间隔稳定 0.200s；`max_retries=2` 下 403 仅发 1 次请求且失败原因 `quota_exceeded`。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.4（2026-09-15 ~ 2026-09-25）
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
