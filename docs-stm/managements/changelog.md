# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.8.8-dev] - 未发布

### Fixed
-（待补充）

## [0.8.7] - 2026-07-27

### Added
- **三层性能基准体系（P3-13）**：① `perf.py` PerfCollector 在 `generate_report()` 三路径（basic/both/full）嵌入轻量计时埋点，每次运行自动记录各阶段耗时到 `data/state/perf_history.jsonl` ② `scripts/perf_report.py` 保留独立基准脚本（mock 外部源）用于精准回归检测 ③ `scripts/perf_view.py` 趋势查看工具读取历史文件输出版本间耗时对比 Markdown 表格。遵循 C3（原子写入）、C8（统一日志）、C14（局部实例非单例）、C16（路径绝对化）约束
- **数据源健康检查自动收集**：每次客户端生成报告时，后台并行运行全量数据源健康检查（HTTP 连通性+延迟），结果存入 `data/state/datasource_health.jsonl` 并注入 DegradationTracker，供数据源可用性矩阵章节（#17）实时展示。`handlers_check_sources.py` 提取 `run_health_checks()` 返回结构化数据，CLI `check-sources` 命令保持不变

### Fixed
- **excel_b_series.py `NameError: _fetch_fund_holdings_cached`**：P2-6（提交 `259e4b4`）将本地私有函数 `_fetch_fund_holdings_cached` 提取到 `fetcher/fund.py` 为公开函数 `fetch_fund_holdings_cached`，删除了本地定义并更新了导入名，但调用点（`_process_b_module` 第 36 行）仍使用旧私有名 `_fetch_fund_holdings_cached`，导致 `enable_b_series=True` 且持有基金时触发 `NameError`，持仓重合度/集中度/风格分析三个模块均回退为占位。修复：导入 `fetch_fund_holdings_cached` 并修正调用名
- **新闻去重 cross_merge_bg2 梯度规则 78% 误判**：v0.8.6 引入的 bg=2 + ratio≥0.40 梯度规则实际仅 2/9 pair 正确合并，其余 7/9 为高频金融 bigram（"指数""涨""成交""额"）导致的虚假重叠（如"N长鑫成交额1300亿"误合并为"沪深总成交额20766亿"、"港股开盘"误合并为"日经225收盘"）。移除该规则，恢复纯 bg≥3 合并条件。涉及 `news_aggregator.py`、`calibrate-dedup-threshold.py`、`test_news_sources.py`

### Changed
- **代码/测试注释历史迭代痕迹清理（6 轮）**：全面清除源码注释、测试注释/描述、管理文档正文（changelog.md/plan.md/review-findings.md 除外）、用户文档中的所有历史变更痕迹。覆盖模式包括「不再」「向后兼容」「保留供兼容」「已废弃」「原有的」「此前」「曾」「已迁」「已拆分」「已改为」等，累计修复 50+ 处。涉及 8 个源码文件、5 个测试文件、3 份管理文档、3 份用户文档。豁免文件按约定保留历史记录
- **P3-11 问题描述修正**：`review-findings.md` P3-11 从错误描述的"async 异步化"修正为 ThreadPoolExecutor 批量并行方案，对齐 C5/C6/C2/C3/§1.4.5 架构约束
- **迭代计划文件同步**：`plan-engineering.md` 大文件拆分/性能基准段标记为已完成，异步化段重写为 TPE 并行方案并补齐架构约束分析；`plan-documentation.md` ADR 段标记为搁置并记录原因；`perf-three-layer-plan.md` 归档至 `archive/v0.8.x/perf_report/`

### Docs
- `review-findings.md` P3-11 补充架构耦合约束脚注（C5/C6/C2/C3/1.4.2/1.4.5）


## [0.8.6] - 2026-07-27

