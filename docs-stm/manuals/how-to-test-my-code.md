# 如何驱动测试 — 测试组合运行指南
> 文档版本：0.10.8-dev

## 概述

本项目的测试框架基于 **pytest**，通过标记（marker）分组支持灵活组合运行。使用 `scripts/test_runner.py` 脚本统一驱动，自动输出结构化报告。

> **关联参考**：各 `--mode` 的精确测试项数统计见 **[test-coverage.md](../managements/test-coverage.md)**。

## 前置条件

```bash
# 安装测试依赖
pip install pytest pytest-html pytest-mock pytest-xdist
# 可选：覆盖率报告
pip install pytest-cov coverage
```

> 以上仅安装测试插件。项目主依赖（httpx、openpyxl、akshare 等）见 `requirements.txt`：`pip install -r requirements.txt`。

## 快速开始

```bash
# 查看所有可用选项
.venv/bin/python scripts/test_runner.py --help

# ===== ① 日常常用（快速反馈，提交前验证） =====

# 提交前快速验证（~20s，P0 门禁）
.venv/bin/python scripts/test_runner.py --mode dev-verify

# 冒烟测试（~2s 快速验证核心通路）
.venv/bin/python scripts/test_runner.py --mode smoke

# 仅运行业务场景测试
.venv/bin/python scripts/test_runner.py --mode scenario

# 集成测试（含场景 + 模块间契约/缓存/TUI 路由）
.venv/bin/python scripts/test_runner.py --mode integration

# 全量单元测试（含 edge/data）
.venv/bin/python scripts/test_runner.py --mode unit

# 常规单元测试（排除 edge/data）
.venv/bin/python scripts/test_runner.py --mode standard

# ===== ② 专项验证（定向覆盖） =====

# 仅运行边缘/异常场景测试
.venv/bin/python scripts/test_runner.py --mode edge

# 极限场景（超多持仓/极端值/高精度）
.venv/bin/python scripts/test_runner.py --mode scenario_extreme

# 数据正确性验证（~2s）
.venv/bin/python scripts/test_runner.py --mode data

# 真实网络验证（opt-in，不入门禁，仅排查数据源连通性时手工运行）
.venv/bin/python scripts/test_runner.py --mode live

# 运行全量 + 行覆盖率报告
.venv/bin/python scripts/test_runner.py --coverage

# ===== ③ 全量/CI 门禁（耗时较长） =====

# 开发期快速验证（5 个 unit 子模块并行 + 基础场景，~20s）
.venv/bin/python scripts/test_runner.py --mode dev-verify

# 合入验证 — PR 前检查（~10s）
.venv/bin/python scripts/test_runner.py --mode verify

# 全量测试（~30s，--mode verify,regression 覆盖单元+场景）
.venv/bin/python scripts/test_runner.py --mode verify,regression

# 全量测试（排除单元测试，~10s 快速全场景覆盖）
.venv/bin/python scripts/test_runner.py --mode all_no_unit
```

## 🔁 只重跑上次失败的测试（`--lf`）

修复代码后验证时，经常只需要重跑**上一次运行失败的那些用例**，而不必等全量通过。pytest 内置的 `--lf`（`--last-failed`）标志专为此场景设计：

```bash
# 只重跑上次 pytest 运行中失败的测试（跳过已通过的）
.venv/bin/python -m pytest src/test/ --lf

# 先收集匹配 marker 的用例，再从其中只重跑上次失败的
.venv/bin/python -m pytest src/test/ -m "unit_providers" --lf
```

**与 `test_runner.py` 的配合**：

`test_runner.py` 使用 `argparse` 管理参数，**不支持** `--` 透传（例如 `.venv/bin/python scripts/test_runner.py --mode all -- --lf` 会报错）。如需 `--lf`，绕过它直接调 pytest，用 `-m` 参数复现目标模式的标记表达式：

```bash
# 先找到目标模式对应的 marker 表达式
# 在 scripts/test_runner.py 的 MODES 字典中查找，例如：
#   regression → "scenario"
#   unit       → "unit"
#   verify     → "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts"

# 然后用 pytest -m + --lf 组合运行
.venv/bin/python -m pytest src/test/ -m "scenario" --lf                  # 等价 --mode regression 的失败重跑
.venv/bin/python -m pytest src/test/ -m "unit_providers" --lf            # 等价 --mode unit 下 unit_providers 的失败重跑
.venv/bin/python -m pytest src/test/ -m "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts" --lf  # 等价 --mode verify
```

> 各 `--mode` 对应的 `-m` 表达式见下文「模式与覆盖范围说明」章节，或直接查看 `scripts/test_runner.py` 中 `MODES` 字典的 `marker` 字段。

