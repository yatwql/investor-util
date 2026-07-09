# R-206：excel_generator.py 拆分迭代计划与技术设计（优化版）

创建日期：2026-07-10（初版）
优化日期：2026-07-10（自行复盘 10 轮后优化版）
状态：待审批
关联问题：R-206（review-findings.md）
参考模式：R-197（market_value.py → market_value.py + market_value_sheet.py）

---

## 0. 自审复盘摘要（15 轮）

| 轮次 | 复盘发现 | 严重度 | 优化措施 |
|:----:|:---------|:------:|:---------|
| 1 | **测试影响低估**：初版称"2 个测试文件需更新"，实际 **8 个文件**引用 `excel_generator`，含 `test_excel_report_structure.py`（9 处 `_create_sheets` 直接导入）、`test_llm_scenarios.py`、`test_llm_placeholder.py` 等 | 🔴 | 新增完整的测试文件清单和 mock 路径映射表 |
| 2 | **I-08 与 I-09 职责重叠**：编排器瘦身（I-08）和测试适配（I-09）有内容交叉（移除 inline import vs 验证无 inline import） | 🟡 | 将 I-08 重命名为"导入路径统一验证"，与 I-09 明确边界 |
| 3 | **I-06 风险低估**：`_write_b_series_sheets` 含 4 个重复的 `fetch_fund_holdings`/`_is_fund` inline import 模式，提取时改为模块级 import 会改变 import 语义（从惰性加载变为加载时导入） | 🟡 | 明确标注 import 语义变更风险，提取时保留惰性加载模式 |
| 4 | **缺少拆分前基线**：没有拆分前的测试覆盖率和行号基线，无法量化每轮迭代的进度 | 🟡 | 新增 I-01：捕获基线（coverage + 文件行数 + 测试通过率） |
| 5 | **回退策略不统一**：I-01 用 `git checkout -- src/python/report/`（太宽），其余用 `git revert HEAD` — 标准不一致 | 🟡 | 统一为 `git revert HEAD`（单次提交可逆），批处理用 `git checkout dev -- src/python/report/` |
| 6 | **C14 约束未验证**：初版约束表检查了 C1~C13，但未检查 C14（渲染期数据不可写入模块级全局变量）。新模块 `excel_b_series.py` 的模块级 dict 有可能被误用作跨函数通信 | 🟡 | 新增 C14 验证 — 所有提取模块的模块级变量必须是不可变常量 |
| 7 | **`_write_news_and_early_warning` 中存在重复 inline import**：`news_correlation.write_news_sheet` 已在 `_import_report_modules` 中导入，但 `_write_news_and_early_warning` 内部又 `try: from src.python.report.news_correlation import write_news_sheet` | 🟢 | I-08 统一解决：消除重复 import，改由 module_loader 传参 |
| 8 | **未检查 scenario/integration 测试 mock 路径**：`test_llm_scenarios.py:899` 直接导入 `_build_llm_usage_sheet`，`test_integration.py:25` 模块级 import `generate_excel_report` | 🟡 | 新增 grep 清单：`handlers_report.py`（唯一非测试引用）、8 个测试文件的精确引用行 |
| 9 | **部分迭代粒度过粗（I-06、I-07）**：I-06（B 系列 167 行）和 I-07（LLM 用量 115 行）提取后仍是较大文件 | 🟢 | 维持 10 轮结构，但标注未来可二次拆分的方向 |
| 10 | **缺少 pipeline 验证步骤**：每轮提取后只跑了单元测试，未跑 pipeline/regression 验证 | 🟡 | 每轮新增 `python -c "from src.python.report.excel_generator import generate_excel_report"` 导入验证 |
| 11 | **B 系列 3 重复代码模式未消除**：`_write_b_series_sheets` 中重合度/集中度/风格 3 个模块具有完全相同的代码结构（inline import + fund_codes 过滤 + fetch_fund_holdings 循环 + try/except 写入），提取后 `excel_b_series.py` 仍含 3 份重复模板代码 | 🟡 | I-07 提取时引入 `_process_b_module` 辅助函数消除重复，约压缩 50 行 |
| 12 | **`_Timer` import 分散 5 个模块**：当前 6 个函数使用 `_Timer`（`_resolve_market_data`/`_resolve_indices`/`_write_llm_section_and_usage`/`generate_excel_report` + 2 处），提取后 4+ 模块需各自导入 `_Timer` | 🟢 | 无动作 — `_Timer` 从 progress.py 导入，轻量无副作，每模块单独导入更清晰 |
| 13 | **`modules` dict 字符串键脆弱性**：当前 15+ 个字符串键（`"write_market_value_sheet"`/`"detect_manager_changes"` 等）通过 `modules.get(key)` 访问，拼写错误在运行时静默返回 None | 🟡 | I-09 冒烟测试阶段为每个提取模块添加键名验证 fixture，确认所有消费方使用正确的键名 |
| 14 | **`test_excel_generator.py` 与 `test_excel_report_structure.py` 的 import 路径更新不一致**：I-03 总览表标注"4 个文件需更新"但计划中 I-03 实际只更新了 2 个测试文件（`test_excel_generator.py` + `test_excel_report_structure.py`） | 🟡 | 修正 I-03 总览表的数字为 2 个文件，或如实标注 4 个（含受影响的 `test_llm_placeholder.py` 和 `test_llm_scenarios.py` — 虽不导入 `_create_sheets` 但共用 excel_generator 名称空间） |
| 15 | **`_write_llm_section_and_usage` 内 `_build_llm_usage_sheet` 裸调用**：`_write_llm_section_and_usage` 在行 495 通过 `_build_llm_usage_sheet(sheets, prog)` 以 bare name 调用 `_build_llm_usage_sheet`。I-08 同时提取两者，裸调用在新模块内仍有效 — 但若提取顺序搞错（先移被调用方后移调用方），run-time 会 NameError | 🟢 | I-08 一次性提取两个函数到 `excel_llm_usage.py`，不开子步骤 |

