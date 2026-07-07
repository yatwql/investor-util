# 个人投资分析报告生成小助手 - 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Changed



---

## [0.2.91] - 2026-07-08

### Added

- **config.json 分组注释**：首次启动生成的 `config.json` 使用 `//` 注释分为 5 组（A.路径与文件 / B.数据源与提供商 / C.市场时段与缓存 / D.行为调优 / E.业绩基准），用户编辑时一目了然。
- **config.json 注释支持**：`get_config()` 读取时自动剥离 `//` 和 `/* */` 注释，`config.json` 从此支持内联注释，与 `llm_settings.json` 行为统一。

### Changed

- **`_DEFAULT_CONFIG` 字段顺序重排**：按业务分组（路径/数据源/市场时段/行为调优/业绩基准），与带注释模板一致。
- **how-to-config.md 同步**：JSON 示例重写为分组注释版；字段说明表顺序与分组对齐，新增 `degradation` 行和独立章节。

### Fixed

- **`industry` 缓存 TTL 文档不同步**：`how-to-config.md` cache_ttl 表写为 `7 天`，代码 `registry.py` 已是 `14 天`（D-4.5 优化），`technical.md` 同理。三处统一为 14 天。
- **`_KNOWN_PROVIDER_NAMES` 缺少 `eastmoney_industry_rest`**：用户配 `"industry": "eastmoney_industry_rest"` 时误报 WARNING，已补入验证集合。
- **`_DEFAULT_CONFIG` `news_top_count` 不一致**：代码为 `100` 但文档写 `300`，经确认推荐值为 `300`，代码改为 `300` 与文档对齐。

### Docs

- **用户手册内部核对**（6 份）：how-to-start.md 方向键操作表新增 `### 键盘操作` 子标题；reports-instruction.md `# 基金业绩评价标准` H1→H2 降级；其余 4 份无调整。
- **how-to-config.md 完整审计**：3 项文档错误修复（industry TTL / degradation 缺失 / 字段表顺序），1 项代码缺陷修复（`_KNOWN_PROVIDER_NAMES`）。

---

## [0.2.90] - 2026-07-08

### Added

- **D-7a：B 系列模块空态占位** — 基金经理变更监控/持仓重合度矩阵/持仓集中度监控/基金风格分析 4 模块在数据为空时不再隐藏页签，改为显示占位文本（来自 `STATUS_MESSAGES` 常量）。`excel_generator.py` 中 B 系列 4 模块改为无条件调用 sheet 写入函数（空数据由 sheet 层自行判断写占位）。HTML 模板同步新增 `empty-section` CSS 类 + 4 模块有条件渲染占位块。
- **D-7b：新闻模块降级 + source_status 追踪** — `news_aggregator.py` 新增 `_last_src_results` 模块级字典 + `get_last_source_status()` 函数，按 `{source_key: {"label", "success", "count", "error"}}` 格式追踪各源拉取结果。`news_correlation.py` 的 `build_news_data()` 提取 `source_status` 注入 `info` 字典；`_build_news_footer()` 在部分源失败时底部列出失败源清单。全源失败时 `write_news_sheet()` 写入 `STATUS_MESSAGES["news_all_failed"]` 占位文本。
- **D-7b 配套：预警模块空态占位** — `early_warning.py` 增加 `None`/空数据容错，行业预警表缺数据时显示"暂无预警数据"，新闻情绪聚合表缺数据时显示"暂无新闻情绪数据"（来自 STATUS_MESSAGES 常量）。
- **akshare Phase 2：持仓分类表分红降级 + _data_status** — `category.py` 新增 `_build_category_data_status(dividend_success)` 和 `_write_data_status_foot()` 调用，分红数据加载失败时在持仓分类表页脚追加状态摘要。`html_builders.py` 的 `_build_category_data()` 返回类型从 `list` 改为 `tuple[list, bool]`，通过 `dividend_success` 追踪 API 异常和空返回两种失败场景。`html_writer.py` 集成 `_build_category_data_status`、`_safe_build_data_status`、`data_status_category` 模板上下文。`report_template.html` 新增 `{{ render_data_status(data_status_category) }}` 条件渲染。
- **D-8：全链路回归基线锁定** — 新增 `test_excel_generator_edge.py`（全局降级冒烟 2 条 + 消息一致性 8 条测试）、`test_fund_bseries_sheet_edge.py`（B 系列 4 模块空数据占位 6 条测试），覆盖所有降级路径的消息一致性验证。
- **新闻降级边缘测试**：新增 `test_news_degradation_edge.py`（7 项测试）覆盖全源失败占位/部分失败"暂无"/source_status 兜底/页脚失败源列表等场景。
- **预警空态边缘测试**：新增 `test_early_warning_edge.py`（5 项测试）覆盖行业/新闻两表缺数据时的占位文本断言。
- **HTML 构建器降级测试**：`test_html_builders.py` 和 `test_html_builders_edge.py` 更新 `_build_category_data()` 的 `(list, bool)` 返回类型断言，新增 `dividend_success` 状态验证。

### Fixed

- **`llm_max_concurrency` 配置键未注册**：`llm_settings.json` 中的 `llm_max_concurrency` 键未在 `get_known_llm_settings_keys()` 中登记，导致 `test_all_keys_tracked` 断言失败。修复：在 `registry.py` 的全局键名集合中加入 `"llm_max_concurrency"`。
- **缓存测试 `test_cache_sharing_between_fetcher_and_market_value` 跨日新鲜度校验干扰**：`_price_cache_fresh` 因 `price_date` 早于交易日判定跨日残留并清空缓存，导致 patch provider 不生效（`_PRICE_PROVIDERS` 持有 import 时的函数对象直接引用）。修复：改用 mock `_price_cache_fresh` 返回 True 直接命中缓存。
- **基金风格分析 `UnboundLocalError`**：`_tencent_failures` 模块级变量在 `classify_fund_style` 内被赋值（`+=1`/`=0`）但缺少 `global` 声明，导致首次 push2 请求失败→触发 Tencent 备用链路时报 `cannot access local variable '_tencent_failures'`。修复：添加 `global _tencent_failures` 声明。
- **HTML 结构测试 7 条已存在失败（D-8 修复）**：`report_template.html` 页脚 div 使用 `class="section"` 导致 `div.section` 选择器匹配 17 个元素（期望 16），尾部 section 缺 id/order 属性触发 HTML 结构验证失败。修复：页脚 div `class="section"` → `class="report-footer"`，新增 `.report-footer` CSS 类（base/mobile/print 三段式），使其不被 `div.section` 选择器匹配。
- **基金风格分析 3 条测试已存在失败（D-8 修复）**：`TestClassifyFundStyle` 中 `test_push2_fallback_to_tencent`/`test_weighted_style`/`test_with_push2_data` 因 `_ext_memo` 模块级缓存污染跨测试用例而失败——`test_no_push2_fallback_code` 先运行并缓存 `"600519": None`，后续测试读取缓存结果而非执行 mock 函数，导致 `is_estimated` 断言不符。修复：`TestClassifyFundStyle.setUp()` 中添加 `_ext_memo.clear()`。
- **回归测试 2 条因价格缓存新鲜度校验引发失败**：`test_datetime_scenarios.py::TestFetchMarketDataMarketAware` 中 `test_fetch_price_calls_get_ttl`/`test_get_ttl_called_with_price` 断言 `get_ttl("price")` 仅调用 1 次，但 v0.2.89 新增 `_price_cache_fresh` 跨日残留检测在缓存无 `price_date` 时触发第二次 `get_ttl("price")` 调用。修复：断言改为 `call_count=2` + `assert_any_call("price")`。

## [0.2.89] - 2026-07-06

### Added

- **收市后价格缓存新鲜度校验**：盘后首次请求时校验缓存 `price_date` 是否为当前交易日，消除盘中 Tencent 降级 EastMoney 导致的跨日陈旧价格残留（ETF 类产品收盘价缺失问题）
- **CLAUDE.md 发布版本标签约定**：发布版本时必须打 `git tag v{版本号}` 并推送

### Changed

- `news_top_count` 缺省配置 100 → 300，同步更新配置示例和文档

### Fixed

- **`news_top_count` 配置不生效（各源始终只取 100 条）**：`build_news_data()` 调用 `aggregate_news()` 仅传 `top_n`，未传 `per_source`，后者默认硬编码为 100。即使 `news_top_count=300`，各源仍只取 100 条。修复：传 `per_source=max(500, news_top_count × 2)` 保障召回，最终按关联度截取 `news_top_count` 条输出。同步更新 `requirements.md`、`technical.md`、`how-to-config.md` 说明召回策略。
- **基金风格分析跳过日志**：无持仓数据的基金（如黄金 ETF）被跳过时补充 debug 日志，消除 12→11 数量疑问

## [0.2.88] - 2026-07-06

### Changed

- **文档审计（10 文档）**：全量核对代码与实际行为，修正 12+ 处过期/错误描述
  - `how-to-config-llm.md`：`thinking_budget` 描述修正
  - `faq.md`：3 处内部链接修复
  - `requirements.md`：`2025E` → `2026E`、LLM 模块数修正、版本标记清理
  - `reports-instruction.md`：`2025E` → `2026E`
  - `technical.md`：`tui_handlers.py` 职责描述修正、chain.py 补入调度表
  - `how-to-start.md`：智能预警脚注修正、函数名中文化
  - `how-to-config.md`：`fund_overlap` 缓存描述修正、`cache_ttl` 按逻辑分组重排
  - `README.md`：移除不存在的"TUI 智能摘要"特性、"多源备线" → "多数据源自动 fallback"
  - `datasource-and-folders.md`：目录树补入 7 个缺失测试文件 + 1 个归档文件，测试计数全面更新
  - `test-coverage.md`：全量 2454 → 2572，所有 mode/分组/跨类标记同步更新
- **CLAUDE.md**：门禁描述移除快照项数，避免版本迭代过期
- **配置文件同步**：`data/config/config.json` 的 `cache_ttl` 按逻辑分组重排
- **代码同步**：`penetration.py`/`penetration_sheet.py` 中 `2025E` → `2026E`

### Removed

- `docs-stm/plan/notes/data-source-pre-study.md`：已归档至 `docs-stm/archive/archived-data-source-pre-study.md`

## [0.2.87] - 2026-07-06

### Added

- **B 迭代（基金持仓深度分析）全模块上线** — 新增 4 页签（13~16）：
  - **基金经理变更监控（B2）**：`src/python/report/fund_manager_analysis.py` + `fund_manager_sheet.py` — 快照式变更检测（1/3/6 月窗口），独立快照键 `fund_manager_snapshot`（不受持仓指纹影响），首次运行引导文案
  - **持仓重合度矩阵（B3）**：`src/python/report/fund_overlap.py` + `fund_overlap_sheet.py` — Jaccard + Overlap Ratio 双指标，热力图矩阵，含/不含市值数据双模式
  - **持仓集中度监控（B4）**：`src/python/report/fund_concentration.py` + `fund_concentration_sheet.py` — 前3/5/10集中度，环比变化+三级预警，独立快照键 `fund_concentration_snapshot`
  - **基金风格分析（B5）**：`src/python/report/fund_style_analysis.py` + `fund_style_sheet.py` — 六宫格风格箱（大盘/中盘/小盘×价值/混合/成长），三级降级链路（push2→Tencent→代码段估算），网格曼哈顿距离漂移检测，独立快照键 `fund_style_snapshot`
- **基金经理数据获取模块**：`src/python/fetcher/fund_manager.py` — 天天基金主页 HTML 解析 + 档案页回退
- **Tencent 扩展字段（市值/PE）**：`src/python/providers/tencent.py` — 新增 `market_cap`(f46) 和 `pe`(f40) 字段
- **TUI 菜单描述同步**：B/L 菜单标注「含基金深度分析」，[1] 菜单描述含基金经理缓存
- **测试覆盖**：B 系列 6 个测试文件共 ~115 项（fetter fund_manager 14 项 + report 模块 101 项）

### Fixed

- **R-158：Excel "LLM API 用量" 页签未显示模块明细**：

- **R-158：Excel "LLM API 用量" 页签未显示模块明细**：
  - `excel_generator.py`：`_build_llm_usage_sheet` 中 `per_module` 从 `formatted` 取改为从 `raw_session` 取
  - 根本原因：`format_session_usage` 在特定状态返回 `{"has_usage": False}`（不含 `per_module` 键），导致 `formatted.get("per_module", {})` 返回空字典，进而 `excel_module_info` 为空、函数提前返回，页签无数据
  - 修复：优先从始终含 `per_module` 的 `raw_session` 读取数据，`formatted` 作为降级回退
  - 新增回归测试 `test_raw_session_per_module_fallback`

- **R-156：push2 行业数据频繁 "Server disconnected" 容错增强**：
  - `eastmoney_industry.py`：重试次数 1→3（4 次总请求），指数退避（0.5s→1s→2s）+ 随机抖动 0.3s
  - `eastmoney_industry.py`：超时 10s→15s，增加随机/隐式导入
  - `industry.py`：`batch_fetch_industry_data` 新增批量级重试，首次失败后短暂等待（0.8s+抖动）重试一次
  - 对应更新测试 `test_us_stock_filtered_out` 断言（call_count 1→2）

- **R-159a：Provider Chain 熔断器线程竞争**：
  - `chain.py`：`batch_fetch_industry_data` 多线程（`ThreadPoolExecutor(max_workers=3)`）同时写入 `_PROVIDER_CONSECUTIVE_FAILURES`，无锁覆盖导致熔断计数器永远达不到阈值
  - 修复：新增 `_PROVIDER_LOCK = threading.Lock()`，所有读写操作线程安全

- **R-159b：A 股代码判定修复 — 250361 基金代码误入行业链路**：
  - `industry._is_a_share_code`：从仅检查"6 位数字"升级为前缀区间检查（60/68/00/30/8），基金代码（250361 等）不再被误判为 A 股
  - 250361 不再触发东方财富 REST 行情页 404 错误

### Added

- **R-159c：代码类型判定中心化 — code_utils.py**：
  - 新增 `src/python/code_utils.py`：资产代码/名称类型识别唯一入口，集中管理所有前缀区间和名称关键词知识
  - 新增函数：`is_a_share_code`、`is_fund_code`、`is_stock_like_code`、`is_exchange_fund_code`、`is_hk_stock_code`、`get_exchange_prefix`、`get_push2_secid`、`is_qdii_by_name`、`is_etf_by_name`、`is_bond_related_by_name`、`is_index_link_by_name`
  - 全量迁移 12 个调用方：`fetcher/industry.py`、`providers/eastmoney_industry.py`、`providers/eastmoney_industry_rest.py`、`providers/tencent.py`、`providers/akshare_extras.py`、`report/penetration.py`、`report/category.py`、`report/market_value.py`、`report/fund_performance.py`、`report/penetration_sheet.py`、`llm/prompts.py`
  - 删除 4 个重复的内部函数：`penetration._is_bond_fund`、`penetration._is_index_link`、`market_value._is_qdii`、`market_value._is_etf`
  - `llm/prompts._is_qdii` 委托至 `code_utils.is_qdii_by_name`
  - `CLAUDE.md` + `technical.md` 添加"代码类型判定中心化"约束

- **R-157：push2 全线不可用时 fallback 链路 — eastmoney_industry_rest**：
  - 新增 `src/python/providers/eastmoney_industry_rest.py`：行情页 HTML scraped 备用链路，解析 `quotedata.bk_name`（行业名称）/ `bk_id`（行业 BK 代码）
  - `chain.py`：`industry` 链扩展为 `["eastmoney_industry", "eastmoney_industry_rest"]`
  - `industry.py`：注册 `eastmoney_industry_rest` 到 provider 映射表
  - 新增测试 13 项：`_quote_prefix`（5 类代码前缀）、`_extract_quotedata`（4 场景）、`fetch_industry_and_concepts`（3 场景，含 mock HTTP 异常）
  - 注意：概念板块数据依赖 push2 XHR 动态加载，fallback 仅提供行业分类，概念列表留空（graceful degradation）

## [0.2.86] - 2026-07-05

### Fixed

