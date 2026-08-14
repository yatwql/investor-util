# 开发者指南

> 文档版本：0.10.13

## 概述

面向本仓库开发者的一站式指南：开发环境与工作流、三级门禁、任务编号规范、测试驱动、辅助脚本速查、版本发布流程。开发者从日常编码到发布的全流程在此闭环。

> **纪律唯一来源**：本指南是面向人的"入口版"，代码注释、测试隔离、目录结构同步等完整纪律见 [CLAUDE.md](../../CLAUDE.md)，细节以该文档为准。

## 开发环境与工作流

| 项 | 约定 |
|:---|:-----|
| **默认工作分支** | `dev`（日常开发、提交均在此分支） |
| **发布分支** | `master`（仅从 dev 合并，打版本标签后发布） |
| **语言** | 中文（UI、报错、报告内容） |
| **Python 环境** | 所有 Python 命令一律使用项目虚拟环境解释器——Linux/macOS 用 `.venv/bin/python`，Windows 用 `.venv\Scripts\python.exe`；**禁止**裸 `python3`/`python`/`pytest`（会命中系统解释器，缺失 pandas 等依赖）。运行测试、脚本、CLI 均同 |
| **提交规范** | 约定式提交：`feat`/`fix`/`docs`/`refactor`/`test`/`chore`/`perf`/`ci` + 可选 scope；修复类可在标题标注对应任务编号 |
| **日志** | `logging` → `logs/app.log` + console（INFO / WARNING / ERROR） |

## 三级门禁

按开发阶段逐级收紧的质量屏障，与测试模式的关系见下：

| 门禁 | 触发点 | 命令 | 说明 |
|:-----|:-------|:-----|:-----|
| **P0** | 提交前 | `.venv/bin/python scripts/test_runner.py --mode dev-verify` + 4 个 check 脚本 | 阻塞提交，不得 commit |
| **P1** | 合入 master 前 | `.venv/bin/python scripts/test_runner.py --mode verify` | 阻塞合入，不得 merge |
| **P2** | 发布前 | `.venv/bin/python scripts/test_runner.py --mode verify,regression` + 4 个 check 脚本 | 阻塞发布，不得 release |

**P0 提交前门禁**（全部通过才可 commit）：

```bash
.venv/bin/python scripts/test_runner.py --mode dev-verify   # 核心单元 + 基础场景快速验证
.venv/bin/python scripts/check-code-traces.py --ci          # 代码注释历史痕迹 + 任务编号标识符检查
.venv/bin/python scripts/check-doc-traces.py --ci           # 文档历史痕迹检查
.venv/bin/python scripts/check-task-numbering.py --ci       # 任务编号全局一致性检查
.venv/bin/python scripts/check-semantic-index.py --ci       # 语义命名索引正反向校验
```

**P1 合入门禁**：`test_runner.py --mode verify`（核心模块单元测试），否则不得 merge。

**P2 发布门禁**：

```bash
.venv/bin/python scripts/test_runner.py --mode verify,regression   # 单元 + 场景验证
.venv/bin/python scripts/check-code-traces.py --ci
.venv/bin/python scripts/check-doc-traces.py --ci
.venv/bin/python scripts/check-task-numbering.py --ci
.venv/bin/python scripts/check-semantic-index.py --ci
```

**辅助（非阻塞）**：`.venv/bin/ruff format --check`（代码格式一致性）——格式问题可通过 `.venv/bin/ruff format` 自动修复，不阻止合并/发布。

> P1/P2 的完整要求（含手动验证项）见 [testplan.md](testplan.md) → 回归测试清单 / 门禁章节。

## 任务编号规范与自动保障

### 编号规则

- `plan.md` 任务清单：`plan-{全局递增序号}`（从 1 开始单调递增，已归档或已完成序号不回收）
- `review-findings.md` 自审问题：`rf-{全局递增序号}`（同样从 1 开始单调递增）
- 序号仅用于标识，**不编码优先级/层级/分类**；优先级在分类表头文字中表达
- 跨文档引用时必须带前缀（`plan-`/`rf-`）避免歧义；历史数据保持原名不追溯重命名

### 编号源标记

各管理文档头部维护「编号源」标记记录**下一个可用编号**：`plan.md` → `plan-next`、`review-findings.md` → `rf-next`。新增任务时**取当前值**作为编号，完成后**递增更新标记**（+1）。标记单调递增、绝不回退，保证与历史归档编号不冲突。

### 语义化命名

代码标识符（函数/变量/类/模块/config 键）与文档正文一律用**语义名**，**禁止用任务代号**（`plan-{N}`/`rf-{N}`/系列代号）。任务代号仅存在于内部计划表作链接锚点，不扩散到实现层。该纪律由双脚本强制——`check-code-traces.py`（负面禁止）+ `check-semantic-index.py`（正面校验「功能语义命名表」与代码一致）。

### 自动保障机制

任务编号全局单调递增、归档不回收，由 `check-task-numbering.py` 校验，防止新增编号与历史归档冲突。四层自动保障：

| 机制 | 触发 | 跨机器 |
|:-----|:-----|:------|
| **P0/P2 门禁** | 提交/发布前 `check-task-numbering.py --ci` | ✅ 零配置 |
| **dev-verify preflight** | `test_runner.py --mode dev-verify` 自动运行 | ✅ 零配置 |
| **Claude Code hook** | 编辑 `plan.md`/`review-findings.md` 后实时校验 | ⚠️ clone 后运行 `.venv/bin/python scripts/install-claude-hook.py` |
| **git pre-commit** | `git commit` 涉及编号文档时自动校验 | ⚠️ clone 后运行 `sh .githooks/install-hooks.sh` |

> `core.hooksPath` 与 `.claude/settings.json` 均为本地配置、不随仓库同步，新机器 clone 后运行上方激活命令一次即可；hook 脚本本体（`.githooks/`、`scripts/`）随仓库同步。

## 测试指南

测试框架基于 **pytest**，通过标记（marker）分组支持灵活组合运行，使用 `scripts/test_runner.py` 统一驱动并自动输出结构化报告。各 `--mode` 的精确测试项数统计见 [test-coverage.md](test-coverage.md)。

### 前置条件

```bash
# 安装测试依赖
pip install pytest pytest-html pytest-mock pytest-xdist
# 可选：覆盖率报告
pip install pytest-cov coverage
```

> 以上仅安装测试插件。项目主依赖（httpx、openpyxl、akshare 等）见 `requirements.txt`：`pip install -r requirements.txt`。

### 快速开始

```bash
# 查看所有可用选项
.venv/bin/python scripts/test_runner.py --help

# ===== ① 日常常用（快速反馈，提交前验证） =====

# 提交前快速验证（P0 门禁；耗时因机器而异，参考 test-coverage.md）
.venv/bin/python scripts/test_runner.py --mode dev-verify

# 冒烟测试（快速验证核心通路）
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

# 数据正确性验证
.venv/bin/python scripts/test_runner.py --mode data

# 真实网络验证（opt-in，不入门禁，仅排查数据源连通性时手工运行）
.venv/bin/python scripts/test_runner.py --mode live

# 运行全量 + 行覆盖率报告
.venv/bin/python scripts/test_runner.py --coverage

# ===== ③ 全量/CI 门禁（耗时较长） =====

# 开发期快速验证（5 个 unit 子模块并行 + 基础场景）
.venv/bin/python scripts/test_runner.py --mode dev-verify

# 合入验证 — PR 前检查
.venv/bin/python scripts/test_runner.py --mode verify

# 全量测试（--mode verify,regression 覆盖单元+场景）
.venv/bin/python scripts/test_runner.py --mode verify,regression

# 全量测试（排除单元测试，快速全场景覆盖）
.venv/bin/python scripts/test_runner.py --mode all_no_unit
```

### 只重跑上次失败的测试（`--lf`）

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
#   verify     → "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web"

# 然后用 pytest -m + --lf 组合运行
.venv/bin/python -m pytest src/test/ -m "scenario" --lf                  # 等价 --mode regression 的失败重跑
.venv/bin/python -m pytest src/test/ -m "unit_providers" --lf            # 等价 --mode unit 下 unit_providers 的失败重跑
.venv/bin/python -m pytest src/test/ -m "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web" --lf  # 等价 --mode verify
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

### 测试模式详解