---

## 1. 问题分析

### 1.1 当前状态

`src/python/report/excel_generator.py` 当前 693 行，是 `src/python/` 下最大的单文件。包含 11 个函数/方法，覆盖 5 个独立职责：

| 函数 | 行数 | 职责域 |
|:-----|:----:|:-------|
| `_import_report_modules()` | 126 | 模块发现 + ImportError 兜底 |
| `_resolve_market_data()` | 56 | 行情市值数据解析 |
| `_resolve_indices()` | 13 | 指数数据解析 |
| `_write_content_sheets()` | 25 | 4 个核心页签编排（汇总/分类/穿透/基金业绩） |
| `_write_news_and_early_warning()` | 57 | 新闻 + 智能预警页签编排 |
| `_write_b_series_sheets()` | 167 | B 系列 4 模块页签编排（最大单函数） |
| `_write_llm_section_and_usage()` | 23 | LLM 分析章节编排 |
| `_build_llm_usage_sheet()` | 86 | LLM 用量页签构建（含 5 状态判定逻辑） |
| `_should_create_sheet()` | 12 | 类型驱动的可见性判定 |
| `_create_sheets()` | 13 | 工作表工厂 |
| `generate_excel_report()` | 75 | **主入口编排器（本该是薄层）** |

### 1.2 核心问题

1. **单文件多职责**：模块发现、数据解析、页签编排、LLM 状态判定混在同一文件，违反单一职责原则
2. **测试耦合广泛**：8 个测试文件直接/间接引用 `excel_generator`，提取后需更新多处导入路径
3. **inline import 重复**：`_write_news_and_early_warning` 中重复了 `_import_report_modules` 已导入的 `news_correlation` 模块
4. **扩展阻力**：新增页签时虽已有类型驱动设计，但 693 行文件本身构成认知负担

### 1.3 与 R-197 的异同

| 维度 | R-197（market_value 拆分） | R-206（excel_generator 拆分） |
|:-----|:--------------------------|:-----------------------------|
| 拆分模式 | 计算层 vs 写入层分离 | 编排器 → 专用模块分解 |
| 拆分粒度 | 1→2 文件（1 提取） | 1→7 文件（6 提取） |
| 测试影响 | 0 文件需更新 | **8 个测试文件**需更新（含 3 个直接 `_build_llm_usage_sheet`/`_create_sheets` 导入） |

---

## 2. 技术设计（优化版）

### 2.1 目标架构

```
excel_generator.py (< 80 行)          # 纯编排器 — 仅保留 generate_excel_report
├── excel_module_loader.py            # 模块发现 + ImportError 兜底
├── excel_sheet_factory.py            # 页签创建 + 可见性判定
├── excel_market_data.py              # 行情市值 + 指数数据解析
├── excel_content_sheets.py           # 核心页签编排（汇总/分类/穿透/基金业绩）
├── excel_news_warning.py             # 新闻 + 智能预警页签编排
├── excel_b_series.py                 # B 系列 4 模块页签编排
└── excel_llm_usage.py                # LLM 分析章节 + 用量页签构建
```

### 2.2 完整测试文件影响清单

以下为所有引用 `excel_generator` 的文件，提取后需逐一验证：

| 文件 | 引用内容 | 提取后影响 | 是否需修改 |
|:-----|:---------|:----------:|:---------:|
| `handlers_report.py:44` | `from src.python.report.excel_generator import generate_excel_report` | `generate_excel_report` 留在原文件 | ❌ 否 |
| `test_excel_generator.py:129-458,702-727` | `generate_excel_report`（14 处）+ `_build_llm_usage_sheet`（1 处）+ `_create_sheets`（3 处）+ patching `excel_generator.get_report_sheet_name` | `_build_llm_usage_sheet` → `excel_llm_usage`; `_create_sheets` → `excel_sheet_factory`; `patch` 目标不变（名称空间仍在 excel_generator） | ✅ I-03/I-08 |
| `test_excel_generator_edge.py:86,105` | `from src.python.report.excel_generator import generate_excel_report` | 不变 | ❌ 否 |
| `test_excel_report_structure.py:62-195,307` | `_create_sheets`（**9 处**）+ `generate_excel_report`（1 处） | `_create_sheets` → `excel_sheet_factory` | ✅ I-03 |
| `test_llm_placeholder.py:57` | `from src.python.report.excel_generator import _build_llm_usage_sheet as _blus` | → `excel_llm_usage` | ✅ I-08 |
| `test_llm_scenarios.py:899` | `from src.python.report.excel_generator import _build_llm_usage_sheet as _blus` | → `excel_llm_usage` | ✅ I-09 |
| `test_integration_scenarios.py:261` | `from src.python.report.excel_generator import generate_excel_report` | 不变 | ❌ 否 |
| `test_integration.py:25` | `from src.python.report.excel_generator import generate_excel_report as _generate_excel_report` | **模块级 import** — 此测试文件在文件顶部导入 `generate_excel_report`，如果产生 import 异常则整个测试文件加载失败 | ✅ I-09 验证 |
| `test_integration_coverage.py:322` | `from src.python.report.excel_generator import generate_excel_report` | 不变 | ❌ 否 |

### 2.3 依赖关系

```
excel_generator.py (编排器)            # < 80 行，纯编排
  ├── excel_module_loader.py           # → report/*, fetcher/* (无反向依赖)
  ├── excel_sheet_factory.py           # → excel_writer, registry (无反向依赖)
  ├── excel_market_data.py             # → market_value, market_value_sheet, registry
  ├── excel_content_sheets.py          # → summary, category, penetration, fund_performance, registry
  ├── excel_news_warning.py            # → news_correlation, early_warning, registry
  ├── excel_b_series.py                # → fund_manager_sheet, fund_overlap_sheet,
  │                                    #    fund_concentration_sheet, fund_style_sheet,
  │                                    #    fetcher/fund, fund_performance, registry
  └── excel_llm_usage.py               # → llm_content, llm/*, summary, registry

各专用模块间：无交叉引用
所有依赖方向：编排器 → 专用模块 → sheet 模块（单向）
```

