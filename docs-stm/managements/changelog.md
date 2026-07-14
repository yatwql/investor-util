# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [0.5.0] - 2026-07-14

### Changed

- **归档目录重组**：`archive/g-board-visibility-iteration-plan.md` 迁入 `archive/report-board-visibility-configable/` 子目录，保持与其它多文件归档一致的目录结构。
- **`should_create_sheet()` 重构（Option A）**：去掉硬编码 type_map 和 board/data 混层参数，改为直接查询注册表中每个 section 的 `data_flag` 字段。`should_create_sheet(section, data_availability)` 成为纯 data 层函数，新增模块只需在 registry 填对 `data_flag` 即可零改动。
- **`create_sheets()` 签名简化**：移除 `news_data_available`/`llm_data_available` 两个 data 层参数，统一为 `data_availability: dict[str, bool]` 字典传入。`excel_generator.py` 调用侧同步构造 data_availability dict。
- **`set_sheet_title()` 移除**：生产代码中已无消费者（`create_sheets` 改用内联连续重新编号），删除 `registry.py` 中的函数定义及对应测试用例，消除 ~25 行死代码。
- **TUI 菜单 B/L 描述更新**：不再硬写`[含基金深度分析]`，改为`[按板块配置]`；L 菜单突出`[含LLM]`为核心差异。同步更新 `requirements.md` 菜单对照表。

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