测试框架围绕两个概念组织：**pytest 标记（marker）** 是测试用例的固有属性（标注"这是什么测试"）；**`--mode`** 是 `scripts/test_runner.py` 脚本对标记的预定义组合（定义"应该运行哪些测试"）。每个 mode 对应一个或多个标记表达式，脚本解析后传给 `.venv/bin/python -m pytest -m` 执行。

#### 回归测试级别

每个回归项按影响范围分四级，与三级流水线的对应关系：

| 级别 | 定义 | 阻断点 | 对应的流水线阶段 |
|:-----|:-----|:-------|:----------------|
| **P0** | 阻塞提交 — 核心功能不可用 | 不得 commit | ① `dev-verify` |
| **P1** | 阻塞合入 master | 不得 merge | ② `verify` |
| **P2** | 阻塞发布 | 不得 release | ③ `verify,regression` |
| **P3** | 建议修复 | 不阻断 | — |

P0 问题必须在 commit 前解决，否则代码不应进入版本控制。P1 问题允许提交但不允许合入主分支。P2 允许合入主分支但不应发布版本。P3 属于已知缺陷或待优化项，可带缺陷发布。

> 注意：P0-P3 是**问题影响力分级**，regression/verify/all 是**测试范围分级**，两者通过门禁阶段关联但不一一对应。例如 P0 问题恰好在 regression 模式中被检出，但 regression 模式并非仅包含"P0 级别"的测试用例——它覆盖全量业务场景，其中任何一项失败都可能导致 P0 阻断。

> **耗时说明**：测试耗时与硬件/操作系统/并行度强相关，不同机器上可能相差一个数量级，因此本文档不标注具体秒数。各模式耗时对照见 [test-coverage.md](test-coverage.md)（「环境耗时对照」表，按机器分列实测）——需预估耗时先在表中定位本机环境列。若本机未在表中，可运行 `python scripts/test_runner.py --mode bench --update-docs` 自动采集回填。

#### 三级验证流水线

项目推荐的四道质量门禁，按开发阶段逐级收紧：

- **提交前门禁（`--mode dev-verify` / P0）** — commit 前必须执行。组合 6 个 unit 子模块（unit_core/unit_providers/unit_fetcher/unit_analysis/unit_scripts/unit_web，并行）+ 基础业务场景（`scenario_basic`），排除 edge/data 和极限场景。是编辑-验证循环中的正式屏障。
- **全场景回归（`--mode regression`）** — commit 前可选的全场景补充验证。覆盖全部 `scenario` 业务场景测试（S0a/S0b/S0d + S1-S33 + T1-T21），确保端到端用户路径不被破坏。推荐在改动了跨模块路径或数据流后补充运行。
- **合入验证（`--mode verify` / P1）** — 准备合并到 master 前必须执行。覆盖 `unit_core`（核心基础设施：缓存引擎、数据模型、注册表）、`unit_providers`（数据源 Provider：腾讯、东方财富、天天基金等）、`unit_fetcher`（数据获取调度：价格、指数、行业分类）、`unit_config`（配置管理）、`unit_news`（新闻聚合）、`unit_llm`（LLM 模块）、`unit_analysis`（分析计算：流动性/再平衡/汇率/债券收益率等）、`unit_scripts`（工程脚本：历史痕迹/版本一致性/任务编号检查）、`unit_web`（Web 入口：上传/运行/进度/产物）九个单元模块。确保数据从抓取→缓存→计算的整条管道通畅且正确。并行执行。场景测试已在 P0 dev-verify（基础场景）和 P2 verify,regression（全场景）中覆盖，P1 不重复。
- **发布验证（`--mode verify,regression`）** — 发布版本（打 tag/release）前必须执行。组合单元测试 + 场景测试，覆盖全部核心通路。
  > 注：若走常规 `dev → merge → tag master` 流程，P1 已保证 `verify` 通过，P2 的 `verify` 属冗余验证。保留冗余是为了覆盖**直接从 dev 打 tag 发布**（未过 P1 合入门禁）的场景。如确定流程中有严格 merge 屏障且不直接发布 dev，P2 可优化为仅 `--mode regression`。详见 [testplan.md](testplan.md) → §6.3 脚注。

> `regression` 与 `scenario` 底层使用相同的标记表达式（`-m "scenario"`），前者是语义别名——强调"提交前快速回归"的用途定位；后者是分类名——强调"业务场景测试"的数据性质。两者可互相替代，但建议按使用场合选用对应名称以增强代码意图可读性。

**推荐工作流：**

```
编码 → --mode dev-verify → commit → 多次积累 → merge → P1 --mode verify → release前 → P2 --mode verify,regression
          ↑                                    ↗
    改完代码随时跑                      若改跨模块调用
      提交前必过P0门禁                  先跑 --mode integration
```

在一次典型开发周期中：
1. **提交前门禁验证**：修改代码后运行 `--mode dev-verify` 确认核心单元+基础场景通过（P0 强制）
2. **全场景补充验证**：若改动了跨模块路径/数据流，再跑 `--mode regression` 确保全场景正常
3. 如果改了跨模块调用关系（缓存、新闻流水线、TUI 路由等），再跑 `--mode integration` 确认接口契约和全链路正常
4. 如果改了 Provider、缓存或数据获取逻辑，再跑 `--mode verify` 确认整条管道通畅
5. 通过后 commit，积累多次提交后准备合并到 master
6. 合并前 CI 自动跑 `--mode verify` 作为合入门禁
7. 发布版本前 CI 自动跑 `--mode verify,regression` 全量验证

#### 模式与覆盖范围说明

每种 `--mode` 对应一组 pytest 标记表达式，由 `scripts/test_runner.py` 转换为 `.venv/bin/python -m pytest -m "<表达式>"` 执行。各模式的覆盖范围存在包含与被包含关系，理解这种关系有助于缩小验证范围以快速反馈：

##### 单元测试系列（`unit` / `standard`）

- **`--mode unit`** 覆盖所有标记为 `unit_*` 的测试（13 个子组：providers、fetcher、llm、news、report、config、config_edge、core、analysis、ui、cli、scripts、web），不含场景测试。这是对代码库中各独立模块的功能正确性验证，所有网络请求均为 mock，不依赖外部 API。
- **`--mode standard`** 在 `unit` 基础上排除 edge（异常边界）和 data（数据正确性）两个跨类标记，仅保留"常规路径"的单元测试。适用于日常开发中快速验证模块本身逻辑正确，不需要关心边界情况。

##### 场景测试系列（`scenario` / `regression` / `integration` / `verify`）

- **`--mode scenario`** 覆盖所有标记为 `scenario_*` 的测试（6 个子组：basic、resilience、llm、datetime、perf、security）。这些测试模拟真实用户操作（如菜单 E/B/L 生成报告），组合多个模块进行端到端验证。

  场景测试按职责分为 **7 大类**：

  - **`scenario_basic` — 基础业务链路**：验证正常业务流程，包括纯股票/纯基金/混合多账户的市值穿透计算、缓存首次/命中逻辑、特殊品种（港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债）的正确分类和计算，以及持仓质量边界（清仓不计入、同名多份额合并、特殊字符不乱码（超多持仓 S0c 在 scenario_extreme）），以及操作行为场景（S29-S33：分红送转除权/定投成本摊薄/部分调仓卖出/跨账户转仓/新股中签待上市）。
  - **`scenario_resilience` — 异常容错场景**：验证系统在非正常输入或环境下的降级能力，包括纯债券基金组合（穿透无股权覆盖）、网络中断（价格从过期缓存读取）、单账户单持仓、零成本持仓（不除零崩溃）。
  - **`scenario_extreme` — 极限场景**：验证极端数据下的正确性，包括超多持仓（S0c，200+ 条批量计算）和极端值（S10，超大/极小份额、高精度净值、零值组合）。标记 `scenario_extreme`，不包含在 `scenario` / `scenario_basic` / `scenario_resilience` 中，需单独运行 `--mode scenario_extreme`。
  - **`scenario_llm` — LLM 场景组合**：验证 LLM 模块在各种状态下的行为，包括缓存/成功/失败混合状态的颜色渲染、五种失败原因独立映射、Extended Thinking 标记、禁用优先原则、断网降级、全缓存无调用、三种输出格式（Excel/HTML/Summary）一致性。
  - **`scenario_datetime` — 日期/时间场景**：验证系统在不同市场时段（盘中/盘前/午休/盘后/非交易日/长假）、产品类型（场外基金/QDII/ETF/股票/混合）、边界条件（时段切换/缝隙/首次启动/断网）以及特殊日历（跨年/季末/汇率故障/调休/港股通假期）下的数据获取正确性和降级表现。