### Added
- **数据源可用性矩阵**：新增报告章节 #17（always 类型），在 Excel/HTML 报告末尾统一展示所有数据源运行状态（正常/降级/失败），聚合 DegradationTracker 会话事件按类别（行情/基金排名/行业分类/指数等）归总；Excel 页签含颜色标注和失败明细，HTML 表格含状态图标和详情列

### Fixed
- **cost_tracker 全局预算 xdist 竞态**：`_input_budget` 和 `_budget_warned` 为模块级全局变量，xdist 并行时其他测试通过 `patch("src.python.llm.session.get_session_usage")` 污染 worker，导致 `get_budget_status()` 中 `usage.get("input_tokens", 0)` 返回 MagicMock 而非 int，`max(0, input_budget - MagicMock)` 抛出 TypeError。修复：`_auto_reset_cost_tracker` autouse fixture 增加 `reset_session_usage()` 调用，每次测试前同时重置 session 用量 + budget，确保 `get_budget_status()` 读取到干净的 int 数据；修复 4 个失败用例（`test_cost_tracker.py::TestBudgetManagement`）
- **穿透测试 HTTP 请求遗漏 mock**：`_prefetch_manager_data()` 在 `compute_penetration_top10()` 中遍历基金调用 `fetch_fund_manager(code)`（每只基金一次 HTTP 请求），`mock_all_apis` 未 mock 该函数导致穿透性能测试实际发出 10 次网络请求耗时 17s — 在 `test_e2e_perf.py::mock_all_apis` 中补回 `patch("src.python.report.penetration.fetch_fund_manager", return_value=None)`
- **`orchestrator.py` 历史走势获取失败时 NoneType 崩溃**：`fetch_history_data()` 可返回 `None`（数据源不可用/异常），但行 763 无条件调用 `.get()` 导致 `AttributeError` — 增加 `if history_data:` 保护，为 None 时跳过全量量化指标计算

### Changed
- **`_extract_entity_bigrams()` 英数专名 `_tk:` 加权**：长度 ≥4 的英文专名（Anthropic/Meta/Helios 等）在实体 bigram 中额外插入 `_tk:` 前缀虚拟 bigram，使 `Anthropic+Meta` 等英数专名重叠的跨源标题即使 ratio<0.40 也能通过 bg≥3 候选区合并，无需降低 ratio 阈值；新规则下 cross_skip 从 3956 降至 10（单次运行）
- **新闻去重跨源梯度阈值**：bg=2 且 ratio≥0.40 时合并（cross_merge_bg2），覆盖 bg=2 实体重叠少但 ratio 较高的重复案例（如"微软Azure Helios" vs "AMD+微软Azure Helios"），对应 616 条遗漏中 ~301 条被捕获
- **`_normalize_title()` 增加孤立年份剥离**：`\b(?:19|20)\d{2}\b` 正则过滤独立 4 位年份数字（1900-2099），减少共享"2026""2025"等年份导致的 SequenceMatcher 虚高
- **`calibrate-dedup-threshold.py` 适配新规则**：新增 cross_merge_bg2 分组统计、梯度阈值边界分析、0.35~0.40 灰色带审查提示

### Docs
- **内部文档序号/组织校对**：全量审核 6 份文档并修复不一致——llm-technical.md（§2.1 去硬编码计数、§9.1 合并子节、§5.1 新增 `_call_gemini()` 图文）、how-to-start.md（示例数据段并入提示）、how-to-config.md（章节 A→J 重新排序 + 新增 risk_free_rate/rebalance/anonymization 等）、reports-instruction.md（#17/#18 序号对齐 6 处）、how-to-use-registry.md（绘图分析→历史回撤分析）、faq.md（E 菜单范围修正）
- **config JSON/章节标题三向对齐**：`_config_defaults.py` 注释标签、config.json JSON 标签、how-to-config.md 描述三方同步为 `B. 报告章节可见性` / `F. 业绩基准与无风险利率`
- **统计数据全量刷新**：folders.md（源码 146/39,294、测试 189/57,960、用例 3765、文档 87）、test-coverage.md（all 3765，11 子组项数同步）
- **plan.md 与 review-findings.md 同步**：6 份 plan 子文档纳入 plan.md 分层管理（P2 ~22d / P3）；plan-engineering.md 内容登记至 review-findings.md（P3-11 HTTP 同步 / P3-13 性能基准）
- **已实现功能状态标注**：plan-documentation.md §1（数据源可靠性文档 ✅）、plan-web-ui.md §4（数据源可用性矩阵 ✅）


