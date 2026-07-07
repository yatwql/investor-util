# C-P1b 迭代计划：Excel 页签编号跟随用户 `report_section_order` 配置

> **版本**：v0.2.86  
> **创建日期**：2026-07-05  
> **关联文档**：`docs-stm/plan/c-iteration-design.md`、`docs-stm/managements/plan.md`（§C-P1b）

---

## 上下文

### 问题

C 迭代（v0.2.85）实现了报告页签序号可配置功能：

- ✅ HTML 报告序号（导航栏、章节标题）跟随用户配置
- ✅ Excel 页签**物理顺序**跟随用户配置
- ❌ **Excel 页签标题中的数字**始终显示默认序号（1-16），不跟随用户配置

### 根因分析

`set_sheet_title()`（`registry.py:351`）始终只查 `_REPORT_SECTION_DEFAULT` 取 number，不接收 `section_order` 参数。调用链路有三层：

1. `_create_sheets()`（`excel_generator.py:550`）→ `set_sheet_title(ws, sec["key"])` — 应传序号的源头
2. 11 个独立 sheet 写入器各自调用 `set_sheet_title(ws, "<key>")` — 覆盖了 `_create_sheets` 的设置
3. `generate_excel_report()` / `generate_html_report()` 内部调 `get_report_section_order()` **不带 config** → 即使序号跟随了自定义顺序，也用的是默认序号

### 范围

| 文件 | 行 | 当前问题 | 修复方式 |
|:-----|:--:|:---------|:---------|
| `registry.py` | 351-366 | `set_sheet_title` 只查 `_REPORT_SECTION_DEFAULT` | 增加可选 `section_order` 参数，优先从配置取 number |
| `excel_generator.py` | 540-552 | `_create_sheets` 不传 `section_order` | 调用 `set_sheet_title` 时传入当前 sec |
| `excel_generator.py` | 601 | `get_report_section_order()` 不带 config | 通过参数接收 config/section_order |
| `html_writer.py` | 233 | 同上 | 通过参数接收 config/section_order |
| `handlers_report.py` | 24-349 | 调用 `generate_excel_report` / `generate_html_report` 时不传 config | 增加 `section_order` 参数传递 |
| 11 个 sheet 写入器 | 各 1 行 | 各自调用 `set_sheet_title` 覆盖标题 | 移除冗余的 `set_sheet_title` 调用 |
| `test_registry.py` | 324-349 | 只测默认值 | 新增 config-aware 测试用例 |
| `test_excel_generator.py` | 全文件 | 未测 sheet 标题 | 新增 `_create_sheets` + 标题断言 |
| 各 sheet 写入器测试 | 多处 | 断言硬编码默认序号 | 更新为正确序号 or 移除断言 |

---

## Phase 划分

### Phase 1：`set_sheet_title` 核心改造 + `_create_sheets` 传参

**目标**：`set_sheet_title` 能接收 `section_order`，`_create_sheets` 能正确传参。

**改动**：

1. `registry.py` — `set_sheet_title(ws, key, section_order=None)`
   - 当 `section_order` 不为 None 时，遍历 `section_order` 匹配 key，取 `sec["number"]`
   - 当 `section_order` 为 None 时，保持现有行为（查 `_REPORT_SECTION_DEFAULT`）
   ```python
   def set_sheet_title(ws, key: str, section_order: list[dict] | None = None) -> None:
       source = section_order or _REPORT_SECTION_DEFAULT
       for sec in source:
           if sec["key"] == key:
               ws.title = f"{sec['number']}.{sec['name']}"
               return
       ...
   ```

2. `excel_generator.py` — `_create_sheets()`
   - `set_sheet_title(ws, sec["key"])` → `set_sheet_title(ws, sec["key"], section_order)`

**可测试性**：  
- 单元测试：`test_registry.py` 新增 `TestSetSheetTitleWithOrder`，传入自定义 `section_order` 验证标题
- 单元测试：`test_excel_generator.py` 新增 `_create_sheets` 的隔离测试