- **`--mode regression`** 与 `--mode scenario` 完全相同，但语义定位为"提交前回归验证"。建议在 git hook 或 CI 前置检查中使用此名称，使流水线意图更加清晰。
- **`--mode integration`** 覆盖场景测试 + 集成测试（`scenario or integration`）。在全部业务场景基础上，增加模块间验证：接口契约、错误隔离、新闻流水线、缓存一致性、TUI 路由。用于修改了跨模块调用关系后的定向回归。
- **`--mode dev-verify`** 提交前门禁模式（P0），组合 6 个 unit 子模块（unit_core/unit_providers/unit_fetcher/unit_analysis/unit_scripts/unit_web，排除 edge/data）并行 + 基础业务场景（`scenario_basic`）。约 20s，适合开发者改完代码后随时跑。不包含极限场景（scenario_extreme）和 LLM/日期/容错等专项场景。
- **`--mode verify`** 合入门禁模式（`unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web`），包含核心基础设施 + 数据源 Provider + 数据获取调度 + 配置管理 + 新闻聚合 + LLM 模块 + 分析计算 + 工程脚本的单元测试，共约 10s（并行执行）。场景测试由 P0 dev-verify（基础场景）和 P2 verify,regression（全场景）覆盖。

##### 专项验证系列（`edge` / `data` / `smoke`）

- **`--mode edge`** 仅运行标记为 `edge` 的测试，覆盖各种异常和边界情况：零值、空数据集、并发竞态、Unicode、时区安全、文件系统边界、API 网络异常等。适用于修改了函数内部错误处理逻辑后的针对性验证。
- **`--mode data`** 仅运行标记为 `data` 的测试，覆盖数据精确性：市值=价格×份额、盈亏=市值-成本、收益率=盈亏÷成本（成本>0）、穿透 TOP10 占比归一化等。适用于修改了数值计算逻辑后的回归。
- **`--mode smoke`** 仅运行标记为 `smoke` 的测试，从 6 个全流程关键节点各选 4 项最快基础测试：核心数据模型→入口读取→分类计算→报告输出→启动依赖→数据获取。全部为纯内存计算、无 IO、每项 <0.1s（速度参考见 `test-coverage.md`）。适用于部署后冒烟或极速"通不通"检查。

##### 真实网络验证（`live`，opt-in，不入门禁）

- **`--mode live`** 运行真实外部网络验证套件（`src/test/live/`），用于排查「数据源是否真的可达 / API 是否漂移」时手工验证。**平时（含 dev-verify/verify/all 全量门禁）完全不运行**——由三层机制保证：
  1. `pytest.ini` 的 `addopts = -m "not live"` 在收集期直接排除；
  2. `conftest.py` 的 `_skip_live_unless_requested` autouse fixture 默认跳过（`-m live` 收集到也 skip）；
  3. `_block_external_network` 阻断 fixture 对非 live 项一律拦死真实网络。
- **内容**：覆盖行情（A 股/ETF/场外基金/中美指数）、新闻源（东方财富/财联社/新浪/华尔街见闻）、基金（历史净值/排名/基准）、akshare 交易日历共 14 项。
- **断言原则**：只校验返回「结构」（字段存在、类型、非空），**不校验具体数值**，容忍真实行情波动（休市、涨跌、数据源改字段）。
- **不含 LLM 真实调用**（防费用）——LLM 连通性由运行时数据源健康检查覆盖。
- 触发方式：`.venv/bin/python scripts/test_runner.py --mode live` 或 `.venv/bin/python -m pytest --run-live -m live`。

##### 全量（`all`）

- **`--mode verify,regression`** 组合模式，等价于分别运行 verify（单元） + regression（场景）。约 30s，作为发布门禁。
- **`--mode all`** 不设任何标记过滤（`.venv/bin/python -m pytest src/test/`），运行全量测试。需要全覆盖时手动调用。
- **`--mode all_no_unit`** 排除所有单元测试（`-m "not unit"`），仅保留场景测试、集成测试和跨类测试。适用于想要全场景覆盖但跳过纯模块逻辑验证的场景。

##### 多模式组合

`--mode` 支持逗号分隔同时运行多个模式：

```bash
# 同时运行场景测试和边缘测试
.venv/bin/python scripts/test_runner.py --mode scenario,edge
```

脚本按 MODES 字典定义的 order 顺序依次执行各模式，结果汇总到同一份 HTML 报告中。适用于 CI 流水线中按阶段逐步收紧的场景。精确实时计数请运行 `.venv/bin/python -m pytest src/test/ --collect-only -q`。

##### `--mode` 与 pytest `-m` 对照

| `--mode` | 等效 `-m` 表达式 | Linux 开发机参考耗时 |
|:---------|:-----------------|:--------:|
| `regression` | `scenario` | ~17s |
| `smoke` | `smoke` | ~2s |
| `unit` | `unit` | ~15s |
| `standard` | `unit and not (edge or data)` | ~16s |
| `edge` | `edge` | ~13s |
| `data` | `data` | ~2s |
| `scenario` | `scenario` | ~18s |
| `integration` | `scenario or integration` | ~14s |
| `verify` | `unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts` | ~10s |
| `dev-verify` | `(unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts) and not (edge or data)` + `scenario_basic`（两阶段） | ~20s |
| `all` | （无过滤，全量） | ~21s |
| `all_no_unit` | `not unit` | ~10s |
| `report` | `unit_report` | ~11s |
| `scenario_extreme` | `scenario_extreme` | ~2s |

> 注：**Linux 开发机参考耗时**按 2026-08-05 实测（Linux x86_64，Intel i5-13500H，12 核 16 线程，46.8 GiB 内存；pytest-xdist worker=8 = medium 50% 核数）。耗时与硬件/操作系统/并行度强相关，不同机器上可能相差一个数量级，仅作相对量级参考；完整说明及不同环境下的耗时对照见 [test-coverage.md](test-coverage.md)（顶部注 + 「采集环境属性」/「各模式耗时对照」表）。若需本机实测，运行 `python scripts/test_runner.py --mode bench --update-docs` 自动采集回填。

##### 跨机器耗时采集与环境耗时对照（`bench` + `--machine-info` / `--update-docs`）

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

### 查看报告

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

### 快速定位失败用例 — `extract-test-failures.py`

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

### 标记选择运行速查

以 `.venv/bin/python -m pytest -m "<表达式>"` 形式快速选取特定标记组合，适合开发调试中定向验证。

**场景标记**：

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

**单元子模块标记**：

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
| `unit_web` | Web 入口（浏览器模式上传/生成/进度/产物，`src/python/web/`） |
| `unit_providers or unit_fetcher` | 数据管道（Provider + 调度） |

**横切标记**：

| 表达式 | 覆盖范围 |
|:-------|:---------|
| `smoke` | 冒烟 |
| `edge` | 边缘/异常场景 |
| `data` | 数据正确性验证 |
| `llm` | 全部 LLM（单元 + 场景） |
| `not llm` | 排除 LLM 后的全量 |

**集成测试标记**：

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

**组合查询示例**：

```bash
# 查看指定标记下有哪些测试（不执行）
.venv/bin/python -m pytest src/test/ -m "edge" --collect-only

# 运行单个测试文件
.venv/bin/python -m pytest src/test/unit/report/test_category.py -v

# 运行单个测试类
.venv/bin/python -m pytest src/test/unit/report/test_category.py::TestCategoryAggregationConsistency -v

# 冒烟测试（快速验证核心通路）
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

### 测试文件规范

- **命名**：`test_<module>.py`
- **类名**：`Test<Feature>`，继承 `unittest.TestCase`
- **方法**：`test_<场景>`
- **单文件上限**：≤ 800 行 / ≤ 80 测试项 / ≤ 15 方法每类
- **标记规则**：单元测试用 `pytestmark` 模块级列表（`[pytest.mark.unit, pytest.mark.<子组>]`），场景测试用类级 `@pytest.mark.scenario + @pytest.mark.<子组>`，edge 测试在 `pytestmark` 中追加 `pytest.mark.edge`
- 新增文件后运行 `.venv/bin/python scripts/check-test-markers.py` 验证标记合规性

### 新增测试指南

新增测试用例时，按以下流程操作：

**确定测试类型和文件位置**：

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

**命名规范**：

```python
# 测试类名 — 模块/场景名 + 测试维度
class TestCacheEdgeCases:          # 模块 + 测试类型
class TestGetTtlMarketAware:       # 函数名 + 场景
class TestScenarioS21:             # 新业务场景递增

