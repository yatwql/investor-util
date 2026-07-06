# C-P1b 迭代计划：Excel 页签编号跟随用户 `report_section_order` 配置

> **状态**：✅ 已实现（v0.2.86）
> **归档**：设计文档保留供回溯参考。实现详情见 `docs-stm/managements/changelog.md`。
>
> **版本**：v0.2.86
> **创建日期**：2026-07-05
> **审查日期**：2026-07-05（第 3 轮复盘 — 调用链全覆盖核查 + 测试影响面逐文件验证）
> **关联文档**：[c-iteration-design.md](c-iteration-design.md)、`docs-stm/managements/plan.md`（§C-P1b）

---

## 问题

C 迭代（v0.2.85）实现了报告页签序号可配置功能：

- ✅ HTML 报告序号（导航栏、章节标题）跟随用户配置
- ✅ Excel 页签**物理顺序**跟随用户配置
- ❌ **Excel 页签标题中的数字**始终显示默认序号（1-16），不跟随用户配置
- ❌ **LLM 页签内部标题行文本**始终显示默认序号（12-15），不跟随用户配置

## 根因分析

两处独立缺陷，同源但独立：

**缺陷 A — 页签标题（表层）**：`set_sheet_title()`（`registry.py:351`）始终只查 `_REPORT_SECTION_DEFAULT` 取 number，不接收 `section_order` 参数。调用链路有三层：

1. `_create_sheets()`（`excel_generator.py:550`）→ `set_sheet_title(ws, sec["key"])` — 应传序号的源头
2. 11 个独立 sheet 写入器各自调用 `set_sheet_title(ws, "<key>")` — **覆盖**了 `_create_sheets` 的设置
3. `generate_excel_report()` / `write_html_report()` 内部调 `get_report_section_order()` **不带 config** → 即使有配置也不生效

**缺陷 B — LLM 页签内部标题行（深层）**：`_get_module_key_map()`（`llm_content.py:102-115`）有两层问题：
1. 调用 `get_report_section_order()` 不带 config → 永远返回默认序号 12-15
2. 模块级缓存 `_MODULE_KEY_MAP` 一次填充后永不过期，后续调用直接命中旧值

```python
# llm_content.py:100
_MODULE_KEY_MAP: dict[str, str] = {}  # ← 模块级缓存，永不失效

def _get_module_key_map():
    if _MODULE_KEY_MAP:
        return _MODULE_KEY_MAP        # ← 第二次调用直接返回缓存
    for sec in get_report_section_order():  # ← 不带 config
        title = f"{sec['number']}.{sec['name']}"  # 永远 12.全球/13.智囊/14.持仓/15.穿透
        _MODULE_KEY_MAP[title] = mk
```

## 范围

### 生产 `set_sheet_title` 调用者（共 12 处生产代码）

| 路径 | 文件:行 | 类型 | 处理方式 |
|:-----|:-------|:----|:---------|
| `_create_sheets()` | `excel_generator.py:550` | 核心创建 | 改为传 `section_order` |
| `write_summary_sheet()` | `summary.py:254` | 冗余 | 删除 |
| `write_market_value_sheet()` | `market_value.py:592` | 冗余 | 删除 |
| `write_category_sheet()` | `category.py:175` | 冗余 | 删除 |
| `write_penetration_sheet()` | `penetration_sheet.py:127` | 冗余 | 删除 |
| `write_fund_performance_sheet()` | `fund_performance.py:362` | 冗余 | 删除 |
| `write_fund_manager_sheet()` | `fund_manager_sheet.py:65` | 冗余 | 删除 |
| `write_fund_overlap_sheet()` | `fund_overlap_sheet.py:77` | 冗余 | 删除 |
| `write_fund_concentration_sheet()` | `fund_concentration_sheet.py:85` | 冗余 | 删除 |
| `write_fund_style_sheet()` | `fund_style_sheet.py:66` | 冗余 | 删除 |
| `write_news_sheet()` | `news_correlation.py:509` | 冗余 | 删除 |
| `write_early_warning_sheet()` | `early_warning.py:309` | 冗余 | 删除 |

