# 实验性功能开关上屏：决策跨期反思闭环接入 TUI 菜单 S 与 Web 配置面板

> 状态：**已实现**——实验开关的上屏改为由 `features.EXPERIMENTAL_FEATURES` 注册表统一驱动（TUI 菜单 S / Web 配置面板 / CLI `--experiment` 三面同源），两处 UI 各自硬编码的实验开关列表已移除。

## Context

`decision_reflection`（决策跨期反思闭环，登记决策 → 真实行情结算命中率 → 教训回灌专家复盘提示词）已在上一轮实现为 P4 实验特性：默认关闭、开关存 `data/config/features.json`、报告三处接缝经 `decision_ledger.is_active()` 惰性判定。**但目前没有任何 UI 能开关它** —— 只能手工编辑 features.json。

问题根因：`features.EXPERIMENTAL_FEATURES`（唯一注册表，已含 4 项实验开关的显示名 + 说明，且保留插入顺序）被两处 UI **各硬编码了一份只含辩论的列表**：

- TUI `handlers_config.py::_cmd_config_llm_modules` 的 `DEBATE_FLAGS`（3 项 → 菜单 S 编号 6-8）
- Web `config_edit.py::_DEBATE_FLAG_KEYS`（驱动白名单 + surface）+ `main.js::CONFIG_LABELS.debate` + 组标题「辩论实验功能」

而 decision_reflection **不是辩论功能**（是决策账本 + 回灌闭环）。因此本方案按已确认方向：**两处 UI 均改为由 `EXPERIMENTAL_FEATURES` 驱动**，并把 Web 组从「辩论实验功能 / debate」更名为「实验性功能 / experiments」—— 语义正确、未来新增实验开关自动上屏、一举消除两处重复列表的既有技术债。

预期结果：TUI 菜单 S 的实验块出现第 9 项「⚗ 决策跨期反思闭环」，Web 配置面板出现第 4 个实验开关，两处与 `features.json` 即时同步。

## 变更范围

### 1. TUI — `src/python/tui/handlers_config.py`

`_cmd_config_llm_modules`：
- 惰性 import 增加 `EXPERIMENTAL_FEATURES`（与已有 `is_feature_enabled`/`save_feature_overrides`/`set_feature_enabled` 同一行）。
- 删除本地 `DEBATE_FLAGS` 字面量，改为由注册表派生（顺序天然为 3 辩论 → decision_reflection）：
  ```python
  experiment_flags = [(flag, name) for flag, (name, _desc) in EXPERIMENTAL_FEATURES.items()]
  ```
- 渲染循环 `enumerate(experiment_flags, len(module_names) + 1)`，编号自动 6→9；item 的 kind 由 `"debate"` 改为 `"experiment"`（切换分支仍是 `set_feature_enabled` + `save_feature_overrides`，逻辑不变）。
- 泛化底部提示两行（现为「实验性辩论模式默认关闭，开启后智囊团深度复盘输出含辩论内容」）→ 不再辩论专属，改为实验功能通用措辞（如「⚗ 实验性功能默认关闭，开启后按各自说明增强输出」+ 保留「⚠ 当前为实验阶段，输出质量可能不稳定」）。
- 同步更新函数 docstring（现描述「辩论模式增强（6-8）」）。

### 2. Web 后端 — `src/python/web/config_edit.py`

- 模块顶部 import `from src.python.config.features import EXPERIMENTAL_FEATURES`（features.py 仅依赖 `core.constants`，无循环依赖）。
- 删除 `_DEBATE_FLAG_KEYS`。
- 白名单第 7 组由注册表生成（白名单仍是唯一事实来源，只是不再手抄）：
  ```python
  # ── 7 实验性功能开关（features.json，来源 features.EXPERIMENTAL_FEATURES）──
  **{flag: {"kind": "bool", "target": "features", "writer": "features"} for flag in EXPERIMENTAL_FEATURES},
  ```
- `get_config_edit_surface` 中 `debate = {...}` → `experiments = {flag: is_feature_enabled(flag) for flag in EXPERIMENTAL_FEATURES}`，返回键 `"llm": {..., "experiments": experiments}`（原 `"debate"`）。
- 更新模块 docstring 与第 6/7 组注释措辞。

### 3. Web 前端 — `src/static/web/main.js`

- `CONFIG_LABELS`：`debate` 组键更名 `experiments`，并新增 `decision_reflection: '决策跨期反思闭环'`（4 项）。
- `renderConfigEdit`：`renderBoolGroup('experiments', '实验性功能（⚗ 实验性，默认关闭）', surface.llm.experiments, { experimental: true })`。
- 更新 LLM 组 `note` 文案（现称「下方『辩论实验功能』三个开关」）→ 指向「下方『实验性功能』对应开关」。
- 渲染器 `renderBoolGroup` 契约不变（仍是 `{key: bool}` + `CONFIG_LABELS[groupKey]`），不新增说明副标题——与现有辩论行保持一致的紧凑呈现。

### 4. 测试

