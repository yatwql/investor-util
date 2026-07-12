# 个人投资分析报告生成小助手 — 技术设计

创建日期：2026-06-28
最后更新：2026-07-12（v0.4.0 — 文档双向校验修正 + 设计约束优化）

---

## 技术架构总览

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  持仓 xlsx   │ ──→ │  数据获取层   │ ──→ │  报告生成层   │
│ (reader.py)  │     │ (fetcher/)   │     │ (report/)    │
└─────────────┘     └──────┬───────┘     └──────┬───────┘
                          │                     │
                    ┌──────▼───────┐      ┌─────▼──────┐
                    │   缓存层      │      │  配置管理层   │
                    │ (cache/)     │      │ (config/)   │
                    └──────────────┘      └────────────┘
                          │                     │
                          └──────────┬──────────┘
                                     ▼
                            ┌──────────────────┐
                            │  中央注册表        │
                            │ (registry.py)     │
                            └──────────────────┘
```

### 核心模块职责

| 模块 | 职责 | 文件 |
|------|------|------|
| TUI 入口 | 主循环、流程编排 | `src/python/main.py` |
| 菜单交互 | 菜单定义、渲染、导航 | `src/python/tui_menu.py` |
| 菜单通用辅助 | 退出/按任意键继续/LLM用量输出 | `src/python/tui_handlers.py` |
| 配置管理 | config.json + llm_key.json（敏感字段）/ llm_settings.json（非敏感参数）读写、mtime 缓存 | `src/python/config/`（拆为子包） |
| 中央注册表 | 数据模块的 name/缓存前缀/TTL/分组/LLM Settings 键名统一注册与查询 | `src/python/registry.py` |
| 缓存引擎 | 泛用 JSON 缓存、TTL、指纹失效、过期清理 | `src/python/cache/`（子包，7 子模块 + services） |
| 数据获取 | Provider Chain 路由、fallback、缓存预热 | `src/python/fetcher/` |
| 持仓读取 | xlsx 解析、多工作表、列校验 | `src/python/reader.py` |
| LLM 客户端 | Claude / OpenAI / DeepSeek API 调用 | `src/python/llm/` |
| 数据源注册中心 | 熔断器/会话缓存/策略选择/审计报告 | `src/python/provider_registry.py` |
| 报告生成 | Excel (openpyxl) + HTML (Jinja2) | `src/python/report/*.py` |

## 目录结构

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── python/                   # 源代码
│   │   ├── __init__.py
│   │   ├── cache/               # 缓存引擎子包（路径/IO/存取/TTL/统计/清理/组管理 + services）
│   │   ├── code_utils.py         # 代码类型判定中心化（A 股/基金/QDII 等识别原语）
│   │   ├── config/               # 配置管理子包（_defaults / _comments / _core）
│   │   ├── constants.py          # 共享常量 + 项目根路径（标记文件查找法）
│   │   ├── fetcher/               # 数据获取调度
│   │   ├── handlers_cache.py     # TUI 缓存管理命令
│   │   ├── handlers_config.py    # TUI 配置管理命令
│   │   ├── handlers_report.py    # TUI 报告生成命令
│   │   ├── http_client.py        # HTTP 客户端工厂
│   │   ├── llm/                  # LLM 集成（12 子模块）
│   │   ├── logger.py             # 日志模块
│   │   ├── main.py               # TUI 入口 + 菜单循环
│   │   ├── market_hours.py       # A 股交易时段判断
│   │   ├── models.py             # 数据模型
│   │   ├── provider_registry.py  # 数据源注册中心 — 熔断器/会话缓存/策略选择/审计报告
│   │   ├── providers/            # 数据源提供商
│   │   ├── reader.py             # 持仓 Excel 解析
│   │   ├── registry.py           # 中央注册表
│   │   ├── report/               # 报告生成
│   │   ├── tui.py                # 键盘输入封装
│   │   ├── tui_handlers.py       # 菜单通用辅助（退出/按任意键/LLM用量输出）
│   │   └── tui_menu.py           # 菜单交互
│   └── test/                     # 测试（按标记分组目录）
│       ├── conftest.py           # pytest 配置 + 分层标记注册
│       ├── helpers.py            # 测试辅助工具
│       ├── unit/                 # 单元测试
│       ├── integration/          # 集成测试
│       ├── scenario/             # 场景测试
├── data/                         # 运行时数据
├── reports/                      # 生成报告
├── logs/                         # 程序日志
├── docs-stm/                     # 项目管理文档
├── scripts/                      # 启动脚本
├── CLAUDE.md / README.md / requirements.txt
```


---

## 代码类型判定中心化

`src/python/code_utils.py` 是资产代码类型识别的唯一入口，集中管理所有前缀区间和名称关键词知识。

### 设计原则

- **code_utils 只提供底层原语**：基于代码前缀/名称关键词的纯技术判定，无业务上下文
- **业务层可组合使用**：category/penetration/market_value 等模块组合多个原语 + 账户上下文做业务分类
- **不允许自行实现**：任何模块不得出现 `code.startswith(("6", "0", "3"))` 或 `"QDII" in name.upper()` 等判定，必须调用 code_utils

### 函数清单

| 函数 | 类型 | 用途 |
|------|------|------|
| `is_a_share_code(code)` | 前缀 | A 股（60/68/00/30/8 开头） |
| `is_exchange_fund_code(code)` | 前缀 | 场内基金/ETF（5/1 开头） |
| `is_hk_stock_code(code)` | 前缀 | 港股通（5 位数字） |
| `get_exchange_prefix(code)` | 前缀 | sh/sz/bj 交易所前缀 |
| `get_push2_secid(code)` | 前缀 | push2 API secid 参数 |
| `is_qdii_by_name(name)` | 名称 | QDII 标识识别 |
| `is_qdii_extended(name)` | 名称 | QDII + 隐式海外基金（纳斯达克/标普等） |
| `is_etf_by_name(name)` | 名称 | ETF 标识识别 |
| `is_etf_by_name_or_code(name, code)` | 名称+代码 | ETF 识别（名称 + 代码 5/1 开头双维度） |
| `is_bond_related_by_name(name)` | 名称 | 债券基金识别（严格版，不含单字"债"） |
| `is_bond_fund_by_name(name)` | 名称 | 债券基金识别（宽松版，含可转债） |
| `is_index_link_by_name(name)` | 名称 | 指数联接基金识别 |
| `is_index_fund_by_name(name)` | 名称 | 场外指数/被动型基金识别 |
| `is_offsite_fund(account)` | 名称 | 场外基金账户（基金/支付宝/微信/银行） |
| `is_money_fund_by_name(name)` | 名称 | 货币基金识别 |
| `is_fund_holding(name, code, account)` | 复合 | 持仓是否需要基金业绩分析 |


---

## 数据源一览

| 用途 | 主链路 API | 备用链路 | Provider 文件 |
|------|-----------|---------|-------------|
| 场内 A 股/ETF 实时价 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `tencent.py` / `sina.py` |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` | `eastmoney.py` |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — | `tiantian.py` |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — | `tiantian.py` |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `tencent.py` |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析） | 腾讯财经 `qt.gtimg.cn` | `sina.py` |
| 财经新闻（新浪） | 新浪财经 `feed.mix.sina.com.cn` | — | `sina_news.py` |
| 财经新闻（东方财富） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — | `eastmoney_news.py` |
| 财经新闻（财联社） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — | `cls_news.py` |
| 财经新闻（华尔街见闻） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives`（JSON API，无需鉴权） | — | `wallstreetcn_news.py` |
| 财经新闻（akshare） | akshare 封装：财新网 + CCTV | — | `akshare_news.py` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com` 三级行业 + 概念板块 | 行情页 `quotedata` 解析（仅行业，无概念） | `eastmoney_industry.py` / `eastmoney_industry_rest.py` |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — | `akshare_extras.py` |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — | `akshare_extras.py` |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — | `akshare_extras.py` |
| 基金经理数据 | 天天基金 `fundf10.eastmoney.com` 经理列表 HTML 解析 | 档案页回退 | `fetcher/fund_manager.py` |

> 指数数据由 `fetcher/index.py` 直调 Provider，**不走 Provider Chain**。双链路自动 fallback：A 股指数腾讯→新浪，美股指数新浪→腾讯。双链路均失败时降级过期缓存。

> 各新闻源的完整端点格式见 [需求文档 §4 — 数据源](requirements.md#4-数据源) 及 [§4.1 DataSourceRegistry](requirements.md#41-datasourceregistry-数据源注册中心v032)。
>
> 新闻数据的编排/处理层由 `news_aggregator.py`（多源聚合去重）、`news_correlator.py`（持仓关联分析）、`news_keywords.py`（关键词提取）、`news_sources.py`（源元数据定义）4 个模块组成，位于 `providers/` 下，与上述 Provider 分离。

---

## 缓存设计

### 策略概览

缓存统一存放在 `data/cache/` 目录，由 `cache/` 子包提供泛用键值对存储接口。完整 TTL 表（23 种类型，含 B 系列 4 模块 + F 迭代 2 模块）及文件名模式见 [需求文档 §5.5 — TTL 明细](requirements.md#55-ttl-明细)。

#### 行业/概念缓存

| 文件名 | 用途 | 默认 TTL | 清除方式 |
|--------|------|---------|---------|
| `industry_{code}.json` | 单只证券的行业分类和概念板块归属 | 14 天 | 菜单 [1] 清理或过期自动清理 |

### 原子写入

`cache/` 和 `config/` 子包共享 `tempfile.mkstemp` + `os.replace` 模式：
- 先通过 `tempfile.mkstemp` 写临时文件，成功后 `os.replace` 原子替换原文件
- 防止断电/崩溃导致文件截断（半写文件）
- 缓存文件 PermissionError 时自动降级到直接写入（Windows 兼容）
- 磁盘满时自动回退到 gzip 压缩以节省空间

### 文件损坏恢复

- `_read_cache_data()` 解析失败时自动 `os.remove` 损坏文件
- 记录 WARNING 日志，下次调用时重新拉取

### 并发安全

- `os.replace` 保证读取方不会看到半写文件
- 多线程同时 `get()` 同一 key 可能产生 TOCTOU 空窗（两线程均认为缓存过期，均拉取 API），但通过 `_write_atomic` 保证同时写入时只有一个生效

### 路径安全

- `_cache_path(key)` 对 key 做 `replace("..", "_")` 防目录穿越
- 缓存目录不存在时 `os.makedirs(dir, exist_ok=True)` 自动创建
- 项目根路径使用 **标记文件查找法**（`constants.py:_find_project_root()`）：
  - 从 `src/python/constants.py` 所在目录向上逐层搜索 `pyproject.toml` 或 `.git`，找到即停
  - 完全**不依赖目录树深度**，重构移动文件不会导致路径偏移
  - 安全上限 20 层，未找到时按当前深度兜底
  - 所有需定位项目根路径的模块统一从 `constants.PROJECT_ROOT` 导入

### 大文件 gzip 压缩

- `set()` 中数据 ≥ 100KB 时自动使用 `.json.gz` 压缩
- 节省约 80-90% 磁盘空间（`profit_forecast` 等全量数据受益最大）
- 读取时透明解压（`_read_cache_data()` 根据后缀自动判断）

### 缓存分组机制

通过 `registry.py` 的 `cache_groups` 字段定义分组：
- **preload（6 模块）**：price, index, llm_global_macro, llm_expert_review, llm_health_check, llm_penetration_deep → 菜单 `[2]` 触发清除
- **refresh（11 模块）**：fund_perf（基金业绩排名）, fund_hold, industry, news, llm_news_correlation, profit_forecast, sector_flow, dividend, fund_benchmarks（基金业绩基准）, fund_manager（基金经理数据）, fund_overlap（持仓重合度）→ 菜单 `[1]` 触发清除
- **独立模块**：tracking, calendar, fund_concentration（集中度历史）, fund_style_snapshot（风格快照）→ 无分组保护，不被菜单缓存命令误删
- **F 迭代独立缓存**：history_stock（历史 K 线，TTL=CACHE_WEEKLY）, history_fund_otc（历史净值，TTL=CACHE_MONTHLY）→ 无分组保护，通过 Provider Chain `_fetch_with_incremental_fallback` 自动管理

### 指纹驱动失效机制

文件名中嵌入 **MD5 指纹哈希**，输入源数据变化时缓存键自动不匹配，等效于缓存未命中：

| 指纹类型 | 指纹来源 | 作用范围 |
|---------|---------|---------|
| **指数指纹** | A股 + 美股指数行情 | `profit_forecast_*`、`sector_flow_*` |
| **代码列表指纹** | 持仓+穿透 A 股代码排序 MD5 | `dividend_*` |
| **输入参数指纹** | 新闻源参数 + 关键词 | `news_*` |
| **输入数据指纹** | 指数+持仓汇总/持仓结构 | `llm_global_macro_*`、`llm_expert_review_*`、`llm_health_check_*`、`llm_penetration_deep_*`、`llm_news_item_*` |

> **TTL 兜底**：即使指纹未变，缓存文件仍有 TTL 到期自动刷新。
> **LLM 指纹策略**：智囊团深度复盘、持仓体检报告、穿透深度分析排除行情波动字段（price/change_pct），仅品种/份额/成本变化时失效。
> **精确键名**（`fund_benchmarks.json`、`holdings_tracking.json`、`trading_calendar.json`、`fund_manager_snapshot.json`、`fund_concentration_snapshot.json`、`fund_style_snapshot.json`）不带指纹后缀，仅在 TTL 到期后刷新。

---

## 功能模块详解

### 资产穿透TOP10

- `compute_penetration_top10()` 纯计算函数，不依赖 openpyxl
- 分类逻辑（QDII/ETF/联接/债券/主动/直接持股）基于代码前缀 + 名称规则，所有底层判定委托至 `code_utils`（见[代码类型判定中心化](#代码类型判定中心化)）
- 板块分类 `classify_sector()` 使用静态关键词映射，同时支持 API 行业数据补充
- 调用 `batch_fetch_industry_data()` 为穿透结果注入行业信息（覆盖静态关键词的局限）

### 财经新闻热点与持仓关联分析

- 5 源并行获取（ThreadPoolExecutor max_workers=5）
- 新闻缓存 `news_{md5}.json`，15 分钟 TTL，MD5 指纹含关键词/参数
- 关键词提取：持仓名称片段 + 代码 + 穿透资产 + **行业名称 + 概念板块**
- 关键词富化 4 种类型：持仓(0) → 穿透(1) → 概念(2) → 行业(3)
- 概念类型：来源为东方财富 push2 API 的行业分类和概念板块
- HTML 富化显示：蓝(持仓) / 紫(穿透) / 橙(概念) / 灰(行业)
- LLM 二次关联分析（可选）：`enabled_llm.news_correlation` 配置开启
- **召回策略**：每个新闻源原始获取量 `per_source = max(500, news_top_count × 2)`，保证去重后候选充足；最终截取 `news_top_count` 条按关联度排序输出

### 行业/概念数据流

```
持仓列表 + 穿透资产
    ↓ 提取所有唯一代码
batch_fetch_industry_data(codes)
    ↓ API / 缓存
industry_{code}.json
    ↓
build_news_data():
  1. 行业名/概念名 → 追加到关键词列表 → 提高新闻匹配率
  2. industry_data → _build_keyword_lookup() → "concept" 类型条目
  3. _enrich_keywords_for_item() → 显示 "XX[概念]"
    ↓
穿透模块:
  4. batch_fetch_industry_data() → 覆盖 sector 字段 → 板块列显示 API 数据

penetration_sector = fetch_industry_data(code).industry  // API优先
                  or classify_sector(name, code)         // 关键词回退
```

### Provider Chain 路由与 fallback

`src/python/providers/` 下的 Provider 按数据类型的优先级定义在 `fetcher/chain.py:_DEFAULT_CHAINS` 中（`price_stock`→`tencent`,`sina`；`price_fund_otc`→`eastmoney`；`industry`→`eastmoney_industry`,`eastmoney_industry_rest` 等），`fetcher/price.py` 的 `fetch_market_data()` 通过 `_fetch_with_fallback()` 遍历 Provider Chain：

```
Provider Chain 注册表（provider_registry.py:DataSourceRegistry）
    ↓
路由此类型首个 Provider（如 price_stock→tencent）
    ↓ 成功? → 返回并缓存
    ↓ 失败?
    ↓
递补下一 Provider（如 price_stock→sina）
    ↓ 成功? → 返回并缓存
    ↓ 失败?
    ↓
尝试最近 `CACHE_WEEKLY`（7天）内过期缓存（降级）
```

- **默认优先级**硬编码在 `fetcher/chain.py:_DEFAULT_CHAINS` 中，`preferred_provider` 可在 `config.json` 中手动将某类型首选调整到链首
- 失败检测：空返回、HTTP 错误、JSON 解析异常均视为失败触发递补
- 全链路失败 → 尝试过期缓存降级 → 仍失败则抛异常由调用方处理
- **价格缓存收市后新鲜度验证**（`fetcher/price.py:_price_cache_fresh`）：盘后首次请求时校验缓存 `price_date` 是否为当前交易日。若盘中因 Tencent 不可用降级写入 Sina 数据（非收盘价），或盘中缓存残留上一交易日数据，收市后自动清除该残留缓存并强制重走 Provider Chain，确保收盘价更新。

### Provider Chain 三层熔断架构

Provider Chain 熔断由 **DataSourceRegistry 单例**（`src/python/provider_registry.py`）统一管理熔断状态、会话缓存和获取策略：

```
┌──────────────────────────────────────────────────┐
│  DataSourceRegistry（单例，双锁线程安全）            │
│                                                    │
│  ┌─ Provider 熔断器 ──────────────────────────┐    │
│  │  • register_provider(name, tier, fallback)  │    │
│  │  • record_success / record_failure(provider) │    │
│  │  • is_circuit_broken / is_chain_broken      │    │
│  │  • 连续 3 次 → 熔断 300s → 冷却期满自动恢复 │    │
│  └────────────────────────────────────────────┘    │
│                                                    │
│  ┌─ 会话级缓存（C4 约束） ─────────────────────┐    │
│  │  • session_cache_get/set(domain, code)        │    │
│  │  • _NOT_FOUND sentinel 区分 None vs 未缓存    │    │
│  │  • 2000 条/domain LRU 淘汰                    │    │
│  │  • domain:"industry"/"industry_rest"/         │    │
│  │           "extended"/"price"                   │    │
│  └────────────────────────────────────────────┘    │
│                                                    │
│  ┌─ 策略选择器 ───────────────────────────────┐    │
│  │  • get_effective_strategy(code_type, chain,  │    │
│  │    market_open) → LIVE_FETCH/CACHE_ONLY      │    │
│  │  • QDII/港股恒为 LIVE_FETCH                  │    │
│  │  • 交易时段外 → CACHE_ONLY                    │    │
│  │  • 全链熔断 → CACHE_ONLY 降级                │    │
│  └────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

**三层熔断架构（实现于 DataSourceRegistry）：**

- **第 1 层 — 熔断预检**：`is_chain_broken(chain)` 检查 chain 中所有 provider 是否全部熔断。`market_value.py` 在批量请求前调用 `get_effective_strategy` 判断是否全链降级到 CACHE_ONLY，避免无效 HTTP 请求。
- **第 2 层 — Provider 级熔断**：`_fetch_with_fallback` 中每次调用前检查 `is_circuit_broken(provider)`。仅传输级异常（超时/断连/DNS/5xx）触发 `record_failure` 计入熔断计数器；代码级空结果（API 正常返回 None）不计入。
- **第 3 层 — 冷却试探恢复**：熔断 300s 后 `is_circuit_broken` 自动解除标记并重置 `consecutive_failures=0`，下次调用即为试探。

**与 LLM Circuit Breaker 的差异：**

| 维度 | Provider Chain 熔断 | push2 行业/概念熔断 | LLM Circuit Breaker |
|:-----|:-------------------|:--------------------|:--------------------|
| 作用域 | 数据 provider（price/industry 等） | push2 行业分类/概念板块 API | LLM API endpoint |
| 实现位置 | `provider_registry.py` DataSourceRegistry | `provider_registry.py` DataSourceRegistry | `llm/circuit_breaker.py` |
| 冷却时长 | 300s | 300s | 60s |
| 试探次数 | 冷却期满放行一次 | 冷却期满放行一次 | 半开状态放行一次 |
| 恢复条件 | 试探成功 → record_success | 试探成功 → record_success | 半开成功 → 关闭熔断 |

**Chain 自动注册：** `fetcher/chain.py` 在模块加载时自动调用 `get_registry().register_default_chains()`，从 `_DEFAULT_CHAINS` 配置注册所有 provider 和 chain。`get_chain(data_type)` 从 registry 返回对应 chain 列表供策略选择器使用。

**消费方感知：** 对 batch 调用方透明。batch 场景日志从 N 条"已被熔断，跳过"降级为 1 条入口 WARNING + 1 条熔断降级 LOG。

### Fetcher 调度架构

`src/python/fetcher/` 各模块按数据类型独立封装，由 `handlers_report.py` 或 `handlers_cache.py` 的菜单命令统一编排调用：

| 模块 | 功能 | 依赖的 Provider | 缓存类型 |
|:-----|:-----|:---------------|:---------|
| `price.py` | 股票/ETF 最新价（腾讯+新浪）| tencent, sina | `price_*` |
| | 场外基金净值 | eastmoney | `price_*` |
| `index.py` | A 股/美股指数 | tencent, sina | `index_*` |
| `fund.py` | 基金排名/持仓/基准 | tiantian | `fund_perf_*`, `fund_hold_*`, `fund_benchmarks` |
| `fund_manager.py` | 基金经理数据 | tiantian HTML 解析 | `fund_manager_*`, `fund_manager_snapshot` |
| `industry.py` | 行业分类+概念板块 | eastmoney_industry, eastmoney_industry_rest | `industry_*` |
| `chain.py` | Provider 优先链定义 + fallback 路由 | —（纯路由逻辑） | — |
| `portfolio_history.py` | 组合历史走势计算器（F2） | —（内部路由到 history_stock/history_fund_otc） | `history_stock_*`, `history_fund_otc_*` |

- **并行预热**：`preload_cache()` 对 preload 组使用 `ThreadPoolExecutor` 并行获取，减少串行等待
- **菜单驱动**：菜单 [1] 和 [2] 分别清除 + 重拉 refresh 和 preload 组，复用 fetcher 模块的预热入口
- **指数独立**：`fetcher/index.py` 直调 Provider，不走 Provider Chain（双链路 fallback 硬编码在此）

### 报告生成管线

`src/python/report/` 采用 编排层（`excel_generator.py` / `html_writer.py`）+ 内容层（各页签写入器）架构：

```
handlers_report.py（菜单触发）
   │
   ├─ info 数据准备（并行预热 + 计算）
   │     └─ report_prepare() 收集所有数据 → info 字典
   │
   ├─ F 迭代数据获取（菜单 L/B）
   │     ├─ F1 快照对比：SnapshotHoldings → load_latest() → HistoryDiff.compute() → save()
   │     ├─ F2 历史走势：PortfolioHistoryCalculator.get_combined_timeseries()（as-if 模拟）
   │     └─ 数据注入：f_context（diff 摘要）→ Excel；history_data（走势）→ HTML
   │
   ├─ Excel 管线
   │     excel_generator.py（编排器 98 行）
   │       → excel_sheet_factory.py（页签创建）
   │       → excel_module_loader.py（模块动态加载）
   │       → excel_market_data.py（行情+指数解析）
   │       → excel_content_sheets.py（穿透/基金业绩/股指期货）
   │       → excel_news_warning.py（新闻+智能预警）
   │       → excel_b_series.py（B 系列 4 模块）
   │       → excel_llm_usage.py（LLM 分析章节+用量页签）
   │       → summary.py / summary_llm_usage.py /
   │         market_value.py + market_value_sheet.py / category.py /
   │         penetration.py / penetration_sheet.py / fund_performance.py /
   │         news_correlation.py / early_warning.py / llm_content.py /
   │         fund_manager_sheet.py / fund_overlap_sheet.py /
   │         fund_concentration_sheet.py / fund_style_analysis.py /
   │         fund_style_sheet.py（各页签写入器，B 系列 4 模块采用计算引擎+写入器分离模式）
   │     → excel_writer.py（通用写入）+ styles.py（样式）
   │
   └─ HTML 管线
         html_writer.py → html_builders.py（数据构建器）
         → tmpl/report_template.html（Jinja2 模板）
```

- **Excel 页签写入器**：各 `_write_*_sheet()` 函数接收 `info` 字典 + `writer`，独立负责单个页签的内容和样式，互不依赖
- **条件渲染**：B 系列基金分析模块（`enable_b_series` 标志）、智能预警页签（菜单 B/L）、LLM 分析章节（菜单 L）在 `info` 中无对应数据时自动跳过
- **汇总页（页签 1）** 由 `summary.py` 的 `write_summary_sheet()` 独立写入。LLM API 用量页签由 `summary_llm_usage.py` 的 `write_llm_usage_sheet()` 写入（从 summary.py 拆分），两者通过 summary.py 的 re-export 保持向后兼容

### 数据降级治理

`src/python/report/data_status.py` 提供数据状态追踪基础设施，被 Excel 和 HTML 两端共享：

- **`DataStatusItem`（TypedDict）**：`{"available": bool, "tier": str, "message": str}` — 单一数据源的可用状态
- **`STATUS_MESSAGES`（dict）**：Excel 和 HTML 两端共享的常量字典，保证消息一致性。按数据源类型分 T2（⚠ 前缀）和 T3/T4（ℹ 前缀）两类
- **`TIER_PREFIX`**：`{"T2": "⚠", "T3": "ℹ", "T4": "ℹ"}` — 按层级自动选择前缀符号
- **`DegradationTracker`**：双信号降级阈值控制器（连续失败计数 + 缓存陈旧度），支持跨会话持久化到 `.degradation_state.json`

Excel 端降级辅助函数（`category.py`等模块中使用）：

- **`_write_placeholder(ws, message)`**：数据为空时写入灰色占位文本（合并单元格），替代隐藏页签行为
- **`_write_data_status_foot(ws, status)`**：在页签底部追加数据源状态摘要行，根据 tier 自动匹配前缀

HTML 端降级机制：

- **`_safe_build_data_status(builder_fn, *args)`**：异常安全的 `DataStatus` 构建包装器，构建失败返回空状态
- **`render_data_status(status)` Jinja2 宏**：在 `report_template.html` 中条件渲染状态摘要区域

### 持仓读取与列校验

`reader.py` 基于 openpyxl 解析持仓 xlsx：

- `load_holdings(filepath)` 遍历所有 worksheet，每 worksheet = 一个账户
- 列校验规则：必须存在且恰好 4 列（名称、代码、持仓份额、每份成本），列名匹配忽略首尾空格
- 数据清洗：代码自动去除后缀（`.SH`/`.SZ`/`.OF`），份额/成本转为 float，空行跳过
- 多文件选择：持仓目录下多个 xlsx 时弹出 TUI 选择器（`tui_handlers.py` 中 `_select_holdings_file()`）

### B 系列：基金深度分析模块

B 系列 4 个模块（fund_manager / fund_overlap / fund_concentration / fund_style）通过 `enable_b_series` 标志控制条件渲染，跟随 `include_news`（菜单 B/L 时触发）。

#### 基金经理变更监控（B2）

`fund_manager_analysis.py` 基于快照比对检测基金经理变更：

- **数据源**：天天基金 `fundf10.eastmoney.com` 基金经理列表（HTML 解析），获取当前基金经理姓名 + 任职起始日
- **快照机制**：`fund_manager_snapshot`（精确键名，无指纹），每日更新，存储每个基金最后一次检查时的经理列表
- **窗口期计算**：任职起始日距今天数：
  - ≤30 天 → 🔴 紧急
  - ≤90 天 → ⚠️ 关注
  - ≤180 天 → ⚠️ 关注（与 90 天同级，用于 91-180 天范围内的变更提示）
  - 首次运行无快照 → 📋 首检（自下次起跟踪）
  - 无变更 → ✅ 正常
- **持股模式**：每个基金独立判断，互不干扰

#### 持仓重合度矩阵（B3）

`fund_overlap.py` 双指标持仓重合度计算：

- **Jaccard 系数**：`|A ∩ B| / |A ∪ B|`
- **重叠率**：`|A ∩ B| / min(|A|, |B|)`
- **最终重合度**：取两者 max（避免分母差异造成的低估）
- **热力图着色**（Excel 条件格式）：≥50% 红底白字、30-50% 橙底白字、15-30% 黄底黑字、>0 绿底黑字、0% 无着色
- **配对明细表**：按重合度降序排列，含共同标的数 + 共同标的名称列表
- **触发条件**：持仓中基金数量 ≥ 2 只

#### 持仓集中度监控（B4）

`fund_concentration.py` 基于持仓 TOP N 占比 + 环比变化：

- **算法**：取每只基金持仓中权重最大的前 3/5/10 只标的，加总占比
- **环比检测**：`fund_concentration_snapshot` 历史快照比对，记录前 10 占比的上期值
- **预警规则**（与环比独立叠加）：
  - 前 10 占比环比 +20% → 🔴 紧急
  - 前 10 占比环比 +10% → ⚠️ 关注
  - 当前前 10 占比 > 80% → ⚠️ 关注
  - 首次运行 → 📋 首次（记录基线）
- **环比变化箭头**：↑/↓ 标识方向

#### 基金风格分析（B5）

`fund_style_analysis.py` 基于持仓个股市值 + PE 数据的加权风格判定：

- **数据源**：东方财富 push2 API（`f20`=总市值、`f9`=动态 PE）；三级降级链路：push2（精确）→ Tencent 扩展字段（可靠，`qt.gtimg.cn` f46=总市值、f40=PE TTM）→ 代码前缀估算（兜底）
- **市值判定**：>500 亿=大盘、100~500 亿=中盘、<100 亿=小盘
- **估值判定**：PE / 行业平均 PE，<70%=价值、>130%=成长、其余=混合
- **加权投票**：最终风格 = 市值权重最大的 size + 估值权重最大的 style
- **漂移检测**：网格曼哈顿距离 = |Δsize| + |Δstyle|（0~4），0=无、1=轻度、2=中度、≥3=严重
- **三级降级**：push2（一级，精确）→ Tencent 扩展字段（二级，可靠，Tencent 数据不标注估算）→ 代码前缀（三级，兜底）：60xxxx→大盘、000/002→中盘、300/688→小盘、4/8→小盘；估值方向统一"混合"+备注"估算风格"
- **性能优化**：会话级缓存委托 DataSourceRegistry session_cache（domain="extended"）跨基金复用，同一股票仅首次 HTTP；Tencent 二级降级基于 registry 熔断器（provider="tencent_style"），避免网络不可达时逐只等待超时
- **独立快照**：`fund_style_snapshot` 精确键名，月级 TTL，不受菜单缓存命令影响

### 报告序号可配置

报告 18 个模块的序号/显示名称由 `registry.py` 注册表驱动，支持用户通过 `config.json` 自定义序号和排列顺序。

#### 设计目标

- 消除 HTML 模板中 27 处硬编码序号和导航链接
- 支持用户自定义各模块的显示序号和出现顺序
- `llm_usage` 始终强制末位（对用户透明）
- 未配置的模块自动按默认顺序排列

#### 注册表结构

`registry.py` 中定义 `_REPORT_SECTION_DEFAULT` 列表：

| 字段 | 类型 | 说明 |
|:-----|:----:|:-----|
| `key` | str | 模块标识，如 `"summary"`、`"fund_manager"` |
| `name` | str | 显示名称，如 `"投资分析汇总"`、`"基金经理变更监控"` |
| `number` | int | 默认序号 |
| `type` | str | 可见性类型：`always` / `history` / `b_series` / `news` / `llm` |
| `data_flag` | str\|None | 运行时数据标志键名，`None` 表示始终可见 |

**可见性类型：**

| 类型 | 数量 | 含义 | data_flag |
|:-----|:----:|:-----|:----------|
| `always` | 5 | 始终显示，不依赖任何数据条件 | `None` |
| `history` | 2 | 始终显示（同 always），数据不可用时显示占位文本 | `history_data` |
| `b_series` | 4 | 仅当对应基金分析数据可用时显示 | `manager_data` / `overlap_data` / `concentration_data` / `style_data` |
| `news` | 2 | 仅当启用新闻功能时显示 | `include_news` / `early_warnings` |
| `llm` | 5 | 仅当 LLM 功能启用时显示 | `llm_enabled` |

#### 配置接口

`config.json` 新增 `report_section_order` 字段（字典格式：`{"模块标识": 序号}`）：

```json
{
  "report_section_order": {
    "fund_manager": 1,
    "summary": 2,
    "fund_performance": 5
  }
}
```

合并规则（`get_report_section_order(config)`）：

1. 无配置或配置为空 → 返回完整 18 项默认顺序
2. 用户配置的模块使用配置序号，其余保持默认序号
3. 已配置模块排在前（按序号升序），未配置模块按默认顺序排后
4. `llm_usage` 始终固定在最后一位

#### section_visible_dict 统一可见性控制

`html_writer.py` 在渲染前预计算一个 `section_visible_dict` 字典，包含每个模块的可见性（`True`/`False`），通过以下数据标志判断：

```
raw_data_flags = {
    # B 系列：返回非 None = 模块已启用 → section 始终可见（空数据时显示占位）
    "manager_data":       manager_analysis is not None,
    "overlap_data":       overlap_matrix is not None,
    "concentration_data": concentration_analysis is not None,
    "style_data":         style_analysis is not None,
    "include_news":       include_news,
    "early_warnings":     bool(early_warnings),
    "llm_enabled":        llm_enabled_flag,
    # F 迭代：history 类型 sections 始终可见（数据不可用时显示占位文本）
    "history_data":       history_data is not None,
}
```

`always` 类型模块的 `data_flag` 为 `None`，默认 `True`。

#### Jinja2 全局函数

`_jinja_section_visible(key)` 在模块级注册为 `_ENV.globals["section_visible"] = lambda key: False`（fail-closed 默认值），渲染时由 `write_html_report` 通过 `render(section_visible=sv_fn, ...)` 传入 context 变量覆盖该默认值。模板中通过 `{% if section_visible("fund_manager") %}` 调用，Jinja2 的 context > globals 解析顺序自动覆盖。

**不写入 `_ENV.globals` 作为渲染期通信渠道**（参见约束 C14）。


#### HTML 模板重构

**导航栏：** 使用 `section_order` 动态循环生成，只渲染当前可见的模块：
```jinja
{% for sec in section_order %}
  {% if section_visible(sec["key"]) %}
    <a href="#sec-{{ sec['key'] }}">{{ sec["number"] }}、{{ sec["name"] }}</a>
  {% endif %}
{% endfor %}
```

**CSS order 视觉排序：** `.container { display: flex; flex-direction: column; }`，每个模块的 `<div class="section">` 使用 `style="order: {{ section_numbers['key'] }};"` 属性，在不改变 DOM 结构的前提下实现视觉重排。

**章节标题：** 硬编码中文序号替换为 `{{ section_numbers['key'] }}、...`。

**条件渲染：** 所有模块的最外层可见性条件从分散的 `{% if manager_analysis and ... %}`、`{% if llm_enabled %}` 等形式统一为 `{% if section_visible("fund_manager") %}` 等。

---

## LLM 客户端技术要点

`src/python/llm/` 包拆分架构（原 `llm_client.py` 解耦为 12 子模块，含 skeleton.py 共享骨架）：

| 模块 | 职责 |
|------|------|
| `api.py` | API 调用路由 (Claude/OpenAI)、重试、截断检测、熔断器集成 |
| `api_base.py` | 共享 API 骨架（`_attempt_api_call`、`_extract_content`、`_process_success_response`、Token 日志） |
| `prompts.py` | System Prompt 常量与构建函数 |
| `generators_orchestrator.py` | LLM 生成编排（4+1 模块，线程池并行，并发数由 `llm_max_concurrency` 配置） |
| `generators_news.py` | 新闻关联分析的 LLM 调用逻辑（关键词提取、召回、LLM 二次分析） |
| `pricing.py` | 模型定价加载、费用估算 |
| `session.py` | 会话用量累计、追踪 |
| `circuit_breaker.py` | 端点熔断器 |
| `fingerprint.py` | 各种缓存指纹计算 |
| `markdown.py` | Markdown→HTML 渲染 |
| `skeleton.py` | 共享生成骨架（_generate_llm_content / _is_llm_module_enabled / _generate_llm_module / _run_batch_mode） |

`__init__.py` 导出所有公共 API 保持向后兼容。

- **统一入口** `_call_llm()` 按 `provider` 路由到 `_call_claude()` 或 `_call_openai()`
- **`_call_llm_with_retry()`** 共享重试/超时/错误处理骨架
- **`_generate_llm_content()` / `_generate_llm_module()`** 共享骨架函数（`skeleton.py`），封装缓存检查 + 调用 + markdown→HTML + 写入的 85% 公共逻辑
- **`generate_global_macro()` / `generate_expert_review()`** 仅保留 prompt 构建 + 配置解析，其余委托 `_generate_llm_module()`（`skeleton.py`）
- **注册表键名派生**（`registry.py`）：每个 LLM 模块的 `settings_suffix` 自动派生出 9 个 `llm_settings.json` 合法键名：`model_`、`temperature_`、`timeout_`、`cache_enabled_`、`max_tokens_`、`system_prompt_`、`thinking_enabled_`、`thinking_budget_`、`reasoning_effort_`。`news_correlation` 外的模块额外增加 `output_brief_`。所有键名由注册表统一校验，新增模块只需在注册表添加一行。

### Extended Thinking

`_call_claude()` 通过 `llm_config` 参数读取 `thinking_enabled_{模块}` 配置，为 Claude API 注入 `thinking` payload 以实现深度推理。

**关键逻辑：**
- `thinking_budget` 与 `max_tokens` 是独立参数：前者控制内部推理 token（不可见），后者控制最终输出 token
- API 约束：`thinking_budget` ≥ `max_tokens + 1024`，代码中 `_call_claude()` 自动兜底不足时补到 `max_tokens + 4096`
- Extended Thinking 与 `temperature` 互斥，开启后自动 `payload.pop("temperature", None)`
- 模块后缀通过 `config_field` 解析：`config_field.replace("max_tokens_", "")` → `"global_macro"` / `"expert_review"` / `"news_correlation"`
- 推荐仅在智囊团深度复盘（expert_review）开启

**payload 示例（开启后）：**
```python
{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 8192,
    "thinking": {"type": "enabled", "budget_tokens": 16000},
    "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
    "messages": [{"role": "user", "content": user}],
}
```

### DeepSeek / Effort 模式

DeepSeek V4+（`deepseek-v4-*` / `deepseek-chat`）通过 Anthropic 兼容端点支持 Extended Thinking，但不使用 `budget_tokens`，而使用 `output_config.effort` 定性控制思考深度：

```python
payload["thinking"] = {"type": "enabled"}
payload["output_config"] = {"effort": "high"}   # "low" / "medium" / "high" / "max"
```

模型名大小写敏感：代码按全小写前缀匹配（`deepseek-v4-`），文档示例统一使用 `deepseek-v4-flash`。

### Prompt Caching（Anthropic 专属）

`_call_claude()` 中 system prompt 使用数组格式 + `cache_control: {"type": "ephemeral"}`。同一 system prompt 在 **5 分钟内**重复使用时，输入 token 扣费大幅降低（缓存写入 ×1.25 价格，命中 ×0.1 价格）。无需任何配置，程序自动启用。

### 熔断器（Circuit Breaker）

`llm/circuit_breaker.py` 实现端点级熔断：连续 3 次失败后熔断 60 秒，半开状态允许 1 次探测。通过 `_cb_is_open()` / `_cb_record_failure()` / `_cb_record_success()` 暴露接口，`_call_llm_with_retry()` 在每次请求前检查熔断状态。

### 输出截断自动重试

`_generate_llm_content()`（`skeleton.py`）在收到 LLM 响应后检测输出中是否含 `_TRUNCATION_MARKER`（`【⚠ 输出已被截断`）。若存在，说明输出达到 `max_tokens` 上限被截断不完整，自动以 `max_tokens × 1.5`（`_AUTO_INCREASE_FACTOR`）重试一次，并输出进度提示。二次截断则保留第一次结果并在末尾追加截断警告。

### 内容过滤安抚重试

`_call_llm_with_retry()`（`api.py`）在 `_process_success_response()` 返回空内容（`result == ""`，可能被 API 内容过滤机制拦截）时，追加 `_CONTENT_FILTER_RECOVERY` 安抚指令到 system prompt 尾部并重试一次：

```
"\n\n注意：请确保你的回答包含实质性的分析内容。"
"如果前一版本未输出任何内容，请提供完整的分析结果。"
"所有数据均基于公开市场信息，请客观分析即可。"
```

安抚成功后返回重试结果；失败则继续尝试 fallback provider（若配置）。

### 会话级 Token 追踪与用量展示

#### 数据收集架构

`llm/session.py` 维护全局线程安全（`threading.Lock`）的 `_session_usage` 字典，作为单个报告生成会话中所有 LLM 调用的累计存储器。

**数据结构：**
```python
_session_usage: dict[str, Any] = {
    "input_tokens": 0,          # 累计输入 token
    "output_tokens": 0,         # 累计输出 token
    "cache_hit_tokens": 0,      # 累计缓存命中 token
    "total_cost": 0.0,          # 累计费用
    "currency": "CNY",          # 货币标识
    "model": "未指定",           # 最近使用的模型名
    "models": [],               # 所有出现过的模型名（去重）
    "call_count": 0,            # API 调用次数（缓存命中不计入）
    "per_module": {},           # 按模块细分
}
```

**模块级记录（`per_module`）** — 每个 LLM 子模块一个条目，共 5 个键：

| 模块键 | 覆盖范围 | 说明 |
|:------|:---------|:-----|
| `global_macro` | 全球政经局势 | 始终启用 |
| `expert_review` | 智囊团深度复盘 | 始终启用 |
| `health_check` | 持仓体检报告 | — |
| `penetration_deep` | 穿透深度分析 | — |
| `news_correlation` | 新闻 LLM 关联分析 | 仅 `enabled_llm.news_correlation = true` 时启用 |

每个模块条目包含：
```python
{
    "model": str,              # 实际使用的模型名
    "input_tokens": int,       # 该模块输入 token
    "output_tokens": int,      # 该模块输出 token
    "cache_hit_tokens": int,   # 缓存命中 token
    "cached": bool,            # 是否来自缓存（无实际 API 调用）
    "thinking": bool,          # 是否启用 Extended Thinking
    "cost": float,             # 该模块费用估算
    "endpoint": str,           # API 端点 URL
}
```

#### 数据收集流程

```
API 调用响应 (usage dict)
    │
    ├─► _process_success_response()          [api.py]
    │       │
    │       ├─► _track_session_usage()        [session.py]
    │       │     ├─ input_tokens += usage.input_tokens
    │       │     ├─ output_tokens += usage.output_tokens
    │       │     ├─ cache_hit_tokens += cache_read
    │       │     ├─ call_count += 1
    │       │     ├─ models.append(model)     (去重)
    │       │     └─ total_cost += _estimate_cost(...)
    │       │
    │       └─► _record_per_module()          [session.py]
    │             └─ per_module[key] ← {model, tokens, cached=False, ...}
    │
    ├─► _handle_cache_hit()                   [skeleton.py]
    │       └─► _record_per_module()           [session.py]
    │             └─ per_module[key] ← {model, tokens, cached=True, ...}
    │                                           (调用次数不计入 call_count)
    │
    ├─► _precheck_one_cache()                 [generators_orchestrator.py]
    │       └─► _record_per_module()           [session.py]
    │
    └─► _finalize_news_token_usage()          [generators_news.py]
            └─► _record_per_module(key="news_correlation")
```

**覆盖范围说明：**
- 每次 **成功的 API 调用**（包括重试后的成功响应）均触发 `_track_session_usage()` 和 `_record_per_module()`
- **缓存命中**（从缓存文件读取 LLM 结果而非调用 API）仅触发 `_record_per_module()`，标记 `cached=True`，不计入 `call_count`
- **模块失败/禁用**（API Key 未配置、熔断器打开、`enabled_llm.{key}=false`）不产生任何用量数据
- **新闻 LLM 关联分析**（`news_correlation`）由 `generators_news.py` 中 `_finalize_news_token_usage()` 单独汇总，以兼容其在新闻处理流程中的独立缓存和批处理逻辑

#### 用量数据到报告输出

```
_session_usage (dict)
    │
    ├─► format_session_usage()               [session.py]
    │     返回展示用格式化字典：
    │     {
    │       "has_usage": bool,         # 是否有任何调用记录
    │       "call_count": int,         # API 调用次数
    │       "model_display": str,      # "deepseek-v4-flash" 或 "modelA / modelB"
    │       "input_tokens": str,       # 格式化为 "25,432"
    │       "output_tokens": str,
    │       "total_tokens": str,       # 输入+输出
    │       "cache_hit_tokens": str,   # 有条件显示（>0 时）
    │       "cost": float,
    │       "cost_display": str,       # "¥0.0456"
    │       "currency": str,
    │       "per_module": dict,        # 各模块原始数据（由消费方自行格式化为明细表）
    │     }
    │
    ├─► Excel 报告                          [excel_llm_usage.py]
    │      build_llm_usage_sheet()
    │        → get_session_usage()
    │        → format_session_usage()
    │        → write_llm_usage_sheet()    写入独立页签 18（LLM API 用量，不追加到汇总页）
    │
    ├─► HTML 报告                           [html_writer.py + template]
    │      _render_llm_module_info()
    │        → _build_module_info_list()   构建模块明细（含状态标签）
    │        → get_session_usage()
    │        → format_session_usage()
    │        → Jinja2 模板变量：llm_session_usage / llm_module_info / llm_endpoint
    │
    └─► TUI 终端                            [tui_handlers.py]
           _print_llm_session_usage()
             → f"本会话 LLM 累计：{calls} 次调用，{total_tok:,} tokens，费用 {symbol}{cost:.4f}"
```

#### 用量展示与 LLM 分析章节的关系

LLM API 用量页签/章节（页签 18 / HTML 底部）**不是独立的 LLM 生成模块**，而是对同一会话中所有 LLM 分析章节调用量的被动统计汇总。

| 方面 | 设计决策 |
|:-----|:---------|
| **触发条件** | 仅菜单 L（全系列完整版报告），与 LLM 分析章节共进退 |
| **无用量不显示** | 无任何 LLM 调用时（API Key 未配置或所有模块已禁用），该页签/章节整个跳过不渲染 |
| **全缓存场景** | 所有模块均为缓存命中（无实际 API 调用），汇总区标注"无新增 API 调用，数据全部来自缓存"，模块明细表正常显示 |
| **与 LLM 章节的物理位置** | Excel 中作为页签 18（最后一位），HTML 中在所有 LLM 分析章节之后渲染 |
| **新闻 LLM 关联分析** | 当 `enabled_llm.news_correlation = true` 时，其 token 使用量计入 `per_module["news_correlation"]`，与另外 4 个 LLM 主模块在同一明细表中展示 |

#### 展示格式

**汇总区字段（顶部）：**

| 字段 | 数据来源 | 格式 |
|:-----|:---------|:-----|
| API 调用次数 | `call_count` | 整数 |
| 模型 | `models` 去重列表 | `model1 / model2` 格式 |
| 输入 Token | `input_tokens` | 千分位格式化 |
| 输出 Token | `output_tokens` | 千分位格式化 |
| 总 Token | `input_tokens + output_tokens` | 千分位格式化 |
| 缓存命中 Token | `cache_hit_tokens`（>0 显示） | 千分位格式化 |
| 累计费用 | `total_cost` + 货币符号 | `¥0.0456` |

**模块明细表字段（每模块一行）：**

| 列 | 数据来源 | Excel 格式 | HTML 格式 |
|:---|:---------|:-----------|:----------|
| 模块 | 模块键映射中文名 | 文本 | 文本 |
| 状态 | `per_module[key].cached` + 模块失败标记 | 带填充色 | 颜色标签（成功/缓存/失败/禁用） |
| 模型 | `per_module[key].model` | 文本 | 文本 |
| 输入 Token | `per_module[key].input_tokens` | 千分位 | 千分位 |
| 输出 Token | `per_module[key].output_tokens` | 千分位 | 千分位 |
| 缓存命中 Token | `per_module[key].cache_hit_tokens` | 千分位或 `—` | 同左 |
| 费用 | `per_module[key].cost` | 格式化货币或"已计入原调用" | 同左 |
| LLM 缓存 | `per_module[key].cached` | ✓ 或 — | ✓ 或 — |
| Thinking | `per_module[key].thinking` | ✓ 或 — | ✓ 或 — |

**状态标签颜色规范：**

| 状态 | 含义 | Excel 填充色 | HTML 标签色 |
|:-----|:-----|:------------|:------------|
| ✅ 成功 | 有实际 API 调用且成功返回 | #E8F5E9（浅绿） | #27ae60（绿） |
| 📦 缓存 | 结果来自缓存文件，无实际 API 调用 | —（默认） | #2e86c1（蓝） |
| ⛔ 失败 | API 调用失败，返回占位文本 | #FFEBEE（浅红） | #e74c3c（红） |
| 🚫 已禁用 | `enabled_llm.{key} = false`，模块被跳过 | #F5F5F5（浅灰） | #95a5a6（灰） |

#### 定价匹配规则

`llm/pricing.py` 中 `_estimate_cost()` 按以下优先级匹配模型定价：

1. 精确匹配（模型全名小写 → 定价表中同名）
2. 前缀匹配（`deepseek-v4-flash-xxx` → `deepseek-v4-flash`）
3. 均不匹配 → 回退到 `MODEL_PRICING` 中的 `"default"` 费率

费用计算（元/百万 token）：
```
费用 = (input_tokens - cache_hit_tokens) / 1_000_000 * input_rate
     + output_tokens / 1_000_000 * output_rate
     + cache_hit_tokens / 1_000_000 * input_cache_hit_rate
```

默认定价表见 `src/python/constants.py:MODEL_PRICING`，用户可通过 `llm_settings.json` 的 `pricing` 字段覆盖。货币符号通过 `pricing.currency` 配置（默认 `CNY → ¥`）。

#### 系统数据缓存统计

LLM 用量页签/章节底部追加"▎数据缓存系统"区域，展示 `cache/` 子包统一管理的进程级缓存命中/未命中/总请求数/命中率。统计范围包括价格、指数、基金净值、基金持仓、基金经理等所有缓存类型。

数据来源：`get_cache_hit_rate()`，报告生成时快照采样。仅在会话中有缓存请求记录（`total > 0`）时渲染。

| 渠道 | 展示位置 | 实现 |
|:-----|:---------|:-----|
| Excel（页签 18） | 状态图例下方，2 列键值表 | `summary_llm_usage.py._write_cache_stats_section()` |
| HTML（第 18 节） | "各模块明细"表格下方 | `report_template.html` 条件渲染 `{% if cache_stats.total > 0 %}` |

#### 会话生命周期

```
main.py 入口（菜单 L 选中文件后）
  │
  ├─ reset_session_usage(config)     // 清空 _session_usage，重新加载定价
  │
  ├─ generate_all_llm_content(...)   // 并发生成 4+1 个 LLM 模块
  │     ├─ 每个模块调用 → _track + _record（API 调用或缓存命中）
  │     └─ ...
  │
  ├─ generate_excel_report(...)      // 写入独立页签 18
  │     └─ build_llm_usage_sheet()
  │
  ├─ write_html_report(...)          // 渲染 HTML 底部
  │     └─ _render_llm_module_info()
  │
  └─ _print_llm_session_usage()      // TUI 一行摘要
```

每次菜单 L 生成报告均为独立会话。会话开始时 `reset_session_usage()` 清空数据并从 `llm_settings.json` 重新加载定价表和货币配置。

---

## 配置管理技术要点

### 配置分层

```
config.json (基础配置)  ──→ get_config() 内存缓存，按 mtime 自动失效
llm_settings.json (非敏感) ──→ get_llm_config() 合并读取，联合 mtime 失效
llm_key.json (敏感密钥)    ──→ 覆盖 llm_settings.json 的同名字段
```

### JSON 注释支持

`config/_comments.py:_strip_json_comments()` 逐字符扫描，支持 `//` 单行注释和 `/* */` 多行注释。正确处理字符串内的转义引号，不会将字符串内的 `//` / `/*` 误伤。

