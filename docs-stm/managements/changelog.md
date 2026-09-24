# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.3]**（2026-09-24）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.4-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 数据源健壮性加固：修健康探针误报 + 场外净值跨厂商备源 + 传输级重试 + 财报正文备源（2026-09-24，rf-428 / plan-56）

**触发**：用户报「`price_price_fund_otc` 与 `report_datasink` 高频连接失败」，建议增加备用通道 / 优化重试 / 延长刷新窗口。

**诊断结论（实测证据）**：主要「失败」是**探针自身缺陷**——`core/check_sources.py` 的 9 个探针全部使用 `http://` 端点且不跟随重定向；上游迁 https 后返回 301/302，探针把 3xx 记成告警（`ok=false`），健康历史里天天基金 / 腾讯K线 / 财联社长期 `ok=0/fail=10`；东方财富行业探针缺 headers 且指向本环境不可达的 push2。**生产取数路径（https + `follow_redirects=True`）一直正常**：实测行业分类批量 3/3 命中（1.1s，备源接管）、场外净值正常返回。真实风险另有两条：`price_fund_otc` **单源无备**；DataSinking 索引 TTL 仅两周、配额压力大。

**变更**：
- **探针修正**（rf-428）：9 个 URL 全部 https；`_check_http` 默认跟随重定向且 **3xx 计「可达（带备注）」**；新增 `_check_any()` 多端点探针，行业分类改「push2 主源 → 行情页备源」，任一可达即判可用并标注「主源不可达，由备源接管」。**实测健康检查 10/10 可用（此前 6/10）**
- **场外净值跨厂商备源**（plan-56）：新增 `providers/sina.py::fetch_fund_nav`（`hq.sinajs.cn/list=f_{code}` → 名称/单位净值/累计净值/前一日净值/净值日期）与 `quote_adapters.SinaFundQuoteAdapter`、手写转换 `_price_transform_sina_fund`；链路 `price_fund_otc` 由单源 `["eastmoney"]` → `["eastmoney", "sina_fund"]`。适配器开关**两条路径同时接线**（否则开关开启时备源会静默失效）；实测主源故障时新浪交付且数值一致
- **传输级同源重试**：`fetcher/chain.fetch_with_fallback` 落槽前对传输级失败（超时/断连/远端断开）同源退避重试一次（0.6s 指数退避 + 抖动）；**不重试代码级空结果**（同一请求同一答案，且白耗 DataSinking 日配额）
- **财报正文备源**：`fetcher/financial_report.py` 抽出 `_attempt_candidates`（章节阶 → 全文阶）并接入**正文级**巨潮接管——此前备源只在「索引为空」时触发，主源索引正常而正文不可得时无退路
- **延长刷新窗口**：财报索引/章节清单 TTL **两周 → 30 天**（与正文同档），降低第三方配额与限速压力；R-FRD-07 语义同步
- **文档同步**：`datasource.md`（场外净值路由 + TTL）、`datasource-reliability.md`（探针语义 + 链路备源表）、`technical.md`（新增 §2.2.1 同源重试 + 链路图 + 缓存说明）、`requirements.md`（R-FRD-07）

**测试**：+26 例（探针 9 / 新浪 provider 4 / 适配器等价 2 / 链路重试 3 / 场外备源端到端 5 / 正文备源接管 3），含静态守卫「探针不得出现 `http://`」与「主源可用时备源零调用」红线断言。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.3（2026-09-15 ~ 2026-09-24）
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
