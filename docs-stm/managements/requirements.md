# 个人投资分析报告生成小助手 — 需求文档

创建日期：2026-06-26
最后更新：2026-07-13（v0.4.2 + 降级日志增强/00代码降级/max_tokens调整）

---

## 1. 运行环境与源代码要求

- R-ENV1. 基础源代码基于 Python 编写
- R-ENV2. Windows 11 使用 PowerShell 脚本启动，支持直接调用 Python 源代码或启动 TUI 界面
- R-ENV3. Linux 使用 Bash 脚本启动，支持直接调用 Python 源代码或启动 TUI 界面

---

## 2. TUI 界面

- R-TUI1. 启动后显示标题"个人投资分析报告生成小助手"
- R-TUI2. 显示以下 14 个选项供用户选择：

| 选项 | 功能 | 说明 |
|---|---|---|
| E | 生成基础版Excel分析报告 | 读取持仓信息生成 Excel 报告（投资分析汇总/市值核算明细表/持仓分类表/资产穿透TOP10/基金业绩分析） |
| H | 生成基础版HTML分析报告 | 读取持仓信息生成 HTML 报告，不含 LLM 增补内容 |
| B | 生成全系列包含新闻的报告(Excel+HTML) [含基金深度分析] | 同时生成 HTML + 含新闻的 Excel 报告，含 B 系列基金深度分析（基金经理变更监控/持仓重合度矩阵/持仓集中度监控/基金风格分析），不含 LLM 增补内容 |
| L | 生成全系列完整版报告(Excel+HTML) [含基金深度分析] | 同时生成 HTML + Excel，含新闻、智能预警、B 系列基金深度分析（基金经理变更监控/持仓重合度矩阵/持仓集中度监控/基金风格分析）、LLM 增补内容（全球政经局势+智囊团深度复盘+持仓体检报告+穿透深度分析+LLM API 用量） |
| C | 配置持仓信息目录 | 配置持仓文件的存放目录 |
| F | 配置持仓信息文件名 | 配置持仓文件的文件名 |
| O | 配置报告输出目录 | 配置报告文件的输出目录（默认 reports） |
| 1 | 更新基础类缓存（含基金业绩/持仓/经理/基准等） | 主动更新 refresh 组全部缓存（基金业绩/持仓/基准/行业分类/新闻/盈利预测/资金流向/分红/基金经理/持仓重合度，详见§5.3 手动刷新表）。纯股票持仓（无基金）时自动跳过基金项，仍主动重拉行业分类、分红、盈利预测、资金流向 |
| 2 | 更新持仓类缓存 | 主动更新价格/指数行情，清除关联 LLM 缓存（智囊团深度复盘、全球政经局势、持仓体检报告、穿透深度分析；另：`llm_news_correlation` 由菜单 1 清理） |
| 3 | 清理过期缓存文件 | 扫描 data/cache/ 目录，删除已过期的缓存文件 |
| 4 | 查看缓存统计信息 | 显示缓存文件总数/大小/按前缀分类/过期预览 |
| S | 配置支持LLM的报告分析章节 | 交互切换各 LLM 报告的启用/停用 |
| R | 刷新配置 | 重新加载 config.json / llm_settings.json / llm_key.json |
| X | 退出 | 退出程序 |

- R-TUI3. E/H/B/L 操作流程：
  - 持仓目录下有多个 xlsx 文件时，弹出选择器要求用户选择其中一个
  - 持仓目录不存在或目录下没有 xlsx 文件时，弹出选择器要求配置持仓目录

> **B 系列**：基金深度分析 4 模块（基金经理变更监控、持仓重合度矩阵、持仓集中度监控、基金风格分析），从菜单 B/L 触发。

---

## 3. 持仓文件格式

持仓 xlsx 文件格式固定：

- 每个页签 = 一个账户，页签名即账户名（如"证券账户""支付宝-余利宝账户"）
- 每个页签固定 4 列：名称（str）、代码（str）、持仓份额（float）、每份成本（float）
- 列名固定，不需要用户配置映射

---

## 4. 数据源

