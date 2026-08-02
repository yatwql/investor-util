# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.6-dev] - 2026-08-02

### Fix

- **rf-145：辩论 synthesis 综合权衡重复复述白脸/黑脸观点** — 实测报告（2026-08-02）：综合权衡出现完整"四、情景分析"段落，且各情景反复引用"黑方指出同质化风险""白方指出防守资产缓冲"复述双方观点。根因：`llm_debate_conditional`（条件推理）开启时 pro/con 因 `skip_scenarios=True` 不写情景分析，改由 synthesis 的 `_build_debate_synthesis_prompt` 注入"按涨/跌/震荡情景给出综合建议"指令；但 `_SYSTEM_DEBATE_SYNTHESIS` 仍残留 rf-93 时代"情景分析已在白脸/黑脸观点中给出、不要在综合权衡中插入情景分析段落"的**过时断言**——system prompt 与 user prompt 直接矛盾，LLM 为满足情景指令只能从白脸/黑脸正文抽取内容填充 → 复述双方观点（rf-93 当年仅改 prompt 文案软约束，conditional 功能合入后未同步更新 system prompt 造成回归）。修复：`_SYSTEM_DEBATE_SYNTHESIS` 保留为 conditional 关闭基线（维持"禁止插入情景分析"）；新增 `_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL` + `_build_system_debate_synthesis(enable_conditional)`，conditional 开启时改用强化版——明确允许按 user prompt 输出情景分析（消除指令冲突）+ 强化引用纪律（综合评估/行动建议/情景分析三部分均"引用一句话概括、不得展开复述"）+ 要求各情景差异化且不与正文机械重复；`generators.py` synthesis 阶段按 `_enable_conditional` 动态选择 system prompt

### Test

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
