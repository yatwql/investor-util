# R-207：summary.py LLM 用量模块提取迭代计划与技术设计

创建日期：2026-07-10
状态：待审批
关联问题：R-207（review-findings.md）
参考模式：R-197（market_value → market_value + market_value_sheet）、R-206（excel_generator 编排器分拆）

---

## 1. 问题分析

### 1.1 当前状态

`src/python/report/summary.py` 当前 617 行，包含 **20 个函数**，覆盖两个独立职责域：

| 职责域 | 函数 | 行数 | 占比 |
|:-------|:-----|:----:|:----:|
| **汇总页签**（`write_summary_sheet`） | `_write_section`、`_write_kv_row`、`_write_kv_row_colored`、`_write_index_row`、`_write_blanks`、`_write_basic_info`、`_write_holdings_overview`、`_write_profit_summary`、`_write_a_share_indices`、`_write_us_indices`、`_build_index_data_status`、`write_summary_sheet` | ~350 | 57% |
| **LLM 用量页签**（`write_llm_usage_sheet`） | `_init_llm_usage_sheet`、`_write_llm_summary_section`、`_write_module_table_header`、`_write_module_data_rows`、`_write_legend`、`_write_cache_stats_section`、`_set_column_widths`、`write_llm_usage_sheet` | ~267 | 43% |

### 1.2 核心问题

1. **两个独立页签共用同文件**：`write_summary_sheet`（页签 1 汇总）和 `write_llm_usage_sheet`（页签 16 API 用量）无函数交叉调用，无共享状态，逻辑完全独立
2. **`write_llm_usage_sheet` 是变异较快的模块**：LLM 用量显示格式、定价表、状态标签等需求变更频繁，混在稳定的汇总页签中增加了合并冲突风险
3. **最大单函数风险**：`_write_module_data_rows`（69 行）在 LLM 用量部分是最复杂函数（10 列渲染 + 4 种状态 + 条件着色），且被 `test_summary.py` 的 `TestWriteModuleDataRows` 直接导入测试
4. **跨文件依赖**：`html_writer.py:23` 从 `summary` 导入 `_build_index_data_status`（私有函数），`test_excel_report_structure.py` 从 `summary` 导入 `_set_column_widths`（私有函数）

### 1.3 与 R-206 的异同

| 维度 | R-206（excel_generator 拆分） | R-207（summary 拆分） |
|:-----|:-----------------------------|:---------------------|
| 拆分模式 | 编排器 → 6 个专用模块 | 汇聚模块 → 按职责域分拆 |
| 拆分粒度 | 1→7 文件 | 1→2 文件（1 提取） |
| 职责边界 | 各函数职责不同，需逐一辨别 | **天然边界清晰**（汇总 vs LLM 用量） |
| 测试影响 | 8 个测试文件需更新 | 3 个测试文件需更新 |

---

## 2. 技术设计

### 2.1 目标架构

```
summary.py (~350 行)              # 仅保留汇总页签功能
  ├── _write_section              # 章节标题
  ├── _write_kv_row               # 键值行
  ├── _write_kv_row_colored       # 着色键值行
  ├── _write_index_row            # 指数行
  ├── _write_blanks               # 空行
  ├── _write_basic_info           # 基本信息
  ├── _write_holdings_overview    # 持仓概况
  ├── _write_profit_summary       # 盈亏汇总
  ├── _write_a_share_indices      # A 股指数
  ├── _write_us_indices           # 美股指数
  ├── _build_index_data_status    # 指数状态（被 html_writer.py 导入）
  └── write_summary_sheet         # 主入口

summary_llm_usage.py (~267 行)    # LLM API 用量页签
  ├── _init_llm_usage_sheet       # 页签初始化
  ├── _write_llm_summary_section  # 汇总数据区
  ├── _write_module_table_header  # 模块明细表头
  ├── _write_module_data_rows     # 模块明细行（最复杂）
  ├── _write_legend               # 状态图例
  ├── _write_cache_stats_section  # 缓存统计
  ├── _set_column_widths          # 列宽设置
  └── write_llm_usage_sheet       # 主入口
```

### 2.2 接口兼容性策略

由于 `excel_generator.py` 通过 `from src.python.report.summary import write_llm_usage_sheet` 导入，提取后需要保持向后兼容：

**策略 A（推荐）**：在 `summary.py` 中保留 re-export：
```python
# summary.py 末尾
from src.python.report.summary_llm_usage import write_llm_usage_sheet  # noqa: F401
```

**策略 B**：直接修改 `excel_generator.py` 的导入路径 → 影响 1 处 inline import，但需要同步修改测试 mock 路径

选择 **策略 A** 的理由：
- `excel_generator.py` 的 inline import 无需修改（零额外风险）
- `test_excel_generator.py` 的 `patch("src.python.report.summary.write_llm_usage_sheet")` mock 路径不变
- 引入 `summary_llm_usage.py` 后相当于在 summary.py 做了"公开 API 转发"

> 注意：`_build_index_data_status` 不提取（被 `html_writer.py` 导入）。`_set_column_widths` 随 LLM 用量部分迁移，`test_excel_report_structure.py` 的导入路径需更新。

### 2.3 依赖关系

```
summary.py (~350 行)                              # 汇总页签
  → excel_writer, market_value, cache, registry
  → data_status (STATUS_MESSAGES, DegradationTracker)

summary_llm_usage.py (~267 行)                    # LLM 用量页签
  → excel_writer, cache (get_cache_hit_rate)
  → llm.pricing (_CURRENCY_SYMBOLS, _PRICING_CURRENCY)
  → summary 不依赖！！！（无交叉引用）

excel_generator.py → summary.py                   # 编排器导入入口
excel_generator.py → summary.py (re-export)       # 通过 re-export 导入 write_llm_usage_sheet
```