### 生产 `get_report_section_order()` 调用者（共 3 处）

| 路径 | 文件:行 | 当前问题 | 修复方式 |
|:-----|:-------|:---------|:---------|
| `_get_module_key_map()` | `llm_content.py:110` | 不带 config → 永远 12-15 | 改为接收 `section_order` 参数 |
| `write_html_report()` | `html_writer.py:233` | 不带 config → 永远 1-16 | 新增可选 `section_order` 参数 |
| `generate_excel_report()` | `excel_generator.py:601` | 不带 config → 永远 1-16 | 新增可选 `section_order` 参数 |

### 生产 `write_llm_sheets()` 调用者（共 1 处）

| 路径 | 文件:行 | 当前问题 | 修复方式 |
|:-----|:-------|:---------|:---------|
| `_write_llm_section_and_usage()` | `excel_generator.py:428` | 不传 `section_order` | 改为传入 |

### 生产 `_get_module_key_map()` 调用者（共 2 处，均在 `llm_content.py` 内）

| 路径 | 行 | 当前问题 | 修复方式 |
|:-----|:--:|:---------|:---------|
| `_get_placeholder()` | 128 | 使用默认标题查占位符 | 接收 `section_order` 参数 |
| `write_llm_sheets()` | 216 | 使用默认标题建逆向映射 | 接收 `section_order` → 传参 |

### 生产 `_get_placeholder()` 调用者（共 1 处，在 `llm_content.py` 内）

| 路径 | 行 | 当前问题 | 修复方式 |
|:-----|:--:|:---------|:---------|
| `_write_content_sheet()` | 188 | 使用默认标题查占位符 | 接收 `section_order` 参数 |

### 生产 `_write_content_sheet()` 调用者（共 1 处，在 `llm_content.py` 内）

| 路径 | 行 | 当前问题 | 修复方式 |
|:-----|:--:|:---------|:---------|
| `write_llm_sheets()` | 240 | 不传 `section_order` | 改为传入 |

### 测试文件影响

| 文件 | 影响 | 说明 |
|:-----|:-----|:-----|
| `test_registry.py:330-349` | **不受影响** | 测 `set_sheet_title` 函数本身，使用默认值 |
| `test_registry.py:353-445` | **不受影响** | 测 `get_report_section_order`，该函数未改动 |
| `test_registry_edge.py` | **不受影响** | 8 个 edge 测试，全针对 `get_report_section_order` |
| `test_summary.py:688` | **需修改** | 移除冗余后写入器不设标题 → fixture 预设标题 |
| `test_market_value.py:1391` | **需修改** | 同上 |
| `test_early_warning.py:288,302` | **需修改** | 同上（2 处） |
| `test_llm_content.py:202,253,281` | **不受影响** | 预创建 sheet 时已设标题，写入器不修改标题 |
| `test_llm_content.py:110,398,414,428,446` | **不受影响** | `_write_content_sheet` 直接调用使用默认 `section_order=None` |
| `test_html_writer.py` | **不受影响** | HTML 模板测试，不涉及 Excel title |
| `test_scenario_section_order.py:77-78` | **不受影响** | 场景测试直接测 `set_sheet_title()` |
| `test_excel_generator.py`（全部） | **不受影响** | mock 结构使用默认参数，新增参数默认 None |
| `test_integration_coverage.py:343` | **不受影响** | 使用默认参数 |
| `test_integration.py`（全部 4 处） | **不受影响** | 同上 |

---

## 收益评估

