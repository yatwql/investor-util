# 数据源一览

## 数据源与缓存对照

| 用途 | 主链路 | 备用链路 | 缓存前缀 | 分组 |
|:-----|:-------|:---------|:---------|:-----|
| 场内 A 股/ETF 实时价 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` → **同花顺金融数据**（官方快照，需 key；带官方 `pe_ttm`） | `price_` | 持仓类 |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` | `price_` | 持仓类 |
| A 股指数行情 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `index_` | 持仓类 |
| 美股指数行情 | 新浪财经 `hq.sinajs.cn`（gb_* 前缀） | 腾讯财经 `qt.gtimg.cn` | `index_` | 持仓类 |
| 基金业绩排名 | 天天基金 `fund.eastmoney.com`（`pingzhongdata/{code}.js` JS 变量解析） | — | `fund_perf_` | 基础类 |
| 基金持仓数据 | 天天基金 `fund.eastmoney.com/{code}.html`（HTML 解析） | 天天基金 `fundf10.eastmoney.com`（季报 API `FundArchivesDatas.aspx`，回溯 4 个季度）→ **同花顺金融数据**（官方披露持仓，需 key；联接基金直返目标 ETF） | `fund_hold_` | 基础类 |
| 基金经理数据 | 天天基金 `fund.eastmoney.com/{code}.html`（HTML 解析，与基金业绩排名同源） | 天天基金 `fundf10.eastmoney.com/jjjl_{code}.html`（档案页） | `fund_manager_` | 基础类 |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业 + 概念板块归属） | 东方财富 REST 行情页（仅行业，无概念） | `industry_` | 基础类 |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — | `profit_forecast_` | 基础类 |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — | `sector_flow_` | 基础类 |
| 股票历史分红 | akshare `stock_history_dividend()` 无参全量拉取后按代码过滤 | — | `dividend_` | 基础类 |
| 无风险利率（Rf） | akshare `bond_zh_us_rate`（国债收益率） | config.json 手动配置兜底 | `bond_yield_rf`¹ | 基础类 |
| 财经新闻（5 源聚合） | 新浪 + 东方财富 + 财联社 + 华尔街见闻 + akshare 并行获取，统一聚合去重 | — | `news_` | 基础类 |
| 股票/ETF 历史日线 | 腾讯财经 K 线接口 | 新浪财经 K 线接口 → **同花顺官方日 K**（前复权，需 key；支持增量起点） | `history_stock_` | 历史走势 |
| 场外基金历史净值 | 天天基金 `pingzhongdata/{code}.js` | 东方财富 `api.fund.eastmoney.com/f10/lsjz`（分页获取） | `history_fund_otc_` | 历史走势 |
| 指数历史日线 | 腾讯财经 K 线接口 | 新浪财经 K 线接口 | `history_index_` | 历史走势 |
| 持仓重合度 | 运行时推导（基于持仓基金前 10 大重仓股的 Jaccard 相似度） | — | —（复用 `fund_hold_`，无独立缓存前缀） | — |
| 基金风格扩展数据（市值/PE） | 东方财富 + 天天基金（基金持仓市值风格 + 市盈率/市净率数据） | — | `extended_` | 基础类 |
| 个股财报全文（持仓基本面章·区块②） | DataSinking `api.datasink.ing`（全文本财报 Markdown，仅 A 股，**需用户自备 key**） | — | `report_datasink_index_` / `report_datasink_doc_` | 基础类 |
| 个股财务指标（持仓基本面章·区块①） | akshare `stock_financial_abstract`（东方财富关键指标，宽表） | DataSinking「公司简介和主要财务指标」章节解析（`datasink_indicator`）→ **同花顺官方合并报表派生**（利润表/资产负债表/现金流量表，需 key；一次给多期） | `fin_indicator_` | 基础类 |
| A 股行情 / 财务 / 基金 / **市场情绪** | 同花顺金融数据服务 `fuyao.aicubes.cn`（官方源，**需用户自备 key**） | — | 行情/持仓/情绪面各域前缀（其中龙虎榜与连板天梯为 `sentiment` 类别**唯一源**） | 基础类 / 分析类 |

