# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.2.27] - 2026-06-29

### Added
- **节假日感知的交易日判定** — `get_last_trading_day()` / `get_prev_trading_day()` 引入
  akshare 交易日历，正确识别端午、中秋、国庆等非交易日，替代简易周度计算

### Changed
- **`get_last_trading_day()` 重写** — 使用 akshare 交易日历 + 日间 9:30 盘前判断，
  同时考虑节假日和交易时间。aksahre 不可用时自动回退简易周度逻辑
- **`get_prev_trading_day()` 重写** — 同样使用交易日历向前查找，正确处理节假日跳越
- **`_get_trading_calendar()`** — 新增模块级缓存函数（7 天 TTL），避免每次重复请求

### Tests
- 新增 3 条节假日测试用例（端午假期盘前/盘中/节后）
- 所有交易日相关测试改用 mock 日历，不依赖网络，结果确定

## [0.2.26] - 2026-06-29

### Fixed
- **盘前运行报告时「所属交易日」错误显示当天** — `get_last_trading_day()` 对周一到周五
  一律返回当天，未考虑开盘时间。周一至五在 9:30 之前（盘前）自动退回上一交易日。
  修复后：2026-06-29 凌晨 02:35 运行 → 正确显示 2026-06-26（上周五）。

## [0.2.25] - 2026-06-29

### Fixed
- **`httpx.RequestError`（网络层错误）未重试** — `_call_llm_with_retry()` 中 `RequestError`
  之前直接返回，不触发任何重试。瞬态网络波动（DNS 抖动、SSL 握手失败、连接重置）
  可导致所有 LLM 调用同时失败。现已增加与 `TimeoutException` 一致的重试逻辑，
  最大重试次数内以指数退避（1s/3s）自动恢复。

## [0.2.24] - 2026-06-29

### Added
- **Extended Thinking 模型兼容性降级** — `_supports_extended_thinking()` 检查模型是否
  在已知支持名单（`claude-sonnet-4*` / `claude-opus-4*`）中，不匹配时自动跳过 `thinking`
  payload 注入并记录 `WARNING` 日志，兼容 `deepseek-v4-flash` 等第三方模型
- **`_supports_extended_thinking()` 单元测试** — 13 条用例覆盖支持/不支持/空模型等场景
- **`_call_claude()` thinking 降级自动化测试** — 5 条用例覆盖注入、跳过、自动兜底、配置缺省等场景

### Changed
- **`thinking_enabled_expert` 默认改为 `true`** — 智囊团深度复盘默认启用 Extended Thinking，
  用户开箱即用无需额外配置
- **`llm_settings.json` 同步** — 新增 6 个 thinking 配置项 + 3 个 `model_*` 缺失项，
  `thinking_enabled_expert: true` 确保与代码默认一致
- **`cache_enabled_news` 重命名为 `cache_enabled_news_correlation`** — 统一命名规范，
  与 `max_tokens_news_correlation` 等现有后缀保持一致

### Removed
- **`cache_ttl.llm` 死配置** — `config.json` 中废弃的泛用 LLM 缓存 TTL 键，
  无代码读取，已删除

## [0.2.23] - 2026-06-29

### Added
- **Extended Thinking 状态标识** — HTML 报告中，Token 用量行末尾追加 `| Extended Thinking`；
  Excel 报告中，模型名称行下方追加 `Extended Thinking 已开启` 行（灰斜体 9pt），
  便于快速确认当前报告各 LLM 章节是否启用深度推理

### Changed
- **`_generate_llm_content()` 新增 `thinking_enabled` 参数** — 由各模块调用方（`generate_global_macro`、
  `generate_expert_review`）从 `llm_settings.json` 读取状态后传入
- **`write_llm_sheets()` 新增 `thinking` 元组参数** — 透传两个 LLM 页签的开启状态至 `_write_content_sheet()`
- **`tui_handlers.py`** — 从配置读取 `thinking_enabled_macro` / `thinking_enabled_expert` 并传入写表逻辑

### Fixed
- **模型名称标识行后缺少 `row += 1`** — 修复 Extended Thinking 行可能覆盖模型名称的边界问题

## [0.2.22] - 2026-06-29

### Added
- **Extended Thinking 支持** — `_call_claude()` 根据 `llm_settings.json` 的 `thinking_enabled_{模块}` 配置注入 `thinking` payload，让 ≥ Claude Sonnet 4 的模型在回答前进行深度推理，提升复杂分析质量
- **`llm_settings.json` 新增 6 个 Extended Thinking 配置项** — `thinking_enabled_macro` / `thinking_enabled_expert` / `thinking_enabled_news_correlation` 及其对应的 `thinking_budget_*` 预算

### Changed
- **`_call_claude()` 签名扩展** — 新增 `llm_config` 参数，用于读取 thinking 配置；开启 thinking 时自动跳过 `temperature`（API 不兼容）

### Docs
- README.md：新增 Extended Thinking 章节，详细说明各场景收益对比和配置方式；llm_settings.json 示例值同步新增 thinking 字段；推荐参数表新增 6 个 thinking 配置项；删除已移除的 `cache_ttl.llm` 泛用键文档

## [0.2.21] - 2026-06-29

### Changed
- **`generate_global_macro()` / `generate_expert_review()` 重构** — 提取 `_generate_llm_content()` 共享骨架函数，消除两函数间约 60 行重复代码
- **新闻 LLM 缓存指纹优化** — 改用 (序号, 标题前 80 字) 摘要计算指纹，避免正文微小差异导致 TTL 内缓存频繁失效

### Fixed
- **LLM 缓存空串假命中** — `_generate_llm_content()` 缓存检查 `is not None` → 真值检查，防止空字符串误判为缓存命中
- **模型名 footer 空白** — 当 model 参数和配置均为空时增加 `"未指定"` 兜底

### Removed
- **`_get_http_pool()` 死代码** — `_thread_local` 懒加载 httpx.Client 回退路径已无用，安全删除
- **`config.json` 无用 `llm` 泛用 TTL 键** — 未使用的 `cache_ttl.llm` 及 `cache.py` 对应前缀映射已删除
- **`generate_all_llm()` 冗余缓存预检** — 预检仅在双方都命中时省线程创建开销，却被各 generate 函数内部自检覆盖，移除

### Added
- **强制刷新 LLM 缓存** — 菜单 [L] 增加交互询问 `是否强制重新生成 LLM 内容？(y/N)`，确认后跳缓存强制生成
- **配置模型路由显示** — `_show_llm_config_status()` 新增逐模块模型名显示行

### Docs
- plan.md：补充下一步迭代计划（A~E 五个增强方向），标注难度和价值

## [0.2.20] - 2026-06-29

### Changed
- **缓存 TTL 配置去冗余** — 从 `llm_settings.json` 移除 `cache_ttl_macro` / `cache_ttl_expert` / `cache_ttl_news`，统一归入 `config.json` → `cache_ttl`，消除两份文件参数冲突风险
- **config.json cache_ttl 键名规范化** — `llm_macro` → `llm_global_macro`、`llm_expert` → `llm_expert_review`、`llm_news` → `llm_news_corr`，与缓存文件命名前缀保持一致

### Fixed
- **菜单 [1] 缓存清除不完整** — 补上遗漏的 `profit_forecast_*` 和 `sector_flow_*` 清除与主动刷新（含进程级 memo 缓存失效），菜单 [1] 现在会主动重新获取这两类数据

### Removed
- **`llm_settings.json` 中的 cache_ttl 字段** — 原 `cache_ttl_macro` / `cache_ttl_expert` / `cache_ttl_news` 已迁移至 `config.json` → `cache_ttl`，llm_settings.json 仅保留 LLM 运行参数

### Docs
- README.md：补充逐章节模型路由（Per-Section Model Routing）文档、参数表中新增 `model_macro` / `model_expert` / `model_news_correlation`
- requirements.md：LLM 章节补充模型路由说明
- README.md / requirements.md：所有 cache_ttl 键名同步至新命名