**工作原理**：pytest 在每次运行后，将失败用例记录到 `.pytest_cache/lastfailed` 文件；`--lf` 读取该文件，只收集文件中的用例执行。如果上次运行全部通过，`--lf` 会提示 `no tests ran`（因为没有失败记录）。

**典型工作流**：

```
# 1. 跑全量 → 发现 N 个失败
.venv/bin/python -m pytest src/test/ -m "edge"

# 2. 修复代码

# 3. 仅重跑失败的 N 个（5 秒而非 5 分钟）
.venv/bin/python -m pytest src/test/ -m "edge" --lf

# 4. 全部通过后，再用无 --lf 的全量确认没有回归
.venv/bin/python -m pytest src/test/ -m "edge"
```

> ⚠ **注意**：
> - `--lf` 依赖上次运行生成的 `.pytest_cache/lastfailed` 文件。如果清理了 `.pytest_cache/` 或切换了虚拟环境，`--lf` 不会生效。此时只需先正常跑一次目标模式生成失败记录即可。
> - 另一相关标志 `--ff`（`--failed-first`）会**先跑上次失败、再跑全部**，适合修复后确认修复 + 检查回归一步到位。
> - `test_runner.py` 不支持 `--lf`，是因为它用 `subprocess.run` 调 pytest 且 argparse 不接收未注册的 `--` 参数。建议日常快速验证时直接使用 `pytest`，门禁检查时再用 `test_runner.py`。

## 测试模式详解

测试框架围绕两个概念组织：**pytest 标记（marker）** 是测试用例的固有属性（标注"这是什么测试"）；**`--mode`** 是 `scripts/test_runner.py` 脚本对标记的预定义组合（定义"应该运行哪些测试"）。每个 mode 对应一个或多个标记表达式，脚本解析后传给 `.venv/bin/python -m pytest -m` 执行。

### 回归测试级别

每个回归项按影响范围分四级，与三级流水线的对应关系：

| 级别 | 定义 | 阻断点 | 对应的流水线阶段 |
|:-----|:-----|:-------|:----------------|
| **P0** | 阻塞提交 — 核心功能不可用 | 不得 commit | ① `dev-verify`（~20s） |
| **P1** | 阻塞合入 master | 不得 merge | ② `verify`（~10s） |
| **P2** | 阻塞发布 | 不得 release | ③ `verify,regression`（~30s） |
| **P3** | 建议修复 | 不阻断 | — |

P0 问题必须在 commit 前解决，否则代码不应进入版本控制。P1 问题允许提交但不允许合入主分支。P2 允许合入主分支但不应发布版本。P3 属于已知缺陷或待优化项，可带缺陷发布。

> 注意：P0-P3 是**问题影响力分级**，regression/verify/all 是**测试范围分级**，两者通过门禁阶段关联但不一一对应。例如 P0 问题恰好在 regression 模式中被检出，但 regression 模式并非仅包含"P0 级别"的测试用例——它覆盖全量业务场景，其中任何一项失败都可能导致 P0 阻断。

> **耗时说明**：本文档 `~Ns` 耗时按 2026-08-05 实测（Linux x86_64，Intel i5-13500H，12 核 16 线程，46GiB 内存；pytest-xdist worker=8 = medium 50% 核数）。**耗时与硬件/操作系统/并行度强相关**——早期标注（如 ~2.5min/~7min）源自另一台慢笔记本环境，不同 OS 或慢机器上可能数倍于此，仅作相对量级参考；完整说明及不同环境下的耗时对照见 `test-coverage.md`（顶部注 + 「环境耗时对照」表）。

### 三级验证流水线

项目推荐的四道质量门禁，按开发阶段逐级收紧：

