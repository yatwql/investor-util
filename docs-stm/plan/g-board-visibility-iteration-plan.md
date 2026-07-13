# G. 报告板块可见性可配置 — 迭代计划与技术设计

> 对应 `plan.md` 中的 [P4] G 任务项。

---

## 1. 设计概述

### 1.1 目标

为报告 5 个板块中尚未受控的 3 个（B 系列 `b_series`、新闻与预警 `news`、历史走势 `history`）增加可用/不可用开关。关闭后对应的页签/章节在 Excel/HTML 中完全不出现。LLM 板块（`llm`）已通过 `enabled_llm` 开关支持，基础核心板块（`always`）始终显示，不在本任务范围内。

### 1.2 设计原则

- **输出控制 vs 数据控制**：开关仅控制*输出可见性*，不阻止数据后台获取（避免开关变化导致缓存状态错乱）
- **遵循既有模式**：以 `llm_enabled` 的处理方式为模板（config.json 布尔字段 → handlers 读取 → sheet_factory/html 判断）
- **向后兼容**：旧 config.json 缺少字段时视为 `true`
- **遵从 C7 约束**：序号和显示名由注册表驱动，不改动
- **遵从 C14 约束**：不写入 `_ENV.globals`

### 1.3 改动范围

| 文件 | 改动 |
|:-----|:------|
| `config/_defaults.py` | 新增 3 个默认字段 |
| `config/_core.py` | 新增验证规则（字段为可选 bool） |
| `config/__init__.py` 或 `config.py` | 新增 `is_board_enabled()` 读取函数 |
| `handlers_report.py` | 4 个菜单命令读取配置字段替代硬编码或跟随逻辑 |
| `report/excel_sheet_factory.py` | `should_create_sheet()` 接收 `history_enabled` 标志 |
| `report/excel_generator.py` | 透传新标志 |
| `report/html_writer.py` | `_build_section_visibility()` 处理 `news_enabled`/`history_enabled`/`b_series_enabled` |
| `handlers_config.py` | 新增 TUI 子菜单（或扩展菜单 S）切换 3 个开关 |
| `test/` | 各迭代对应的测试用例 |

### 1.4 不动范围

- `html_jinja_env.py` 的 `section_visible` 闭包机制不变，只是外层 `data_flag` 字典多了 3 个键
- `report/portfolio_history.py` 数据获取逻辑不变
- `providers/` 新闻/行业数据获取逻辑不变
- 注册表 `_REPORT_SECTION_DEFAULT` 结构不变
- `excel_b_series.py` 等页签写入逻辑不变

---

## 2. 技术设计

### 2.1 配置字段

在 `config.json` 顶部新增（`_defaults.py` 同步）：

```json
{
  "b_series_enabled": true,
  "news_enabled": true,
  "history_enabled": true,
  // ... 其余现有字段
}
```

缺失时各读取函数回退 `True`。

### 2.2 现有关联梳理

当前系统中，`include_news` 控制的不只是 `news` 类型的页签：

| 变量 | 控制范围 | 当前来源 |
|:-----|:---------|:---------|
| `include_news` | type=news 页签（#10 新闻关联、#11 智能预警） | 菜单 E=H=false，B=L=true |
| `include_b_series` | type=b_series 页签（#6~9） | `include_news` 跟随（B/L 含） |
| `include_llm` | type=llm 页签（#12~15、#18） | `llm_enabled` 配置 |
| history type | type=history 页签（#16~17） | 始终可见 |

拆分后：

| 变量 | 控制范围 | 新来源 |
|:-----|:---------|:-------|
| `news_enabled` | type=news 页签（#10、#11） | `config.json` → `news_enabled` |
| `b_series_enabled` | type=b_series 页签（#6~9） | `config.json` → `b_series_enabled` |
| `history_enabled` | type=history 页签（#16~17） | `config.json` → `history_enabled` |
| `llm_enabled` | type=llm 页签（#12~15、#18） | 已有 |