| 收益 | 维度 | 量级 | 说明 |
|:-----|:------|:----:|:------|
| 用户可见修复 | 用户 | ★★★ | Excel 页签标题数字 + LLM 内容标题行数字跟随 config.json 配置 |
| 架构清理 | 开发 | ★★☆ | 移除 11 处职责错配的冗余调用，职责统一到 `_create_sheets` |
| 正确性修复 | 开发 | ★★★ | 修复 `_MODULE_KEY_MAP` 模块级缓存永不过期 bug |
| 测试资产 | 开发 | ★★★ | 新增 ~10 个 config-aware 测试用例，覆盖自定义顺序路径 |
| 技术债务清偿 | 开发 | ★★☆ | 清偿 3 项遗留债务 |
| 文档收益 | 团队 | ★☆☆ | changelog 和 technical.md 更新，plan.md 标记完成 |

---

## Phase 划分

### Phase 1：核心改造 + 移除冗余 + 单元测试同步

**目标**：
1. `set_sheet_title` 能接收 `section_order`
2. `_create_sheets` 传参
3. 写入器不再覆盖标题
4. **同步编写单元测试验证**

**背景**：经确认，11 个写入器的 `ws` 均来自 `_create_sheets()` 创建后传入，**无任何生产代码路径绕过 `_create_sheets`**。移除冗余调用不存在隐藏依赖风险。

**改动 A — `registry.py`**：`set_sheet_title(ws, key, section_order=None)`
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

**改动 B — `excel_generator.py`**：`_create_sheets()` 传参
```python
set_sheet_title(ws, sec["key"], section_order)
```

**改动 C — 移除 11 个写入器的冗余 `set_sheet_title` 调用**（每个文件删 1 行）：

| 写入器文件 | 行 | 删除 |
|:-----------|:--:|:-----|
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

**同步修改测试**（4 处 `ws.title` 断言改为由 fixture 预设标题）：

| 文件 | 行 | 原断言 |
|:-----|:---|:-------|
| `test_summary.py` | 688 | `self.assertEqual(self.ws.title, "1.投资分析汇总")` |
| `test_market_value.py` | 1391 | `self.assertEqual(ws.title, "2.市值核算明细表")` |
| `test_early_warning.py` | 288 | `assert ws.title == "11.智能预警"` |
| `test_early_warning.py` | 302 | `assert ws.title == "11.智能预警"` |

改为：在测试 `setUp` 中由 fixture 预设 `ws.title`，写入器不再设标题后该值保持 fixture 预设。

**同步新增测试（随代码一起提交，使用 `@pytest.mark.unit_core` / `@pytest.mark.unit_report`）**：

| 测试文件 | 测试内容 | 项数 | Marker |
|:---------|:---------|:----:|:-------|
| `test_registry.py` | `TestSetSheetTitleWithOrder`：自定义顺序 → 标题使用正确序号 | 1 | `unit_core` |
| `test_registry.py` | `TestSetSheetTitleWithOrder`：部分自定义 → 未配置项使用默认序号 | 1 | `unit_core` |
| `test_registry.py` | `TestSetSheetTitleWithOrder`：传入 None → 向后兼容默认行为 | 1 | `unit_core` |
| `test_excel_generator.py` | `TestCreateSheets`：默认顺序 → 标题正确 | 1 | `unit_report` |
| `test_excel_generator.py` | `TestCreateSheets`：自定义顺序 → 标题正确 | 1 | `unit_report` |
| `test_excel_generator.py` | `TestCreateSheets`：可见性过滤 → 筛选正确 | 1 | `unit_report` |

**可回退**：签名向后兼容（`section_order=None` 默认），删除行可 `git revert` 恢复。
**风险**：**低**（确认无生产路径绕过 `_create_sheets`，已有 grep 证据）
**Checkpoint**：
```bash
python -m pytest src/test/unit/core/test_registry.py -v -k "TestSetSheetTitleWithOrder"
python -m pytest src/test/unit/report/test_excel_generator.py -v -k "TestCreateSheets"
```

---

### Phase 2：Config 接入 + `_get_module_key_map()` 修复 + 验证测试

**目标**：
1. 用户的 `report_section_order` 配置通过完整链路生效
2. 修复 `_get_module_key_map()` 模块级缓存不过期缺陷
3. 注入自定义 section_order 验证产出

**改动 A — `excel_generator.py`**：`generate_excel_report()` 新增参数 + 内部传参