## [0.8.5] - 2026-07-24

### Fixed
- **CI 超时 & 退出码混乱**：`regression` 和 `verify` Phase B 的 600s 超时在 CI 慢速 runner 上频繁截断场景测试；超时退出码 `-1` 经 `sys.exit()` 转为 255，难以区分与真实崩溃 — 增加默认超时到 1200s，CI 全部加 `--no-timeout` 禁用超时，超时退出码改为标准 124

### Changed
- **P0 提交门禁优化**：`regression`（~6min 全场景）改 `dev-verify`（~1min 核心单元+基础场景）—— 最频繁的编辑-验证循环从 6 分钟降为 1 分钟，释放开发效率
- **verify 模式瘦身**：移除 Phase B 场景测试（重复 P0 regression），仅保留单元测试（~50s 而非 ~5min）—— 场景测试由 P0（dev 提交）和 P2（版本发布）覆盖
- **P2 发布门禁优化**：`all`（3741 测试，~6.5min）改 `verify,regression`（单元+场景，1306 测试，~3min）—— 减少 65% 测试量，仍覆盖核心通路
- **`src/test/` 目录结构全面重组**：
  - `unit/` 新增 `analysis/` 子目录：9 个分析计算测试文件从根目录移入（流动性/再平衡/汇率/债券收益率），标记 `unit_providers` → `unit_analysis`
  - `unit/` 新增 `cli/` 子目录：`test_cli.py` / `test_cli_edge.py` 从根目录移入
  - `unit/` `test_cost_tracker.py` 移入 `llm/`，标记 `unit_providers` → `unit_llm`
  - `unit/` `test_orchestrator.py` 从根目录移入 `report/`
  - `scenario/` 新增 `perf/` 和 `security/` 子目录：`test_e2e_perf.py` / `test_security.py` 从根目录移入；`test_chain_resilience.py` 移入 `resilience/`；`test_llm_hallucination.py` 移入 `llm/`
  - `integration/`：`test_cli_integration.py` 从根目录移入
  - `unit/conftest.py` `_DIR_TO_MARKER` 补齐 `analysis`/`cli`/`handlers` 映射，新增标记校验兜底
  - 清理空目录 `unit/report/template/`
  - 根目录 4 个"流浪"测试文件全部归位，`src/test/` 根目录不再有除 `conftest.py`/`helpers.py`/`__init__.py` 外的测试文件

### Docs
- **门禁文档同步**：CLAUDE.md、how-to-test-my-code.md（10 处）、testplan.md、test-coverage.md（verify 项数 2180→~1022）、scripts-reference.md（4 处）– 与 verify 瘦身/P2 优化对齐
- **目录树全量同步**：`folders.md` — 更新统计（源码 143→144、测试 177→185、用例 3616→3760、文档 73→81）；展开测试子组完整目录树（unit 含 11 子组含 analysis/cli、integration 含 test_cli_integration、scenario 含 6 子组含 perf/security、data/hallucination 数据集）；补充 `_validation.py`、`__init__.py`、`.github/workflows/ci.yml`、`pytest.ini`、`reason.bat` 等新文件；清理冗余版本描述
- **测试重组同步**：CLAUDE.md C12 示例路径加 `unit/analysis/` 前缀；testplan.md P0 引用 `regression` → `dev-verify` + hallucination 路径更新；test-coverage.md 新增 analysis 行、功能域表同步、场景测试源统计更新；how-to-test-my-code.md Quick Start/P0 门禁/工作流图/unit 子组数对齐
- **数据源文档补充**：`datasource.md` — 新增"持仓重合度"(`fund_overlap_`)和"基金风格扩展数据"(`extended_`)两条数据源；`bond_yield_rf` 标注精确缓存键脚注；补充 exact_cache_keys 仅模块说明