## [0.2.19] - 2026-06-28

### Changed
- **LLM 调用代码重构** — 提取 `_call_llm_with_retry()` 共享函数，消除 `_call_claude` / `_call_openai` 中约 100 行重复的重试/超时/错误处理代码
- **新闻关联分析分批并行化** — `enhance_news_correlation()` 分批处理从串行 `for` 循环改为 `ThreadPoolExecutor(max_workers=3)` 并行，6 批并行处理后墙钟时间降低约 60%（30s → ~10s）

### Added
- **模型路由** — `llm_settings.json` 新增 `model_macro` / `model_expert` / `model_news_correlation` 配置项，per-module 独立模型选择，未配置时沿用 `llm_key.json` 的全局 `model` 字段
- **Prompt Caching** — Claude API system prompt 使用数组格式 + `cache_control` 支持 Anthropic Prompt Caching，批量新闻关联分析时 5 分钟内同 system prompt 节省约 50% 输入 token 费用

### Fixed
- **`enhance_news_correlation` id() 映射** — top_news → news_data 原始位置映射从 `id()`（对象身份）改为 `enumerate` 保留原始索引，消除对象身份漂移的理论风险

### Removed
- **`_fingerprint` 假注释** — 从 `llm_settings.json` 移除 JSON 中用作注释的 `_fingerprint` 字段（无代码读取，纯误导性装饰）

### Docs
- requirements.md：模型路由新配置项说明
- changelog.md：本版本记录

## [0.2.18] - 2026-06-28

### Added
- **机构盈利预测集成** — 调用 akshare `stock_profit_forecast_em()` 获取全量股票机构的研报覆盖、预测 EPS、评级分布
  - 穿透 TOP10（模块 4）新增「预测EPS(2025E)」列
  - 基金业绩分析（模块 5）新增「机构覆盖」列，显示研报家数和预测 EPS
  - 缓存策略：指数指纹 + 1 天 TTL 双因子失效
- **行业资金流向集成** — 调用 akshare `stock_sector_fund_flow_rank()` 获取今日行业资金流向排名
  - LLM 宏观分析 Prompt 注入前 5 个行业资金流向数据（名称、涨跌幅、主力净流入）
  - 缓存策略：指数指纹 + 15 分钟 TTL 双因子失效
  - 新增 `get_sector_fund_flow()` 函数，TUI 菜单 [1] 刷新时更新
- **分红历史集成** — 调用 akshare `stock_history_dividend()` 获取个股历年分红数据
  - 分类汇总（模块 3）新增「年均股息率」列：`avg_dividend / price × 100%`
  - 穿透 TOP10（模块 4）新增「年均股息率」列：原始 `avg_dividend` 值
  - 缓存策略：持仓/穿透代码列表指纹 + 1 月 TTL 双因子失效
  - 多线程并行获取（max_workers=5），TUI 菜单 [1] 刷新时更新
- **进程级内存缓存层** — 在文件缓存之上新增 `_MEMO_CACHE`，减少同一会话内的重复文件读取
  - profit_forecast: 5 分钟 memo TTL，sector_flow: 1 分钟，dividend: 10 分钟
- **指数数据内存缓存** — `_INDEX_MEMO` 缓存 `fetch_indices()`/`fetch_us_indices()` 结果 60 秒，消除每次指纹计算时的重复 HTTP 请求

### Changed
- **LLM 宏观缓存 TTL**：`cache_ttl_macro` 从 4 小时（14400s）调整为 24 小时（86400s），配合指数指纹驱动缓存失效策略，减少不必要的 API 调用
- **行业资金流向缓存 TTL**：`sector_flow` 从 1 天（86400s）调整为 15 分钟（900s），提升盘中数据的时效性
- `_compute_index_fingerprint()` 改为使用 `_INDEX_MEMO` 缓存指数数据，避免每次指纹计算重复 HTTP 请求
- 所有 akshare_extras 调用（profit_forecast/sector_flow/dividend）增加进程级 memo 缓存，减少文件缓存读取

### Fixed
- 移除 `exc_info=True` 参数从 `logger.debug("分红数据解析失败")` 调用中（仅在 Exception 级别有意义）
- 修复 `_DIVIDEND_CACHE_PREFIX` 重复定义问题

### Docs
- config.json cache_ttl 补充 8 个缺失条目（news_corr, industry, llm, llm_macro, llm_expert, profit_forecast, sector_flow, dividend）
- llm_settings.json cache_ttl_macro 同步为 86400
- requirements.md：菜单 [1] 范围新增 `dividend_*` 清除；TTL 表新增 profit_forecast/sector_flow/dividend；Cache 文件清单新增对应条目；模块列宽同步
- README.md：版本更新至 0.2.18，功能特性新增，配置示例同步，cache_ttl 表补全

### Tests
- 新增 `src/test_akshare_extras.py`：16 项测试覆盖指数指纹、缓存键、分红汇总计算、分红数据获取全路径、内存缓存（TestMemoCache 5 项）
- `src/test_llm_client.py`：新增 2 项 sector_flow 测试
- 全量 737 passed, 30 subtests passed

## [0.2.17] - 2026-06-28

### Changed
- **文档精简**：`plan.md` 历史迭代（Iter 1.1~3.7）归档至 `docs-stm/plan/archived_plan.md`，原文件从 525 行精简至 70 行；`review-findings.md` 审计记录精简保留典型问题，从 135 行压缩至 50 行
- **main.py 职责拆分**：拆分为 `tui_menu.py`（菜单定义/渲染）、`tui_handlers.py`（命令处理器），`main.py` 从 1177 行降至 100 行（纯入口+主循环）
- **news_aggregator.py 模块拆分**：拆分为 `news_keywords.py`（关键词提取）、`news_correlator.py`（关联匹配）、`news_sources.py`（源获取注册），`news_aggregator.py` 保留聚合逻辑
- **technical.md**：`llm.json` 引用更新为 `llm_key.json` / `llm_settings.json`

### Added
- **新测试模块**：`test_tui_menu.py`（17 项）、`test_tui_handlers.py`（14 项）、`test_news_keywords.py`（17 项）、`test_news_correlator.py`（16 项）、`test_news_sources.py`（11 项）、`test_integration.py`（7 项），共 +76 测试

## [0.2.16] - 2026-06-28

### Fixed
- **P0 config null 覆写**：`config.json` 中字段设为 `null` 时不再覆盖默认值，防止 `int(None)` 崩溃（`src/config.py`）
- **P1 benchmark 竞态条件**：多线程并发调用 `fetch_fund_benchmark()` 时，以每个基金代码独立加锁防止数据覆写（`src/fetcher.py`）
- **P1 缓存参数无效**：`tiantian.py` 缓存绕开参数 `"rt": "0.123456"` 硬编码固定值，改为 `random.random()` 真正生效
- **P1 死关键词**：`penetration.py` 板块分类中 `"JP MORGAN"` / `"MORGAN STANLEY"` 因去空格后无法匹配，移除
- **P2 重试次数不匹配**：`_call_claude()` / `_call_openai()` 中重试条件仍用硬编码 `_RETRY_MAX=2` 而非用户配置的 `max_retries`，修正；延迟数组扩展至 `[1, 3, 5, 10, 15]` 支持更多重试
- **P2 空 LLM 结果缓存**：LLM 返回空白内容时不再写入缓存，避免 TTL 期内输出空白报告
- **P2 零成本持仓放行**：零成本持仓（赠与/转股）不再被 `cost_price <= 0` 跳过，改为仅跳过负成本

