# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.6-dev] - 2026-08-02

### Fix

- **rf-149：Excel 端 LLM 内容分段缺陷（footer 重复 + 事实校验摘要明细样式丢失 + 整模块坍缩）** — 跟进 rf-148 报告检查（2026-08-02）：`_write_content_sheet` 按 `\n\n` 分段，但真实 LLM 内容由 `markdown_to_html` 以**无换行方式**拼接 `<p>` 标签 → ① 整模块坍缩进一个单元格（markdown.py `"".join(parts)` 无分隔符）；② orchestrator 以单 `\n` 追加校验摘要到 footer `</p>` 之后 → `paragraphs[-1] == footer_text` 排除守卫失效，footer 在正文出现一次（被染绿/琥珀）+ 末尾灰字再写一次 = **重复**；③ 摘要块内部明细行（⚠ 提示 / ℹ 建议提及 / `已修正明细`）坍缩在同一单元格，灰色 `#888/#999` 样式全部丢失。修复：`llm_content.py` 新增 `_split_html_blocks()` 按块级 HTML 标签（`<p>/<li>/<div>/<h1-6>/<ul>/<ol>/<br>`）分段，游离 `<span>` 附属行并入前一块，纯文本输入回退 `\n\n` 分段兼容历史；`_write_content_sheet` 改用新分段逻辑，footer 块正文跳过、末尾统一写一次；新增 `_write_fact_check_block()` 将摘要块拆为多行——首行绿/琥珀、明细行灰色小字（新 `_FACT_CHECK_DETAIL_FONT`）。修复后 Excel 端校验摘要与 HTML 端视觉一致
  - **技术债加固**（同日自查）：① `_strip_html` 块级结束标签（`</p>/</li>/</h1-6>/<br>/<hr>` 等）先转换行 + 连续换行折叠，剥离后的 `<ul>` 列表、摘要明细行保留段落结构，不再标签间文本粘连成一行；② `_calc_row_height` 逐行估算宽度求和，`<ul>` 多行列表块行高按实际行数，不再按总字符数低估导致 Excel 截断；③ `_split_html_blocks` 块级正则补 `<hr>`，游离文本并入前块时先 strip 自身换行再补单个 `\n`，消除 `\n\n` 被二次分段的隐患
  - **文档同步**：`folders.md` 统计项刷新（主程序 45,481 / scripts 4,097 / 测试 62,393 行、测试用例 3,964、项目文档 95、archive 修正 80=76 md+3 py+1 txt）+ `llm_content.py` 目录树描述补充；`test-coverage.md` 按 `collect-test-coverage.py` 实时快照更新（all 3964 / unit 3647 / unit_llm 691 / unit_report 1163 / 跨类 llm 530）；`reports-instruction.md` 补充 Excel 端摘要明细行灰色小字 + footer 单次呈现说明
- **rf-148：事实校验自动修正明细不可见（仅显示"修正 N 处"计数）** — 用户反馈（2026-08-02，他机运行报告）：智囊团深度复盘等模块事实校验摘要显示"21/24 项检查全部通过（自动修正 3 处数值）"，但修正明细（wrong%→correct% + 句段）不落盘、不在摘要展开，用户无法得知具体修正了哪些数值。修复：`run_fact_check` 自动修正后 ① 修正明细写入 `invest` 日志（模块标签 + `wrong%→correct%（句段）` 逐条）；② HTML 校验摘要追加灰色小字「已修正明细: …」行（追加在模块章节尾部，供用户直接查看）。新增回归测试 `test_corrections_detail_in_summary`（摘要含 `5.0%→30.3%` + 句段）/ `test_corrections_logged`（caplog 捕获日志含明细）。不破坏既有格式：`llm_content.py` 摘要正则匹配宽松，明细行不影响
- **rf-147：资产穿透 TOP10 两图风格不统一（行业分布横条 vs 穿透 TOP10 竖桩）** — 用户反馈（2026-08-02）：穿透章节两图并排，行业分布图为 `indexAxis: 'y'` 水平条，穿透 TOP10 为垂直柱状图，横竖混排观感割裂。修复：`chart-init.js` `initIndustryBar` 移除 `indexAxis: 'y'` 并调整 scales 为垂直配置（x 轴类别加 `maxRotation: 45` 防长行业名遮挡、y 轴数值网格），与 `initPenetrationBar` 竖桩风格统一；同步 `report_template.html` / `test-chart.html` 两图 aria-label 统一为「垂直柱状图」（穿透 TOP10 补充"垂直"前缀，语义与渲染一致）；`reports-instruction.md` 交互图表描述同步。新增回归测试 `test_industry_and_penetration_bars_both_vertical`（断言两图 aria-label 均含"垂直柱状图"且无"水平"残留）
- **rf-146：新闻去重 bg=2 梯度阈值显示不一致** — 校准脚本复跑（2026-08-02）：0.9.2 将代码阈值 0.45 调低至 0.40 时未全量同步——`news_dedup.py` docstring 仍写 "ratio ≥ 0.45"，`calibrate-dedup-threshold.py` 的 `_CROSS_BG2_RATIO = 0.45` 常量、梯度规则注释及「当前阈值规则」显示均仍为 0.45，而 `_dedup_by_title` 实际执行 `ratio >= 0.40`，校准报告展示的阈值规则与实际代码不符。修复：`news_dedup.py` docstring + `calibrate-dedup-threshold.py` 注释/常量/显示打印三处 0.45 → 0.40 全量同步。行为零变化（规则本身早已按 0.40 生效）；回归护栏由既有边界测试 `test_cross_source_bg2_high_ratio_merged` / `test_cross_source_bg2_low_ratio_kept` 锁定
- **rf-145：辩论 synthesis 综合权衡重复复述白脸/黑脸观点** — 实测报告（2026-08-02）：综合权衡出现完整"四、情景分析"段落，且各情景反复引用"黑方指出同质化风险""白方指出防守资产缓冲"复述双方观点。根因：`llm_debate_conditional`（条件推理）开启时 pro/con 因 `skip_scenarios=True` 不写情景分析，改由 synthesis 的 `_build_debate_synthesis_prompt` 注入"按涨/跌/震荡情景给出综合建议"指令；但 `_SYSTEM_DEBATE_SYNTHESIS` 仍残留 rf-93 时代"情景分析已在白脸/黑脸观点中给出、不要在综合权衡中插入情景分析段落"的**过时断言**——system prompt 与 user prompt 直接矛盾，LLM 为满足情景指令只能从白脸/黑脸正文抽取内容填充 → 复述双方观点（rf-93 当年仅改 prompt 文案软约束，conditional 功能合入后未同步更新 system prompt 造成回归）。修复：`_SYSTEM_DEBATE_SYNTHESIS` 保留为 conditional 关闭基线（维持"禁止插入情景分析"）；新增 `_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL` + `_build_system_debate_synthesis(enable_conditional)`，conditional 开启时改用强化版——明确允许按 user prompt 输出情景分析（消除指令冲突）+ 强化引用纪律（综合评估/行动建议/情景分析三部分均"引用一句话概括、不得展开复述"）+ 要求各情景差异化且不与正文机械重复；`generators.py` synthesis 阶段按 `_enable_conditional` 动态选择 system prompt

