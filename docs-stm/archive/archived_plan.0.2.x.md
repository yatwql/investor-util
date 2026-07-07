# 实现计划归档 — v0.2.x

> 归档时间：2026-07-08
> 原始文件：`docs-stm/managements/plan.md`
> 涵盖版本：v0.2.0 ~ v0.2.91

---

## B 迭代 — 基金深度分析（v0.2.87）

基金深度分析 4 模块：基金经理变更监控/持仓重合度矩阵/持仓集中度监控/基金风格分析。详见 changelog.md 及 `docs-stm/archive/c-iteration-design.md`、`docs-stm/archive/c-p1b-excel-title-number-fix.md`。

## C 迭代 — 报告序号可配置（v0.2.85 ~ v0.2.86）

报告序号可配置，详见 changelog.md 及 `docs-stm/archive/c-iteration-design.md`、`docs-stm/archive/c-p1b-excel-title-number-fix.md`。

## D 迭代 — 数据降级分层治理（v0.2.88 ~ v0.2.91）

D 迭代（数据降级分层治理，Phase 0-3）已完结，详见设计文档 `docs-stm/archive/d-iteration-data-degradation-design.md` 及 changelog.md。核心产出：

- **T1/T2/T3/T4 分层模型**：按数据源稳定性四层分级，每层降级行为不同
- **`_data_status` 机制**：`DataStatusItem(available, tier, message)` 字典 + `STATUS_MESSAGES` 共享常量 + 层前缀（T2→⚠ / T3/T4→ℹ）
- **Excel 降级辅助**：`_write_placeholder()`（占位文本）和 `_write_data_status_foot()`（状态页脚）
- **HTML 降级渲染**：`render_data_status` Jinja2 宏 + `_safe_build_data_status()` 异常安全包装
- **新闻 source_status 追踪**：`get_last_source_status()` 全源失败→占位/部分失败→底部列表
- **akshare 分红/盈利预测降级**：`dividend_success` 布尔返回值 + 页脚状态摘要
- **全链路回归测试**：新增 5 个边缘测试文件覆盖全部降级路径

## 其他已完成迭代

A/A2/A3/A4/A5/J/K/L/P/N/Q/R/M/T/S/V/U/W/X/Y1/Y2/Y3/Y4/Y5/Y6/Z1/Z2/Z3/Z4 等迭代的详细变更记录见 `docs-stm/managements/changelog.md`。
