# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [0.5.0] - 2026-07-14

### Fixed

- **HTML 报告缺失 LLM 页面**：`write_html_report()` 的 `enable_llm` 参数默认值为 `False`，而 `_cmd_generate_full()`（L 菜单）调用时未传入 `enable_llm=True`，导致 HTML 报告中所有 LLM 板块被隐藏且无连续编号。已修复为传递 `is_enable_llm()` 配置值，并同步新增 `is_enable_llm()` 函数作为统一读取入口。

### Changed

- **`is_enable_llm()` 新增**：在 `config/_core.py` 新增 LLM 板块可见性判断函数，读取 `llm_settings.json` 的 `enabled_llm`，仅检测 4 个 LLM 报告模块（global_macro / expert_review / health_check / penetration_deep），不包含 `news_correlation`。缺失时默认启用（向后兼容）。导出为 `config.is_enable_llm()`。
- **L 菜单 LLM 生成条件化**：`_cmd_generate_full()` 在 `is_enable_llm()` 返回 False 时不再提交 LLM 线程任务，避免无谓开销。新闻/LLM 组合的 4 种开关状态（双启/仅新闻/仅 LLM/双关）均正确处理。
- **B 菜单显式同步 enable_llm=False**：`_cmd_generate_both()` 的 Excel 和 HTML 调用均显式传入 `enable_llm=False`，与 B 菜单"不含 LLM"的语义对齐。
- **Provider 熔断器阈值可配置化**：`ProviderState.failure_threshold` 和 `cooldown_secs` 改为 per-instance，不再使用全局默认值。`eastmoney_industry` 注册时传入 `failure_threshold=6, cooldown_secs=120`，避免 3 线程并发调用时一次网络抖动即熔断。其他单股票 API 保持默认 3/300s。

### Docs

- **datasource-and-folders.md**：目录树中 `g-board-visibility-iteration-plan.md` 单文件引用更新为 `report-board-visibility-configable/` 目录+子文件层级。
- **用户文档版本标记清理**：`how-to-config.md` 的 H 节标题及 `faq.md` 的锚点移除 `v0.5.0`/`v050` 后缀，用户文档只描述当前状态，不反映版本历史。

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
