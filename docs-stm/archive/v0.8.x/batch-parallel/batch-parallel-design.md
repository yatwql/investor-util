# rf-1 批量并行调度技术设计

> **对应自审**：`rf-1`
> **目标**：将 full 路径从 ~84s 优化至 ~67s，核心消除 ~17s 串行 IO 等待
> **状态**：全部完成（dev-verify 1114 ✅ + edge 478 ✅）
>
> **基线修正说明**：审计发现 `market_value.py:523` 已有 `ThreadPoolExecutor(max_workers=8)` + `get_effective_strategy()` 非交易时段缓存策略，行情环节已并行。实际瓶颈为 **fund 排名/持仓（串行 18s）+ industry（3 workers 偏保守 15s）**。修正后预期提速从 35% 降至 ~20%。
>
> **设计缺陷修复**：
> - **TD-5**：`retry_failed()` 改为实例方法复用主 executor，避免线程泄漏（迭代 3）
> - **TD-7**：聚合降级增加 `ratio` + `severity` 字段，防止恶化趋势被掩盖（迭代 4）
> - **TD-8**：fund 批量同时覆盖 `fund_performance.py` 和 `html_builders.py` 两处串行消费者（迭代 6）

---

## 1. 背景与设计总览

### 1.1 问题定义

核心批量数据获取（行情 15 品种、基金排名 10 基金、基金持仓 10 基金、行业 55+ 代码）在批次内逐资产串行或并发不足。审计发现行情环节已有 TPE 并行，实际瓶颈在**未并行或并行度较低**的环节。

### 1.2 当前管线实测基线

```
prepare_report_data:
  ├── 行情获取(已并行 8w)     ~14s   ← 已优化，不动
  ├── 批量指数(orch_prep 2w)  ~2s    ← 已优化，不动
  ├── 穿透计算 (含 IO+CPU)   ~30s   ← 核心优化对象
  │   ├── fund 持仓获取(串行)  ~8s   ← 需要批量
  │   ├── 股票层处理            ~2s   ← CPU bound
  │   ├── 行业分类(batch 3w)  ~15s   ← 可优化
  │   └── 穿透分类/排序        ~5s   ← CPU bound 不动
  ├── 业绩排名获取(串行)      ~10s   ← 需要批量
  ├── LLM+新闻(已有并行)      ~15s   ← 已有并线，不动
  ├── 组合校准/量化指标       ~10s   ← CPU bound 固定开销
  └── 其他开销                 ~3s   ← 固定开销
                                ────
  full 路径合计:             ~84s
```

### 1.3 改造目标与期望提速

| 环节 | 当前 | 并行预期 | 改善 | 方式 |
|:-----|:----|:---------|:-----|:-----|
| 基金排名 (10基金) | ~10s 串行 | ~4s | -6s | BatchDispatcher 3w |
| 基金持仓 (10基金) | ~8s 串行 | ~3s | -5s | BatchDispatcher 3w |
| 行业 (55+代码) | ~15s (3w) | ~8s (8w) | -7s | BatchDispatcher 8w + 通用重试 |
| **串行 IO 可节约** | **~33s** | **~15s** | **-18s** | |
| **full 路径总时间** | **~84s** | **~67s** | **-20%** | |

> 实际上限受限于：LLM 调用（15s 不可并行）、穿透计算与行情依赖链、CPU 固定开销。

### 1.4 设计缺陷修复清单

| 编号 | 缺陷 | 影响 | 修复方式 | 迭代 |
|:-----|:------|:-----|:---------|:-----|
| **TD-5** | `retry_failed()` 每次调用新建 TPE → 线程泄漏 | industry.py 55+ 代码重试轮泄漏 55 个线程 | 改为实例方法复用主 executor | 3 |
| **TD-7** | 聚合降级 `record_aggregated` 不区分 3/15 和 15/15 | 连续 3 次大跌 vs 小毛刺无法区分 | 增加 `ratio` + `severity` 字段 | 4 |
| **TD-8** | fund 并行只在 `fund.py` 层做了，但 `fund_performance.py` 和 `html_builders.py` 两处串行消费者未切换 | 并行代码写了但不生效 | 两处同时切换，测试覆盖两处 | 6 |
| **TD-4** | `max_total_workers` 漏算已有池 | 计数偏差 | 调至 15，按实际管线计算 | 8a |

### 1.5 不优化项（明确排除）

- **行情环节（已并行）** ：`market_value.py:523` 已有 `TPE(max_workers=8)` + `get_effective_strategy()`，非交易时段全程缓存
- **指数环节（已并行）** ：`orch_prep` 池 2 workers
- **async/await 全链路改造** — 与 C5 冲突，收益有限
- **LLM 调用并行化** — LLM 已按模块并行编排，瓶颈在 API 响应时间
- **报告渲染并行化** — HTML/Excel 渲染为 CPU 密集型
- **HTTP 连接池共享** — 现有连接池已够用

---

## 2. 架构约束遵从矩阵