### 2.4 设计约束遵从性检查

| 约束 | 合规说明 |
|:-----|:---------|
| C1 代码类型判定中心化 | 不影响 — 提取模块不新增 `code.startswith` 判定 |
| C2 缓存统一管理 | 不影响 — `fetch_fund_holdings` 等通过统一缓存路径 |
| C4 会话级复用缓存 | 不影响 — B 系列模块仍通过 `DataSourceRegistry.session_cache` |
| C5 HTTP 客户端统一 | 不影响 — 提取模块不新增 HTTP 调用 |
| C6 Provider Chain 必经 | 不影响 — `fetch_fund_holdings` 等保持 Provider Chain |
| C7 报告序号不可硬编码 | 提取模块通过 `get_report_sheet_name`/`get_report_section_order` 从 registry 读取 |
| C8 日志统一 | 新模块使用 `logging.getLogger("invest")` |
| C9 LLM 模块注册 | 不影响 — `excel_llm_usage.py` 从 registry 获取模块名 |
| C10 新闻召回策略 | 不影响 — `excel_news_warning.py` 透传 `news_top_count` |
| C11 测试标记强制 | 新模块的测试文件需标注 `@pytest.mark.unit_report` |
| C12 边缘测试文件隔离 | 边缘测试放 `*_edge.py` |
| C13 测试敏感路径隔离 | 不影响 — conftest autouse fixture 自动生效 |
| **C14 渲染期数据不入全局变量** | 所有提取模块的模块级变量 **必须** 是 `_HEADERS`/`_MODULE_KEYS`/`_DISPLAY_REASON` 等不可变常量。不得出现可变 dict/set 等跨函数通信 |

---

## 3. 迭代计划（优化版）

### 3.1 迭代总览

| 轮次 | 内容 | 源文件风险 | 测试影响 | 回退策略 | 预计耗时 |
|:----:|:-----|:----------:|:--------:|:---------|:--------:|
| I-01 | **基线捕获**：记录行数/覆盖率/测试通过率 | 无 | 无 | — | 15 min |
| I-02 | 提取 `_import_report_modules` → `excel_module_loader.py` | 低 | **0** 文件 | `git revert HEAD` | 30 min |
| I-03 | 提取 `_create_sheets` + `_should_create_sheet` → `excel_sheet_factory.py` | 低 | **2** 文件需更新 | `git revert HEAD` | 30 min |
| I-04 | 提取 `_resolve_market_data` + `_resolve_indices` → `excel_market_data.py` | 低 | **0** 文件 | `git revert HEAD` | 20 min |
| I-05 | 提取 `_write_content_sheets` → `excel_content_sheets.py` | 低 | **0** 文件 | `git revert HEAD` | 20 min |
| I-06 | 提取 `_write_news_and_early_warning` → `excel_news_warning.py` | 低 | **0** 文件 | `git revert HEAD` | 25 min |
| I-07 | 提取 `_write_b_series_sheets` → `excel_b_series.py` | **中** | **0** 文件 | `git revert HEAD` | 40 min |
| I-08 | 提取 LLM 函数 → `excel_llm_usage.py` + 更新 3 测试文件 | **中** | **3** 文件需更新 | `git revert HEAD` | 40 min |
| I-09 | 导入路径统一验证 + 新增提取模块冒烟测试 | 低 | 新增 **5** 测试文件 | `git revert HEAD` | 45 min |
| I-10 | 文档同步 + 全量回归验证 | 低 | 运行全量 | `git checkout dev -- docs-stm/` | 30 min |

**总预计：~4.5 小时**（较初版增加 30 分钟，主要用于更全面的测试适配）

### 3.2 I-01：基线捕获（新增轮次）

**目标**：捕获拆分前的行数、覆盖率、测试通过率，作为可回退的起点。

**步骤**：
1. 记录 `excel_generator.py` 精确行数：`wc -l src/python/report/excel_generator.py`
2. 运行全量单元测试验证通过率：
   ```bash
   python -m pytest src/test/unit/report/test_excel_generator.py -v --tb=short 2>&1 | tail -5
   ```
3. 运行回归验证：
   ```bash
   python scripts/test_runner.py --mode regression
   ```
4. 记录当前覆盖率概况：
   ```bash
   python -m pytest src/test/unit/report/test_excel_generator.py --cov=src.python.report.excel_generator --cov-report=term 2>&1 | tail -10
   ```
5. 保存结果到 `docs-stm/tmp/R-206-baseline.md`

**验收标准**：
- [ ] 基线文件包含 `excel_generator.py` 行数（693）
- [ ] 单元测试 100% 通过
- [ ] regression 100% 通过
- [ ] 基线文件留存备查

### 3.3 I-02：提取模块加载器

**目标**：将 `_import_report_modules()` 整体迁移到 `excel_module_loader.py`。

**步骤**：
1. 创建 `src/python/report/excel_module_loader.py`
2. 移动 `_import_report_modules` 函数，重命名为 `load_report_modules`
3. 搬运所有依赖 import（`logging`、`ProgressReporter`、`_Timer` 等）
4. `excel_generator.py` 顶部添加 `from src.python.report.excel_module_loader import load_report_modules`
5. 将 `generate_excel_report` 内的调用改为 `modules = load_report_modules(prog)`
6. 验证三步曲：
   ```bash
   python -c "import ast; ast.parse(open('src/python/report/excel_module_loader.py').read())"
   python -c "from src.python.report.excel_generator import generate_excel_report"
   python -m pytest src/test/unit/report/test_excel_generator.py -v -x --tb=short
   ```