- **提交前门禁（`--mode dev-verify` / P0）** — commit 前必须执行。组合 5 个 unit 子模块（unit_core/unit_providers/unit_fetcher/unit_analysis/unit_scripts，并行）+ 基础业务场景（`scenario_basic`），排除 edge/data 和极限场景。约 20s。是编辑-验证循环中的正式屏障。
- **全场景回归（`--mode regression`）** — commit 前可选的全场景补充验证。覆盖全部 `scenario` 业务场景测试（S0a/S0b/S0d + S1-S33 + T1-T21），确保端到端用户路径不被破坏。约 17s。推荐在改动了跨模块路径或数据流后补充运行。
- **合入验证（`--mode verify` / P1）** — 准备合并到 master 前必须执行。覆盖 `unit_core`（核心基础设施：缓存引擎、数据模型、注册表）、`unit_providers`（数据源 Provider：腾讯、东方财富、天天基金等）、`unit_fetcher`（数据获取调度：价格、指数、行业分类）、`unit_config`（配置管理）、`unit_news`（新闻聚合）、`unit_llm`（LLM 模块）、`unit_analysis`（分析计算：流动性/再平衡/汇率/债券收益率等）、`unit_scripts`（工程脚本：历史痕迹/版本一致性/任务编号检查）八个单元模块。确保数据从抓取→缓存→计算的整条管道通畅且正确。并行执行，约 10s。场景测试已在 P0 dev-verify（基础场景）和 P2 verify,regression（全场景）中覆盖，P1 不重复。
- **发布验证（`--mode verify,regression`）** — 发布版本（打 tag/release）前必须执行。组合单元测试 + 场景测试，覆盖全部核心通路。约 30s。
  > 注：若走常规 `dev → merge → tag master` 流程，P1 已保证 `verify` 通过，P2 的 `verify` 属冗余验证。保留冗余是为了覆盖**直接从 dev 打 tag 发布**（未过 P1 合入门禁）的场景。如确定流程中有严格 merge 屏障且不直接发布 dev，P2 可优化为仅 `--mode regression`（~17s）。详见 [`testplan.md`](../managements/testplan.md) → §6.3 脚注。


> `regression` 与 `scenario` 底层使用相同的标记表达式（`-m "scenario"`），前者是语义别名——强调"提交前快速回归"的用途定位；后者是分类名——强调"业务场景测试"的数据性质。两者可互相替代，但建议按使用场合选用对应名称以增强代码意图可读性。

**推荐工作流：**

```
编码 → --mode dev-verify(~20s) → commit → 多次积累 → merge → P1 --mode verify(~10s) → release前 → P2 --mode verify,regression(~30s)
          ↑                                    ↗
    改完代码随时跑                      若改跨模块调用
      提交前必过P0门禁                  先跑 --mode integration(~14s)
```

在一次典型开发周期中：
1. **提交前门禁验证**：修改代码后运行 `--mode dev-verify`（~20s）确认核心单元+基础场景通过（P0 强制）
2. **全场景补充验证**：若改动了跨模块路径/数据流，再跑 `--mode regression`（~17s）确保全场景正常
3. 如果改了跨模块调用关系（缓存、新闻流水线、TUI 路由等），再跑 `--mode integration`（~14s）确认接口契约和全链路正常
4. 如果改了 Provider、缓存或数据获取逻辑，再跑 `--mode verify`（~10s）确认整条管道通畅
5. 通过后 commit，积累多次提交后准备合并到 master
6. 合并前 CI 自动跑 `--mode verify` 作为合入门禁（~10s）
7. 发布版本前 CI 自动跑 `--mode verify,regression`（~30s）全量验证

### 模式与覆盖范围说明

每种 `--mode` 对应一组 pytest 标记表达式，由 `scripts/test_runner.py` 转换为 `.venv/bin/python -m pytest -m "<表达式>"` 执行。各模式的覆盖范围存在包含与被包含关系，理解这种关系有助于缩小验证范围以快速反馈：

#### 🔷 单元测试系列（`unit` / `standard`）

- **`--mode unit`** 覆盖所有标记为 `unit_*` 的测试（12 个子组：providers、fetcher、llm、news、report、config、config_edge、core、analysis、ui、cli、scripts），不含场景测试。这是对代码库中各独立模块的功能正确性验证，所有网络请求均为 mock，不依赖外部 API。
- **`--mode standard`** 在 `unit` 基础上排除 edge（异常边界）和 data（数据正确性）两个跨类标记，仅保留"常规路径"的单元测试。适用于日常开发中快速验证模块本身逻辑正确，不需要关心边界情况。

#### 🔷 场景测试系列（`scenario` / `regression` / `integration` / `verify`）

