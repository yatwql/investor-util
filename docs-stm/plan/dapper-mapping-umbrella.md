# 实现计划：智能预警 + P1 优化

## 背景

用户要求：
1. 实现 **D. 智能预警**（行业资金流向联动 + 新闻情绪聚合）
2. 一并完成 **P1 代码优化**（`_sanitize_endpoint` 去重、`cache.set()` 去重、`fetch_market_data()` 复用 fallback）
3. 将 P2 优化项（4-7）记入 plan.md 未来迭代计划

---

## 一、P1 优化（3 项）

### P1-1：`_sanitize_endpoint` 去重

**现状**：`llm/prompts.py` 第 187-192 行定义了一份完全相同的 `_sanitize_endpoint()`，且该函数在 `prompts.py` 中**无人调用**（是死代码），仅在其 `__all__` 中被列出并通过 `content.py` 的 `from prompts import *` 重新导出。而 `llm_client.py` 第 50 行已从 `api.py` 导出了同一函数。

**操作**：
- 从 `llm/prompts.py` 删除 `_sanitize_endpoint` 函数（187-192 行）
- 从 `llm/prompts.py` 的 `__all__` 中删除 `"_sanitize_endpoint"`（第 18 行）
- `api.py` 中的版本保持不动

**测试**：无测试覆盖此函数，删除安全。

### P1-2：`cache.py` `set()` 写入逻辑去重

**现状**：`set()` 方法（第 101-200 行）中，主写入路径（130-151 行）和 `FileNotFoundError` 重试块（163-184 行）有 **21 行完全相同的原子写入逻辑**（gzip 判断 → 写临时文件 → `os.replace` → `PermissionError` 兜底 → 清理旧格式文件）。

**操作**：
- 提取私有函数 `_write_atomic(fd, tmp_path, final_path, path, json_str, raw_bytes, use_gzip)`（约 21 行）
- 主路径和重试块都调用此函数
- 重试块仅保留目录重建 + `mkstemp` 的布局代码

**测试**：`test_cache.py` 中无测试覆盖 `FileNotFoundError` 重试路径，提取后为 `_write_atomic` 添加简单测试。

### P1-3：`fetch_market_data()` 复用 `_fetch_with_fallback()`

**现状**：`fetcher.py` 中 `_fetch_with_fallback()`（93-168 行）提供了通用 fallback 链模式，但 `fetch_market_data()`（248-313 行）因两个原因无法使用它：
1. **Per-provider 名称验证**：腾讯链路需要 `_name_matches()` 检查
2. **Per-provider 转换函数**：`_PRICE_TRANSFORMS` 是 `dict[str, Callable]`，而 `_fetch_with_fallback` 只接受单个 `transform`

**操作**：
- 在 `_fetch_with_fallback()` 中新增 `validate: Callable[[dict, str], bool] | None = None` 参数——在 transform 前调用，接收 `(raw, provider_name)`
- 使 `_fetch_with_fallback()` 的 `transform` 参数支持 `dict[str, Callable]`——如果传入 dict，则按 `provider_name` 选择对应的转换函数
- 重构 `fetch_market_data()` 委托给 `_fetch_with_fallback()`，传入 `validate` 和 `_PRICE_TRANSFORMS`

**测试**：`test_fetcher.py` 中 `TestFetchMarketData`（57-114 行）的 mock 需要更新——原 mock `_PRICE_PROVIDERS` 改为 mock `_fetch_with_fallback`。现有 4 个测试用例（缓存命中、API 成功、全部失败、名称不匹配）应全部保持通过。

---

## 二、D. 智能预警（2 个子功能）

### 核心思路

智能预警**不依赖 LLM**，是对已有计算数据的二次加工。包括两个独立维度，合并输出到一个报告章节（Excel 页签 + HTML 章节），位置：在「财经新闻热点」之后、「LLM 章节」之前。

### 新增模块：`src/python/report/early_warning.py`

#### D-1：行业资金流向联动

**输入数据**：
- `get_sector_fund_flow()` → `[{name, change_pct, main_net_inflow, main_net_inflow_pct, top_stock}]`
- 穿透 TOP10 → `[{name, codes, sector, concepts, mv, ratio_pct, ...}]`

