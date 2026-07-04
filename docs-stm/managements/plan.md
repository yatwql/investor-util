# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-05（v0.2.85 — B 迭代完成：基金经理变更/重合度矩阵/集中度监控/风格漂移 4 模块）

---

## 问题描述

个人投资者需要基于持仓数据和市场行情，生成包含市值核算、资产穿透、基金分析等内容的投资分析报告。当前无现成工具，需从零构建 Python TUI 应用，对接中国金融数据源，输出 Excel 和 HTML 格式报告。

---

## 需求

完整需求详见 [`docs-stm/managements/requirements.md`](requirements.md)。

---

## 关键技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| TUI 框架 | 原生 `input()` 循环 | 零依赖，开发最快，满足菜单需求 |
| Excel 库 | `openpyxl` | 原生支持 .xlsx 读写、颜色/字体格式设置 |
| HTTP 客户端 | `httpx` | 同步/异步、连接复用，比 requests 现代 |
| 数据解析 | 手动解析，不使用 pandas | 减少依赖，数据量小，自定义校验更可控 |
| 配置持久化 | `data/config/config.json` | JSON 简单可靠，无需额外依赖 |
| AI 全球政经局势 + 智囊团深度复盘 + 持仓体检报告 + 穿透深度分析 + 财经新闻热点与持仓关联分析 | LLM 生成 | 支持 Claude/OpenAI/DeepSeek API，缓存策略分层，System Prompt 外部可配置 |
| 报告模板 | 程序生成（Excel openpyxl / HTML Jinja2） | Excel 和 HTML 报告均程序化生成 |

---

## 当前配置架构

LLM 配置拆分为两个独立文件：

| 文件 | 内容 | 用途 |
|------|------|------|
| `data/config/llm_key.json` | 4 个必填 + 4 个可选回退字段 | API 调用渠道（provider / api_key / model / endpoint / fallback_*） |
| `data/config/llm_settings.json` | 所有非敏感配置 | 参数调优（temperature、timeout、cache、system_prompt、thinking 等） |

---

## 系统影响

- `data/holdings/`、`data/cache/`、`data/config/` 在首次运行时需保证存在
- `data/config/config.json` 在程序生命周期外持久保存，含 `output_dir` 字段控制报告输出位置
- 程序依赖外部中国金融 API，网络不可用时降级运行（使用缓存数据或显示"--"）
- 持仓目录多 xlsx 文件时，用户通过 TUI 选择

---

## 风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 腾讯/东方财富 API 变更或封禁 | 行情获取失败 | 备用链路自动切换；缓存支撑当日使用 |
| 持仓 xlsx 格式与预期不一致 | 解析失败或数据错误 | 固定列名解析 + 字段校验 + 友好提示 |
| 基金穿透计算量大 | 报告生成变慢 | 穿透结果缓存每日更新 |
| LLM API Key 未配置 / 超时 | 全球政经局势 / 智囊团深度复盘不可用 | 降级输出占位文本，不阻塞报告生成 |
| LLM Token 费用超预期 | 成本增加 | 缓存 LLM 结果；限制输入上下文；分层缓存 TTL |

---

## 验证

每次迭代完成后：
1. 运行 `python src/python/main.py`，确认 TUI 正常导航
2. 选择对应功能生成报告文件
3. 打开输出目录下的报告确认内容完整
4. 模拟异常场景（断网、空目录、格式错误）确认程序不崩溃

---

## ✅ 已完成迭代

所有已完成迭代（A/A2/A3/A4/A5/B/J/K/L/P/N/Q/R/M/T/S/V/U/W/X/Y1/Y2/Y3/Y4/Y5/Y6/Z1/Z2/Z3/Z4）的详细变更记录见 [`docs-stm/managements/changelog.md`](changelog.md).

---

### 待实现方向（按风险收益比排序）

