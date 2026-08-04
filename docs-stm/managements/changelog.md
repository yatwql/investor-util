# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.1-dev] - 2026-08-04

### rf-208 门禁补强：任务编号标识符/注释纪律（check-code-traces.py / check-doc-traces.py）

- **缺陷**：语义命名纪律要求代码标识符与注释一律语义名、禁任务代号（`plan-N`/`rf-N`/B 系列/F 系列等），但 `check-code-traces.py` 只扫注释且 CODE 模式仅 `(?:rf|plan|R)-\d+`——抓不住 `b_series`/`G系列`/`F4`/`B6` 系列代号，也完全不扫代码标识符（变量/函数/类名）。
- **修复**：
  - **注释侧**（`check-code-traces.py` + `check-doc-traces.py` 的 CODE 模式）：新增 `[A-Za-z]系列`、单字母`_series` 两条零误报系列代号模式（负向 lookbehind 排除 `drawdown_series` 等合法多字母词）。
  - **标识符侧**（`check-code-traces.py` 新增扫描维度）：`.py` 用 `ast` 精确提取函数/类/参数/赋值目标/导入别名，`.js/.mjs` 用正则提取声明名；`IDENTIFIER_PATTERNS` 捕获大写裸字母+数字（`F4`/`B6`）、单字母`_series`/`系列`、嵌入 `rf/plan`+数字（`rf_205_fix`/`plan18_hack`）；`IDENT` 类等同 CODE 退出码 2。
  - **明确不捕获**（避免误伤，注释侧含原因）：小写短局部名（`h1/t1/f1`——Future/测试脚手架）、注释中裸"族字母+数字"（与 Excel 单元格 `A1/B2` 结构性冲突）、`C20`/`P1`/`S-P1`/`A3`/`R17` 等合法约束/优先级/场景/需求交叉引用。
- **测试**：`src/test/unit/scripts/test_trace_check_scripts.py` 新增 9 例——注释系列代号正/负用例（`b_series`/`G系列` 命中；`drawdown_series`/`全系列`/`C20`/`A1:B1` 不命中）、标识符违规命中与合法短局部不命中、`_iter_identifiers` AST/JS 提取断言。
- **验证**：`check-code-traces.py --ci`/`check-doc-traces.py --ci` 对现有代码仓 0 命中（新增模式零误报）。

### rf-207 数值校验策略 1 忽略句中明确品种代码（漏检）（fact_checker 数值一致性）

- **缺陷**：`_evaluate_percent_value` 策略 1 做全局最近邻匹配，句中已含明确品种代码/名称时仍与全部参考收益率比较——数值只要接近任一无关品种（容差内）即判定一致，不按句中主体校验。例：601939 实际 1.87%、240012 实际 2.24%，「建设银行收益率 3.2%」→ 3.2 与 240012 差 0.96≤容差被误判通过，漏检与主体 601939 的 1.33 超差。与 rf-205（过修）方向相反，属漏检。
- **修复**：主体解析提前到策略 1 前——句中有明确持仓主体（句中单个持仓代码 / 名称指代）时按该主体实际收益率校验（容差内通过、超差报错到该主体），无主体或主体无收益率数据（`stock_rates_abs` 缺失）时回退全局最近邻（历史语义）；主体解析块上移后去除底部重复逻辑。
- **测试**：`src/test/unit/llm/test_fact_checker.py` 新增 `TestRegressionExplicitSubjectBeatsGlobalNearest` 5 例——名称/代码指代主体超差被修正到该主体、主体容差内通过、无主体回退全局最近邻、主体无收益率数据回退不崩溃。
- **验证**：全仓 `check-code-traces.py --ci` 仍 0 命中（新注释无任务编号）；llm 目录 738 例全过。

### rf-206 版本一致性回归测试 Windows 路径分隔符失效（test_check_version_consistency）

- **缺陷**：`TestDocHeaderRegistration::test_doc_header_docs_registered_as_header` 硬编码正斜杠路径（`docs-stm/managements/plan.md`），而 `check-version-consistency.py` 的 `CHECKS` 用 `Path` 拼接、`relative_to` 在 Windows 返回反斜杠分隔 → `types.get(rel)` 恒为 None，dev-verify 必失败。随 rf-204 引入，从未在 Windows 通过。
- **修复**：构造 CHECKS 类型字典时把 `relative_to` 结果分隔符规范化为 `/`（`.replace("\\", "/")`），Linux/macOS 无副作用。
- **测试**：修复即回归——同一用例在 Windows 通过，dev-verify 全绿。

### rf-205 事实校验误修正非收益率数值 + 亏损符号丢失（fact_checker 数值一致性）