- **C-P1b：Excel 页签标题跟随用户 `report_section_order` 配置**：
  - `registry.py`：`set_sheet_title()` 扩展接收 `section_order: list[dict] | None` 参数，优先从配置取 number，未命中时回退默认值
  - `excel_generator.py`：`_create_sheets()` 传入 `section_order`，新增 `section_order` 参数到 `generate_excel_report()` → `_write_llm_section_and_usage()`
  - 11 个 sheet 写入器移除冗余 `set_sheet_title()` 调用，标题统一由 `_create_sheets()` 设置
  - `llm_content.py`：`_get_module_key_map()` 移除模块级缓存 `_MODULE_KEY_MAP`，改为每次按 `section_order` 动态构建；`_get_placeholder()`、`_write_content_sheet()`、`write_llm_sheets()` 均接收并传递 `section_order`
  - `html_writer.py`：`write_html_report()` 接收 `section_order` 参数，内部传递至模板渲染
  - `handlers_report.py`：4 条命令函数（`_cmd_generate_excel` / `_cmd_generate_html` / `_cmd_generate_both` / `_cmd_generate_full`）从 config 读取 `section_order` 传入生成管线
  - 新增测试 16 项（llm_content 10 + scenario 6），回归验证 906 项通过

## [0.2.85] - 2026-07-05

### Added

- **C 迭代：报告序号可配置（4 Phase）**：
  - **C-P1a：注册表 + 配置校验** — `registry.py` 新增 `_REPORT_SECTION_DEFAULT` 注册表（16 模块/4 种 visibility）、`get_report_section_order()`（配置合并/缺省回退/稳定排序）、`set_sheet_title()`（Excel 页签统一命名）、`get_report_section_keys()`（key 集合查询）；`config.py` 新增 `validate_report_section_order()` 校验（重复序号/未知 key/零值）；`html_writer.py` 新增 `_jinja_section_visible()` + `section_visible_dict`（模板层条件渲染入口）。新增测试 31 项（registry 21 + config 10），含 edge 场景专项覆盖
  - **C-P1b：Excel 全链路集成** — `excel_generator.py` `_create_sheets()` + 11 个写入器页签标题统一使用 `set_sheet_title()`；新增 `report_section_order` 配置读取与排序逻辑
  - **C-P2：HTML 全链路重构** — `html_writer.py` `_write_html_report()` 按 `report_section_order` 动态渲染；`_ENV.globals` 注册 `section_visible` Jinja2 全局函数；`report_template.html` 导航栏/正文均使用 `{% for sec in report_section_order %}` 循环 + `section_visible(section.key)` 条件渲染；CSS order 统一管理
  - **C-P3：文档更新** — `requirements.md` 补充报告序号可配置需求；`technical.md` 新增 C 迭代技术设计章节（注册表结构/4 种 visibility/section_visible_dict/CSS order/Jinja2 全局函数）；`how-to-config.md` + `config.json` 示例补充 `report_section_order` 配置说明；`datasource-and-folders.md` 目录树补充 registry.py；`test-coverage.md` 计数同步（单元 1990→2137，全量 2353→2384）
  - `llm_usage` 固定末位机制；未配置模块按默认顺序排后；`b_series` 类型的 4 个模块通过 `enable_b_series` 控制可见性

### Changed

- **模块命名统一**：`excel_generator.py` 函数名 `_write_fund_deep_sheets` → `_write_b_series_sheets`，与 `enable_b_series` 标志命名对齐

### Fixed

- **plan.md 优先级排序**：C 迭代计划经四轮审查优化后定稿（O11-O14 优化：核数减半/dirty 文件/决策回顾/依赖冲突）

---

## [0.2.84] - 2026-07-04

### Added

- **A5 Phase 1：pytest-xdist 并行执行**：`test_runner.py` MODES 新增 `parallel` 字段，`--parallel` 参数支持 high/medium/low 三档（缺省 medium=50%核数）；新增 `report` 模式（`unit_report` 675 项~15s）。`conftest.py` 零改动（无共享 fixture）。

### Changed

- **CLAUDE.md/plan.md/test-coverage.md 门禁耗时同步**：P1 verify 从~12min→~49s，P0 regression/~30s 不变，P2 all/~待测
- **A5 实施决策**：Phase 2 文件拆分跳过（unit 20s 无需拆分）、Phase 3 增量测试延期（全量够快无需增量复杂度）

### Fixed

- **资产穿透TOP10 基金伪穿透垃圾数据污染**（#O15）：天天基金 API 对华安黄金ETF(518880)返回了无效持仓数据——3 只财通基金代码以 ratio=401%/399%/359%（>100%）作为黄金 ETF 的"持仓"出现。穿透模块未验证 ratio 合法性，照单全收导致：
  - 不持有的基金出现在穿透 TOP10 中
  - 穿透市值 = fund_mv × 401% ≈ 4 倍基金市值放大
  - 报表合计穿透金额远超实际持仓总额

  修复双管齐下：
  1. `_merge_fund_layer` 新增 ratio 阈值校验：仅接受 `0 < ratio ≤ 100` 的持仓条目，明确非法数据直接过滤
  2. 若某基金的所有持仓条目均被过滤，计入 `unknown_mv`（统计信息）而非加入 merged 污染 TOP10（上一轮 fix 保留）

  新增回归测试 4 条（含精确复现 518880 场景的测试用例）。

## [0.2.83] - 2026-07-04

### Changed

- **Jinja2 autoescape 安全修复**：`html_writer.py` `_ENV` 启用 `autoescape=True`，4 个 LLM 内容变量（`global_macro`/`expert_review`/`health_check`/`penetration_deep`）显式使用 `|safe` 过滤器
- **conftest.py marker 描述同步**：`scenario`（S1-S20→S1-S33）、`scenario_basic`（S1-S5→S1-S33）、`scenario_datetime`（T1-T16→T21）三个标记描述与当前覆盖范围对齐
- **faq.md 5 处事实修正**：TTL 描述改为结构化列表（盘中30s/盘后24h/LLM 2h）；报告文件名修正（`report_*.xlsx`→`个人投资分析报告.xlsx`）；日志轮转说明纠正（保留7天每天备份→10MB按大小切割保留5份）；内存持仓表述澄清（"复用内存中的持仓数据"→"复用已获取的缓存数据"）
- **reports-instruction.md 措辞修正**：持仓概况"各账户小计"→"持仓概况分类计数（分账户小计详见市值核算明细表）"
- **testplan.md**：移除 §1.8 硬编码分组统计项数及 edge 文件行项数，测试覆盖改用"全量已覆盖"
- **how-to-test-my-code.md**：移除 3 处硬编码测试计数引用，统一指向 test-coverage.md 作为权威计数源
- **CLAUDE.md**：管理文档列表补充 `test-coverage.md`
- **test-coverage.md**：全量测试及分组计数与最新状态同步
- **版本号同步**：constants.py `APP_VERSION` 0.2.62→0.2.83，README.md 0.2.65→0.2.83，how-to-test-my-code.md/plan.md 同步至 v0.2.83（修复此前 20 个版本脱节）

### Added

- **test_security_edge.py 新增 4 项测试**：`test_template_autoescapes_html_tags`、`test_template_autoescapes_event_handler`、`test_money_filter_autoescape_safe`、`test_profit_color_filter_autoescape_safe`，验证 Jinja2 模板层自动转义生效

### Fixed

- **test_security_edge.py 测试更新**：`test_jinja2_autoescape_missing`→`test_jinja2_autoescape_enabled`，断言从 `assertFalse` 改为 `assertTrue`

---

## [0.2.84] - 2026-07-04

### Changed

- **pyproject.toml 版本同步**：`version` 0.2.52→0.2.83，与 `constants.py` APP_VERSION 对齐（修复 31 个小版本脱节）
- **review-findings.md**：新增 R-148~R-153 审计项，R-148/R-153 已修复摘要留表，明细移入 changelog

### Fixed

- **12 处 `except Exception` 补充异常追踪**：`market_hours.py`（新增 `logger.warning`+`exc_info=True`）、`tui_handlers.py`、`providers/akshare_extras.py`（3 处）、`report/category.py`、`report/fund_performance.py`、`report/market_value.py`、`report/penetration_sheet.py`（2 处）、`report/penetration.py` — 确保非预期异常有完整 traceback

### Style

- **模板数字格式化统一**：`report_template.html` 中 8 处 `{{ "{:,}".format(value) }}` 替换为 `{{ value | thousands }}`，统一使用已有自定义 Jinja2 filter

---

## [0.2.63] - 2026-07-02

### Added
- **边缘场景测试增补（迭代 V）**：在执行已有 conftest.py 和测试框架基础上新增 6 个 `_edge.py` 文件和增强 2 个已有 `_edge.py`，共 19 个新测试用例，覆盖 cache 损坏恢复、API 异常数据、市场时段边界等边缘场景。

### Changed
- **错误提示优化**：所有直接暴露原始异常堆栈给用户的 `print(str(e))` 替换为友好中文提示，引导用户查看日志文件，避免恐慌
  - `_prepare_holdings` 异常改用 `_print_error_with_hint` 分类提示（`tui_handlers.py`）
  - `handlers_report.py` 中所有 `add_error`/`.error()` 调用用"详情请查看日志"替代原始 `{e}`
  - `progress.py` 中 `ProgressReporter.call_sheet` 和 `TuiProgressReporter.call_sheet` 的 `add_error` 同样用友好提示替代原始 `{e}`
  - `excel_generator.py` 中新闻/LLM/智能预警模块异常同样改为友好提示
- **`constants.py`**：`APP_VERSION` 0.2.61 → 0.2.62
- **`README.md`**：用户文档表增加"如何测试我的代码"链接

### Changed
- **pytest 标记层级体系**：原有 6 个扁平 marker 扩展为 15 个分层 marker
  - 场景测试：`scenario` 父标记 → `scenario_basic`（S1-S5, 9 项）/ `scenario_extended`（S6-S10, 18 项）/ `scenario_llm`（S11-S20, 19 项）/ `scenario_datetime`（T1-T16, 61 项）— 子标记总和 = 107，父标记匹配全部
  - 单元测试：`unit` 父标记 → `unit_providers`（166 项）/ `unit_fetcher`（118 项）/ `unit_llm`（331 项）/ `unit_news`（176 项）/ `unit_report`（558 项）/ `unit_config`（42 项）/ `unit_core`（277 项）/ `unit_ui`（142 项）— 子标记总和 = 1810，父标记匹配全部
  - 跨类标签：`llm` 同时覆盖 `unit_llm`（331 项）+ `scenario_llm`（19 项），`-m "llm"` = 350 项
  - `conftest.py` 注册全部新 markers，docstring 更新分层树
  - `scripts/test_runner.py` MODES 字典新增 `integration` 模式
- **测试文件目录分组搬迁**：60 个测试文件从扁平 `src/test/` 按标记分组迁入子目录
  - `src/test/unit/{providers,fetcher,llm,news,report,config,core,ui}/`（8 组，56 文件）
  - `src/test/scenario/{basic,extended,llm,datetime}/`（4 组，4 文件）
  - `conftest.py` / `helpers.py` 保留在根级共享
  - 所有 `from src.python.*` 导入不受影响，0 处路径断裂
- **`datasource-and-folders.md`**：目录树全面更新为新分层结构
- **`how-to-test-my-code.md`**：单文件运行路径示例改为新子目录路径
- **`how-to-use-registry.md`**：test_registry.py 路径同步更新
- **`testplan.md`**：示例命令路径同步更新
- **`plan.md`**：新增 T. 测试标记与目录分组已完成迭代条目

### Added
- **冒烟测试 `smoke` 标记（24 项）**：从核心数据模型、入口读取、分类计算、报告输出、启动依赖、数据获取 6 个关键节点各选 4 项最快基础测试，分配 `@pytest.mark.smoke`。`-m "smoke"` 可在 ~2s 内验证核心通路。涉及文件：`test_models.py`、`test_reader.py`、`test_category.py`、`test_excel_generator.py`、`test_config.py`、`test_eastmoney.py`。
- **LLM 测试 API Key 审计**：确认全部 350 项 `llm` 标记测试（unit_llm 331 + scenario_llm 19）均为 mock 测试，无需真实 API key。`how-to-test-my-code.md` 新增逐文件 mock 分析表。

### Changed
- **`test_runner.py` MODES 字典 order 修复**：scenario/regression 重复 order=3 修复为各模式唯一值（regression=4→verify=5→integration=6→edge=7→data=8→all=9）；新增 `smoke` 模式（order=10，marker="smoke"）
- **全量文档一致性审阅**：`datasource-and-folders.md` 标记数 15→19、`cls_news`→`cls` 配置修正；`faq.md` 过时引用修正；`how-to-test-my-code.md` 完整更新（三级流水线、10 模式表、smoke 明细、LLM mock 分析）；`plan.md`/`technical.md`/`review-findings.md` 标记计数 15→19；`plan.md` S 节模式列表同步

### Fixed
- **🐛 首批标记插入脚本损坏 6 个测试文件**：脚本 `last_import_idx` 错误匹配方法体内的 `import httpx`，将 `import pytest` / `pytestmark` 插入到测试方法体中（test_eastmoney_industry.py:244、test_sina_news.py:193、test_tencent.py:228 等）。修复：写 `fix_markers.py` 用 AST 验证替换，删除所有误插标记并正确插入模块级位置。全量 1938 测试收集恢复。
- **`test_tui_handlers.py::TestPrintErrorWithHint`**：修正两个测试断言，验证友好提示而非原始异常文本
- **`test_excel_generator.py::test_sheet_exception_isolation`**：修正断言验证友好提示格式，增加"不暴露原始异常类型"断言

---

## [0.2.61] - 2026-07-02

### Changed
- **`plan.md`**：R 测试覆盖增补三期（数据正确性 + 异常场景 + 测试文件治理）从"待实现方向"移入"✅ 已完成迭代"；原 R 节详细规格删除（已归档至 changelog.md）；S 测试报告系统标记为 🟡 暂停中并注明进展
- **`constants.py`**：`APP_VERSION` 0.2.59 → 0.2.61（同步 v0.2.60 遗漏的版本号更新）

### Added
- **`src/test/conftest.py`**（新建）：注册 6 个 pytest marker（scenario/llm/datetime/edge/smoke/data），支持组合筛选运行
- **`docs-stm/manuals/how-to-test-my-code.md`**（新建）：用户文档，覆盖 CLI 用法、marker 选择、报告查看、常见问题
- **`src/test/test_market_value_edge.py`** 新增 22 项异常场景测试：
  - `TestCountTradingDaysBack`（8 项）：交易日计数回退边界（同日/隔日/跨周末/超 60 天/未来/无效日期）
  - `TestDeterminePriceTypeNavGap`（10 项）：净值空窗期价格类型（T 到 T-5 及更久/3 个月/未来）
  - `TestDeterminePriceTypeSessionSwitch`（4 项）：交易时段切换取价（11:29:59→11:30:00→14:59:59→15:00:00）
- **`src/test/test_cache.py::TestGetTTLMarketHourAware`**（10 项）：市场时段感知 TTL（开盘短 TTL 30s/闭市长 TTL/类型非感知/配置缺失/无效值）
- **pytest marker 标注**：6 个测试文件添加 `@pytest.mark.data` 或 `@pytest.mark.edge`

### Fixed
- **test_category.py 6 项断言错误**：期望值未对齐中文简标签（"被动指数"→"指数"、"主动管理"→"主动"、"股票"→"A 股"）；`test_single_holding` 使用 dict 而非 `DetailRow` 对象
- **test_fetcher_index.py 迭代 bug**：`for item in result` 遍历 dict keys（字符串）而非 `result.values()`
- **test_market_value_edge.py `trading_day` 缺失**：`price_update_status([detail])` 缺少第二参数
- **test_qdii_timezone.py 5 项**：4 处 `price_update_status` 缺少 `trading_day` 参数；HK 基金名称应含 `(QDII)` 后缀以被 `_is_qdii()` 识别
- **test_fund_performance.py `_calc_fund_scores` 不存在**：重写为 `write_fund_performance_sheet` 集成测试；`_format_rank` 补充 `rank is None`/`total is None` 检查
- **test_cache.py patch 目标错误**：`cache.get_config` → `config.get_config`（`get_config` 在函数体内导入）