# 测试方法名 — test_ + 场景 + 预期结果
def test_empty_holdings_returns_zero(self):
def test_ttl_during_trading_hours_returns_30s(self):
def test_qdii_nav_date_delayed_t2(self):
```

**新增后必须更新的文件**：

1. **`test-coverage.md` 场景测试分组表** — 新增 S/T/D 场景时补充条目（含测试类参考列）
2. **`folders.md`** — 新增 test_*.py 文件后更新目录树
3. **`changelog.md`** — 记录新增的测试数量和覆盖场景
4. **`plan.md`** — 如果在迭代中新增的功能，更新对应条目的完成状态
5. **`unit/conftest.py`** — 新增 `unit/` 下测试文件时确认 `pytestmark` 列表包含正确的 `unit_*` 子标记

**新增后必须执行的验证**：

```bash
.venv/bin/python -m pytest src/test/                                   # 全量通过
.venv/bin/python -m pytest --co                                         # 无 patch 残留污染
.venv/bin/python -m pytest src/test/unit/core/test_registry.py --co -v      # 新文件隔离（示例）
.venv/bin/python scripts/check-test-markers.py                # 标记合规性检查（AST 静态扫描）
```

**文件膨胀阈值**：

| 指标 | 警告线 | 红线 | 措施 |
|:-----|:------:|:----:|:-----|
| 单文件测试数 | > 80 项 | > 120 项 | 拆分到子文件 `test_xxx_part1.py` / `test_xxx_part2.py` |
| 单文件行数 | > 800 行 | > 1200 行 | 考虑按被测函数 / 场景类型拆分 |
| 单类方法数 | > 15 项 | > 25 项 | 拆为多个 Test 类或拆分文件 |
| 单方法 mock 数 | > 5 个 patch | > 8 个 patch | 重构被测函数以降低耦合 |

### 常见问题

**Q: 运行报错 `no tests collected`？**
A: 确认使用了正确的 marker 名：`.venv/bin/python -m pytest src/test/ -m "edge" --collect-only` 可预览匹配的测试。

**Q: 报告中文乱码？**
A: 确保操作系统编码为 UTF-8。Windows PowerShell：`chcp 65001`；Linux/Mac 默认即可。

**Q: 需要跳过 LLM 测试？**
A: 使用 `--mode edge` 仅跑边缘用例，或 `.venv/bin/python scripts/test_runner.py --mode scenario` 仅跑业务场景（不含 LLM 场景）。若要排除全部 LLM 相关（单元 + 场景），使用 `.venv/bin/python -m pytest src/test/ -m "not llm"`。注意 `--mode unit` **包含** `unit_llm`（均为 mock，无需 API key），不跳过 LLM。

**Q: 新增测试文件后运行报错 `missing unit_* marker`？**
A: `unit/conftest.py` 的验证模式要求每个单元测试文件必须包含 `unit_*` 子标记。在文件顶部添加 `pytestmark = [pytest.mark.unit, pytest.mark.<子组>]`，子组名见 `conftest.py` 注册表（如 `unit_providers`、`unit_report` 等）。

**Q: 如何添加新的测试标记？**
A: 在 `src/test/conftest.py` 的 `pytest_configure` 中注册新标记，然后在测试类前加 `@pytest.mark.<新标记>`。单元测试使用模块级 `pytestmark` 列表，而非类级装饰器。

**Q: 如何验证新增文件的标记是否正确？**
A: 运行 `.venv/bin/python scripts/check-test-markers.py`，脚本会静态扫描所有 `test_*.py` 文件，检查标记完整性、是否有拼写错误、`_edge.py` 是否漏标 `edge` 等。

## 辅助脚本速查

项目 `scripts/` 目录下的所有工具脚本用法速查，按分类组织。

### 一览

| 脚本 | 分类 | 一句话 |
|:-----|:-----|:-------|
| `test_runner.py` | 测试 | pytest 标记模式封装驱动，支持 14 种 `--mode` |
| `extract-test-failures.py` | 测试 | 从 pytest-html 报告提取失败用例详情 |
| `check-code-traces.py` | 测试 | 代码注释/文档字符串中历史变更痕迹检查 |
| `check-doc-traces.py` | 测试 | 面向读者文档（.md）中历史变更痕迹检查 |
| `check-test-markers.py` | 测试 | AST 静态扫描验证测试标记合规性 |
| `check-task-numbering.py` | 测试 | 任务编号（plan-/rf-）全局一致性检查，防新增编号与历史归档冲突 |
| `check-task-numbering-hook.py` | 测试 | Claude Code PostToolUse hook——编辑编号管理文档后自动校验编号一致性 |
| `check-semantic-index.py` | 测试 | 功能语义命名表正反向一致性校验（表外键 / 僵尸条目 / 合并章 key 缺失） |
| `install-claude-hook.py` | 测试 | 安装/卸载 Claude Code PostToolUse hook（任务编号一致性自动校验） |
| `llm_hallucination_sampler.py` | 测试 | 10 组标准持仓 × LLM 幻觉率采样 |
| `calibrate-dedup-threshold.py` | 测试 | 新闻去重阈值校准分析 |
| `collect-test-coverage.py` | 测试 | 测试覆盖计数收集（`--collect-only` 快照，供 test-coverage.md 更新） |
| `smoke-web.py` | 测试 | Web 模式 HTTP 冒烟脚本（test_client 进程内全链路断言，可独立运行） |
| `check-version-consistency.py` | 质量 | 版本号全局一致性检查（发布前必跑） |
| `perf_report.py` | 诊断 | 端到端报告生成管线性能基准（独立脚本，mock 外部数据源） |
| `perf_view.py` | 诊断 | 性能历史趋势查看（读取 perf_history.jsonl → 跨版本耗时对比） |
| `diagnose_gemini_proxy.py` | 诊断 | Gemini API 代理连通性诊断 |
| `probe-csi-factor-indices.py` | 诊断 | CSI 风格指数可用性探测（风格因子回归前置决策闸门） |
| `launch.sh` / `launch.ps1` | 启动 | Linux/macOS / Windows 一键启动脚本（无参数启动 TUI；`web` 子命令启动 Web 浏览器模式） |
| `cli.sh` / `cli.ps1` | 启动 | Linux/macOS / Windows CLI 命令行包装（无参数默认生成报告） |
| `check-sources` | 诊断 | cli.py 子命令：数据源联通性检测 |
| `whatif` | 诊断 | cli.py 子命令：调仓 What-if 模拟（对比两份持仓生成独立 diff 报告，见 [快速开始](../manuals/how-to-start.md)） |

### 测试类

**`test_runner.py` — 测试模式驱动**

pytest 的 `-m` 标记表达式封装层，按 `--mode` 选择预定义组合。所有 `--mode` 的详细说明见上文「测试模式详解」章节。

```bash
# 查看所有可用 mode
.venv/bin/python scripts/test_runner.py --help

# 日常提交前门禁（P0）
.venv/bin/python scripts/test_runner.py --mode dev-verify

# 合入门禁（P1）
.venv/bin/python scripts/test_runner.py --mode verify

# 发布门禁（P2）
.venv/bin/python scripts/test_runner.py --mode verify,regression

# 跨机器耗时采集 + 自动更新 test-coverage.md 环境耗时对照（含机器信息采集）
.venv/bin/python scripts/test_runner.py --mode bench --update-docs

# 带行覆盖率
.venv/bin/python scripts/test_runner.py --mode unit --coverage
```

**`extract-test-failures.py` — 失败用例提取**

见上文「快速定位失败用例」章节。

**`smoke-web.py` — Web 模式 HTTP 冒烟脚本**

Web 模式全链路可复跑冒烟验证（上传→生成→进度→产物，Flask `test_client` 进程内走 HTTP 契约，不占端口、不发真实网络）。管线（fake executor）、健康探测、历史记录均 mock，`output_dir` 与上传目录临时隔离，不触碰真实数据。

```bash
# 全量断言（页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离/正式-用存量/配置编辑）
.venv/bin/python scripts/smoke-web.py