⚠️ **变量名注意事项**：当前代码 `generate_excel_report()` 内部第 601 行有 `section_order = get_report_section_order()`。若新增同名参数，该行会影子覆盖(overshadow)参数值。因此内部名称必须改为如 `order` 或 `resolved_order`，而 `section_order` 保留为参数名。

```python
def generate_excel_report(..., section_order: list[dict] | None = None):
    ...
    order = section_order or get_report_section_order()   # ← 内部名 order，非 section_order
    sheets = _create_sheets(wb, order, ...)
    ...
    _write_llm_section_and_usage(sheets, include_llm, llm_content, prog, section_order=order)
```

`handlers_report.py` 中 `_generate_excel_report()` 委托函数使用 `**kwargs`，`section_order=sec_order` 会自动透传，无需修改委托函数。

**改动 B — `html_writer.py`**：`write_html_report()` 新增参数

```python
def write_html_report(..., section_order: list[dict] | None = None):
    ...
    order = section_order or get_report_section_order()
    section_numbers = {sec["key"]: sec["number"] for sec in order}
```
上述 `section_numbers` 替换现有第 233-234 行。现有 `section_visible_dict` 构建逻辑（行 246-251）遍历 `section_order`，自定义顺序天然生效。

**改动 C — `handlers_report.py`**：各 `_cmd_*` 函数接入配置

```python
config = get_config_cache() or {}
sec_order = get_report_section_order(config)
```

需要修改的 4 个函数及其调用点：

| 函数 | 位置 | 传递路径 |
|:-----|:-----|:---------|
| `_cmd_generate_excel()` | 行 39-41 | `_generate_excel_report(holdings, ..., section_order=sec_order)` |
| `_cmd_generate_html()` | 行 61-64 | `write_html_report(..., section_order=sec_order)` |
| `_cmd_generate_both()` | 行 97 + 110-113 | 两个函数都传 |
| `_cmd_generate_full()` | 行 325 + 340-341 | 两个函数都传 |

**改动 D — `llm_content.py`**：修复 `_get_module_key_map()` 缺陷（技术债务清偿）

完整调用链透传（由外到内）— 所有 4 个被调用函数新增 `section_order` 可选参数：

```
generate_excel_report(excel_generator.py)
  └─ _write_llm_section_and_usage(sheets, ..., section_order)
       └─ write_llm_sheets(sheets, llm_content, section_order)    ← 新增 section_order 参数
            ├─ _get_module_key_map(section_order)                  ← 原 _MODULE_KEY_MAP 缓存移除
            │   return {f"{sec['number']}.{sec['name']}": sec["key"] for sec in order}
            └─ _write_content_sheet(ws, title, content, section_order)  ← 新增 section_order
                 └─ if content is None:
                        _get_placeholder(title, section_order)      ← 新增 section_order
                         └─ _get_module_key_map(section_order).get(title) ← 确保占位符查找正确
```

**4 个函数全在 `llm_content.py` 内闭环**，无外部调用者，重构安全。

```python
# 移除模块级缓存 _MODULE_KEY_MAP（14 项迭代无需缓存）

def _get_module_key_map(section_order: list[dict] | None = None) -> dict[str, str]:
    result = {}
    order = section_order or get_report_section_order()
    for sec in order:
        mk = sec["key"]
        if mk != "news_correlation" and mk != "llm_usage":
            title = f"{sec['number']}.{sec['name']}"
            result[title] = mk
    return result

def _get_placeholder(title: str, section_order: list[dict] | None = None) -> str:
    mk = _get_module_key_map(section_order).get(title)
    ...

def _write_content_sheet(ws, title, content, section_order: list[dict] | None = None):
    if content is None:
        placeholder = _get_placeholder(title, section_order)
    ...

def write_llm_sheets(sheets, llm_content, section_order: list[dict] | None = None):
    _reverse = {v: k for k, v in _get_module_key_map(section_order).items()}
    ...
    _write_content_sheet(ws, title, content, section_order)
```