| 约束 | 约束内容 | 适配方式 | 影响迭代 |
|:-----|:---------|:---------|:---------|
| **C2** | 缓存统一管理 | 并行写入仍走 `cache/` 子包，系列化到 cache key 级别 | 2 |
| **C3** | 缓存原子写入 | TPE 各任务独立调用 `cache_set()`，不改变原子写入路径 | 2 |
| **C4** | 会话级 API 复用 | BatchDispatcher 通过 `session_cache` 消重同资产重复请求 | 2、5、6 |
| **C5** | HTTP 客户端统一 | 使用 TPE 而非 async/await，httpx 同步客户端不变 | 全集 |
| **C6** | Provider Chain 必经 | 以 `fetch_with_fallback()` 为最小并行单元，不绕过链 | 全集 |
| **C8** | 日志统一 | 并行日志使用 `logging.getLogger("invest")`，带资产 code 前缀 | 1 |
| **C11** | 测试标记强制 | 新增测试必须标注对应 marker | 全测试迭代 |
| **C12** | 边缘测试文件隔离 | 边缘场景测试放入 `*_edge.py` | 9 |
| **§1.4.5** | 降级治理 | 批量失败聚合为单一降级记录；`record_aggregated` 提供 ratio+severity | 4 |

---

## 3. 风险总览

| 风险 | 等级 | 缓解措施 |
|:-----|:-----|:---------|
| fund_performance + html_builders 两处消费者漏切一处（TD-8） | 中 | 迭代 6 测试覆盖两文件，验收标准明确两处切换 |
| TPE 嵌套 → industry 批量内的 fetch_industry_data 内部还有 TPE | 中 | 确认 `fetch_industry_data` 内部无 TPE——纯 `fetch_with_fallback()` |
| `retry_failed` 改为实例方法后引入 executor 状态依赖 | 低 | `self._executor` 在 shutdown 后调用 `retry_failed` 抛 `RuntimeError`——文档化 |
| 聚合降级 ratio 字段下游消费者不识别 | 低 | `detail` dict 自由扩展，不识别的消费者跳过即可 |
| Tiantian 反爬对并发敏感（fund 批量 3 workers） | 中 | 默认 3，通过 `batch_rate_limit.tiantian` 可调间隔 |
| 行业全链熔断后 55+ 代码全部 skipped，消费者感知不到 | 低 | 熔断预检日志 WARNING，返回空 dict 时消费者自行处理 |
| C4 session_cache 是否覆盖 penetration.py 中 fund_hold 的重复调用？ | 中 | 确认 `fetch_fund_holdings_cached()` 已使用 session_cache |

---

## 4. 收益分析

### 4.1 直接收益

| 维度 | 当前 | 优化后 | 改善 |
|:-----|:-----|:-------|:-----|
| full 路径总耗时 | ~84s | ~67s | **-20%** |
| 串行 IO 耗时 | ~33s | ~15s | **-55%** |
| 用户等待体验 | 接近 90s | 接近 1min | 可接受阈值提升 |

### 4.2 间接收益

- **批量抽象层复用**：BatchDispatcher 可被未来新增的数据类型直接使用
- **代码一致性**：industry.py 自定义 TPE → 统一 BatchDispatcher + 通用重试
- **3 项设计缺陷修复**：TD-5（线程泄漏）/ TD-7（降级恶化）/ TD-8（切换遗漏）

---

## 6. 附录

### 6.1 设计缺陷修复对照

| 编号 | 缺陷 | 修复方式 | 验证方式 | 所在迭代 |
|:-----|:------|:---------|:---------|:---------|
| TD-5 | retry_failed 新建 TPE 线程泄漏 | 改为实例方法复用 self._executor | 迭代 9 线程泄漏边缘场景 | 3 |
| TD-7 | 聚合降级不区分轻重 | 增加 ratio+severity | 迭代 4 测试 ratio=0.2 vs 1.0 | 4 |
| TD-8 | fund 批量两处消费者未切 | fund_performance + html_builders 同轮切换 | 迭代 6 测试两文件 | 6 |
| TD-4 | 线程池上限漏算 | 调至 15 + 文档 | 迭代 8b 集成测试 | 8a |

### 6.3 配置新增（config.json）

```jsonc
{
  "batch": {
    "max_total_workers": 15,
    "fund_workers": 3,
    "industry_workers": 8
  },
  "batch_rate_limit": {
    "tencent": 0.0,
    "sina": 0.0,
    "eastmoney": 0.1,
    "tiantian": 0.5,
    "eastmoney_industry": 0.05
  }
}
```

### 6.5 未来优化方向（不在本轮范围）

以下项在本轮不实施，但作为文档化可追踪的后续方向：

| # | 方向 | 内容 | 触发条件 | 收益预期 |
|:--|:-----|:------|:---------|:---------|
| F1 | fund 持仓 + industry 并行化 | 当前 `_merge_fund_layer` → `_enrich_with_industry_api` 在 `compute_penetration_top10()` 内串行。通过重构 penetration 开始阶段就同时启动两个 batch，可让 fund 持仓和行业分类**真正并行** | 本次完成后持仓+行业总耗时仍 > 15s | 额外 -4~5s（3s+8s → 5s～6s） |
| F2 | fund 排名 session_cache | 当前 fund 排名只有文件缓存无 session_cache。Excel 渲染阶段写完排名后，HTML 渲染靠文件缓存去重（1s 左右）。若加 session_cache 可消除文件 IO | 文件缓存去重耗时 > 0.5s | 额外 -0.5s |
| F3 | `cache/operations.py` `refresh_fund_cache()` 并行化 | 当前 `warm_cache=True` 时串行更新所有基金缓存，但 `warm_cache` 默认 False 不在管线热路径 | 用户开启 `warm_cache` 且等待 > 10s | 低（冷路径） |
| F4 | 日志噪声控制标准化 | BatchDispatcher 单资产失败已降为 DEBUG（Iter 1），但 `cache.py`/`chain.py` 中仍有单资产 ERROR | 用户反馈日志噪声 | 可维护性改善 |
