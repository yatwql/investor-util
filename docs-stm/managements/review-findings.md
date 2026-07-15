# 个人投资分析报告生成小助手 - 自我审查问题记录

---

P1 问题（3 项）已全部修复完毕，详见 [`changelog.md`](changelog.md)。

> 历史自审记录已归档：

---

## 当前待处理问题（2026-07-15 全面代码审查）

> 审查方法：并行派出 Architecture Strategist、Maintainability Reviewer、Pattern Recognition Specialist 三个 Agent 对全库（src/python/ + src/test/）进行独立分析后汇总。
> 审查范围：架构约束遵从（technical.md §2/#9）、死代码、重复代码、命名规范、模块级副作用、测试覆盖缺口。

### P2（中优先级 — 已全部修复）

P2 问题（10 项）已全部修复完毕，详见 [`changelog.md`](changelog.md)。

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-2 | **模块级副作用** | `llm/pricing.py` | 82 | 模块加载时执行 `reload_pricing()` 读取配置文件（文件 I/O）。 | **低**：影响启动时间 | 延迟到首次调用 `estimate_cost()` 时执行 |
| P3-4 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性 | 将评级计算、风险分析拆出 |
| P3-5 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：降低可读性 | 考虑拆分子模块 |
| P3-6 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：降低可读性 | 验证函数提取到 `_validate.py` |
| P3-9 | **测试覆盖缺口** | `report/fund_style_analysis.py` | 244-288 | `_tencent_extended` / `_push2_extended` 的会话级缓存去重依赖全局单例协作，无集成测试验证跨模块缓存共享。 | **低**：潜在缓存协方差错 | 补充集成测试 |

#### 已修复 P3 问题

- **P3-1**（模块级副作用 → 惰性注册）：`report/fund_style_analysis.py` 模块加载时执行 `get_registry().register_provider("tencent_style")`，改为 `_ensure_tencent_provider_registered()` 懒加载函数，首次调用 `classify_fund_style` 时注册。
- **P3-7**（report 层依赖 UI 层 → 颜色常量独立）：创建 `ansi_colors.py` 共享模块，`report/progress.py` 改为从此导入而非 `tui_menu`。
- **P3-8**（遗留 print → logging）：`api_base.py` 中 `print(msg)` 改为 `logger.info("%s", msg)`。
- **P3-10**（冷却恢复测试缺口）：补充 `test_is_chain_broken_cooldown` 测试。
- **P3-11**（配置验证缺失）：增强 `_validate_user_fund_benchmarks` 逐项验证。
- **P3-12**（多余空白行）：删除 `config/_core.py` 中连续三空白行。

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
