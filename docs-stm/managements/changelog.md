# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.10-dev] - 开发中（未发布）

### test-chart.html 动态注入脚本顺序修复（rf-248）

- **缺陷**：TD8 调试页 `src/static/test-chart.html` 引导脚本用动态 `createElement('script')` 注入 6 个 chart 资产，但未设 `s.async=false`。动态 script 默认 async=true **无序执行**，chart-init.js（约 13KB）可能先于 chart.min.js（约 200KB）执行，触发 chart-init.js 顶部守卫（`typeof Chart === 'undefined' || !window.ChartCommon`）静默 return，图表永不初始化——ok/degraded/empty 全场景实测均「0/6 图已初始化」、无 tooltip（用户 2026-08-06 另机复现；empty 场景仅 radar badge 走「占位」分支，其余图空白；偶发 800ms 自检时 Chart 尚未加载完成还会误报「引擎缺失」banner）。
- **修复**：注入循环补 `s.async=false`，保证脚本按注入顺序执行（chart.min.js → … → chart-init.js 最后），对齐报告模板 `defer` 语义。
- **影响范围**：仅调试页受影响；生产报告模板（report_template.html）/ whatif 模板（whatif_template.html）均用静态 `<script defer>`，执行顺序有保证，无此缺陷。
- **验证**：修复后待用户另机重测三场景（ok/degraded/empty 应 6/6 图初始化、tooltip 可用；offline 场景保留引擎缺失文本，属 R21 预期）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

---

## [0.10.9] - 2026-08-06

### LLM 空响应安全网扩展（关闭 thinking 重试 + thinking 并发信号量）

- **空内容诊断增强**：`llm/api_base.py::_extract_content` 空 content 诊断日志补充响应细节（stop_reason / block 结构 / HTTP 状态），出现 HTTP 200 + 空正文时可快速定位是 thinking 耗尽还是端点偶发异常。
- **安全网覆盖范围扩展**：DeepSeek 等强制推理模型在 `payload` 未显式携带 thinking 参数时也会落入默认思考模式（effort=high）占满 `max_tokens`，导致 `stop_reason=max_tokens` 无正文。`_api_claude.py` 安全网触发条件由「显式 thinking + 思考耗尽」放宽到「强制推理模型（`_is_effort_model`）或思考耗尽」；重试 payload 显式 `thinking.type=disabled` 并移除互斥参数（output_config / reasoning_effort），避免重试再次触发思考。
- **thinking 并发信号量**：`generators_orchestrator.py` 新增 `llm_max_thinking_concurrency`（默认 1）BoundedSemaphore，约束开启 Extended Thinking 的模块（health_check / expert_review 等 `thinking_enabled_{suffix}=true`）同时最多 N 个在跑，从源头降低多 thinking 模块并发涌向 DeepSeek 时偶发空 content（HTTP 200 空响应）的概率；非 thinking 模块不受此限，总并发仍受 `llm_max_concurrency` 约束。新键登记至 registry `get_known_llm_settings_keys()`，默认模板 `_llm_settings_defaults.py` 同步生成。
- **配置同步**：`data/config/llm_settings.json` 全局设置区补 `llm_max_thinking_concurrency: 1`；how-to-config-llm.md（全局配置 8 项说明 + 完整范例）、requirements.md（全局配置参数表）、llm-technical.md（全局键名清单 + 4.2 并发控制段落）、testplan.md（llm/ 包覆盖描述补 thinking 并发信号量）同步。
- **测试**：test_llm_api.py 新增强制推理模型空 content 关闭 thinking 重试用例；test_generate_all_llm.py 新增 `TestThinkingConcurrencyLimit`（thinking 模块串行/非 thinking 不受限/总并发不超限）；test_llm_api_base_edge.py 空 content 诊断断言；test_registry.py `test_llm_settings_keys_count` 断言由 86 更新为 87（新增全局键）。LLM 测试全部 mock `call_llm` / `call_llm_with_retry` / `make_http_client`，无真实 API 调用。
- **门禁**：dev-verify 1862 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 报告子模块无候选/无数据时页面提示 + data_quality 缺省开启（rf-247）