### Test

- **rf-149 回归测试** — `test_llm_content.py` 新增 `TestSplitHtmlBlocks` 9 例（`test_no_newline_between_p` 无换行 `<p>` 分段 / `test_no_block_tags` 纯文本 `\n\n` 回退 / `test_p_newline_p` / `test_orphan_span_merged_into_prev_block` 游离 `<span>` 并入前块 / `test_orphan_span_without_newline_gets_separator` 并入补 `\n` 防粘连 / `test_hr_separates_blocks` `<hr>` 独立分块 / `test_ul_list_kept_as_single_block` `<ul>` 整体一块）+ `TestWriteContentSheetFactCheck` 5 例（`test_footer_not_repeated_after_summary_appended` 摘要追加后 footer 仅末尾一次 / `test_warn_summary_first_line_amber_detail_gray` 告警首行琥珀+明细灰 / `test_pass_summary_green_corrections_gray` 通过首行绿+已修正明细灰 / `test_no_newline_p_tags_split_into_rows` 无换行多段独立单元格 / `test_ul_list_row_height_sufficient` 列表块行高按行数）+ `TestCalcRowHeight` 2 例（`test_multiline_uses_newline_count` / `test_multiline_takes_max_of_both` 多行行高）。LLM 套件 690 passed，dev-verify 1198 passed
- **rf-145 回归测试** — `test_debate_prompts.py` 新增 `TestBuildSystemDebateSynthesis` 3 例：`test_conditional_false_returns_baseline`（conditional 关闭返回 `_SYSTEM_DEBATE_SYNTHESIS` 基线、保留"禁止插入情景分析"）、`test_conditional_true_allows_scenario_with_citation_discipline`（conditional 开启：允许输出情景分析 + **不含**与 user prompt 冲突的"禁止插入情景分析"断言 + 强化引用纪律 + 输出结构含"5. 情景分析"）、`test_conditional_varies_by_flag`（开关切换返回内容不同）；`test_debate_generators.py` 新增 `test_system_prompt_uses_conditional_variant_when_enabled`（mock `generators.is_feature_enabled` 使 conditional 开启 → synthesis 阶段 system_prompt 切换为 `_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL`，且与 `_build_system_debate_synthesis(True)` 一致、无冲突断言）。LLM 套件 673 passed

### Docs

- **变更日志 / 实现计划 / 自审记录 0.9.* 版本记录归档迁移** — 将已发布版本（0.9.0 ~ 0.9.5，不含 dev）的变更记录 / 已完成计划项 / 已修复问题自审记录迁移至 `archive/v0.9.x/`：新增 `archived_changelog.0.9.x.md`、`archived_review-findings.0.9.x.md`（`archived_plan.0.9.x.md` 此前已含 plan-1/plan-7 已完成项索引）。三份管理文档（changelog.md / plan.md / review-findings.md）均保留对归档文档的引用，便于查看旧记录。同步 `scripts-reference.md`（补 `collect-test-coverage.py` 脚本条目）、`folders.md`（archive/v0.9.x 子树补 2 个归档文件 + 统计项更新）。

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.5（2026-07-30 ~ 2026-08-02）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
