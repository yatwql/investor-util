# G. 报告板块可见性可配置 — 迭代计划与技术设计

> 对应 `plan.md` 中的 [P4] G 任务项。

---

## 1. 设计概述

### 1.1 目标

为报告 5 个板块中尚未受控的 3 个增加可用/不可用开关。关闭后对应的页签/章节在 Excel/HTML 中完全不出现。

| 板块 | type | 配置字段 | 含页签 |
|:-----|:-----|:---------|:-------|
| B 系列基金深度分析 | `b_series` | `enable_b_series` | #6 基金经理变更监控、#7 持仓重合度矩阵、#8 持仓集中度监控、#9 基金风格分析 |
| 新闻与预警 | `news` | `enable_news` | #10 财经新闻热点与持仓关联分析、#11 智能预警 |
| 历史走势 | `history` | `enable_history` | #16 组合历史走势、#17 历史回撤分析 |

LLM 板块（`llm`，#12~15、#18）已通过现有 `enabled_llm` 机制支持，基础核心板块（`always`，#1~5）始终显示，均不在本任务范围内。

### 1.2 设计原则

- **两层可见性模型**：页签可见性 = 板块开关（board 层）AND 数据可用性（data 层）。避免"用户开启了但没有数据时页签静默消失"的缺陷
- **板块关闭 = 完全跳过**：关闭板块时，对应的数据获取和输出渲染均跳过，不做"缓存预热"例外（见 §2.5）
- **严格区分配置与运行时**：`enable_news`（配置字段，表示用户意愿）与 `news_data_available`（运行时标志，表示数据获取状态）**不可混淆**——前者是 board 层输入，后者是 data 层输入
- **两端各自内联 board dict**：Excel 和 HTML 两端都各自构造 `{"always":True, "b_series":..., ...}` 字面量，不提取公共函数。行为一致性由集成测试保证
- **遵循既有模式**：以 `enabled_llm`（config 对象）的处理方式为模板（config.json → handlers 读配置 → sheet_factory/html 双层判断）
- **向后兼容**：旧 config.json 缺少字段时视为 `true`
- **数据层不变**：不改缓存引擎、Provider Chain、注册表 data_flag 字段

### 1.3 设计约束遵守

| 约束 | 遵守方式 | 自检状态 |
|:-----|:---------|:---------|
| **C1 代码类型判定中心化** | 不涉及代码类型判定，不受影响 | ✅ |
| **C2 缓存统一管理** | 不改缓存层。跳过数据获取是在入口处做条件判断，不影响缓存层代码 | ✅ |
| **C3 缓存原子写入** | 配置文件写入使用 `set_config()`（内部 `tempfile.mkstemp`+`os.replace`） | ✅ |
| **C4 会话级 API 复用缓存** | 分析 B 系列数据依赖时引用 `session_cache_get("fund_hold", code)`——B 系列关闭时 fund_hold 由穿透模块兜底，不破坏 C4 | ✅ |
| **C5 HTTP 客户端统一** | 不涉及新增 HTTP 调用 | ✅ |
| **C6 Provider Chain 必经** | 跳过数据获取是在 Provider Chain 入口之前做条件判断，不是绕过链路 | ✅ |
| **C7 报告序号不可硬编码** | `should_create_sheet()` 的 `type_map` 硬编码 type→bool 属于 conscious trade-off（type 数已稳定在 5，不值得抽象化） | ⚠️ 已评估 |
| **C8 日志统一** | 使用 `logger = logging.getLogger("invest")` | ✅ |
| **C9 LLM 模块注册** | 不涉及 LLM 模块 | ✅ |
| **C10 新闻召回策略** | 不影响 | ✅ |
| **C11 测试标记强制** | 新增测试全部标注对应 marker | ✅ |
| **C12 边缘测试文件隔离** | 边界场景测试放在 `*_edge.py` | ✅ |
| **C13 测试敏感路径隔离** | 使用 `_isolate_sensitive_paths` fixture | ✅ |
| **C14 渲染期数据不可写入模块级全局变量** | `_compute_section_visibility()` 闭包机制维持不变，仅增加 board 层参数。_sv_fn 闭包边界不受影响 | ✅ |
| **C15 控制台日志着色** | 不涉及 | ✅ |

### 1.4 改动范围总览

| 模块 | 文件 | 改动 |
|:-----|:-----|:------|
| 配置 | `config/_defaults.py` | 新增 3 个默认字段 |
| 配置 | `config/_core.py` | 新增验证规则（字段为可选 bool） |
| 配置 | `config/__init__.py` | 新增 3 个 is_xxx_enabled() 读取函数 |
| 公共工具 | — | 无新增文件。Excel 和 HTML 两端各自内联 board dict 字面量 |
| 报告核心 | `report/excel_sheet_factory.py` | `create_sheets()` 签名新增 `enable_history`；board 层预过滤在 `should_create_sheet()` 之前拦截 |
| 报告核心 | `report/excel_generator.py` | 透传 3 个独立标志；移除 `include_b_series` 跟随旧 `include_news` 的联动逻辑 |
| 报告核心 | `report/html_writer.py` | `_compute_section_visibility()` 新增 board 层判断（两层模型），参数名更新 `include_news`→`news_data_available`（data 层），新增 `enable_news`（board 层） |
| TUI 入口 | `main.py` | 移除 H 菜单键绑定（取消 `_cmd_generate_html` 入口） |
| TUI | `handlers_report.py` | 移除 `_cmd_generate_html()`（~25 行）；剩余 3 个菜单命令（E/B/L）从 config 读取 3 个标志；提取 F2 历史获取公共函数 |
| TUI | `handlers_config.py` | 新增板块配置子菜单（读/写 config.json） |
| TUI | `tui_menu.py` | 注册新菜单项 `[P]` 配置报告板块；移除 H 菜单行 |
| 测试 | `test/` 各文件 | 每轮内嵌对应测试，末轮集成验证 |

---

## 2. 技术设计

### 2.1 配置字段

```json
{
  // 板块可见性（关闭后对应页签/章节在报告中完全隐藏）
  "enable_b_series": true,    // B 系列基金深度分析（#6~9）
  "enable_news": true,        // 新闻与预警（#10~11）
  "enable_history": true,     // 历史走势+回撤分析（#16~17）
  ...
}
```

缺失时各读取函数回退 `True`。

### 2.2 Board Flags 内联方案

Excel 和 HTML 两端各自构造内联 dict 字面量，不提取公共函数。结构相同：