**无循环依赖**：`summary_llm_usage.py` 不导入 `summary.py`，反之亦然。

### 2.4 设计约束遵从性检查

| 约束 | 合规说明 |
|:-----|:---------|
| C1 代码类型判定中心化 | 不适用 — LLM 用量页签不涉及资产类型判定 |
| C2 缓存统一管理 | 不影响 — `get_cache_hit_rate` 通过 cache.py |
| C3 缓存原子写入 | 不适用 — 本模块不写缓存（只读 `get_cache_hit_rate`） |
| C4 会话级 API 复用缓存 | 不适用 — 模块为纯展示层，不触发 HTTP |
| C5 HTTP 客户端统一 | 不适用 — 模块无网络请求 |
| C6 Provider Chain 必经 | 不适用 — 模块不调用任何 Provider |
| C7 报告序号不可硬编码 | 不影响 — `get_report_sheet_name` 从 registry 读取 |
| C8 日志统一 | `logging.getLogger("invest")` |
| C9 LLM 模块注册 | 不影响 — `write_llm_usage_sheet` 属于报告展示层，非 LLM 生成模块 |
| C10 新闻召回策略 | 不适用 — 模块不涉及新闻 |
| C11 测试标记强制 | 新模块测试文件标注 `@pytest.mark.unit_report` |
| C12 边缘测试文件隔离 | 边缘测试放 `*_edge.py` |
| C13 测试敏感路径隔离 | 不影响 — conftest autouse fixture 自动生效 |
| **C14 渲染期数据不入全局变量** | 模块级变量仅含 `_HEADERS`、`_STATUS_COLORS` 等不可变常量 |

### 2.5 测试影响清单

| 文件 | 引用内容 | 提取后影响 | 是否需修改 |
|:-----|:---------|:----------:|:---------|
| `test_summary.py:23` | `from src.python.report import summary as s` | 不提取 `Summary` class 所以 `s._write_section` 等不变 | ❌ 否 |
| `test_summary.py:766` | `from src.python.report.summary import _write_module_data_rows` | → `summary_llm_usage` | ✅ I-09 |
| `test_excel_report_structure.py:245,256` | `from src.python.report.summary import _set_column_widths` | → `summary_llm_usage` | ✅ I-09 |
| `test_excel_generator.py:459` | `patch("src.python.report.summary.write_llm_usage_sheet")` | re-export 保持不变 | ❌ 否 |
| `html_writer.py:23` | `from src.python.report.summary import _build_index_data_status` | 不提取该函数 | ❌ 否 |
| `excel_generator.py:508` | `from src.python.report.summary import write_llm_usage_sheet` | re-export 不变 | ❌ 否 |

---

## 3. 迭代计划

### 3.1 迭代总览

| 轮次 | 内容 | 源文件风险 | 测试影响 | 预计耗时 |
|:----:|:-----|:----------:|:--------:|:--------:|
| I-01 | **基线捕获**：行数/测试通过率/覆盖率记录 | 无 | 无 | 10 min |
| I-02 | 创建 `summary_llm_usage.py` + move `_init_llm_usage_sheet` + `_write_legend` + **添加 re-export** | 低 | 0 文件 | 25 min |
| I-03a | Move `_write_cache_stats_section` + 更新 re-export | 低 | 0 文件 | 12 min |
| I-03b | Move `_set_column_widths` + 更新 re-export | 低 | 0 文件 | 12 min |
| I-04 | Move `_write_llm_summary_section` + 更新 re-export | 低 | 0 文件 | 15 min |
| I-05 | Move `_write_module_table_header` + 更新 re-export | 低 | 0 文件 | 12 min |
| I-06 | Move `_write_module_data_rows` + 更新 re-export | **中** | 0 文件 | 25 min |
| I-07 | Move `write_llm_usage_sheet` + re-export 终态审查 | 中 | 0 文件 | 20 min |
| I-08 | 清理 + 线数验证（终态 ≈360 行） | 低 | 0 文件 | 12 min |
| I-09 | 更新测试导入路径 + 新增 `test_summary_llm_usage.py` | 中 | **3** 文件需更新 | 30 min |
| I-10 | 文档同步 + 全量回归验证 | 低 | 运行全量 | 20 min |

**总预计：~3 小时**

### 3.2 I-01：基线捕获

**步骤**：
1. 记录 `summary.py` 精确行数：`wc -l src/python/report/summary.py`
2. 运行现有测试验证通过率：
   ```bash
   python -m pytest src/test/unit/report/test_summary.py -v --tb=short
   python -m pytest src/test/unit/report/test_excel_report_structure.py -v --tb=short -k "test_column_widths or test_set_column"
   ```
3. grep 所有 `summary` 引用确认基线：
   ```bash
   grep -rn "from src.python.report.summary" src/ --include="*.py"
   ```

**验收标准**：
- [ ] `summary.py` 行数记录（617）
- [ ] `test_summary.py` 100% 通过
- [ ] 所有外部引用清单确认

### 3.3 I-02：创建 `summary_llm_usage.py` + 迁移辅助函数 + 添加 re-export

**目标**：创建新模块并迁移最稳定的辅助函数。**关键变更**：re-export 必须在此轮立即添加，否则 `write_llm_usage_sheet`（仍在 summary.py）对 `_init_llm_usage_sheet` 的 bare name 调用会抛出 `NameError`。

**步骤**：
1. 创建 `src/python/report/summary_llm_usage.py`
2. 添加 `pytestmark` 标记（后续测试用）
3. 搬运依赖导入（`logging`、`openpyxl.styles` 等）
4. 移动 `_init_llm_usage_sheet`
5. 移动 `_write_legend`
6. **在 `summary.py` 末尾添加 re-export**：
   ```python
   from src.python.report.summary_llm_usage import (  # noqa: F401
       _init_llm_usage_sheet,
       _write_legend,
   )
   ```
