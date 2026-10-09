# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.8]**（2026-10-09）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.9-dev] - 开发中（未发布）

- **修复/数据**：**场外净值缓存新鲜度门禁按基金类型分域（rf-652）**——`_price_cache_fresh` 新增 `name` 形参并按 `is_qdii_extended` 细化阈值：QDII 官方净值合法 T-1（不变），国内场外 T 日当晚披露、盘后要求 T；两处调用点传入持仓名（`fetcher/price.py` 强刷路径 `expected_name`、`report/market_value.py` CACHE_ONLY 路径 `h.name`），与 `price_update_status` 口径同源。修前实测 5 只国内场外缓存停在 T-1 被误判新鲜、报告「价格更新状态」8/13（东财已返回 T），修后盘后强刷取到 T。回归 4 项。
- **技术债/文档+配置**：**过去 72h 实现核查三项修复（rf-653）**——① rf-647 的 429 行为变更（归 `quota` 终态、首试即 600s 长冷却熔断、零退避重试）同步入 `llm-technical.md`（§4.2 与 403 的配合、§6.1 容错层次新增「全链延迟重试」、§6.2 重试表、§6.3 失败原因表补 `FAIL_REASON_QUOTA_EXCEEDED`、§12.2 全局键）、`requirements.md`（R-LLM-10 与 `max_retries` 说明）、`technical.md`（LLM 降级与 C26）、`developer-guide.md`；② `llm_full_fail_retry_delay` 补入 `_DEFAULT_LLM_SETTINGS`/模板/已知键集（原 `skeleton` 直接读取却未登记，用户设置会被判「未知配置项」），加「默认集 ⊆ 已知键集」结构回归；③ `_factor_zoo` 根路径收敛为包 `__init__.py` 的 `PROJECT_ROOT` 单一来源（原 catalog/metrics/stages 三处各算 `parents[2]`）。

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.8（2026-10-03 ~ 2026-10-09）
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