### Performance
- **指数并行**：`fetch_indices()` 从顺序获取改为 `ThreadPoolExecutor(max_workers=5)` 并行拉取 5 个 A 股指数
- **行业数据并行**：`batch_fetch_industry_data()` 从顺序循环改为 `max_workers=10` 并行 HTTP 请求
- **benchmark 缓存锁优化**：带双重检查的 per-code 锁，减少不必要的重新获取

### Removed (死代码)
- `src/report/styles.py`：`NUMBER_ALIGN` 常量（无引用）
- `src/report/excel_writer.py`：`add_styles_to_cells()` 函数（无调用且不生效）
- `src/test_excel_writer.py`：`TestAddStyles` 测试类（对应死函数）

### Changed
- `src/report/summary.py`：收益率盈亏着色从脆弱的字符串解析改为纯 `isinstance(val, (int, float))` 处理
- `src/report/penetration.py`：`__import__("datetime")` 惰性导入改为顶层 `from datetime import datetime`
- `src/report/excel_writer.py`：`_ensure_reports_dir()` 增加存档子目录写入权限检测
- `src/reader.py`：零成本持仓允许穿透计算和盈亏显示

### Tests
- 633 passed (30 subtests)，移除 1 个死代码测试类，更新 2 个测试适配新逻辑

## [0.2.15] - 2026-06-28

### Changed
- LLM 配置文件拆分：敏感密钥 `data/config/llm.json` → `data/config/llm_key.json`，config.json 键名 `llm_config_file` → `llm_key_file`
- LLM 非敏感配置从 config.json llm_settings 段独立为 `data/config/llm_settings.json`，config.json 新增 `llm_settings_file` 引用
- `src/config.py`：`get_llm_config_path()` → `get_llm_key_path()`，新增 `get_llm_settings_path()`
- `get_llm_config()` 读取逻辑：基础层从 config.json.llm_settings 改为 llm_settings.json（向后兼容保留 config.json.llm_settings 回退）
- `src/config.py` 缺省 temperature 默认值：`temperature_macro=0.3`、`temperature_expert=0.8`、`temperature_news_correlation=0.1`（原为 `None`）
- 全量用户提示信息从 `llm.json` → `llm_key.json` / `llm_settings.json`

### Added
- `src/config.py`：新增 `_ensure_llm_settings_file()` 自动初始化函数（`init_config()` 触发）
- llm_settings.json 写入代码内置 system_prompt 缺省值，用户可直接编辑覆盖

### Docs
- README.md：LLM 配置指引重写为双文件架构，新增推荐值说明
- requirements.md/plan.md/testplan.md：llm.json 引用更新为 llm_key.json，TLT 优先级链更新
- changelog.md：本版本记录

## [0.2.14] - 2026-06-28

### Added
- 新增财经新闻源：华尔街见闻（wallstreetcn.com）
  - API：`api-one.wallstcn.com/apiv1/content/lives?channel=global-channel`（全球财经直播流）
  - 无鉴权要求，JSON 格式，标题/正文/时间戳字段完整
  - 新增 `src/providers/wallstreetcn_news.py`（参考 sina_news.py 结构）
  - `news_aggregator.py` 注册：`_SOURCE_LABELS`、`_FALLBACK_ENABLED`、`_FETCH_MAP` 新增 wallstreetcn 条目
- 新增财经新闻源：akshare（财新网 / CCTV）
  - 通过 akshare 开源库间接获取财新网要闻 + 央视财经新闻
  - 新增 `src/providers/akshare_news.py`
  - `news_aggregator.py`、`config.py` 注册 akshare 源，默认启用
  - `requirements.txt` 新增 `akshare>=1.18.0`
- 新闻页脚标注成功访问的数据源：HTML 报告「财经新闻热点与持仓关联分析」底部新增"本次抓取财经资讯所使用的数据源"行，仅列出成功获取数据的源，无论是否匹配到关键词

### Changed
- `news_aggregator.py`：ThreadPoolExecutor max_workers 从 3 提升至 5（适配 5 源并行）
- `build_news_data()` 返回值 meta 新增 `active_sources` 字段

### LLM 配置优化
- `llm_client.py`：`temperature_macro / temperature_expert / temperature_news_correlation` — 每个模块独立控制生成温度，从 llm.json 读取，不设置时使用 API 默认值
- `llm_client.py`：`timeout_macro / timeout_expert / timeout_news_correlation` — 每个模块独立控制 API 超时，替代原来的硬编码 60s/120s/60s
- `llm_client.py`：`max_retries` — API 调用重试次数从 llm.json 读取（默认 2），替代硬编码 `_RETRY_MAX`
- `llm_client.py`：`cache_enabled_macro / cache_enabled_expert / cache_enabled_news` — 缓存独立开关，关闭时每次重新生成，适用于需要实时更新的场景
- `llm_client.py`：`output_brief_macro / output_brief_expert` — 精简模式，附加大幅缩减的输出长度约束到 system prompt，适用于快速预览场景
- `generate_all_llm()` 缓存预检也尊重 cache_enabled 开关，禁用时跳过双缓存检查

### Docs
- README.md：版本号、news_sources 配置表、数据源表、目录结构、特性列表同步更新
- requirements.md：数据源表同步
- changelog.md：本版本记录

## [0.2.13] - 2026-06-28

### Added
- 穿透 TOP10 新增「概念」列：排名|名称|代码|穿透市值|占比|板块|**概念**|来源明细
  - 概念数据从行业分类缓存获取（`batch_fetch_industry_data`），取前 3 个概念以 ` / ` 拼接
  - `compute_penetration_top10()` 返回条目标新增 `concepts` 字段
  - HTML 模板同步新增概念列
- 新闻关联关键词补充行业/概念标签：
  - `_build_keyword_lookup()` 为持仓/穿透条目附加 `industry` 和 `concepts_list` 字段
  - 新增 `_format_industry_tags()` 生成 ` [行业 · 概念]` 后缀
  - 持仓显示变为 `长江电力(600900) [电力 · 水电]`、穿透显示变为 `腾讯控股[穿透] [互联网科技 · 社交]`

### Tests
- `test_penetration.py`：新增 `TestPenetrationConcepts`（2 项测试）验证 concepts 字段输出
- `test_news_correlation.py`：新增 `TestFormatIndustryTags`（6 项测试）、`TestEnrichKeywordsWithIndustryTags`（3 项测试）
- 全量 626 passed, 30 subtests passed

## [0.2.12] - 2026-06-28

### Added
- HTML 报告市值核算明细表取价方式列蓝色标识（与 Excel 端同步）
  - 新增 `_jinja_price_type_color` Jinja2 过滤器：校内收盘价(T)/官方净值(T) → #0066CC
  - QDII 基金官方净值(T-1) → #0066CC
- 新增 7 项 `test_html_writer.py` 测试覆盖取价方式着色规则

### Tests
- `test_html_writer.py` 新增 TestJinjaFilters 取价方式着色场景：场内收盘价(T)、官方净值(T)、QDII T-1、非 QDII T-1、场内实时价、未知类型、无名称 T-1
- 全量 615 passed, 30 subtests passed

## [0.2.11] - 2026-06-28

### Added
- 新增 `src/providers/eastmoney_industry.py`：东方财富 push2 API 行业分类/概念板块 provider
- 行业/概念自动获取：`fetch_industry_and_concepts()` 从 `push2.eastmoney.com` 获取三级行业名称、行业ID、概念板块列表和概念ID
- 缓存集成：新增 `industry` 缓存类型（7 天 TTL），文件名 `industry_{code}.json`
- 新闻关键词扩展：`build_news_data()` 自动获取持仓+穿透资产的行业名称和概念板块，追加到关键词列表提高匹配率
- 关键词富化新增"概念"类型（橙标）：行业名称和概念板块显示为 `XXX[概念]`，排序优先级位于穿透和行业之间
- 穿透模块板块分类增强：`compute_penetration_top10()` 调用 `batch_fetch_industry_data()` 补充 API 行业数据，优先覆盖板块列
- HTML 模板新增 `.source-tag-concept` CSS 类：琥珀色背景 + 深橙色文字
- 菜单 [1] 更新基础类缓存：新增 `industry_*` 前缀清除
- 新增 `src/test_eastmoney_industry.py`（10 项测试）