7. 验证：
   ```bash
   # re-export 验证
   python -c "from src.python.report.summary import _init_llm_usage_sheet"
   # 确认 test_summary.py 不通过 s.* 间接调用（若有则需保留代理函数）
   grep "s\._init_llm_usage_sheet" src/test/unit/report/test_summary.py || echo "OK"
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `summary_llm_usage.py` 存在并可导入
- [ ] `_init_llm_usage_sheet` 和 `_write_legend` 在新模块中
- [ ] `summary.py` 中已删除这两个函数的定义
- [ ] re-export 使 `from summary import _init_llm_usage_sheet` 可用
- [ ] 现有测试全部通过

**回退方案**：`git revert HEAD`

### 3.4 I-03a：迁移 `_write_cache_stats_section`

**目标**：迁移缓存统计函数（无外部测试依赖，最低风险）。

**步骤**：
1. 将 `_write_cache_stats_section` 从 `summary.py` 移动到 `summary_llm_usage.py`（含 inline import `from src.python.cache import get_cache_hit_rate`）
2. 更新 re-export 加入 `_write_cache_stats_section`
3. 验证：
   ```bash
   python -c "from src.python.report.summary import _write_cache_stats_section"
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `_write_cache_stats_section` 在新模块中
- [ ] `summary.py` re-export 保持有效
- [ ] 全部测试通过

**回退方案**：`git revert HEAD`

### 3.5 I-03b：迁移 `_set_column_widths`

**目标**：迁移列宽设置函数（被 `test_excel_report_structure.py` 直接导入）。

**步骤**：
1. 将 `_set_column_widths` 从 `summary.py` 移动到 `summary_llm_usage.py`
2. 更新 re-export 加入 `_set_column_widths`
3. 验证：
   ```bash
   # re-export 使 from summary import _set_column_widths 保持有效
   python -c "from src.python.report.summary import _set_column_widths"
   python -m pytest src/test/unit/report/test_excel_report_structure.py -v -x --tb=short
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `_set_column_widths` 在新模块中
- [ ] `from summary import _set_column_widths` 通过 re-export 保持有效
- [ ] `test_excel_report_structure.py` **不失败**（re-export 保障）

**回退方案**：`git revert HEAD`

### 3.6 I-04：迁移 `_write_llm_summary_section`

**目标**：迁移 LLM 汇总区域函数 + 同步更新 re-export。

**步骤**：
1. 将 `_write_llm_summary_section` 从 `summary.py` 移动到 `summary_llm_usage.py`
2. 搬运 `PatternFill` 等 openpyxl 样式依赖
3. 更新 re-export 加入 `_write_llm_summary_section`
4. 验证：
   ```bash
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `_write_llm_summary_section` 在新模块中
- [ ] `summary.py` 中已删除该函数定义（re-export 保持可用）
- [ ] 现有测试通过

**回退方案**：`git revert HEAD`

### 3.7 I-05：迁移 `_write_module_table_header`

**目标**：迁移模块明细表头函数 + 同步更新 re-export。

**步骤**：
1. 将 `_write_module_table_header` 从 `summary.py` 移动到 `summary_llm_usage.py`
2. 更新 re-export 加入 `_write_module_table_header`
3. 验证：`python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short`

**验收标准**：
- [ ] `_write_module_table_header` 在新模块中
- [ ] `summary.py` 中已删除该函数定义（re-export 保持可用）
- [ ] 现有测试通过

**回退方案**：`git revert HEAD`

### 3.8 I-06：迁移 `_write_module_data_rows`

**目标**：迁移最大、最复杂的 LLM 数据行渲染函数（69 行） + 同步更新 re-export。

**步骤**：
1. 将 `_write_module_data_rows` 从 `summary.py` 移动到 `summary_llm_usage.py`
2. 注意搬运 inline import：`from src.python.llm.pricing import _CURRENCY_SYMBOLS, _PRICING_CURRENCY`
3. 更新 re-export 加入 `_write_module_data_rows`
4. 验证：
   ```bash
   python -c "from src.python.report.summary import _write_module_data_rows"
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `_write_module_data_rows` 在新模块中
- [ ] `from summary import _write_module_data_rows` 通过 re-export 有效
- [ ] `test_summary.py::TestWriteModuleDataRows` **通过**（re-export 使其可访问）

**回退方案**：`git revert HEAD`

### 3.9 I-07：迁移 `write_llm_usage_sheet` + re-export 终态审查

**目标**：迁移 LLM 用量页签主入口函数。re-export 已在 I-02~I-06 轮逐步积累，此轮完成最终形态并验证 `test_excel_report_structure.py`。

**步骤**：
1. 将 `write_llm_usage_sheet` 从 `summary.py` 移动到 `summary_llm_usage.py`
2. re-export 终态确认（已在之前各轮逐步构建，此轮 update）：
   ```python
   from src.python.report.summary_llm_usage import (  # noqa: F401
       _init_llm_usage_sheet, _write_llm_summary_section,
       _write_module_table_header, _write_module_data_rows,
       _write_legend, _write_cache_stats_section,
       _set_column_widths, write_llm_usage_sheet,
   )
   ```
3. 验证：
   ```bash
   python -c "from src.python.report.summary import write_llm_usage_sheet"
   python -c "from src.python.report.summary import _set_column_widths"
   python -m pytest src/test/unit/report/test_excel_report_structure.py -v -x --tb=short
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `write_llm_usage_sheet` 在新模块中
- [ ] re-export 终态列表完整（8 个函数）
- [ ] `from summary import write_llm_usage_sheet` 仍可用
- [ ] `from summary import _set_column_widths` 仍可用
- [ ] `test_excel_generator.py` mock 路径不变
- [ ] `test_excel_report_structure.py` 100% 通过
- [ ] `test_summary.py` 全部通过

