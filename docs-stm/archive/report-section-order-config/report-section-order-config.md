# C 迭代：报告序号可配置 — 详细设计

> **状态**：✅ 已实现（v0.2.85~v0.2.86）— C-P1a/P1b/P2/P3 全 Phase 上线
> **注意**：本文档为 C 迭代完整设计，其中 C-P1b 部分（Excel 页签序号跟随用户配置）包含来自同名子设计文档的详细实现方案（已合并）
> **归档**：设计文档保留供回溯参考。实现详情见 `docs-stm/managements/changelog.md`。
>
> 本文档包含 C 迭代的完整设计过程、五轮审查发现、风险分析、技术债务记录和逐 Phase 实施方案。
>
> 管理层面摘要见 `docs-stm/managements/plan.md`。

---

## 需求分析

当前序号硬编码分散在代码中，导致两个问题：
- **序号跳跃**：HTML 中"五、基金业绩分析"→"十三、基金经理变更监控"→"六、新闻"，中间缺六~十二
- **顺序不可配**：用户无法调整模块前后顺序

覆盖的 16 个模块：

| 模块标识 | 默认序号 | 中文名 | 类型 |
|----------|----------|--------|------|
| `summary` | 1 | 投资分析汇总 | 始终显示 |
| `market_value` | 2 | 市值核算明细表 | 始终显示 |
| `category` | 3 | 持仓分类表 | 始终显示 |
| `penetration` | 4 | 资产穿透TOP10 | 始终显示 |
| `fund_performance` | 5 | 基金业绩分析 | 始终显示 |
| `fund_manager` | 6 | 基金经理变更监控 | B 系列（有数据才显示） |
| `fund_overlap` | 7 | 持仓重合度矩阵 | B 系列（有数据才显示） |
| `fund_concentration` | 8 | 持仓集中度监控 | B 系列（有数据才显示） |
| `fund_style` | 9 | 基金风格分析 | B 系列（有数据才显示） |
| `news_correlation` | 10 | 财经新闻热点与持仓关联分析 | 新闻（需启用） |
| `early_warning` | 11 | 智能预警 | 固定（需启用） |
| `global_macro` | 12 | 全球政经局势 | LLM |
| `expert_review` | 13 | 智囊团深度复盘 | LLM |
| `health_check` | 14 | 持仓体检报告 | LLM |
| `penetration_deep` | 15 | 穿透深度分析 | LLM |
| `llm_usage` | 16 | LLM API 用量 | LLM（**始终最后**） |

硬编码散布范围（27 处需要修改）：
- **HTML 模板**：16 处 `.section-title` + 11 处导航栏 `<a>` 硬编码中文+序号
- **Excel 页签**：11 个文件中独立的 `ws.title = f"X.{name}"` 调用
- **LLM 序号**：`llm_content.py` 的 `_get_module_key_map()` 硬编码起始序号 8

---

## 设计要点