---

## [0.8.4] - 2026-07-22

### Fixed
- **`metrics.py` 零方差浮点精度（Linux CI）**：`sharpe_ratio()` 和 `individual_volatility()` 使用 `variance == 0` 精确比较，但 Linux 上 `[0.001]*252` 的方差计算因浮点精度返回 `~6.8e-41` 而非 0，导致夏普返回天文数字而非 None、波动率返回 `1e-17` 而非 0.0 — 改为 `< 1e-15` epsilon 容差
- **`test_fund.py` threading.Lock 类型检查兼容**：Python 3.10 某些平台上 `threading.Lock` 在 `isinstance()` 中非 type 类型 — 改用 `type(threading.Lock())` 动态获取实际类型
- **`llm_hallucination_sampler.py` 中文引号语法错误**：第 324 行中文引号误用 ASCII 双引号，导致 Python 3.10 下 SyntaxError（ruff 强于本地版本检测到），CI 回归测试失败 — 改用单引号包裹字符串
- **`fallback.py` 占位文本缺字**：智囊团深度复盘降级占位文本缺少"成"字（"无法生"→"无法生成"），已补回
- **`handlers_config.py` 辩论模式说明缺字**：辩论模式启用说明中"智囊团复盘"缺少"深度"二字，正文为"智囊团深度复盘"
- **`news_correlation.py` 日志使用缩写**：LLM 新闻关联失败日志"LLM 新闻关联分析"改为完整模块名"财经新闻热点与持仓关联分析（LLM）"

### Changed
- **`generators_orchestrator.py` 消除硬编码模块标签**：事实校验阶段 `_module_labels` 字典从硬编码改为调用 `get_llm_module_names()`，与注册表自动同步

### Chore
- **ruff format 全量对齐**：33 个源码文件 `ruff format` 格式化，CI 格式检查不再报错（非阻塞门禁，但保持全绿）

## [0.8.3] - 2026-07-22

### Fixed
- **P3-12 CI 测试持续失败**：三个原因修复：① `pyproject.toml` 中 `required_plugins` 将 `pytest-mock` 死锁在 `==3.15.1`，但 deps 声明 `>=3.15`，导致 pip 安装的版本不满足硬校验，pytest 拒绝启动 — 统一改为 `>=3.15`；② `format` job 的 Ruff 检查无 `continue-on-error: true`，非阻塞门禁却阻断 CI — 已添加；③ `all` 模式无 `--no-timeout`，大套件易超时截断 — 已添加
- **辩论模式 HTML 报告编码错误**：`report_template.html` 中辩论白脸（pro_text）和黑脸（con_text）的 Jinja2 模板变量缺少 `| safe` 过滤器，导致 LLM 返回的 HTML 内容被转义为文本源码显示。综合权衡段（`expert_review`）已有 `| safe`，不受影响
- **`_normalize_title()` 数字模式过滤**：加入百分比 `\d+(?:\.?\d+)?%` 和金额 `\d+(?:\.?\d+)?[万亿]` 正则过滤，减少跨源去重时不同新闻因共享数字模式（如"20%""25亿"）导致的 SequenceMatcher 比率虚高。同步更新 `test_cross_source_english_token_only_overlap` 测试用例（去百分比后实体 bigram 由 4 降为 2，正确保持 2 条独立新闻）
- **全球政经局势 LLM 虚构最大持仓**：`_build_global_macro_prompt()` 未传入持仓排名数据，LLM 猜测"561910 为最大持仓"但实际最大为 011506。修复：prompt 中新增【持仓TOP3】区块（按市值排序的名称/代码/市值/占比/收益率），并在 system prompt 追加"请勿虚构持仓排名"约束。涉及 `prompts_action.py`、`generators.py`、`generators_orchestrator.py`
- **`_normalize_title()` 扩展前缀/数字模式降去重噪声**：校准锚点分析发现 257 条 bg≤1/ratio≥0.40 噪声。修复：新增 7 个编辑栏目前缀（数据图解、CCI快报、市场动态等）、剔除事件年份数字（`WAIC 2026`→`WAIC`）、剔除排名标记（前N），降低未来校准分析的 false high 比例
- **`_normalize_title()` 再增 4 个高频率栏目前缀**：`量化观察`、`刷屏`、`尾盘`、`华尔街见闻早餐`，基于 3650 条 cross_skip 锚点数据分析补充

