# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.1]**（2026-10-03）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.2-dev] - 开发中（未发布）

### Added

- **基金申购限购信息接入（`plan-72` 迭代 1~3）**：天天基金申购状态总表全量取数（直连解析 + akshare 备链 + `purchase_schema` 载荷准入 + 会话复用单次经链），持仓明细市值明细末列「申购状态」条件列（限大额日限额/暂停申购下一开放日，Excel 与 HTML 单源文案）+ 双端口径脚注（天天基金渠道口径）与按交易日历的 ≤3 / 4~7 / >7 交易日三档时效标注；功能开关 `fund_purchase_limit`（默认开，注册表报告组），数据全链失败 `available=False` 时静默隐列、四层降级不阻断报告生成（设计文档 `docs/plan/fund-purchase-limit-design.md`）
- **What-if 目标持仓申购受限提示（`plan-74` 四迭代）**：受限标的预格式化索引 `restricted_index`（契约条件字段，与单元格同源格式化，编排层注入 + What-if 路径单点挂载）+ 申购可行性判定 `evaluate_purchase_feasibility`（限大额 `ceil(金额÷日限额)` 交易日估算、超 60 交易日判不可行、暂停引用下一开放日、金额/限额未知不给天数）+ 目标持仓新增/加仓腿提示注入 `build_whatif_data(restricted_index=…)`（卖出腿不判定；条件键 `feasibility`，Excel 持仓变动明细尾部 + HTML⑦申购受限提示节）；降级态（开关关/不可用/时效超限/取契约异常）契约与输出逐字节回退现网行为，调仓建议与行动摘要零改动（设计文档 `docs/plan/fund-purchase-limit-advice-design.md`）

### Changed

- 限购总表缓存显式注册进数据模块注册表（data_type `fund_purchase` + 精确键 `fund_purchase_status_table`，TTL 与官方净值同源 `CACHE_DAILY` 24h）：此前未注册、靠 `get_ttl` 回退巧合与净值同档，回退逻辑或常量一变即无声漂移；仍不入菜单刷新组（大表不随菜单强抓），`datasource.md` 脚注同步
- **限购线文档一致性核对修正**：`reports-instruction.md` 持仓市值明细 15→16 列（申购状态条件列 + 脚注/时效/降级说明）与 What-if 申购受限提示块（页签表/产物/设计边界/功能对照表 4 处）；`requirements.md` R-WIF-05 输出描述与 R-WIF-06 网络语义（what-if 默认本地计算，提示经缓存链读限购总表：命中零联网/未命中现场取一次/失败静默兔底）；TUI/CLI 手册 What-if 段同源修正；FAQ 新增「申购状态」列问答；`datasource-reliability.md` 3.11 用途行补 What-if 消费方；README What-if 特性行补受限提示

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