```python
board_flags = {
    "always":   True,
    "b_series": enable_b_series,
    "news":     enable_news,      # ← 配置驱动的 board 层值，不是运行时 news_data_available
    "history":  enable_history,
    "llm":      enable_llm,
}
```

两端行为一致性由迭代 4 和迭代 6 的集成测试覆盖，避免共享函数带来的过度抽象。

### 2.3 两层可见性模型（核心设计）

```
section_visible = board_enabled(type) AND data_available(data_flag)
                  ↑ 用户配置              ↑ 数据是否就绪（现有机制）
```

实现方式——在 `html_writer.py` 的 `_compute_section_visibility()` 中：

```python
# board 层配置（内联 dict）
board_flags = {
    "always":   True,
    "b_series": enable_b_series,
    "news":     enable_news,          # ← 配置驱动，非菜单驱动
    "history":  enable_history,
    "llm":      enable_llm,           # ← board 层，从 enabled_llm 派生
}

# 数据层标志（不变，仍是各子模块的 data_available）
data_flags: dict[str, bool] = {
    "manager_data":      manager_analysis is not None,
    "overlap_data":      overlap_matrix is not None,
    "concentration_data": concentration_analysis is not None,
    "style_data":        style_analysis is not None,
    "news_data_available":      news_data_available,          # ← 运行时标志（菜单驱动），表示"数据是否已获取"
    "early_warnings":    bool(early_warnings),
    "llm_enabled":       llm_data_available,                 # ← data 层：LLM 内容是否成功生成
}

# 两层合并
for sec in order:
    board_ok = board_flags.get(sec["type"], True)
    data_ok = data_flags.get(sec["data_flag"], True) if sec["data_flag"] else True
    section_visible_dict[sec["key"]] = board_ok and data_ok
```

**关键变更**：board_flags 中的 `"news"` 使用 `enable_news`（配置值），**不是** `news_data_available`（菜单驱动的运行时值）。这样在"菜单 B + enable_news=false"时，board_ok=false 正确拦截新闻板块。

`_REPORT_SECTION_DEFAULT` 的 `data_flag` 字段**完全不变**。

### 2.4 命名规范

| 变量名 | 所属层次 | 驱动来源 | 含义 |
|:-------|:---------|:---------|:-----|
| `enable_news` | board 层 | config.json | 用户意愿——新闻板块是否开启 |
| `news_data_available` | data 层 | 数据获取状态 | 运行时标志——新闻数据是否已获取 |
| `enable_b_series` | board 层 | config.json | 用户意愿——B 系列板块是否开启 |
| `enable_history` | board 层 | config.json | 用户意愿——历史走势板块是否开启 |
| `enable_llm` | board 层 | config.json `enabled_llm` | 用户意愿——LLM 板块是否开启 |
| `llm_data_available` | data 层 | LLM 生成状态 | 运行时标志——LLM 内容是否成功生成 |

### 2.5 数据流

```
config.json                          handlers_report.py
  ├─ enable_b_series ─────────────→ _cmd_generate_excel()    [E]
  ├─ enable_news    ─────────────→   │  → core 数据 → Excel 报告
  ├─ enable_history ─────────────→   │    （board 不影响数据获取，仅输出侧隐藏页签）
  └─ (enabled_llm config 已有)          │
                                       ├─ _cmd_generate_both()    [B]
                                       │  → core + news + B 系列 + F1/F2
                                       │  → Excel + HTML 报告
                                       │  → board 向下覆盖：关→跳过获取
                                       │
                                       ├─ _cmd_generate_full()    [L]
                                       │  → core + news + B 系列 + F1/F2 + LLM
                                       │  → Excel + HTML 报告
                                       │  → board 向下覆盖：关→跳过获取
                                       │
                                       ├─→ excel_generator(board_flags...)
                                       │     └─→ excel_sheet_factory()
                                       │            ├─ 内联 board_flags dict
                                       │            └─ should_create_sheet() → data 层判断
                                       │
                                       ├─→ ProgressReporter.update()  ← 跳过时输出提示
                                       │
                                       └─→ html_writer(board_flags...)
                                             └─→ _compute_section_visibility()
                                                   ├─ 内联 board_flags dict
                                                   ├─ data_flags (数据就绪)
                                                   └─ → section_visible_dict
                                                        └─ → Jinja2 template

  TUI 菜单
  handlers_config.py
  └─→ _cmd_config_report_boards()
        → 读取 config.json → 显示当前状态
        → 用户切换 → set_config() 写入 config.json
```

### 2.6 输出侧函数签名变更

**`report/excel_sheet_factory.py`**：

```python
def create_sheets(
    wb, section_order,
    enable_b_series=True,       # board 层：配置驱动（默认与 config 一致）
    news_data_available=False,  # data 层：运行时标志，表示新闻数据是否已获取
    enable_news=True,           # board 层：配置驱动（默认与 config 一致）
    llm_data_available=False,   # data 层：运行时标志
    enable_history=True,        # board 层：配置驱动
    enable_llm=True,            # board 层：配置驱动（从 enabled_llm 派生）
) -> dict:
```

内部实现——board 层预过滤使用配置驱动的 `enable_news`，data 层保持 `news_data_available`：

```python
board_flags = {
    "always":   True,
    "b_series": enable_b_series,
    "news":     enable_news,         # ← 配置驱动（非 news_data_available！）
    "history":  enable_history,
    "llm":      enable_llm,          # ← board 层（llm_data_available 用于 data 层）
}

for sec in section_order:
    if not board_flags.get(sec.get("type", ""), True):
        continue          # board 层关闭 → 完全跳过创建
    if not should_create_sheet(sec, ...):  # data 层判断
        continue
    ...
```

> **board vs data 层的职责**：board 层回答"用户想看这个板块吗？"（配置驱动），data 层回答"这个菜单类型支持这个板块吗？"（运行时驱动）。`should_create_sheet()` 中 `type_map["news"] = news_data_available` 保持不变，仍用于 data 层判断。

**`report/excel_generator.py`** 的 `generate_excel_report()` 签名新增 `enable_news`：

```python
def _compute_section_visibility(
    order: list[dict],
    manager_analysis, overlap_matrix,
    concentration_analysis, style_analysis,
    news_data_available: bool,                    # data 层：数据是否已获取
    early_warnings,
    llm_data_available: bool,            # data 层：LLM 内容是否成功生成
    # ↓↓↓ 新增 board 层参数 ↓↓↓
    enable_news: bool = True,             # board 层：新闻板块是否开启（配置）
    enable_b_series: bool = True,         # board 层：B 系列板块是否开启
    enable_history: bool = True,          # board 层：历史走势板块是否开启
    enable_llm: bool = True,              # board 层：LLM 板块是否开启（配置）
) -> tuple:
```