1. **配置格式**：`config.json` 新增 `report_section_order: {"模块标识": 序号}`。用户配置的序号**同时作为显示序号和排序依据**。例如 `{"fund_manager": 1, "summary": 2, "fund_performance": 5}` → fund_manager 显示"1."（排第 1 位）、summary 显示"2."（排第 2 位）、fund_performance 显示"5."（排第 5 位）；未配置模块按默认顺序排在已配置模块之后，序号从 6 开始
2. `llm_usage` 不参与配置，强制最后一位
3. 未配置模块按默认顺序排在已配置模块之后
4. **统一 key 体系**：`registry.py` 中定义 `_REPORT_SECTION_DEFAULT` 为唯一权威 key 来源，提供 `get_report_section_keys()` 供配置校验
5. 引入 `set_sheet_title(ws, key)` 辅助函数统一设置页签名，11 个文件改法一致
6. `excel_generator.py` 引入 `_create_sheets(wb, section_order, ...)` 函数按序创建页签并返回 `{key: ws}` 字典（替代 `_SheetManager` class，避免过度抽象）
7. **LLM 页签**由 `excel_generator.py` **预先创建**后传入 `write_llm_sheets()`，`llm_content.py` 只写内容不创建页签（解决页签创建顺序与配置顺序不匹配的问题）
8. **HTML 采用"参数化序号"方案**（非"循环渲染"）：只替换模板中的硬编码数字，不重构模板结构。Python 端计算 `section_numbers` 字典传给 Jinja2
9. HTML 条件可见性通过 **Jinja2 宏**统一维护：定义一个 `section_visible(key, sv_dict)` 宏，导航栏和正文 14 个 `{% if %}` 都调用同一个宏
10. **不配置时 100% 保持现状**（回归安全）
11. HTML 正文 section 排序使用 **CSS `order` 属性**方案：.container 改为 flex 列布局，每个 section 加 `style="order: N;"`，实现视觉重排而不改变 DOM 结构和模板结构
12. **注册表加 `type` 字段统一可见性规则**：`_REPORT_SECTION_DEFAULT` 每项新增 `type` 字段（`always` / `b_series` / `news` / `llm`），`_should_create_sheet()` 和 `section_visible` 宏都基于 `type` 做通用判断，不再硬编码列举 key 列表。具体映射：
    - `always`（5 个）：summary, market_value, category, penetration, fund_performance
    - `b_series`（4 个）：fund_manager, fund_overlap, fund_concentration, fund_style
    - `news`（2 个）：news_correlation, early_warning
    - `llm`（5 个）：global_macro, expert_review, health_check, penetration_deep, llm_usage
    - 新增模块只需在注册表加一行 `type`，两套可见性规则自动继承。无需修改 `_should_create_sheet` 或 `section_visible` 宏。
13. **`section_visible_dict` 按 data_flag 自动生成**：注册表每项新增可选 `data_flag` 字段（如 `fund_manager` → `manager_data`），Python 端遍历注册表生成 `{key: bool}` 字典传给模板，宏只需 `sv_dict.get(key)`。新增模块只需在注册表标 `type` + `data_flag`，可见性规则自动继承，无需修改 Python 端 `section_visible_dict` 构造代码或模板宏。

---

## 审查过程与风险控制

### 第一轮审查发现的风险

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| HTML 模板循环渲染破坏可维护性 | 🔴高 | 采用参数化序号方案，不重构模板结构，只替换数字 |
| 11 个 sheet 文件 `ws.title` 写法各不同，遗漏修改 | 🟡中 | 统一使用 `set_sheet_title(ws, key)` 辅助函数，每个文件改法一致，grep 可验证无残留 |
| `excel_generator.py` 内部 `sheets["ws1"]`/`ws13` 硬编码索引需重构 | 🟡中 | 引入 `_SheetManager` 辅助类，内部函数通过 `sm.get(key)` 索引 |
| 与现有 `move_sheet` 冲突 | 🟢低 | C-P1b 中直接删除（按序创建即正确顺序） |
| 用户配置的序号与条件可见性交叉（B 系列无数据但序号已安排） | 🟢低 | 用户自行处理序号跳空，不自动补号 |

### 第二轮审查发现的新风险

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| `llm_content.py` 内部 `wb.create_sheet()` 追加到末尾，与配置排序不兼容 | 🟡中 | 改为由 `excel_generator.py` **在流程开始时**按序预先创建所有 LLM 页签 |
| `excel_generator.py` 中页签创建、数据计算、内容写入三个步骤耦合 | 🟡中 | `_SheetManager` 在流程开始时按序预创建所有页签；各 `_write_*` 函数通过 `sm.get(key)` 获取 |
| 模块标识 key 在注册表和报告模块中不统一 | 🟡中 | `registry.py` 定义唯一权威 key；`_validate_report_section_order()` 校验 |
| C-P3 正文循环渲染破坏 14 种不同 section 结构 | 🟡中 | **C-P3 降级为只改导航栏**。正文保持固定位置不动 |

### 第三轮审查发现的风险

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| `_SheetManager` 预创建 LLM 页签导致禁用模块出现空页签 | 🟡中 | 采用 Option A：预创建+写入占位符（与 HTML 端一致） |
| 模板 `{% if news_enabled %}` 死代码 | 🟢低 | C-P2 顺手修复：改为 `{% if news_data %}` 或直接删除 |
| `llm_usage` 页签由 `summary.py` 创建，易被遗漏 | 🟢低 | C-P1b 的 `_SheetManager` 覆盖全部 16 个模块 |

