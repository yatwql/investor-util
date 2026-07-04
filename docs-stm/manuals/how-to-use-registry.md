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

见 `registry.py` 中 `_MODULE_REGISTRY: tuple[DataModuleDef, ...]` — 当前包含以下几类：

| 分组 | 包含模块 | data_type | TTL | 说明 |
|------|---------|-----------|:---:|------|
| **行情（preload）** | 股票价格、市场指数 | `price`, `index` | 24h（交易时段 30s） | 换持仓后需重新获取 |
| **基金数据（refresh）** | 基金业绩排名、基金持仓 | `rank`, `hold` | 1d~1w | 主动刷新按钮触发 |
| **行业分类（refresh）** | 行业分类 | `industry` | 1w | 主动刷新触发 |
| **新闻（refresh）** | 新闻聚合 | `news` | 15min | 短 TTL 高频更新 |
| **LLM 模块（preload/refresh）** | 全球政经局势、智囊团复盘、体检报告、穿透分析、财经新闻热点与持仓关联分析 | `llm_global_macro` ~ `llm_news_correlation` | 1h~24h | 带 `settings_suffix` |
| **补充数据（refresh）** | 盈利预测、资金流向、分红 | `profit_forecast`, `sector_flow`, `dividend` | 15min~1M | 主动刷新触发 |
| **基金深度分析（refresh）** | 基金经理、持仓重合度 | `fund_manager`, `fund_overlap` | 24h~7d | B 迭代模块，主动刷新触发 |
| **基金深度分析（无分组）** | 集中度历史快照、风格快照 | `fund_concentration`, `fund_style_snapshot` | 30d | 精确键名，不被清除操作命中 |
| **精确键名** | 基金业绩基准、持仓跟踪、交易日历 | `benchmark`, `tracking`, `calendar` | 2w~1M | 固定键名，非前缀匹配 |

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
| — | 财经新闻热点与持仓关联分析（通过 `get_llm_module_name("news_correlation")` 获取标题） | 6. |
| `early_warning` | 智能预警 | 7. |
| — | 基金经理变更监控 | 13. |
| — | 持仓重合度矩阵 | 14. |
| — | 持仓集中度监控 | 15. |
| — | 基金风格分析 | 16. |
| — | LLM 分析模块（4 个页签，见下表） | 8. |
| — | LLM API 用量 | 12.（注） |

第 8 号位置为 LLM 分析模块页签区，共 4 个页签，按 `write_llm_sheets()` 写入顺序排列：

| 页签内容 | 对应 `settings_suffix` | Excel 子序号 |
|---------|----------------------|:-----------:|
| 全球政经局势 | `global_macro` | 8.1 |
| 智囊团深度复盘 | `expert_review` | 8.2 |
| 持仓体检报告 | `health_check` | 8.3 |
| 穿透深度分析 | `penetration_deep` | 8.4 |