### Tests
- 修复 20 项数据正确性测试缺陷
- 新增 42 项测试（异常场景 22 + cache TTL 10 + conftest.py 基建）
- 全量 1900+ 测试通过
- `test-coverage-map.md` 总量 36→40 条目（NAV 空窗期 ✅、QDII 多时区 ✅、交易时段切换 ✅、cache TTL ✅）

---

## [0.2.60] - 2026-07-02

### Changed
- **`plan.md`**：Q（日期/时间数据获取场景测试）从"待实现方向"移至"✅ 已完成迭代"；Q 实施发现的 4 个新功能需求归并入 R 迭代范围；新增 R 子方向"测试文件治理"（文件拆分/pytest 标记/验证脚本）
- **`testplan.md`** 全量审阅修订（§1.4/§2/§3/§4/§6/§7 重写或扩充）：
  - §1.4 集成测试：6 条模糊描述 → 11 条维度化清单 + 覆盖状态
  - §2 数据正确性验证：10 项 → 16 项（新增三维度聚合/行业占比/指数合理性等）
  - §3 UI/UX 验证：6 项 → 20 项（新增打印样式/报告归档/首次引导等）
  - §4 回归测试清单：7 行 → 15 行 + P0/P1/P2/P3 语义定义
  - §5 迭代测试重点：34 行碎片 → 10 行快速索引
  - §6 Mock 策略：过期示例更新 + akshare/datetime/cache 模板
  - §7 验收标准：7 条 → 14 条四维门禁
  - 新增 §0 测试环境要求 / §9 新增测试指南
  - §1.2 标题+描述完善，明确"横切测试编写规范"定位
  - §1.3 新增文件范围说明表 + 场景间前置依赖列
  - §1.4 vs §1.5 去重，添加交叉引用
  - §1.7 从 40+ 行手动表格精简为汇总表，详细映射移至 `docs-stm/plan/test-coverage-map.md`
  - §4"57 文件"硬编码 → `pytest --collect-only` 动态统计
- **`scripts/validate_coverage_map.py`**（新建）：场景-测试文件覆盖率映射验证脚本，支持 `--summary` / `--update`

### Added
- **`docs-stm/plan/test-coverage-map.md`**（新建）：详细场景-测试文件覆盖率映射（从 testplan.md §1.7 拆分）
- **`scripts/validate_coverage_map.py`**：覆盖率映射验证脚本，扫描 `src/test/` 所有 Test 类并对比映射文件准确性

### Tests
- 全量测试文件数：59，测试类数：327
- `test_datetime_scenarios.py` 61 项（已计入 v0.2.59，此处仅确认）

### Fixed
- **🐛 `_handle_truncation` 丢弃 usage（R-145）**：`skeleton.py:171` 非截断路径下 `return result, None` 应改为 `return result, usage`。导致 `_finalize_and_cache` 中 `if usage:` 整个块被跳过，`_record_per_module()` 和 HTML 页脚 Token 信息均未执行。影响：LLM API 用量模块明细全部显示 `—`，各章节底部无"模型：X | Token 用量：..." 信息。修复：增加 `usage` 参数透传。
- **🐛 `news_correlation` 遗漏在 LLM 模块明细表（R-146）**：`excel_generator.py:281` / `html_writer.py:497` / `summary.py:325` 三处硬编码 `MODULE_KEYS = [4个模块]`，漏了 `"news_correlation"`。修复：三处均添加 `"news_correlation"`。同步修复 `html_writer.py:564` `module_disabled` 字典循环。
- **🐛 缓存模块 Token 显示为 `—`（R-147）**：HTML 模板 `report_template.html:893-896` 使用 `{% if _mi.total_tokens %}`，Jinja2 中 `0` 为 falsy，缓存模块 Token=0 时显示 `—`。修复：改为 `{% if _mi.status == "unknown" %}—{% else %}{{ ... }}{% endif %}`。
- **🐛 基金业绩"较差"评级颜色错误（深绿→浅绿）**：`fund_performance.py` 中"较差"评级误用 `GREEN_FONT`（#009900），与 footnote 承诺的"深绿"不符。HTML 模板 `report_template.html` 第 536 行**遗漏"较差"条件分支**，导致该评级单元格无任何颜色样式，保持默认黑色。修复：`styles.py` 新增 `DARK_GREEN_FONT`（#006400）；`fund_performance.py` 改为 `DARK_GREEN_FONT`；HTML 模板补齐 `{{ ' color: #006400; font-weight: 600;' if p['rating_tag'] == '较差' }}`。
- **🐛 `_write_module_data_rows` 缺少 `Border`/`Side` 导入**：函数内使用 `Border()` / `Side()` 但未导入，正常执行因 `write_llm_module_status_block` 先执行导入了这些符号而掩盖。独立调用时抛出 `NameError`。修复：函数内添加 `from openpyxl.styles import Border, Side`。
- **🐛 `test_mixed_cached_and_success` 断言错误**：测试 `assertNotIn("Extended Thinking", all_text)` 但 "智囊团深度复盘" 模块启用了 Thinking，`Extended Thinking` 正确出现在输出中。修复：改为 `assertEqual(all_text.count("Extended Thinking"), 1)` 精确计数。

### Added
- **`test_skeleton.py::TestHandleTruncation`**（3 项新测试）：非截断保留 usage、None 保留 usage、空字符串保留 usage。直接验证 `_handle_truncation` 的核心契约。
- **`test_summary.py::TestWriteModuleDataRows`**（6 项新测试）：缓存命中行渲染、成功+Thinking 行渲染、禁用行渲染、失败行渲染、空 status_label 跳过、4 状态混合行序列验证。覆盖 Excel 单元格级渲染逻辑（Token 格式化、费用展示、✓/— 标记）。
- **`test_llm_scenarios.py`**（33 项新测试）：LLM 全场景组合 + 异常/Edge Case + 输出格式一致性 + HTML 模板分支巡检。
- **`styles.py::DARK_GREEN_FONT`**：深绿色字体常量 `Font(color="006400")`，用于基金业绩"较差"评级标色。

### Changed
- **`logger.py`：测试日志写入 `logs/test.log`** — 通过 `sys.argv` 检测 pytest 环境，测试期间日志写入独立文件，避免与运行时 `logs/app.log` 混淆。
- **`test_html_writer.py` 测试隔离增强** — `TestWriteHtmlReportLlmType.setUp/tearDown` 保存并清理 `_LLM_MODULE_FAILURE` 全局状态，消除前序测试跨类残留。模块明细计数断言从 `4` 更新为 `5`。
- **`_finalize_news_token_usage` 记录增强** — 新增 `all_cached` 参数，全缓存场景也调用 `_record_per_module`；新增 `_estimate_cost` 计算费用；传递 `endpoint` 字段。
- **`plan.md`**：新增 P. 业务场景测试增强迭代方向（S11-S17 LLM 全场景组合 + 异常/Edge Case + 输出格式一致性验证）；新增 Q. 日期/时间数据获取场景测试方向；P 节已完成并移至待实现方向 → 已完成迭代。
- **`testplan.md`**：业务场景表扩展 S11-S17（LLM 混合缓存/失败/Thinking/禁用/断网/部分超期）；新增 1.6 日期/时间数据获取场景测试 T1-T16；新增 1.7 场景-测试文件覆盖率映射；迭代列表新增 v0.2.59。

### Tests
- 全量 **1854 passed**（12 skipped，65 subtests passed）。
- **新增 `test_llm_scenarios.py`**（33 项），覆盖 S11-S17 LLM 混合缓存+全部失败+Thinking+禁用+断网+部分超期+全缓存、空持仓+LLM、HTML/Excel/Summary 输出一致性、模板分支审计。
- **新增 `test_datetime_scenarios.py`**（61 项），覆盖 T1-T16 日期/时间数据获取场景：
  - T1~T6 市场状态组合（get_ttl market-hour-aware 12 项 + is_midday_break 7 项 + 长假边界 6 项）
  - T7~T11 产品类型分类（classify_holdings 17 项 + count_trading_days_back 9 项）
  - T12~T16 边界 Edge Case（TTL 过渡/首次启动/fetch 链路 5 项）
- `test_skeleton.py` 从 2 项扩充至 **5 项**（+3）
- `test_html_writer.py` 模块计数 4→5，隔离修复

---

## [0.2.58] - 2026-07-02

### Added
- **指数双链路 fallback**：A 股指数新增新浪财经备用链路（sina.fetch_a_indices，s_* 前缀），腾讯失败时自动切换；美股指数新增腾讯财经备用链路（tencent.fetch_index_price，gb_* 前缀），新浪 2 次重试失败后自动切换。双链路均失败时降级过期缓存。
- **`src/python/providers/sina.py`** 新增 `_parse_a_index()`、`fetch_a_indices()` — A 股指数解析与获取（s_* 前缀，字段索引：name/price/change/change_pct/volume/amount/datetime）。
- **`src/python/providers/tencent.py`** 新增 `fetch_index_price(code)` — 通用指数获取，不添加交易所前缀，直接请求原始代码。

### Changed
- **`fetcher/index.py`** 重构为模块级函数：`_fetch_indices_from_tencent()` / `_fetch_indices_from_sina()` / `_fetch_us_from_tencent()`，主链路→备用链路→过期缓存三层降级。
- **`technical.md` / `datasource-and-folders.md`**：数据源表 A 股/美股指数备用链路从"—"更新为实际备用 API。

### Tests
- `test_fetcher_index.py`：从 8 项扩展至 13 项，新增腾讯→新浪 fallback、新浪→腾讯 fallback、双链路均失败降级等场景覆盖。
- `test_fetcher.py`：`TestFetchUsIndices` mock 补充腾讯备用链路模拟。

---

## [0.2.57] - 2026-07-01

### Fixed
- **🐛 `industry` Provider Chain 缺失（R-138）**：`fetcher/chain.py` 的 `_DEFAULT_CHAINS` 无 `"industry"` 条目，导致 `_fetch_with_fallback("industry", ...)` 的 Provider Chain 永不会执行。由于 `industry.py` 回调了独立的 `eastmoney_industry.fetch_industry_and_concepts()`（不经 Chain），该缺陷未暴露为数据异常。修复：补充 `"industry": ["eastmoney_industry"]` 到 `_DEFAULT_CHAINS`。
- **🐛 `claude-fable-5` 缺失 Extended Thinking 名单（R-141）**：`llm/api.py` 的 `_THINKING_SUPPORTED_PREFIXES` 未包含 `claude-fable-5`，新模型使用时自动降级跳过 Extended Thinking。修复：补入名单。

### Removed（死代码 / 向后兼容代码）
- **R-138: `_PROVIDER_REGISTRY` 死字典**：`fetcher/chain.py` 废弃的旧版 Provider 注册字典，无任何引用。
- **R-140: `_strip_token_line()` 向后兼容函数**：`llm/api.py` 的 `_TOKEN_LINE_RE` 正则及 `_strip_token_line()` 函数（R-131 移除旧版 Token 行格式后遗留），以及 `generators.py`/`skeleton.py` 中的调用处、`test_api.py` 中的导入和测试类。
- **R-139: `config.py` 过期 Provider 条目**：`_KNOWN_PROVIDER_TYPES` 移除已废弃的 `index`、`us_index`；`_KNOWN_PROVIDER_NAMES` 增补 `eastmoney_industry`。
- **R-142: 未使用 import**：`fetcher/index.py` `CACHE_DAILY`、`fetcher/fund.py` `CACHE_DAILY`/`CACHE_MONTHLY`/`CACHE_WEEKLY`。

### Changed
- **R-143: config.json + 管理文档同步**：`cache_ttl` 补充 `tracking`（2592000）和 `calendar`（1209600）。`technical.md` 缓存分组计数修正（preload 5→6、refresh 10→9）。`requirements.md` cache_ttl 项数 15→17。`how-to-config.md` 同步更新示例 JSON、TTL 表及 ungrouped 说明。
- **`fetcher/index.py` docstring**：更新新浪备用链路描述（"仅有主链路，无可用备用"）。
- **文件标题更新**：review-findings.md 最后更新 v0.2.57。

### Tests
- `test_api.py`：移除 `_strip_token_line` 导入和 3 项测试 → 41 passed（-3 项），全量测试 1708 passed。[^1]

[^1]: 原 1711 passed - 3 项移除 = 1708 passed，12 skipped，31 subtests passed。  

### Fixed
- **P0: 指数 `market_hour_aware` 不生效**（R-136）：`fetcher/index.py` 硬编码 `CACHE_DAILY` 代替 `get_ttl("index")`，盘中 30s 短 TTL 对指数无效。修复后指数在交易时段内自动使用短 TTL 刷新实时行情。
- **P1: 多处硬编码 TTL 绕过 `get_ttl()`（R-137）**：`fund.py` 基金排名/基金持仓/基准、`industry.py` 行业分类、`market_value.py` 交易日历共 5 处硬编码常量改为 `get_ttl("type")`，确保 `config.json` 中的 `cache_ttl.*` 配置变更对所有读缓存路径生效。
- **P1: `test_fund.py` 双重检查锁用例锁外竞态**：`_call_no` 非线程安全的 RMW 竞态在 `get_ttl()` 微耗时变化后暴露。改为 `threading.Event` 精确控制缓存状态，消除时序依赖。

### Changed
- **P2: `llm_health_check` TTL 7200→86400**（注册表 + config.json + 用户文档同步）：持仓体检报告基于组合结构（行业集中度/流动性/成本结构），持仓不变时无需每小时重新生成，24h + 持仓指纹变化自动失效更合理。
- **P3: 交易日历 TTL 不一致消除**：`registry.py` 注册 14 天 + `market_value.py` 读缓存统一使用 `get_ttl("calendar")`，与 `cleanup_expired()` 清理周期一致。
- **scripts/launch.ps1 / launch.sh**：`pip install -q` → `-qq`，抑制 `.venv` 内 pip 版本更新通知（venv 继承 Python 3.13.0 捆绑的 pip 24.2，而系统 pip 已升级至 26.1.2）。
- **config.json + how-to-config.md 同步**：config.json 的 `cache_ttl` 补充缺失的 `tracking`（2592000）和 `calendar`（1209600）条目；how-to-config.md 同步更新示例 JSON、TTL 参数表及无分组说明；requirements.md cache_ttl 项数从 15→17。
- **technical.md 缓存分组计数修正**：preload 组 5→6 模块（llm_health_check 加入后未更新）、refresh 组 10→9 模块（列表实际只有 9 项）。

### Tests
- 全量 1711 passed, 12 skipped, 31 subtests passed。

---

## [0.2.55] - 2026-07-01

### Added
- **P0: `_parse_syl_returns()` 长周期 + `--` 防御**：新增 `syl_2n`/`syl_3n`/`syl_5n` 长周期变量名映射；`--` 占位符跳过而非解析为数值，避免净值数据不足时误显示零收益。新增 4 项测试。
- **P1: `_parse_risk_analysis()` 风险分析解析**：从 `Data_riskAnalysis` JS 变量解析年化波动率、最大回撤、夏普比率等风险指标。支持 JSON 对象格式（categories+data）和数组格式（`[名称,值]`）。`fetch_fund_rankings()` 返回字典新增 `risk_analysis` 字段。新增 7 项测试。
- **P2: 5 级评级系统 + 类型差异化阈值**：
  - **5 级评级**：4 级→5 级（优秀≤10%/良好≤30%/稳定≤50%/偏差≤75%/较差>75%），与 Morningstar/银河证券行业标准对齐。
  - **`_pct_to_rating()` 独立函数**：百分位→评级纯函数，支持自定义阈值。
  - **`_RATING_THRESHOLDS` 类型差异化**：`bond`/`qdii` 宽松（15%/35%/55%/80%），`index` 严格（10%/25%/45%/70%），`default` 标准（10%/30%/50%/75%）。
  - **`fund_type_hint` 参数**：`_calc_rating_from_entry()` 自动选择类型阈值。
- **`fund_performance.py` 同步 5 级**：`_RATING_ORDER` 扩展为 `["较差","偏差","稳定","良好","优秀"]`；`_RATING_COMMENT` 新增 `"较差"`；`_adjust_rating_with_benchmark` 自动适配。

