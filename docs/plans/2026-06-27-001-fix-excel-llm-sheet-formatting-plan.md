---
title: fix: Excel LLM 报告页签排版优化 - 段落分行 + 文本换行 + 缓存提示
type: fix
date: 2026-06-27
---

## 问题

Excel 报告的"全球政经局势"（模块 7）和"智囊团深度复盘"（模块 8）有两个问题：

1. **排版不可读**：全部内容写入一个合并单元格 A2:B50，未启用文本换行，也未设置行高，所有文本坍缩在一行内溢出边界。
2. **无缓存提示**：使用缓存时用户不知道内容是来自缓存而非实时调用 LLM。

## 要求

**R1.** 两个 LLM 页签的内容按段落分行显示，每段占独立行，段落间有视觉间隔。

**R2.** 启用文本换行（`wrap_text=True`），文本在单元格内自动换行适应列宽。

**R3.** 行高根据内容自动计算，确保所有文本可见。

**R4.** 列宽固定在合理范围（约 80 字符），不因单行内容过宽而撑出超宽列。

**R5.** 保留文本框样式（左对齐、顶部对齐），阅读体验接近 HTML 报告。

**R6.** 修复不破坏现有行为：标题行样式、冻结窗格、None 占位符逻辑保持不变。

**R7.** 当 LLM 内容来自缓存时，在对应页签底部写入提示文字"本章节内容使用了 LLM 缓存，未直接调用 LLM 服务"；未使用缓存则不显示。

## 关键决策

- **段落拆分而非 Markdown 解析** — 按双换行（`\n\n`）拆分为段落写入独立行，而非尝试解析 Markdown 语法（`##` / `**` / `-`）。理由：(1) 宏观分析是纯文本段落；(2) 智囊团复盘虽含 Markdown 标记，但段落拆分已大幅提升可读性；(3) Markdown 标记作为文本保留，仍可辅助理解结构；(4) 实现复杂度低。
- **行高 = f(内容长度, 列宽)** — 按中文字符双倍宽度估算每行字符数，`ceil(段落字符数 / 每行字符数) × 15pt` 计算行高。不依赖 Excel 自动行高（openpyxl 不支持）。
- **列宽 80 固定** — 对中文字符约 40 字/行，兼顾阅读体验和页面利用；替代现有 `auto_width`（会因单段落长文本撑出超宽列）。
- **缓存标记通过函数返回值透传** — `generate_global_macro` / `generate_expert_review` 各返回 `(html, from_cache)` 二元组，`generate_all_llm` 返回四元组 `(macro_html, expert_html, macro_cached, expert_cached)`，最终传入 `write_llm_sheets`。不在 Excel 层重新查缓存——缓存判定已在 LLM 层完成，透传标记更简单可靠。

## 影响范围

涉及 5 个源文件：
- `src/llm_client.py` — 返回值类型变更（`Optional[str]` → `tuple[Optional[str], bool]`）
- `src/report/llm_content.py` — 排版重构 + 缓存提示
- `src/report/styles.py` — 新增 `CONTENT_FONT` 常量
- `src/report/html_writer.py` — 调用处解包新返回值（忽略缓存标记）
- `src/main.py` — 调用处解包新返回值 + 透传缓存标记到 Excel 层

## 实施方案

### U1. 缓存标记上游透传 — `generate_global_macro` / `generate_expert_review` / `generate_all_llm`

**目标：** 让 LLM 生成层的缓存状态能够传递到 Excel 写入层。

**文件：**
- `src/llm_client.py`（修改）
- `src/main.py`（修改 — 调用处解包 + 透传）
- `src/report/html_writer.py`（修改 — 调用处解包忽略缓存标记）

**方案：**

1. `generate_global_macro` 返回值从 `Optional[str]` 改为 `tuple[Optional[str], bool]`：
   - 缓存命中时返回 `(cached, True)`
   - LLM 调用成功后返回 `(html, False)`
   - LLM 不可用 / 失败时返回 `(None, False)`

2. `generate_expert_review` 同上。