| 用途 | 主链路 | 备用链路 |
|---|---|---|
| 场内 A 股/ETF 实时价 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 基金业绩排名 | 天天基金 JS 变量解析 | — |
| 财经新闻 | 5 源并行：新浪/东方财富/财联社/华尔街见闻/akshare | — |
| 市场指数（A股） | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS变量解析） | 腾讯财经 `qt.gtimg.cn` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com` | 行情页 `quotedata` 解析 |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量研报覆盖 | — |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — |
| 股票历史分红 | akshare `stock_history_dividend()`（全量拉取后按代码过滤） | — |
| 基金经理数据 | 天天基金 `fundf10.eastmoney.com` 经理列表页面 HTML 解析 + 档案页回退 | — |
| 个股/ETF 历史 K 线 | 腾讯财经 `qt.gtimg.cn` K 线接口 | 新浪财经 `hq.sinajs.cn` 日线数据 |
| 场外基金历史净值 | 天天基金 `fundf10.eastmoney.com` 净值页面 | 东方财富 `api.fund.eastmoney.com` 历史净值接口 |

> **指数双链路说明**：指数数据由 `fetcher/index.py` 直调 Provider，不走 Provider Chain。双链路自动 fallback：A 股指数腾讯→新浪，美股指数新浪→腾讯。双链路均失败时降级过期缓存（`stale_cache`）。
>
> 各新闻源的完整端点格式见 [数据源一览文档](../manuals/datasource-and-folders.md)。

---

### 4.1 DataSourceRegistry 数据源注册中心

`src/python/provider_registry.py:DataSourceRegistry` 是一个**线程安全单例**，作为所有数据源获取的集中调度层。减少各模块各自管理熔断/缓存的冗余实现。

**三大职责：**

| 职责 | 说明 | 关键方法 |
|:-----|:------|:---------|
| **Provider 熔断器** | 每个 Provider 独立熔断（连续 3 次失败→熔断 300 秒→自动放行试探） | `record_success()`、`record_failure()`、`is_circuit_broken()`、`get_available_providers()` |
| **会话级缓存** | 同一会话内跨模块共享的进程级内存缓存。按 domain 分组（如 `"price"`、`"extended"`），每 domain 上限 2000 条目，超限淘汰最旧 | `session_cache_get/set/contains/clear()` |
| **策略选择** | 根据代码类型（A 股/港股/QDII）+ 市场时段 + 熔断状态自动选择获取策略：`LIVE_FETCH`（盘中实时）、`CACHE_ONLY`（盘后只读）、`PLACEHOLDER`（预留） | `get_effective_strategy()`、`fetch_or_cached()` |

**统一获取入口 `fetch_or_cached()`：**

策略感知三路径：
1. 盘后（`CACHE_ONLY`）→ session cache → file cache 两级 fallback
2. 盘中 + 全链熔断 → 降级到 `CACHE_ONLY`，不发起 HTTP
3. 盘中 + 有可用 Provider → 执行 fetch_fn，结果写入 session cache

**审计报告 `generate_status_report()`：** 输出所有 Provider 的熔断状态、成功率、缓存命中统计，供 TUI 菜单 [4] 查看。

**与 DegradationTracker 的边界：**
- `DataSourceRegistry` 管"能不能调用"（HTTP 级快速跳过，固定阈值，自动冷却）
- `DegradationTracker`（`data_status.py`）管"数据能不能信任"（数据质量级，可配置阈值）

---

## 5. 缓存策略

缓存统一存放在 `data/cache/` 目录，采用 JSON/JSON.GZ 格式，由 `src/python/cache/` 子包（7 个职责单一的子模块 + services）提供泛用键值对存储接口。

### 5.1 四层缓存架构

| 层级 | 管理方式 | 示例 |
|------|---------|------|
| **单条缓存**（引擎自动管理） | `{类型前缀}_{键名}.json`，按 TTL 自动过期 | `price_600900.json`、`llm_global_macro_{fingerprint}.json` |
| **合并缓存**（菜单手动生成 + 自动管理） | 固定文件名，跨会话复用 | `fund_benchmarks.json`（30天） |
| **特殊独立缓存**（无 cache_group 保护） | 固定文件名，不受菜单 [1][2] 清除 | `holdings_tracking.json`（持仓跟踪）、`trading_calendar.json`（交易日历）、`fund_concentration_snapshot.json`（集中度历史快照）、`fund_style_snapshot.json`（风格快照）、`history_stock_*`（历史 K 线）、`history_fund_otc_*`（历史净值） |
| **进程级内存缓存**（memo） | 同一会话内减少文件 IO，短 TTL | 指数数据 60s、盈利预测 5min、分红 10min |

### 5.2 指纹驱动失效机制

核心策略：文件名中内嵌 **MD5 指纹**，输入源数据变化时缓存键自动不匹配，等效于"缓存未命中"，无需手动清除。

| 指纹类型 | 指纹来源 | 作用范围 |
|---------|---------|---------|
| **指数指纹** | A股 + 美股指数行情 | `profit_forecast_*`、`sector_flow_*` |
| **代码列表指纹** | 持仓+穿透 A 股代码排序 MD5 | `dividend_*` |
| **输入参数指纹** | 新闻源参数 + 关键词 | `news_*` |
| **输入数据指纹** | 指数+持仓汇总/持仓结构 | `llm_global_macro_*`、`llm_expert_review_*`、`llm_health_check_*`、`llm_penetration_deep_*`、`llm_news_item_*` |

> **TTL 兜底**：即使指纹未变，缓存文件仍有 TTL 到期自动刷新。
> **LLM 指纹策略**：智囊团深度复盘、持仓体检报告、穿透深度分析排除行情波动字段（price/change_pct），仅品种/份额/成本变化时失效。
> **交易时段短 TTL**：`price` 和 `index` 在 A 股交易时段（09:30–11:30 + 13:00–15:00）自动使用 `market_hour_ttl`（默认 30s），盘后回落常规 TTL。
> **收市后价格缓存新鲜度验证**：盘后即使长 TTL 未到期，`fetcher/price.py` 的 `_price_cache_fresh()` 会校验缓存中 `price_date` 是否为当前交易日。识别盘中降级残留的过时数据时自动清除并重取。

### 5.3 手动刷新

| 菜单 | 功能 | 清除范围 |
|---|---|---|
| `[1] 更新基础类缓存` | 清除 refresh 组缓存（基金业绩/持仓/基准/行业/新闻/新闻LLM/盈利预测/资金流向/分红/基金经理/重合度/基金风格扩展数据）后重新拉取 | `fund_perf_*`、`fund_hold_*`、`fund_benchmarks.json`、`industry_*`、`news_*`、`llm_news_item_*`（对应 `llm_news_correlation` 分组）、`profit_forecast_*`、`sector_flow_*`、`dividend_*`、`fund_manager_*`、`fund_overlap_*`、`extended_*` |
| `[2] 更新持仓类缓存` | 清除 preload 组缓存（价格/指数行情，LLM 四大分析模块）后重新拉取 | `price_*`、`index_*`、`llm_global_macro_*`、`llm_expert_review_*`、`llm_health_check_*`、`llm_penetration_deep_*`（`llm_news_correlation` 归菜单 [1]） |
| `[3] 清理过期缓存` | 按 TTL 扫描删除过期文件 | 全部过期缓存 |
| `[4] 查看缓存统计` | 只读统计 | — |

> **纯股票组合**：无基金时自动跳过基金排名/持仓/基准刷新，仍主动重拉行业分类、分红、盈利预测、资金流向。
> **无分组保护**：`holdings_tracking.json`、`trading_calendar.json`、`fund_concentration_snapshot.json`、`fund_style_snapshot.json`、`history_stock_*`、`history_fund_otc_*` 不隶属于任何 cache_group，不受菜单 [1][2] 清除命令影响，仅通过菜单 [3] 过期自动清理。
>
> **持仓快照**：`data/history/snapshots/` 目录存放 F1 环比对比的持仓快照，非缓存系统（详见 [§8.4](#84-持仓快照f1)）。

### 5.4 降级规则

缓存过期但 API 请求失败时使用过期缓存数据。过期天数阈值由 degradation 配置控制（T2=3天、T3=14天、T4=14天，每级 `stale_days`），缓存文件损坏时自动删除并触发重新获取。

### 5.5 TTL 明细

#### 行情/数据类

| 键名 | 文件名模式 | 默认 TTL | 指纹 | 说明 |
|:-----|-----------|:--------:|:----|:-----|
| `price` | `price_{code}.json` | 24h（交易时段 30s） | — | 股票/基金最新价、昨收 |
| `index` | `index_{code}.json` | 24h（交易时段 30s） | — | 市场指数行情 |
| `news` | `news_{md5}.json` | 15 分钟 | 新闻源参数 + 关键词 | 多源新闻聚合结果 |
| `sector_flow` | `sector_flow_{fingerprint}.json` | 15 分钟 | A股+美股指数 | 行业资金流向排名 |
| `rank` | `fund_perf_{code}.json` | 24h | — | 基金同类排名+区间收益率 |
| `profit_forecast` | `profit_forecast_{fingerprint}.json` | 24h | A股+美股指数 | 机构盈利预测全量数据 |
| `hold` | `fund_hold_{code}.json` | 7 天 | — | 基金前 10 持仓明细 |
| `industry` | `industry_{code}.json` | 14 天 | — | 行业分类/概念板块 |
| `dividend` | `dividend_{fingerprint}.json` | 30 天 | 持仓+穿透 A 股代码列表 | 股票历史分红汇总 |
| `benchmark` | `fund_benchmarks.json` | 30 天 | — | 业绩比较基准对照表 |

#### LLM 分析类

| 键名 | 文件名模式 | 默认 TTL | 指纹 | 说明 |
|:-----|-----------|:--------:|:----|:-----|
| `llm_expert_review` | `llm_expert_review_{fingerprint}.json` | 2h | 持仓汇总 + 分类计数 + 穿透 TOP10 + 持仓明细 | 智囊团深度复盘 |
| `llm_news_correlation` | `llm_news_item_{hash}.json`（逐条） | 1h | 标题前 80 字 + 持仓指纹 | 财经新闻热点与持仓关联分析 |
| `llm_global_macro` | `llm_global_macro_{fingerprint}.json` | 24h | A股/美股指数 + 持仓汇总 | 全球政经局势 |
| `llm_health_check` | `llm_health_check_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 持仓体检报告 |
| `llm_penetration_deep` | `llm_penetration_deep_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 穿透深度分析 |

#### 基金深度分析类

| 键名 | 文件名模式 | 默认 TTL | 指纹 | 说明 |
|:-----|-----------|:--------:|:----|:-----|
| `fund_manager` | `fund_manager_{code}.json` + `fund_manager_snapshot.json` | 24h | — | 基金经理数据 + 快照 |
| `fund_overlap` | 实时计算，无独立缓存（推导自 `fund_hold_{code}.json`） | 7 天 | — | 持仓重合度数据（前缀用于清理注册） |
| `fund_concentration` | `fund_concentration_snapshot.json` | 30 天 | — | 集中度历史快照（精确键名，无分组） |
| `fund_style_snapshot` | `fund_style_snapshot.json` | 30 天 | — | 风格快照（精确键名，无分组） |
| `extended` | `extended_{code}.json` | 24h | — | 基金风格扩展数据（市值/PE），refresh 组 |

#### 历史走势类

| 键名 | 文件名模式 | 默认 TTL | 指纹 | 说明 |
|:-----|-----------|:--------:|:----|:-----|
| `history_stock` | `history_stock_{code}.json` | 7 天 | — | 个股/ETF 历史 K 线（周级 TTL，无分组保护） |
| `history_fund_otc` | `history_fund_otc_{code}.json` | 30 天 | — | 场外基金历史净值（月级 TTL，无分组保护） |

#### 系统类

| 键名 | 文件名模式 | 默认 TTL | 指纹 | 说明 |
|:-----|-----------|:--------:|:----|:-----|
| `tracking` | `holdings_tracking.json` | 30 天 | — | 持仓跟踪数据（精确键名，用于指纹比对和新增资产检测） |
| `calendar` | `trading_calendar.json` | 14 天 | — | A 股交易日历（精确键名） |

> `—` 表示精确键名（无指纹后缀），TTL 到期后刷新。

---

## 6. 输出文件要求

### 6.1 文件命名

| 类型 | 最新文件 | 存档文件 |
|---|---|---|
| Excel | `个人投资分析报告.xlsx` | `个人投资分析报告-<YYYYMMDD>-<HHmmss>.xlsx` |
| HTML | `个人投资分析报告.html` | `个人投资分析报告-<YYYYMMDD>-<HHmmss>.html` |

最新文件存放到 `output_dir` 根目录（默认为 `reports/`，可通过菜单 R 或 `data/config/config.json` 中的 `output_dir` 字段配置），存档文件存放到 `{output_dir}/<YYYYMMDD>/` 子目录。

### 6.2 输出内容

各页签/章节的功能概要如下。字段布局、展示格式、列明细详见 [§8.2](#82-各页签字段详情)。

| 页签 | 触发菜单 | 功能概要 | 字段详情 |
|:-----|:--------:|:---------|:--------:|
| 投资分析汇总 | E/H/B/L | 指数行情 + 账户汇总（日期、A股/美股指数、总市值/成本/盈亏） | §8.2.1 |
| 市值核算明细表 | E/H/B/L | 15 列持仓明细（含分账户小计+总计），数据复用穿透 + 价格/净值模块 | §8.2.2 |
| 持仓分类表 | E/H/B/L | 按资产属性+投资分类双维度分组，10 列明细，复用市值核算结果 | §8.2.3 |
| 资产穿透TOP10 | E/H/B/L | 基金底层标的拆解→合并→排序，底部标注剩余市值及无法穿透基金 | §8.2.4 |
| 基金业绩分析 | E/H/B/L | 同类排名 + 业绩基准对比，依赖天天基金 API 排名/收益率数据 | §8.2.5 |
| 基金经理变更监控 | B/L（B 系列） | 天天基金 API 获取经理列表，与历史快照比对检测变更 | §8.2.6 |
| 持仓重合度矩阵 | B/L（B 系列） | 两两基金计算 Jaccard + 重叠率双指标，输出热力图矩阵 + 配对明细 | §8.2.7 |
| 持仓集中度监控 | B/L（B 系列） | 前 3/5/10 占比 + 环比变化 + 快照比较 | §8.2.8 |
| 基金风格分析 | B/L（B 系列） | 市值/PE 加权判定六宫格风格箱 + 三级降级链路 | §8.2.9 |
| 财经新闻热点与持仓关联分析 | B/L | 5 源并行获取，关键词来源=持仓名称/代码 + 穿透TOP10 + 行业/概念，子串匹配→排序→TOP N（由 `news_top_count` 配置） | §8.2.10 |
| 智能预警 | B/L | 行业资金联动 + 新闻情绪聚合，对已有计算数据的二次加工 | §8.2.11 |
| 全球政经局势 | L | 基于市场指数 + 持仓结构生成全球政经局势分析 | §7.1 |
| 智囊团深度复盘 | L | 三阶段圆桌会议（召集令→辩论→定音锤）模拟，调仓建议和风险预警 | §7.2 |
| 持仓体检报告 | L | 从风险分散度/流动性/收益合理性/成本结构四维度量化评分 | §7.3 |
| 穿透深度分析 | L | 行业集中度仪表盘 + 国别/币种暴露分析 | §7.4 |
| 组合历史走势 | E/H/B/L | as-if 市值曲线、累计收益率、最大回撤、年化波动率（数据不可用时显示占位） | §8.2.12 |
| 回撤分析 | E/H/B/L | 回撤面积图、最大回撤值/率/区间 | §8.2.13 |
| LLM API 用量 | L | 当前会话的 LLM API 用量统计汇总（调用次数/token/费用/模块明细） | §7.5 |

> **B 系列**（基金经理/重合度/集中度/风格）需有基金持仓数据才能生成，无数据时显示灰色占位文本。
>
> **新闻**模块含可选 LLM 二次关联分析（`enabled_llm.news_correlation=true` 时开启）。各新闻源原始获取量 = `max(500, news_top_count × 2)`，华尔街见闻 API 硬上限 100 条除外。
>
> **F 系列**（组合历史走势、回撤分析）在 E/H/B/L 全菜单模式下均可用，数据可用性由 `history.analysis` 配置（`"off"` / `"prompt"` / `"auto"`）控制，详情见 [§8.2.12](#8212-组合历史走势)。F1 持仓快照对比不受此配置影响，始终自动执行（详见 [§8.4](#84-持仓快照f1)）。

---

## 7. LLM 智能分析

LLM 分析模块是可选增强内容，基于外部持仓摘要数据和市场数据，调用 Claude / OpenAI / DeepSeek API 生成多角度投资分析。仅在菜单 L（全系列完整版报告）中触发，所有模块均可通过菜单 S 或 `enabled_llm` 配置独立启停。

> 各模块的完整配置项（model_* / temperature_* / max_tokens_* 等）见 [§9.3](#93-llm_settingsjson非敏感参数可纳入版本控制)。Provider 配置、Extended Thinking 详解、定价表等详见 [LLM 配置指引](../manuals/how-to-config-llm.md)。

### 7.1 全球政经局势（默认编号 12）

基于市场数据和持仓结构生成全球政经局势分析。
通过菜单 L 生成「12.全球政经局势」页签/章节。

**生成逻辑：** `generate_global_macro()` 读取指数行情 + 持仓汇总，调用 LLM 生成分析。
缓存策略：24 小时 TTL，指数/持仓变化时指纹自动失效。

### 7.2 智囊团深度复盘（默认编号 13）

基于持仓明细和盈亏数据生成优化建议和风险预警。
通过菜单 L 生成「13.智囊团深度复盘」页签/章节。

**生成逻辑：** `generate_expert_review()` 模拟三阶段圆桌会议：召集令→辩论→定音锤，
输出调仓建议和风险预警。缓存策略 2 小时 TTL，指纹排除行情波动字段。

### 7.3 持仓体检报告（默认编号 14）

从风险分散度、流动性、收益合理性、成本结构四个维度
对投资组合进行量化打分（每项满分 100）并给出改进建议。

- **Excel**：通过菜单 L 生成「14.持仓体检报告」页签 ✅
- **HTML**：通过菜单 L 渲染在报告第 14 节 ✅

**生成逻辑：** `generate_health_check()` 复用现有持仓数据（市值核算明细 + 穿透 TOP10 +
分类计数），缓存策略（24 小时 TTL，指纹排除行情波动字段）。每个维度独立评分，
最终输出综合评分和评级（优/良/中/差）及 3-5 条具体可操作建议。

### 7.4 穿透深度分析（默认编号 15）

从行业集中度、国别/币种暴露角度对投资组合进行深度分析。

- **行业集中度仪表盘**：基于现有穿透 + 行业分类数据，计算占净值比重最大的前 N 行业，
  当某行业占比 > 30% 时标注集中度风险
- **国别/币种暴露**：QDII/港股通/美股/A 股按币种分类，计算外汇风险敞口百分比，
  输出分散化建议
- **Excel**：通过菜单 L 生成「15.穿透深度分析」页签 ✅
- **HTML**：通过菜单 L 渲染在报告第 15 节 ✅

**生成逻辑：** `generate_penetration_deep_analysis()` 复用穿透 TOP10 + 行业分类数据，
计算行业集中度和国别/币种暴露度。缓存策略 24 小时 TTL，指纹排除行情波动字段。
每个维度输出分析和建议。

### 7.5 LLM API 用量

本页签/章节**不是 LLM 生成内容**，而是对当前会话中所有 LLM API 调用量的统计汇总。仅在菜单 L 中生成，随 LLM 分析章节一并输出。

**数据来源：** 5 个 LLM 子模块（global_macro / expert_review / health_check / penetration_deep / news_correlation 可选），每次 API 调用由 `_track_session_usage()` 自动记录 token 数和费用，缓存命中由 `_record_per_module()` 记录但不计入调用次数。

覆盖范围：
- **每次成功的 API 调用** — 记录 token 数和费用
- **缓存命中** — 记录来源（缓存），不计入 API 调用次数
- **模块失败/跳过** — 在状态中标记"失败"/"已禁用"，不产生用量数据

不纳入统计：
- LLM Key 未配置 → 整会话无用量数据，API 用量页签不显示
- 菜单 B/H/E 不触发任何 LLM 调用 → 页签不生成

**输出内容格式：**

1. **汇总区**（顶部）— 一次调用总览：

| 字段 | 说明 |
|:-----|:-----|
| API 调用次数 | 成功调用 LLM API 的次数（不含缓存命中） |
| 模型 | 本次会话使用过的模型名称（去重，`/` 分隔） |
| 输入 Token | 累计输入 token 数 |
| 输出 Token | 累计输出 token 数 |
| 总 Token | 累计总 token 数 |
| 缓存命中 Token | 缓存命中节省的输入 token（有数据时显示） |
| 累计费用 | 按模型定价表实时估算的累计费用 |

2. **模块明细表**（汇总区下方）— 每个 LLM 子模块一行：

| 列名 | 说明 |
|:-----|:-----|
| 模块 | 5 个 LLM 子模块名称 |
| 状态 | ✅ 成功 / 📦 缓存 / ⛔ 失败 / 🚫 已禁用 |
| 模型 | 该模块实际使用的模型名 |
| 输入 Token | 该模块累计输入 token |
| 输出 Token | 该模块累计输出 token |
| 缓存命中 Token | 缓存命中 token（无缓存时为 `—`） |
| 费用 | 该模块费用（缓存命中时标注"已计入原调用"） |
| LLM 缓存 | ✓ / — |
| Thinking | ✓ / — |

3. **系统数据缓存统计** — 底部追加当前会话的数据缓存命中/未命中/总请求数/命中率，仅在有缓存请求时显示。

**格式差异：**
- **Excel**：独立页签 18，汇总区 + 表格，状态列条件颜色填充
- **HTML**：渲染在所有 LLM 分析章节之后，格式与 Excel 一致
- **TUI**：完成时终端输出一行摘要（`"本会话 LLM 累计：N 次调用，N tokens，费用 ¥N"`）

**场景渲染规则：**
- 所有模块均缓存命中且无成功调用 → 汇总区标注"无新增 API 调用，数据来自缓存"
- 无任何用量数据（Key 未配置）→ 整个区块不渲染

**定价与费用估算：**

费用按模型名称匹配内置定价表（`src/python/constants.py` `MODEL_PRICING`），支持用户通过 `llm_settings.json` 的 `pricing` 字段覆盖。计算规则：

```
费用 = (input_tokens - cache_hit_tokens) / 1_000_000 × input_rate
     + output_tokens / 1_000_000 × output_rate
     + cache_hit_tokens / 1_000_000 × input_cache_hit_rate
