# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.8.6-dev

---

## 当前待处理问题

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 768 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件（较记录时增长 24 行）。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 652 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责（较记录时增长 17 行）。 | **低**：同上 | 考虑拆分子模块 |
| P3-11 | **HTTP 全同步低效** | `providers/` + `fetcher/` | 80+ 处 | 所有 HTTP 请求同步串联执行。行情获取（15 品种）、基金排名（10 基金）、行业数据（55+ 代码）等环节完全串行，是性能瓶颈。 | **中**：报告生成速度受限，单次全量约 85s 中 >50s 为串行 IO | 改造瓶颈路径（price/fund/industry 批量请求）为 async 并发，预计提速 2-3 倍（5.5d） |
| P3-13 | **缺乏性能基准** | `scripts/` | — | 无端到端性能基准，无法量化进度、检测回归、管理用户预期。 | **低**：无法感知版本间的性能退化 | 新增 `perf_profile.py` 冷/热缓存基准 + 分阶段耗时输出（1d） |

> 上述 P3-11、P3-13 源自 [`plan-engineering.md`](../plan/plan-engineering.md)（工程质量与性能优化方案）。


---

## 归档

### 已修复问题

| # | 分类 | 问题 | 修复内容 | 修复版本 |
|---|------|------|---------|---------|
| P3-12 | CI 测试失败 | `pyproject.toml` 中 `required_plugins` 将 `pytest-mock` 死锁在 `==3.15.1`，但 deps 声明 `>=3.15`，导致 pip 安装的版本（如 `3.15.2`）不满足 `==3.15.1` 硬校验，pytest 拒绝启动；`format` job 的 Ruff 检查无 `continue-on-error`，阻塞 CI；`all` 模式无 `--no-timeout` 易超时截断 | ① `required_plugins` 改为 `pytest-mock>=3.15` 与 deps 一致 ② `format` job 添加 `continue-on-error: true` ③ `all` 模式添加 `--no-timeout` | v0.8.6-dev |

### 归档档案

- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)

