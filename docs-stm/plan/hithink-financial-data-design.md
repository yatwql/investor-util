# 同花顺金融数据服务接入设计（hithink）

> 版本：0.11.1-dev ｜ 状态：**阶段 1 已实现**（provider 层 + 52 例单测）；阶段 2~5 待实施（需 API key 实测校准字段）
> 上游：<https://github.com/HiThink-Tech/Financial-API>（同花顺官方 A 股数据服务）
> 契约来源：<https://fuyao.aicubes.cn/llms-full.txt>（完整接口文档聚合）

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

### 阶段 1 ✅ provider 层（已实现）

`providers/hithink.py`：凭据声明（`CredentialSpec`，节名 `hithink`，环境变量 `HITHINK_FINANCE_API_KEY`）、
限速器（间隔 = 1/qps，默认 3，可经 `config.json` 的 `hithink.qps` 覆盖）、
响应信封解析（`code != 0` → 按 `_ERROR_HINTS` 记 WARNING 返回空）、
**触发限流不立即重试**（遵循官方指引，与 datasink 的「退避重试一次」策略相反）、
16 个域接口函数（只取原始响应，不做字段归一）、`to_thscode()` 映射。

单测 52 例：凭据门禁 / 限速先于请求 / 信封与错误码 / HTTP 分支（429 不重试）/ thscode 映射 / 各域路径与参数（含 `limit` 与 `start+end` 互斥）。

### 阶段 2 ⬜ 财务指标域（第三链路 → 可升主源）

- 新增 `fetcher/financial_indicator_adapters.py::HithinkIndicatorAdapter`，把
  `financials/indicators` 的五类 `index_id`/`value` 映射到既有 `FinancialIndicatorFields`。
- **前置实测项**：文档只给「五类指标」分类，**具体 `index_id` 字段名清单需拉官方指标表 +
  用真实响应校准**（无 key 无法确认，故不先写死映射表）。
- 收益：akshare 主源失效时不必依赖 DataSinking 的章节解析支路。

### 阶段 3 ⬜ 基金披露持仓域（收益最大）

- 现穿透链路是「天天基金专用路径」（`providers/tiantian_holdings.py` + `fetcher/fund.py`），
  本阶段把它改为**两源链**：`hithink`（官方披露持仓，含历史）与 `tiantian`（既有行为）互为备份。
- 缓存归 `fund_hold_` 前缀，沿用 `hold_schema` **载荷语义版本**闸门（跨源字段形态不同 → 版本号区分，防旧载荷遮蔽）。
- **实测项**：交叉校验同一基金的持仓占比与报告期（对齐 `plan-47` 的全量穿透需求评估）。

### 阶段 4 ⬜ 行情 / 日历 / 公司行动

- `fetcher/quote_adapters.py::HithinkQuoteAdapter` → quote 域**第三链路**（腾讯→新浪→同花顺）。
- 历史日 K 的**前/后复权**可作为组合历史走势/回撤的复权口径来源。
- `fetch_trading_days()` 校准 `core/trading_calendar.py`；`fetch_adjustment_factors()` 供持仓成本
  与「年均股息」列交叉校验。

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