**算法**：
1. 从穿透 TOP10 收集所有 `concepts`（概念板块标签，来自东方财富 API）
2. 对每个行业资金流向条目，检查其 `name` 是否匹配任一穿透资产的 `concepts`
3. 如果匹配且 `main_net_inflow` < -5000 万（阈值可配置），标记为预警
4. 按净流出金额排序，严重流出标记为"危险"，轻微为"关注"

**输出数据结构**：
```python
# 单个预警条目
{
    "sector_name": "电池",
    "main_net_inflow": -500000000,   # 负数=净流出
    "main_net_inflow_pct": -5.21,
    "change_pct": -2.35,
    "matched_assets": [
        {"name": "电池ETF", "code": "561910", "mv": 50000, "ratio_pct": 5.2}
    ],
    "alert_level": "danger",  # "danger" | "warning"
}
```

**为什么用概念匹配而不是板块**：行业资金流向的行业名（电池、白酒、证券）与东方财富概念标签（电池、白酒、证券）使用同一命名体系。穿透数据的 `sector` 是宽泛分类（新能源、消费），不适合直接匹配。

#### D-2：新闻情绪聚合

**输入数据**：
- `build_news_data()` 返回的 `(news_data, llm_meta)` 元组
- `news_data` 中每条新闻如果开启了 LLM 关联分析，包含 `llm_analysis.sentiment`（"利好"|"利空"|"中性"）和 `llm_analysis.relevance`（"高"|"中"|"低"|"无关"）
- 每条新闻还包含 `matched_keywords`（关联关键词列表）

**算法**：
1. 筛选 LLM 关联度 ≥ "中" 的新闻
2. 从 `matched_keywords` 中提取持仓代码/名称
3. 按持仓代码聚合：
   - 总提及次数
   - 利好/利空/中性数量
   - 计算情绪得分 = (利好 - 利空) / 总数
4. 按提及次数排序，取 TOP N 最受关注的品种

**输出数据结构**：
```python
{
    "code": "600900",
    "name": "长江电力",
    "total_mentions": 12,
    "positive": 3,
    "negative": 5,
    "neutral": 4,
    "sentiment_score": -0.17,  # -1~1，负数偏空
    "sentiment_label": "偏利空",
    "top_stories": ["新闻标题1", "新闻标题2"]
}
```

#### D-3：综合函数

```python
def compute_early_warnings(
    penetration_top10: list[dict],
    sector_flow: list[dict],
    news_data: list[dict] | None = None,
    news_llm_meta: dict | None = None,
) -> dict:
    """计算智能预警数据。
    
    Returns:
        {
            "sector_alerts": [...],   # 行业资金流向预警列表
            "sentiment_alerts": [...], # 新闻情绪聚合列表
            "has_warnings": True/False
        }
    """
```

### 集成到 Excel

**文件**：`src/python/report/excel_writer.py`（新增写入函数）

```python
def write_early_warning_sheet(ws, early_warnings: dict) -> None:
    """写入智能预警页签。
    
    结构：
    - 标题行：智能预警
    - 第一部分：行业资金流向联动预警（表格）
        行业 | 主力净流入 | 涨跌幅 | 关联持仓 | 预警等级
    - 第二部分：新闻情绪聚合（表格）
        持仓品种 | 提及次数 | 利好 | 利空 | 中性 | 情绪 | 最新要闻
    """
```

**页签位置**：第 7 号页签（"智能预警"），后续 LLM 页签顺延为 8-11。需要修改 `_generate_excel_report()` 中页签创建顺序和 `write_llm_sheets()` 中页签索引。

**页签名**：`11.智能预警`（使用序号前缀保持排序）

> 注：序号"11"是因为这是第 11 个页签（1.汇总 → 2.市值核算 → 3.持仓分类 → 4.资产穿透TOP10 → 5.基金业绩分析 → 6.财经新闻热点 → 11.智能预警 → 7~10.LLM 章节）。但为了显示顺序，放在第 7 位创建。页签序号用于排序显示，不影响功能。

### 集成到 HTML

**文件**：`src/python/report/html_writer.py`

- 在 `write_html_report()` 中新增 `early_warnings: dict | None = None` 参数
- 在获取新闻数据后、LLM 生成前，调用 `compute_early_warnings()`
- 传入模板

**文件**：`src/python/tmpl/report_template.html`

- 在「财经新闻热点」之后、「全球政经局势」之前新增一节：
  ```html
  <!-- MODULE 7: 智能预警 -->
  <div class="section">
      <div class="section-title">七、智能预警</div>
      {% if early_warnings and early_warnings.has_warnings %}
      ...预警表格...
      {% else %}
      <div class="section-content">当前无预警信息。</div>
      {% endif %}
  </div>
  ```

