# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [0.5.1] - 2026-07-14

### Fixed

- **HTML 报告导航栏序号不连续**：导航栏使用 `sec["number"]`（注册表中的原始编号）而非重新编号后的 `section_numbers`，导致关闭 B 系列/历史走势后导航栏显示原始序号（1,2,3,4,5,10,11...）而章节标题已正确连续编号（1,2,3,4,5,6,7...）。已修复：导航栏改为使用 `section_numbers[sec["key"]]`，与章节标题统一。

- **HTML 报告缺失 LLM 页面**：`write_html_report()` 的 `enable_llm` 参数默认值为 `False`，而 `_cmd_generate_full()`（L 菜单）调用时未传入，导致 HTML 报告中所有 LLM 板块被隐藏且无连续编号。已修复为传递 `is_enable_llm()` 配置值，并同步新增该函数作为统一读取入口。

- **误导日志"实增 N 个"**：`news_correlation.py` 中行业/概念关键词扩展日志使用了"实增"（暗示随时间增长），但实际是持仓关键词（股票名）与行业/概念关键词（行业名、板块名）两个不重叠集合的差值，每次结果相同。已改为"行业/概念 N 个"。

### Changed

- **`is_enable_llm()` 新增**：在 `config/_core.py` 新增 LLM 板块可见性判断函数，读取 `llm_settings.json` 的 `enabled_llm`，仅检测 4 个 LLM 报告模块（global_macro / expert_review / health_check / penetration_deep），不包含 `news_correlation`。缺失时默认启用（向后兼容）。
- **L 菜单 LLM 生成条件化**：`_cmd_generate_full()` 在 `is_enable_llm()` 返回 False 时不再提交 LLM 线程任务。新闻/LLM 组合的 4 种开关状态（双启/仅新闻/仅 LLM/双关）均正确处理。
- **B 菜单显式同步**：`_cmd_generate_both()` 的 Excel 和 HTML 调用均显式传入 `enable_llm=False`，与 B 菜单"不含 LLM"的语义对齐。
- **Provider 熔断器阈值可配置化**：`ProviderState.failure_threshold` 和 `cooldown_secs` 改为 per-instance。`eastmoney_industry` 使用 `failure_threshold=6, cooldown_secs=120`，避免 3 线程并发调用时一次网络抖动即熔断。单股票 API 保持默认 3/300s。

### Docs

- **technical.md**：`is_enable_llm()` 加入 board 层对照表，llm 配置来源说明更新。
- **how-to-config.md**：H 节新增 LLM 可见性配置行，内容只描述当前状态。
- **how-to-config-llm.md**：新增板块可见性与 `enabled_llm` 的关联提示。
- **faq.md**：板块可见性配置项补充 `enabled_llm`，菜单生成范围说明同步。
- **how-to-start.md**：报告内容对照表 B/L 菜单改用 ☆ 标注配置驱动型可见性，新增脚注 ⁵ 说明。
- **reports-instruction.md**：可见性规则表重构为两层模型（board+data），LLM 模块触发条件补充 `enabled_llm` 配置控制。
- **requirements.md**：熔断器/push2/基金风格加速阈值文字同步。

## [0.5.0] - 2026-07-14

### Changed

- **归档目录重组**：`archive/g-board-visibility-iteration-plan.md` 迁入 `archive/report-board-visibility-configable/` 子目录，保持与其它多文件归档一致的目录结构。
- **`should_create_sheet()` 重构（Option A）**：去掉硬编码 type_map 和 board/data 混层参数，改为直接查询注册表中每个 section 的 `data_flag` 字段。`should_create_sheet(section, data_availability)` 成为纯 data 层函数，新增模块只需在 registry 填对 `data_flag` 即可零改动。
- **`create_sheets()` 签名简化**：移除 `news_data_available`/`llm_data_available` 两个 data 层参数，统一为 `data_availability: dict[str, bool]` 字典传入。
- **`set_sheet_title()` 移除**：生产代码中已无消费者（`create_sheets` 改用内联连续重新编号），删除 ~25 行死代码。
- **TUI 菜单 B/L 描述更新**：不再硬写`[含基金深度分析]`，改为`[按板块配置]`；L 菜单突出`[含LLM]`为核心差异。

### Docs

- **datasource-and-folders.md**：目录树中 `g-board-visibility-iteration-plan.md` 单文件引用更新为 `report-board-visibility-configable/` 目录+子文件层级。

---

> **v0.4.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.4.x.md](../archive/archived_changelog.0.4.x.md)。
> 涵盖 v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）共 5 个版本。
>
> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.3.x.md](../archive/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）共 8 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.2.x.md](../archive/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