- **候选基金无配置提示**：`candidate_compare` 子模块开启但 `config.comparison_candidates` 未配置（或全部代码非法）时，原先 HTML 端静默跳过候选基金比较区块、Excel 端静默不写，用户无从判断原因。现在 HTML 模板（report_template.html）外层守卫改为 `{% if candidate_data %}` + 内部 `available` 分支，无候选时渲染「📭 未配置候选基金（config.comparison_candidates 为空），无法输出候选基金比较…」占位（含被忽略的非法代码列表）；Excel 端新增 `_write_candidate_unavailable_block`（标题 + `_write_placeholder` 占位）；`html_renderers.py` 同步 `prog.warn` 提示。
- **成本流水无数据提示**：`cost_lots` 子模块开启但持仓 Excel 未录入交易/分红流水时，HTML 端盈亏汇总区补「成本流水子模块已开启，但持仓 Excel 未录入交易/分红流水，资金加权收益率 (XIRR)、成本分档、分红累计无法计算」提示（Excel 端 summary.py 已有占位，本次对齐 HTML 端）。
- **data_quality 缺省开启**：`report_submodules.data_quality` 默认值由 `false` 改为 `true`（数据质量仪表盘 = 品种覆盖 + 可信度，属长期可信核心，开箱即得）；访问器 `is_enable_data_quality` 兜底逻辑（report_submodules 缺失/非 dict/data_quality 键缺失）同步改为缺省 `true`，与 `enable_action` 缺省开启口径一致；配置生成模板注释同步。
- **文档同步**：how-to-config.md（示例配置 + 参数表默认值）、how-to-menu.md（子模块默认说明）、requirements.md（`report_submodules` 默认值）、technical.md（功能语义命名表 data_quality 行默认开）、reports-instruction.md（候选基金比较子表补充「无候选时占位提示」行为说明）、test-coverage.md + folders.md（测试计数快照刷新：`all` 5,146→5,196、dev-verify 1,846→1,864）。
- **测试**：test_fund_performance.py 新增 `TestWriteCandidateUnavailableBlock` 2 用例（无候选写占位 / 占位列出非法代码）；test_html_writer.py 候选基金无候选渲染拆 3 例（None 不渲染 / available=False 显示未配置提示 / invalid 列表显示）+ 成本流水空数据提示 2 例；test_config.py `TestIsEnableDataQuality` 重写为默认 true + 新增 `_DEFAULT_CONFIG` 断言；test_handlers_config.py 数据质量默认开（toggle 测试改关）。
- **门禁**：定向 250 passed；dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 历史走势默认自动获取 + 关闭时醒目警示（rf-245）

- **警示修复**：`fetch_history=False`（历史走势关闭/跳过）时原先静默返回 `None`，下游只剩误导性的「尾部风险：无历史 bars」占位警告，用户无法判断是配置关闭所致。现在 `report/_snapshot.py::fetch_history_data` 在 fetch 关闭时通过 `reporter.warn`（[!] 黄色）+ `logger.warning` 醒目提示「组合历史走势获取已跳过（history off）」及占位后果（历史走势/回撤章节、尾部风险指标、累计收益率等显示"数据不可用"），并提示开启方式（CLI `--history auto`）。
- **默认值调整**：CLI `--history` 默认值由 `off`（跳过）改为跟随配置层——未显式传参时 `generate_report` 按 `config.history.fetch_mode`（`off`/`auto`/`prompt`，默认 `auto`）决定是否获取。`auto`/`prompt` 均视为获取（prompt 为 TUI 交互询问，CLI 非交互场景按获取处理），仅 `off` 跳过。config.json 默认 `fetch_mode="auto"` 不变，新用户开箱即获取组合历史走势。
- **影响**：`both`/`full` 报告默认包含组合历史走势/回撤、尾部风险、累计收益率等数据（原来默认占位）；`--history off` 可显式跳过。包装脚本（`cli.sh`/`cli.ps1`）无参数默认 both 同样受益。
- **文档同步**：how-to-start.md（`--history` 参数表默认说明 + 报告类型段落）、cli.sh/cli.ps1 头部注释（历史走势默认 auto 获取）。
- **测试**：`test_orchestrator.py` 新增 `test_generate_report_both_fetch_history_follows_config`（配置驱动解析 off/auto/缺失三态）+ `test_fetch_history_data_fetch_false` 增加警示断言；`test_cli.py` 默认断言更新（`--history` 未传 → None）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### Excel 序号收敛到导航层（页签栏 + HTML 标题）（rf-244）

