# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.0
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C19）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P2 - 代码质量（低优先级，增量改进）

#### P2A — 文件过长（>500 行，建议拆分）

| # | 文件 | 行数 | 拆分建议 |
|---|------|------|----------|
| **rf-75** | `registry.py` | 617 | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责 |
| **rf-76** | `llm/fact_checker.py` | 623 | 核心校验逻辑与辅助函数分离（注：长函数已拆分，文件级别未拆） |
| **rf-77** | `handlers_config.py` | 553 | JSON 文本编辑函数提取到 `config/` 子模块 |
| **rf-78** | `fetcher/batch.py` | 549 | BatchDispatcher 本身内聚，可维持现状 |
| **rf-79** | `code_utils.py` | 541 | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出 |
| **rf-80** | `report/data_status.py` | 528 | DegradationTracker 单类偏大 |
| **rf-81** | `report/html_renderers.py` | 521 | 所有 HTML render 函数揉合一体 |
| **rf-85** | `fetcher/fund.py` | 394 | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 447 | Excel 编排器 |

---

## 归档

### 归档档案

- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
