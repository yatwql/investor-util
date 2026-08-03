# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.9] - 2026-08-03

### Feat

- **TUI 菜单添加调仓 What-if 模拟入口（W 快捷键）** — `tui_menu.py` 菜单项 + `tui.py` 回调绑定（W → `handlers_whatif._cmd_whatif`）；新增 `handlers_whatif.py`（选基准 + 目标持仓 → 生成独立调仓 diff 报告）；补 `test_handlers_whatif.py` / `test_tui_menu.py` 测试，同步 how-to-start.md / scripts-reference.md 文档
- **文档历史痕迹检查脚本（check-doc-traces.py）+ 代码检查脚本重命名（check-code-traces.py）** — 新增 `scripts/check-doc-traces.py`：扫描面向读者文档（README + docs-stm/managements、docs-stm/manuals，豁免 changelog/review-findings/plan 及 archive/plan/tmp 目录），检查历史变更痕迹（来源叙述/历史实现/迁移/任务编号/归档引用/版本号/Iter），豁免版本头/需求 ID/目录树/当前能力/发布流程/工具场景/模型名；`check-history-traces.py` 重命名 `check-code-traces.py` 与文档检查对称可区分；两检查器接入 P0 提交门禁。后续打磨：收紧过宽豁免（版本头改行首锚定）、引入 LOW 类别（需人工判断的变更/过渡/待办描述）、Markdown 围栏代码块内命令示例自动跳过、模式列表模块级缓存

### Fix

- **rf-163：持仓相关性常数序列标准差容差判定（修复 GitHub CI Python 3.11.15 失败）** — CI `test_pearson_pvalue_constant_series` 断言 `1.373948616504741e-17 == 0.0` 失败。根因：CPython `sum()` 实现差异——3.12+ 误差补偿求和 vs 3.11 朴素累加，常数序列 `[0.01]*60` 在 3.11 下均值舍入为 `0.010000000000000005`、标准差 `sx=4.03e-17`（非精确 0.0），绕过 `sx == 0` 常数序列保护，与噪声序列算出虚假近零相关。修复：`analysis/correlation.py` 新增 `_CONSTANT_EPS=1e-12`（常数/近常数序列判定阈值，与 `metrics._VARIANCE_EPSILON`/`whatif._EPS` 项目容差模式一致），`sx < _CONSTANT_EPS or sy < _CONSTANT_EPS` → 返回 `(0.0, 1.0)` 绝不硬算。修复后常数序列在两种 CPython 版本下均稳定判定不显著
- **rf-164：test_config 过期行尾注释断言同步（#11→#12）** — rf-160 将模板市场新闻模块注释 `#11`→`#12`（基金深度分析范围扩至 #6~11 后顺延），但 `test_preserves_comment_groups_and_inline` 仍断言 `// 市场新闻（#11）` → 断言失败。根因：dev-verify Phase A marker（`unit_core or unit_providers or unit_fetcher or unit_analysis`）不含 `unit_config`，config 目录测试不在 P0 门禁内，过期断言漏检。修复：断言同步为 `// 市场新闻（#12）`；暴露门禁盲区（`unit_config` 不在 dev-verify Phase A 覆盖范围）
- **rf-113：浏览器人工验证载体修复（test-chart.html 补 chart-common.js 注入）** — rf-159 重构后 chart-init.js 依赖 `window.ChartCommon`（由 chart-common.js 提供），但调试页 test-chart.html 注入列表漏掉该文件，导致 0/6 图全部跳过、rf-113 前置准备自检载体失效。修复注入顺序与报告模板一致（chart-common.js 先于 chart-init.js），验证清单更新至 7 JS 资产并补依赖说明
- **配置兼容性清理（缓存键 _v2 后缀 / llm_settings 补默认 / 删除旧 fallback 字段）** — `cache/_paths.py` 缓存路径加 `_v2` 后缀，旧缓存键自动失效重建（后缀兼容前缀匹配清理/统计/敏感识别）；`config/_core.py` `get_llm_config` 运行时 `_merge_llm_defaults` 补全默认值（默认打底 + null 不覆盖 + dict 一层合并 + 未知键透传）；`llm/api.py` 删除旧 `fallback_*` 字段回退块，统一由 `llm_providers.json` 多 Provider 链式配置承担高可用/降级；文档移除"旧 fallback_* 字段已移除"历史痕迹措辞改为正向指引

