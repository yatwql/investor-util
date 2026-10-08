# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.6]**（2026-10-07）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.7-dev] - 开发中（未发布）

- **工程效能**：**中央注册表按注册职责域拆分**——`core/registry.py`（785 行临界，余 15 行）下沉 `core/data_registry.py`（数据模块/缓存 TTL/LLM 设置键派生，441 行）+ `core/report_section_registry.py`（报告章节/导航分组/页签名称派生，335 行），`registry.py` 收敛为 62 行门面（computation/section_block 单入口再导出保留，导入面与测试 patch 面不变）；两域零跨域引用、`__all__` 声明契约互不相交；`check-semantic-index` 章节 AST 解析改指持有子模块；门面同一性+域契约测试 3 项 | rf-75

- **工程效能**：**临界文件按域拆分**——`llm/prompts_core.py`（800→350）按职责下沉三子模块（`failure_reasons` 失败原因常量 / `prompts_data_blocks` 上下文数据块与格式化辅助 / `prompts_review` 自审与持仓复盘提示词），`llm/generators.py`（787→444）按生成器域下沉 `generators_singletons`（单例四生成函数）；两文件保留门面 re-export（消费方导入面不变），仅 4 处测试 patch 按「测试指向持有子模块」纪律改指新域；llm-technical/folders 同步 + 门面同一性回归测试 4 项 | rf-626

- **工程效能/发布**：**版本一致性 `--fix` 不再吞空行 + 消除脚本 SyntaxWarning**——`_auto_fix_header` 行首空白类改同行字符类（原 `\s` 含换行，MULTILINE 下吞掉版本头前空行，developer-guide 受损已恢复），docstring 改 raw 串消除 invalid escape 警告；回归补「空行保留 + 跨行不误判 + 无警告编译」用例 | rf-624
- **工程效能/发布**：**`release.py publish` 归一化 `--title`**——新增 `normalize_release_title()` 剥离 title 自带的 `release: v… —— ` 前缀，防双前缀 subject（v0.12.6 发布提交实测出现，历史不可变，修复防再犯） | rf-625
- **运行体验**：**生成进行中阶段 ETA 预估**——`core/perf` 新增同阶段历史中位数预估 `estimate_stage_eta`（最近 20 次运行同名阶段减已耗时、严格同报告类型筛样本、无样本与读档/计算异常一律静默降级）与阶段状态唯一格式器；`PerfCollector` 可选阶段广播回调（回调异常隔离，basic/both/full 三处管线构造点零调用点改动）；`ProgressReporter.stage_progress` 基类单一实现，CLI verbose / Web / TUI 同源（瞬时阶段不刷屏、历史不足先静默后仅显已耗时） | plan-97
- **运行体验**：**主菜单页头常驻状态仪表盘**——新增 `tui/status_line` 五项本地单源组装（上次报告时间 ← perf 历史末条 / 缓存过期数 ← 与 [4] 同口径统计 / 数据新鲜度 ← 最新价格缓存数据日期与自然日龄 / 降级源数 ← 健康历史末条 fail_count / LLM 状态点 ← llm_status 同源 ●○），逐项异常降级为「—」、整行永不抛、TTL 45s 记忆化随页头重绘零外部调用（新鲜度刻意不取交易日历：日历缓存未命中会走 akshare 触网），`print_header` 标题下常驻一行并附详情菜单指引 | plan-96
- **报告呈现**：**月度收益日历（近 24 个月年 × 月红绿格）**——`analysis/monthly_returns` 按月聚合（月末/上月末−1、首月 inception 基线、截窗保真实上窗基线、胜亏平与最长连亏统计；as-if 现行 + realized 预留的双口径并排结构），`history_data.monthly_returns` 三处返回点单源注入；HTML 端纯表格热力格（正值红/负值绿，无 JS 天然具备无脚本回退）+ Excel 页签第四区块（FMT_PERCENT 小数 + profit_font 红绿字 + 口径统计说明行），区块注册表/矩阵/语义表/需求/手册/faq 目录树同步 | plan-86
- **运行保障**：**生成中断一致性收口**——新增 `report/run_integrity`（`guard_run` 装饰 `generate_report`，ContextVar 线程隔离）：KeyboardInterrupt 安全落点清理未完成临时产物 + 进度通道提示「已写盘/未完成已丢弃/已清理临时文件」明细 + `status=interrupted`（含 `interrupted_stage`）落 perf_history（`save` 幂等一次一录，页头状态行显「（已中断）」不误判成功）+ 健康检查收敛；HTML/Excel 产物改同目录 `.tmp` + `os.replace` 原子落盘（中断不再产生半写文件，遗留预清扫），收口不吞 KI（CLI 退出码 130/菜单「操作已取消」语义不变）；新需求 R-OUT-13 + faq 中断问答改写 | plan-98

（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.6（2026-10-03 ~ 2026-10-07）
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