- **设计调整**：序号只在 Excel 页签栏 tab 名与 HTML 章节标题出现，Excel 正文标题统一为纯中文名（与投资组合概要/市值/分类/穿透/基金业绩/数据源可用性矩阵一致）。撤除 rf-243 引入的正文标题序号同步机制（`get_report_section_number_from_order`、create_sheets 的 `visible_number` 标记、7 个页签写入函数的 `section_order` 透传），回归更简设计——正文不依赖序号，调整配置/隐藏章节不会错位。
- **效果**：Excel 页签栏保留连续序号（行动建议=10、组合演进=13、数据源可用性矩阵=14），正文标题为「行动建议」「组合演进」「数据源可用性矩阵」纯中文名；HTML 章节标题保留序号。
- **测试**：test_correlation_sheet 正文标题断言更新为纯中文名；191 受影响单测 + dev-verify 1864 passed；4 项 trace `--ci` 全 [OK]。

### cli.ps1 补 UTF-8 BOM，修复 Windows PowerShell 中文解析崩溃（rf-246）

- **缺陷**：`scripts/cli.ps1` 文件头注释声称 "Encoding: UTF-8 with BOM"，实际文件**无 BOM**。Windows PowerShell 5.1 对无 BOM 的 UTF-8 中文按 ANSI/GBK 误读，导致中文注释解析崩溃（"字符串缺少终止符" / "语句块或类型定义中缺少右}"），跨机器复现（另一台电脑运行同样报错）。
- **修复**：补回 BOM（`EF BB BF`，UTF-8 + CRLF），PowerShell Parser 验证通过（`[System.Management.Automation.Language.Parser]::ParseFile` 无 errors）。
- **编码纪律落盘**：CLAUDE.md 技术要点新增「编码/BOM（Windows 脚本）」条目——`*.ps1` 必须 UTF-8 BOM + CRLF，否则 PS 5.1 按 GBK 误读崩溃；新增 `.editorconfig`（`[*.ps1] charset = utf-8-bom, end_of_line = crlf`），支持 EditorConfig 的编辑器**跨机器自动遵守**，避免此问题在其他电脑复发。
- **文档同步**：folders.md 目录树登记 `.editorconfig`。
- **验证**：BOM 字节（`ef bb bf`）+ PowerShell 解析器双重确认；CLI 包装脚本功能不受影响。

### Excel 正文标题序号跟随报告章节顺序配置（rf-243）

- **缺陷**：`report_section_order` 配置生效后，Excel 页签栏 tab 名按 create_sheets 可见连续序号重编号（行动建议=10、组合演进=13、数据源可用性矩阵=14），但 7 个深度分析页签（行动建议/组合演进/基金经理变更/持仓集中度/持仓关系矩阵/风格与因子/组合历史走势回撤）正文标题仍用注册表默认序号（行动建议=17、组合演进=16），与页签栏不一致。
- **修复**：create_sheets 创建页签时就地标记 `visible_number`（与 tab 名同源）；registry 新增 `get_report_section_number_from_order`，正文标题按「可见连续序号 → 配置序号 → 注册表默认」取值；7 个页签写入函数新增 `section_order` 参数，excel_generator / excel_fund_deep_analysis 透传配置后 order。正文标题与页签栏序号现完全一致。
- **说明**：该方案随后被 rf-244 设计调整取代——正文标题统一为纯中文名，序号仅收敛到导航层，本条目保留作过程记录。

### 报告页签显示顺序配置（行动建议提前至第 10 位）

- **配置**：`config.json` 的 `report_section_order` 由 `{}`（使用注册表默认）改为**完整配置 18 项**——`action`（行动建议）置于序号 10，原 10-16 依次顺延（`news_correlation`=11、`global_macro`=12、`expert_review`=13、`health_check`=14、`penetration_deep`=15、`portfolio_history_drawdown`=16、`portfolio_evolution`=17），`data_source_status`=18，`llm_usage` 强制末位。注册表默认值（行动建议=17）未改，清空该字段即恢复默认。
- **效果**：Excel 页签与 HTML 章节顺序/标题编号同步变化——行动建议提前至第 10 位，财经新闻/全球政经/智囊团/持仓体检/穿透深度/组合历史走势/组合演进依次顺延；数据源可用性矩阵编号不变（both 模式 14、full 模式 18）。
- **文档同步**：reports-instruction.md（主表 + 分组表重排）、requirements.md（§6.3 表 + §6.4.x 小节物理重排与重编号）、how-to-config.md（默认序号表后补本仓库配置说明）、technical.md（注册表 number 描述两处补配置说明）、faq.md（§13 智囊团引用）。
- **门禁**：dev-verify 1864 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。注册表默认值未改，test_registry 等断言不受影响。

