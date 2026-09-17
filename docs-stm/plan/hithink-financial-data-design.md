# 同花顺金融数据服务接入设计（hithink）

> 版本：0.11.1-dev ｜ 状态：**阶段 1 已实测通过、阶段 3 已实施**（provider 层 + 55 例单测 + 11 端点真实连通，见 §4.1）；阶段 2~5 待实施（映射表按实测字段落表）
> 上游：<https://github.com/HiThink-Tech/Financial-API>（同花顺官方 A 股数据服务）
> 契约来源：<https://fuyao.aicubes.cn/llms-full.txt>（完整接口文档聚合）
> 归档去向：全部 5 个阶段完成后，本文档随完成态归档至 `docs-stm/archive/v0.11.x/hithink-data-source/`（与 plan-45 / plan-46 的设计文档先例一致）；未完成前留在 `docs-stm/plan/`。当前进度：阶段 1 ✅ / 阶段 2 ✅ / 阶段 3 ✅ / 阶段 4 ✅（复权因子消费待接）/ 阶段 5 ⬜

---

## 1. 为什么接

现有数据链路的缺口与不稳点（详见 `docs-stm/manuals/datasource-reliability.md`）：

| 现状 | 问题 |
|---|---|
| 穿透基金持仓：天天基金 HTML 主 + 季度 API 兜底 | 爬虫链路，7 天缓存，长期 `★★★☆☆`，常有降级；`plan-47`（基金 ROE 加权）需要**全量穿透**，现穿透层只保留 top10 |
| 财务指标：akshare `stock_financial_abstract` 主源 | 第三方爬虫封装，上游接口漂移会直接打断主源 |
| 行情：腾讯 → 新浪 → 过期缓存 | 两个非官方源互为备份，缺第三个正交链路 |
| 估值 / 交易日历 / 公司行动 | 估值现值来自行情+财务拼算；交易日历为自实现原语；公司行动（分红送转配股）无数据源 |
| 市场情绪（涨跌停/连板/龙虎榜/异动/热榜） | **完全没有** |

同花顺官方 API 的价值：**官方源**（非爬虫）、**不限累计调用次数**（仅按负载动态限流）、字段级契约明确（snake_case + 毫秒时间戳 + 显式 `currency`）。

**明确的覆盖边界（官方文档声明，不可误用）**：分钟 K / tick、**海外行情**、**宏观数据**、**新闻公告原文与研报**。因此：
- **不能**替代 DataSinking 的财报全文链路（区块② 的缺口仍由 `plan.md` 的财报第二数据源项承接）；
- QDII 穿透中的美股（MU/NVDA 等）仍走既有美股链路；
- 估值只给**现值**快照（无历史）→ 「真实估值分位」仍需历史序列，本源只提升现值稳定性。

---

## 2. 功能语义命名表

| 代码标识符 | 中文语义 |
|---|---|
| `providers/hithink.py` | 同花顺金融数据服务 provider（A 股行情/财务/基金/情绪面） |
| `SOURCE_ID = "hithink"` / `DISPLAY_NAME` | 数据源标识「hithink」/ 用户可见名「同花顺金融数据」 |
| `to_thscode()` | 项目代码 → 同花顺 thscode（`.SH`/`.SZ`/`.BJ`/`.OF`），场外基金由调用方以 `is_fund` 给语义（`00` 重叠区不可猜） |
| `fetch_financial_indicators()` | 单只 A 股指定报告期五类财务指标（成长/盈利/偿债/营运/现金流） |
| `fetch_income_statements()` / `fetch_balance_sheets()` / `fetch_cash_flow_statements()` | 利润表 / 资产负债表 / 现金流量表多期序列（`limit` 与 `start`+`end` 两模式互斥） |
| `fetch_valuation_snapshot()` | 估值快照（PE-TTM/MRQ、PB-MRQ、PS-TTM、PCF-TTM；单次 ≤100 代码，无历史） |
| `fetch_price_snapshot()` / `fetch_price_history()` | 行情快照（批量/全市场分页）/ 历史日 K（±10 年窗口，支持前/后复权） |
| `fetch_trading_days()` | 近一年交易日序列（固定窗口，无入参） |
| `fetch_adjustment_factors()` | 复权因子事件流（现金分红/送股/配股） |
| `fetch_index_constituents()` | 同花顺指数 / 板块成分股（含沪深 300 等标准指数） |
| `fetch_limit_up_ladder()` / `fetch_dragon_tiger_list()` | 连板天梯 / 龙虎榜（全部·机构榜·游资榜） |
| `fetch_fund_portfolio_holdings()` / `fetch_fund_stock_history()` / `fetch_fund_nav()` | 基金最新披露持仓 / 历史股票持仓 / 净值序列 |
| `reset_hithink_limiter()` | 重置限速器单例（测试隔离与配置热更新） |