> 注：字母编号跳跃出于历史分配——已完成迭代占用了相应字母（详见上方 ✅ 已完成迭代），剩余字母保留给此前已规划但优先级较低的后续迭代。

---



### [P2-2] Y. Edge Case 纵深覆盖增补（四期）（低难度 / 中价值）

Y 系列（Y1-Y6）已全部完成，共 ~198 项 edge 测试覆盖了零值/空集/时区/缓存/API 异常/数据质量/文件系统/数值计算/安全纵深/配置环境等维度。

详细变更见 changelog.md Unreleased 章节。

---

Z 系列（Z1-Z4）已全部完成：
- Z1（特殊品种 S21-S28，27 项）
- Z2（操作行为 S29-S33，15 项）
- Z3（持仓质量 S0a-S0d，16 项）
- Z4（时间补充 T17-T21，21 项）

详细变更见 changelog.md Unreleased 章节。


### [P4] F. LLM 分析增强（低难度 / 中价值）

- **环比分析**：对比历史报告摘要，说明组合变化趋势
- **报告对比**：将本次报告的关键指标（市值/盈亏/仓位）与上次对比，输出变化摘要
- **回撤监控**：从历史缓存中提取持仓的连续回撤曲线

---

### [P5] O. 工程化增强（低难度 / 低价值）

- **CI/CD 集成**：添加 GitHub Actions 自动化流水线，每次 Push 自动运行 `pytest`
- **Excel 页签并行写入**：报告生成时每个页签独立写入，可考虑并行加速

---

### [P3] C. 报告序号可配置（中难度 / 高价值）

**目标**：在 `config.json` 中配置 Excel 页签和 HTML 章节标题的序号，使报告模块顺序可自定义。

---

#### 需求分析

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
| `fund_manager` | 13 | 基金经理变更监控 | B 系列（有数据才显示） |
| `fund_overlap` | 14 | 持仓重合度矩阵 | B 系列（有数据才显示） |
| `fund_concentration` | 15 | 持仓集中度监控 | B 系列（有数据才显示） |
| `fund_style` | 16 | 基金风格分析 | B 系列（有数据才显示） |
| `news_correlation` | 6 | 财经新闻热点与持仓关联分析 | 新闻（需启用） |
| `early_warning` | 7 | 智能预警 | 固定（需启用） |
| `global_macro` | 8 | 全球政经局势 | LLM |
| `expert_review` | 9 | 智囊团深度复盘 | LLM |
| `health_check` | 10 | 持仓体检报告 | LLM |
| `penetration_deep` | 11 | 穿透深度分析 | LLM |
| `llm_usage` | 12 | LLM API 用量 | LLM（**始终最后**） |

硬编码散布范围（19 处需要修改）：
- **HTML 模板**：14 处 `.section-title` + 11 处导航栏 `<a>` 硬编码中文+序号
- **Excel 页签**：11 个文件中独立的 `ws.title = f"X.{name}"` 调用
- **LLM 序号**：`llm_content.py` 的 `_get_module_key_map()` 硬编码起始序号 8

---

#### 设计要点

1. 配置格式：`config.json` 新增 `report_section_order: {"模块标识": 序号}`
2. `llm_usage` 不参与配置，强制最后一位
3. 未配置模块按默认顺序排在已配置模块之后
4. 统一 key 体系：`registry.py` 中定义 `_REPORT_SECTION_DEFAULT` 为唯一权威 key 来源，提供 `get_report_section_keys()` 供配置校验
5. 引入 `set_sheet_title(ws, key)` 辅助函数统一设置页签名，11 个文件改法一致
6. `excel_generator.py` 引入 `_SheetManager` 辅助类管理页签的创建与按 key 索引
7. LLM 页签由 `excel_generator.py` **预先创建**后传入 `write_llm_sheets()`，`llm_content.py` 只写内容不创建页签（解决页签创建顺序与配置顺序不匹配的问题）
8. **HTML 采用"参数化序号"方案**（非"循环渲染"）：只替换模板中的硬编码数字，不重构模板结构。Python 端计算 `section_numbers` 字典传给 Jinja2
9. HTML 条件可见性在 Phase 3 由 Python 端 `_section_visible(key, ...)` 函数统一判断，替代当前模板中的分散 `{% if %}`
10. 不配置时 100% 保持现状（回归安全）