### Refactor

- **rf-76：`llm/fact_checker.py`（899 行超 800 硬上限）拆分为 `fact_checker/` 子包** — 按职责拆为 9 个私有模块：`_constants.py`（关键词词表/指数代码集/默认容差）、`_patterns.py`（正则模式）、`_utils.py`（HTML 剥离/句子拆分/持仓映射/组合数值）、`_context.py`（回撤/变化率/贡献度/仓位/假设/建议语境检测）、`_numerical.py`（数值一致性检查器 + `_evaluate_percent_value`）、`_symbols.py`（品种存在性）、`_ranking.py`（排名正确性）、`_corrections.py`（数值自动修正）、`_runner.py`（`run_fact_check` 统一入口）。`__init__.py` 重导出 4 个公开函数，`from src.python.llm.fact_checker import ...` 对外导入路径不变（`generators_orchestrator.py` 与两个测试文件零改动）。顺带删除死代码 `_RANK_TOP_N_PATTERN`（全库无引用）与未使用导入 `Any`。最大模块 `_numerical.py` 251 行。回归：`test_fact_checker.py` + `test_llm_hallucination.py` 82 例、orchestrator 相关 98 例全部通过（纯拆分零行为变更）
- **rf-77：`tui/handlers_config.py`（573 行）提取 JSON 文本编辑函数到 `config/_json_patch.py`** — 573→490 行。纯 JSON 编辑算法（`_update_json_raw_text` 字段级替换保留注释/空白 + `_replace_dict_block` dict 值区块 brace 平衡自适应缩进，93 行）从 TUI 配置命令处理器中提取至 `config/_json_patch.py`（无 TUI/IO 依赖）；`handlers_config.py` 保留 TUI 交互函数（`_read_llm_settings`/`_write_llm_settings`）与全部 `_cmd_*` 命令处理器。`config/__init__.py` 补 `_json_patch` 子模块引用，导入路径 `from src.python.config._json_patch import ...`。回归：`test_handlers_config.py` 9 例 + config/handlers/ui 338 passed（纯提取零行为变更）
- **whatif 业务逻辑抽象共享层（CLI/TUI 去重）** — 新增 `report/whatif_operations.py`：`WhatifRunResult` + `run_whatif_simulation`，封装 build_whatif_data → 校验 available → write_whatif_report 业务链，镜像 `cache/operations.py` 共享层模式。CLI `_handle_whatif` 与 TUI `_cmd_whatif` 仅保留入口渠道差异化逻辑（文件来源解析、判空、错误呈现、退出码/路径输出），遵循"CLI/TUI 只是入口渠道，业务逻辑公共抽象"设计约束。同步新增共享层单元测试、CLI/TUI 测试 mock 边界更新至 `run_whatif_simulation`
- **history_mode 语义化重构（配置键 history.fetch_mode + 运行时参数 fetch_history）** — 配置层：`history.analysis` → `history.fetch_mode`（三态 off/prompt/auto），`config/_core.py` 自动迁移旧键 + 校验合法取值；运行层：报告生成参数 `history_mode(str)` → `fetch_history(bool)`，消除 4 处 `_resolved_mode` 二义性解析，`_prompt_history` 返回 bool 仅在 config fetch_mode=prompt 时询问。同步 how-to-config/how-to-menu/reports-instruction/requirements 文档 + 三态测试与旧键迁移测试
- **F1/F2 系列命名语义化（注释/文档字符串/日志前缀/文档章节）** — 将不透明 F1/F2/F3 缩写展开为语义化名称：F1（快照对比/持仓快照）→ 快照对比/持仓快照、F2（历史走势）→ 历史走势/组合历史走势、日志前缀 `[F1]`/`[F2]` → `[环比]`/`[历史走势]`；清理过期文档引用 §6.6 F1（原 plan-1 遗留，改为 metrics_* 功能开关）。纯表述变更零逻辑改动，dev-verify 1268 通过
- **归档 plan 设计文件至 archive/v0.9.x/（目录名按内容、混合内容拆分）** — 归档已完成项设计文档（plan-2/3/5/6/9/12 + rf-122/rf-150 对应设计/实施文件），目录名改为与内容相关（correlation-drawdown/、first-run-wizard/、whatif-simulation/、portfolio-evolution/、qa-concentration-chart-optimization/、fix-deepseek-thinking/）；混合内容拆分（plan-implement-2-3-9 → correlation-drawdown + first-run-wizard、whatif-evolution → whatif-simulation + portfolio-evolution）；外部引用全量同步（archived_plan 索引、plan.md 失效锚点修复、technical.md 设计边界、folders.md 目录树）