- **`--mode scenario`** 覆盖所有标记为 `scenario_*` 的测试（6 个子组：basic、resilience、llm、datetime、perf、security）。这些测试模拟真实用户操作（如菜单 E/B/L 生成报告），组合多个模块进行端到端验证。

  场景测试按职责分为 **7 大类**：

  - **`scenario_basic` — 基础业务链路**：验证正常业务流程，包括纯股票/纯基金/混合多账户的市值穿透计算、缓存首次/命中逻辑、特殊品种（港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债）的正确分类和计算，以及持仓质量边界（清仓不计入、同名多份额合并、特殊字符不乱码（超多持仓 S0c 在 scenario_extreme）），以及操作行为场景（S29-S33：分红送转除权/定投成本摊薄/部分调仓卖出/跨账户转仓/新股中签待上市）。
  - **`scenario_resilience` — 异常容错场景**：验证系统在非正常输入或环境下的降级能力，包括纯债券基金组合（穿透无股权覆盖）、网络中断（价格从过期缓存读取）、单账户单持仓、零成本持仓（不除零崩溃）。
  - **`scenario_extreme` — 极限场景**：验证极端数据下的正确性，包括超多持仓（S0c，200+ 条批量计算）和极端值（S10，超大/极小份额、高精度净值、零值组合）。标记 `scenario_extreme`，不包含在 `scenario` / `scenario_basic` / `scenario_resilience` 中，需单独运行 `--mode scenario_extreme`。
  - **`scenario_llm` — LLM 场景组合**：验证 LLM 模块在各种状态下的行为，包括缓存/成功/失败混合状态的颜色渲染、五种失败原因独立映射、Extended Thinking 标记、禁用优先原则、断网降级、全缓存无调用、三种输出格式（Excel/HTML/Summary）一致性。
  - **`scenario_datetime` — 日期/时间场景**：验证系统在不同市场时段（盘中/盘前/午休/盘后/非交易日/长假）、产品类型（场外基金/QDII/ETF/股票/混合）、边界条件（时段切换/缝隙/首次启动/断网）以及特殊日历（跨年/季末/汇率故障/调休/港股通假期）下的数据获取正确性和降级表现。

- **`--mode regression`** 与 `--mode scenario` 完全相同，但语义定位为"提交前回归验证"。建议在 git hook 或 CI 前置检查中使用此名称，使流水线意图更加清晰。
- **`--mode integration`** 覆盖场景测试 + 集成测试（`scenario or integration`）。在全部业务场景基础上，增加模块间验证：接口契约、错误隔离、新闻流水线、缓存一致性、TUI 路由。用于修改了跨模块调用关系后的定向回归。
- **`--mode dev-verify`** 提交前门禁模式（P0），组合 5 个 unit 子模块（unit_core/unit_providers/unit_fetcher/unit_analysis/unit_scripts，排除 edge/data）并行 + 基础业务场景（`scenario_basic`）。约 20s，适合开发者改完代码后随时跑。不包含极限场景（scenario_extreme）和 LLM/日期/容错等专项场景。
- **`--mode verify`** 合入门禁模式（`unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts`），包含核心基础设施 + 数据源 Provider + 数据获取调度 + 配置管理 + 新闻聚合 + LLM 模块 + 分析计算 + 工程脚本的单元测试，共约 10s（并行执行）。场景测试由 P0 dev-verify（基础场景）和 P2 verify,regression（全场景）覆盖。

#### 🔷 专项验证系列（`edge` / `data` / `smoke`）

- **`--mode edge`** 仅运行标记为 `edge` 的测试，覆盖各种异常和边界情况：零值、空数据集、并发竞态、Unicode、时区安全、文件系统边界、API 网络异常等。适用于修改了函数内部错误处理逻辑后的针对性验证。
- **`--mode data`** 仅运行标记为 `data` 的测试，覆盖数据精确性：市值=价格×份额、盈亏=市值-成本、收益率=盈亏÷成本（成本>0）、穿透 TOP10 占比归一化等。适用于修改了数值计算逻辑后的回归。
- **`--mode smoke`** 仅运行标记为 `smoke` 的测试，从 6 个全流程关键节点各选 4 项最快基础测试：核心数据模型→入口读取→分类计算→报告输出→启动依赖→数据获取。全部为纯内存计算、无 IO、每项 <0.1s，合计 ~2s。适用于部署后冒烟或极速"通不通"检查。

#### 🔷 真实网络验证（`live`，opt-in，不入门禁）

- **`--mode live`** 运行真实外部网络验证套件（`src/test/live/`），用于排查「数据源是否真的可达 / API 是否漂移」时手工验证。**平时（含 dev-verify/verify/all 全量门禁）完全不运行**——由三层机制保证：
  1. `pytest.ini` 的 `addopts = -m "not live"` 在收集期直接排除；
  2. `conftest.py` 的 `_skip_live_unless_requested` autouse fixture 默认跳过（`-m live` 收集到也 skip）；
  3. `_block_external_network` 阻断 fixture 对非 live 项一律拦死真实网络。
- **内容**：覆盖行情（A 股/ETF/场外基金/中美指数）、新闻源（东方财富/财联社/新浪/华尔街见闻）、基金（历史净值/排名/基准）、akshare 交易日历共 14 项。
- **断言原则**：只校验返回「结构」（字段存在、类型、非空），**不校验具体数值**，容忍真实行情波动（休市、涨跌、数据源改字段）。
- **不含 LLM 真实调用**（防费用）——LLM 连通性由运行时数据源健康检查覆盖。
- 触发方式：`.venv/bin/python scripts/test_runner.py --mode live` 或 `.venv/bin/python -m pytest --run-live -m live`。