**注意**：`include_news` 作为变量名将被保留，但含义简化为"菜单 B/L 是否应包含新闻相关页签"，不再负载体 B 系列的跟随逻辑。

### 2.3 数据流

```
config.json                      handlers_report.py
  ├─ b_series_enabled ──────────→ _cmd_generate_full()
  ├─ news_enabled    ──────────→   ├─→ excel_generator(include_news, include_b_series, include_llm)
  ├─ history_enabled ──────────→   │     └─→ excel_sheet_factory(history_enabled)
  └─ (llm_enabled 已有)          │     └─→ excel_b_series(b_series_enabled)
                                  └─→ html_writer(include_news, b_series_enabled, history_enabled)
                                        └─→ _build_section_visibility()
                                              └─→ section_visible_dict
                                                    └─→ Jinja2 template
  TUI 菜单
  handlers_config.py
  └─→ 编辑 config.json → 下次报告生成生效
```

### 2.4 函数签名变更

`excel_sheet_factory.py`：

```python
def create_sheets(
    wb, section_order,
    enable_b_series=False,
    include_news=False,
    include_llm=False,
    history_enabled=True,              # ← 新增
) -> dict:
```

`should_create_sheet()` 增加：

```python
type_map = {
    "history": history_enabled,        # ← 从 True 变为可配置
    ...
}
```

`html_writer.py` 中的 `_build_section_visibility()`：

```python
raw_data_flags = {
    "include_news": include_news,      # 已有
    "b_series_enabled": b_series_enabled,      # ← 新增
    "news_enabled": include_news,               # ← 新增（别名，复用 include_news 值）
    "history_enabled": history_enabled,         # ← 新增
    "early_warnings": bool(early_warnings),     # 已有
    "llm_enabled": llm_enabled_flag,            # 已有
}
```

注册表 `_REPORT_SECTION_DEFAULT` 中对应的 `data_flag`：

```python
# 已有
{"key": "fund_manager",       "type": "b_series",  "data_flag": "manager_data"},
# ...
# 改为（新增 data_flag 关联到板块级开关）
{"key": "fund_manager",       "type": "b_series",  "data_flag": "b_series_enabled"},
{"key": "news_correlation",   "type": "news",      "data_flag": "include_news"},
{"key": "early_warning",      "type": "news",      "data_flag": "include_news"},
{"key": "portfolio_history",  "type": "history",   "data_flag": "history_enabled"},
{"key": "drawdown_analysis",  "type": "history",   "data_flag": "history_enabled"},
```

> 变更后 `data_flag` 语义从"数据是否就绪"扩展为"数据就绪 && 板块是否启用"。HTML 侧的 `section_visible_dict` 会联动判断。

### 2.5 设计约束遵守

| 约束 | 遵守方式 |
|:-----|:---------|
| C7 报告序号不可硬编码 | 不改序号逻辑，只控制页签创建/隐藏 |
| C14 不写 _ENV.globals | 不新增模块级全局变量，section_visible 闭包机制不变 |
| C2 缓存统一管理 | 不改缓存层 |
| C6 Provider Chain 必经 | 不改数据获取链路 |
| C8 日志统一 | 使用 `logger = logging.getLogger("invest")` |

### 2.6 风险与缓解

| 风险 | 影响 | 缓解 |
|:-----|:-----|:-----|
| 板块关闭后数据缓存停止更新，开启后立即面临冷启动 | 用户开启后等待变长 | 迭代 6 专项处理：关闭仅控输出，数据仍按 TTL 后台获取 |
| 用户误关闭导致页签发懵 | 用户困惑 | TUI 菜单明确标注关闭范围，报告页脚加注"部分板块已关闭"提示 |
| `b_series_enabled` 与现有 `include_b_series` 跟随逻辑冲突 | B 系列在菜单 E/H 中意外显示 | 统一入口：`include_b_series` 统一从配置读取，不再依赖 `include_news` |
| 旧 config.json 升级后找不到新字段 | 板块被隐藏 | 读取函数默认 `True`，缺失时日志 INFO 提示 |