**回退方案**：`git revert HEAD`

### 3.10 I-08：清理 + 线数验证

**目标**：最终检查 — summary.py 不再包含 LLM 用量函数定义（仅保留 re-export）。

**步骤**：
1. 确认以下函数已在 `summary.py` 中删除定义（仅保留 re-export）：
   - `_init_llm_usage_sheet`、`_write_llm_summary_section`、`_write_module_table_header`
   - `_write_module_data_rows`、`_write_legend`、`_write_cache_stats_section`
   - `_set_column_widths`、`write_llm_usage_sheet`
2. 确认 re-export 导入列表完整
3. 验证文件行数 ≈360 行（含 re-export 区域）
4. 运行全部关联测试：
   ```bash
   python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
   python -m pytest src/test/unit/report/test_excel_report_structure.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `summary.py` ≈360 行（减少 ≈260 行，含 re-export 开销）
- [ ] re-export 列表完整（8 个函数）
- [ ] `test_summary.py` 100% 通过
- [ ] `test_excel_report_structure.py` 100% 通过
- [ ] `test_excel_generator.py` 全部通过

**回退方案**：`git revert HEAD`

### 3.11 I-09：更新测试导入路径 + 新增测试文件

**目标**：消除对 `summary.py` re-export 的依赖，改为直接导入 `summary_llm_usage`。

**步骤**：
1. **更新 `test_summary.py`**：
   - `TestWriteModuleDataRows` 中的 `from src.python.report.summary import _write_module_data_rows` → `from src.python.report.summary_llm_usage import _write_module_data_rows`
2. **更新 `test_excel_report_structure.py`**：
   - 2 处 `from src.python.report.summary import _set_column_widths` → `from src.python.report.summary_llm_usage import _set_column_widths`
3. **新增 `test_summary_llm_usage.py`**：
   - 迁移 `TestWriteModuleDataRows`（从 `test_summary.py` 迁移）
   - 新增 `test_init_llm_usage_sheet` 冒烟测试
   - 新增 `test_write_legend` 冒烟测试
   - 新增 `test_set_column_widths` 冒烟测试
   - 标记：`pytestmark = [pytest.mark.unit, pytest.mark.unit_report]`
4. 运行验证：
   ```bash
   python -m pytest src/test/unit/report/test_summary_llm_usage.py -v
   python -m pytest src/test/unit/report/test_summary.py -v
   python -m pytest src/test/unit/report/test_excel_report_structure.py -v
   ```

**验收标准**：
- [ ] `test_summary.py::TestWriteModuleDataRows` 导入路径已更新
- [ ] `test_excel_report_structure.py` 2 处导入路径已更新
- [ ] `test_summary_llm_usage.py` 存在，包含 `TestWriteModuleDataRows`
- [ ] 3 个测试文件全部通过

**回退方案**：`git revert HEAD`

### 3.12 I-10：文档同步 + 全量回归

**目标**：同步文档 + 最终全量回归验证。

**步骤**：
1. 更新 `docs-stm/manuals/datasource-and-folders.md` 目录树：新增 `summary_llm_usage.py` 条目
2. 更新 `docs-stm/managements/technical.md`：
   - 报告生成管线章节：新增 `summary_llm_usage.py` 层次
   - 模块间依赖关系章节：补充 `summary_llm_usage` 的依赖
3. 更新 `docs-stm/managements/review-findings.md`：R-207 改为"✅ 已完成"
4. 运行回归：
   ```bash
   python scripts/test_runner.py --mode regression
   ```

**验收标准**：
- [ ] `datasource-and-folders.md` 目录树包含 `summary_llm_usage.py`
- [ ] `technical.md` 模块依赖图更新
- [ ] `review-findings.md` R-207 标记为已完成
- [ ] regression 模式 100% 通过

**回退方案**：`git checkout dev -- docs-stm/`

---

## 4. 风险分析

### 4.1 风险矩阵

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|:---|:-----|:----:|:----:|:----:|:---------|
| R1 | **re-export 遗漏导致 `from summary import write_llm_usage_sheet` 失败** | 中 | **高** | 🔴 | I-07 后立即验证 `python -c "from src.python.report.summary import write_llm_usage_sheet"` |
| R2 | **test_excel_generator.py mock 路径因 re-export 失效** | 低 | 高 | 🟡 | `patch("src.python.report.summary.write_llm_usage_sheet")` 针对的是 `summary` 名称空间，re-export 后该名称空间仍存在，mock 不受影响 |
| R3 | **I-03~I-06 期间 test_excel_report_structure.py 测试失败** | 确定 | 中 | 🟡 | 明确标注为"预期中间状态"，I-09 统一修复 |
| R4 | **`_build_index_data_status` 被 html_writer.py 直接导入（私有函数）** | 低 | 中 | 🟡 | 不提取该函数，保留在 summary.py |
| R5 | **re-export 导致 `flake8 F401` 警告** | 中 | 低 | 🟢 | 添加 `# noqa: F401` 注释 |
| R6 | **`test_summary.py` 中 `from src.python.report import summary as s` 模块级 import 因 re-export 引入额外依赖** | 低 | 低 | 🟢 | re-export 只在 import 时加载，不影响运行时行为 |

### 4.2 每轮验证步骤