### 行动建议章节默认开启 + 菜单 P 可视化开关

- **默认值调整**：`enable_action` 由默认关闭改为**默认开启**——`_config_defaults._DEFAULT_CONFIG["enable_action"]=True`；`get_config()` 合并逻辑以默认值打底，现有用户 config.json 缺失该键时自动补为开启（显式 `false` 的用户保持关闭）。访问器 `is_enable_action()` 缺失时返回 True，日志提示「缺少 enable_action，使用默认值 true」。
- **菜单 P 新增开关**：TUI 菜单 `[P] 配置报告可选章节` 面板新增第 5 项「行动建议（再平衡信号/交易纪律/调仓建议/收益归因）」，与既有 4 个章节组一致地交互切换；LLM 分析章节提示顺延为第 6 项。菜单 P 主菜单 label 同步加入「行动建议」。
- **行为影响**：开启后 E/B/L 报告均输出行动建议章（number=17，type=action）；关闭时章节隐藏且智囊团深度复盘隐藏「行动摘要」子块，剩余章节自动连续编号。
- **文档同步**：how-to-config.md（默认值表/章节可见性表/菜单归属/章节对照 5 处）、how-to-menu.md（主菜单 label/脚注/章节说明/菜单 P 详解 4 处）、faq.md、how-to-use-registry.md、requirements.md、reports-instruction.md、technical.md 全文「默认关」→「默认开，菜单 P 可切换」。
- **测试**：`TestIsEnableAction` 新增 `test_default_config_says_enabled`（断言 `_DEFAULT_CONFIG["enable_action"]` 为 True）；`test_default_true_when_missing` 保持缺失→True；test_registry/test_action_html/test_report_chapter_consistency 注释同步。
- **门禁**：dev-verify 1846 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 事实校验两处误修正修复（rf-239）

- **缺陷 1：名称指代主体定位平局误路由**。真实报告「止盈纪律」句「建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%」中，171.23% 被误修正为 70.2%（601398 工商银行收益率）——`_locate_subject_code` 名称分支用起点距离 `abs(idx-anchor)`，建设银行(idx=0)与工商银行(idx=16)距 anchor=8 平局，先迭代者（工商银行）胜出，把 601939 的**正确** 171.23% 判错并改写。修复：名称分支改用**最近边距离** `min(abs(idx-anchor), abs(idx+len(name)-anchor))`，与代码分支一致，紧邻数值的名称唯一胜出。
- **缺陷 2：风险警戒阈值误修正**。同句「设立止损线：当前亏损-11.80%，已接近回调20%的警戒区域」中，「回调20%」是止损警戒阈值而非收益率声称（实际 -11.80% 同句另述且正确），却被误修正为 -11.8%（159222）。修复：`_is_trim_target_context` 增加警戒阈值检测——新增 `_WARNING_THRESHOLD_KEYWORDS=("警戒",)`，数值前后更宽窗口（-25/+8）内出现警戒词即判定为风控阈值，跳过收益率比较。
- **测试**：新增 `TestNameSubjectNearestEdge`（3 用例）+ `TestWarningThresholdContext`（3 用例）回归测试，修复前均失败；fact_checker 单文件 109 通过；完整合成稿+真实持仓端到端复现 corrections 由 2 处降为 0。
- **门禁**：fact_checker 单文件 109 passed（未跑全量，用户要求最小验证）。

### 菜单 P 新增报告增强子模块配置（6 项区块级开关）

- **新增访问器**：`config.is_enable_industry_beta()` 读取 `report_submodules.industry_beta`——与 data_quality / candidate_compare / cost_lots / valuation_percentile / market_temperature 五个既有访问器一致，导出至 `src.python.config`。
- **菜单 P 子菜单**：TUI 菜单 `[P] 配置报告可选章节` 新增第 6 项「报告增强子模块」，进入子菜单逐项切换 6 项区块级开关（数据质量仪表盘 / 行业Beta子表 / 候选基金比较子表 / 成本流水 / 估值分位 / 市场温度，默认全关），实时保存到 `report_submodules`；LLM 分析章节提示顺延为第 7 项。菜单 P 主菜单 label 同步加入「报告增强子模块」。
- **文档同步**：how-to-menu.md（主菜单 label / 菜单 P 详解）、how-to-config.md（6 行 report_submodules 配置方式 手动编辑 → 菜单 P → 6）。
- **测试**：`TestIsEnableIndustryBeta`（5 用例）+ `TestConfigReportSubmodules`（4 用例，mock 输入/配置读写），定向 13 passed（本机慢，全套在另一台电脑运行）。