### Changed
- 数据源表：行业分类/概念板块从"规划中"更新为"已实现"
- NEWS_COLS 模块 6 运行流程：在 `aggregate_news()` 前先获取行业/概念数据并扩展关键词
- `check_and_refresh_caches()` 新增 `industry_*` 缓存自动清理（持仓变更时）
- `_check_and_warm_for_new_assets()` 新增新增资产行业分类自动预热（`batch_fetch_industry_data`）
- `_build_keyword_lookup()`：新增 `industry_data` 参数处理行业和概念板块关键词
- `_enrich_keywords_for_item()`：新增 `concept` 类型处理逻辑
- type_order 扩展：holding(0) → penetration(1) → concept(2) → industry(3)

### Docs
- requirements.md：数据源表、缓存文件清单、TTL 表、菜单 [1] 范围、模块 4 板块分类增强、模块 6 关键词来源同步
- README.md：版本 v0.2.11、数据源表、缓存文件清单、菜单表、模块 6 概念类型、缓存覆盖矩阵（菜单 [1]/[2] 矩阵表）
- testplan.md：新增 v0.2.11 测试重点
- changelog.md：本版本记录
- review-findings.md：新增审查记录
- technical.md：新增技术文档

### Tests
- 新增 `src/test_eastmoney_industry.py`：10 项测试覆盖正常返回（含/不含概念）、data 为空、响应为空、超时异常、基金代码
- `src/test_news_correlation.py`：新增 3 项测试覆盖概念类型 lookup 构建、概念类型优先于行业、混合类型排序
- 全量 607 passed, 30 subtests passed

### Added
- 关键词富化：`_build_keyword_lookup()` / `_enrich_keywords_for_item()` / `_format_enriched_keywords()` 三个新函数，自动标注每个关联关键词的来源类型（持仓/穿透/行业）
- 关键词富化集成到 `build_news_data()`，每条新闻新增 `enriched_keywords` 字段
- Excel 新闻页签格式优化：B 列（标题）宽 40、C 列（摘要）宽 50，启用文本换行 + 左对齐
- HTML 模板关键词列改用 `enriched_keywords`，按类型着色（持仓→蓝、穿透→紫、行业→灰）
- CLAUDE.md 新增缺陷自测规则：修复缺陷时优先编写测试用例，新增功能时主动研究能否自测

### Changed
- **菜单 [1] 更新基础类缓存**：清除范围新增 `news_*` 和 `llm_news_corr_*`（补全缓存清理覆盖）
- `write_news_sheet()`：关联关键词列使用 `_format_enriched_keywords()` 替代纯 `", ".join(matched_keywords)`，优先显示富化文本
- `_build_keyword_lookup()` 中文名称索引策略：从 4 字或更长名称中生成 2 字滑动窗口片段（如"长江电力"→"长江""电力"），提高短关键词匹配率

### Docs
- requirements.md：同步菜单 [1] 缓存范围、缓存文件清单新增 `llm_news_corr_*`、TTL 表新增 `news_corr`、模块 6 新增关键词富化/LLM 关联分析/Excel 格式优化描述、数据源表新增东方财富行业/概念板块
- README.md：版本 v0.2.9，同步菜单/缓存/模块 6 描述
- testplan.md：新增关键词富化函数/Excel 格式/HTML 同步测试类别
- review-findings.md：新增最新一致性审查记录
- CLAUDE.md：新增缺陷自测规则要求

### Tests
- 新增 3 个测试类：TestBuildKeywordLookup、TestEnrichKeywordsForItem、TestWriteNewsSheetFormatting
- 新增 15 项测试：覆盖 lookup 构建（持仓/穿透/去重/空）、富化逻辑（三种类型、排序、空兜底）、格式断言（wrap_text、列宽、对齐）
- 全量 592 passed, 30 subtests passed

## [0.2.9] - 2026-06-28

### Added
- LLM 新闻关联分析：新增配置选项 `llm_news_analysis`（默认关闭），开启后使用 LLM 对关键词匹配后的新闻进行二次关联分析，逐条判定关联度（高/中/低/无关）并给出原因分析
- `enhance_news_correlation()`：llm_client 新函数，含 Prompt 构建、缓存、JSON 解析、token 用量跟踪
- Excel & HTML 新闻页签 LLM 分析列：当数据含 `llm_analysis` 时自动增加 "LLM 关联分析" 列
- Excel & HTML 页签底部智能注脚：LLM 缓存命中 → "使用了LLM缓存"；LLM 未启用 → "未依赖于LLM服务，使用传统爬虫+NLP能力"；LLM 启用 + 非缓存 → Token 消耗明细
- llm.json 新增 `max_tokens_news_correlation` / `cache_ttl_news_correlation` / `system_prompt_news_correlation` 配置
- HTML 报告：`write_html_report()` 新增 `news_llm_meta` 参数，内部新闻获取改用 `build_news_data()` 以支持 LLM 增强
- HTML 模板：新增 `has_llm_analysis` 控制 LLM 列显隐，`thousands` Jinja2 过滤器
- 缓存清理：菜单 [1] 新增 `llm_news_corr_*` 前缀清除，补全漏网之鱼
- 新测试：TestBuildNewsDataWithLLM、TestApplyLLMAnalysis、TestEnhanceNewsCorrelation、TestBuildHoldingsSummary、TestBuildNewsSummary、TestNewsLlmMetaTemplate、TestWriteHtmlReportNewsLlmMeta、TestJinjaFilters 等合计 34 项

### Changed
- `build_news_data()` 返回类型：`list` → `tuple[list, dict]`（新增 metadata 字典，含 llm_enabled/llm_cached/token_usage）
- `write_news_sheet()` 参数：`llm_token_usage` → `llm_meta`（metadata 字典）
- `_generate_excel_report()` 参数：`news_token_usage` → `news_llm_meta`
- `_get_cache_ttl_llm()` 新增 `"news"` subtype 支持（默认 3600s）

## [0.2.8] - 2026-06-27

### Performance
- 菜单 [1]（基础类缓存）：串行循环 → ThreadPoolExecutor(max_workers=3) 并发刷新，每线程内串行完成 fetch_fund_rankings + fetch_fund_holdings + fetch_fund_benchmark
- 菜单 [2]（持仓类缓存）：串行循环 → ThreadPoolExecutor(max_workers=5) 并发取价，报价完成后单线程更新指数和报告计数
- 新闻 3 源获取：串行 for 循环 → ThreadPoolExecutor(max_workers=3) 并行拉取新浪/东方财富/财联社
- 指数获取：ThreadPoolExecutor(max_workers=2) A 股 + 美股并行
- LLM 生成：ThreadPoolExecutor(max_workers=2) 全局政经 + 智囊团并行
- generate_all_llm 缓存预检：双缓存均命中时直接返回，跳过线程池

### Added
- 新闻缓存：aggregate_news() 增加 15 分钟 TTL 缓存，键名 `news_{md5}`，多源新闻结果复用
- get_llm_config() mtime 缓存：仅当 llm.json 文件修改时间变化时重新读取，减少重复 IO
- LLM Token 用量双重展示：控制台 print 输出 + 报告文件 HTML 尾注 (`<p style="color:#888;font-size:12px">⚡ Token 用量：...</p>`)
- Token 压缩 `_fmt_wan()` 工具函数：万/亿中文单位格式化，减少 ~20-30% 输入 token
- `_busy` 标志：防止菜单反复按键导致任务重入
- `_check_network_available(details)` 辅助函数：检查网络连通性并提供详情
- 配置校验：cache_ttl 正数校验警告、llm.json provider/endpoint 合法性警告
- cache.set() FileNotFoundError 重试保护：竞争删除目录与创建文件之间的竞态条件