```bash
# Step 1: 主入口导入
python -c "from src.python.report.summary import write_summary_sheet, write_llm_usage_sheet"
# Step 2: summary.py 语法
python -c "import ast; ast.parse(open('src/python/report/summary.py').read())"
# Step 3: 核心测试（含 re-export 验证）
python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short
# Step 4 (每两轮): handers_report 链路
python -m pytest src/test/scenario/basic/test_integration.py -x --tb=short -q
```

---

## 5. 收益评估

### 5.1 直接收益

| 指标 | 拆分前 | 拆分后 | 变化 |
|:-----|:------:|:------:|:----:|
| `summary.py` 行数 | 617 | ~350 | **-43%** |
| 函数/文件 | 20 | 12 | 单一职责 |
| LLM 用量模块独立性 | 混在 summary.py | 独立 `summary_llm_usage.py` | 隔离化 |
| 更新 LLM 用量格式 | 需改 summary.py | 只需改 `summary_llm_usage.py` | 风险隔离 |

### 5.2 间接收益

- **变异隔离**：LLM 定价表、状态颜色、列格式等高频变更不再影响稳定的汇总页签
- **`html_writer.py` 不再依赖 summary 的私有函数**（`_build_index_data_status` 虽未移动，但 LLM 相关引用被消除）
- **测试定位**：LLM 用量测试集中在 `test_summary_llm_usage.py`

### 5.3 技术债务（明确遗留）

- `summary.py` 末尾的 re-export 是"过渡债务" — 建议 2 次迭代后消除，改为直接导入 `summary_llm_usage`
- `_build_index_data_status` 仍留在 `summary.py` 中并被 `html_writer.py` 直接导入 — 这是一个 `from html_writer import _build_index_data_status` 的跨文件私有函数依赖，但超出了本次迭代范围

---

## 6. 自审记录（15 维复盘结果）

### 6.1 自查维度

| # | 维度 | 发现 | 严重度 | 优化措施 |
|:---|:-----|:-----|:------:|:---------|
| D1 | **设计约束完整性** | 约束表仅列了 9/14 条（C1/C2/C7/C8/C9/C11/C12/C13/C14），缺少 C3/C4/C5/C6/C10 五项 | 🟢 低 | 补齐全部 14 条，不适用项标注"不适用" |
| D2 | **迭代粒度合理性** | I-03 合并移动两个函数，但 _write_cache_stats_section（0 测试影响）和 _set_column_widths（被 test_excel_report_structure.py 直接导入）的测试影响不同 | 🟢 低 | 将 I-03 拆为 I-03a（_write_cache_stats_section）和 I-03b（_set_column_widths） |
| D3 | **验收标准完整性** | I-02 验收标准未确认 `test_summary.py` 是否通过 `s.*` 间接调用被移动的函数 | 🟡 中 | 在 I-02 验收标准中增加 `grep s\._init_llm_usage_sheet test_summary.py` 确认步骤 |
| D4 | **风险矩阵覆盖度** | 缺少"导入链断裂风险"——summary_llm_usage.py 导入错误会导致 report 包整体加载失败 | 🟡 中 | 新增 R7：导入链断裂风险 |
| D5 | **[CRITICAL] re-export 时机** | `write_llm_usage_sheet`（仍留在 summary.py）通过 bare name 调用 7 个辅助函数（`_init_llm_usage_sheet(ws)` 等）。I-02 删除函数定义后不立即加 re-export 会导致 NameError | 🔴 **高** | re-export **必须**在 I-02 立即添加，随每次迭代逐步扩充，不得推迟到 I-07 |
| D6 | **I-07 验收标准遗漏** | I-07 的 re-export 会使 `from summary import _set_column_widths` 恢复可用，但验收标准未包含 `test_excel_report_structure.py` | 🟡 中 | I-07 验收标准增加该测试验证 |
| D7 | **"预期失败"误判** | I-03 标注 `test_excel_report_structure.py` 预期失败，但若 I-02 就添加了 re-export，`from summary import _set_column_widths` 仍然有效，不应失败 | 🟡 中 | 去除"预期失败"标注，改为"re-export 保持有效" |
| D8 | **行数估计偏乐观** | `~350` 行未计入 re-export 区域（~8 行）、`__all__` 等固定开销，终态约 360-365 行 | 🟢 低 | 修正为 `~360` 行 |
| D9 | **跨项目冲突风险** | R-206（excel_generator 拆分）与 R-207 都修改 `datasource-and-folders.md` 和 `technical.md`，并行执行时有合并冲突风险 | 🟡 中 | 风险矩阵新增 R8 |
| D10 | **测试文件共享风险** | `test_excel_report_structure.py` 同时被 R-206（改 _create_sheets 共 9 处）和 R-207（改 _set_column_widths 共 2 处）修改 | 🟡 中 | 风险矩阵新增 R9，建议 R-207 在 R-206 后执行 |
| D11 | **import 链深度** | summary_llm_usage.py 依赖链含 2 个 inline import（`llm.pricing._CURRENCY_SYMBOLS` 私变量 + `cache.get_cache_hit_rate`）均为 lazy 加载 | 🟡 中 | 风险可接受，inline import 是既有模式 |
| D12 | **_write_cache_stats_section 位置计算** | 该函数签名 `(ws) -> None` 不使用 row 参数，通过 `ws.max_row + 2` 动态定位 | 🟢 低 | 移动后行为不变，无需特别处理 |
| D13 | **R-206/R-207 顺序依赖** | R-206 只拆 excel_generator.py 内部函数，不修改向 summary 的导入代码（lines 42/508） | 🟢 低 | **R-207 可独立执行，无需等 R-206** |
| D14 | **TestWriteModuleDataRows 搬迁陷阱** | I-09 搬迁该测试类时可能含 `s.*` 隐式引用，导致交叉依赖 | 🟡 中 | 搬迁前审阅代码，确保无 `s.*` 隐式调用 |
| D15 | **_build_index_data_status 隐形成本** | 该函数留在 summary.py 中被 html_writer.py 导入，造成"此函数属汇总页签"的错误认知 | 🟡 中 | I-08 清理中补充注释标注"被 html_writer.py 使用" |