**验收标准**：
- [ ] `excel_module_loader.py` 存在，包含 `load_report_modules()`
- [ ] `excel_generator.py` 不再定义 `_import_report_modules`
- [ ] 三步验证全部通过
- [ ] 文件行数减少 ≈126 行

**回退方案**：`git revert HEAD`（单次提交）

### 3.4 I-03：提取 Sheet 工厂

**目标**：将 `_create_sheets` + `_should_create_sheet` 迁移到 `excel_sheet_factory.py`。这是测试影响最大的提取操作。

**步骤**：
1. 创建 `src/python/report/excel_sheet_factory.py`
2. 移动 `_should_create_sheet` → `should_create_sheet`
3. 移动 `_create_sheets` → `create_sheets`
4. 搬运依赖（`set_sheet_title`、`Worksheet` 类型等）
5. `excel_generator.py` 从 `excel_sheet_factory` 导入
6. **更新测试文件**（共 4 个）：
   - `test_excel_generator.py`（3 处 `_create_sheets` 引用 → 改为 `excel_sheet_factory`）
   - `test_excel_report_structure.py`（**9 处** `_create_sheets` 引用 → 统一改）
7. 验证三步曲

> ⚠ **关键风险**：`test_excel_report_structure.py` 有 9 处分散的 `from src.python.report.excel_generator import _create_sheets`。建议用 sed 批量替换：
> ```bash
> sed -i 's|from src.python.report.excel_generator import _create_sheets|from src.python.report.excel_sheet_factory import create_sheets|g' \
>   src/test/unit/report/test_excel_report_structure.py
> sed -i 's|\b_create_sheets\b|create_sheets|g' \
>   src/test/unit/report/test_excel_report_structure.py
> ```
> `test_excel_generator.py:TestCreateSheets` 类似处理。

**验收标准**：
- [ ] `excel_sheet_factory.py` 存在
- [ ] 4 个测试文件导入路径已更新
- [ ] 三步验证全部通过
- [ ] 文件行数减少 ≈25 行

**回退方案**：`git revert HEAD`

### 3.5 I-04：提取行情数据解析

**目标**：将 `_resolve_market_data` + `_resolve_indices` 迁移到 `excel_market_data.py`。

**步骤**：
1. 创建 `src/python/report/excel_market_data.py`
2. 移动两个函数，重命名为 `resolve_market_data` / `resolve_indices`
3. 搬运 `_Timer` import、`classify_holdings`、`get_last_trading_day` 等依赖
4. `excel_generator.py` 导入新模块
5. 验证三步曲

**验收标准**：
- [ ] 外部传入 details/a_indices/us_indices 时仍正确复用
- [ ] 无 details 时内部获取逻辑正常
- [ ] 行情全零时 `add_error` 触发
- [ ] 三步验证通过
- [ ] 文件行数减少 ≈70 行

**回退方案**：`git revert HEAD`

### 3.6 I-05：提取核心内容页签写入

**目标**：将 `_write_content_sheets` 迁移到 `excel_content_sheets.py`。

**步骤**：
1. 创建 `src/python/report/excel_content_sheets.py`
2. 移动 `_write_content_sheets` → `write_content_sheets`
3. 搬运 `_Timer` 等依赖
4. `excel_generator.py` 导入新模块
5. 验证三步曲

**验收标准**：
- [ ] 4 个核心页签（汇总/分类/穿透/基金业绩）写入正常
- [ ] 穿透结果正确返回
- [ ] 三步验证通过
- [ ] 文件行数减少 ≈30 行

**回退方案**：`git revert HEAD`

### 3.7 I-06：提取新闻 + 预警页签写入

**目标**：将 `_write_news_and_early_warning` 迁移到 `excel_news_warning.py`。

**步骤**：
1. 创建 `src/python/report/excel_news_warning.py`
2. 移动 `_write_news_and_early_warning` → `write_news_and_early_warning`
3. **保留内部 inline import**（`try: from src.python.report.news_correlation import write_news_sheet, build_news_data`）— 不改变惰性加载语义
4. `excel_generator.py` 导入新模块
5. 验证三步曲

**验收标准**：
- [ ] `include_news=False` 时跳过
- [ ] 外部传入 `news_data` 时正确复用
- [ ] 无外部数据时内部 `build_news_data` 调用正常
- [ ] 新闻模块 ImportError 时 `add_error` 触发
- [ ] 三步验证通过
- [ ] 文件行数减少 ≈60 行

**回退方案**：`git revert HEAD`

### 3.8 I-07：提取 B 系列页签写入 + 消除 3 重复代码

**目标**：将 `_write_b_series_sheets` 迁移到 `excel_b_series.py`，同时消除 3 个子模块间的重复代码模式（详见 D11）。

**步骤**：
1. 创建 `src/python/report/excel_b_series.py`
2. 移动 `_write_b_series_sheets` → `write_b_series_sheets`
3. **保留惰性加载**：4 个 `fetch_fund_holdings`/`_is_fund` 的 inline import 不提升到模块级，保持 `try: from ... except ImportError` 原样
4. **新增 `_process_b_module` 辅助函数** — 将重合度/集中度/风格 3 个子模块共享的「inline import → fund_codes 过滤 → fetch_fund_holdings 循环 → 异常处理」模板抽取为可复用函数
   ```python
   def _process_b_module(
       holdings: list,
       data: dict,
       process_fn: Callable,
       prog: ProgressReporter,
   ) -> tuple[list[str], dict[str, dict]]:
       """B 系列模块的通用数据准备模板。
       
       每个模块保持独立 try/except，一个模块异常不影响其他。
       """
       from src.python.fetcher.fund import fetch_fund_holdings
       from src.python.report.fund_performance import _is_fund
       fund_codes = list(dict.fromkeys(h.code for h in holdings if _is_fund(h)))
       result_holdings = {}
       for code in fund_codes:
           fh = fetch_fund_holdings(code)
           if fh and fh.get("holdings"):
               result_holdings[code] = {
                   "name": fh.get("name", code),
                   "holdings": fh["holdings"],
               }
       return fund_codes, result_holdings
   ```