---

## 3. 阶段划分

### 阶段 1 ✅ provider 层（已实现 + 实测通过，见 §4.1）

`providers/hithink.py`：凭据声明（`CredentialSpec`，节名 `hithink`，环境变量 `HITHINK_FINANCE_API_KEY`）、
限速器（间隔 = 1/qps，默认 3，可经 `config.json` 的 `hithink.qps` 覆盖）、
响应信封解析（`code != 0` → 按 `_ERROR_HINTS` 记 WARNING 返回空）、
**触发限流不立即重试**（遵循官方指引，与 datasink 的「退避重试一次」策略相反）、
16 个域接口函数（只取原始响应，不做字段归一）、`to_thscode()` 映射。

单测 52 例：凭据门禁 / 限速先于请求 / 信封与错误码 / HTTP 分支（429 不重试）/ thscode 映射 / 各域路径与参数（含 `limit` 与 `start+end` 互斥）。

### 阶段 2 ✅ 财务指标域（第三链路）

- **实现**：`analysis/financial_statement_derive.py::derive_indicator_records`（三张合并报表 → 标准字段，纯函数）
  + `fetcher/financial_indicator_adapters.py::HithinkIndicatorAdapter`（链路第三槽，单期）
  + `fetcher/financial_indicator.py::fetch_hithink_indicator_series`（**多期**回退：三张报表各一次请求即得近若干期，
  使趋势/质量档在同源序列上仍可算——优于链路单期兜底）。
- **映射口径**（放弃逐项映射 `index_id`，改为从**报表原值派生**）：营收=营业收入、归母净利=归属于母公司股东的净利润
  （缺失回退合并净利）、经营现金流=经营活动现金流净额、EPS=基本每股收益；毛利率=(营业收入−营业成本)/营业收入、
  负债率=负债合计/资产合计、ROE=归母净利/归母权益（期末口径）；同比=与**上年同期**比较（同文种、报告期减一年）。
- **报告期口径（关键实测修正）**：上游季度条目的 `period_end_ms` 是**披露窗口起点**（2026Q1 = 04-01）而非报告期末，
  故改用 `fiscal_year`+`fiscal_period` 归一为标准季末（Q1→03-31 / Q2→06-30 / Q3→09-30 / Q4→12-31），
  与主源 akshare 的报告期完全对齐（否则同报告期对不上，同比与趋势比较都会错位）。
- **实测（长江电力 600900）**：报告期序列与主源一致；2026-06-30 各项数值与主源一致（营收 379.29 亿、归母 147.56 亿、
  毛利率 57.89%、负债率 59.36%、经营现金流 241.28 亿、EPS 0.6031、营收同比 0.033562）；差异仅 ROE（6.47% 期末 vs 6.55% 加权）
  与 `bvps` 恒缺失（官方资产负债表不提供总股本）。
- **收益**：主源失效时不必依赖 DataSinking 的章节解析支路，且保住**多期趋势**能力。
- **收尾待办**：PE/PB 口径修正（`rf-386`）——需为指标契约新增 `pe_ttm`/`pb_mrq` 字段并同步附录 H 与双端渲染，
  本次未做（避免顺手改契约）。

### 阶段 3 ✅ 基金披露持仓域（已实施）

- 链路：`fetcher/chain.py::_DEFAULT_CHAINS["fund_hold"] = ["tiantian", "hithink"]`，provider 表
  `fetcher/fund.py::_FUND_HOLD_PROVIDERS` 同序（天天基金主 → 同花顺官方备，需 key）。
- **载荷归一**：`_normalize_hold_payload`（按形状识别）——天天基金形态原样透传（主源可用时输出逐字不变）；
  同花顺形态映射为 `code/name/date/holdings`：只取 `asset_type=stock`（债券/基金资产不进股票层）、
  `hold_ratio`→`ratio`、报告期取 `end_date_ms`（回退 `publish_date_ms`）→ `YYYY-MM-DD`。
- **联接基金信号**：`providers/hithink.py::fetch_fund_holdings` 在「持仓仅一只 `fund` 型资产」时直返
  `feeder_target_code`，既有 `feeder_penetration` 链路据此穿透（省去 HTML 探测）。
