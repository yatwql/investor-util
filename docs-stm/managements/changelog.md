# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.10] - 2026-08-03

### Feat

- 调仓 What-if 模拟报告归档格式对齐主报告（用户建议）：最新版固定名 `调仓模拟.xlsx` / `调仓模拟.html`（每次覆盖为最新对比）+ 日期目录归档版 `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx/.html`（超 180 天自动清理），见 `report/whatif_writer.py`
- TUI 调仓模拟单文件场景增强（用户建议）：持仓目录只有基准一份时，`_select_candidate_file` 引导三选——`[1]` 自动复制基准为可编辑目标模板（`<基准名>-调仓后模板.xlsx`，同名追加序号不覆盖）/ `[2]` 手动输入目标文件完整路径 / 回车取消，见 `tui/handlers_whatif.py`
- 报告首页投资分析汇总：统计时间值（如 `2026-08-03 14:02:57`）字体加粗；所属交易日值（如 `2026-08-03`）字体加粗 + 加大（Excel 12 号 / HTML 16px）+ 蓝色（2E75B6）。标签列不受影响。见 `report/summary.py`（`_STAT_TIME_FONT`/`_TRADING_DAY_FONT`）+ `tmpl/report_template.html`
- 调仓 What-if **指定生效日时序回测**：CLI `--effective-date YYYY-MM-DD` / TUI 菜单 W 生效日提示输入后，opt-in 联网取**生效日后**行情，用 as-if 市值（份额 × 每日价格）对比基准/目标组合并归一化到 100 基点，输出区间收益 / 年化收益 / 年化波动率 / 夏普 / 最大回撤 + 净值/回撤曲线。Excel 追加第 4 页签「时序回测」，HTML 追加④时序回测区（2 张折线图 + 图下说明）。纯计算在 `analysis/whatif_backtest.py`（不联网、不 import report/），联网编排在 `report/whatif_operations.py::build_whatif_backtest`，CLI/TUI 仅传参不承载业务逻辑。未指定生效日维持纯截面比较、零网络请求；数据不足/不可对齐 → 回测降级不阻塞主报告。见 `analysis/whatif_backtest.py` + `report/whatif_operations.py` + `report/portfolio_history.py`（days 透传）+ `report/whatif_sheet.py` + `tmpl/whatif_template.html`

### Fix

- **rf-168** 智囊团深度复盘排名事实校验误报：`check_ranking_correctness` 旧实现将"第N大/前N大持仓"等一律按"最大持仓"校验（仅接受市值第1名），并把"句中第一个代码"当作声称对象——LLM 调仓方案表里"040046 继续持有第一重仓"（正确）被归因到句首 561910，"561910 已是组合第三大持仓"（正确）被当"最大持仓"误报。现按声称类型拆分校验（`_RANK_MAX_PATTERN` 最大/最重/首要→市值第1名、`_RANK_ORDINAL_PATTERN` 第N大→第N名、`_RANK_TOP_PATTERN` 前N大/头N大→前N名内），告警文案反映实际声称类型；归因改为表格行内就近找代码（跨行不误归因，见 `_claimed_code`）；"主要持仓"等模糊声称不再校验。见 `llm/fact_checker/_ranking.py` + `llm/fact_checker/_patterns.py`
- **rf-166** TUI 按 W 调仓模拟 output_dir 相对路径 bug：`get_config_cache()` 未初始化时回退 `{}` 导致输出目录依赖启动目录；改为回退 `get_config()`（absolutized 路径），与 CLI 一致
- **rf-165** TUI 按 W 调仓模拟单持仓文件场景：持仓目录只有基准一份文件时候选为空直接退出不生成报告；改为引导选择目标文件（自动复制模板 / 手动输入完整路径 / 取消），不再直接退出
- **rf-167** 缓存原子写测试隔离缺陷：`test_set_atomic_write_content` 误扫全局系统临时目录（断言对象与原子写实际目录/后缀不符），并行测试下偶发失败；改为扫描缓存目录内 `.tmp` 残留

### Docs