```

货币符号默认 `¥`（CNY），可通过 `pricing.currency` 切换为 `$`（USD）、`€`（EUR）、`£`（GBP）、`¥`（JPY）。

---

## 8. 页面/页签布局

- Excel 格式：每个模块独立一个页签，页签编号 1~18（可通过 `report_section_order` 配置自定义序号），统一用数字前缀保证排序
- HTML 格式：所有模块在同一页面中按顺序排列，附目录锚点导航，使用 CSS `order` 属性实现视觉排序；各模块的条件渲染通过 `section_visible_dict` 统一控制（根据数据可用性和菜单类型自动判断）
- **编号惯例**：HTML 序号使用中文数字（随 `report_section_order` 配置动态变化），Excel 页签使用阿拉伯数字前缀
- **序号配置**：用户可在 `config.json` 中通过 `report_section_order` 字段自定义各模块的序号和排列顺序。`llm_usage` 强制固定在最后一位，不参与排序配置

### 8.1 完整页签对照表

| 序号 | 页签名称 | 触发菜单 | 是否 LLM | 说明 |
|:----:|:---------|:--------:|:--------:|:-----|
| 1 | 投资分析汇总 | E/H/B/L | — | 指数行情、账户汇总、持仓概况 |
| 2 | 市值核算明细表 | E/H/B/L | — | 15 列明细，含分账户小计+总计 |
| 3 | 持仓分类表 | E/H/B/L | — | 按资产属性+投资分类分组聚合 |
| 4 | 资产穿透TOP10 | E/H/B/L | — | 基金底层标的拆解合并排序 |
| 5 | 基金业绩分析 | E/H/B/L | — | 同类排名、收益率、基准对比 |
| 6 | 基金经理变更监控 | B/L（基金深度） | — | 快照式变更检测（1/3/6月窗口），三级预警 |
| 7 | 持仓重合度矩阵 | B/L（基金深度） | — | Jaccard+Overlap Ratio 双指标热力图 |
| 8 | 持仓集中度监控 | B/L（基金深度） | — | top3/5/10 占比 + 环比变化 + 三级预警 |
| 9 | 基金风格分析 | B/L（基金深度） | — | 市值/PE 加权六宫格 + 网格距离漂移评分 |
| 10 | 财经新闻热点与持仓关联分析 | B/L | — | 5 源新闻关键词匹配，可选 LLM 二次关联分析；启用时 Token 用量计入页签 18 |
| 11 | 智能预警 | B/L | — | 行业资金联动 + 新闻情绪聚合 |
| 12 | 全球政经局势 | L | ✅ | LLM 基于指数+持仓结构生成 |
| 13 | 智囊团深度复盘 | L | ✅ | LLM 三阶段圆桌会议 |
| 14 | 持仓体检报告 | L | ✅ | LLM 四维度评分 |
| 15 | 穿透深度分析 | L | ✅ | LLM 行业集中度+国别暴露 |
| 16 | 组合历史走势 | E/H/B/L | — | as-if 市值曲线、累计收益率、最大回撤、年化波动率 |
| 17 | 回撤分析 | E/H/B/L | — | 回撤面积图、最大回撤值/率/区间 |
| 18 | LLM API 用量 | L | — | Token 用量、费用估算、模块明细 |

### 8.2 各页签字段详情

以下列出页签 1~5（基础报表页签）的字段布局与展示格式。页签 6~11（基金深度分析 + 新闻模块）详见本小节 8.2.6~8.2.11。页签 12~15（LLM 分析章节）详见 [§7](#7-llm-智能分析)。页签 16~17（组合历史走势 + 回撤分析）详见本小节 8.2.12~8.2.13。

#### 8.2.1 投资分析汇总

| 区块 | 内容 |
|:-----|:-----|
| 当前时间 | 生成日期时间 + 所属交易日 |
| A 股指数 | 上证指数、沪深300、创业板指（涨跌幅+点数） |
| 美股指数 | 道琼斯、纳斯达克、标普500（涨跌幅+点数） |
| 账户汇总 | 总市值、总成本、总盈亏、本日盈亏 |

#### 8.2.2 市值核算明细表

15 列明细表：

| # | 列名 | 说明 |
|---|---|---|
| 1 | 账户 | 证券/支付宝/微信/谱蓝 |
| 2 | 名称 | 资产全称 |
| 3 | 代码 | 6 位代码 |
| 4 | 最新价 | 当前价格/净值 |
| 5 | 净值日期 | 具体日期如 2026-06-23 |
| 6 | 昨日价 | 前一日收盘价/净值 |
| 7 | 取价方式 | 场内实时价/场内收盘价/官方净值(T)/官方净值(T-1) |
| 8 | 溢价率 | 对 QDII 基金显示 |
| 9 | 份额 | 持仓数量 |
| 10 | 市值 | 价格 × 份额 |
| 11 | 成本 | 成本价 × 份额 |
| 12 | 盈亏 | 累计盈亏（市值 - 成本） |
| 13 | 收益率 | 累计收益率 |
| 14 | 本日盈亏 | 仅场内品种计算，场外非当日更新标 0 |
| 15 | 取价渠道 | 腾讯财经/天天基金网 |

**格式规则：**
- 分账户小计在该账户所属资产下立即显示，总计在最后
- 盈亏正数红色，负数绿色
- 取价方式蓝色标识（`#0066CC`）：场内收盘价(T) / 官方净值(T) / QDII 官方净值(T-1) 时蓝色显示