# 仅打印失败项
.venv/bin/python scripts/smoke-web.py --quiet
```

退出码：0 = 全部通过；2 = 存在失败项。同款断言已由 `src/test/unit/web/test_smoke_web.py`（`unit_web` 标记）纳入 `dev-verify`/`verify` 门禁，本脚本用于手动快速复跑。

**`check-code-traces.py` — 代码注释历史痕迹检查**

扫描 `src/python/`、`src/test/`、`src/static/`、`scripts/` 下所有 `.py` / `.js` / `.mjs` / `.html` / `.sh` / `.ps1` / `.bat` / `.cmd` 文件的注释和文档字符串，检查是否含有代码历史迭代信息（来源拆分、版本号、任务编号、历史迭代叙述等）。代码注释只应描述"当前是什么"，不应记录"从哪里来、怎么变的"。

```bash
# 检查全部
.venv/bin/python scripts/check-code-traces.py

# 详细输出（含排除行信息）
.venv/bin/python scripts/check-code-traces.py -v

# CI 模式（仅输出 文件名:行号，非零退出码）
.venv/bin/python scripts/check-code-traces.py --ci
```

**退出码含义**：

| 退出码 | 含义 | 行动 |
|:------:|:-----|:-----|
| 0 | 全部通过 | 无需处理 |
| 1 | HIGH/ORIGIN/VERSION 痕迹 | 必须修复后再提交 |
| 2 | CODE/IDENT/CHAPTER/ROUND（任务编号/标识符/章节编号引用） | 应从注释/标识符中移除 |
| 3 | 仅 TODO/CHANGE/DEPR 级别 | 建议人工复核 |

**`check-doc-traces.py` — 文档历史痕迹检查**

扫描项目根 `README.md` 与 `docs-stm/managements/`、`docs-stm/manuals/` 下所有 `.md` 文件（豁免 `changelog.md` / `review-findings.md` / `plan.md` 及 `archive/`、`plan/`、`tmp/` 目录），检查面向读者的文档正文是否含有历史变更信息（来源叙述、历史实现、迁移痕迹、任务编号、归档文件引用、版本号、Iter 迭代标记等）。此类文档只应描述"当前是什么/做什么"，不应记录"从哪里来、怎么变的"；历史记录集中在管理文档（changelog / review-findings / plan）中。

两条核心规则：
1. **正文不得带历史痕迹**：文档正文不得包含历史变更信息（来源叙述、原/旧实现、迁移/重命名、任务编号、版本号、Iter 迭代标记等），只反映"当前是什么/做什么"。例外：`changelog.md` / `plan.md` / `review-findings.md`（历史/计划记录性质）
2. **正文不得引用归档文件**：除上述三个例外文档外，其他管理文档与用户文档正文不得引用 `docs-stm/archive/` 下目录或 `archived_*.md`。例外：`folders.md` 的目录树（`│ ├ └` 行）与统计表行可引用 archive 目录及文件名——目录树记录项目结构，archive/ 条目是结构的一部分

细节规则：
- **Markdown 围栏代码块**（``` 包裹）内为命令/配置示例，非文档叙述，自动跳过（避免 `git tag`、`APP_VERSION` 等示例误报）
- **版本头豁免仅行首锚定**：只豁免 `> 文档版本：vX.Y.Z` 这类版本头行；行中叙述（如"该功能于版本 `vX.Y.Z` 中引入"）仍会命中版本号痕迹
- **当前能力描述豁免**：暂不支持 / 不再支持 / 不正式支持 / 发布版本前 / 门禁流程等合法当前状态描述不报
- **运行时产物归档描述豁免**：报告按日期归档属当前功能描述（"归档版报告" / "历史归档至 `YYYYMMDD/` 日期子目录" / "报告已归档到 `reports/`" 等），不视为仓库归档引用
- **LOW 级别**：命中需人工判断的变更/过渡类描述时提示复核，不阻塞提交

```bash
# 检查全部
.venv/bin/python scripts/check-doc-traces.py

# 详细输出（含豁免行信息）
.venv/bin/python scripts/check-doc-traces.py -v

# CI 模式（仅输出 文件名:行号，非零退出码）
.venv/bin/python scripts/check-doc-traces.py --ci
```

**退出码含义**：

| 退出码 | 含义 | 行动 |
|:------:|:-----|:-----|
| 0 | 全部通过 | 无需处理 |
| 1 | HIGH/ARCHIVE/CODE/CIPHER/CHAPTER/ROUND 痕迹 | 应从文档中移除 |
| 2 | 仅 LOW 级别痕迹（需人工判断的变更/过渡类描述） | 建议人工复核 |

**`check-test-markers.py` — 标记合规性检查**

AST 静态扫描所有 `test_*.py` 文件，检查：
- 标记完整性（是否有 `unit_*` 子标记）
- 拼写错误（未注册的 marker 名）
- `_edge.py` 是否漏标 `edge`，或非 `_edge.py` 文件是否误标 `edge`

```bash
.venv/bin/python scripts/check-test-markers.py
```

无报错输出即合规。新增/修改测试文件后必须运行此脚本。

**`check-task-numbering.py` — 任务编号全局一致性检查**

校验 `plan-` / `rf-` 两类任务编号与各管理文档头部的「编号源」标记（`plan-next` / `rf-next`）是否一致，防止新增编号与历史归档冲突。

新增任务时，编号取管理文档头部 `plan-next` / `rf-next` 当前值，用后将其递增更新；若标记遗漏递增或初值写小，本脚本会扫描当前文档 + 全部历史归档并报错提示修正值。

```bash
.venv/bin/python scripts/check-task-numbering.py            # 检查全部（plan + rf）
.venv/bin/python scripts/check-task-numbering.py --kind rf  # 仅检查 rf
.venv/bin/python scripts/check-task-numbering.py --ci       # CI 模式（只输出错误）
```

自动保障机制（四层，跨机器同步策略见「任务编号规范与自动保障」章节）：P0 门禁、dev-verify preflight、Claude Code hook、git pre-commit。

**`check-semantic-index.py` — 语义命名索引正反向一致性检查**

校验技术设计文档（`technical.md`）「功能语义命名表」章节（`<!-- semantic-index:start/end -->` 标记区间）与代码的**正面一致性**，与 `check-code-traces.py` 的负面禁止互补：

1. **正向**：`_config_defaults.py` 中 `report_submodules` 字典每个键（运行时配置开关）必须已登记在「功能语义命名表」中（防新增开关绕过登记）
2. **反向**：表中每个语义 slug 在 `src/python/` 下至少一处非注释代码引用（防僵尸条目——功能删除后表行残留）
3. **合并章**：表下「合并章代码标识符」注声明的 sheet key 必须存在于 `core/registry.py` 的 `_REPORT_SECTION_DEFAULT` 注册表

```bash
.venv/bin/python scripts/check-semantic-index.py       # 检查全部
.venv/bin/python scripts/check-semantic-index.py -v    # 详细输出（打印每项解析结果）
.venv/bin/python scripts/check-semantic-index.py --ci  # CI 模式（只输出错误，退出码 2）
```

**`check-task-numbering-hook.py` — Claude Code PostToolUse hook**

Claude Code 编辑 `plan.md` / `review-findings.md` 后自动运行编号校验，失败返回非零退出码中断编辑。读取 `__INJECTED_OBJECT__`（环境变量或命令行参数）识别目标文件；无 hook 上下文或非编号文档时放行。由 `.claude/settings.json` 的 PostToolUse 钩子调用（不随仓库同步，需 `install-claude-hook.py` 接线）。

**`install-claude-hook.py` — Claude Code hook 安装/卸载**

`.claude/settings.json` 被 `.gitignore` 排除、不随仓库同步。本脚本将 `check-task-numbering-hook.py` 的 PostToolUse 钩子写入该文件，跨机器 clone 后运行一次即完成接线。

```bash
.venv/bin/python scripts/install-claude-hook.py             # 安装（幂等，保留已有配置）
.venv/bin/python scripts/install-claude-hook.py --uninstall # 卸载
```