---

## 3. 迭代计划（10 轮）

### 迭代 1：Config 默认值与 schema

**范围**：`config/_defaults.py`、`config/_core.py`

**内容**：
- `_defaults.py` 中 `_DEFAULT_CONFIG` 新增 `b_series_enabled: true`、`news_enabled: true`、`history_enabled: true`
- `_core.py` 的 `validate_config()` 中验证：上述字段必须为 bool（如果存在）；不存在不报错
- 新增字段应出现在 `_COMMENTED_TEMPLATE` 的注释模板中

**验收标准**：
- [ ] `_DEFAULT_CONFIG` 包含 3 个新字段且默认 `true`
- [ ] 验证函数接受缺失字段（旧配置升级）
- [ ] 验证函数拒绝非 bool 值（`"yes"`/ `1` / `null` 时报错）
- [ ] 验证函数接受 `true` / `false`
- [ ] `_COMMENTED_TEMPLATE` 新字段带中文注释

**可回退**：仅新增的配置字段默认值，无行为变化。回退只需删除字段。

---

### 迭代 2：Config 读取函数

**范围**：`config/__init__.py` 或现有 `config` 模块

**内容**：
- 新增 `is_b_series_enabled(config: dict) -> bool`
- 新增 `is_news_enabled(config: dict) -> bool`
- 新增 `is_history_enabled(config: dict) -> bool`
- 各函数内部逻辑：`config.get(key, True)`，缺失时 logger.debug 记录
- 单元测试覆盖：字段存在/缺失/非 bool 边界

**验收标准**：
- [ ] 3 个读取函数在字段缺失时返回 `True`
- [ ] 3 个读取函数在字段 `false` 时返回 `False`
- [ ] 单元测试 ≥6 项（2 场景 × 3 函数：缺失 + 设为 false）
- [ ] 向后兼容：默认值不变

**可回退**：纯新增辅助函数，无消费者则不产生行为变化。

---

### 迭代 3：Excel Sheet Factory 接收历史走势开关

**范围**：`report/excel_sheet_factory.py`

**内容**：
- `create_sheets()` 签名新增 `history_enabled: bool = True`
- `should_create_sheet()` 的 `type_map` 中 `"history"` 从 `True` 改为 `history_enabled`
- `excel_generator.py` 的 `generate_excel_report()` 调用处传入 `history_enabled`
- 当前 `generate_excel_report()` 调用者全部使用默认值 `True`（无行为变化）

**验收标准**：
- [ ] `should_create_sheet({"type": "history"}, ...)` 在 `history_enabled=False` 时返回 `False`
- [ ] `should_create_sheet({"type": "history"}, ...)` 在 `history_enabled=True` 时返回 `True`
- [ ] 现有 E/H/B/L 菜单行为无变化（全部默认 `True`）
- [ ] 单元测试 ≥4 项

**可回退**：不改调用者，不改 HTML 侧。回退只需恢复签名默认值。

---

### 迭代 4：B 系列与新闻独立控制

**范围**：`handlers_report.py`、`report/excel_generator.py`

**内容**：
- `handlers_report.py` 中 `_cmd_generate_excel()`、`_cmd_generate_html()`、`_cmd_generate_both()`、`_cmd_generate_full()` 调用 `is_b_series_enabled()`、`is_news_enabled()`、`is_history_enabled()` 读取配置
- 移除 `generate_excel_report()` 中 `include_b_series` 跟随 `include_news` 的默认逻辑
- `handlers_report.py` 透传 3 个独立的 bool 参数给 `generate_excel_report()`

**验收标准**：
- [ ] `config.json` 中 `"b_series_enabled": false` 时，B 系列 #6~9 不在 Excel 中创建
- [ ] `config.json` 中 `"news_enabled": false` 时，新闻 #10~11 不在 Excel 中创建
- [ ] `config.json` 中 `"history_enabled": false` 时，历史走势 #16~17 不在 Excel 中创建
- [ ] 各字段缺省时默认开启（向后兼容）
- [ ] 单元测试 ≥6 项（3 个开关 × 开/关）