`test_llm_content.py` 现有 5 处 `_write_content_sheet` 直接调用和 4 处 `write_llm_sheets` 调用均不传入 `section_order`（默认 None），向后兼容，无需修改。

**改动 E — 同步新增测试（随代码一起提交）**：

| 测试文件 | 测试内容 | 项数 | Marker |
|:---------|:---------|:----:|:-------|
| `test_excel_generator.py` | 注入自定义 `section_order` → sheet 标题验证 | 1 | `unit_report` |
| `test_llm_content.py` | `_get_module_key_map` 传入自定义 section_order → 标题正确 | 2 | `unit_llm` |
| `test_llm_content.py` | `write_llm_sheets` 传入自定义 section_order → 内部标题行正确 | 1 | `unit_llm` |
| `test_excel_generator.py` | `_write_llm_section_and_usage` 透传 section_order | 1 | `unit_report` |

**Checkpoint**（注入验证，不修改 config.json）：
```python
custom_order = [
    {"key": "fund_performance", "name": "基金业绩分析", "number": 1, ...},
    {"key": "summary",           "name": "投资分析汇总",   "number": 2, ...},
    {"key": "market_value",      "name": "市值核算明细表", "number": 3, ...},
]
generate_excel_report(holdings, ..., section_order=custom_order)
# → 第 1 个页签标题: "1.基金业绩分析"
```

**可回退**：参数可选 None → 保持现有行为。`generate_excel_report()` 内部变量名与参数名不同，不会影子覆盖。
**风险**：**低**

---

### Phase 3：场景测试 + 回归验证

**目标**：端到端覆盖新增功能，确保全量回归。

**新增测试用例**：

| 测试文件 | 测试内容 | 项数 | Marker |
|:---------|:---------|:----:|:-------|
| `test_scenario_section_order.py` | 配置自定义顺序 → Excel 标题跟随 | 1 | `scenario_basic` |
| `test_scenario_section_order.py` | 配置自定义顺序 → HTML 标题跟随 | 1 | `scenario_basic` |

**回归验证**：
```bash
python scripts/test_runner.py --mode regression   # P0：234 项业务场景
python scripts/test_runner.py --mode verify       # P1：898 项
```

---

### Phase 4：文档更新

**目标**：将 C-P1b 标记为已完成。

| 文档 | 更新内容 |
|:-----|:---------|
| `docs-stm/managements/plan.md` | §C-P1b 标记完成，移除"已知限制"段落 |
| `docs-stm/managements/technical.md` | 补充 Excel 页签编号跟随配置的说明 |
| `docs-stm/managements/changelog.md` | 新增 v0.2.86 条目 |
| `docs-stm/manuals/reports-instruction.md` | 如有固定编号描述则同步更新 |

---

## 技术债务处理

### 本次迭代清偿的债务

| 债务 | 来源 | 等级 | 处理方式 | Phase |
|:-----|:-----|:----:|:---------|:----:|
| `_MODULE_KEY_MAP` 模块级缓存永不过期 | `llm_content.py:100` | ★★☆ | 移除缓存，每次从 `section_order` 参数构建 | Phase 2 |
| `_get_placeholder()` 查缓存链缺 `section_order` 透传 | `llm_content.py:126-133` | ★★★ | 沿 4 层调用链全量透传 | Phase 2 |
| 11 个写入器冗余调用 `set_sheet_title` | 各写入器文件 | ★★☆ | 职责统一到 `_create_sheets` | Phase 1 |

### 已识别但不在本次范围的技术债务

| 债务 | 位置 | 等级 | 说明 |
|:-----|:------|:----:|:------|
| `MODULE_KEYS` 硬编码列表 | `excel_generator.py:464` | ★☆☆ | 新增 LLM 模块时需同步维护，域逻辑目前稳定 |
| `write_html_report()` 14 个参数签名 | `html_writer.py:163` | ★★☆ | 可维护性退化，后续可改用 dataclass 或拆分为配置对象 |
| `_get_module_key_map()` 硬编码 filter(`news_correlation`, `llm_usage`) | `llm_content.py:112` | ★☆☆ | 域逻辑正确，不属缺陷，本次不改动 |