- 发布门禁（P2）补充代码/文档历史痕迹检查：`check-code-traces.py --ci` + `check-doc-traces.py --ci`（与 P0 一致），见 `testplan.md` §6.3 第 11 条与 `CLAUDE.md` 发布门禁（P2）
- **rf-169** 管理/用户文档正文一致性审计 + `check-doc-traces.py` 打磨（2026-08-03）：① `folders.md` 目录树移除 4 处行数注释（`_numerical.py`/`chart_data_builder.py`/`chart-config.js`/`chart-init.js`，行数不必要且随迭代过时）；② `requirements.md` §6.4 字段定义补齐缺失小节——6.4.10 因子暴露分析 / 6.4.11 持仓相关性矩阵 / 6.4.13-16 LLM 模块（全球政经局势/智囊团深度复盘/持仓体检报告/穿透深度分析）/ 6.4.21 LLM API 用量（字段按代码实况），编号恢复连续 6.4.1~6.4.21 对齐 §6.3 模块号；③ `technical.md` 与代码实况同步——LLM 包子模块数 16→36、excel_generator 编排器 437→477 行、STATUS_MESSAGES 16→23 条、附录 A 目录补 `src/static/` + `startup_wizard.py`；④ `testplan.md` unit 子组计数 11→10（与 test-coverage.md 一致）、§6.4 人工验证菜单清单补 [W]、whatif CLI 示例补 `--effective-date`、LLM 场景文件组织描述去历史化；⑤ `check-doc-traces.py` 新增无 v 前缀裸版本号检测（`0.9.8` 在散文中命中 HIGH，限 0 开头避免误伤章节号/包版本），并补充相应豁免

### Test

- 新增 `test_whatif_writer.py`（4 用例）：调仓模拟报告输出归档格式——Excel/HTML 最新版固定名 + 日期目录归档版 + 触发 `_cleanup_old_archives` + 最新版被占用抛 PermissionError / 归档版写失败仅告警
- `test_handlers_whatif.py` 增 3 用例：单文件场景选 `[1]` 自动复制模板返回模板路径 / 无效选择后复制 / 复制失败（OSError）返回 None
- `test_set_atomic_write_content` 隔离修复（rf-167 回归）：扫描缓存目录 `.tmp` 残留而非全局系统临时目录
- `test_fact_checker.py` 增 10 排名回归用例（rf-168）：第N大/前N大正确与错误（`test_second_largest_correct_pass`/`test_third_largest_wrong_flagged` 等）、top3 内非第一通过、top3 外告警、"主要持仓"模糊声称跳过、表格句就近归因（`test_table_sentence_nearest_code_attribution`——"040046 第一重仓 + 561910 第三大持仓"正确不误报）与表格句错误声称仍检出
- `test_summary.py` 增 `TestWriteBasicInfoFonts`（3 用例）：统计时间值加粗 / 所属交易日值加粗+加大+蓝色 / 标签列不受影响（真实 openpyxl 工作表 + patch `get_last_trading_day`）
- `test_html_report_structure.py` 增 `TestSummaryDateTimeValueStyles`（3 用例）：统计时间值加粗 / 所属交易日值加粗+16px+蓝色 / 标签列无内联样式
- 新增 `test_whatif_backtest.py` + `test_whatif_backtest_edge.py`：时序回测纯计算——天数折算/钳位/坏格式/未来日期、并集+LOCF+锚点对齐、归一化/收益率/回撤序列数值、5 指标对比（`pytest.approx`）、数据不足/两侧空/不可对齐降级、status 传播
- `test_portfolio_history.py` 增 days 透传断言：`history_stock/history_fund_otc` 调用补 days=30；`get_combined_timeseries` days=365 透传到 `calculate_for_holding`
- `test_whatif_operations.py` / `test_whatif_sheet.py` / `test_whatif_writer.py` / `test_whatif_html.py` 扩展：未指定生效日不加 backtest 键、回测异常降级不阻塞、Excel 第 4 页签、HTML ④时序回测区出现/隐藏 + 回测线图 caption + R9 负载
- `test_cli.py` 增 `--effective-date` 解析与透传断言；`test_handlers_whatif.py` `TestCmdWhatif` 补 `_prompt_effective_date` mock + 生效日输入透传/回车空→None

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.9（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