### 测试污染真实快照目录修复（rf-240）

- **缺陷**：`test_corrupt_snapshot_file_skipped` 用 `from src.python.core.constants import HISTORY_SNAPSHOT_DIR` 在 import 时把快照目录**旧值**拷贝进测试模块，绕过 conftest `_isolate_sensitive_paths` 的 monkeypatch 隔离，把测试用损坏文件 `snapshot_corrupt.json` 写入**真实** `data/history/snapshots/`。后果：每次生成报告时 `[WARNING] 文件损坏 snapshot_corrupt.json`（程序自动跳过，不阻塞报告，但持续刷日志），且跨机器残留（另一台电脑运行过测试即同样产生）。
- **修复**：测试文件改用 `import src.python.core.constants as core_constants` 模块属性访问 `core_constants.HISTORY_SNAPSHOT_DIR`，使 conftest 隔离生效——损坏文件写入 `tmp_path` 而非真实目录。生产代码 `snapshot_diff.py` 经 `history_snapshot.load_all` 读取（模块属性引用）本就不受影响。
- **清理**：已删除本机残留的 `data/history/snapshots/snapshot_corrupt.json`（未跟踪的测试垃圾，非用户数据）。其他机器同样删除该文件即可。
- **回归验证**：edge 测试 6 passed，运行前后真实快照目录 diff 无新增残留。

### 数据质量仪表盘区块渲染崩溃修复（rf-241）

- **缺陷**：`report_template.html` 数据质量仪表盘「品种覆盖/可信度」区块中 `position_status.items` / `data_freshness.items` 在 Jinja2 命中 dict 内置 `items` 方法（bound method）而非契约键 `"items"`——`data_quality` 子模块开启且契约有数据时，guard 恒真，`{% for item in ... %}` 迭代 bound method → `TypeError: 'builtin_function_or_method' object is not iterable`，HTML 报告生成失败（另一台电脑菜单 L 实测崩溃）。该缺陷自数据质量仪表盘引入（87a137a4）即存在，因 `data_quality` 默认关、既有测试未开启该子模块渲染模板而漏测。
- **修复**：guard 与循环改用 `.get("items")`（与生产代码 `data_freshness.get("items")` 一致）；空 items 时正确走降级占位「未获取行情数据，品种覆盖无法判定」而非进入空表。
- **回归**：新增 `TestHtmlDataQualityBlocks` 4 用例（品种覆盖渲染/可信度渲染/空 items 占位/data_quality 关闭跳过），修复前 `_render_template` 抛 TypeError。
- **门禁**：dev-verify 全量通过 + 4 个 trace 检查全 [OK]。

### 数据质量仪表盘测试覆盖补强

- **可信度（`test_data_freshness.py`）**：新增 dict 形式明细分类（`_detail_value` dict 分支）、跳变检测跳过无 code/None 明细、摘要未显式传交易日自动推断、昨收为 0 时 `change_pct` 记 0.0 不除零；新增 `_infer_latest_nav_date` 直接测试（取最新净值日期 / 忽略无效日期 / 无净值回退当天日期）。
- **品种覆盖（`test_holding_status.py`）**：新增大写 SH/SZ/BJ 交易所前缀归一、单字符简称不子串匹配、dict 形式明细标注、股票「暂无行情」判可能退市、同代码多条明细取首条（`setdefault` 语义）。
- **页签写入（`test_data_quality_sheet.py`）**：新增 `build_coverage_block` 全部正常 abnormal_count=0、契约 available=True 但缺 items 键容错。
- **HTML 渲染（`test_html_report_structure.py`）**：新增报告头部数据异常摘要告警行（异常时显示 summary + 章节号引用、正常时隐藏）与异常行 `src-matrix-failed`/正常行 `src-matrix-ok` 高亮断言。
- **门禁**：四文件 162 passed；dev-verify 1864 passed + 4 个 trace 检查全 [OK]；ruff format 已一致。

### 报告生成骨架测试污染真实 reports 目录修复（rf-242）

