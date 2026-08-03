# 中央注册表（registry）使用说明

## 概述

`src/python/core/registry.py` 是本项目的**中央注册表**，统一管理所有数据模块的：

- **中文名称**（`name`）— 页面、报告、日志中显示的人类可读名称
- **缓存前缀**（`cache_prefixes`）— 缓存文件名的前缀，用于按类型清理/匹配
- **缓存 TTL**（`cache_ttl`）— 每种数据类型默认缓存过期时间
- **精确缓存键**（`exact_cache_keys`）— 无通配前缀的固定缓存文件名
- **LLM Settings 后缀**（`settings_suffix`）— LLM 模块在 `llm_settings.json` 中的键名后缀
- **缓存分组**（`cache_groups`）— 用于按组批量清除缓存的标签

设计原则：**一处注册，全局生效**。新增数据模块只需在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`，所有派生结构自动同步。

> **架构背景**：注册表是数据获取层与报告生成层之间的契约层，详细架构说明见[技术设计文档](../managements/technical.md)。

---

## 核心数据结构

```python
@dataclass(frozen=True)
class DataModuleDef:
    name: str                  # 中文名称（报告标题、日志、TUI 展示）
    data_type: str             # 数据类型键（用于 TTL 查找）
    cache_prefixes: tuple[str, ...] = ()
    exact_cache_keys: tuple[str, ...] = ()
    cache_ttl: float = CACHE_DAILY
    settings_suffix: str | None = None   # None 表示非 LLM 模块
    cache_groups: tuple[str, ...] = ()

    @property
    def is_llm(self) -> bool:
        """是否为 LLM 模块（即有 settings 键名）。"""
        return self.settings_suffix is not None

    def llm_settings_keys(self) -> set[str]:
        """返回该模块的所有 llm_settings.json 合法键名（共 9~10 个键）。"""
        ...
```

> `DataModuleDef` 是不可变的（`frozen=True`），注册后不可修改。
>
> 两个派生成员在新增 LLM 模块时尤为有用：
> - `is_llm` — 自动判断是否为 LLM 模块（`settings_suffix is not None`）
> - `llm_settings_keys()` — 生成该模块在 `llm_settings.json` 中的所有合法键名，新增后可用于配置校验

---

## 注册表结构

见 `core/registry.py` 中 `_MODULE_REGISTRY: tuple[DataModuleDef, ...]` — 当前包含以下几类：

| 分组 | 包含模块 | data_type | TTL | 说明 |
|------|---------|-----------|:---:|------|
| **行情（preload）** | 股票价格、市场指数 | `price`, `index` | 24h（交易时段 30s） | 换持仓后需重新获取 |
| **基金数据（refresh）** | 基金业绩排名、基金持仓 | `rank`, `hold` | 1d~1w | 主动刷新按钮触发 |
| **行业分类（refresh）** | 行业分类 | `industry` | 14天 | 主动刷新触发 |
| **新闻（refresh）** | 新闻聚合 | `news` | 15min | 短 TTL 高频更新 |
| **LLM 模块（preload/refresh）** | 全球政经局势、智囊团复盘、体检报告、穿透分析、财经新闻热点与持仓关联分析 | `llm_global_macro` ~ `llm_news_correlation` | 1h~24h | 带 `settings_suffix` |
| **辩论模式（preload）** | 辩论白脸、辩论黑脸、辩论综合 | `llm_debate_pro`, `llm_debate_con`, `llm_debate_synthesis` | 24h | 实验功能三段独立缓存键（复用 expert_review 指纹）。**仅缓存管理用途**：注册表条目保留供 TTL/前缀清理使用，菜单 [S] 已隐藏，实际启停由 Feature Flag `llm_debate_procon`（正反辩论）控制 |
| **补充数据（refresh）** | 盈利预测、资金流向、分红、无风险利率 | `profit_forecast`, `sector_flow`, `dividend`, `bond_yield` | 15min~30d | 主动刷新触发；`bond_yield` 为精确键名 `bond_yield_rf` |
| **基金深度分析（refresh）** | 基金经理、持仓重合度、基金风格扩展数据 | `fund_manager`, `fund_overlap`, `extended` | 24h~7d | 基金深度分析模块，主动刷新触发 |
| **基金深度分析（无分组）** | 集中度历史快照、风格快照 | `fund_concentration`, `fund_style_snapshot` | 30d | 精确键名，不被清除操作命中 |
| **历史走势类（无分组）** | 历史股票日线、历史基金净值、指数历史日线 | `history_stock`, `history_fund_otc`, `history_index` | 1w~1M | 无分组保护，不被菜单缓存命令误删，通过 `portfolio_history.py` 内部路由自动管理 |
| **精确键名（含 refresh）** | 基金业绩基准、持仓跟踪、交易日历 | `benchmark`, `tracking`, `calendar` | 2w~1M | `benchmark` 归入 `refresh` 组，`tracking`/`calendar` 无分组 |

---

## 公共 API

### 遍历与查询

```python
from src.python.core.registry import get_registry