**可回退**：不改 HTML 侧。回退只需在 handlers 中恢复旧逻辑。

---

### 迭代 5：HTML 报告板块可见性

**范围**：`report/html_writer.py`

**内容**：
- `_build_section_visibility()` 新增 `b_series_enabled`、`news_enabled`、`history_enabled` 三个原始数据标志
- 注册表 `_REPORT_SECTION_DEFAULT` 中 `b_series` 类型的 `data_flag` 从 `"manager_data"` 等改为 `"b_series_enabled"`
- `history` 类型的 `data_flag` 新增为 `"history_enabled"`
- HTML 模板的 `{% if section_visible("fund_manager") %}` 等条件不变（底层 `data_flag` 变更后自动生效）
- 注意：`b_series_enabled` 与子模块级 `manager_data` 等的关系：板块关闭 → 整组不可见，板块开启 → 按子模块数据是否就绪决定（保留现有二级控制）

**验收标准**：
- [ ] `"news_enabled": false` 时 HTML 不渲染新闻章节 #10~11
- [ ] `"history_enabled": false` 时 HTML 不渲染走势回撤章节 #16~17
- [ ] `"b_series_enabled": false` 时 HTML 不渲染 B 系列章节 #6~9
- [ ] 各字段缺省时 HTML 渲染正常
- [ ] 单元测试 ≥6 项

**可回退**：不改 TUI 菜单。回退只需在 html_writer 中恢复旧 `_build_section_visibility()`。

---

### 迭代 6：TUI 菜单新增板块配置命令

**范围**：`handlers_config.py`、`tui_menu.py`（菜单项注册）

**内容**：
- 新增 `handlers_config.py` 中的 `_cmd_config_report_boards()` 函数
- 交互方式：类似菜单 S 的 1-5 数字切换，1=B 系列、2=新闻与预警、3=历史走势、4=LLM 板块（可选，只读或引用已有）、0=返回
- 从 `config.json` 读取当前状态渲染菜单
- 切换后写入 `config.json`（使用 `atomic_write` 遵守 C3）
- 主菜单新增一项（如 `[P]` 配置报告板块可见性），在菜单 S 附近
- 菜单项注册到 `tui_menu.py` 的 `_MENU_ITEMS`

**验收标准**：
- [ ] 按 `P` 进入板块配置子菜单
- [ ] 子菜单显示 3 个板块当前状态（✓启用/✗禁用）
- [ ] 按 1/2/3 切换对应板块启停并实时保存到 config.json
- [ ] 按 0 返回主菜单
- [ ] 修改 config.json 后下次报告生成生效
- [ ] 边界：config.json 不可写时友好报错

**可回退**：新增菜单项和 handler，不与既有功能耦合。回退只需移除菜单项注册。

---

### 迭代 7：TUI 菜单子页面完善

**范围**：`handlers_config.py`

**内容**：
- 完善子菜单 UI：添加板块说明行（关闭后哪些页签消失）
- 状态变化时显示反馈（如 `[OK] B 系列已关闭（#6-9 基金经理/重合度/集中度/风格分析将不再显示）`）
- 特殊提示：历史走势关闭时也关闭回撤分析（两者一体）
- 异常处理：config.json 读取失败时降级显示默认值并提示

**验收标准**：
- [ ] 子菜单显示每个板块包含的页签编号和名称
- [ ] 切换时有清晰反馈，说明页签范围
- [ ] config.json 损坏时不会崩溃，有友好提示
- [ ] 手动编辑 config.json 后，TUI 菜单下次进入时反映最新状态

**可回退**：纯 UI 改善，无逻辑变更。

---

### 迭代 8：数据获取与输出解耦验证

**范围**：`handlers_report.py`