### Changed
- LLM 缓存直接存储 HTML（取消双重 `_markdown_to_html` 调用，缓存读取后直接用于 HTML 报告）
- max_tokens 分离为 `max_tokens_macro=800` / `max_tokens_expert=8192`，移除全局 `max_tokens` 冗余配置
- `_SYSTEM_EXPERT` 压缩：~435 字 → ~230 字，移除 emoji、冗余指示词和多级标题格式
- `_LLM_TIMEOUT` 统一提升：60.0 → 120.0（覆盖所有 LLM 调用路径）
- `write_llm_sheets()` 参数精简：12 个参数 → 2 个参数 `(wb, llm_content)`
- `_generate_excel_report()` 增加 `news_data` 参数，复用调用方预获取的新闻数据
- `write_html_report()` 增加 `news_data` 参数，复用预获取新闻，复用日志标记"复用调用方传入的新闻数据"
- `_call_llm()` / `_call_claude()` / `_call_openai()` 返回类型：`Optional[str]` → `tuple[Optional[str], Optional[dict]]`
- 7 个 `_cmd_*` 函数中每次 `read_holdings()` 后增加空持仓检查并直接返回
- cache 前缀映射表：移除 `"portfolio": "hold"` 和 `"penetration": "hold"` 条目
- `exact_map` 新增 `"holdings_tracking": "benchmark"`（30 天 TTL）
- `get_llm_config()` 引入 mtime 缓存：每次调用不再重复读文件 IO
- config.py 模块级 `logger` 替代多处 `__import__("logging").getLogger("invest")`
- `_generate_details` 移除 `_is_stock` 判断和 `UnboundLocalError` 修复保持（v0.2.7 遗留清理）

### Fixed
- `_check_claude_truncation` 返回类型修正：`None` → `bool`
- `_check_openai_truncation` 返回类型修正：`None` → `bool`
- cache.set() 目录删除竞态条件：FileNotFoundError 时自动重试
- `_call_llm` fallback 简化：`max_tokens = max_tokens or 2500`（移除 `llm_config.get("max_tokens", 2500)`）
- `html_writer.py`：a_indices/us_indices 从 list 改为 dict（fetch_indices() 原始类型），LLM 调用不再因 `.values()` 缺失崩溃；模板渲染使用独立 list 变量
- `fund_performance.py`：`perf_eval.get("categories")` / `perf_eval.get("data")` 在 API 返回 JSON null 时返回 None，导致 `enumerate(categories)` 和 `len(scores)` 崩溃 — 改用 `or []` 兜底
- `summary.py`：`write_summary_sheet` 接收的 `fetch_indices()` 指数数据被调用方错误转为 list 后传入，`dict.get()` 操作引发 `AttributeError` 崩溃 — 修正为保留 dict 原始类型传递
- `fund_performance.py`：`_adjust_rating_with_benchmark` 中 `perf_eval.get("categories")` 在 JSON null 时返回 None 而非空列表，循环中 cat 为 None 时 `"超额" in cat` 引发 `TypeError` 崩溃 — 改用 `or []` 兜底

### Removed (Dead Code)
- `src/cache.py`：移除 `exists()` 函数（无生产调用者）
- `src/providers/tiantian.py`：移除 `fetch_fund_type()` 函数（定义但未调用）
- `src/providers/sina_news.py`：移除 3 个死函数 `correlate_news_with_holdings` / `fetch_and_correlate` / `build_holding_keywords`；移除未使用的 `import re`
- `src/report/llm_content.py`：移除 ~60 行死代码 else 分支（从未执行）；移除 12 个未使用参数；移除未使用的 import（fetch_indices, fetch_us_indices, generate_all_llm, DetailRow, compute_penetration_top10, Holding, write_data_row）
- `src/main.py`：移除 `portfolio_items` 字典；移除未使用的 import（DetailRow, classify_holdings, compute_penetration_top10）
- `src/test_cache.py`：移除 `TestCacheExists` 类（test_exists_file_present, test_exists_file_absent）
- `src/test_llm_client.py`：更新 `_call_llm` 路由测试适配新的 `(content, usage)` 元组返回类型
- `llm.json`：移除冗余 `max_tokens` 字段

### Docs
- CLAUDE.md：精简为 18 行，移除冗余目录树（引用 docs-stm/README.md）
- README.md：版本 v0.2.8，菜单文字同步，LLM 配置表更新，缓存章节重写（3 层+指纹机制）
- requirements.md：菜单表同步，缓存文件/TTL 表更新，引用链同步
- review-findings.md：新增优化/审计审查记录
- plan.md：新增 Iter 3.6 全面性能优化与代码清理
- testplan.md：测试覆盖更新（534 项）
- changelog.md：本版本记录

## [0.2.7] - 2026-06-27

### Added
- LLM 缓存分层策略：全球政经局势 TTL 4 小时（`cache_ttl_macro`），智囊团深度复盘 TTL 2 小时（`cache_ttl_expert`），支持 llm.json 配置
- LLM 缓存键引入指纹（MD5 of input data），持仓/指数数据变更时缓存自动失效
- 菜单 [2] 更新持仓类缓存时主动清除 `llm_expert_*` 和 `llm_global_macro_*` 缓存文件
- `cache_ttl_macro` / `cache_ttl_expert` 字段写入 `data/config/llm.json` 示例模板

### Changed
- LLM 缓存 TTL 配置从 `config.json` 迁移至 `llm.json`，优先级链：`llm.json` → `config.json` → 代码默认值
- 菜单 L 从 `force=True`（每次强制调用）改为 `force=False`（缓存有效期内复用，指纹+TTL 双重校验）
- B 菜单/L 菜单内部改为数据预计算一次，HTML 和 Excel 复用结果，消除重复 LLM 调用
- ThreadPoolExecutor 串行化（`generate_all_llm`），消除全局 `httpx.Client` 线程安全问题
- `_generate_details` 改为 `ThreadPoolExecutor(max_workers=8)` 并发取价，提升大持仓性能
- 菜单文字统一：`EXCEL` → `Excel`，`基础缓存信息` → `基础类缓存`，`持仓相关缓存信息` → `持仓类缓存`

### Fixed
- L 菜单 LLM 双重调用问题（HTML writer 和 Excel writer 各调用一次 → 改为预计算后传递 `llm_content` 元组）
- ThreadPoolExecutor + httpx.Client 死锁导致 L 菜单卡死（LLM 全局线程池安全改造）
- 空持仓场景下 _generate_details 的 `UnboundLocalError`（DetailRow 构造移至循环体内）

### Docs
- README.md：菜单文字同步、缓存 TTL 表区分 llm_macro/llm_expert、LLM 配置新增 `cache_ttl_macro`/`cache_ttl_expert` 字段、FAQ 更新
- requirements.md：菜单表同步、TTL 表新增 LLM 条目、手动刷新说明更新
- changelog.md：本版本记录

## [0.2.6] - 2026-06-27

### Fixed
- 穿透TOP10三重计算优化：compute_penetration_top10 统一计算一次，三处复用（穿透页签/新闻关键词/LLM增补）

### Added
- LLM System Prompt 外部可配置：data/config/llm.json 新增 system_prompt_macro / system_prompt_expert 字段
- 智囊团升级为5位专家模式：三阶段圆桌会议（召集令 → 两轮辩论 → 定音锤），System Prompt 精简至 297 字
- LLM 全局四大优化：并行调用（ThreadPoolExecutor 并发生成模块7+8）、httpx连接复用（全局 _HTTP_POOL 共享连接池）、LLM配置内存缓存（_LLM_CONFIG_CACHE 避免重复文件IO）、提示词紧凑化