#### 8.2.3 持仓分类表

| # | 列名 | 说明 |
|---|------|------|
| 1 | 资产属性 | 资产大类（股票/基金/债券/现金） |
| 2 | 投资分类 | 细分类型（A股/QDII/主动/被动/指数/混合/纯债/货币） |
| 3 | 名称 | 资产全称 |
| 4 | 代码 | 6 位代码 |
| 5 | 市值 | 最新价 × 份额 |
| 6 | 成本 | 成本价 × 份额 |
| 7 | 盈亏 | 累计盈亏（市值 - 成本） |
| 8 | 收益率 | 累计收益率（盈亏 / 成本） |
| 9 | 本日盈亏 | 仅场内品种计算，场外非当日更新标 0 |
| 10 | 年均股息率 | 持仓 A 股的年均股息/最新价 × 100% |

#### 8.2.4 资产穿透TOP10

| # | 列名 | 说明 |
|---|------|------|
| 1 | 排名 | 1~10 |
| 2 | 名称 | 资产名称 |
| 3 | 代码 | 6 位代码 |
| 4 | 穿透市值 | 合并后的市值 |
| 5 | 占比 | 占总穿透市值比例 |
| 6 | 板块 | 所属板块/行业 |
| 7 | 概念 | 东方财富概念标签 |
| 8 | 预测EPS(YYYYE)† | 机构盈利预测 |
| 9 | 年均股息 | 历史分红每股年均金额（元/年）。† `YYYYE` 为 `datetime.now().year` 动态生成，跨年自动更新 |
| 10 | 来源明细 | 来自哪些基金的持仓 |

