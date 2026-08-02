# 修复：集中度问答无输出内容 + 资产穿透TOP10 两柱状图区分优化

> **状态**：rf-150 已实现并通过回归验证（v0.9.6 发布，当前开发版本 v0.9.7-dev）。设计文档保留在 `docs-stm/plan/`，待 release 后随版本段归档。

## Context

用户在另一台机器运行报告，开启"智囊团深度复盘"辩论模式的三个开关（正反辩论 / 条件推理 / 集中度问答），但报告中**看不到集中度问答内容**。同时希望优化"资产穿透TOP10"章节两个柱状图：**明显区分两图**（当前都用主色蓝）并**分两行显示**（当前 flex 并排，小屏显示不齐）。

### 根因一：集中度问答实际不产生任何可见内容（代码缺陷，与机器无关）

即使 `llm_debate_qa_concentration` 开关开启，报告里也没有集中度回答内容，原因有二：

1. **`_build_qa_concentration_block()`**（`src/python/llm/prompts_action.py:115`）生成的集中度引导段末尾明确写着"**（以上问题旨在引发思考，无需在本次报告中回答。）**"——只是"让 LLM 想一想"的提示，LLM 不会输出任何集中度回答。这与需求文档 `R-LLM-DB-QA-CONCENTRATION-03`（要求"输出集中度风险的量化评估、与分散化基准的定量对比、针对性的调仓建议"）矛盾。实现沿用了设计文档 I-05 的"反问引导"方案，但需求描述的是"要输出内容"。
2. **辩论模式的综合权衡（synthesis）阶段完全不支持集中度问答**：`_build_debate_synthesis_prompt()`（`prompts_action.py:472`）只接受 `enable_conditional`（条件推理）参数。用户在辩论模式下看到的主体内容正是**综合权衡**，条件推理能显示（synthesis 支持 conditional），集中度问答则无处可现。

附带缺陷：`_build_expert_review_prompt()` 调用 `_build_qa_concentration_block()` 时 `threshold=0.20` 硬编码（`prompts_action.py:334`），未读取 `llm_settings.json` 的 `debate.qa_concentration.threshold` 配置（违反需求 `R-LLM-DB-QA-CONCENTRATION-04`）。

### 根因二：资产穿透TOP10 两柱状图难以区分 + 并排布局小屏不齐

- 两图（行业分布 `chart_industry_bar`、穿透TOP10 `chart_penetration_bar`）都是垂直柱状图且都用主色蓝 #2E75B6（`chart-init.js:184` / `:218`）。
- 模板 `report_template.html:873` 中两图在 `.penetration-charts` flex 容器并排（`flex:1; min-width:280px`），小屏容易显示不齐。

## 修复方案

### A. 集中度问答：对齐需求，让综合权衡真正输出"### 集中度问答"章节

**A1. `prompts_action.py` — `_build_qa_concentration_block()`（115-180 行）**
- 删除结尾"（以上问题旨在引发思考，无需在本次报告中回答。）"，改为**要求回答**的引导语。
- 触发器逻辑不变（单品种>阈值 / 前3>60% / 行业>40%），输出改为要求 LLM 针对每项集中度风险给出：① 量化评估（对比 20%/60%/40% 基准，标注超限幅度）；② 与分散化基准的定量对比；③ 针对性的调仓建议。
- 该函数同时被标准模式（非辩论）expert_review 复用，符合需求 R-LLM-DB-QA-CONCENTRATION-05（集中度问答嵌入智囊团复盘输出中）。

**A2. `prompts_action.py` — `_build_debate_synthesis_prompt()`（472-514 行）**
- 新增参数：`enable_qa_concentration: bool = False`、`industry_concentration: dict | None = None`、`holdings_details: list[dict] | None = None`、`total_mv: float = 0`。
- 当 `enable_qa_concentration=True` 时，追加集中度问答指令段：调用 `_build_qa_concentration_block()` 生成引导（要求回答版），并明确要求"在综合权衡中输出 **'### 集中度问答'** 章节，位于调仓建议之前"。

**A3. `prompts_core.py` — `_build_system_debate_synthesis()`（589-604 行）**
- 扩展签名：`_build_system_debate_synthesis(enable_conditional=False, enable_qa_concentration=False)`。
- qa 启用时在所选版本（基线/conditional）末尾追加一句，要求 LLM 遵循 user prompt 输出集中度问答章节（不重写编号结构，避免与 conditional 的"5.情景分析"冲突）。

**A4. `generators.py` — `generate_debate_procon()`（355-617 行）**
- 调用 `_build_debate_synthesis_prompt()` 时传入 `enable_qa_concentration=_enable_qa_concentration`、`industry_concentration=_industry_conc`、`holdings_details`、`total_mv`。
- 调用 `_build_system_debate_synthesis(_enable_conditional, _enable_qa_concentration)`（当前只传 conditional）。
- `_enable_qa_concentration` 与 `_industry_conc` 在函数内已计算（393-394 行），直接复用。

