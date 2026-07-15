# 数据源一览

| 用途 | 主链路 | 备用链路 |
|------|--------|----------|
| 场内 A 股/ETF 实时价 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 财经新闻（源1） | 新浪财经 `feed.mix.sina.com.cn` | — |
| 财经新闻（源2） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — |
| 财经新闻（源3） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | —（需签名鉴权，默认关闭） |
| 财经新闻（源4） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives` | — |
| 财经新闻（源5） | akshare 封装：财新网 `stock_news_main_cx()` + CCTV `news_cctv()` | — |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn`（s_* 前缀） |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析，gb_* 前缀） | 腾讯财经 `qt.gtimg.cn` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业分类 + 概念板块归属） | 行情页 `quotedata` 解析（仅行业，无概念） |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — |
| 股票/ETF 历史日线 | 腾讯财经 `qt.gtimg.cn`（`f_day` 查询） | 新浪财经 `hq.sinajs.cn`（`hq_f_day` 查询） |
| 场外基金历史净值 | 天天基金 `fundf10.eastmoney.com` `lsjz` 净值列表 | 东方财富 `api.fund.eastmoney.com` 历史净值接口 |

> **架构说明：** 指数数据由 `fetcher/index.py` 直接调用对应 API（不经过 Provider Chain）。A 股指数：腾讯→新浪备用→过期缓存；美股指数：新浪（2 次重试）→腾讯备用→过期缓存。历史走势数据由 `report/portfolio_history.py` 内部路由到对应 Provider 的 history 接口（`_fetch_with_incremental_fallback`），走双链路 fallback。
