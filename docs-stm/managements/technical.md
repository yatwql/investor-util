# 个人投资分析报告生成小助手 — 技术设计

> 文档版本：v0.6.0

## 目录

- [1. 总体技术架构](#1-总体技术架构)
- [2. 核心架构原则与设计决策](#2-核心架构原则与设计决策)
- [3. 数据获取层](#3-数据获取层)
- [4. 缓存层](#4-缓存层)
- [5. 报告生成层](#5-报告生成层)
- [6. LLM 集成层](#6-llm-集成层)
- [7. 辅助模块设计](#7-辅助模块设计)
- [8. 模块间依赖关系](#8-模块间依赖关系)
- [9. 架构设计约束](#9-架构设计约束)
- [附录](#附录)

---

## 1. 总体技术架构

### 1.1 系统分层

系统按数据流向分为五层，由贯穿层串联：

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                          输入层                                   │
  │             持仓 xlsx ──→ reader.py ──→ models.Holding             │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │ holdings
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                       数据获取层 (fetcher/)                       │
  │                                                                   │
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
  │                        缓存层 (cache/)                            │
  │        泛用 JSON KV · TTL · 指纹失效 · 分组 · 原子写入           │
  │        大文件 gzip · 路径安全 · 文件损坏自恢复                    │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                      数据处理/计算层                               │
  │                                                                   │
  │  资产穿透    市值核算    持仓分类    新闻关联    组合历史走势       │
  │  B 系列基    LLM 智能   (均在 report/ 或 llm/ 中实现)             │
  │  金深度分    分析                                                   │
  │  析模块                                                           │
  └──────────────────────────────────┬────────────────────────────────┘
                                     │ info 字典
                                     ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                        报告生成层 (report/)                        │
  │                                                                   │
  │  ┌─────────────────────────┐   ┌───────────────────────────────┐  │
  │  │   Excel 管线            │   │   HTML 管线                   │  │
  │  │   openpyxl              │   │   Jinja2 模板                 │  │
  │  │   双端共享 data_status   │   │   CSS order 视觉排序          │  │
  │  └─────────────────────────┘   └───────────────────────────────┘  │
  └───────────────────────────────────────────────────────────────────┘

                 贯穿层：config/ · registry.py · provider_registry.py
```

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
          报告准备阶段（report_prepare）
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

### 1.3 模块职责总览

| 层次 | 模块 | 职责 | 文件 |
|:-----|:-----|:------|:-----|
| **入口** | TUI 主循环 | 菜单编排、用户交互流 | `main.py` / `tui_menu.py` / `tui_handlers.py` |
| **输入** | 持仓读取 | xlsx 解析、列校验、多账户 | `reader.py` |
| **配置** | 配置管理层 | config.json / llm_settings.json 读写 | `config/` |
| **注册** | 中央注册表 | name/缓存前缀/TTL/分组/LLM Settings 键名 | `registry.py` |
| **数据获取** | 数据源注册中心 | 熔断器、会话缓存、策略选择、审计报告 | `provider_registry.py` |
| **数据获取** | Fetcher 调度 | Provider Chain 路由、数据获取编排 | `fetcher/price.py` 等 |
| **数据获取** | 数据源 Provider | 外部 API 封装（14 个文件） | `providers/*.py` |
| **缓存** | 缓存引擎 | 泛用 JSON KV、TTL、指纹、分组、清理 | `cache/` |
| **数据处理** | 代码类型判定 | 资产类型识别原语 | `code_utils.py` |
| **数据处理** | 交易时段判断 | A 股交易时段、午间休市 | `market_hours.py` |
| **报告** | 报告编排与写入 | Excel + HTML 双管线生成 | `report/excel_generator.py` / `html_writer.py` |
| **报告** | 内容模块 | 各页签写入器（~20 个文件） | `report/*.py` |
| **LLM** | 智能分析 | Claude/OpenAI 调用、骨架、Prompt Caching | `llm/` |

[↑ 回到顶部](#目录)

---

## 2. 核心架构原则与设计决策

以下五项跨模块设计决策贯穿系统全局，是所有新增/修改代码的架构约束。

### 2.1 代码类型判定中心化（C1）

**决策**：所有资产代码类型判定集中到 `src/python/code_utils.py`，禁止任何模块自行实现。

**动机**：系统 20+ 处需要判断资产类型（A 股/ETF/基金/QDII/港股/债券等），分散判定导致代码前缀知识散落、"魔法判定"遍地、新增资产类型时全局搜索替换。

**约定**：`code_utils.py` 只提供纯技术原语（基于前缀/名称关键词），业务层组合使用。任何模块不得出现 `code.startswith(("6", "0", "3"))` 或 `"QDII" in name.upper()` 等判定。

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
| | `is_index_fund_by_name(name)` | 指数/ETF联接/中证/沪深300等 | 场外指数基金 |
| | `is_index_link_by_name(name)` | ETF联接/联接/链接 | 指数联接基金 |
| 复合 | `is_etf_by_name_or_code(name, code)` | 名称+代码双维度 | ETF 增强识别 |
| | `is_otc_fund_by_name(name, code)` | 00 代码+名称含基金关键词 | 00 代码重叠区 → 场外基金 |
| | `is_offsite_fund(account)` | 关键词匹配 | 场外基金账户 |
| | `is_fund_holding(name, code, account)` | 三者联合 | 持仓是否需要基金业绩分析 |

#### 内部工具

`_strip_prefix(code)` — 去除 `sh/sz/bj` 前缀，返回纯净 6 位数字代码，非 6 位数字时返回空字符串。所有前缀型判定函数均先调用此函数再匹配。

#### 关键词常量（可供外部导入）

| 常量名 | 值 | 用途 |
|:-------|:----|:------|
| `FUND_ACCOUNT_KEYWORDS` | `("基金", "支付宝", "微信", "银行")` | 场外基金账户判定 |
| `MONEY_KEYWORDS` | `("货币", "现金", "增利", "宝")` | 货币基金识别 |
| `INDEX_KEYWORDS` | `("指数", "ETF联接", "中证", "沪深300", ...)` | 指数基金判定 |

[↑ 回到顶部](#目录)

### 2.2 Provider Chain 必经（C6）

**决策**：绝大多数数据获取必须通过 `fetcher/chain.py` 的 `fetch_with_fallback()`，不得直接调用 Provider 函数。

**动机**：跳过 Chain 直接调用 Provider 会导致熔断器不被激活（故障后无冷却恢复）、fallback 链路断路（某 Provider 失败时不会自动递补）、日志审计缺失（故障记录无法集中追踪）。

**例外**：`fetcher/index.py` 直调 Provider（双链路 fallback 硬编码），原因是指数数据不适用熔断器的单股票级粒度。单元测试 mock 场景除外。

详见 [§3.1 Provider Chain 路由与 fallback](#31-provider-chain-路由与-fallback)。

[↑ 回到顶部](#目录)

### 2.3 缓存统一管理（C2 / C3）

**决策**：所有持久化缓存必须通过 `cache/` 子包的 `get()`/`set()` 接口读写（C2），写入必须使用 `tempfile.mkstemp` + `os.replace` 原子写入模式（C3）。

**动机**：直接操作 `data/cache/` 文件系统导致 TTL 失效、分组清理遗漏、路径穿越等隐患。直接覆写文件在断电/崩溃时产生半写损坏文件。

详见 [§4 缓存层](#4-缓存层)。

[↑ 回到顶部](#目录)

### 2.4 报告配置化（C7 / C14）

**决策**：报告 18 个模块的序号、显示名称、板块可见性由配置驱动，消除硬编码。渲染期数据通过模板 context 传递，禁止写入模块级全局变量。

**两层可见性模型**：

```
section_visible = board_enabled(section.type) AND data_available(section.data_flag)
```

| 层级 | 含义 | 来源 |
|:-----|:------|:------|
| board 层 | 用户配置的板块开关 | `config.json` (`enable_b_series` / `enable_news` / `enable_history`) |
| data 层 | 运行时数据可用性 | 各子模块返回值非 None 判定 |

详见 [§5.4 板块可见性两层模型](#54-板块可见性两层模型) 和 [§5.5 报告序号可配置](#55-报告序号可配置)。

[↑ 回到顶部](#目录)

### 2.5 数据降级治理体系

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

**降级状态基础设施**（`report/data_status.py`）：
- `DataStatusItem` — 单一数据源的可用状态（available / tier / message）
- `STATUS_MESSAGES` — Excel/HTML 两端的共享常量字典（16 条消息）
- `DegradationTracker` — 双信号降级阈值控制器（连续失败计数 + 缓存陈旧度），支持跨会话持久化

详见 [§5.10 数据降级在报告中的体现](#510-数据降级在报告中的体现)。

[↑ 回到顶部](#目录)

---

## 3. 数据获取层

### 3.1 Provider Chain 路由与 fallback

Provider Chain 采用**职责链（Chain of Responsibility）模式**：每个数据类型定义一条优先级链路，`fetch_with_fallback()` 依次尝试，失败则递补下一 Provider。

#### 数据的默认链路

```
                           Provider Chain 结构
 ┌──────────────────────────────────────────────────────────────────┐
 │  price_stock:   腾讯财经 (qt.gtimg.cn)  →  新浪财经 (hq.sinajs.cn)│
 │  price_fund_otc: 东方财富净值 API (直达，无备用)                   │
 │  history_stock:  腾讯财经 K 线          →  新浪财经 K 线          │
 │  history_index:  腾讯财经 K 线          →  新浪财经 K 线          │
 │  history_index_us: 新浪财经 K 线        →  腾讯财经 K 线          │
 │  history_fund_otc: 天天基金 pingzhongdata → 东方财富净值分页       │
 │  industry:       东方财富 push2          →  行情页 quotedata      │
 │  fund_rank:      天天基金 (直达)                                  │
 │  fund_hold:      天天基金 (直达)                                  │
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
          YES              NO (回到循环顶)
            │
            ▼
    ┌─────────────────┐
    │ 过期缓存降级      │─── cache_get(key, CACHE_WEEKLY=7天)
    │ (stale fallback) │     命中? → 返回旧数据
    └────────┬────────┘     未命中? → 返回 None
             │
             ▼
    ┌─────────────────┐
    │ 全链路不可用      │─── 调用方处理（占位文本/异常）
    └─────────────────┘
```

**消费方透明设计**：市场行情批量请求时（如 `report/market_value.py`），每个代码独立触发 Chain，失败资产在汇总日志中列出，不影响其他资产获取：

```
市场行情获取：14 成功，1 失败；失败资产: ['广发多因子灵活配置混合(002943)']
```

[↑ 回到顶部](#目录)

### 3.2 三层熔断架构

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
│  │  cooldown_secs 期满后 is_circuit_broken() 自动：          │   │
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
│  │  2000 条/domain O(1) 淘汰                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

#### 熔断参数对比

| 维度 | 单股票 API | 批量 API（eastmoney_industry） | LLM 熔断器 |
|:-----|:----------|:-----------------------------|:----------|
| 实现位置 | `provider_registry.py` | `provider_registry.py` | `llm/circuit_breaker.py` |
| 熔断阈值 | 连续 3 次传输级失败 | 连续 6 次传输级失败 | 连续 N 次 |
| 冷却时长 | 300s | 120s | 60s |
| 试探次数 | 冷却期满放行一次 | 冷却期满放行一次 | 半开状态放行一次 |
| 恢复条件 | 试探成功 → record_success | 试探成功 → record_success | 半开成功 → 关闭熔断 |

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
        ② 文件缓存 cache_get(cache_key_fn(code), 7天)
           → 设置 _cache_date_mismatch 标记
           → 写入 session cache
           → 返回
```

CACHE_ONLY 时文件缓存中的 `price_date` 若非当天数据，设置 `_cache_date_mismatch=True` 标记供详情行显示处理。

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

[↑ 回到顶部](#目录)

### 3.3 Fetcher 调度架构

`src/python/fetcher/` 各模块按数据类型独立封装：

```
fetcher/
├── price.py            股票/ETF 最新价 + 场外基金净值 + 00 代码降级
├── index.py            A 股/美股指数（直调 Provider，不走 Chain）+ fetch_index_history 历史日线（走 Chain，C6 约束）
├── fund.py             基金排名/持仓/基准（天天基金数据）
├── fund_manager.py     基金经理数据（天天基金 HTML 解析）
├── industry.py         行业分类+概念板块（push2 双链路）
├── chain.py            Provider 优先链定义 + fallback 路由 + 增量合并
├── portfolio_history.py 组合历史走势计算（位于 report/ 包）
└── history_diff.py     F1 快照差异计算（纯计算，无 I/O）
```

**并行预热**：`preload_cache()` 对 preload 组使用 `ThreadPoolExecutor` 并行获取，减少串行等待。

**菜单驱动**：菜单 [1] 清除 + 重拉 refresh 组，菜单 [2] 清除 + 重拉 preload 组，均复用 fetcher 模块的预热入口。

[↑ 回到顶部](#目录)

### 3.4 关键机制

#### 3.4.1 00 代码降级

**问题**：OTC 基金代码与 A 股代码前缀重叠（均以 `00` 开头），`is_a_share_code()` 无法区分。`price.py` 和 `portfolio_history.py` 需要"先股票链路，失败后基金链路"的双阶段降级。

**判定支持函数**（`code_utils.py`）：

| 函数 | 策略 | 用途 |
|:-----|:------|:------|
| `is_otc_code_overlap(code)` | 仅前缀检测（00 开头） | 快速预筛——"是否值得尝试基金净值 API" |
| `is_otc_fund_by_name(name, code)` | 名称+代码双维度 | 00 代码+名称含基金关键词→确认为场外基金 |

`_OTC_FUND_NAME_KW = ("混合", "纯债", "短债", "中短债", "利率债", "信用债", "货币", "联接", "增利")`

**price.py 降级流程（流程图）**：

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
        失败(返回None)
             │
       ┌─────┴─────┐
       │ 需要降级?  │──→ NO ──→ 返回 None（最终失败）
       │(00代码?)   │
       └─────┬─────┘
           YES
             │
             ▼
    ┌────────────────────┐           ┌──────────────────┐
    │ price_fund_otc 链路 │──→ 成功? ──→ 记录"降级成功"  │
    │ eastmoney 净值     │           └──────────────────┘
    └────────┬───────────┘
        失败(返回None)
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

[↑ 回到顶部](#目录)

#### 3.4.2 指数独立获取

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

#### 3.4.3 Fallback 日志增强

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

## 4. 缓存层

### 4.1 策略概览

缓存统一存放在 `data/cache/` 目录，由 `cache/` 子包提供泛用键值对存储接口。

#### 子模块结构

```
cache/
├── __init__.py        公开 API 导出（__all__ 精简为 I-07 最终形态）
├── _store.py          核心存取：get()、set()、clear()
├── _ttl.py            TTL 查询：get_ttl()、get_cache_age()
├── _io.py             文件 I/O：_read_cache_data()、_write_atomic()
├── _paths.py          路径管理：_cache_path()、_GZIP_THRESHOLD（100KB）
├── _groups.py         分组清理：clear_by_group()、clear_by_prefix()
├── _cleanup.py        过期清理：cleanup_expired()
├── _stats.py          统计：缓存命中率、命中/未命中计数
└── services/
    └── holdings_tracker.py  持仓跟踪、指纹比对、增量刷新
```

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

[↑ 回到顶部](#目录)

### 4.2 原子写入与并发安全

**原子写入模式**（C3 约束，`cache/` 和 `config/` 子包共享）：

```
tempfile.mkstemp(dir=cache_dir) → fd, tmp_path
    write(fd, data)
    close(fd)
    os.replace(tmp_path, target_path)  ← 原子替换
```

**并发安全**：
- `os.replace` 保证读取方不会看到半写文件（文件系统级原子操作）
- 多线程同时 `get()` 同一 key 可能产生 TOCTOU 空窗（两线程均认为缓存过期，均拉取 API），但通过 `_write_atomic` 保证同时写入时只有一个生效
- `clear()` 操作使用 `_cache_lock` 互斥

**路径安全**：
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

[↑ 回到顶部](#目录)

### 4.3 指纹驱动失效机制

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
| **指数指纹** | `akshare_extras.py:_compute_index_fingerprint()` | A股+美股指数收盘价（列表拼接→MD5） | `profit_forecast_*`、`sector_flow_*` |
| **代码列表指纹** | `holdings_tracker.py:compute_holdings_fingerprint()` | 持仓+穿透 A 股代码（去重排序→MD5） | `dividend_*` |
| **输入参数指纹** | `news_aggregator.py:_compute_cache_key()` | 新闻源参数+关键词（拼接→MD5） | `news_*` |
| **输入数据指纹** | `llm/fingerprint.py` | LLM 模块依赖数据（持仓汇总/结构序列化→MD5） | `llm_global_macro_*`、`llm_expert_review_*`、`llm_health_check_*`、`llm_penetration_deep_*`、`llm_news_item_*` |

**LLM 指纹筛选**：expert_review / health_check / penetration_deep 的 `_compute_fingerprint()` 在序列化前排除行情波动字段（`price`、`change_pct`），仅品种/份额/成本变化时指纹改变。

**精确键名**：`fund_benchmarks.json`、`fund_concentration_snapshot.json`、`holdings_tracking.json` 等无指纹后缀，仅依赖标准 TTL 过期刷新。

**双保险**：指纹机制与 TTL 互补——指纹未变但 TTL 到期同样触发刷新（TTL 优先，指纹为辅助手段）。

[↑ 回到顶部](#目录)

### 4.4 缓存分组

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

[↑ 回到顶部](#目录)

---

## 5. 报告生成层

### 5.1 管线总览

`src/python/report/` 采用**编排器 + 内容模块**架构，Excel 和 HTML 双端共享 `data_status.py` 降级状态基础设施。

```
                                         handlers_report.py
                                              │
                                              ▼
                                     report_prepare()
                                     并行获取所有数据
                                     合并为 info 字典
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
                                 early_warning /          DegradationTracker)
                                 B 系列 4 个 /
                                 excel_writer.py +
                                 styles.py
```

**条件渲染**：B 系列基金分析（`enable_b_series`）、智能预警（菜单 B/L）、LLM 分析（菜单 L）在 `info` 中无对应数据时自动跳过，不在报告中生成空白页签/章节。

[↑ 回到顶部](#目录)

### 5.2 Excel 管线

**编排器职责**（`excel_generator.py`，~98 行）：
1. 调用 `create_sheets()` 创建 workbook 和页签
2. 迭代 `excel_module_loader.py` 动态加载的内容模块
3. 每个模块接收 `(ws, info, writer)` → 独立写入页签内容和样式

**页签写入器约定**：`_write_*_sheet()` 接收 `info` 字典 + `writer`，独立负责单个页签的内容和样式，互不依赖。

**内容模块动态加载**：`excel_module_loader.py` 通过模块注册表发现并加载写入函数，新增模块只需在注册表中添加条目，无需修改编排器。

[↑ 回到顶部](#目录)

### 5.3 HTML 管线

| 组件 | 文件 | 职责 |
|:-----|:-----|:------|
| 编排器 | `html_writer.py` | 调用 builders → 渲染 → 保存 |
| 数据构建器 | `html_builders.py` | 原始数据 → 结构化渲染对象 |
| 渲染器 | `html_renderers.py` | Markdown→HTML 转换、格式处理 |
| 模板 | `tmpl/report_template.html` | Jinja2 模板 + 宏 |
| 环境 | `html_jinja_env.py` | Jinja2 环境初始化、过滤器注册 |
| 保存 | `html_save.py` | HTML 文件写入 |

**渲染期通信**（C14 约束）：所有渲染期数据（`section_visible_dict` 等）必须通过模板 `render()` 的 context 参数传递，不得写入 `_ENV.globals` 或模块级 dict 作为跨函数通信渠道。单次会话中不变的数据（如 `_ENV` 过滤器注册）不受此限。

[↑ 回到顶部](#目录)

### 5.4 板块可见性两层模型

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

`html_writer.py:_compute_section_visibility()` 集中实现两层合并，返回 `section_visible_dict`：

```python
board_flags = {
    "always":   True,
    "b_series": enable_b_series,
    "news":     enable_news,
    "history":  enable_history,
    "llm":      enable_llm,
}

# 可见性判定循环
for sec in section_order:
    board_ok = board_flags.get(sec["type"], True)
    if not board_ok: continue                  # board 层关闭
    flag_name = sec.get("data_flag")
    if not flag_name:                          # always/history 类型
        section_visible_dict[sec["key"]] = True
    else:                                      # b_series/news/llm 类型
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
| `early_warnings` | `bool(early_warnings)` | `news` | 智能预警 |
| `llm_enabled` | `llm_enabled_flag` | `llm` | LLM 全部 5 模块 |

`always` 类型模块（summary / market_value / category / penetration / fund_performance）无 data_flag，始终显示。

#### Board 层配置

| 函数 | 配置字段 | 配置来源 | 对应 section.type |
|:-----|:---------|:---------|:------------------|
| `is_enable_b_series(config)` | `enable_b_series` | `config.json` | `b_series` |
| `is_enable_news(config)` | `enable_news` | `config.json` | `news` |
| `is_enable_history(config)` | `enable_history` | `config.json` | `history` |
| `is_enable_llm(config)` | `enabled_llm`（4 个子键任一启用） | `llm_settings.json` | `llm` |

缺失均视为 `true`（向后兼容），类型/格式错误记录 WARNING。

[↑ 回到顶部](#目录)

### 5.5 报告序号可配置

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

18 个模块分布：`always`×5、`b_series`×4、`news`×2、`llm`×5、`history`×2。

#### 配置接口

```json
{
  "report_section_order": {
    "fund_manager": 1,
    "summary": 2,
    "fund_performance": 5
  }
}
```

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

```
1. 从 section_order 筛选所有可见模块（board+data 双层过滤）
2. 将 llm_usage 从可见列表分离，强制追加到末尾
3. 按新顺序从 1 开始分配连续序号
4. visible_numbers = {sec["key"]: idx for idx, sec in enumerate(ordered_visible, start=1)}
```

**HTML 端**：导航栏使用 `section_order` 动态循环（只渲染可见模块），CSS `order` 属性视觉排序，章节标题使用 `{{ section_numbers['key'] }}` 动态显示。

**Excel 端**：页签标题采用 `f"{visible_count}.{sec['name']}"` 格式。

[↑ 回到顶部](#目录)

### 5.6 组合历史走势计算算法

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
│ 输出：max_drawdown_val, max_drawdown_pct,     │
│       drawdown_start, drawdown_end           │
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

- 有新高时自动重置潜在回撤起算日
- 返回时金额和百分比均取负值（如 `-49626.48`、`-10.22%`）

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

**增量合并流程**：

```
fetch_with_incremental_fallback(chain_name, code, days)
    │
    ▼
cache_key = f"history_{chain_name}_{code}"
cached = cache_get(cache_key, CACHE_WEEKLY)  ← 读取已有缓存作为底座
last_cached_date = cached[-1]["date"] if cached else None
    │
    ▼
providers = _get_chain(chain_name)  ← 获取 Provider Chain
    │
    ▼
new_data = _try_providers(providers, ..., start_from=last_cached_date)
    │                 (增量获取：只请求 last_cached_date 之后的数据)
    ▼
┌──────────────────────────────────────────┐
│ new_data 非空?                           │
├────────────┬─────────────────────────────┤
│  YES       │  NO                         │
│   │        │     ↓                       │
│   ▼        │  ┌──────────────────┐       │
│ 检查是否   │  │ 有缓存?          │       │
│ 全量返回   │  ├──────┬───────────┤       │
│ (起点 ≤    │  │ YES  │ NO        │       │
│  缓存起点) │  │ 返回 │ 返回 []   │       │
│   │       │  │ 缓存  │           │       │
│   ▼       │  └──────┘           │       │
│ 增量合并   │                      │       │
│ _merge_   │                      │       │
│ by_date   │                      │       │
│   │       │                      │       │
│   ▼       │                      │       │
│ 连续性     │                      │       │
│ 校验      │                      │       │
│ _validate │                      │       │
│ _continuity│                     │       │
│   │       │                      │       │
│   ▼       │                      │       │
│ 重叠?     │── YES → 全量刷新     │       │
│ (历史修正) │  cache_clear +       │       │
│           │  无 start_from 重取  │       │
└───────────┴──────────────────────┘       │
                     │
                     ▼
              写入 cache_set
              返回 new_data[-days:]
```

**Provider 惰性加载**：通过 `_HISTORY_PROVIDER_MAP` 实现动态 `importlib.import_module()`，避免模块加载时的循环依赖。

**合并算法**（`_merge_by_date`）：
- `seen = {d["date"] for d in cached}` 记录已有日期
- 新数据同天覆盖（`_replace_by_date`），处理历史修正
- `sorted(merged, key=lambda x: x["date"])` 升序排列

**连续性校验**（`_validate_continuity`）：
- 新数据首日 < 旧数据末日 → 重叠 → 触发全量刷新
- 日期跳空 >5 交易日 → 记录 WARNING（部分历史不可达）
- **纯检测/日志用途**，异常不影响主流程

**东财历史净值分页**：`eastmoney.fetch_fund_nav_history()` 改用 `pageSize=20` + 分页循环代替单次 `pageSize=365`（超 API 上限返回 null），页间 0.3s 防限流，最多 10 页（约 200 条 ≈10 个月）。

#### 基准指数对比

基准指数历史走势的并行获取与归一化对齐，在 5 步算法链基础上叠加显示。

**配置接口**（`config.json`）：
```json
{
  "history": {
    "benchmark_indices": {
      "sh000300": "沪深300",
      "gb_inx": "标普500"
    },
    "analysis": "auto"
  }
}
```

**配置合并保护**：嵌套 dict 合并时使用 `merged[key] = {**merged[key], **val}` 而非直接覆盖，避免 `benchmark_indices` 默认值被 `history.analysis` 配置静默覆盖。

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

**`fetch_benchmarks()`** — 并行获取多个指数的历史日线：
- 接收 `{代码: 名称}` 映射，如 `{"sh000300": "沪深300", "gb_inx": "标普500"}`
- 使用 `ThreadPoolExecutor(max_workers=4)` 并行调用 `fetch_index_history()`
- 各指数独立处理，失败不影响其他
- 全部失败时返回空字典，调用方静默降级

**`normalize_benchmarks()`** — 归一化到 100 基点并与组合走势对齐：

```
输入：组合走势 bars + 各指数原始数据 {code: {name, bars}}
    │
    ▼
① 构建 date→close 映射（过滤无效 close）
    │
    ▼
② 无重叠检测：指数数据完全早于/晚于组合区间 → 跳过
    │
    ▼
③ 确定对齐起算日 align_start = max(组合起算日, 指数首条数据日)
    │
    ▼
④ 起算日 close 获取：在 align_start 当天或之前取最近的 close
    │
    ▼
⑤ LOCF 填充缺失日 + 归一化：
   value = last_close / close_at_start × 100
    │
    ▼
⑥ 计算区间累计收益率（终值 - 100）
    │
    ▼
⑦ 计算区间最大回撤（Peak-to-Trough，归一化值）
```

**输出数据字典（每指数）**：
```python
{
    "code": str,              # 指数代码
    "name": str,              # 指数名称
    "bars": [                 # 归一化走势，与组合日期一一对应
        {"date": str, "value": float},
    ],
    "total_return_pct": float,  # 区间累计收益率（%）
    "max_drawdown_pct": float,  # 区间最大回撤（%）
    "data_start": str,         # 有效起始日
    "data_end": str,           # 有效结束日
    "status": str,             # "ok" | "degraded"
}
```

**防御性编程**：
- `bar.get("date")` 防御性检查（防止 KeyError）
- 每次 index bar 的 close 校验：`isinstance(close, (int, float)) and close > 0`
- 每个基准完成归一化后输出 `logger.info("[normalize] %s(%s) 归一化完成, %d 条数据")`
- 异常捕获在 `get_combined_timeseries()` 的 try/except 中，不阻塞主流程

**HTML 渲染**：`drawSimpleChart()` 多 dataset 版本，组合 as-if 曲线（实线）+ 基准指数（虚线，颜色循环），右侧图例显示。回撤图同样叠加基准指数的回撤序列（灰色虚线）。移除了 Chart.js CDN 外部依赖，使用 Canvas 2D API 原生渲染。

**Excel 渲染**：`portfolio_history` 页签每基准一列（归一化值 `'0.00'` 格式），`drawdown_analysis` 页签对比指标矩阵（累计收益率/最大回撤/波动率等）。

**注册表条目**：`history_stock` / `history_fund_otc` / `history_index` / `history_index_us` 历史走势数据在 registry 中注册为无分组缓存，不受菜单缓存命令影响。

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

[↑ 回到顶部](#目录)

### 5.7 B 系列：基金深度分析模块

B 系列 4 个模块通过 `enable_b_series` 标志控制条件渲染，跟随 `include_news`（菜单 B/L 时触发）。

```
                    B 系列模块架构
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
    │
    ▼
配对明细表：按重合度降序排列
    含共同标的数 + 共同标的名称列表
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

基于持仓个股市值 + PE 数据的加权风格判定（`fund_style_analysis.py`）：

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

[↑ 回到顶部](#目录)

### 5.8 资产穿透 TOP10

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

[↑ 回到顶部](#目录)

### 5.9 财经新闻热点与持仓关联分析

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
           概念类型来源：东方财富 push2 API 行业分类和概念板块
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

#### LLM 二次关联分析

可选功能（`enabled_llm.news_correlation` 配置开启），对已排序新闻做 LLM 深度关联评分，用于提升关联准确性。

[↑ 回到顶部](#目录)

### 5.10 数据降级在报告中的体现

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
│        B系列/新闻/预警/历史走势）                            │
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
`data/state/` 目录与 `data/cache/` 同级但独立管理，存放运行时跨会话状态文件而非可清理的缓存数据，
避免 `cache.cleanup_expired()` 误清理。

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

## 6. LLM 集成层

### 6.1 架构总览

`src/python/llm/` 包为 12 子模块架构：

```
llm/
├── generators_orchestrator.py  入口：4+1 模块并行编排
├── skeleton.py                 骨架：缓存检查→API→markdown→HTML（85%公共逻辑）
├── api.py                      API 路由 + 重试 + 截断检测 + 熔断器
├── api_base.py                 底层 HTTP 调用（_attempt_api_call）
├── generators.py              4 个单例生成函数
├── prompts.py                  System Prompt + User Prompt 构建
├── fingerprint.py              缓存指纹计算
├── session.py                  会话用量追踪（线程安全）
├── pricing.py                  费用估算
├── markdown.py                 Markdown→HTML 转换
├── circuit_breaker.py          LLM API 熔断器
└── models.py                   数据模型
```

**调用链**：

```
generators_orchestrator（并行调度 4+1 模块）
    │
    └── skeleton.generate_llm_module()
            │ ① 缓存检查（指纹+TTL）→ 命中则直接返回
            │ ② API 调用
            ├── api.call_llm()
            │      └── api_base._attempt_api_call()
            │              ├── Claude → anthropic SDK
            │              └── OpenAI/DeepSeek → openai SDK
            │ ③ Markdown→HTML（markdown.py）
            │ ④ 写入缓存
            └── 返回结果
```

### 6.2 关键机制

| 机制 | 实现 | 说明 |
|:-----|:------|:------|
| Extended Thinking | Claude: `thinking.budget_tokens`；DeepSeek: `output_config.effort` | 与 `temperature` 互斥 |
| Prompt Caching | Anthropic 专属，system prompt 数组 + `cache_control: ephemeral` | 5 分钟内复用免全价 |
| 截断重试 | 检测 `TRUNCATION_MARKER` 后自动 1.5× max_tokens 重试一次 | 修复内容被截断的情况 |
| 内容过滤安抚 | 空返回时追加安抚指令重试 | 应对内容审查误杀 |
| 会话用量追踪 | `session.py` 维护线程安全 `session_usage` 字典 | 按模块粒度追踪 token/费用/缓存命中 |

**LLM 模块配置化**：每个 LLM 模块（global_macro / expert_review / health_check / penetration_deep / news_correlation）在 `registry.py` 中通过 `settings_suffix` 注册，自动派生 `llm_settings.json` 的所有合法键名（model / temperature / timeout / cache_enabled / max_tokens / system_prompt / thinking_enabled / thinking_budget / reasoning_effort / output_brief）。

详细设计见 [LLM 技术要点文档](llm-technical.md)。

[↑ 回到顶部](#目录)

---

## 7. 辅助模块设计

### 7.1 配置管理

#### 配置分层

```
config.json (基础配置)       → get_config() 内存缓存，按 mtime 自动失效
llm_settings.json (非敏感)    → get_llm_config() 合并读取，联合 mtime 失效
llm_key.json (敏感密钥)       → 覆盖 llm_settings.json 的同名字段
```

`config/` 子包结构：

```
config/
├── __init__.py        # 公开 API 导出
├── _core.py           # 核心读写：get_config()、set_config()、is_enable_*()
├── _defaults.py       # 默认配置值定义
└── _comments.py       # JSON 注释剥离（_strip_json_comments）
```

#### JSON 注释支持

`_strip_json_comments()` 逐字符扫描，支持 `//` 单行注释和 `/* */` 多行注释，正确处理字符串内的转义引号，不会将字符串内的 `//` / `/*` 误伤。

#### 原子写入

配置文件（`set_config`）和缓存写入（`_write_atomic`）均使用 `tempfile.mkstemp` + `os.replace` 模式。

[↑ 回到顶部](#目录)

### 7.2 中央注册表（registry.py）

**设计目标**：消除 `config.py` / `cache.py` / `constants.py` 三处分散维护的遗漏风险，做到"一处注册，全局生效"。

#### DataModuleDef 条目结构

```python
@dataclass(frozen=True)
class DataModuleDef:
    name: str                # 人类可读名称，"股票价格"、"全球政经局势"
    data_type: str           # 数据类型键，用于 TTL 查找和路由
    cache_prefixes: tuple    # 缓存前缀，如 ("price_",)
    exact_cache_keys: tuple  # 精确缓存键名，如 ("fund_manager_snapshot",)
    cache_ttl: float         # 默认缓存过期时间（秒）
    settings_suffix: str|None# LLM settings 键后缀，None=非 LLM 模块
    cache_groups: tuple      # 分组，("preload",) / ("refresh",) 或空
```

当前注册 **25 个数据模块**：

| 分类 | 数量 | 模块 |
|:-----|:----:|:-----|
| 基础行情（preload） | 2 | price、index |
| 基金数据（refresh） | 2 | rank、hold |
| 行业 | 1 | industry |
| 新闻（refresh） | 1 | news |
| LLM 分析（preload/refresh） | 5 | global_macro、expert_review、news_correlation、health_check、penetration_deep |
| 补充数据（refresh） | 4 | profit_forecast、sector_flow、extended、dividend |
| B 系列基金分析（refresh/无分组） | 4 | fund_manager、fund_overlap、fund_concentration、fund_style_snapshot |
| 精确键名（refresh/无分组） | 3 | benchmark、tracking、calendar |
| 历史走势（无分组） | 4 | history_stock、history_fund_otc、history_index、history_index_us |

#### 派生产出接口

| 接口 | 用途 | 消除的散落信息 |
|:-----|:------|:--------------|
| `get_cache_ttl_defaults()` | data_type → TTL 默认值 | `constants.py` 的 `CACHE_TTL_DEFAULTS` |
| `get_prefix_type_map()` | 缓存前缀 → data_type | `cache.py` 的 `prefix_type_map` |
| `get_exact_type_map()` | 精确键名 → data_type | `cache.py` 的 `exact_map` |
| `get_known_llm_settings_keys()` | `llm_settings.json` 合法键名 | `config.py` 的 `_KNOWN_LLM_SETTINGS_KEYS` |
| `get_report_section_order()` | 用户配置+默认顺序合并 | `html_writer.py` / `excel_generator.py` 硬编码 |
| `get_llm_module_names()` | suffix → 中文名称 | 各模块内部 `_label_map` 字典 |

[↑ 回到顶部](#目录)

### 7.3 市场时段判断（market_hours.py）

**三层 fallback 架构**：

```
is_market_open()
    │
    ▼
┌─────────────────────────────────────────────┐
│ 第 1 层：config.json 手动覆盖                 │
│ market_hours.start / end                    │
│ 支持午间不中断模式（连续时段）                  │
│ market_hours.official_source: false 关闭 API  │
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
│ make_http_client(timeout=5.0)               │
├─────────────────────────────────────────────┤
│ 成功? → 返回 True/False                      │
│ API 不可用? → 进入下一层                      │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│ 第 3 层：内置默认值                           │
│ 北京时区工作日 09:30-11:30 + 13:00-15:00     │
│ 自动排除午餐和周末                            │
├─────────────────────────────────────────────┤
│ 固定返回 True/False                          │
└─────────────────────────────────────────────┘
```

**时区安全**：所有 `datetime.now()` 调用均使用 `timezone(timedelta(hours=8))` 北京时区，防止 UTC 服务器上时段判断全错。异常时保守返回 `False`。

**消费方**：
- `cache/_ttl.py:get_ttl()` — 交易时段内 `market_hour_aware` 类型自动使用短 TTL（30s）
- `report/market_value.py:is_market_open()` — 取价方式标签判断
- `report/market_value.py:is_midday_break()` — 午间休市识别（11:30-13:00，用于区分"午市收盘"和"收盘价"）

[↑ 回到顶部](#目录)

### 7.4 持仓读取与列校验（reader.py）

基于 openpyxl 解析持仓 xlsx：

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

多文件选择：持仓目录下多个 xlsx 时弹出 TUI 选择器（`tui_handlers.py` 中 `select_holdings_file()`）。

[↑ 回到顶部](#目录)

---

## 8. 模块间依赖关系

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

report/excel_generator.py (Excel 编排器)
  → report/excel_module_loader.py (模块动态加载)
  → report/excel_sheet_factory.py (页签创建/可见性)
  → report/excel_market_data.py / excel_content_sheets.py
  → report/excel_news_warning.py / excel_b_series.py / excel_llm_usage.py
    → report/summary.py / summary_llm_usage.py
    → report/market_value*.py / category.py / penetration*.py
    → report/fund_performance.py / news_correlation.py
    → report/llm_content.py / early_warning.py
    → report/fund_manager_sheet.py / fund_overlap*.py
    → report/fund_concentration*.py / fund_style*.py
  → report/excel_writer.py + styles.py
  → report/data_status.py (降级状态)

report/html_writer.py (HTML 编排)
  → report/html_builders.py (数据构建器)
  → report/html_renderers.py (Markdown→HTML)
  → report/html_jinja_env.py (Jinja2 环境)
  → report/html_save.py (文件写入)
  → tmpl/report_template.html (Jinja2 模板)
  → report/data_status.py

llm/generators_orchestrator.py (LLM 编排)
  → llm/skeleton.py → llm/api.py → llm/prompts.py
  → llm/fingerprint.py / pricing.py / session.py / markdown.py
  → cache/ (LLM 结果缓存)

config/ → registry.py (注册表驱动的 TTL/分组/键名)
handlers_*.py → 各模块入口函数编排
```

[↑ 回到顶部](#目录)

---

## 9. 架构设计约束

本节定义系统架构层面的**设计约束**。所有新增或修改的代码必须遵守，违反即视为架构违规。
约束按职责域分组，每个约束包含：设计目的（为何存在）、违反后果（不遵守的影响）、适用范围（哪些模块/场景受约束）。

### 9.1 数据获取层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C1** | **代码类型判定中心化** — 所有资产代码类型判定必须使用 `code_utils.py` 提供的函数，禁止任何模块自行实现判定逻辑 | 系统 20+ 处需要判断资产类型（A 股/ETF/基金/QDII/港股/债券等），分散判定导致代码前缀知识散落，"魔法判定"遍地，新增资产类型时需全局搜索替换 | 代码评审不通过；新增资产类型时遗漏大量散落判定点 | 所有涉及代码类型判定的模块（fetcher/、report/、llm/ 等） |
| **C4** | **会话级 API 复用** — 同次会话内同一 API 返回的数据必须通过 `DataSourceRegistry.session_cache` 复用，禁止重复 HTTP 请求 | 避免同一资产在多个模块中重复请求相同 API 数据，降低 API 限频风险，提升性能 | API 调用量膨胀、触发限频、报告生成时间增长 | 所有通过 Provider 获取数据的模块 |
| **C5** | **HTTP 客户端统一** — 所有 HTTP 请求必须使用 `http_client.py` 工厂方法创建客户端实例 | 统一 SSL 配置、超时策略、连接池管理；防止各模块自行构造 request 导致配置散落、连接池泄漏 | SSL 配置不一致、连接泄漏、重试策略不统一 | 所有发起 HTTP 请求的模块（providers/、llm/） |
| **C6** | **Provider Chain 必经** — 大多数数据获取必须通过 `fetch_with_fallback()` 走 Chain 路由，不得直接调用 Provider 函数 | 跳过 Chain 直接调用 Provider 会导致熔断器不被激活（故障后无冷却恢复）、fallback 链路断路（某 Provider 失败时不会自动递补）、日志审计缺失 | 熔断器失效、fallback 断路、故障记录缺失 | fetcher/ 各模块（例外：index.py 直调 Provider 的双链路 fallback 硬编码，熔断器不适用于指数场景） |

### 9.2 缓存层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C2** | **缓存统一管理** — 所有持久化缓存必须通过 `cache/` 子包的 `get()`/`set()` 接口读写，禁止直接操作 `data/cache/` 文件系统 | 直接操作文件系统导致 TTL 失效（缓存无法感知过期时间）、分组清理遗漏（菜单命令无法清除对应缓存）、路径穿越隐患 | 缓存不一致、TTL 失效、分组清理遗漏、路径安全风险 | 所有读写 data/cache/ 的模块 |
| **C3** | **缓存原子写入** — 所有缓存/配置文件写入必须使用 `tempfile.mkstemp` + `os.replace` 原子写入模式 | 直接覆写文件在断电/崩溃时产生半写损坏文件，导致后续读取解析失败 | 半写文件损坏、数据不完整、崩溃后无法自恢复 | cache/ 子包、config/ 子包、history_snapshot.py |

### 9.3 报告层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C7** | **报告序号不可硬编码** — 报告 18 个模块的序号和显示名称必须通过 `registry.py` 的 `_REPORT_SECTION_DEFAULT` 注册表驱动，支持 `config.json` 自定义覆盖 | 硬编码序号使得用户无法通过配置调整报告章节顺序，且新增/删除模块时需要全局修改序号 | 序号配置失效、用户自定义顺序不生效 | report/ 编排器（excel_generator.py、html_writer.py） |
| **C10** | **新闻召回策略可配置** — `per_source` 每源获取数量必须与 `news_top_count` 最终截取数量解耦，`per_source` 动态计算为 `max(500, news_top_count × 2)`，不可写死 | 固定值会导致去重后候选新闻不足，最终截取数不满足用户配置 | 新闻候选不足、用户配置不生效 | providers/news_aggregator.py |
| **C14** | **渲染期数据不可写入模块级全局变量** — 所有渲染期数据（如 `section_visible_dict`）必须通过模板 `render()` 的 context 参数传递，不得写入 `_ENV.globals` 或模块级 dict | 模块级全局变量在并发/多次渲染场景下产生状态污染，且难以追踪数据流向 | 并发不安全、渲染状态污染、数据流向不可追踪 | report/html_writer.py、模板渲染相关模块 |

### 9.4 LLM 集成层约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C9** | **LLM 模块注册** — 新增 LLM 分析模块时，必须在 `generators_orchestrator.py` 的 `_MODULE_FNS` 字典和 `registry.py` 的 `DataModuleDef` 注册表中同时注册 | 仅在 orchestrator 注册会导致缓存/TTL/统计遗漏；仅在 registry 注册会导致编排调度遗漏 | LLM 调度遗漏、缓存 TTL 未定义、用量统计缺失 | llm/ 包 + registry.py |

### 9.5 基础设施约束

| # | 约束 | 设计目的 | 违反后果 | 适用范围 |
|:---|:-----|:---------|:---------|:---------|
| **C8** | **日志统一** — 所有模块必须使用 `logging.getLogger("invest")` 获取日志器，禁止直接使用 `print()` 输出运行时诊断信息 | 统一日志名称使日志过滤、级别控制、格式管理集中生效；`print()` 无法控制日志级别，污染 stdout | 日志碎片化、日志级别失控、`print()` 干扰输出流 | 全模块（交互式 print 如进度提示不受此限） |
| **C15** | **控制台日志着色** — WARNING 级别使用黄色输出、ERROR 级别使用红色输出；当 `NO_COLOR` 环境变量设置或输出非 TTY 时自动降级为无颜色 | 着色提升控制台日志的辨识度，便于快速定位告警和错误；降级保证日志导出、管道重定向时无转义字符污染输出 | 日志可读性降低、非 TTY 环境下转义字符污染 | `logger.py`（_ColoredFormatter） |

### 9.6 测试约束

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
│   │   ├── cache/               # 缓存引擎子包（7 子模块 + services）
│   │   ├── code_utils.py        # 代码类型判定中心化
│   │   ├── config/              # 配置管理子包（_defaults / _comments / _core）
│   │   ├── constants.py         # 共享常量 + 项目根路径（标记文件查找法）
│   │   ├── fetcher/             # 数据获取调度（price/index/fund/industry/chain/akshare）
│   │   ├── handlers_cache.py    # TUI 缓存管理命令
│   │   ├── handlers_config.py   # TUI 配置管理命令
│   │   ├── handlers_report.py   # TUI 报告生成命令
│   │   ├── http_client.py       # HTTP 客户端工厂
│   │   ├── llm/                 # LLM 集成（12 子模块）
│   │   ├── logger.py            # 日志模块（_ColoredFormatter）
│   │   ├── main.py              # TUI 入口 + 菜单循环
│   │   ├── market_hours.py      # A 股交易时段判断
│   │   ├── models.py            # 数据模型
│   │   ├── provider_registry.py # 数据源注册中心 — 熔断/缓存/策略/审计
│   │   ├── providers/           # 数据源提供商（14 个文件）
│   │   ├── reader.py            # 持仓 Excel 解析
│   │   ├── registry.py          # 中央注册表（25 个数据模块 + 18 个报告模块）
│   │   ├── report/              # 报告生成（~30 个文件）
│   │   ├── tui.py               # 键盘输入封装
│   │   ├── tui_handlers.py      # 菜单通用辅助
│   │   └── tui_menu.py          # 菜单交互
│   └── test/                    # 测试（按标记分组）
│       ├── conftest.py          # pytest 配置 + 分层标记注册
│       ├── helpers.py           # 测试辅助工具
│       ├── unit/                # 单元测试
│       ├── integration/         # 集成测试
│       └── scenario/            # 场景测试
├── data/                        # 运行时数据（config/holdings/cache）
├── reports/                     # 生成报告
├── logs/                        # 程序日志
├── docs-stm/                    # 项目管理文档
├── scripts/                     # 启动/测试脚本
├── pyproject.toml
└── CLAUDE.md
```

[↑ 回到顶部](#目录)

---

### 附录 B：数据源完整一览

| 用途 | 链路方案 | Provider 文件 |
|:-----|:---------|:-------------|
| 场内 A 股/ETF 实时价 | 腾讯财经 → 新浪财经（双链路 fallback） | `tencent.py` / `sina.py` |
| 场外基金净值 | 东方财富（直达，无备用） | `eastmoney.py` |
| 基金业绩排名 | 天天基金 JS 变量解析（直达） | `tiantian.py` |
| 基金持仓数据 | 天天基金 HTML 解析（直达） | `tiantian.py` |
| A 股指数 | 腾讯财经 → 新浪财经（双链路 fallback） | `tencent.py` / `sina.py` |
| 美股指数 | 新浪财经 → 腾讯财经（双链路 fallback） | `sina.py` |
| 财经新闻 | 5 源并行：新浪/东方财富/财联社/华尔街见闻/akshare | 各 `*_news.py` |
| 行业分类/概念板块 | 东方财富 push2（主）→ quotedata 回退 | `eastmoney_industry.py` / `eastmoney_industry_rest.py` |
| 机构盈利预测 | akshare 全量获取（直达） | `fetcher/akshare.py`（封装 `akshare_extras.py`） |
| 行业资金流向 | akshare 今日排名（直达） | `fetcher/akshare.py`（封装 `akshare_extras.py`） |
| 股票历史分红 | akshare 逐股获取（直达） | `fetcher/akshare.py`（封装 `akshare_extras.py`） |
| 基金经理数据 | 天天基金 HTML 解析（主）→ 档案页回退 | `fetcher/fund_manager.py` |

> 各数据源具体 API 端点格式见 [需求文档 §5.1 — 数据源总览](requirements.md#51-数据源总览)。
>
> 新闻数据处理模块：`news_aggregator.py`（聚合去重）、`news_correlator.py`（关联分析）、`news_keywords.py`（关键词提取）、`news_sources.py`（源元数据定义），位于 `providers/` 下。

[↑ 回到顶部](#目录)

---

### 附录 C：缓存 TTL 明细表

#### 行情/数据类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `price` | `price_{code}.json` | 24h | 交易时段 30s | — | preload |
| `index` | `index_{code}.json` | 24h | 交易时段 30s | — | preload |
| `news` | `news_{md5}.json` | 15 分钟 | — | 新闻源参数+关键词 | refresh |
| `sector_flow` | `sector_flow_{fingerprint}.json` | 15 分钟 | — | A股+美股指数 | refresh |
| `rank` | `fund_perf_{code}.json` | 24h | — | — | refresh |
| `profit_forecast` | `profit_forecast_{fingerprint}.json` | 24h | — | A股+美股指数 | refresh |
| `hold` | `fund_hold_{code}.json` | 7 天 | — | — | refresh |
| `industry` | `industry_{code}.json` | 14 天 | — | — | refresh |
| `dividend` | `dividend_{fingerprint}.json` | 30 天 | — | 持仓+穿透 A 股代码 | refresh |
| `benchmark` | `fund_benchmarks.json` | 30 天 | — | — | refresh |

#### LLM 分析类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `llm_expert_review` | `llm_expert_review_{fingerprint}.json` | 2h | — | 持仓汇总+分类+穿透+明细 | preload |
| `llm_news_correlation` | `llm_news_item_{hash}.json`（逐条） | 1h | — | 标题前 80 字+持仓指纹 | refresh |
| `llm_global_macro` | `llm_global_macro_{fingerprint}.json` | 24h | — | A股/美股指数+持仓汇总 | preload |
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
| `history_index_us` | `history_index_us_{code}.json` | 30 天 | — | — | 无分组 |

#### 系统类

| 键名 | 文件名模式 | TTL | 盘中特殊 | 指纹 | 分组 |
|:-----|:----------|:---:|:--------:|:----|:-----|
| `tracking` | `holdings_tracking.json` | 30 天 | — | — | 无分组 |
| `calendar` | `trading_calendar.json` | 14 天 | — | — | 无分组 |

> `—` 表示精确键名（无指纹后缀），TTL 到期后刷新。

[↑ 回到顶部](#目录)