### Changed
- 模块 7/8 用户提示词改为紧凑格式，减少约 35% 输入 token
- _build_macro_prompt / _build_review_prompt 输出格式精简，单行摘要替代多段描述

## [0.2.5] - 2026-06-27

### Fixed
- 持仓变更检测：新增持仓时自动预热 price/fund_perf/fund_hold 单条缓存；清除过期的 fund_benchmarks 和 penetration_cache 合并缓存
- 缓存降级覆盖：fetch_market_data / _fetch_with_fallback / fetch_indices 在 API 全失败时降级使用 7 天内过期缓存
- H 菜单语义修复：H 菜单生成"基础的 HTML"不再包含财经新闻（与 E/N/B 菜单的语义保持一致）
- 代码清理：移除 fetcher.py 中未使用的 tiantian_holdings 注册项、cache.py 前缀匹配边缘情况、未使用的导入变量

### Added
- Excel LLM 增补页签：模块 7（全球政经局势）和模块 8（智囊团深度复盘）通过菜单 L 触发
- 新增 src/report/llm_content.py：LLM 内容写入 Excel 页签（含 HTML 标签剥离、合并单元格排版）
- cache.py check_and_refresh_caches()：持仓 MD5 指纹检测，持仓变更时自动清除关联缓存并返回新增代码列表
- main.py _check_and_warm_for_new_assets()：对新增资产自动预热价格/业绩/持仓缓存
- 新增缓存文件 holdings_tracking.json：记录持仓指纹和代码集合，用于变更检测

### Changed
- main.py: _cmd_generate_html 增加 news 参数控制是否获取新闻；_cmd_generate_full 传 enable_llm/include_llm=True
- main.py: _generate_excel_report 新增 include_llm 参数
- html_writer.py: write_html_report 新增 include_news 参数，新闻获取改为可选
- llm_content.py: write_llm_sheets 新增 penetration_data 可选参数，支持传入预计算穿透数据
- requirements.md: 缓存降级规则标记为"已实现"

## [0.2.4] - 2026-06-27

### Added
- 财经新闻源扩展为 3 源并行获取：新浪财经（`feed.mix.sina.com.cn`）+ 东方财富（`push-api-html.eastmoney.com`）+ 财联社（`www.cls.cn`）
- 新增 `src/providers/cls_news.py`：财联社 7×24 实时财经快讯 provider
- 新增 `src/providers/eastmoney_news.py`：改写为 JSON push API 替代原 HTML 爬取方式
- 新增 `src/providers/news_aggregator.py`：多源新闻聚合器，统一关键词提取 + 去重 + 关联排序
- 新闻关键词扩展：除直接持仓外，新增穿透 TOP10 底层资产（代码 + 名称）参与关键词匹配
- `build_holding_keywords()` 新增 `penetrated_assets` 参数，提取穿透资产代码和中文名
- config.json `cache_ttl` 项新增 `llm` 类型预留字段
- requirements.md：数据源表更新（3 源 + 美股指数）、缓存策略重写（用途/命名/TTL 表）、基金业绩评价三层标准
- README.md：多源新闻特性、缓存策略重写、基金业绩评价标准、目录结构更新（新增 3 个 provider 文件）
- plan.md：Iter 3.2 文件清单更新

### Changed
- build_news_data() 新增 `penetrated_assets` 参数，传入穿透列表自动扩展关键词
- html_writer.py：新闻获取改为使用 news_aggregator 聚合器，传入穿透资产数据
- main.py：Excel 报告新闻页签生成前先计算穿透 TOP10，传递资产列表到新闻关联
- eastmoney_news.py：从 HTML 爬取重写为 JSON push API，删除废弃的 `_parse_list_html`/`_fallback_fetch`/`fetch_and_correlate`
- 缓存清理模块 `cleanup_expired()` 增加 `llm_` 前缀映射

### Docs
- requirements.md：全面重写缓存策略章节（用途/命名规则/TTL 对照/引擎接口/降级规则）；基金业绩评价标准增加三层计算逻辑说明；数据源表补充 3 源新闻和美股指数
- README.md：同步缓存说明、数据源、业绩评价标准；目录结构新增 providers 文件清单

### Added
- 穿透模块新增板块分类（消费/科技/医药/新能源/金融等），Excel + HTML 均显示板块列
- 穿透模块底部标注新增无法获取穿透数据的基金明细（名称+代码）
- 穿透模块关键词映射表覆盖 10+ 板块、100+ 关键词
- QDII/债券基金季报持仓回退链路：改用 `FundArchivesDatas.aspx` JS 变量解析替代已废弃的 `FundArchivesDatas` JSONP 接口
- 文档全量审计：CLAUDE.md/README.md/requirements.md/testplan.md/changelog.md 五文件同步
- config.py: `output_dir` 配置项（默认 "reports"），报告输出目录可配置
- config.py: `news_top_count` 配置项（默认 100），财经新闻 TOP N 可配置
- main.py: 新增菜单 L（生成包含所有内容的全系列报告，含 LLM 增补内容）
- main.py: 新增菜单 R（配置报告输出目录）
- main.py: `_cmd_generate_full` 全系列报告生成函数（L 菜单）
- main.py: `_cmd_config_output_dir` 输出目录配置函数（R 菜单）
- main.py: 配置显示中增加输出目录行
- main.py: 所有含新闻的生成路径（H/B/L/N）读取 `news_top_count` 配置并向下传递
- excel_writer.py: `save_workbook` 增加 `output_dir` 参数
- html_writer.py: `write_html_report` 增加 `output_dir` 参数，移除硬编码 `_REPORT_DIR`
- html_writer.py: `write_html_report` 增加 `news_top_count` 参数，控制新闻输出条数
- requirements.md: 模块 7/8 改为"Excel + HTML，LLM 增补项目"
- fund_performance.py: 业绩评价标色（优秀→红色、偏差→绿色、稳定→蓝色，Excel + HTML）
- styles.py: 新增 `BLUE_FONT` 常量
- main.py: 新增菜单 [3] 清理过期缓存文件（`_cmd_cleanup_cache`）
- main.py: 新增菜单 [4] 查看缓存统计信息（`_cmd_show_cache_stats`）
- main.py: 启动时自动静默清理过期缓存文件
- main.py: 持仓文件选择器增强，显示文件名/大小/修改日期/账户数
- main.py: 新增 `_print_error_with_hint()` 异常友好提示（网络错误/权限不足/文件损坏）
- cache.py: 新增 `cleanup_expired()` 清理过期缓存文件（支持 dry-run 预览）
- cache.py: 新增 `get_cache_stats()` 缓存统计信息（总数/大小/按前缀分类）
- cache.py: 新增 `get_cache_dir()` 获取缓存目录绝对路径
- reader.py: 新增 `get_xlsx_info()` 获取 xlsx 文件信息（页签数/行数）
- html_writer.py: 模块 7/8 模板占位文本（`llm_enabled=False` 时输出"本节内容待生成"提示）
- report_template.html: 新增模块 7（全球政经局势）和模块 8（智囊团深度复盘）占位区域，`{% if llm_enabled %}` 条件渲染