registry = get_registry()            # → tuple[DataModuleDef, ...]
for m in registry:
    print(m.name, m.data_type, m.cache_ttl)
```

### 缓存相关

```python
from src.python.core.registry import (
    get_cache_ttl_defaults,          # → dict[data_type → ttl]
    get_prefix_type_map,             # → dict[prefix → data_type]
    get_exact_type_map,              # → dict[exact_key → data_type]
    get_registered_data_types,       # → set[data_type]
)
```

**用途：**
- `get_cache_ttl_defaults()` — `config/_config_defaults.py` 用于默认配置模板生成
- `get_prefix_type_map()` — `cache/_cleanup.py` 的 `cleanup_expired()` 按文件名前缀推断类型
- `get_exact_type_map()` — `cache/_cleanup.py` 清理精确键名缓存文件
- `get_registered_data_types()` — 校验/测试用

### LLM 模块名称查询

```python
from src.python.core.registry import (
    get_llm_module_name,             # suffix → 中文名称
    get_llm_module_names,            # → dict[suffix → 名称]
)
```

**用途：**
- `get_llm_module_name("expert_review")` → `"智囊团深度复盘"`
- `get_llm_module_names()` → `{"global_macro": "全球政经局势", "expert_review": "智囊团深度复盘", ...}`
- 可选 suffix：`global_macro`, `expert_review`, `health_check`, `penetration_deep`, `news_correlation`（另含缓存管理保留条目 `debate_pro`/`debate_con`/`debate_synthesis`，已在菜单层隐藏）

### LLM Settings 键名查询

```python
from src.python.core.registry import (
    get_known_llm_settings_keys,     # → set[str]
)
```

**用途：**
- 返回 `llm_settings.json` 中所有合法配置键名，用于配置校验

### enabled_llm 子键查询

```python
from src.python.core.registry import (
    get_known_enabled_llm_keys,      # → set[str]
)
```

**用途：**
- 返回 `llm_settings.json` → `enabled_llm` 字典的所有合法子键（即各 LLM 模块的 `settings_suffix`：`global_macro` / `expert_review` / `health_check` / `penetration_deep` / `news_correlation`，另含缓存管理保留条目 `debate_pro` / `debate_con` / `debate_synthesis`），用于 `_validate_enable_llm()` 的子键拼写校验

### 报表排序与页签名称

```python
from src.python.core.registry import (
    get_report_sheet_name,           # sheet_key → 中文标题
    get_report_section_order,        # config → list[dict]（含 key/number/type/data_flag 的完整排序列表）
    get_report_section_number,       # key → 当前配置下的序号
    get_report_section_keys,         # → list[key]
)
```

**用途：**
- `get_report_sheet_name("summary")` → `"投资分析汇总"`
- `get_report_section_order(config)` → 解析 `report_section_order` 配置，返回有序键列表
- `get_report_section_number("fund_manager")` → 当前配置下该模块的序号（被基金深度分析各页签写入器调用）
- `get_report_section_keys()` → 全部 21 个模块键名（见下表）

全部键名及对应中文标题：

| 键名 | 中文标题 | 说明 |
|------|---------|:----:|
| `summary` | 投资分析汇总 | 始终显示 |
| `market_value` | 市值核算明细表 | 始终显示 |
| `category` | 持仓分类表 | 始终显示 |
| `penetration` | 资产穿透TOP10 | 始终显示 |
| `fund_performance` | 基金业绩分析 | 始终显示 |
| `fund_manager` | 基金经理变更监控 | 基金深度分析 |
| `fund_overlap` | 持仓重合度矩阵 | 基金深度分析 |
| `fund_concentration` | 持仓集中度监控 | 基金深度分析 |
| `fund_style` | 基金风格分析 | 基金深度分析 |
| `factor_exposure` | 因子暴露分析 | 基金深度分析 |
| `correlation_analysis` | 持仓相关性矩阵 | 基金深度分析 |
| `news_correlation` | 财经新闻热点与持仓关联分析 | 新闻 |
| `global_macro` | 全球政经局势 | LLM |
| `expert_review` | 智囊团深度复盘 | LLM |
| `health_check` | 持仓体检报告 | LLM |
| `penetration_deep` | 穿透深度分析 | LLM |
| `portfolio_history` | 组合历史走势 | 历史走势 |
| `drawdown_analysis` | 历史回撤分析 | 历史走势 |
| `portfolio_evolution` | 组合演进 | 独立开关（`enable_portfolio_evolution`，数据不可用时占位） |
| `data_source_status` | 数据源可用性矩阵 | 始终显示 |
| `llm_usage` | LLM API 用量 | LLM（强制末位） |

> LLM 模块（`global_macro`/`expert_review`/`health_check`/`penetration_deep`/`news_correlation`）的页签标题统一通过 `get_llm_module_name(settings_suffix)` 获取；`llm_usage` 的序号和名称也在 registry 中注册，内容（Token/费用数据）由程序动态计算。

完整 21 模块默认序号列表见 [配置指南→report_section_order](how-to-config.md#report_section_order-报告序号配置)，用户可通过该字段自定义排序。

### 计算模块查询

```python
from src.python.core.registry import (
    get_computation_registry,        # → tuple[ComputModuleDef, ...]
    get_computation_module,          # module_key → ComputModuleDef | None
)
```

**用途：**
- `get_computation_registry()` — 遍历所有计算/分析模块（量化指标、流动性分析、外汇敞口、情景分析、组合校准、用户画像、事实校验器），用于运行时发现和文档生成
- `get_computation_module("analytics_metrics")` → 按 module_key 查找单个计算模块定义

当前注册的计算模块见 §计算模块注册表。

---

## 消费方清单（代表性）

| 消费方 | 调用的 API | 用途 |
|--------|-----------|------|
| `config/_core.py` | `get_known_llm_settings_keys()`, `get_report_section_keys()` | 配置校验 |
| `cache/_ttl.py` | `get_cache_ttl_defaults()` | TTL 运行时解析 |
| `cache/_cleanup.py` | `get_prefix_type_map()`, `get_exact_type_map()` | 过期缓存清理 |
| `cache/_groups.py` | `get_registry()` | 按组批量清除缓存 |
| `llm/generators_orchestrator.py` | `get_llm_module_name()`, `get_llm_module_names()` | LLM 调度标签 |
| `llm/skeleton.py` | `get_llm_module_name()` | LLM 骨架消息映射 |
| `report/orchestrator.py` | `get_llm_module_name()`, `get_report_section_order()` | 报告生成编排（LLM 模块标签 + 页签排序） |
| `tui/handlers_config.py` | `get_llm_module_names()` | 菜单 S LLM 配置展示（经 `filter_menu_llm_modules()` 过滤隐藏辩论三模块） |
| `report/excel_generator.py` | `get_report_section_order()` | Excel 页签排序 |
| `report/html_writer.py` | `get_llm_module_name()`, `get_llm_module_names()` | HTML 模板注入 |
| `report/llm_module_info.py` | `get_llm_module_names()` | 构建模块状态/Token用量/费用信息 |
| `report/excel_llm_usage.py` | `build_llm_module_info()`（→ `llm_module_info.py` 间接调用） | LLM API 用量页签写入 |

> 完整列表：除上表外，各页签写入器（`summary.py`、`market_value_sheet.py`、`category.py` 等）均调用 `get_report_sheet_name()` 获取页签名。新增模块在 `_MODULE_REGISTRY` 注册后自动同步到所有消费方。

---

## 如何新增模块

### 新增非 LLM 数据缓存模块

在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`：