### Docs

- **rf-162：已发布版本 0.9.8 的 `### Fix` 清理"（开发中）"遗留占位** — 0.9.8-dev 切版时（bca6d4a）模板预置 `### Fix（开发中）`，开发期无任何 fix 提交（仅 feat/docs/refactor），发布提交（e6cbd4c）只改版本头未清理占位。现改为"无（本版本无 bug 修复提交，仅功能 + 技术债清理）"，与已发布版本 changelog 应为终态的约定对齐。纯文档修正，零行为变更
- **rf-161：requirements R-DATA-05 补"跨日残留强刷"动作 + technical 流程图补写回缓存** — 自查发现 R-DATA-05 只描述"验证 price_date 是否为当日数据"，未写明验证不通过时的处置：现补全为"收盘后需验证缓存中 price_date 是否为**最近交易日**数据；验证不通过（跨日残留）时**强制清除缓存并重新获取最新净值写回**，避免盘中降级残留数据滞留"（与 `fetcher/price.py` `_fetch_price_with_cache_refresh` 实况一致）。同步 technical.md §2.4.1 强刷流程图补"→ 成功后自动写回缓存"节点。纯文档补充，零行为变更
- **rf-160：requirements/technical/llm-technical 三份管理文档交叉核对冲突修复** — 按代码实况对齐 6 处跨文档冲突：① T4 降级缓存陈旧阈值 technical.md（§4.11 + 附录 D）"7 天"→"14 天"（与 `_config_defaults.py`/requirements §11.1 一致）；② 持仓体检维度 requirements.md R-LLM-HC-01 + technical.md §5.3 "四维/4 维"→"五维度/5 维"（与 `prompts_core.py`/llm-technical §2.2 一致），llm-technical §8.1 体检 prompt 补数据质量维度 bullet；③ 场外基金净值 requirements.md §5.1 备用"天天基金"→"—"（`price_fund_otc` 直达无备用）；④ 基金深度分析 technical.md §4.8 "5 个模块"→"6 个"（注册表 #6~#11），架构图补持仓相关性矩阵（Pearson 相关+显著性）；⑤ E 菜单核心模块 requirements.md §1.2/§3.2 补组合演进（"6 个核心模块"→"7 个"）；⑥ LLM 熔断阈值 technical.md §2.2 "连续 N 次"→"连续 3 次"。同步修正：README.md/faq.md/folders.md 数据源可用性矩阵章节号 #18→#20；how-to-config.md §P flag 表 + JSON 示例、代码注释（`_config_defaults.py`/`_core.py`/`handlers_config.py` TUI 菜单）基金深度分析范围 #6~10→#6~11 且市场新闻 #11→#12、历史走势 #16~17→#17~18；report_template.html MODULE 注释 12~21（新闻 #12→LLM API 用量 #21）+ evolution partial MODULE 18→19；requirements.md §6.4 字段定义小节编号对齐模块号（6.4.11 财经新闻→6.4.12、6.4.16→6.4.17、6.4.17→6.4.18、数据源 6.4.18→6.4.20 并与组合演进 6.4.19 换序）。纯文档/注释修改，零行为变更
- **已发布版本变更记录迁移归档（changelog/plan/review-findings → archive/v0.9.x/）** — changelog.md 的 [0.9.6]/[0.9.7]/[0.9.8] 章节、plan.md 已完成项（plan-2/3/5/6/9/12）、review-findings 已修复记录（rf-115/116/119、rf-145~rf-159）迁移合并至 archived_changelog.0.9.x.md / archived_plan.0.9.x.md / archived_review-findings.0.9.x.md（涵盖版本更新至 v0.9.0 ~ v0.9.8）；review-findings.md 仅保留当前迭代待处理项
- **technical.md §4.13 设计边界移除 archive 引用，整合为自包含正文** — 删除对 `../archive/v0.9.x/whatif-simulation/plan-whatif-simulation.md` 的引用，设计边界（成本口径 / 不可回测 / 双份数据内存 / 勿误用为回测）四点自包含，不再依赖归档文档
- **folders.md 清理历史痕迹（归档文件去任务编号，引用与统计同步）** — 归档目录 3 个带 R-*/plan-* 编号文件重命名为纯语义名，同步 archived_plan/archived_changelog/review-findings/folders.md 引用，technical.md 标题去掉 plan-5/plan-6 任务编号后缀
- **review-findings P2A 统一文件拆分判定标准 + 状态列精简** — P2A 判定标准澄清（800 行为编码规范硬上限必须拆分 / 500-800 行为可选优化，仅职责割裂且拆分风险低才建议；内聚型文件即使 >500 也维持现状），rf-75/78/79/80/81 按新标准标维持现状；状态列去除历史增长量（如 617→653↑36）只保留最新实测行数与当前判定，行数用 wc -l 实测核对
- **folders.md 目录树注释自描述清理 + 模板注释去历史痕迹** — partials/static 注释清理设计文档编号引用（R21/S2/O1/TD8/§4.5），test-chart.html S2 说明、evolution_section.html "自 report_template.html 提取" 等历史痕迹修正为当前状态描述；test 压缩条目拆分可读