> LLM 模块页签标题通过 `get_llm_module_name(settings_suffix)` 获取，无需在 `get_report_sheet_name()` 中录入。第 6 号的新闻页签虽使用 `get_llm_module_name("news_correlation")` 获取标题，但它独立于 LLM 分析模块区（第 8 号），在新闻数据就绪时写入。第 12 号的 LLM API 用量页签为程序生成，不依赖 registry。
> 
> **关于序号**：上表中 Excel 序号为页签标题中的编号前缀。因 B 模块页签（13-16）在 LLM 页签（8-12）之前创建、LLM 页签通过 `wb.create_sheet()` 默认追加到末尾，实际物理排序为 1-7→13-16→8-11→12，非严格递增。参见 [R-155](../managements/review-findings.md#r-155-excel-页签排序错位)。

---

## 消费方清单

registry 的派生产出被以下模块消费：

| 消费方 | 调用的 API | 用途 |
|--------|-----------|------|
| `src/python/config.py` | `get_cache_ttl_defaults()`, `get_known_llm_settings_keys()` | 配置校验 + TTL 兜底 |
| `src/python/cache.py` | `get_prefix_type_map()`, `get_exact_type_map()`, `get_cache_ttl_defaults()`, `get_registry()` | 缓存清理 |
| `src/python/llm/generators.py` | `get_llm_module_names()`, `_MN()` | 模块标签路由、日志 |
| `src/python/llm/skeleton.py` | `get_llm_module_name()` | LLM 骨架模块消息映射 |
| `src/python/main.py` | `get_llm_module_names()` | 菜单显示 |
| `src/python/tui_menu.py` | `get_llm_module_names()` | LLM 配置状态展示 |
| `src/python/tui_handlers.py` | `get_llm_module_name()` | TUI 输出框标题 |
| `src/python/handlers_report.py` | `get_llm_module_name()` | LLM 模块失败标签、报告生成 |
| `src/python/handlers_config.py` | `get_llm_module_names()` | 菜单 S LLM 模块配置展示 |
| `src/python/report/llm_content.py` | `get_registry()`, `get_llm_module_name()` | Excel LLM 分析章节生成 |
| `src/python/report/news_correlation.py` | `get_llm_module_name()` | 新闻页签标题 |
| `src/python/report/excel_generator.py` | `get_llm_module_name()`, `get_report_sheet_name()` | 错误提示、`_Timer`/`_call_sheet` 标签 |
| `src/python/report/html_writer.py` | `get_llm_module_name()`, `get_llm_module_names()` | HTML 模板注入、日志 |
| `src/python/report/summary.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/market_value.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/category.py` | `get_report_sheet_name()` | 页签标题 |
| `src/python/report/penetration_sheet.py` | `get_llm_module_name()`, `get_report_sheet_name()` | 穿透 sheet 写入 |
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

1. **`llm_settings.json`** — 新增同名配置键组，键名为 `{model|temperature|...}_{my_analysis}`，共 10 个键
2. **`llm/generators.py`** — 添加 LLM 调用函数，调用 `_call_llm("my_analysis", context)` 并处理返回
3. **`report/llm_content.py`** — 在 `write_llm_sheets()` 中注册新页签，调用 generators 中的新函数写入对应单元格
4. **`llm/__init__.py`** — 将新生成函数加入 `__all__` 供外部导入

#### 新增 LLM 模块检查清单

| # | 步骤 | 操作位置 | 产出 |
|---|------|---------|------|
| ① | **注册模块定义** | `registry.py` → `_MODULE_REGISTRY` | 添加 `DataModuleDef` 实例，含 `settings_suffix` |
| ② | **配置 JSON 键组** | `llm_settings.json` | 新增 9~10 个 `{key}_{suffix}` 配置键 |
| ③ | **实现生成函数** | `llm/generators.py` | 新增异步生成函数，通过 `_call_llm()` 调用 LLM |
| ④ | **添加报告页签** | `report/llm_content.py` | 在 `write_llm_sheets()` 中注册新 sheet 并写入结果 |
| ⑤ | **暴露导出接口** | `llm/__init__.py` | 将新生成函数加入 `__all__` |
| ⑥ | **运行注册表测试** | 终端 | `pytest src/test/unit/core/test_registry.py -v` — 验证 TTL/前缀/键名完整性 |
| ⑦ | **验证标记合规** | 终端 | `python scripts/check-test-markers.py` — 确认测试文件标记无遗漏 |

### 精确键名缓存（无前缀匹配）

```python
DataModuleDef("我的固定键", "fixed",
              exact_cache_keys=("my_special_cache",),
              cache_ttl=CACHE_WEEKLY),
```

精确键名不会被前缀通配误匹配，适合固定文件名的缓存。

---

## 无需手动维护的派生产出

以下映射原分散在多个文件中硬编码维护，现已统一由 registry 自动派生，**新增模块时只需在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`，无需再手动维护以下任一位置**：

- 缓存 TTL 默认值（原 `constants.CACHE_TTL_DEFAULTS`）→ `get_cache_ttl_defaults()`
- 缓存前缀/精确键名映射（原 `cache.prefix_type_map` / `exact_map`）→ `get_prefix_type_map()` / `get_exact_type_map()`
- LLM settings 键名（原 `config._KNOWN_LLM_SETTINGS_KEYS`）→ `get_known_llm_settings_keys()`
- LLM 模块名称（原 `generators._label_map`、`tui_menu._MODULE_DISPLAY`）→ `get_llm_module_names()`
- 报表页签标题（原 6 处 `ws.title` + `write_title_row`）→ `get_report_sheet_name()`
- Excel 生成器标签（原 12 处 `_Timer`/`_call_sheet` 硬编码）→ `get_report_sheet_name()`

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