**板块分类增强：** 在关键词映射分类基础上，额外调用东方财富 push2 API 获取三级行业分类作为板块列的补充数据源。API 数据可用时优先覆盖板块列。

#### 8.2.5 基金业绩分析

| # | 列名 | 说明 |
|---|------|------|
| 1 | 基金 | 基金名称 |
| 2 | 代码 | 6 位代码 |
| 3 | 类型 | 场内ETF/场外主动型/场外指数/场外QDII/场外债券（穿透分类自动标注） |
| 4 | 近3月 | 近3月收益率 |
| 5 | 近6月 | 近6月收益率 |
| 6 | 近12月 | 近12月收益率 |
| 7 | 持仓累计盈亏(¥) | 市值 - 成本 |
| 8 | 持仓收益率 | 盈亏 / 成本 |
| 9 | 业绩基准 | 比较基准名称 |
| 10 | 业绩评价 | 三层评级结果（优秀/良好/稳定/偏差/较差） |
| 11 | 同类排名 | 格式"排名/总数"，如 23/156 |
| 12 | 机构覆盖 | 研报家数 + 预测EPS |

#### 8.2.6 基金经理变更监控

| # | 列名 | 说明 |
|---|------|------|
| 1 | 基金名称 | 基金全称 |
| 2 | 代码 | 6 位代码 |
| 3 | 当前基金经理 | 现任经理姓名 |
| 4 | 任职天数 | 当前经理已任职天数 |
| 5 | 1 月内变更 | 🔴 是 / ✅ 否（— 表示首次运行） |
| 6 | 3 月内变更 | ⚠️ 是 / ✅ 否 |
| 7 | 6 月内变更 | ⚠️ 是 / ✅ 否 |
| 8 | 预警级别 | 🔴 紧急 / ⚠️ 关注 / 📋 首检 / ✅ 正常 |

**预警规则：**
- 30 天内发生经理变更 → 🔴 紧急
- 90 天内发生经理变更 → ⚠️ 关注
- 180 天内发生经理变更 → ⚠️ 关注（与 90 天同级，用于 91-180 天范围的变更提示）
- 首次运行无历史快照 → 📋 首检（自下次起跟踪）
- 以上均不满足 → ✅ 正常

**数据来源：** 天天基金 `fundf10.eastmoney.com` 基金经理列表页面（HTML 解析）+ 本地快照比对。

#### 8.2.7 持仓重合度矩阵

**热力图矩阵：**

矩阵元素 = max(Jaccard 系数, 重叠率)，其中：

```
Jaccard = |A ∩ B| / |A ∪ B|
重叠率  = |A ∩ B| / min(|A|, |B|)
```

| 重合度范围 | 着色 |
|:----------|:-----|
| ≥ 50% | 🔴 红色白字 |
| 30% ~ 50% | 🟠 橙色白字 |
| 15% ~ 30% | 🟡 黄色黑字 |
| > 0% | 🟢 绿色黑字 |
| 0% | 无着色 |

**配对明细表：**

| # | 列名 | 说明 |
|---|------|------|
| 1 | 序号 | 按重合度降序排列 |
| 2 | 基金 A | 基金名称+代码 |
| 3 | 基金 B | 基金名称+代码 |
| 4 | 共同标的数 | 共同持有的标的数量 |
| 5 | Jaccard | Jaccard 相似度百分数 |
| 6 | 共同标的 | 共同持有的标的名称列表 |

**触发条件：** 持仓中被识别为基金的类型（含场内 ETF、场外基金等）≥ 2 只。满足条件后拉取各基金的底层穿透数据用于重合度计算。

#### 8.2.8 持仓集中度监控

| # | 列名 | 说明 |
|---|------|------|
| 1 | 基金名称 | 基金全称 |
| 2 | 代码 | 6 位代码 |
| 3 | 前 3 占比 | 前 3 大持仓占总仓位比例 |
| 4 | 前 5 占比 | 前 5 大持仓占总仓位比例 |
| 5 | 前 10 占比 | 前 10 大持仓占总仓位比例 |
| 6 | 上期前 10 | 历史快照中的前 10 占比 |
| 7 | 环比变化 | 本次前 10 - 上期前 10（附 ↑↓ 箭头） |
| 8 | 预警 | 🔴 紧急 / ⚠️ 关注 / 📋 首次 / ✅ 正常 |

**预警规则（与环比独立叠加）：**
- 前 10 占比环比变化 > +20% → 🔴 紧急
- 前 10 占比环比变化 > +10% → ⚠️ 关注
- 当前前 10 占比 > 80% → ⚠️ 关注（与环比独立）
- 首次运行 → 📋 首次（记录基线）
- 以上均不满足 → ✅ 正常

#### 8.2.9 基金风格分析

| # | 列名 | 说明 |
|---|------|------|
| 1 | 基金名称 | 基金全称 |
| 2 | 代码 | 6 位代码 |
| 3 | 当前风格 | 六宫格风格（如"大盘成长"） |
| 4 | 上期风格 | 历史快照中的风格 |
| 5 | 漂移等级 | 🔴 严重 / ⚠️ 中度 / ▲ 轻度 / 📋 基准确立中 / ✅ 无 |
| 6 | 漂移评分 | 网格曼哈顿距离（0~4） |
| 7 | 备注 | 估算风格标注 |
| 8 | 标识 | 📋 基线 / ✅ |