### 2.7 数据获取与输出解耦策略

> **H 菜单已取消**（v0.4.5）。原 H（仅 HTML 报告）与 E 功能重叠，移除后菜单简化为 E/B/L 三层。

> 原则：板块关闭 = 完全跳过，统一一刀切，不做"缓存预热"例外。

**菜单数据获取范围：**

| 菜单 | 原始定位 | board 对数据获取的影响 | board 对输出侧的影响 |
|:-----|:---------|:----------------------|:---------------------|
| **E**（Excel） | 快速生成 Excel，仅 core 数据 | **不影响**——永远不拉 news/B/history | 页签按 board 隐藏 |
| **B**（Both） | 全系列 Excel+HTML | **向下覆盖**——board 关→跳过对应数据获取 | 页签按 board 隐藏 |
| **L**（Full） | 全量+LLM Excel+HTML | **向下覆盖**——board 关→跳过对应数据获取 | 页签按 board 隐藏 |

**设计理由：** E 菜单的合约是"快速 Excel"（~5s），board 开关不应破坏这个合约。B/L 本身就要获取这些扩展数据，board 关只是节省获取成本。三者互不矛盾。

**各板块关闭时的具体行为：**

| 板块 | 板块关闭时行为 | 依据 |
|:-----|:--------------|:-----|
| 新闻 | 跳过 5 源 HTTP + LLM 关联分析（B/L 菜单下） | 省流量 + 省 Token 费用 |
| B 系列 | 跳过基金经理数据获取 + 4 个模块的计算（B/L 菜单下） | 省 CPU（fund_hold 由穿透模块兜底，B 系列只是复用） |
| 历史走势（F2） | 跳过 N×M 个 HTTP 请求（B/L 菜单下） | 省最多流量（最昂贵操作） |

**三个板块**的独有数据都不被其他模块依赖（B 系列的 fund_hold 由穿透模块兜底，其他两个的数据仅限自身使用），因此关闭时完全跳过没有任何副作用。

> **F1 持仓快照说明**：`enable_history` **不影响** F1 持仓快照。F1 快照（`history_snapshot.py`）始终在 B/L 菜单下自动执行，snapshot 文件保存在 `data/history/snapshots/`，独立于缓存系统。当 `enable_history=false` 时：
> - F2 历史走势：不获取，对应页签隐藏
> - F1 快照对比：继续捕获快照（save + prune），但环比差异摘要随 #17 回撤分析页签的隐藏而不可见
> - 下次 `enable_history=true` 时：F1 可追溯到完整的快照链，无数据断裂

实现方式：`handlers_report.py` 中各菜单命令读取配置字段，在数据获取阶段就条件跳过。

**F2 历史获取消除重复**：当前 `_cmd_generate_both()` 和 `_cmd_generate_full()` 中存在完全相同的 ~25 行 F2 历史数据获取代码。本迭代将提取为共享函数 `_fetch_history_data(history_mode, holdings)`，避免迭代 5 中需要改 2 处的风险。

### 2.8 风险与缓解

| 风险 | 影响 | 缓解 |
|:-----|:-----|:-----|
| **用户误操作关闭板块后页面静默消失** | 用户以为数据出问题 | 1) TUI 菜单切换时有明确范围提示；2) 报告页脚或汇总区可选标注"部分板块已关闭"；3) Excel/HTML 中板块关闭时不留下空位也不显示占位（静默隐藏），与 LLM 禁用行为一致 |
| **两层模型遗漏导致数据不可用时误显示** | 板块开关开 + 数据获取失败 → 显示空内容 | 两层模型要求 `board_ok AND data_ok`，空数据由 data_flag 拦截。需确保 `section_visible_dict` 对所有既有 data_flag 仍然赋值 |
| **旧 config.json 无新字段** | 板块被隐藏 | 读取函数默认 `True`，缺失时 logger.debug 记录 |
| **历史数据获取代码重复** | 迭代 5 需改 2 处，可能漏改 | ✅ 提取 F2 历史获取为共享函数 `_fetch_history_data()` |
| **F1 快照行为未定义**（enable_history=false 时） | F1 快照被误跳过导致环比链断裂 | ✅ §2.7 中明确 F1 不受影响，始终执行 |
| **两层模型增加理解成本** | 后续开发者可维护性降低 | 代码注释标注两层逻辑；两端内联 board dict 保持代码局部性 |
| **`news_data_available` 误用配置值**（传入 `enable_news` 而非真实数据状态 `news_available`） | enable_news=True + 数据获取失败 → 空内容页签 | ✅ §2.7/Iter5 中明确区分：`news_available = bool(news_data) if enable_news else False`，data 层传 `news_available` 非 `enable_news` |

### 2.9 进度汇报与冷启动说明

**板块跳过时的 TUI 反馈：**

在每个数据获取阶段前检查 board flag，跳过时通过 `ProgressReporter` 输出明确提示，避免用户困惑：

```
[..] 正在获取新闻数据 ...
[板块配置] 新闻板块已关闭，跳过
[..] 正在获取基金经理数据 ...
[板块配置] B 系列已关闭，跳过
[板块配置] 历史走势已关闭，跳过
```

实现方式：`handlers_report.py` 中各条件判断前插入 `progress.update()` 或 `progress.log()`。

**冷启动行为（板块重开后的缓存状态）：**

| 板块 | 关闭期间丢失的缓存 | 重开首次加载影响 | 评估 |
|:-----|:------------------|:----------------|:-----|
| 新闻 | `news_*`（15 分钟 TTL，关闭期间无新缓存写入） | 5 源并行 ~3s | 🔵 **低**——与首次生成无差异 |
| B 系列 | `fund_manager_*`（24h TTL） | ~2s 获取经理数据 | 🔵 **低**——fund_hold 由穿透模块持续维护不受影响 |
| 历史走势 | `history_stock_*`（7d TTL）+ `history_fund_otc_*`（30d TTL） | N×1~2s | 🟠 **中**——关闭 30 天以上所有历史缓存已过期，首次重开需全量重拉，属预期行为 |

注意：F1 持仓快照不受 `enable_history` 影响，始终在 B/L 菜单下自动执行（见 §2.7）。

### 2.10 板块关闭后的序号策略

**核心规则**：报告仅对当前可见的模块重新编排连续序号，隐藏的模块完全从序号序列中移除，不留下空洞。

#### 重新编号实现

**HTML 端**（`_compute_section_visibility()` 返回值改造）：