### 集成到报告生成流程

**文件**：`src/python/tui_handlers.py`

- `_generate_excel_report()`：新增 `early_warnings` 参数，在创建页签时加入智能预警页签
- `_cmd_generate_full()`：在获取 `_sector_flow` 和 `news_data` 后计算预警数据，传递到 Excel 和 HTML 生成函数
- 所有包含新闻的报告（菜单 N/B/L）自动附带智能预警

### 关于菜单选项

智能预警**不新增菜单项**，它作为已有报告流程的内置增值：
- N（含新闻的 Excel）：自动包含
- B（含新闻的 HTML+Excel）：自动包含
- L（全系列完整版）：自动包含

---

## 三、更新 plan.md 未来迭代

将 P2 优化项（4-7）追加到 plan.md 的「待实现方向」区域：

### H. 代码架构优化（中难度 / 高可维护性）

- **LLM Generator 函数去重**：`generate_global_macro`、`generate_expert_review`、`generate_health_check`、`generate_penetration_deep_analysis` 四个函数骨架相同（llm_config → fingerprint → build prompt → `_generate_llm_content`），可抽参数化 dispatch 函数
- **Prompt Builder 去重**：`_build_expert_review_prompt`、`_build_health_check_prompt`、`_build_penetration_deep_prompt` 共享 70% 结构（摘要+持仓循环+穿透循环），可抽共享模板
- **`_DEFAULT_LLM_SETTINGS` 注册表化**：`_ensure_llm_settings_file()` 中硬编码 50 个默认值改为从 registry 自动派生
- **`tui_handlers.py` 拆分**：1331 行的单文件拆为按领域（cache/report/llm）的子模块

---

## 四、涉及文件清单

### 新增文件
| 文件 | 用途 |
|------|------|
| `src/python/report/early_warning.py` | 智能预警核心计算逻辑 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `src/python/llm/prompts.py` | 删除 `_sanitize_endpoint`（187-192）+ `__all__` 中移除（第 18 行） |
| `src/python/cache.py` | 提取 `_write_atomic()` 辅助函数，消除 `set()` 中 21 行重复 |
| `src/python/fetcher.py` | `_fetch_with_fallback()` 增加 `validate` + dict `transform` 支持；`fetch_market_data()` 重构委托 |
| `src/python/report/excel_writer.py` | 新增 `write_early_warning_sheet()` |
| `src/python/report/html_writer.py` | 新增 `early_warnings` 参数，集成新章节 |
| `src/python/tmpl/report_template.html` | 新增「七、智能预警」章节 |
| `src/python/tui_handlers.py` | 报告流程集成智能预警 |
| `docs-stm/managements/plan.md` | 迁移 P2 项目标至「待实现方向」 |

### 测试文件
| 文件 | 用途 |
|------|------|
| `src/test/test_cache.py` | 新增 `_write_atomic` 测试 |
| `src/test/test_fetcher.py` | 更新 mock 路径，保持现有用例通过 |
| `src/test/test_early_warning.py` | 新增 智能预警 计算逻辑测试 |

### 文档
| 文件 | 用途 |
|------|------|
| `docs-stm/managements/changelog.md` | v0.2.36 条目 |
| `docs-stm/managements/testplan.md` | 新增迭代记录 |
| `docs-stm/managements/plan.md` | 迁移 P2 至待实现方向 |

---

## 五、验证方案

1. **运行全量测试**：`pytest src/test/` → 现有 966 passed 不降反升（新增测试）
2. **生成含新闻报告**：菜单 N 或 L → 确认 Excel 出现「智能预警」页签
3. **HTML 报告检查**：确认「七、智能预警」章节内容正确
4. **边缘情况**：
   - 行业资金流向 API 不可用 = 预警部分显示"无数据"
   - LLM 新闻分析未开启 = 情绪聚合部分显示"开启 LLM 新闻关联分析后可用"
   - 无新闻数据 = 情绪聚合显示"暂无新闻数据"
5. **优化验证**：
   - `_sanitize_endpoint` 不再从 `prompts.py` 导入（grep 确认）
   - `cache.py` 写入逻辑去重（diff 确认）
   - `fetch_market_data` 已委托给 `_fetch_with_fallback`（功能测试通过）
