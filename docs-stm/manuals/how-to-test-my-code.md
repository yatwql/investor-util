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

# 快速回归 — 提交前验证（scenario 107 项，~25s）
python scripts/test_runner.py --mode regression

# 合入验证 — PR 前检查（场景+核心模块 668 项，~10min）
python scripts/test_runner.py --mode verify

# 仅运行业务场景测试
python scripts/test_runner.py --mode scenario

# 仅运行边缘/异常场景测试
python scripts/test_runner.py --mode edge

# 运行全量 + 行覆盖率报告
python scripts/test_runner.py --coverage
```

## 测试组合说明

| `--mode` 值 | pytest 标记 | 覆盖范围 | 典型耗时 |
|:------------|:------------|:---------|:---------|
| `unit` | `unit` | 全量单元（含 edge/data 标记，1810 项） | ~25min |
| `standard` | `unit and not (edge or data)` | 常规单元（排除 edge/data） | ~25min |
| `scenario` | `scenario` | §1.3 + §1.6 全量业务场景（S1-S20 + T1-T16，107 项） | ~25s |
| **`regression`** | `scenario` | **提交前极速验证（同 scenario 107 项）** | **~25s** |
| **`verify`** | `scenario or unit_core or unit_providers or unit_fetcher` | **合入验证（场景+核心/数据源/管道 668 项）** | **~10min** |
| `edge` | `edge` | §1.5 异常/边界场景（39 项） | ~10s |
| `data` | `data` | 数据正确性验证（28 项） | ~10s |
| `integration` | `scenario or integration` | 集成/端到端流程测试（含场景标记） | ~10s（待补充） |
| `all` | 无限制 | 全量 1938 项 | ~26min |

> **注意**：`smoke` 标记已在 `conftest.py` 注册但尚未分配测试，后续新增测试时逐步补上标记即可自动生效。`edge` 和 `data` 标记已在对应测试类/方法上使用。`datetime` 标记已废弃，由 `scenario_datetime` 替代。

## 查看报告

每次运行后，测试报告输出到：

```
docs-stm/test-reports/latest/
├── index.html            # 汇总页（打开此文件查看总览）
├── unit/
│   └── report.html       # 单项详细报告
├── scenario/
│   └── report.html
├── integration/
│   └── report.html
├── regression/
│   └── report.html
├── edge/
│   └── report.html
└── all/
    └── report.html
```

**打开方式**：直接用浏览器打开 `docs-stm/test-reports/latest/index.html`

## 直接使用 pytest（跳过脚本）

```bash
# 运行指定标记组合
pytest src/test/ -m "edge" -v --html=docs-stm/test-reports/latest/edge/report.html

# 排除 LLM 相关测试（不需要 API key）
pytest src/test/ -m "not llm" -v

# 运行单个测试文件（按目录分组存放）
pytest src/test/unit/report/test_category.py -v

# 运行单个测试类
pytest src/test/unit/report/test_category.py::TestCategoryAggregationConsistency -v
```

## 标记分组（pytest markers）

| 标记 | 归属 | 说明 |
|:-----|:-----|:-----|
| **场景测试（父标记）** | | |
| `scenario` | — | 全量业务场景（S1-S20 + T1-T16，107 项） |
| ├─ `scenario_basic` | 子标记 | 基础业务链路（S1-S5，9 项） |
| ├─ `scenario_extended` | 子标记 | 扩展业务场景（S6-S10，18 项） |
| ├─ `scenario_llm` | 子标记 | LLM 场景组合（S11-S20，19 项） |
| └─ `scenario_datetime` | 子标记 | 日期/时间场景（T1-T16，61 项） |
| **单元测试（父标记）** | | |
| `unit` | — | 全量单元测试（8 子组，1810 项） |
| ├─ `unit_providers` | 子标记 | 数据源 Provider（166 项） |
| ├─ `unit_fetcher` | 子标记 | 抓取器（118 项） |
| ├─ `unit_llm` | 子标记 | LLM 模块（331 项） |
| ├─ `unit_news` | 子标记 | 新闻源（176 项） |
| ├─ `unit_report` | 子标记 | 报表生成（558 项） |
| ├─ `unit_config` | 子标记 | 配置管理（42 项） |
| ├─ `unit_core` | 子标记 | 核心模块（277 项） |
| └─ `unit_ui` | 子标记 | TUI 交互（142 项） |
| **横切标记** | | |
| `llm` | 横切 | 全部 LLM 相关（unit_llm 331 + scenario_llm 19 = 350 项，需 API key） |
| **其他** | | |
| `edge` | 独立 | 边缘/异常场景测试 |
| `data` | 独立 | 数据正确性验证测试 |
| `smoke` | 独立 | 冒烟测试（快速验证核心功能，待分配） |

### 组合查询示例

```bash
# 冒烟 + 边缘测试
pytest src/test/ -m "smoke or edge" -v

# 除 LLM 外的全部测试
pytest src/test/ -m "not llm" -v

# 全量业务场景（S1-S20 + T1-T16）
pytest src/test/ -m "scenario" -v

# 仅 LLM 场景（S11-S20）
pytest src/test/ -m "scenario_llm" -v

# 基础业务链路 + 日期/时间场景
pytest src/test/ -m "scenario_basic or scenario_datetime" -v

## 回归测试级别

| 级别 | 定义 | 阻断点 |
|:-----|:-----|:-------|
| P0 | 阻塞提交 — 核心功能不可用 | 不得 commit |
| P1 | 阻塞合入 master | 不得 merge |
| P2 | 阻塞发布 | 不得 release |
| P3 | 建议修复 | 不阻断 |

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
