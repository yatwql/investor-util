# 数据源一览

## 数据源与缓存对照

| 用途 | 主链路 | 备用链路 | 缓存前缀 | 分组 |
|:-----|:-------|:---------|:---------|:-----|
| 场内 A 股/ETF 实时价 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `price_` | 持仓类 |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` | `price_` | 持仓类 |
| A 股指数行情 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `index_` | 持仓类 |
| 美股指数行情 | 新浪财经 `hq.sinajs.cn`（gb_* 前缀） | 腾讯财经 `qt.gtimg.cn` | `index_` | 持仓类 |
| 基金业绩排名 | 天天基金 `fund.eastmoney.com`（`pingzhongdata/{code}.js` JS 变量解析） | — | `fund_perf_` | 基础类 |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com`（HTML 解析） | — | `fund_hold_` | 基础类 |
| 基金经理数据 | 东方财富 `fund.eastmoney.com/{code}.html`（HTML 解析） | 天天基金 `fundf10.eastmoney.com/jjjl_{code}.html` | `fund_manager_` | 基础类 |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业 + 概念板块归属） | 东方财富 REST 行情页（仅行业，无概念） | `industry_` | 基础类 |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — | `profit_forecast_` | 基础类 |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — | `sector_flow_` | 基础类 |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — | `dividend_` | 基础类 |
| 无风险利率（Rf） | akshare `bond_zh_us_rate`（国债收益率） | config.json 手动配置兜底 | `bond_yield_rf`¹ | 基础类 |
| 财经新闻（5 源聚合） | 新浪 + 东方财富 + 财联社 + 华尔街见闻 + akshare 并行获取，统一聚合去重 | — | `news_` | 基础类 |
| 股票/ETF 历史日线 | 腾讯财经 K 线接口 | 新浪财经 K 线接口 | `history_stock_` | 历史走势 |
| 场外基金历史净值 | 天天基金 `pingzhongdata/{code}.js` | 东方财富 `api.fund.eastmoney.com/f10/lsjz`（分页获取） | `history_fund_otc_` | 历史走势 |
| 指数历史日线 | 腾讯财经 K 线接口 | 新浪财经 K 线接口 | `history_index_` | 历史走势 |
| 持仓重合度 | 在线计算（基于持仓基金前 10 大重仓股的 Jaccard 相似度） | — | `fund_overlap_` | 基础类 |
| 基金风格扩展数据（市值/PE） | 东方财富 + 天天基金（基金持仓市值风格 + 市盈率/市净率数据） | — | `extended_` | 基础类 |

> **缓存前缀**列对应 `data/cache/` 目录下的文件名前缀，同一前缀的文件按 TTL 统一管理。
> ¹ `bond_yield_rf` 为精确缓存键名（`exact_cache_keys`），非前缀匹配，单独管理。
> 表中仅含具有 `cache_prefixes` 或 `exact_cache_keys` 的数据模块。此外还有少数 `exact_cache_keys` 模块，使用具体键名而非前缀匹配，不受 TTL 扫描清除影响（如 `trading_calendar`、`fund_benchmarks`、`holdings_tracking`、`fund_concentration_snapshot`、`fund_style_snapshot`、`fund_manager_snapshot`）。其中 `fund_benchmarks`、`fund_manager_snapshot` 等仍归属于缓存分组，可通过菜单 `[1]` 刷新。
> **分组**列对应菜单 `[1]`（基础类）/ `[2]`（持仓类）的缓存刷新范围。历史走势类不受菜单缓存命令影响，仅按 TTL 过期。

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
- **美股指数** → `history_index_us` 通道：新浪财经（`gb_*` 前缀） → 腾讯财经（备用，因腾讯 K-line API 不支持 `gb_*` 代码）
- **风格与因子分析·因子回归**（`analysis/factor_exposure.py`，写入 `style_factor_data` 契约）复用 `history_index` 通道，并行拉取 CSI 风格因子指数 K 线（价值=sh000919、成长=sh000925、质量=sh000930）与基准指数（沪深300 sh000300）做 OLS 回归。因子指数不注册到 `_A_INDICES`（避免污染实时指数循环 fetch_indices），无专属缓存前缀，随 `history_index_` 统一按 TTL 管理
- **风格与因子分析·行业 Beta 子表**（`analysis/industry_beta.py`，内嵌于 `style_factor_data.industry_beta`，开关 `report_submodules.industry_beta` 默认关）复用 `history_index` 通道拉取中证行业指数 K 线（`INDUSTRY_INDEX_MAP`：银行=sh000986、证券=sz399975、白酒/食品饮料=sz399997、半导体/电子=sz399995、有色/贵金属=sz399996、煤炭=sz399998、医药=sz399989、钢铁=sz399994、房地产=sh000980、能源=sh000928、环保=sz399973、保险=sz399983）做单因子 OLS（复用 `compute_factor_exposure`，不重复实现）；行业分类复用 `batch_fetch_industry_data`（`industry_` 前缀缓存）

### 实时行情

由 `fetcher/index.py` 内部路由（`fetch_indices` / `fetch_us_indices`）：

- **A 股指数** → 腾讯财经 → 新浪财经（备用）
- **美股指数** → 新浪财经 → 腾讯财经（备用）

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
| 股票/ETF 历史日线 | 交易日更新 | 包含前复权数据，含涨跌幅、成交量、换手率 |

---

## 常见问题

### 数据源不可用

| 现象 | 可能原因 | 处理方式 |
|:-----|:---------|:---------|
| 实时行情为空 | 非交易时段、股票停牌、数据源维护 | 自动使用备用链路，或使用过期缓存 |
| 基金净值未更新 | 当日净值尚未发布、节假日 | 程序自动使用前一日净值，日志记录 INFO |
| 新闻为空 | 网络异常、选中的新闻源全量不可用 | 自动跳过该源，其他源正常采集 |
| 行业资金流向为空 | 非交易日、数据源休息 | 显示占位，不影响其他数据模块 |

> 所有数据请求均经过 Provider Chain 处理：首次重试（最多 3 次）→ 熔断（持续失败时开启）→ 降级使用过期缓存（如有）。日志中 WARNING 级别的消息对应数据降级事件，属正常行为。

### akshare 兼容性

本程序依赖 **akshare**（`pyproject.toml` 锁定 `akshare==1.18.64`，兼容下限 `>= 1.16.0`）。akshare 接口更新较频繁，以下场景可能导致数据获取失败：

- akshare 版本过低 → 接口签名变更导致报错 → 执行 `pip install --upgrade akshare`
- akshare 版本过高 → 接口返回格式微调 → 如遇兼容问题，可先检查 `logs/app.log` 中的具体报错信息

如遇 akshare 相关报错，先升级 akshare 至最新版：`pip install --upgrade akshare`。

### 新闻源签名鉴权

财联社（`cls`）数据源默认关闭（`"cls": false`），因其需要签名鉴权，在部分网络环境下不可用。如需开启：
1. 在 `config.json` 中将 `news_sources.cls` 改为 `true`
2. 确保网络能直连 `www.cls.cn`
3. 如遇 403，说明签名鉴权失败，数据源不可用，请关闭该源
