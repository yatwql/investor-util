# 如何驱动测试 — 测试组合运行指南

## 概述

本项目的测试框架基于 **pytest**，通过标记（marker）分组支持灵活组合运行。使用 `scripts/test_runner.py` 脚本统一驱动，自动输出结构化报告。

## 前置条件

```bash
# 安装测试依赖
pip install pytest pytest-html pytest-mock
# 可选：覆盖率报告
pip install pytest-cov coverage
```

## 快速开始

```bash
# 查看所有可用选项
python scripts/test_runner.py --help

# 运行全量测试（默认）
python scripts/test_runner.py

# 全量单元测试（含 edge/data）
python scripts/test_runner.py --mode unit

# 常规单元测试（排除 edge/data）
python scripts/test_runner.py --mode standard

# 快速回归 — 提交前验证（~25s）
python scripts/test_runner.py --mode regression

# 合入验证 — PR 前检查（~10min）
python scripts/test_runner.py --mode verify

# 仅运行业务场景测试
python scripts/test_runner.py --mode scenario

# 仅运行边缘/异常场景测试
python scripts/test_runner.py --mode edge

# 运行全量 + 行覆盖率报告
python scripts/test_runner.py --coverage

# 冒烟测试（~2s 快速验证核心通路）
python scripts/test_runner.py --mode smoke

# 集成测试（同场景 107 项）
python scripts/test_runner.py --mode integration

# 数据正确性验证（~10s）
python scripts/test_runner.py --mode data

# 全量测试（1938 项，~26min）
python scripts/test_runner.py --mode all
```

## 测试模式详解

测试框架围绕两个概念组织：**pytest 标记（marker）** 是测试用例的固有属性（标注"这是什么测试"）；**`--mode`** 是 `scripts/test_runner.py` 脚本对标记的预定义组合（定义"应该运行哪些测试"）。每个 mode 对应一个或多个标记表达式，脚本解析后传给 `pytest -m` 执行。

### 三级验证流水线

项目推荐的三道质量门禁，按开发阶段逐级收紧：

- **提交前验证（`--mode regression`）** — 每次代码变更后、commit 前必须执行。覆盖全部 107 项业务场景测试，确保 S1-S20 端到端用户路径和 T1-T16 日期/时间场景不被破坏。约 25s 即可完成。是编辑-验证循环中的第一道屏障，核心原则是"够快才能频繁跑，频繁跑才能尽早发现问题"。
- **合入验证（`--mode verify`）** — 准备合并到 master 前必须执行。在 regression 的业务场景基础上，增加 `unit_core`（核心基础设施：缓存引擎、数据模型、注册表）、`unit_providers`（数据源 Provider：腾讯、东方财富、天天基金等）、`unit_fetcher`（数据获取调度：价格、指数、行业分类）三个关键单元模块。共 668 项，确保数据从抓取→缓存→计算的整条管道通畅且正确。约 10min，适合作为 PR CI 门禁或合入前的手动检查。
- **发布验证（`--mode all`）** — 发布版本（打 tag/release）前必须执行。全量 1938 项测试全部过一遍，包括所有单元测试和场景测试、LLM 模块测试、UI 测试等。确保任何改动不会在新版本中遗漏。约 26min，适合发布前的夜间或定时全量回归。

> `regression` 与 `scenario` 底层使用相同的标记表达式（`-m "scenario"`），测试项数同为 107。前者是语义别名——强调"提交前快速回归"的用途定位；后者是分类名——强调"业务场景测试"的数据性质。两者可互相替代，但建议按使用场合选用对应名称以增强代码意图可读性。

**推荐工作流：**

```
编码 → --mode regression(25s) → commit → 多次积累 → --mode verify(10min) → merge → release前 → --mode all(26min)
                                  ↑
                          此处可反复跑 regression
```

