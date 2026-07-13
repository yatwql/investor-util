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

# 目录结构

```
investor-util/
│
├── src/                              # 源代码根包，所有业务模块与测试用例的公共父级
│   ├── __init__.py                   # 包标记（空文件）
│   │
│   ├── python/                       # 主程序代码，按职责划分为数据获取、报告生成、LLM 等子模块
│   │   ├── __init__.py               # 包标记（空文件）
│   │   ├── cache/                     # 缓存引擎子包（Strangler Fig 重构后，含路径/IO/存储/TTL/统计/清理/组管理）
│   │   │   ├── __init__.py            # 包定义 + 公共 API re-export（all: get/set/clear/ttl/stats/cleanup/groups/holdings）
│   │   │   ├── _paths.py              # 路径/常量子模块 — _CACHE_DIR、gzip 阈值、_cache_path()
│   │   │   ├── _io.py                 # 文件 IO 子模块 — 原子读写、gzip 透明压缩/解压、损坏自动恢复
│   │   │   ├── _store.py              # 核心存取子模块 — get/set/clear + _cache_lock
│   │   │   ├── _ttl.py                # TTL 子模块 — 交易时段感知 TTL 计算、缓存年龄查询
│   │   │   ├── _stats.py              # 命中率统计子模块 — 缓存击中/未中计数、目录统计
│   │   │   ├── _cleanup.py            # 过期清理子模块 — 扫描缓存目录、过期删除、dry_run 预览
│   │   │   ├── _groups.py             # 组管理子模块 — 按前缀/缓存组批量清除
│   │   │   └── services/              # 业务服务子包
│   │   │       ├── __init__.py        # 包标记（空文件）
│   │   │       └── holdings_tracker.py # 持仓跟踪服务 — 指纹计算+变更检测+关联缓存自动刷新
│   │   ├── code_utils.py             # 证券代码/名称类型判定中心 — A股/基金/债券/港股通/ETF/QDII 识别原语
│   │   ├── config/                    # 配置管理子包（_defaults / _comments / _core）— config.json / llm_key / llm_settings 读写、校验
│   │   ├── constants.py              # 共享常量 + 项目根路径（标记文件查找法）— 版本号、缓存频率、模型定价、PROJECT_ROOT
│   │   ├── http_client.py            # HTTP 客户端工厂 — 统一 httpx.Client 创建、超时/重试配置
│   │   ├── logger.py                 # 日志模块 — logging 配置、文件+控制台双输出
│   │   ├── main.py                   # 程序入口 — TUI 主循环、流程编排、菜单路由
│   │   ├── market_hours.py           # 交易时段判断 — A 股盘中/盘后识别、东方财富 API 实时状态、可配置时段
│   │   ├── models.py                 # 数据模型 — NamedTuple / dataclass 定义
│   │   ├── provider_registry.py      # 数据源注册中心 — 熔断器、会话级缓存、获取策略选择、审计报告
│   │   ├── reader.py                 # 持仓读取 — xlsx 解析、多 worksheet、列校验
│   │   ├── registry.py               # 中央注册表 — 所有数据模块的 name/缓存前缀/TTL/分组 统一注册
│   │   ├── tui.py                    # 键盘输入封装 — getch() 跨平台实现、方向键/快捷键解析
│   │   ├── tui_handlers.py           # 菜单通用辅助函数 — 文件选择器、输出框渲染、进度显示
│   │   ├── tui_menu.py               # 菜单交互 — 菜单定义、渲染、导航、快捷键映射
│   │   ├── handlers_cache.py         # 缓存管理命令 — 菜单 [1]~[4] 的实现：刷新缓存、清理过期、统计
│   │   ├── handlers_config.py        # 配置管理命令 — 菜单 [C]/[F]/[O]/[S]/[R] 的实现：目录/文件/LLM 模块启停
│   │   ├── handlers_report.py        # 报告生成命令 — 菜单 [E]/[H]/[B]/[L] 的实现：生成各类型报告
│   │   │
│   │   ├── fetcher/                  # 数据获取调度层，负责 Provider 路由分发与缓存预热
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── chain.py              # Provider Chain — 多源路由、fallback 自动切换、过期缓存降级
│       │   │   ├── history_diff.py       # 持仓快照差异计算 — 环比对比（F1：新增/清仓/增持/减持）
│       │   │   ├── fund.py               # 基金数据获取 — 净值/持仓/排名/基准的缓存感知封装
│       │   │   ├── index.py              # 指数行情获取 — A股 + 美股指数、缓存 TTL 管理
│       │   │   ├── industry.py           # 行业/概念数据获取 — 行业分类、概念板块归属、批量接口
│       │   │   ├── fund_manager.py       # 基金经理数据获取 — 主页 HTML 解析 + 档案页回退
│       │   │   └── price.py              # 价格行情获取 — 场内实时价/收盘价/ETF 溢价
│   │   │
│   │   ├── providers/                # 数据源提供商，封装各第三方 API 的具体调用逻辑
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── tencent.py            # 腾讯财经 — 场内实时价/收盘价/A 股指数（qt.gtimg.cn）
│       │   │   ├── sina.py               # 新浪财经 — 美股指数（hq.sinajs.cn，JS 变量解析）
│       │   │   ├── eastmoney.py          # 东方财富 — 场外基金净值 + 备用价格链路（push2.eastmoney.com）
│       │   │   ├── tiantian.py           # 天天基金 — 基金业绩排名 + 季报持仓（JS 变量解析 + HTML 解析）
│       │   │   ├── eastmoney_industry.py # 东方财富行业分类 — 三级行业 + 概念板块归属（push2 API）
│       │   │   ├── eastmoney_industry_rest.py # 东方财富行业分类备用 — 行情页 quotedata 解析（push2 不可用时 fallback）
│       │   │   ├── akshare_extras.py     # akshare 封装 — 盈利预测 / 行业资金流向 / 股票历史分红
│       │   │   ├── akshare_news.py       # akshare 新闻 — 财新网要闻 + CCTV 财经新闻
│       │   │   ├── sina_news.py          # 新浪财经新闻 — feed.mix.sina.com.cn
│       │   │   ├── eastmoney_news.py     # 东方财富新闻 — np-weblist 快讯接口
│       │   │   ├── cls_news.py           # 财联社新闻 — www.cls.cn 滚动新闻（需签名鉴权，默认关闭）
│       │   │   ├── wallstreetcn_news.py  # 华尔街见闻 — api-one.wallstcn.com 全球财经直播流
│       │   │   ├── news_aggregator.py    # 新闻聚合器 — 多源并行获取、去重、排序、缓存
│       │   │   ├── news_sources.py       # 新闻源注册表 — 源标签/获取函数/默认启停映射
│       │   │   ├── news_correlator.py    # 新闻关联引擎 — 持仓关键词匹配、关联度排序
│       │   │   └── news_keywords.py      # 关键词提取 — 从持仓+穿透+行业数据生成关键词全集
│   │   │
│   │   ├── schemas/                 # 数据模型定义
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   └── history.py            # 历史走势数据模型 — 持仓快照、回撤指标等结构化数据
│   │   │
│   │   ├── llm/                      # LLM 客户端，包含 API 调用、缓存指纹、提示词模板与会话统计等子模块
│       │   │   ├── __init__.py           # 公共 API 导出，直链 generators_orchestrator/news
│       │   │   ├── api.py                # Provider 路由 + Claude/OpenAI 调用 + Extended Thinking
│       │   │   ├── api_base.py           # API 基础设施，提供重试、截断、内容提取与失败追踪等公共逻辑
│       │   │   ├── circuit_breaker.py    # 熔断器 — 端点级熔断，防止级联超时
│       │   │   ├── fingerprint.py        # 缓存指纹 — LLM 输入指纹计算、TTL 管理
│       │   │   ├── generators.py         # 4 个单例生成函数（global_macro/expert_review/health_check/penetration）
│       │   │   ├── generators_news.py    # 财经新闻的 LLM 关联分析逻辑
│       │   │   ├── generators_orchestrator.py  # LLM 批量任务编排，支持缓存预检与线程池并发分发
│       │   │   ├── markdown.py           # Markdown→HTML 渲染
│       │   │   ├── pricing.py            # 模型定价 — 各模型 Token 单价加载、费用估算
│       │   │   ├── prompts.py            # 系统提示词 — 内置 System Prompt 常量 + 构建函数
│       │   │   ├── session.py            # 会话统计 — 本次会话的 Token 用量累计、费用汇总
│       │   │   └── skeleton.py           # 共享骨架 — _generate_llm_content 等核心编排逻辑
│   │   │
│   │   ├── report/                   # 报告生成模块，同时支持 Excel 电子表格与 HTML 网页两种输出格式
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── excel_generator.py    # Excel 报告编排器，统筹各子模块完成报告生成
│       │   │   ├── excel_writer.py       # Excel 写入 — openpyxl Workbook 创建、页签容器管理
│       │   │   ├── excel_module_loader.py # 报告模块动态加载器，支持 ImportError 时的优雅降级
│       │   │   ├── excel_sheet_factory.py # Excel 页签工厂，按数据类型驱动页签创建与可见性控制
│       │   │   ├── excel_market_data.py   # 行情市值与指数数据的解析逻辑
│       │   │   ├── excel_content_sheets.py # 核心内容页签写入，涵盖汇总、分类、穿透与基金业绩
│       │   │   ├── excel_news_warning.py  # 新闻与智能预警页签的写入逻辑
│       │   │   ├── excel_b_series.py      # B 系列页签写入，包含基金经理、重合度、集中度与风格分析
│       │   │   ├── excel_llm_usage.py     # LLM 分析章节与 API 用量页签的整合写入
│       │   │   ├── styles.py             # Excel 样式 — 颜色/字体/边框/对齐/数字格式定义
│       │   │   ├── summary_llm_usage.py   # 投资分析汇总中的 LLM API 用量页签
│       │   │   ├── summary.py            # 投资分析汇总页签 — 指数行情、账户汇总
│       │   │   ├── market_value.py       # 市值核算计算引擎 — 行情获取、细节行生成、盈亏计算
│       │   │   ├── market_value_sheet.py # 市值核算 Excel 写入层 — 行值转换、着色、分组写入
│       │   │   ├── category.py           # 持仓分类表页签 — 按资产属性+投资分类聚合
│       │   │   ├── data_status.py        # 数据源状态追踪 — DataStatusItem / STATUS_MESSAGES / DegradationTracker
│       │   │   ├── penetration.py        # 资产穿透 TOP10 — 基金穿透合并、行业分类、板块映射
│       │   │   ├── penetration_sheet.py  # 穿透 TOP10 的 Excel 页签写入
│       │   │   ├── fund_performance.py   # 基金业绩分析页签 — 排名/收益率/基准对比/评级
│       │   │   ├── news_correlation.py   # 新闻关联分析页签 — 财经新闻关键词匹配
│       │   │   ├── early_warning.py      # 智能预警页签 — 行业资金流向联动 + 新闻情绪聚合
│       │   │   ├── llm_content.py        # LLM 增补页签写入 — 各 LLM 模块的 Excel 页签生成
│       │   │   ├── portfolio_history.py  # 组合历史走势计算 — as-if 市值曲线、回撤/波动率指标（F2）
│       │   │   ├── history_snapshot.py   # 持仓快照持久化 — 原子写入、最新快照加载、旧快照清理（F1）
│       │   │   ├── html_writer.py        # HTML 报告生成编排器 — 调用子渲染函数、模板渲染
│       │   │   ├── html_jinja_env.py     # Jinja2 模板环境，提供过滤器注册与 section_visible 控制标记
│       │   │   ├── html_renderers.py     # HTML 报告各章节的渲染函数集合
│       │   │   ├── html_save.py          # HTML 报告保存，负责覆盖写入最新版、按日期归档并自动清理过期归档
│       │   │   ├── html_builders.py      # HTML 报告的数据构建器，负责持仓分类与基金业绩数据组装
│       │   │   ├── fund_concentration.py        # 持仓集中度监控 — top3/5/10 占比+环比变化+三级预警
│       │   │   ├── fund_concentration_sheet.py  # 持仓集中度监控 Excel 写入 — 10 列输出+变化箭头/标识
│       │   │   ├── fund_manager_analysis.py     # 基金经理变更分析 — 快照式变更检测（1/3/6 月窗口）
│       │   │   ├── fund_manager_sheet.py        # 基金经理变更监控 Excel 写入 — 8 列+预警着色
│       │   │   ├── fund_overlap.py              # 持仓重合度矩阵 — Jaccard+Overlap Ratio 双指标计算
│       │   │   ├── fund_overlap_sheet.py        # 持仓重合度矩阵 Excel 写入 — 热力图输出
│       │   │   ├── fund_style_analysis.py       # 基金风格判定+漂移检测 — 市值/PE 加权、网格距离、快照
│       │   │   ├── fund_style_sheet.py          # 基金风格分析 Excel 写入 — 8 列、漂移等级着色
│       │   │   └── progress.py                  # 进度报告接口 — ProgressReporter 基类 + TuiProgressReporter
│   │   │
│   │   └── tmpl/
│   │       └── report_template.html  # HTML 报告 Jinja2 模板
│   │
│   └── test/                             # 测试套件，按 pytest 标记分层组织为 unit / integration / scenario
│       ├── __init__.py                   # 包标记（空文件）
│       ├── conftest.py                   # pytest 配置 — 所有标记注册（19 个分层标记）、fixture
│       ├── helpers.py                    # 测试辅助工具（SynchronousExecutor 异步转同步执行器）
│       ├── unit/                         # 单元测试，按被测模块划分子分组
│       │   ├── __init__.py               # 子包标记（空文件）
│       │   ├── conftest.py               # 单元测试级 pytest fixture/配置
│       │   ├── providers/                # 数据源 provider 测试（≈167 项）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_eastmoney.py     # 东方财富净值 API — _strip_jsonp / _safe_float / fetch_nav（15 项）
│       │   │   ├── test_eastmoney_industry.py  # 东方财富行业分类 API — _secid 前缀规则、fetch_industry_and_concepts（26 项）
│       │   │   ├── test_tencent.py       # 腾讯财经行情 — _add_prefix / _parse_float / _parse_response / fetch_price（16 项）
│       │   │   ├── test_sina.py          # 新浪财经指数 — _parse_us_index / fetch_us_indices（10 项）
│       │   │   ├── test_tiantian.py      # 天天基金 — _find_holdings_table / _parse_syl_returns / _calc_rating_from_entry（65 项）
│       │   │   └── test_akshare_extras.py # akshare 封装 — 盈利预测/行业资金流向/分红（16 项）
│       │   ├── fetcher/                  # 抓取器测试（189 项，含熔断预检/冷却恢复）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_chain.py         # Provider Chain — _get_chain / _fetch_with_fallback 全链路 + 熔断预检（30 项）
│       │   │   ├── test_chain_edge.py    # Provider Chain 异常场景 — 全链 fallback/超时/空响应/冷却探针（8 项）
│       │   │   ├── test_fetcher.py       # 抓取器调度 — 指数/行业/价格聚合入口（5 项）
│       │   │   ├── test_fetcher_price.py # 行情抓取 — _name_matches / _price_cache_key / _price_transform（22 项）
│       │   │   ├── test_fetcher_index.py # 指数抓取 — 腾讯→新浪 fallback 双链路（13 项）
│       │   │   ├── test_fetcher_industry.py # 行业抓取 — _industry_transform / fetch_industry_data / 熔断预检 batch（41 项）
│       │   │   ├── test_fund.py          # 基金抓取 — 基准三层策略 / HTML 正则解析 / per-code 锁（19 项）
│   │   │   ├── test_fund_manager.py  # 基金经理数据获取测试，覆盖 HTML 解析与档案页回退
│       │   │   └── test_api_edge.py      # HTTP Provider 异常场景 — 超时/DNS/SSL/429/503/JSON 异常（23 项 Y1）
│       │   ├── handlers/                  # 菜单命令处理测试（31 项）
│       │   │   ├── __init__.py            # 子包标记（空文件）
│       │   │   ├── test_handlers_cache.py  # 缓存管理命令测试 — 刷新/清理/统计（涉及 registry 和 fetcher）
│       │   │   └── test_handlers_report.py # 报告生成命令测试 — 菜单 E/H/B/L 的场景覆盖
│       │   ├── llm/                      # LLM 相关测试（480 项）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_api.py           # LLM API 调用 — 重试/熔断/回退/截断/Provider 路由（44 项）
│       │   │   ├── test_api_base.py      # API 基础设施 — _extract_content / _check_truncation / _supports_extended_thinking（~60 项）
│       │   │   ├── test_api_base_edge.py # API 基础设施异常 — _check_circuit_breaker / _process_success_response / _call_llm_with_retry 异常（13 项，@pytest.mark.edge）
│       │   │   ├── test_api_edge.py      # LLM API 异常场景 — 网络错误/HTTP 错误码/超时
│       │   │   ├── test_circuit_breaker_recovery.py  # 熔断器恢复 — 冷却/半开/重开全生命周期（15 项）
│       │   │   ├── test_circuit_breaker_edge.py    # 熔断器异常场景 — 并发熔断/恢复竞争
│       │   │   ├── test_fingerprint.py   # 缓存指纹 — _extract_stable_holdings / _build_llm_fingerprint（16 项）
│       │   │   ├── test_generators.py    # 生成编排 — _apply_llm_news_correlation / _precheck_one_cache / 四函数签名校验（21 项）
│       │   │   ├── test_generators_news.py # 新闻 LLM 关联分析 — 缓存/批处理/用量汇总测试
│       │   │   ├── test_generators_news_edge.py # 新闻 LLM 异常场景 — 空输入/网络失败/边际条件测试（edge）
│       │   │   ├── test_generators_orch.py # LLM 批量编排 — 线程池并发/缓存预检/模块调度测试
│       │   │   ├── test_generators_orch_edge.py # LLM 编排异常场景 — 并发限制/模块故障隔离（edge）
│       │   │   ├── test_llm.py           # LLM 客户端 — _markdown_to_html / generate_all_llm / prompt 构建（50 项）
│       │   │   ├── test_llm_content.py   # LLM 内容 Excel 写入 — _strip_html / _write_content_sheet / section_order（18 项）
│       │   │   ├── test_llm_placeholder.py # LLM 占位文本 — 未配置/已禁用/API 失败三种状态（3 项）
│       │   │   ├── test_llm_placeholder_distinction_edge.py # LLM 三态互斥 — NOT_CONFIGURED/MODULE_DISABLED/API_ERROR 文本区分（6 项）
│       │   │   ├── test_prompts.py       # 系统提示词测试 — FAIL_REASON 常量/格式化函数/Prompt 构建函数（45 项）
│       │   │   ├── test_session.py       # 会话统计 — reset / get / format / _track_session_usage（32 项）
│       │   │   └── test_skeleton.py      # 共享骨架 — _is_llm_module_enabled / _handle_truncation（9 项）
│       │   ├── news/                     # 新闻抓取测试（≈176 项）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_news_aggregator.py  # 新闻聚合器 — 多源并行/去重/缓存三态（16 项）
│       │   │   ├── test_news_correlator.py # 新闻关联引擎 — 关键词匹配/关联度排序（27 项）
│       │   │   ├── test_news_keywords.py # 关键词提取 — 从持仓/穿透/行业生成关键词（12 项）
│       │   │   ├── test_news_sources.py  # 新闻源注册表 — 启停映射/默认配置（11 项）
│       │   │   ├── test_eastmoney_news.py # 东方财富新闻 — _parse_news_item / fetch_news 全流程（18 项）
│       │   │   ├── test_sina_news.py     # 新浪财经新闻 — _ts_to_str / fetch_news 参数透传（17 项）
│       │   │   ├── test_wallstreetcn_news.py # 华尔街见闻新闻 — _parse_news_item HTML 剥离（15 项）
│       │   │   ├── test_cls_news.py      # 财联社新闻 — _parse_news_item 缺字段测试（21 项）
│       │   │   └── test_akshare_news.py  # akshare 新闻 — 财新网 + CCTV 双链路（16 项）
│       │   ├── report/                   # 报表生成测试（≈1020 项）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_excel_writer.py  # Excel 写入引擎 — Workbook 创建/页签管理（30 项）
│       │   │   ├── test_excel_roundtrip.py # Excel 读写回环测试 — 保存后重开验证数据完整性
│       │   │   ├── test_excel_report_structure.py # Excel 报告结构验证 — 页签序号/条件显示/命名
│       │   │   ├── test_html_writer.py   # HTML 报告生成 — Jinja2 渲染/LLM 章节分支（89 项）
│       │   │   ├── test_html_writer_edge.py # HTML 写入器异常场景 — 降级渲染/条件分支边界
│       │   │   ├── test_html_template.py  # HTML 模板分支审计 — 评级颜色/模块启停/条件渲染
│       │   │   ├── test_excel_format_edge.py # Excel 数字格式 — 金额/百分比/份额千分位 styles.py 常量（7 项）
│       │   │   ├── test_html_report_structure.py # HTML 报告结构验证 — 章节顺序/条件渲染/导航
│       │   │   ├── test_html_report_structure_edge.py # HTML 结构验证异常场景 — 缺失 section/降级页脚
│       │   │   ├── test_excel_generator.py # Excel 报告编排 — 懒导入/异常隔离/计时（15 项）
│       │   │   ├── test_summary.py       # 投资分析汇总页签 — 指数行情/账户汇总/LLM 用量（85 项）
│       │   │   ├── test_market_value.py  # 市值核算明细表 — 15 列持仓盈亏计算（59 项）
│       │   │   ├── test_market_value_sheet.py # 市值核算 Excel 写入层 — 行值转换/着色/分组（31 项）
│       │   │   ├── test_market_value_strategy_edge.py # 行情获取策略边缘用例 — 策略选择退化验证（8 项）
│       │   │   ├── test_penetration.py   # 资产穿透 TOP10 — 基金合并/行业分类（12 项）
│       │   │   ├── test_penetration_edge.py # 穿透异常场景 — 占比归一化/零总市值/单资产（12 项）
│       │   │   ├── test_portfolio_history.py # 组合历史走势 — 代码类型路由/00 降级/as-if 市值/波动率（28 项）
│       │   │   ├── test_fund_concentration.py # 持仓集中度监控测试（15 项 B4）
│       │   │   ├── test_fund_performance.py # 基金业绩分析 — 排名/评级/评级分布直方图（48 项）
│       │   │   ├── test_category.py      # 持仓分类表 — 按资产属性+投资分类聚合（30 项）
│       │   │   ├── test_category_edge.py # 持仓分类异常场景 — 空数据/降级分红/占位文本
│       │   │   ├── test_classification_utils.py # 分类工具函数 — 资产分类/映射/判定（B 系列辅助）
│       │   │   ├── test_data_integrity.py # 数据正确性验证 — 分类聚合/行业占比/指数合理性/多币种/多时区
│       │   │   ├── test_data_quality_edge.py # 数据质量异常场景 — 停牌/负净值/债券违约/FOF 嵌套（22 项 Y2）
│       │   │   ├── test_data_status.py   # 数据源状态追踪组件 DataStatusItem 与 DegradationTracker 的测试
│       │   │   ├── test_market_value_edge.py # 行情异常场景 — NAV 空窗期/交易时段切换/溢价率（37 项）
│       │   │   ├── test_qdii_timezone_edge.py # QDII 多时区 — _is_qdii / 多时区日期转换（26 项）
│       │   │   ├── test_news_correlation.py # 新闻关联分析页签 — 新闻匹配/关键词写入（49 项）
│       │   │   ├── test_early_warning.py # 智能预警页签 — 行业资金流出/新闻情绪聚合（25 项）
│       │   │   ├── test_early_warning_edge.py # 智能预警在空数据状态下的占位行为验证
│       │   │   ├── test_excel_generator_edge.py # 全局降级场景的冒烟测试与消息一致性验证
│       │   │   ├── test_fund_bseries_sheet_edge.py # B 系列报告在空数据时的占位展示验证
│       │   │   ├── test_html_builders.py # HTML 数据构建器 — 持仓分类表/基金业绩数据构建
│       │   │   ├── test_html_builders_edge.py # HTML 数据构建器异常场景 — 分红 API 降级/盈利预测失败
│       │   │   ├── test_news_degradation_edge.py # 新闻源全部或部分失败时的降级展示验证
│       │   │   ├── test_progress.py      # 进度报告 — ProgressReporter / 错误跟踪/耗时排行（33 项）
│       │   │   ├── test_fund_style_analysis.py # 基金风格分析 — 市值/PE 加权、网格距离、漂移检测（32 项）
│       │   │   ├── test_fund_manager_analysis.py # 基金经理变更分析测试（B2）
│       │   │   ├── test_fund_manager_sheet.py # 基金经理变更监控 Excel 写入测试（B2）
│       │   │   ├── test_fund_overlap.py # 持仓重合度矩阵测试（21 项 B3）
│       │   │   └── test_security_edge.py # 安全纵深 — 公式注入/XSS/符号链接/路径遍历/原型污染/临时文件竞争（19 项 Y6，含 4 项 autoescape）
│       │   ├── config/                   # 配置测试（76 项）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_config.py        # 配置管理 — config.json / llm_settings 读写/校验（31 项）
│       │   │   ├── test_config_atomic.py # 原子写入 — 创建/覆盖/异常清理/缓存失效（11 项）
│       │   │   ├── test_config_atomic_edge.py # 原子写入异常场景 — 写入失败/目录不可写/权限拒绝
│       │   │   ├── test_config_edge.py   # 配置异常场景 — 文件损坏/格式错误/缺失字段
│       │   │   └── test_config_firstrun_edge.py # 首次运行引导 — 配置缺失自动初始化/目录创建/损坏降级（4 项）
│       │   ├── core/                     # 核心模块测试（396 项）
│       │   │   ├── __init__.py           # 子包标记（空文件）
│       │   │   ├── test_cache.py         # 缓存引擎 — TTL 管理/过期清理/市场时段感知（181 项）
│       │   │   ├── test_cache_edge.py      # 缓存异常场景 — 文件损坏/并发写入/目录权限
│       │   │   ├── test_filesystem_edge.py # 文件系统异常场景 — 加密 Excel/损坏文件/权限/超长路径（18 项 Y3）
│       │   │   ├── test_http_client.py   # HTTP 客户端工厂 — _should_verify / make_http_client（17 项）
│       │   │   ├── test_market_hours.py  # 交易时段判断 — _is_market_open 三层编排（41 项）
│       │   │   ├── test_market_hours_edge.py # 交易时段异常场景 — 跨时区/节假日/午夜边界
│       │   │   ├── test_models.py        # 数据模型 — NamedTuple / dataclass 定义校验（17 项）
│       │   │   ├── test_reader.py        # 持仓读取 — xlsx 解析/多 worksheet/列校验（11 项）
│       │   │   ├── test_provider_registry.py # 数据源注册中心 — 熔断/会话缓存/策略选择/并发安全（37 项）
│       │   │   ├── test_phase_timeout.py     # 全局超时上下文管理器 — phase_timeout 嵌套保护/超时行为（8 项）
│       │   │   ├── test_registry.py      # 中央注册表 — 模块注册/TTL 映射/设置键派生（21 项）
│       │   │   └── test_registry_edge.py # 注册表异常场景 — 重复注册/不存在的模块/别名冲突
│       │   └── ui/                       # TUI 测试（164 项）
│       │       ├── __init__.py           # 子包标记（空文件）
│       │       ├── test_tui.py           # 键盘输入 — getch() 跨平台/方向键解析（32 项）
│       │       ├── test_tui_edge.py      # TUI 异常友好提示 — _print_error_with_hint 7 种异常分类 + 菜单调度异常捕获（18 项 edge）
│       │       ├── test_tui_menu.py      # 菜单交互 — 菜单渲染/导航/快捷键（27 项）
│       │       ├── test_tui_handlers.py  # 通用辅助 — 文件选择器/输出框/进度显示（20 项）
│       │       ├── test_handlers.py      # 菜单命令 — 缓存刷新/配置/LLM 模块管理（23 项）
│       │       └── test_log_sanitize.py  # 日志脱敏 — 敏感信息过滤/安全日志（40 项）
│       │
│       ├── integration/                # 集成测试（29 项，含新闻流水线全链路/契约验证）
│       │   ├── __init__.py               # 子包标记（空文件）
│       │   ├── test_integration_coverage.py  # 集成测试覆盖：接口契约/错误隔离/新闻流水线/缓存一致性/TUI 路由
│       │   └── test_news_pipeline_edge.py # 新闻全链路集成 — 聚合/去重/关联端到端 mock 验证（2 项）
│       └── scenario/                     # 场景测试（278 项，4 个子分组）
│           ├── __init__.py               # 子包标记（空文件）
│           ├── basic/                    # 基础业务场景 S0a-S0d + S1-S5 + S21-S33 + C-P1b + P1p（97 项）
│           │   ├── __init__.py           # 子包标记（空文件）
│           │   ├── test_integration.py              # S1-S5：持仓读取/行情获取/市值核算/分类汇总/报告生成
│           │   ├── test_scenario_holdings_quality.py # S0a-S0d（Z3）：清仓跳过/A-C份额/特殊字符（S0c 已移至 resilience）
│           │   ├── test_scenario_special_securities.py # S21-S28（Z1）：港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债
│           │   ├── test_scenario_operational_behavior.py # S29-S33（Z2）：分红送转/定投摊薄/部分卖出/跨账户转仓/新股待上市
│           │   ├── test_scenario_penetration.py  # P1p：穿透深度场景 — 多级基金嵌套/分级合并/行业归属
│           │   └── test_scenario_section_order.py # C-P1b：报告序号可配置（自定义/部分配置/未知 key 合并场景，6 项）
│           ├── resilience/               # 异常容错场景 S6-S10 + 极限场景（24 项）
│           │   ├── __init__.py           # 子包标记（空文件）
│           │   ├── test_integration_scenarios.py  # S6-S9：纯债分类/网络降级/单行报告/零成本利润
│           │   └── test_scenario_extreme.py # S0c+S10：超多持仓/极端份额/高精度净值/零成本组合（scenario_extreme 标记，8 项）
│           ├── llm/                      # LLM 场景 S11-S20（32 项）
│           │   ├── __init__.py           # 子包标记（空文件）
│           │   └── test_llm_scenarios.py # S11-S20：混合缓存/全部失败/Thinking/禁用/断网/部分超期/HTML 分支
│           └── datetime/                 # 日期时间场景 T1-T21（100 项）
│               ├── __init__.py           # 子包标记（空文件）
│               └── test_datetime_scenarios.py  # T1-T21：市场状态/产品分类/边界 Edge Case/跨年/调休/汇率故障/港股通假期
│
├── data/                             # 运行时数据目录，存放持仓文件、API 缓存与用户配置
│   ├── holdings/                     # 持仓 xlsx 文件（用户放置）
│   ├── cache/                        # API 响应缓存（自动生成，JSON/JSON.GZ）
│   ├── config/                       # 配置文件（手动编辑）
│   │   ├── config.json               # 主配置 — 目录/文件路径、缓存 TTL、新闻源启停、预警参数
│   │   ├── llm_key.json              # LLM 密钥 — provider / api_key / model / endpoint / fallback
│   │   └── llm_settings.json         # LLM 参数 — temperature / max_tokens / thinking / system_prompt
│   │
│   └── ...（其他子目录不存在，仅以上三个）
│
├── reports/                          # 报告输出目录，保存最新版与按日期归档的历史报告
├── logs/                             # 程序日志（app.log，自动生成）
│
├── test-reports/                      # 测试报告输出（自动生成）
│   ├── latest/                        # 最新测试报告（按 --mode 生成子目录）
│       │   ├── index.html                 # 汇总页 — 各模式通过/失败总览 + 最近运行时间
│       │   ├── unit/report.html           # 单元测试报告（标记 -m "unit"，2699 项）
│       │   ├── standard/report.html       # 常规单元报告（标记 -m "unit and not (edge or data)"，2204 项）
│       │   ├── scenario/report.html       # 场景测试报告（标记 -m "scenario"，278 项）
│       │   ├── regression/report.html     # 回归测试报告（标记 -m "scenario"，模式别名，278 项）
│       │   ├── verify/report.html         # 合入验证报告（标记 -m "scenario or unit_core or unit_providers or unit_fetcher"，1057 项）
│       │   ├── integration/report.html    # 集成测试报告（标记 -m "scenario or integration"，306 项）
│       │   ├── smoke/report.html          # 冒烟测试报告（标记 -m "smoke"，24 项）
│       │   ├── edge/report.html           # 边缘场景报告（标记 -m "edge"，318 项）
│       │   ├── data/report.html           # 数据正确性报告（标记 -m "data"，65 项）
│       │   ├── report/report.html         # 仅报告模块测试（标记 -m "unit_report"，≈1020 项）
│       │   ├── all/report.html            # 全量测试报告（无标记筛选，3006 项）
│       │   ├── all_no_unit/report.html    # 排除单元测试报告（标记 -m "not unit"，306 项）
│       │   └── coverage/                  # HTML 行覆盖率报告（--coverage 时生成）
│   └── archives/                      # 历史报告存档
│       └── <YYYYMMDD>/                # 按日期归档的子目录（含完整 latest/ 快照）
│
├── scripts/                          # 启动脚本与测试工具
│   ├── launch.ps1                    # Windows PowerShell 启动脚本
│   ├── launch.sh                     # Linux Bash 启动脚本
│   ├── test_runner.py                # 测试驱动脚本 — pytest 统一运行 + 结构化 HTML 报告输出
│   ├── check-test-markers.py         # 标记合规检查 — AST 静态扫描 test_*.py 的 pytest 标记完整性
│   ├── check-version-consistency.py # 版本号一致性检查 — 以 constants.py 为单一来源校验 9 处版本号
│
├── docs-stm/                         # 项目文档目录，包含用户手册、管理文档与历史归档
│   ├── archive/                       # 历史文件归档
│   │   ├── archived_changelog.0.1.x.md        # v0.1.x 版本变更日志归档
│   │   ├── archived_changelog.0.2.x.md        # v0.2.x 版本变更日志归档（v0.2.0 ~ v0.2.91 共 47 个版本）
│   │   ├── archived_plan.0.1.x.md             # v0.1.x 实现计划归档（Iter 1.1~1.5）
│   │   ├── archived_plan.0.2.x.md             # v0.2.x 实现计划归档（B/C/D 等迭代详情）
│   │   ├── archived_review-findings.0.1.x.md  # v0.1.x 自审问题记录归档
│   │   ├── archived_review-findings.0.2.x.md  # v0.2.x 自审问题记录归档（R-149~R-159 等 8 条）
│   │   ├── archived_changelog.0.3.x.md        # v0.3.x 版本变更日志归档（v0.3.0 ~ v0.3.10 共 8 个版本）
│   │   ├── archived_plan.0.3.x.md             # v0.3.x 实现计划归档（D-8b/D-10/D-11 审查修复）
│   │   ├── archived_review-findings.0.3.x.md  # v0.3.x 自审问题记录归档（D-9/D-10/D-11 等 6 条）
│   │   ├── archived-data-source-pre-study.md  # 数据源预研笔记（已归档，原位于 plan/notes/）
│   │   ├── test-runtime-optimization/         # 📁 测试可扩展性优化设计归档
│   │   │   └── A5-test-runtime-optimization.md # 测试运行时可扩展性优化设计（已归档）
│   │   ├── fund-deep-analysis/                # 📁 基金深度分析设计归档
│   │   │   └── B1-fund-deep-analysis.md       # 基金深度分析 4 模块设计（已归档）
│   │   ├── report-section-order-config/                        # 📁 报告序号可配置设计归档
│   │   │   └── report-section-order-config.md                  # 报告序号可配置设计（已归档）
│   │   ├── akshare-integration/                        # 📁 akshare 数据源集成归档
│   │   │   └── akshare-integration-profit-forecast-sector-flow.md  # akshare 盈利预测 + 资金流向集成（已归档）
│   │   ├── report-early-warning/                       # 📁 智能预警 + P1 代码优化归档
│   │   │   └── early-warning-and-p1-optimization.md    # 智能预警 + P1 代码优化实施计划（已归档）
│   │   ├── test-add-config-edge-testcase/               # 📁 配置/环境纵深测试归档
│   │   │   └── y5-edge-test-config-env.md              # 配置/环境纵深测试实施计划（已归档）
│   │   ├── data-degradation/                                   # 📁 数据降级重构归档
│   │   │   ├── d-iteration-data-degradation-design.md          # 数据降级分层治理完整设计（已归档）
│   │   │   ├── d-iteration-data-degradation-iteration-plan.md  # 精细化子迭代拆分方案（已归档）
│   │   │   └── data-degradation-refactoring.md                 # 数据降级系统重构精细化子迭代方案（已归档）
│   │   ├── test-coverage-map/                        # 📁 场景-测试文件覆盖率映射归档
│   │   │   ├── test-coverage-map.md                  # 场景-测试文件覆盖率映射（已归档）
│   │   │   └── validate_coverage_map.py              # 覆盖率映射验证脚本（已归档）
│   │   ├── test-verify-mode-optimization/               # 📁 verify 模式测试优化归档
│   │   │   └── r200_verify_mode_optimization.md         # verify 模式测试执行优化（已归档）
│   │   ├── refactor-cache-engine/                      # 📁 缓存引擎重构设计归档
│   │   │   └── cache-refactor-plan.md                  # 缓存引擎 Strangler Fig 重构计划（已归档）
│   │   ├── refactor-excel-generator/              # Excel 报告编排器，统筹各子模块完成报告生成
│   │   │   └── R-206-excel-generator-split-plan.md # Excel 报告编排器，统筹各子模块完成报告生成
│   │   ├── refactor-html_writer/                     # 📁 html_writer.py 分拆设计归档
│   │   │   └── r178_html_writer_split.md             # html_writer.py 5 步分拆计划（含 C14 约束引入）（已归档）
│   │   ├── refactor-market_value_split_design/       # 📁 market_value.py 分拆设计归档
│   │   │   └── r197_market_value_split.md            # market_value.py 拆分为计算层+写入层（已归档）
│   │   ├── refactor-llm_split_design/                # 📁 LLM 模块分拆设计归档
│   │   │   └── r198_llm_split_design.md              # LLM 模块横向拆分（已归档）
│   │   ├── refactor-summary-llm-usage/             # 📁 summary.py LLM 用量拆分设计归档
│   │   │   └── R-207-summary-llm-usage-split-plan.md # summary.py LLM 用量拆分（已归档）
│   │   └── portfolio-history-comparison/              # 📁 组合历史走势设计归档
│   │       └── F-portfolio-history-comparison.md     # 组合历史走势计划与技术设计（已归档）
│   ├── plan/                         # 计划与设计文件
│   ├── manuals/                      # 用户文档分册
│   │   ├── how-to-start.md           # 快速开始 — 启动方式、持仓格式、菜单操作说明
│   │   ├── how-to-config.md          # 配置指南 — config.json 字段说明 + cache_ttl + 缓存分组
│   │   ├── how-to-config-llm.md      # LLM 配置指引 — llm_key.json / llm_settings.json
│   │   ├── how-to-use-registry.md    # 中央注册表使用说明
│   │   ├── datasource-and-folders.md # 数据源一览 + 目录结构（本文档）
│   │   ├── faq.md                    # 常见问题解答 — 使用中的高频问题，按类别组织
│   │   ├── how-to-test-my-code.md    # 如何测试我的代码 — 本地运行测试、测试报告系统、新增测试指南
│   │   └── reports-instruction.md    # 报告文件结构说明
│   ├── tmp/                          # 临时文件 / 过程文件（git 忽略）
│   └── managements/                  # 管理文档
│       ├── plan.md                   # 实现计划（关键技术决策 + 下一步迭代计划）
│       ├── requirements.md           # 需求文档（完整需求规格）
│       ├── technical.md              # 技术设计文档
│       ├── llm-technical.md          # LLM 客户端架构与技术细节
│       ├── testplan.md               # 质量控制与测试标准
│       ├── changelog.md              # 变更日志 — 当前 [Unreleased] 版本；v0.1.x/v0.2.x 完整记录见 archives/
│       ├── test-coverage.md          # 测试覆盖统计（mode/功能域/场景分组/单元分组/跨类标记）
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

> 注意：项目每次版本变更后，目录树和测试文件数可能滞后。请以代码仓库实际结构为准。
>
> 最后更新：2026-07-13