### 6.2 关键问题详解

#### D5 [CRITICAL]：re-export 时机错误

经过代码验证，`write_llm_usage_sheet`（定义在 summary.py 第 577-617 行）**全部 7 个辅助函数调用均为 bare name 调用**：

```
write_llm_usage_sheet()
  ├── row = _init_llm_usage_sheet(ws)              ← bare name
  ├── row = _write_llm_summary_section(ws, row, …)  ← bare name
  ├── row = _write_module_table_header(ws, row, …)  ← bare name
  ├── row = _write_module_data_rows(ws, row, …)     ← bare name
  ├── _write_legend(ws, row)                        ← bare name
  ├── _write_cache_stats_section(ws)                ← bare name
  └── _set_column_widths(ws, …)                     ← bare name
```

这意味着——**函数定义被移出 summary.py 后，Python 在 summary 模块的名称空间中找不到该名称，会抛出 `NameError`**。re-export 机制正是为了修补这个缺口：`from summary_llm_usage import _init_llm_usage_sheet` 将名称重新注入 summary 的名称空间，使 bare name 调用仍能正确解析。

**修正后的策略**：每次移动函数到 summary_llm_usage.py 时，**同步更新** summary.py 末尾的 re-export 区块，确保被移动的函数名仍存在于 summary 模块的名称空间中。re-export 不是 I-07 才做的事，而是 I-02~I-07 每轮都要维护的实时保障。

#### D11 [中]：import 链深度风险

`summary_llm_usage.py` 的依赖链有两处 inline import：

```
summary_llm_usage.py
  ├── _write_cache_stats_section()  → from src.python.cache import get_cache_hit_rate  (lazy inline)
  └── _write_module_data_rows()     → from src.python.llm.pricing import _CURRENCY_SYMBOLS, _PRICING_CURRENCY  (lazy inline)
```

**风险**：
- `llm.pricing._CURRENCY_SYMBOLS` 和 `_PRICING_CURRENCY` 是 `llm.pricing` 的**私有变量**——它们被 `summary.py` 以 inline import 方式跨模块访问，本已不符合封装原则。提取到 `summary_llm_usage.py` 后问题延续但未恶化。
- `cache.get_cache_hit_rate()` 是公开 API，无风险。
- 两处均为 lazy inline import（函数体内加载），不是模块级加载，**不会**因 summary_llm_usage.py 被 import 而导致整条链立刻加载。

**结论**：风险可接受，无动作。

#### D12 [低]：`_write_cache_stats_section` 位置计算方式不变

验证发现：`_write_cache_stats_section(ws)` 的签名是 `(ws) -> None`，不使用 `row` 参数。它内部通过 `ws.max_row + 2` 动态计算写入位置。这意味着：
1. 移动后行为不受影响（函数体不变）
2. 它不依赖 `write_llm_usage_sheet` 传入的 `row` 值
3. 验证步骤无需特别处理

#### D13 [低]：R-206/R-207 顺序依赖再评估

R-206（excel_generator 拆分）修改的是 excel_generator.py 的内部结构，**不影响**该文件对 `summary.py` 的导入代码：

```
excel_generator.py:42:     from src.python.report.summary import write_summary_sheet   ← 不变的导入
excel_generator.py:508:    from src.python.report.summary import write_llm_usage_sheet  ← 不变的导入
```

这两个导入在 R-206 的作用范围内不被触及（R-206 只拆分 excel_generator.py 的内部函数，不修改它向 summary 的导入）。**R-207 可独立执行，无需等待 R-206**。

#### D14 [中]：`test_summary.py` TestWriteModuleDataRows 搬迁陷阱

`TestWriteModuleDataRows` 目前完整定义在 `test_summary.py`（~130 行，行 755-892）。I-09 计划将其迁移到 `test_summary_llm_usage.py`。但有一个隐患：

**原文 `TestWriteModuleDataRows` 中可能通过 `s.*` 访问 summary 中的其他函数**（如 `s._write_section`、`s._set_column_widths` 等 fixture 调用）。搬迁后，`test_summary_llm_usage.py` 不应该为调用 `s.*` 而导入 `summary` 模块（那样会产生不必要的交叉依赖）。

**缓解措施**：搬迁前审阅 `TestWriteModuleDataRows` 的代码，确保所有 `s.*` 引用要么替换为直接导入 `summary_llm_usage`，要么被识别为 setUp 依赖（保留在 test_summary.py 中）。

#### D15 [中]：`_build_index_data_status` 未被提取的隐形成本

`_build_index_data_status` 留在 summary.py 中，被 `html_writer.py:23` 通过 `from src.python.report.summary import _build_index_data_status` 直接导入（私有函数跨模块访问）。这产生了一个**隐形的错误信号**——未来开发者看到 summary.py 仍包含 `_build_index_data_status`，会以为这是"汇总页签"的一部分，但实际上它被 HTML 报告使用。

**收益/代价**：本次暂不移动 `_build_index_data_status` 到独立的 data module（超出范围）。但应在 `summary.py` 中为 `_build_index_data_status` 加注释标注"被 html_writer.py 使用"。

**建议**：I-08 清理步骤中增加「为 `_build_index_data_status` 添加非 LLM 相关注释说明」的动作。

---

## 7. 深层技术债务分析

### 7.1 遗留债务清单

