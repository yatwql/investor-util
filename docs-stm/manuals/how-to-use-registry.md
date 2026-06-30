# 中央注册表（registry）使用说明

## 概述

`src/python/registry.py` 是本项目的**中央注册表**，统一管理所有数据模块的：

- **中文名称**（`name`）— 页面、报告、日志中显示的人类可读名称
- **缓存前缀**（`cache_prefixes`）— 缓存文件名的前缀，用于按类型清理/匹配
- **缓存 TTL**（`cache_ttl`）— 每种数据类型默认缓存过期时间
- **精确缓存键**（`exact_cache_keys`）— 无通配前缀的固定缓存文件名
- **LLM Settings 后缀**（`settings_suffix`）— LLM 模块在 `llm_settings.json` 中的键名后缀
- **缓存分组**（`cache_groups`）— 用于按组批量清除缓存的标签

设计原则：**一处注册，全局生效**。新增数据模块只需在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`，所有派生结构自动同步。

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
```

> `DataModuleDef` 是不可变的（`frozen=True`），注册后不可修改。

---

## 注册表结构

见 `registry.py` 中 `_MODULE_REGISTRY: tuple[DataModuleDef, ...]` — 当前包含以下几类：

| 分组 | 包含模块 | TTL | 说明 |
|------|---------|-----|------|
| **行情（preload）** | 股票价格、市场指数、LLM 四大分析模块 | 2h~24h | 换持仓后需重新获取 |
| **基金数据（refresh）** | 基金业绩排名、基金持仓 | 1d~1w | 主动刷新按钮触发 |
| **新闻（refresh）** | 新闻聚合 | 15min | 短 TTL 高频更新 |
| **行业/补充（refresh）** | 行业分类、盈利预测、资金流向、分红 | 15min~1M | 主动刷新触发 |
| **精确键名** | 基金业绩基准、持仓跟踪、交易日历 | 2w~1M | 固定键名，非前缀匹配 |
| **LLM 模块（preload/refresh）** | 全球政经局势、智囊团复盘、体检报告、穿透分析、新闻关联 | 2h~24h | 带 `settings_suffix` |

---

## 公共 API

### 遍历与查询

```python
from src.python.registry import get_registry

registry = get_registry()            # → tuple[DataModuleDef, ...]
for m in registry:
    print(m.name, m.data_type, m.cache_ttl)
```

### 缓存相关

```python
from src.python.registry import (
    get_cache_ttl_defaults,          # → dict[data_type → ttl]
    get_prefix_type_map,             # → dict[prefix → data_type]
    get_exact_type_map,              # → dict[exact_key → data_type]
    get_registered_data_types,       # → set[data_type]
)
```

**用途：**
- `get_cache_ttl_defaults()` — `config.py` 用于计算配置 override 后的最终 TTL
- `get_prefix_type_map()` — `cache.py` 的 `cleanup_expired()` 按文件名前缀推断类型
- `get_exact_type_map()` — `cache.py` 清理精确键名缓存文件
- `get_registered_data_types()` — 校验/测试用

### 报表页签名称查找

```python
from src.python.registry import (
    get_report_sheet_name,             # sheet_key → 中文标题
)
```

**用途：**
- `get_report_sheet_name("summary")` → `"投资分析汇总"`
- `get_report_sheet_name("penetration")` → `"资产穿透TOP10"`
- 可选键名：`summary`, `market_value`, `category`, `penetration`, `fund_performance`, `early_warning`

| 键名 | 中文标题 | Excel 序号 |
|------|---------|-----------|
| `summary` | 投资分析汇总 | 1. |
| `market_value` | 市值核算明细表 | 2. |
| `category` | 持仓分类表 | 3. |
| `penetration` | 资产穿透TOP10 | 4. |
| `fund_performance` | 基金业绩分析 | 5. |
| `early_warning` | 智能预警 | 7. |

> LLM 模块页签（global_macro/expert_review/health_check/penetration_deep）和 news_correlation 的标题已通过 `get_llm_module_name()` 注册，无需再次录入。

---

## 消费方清单

registry 的派生产出被以下模块消费：

