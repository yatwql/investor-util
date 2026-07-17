# 实现计划归档 — v0.6.x

> 归档时间：2026-07-17
> 原始文件：`docs-stm/managements/plan.md`
> 涵盖版本：v0.6.0 ~ v0.6.6

---

## v0.6.x 变更概要

### ✅ [P3] I. 命令行模式（CLI）— 支持定时任务驱动报告生成（v0.6.2 已完成）

> 原始设计：`docs-stm/archive/v0.6.x/cli-mode/cli-mode-technical-design.md`
> 迭代计划：`docs-stm/archive/v0.6.x/cli-mode/cli-mode-iteration-plan.md`

CLI 命令行模式支持定时任务驱动报告生成，无需 TUI 交互。

**要点**：
- `cli.py` 入口：argparse（report/cache 子命令）+ config 覆写 + 退出码硬化
- `report/cli_progress.py`：CliProgressReporter（常规→logging，verbose→stderr 彩色输出）
- `logger.py`：`log_app_boundary()` 记录启动/关闭事件
- `docs-stm/manuals/how-to-schedule.md`：定时任务配置指南
- 共享层路由：CLI 和 TUI 公用 handlers_report/orchestrator 逻辑

**迁移**：
- [P3] I 从待实现方向移至"已完成迭代"
- 设计文档归档至 `docs-stm/archive/v0.6.x/cli-mode/`

---

### ✅ [P4] H. 智能预警模块去留评估（v0.6.3 已完成 — 完全移除）

经 P4-1 评估确认两个维度均不可靠后，完全移除智能预警（early_warning）模块。

**评估结论**：
- **行业资金流向**：0% 成功率（废弃），东方财富接口极不稳定
- **新闻情绪聚合**：因 str/dict 类型 Bug 恒空，LLM 成本收益比不佳
- **结论**：完全移除，删除 `report/early_warning.py`、测试文件及相关注册表条目

**迁移**：
- P4 H 从待实现方向移除

---

### ✅ P1 S1~S3：orchestrator 共享层提取（v0.6.1 已完成）

**S1（已完成）**：创建 `report/orchestrator.py`，定义 `ReportContext`、`ReportType` 等共享数据结构
**S2（已完成）**：提取 `generate_report()` 流程函数，TUI/CLI 共用
**S3（已完成）**：`handlers_report.py` 缩减依赖，`orchestrator` 作为唯一入口

**要点**：
- `cache/operations.py`：缓存操作共享层，含 `update_basic_cache()`、`update_position_cache()`、`cleanup_cache()`、`get_cache_stats()`
- handlers_cache.py 从 457 行缩减至 246 行（-46%）
- `technical.md` 全面重组：分层结构（总体架构→概要设计→逐层详细设计→架构约束→附录）

---

### ✅ v0.6.0：管理文档清理 + 版本号统一

- 补齐管理文档版本头（llm-technical.md、review-findings.md、test-coverage.md、folders.md）
- 统一全栈版本号至 v0.6.0
- 清理历史痕迹

---

### ✅ v0.6.4：全量架构约束整改（27 项）

完成 review-findings.md 中 P1(7项)+P2(11项)+P3(7+2项) 共 27 项修复，涵盖：
- C6 Provider Chain 必经：5 处直调 provider 改为通过 fetcher 层转发
- C7 报告序号动态化：4 个 sheet 标题改为 `get_report_section_number()`
- C3 缓存原子写入：2 处 config 写入改用 `tempfile.mkstemp + os.replace`
- C8 日志统一：5 处 `print()` 替换为 `logger`
- C14 渲染期全局变量：`timing_records` 改为 ProgressReporter 实例级
- C1 代码类型判定中心化：国家映射/code_utils 函数；ETF/联接判定
- 死代码/命名清理：重命名、删除死代码、变量命名规范化
- P3-8 定价懒加载：`reload_pricing()` 惰性化
- P3-12 缓存共享测试：新增 `TestExtendedCacheSharing`

---

### ✅ v0.6.5：LLM 关联分析情绪着色

Excel 和 HTML 报告对 `[利好]` 标记红色、`[利空]` 标记绿色着色。

**要点**：
- `_colorize_llm_cell`（Excel） + `sentiment_colorize` Jinja2 过滤器（HTML）
- 中性/无标记保持默认黑色

---

### ✅ v0.6.6：新闻去重增强 + 文档同步

- `_dedup_by_title` 新增子串包含规则：跨源、同源快讯版 vs 全文版去重
- folders.md 同步：补充遗漏文件 + 归档路径 cleanup