### Test

- **rf-161：场外基金净值盘后新鲜度 + 跨日残留强刷路径回归测试** — `test_fetcher_price.py` 新增 8 例：`TestPriceCacheFresh` 5 例（盘中不校验恒新鲜 / 盘后 price_date ≥ 最近交易日新鲜 / price_date < 最近交易日跨日残留不新鲜 / 无 price_date 不新鲜 / 校验异常保守视新鲜，mock `is_market_open` + `get_last_trading_day`）；`TestFetchPriceCacheRefresh` 3 例（跨日残留 → `cache.clear` 被调用 + 二次拉取返回最新净值 / 新鲜缓存 → 仅一次 fetch 且不清缓存 / 首次 fetch 即 None → 不进强刷分支，mock `_price_cache_fresh` + `fetch_with_fallback` + `cache.clear`）。直接断言缺陷场景，而非仅正常路径
- **rf-163 回归测试** — `test_correlation.py` 新增 `test_pearson_pvalue_near_constant_series`（近常数序列波动 ~1e-14 仍判常数返回 (0.0, 1.0)，不因浮点误差硬算）；`test_pearson_pvalue_constant_series` 断言由精确 `== 0.0` 改为容差 `abs(r) < 1e-12 and p == 1.0`——验证"行为"（不硬算）而非实现细节，两种 CPython `sum` 实现（3.11 朴素累加 / 3.12+ 误差补偿求和）下均稳定
- **rf-164 回归测试** — `test_config.py::test_preserves_comment_groups_and_inline` 行尾注释断言 `// 市场新闻（#11）`→`// 市场新闻（#12）` 与模板注释一致，锁定单键 patch 保留注释行为不回退
- **rf-113 回归测试（TestDebugPageAssets）** — `test_feature_interactive.py` 新增：验证 test-chart.html 注入列表含 chart-common.js 且先于 chart-init.js；离线场景仅移除引擎文件。直接断言缺陷场景（注入顺序/依赖关系）

### Chore

- **CI ruff format 检查修复（6 文件格式修正）** — GitHub CI `ruff format --check src/python/ scripts/` 报 6 个文件未格式化（历史遗留格式债务，非本次改动引入）：`scripts/probe-csi-factor-indices.py`、`src/python/analysis/drawdown_events.py`、`src/python/config/_core.py`、`src/python/llm/prompts_action.py`、`src/python/report/_history_quality.py`、`src/python/report/correlation_sheet.py`。全量运行 `ruff format src/python/ scripts/`（217 文件）修复，纯空白/换行调整零逻辑变更（对齐 v0.9.0 ruff 全量格式修正惯例）

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.8（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
