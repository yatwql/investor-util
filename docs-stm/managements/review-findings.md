# 个人投资分析报告生成小助手 - 自我审查问题记录

---

P1 问题（3 项）已全部修复完毕，详见 [`changelog.md`](changelog.md)。

> 历史自审记录已归档：

---

## 当前待处理问题（2026-07-15 全面代码审查）

> 审查方法：并行派出 Architecture Strategist、Maintainability Reviewer、Pattern Recognition Specialist 三个 Agent 对全库（src/python/ + src/test/）进行独立分析后汇总。
> 审查范围：架构约束遵从（technical.md §2/#9）、死代码、重复代码、命名规范、模块级副作用、测试覆盖缺口。

### P2（中优先级 — 建议下个版本规划）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P2-1 | **C1-代码判定分散** | `report/fund_style_analysis.py` | 137-146 | `_estimate_style_by_code()` 内 7 处硬编码代码前缀判定（`60`→大盘、`000`/`002`→中盘等），未使用 `code_utils.py` 原语。 | **中**：前缀知识散落 | 在 `code_utils.py` 新增 `estimate_market_cap_by_prefix(code)` 函数，统一规模估算 |
| P2-2 | **C1-代码判定分散** | `fetcher/price.py` | 163 | 硬编码 `code.startswith("00")` 做降级判定，应使用 `code_utils.is_otc_code_overlap()`。 | **中**：重复前缀知识 | 替换为 `is_otc_code_overlap(code)` |
| P2-3 | **C1-代码判定分散** | `report/penetration.py` | 106 | `code.startswith("5")` 仅覆盖沪市 ETF，漏掉 1 开头的深市 ETF。应使用 `is_exchange_fund_code(code)`。 | **低**：覆盖不全 | 替换为 `is_exchange_fund_code(code)` |
| P2-4 | **C2-缓存统一管理** | `report/data_status.py` | 84,137,162 | `DegradationTracker` 跨会话持久化通过 `open()` 直接读写 `data/cache/.degradation_state.json`，绕过 `cache/` 子包接口。`cache.cleanup_expired()` 无法感知。 | **中**：缓存管理缺口 | 将状态文件移出 `data/cache/`（如 `data/state/`），或在 `cache/` 接口中增加显式持久化状态存取 |
| P2-5 | **C9-LLM 模块注册不全** | `llm/generators_orchestrator.py` | 209-234 | `_MODULE_FNS` 缺少 `news_correlation`，该模块通过 `report/news_correlation.py` 直接调用而非 orchestrator 调度，并发管理/缓存/失败处理机制与其余 4 个 LLM 模块不一致。 | **中**：调度框架不统一 | 将 `news_correlation` 注册到 `_MODULE_FNS` |
| P2-6 | **重复代码** | `report/html_renderers.py` / `report/excel_b_series.py` | 37-49 / 23-31 | `_fetch_fund_holdings_cached` 函数完全一致（会话缓存封装），两份代码定义了相同的函数。 | **中**：维护双重负担 | 提取到共享模块（如 `fetcher/fund.py` 或新建共享工具模块） |
| P2-7 | **重复代码** | `report/html_renderers.py` / `excel_llm_usage.py` | 519-576 / 42-126 | `_build_module_info_list` 与 `build_llm_usage_sheet` 以几乎相同的模式迭代相同键名并检查相同失败原因常量。 | **中**：维护双重负担 | 提取共享的模块信息构建函数 `registry.build_llm_module_info()` |
| P2-8 | **死代码（未使用导入）** | 7 个文件 | 多行 | `handlers_config.py:9` 的 `import sys`；`cache/_io.py:13` 的 `from typing import Any`；`cache/_ttl.py:10` 同款；`html_renderers.py:6` 的 `from datetime import datetime`；`akshare_extras.py:19` 的 `as_completed`；`schemas/history.py:15` 的 `field`。 | **低**：代码冗余 | 删除未使用的 import 语句 |
| P2-9 | **死代码（枚举值）** | `provider_registry.py` | 67-71 | `FetchStrategy.PLACEHOLDER` 枚举值定义但从未被 `get_effective_strategy()` 返回。 | **低**：概念死分支 | 删除 `PLACEHOLDER` 枚举值及关联文档注释 |
| P2-10 | **Direct provider 调用** | report 层 9 处 | 多文件 | `html_renderers.py:32`、`news_correlation.py:414`、`category.py:118`、`fund_performance.py:211`、`html_builders.py:53,119`、`penetration_sheet.py:80,94` 直接导入 `akshare_extras` 的函数，无 fetcher 封装层。 | **中**：架构缺口 | 创建 `fetcher/akshare.py` 封装层，统一走 provider → Chain 路径 |
| P2-11 | **Report 导入私有 fetcher 函数** | `report/portfolio_history.py` | 33 | 导入 `_fetch_with_incremental_fallback`（私有函数）。 | **中**：封装缺口 | 改为公开 API 命名，或通过 `fetcher/__init__.py` 导出 |

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-1 | **模块级副作用** | `report/fund_style_analysis.py` | 36-37 | 模块加载时执行 `get_registry().register_provider("tencent_style", ...)`，导入即修改全局注册中心。 | **低**：影响测试隔离 | 改为惰性初始化：首次需要时注册 |
| P3-2 | **模块级副作用** | `llm/pricing.py` | 82 | 模块加载时执行 `reload_pricing()` 读取配置文件（文件 I/O）。 | **低**：影响启动时间 | 延迟到首次调用 `estimate_cost()` 时执行 |
| P3-4 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性 | 将评级计算、风险分析拆出 |
| P3-5 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：降低可读性 | 考虑拆分子模块 |
| P3-6 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：降低可读性 | 验证函数提取到 `_validate.py` |
| P3-7 | **抽象依赖倒置** | `report/progress.py` | 14 | 从 `tui_menu.py` 导入颜色常量，report 层抽象模块依赖 UI 层模块。 | **低**：抽象不纯 | 将颜色常量定义移到独立的共享模块 |
| P3-9 | **测试覆盖缺口** | `report/fund_style_analysis.py` | 244-288 | `_tencent_extended` / `_push2_extended` 的会话级缓存去重依赖全局单例协作，无集成测试验证跨模块缓存共享。 | **低**：潜在缓存协方差错 | 补充集成测试 |

---

> 历史自审记录已归档：
>
> **v0.5.x**：[`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
>
> **v0.4.x**：[`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
>
> **v0.3.x**：[`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
>
> **v0.2.x**：[`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
>
> **v0.1.x**：[`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