在一次典型开发周期中：
1. 修改代码后，运行 `--mode regression`（25s）确认业务场景没有走歪
2. 如果改了 Provider、缓存或数据获取逻辑，再跑 `--mode verify`（10min）确认整条管道通畅
3. 通过后 commit，积累多次提交后准备合并到 master
4. 合并前跑 `--mode verify` 作为合入门禁
5. 发布版本前跑 `--mode all`（26min）全量扫一遍

### 回归测试级别

每个回归项按影响范围分四级，与三级流水线的对应关系：

| 级别 | 定义 | 阻断点 | 对应的流水线阶段 |
|:-----|:-----|:-------|:----------------|
| **P0** | 阻塞提交 — 核心功能不可用 | 不得 commit | ① `regression`（~25s） |
| **P1** | 阻塞合入 master | 不得 merge | ② `verify`（~10min） |
| **P2** | 阻塞发布 | 不得 release | ③ `all`（~26min） |
| **P3** | 建议修复 | 不阻断 | — |

P0 问题必须在 commit 前解决，否则代码不应进入版本控制。P1 问题允许提交但不允许合入主分支。P2 允许合入主分支但不应发布版本。P3 属于已知缺陷或待优化项，可带缺陷发布。

### 模式与覆盖范围说明

每种 `--mode` 对应一组 pytest 标记表达式，由 `scripts/test_runner.py` 转换为 `pytest -m "<表达式>"` 执行。各模式的覆盖范围存在包含与被包含关系，理解这种关系有助于缩小验证范围以快速反馈：

#### 🔷 单元测试系列（`unit` / `standard`）

- **`--mode unit`** 覆盖所有标记为 `unit_*` 的测试（8 个子组：providers、fetcher、llm、news、report、config、core、ui），不含场景测试。这是对代码库中各独立模块的功能正确性验证，所有网络请求均为 mock，不依赖外部 API。
- **`--mode standard`** 在 `unit` 基础上排除 edge（异常边界）和 data（数据正确性）两个跨类标记，仅保留"常规路径"的单元测试。适用于日常开发中快速验证模块本身逻辑正确，不需要关心边界情况。

#### 🔷 场景测试系列（`scenario` / `regression` / `integration` / `verify`）

- **`--mode scenario`** 覆盖所有标记为 `scenario_*` 的测试（4 个子组：basic、extended、llm、datetime），共 107 项。这些测试模拟真实用户操作（如菜单 E/H/B/L 生成报告），组合多个模块进行端到端验证。
- **`--mode regression`** 与 `--mode scenario` 完全相同，但语义定位为"提交前回归验证"。建议在 git hook 或 CI 前置检查中使用此名称，使流水线意图更加清晰。
- **`--mode integration`** 覆盖 `scenario or integration`，在场景测试基础上增加显式标注为 `integration` 的集成契约测试。当前 `integration` 标记尚未分配独立测试项，因此实际项数与 `scenario` 相同（107 项）。
- **`--mode verify`** 覆盖范围最广的组合模式（`scenario or unit_core or unit_providers or unit_fetcher`），包含了全部场景测试 + 核心基础设施 + 数据源 Provider + 数据获取调度。这是"快速回查"的上限——确保数据管道整条链路正常，但跳过纯 UI、纯 LLM 等不直接影响数据流的模块。

#### 🔷 专项验证系列（`edge` / `data` / `smoke`）

- **`--mode edge`** 仅运行标记为 `edge` 的测试（39 项），覆盖各种异常和边界情况：零值、空数据集、并发竞态、Unicode、时区安全、文件系统边界等。适用于修改了函数内部错误处理逻辑后的针对性验证。
- **`--mode data`** 仅运行标记为 `data` 的测试（28 项），覆盖数据精确性：市值=价格×份额、盈亏=市值-成本、收益率=盈亏÷成本（成本>0）、穿透 TOP10 占比归一化等。适用于修改了数值计算逻辑后的回归。
- **`--mode smoke`** 仅运行标记为 `smoke` 的测试（24 项），从 6 个全流程关键节点各选 4 项最快基础测试：核心数据模型→入口读取→分类计算→报告输出→启动依赖→数据获取。全部为纯内存计算、无 IO、每项 <0.1s，合计 ~2s。适用于部署后冒烟或极速"通不通"检查。