```python
# 原有：section_numbers = {sec["key"]: sec["number"] for sec in order}  ← 静态序号

# 改为：基于可见性重新编号 + llm_usage 强制末位
visible_list = [sec for sec in order if section_visible_dict.get(sec["key"], False)]
llm_sec = [s for s in visible_list if s["key"] == "llm_usage"]
other_secs = [s for s in visible_list if s["key"] != "llm_usage"]
ordered_visible = other_secs + llm_sec  # llm_usage 始终末位

display_numbers = {}
for idx, sec in enumerate(ordered_visible, start=1):
    display_numbers[sec["key"]] = idx

return display_numbers, section_visible_dict, _sv_fn
```

函数签名不变（返回 `tuple[dict[str, int], dict[str, bool], Any]`），只是第一个返回值从静态序号变为重编号的连续序号。调用方 `write_html_report()` 不需要任何改动，它获取后传递给模板的变量名仍是 `section_numbers`。

**模板影响**：

| 位置 | 现有写法 | 改为 | 改动量 |
|:-----|:---------|:-----|:-------|
| 18 个章节 div CSS order + 标题 | `{{ section_numbers['summary'] }}` | 不变（值已自动变为重编号） | **0 行** |
| 导航栏 | `{{ sec["number"] }}` | `{{ section_numbers[sec["key"]] }}` | **1 行** |

模板只需修改导航栏那一行——所有章节标题和 CSS order 自动受益。

**Excel 端**（`create_sheets()` 改造）：

```python
# 不再调用 set_sheet_title(ws, key, section_order)
# 改为在创建设工作表时直接设置连续序号
visible_count = 0
for sec in section_order:
    if not board_flags.get(sec.get("type", ""), True):
        continue
    if not should_create_sheet(sec, ...):
        continue
    visible_count += 1
    if sec["key"] == "llm_usage":
        continue  # llm_usage 暂不计入，待末位处理
    ws = wb.create_sheet()
    ws.title = f"{visible_count}.{sec['name']}"
    sheets[sec["key"]] = ws

# llm_usage 始终末位
if "llm_usage" in sheets:
    ws = sheets.pop("llm_usage")
    visible_count += 1
    ws.title = f"{visible_count}.{sec['name']}"  # 实际是 llm_usage 的名称
    sheets["llm_usage"] = ws
```

**两种极端情况验证**：

| 场景 | 可见模块 | 序号 |
|:-----|:---------|:----|
| 全开（默认） | 1~5 always + 6~9 B + 10~11 news + 12~15 LLM + 16~17 history + 18 llm_usage | 1, 2, 3, ..., 18 连续（与现有行为一致 ✅） |
| B 关、news 关、history 关 | 1~5 always + 12~15 LLM + 18 llm_usage | 1~5（always）, 6~9（LLM）, 10（llm_usage）连续 |
| 全关（仅 always） | 1~5 always + 18 llm_usage | 1~5（always）, 6（llm_usage） |

注意：B 系列 4 个模块即使数据和板块都可用，它们本身是 4 个独立的 section。重新编号时会为每个模块分配独立的序号。LLM 5 个模块同理。

**与 `report_section_order` 的交互**：

`report_section_order` 配置控制的是"在 `section_order` 列表中各模块的相对排序位置"。重新编号是在渲染时基于这个已排序的列表、再过滤可见模块后做的。所以：

```
report_section_order = {"fund_manager": 1, ...}
→ section_order 列表按此排序：[fund_manager, summary, ...]
→ 渲染时 visible_list 从 section_order 取
→ display_numbers 按 visible_list 中出现的顺序分配
```

用户配置的序号优先级始终高于重新编号：用户设为 1 的模块在 section_order 中排第一，渲染时也获得最小的连续编号。**完全不冲突。**

---

## 3. 迭代计划（8 轮）

### 迭代 1：Config 默认值 + schema

**范围**：`config/_defaults.py`、`config/_core.py`

**内容**：
- `_defaults.py` 中 `_DEFAULT_CONFIG` 新增 3 个字段：`enable_b_series`、`enable_news`、`enable_history`，默认 `true`
- `_core.py` 的 `validate_config()` 中验证：字段存在时必须是 bool；不存在不报错
- `_COMMENTED_TEMPLATE` 中带中文注释

**测试**：
- `test_config.py`：默认值正确性（3 项），旧配置缺失不报错（1 项），非 bool 值拒绝（2 项：null、字符串）

**验收标准**：
- [ ] `_DEFAULT_CONFIG` 包含 3 个新字段且默认 `true`
- [ ] 验证函数接受缺失字段（旧配置升级）
- [ ] 验证函数拒绝非 bool 值（`"yes"`/`1`/`null` 时报错）
- [ ] 验证函数接受 `true`/`false`
- [ ] `_COMMENTED_TEMPLATE` 新字段带中文注释
- [ ] 测试 ≥6 项，全部通过

**可回退**：仅新增的配置默认值，无行为变化。回退只需删除字段。

---

### 迭代 2：Config 读取函数 + TUI 菜单骨架

**范围**：`config/__init__.py`、`handlers_config.py`、`tui_menu.py`

**内容**：
- 新增 `is_enable_b_series(config) -> bool`、`is_enable_news(config) -> bool`、`is_enable_history(config) -> bool`
- 各函数内部逻辑：`config.get(key, True)`，缺失时 logger.debug 记录
- 新增 `_cmd_config_report_boards()` 命令处理函数：
  - 1-3 数字切换 B 系列/新闻/历史走势
  - 切换时写入 config.json（使用 `set_config()`，内部 `tempfile.mkstemp`+`os.replace` 遵守 C3）
  - 切换后显示反馈（含关闭后影响的页签编号和名称）
  - 4=LLM 板块（只读参考），0=返回
- 主菜单注册 `[P]` 配置报告板块可见性

**测试**：
- `test_config.py`：3 个读取函数，字段存在/缺失/非 bool 边界（≥6 项）
- `test_handlers_config.py`：子菜单显示逻辑（≥4 项）
- `test_handlers_config_edge.py`：config.json 写入权限拒绝时友好报错（1 项，标记 `@pytest.mark.edge`）

**验收标准**：
- [ ] 3 个读取函数在字段缺失时返回 `True`，`false` 时返回 `False`
- [ ] 按 `P` 进入子菜单，显示 3 个板块当前状态（✓启用/✗禁用）
- [ ] 按 1/2/3 切换对应板块启停，实时写入 config.json
- [ ] 切换反馈标注具体页签范围
- [ ] 边界：config.json 读取失败时降级默认值并提示，写入失败友好报错
- [ ] 向后兼容：默认值不变
- [ ] 测试 ≥11 项，全部通过