### 第四轮审查发现的风险

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| HTML 正文 14 个 section 结构完全不同，循环渲染不可行 | 🟡中 | **C-P3 改为只改导航栏**。读者通过导航栏跳转阅读，正文保持不动 |

### 第五轮审查发现的风险与技术债务

| # | 问题 | 性质 | 缓解措施 |
|---|------|------|----------|
| 1 | C-P3 仅改导航栏不够：正文仍在页面末尾，阅读仍按旧顺序 | ❓设计缺陷 | 改用 CSS `order` 方案 |
| 2 | 导航栏可见性条件与正文 `{% if %}` 重复 | 🟡技术债务(A) | 用 Jinja2 宏统一 |
| 3 | `_SheetManager` class 封装开销 > 价值 | 🟡技术债务(B) | 降级为 `_create_sheets()` 函数 |
| 4 | C-P2 和 C-P3 在同一文件，分开实施增加开销 | 🟢优化 | 合并为 C-P2"HTML 全链路" |
| 5 | 配置序号语义未明确 | 🟢文档 | 设计要点 #1 已补充说明 |
| 6 | **(D)** `_should_create_sheet` 和 `section_visible` 两套独立规则 | 🟡风险 | 注册表加 `type` 字段，两侧都基于 `type` 判断 |
| 7 | **(E)** 模块 key 散落在 5 个消费点 | 🟡风险 | 注册表是唯一枚举 key 的地方，其余消费点只看 `type` |

---

## Phase 划分

全 Phase 概览（按递增复杂度排列）：

| Phase | 代码 | 文件数 | 风险 | 对外可见变更 | 能否独立回退 |
|-------|------|--------|------|-------------|-------------|
| C-P1a 🔧 基础层 | `registry.py` + `config.py` + 测试 | 4 | 🟢低 | 无（纯新增，无人调用） | 可单独回退 |
| C-P1b 🏗️ Excel 全链路 | `excel_generator.py` + 11 sheet 文件 + `llm_content.py` + `summary.py` | 14 | 🟡中 | Excel 页签支持配置序号 | 依赖 C-P1a |
| C-P2 🖌️ HTML 全链路 | `html_writer.py` + `report_template.html` | 3 | 🟢低 | HTML 序号+排序来自配置 | 可单独回退到 C-P1b |
| C-P3 📖 文档验证 | `how-to-config.md` + `plan.md` | 2 | 🟢低 | 无代码变更 | — |

---

### C-P1a 🔧 基础层（4 文件，纯新增，无行为变更）

**目标**：完成注册表、配置、辅助函数的基础代码，不改变任何已有行为。

**改动文件**：

| 文件 | 改动内容 | 是否影响现有行为 |
|------|----------|------------------|
| `registry.py` | 新增 `_REPORT_SECTION_DEFAULT` 顺序定义（16 项完整列表，每项含 `key`/`name`/`number`/`type`/`data_flag` 字段）；`type`（`always`/`b_series`/`news`/`llm`）供 Excel `_should_create_sheet()` 和 HTML `section_visible()` 宏共同消费；`data_flag` 标记 HTML 端检查的 `raw_data_flags` 字典键名；新增 `get_report_section_order(config)`（合并配置+默认+llm_usage 置尾）；新增 `set_sheet_title(ws, key)`；新增 `get_report_section_keys()` | ❌ 纯新增 |
| `config.py` | `validate_config()` 中新增 `_validate_report_section_order()` 校验（重复序号警告、未知标识警告、负值/非整数警告） | ❌ 纯新增 |
| `config.json` | 可选新增 `report_section_order` 配置 | ❌ 可选新增 |
| `test_registry.py` | 新增 `TestReportSectionOrder`（6+ 场景） | — |
| `test_config.py` | 新增 `test_validate_report_section_order_*`（4+ 场景） | — |