#### 🔷 全量（`all`）

- **`--mode verify,regression`** 组合模式，等价于分别运行 verify（单元） + regression（场景）。约 30s，作为发布门禁。
- **`--mode all`** 不设任何标记过滤（`.venv/bin/python -m pytest src/test/`），运行全量测试。需要全覆盖时手动调用。
- **`--mode all_no_unit`** 排除所有单元测试（`-m "not unit"`），仅保留场景测试、集成测试和跨类测试。适用于想要全场景覆盖但跳过纯模块逻辑验证的场景。

#### 🔷 多模式组合

`--mode` 支持逗号分隔同时运行多个模式：

```bash
# 同时运行场景测试和边缘测试
.venv/bin/python scripts/test_runner.py --mode scenario,edge
```

脚本按 MODES 字典定义的 order 顺序依次执行各模式，结果汇总到同一份 HTML 报告中。适用于 CI 流水线中按阶段逐步收紧的场景。精确实时计数请运行 `.venv/bin/python -m pytest src/test/ --collect-only -q`。

#### 🔷 跨机器耗时采集与环境耗时对照（`bench` + `--machine-info` / `--update-docs`）

耗时与**硬件配置、操作系统与并行度**强相关。跨机器复现耗时并回填对照表：

```bash
# 仅采集：顺序运行 14 个对照表模式（不含 live），打印环境属性表 + 各模式实测耗时表
.venv/bin/python scripts/test_runner.py --mode bench --machine-info

# 采集并自动更新 test-coverage.md「环境耗时对照」两张表
.venv/bin/python scripts/test_runner.py --mode bench --update-docs   # 隐含 --machine-info
```

- **`--mode bench`** 是 14 个对照表模式的聚合别名（`_MODE_TABLE_ORDER` 除 `live` 外全部），按对照表顺序运行；结果去重保序，非 bench 模式原样透传。
- **`--machine-info`** 采集 14 项环境属性（操作系统/系统版本/架构/主机名/CPU 型号/物理核数/逻辑线程/内存/磁盘类型/文件系统/Python 版本/并行级别/worker 数/采集日期，跨平台容错）并输出两张 Markdown 表格。
- **`--update-docs`** 在跑完后**自动写入** `test-coverage.md` 的两张表（按主机名匹配列：同机覆盖刷新日期、新机器追加列；历史参考列不受影响）。默认**永不写文档**，仅在显式传入该标志时更新；内容未变化则跳过写入（幂等）。
- 中断保护：bench 中途 `Ctrl+C` 先打印已采集部分并回填已完成模式，慢机器不丢数据。
- 典型耗时与对照说明见 `test-coverage.md` 顶部注 + 「环境耗时对照」表。

## 查看报告

每次运行后，测试报告输出到（每个子目录对应一个 `--mode` 名称）：

```
test-reports/latest/
├── index.html            # 汇总页（打开此文件查看总览）
├── unit/
│   └── report.html       # 单元测试
├── standard/
│   └── report.html       # 常规单元测试
├── scenario/
│   └── report.html       # 业务场景测试
├── scenario_extreme/
│   └── report.html       # 极限场景测试
├── integration/
│   └── report.html       # 集成测试（场景 + 模块间契约）
├── regression/
│   └── report.html       # 回归测试 / 场景别名
├── dev-verify/
│   └── report.html       # 开发期快速验证
├── verify/
│   └── report.html       # 合入验证
├── edge/
│   └── report.html       # 边缘场景测试
├── data/
│   └── report.html       # 数据正确性验证
├── live/
│   └── report.html       # 真实网络验证（opt-in，--mode live 才生成）
├── all/
│   └── report.html       # 全量测试
├── all_no_unit/
│   └── report.html       # 全量测试（排除单元测试）
├── smoke/
│   └── report.html       # 冒烟测试
```

**打开方式**：直接用浏览器打开 `test-reports/latest/index.html`

### 🔧 快速定位失败用例 — `scripts/extract-test-failures.py`

运行 `test_runner.py --mode verify,regression` 等全量测试后，直接从 HTML 报告中提取失败/错误用例的详细信息，无需手动翻浏览器：

```bash
# 自动查找 test-reports/latest/ 下的报告
.venv/bin/python scripts/extract-test-failures.py

# 指定报告路径
.venv/bin/python scripts/extract-test-failures.py test-reports/latest/all/report.html

# 仅输出汇总统计（不打印日志）
.venv/bin/python scripts/extract-test-failures.py --summary

# 输出 JSON 格式（便于管道处理）
.venv/bin/python scripts/extract-test-failures.py --json
```

**典型工作流**：