- `src/test/unit/web/test_config_edit.py`（`@pytest.mark.unit, unit_web`）：
  - `_EXPECTED_WHITELIST` 第 7 组注释更新 + 新增 `decision_reflection`（精确集合断言）。
  - `test_surface_values_from_defaults`：`data["llm"]["debate"]` → `["experiments"]`；显式断言其键集合 = 4 项；保留 `all(v is False ...)`。
  - 新增 `test_decision_reflection_flag_write_takes_effect`（镜像既有 `test_debate_flag_write_takes_effect`）：写 `{"key": "decision_reflection", "value": true}` → 200、`is_feature_enabled` 生效、features.json 含覆写。
- `src/test/unit/handlers/test_handlers_config.py`（`@pytest.mark.unit, unit_core`）：
  - 新增 `_cmd_config_llm_modules` 回归测试：patch `handlers_config._read_llm_settings`（返回 `({}, path)`）、`core.registry.get_llm_module_names`、`tui.tui_menu.filter_menu_llm_modules`（返回 5 个标准模块）、`config.features.save_feature_overrides`、`input` side_effect `["9", "0"]`、`press_any_key`；断言 `save_feature_overrides` 以 `{"decision_reflection": True}` 调用——直接锁定「菜单第 9 项 = decision_reflection」这一用户可见行为。

### 5. 文档（语义命名纪律：正文用语义名，不出现任务代号）

- `docs-stm/manuals/how-to-use-tui-menu.md` §S：实验块表由 (6-8) 扩为 (6-9) 并加「9 ⚗ 决策跨期反思闭环」行；features 键名 ↔ 菜单编号对照表加 `decision_reflection | 9`；「⚗ 辩论模式说明」段泛化为实验功能措辞；「共 27 项开关」→ 28。
- `docs-stm/manuals/how-to-config.md` §M：标题与正文「27 项」→「28 项」；功能开关表新增 `decision_reflection | false | 决策跨期反思闭环…` 行；菜单 [S] 面板布局说明 6-8 → 6-9 并泛化；§P Web 映射表「辩论实验功能」行 → 「实验性功能」并列出 4 键 / `[S]` 6~9。
- `docs-stm/manuals/how-to-config-llm.md`：菜单 [S] 两段式措辞（~235 行）与 `debate` 配置段说明（~301 行）同步——澄清 debate 配置段与 decision_reflection 均「由 Feature Flag 启停」。
- `docs-stm/managements/technical.md`：实验开关计数（27→28，功能分组加「决策 1」）、白名单组描述（辩论实验 3 → 实验性功能 4）、`/api/config/edit` 7 组描述、「功能语义命名表」相关行同步。
- `docs-stm/managements/changelog.md`：新增一条（语义措辞，无任务代号）——实验性功能开关接入 TUI 菜单 S 与 Web 配置面板，两处改由 `EXPERIMENTAL_FEATURES` 驱动。
- `docs-stm/managements/test-coverage.md`：若新增测试方法使 unit_web/unit_core 计数变化，提交前跑 `scripts/collect-test-coverage.py` 按实时值刷新对应行（保持父=子和不变式）。
- `docs-stm/managements/review-findings.md`：自审若发现问题按流程登记；无问题则不新增。
- 无新增/重命名文件 → `folders.md` 目录树不变。

### 6. 计划文件归档

本计划属「中间计划文件」→ 获批后迁移到 `docs-stm/plan/`，不留在 `.claude/plans/`。

## 关键复用点（勿新造）

- `features.EXPERIMENTAL_FEATURES` — 唯一注册表（显示名 + 说明，顺序保留），两处 UI 的唯一数据来源。
- `features.is_feature_enabled` / `set_feature_enabled` / `save_feature_overrides` — 读写原语，不新增。
- `config_edit._dispatch_write` 的 `writer=="features"` 分支 — 已有，白名单生成后自动复用。
- `decision_ledger.FEATURE_FLAG` / `is_active()` — 运行时判定，无需改动（菜单开启后即生效，无需重启）。

## 验证

1. 单元：`.venv/bin/python -m pytest src/test/unit/web/test_config_edit.py src/test/unit/handlers/test_handlers_config.py -v --tb=short`
2. 交互手测：
   - 启动 TUI → 菜单 [S] → 确认实验块含 6/7/8/9，第 9 项为「⚗ 决策跨期反思闭环」；输入 9 切换后 `data/config/features.json` 出现 `"decision_reflection": true`。
   - 启动 Web → 配置编辑面板 → 确认「实验性功能（⚗ 实验性，默认关闭）」组含 4 项，勾选 decision_reflection 写盘成功（`features.json.bak` 生成）。
3. 格式：`.venv/bin/ruff format --check`。
4. P0 提交门禁：
   - `.venv/bin/python scripts/test-runner.py --mode dev-verify`
   - `.venv/bin/python scripts/check-code-traces.py --ci`
   - `.venv/bin/python scripts/check-doc-traces.py --ci`
   - `.venv/bin/python scripts/check-task-numbering.py --ci`
   - `.venv/bin/python scripts/check-semantic-index.py --ci`
5. 提交：本改动独立一次提交（与已完成的 decision_reflection 实现提交分离）。