**验收条件**：
- ✅ `get_report_section_order()` 无配置时返回完整 16 项默认顺序，序号与当前硬编码一致
- ✅ 配置 `{"fund_manager": 1, "summary": 2}` → 返回 [fund_manager(1), summary(2), ...其他按默认排序...]
- ✅ `llm_usage` 永远是最后一位（无论配置怎么配）
- ✅ 重复序号、非整数、负值、未知标识 → WARNING，不崩溃
- ✅ `set_sheet_title(ws, "category")` 设置页签名为 `"3.持仓分类表"`
- ✅ 回归测试全部通过

---

### C-P1b 🏗️ Excel 全链路（基于 C-P1a，14 文件改动）

**目标**：Excel 报告全链路支持配置序号。

> **顺手清理（分两 phase 执行）**：
> - **C-P1b 负责**：`excel_generator.py` 内 `fund_deep` → `enable_b_series`（_write_fund_deep_sheets 签名、create_sheets 签名、write_html_report 调用处）；删除 `wb.move_sheet(ws13–ws16)` 后置逻辑；**同时删除 `summary.py` 中 `_init_llm_usage_sheet()` 的 `wb.move_sheet(title, offset=...)`**（新 `_create_sheets` 已按序创建，llm_usage 固定末尾，move_sheet 成为死操作）
> - **C-P2 负责**：`html_writer.py` 内 `fund_deep` → `enable_b_series`（函数签名 4 处 + 调用 4 处）
> - **验收门禁**：C-P2 完成后 `grep -rn "fund_deep" src/python/report/` 应返回 0 条

**改动文件**：

| 文件 | 改动内容 |
|------|----------|
| `excel_generator.py` | 引入 `_create_sheets(wb, section_order, ...)` 函数按序预创建页签，返回 `{key: ws}` 字典；内部函数通过 `sheets.get(key)` 索引；删除 `wb.move_sheet(ws13–ws16)` 后置逻辑；删除 `_write_fund_deep_sheets` 中的 `fund_deep` → `enable_b_series`；将预创建的 LLM ws 列表传入 `write_llm_sheets()` |
| 11 个 sheet 文件 | `ws.title = f"X.{name}"` → `set_sheet_title(ws, "模块标识")` 一行改动 |
| `llm_content.py` | `write_llm_sheets()` 接收预创建的 `ws_list` 参数，不再调用 `wb.create_sheet()`；`_get_module_key_map()` 从 `get_report_section_order()` 读取，删除硬编码 `idx = 8` |
| `summary.py` | `_init_llm_usage_sheet()` 使用配置序号，不再硬编码标题；**删除 `wb.move_sheet(title, offset=...)`**（新设计下 llm_usage 页签已在末尾） |

**关键设计 —— `_create_sheets()` 函数**（基于注册表 `type` 字段，不再硬编码 key 列表）：

```python
# ── 类型驱动的可见性判断（唯一规则源，HTML 端也使用同一逻辑）──
def _should_create_sheet(sec: dict, enable_b_series: bool, include_news: bool, include_llm: bool) -> bool:
    """按 sec.type 判断是否创建页签。新增模块只需在注册表标 type，无需改此函数。"""
    type_map = {
        "always":    True,                       # summary, market_value, category, penetration, fund_performance
        "b_series":  enable_b_series,            # fund_manager, fund_overlap, fund_concentration, fund_style
        "news":      include_news,               # news_correlation, early_warning
        "llm":       include_llm,                # global_macro, expert_review, health_check, penetration_deep, llm_usage
    }
    return type_map.get(sec.get("type", ""), False)

def _create_sheets(wb, section_order, enable_b_series=False, include_news=False, include_llm=False) -> dict[str, Any]:
    """按配置顺序创建所有页签，返回 {key: ws} 字典。"""
    sheets: dict[str, Any] = {}
    for sec in section_order:
        if not _should_create_sheet(sec, enable_b_series, include_news, include_llm):
            continue
        ws = wb.create_sheet()
        set_sheet_title(ws, sec["key"])
        sheets[sec["key"]] = ws
    return sheets
```

> 此方案消除了技术债务 (D)：**零重复**——新增模块只需在注册表加一行并指定 `type`，`_should_create_sheet` 和 HTML `section_visible` 宏自动继承，不用两处改。同时消除了 (E)：模块 key 不再散落在 5 个消费点，注册表是唯一枚举 key 的地方。