5. 基金经理变更监控保持独立逻辑（不通用）
6. `excel_generator.py` 导入新模块
7. 验证三步曲

**验收标准**：
- [ ] `enable_b_series=False` 时跳过
- [ ] 4 个子模块（基金经理/重合度/集中度/风格）写入正常
- [ ] 基金数 < 2 时重合度/集中度/风格正确跳过
- [ ] **3 个重复的 inline import + filtering 模板已消除**
- [ ] 各模块异常隔离（一个失败不影响其他） — `_process_b_module` 内异常不影响后续模块
- [ ] 三步验证通过
- [ ] 文件行数减少 ≈170 行

**回退方案**：`git revert HEAD`

### 3.9 I-08：提取 LLM 分析章节 + 用量页签

**目标**：将 `_write_llm_section_and_usage` + `_build_llm_usage_sheet` 迁移到 `excel_llm_usage.py`。这是测试影响最大的提取操作。

**步骤**：
1. 创建 `src/python/report/excel_llm_usage.py`
2. 移动 `_write_llm_section_and_usage` → `write_llm_section_and_usage`
3. 移动 `_build_llm_usage_sheet` → `build_llm_usage_sheet`
4. 搬运 `MODULE_KEYS`、`DISPLAY_REASON` 等模块级常量
5. 搬运 `FAIL_REASON_DISABLED`、`_LLM_MODULE_FAILURE` 等 import
6. `excel_generator.py` 导入新模块
7. **更新测试文件**（共 3 个）：
   - `test_excel_generator.py:TestBuildLlmUsageSheet`（1 处 `_build_llm_usage_sheet` 引用）
   - `test_llm_placeholder.py:57`（1 处 `_build_llm_usage_sheet` 引用）
   - `test_llm_scenarios.py:899`（1 处 `_build_llm_usage_sheet` 引用）
8. 验证三步曲 + 专门测试：
   ```bash
   python -m pytest src/test/unit/report/test_excel_generator.py::TestBuildLlmUsageSheet -v -x
   python -m pytest src/test/unit/llm/test_llm_placeholder.py -v -x
   ```

**验收标准**：
- [ ] `include_llm=False` 时跳过
- [ ] 5 状态判定正确（缓存/成功/禁用/失败/无状态跳过）
- [ ] `excel_module_info` 为空时不调用 `write_llm_usage_sheet`
- [ ] 3 个测试文件的导入路径已更新
- [ ] 三步验证 + 专门测试全部通过
- [ ] 文件行数减少 ≈115 行

**回退方案**：`git revert HEAD`

### 3.10 I-09：导入路径统一验证 + 冒烟测试

**目标**：确认所有 inline import 已被消除或正确保留 + 新增提取模块的冒烟测试。

**步骤**：
1. **全局 grep 验证** — 确认 `excel_generator.py` 中不再包含 `try: from ... except ImportError`（除 `_write_news_and_early_warning` 和 `_write_b_series_sheets` 保留的惰性加载）
2. **grep 残留检查**：
   ```bash
   grep -rn "from src.python.report.excel_generator import _" src/ --include="*.py"
   ```
   期望结果：空（无私有函数引用）
3. **`excel_generator.py` C14 验证** — 确认模块级变量仅为不可变常量
4. **新增冒烟测试文件**：
   - `test_excel_module_loader.py`（`pytestmark = [pytest.mark.unit, pytest.mark.unit_report]`）
   - `test_excel_sheet_factory.py`（从 `test_excel_generator.py` 迁移 `TestCreateSheets`）
   - `test_excel_market_data.py`（`resolve_market_data` 和 `resolve_indices` 基本路径）
   - `test_excel_b_series.py`（`write_b_series_sheets` 跳过/异常隔离）
   - `test_excel_llm_usage.py`（从 `test_excel_generator.py` 迁移 `TestBuildLlmUsageSheet`）
5. 运行所有新测试验证

**验收标准**：
- [ ] `excel_generator.py` 不再导入任何残留的私有函数
- [ ] 全局 grep 无残留 `from src.python.report.excel_generator import _`
- [ ] 5 个新冒烟测试文件创建并通过
- [ ] `test_excel_generator.py` 剩余测试全部通过（旧 mock 路径不变）
- [ ] `test_integration.py` 模块级 import `generate_excel_report` 正常

**回退方案**：`git revert HEAD`

### 3.11 I-10：文档同步 + 全量回归

**目标**：同步文档 + 最终全量回归验证。

**步骤**：
1. 更新 `docs-stm/manuals/datasource-and-folders.md` 目录树：
   - 新增 6 个 `excel_*.py` 文件条目
   - 描述前缀"从 excel_generator.py 拆分"
2. 更新 `docs-stm/managements/technical.md`：
   - 报告生成管线章节：新增提取模块层次
   - 模块间依赖关系章节：分离后的依赖图
3. 更新 `docs-stm/managements/review-findings.md`：R-206 改为"✅ 已完成"，摘要行保留
4. 运行 pipeline 回归：
   ```bash
   python scripts/test_runner.py --mode regression
   ```
5. 边缘测试验证：
   ```bash
   python -m pytest src/test/unit/report/test_excel_generator_edge.py -v
   ```

**验收标准**：
- [ ] `datasource-and-folders.md` 目录树包含所有新模块
- [ ] `technical.md` 模块依赖图更新
- [ ] `review-findings.md` R-206 标记为已完成
- [ ] regression 模式 100% 通过
- [ ] 边缘测试 100% 通过

**回退方案**：`git checkout dev -- docs-stm/`（整批文档回退）

---

