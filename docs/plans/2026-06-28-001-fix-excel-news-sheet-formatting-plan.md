---
title: feat: Excel 财经新闻热点页签显示优化与关键词丰富
type: feat
date: 2026-06-28
execution: code
---

# Excel 财经新闻热点页签显示优化与关键词丰富

## 问题描述

Excel 报告的"财经新闻热点"页签存在两个问题：

1. **显示拥挤**：新闻标题和摘要是长文本，但当前 `auto_width(max_width=30)` 截断列宽，且无文本换行，导致内容挤在一起，难以阅读。
2. **关联关键词信息不足**：`matched_keywords` 仅列出原始关键词字符串（如 `"长江电力"`、`"600900"`、`"电力"`），无法区分该关键词来自持仓名称/代码、穿透资产还是行业词汇。用户无从知晓"这条新闻是通过什么持仓关联到的"。

---

## 需求

1. 优化"财经新闻热点"页签的列宽、换行、对齐，使长文本可读
2. "关联关键词"列展示每个匹配关键词的上下文：持仓代码+名称、穿透资产标签、行业标签
3. 需要同时在 Excel 和 HTML 两个报告格式中体现（HTML 的完善同步跟进）

---

## 范围边界

### In Scope
- `src/report/news_correlation.py` — `write_news_sheet()` 的显示逻辑
- `src/report/excel_writer.py` — 文本换行支持、自定义列宽
- `src/report/news_correlation.py` — 关键词丰富逻辑（`build_news_data()` + `write_news_sheet()`）
- `src/tmpl/report_template.html` — HTML 新闻区关键词丰富
- `src/report/html_writer.py` — HTML 侧参数传递
- `src/test_news_correlation.py` — 测试更新
- `src/test_html_writer.py` — 测试更新

### Out of Scope
- 不改变新闻获取/聚合/去重逻辑
- 不改变 LLM 增强流程
- 不改变其他 Excel 页签的样式
- 不改变 `build_news_data()` 的返回类型签名

---

## 关键技术决策

### 关键词丰富策略

在 `build_news_data()` 中对每条新闻的 `matched_keywords` 做后处理，逐一比对 holdings 和 penetrated_assets，生成新的 `enriched_keywords` 字段：

```python
# 每条 news_item 新增：
news_item["enriched_keywords"] = [
    {"display": "长江电力(600900)", "type": "holding"},       # 持仓
    {"display": "腾讯控股(00700)", "type": "penetration"},     # 穿透
    {"display": "电力", "type": "industry"},                   # 行业
]
```

由 `_enrich_keyword_display(keywords, holdings, penetrated_assets) -> list[dict]` 函数实现。

### Excel 显示改善方案

- 在 `write_news_sheet()` 中对"新闻标题"(B列)和"摘要"(C列)启用 `Alignment(wrap_text=True)`
- B列和C列设为左对齐（而不是居中对齐）
- 手动设置 B列 ~40 width、C列 ~50 width（覆盖 `auto_width` 的 max_width=30）
- 适当增大行高 (`ws.row_dimensions[row].height = None`) 以自动适配文本

### HTML 同步

- 新的 `enriched_keywords` 字段已经随 `news_data` 传入 HTML 模板
- 模板中 "关联关键词" 列的渲染改为使用 `enriched_keywords`（fallback 到 `matched_keywords`）
- 在 HTML 端增加样式区分不同类型：持仓→蓝色、穿透→紫色、行业→灰色

---

## 实施单元

### U1. 关键词丰富函数

**Goal:** 实现 `_enrich_keyword_display()` 函数，对 news_item 的 `matched_keywords` 做后处理，生成带上下文的 `enriched_keywords`。

**Dependencies:** 无

**Files:**
- Modify: `src/report/news_correlation.py`

**Approach:**
1. 新增 `_build_keyword_lookup(holdings, penetrated_assets) -> dict[str, dict]` 构建正向查找表
   - 对每个持仓：`keyword → {"type": "holding", "name": h.name, "code": h.code}`
   - 对每个穿透资产：`keyword → {"type": "penetration", "name": asset.name, "codes": asset.codes}`
   - 额外标记纯代码匹配（`keyword == h.code`）和名称片段匹配（`keyword in h.name`）
2. 新增 `_enrich_keywords_for_item(item, keyword_lookup) -> list[dict]`
   - 遍历 `item["matched_keywords"]`，查 lookup
   - 命中持仓 → `{"display": "长江电力(600900)", "type": "holding", "code": "600900"}`
   - 命中穿透 → `{"display": "腾讯控股[穿透]", "type": "penetration"}`
   - 未命中 → `{"display": "电力", "type": "industry"}`
   - 去重（同一 holding 通过不同关键词命中多次只显示一次）
3. 在 `build_news_data()` 中调用 enrichment
4. `format_enriched_keywords(enriched) -> str` 生成单行显示字符串

**Test scenarios:**
- 新闻匹配到持仓名称 → 生成 "长江电力(600900)" display + type="holding"
- 新闻匹配到持仓代码 → 同样生成 "长江电力(600900)"（去重后合并）
- 新闻匹配到穿透资产名称 → 生成 "腾讯控股[穿透]"
- 新闻匹配到行业词汇（不在持仓/穿透中）→ 生成 "电力" + type="industry"
- 空 keywords / 空 holdings → 不报错
- 同一持仓被 keyword 和 code 同时匹配 → 只显示一次