> **LLM 禁用模块处理**：采用 Option A——`_create_sheets` 预创建所有 LLM 页签（含禁用的），禁用模块由 `write_llm_sheets()` 写入占位符文本。

**验收条件**：
- ✅ Excel 所有页签名 = `"{序号}.{中文名}"`，与配置一致
- ✅ B 系列不使用 `move_sheet`，创建即正确位置
- ✅ llm_usage 页签始终在最后
- ✅ LLM 页签按配置序号出现在正确位置（而非全部追加末尾）
- ✅ 不配置时顺序与 C-P1a 之前完全一致（回归）
- ✅ `excel_generator.py` 中无 `wb.move_sheet(ws13` 调用（已删除）
- ✅ `summary.py` 中无 `wb.move_sheet` 调用（已删除）
- ✅ 回归测试全部通过（全量 2244 项）

### C-P1b 详细实现方案

#### 问题根因

`set_sheet_title()`（`registry.py:351`）始终只查 `_REPORT_SECTION_DEFAULT` 取 number，不接收 `section_order` 参数。调用链路有三层：

1. `_create_sheets()`（`excel_generator.py:550`）→ `set_sheet_title(ws, sec["key"])` — 应传序号的源头
2. 11 个独立 sheet 写入器各自调用 `set_sheet_title(ws, "<key>")` — 覆盖了 `_create_sheets` 的设置
3. `generate_excel_report()` / `generate_html_report()` 内部调 `get_report_section_order()` **不带 config** → 即使序号跟随了自定义顺序，也用的是默认序号

#### 改动范围

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

#### Phase 拆分

**Phase 1：`set_sheet_title` 核心改造 + `_create_sheets` 传参**

改动：
1. `registry.py` — `set_sheet_title(ws, key, section_order=None)`
   - 当 `section_order` 不为 None 时，遍历 `section_order` 匹配 key，取 `sec["number"]`
   - 当 `section_order` 为 None 时，保持现有行为（查 `_REPORT_SECTION_DEFAULT`）
2. `excel_generator.py` — `_create_sheets()` 中 `set_sheet_title(ws, sec["key"])` → `set_sheet_title(ws, sec["key"], section_order)`

**Phase 2：移除 11 个写入器的冗余 `set_sheet_title` 调用**

| 文件 | 删除行内容 |
|:-----|:-----------|
| `summary.py:254` | `set_sheet_title(ws, "summary")` |
| `market_value.py:592` | `set_sheet_title(ws, "market_value")` |
| `category.py:175` | `set_sheet_title(ws, "category")` |
| `penetration_sheet.py:127` | `set_sheet_title(ws, "penetration")` |
| `fund_performance.py:362` | `set_sheet_title(ws, "fund_performance")` |
| `fund_manager_sheet.py:65` | `set_sheet_title(ws, "fund_manager")` |
| `fund_overlap_sheet.py:77` | `set_sheet_title(ws, "fund_overlap")` |
| `fund_concentration_sheet.py:85` | `set_sheet_title(ws, "fund_concentration")` |
| `fund_style_sheet.py:66` | `set_sheet_title(ws, "fund_style")` |
| `news_correlation.py:509` | `set_sheet_title(ws, "news_correlation")` |
| `early_warning.py:309` | `set_sheet_title(ws, "early_warning")` |

**Phase 3：Config 接入 — 将 `section_order` 传入报告生成链路**

1. `excel_generator.py:generate_excel_report()` — 新增可选参数 `section_order: list[dict] \| None = None`
2. `html_writer.py:write_html_report()` — 新增可选参数 `section_order: list[dict] \| None = None`
3. `handlers_report.py` — 各 `_cmd_*` 函数读取 config，调用 `get_report_section_order(config)` 传入

**Phase 4：新增测试**

| 文件 | 类/方法 | 覆盖内容 |
|:-----|:--------|:---------|
| `test_registry.py` | `TestSetSheetTitleWithOrder` | 自定义 section_order → 标题使用正确序号 |
| `test_registry.py` | 同上 | 部分自定义 → 未配置项使用默认序号 |
| `test_registry.py` | 同上 | 传入 None（向后兼容）→ 使用默认序号 |
| `test_excel_generator.py` | `TestCreateSheets` | 按自定义顺序创建 sheet、标题正确 |
| `test_excel_generator.py` | 同上 | 可见性过滤 + 标题断言 |
| `test_scenario_section_order.py` | `test_custom_order_excel_titles` | 端到端：Excel 页签标题跟随配置 |
| `test_scenario_section_order.py` | `test_custom_order_html_titles` | 端到端：HTML 标题正确 |