## 4. 风险分析（优化版）

### 4.1 风险矩阵

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|:---|:-----|:----:|:----:|:----:|:---------|
| R1 | **模块间 import 遗漏** | 中 | 高 | 🔴 | 每轮三步验证 + pipeline 回归 |
| R2 | **`test_excel_report_structure.py` 9 处 `_create_sheets` 导入遗漏** | 中 | 高 | 🔴 | 用 sed 批量替换 + 人工复查 |
| R3 | **`test_llm_scenarios.py` + `test_llm_placeholder.py` 的 `_build_llm_usage_sheet` 导入遗漏** | 中 | 中 | 🟡 | I-09 全局 grep 捕获 |
| R4 | **惰性加载语义改变**（inline import 提升到模块级） | 低 | 中 | 🟡 | I-06/I-07 明确标记"保留 inline import" |
| R5 | **`test_integration.py` 模块级 import 异常**（文件顶部 import `generate_excel_report`，若 excel_generator 导入链断裂则整文件失败） | 低 | 高 | 🟡 | 每轮后运行 `python -m pytest src/test/scenario/basic/test_integration.py -x --tb=short` |
| R6 | **C14 违规**：提取模块意外创建可变的模块级 dict/list 作为跨函数通信渠道 | 低 | 中 | 🟡 | 每个提取模块代码审查，确认模块级变量为不可变常量 |
| R7 | **`handlers_report.py` 导入链断裂**（唯一非测试引用） | 低 | **高** | 🟡 | 每轮三步验证中 `python -c "from src.python.report.excel_generator import generate_excel_report"` 已覆盖 |
| R8 | **回归测试覆盖不足**（拆分引入行为偏差但测试未覆盖） | 低 | 中 | 🟡 | I-10 全量 --mode regression 验证 |

### 4.2 每轮必做验证

每轮提取后，必须通过以下 **3 步验证 + 1 项专项**：

```bash
# Step 1: 语法检查
python -c "import ast; ast.parse(open('src/python/report/excel_generator.py').read())"
# Step 2: 主入口导入（验证 handlers_report.py 链路）
python -c "from src.python.report.excel_generator import generate_excel_report"
# Step 3: 单元测试（快速）
python -m pytest src/test/unit/report/test_excel_generator.py -v -x --tb=short
# Step 4 (每两轮至少一次): 集成测试链路
python -m pytest src/test/scenario/basic/test_integration.py -x --tb=short -q
```

---

## 5. 收益评估

### 5.1 直接收益

| 指标 | 拆分前 | 拆分后 | 变化 |
|:-----|:------:|:------:|:----:|
| `excel_generator.py` 行数 | 693 | < 80 | **-88%** |
| 函数/文件 | 11 | 1~2 | 单一职责 |
| 模块导入集中管理 | 分散 7 处 inline import | 统一在 `excel_module_loader.py` | 集中化 |
| LLM 状态判定逻辑 | 混在编排器中 | 独立 `excel_llm_usage.py` | 隔离化 |
| 页签创建逻辑 | 混在编排器中 | 独立 `excel_sheet_factory.py` | 独立化 |

### 5.2 间接收益

- **新增页签只需 2 步**：注册表加一行 + `excel_module_loader.py` 加一行 import → 无需碰编排器
- **测试定位更快**：每个模块职责明确，测试文件按模块组织
- **降低认知负担**：新人只需理解 1 个入口 + N 个专用模块
- **分支合并冲突减少**：不同模块的变更不会冲突

### 5.3 技术债务（明确遗留）

- I-07 提取后 `excel_b_series.py` 仍是最新最大文件（≈170 行），4 个子模块内部对称循环未消除
- `_write_news_and_early_warning` 的 inline import 未消除（保留惰性加载语义）
- `excel_content_sheets.py`、`excel_news_warning.py` 提取后仍薄（~30-60 行），但维持稳定无需继续拆分
- `modules` dict 字符串键访问（无类型检查）是既有架构债务，未被本计划解决
- I-07 的 `_process_b_module` 辅助函数是已有代码的提取重组，不引入新债务

---

## 6. 深层复盘分析（D11-D15）

### D11：B 系列 3 重复代码模式

经过代码验证，`_write_b_series_sheets`（行 304-470）中 3 个子模块（重叠矩阵/集中度/风格分析）具有**完全相同的代码结构**：

```python
def _write_b_series_sheets(...):
    # ── 基金经理变更监控（行 314-332）：独特逻辑，无模板化
    ...

    # ── 持仓重合度矩阵（行 338-386）：模板 A
    try:
        from src.python.fetcher.fund import fetch_fund_holdings
        from src.python.report.fund_performance import _is_fund
        fund_codes = list(dict.fromkeys(h.code for h in holdings if _is_fund(h)))
        if len(fund_codes) >= 2:
            fund_holdings = {}
            for code in fund_codes:
                fh = fetch_fund_holdings(code)
                ...
        ...
    except Exception as e:
        prog.add_error("...数据获取失败")

    # ── 持仓集中度监控（行 392-428）：模板 A（完全相同的 try→import→filter→loop→write 模式）
    # ── 基金风格分析（行 434-470）：模板 A（完全相同的 try→import→filter→loop→write 模式）
```

**模板 A 在每个子模块中重复了 4 个结构点**：
1. Lazy inline import `fetch_fund_holdings` + `_is_fund`
2. `list(dict.fromkeys(h.code for h in holdings if _is_fund(h)))` 过滤
3. `for code in fund_codes: fh = fetch_fund_holdings(code)` 循环
4. `except Exception as e: logger.warning(...); prog.add_error(...)` 异常处理

**重复成本估算**：
- 每份模板 ≈12 行 import + 过滤 + 循环样板，3 份 = **36 行重复代码**
- 提取为共用辅助函数可压缩 ≈30 行
- 未来新增 B 系列模块时若仍按模板复制粘贴，重复进一步扩大