### Changed
- **`test_tiantian.py` `TestCalcRatingFromEntry` 重写**：23 项覆盖 5 级边界 + 类型差异化阈值（bond/index/qdii/unknown 回退）；rank_outranks 矛盾回归用例从"偏差"→"较差"（5 级后底部 3.3% 映射正确）。

### Tests
- 全量 **1711 passed**（+20）, 12 skipped, 31 subtests passed。
- `test_tiantian.py` 从 39 项扩充至 **65 项**（+26）

---

## [0.2.54] - 2026-07-01

### Fixed
- **P0 CRASH × 6**：
  - **R-116** `tui_menu.py` `config["holdings_dir"]` 裸键访问 → `.get()` 安全读取（配置异常时菜单入口崩溃）
  - **R-117** `tui_menu.py` `endpoint.split("/")[2]` → 安全解析（短端点格式时配置显示崩溃）
  - **R-114** `tui.py` Linux 非 TTY 下 `termios.tcgetattr` 崩溃 → 加 `isatty()` 保护
  - **R-130** `tui.py` Windows `msvcrt.getch()` 方向键二次读取时 `KeyboardInterrupt` 保护
  - **R-119** `fetcher/industry.py` `future.result()` 无异常防护 → 加 `try/except` 批量继续
  - **R-113** `providers/tiantian.py` 全宽括号正则 `group(1)` 为 `None` → 合并为 `[\(（]` 字符集
- **P0 HANG × 1**：
  - **R-115** `tui.py` Linux ESC 序列 `read(2)` 永久阻塞 → 逐字节 `select.select` 超时读取
- **P1 WRONG DATA × 5**：
  - **R-120** `providers/tencent.py` `_add_prefix()` 缺失 2/4/8/9 前缀 → 补 sz/bj 映射
  - **R-122** `providers/akshare_extras.py` `_run_with_timeout` 未实际超时 → `shutdown(wait=False)`
  - **R-124** `providers/akshare_extras.py` NaN 穿透写入非法 JSON → `math.isnan` 返回 `None`
  - **R-123** `providers/akshare_extras.py` 分红 API `future.result()` 无超时 → 加 30s timeout
  - **R-121** `providers/sina.py` 硬编码 `var hq_str_` 无格式校验 → 加 `startswith` 告警
- **P1 场景问题 × 3**：
  - **R-101** `providers/eastmoney.py` 备用链路 `yesterday_nav=0` → today_profit 虚高修复
  - **R-103** `report/market_value.py` 零成本 `profit_rate=0%` → 改为 `None`
  - **R-125** `providers/akshare_extras.py` `_MEMO_CACHE` 无界 → LRU 淘汰（上限 100）
- **基金业绩评级 bug（R-131）**：百分位(Data_rateInSimilarPersent)与排名/总数(Data_rateInSimilarType)来自不同同类分组导致评级矛盾（如 159222 自由现金流ETF：百分位 3.33→优秀，排名 4823/4985→偏差，最终错误显示"优秀"）。修复后：同时计算百分位评级和排名评级，不一致时以排名/总数为准并记日志。同步新增 6 项回归测试。
- **`_parse_rank_entry` 异常防御增强（R-132）**：捕获补充 `AttributeError`。

### Added
- **`src/test/test_config_atomic.py`（R-085 ✅）**：11 项测试覆盖原子写入创建/覆盖/持久化/异常时临时文件清理/递归目录创建/缓存失效。
- **`src/test/test_circuit_breaker_recovery.py`（R-087 ✅）**：15 项测试覆盖熔断器全生命周期（关闭→1次失败→2次→3次→开启→冷却→半开→恢复/重开）。
- **`src/test/test_market_value_edge.py`（R-090+R-091 ✅）**：15 项测试覆盖溢价率占位符"--"、非 T 日 today_profit=0、腾讯始终计算、负值利润、空 nav_date。
- **`src/test/test_penetration_edge.py`（R-092 ✅）**：12 项测试覆盖占比归一化(≈100%)、零总市值→全零、单资产→100%、TOP10 上限、金额为空处理。
- **`src/test/test_integration_scenarios.py`（R-095 S6~S10 ✅）**：17 项测试覆盖纯债基金分类、Provider 回退至过期缓存、单只持仓利润计算、零成本利润率为 None、极端份额与高精度 NAV。

### Changed
- **日志轮转确认已有实现**：`src/python/logger.py` 使用 `RotatingFileHandler`（10MB/5备份），`logs/app.log` 已有大小轮转，无需修改。plan.md M 节条目移除。
- **review-findings.md**：R-085~R-132 全部完成，待办区清空。

### Tests
- 全量 1691 passed（+156）, 11 skipped, 30 subtests passed。
- P 节 12 项测试补全 + 补充修复 8 项预存测试缺陷 + R-131 评级 bug 6 项回归。

### Docs
- **plan.md**：P 区 12 项清理归档，移除已完成"日志轮转"条目；N 节 HTML 响应式 ✅ 从待实现方向移至已完成迭代。
- **datasource-and-folders.md**：测试文件数 50→57，passed 1535→1691。
- **technical.md**：测试数 1691 passed 同步。

## [0.2.53] - 2026-07-01

### Added
- **`_format_holdings_block()` / `_format_penetration_block()` 共享格式化函数**（`prompts.py`）：抽取为 3 模块（expert_review / health_check / penetration_deep）共用的持仓明细格式化函数，消除重复循环。
- **`_LLM_CLIENT_SETTINGS` HTTP 连接池配置**（`generators.py`）：`http2=True` 多路复用 + 连接池上限 20 / 空闲保持 10，减少 API 连接建立开销。

### Changed
- **P1: LLM Prompt 精简** — `_build_expert_review_prompt` 启用 `compact` 模式，省略今日涨跌幅字段（场外基金保留净值日期）。输入 token 减少 10~15%，缓存受行情波动影响降低。
- **P2: HTTP 会话复用** — `_make_runner` 创建 `httpx.Client` 时使用共享 `_LLM_CLIENT_SETTINGS`，统一超时/连接池参数。
- **`_FALLBACK_ENABLED` 死代码移除**（`news_sources.py`）：R-055 时清理了引用但未删除定义，现彻底移除。

### Fixed
- **config.json 缺少 `early_warning` 配置段**：补齐 `sector_alert_threshold_*` 和 `sentiment_top_n` 三个可调参数。
- **P0: `handlers_cache.py` 缺失 `read_holdings` 导入（R-084）**：从 `tui_handlers.py` 拆分出 `handlers_cache.py` 时，`_read_holdings_and_clear_cache()` 依赖的 `read_holdings` 导入未随迁，菜单 [1]/[2] 刷新缓存时 `NameError`。已补上 `from src.python.reader import read_holdings`。

### Docs
- **review-findings.md**：精简审查记录，待办区全部清空（R-001~R-083 ✅）；R-084（P0 导入缺失）已完成并移入 changelog；新增场景审计 12 项（R-101~R-112）。
- **plan.md / technical.md / README.md**：版本号同步至 v0.2.52，K/L/M/N/O 方向标注。
- **datasource-and-folders.md**：测试文件数 35→50，新增 `reason.bat`。

### Tests
- 全量 1535 passed, 11 skipped, 30 subtests passed。

---

## [0.2.52] - 2026-07-01

### Changed
- **15 个大函数全部拆分完成（R-056~R-070 ✅）**：P2 大函数治理二期收官，函数均 ≤75 行：
  - `config.py:validate_config()` 123→71 行，提取 `_validate_sector_alerts`/`_validate_numeric_range`/`_validate_sentiment_top_n`
  - `report/early_warning.py:_compute_sentiment_alerts()` 99→48 行，提取 `_collect_news_sentiments`/`_build_sentiment_alert_items`
  - `llm/markdown.py:_markdown_to_html()` 96→34 行，提取 `_convert_code_block`/`_convert_table`/`_convert_inline`
  - `llm/api.py:_call_llm_with_retry()` 94→50 行，提取 `_execute_with_retry`/`_should_retry`
  - `fetcher/chain.py:_fetch_with_fallback()` 90→42 行，提取 `_try_chain_provider`/`_degrade_expired_cache`
  - `providers/news_keywords.py:build_holding_keywords()` 86→35 行，提取 `_build_keyword_sources`/`_enrich_industry_keywords`
  - `llm/api.py:_call_claude()` 85→45 行，提取 `_inject_thinking`/`_format_claude_messages`
  - `providers/eastmoney_industry.py:fetch_industry_and_concepts()` 82→38 行，提取 `_call_industry_api`/`_parse_industry_result`
  - `report/market_value.py:write_market_value_sheet()` 79→40 行，提取 `_init_market_value_sheet`/`_build_market_value_data`
  - `report/market_value.py:_generate_details()` 78→32 行，提取 `_fetch_price_batch`/`_compute_detail_row`
  - `providers/akshare_extras.py:get_dividend_data()` 78→35 行，提取 `_fetch_dividend_api`/`_compute_avg_dividend`
  - `llm/prompts.py:_build_penetration_deep_prompt()` 78→30 行，提取 `_build_industry_concentration`/`_build_currency_exposure`
  - `llm/skeleton.py:_generate_llm_module()` 77→40 行，提取 `_build_llm_module_input`/`_process_llm_module_result`
  - `cache.py:cleanup_expired()` 77→35 行，提取 `_scan_cache_files`/`_filter_expired`
  - `report/html_writer.py:_render_llm_module_info()` 76→32 行，提取 `_build_llm_section_html`/`_build_footer_line`

### Added
- **`src/test/test_akshare_news.py`（R-071 ✅）**：16 项测试覆盖 `_fetch_from_caixin`（9 项纯函数 + mock 含未安装/异常/空数据/正常解析/去重/截断/过滤）+ `_fetch_cctv_news`（4 项）+ `fetch_news`（3 项聚合）。
- **`src/test/test_cls_news.py`（R-072 ✅）**：21 项测试覆盖 `_ts_to_str`（3 项）+ `_parse_news_item`（10 项纯函数）+ `fetch_news`（8 项 HTTP/异常/缺字段）。
- **`src/test/test_eastmoney.py`（R-073 ✅）**：15 项测试覆盖 `_strip_jsonp`（2 项）+ `_safe_float`（3 项）+ `_fallback_fundf10`（4 项）+ `fetch_nav`（6 项 HTTP/异常/缓存/回退/错误解析）。
- **`src/test/test_sina.py`（R-074 ✅）**：10 项测试覆盖 `_parse_us_index`（4 项纯函数）+ `fetch_us_indices`（6 项 HTTP/异常/部分失败/空数据）。
- **`src/test/test_tencent.py`（R-075 ✅）**：16 项测试覆盖 `_add_prefix`（6 项）+ `_parse_float`（5 项）+ `_parse_response`（6 项纯函数，含 35 字段补齐）+ `fetch_price`（4 项 HTTP/超时/网络异常/解析失败）。
- **`src/test/test_news_aggregator.py`（R-076 ✅）**：16 项测试覆盖 `get_enabled_sources`（3 项）+ `_compute_cache_key`（3 项）+ `_finalize_news_results`（5 项）+ `aggregate_news`（5 项编排，含缓存命中/未命中/全失败/默认源）。
- **`src/test/test_fetcher_index.py`（R-077 ✅）**：8 项测试覆盖 `_index_cache_key`（2 项）+ `fetch_indices`（3 项）+ `fetch_us_indices`（3 项 HTTP/异常 + provider 回退）。
- **`src/test/test_fetcher_industry.py`（R-078 ✅）**：10 项测试覆盖 `_industry_transform`（4 项纯函数）+ `fetch_industry_data`（3 项）+ `batch_fetch_industry_data`（3 项并发）。
- **`src/test/test_fetcher_price.py`（R-079 ✅）**：21 项测试覆盖 `_name_matches`（4 项）+ `_price_cache_key`（2 项）+ `_price_transform_tencent`（5 项）+ `_price_transform_eastmoney`（3 项）+ `fetch_market_data`（7 项编排/异常/降级/部分失败）。
- **R-080 ✅ 旧式 typing 泛型 → 内置泛型**：13 个文件的 `List[X]`/`Dict[X,Y]`/`Optional[X]`/`Tuple[X,Y]` 全部替换为 `list[X]`/`dict[X,Y]`/`X | None`/`tuple[X,Y]`。涉及：reader.py、category.py、excel_writer.py、fund_performance.py、html_builders.py、html_writer.py、market_value.py、news_correlation.py、penetration.py、penetration_sheet.py、llm/api.py、news_aggregator.py、news_keywords.py。
- **R-082 ✅ `.format()` → f-string（3 处）**：`generators.py`/`skeleton.py` 中模板 `.format()` 改为函数调用 `_cache_line_model_tpl()`；`html_writer.py` 中存档文件名改为 f-string。
- **R-083 ✅ pyproject.toml 同步**：版本号 0.2.36→0.2.52，依赖 `>=`→`==` 精确版本（与 requirements.txt 一致），补充 `lxml==6.1.1` 和 pytest 插件。

### Changed
- **`config.py:validate_config()` 新增 early_warning 段校验（R-054 续）**：补充 `sentiment_top_n` 正整型验证。

### Tests
- 9 个新测试文件 + 140 项新增测试（全量 1535 passed, 11 skipped）。
- 新增测试覆盖 providers/tencent/sina/eastmoney/akshare_news/cls_news/news_aggregator、fetcher/index/industry/price 共 9 个模块。

### Docs
- **review-findings.md**：R-056~R-070（大函数治理二期）、R-071~R-079（测试覆盖补全三期）全部完成，移出待办区。待办区仅保留 P3 R-080~R-083。
- **版本号同步**：constants.py 0.2.51→0.2.52

## [0.2.51] - 2026-07-01

### Added
- **`src/test/test_fingerprint.py`（R-044 ✅）**：16 项测试覆盖 `_extract_stable_holdings`（5 项）/ `_extract_stable_penetration`（5 项）/ `_build_llm_fingerprint`（6 项，含确定性/不同输入/full_penetration/价格无关/hex 格式/全默认值）。
- **`src/test/test_eastmoney_news.py`（R-047 ✅）**：18 项测试覆盖 `_parse_news_item`（9 项纯函数）+ `fetch_news`（9 项 HTTP/异常/空数据/无效条目过滤）。
- **`src/test/test_sina_news.py`（R-048 ✅）**：17 项测试覆盖 `_ts_to_str`（2 项）+ `_parse_news_item`（9 项纯函数）+ `fetch_news`（8 项 HTTP/异常/参数验证）。
- **`src/test/test_wallstreetcn_news.py`（R-049 ✅）**：15 项测试覆盖 `_ts_to_str`（2 项）+ `_parse_news_item`（12 项纯函数，含标题回退/HTML 剥离/URI 处理/截断）+ `fetch_news`（9 项 HTTP/异常/limit 上限）。

### Changed
- **`llm/__init__.py` 过度导出清理（R-050 ✅）**：从 6 个子模块 re-export 的 ~60 个私有符号仅保留公有接口（FAIL_REASON_* 常量 + 6 个公开函数）。`_LLM_MODULE_FAILURE`/`_CACHE_PREFIX_LLM` 等私有符号改为从子模块直接导入。同步修复 `test_llm.py` 中 26 处 import 路径。
- **`llm/skeleton.py` 全局 max_tokens 回退路径清理**：`llm_config.get(f"max_tokens_{module_key}") or llm_config.get("max_tokens", max_tokens_default)` → `llm_config.get(f"max_tokens_{module_key}", max_tokens_default)`。移除旧版全局 `max_tokens` 幽灵字段兜底。
- **`config.py` 跨文件键名兼容机制清理**：移除 `_LLM_KEY_OVERLAP_KEYS` 集合及 `_KNOWN_TOTAL_KEYS` 合集。llm_key.json 与 llm_settings.json 的键名严格分离。
- **`llm/circuit_breaker.py`（R-043 ✅ 无需加测）**：熔断器逻辑已由 test_api.py 7 项测试间接充分覆盖，无需单独测试文件。
- **`llm/pricing.py`（R-045 ✅ 无需加测）**：定价计算已由 test_pricing.py 8 项测试覆盖。
- **`llm/markdown.py`（R-046 ✅ 无需加测）**：Markdown→HTML 转换已由 test_markdown.py 11 项测试覆盖。

