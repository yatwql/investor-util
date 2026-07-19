# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.7.4-dev

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

> 归档版本按从新到旧排列：

- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md) — v0.6.0 ~ v0.6.7
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md) — v0.5.0 ~ v0.5.12
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md) — v0.4.0 ~ v0.4.5
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md) — v0.3.0 ~ v0.3.10
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md) — v0.2.0 ~ v0.2.91
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md) — 早期版本记录

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办

### P0 — 发布门禁

（待排期）

### P1 — Phase 1 管线基础设施 + 核心功能（~132h）

> **已完成**: P2 Tier 0 + MVP（v0.7.3，10 项任务，详见 changelog.md）
>
> **依赖链**：P1-03←PRE-01 · P1-04→P1-05 · P1-06-A→P1-06→P1-07→P1-08/09 · P1-08→P1-08-B · P1-03+P1-04→P1-10 · P1-11→P1-12 · P1-17→P1-18→P1-19
>
> 详细任务描述见 `docs-stm/plan/better-investment-advice/better-investment-task.md`

| 序号 | 任务 | 依赖 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **P1-03: Rf 获取——`bond_zh_us_rate` + 手动兜底** | ←PRE-01 | 6h | 新建 `bond_yield.py`，通过 akshare `bond_zh_us_rate()` 获取国债收益率 + 用户手动配置兜底。C6 合规：chain 路由 |
| 2 | **P1-04: 个股日收益率管线暴露** | — | 8h | `portfolio_history.py` daily_returns 从局部变量→返回值，10 品种手动校验 |
| 3 | **P1-05: 组合日收益率暴露** | ←P1-04 | 4h | `get_combined_timeseries` 新增 `daily_returns_portfolio` 字段 |
| 4 | **P1-06-A: f_context 组装逻辑抽取** | — | 8h | orchestrator.py→`f_context_builder.py`，统一数据合并点 + 类型断言 |
| 5 | **P1-06: 阻断点 1——prepare_report_data 加 risk_metrics** | ←P1-06-A | 4h | 新增 `"risk_metrics": {}` 空字典占位，下游 `.get()` 兼容 |
| 6 | **P1-07: 阻断点 2——capture_snapshot 加风险字段** | ←P1-06 | 4h | f_context 新增 risk_metrics/portfolio_daily_returns 透传，双路径覆盖 |
| 7 | **P1-08: 阻断点 3——generate_all_llm 暴露 history_data** | ←P1-07 | 4h | 确保 portfolio_history 数据作为 f_context 键传递到 prompt |
| 8 | **P1-08-B: prompts.py 拆为三文件** | ←P1-08 | 4h | 拆分为 `prompts_core.py` / `prompts_tables.py` / `prompts_action.py`，统一入口 |
| 9 | **P1-09: 阻断点 4——_fingerprint 含风险信号 Hash** | ←P1-06 | 4h | fingerprint 增加 risk_metrics/data_degradation/diff 摘要 |
| 10 | **P1-10: 数据模块注册 + _COMPUTATION_REGISTRY** | ←P1-03,P1-04 | 8h | registry.py 注册 bond_yield + 创建计算模块注册表（预留 6 模块） |
| 11 | **P1-11: 功能开关注册 JSON Schema（18 开关）** | — | 12h | Feature Flag 体系：`is_feature_enabled()` + 18 开关默认值 |
| 12 | **P1-12: 指标级断路包装器** | ←P1-11 | 12h | 指标连续失败 3 次→静默 24h，C20 联动（Flag 关闭不计失败） |
| 13 | **P1-13: 持仓匿名化最小版** | — | 8h | `anonymizer.py`：名称替换/数量模糊/关闭三种模式 |
| 14 | **P1-14: 缓存文件权限保护** | — | 4h | `cache.py` 写缓存设 0o600，启动检查目录权限 |
| 15 | **P1-15: Rf fetcher 测试用例** | ←P1-03 | 4h | mock 正常/异常/手动配置/缓存命中 4 场景 |
| 16 | **P1-16: 管线集成冒烟测试** | ←P1-06~09 | 8h | 最小持仓 fixture 覆盖 4 阻断点，30s 快速执行 |
| 17 | **P1-17: 熔断器改进——指数退避** | — | 4h | 60s→300s→900s→3600s 退避，成功重置 |
| 18 | **P1-18: 熔断器改进——持久化** | ←P1-17 | 4h | 熔断状态持久化到 `circuit_breaker.json`，TTL 24h 清理 |
| 19 | **P1-19: 双熔断器统一网关** | ←P1-18 | 4h | 统一 `circuit_breaker.py` + `provider_registry.py` 网关层 |
| 20 | **P1-20: LLM 失败自动降级模板** | — | 8h | LLM 全失败时 full 路径→both 路径 + 占位文本 |
| 21 | **P1-21: f_context Schema Full Schema 补充** | ←P1-06~08 | 6h | 在 Pre-Schema 基础上追加 Phase 1 新增键定义 |
| 22 | **P1-22: analysis/ 层定位 + category.py→code_utils.py** | — | 12h | 消除 analysis→report 逆向依赖，提取分类函数 + 币种判定 |
| | **合计** | | **~132h** | P1-01/P1-02 已取消（PRE-01 验证 API 不可用） |

### P4 — 基础设施改善

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **加密 API 密钥存储** | 待处理 | 4 小时 | 当前 `llm_key.json` 明文存储 API 密钥。改用对称加密（`cryptography.fernet`），运行时解密进内存。KEK 从环境变量 `INVESTOR_UTIL_KEY` 读取，首次使用自动生成并提示用户保存。包含加密/解密函数、存量密钥迁移脚本、启动时解密失败回退提示。独立于 better-investment-advice，为通用基础设施改善项。 |