```python
DataModuleDef("我的中文名称", "my_data_type",
              cache_prefixes=("mydata_",),
              cache_ttl=CACHE_DAILY,
              cache_groups=("refresh",)),
```

- `name` — 中文显示名
- `data_type` — 内部标识键，需唯一
- `cache_prefixes` — 缓存文件名前缀（可多个），清理时按前缀匹配。**注意：长前缀需排在短前缀之前**，否则短前缀可能先匹配（如 `"llm_"` 会误匹配 `"llm_global_macro_"`）。实际声明时所有 LLM 模块均已使用完整长前缀，无歧义
- `cache_ttl` — 使用 `CACHE_DAILY` / `CACHE_WEEKLY` / `CACHE_MONTHLY` 或自定义秒数
- `cache_groups` — `"preload"`（换持仓需重取）或 `"refresh"`（主动刷新按钮触发）；**留空 `()` 表示不被任何组清除操作命中**（如 `tracking`、`calendar` 等安全设计）

### 新增 LLM 分析模块

除上述字段外，还需设置 `settings_suffix`：

```python
DataModuleDef("我的 LLM 分析", "llm_my_analysis",
              cache_prefixes=("llm_my_analysis_",),
              cache_ttl=7200,
              settings_suffix="my_analysis",
              cache_groups=("preload",)),
```

