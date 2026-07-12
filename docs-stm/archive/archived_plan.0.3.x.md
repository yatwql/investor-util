# 实现计划归档 — v0.3.x

> 归档时间：2026-07-12
> 原始文件：`docs-stm/managements/plan.md`
> 涵盖版本：v0.3.0 ~ v0.3.8

---

## D-8b 全面审查修复（R-160 ~ R-176，v0.3.3）

D-8b 审查发现的 17 项代码质量问题，全部在 v0.3.3 修复：

| # | 标题 | 修复版本 |
|:-:|:-----|:--------|
| R-161 | TOCTOU 竞态 — fetcher/chain.py 锁合并 | v0.3.3 |
| R-162 | `_TRANSPORT_FAILURE` 类型污染 — 纯哨兵替换 | v0.3.3 |
| R-163 | 废弃 build-backend — setuptools 切换 | v0.3.3 |
| R-164 | 配置模板一致性防护 — 新增测试 | v0.3.3 |
| R-165 | Ruff 规则集升级 — SIM/UP/ARG/PERF | v0.3.3 |
| R-166 | mypy 严格模式升级 — 77 errors → 0 | v0.3.3 |
| R-167 | `_ext_memo` 会话级复用缓存推广 | v0.3.3 |
| R-168 | 配置 mtime+size 双因子缓存 | v0.3.3 |
| R-169 | 429 API 限速差异化提示 | v0.3.3 |
| R-170 | 新闻流水线集成测试修复 | v0.3.3 |
| R-171 | CI/CD 流水线配置 | v0.3.3 |
| R-172 | HTTP 异步客户端支持 | v0.3.3 |
| R-173 | ThreadPoolExecutor 集中管理 | v0.3.3 |
| R-174 | 配置校验去重 — `_section()` 辅助函数 | v0.3.3 |
| R-175 | colorama 降级为可选依赖 | v0.3.3 |
| R-176 | docstring 误放修复 | v0.3.3 |

## D-10 数据降级重构（Step A~E，v0.3.3）

`DataSourceRegistry` 单例集中管理熔断器/会话缓存/获取策略选择，`chain.py` 全局变量迁移，`_ext_memo` 模块级缓存迁移。

## R-188~R-191（v0.3.3）

3 项存量测试断言对齐 + eastmoney_industry 局部熔断器迁移。

## R-211 测试隔离补完

测试输出目录/日志文件/xdist worker 全链路隔离。

## Z6 缓存引擎拆分重构（v0.3.5 ~ v0.3.6）

667 行单体 `cache.py` 拆分为 `cache/` 子包（7 子模块 + services：路径、IO、核心存取、TTL、命中率统计、过期清理、组管理）。持仓跟踪独立为 `services/holdings_tracker.py`（业务层），经 `cache` 包 re-export 保持调用方兼容。同步修复缓存路径偏移（`_PROJECT_ROOT` `dirname` 深度未同步导致 `src/data/cache/` 目录偏移）。
