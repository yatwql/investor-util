# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.8]**（2026-10-09）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.9-dev] - 开发中（未发布）

- **功能/数据**：**市场温度第一因子升级为估值分位（plan-116 完成）**——新增指数估值历史源 `fetcher/index_valuation.py`（akshare 乐咕 `stock_index_pe_lg`/`stock_index_pb_lg`，沪深300 月频 PE/PB 2005 起；1 周缓存 + 30 天旧缓存兑底；**可选源不计入共享 `akshare` 熔断键**防乐咕故障连坐无风险利率）；`bond_yield` 扩展 10Y 国债收益率全历史序列（`bond_yield_history` 独立键，ERP 因子数据底座）；`build_erp_series` 按日期 asof 对齐（修复尾部 zip 会把历史 PE 与近期 rf 错位配对的缺陷）；三因子第一项 = PE/PB/ERP 各自历史分位等权（样本下限 60），估值序列不可得 → 旧缓存兑底 → 回落点位分位（=升级前行为，温度行永不消失；实测当日两口径分差 7.6 分、同档）；契约新增 `valuation_percentile`/`valuation_components`/`first_factor` 三键，Excel/HTML 三因子行首项按口径动态展示「估值分位/价格分位」，免责声明同步。**回看窗口 750 → 2000 交易日**（实测腾讯/东财源上限 ≈8 年），并修复**链路文件缓存窗口锁死缺陷**（增量合并从缓存末日补数把短窗口永久钉死——修前请求 2000 天实测只返 91 根；现短于请求窗口且存在文件缓存时自动清缓存全量重取）。新增测试 33 项（单元计数 9,475 → 9,508），文档同步（技术契约注记 16 键/数据源表/缓存表/目录树、datasource 两册、folders）

- **修复/分析**：**市场温度波动率分量方向反转**——`_vol_component` 由「越高越热」改为「越高越冷」：A 股高波动多现于恐慌下跌（股灾/贸易战/急跌）而非狂热顶部，旧口径同向会把恐慌期温度硬抬高（波动分量最高 +20 分），可能把「低估」推成「合理」；回归用例锁定「其余因子相同、波动越高温度越低」及低估区反向陷阱（`test_volatility_direction_reversed`）。契约/权重/免责声明/三档刻度均不变；PE/PB 估值分位化 + 股债性价比 + 回看窗口拉长已立项 plan-116（同版本内完成，见上条）

- **重构/配置**：**量化指标 7 个逐项开关合并为单开关 `metrics_enabled`（plan-115）**——菜单 `[S]` 18-24 号 `metrics_*` 七项并为「量化指标显示」一项（指标始终全量计算、开关只管显示；注册表 34→28 项、常规组 16→10，面板编号与各手册表格/计数同步）；雷达图改为单开关口径（关闭 → 全轴 N/A，**降级 3 轴路径此前不过滤已补齐**）；`circuit_breaker_wrapper` 两份逐项 flag_map 收敛为单常量；**修复 `_ff_was_off` 只读不写**（rf-654：开关「开回时重置断路器」的契约从未生效，关闭前的残留失败计数会跨周期累计）；旧 `metrics_*` 键按无消费者告警。**补齐测试**：熔断 FF 联动 6 项（此前零覆盖）+ 降级路径过滤 + 旧键告警回归；生效面维持现状（不扩到 LLM 指标表/正文）。

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
