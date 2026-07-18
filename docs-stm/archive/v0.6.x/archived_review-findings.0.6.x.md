# 自我审查问题记录归档 — v0.6.x

> 归档时间：2026-07-17
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.6.0 ~ v0.6.6

---

## v0.6.1 全库代码审查

> 审查方法：Architecture Strategist、Maintainability Reviewer、Pattern Recognition Specialist 三个 Agent 并行分析。
> 审查范围：架构约束遵从、死代码、重复代码、命名规范、模块级副作用、测试覆盖缺口。

### P3（低优先级）— 全部已修复

| # | 分类 | 文件 | 问题 | 修复版本 |
|---|------|------|------|----------|
| P3-1 (原) / P3-8 (重编号) | **模块级副作用** | `llm/pricing.py` | 模块加载时执行 `reload_pricing()` 读取配置文件 | v0.6.4（惰性加载） |
| P3-2 (原) / P3-9 | **文件过长** | `providers/tiantian.py` | 多职责揉合，744 行 | 长期跟踪（当前仍存在） |
| P3-3 (原) / P3-10 | **文件过长** | `report/fund_style_analysis.py` | 多职责揉合，635 行 | 长期跟踪（当前仍存在） |
| P3-4 (原) / P3-11 | **文件过长** | `config/_core.py` | 多职责揉合，631 行 | 长期跟踪（当前仍存在） |
| P3-5 (原) / P3-12 (重编号) | **测试覆盖缺口** | `report/fund_style_analysis.py` | 会话级缓存跨模块共享无集成测试 | v0.6.4（新增 TestExtendedCacheSharing） |

> **注**：P3-9、P3-10、P3-11 三项仍存在于当前 review-findings.md 中作为长期跟踪项。

---

## v0.6.4 全量架构约束审查

> 审查方法：全库代码扫描（src/python/ + src/test/），按 technical.md §1.4（核心架构决策）和 §8（架构设计约束）逐条核对。

### P1（高优先级）— 全部在 v0.6.4 修复

| # | 问题 | 修复方式 |
|---|------|----------|
| P1-1 (C6) | `orchestrator.py` 直调 `tencent.get_realtime_price` | 改为通过 fetcher/price.py 转发 |
| P1-2 (C6) | `fund_style_analysis.py` 直调 Provider 私有函数 | 全部移除直接调用，经 Provider Chain |
| P1-3 (C6) | `news_correlation.py` 直调 Provider 缓存 | 改为通过 fetcher/news.py 调度 |
| P1-4~P1-7 (C7) | B 系列 4 个 sheet 标题硬编码 13-16 | 改为 `get_report_section_number()` 动态获取 |

### P2（中优先级）— 全部在 v0.6.4 修复

| # | 问题 | 修复方式 |
|---|------|----------|
| P2-1 (C6) | `handlers_cache.py` 缓存操作用户直调 Provider | 改为 operations 层转发 |
| P2-2 (C6) | `eastmoney_industry.py` 直调 Provider | 改为 fetcher/industry.py 转发 |
| P2-3~P2-4 (C3) | `init_config()` 和 `_ensure_llm_settings_file()` 非原子写入 | `tempfile.mkstemp + os.replace` |
| P2-5~P2-9 (C8) | LLM 模块 3 处 + report 2 处 `print()` | 替换为 `logger` |
| P2-10 (C14) | `timing_records` 模块级可变列表 | 改为 ProgressReporter 实例级属性 |
| P2-11 (C1) | `llm/prompts.py` 硬编码国家映射 | 改为 `code_utils` 函数 |

### P3（低优先级）— 在 v0.6.4 部分修复

| # | 问题 | 修复方式 |
|---|------|----------|
| P3-6 (C5) | 4 个 LLM 模块的 `import httpx` 直引 | 移至 `TYPE_CHECKING` 块 |
| P3-7 (C1) | `news_keywords.py` 手动 ETF/联接判定 | 改为 `is_etf_by_name()` / `is_index_link_by_name()` |
| P3-1~P3-5 | 死代码/命名清理（重命名、删除死代码等） | 逐项清理 |
| P3-8 | pricing.py 模块级副作用 | 惰性加载（v0.6.4） |
| P3-12 | 缓存共享测试缺口 | 新增 TestExtendedCacheSharing（v0.6.4） |

### 约束覆盖总结

| 约束 | 状态 |
|:-----|:------|
| **C1** 代码类型判定中心化 | ✅ 全部已修复 |
| **C2** 缓存统一管理 | ✅ 全部通过 |
| **C3** 缓存原子写入 | ✅ 已修复 |
| **C5** HTTP 客户端统一 | ✅ 已修复 |
| **C6** Provider Chain 必经 | ✅ 已修复 |
| **C7** 报告序号不可硬编码 | ✅ 已修复 |
| **C8** 日志统一 | ✅ 已修复 |
| **C9** LLM 模块注册 | ✅ 全部通过 |
| **C14** 渲染期全局变量 | ✅ 已修复 |
| 死代码/命名残留 | ✅ 已修复 |

---

## v0.6.7 文档审计清理

> 审查范围延续 v0.6.4 方法。

### 变更

- 移除已清零的「按约束分类汇总」表（所有约束已通过验证，无需继续跟踪）
- 移除已修复问题的详细记录，仅保留仍在长期跟踪的 3 项 P3 文件过长问题

### 当前仍跟踪的 P3 项（已转移至 v0.7.0-dev）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 744 行 | 多职责揉合 | **低** | 拆分评级计算 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 多职责揉合 | **低** | 拆分子模块 |
| P3-11 | **文件过长** | `config/_core.py` | 631 行 | 验证函数可提取 | **低** | 提取 _validate.py |