- **缺陷**：`src/test/unit/report/test_orchestrator.py::test_generate_report_skeleton` 用 `config={}` 真实调用 `generate_report(holdings=[], ...)`——report_type 默认 basic（仅生成 Excel 不写 HTML），且未 patch `generate_excel_report` 写盘函数。`output = output_dir or config.get("output_dir", "reports")` 在 `config={}` 时 fallback 到相对路径 `"reports"`，解析为真实 `reports/` 目录；空持仓每次生成一个空页签 Excel 归档（`reports/{YYYYMMDD}/个人投资分析报告-*.xlsx`）+ 覆盖根目录最新版，跨整天累积 37 个残留文件。该缺陷被 `result.excel_ok=True`/`report_generated=True` 断言掩盖（basic 路径正常返回成功），既有测试未校验输出目录隔离而漏测。
- **修复**：传入 `output_dir=tempfile.TemporaryDirectory()` 隔离输出到临时目录，保留真实生成流程（骨架返回 ReportResult 断言不变）。
- **清理**：删除 reports 目录下全部 37 个空页签归档 + 根目录空最新版（均已验证不含真实持仓数据，抽样 + 全量扫描 0 命中）。
- **回归验证**：重跑 `test_orchestrator.py`（50 passed）+ `--mode report` 全量（1488 passed）后 reports 目录零新增。

### 报告输出目录兜底防线（rf-242 加固）

- **新增 conftest autouse fixture**：`_isolate_report_output_dir` 统一安装，把两个真实落盘入口——`excel_writer.save_workbook`（`excel_module_loader` 运行时 `from ... import save_workbook` 取到被 patch 后的模块属性，报告链路天然覆盖）与 `html_save._save_html_report`/`html_writer._save_html_report`（模块级拷贝引用，两处一起 patch）——收到的输出目录解析后等于项目真实 `reports/` 时透明重定向到 `tmp_path/reports`。测试漏传输出目录（如 `generate_report` 在 config 缺 output_dir 时 fallback 到相对路径 `"reports"`）不再污染真实 reports 目录。判定基于绝对路径相等，显式指向临时目录的测试不受影响；测试自身 mock 写盘函数会覆盖本包装。
- **回归守护**：`test_generate_report_skeleton` 恢复为 `config={}` 不传 output_dir 的真实调用（复现缺陷场景），用运行前后 `reports/` 文件快照断言无新增，作永久回归守护——防线失效即测试失败。
- **验证**：test_orchestrator 50 passed；report 模式全量 1488 passed；dev-verify 1864 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致；全程 reports 目录零新增。

### CLI 命令行包装脚本（cli.sh / cli.ps1）

- **新增**：`scripts/cli.sh`（Linux/macOS）与 `scripts/cli.ps1`（Windows PowerShell）——CLI 命令行模式的便捷入口。**无参数调用时默认生成报告**；传入参数时原样透传给 CLI，与直调 `python -m src.python.cli <args>` 完全等效。
- **无参数默认类型**：`report --type both`（Excel+HTML 双格式、不含 LLM、全部页签有数据）——响应实测反馈：初始默认 basic（约 1 分钟仅 Excel）只生成核心 5 页签 + 数据源矩阵，新闻/历史/LLM 相关页签为降级占位，不符合"无参数=完整报告"预期，故改为 both。注意：这仅改变**包装脚本**的无参数默认；CLI 本身 `--type` 默认仍为 basic（直调 `python -m src.python.cli report` 不带 `--type` 仍是轻量模式）。
- **实现**：自动切换到项目根目录并定位虚拟环境解释器（`.venv/bin/python` / `.venv\Scripts\python.exe`），缺失时提示先运行 launch.sh / launch.ps1 初始化；创建基础数据目录（data/holdings、data/cache、data/config、docs-stm/tmp、logs）；退出码透传 CLI 结果（0=成功/1=部分失败/2=严重错误）。
- **文档同步**：folders.md 目录树登记两文件 + 统计表说明补充；scripts-reference.md 一览表与启动脚本章节新增两条（同时给出直调 python 与包装脚本两种调用方式，并说明包装脚本默认 both 与 CLI 默认 basic 的差异）；how-to-start.md CLI 模式一节补充「便捷入口」用法 + 三种报告类型差异说明。
- **验证**：both 模式实测 14 页签中 13 个有实质数据（仅组合历史走势因 `--history` 默认 off 为占位，加 `--history auto` 可得）；`--help`/`report --help`/`cache --help` 参数透传正常；bash -x 确认无参数 `set -- report --type both`；dev-verify 1864 passed + 4 个 trace 检查全 [OK]；运行期间 reports 目录零新增。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.8（2026-08-04 ~ 2026-08-06）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