### Changed（续）
- **`requirements.txt` 版本锁定（R-053 ✅）**：从未锁定范围（`>=`）改为精确版本锁定（`==`），新增 `lxml==6.1.1` 和 `pytest==9.1.1`/`pytest-mock==3.15.1` 测试依赖。
- **`config.py:validate_config()` 新增 early_warning 配置段校验（R-054 ✅）**：覆盖 `sector_alert_threshold_warning`/`danger`/`sentiment_top_n` 的类型、范围（阈值应为负值）和格式校验。
- **`news_aggregator.py` 清理 `_FALLBACK_ENABLED` 死路径（R-055 ✅）**：移除对 `_FALLBACK_ENABLED` 的导入和后备引用，简化 `get_enabled_sources()` 逻辑。同步更新 `test_news_sources.py`（移除 7 项相关测试）。
- **`html_writer.py` 拆分 — 提取 `html_builders.py`（R-051 ✅）**：将 `_build_category_data`、`_build_single_perf_item`、`_build_perf_data`、`_parse_return_raw` 4 个数据构建函数（~175 行）迁入独立模块。主文件从 792 行降至 617 行（-22%）。render 函数通过导入保持对外接口不变，测试 mock 路径无需变更。
- **`penetration.py` 拆分 — 提取 `penetration_sheet.py`（R-052 ✅）**：将 `write_penetration_sheet` 及 6 个辅助函数（共 ~185 行）迁入独立模块。`penetration.py` 保留 `compute_penetration_top10` 及所有分类/合并逻辑，从 715 行降至 530 行（-26%）。同步更新 `excel_generator.py` 的 lazy import 和 `test_excel_generator.py` 的 mock 路径。

### Docs
- **review-findings.md**：P2 全部 7 项问题（R-043~R-049）完成，移除待办表。R-050/R-053/R-054/R-055/R-051/R-052 全部完成，待办区清空。
- **plan.md**：移除已完成 H（代码治理 R-051~R-053）和 I（配置治理 R-054~R-055）待实现方向，统一纳入 A5 完成项。
- **README.md**：版本号 0.2.49→0.2.51 同步。
- **datasource-and-folders.md**：新增 `html_builders.py`/`penetration_sheet.py` 目录描述，测试数 1264→1395。
- **technical.md**：测试数 1264→1395，最后更新描述同步。
- **版本号同步**：constants.py 0.2.50→0.2.51

### Fixed
- **缓存 TTL 市场时段感知逻辑缺陷（🐛 561910 价格偏差根因）**：`cache.py:get_ttl()` 中 `market_hour_aware` 检查位于显式 `cache_ttl` 配置之后导致死代码，盘中 30s 短 TTL 永不生效。交换判断顺序：交易时段内对 `market_hour_aware` 声明类型优先使用短 TTL，确保实时价格更新。
- **HTML 报告：B 模式下不应展示 LLM 分析章节占位符**：`report_template.html` 中八～十二节（全球政经局势/智囊团深度复盘/持仓体检报告/穿透深度分析/LLM API 用量）在 `llm_enabled=False` 时仍渲染"本节内容待生成"占位内容。包裹 `{% if llm_enabled %}` 条件，B 模式下完全隐藏。

### Changed
- **`report/news_correlation.py:_build_keyword_lookup()` 拆分（R-035 ✅）**：119→28 行，提取 5 个辅助函数（`_extract_terms`/`_index_holdings`/`_index_penetrated_assets`/`_index_industry_concepts`/`_enrich_with_industry_data`）。
- **`report/category.py:write_category_sheet()` 拆分（R-036 ✅）**：124→58 行，提取 3 个辅助函数（`_load_dividend_data`/`_yield_text`/`_write_category_group`）。修复 subtotal/total 值数组元素数与 API 签名一致（10→9）。
- **`llm/generators.py:enhance_news_correlation()` 拆分（R-037 ✅）**：128→35 行，提取 5 个辅助函数（`_select_top_news`/`_build_news_hooks`/`_map_llm_results`/`_merge_llm_analysis`/`_finalize_news_token_usage`）。
- **`llm/api.py:_call_llm_with_retry()` 拆分（R-038 ✅）**：114→75 行，提取 `_check_circuit_breaker`/`_process_success_response`。
- **`report/news_correlation.py:write_news_sheet()` 拆分（R-039 ✅）**：113→48 行，提取 3 个辅助函数（`_build_news_footer`/`_write_news_token_footer`/`_set_news_column_widths`）。
- **`report/html_writer.py:_build_perf_data()` 拆分（R-040 ✅）**：107→27 行，提取 `_build_single_perf_item`。
- **`providers/news_aggregator.py:aggregate_news()` 拆分（R-041 ✅）**：106→27 行，提取 4 个辅助函数（`_compute_cache_key`/`_check_news_cache`/`_save_news_cache`/`_fetch_from_all_sources`/`_log_source_status`/`_finalize_news_results`）。
- **`report/penetration.py:write_penetration_sheet()` 拆分（R-042 ✅）**：105→40 行，提取 3 个辅助函数（`_load_profit_forecast_safe`/`_load_dividend_data_safe`/`_write_penetration_footer`）。

### Added
- **`src/test/test_http_client.py`（R-033 ✅）**：17 项测试覆盖 `_should_verify`（8 种 env 值）+ `make_http_client`（6 种 kwargs 组合 + context manager）。
- **`src/test/test_market_hours.py`（R-034 ✅）**：41 项测试覆盖 `_parse_time_to_minutes`（10 项）/ `_fetch_trading_status_from_official`（7 项）/ `_is_market_open_fallback`（14 项）/ `_is_market_open_config`（6 项）/ `is_market_open`（5 项三层编排）。

## [0.2.49] - 2026-07-01

### Changed
- **未使用 import 清理（R-025 ✅）**：移除 12 个文件中的 19 处未使用 import，保留 `cache.py` 的 `CACHE_WEEKLY`/`CACHE_MONTHLY`（外部模块通过 cache.py 便捷导入）及 `generators.py` 的 `_generate_llm_content`（`__init__.py` 经由此处再导出）。
- **`report/fund_performance.py:write_fund_performance_sheet()` 拆分（R-026 ✅）**：164→55 行，提取 4 个辅助函数（`_load_profit_forecast`/`_coverage_text`/`_write_one_fund_row`/`_write_rating_distribution`）。主函数降至 55 行编排，47 项测试全部通过。
- **`report/summary.py:write_summary_sheet()` 拆分（R-027 ✅）**：163→43 行，提取 5 个辅助函数（`_write_basic_info`/`_write_holdings_overview`/`_write_profit_summary`/`_write_a_share_indices`/`_write_us_indices`）。主函数降至 43 行编排，45 项测试全部通过。
- **`report/news_correlation.py:build_news_data()` 拆分（R-028 ✅）**：159→60 行，提取 4 个辅助函数（`_expand_industry_keywords`/`_extract_active_sources`/`_apply_llm_enhancement`/`_enrich_news_keywords`）。news_correlation 测试 49 项全部通过。
- **`providers/tiantian.py` 三大函数拆分（R-029 ✅）**：`fetch_fund_holdings`(143→20行) 提取 `_request_fund_html`/`_find_holdings_table`/`_parse_holdings_rows`/`_extract_fund_meta`；`fetch_quarterly_holdings`(150→48行) 提取 `_request_quarterly_api`/`_parse_quarterly_holdings`/`_extract_quarterly_meta`；`fetch_fund_rankings`(135→40行) 提取 `_request_pingzhong_data`/`_parse_syl_returns`/`_parse_rank_entry`/`_calc_rating_from_entry`/`_parse_perf_evaluation`。全量 1216 测试通过。
- **`llm/skeleton.py` 两大函数拆分（R-030 ✅）**：`_generate_llm_content`(136→43行) 提取 `_handle_cache_hit`/`_finalize_and_cache`/`_handle_truncation`；`_run_batch_mode`(112→57行) 提取 `_check_batch_caches`/`_execute_and_merge_batch`。148 项 LLM 测试全部通过。

### Added
- **`src/test/test_tiantian.py`（R-031 ✅）**：39 项测试覆盖 `_find_holdings_table`/`_parse_holdings_rows`/`_extract_fund_meta`/`_parse_quarterly_holdings`/`_extract_quarterly_meta`/`_parse_syl_returns`/`_parse_rank_entry`/`_calc_rating_from_entry`/`_parse_perf_evaluation` 共 9 个纯函数。
- **`src/test/test_skeleton.py`（R-032 ✅）**：9 项测试覆盖 `_is_llm_module_enabled` 全分支 + 模块导入验证。

### Docs
- **review-findings.md**：R-025 标记 ✅ 已完成，待办区保留 R-026~R-032（P3）。
- **technical.md**：目录结构修正（移除重复 registry.py、添加 http_client.py），更新最后更新日期。
- **plan.md**：版本号更新至 v0.2.49。
- **版本号同步**：constants.py 0.2.48→0.2.49，README.md 0.2.48→0.2.49
- **全量文档一致性审计**：修复 5 处不一致：`how-to-start.md` 菜单 S 穿透深度分析默认状态 [关闭]→[开启]（代码默认 true）；`requirements.md` 最后更新 2026-06-30→2026-07-01；`testplan.md` 最后更新 2026-06-30→2026-07-01；`datasource-and-folders.md` 和 `technical.md` 测试数 "共 1264 项"→"1264 passed / 11 skipped"
- **datasource-and-folders.md 目录结构完善**：补全 `.gitignore` 根文件描述；为 5 个 `__init__.py`（src/、src/python/、fetcher/、providers/、report/）补充描述（包标记/公共 API 导出）；修正 `data/config/` 树形符号（├──/└── 层级）；调整 manuals 各分册描述更精确

## [0.2.48] - 2026-07-01

### Changed
- **`report/excel_generator.py:generate_excel_report()` 拆分（R-020 ✅）**：296 行→8 个函数（均 ≤75 行），提取 `_import_report_modules`/`_resolve_market_data`/`_resolve_indices`/`_write_content_sheets`/`_write_news_and_early_warning`/`_write_llm_section_and_usage`/`_build_llm_usage_sheet`。主函数降至 70 行。解决 ws2 循环依赖（直接传参而非通过 dict）。
- **`llm/generators.py:generate_all_llm()` 拆分（R-021 ✅）**：224 行→5 个函数（均 ≤75 行），提取 `_compute_module_cache_info`/`_precheck_one_cache`/`_precheck_all_modules`/`_dispatch_llm_workers`。`_make_runner` 闭包工厂统一 4 个近相同模块，主函数降至 72 行。
- **`report/summary.py:write_llm_usage_sheet()` 拆分（R-022 ✅）**：215 行→6 个辅助函数（均 ≤40 行），提取 `_init_llm_usage_sheet`/`_write_llm_summary_section`/`_write_module_table_header`/`_write_module_data_rows`/`_write_legend`/`_set_column_widths`。主函数降至 50 行。
- **`report/penetration.py:compute_penetration_top10()` 拆分（R-023 ✅）**：199 行→6 个函数（均 ≤55 行），提取 `_classify_and_group`/`_merge_fund_layer`/`_merge_stock_layer`/`_enrich_with_industry_api`/`_build_penetration_result`。主函数降至 20 行编排。

### Added
- **`src/test/test_handlers.py`（R-024 ✅）**：23 项测试覆盖 handlers_cache/handlers_config/handlers_report 三大模块的可测试辅助函数。包括 JSON 注释读取/写入、缓存刷新报告输出、单基金缓存刷新、盈利预测/行业资金流向、LLM+新闻 Future 处理、智能预警计算、用户输入选择。

### Docs
- **review-findings.md**：R-020~R-024 全部标记 ✅ 已完成，待办区再次清空。
- **technical.md**：测试文件数 34→33（核验修正）。
- **版本号同步**：constants.py 0.2.47→0.2.48，README.md 0.2.47→0.2.48

## [0.2.47] - 2026-07-01

### Changed
- **`cache.py` 交易时段判断提取为独立模块 `market_hours.py`（R-019 ✅）**：`_is_market_open()` 及其 5 个辅助函数（`_parse_time_to_minutes`、`_fetch_trading_status_from_official`、`_is_market_open_config`、`_is_market_open_official`、`_is_market_open_fallback`）及相关常量从 cache.py 迁入新文件 `src/python/market_hours.py`。cache.py 通过 `from src.python.market_hours import is_market_open as _is_market_open` 引用。测试文件同步更新 mock 路径。
- **`tui_handlers.py` 拆分（R-018 ✅）**：按职责拆为 `handlers_report.py`（报告生成，357 行）、`handlers_cache.py`（缓存管理，335 行）、`handlers_config.py`（配置管理，182 行）。`tui_handlers.py` 从 1147 行降至 234 行（-80%），保留菜单调度 + 通用辅助函数。`main.py` 导入目标改为各 handlers 模块。

### Docs
- **review-findings.md**：R-018 ✅、R-019 ✅ 标记已完成，全部待办问题清空。
- **technical.md**：项目结构树新增 `market_hours.py`、`handlers_report.py`、`handlers_cache.py`、`handlers_config.py`。
- **版本号同步**：constants.py 0.2.46→0.2.47，README.md 0.2.46→0.2.47

## [0.2.46] - 2026-07-01

### Fixed
- **`llm/api.py` HTTPStatusError 未捕获修复（R-015 完）**：`_call_llm_with_retry` 中 `raise_for_status()` 抛出的 `httpx.HTTPStatusError`（429/503 全部重试耗尽后）不被 `except httpx.RequestError` 捕获，改为 `except httpx.HTTPError` 后正常捕获。test_api.py 44 项全部通过。
- **`report/progress.py` ProgressReporter 基类错误存储修复**：基类 `add_error()` 仅 `logger.warning` 未存储错误，`get_errors()` 恒返回 `[]`。将 `_errors` 列表初始化、`add_error()`、`get_errors()` 从 `TuiProgressReporter` 提升至基类 `ProgressReporter`。

### Added
- **`src/test/test_api.py` — llm/api.py 单元测试**：44 项测试覆盖熔断/重试/回退/截断/Content Filter 安抚重试/JSON 解码/空内容/Provider 路由/fallback 链。
- **`src/test/test_excel_generator.py` — excel_generator.py 单元测试（重写）**：15 项测试覆盖基本路径、新闻/LLM 包含路径、模块缺失降级、页签异常隔离、`progress=None` 默认值、计时记录。修正 mock 策略以适配懒导入（模块级 → 源模块补丁）。
- **`docs-stm/manuals/reports-instruction.md` LLM API 用量章节**：新增独立说明章节，涵盖出现条件（仅菜单 L）、页签结构（汇总区 + 模块明细表）、状态颜色标识、完整示例表格。

### Docs
- **review-findings.md**：R-015 ✅ 标记完成，新增 2026-07-01 R-015 完成记录。
- **plan.md**：A. 测试覆盖补全 标记为 ✅ 已完成（v0.2.46）。
- **technical.md**：测试文件数 30→34 同步（R-017 ✅）。
- **版本号同步**：constants.py 0.2.45→0.2.46，README.md 0.2.45→0.2.46

## [0.2.45] - 2026-07-01

### Changed
- **`_cmd_generate_full` 继续拆分（R-009 完）**：提取 `_prepare_report_data()`（69 行）、`_prompt_force_llm()`（26 行）、`_compute_early_warnings()`（26 行）。`_cmd_generate_full` 从 136 行降至 75 行（-45%）。`tui_handlers.py` 所有函数均 ≤75 行。
- **`cache.py _is_market_open` 拆解（R-010 完）**：提取 3 个策略辅助函数 `_is_market_open_config()` / `_is_market_open_official()` / `_is_market_open_fallback()`，主函数降至 16 行 3 层链式调用。`check_and_refresh_caches` 已提取 `_read_holdings_tracking()` / `_clear_holdings_related_caches()`。

### Docs
- **review-findings.md**：R-009 ✅、R-010 ✅ 标记完成，R-015 ◐ 更新为 P3 延期（后续迭代补充）。
- **review-findings.md 清理**：确认所有可修复问题已修复完毕，R-009/R-010/R-014/R-016 已完成项移出待办区，待办区清空。
- **版本号同步**：constants.py 0.2.44→0.2.45，README.md 0.2.44→0.2.45