```
# 1. 跑全量测试
.venv/bin/python scripts/test_runner.py --mode verify,regression

# 2. 快速查看哪些用例失败
.venv/bin/python scripts/extract-test-failures.py --summary

# 3. 查看失败详情（含错误堆栈最后 500 字符）
.venv/bin/python scripts/extract-test-failures.py

# 4. 修复后，只重跑之前失败的用例
.venv/bin/python -m pytest src/test/ -m "<对应标记>" --lf
```

> 脚本自动定位 `test-reports/latest/all/report.html` 等常用路径，无需每次指定路径。

## 辅助脚本

> 所有辅助脚本的完整参考（含测试驱动/失败提取/标记检查/幻觉率采样/去重校准/版本一致性检查/性能基准/Gemini 诊断）详见 [`scripts-reference.md`](./scripts-reference.md)。

### LLM 幻觉率采样测试

**数据集简介**（共 10 组）：

| # | 名称 | 品种数 | 测试重点 |
|---|------|:------:|----------|
| 1 | 基本 A 股组合 | 3 | 标准正收益场景 |
| 2 | 混合基金组合 | 5 | 股+基混合，部分亏损 |
| 3 | 含较大亏损组合 | 4 | 亏损品种描述准确性 |
| 4 | 权重集中组合 | 3 | 集中度风险描述 |
| 5 | 分散组合 | 8 | 多品种小额分散 |
| 6 | 多账户组合 | 6 | 三账户场内外混合 |
| 7 | 偏防守组合 | 4 | 高股息防守型 |
| 8 | 全基金组合 | 3 | 穿透逻辑幻觉 |
| 9 | 零成本特殊场景 | 3 | 继承/赠予零成本 |
| 10 | 极简组合 | 2 | 最小规模边界 |

**幻觉率标准**：目标 **< 5%**。每次 prompt 重大修改后应重新采样。

**注意**：事实校验器对仓位占比百分比和情景假设百分比设跳过策略（`_POSITION_WEIGHT_KEYWORDS` / `_HYPOTHETICAL_KEYWORDS`），避免将百分比陈述误报为幻觉。最终幻觉率以 `docs-stm/tmp/hallucination-report.md` 为准。

## 标记选择运行速查

以 `.venv/bin/python -m pytest -m "<表达式>"` 形式快速选取特定标记组合，适合开发调试中定向验证。

### 场景标记

| 表达式 | 覆盖范围 |
|:-------|:---------|
| `scenario` | 全部业务场景 S0a/S0b/S0d + S1-S33 + T1-T21（S0c 属 `scenario_extreme`，不计入） |
| `scenario_basic` | 基础链路 S0a/S0b/S0d + S1-S5 + S21-S33 |
| ├ `scenario_stock` | S1: 纯股票组合 |
| ├ `scenario_fund` | S2: 纯基金组合 |
| ├ `scenario_mixed_accounts` | S3: 混合多账户 |
| ├ `scenario_new_holdings` | S4: 新持仓无缓存 |
| └ `scenario_cache_hit` | S5: 缓存全命中 |
| `scenario_resilience` | 异常容错场景 S6-S9 |
| ├ `scenario_bond` | S6: 纯债券基金组合 |
| ├ `scenario_network_down` | S7: 网络中断降级 |
| ├ `scenario_single_holding` | S8: 单账户单持仓 |
| └ `scenario_zero_cost` | S9: 零成本持仓 |
| `scenario_extreme` | 极限场景 S0c+S10：超多持仓/极端份额/高精度净值/零值组合 |
| `scenario_llm` | LLM 场景 S11-S20 |
| `scenario_datetime` | 日期/时间场景 T1-T21 |
| `scenario_basic or scenario_datetime` | 基础链路 + 日期场景 |
| `scenario_cache_hit or scenario_zero_cost` | 缓存 + 零成本组合 |

### 单元子模块标记

以 `.venv/bin/python -m pytest -m "<表达式>"` 快速选取单元子模块。