#### 🔷 全量（`all`）

- **`--mode all`** 不设任何标记过滤（`pytest src/test/`），运行全部 1938 项测试。包含所有单元测试、场景测试、跨类标记测试。约 26min，作为发布前的最终全量回归。

#### 多模式组合

`--mode` 支持逗号分隔同时运行多个模式：

```bash
# 同时运行场景测试和边缘测试
python scripts/test_runner.py --mode scenario,edge
```

脚本按 MODES 字典定义的 order 顺序依次执行各模式，结果汇总到同一份 HTML 报告中。适用于 CI 流水线中按阶段逐步收紧的场景。

## 测试覆盖统计

按不同的 `--mode` / pytest 标记统计当前（2026-07-02）测试覆盖规模：

### 模式对应测试量

| `--mode` 值 | 覆盖项数 | 典型耗时 |
|:------------|:--------:|:---------|
| `unit` | 1810 | ~25min |
| `standard` | 1743 | ~25min |
| `scenario` | 107 | ~25s |
| `regression` | 107 | ~25s |
| `verify` | 668 | ~10min |
| `integration` | 107（同 scenario） | ~25s |
| `edge` | 39 | ~10s |
| `data` | 28 | ~10s |
| `all` | 1938 | ~26min |
| `smoke` | 24 | ~2s |

### 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py` | 166 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain) | `unit/fetcher/test_fetcher*.py` + `test_fund.py` + `test_chain.py` | 118 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 176 |
| **报告生成** | `report/`(excel, html, category, penetration, fund_performance, market_value, summary, early_warning, news_correlation, qdii_timezone) | `unit/report/test_{excel_generator,excel_writer,html_writer,category,summary,market_value,penetration,fund_performance,early_warning,news_correlation,qdii_timezone}.py` 等 15 文件 | 558 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, generators, markdown, pricing, prompts, session, skeleton) | `unit/llm/`(8 文件) + `scenario/llm/test_llm_scenarios.py` | 350 |
| **核心基础设施** | `cache.py`, `models.py`, `reader.py`, `registry.py`, `http_client.py`, `market_hours.py` | `unit/core/test_{cache,models,reader,registry,http_client,market_hours}.py` | 277 |
| **配置管理** | `config.py`, `constants.py` | `unit/config/test_config*.py` | 42 |
| **TUI 交互** | `tui*.py`, `handlers_*.py`, `main.py` | `unit/ui/test_{handlers,tui,tui_handlers,tui_menu,log_sanitize}.py` | 142 |
| **端到端业务场景** | 多模块组合（菜单 E/H/B/L → 读取 → 计算 → 报告 → LLM） | `scenario/`(basic, extended, llm, datetime 共 4 文件) | 107 |

### 场景测试分组（scenario）

| 标记 | 覆盖场景 | 覆盖项数 | 典型耗时 |
|:-------|:---------|:--------:|:---------|
| `scenario`（父标记） | S1-S20 + T1-T16 全量业务场景 | **107** | ~25s |
| ├─ `scenario_basic` | 基础业务链路 S1-S5 | 9 | ~2s |
| ├─ `scenario_extended` | 扩展业务场景 S6-S10 | 18 | ~5s |
| ├─ `scenario_llm` | LLM 场景组合 S11-S20 | 19 | ~5s |
| └─ `scenario_datetime` | 日期/时间场景 T1-T16 | 61 | ~15s |

### 单元测试分组（unit）