**可回退**：菜单项可移除，读取函数无消费者时不产生行为变化。

---

### 迭代 3：Excel 全板块可见性 + 连续重新编号

**范围**：`report/excel_sheet_factory.py`、`report/excel_generator.py`、`handlers_report.py`

**内容**：

**A. Excel sheet_factory 改造（board 层预过滤 + 连续重新编号）：**
- `create_sheets()` 签名新增 `enable_history: bool = True`、`enable_news: bool = True`
- `should_create_sheet()` 保持现有 data_flag 逻辑不变
- 在 `should_create_sheet()` 之前用内联 board_flags dict 做 board 层预过滤
- **连续重新编号**（见 §2.10）：不再调用 `set_sheet_title()`，改为在创建每个可见模块时按过滤后的可见顺序分配连续序号。`llm_usage` 强制末位（先创建其他可见页签，最后再创建 llm_usage 并赋予最大号）

**实施前必须先确认所有引用点：**
- 执行 `grep -rn "include_b_series" src/python/ src/test/` 确认无遗漏，再改类型签名

**B. generator 改造：**
- `generate_excel_report()` 移除 `include_b_series` 跟随旧 `include_news` 的联动逻辑（`excel_generator.py:62`）
- 签名新增 `enable_b_series`、`enable_news`、`enable_history` 三个独立参数
- ⚠️ `include_b_series` 参数类型从 `bool|None` 改为 `bool`，移除 None 分支。调用方必须传入决定值
- 内部 `enable_b_series = include_b_series`（不再与旧 `include_news` 联动）

**C. handlers 联动（**此轮只做参数传递，不做数据获取条件判断**）：**
- `_cmd_generate_excel()`、`_cmd_generate_both()`、`_cmd_generate_full()` 调用 `is_enable_b_series()`、`is_enable_news()`、`is_enable_history()` 读取配置
- 将配置值传入 `_generate_excel_report()` 和 `write_html_report()`
- `_cmd_generate_both()` 中 F2 数据获取条件 `history.analysis` **不变**（数据获取侧，迭代 5 专门处理）

**测试**：
- `test_excel_sheet_factory.py` 追加：
  - board 层：`create_sheets` 传入 `enable_news=False` + `news_data_available=True`（模拟菜单 B 但配置关闭）→ news 页签**不创建**（1 项，**关键 regression 测试**）
  - 两层模型：板块关 + 数据有 → 不创建；板块开 + 数据无 → 创建（占位逻辑不变）；板块开 + 数据有 → 创建（≥3 项）
  - B 系列脱钩验证：传入 `enable_b_series=True, news_data_available=False` → B 系列页签**创建**（1 项，**关键回归测试**）
  - E 菜单传入 `enable_b_series=False, news_data_available=False` → B 系列页签**不创建**（1 项）
- `test_excel_report_structure.py`：整体结构验证——3 个板块开关各 2 种状态 × 首尾组合（≥3 项）
- `test_excel_sheet_factory.py` 追加重新编号验证：
  - B 关场景：验证页签标题为 `1.投资分析汇总 2.市值核算明细表 3.持仓分类表 4.资产穿透TOP10 5.基金业绩分析 6.财经新闻热点 ...`（连续无空洞，1 项）
  - 全关（仅 always）场景：验证页签标题为 `1.投资分析汇总 ... 5.基金业绩分析 6.LLM API 用量`（llm_usage 末位，1 项）

**验收标准**：
- [ ] `"enable_b_series": false` 时，#6~9 不在 Excel 中创建
- [ ] `"enable_news": false` 时，#10~11 不在 Excel 中创建
- [ ] `"enable_history": false` 时，#16~17 不在 Excel 中创建
- [ ] B 系列不再跟随旧 `include_news`：`enable_news=False`（旧 `include_news=False`）→ 不影响 B 系列页签创建，验证 `enable_b_series=True` 时 B 系列仍创建
- [ ] 旧 `include_b_series` 参数兼容：仍然接受 `bool`，但不接受 `None`
- [ ] 各字段缺省时默认开启（向后兼容，行为不变）
- [ ] E 菜单不受 3 个新字段影响（它原本就不含这些板块；H 已取消）
- [ ] **重新编号**：B 关场景 Excel 页签标题连续无空洞（1→2→...→n，非 1→6→...）
- [ ] **重新编号**：全关（仅 always）场景 llm_usage 页签在最后
- [ ] 测试 ≥15 项，全部通过

**可回退**：不改 HTML 侧（由迭代 4 覆盖）。回退需：恢复 `excel_generator.py:62` 的跟随逻辑 + handlers 恢复旧参数

**风险等级**：高（`include_b_series` 跟随逻辑拆除必须在一次提交中完成，不可分步；handler 和 generator 的修改必须同步）

---

### 迭代 4：HTML 两层可见性模型

**范围**：`report/html_writer.py`

**内容**：
- `write_html_report()` 签名新增 `enable_b_series: bool = True`、`enable_history: bool = True`
- `_compute_section_visibility()` 实现两层模型：

```python
def _compute_section_visibility(
    order, manager_analysis, overlap_matrix,
    concentration_analysis, style_analysis,
    news_data_available: bool,               # data 层：数据是否已获取
    early_warnings,
    llm_data_available: bool,               # data 层：LLM 内容是否成功生成
    # ↓↓↓ board 层新增参数 ↓↓↓
    enable_news: bool = True,        # board 层：配置驱动（不是 news_data_available！）
    enable_b_series: bool = True,
    enable_history: bool = True,
    enable_llm: bool = True,         # board 层：配置驱动（从 enabled_llm 派生）
):
    board_flags = {
        "always":   True,
        "b_series": enable_b_series,
        "news":     enable_news,            # ← 配置字段
        "history":  enable_history,
        "llm":      enable_llm,             # ← board 层
    }
    data_flags = {
        "manager_data":       manager_analysis is not None,
        "overlap_data":       overlap_matrix is not None,
        "concentration_data": concentration_analysis is not None,
        "style_data":         style_analysis is not None,
        "news_data_available":       news_data_available,  # ← data 层（菜单驱动）
        "early_warnings":     bool(early_warnings),
        "llm_enabled":        llm_data_available,         # ← data 层（LLM 生成成功？）
    }
    section_visible_dict = {}
    for sec in order:
        board_ok = board_flags.get(sec["type"], True)
        data_ok = data_flags.get(sec["data_flag"], True) if sec["data_flag"] else True
        section_visible_dict[sec["key"]] = board_ok and data_ok
    ...
```