**`install-hooks.sh` — git pre-commit hook 激活脚本（`.githooks/`）**

`.githooks/` 的 git pre-commit hook（任务编号一致性校验）默认**休眠**——`core.hooksPath` 是本机 git 配置、不随仓库同步。clone 后运行一次激活：

```bash
sh .githooks/install-hooks.sh          # 启用（写入本机 core.hooksPath）
sh .githooks/install-hooks.sh --off   # 停用
```

与 `install-claude-hook.py`（Claude Code hook）配套；两条 hook 均调用 `check-task-numbering-hook.py` 校验编号文档。

**`llm_hallucination_sampler.py` — LLM 幻觉率采样**

见下文「LLM 幻觉率采样测试」章节。

**`calibrate-dedup-threshold.py` — 新闻去重阈值校准**

新闻标题去重（同源/跨源两档阈值 + 中文 bigram）在每次报告运行时自动记录"边界案例"到 `data/cache/dedup_anchors.jsonl`。积累足够锚点后，用此脚本分析当前阈值是否合理。

```bash
# 分析全部锚点，输出建议
.venv/bin/python scripts/calibrate-dedup-threshold.py

# 仅看汇总统计（不展开详细列表）
.venv/bin/python scripts/calibrate-dedup-threshold.py --summary

# 指定锚点文件
.venv/bin/python scripts/calibrate-dedup-threshold.py --file data/cache/dedup_anchors.jsonl
```

**校准时机**：建议锚点文件积累 **100 条以上**（约 5~10 次报告运行）后校准一次。脚本只分析不自动修改阈值，是否需要调整由开发者判断。

**`collect-test-coverage.py` — 测试覆盖计数收集**

只做 `.venv/bin/python -m pytest --collect-only`（收集测试项，**不执行测试**，耗时约 2s），按 `test_runner.py` MODES 的 marker 表达式本地归类计数，输出各模式 / unit 子标记 / scenario 分组 / 跨类标记 / 功能域 / 文件分布的项数，供 `docs-stm/managements/test-coverage.md` 快照更新使用。

```bash
.venv/bin/python scripts/collect-test-coverage.py
```

**说明**：
- 只收集不执行——测试体不会运行，不影响测试结果，也不会触发真实数据源 / LLM 调用
- 项数随版本迭代变化，属撰写时快照，精确计数以本脚本实时输出为准
- 计数口径与 `test_runner.py` 的 `MODES` marker 表达式对齐（verify / dev-verify 等组合模式同样本地复现）

### 质量类

**`check-version-consistency.py` — 版本号一致性检查**

发布版本前必须运行。检查 `APP_VERSION`（`src/python/core/constants.py`）与以下文件的版本号是否一致：

- `pyproject.toml`（`version` 字段，`--fix` 可自动同步）
- `README.md`
- 管理文档 10 份：`plan.md`、`technical.md`、`requirements.md`、`testplan.md`、`review-findings.md`、`llm-technical.md`、`folders.md`、`test-coverage.md`、`changelog.md`、`developer-guide.md`

```bash
# 无参数运行，逐项检查并报 [OK]/[ERR]
.venv/bin/python scripts/check-version-consistency.py
```

全部 `[OK]` 方可提交。如有 `[ERR]`，按提示逐个同步，然后重跑直到全部通过。版本切换工作流见下文「版本发布流程」章节。

### 诊断类

**`perf_report.py` — 端到端性能基准**

生成 20+ 品种 + 3 年模拟持仓，运行 basic/both 报告生成管线，测量各阶段耗时。

```bash
.venv/bin/python scripts/perf_report.py
```

**输出**：`docs-stm/tmp/better-investment-performance-test-report.md`

**目标**：basic 模式总耗时 < 60s

**`perf_view.py` — 性能历史趋势查看**

读取 `data/state/perf_history.jsonl`（由 `PerfCollector` 在每次报告生成时自动追加），按版本和报告类型分组统计，输出版本间性能趋势对比。

```bash
# 输出全部历史趋势到 stdout
.venv/bin/python scripts/perf_view.py

# 仅看 full 类型报告的性能趋势
.venv/bin/python scripts/perf_view.py --report-type full

# 仅看最近 30 条记录
.venv/bin/python scripts/perf_view.py --last 30

# 同时写入 docs-stm/tmp/perf_trend.md
.venv/bin/python scripts/perf_view.py --save
```

**输出列说明**：

| 列 | 含义 |
|:---|:------|
| 阶段 | 报告生成管线阶段名称（行情获取/快照对比/历史走势/HTML 生成/Excel 生成 等） |
| 平均耗时 | 该阶段历史平均耗时 |
| 最短/最长 | 该阶段历史最小/最大耗时 |
| 次数 | 该阶段出现次数（条件阶段如历史走势仅在启用时出现） |

**数据来源**：每次 `generate_report()` 调用时自动记录到 `data/state/perf_history.jsonl`，无需手动触发。

**`diagnose_gemini_proxy.py` — Gemini API 代理诊断**

当 Gemini API 代理（如 `http://10.22.207.29:10037`）出现连通性问题时，逐项检测网络层、代理层和 API 层的健康状况。

```bash
.venv/bin/python scripts/diagnose_gemini_proxy.py
```

**检测项目**：
1. 直接 Google 连通性（`google.com`）
2. 代理服务器连通性（`telnet` 式探测）
3. 代理 HTTP 请求（`curl -x` 等效）
4. Gemini API 真实调用（使用当前 `llm_key.json` 配置）
5. DNS 解析
6. 各环境变量（`HTTP_PROXY` / `HTTPS_PROXY` / `http_proxy` / `https_proxy`）

每项显示 ✅/❌ 状态和详细错误信息，定位哪一层出了问题。

**`probe-csi-factor-indices.py` — CSI 风格指数可用性探测**

CSI 风格指数可用性探测（风格因子回归前置决策闸门），决定风格因子回归是否可用。

### 启动脚本

**`launch.sh` — Linux/macOS 启动**

```bash
./scripts/launch.sh
```

**`launch.ps1` — Windows PowerShell 启动**

```powershell
.\scripts\launch.ps1
```

两者均负责：激活虚拟环境（如存在）、设置 `PYTHONPATH`、启动主程序 TUI。

**`launch.sh web` / `launch.ps1 web` — Web 浏览器模式**

```bash
./scripts/launch.sh web                       # Linux/macOS，默认监听 http://127.0.0.1:8000
./scripts/launch.sh web --port 8080           # 换端口
./scripts/launch.sh web --host 0.0.0.0        # 局域网访问（绑定非回环地址需自行评估暴露风险）
```

```powershell
.\scripts\launch.ps1 web                      # Windows，默认监听 http://127.0.0.1:8000
.\scripts\launch.ps1 web --port 8080
```

`web` 子命令启动轻量 Web 服务（`src/python/web/server.py`），浏览器打开提示地址即可上传持仓、选择报告格式（基础/标准/完整）、实时查看生成进度并预览/下载产物；亦支持 `--config <path>` 指定备用配置文件（详见 [快速开始](../manuals/how-to-start.md) 方式四）。同一时间仅执行一个报告生成任务（单 worker 串行队列），新任务自动排队。

**`cli.sh` / `cli.ps1` — CLI 命令行包装**

CLI 模式的便捷入口，跳过 TUI 界面，直接以命令行模式运行。**无参数调用时默认生成报告**（`report --type both`，Excel+HTML 双格式，不含 LLM——全部页签有数据）；传入参数时原样透传给 CLI。

```bash
# Linux/macOS
./scripts/cli.sh                        # 无参数 -> 默认生成报告（both，Excel+HTML）
./scripts/cli.sh report --type full     # 生成全量报告（含 LLM）
./scripts/cli.sh cache --stats          # 查看缓存状态
./scripts/cli.sh --help                 # 查看 CLI 帮助
```

```powershell
# Windows PowerShell
.\scripts\cli.ps1                        # 无参数 -> 默认生成报告（both，Excel+HTML）
.\scripts\cli.ps1 report --type full     # 生成全量报告（含 LLM）
.\scripts\cli.ps1 cache --stats          # 查看缓存状态
.\scripts\cli.ps1 --help                 # 查看 CLI 帮助
```

与直接调用 Python 模块**完全等效**（二选一即可）：