### Changed
- main.py: TUI 菜单扩展为 13 选项，新增 [3] 清理过期缓存 / [4] 查看缓存统计
- main.py: TUI 菜单重构，E=核心 Excel（5 模块），N=Excel+新闻增补（6 模块）
- main.py: TUI 菜单 E→生 EXCEL 分析报告，N→生成包含新闻的 EXCEL 分析报告
- main.py: TUI 菜单 H→生成 基础的 HTML 分析报告（不含 LLM 增补）
- main.py: TUI 菜单 A→B 生成全系列包含新闻的报告 (Excel + HTML)
- main.py: `_cmd_generate_both` 改为 B 快捷键，生成 HTML + Excel（含新闻）
- tiantian.py: `fetch_quarterly_holdings` 重写为解析 `apidata.content` HTML（支持 GBK 编码）
- tiantian.py: `fetch_fund_holdings` 移除早期 return 阻塞季报回退路径的问题
- requirements.md: TUI 菜单表重构（11 选项，新增 B/L/R，更新 H 标签）；模块 7/8 改为 Excel + HTML
- README.md: 菜单表、配置说明同步更新；模块 7/8 改为 LLM 增补项目
- testplan.md: Iter 3 测试重点增加 N/A 新菜单和新闻关联验证
- sina_news.py: `correlate_news_with_holdings` / `fetch_and_correlate` 增加 `top_n` 参数，硬编码 50/100 改为可配置
- sina_news.py: `fetch_and_correlate` 增加 `max_news = max(max_news, top_n * 3)` 自动缩放逻辑，确保 `top_n` 较大时能获取足够原始新闻条数
- news_correlation.py: `build_news_data` 增加 `top_n` 参数
- html_writer.py: 增加 `_test_writable()` 目录可写性检查辅助函数
- excel_writer.py: `save_workbook` 存档路径增加 PermissionError/OSError try/except 保护
- plan.md: 更新 TOP 20→TOP N；移除 A→B 旧注释

### Bug Fixes
- tiantian.py: ETF 收益率正则不匹配负号的问题（`[\d.]+` → `-?[\d.]+`），影响 159222/518880 等 ETF 的近 3 月/近 6 月数据显示
- fetcher.py: `fetch_us_indices` 增加重试机制 + 过期缓存降级逻辑，解决新浪 API 偶发不可用导致美股指数缺失的问题
- 注意：ETF 区间收益率修复后，需通过菜单 [1] 刷新基础缓存以清除旧缓存数据
- summary.py: 美股指数键名 `int_*` 修正为 `gb_*`，匹配 Sina API 实际返回的代码格式，汇总页美股指数恢复正常显示
- report_template.html: 穿透占比列 `entry["ratio_pct"] / 100 | pct` 缺少括号导致 Jinja2 过滤器优先级异常报错，已修复
- market_value.py: 场外基金本日盈亏使用 `trading_day`（所属交易日）/ `prev_td`（前一交易日）做对比，替代原来的 `today_str` 日历日期对比，解决非当日更新的场外基金本日盈亏始终为 0 的问题
- cache.py: `get()` 读取 JSON 损坏时自动删除损坏文件而非静默跳过
- main.py: 全部异常处理升级为 `_print_error_with_hint()`，网络错误/权限错误/文件找不到/JSON 损坏分别给出针对性中文提示

### Added (Iter 3.1)
- HTML 报告生成引擎（Jinja2 模板引擎）：5 个模块完整渲染到单页 HTML
- `src/report/html_writer.py`: 报告编排引擎，复用现有计算逻辑
- `src/tmpl/report_template.html`: Jinja2 HTML 模板（含响应式 CSS、盈亏着色）
- reqiurements.txt: 新增 Jinja2 依赖
- TUI 菜单 H/A 选项接入真实 HTML 生成

### Added (Iter 3.2)
- `src/providers/sina_news.py`: 新浪财经新闻获取 + 持仓关键词关联模块
- `src/report/news_correlation.py`: 新闻关联分析的 Excel 页签生成 + HTML 数据构建
- TUI 菜单新增 N 选项：生成包含新闻的 Excel 报告
- HTML 报告新增模块 6（财经新闻热点与持仓关联分析）


## [0.2.2] - 2026-06-27

### Added
- 基金业绩分析「类型」列使用穿透分类系统自动标注：场内ETF、场外主动型基金、场外指数基金、场外QDII基金、场外债券基金（取代 API 原始类型）
- 基金业绩分析新增 2 列：累计盈亏(¥)、收益率（从市值核算模块提取持仓盈亏数据），表格扩展为 11 列
- category.py: 收益率列 (8) 增加红绿着色（同盈亏列/本日盈亏列处理方式）

### Changed
- fund_performance.py: 列数 9 → 11，新增累计盈亏(¥)、收益率两列
- fund_performance.py: 类型列数据源从 `perf_data.get("type")` 改为 `classify_penetration()` + 中文映射
- fund_performance.py: 获取失败的空行也标注基金类型，而非占位符 `"--"`
- market_value.py: `_determine_price_type` 移除未使用的 `is_qdii` 形参
- fetcher.py: 移除重复的 `import re`（顶层已有导入）
- main.py: 菜单 [2] 更新持仓缓存时不再写入 `daily_data.json`，改为直接更新单条 `price_{code}.json` 文件（由 `fetch_market_data` 自动完成）
- main.py: 菜单 [1] 不再写入 `fund_performance_cache.json`、`fund_holdings_cache.json` 合并文件，改为依赖 `fund_perf_{code}.json`、`fund_hold_{code}.json` 单条缓存
- main.py: 菜单 [1] 步骤合并为 2 步（原 3 步），移除 `perf_collected`/`bm_collected` 等死代码
- main.py: HTML 占位菜单版本号更新至 0.2.2
- requirements.md/README.md: 模块 5 列名修正为"持仓累计盈亏(¥)"/"持仓收益率"，缓存文件表移除 `fund_benchmarks.json` 重复项

### Removed
- `daily_data.json` 缓存文件废弃，不再生成（价格数据存于 `price_{code}.json` 即可）
- `fund_performance_cache.json` 缓存文件废弃，不再生成（业绩数据存于 `fund_perf_{code}.json` 即可）
- `fund_holdings_cache.json` 缓存文件废弃，不再生成（持仓数据存于 `fund_hold_{code}.json` 即可）

### Bug Fixes
- category.py: `_apply_profit_colors` 缺少对收益率列 (8) 的着色（已补充）
- fund_performance.py: 移除未使用的 font 导入（NORMAL_FONT, RED_FONT, GREEN_FONT, BOLD_FONT, FMT_PERCENT）

## [0.2.1] - 2026-06-27

### Added
- TUI 菜单新增 [1] 更新基础缓存信息（主动获取基金业绩/持仓/基准并写入缓存文件）
- TUI 菜单新增 [2] 更新持仓相关缓存信息（主动获取价格/指数/穿透数据并写入缓存文件）
- 穿透模块新增 `compute_penetration_top10()` 纯计算函数（不依赖 openpyxl），返回结构化的可序列化缓存数据
- 缓存模块新增 `clear_by_prefix(prefix)` 方法，按前缀批量清除缓存
- 基础缓存命令实际调用 API 获取数据后写入合并缓存文件（`fund_performance_cache.json`、`fund_holdings_cache.json`）
- 持仓缓存命令实际调用 API 获取价格/指数后写入 `portfolio_latest.json`、`penetration_cache.json`、`daily_data.json`
- 穿透分类新增精细化识别（QDII/ETF/场外联接/债券基金/主动权益/直接股票/忽略）
- 穿透来源列标注基金类型标签（`[QDII]`、`[ETF]`、`[联接]`、`[债券]`、`[权益]`）
- 穿透底部统计按类型细分（如 `QDII2 + ETF3 + 联接1`）
- 穿透单元测试 `src/test_penetration.py`（40 项测试，覆盖全部分类分支和合并排序逻辑）
- 管理文档全面审计，更新 README.md/requirements.md/testplan.md 与代码实际行为同步

### Changed
- "生成全系列报告" 快捷键从 B 改为 A（避免与基础缓存冲突）
- README.md：版本号更新至 0.2.1，新增缓存文件说明章节，菜单/目录结构同步最新代码
- requirements.md：基金业绩列数修正为 9 列（与实际代码一致），缓存策略章节重写为缓存文件清单+TTL常量表
- testplan.md：更新单元测试覆盖要求，增加穿透分类和缓存刷新模块的测试重点

