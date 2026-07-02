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

# 仅运行单元测试
python scripts/test_runner.py --mode unit

# 仅运行业务场景测试
python scripts/test_runner.py --mode scenario

# 仅运行集成测试
python scripts/test_runner.py --mode integration

# 仅运行回归测试（P0-P2）
python scripts/test_runner.py --mode regression

# 仅运行边缘/异常场景测试
python scripts/test_runner.py --mode edge

# 运行全量 + 行覆盖率报告
python scripts/test_runner.py --coverage
```

## 测试组合说明

| `--mode` 值 | pytest 标记 | 覆盖范围 | 典型耗时 |
|:------------|:------------|:---------|:---------|
| `unit` | 无标记（默认含 `not scenario`） | 纯单元测试，不含场景集成 | ~5s |
| `scenario` | `scenario` | §1.3 业务场景 S1-S20 | ~60s |
| `integration` | `scenario` 或 `integration` | 集成/端到端流程 | ~60s |
| `regression` | 无限制（含全部 P0-P2 级别） | 提交前必须通过的验证集 | ~30s |
| `edge` | `edge` | §1.5 异常/边界场景 | ~15s |
| `all` | 无限制 | 全量 1900+ 测试 | ~5min |

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

# 运行单个测试文件
pytest src/test/test_category.py -v

# 运行单个测试类
pytest src/test/test_category.py::TestCategoryAggregationConsistency -v
```

## 标记分组（pytest markers）

| 标记 | 说明 |
|:-----|:-----|
| `scenario` | 业务场景集成测试（S1-S20） |
| `llm` | LLM 相关测试（需 API key 配置） |
| `datetime` | 日期/时间/交易时段测试（T1-T16） |
| `edge` | 边缘/异常场景测试 |
| `smoke` | 冒烟测试（快速验证核心功能） |
| `data` | 数据正确性验证测试 |

### 组合查询示例

```bash
# 冒烟 + 边缘测试
pytest src/test/ -m "smoke or edge" -v

# 除 LLM 外的全部测试
pytest src/test/ -m "not llm" -v

# 日期相关 + 边缘场景
pytest src/test/ -m "datetime or edge" -v
```

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