> **缓存前缀**列对应 `data/cache/` 目录下的文件名前缀，同一前缀的文件按 TTL 统一管理。持仓重合度为运行时推导模块（复用 `fund_hold_` 缓存），无独立缓存前缀。
> ¹ `bond_yield_rf` 为精确缓存键名（`exact_cache_keys`），非前缀匹配，单独管理。
> 表中仅含具有 `cache_prefixes` 或 `exact_cache_keys` 的数据模块。此外还有少数 `exact_cache_keys` 模块，使用具体键名而非前缀匹配，不受 TTL 扫描清除影响（如 `trading_calendar`、`fund_benchmarks`、`holdings_tracking`、`fund_concentration_snapshot`、`fund_style_snapshot`、`fund_manager_snapshot`）。其中 `fund_benchmarks`、`fund_manager_snapshot` 等仍归属于缓存分组，可通过菜单 `[1]` 刷新。
> **分组**列对应菜单 `[1]`（基础类）/ `[2]`（持仓类）的缓存刷新范围。历史走势类不受菜单缓存命令影响，仅按 TTL 过期。
> **行业名归一化**：行业分类数据在入库时剥离行业名末尾的申万层级后缀（Ⅰ/Ⅱ/Ⅲ/Ⅳ，如「银行Ⅱ」「白酒Ⅱ」）——该后缀是申万分层命名标记，对零售报告读者是纯噪声，报告展示统一用剥离后的行业名（如「银行」「白酒」）。
> **财报全文两级缓存**：`report_datasink_index_`（报告元数据，TTL 两周）/ `report_datasink_doc_`（章节正文，TTL 一月）；两者均归「基础类」，随菜单 `[1]` 与 TTL 管理。

### LLM 模块缓存

LLM 分析结果独立缓存，通过指纹自动失效，不占用数据源请求链路：

| 模块 | 缓存前缀 | 默认 TTL | 分组 |
|:-----|:---------|:--------:|:-----|
| 全球政经局势 | `llm_global_macro_` | 24h | 持仓类 |
| 智囊团深度复盘 | `llm_expert_review_` | 2h | 持仓类 |
| 持仓体检报告 | `llm_health_check_` | 24h | 持仓类 |
| 穿透深度分析 | `llm_penetration_deep_` | 24h | 持仓类 |
| 财经新闻热点与持仓关联分析（LLM 二次关联） | `llm_news_item_` | 1h | 基础类 |
| 辩论模式三段缓存（pro/con/synthesis，实验功能） | `llm_debate_pro_` / `llm_debate_con_` / `llm_debate_synthesis_` | 24h | 持仓类 |

---

## 数据源路由说明

### 指数历史 K 线

由 `fetcher/index.py` 通过 Provider Chain 获取（`fetch_with_incremental_fallback`）：

