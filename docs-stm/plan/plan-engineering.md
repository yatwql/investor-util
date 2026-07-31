# 工程质量与性能优化：批量并行（rf-1）

> `rf-2`（tiantian.py 拆分）、`rf-3`（fund_style_analysis.py 拆分）、`rf-4`（性能基准）、`rf-1`（批量并行）**均已归档至 `archive/v0.8.x/`**。
>
> tiantian.py 拆分：↗ [`archive/v0.8.x/tiantian-split/tiantian-split.md`](../archive/v0.8.x/tiantian-split/tiantian-split.md)
> fund_style_analysis.py 拆分：↗ [`archive/v0.8.x/fundstyle-split/fundstyle-split.md`](../archive/v0.8.x/fundstyle-split/fundstyle-split.md)
> 性能基准体系：↗ [`archive/v0.8.x/perf-benchmark/perf-benchmark.md`](../archive/v0.8.x/perf-benchmark/perf-benchmark.md)
> 批量并行调度技术设计：↗ [`archive/v0.8.x/batch-parallel/batch-parallel-design.md`](../archive/v0.8.x/batch-parallel/batch-parallel-design.md)
> 批量并行调度迭代计划：↗ [`archive/v0.8.x/batch-parallel/batch-parallel-iteration-plan.md`](../archive/v0.8.x/batch-parallel/batch-parallel-iteration-plan.md)

## 目录

1. [批量数据获取串行瓶颈](#1-批量数据获取串行瓶颈)

---

## 1. 批量数据获取串行瓶颈

### 概述

核心批量数据获取（行情 15 品种、基金排名 10 基金、行业 55+ 代码）在批次内逐资产串行请求，全量 full 路径约 85s 中 ~50s 为串行 IO。

### 根因分析

串行是架构层的有意选择，非代码疏忽。数据获取层围绕**单资产接口**设计（`fetch_market_data(code)`、`fetch_fund_rank(code)` 等均以单代码为粒度）：

| 架构决策 | 影响 | 约束编号 |
|:---------|:-----|:---------|
| Provider Chain 必经 | 每资产独立走完 fallback+熔断器链路保障可靠性 | C6 / §1.4.2 |
| 缓存统一管理 | 按资产代码缓存键 | C2 |
| 数据降级治理 | 按资产维度做降级追踪 | §1.4.5 |
| HTTP 客户端统一 | 同步 httpx 客户端，不支持 async/await | C5 |

### 方案决策：ThreadPoolExecutor 批量并行（否决 async/await）

**否决 async/await 的原因**：
- 与 C5 冲突——httpx 同步客户端统一管理 SSL/超时/连接池，切换 async 需推翻整个 HTTP 层
- 与 C6 冲突——Provider Chain 为同步调用链设计，熔断器/fallback 皆为同步
- 与 C2/C3 冲突——缓存层原子写入为同步 `tempfile.mkstemp` + `os.replace`
- 与 §1.4.5 冲突——降级追踪的调用栈设计假设同步路径
- 改造成本极大（80+ 调用点），且收益上限受限于 IO 等待时间重叠（非 cpu-bound 加速）

**选择 ThreadPoolExecutor 的原因**：
- 与系统现有并行模式一致（附录E：`orch_prep`/`orch_llm_news`/`cache_ops` 均为 TPE）
- Provider Chain 无需改动——每资产 `fetch_with_fallback()` 保持同步，外层 TPE 池调度 N 个资产并行
- 缓存写入天然安全——cache key 异质性避免文件冲突
- 无需新增测试基础设施——ThreadPoolExecutor 无需 pytest-asyncio

### 设计方案

引入批量并行抽象层（`batch.py` + `chain.py` 增强）：

```
                 ┌──────────────────────────────┐
                 │     BatchDispatcher           │
                 │  (ThreadPoolExecutor 池)       │
                 └──────┬───────┬───────┬───────┘
                        │       │       │
                   ┌────┘   ┌───┘   ┌───┘
                   ▼        ▼       ▼
            fetch_with_fallback(code₁)
            fetch_with_fallback(code₂)     ← 每资产独立走完整 Chain
            fetch_with_fallback(codeₙ)
```

核心功能：
1. **链级并行** — N 资产同时走各自的 Provider Chain，IO 等待时间重叠
2. **熔断器感知** — 聚合多资产熔断状态，避免集体突发对同一 Provider 施压
3. **限速控制** — Provider 感知的批间间隔，防 API 限频
4. **降级追踪聚合** — 多资产同时降级时聚合为单一降级记录（适配 §1.4.5）
5. **缓存复用** — 保留 C4 会话级缓存，同资产跨环节重复请求不重复获取

### 工作量估算：**8-10 天**

| 阶段 | 内容 | 天数 |
|------|------|------|
| 批量并行抽象层 | `batch.py` + `chain.py` 增强（熔断器感知/限速/降级聚合） | 3-4 |
| price.py 批量行情 | 主链路行情 15 品种并行（收益最大） | 1.5 |
| fund.py 批量净值/排名 | 基金净值/排名 10 品种并行 | 1 |
| industry.py 批量行业 | 行业 55+ 代码并行 | 1 |
| 测试适配 | ThreadPoolExecutor 并行测试 + 熔断器感知测试 | 1.5 |
| **合计** | | **8-10 天** |

### 约束遵从

| 约束 | 适配方式 |
|:-----|:---------|
| C2/C3 缓存管理 | 并行写仍走 cache/ 子包，cache key 异质性避免文件冲突 |
| C4 会话缓存 | 同资产跨环节通过 DataSourceRegistry.session_cache 消重 |
| C5 HTTP 统一 | TPE 方案不引入 async/await，httpx 同步客户端不变 |
| C6 Provider Chain | 以 `fetch_with_fallback()` 为最小并行单元，不绕过链 |
| C8 统一日志 | 并行日志带资产 code 前缀便于追踪 |
| C10 新闻可配置 | 并行数量受用户配置约束 |
| §1.4.5 降级治理 | 批量失败聚合为单一降级记录，避免 N 条噪声 |