### 原子写入

配置文件（`set_config`）和缓存写入（`_write_atomic`）均使用 `tempfile.mkstemp` + `os.replace` 模式。详细机制（含 Windows 降级、gzip 回退）见 [缓存设计 / 原子写入](#原子写入)。

---

## 市场时段判断（market_hours.py）

三层 fallback 架构：

```
第 1 层：config.json market_hours.start / end 手动覆盖
第 2 层：东方财富 push2 API 实时交易状态（盘中缓存 60s，盘后 7 天）
第 3 层：内置默认值（北京时间 09:30-11:30 + 13:00-15:00，排除周末）
```

**时区安全**：所有 `datetime.now()` 调用均使用 `timezone(timedelta(hours=8))` 北京时区，防止 UTC 服务器上时段判断全错。

**消费方**：
- `cache/` 子包 `get_ttl()` → 交易时段内 `market_hour_aware` 类型自动使用 `market_hour_ttl`（默认 30s）
- `report/market_value.py:is_market_open()` → 取价方式标签判断（委派 market_hours 实现）
- `report/market_value.py:is_midday_break()` → 午间休市识别

---

## 模块间依赖关系

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

report/excel_generator.py (Excel 编排器，98 行)
  → report/excel_module_loader.py (模块动态加载)
  → report/excel_sheet_factory.py (页签创建/可见性判定)
  → report/excel_market_data.py (行情/指数解析)
  → report/excel_content_sheets.py (穿透/基金业绩/股指期货)
  → report/excel_news_warning.py (新闻+智能预警)
  → report/excel_b_series.py (B 系列 4 模块)
  → report/excel_llm_usage.py (LLM 章节+用量页签)
    → report/summary.py, summary_llm_usage.py, market_value.py,
      category.py, penetration.py, fund_performance.py,
      news_correlation.py, llm_content.py, fund_manager_sheet.py,
      fund_overlap.py, fund_concentration.py, fund_style_analysis.py (各页签写入)
  → report/excel_writer.py, styles.py (通用写入/样式)
  → report/data_status.py (降级状态追踪，Excel/HTML 共享)
  → report/html_writer.py (HTML 编排)
    → report/html_builders.py (数据构建器)
    → report/data_status.py (STATUS_MESSAGES / DataStatusItem)
    → tmpl/report_template.html (Jinja2 模板 + render_data_status 宏)

llm/generators_orchestrator.py (LLM 编排)
  → llm/generators.py (4 单例生成函数)
  → llm/skeleton.py (共享生成骨架)
    → llm/api.py (API 调用+重试+截断+熔断)
    → llm/prompts.py (System Prompt + User Prompt 构建)
    → llm/fingerprint.py (缓存指纹)
    → llm/markdown.py (Markdown→HTML)
    → llm/pricing.py, session.py (定价+用量)
  → cache/ (LLM 结果缓存)

config/ → registry.py (注册表驱动的 TTL/分组/键名)
handlers_*.py → 各模块入口函数编排
```

---

## 设计约束

以下跨模块约束对所有代码生效，违反即视为架构违规。

| # | 约束 | 说明 | 违反后果 | 参考来源 |
|:---|:-----|:------|:---------|:---------|
| C1 | **代码类型判定中心化** | 任何模块不得自行实现资产类型判定（`code.startswith()`、`"QDII" in name.upper()` 等），必须调用 `code_utils` 提供的原语组合 | 代码评审不通过 | [代码类型判定中心化](#代码类型判定中心化) |
| C2 | **缓存统一管理** | 所有持久化缓存必须通过 `cache/` 子包的 `get()`/`set()` 读写，不得直接操作 `data/cache/` 文件系统 | 缓存不一致、TTL 失效 | [缓存设计](#缓存设计) |
| C3 | **缓存原子写入** | 缓存和配置文件写入必须使用 `tempfile.mkstemp` + `os.replace` 模式，禁止直接覆写文件 | 断电/崩溃后半写文件损坏 | [原子写入](#原子写入) |
| C4 | **会话级 API 复用缓存** | 同次会话内同一外部 API 数据被多处/多次请求时，**必须**使用 `DataSourceRegistry.session_cache` 缓存结果，避免重复 HTTP 调用（参考 `provider_registry.py`） | 性能退化、API 限频 | [Provider Chain 三层熔断架构](#provider-chain-三层熔断架构) |
| C5 | **HTTP 客户端统一** | 所有 HTTP 请求必须使用 `http_client.py` 的 `make_http_client()` / `make_async_http_client()` 工厂方法，不得直接实例化 `httpx.Client()` / `httpx.AsyncClient()` | SSL 配置不一致、连接池泄漏 | `http_client.py` |
| C6 | **Provider Chain 必经** | 绝大部分数据获取必须通过 `fetcher/chain.py` 的 `fetch_with_fallback()` / `batch_fetch_with_fallback()`，不得直接调用 Provider 函数（单元测试 mock 场景、指数数据直调 Provider 除外） | 熔断器失效、fallback 链路断路 | [Provider Chain](#provider-chain) |
| C7 | **报告序号不可硬编码** | 报告 18 个模块的序号和显示名称必须通过 `registry.py` 注册表驱动，任何模块不得出现硬编码序号或页签标题 | 序号配置失效、排序错位 | [报告序号可配置](#报告序号可配置) |
| C8 | **日志统一** | 所有模块必须使用 `logger = logging.getLogger("invest")`，不得创建独立的 logger 实例 | 日志碎片化、归档/轮转失效 | `logger.py` |
| C9 | **LLM 模块注册** | 新增 LLM 分析模块时，**必须在** `generators_orchestrator.py` 的 `_MODULE_FNS` 字典和 `_compute_module_cache_info()` 中注册调度入口和缓存信息，在 `registry.py` 中注册模块标识 | 模块不参与并发调度、用量统计遗漏 | [LLM 客户端技术要点](#llm-客户端技术要点) |
| C10 | **新闻召回策略** | `per_source`（每源原始获取量）与 `top_n`（最终输出量）解耦：各源原始获取量 = `max(500, news_top_count × 2)`，不可写死为固定值。华尔街见闻 API 硬上限 100 条除外 | 配置 `news_top_count` 不生效 | [财经新闻热点与持仓关联分析](#财经新闻热点与持仓关联分析) |
| C11 | **测试标记强制** | 新增/修改测试用例（测试类或方法）**必须**标注对应的 pytest marker（通过 `pytestmark` 模块级变量），新增 marker 需同步注册到 `conftest.py` 的 `pytest_configure`。`conftest.py` 的 `pytest_collection_modifyitems` 在收集期自动检查标记遗漏并发出 `PytestWarning` | CI 门禁不通过 | `src/test/conftest.py` |
| C12 | **边缘测试文件隔离** | `@pytest.mark.edge` 测试**必须**放在 `*_edge.py` 文件中，不得与普通测试混搭。`conftest.py` 的 `pytest_collection_modifyitems` 在收集期自动校验 | 测试收集失败 | `src/test/conftest.py` |
| C13 | **测试敏感路径隔离** | 运行测试时**不得**修改用户的配置文件（`data/config/`）、持仓文件（`data/holdings/`）等敏感数据。`conftest.py` 的 `_isolate_sensitive_paths` autouse fixture 自动将 `config.json` 和缓存目录重定向到临时目录 | 用户数据被污染 | `src/test/conftest.py` |
| C14 | **渲染期数据不可写入模块级全局变量** | 任何渲染期数据（section_visible_dict 等）必须通过模板 render context 或函数参数传递，**不得**写入 `_ENV.globals`、模块级 dict 等作为跨函数通信渠道。单次会话中不变的数据（如 _ENV 过滤器注册）不受此限 | 并发不安全、状态污染、跨请求泄漏 | [报告生成管线](#报告生成管线) |