## [0.2.44] - 2026-07-01

### Changed
- **`_cmd_update_basic_cache` 提取 4 个模块级函数**：`_refresh_one_fund_cache()`、`_refresh_profit_forecast_cache()`、`_refresh_sector_flow_cache()`、`_print_cache_refresh_report()`。去除 3 个内嵌闭包，`_refresh_common_caches()` 复用提取函数并返回 `(pf_ok, sf_ok)`。`_cmd_update_basic_cache` 从 130 行降至 67 行（-48%）。

### Added
- **`src/test/test_fund.py` — fetcher/fund.py 单元测试**：19 项测试覆盖基准三层策略（API 解析/内置库/config 覆盖）、HTML 正则解析（含 script 标签/冒号变体/无匹配/HTTP 异常/多 URL 回退）、per-code 锁管理、双重检查锁并发、config 合并异常兜底。

### Docs
- **review-findings.md 更新**：R-014 ✅ 标记完成，R-015 ◐ 更新为部分完成（test_fund.py 已覆盖），新增 2026-07-01 全量审查记录。
- **plan.md 新增「代码质量持续优化」方向 (A)**：在下一步迭代计划中补充 cache.py 大函数拆分、测试增补、文档同步三个子方向。
- **technical.md 测试文件数：29→30**
- **版本号同步**：constants.py 0.2.43→0.2.44，README.md 0.2.43→0.2.44

---

## [0.2.43] - 2026-07-01

### Fixed
- **`_read_llm_settings()` JSON 注释崩溃**：R-012 提取时用 `json.load()` 代替了 `json.loads(_strip_json_comments())`，导致含 `//` 注释的 `llm_settings.json` 解析失败（菜单 [S] `[ERR] 无法读取 llm_settings.json`），现改回使用 `_strip_json_comments()` 先剥离注释再解析。

### Changed
- **`_cmd_generate_full` 提取 `_process_llm_news_futures()`**：184 行大函数中闭包 `_run_llm` 内联为 `generate_all_llm` 直接传参，`as_completed` 结果处理逻辑提取为独立函数，主函数降至 136 行（-26%），新函数职责明确。

### Docs
- **how-to-start.md 菜单 S 同步**：ASCII 图从 4→5 模块（含「财经新闻热点与持仓关联分析」），菜单 L 描述「LLM 四模块」→「LLM 多模块分析（5 个）」，菜单 1 描述补齐新闻关联分析缓存清除说明。
- **review-findings.md 清理**：R-011/R-012/R-013 已完成项移除待办状态，更新 R-009 进度描述。
- **版本号同步**：constants.py 0.2.41→0.2.43，README.md 0.2.42→0.2.43。

---

## [0.2.42] - 2026-07-01

### Changed
- **`write_html_report` 拆分为 12 个子函数**：390 行单体函数拆分为 `_render_market_value_section`、`_render_account_grouping`、`_render_category_info`、`_render_index_section`、`_render_category_table`、`_render_penetration_section`、`_render_fund_performance_section`、`_render_news_section`、`_render_llm_content_section`、`_render_llm_module_info`、`_save_html_report`、`_time_strings`，主函数降为 ~60 行，各子函数职责明确。
- **`tui_handlers.py` 提取 5 个共享函数**：`_prepare_holdings()`（持仓选择/读取/预热一体化）、`_finish_report()`（收尾收拢）、`_fetch_prices_and_indices()`（并行价格+指数）、`_read_llm_settings()` / `_write_llm_settings()`（配置读写分离），4 个 `_cmd_generate_*` 函数前置/后置逻辑复用，`_cmd_config_llm_modules` 读写职责分离。
- **`cache.py` 提取 `_read_cache_data()`**：统一处理 gzip/非 gzip 缓存文件读取、损坏自动删除，`get()` 从 67 行精简至 33 行，`cleanup_expired()` 复用同一辅助函数。

### Added
- **`src/test/test_chain.py` — Provider Chain 单元测试**：23 项测试覆盖 `_get_chain`（默认顺序、preferred_provider 前置、异常安全）和 `_fetch_with_fallback`（缓存命中、Provider 遍历回退、验证通过/拒绝、转换函数、per-provider 转换字典、过期缓存降级、未知 Provider 跳过、参数传递）。
- **`src/test/test_progress.py` — ProgressReporter 单元测试**：33 项测试覆盖基类、静默报告器、TUI 格式化输出、错误跟踪、耗时排行、_Timer 计时器。
- **`src/test/test_session.py` — 会话用量单元测试**：32 项测试覆盖 `reset/get/format/_track/_record_per_module` 全接口，含 claude/openai provider 差异、多模型去重、模块级累计。
- **`src/python/http_client.py`** — HTTP 客户端工厂模块，`make_http_client(**kwargs)` 自动读取 `SSL_VERIFY` 环境变量，避免各 provider 分散使用 `verify=False`。

### Fixed
- **`fetcher/fund.py` 静默异常加日志**：`_fetch_benchmark_from_api` 的 `except: continue` 和 `_get_full_benchmark_table` 的 `except: pass` 补充 `logger.debug`，避免运行时错误线索丢失。
- **3 处剩余静默异常**：`main.py:71` `_print_session_usage_on_exit`、`cache.py:528` `check_and_refresh_caches`、`llm/skeleton.py:188` 费用字符串解析 — 在 `except: pass` 前增加 `logger.warning(...)` 记录上下文。
- **`cache.py` `cleanup_expired(dry_run=True)` 不删除损坏文件**：`_read_cache_data()` 新增 `dry_run` 参数，预览模式仅计数不删。

### Removed
- **`fetcher/__init__.py` 向后兼容转发层**：曾为 `fetcher.py` → `fetcher/` 子包迁移保留约 40 项私有符号 + 7 个公有函数的 re-export。所有消费者改为直接从子模块导入。
- **`report/llm_content.py` 旧版页脚兼容代码**：移除 `from_cache`、`model_name`、`thinking_enabled` 参数及对应回退逻辑。

### Changed
- **akshare_extras.py 延迟导入统一**：3 处函数内 `import akshare as ak` 提至模块级统一导入，失败时 `ak = None` 兜底。
- **`verify=False` 统一治理**：`make_http_client()` 工厂函数替换 11 个模块共 14 处 `verify=False` 调用。

### Docs
- **how-to-config.md 新增「缓存分组」章节**：说明 `preload` / `refresh` 两个分组与菜单 `[1]`/`[2]` 的对应关系。
- **how-to-config.md 修复 `cache_ttl` 调整建议冲突**：移除与 market_hour_aware 盘中 30s 短 TTL 矛盾的调整建议。
- **CLAUDE.md 新增自审记录规则**：自查所有问题必须记录到 review-findings.md，修复后移至 changelog.md。
- **全量文档审计修复**：how-to-start.md（菜单 H/添加 S/R/表格修正）、how-to-config.md（菜单 O/early_warning）、how-to-config-llm.md（模型名修正）、README.md（版本号 0.2.40→0.2.42/移除菜单 N）、requirements.md（菜单数 12→14）、technical.md（测试数 26→29）、review-findings.md（R-011~R-013✅ 完成、R-009/R-010◐ 部分完成）
- **管理文档一致性审计**：iteration-plan.md 清空、technical.md fetcher 路径修正、review-findings.md 清理已完成审查清单。

---

## [0.2.38] - 2026-06-30

### Added
- **`src/python/llm/skeleton.py` — 独立骨架模块**：从 generators.py 拆分 4 个共享函数（`_is_llm_module_enabled`、`_generate_llm_content`、`_generate_llm_module`、`_run_batch_mode`），用于标准模式和批量模式 LLM 生成。
- **TUI 版本号显示**：菜单头部显示 `v0.2.38`。
- **TUI 菜单 [S] / [R]**：[S] 交互切换各 LLM 模块启停，[R] 立即刷新配置（config.json / llm_settings.json / llm_key.json）。
- **TUI 菜单 [S] 新增 `_cmd_config_llm_modules()`**：读取 `llm_settings.json`，交互式启用/禁用 LLM 模块。
- **TUI 菜单 [R] 新增 `_cmd_refresh_config()`**：清除 config 层缓存，强制重载三个配置文件。

### Changed
- **generators.py 拆分**：980 行 → skeleton.py (383 行) + generators.py (~280 行)。4 个骨架函数移至 skeleton.py，generators.py 保留 5 个生成器函数 + 1 个批量编排函数。
- **价格/指数缓存 TTL：静态 24h → 动态 market-hours 感知 TTL**：`cache.py` 新增 `_is_market_open()`，支持多渠道判断：
  - 优先读取 config.json `market_hours.start/end` 手动覆盖
  - 其次从东方财富 push2 API（上证指数 f100 交易状态）实时获取（缓存 TTL：盘中 30s，盘后 7 天）
  - 最后回退内置默认值（09:30–11:30 + 13:00–15:00，自动排除午餐休市）
  - 通过 `config.json` 的 `market_hour_aware`（`["price", "index"]`）和 `market_hour_ttl: 30` 驱动
- **TUI LLM 状态输出：区分跳过 vs 失败**：`tui_handlers.py` 报告生成循环按模块检查 `_LLM_MODULE_FAILURE` 原因，跳过的模块显示 `[..] 已跳过`，真正失败的模块显示 `[!] 内容生成失败` 并调用 `_add_error()`。
- **JSON 注释支持**：`config.py` 新增 `_strip_json_comments()`，在解析 `llm_settings.json` / `llm_key.json` 前自动剥离 `//` 和 `/* */` 注释，方便用户在配置文件中加注说明。
- **llm_settings.json 按业务模块分组重排**：用 `//` 注释标六大模块标题（全球政经局势 / 智囊团深度复盘 / 持仓体检报告 / 穿透深度分析 / 新闻关联分析 / 计价），配置项归入对应分组，便于阅读和维护。
- **README.md 版本号 0.2.37 → 0.2.38**，恢复缺失的用户文档链接。
- **test_llm.py / test_config.py mock 路径更新**：适应 generators→skeleton 的模块拆分，共 20 个 mock 路径修正。

### Fixed
- **HTML 报告指数涨跌幅双 `+` 号**：`report_template.html` 中 `{% if ... %}+{% endif %}{{ change | change }}` 的 `| change` 过滤器已自带 `+`，移除模板中的显式 `+` 前缀。
- **`_is_market_open()` 午餐排除**：从 09:30–15:00 连续区间改为 09:30–11:30 + 13:00–15:00，交易时段判断更精确。

### Docs
- **重写 how-to-config-llm.md** (581 行)：新增"LLM 业务模块架构与公共特征"章节（8 项公共特征），统一配置表格，补充缺失示例说明，去冗余。

## [0.2.37] - 2026-06-30

### Changed
- **`generators.py` P 重构 — 4 个 LLM 生成器提取共享骨架 `_generate_llm_module()`**：
  每个生成器从 ~70 行简化为 ~18 行的薄包装，通过 closure 传入 `fingerprint_fn`/`prompt_builder` 定制行为。
  文件 1050→961 行（-8.5%）
- **所有硬编码 LLM 模块名 → registry 查找**：
  - `news_correlation.py`：页签标题、write_title_row、6 处 logger 改用 `get_llm_module_name()`
  - `excel_generator.py`：`_add_error()` 消息、`_Timer` 标签改用 `get_llm_module_name()`
  - `tui_handlers.py`：4 个 `_print_box()` 标题改用 `get_llm_module_name()`
  - `generators.py`：所有 closure/disabled/completion logger 消息改用 `_MN()` 注册中心查找
- **所有非 LLM 报表页签中文名 → `get_report_sheet_name()` 统一注册**：
  - `registry.py` 新增 `_REPORT_SHEET_NAMES` 字典和 `get_report_sheet_name()` 函数（6 个页签）
  - `summary.py` / `market_value.py` / `category.py` / `penetration.py` / `fund_performance.py` / `early_warning.py` — 6 文件的 `ws.title` + `write_title_row` 共 12 处替换
  - `excel_generator.py` — `_Timer` 标签 7 处 + `_call_sheet` 标签 5 处共 12 处替换
  - 至此所有运行时的模块中文名均通过 registry 查找，实现"一处注册、全局生效"
- **清理 P 重构后的残留未使用 import**：移除 `datetime`/`timezone`/`timedelta`、`_CONTENT_FILTER_RECOVERY`、函数体内 `import re`
- **指纹函数 `_expert_review_fingerprint` / `_health_check_fingerprint` / `_penetration_deep_fingerprint` 合并为 `_build_llm_fingerprint()`**：3 个同构函数通过 `full_penetration` 参数统一，从 `fingerprint.py` 和 `generators.py` 中消除 ~30 行重复代码
- **`_generate_llm_module()` 新增批量模式**：通过 `batch_preparer` / `per_item_cache_fn` / `batch_prompt_fn` / `response_parser` 四个 hook，将 `enhance_news_correlation` 纳入共享骨架。旧函数从 ~230 行简化为 ~120 行，提取 `_run_batch_mode()` 辅助函数供未来批量模块复用
- **`api.py` `__all__` 清理**：`_CONTENT_FILTER_RECOVERY` 已无外部消费者，移出导出列表
- **`llm/__init__.py` 同步**：更新指纹导出名和 api 导出名
- **TUI 摘要标题统一**：`health_check` 和 `penetration_deep` 的 `_print_box` 标题后缀"摘要"/"概要"改为纯模块名，与 macro/expert 一致

### Docs
- **注册中心使用说明 `docs-stm/manuals/how-to-use-registry.md`** — 完整覆盖 DataModuleDef 结构、公共 API、消费方清单、新增模块流程
- **README.md** — 新增注册中心文档链接
- **管理文档修复**：
  - `technical.md`：content.py 已删除，子模块 9→8
  - `datasource-and-folders.md`：同上
  - `how-to-config-llm.md`：步骤 3/6 改为引用 registry
- **`changelog.md`**：本版本记录

### Tests
- 全量 1026 passed, 11 skipped, 30 subtests passed

## [0.2.36] - 2026-06-30

### Added
- **智能预警模块 `src/python/report/early_warning.py`** — 两个独立预警维度：
  - 行业资金流向联动：穿透资产的行业概念与今日行业资金流向匹配，净流出超过阈值自动标记预警等级（注意/关注/危险）
  - 新闻情绪聚合：财经新闻热点与持仓关联分析结果按持仓品种汇总，计算情绪得分与偏好评级
- **`src/test/test_early_warning.py` 智能预警测试** — 25 项测试覆盖：
  - 集成测试（正常数据/无数据/无LLM/正向净流入/空输入等 6 场景）
  - 行业预警单元测试（危险/关注/注意等级判定、概念匹配、排序、空输入）
  - 情绪聚合单元测试（代码聚合、低关联过滤、LLM未启用、情绪标签、要闻限制）
  - Excel 写入测试（正常数据/空数据 mock openpyxl）

### Changed
- **Excel 报告新增「11.智能预警」页签** — 位于财经新闻之后、LLM 章节之前，含行业联动 + 情绪聚合双表格
- **HTML 报告新增「七、智能预警」章节** — 含 Jinja2 模板渲染双表格，无预警显示占位文本
- 后续 LLM 章节编号顺延（七→八→九→十→十一→十二）
- 报告生成流程（菜单 N/B/L）自动附带智能预警

### P1 Optimized
- **`_sanitize_endpoint()` 去重** — 删除 `prompts.py` 中死代码副本（`api.py` 版本保持不动）
- **`cache.py` `_write_atomic()` 提取** — 消除 `set()` 中 21 行写入逻辑重复，提取私有辅助函数
- **`fetch_market_data()` 委托重构** — `_fetch_with_fallback()` 新增 `validate` + dict `transform` 支持，行情获取复用通用 fallback 链

### Tests
- 新建 `test_early_warning.py`（25 项）
- 全量 991 passed, 11 skipped, 30 subtests passed

## [0.2.35] - 2026-06-30

