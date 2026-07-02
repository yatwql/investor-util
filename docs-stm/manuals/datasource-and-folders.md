# 数据源一览

| 用途 | 主链路 | 备用链路 |
|------|--------|----------|
| 场内实时/收盘价 | 腾讯财经 `qt.gtimg.cn` | 东方财富 `push2.eastmoney.com` |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 财经新闻（源1） | 新浪财经 `feed.mix.sina.com.cn` | — |
| 财经新闻（源2） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — |
| 财经新闻（源3） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — |
| 财经新闻（源4） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives` | — |
| 财经新闻（源5） | akshare 封装：财新网 `stock_news_main_cx()` + CCTV `news_cctv()` | — |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn`（s_* 前缀） |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析，gb_* 前缀） | 腾讯财经 `qt.gtimg.cn` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业分类 + 概念板块归属） | — |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — |

> **架构说明：** 指数数据由 `fetcher/index.py` 直接调用对应 API（不经过 Provider Chain）。A 股指数：腾讯→新浪备用→过期缓存；美股指数：新浪（2 次重试）→腾讯备用→过期缓存。

---

# 目录结构

```
investor-util/
│
├── src/                              # 源代码 — 根包声明（空 `__init__.py`，使 src 可被 Python 导入）
│   ├── __init__.py                   # 包标记（空文件）
│   │
│   ├── python/                       # 主程序代码 — 业务子包声明
│   │   ├── __init__.py               # 包标记（空文件）
│   │   ├── cache.py                  # 缓存引擎 — 泛用 JSON 文件缓存、TTL 管理、过期清理、指纹失效
│   │   ├── config.py                 # 配置管理 — config.json / llm_key.json / llm_settings.json 读写、校验
│   │   ├── constants.py              # 共享常量 — 版本号、缓存频率常量（CACHE_DAILY 等）、模型定价
│   │   ├── http_client.py            # HTTP 客户端工厂 — 统一 httpx.Client 创建、超时/重试配置
│   │   ├── logger.py                 # 日志模块 — logging 配置、文件+控制台双输出
│   │   ├── main.py                   # 程序入口 — TUI 主循环、流程编排、菜单路由
│   │   ├── market_hours.py           # 交易时段判断 — A 股盘中/盘后识别、东方财富 API 实时状态、可配置时段
│   │   ├── models.py                 # 数据模型 — NamedTuple / dataclass 定义
│   │   ├── reader.py                 # 持仓读取 — xlsx 解析、多 worksheet、列校验
│   │   ├── registry.py               # 中央注册表 — 所有数据模块的 name/缓存前缀/TTL/分组 统一注册
│   │   ├── tui.py                    # 键盘输入封装 — getch() 跨平台实现、方向键/快捷键解析
│   │   ├── tui_handlers.py           # 菜单通用辅助函数 — 文件选择器、输出框渲染、进度显示
│   │   ├── tui_menu.py               # 菜单交互 — 菜单定义、渲染、导航、快捷键映射
│   │   ├── handlers_cache.py         # 缓存管理命令 — 菜单 [1]~[4] 的实现：刷新缓存、清理过期、统计
│   │   ├── handlers_config.py        # 配置管理命令 — 菜单 [C]/[F]/[O]/[S]/[R] 的实现：目录/文件/LLM 模块启停
│   │   ├── handlers_report.py        # 报告生成命令 — 菜单 [E]/[H]/[B]/[L] 的实现：生成各类型报告
│   │   │
│   │   ├── fetcher/                  # 数据获取调度（Provider 路由 + 缓存预热）
│   │   │   ├── __init__.py           # 子包标记（空文件）
│   │   │   ├── chain.py              # Provider Chain — 多源路由、fallback 自动切换、过期缓存降级
│   │   │   ├── fund.py               # 基金数据获取 — 净值/持仓/排名/基准的缓存感知封装
│   │   │   ├── index.py              # 指数行情获取 — A股 + 美股指数、缓存 TTL 管理
│   │   │   ├── industry.py           # 行业/概念数据获取 — 行业分类、概念板块归属、批量接口
│   │   │   └── price.py              # 价格行情获取 — 场内实时价/收盘价/ETF 溢价
│   │   │
│   │   ├── providers/                # 数据源提供商（各 API 的具体实现）
│   │   │   ├── __init__.py           # 子包标记（空文件）
│   │   │   ├── tencent.py            # 腾讯财经 — 场内实时价/收盘价/A 股指数（qt.gtimg.cn）
│   │   │   ├── sina.py               # 新浪财经 — 美股指数（hq.sinajs.cn，JS 变量解析）
│   │   │   ├── eastmoney.py          # 东方财富 — 场外基金净值 + 备用价格链路（push2.eastmoney.com）
│   │   │   ├── tiantian.py           # 天天基金 — 基金业绩排名 + 季报持仓（JS 变量解析 + HTML 解析）
│   │   │   ├── eastmoney_industry.py # 东方财富行业分类 — 三级行业 + 概念板块归属（push2 API）
│   │   │   ├── akshare_extras.py     # akshare 封装 — 盈利预测 / 行业资金流向 / 股票历史分红
│   │   │   ├── akshare_news.py       # akshare 新闻 — 财新网要闻 + CCTV 财经新闻
│   │   │   ├── sina_news.py          # 新浪财经新闻 — feed.mix.sina.com.cn
│   │   │   ├── eastmoney_news.py     # 东方财富新闻 — np-weblist 快讯接口
│   │   │   ├── cls_news.py           # 财联社新闻 — www.cls.cn 滚动新闻（需签名鉴权，默认关闭）
│   │   │   ├── wallstreetcn_news.py  # 华尔街见闻 — api-one.wallstcn.com 全球财经直播流
│   │   │   ├── news_aggregator.py    # 新闻聚合器 — 多源并行获取、去重、排序、缓存
│   │   │   ├── news_sources.py       # 新闻源注册表 — 源标签/获取函数/默认启停映射
│   │   │   ├── news_correlator.py    # 新闻关联引擎 — 持仓关键词匹配、关联度排序
│   │   │   └── news_keywords.py      # 关键词提取 — 从持仓+穿透+行业数据生成关键词全集
│   │   │
│   │   ├── llm/                      # LLM 客户端（9 个子模块 + __init__.py 导出公共 API）
│   │   │   ├── __init__.py           # 公共 API 导出，保持向后兼容
│   │   │   ├── api.py                # API 调用 — Claude/OpenAI/DeepSeek 统一路由、重试、截断检测
│   │   │   ├── circuit_breaker.py    # 熔断器 — 端点级熔断，防止级联超时
│   │   │   ├── fingerprint.py        # 缓存指纹 — LLM 输入指纹计算、TTL 管理
│   │   │   ├── generators.py         # 生成编排 — 5 个 LLM 模块（1 个可选）的入口函数、批量调度
│   │   │   ├── markdown.py           # Markdown→HTML 渲染
│   │   │   ├── pricing.py            # 模型定价 — 各模型 Token 单价加载、费用估算
│   │   │   ├── prompts.py            # 系统提示词 — 内置 System Prompt 常量 + 构建函数
│   │   │   ├── session.py            # 会话统计 — 本次会话的 Token 用量累计、费用汇总
│   │   │   └── skeleton.py           # 共享骨架 — _generate_llm_content 等核心编排逻辑
│   │   │
│   │   ├── report/                   # 报告生成（Excel + HTML）
│   │   │   ├── __init__.py           # 子包标记（空文件）
│   │   │   ├── excel_generator.py    # Excel 报告编排 — 调用各页签写入函数、计时、异常隔离
│   │   │   ├── excel_writer.py       # Excel 写入 — openpyxl Workbook 创建、页签容器管理
│   │   │   ├── styles.py             # Excel 样式 — 颜色/字体/边框/对齐/数字格式定义
│   │   │   ├── summary.py            # 投资分析汇总页签 — 指数行情、账户汇总、LLM 用量
│   │   │   ├── market_value.py       # 市值核算明细表页签 — 15 列持仓行情、盈亏计算
│   │   │   ├── category.py           # 持仓分类表页签 — 按资产属性+投资分类聚合
│   │   │   ├── penetration.py        # 资产穿透 TOP10 — 基金穿透合并、行业分类、板块映射
│   │   │   ├── penetration_sheet.py  # 穿透 TOP10 Excel 写入 — 从 penetration.py 拆分的页签写入函数
│   │   │   ├── fund_performance.py   # 基金业绩分析页签 — 排名/收益率/基准对比/评级
│   │   │   ├── news_correlation.py   # 新闻关联分析页签 — 财经新闻关键词匹配
│   │   │   ├── early_warning.py      # 智能预警页签 — 行业资金流向联动 + 新闻情绪聚合
│   │   │   ├── llm_content.py        # LLM 增补页签写入 — 各 LLM 模块的 Excel 页签生成
│   │   │   ├── html_writer.py        # HTML 报告生成 — Jinja2 模板渲染、HTML 章节编排
│   │   │   ├── html_builders.py      # HTML 数据构建器 — 持仓分类表/基金业绩数据构建（从 html_writer.py 拆分）
│   │   │   └── progress.py           # 进度报告接口 — ProgressReporter 基类 + TuiProgressReporter
│   │   │
│   │   └── tmpl/
│   │       └── report_template.html  # HTML 报告 Jinja2 模板
│   │
│   └── test/                         # 单元测试（57 个 test_*.py + helpers.py，1713 passed / 12 skipped）
│
├── data/                             # 运行时数据
│   ├── holdings/                     # 持仓 xlsx 文件（用户放置）
│   ├── cache/                        # API 响应缓存（自动生成，JSON/JSON.GZ）
│   ├── config/                       # 配置文件（手动编辑）
│   │   ├── config.json               # 主配置 — 目录/文件路径、缓存 TTL、新闻源启停、预警参数
│   │   ├── llm_key.json              # LLM 密钥 — provider / api_key / model / endpoint / fallback
│   │   └── llm_settings.json         # LLM 参数 — temperature / max_tokens / thinking / system_prompt
│   │
│   └── ...（其他子目录不存在，仅以上三个）
│
├── reports/                          # 生成报告输出（最新版 + 按日期存档，自动生成）
├── logs/                             # 程序日志（app.log，自动生成）
│
├── scripts/                          # 启动脚本
│   ├── launch.ps1                    # Windows PowerShell 启动脚本
│   └── launch.sh                     # Linux Bash 启动脚本
│
├── docs-stm/                         # 项目文档
│   ├── plan/                         # 计划与设计文件
│   │   ├── archived_plan.md          # 历史迭代归档（Iter 1.1~3.7）
│   │   └── iteration-plan.md         # 迭代计划细节
│   ├── manuals/                      # 用户文档分册
│   │   ├── how-to-start.md           # 快速开始 — 启动方式、持仓格式、菜单操作说明
│   │   ├── how-to-config.md          # 配置指南 — config.json 字段说明 + cache_ttl + 缓存分组
│   │   ├── how-to-config-llm.md      # LLM 配置指引 — llm_key.json / llm_settings.json
│   │   ├── how-to-use-registry.md    # 中央注册表使用说明
│   │   ├── datasource-and-folders.md # 数据源一览 + 目录结构（本文档）
│   │   ├── faq.md                    # 常见问题解答 — 使用中的高频问题，按类别组织
│   │   └── reports-instruction.md    # 报告文件结构说明
│   ├── tmp/                          # 临时文件 / 过程文件（git 忽略）
│   └── managements/                  # 管理文档
│       ├── plan.md                   # 实现计划（关键技术决策 + 下一步迭代计划）
│       ├── requirements.md           # 需求文档（完整需求规格）
│       ├── technical.md              # 技术设计文档
│       ├── testplan.md               # 质量控制与测试标准
│       ├── changelog.md              # 变更日志 — 所有版本的详细更新记录
│       └── review-findings.md        # 自审问题记录
│
├── .gitignore                        # Git 忽略规则 — 排除缓存/日志/虚拟环境/敏感密钥
├── CLAUDE.md                         # Claude Code 项目指引 — AI 编程助手的行为规范
├── README.md                         # 用户文档总入口（指向各分册）
├── pyproject.toml                    # Python 项目元数据（setuptools 配置）
├── pytest.ini                        # pytest 配置 — testpaths / 标记注册 / 命令行选项
├── reason.bat                        # Windows 一键启动批处理脚本
├── requirements.txt                  # Python 依赖清单（pip install -r 安装）
```

> 注意：项目每次版本变更后，`technical.md` 中的目录树和测试文件数可能滞后。请以本文档为准。
