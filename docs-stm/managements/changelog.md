# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.8.2-dev] - 未发布

### Changed
- **术语统一（报告内容+注释+文档）**：全项目范围将内部架构术语替换为用户友好术语
  - `板块可见性` → `章节可见性`（config 注释、日志、管理文档）
  - `B 系列` / `B 系列基金深度分析` → `基金深度分析`（Excel 页签、HTML 注释、模块 docstring、文档）
  - `新闻板块` → `市场新闻`（config 注释、文档）
  - `LLM 板块` → `LLM 分析章节` / `LLM 分析章节组`（config 注释、文档）
  - `板块开关` → `章节开关`（technical.md）
  - `板块配置` → `章节配置`（日志输出，此前已改）
  - 覆盖文件：`config/_config_defaults.py`、`config/_core.py`、`features.py`、`registry.py`、`report/excel_b_series.py`、`report/data_status.py`、`report/orchestrator.py`、`report/html_writer.py`、`report/excel_generator.py`、`report/excel_sheet_factory.py`、`report/tmpl/report_template.html`、`README.md`、5 份用户文档、3 份管理文档

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