| # | 债务项 | 引入时间 | 消除成本 | 建议消除时机 |
|:---|:-------|:--------:|:--------:|:-----------|
| TD1 | `summary.py` re-export 层（≈8 行，8 个函数） | R-207 | 低（更新 4 处 import） | 下次 LLM 用量变更 PR |
| TD2 | `_build_index_data_status` 私有函数跨文件被 `html_writer.py` 导入 | 旧有 | 中（提取到共享模块+更新 2 文件） | `html_writer.py` 重构时 |
| TD3 | `summary_llm_usage.py` 通过 inline import 访问 `llm.pricing._CURRENCY_SYMBOLS` 等私有变量 | 旧有（搬运） | 低（公开化定价常量为公开 API） | 随定价表更新时 |
| TD4 | `TestWriteModuleDataRows`（130 行）在 test_summary.py 和 test_summary_llm_usage.py 之间存在搬迁期双维护风险 | R-207 | 低（按 I-09 执行后消除） | I-09 完成后 |

### 7.2 收益/风险/债务平衡表

| 决策 | 收益 | 风险 | 新增债务 |
|:-----|:-----|:-----|:---------|
| **re-export 策略**（当前方案） | 零外部文件修改；零测试 breakage | re-export 行被误删的风险 | TD1（可消除） |
| **直接修改导入路径**（替代方案） | 无 re-export 债务 | 需改 5 个文件；`test_excel_generator.py` mock 路径变化 | TD1 不复存在 |
| **不拆 summary.py**（不做） | 零风险 | 文件持续膨胀（>617 行）；变异隔离失效 | — |

**结论**：re-export 策略收益/风险比更高。TD1 债务量（8 行）远小于直接改 5 文件的风险面。

---

## 8. 风险矩阵终版（合并优化后）

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|:---|:-----|:----:|:----:|:----:|:---------|
| R1 | re-export 遗漏 | 中 | 🔴 | 高 | 每轮验证 `python -c "from src.python.report.summary import *"` |
| R2 | test_excel_generator.py mock 路径失效 | 低 | 高 | 🟡 | re-export 后 summary 名称空间不变，mock 路径无变化 |
| R3 | test_excel_report_structure.py 测试失败 | 低（已修复） | 中 | 🟢 | re-export 已保障（I-02起） |
| R4 | `_build_index_data_status` 私函数依赖 | 低 | 中 | 🟡 | 本次不提取，加注释标注 |
| R5 | flake8 F401 警告 | 中 | 低 | 🟢 | `# noqa: F401` |
| R6 | 模块级 import 引入额外依赖 | 低 | 低 | 🟢 | re-export 只加载符号，不影响运行 |
| R7 | summary_llm_usage.py import 链断裂 → report 包加载失败 | 低 | 🔴 | 高 | 每轮含 `python -c "from src.python.report.summary_llm_usage import *"` |
| R8 | test_summary.py TestWriteModuleDataRows 搬迁遗漏 `s.*` 引用 | 中 | 中 | 🟡 | I-09 前审阅测试代码，确保无 `s.*` 隐式依赖 |
| R9 | R-206/R-207 文档冲突 | 中 | 低 | 🟢 | datasource-and-folders.md 分两段编辑即可 |

---

## 9. 优化后迭代计划

基于 6.1 的自查结果，对原计划做以下优化：

### 7.1 变更摘要

| 轮次 | 原计划 | 优化后 | 变更原因 |
|:----:|:-------|:-------|:---------|
| I-02 | 创建 summary_llm_usage.py + move 2 个函数 | 同上 + **立即添加 re-export** | D5 — 否则 write_llm_usage_sheet NameError |
| I-03a | （原 I-03）合并移动 2 个函数 | **仅**移动 _write_cache_stats_section | D2 — 与 _set_column_widths 解耦 |
| I-03b | — | **新增**：移动 _set_column_widths + 更新 re-export | D7 — 单独处理测试影响 |
| I-04 | 仅移动函数 | 移动函数 + **更新 re-export** | D5 — 每轮保障名称空间 |
| I-05 | 仅移动函数 | 移动函数 + **更新 re-export** | D5 — 同上 |
| I-06 | 仅移动函数 | 移动函数 + **更新 re-export** | D5 — 同上 |
| I-07 | 移动入口 + 添加 re-export | 移动入口 + **re-export 终态审查** | D6 — 增加 test_excel_report_structure.py 验证 |
| — | 未覆盖 | **新增 R8/R9 风险管理** | D9/D10 — 跨项目冲突 |

### 7.2 优化后迭代详细步骤

#### I-01：基线捕获（不变）

（内容与原 I-01 一致）

#### I-02：创建 summary_llm_usage.py + 迁移辅助函数 + 添加 re-export

**变更：新增 re-export 步骤**。

```python
# summary.py 末尾
from src.python.report.summary_llm_usage import (  # noqa: F401
    _init_llm_usage_sheet,
    _write_legend,
)
```

**验收标准增加**：
- `grep "s\._init_llm_usage_sheet" src/test/unit/report/test_summary.py` 确认无引用（若有则需保留代理函数）
- `python -c "from src.python.report.summary import _init_llm_usage_sheet"` 验证 re-export 生效
- `test_summary.py` 全部通过

#### I-03a：迁移 _write_cache_stats_section

**变更：从原 I-03 拆分，仅迁移 _write_cache_stats_section**。

区分原因：_write_cache_stats_section 不涉及测试变化，独立迁移风险更低。

**步骤**：
1. 将 `_write_cache_stats_section` 从 `summary.py` 移动到 `summary_llm_usage.py`（含 inline import `from src.python.cache import get_cache_hit_rate`）
2. 更新 re-export：
   ```python
   from src.python.report.summary_llm_usage import (  # noqa: F401
       _init_llm_usage_sheet,
       _write_legend,
       _write_cache_stats_section,
   )
   ```