**Phase 5：文档更新**（plan.md / technical.md / changelog.md / reports-instruction.md）

#### 风险与缓解

| 风险 | 等级 | 缓解 |
|:-----|:----:|:-----|
| 移除写入器 `set_sheet_title` 后，某未发现的直接调用路径中断 | 中 | Phase 2 后立即运行全量测试 + 真人验证生成一份完整报告 |
| Config 在 `handlers_report.py` 中不可达 | 低 | 已有 `get_config_cache()` 模式 |
| 与用户配置的 `llm_usage` 强制末位冲突 | 低 | `get_report_section_order` 已有处理逻辑 |

#### Phase 依赖关系

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

#### 端到端手动验证步骤

```
1. 修改 data/config/config.json，添加:
   "report_section_order": {
       "fund_performance": 1,
       "summary": 2,
       "market_value": 3
   }

2. 运行 main.py → 菜单 E → 生成 Excel
3. 打开 .xlsx：第 1 个页签 "1.基金业绩分析"、第 2 个 "2.投资分析汇总"、第 3 个 "3.市值核算明细表"
4. 恢复 config.json 删除 report_section_order → 重启 → 标题恢复默认 1-16
```

---

### C-P2 🖌️ HTML 全链路（3 文件，低风险，解决跳号 + 排序 + 统一可见性）

**目标**：一次性完成 HTML 报告的所有序号和排序改造。

**为什么合并原 C-P2 + C-P3**：原 C-P2（替换 25 处序号）和 C-P3（改导航栏）都在同一文件 `report_template.html`，分开实施增加 commit 和测试开销。各风险 🟢低，合并后用一 commit 交付，回退也只用 revert 一次。

> **顺手清理（接 C-P1b）**：`html_writer.py` 内 `fund_deep` → `enable_b_series`（函数签名 4 处 + 调用 4 处）。C-P2 完成后 `grep -rn "fund_deep" src/python/report/` 应返回 0 条。

**方案（4 个子步骤，按执行顺序）**：

1. **赋值**：`html_writer.py` 计算 `section_numbers`、`section_order`、`section_visible_dict`，传给模板
2. **替换序号**：模板中全部 25 处硬编码数字替换为 `{{ section_numbers["key"] }}`
3. **CSS order 视觉排序**：每个 `.section` 容器加 `style="order: N;"`，`.container` 改为 `display: flex; flex-direction: column;`
4. **Jinja2 宏统一可见性**：宏定义基于 `sec_type` + `data_flag` 做通用判断，导航栏和正文都调用同一个宏

```python
# html_writer.py — 在 render 时计算
section_order = get_report_section_order()                    # 排序列表（含 type/data_flag）
section_numbers = {sec["key"]: sec["number"] for sec in section_order}  # 序号字典

# 数据标记字典（按需计算，不硬编码 key 列表）
raw_data_flags = {
    "manager_data": bool(manager_analysis and manager_analysis.get("results")),
    "overlap_data": bool(overlap_matrix and overlap_matrix.get("funds") and overlap_matrix["funds"]|length >= 2),
    "concentration_data": bool(concentration_analysis and concentration_analysis.get("results")),
    "style_data": bool(style_analysis and style_analysis.get("results")),
    "include_news": include_news,
    "early_warnings": bool(early_warnings),
    "llm_enabled": llm_enabled_flag,
}

# 按注册表 type + data_flag 映射每章的可见性（单一规则源，零重复）
section_visible_dict = {}
for sec in section_order:
    flag_name = sec.get("data_flag")
    if not flag_name:
        section_visible_dict[sec["key"]] = True   # always 类型
    else:
        section_visible_dict[sec["key"]] = raw_data_flags.get(flag_name, False)

# 注册 Jinja2 全局变量
_ENV.globals["section_order"] = section_order
_ENV.globals["section_numbers"] = section_numbers
_ENV.globals["section_visible_dict"] = section_visible_dict

html = _ENV.get_template("report_template.html").render(...)
```