### Changed
- **辩论模式防幻觉增强**：pro/con 系统提示词新增严格约束——"数据来自输入，不得虚构任何数值、百分比或排名"；health_check 提示词补充"不得编造未提供的数值"
- **事实校验器防误报**：新增 `_PROPORTION_KEYWORDS` 策略，跳过"XX%的品种""XX%的持仓"等品种计数比例语境，不再将其误判为收益率与累计收益率比较
- **config.json 中文注释分组对齐 TUI 菜单**：B 组注释 `章节可见性` → `报告可选章节`，补充行内注释（`enable_b_series: 基金深度分析（#6~9）` 等），`enable_history` 章节编号修正 `#15~#16` → `#16~17`（与 TUI 菜单描述一致）；默认值和模板同步更新。涉及 `config.json`、`_config_defaults.py`
- **历史走势基准指数移除标普500(gb_inx)**：默认 `benchmark_indices` 移除 `gb_inx: "标普500"`（Sina/Tencent K-line 均不可用，走势始终空白）。同步更新：`_config_defaults.py`（默认值 + 模板）、`config.json`、`benchmark.py` docstring、`how-to-config.md`（示例/字段表/描述 4 处）、`requirements.md`（配置表 1 处）。美股日行情数据源不受影响

## [0.8.2] - 2026-07-22

### Fixed
- **新闻去重算法优化**：`_extract_entity_bigrams()` 加入英数 token 提取（原仅中文 bigram，丢失"AI""AMD"等英文专名），实测减少 14.5% 跨源漏判；扩展 `_STOP_BIGRAMS` 过滤同比/环比等高频噪声；阈值经 80396 条锚点数据分析确认不变
- **校准工具错误建议修正**：`calibrate-dedup-threshold.py` — 按 bigram 重叠度分档分析 cross_skip，不再对 bg≤1（无实体重叠）的 pair 误判"降低阈值"，正确归因于公共日期/财经关键词虚高；移除 ⚠ 字符修复 Windows GBK 编码崩溃
- **SequenceMatcher 剥离日期模式降虚高**：`_dedup_by_title()` 中 comparison 前先剥离 `\d{4}年|\d+月|\d+日` 通用日期格式，防止完全不相关的新闻（如"2026年7月票房" vs "2026年7月经营质量"）因共享日期 ratio 虚高进入候选区

### Changed
- **同步 technical.md 去重算法描述至最新代码**：算法概述去掉校准数据细节；流程图新增日期剥离步骤；核心概念表 STOP 集 24→44 词并含英数 token；实体 bigram 提取补充英数 token 步骤和 STOP 全列表；校准工具输出描述同步为三档分仓分类
- **术语统一（报告内容+注释+文档）**：全项目范围将内部架构术语替换为用户友好术语
  - `板块可见性` → `章节可见性`（config 注释、日志、管理文档）
  - `B 系列` / `B 系列基金深度分析` → `基金深度分析`（模块 docstring、代码注释、HTML 模板注释、文档）
  - `新闻板块` → `市场新闻`（config 注释、文档）
  - `LLM 板块` → `LLM 分析章节` / `LLM 分析章节组`（config 注释、文档）
  - `板块开关` → `章节开关`（technical.md）
  - `板块配置` → `章节配置`（日志输出，此前已改）
  - 覆盖文件：`config/_config_defaults.py`、`config/_core.py`、`features.py`、`registry.py`、`report/excel_b_series.py`、`report/data_status.py`、`report/orchestrator.py`、`report/html_writer.py`、`report/excel_generator.py`、`report/excel_sheet_factory.py`、`report/tmpl/report_template.html`、`README.md`、5 份用户文档、3 份管理文档