| 标记 | 覆盖模块 | 覆盖项数 | 典型耗时 |
|:-------|:---------|:--------:|:---------|
| `unit`（父标记） | 8 个子组合计 | **1810** | ~25min |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等） | 166 | ~2min |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业） | 118 | ~1.5min |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架） | 331 | ~4min |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 176 | ~2min |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入） | 558 | ~7min |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key） | 42 | ~30s |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表） | 277 | ~3.5min |
| └─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示） | 142 | ~2min |

### 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 | 典型耗时 |
|:-------|:---------|:--------:|:---------|
| `llm` | 全部 LLM 相关（unit_llm 331 + scenario_llm 19） | **350** | ~4min |
| `smoke` | 6 个关键节点各 4 项，共 24 项 | **24** | ~2s |
| `integration` | 集成/端到端流程测试（当前与 scenario 合并统计） | **107**（同 scenario） | ~25s |
| `edge` | 异常/边界场景 | **39** | ~10s |
| `data` | 数据正确性验证 | **28** | ~10s |

### LLM 标记与 API Key 说明

`llm` 标记的 350 项测试 **全部不需要真实 API key**（均为 mock 测试）：

| 测试文件 | mock 数 | 是否需 API key | 说明 |
|:---------|:-------:|:--------------|:-----|
| `unit/llm/test_fingerprint.py` | 0 处 | ❌ 不需要 | 纯逻辑：持仓指纹确定性计算 |
| `unit/llm/test_session.py` | 0 处 | ❌ 不需要 | 纯逻辑：会话用量跟踪 |
| `unit/llm/test_skeleton.py` | 0 处 | ❌ 不需要 | 纯逻辑：骨架结构测试，`"sk-xxx"` 仅作 dummy 值 |
| `unit/llm/test_llm_content.py` | 0 处 | ❌ 不需要 | 纯逻辑：内容截断/处理 |
| `unit/llm/test_llm_placeholder.py` | 1 处 | ❌ 不需要 | 占位符生成 |
| `unit/llm/test_circuit_breaker_recovery.py` | 15 处 | ❌ 不需要 | 熔断器逻辑，全部 mock |
| `unit/llm/test_api.py` | 103 处 | ❌ 不需要 | API 路由/重试，全部 mock |
| `unit/llm/test_llm.py` | 243 处 | ❌ 不需要 | LLM Manager 编排逻辑，全部 mock |
| `scenario/llm/test_llm_scenarios.py` | 35 处 | ❌ 不需要 | 场景流程，全部 mock |

> 全部 350 项 LLM 测试均为 mock，无需真实 API key。`-m "not llm"` 跳过的是 LLM 模块而非真实 API 依赖。

### Smoke 测试明细

| 节点 | 文件 | 测试方法 | 验证点 |
|:-----|:-----|:---------|:-------|
| **核心数据模型** | `unit/core/test_models.py` | `test_create_minimal` | 最简构造，所有字段必填 |
| | | `test_repr` | repr 含关键字段 |
| | | `test_eq_different` | 不同持仓不等 |
| | | `test_eq_same_values` | 相同字段值相等 |
| **入口读取** | `unit/core/test_reader.py` | `test_none_returns_empty` | `_safe_str(None)` → `""` |
| | | `test_string_stripped` | `_safe_str` 去除空格 |
| | | `test_number_to_string` | `_safe_str(513300)` → `"513300"` |
| | | `test_empty_string` | `_safe_str("")` → `""` |
| **分类计算** | `unit/report/test_category.py` | `test_qdii` | QDII → (基金, QDII) |
| | | `test_bond` | 含债 → (债券, 纯债) |
| | | `test_stock` | 6/0/3 开头 → (股票, A股) |
| | | `test_index_fund` | 5 开头 ETF → (基金, 指数) |
| **报告输出** | `unit/report/test_excel_generator.py` | `test_basic_generation` | 所有模块正常生成 |
| | | `test_summary_module_missing` | 模块缺失降级 |
| | | `test_sheet_exception_isolation` | 页签异常不阻塞其他 |
| | | `test_default_progress_reporter` | progress=None 不抛异常 |
| **启动依赖** | `unit/config/test_config.py` | `test_missing_file_returns_defaults` | 缺文件返回默认值 |
| | | `test_valid_config_read` | 完整配置正常读取 |
| | | `test_init_creates_default_config` | 初始化创建默认配置 |
| | | `test_set_and_get` | 写入后读取一致 |
| **数据获取** | `unit/providers/test_eastmoney.py` | `test_jsonp_format` | JSONP 提取 JSON |
| | | `test_pure_json` | 纯 JSON 原样返回 |
| | | `test_normal` | `_safe_float("1.2345")` |
| | | `test_empty_string` | `_safe_float("")` → 0.0 |