| 表达式 | 覆盖范围 |
|:-------|:---------|
| `unit` | 所有单元测试 |
| `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等） |
| `unit_fetcher` | 数据获取调度 |
| `unit_llm` | LLM 模块 |
| `unit_news` | 新闻处理 |
| `unit_report` | 报表生成 |
| `unit_config` | 配置管理 |
| `unit_core` | 核心基础设施（缓存/模型/注册表等） |
| `unit_analysis` | 分析计算（流动性/再平衡/汇率/债券收益率/情景） |
| `unit_config_edge` | 配置管理边缘场景（必须放在 `*_edge.py`） |
| `unit_ui` | TUI 交互 |
| `unit_cli` | CLI 命令行模式 |
| `unit_scripts` | 工程脚本（历史痕迹/版本一致性/任务编号检查） |
| `unit_providers or unit_fetcher` | 数据管道（Provider + 调度） |

### 横切标记

以 `.venv/bin/python -m pytest -m "<表达式>"` 快速选取横切标记。

| 表达式 | 覆盖范围 |
|:-------|:---------|
| `smoke` | 冒烟 |
| `edge` | 边缘/异常场景 |
| `data` | 数据正确性验证 |
| `llm` | 全部 LLM（单元 + 场景） |
| `not llm` | 排除 LLM 后的全量 |

### 集成测试标记

| 表达式 | 覆盖范围 |
|:-------|:---------|
| `integration`（父标记） | 全部集成测试 |
| ├─ `integration_contract` | 模块间接口契约验证 |
| ├─ `integration_isolation` | 错误隔离业务语义验证 |
| ├─ `integration_news_pipeline` | 新闻流水线全链路 |
| ├─ `integration_cache` | 跨模块缓存一致性验证 |
| ├─ `integration_tui` | TUI → Handler 路由集成测试 |
| └─ `integration_cli` | CLI 命令行模式集成测试 |

场景标记表末尾列出了常用的标记组合表达式（如 `scenario_basic or scenario_datetime`、`scenario_cache_hit or scenario_zero_cost`），可在此基础上按需调整。

### 组合查询示例

除上表按标记选择外，也可直接使用 `pytest` 进行灵活组合查询：

```bash
# 查看指定标记下有哪些测试（不执行）
.venv/bin/python -m pytest src/test/ -m "edge" --collect-only

# 运行单个测试文件
.venv/bin/python -m pytest src/test/unit/report/test_category.py -v

# 运行单个测试类
.venv/bin/python -m pytest src/test/unit/report/test_category.py::TestCategoryAggregationConsistency -v

# 冒烟测试（~2s 验证核心通路）
.venv/bin/python -m pytest src/test/ -m "smoke" -v

# 冒烟 + 边缘测试
.venv/bin/python -m pytest src/test/ -m "smoke or edge" -v

# 除 LLM 外的全部测试
.venv/bin/python -m pytest src/test/ -m "not llm" -v

# 仅 LLM 场景（S11-S20）
.venv/bin/python -m pytest src/test/ -m "scenario_llm" -v

# 基础业务链路 + 日期/时间场景
.venv/bin/python -m pytest src/test/ -m "scenario_basic or scenario_datetime" -v

# 输出 HTML 报告
.venv/bin/python -m pytest src/test/ -m "edge" -v --html=test-reports/latest/edge/report.html
```

## 测试文件规范

- **命名**：`test_<module>.py`
- **类名**：`Test<Feature>`，继承 `unittest.TestCase`
- **方法**：`test_<场景>`
- **单文件上限**：≤ 800 行 / ≤ 80 测试项 / ≤ 15 方法每类
- **标记规则**：单元测试用 `pytestmark` 模块级列表（`[pytest.mark.unit, pytest.mark.<子组>]`），场景测试用类级 `@pytest.mark.scenario + @pytest.mark.<子组>`，edge 测试在 `pytestmark` 中追加 `pytest.mark.edge`
- 新增文件后运行 `.venv/bin/python scripts/check-test-markers.py` 验证标记合规性

## 新增测试指南

新增测试用例时，按以下流程操作：

### 确定测试类型和文件位置

| 测试类型 | 放哪里 | 示例 |
|:---------|:-------|:-----|
| **模块单元测试** | 已有对应 `test_<module>.py` 追加 | `test_cache_core.py` 追加 `TestCacheEdgeCases` |
| **新模块测试** | 新建 `test_<新模块>.py` | `test_news_correlator.py` |
| **业务场景测试** | `test_scenario_basic_flows.py`（基础链路 S1-S5）或 `test_scenario_resilience_flows.py`（异常容错 S6-S9）或 `test_scenario_extreme.py`（极限 S0c+S10） | S1 → `test_scenario_basic_flows.py` |
| **持仓质量场景** | `test_scenario_holdings_quality.py` | S0a/S0b/S0d |
| **特殊品种场景** | `test_scenario_special_securities.py` | S21-S28 |
| **操作行为场景** | `test_scenario_operational_behavior.py` | S29-S33 |
| **报告序号场景** | `scenario/basic/test_scenario_section_order.py` | 序号合规性 |
| **LLM 场景测试** | `scenario/llm/` 下 9 个文件：`test_llm_mixed_cache.py` / `test_llm_module_info.py` / `test_llm_extended_thinking.py` / `test_llm_disabled.py` / `test_llm_disabled_cache.py` / `test_llm_network_error.py` / `test_llm_partial_cache.py` / `test_llm_empty_holdings.py` / `test_llm_hallucination.py` | S11-S20 |
| **日期/时间场景** | `test_datetime_scenarios.py` | T1-T21 |
| **辩论模式场景** | `integration/test_debate_pipeline.py` | 端到端管线 |
| **辩论模式单元测试** | `unit/llm/test_debate_*.py` | generators/prompts/edge/token_budget/conditional/qa |
| **缺陷回归测试** | 对应模块的 `test_*.py` 或 `test_regression.py` | Bug fix 的断言 |
| **边缘/异常场景测试** | 对应模块的 `test_<module>_edge.py` | 使用 `@pytest.mark.edge` 标记，放置于模块目录下 |

### 命名规范

```python # 测试类名 — 模块/场景名 + 测试维度
class TestCacheEdgeCases:          # 模块 + 测试类型
class TestGetTtlMarketAware:       # 函数名 + 场景
class TestScenarioS21:             # 新业务场景递增