**建议**：I-07 提取 `_write_b_series_sheets` 时引入 `_process_b_module` 辅助函数：

```python
def _process_b_module(
    holdings: list,
    module_name: str,
    process_fn: Callable,
    prog: ProgressReporter,
) -> Any:
    """B 系列模块的通用处理模板。"""
    try:
        from src.python.fetcher.fund import fetch_fund_holdings
        from src.python.report.fund_performance import _is_fund
        fund_codes = list(dict.fromkeys(h.code for h in holdings if _is_fund(h)))
        ...
    except Exception as e:
        prog.add_error(f"{module_name}数据获取失败")
```

**风险**：引入辅助函数可能改变异常传播行为（原代码每个模块独立 try/except，共用辅助函数后一个模块的异常不会影响其他模块 — 这与原行为一致，即本来就是独立的）。**低风险**。

### D12：`_Timer` import 分布

代码验证结果：

| 使用 `_Timer` 的函数 | 行位置 | 提取目标模块 |
|:---------------------|:------:|:------------|
| `_resolve_market_data` | 167, 170 | `excel_market_data.py`（I-04） |
| `_resolve_indices` | 210 | `excel_market_data.py`（I-04） |
| `_write_llm_section_and_usage` | 481 | `excel_llm_usage.py`（I-08） |
| `generate_excel_report` | 685 | `excel_generator.py`（保留） |

**结论**：
- `excel_market_data.py` 需从 `progress.py` 导入 `_Timer`
- `excel_llm_usage.py` 需从 `progress.py` 导入 `_Timer`
- `excel_generator.py`（编排器）保留 `_Timer` 导入用于保存
- `excel_news_warning.py` 和 `excel_b_series.py` **不**使用 `_Timer`
- `excel_content_sheets.py` 和 `excel_sheet_factory.py` **不**使用 `_Timer`
- 每模块独立导入 `_Timer` 更清晰，不产生循环依赖，**无需集中化**

### D13：`modules` dict 键名脆弱性

**键名清单**（来自 `_import_report_modules` 的返回字典）：

| 键名 | 消费方 | 类型安全 |
|:-----|:-------|:--------:|
| `"fetch_indices"` | `_resolve_indices` 行 212 | ❌ 字符串 |
| `"fetch_us_indices"` | `_resolve_indices` 行 213 | ❌ 字符串 |
| `"create_workbook"` | `generate_excel_report` 行 660 | ❌ 字符串 |
| `"save_workbook"` | `generate_excel_report` 行 661 | ❌ 字符串 |
| `"write_summary_sheet"` | `_write_content_sheets` 行 224 | ❌ 字符串 |
| `"write_category_sheet"` | `_write_content_sheets` 行 230 | ❌ 字符串 |
| `"write_market_value_sheet"` | `_resolve_market_data` 行 150 | ❌ 字符串 |
| `"write_penetration_sheet"` | `_write_content_sheets` 行 236 | ❌ 字符串 |
| `"compute_penetration_top10"` | `_write_content_sheets` 行 233 | ❌ 字符串 |
| `"write_fund_performance_sheet"` | `_write_content_sheets` 行 239 | ❌ 字符串 |
| `"detect_manager_changes"` | `_write_b_series_sheets` 行 314 | ❌ 字符串 |
| `"write_fund_manager_sheet"` | `_write_b_series_sheets` 行 325 | ❌ 字符串 |
| `"compute_overlap_matrix"` | `_write_b_series_sheets` 行 335 | ❌ 字符串 |
| `"write_overlap_matrix_sheet"` | `_write_b_series_sheets` 行 336 | ❌ 字符串 |
| `"compute_concentration"` | `_write_b_series_sheets` 行 389 | ❌ 字符串 |
| `"write_concentration_sheet"` | `_write_b_series_sheets` 行 390 | ❌ 字符串 |
| `"analyze_style_for_all_funds"` | `_write_b_series_sheets` 行 431 | ❌ 字符串 |
| `"write_style_sheet"` | `_write_b_series_sheets` 行 432 | ❌ 字符串 |
| `"classify_holdings"` | `_resolve_market_data` 行 151 | ❌ 字符串 |
| `"get_last_trading_day"` | `_resolve_market_data` 行 197 | ❌ 字符串 |
| `"price_update_status"` | `_resolve_market_data` 行 194 | ❌ 字符串 |
| `"_generate_details"` | `_resolve_market_data` 行 173 | ❌ 字符串 |

**共 22 个字符串键**。任意一个拼写错误在 `modules.get(key)` 时不会触发 IDE 警告、不会触发 mypy，仅在运行时静默返回 None，然后 `prog.call_sheet` 或条件判断时跳过，**无报错无声丢失**。

**缓解措施**：
- I-09 新增的冒烟测试中包含键名验证 fixture：
  ```python
  def test_module_keys(monkeypatch):
      from src.python.report.excel_module_loader import load_report_modules
      from src.python.report.progress import SilentProgressReporter
      modules = load_report_modules(SilentProgressReporter())
      assert modules.get("write_market_value_sheet") is not None
      assert modules.get("detect_manager_changes") is not None
      # ... 验证全部 22 个键
  ```
- 此测试确保提取后所有键名在消费方正确

**风险评级**：🟡 中（运行时静默失败，测试可捕获）。

### D14：测试文件 import 路径更新范围不一致

问题验证：I-03 总览表标注「**4** 文件需更新」，但 I-03 详细步骤中只提及 2 个测试文件：

| 文件 | `_create_sheets` 引用 | 是否被 I-03 步骤覆盖 |
|:-----|:--------------------:|:------------------:|
| `test_excel_generator.py` | 3 处 | ✅ |
| `test_excel_report_structure.py` | **9 处** | ✅ |
| `test_excel_generator_edge.py` | 0 处（只导入 `generate_excel_report`） | ❌ 不需要 |
| `test_llm_placeholder.py` | 0 处（只导入 `_build_llm_usage_sheet`） | ❌ 不需要（I-08 才涉及） |
| `test_llm_scenarios.py` | 0 处（只导入 `_build_llm_usage_sheet`） | ❌ 不需要（I-08 才涉及） |