### Added
- **`src/python/registry.py` 配置注册表模块** — 引入中央注册表模式，使用 `DataModuleDef` 数据类统一管理所有数据模块的：
  - 缓存文件名前缀 → 数据类型映射（`get_prefix_type_map()`）
  - 数据类型 → 默认 TTL 映射（`get_cache_ttl_defaults()`）
  - LLM settings 键名自动派生（`get_known_llm_settings_keys()`）
  - 精确缓存键名映射（`get_exact_type_map()`）
  - 新增模块只需在 `_MODULE_REGISTRY` 添加一行，三处派生映射自动同步
- **`src/test/test_registry.py` 注册表测试** — 21 项测试覆盖：
  - 注册表完备性（无重复 data_type/前缀/键名、LLM/非LLM模块正确标记）
  - 派生映射正确性（全量 data_type TTL 覆盖、已知条目值精确断言）
  - DataModuleDef 单元测试（key 生成、不可变性、news_correlation 例外）

### Changed
- **`config.py` 去硬编码** — `_KNOWN_LLM_SETTINGS_KEYS` 改为 `get_known_llm_settings_keys()` 动态派生；`cache_ttl` 默认值改为 `get_cache_ttl_defaults()` 调用
- **`cache.py` 去硬编码** — `prefix_type_map` / `exact_map` / TTL 查找均改为调用 registry 函数
- **`constants.py` 清理** — 移除 `CACHE_TTL_DEFAULTS` 字典（已迁移至 registry），保留 `CACHE_DAILY/WEEKLY/MONTHLY` 零依赖常量

### Tests
- 新建 `test_registry.py`（21 项）
- 全量 966 passed, 11 skipped, 30 subtests passed

## [0.2.34] - 2026-06-30

### Changed
- **`content.py` 拆分为 `prompts.py` + `generators.py`** — 1471 行的 `content.py` 按职责拆分为提示词常量/构建函数（`prompts.py`）和编排逻辑（`generators.py`），`content.py` 保留为兼容重导出入口。`llm/` 包总子模块数增至 9 个。

### Fixed
- **`src/test/test_helpers.py` → `helpers.py`** — 该文件定义 `SynchronousExecutor` 测试辅助类，非测试用例，重命名以避免 pytest 误扫描（零个 `test_` 函数）并消除命名误导
- **`content.py` 移除冗余 `cache_get` 导入** — `cache_get` 在 `content.py` 中未直接使用（所有缓存读取通过 `_lm.cache_get()` 懒导入），仅保留 `cache_set`

### Tests
- **补充 System Prompt 覆盖路径测试** — 验证 `llm_settings.json` 中 `system_prompt_*` 设为非 null 时覆盖生效，设为 null 时回退到代码内置默认值

### Docs
- **`plan.md` 新增注册表模式迭代计划** — 将"配置注册表模式（远期蓝图）"写入下一次迭代规划

## [0.2.33] - 2026-06-29

### Changed
- **模块耗时日志名称同步** — `_Timer` 标签与 Excel 页签名/HTML 章节名统一：
  `汇总页`→`投资分析汇总`、`行情页`→`市值核算明细表`、`穿透TOP10`→`资产穿透TOP10`、
  `基金业绩`→`基金业绩分析`、`新闻数据`/`新闻页`→`财经新闻热点与持仓关联分析`、
  `LLM增补`→`LLM 分析章节`

### Changed
- **`_generate_excel_report` Import 隔离** — 7 个报告模块改为逐个 try/except 懒导入，
  缺失模块不会拖垮整个报告，仅跳过该页签并记录错误。
- **`_generate_excel_report` Sheet 写入隔离** — 6 个 Sheet 写入步骤使用 `_call_sheet()`
  统一包装，单个页签写入失败不影响其他页签。
- **Excel/HTML/日志名称统一** — 修复 `penetration.py`、`fund_performance.py`、
  `llm_content.py`、`report_template.html` 中页签名和章节名前缀空格不一致（`4. 资产` → `4.资产`），
  HTML 中 `资产穿透 TOP 10` → `资产穿透TOP10`，与日志模块名完全对齐。

### Tests
- 全量 814 项测试通过

## [0.2.32] - 2026-06-29

### Added
- **`generate_*` 函数新增 `llm_config` 参数** — 4 个 LLM 生成函数（`generate_global_macro` /
  `generate_expert_review` / `generate_health_check` / `generate_penetration_deep_analysis`）
  新增可选 `llm_config: dict | None = None` 参数。传入时跳过内部 `get_llm_config()` 调用，
  避免多线程场景下冗余文件 I/O
- **`enhance_news_correlation` 新增 `llm_config` 参数** — 与 4 个 `generate_*` 函数一致，
  传入时跳过内部 `get_llm_config()` 调用。`news_correlation.py` 调用处已持有 `_llm_config`
  变量，同步透传

### Changed
- **`generate_all_llm()` 缓存预检** — `get_llm_config()` 改为仅在顶层调用一次，预计算
  全部 4 个模块的指纹 + 缓存键，仅对缓存未命中的模块提交线程池任务。缓存命中的模块
  直接读取缓存内容，减少线程开销和文件 I/O
- **财经新闻热点与持仓关联分析改为逐条缓存** — 每篇文章独立计算缓存键（标题前 80 字 + 持仓指纹）。
  新文章加入时仅新文章的缓存缺失，已缓存的老文章在 TTL 内直接复用，不再触发整批重分析。
  单篇缓存存储 `(relevance, sentiment, analysis)` 元组

### Fixed
- **场外基金本日盈亏修复** — 仅净值日期等于当前交易日（T）时计算本日盈亏。
  此前 T-1 净值也参与计算，导致净值未发布时误将昨日变动标为"本日盈亏"。
  涵盖 QDII 与非 QDII 所有场外基金。
- **DeepSeek V4 Flash 定价修正** — `_MODEL_PRICING` 中
	- **how-to-start.md — 报告内容表/B/L 菜单说明/菜单 1 补全 B 模块（3 处同步修正）**：
	  - 报告内容对照表：新增基金深度分析列（B 系列 4 模块），B/L 标注 ✅
	  - 菜单 B/L 说明：追加 B 系列基金深度分析（与 requirements.md §2 已修内容对齐）
	  - 菜单 1 说明：补充 /基金经理/持仓重合度（refresh 组 11 模块）
  `deepseek-v4-flash` 从 `$0.50/$2.00` 更正为 `$0.14/$0.28`（每百万 token
  input/output），与官方 2026 年定价一致。

### Tests
- **`TestGenerateFunctionsAcceptLlmConfig`** — 4 条用例验证 `llm_config` 参数透传
- **`TestEnhanceNewsCorrelationUsesLlmConfig`** — 1 条用例验证 `enhance_news_correlation`
  的 `llm_config` 参数透传
- **`TestGenerateAllLlmCachePrecheck`** — 4 条用例验证缓存预检：全部命中/全部未命中/
  force 跳过/部分命中
- **`TestEnhanceNewsCorrelationGranularCache`** — 3 条用例验证逐条缓存：
  全部缓存/全部未缓存/部分混合
- **回归测试 — 场外基金本日盈亏** — 3 条用例：T-1 净值→today_profit=0、
  T-2 净值→price_type="官方净值(T-2)"、T 净值→today_profit 正常计算
- 全量 800 项测试通过（移除 11 个 `_date_within_days` 测试）

### Changed
- **`_estimate_cost` 改为从 `_PRICING_MERGED` 读取** — 新增模块级 `_PRICING_MERGED` 字典，
  初始化时从 `llm_settings.json` 的 `pricing` 段与 `_MODEL_PRICING` 合并（文件配置优先级更高）。
  `_reload_pricing()` 支持运行时重新加载定价配置。
- **`_DEFAULT_LLM_SETTINGS` 新增 `pricing` 默认段** — 包含所有已知模型的硬编码定价，
  自动创建 `llm_settings.json` 时写入。用户可直接编辑该文件覆盖或新增模型定价。
- **`_estimate_cost` 新增缓存命中计费** — 新增可选 `cache_hit_input_tokens` 参数，
  配合 `pricing` 中新增的 `input_cache_hit` 字段（缓存命中输入价格），
  在 API 返回 `cache_read_input_tokens` 时精确估算费用。
  Claude 模型缓存命中价为 input 的 10%（0.30 vs 3.0），
  无缓存折扣的模型（DeepSeek/GPT）设为与 input 相同。
- **`_MODEL_PRICING` 新增 `input_cache_hit` 字段** — 每个模型硬编码默认值增加缓存命中价格。
- **报告/日志显示缓存命中量** — HTML 报告和终端日志在 API 返回缓存命中数据时，
  显示"缓存命中：N tokens"标记。
- **新增 `deepseek-v4-pro` 模型定价** — 按官方 CNY 定价设置：input=3、output=6、input_cache_hit=0.025
- **`pricing` 段新增 `currency` 字段** — 支持多币种标识（`"CNY"` / `"USD"`），
  `_reload_pricing()` 读取后存入 `_PRICING_CURRENCY`，`_estimate_cost()` 用 `_CURRENCY_SYMBOLS` 映射符号输出
- **`llm_news_item` 加入 `prefix_type_map`** — `cache.py` 的过期清理函数现在能正确识别逐条新闻缓存并分配 1h TTL
- **菜单 [1] 补充 `llm_news_item_` 清理** — 更新基础类缓存时一并清理逐条新闻 LLM 缓存
- **管理文档审计修复** — requirements.md 章节编号 5.3→5.1→5.2→5.3→5.4 纠正、`llm_news_item_` 缺失补充、最后更新日期补全、plan.md 交叉引用修复；testplan.md 源文件路径修正（src/→src/python/）；technical.md `tmpl/` 目录位置修正（report/子目录→同级）；review-findings.md 测试计数更新（783→811）及审计记录追加
- **README 版本/参数同步** — 版本号 0.2.30→0.2.32；`max_tokens_penetration_deep` 示例值 2048→4096（与代码默认一致）；Token 消耗参考表改为 CNY 计价示例（DeepSeek-V4-Flash）
- **`generate_penetration_deep_analysis` fallback `max_tokens` 修正** — 兜底值 2048→4096，匹配 `max_tokens_penetration_deep` 默认值
- **穿透深度分析 Prompt 措辞修正** — system prompt + user prompt "前 N 大"→"TOP 10"（输入固定为 10 条），"占总资产"→"占总市值百分比"
- **内容过滤安抚重试** — `_call_llm_with_retry` 对空内容返回 `("", usage)` 而非 `(None, None)`，`_call_llm` 检测空内容后追加 `_CONTENT_FILTER_RECOVERY` 指令重试一次。DeepSeek 安全过滤误杀时自动恢复，不再直接失败
- **财经新闻热点与持仓关联分析批量合并** — `BATCH_SIZE` 从 5 增至 10，冷启动时 LLM 调用次数从 6 次降至 3 次，减少约 50%
- **会话级 Token 用量累计跟踪** — 新增 `_session_usage` 模块全局累积器（input/output/cache_hit/cost/call_count），`_track_session_usage()` 在每次 `_call_llm_with_retry` 成功后同步累计。导出 `get_session_usage()` / `reset_session_usage()` 供外部读取
- **汇总页签「LLM 用量」** — `write_summary_sheet` 新增 `llm_session_usage` 参数，报告汇总页底部显示本会话 LLM 调用次数、模型、输入/输出 token、缓存命中、累计费用
- **TUI 会话统计** — 报告生成完成后终端输出 `本会话 LLM 累计：N 次调用，X tokens，费用 ¥X.XX`

## [0.2.31] - 2026-06-29

### Added
- **熔断器（Circuit Breaker）** — LLM API 连续失败 3 次后自动开启 60s 冷却，
  冷却期内跳过对故障 endpoint 的请求，返回特定失败原因 `circuit_open`
  - `_cb_endpoint()` / `_cb_record_failure()` / `_cb_record_success()` / `_cb_is_open()` —
    熔断器核心函数，按域名粒度统计失败次数
  - `_call_llm_with_retry()` 入口检查熔断状态，冷却期内返回含熔断状态
- **跨 provider 自动回退** — 主 provider（如 claude）失败时自动尝试
  `fallback_provider`（如 openai），支持独立的 `fallback_api_key` / `fallback_endpoint` /
  `fallback_model` 配置
  - `_call_llm()` 新增双 provider 链式调用：主 → 回退。回退仍失败时返回 `fallback_failed`
  - TUI 输出回退状态：`[..] LLM 主 provider (claude) 失败，正在回退到 openai...`
- **失败原因传播至 Excel 占位符** — LLM 生成失败时，区分 5 种原因
  （`not_configured` / `api_error` / `network_error` / `timeout` / `circuit_open`），
  Excel 页签不同占位提示
  - `_LLM_MODULE_FAILURE` 字典、`FAIL_REASON_*` 常量、`_MODULE_KEY_MAP` 映射
  - `_get_placeholder()` 按失败原因输出针对性中文提示
- **缓存模型名保留** — 缓存命中时从缓存 HTML 提取原始模型名称并显示
  - `_extract_model_from_cached()` / `_MODEL_LINE_RE` — 从 Token 行提取模型名
  - `_CACHE_LINE_MODEL_TPL` — 新模板：`本次使用LLM缓存（原始模型：{model}）`
- **财经新闻热点与持仓关联分析 TUI 进度反馈** — 重试/回退时 TUI 输出可视化进度（`[..]` 标记）
- **自适应 max_tokens 截断重试** — `_generate_llm_content()` / `_process_batch()` 中
  检测到 `_TRUNCATION_MARKER` 后自动以 1.5 倍 max_tokens 重试一次
  - `_AUTO_INCREASE_FACTOR` / `_AUTO_INCREASE_MAX_RETRIES` — 常量控制重试倍数和次数
  - TUI 输出：`[..] 输出被截断，自动增大 max_tokens (4096 → 6144) 重新生成...`
  - 二次截断时记录 WARNING 日志提示手动增大配置
- **费用估算** — `_estimate_cost()` 基于 `_MODEL_PRICING` 定价表估算单次 API 费用
  - HTML 报告 footer 追加 `| 估算费用：$0.012`
  - TUI 输出追加 `| 估算费用: $0.008`（需已知定价模型）
  - 支持 10 种常见模型定价（Claude / GPT / DeepSeek），未知模型显示 "-"

### Changed
- **`_call_llm()` 拆分为二层** — 提取 `_call_single_provider()` 处理单 provider 调用，
  `_call_llm()` 负责主+回退链式调度
- **`_call_llm_with_retry()` 增强** — 成功时调用 `_cb_record_success()` 重置熔断状态；
  各类异常（超时/网络错误/HTTP 429/503）调用 `_cb_record_failure()`
- **所有 LLM 模块统一 token/model 显示** — `_generate_llm_content()` 在非缓存时
  追加灰色 footer：`模型：xxx | Token 用量：输入 X / 输出 Y = Z`；缓存时显示
  原始模型名或通用缓存提示
- **Extended Thinking 统一底部提示** — 无论缓存/非缓存，只要配置了 `thinking_enabled=true`，
  HTML 底部缓存提示行或 Token 行追加 `| Extended Thinking`；Excel 页签始终追加
  `Extended Thinking 已开启` 标识行（灰斜体 9pt）
- **`_log_token_usage()` 增强** — 新增 `model_name` 参数，已知模型时 TUI 输出追加估算费用
- **`_call_llm_with_retry()` 签名扩展** — 新增 `model_name` 参数，
  `_call_claude()` / `_call_openai()` 透传模型名实现费用估算
- **Excel 页签名称更新** — `1. 汇总` → `1.投资分析汇总`、`2. 市值核算` → `2.市值核算明细表`、
  `3. 分类汇总` → `3.分类汇总表`、`6. 财经新闻热点` → `6.财经新闻热点与持仓关联分析`
  （summary.py / market_value.py / category.py / news_correlation.py + 测试文件同步）
- **`llm_content.py` 增强** — `_write_content_sheet()` 使用 `_get_placeholder()` 替代
  硬编码占位符；`_get_placeholder()` 消费 `_LLM_MODULE_FAILURE` 中的失败原因
- **穿透深度分析 命名修正** — 日志/模板/注释中 `穿透深度分析` → `穿透深度分析`（html_writer.py、
  report_template.html、changelog.md）