```html
{# report_template.html — 宏定义（放在模板顶部，基于 sec_type，无硬编码 key） #}
{%- macro section_visible(key, sv_dict) -%}
{{- sv_dict.get(key, False) -}}
{%- endmacro -%}

{# 导航栏 — 按 section_order 循环 #}
<nav class="section-nav">
{% for sec in section_order %}
  {% if section_visible(sec.key, section_visible_dict) %}
  <a href="#sec-{{ sec.key }}">{{ sec.number }}、{{ sec.name }}</a>
  {% endif %}
{% endfor %}
</nav>

{# CSS order — .container 改为 flex 列布局 #}
<style>
  .container { display: flex; flex-direction: column; }
</style>

{# 正文 section（保持固定位置，只加 style="order" + 宏调用） #}
{% if section_visible("summary", section_visible_dict) %}
<div id="sec-summary"></div>
<div class="section" style="order: {{ section_numbers['summary'] }};">
    <div class="section-title">{{ section_numbers["summary"] }}、投资分析汇总</div>
    <!-- 内容不变 -->
</div>
{% endif %}

<!-- 其余 13 个 section 同理 -->
```

**改动文件**：
- `html_writer.py`：计算 `section_numbers`/`section_order`/`data_flags`；注册宏全局变量；`fund_deep` → `enable_b_series`（函数签名 4 处 + 调用 4 处）
- `report_template.html`：宏定义；27 处硬编码数字替换（16 处 section-title + 11 处导航栏，导航栏改为 `{% for sec in section_order %}` 循环后自动消除全部 11 处）；14 处 `style="order"`；14 处 `{% if %}` → 宏调用

**验收条件**：
- ✅ 所有章节标题 = `"数字、中文名"`，序号正确
- ✅ 正文按 order 属性顺序显示（导航栏跳转顺序 = 视觉顺序 = 配置顺序）
- ✅ 导航栏顺序正确，无数据的模块不显示
- ✅ Jinja2 宏在导航栏和正文中都返回正确结果
- ✅ 不配置时顺序与 C-P1b 完全一致（回归）
- ✅ `grep -rn "fund_deep" src/python/report/` 返回 0 条（两端重命名完成无残留）

---

### C-P3 📖 文档 + 集成验证

**改动文件**：
- `docs-stm/manuals/how-to-config.md`：新增 `report_section_order` 配置说明
- `plan.md`：标记 C 迭代完成

**验收条件**：
- ✅ 实际生成一份完整 Excel + HTML 报告，检查所有序号
- ✅ 场景覆盖：不配置（默认顺序）、配置完整、部分配置、LLM 禁用时无 LLM 章节
- ✅ how-to-config.md 有 report_section_order 说明

---

## 遗留技术债务

| 编号 | 问题 | 影响 | 处理策略 |
|------|------|------|----------|
| **(B)** | CSS order 方案下 DOM 顺序 ≠ 视觉顺序，Tab 键/打印顺序偏离视觉 | 🟢低（报告为纯阅读，非交互应用） | 记录，不处理。如需修复需改为服务器端重排 |
| **(C)** | 11 个 sheet 文件的页签命名权从子模块上提到 `excel_generator.py`，子模块失去"自包含"能力 | 🟢低（有意为之） | 日志审计：`set_sheet_title()` 内部加 `logger.debug`，运行时确认全部被调用 |
| **(F)** | `fund_deep` 参数名语义模糊——它控制"B 系列模块是否启用"，名称像"深度分析" | 🟢 **已解决** — C-P1b 改 `excel_generator.py`，C-P2 改 `html_writer.py`，验收门禁 `grep -rn "fund_deep"` 应返回 0 |
| **(G)** | `raw_data_flags` 字典中的 `include_news` 和 `early_warnings` 值含义接近但不等价（`include_news` 是配置开关，`early_warnings` 是实际数据），`news` 类型的 `data_flag` 分别指向两者 | 🟢低（当前无歧义） | 保持现状。如果后续新增新闻类模块，需确认应使用哪个 flag |