| 消费方 | 调用的 API | 用途 |
|--------|-----------|------|
| `src/python/config.py` | `get_cache_ttl_defaults()`, `get_known_llm_settings_keys()` | 配置校验 + TTL 兜底 |
| `src/python/cache.py` | `get_prefix_type_map()`, `get_exact_type_map()`, `get_cache_ttl_defaults()` | 缓存清理 |
| `src/python/llm/generators.py` | `get_llm_module_names()`, `_MN()` | 模块标签路由、日志 |
| `src/python/main.py` | `get_llm_module_names()` | 菜单显示 |
| `src/python/tui_menu.py` | `get_llm_module_names()` | LLM 配置状态展示 |
| `src/python/tui_handlers.py` | `get_llm_module_name()` | TUI 输出框标题 |
| `src/python/handlers_report.py` | `get_llm_module_name()` | LLM 模块失败标签、报告生成 |
| `src/python/report/llm_content.py` | `get_registry()`, `get_llm_module_name()` | Excel LLM 分析章节生成 |
| `src/python/report/news_correlation.py` | `get_llm_module_name()` | 新闻页签标题 |
| `src/python/report/excel_generator.py` | `get_llm_module_name()`, `get_report_sheet_name()` | 错误提示、`_Timer`/`_call_sheet` 标签 |
| `src/python/report/html_writer.py` | `get_llm_module_name()`, `get_llm_module_names()` | HTML 模板注入、日志 |
| `src/python/report/summary.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/market_value.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/category.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/penetration.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/fund_performance.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/early_warning.py` | `get_report_sheet_name()` | 页签标题 |

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
- `cache_prefixes` — 缓存文件名前缀（可多个），清理时按前缀匹配
- `cache_ttl` — 使用 `CACHE_DAILY` / `CACHE_WEEKLY` / `CACHE_MONTHLY` 或自定义秒数
- `cache_groups` — `"preload"`（换持仓需重取）或 `"refresh"`（主动刷新按钮触发）；新模块如不希望被任何组清除则不填

### 新增 LLM 分析模块

除上述字段外，还需设置 `settings_suffix`：

```python
DataModuleDef("我的 LLM 分析", "llm_my_analysis",
              cache_prefixes=("llm_my_analysis_",),
              cache_ttl=7200,
              settings_suffix="my_analysis",
              cache_groups=("preload",)),
```

添加后需补充：

1. **`llm_settings.json`** — 添加 `model_my_analysis`、`temperature_my_analysis` 等 10 个配置键
2. **`llm/generators.py`** — 添加 LLM 调用函数
3. **`report/llm_content.py`** — 在 `write_llm_sheets()` 中添加新页签
4. **`llm/__init__.py`** — 若需要 export 新生成函数

### 精确键名缓存（无前缀匹配）

```python
DataModuleDef("我的固定键", "fixed",
              exact_cache_keys=("my_special_cache",),
              cache_ttl=CACHE_WEEKLY),
```

精确键名不会被前缀通配误匹配，适合固定文件名的缓存。

---

## 无需手动维护的派生产出

以下映射**不再**需要手动维护，均由 registry 自动派生：

| 历史位置 | 已迁移到 registry |
|---------|------------------|
| `constants.py` → `CACHE_TTL_DEFAULTS` | `get_cache_ttl_defaults()` |
| `cache.py` → `prefix_type_map` | `get_prefix_type_map()` |
| `cache.py` → `exact_map` | `get_exact_type_map()` |
| `config.py` → `_KNOWN_LLM_SETTINGS_KEYS` | `get_known_llm_settings_keys()` |
| `generators.py` → `_label_map` | `get_llm_module_names()` |
| `tui_menu.py` → `_MODULE_DISPLAY` | `get_llm_module_names()` |
| `llm_content.py` → `_MODULE_KEY_MAP` 硬编码 | `_get_module_key_map()` via `get_registry()` |
| `tui_menu.py` → 内联 print 模块名 | `get_llm_module_names()` 循环 |
| `summary.py/market_value.py/...` → 6 处硬编码 `ws.title` + `write_title_row` | `get_report_sheet_name()` |
| `excel_generator.py` → 12 处硬编码 `_Timer`/`_call_sheet` 标签 | `get_report_sheet_name()` |

> 新增模块时 **只需修改 registry.py**，上述所有派生产出自动同步。

---

## 测试

registry 的测试在 `src/test/test_registry.py`，验证：

- TTL 默认值完整性
- 前缀类型映射一致性
- 精确键名映射
- LLM settings keys 与模块列表匹配
- 所有 LLM 模块都有 settings_suffix
- 缓存分组标记完整性

运行：`pytest src/test/test_registry.py -v`