- **同步 technical.md 与 llm-technical.md 交叉引用**：§5（LLM 集成层）各子节末指向 llm-technical.md 对应章节；§8（架构设计约束）C9/C17/C18 补充 llm-technical.md 参考；llm-technical.md 首部补充引言说明其与 technical.md 的定位关系
- **清理版本历史术语**：源码注释中移除历版本号引用（`akshare 1.18.64` → `新版`，`旧/新模式` → `单/多凭据格式`）；CLAUDE.md 架构遵从指引改为引用 §架构设计约束表
- **测试隔离增强**：conftest.py 新增 `_auto_reset_feature_flags` fixture 防止 feature 状态跨测试泄漏；LLM 空持仓场景兼容 8/9 元组返回值；e2e_perf 补充缺失 mock
- **用户文档违规引用清理**：how-to-config.md 移除 requirements.md 引用；faq.md 移除 changelog.md 引用；how-to-test-my-code.md 13→1 处管理文档引用合并；README.md 内部文档区标题优化

## [0.8.1] - 2026-07-22

### Fixed
- **P3-13**: `llm/generators.py` `_filter_hallucinated_codes` — 英文词误杀修复：全小写启发式 + `_HALLU_SAFE_WORDS` 白名单豁免 HTML/CSS 标签（`style`、`flash`、`color` 等）和金融术语（`QDII`、`ETF`），正则 `[A-Za-z0-9]{4,6}` 不再误判全小写词，真正虚构代码仍被过滤
- **P2-11b**: `analysis/metrics.py` 新增 `portfolio_beta_analysis()` — 组合 Beta 95% 置信区间、t 统计量、p 值及可靠性标记（区间宽度 > 1.5 标记不可靠）
- **P3-09b**: `analysis/alignment_correction.py` 实现三项口径修正因子 — 组合综合费率估算 (`portfolio_fee_estimation`)、现金剥离 (`cash_stripping`)、时间加权收益率 TWR (`twr_calculation`)，统一入口 `compute_alignment_factors` 已集成至报告管线
- **P2-12**: `config/_core.py` 验证函数提取至 `config/_validation.py`（`_core.py` 1146→739 行，-407 行；`_validation.py` 新建 442 行）

### Changed
- **features.py** + **orchestrator.py**: 实验性功能开启时，生成报告日志中以 `[ERROR]`（红色）高亮显示具体开启了哪些实验性功能
- 版本号更新至 v0.8.1
- **check-version-consistency.py**: review-findings.md、llm-technical.md 加入版本号一致性检查清单（11 项）
- **tui_menu.py**: 菜单 [S] 描述改为"配置 LLM 分析章节"，更简洁准确
- **handlers_config.py**: 辩论模式区域标注 ⚗ 实验性功能标识，底部增加实验阶段提示
- **review-findings.md**: P3-12 新增 CI 测试失败跟踪项；P3-13 新增 debate 幻觉过滤误杀问题；P3-9/P3-10/P3-11 更新实际行号

## [0.8.0] - 2026-07-21

### Changed
- 版本号发布 v0.8.0
- **review-findings.md**：新增 P2 段，记录 Beta 置信区间（P2-11b）和口径修正因子（P3-09b）两项技术债务，待后续迭代切入

---

## 归档

- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