---

#### 实施风险与控制

**第一轮审查发现的风险**：

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| HTML 模板循环渲染破坏可维护性 | 🔴高 | 采用参数化序号方案，不重构模板结构，只替换数字 |
| 11 个 sheet 文件 `ws.title` 写法各不同，遗漏修改 | 🟡中 | 统一使用 `set_sheet_title(ws, key)` 辅助函数，每个文件改法一致，grep 可验证无残留 |
| `excel_generator.py` 内部 `sheets["ws1"]`/`ws13` 硬编码索引需重构 | 🟡中 | 引入 `_SheetManager` 辅助类，内部函数通过 `sm.get(key)` 索引 |
| 与现有 `move_sheet` 冲突 | 🟢低 | Phase 1b 中直接删除（按序创建即正确顺序） |
| 用户配置的序号与条件可见性交叉（B 系列无数据但序号已安排） | 🟢低 | 用户自行处理序号跳空，不自动补号 |

**第二轮审查发现的新风险**：

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| `llm_content.py` 内部 `wb.create_sheet()` 追加到末尾，与配置排序不兼容（如用户将 global_macro 序号配在 fund_manager 之前，但 llm_content.py 在流程末尾才创建页签） | 🟡中 | 改为由 `excel_generator.py` **在流程开始时**按序预先创建所有 LLM 页签，`write_llm_sheets()` 只接收 ws 列表只写内容不创建 |
| `excel_generator.py` 中页签创建、数据计算、内容写入三个步骤耦合在一起，按配置序号排序需要分离创建与写入 | 🟡中 | `_SheetManager` 在流程开始时按序预创建所有页签；各 `_write_*` 函数通过 `sm.get(key)` 获取已创建的 ws；数据计算已在 `_resolve_market_data` 中先行完成，无需解耦 |
| 模块标识 key 在注册表和报告模块中不统一（如 `llm_news_correlation` vs `news_correlation`），用户配置时容易混淆 | 🟡中 | `registry.py` 的 `_REPORT_SECTION_DEFAULT` 定义唯一权威 key；`_validate_report_section_order()` 校验时用 `get_report_section_keys()` 检查 |
| Phase 3 循环渲染后，条件可见性判断需从模板 `{% if %}` 迁移到 Python 端，判断逻辑分散在各渲染函数中 | 🟢低 | 新增 `_section_visible(key, ...)` 集中函数管理可见性规则；可测可维护 |

---

#### Phase 划分

##### Phase 1a — 基础层（4 文件，纯新增，无行为变更）

**目标**：完成注册表、配置、辅助函数的基础代码，不改变任何已有行为。**即便 Phase 1b 被回退，1a 的代码也可保留**。

**改动文件**：

| 文件 | 改动内容 | 是否影响现有行为 |
|------|----------|------------------|
| `registry.py` | 新增 `_REPORT_SECTION_DEFAULT` 顺序定义（16 项完整列表）；新增 `get_report_section_order(config)`（合并配置+默认+llm_usage 置尾）；新增 `set_sheet_title(ws, key)`；新增 `get_report_section_keys()` | ❌ 纯新增函数，无人调用也不影响现有功能 |
| `config.py` | `validate_config()` 中新增 `_validate_report_section_order()` 校验（重复序号警告、未知标识警告、负值/非整数警告） | ❌ 纯新增校验，不影响现有配置项 |
| `config.json` | 可选新增 `report_section_order` 配置（用户不写此字段则完全不影响） | ❌ 可选新增，无人配则等同不存在 |
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

