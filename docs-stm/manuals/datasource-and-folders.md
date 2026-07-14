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

---

## 目录结构

```
investor-util/
│
├── src/                              # 源代码
│   ├── python/                       # 主程序代码
│   │   ├── cache/                    #   缓存引擎（TTL/清理/统计/分组）
│   │   ├── config/                   #   配置管理（config.json / llm_settings / llm_key）
│   │   ├── fetcher/                  #   数据获取调度（价格/指数/行业/基金/快照）
│   │   ├── providers/                #   数据源提供商（腾讯/东方财富/天天基金/新浪/akshare/新闻多源）
│   │   ├── schemas/                  #   数据模型定义
│   │   ├── llm/                      #   LLM 客户端（API 调用/提示词/缓存指纹/会话统计）
│   │   ├── report/                   #   报告生成（Excel + HTML，含各页签写入器）
│   │   ├── tmpl/                     #   HTML 报告模板
│   │   ├── main.py                   #   程序入口 + TUI 主循环
│   │   ├── registry.py               #   中央注册表（模块定义/TTL/分组）
│   │   ├── provider_registry.py      #   数据源注册中心（熔断器/会话缓存）
│   │   ├── models.py                 #   数据模型
│   │   ├── reader.py                 #   持仓 xlsx 读取
│   │   ├── code_utils.py             #   证券代码/类型判定
│   │   ├── market_hours.py           #   交易时段判断
│   │   ├── http_client.py            #   HTTP 客户端
│   │   ├── constants.py              #   全局常量/版本号
│   │   ├── logger.py                 #   日志模块
│   │   ├── tui*.py                   #   TUI 交互（菜单/键盘/辅助）
│   │   └── handlers_*.py             #   菜单命令实现（报告/缓存/配置）
│   │
│   └── test/                         # 测试套件
│       ├── unit/                     #   单元测试（8 个子组：providers/fetcher/llm/news/report/config/core/ui）
│       ├── integration/              #   集成测试（契约/隔离/流水线）
│       ├── scenario/                 #   场景测试（basic/resilience/extreme/llm/datetime）
│       ├── conftest.py               #   pytest 全局配置 + 标记注册
│       └── helpers.py                #   测试辅助工具
│
├── data/                             # 运行时数据
│   ├── holdings/                     #   持仓 xlsx 文件（用户放置）
│   ├── cache/                        #   API 响应缓存（自动生成，JSON/GZ）
│   ├── config/                       #   配置文件（config.json / llm_key.json / llm_settings.json）
│   └── history/snapshots/            #   持仓快照（自动生成，保留 60 天）
│
├── reports/                          # 报告输出（最新版 + 按日期归档）
├── logs/                             # 程序日志（app.log，自动轮转）
├── test-reports/                     # 测试报告（自动生成，按 mode 分组）
├── scripts/                          # 启动脚本 + 测试工具
│   ├── launch.ps1 / launch.sh        #   Windows / Linux 启动脚本
│   ├── test_runner.py                #   测试驱动（pytest 模式封装）
│   ├── check-test-markers.py         #   标记合规检查
│   └── check-version-consistency.py  #   版本号一致性检查
│
├── docs-stm/                         # 项目文档
│   ├── manuals/                      #   用户文档分册
│   ├── managements/                  #   管理文档（需求/设计/计划/测试标准/变更日志）
│   ├── plan/                         #   中间设计文件
│   ├── archive/                      #   历史归档
│   └── tmp/                          #   临时文件（git 忽略）
│
├── CLAUDE.md                         # AI 编程助手指引
├── README.md                         # 用户文档总入口
├── pyproject.toml                    # Python 项目元数据
├── requirements.txt                  # Python 依赖清单
└── .gitignore                        # Git 忽略规则
```

> 注意：目录树为主层级结构，具体源文件细节以代码仓库实际结构为准。测试文件数和文件行数随版本迭代变化。
>
> 最后更新：2026-07-14