**风格判定逻辑（主方案 A—push2 数据可用）：**
- 大盘/中盘/小盘：总市值 >500 亿=大盘、100~500 亿=中盘、<100 亿=小盘
- 成长/价值/混合：PE / 行业平均 PE，<70%=价值、>130%=成长、其余=混合
- 最终风格 = 市值权重最大的 size + PE 权重最大的 style

**降级方案（三级链路，优先级从高到低）：**
1. **push2 API**（一级，精确）：同主方案，市值+PE 数据直接判定
2. **Tencent 扩展字段**（二级，可靠）：通过 `qt.gtimg.cn` f46（总市值，亿）×1e8→元、f40（PE TTM）获取数据，质量接近 push2，不标注估算
3. **代码前缀估算**（三级，兜底）：60xxxx → 大盘，000/002 → 中盘，300/688 → 小盘，4/8 → 小盘；估值方向统一"混合"，备注标注"估算风格"

**漂移检测：**
- 网格距离 = |Δsize| + |Δstyle|（曼哈顿距离，0~4）
- 距离=0→无、=1→轻度、=2→中度、≥3→严重
- 首次运行记录基线，标注"基准确立中"

#### 8.2.10 财经新闻热点与持仓关联分析

**关键词富化显示：** 自动识别每个匹配关键词的来源类型并以不同样式标识：

| 来源 | 格式 | Excel 显示 | HTML 显示 |
|:-----|:-----|:-----------|:----------|
| 持仓 | `长江电力(600900)` | 格式化字符串 | 蓝色标签 |
| 穿透 | `腾讯控股[穿透]` | 格式化字符串 | 紫色标签 |
| 概念 | `CPO光模块[概念]` | 格式化字符串 | 橙色标签 |
| 行业 | `电力` | 格式化字符串 | 灰色标签 |

关键词按 **持仓→穿透→概念→行业** 顺序排列。

**LLM 关联分析列（可选）：** `enabled_llm.news_correlation=true` 时显示，每条新闻的关联度评级（高/中/低/无关）+ 原因分析。

**Excel 格式优化：** 新闻标题列宽 40、摘要列宽 50，文本换行 + 左对齐。

#### 8.2.11 智能预警

**行业资金联动表：**

| 列 | 说明 |
|:---|:-----|
| 行业名称 | 匹配到的行业名称 |
| 主力净流入 | 今日主力资金净流入额 |
| 涨跌幅 | 行业指数涨跌 |
| 关联持仓 | 匹配到的持仓品种 |
| 预警等级 | ⚠注意 / 🔴危险 |

**新闻情绪聚合表：**

| 列 | 说明 |
|:---|:-----|
| 持仓品种 | 持仓名称/代码 |
| 提及次数 | 关联新闻数量 |
| 利好/利空/中性计数 | 按情绪分类统计 |
| 情绪得分 | -1~1 |
| 最新要闻 TOP3 | 该品种关联度最高的 3 条新闻标题 |

#### 8.2.12 组合历史走势

以折线图展示组合市值变化轨迹和各关键期指标，基于 **as-if 模拟**（当前持仓份额 × 历史价格/净值），数据由 `portfolio_history.py:PortfolioHistoryCalculator` 计算。

**数据来源：**
- 场内股票/ETF：腾讯财经 K 线（`qt.gtimg.cn`）或新浪财经（`hq.sinajs.cn`），缓存类型 `history_stock_*`（周级 TTL）
- 场外基金：天天基金历史净值（`fundf10.eastmoney.com`），缓存类型 `history_fund_otc_*`（月级 TTL）

**返回数据结构（`history_data` 字典）：**

| 字段 | 类型 | 说明 |
|:-----|:----:|:-----|
| `bars` | list[dict] | 时间线数组，每项含 `date`、`total_value`、`drawdown`、`drawdown_pct` |
| `total_return` | float | 累计收益金额（期末市值 - 期初市值） |
| `total_return_pct` | float | 累计收益率（百分比） |
| `max_drawdown` | float | 最大回撤金额 |
| `max_drawdown_pct` | float | 最大回撤幅度（百分比） |
| `drawdown_start` | str | 最大回撤开始日期（始于峰值日） |
| `drawdown_end` | str | 最大回撤结束日期 |
| `annualized_volatility` | float | 年化波动率 |
| `status` | str | `"ok"` / `"degraded"`（部分持仓不可用）/ `"unavailable"` |
| `warnings` | list[str] | 降级/异常提示信息列表 |
| `failed_holdings` | list[str] | 获取失败的持仓名称(代码)列表 |
| `successful_holdings` | list[str] | 获取成功的持仓名称(代码)列表 |
| `data_start` | str | 数据起始日期（首条 bars 日期） |
| `data_end` | str | 数据截止日期（末条 bars 日期） |

**渲染形式：**
- **HTML**：原生 Canvas 即时渲染（drawSimpleChart 折线图）+ 3 个摘要卡片（累计收益/最大回撤/年化波动率）+ 降级提示信息
- **Excel**：该模块在 Excel 中仅以灰色占位文本呈现（数据不可用提示），完整图表内容仅在 HTML 报告中展示

**触发条件：**
- 由 `history.analysis` 配置（`"off"`/`"prompt"`/`"auto"`，默认 `"off"`）控制是否获取历史走势（见 §9.1）
- `"prompt"` 模式：报告生成后询问用户是否需要获取（约耗时 15s）
- `"auto"` 模式：报告生成时自动获取，不询问
- `"off"` 模式：不获取数据，报告渲染占位文本

#### 8.2.13 回撤分析

以面积图展示组合在整个观测期内的回撤幅度变化，突出最大回撤区间。

**数据来源：** 与组合历史走势共用同一 `history_data` 字典，复用 `bars[i].drawdown_pct` 绘制回撤曲线。

**渲染指标：**

| 指标 | 说明 |
|:-----|:-----|
| 最大回撤幅度 | `max_drawdown_pct`，历史最深回撤百分比 |
| 最大回撤金额 | `max_drawdown`，历史最深回撤金额 |
| 回撤区间 | `drawdown_start` → `drawdown_end`，最大回撤的起止日期区间（`drawdown_start` 始于峰值日） |

**渲染形式：**
- **HTML**：原生 Canvas 即时渲染（drawSimpleChart 回撤面积图，红色填充）+ 3 个摘要卡片（回撤幅度/回撤金额/回撤区间）
- **Excel**：该模块在 Excel 中仅以灰色占位文本呈现（数据不可用提示），完整图表内容仅在 HTML 报告中展示

### 8.3 取价方式规范

| 取价方式 | 触发条件 | 蓝色标识 |
|:---------|:---------|:--------:|
| 场内实时价 | 腾讯 source_api 且市场开盘 | — |
| 场内午市收盘(T) | 腾讯 source_api，午间休市，nav_date == T | — |
| 场内收盘价(T) | 腾讯 source_api，盘后，nav_date == T | ✅ `#0066CC` |
| 场内收盘价(T-1) | 腾讯 source_api，盘后，nav_date == 前一交易日 | — |
| 官方净值(T) | East Money source 且 nav_date == T | ✅ `#0066CC` |
| 官方净值(T-1) | QDII 基金且 nav_date == 前一交易日 | ✅ `#0066CC` |
| 官方净值(T-N) | nav_date 为 2~5 个交易日前 | — |
| 官方净值(YYYY-MM-DD) | nav_date 为 6 个交易日以上 | — |

### 8.4 持仓快照（F1）

持仓快照用于环比对比（F1），存放在 `data/history/snapshots/` 目录，**独立于缓存系统**。