- `_REPORT_SECTION_DEFAULT` 的 `data_flag` **完全不改动**
- `_cmd_generate_both()` 和 `_cmd_generate_full()` 从 config 读取并传入新参数
- 性能分析：`board_flags` 和 `data_flags` 均为 O(n) 遍历 `section_order`（~18 项），无性能风险
- **连续重新编号**（见 §2.10）：在两层合并计算出 `section_visible_dict` 之后，按可见顺序分配连续序号，`llm_usage` 末位。函数返回值第一个元素从静态 `section_numbers` 改为重编后的 `visible_numbers`：
  ```python
  # 在 section_visible_dict 计算完成后：
  visible_list = [sec for sec in order
                  if section_visible_dict.get(sec["key"], False)]
  llm_sec = [s for s in visible_list if s["key"] == "llm_usage"]
  other_secs = [s for s in visible_list if s["key"] != "llm_usage"]
  ordered_visible = other_secs + llm_sec
  visible_numbers = {sec["key"]: idx for idx, sec in
                    enumerate(ordered_visible, start=1)}
  return visible_numbers, section_visible_dict, _sv_fn
  ```

**模板修改**：`report_template.html` 导航栏 1 行：
```jinja
{# 旧：{{ sec["number"] }}、{{ sec["name"] }} #}
{% if section_visible(sec["key"]) %}
<a href="#sec-{{ sec['key'] }}">{{ section_numbers[sec["key"]] }}、{{ sec["name"] }}</a>
{% endif %}
```
所有 18 处 `{{ section_numbers['key'] }}` 无需改动——值已自动变为重编号。

**测试**：
- `test_html_writer.py` / `test_html_template.py` 追加：
  - 3 个板块开关各 2 种状态 × 2 层组合（4 象限：开+有数据、开+无数据、关+有数据、关+无数据），多板块分多个 fixture（≥6 项）
  - **关键场景**：菜单 B 模拟 + `enable_news=False` → news 板块不可见（验证 board_flags 使用 `enable_news` 而非 `news_data_available`）（2 项）
  - 验证 `section_visible_dict` 中的 expected 值正确（≥6 项）
  - 重新编号验证：`_compute_section_visibility` 返回的 `visible_numbers` 字典中：
    - 全关场景（仅 always + llm）→ 序号 1~6 连续（1 项）
    - llm_usage 在所有场景下都是最大序号（1 项）
  - HTML 导航栏渲染验证：渲染后的 HTML 导航链接序号无空洞（1 项）

**验收标准**：
- [ ] `"enable_news": false` 时 HTML 不渲染新闻章节 #10~11（**含菜单 B 场景**）
- [ ] `"enable_history": false` 时 HTML 不渲染走势回撤章节 #16~17
- [ ] `"enable_b_series": false` 时 HTML 不渲染 B 系列章节 #6~9
- [ ] 板块开 + 数据不可用 → 页签可见（现有占位逻辑不变，不应被 board 层拦截）
- [ ] 板块关 + 数据可用 → 页签不可见（board 层拦截）
- [ ] 各字段缺省时 HTML 渲染正常（向后兼容）
- [ ] `_REPORT_SECTION_DEFAULT` 无任何改动
- [ ] 测试 ≥14 项，全部通过

**可回退**：不改 TUI 菜单。回退只需在 `html_writer.py` 中恢复旧 `_compute_section_visibility()`。

---

### 迭代 5：数据获取条件跳过 + F2 重复代码消除 + 取消 H 菜单

**范围**：`handlers_report.py`、`main.py`、`tui_menu.py`

**内容**：

**A. 取消 H 菜单（先做，简化后续改动点）：**
- 删除 `_cmd_generate_html()` 函数（~25 行）及其在 `main.py` 的键绑定
- 从 `tui_menu.py` 的 `MENU_ITEMS` 中移除 H 行
- 原 H 菜单的 HTML 报告生成能力仍可通过 B 菜单获得（Excel+HTML 同时生成）

**B. 消除重复代码——F2 历史获取 + F1 快照（先做，让后续改动的点从 2 处减为 1 处）：**

- 提取 `_cmd_generate_both()` 和 `_cmd_generate_full()` 中相同的 ~25 行 F2 历史获取代码：
  ```python
  def _fetch_history_data(history_mode: str, holdings: list) -> tuple:
      """提取 F2 历史走势数据获取逻辑，消除重复。"""
      if history_mode not in ("auto", "prompt"):
          return None, None
      # ... 原有的 F2 获取逻辑 ...
      return f_context, history_data
  ```

- 提取两处相同的 ~67 行 F1 快照代码（规模是 F2 的 2.7 倍）：
  ```python
  def _capture_snapshot(holdings, details) -> dict | None:
      """F1 快照创建 + 差异计算 + 保存 + 清理。返回 f_context 或 None。"""
      try:
          _snapshot_holdings = [
              SnapshotHolding(
                  code=d.code, name=getattr(d, "name", ""),
                  shares=0.0, cost_price=0.0,
                  market_value=d.market_value, total_pnl=d.profit, cost_total=d.cost,
              )
              for d in details
          ]
          for h in _snapshot_holdings:
              _orig = next((x for x in holdings if x.code == h.code), None)
              if _orig:
                  object.__setattr__(h, "shares", _orig.shares)
                  object.__setattr__(h, "cost_price", _orig.cost_price)
          _snapshot = SnapshotData(
              accounts=(AccountSnapshot(account_name="全部",
                                        holdings=tuple(_snapshot_holdings)),),
              total_value=sum(d.market_value for d in details),
              total_cost=sum(d.cost for d in details),
              total_pnl=sum(d.profit for d in details),
              timestamp=datetime.now().strftime("%Y%m%dT%H%M%S"),
          )
          _old = load_latest()
          _diff = HistoryDiff.compute(_snapshot, _old)
          save(_snapshot)
          prune(
              retention_days=config.get("history", {}).get("snapshot_retention_days", 60),
              max_count=config.get("history", {}).get("snapshot_max_count", 365),
          )
          if not _diff.is_first_check:
              return {"diff": {...构建差异字典...}, "diff_trimmed": _diff.trimmed,
                      "days_since_last": _diff.days_since_last_report}
          return None
      except Exception:
          logger.info("[F1] 环比数据准备跳过（首次运行或异常）", exc_info=True)
          return None
  ```
  提取后 B/L 两处各从 ~95 行（F1~67 + F2~25 + 条件）精简为 ~5 行调用：`f_context = _capture_snapshot(holdings, details)` + `history_data = _fetch_history_data(...)`。