- **A 股指数** → `history_index` 通道：腾讯财经 → 新浪财经（备用）
- **美股指数** → `history_index_us` 通道：新浪财经 → 腾讯财经。两者共用指数 K 线函数（`fetch_index_kline`），新浪侧实现位于 `providers/sina_kline.py`，但其 `getKLineData` 端点对全部代码返回 404/空，实际取数通常由腾讯完成；而腾讯 K 线接口对 `gb_*` 代码支持有限，因此该通道可能整链取空——空结果按正常降级记录（成因与现状见 `datasource-reliability.md` §4.2）
- **风格与因子分析·风格因子回归**（`analysis/style_factor_regression.py`，写入 `style_factor_data` 契约）复用 `history_index` 通道，并行拉取 CSI 风格因子指数 K 线（价值=sh000919、成长=sh000925、质量=sh000930）与基准指数（沪深300 sh000300）做 OLS 回归。因子指数不注册到 `_A_INDICES`（避免污染实时指数循环 fetch_indices），无专属缓存前缀，随 `history_index_` 统一按 TTL 管理
- **风格与因子分析·行业 Beta 子表**（`analysis/industry_beta.py`，内嵌于 `style_factor_data.industry_beta`，开关 功能开关 `industry_beta` 默认关）复用 `history_index` 通道拉取中证行业指数 K 线（`INDUSTRY_INDEX_MAP`：银行=sh000986、证券=sz399975、白酒/食品饮料=sz399997、半导体/电子=sz399995、有色/贵金属=sz399996、煤炭=sz399998、医药=sz399989、钢铁=sz399994、房地产=sh000980、能源=sh000928、环保=sz399973、保险=sz399983）做单因子 OLS（复用 `compute_factor_exposure`，不重复实现）；行业分类复用 `batch_fetch_industry_data`（`industry_` 前缀缓存）

### 实时行情

由 `fetcher/index.py` 内部路由（`fetch_indices` / `fetch_us_indices`）：

- **A 股指数** → 腾讯财经 → 新浪财经（备用）
- **美股指数** → 新浪财经 → 腾讯财经（备用）

### 同花顺金融数据服务（hithink）

- **用途与边界**：A 股行情快照 / 历史日 K（含前·后复权）、财务报表与五类财务指标、估值快照（PE/PB/PS/PCF，**仅现值无历史**）、交易日历、复权因子事件流、指数与板块成分股、公募基金披露持仓 / 历史持仓 / 净值、涨跌停与连板天梯、龙虎榜（全部·机构·游资）。**不含**：分钟 K/tick、**海外行情**、**宏观数据**、**新闻公告原文与研报** → 不可用于替代财报全文与新闻链路

- **鉴权**：用户自备 key（免费申领 <https://fuyao.aicubes.cn/admin/>），存通用密钥文件 `data/config/data_key.json` 的 `hithink` 节（`{"hithink": {"api_key": "..."}}`）或环境变量 `HITHINK_FINANCE_API_KEY`（优先）；缺 key 时链路主动跳过，不发请求

- **限流**：官方**不限累计调用次数**，按负载动态限流（HTTP 429 或信封 `code=4001`）。本程序每次请求前经 `RateLimiter`（间隔 = 1/qps，**默认 2（实测值：3 时连续拉 11 个端点即被 429）**，可经 `config.json` 的 `hithink.qps` 覆盖）；**命中限流不立即重试**（遵循官方指引），记 WARNING 后由链路降级

- **响应信封**：`{code, message, request_id, data}`，HTTP 状态码恒 200，业务错误看 `code`（`0` 成功；`2001` 凭据无效、`2003` 权限不足、`4001` 频率超限、`5003` 数据源不可用等）

- **实测（2026-09-16，key 已配置）**：11 个端点实测 10 通；`/api/a-share-index/constituents/ths-stock-list`（指数/板块成分股）两次 429 → 该接口限流更严或需更高权限，接入前复核。另发现官方估值口径为 TTM/MRQ，与项目自算 PE（报告期 EPS 口径）不可比（长江电力 19.17 vs 47.19）
- **已接入域**：**市场情绪**（龙虎榜 + 连板梯队 → 行动建议章内嵌块，开关 `market_sentiment`；只保留命中持仓/穿透标的代码的事件行，**无命中时该区块不显示**）、**行情**（`price_stock` 第三槽，官方快照）、**历史日 K**（`history_stock` 第三槽，前复权，支持增量）、**交易日历**（akshare 失败时的官方兜底）、**财务指标**（`financial_indicator` 链路**第三槽**：主源不可用时由三张官方合并报表派生多期指标，口径与主源对齐）、**基金披露持仓**（`fund_hold` 链路**备源**：天天基金全链不可用时接管，载荷经同一归一器落到同一契约；联接基金直接返回目标 ETF，省去 HTML 探测）。provider 层剩余域（复权因子事件流的消费方「分红流水漏记校验」）按 `plan.md` 计划表推进