| 特性 | 说明 |
|:-----|:------|
| 存储格式 | `data/history/snapshots/snapshot_{timestamp}.json`（JSON，带时间戳） |
| 写入时机 | B/L 菜单生成报告时自动创建 |
| 原子写入 | `tempfile.mkstemp` + `os.replace`，避免半写损坏 |
| 自动清理 | `save()` 后触发 `prune()`，两阶段：① 超 60 天（`history.snapshot_retention_days`）删除；② 超 365 个（`history.snapshot_max_count`）删最旧 |
| 对比逻辑 | 加载上次快照 → `HistoryDiff.compute()` → 输出总市值Δ/总盈亏Δ/持仓变动（新增/清仓/增持/减持）TOP5 |
| 故障降级 | 首次运行无快照 / 快照损坏 → 跳过对比，下次自动建立基线 |

### 8.5 F 系列：F1 持仓快照 vs F2 组合历史走势

F1 与 F2 是两套独立的数据机制，共用 F 前缀但无数据依赖，各自独立降级。

| 维度 | F1 持仓快照对比 | F2 组合历史走势 |
|:-----|:---------------|:---------------|
| **本质** | 环比对比——本次 vs 上次的快照差异 | 回溯模拟——假设份额不变 × 历史价格 |
| **数据来源** | 本次报告的持仓市值/盈亏计算结果 | 外部第三方行情/净值 API（腾讯/新浪/天天/东方财富） |
| **存储位置** | `data/history/snapshots/snapshot_{timestamp}.json` | `data/cache/history_stock_{code}.json` / `history_fund_otc_{code}.json` |
| **生命周期** | 60 天 + 365 上限自动清理（`prune()`） | 标准缓存系统，按 TTL 过期（周级/月级） |
| **输出位置** | 嵌入 §8.2.13 回撤分析页脚（快照摘要卡片） | 独立产出 §8.2.12 走势图 + §8.2.13 回撤分析 |
| **控制开关** | 始终自动执行，不受任何配置影响 | `history.analysis`（`"off"` / `"prompt"` / `"auto"`） |
| **失败影响** | 跳过对比，下次自动重建基线 | 走势图显示占位文本，回撤指标不可用 |
| **00 代码降级** | 不涉及 | K 线全空→自动降级基金净值链路 |
| **代码文件** | `report/history_snapshot.py` + `fetcher/history_diff.py` | `report/portfolio_history.py` + `fetcher/chain.py` |

---

## 9. 配置文件规格

### 9.1 config.json

| 字段 | 类型 | 默认值 | TUI 修改 | 说明 |
|:-----|:----:|:------:|:--------:|:-----|
| `holdings_dir` | str | `data/holdings` | C | 持仓 xlsx 目录 |
| `holdings_filename` | str | `个人投资持仓信息.xlsx` | F | 持仓文件名 |
| `output_dir` | str | `reports` | O | 报告输出根目录 |
| `news_top_count` | int | `300` | 手动 | 新闻关联输出 TOP N |
| `news_sources` | dict | {sina:true, eastmoney:true, cls:false, wallstreetcn:true, akshare:true} | 手动 | 各新闻源启停 |
| `preferred_provider` | dict | `{}` | 手动 | Provider Chain 首选覆写（price/fund_rank/fund_hold/industry） |
| `user_fund_benchmarks` | dict | `{}` | 手动 | 自定义基金基准 {代码: 基准代码} |
| `early_warning` | dict | `{sector_alert_threshold_warning:-50000000, sector_alert_threshold_danger:-200000000, sentiment_top_n:10}` | 手动 | 智能预警阈值（单位：元） |
| `default_menu_key` | str | `"L"` | 手动 | TUI 菜单默认选项快捷键，取值为任一有效菜单键（如 E/H/B/L），启动后光标自动定位 |
| `report_section_order` | dict | `{}` | 手动 | 报告模块序号配置。键=模块标识，值=序号。已配置模块按序号升序排列在前，未配置模块按默认顺序排后。`llm_usage` 强制末位。示例：`{"fund_manager": 1, ...}`。空对象 `{}` 使用默认 18 项顺序 |
| `market_hour_aware` | list | `["price", "index"]` | 手动 | 交易时段短 TTL 的数据类型 |
| `market_hour_ttl` | int | `30` | 手动 | 交易时段缓存有效期（秒） |
| `market_hours` | dict | `{start:"09:30", end:"15:00", official_source:true}` | 手动 | 交易时段配置。`official_source=true` 时优先通过东方财富 push2 API 获取实时交易状态，false 时仅依赖内置默认时段 |
| `degradation` | dict | T2/T3/T4 三级配置 | 手动 | 双信号降级阈值：每层级含 `unreachable_threshold`（连续失败次数）、`empty_data_threshold`（连续空数据次数）、`stale_days`（过期缓存可用天数） |
| **_history 对象** | | | | 以下字段属于顶层 `history` 字典 |
| `history.analysis` | str | `"off"` | 手动 | 组合历史走势获取模式：`"off"`=关闭、`"prompt"`=报告后询问用户、`"auto"`=自动获取 |
| `history.snapshot_retention_days` | int | `60` | 手动 | 持仓快照保留天数（超过此天数的旧快照自动删除） |
| `history.snapshot_max_count` | int | `365` | 手动 | 持仓快照最大保留数（安全上限，超过则删除最旧的） |
| `cache_ttl` | dict | 24 项 | 手动 | 各缓存类型 TTL（秒） |
| `llm_key_file` | str | `data/config/llm_key.json` | 手动 | LLM 密钥文件路径 |
| `llm_settings_file` | str | `data/config/llm_settings.json` | 手动 | LLM 参数文件路径 |

### 9.2 llm_key.json（敏感字段，建议 gitignore）

| 字段 | 必填 | 说明 |
|:-----|:----:|:-----|
| `provider` | ✅ | `"claude"` / `"openai"`（DeepSeek 使用 `"claude"` + Anthropic 兼容端点） |
| `api_key` | ✅ | API Key |
| `model` | ✅ | 默认模型名 |
| `endpoint` | ✅ | API 端点 URL |
| `fallback_provider` | — | 主 provider 失败时回退的 provider |
| `fallback_api_key` | — | 回退 provider 的 API Key |
| `fallback_endpoint` | — | 回退 provider 的端点 URL |
| `fallback_model` | — | 回退 provider 的默认模型 |

### 9.3 llm_settings.json（非敏感参数，可纳入版本控制）

**全局配置**

| 键 | 类型 | 默认值 | 说明 |
|:---|:----:|:------:|:-----|
| `max_retries` | int | `2` | 429/503 最大重试次数 |
| `llm_max_concurrency` | int | `3` | LLM 4+1 模块并发生成最大线程数 |
| `enabled_llm` | dict | 全局开启 + news_correlation 默认关闭 | 各模块独立启停开关 |
| `pricing` | dict | `{currency:"CNY"}` | 模型定价表覆盖 |

**模块级配置**（`{key}` 替换为 global_macro / expert_review / health_check / penetration_deep / news_correlation）

| 键 | 类型 | 说明 |
|:---|:----:|:-----|
| `system_prompt_{key}` | str/null | `null`=使用代码内置提示词 |
| `model_{key}` | str/null | `null`=使用 llm_key.json 的默认 model |
| `temperature_{key}` | float | 0.1~0.8（模块差异） |
| `max_tokens_{key}` | int | 1024~8192（模块差异） |
| `timeout_{key}` | int | 60~120s（模块差异） |
| `cache_enabled_{key}` | bool | 是否缓存 LLM 结果 |
| `output_brief_{key}` | bool | 精简模式 ≤200~300 字（news_correlation 不支持） |
| `thinking_enabled_{key}` | bool | Extended Thinking 开关 |
| `thinking_budget_{key}` | int | Claude Thinking token 预算（≥max_tokens+1024，自动兜底） |
| `reasoning_effort_{key}` | str | DeepSeek 推理深度：`"high"` / `"max"` |

---

## 10. 错误处理与降级策略