**C. 数据获取 × Board 交互规则（取消 H 后简化为向下覆盖模型）：**

| 菜单 | 规则 | 实现 |
|:-----|:-----|:------|
| **E** | board **不影响**数据获取（仅输出侧） | 保持现状，不检查任何 board flag |
| **B** | board **向下覆盖**：关→跳过获取 | 每个扩展数据类型检查对应 board flag |
| **L** | board **向下覆盖**：关→跳过获取 | 同 B，额外加 LLM 判断（已有） |

```python
# E 菜单：永远不检查 board flags，只取 core
def _cmd_generate_excel():
    ...
    _generate_excel_report(holdings, news_data_available=False, ...)

# B/L 菜单：board 向下覆盖
def _cmd_generate_both():
    config = get_config_cache() or {}
    enable_b_series = is_enable_b_series(config)
    enable_news     = is_enable_news(config)
    enable_history  = is_enable_history(config)

    # 条件获取，board OFF → 跳过
    if enable_news:
        news_data = build_news_data(...)
    else:
        news_data = None
        logger.info("[板块配置] 新闻板块已关闭，跳过数据获取")

    # 关键：data 层标志反映真实数据状态，而非配置值
    # enable_news=True 但网络/API 失败时 → news_available=False
    # 避免新闻板块"显示但空内容"（两层模型正确拦截）
    news_available = bool(news_data) if enable_news else False

    if enable_b_series:
        manager_data = fetch_fund_manager_data(...)
    else:
        manager_data = None
        logger.info("[板块配置] B 系列已关闭，跳过数据获取")

    _history_mode = config.get("history", {}).get("analysis", "off")
    if enable_history and _history_mode in ("prompt", "auto"):
        f_context, history_data = _fetch_history_data(_history_mode, holdings)
    else:
        logger.info("[板块配置] 历史走势已关闭，跳过数据获取")

    # 输出侧：board 层传 enable_xxx，data 层传真实数据状态
    _generate_excel_report(holdings, news_data_available=news_available,
                           enable_b_series=enable_b_series,
                           enable_news=enable_news,
                           enable_history=enable_history, ...)
    write_html_report(holdings, news_data_available=news_available,
                      enable_b_series=enable_b_series,
                      enable_news=enable_news,
                      enable_history=enable_history, ...)
```

> **关键区分**：`news_data_available`（data 层）传递 `news_available`（真实数据状态），**不是** `enable_news`（配置值）。这确保网络/API 失败时两层模型正确拦截空内容。B 系列和 F2 同理，它们的 data 层标志由内部模块的 `is not None` 判断自行决定。详见 §5 风险表新增项。

**D. TUI 进度汇报联动（见 §2.9）：**
- 每个条件判断前插入 `progress.update()` 或 `progress.log()`，板块关闭时输出 `[板块配置] %s 已关闭，跳过` 进度提示
- 适用于 B/L 菜单

**测试：**
- 验证 `_cmd_generate_html` 已移除（调用 `main()` 时 H 键无响应）（1 项）
- mock `is_enable_news()` 返回 False → 验证 `build_news_data` 未被调用（B/L 菜单下）（1 项）
- mock `is_enable_b_series()` 返回 False → 验证基金经理数据获取未被调用（1 项）
- mock `is_enable_history()` 返回 False → 验证 `_fetch_history_data` 未被调用（1 项）
- 验证 logger.info 被正确调用（计数 ≥3，用 `caplog` 或 `assert_called_with`）（1 项）
- mock `enable_history=True` + `history.analysis="off"` → F2 仍不获取（确保与已有配置的交互正确）（1 项）
- E 菜单下即使 board 全开，验证 `build_news_data` **未被调用**（1 项，E 不受 board 影响）
- 验证 F1 快照在 B/L 菜单下 `enable_history=False` 时仍然执行（mock `SnapshotData.save` 验证）（1 项）
- 验证 `_capture_snapshot()` 提取后 `_cmd_generate_both()` 和 `_cmd_generate_full()` 中 F1 代码已消除重复（调用同一共享函数）（1 项）
- mock `enable_news=True` + `build_news_data()` 返回 None → 验证 `news_data_available=False` 传递到输出侧（data 层正确反映真实状态，非配置值）（1 项）

**验收标准：**
- [x] H 菜单已移除，`_cmd_generate_html()` 函数已删除
- [x] `enable_news: false` → B/L 菜单下新闻数据不获取
- [x] `enable_b_series: false` → B/L 菜单下 B 系列数据不获取
- [x] `enable_history: false` → B/L 菜单下历史走势数据不获取（F2 仅）
- [x] `enable_history: false` 且 `history.analysis="auto"` → 仍不获取（`enabled` 优先级高于 `analysis`）
- [x] E 菜单下即使 board 全开，仍不获取扩展数据（向后兼容）
- [x] F1 快照在 `enable_history=false` 时**仍然执行**（B/L 菜单下）
- [x] 日志可追踪：板块关闭时 log INFO 记录
- [x] F2 历史获取重复代码已消除（`_cmd_generate_both` 和 `_cmd_generate_full` 中调用 `_fetch_history_data()`）
- [x] F1 快照重复代码已消除（`_cmd_generate_both` 和 `_cmd_generate_full` 中调用 `_capture_snapshot()`）
- [x] `news_data_available` 传递真实数据状态（`news_available`）而非配置值（`enable_news`）
- [x] 测试 ≥10 项，全部通过

**可回退**：纯行为修正，不新增接口。回退只需恢复 `handlers_report.py` 中的条件判断、`_capture_snapshot()`、`_fetch_history_data()` 和 `_cmd_generate_html` 函数。

---

### 迭代 6：集成测试 + 边界场景

**范围**：`test/` 各文件

**内容**：

A. Excel + HTML 整体集成（`test_excel_report_structure.py` / `test_html_report_structure.py` 追加）：
- 生成完整报告，修改配置开关，验证页签/章节正确创建或隐藏（≥6 项）

B. 场景测试（`scenario/` 追加，标记 `scenario_basic`）：
- 新增场景：config.json 中 3 个板块全关 → 验证报告只有 always + llm 页签（1 项）
- 新增场景：`enable_b_series=true` + 纯股票组合（无基金）→ B 系列页签不意外出现（1 项，**纯股票回归**）
- 新增场景：`enable_news=false` + 菜单 B → 无新闻页签（1 项，**board 层覆盖 data 层验证**）
- 新增场景：E 菜单下 board 全开 → 验证扩展数据未被获取（1 项，E 不受 board 影响）