### Config
- `data/config/llm_settings.json` — 新增 `fallback_provider` / `fallback_api_key` /
  `fallback_endpoint` / `fallback_model` 等回退配置项（可选）

### Tests
- 全量 783 项测试通过

## [0.2.30] - 2026-06-29

### Added
- **穿透深度分析** — 新增 LLM 生成模块，从行业集中度、国别/币种暴露维度
  对投资组合进行深度分析，含行业集中度仪表盘、外汇风险敞口分析、改进建议
  - `generate_penetration_deep_analysis()` / `_build_penetration_deep_prompt()` /
    `_SYSTEM_PENETRATION_DEEP` — 核心生成函数、Prompt 构建、System Prompt
  - `_penetration_deep_fingerprint()` — 稳定指纹计算（排除行情波动字段）
  - Excel 页签「10. 穿透深度分析」— 调用 `write_llm_sheets()` 写入第 10 个页签
  - HTML 报告「十、穿透深度分析」— 模板新增第 10 节，条件渲染穿透分析或占位提示
  - TUI 展示 — `_show_llm_tui()` 新增穿透分析摘要框
- **配置项** — `llm_settings.json` 新增 `_penetration_deep` 系列 10 项配置（temperature /
  timeout / cache_enabled / max_tokens / model / system_prompt / thinking_enabled /
  thinking_budget / reasoning_effort / output_brief）
- **缓存支持** — `cache.py` 注册 `llm_penetration_deep` 前缀（24h TTL），菜单 [2] 新增清除
  `llm_penetration_deep_*` 缓存

### Changed
- **`generate_all_llm()` 返回 8 元组** — 原 `(macro, expert, health, macro_cached, expert_cached,
  health_cached)` 扩展为 `(macro, expert, health, penetration, macro_cached, expert_cached,
  health_cached, penetration_cached)`
- **`write_llm_sheets()` 签名扩展** — `llm_content` / `llm_cached` / `model_names` /
  `thinking` 均从 3 元组扩展为 4 元组
- **`write_html_report()` 签名扩展** — `llm_content` 从 3 元组扩展为 4 元组
- **`_generate_excel_report()` 同步** — `llm_cached` 默认值从 `(False, False, False)` 扩展为
  `(False, False, False, False)`
- **`_cmd_generate_full()` 同步** — 8 元组解包 `llm_macro, llm_expert, llm_health, llm_penetration, ...`
- **`_show_llm_tui()` 新增 `penetration_text` 参数** — 可选，展示穿透深度摘要
- **Excel 报告页签名称加序号前缀** — 所有页签名统一添加 `N. ` 前缀（如 `1. 汇总`、
  `2. 市值核算` ... `10. 穿透深度分析`），与 HTML 报告章节顺序对齐

### Config
- `data/config/config.json` — `cache_ttl` 新增 `llm_penetration_deep: 86400`
- `data/config/llm_settings.json` — 新增 `temperature_penetration_deep: 0.5`,
  `max_tokens_penetration_deep: 4096`, `thinking_enabled_penetration_deep: false` 等 10 项
- `src/python/config.py` — `_DEFAULT_LLM_SETTINGS` 新增 `_penetration_deep` 系列默认值
- `src/python/cache.py` — `_CACHE_TTL_DEFAULTS` + `prefix_type_map` 注册 `llm_penetration_deep`
- `src/python/tui_menu.py` — `_show_llm_config_status()` 模型路由显示新增 `model_health_check`
  和 `model_penetration_deep`，共 5 条路由

## [0.2.29] - 2026-06-29

### Added
- **持仓体检报告** — 新增 LLM 生成模块，从风险分散度/流动性/收益合理性/成本结构
  四个维度对投资组合进行量化打分并给出改进建议
  - `generate_health_check()` / `_build_health_check_prompt()` / `_SYSTEM_HEALTH_CHECK` —
    核心生成函数、Prompt 构建、System Prompt
  - `_health_check_fingerprint()` — 稳定指纹计算（同智囊团，排除行情波动字段）
  - Excel 页签「持仓体检报告」— 调用 `write_llm_sheets()` 写入第 9 个页签
  - HTML 报告「九、持仓体检报告」— 模板新增第 9 节，条件渲染体检内容或占位提示
  - TUI 展示 — `_show_llm_tui()` 新增体检摘要框（提取综合评分行）
- **配置项** — `llm_settings.json` 新增 `_health_check` 系列 10 项配置（temperature / timeout /
  cache_enabled / max_tokens / model / system_prompt / thinking_enabled / thinking_budget /
  reasoning_effort / output_brief）
- **缓存支持** — `cache.py` 注册 `llm_health_check` 前缀（2h TTL），菜单 [2] 新增清除
  `llm_health_check_*` 缓存

### Changed
- **`generate_all_llm()` 返回 6 元组** — 原 `(macro, expert, macro_cached, expert_cached)`
  扩展为 `(macro, expert, health, macro_cached, expert_cached, health_cached)`
- **`write_llm_sheets()` 签名扩展** — `llm_content` / `llm_cached` / `model_names` /
  `thinking` 均从 2 元组扩展为 3 元组
- **`write_html_report()` 签名扩展** — `llm_content` 从 2 元组扩展为 3 元组
- **`_generate_excel_report()` 同步** — `llm_cached` 默认值从 `(False, False)` 扩展为
  `(False, False, False)`
- **`_cmd_generate_full()` 同步** — 6 元组解包 `llm_macro, llm_expert, llm_health, ...`
- **`_show_llm_tui()` 新增 `health_text` 参数** — 可选，展示体检摘要评分

### Config
- `data/config/config.json` — `cache_ttl` 新增 `llm_health_check: 7200`
- `data/config/llm_settings.json` — 新增 `temperature_health_check: 0.5`,
  `max_tokens_health_check: 4096`, `thinking_enabled_health_check: true` 等 10 项
- `src/python/config.py` — `_DEFAULT_LLM_SETTINGS` 新增 `_health_check` 系列默认值
- `src/python/cache.py` — `_CACHE_TTL_DEFAULTS` + `prefix_type_map` 注册 `llm_health_check`

## [0.2.28] - 2026-06-29

### Added
- **DeepSeek Extended Thinking 支持** — 检测到 `deepseek-v4-*` / `deepseek-chat` 模型时，
  使用 `output_config.effort`（"high"/"max"）替代 Claude 的 `thinking.budget_tokens`，
  实现与 Anthropic 协议兼容的思考深度控制
- **`reasoning_effort_*` 配置项** — `llm_settings.json` 新增 `reasoning_effort_global_macro` /
  `reasoning_effort_expert_review` / `reasoning_effort_news_correlation`，默认 `"high"`；
  Claude 忽略此字段，DeepSeek 模型自动读取
- **`_is_effort_model()` 检测函数** — 区分 Claude（`thinking.budget_tokens` 定量预算）
  与 DeepSeek（`output_config.effort` 定性深度）的 thinking payload 注入逻辑
- **`model_global_macro` / `model_expert_review` / `model_news_correlation` 配置项** — 支持为各 LLM 模块
  指定独立的模型名称，覆盖全局配置，默认 `null`（使用全局模型）

### Changed
- **`max_tokens_global_macro` 默认值 800→1024** — 增加宏观分析输出空间
- **`llm_settings.json` 同步** — 新增 `reasoning_effort_*`（3 项）和 `model_*`（3 项），
  `thinking_enabled_expert_review: true`，与代码默认保持完全一致

### Tests
- **新增 `TestIsEffortModel` 测试类** — 6 条用例覆盖 DeepSeek/Claude/空模型/大小写/前缀匹配
- **`TestSupportsExtendedThinking` 扩展** — 4 条 DeepSeek 测试用例（v4-flash / chat / 大小写）
- **`_is_effort_model` 导入验证** — 验证新导出函数可正确导入

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
- **`write_llm_sheets()` 新增 `thinking` 元组参数** — 透传两个 LLM 分析章节的开启状态至 `_write_content_sheet()`
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
- **config.json cache_ttl 键名规范化** — `llm_macro` → `llm_global_macro`、`llm_expert` → `llm_expert_review`、`llm_news` → `llm_news_correlation`，与缓存文件命名前缀保持一致

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
- **财经新闻热点与持仓关联分析分批并行化** — `enhance_news_correlation()` 分批处理从串行 `for` 循环改为 `ThreadPoolExecutor(max_workers=3)` 并行，6 批并行处理后墙钟时间降低约 60%（30s → ~10s）

### Added
- **模型路由** — `llm_settings.json` 新增 `model_macro` / `model_expert` / `model_news_correlation` 配置项，per-module 独立模型选择，未配置时沿用 `llm_key.json` 的全局 `model` 字段
- **Prompt Caching** — Claude API system prompt 使用数组格式 + `cache_control` 支持 Anthropic Prompt Caching，批量财经新闻热点与持仓关联分析时 5 分钟内同 system prompt 节省约 50% 输入 token 费用

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
  - 穿透 TOP10（资产穿透 TOP10）新增「预测EPS(2025E)」列
  - 基金业绩分析（基金业绩分析）新增「机构覆盖」列，显示研报家数和预测 EPS
  - 缓存策略：指数指纹 + 1 天 TTL 双因子失效
- **行业资金流向集成** — 调用 akshare `stock_sector_fund_flow_rank()` 获取今日行业资金流向排名
  - LLM 宏观分析 Prompt 注入前 5 个行业资金流向数据（名称、涨跌幅、主力净流入）
  - 缓存策略：指数指纹 + 15 分钟 TTL 双因子失效
  - 新增 `get_sector_fund_flow()` 函数，TUI 菜单 [1] 刷新时更新
- **分红历史集成** — 调用 akshare `stock_history_dividend()` 获取个股历年分红数据
  - 分类汇总（持仓分类表）新增「年均股息率」列：`avg_dividend / price × 100%`
  - 穿透 TOP10（资产穿透 TOP10）新增「年均股息率」列：原始 `avg_dividend` 值
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
- **文档精简**：`plan.md` 历史迭代（Iter 1.1~3.7）归档至 `docs-stm/plan/archived_plan.md`（已删除，内容分别并入 `docs-stm/archive/archived_plan.0.1.x.md` 和 changelog.md），原文件从 525 行精简至 70 行；`review-findings.md` 审计记录精简保留典型问题，从 135 行压缩至 50 行
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
- NEWS_COLS 财经新闻热点与持仓关联分析 运行流程：在 `aggregate_news()` 前先获取行业/概念数据并扩展关键词
- `check_and_refresh_caches()` 新增 `industry_*` 缓存自动清理（持仓变更时）
- `_check_and_warm_for_new_assets()` 新增新增资产行业分类自动预热（`batch_fetch_industry_data`）
- `_build_keyword_lookup()`：新增 `industry_data` 参数处理行业和概念板块关键词
- `_enrich_keywords_for_item()`：新增 `concept` 类型处理逻辑
- type_order 扩展：holding(0) → penetration(1) → concept(2) → industry(3)

### Docs
- requirements.md：数据源表、缓存文件清单、TTL 表、菜单 [1] 范围、资产穿透 TOP10 板块分类增强、财经新闻热点与持仓关联分析 关键词来源同步
- README.md：版本 v0.2.11、数据源表、缓存文件清单、菜单表、财经新闻热点与持仓关联分析 概念类型、缓存覆盖矩阵（菜单 [1]/[2] 矩阵表）
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
- requirements.md：同步菜单 [1] 缓存范围、缓存文件清单新增 `llm_news_corr_*`、TTL 表新增 `news_corr`、财经新闻热点与持仓关联分析 新增关键词富化/LLM 关联分析/Excel 格式优化描述、数据源表新增东方财富行业/概念板块
- README.md：版本 v0.2.9，同步菜单/缓存/财经新闻热点与持仓关联分析 描述
- testplan.md：新增关键词富化函数/Excel 格式/HTML 同步测试类别
- review-findings.md：新增最新一致性审查记录
- CLAUDE.md：新增缺陷自测规则要求

### Tests
- 新增 3 个测试类：TestBuildKeywordLookup、TestEnrichKeywordsForItem、TestWriteNewsSheetFormatting
- 新增 15 项测试：覆盖 lookup 构建（持仓/穿透/去重/空）、富化逻辑（三种类型、排序、空兜底）、格式断言（wrap_text、列宽、对齐）
- 全量 592 passed, 30 subtests passed

## [0.2.9] - 2026-06-28

### Added
- 财经新闻热点与持仓关联分析：新增配置选项 `llm_news_analysis`（默认关闭），开启后使用 LLM 对关键词匹配后的新闻进行二次关联分析，逐条判定关联度（高/中/低/无关）并给出原因分析
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
- LLM 全局四大优化：并行调用（ThreadPoolExecutor 并发生成全球政经局势/智囊团深度复盘）、httpx连接复用（全局 _HTTP_POOL 共享连接池）、LLM配置内存缓存（_LLM_CONFIG_CACHE 避免重复文件IO）、提示词紧凑化

### Changed
- 全球政经局势/智囊团深度复盘 用户提示词改为紧凑格式，减少约 35% 输入 token
- _build_macro_prompt / _build_review_prompt 输出格式精简，单行摘要替代多段描述

## [0.2.5] - 2026-06-27

### Fixed
- 持仓变更检测：新增持仓时自动预热 price/fund_perf/fund_hold 单条缓存；清除过期的 fund_benchmarks 和 penetration_cache 合并缓存
- 缓存降级覆盖：fetch_market_data / _fetch_with_fallback / fetch_indices 在 API 全失败时降级使用 7 天内过期缓存
- H 菜单语义修复：H 菜单生成"基础的 HTML"不再包含财经新闻（与 E/N/B 菜单的语义保持一致）
- 代码清理：移除 fetcher.py 中未使用的 tiantian_holdings 注册项、cache.py 前缀匹配边缘情况、未使用的导入变量

### Added
- Excel LLM 增补页签：全球政经局势（全球政经局势）和智囊团深度复盘（智囊团深度复盘）通过菜单 L 触发
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
- requirements.md: 全球政经局势/智囊团深度复盘 改为"Excel + HTML，LLM 增补项目"
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
- html_writer.py: 全球政经局势/智囊团深度复盘 模板占位文本（`llm_enabled=False` 时输出"本节内容待生成"提示）
- report_template.html: 新增全球政经局势（全球政经局势）和智囊团深度复盘（智囊团深度复盘）占位区域，`{% if llm_enabled %}` 条件渲染

### Changed
- main.py: TUI 菜单扩展为 13 选项，新增 [3] 清理过期缓存 / [4] 查看缓存统计
- main.py: TUI 菜单重构，E=核心 Excel（5 模块），N=Excel+新闻增补（6 模块）
- main.py: TUI 菜单 E→生 EXCEL 分析报告，N→生成包含新闻的 EXCEL 分析报告
- main.py: TUI 菜单 H→生成 基础的 HTML 分析报告（不含 LLM 增补）
- main.py: TUI 菜单 A→B 生成全系列包含新闻的报告 (Excel + HTML)
- main.py: `_cmd_generate_both` 改为 B 快捷键，生成 HTML + Excel（含新闻）
- tiantian.py: `fetch_quarterly_holdings` 重写为解析 `apidata.content` HTML（支持 GBK 编码）
- tiantian.py: `fetch_fund_holdings` 移除早期 return 阻塞季报回退路径的问题
- requirements.md: TUI 菜单表重构（11 选项，新增 B/L/R，更新 H 标签）；全球政经局势/智囊团深度复盘 改为 Excel + HTML
- README.md: 菜单表、配置说明同步更新；全球政经局势/智囊团深度复盘 改为 LLM 增补项目
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
- `src/report/news_correlation.py`: 财经新闻热点与持仓关联分析的 Excel 页签生成 + HTML 数据构建
- TUI 菜单新增 N 选项：生成包含新闻的 Excel 报告
- HTML 报告新增财经新闻热点与持仓关联分析（财经新闻热点与持仓关联分析）


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
- requirements.md/README.md: 基金业绩分析 列名修正为"持仓累计盈亏(¥)"/"持仓收益率"，缓存文件表移除 `fund_benchmarks.json` 重复项

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

---

> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
> 涵盖：项目初始化、Iter 1.1~1.4（骨架、配置、持仓读取、TUI 菜单、数据源接入、Excel 输出）。