**A5. threshold 硬编码修复**
- 在 `_build_expert_review_prompt()`（`prompts_action.py:330-338`）和 `generate_debate_procon()` 中，从 `llm_settings.json` 的 `debate.qa_concentration.threshold` 读取阈值（默认 0.20），替换硬编码。读取方式仿照同函数 conditional 分支已有的 `get_llm_config()` 内联读取模式（298-300 行）。

### B. 资产穿透TOP10 两柱状图：蓝+橙区分 + 分两行布局

**B1. `chart-config.js` — `ChartTheme` 新增 `barColors`**
- `barColors: ['#2E75B6', '#E68A00']`（蓝/橙，与现有 A3 色盲安全 palette 一致）。

**B2. `chart-init.js` — 两图默认底色区分（保持垂直柱状图，不破坏 rf-147 测试）**
- `initIndustryBar()`（170-202 行）：backgroundColor 默认 `ChartTheme.barColors[0]`（蓝）。
- `initPenetrationBar()`（204-236 行）：backgroundColor 默认从 `'rgba(46,117,182,0.75)'` 改为 `ChartTheme.barColors[1]`（橙 #E68A00），可加半透明 `rgba(230,138,0,0.75)`。
- 颜色遵循 A3 约束"颜色 JS 侧单一来源"（`test_chart_data_builder.py:281` 断言 Python 侧 dataset 不硬编码颜色），Python 侧 `chart_data_builder.py` **不改**。

**B3. `report_template.html` — 两图分两行显示**
- 模板 873-892 行：保留 `.penetration-charts` flex + wrap 容器，但两个子 div 的样式从 `flex: 1; min-width: 280px;` 改为 `flex: 1 1 100%; max-width: 720px; margin: 0 auto;`——每图独占一行、居中，小屏天然适配。
- canvas 的 id / aria-label / `.chart-box` 结构不变，不破坏 `test_html_report_structure.py` 的 canvas 数量与存在性断言。

## 测试（遵循项目"缺陷自测 + 强制 marker"约定）

集中度问答：
- **更新** `src/test/unit/llm/test_debate_qa.py`：`test_disclaimer_present`（原断言"以上问题旨在引发思考"，改为新引导语断言，如"集中度问答"或"量化评估"）；补充新引导语含"调仓建议"的断言。
- **新增** `_build_debate_synthesis_prompt` 的 qa_concentration 测试（enable_qa_concentration=True 时 prompt 含集中度问答指令；False 时不含）→ 放 `test_debate_prompts.py`（`@pytest.mark.unit_llm`）。
- **新增** `_build_system_debate_synthesis(enable_conditional, enable_qa_concentration)` 组合测试 → `test_debate_prompts.py`。
- **新增** threshold 配置读取测试（mock `get_llm_config` 返回自定义 threshold，断言 `_build_qa_concentration_block` 按该阈值触发）。
- 检查 `test_debate_generators.py` 现有 synthesis system prompt 测试（如 `test_system_prompt_uses_conditional_variant_when_enabled`）在签名扩展后仍通过；必要时同步更新。

柱状图：
- `test_chart_data_builder.py` / `test_chart_data_builder_edge.py`：不改 Python dataset，预计不受影响，跑一遍确认。
- `test_html_report_structure.py`：`test_penetration_charts_rendered_when_data`（canvas 数量 6）、`test_industry_and_penetration_bars_both_vertical`（垂直柱状图 aria-label）预计不受影响，跑一遍确认。

## 文档

- `docs-stm/managements/review-findings.md`：新增自审问题 `rf-150`（集中度问答设计/需求不一致：反问引导"无需回答"导致无输出 + synthesis 阶段缺失 + threshold 硬编码）。修复后移除详细说明（仅留摘要行）。
- `docs-stm/managements/changelog.md`：记录集中度问答修复 + 柱状图优化。
- 需求文档 `R-LLM-DB-QA-CONCENTRATION-*` 本身正确，不改；实现对齐需求即可。

## 验证

1. 集中度问答单测：`python -m pytest src/test/unit/llm/test_debate_qa.py src/test/unit/llm/test_debate_prompts.py src/test/unit/llm/test_debate_generators.py -v --tb=short`
2. 柱状图单测：`python -m pytest src/test/unit/report/test_chart_data_builder.py src/test/unit/report/test_html_report_structure.py -v --tb=short`
3. 全量门禁：`python scripts/test_runner.py --mode dev-verify` + `python scripts/check-history-traces.py --ci`
4. 手动验证（可选，需 LLM 配置）：开启三个 debate feature 生成一份报告，确认综合权衡含"### 集中度问答"章节；打开 HTML 查看穿透章节两图分两行显示、颜色蓝/橙区分。