3. `generate_all_llm` 返回值从 `tuple[Optional[str], Optional[str]]` 改为 `tuple[Optional[str], Optional[str], bool, bool]`：
   - `(macro_html, expert_html, macro_cached, expert_cached)`

4. **`generate_all_llm` 内部流更新** — `_run_macro()` 和 `_run_expert()` 闭包现返回二元组，其 `as_completed` 循环（约第 860-876 行）需做解包：
   ```python
   # 旧
   macro_result = macro_future.result()
   expert_result = expert_future.result()
   return macro_result, expert_result

   # 新
   macro_result, macro_cached = macro_future.result()
   expert_result, expert_cached = expert_future.result()
   return macro_result, expert_result, macro_cached, expert_cached
   ```
   缓存预检提前返回（约第 851 行）从 `return (_macro_cached, _expert_cached)` 改为 `return (_macro_cached, _expert_cached, True, True)`。

5. **`_generate_excel_report` 签名更新** — 主函数 `main.py` 约第 419 行需要新增 `llm_cached: tuple[bool, bool] = (False, False)` 形参，并在调用处（约第 523 行）传入：
   ```python
   macro_text, expert_text = write_llm_sheets(wb, llm_content=llm_content,
       llm_cached=llm_cached)
   ```

**调用方更新（同属本单元）：**

- `src/main.py` 第 791 行：`llm_macro, llm_expert = _llm_fut.result()` → `llm_macro, llm_expert, macro_cached, expert_cached = _llm_fut.result()`
- `src/main.py` 第 793 行：`llm_content = (llm_macro, llm_expert)` 不变
- `src/main.py`：`llm_cached = (macro_cached, expert_cached)` 传入 `_generate_excel_report`
- `src/report/html_writer.py` 第 290 行：`global_macro_content, expert_review_content, _, _ = generate_all_llm(...)`

**测试场景：**

- **缓存命中**：mock 缓存返回非 None → `from_cache=True`
- **缓存未命中**：mock 缓存返回 None → `from_cache=False`
- **LLM 不可用**：llm_config=None → 返回 `(None, False)`
- **双缓存全部命中**：`generate_all_llm` 返回的标记均为 True
- **宏缓存命中 + 专家未命中**：各自的标记独立正确
- **测试更新**：`test_llm_client.py` 中 `TestGenerateAllLlm` 更新：
  - `mock_macro.return_value = ("<p>宏</p>", False)`（二元组）
  - `mock_expert.return_value = ("<p>策略</p>", False)`（二元组）
  - 解包从 `macro, expert = generate_all_llm(...)` 改为 `macro, expert, mc, ec = ...`
- `test_html_writer.py` 中 `mock_llm.return_value = ("<p>宏观</p>", "<p>复盘</p>")` 改为 4 元组 `("<p>宏观</p>", "<p>复盘</p>", False, False)`；使用 mock 的测试中解包从 `global_macro_content, expert_review_content = generate_all_llm(...)` 改为加 `_, _`

### U2. 重构 `_write_content_sheet` — 段落分行 + 文本换行 + 缓存提示

**目标：** LLM 内容从单合并单元格改为多行段落展示，并在页尾写入缓存提示。

**文件：**
- `src/report/llm_content.py`（修改）
- `src/report/styles.py`（修改——增加内容区字体常量 `CONTENT_FONT`）

**依赖：** U1（需要接收 `from_cache` 标记）

**方案：**

1. 移除 `_CONTENT_MERGE_END_ROW = 50` 常量和整块合并逻辑。
2. 剥离 HTML 后，对纯文本按 `\n\n` 分割为段落列表，过滤空段落。
3. 从标题行下一行开始，逐段落写入：
   - 每段单独一行，列 A 写入文本
   - 列 A 设置 `Alignment(wrap_text=True, vertical="top", horizontal="left")`
   - 列 A 字体使用 `CONTENT_FONT`（新增常量：size=11, 黑色）
   - 列 A 宽度固定为 80
   - 段落间插入一个空行作为间距
4. 行高计算（每个段落独立计算）：
   - 列宽 80 → 约 40 中文字符/行
   - `lines = ceil(len(paragraph) / 40)`
   - `row_height = max(lines * 15, 30)`（最小 30pt）
