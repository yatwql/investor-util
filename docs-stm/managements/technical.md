# 个人投资分析报告生成小助手 — 技术设计

> 文档版本：0.8.12-dev

## 目录

- [1. 总体技术架构与概要设计](#1-总体技术架构与概要设计)
  - [1.1 系统分层](#11-系统分层)
  - [1.2 核心数据流](#12-核心数据流)
  - [1.3 模块职责总览](#13-模块职责总览)
  - [1.4 概要设计 — 核心架构决策](#14-概要设计--核心架构决策)
- [2. 数据获取层详细设计](#2-数据获取层详细设计)
  - [2.1 Provider Chain 路由与 fallback](#21-provider-chain-路由与-fallback)
  - [2.2 三层熔断架构](#22-三层熔断架构)
  - [2.3 Fetcher 调度架构](#23-fetcher-调度架构)
  - [2.4 关键机制](#24-关键机制)
- [3. 缓存层详细设计](#3-缓存层详细设计)
  - [3.1 子模块结构](#31-子模块结构)
  - [3.2 核心接口与 TTL 分辨率](#32-核心接口与-ttl-分辨率)
  - [3.3 原子写入与并发安全](#33-原子写入与并发安全)
  - [3.4 指纹驱动失效机制](#34-指纹驱动失效机制)
  - [3.5 缓存分组](#35-缓存分组)
  - [3.6 缓存操作共享层](#36-缓存操作共享层)
- [4. 报告生成层详细设计](#4-报告生成层详细设计)
  - [4.1 管线总览](#41-管线总览)
  - [4.2 报告编排器](#42-报告编排器)
  - [4.3 Excel 管线](#43-excel-管线)
  - [4.4 HTML 管线](#44-html-管线)
  - [4.5 章节可见性两层模型](#45-章节可见性两层模型)
  - [4.6 报告序号可配置](#46-报告序号可配置)
  - [4.7 组合历史走势计算算法](#47-组合历史走势计算算法)
  - [4.8 基金深度分析](#48-基金深度分析)
  - [4.9 资产穿透 TOP10](#49-资产穿透-top10)
  - [4.10 财经新闻热点与持仓关联分析](#410-财经新闻热点与持仓关联分析)
  - [4.11 数据降级治理体系](#411-数据降级治理体系)
- [5. LLM 集成层（概要设计）](#5-llm-集成层概要设计)
  - [5.1 架构总览](#51-架构总览)
  - [5.2 调用链概览](#52-调用链概览)
  - [5.3 模块清单](#53-模块清单)
  - [5.4 多 Provider 链模式](#54-多-provider-链模式)
  - [5.5 关键机制](#55-关键机制)
- [6. 辅助模块详细设计](#6-辅助模块详细设计)
  - [6.1 配置管理](#61-配置管理)
  - [6.2 中央注册表](#62-中央注册表)
  - [6.3 市场时段判断](#63-市场时段判断)
  - [6.4 持仓读取与列校验](#64-持仓读取与列校验)
  - [6.5 代码类型判定中心化](#65-代码类型判定中心化)
  - [6.6 HTTP 客户端统一](#66-http-客户端统一)
- [7. 模块间依赖关系](#7-模块间依赖关系)
- [8. 架构设计约束](#8-架构设计约束)
  - [8.1 数据获取层约束](#81-数据获取层约束)
  - [8.2 缓存层约束](#82-缓存层约束)
  - [8.3 报告层约束](#83-报告层约束)
  - [8.4 LLM 集成层约束](#84-llm-集成层约束)
  - [8.5 基础设施约束](#85-基础设施约束)
  - [8.6 测试约束](#86-测试约束)
- [附录](#附录)
  - [附录 A：目录结构](#附录-a目录结构)
  - [附录 B：数据源一览](#附录-b数据源一览)
  - [附录 C：缓存 TTL 明细](#附录-c缓存-ttl-明细)
  - [附录 D：降级层级与阈值定义](#附录-d降级层级与阈值定义)
  - [附录 E：线程池分布](#附录-e线程池分布)
  - [附录 F：指标降级依赖矩阵](#附录-f指标降级依赖矩阵)
  - [附录 G：报告生成降级路径矩阵](#附录-g报告生成降级路径矩阵)
  - [附录 H：pipeline_data Schema 定义](#附录-hpipeline_data-schema-定义)

---

## 1. 总体技术架构与概要设计

### 1.1 系统分层

系统按数据流向分为五层，由贯穿层串联。整体架构如下：

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                        输入层                                      │
  │             持仓 xlsx ──→ reader.py ──→ models.Holding             │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │ holdings
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                       数据获取层 (fetcher/)                        │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
  │  │ price.py │ │ index.py │ │ fund.py  │ │industry  │ │ 其他    │ │
  │  │腾讯→新浪  │ │ 指数直调  │ │天天解析  │ │ push2    │ │ ...    │ │
  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
  │       │            │            │            │            │       │
  │  Provider Chain 路由 + fallback + 熔断器 (provider_registry.py)  │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                        缓存层 (cache/)                              │
  │        泛用 JSON KV · TTL · 指纹失效 · 分组 · 原子写入             │
  │        大文件 gzip · 路径安全 · 文件损坏自恢复                      │
  │        缓存操作共享层 (operations.py — TUI/CLI 共用)               │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                      报告编排层 (orchestrator.py)                  │
  │  数据准备 → 快照 → 历史走势 → LLM+新闻并取 → 双管线  │
  │              内部管理 orch_prep / orch_llm_news 线程池             │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │ info 字典
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                        报告生成层 (report/)                         │
  │  ┌─────────────────────────┐   ┌───────────────────────────────┐  │
  │  │   Excel 管线            │   │   HTML 管线                   │  │
  │  │   openpyxl              │   │   Jinja2 模板                 │  │
  │  │   双端共享 data_status   │   │   CSS order 视觉排序          │  │
  │  └─────────────────────────┘   └───────────────────────────────┘  │
  └───────────────────────────────────────────────────────────────────┘
```

**双入口：TUI 与 CLI**

| 入口 | 通道 | 入口文件 | 用户交互层 | 业务逻辑层 | 进度报告 |
|:-----|:-----|:---------|:----------|:----------|:---------|
| TUI | 交互菜单 | `tui.py` | `tui_menu.py` + `handlers_*.py` | `report/orchestrator.py` + `cache/operations.py` | `TuiProgressReporter` |
| CLI | 命令行参数 | `cli.py` | argparse（不经过 handlers_*） | `report/orchestrator.py` + `cache/operations.py` | `CliProgressReporter` |

**共享模块**（TUI/CLI 均直接使用）：

| 共享层 | 位置 | 用途 |
|:-------|:-----|:------|
| 报告编排器 | `report/orchestrator.py` | 三路径报告生成（basic/both/full） |
| 缓存操作 | `cache/operations.py` | 缓存刷新/清理/统计 |
| 进度接口 | `report/progress.py` | `ProgressReporter` 基类 |
| 持仓读取 | `reader.py` | xlsx 解析 |
| 配置管理 | `config/` | 三文件分层配置 |

**分层差异**：TUI 的 `handlers_report.py` / `handlers_cache.py` 是极薄包装层（仅保留交互逻辑如文件选择、结果格式化），CLI 通过 argparse 直接调用共享层，不经过 handlers_*。保证两次实现共用同一套业务逻辑。

**贯穿层**：`config/` · `registry.py` · `provider_registry.py` · `code_utils.py` · `market_hours.py` · `perf.py`

**关键分层原则**：
- 每一层只能依赖其下层和贯穿层，禁止反向依赖
- 数据获取层通过 Provider Chain 解耦数据源，新增数据源无需修改调用方
- 缓存层作为数据获取层和报告层之间的缓冲，提供 TTL、指纹和分组管理
- 报告编排层统筹数据准备和双管线生成，消除 TUI 与 CLI 间的逻辑重复
- 贯穿层提供全局共享的基础设施（配置、注册表、熔断器、代码类型判定）

### 1.2 核心数据流

从持仓文件到报告产出的完整数据流转：

```
持仓 xlsx
    │
    ▼
reader.py ──→ models.Holding / DetailRow（持仓数据模型）
    │
    ├─────────── 获取层（并行）──────────────┐
    │                                        │
    ▼                                        ▼
fetcher/price.py ──→ cache/     fetcher/fund.py ──→ cache/
fetcher/index.py ──→ cache/     fetcher/industry.py ──→ cache/
providers/news_*.py ──→ cache/  fetcher/fund_manager.py ──→ cache/
llm/generators_orchestrator.py ──→ cache/（可选）
    │                                        │
    └─────────────────┬──────────────────────┘
                      │
                      ▼
          报告编排层（orchestrator.py）
              合并为 info 字典
    {
      market_data:     {code: {price, yesterday_close, ...}}
      index_data:      {index_code: {price, change_pct, ...}}
      fund_data:       {code: {rank, holdings, benchmarks, ...}}
      penetration_data:{top10, classification, sector, ...}
      news_data:       [{title, source, summary, correlation, ...}]
      llm_data:        {global_macro, expert_review, health_check, ...}
      history_data:    {timeseries, drawdown, return_pct, benchmarks, ...}
      ...
    }
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
   Excel 管线    HTML 管线    (或两者同时)
   .xlsx 报告    .html 报告
```

**报告类型与对应路径**：

| 报告类型 | 菜单 | 数据准备深度 | 输出格式 | LLM |
|:---------|:----|:------------|:---------|:----|
| `basic` | E | 行情+指数（无穿透/分类/新闻） | Excel 单格式 | ❌ |
| `both` | B | 轻量行情 + 快照 + 历史走势（条件） | HTML + Excel | ❌ |
| `full` | L | 完整行情 + 穿透 + 快照 + 历史走势 + 资金流向 | HTML + Excel | ✅ |

### 1.3 模块职责总览

| 层次 | 模块 | 职责 | 文件 |
|:-----|:-----|:------|:-----|
| **用户交互** | TUI 主循环 | 菜单编排、用户交互流 | `tui.py` / `tui_menu.py` |
| **用户交互** | CLI 命令行 | argparse 解析、共享层直调、定时任务驱动 | `cli.py` |
| **用户交互** | Handler 命令 | TUI 命令 → 委托编排层或共享层 | `handlers_*.py` |
| **用户交互** | 进度报告 | ProgressReporter 解耦进度输出 | `report/progress.py` |
| **用户交互** | CLI 进度报告 | CliProgressReporter（logging 输出 / verbose stderr） | `report/cli_progress.py` |
| **输入** | 持仓读取 | xlsx 解析、列校验、多账户 | `reader.py` |
| **配置** | 配置管理层 | 三文件分层配置 | `config/` |
| **注册** | 中央注册表 | 数据模块 + 报告模块注册 | `registry.py` |
| **数据获取** | 数据源注册中心 | 熔断器、会话缓存、策略、审计 | `provider_registry.py` |
| **数据获取** | Fetcher 调度 | Provider Chain 路由、数据获取 | `fetcher/price.py` 等 |
| **数据获取** | 数据源 Provider | 外部 API 封装 | `providers/*.py` |
| **缓存** | 缓存引擎 | 泛用 JSON KV、TTL、指纹、分组 | `cache/` |
| **缓存** | 缓存操作共享层 | TUI/CLI 共用的业务级缓存操作 | `cache/operations.py` |
| **编排** | 报告编排器 | 数据准备 → 管线编排 | `report/orchestrator.py` |
| **报告** | Excel 管线 | openpyxl 写入 | `report/excel_generator.py` |
| **报告** | HTML 管线 | Jinja2 模板渲染 | `report/html_writer.py` |
| **报告** | 内容模块 | 各页签写入器 | `report/*.py` |
| **LLM** | 智能分析 | Claude/OpenAI/Gemini 调用、Provider Chain 策略路由、Multi-Provider 多链切换、fingerprint 指纹缓存、Extended Thinking、骨架流程、并行编排、费用估算 | `llm/` |
| **贯穿** | 代码类型判定 | 资产识别原语 | `code_utils.py` |
| **贯穿** | 交易时段判断 | A 股时段、午间休市 | `market_hours.py` |
| **贯穿** | HTTP 客户端 | 统一工厂 | `http_client.py` |
| **贯穿** | 性能收集 | PerfCollector 三路径计时 + perf_history.jsonl 持久化 | `perf.py` |

### 1.4 概要设计 — 核心架构决策

以下五项跨模块架构决策贯穿系统全局，是所有新增/修改代码的设计基础。

#### 1.4.1 代码类型判定中心化

**决策**：所有资产代码类型判定集中到 `src/python/code_utils.py`，禁止任何模块自行实现判定逻辑。

**动机**：系统 20+ 处需要判断资产类型（A 股/ETF/基金/QDII/港股/债券等），分散判定导致代码前缀知识散落、新增资产类型时需全局搜索替换。

**原语体系**（详见 [§6.5](#65-代码类型判定中心化)）：

```
判定维度：
  代码前缀 → is_a_share_code() / is_exchange_fund_code() / is_hk_stock_code() / ...
  名称关键词 → is_qdii_by_name() / is_etf_by_name() / is_bond_fund_by_name() / ...
  复合判定 → is_otc_fund_by_name(name, code) / is_etf_by_name_or_code() / ...
```

#### 1.4.2 Provider Chain 必经

**决策**：大多数数据获取必须通过 `fetcher/chain.py` 的 `fetch_with_fallback()`，不得直接调用 Provider 函数。

**动机**：跳过 Chain 直接调用 Provider 会导致三方面失效：
1. **熔断器不被激活** — 故障后无冷却恢复
2. **fallback 链路断路** — Provider 失败时不会自动递补
3. **日志审计缺失** — 故障记录无法集中追踪

**唯一例外**：`fetcher/index.py` 直调 Provider（双链路 fallback 硬编码在模块内），原因是指数数据不适用熔断器的单股票级粒度。

#### 1.4.3 缓存统一管理

**决策**：所有持久化缓存必须通过 `cache/` 子包的 `get()`/`set()` 接口读写，写入必须使用 `tempfile.mkstemp` + `os.replace` 原子写入模式。

**动机**：直接操作 `data/cache/` 文件系统导致 TTL 失效、分组清理遗漏、路径穿越等隐患。直接覆写文件在断电/崩溃时产生半写损坏文件。

#### 1.4.4 报告配置化

**决策**：报告 18 个模块的序号、显示名称、章节可见性由配置驱动，消除硬编码。渲染期数据通过模板 context 传递，禁止写入模块级全局变量。

**两层可见性模型**：

```
section_visible = board_enabled(section.type) AND data_available(section.data_flag)
```

| 层级 | 含义 | 来源 |
|:-----|:------|:------|
| board 层 | 用户配置的章节开关 | `config.json`（`enable_b_series`/`enable_news`/`enable_history`） |
| data 层 | 运行时数据可用性 | 各子模块返回值非 None 判定 |

#### 1.4.5 数据降级治理体系

**决策**：数据获取过程中任何环节失败都应静默降级而非中断报告生成，降级状态在报告中可视化呈现。

```
                          ┌──────────────────────┐
                          │   数据获取请求         │
                          ▼                      │
              Provider Chain 遍历                │
              ↓ 成功 → 返回最新数据               │
              ↓ 失败 → 递补下一 Provider          │
                          ▼                      │
              ┌──────────────────────┐           │
              │ 全链均失败？          │           │
              └──────┬───────┬───────┘           │
                    Yes       No                 │
                     ▼                           │
              ┌──────────────────────┐           │
              │ 尝试过期缓存降级      │──继续遍历→─┘
              │ (CACHE_WEEKLY=7天)   │
              └──────┬───────┬───────┘
                  有缓存      无缓存
                     ▼           ▼
              ┌──────────┐ ┌──────────────┐
              │返回旧数据 │ │抛异常         │
              │+降级标记  │ │调用方写入占位 │
              └──────────┘ └──────────────┘
```

**双重降级系统**：

| 系统 | 层级 | 管什么 | 粒度 | 恢复方式 |
|:-----|:-----|:-------|:-----|:---------|
| DataSourceRegistry | 熔断层（HTTP 级） | 这个 Provider 能不能调用 | per-provider | 固定 300s 冷却 |
| DegradationTracker | 降级决策层（数据质量级） | 这批数据能不能信任 | per-source | 跨会话持久化 |

[↑ 回到顶部](#目录)

---

## 2. 数据获取层详细设计

### 2.1 Provider Chain 路由与 fallback

Provider Chain 采用**职责链（Chain of Responsibility）模式**：每个数据类型定义一条优先级链路，`fetch_with_fallback()` 依次尝试，失败则递补下一 Provider。

#### 数据的默认链路

```
                           Provider Chain 结构
 ┌──────────────────────────────────────────────────────────────────┐
 │  price_stock:   腾讯财经 (qt.gtimg.cn)  →  新浪财经 (hq.sinajs.cn)│
 │  price_fund_otc: 东方财富净值 API（直达，无备用）                   │
 │  history_stock:  腾讯财经 K 线          →  新浪财经 K 线          │
 │  history_index:  腾讯财经 K 线          →  新浪财经 K 线          │
 │  history_index_us: 新浪财经 K 线        →  腾讯财经 K 线          │
 │  history_fund_otc: 天天基金 pingzhongdata → 东方财富净值分页       │
 │  industry:       东方财富 push2          →  行情页 quotedata      │
 │  fund_rank:      天天基金（直达）                                   │
 │  fund_hold:      天天基金（直达）                                   │
 └──────────────────────────────────────────────────────────────────┘
```

`preferred_provider` 可在 `config.json` 中手动将某类型的首选 Provider 调整到链首。

#### 失败检测

以下情况均视为 Provider 失败，触发递补：
- 返回空数据（`None` 或空列表）
- HTTP 错误（4xx/5xx）
- JSON 解析异常
- 超时/断连/DNS 解析失败
- 数据验证未通过（如名称不匹配、price_date 非当前交易日）

#### fetch_with_fallback() 完整流程

```
请求 data_type + code
     │
     ▼
┌─────────────────┐
│ cache_get(key)  │─── 命中且未过期 ───→ 直接返回缓存数据
│ （先检查缓存）   │
└────────┬────────┘
    未命中或过期
         │
         ▼
┌─────────────────┐
│ 获取 chain 列表  │←── _DEFAULT_CHAINS[data_type] + preferred_provider 覆盖
└────────┬────────┘
         │
         ▼
    ┌────┴────┐  ←── 对 chain 中每个 provider_name 循环
    │         │
    ▼         │
┌──────────────────────┐
│ is_circuit_broken()  │─── 已熔断 → 跳过，尝试下一个 Provider
└────────┬─────────────┘
    未熔断
         │
         ▼
┌──────────────────────┐
│ _try_provider_fetch  │
│  → catch 异常         │
│  → 调用 fetch_fn()    │
│  → validate()         │
│  → transform()        │
└────────┬──────────────┘
         │
    ┌────┴────────────┐
    │                 │
    成功              失败
    │                 │
    ▼                 ▼
┌──────────┐   ┌──────────────┐
│success() │   │ 传输级异常?   │
│cache_set │   ├─────┬───────┤
│返回数据   │   │ YES │  NO   │
└──────────┘   │     │       │
               ▼     │       │
          ┌────────┐ │       │
          │failure │ │       │
          │熔断计数 │ │       │
          └────────┘ │       │
                     ▼       ▼
                ┌──────────────┐
                │ 不计入熔断   │
                │ 继续下一链路  │
                └──────────────┘
                         │
                    ┌────┘
                    ▼
           全部 Provider 失败?
           ┌──────┴──────┐
          YES              NO（回到循环顶）
            │
            ▼
    ┌─────────────────┐
    │ 过期缓存降级      │─── cache_get(key, CACHE_WEEKLY=7 天)
    │ (stale fallback) │     命中? → 返回旧数据
    └────────┬────────┘     未命中? → 返回 None
             │
             ▼
    ┌─────────────────┐
    │ 全链路不可用      │─── 调用方处理（占位文本/异常）
    └─────────────────┘
```

**消费方透明设计**：市场行情批量请求时（如 `report/market_value.py`），每个代码独立触发 Chain，失败资产在汇总日志中列出，不影响其他资产获取。

### 2.2 三层熔断架构

由 `DataSourceRegistry` 单例（`src/python/provider_registry.py`）统一管理，采用**双锁设计**（`_provider_lock` + `_cache_lock`）使熔断操作和会话缓存互不阻塞。

```
┌──────────────────────────────────────────────────────────────────┐
│  DataSourceRegistry（单例）                                       │
│                                                                   │
│  ┌─ 第 1 层：熔断预检 ──────────────────────────────────────┐   │
│  │  get_effective_strategy(code_type, chain, market_open)      │   │
│  │  → QDII/港股恒为 LIVE_FETCH                                 │   │
│  │  → 非交易时段 → CACHE_ONLY（只读缓存，不发起 HTTP）           │   │
│  │  → 全链熔断 → CACHE_ONLY 降级                               │   │
│  │  → 正常盘中 → LIVE_FETCH                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ 第 2 层：Provider 级熔断 ───────────────────────────────┐   │
│  │                                                              │   │
│  │  ┌─────────┐    连续 3 次     ┌──────────┐    冷却期满      │   │
│  │  │  正常    │ ───────────────→ │  熔断中   │ ─────────────→ │   │
│  │  │ (Closed) │                 │ (Open)   │                 │   │
│  │  └────┬────┘                 └────┬─────┘                 │   │
│  │       │                           │                        │   │
│  │       │ record_success()          │ 冷却期满自动解除       │   │
│  │       │ ← 重置熔断计数             │ 重置 failures=0       │   │
│  │       │                           │ 放行一次试探           │   │
│  │       │                           │                        │   │
│  │  仅传输级异常（超时/断连/DNS/5xx）触发 record_failure()      │   │
│  │  代码级空结果（API 正常返回 None）不计入熔断计数器            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ 第 3 层：冷却试探恢复 ─────────────────────────────────┐   │
│  │  cooldown_secs 期满后 is_circuit_broken() 自动             │   │
│  │  1. 设置 is_skipped = False                               │   │
│  │  2. 重置 consecutive_failures = 0                         │   │
│  │  3. 返回 False（未熔断），下次调用即为试探                  │   │
│  │  试探成功 → record_success() → 恢复正常                    │   │
│  │  试探失败 → 重新熔断                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─ 会话级缓存（C4 约束） ──────────────────────────────────┐   │
│  │  domain = "industry" / "industry_rest" / "extended" / ...   │   │
│  │  session_cache_get/set(domain, code)                        │   │
│  │  NOT_FOUND sentinel 区分 None vs 未缓存                     │   │
│  │  2000 条/domain O(1) 淘汰                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

#### 熔断参数对比

| 维度 | 单股票 API | 批量 API（eastmoney_industry） | LLM 熔断器 |
|:-----|:----------|:-----------------------------|:----------|
| 实现位置 | `provider_registry.py` | `provider_registry.py` | `llm/circuit_breaker.py` |
| 熔断阈值 | 连续 3 次传输级失败 | 连续 6 次传输级失败 | 连续 N 次 |
| 冷却时长 | 指数退避 60s→300s→900s→3600s | 120s | 60s |
| 试探次数 | 冷却期满放行一次 | 冷却期满放行一次 | 半开状态放行一次 |
| 恢复条件 | 试探成功 → record_success | 试探成功 → record_success | 半开成功 → 关闭熔断 |
| 持久化 | `data/state/circuit_breaker.json` | `data/state/circuit_breaker.json` | 会话级（无持久化） |

**指数退避**：单股票 API 熔断器冷却时间采用指数退避策略（60s→300s→900s→3600s），每次连续失败冷却时长翻倍递增，成功恢复后重置为基础值。

**跨会话持久化**：熔断器状态持久化到 `data/state/circuit_breaker.json`，与 `data/cache/` 隔离，避免缓存清理误删。会话重启后恢复熔断记忆。

**双熔断器统一网关**：`provider_registry.py` 和 `circuit_breaker.py` 通过统一的熔断网关管理。Provider 级熔断（HTTP 传输层）管"某个数据源能不能调用"；数据模块级熔断（业务层）管"某类数据是否跳过"。两熔断器状态同步。

#### Chain 自动注册

`fetcher/chain.py` 在模块加载时自动调用 `get_registry().register_default_chains()`，从 `_DEFAULT_CHAINS` 配置注册所有 provider 和 chain。在 `register_default_chains()` 中 per-provider 配置 tier/timeout/failure_threshold/cooldown_secs（如 eastmoney_industry 阈值 6 次/冷却 120s）。

#### 策略选择器

`DataSourceRegistry.get_effective_strategy()` 根据代码类型、熔断状态、市场时段返回获取策略：

```
输入: code_type, chain, market_open
           │
           ▼
    ┌──────────────┐
    │ 代码类型感知   │
    ├──────────────┤
    │ QDII/港股?   │─── YES ──→ LIVE_FETCH（不受 A 股时段限制）
    └──────┬───────┘
           NO
           ▼
    ┌──────────────┐
    │ 交易时段检测   │
    ├──────────────┤
    │ 非交易时段?   │─── YES ──→ CACHE_ONLY
    └──────┬───────┘
         交易时段中
           ▼
    ┌──────────────┐
    │ 全链熔断?     │
    ├──────────────┤
    │ is_chain_   │─── YES ──→ CACHE_ONLY（降级）
    │ broken()?   │
    └──────┬───────┘
           NO
           ▼
      LIVE_FETCH
```

#### 统一获取入口 `fetch_or_cached()`

`DataSourceRegistry.fetch_or_cached()` 封装了策略选择 → 执行获取 → 会话缓存的完整流程：

```
fetch_or_cached(code, code_type, fetch_fn, chain, cache_domain, cache_key_fn)
    │
    ▼
get_effective_strategy(code_type, chain)
    │
    ├── LIVE_FETCH: 执行 fetch_fn(code) → session_cache_set(domain, code, result)
    │
    └── CACHE_ONLY:
        ① session_cache_get(domain, code) → 命中则返回
        ② 文件缓存 cache_get(cache_key_fn(code), 7 天)
           → 设置 _cache_date_mismatch 标记
           → 写入 session cache → 返回
```

#### 数据获取全局超时 `phase_timeout()`

`provider_registry.py` 提供 `phase_timeout` 上下文管理器，用于数据获取阶段超时保护：

```
with phase_timeout(seconds=120, phase_name="data_fetch") as ctx:
    for code in codes:
        if ctx.expired: break          # 超时退出
        fetch_market_data(code)        # 已获取的数据保留
        ctx.check()                    # 超时抛 TimeoutError
    # 超时后：已完成的数据保留，未完成的以占位处理
```

- 超时不影响正在运行的 HTTP 线程（Python 无法 kill 线程），结果被丢弃
- 不支持嵌套（检测到嵌套时抛 RuntimeError）
- Context 提供 `expired`、`elapsed`、`remaining`、`check()` 四个接口

#### 审计报告

`DataSourceRegistry.generate_status_report()` 输出所有 Provider 的运行时状态（可用性、连续失败次数、熔断状态、冷却剩余时间、总成功/失败次数等），供调试和监控使用。

### 2.3 Fetcher 调度架构

`src/python/fetcher/` 各模块按数据类型独立封装：

```
fetcher/
├── price.py            股票/ETF 最新价 + 场外基金净值 + 00 代码降级
├── index.py            A 股/美股指数（直调 Provider，不走 Chain）
│                       + fetch_index_history 历史日线（走 Chain，C6 约束）
├── fund.py             基金排名/持仓/基准（天天基金数据）
├── fund_manager.py     基金经理数据（天天基金 HTML 解析）
├── industry.py         行业分类+概念板块（push2 双链路）
├── chain.py            Provider 优先链定义 + fallback 路由 + 增量合并
├── akshare.py          AKShare 数据获取（备用数据源）
├── bond_yield.py       债券收益率数据
├── news.py             新闻数据获取
├── portfolio_history.py 组合历史走势计算（位于 report/ 包）
└── history_diff.py     F1 快照差异计算（纯计算，无 I/O）
```

**并行预热**：`preload_cache()` 对 preload 组使用 `ThreadPoolExecutor` 并行获取，减少串行等待。

**菜单驱动**：菜单 [1] 清除 + 重拉 refresh 组，菜单 [2] 清除 + 重拉 preload 组，均复用 fetcher 模块的预热入口。

### 2.4 关键机制

#### 2.4.1 00 代码降级

**问题**：OTC 基金代码与 A 股代码前缀重叠（均以 `00` 开头），`is_a_share_code()` 无法区分。`price.py` 和 `portfolio_history.py` 需要"先股票链路，失败后基金链路"的双阶段降级。

**判定支持函数**（`code_utils.py`）：

| 函数 | 策略 | 用途 |
|:-----|:------|:------|
| `is_otc_code_overlap(code)` | 仅前缀检测（00 开头） | 快速预筛——是否值得尝试基金净值 API |
| `is_otc_fund_by_name(name, code)` | 名称+代码双维度 | 00 代码+名称含基金关键词→确认为场外基金 |

`_OTC_FUND_NAME_KW = ("混合", "纯债", "短债", "中短债", "利率债", "信用债", "货币", "联接", "增利")`

**price.py 降级流程**：

```
fetch_market_data(code, expected_name)
    │
    ▼
┌──────────────────────────────────────┐
│ 代码类型路由                          │
│ if is_exchange_fund or is_a_share:   │
│   data_type = "price_stock"          │←── 主链路: tencent → sina
│ else:                                │
│   data_type = "price_fund_otc"       │←── 直达: eastmoney
│                                      │
│ _needs_degrade = (data_type=="price_stock" AND code.startswith("00"))
└────────────┬─────────────────────────┘
             │
             ▼
    ┌────────────────────┐
    │ price_stock 链路   │──→ 成功? ──→ 返回结果
    │ tencent → sina    │
    └────────┬───────────┘
        失败（返回 None）
             │
       ┌─────┴─────┐
       │ 需要降级?  │──→ NO ──→ 返回 None（最终失败）
       │（00 代码?）│
       └─────┬─────┘
           YES
             │
             ▼
    ┌────────────────────┐           ┌──────────────────┐
    │ price_fund_otc 链路 │──→ 成功? ──→ 记录"降级成功"  │
    │ eastmoney 净值     │           └──────────────────┘
    └────────┬───────────┘
        失败（返回 None）
             │
             ▼
    记录"降级也失败"
    返回 None
```

**关键设计保障**：
- 主链路成功时永不触达降级，零误判风险
- 降级成功/失败均有日志区分（含资产名称和期望名称）
- `portfolio_history.py` 中 `fetch_with_incremental_fallback()` 对返回空列表的首个 provider 同样执行递补，非简单返回

**`_price_cache_fresh` 收市后新鲜度验证**：

```
_fetch_with_cache_refresh() 返回数据后
    │
    ▼
┌─────────────────────┐
│ is_market_open()?   │── YES → 盘中，短 TTL 已保证实时性，无需验证
└────────┬────────────┘
        NO（盘后）
         │
         ▼
┌─────────────────────┐
│ price_date ≥         │
│ 最近交易日?          │── YES → 新鲜缓存，返回
└────────┬────────────┘
        NO（跨日残留）
         │
         ▼
cache_clear(cache_key) → 强制刷新 → 重新走 Provider Chain
（盘中因 Tencent 不可用降级写入 EastMoney 净值，
  或盘中缓存的上一交易日残留，均在收市后自动清除）
```

#### 2.4.2 指数独立获取

指数数据由 `fetcher/index.py` 直调 Provider，**不走 Provider Chain**：

```
fetch_index_data(code)
    │
    ├── A 股指数 (000001/399001/...)
    │     腾讯财经 (qt.gtimg.cn)
    │         ↓ 失败
    │     新浪财经 (hq.sinajs.cn)
    │         ↓ 均失败
    │     过期缓存降级
    │
    └── 美股指数 (.DJI/.IXIC/.INX)
          新浪财经 (hq.sinajs.cn, JS 变量解析)
              ↓ 失败
          腾讯财经 (qt.gtimg.cn)
              ↓ 均失败
          过期缓存降级
```

**不走 Chain 的原因**：
- 指数无熔断器适用的"故障单元"概念（单指数失败不意味所有指数都失败）
- 双链路 fallback 硬编码在 index.py 内部，双向链路（A 股腾讯→新浪，美股新浪→腾讯）
- 双链路均失败时降级过期缓存

#### 2.4.3 Fallback 日志增强

所有 Provider Chain 的 fallback/降级日志均包含资产 `[code]` 和名称标签：

| 日志类型 | 示例 |
|:---------|:------|
| API 返回空 | `[price_stock] [002943] 新浪财经 返回空，尝试下一链路` |
| 链路切换 | `[price_stock] [002943] 新浪财经 成功` |
| 全链路降级过期缓存 | `[price_stock] [002943] 全部 Provider 不可用，降级使用过期缓存` |
| 00 代码降级触发 | `[price] [002943 广发多因子] 股票链路全部失败，降级尝试东方财富净值链路` |
| 00 代码降级成功 | `[price] [002943 广发多因子] 降级成功——通过场外基金链路获取到净值` |
| 汇总失败资产 | `市场行情获取：14 成功，1 失败；失败资产: ['广发多因子(002943)']` |

[↑ 回到顶部](#目录)

---

## 3. 缓存层详细设计

### 3.1 子模块结构

缓存统一存放在 `data/cache/` 目录，由 `cache/` 子包提供泛用键值对存储接口：

```
cache/
├── __init__.py        公开 API 导出（__all__ 精简形态）
├── _store.py          核心存取：get()、set()、clear()
├── _ttl.py            TTL 查询：get_ttl()、get_cache_age()
├── _io.py             文件 I/O：_read_cache_data()、_write_atomic()
├── _paths.py          路径管理：_cache_path()、_GZIP_THRESHOLD（100KB）
├── _groups.py         分组清理：clear_by_group()、clear_by_prefix()
├── _cleanup.py        过期清理：cleanup_expired()
├── _stats.py          统计：缓存命中率、命中/未命中计数
├── operations.py      缓存操作共享层（TUI/CLI 共用业务逻辑）
└── services/
    └── holdings_tracker.py  持仓跟踪、指纹比对、增量刷新
```

### 3.2 核心接口与 TTL 分辨率

#### 核心接口

| 函数 | 签名 | 说明 |
|:-----|:------|:------|
| `get(key, max_age_seconds)` | `(str, float) → Any\|None` | 先查 `.json.gz`，不存在时回退 `.json`；超龄返回 None |
| `set(key, data)` | `(str, Any) → None` | `{"_ts": now, "_data": data}` 序列化 + 原子写入；≥100KB 自动 `.json.gz` |
| `clear(key)` | `(str) → None` | 同时删除 `.json` 和 `.json.gz` |
| `get_ttl(data_type)` | `(str) → float` | TTL 分辨率（见下方流程图） |
| `clear_by_group(group)` | `(str) → None` | 按 preload/refresh 分组清除 |
| `cleanup_expired()` | `() → int` | 扫描全量缓存，删除超龄项 |

#### TTL 分辨率流程

```
get_ttl(data_type)
    │
    ▼
┌──────────────────────────────┐
│ data_type 在 market_hour_   │
│ aware 列表中?                │── NO ─┐
└────────────┬─────────────────┘       │
            YES                         │
             │                          │
             ▼                          │
┌──────────────────────────────┐       │
│ is_market_open()?            │       │
├──────────────────────────────┤       │
│ YES → 交易时段内              │       │
│   ↓                          │       │
│   market_hour_ttl（config）   │       │
│   默认 30s，范围 [30, 86400]  │       │
│                              │       │
│ NO → 非交易时段               │       │
└────────────┬─────────────────┘       │
             │                          │
             ▼                          ▼
    ┌──────────────────────────────────────┐
    │ config.json → cache_ttl.{data_type}  │
    │ 用户显式配置?                          │
    ├────────────┬─────────────────────────┤
    │ YES → 返回  │ NO → registry 默认值   │
    │ 用户配置值   │ get_cache_ttl_defaults │
    └────────────┘         │
                           ▼
                  ┌──────────────────┐
                  │ 类型未注册?       │
                  ├──────┬───────────┤
                  │ YES  │ NO        │
                  │ 回退  │ 返回默认值 │
                  │86400s│           │
                  └──────┘           │
```

**`market_hour_aware` 类型列表**：由 `config.json` 的 `market_hour_aware` 数组配置（如 `["price", "index"]`），非硬编码。

### 3.3 原子写入与并发安全

**原子写入模式**（C3 约束，`cache/` 和 `config/` 子包共享）：

```
tempfile.mkstemp(dir=cache_dir) → fd, tmp_path
    write(fd, data)
    close(fd)
    os.replace(tmp_path, target_path)  ← 原子替换
```

#### set() 写入细节

```
set(key, data)
    │
    ▼
payload = {"_ts": time.time(), "_data": data}
    │
    ▼
json_str = json.dumps(payload, ensure_ascii=False, indent=2)
    │
    ▼
┌────────────────────────────┐
│ len(raw_bytes) > 100KB?   │
├────────────┬───────────────┤
│ YES → .gz  │ NO → .json   │
└────────────┴───────────────┘
    │
    ▼
tempfile.mkstemp(dir=...) → fd, tmp_path
    │
    ▼
_write_atomic(fd, tmp_path, final_path)
    │
    ├── 成功 → os.replace(tmp_path, final_path)
    ├── FileNotFoundError → 目录被删除? 重试一次
    ├── OSError → 日志 WARNING
    └── PermissionError → 降级到直接写入（Windows 兼容）
```

#### 并发安全

- `os.replace` 保证读取方不会看到半写文件（文件系统级原子操作）
- 多线程同时 `get()` 同一 key 可能产生 TOCTOU 空窗（两线程均认为缓存过期，均拉取 API），但通过 `_write_atomic` 保证同时写入时只有一个生效
- `clear()` 操作使用 `_cache_lock` 互斥

#### 路径安全

- `_cache_path(key)` 对 key 做 `replace("..", "_")` 防目录穿越
- 缓存目录不存在时 `os.makedirs(dir, exist_ok=True)` 自动创建

**项目根路径查找**（`constants.py:_find_project_root()`）：

```
从 src/python/constants.py 所在目录
    → 向上逐层搜索 pyproject.toml 或 .git
    → 找到即停，完全不依赖目录树深度
    → 安全上限 20 层，未找到时按当前文件所在目录兜底
```

所有需定位项目根路径的模块统一从 `constants.PROJECT_ROOT` 导入。

**文件损坏恢复**：`_read_cache_data()` 解析失败时自动 `os.remove` 损坏文件，记录 WARNING 日志，下次调用时重新拉取。

### 3.4 指纹驱动失效机制

**问题**：部分缓存依赖外部输入源（如持仓列表、指数收盘价），输入变化时需重新拉取。但基于名称的缓存键无法感知"数据变了"，只能依赖 TTL 等待过期。

**方案**：缓存文件名中内嵌 MD5 前 12 位十六进制摘要，输入源数据变化时摘要改变，缓存键自动不匹配。

```
文件名模式: {prefix}_{digest}.json
示例:       profit_forecast_a1b2c3d4e5f6.json

读取流程:
    │
    ▼
读取缓存文件 → 提取文件名中的 digest
    │
    ▼
根据输入源数据实时重算 MD5 摘要
    │
    ▼
┌──────────────────────┐
│ digest == 重算值?    │
├────────┬─────────────┤
│ YES →  │ NO →        │
│ 缓存有效│ 缓存未命中   │
│ 返回   │ 跳过读取     │
└────────┘ 触发重新拉取 │
           └────────────
```

#### 指纹类型

| 指纹类型 | 计算位置 | 输入源 | 作用范围 |
|:---------|:---------|:-------|:---------|
| **指数指纹** | `akshare_extras.py:_compute_index_fingerprint()` | A 股+美股指数收盘价（列表拼接→MD5） | `profit_forecast_*`、`sector_flow_*` |
| **代码列表指纹** | `holdings_tracker.py:compute_holdings_fingerprint()` | 持仓+穿透 A 股代码（去重排序→MD5） | `dividend_*` |
| **输入参数指纹** | `news_aggregator.py:_compute_cache_key()` | 新闻源参数+关键词（拼接→MD5） | `news_*` |
| **输入数据指纹** | `llm/fingerprint.py` | LLM 模块依赖数据（持仓汇总/结构序列化→MD5） | `llm_global_macro_*`、`expert_review_*`、`health_check_*`、`penetration_deep_*`、`news_item_*` |

**LLM 指纹筛选**：expert_review / health_check / penetration_deep 的 `_compute_fingerprint()` 在序列化前排除行情波动字段（`price`、`change_pct`），仅品种/份额/成本变化时指纹改变。

**精确键名**：`fund_benchmarks.json`、`fund_concentration_snapshot.json`、`holdings_tracking.json` 等无指纹后缀，仅依赖标准 TTL 过期刷新。

**双保险**：指纹机制与 TTL 互补——指纹未变但 TTL 到期同样触发刷新（TTL 优先，指纹为辅助手段）。

### 3.5 缓存分组

通过 `registry.py` 的 `cache_groups` 字段定义分组，由 `clear_by_group()` 统一管理：

```
                   缓存分组体系
                         │
        ┌────────────────┼────────────────┐
        │                │                 │
        ▼                ▼                 ▼
   ┌─────────┐     ┌──────────┐     ┌──────────┐
   │ preload  │     │ refresh  │     │ 无分组    │
   ├─────────┤     ├──────────┤     ├──────────┤
   │ 价格    │     │ 基金业绩  │     │ 历史股票  │
   │ 指数    │     │ 基金持仓  │     │ 日线     │
   │ LLM 全  │     │ 行业分类  │     │ 历史基金  │
   │ 球宏观  │     │ 新闻聚合  │     │ 净值     │
   │ LLM 智  │     │ 盈利预测  │     │ 集中度   │
   │ 囊团    │     │ 资金流向  │     │ 快照     │
   │ LLM 体  │     │ 基金经理  │     │ 风格快照 │
   │ 检报告  │     │ 基金风格  │     └──────────┘
   │ LLM 穿  │     │ 分红数据  │     （不被菜单
   │ 透分析  │     │ 业绩基准  │     命令误删）
   └─────────┘     └──────────┘
   菜单 [2] 触发    菜单 [1] 触发
```

**缓存分组设计原则**：
- **preload 组**：换持仓文件后应重取的基础行情和 LLM 分析
- **refresh 组**：可手动刷新的基金/行业/新闻等
- **无分组**：历史走势（per-code 缓存，不因切换持仓文件而清除）和基金深度分析快照（精确键名，独立管理）

### 3.6 缓存操作共享层

`cache/operations.py` 封装了 TUI 和 CLI 共用的缓存操作业务逻辑，通过 `ThreadPoolExecutor` 并行执行缓存刷新任务，消除 `handlers_cache.py` 中的逻辑重复。

#### 数据结构

```python
@dataclass
class CacheUpdateResult:
    total_funds: int = 0
    perf_ok: int = 0        # 基金业绩数
    hold_ok: int = 0        # 基金持仓数
    bm_ok: int = 0          # 基准成功数
    pf_ok: int = 0          # 盈利预测
    sf_ok: int = 0          # 资金流向
    ind_ok: int = 0         # 行业分类数
    div_ok: int = 0         # 分红数据
    errors: list[str] = field(default_factory=list)
    # exit_code: 0=全成功 / 1=部分失败 / 2=全无数据

@dataclass
class PositionCacheResult:
    total: int = 0           # 持仓总数
    price_ok: int = 0        # 价格成功数
    a_index_count: int = 0
    us_index_count: int = 0
    errors: list[str] = field(default_factory=list)

@dataclass
class CacheStats:
    total_files: int = 0
    total_size_bytes: int = 0
    expired: int = 0
    hit_rate: float = 0.0
    # 快照目录 + 运行时状态统计
    snapshot_files: int = 0
    state_files: int = 0
```

#### 对外接口

| 函数 | 说明 |
|:-----|:------|
| `update_basic_cache(holdings, reporter) → CacheUpdateResult` | 基金缓存 + 公共缓存（盈利预测/资金流向/行业/分红）并行刷新 |
| `update_position_cache(holdings, reporter) → PositionCacheResult` | 持仓价格 + 指数并行获取 |
| `cleanup_cache(reporter) → int` | 扫描清理过期缓存 |
| `get_cache_stats(reporter) → CacheStats` | 三目录统计（cache + snapshots + state） |

#### 内部线程池

`operations.py` 管理独立的 `cache_ops` 线程池（`max_workers=4`），与 orchestrator 的 `orch_prep`、`orch_llm_news` 池隔离：

```python
_POOL: ThreadPoolExecutor | None = None

def _get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_ops")
    return _POOL
```

**关键设计**：`cache/operations.py` 是 `ThreadPoolExecutor` 的唯一宿主，`handlers_cache.py` 和其他调用方通过调用 `operations.py` 的函数间接使用线程池，不直接持有池引用。

[↑ 回到顶部](#目录)

---

## 4. 报告生成层详细设计

### 4.1 管线总览

`src/python/report/` 采用**编排器 + 内容模块**架构，Excel 和 HTML 双端共享 `data_status.py` 降级状态基础设施。顶层由 `orchestrator.py` 统一调度，TUI 的 `handlers_report.py` 仅作为"薄壳"委托编排器。

```
                                         handlers_report.py
                                              │
                                              ▼
                                     orchestrator.generate_report()
                                      │
                                      ├── basic: 仅 Excel（无数据准备）
                                      ├── both:  HTML+Excel（无 LLM）
                                      └── full:  HTML+Excel+LLM
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    ▼                         ▼                         ▼
          历史走势可选分支               Excel 管线                HTML 管线
          (菜单 L/B)                    │                      │
            │                           ▼                      ▼
            ▼                  excel_generator.py       html_writer.py
      ┌──────────┐                 (编排器 98 行)          │
      │ F1 快照  │                     │                   ▼
      │ 比较     │                     ▼           html_builders.py
      │          │           excel_sheet_factory.py   (数据构建器)
      │ F2 历史  │                     │                   │
      │ 走势计算 │                     ▼                   ▼
      └──────────┘           excel_module_loader.py  tmpl/report_template.html
            │                 (动态加载写入器)         (Jinja2 模板)
            ▼                       │
     注入 info →                内容模块写入器:
     Excel/HTML                  summary / market_value /
                                 category / penetration /
                                 fund_performance /      共享: data_status.py
                                 news_correlation /       (STATUS_MESSAGES/
                                 llm_content /            TIER_PREFIX/
                                                          DegradationTracker)
                                 基金深度分析 4 个 /
                                 excel_writer.py +
                                 styles.py
```

### 4.2 报告编排器

`report/orchestrator.py` 是 TUI 和 CLI 共用的报告编排共享层，负责：

1. **数据准备**：行情获取、指数获取、资产穿透 TOP10
2. **快照创建与差异计算**：F1 持仓快照 + 环比差异
3. **历史走势计算**：F2 组合 as-if 走势 + 基准指数对比
4. **行业资金流向获取**
5. **LLM + 新闻并行获取**（4 分支统一处理）
6. **双管线生成**：HTML + Excel

#### pipeline_data 数据上下文

`report/pipeline_data_builder.py` 集中组装传递给 LLM 的数据上下文 `pipeline_data`。包含 `build()`（A 通道：快照环比差异组装）和 `build_prep()`（B 通道：行情/持仓/指标数据组装）两个构造器，入口统一做类型断言（C19 约束）。

`pipeline_data` 遵循 C19 Schema 契约：所有键必须在 pipeline_data Schema 定义集中存放处预定义类型、版本号和写入/消费模块后，才能在代码中使用该键（详见附录 H）。

#### 三种报告路径

**basic 路径**（菜单 E）：最简路径，仅生成 Excel，不调编排器数据准备层（`prepare_report_data()`），但汇总页签内部通过 fetcher 独立获取指数行情数据：

```
generate_report("basic")
    → 读取章节顺序配置
    → generate_excel_report()
    → 返回 ReportResult
```

**both 路径**（菜单 B）：生成 HTML+Excel，不含 LLM：

```
_generate_report_both()
    → _compute_details()           轻量行情获取（无指数/穿透/分类）
    → capture_snapshot()           F1 快照对比
    → fetch_history_data()         条件：enable_history=True
    → write_html_report()          HTML 管线
    → generate_excel_report()      Excel 管线
```

**full 路径**（菜单 L）：生成 HTML+Excel+LLM：

```
_generate_report_full()
    → prepare_report_data()        完整数据准备（含指数/穿透/分类/明细）
    → capture_snapshot()           F1 快照
    → fetch_history_data()         条件：enable_history=True
    → get_sector_fund_flow()       行业资金流向
    → _fetch_llm_and_news()        LLM+新闻并行（4 分支：均开/仅 LLM/仅新闻/均关）
    → write_html_report()
    → generate_excel_report()
```

#### 进度报告接口

编排器通过 `ProgressReporter` 接口输出进度消息，不直接依赖 TUI 或 `print()`：

```python
class ProgressReporter:
    def info(self, msg: str)       # ℹ️ 进行中
    def ok(self, msg: str)         # ✅ 成功
    def warn(self, msg: str)       # ⚠️ 告警
    def error(self, msg: str)      # ❌ 错误
    def add_error(self, msg: str)  # 累计错误
```

TUI 环境使用 `TuiProgressReporter`（输出到终端），CLI 环境使用 `CliProgressReporter`。

**CliProgressReporter**（`report/cli_progress.py`）行为：

| 模式 | info/ok | warn | error | 输出目标 |
|:-----|:--------|:-----|:------|:---------|
| 常规（verbose=False，默认） | `logging.INFO` | `logging.WARNING` | `logging.ERROR` | logs/app.log |
| verbose（verbose=True） | `logging.INFO` + stderr `[..]/[OK]` | `logging.WARNING` + stderr `[!]` | `logging.ERROR` + stderr `[ERR]` | app.log + stderr |

verbose 模式颜色由 `stderr.isatty()` + `NO_COLOR` 环境变量控制，使用本地颜色常量（不依赖 `ansi_colors` 模块级常量，后者基于 `stdout.isatty()`）。

#### 内部线程池

| 池名称 | 位置 | max_workers | 用途 |
|:-------|:-----|:-----------|:------|
| `orch_prep` | `prepare_report_data()` | 2 | 并行获取 A 股/美股指数 |
| `orch_llm_news` | `_fetch_llm_and_news()` | 2 | 并行获取 LLM + 新闻 |

### 4.3 Excel 管线

**编排器职责**（`excel_generator.py`）：
1. 调用 `create_sheets()` 创建 workbook 和页签
2. 迭代 `excel_module_loader.py` 动态加载的内容模块
3. 每个模块接收 `(ws, info, writer)` → 独立写入页签内容和样式

**页签写入器约定**：`_write_*_sheet()` 接收 `info` 字典 + `writer`，独立负责单个页签的内容和样式，互不依赖。

**内容模块动态加载**：`excel_module_loader.py` 通过模块注册表发现并加载写入函数，新增模块只需在注册表中添加条目，无需修改编排器。

### 4.4 HTML 管线

| 组件 | 文件 | 职责 |
|:-----|:-----|:------|
| 编排器 | `html_writer.py` | 调用 builders → 渲染 → 保存 |
| 数据构建器 | `html_builders.py` | 原始数据 → 结构化渲染对象 |
| 渲染器 | `html_renderers.py` | Markdown→HTML 转换、格式处理 |
| 模板 | `tmpl/report_template.html` | Jinja2 模板 + 宏 |
| 环境 | `html_jinja_env.py` | Jinja2 环境初始化、过滤器注册 |
| 保存 | `html_save.py` | HTML 文件写入 |

**渲染期通信**（C14 约束）：所有渲染期数据（`section_visible_dict` 等）必须通过模板 `render()` 的 context 参数传递，不得写入 `_ENV.globals` 或模块级 dict 作为跨函数通信渠道。单次会话中不变的数据（如 `_ENV` 过滤器注册）不受此限。

### 4.5 章节可见性两层模型

报告模块按两层模型决定是否在最终报告中显示：

```
                         section[key]
                              │
                              ▼
                    ┌─────────────────────┐
                    │ board 层预过滤        │
                    │ board_flags[type]?   │
                    ├──────────┬──────────┤
                    │ False    │ True     │
                    │ (关闭)   │ (开启)   │
                    └──────────┴──────────┘
                         │          │
                    隐藏整个         ▼
                    type       ┌─────────────────────┐
                               │ data 层判断          │
                               │ data_flag 在         │
                               │ data_availability 中 │
                               ├──────────┬──────────┤
                               │ None     │ 有值     │
                               │ (always/ │ (bool)   │
                               │ history) │          │
                               └──────────┴──────────┘
                                    │          │
                                始终可见    True=可见
                                           False=隐藏
```

#### Excel 端实现

`excel_sheet_factory.py:create_sheets()` 分成两步：
1. board 层预过滤：`board_flags` 关闭的 section → `continue`
2. data 层判断：`should_create_sheet(sec, data_availability)` → 按 `sec["data_flag"]` 在 `data_availability` 中查询

#### HTML 端实现

`html_writer.py:_compute_section_visibility()` 集中实现两层合并：

```python
board_flags = {
    "always":   True,
    "b_series": enable_b_series,
    "news":     enable_news,
    "history":  enable_history,
    "llm":      enable_llm,
}

for sec in section_order:
    board_ok = board_flags.get(sec["type"], True)
    if not board_ok: continue
    flag_name = sec.get("data_flag")
    if not flag_name:
        section_visible_dict[sec["key"]] = True
    else:
        section_visible_dict[sec["key"]] = data_flags.get(flag_name, False)
```

#### data_flag 定义

| data_flag | 判定依据 | 对应 section.type | 说明 |
|:----------|:---------|:-----------------|:------|
| `None` | 始终可见 | `always` / `history` | 不依赖数据状态 |
| `manager_data` | `manager_analysis is not None` | `b_series` | B2 基金经理 |
| `overlap_data` | `overlap_matrix is not None` | `b_series` | B3 持仓重合度 |
| `concentration_data` | `concentration_analysis is not None` | `b_series` | B4 持仓集中度 |
| `style_data` | `style_analysis is not None` | `b_series` | B5 基金风格 |
| `include_news` | `include_news` flag | `news` | 新闻关联分析 |
| `llm_enabled` | `llm_enabled_flag` | `llm` | LLM 全部 5 模块 |

`always` 类型模块（summary / market_value / category / penetration / fund_performance）无 data_flag，始终显示。

### 4.6 报告序号可配置

报告 18 个模块的序号/显示名称由 `registry.py` 的 `_REPORT_SECTION_DEFAULT` 注册表驱动，支持用户通过 `config.json` 自定义。

#### 注册表结构

每条记录包含 5 个字段：

```python
{
    "key": "fund_manager",      # 模块标识
    "name": "基金经理变更监控",   # 显示名称
    "number": 6,                 # 默认序号
    "type": "b_series",          # 可见性类型
    "data_flag": "manager_data", # 数据标志键名
}
```

18 个模块分布：`always`×6、`b_series`×4、`news`×1、`llm`×5、`history`×2。

#### 合并规则流程

```
get_report_section_order(config)
    │
    ▼
┌────────────────────────┐
│ config 中有             │
│ report_section_order?  │── NO ──→ 返回完整 18 项默认顺序
└───────────┬────────────┘
           YES
            │
            ▼
分离已配置/未配置模块（llm_usage 除外）
    │
    ├── 已配置 → 使用配置序号，收集到 configured[]
    └── 未配置 → 保持默认序号，收集到 unconfigured[]
    │
    ▼
configured.sort(key=lambda x: x["number"])   ← 按配置序号升序
result = configured + unconfigured            ← 已配置在前，未配置在后
    │
    ▼
找到 llm_usage，从当前位置删除 → 追加到 result 末尾 ← 强制末位
    │
    ▼
返回 result（18 项，key/number/type/data_flag）
```

#### 渲染实现

**连续重新编号**：
1. 从 section_order 筛选所有可见模块（board+data 双层过滤）
2. 将 llm_usage 从可见列表分离，强制追加到末尾
3. 按新顺序从 1 开始分配连续序号

**HTML 端**：导航栏使用 `section_order` 动态循环（只渲染可见模块），CSS `order` 属性视觉排序，章节标题使用 `{{ section_numbers['key'] }}` 动态显示。

**Excel 端**：页签标题采用 `f"{visible_count}.{sec['name']}"` 格式。

### 4.7 组合历史走势计算算法

`portfolio_history.py` 的 `get_combined_timeseries()` 实现 5 步算法链。

#### 算法流程总览

```
输入：各只持仓的历史数据 {holding: [{date, value}, ...]}
    │
    ▼
┌─────────────────────────────────────────────┐
│ ① LOCF 合并                                  │
│ 全程集合并 → 每只持仓沿用上次已知值             │
│ 输出：{date: total_value}                     │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ ② 有效区间双向截断                             │
│ 正向找 valid_start_idx ≥ 覆盖阈值              │
│ 反向找 valid_end_idx ≥ 覆盖阈值                │
│ 截断后区间用于收益率/回撤计算                    │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ ③ 回撤算法 (Peak-to-Trough)                  │
│ 遍历日期，新高更新 peak，记录最深回撤            │
│ 输出：max_drawdown_val, max_drawdown_pct       │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ ④ 累计收益率                                  │
│ first_val = bars[0]["total_value"]            │
│ last_val  = bars[-1]["total_value"]           │
│ total_return_pct = (last-first)/first × 100   │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ ⑤ 年化波动率                                  │
│ daily_returns = [(curr-prev)/prev ...]        │
│ annualized_vol = std(daily_returns, ddof=1)   │
│                   × √252                      │
└───────────────────────────────────────────────┘
```

#### ① LOCF（Last Observation Carried Forward）合并

**问题**：每只持仓的历史数据日期集合不同（股票有完整日 K 线、QDII 净值 T-1 滞后、债券基金更新频率更低）。简单地对交集日期求和会丢失大量数据。

**方案**：对全部出现过的日期做全程集合并合并，某基金在某日无新净值时沿用上次已知值：

```
all_dates = sorted(∪ {dates_of_each_holding})
for each_holding:
    last_val = 0
    for d in all_dates:
        if d in holding_data: last_val = holding[d]
        if last_val > 0: total_value[d] += last_val
```

**效果**：避免 QDII 净值滞后、场外基金更新慢导致当日组合市值骤降、收益率虚低。

#### ② 有效区间双向截断

**问题**：不同基金数据起止日期不同，直接用全部日期计算收益率会失真（边界上只有部分基金有数据）。

**方案**：
- **起算点（valid_start_idx）**：正向遍历，找第一天 ≥ 覆盖阈值
- **终止点（valid_end_idx）**：反向遍历，找最后一天 ≥ 覆盖阈值
- 截断后锁定的区间才是收益率计算的"有效区间"
- 走势图仍显示完整时间线（含边界数据），但累计收益率和回撤指标只以有效区间为基准
- **覆盖阈值**：默认 `0.8`（80%），可通过 `config.json` 的 `history.coverage_threshold` 配置（0~1）

#### ③ 回撤算法（Peak-to-Trough）

```
peak = 0
for each date in sorted_dates:
    tv = total_value[date]
    if tv > peak:
        peak = tv                         # 新高 → 更新峰值
        current_dd_start = date            # 记下潜在回撤起算日
    drawdown = peak - tv                   # 当前回撤金额
    drawdown_pct = drawdown / peak × 100   # 回撤百分比
    if drawdown > max_drawdown_val:        # 追踪最大回撤
        max_drawdown_val = drawdown
        max_drawdown_pct = drawdown_pct
        drawdown_end = date                # 回撤最深日
        drawdown_start = current_dd_start  # 该段回撤的峰值日
```

#### ④ 累计收益率

```
first_val = bars[0]["total_value"]    # 有效区间第一日市值
last_val  = bars[-1]["total_value"]   # 有效区间最后一日的市值
total_return_pct = (last_val - first_val) / first_val × 100
```

#### ⑤ 年化波动率

```
daily_returns = [(curr - prev) / prev for adjacent days]
annualized_vol = std(daily_returns, ddof=1) × √252
```

使用样本标准差（`ddof=1`），交易日假设 252 天。

#### 走势数据获取：增量合并 Fallback

`fetch_with_incremental_fallback()` 与 `fetch_with_fallback()` 的对比：

| 维度 | `fetch_with_fallback` | `fetch_with_incremental_fallback` |
|:-----|:-----------------------|:----------------------------------|
| 用途 | 单次价类数据（价格/行业） | 时序数据（历史走势） |
| 缓存策略 | 先读缓存→命中直接返回 | 先读缓存做底座→增量获取新数据→合并 |
| 过期缓存降级 | 全链路失败时降级 7 天内过期缓存 | 全链路失败时返回空列表 `[]`（显示占位文本） |
| 数据修正感知 | 无感知 | 重叠检测→自动全量刷新（应对除权除息） |

#### 基准指数对比

基准指数历史走势的并行获取与归一化对齐，在 5 步算法链基础上叠加显示。

**配置接口**（`config.json`）：

```json
{
  "history": {
    "benchmark_indices": { "sh000300": "沪深300", "gb_inx": "标普500" },
    "analysis": "auto"
  }
}
```

**技术流程**：

```
get_combined_timeseries()
    │
    ▼ (5 步算法链完成后)
    ┌─────────────────────────────────────┐
    │ self._benchmark_indices 非空?       │── NO → benchmarks = []
    └──────────────┬──────────────────────┘
                   YES
                   ▼
    ┌─────────────────────────────────────┐
    │ fetch_benchmarks(indices, days)     │
    │ (ThreadPoolExecutor 并行获取，       │
    │  走 fetch_index_history → chain)     │
    └──────────────┬──────────────────────┘
                   ▼
    ┌─────────────────────────────────────┐
    │ normalize_benchmarks(bars, raw)     │
    │ LOCF合并→起算日对齐→归一化至100基点  │
    └──────────────┬──────────────────────┘
                   ▼
             benchmarks 列表
```

**防御性编程**：
- `bar.get("date")` 防御性检查（防止 KeyError）
- 每次 index bar 的 close 校验：`isinstance(close, (int, float)) and close > 0`
- 每个基准完成归一化后输出 `logger.info(...)` 
- 异常捕获在 try/except 中，不阻塞主流程

**HTML 渲染**：`drawSimpleChart()` 多 dataset 版本，组合 as-if 曲线（实线）+ 基准指数（虚线，颜色循环），右侧图例显示。使用 Canvas 2D API 原生渲染（无 Chart.js 外部依赖）。

**Excel 渲染**：`portfolio_history` 页签每基准一列（归一化值），`drawdown_analysis` 页签对比指标矩阵。

#### F1 快照存储与清理（history_snapshot.py）

```
save():
    data/history/snapshots/snapshot_{timestamp}.json
    tempfile.mkstemp + os.replace（符合 C3 约束）

prune()：两阶段自动清理
    ① 时间优先：删除超过 HISTORY_SNAPSHOT_RETENTION_DAYS（默认 60d）
                 可通过 config.json history.snapshot_retention_days 配置
    ② 数量兜底：剩余文件超过 HISTORY_SNAPSHOT_MAX_COUNT（默认 365）
                 可通过 config.json history.snapshot_max_count 配置
                 时删最旧超出部分
```

### 4.8 基金深度分析

基金深度分析 4 个模块通过 `enable_b_series` 标志控制条件渲染，跟随 `include_news`（菜单 B/L 时触发）。

```
                    基金深度分析模块架构
                         │
           enable_b_series = True?
                         │
              ┌──────────┴──────────┐
              │                     │
         B2 基金经理变更        B3 持仓重合度
         快照比对检测          Jaccard+重叠率
              │                     │
         B4 持仓集中度          B5 基金风格分析
         TOP N 占比+环比      市值/PE 加权判定
```

#### B2 基金经理变更监控

基于快照比对检测基金经理变更：

```
天天基金 fundf10 基金经理列表 HTML 解析
    │ 获取当前经理姓名 + 任职起始日
    ▼
fund_manager_snapshot 快照（精确键名，每日更新）
    │ 与历史快照比对
    ▼
窗口期计算（任职起始日距今天数）：
    ≤30天   → 🔴 紧急
    ≤90天   → ⚠️ 关注
    ≤180天  → ⚠️ 关注（91~180天范围）
    首次运行 → 📋 首检（自下次起跟踪）
    无变更   → ✅ 正常
```

- 每个基金独立判断，互不干扰
- 快照使用精确键名（`fund_manager_snapshot`），无指纹后缀，每日 TTL 过期自动刷新

#### B3 持仓重合度矩阵

双指标持仓重合度计算（`fund_overlap.py`）：

```
Jaccard 系数 = |A ∩ B| / |A ∪ B|
重叠率      = |A ∩ B| / min(|A|, |B|)
最终重合度  = max(Jaccard, 重叠率)
    │
    ▼
Excel 热力图着色：
    ≥50%  → 红底白字
    30~50% → 橙底白字
    15~30% → 黄底黑字
    >0     → 绿底黑字
    0%     → 无着色
```

触发条件：持仓中基金数量 ≥ 2 只。

#### B4 持仓集中度监控

基于持仓 TOP N 占比 + 环比变化（`fund_concentration.py`）：

```
取每只基金权重最大的前 3/5/10 只标的
    → 加总占比
    → fund_concentration_snapshot 环比比对
    │
    ▼
预警规则（与环比独立叠加）：
    · 前 10 占比环比 +20%  → 🔴 紧急
    · 前 10 占比环比 +10%  → ⚠️ 关注
    · 当前前 10 占比 >80%  → ⚠️ 关注
    · 首次运行               → 📋 首次
```

- 环比变化箭头：↑/↓ 标识方向
- 快照使用精确键名（`fund_concentration_snapshot`），月级 TTL

#### B5 基金风格分析

基于持仓个股市值 + PE 数据的加权风格判定（`fund_style_classify.py` / `fund_style_report.py`）：

```
三级降级链路：
 push2 (精确) → Tencent 扩展字段 (可靠) → 代码前缀估算 (兜底)
    │
    ▼
市值判定：总市值 >500亿=大盘  100~500亿=中盘  <100亿=小盘
估值判定：PE/行业平均PE  <70%=价值  >130%=成长  其余=混合
    │
    ▼
加权投票 → 最终风格 = 市值权重最大的 size + 估值权重最大的 style
    │
    ▼
漂移检测：网格曼哈顿距离 |Δsize| + |Δstyle|（0~4）
    0=无  1=轻度  2=中度  ≥3=严重
```

**性能优化**：
- 会话级缓存委托 DataSourceRegistry session_cache（domain="extended"），同一股票仅首次 HTTP
- Tencent 二级降级基于 registry 熔断器（provider="tencent_style"），避免网络不可达时逐只等待超时
- 独立快照 `fund_style_snapshot` 精确键名，月级 TTL，不受菜单缓存命令影响

### 4.9 资产穿透 TOP10

`compute_penetration_top10()` 纯计算函数，不依赖 openpyxl。

**分类逻辑**：QDII / ETF / 联接 / 债券 / 主动 / 直接持股，基于代码前缀 + 名称规则，所有底层判定委托至 `code_utils`。

**板块分类（双层策略）**：

```
板块 = API 数据优先 (fetch_industry_data(code).industry)
         or 关键词回退 (classify_sector(name, code))
```

**行业/概念数据流**（与新闻关键词体系共享）：

```
持仓列表 + 穿透资产
    │ 提取所有唯一代码
    ▼
batch_fetch_industry_data(codes)
    │ API / 缓存
    ▼
industry_{code}.json
    │
    ├──→ 穿透模块：注入 sector 字段 → 板块列显示 API 数据
    │
    └──→ build_news_data()：行业名/概念名 → 追加到关键词列表
                             → 提高新闻匹配率
                             → 显示 "XX[概念]"
```

### 4.10 财经新闻热点与持仓关联分析

#### 整体流程

```
 五源并行获取
 ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────┐
 │新浪  │ │东财  │ │财联社 │ │华尔街见闻│ │akshare│
 └──┬───┘ └──┬───┘ └──┬───┘ └────┬─────┘ └──┬───┘
    └────────┴────┬───┴─────┬─────┴──────────┘
                  │         │
                  ▼         ▼
           news_aggregator.py   每个源 per_source = max(500, news_top_count×2)
           (多源聚合去重)        news_{md5}.json 缓存，15 分钟 TTL
                  │             MD5 指纹含关键词/参数
                  ▼
           news_keywords.py
           关键词提取：持仓名称片段 + 代码 + 穿透资产 + 行业 + 概念
           4 种类型富化：持仓(0) → 穿透(1) → 概念(2) → 行业(3)
                  │
                  ▼
           news_correlator.py ←── news_correlation(持仓, 新闻) → 关联度评分
           按关联度排序 → 截取 news_top_count 条输出
                  │
           ┌─────┴─────┐
           │           │
           ▼           ▼
       HTML 渲染    LLM 二次关联（可选）
       (蓝/紫/橙/灰 着色)  enabled_llm.news_correlation
```

#### 订阅源端点

| 源 | API | 端点 |
|:----|:-----|:------|
| 新浪财经 | RSS + JSON | `feed.mix.sina.com.cn` |
| 东方财富 | 快讯列表 | `np-weblist.eastmoney.com/comm/web/getFastNewsList` |
| 财联社 | 滚动列表 | `www.cls.cn/v1/roll/get_roll_list` |
| 华尔街见闻 | 直播流 | `api-one.wallstcn.com/apiv1/content/lives`（无鉴权） |
| akshare | 封装 | 财新网 + CCTV |

#### 关键词体系

**4 种类型富化**：

| 类型编号 | 类型 | 来源 | HTML 着色 |
|:--------|:-----|:------|:---------|
| 0 | 持仓 | 持仓名称片段 | 蓝色 |
| 1 | 穿透 | 穿透资产名称 | 紫色 |
| 2 | 概念 | 东方财富 push2 概念板块 | 橙色 |
| 3 | 行业 | 东方财富 push2 行业分类 | 灰色 |

#### 召回策略

`per_source = max(500, news_top_count × 2)` — 每源原始获取量动态计算，保证去重后候选充足。最终截取 `news_top_count` 条按关联度排序输出。

#### 新闻去重算法

`_dedup_by_title()` 采用**两阶段模糊去重 + 实体 bigram + 英数 token 辅助判定**策略。

##### 整体流程

```
_dedup_by_title(items)
    │
    ▼
遍历每篇新闻，对其已保留列表逐条比较：
    │
    ├── ① 同源判定（same_source = True）
    │       提取中文实体 bigram，≥ 4 即合并
    │       （同源不会出现方向对立报道，不依赖比率阈值）
    │
    ├── ② 跨源安全区（ratio ≥ 0.50）
    │       SequenceMatcher 前剥离 "2026年/7月/15日" 等日期模式，
    │       避免不同新闻因共享日期格式虚高 ratio
    │       ratio ≥ 0.50 直接合并，无需 bigram 校验
    │       擦边案例（0.50~0.60）写入锚点
    │
    ├── ③ 跨源候选区（0.30 ≤ ratio < 0.50）
    │       需额外共享 ≥ 3 个实体 bigram（含英数 token）防误杀
    │       → bigram ≥ 3：合并，写入 cross_merge 锚点
    │       → bigram < 3：跳过，写入 cross_skip 锚点
    │
    └── ④ 子串包含降级
           短标题（≥6 字）被长标题完全包含 → 判定为重复
```

##### 核心概念

| 概念 | 含义 | 默认值 |
|:-----|:------|:-------|
| **ratio**（模糊匹配率） | `difflib.SequenceMatcher.ratio()` — 基于标准化标题的字符级相似度 | — |
| **cross_threshold**（跨源阈值） | 跨源新闻触发 bigram 辅助判定的最低 ratio 门槛 | **0.30**（可调） |
| **安全区** | ratio ≥ 0.50，直接合并，不依赖 bigram | ≥0.50 |
| **候选区** | 0.30 ≤ ratio < 0.50，需额外 bigram 校验防误杀 | [0.30, 0.50) |
| **bigram（字符二元组）** | 中文标题的连续 2 字切片，用于提取实体身份 | — |
| **实体 bigram** | 过滤掉财经动词/形容词后的 bigram 集合（含英数 token） | STOP 集含 44 个词 |
| **bigram_overlap** | 两标题实体 bigram 交集大小 | 同源≥4/跨源≥3 判定重复 |
| **同源（same_source）** | 两新闻来自同一源头（如新浪 vs 新浪） | 仅依赖 bigram，不依赖 ratio |
| **跨源（cross_source）** | 两新闻来自不同源头 | 依赖 ratio + bigram 双重判定 |

##### SequenceMatcher 比率

`difflib.SequenceMatcher.ratio()` 计算两个标准化标题的相似度（0.0~1.0），值越高表示字符级匹配越强。经过 `_normalize_title()` 预处理（去除标点/空白/特殊字符、过滤百分比 `\d+(?:\.?\d+)?%` 和金额 `\d+(?:\.?\d+)?[万亿]` 数字模式）后，再剥离 `\d{4}年|\d+月|\d+日` 通用日期模式（防止不同新闻因共享日期格式虚高 ratio）：

- **0.50 以上**：大概率同一事件（如"XX 突破 3 万亿" vs "XX突破3万亿元"）
- **0.30~0.50**：可能同一事件，但用词差异较大（如"XX 创历史新高" vs "XX 再次刷新纪录"）
- **0.30 以下**：不太可能同一事件

##### 实体 bigram 提取

`_extract_entity_bigrams()` 提取标题中的实体特征（中文 bigram + 英数 token）：

```python
步骤：
  ① 英数 token：提取 [a-zA-Z]+ 和 [0-9]+，长度 ≥ 2 过滤单字符噪声
  ② 中文 bigram：正则去除非中文字符 → 滑动窗口取连续 2 字
  ③ 过滤 _STOP_BIGRAMS（财经动词/形容词/噪声）
```

**STOP 词列表**（44 个，不参与实体判定）：上调、下跌、上涨、超越、低于、高于、首次、今日、昨日、本周、上周、本月、上月、盘中、盘后、早盘、午盘、收盘、开盘、不会、将会、成为、宣布、公布、发布、推动、发力、实现、加大、降低、回升、有望、再度、时隔、同比、环比、预计、累计、显示、预期、影响、明显、相关、报告、数据、来源、表示、认为、其中、分别、总额、规定。

**示例**：标题"英伟达Blackwell AI芯片发布" → 英数 token：`{"blackwell", "ai"}`；中文 bigram：英伟、伟达、达、芯片、片发、发布 → 过滤掉"发布"后 → **实体集合：`{"blackwell", "ai", "英伟", "伟达", "芯片", "片发"}`**

##### 两档阈值策略

| 情境 | 判定规则 | 设计依据 |
|:-----|:---------|:---------|
| 同源（same_source） | 实体 bigram ≥ 4 判定重复 | 同源不会出现"突破3万亿"vs"跌破3万亿"对立报道，bigram 足以识别 |
| 跨源安全区（ratio ≥ 0.50） | 直接合并，无需 bigram | 高比率意味着本质相同，不可能误杀 |
| 跨源候选区（0.30 ≤ ratio < 0.50） | ratio ≥ cross_threshold AND 实体 bigram ≥ 3 | 低比率可能只是话题相关而非重复，需 bigram 确认有实质实体重叠 |
| 子串包含 | 短标题（≥6 字）被长标题完整包含 | 兜底，捕获大标题含小标题的极端情况 |

##### 锚点采集体系

去重判定边界案例自动采集到 `dedup_anchors.jsonl`（append-only），供 `calibrate-dedup-threshold.py` 分析阈值合理性：

| 锚点规则 | 采集条件 | 用途 |
|:---------|:---------|:------|
| `same_src` | 同源 bigram 2~5 | 评估同源阈值是否过紧/过松 |
| `cross_safe` | 跨源 ratio 0.50~0.60 | 验证安全区下限是否合理 |
| `cross_merge` | 跨源候选区合并成功（bigram≥3） | 验证候选区判定正确性 |
| `cross_skip` | 跨源候选区但 bigram 不足 | 评估是否需要降低阈值 |

##### 校准工具

`python scripts/calibrate-dedup-threshold.py` 分析 `data/cache/dedup_anchors.jsonl`，输出：

- 各规则覆盖统计（cross_skip / cross_merge / cross_safe / same_src）
- 跨源 ratio 和 bigram 分布，按 bigram 分档（bg=0 无实体重叠 / bg=1 几乎无重叠 / bg≥2 需审查）
- 边界样本明细（前 5~10 条）
- 阈值评估建议（区分"实体重叠漏判"与"日期/财经关键词虚高"）

### 4.11 数据降级治理体系

#### 降级状态基础设施（`report/data_status.py`）

```
┌─────────────────────────────────────────────────────────────┐
│                    DataStatusItem（TypedDict）               │
│  { "available": bool,   数据是否可用                         │
│    "tier": "T2"/"T3"/"T4",  层级                             │
│    "message": str }      最终展示文本，直接渲染               │
│                                                             │
│  STATUS_MESSAGES（常量字典，Excel/HTML 两端共享）             │
│  rank_unavailable:       "基金业绩排名数据不可用，排名列显示 --"│
│  industry_unavailable:   "行业分类数据暂不可用（push2 不稳定）"│
│  profit_forecast:        "盈利预测数据不可用，EPS 列显示 --"  │
│  news_all_failed:        "新闻数据暂不可用，请检查网络连接"   │
│  history_correction:     "检测到历史数据修正，走势可能已重算" │
│  ...（共 16 条，覆盖价格/排名/行业/穿透/盈利/分红/指数/      │
│        基金深度分析/新闻/预警/历史走势）                            │
│                                                             │
│  TIER_PREFIX = {"T2": "⚠", "T3": "ℹ", "T4": "ℹ"}           │
└─────────────────────────────────────────────────────────────┘
```

**与 HTML 端 `raw_data_flags` 的交互边界**：
- `raw_data_flags = False` → 模块隐藏（不显示占位）
- `raw_data_flags = True` 且 `_data_status` 有失败项 → 页签底部显示状态摘要
- `raw_data_flags = True` 且 `_data_status` 全成功 → 一切正常，不渲染摘要

#### Excel 端

| 辅助函数 | 用途 |
|:---------|:------|
| `_write_placeholder(ws, message)` | 数据为空时写入灰色占位文本（合并单元格） |
| `_write_data_status_foot(ws, status)` | 页签底部追加数据源状态摘要行，按 tier 自动匹配前缀 |

#### HTML 端

| 机制 | 用途 |
|:-----|:------|
| `_safe_build_data_status(builder_fn, *args)` | 异常安全构建包装器，构建失败返回空状态 |
| `render_data_status(status)` Jinja2 宏 | 在 `report_template.html` 中条件渲染状态摘要 |

#### DegradationTracker 双信号降级

| 信号 | 默认阈值 | 说明 |
|:-----|:---------|:------|
| 连续失败计数 | T2: 2 次 / T3: 2 次 / T4: 1 次 | 累计失败次数达阈值后触发降级 |
| 缓存陈旧天数 | T2: 3 天 / T3: 14 天 / T4: 7 天 | 距上次成功获取的天数超阈值后触发降级 |

可配置于 `config.json` 的 `degradation` 字段。支持跨会话持久化到 `data/state/.degradation_state.json`。

**与 DataSourceRegistry 的职责边界**：

```
DataSourceRegistry（熔断层）  ─  管"这个 Provider 能不能调用"
    HTTP 层面的快速跳过
    per-provider 粒度
    固定阈值（3次/300s）
    自动冷却恢复

DegradationTracker（降级决策层） ─  管"这批数据能不能信任"
    数据质量层面的占位/降级决策
    per-data_source 粒度
    双信号（失败计数+缓存陈旧），配置可调阈值
    跨会话持久化
```

[↑ 回到顶部](#目录)

---

## 5. LLM 集成层（概要设计）

### 5.1 架构总览

`src/python/llm/` 包按调用层次分为四层，共 16 个子模块（含 fact_checker.py / fallback.py；`prompts.py` 为统一导出入口，实际逻辑在 core/tables/action 3 文件中）：

```
入口层         generators_orchestrator.py    4+1 模块并行编排
                  │
编排层         skeleton.py                   标准/批量模式共享骨架
                  │
API 层         api.py        Provider 路由 + Multi-Provider Chain 遍历
               api_base.py   HTTP 调用 + 重试骨架
               strategy.py   多 Provider 切换策略引擎
                  │
共享层         generators.py         4 个单例生成函数
               generators_news.py   新闻 LLM 批量关联分析
               prompts.py           System/User Prompt 构建
               fingerprint.py       缓存指纹计算
               session.py           会话用量追踪
               cost_tracker.py      Token 预算管理
               pricing.py           费用估算
               markdown.py          Markdown→HTML 转换
               circuit_breaker.py   LLM API 熔断器
               fact_checker.py      LLM 输出伪代码/幻觉过滤
               fallback.py          全失败降级占位模板
```

**LLM 模块配置化**：每个 LLM 模块（global_macro / expert_review / health_check / penetration_deep / news_correlation）在 `registry.py` 中通过 `settings_suffix` 注册，自动派生 `llm_settings.json` 的所有合法键名。

**辩论模式（实验性路由）**：当 Feature Flag `llm_debate_procon` / `llm_debate_conditional` / `llm_debate_qa_concentration` 任一启用时，`generators_orchestrator.py` 中的 `_debate_wrapper` 闭包替换 `_MODULE_FNS["expert_review"]`。辩论模式与标准模式互斥（辩论优先），路由后 `skeleton.generate_llm_module()` 走辩论三段缓存（`llm_debate_pro_` / `llm_debate_con_` / `llm_debate_synthesis_`）而非标准 expert_review 缓存。三段独立的 `DataModuleDef` 注册在 `registry.py` 中（preload 组，24h TTL）。

各子模块的详细设计见 `llm-technical.md` §1~§4（架构总览、模块清单、骨架流程、并行编排）。

### 5.2 调用链概览

LLM 分析从编排入口到最终 HTML 输出，经过缓存检查 → API 调用 → 内容转换 → 缓存写入的完整链路：

```
generators_orchestrator（并行调度 4+1 模块）
    │
    └── skeleton.generate_llm_module()
            │ ① 缓存检查（指纹+TTL）→ 命中则直接返回
            │ ② 乐观预检链首 Provider 缓存键
            │ ③ API 调用（走 Provider Chain）
            ├── api.call_llm()
            │      ├── strategy.resolve_provider_chain() → 策略排序
            │      ├── api.call_provider_entry() × N（逐链尝试）
            │      │      └── _resolve_entry_credentials()（credentials_ref 解析）
            │      └── api_base._attempt_api_call()
            │              ├── Claude → anthropic SDK
            │              └── OpenAI/DeepSeek → openai SDK
            │ ④ 内容过滤安抚重试（空返回时追加安抚提示）
            │ ⑤ Markdown→HTML（markdown.py）
            │ ⑥ 写入缓存（Provider 感知键名，记录实际 Provider 名）
            └── 返回 (result, usage, provider_name) 三元组
```

完整调用链含重试、熔断、截断重试、缓存写入的各分支流程，详见 `llm-technical.md` §3（骨架流程）和 §6（重试与容错）。

### 5.3 模块清单

LLM 集成层提供 5 个分析模块，通过 `llm_settings.json` 的 `enabled_llm` 逐模块独立开关：

| 模块 | 标识 | 功能概要 | 缓存分组 | 默认 TTL |
|:-----|:-----|:---------|:---------|:--------|
| 全球政经局势 | `global_macro` | A 股/美股指数+持仓汇总 → 宏观判断 | preload | 24h |
| 智囊团深度复盘 | `expert_review` | 持仓明细+穿透 → 专业分析师多视角辩论 | preload | 2h |
| 组合体检报告 | `health_check` | 持仓明细（排除行情波动）→ 4 维健康度评分 | preload | 24h |
| 穿透深度分析 | `penetration_deep` | 穿透 TOP10 → 行业/品种/国家集中度分析 | preload | 24h |
| 新闻二次关联 | `news_correlation` | 逐条新闻 → LLM 深度关联评分（批量模式） | refresh | 1h |

每个模块的详细参数（model、temperature、timeout、max_tokens 等）通过 `module_{标识}` 命名约定在 `llm_settings.json` 中配置。

**辩论模式路由**：当 Feature Flag 开启时，expert_review 模块的生成入口被 `_debate_wrapper` 接管，输出路径变为 debate 三段式。辩论模式使用独立的缓存键（`llm_debate_pro_`/`llm_debate_con_`/`llm_debate_synthesis_`）和 Token 预算守卫，三段缓存共用 expert_review 的持仓指纹（排除行情波动），默认 TTL 24h。辩论模式启用时报告页签标题尾部附加"(实验)"标签。

各模块的详细配置参数、System Prompt 设计、User Prompt 构建逻辑见 `llm-technical.md` §8（提示词管理）。辩论模式详见 `llm-technical.md` §4.1 和 §5.5。

### 5.4 多 Provider 链模式

LLM API 调用支持多 Provider 链式容错，与数据获取层的 Provider Chain（§2.1）采用相同设计理念，但策略引擎独立：

- **配置分离**：Provider 路由配置在 `llm_providers.json`，敏感凭据通过 `credentials_ref` 引用 `llm_key.json` 中的凭据块
- **策略引擎**：`strategy.py` 支持 4 种链切换策略 — priority（优先级排序）、weighted（加权随机）、cost_first（成本优先）、fallback_only（仅递补）
- **逐链尝试**：`api.call_provider_entry()` 按策略排序后逐链调用，成功即返回，全链失败后降级为占位文本
- **Provider 感知缓存**：缓存键格式 `llm_{module}_{provider_name}_{fingerprint}`，不同 Provider 的缓存互不冲突
- **失败追踪**：`LLM_MODULE_FAILURE` 字典记录每个模块的 attempted Provider 列表及 final_status，供报告展示

4 种策略的详细排序逻辑和 credentials_ref 解析流程见 `llm-technical.md` §5（API 调用层）。

### 5.5 关键机制

| 机制 | 实现 | 说明 |
|:-----|:------|:------|
| Extended Thinking | Claude: `thinking.budget_tokens`；DeepSeek: `output_config.effort` | 与 `temperature` 互斥 |
| Prompt Caching | Anthropic 专属，system prompt 数组 + `cache_control: ephemeral` | 5 分钟内复用免全价 |
| 截断重试 | 检测 `TRUNCATION_MARKER` 后自动 1.5× max_tokens 重试一次 | 修复内容被截断的情况 |
| 内容过滤安抚 | 空返回时追加安抚指令重试 | 应对内容审查误杀 |
| 会话用量追踪 | `session.py` 维护线程安全 `session_usage` 字典 + `cost_tracker.py` 报告级预算管理 | 按模块粒度追踪 token/费用/缓存命中/耗时 |
| Token 预算告警 | `cost_tracker.check_input_budget()` — 累计输入 Token 超 8K 时日志告警（不截断） | 为模型分层提供基线数据 |
| 调用耗时记录 | `skeleton.py` `time.monotonic()` 计时 → `record_per_module(duration=)` → HTML 页脚展示 | 每次 call_llm() 记录实际耗时 |
| LLM 熔断 | `llm/circuit_breaker.py` — 连续 N 次失败 → 60s 冷却 → 半开状态试探 | 防止无效调用浪费 token |
| 指纹缓存 | `fingerprint.py` — 依赖数据指纹过滤（排除行情波动字段） | 仅品种/份额/成本变化时重新调用 |
| 乐观缓存预检 | 从 Provider 链中取链首 Provider 优先检查缓存，命中即返回 | 减少链遍历开销 |
| 辩论路由 | `_debate_wrapper` 闭包替换 `_MODULE_FNS["expert_review"]`，Feature Flag 控制启停（默认关闭） | 辩论模式与标准模式互斥，辩论优先 |
| Token 预算守卫 | 每阶段输出字符数 > `int(max_tokens × 0.65)` 时触发保护：1× 超限→跳过 synthesis 阶段并拼接 pro+con；2× 超限→回退标准模式 | 防止辩论模式过度消耗 token |
| 虚构代码过滤 | `_filter_hallucinated_codes()` 基于正则的行级过滤，使用 `(?:^\|[^A-Za-z0-9])([A-Za-z0-9]{4,6})(?=[^A-Za-z0-9]\|$)` 适配中文环境 | 消除 LLM 产生的虚构证券代码 |

各项机制的详细实现见 `llm-technical.md` §5~§11（API 调用层、重试与容错、缓存与指纹失效、提示词管理、会话级 Token 追踪、模型定价、熔断器）。

[↑ 回到顶部](#目录)

---

## 6. 辅助模块详细设计

### 6.1 配置管理

#### 配置分层

```
config.json (基础配置)       → get_config() 内存缓存，按 mtime 自动失效
llm_settings.json (非敏感)    → get_llm_config() 合并读取，联合 mtime 失效
llm_key.json (敏感凭据)       → 覆盖 llm_settings.json 的同名字段；多凭据块供 credentials_ref 引用
llm_providers.json (链配置)   → _load_llm_providers() 读取，$inject_provider_chain_data 注入
```

`config/` 子包结构：

```
config/
├── __init__.py                   # 公开 API 导出
├── _comments.py                  # JSON 注释剥离（_strip_json_comments）
├── _config_defaults.py           # config.json 默认值定义 + 模板生成
├── _core.py                      # 核心读写：get_config()、set_config()、init_config()
├── _validation.py                # 配置校验：validate_config()、_absolutize_paths()
├── _llm_defaults.py              # llm_settings.json 默认模板生成
└── _llm_providers_defaults.py    # llm_providers.json 默认模板生成
```

#### JSON 注释支持

`_strip_json_comments()` 逐字符扫描，支持 `//` 单行注释和 `/* */` 多行注释，正确处理字符串内的转义引号，不会将字符串内的 `//` / `/*` 误伤。

#### 原子写入

配置文件（`set_config`）和缓存写入（`_write_atomic`）均使用 `tempfile.mkstemp` + `os.replace` 模式。

### 6.2 中央注册表

**设计目标**：消除 `config.py` / `cache.py` / `constants.py` 三处分散维护的遗漏风险，做到"一处注册，全局生效"。

#### DataModuleDef 条目结构

```python
@dataclass(frozen=True)
class DataModuleDef:
    name: str                # 人类可读名称
    data_type: str           # 数据类型键，用于 TTL 查找和路由
    cache_prefixes: tuple    # 缓存前缀，如 ("price_",)
    exact_cache_keys: tuple  # 精确缓存键名
    cache_ttl: float         # 默认缓存过期时间（秒）
    settings_suffix: str|None# LLM settings 键后缀，None=非 LLM 模块
    cache_groups: tuple      # 分组
```

当前注册 **29 个数据模块**：

| 分类 | 数量 | 模块 |
|:-----|:----:|:-----|
| 基础行情（preload） | 2 | price、index |
| 基金数据（refresh） | 2 | rank、hold |
| 行业 | 1 | industry |
| 新闻（refresh） | 1 | news |
| LLM 分析（preload/refresh） | 5 | global_macro、expert_review、news_correlation、health_check、penetration_deep |
| 辩论缓存（preload，实验） | 3 | llm_debate_pro、llm_debate_con、llm_debate_synthesis |
| 补充数据（refresh） | 3 | profit_forecast、sector_flow、dividend |
| 基金深度分析（refresh/无分组） | 5 | fund_manager、fund_overlap、fund_concentration、fund_style_snapshot、**extended** |
| 无风险利率（refresh） | 1 | **bond_yield** |
| 精确键名（refresh/无分组） | 3 | benchmark、tracking、calendar |
| 历史走势（无分组） | 3 | history_stock、history_fund_otc、history_index |

#### 计算模块注册表（`_COMPUTATION_REGISTRY`）

除数据模块注册外，系统维护独立的计算模块注册表 `_COMPUTATION_REGISTRY`，记录所有分析/指标计算模块的元信息。

```python
@dataclass(frozen=True)
class ComputModuleDef:
    name: str           # 中文名称
    module_key: str     # 键名（如 "analytics_metrics"）
    label: str          # 短标签
    dependencies: tuple # 前置数据依赖
    description: str    # 功能说明
    status: str         # planned / implemented
```

当前注册 7 个计算模块：

| module_key | name | 状态 | 说明 |
|:-----------|:-----|:----:|:-----|
| `analytics_metrics` | 量化指标计算 | ✅ | 夏普比率、卡玛比率、HHI 集中度、组合 Beta、持仓胜率、换手率、波动率、最大回撤 |
| `analytics_liquidity` | 流动性分析 | ✅ | 场内/场外比例、停牌风险、基金封闭期分析 |
| `analytics_fx_exposure` | 外汇敞口分析 | ✅ | A股/港股/美股 国别分布与外汇风险敞口判断 |
| `analytics_fact_checker` | 事实锚定校验器 | ✅ | LLM 输出的事实校验：数值一致性、品种存在性、排名正确性（纯算法层） |
| `analytics_scenario` | 情景分析 | ✅ | 市场涨跌情景模拟、3 情景表、置信区间传播 |
| `analytics_alignment` | 组合校准分析 | ✅ | 费率估算/现金剥离/TWR 计算 |
| `analytics_inferrer` | 用户画像推断 | ⏳ | 持仓结构→风险偏好推断 |

计算模块与报表层保持单向依赖，禁止反向导入 report/。

#### 派生产出接口

| 接口 | 用途 |
|:-----|:------|
| `get_cache_ttl_defaults()` | data_type → TTL 默认值 |
| `get_prefix_type_map()` | 缓存前缀 → data_type |
| `get_exact_type_map()` | 精确键名 → data_type |
| `get_known_llm_settings_keys()` | `llm_settings.json` 合法键名 |
| `get_report_section_order()` | 用户配置+默认顺序合并 |
| `get_llm_module_names()` | suffix → 中文名称 |

### 6.3 市场时段判断

**三层 fallback 架构**（`market_hours.py`）：

```
is_market_open()
    │
    ▼
┌─────────────────────────────────────────────┐
│ 第 1 层：config.json 手动覆盖                 │
│ market_hours.start / end                    │
│ 支持午间不中断模式（连续时段）                  │
├─────────────────────────────────────────────┤
│ 成功? → 返回 True/False                      │
│ 未配置? → 进入下一层                          │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ 第 2 层：东方财富 push2 API 实时交易状态      │
│ 上证指数 secid=1.000001, f100 字段          │
│   0=未开盘 / 1=交易中 / 2=收盘 / 3=午间休市   │
│ 缓存策略：盘中 60s，盘后 7 天                 │
├─────────────────────────────────────────────┤
│ 成功? → 返回 True/False                      │
│ API 不可用? → 进入下一层                      │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ 第 3 层：内置默认值                           │
│ 北京时区工作日 09:30-11:30 + 13:00-15:00     │
├─────────────────────────────────────────────┤
│ 固定返回 True/False                          │
└─────────────────────────────────────────────┘
```

**时区安全**：所有 `datetime.now()` 调用均使用 `timezone(timedelta(hours=8))` 北京时区，防止 UTC 服务器上时段判断全错。异常时保守返回 `False`。

**消费方**：
- `cache/_ttl.py:get_ttl()` — 交易时段内 `market_hour_aware` 类型自动使用短 TTL（30s）
- `report/market_value.py:is_market_open()` — 取价方式标签判断
- `report/market_value.py:is_midday_break()` — 午间休市识别（11:30-13:00）

### 6.4 持仓读取与列校验

基于 openpyxl 解析持仓 xlsx（`reader.py`）：

```
load_holdings(filepath)
    │ 遍历所有 worksheet
    │ 每个 worksheet = 一个账户
    ▼
列校验规则：
    必须存在且恰好 4 列
    列名匹配忽略首尾空格
    列顺序：名称、代码、持仓份额、每份成本
    │
    ▼
数据清洗：
    代码自动去除后缀（.SH / .SZ / .OF）
    份额/成本转为 float
    空行跳过
    │
    ▼
返回：list[Holding]（每行一个 Holding）
```

### 6.5 代码类型判定中心化

所有资产代码类型判定集中到 `src/python/code_utils.py`，以纯技术原语形式提供。

#### 原语清单

| 维度 | 函数 | 判定依据 | 用途 |
|:-----|:------|:---------|:------|
| 代码前缀 | `is_a_share_code(code)` | 60/68/00/30/8 开头 | A 股股票识别 |
| | `is_exchange_fund_code(code)` | 5/1 开头 | 场内基金/ETF |
| | `is_hk_stock_code(code)` | 5 位纯数字 | 港股通标的 |
| | `is_otc_code_overlap(code)` | 00 开头 | A 股/OTC 基金代码重叠区检测 |
| | `get_exchange_prefix(code)` | 前缀规则 | sh/sz/bj 交易所前缀 |
| | `is_index_code(code)` | sh/sz 前缀或 000/399/932 开头或 gb_ 前缀 | 指数代码识别 |
| | `is_us_index_code(code)` | gb_ 前缀 | 美股指数识别 |
| | `get_index_exchange_prefix(code)` | sh/sz 前缀 | 指数所属交易所前缀 |
| | `get_push2_secid(code)` | 前缀规则 | push2 API secid 参数 |
| 名称关键词 | `is_qdii_by_name(name)` | "QDII" | QDII 标识 |
| | `is_qdii_extended(name)` | QDII + 隐式关键词 | QDII + 隐式海外基金 |
| | `is_etf_by_name(name)` | "ETF" | ETF 标识 |
| | `is_bond_related_by_name(name)` | 纯债/短债/利率债等（不含单字"债"） | 债券基金（严格） |
| | `is_bond_fund_by_name(name)` | 含"债" | 债券基金（宽松，含可转债） |
| | `is_money_fund_by_name(name)` | 货币/现金/增利/宝 | 货币基金 |
| | `is_index_fund_by_name(name)` | 指数/ETF 联接/中证/沪深 300 等 | 场外指数基金 |
| | `is_index_link_by_name(name)` | ETF 联接/联接/链接 | 指数联接基金 |
| 复合 | `is_etf_by_name_or_code(name, code)` | 名称+代码双维度 | ETF 增强识别 |
| | `is_otc_fund_by_name(name, code)` | 00 代码+名称含基金关键词 | 00 代码重叠区→场外基金 |
| | `is_offsite_fund(account)` | 关键词匹配 | 场外基金账户 |
| | `is_fund_holding(name, code, account)` | 三者联合 | 持仓是否需要基金业绩分析 |

#### 内部工具

`_strip_prefix(code)` — 去除 `sh/sz/bj` 前缀，返回纯净 6 位数字代码，非 6 位数字时返回空字符串。所有前缀型判定函数均先调用此函数再匹配。

#### 关键词常量

| 常量名 | 值 | 用途 |
|:-------|:----|:------|
| `FUND_ACCOUNT_KEYWORDS` | `("基金", "支付宝", "微信", "银行")` | 场外基金账户判定 |
| `MONEY_KEYWORDS` | `("货币", "现金", "增利", "宝")` | 货币基金识别 |
| `INDEX_KEYWORDS` | `("指数", "ETF联接", "中证", "沪深300", ...)` | 指数基金判定 |

### 6.6 HTTP 客户端统一

所有 HTTP 请求必须使用 `http_client.py` 工厂方法创建客户端实例（C5 约束），统一 SSL 配置、超时策略、连接池管理。

```python
make_http_client(timeout=10.0) → httpx.Client
```

默认超时 10s，支持 per-call 覆盖，所有 provider 模块统一使用此接口。

[↑ 回到顶部](#目录)

---

## 7. 模块间依赖关系

```
reader.py (持仓解析)
  → models.py (Holding/DetailRow 数据模型)
  → fetcher/price.py (价格获取)
  → fetcher/index.py (指数获取)
  → fetcher/fund.py (基金数据获取)
  → fetcher/industry.py (行业分类)
  → providers/* (各数据源 API 实现)
  → cache/ (缓存读写)
    → market_hours.py (交易时段感知 TTL)
    → registry.py (TTL 默认值、缓存分组)

cache/operations.py (缓存操作共享层)
  → cache/ (缓存引擎核心)
  → providers/akshare_extras.py (盈利预测/资金流向/分红)
  → fetcher/industry.py (行业分类)
  → fetcher/fund_manager.py (基金经理)
  → fetcher/fund.py (基金业绩)
  → fetcher/price.py / index.py (持仓缓存)

report/orchestrator.py (报告编排层)
  → report/market_value.py (行情获取)
  → fetcher/index.py (指数)
  → report/penetration.py (资产穿透)
  → report/history_snapshot.py (F1 快照)
  → report/portfolio_history.py (F2 历史走势)
  → report/news_correlation.py (新闻关联)
  → llm/generators_orchestrator.py (LLM 编排)
  → report/html_writer.py (HTML 管线)
  → report/excel_generator.py (Excel 管线)
  → config/ (开关配置)
  → registry.py (报告模块注册)

report/excel_generator.py (Excel 编排器)
  → report/excel_module_loader.py (模块动态加载)
  → report/excel_sheet_factory.py (页签创建/可见性)
  → report/*.py (各页签写入器)
  → report/excel_writer.py + styles.py
  → report/data_status.py (降级状态)

report/html_writer.py (HTML 编排器)
  → report/html_builders.py (数据构建器)
  → report/html_renderers.py (Markdown→HTML)
  → report/html_jinja_env.py (Jinja2 环境)
  → report/html_save.py (文件写入)
  → tmpl/report_template.html (Jinja2 模板)
  → report/data_status.py

llm/ (LLM 集成)
  → llm/generators_orchestrator.py → skeleton.py → api.py → api_base.py
  → llm/prompts.py / fingerprint.py / pricing.py / session.py
  → cache/ (LLM 结果缓存)

handlers_*.py (TUI 命令)
  → orchestrator.py 或 cache/operations.py (委托业务逻辑)
  → report/progress.py (TuiProgressReporter)

config/ → registry.py
code_utils.py → 各 fetcher/report/llm 模块（跨层依赖，无环）
```

[↑ 回到顶部](#目录)

---

## 8. 架构设计约束

本节定义系统架构层面的**设计约束**。所有新增或修改的代码必须遵守，违反即视为架构违规。
约束按职责域分组，每个约束包含：设计目的（为何存在）、违反后果（不遵守的影响）、适用范围（哪些模块/场景受约束）。

### 8.1 数据获取层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C1** | **代码类型判定中心化** — 所有资产代码类型判定必须使用 `code_utils.py` 提供的函数，禁止任何模块自行实现判定逻辑 | 系统 20+ 处需要判断资产类型（A 股/ETF/基金/QDII/港股/债券等），分散判定导致代码前缀知识散落，"魔法判定"遍地，新增资产类型时需全局搜索替换 | 代码评审不通过；新增资产类型时遗漏大量散落判定点 | 所有涉及代码类型判定的模块（fetcher/、report/、llm/ 等） |
| **C4** | **会话级 API 复用** — 同次会话内同一 API 返回的数据必须通过 `DataSourceRegistry.session_cache` 复用，禁止重复 HTTP 请求 | 避免同一资产在多个模块中重复请求相同 API 数据，降低 API 限频风险，提升性能 | API 调用量膨胀、触发限频、报告生成时间增长 | 所有通过 Provider 获取数据的模块 |
| **C5** | **HTTP 客户端统一** — 所有 HTTP 请求必须使用 `http_client.py` 工厂方法创建客户端实例 | 统一 SSL 配置、超时策略、连接池管理；防止各模块自行构造 request 导致配置散落、连接池泄漏 | SSL 配置不一致、连接泄漏、重试策略不统一 | 所有发起 HTTP 请求的模块（providers/、llm/） |
| **C6** | **Provider Chain 必经** — 大多数数据获取必须通过 `fetch_with_fallback()` 走 Chain 路由，不得直接调用 Provider 函数 | 跳过 Chain 直接调用 Provider 会导致熔断器不被激活（故障后无冷却恢复）、fallback 链路断路（某 Provider 失败时不会自动递补）、日志审计缺失 | 熔断器失效、fallback 断路、故障记录缺失 | fetcher/ 各模块（例外：index.py 直调 Provider 的双链路 fallback 硬编码，熔断器不适用于指数场景） |

### 8.2 缓存层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C2** | **缓存统一管理** — 所有持久化缓存必须通过 `cache/` 子包的 `get()`/`set()` 接口读写，禁止直接操作 `data/cache/` 文件系统 | 直接操作文件系统导致 TTL 失效（缓存无法感知过期时间）、分组清理遗漏（菜单命令无法清除对应缓存）、路径穿越隐患 | 缓存不一致、TTL 失效、分组清理遗漏、路径安全风险 | 所有读写 data/cache/ 的模块 |
| **C3** | **缓存原子写入** — 所有缓存/配置文件写入必须使用 `tempfile.mkstemp` + `os.replace` 原子写入模式 | 直接覆写文件在断电/崩溃时产生半写损坏文件，导致后续读取解析失败 | 半写文件损坏、数据不完整、崩溃后无法自恢复 | cache/ 子包、config/ 子包、history_snapshot.py |

### 8.3 报告层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C7** | **报告序号不可硬编码** — 报告 18 个模块的序号和显示名称必须通过 `registry.py` 的 `_REPORT_SECTION_DEFAULT` 注册表驱动，支持 `config.json` 自定义覆盖 | 硬编码序号使得用户无法通过配置调整报告章节顺序，且新增/删除模块时需要全局修改序号 | 序号配置失效、用户自定义顺序不生效 | report/ 编排器（excel_generator.py、html_writer.py） |
| **C10** | **新闻召回策略可配置** — `per_source` 每源获取数量必须与 `news_top_count` 最终截取数量解耦，`per_source` 动态计算为 `max(500, news_top_count × 2)`，不可写死 | 固定值会导致去重后候选新闻不足，最终截取数不满足用户配置 | 新闻候选不足、用户配置不生效 | `providers/news_aggregator.py` |
| **C14** | **渲染期数据不可写入模块级全局变量** — 所有渲染期数据（如 `section_visible_dict`）必须通过模板 `render()` 的 context 参数传递，不得写入 `_ENV.globals` 或模块级 dict | 模块级全局变量在并发/多次渲染场景下产生状态污染，且难以追踪数据流向 | 并发不安全、渲染状态污染、数据流向不可追踪 | report/html_writer.py、模板渲染相关模块 |
| **C19** | **pipeline_data Schema 契约** — 所有 pipeline_data 键必须先在 pipeline_data Schema 定义文档中预定义类型、版本号、写入/消费模块后，才能在代码中使用该键（详见附录 H） | 无 schema 定义的键在管线中类型不匹配时引发难调试的 KeyError，且多人并行开发时互相不知道对方新增的键 | 违反时集成测试不通过 | report/orchestrator.py、所有向 pipeline_data 注入数据的模块 |

### 8.4 LLM 集成层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C9** | **LLM 模块注册** — 新增 LLM 分析模块时，必须在 `generators_orchestrator.py` 的 `_MODULE_FNS` 字典和 `registry.py` 的 `DataModuleDef` 注册表中同时注册（详见 `llm-technical.md` §12） | 仅在 orchestrator 注册会导致缓存/TTL/统计遗漏；仅在 registry 注册会导致编排调度遗漏 | LLM 调度遗漏、缓存 TTL 未定义、用量统计缺失 | llm/ 包 + registry.py |
| **C17** | **Multi-LLM Provider Chain** — 所有 LLM API 调用必须通过 Provider Chain（`strategy.py` + `api.py`）路由，`call_llm()` 返回 `(result, usage, provider_name)` 三元组，provider_name 记录实际使用的 Provider 条目名（详见 `llm-technical.md` §5.2） | 手动切换 Provider 导致配置散落、失败无法递补、Provider 名称不可追踪 | API 调用不经过 Chain → 无法自动递补、Provider 名称缺失 → 缓存键冲突、用量统计不准确 | llm/api.py、llm/skeleton.py、llm/strategy.py |
| **C18** | **credentials_ref 凭据分离** — API 凭据（api_key/model/endpoint）必须通过 `llm_key.json` 的 `credentials_ref` 引用，禁止在 `llm_providers.json` 中直接存储敏感凭据（详见 `llm-technical.md` §5.3） | 凭据与路由配置混存导致凭据泄露风险；凭据变更时需同时修改两份配置 | 凭据泄露风险、凭据变更需多处修改、凭据复用困难 | data/config/llm_providers.json、data/config/llm_key.json、config/_core.py、llm/api.py |

### 8.5 基础设施约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C8** | **日志统一** — 所有模块必须使用 `logging.getLogger("invest")` 获取日志器，禁止直接使用 `print()` 输出运行时诊断信息 | 统一日志名称使日志过滤、级别控制、格式管理集中生效；`print()` 无法控制日志级别，污染 stdout | 日志碎片化、日志级别失控、`print()` 干扰输出流 | 全模块（交互式 print 如进度提示不受此限） |
| **C15** | **控制台日志着色** — WARNING 级别使用黄色输出、ERROR 级别使用红色输出；当 `NO_COLOR` 环境变量设置或输出非 TTY 时自动降级为无颜色 | 着色提升控制台日志的辨识度，便于快速定位告警和错误；降级保证日志导出、管道重定向时无转义字符污染输出 | 日志可读性降低、非 TTY 环境下转义字符污染 | `logger.py`（_ColoredFormatter） |
| **C16** | **路径绝对化** — 配置层输出的路径型键（`holdings_dir`、`output_dir`、`llm_key_file`、`llm_providers_file`、`llm_settings_file`）必须为绝对路径，在 `get_config()` 返回前经 `_absolutize_paths()` 统一转换；下游消费者不得依赖 CWD | `tui.py`/`cli.py` 去掉了 `os.chdir`，相对路径无法被正确解析 | 路径查找失败、配置文件/持仓文件/报告输出找不到 | `config/_core.py`（转换点），所有消费路径型配置的模块 |

### 8.6 测试约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C11** | **测试标记强制** — 新增/修改的测试用例（测试类或测试方法）必须标注对应的 pytest marker（如 `@pytest.mark.unit_providers`），marker 定义在 `src/test/conftest.py` 的 `pytest_configure` 中 | 未标记的测试用例无法被分层测试命令精确选择，也无法纳入回归/验证门禁范围 | CI 门禁不通过、测试分类失效 | src/test/ 所有测试文件 |
| **C12** | **边缘测试文件隔离** — `@pytest.mark.edge` 标记的测试用例必须放置在 `*_edge.py` 文件中，不得与普通测试混放在同一文件 | edge 场景测试对运行环境有特殊要求（预期失败、网络不可达等），混放会导致普通测试运行被 edge 场景的 fixture 干扰 | 测试收集失败、`pytest_collection_modifyitems` 校验报错 | src/test/ 边缘测试文件 |
| **C13** | **测试敏感路径隔离** — 运行测试时不得修改用户的配置文件（`data/config/`）、持仓文件（`data/holdings/`）等敏感数据；`conftest.py` 的 `_isolate_sensitive_paths` autouse fixture 会自动将 `config.json` 和缓存目录重定向到临时目录 | 测试污染用户数据导致不可逆的配置丢失或持仓文件损坏 | 用户数据被污染、配置丢失 | src/test/ 所有测试用例 |

[↑ 回到顶部](#目录)

---

## 附录

### 附录 A：目录结构

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── python/                   # 源代码
│   │   ├── __init__.py
│   │   ├── analysis/            # 业务分析计算层（再平衡、量化指标）
│   │   ├── anonymizer.py        # 持仓匿名化（名称替换/数量模糊/关闭三模式）
│   │   ├── ansi_colors.py       # ANSI 颜色常量（终端输出着色）
│   │   ├── cache/               # 缓存引擎子包（8 子模块 + operations + services）
│   │   ├── circuit_breaker.py   # 统一断路器网关（Provider + LLM 熔断状态查询）
│   │   ├── cli.py               # CLI 命令行入口（argparse + 共享层直调）
│   │   ├── code_utils.py        # 代码类型判定中心化
│   │   ├── config/              # 配置管理子包（_config_defaults / _comments / _core）
│   │   ├── constants.py         # 共享常量 + 项目根路径（标记文件查找法）
│   │   ├── features.py          # 功能开关注册表（28 项 Feature Flag）
│   │   ├── fetcher/             # 数据获取调度（price/index/fund/fund_manager/industry/chain/akshare/bond_yield/news/history_diff）
│   │   ├── handlers_cache.py    # TUI 缓存管理命令（薄壳委托 operations）
│   │   ├── handlers_check_sources.py # 数据源健康检查命令处理器
│   │   ├── handlers_config.py   # TUI 配置管理命令
│   │   ├── handlers_report.py   # TUI 报告生成命令（薄壳委托 orchestrator）
│   │   ├── http_client.py       # HTTP 客户端工厂
│   │   ├── llm/                 # LLM 集成（编排/骨架/API 路由/提示词/指纹/熔断器等）
│   │   ├── logger.py            # 日志模块（_ColoredFormatter）
│   │   ├── market_hours.py      # A 股交易时段判断
│   │   ├── perf.py               # 性能收集（PerfCollector 计时 + perf_history.jsonl）
│   │   ├── models.py            # 数据模型
│   │   ├── provider_registry.py # 数据源注册中心 — 熔断/缓存/策略/审计
│   │   ├── providers/           # 数据源提供商（各 API 封装）
│   │   ├── reader.py            # 持仓 Excel 解析
│   │   ├── registry.py          # 中央注册表（29 个数据模块 + 18 个报告模块 + 7 个计算模块）
│   │   ├── report/              # 报告生成（编排器/进度/管线/数据构建器/页签写入器）
│   │   ├── schemas/             # Pydantic 数据模式（快照等）
│   │   ├── tui.py               # TUI 入口 + 菜单循环
│   │   ├── tui_handlers.py      # 菜单通用辅助
│   │   ├── tui_keys.py          # 键盘输入封装
│   │   └── tui_menu.py          # 菜单交互
│   └── test/                    # 测试（按标记分组）
│       ├── conftest.py          # pytest 配置 + 分层标记注册
│       ├── helpers.py           # 测试辅助工具
│       ├── unit/                # 单元测试
│       ├── integration/         # 集成测试
│       └── scenario/            # 场景测试
├── data/                        # 运行时数据（config/holdings/cache/state/snapshots）
├── reports/                     # 生成报告
├── logs/                        # 程序日志
├── docs-stm/                    # 项目管理文档（含 managements/、plan/、manuals/）
├── scripts/                     # 启动/测试脚本
├── pyproject.toml
└── CLAUDE.md
```

### 附录 B：数据源一览

| 用途 | 链路方案 | Provider 文件 |
|:-----|:---------|:-------------|
| 场内 A 股/ETF 实时价 | 腾讯财经 → 新浪财经（双链路 fallback） | `tencent.py` / `sina.py` |
| 场外基金净值 | 东方财富（直达，无备用） | `eastmoney.py` |
| 基金业绩排名 | 天天基金 JS 变量解析（直达） | `tiantian_ranking.py` |
| 基金持仓数据 | 天天基金 HTML 解析（直达） | `tiantian_holdings.py` |
| A 股指数 | 腾讯财经 → 新浪财经（双链路 fallback） | `tencent.py` / `sina.py` |
| 美股指数 | 新浪财经 → 腾讯财经（双链路 fallback） | `sina.py` |
| 财经新闻 | 5 源并行：新浪/东方财富/财联社/华尔街见闻/akshare | 各 `*_news.py` |
| 行业分类/概念板块 | 东方财富 push2（主）→ quotedata 回退 | `eastmoney_industry.py` / `eastmoney_industry_rest.py` |
| 机构盈利预测 | akshare 全量获取（直达） | `fetcher/akshare.py`（封装 `akshare_extras.py`） |
| 行业资金流向 | akshare 今日排名（直达） | `fetcher/akshare.py`（封装 `akshare_extras.py`） |
| 股票历史分红 | akshare 逐股获取（直达） | `fetcher/akshare.py`（封装 `akshare_extras.py`） |
| 基金经理数据 | 天天基金 HTML 解析（主）→ 档案页回退 | `fetcher/fund_manager.py` |
| 无风险利率（Rf） | akshare `bond_zh_us_rate`（Sina 国债收益率）→ 手动配置兜底 | `fetcher/bond_yield.py` |

新闻数据处理模块：`news_aggregator.py`（聚合去重）、`news_correlator.py`（关联分析）、`news_keywords.py`（关键词提取）、`news_sources.py`（源元数据定义），均位于 `providers/` 下。

### 附录 C：缓存 TTL 明细

#### 行情/数据类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `price` | `price_{code}.json` | 24h | 交易时段 30s | — | preload |
| `index` | `index_{code}.json` | 24h | 交易时段 30s | — | preload |
| `news` | `news_{md5}.json` | 15 分钟 | — | 新闻源参数+关键词 | refresh |
| `sector_flow` | `sector_flow_{fingerprint}.json` | 15 分钟 | — | A 股+美股指数 | refresh |
| `rank` | `fund_perf_{code}.json` | 24h | — | — | refresh |
| `profit_forecast` | `profit_forecast_{fingerprint}.json` | 24h | — | A 股+美股指数 | refresh |
| `hold` | `fund_hold_{code}.json` | 7 天 | — | — | refresh |
| `industry` | `industry_{code}.json` | 14 天 | — | — | refresh |
| `dividend` | `dividend_{fingerprint}.json` | 30 天 | — | 持仓+穿透 A 股代码 | refresh |
| `benchmark` | `fund_benchmarks.json` | 30 天 | — | — | refresh |

#### LLM 分析类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `llm_expert_review` | `llm_expert_review_{fingerprint}.json` | 2h | — | 持仓汇总+分类+穿透+明细 | preload |
| `llm_debate_pro` | `llm_debate_pro_{fingerprint}.json` | 24h | — | 复用 expert_review 持仓指纹（排除行情波动） | preload |
| `llm_debate_con` | `llm_debate_con_{fingerprint}.json` | 24h | — | 复用 expert_review 持仓指纹（排除行情波动） | preload |
| `llm_debate_synthesis` | `llm_debate_synthesis_{fingerprint}.json` | 24h | — | 复用 expert_review 持仓指纹（排除行情波动） | preload |
| `llm_news_correlation` | `llm_news_item_{hash}.json`（逐条） | 1h | — | 标题前 80 字+持仓指纹 | refresh |
| `llm_global_macro` | `llm_global_macro_{fingerprint}.json` | 24h | — | A 股/美股指数+持仓汇总 | preload |
| `llm_health_check` | `llm_health_check_{fingerprint}.json` | 24h | — | 持仓明细（排除行情波动） | preload |
| `llm_penetration_deep` | `llm_penetration_deep_{fingerprint}.json` | 24h | — | 持仓明细（排除行情波动） | preload |

#### 基金深度分析类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `fund_manager` | `fund_manager_{code}.json` + `fund_manager_snapshot.json` | 24h | — | — | refresh |
| `fund_overlap` | 实时计算（推导自 `fund_hold_{code}.json`） | 7 天 | — | — | refresh |
| `fund_concentration` | `fund_concentration_snapshot.json` | 月级快照 | — | — | 无分组 |
| `fund_style_snapshot` | `fund_style_snapshot.json` | 月级快照 | — | — | 无分组 |
| `extended` | `extended_{code}.json` | 24h | — | — | refresh |

#### 历史走势类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `history_stock` | `history_stock_{code}.json` | 7 天 | — | — | 无分组 |
| `history_fund_otc` | `history_fund_otc_{code}.json` | 30 天 | — | — | 无分组 |
| `history_index` | `history_index_{code}.json` | 30 天 | — | — | 无分组 |

#### 系统类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `tracking` | `holdings_tracking.json` | 30 天 | — | — | 无分组 |
| `calendar` | `trading_calendar.json` | 14 天 | — | — | 无分组 |
| `bond_yield` | `bond_yield_rf`（精确键名） | 1 天 | — | — | refresh |

> `—` 表示精确键名（无指纹后缀），TTL 到期后刷新。

### 附录 D：降级层级与阈值定义

| 层级 | 含义 | 显示前缀 | 连续失败阈值 | 缓存陈旧阈值 |
|:-----|:------|:---------|:------------|:------------|
| T2 | 数据不可用 | ⚠ | 2 次 | 3 天 |
| T3 | 数据部分可用 | ℹ | 2 次 | 14 天 |
| T4 | 数据临时不可用 | ℹ | 1 次 | 7 天 |

降级配置位于 `config.json` 的 `degradation` 字段，支持 per-source 覆盖。

### 附录 E：线程池分布

| 池名称 | 所在模块 | max_workers | 线程名前缀 | 用途 |
|:-------|:---------|:-----------|:----------|:------|
| `orch_prep` | `report/orchestrator.py`（`prepare_report_data`） | 2 | `orch_prep` | 并行获取 A 股/美股指数 |
| `orch_llm_news` | `report/orchestrator.py`（`_fetch_llm_and_news`） | 2 | `orch_llm_news` | 并行获取 LLM + 新闻 |
| `cache_ops` | `cache/operations.py` | 4 | `cache_ops` | 并行刷新基金/行业/公共缓存 |

各线程池互不共享，职责隔离。

### 附录 F：指标降级依赖矩阵

| 指标 | 依赖数据 | K 线完全不可用 | K 线部分缺失 | 说明 |
|:-----|:---------|:--------------|:-----------|:------|
| 夏普比率 | Rf + 组合日收益率 + 波动率 | None（显示 --） | 置信度降为 low | 依赖 Rf 获取器 |
| 卡玛比率 | 组合日收益率 + 最大回撤 | None（显示 --） | 置信度降为 low | — |
| HHI | 持仓权重（不依赖行情） | 正常计算 | 正常计算 | 仅需权重数据 |
| 胜率 | 盈亏品种数（不依赖行情） | 正常计算 | 正常计算 | 仅需盈亏数据 |
| 换手率 | 期间变动金额 + 均值市值（不依赖 K 线） | 正常计算 | 正常计算 | 期间变动数据仅快照支持 |
| 风险贡献 | 品种波动率 + 权重 | 仅权重等比例分配 | 部分品种用等比例替代 | 简化版非 Euler 分解 |
| Beta | 组合日收益率 + 基准日收益率 | None（显示 --） | 置信度降为 low | 252 日窗口 |
| 回撤分位(1年) | 组合日收益率（约 250 交易日） | None（显示 --） | 数据不足 60 日则不计算 | — |
| 回撤分位(全历史) | 组合日收益率 | None（显示 --） | 数据不足 60 日则不计算 | 1 年/3 年/全历史三档 |

> K 线数据通过腾讯/新浪 API 获取，两者均为已知不可靠来源。熔断时降级行为由 DegradationTracker 记录并传递至 pipeline_data['data_degradation']，LLM prompt 据此展示"部分指标因行情数据不全暂时无法计算"。

### 附录 G：报告生成降级路径矩阵

| 故障场景 | basic 路径 | both 路径 | full 路径 | LLM 分析章节 |
|:---------|:----------|:---------|:---------|:---------|
| 行情数据全熔断 | 显示 -- | 生成但注明行情缺失 | 生成但注明行情缺失 | LLM 跳过行情相关部分 |
| 概念数据熔断 | N/A | N/A | 概念板块段落显示占位文本 | 引用 DegradationTracker |
| Rf 数据不可用 | N/A | N/A | 夏普等 Rf 依赖指标显示 -- | 注明'无风险利率数据不可用' |
| LLM API 全部不可用 | 正常 | 正常（无 LLM） | 自动降级为 both 路径 | 显示'智能分析暂时不可用' |
| 单一 LLM 模块失败 | 正常 | 正常 | 仅该模块显示占位文本 | 其余 LLM 模块正常 |
| 多源并发故障 | 正常 | 生成但注明大面积降级 | 生成但注明大面积降级 | 所有不可用数据源标注降级 |
| 文件系统写失败 | 报告生成失败 | 报告生成失败 | 报告生成失败 | — |

> 基本原则：任何数据获取失败均不得阻止报告生成（文件系统写失败除外）。降级状态下生成的报告必须在页脚注明降级摘要。

### 附录 H：pipeline_data Schema 定义（当前已实现 + 计划中）

> 完整定义和维护责任见 pipeline_data Schema 定义文档。
> 此处仅列出当前阶段已确认的键名和类型。

| 键名 | 类型 | Optional | 状态 | 写入阶段 |
|:-----|:----|:---------|:------|:--------|
| market_data | dict | 否 | 已实现 | prepare_report_data |
| index_data | dict | 是 | 已实现 | prepare_report_data |
| fund_data | dict | 是 | 已实现 | prepare_report_data |
| penetration_data | dict | 是 | 已实现 | prepare_report_data |
| news_data | list | 是 | 已实现 | fetch_news |
| llm_data | dict | 是 | 已实现 | generate_all_llm |
| history_data | dict | 是 | 已实现 | fetch_history_data |
| risk_metrics | dict | 是 | 已实现 | prepare_report_data |
| data_degradation | list[dict] | 是 | 已实现 | capture_snapshot |
| llm_status | str | 是 | 已实现 | generate_all_llm |
| rebalance_signals | list[dict] | 是 | 已实现 | prepare_report_data |
| liquidity_warnings | list[dict] | 是 | 已实现 | capture_snapshot |
| fx_exposure | dict | 是 | 已实现 | fx_exposure (analysis/) |
| scenario_analysis | dict | 是 | 已实现 | prepare_report_data |

[↑ 回到顶部](#目录)