### Bug Fixes
- penetration.py: 移除废弃的 `_get_penetration_category` / `_count_failed_funds` 函数
- penetration.py: `write_penetration_sheet` 重构为调用 `compute_penetration_top10`，消除代码重复
- main.py: 缓存命令不再写入空占位，改为实际获取完整数据并写入指定缓存文件名

## [0.2.0] - 2026-06-27

### Added
- 分类汇总模块 `src/report/category.py`（按资产属性 + 投资分类分组统计）
- 资产穿透 TOP10 模块 `src/report/penetration.py`（合并基金底层持仓，全仓前 10）
- 基金业绩分析模块 `src/report/fund_performance.py`（同类排名、区间收益、评级标签）
- 报告包标记 `src/report/__init__.py`，供应商包标记 `src/providers/__init__.py`
- `docs-stm/plan/` 目录，存放计划文件

### Iter 2 — 分类汇总 + 资产穿透 TOP10 + 基金业绩分析 ✅ 已完成
- 分类汇总模块 `src/report/category.py`（股票/债券/基金/现金资产属性分组 + 主动/被动/固收投资分类分组，计算各类小计）
- 资产穿透 TOP10 模块 `src/report/penetration.py`（每只基金拆解前 10 持仓，合并相同标的+直接持股，按市值降序取全仓前 10）
- 基金业绩分析模块 `src/report/fund_performance.py`（调天天基金 API 获取同类排名和区间收益，按排名百分位打标签：优秀/良好/稳定/偏差）
- `main.py` B 选项和 E 选项接入 3 个新页签（分类汇总 → 资产穿透 TOP10 → 基金业绩分析）
- 首次 Iter 2 完整验证：5 个页签全部生成，10 条持仓完整走通

### Bug Fixes
- **tencent.py**: 修复 `FIELD_MAP` 中 `昨日价`（昨收盘价繁体/简体）列名匹配问题，简体"昨收盘"无法匹配 API 返回的繁体"昨收盤"键
- **tencent.py**: 修复 `_add_prefix` 中 5xxxxx ETF（561910/518880）前缀缺失问题
- **fetcher.py**: 重构取价策略，先尝试腾讯财经（所有代码）→ 失败回退东方财富净值，消除前缀猜测依赖
- **market_value.py**: 修复本日盈亏计算逻辑，场内/场外区分处理

### Changed
- `data/config/` 目录生效，配置路径从 `data/cache/config.json` 迁移至 `data/config/config.json`
- 启动脚本（launch.ps1 / launch.sh）增加 `data/config/` 目录创建
- 管理文档文件从 `~/.claude/plans/` 迁移至 `docs-stm/plan/`
- 文档全量审计，修复 CLAUDE.md/README.md/plan.md/requirements.md/testplan.md/changelog.md 中的不一致

### Planning
- Iter 3 拆分为 4 个子迭代（3.1 HTML 引擎 → 3.2 新闻关联 → 3.3 占位模块 → 3.4 LLM 接入）

## [0.1.0] - 2026-06-26

### Added
- 项目初始化，创建目录骨架
- 需求文档 `docs-stm/managements/requirements.md`
- 实现计划 `docs-stm/managements/plan.md`
- 质量标准与测试计划 `docs-stm/managements/testplan.md`
- 自我审查问题记录 `docs-stm/managements/review-findings.md`
- 本变更日志 `docs-stm/managements/changelog.md`
- 管理文档统一移至 `docs-stm/managements/` 目录
- 软件使用说明 `docs-stm/README.md`
- 代码配置文件 `CLAUDE.md`
- 示例持仓数据 `data/holdings/个人投资持仓信息.xlsx`

### Iter 1.1 — 项目骨架 + 配置管理 ✅ 已完成
- Python 包标记 `src/__init__.py`
- 配置管理模块 `src/config.py`（读写 `data/cache/config.json`，JSON 损坏容错）
- 日志模块 `src/logger.py`（控制台 + 文件双输出，防重复 handler）
- 依赖清单 `requirements.txt`（openpyxl, httpx）
- Windows 启动脚本 `scripts/launch.ps1`（自动 venv + pip install + 目录创建）
- Linux 启动脚本 `scripts/launch.sh`（同上）

### Iter 1.2 — 持仓读取 + TUI 菜单 ✅ 已完成
- 持仓数据结构 `src/models.py`（Holding dataclass）
- xlsx 解析器 `src/reader.py`（多工作表、表头校验、空行跳过）
- TUI 主菜单 `src/main.py`（6 选项 input() 循环，文件选择，配置管理）
- 键盘输入模块 `src/tui.py`（跨平台 msvcrt/termios 封装）
- 主菜单增强：方向键 ↑↓ 导航 + Enter 确认 + 默认选中第一项 + Ctrl+C 退出
- 修复 Windows 终端 GBK 编码兼容性问题（emoji/¥ → ASCII 替代）
- 修复 `scripts/launch.ps1` 路径问题（`Set-Location $projectRoot`）

### Bug Fixes (代码审查后修复)
- **reader.py**: try/finally 保护 workbook 资源释放；try/except 捕获 xlsx 损坏异常；精确行号追踪错误位置；份额/成本缺失时警告并跳过行；修复 `cell.value or ""` 吞掉数值 0 的问题
- **tui.py**: Linux 上 Ctrl+C 正确返回 KEY_CTRL_C；ESC 序列读取增加 150ms 超时（防单按 ESC 阻塞）；Windows 兼容 `\x00` 扩展键前缀
- **main.py**: 全部 `input()` 调用增加 EOFError 保护；入口处 `os.chdir(_project_root)` 保障相对路径；`_config_cache` 减少重复文件 I/O；顶层 KeyboardInterrupt 兜底退出

### Iter 1.3 — 数据源接入 + 缓存管理 ✅ 已完成
- 泛用 JSON 缓存模块 `src/cache.py`（get/set/clear，按秒过期，7 个缓存文件频率常量）
- 腾讯财经 API 封装 `src/providers/tencent.py`（`qt.gtimg.cn`，自动加 sh/sz 前缀，~ 分隔符解析）
- 东方财富 API 封装 `src/providers/eastmoney.py`（`api.fund.eastmoney.com` 获取净值，天天基金 fundf10 备用链路）
- 数据获取路由 `src/fetcher.py`（代码前缀自动识别股票/基金，先读缓存再调 API，缓存失败静默降级）
- API 联调验证：股票(600900=26.65)、ETF(159222=1.132)、场外基金(011506=2.1717)、QDII(017730=4.9361)、债券(012325=1.1351)

### Iter 1.4 — 汇总 + 市值核算 + Excel 输出 ✅ 已完成
- 样式常量 `src/report/styles.py`（正数红色/负数绿色字体，表头/小计/总计填充色，数字格式）
- Excel 输出引擎 `src/report/excel_writer.py`（标题行/表头行/数据行/小计/总计，列宽自适应，冻结首行，双路径保存最新+存档）
- 汇总模块 `src/report/summary.py`（统计时间、总市值/成本/盈亏/收益率/本日盈亏）
- 市值核算模块 `src/report/market_value.py`（15 列明细表，分账户小计+总计，盈亏红绿着色）
- 修正 `tencent.py` `_add_prefix` 缺失 5xxxxx ETF 前缀（561910/518880 等 ETF 正确取价）
- 重构 `fetcher.py`：先尝试腾讯财经（所有代码）→ 失败回退东方财富净值（消除前缀猜测依赖）
- `main.py` E 选项接入真实 Excel 生成（读持仓 → 取行情 → 写市值核算 → 写汇总 → 保存 reports/）
- 首次生成验证：15 条持仓，2 个页签，总市值 51.8 万，总盈亏 +24.5 万

### 配置更新
- 配置文件路径从 `data/cache/config.json` 迁移至 `data/config/config.json`
- 启动脚本（launch.ps1 / launch.sh）增加 `data/config/` 目录创建
- README 同步更新配置路径说明
