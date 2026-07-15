# 自我审查问题记录归档 — v0.5.x

> 归档时间：2026-07-15
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.5.0 ~ v0.5.7（含后续修复追溯）

## v0.5.0 ~ v0.5.5

v0.5.x 期间所有自查问题均通过即时修复处理，直接纳入 changelog，未在 review-findings.md 中积累待办记录。详细变更见 [`archived_changelog.0.5.x.md`](archived_changelog.0.5.x.md)。

## v0.5.6 ~ v0.5.7 全面代码审查

> 审查方法：并行派出 Architecture Strategist、Maintainability Reviewer、Pattern Recognition Specialist 三个 Agent 对全库（src/python/ + src/test/）进行独立分析后汇总。
> 审查范围：架构约束遵从（technical.md §2/#9）、死代码、重复代码、命名规范、模块级副作用、测试覆盖缺口。

### P1（高优先级）— 已全部修复

| # | 问题 | 修复方式 |
|---|------|----------|
| P1-1 | `generators_orchestrator.py`/`skeleton.py` 直接 `httpx.Client()` 绕过统一 SSL | 改为 `make_http_client()` |
| P1-2 | `fund_style_analysis.py` 直接调用 Provider 私有函数 | 全部移除直接调用，经 Provider Chain |
| P1-3e | 私有符号跨包导入（5 个消费者文件同步遗漏） | 修复全部内部调用点 |
| P1-3f | LLM 模块私有符号全局重命名（8 个消费模块同步） | 完整重命名 + 消费者更新 |

### P2（中优先级）— 已全部修复

| # | 问题 | 修复方式 |
|---|------|----------|
| P2-1 | `fund_style_analysis.py` 硬编码代码前缀判定 | 提取到 `code_utils.py` |
| P2-2 | `price.py` 硬编码 `code.startswith("00")` | 替换为 `code_utils.is_otc_code_overlap()` |
| P2-3 | `penetration.py` 硬编码 `code.startswith("5")` | 替换为 `code_utils.is_exchange_fund_code()` |
| P2-4 | DegradationTracker 状态文件路径 | 从 `data/cache/` 移至 `data/state/` |
| P2-5 | news_correlation 缺少统一封装 | 新增 `run_news_correlation_safe()` |
| P2-6 | 重复 `_fetch_fund_holdings_cached` | 提取到 `fetcher/fund.py` |
| P2-7 | 重复 LLM 模块信息构建 | 新建 `report/llm_module_info.py` 共享函数 |
| P2-8 | 7 处死导入 | 清理 |
| P2-9 | `FetchStrategy.PLACEHOLDER` 死分支 | 移除枚举值 |
| P2-10 | akshare 直接依赖 | 创建 `fetcher/akshare.py` 封装层 |

### P3（低优先级）— 已部分修复

| # | 问题 | 修复方式 |
|---|------|----------|
| P3-1 | 模块级副作用：`fund_style_analysis.py` 导入时注册 Provider | 改为惰性初始化 `_ensure_tencent_provider_registered()` |
| P3-3 | `provider_registry.py` 模块级副作用：导入时注册默认链 | 移除第 467 行 |
| P3-7 | report 层依赖 UI 层颜色常量 | 创建 `ansi_colors.py` 共享模块 |
| P3-8 | `api_base.py` 遗留 print | 改为 `logger.info` |
| P3-10 | 冷却恢复测试缺口 | 补充 `test_is_chain_broken_cooldown` |
| P3-11 | 配置验证缺失 | 增强 `_validate_user_fund_benchmarks` |
| P3-12 | 多空白行 | 删除 `_core.py` 中连续三空白行 |

### 剩余待跟踪

以下 P3 项延续至后续版本跟踪：

- P3-2（模块级副作用：`llm/pricing.py` 加载时读配置）
- P3-4（文件过长：`providers/tiantian.py` 744 行）
- P3-5（文件过长：`report/fund_style_analysis.py` 635 行）
- P3-6（文件过长：`config/_core.py` 631 行）
- P3-9（测试覆盖缺口：Tencent/Push2 会话缓存集成测试）