**可回退**：函数签名向后兼容（`section_order=None` 默认），不改动任何调用方。  
**风险**：低 — 函数接口扩展，不修改现有行为。

---

### Phase 2：移除 11 个写入器的冗余 `set_sheet_title` 调用

**目标**：`_create_sheets` 是唯一设置 sheet 标题的地方，各写入器不再覆盖。

**改动**（纯删除）：

| 文件 | 行 | 删除内容 |
|:-----|:--:|:---------|
| `summary.py` | 254 | `set_sheet_title(ws, "summary")` |
| `market_value.py` | 592 | `set_sheet_title(ws, "market_value")` |
| `category.py` | 175 | `set_sheet_title(ws, "category")` |
| `penetration_sheet.py` | 127 | `set_sheet_title(ws, "penetration")` |
| `fund_performance.py` | 362 | `set_sheet_title(ws, "fund_performance")` |
| `fund_manager_sheet.py` | 65 | `set_sheet_title(ws, "fund_manager")` |
| `fund_overlap_sheet.py` | 77 | `set_sheet_title(ws, "fund_overlap")` |
| `fund_concentration_sheet.py` | 85 | `set_sheet_title(ws, "fund_concentration")` |
| `fund_style_sheet.py` | 66 | `set_sheet_title(ws, "fund_style")` |
| `news_correlation.py` | 509 | `set_sheet_title(ws, "news_correlation")` |
| `early_warning.py` | 309 | `set_sheet_title(ws, "early_warning")` |

**同步更新测试（约 6 处断言）**：
- `test_summary.py:688` — 删除或改为在调用前由 fixture 预设标题
- `test_market_value.py:1391` — 同上
- `test_early_warning.py:288,302` — 同上
- `test_llm_content.py:254-257` — 同上（已由上一会话修复过标题号）

**可测试性**：移除后各写入器的单元测试中，`ws.title` 断言需设为 fixture 预设（写入器不再负责设标题）。  
**可回退**：纯删除，git revert 即可。  
**风险**：中 — 需确认没有代码路径直接调用写入器而不经过 `_create_sheets`。所有入参 `ws` 均由调用方传入，`_create_sheets` 在 `generate_excel_report` 开始时即创建所有页签，因此安全。

---

### Phase 3：Config 接入 — 将 `section_order` 传入报告生成链路

**目标**：`generate_excel_report` / `generate_html_report` 能接收用户的 `report_section_order` 配置。

**改动**：

1. `excel_generator.py:generate_excel_report()`
   - 新增可选参数 `section_order: list[dict] | None = None`
   - 内部改为：`order = section_order or get_report_section_order()`
   - 传给 `_create_sheets` 和内部各子函数

2. `html_writer.py:write_html_report()`
   - 新增可选参数 `section_order: list[dict] | None = None`
   - 类似逻辑

3. `handlers_report.py`
   - 各 `_cmd_*` 函数中读取 config（已有 `config = get_config_cache()`）
   - 调用 `get_report_section_order(config)` 获取合并后的 section_order
   - 传入 `generate_excel_report` / `write_html_report` 的 `section_order` 参数

**可测试性**：  
- `test_excel_generator.py` 可注入自定义 `section_order`，验证生成 sheet 的顺序和标题
- `test_handlers.py` 可 mock config 后验证正确的 section_order 被传入

**可回退**：参数可选 None → 保持现有行为。  
**风险**：低 — 参数扩展，不修改现有行为。

---

### Phase 4：新增测试 + 回归验证

**目标**：覆盖新增功能，确保无回归。

**新增测试用例**：

| 文件 | 类/方法 | 覆盖内容 |
|:-----|:--------|:---------|
| `test_registry.py` | `TestSetSheetTitleWithOrder` | 传入自定义 section_order → 标题使用正确序号 |
| `test_registry.py` | 同上 | 传入部分自定义 → 未配置项使用默认序号 |
| `test_registry.py` | 同上 | 传入 None（向后兼容）→ 使用默认序号 |
| `test_excel_generator.py` | `TestCreateSheets` | `_create_sheets` 按自定义顺序创建 sheet、标题正确 |
| `test_excel_generator.py` | 同上 | 可见性过滤 + 标题断言 |
| `test_scenario_section_order.py` | `test_custom_order_excel_titles` | 端到端：用户配置自定义报告顺序 → 生成的 Excel 页签标题跟随配置 |
| `test_scenario_section_order.py` | `test_custom_order_html_titles` | 端到端：HTML 标题确认正确 |