**Verification:** 单元测试通过，所有 `_enrich_keyword_display` 场景覆盖。

---

### U2. Excel 新闻页签格式优化

**Goal:** 改善"财经新闻热点"页签的可读性。

**Dependencies:** U1（需要 enriched_keywords 数据）

**Files:**
- Modify: `src/report/news_correlation.py`（`write_news_sheet()`）
- Modify: `src/report/excel_writer.py`（可选：增加 `LEFT_ALIGN_WRAP` 样式常量）

**Approach:**
1. 在 `write_news_sheet()` 的数据行写入后，对 B 列（新闻标题）和 C 列（摘要）设置：
   ```python
   from openpyxl.styles import Alignment
   wrap_left = Alignment(horizontal="left", vertical="top", wrap_text=True)
   ws.cell(row=r, column=2).alignment = wrap_left
   ws.cell(row=r, column=3).alignment = wrap_left
   ```
2. 手动设置列宽（在 `auto_width()` 之前或之后覆盖）：
   ```python
   ws.column_dimensions["B"].width = 40  # 标题
   ws.column_dimensions["C"].width = 50  # 摘要
   ```
3. 在 "关联关键词" 列使用 `format_enriched_keywords()` 的输出替换纯 `", ".join(matched_keywords)`
4. 对 LLM 分析列（若有）设置合适的宽度

**Test scenarios:**
- 有长度的标题和摘要 → 验证 wrap_text 被设置
- 列宽自动适配 → 验证 B 列 > 默认 max_width
- 关键词列显示 `长江电力(600900)` 格式字符串
- 空数据 → 不影响已有占位逻辑
- 有 LLM 分析列时同样正确

**Verification:** 手动打开 Excel 确认可读性 + 单元测试验证 alignment 和 column_dimensions 设置正确。

---

### U3. HTML 报告富化关键词同步

**Goal:** HTML 报告的新闻区域同样显示富化关键词。

**Dependencies:** U1（enriched_keywords 字段已存在于 news_data）

**Files:**
- Modify: `src/tmpl/report_template.html`

**Approach:**
1. 模板中的 "关联关键词" 列改为优先使用 `enriched_keywords`，fallback 到 `matched_keywords`
2. 用不同颜色区分来源：持仓/穿透/行业
3. 兼容没有 `enriched_keywords` 的旧缓存数据

**Test scenarios:** 略（HTML 已通过 U1 的数据层面覆盖）
- 此单元较为简单，无需单独测试

---

### U4. 测试更新

**Goal:** 为 U1 和 U2 添加/更新测试覆盖。

**Dependencies:** U1, U2

**Files:**
- Modify: `src/test_news_correlation.py`

**Approach:**
- 为 `_enrich_keyword_display` / `_build_keyword_lookup` 新增测试类
- 覆盖 holding、penetration、industry 三种类型
- 覆盖空列表/无匹配边界
- 覆盖去重逻辑
- 为 `write_news_sheet` 的 wrap_text / column_width 设置新增断言

**Test scenarios:**
- 持仓名称匹配 → display = "名称(代码)"
- 持仓代码匹配 → 与名称去重后合并显示
- 穿透资产匹配 → display = "名称[穿透]"
- 行业词汇匹配 → display = "词汇"
- 混合场景 → 按 持仓 > 穿透 > 行业 顺序显示
- Excel 列宽 B → 40, C → 50
- B/C 列 alignment wrap_text=True + horizontal="left"

**Verification:** ```cd D:/codebase/zoo/investor-util && python -m pytest src/test_news_correlation.py -v``` 全部通过。

---

## 依赖关系

```
U1 (关键词丰富) ──→ U2 (Excel 格式)
  │
  └──→ U3 (HTML 同步)
  │
  └──→ U4 (测试)
```

U1 是无依赖的基座变更。U2 和 U3 依赖 U1 的 `enriched_keywords` 字段。U4 依赖 U1 和 U2 确定测试断言。

---

## 未纳入实施的问题

### 关键词去重合并粒度

同一持仓的名称和代码可能同时匹配同一条新闻。例如持有"长江电力(600900)"，新闻中同时出现"长江电力"和"600900"。当前方案保留两条独立的 `enriched_keywords` 条目但 `display` 相同 → 在 `format_enriched_keywords()` 中做最后去重。

### `auto_width` 与手动列宽覆盖

当前计划在 `auto_width()` 之后手动覆盖 B/C 列。这可能导致 B/C 列偏窄（auto_width 已截断到 30）。替代方案：先手动设置 B/C 再到 `auto_width` 处理剩余列。选择后者更合理。决定：`auto_width` 调用之前设置 B/C 列宽。

### 行高自适应

openpyxl 中 `ws.row_dimensions[row].height = None` 在某些 Excel 客户端中不会自动换行展开。备选：根据文本行数估算行高并手动设置。估算公式：`ceil(len(text) / chars_per_line) * line_height`。简单起见先设为 None，若手动观察展开效果不佳再启用估算。
