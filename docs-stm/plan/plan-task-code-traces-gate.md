# 增强 check-code-traces.py：任务编号标识符/注释检查

## Context

CLAUDE.md 语义命名纪律规定：代码标识符（函数/变量/类名）与注释**一律用语义名，禁止用任务代号**（`plan-N`/`rf-N`/B 系列/F 系列等）。但 `scripts/check-code-traces.py` 目前只扫描**注释/文档串**，CODE 模式仅 `(?:rf|plan|R)-\d+`：
- 抓不住 `b_series`、`G系列`、`F4`、`B6` 这类系列代号
- 完全不扫描**代码标识符**（变量名/函数名/类名）

用户要求增强：标识符 + 注释都不能含任务编号（例：`b_series`、`G系列`、`F4`、`B6`、`plan-18`、`rf-185`）。

**误报面已实证（全部通过 grep/AST 全仓扫描验证）**：
- `C1~C20`（架构约束）、`P1`（优先级）、`S-P1~P4`（场景 ID）、`Y1/Y3`（edge 类后缀）、`A3/O1/R17/S2/TD8`（JS 注释约束引用）、`f9/f20/f57`（东财 API 字段码）、`f1~f4`（concurrent.futures Future 变量）、`b1/b2`（按钮）、`h1/t1/f1/x0/p50`（测试脚手架短局部）——**均合法**，不得误伤
- `[A-Za-z]系列` 在 src 全仓 **0 命中**；大写裸 `[A-Z]\d{1,3}` 独立标识符 **0 命中**（所有独立字母+数字标识符全是小写）；单字母 `_series` 无命中（现有 `drawdown_series`/`holding_series` 是多字母词+series，合法）

## 设计

### 1. 注释侧：扩展 CODE 模式（`PATTERNS`）

在现有 `(?:rf|plan|R)-\d+` 基础上新增 3 条（全部零误报）：

| 模式 | 说明 |
|------|------|
| `(?<![A-Za-z])[A-Za-z]_series\b` | 单字母+`_series`（如 `b_series`）；负向 lookbehind 排除 `drawdown_series` |
| `[A-Za-z]系列` | 任务批次系列别名（如 `G系列`）；`全系列/中证指数系列` 前缀为 CJK 不匹配 |
| `\b[BFG][0-9]{1,2}\b` | 任务族字母+数字（如 `F4`、`B6`），仅大写族字母，区别于合法 `C20`/`P1`/`S-P1`；族字母抽为可配置 `TASK_FAMILY_LETTERS` frozenset（默认 B/F/G，新增族一行扩展） |

### 2. 标识符侧：新增扫描维度（类别 `IDENT`，等同 CODE 退出码 2）

新增 `IDENTIFIER_PATTERNS: list[tuple[str, str, str]]`（pattern 匹配**完整标识符 token**）：

| 模式 | 说明 |
|------|------|
| `^[A-Z][0-9]{1,3}$` | 大写裸字母+数字独立标识符（`F4`、`B6`），无语义常量名 |
| `^[A-Za-z]_series$` | 单字母+`_series`（`b_series`） |
| `^[A-Za-z]系列$` | 单字母+`系列`（`G系列`，Python 3 允许 unicode 标识符） |
| `rf[_-]?\d+` / `plan[_-]?\d+`（子串） | 任务编号嵌入标识符（`rf_205_fix`、`plan18_hack`） |

**实现**：
- 新函数 `_iter_identifiers(fpath)`：
  - `.py`：用 `ast` 遍历——`FunctionDef/AsyncFunctionDef/ClassDef.name`、函数参数（args/kwonlyargs/posonlyargs/vararg/kwarg）、`Name`(Store) 赋值目标、`alias.asname/name`、`arg`
  - `.js/.mjs`：正则提取声明 `\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)\b` + 箭头函数参数
  - `.html`：跳过（内联 JS 由 .js 覆盖）
- `scan_file` 在注释扫描后追加标识符扫描；`_is_tool_self`/`SKIP_FILES` 同注释扫描豁免
- `main()`：`IDENT` 计入 `code_count`（与 CODE 同走退出码 2），汇总行区分显示

### 3. 明确不捕获（文档写明局限）
- 小写裸字母+数字短局部名（`h1/t1/f1/x0/p50`）——与 Future 变量/API 字段码/测试脚手架结构同形，无法区分，误报风暴
- 注释中**非族字母**大写代号（`C20`/`P1`/`S-P1`/`A3`/`R17`）——合法交叉引用
- 小写族字母+数字在注释中（`f9/f20/f57` API 字段）——故族字母规则限大写

## 修改文件

1. **`scripts/check-code-traces.py`**
   - `PATTERNS` CODE 段加 3 条模式；`TASK_FAMILY_LETTERS` frozenset
   - 新增 `IDENTIFIER_PATTERNS`、`_iter_identifiers()`、`_scan_identifiers()`；`scan_file`/`main` 接线
   - docstring 更新（新增 IDENT 维度 + 退出码语义）

2. **`src/test/unit/scripts/test_trace_check_scripts.py`**（沿用 `unit_scripts` marker）
   - 注释模式正/负用例：`b_series 说明`/`G系列`/`F4 方案` 命中；`drawdown_series`/`全系列`/`C20 约束`/`f9=市盈率` 不命中
   - 新增 `_ident_hit()` 辅助 + 标识符用例：`F4=1`/`b_series=1`/`G系列=1`/`def rf_205_hack()` 命中；`f1=1`/`drawdown_series=[]`/`h1=1`/`p50=1` 不命中
   - `_iter_identifiers` 对 Python 代码片段的提取断言

3. **`scripts/check-doc-traces.py`**（一致性，廉价）：CODE 段加 `[A-Za-z]系列`、单字母 `_series` 两条（docs 正文同样禁用任务代号）

4. **文档**（per CLAUDE.md）：
   - `docs-stm/managements/review-findings.md`：记 rf-208（门禁缺口：任务编号标识符/注释未强制）→ 修复后移入已修复摘要，`rf-next` 递增
   - `docs-stm/managements/changelog.md`：补 rf-208 变更记录
   - `CLAUDE.md` 语义化命名段：补一句「check-code-traces 强制校验标识符+注释任务代号」

## 验证

1. `python scripts/check-code-traces.py --ci` → 对现有代码 **0 命中**（新增模式零误报）
2. `python -m pytest src/test/unit/scripts/test_trace_check_scripts.py -v --tb=short` → 全过（新增+既有用例）
3. `python scripts/test_runner.py --mode dev-verify` + `check-task-numbering.py --ci` + `check-doc-traces.py --ci` → P0 门禁全绿
4. 手工冒烟：临时构造含 `F4`/`b_series`/`rf_205_fix` 的代码片段确认被检出、含 `C20`/`h1`/`drawdown_series` 的不被检出

## 收尾
- 本计划文件（`.claude/plans/`）用毕后迁移到 `docs-stm/plan/`（CLAUDE.md 违规补救要求）
