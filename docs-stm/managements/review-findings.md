# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.10-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C20）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P1 — probe 探测发现（plan-7 决策相关，2026-08-01）

（无待处理项 — rf-102/103/104/106 已全部处理，见"已修复"表）

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> 来源：`archive/v0.9.x/chartjs-upgrade/plan-chartjs-report-upgrade.md` §4.5/§4.7/§4.8/§4.10/§5 Iter 7 + `archive/v0.9.x/chartjs-upgrade/plan-chartjs-risk-analysis.md` §4 TD 表。
> plan-1 代码与自动化测试已落地（dev-verify 1181 passed），以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复 |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器 |
| **rf-117** | A6 键盘可达性未做（Chart.js tooltip 为鼠标悬停驱动，键盘聚焦不触发） | 设计明确"不做 MVP 记入技术债"（upgrade.md §4.8 A6）；如需支持，给 chart-init.js 加键盘交互扩展 |
| **rf-118** | 相关性矩阵 Heatmap 仅占位文本（Chart.js Matrix 插件未引入） | 依赖 plan-2 提供 `correlation_data` 后引入 `chartjs-chart-matrix` 渲染（Iter 7 已推迟，非 YAGNI） |
| **rf-120** | S5 CSP 未配置（报告为离线静态 HTML，无外部域名） | 可选不做 MVP（upgrade.md §4.10 S5）；未来若加 CSP 仅需 `script-src 'self'` |
| **rf-121** | TD2：报告体积增大 ~200KB（chart.min.js 随每份报告复制） | R21 决策接受的"报告自包含"代价；如未来对体积敏感可改 CDN 优先 + 本地兜底 |

### P1 — LLM thinking 预算耗尽（2026-08-02）

（无待处理项 — rf-122 已处理，见"已修复"表；竞态根因 + 配置缓解详见 changelog Fix 条目）

### P1 — plan-5/6 新功能遗留技术债（2026-08-03）

（无待处理项 — rf-159 已处理，见"已修复"表）

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> 行数核对：2026-08-03（`wc -l` 实测）。`fact_checker.py`（rf-76）与 `handlers_config.py`（rf-77）均已拆分处理（见"已修复"表）。拆分判定标准：**800 行是编码规范硬上限，超过必须拆分**；500-800 行为**可选优化**，仅当职责确实割裂、拆分风险低时才建议做——内聚型文件（如中央注册表、单类内聚）即使 >500 也维持现状。当前 P2A 无待处理项，其余维持现状。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 653 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 537 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 534 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 未超限（<500，维持现状） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 477 | 未超限（<500，维持现状） | Excel 编排器 |

#### P2B — 文档与实现不符（低优先级，增量改进）

| # | 问题 | 修复方向 |
|---|------|----------|

### P3 — 测试覆盖缺口（建议补齐）

| # | 位置 | 问题 |
|---|------|------|

---