# 测试方法名 — test_ + 场景 + 预期结果
def test_empty_holdings_returns_zero(self):
def test_ttl_during_trading_hours_returns_30s(self):
def test_qdii_nav_date_delayed_t2(self):
```

### 新增后必须更新的文件

1. **`test-coverage.md` 场景测试分组表** — 新增 S/T/D 场景时补充条目（含测试类参考列）
2. **`folders.md`** — 新增 test_*.py 文件后更新目录树
3. **`changelog.md`** — 记录新增的测试数量和覆盖场景
4. **`plan.md`** — 如果在迭代中新增的功能，更新对应条目的完成状态
5. **`unit/conftest.py`** — 新增 `unit/` 下测试文件时确认 `pytestmark` 列表包含正确的 `unit_*` 子标记

### 新增后必须执行的验证

```bash
.venv/bin/python -m pytest src/test/                                   # 全量通过
.venv/bin/python -m pytest --co                                         # 无 patch 残留污染
.venv/bin/python -m pytest src/test/unit/core/test_registry.py --co -v      # 新文件隔离（示例）
.venv/bin/python scripts/check-test-markers.py                # 标记合规性检查（AST 静态扫描）
```

### 文件膨胀阈值

| 指标 | 警告线 | 红线 | 措施 |
|:-----|:------:|:----:|:-----|
| 单文件测试数 | > 80 项 | > 120 项 | 拆分到子文件 `test_xxx_part1.py` / `test_xxx_part2.py` |
| 单文件行数 | > 800 行 | > 1200 行 | 考虑按被测函数 / 场景类型拆分 |
| 单类方法数 | > 15 项 | > 25 项 | 拆为多个 Test 类或拆分文件 |
| 单方法 mock 数 | > 5 个 patch | > 8 个 patch | 重构被测函数以降低耦合 |

## 常见问题

### 运行问题

**Q: 运行报错 `no tests collected`？**
A: 确认使用了正确的 marker 名：`.venv/bin/python -m pytest src/test/ -m "edge" --collect-only` 可预览匹配的测试。

**Q: 报告中文乱码？**
A: 确保操作系统编码为 UTF-8。Windows PowerShell：`chcp 65001`；Linux/Mac 默认即可。

### LLM 相关

**Q: 需要跳过 LLM 测试？**
A: 使用 `--mode edge` 仅跑边缘用例，或 `.venv/bin/python scripts/test_runner.py --mode scenario` 仅跑业务场景（不含 LLM 场景）。若要排除全部 LLM 相关（单元 + 场景），使用 `.venv/bin/python -m pytest src/test/ -m "not llm"`。注意 `--mode unit` **包含** `unit_llm`（均为 mock，无需 API key），不跳过 LLM。

### 标记问题

**Q: 新增测试文件后运行报错 `missing unit_* marker`？**
A: `unit/conftest.py` 的验证模式要求每个单元测试文件必须包含 `unit_*` 子标记。在文件顶部添加 `pytestmark = [pytest.mark.unit, pytest.mark.<子组>]`，子组名见 `conftest.py` 注册表（如 `unit_providers`、`unit_report` 等）。

**Q: 如何添加新的测试标记？**
A: 在 `src/test/conftest.py` 的 `pytest_configure` 中注册新标记，然后在测试类前加 `@pytest.mark.<新标记>`。单元测试使用模块级 `pytestmark` 列表，而非类级装饰器。

**Q: 如何验证新增文件的标记是否正确？**
A: 运行 `.venv/bin/python scripts/check-test-markers.py`，脚本会静态扫描所有 `test_*.py` 文件，检查标记完整性、是否有拼写错误、`_edge.py` 是否漏标 `edge` 等。