---

## 风险与缓解

| 风险 | 级 | 缓解 |
|:-----|:--:|:-----|
| 移除写入器 `set_sheet_title` 后某未发现的直接调用路径中断 | **低** | 经全量 grep 确认 12 处生产调用全部已预见，Phase 1 checkpoint 验证 |
| `_get_module_key_map()` 调用链 `section_order` 漏传 | **低** | 4 个函数全在 `llm_content.py` 内闭环，无外部跨模块调用 |
| `generate_excel_report()` 内部变量掩盖参数（影子覆盖） | **极低** | 设计时内部变量名与参数名不同（`order` vs `section_order`），code review 可捕获 |
| `_generate_excel_report()` 委托函数 `**kwargs` 不能透传 | **低** | `**kwargs` 天然支持新增关键字参数，无需修改委托函数 |
| Config 在 `handlers_report.py` 中不可达 | **低** | 已有 `get_config_cache()` 模式，4 条路径都使用 |
| 与用户配置的 `llm_usage` 强制末位冲突 | **低** | `get_report_section_order` 已有处理逻辑（Pop + append） |
| `_get_module_key_map()` 缓存移除后反复调用性能 | **极低** | 最多 14 项迭代，每次构建 dict < 0.01ms，无 I/O |
| 现有测试因新增参数而中断 | **极低** | 参数默认值 None，现有测试照常通过，已验证 `test_llm_content.py` + `test_excel_generator.py` + `test_integration.py` |
| `test_registry_edge.py` 被波及 | **极低** | 8 个 edge case 全测 `get_report_section_order()`，不涉及 `set_sheet_title()` |

**结论：所有风险已确认可控，可以开始实施。**

---

## 验证方案

### 自动化验证

```bash
# Phase 1 checkpoint
python -m pytest src/test/unit/core/test_registry.py -v -k "TestSetSheetTitleWithOrder"
python -m pytest src/test/unit/report/test_excel_generator.py -v -k "TestCreateSheets"

# Phase 2 checkpoint
python -m pytest src/test/unit/report/test_excel_generator.py -v -k "TestGenerateWithCustomOrder"
python -m pytest src/test/unit/llm/test_llm_content.py -v -k "module_key_map or custom_order"

# Phase 3 回归
python scripts/test_runner.py --mode regression   # P0：234 项
python scripts/test_runner.py --mode verify       # P1：898 项
```

### 端到端手动验证

```
1. 编辑 data/config/config.json，添加：
   "report_section_order": {
       "fund_performance": 1,
       "summary": 2,
       "market_value": 3
   }

2. 运行程序 → 菜单 E → 选择持仓 → 生成 Excel
3. 打开 .xlsx：
   - 第 1 个页签："1.基金业绩分析"
   - 第 2 个页签："2.投资分析汇总"
   - 第 3 个页签："3.市值核算明细表"
   - 后续未配置模块按默认序号续排
   - LLM 页签内部标题行文本（若有 LLM 内容）：跟随配置序号

4. 恢复 config.json，删除 report_section_order
5. 重启生成 → 标题恢复默认 1-16
```

---

## Phase 依赖关系

```
Phase 1 (set_sheet_title 改造 + 11 处冗余移除 + 单元测试)
   │
   ▼
Phase 2 (Config 接入 + _get_module_key_map 缓存修复 + 验证测试)
   │
   ▼
Phase 3 (场景测试 + 回归验证)
   │
   ▼
Phase 4 (文档)
```

每个 Phase 可回退：
- **Phase 1**：签名向后兼容（默认值 None），删除行可 `git revert`
- **Phase 2**：参数可选 None → 保持现有行为；缓存移除后功能仍正确（只是略慢 0.01ms）
- **Phase 3**：新增测试不修改现有逻辑，无回退风险
- **Phase 4**：纯文档变更