- **代码候选解析**：`fund_thscode_candidates`（补零 + 场内/场外后缀，逐个试到命中）——实测 `16055.OF`
  报 `code=3001`、`016055.OF` 命中（仓库读取层已补零，此处为防御）。
- **不递增 `hold_schema`**：缓存写入前必经归一，载荷恒为同一形态，旧条目不会被误读；递增只会让全体用户白缓存失效。
- 实测：股票型 `011506.OF` / QDII `017730.OF`（含 AMD/MU/KLAC）/ ETF `561910.SH` 均返回 10 项股票持仓；
  联接基金 `016055.OF` → 单只 `fund` 型（`513390.SH` 博时纳斯达克100ETF）；债券型 `012325.OF` 仅 `bond`
  持仓 → 股票层为空（与天天基金「股票表为空」同口径）。
- **阶段 3 收尾待办**：① 用同花顺**历史**持仓接口（`/portfolio/stock-history`）支撑 `plan-47` **全量穿透**
  （现披露持仓仅前 10 大）；② 与天天基金做同基金占比/报告期交叉校验（校准容差）。

### 阶段 4 ✅ 行情 / 日历 / 公司行动（复权因子消费待接）

- **行情第三槽**：`price_stock` = 腾讯 → 新浪 → **同花顺**；新增
  `HithinkQuoteAdapter`（别名 `last_price`→`price`、`prev_price`→`yesterday_close`，
  不提供总市值 → `None`）。实测 600900：价 28.44 / 昨收 28.46 / 价格日 2026-09-17。
- **历史日 K 第三槽**：`history_stock` = 腾讯 → 新浪 → **同花顺**（`_HISTORY_PROVIDER_MAP`
  注册 `src.python.providers.hithink`），`providers/hithink.fetch_kline(code, days, start_from)`
  取**前复权**日 K 并对齐既有 provider 形态（`{date, open, close, high, low, volume}` 升序）。
  **实测坑**：上游历史 K 线日期字段是 `date_ms`（行情快照才是 `timestamp`），混用会解析出 0 条。
- **交易日历官方兜底**：`core/trading_calendar._get_trading_calendar()` 在 akshare 失败后尝试
  `calendar/trading-days`（惰性导入 providers，避免 core→providers 层次反转；再失败才走简易周度判断）。
  实测官方序列 243 个交易日。
- **待接消费者**：`adjustment_factors`（复权因子事件流）目前无生产消费者——计划用于
  **分红流水漏记校验**（用官方除权除息事件与用户「分红流水」页签交叉核对），属阶段收尾项。

### 阶段 5 ⬜ 情绪面新章节（新能力）

- 新数据域 `market_sentiment`（涨跌停池 / 连板天梯 / 龙虎榜）+ 报告章节「市场情绪与资金热点」，
  **功能开关默认关**；可选把「持仓/穿透标的当日上榜、所属概念连板」注入既有 LLM 信号预消化
  （`signal_pre_digest` 机制），与「财经新闻热点与持仓关联」章节互补。
- 需先定契约（新域 → `schemas/datasource_fields.py` 登记 + 附录 H + 双端可见性一致性测试）。

---

## 4. 验证计划（拿到 key 后逐项做）

1. 连通性与字段实测：对 `600519.SH`/`600900.SH`/`000001.SZ` 跑通各域接口，核对字段名与文档一致性（阶段 2~4 的映射据此校准）。
2. 限流行为：确认软限流触发形态（HTTP 429 / `code=4001`）与我们的日志/降级表现。
3. 交叉校验：估值 PE/PB 与东财口径比对；基金披露持仓与天天基金比对（报告期、占比、股票集合）。
4. 报告回归：开启对应开关跑一次完整报告，核对新区块/新链路与 `dev-verify` 门禁。

---
## 4.1 实测结果（2026-09-16，key 已配置）

**连通性**：11 个端点实测，**10 个成功**；失败 1 个：`/api/a-share-index/constituents/ths-stock-list` 连续两次 429（同时段其他端点正常，退避 3s 后仍 429）→ 判定为**该接口独立限流或权限要求更高**，阶段 4 接入前需复核。

**关键字段结构（实测，可直接用于阶段 2/3 映射）**：