C. 边缘测试（`*_edge.py`）：
- config.json 损坏时的降级行为（1 项）
- config.json 写入权限拒绝时 TUI 的友好提示（1 项）
- 读取函数对非预期类型（如 `"enabled": "maybe"`）的 fallback（1 项）
- `enable_history=false` 时验证 F1 snapshot 仍被保存（mock `SnapshotData.save` 验证）（1 项）
- H 菜单已移除，验证按 H 键无响应（1 项）

D. 标记合规验证：
- `python scripts/check-test-markers.py` 无报错
- 新增 marker（如有）注册到 `conftest.py`

**验收标准**：
- [ ] 集成场景：全关模式只产生 always + llm 页签/章节
- [ ] 集成场景：混合开关模式（B 关其余开）验证正确
- [ ] 纯股票 + B 系列开启 → B 系列不意外创建
- [ ] 菜单 B + enable_news=false → 新闻不显示（board 层胜出）
- [ ] E 菜单不受 board 影响：board 全开时 E 仍不获取扩展数据
- [ ] H 菜单已从 UI 中移除，按 H 无响应
- [ ] 边界场景：config.json 损坏时所有板块默认开启
- [ ] 边界场景：TUI 菜单中 config.json 不可写时报友好错误
- [ ] 边界场景：F1 快照在 enable_history=false 时仍然保存
- [ ] 标记合规：`check-test-markers.py` 无报错
- [ ] 测试 ≥15 项，全部通过

**可回退**：纯测试新增，无代码变更。回退只需移除测试用例。

---

### 迭代 7：文档同步

**范围**：`docs-stm/manuals/how-to-config.md`、`docs-stm/manuals/reports-instruction.md`、`docs-stm/managements/changelog.md`

**内容**：
- `how-to-config.md`：
  - config.json JSON 样本新增 3 个字段（在 llm 相关字段附近，分组注释）
  - 字段说明表新增 3 行：默认值 `true`、说明（含所属页签范围）、TUI 修改方式（菜单 P）
  - TUI 菜单说明表新增 `[P] 配置报告板块可见性` 项
  - 注明 `enable_news` 与 `news_sources` 的关系：前者控制板块启停，后者控制数据源启停
- `reports-instruction.md`：
  - "页面/章节分组"节补充配置字段名和开关说明
  - 注明字段缺失时默认开启
- `changelog.md`：v0.4.5 完整记录本次变更

**验收标准**：
- [ ] `how-to-config.md` 4 处更新（JSON 样本 + 字段表 + 菜单表 + news 字段关系说明）
- [ ] `reports-instruction.md` 分组节标注配置字段
- [ ] `changelog.md` v0.4.5 条目
- [ ] 目录树同步检查（`datasource-and-folders.md`）——本次不新增文件，无需更新目录树（无新 .py 文件）

---

### 迭代 8：回归验证 + 发布准备

**范围**：全量验证

**内容**：
- 运行 `python scripts/test_runner.py --mode regression`（业务场景，确保端到端不被破坏）
- 运行 `python scripts/test_runner.py --mode unit`（全量单元测试，确保新增模块无回归）
- 运行 `python scripts/check-version-consistency.py`（版本号一致性）

**验收标准**：
- [ ] regression 模式全部通过
- [ ] unit 模式全部通过
- [ ] `check-version-consistency.py` 无 [ERR]
- [ ] 手工验证：TUI 菜单 P 的 3 个开关 2 种状态，每次生成报告验证对应页签正确显示/隐藏
- [ ] 手工验证：菜单 B + enable_news=false → 新闻不显示
- [ ] 手工验证：纯股票组合 + enable_b_series=true → B 系列不意外显示

---

## 4. 总量估算

| 迭代 | 内容 | 代码量 | 测试项数 | 风险 |
|:-----|:-----|:------|:---------|:-----|
| 1 | Config 默认值 + schema | +15 | 6 | 低 |
| 2 | 读取函数 + TUI 菜单骨架 | +120 | 11 | 低 |
| 3 | Excel 全板块可见性（含 include_b_series 解耦、enable_news 分离） | +55 | 13 | **高**（`include_b_series` 跟随逻辑拆除必须原子提交） |
| 4 | HTML 两层可见性模型（board/data 层分离） | +40 | 14 | 中（`enable_news` vs `news_data_available` 分离） |
| 5 | 取消 H 菜单 + F1/F2 重复消除 + 数据获取条件跳过 + 进度 UX | -52 | 9 | 中 |
| 6 | 集成测试 + 边界场景（含纯股票/F1 快照回归） | +120 | 15+ | 低 |
| 7 | 文档同步 | +35 | — | 低 |
| 8 | 回归验证 | — | — | — |
| **合计** | **8 轮** | **~395** | **~67** | — |

---

## 5. 技术债务评估

| 债务项 | 类型 | 影响 | 本设计处理 |
|:-------|:-----|:-----|:-----------|
| `include_news`（已→`news_data_available`）职责过载（同时控制 news + b_series） | 命名混乱 | 可读性 | ✅ 解耦，b_series 独立；`news_data_available` 仅表 data 层 |
| `include_news`（已→`news_data_available`）误作 board 层判断（旧设计缺陷） | 逻辑错误 | 菜单 B + enable_news=false 误显示 | ✅ board_flags 使用 `enable_news`（配置） |
| `should_create_sheet` 的 type_map 硬编码 type→bool | 僵化性 | 新增 type 需改此函数 | ❌ 不改（type 数稳定在 5，不值得抽象化） |
| `_build_section_visibility()`（应为 `_compute_section_visibility`） | 文档/代码不一致 | 理解困难 | ✅ 已修正函数名引用 |
| F2 历史获取代码重复（`_cmd_generate_both` + `_cmd_generate_full`） | 重复 | 维护成本 | ✅ 提取为 `_fetch_history_data()` |
| `_compute_section_visibility()` 中 data_flag 缺失时自动 True | 隐式默认 | 新增模块忘记设 data_flag 会始终可见 | ⚠️ 现有问题，本迭代不新增 data_flag，不恶化 |
| 配置约束表中 C4、C3 引用不准确 | 文档错误 | 误导读者 | ✅ 已精确引用 `set_config()` 和 `session_cache_get` |
| **H 菜单与 E 功能重叠**（数据范围相同，仅格式不同） | 冗余代码 | 维护成本 + 菜单混淆 | ✅ **已消除**——H 菜单已移除，`_cmd_generate_html()` 已删除 |