##### Phase 1b — Excel 全链路（基于 Phase 1a，14 文件改动）

**目标**：Excel 报告全链路支持配置序号。改动的文件多（14 个），但每处改动模式单一。

**改动文件**：

| 文件 | 改动内容 |
|------|----------|
| `excel_generator.py` | 引入 `_SheetManager` 辅助类，在流程开始按序预创建所有页签（含 LLM 页签）；内部函数签名从 `sheets` 字典改为 `_SheetManager`；删除 `wb.move_sheet(ws13...)` 后置逻辑；将预创建的 LLM ws 列表传入 `write_llm_sheets()` |
| 11 个 sheet 文件 | `ws.title = f"X.{name}"` → `set_sheet_title(ws, "模块标识")` 一行改动 |
| `llm_content.py` | `write_llm_sheets()` 接收预创建的 `ws_list` 参数，不再调用 `wb.create_sheet()`；`_get_module_key_map()` 从 `get_report_section_order()` 读取，删除硬编码 `idx = 8` |
| `summary.py` | `_init_llm_usage_sheet()` 使用配置序号，不再硬编码标题 |

**关键设计 —— `_SheetManager`**：

```python
class _SheetManager:
    """按配置顺序管理页签创建与索引。"""
    def __init__(self, wb, section_order, fund_deep=False, include_news=False, include_llm=False):
        self._map = {}
        for sec in section_order:
            key = sec["key"]
            if key == "llm_usage" and not include_llm:
                continue
            # B 系列无 fund_deep 时跳过
            # llm 模块（不含 news_correlation）由 Phase 1b 统一在 excel_generator 中创建
            if not self._should_create(key, fund_deep, include_news, include_llm):
                continue
            ws = wb.create_sheet()
            set_sheet_title(ws, key)
            self._map[key] = ws

    def get(self, key: str):
        return self._map.get(key)
    
    def llm_sheets(self) -> list[tuple[str, Any]]:
        """返回所有 LLM 模块的 (key, ws) 列表。"""
        return [(k, v) for k, v in self._map.items() 
                if k in _LLM_MODULE_KEYS]
```

**验收条件**：
- ✅ Excel 所有页签名 = `"{序号}.{中文名}"`，与配置一致
- ✅ B 系列不使用 `move_sheet`，创建即正确位置
- ✅ llm_usage 页签始终在最后
- ✅ LLM 页签按配置序号出现在正确位置（而非全部追加末尾）
- ✅ 不配置时顺序与 Phase 1a 之前完全一致（回归）
- ✅ 回归测试全部通过（全量 2244 项）

---

##### Phase 2 — HTML 序号参数化（3 文件，低风险，解决跳号）

**目标**：不改动模板结构，只在 Python 端计算当前各模块的序号，模板中替换全部 25 处硬编码序号变量。**这是 C 迭代的核心优化：不重构模板渲染逻辑**。

**方案**：

```python
# html_writer.py 在 render 时计算
section_numbers = {sec["key"]: sec["number"] for sec in get_report_section_order()}
html = _ENV.get_template("report_template.html").render(
    ..., section_numbers=section_numbers,
)
```

模板中全部 `一、` → `{{ section_numbers["summary"] }}、`：
```html
<div class="section-title">{{ section_numbers["summary"] }}、投资分析汇总</div>
<a href="#sec-summary">{{ section_numbers["summary"] }}、投资分析汇总</a>
```

**不改动的部分**：
- 所有 `{% if %}` 条件可见性逻辑保留原样
- section 内部 HTML 结构不变
- 渲染顺序仍按当前函数调用顺序（Phase 3 才改排序）
- 回退只需改 `render()` 一行调用 — 把 `section_numbers=` 改为空字典即可

**改动文件**：
- `html_writer.py`：计算 `section_numbers` 并传给模板
- `report_template.html`：全部 14 处 `.section-title` + 11 处导航栏硬编码序号替换为变量

