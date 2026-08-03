# 目录结构

> 文档版本：0.10.0
>
> 项目目录树 — 新增/重命名任何非排除文件或目录时，必须同步更新此文档。
>
> **项目统计**
>
> | 类别 | 开发语言 | 文件数 | 代码行数 | 说明 |
> |---|---|---|---|---|
| 主程序代码 | Python | 209 | 49,353 | `src/python/` 下所有 `.py`（不含测试，含 14 个 `__init__.py`） |
| HTML 报告模板 | HTML | 3 | 3,298 | `src/python/tmpl/report_template.html` + `whatif_template.html`（调仓 What-if 独立 HTML 页）+ `partials/evolution_section.html`（组合演进章节 partial） |
| 辅助脚本 | Python | 16 | 4,900 | `scripts/`（启动脚本、测试驱动、工具检查、任务编号检查、性能测试、LLM 幻觉率评估、测试覆盖计数、代码/文档历史痕迹检查、Claude Code hook 安装/校验） |
| **源代码合计** | — | **228** | **57,551** | 主程序 + 模板 + 脚本 |
| **测试代码** | Python | **247** | **69,599** | `src/test/` 所有 `.py` 文件 |
| **测试用例** | — | — | **4,425 个** | `pytest --collect-only` 统计（`scripts/collect-test-coverage.py` 实时收集快照） |
| **用户文档** | Markdown | **13** | — | 含 README.md |
| ├ manuals/ | 用户手册分册 | 12 | — | 配置/faq/快速上手/CLI 等 |
| **项目文档** | Markdown | **97** | — | 含 CLAUDE.md |
| ├ managements/ | 管理文档 | 9 | — | 变更日志/目录树/测试计划/技术设计等 |
| ├ archive/ | 版本归档 | 92 | — | 各版本 changelog/plan/review-findings 等（88 md + 3 py + 1 txt） |
| ├ plan/ | 中间设计文件 | 1 | — | 当前迭代中的设计方案 |
| └ tmp/ | 临时文件 | — | — | 调试产物、迁移暂存（git 忽略，不计入统计） |

## 目录树