| 场景 | 用户感知 | 内部处理 |
|:-----|:---------|:---------|
| 网络断开 | TUI 提示网络异常 | 过期缓存降级使用（由 degradation 配置的 stale_days 控制，T2=3天/T3=14天/T4=14天） |
| API 超时 | 单条数据跳过，其余继续 | Provider Chain 自动切换备用链路；连续超时触发 DataSourceRegistry 熔断器（3次失败→熔断300秒→冷却后自动放行） |
| API 返回异常/空数据 | 显示 `--` 占位 | 日志记录 WARNING |
| 缓存文件损坏 | 透明修复 | 自动删除并重新获取 |
| 配置值异常 | 启动时输出 WARNING | 使用代码默认值兜底 |
| LLM API Key 未配置 | 显示占位文本"本节内容待生成 — LLM 未配置（请配置 data/config/llm_key.json）" | 跳过 LLM 模块，不阻塞 |
| LLM 模块已禁用 | 主分析章节（页签 12~15）完全跳过不渲染，不留空位；LLM API 用量页签（页签 18）中对应模块行显示"已禁用"灰色状态 | `continue` 跳过 / `{# 模块已禁用，完全跳过 #}` |
| LLM 超时/失败 | 根据 FAIL_REASON_* 类型输出差异化占位（见 llm_content.py _PLACEHOLDER_BY_REASON） | 熔断器自动冷却，支持 fallback_provider 回退 |
| LLM 输出截断 | 自动增大 max_tokens 1.5× 重试 | 日志 ERROR 提示 |
| LLM 内容过滤（空返回） | 追加安抚指令重试 | 日志 WARNING |
| config.json 损坏 | 回退到全默认配置 | 日志 WARNING |
| 报告输出目录无写入权限 | 提示错误 | PermissionError，不继续 |
| 持仓文件格式异常 | 跳过异常行，继续解析 | 提示具体行号错误 |
| 空持仓 | 暂停生成 | 直接返回，不生成报告 |
| 熔断器触发 | 跳过该端点请求 | 冷却期后自动恢复 |
| push2 数据源熔断 | 行业分类/概念板块/基金风格分析自动降级为备用数据或代码估算结果 | DataSourceRegistry 熔断器（连续 3 次失败后熔断 push2，冷却 5 分钟后自动放行试探）；原 eastmoney_industry.py 局部熔断器已于 R-188 迁移至 DataSourceRegistry |
| 收市后价格缓存过期（盘中降级残留） | 无感知（透明修复） | `_price_cache_fresh()` 校验缓存 `price_date`，发现非当日时自动清除缓存并重新请求 |
| T2 增强数据源失败（指数/基金排名） | 列级 `--` + 页脚 ⚠/ℹ 状态摘要 | `_data_status` 字典（DataStatusItem）追踪各源 available/tier/message；Excel 端 `_write_data_status_foot()` 写入灰色页脚；HTML 端 `render_data_status` Jinja2 宏渲染 |
| T3 数据源失败（行业分类）/ T4 数据源失败（盈利预测、分红） | 列级 `--` + 页脚状态摘要 | 同上 DegradationTracker 双信号降级 |
| B 系列模块数据不可用（基金经理变更/重合度/集中度/风格） | 模块级占位文本，不隐藏页签 | `STATUS_MESSAGES` 共享常量 + `_write_placeholder()` grey-bg 占位（Excel）；HTML 模板 `empty-section` 条件占位块（独立于 degradation 体系） |
| 新闻多源并行获取（5 源全失败/部分失败） | 全源失败 → 模块级占位文本；部分失败 → 页脚列出失败源清单 | `news_aggregator._last_src_results` + `get_last_source_status()` 追踪各源 fetch 结果；`news_correlation._build_news_footer()` 追加失败源列表 |
| akshare 分红数据获取失败 | 年均股息率列显示 `--`；页脚状态摘要标记分红不可用 | `_build_category_data()` 返回 `(list, bool)`，`dividend_success=False` 时触发 `_build_category_data_status()` 写入状态摘要 |
| 指数/指数数据双链路均失败 | 指数区域显示 `--`，不影响其余模块 | `fetcher/index.py` 腾讯→新浪→过期缓存三层降级 |
| **OTC 基金 00 代码实时行情降级** | 无感知(透明修复) | `price.py` 中 `00` 开头代码（A 股/OTC 基金代码前缀重叠区）的股票链路（腾讯→新浪）全失败后，自动降级到 `price_fund_otc`（东方财富净值）；降级成功/失败均有日志区分 |
| **OTC 基金 00 代码历史走势降级** | 走势图数据源自动切换 | `portfolio_history.py` 中 `00` 开头代码的 K 线历史全空时，自动降级到 `history_fund_otc`（天天基金历史净值） |
| **降级日志增强**（v0.4.1+） | 日志输出更清晰 | 所有 Provider Chain 的 fallback 日志追加 `[code]` 标签；00 代码降级日志含资产名称；市场行情失败汇总时列出具体失败资产名称(`基金名(code)`) |
| F1 快照对比 — 首次运行无历史快照 | 显示"首次运行，暂无环比数据"占位 | `SnapshotData.load_latest()` 返回 None，跳过差异对比 |
| F1 快照对比 — 快照读取异常/损坏 | 跳过环比对比，不影响报告其余模块 | 日志 WARNING，`f_context` 置为 None |
| F1 快照自动清理失败（权限/文件锁定） | 日志 WARNING 跳过该文件，快照目录可能膨胀 | `prune()` 日志记录失败路径，保留已有文件继续运行 |
| F2 历史走势 — 全部持仓数据不可用 | 页面显示占位文本"组合历史走势数据不可用"；快照对比不受影响 | `history_data.status = "unavailable"`，HTML 模板条件渲染占位块 |
| F2 历史走势 — 部分持仓数据缺失 | 页面显示降级警告清单（"部分持仓历史走势不可用（3/5）"），观测期压缩但不中断 | `history_data.status = "degraded"`，`warnings` 列表逐条标注；Excel 页脚追加状态提示 |
| F2 历史走势 — 获取模式为 `"off"` | 报告页面显示占位文本，不报错 | `handlers_report.py` 依据 `history.analysis` 配置跳过获取流程，`f_context` 保持 None |

---

## 11. 性能与资源约束

| 约束项 | 设计决策 |
|:-------|:---------|
| **并发策略** | ThreadPoolExecutor：新闻 5 源并发获取、LLM 4+1 模块（4 个 LLM 分析模块 + 可选的新闻关联分析）并发生成（并行数由 `llm_max_concurrency` 配置，默认 3）、取价批量异步 |
| **基金风格加速** | DataSourceRegistry session_cache（domain="extended"）跨基金复用；Tencent 二级降级基于 registry 熔断器；push2 超时 5s、重试 1 次、熔断阈值 3 |
| **HTTP 连接池** | LLM 客户端专用 HTTP/2 多路复用 + 连接池上限 20 / 空闲保持 10（`llm/generators_orchestrator.py` `_LLM_CLIENT_SETTINGS`），通用 HTTP 客户端仅 SSL 配置 |
| **缓存原子写入** | `tempfile.mkstemp` + `os.replace` 模式，防断电半写导致文件截断 |
| **配置原子写入** | 同上，防 config.json 截断导致下次启动丢失全部自定义配置 |
| **大文件优化** | 缓存超过 100KB 自动 gzip 压缩（`.json.gz`），节省 80-90% 磁盘 |
| **时区安全** | 所有交易时段判断统一使用 `timezone(timedelta(hours=8))` 北京时间 |
| **LLM Prompt 精简** | 专家复盘 compact 模式省略今日涨跌幅，输入 token 减少 10-15% |
| **LLM Prompt 缓存** | Claude API 使用 `cache_control: ephemeral` 5 分钟内复用 system prompt |
| **加载顺序** | `get_config()` 带 mtime 缓存，避免每次读取磁盘 |