| 端点 | 实测结构 |
|---|---|
| `financials/indicators` | `{thscode, report, abilities:[{ability, indicators:[{index_id, value}]}]}`；实测五类：`growth`(4) / `profitability`(5) / `solvency`(5) / `operation`(5) / `cash-flow`(4)，`index_id` 形如 `calculate_operating_income_yoy_growth_ratio`、`total_assets_net_ratio`、`current_ratio`、`total_assets_turnover_ratio`、`net_profit_cash_content`（**全量清单待阶段 2 落表**） |
| `financials/income-statements` | `item[{thscode, ticker, period, fiscal_year, fiscal_period, report_date_ms, period_end_ms, currency, operating_income, operating_costs, ...}]` |
| `valuations/snapshot` | `item[{thscode, ticker, name, pe_ttm, pe_mrq, pb_mrq, ps_ttm, pcf_ttm}]` |
| `prices/snapshot` | `item[{thscode, ticker, volume, turnover, last_price, price_change, price_change_ratio_pct, open_price, high_price, low_price, prev_price}]` |
| `corporate-actions/adjustment-factors` | `item[{ticker, ex_date_ms, dividend_per_share, per_share_bonus}]`（长江电力 26 条事件） |
| `fund/portfolio/holdings` | 汇总 `{total_stock_ratio_pct, stock_ratio_pct, main_industry, concentration_ratio}` + `item[{thscode, ticker, stock_name, hold_ratio, asset_type, position_capital, position_count, security_market_value_rate_pct, period_increase_rate_pct, investment_rank, start_date_ms, ...}]`；实测 建信高端装备(011506.OF) 10 项（华峰测控 9.53% / 长川科技 8.95% / 中际旭创 7.39%），报告期 2026-04-01（2026Q1 披露） |
| `fund/performance/nav` | `item[{nav_date, unit_nav, adj_nav}]` |
| `special-data/dragon-tiger-list` | `{timestamp, board_type, trade_date, count, stock_count, stock_items[{thscode, ticker, name, concept_list, change, net_value, net_rate, hot_rank, buy_value, sell_value, limit_reason, range_days, org_net_value}], hot_money_items}`；实测 2026-09-16 共 73 条 |
| `special-data/limit-up-ladder` | `{window:{length, date_list, board_caps}, item[{date, boards}]}` 近 30 个交易日 |
| `calendar/trading-days` | `item[{date_ms, date}]`，实测 243 个交易日 |

**限流实测**：默认 3 qps 时连续拉取 11 个端点即触发 429 → **默认 qps 下调为 2.0**（`config.json` 的 `hithink.qps` 可覆盖），并保持「触发限流不立即重试」策略。

**口径差异发现（重要）**：项目现有「当前 PE/PB」是**自算**（现价 ÷ 报告期 EPS/BVPS），与官方 TTM/MRQ 口径不可比——长江电力实测：项目报告 47.19（半年报 EPS 口径）vs 官方 `pe_ttm` 19.17；PB 一致（3.22 vs 3.21）。阶段 2 应以官方 `pe_ttm`/`pe_mrq`/`pb_mrq` 为准（并顺带获得 `ps_ttm`/`pcf_ttm` 两个新维度）。
## 5. 架构约束自查（对照 `technical.md` 架构设计约束）

- **不新造取数路径**：provider 只取原始响应；字段归一交 `source_adapter`，缓存/熔断/降级交 `fetcher/chain`（C-取数链路分层）。
- **契约台账**：新增域（阶段 5）须登记 `DOMAIN_RECORDS` + 附录 H + 双端一致性测试；阶段 2~4 复用既有域，不改契约。
- **开关默认关**：阶段 5 新章节挂 Feature Flag（默认关），关闭时输出与引入前逐字节一致。
- **凭据安全**：只读密钥文件/环境变量，值不落日志、报告、缓存（R-CRD-07）。
- **测试隔离**：新增单例（限速器）已在 `src/test/conftest.py` 增加 autouse 重置 fixture；无新增持久化状态文件。

---

## 6. 风险

- **未实测**：无 key 时接口路径/字段可能有偏差（文档聚合版与线上实现存在滞后可能）→ 阶段 2 起必须实测校准后再写映射表。
- **官方能力边界**：财报全文/新闻原文/海外行情不可得（见 §1），不要用它接 `plan.md` 的财报第二数据源。
- **限流策略**：官方「不限累计调用次数」但保留动态限流，故我们不重试、只降级；若后续被限流频繁命中，改为按 `config.json` 的 `hithink.qps` 降速并加失败退避。