```bash
.venv/bin/python -m src.python.cli report --type both      # Linux/macOS 直调
.venv\Scripts\python.exe -m src.python.cli report --type both   # Windows 直调
```

> 注意：包装脚本的「无参数默认 both」与 CLI 本身的 `--type` 默认值（basic，仅 Excel）不同——直接直调 `python -m src.python.cli report`（不带 `--type`）仍走 basic 轻量模式（只生成核心页签，新闻/历史/LLM 等页签为降级占位）。包装脚本无参数时自动补 `report --type both`，确保拿到完整非 LLM 报告。

包装脚本相比直调的好处：自动切换到项目根目录、自动定位虚拟环境解释器（避免误用系统 python 缺失 pandas 等依赖）、无参数时自动补 `report` 子命令。CLI 完整参数说明见 [快速开始](../manuals/how-to-start.md) 的「CLI 命令行模式」一节。

### CLI 子命令

**`check-sources` — 数据源健康检查**

跳过 TUI 交互界面，直接测试各数据源联通性并报告延迟。

```bash
# 运行数据源健康检查
.venv/bin/python -m src.python.cli check-sources
```

**输出示例**：

```
数据源健康检查结果 (YYYY-MM-DD)
──────────────────────────────────────────────────────────
  ✅  腾讯财经      行情           45ms  正常
  ✅  新浪财经      行情           82ms  正常
  ⚠️  天天基金      持仓/排名     2.3s  响应慢
  ❌  财联社        新闻           timeout  连接超时
```

**检查覆盖范围**：腾讯财经行情、新浪财经行情、东方财富净值、天天基金持仓/排名、东方财富行业分类、新浪财经新闻、东方财富新闻、华尔街见闻、财联社、腾讯 K 线——共 **10 个端点**。

**退出码**：0=全部正常，1=有告警（部分源慢），2=有失败。

### LLM 幻觉率采样测试

对 **10 组标准化持仓数据** 调用当前 prompt，经事实校验器验证后统计幻觉率（`scenario_llm` 幻觉率采样测试）。

**数据集简介**：

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

**脚本用法**：

```bash
# 完整采样（调用 LLM API 对 10 组数据生成分析）
.venv/bin/python scripts/llm_hallucination_sampler.py

# 仅测试特定模块（默认 expert_review）
.venv/bin/python scripts/llm_hallucination_sampler.py --module health_check

# 仅测试特定数据集（1-indexed）
.venv/bin/python scripts/llm_hallucination_sampler.py --dataset 1,3,5

# 跳过 API 调用，只构建 prompt 验证结构
.venv/bin/python scripts/llm_hallucination_sampler.py --dry-run

# 跳过缓存强制重新生成
.venv/bin/python scripts/llm_hallucination_sampler.py --force
```

**输出**：
- 报告文件：`docs-stm/tmp/hallucination-report.md`
- Dry-run prompt 转储：`docs-stm/tmp/hallucination-prompts-{module}.md`

**注意**：事实校验器对仓位占比百分比和情景假设百分比设跳过策略（`_POSITION_WEIGHT_KEYWORDS` / `_HYPOTHETICAL_KEYWORDS`），避免将百分比陈述误报为幻觉。最终幻觉率以 `docs-stm/tmp/hallucination-report.md` 为准。

## 注册表使用（registry）

`src/python/core/registry.py` 是本项目的**中央注册表**，统一管理所有数据模块的：中文名称（`name`）、缓存前缀（`cache_prefixes`）、缓存 TTL（`cache_ttl`）、精确缓存键（`exact_cache_keys`）、LLM Settings 后缀（`settings_suffix`）、缓存分组（`cache_groups`）。

设计原则：**一处注册，全局生效**。新增数据模块只需在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`，所有派生结构自动同步。

> **架构背景**：注册表是数据获取层与报告生成层之间的契约层，详细架构说明见 [technical.md](technical.md)（缓存层 / 报告生成层章节）；当前已注册模块的功能语义清单见其「功能语义命名表」章节。

### 核心数据结构

```python
@dataclass(frozen=True)
class DataModuleDef:
    name: str                    # 中文名称（报告标题、日志、TUI 展示）
    data_type: str               # 数据类型键（用于 TTL 查找）
    cache_prefixes: tuple[str, ...] = ()
    exact_cache_keys: tuple[str, ...] = ()
    cache_ttl: float = CACHE_DAILY
    settings_suffix: str | None = None   # None 表示非 LLM 模块
    cache_groups: tuple[str, ...] = ()
```

- `DataModuleDef` 是不可变的（`frozen=True`），注册后不可修改。
- `is_llm` — 自动判断是否为 LLM 模块（`settings_suffix is not None`）。
- `llm_settings_keys()` — 生成该模块在 `llm_settings.json` 中的所有合法键名，新增 LLM 模块后可用于配置校验。

### 公共 API 速查

**遍历与查询**：

```python
from src.python.core.registry import get_registry
registry = get_registry()          # → tuple[DataModuleDef, ...]
```

**缓存相关**：

```python
from src.python.core.registry import (
    get_cache_ttl_defaults,        # → dict[data_type → ttl]
    get_prefix_type_map,           # → dict[prefix → data_type]
    get_exact_type_map,            # → dict[exact_key → data_type]
    get_registered_data_types,     # → set[data_type]
)
```

`get_cache_ttl_defaults()` 供 `config/_config_defaults.py` 生成默认配置模板；`get_prefix_type_map()` / `get_exact_type_map()` 供 `cache/_cleanup.py` 按文件名前缀 / 精确键名清理过期缓存；`get_registered_data_types()` 用于校验与测试。

**LLM 模块名称查询**：

```python
from src.python.core.registry import (
    get_llm_module_name,           # suffix → 中文名称
    get_llm_module_names,          # → dict[suffix → 名称]
)
```

合法 suffix：`global_macro` / `expert_review` / `health_check` / `penetration_deep` / `news_correlation`（另含缓存管理保留条目 `debate_pro` / `debate_con` / `debate_synthesis`，菜单层已隐藏）。

**LLM Settings 键名查询**：

```python
from src.python.core.registry import get_known_llm_settings_keys   # → set[str]
```

返回 `llm_settings.json` 中所有合法配置键名，用于配置校验。

**enabled_llm 子键查询**：

```python
from src.python.core.registry import get_known_enabled_llm_keys    # → set[str]
```

返回 `enabled_llm` 字典的所有合法子键（即各 LLM 模块的 `settings_suffix`），用于 `_validate_enable_llm()` 的子键拼写校验。

**报表排序与页签名称**：

```python
from src.python.core.registry import (
    get_report_sheet_name,         # sheet_key → 中文标题
    get_report_section_order,      # config → list[dict]（含 key/number/type/data_flag 的完整排序列表）
    get_report_section_number,     # key → 当前配置下的序号
    get_report_section_keys,       # → list[key]
)
```

- `get_report_sheet_name("summary")` → `"投资分析汇总"`
- `get_report_section_order(config)` → 解析 `report_section_order` 配置，返回有序键列表
- `get_report_section_number("fund_manager")` → 当前配置下该模块的序号（被基金深度分析各页签写入器调用）
- `get_report_section_keys()` → 全部 19 个模块键名（键名→中文标题对照见 [配置指南 → report_section_order](../manuals/how-to-config.md#report_section_order-报告序号配置)）

**计算模块查询**：

```python
from src.python.core.registry import (
    get_computation_registry,      # → tuple[ComputModuleDef, ...]
    get_computation_module,        # module_key → ComputModuleDef | None
)
```

`get_computation_registry()` 遍历所有计算/分析模块，用于运行时发现和文档生成；`get_computation_module("analytics_metrics")` 按 module_key 查找单个计算模块定义。

### 新增数据模块（非 LLM）

在 `_MODULE_REGISTRY` 中添加一行 `DataModuleDef`：

```python
DataModuleDef("我的中文名称", "my_data_type",
              cache_prefixes=("mydata_",),
              cache_ttl=CACHE_DAILY,
              cache_groups=("refresh",)),