## 已修复（摘要）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-164 | `test_config.py::TestSetConfigSingleKeyPatch::test_preserves_comment_groups_and_inline` **过期断言**（2026-08-03 ruff 回归运行发现）：rf-160 已将模板市场新闻行尾注释 `#11`→`#12`（基金深度分析范围扩至 #6~11 后顺延），测试仍断言 `// 市场新闻（#11）` → 断言失败 | 断言同步为 `// 市场新闻（#12）`；暴露 dev-verify Phase A marker（`unit_core or unit_providers or unit_fetcher or unit_analysis`）**不含 `unit_config`** 的门禁盲区——config 目录测试不在 P0 门禁内，该目录缺陷测试易漏检 | `changelog.md` → Fix |
| rf-163 | GitHub CI 失败（Python 3.11.15）：`test_pearson_pvalue_constant_series` 断言 `1.373948616504741e-17 == 0.0` 失败——常数序列标准差非精确 0 触发虚假近零相关 | `analysis/correlation.py` 新增 `_CONSTANT_EPS=1e-12` 容差判定（`sx < _CONSTANT_EPS or sy < _CONSTANT_EPS` → 返回 (0.0, 1.0) 绝不硬算）替代精确 `== 0`。根因：CPython `sum()` 实现差异——3.12+ 误差补偿求和 vs 3.11 朴素累加，常数序列 `[0.01]*60` 在 3.11 下均值舍入为 `0.010000000000000005`、标准差 `sx=4.03e-17`（非精确 0.0），绕过 `sx == 0` 保护产生虚假相关 | `changelog.md` → Fix / Test |
| rf-162 | changelog.md **已发布版本 0.9.8 的 `### Fix` 遗留"（开发中）"占位符**（2026-08-03 自查）：0.9.8-dev 切版时（bca6d4a）按模板预置占位，开发期无任何 fix 提交（仅 feat/docs/refactor），发布提交（e6cbd4c）只改了版本头 0.9.8-dev→0.9.8，未清理占位。已发布版本 changelog 应为终态，"（开发中）"会误导读者以为版本未完成；对比 0.9.7/0.9.6 发布版均无此占位 | 0.9.8 `### Fix` "（开发中）"→"无（本版本无 bug 修复提交，仅功能 + 技术债清理）"，保留分类显式说明为空 | `changelog.md` → Docs |
| rf-161 | requirements.md **R-DATA-05 描述不完整**（2026-08-03 自查）：只写"收盘后需验证缓存中 price_date 是否为当日数据"，未写明验证不通过时**强制清除缓存并重新获取最新净值写回**的动作；technical.md §2.4.1 强刷流程图亦未写明刷新成功后自动写回缓存 | requirements.md R-DATA-05 → "收盘后需验证缓存中 price_date 是否为**最近交易日**数据；验证不通过（跨日残留）时**强制清除缓存并重新获取最新净值写回**，避免盘中降级残留数据滞留"（与 `fetcher/price.py` `_fetch_price_with_cache_refresh` 实况一致：`cache.clear(cache_key)` → 重新走 Provider Chain → `cache_set` 写回）；technical.md §2.4.1 流程图补"→ 成功后自动写回缓存"。同步补 `src/test/unit/fetcher/test_fetcher_price.py` 回归测试 8 例（`TestPriceCacheFresh` 5 例 + `TestFetchPriceCacheRefresh` 3 例，mock `is_market_open`/`get_last_trading_day`/`_price_cache_fresh`/`fetch_with_fallback`/`cache.clear`，直接验证跨日残留强刷与新鲜不刷断言） | `changelog.md` → Docs / Test |
| rf-160 | requirements.md / technical.md / llm-technical.md 三份管理文档**交叉核对冲突**（2026-08-03 文档审计）：① **T4 降级缓存陈旧阈值不一致**——technical.md §4.11 DegradationTracker 表 + 附录 D 写"7 天"，代码 `_config_defaults.py` 与 requirements.md §11.1 均 14 天；② **持仓体检维度数不一致**——requirements.md R-LLM-HC-01 + technical.md §5.3 写"四维/4 维"，代码 `prompts_core.py` 与 llm-technical.md §2.2 为五维（含数据质量）；③ **场外基金净值数据源不一致**——requirements.md §5.1 备用写"天天基金"，代码 `chain.py` `price_fund_otc: ["eastmoney"]` 直达无备用；④ **基金深度分析模块数不一致**——technical.md §4.8 写"5 个模块"+ 架构图缺持仓相关性矩阵，注册表为 6 个（#6~#11）；⑤ **E 菜单核心模块数不一致**——requirements.md §1.2/§3.2 写"6 个核心模块"漏组合演进，实际 always×7；⑥ **LLM 熔断阈值不明确**——technical.md §2.2 LLM 列写"连续 N 次"，实际连续 3 次 | 全部按代码对齐：① technical.md §4.11 + 附录 D T4 → 14 天；② requirements.md R-LLM-HC-01 + technical.md §5.3 → 五维度，llm-technical.md §8.1 体检 prompt 补数据质量维度 bullet；③ requirements.md §5.1 备用 → —（直达）；④ technical.md §4.8 "5 个"→"6 个"+ 架构图补持仓相关性矩阵（Pearson 相关+显著性），同步 how-to-config.md §P flag 表/JSON 示例 + 代码注释（`_config_defaults.py`/`_core.py`/`handlers_config.py` TUI 菜单 + report_template.html MODULE 注释 12~21 + evolution partial MODULE 19）；⑤ requirements.md §1.2/§3.2 补组合演进（6→7 个核心模块）；⑥ technical.md §2.2 LLM 熔断 → 连续 3 次。另修 README.md #18→#20 数据源可用性矩阵章节号、faq.md/folders.md 同号、requirements.md §6.4 字段定义小节编号对齐模块号（6.4.11→12/6.4.16→17/6.4.17→18/6.4.18 数据源→20 且与 6.4.19 组合演进换序） | `changelog.md` → Docs |
| rf-76 | `llm/fact_checker.py` 达 **899 行超 800 硬上限**（623→899，↑276；长函数已拆分，文件级别未拆） | 拆分为 `llm/fact_checker/` 子包（9 个私有模块：`_constants`/`_patterns`/`_utils`/`_context`/`_numerical`/`_symbols`/`_ranking`/`_corrections`/`_runner`），`__init__.py` 重导出 4 个公开函数（`run_fact_check`/`check_numerical_consistency`/`check_symbol_existence`/`check_ranking_correctness`），对外导入路径 `from src.python.llm.fact_checker import ...` 不变。最大模块 `_numerical.py` 251 行。顺带删除死代码 `_RANK_TOP_N_PATTERN`（全库无引用）与未使用导入 `Any` | `changelog.md` → Refactor |
| rf-77 | `tui/handlers_config.py` 达 **573 行**（500-800 可选优化区间，职责割裂） | 将纯 JSON 文本编辑函数提取到 `config/_json_patch.py`（`_update_json_raw_text`/`_replace_dict_block`，93 行，无 TUI/IO 依赖，适配带注释 JSON 的字段级替换 + dict 区块 brace 平衡）；`handlers_config.py` 保留 TUI 交互函数（`_read_llm_settings`/`_write_llm_settings`）与全部 `_cmd_*` 命令处理器，573→490 行。`config/__init__.py` 补 `_json_patch` 子模块引用，导入路径 `from src.python.config._json_patch import ...` | `changelog.md` → Refactor |

> 已发布版本已修复问题记录已迁移归档至 [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) （v0.9.0 ~ v0.9.5：rf-90 ~ rf-144；v0.9.6 / v0.9.7 / v0.9.8：rf-115/116/119、rf-145 ~ rf-159），本表仅跟踪当前迭代（0.9.10-dev）修复项。

---

## 归档

### 归档档案

- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.8（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
