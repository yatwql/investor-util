# 数据源一览

## 数据源与缓存对照

| 用途 | 主链路 | 备用链路 | 缓存前缀 | 分组 |
|:-----|:-------|:---------|:---------|:-----|
| 场内 A 股/ETF 实时价 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `price_` | 价格 |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` | `fund_nav_` | 价格 |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — | `fund_perf_` | 基础 |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — | `fund_holding_` | 基础 |
| 财经新闻（新浪） | 新浪财经 `feed.mix.sina.com.cn` | — | `news_sina_` | 新闻 |
| 财经新闻（东方财富） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — | `news_eastmoney_` | 新闻 |
| 财经新闻（财联社） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | —（需签名鉴权，默认关闭） | `news_cls_` | 新闻 |
| 财经新闻（华尔街见闻） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives` | — | `news_wallstreetcn_` | 新闻 |
| 财经新闻（akshare 封装） | akshare：财新网 `stock_news_main_cx()` + CCTV `news_cctv()` | — | `news_akshare_` | 新闻 |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn`（s_* 前缀） | `index_` / `query_` | 价格 |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（gb_* 前缀 JS 变量解析） | 腾讯财经 `qt.gtimg.cn` | `index_us_` / `query_` | 价格 |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业 + 概念板块归属） | 行情页 `quotedata` 解析（仅行业，无概念） | `industry_` | 基础 |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — | `forecast_` | 基础 |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — | `sector_flow_` | 基础 |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — | `dividend_` | 基础 |
| 股票/ETF 历史日线 | 腾讯财经 `qt.gtimg.cn`（`f_day` 查询） | 新浪财经 `hq.sinajs.cn`（`hq_f_day`） | `history_` | 历史走势 |
| 场外基金历史净值 | 天天基金 `fundf10.eastmoney.com` `lsjz` 净值列表 | 东方财富 `api.fund.eastmoney.com` 历史净值 | `fund_nav_history_` | 历史走势 |

> **缓存前缀**列对应 `data/cache/` 目录下的文件名前缀，同一前缀的文件按 TTL 统一管理。
> **分组**列对应菜单 `[1]`（基础类）/ `[2]`（持仓类）的缓存刷新范围。

---

## 数据源路由说明

### 指数历史 K 线

由 `fetcher/index.py` 通过 Provider Chain 获取（`fetch_with_incremental_fallback`）：

- **A 股指数** → `history_index` 通道：腾讯财经 → 新浪财经（备用）
- **美股指数** → `history_index_us` 通道：新浪财经（`gb_*` 前缀） → 腾讯财经（备用，因腾讯 K-line API 不支持 `gb_*` 代码）

### 实时行情

由 `report/portfolio_history.py` 内部路由：

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
| 财经新闻 | 实时推送 | 5 源聚合去重，部分源可能有 1~5 分钟延迟 |
| 行业分类 | 季度更新 | 东方财富三级行业分类，含概念板块归属 |
| 机构盈利预测 | 不定期更新 | 基于券商研报汇总，时效性取决于研报发布时间 |
| 行业资金流向 | 交易日实时 | akshare 今日排名，非交易日或盘前为空 |
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

本程序依赖 **akshare >= 1.16.0**。akshare 接口更新较频繁，以下场景可能导致数据获取失败：

- akshare 版本过低 → 接口签名变更导致报错 → 执行 `pip install --upgrade akshare`
- akshare 版本过高 → 接口返回格式微调 → 如遇兼容问题，可先检查 `logs/app.log` 中的具体报错信息

如遇 akshare 相关报错，先升级 akshare 至最新版：`pip install --upgrade akshare`。

### 新闻源签名鉴权

财联社（`cls`）数据源默认关闭（`"cls": false`），因其需要签名鉴权，在部分网络环境下不可用。如需开启：
1. 在 `config.json` 中将 `news_sources.cls` 改为 `true`
2. 确保网络能直连 `www.cls.cn`
3. 如遇 403，说明签名鉴权失败，数据源不可用，请关闭该源