```

- `name` — 中文显示名；`data_type` — 内部标识键，需唯一。
- `cache_prefixes` — 缓存文件名前缀（可多个），清理时按前缀匹配。**注意：长前缀需排在短前缀之前**，否则短前缀可能先匹配（如 `"llm_"` 会误匹配 `"llm_global_macro_"`）。实际声明时所有 LLM 模块均已使用完整长前缀，无歧义。
- `cache_ttl` — 使用 `CACHE_DAILY` / `CACHE_WEEKLY` / `CACHE_MONTHLY` 或自定义秒数。
- `cache_groups` — `"preload"`（换持仓需重取）或 `"refresh"`（主动刷新按钮触发）；**留空 `()` 表示不被任何组清除操作命中**（如 `tracking`、`calendar` 等安全设计）。

### 新增 LLM 分析模块

除上述字段外，还需设置 `settings_suffix`：

```python
DataModuleDef("我的 LLM 分析", "llm_my_analysis",
              cache_prefixes=("llm_my_analysis_",),
              cache_ttl=7200,
              settings_suffix="my_analysis",
              cache_groups=("preload",)),
```

#### 新增 LLM 模块检查清单

| # | 步骤 | 操作位置 | 产出 |
|---|------|---------|------|
| ① | **注册模块定义** | `core/registry.py` → `_MODULE_REGISTRY` | 添加 `DataModuleDef` 实例，含 `settings_suffix` |
| ② | **配置 JSON 键组** | `llm_settings.json` | 新增 9~10 个 `{key}_{suffix}` 配置键（`news_correlation` 不含 `output_brief`） |
| ③ | **实现生成函数** | `llm/generators.py` | 新增生成函数，通过 `_call_llm()` 调用 LLM |
| ④ | **注册调度入口** | `llm/generators_orchestrator.py` | 在 `_MODULE_FNS` 字典中添加新模块条目（键=settings_suffix，值=lambda 调用新函数）；在 `_compute_module_cache_info()` 中添加对应的指纹计算和 `info` 条目 |
| ⑤ | **添加报告页签** | `report/llm_content.py` | 在 `write_llm_sheets()` 的 `_module_keys` 和 `_module_contents` 列表中添加新模块键名 |
| ⑥ | **暴露导出接口** | `llm/__init__.py` | 将新生成函数加入 `__all__` |
| ⑦ | **运行注册表测试** | 终端 | `.venv/bin/python -m pytest src/test/unit/core/test_registry.py -v` — 验证 TTL/前缀/键名完整性 |
| ⑧ | **验证标记合规** | 终端 | `.venv/bin/python scripts/check-test-markers.py` — 确认测试文件标记无遗漏 |

> **LLM 模块补充步骤**：在上述 registry 清单基础上，新增 LLM 模块还需完成领域特定步骤——`llm/prompts.py` 新增 `_SYSTEM_{MODULE}` 常量与提示词构建函数；`report/html_writer.py`（HTML）+ `report/llm_content.py`（Excel）新章节双渲染；`config.json` → `cache_ttl` 添加 `llm_{module}` 条目；`llm_settings.json` 加入推荐默认值并更新 [配置指南](../manuals/how-to-config.md)。

### 精确键名缓存

```python
DataModuleDef("我的固定键", "fixed",
              exact_cache_keys=("my_special_cache",),
              cache_ttl=CACHE_WEEKLY),
```

精确键名不会被前缀通配误匹配，适合固定文件名的缓存。

### 计算模块注册表（_COMPUTATION_REGISTRY）

除 `_MODULE_REGISTRY`（有缓存的数据模块）外，`core/registry.py` 还维护 `_COMPUTATION_REGISTRY`——纯计算模块（无缓存）的注册表：

```python
@dataclass(frozen=True)
class ComputModuleDef:
    name: str               # 中文名称
    module_key: str         # 唯一键，如 "analytics_liquidity"
    label: str              # 短标签（日志/提示）
    dependencies: tuple     # 前置数据模块键名
    description: str        # 功能说明
```

| module_key | 名称 | 依赖 | 状态 |
|:-----------|:-----|:-----|:----:|
| `analytics_metrics` | 量化指标计算 | bond_yield, history | ✅ implemented |
| `analytics_liquidity` | 流动性分析 | — | ✅ implemented |
| `analytics_fx_exposure` | 外汇敞口分析 | — | ✅ implemented |
| `analytics_scenario` | 情景分析 | history | ✅ implemented |
| `analytics_alignment` | 组合校准分析 | — | ✅ implemented |
| `analytics_inferrer` | 用户画像推断 | — | ⏳ planned |
| `analytics_fact_checker` | 事实锚定校验器 | — | ✅ implemented |

新增计算模块只需在 `_COMPUTATION_REGISTRY` 中添加一行 `ComputModuleDef`，纯算法模块无需缓存注册。

### 无需手动维护的派生产出

新增模块时只需在 `_MODULE_REGISTRY` 添加一行 `DataModuleDef`，即可自动同步到以下位置：

- 缓存 TTL 默认值 → `get_cache_ttl_defaults()`
- 缓存前缀/精确键名映射 → `get_prefix_type_map()` / `get_exact_type_map()`
- LLM settings 键名 → `get_known_llm_settings_keys()`
- LLM 模块名称 → `get_llm_module_names()`

> 报表页签标题与顺序由独立的 `_REPORT_SECTION_DEFAULT` 注册表驱动，`get_report_sheet_name()` / `get_report_section_order()` 均读该注册表，**不**随 `_MODULE_REGISTRY` 自动派生。

### 测试

registry 的测试在 `src/test/unit/core/test_registry.py`，验证 TTL 默认值完整性、前缀类型映射一致性、精确键名映射、LLM settings keys 与模块列表匹配、所有 LLM 模块都有 settings_suffix、缓存分组标记完整性。

```bash
.venv/bin/python -m pytest src/test/unit/core/test_registry.py -v
```

## 版本发布流程

发布版本时，按以下四步顺序执行：

**① 版本号一致**

先修改 `src/python/core/constants.py`（`APP_VERSION`），然后运行：

```bash
.venv/bin/python scripts/check-version-consistency.py
```

按 `[ERR]` 提示逐个同步其余文件（`pyproject.toml`、`README.md`、各管理文档），直到全部 `[OK]` 再提交。任何版本号变更均应全局覆盖，避免遗漏。

**② 发布数据文档刷新**

发布版本前，必须运行：

```bash
.venv/bin/python scripts/collect-test-coverage.py
```

按实时收集结果核对/更新以下文档的数据快照（非版本号），保证统计与目录结构时效性：
- `test-coverage.md` — 模式/unit 子标记/跨类/功能域各项测试计数
- `folders.md` — 项目统计表及目录树新增/重命名文件
- `datasource.md` + `datasource-reliability.md` — 数据源清单/路由归属/可靠性描述与实际代码配置一致

数据快照更新与「版本号一致」的版本头同步可在同一次提交内完成。

**③ 版本标签**

完成版本号更新并提交后，执行：

```bash
git tag v{版本号}
git push origin --tags
```

确保每次发布都可追溯。

**④ 开发版本切换**

发布版本并打 tag 后，**立即**将 `APP_VERSION` 和所有管理文档版本头改为**下一个版本的 `-dev`**（如发布 v0.6.8 后即改为 v0.6.9-dev），运行 `check-version-consistency.py` 验证全链 `[OK]` 后提交，然后继续开发。开发期间版本号始终标识为下一个预期发布版本的 `-dev`。

## 关键纪律来源

本指南为面向开发者的"入口版"。以下完整纪律以 [CLAUDE.md](../../CLAUDE.md) 为准：

- **架构遵从**：所有模块必须遵守 `technical.md` 的「架构设计约束」表格（含设计目的/违反后果/适用范围）和「概要设计—核心架构决策」。涉及数据降级/熔断逻辑时额外参考概要设计双重降级治理体系说明
- **测试隔离**：运行测试不得修改用户的配置文件、持仓文件等敏感数据；`conftest.py` 自动将 `config.json` 和缓存目录重定向到临时目录
- **缺陷自测**：发现并修复缺陷时，**必须**为该缺陷编写可自测的回归测试用例，避免再次回退；新增功能时**必须**同步编写测试用例覆盖
- **目录结构同步**：新增/重命名任何非排除文件或目录时，**必须**同步更新 `folders.md` 中的目录树，并确保每个文件都有简短说明
- **文件归属三原则**：中间计划文件 → `docs-stm/plan/`；运行时临时产物 → `docs-stm/tmp/`；`.claude/` 全局目录只存放 Claude Code 工具自动管理的运行时数据，**禁止主动写入**任何文件