**回归验证**：
```
python scripts/test_runner.py --mode verify    # P1 门禁（898 项）
python scripts/test_runner.py --mode all       # P2 全量（2421 项）
```

---

### Phase 5：文档更新

**目标**：更新技术文档和管理文档，反映 C-P1b 已完成。

| 文档 | 更新内容 |
|:-----|:---------|
| `docs-stm/managements/plan.md` | §C-P1b 标记为已完成，移除"已知限制"段落 |
| `docs-stm/managements/technical.md` | 在介绍 C 迭代处补充 Excel 页签编号跟随配置 |
| `docs-stm/managements/changelog.md` | 新增 v0.2.86 条目，说明 C-P1b 修复 |
| `docs-stm/manuals/reports-instruction.md` | 如有提及"页签标题固定编号"的描述，同步更新 |

---

## 风险与缓解

| 风险 | 等级 | 缓解 |
|:-----|:----:|:-----|
| 移除写入器 `set_sheet_title` 后，某未发现的直接调用路径中断 | 中 | Phase 2 后立即运行全量测试 + 真人验证生成一份完整报告 |
| Config 在 `handlers_report.py` 中不可达 | 低 | 已有 `get_config_cache()` 模式 |
| 与用户配置的 `llm_usage` 强制末位冲突 | 低 | `get_report_section_order` 已有处理逻辑 |
| Phase 间有依赖无法并行 | 低 | 严格按 Phase 1→2→3→4→5 顺序执行，后一 Phase 依赖前一 Phase 的结果 |

---

## 验证方案

每个 Phase 完成后：

1. **Phase 1**：`python -m pytest src/test/unit/core/test_registry.py::TestSetSheetTitleWithOrder -v`
2. **Phase 1**：`python -m pytest src/test/unit/report/test_excel_generator.py::TestCreateSheets -v`
3. **Phase 2**：`python -m pytest src/test/unit/report/ -v`（确认所有写入器测试通过）
4. **Phase 3**：端到端生成报告 `python src/python/main.py` → 菜单 E → 检查 Excel 页签标题
5. **Phase 4**：`python scripts/test_runner.py --mode regression`（P0 门禁）
6. **最终**：`python scripts/test_runner.py --mode all`（P2 门禁）

### 端到端手动验证步骤

```
1. 修改 data/config/config.json，添加:
   "report_section_order": {
       "fund_performance": 1,
       "summary": 2,
       "market_value": 3
   }

2. 运行 python src/python/main.py
3. 菜单 E → 选择持仓 → 生成 Excel
4. 打开生成的 .xlsx：
   - 第 1 个页签标题应为 "1.基金业绩分析"
   - 第 2 个页签标题应为 "2.投资分析汇总"
   - 第 3 个页签标题应为 "3.市值核算明细表"
   - 后续未配置页签以默认序号按顺序续排

5. 恢复 config.json 删除 report_section_order
6. 重启 → 生成报告 → 标题恢复默认 1-16 序号
```

---

## Phase 依赖关系

```
Phase 1 (核心函数)
   │
   ▼
Phase 2 (移除冗余调用) ─── 需要 Phase 1 的 set_sheet_title 已就位
   │
   ▼
Phase 3 (Config 接入) ─── 独立于 Phase 2，可先发 PR review
   │
   ▼
Phase 4 (测试) ─── 覆盖 Phase 1-3 的全链路
   │
   ▼
Phase 5 (文档) ─── 最后更新
```

Phase 2 和 Phase 3 可以并行开发，但建议顺序执行减少冲突。Phase 4 和 Phase 5 必须在其他 Phase 完成后进行。