添加后还需在以下位置补充配套代码：

1. **`llm_settings.json`** — 新增同名配置键组，键名为 `{model|temperature|...}_{my_analysis}`，共 9~10 个键（`news_correlation` 不含 `output_brief`）
2. **`llm/generators.py`** — 添加 LLM 调用函数，如 `generate_new_module()`
3. **`llm/generators_orchestrator.py`** — 在 `_MODULE_FNS` 字典中注册新模块的生成函数，同时在 `_compute_module_cache_info()` 中添加对应的指纹和缓存信息计算逻辑
4. **`report/llm_content.py`** — 在 `write_llm_sheets()` 的 `_module_keys` 和 `_module_contents` 列表中追加新模块键名及对应内容变量
5. **`llm/__init__.py`** — 将新生成函数加入 `__all__` 供外部导入

#### 新增 LLM 模块检查清单

| # | 步骤 | 操作位置 | 产出 |
|---|------|---------|------|
| ① | **注册模块定义** | `core/registry.py` → `_MODULE_REGISTRY` | 添加 `DataModuleDef` 实例，含 `settings_suffix` |
| ② | **配置 JSON 键组** | `llm_settings.json` | 新增 9~10 个 `{key}_{suffix}` 配置键 |
| ③ | **实现生成函数** | `llm/generators.py` | 新增生成函数，通过 `_call_llm()` 调用 LLM |
| ④ | **注册调度入口** | `llm/generators_orchestrator.py` | 在 `_MODULE_FNS` 字典中添加新模块条目（键=settings_suffix，值=lambda 调用新函数）；在 `_compute_module_cache_info()` 中添加对应的指纹计算和 `info` 条目 |
| ⑤ | **添加报告页签** | `report/llm_content.py` | 在 `write_llm_sheets()` 的 `_module_keys` 和 `_module_contents` 列表中添加新模块键名 |
| ⑥ | **暴露导出接口** | `llm/__init__.py` | 将新生成函数加入 `__all__` |
| ⑦ | **运行注册表测试** | 终端 | `pytest src/test/unit/core/test_registry.py -v` — 验证 TTL/前缀/键名完整性 |
| ⑧ | **验证标记合规** | 终端 | `python scripts/check-test-markers.py` — 确认测试文件标记无遗漏 |