**结论**：实际 I-03 只需更新 **2 个文件**，总览表的「4」是笔误。**或**表头的「4」把全部要修改的文件数加总了，建议修正为 2。

**此外，还存在 `test_excel_report_structure.py` 的双重修改风险**：
- R-206 I-03：将 `from src.python.report.excel_generator import _create_sheets` → `from src.python.report.excel_sheet_factory import create_sheets`
- R-207 I-03b：将 `from src.python.report.summary import _set_column_widths` → `from src.python.report.summary_llm_usage import _set_column_widths`

如果 R-206 和 R-207 依次执行，`test_excel_report_structure.py` 会经历两轮 import 修改（9+2 处变化）。

**建议**：I-03 步骤中明确标注修改范围为 **2 个文件**，并建议按 R-206 → R-207 顺序执行以避免两个拆分项目同时修改同一测试文件。

### D15：`_write_llm_section_and_usage` 的 `_build_llm_usage_sheet` 裸调用

验证 code review：

```python
# line 473-495
def _write_llm_section_and_usage(...):
    ...
    _build_llm_usage_sheet(sheets, prog)   # ← bare name 调用（line 495）

# line 498
def _build_llm_usage_sheet(sheets, prog):   # ← 被调用方（line 498）
    from src.python.report.summary import write_llm_usage_sheet
    ...
```

I-08 计划将**两个函数同时**提取到 `excel_llm_usage.py`。在新模块中，两者仍为同一模块内的函数，bare name 调用仍有效。**无风险**。

**但有一个潜在问题**：`_build_llm_usage_sheet` 的 inline import `from src.python.report.summary import write_llm_usage_sheet`（行 508）。这个导入依赖在提取后变为 `excel_llm_usage.py → summary.py`。此时 `summary.py` 中的 `write_llm_usage_sheet` 应该仍存在（除非 R-207 先运行将其提取到 `summary_llm_usage.py`）。

**顺序依赖性**：
- R-206 先 + R-207 后：`excel_llm_usage.py` 导入 `summary.write_llm_usage_sheet` → R-207 完成后 `summary.py` 保留 re-export → ✅ 保证
- R-207 先 + R-206 后：`summary.py` re-export 后 `write_llm_usage_sheet` 仍在 summary 名称空间 → I-08 提取时仍可正常导入 → ✅ 保证

**结论**：无论执行顺序均无风险。`summary.py` 的 re-export 策略使得 `from summary import write_llm_usage_sheet` 在 R-207 后仍然有效。

---

## 7. 风险矩阵优化（追加 D11-D15）

| # | 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|:---|:-----|:----:|:----:|:----:|:---------|
| R1 | 模块间 import 遗漏 | 中 | 🔴 | 高 | 每轮三步验证 |
| R2 | `test_excel_report_structure.py` 9 处导入遗漏 | 中 | 🔴 | 高 | sed 批量替换 + 复查 |
| R3 | `test_llm_*` 的 `_build_llm_usage_sheet` 导入遗漏 | 中 | 🟡 | 中 | I-09 全局 grep |
| R4 | 惰性加载语义改变 | 低 | 🟡 | 中 | 保留 inline import |
| R5 | `test_integration.py` 模块级 import 断裂 | 低 | 🔴 | 高 | 每轮 `test_integration.py` 验证 |
| R6 | C14 违规（全局变量） | 低 | 🟡 | 中 | 提取模块代码审查 |
| R7 | `handlers_report.py` 导入断裂 | 低 | 🔴 | 高 | 三步验证已覆盖 |
| R8 | 回归测试覆盖不足 | 低 | 🟡 | 中 | I-10 --mode regression |
| **R9** | **B 系列辅助函数引入异常传播变化** | 低 | 中 | 🟡 | 每个模块保持独立 try/except，与原行为一致 |
| **R10** | **`modules` 字典键名拼写错误** | 中 | 中 | 🟡 | I-09 新增键名验证 fixture |
| **R11** | **`test_excel_report_structure.py` 双重修改（R-206 + R-207 先后改同一文件）** | 中 | 低 | 🟢 | 按 R-206 → R-207 顺序执行 |
| **R12** | **`_write_news_and_early_warning` 中 2 个 inline import 来自同一模块不同作用域** | 低 | 低 | 🟢 | 提取到 `excel_news_warning.py` 可合并为一次性导入 |

---

## 8. 进度追踪

| 轮次 | 状态 | 分支 | 提交语 |
|:----:|:----:|:-----|:-------|
| I-01 | ⏳ 待启动 | `dev-feat/excel-split` | `feat(R-206/I-01): baseline capture` |
| I-02 | ⏳ 待启动 | 续上 | `feat(R-206/I-02): extract module loader` |
| I-03 | ⏳ 待启动 | 续上 | `feat(R-206/I-03): extract sheet factory` |
| I-04 | ⏳ 待启动 | 续上 | `feat(R-206/I-04): extract market data` |
| I-05 | ⏳ 待启动 | 续上 | `feat(R-206/I-05): extract content sheets` |
| I-06 | ⏳ 待启动 | 续上 | `feat(R-206/I-06): extract news warning` |
| I-07 | ⏳ 待启动 | 续上 | `feat(R-206/I-07): extract B series` |
| I-08 | ⏳ 待启动 | 续上 | `feat(R-206/I-08): extract LLM usage` |
| I-09 | ⏳ 待启动 | 续上 | `feat(R-206/I-09): test adapt + smoke` |
| I-10 | ⏳ 待启动 | 续上 | `feat(R-206/I-10): doc sync + regression` |