3. 验证 `test_summary.py` 全部通过（write_llm_usage_sheet 依赖的 `_write_cache_stats_section` 通过 re-export 可达）

#### I-03b：迁移 _set_column_widths

**目标**：单独迁移被 test_excel_report_structure.py 直接导入的函数。

**步骤**：
1. 将 `_set_column_widths` 从 `summary.py` 移动到 `summary_llm_usage.py`
2. 更新 re-export 加入 `_set_column_widths`
3. 验证：
   - `python -c "from src.python.report.summary import _set_column_widths"`（re-export 保持有效）
   - `python -m pytest src/test/unit/report/test_excel_report_structure.py -v -x --tb=short`（re-export 使测试不中断）
   - `python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short`

**验收标准**：
- `_set_column_widths` 在新模块中
- `from summary import _set_column_widths` 仍有效（re-export）
- `test_excel_report_structure.py` **不失败**（因 re-export）

#### I-04：迁移 _write_llm_summary_section

**变更：增加 re-export 更新步骤**。

**步骤**：
1. 移动 `_write_llm_summary_section`
2. 更新 re-export 加入 `_write_llm_summary_section`
3. 验证 `test_summary.py` 全部通过

#### I-05：迁移 _write_module_table_header

**变更：增加 re-export 更新步骤**。

**步骤**：
1. 移动 `_write_module_table_header`
2. 更新 re-export 加入 `_write_module_table_header`
3. 验证 `test_summary.py` 全部通过

#### I-06：迁移 _write_module_data_rows

**变更：增加 re-export 更新步骤**。

**步骤**：
1. 移动 `_write_module_data_rows`（含 inline pricing import）
2. 更新 re-export 加入 `_write_module_data_rows`
3. 验证 `test_summary.py` 全部通过（**不预期失败**，因 re-export）

**验收标准**：
- `_write_module_data_rows` 在新模块中
- `from summary import _write_module_data_rows` 仍有效（re-export）
- `test_summary.py::TestWriteModuleDataRows` 通过（re-export 使其可访问）

#### I-07：迁移 write_llm_usage_sheet + re-export 终态审查

**变更：增加 test_excel_report_structure.py 验证**。

**步骤**：
1. 移动 `write_llm_usage_sheet`
2. re-export 终态：
   ```python
   from src.python.report.summary_llm_usage import (  # noqa: F401
       _init_llm_usage_sheet,
       _write_llm_summary_section,
       _write_module_table_header,
       _write_module_data_rows,
       _write_legend,
       _write_cache_stats_section,
       _set_column_widths,
       write_llm_usage_sheet,
   )
   ```
3. 验证：
   - `python -c "from src.python.report.summary import write_llm_usage_sheet"`
   - `python -c "from src.python.report.summary import _set_column_widths"`（re-export 终态验证）
   - `python -m pytest src/test/unit/report/test_excel_report_structure.py -v -x --tb=short` **（新增）**
   - `python -m pytest src/test/unit/report/test_summary.py -v -x --tb=short`

#### I-08：清理 + 验证线数（不变）

**验收标准**：
- `summary.py` ≈360 行（修正后精确值，含 re-export 区域）
- `test_excel_report_structure.py` 全部通过（re-export 使 _set_column_widths 可用）

#### I-09：测试导入路径更新（不变）

#### I-10：文档同步 + 全量回归（不变）

### 7.3 风险矩阵优化

新增以下风险项：

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|:---|:-----|:----:|:----:|:----:|:---------|
| **R7** | **import 链断裂**：summary_llm_usage.py 内部导入错误 → report 包整体加载失败 | 低 | **高** | 🔴 | 轮次验证步骤含 `python -c "from src.python.report.summary_llm_usage import *"` |
| **R8** | **R-206/R-207 并行文档冲突**：datasource-and-folders.md 和 technical.md 被两项目同时修改 | 低 | 中 | 🟡 | 建议 R-207 在 R-206 落地后执行，或在同一分支依次执行 |
| **R9** | **test_excel_report_structure.py 共享修改**：R-206 改 _create_sheets（9 处），R-207 改 _set_column_widths（2 处） | 中 | 低 | 🟢 | 按顺序执行，R-207 在 R-206 已合并的 dev 上开分支 |

---

## 10. 优化后进度追踪

| 轮次 | 状态 | 分支 | 提交语 |
|:----:|:----:|:-----|:-------|
| I-01 | ⏳ 待启动 | `dev-feat/summary-llm-split` | `feat(R-207/I-01): baseline capture` |
| I-02 | ⏳ 待启动 | 续上 | `feat(R-207/I-02): create summary_llm_usage + move helpers + re-export` |
| I-03a | ⏳ 待启动 | 续上 | `feat(R-207/I-03a): move _write_cache_stats + update re-export` |
| I-03b | ⏳ 待启动 | 续上 | `feat(R-207/I-03b): move _set_column_widths + update re-export` |
| I-04 | ⏳ 待启动 | 续上 | `feat(R-207/I-04): move _write_llm_summary_section + update re-export` |
| I-05 | ⏳ 待启动 | 续上 | `feat(R-207/I-05): move _write_module_table_header + update re-export` |
| I-06 | ⏳ 待启动 | 续上 | `feat(R-207/I-06): move _write_module_data_rows + update re-export` |
| I-07 | ⏳ 待启动 | 续上 | `feat(R-207/I-07): move write_llm_usage_sheet + finalize re-export` |
| I-08 | ⏳ 待启动 | 续上 | `feat(R-207/I-08): clean + verify line count (~360)` |
| I-09 | ⏳ 待启动 | 续上 | `feat(R-207/I-09): test adapt + new test_summary_llm_usage.py` |
| I-10 | ⏳ 待启动 | 续上 | `feat(R-207/I-10): doc sync + regression` |