> **LLM 模块补充步骤**：在上述 registry 清单基础上，新增 LLM 模块还需完成以下领域特定的步骤：

| # | 步骤 | 操作位置 | 产出 |
|---|------|---------|------|
| ⑨ | **添加系统提示词** | `llm/prompts.py` | 新增 `_SYSTEM_{MODULE}` 常量和提示词构建函数 |
| ⑩ | **适配报告模板** | `report/html_writer.py`（HTML）+ `report/llm_content.py`（Excel） | 新章节在两种报告中正确渲染 |
| ⑪ | **配置缓存 TTL** | `data/config/config.json` → `cache_ttl` | 添加 `llm_{module}` 条目 |
| ⑫ | **更新用户文档** | `llm_settings.json` 加入推荐默认值 + 更新配置指南 | 用户可查阅和配置 |

### 精确键名缓存（无前缀匹配）

```python
DataModuleDef("我的固定键", "fixed",
              exact_cache_keys=("my_special_cache",),
              cache_ttl=CACHE_WEEKLY),
```

精确键名不会被前缀通配误匹配，适合固定文件名的缓存。

---

## 计算模块注册表（_COMPUTATION_REGISTRY）

除 `_MODULE_REGISTRY`（有缓存的数据模块）外，`core/registry.py` 还维护 `_COMPUTATION_REGISTRY`——纯计算模块（无缓存）的注册表。

```python
@dataclass(frozen=True)
class ComputModuleDef:
    name: str               # 中文名称
    module_key: str          # 唯一键，如 "analytics_liquidity"
    label: str               # 短标签（日志/提示）
    dependencies: tuple      # 前置数据模块键名
    description: str         # 功能说明
```

当前已注册的计算模块：

| module_key | 名称 | 依赖 | 状态 |
|:-----------|:-----|:-----|:----:|
| `analytics_metrics` | 量化指标 | bond_yield, history | ✅ implemented |
| `analytics_liquidity` | 流动性分析 | — | ✅ implemented |
| `analytics_fx_exposure` | 外汇敞口分析 | — | ✅ implemented |
| `analytics_scenario` | 情景分析 | history | ✅ implemented |
| `analytics_alignment` | 组合校准分析 | — | ✅ implemented |
| `analytics_inferrer` | 用户画像推断 | — | ⏳ planned |
| `analytics_fact_checker` | 事实锚定校验器 | — | ✅ implemented |

新增计算模块只需在 `_COMPUTATION_REGISTRY` 中添加一行 `ComputModuleDef`，纯算法模块无需缓存注册。

---

## 无需手动维护的派生产出

以下映射由 registry 自动派生，**新增模块时只需在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`，即可自动同步到以下所有位置**：

- 缓存 TTL 默认值 → `get_cache_ttl_defaults()`
- 缓存前缀/精确键名映射 → `get_prefix_type_map()` / `get_exact_type_map()`
- LLM settings 键名 → `get_known_llm_settings_keys()`
- LLM 模块名称 → `get_llm_module_names()`
- 报表页签标题 → `create_sheets()` 内联连续重新编号, `get_report_sheet_name()`
- Excel 生成器标签 → `get_report_sheet_name()` / `get_report_section_order()`

---

## 测试

registry 的测试在 `src/test/unit/core/test_registry.py`，验证：

- TTL 默认值完整性
- 前缀类型映射一致性
- 精确键名映射
- LLM settings keys 与模块列表匹配
- 所有 LLM 模块都有 settings_suffix
- 缓存分组标记完整性

运行：`pytest src/test/unit/core/test_registry.py -v`