> **在报告里怎么看同花顺有没被用上**：行情 / 历史日 K / 财务指标 / 基金持仓这几条链路里同花顺都是**末位兜底槽**（前序腾讯/新浪/天天基金/akshare 成功就不会轮到它），故「没出现在报告里」不等于「key 没生效」。看两列即可判定：① 可用性矩阵的**「命中源（本次取数）」**列——列出本次该类别实际服务的 provider 与次数（如 `同花顺金融数据 ×2`；全部命中缓存时显示 `—`），只有真的走到该源时才会点名；② 说明表的**「本次使用」**列——该类别本次有没有取到数据（含命中缓存）。两者并读即得「用了谁的数」与「有没有取到」。市场情绪是唯一以同花顺为**唯一源**的类别，其数据被取到时矩阵会出现「市场情绪」行、说明表出现同名行；若该区块空白，先看 `logs/app.log` 的 `[market_sentiment] 命中 N 条`——`N=0` 表示持仓/穿透标的当日未上榜（源已取到、只是无事件行），非故障。
### 财报全文（DataSinking）

由 `fetcher/financial_report.py` 逐标的取数、`report/financial_report_digest.py` 装配（章节 `financial_report_digest`，开关 功能开关 `financial_report_digest` 默认关）：

- **鉴权**：用户自备 key（免费 key 在 datasink.ing 领取），存通用密钥文件 `data/config/data_key.json` 的 `datasink` 节（`{"datasink": {"api_key": "..."}}`）或环境变量 `DATASINK_API_KEY`（优先）；缺 key 时链路主动跳过，章节写占位并给申请指引
- **取数**：`/documents`（元数据，年报优先、半年报兜底）→ `/documents/{id}?section=`（按配置 `datasink.sections` 逐章节取正文并拼接）→ 按 `datasink.max_chars` 截断；单篇正文经 Provider Chain + 财报域适配器两槽（复用缓存/熔断/降级）
- **限速与配额**：请求间隔 = 1/每秒上限（免费档 3 请求/秒、付费档 31），每次请求前经 `RateLimiter`；日配额计数存 `data/state/datasink_quota.json`（免费档 8,191 篇/日），超限即停并告警。免费档无批量端点，必然逐篇请求
- **仅 A 股**：沪（600/601/603/605/688/689）→ `.SS`、深（000/001/002/003/300/301）→ `.SZ`、北（43/83/87/92）→ `.BJ`

---

## 数据质量说明