```
investor-util/
├── src/                              # 源代码
│   ├── python/                       # 主程序代码
│   │   ├── __init__.py               #   包标记（空文件）
│   │   ├── startup_wizard.py         #   首次运行引导向导（检查配置/创建模板/启动模式引导）
│   │   ├── cache/                    # 缓存引擎（TTL/清理/统计/分组/IO）
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── _cleanup.py           #   过期缓存清理（按 TTL 分组删除）
│   │   │   ├── _groups.py            #   缓存分组管理（按前缀路由到不同组）
│   │   │   ├── _io.py                #   缓存序列化/反序列化（JSON/GZip）
│   │   │   ├── _paths.py             #   缓存文件路径生成与管理
│   │   │   ├── _stats.py             #   缓存统计信息（命中率/大小/数量）
│   │   │   ├── _store.py             #   缓存存取核心（get/set/delete/exists）
│   │   │   ├── _ttl.py               #   TTL 策略（含盘中/盘后/非交易日区分）
│   │   │   ├── operations.py             #   缓存操作共享层
│   │   │   └── services/             # 缓存上层服务
│   │   │       ├── __init__.py       #       子包标记
│   │   │       └── holdings_tracker.py #     持仓快照缓存追踪器
│   │   │
│   │   ├── config/                   # 配置管理
│   │   │   ├── __init__.py           #   子包标记，导出统一配置入口
│   │   │   ├── _comments.py          #   配置文件注释读写
│   │   │   ├── _config_defaults.py   #   config.json 默认值定义
│   │   │   ├── _core.py              #   配置加载/保存/校验核心逻辑
│   │   │   ├── _json_patch.py        #   JSON 字段级文本替换（dict 区块 brace 平衡）
│   │   │   ├── _llm_defaults.py      #   llm_settings.json 默认值定义
│   │   │   ├── _llm_providers.py     #   LLM 提供程序配置解析
│   │   │   ├── _llm_providers_defaults.py # llm_providers.json 默认值定义
│   │   │   ├── _local_state.py       #   机器本地状态标志读写（首次引导/隐私已读，存 data/state/local_state.json，含 config.json 旧键惰性迁移）
│   │   │   ├── _validation.py        #   配置校验函数集
│   │   │   ├── anonymizer.py         #   匿名化模块（4 模式：关闭/代码显示/完全匿名/汇总）
│   │   │   └── features.py           #   Feature Flag 注册中心（开关集中管理，含默认值与运行时控制，持久化到 data/config/features.json）
│   │   │
│   │   ├── fetcher/                  # 数据获取调度
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── akshare.py            #   akshare 封装层（盈利预测/资金流向/分红）
│   │   │   ├── bond_yield.py         #   无风险利率获取（akshare 国债收益率 + config 手动兜底）
│   │   │   ├── batch.py              #   批量并行调度（BatchDispatcher + RateLimiter）
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
│   │   │   ├── _utils.py             #   提供商模块共享工具函数
│   │   │   ├── tencent.py            #   腾讯财经 API（A 股/ETF 实时价）
│   │   │   ├── sina.py               #   新浪财经 API（备用实时价/美股指数）
│   │   │   ├── sina_kline.py          #   新浪财经 API — K 线数据
│   │   │   ├── eastmoney.py          #   东方财富 API（场外基金净值/历史净值）
│   │   │   ├── eastmoney_industry.py #   东方财富行业分类/概念板块
│   │   │   ├── eastmoney_industry_rest.py # 东方财富行业 REST 接口封装
│   │   │   ├── tiantian_base.py        #   天天基金 API — 公共 HTTP 请求解析
│   │   │   ├── tiantian_holdings.py    #   天天基金 API — 基金持仓数据
│   │   │   ├── tiantian_nav.py         #   天天基金 API — 历史净值数据
│   │   │   ├── tiantian_ranking.py     #   天天基金 API — 业绩排名/评级/风险分析
│   │   │   ├── akshare_extras.py     #   akshare 封装（盈利预测/资金流向/分红）
│   │   │   ├── akshare_news.py       #   akshare 新闻源（财新网/CCTV）
│   │   │   ├── sina_news.py          #   新浪财经新闻源
│   │   │   ├── eastmoney_news.py     #   东方财富新闻源
│   │   │   ├── cls_news.py           #   财联社新闻源（签名鉴权，默认关闭）
│   │   │   ├── wallstreetcn_news.py  #   华尔街见闻新闻源
│   │   │   ├── news_aggregator.py    #   新闻聚合器（多源合并去重）
│   │   │   ├── news_dedup.py         #   新闻标题去重
│   │   │   ├── news_correlator.py    #   新闻与持仓关联分析
│   │   │   ├── news_keywords.py      #   新闻关键词提取与匹配
│   │   │   └── news_sources.py       #   新闻源注册与配置
│   │   │
│   │   ├── analysis/                 # 业务计算层（独立无依赖，不导入 report/）
│   │   │   ├── __init__.py                    #   包标记；导出 check_liquidity 等
│   │   │   ├── _fee_estimation.py             #   组合综合费率估算
│   │   │   ├── _math_utils.py                 #   数学工具函数（Beta/t-分布）
│   │   │   ├── _silence.py                    #   再平衡静默期管理
│   │   │   ├── alignment_correction.py        #   口径修正因子计算（估值偏差校准）
│   │   │   ├── circuit_breaker_wrapper.py     #   指标级断路包装器
│   │   │   ├── drawdown_warning.py            #   回撤历史分位预警
│   │   │   ├── drawdown_events.py             #   回撤事件识别（新高/回撤起止/幅度）
│   │   │   ├── factor_exposure.py             #   因子暴露分析（MVP 3 因子：价值/成长/质量，OLS 回归）
│   │   │   ├── correlation.py                 #   持仓相关性矩阵（Pearson 相关/显著性/下三角矩阵）
│   │   │   ├── fx_exposure.py                 #   外汇敞口分析（港股/QDII 汇率风险）
│   │   │   ├── liquidity.py                   #   流动性风险评估（场内品种变现天数计算）
│   │   │   ├── metrics.py                     #   量化指标计算（夏普/卡玛/HHI/Beta 等）
│   │   │   ├── portfolio_evolution.py         #   组合演进（多快照聚合 → C19 evolution_data）
│   │   │   ├── rebalance.py                   #   再平衡信号计算（品种偏离度/调整建议）
│   │   │   ├── scenario.py                    #   情景分析（Beta 推导 → 6 种市场情景预期变动）
│   │   │   ├── simple_rebalance.py            #   极简再平衡（单品种超15%警戒线）
│   │   │   ├── whatif.py                      #   调仓 What-if 模拟（双持仓成本口径对比）
│   │   │   └── whatif_backtest.py             #   调仓 What-if 时序回测（纯计算：生效日折算/序列对齐/5 指标）
│   │   │
│   │   ├── llm/                      # LLM 智能分析
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── api.py                #   LLM API 主入口（自动路由 provider）
│   │   │   ├── api_base.py           #   LLM API 基类（请求/重试/流式）
│   │   │   ├── _thinking.py          #   Extended Thinking 配置
│   │   │   ├── circuit_breaker.py    #   熔断器（连续失败/冷却恢复）
│   │   │   ├── cost_tracker.py       #   Token 成本跟踪与预算管理（会话级 Token 守卫）
│   │   │   ├── fact_checker/         # LLM 事实锚定校验器（数值/品种/排名一致性校验）
│   │   │   │   ├── __init__.py       #       子包标记，re-export run_fact_check 等 4 个公开函数
│   │   │   │   ├── _constants.py     #       关键词词表/指数代码集/默认容差
│   │   │   │   ├── _context.py       #       语境检测（回撤/变化率/贡献度/仓位/假设/建议）
│   │   │   │   ├── _corrections.py   #       数值自动修正
│   │   │   │   ├── _numerical.py     #       数值一致性检查器
│   │   │   │   ├── _patterns.py      #       正则模式
│   │   │   │   ├── _ranking.py       #       排名正确性检查器
│   │   │   │   ├── _runner.py        #       run_fact_check 统一入口（全量校验 + 自动修正）
│   │   │   │   ├── _symbols.py       #       品种存在性检查器
│   │   │   │   └── _utils.py         #       HTML 剥离/句子拆分/持仓映射/组合数值
│   │   │   ├── fallback.py           #   LLM 故障降级模板（所有模块失败时提供占位内容，防止报告空白）
│   │   │   ├── fingerprint.py        #   缓存指纹（请求去重，避免重复调用）
│   │   │   ├── generators.py         #   提示词生成（全局政经/智囊团复盘）
│   │   │   ├── generators_news.py    #   新闻分析提示词生成
│   │   │   ├── generators_orchestrator.py # LLM 多轮对话编排
│   │   │   ├── _api_claude.py         #   Claude API 调用实现
│   │   │   ├── _call_claude.py        #   Claude API 单 Provider 调用
│   │   │   ├── _api_gemini.py         #   Gemini API 调用实现
│   │   │   ├── _call_gemini.py        #   Gemini API 单 Provider 调用
│   │   │   ├── _api_openai.py         #   OpenAI API 调用实现
│   │   │   ├── _call_openai.py        #   OpenAI API 单 Provider 调用
│   │   │   ├── _hallucination_filter.py #   LLM 幻觉过滤
│   │   │   ├── markdown.py           #   LLM 输出 Markdown 解析/格式化
│   │   │   ├── pricing.py            #   Token 计费与用量统计
│   │   │   ├── prompts.py            #   提示词模板库
│   │   │   ├── prompts_action.py     #   LLM 分析模块提示词构造（全局政经/智囊团复盘/体检/穿透）
│   │   │   ├── prompts_core.py       #   核心提示词模块（系统提示常量/缓存前缀/通用格式化）
│   │   │   ├── prompts_tables.py     #   提示词表格模块（持仓/穿透/场景分析格式化与摘要构造）
│   │   │   ├── session.py            #   LLM 会话管理（上下文窗口/历史）
│   │   │   ├── skeleton.py           #   LLM 内容骨架生成（结构化输出引导）
│   │   │   ├── _batch_mode.py        #   LLM 批量处理（缓存预检/并行调用/合并）
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
│   │   │   ├── excel_fund_deep_analysis.py  #   Excel 基金深度分析页签（基金深度分析：经理/重合度/集中度/风格/因子暴露）
│   │   │   ├── excel_llm_usage.py    #   Excel LLM 用量统计页签
│   │   │   ├── excel_writer.py       #   Excel 底层写入器（openpyxl 封装）
│   │   │   ├── _debate_utils.py      #   辩论模式检测工具函数（共享 html/excel）
│   │   │   ├── html_writer.py        #   HTML 报告主写入器
│   │   │   ├── html_builders.py      #   HTML 各区块构建器
│   │   │   ├── html_renderers.py     #   HTML 渲染管线
│   │   │   ├── html_jinja_env.py     #   Jinja2 模板环境配置
│   │   │   ├── html_save.py          #   HTML 保存/导出
│   │   │   ├── penetration.py        #   穿透持仓分析（嵌套基金）
│   │   │   ├── penetration_sheet.py  #   穿透分析 Excel 页签
│   │   │   ├── pipeline_data_builder.py # 管线数据上下文组装
│   │   │   ├── market_value.py       #   市值计算与盈亏分析
│   │   │   ├── market_value_sheet.py #   市值分析 Excel 页签
│   │   │   ├── category.py           #   持仓分类（股票/基金/债券/QDII 等）
│   │   │   ├── chart_data_builder.py #   Chart.js 6 图数据集预处理器
│   │   │   ├── fund_performance.py   #   基金业绩分析（排名/回撤/超额收益）
│   │   │   ├── fund_concentration.py #   基金持仓集中度分析
│   │   │   ├── fund_concentration_sheet.py # 集中度 Excel 页签
│   │   │   ├── fund_manager_analysis.py # 基金经理分析
│   │   │   ├── fund_manager_sheet.py #   基金经理 Excel 页签
│   │   │   ├── fund_overlap.py       #   基金持仓重叠分析
│   │   │   ├── fund_overlap_sheet.py #   重叠分析 Excel 页签
│   │   │   ├── fund_style_base.py       #   基金风格基础（常量/快照/PECity阈值）
│   │   │   ├── fund_style_classify.py   #   基金风格分类计算（push2→Tencent→兜底降级）
│   │   │   ├── fund_style_report.py     #   基金风格漂移检测与全基金分析入口
│   │   │   ├── fund_style_sheet.py   #   风格分析 Excel 页签
│   │   │   ├── factor_exposure_sheet.py #  因子暴露 Excel 页签（β/t/显著性/风格归属）
│   │   │   ├── correlation_sheet.py  #   持仓相关性矩阵 Excel 页签（热力格/配对明细）
│   │   │   ├── evolution_sheet.py    #   组合演进 Excel 页签（总市值/HHI/TOP 变迁）
│   │   │   ├── portfolio_history.py  #   组合历史净值走势分析
│   │   │   ├── _history_quality.py   #   历史走势数据质量校验
│   │   │   ├── history_snapshot.py   #   持仓快照管理（保留 60 天）
│   │   │   ├── _snapshot.py          #   快照与历史数据（持仓快照/环比差异/组合历史走势）
│   │   │   ├── news_correlation.py   #   新闻与持仓关联分析报告
│   │   │   ├── orchestrator.py       #   报告编排共享层（TUI/CLI 共用）
│   │   │   ├── _llm_news.py          #   LLM/新闻并行获取（线程池提交/收集/报告）
│   │   │   ├── _pipeline.py          #   报告管线编排（单管线/双管线调度）
│   │   │   ├── _report_generation.py #   报告生成实现（both/full 两种路径）
│   │   │   ├── privacy_notice.py     #   隐私提示模块（首次运行提示 + 报告脚注）
│   │   │   ├── summary.py            #   报告摘要生成
│   │   │   ├── summary_llm_usage.py  #   LLM 使用情况摘要
│   │   │   ├── data_status.py        #   数据质量状态（缺失/过期/降级标记）
│   │   │   ├── data_source_matrix.py #   数据源可用性矩阵（报告章节 #20）
│   │   │   ├── downsample.py         #   P1 服务端下采样（日频→周/月聚合）
│   │   │   ├── llm_content.py        #   LLM 分析结果写入报告（块级 HTML 分段 + 事实校验摘要分块着色）
│   │   │   ├── llm_module_info.py    #   LLM 模块信息构建（共享函数）
│   │   │   ├── progress.py           #   报告生成进度跟踪
│   │   │   ├── cli_progress.py         #   CLI 进度报告器（CliProgressReporter）
│   │   │   ├── whatif_sheet.py       #   调仓 What-if Excel 页签（摘要/分类/变动明细）
│   │   │   ├── whatif_writer.py      #   调仓 What-if 报告输出编排（Excel+HTML）
│   │   │   ├── whatif_operations.py  #   调仓 What-if 操作共享层（CLI/TUI 共用的业务链）
│   │   │   └── styles.py             #   Excel 样式定义
│   │   │
│   │   ├── tmpl/                     # HTML 报告模板
│   │   │   ├── report_template.html  #   Jinja2 HTML 报告主模板
│   │   │   ├── whatif_template.html  #   调仓 What-if 独立 HTML 页（双环图+变动明细）
│   │   │   └── partials/             #   章节级 partial（report_template.html 经 Jinja include 引入）
│   │   │       └── evolution_section.html  #   组合演进章节（多快照趋势，含专用图表数据段）
│   │   │
│   │   ├── core/                     # 核心基础设施
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── _phase_timeout.py     #   数据获取阶段超时管理
│   │   │   ├── _session_cache.py     #   会话缓存管理
│   │   │   ├── ansi_colors.py        #   ANSI 颜色常量（终端输出着色）
│   │   │   ├── check_sources.py      #   数据源健康检查命令处理器（CLI/报告共享）
│   │   │   ├── circuit_breaker.py    #   统一断路器网关（Provider + LLM 熔断状态查询）
│   │   │   ├── code_utils.py         #   证券代码/类型判定工具
│   │   │   ├── constants.py          #   全局常量/版本号
│   │   │   ├── http_client.py        #   HTTP 客户端（请求/重试/超时）
│   │   │   ├── logger.py             #   日志模块（文件+控制台，自动轮转）
│   │   │   ├── market_hours.py       #   交易时段判断（A股/港股/QDII）
│   │   │   ├── models.py             #   数据模型（持仓/行情/基金/新闻）
│   │   │   ├── perf.py               #   性能收集（PerfCollector 计时 + 数据源健康检查持久化）
│   │   │   ├── provider_registry.py  #   数据源注册中心（熔断器/会话缓存）
│   │   │   ├── reader.py             #   持仓 xlsx 文件读取
│   │   │   └── registry.py           #   中央注册表（模块/TTL/分组定义）
│   │   │
│   │   ├── cli/                      # CLI 命令行模式入口
│   │   │   ├── __init__.py           #   子包标记，re-export cli 符号
│   │   │   ├── __main__.py           #   python -m 入口
│   │   │   └── cli.py                #   argparse + 共享层路由（report/update/whatif 子命令）
│   │   │
│   │   ├── tui/                      # TUI 交互模式入口
│   │   │   ├── __init__.py           #   子包标记
│   │   │   ├── __main__.py           #   python -m 入口
│   │   │   ├── handlers_cache.py     #   缓存管理命令处理器
│   │   │   ├── handlers_config.py    #   配置管理命令处理器
│   │   │   ├── handlers_report.py    #   报告生成命令处理器
│   │   │   ├── handlers_whatif.py    #   调仓 What-if 模拟命令处理器（对比两份持仓生成独立报告）
│   │   │   ├── tui.py                #   主循环入口
│   │   │   ├── tui_handlers.py       #   键盘/事件处理
│   │   │   ├── tui_keys.py           #   终端键盘输入封装
│   │   │   └── tui_menu.py           #   菜单系统
│   │
│   ├── static/                       # 前端静态资产（本地 bundle + 调试页）
│   │   ├── chart.min.js              #   Chart.js v4.4.3 UMD（本地 bundle，205KB，离线自包含）
│   │   ├── chart-print.js            #   打印降级（beforeprint 快照 <img> / afterprint 恢复）
│   │   ├── chart-config.js           #   Chart.js 全局配置（主题色/动画关闭/DPR 限制）
│   │   ├── chart-export.js           #   单图导出 PNG 按钮（.chart-box 注入，2x 分辨率下载）
│   │   ├── chart-common.js           #   Chart.js 公共初始化 helper（trackChart/lineOptions/doughnutOptions，chart-init 与 What-if 页共用）
│   │   ├── chart-init.js             #   6 张图初始化（单图异常隔离 + degraded 虚线）
│   │   ├── toc.js                    #   左侧目录 TOC（折叠/展开 + IntersectionObserver 滚动高亮，离线自包含）
│   │   ├── theme.js                   #   主题切换（深/浅色 + localStorage 持久化 + Chart.js 重绘 + 打印浅色协调）
│   │   ├── test-chart.html           #   独立调试页：6 图渲染/降级/离线场景自检（Chart.js 升级验证载体）
│   │   └── README.md                 #   资产说明 + Chart.js 版本号记录（升级指引：替换引擎后先在此页验证）
│   │
│   └── test/                         # 测试套件
│       ├── __init__.py               #   包标记（空文件）
│       ├── conftest.py               #   pytest 全局配置 + 标记注册
│       ├── helpers.py                #   测试辅助工具
│       ├── data/                     #   测试数据集
│       │   └── hallucination/        #   幻觉测试数据集
│       │       ├── __init__.py       #       子包标记
│       │       └── datasets.py       #       幻觉评估标准持仓数据
│       ├── unit/                     #   单元测试（14 子目录）
│       │   ├── __init__.py           #   子包标记
│       │   ├── conftest.py           #   单元测试 conftest
│       │   ├── analysis/             #   分析计算单元测试
│       │   │   ├── __init__.py       #       子包标记
│       │   │   ├── test_bond_yield.py         #   无风险利率获取
│       │   │   ├── test_bond_yield_edge.py    #   无风险利率边缘场景
│       │   │   ├── test_circuit_breaker_wrapper.py #   断路器包装器测试
│       │   │   ├── test_fx_exposure.py        #   外汇敞口分析
│       │   │   ├── test_liquidity.py          #   流动性分析：场内品种变现天数
│       │   │   ├── test_liquidity_edge.py     #   流动性分析：边缘场景
│       │   │   ├── test_liquidity_otc.py      #   流动性分析：场外赎回天数
│       │   │   ├── test_liquidity_otc_edge.py #   流动性分析：场外边缘场景
│       │   │   ├── test_rebalance.py          #   再平衡信号计算
│       │   │   ├── test_rebalance_edge.py     #   再平衡边缘场景
│       │   │   ├── test_scenario_analysis.py       #   情景分析测试
│       │   │   ├── test_alignment_correction.py #   口径修正因子计算
│       │   │   ├── test_drawdown_warning.py   #   回撤历史分位预警
│       │   │   ├── test_drawdown_events.py    #   回撤事件识别
│       │   │   ├── test_drawdown_events_edge.py #  回撤事件识别边缘场景
│       │   │   ├── test_factor_exposure.py    #   因子暴露分析（OLS 回归/样本下限/停更剔除）
│       │   │   ├── test_correlation.py        #   持仓相关性矩阵计算（已知答案/矩阵布局/降级）
│       │   │   ├── test_correlation_edge.py   #   相关性矩阵边缘场景（NaN/Inf/日期缺口）
│       │   │   ├── test_portfolio_evolution.py #  组合演进聚合计算（多快照趋势/HHI/TOP 变迁）
│       │   │   ├── test_whatif.py             #   调仓 What-if 计算（变动识别/成本权重/HHI/降级）
│       │   │   ├── test_whatif_backtest.py    #   调仓 What-if 时序回测（天数折算/序列对齐/5 指标/降级）
│       │   │   └── test_whatif_backtest_edge.py #  时序回测边缘场景（未来日期/单 bar/首值 0/极端涨跌）
│       │   ├── config/              #   配置单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_config.py            #   配置管理核心测试
│       │   │   ├── test_config_atomic.py     #   配置原子操作测试
│       │   │   ├── test_config_atomic_edge.py #   配置原子操作边缘场景
│       │   │   ├── test_config_edge.py       #   配置管理边缘场景
│       │   │   ├── test_config_firstrun_edge.py #   首次运行配置边缘场景
│       │   │   ├── test_config_llm_multi.py      #   LLM 多配置测试
│       │   │   ├── test_config_llm_multi_edge.py #   LLM 多配置边缘场景
│       │   │   ├── test_config_validation.py     #   配置校验函数测试
│       │   │   └── test_local_state.py           #   机器本地状态读写与旧键迁移测试
│       │   ├── core/                #   核心模块单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_cache_core.py       #   缓存核心功能测试（含 TTL/目录/常量）
│       │   │   ├── test_cache_cleanup.py    #   缓存清理与统计测试
│       │   │   ├── test_cache_format.py     #   缓存格式测试
│       │   │   ├── test_cache_edge.py       #   缓存边缘场景测试
│       │   │   ├── test_code_utils.py       #   证券代码工具测试
│       │   │   ├── test_filesystem_edge.py  #   文件系统边缘场景
│       │   │   ├── test_http_client.py      #   HTTP 客户端测试
│       │   │   ├── test_market_hours.py     #   交易时段判断测试
│       │   │   ├── test_market_hours_edge.py #   交易时段边缘场景
│       │   │   ├── test_metrics.py          #   量化指标计算测试
│       │   │   ├── test_metrics_edge.py     #   量化指标边缘场景
│       │   │   ├── test_models.py           #   数据模型测试
│       │   │   ├── test_phase_timeout.py    #   阶段超时测试
│       │   │   ├── test_provider_registry.py #   数据源注册中心测试
│       │   │   ├── test_reader.py           #   持仓文件读取测试
│       │   │   ├── test_registry.py         #   中央注册表测试
│       │   │   ├── test_registry_edge.py    #   注册表边缘场景
│       │   ├── cache/               #   缓存单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_cache_io.py         #   缓存 IO 测试
│       │   │   ├── test_holdings_tracker.py #   持仓快照缓存追踪器
│       │   ├── fetcher/             #   数据获取单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_fetcher_api_edge.py  #   API 获取边缘场景
│       │   │   ├── test_batch.py            #   批量调度单元测试
│       │   │   ├── test_chain.py            #   数据链主链路测试
│       │   │   ├── test_chain_edge.py       #   数据链边缘场景
│       │   │   ├── test_fetcher.py          #   获取调度核心测试
│       │   │   ├── test_fetcher_index.py    #   指数行情获取测试
│       │   │   ├── test_fetcher_industry.py #   行业分类获取测试
│       │   │   ├── test_fetcher_price.py    #   行情价格获取测试
│       │   │   ├── test_fund.py             #   基金数据获取测试
│       │   │   └── test_fund_manager.py     #   基金经理数据测试
│       │   ├── handlers/            #   命令处理器单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_handlers_cache.py  #   缓存管理命令处理测试
│       │   │   ├── test_handlers_config.py #   命令处理器配置测试
│       │   │   ├── test_handlers_report.py #   报告生成命令处理测试
│       │   │   └── test_handlers_whatif.py #   调仓 What-if 命令处理测试
│       │   ├── llm/                 #   LLM 单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_llm_cache_multi.py         #   多 Provider 缓存测试
│       │   │   ├── test_circuit_breaker_edge.py  #   LLM 熔断器边缘场景
│       │   │   ├── test_circuit_breaker_recovery.py # 熔断恢复测试
│       │   │   ├── test_cost_tracker.py     #   Token 成本跟踪测试
│       │   │   ├── test_debate_conditional.py #   辩论条件触发测试
│       │   │   ├── test_debate_edge.py        #   辩论边缘场景
│       │   │   ├── test_debate_generators.py  #   辩论提示词生成测试
│       │   │   ├── test_debate_prompts.py     #   辩论提示词模板测试
│       │   │   ├── test_debate_qa.py          #   辩论 Q&A 测试
│       │   │   ├── test_debate_token_budget.py #   辩论 Token 预算测试
│       │   │   ├── test_fact_checker.py       #   事实校验器测试
│       │   │   ├── test_fingerprint.py        #   缓存指纹测试
│       │   │   ├── test_generators.py         #   全局提示词生成测试
│       │   │   ├── test_integration_multi.py  #   多 Provider 集成测试
│       │   │   ├── test_llm_analysis.py       #   LLM 分析测试
│       │   │   ├── test_llm_api.py            #   LLM API 主入口测试
│       │   │   ├── test_llm_api_base.py       #   LLM API 基类测试
│       │   │   ├── test_llm_api_base_calls.py #   LLM API 基类调用测试
│       │   │   ├── test_llm_api_base_edge.py  #   API 基类边缘场景
│       │   │   ├── test_llm_api_edge.py       #   API 边缘场景
│       │   │   ├── test_llm_api_multi.py      #   多 Provider API 测试
│       │   │   ├── test_llm_api_multi_edge.py #   多 Provider 边缘场景
│       │   │   ├── test_llm_content.py        #   LLM 内容写入测试
│       │   │   ├── test_llm_fallback.py       #   LLM 降级回退策略
│       │   │   ├── test_llm_generators.py     #   LLM generators 测试
│       │   │   ├── test_llm_placeholder.py    #   LLM 占位内容测试
│       │   │   ├── test_llm_placeholder_distinction_edge.py # 占位区分边缘场景
│       │   │   ├── test_llm_prompts.py        #   LLM 提示词测试
│       │   │   ├── test_llm_session.py        #   LLM 会话测试
│       │   │   ├── test_llm_utils.py          #   LLM 工具函数测试
│       │   │   ├── test_llm_prompt_builders.py     #   提示词构建器测试
│       │   │   ├── test_prompts_core.py       #   提示词核心测试
│       │   │   ├── test_llm_session_usage.py       #   会话用量管理测试
│       │   │   ├── test_skeleton.py           #   内容骨架生成测试
│       │   │   └── test_strategy.py           #   策略引擎测试
│       │   ├── news/                #   新闻单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_akshare_news.py       #   akshare 新闻源测试
│       │   │   ├── test_cls_news.py           #   财联社新闻源测试
│       │   │   ├── test_eastmoney_news.py     #   东方财富新闻源测试
│       │   │   ├── test_news_aggregator.py    #   新闻聚合器测试
│       │   │   ├── test_news_correlator.py    #   新闻关联分析测试
│       │   │   ├── test_news_keywords.py      #   新闻关键词测试
│       │   │   ├── test_news_sources.py       #   新闻源注册测试
│       │   │   ├── test_sina_news.py          #   新浪新闻源测试
│       │   │   └── test_wallstreetcn_news.py  #   华尔街见闻新闻源测试
│       │   ├── providers/           #   数据源提供商单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_akshare_extras.py     #   akshare 封装测试
│       │   │   ├── test_eastmoney.py          #   东方财富 API 测试
│       │   │   ├── test_eastmoney_industry.py #   东方财富行业分类测试
│       │   │   ├── test_sina.py               #   新浪财经 API 测试
│       │   │   ├── test_sina_edge.py          #   新浪财经边缘场景
│       │   │   ├── test_tencent.py            #   腾讯财经 API 测试
│       │   │   ├── test_tencent_edge.py       #   腾讯财经边缘场景
│       │   │   └── test_tiantian.py           #   天天基金 API 测试
│       │   ├── report/              #   报告单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_benchmark.py              #   业绩基准测试
│       │   │   ├── test_benchmark_edge.py         #   基准边缘场景
│       │   │   ├── test_category.py               #   持仓分类测试
│       │   │   ├── test_category_edge.py          #   分类边缘场景
│       │   │   ├── test_chart_data_builder.py     #   Chart.js 6 图数据集预处理器测试
│       │   │   ├── test_chart_data_builder_edge.py #   图表数据预处理器边缘场景（行业归"其他"等）
│       │   │   ├── test_classification_utils.py   #   分类工具测试
│       │   │   ├── test_data_integrity.py         #   数据完整性测试
│       │   │   ├── test_data_quality_edge.py      #   数据质量边缘场景
│       │   │   ├── test_data_source_matrix.py     #   数据源可用性矩阵测试
│       │   │   ├── test_data_status.py            #   数据状态测试
│       │   │   ├── test_downsample.py             #   P1 服务端下采样测试（§4.9）
│       │   │   ├── test_excel_fund_deep_analysis.py  #   Excel 基金深度分析页签测试
│       │   │   ├── test_excel_format_edge.py      #   Excel 格式边缘场景
│       │   │   ├── test_excel_generator.py        #   Excel 生成测试
│       │   │   ├── test_excel_generator_edge.py   #   Excel 生成边缘场景
│       │   │   ├── test_excel_report_structure.py #   Excel 报告结构测试
│       │   │   ├── test_excel_roundtrip.py        #   Excel 写入读取回环测试
│       │   │   ├── test_excel_writer.py           #   Excel 写入器测试
│       │   │   ├── test_feature_interactive.py    #   交互图表 Feature Flag 管线测试
│       │   │   ├── test_fund_deep_analysis_sheet_edge.py # 基金深度分析页签边缘场景
│       │   │   ├── test_fund_concentration.py     #   基金集中度测试
│       │   │   ├── test_fund_manager_analysis.py  #   基金经理分析测试
│       │   │   ├── test_fund_manager_sheet.py     #   基金经理页签测试
│       │   │   ├── test_fund_overlap.py           #   基金重叠分析测试
│       │   │   ├── test_fund_performance.py       #   基金业绩测试
│       │   │   ├── test_fund_style_analysis.py    #   基金风格测试
│       │   │   ├── test_correlation_html.py       #   持仓相关性章节 HTML 呈现
│       │   │   ├── test_correlation_sheet.py      #   持仓相关性矩阵 Excel 页签呈现
│       │   │   ├── test_evolution_html.py         #   组合演进章节 HTML 呈现（图表+图下说明）
│       │   │   ├── test_evolution_sheet.py        #   组合演进 Excel 页签呈现
│       │   │   ├── test_whatif_html.py            #   调仓 What-if 独立 HTML 页呈现
│       │   │   ├── test_whatif_sheet.py           #   调仓 What-if Excel 三页签呈现
│       │   │   ├── test_whatif_operations.py      #   调仓 What-if 操作共享层测试
│       │   │   ├── test_whatif_writer.py          #   调仓 What-if 报告输出（固定名+日期归档+清理）
│       │   │   ├── test_drawdown_html_excel.py    #   回撤明细 HTML/Excel 呈现
│       │   │   ├── test_html_builders.py          #   HTML 构建器测试
│       │   │   ├── test_html_builders_edge.py     #   HTML 构建器边缘场景
│       │   │   ├── test_html_report_structure.py  #   HTML 报告结构测试
│       │   │   ├── test_html_report_structure_edge.py # HTML 结构边缘场景
│       │   │   ├── test_html_template.py          #   HTML 模板测试
│       │   │   ├── test_theme_js.py               #   暗色模式 theme.js 静态断言
│       │   │   ├── test_html_writer.py            #   HTML 写入器测试
│       │   │   ├── test_html_writer_edge.py       #   HTML 写入器边缘场景
│       │   │   ├── test_market_value.py           #   市值计算测试
│       │   │   ├── test_market_value_edge.py      #   市值边缘场景
│       │   │   ├── test_market_value_sheet.py     #   市值页签测试
│       │   │   ├── test_market_value_strategy_edge.py # 市值策略边缘场景
│       │   │   ├── test_news_correlation.py       #   新闻关联报告测试
│       │   │   ├── test_news_degradation_edge.py  #   新闻降级边缘场景
│       │   │   ├── test_penetration.py            #   穿透分析测试
│       │   │   ├── test_penetration_edge.py       #   穿透分析边缘场景
│       │   │   ├── test_pipeline_utils.py          #   管线工具函数测试
│       │   │   ├── test_portfolio_history.py      #   组合历史走势测试
│       │   │   ├── test_progress.py               #   进度跟踪测试
│       │   │   ├── test_qdii_timezone_edge.py     #   QDII 时区边缘场景
│       │   │   ├── test_security_edge.py          #   证券边缘场景
│       │   │   ├── test_orchestrator.py           #   报告编排器单元测试
│       │   │   └── test_summary.py                #   摘要生成测试
│       │   ├── scripts/              #   工程脚本单元测试（历史痕迹检查工具自检/豁免/补强模式）
│       │   │   ├── __init__.py       #       子包标记
│       │   │   └── test_trace_check_scripts.py  #   check-code/doc-traces 工具自身豁免+时序模式检出/豁免回归
│       │   ├── startup/              #   首次运行引导单元测试
│       │   │   ├── __init__.py       #       子包标记
│       │   │   └── test_startup_wizard.py  #   首次运行引导向导测试
│       │   ├── cli/                 #   CLI 命令行模式单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_cli.py               #   CLI 命令行模式单元测试
│       │   │   └── test_cli_edge.py          #   CLI 边缘场景测试
│       │   ├── ui/                  #   UI 单元测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_log_sanitize.py     #   日志清洗测试
│       │   │   ├── test_tui.py              #   TUI 交互测试
│       │   │   ├── test_tui_edge.py         #   TUI 边缘场景
│       │   │   ├── test_tui_handlers.py     #   TUI 事件处理测试
│       │   │   └── test_tui_menu.py         #   TUI 菜单测试
│       ├── integration/              #   集成测试（契约/隔离/流水线）
│       │   ├── __init__.py           #   子包标记
│       │   ├── test_debate_pipeline.py    #   辩论多轮对话管线集成测试
│       │   ├── test_cli_integration.py    #   CLI 命令行模式集成测试
│       │   ├── test_integration_coverage.py # 集成测试覆盖率校验
│       │   └── test_news_pipeline_edge.py   # 新闻管线边缘场景集成测试
│       ├── scenario/                 #   场景测试（basic/datetime/llm/perf/resilience/security 六子组）
│       │   ├── __init__.py           #   子包标记
│       │   ├── basic/               #   基本面场景测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_scenario_basic_flows.py    #   基础业务链路场景测试
│       │   │   ├── test_pipeline_metrics_injection.py # 管线指标注入测试
│       │   │   ├── test_pipeline_smoke.py          #   管线冒烟测试
│       │   │   ├── test_scenario_holdings_quality.py # 持仓质量场景测试
│       │   │   ├── test_scenario_operational_behavior.py # 操作行为场景测试
│       │   │   ├── test_scenario_section_order.py  #   报告章节顺序场景测试
│       │   │   ├── test_scenario_penetration_basic.py    #   穿透分析基础场景
│       │   │   ├── test_scenario_penetration_advanced.py #   穿透分析高级场景
│       │   │   ├── test_scenario_penetration_mixed.py   #   穿透分析混合场景
│       │   │   ├── test_scenario_penetration_edge.py    #   穿透分析边缘场景
│       │   │   ├── test_scenario_special_securities.py # 特殊证券场景测试
│       │   │   └── test_pipeline_factor_exposure.py     #   因子暴露管线场景测试
│       │   ├── datetime/            #   日期时间场景测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   └── test_datetime_scenarios.py #   日期时间场景测试
│       │   ├── llm/                 #   LLM 场景测试（12 测试文件）
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_llm_mixed_cache.py      #   混合缓存+真实调用
│       │   │   ├── test_llm_all_fail.py         #   全部失败（5 种原因）
│       │   │   ├── test_llm_extended_thinking.py #   Extended Thinking 混合
│       │   │   ├── test_llm_disabled.py         #   LLM 不启用
│       │   │   ├── test_llm_disabled_cache.py   #   禁用+缓存混合
│       │   │   ├── test_llm_network_error.py    #   断网下 LLM 降级
│       │   │   ├── test_llm_partial_cache.py    #   部分缓存超期
│       │   │   ├── test_llm_empty_holdings.py   #   空持仓/全缓存
│       │   │   ├── test_llm_output_consistency.py #  输出格式一致性
│       │   │   ├── test_llm_non_trading_day.py  #   非交易日 LLM 行为
│       │   │   ├── test_llm_multi_account.py    #   多账户多轮交互
│       │   │   └── test_llm_hallucination.py    #   LLM 幻觉率采样场景测试
│       │   ├── perf/                #   性能场景测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   └── test_e2e_perf.py #   端到端性能场景测试
│       │   ├── resilience/          #   弹性场景测试
│       │   │   ├── __init__.py      #       子包标记
│       │   │   ├── test_chain_resilience.py   #   数据链弹性场景测试
│       │   │   ├── test_scenario_resilience_flows.py # 弹性业务链路场景测试
│       │   │   └── test_scenario_extreme.py      #   极端场景测试
│       │   └── security/            #   安全场景测试
│       │       ├── __init__.py      #       子包标记
│       │       └── test_security.py #   安全场景测试
│
├── data/                             # 运行时数据
│   ├── holdings/                     #   持仓 xlsx 文件（用户放置）
│   ├── knowledge/                    #   知识数据（fund_benchmarks.json / sector_keywords.json，随仓库发布）
│   ├── calibration/                  #   校准数据（dedup_anchors.jsonl，自动生成）
│   ├── cache/                        #   API 响应缓存（自动生成，JSON/GZ）
│   ├── config/                       #   配置文件（config.json / features.json / llm_key.json / llm_settings.json / llm_providers.json）
│   ├── state/                        #   运行时状态文件（.degradation_state.json / circuit_breaker.json / local_state.json 等，自动生成，机器本地不随仓库同步）
│   └── history/snapshots/            #   持仓快照（自动生成，保留 60 天）
│
├── reports/                          # 报告输出（最新版 + 按日期归档）
├── logs/                             # 程序日志（app.log，自动轮转）
├── test-reports/                     # 测试报告（自动生成，按 mode 分组）
├── .githooks/                        # git hooks（任务编号一致性 pre-commit，跨机器需 install-hooks.sh 激活）
│   ├── pre-commit                    #   pre-commit hook（提交涉及 plan.md/review-findings.md 时校验编号）
│   └── install-hooks.sh              #   hooks 激活脚本（clone 后运行一次启用 core.hooksPath）
├── .github/                         # GitHub 配置
│   └── workflows/                      #   CI/CD 配置文件
│       └── ci.yml                   #   CI/CD 流水线（P0/P1/P2 三级门禁）
├── pytest.ini                       # pytest 全局配置
├── reason.bat                       # Reasonix AI code editor 启动（`reasonix code`）
├── scripts/                          # 启动脚本 + 测试工具
│   ├── launch.ps1                   #   Windows PowerShell 启动脚本
│   ├── launch.sh                    #   Linux/macOS 启动脚本
│   ├── test_runner.py               #   测试驱动（pytest 模式封装）
│   ├── check-test-markers.py        #   测试标记合规检查
│   ├── check-task-numbering.py      #   任务编号（plan-/rf-）全局一致性检查
│   ├── check-task-numbering-hook.py #   Claude Code PostToolUse hook（编辑编号文档后自动校验）
│   ├── install-claude-hook.py       #   Claude Code hook 安装/卸载（跨机器接线）
│   ├── check-version-consistency.py #   版本号一致性检查
│   ├── calibrate-dedup-threshold.py #   新闻去重阈值校准
│   ├── collect-test-coverage.py     #   测试覆盖计数收集（pytest --collect-only 快照，供 test-coverage.md 更新）
│   ├── check-code-traces.py         #   代码注释历史痕迹检查
│   ├── check-doc-traces.py          #   文档历史痕迹检查
│   ├── llm_hallucination_sampler.py  #   LLM 幻觉率采样测试（10组标准持仓+事实校验器验证）
│   ├── perf_report.py               #   端到端性能基准测试（独立脚本，mock 外部数据源）
│   ├── perf_view.py                 #   性能历史趋势查看（读取 perf_history.jsonl -> Markdown 对比表格）
│   ├── probe-csi-factor-indices.py  #   CSI 风格指数可用性探测（因子暴露分析前置决策闸门）
│   ├── diagnose_gemini_proxy.py     #   Gemini API 代理连通性诊断
│   └── extract-test-failures.py      #   pytest-html 报告失败用例提取
├── docs-stm/                         # 项目文档
│   ├── manuals/                      #   用户手册分册
│   │   ├── datasource.md             #     数据源一览
│   │   ├── datasource-reliability.md #     数据源可靠性文档（运维视角）
│   │   ├── faq.md                    #     常见问题解答
│   │   ├── how-to-config-llm.md      #     LLM 配置指南
│   │   ├── how-to-config.md          #     配置说明
│   │   ├── how-to-menu.md            #     菜单操作指南
│   │   ├── how-to-start.md           #     快速上手
│   │   ├── how-to-schedule.md       #     定时任务配置指南
│   │   ├── how-to-test-my-code.md    #     测试编写指南
│   │   ├── scripts-reference.md      #     辅助脚本参考（全）
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
│   ├── plan/                         #   中间设计文件（当前迭代中，仅未完成项）
│   │   └── plan-web-ui.md              #     轻量 Web UI 计划（日志可视化 / HTML 暗色模式）
│   ├── archive/                      #   历史归档
│   │   ├── porting-to-rust-vs-java-analysis.md  #   Rust/Java 移植技术分析
│   │   ├── v0.1.x/                            # v0.1.x 版本归档
│   │   │   ├── archived_changelog.0.1.x.md        # 变更日志归档 v0.1.x
│   │   │   ├── archived_plan.0.1.x.md             # 实现计划归档 v0.1.x
│   │   │   └── archived_review-findings.0.1.x.md  # 自审记录归档 v0.1.x
│   │   ├── v0.2.x/                            # v0.2.x 版本归档
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
│   │   ├── v0.3.x/                            # v0.3.x 版本归档
│   │   │   ├── archived_changelog.0.3.x.md        # 变更日志归档 v0.3.x
│   │   │   ├── archived_plan.0.3.x.md             # 实现计划归档 v0.3.x
│   │   │   ├── archived_review-findings.0.3.x.md  # 自审记录归档 v0.3.x
│   │   │   ├── refactor-cache-engine/             # 缓存引擎重构
│   │   │   │   └── cache-refactor-plan.md         # 缓存引擎重构计划
│   │   │   ├── refactor-excel-generator/          # Excel 生成器重构
│   │   │   │   └── excel-generator-split-plan.md # Excel 生成器拆分计划
│   │   │   ├── refactor-html_writer/              # HTML 写入器重构
│   │   │   │   └── r178_html_writer_split.md      # HTML 写入器拆分
│   │   │   ├── refactor-llm_split_design/         # LLM 拆分重构
│   │   │   │   └── r198_llm_split_design.md       # LLM 拆分设计
│   │   │   ├── refactor-market_value_split_design/ # 市值拆分重构
│   │   │   │   └── r197_market_value_split.md     # 市值拆分设计
│   │   │   ├── refactor-summary-llm-usage/        # LLM 用量摘要重构
│   │   │   │   └── summary-llm-usage-split-plan.md # LLM 用量摘要拆分计划
│   │   │   └── test-verify-mode-optimization/     # 测试verify 模式运行优化
│   │   │       └── r200_verify_mode_optimization.md # 测试verify 模式运行优化
│   │   ├── v0.4.x/                            # v0.4.x 版本归档
│   │   │   ├── archived_changelog.0.4.x.md        # 变更日志归档 v0.4.x
│   │   │   ├── archived_plan.0.4.x.md             # 实现计划归档 v0.4.x
│   │   │   ├── archived_review-findings.0.4.x.md  # 自审记录归档 v0.4.x
│   │   │   ├── portfolio-history-comparison/      # 组合历史对比
│   │   │   │   ├── F-portfolio-history-comparison.md        # F 迭代计划与技术设计
│   │   │   │   └── html-report-chart-native-canvas-fallback-plan.md # HTML Canvas 渲染修复
│   │   │   └── test-add-config-edge-testcase/     # 边缘测试配置
│   │   │       └── y5-edge-test-config-env.md     # 边缘测试配置环境
│   │   ├── v0.5.x/                            # v0.5.x 版本归档
│   │   │   ├── archived_changelog.0.5.x.md        # 变更日志归档 v0.5.x
│   │   │   ├── archived_plan.0.5.x.md             # 实现计划归档 v0.5.x
│   │   │   ├── archived_review-findings.0.5.x.md  # 自审记录归档 v0.5.x
│   │   │   ├── portfolio-benchmark-comparison/    # I 迭代基准指数对比归档
│   │   │   │   ├── I-comparative-benchmark-design.md    # I 迭代基准对比设计
│   │   │   │   ├── I-comparative-benchmark-iteration.md # I 迭代基准对比迭代计划
│   │   │   │   └── plan-iter-8-excel-benchmark-columns.md # I 迭代 Excel 基准指数列
│   │   │   └── report-board-visibility-configable/ # 看板可见性配置
│   │   │       └── g-board-visibility-iteration-plan.md # 看板可见性配置迭代计划
│   │   ├── v0.6.x/                            # v0.6.x 版本归档
│   │   │   ├── archived_changelog.0.6.x.md        # 变更日志归档 v0.6.x
│   │   │   ├── archived_plan.0.6.x.md             # 实现计划归档 v0.6.x
│   │   │   ├── archived_review-findings.0.6.x.md  # 自审记录归档 v0.6.x
│   │   │   ├── llm-multi-provider/                # 多 LLM Provider 链式服务归档
│   │   │   │   ├── llm-multi-provider-design.md       # 多 LLM Provider 链式服务技术设计
│   │   │   │   └── llm-multi-provider-iteration-plan.md # 多 LLM Provider 链式服务迭代计划
│   │   │   └── cli-mode/                          # CLI 命令行模式归档
│   │   │       ├── cli-mode-iteration-plan.md     # CLI 迭代计划
│   │   │       └── cli-mode-technical-design.md   # CLI 技术设计
│   │   ├── v0.7.x/                            # v0.7.x 版本归档
│   │   │   ├── archived_changelog.0.7.x.md        # 变更日志归档 v0.7.x
│   │   │   ├── archived_plan.0.7.x.md             # 实现计划归档 v0.7.x
│   │   │   ├── archived_review-findings.0.7.x.md  # 自审记录归档 v0.7.x
│   │   │   └── better-investment-advice/           # 投资建议改进分析讨论（已归档）
│   │   │       ├── discussion-better-investment-advice.md             # 可行性调研：6 层改进方向与实施路径
│   │   │       ├── better-investment-task.md                          # 最小粒度工作任务分解（86 任务）
│   │   │       ├── data-channels-schema.md                            # 数据通道 Schema 文档
│   │   │       ├── data-source-stability-test-report.md               # 数据源稳定性专项测试报告
│   │   │       ├── better-investment-performance-test-report.md        # 端到端性能基准测试报告
│   │   │       ├── task91-enhanced-llm-strategy.md                    # 增强型 LLM 策略引擎设计
│   │   │       ├── r1-insert-feasibility-audit-into-discussion.py      # R1 数据源可行性审查插入脚本（最终版）
│   │   │       ├── debug-find-insert-anchor_r1.py                     # R1 锚点定位合并调试脚本
│   │   │       ├── llm-hallucination-report_expert-review.md           # LLM 幻觉率采样报告（expert_review 模块）
│   │   │       ├── llm-hallucination-prompts_expert-review.md          # 幻觉采样完整 Prompt 构造（Dry-Run）
│   │   │       └── llm-hallucination-sample-output_expert-review.txt   # 幻觉采样 LLM 原始输出样本
│   │   ├── v0.8.x/                           # v0.8.x 版本归档
│   │   │   ├── archived_changelog.0.8.x.md    # 变更日志归档 v0.8.x
│   │   │   ├── archived_plan.0.8.x.md         # 实现计划归档 v0.8.x
│   │   │   ├── archived_review-findings.0.8.x.md # 自审记录归档 v0.8.x
│   │   │   ├── tiantian-split/               #   tiantian.py 大文件拆分记录
│   │   │   │   └── tiantian-split.md          #     tiantian.py 拆分记录
│   │   │   ├── fundstyle-split/               #   fund_style_analysis.py 大文件拆分记录
│   │   │   │   └── fundstyle-split.md         #     fund_style_analysis.py 拆分记录
│   │   │   ├── datasource-matrix/             #   数据源可用性矩阵实现记录
│   │   │   │   └── datasource-matrix.md       #     数据源可用性矩阵实现记录
│   │   │   ├── datasource-reliability-documentation/   #   数据源可靠性文档
│   │   │   │   └── datasource-reliability-documentation.md # 数据源可靠性文档
│   │   │   ├── perf-benchmark/               #   性能基准体系（自动计时/回归检测/趋势工具）
│   │   │   │   ├── perf-completion-summary.md #     性能基准体系归档摘要
│   │   │   │   └── perf-design-and-verification.md # 性能基准体系设计方案
│   │   │   ├── batch-parallel/             #   批量并行调度重构（BatchDispatcher + 线程池配置）
│   │   │   │   ├── batch-parallel-design.md #      批量并行调度技术设计
│   │   │   │   └── batch-parallel-iteration-plan.md # 批量并行调度迭代计划
│   │   ├── v0.9.x/                           # v0.9.x 版本归档（changelog/plan/review-findings + 设计文档）
│   │   │   ├── archived_plan.0.9.x.md         # 实现计划归档 v0.9.x（设计文档索引）
│   │   │   ├── archived_changelog.0.9.x.md     # 变更日志归档 v0.9.x
│   │   │   ├── archived_review-findings.0.9.x.md # 自审记录归档 v0.9.x
│   │   │   ├── abandoned-design/               #   已放弃设计决策归档区（plan-4 业绩归因）
│   │   │   │   └── plan-4-brinson-attribution-abandoned.md # plan-4 业绩归因（Brinson）放弃设计
│   │   │   ├── chartjs-upgrade/               #   交互式 HTML 报告升级设计（8 迭代）
│   │   │   │   ├── plan-chartjs-report-upgrade.md   # Chart.js 升级实施方案
│   │   │   │   ├── plan-chartjs-risk-analysis.md    # Chart.js 升级风险/收益/架构分析
│   │   │   │   └── iter7-verification-checklist.md # Iter 7 浏览器人工验证清单
│   │   │   ├── factor-exposure/                 #   因子暴露分析设计
│   │   │   │   └── plan-factor-exposure.md      #     因子暴露分析设计
│   │   │   ├── correlation-drawdown/            #   相关性矩阵 + 回撤/净值设计与实施
│   │   │   │   ├── plan-correlation-drawdown.md #     分析功能基础增强设计
│   │   │   │   └── plan-correlation-drawdown-implementation.md # 实施总纲
│   │   │   ├── first-run-wizard/                #   首次运行引导设计与实施
│   │   │   │   ├── plan-first-run-wizard.md     #     首次运行引导设计
│   │   │   │   └── plan-first-run-wizard-implementation.md # 实施细节
│   │   │   ├── whatif-simulation/               #   调仓 What-if 模拟设计
│   │   │   │   └── plan-whatif-simulation.md    #     调仓 What-if 模拟设计
│   │   │   ├── whatif-backtest/                 #   调仓 What-if 指定生效日时序回测设计
│   │   │   │   └── plan-whatif-backtest.md      #     调仓 What-if 指定生效日时序回测设计
│   │   │   ├── portfolio-evolution/             #   多快照趋势追踪/组合演进设计
│   │   │   │   └── plan-portfolio-evolution.md  #     多快照趋势追踪设计
│   │   │   ├── html-dark-mode/                  #   HTML 暗色模式实施归档
│   │   │   │   ├── dark-mode-implementation.md  #     plan-11 暗色模式实施记录
│   │   │   │   └── plan-11-dark-mode-plan.md    #     plan-11 暗色模式实施计划
│   │   │   ├── fix-deepseek-thinking/           #   DeepSeek thinking 思考耗尽修复设计
│   │   │   │   └── plan-fix-deepseek-thinking-exhaustion.md # 思考耗尽修复方案
│   │   │   └── qa-concentration-chart-optimization/ # 集中度问答 + 穿透柱状图优化修复设计
│   │   │       └── plan-fix-qa-concentration-and-chart-optimization.md # 集中度问答 + 柱状图优化修复
│   └── tmp/                          #   临时文件（git 忽略，不展开）
│
├── CLAUDE.md                         # AI 编程助手指引
├── README.md                         # 用户文档总入口
├── pyproject.toml                    # Python 项目元数据
├── requirements.txt                  # Python 依赖清单
└── .gitignore                        # Git 忽略规则
```

> 注意：目录树为主层级结构，测试文件数和文件行数随版本迭代变化。
