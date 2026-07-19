# 目录结构

> 文档版本：v0.7.1-dev
>
> 项目目录树 — 新增/重命名任何非排除文件或目录时，必须同步更新此文档。
>
> **项目统计**
>
> | 类别 | 开发语言 | 文件数 | 代码行数 | 说明 |
> |---|---|---|---|---|
> | 主程序代码 | Python | 121 | 28,081 | `src/python/` 下所有 `.py`（不含测试） |
> | HTML 报告模板 | HTML | 1 | 1,750 | `src/python/tmpl/report_template.html` |
> | 辅助脚本 | Python/Shell | 6 | 1,739 | `scripts/`（启动脚本、测试驱动、工具检查） |
> | **源代码合计** | — | **128** | **31,570** | 主程序 + 模板 + 脚本 |
> | **测试代码** | Python | **158** | **50,346** | `src/test/` 所有 `.py` 文件 |
> | **测试用例** | — | — | **3,253 个** | `pytest --collect-only` 统计 |
> | **用户文档** | Markdown | **67** | **31,523** | `docs-stm/`（65 文件）+ `README.md` + `CLAUDE.md` |

## 目录树

```
investor-util/
│
├── src/                              # 源代码
│   ├── python/                       # 主程序代码
│   │   ├── __init__.py               #   包标记（空文件）
│   │   ├── cache/                    # 缓存引擎（TTL/清理/统计/分组/IO）
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── _cleanup.py           #   过期缓存清理（按 TTL 分组删除）
│   │   │   ├── _groups.py            #   缓存分组管理（按前缀路由到不同组）
│   │   │   ├── _io.py                #   缓存序列化/反序列化（JSON/GZip）
│   │   │   ├── _paths.py             #   缓存文件路径生成与管理
│   │   │   ├── _stats.py             #   缓存统计信息（命中率/大小/数量）
│   │   │   ├── _store.py             #   缓存存取核心（get/set/delete/exists）
│   │   │   ├── _ttl.py               #   TTL 策略（含盘中/盘后/非交易日区分）
│   │   │   ├── operations.py             #   缓存操作共享层（S8~S11 从 handlers_cache 提取）
│   │   │   └── services/             # 缓存上层服务
│   │   │       ├── __init__.py       #       子包标记
│   │   │       └── holdings_tracker.py #     持仓快照缓存追踪器
│   │   │
│   │   ├── config/                   # 配置管理
│   │   │   ├── __init__.py           #   子包标记，导出统一配置入口
│   │   │   ├── _comments.py          #   配置文件注释读写
│   │   │   ├── _config_defaults.py   #   config.json 默认值定义
│   │   │   ├── _core.py              #   配置加载/保存/校验核心逻辑
│   │   │   ├── _llm_defaults.py      #   llm_settings.json 默认值定义
│   │   │   └── _llm_providers_defaults.py # llm_providers.json 默认值定义
│   │   │
│   │   ├── fetcher/                  # 数据获取调度
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── akshare.py            #   akshare 封装层（盈利预测/资金流向/分红）
│   │   │   ├── chain.py              #   Provider Chain 获取链路（主→备→过期缓存）
│   │   │   ├── fund.py               #   基金数据获取（净值/业绩排名/持仓）
│   │   │   ├── fund_manager.py       #   基金经理数据获取
│   │   │   ├── history_diff.py       #   历史数据差分同步
│   │   │   ├── index.py              #   指数行情获取（A股/美股，直连 API 不走 Chain）
│   │   │   ├── industry.py           #   行业分类/概念板块数据获取
│   │   │   ├── news.py               #   新闻数据获取封装层（聚合器+关键词转发）
│   │   │   └── price.py              #   行情价格获取（股票/ETF）
│   │   │
│   │   ├── providers/                # 数据源提供商实现
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── tencent.py            #   腾讯财经 API（A 股/ETF 实时价）
│   │   │   ├── sina.py               #   新浪财经 API（备用实时价/美股指数）
│   │   │   ├── eastmoney.py          #   东方财富 API（场外基金净值/历史净值）
│   │   │   ├── eastmoney_industry.py #   东方财富行业分类/概念板块
│   │   │   ├── eastmoney_industry_rest.py # 东方财富行业 REST 接口封装
│   │   │   ├── tiantian.py           #   天天基金 API（基金业绩排名/评级）
│   │   │   ├── akshare_extras.py     #   akshare 封装（盈利预测/资金流向/分红）
│   │   │   ├── akshare_news.py       #   akshare 新闻源（财新网/CCTV）
│   │   │   ├── sina_news.py          #   新浪财经新闻源
│   │   │   ├── eastmoney_news.py     #   东方财富新闻源
│   │   │   ├── cls_news.py           #   财联社新闻源（签名鉴权，默认关闭）
│   │   │   ├── wallstreetcn_news.py  #   华尔街见闻新闻源
│   │   │   ├── news_aggregator.py    #   新闻聚合器（多源合并去重）
│   │   │   ├── news_correlator.py    #   新闻与持仓关联分析
│   │   │   ├── news_keywords.py      #   新闻关键词提取与匹配
│   │   │   └── news_sources.py       #   新闻源注册与配置
│   │   │
│   │   ├── analysis/                 # 业务计算层（独立无依赖，不导入 report/）
│   │   │   ├── __init__.py           #   包标记；导出 check_liquidity 等
│   │   │   ├── metrics.py            #   量化指标计算（夏普/卡玛/HHI/Beta 等）
│   │   │   ├── simple_rebalance.py   #   极简再平衡（单品种超15%警戒线）
│   │   │   ├── circuit_breaker_wrapper.py # 指标级断路包装器
│   │   │   ├── drawdown_warning.py   #   回撤历史分位预警
│   │   │   └── liquidity.py          #   流动性风险评估（场内品种变现天数计算）
│   │   │
│   │   ├── llm/                      # LLM 智能分析
│   │   │   ├── api.py                #   LLM API 主入口（自动路由 provider）
│   │   │   ├── api_base.py           #   LLM API 基类（请求/重试/流式）
│   │   │   ├── circuit_breaker.py    #   熔断器（连续失败/冷却恢复）
│   │   │   ├── fingerprint.py        #   缓存指纹（请求去重，避免重复调用）
│   │   │   ├── generators.py         #   提示词生成（全局政经/智囊团复盘）
│   │   │   ├── generators_news.py    #   新闻分析提示词生成
│   │   │   ├── generators_orchestrator.py # LLM 多轮对话编排
│   │   │   ├── markdown.py           #   LLM 输出 Markdown 解析/格式化
│   │   │   ├── pricing.py            #   Token 计费与用量统计
│   │   │   ├── prompts.py            #   提示词模板库
│   │   │   ├── session.py            #   LLM 会话管理（上下文窗口/历史）
│   │   │   ├── skeleton.py           #   LLM 内容骨架生成（结构化输出引导）
│   │   │   └── strategy.py           #   Provider 多链切换策略引擎
│   │   │
│   │   ├── schemas/                  # 数据模型定义
│   │   │   ├── __init__.py           #   子包标记
│   │   │   └── history.py            #   历史净值/行情数据模型
│   │   │
│   │   ├── report/                   # 报告生成引擎
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── benchmark.py          #   业绩基准配置与匹配
│   │   │   ├── excel_generator.py    #   Excel 报告生成总控
│   │   │   ├── excel_module_loader.py #  Excel 页签模块动态加载
│   │   │   ├── excel_sheet_factory.py #  Excel 页签工厂（按配置创建页签）
│   │   │   ├── excel_content_sheets.py #  Excel 内容页签（持仓明细/汇总）
│   │   │   ├── excel_market_data.py  #   Excel 行情数据页签
│   │   │   ├── excel_news_warning.py #   Excel 新闻页签
│   │   │   ├── excel_b_series.py     #   Excel B 系列基金深度分析页签
│   │   │   ├── excel_llm_usage.py    #   Excel LLM 用量统计页签
│   │   │   ├── excel_writer.py       #   Excel 底层写入器（openpyxl 封装）
│   │   │   ├── html_writer.py        #   HTML 报告主写入器
│   │   │   ├── html_builders.py      #   HTML 各区块构建器
│   │   │   ├── html_renderers.py     #   HTML 渲染管线
│   │   │   ├── html_jinja_env.py     #   Jinja2 模板环境配置
│   │   │   ├── html_save.py          #   HTML 保存/导出
│   │   │   ├── penetration.py        #   穿透持仓分析（嵌套基金）
│   │   │   ├── penetration_sheet.py  #   穿透分析 Excel 页签
│   │   │   ├── market_value.py       #   市值计算与盈亏分析
│   │   │   ├── market_value_sheet.py #   市值分析 Excel 页签
│   │   │   ├── category.py           #   持仓分类（股票/基金/债券/QDII 等）
│   │   │   ├── fund_performance.py   #   基金业绩分析（排名/回撤/超额收益）
│   │   │   ├── fund_concentration.py #   基金持仓集中度分析
│   │   │   ├── fund_concentration_sheet.py # 集中度 Excel 页签
│   │   │   ├── fund_manager_analysis.py # 基金经理分析
│   │   │   ├── fund_manager_sheet.py #   基金经理 Excel 页签
│   │   │   ├── fund_overlap.py       #   基金持仓重叠分析
│   │   │   ├── fund_overlap_sheet.py #   重叠分析 Excel 页签
│   │   │   ├── fund_style_analysis.py #  基金风格分析（大小盘/价值成长）
│   │   │   ├── fund_style_sheet.py   #   风格分析 Excel 页签
│   │   │   ├── portfolio_history.py  #   组合历史净值走势分析
│   │   │   ├── history_snapshot.py   #   持仓快照管理（保留 60 天）
│   │   │   ├── news_correlation.py   #   新闻与持仓关联分析报告
│   │   │   ├── orchestrator.py       #   报告编排共享层（TUI/CLI 共用）
│   │   │   ├── summary.py            #   报告摘要生成
│   │   │   ├── summary_llm_usage.py  #   LLM 使用情况摘要
│   │   │   ├── data_status.py        #   数据质量状态（缺失/过期/降级标记）
│   │   │   ├── llm_content.py        #   LLM 分析结果写入报告
│   │   │   ├── llm_module_info.py    #   LLM 模块信息构建（共享函数）
│   │   │   ├── progress.py           #   报告生成进度跟踪
│   │   │   ├── cli_progress.py         #   CLI 进度报告器（CliProgressReporter）
│   │   │   └── styles.py             #   Excel 样式定义
│   │   │
│   │   ├── tmpl/                     # HTML 报告模板
│   │   │   └── report_template.html  #   Jinja2 HTML 报告主模板
│   │   │
│   │   ├── main.py                   # 程序入口 + TUI 主循环
│   │   ├── cli.py                    # 程序入口 + CLI 命令行模式（argparse + 共享层路由）
│   │   ├── tui.py                    # TUI 交互主界面
│   │   ├── tui_menu.py               # TUI 菜单系统
│   │   ├── tui_handlers.py           # TUI 键盘/事件处理
│   │   ├── handlers_report.py        # 报告生成命令处理器
│   │   ├── handlers_cache.py         # 缓存管理命令处理器
│   │   ├── handlers_config.py        # 配置管理命令处理器
│   │   ├── registry.py               # 中央注册表（模块/TTL/分组定义）
│   │   ├── provider_registry.py      # 数据源注册中心（熔断器/会话缓存）
│   │   ├── models.py                 # 数据模型（持仓/行情/基金/新闻）
│   │   ├── reader.py                 # 持仓 xlsx 文件读取
│   │   ├── ansi_colors.py            # ANSI 颜色常量（终端输出着色）
│   │   ├── code_utils.py             # 证券代码/类型判定工具
│   │   ├── market_hours.py           # 交易时段判断（A股/港股/QDII）
│   │   ├── http_client.py            # HTTP 客户端（请求/重试/超时）
│   │   ├── constants.py              # 全局常量/版本号
│   │   └── logger.py                 # 日志模块（文件+控制台，自动轮转）
│   │
│   └── test/                         # 测试套件
│       ├── unit/                     #   单元测试（8 子组：providers/fetcher/llm/news/report/config/core/ui）
│       │   ├── test_liquidity.py          #   流动性分析：场内品种变现天数（10 tests）
│       │   ├── test_liquidity_edge.py     #   流动性分析：边缘场景（极端大持仓/低流动性/空K线）
│       │   ├── test_liquidity_otc.py      #   流动性分析：场外赎回天数（配置上限/未配置/零上限，8 tests）
│       │   └── test_liquidity_otc_edge.py #   流动性分析：场外边缘场景（巨额赎回/混合配置）
│       ├── integration/              #   集成测试（契约/隔离/流水线）
│       ├── scenario/                 #   场景测试（basic/resilience/extreme/llm/datetime）
│       ├── conftest.py               #   pytest 全局配置 + 标记注册
│       ├── helpers.py                #   测试辅助工具
│       ├── test_cli.py               #   CLI 命令行模式单元测试
│       ├── test_cli_edge.py          #   CLI 边缘场景测试
│       ├── test_cli_integration.py   #   CLI 集成测试
│       └── test_orchestrator.py      #   报告编排器单元测试
│
├── data/                             # 运行时数据
│   ├── holdings/                     #   持仓 xlsx 文件（用户放置）
│   ├── cache/                        #   API 响应缓存（自动生成，JSON/GZ）
│   ├── config/                       #   配置文件（config.json / llm_key.json / llm_settings.json）
│   ├── state/                        #   运行时状态文件（降级状态等，自动生成）
│   └── history/snapshots/            #   持仓快照（自动生成，保留 60 天）
│
├── reports/                          # 报告输出（最新版 + 按日期归档）
├── logs/                             # 程序日志（app.log，自动轮转）
├── test-reports/                     # 测试报告（自动生成，按 mode 分组）
├── scripts/                          # 启动脚本 + 测试工具
│   ├── launch.ps1                    #   Windows PowerShell 启动脚本
│   ├── launch.sh                     #   Linux/macOS 启动脚本
│   ├── test_runner.py                #   测试驱动（pytest 模式封装）
│   ├── check-test-markers.py         #   测试标记合规检查
│   ├── check-version-consistency.py  #   版本号一致性检查
│   └── extract-test-failures.py      #   pytest-html 报告失败用例提取
│
├── docs-stm/                         # 项目文档
│   ├── manuals/                      #   用户手册分册
│   │   ├── datasource.md             #     数据源一览
│   │   ├── faq.md                    #     常见问题解答
│   │   ├── how-to-config-llm.md      #     LLM 配置指南
│   │   ├── how-to-config.md          #     配置说明
│   │   ├── how-to-menu.md            #     菜单操作指南
│   │   ├── how-to-start.md           #     快速上手
│   │   ├── how-to-schedule.md       #     定时任务配置指南
│   │   ├── how-to-test-my-code.md    #     测试编写指南
│   │   ├── how-to-use-registry.md    #     注册表使用说明
│   │   └── reports-instruction.md    #     报告使用说明
│   ├── managements/                  #   管理文档
│   │   ├── changelog.md              #     变更日志
│   │   ├── folders.md                #     目录结构
│   │   ├── llm-technical.md          #     LLM 技术设计
│   │   ├── plan.md                   #     总体实现计划
│   │   ├── requirements.md           #     需求规格说明
│   │   ├── review-findings.md        #     自审记录
│   │   ├── technical.md              #     技术设计文档
│   │   ├── test-coverage.md          #     测试覆盖率统计
│   │   └── testplan.md               #     测试计划
│   ├── plan/                         #   中间设计文件（当前迭代中）
│   │   ├── better-investment-advice/            #   投资建议改进分析讨论
│   │   │   ├── discussion-better-investment-advice.md    # 可行性调研：6 层改进方向与实施路径
│   │   │   ├── better-investment-task.md                 # 最小粒度工作任务分解（86 任务）
│   │   │   ├── f_context-schema.md              # f_context Pre-Schema 文档（管线键定义+类型断言）
│   │   │   └── rf-and-885005-test-report.md              # Rf & 885005 数据源稳定性专项测试报告

│   ├── archive/                      #   历史归档
│   │   ├── v0.1.x/                            # v0.1.x 版本迭代归档
│   │   │   ├── archived_changelog.0.1.x.md        # 变更日志归档 v0.1.x
│   │   │   ├── archived_plan.0.1.x.md             # 实现计划归档 v0.1.x
│   │   │   └── archived_review-findings.0.1.x.md  # 自审记录归档 v0.1.x
│   │   ├── v0.2.x/                            # v0.2.x 版本迭代归档
│   │   │   ├── archived_changelog.0.2.x.md        # 变更日志归档 v0.2.x
│   │   │   ├── archived_plan.0.2.x.md             # 实现计划归档 v0.2.x
│   │   │   ├── archived_review-findings.0.2.x.md  # 自审记录归档 v0.2.x
│   │   │   ├── archived-data-source-pre-study.md  # 数据源可行性预研报告
│   │   │   ├── data-degradation/                  # 数据降级处理方案
│   │   │   │   ├── d-iteration-data-degradation-design.md     # 数据降级设计
│   │   │   │   ├── d-iteration-data-degradation-iteration-plan.md # 数据降级迭代计划
│   │   │   │   └── data-degradation-refactoring.md            # 数据降级重构
│   │   │   ├── fund-deep-analysis/                # 基金深度分析
│   │   │   │   └── B1-fund-deep-analysis.md       # 基金持仓深度分析迭代
│   │   │   ├── profit-forecast-sector-flow/          # 盈利预测与资金流向
│   │   │   │   └── profit-forecast-sector-flow-akshare-integration.md # 盈利预测+资金流向 akshare 集成
│   │   │   ├── report-early-warning/              # 预警优化
│   │   │   │   └── early-warning-and-p1-optimization.md # 预警与 P1 优化
│   │   │   ├── report-section-order-config/       # 报告章节顺序
│   │   │   │   └── report-section-order-config.md # 报告章节顺序配置
│   │   │   ├── test-coverage-map/                 # 测试覆盖地图
│   │   │   │   ├── test-coverage-map.md           # 测试覆盖地图文档
│   │   │   │   └── validate_coverage_map.py       # 覆盖地图验证脚本
│   │   │   └── test-runtime-optimization/         # 测试运行优化
│   │   │       └── A5-test-runtime-optimization.md # 测试运行优化
│   │   ├── v0.3.x/                            # v0.3.x 版本迭代归档
│   │   │   ├── archived_changelog.0.3.x.md        # 变更日志归档 v0.3.x
│   │   │   ├── archived_plan.0.3.x.md             # 实现计划归档 v0.3.x
│   │   │   ├── archived_review-findings.0.3.x.md  # 自审记录归档 v0.3.x
│   │   │   ├── refactor-cache-engine/             # 缓存引擎重构
│   │   │   │   └── cache-refactor-plan.md         # 缓存引擎重构计划
│   │   │   ├── refactor-excel-generator/          # Excel 生成器重构
│   │   │   │   └── R-206-excel-generator-split-plan.md # Excel 生成器拆分计划
│   │   │   ├── refactor-html_writer/              # HTML 写入器重构
│   │   │   │   └── r178_html_writer_split.md      # HTML 写入器拆分
│   │   │   ├── refactor-llm_split_design/         # LLM 拆分重构
│   │   │   │   └── r198_llm_split_design.md       # LLM 拆分设计
│   │   │   ├── refactor-market_value_split_design/ # 市值拆分重构
│   │   │   │   └── r197_market_value_split.md     # 市值拆分设计
│   │   │   ├── refactor-summary-llm-usage/        # LLM 用量摘要重构
│   │   │   │   └── R-207-summary-llm-usage-split-plan.md # LLM 用量摘要拆分计划
│   │   │   └── test-verify-mode-optimization/     # 测试verify 模式运行优化
│   │   │       └── r200_verify_mode_optimization.md # 测试verify 模式运行优化
│   │   ├── v0.4.x/                            # v0.4.x 版本迭代归档
│   │   │   ├── archived_changelog.0.4.x.md        # 变更日志归档 v0.4.x
│   │   │   ├── archived_plan.0.4.x.md             # 实现计划归档 v0.4.x
│   │   │   ├── archived_review-findings.0.4.x.md  # 自审记录归档 v0.4.x
│   │   │   ├── portfolio-history-comparison/      # 组合历史对比
│   │   │   │   ├── F-portfolio-history-comparison.md        # F 迭代计划与技术设计
│   │   │   │   └── html-report-chart-native-canvas-fallback-plan.md # HTML Canvas 渲染修复
│   │   │   └── test-add-config-edge-testcase/     # 边缘测试配置
│   │   │       └── y5-edge-test-config-env.md     # 边缘测试配置环境
│   │   ├── v0.5.x/                            # v0.5.x 版本迭代归档
│   │   │   ├── archived_changelog.0.5.x.md        # 变更日志归档 v0.5.x
│   │   │   ├── archived_plan.0.5.x.md             # 实现计划归档 v0.5.x
│   │   │   ├── archived_review-findings.0.5.x.md  # 自审记录归档 v0.5.x
│   │   │   ├── portfolio-benchmark-comparison/    # I 迭代基准指数对比归档
│   │   │   │   ├── I-comparative-benchmark-design.md    # I 迭代基准对比设计
│   │   │   │   ├── I-comparative-benchmark-iteration.md # I 迭代基准对比迭代计划
│   │   │   │   └── plan-iter-8-excel-benchmark-columns.md # I 迭代 Excel 基准指数列
│   │   │   └── report-board-visibility-configable/ # 看板可见性配置
│   │   │       └── g-board-visibility-iteration-plan.md # 看板可见性配置迭代计划
│   │   ├── v0.6.x/                            # v0.6.x 版本迭代归档
│   │   │   ├── archived_changelog.0.6.x.md        # 变更日志归档 v0.6.x
│   │   │   ├── archived_plan.0.6.x.md             # 实现计划归档 v0.6.x
│   │   │   ├── archived_review-findings.0.6.x.md  # 自审记录归档 v0.6.x
│   │   │   ├── llm-multi-provider/                # 多 LLM Provider 链式服务归档
│   │   │   │   ├── llm-multi-provider-design.md       # 多 LLM Provider 链式服务技术设计
│   │   │   │   └── llm-multi-provider-iteration-plan.md # 多 LLM Provider 链式服务迭代计划
│   │   │   └── cli-mode/                          # CLI 命令行模式归档
│   │   │       ├── cli-mode-iteration-plan.md     # CLI 迭代计划
│   │   │       └── cli-mode-technical-design.md   # CLI 技术设计
│   │   └── tmp/                          #   临时文件（git 忽略，不展开）
│
├── CLAUDE.md                         # AI 编程助手指引
├── README.md                         # 用户文档总入口
├── pyproject.toml                    # Python 项目元数据
├── requirements.txt                  # Python 依赖清单
└── .gitignore                        # Git 忽略规则
```

> 注意：目录树为主层级结构，测试文件数和文件行数随版本迭代变化。
