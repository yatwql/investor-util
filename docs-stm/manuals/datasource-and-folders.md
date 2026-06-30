# 数据源一览

| 用途 | 主链路 | 备用链路 |
|------|--------|----------|
| 场内实时/收盘价 | 腾讯财经 `qt.gtimg.cn` | 东方财富 `push2.eastmoney.com` |
| 场外基金净值 | 东方财富 `fundf.eastmoney.com` | 天天基金 `fundgz.1234567.com.cn` |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 财经新闻（源1） | 新浪财经 `feed.mix.sina.com.cn` | — |
| 财经新闻（源2） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — |
| 财经新闻（源3） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — |
| 财经新闻（源4） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives` | — |
| 财经新闻（源5） | akshare 封装：财新网 `stock_news_main_cx()` + CCTV `news_cctv()` | — |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | — |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析） | — |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业分类 + 概念板块归属） | — |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — |

---

# 目录结构

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── python/                   # 源代码
│   │   ├── __init__.py
│   │   ├── main.py               # 入口
│   │   ├── cache.py              # 缓存管理
│   │   ├── config.py             # 配置文件管理
│   │   ├── fetcher/               # 数据获取路由（子包：chain/price/index/fund/industry）
│   │   ├── llm/                  # LLM 客户端（9 子模块：api/pricing/session/circuit_breaker/fingerprint/markdown/generators/prompts/skeleton）
│   │   ├── constants.py          # 共享常量
│   │   ├── logger.py             # 日志模块
│   │   ├── models.py             # 数据模型
│   │   ├── reader.py             # 持仓读取
│   │   ├── tui.py                # TUI 主循环
│   │   ├── tui_menu.py           # 菜单交互
│   │   ├── tui_handlers.py       # 菜单功能执行
│   │   ├── providers/            # 数据源提供商
│   │   │   ├── __init__.py
│   │   │   ├── akshare_extras.py
│   │   │   ├── akshare_news.py
│   │   │   ├── cls_news.py
│   │   │   ├── eastmoney.py
│   │   │   ├── eastmoney_industry.py
│   │   │   ├── eastmoney_news.py
│   │   │   ├── news_aggregator.py
│   │   │   ├── news_correlator.py
│   │   │   ├── news_keywords.py
│   │   │   ├── news_sources.py
│   │   │   ├── sina.py
│   │   │   ├── sina_news.py
│   │   │   ├── tencent.py
│   │   │   ├── tiantian.py
│   │   │   └── wallstreetcn_news.py
│   │   ├── report/               # 报告生成
│   │   │   ├── __init__.py
│   │   │   ├── category.py
│   │   │   ├── early_warning.py        # 智能预警（行业资金流向联动 + 新闻情绪聚合）
│   │   │   ├── excel_writer.py
│   │   │   ├── fund_performance.py
│   │   │   ├── html_writer.py
│   │   │   ├── llm_content.py
│   │   │   ├── market_value.py
│   │   │   ├── news_correlation.py
│   │   │   ├── penetration.py
│   │   │   ├── styles.py
│   │   │   └── summary.py
│   │   └── tmpl/
│   │       └── report_template.html
│   └── test/                     # 测试
│       ├── __init__.py
│       └── test_*.py (26 个)
├── data/
│   ├── holdings/                 # 持仓 xlsx 文件
│   ├── cache/                    # API 响应缓存
│   └── config/                   # 配置文件（config.json, llm_key.json, llm_settings.json）
├── reports/                      # 生成报告（最新版+按日期存档）
├── logs/                         # 程序日志（app.log）
├── docs-stm/                     # 项目管理文档
│   ├── plan/                     # 计划/设计文件
│   ├── manuals/                  # 用户文档分册
│   ├── tmp/                      # 临时/过程文件
│   └── managements/
│       ├── plan.md               # 实现计划
│       ├── requirements.md       # 需求文档
│       ├── testplan.md           # 测试计划
│       ├── changelog.md          # 变更日志
│       └── review-findings.md    # 自审记录
├── scripts/
│   ├── launch.ps1                # Windows 启动脚本
│   └── launch.sh                 # Linux 启动脚本
├── CLAUDE.md                     # Claude Code 指引
├── README.md                     # 用户文档（总入口）
└── requirements.txt
```
