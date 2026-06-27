# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

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