**验收条件**：
- ✅ 所有章节标题 = `"数字、中文名"`，序号正确
- ✅ 不配置时顺序与 Phase 1b 完全一致（回归）
- ✅ 导航栏显示正确序号
- ✅ 条件隐藏（B 系列/LLM 无数据）仍正常工作

---

##### Phase 3 — HTML 可配置排序（2 文件，中风险，可回退到 Phase 2）

**目标**：在 Phase 2 的基础上，使 HTML 按配置序号重新排列模块展示顺序。

**方案**：`html_writer.py` 新增 `_section_visible(key, **data_flags)` 统一判断可见性。`write_html_report()` 按 `section_order` 顺序调用各 `_render_*` 函数，收集 HTML 片段为有序列表，模板循环渲染。

```python
# 条件可见性集中管理
_B_MODULE_KEYS = {"fund_manager", "fund_overlap", "fund_concentration", "fund_style"}
_LLM_MODULE_KEYS = {"global_macro", "expert_review", "health_check", "penetration_deep"}
_ALWAYS_VISIBLE = {"summary", "market_value", "category", "penetration", "fund_performance"}

def _section_visible(key: str, **kwargs) -> bool:
    if key in _ALWAYS_VISIBLE:
        return True
    if key in _B_MODULE_KEYS:
        return bool(kwargs.get(f"{key}_data"))
    if key == "news_correlation":
        return kwargs.get("include_news", False)
    if key == "early_warning":
        return bool(kwargs.get("early_warnings"))
    if key in _LLM_MODULE_KEYS or key == "llm_usage":
        return bool(kwargs.get("llm_enabled"))
    return True

# 按序收集已渲染的片段
sections_html = []
for sec in section_order:
    key = sec["key"]
    if not _section_visible(key, **data_flags):
        continue
    render_fn = _RENDER_FUNCTIONS[key]  # 分发映射表
    html_content = render_fn(**render_args)
    sections_html.append({
        "key": key, "number": sec["number"], "name": sec["name"],
        "content": html_content,
    })
```

模板中用循环替代当前各 section 的固定位置：
```html
<nav class="section-nav">
{% for sec in sections_html %}
  <a href="#sec-{{ sec.key }}">{{ sec.number }}、{{ sec.name }}</a>
{% endfor %}
</nav>

{% for sec in sections_html %}
<div id="sec-{{ sec.key }}"></div>
<div class="section">
    <div class="section-title">{{ sec.number }}、{{ sec.name }}</div>
    <div class="section-content">{{ sec.content | safe }}</div>
</div>
{% endfor %}
```

**可进可退策略**：
- 如果循环渲染后预览有问题，可以**只回退到 Phase 2**（参数化序号但保持固定顺序），序号的正确性不受影响
- `_RENDER_FUNCTIONS` 分发映射表是纯数据驱动，新增/移除模块只需要改这个映射表
- `_section_visible()` 集中函数易于测试

**改动文件**：
- `html_writer.py`：重构 `write_html_report()` 的渲染流程；新增 `_section_visible()` + `_RENDER_FUNCTIONS` 映射表

**验收条件**：
- ✅ 按配置序号排序后 HTML 模块顺序正确
- ✅ B 系列/LLM 无数据时自动隐藏
- ✅ 有数据时正常显示
- ✅ 不配置时顺序与 Phase 2 一致（回归）

---

##### Phase 4 — 文档 + 集成验证

**改动文件**：
- `docs-stm/manuals/how-to-config.md`：新增 `report_section_order` 配置说明
- `plan.md`：标记 C 迭代完成

**验收条件**：
- ✅ 实际生成一份完整 Excel + HTML 报告，检查所有序号
- ✅ 场景覆盖：不配置（默认顺序）、配置完整、部分配置、LLM 禁用时无 LLM 章节
- ✅ how-to-config.md 有 report_section_order 说明