## 查看报告

每次运行后，测试报告输出到：

```
docs-stm/test-reports/latest/
├── index.html            # 汇总页（打开此文件查看总览）
├── unit/
│   └── report.html       # 单元测试（1810 项）
├── standard/
│   └── report.html       # 常规单元测试（1743 项）
├── scenario/
│   └── report.html       # 业务场景测试（107 项）
├── regression/
│   └── report.html       # 回归测试/场景别名（107 项）
├── verify/
│   └── report.html       # 合入验证（668 项）
├── integration/
│   └── report.html       # 集成测试（同 scenario 107 项）
├── edge/
│   └── report.html       # 边缘场景测试（39 项）
├── data/
│   └── report.html       # 数据正确性验证（28 项）
├── all/
│   └── report.html       # 全量测试（1938 项）
└── smoke/
    └── report.html       # 冒烟测试（24 项）
```

**打开方式**：直接用浏览器打开 `docs-stm/test-reports/latest/index.html`

## 直接使用 pytest 组合查询

```bash
# 查看指定标记下有哪些测试（不执行）
pytest src/test/ -m "edge" --collect-only

# 运行单个测试文件
pytest src/test/unit/report/test_category.py -v

# 运行单个测试类
pytest src/test/unit/report/test_category.py::TestCategoryAggregationConsistency -v

# 冒烟测试（24 项，~2s 验证核心通路）
pytest src/test/ -m "smoke" -v

# 冒烟 + 边缘测试
pytest src/test/ -m "smoke or edge" -v

# 除 LLM 外的全部测试
pytest src/test/ -m "not llm" -v

# 仅 LLM 场景（S11-S20）
pytest src/test/ -m "scenario_llm" -v

# 基础业务链路 + 日期/时间场景
pytest src/test/ -m "scenario_basic or scenario_datetime" -v

# 输出 HTML 报告
pytest src/test/ -m "edge" -v --html=docs-stm/test-reports/latest/edge/report.html
```

## 测试文件规范

- **命名**：`test_<module>.py`
- **类名**：`Test<Feature>`，继承 `unittest.TestCase`
- **方法**：`test_<场景>`
- **单文件上限**：≤ 800 行 / ≤ 80 测试项 / ≤ 15 方法每类
- **标记**：新增测试类应添加对应 `@pytest.mark.<group>`

## 常见问题

**Q: 运行报错 `no tests collected`？**
A: 确认使用了正确的 marker 名：`pytest src/test/ -m "edge" --collect-only` 可预览匹配的测试。

**Q: 需要跳过 LLM 测试？**
A: 使用 `--mode unit` 或 `python scripts/test_runner.py --mode unit` 即可跳过 LLM 场景。

**Q: 如何添加新的测试标记？**
A: 在 `src/test/conftest.py` 的 `pytest_configure` 中注册新标记，然后在测试类前加 `@pytest.mark.<新标记>`。

**Q: 报告中文乱码？**
A: 确保操作系统编码为 UTF-8。Windows PowerShell：`chcp 65001`；Linux/Mac 默认即可。