- **缺陷**：`_evaluate_percent_value` 的 closest-ref 最近邻匹配假设报告每个百分比都是持仓收益率，把非收益率语境数值误修正并污染 2026-08-04 报告 HTML：胜率 `80%→8.9%`、评分权重 `20%/25%→16.6%/26.0%`、相对基准跑输差 `1.10%→2.2%`；且 `stock_rates_abs` 取绝对值使亏损品种（518880 实际 -8.86%）修正输出 `+8.9%`，亏损写成盈利。
- **修复**：补「胜率/权重/相对基准跑输跑赢」三种近邻语境跳过（数值紧邻语境词才判定，避免同句真实收益率被连带跳过）；修正输出改用带符号收益率（`stock_rates`/`profit_rate_signed`）保留盈亏方向。
- **测试**：`src/test/unit/llm/test_fact_checker.py` 新增 `TestRegressionFalseCorrectionContexts` 5 例（胜率/权重/相对基准不被修正、亏损符号保留、run_fact_check 整链路摘要无修正明细）。
- **关联**：方向相反的同源弱点（句中含明确代码时策略 1 仍全局最近邻 → 漏检）见 rf-207（已修复）。

### rf-204 版本一致性检查缺陷修复（check-version-consistency.py）

- **缺陷**：`_check_contains` 仅判断全文是否包含目标版本串，正文偶然出现的版本号（如 v0.10.0）会掩盖头部 `文档版本：` 行未同步，导致漏检误判 [OK]。
- **修复**：管理文档改用新增的 `header` 断言——按 `> 文档版本：{v}` 头部行首精确匹配；`--fix` 模式自动修正头部版本行；changelog（`[X.Y.Z]` 标题行）保留 contains、README（`当前版本：`）保留 exact。
- **测试**：新增 `src/test/unit/scripts/test_check_version_consistency.py`（9 例，覆盖 rf-204 回归场景/头部精确匹配/--fix 修正/CHECKS 注册防止退回 contains）。

### 历史任务编号冲突清理（check-task-numbering.py 全局校验）

- **背景**：v0.8 归档（2026-07-30 创建）已占用 plan-12/13/14 与 rf-90~135；v0.9 开发（07-31 起）重新从 plan-12、rf-90 起编号，造成两代归档编号交叉冲突。
- **plan 编号修复**：v0.9 归档中的组合演进项 plan-12 → **plan-15**；HTML 左侧 TOC 项（新需求）→ **plan-16**（不得占用 v0.8 已用 plan-12）。`plan-next` 更新为 **17**。
- **rf 编号修复**：v0.9 归档中与 v0.8 冲突的 30 个编号（90-112、115、116、119、122-125）按升序整体重命名为 **rf-174 ~ rf-203**（定义行 + changelog/plan 归档内交叉引用同步替换；`archived_changelog.0.9.x.md` L424 为 v0.8 迁移参考行，保留原编号）。`rf-next` 更新为 **204**。
- **约束遵守**：跨文档引用带前缀、历史已归档编号不回收、编号源标记单调递增不回退；`scripts/check-task-numbering.py --ci` 验证 plan（17 > 16）与 rf（204 > 203）全局无冲突。

### 任务编号自动保障机制（三层 + P0 门禁）

- **校验脚本**：新增 `scripts/check-task-numbering.py`（`--kind plan/rf` 单序列、`--ci` 静默模式），扫描当前管理文档 + 全部历史归档，断言 `plan-next`/`rf-next` 严格大于已用最大编号，防止新增编号撞历史。
- **Claude Code hook**：新增 `scripts/check-task-numbering-hook.py`（PostToolUse，编辑 `plan.md`/`review-findings.md` 后自动校验、失败中断编辑）+ `scripts/install-claude-hook.py`（跨机器接线，`.claude/settings.json` 被 gitignore 排除，clone 后运行一次激活）。
- **git pre-commit**：新增 `.githooks/pre-commit`（提交涉及编号文档时自动校验）+ `.githooks/install-hooks.sh`（`core.hooksPath` 为本地配置，clone 后运行一次激活，`--off` 停用）。
- **dev-verify 门禁**：`test_runner.py` dev-verify 模式新增 `preflight` 机制，运行测试前自动执行 `check-task-numbering.py --ci`，失败即中止并提示修正。
- **P0/P2 门禁描述**：CLAUDE.md 提交前（P0）/发布前（P2）门禁追加 `check-task-numbering.py --ci`，与 `check-code-traces.py` 同构。
- **测试**：新增 `src/test/unit/scripts/test_task_numbering_hook_scripts.py`（14 例，hook 目标判定/放行/拦截/OSError 兜底/双注入方式 + 安装脚本幂等/合并/卸载；全部用 tmp_path 假文件隔离，不触碰真实编号文档）。

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