| 数据类别 | 更新频率 | 数据质量说明 |
|:---------|:---------|:-------------|
| 场内实时价 | 日间实时（缓存 TTL 内可能延迟 15s~30s） | 腾讯/新浪官方行情，延迟 ≤ 3 秒 |
| 场外基金净值 | 每日 1 次（通常 19:00~22:00 更新） | 基金公司发布后同步至东方财富/天天基金 |
| 基金业绩排名 | 每日更新 | 基于前一日净值计算，百分位排名含 1/3/6/12 月多周期 |
| 基金持仓数据 | 季报更新（每年 4/8/10 月末） | 非实时，为最新披露的季报持仓（含前 10 大重仓 + 全部持仓明细） |
| 基金经理数据 | 不定期更新 | 基于基金公司公告，变更时同步至天天基金 |
| 财经新闻 | 实时推送 | 5 源聚合去重，部分源可能有 1~5 分钟延迟 |
| 行业分类 | 季度更新 | 东方财富三级行业分类，含概念板块归属 |
| 机构盈利预测 | 不定期更新 | 基于券商研报汇总，时效性取决于研报发布时间 |
| 行业资金流向 | 交易日实时 | akshare 今日排名，非交易日或盘前为空 |
| 无风险利率 | 每日更新 | akshare 获取中国 10Y 国债收益率，config 可手动覆盖 |
| 股票/ETF 历史日线 | 交易日更新 | 包含前复权数据（腾讯/新浪为主，同花顺官方前复权为第三链路），含开高低收与成交量（涨跌幅由相邻交易日收盘价推得；换手率另由组合两期持仓计算，取自行情 K 线之外） |
| 个股财报全文 | 定期报告披露后（法定延迟，QDII 更晚） | DataSinking 转 Markdown，来源为官方披露平台（cninfo/DART/EDINET/MOPS），仅 A 股；**取最新报告期（跨文种：年报/半年报/一季报/三季报）**，章节按文档实际清单匹配（季报自动取「主要财务数据」类章节）；报告期由接口返回，正文按配置截断；需自备 key |
| 个股财务指标 | 季报/年报披露后（随定期报告） | akshare 转结构化关键指标（营收/净利/同比/毛利率/ROE/负债率/现金流/EPS/每股净资产）；金额单位元、比率小数比例；无需凭据。备用支路从 DataSinking「公司简介和主要财务指标」章节解析；第三链路为**同花顺官方合并报表派生**（多期、口径与主源一致；报告期按财季归一到季末）。**PE/PB 口径**：官方源给出 `pe_ttm`/`pb_mrq` 时优先采用（TTM 口径），否则回退「现价 ÷ 报告期 EPS/BVPS」自算——跨源比较估值倍数前先看口径 |

---

## 常见问题

### 数据源不可用

| 现象 | 可能原因 | 处理方式 |
|:-----|:---------|:---------|
| 实时行情为空 | 非交易时段、股票停牌、数据源维护 | 自动使用备用链路，或使用过期缓存 |
| 基金净值未更新 | 当日净值尚未发布、节假日 | 程序自动使用前一日净值，日志记录 INFO |
| 新闻为空 | 网络异常、选中的新闻源全量不可用 | 自动跳过该源，其他源正常采集 |
| 行业资金流向为空 | 非交易日、数据源休息 | 显示占位，不影响其他数据模块 |
| 财报摘要为空 | 未配置 DataSinking key、无 A 股个股持仓/穿透标的、或该标的的报告在源侧缺目标章节（失败清单会写明「索引无该标的报告」或「目标章节缺失（已试报告期：…）」） | 章节写占位并给出申请指引；配置 `data/config/data_key.json` 的 `datasink` 节并开启 功能开关 `financial_report_digest` 后生效。最新一期缺章节时会自动回溯上一份报告（年报/半年报优先），章节接口不可用时会整篇下载后按关键词定位片段；银行股等源侧**完全未收录该期报告**的标的会退到可得的上一期并在失败清单如实列出原因 |

> 所有数据请求均经过 Provider Chain 处理：单个 provider 失败即切换链上下一个源 → 连续失败达阈值（3 次，行业链 6 次）后熔断该源 → 全部源不可用时降级使用过期缓存（如有）。日志中 WARNING 级别的消息对应数据降级事件，属正常行为。

### akshare 兼容性

本程序依赖 **akshare**（`pyproject.toml` 锁定 `akshare==1.18.64`）。akshare 接口更新较频繁，以下场景可能导致数据获取失败：

- akshare 版本过低 → 接口签名变更导致报错
- akshare 版本过高 → 接口返回格式微调

如遇 akshare 相关报错，先核对 `pyproject.toml` 锁定版本与 `logs/app.log` 中的具体报错信息，再决定是否调整版本并同步更新锁定。

### 新闻源签名鉴权

财联社（`cls`）数据源默认关闭（`"cls": false`），因其需要签名鉴权，在部分网络环境下不可用。如需开启：
1. 在 `config.json` 中将 `news_sources.cls` 改为 `true`
2. 确保网络能直连 `www.cls.cn`
3. 如遇 403，说明签名鉴权失败，数据源不可用，请关闭该源