5. 接收 `from_cache: bool` 参数，若为 True 则在所有段落后方追加一行灰色提示文字：
   - 写入列 A，文本："⚠ 本章节内容使用了 LLM 缓存，未直接调用 LLM 服务"
   - 字体灰色（`Font(color="999999", size=9, italic=True)`）
   - 行高 20pt
6. `write_llm_sheets` 签名从 `(wb, llm_content)` 改为 `(wb, llm_content, llm_cached=(False, False))`。
7. 无内容时写入占位符（当前行为不变），占一行居中。

**测试场景：**

- **正常多段落**：输入 3 段内容 → 输出 3 行，每行启用 wrap_text
- **单段内容**：单段落 → 输出 1 行
- **None 内容**：content=None → 写入占位符一行
- **空字符串**：content="" → 写入占位符
- **段落含中英文混排**：行高中文双倍宽度计算正确
- **wrap_text 属性**：每行 `cell.alignment.wrap_text = True`
- **列宽固定 80**：不受文本长度影响
- **标题行不变**：标题行字体/填充/居中对齐与当前一致
- **from_cache=True**：页尾追加灰色缓存提示行
- **from_cache=False**：无缓存提示行
- **冻结窗格**：`ws.freeze_panes == "A2"`

### U3. 新增 `src/test_llm_content.py` 覆盖

**目标：** 为 U1-U2 变更提供全面的函数级覆盖。

**文件：**
- `src/test_llm_content.py`（新增）

**方案：**

测试类设计：
- `TestStripHtml` — `_strip_html` 函数测试
- `TestWriteContentSheet` — `_write_content_sheet` 行为测试
- `TestWriteLlmSheets` — `write_llm_sheets` 集成测试

使用 `openpyxl.Workbook()` 创建真实 workbook 调用目标函数，验证单元格内容、样式、换行、行高、缓存提示行。

**测试场景：**

`TestStripHtml`:
- 含 `<p>`、`<strong>` 标签 → 纯文本正确剥离
- `&amp;` HTML 实体 → 保持原样（已知行为，不处理实体）
- None / 空字符串 → 返回空字符串

`TestWriteContentSheet`:
- **三段输入 → 3 行内容**：A1 标题行，A2/A4/A6 段落（A3/A5 空行间距）
- **单段 → 1 行内容**
- **content=None → A2 写占位符**
- **段落换行属性**：每行 `cell.alignment.wrap_text` 为 True
- **列宽 → `ws.column_dimensions["A"].width == 80`
- **行高**：短段落 30pt，长段落 > 30pt
- **标题行不变**：A1 字体/填充/对齐保持不变
- **冻结窗格 → freeze_panes == "A2"
- **from_cache=True → 末行灰色提示**：末尾行内容含"LLM 缓存"
- **from_cache=False → 无提示行**

`TestWriteLlmSheets`:
- 返回 `(text7, text8)` 二元组（纯文本，用于 TUI）
- 两个 sheet 标题分别为"全球政经局势"和"智囊团深度复盘"
- 缓存标记独立：macro 缓存 + expert 未缓存 → sheet7 有提示、sheet8 无

## 测试验证

```bash
cd D:/codebase/zoo/investor-util
python -m pytest src/test_llm_content.py src/test_llm_client.py -v
```

预期：全部测试通过，新增约 18 个测试用例。现有约 500 用例不受影响。

## 风险和注意事项

- U1 返回值类型变更需要更新所有调用方和内部流。已确认所有点：`generate_all_llm` 内部 `as_completed` 循环、缓存预检提前返回、`_generate_excel_report` 签名、`main.py` 外部调用、`html_writer.py` 调用。
- 无数据管道变更、无网络 I/O 变更、无外部 API 变更。
- 回归风险低：现有 3 个测试文件（`test_llm_client.py`、`test_html_writer.py`、`test_llm_content.py` 新增）覆盖变更路径。`generate_all_llm` 的其他行为（force 参数透传、TTL 取值）不受返回值类型变更影响。