**内容**：
- 检查所有 4 个菜单命令的数据获取流程：当某个板块关闭时，其所需数据是否仍然被获取
- 预期行为：板块关闭**不跳过**数据获取——例如 `news_enabled: false` 时，新闻仍会在后台获取并缓存，只是报告中不渲染
- 修复任何因板块关闭而跳过数据获取的代码路径（如 `_cmd_generate_both` 的 B 系列数据获取被 `include_news` 条件包裹的）
- 增加内部测试：mock config 返回 false，验证数据获取函数仍被调用

**验收标准**：
- [ ] `news_enabled: false` 时，新闻数据仍在后台获取（缓存预热正常）
- [ ] `b_series_enabled: false` 时，基金持仓数据仍在后台获取
- [ ] `history_enabled: false` 时，历史走势数据不在后台获取（免去不必要的 API 调用——这个是例外：既然用户不需要这个板块，不获取也没关系）
- [ ] 日志可追踪：板块关闭时 log INFO 记录

**可回退**：纯修正，不新增接口。回退时不影响既有功能。

---

### 迭代 9：测试覆盖

**范围**：`test/`

**内容**：
- 单元测试：
  - `test_config.py`：3 个新字段的读取和验证（≥6 项）
  - `test_excel_sheet_factory.py`（或已有文件追加）：`should_create_sheet` 对 5 种 type 在新 3 种标志下的行为（≥12 项）
  - `test_html_writer.py`：`_build_section_visibility` 对 3 个新标志的处理（≥6 项）
  - `test_handlers_config.py`（或已有文件追加）：板块配置子菜单的显示逻辑（≥6 项）
- 边缘测试（`*_edge.py`）：
  - config.json 损坏/缺失字段时的降级（≥3 项）
  - config.json 写入权限拒绝时的错误处理（1 项）
- 新增文件按规范标注 `pytest.mark.unit` + 子组标记
- 新增标记（如需）注册到 `conftest.py`

**验收标准**：
- [ ] 全部新测试通过
- [ ] `python scripts/check-test-markers.py` 无报错
- [ ] 边缘测试在 `*_edge.py` 文件中

---

### 迭代 10：文档同步

**范围**：`docs-stm/manuals/how-to-config.md`、`docs-stm/manuals/reports-instruction.md`、`docs-stm/managements/changelog.md`

**内容**：
- `how-to-config.md`：
  - config.json JSON 样本新增 3 个字段
  - 字段说明表新增 3 行：默认值、说明、TUI 修改方式
  - TUI 菜单说明新增 `[P] 配置报告板块可见性` 项
- `reports-instruction.md`：
  - 新增的"页面/章节分组"节补充开关对应说明
  - 注明各板块的配置字段名
- `changelog.md`：完整记录本次变更
- `datasource-and-folders.md`：无变更（不改目录结构）

**验收标准**：
- [ ] `how-to-config.md` 3 处更新（JSON 样本 + 字段表 + 菜单表）
- [ ] `reports-instruction.md` 分组节标注配置字段
- [ ] `changelog.md` v0.4.5 条目
- [ ] 目录树同步检查

---

## 4. 总量估算

| 迭代 | 文件数 | 代码量（估算） | 测试项数 | 风险 |
|:-----|:------|:--------------|:---------|:-----|
| 1 | 2 | +15 行 | 4 | 低 |
| 2 | 1 | +20 行 | 6 | 低 |
| 3 | 3 | +10 行 | 4 | 低 |
| 4 | 2 | +40 行 | 6 | 中（可能影响现有菜单） |
| 5 | 2 | +30 行 | 6 | 中（注册表 data_flag 修改需审视） |
| 6 | 2 | +80 行 | — | 中（新建 TUI 子菜单） |
| 7 | 1 | +30 行 | — | 低 |
| 8 | 1 | +10 行 | 3 | 低 |
| 9 | 3+ | +120 行 | 34+ | 低 |
| 10 | 3 | +30 行 | — | 低 |
| **合计** | ~20 | ~385 行 | ~69 项 | — |
