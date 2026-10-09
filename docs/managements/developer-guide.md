# 开发者指南

> 文档版本：0.12.7-dev

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
### pi 模型与服务配置（编程档采样 + 订阅端点节流 + 缓存/思考调优）

本项目**版本受控**的 pi 配置分两个文件，作用域机制不同：

| 文件 | 作用域 | 生效条件 |
|---|---|---|
| `.pi/models.json` | 模型覆盖 | 软链到 `~/.pi/agent/models.json`（pi **不读**项目级 models.json） |
| `.pi/settings.json` | 项目设置 | **pi 直接读项目级 settings.json**，但需 `~/.pi/agent/trust.json` 已授予该项目信任 |

`.pi/models.json` 的覆盖分两类：

**① 编程档采样（`deepseek` 按量端点）**

| 覆盖项 | 值 | 为什么 |
|---|---|---|
| `samplingParams.temperature` | `0.0` | DeepSeek 官方建议：**代码生成/数学解题用 0.0**（通用对话 1.3、创意写作 1.5）；低温让补丁/重构更确定、减少格式抖动 |
| `maxTokens` | `65536` | 内置目录值 384K 对编程偏大；收窄到 64K 仍远超常规补丁/文件写入需要，同时给单次响应设成本上限。**注意思考（reasoning）与正文共享该预算**——预算被思考吃满时正文会被截断 |

> **覆盖键必须与目录当前模型 id 精确匹配**：id 不一致时该覆盖**不生效且无任何告警**（pi 侧按 `Unknown override IDs are ignored` 处理，静默忽略）。因此 **`pi --list-models` 是本文件的唯一验收手段**——JSON 已写入不等于生效；目录同步（内置目录升级、`/model` 重载）后须复核各覆盖仍命中，否则 `maxTokens`/`contextWindow` 会悄悄退回目录默认值。

**② 订阅端点节流（`kimi-coding` / `opencode-go`）**

订阅制端点（Kimi Code / OpenCode Go）按**滚动时间窗**计量，窗口额度按「交互式 agentic coding」标定；而 pi 的自动压缩阈值是 `contextTokens > contextWindow − reserveTokens(默认 16K)`，目录里这些端点 `contextWindow` 高达 1M——**压缩几乎不触发，每轮请求要把近百万 tokens 的上下文发出去**，几个轮次就吃掉一个窗口。故对这两类端点统一收窄（**只降不升**，已低于上限的模型不写覆盖）：

| 覆盖项 | 值 | 为什么 |
|---|---|---|
| `maxTokens` | `65536` | 目录值 128K~384K（如 `grok-4.6` 500K）对编程无必要，且思考与正文共享该预算 |
| `contextWindow` | `262144` | 把「压缩触发点」从 ~1M 拉到 ~246K → **单轮输入封顶**，这是降窗口消耗的最大单项；代价是压缩更频繁、跨轮记忆略少 |

**③ 思考档位（全局，不在本文件）**：`~/.pi/agent/settings.json` 的 `defaultThinkingLevel` 设为 `low`（原 `high`）。思考 token 计入 output，实测输出量≈输入量是其主因；需要时用 `/thinking` 临时提升。

**④ 提示缓存保留（`PI_CACHE_RETENTION=long` + `promptCache` 声明）**

缓存命中把重复前缀按缓存读价计费（DeepSeek 缓存读约为标准输入价的 1/10），所以要尽量让前缀「热着」。这条链需要**两个条件同时成立**，缺一即静默无效：

| 环节 | 载体 | 作用 |
|---|---|---|
| 选择保留档 | shell 环境变量 `PI_CACHE_RETENTION=long`（`~/.bashrc`） | `getPromptCacheTtlMs` 按该值选 `long` 档；未设置则恒为 `short`。解析顺序：凭据块 `env` → `process.env` → Bun 沙箱回退 |
| 声明生命周期 | `.pi/models.json` 覆盖项 `promptCache` | **目录里没有任何模型声明 `promptCache`**，未声明时 `getPromptCacheTtlMs` 返回 `undefined` → 该模型**无缓存保活资格**，环境变量设了也白设。故对 pi 实际使用的按量模型（`deepseek-flash`/`deepseek-v4-pro`）显式声明 `{short: 300, long: 3600}`（取已公布区间的保守端） |

缓存保活本身**消耗额度但不占上下文**（保活请求以 1 token 输出重发，用量计入会话统计，不进模型上下文）；pi 仅在「模型声明了生命周期」且「估算避免的未命中成本 ≥ $0.05」时才保活，故不是盲目刷量。

> **刻意不下发到订阅端点**：`kimi-coding`/`opencode-go` 按窗口计量，保活刷新会白吃窗口额度，而收益取决于端点是否真支持提示缓存（未实测）。这是**待测量项**，不在本配置内。

**⑤ 思考预算（`thinkingBudgets`，`~/.pi/agent` 之外的 `.pi/settings.json`）**

内置档位预算为 `minimal:1024 / low:2048 / medium:8192 / high:16384`（`xhigh`/`max` 亦 16384）。合并语义是 `{...内置默认, ...自定义}`（`thinkingBudgetForLevel`），**故只需写要改的档位**，未写档位继续用内置值。当前只压最低两档（`minimal:512`、`low:1024`），**`medium`/`high` 保持内置**——它们承担用 `/thinking` 提升后的复杂推理，压掉会让升档失效。

**⑥ 诊断开关（`showCacheMissNotices: true`）**

开启后上屏显著缓存未命中、缓存保活成功、**压缩用量**、provider 恢复四类通知。这是排查「额度去哪了」的主观测口：压缩一次要读整个上下文，其用量此前完全不可见。

**未改动**：`thinkingLevelMap`（内置 `low/high/max` 已够用，用 `/thinking` 切档）、`compat`（`thinkingFormat` 等由 pi 内置目录提供）、`input`（flash 为纯文本，视觉实验版另有一个模型）、`samplingParams`（仅对 OpenAI 兼容传输生效；订阅端点走 Anthropic/兼容协议时该参数不适用，故未对它们下发）。

**为什么模型覆盖放在 `.pi/` 而要软链生效**：pi CLI **只读** `~/.pi/agent/models.json`（`getModelsPath() = getAgentDir() + "/models.json"`，`getAgentDir()` 只认 `PI_AGENT_DIR` 或 `~/.pi/agent`），**不读项目级 `.pi/models.json`**；项目级 `.pi/` 仅支持 `settings.json`/扩展/技能/主题。因此模型覆盖的仓库文件是**唯一事实来源**，用软链挂到全局路径生效（`settings.json` 走项目级路径，无需软链）：

```bash
ln -sf "$PWD/.pi/models.json" ~/.pi/agent/models.json
```

验证与排查：

- **`timeout 90 pi --list-models | grep -E 'deepseek|kimi|opencode'`**：`deepseek-flash` 应显示 `65.5K`、`kimi-coding`/`opencode-go` 应显示 `262.1K / 65.5K`；仍是 `1M / 384K` 即**覆盖键名已失效**（目录改名），按上文修正键名
- 出现 `Warning: errors loading models.json` 说明 JSON/schema 有问题
- **项目设置是否生效**：`.pi/settings.json` 依赖项目信任（`~/.pi/agent/trust.json` 里该项目为 `true`）；未授予信任时项目设置被整体忽略，而 `.pi/models.json` 因走软链不受影响——两者失效条件不同，排查时分开看
- 订阅端点用量激增时的排查顺序：① `--list-models` 确认覆盖生效 → ② 会话是否超长（`/new` 分任务）→ ③ 思考档位是否被 `/thinking` 提升 → ④ 打开 `showCacheMissNotices` 看压缩用量与缓存命中
- 若 `~/.pi/agent/models.json` 已是实体文件（例如以后 `/login` 或 `pi config` 写过），软链会失败：先备份再决定合并

## 三级门禁

按开发阶段逐级收紧的质量屏障，与测试模式的关系见下：

| 门禁 | 触发点 | 命令 | 说明 |
|:-----|:-------|:-----|:-----|
| **P0** | 提交前 | `.venv/bin/python scripts/test-runner.py --mode dev-verify` + 十守护（`--ci` 全套，钩子自动执行） | 阻塞提交，不得 commit |
| **P1** | 合入 master 前 | `.venv/bin/python scripts/test-runner.py --mode verify` | 阻塞合入，不得 merge |
| **P2** | 发布前 | `.venv/bin/python scripts/test-runner.py --mode regression` + 十守护（`--ci` 全套） | 阻塞发布，不得 release |

**P0 提交前门禁**（全部通过才可 commit；手动项 = dev-verify，下列十守护由 pre-commit 钩子在 `git commit` 时自动执行、CI guards job 同源兜底，本地不手动重复——清单为五处同源引用）：

```bash
.venv/bin/python scripts/test-runner.py --mode dev-verify   # 核心单元 + 基础场景快速验证
.venv/bin/python scripts/check-code-traces.py --ci          # 代码注释历史痕迹 + 任务编号标识符检查
.venv/bin/python scripts/check-doc-traces.py --ci           # 文档历史痕迹检查
.venv/bin/python scripts/check-task-numbering.py --ci       # 任务编号全局一致性检查
.venv/bin/python scripts/check-semantic-index.py --ci       # 语义命名索引正反向校验
.venv/bin/python scripts/check-doc-drift.py --ci            # 文档与实现一致性（章节/开关/默认值/面板编号/目录树/统计表/归档索引/分区纪律/Thinking 支持矩阵/章节-区块矩阵）
.venv/bin/python scripts/check-test-redundancy.py --ci      # 测试用例冗余与无效（死用例/无断言/完全重复/自证用例/硬编码演进总数）
.venv/bin/python scripts/check-requirement-trace.py --ci   # 需求 ID ↔ 验证载体追溯（已补全域全覆盖 + 载体文件存在）
.venv/bin/python scripts/check-version-consistency.py --ci   # 版本号全局一致性（APP_VERSION ↔ README/pyproject/管理文档 10 份）
.venv/bin/python scripts/check-doc-links.py --ci              # 文档死链/死锚点/重复标题/层级/编号序列/§引用机检
.venv/bin/python scripts/check-file-length.py --ci         # 单文件行数红线（主程序/脚本 >1000 行 / 测试 >1200 行）
```

> **`--sync` 统计快照口径（CI 分叉坑）**：`check-doc-drift --sync`（及 pre-commit 自动回写）按**工作区**实测写入 `folders.md` 行数，而 CI 的 `check-doc-drift` 按 **committed** 树实测——若受检目录存在**长期不提交的修改**（本地游离改动），本地已同步的数字会在 CI 上判「不一致」，连带 guards / test / portability 三个 job 同时红。提交前确认受检文件全部纳入本次提交；有长期游离修改时先提交它们、再 `--sync`。

**P1 合入门禁**：`test-runner.py --mode verify`（核心模块单元测试），否则不得 merge。

**P2 发布门禁**：

```bash
.venv/bin/python scripts/test-runner.py --mode regression              # 场景回归（单元由 P1 合入门禁 + CI master 档覆盖）
.venv/bin/python scripts/check-code-traces.py --ci
.venv/bin/python scripts/check-doc-traces.py --ci
.venv/bin/python scripts/check-task-numbering.py --ci
.venv/bin/python scripts/check-semantic-index.py --ci
.venv/bin/python scripts/check-doc-drift.py --ci
.venv/bin/python scripts/check-test-redundancy.py --ci
.venv/bin/python scripts/check-requirement-trace.py --ci
.venv/bin/python scripts/check-version-consistency.py --ci
.venv/bin/python scripts/check-doc-links.py --ci
.venv/bin/python scripts/check-file-length.py --ci
```

**辅助（非阻塞）**：`.venv/bin/ruff check`（lint 基线，选择项与刻意豁免均在 `pyproject.toml` 显式声明）+ `.venv/bin/ruff format --check`（代码格式一致性）——问题可经 `.venv/bin/ruff check --fix` / `.venv/bin/ruff format` 自动修复，不阻止合并/发布。当前两者均为零告警基线，新增代码应在提交前保持干净。

**CI 同步执行（`.github/workflows/ci.yml`）**：三档测试按分支/标签分流——`dev` 推送跑 P0（`dev-verify`）、`master` 推送或 PR 跑 P1（`verify`）、打 `v*` tag 跑 P2（`regression`），矩阵覆盖 Python 3.11/3.12/3.13；另有三个独立 job：`guards`（**阻塞**，10 个 `--ci` 守护脚本即上方 P0/P2 清单全量——job 内按 pre-commit 同款后台并行回放，任一守护非零退出折叠为 FAIL 分组并使 job 红；守护经 src.python 链依赖项目运行时包（如 check-doc-drift → httpx），故 editable 安装保留）、`portability`（**阻塞**，非 UTF-8 locale + 隐式编码双探针，见下方「编码/locale 自检」）与 `format`（非阻塞，`ruff format --check src/python/ scripts/` + `ruff check`）。

### 编码/locale 自检（旧 pip 回退解码 / 隐式编码）

本机与 CI 的常规三道测试全跑在 **UTF-8 locale** 上，因此「旧 pip 对含非 ASCII 的需求文件回退 locale 解码」与「未显式 `encoding=` 的文本 I/O」这两类缺陷在常规门禁上**结构性不可见**（中文 Windows cp936 用户首启就装不上依赖、报告写盘时静默变 GBK）。两道精确探针已入 CI `portability` job（阻塞），且都能在任意平台本地复现：

```bash
# ① 旧 pip（最后一版按「BOM → PEP263 cookie → locale 编码」解码）在非 UTF-8 locale 下真实解析需求文件：
#    LC_ALL=C 是同类 locale 回退的最严档（ASCII 单字节，任何非 ASCII 字节必炸）；
#    去掉 requirements.txt 的 BOM 可复现原缺陷（UnicodeDecodeError）
python -m pip install -q "pip==24.3.1"
LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 python -m pip install --dry-run --no-deps -r requirements.txt

# ② PEP 597 隐式编码严格档：任何未显式 encoding= 的文本 I/O 立即失败（豁免项见 pytest.ini）
PYTHONWARNDEFAULTENCODING=1 .venv/bin/python -m pytest src/test/unit -q
```

> ①号命令在受 PEP 668（externally-managed-environment）系统级管理的解释器上会被拒：装进临时 venv 复现，或追加 `--break-system-packages`（`--dry-run` 不做实际安装，无风险）；CI 的 setup-python 环境不受此限。

> 为何不直接跑 Windows runner：GitHub 的 `windows-latest` 是 en-US/cp1252（单字节，只会乱码不会报错），装不住 GBK 类 locale 回退；为何不在 ubuntu 上装 GB18030 跑全套件：中文**文件名**在 POSIX `fsencoding=ascii` 下会失败（18 处中文报表文件名），而 cp936 Windows 反而正常——那是探测方法的伪影，不是缺陷。两道探针因此取「精确模拟消费方」而非「换整个 locale 跑全套件」。

> P1/P2 的完整要求（含手动验证项）见 [testplan.md](testplan.md) → 回归测试清单 / 门禁章节。

### 日志回显纪律（要求改配置必给现值）

凡日志 / CLI / TUI 输出**要求读者调整某个配置值**（并发、间隔、上限、超时、重试、开关等），必须**同时回显该项的当前值与配置项名/所在文件**，使读者不翻配置即可知道「从多少调到多少」：

- **回显形态**：`<config_field>=<值>`、`（当前 X → 已试 Y）`、`provider[<条目>] pacing.max_concurrency=<值>、pacing.min_interval=<值>`；配置里**未声明**时标「未配置」而非留空（避免误读为 0/已配）。
- **密钥/凭据类豁免**：涉及 `api_key` / `llm_key.json` / `data_key.json` / token / password 的提示只回显**文件名、条目名、路径**，绝不回显密钥本体或其片段（对齐 `scenario_security` 的「日志不记录完整密钥」基线）。
- **已覆盖点**：429 诊断 `pacing._concurrency_hint`（两级并发 + 间隔，由 `api_base` 重试骨架复用）、截断提示 `api_base._check_*_truncation`、思考耗尽 `api_base._extract_content`（配置上下文由 `_process_success_response` 经线程局部注入）与 `_api_claude` 安全网日志、截断重试耗尽 `skeleton._handle_truncation`、worker 钳位 `fetcher/batch.py`、阈值超限 `providers/news_dedup.py`。
- **回归用例**：`test_llm_api_base.py::TestThinkingExhaustedConfigEcho`、`test_llm_api_attempt.py::TestAttemptApiCall` 429 回显组（含 `test_rate_limit_429_log_echoes_min_interval_value_when_advised`）、`test_llm_api_retry_errors.py` 429 重试链、`test_skeleton.py::test_exhausted_retry_log_names_config_field_and_both_values`、`test_llm_api.py::test_thinking_exhausted_log_echoes_current_budget`。新增此类日志时按本节口径补回显与用例。

### 计划收尾：文档触点清单与一次性枚举

任务收尾的墙钟主因是「文档触点 × 往返轮次」——触点靠守护报错被动驱动时，每轮报错就是一次完整往返。按任务类型对照下表**主动扫一遍触点**，再按三步工作流收敛：

**触点清单（按任务类型）**：

| 任务类型 | 必同步触点 |
|:---------|:-----------|
| 新报告章节 | `registry.py` 注册表 → `reports-instruction.md`（目录/章节表/分组表/可见性总表/页签上限）→ `requirements.md` 章清单 → `technical.md`（结果区计数/`report_section_order`）→ `how-to-use-tui-menu.md`（报告块编号段）→ `folders.md`（新 partial/模板）→ `report_template.html` include |
| 新功能开关 | `features.py` 注册表 → `how-to-config.md`（开关表+计数+实验/常规分列+Web 面板行）→ `how-to-use-tui-menu.md`（开关区行与编号）→ `technical.md`（语义命名表/开关计数）→ `testplan.md`（若涉门禁） |
| 新文件/目录 | `folders.md` 目录树（`check-doc-drift --sync` 回写统计表）→ 若为 `scripts/*`：本文件「辅助脚本速查」一览与分类段 |
| 新测试 | `conftest.py` marker 注册（若需）→ `.venv/bin/python scripts/collect-test-coverage.py` 刷新 `test-coverage.md` → 边缘用例入 `*_edge.py` |
| 新 LLM 模块/seam | `registry.py` + 统一附录（`skeleton._build_prompt_appendix`）+ `technical.md`（语义命名表/seam 表/附录 H）→ 指纹条件并入用例 |
| 每个计划收尾（通用） | `plan.md`（状态翻转+归档 note）→ 当期计划归档文档（归档段+设计文档索引，入 0.12 期归档）→ `review-findings.md`（rf 登记，rf-next 递增）→ `changelog.md`（含 rf token）→ `test-coverage.md`/`folders.md` 计数刷新 → 涉版本时 `check-version-consistency` |

**三步工作流**：

1. **一次枚举**：编辑全部完成后按下方「计划收尾：文档触点清单」主动扫触点批量核对/修复（统计快照回写与十守护校验由提交时的 pre-commit 钩子自动完成，本地不手动重复）。
2. **批量修复**：按上表 + 触点一次性修完，同一文件多处改动合并为一次 edit。
3. **单次复核**：手动只跑 `dev-verify` 测试门禁；ruff 探针（错误类阻塞 + format 非阻塞提示）与十守护一并交由 `git commit` 的 pre-commit 钩子一次收集（失败即中止）→ 批量修复 → 重新提交，不手动重复跑守护。

**红线**：编辑批次与 `--sync`/检查类脚本**永不同批**（sync 写文件，与编辑并行会竞态）；`check-file-length` 随每批代码改动跑，ruff 由钩子在提交时把关（批内可提前手跑），不留到收尾才爆。

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

### 外部借鉴前置比对清单

引入外部项目（开源仓库、方案、文章）的做法前，**必须先对照本仓库现状**——实测教训：已有多项借鉴（LLM 输出自检、多空双视角辩论、Prompt 模板外置、多源新闻交叉验证）的立项前提被「本仓库已有实现」推翻，属可避免的往返成本（该清单即为此固化的纪律）。

设计文档（`docs/plan/`）开头须逐条填写结论：

| # | 比对项 | 结论要求 |
|:--|:-------|:---------|
| 1 | **能力是否已存在** | 列出检索到的既有实现（模块/函数/开关）与代码位置；已存在则**直接归档为「已评估未采纳」**并写明证据 |
| 2 | **部分存在时的缺口边界** | 明确「已有什么」与「真实缺什么」，据此**重新定位**（例：确定性事实校验已有 → 模型自检改为「分层不重叠」而非新建同类） |
| 3 | **是否已有配置级/开关级替代** | 用户诉求能否由既有配置键或开关满足（例：prompt 定制已由 `system_prompt_*` 覆盖）——已满足则价值须重估 |
| 4 | **是否触及缓存指纹与已校准输出** | 改动若进入提示词正文、影响输入摘要或产物结构，须评估缓存键同源与既有校准的复验成本（缓存指纹唯一事实来源约束） |
| 5 | **是否有真实消费者** | 新能力必须有真实调用方（CLI/报告/评测脚本）；否则属死代码，须先定消费者或不做 |

> 比对结论写进对应设计文档与任务编号管理文档；已存在的能力直接归档为「已评估未采纳」并写明证据。

### 自动保障机制

任务编号全局单调递增、归档不回收，由 `check-task-numbering.py` 校验，防止新增编号与历史归档冲突。五层自动保障：

| 机制 | 触发 | 跨机器 |
|:-----|:-----|:------|
| **P0/P2 门禁** | 提交/发布前 10 个 `--ci` 守护脚本全量（清单见 P0/P2 门禁条款） | ✅ 零配置 |
| **dev-verify preflight** | `test-runner.py --mode dev-verify` 自动运行（仅 `check-task-numbering` 快检；重量守护不入预检，由钩子唯一执行防同树重复） | ✅ 零配置 |
| **Claude Code hook** | 编辑 `plan.md`/`review-findings.md` 后实时校验 | ⚠️ clone 后运行 `.venv/bin/python scripts/install-claude-hook.py` |
| **git pre-commit** | `git commit` 执行十守护（与 P0/CI guards 同源）：**读写分层调度**——不读 folders.md 的守护（快集 code-traces/task-numbering/semantic-index/requirement-trace + py 域 file-length + 测试域 test-redundancy）先行后台启动，与 `check-doc-drift` 串行段（跨域守护，恒跑；涉及 `docs/managements/` 或 `src/test/` 时 `--sync` 自动回写统计快照）并行执行；读 folders.md 的 version-consistency 与 doc 域（doc-traces/doc-links）在 doc-drift 完成后启动（避 --sync 写读竞态）；域条件不变（doc 域仅 `*.md`、py 域仅 `*.py`、测试域仅 `src/test/` 变更触发），典型提交约 1~4 秒；三守护另有结论缓存（输入指纹未变回放上次结论，冷/热 --ci 输出逐字一致）；CI guards job 恒全量兜底 | ⚠️ clone 后运行 `sh .githooks/install-hooks.sh` |
| **CI guards job** | push / PR / tag 时自动校验（10 个 `--ci` 脚本之一） | ✅ 零配置 |

> `core.hooksPath` 与 `.claude/settings.json` 均为本地配置、不随仓库同步，新机器 clone 后运行上方激活命令一次即可；hook 脚本本体（`.githooks/`、`scripts/`）随仓库同步。

## 测试指南

**测试报告布局**：每次运行写入 `test-reports/latest/`——汇总页 `index.html`（各模式的通过/失败/耗时 + 报告链接）与该模式的 pytest-html 详细报告。单轮/非分阶段模式为 `<mode>/report.html`（`dev-verify` 已双阶段合一，单轮报告即此名）；**多阶段模式每阶段一个报告文件**（`<mode>/report_phase_A.html` / `report_phase_B.html`），汇总页逐阶段给链接。早前两阶段曾共用 `report.html`，后跑的阶段会覆盖前者，导致详细报告只剩最后一阶段（排查时看不到真正的失败面）——多阶段逐文件机制即为防此。

测试框架基于 **pytest**，通过标记（marker）分组支持灵活组合运行，使用 `scripts/test-runner.py` 统一驱动并自动输出结构化报告。各 `--mode` 的精确测试项数统计见 [test-coverage.md](test-coverage.md)。

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
.venv/bin/python scripts/test-runner.py --help

# ===== ① 日常常用（快速反馈，提交前验证） =====

# 提交前快速验证（P0 门禁；耗时因机器而异，参考 test-coverage.md）
.venv/bin/python scripts/test-runner.py --mode dev-verify

# 冒烟测试（快速验证核心通路）
.venv/bin/python scripts/test-runner.py --mode smoke

# 仅运行业务场景测试
.venv/bin/python scripts/test-runner.py --mode scenario

# 集成测试（含场景 + 模块间契约/缓存/TUI 路由）
.venv/bin/python scripts/test-runner.py --mode integration

# 全量单元测试（含 edge/data）
.venv/bin/python scripts/test-runner.py --mode unit

# 常规单元测试（排除 edge/data）
.venv/bin/python scripts/test-runner.py --mode standard

# ===== ② 专项验证（定向覆盖） =====

# 仅运行边缘/异常场景测试
.venv/bin/python scripts/test-runner.py --mode edge

# 极限场景（超多持仓/极端值/高精度）
.venv/bin/python scripts/test-runner.py --mode scenario_extreme

# 数据正确性验证
.venv/bin/python scripts/test-runner.py --mode data

# 真实网络验证（opt-in，不入门禁，仅排查数据源连通性时手工运行）
.venv/bin/python scripts/test-runner.py --mode live

# 运行全量 + 行覆盖率报告
.venv/bin/python scripts/test-runner.py --coverage

# ===== ③ 全量/CI 门禁（耗时较长） =====

# 开发期快速验证（6 个 unit 子模块并行 + 基础场景）
.venv/bin/python scripts/test-runner.py --mode dev-verify

# 合入验证 — PR 前检查
.venv/bin/python scripts/test-runner.py --mode verify

# 全量测试（--mode verify,regression 覆盖单元+场景）
.venv/bin/python scripts/test-runner.py --mode verify,regression

# 全量测试（排除单元测试，快速全场景覆盖）
.venv/bin/python scripts/test-runner.py --mode all_no_unit
```

### 只重跑上次失败的测试（`--lf`）

修复代码后验证时，经常只需要重跑**上一次运行失败的那些用例**，而不必等全量通过。pytest 内置的 `--lf`（`--last-failed`）标志专为此场景设计：

```bash
# 只重跑上次 pytest 运行中失败的测试（跳过已通过的）
.venv/bin/python -m pytest src/test/ --lf

# 先收集匹配 marker 的用例，再从其中只重跑上次失败的
.venv/bin/python -m pytest src/test/ -m "unit_providers" --lf
```

**与 `test-runner.py` 的配合**：

`test-runner.py` 使用 `argparse` 管理参数，**不支持** `--` 透传（例如 `.venv/bin/python scripts/test-runner.py --mode all -- --lf` 会报错）。如需 `--lf`，绕过它直接调 pytest，用 `-m` 参数复现目标模式的标记表达式：

```bash
# 先找到目标模式对应的 marker 表达式
# 在 scripts/test-runner.py 的 MODES 字典中查找，例如：
#   regression → "scenario"
#   unit       → "unit"
#   verify     → "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web"

# 然后用 pytest -m + --lf 组合运行
.venv/bin/python -m pytest src/test/ -m "scenario" --lf                  # 等价 --mode regression 的失败重跑
.venv/bin/python -m pytest src/test/ -m "unit_providers" --lf            # 等价 --mode unit 下 unit_providers 的失败重跑
.venv/bin/python -m pytest src/test/ -m "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web" --lf  # 等价 --mode verify
```

> 各 `--mode` 对应的 `-m` 表达式见下文「模式与覆盖范围说明」章节，或直接查看 `scripts/test-runner.py` 中 `MODES` 字典的 `marker` 字段。

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
> - `test-runner.py` 不支持 `--lf`，是因为它用 `subprocess.run` 调 pytest 且 argparse 不接收未注册的 `--` 参数。建议日常快速验证时直接使用 `pytest`，门禁检查时再用 `test-runner.py`。

### 测试模式详解

测试框架围绕两个概念组织：**pytest 标记（marker）** 是测试用例的固有属性（标注"这是什么测试"）；**`--mode`** 是 `scripts/test-runner.py` 脚本对标记的预定义组合（定义"应该运行哪些测试"）。每个 mode 对应一个或多个标记表达式，脚本解析后传给 `.venv/bin/python -m pytest -m` 执行。

#### 回归测试级别

每个回归项按影响范围分四级，与三级流水线的对应关系：

| 级别 | 定义 | 阻断点 | 对应的流水线阶段 |
|:-----|:-----|:-------|:----------------|
| **P0** | 阻塞提交 — 核心功能不可用 | 不得 commit | ① `dev-verify` |
| **P1** | 阻塞合入 master | 不得 merge | ② `verify` |
| **P2** | 阻塞发布 | 不得 release | ③ `regression` |
| **P3** | 建议修复 | 不阻断 | — |

P0 问题必须在 commit 前解决，否则代码不应进入版本控制。P1 问题允许提交但不允许合入主分支。P2 允许合入主分支但不应发布版本。P3 属于已知缺陷或待优化项，可带缺陷发布。

> 注意：P0-P3 是**问题影响力分级**，regression/verify/all 是**测试范围分级**，两者通过门禁阶段关联但不一一对应。例如 P0 问题恰好在 regression 模式中被检出，但 regression 模式并非仅包含"P0 级别"的测试用例——它覆盖全量业务场景，其中任何一项失败都可能导致 P0 阻断。

> **耗时说明**：测试耗时与硬件/操作系统/并行度强相关，不同机器上可能相差一个数量级，因此本文档不标注具体秒数。各模式耗时对照见 [test-coverage.md](test-coverage.md)（「环境耗时对照」表，按机器分列实测）——需预估耗时先在表中定位本机环境列。若本机未在表中，可运行 `.venv/bin/python scripts/test-runner.py --mode bench --update-docs` 自动采集回填。

#### 三级验证流水线

项目推荐的四道质量门禁，按开发阶段逐级收紧：

- **提交前门禁（`--mode dev-verify` / P0）** — commit 前必须执行。组合 6 个 unit 子模块（unit_core/unit_providers/unit_fetcher/unit_analysis/unit_scripts/unit_web，并行）+ 基础业务场景（`scenario_basic`），排除 edge/data 和极限场景。是编辑-验证循环中的正式屏障。
- **全场景回归（`--mode regression`）** — commit 前可选的全场景补充验证。覆盖全部 `scenario` 业务场景测试（S0a/S0b/S0d + S1-S33 + T1-T21），确保端到端用户路径不被破坏。推荐在改动了跨模块路径或数据流后补充运行。
- **合入验证（`--mode verify` / P1）** — 准备合并到 master 前必须执行。覆盖 `unit_core`（核心基础设施：缓存引擎、数据模型、注册表）、`unit_providers`（数据源 Provider：腾讯、东方财富、天天基金等）、`unit_fetcher`（数据获取调度：价格、指数、行业分类）、`unit_config`（配置管理）、`unit_news`（新闻聚合）、`unit_llm`（LLM 模块）、`unit_analysis`（分析计算：流动性/再平衡/汇率/债券收益率等）、`unit_scripts`（工程脚本：历史痕迹/版本一致性/任务编号检查）、`unit_web`（Web 入口：上传/运行/进度/产物）九个单元模块。确保数据从抓取→缓存→计算的整条管道通畅且正确。并行执行。场景测试已在 P0 dev-verify（基础场景）和 P2 verify,regression（全场景）中覆盖，P1 不重复。
- **发布验证（`--mode regression`）** — 发布版本（打 tag/release）前必须执行。覆盖全部场景回归测试。
  > 注：**简化口径已采纳（2026-10-07，详见 [testplan.md](testplan.md) → §6.3 脚注）**：本项目发布流程强制 `dev → merge → tag master`，P1 合入门禁（`--mode verify`）与 CI `master` 档（同提交 verify）已双重覆盖单元验证，tag 档 CI 同步只跑 `regression`；直接从 dev 打 tag（绕过 P1）属流程违规。若流程约束放宽（允许直接发布 dev），须恢复 `--mode verify,regression`。

> `regression` 与 `scenario` 底层使用相同的标记表达式（`-m "scenario"`），前者是语义别名——强调"提交前快速回归"的用途定位；后者是分类名——强调"业务场景测试"的数据性质。两者可互相替代，但建议按使用场合选用对应名称以增强代码意图可读性。

**推荐工作流：**

```
编码 → --mode dev-verify → commit → 多次积累 → merge → P1 --mode verify → release前 → P2 --mode regression
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
7. 发布版本前 CI 自动跑 `--mode regression` 场景回归验证（单元由 P1 master 档覆盖）

#### 模式与覆盖范围说明

每种 `--mode` 对应一组 pytest 标记表达式，由 `scripts/test-runner.py` 转换为 `.venv/bin/python -m pytest -m "<表达式>"` 执行。各模式的覆盖范围存在包含与被包含关系，理解这种关系有助于缩小验证范围以快速反馈：

##### 单元测试系列（`unit` / `standard`）

- **`--mode unit`** 覆盖所有标记为 `unit_*` 的测试（12 个子组：providers、fetcher、llm、news、report、config、core、analysis、ui、cli、scripts、web），不含场景测试。这是对代码库中各独立模块的功能正确性验证，所有网络请求均为 mock，不依赖外部 API。
- **`--mode standard`** 在 `unit` 基础上排除 edge（异常边界）和 data（数据正确性）两个跨类标记，仅保留"常规路径"的单元测试。适用于日常开发中快速验证模块本身逻辑正确，不需要关心边界情况。

##### 场景测试系列（`scenario` / `regression` / `integration` / `verify`）

- **`--mode scenario`** 覆盖带 `scenario` 标记的场景测试（4 个子组：basic、resilience、llm、datetime；`scenario_extreme`、`scenario_perf`、`scenario_security` 不携带该标记，分别由 `--mode scenario_extreme` / `perf` / `security` 单独运行）。这些测试模拟真实用户操作（如菜单 E/B/L 生成报告），组合多个模块进行端到端验证。

  场景测试按职责分为 **7 大类**：

  - **`scenario_basic` — 基础业务链路**：验证正常业务流程，包括纯股票/纯基金/混合多账户的市值穿透计算、缓存首次/命中逻辑、特殊品种（港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债）的正确分类和计算，以及持仓质量边界（清仓不计入、同名多份额合并、特殊字符不乱码（超多持仓 S0c 在 scenario_extreme）），以及操作行为场景（S29-S33：分红送转除权/定投成本摊薄/部分调仓卖出/跨账户转仓/新股中签待上市）。
  - **`scenario_resilience` — 异常容错场景**：验证系统在非正常输入或环境下的降级能力，包括纯债券基金组合（穿透无股权覆盖）、网络中断（价格从过期缓存读取）、单账户单持仓、零成本持仓（不除零崩溃），以及数据链路韧性（多源故障级联熔断、冷却期试探、熔断器持久化、LLM 端点独立熔断）。
  - **`scenario_extreme` — 极限场景**：验证极端数据下的正确性，包括超多持仓（S0c，200+ 条批量计算）和极端值（S10，超大/极小份额、高精度净值、零值组合）。标记 `scenario_extreme`，不包含在 `scenario` / `scenario_basic` / `scenario_resilience` 中，需单独运行 `--mode scenario_extreme`。
  - **`scenario_llm` — LLM 场景组合**：验证 LLM 模块在各种状态下的行为，包括缓存/成功/失败混合状态的颜色渲染、五种失败原因独立映射、Extended Thinking 标记、禁用优先原则、断网降级、全缓存无调用、三种输出格式（Excel/HTML/Summary）一致性。
  - **`scenario_datetime` — 日期/时间场景**：验证系统在不同市场时段（盘中/盘前/午休/盘后/非交易日/长假）、产品类型（场外基金/QDII/ETF/股票/混合）、边界条件（时段切换/缝隙/首次启动/断网）以及特殊日历（跨年/季末/汇率故障/调休/港股通假期）下的数据获取正确性和降级表现。
  - **`scenario_perf` — 性能基准场景**：以 mock 持仓与 mock API 跑 20 品种全量报告生成管线，记录各阶段耗时分布建立性能基线（basic 模式目标 <60s，>120s 判失败）。
  - **`scenario_security` — 安全基线场景**：5 项安全基线自动化验证——密钥文件权限不可公开读取、缓存文件不含明文密钥、匿名化模式报告不含真实名称/代码、LLM API 日志不记录完整密钥、HTML 报告不泄露文件系统路径。

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
- **非 live 用例的断网机制（2026-09-26 收紧）**：守卫只阻断**建连**（`socket.socket.connect`/`connect_ex`、`create_connection`、`getaddrinfo`），**不阻断 `socket.socket()` 构造**——否则会误伤第三方库的**导入期**探测（urllib3 导入期构造 socket 且仅被 `except Exception` 包住，硬化后会直接使库导入失败）。抛出的 `NetworkBlockedInTests` 继承 `BaseException`（而非 `RuntimeError`）：provider/fetcher 普遍用 `except Exception` 降级，用 `Exception` 子类会被静静吞掉，使漏 mock 退化成“验证网络被阻断后的降级”并白等链路瞬时重试退避（实测 unit 模式 1072 次未 mock 尝试 / 300 次退避睡眠 / 累计 149.3s 空等）。
- **不依赖外部数据的文件写 `offline_external_sources`**：报告/编排/集成类用例的**附带依赖**（交易日历/行业数据/行情/健康探针/akshare 直连路径）常在未被 mock 时被真实访问。这类文件在模块级加 `pytest.mark.usefixtures("offline_external_sources")`，由 `src/test/_network_guard.py::apply_offline_stubs` 把仓内 HTTP 出口（`httpx.Client`）、交易日历、akshare（`sys.modules` 级）换成“即时取不到”，并把 `fetcher.chain._TRANSIENT_RETRY_BACKOFF`（链路级）与 provider 级重试策略（腾讯/东方财富 K 线、财务指标多期）退避一并置 0（仓内既有测试惯例）——链路口径仍为“源不可用→降级”，但零网络、零等待。需要验证某源真实行为的用例**必须自行 mock**，不得用本 fixture 遮掩。
- **内容**：覆盖行情（A 股/ETF/场外基金/中美指数）、新闻源（东方财富/财联社/新浪/华尔街见闻）、基金（历史净值/排名/基准）、akshare 交易日历共 **14 个用例**（行情 5 / 新闻 4 / 基金 3 / 交易日历 2）。
- **断言原则**：只校验返回「结构」（字段存在、类型、非空），**不校验具体数值**，容忍真实行情波动（休市、涨跌、数据源改字段）。
- **不含 LLM 真实调用**（防费用）——LLM 连通性由运行时数据源健康检查覆盖。
- 触发方式：`.venv/bin/python scripts/test-runner.py --mode live` 或 `.venv/bin/python -m pytest --run-live -m live`。

##### 数据源真实响应录制与回放（cassette）

**要解决的问题**：数据源单元测试全部喂**手工构造的假响应**，测的是「我以为上游长什么样」。上游字段改名、值加前后缀、换分隔符、错误页返回 HTML 这类回归，**只有真实响应体测得出**。cassette 把上游真实响应体录进仓库，此后离线回放——既有真实数据，又不碰网络，且随默认套件入门禁。

| 组成 | 位置 |
|:-----|:-----|
| 回放引擎 | `src/python/core/cassette.py`（只依赖 stdlib + httpx + `core.http_client`） |
| 解析器绑定表 | `src/python/fetcher/cassette_checks.py`（cassette 名 → 当前解析器调用） |
| 已录制响应 | `src/test/data/cassettes/*.json`（git 跟踪） |
| 回放回归用例 | `src/test/unit/providers/test_cassette_replay.py` |
| 录制用例 | `src/test/live/test_live_cassette_record.py` |

**在用例里用已录制响应**——声明所需 cassette，运行期自动离线回放，用例内的 provider 调用照常写：

```python
pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]

@pytest.mark.cassette("tencent_quote", source="腾讯行情")
def test_tencent_quote_parses(self):
    data = tencent.fetch_price("600519")     # 响应来自 cassette，不联网
    assert data["price"] == pytest.approx(1285.13)
```

**刷新/新增录制**（显式联网动作，双开关缺一不可）：

```bash
# 录制全部登记的 cassette 并即时回放自检
.venv/bin/python scripts/test-runner.py --mode live --record-cassettes

# 只录一个
.venv/bin/python -m pytest -m live --run-live --record-cassettes \
    src/test/live/test_live_cassette_record.py -k tencent_quote
```

新增一个 cassette 需要三处同步：绑定表加一条解析器调用（`CASSETTE_CHECKS`）、录制用例加一个 `@pytest.mark.cassette(...)` 测试、回放回归用例加精确值断言。

**离线保证与非目标**：

- 回放**未命中即失败**（`CassetteMissError`），**绝不回落真实网络**——避免「以为在回放、实则在联网」。该异常刻意不继承 `httpx.HTTPError`，否则 provider 会把它当成网络错误降级到别的源，掩盖夹具缺失。
- 非 live 用例的真实请求已被 `conftest.py` 的 `_block_external_network` 拦死，**机制上不可能意外产生录制**。
- 录制产物进 git（每份几 KB ~ 百 KB），**不入门禁的 live 套件**；夹具刷新须走上面的显式开关。
- 维护入口：`cassettes`（列出）/ `cassettes --verify`（离线回放 + 交当前解析器解析，失败退出码 2），见下节「CLI 子命令」。
- 与「HTTP 客户端统一」约束的关系：回放寄生于「所有 HTTP 请求必须经 `core/http_client.py` 工厂」；绕过工厂自建客户端的 provider 不受回放替换，其用例会真实联网且静默通过。设计细节见 `technical.md` §2.6。

##### 全量（`all`）

- **`--mode verify,regression`** 组合模式，等价于分别运行 verify（单元） + regression（场景）。约 30s，作为发布门禁。
- **`--mode all`** 不设任何标记过滤（`.venv/bin/python -m pytest src/test/`），运行全量测试。需要全覆盖时手动调用。
- **`--mode all_no_unit`** 排除所有单元测试与联网测试（`-m "not unit and not live"`），仅保留场景测试、集成测试和跨类测试。适用于想要全场景覆盖但跳过纯模块逻辑验证的场景。

##### 多模式组合

`--mode` 支持逗号分隔同时运行多个模式：

```bash
# 同时运行场景测试和边缘测试
.venv/bin/python scripts/test-runner.py --mode scenario,edge
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
| `verify` | `unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web` | ~10s |
| `dev-verify` | `((unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts or unit_web or unit_report) and not (edge or data)) or scenario_basic`（单轮合一，原两阶段并集，收集数对拍一致） | ~20s |
| `all` | （无过滤，全量） | ~21s |
| `all_no_unit` | `not unit and not live` | ~10s |
| `report` | `unit_report` | ~11s |
| `scenario_extreme` | `scenario_extreme` | ~2s |
| `perf` | `scenario_perf` | 见 test-coverage.md |
| `security` | `scenario_security` | 见 test-coverage.md |
| `live` | `live`（需 `--run-live`） | — |

> 注：**Linux 开发机参考耗时**按 2026-08-05 实测（Linux x86_64，Intel i5-13500H，12 核 16 线程，46.8 GiB 内存；pytest-xdist worker=8 = medium 50% 核数）。耗时与硬件/操作系统/并行度强相关，不同机器上可能相差一个数量级，仅作相对量级参考；完整说明及不同环境下的耗时对照见 [test-coverage.md](test-coverage.md)（顶部注 + 「采集环境属性」/「各模式耗时对照」表）。若需本机实测，运行 `.venv/bin/python scripts/test-runner.py --mode bench --update-docs` 自动采集回填。

##### 跨机器耗时采集与环境耗时对照（`bench` + `--machine-info` / `--update-docs`）

耗时与**硬件配置、操作系统与并行度**强相关。跨机器复现耗时并回填对照表：

```bash
# 仅采集：顺序运行 14 个对照表模式（不含 live），打印环境属性表 + 各模式实测耗时表
.venv/bin/python scripts/test-runner.py --mode bench --machine-info

# 采集并自动更新 test-coverage.md「环境耗时对照」两张表
.venv/bin/python scripts/test-runner.py --mode bench --update-docs   # 隐含 --machine-info
```

- **`--mode bench`** 是 14 个对照表模式的聚合别名（`_MODE_TABLE_ORDER` 除 `live` 外全部），按对照表顺序运行；结果去重保序，非 bench 模式原样透传。
- **`--machine-info`** 采集 14 项环境属性（操作系统/系统版本/架构/主机名/CPU 型号/物理核数/逻辑线程/内存/磁盘类型/文件系统/Python 版本/并行级别/worker 数/采集日期，跨平台容错）并输出两张 Markdown 表格。
- **`--update-docs`** 在跑完后**自动写入** `test-coverage.md` 的两张表（按主机名匹配列：同机覆盖刷新日期、新机器追加列；历史参考列不受影响）。默认**永不写文档**，仅在显式传入该标志时更新；内容未变化则跳过写入（幂等）。
- **采集时机（不是提交门禁）**：`bench` 会**跑完全部 14 个模式**（全量套件多轮），耗时以分钟计。它**不进 P0/P1/P2 门禁**，也不必每次提交都重采——仅在两种时机采集：① **发布前**刷新 `test-coverage.md` 数据快照（见 CLAUDE.md「发布数据文档刷新」）；② 换机器 / 需本机耗时参考时。日常提交只需 P0 `dev-verify` + 守护脚本。
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

运行 `test-runner.py --mode verify,regression` 等全量测试后，直接从 HTML 报告中提取失败/错误用例的详细信息，无需手动翻浏览器：

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
.venv/bin/python scripts/test-runner.py --mode verify,regression

# 2. 快速查看哪些用例失败
.venv/bin/python scripts/extract-test-failures.py --summary

# 3. 查看失败详情（含错误堆栈最后 500 字符）
.venv/bin/python scripts/extract-test-failures.py

# 4. 修复后，只重跑之前失败的用例
.venv/bin/python -m pytest src/test/ -m "<对应标记>" --lf
```

> 脚本自动定位 `test-reports/latest/all/report.html` 等常用路径，无需每次指定路径。

### 定位顺序依赖失败 — `find-order-dependent-test.py`

当某个用例**单跑通过、与全套一起跑却失败**（典型：fixture / 模块级 patch 泄漏到后续用例，如日历注入与离线桩的装配栈序错误），手工二分需要 10+ 轮 pytest 往返。本脚本自动完成：单跑确认 → 收集参考顺序 → 复现门（前置合跑必须让目标失败，含无关失败即中止）→ 最小失败前缀二分 → 单文件配对确认（不成立则预算内精简）→ 输出污染源与最小复现命令。

```bash
# 默认在 src/test 收集顺序，对目标之前的全部文件做二分
.venv/bin/python scripts/find-order-dependent-test.py "src/test/unit/report/test_market_value.py::TestClass::test_name"

# 已知大概范围时限定候选（大幅提速，推荐）
.venv/bin/python scripts/find-order-dependent-test.py "<目标>" --candidates "src/test/unit/report/test_event_impact_wiring.py"

# 只做单跑确认与候选枚举（不执行二分）
.venv/bin/python scripts/find-order-dependent-test.py "<目标>" --dry-run
```

退出码：0 = 已定位；1 = 目标单跑即失败（非顺序依赖，请直接调试该用例）；2 = 无法复现/前置含无关失败/用法错误。前置条件：全套除目标外全绿；`--max-runs`（默认 40）限制 pytest 运行次数硬上限。定位后优先修**泄漏方**（fixture 栈序 / 未恢复的 patch），而非给受害用例加隔离。

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
- **真值单一来源**：断言中的「事实」必须从真值来源**动态派生**，禁止写死会随开发演进的派生量（需求/章节/开关/注册表/枚举的**条数**与**逐条清单**）。写死后新增一条需求/章节就会把测试打红（良性变更误判为回归），且与门禁脚本职责重复。
  - ✅ 结构关系断言：`set(a) == set(b)`（双向相等）、`expected <= set(a)`（覆盖）、`numbers == list(range(1, n+1))`（序号连续）、`len(keys) == len(set(keys))`（唯一性）、逐项遍历
  - ❌ 硬编码总数：`assert len(req_ids) == 276`、`assert len(sections) == 17`
  - 需要「条数」语义时用「域覆盖 + 序号连续」等价表达（强度不低于写死条数，且能发现跳号/重号）
  - 由此守：`scripts/check-test-redundancy.py` 第 5 类 `check_hardcoded_evolving_totals`
- 新增文件后运行 `.venv/bin/python scripts/check-test-markers.py` 验证标记合规性

### 新增测试指南

新增测试用例时，按以下流程操作：

**确定测试类型和文件位置**：

| 测试类型 | 放哪里 | 示例 |
|:---------|:-------|:-----|
| **模块单元测试** | 已有对应 `test_<module>.py` 追加 | `test_cache_io.py` 追加 `TestCacheEdgeCases` |
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

**加载 `scripts/` 下脚本（动态加载）**：

```python
from src.test._script_loader import load_script

mod = load_script("check-svg.py")                                            # 模块名由文件名派生
mod = load_script("_test_runner/modes.py", module_name="modes_under_test")   # 子路径 + 显式模块名
```

> 唯一实现为 `src/test/_script_loader.py`：按文件名/子路径加载 `scripts/` 下脚本、每次调用重新执行返回新实例、注册进 `sys.modules`（`@dataclass` 按 `cls.__module__` 回查命名空间依赖它）。**禁止**在测试文件里再手写 `importlib.util.spec_from_file_location` 样板或自定义 `_load_script`——`unit/scripts/test_script_loader.py` 的样板唯一性机检会检出（除 loader 自身外出现动态加载样板、或定义同名本地加载器均判失败）。

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
| 主程序单文件行数（`src/python/`） | > 500 行 | > 1000 行 | 按职责域下沉拆分（域下沉 + 门面 re-export，消费方导入面不变） |
| 脚本单文件行数（`scripts/` 递归含包内子模块） | > 400 行 | > 1000 行 | 按职责拆包（评测核心 / 阶段编排 / CLI 等），入口仅留 CLI 与原面 re-export |
| 测试单文件行数（`src/test/`） | > 800 行 | > 1200 行 | 考虑按被测函数 / 场景类型拆分 |
| 单文件测试数 | > 80 项 | > 120 项 | 拆分到子文件 `test_xxx_part1.py` / `test_xxx_part2.py` |
| 单类方法数 | > 15 项 | > 25 项 | 拆为多个 Test 类或拆分文件 |
| 单方法 mock 数 | > 5 个 patch | > 8 个 patch | 重构被测函数以降低耦合 |

> **门禁**：红线列由 `scripts/check-file-length.py --ci` 强制——**主程序 >1000 行**（硬上限，review-findings 文件过长登记区）、**脚本 >1000 行**与**测试 >1200 行**即 finding 退出 2；豁免路径须与 review-findings 挂账同步（拆分后自动提示移除豁免）。`-v` 另输出可选优化区间清单（主程序 >500 / 脚本 >400 / 测试 >800），review-findings「文件过长」登记表以该清单为派生源。

### 常见问题

**Q: 运行报错 `no tests collected`？**
A: 确认使用了正确的 marker 名：`.venv/bin/python -m pytest src/test/ -m "edge" --collect-only` 可预览匹配的测试。

**Q: 报告中文乱码？**
A: 确保操作系统编码为 UTF-8。Windows PowerShell：`chcp 65001`；Linux/Mac 默认即可。

**Q: 需要跳过 LLM 测试？**
A: 使用 `--mode edge` 仅跑边缘用例，或 `.venv/bin/python scripts/test-runner.py --mode scenario` 仅跑业务场景（不含 LLM 场景）。若要排除全部 LLM 相关（单元 + 场景），使用 `.venv/bin/python -m pytest src/test/ -m "not llm"`。注意 `--mode unit` **包含** `unit_llm`（均为 mock，无需 API key），不跳过 LLM。

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
| `test-runner.py` | 测试 | pytest 标记模式封装驱动，支持 17 种 `--mode` |
| `extract-test-failures.py` | 测试 | 从 pytest-html 报告提取失败用例详情 |
| `find-order-dependent-test.py` | 测试 | 单跑绿合跑红的顺序依赖污染源二分定位 |
| `check-code-traces.py` | 测试 | 代码注释/文档字符串中历史变更痕迹检查 |
| `check-doc-traces.py` | 测试 | 面向读者文档（.md）中历史变更痕迹检查 |
| `check-test-markers.py` | 测试 | AST 静态扫描验证测试标记合规性 |
| `check-task-numbering.py` | 测试 | 任务编号（plan-/rf-）全局一致性检查，防新增编号与历史归档冲突 |
| `check-task-numbering-hook.py` | 测试 | Claude Code PostToolUse hook——编辑编号管理文档后自动校验编号一致性 |
| `check-semantic-index.py` | 测试 | 功能语义命名表正反向一致性校验（功能开关注册表表外键 / 僵尸条目 / 合并章 key 缺失） |
| `check-doc-drift.py` | 测试 | 文档与实现一致性校验（章节表/章节数量、开关表/分组计数/默认值断言、配置与 LLM 默认值表、TUI 面板编号、目录树、项目统计表；`--sync` 自动回写统计快照） |
| `check-doc-links.py` | 测试 | 文档链接与结构一致性校验（死链/死锚点/重复标题/层级/编号序列/§引用） |
| `check-file-length.py` | 测试 | 单文件行数红线守护（主程序/脚本 >1000 行 / 测试 >1200 行；豁免登记与 review-findings 挂账同步，`-v` 输出可选优化区间清单供登记表派生） |
| `check-test-redundancy.py` | 测试 | 测试用例冗余与无效检查（死用例 / 无断言 / 完全重复 / 自证用例 / 硬编码演进总数） |
| `check-requirement-trace.py` | 测试 | 需求 ID ↔ 验证载体追溯（单段 ID 全域覆盖 / 载体文件存在 / ID 双向一致） |
| `install-claude-hook.py` | 测试 | 安装/卸载 Claude Code PostToolUse hook（任务编号一致性自动校验） |
| `llm-hallucination-sampler.py` | 测试 | 10 组标准持仓 × LLM 幻觉率采样（薄 CLI，实现在 `_halluc_sampler/` 包） |
| `calibrate-dedup-threshold.py` | 测试 | 新闻去重阈值校准分析 |
| `collect-test-coverage.py` | 测试 | 测试覆盖计数收集（`--collect-only` 快照，供 test-coverage.md 更新） |
| `smoke-web.py` | 测试 | Web 模式 HTTP 冒烟脚本（test_client 进程内全链路断言，可独立运行） |
| `check-version-consistency.py` | 质量 | 版本号全局一致性检查（P0/P2 守护脚本 + 发布流程必跑） |
| `check-style-guardrails.py` | 质量 | 设计护栏机检（DESIGN.md 护栏样式面；E 级：强调色越权/明暗同步/双面 token 对表判 finding，W 级：裸色值/圆角档位观察统计——**观察期**未入钩子与 CI） |
| `check-script-contract.py` | 质量 | scripts 顶层脚本契约机检（退出码声明 ⊆ {0,2} 白名单、check-* 统一 `add_common_args` CLI 面、文本 I/O 显式 encoding、脚本↔测试覆盖映射，四条规则——**观察期**未入钩子与 CI） |
| `release.py` | 发布 | 发布流程分步编排（check/prepare/refresh/evolution/gate/publish/devbump，每步独立可审阅、失败即停） |
| `perf-report.py` | 诊断 | 端到端报告生成管线性能基准（独立脚本，mock 外部数据源） |
| `perf-view.py` | 诊断 | 性能历史趋势查看（读取 perf_history.jsonl → 跨版本耗时对比） |
| `probe.py` | 诊断 | 探测统一入口（按 target 分发到 `probes/` 子模块；新探针实现契约面登记即用） |
| `probe-csi-factor-indices.py` / `probe-push2.py` | 诊断 | 旧入口兼容垫片（薄委托到 `probes/csi.py` / `probes/push2.py`，用法不变） |
| `check-svg.py` | 诊断 | README SVG 架构图检查（子命令 `geom` 几何 / `pixel` 像素 / `text-overflow` 文字色越界；像素子命令需 Pillow） |
| `_checklib.py` | 内部 | 检查脚本共享设施（统一 `-v/--ci` 契约与 `[OK]`/`[ERR]` 输出、`rel()`、`report()`、文档区间与表格解析） |
| `_test_runner/` | 内部 | 测试驱动内部实现包（paths / modes / pytest_env / machine_info / doc_writer / report_html / runner） |
| `launch.sh` / `launch.ps1` | 启动 | Linux/macOS / Windows 一键启动脚本（无参数启动 TUI；`web` 子命令启动 Web 浏览器模式） |
| `cli.sh` / `cli.ps1` | 启动 | Linux/macOS / Windows CLI 命令行包装（无参数默认生成报告） |
| `llm.sh` / `llm.ps1` | 启动 | Linux/macOS / Windows 完整报告快捷入口（固定 `report --type full`，等价 TUI「生成完整报告」） |
| `check-sources` | 诊断 | cli.py 子命令：数据源联通性检测 |
| `doctor` | 诊断 | cli.py 子命令：系统自检（环境/配置/目录/开关/适配/凭据/数据源七组，`--offline`/`--timeout`，不受实验开关约束） |
| `view-logs` | 诊断 | cli.py 子命令：查看结构化运行日志（`--level`/`--lines`/`--since`/`--until`，与 TUI `[V]` 同实现） |
| `whatif` | 诊断 | cli.py 子命令：调仓 What-if 模拟（对比两份持仓生成独立 diff 报告，见 [快速开始](../manuals/how-to-start.md)） |
| `cassettes` | 诊断 | cli.py 子命令：数据源记录-回放维护（列表 / `--verify` 离线回放校验，见下文「CLI 子命令」） |

### 测试类

**`test-runner.py` — 测试模式驱动**

pytest 的 `-m` 标记表达式封装层，按 `--mode` 选择预定义组合。所有 `--mode` 的详细说明见上文「测试模式详解」章节。

```bash
# 查看所有可用 mode
.venv/bin/python scripts/test-runner.py --help

# 日常提交前门禁（P0）
.venv/bin/python scripts/test-runner.py --mode dev-verify

# 合入门禁（P1）
.venv/bin/python scripts/test-runner.py --mode verify

# 发布门禁（P2）
.venv/bin/python scripts/test-runner.py --mode verify,regression

# 跨机器耗时采集 + 自动更新 test-coverage.md 环境耗时对照（含机器信息采集）
.venv/bin/python scripts/test-runner.py --mode bench --update-docs

# 带行覆盖率
.venv/bin/python scripts/test-runner.py --mode unit --coverage
```

**`extract-test-failures.py` — 失败用例提取**

见上文「快速定位失败用例」章节。

**`find-order-dependent-test.py` — 顺序依赖污染源二分**

见上文「定位顺序依赖失败」章节。

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

扫描项目根 `README.md` 与 `docs/managements/`、`docs/manuals/` 下所有 `.md` 文件（豁免 `changelog.md` / `review-findings.md` / `plan.md` 及 `archive/`、`plan/`、`tmp/` 目录），检查面向读者的文档正文是否含有历史变更信息（来源叙述、历史实现、迁移痕迹、任务编号、归档文件引用、版本号、Iter 迭代标记等）。此类文档只应描述"当前是什么/做什么"，不应记录"从哪里来、怎么变的"；历史记录集中在管理文档（changelog / review-findings / plan）中。

两条核心规则：
1. **正文不得带历史痕迹**：文档正文不得包含历史变更信息（来源叙述、原/旧实现、迁移/重命名、任务编号、版本号、Iter 迭代标记等），只反映"当前是什么/做什么"。例外：`changelog.md` / `plan.md` / `review-findings.md`（历史/计划记录性质）
2. **正文不得引用归档文件**：除上述三个例外文档外，其他管理文档与用户文档正文不得引用 `docs/archive/` 下目录或 `archived_*.md`。例外：`folders.md` 的目录树（`│ ├ └` 行）与统计表行可引用 archive 目录及文件名——目录树记录项目结构，archive/ 条目是结构的一部分

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

1. **正向**：功能开关注册表中 `GROUP_REPORT` 分组的每个键（报告章节与增强开关）必须已登记在「功能语义命名表」中（防新增开关绕过登记）
2. **反向**：表中每个语义 slug 在 `src/python/` 下至少一处非注释代码引用（防僵尸条目——功能删除后表行残留）
3. **合并章**：表下「合并章代码标识符」注声明的 sheet key 必须存在于 `core/registry.py` 的 `_REPORT_SECTION_DEFAULT` 注册表

```bash
.venv/bin/python scripts/check-semantic-index.py       # 检查全部
.venv/bin/python scripts/check-semantic-index.py -v    # 详细输出（打印每项解析结果）
.venv/bin/python scripts/check-semantic-index.py --ci  # CI 模式（只输出错误，退出码 2）
```

**检查脚本的共享设施与统一契约（`_checklib.py` / `_traces_code/` / `_test_runner/`）**

`scripts/` 下的检查脚本共用一套 CLI 契约与设施，避免每个脚本各写一份：

- **统一契约**（`_checklib.add_common_args()` / `report()`）：`-v/--verbose` 详细输出、`--ci` 仅输出 `文件:描述`；**通过退出 0，发现 finding 退出 2**（`check-code-traces.py` 另有 HIGH=1 / LOW=3 的分级语义，属其自身约定）；通过打印 `[OK] …`，失败逐条 `[ERR] file:desc`（`--ci` 下为裸行）+ 汇总行
- **共享原语**：`REPO_ROOT` / `rel()`（仓库相对路径，非仓库内路径原样返回）、`extract_region()` / `replace_region()`（标记区间）、`extract_table_region()` / `replace_table_region()`（表区域，带结构校验）
- **`_traces_code/`**：check-code-traces 内部实现包——`exemptions.py`（「章节计数豁免」与「迭代轮次豁免」，check-doc-traces 同共用）、`patterns.py`（模式表与行级豁免）、`extract.py`（注释/标识符抽取）、`scan.py`（扫描调度）、`layers.py`（core 反向依赖守卫）、`config.py`（扫描域配置）；check-code-traces.py 只留 CLI 与原面 re-export
- **`_test_runner/`**：`test-runner.py` 的内部实现包（paths / modes / pytest_env / machine_info / doc_writer / report_html / runner），入口仅保留 CLI 与主流程并原面 re-export —— 既有测试访问 `test_runner._env_value` 等名字仍有效；**注意**：monkeypatch 内部状态（如 `_LATEST_DIR` / `_DOC_COVERAGE_PATH`）须指向持有它的子模块（`_test_runner.report_html` / `_test_runner.doc_writer`）

> 新增检查脚本时直接复用 `_checklib`，不要自建 argparse/输出/退出样板；新增共享模式放 `_traces_code/exemptions.py`。

**`check-doc-drift.py` — 文档与实现一致性检查**

把文档里的「事实断言」（计数、清单、默认值、面板编号、目录树、统计表）与权威源逐条对账，
使漂移在提交前暴露。与 `check-doc-traces.py` 互补：那边管「不该写的内容」（历史痕迹），这边管
「写了但与实现不符的内容」。

十六项检查（权威源 → 受检文档）：

1. 报告章节表（`reports-instruction.md`）↔ 章节注册表 `_REPORT_SECTION_DEFAULT`（行数/序号/名称）
2. 章节数量断言（`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`）↔ 注册表章节数
3. 功能开关表（`how-to-config.md` 三组区段）↔ `feature_switch_registry`（成员/默认值/无表外键）
4. 开关分组计数断言（`⚗实验 A / 常规 B / 报告章节与增强 C`、`实验组（N 项`、`共 N 项开关`）↔ 分组计数
5. 开关默认值断言（`` `flag` `` 后紧随「默认开/关」）↔ 注册表默认值
6. 配置标量默认值表（`how-to-config.md`）↔ `_DEFAULT_CONFIG`
7. LLM 默认参数表（`llm-technical.md`）↔ `_DEFAULT_LLM_SETTINGS` + 缓存 TTL 注册表
8. TUI `[S]` 面板编号连续性与分组边界（`how-to-use-tui-menu.md`）↔ `handlers_config.py` 的派生编号规则
9. 目录树（`folders.md`）↔ 文件系统实测（`src/`、`scripts/`、`docs/{managements,manuals,plan}`）
10. 项目统计表（`folders.md`）↔ 实测文件数/行数（加 `--with-test-count` 再核「测试用例」行）
11. 测试覆盖计数表（`test-coverage.md`）↔ `scripts/collect-test-coverage.py` 快照（仅 `--with-test-count`）
12. 归档索引完整性：changelog / plan / review-findings 三份管理文档的「归档」索引 ↔ 归档目录下
    `archived_*` 文件**双向**比对（漏列 → 「缺少」；幽灵引用 → 「不存在」）
13. 管理文档分区纪律：review-findings 未完成/已解决分区互斥且已解决项须在 changelog 有修复记录；
    plan 未完成区不得含 ✅/已归档项；现行 changelog 只允许一个 `-dev` 段头
14. Extended Thinking 支持矩阵：手册对比表须覆盖代码支持的全部厂商族、「仅」式预算枚举句须列全、
    默认开思考族须有提示（权威源为 `llm/api_base.py` 的前缀名单）
15. Provider Chain 降级表：`fetcher/chain_config.py::_DEFAULT_CHAINS` 的 15 条链 ↔
    `datasource-reliability.md` §4.2 表逐链**双向**比对（漏链 → 「缺少链路」；幽灵行 → 「无此链」）
16. 守护清单同源：developer-guide 的 P0/P2 门禁代码块、`ci.yml` guards steps、CLAUDE.md P0/P2 条款、
    testplan P0/P2 清单行与 `.githooks/pre-commit` 执行体，五处的 `scripts/check-*.py --ci` 引用集合两两一致（新增守护脚本漏改任一处即报）

```bash
.venv/bin/python scripts/check-doc-drift.py                   # 十六项全查
.venv/bin/python scripts/check-doc-drift.py -v                # 详细输出（打印解析结果与实测统计）
.venv/bin/python scripts/check-doc-drift.py --ci              # CI 模式（只输出 文件:描述，退出码 2）
.venv/bin/python scripts/check-doc-drift.py --with-test-count # 附带 pytest 收集，核对「测试用例」与 test-coverage.md 计数表
.venv/bin/python scripts/check-doc-drift.py --sync             # 统计快照自动同步（实测数字回写 folders.md 并 git add，幂等）
```

> **统计快照漂移的自动化治理**：第 10 项「项目统计表」的数字（文件数/行数/用例数）是随日常
> 提交高频变化的派生量（changelog 每补一行、用例每增删即变），人工同步必漏，曾是 CI 最高频红源。
> `--sync` 把实测值自动回写 `folders.md` 对应单元格（只改数字、保留千分位/粗体风格与说明文字，
> 不触碰版本演进对照表），并把回写结果 `git add` 加入暂存区；git pre-commit 钩子在提交涉及
> `docs/managements/` 或 `src/test/` 时自动调用（见「install-hooks.sh」条）。其余类目
> （清单/默认值/目录树/归档索引）的漂移仍需人工按提示修正。

> 按设计豁免的文档：`changelog.md` / `review-findings.md`（如实引用旧数字作为变更记录）与
> 版本快照类文档（历次发布的归档快照）不参与计数与默认值断言扫描。修正提示：报告里的数字就是
> 实测值，直接按提示改文档即可；目录树缺条目时按所属子包位置补一行（含简短职责说明）。

**`check-test-redundancy.py` — 测试用例冗余与无效检查**

静态分析 `src/test/`（默认跳过 `pytest.ini` 刻意排除的 `live/` 真网套件），抓五类「看着有测试其实没测住」的问题：

1. **死用例**：同文件同类同名重复定义（后者覆盖前者）、类名不以 `Test` 开头的方法形式 `test_*`、`Test*` 类定义了 `__init__`（pytest 整类跳过）
2. **无断言用例**：既无 `assert`、也无 `pytest.raises/warns/fail`、也无 `assertEqual` 等 `assert*` / `assert_called*`，且不经同类辅助方法（如 `self._assert_pairs_contain(...)`，其内部含断言）——断言落在辅助方法里同样算数
3. **完全重复用例**：去 docstring 后「函数体 + 参数 + 装饰器」AST 归一化一致（同一被测对象同一断言）。凡函数体内出现**无法解析**的 `self.<attr>` 间接调用（目标来自 `setUp` / 跨模块基类）一律跳过比对——避免把「同名方法绑定不同被测对象」的并行覆盖误判为重复
4. **自证用例**：同一用例内既 `@patch("<mod>.<fn>")` 又直接调用同名函数，且把该 mock 的 `.return_value` 设成某字面量、再用断言与该字面量比较（断言恒真，等于没测）
5. **硬编码「会演进的总数」**：把**可增长集合的条数**写死进断言（如 `assert len(req_ids) == 276`、`assert len(sections) == 17`）。
   这类总数是文档真值来源的派生量，**新增一条需求/章节/开关就会把测试打红**——良性变更被误判为回归，而它捕捉不到任何真实缺陷；且与门禁脚本（如 `check-requirement-trace` 的全域覆盖断言）**职责重复**。
   正确写法是断言**结构关系**：集合双向相等（`set(a) == set(b)`）、子集/覆盖（`expected <= set(a)`）、序号连续（`numbers == list(range(1, n+1))`）、唯一性（`len(keys) == len(set(keys))`）。
   判定保守（宁少报不误报）：仅看 `assert` 中的 `len(x) ==/> 数字`；实参名需含语义关键词（`requirement`/`section`/`switch`/`module`/`domain`/…）**或**文件路径含 `requirement`/`registry`；忽略 `<= 3` 的小数字（常为有意断言）。

```bash
.venv/bin/python scripts/check-test-redundancy.py                 # 五类全查
.venv/bin/python scripts/check-test-redundancy.py -v              # 详细输出（扫描规模 + 各类计数 + 跳过的间接调用用例数）
.venv/bin/python scripts/check-test-redundancy.py --ci            # CI 模式（只输出 文件:描述，退出码 2）
.venv/bin/python scripts/check-test-redundancy.py --include-live  # 连带扫描 src/test/live/
```

> 删除/合并用例后须同步刷新 `test-coverage.md`（模式/子标记计数）与 `folders.md`（测试文件数/行数/用例数），
> 两处由 `check-doc-drift.py --with-test-count` 兜底核对。**修法优先级**：名实不符的用例应改成真正跑它名字
> 声称的场景（补上原本空白的覆盖），而不是改名了事。

**`check-requirement-trace.py` — 需求 ID ↔ 验证载体追溯**

校验 `requirements.md` 的需求 ID 与 `testplan.md` §2.1 追溯表的双向一致：映射表格式齐备、ID 均存在于需求侧、ID 唯一、**已补全域全覆盖**（`_COVERED_DOMAINS` 中每个域的全部 ID 均有载体行）、载体文件真实存在于磁盘。

```bash
.venv/bin/python scripts/check-requirement-trace.py                 # 全量校验
.venv/bin/python scripts/check-requirement-trace.py -v              # 详细输出（逐域覆盖进度）
.venv/bin/python scripts/check-requirement-trace.py --ci            # CI 模式（只输出 文件:描述，退出码 2）
```

> 覆盖口径：仅识别 `R-<域>-<序号>` 形式的**单段**需求 ID；`requirements.md` §7.2–§7.8.4 的双段子域 ID（如 `R-LLM-GM-01`）
> 不在本脚本与追溯表范围内。

**`check-doc-links.py` — 文档链接与结构一致性检查**

校验当前文档集（`README.md` / `CLAUDE.md` / 管理 / 手册 / 计划；归档快照按设计豁免）六类问题：死文件链接、死锚点（GitHub slug 规则 + `<a id>` 显式锚点，行内代码等长遮罩、代码围栏跳过）、重复标题（锚点歧义）、标题层级跳变、编号序列跳变（数字按层级+父前缀分组，中文数字按层级分组）、`xxx.md §N` 跨文档章节引用失配（归属取同一行 § 前最近的 `.md` 记号；无文件名且文档使用编号章节时自归属）。

```bash
.venv/bin/python scripts/check-doc-links.py                          # 全量校验
.venv/bin/python scripts/check-doc-links.py -v                       # 详细输出（打印扫描文档清单）
.venv/bin/python scripts/check-doc-links.py --ci                     # CI 模式（只输出 文件:行:描述，退出码 2）
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

`.githooks/` 的 git pre-commit hook（10 个守护脚本全量校验 + 统计快照自动同步）默认**休眠**——`core.hooksPath` 是本机 git 配置、不随仓库同步。clone 后运行一次激活：

```bash
sh .githooks/install-hooks.sh          # 启用（写入本机 core.hooksPath）
sh .githooks/install-hooks.sh --off   # 停用
```

与 `install-claude-hook.py`（Claude Code hook）配套；两条 hook 均调用 `check-task-numbering-hook.py` 校验编号文档。

**`llm-hallucination-sampler.py` — LLM 幻觉率采样**

见下文「LLM 幻觉率采样测试」章节。

**`calibrate-dedup-threshold.py` — 新闻去重阈值校准**

新闻标题去重（同源/跨源安全区分级 + 候选区阶梯 + 方向对立防护，阈值见 `news_dedup.py` 校准常量）在每次报告运行时自动记录"边界案例"到 `data/cache/dedup_anchors.jsonl`。积累足够锚点后，用此脚本分析当前阈值是否合理。

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

只做 `.venv/bin/python -m pytest --collect-only`（收集测试项，**不执行测试**，耗时约 2s），模式计数谓词由 `_test_runner/modes.py::MODES` 的 marker 表达式现场编译，输出各模式 / unit 子标记 / scenario 分组 / 跨类标记 / 功能域 / 文件分布的项数，供 `docs/managements/test-coverage.md` 快照更新使用。

```bash
.venv/bin/python scripts/collect-test-coverage.py
```

**说明**：
- 只收集不执行——测试体不会运行，不影响测试结果，也不会触发真实数据源 / LLM 调用
- 项数随版本迭代变化，属撰写时快照，精确计数以本脚本实时输出为准
- 计数口径直接取自 `MODES` 的 marker 表达式（复用 pytest 自身的 `-m` 求值器，`verify` / `dev-verify` 等组合模式与阶段 marker 回落同源），表达式只在 `modes.py` 定义一处、模式增删自动跟随；`all`（已由「总收集: N」表达）与 `live`（默认收集宇宙排除，计数恒 0）为显式豁免并在脚本内注记理由

### 质量类

**`check-version-consistency.py` — 版本号一致性检查**

发布版本前必须运行。检查 `APP_VERSION`（`src/python/core/constants.py`）与以下文件的版本号是否一致：

- `pyproject.toml`（`version` 字段，`--fix` 可自动同步）
- `README.md`
- 管理文档 10 份：`plan.md`、`technical.md`、`requirements.md`、`testplan.md`、`review-findings.md`、`llm-technical.md`、`folders.md`、`test-coverage.md`、`changelog.md`、`developer-guide.md`
- `folders.md` 另含一条 `evolution_head` 断言：版本演进对照表「当前开发版（」列头版本号与 `APP_VERSION` 同步（与文档版本头双点校验，发版漏改即报错，`--fix` 可自动同步）；断言只锚列头文本，表内统计数据行的刷新义务在「版本发布流程 ② 发布数据文档刷新」

```bash
# 无参数运行，逐项检查并报 [OK]/[ERR]
.venv/bin/python scripts/check-version-consistency.py
```

全部 `[OK]` 方可提交。如有 `[ERR]`，按提示逐个同步，然后重跑直到全部通过。版本切换工作流见下文「版本发布流程」章节。

### 发布类

**`release.py` — 发布流程分步编排**

把「版本发布流程」固化为可执行子命令，每步独立可审阅、失败即停不连锁：

```bash
.venv/bin/python scripts/release.py check     # 预检：分支/工作树/版本形态/tag/版本一致性
.venv/bin/python scripts/release.py prepare   # 版本全链 + changelog 发布段归档 + 一致性 --fix
.venv/bin/python scripts/release.py refresh   # bench --update-docs + collect + doc-drift --sync
.venv/bin/python scripts/release.py evolution --release   # 演进对照快照（默认只滚当前开发版列）
.venv/bin/python scripts/release.py gate      # P2：regression + 十守护 --ci
.venv/bin/python scripts/release.py publish --title "<发布主题>"   # release 提交 + P1 verify + --no-ff 合并 + tag
.venv/bin/python scripts/release.py devbump    # 切下一开发版并提交
```

`publish` / `devbump` 默认不推送（只打印推送命令），`--push` 才执行；rf 归档迁移保留人工（需判断归档段语义）。

### 诊断类

**`perf-report.py` — 端到端性能基准**

生成 20+ 品种 + 3 年模拟持仓，运行 basic/both 报告生成管线，测量各阶段耗时。

```bash
.venv/bin/python scripts/perf-report.py
```

**输出**：`docs/tmp/better-investment-performance-test-report.md`

**目标**：basic 模式总耗时 < 60s

**`perf-view.py` — 性能历史趋势查看**

读取 `data/state/perf_history.jsonl`（由 `PerfCollector` 在每次报告生成时自动追加），按版本和报告类型分组统计，输出版本间性能趋势对比。

```bash
# 输出全部历史趋势到 stdout
.venv/bin/python scripts/perf-view.py

# 仅看 full 类型报告的性能趋势
.venv/bin/python scripts/perf-view.py --report-type full

# 仅看最近 30 条记录
.venv/bin/python scripts/perf-view.py --last 30

# 同时写入 docs/tmp/perf_trend.md
.venv/bin/python scripts/perf-view.py --save
```

**输出列说明**：

| 列 | 含义 |
|:---|:------|
| 阶段 | 报告生成管线阶段名称（行情获取/快照对比/历史走势/HTML 生成/Excel 生成 等） |
| 平均耗时 | 该阶段历史平均耗时 |
| 最短/最长 | 该阶段历史最小/最大耗时 |
| 次数 | 该阶段出现次数（条件阶段如历史走势仅在启用时出现） |

**数据来源**：每次 `generate_report()` 调用时自动记录到 `data/state/perf_history.jsonl`，无需手动触发；中断运行以 `status=interrupted` 记录（含 `interrupted_stage`），与成功完成（`completed`）区分，页头状态行据显「已中断」。

**`probe.py` — 探测统一入口（target 分发 registry）**

所有连通性/可用性探测统一走 `scripts/probe.py <target> [options…]`：target 实现在 `scripts/probes/<语义名>.py`（声明 `PROBE_TARGET` / `build_parser()` / `run(args)` 契约面并在 `probes/__init__.py` 登记），**全部纯只读**（不写缓存/熔断/降级记录，无副作用）；新探针只需新增子模块并登记，入口无需改动。现有 target：

- `csi` — CSI 风格指数可用性探测（因子暴露分析已实施，现为**周期性复核**工具：新机器/新窗口验证指数链路与停更预警，条数+新鲜度双维度判定）
- `push2` — 东方财富 push2 连通性诊断（见下）

旧入口 `probe-csi-factor-indices.py` / `probe-push2.py` 保留为薄委托垫片，命令用法不变。

**`csi` target — CSI 风格指数可用性**：判定全量 5 因子 / MVP 3 因子 / 不可行；建议数据回归前置运行一次。

```bash
.venv/bin/python scripts/probe.py csi --days 365
```

**`probe-push2.py` — 东方财富 push2 连通性诊断**

东方财富 push2 连通性探测，用于区分「程序缺陷」与「网络环境拦截」。部分电脑运行报告时 push2 频繁出现 `Server disconnected without sending a response`（服务器接受 TCP 连接但未返回响应即断开），触发熔断退避（60s→300s→900s→3600s）后降级到备用链路——用此脚本可快速定位根因，决定是否需要调整代码或加速降级。

```bash
.venv/bin/python scripts/probe.py push2     # 默认探测 3 次（旧命令 probe-push2.py 等效）
```

判读：
- **三次全部成功** → 网络正常，之前失败为临时抖动/时段性，无需改动
- **三次全失败、且 curl 对照也失败** → 网络/防火墙/代理拦截 push2，属环境问题（curl_cffi 指纹大概率无效，可考虑加速降级）
- **脚本失败、curl 对照成功** → httpx/TLS 指纹被 WAF 拦截，curl_cffi 浏览器指纹方案才有价值

curl 对照命令：`curl -s "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f58"`。纯只读探测，不写缓存/熔断/降级记录，无副作用。

**`check-svg.py` — README SVG 架构图检查（三合一）**

README 首屏架构图（`src/static/architecture.svg` / `llm-chain.svg` / `capabilities.svg`）的渲染质量检查，改图后用于验证文本不越界/重叠。三个渲染质量检查（几何/像素越界/文字色越界）合并为一个带子命令的统一入口（注意：**均带 `--ci` 与退出码语义**，0=通过 / 1=缺 Pillow / 2=发现越界）。

```bash
# 几何审查：文本越界 / 贴边 / 文本重叠（估算字体宽度；矩形底部不齐仅作提示，不计入退出码）
.venv/bin/python scripts/check-svg.py geom <svg路径…>

# 像素审查：副标题行区域亮色像素是否越出卡片右缘（需 Pillow）
.venv/bin/python scripts/check-svg.py pixel <png> <scale> <card_r> <row_y0> <row_y1> <margin>

# 像素审查：精确匹配文字色像素越界（需 Pillow）
.venv/bin/python scripts/check-svg.py text-overflow <png> <scale> <card_r> <y0> <y1> <margin>
```

参数含义：`scale` = px per svg unit；`card_r` = 卡片右缘 x（svg 单位）；`row_y*/y*` = 检测区 y 范围（svg 单位）；`margin` = 检测范围到卡片右缘的右扩量（svg 单位）。几何审查纯标准库；两个像素子命令需 Pillow（`pip install -e '.[svg]'`，缺失时给出可读指引并以退出码 1 结束）。

> **当前状态**：三张 SVG 均通过 `geom`——卡片内文本按估宽模型的右余量 ≥10px（`capabilities.svg` ≥19px）。贴边阈值由 `_PADDING_WARN`（6px）定义，矩形底部不齐仅作提示项（流程图同列卡片高度本就允许不同）。**改图后请重跑本脚本**；本脚本不在提交前/发布前门禁清单内，按需运行。

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

> 注意：包装脚本的「无参数默认 both」与 CLI 本身的 `--type` 默认值（basic，仅 Excel）不同——直接直调 `.venv/bin/python -m src.python.cli report`（不带 `--type`）仍走 basic 轻量模式（只生成核心页签，新闻/历史/LLM 等页签为降级占位）。包装脚本无参数时自动补 `report --type both`，确保拿到完整非 LLM 报告。

包装脚本相比直调的好处：自动切换到项目根目录、自动定位虚拟环境解释器（避免误用系统 python 缺失 pandas 等依赖）、无参数时自动补 `report` 子命令。CLI 完整参数说明见 [快速开始](../manuals/how-to-start.md) 的「CLI 命令行模式」一节。

**`llm.sh` / `llm.ps1` — 完整报告快捷入口**

只做一件事：生成含 LLM 分析章节的完整报告，等价于 TUI 菜单的「生成完整报告(Excel+HTML) [含LLM，按章节配置]」。
子命令与报告类型写死在脚本里，免去每次敲 `report --type full`。

```bash
./scripts/llm.sh                  # 生成完整报告（含 LLM）
./scripts/llm.sh --force-llm      # 强制重新调用 LLM，跳过缓存
./scripts/llm.sh --history off    # 本次不获取组合历史走势
```

```powershell
.\scripts\llm.ps1 --force-llm
```

追加的参数即 `report` 的报告级参数（`--type` / `--history` / `--force-llm`）；组合历史走势不写死，
由配置 `history.fetch_mode` 决定（与 TUI 菜单一致）。需要全局参数（`--config` / `--output` /
`--experiment` / `--feature`）时仍走 `cli.sh` / `cli.ps1`——它们必须写在 `report` 子命令之前。

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

**`cassettes` — 数据源记录-回放维护**

维护已录制的真实数据源响应（见上文「数据源真实响应录制与回放（cassette）」）。与 `doctor` 同例：**无需配置、不受任何实验开关约束、不发起网络请求**。

```bash
# 列出已录制响应（来源/录制时间/交互数/大小）
.venv/bin/python -m src.python.cli cassettes

# 逐条离线回放并交给当前解析器解析（不联网）
.venv/bin/python -m src.python.cli cassettes --verify
```

**`--verify` 输出标记**：`[OK]` 解析正常；`[!]` 该 cassette 未登记解析器（只校验文件可读，不伪造成 OK）；`[ERR]` 解析器吃不下已录制的真实响应体——**上游格式可能已变，需重新录制**。

**退出码**：0=正常（含列表模式与全部 `[OK]`/`[!]`），2=有录制的解析路径失败。

**`doctor` — 系统自检**

一次性盘点「跑不起来」的常见根因，分环境/配置/目录/功能开关/数据源适配/数据源凭据/数据源七组，失败项附可执行修复建议。与 `check-sources` 的分工：后者只测数据源联通性，前者还覆盖解释器/虚拟环境、配置可解析与关键字段、目录可读写。

```bash
# 完整自检（含数据源网络检查）
.venv/bin/python -m src.python.cli doctor

# 仅查本地环境/配置/目录，跳过网络（瞬时返回）
.venv/bin/python -m src.python.cli doctor --offline

# 收紧网络检查的整体耗时预算（秒，默认 8）
.venv/bin/python -m src.python.cli doctor --timeout 5
```

**无需配置**：与 `view-logs` / `cassettes` 同例，在 `init_config()` **之前**分派——配置损坏正是自检要定位的场景，若被配置初始化拦住即成死锁。

**不受开关约束**：TUI 菜单 `[T]` 与 Web 自检卡片由 `doctor_check` 门控（该开关默认开启），但 CLI 子命令始终可用（同理，被开关拦住就失去了诊断手段）。

**退出码**：0=全部通过，1=有失败项（`_EXIT_PARTIAL`）。自检有失败项不算命令本身失败——命令跑完了并给出了结论，故用 PARTIAL 而非 SEVERE。

**`view-logs` — 查看结构化运行日志**

按级别/时间过滤读取日志尾部，**无需配置**（配置损坏时仍可查看日志诊断）。

```bash
# 查看最近日志（默认读末尾 5000 物理行）
.venv/bin/python -m src.python.cli view-logs

# 只看 ERROR + CRITICAL
.venv/bin/python -m src.python.cli view-logs --level ERROR

# 只看指定日期之后 / 只读末尾 200 行
.venv/bin/python -m src.python.cli view-logs --since 2026-08-16
.venv/bin/python -m src.python.cli view-logs --lines 200
```

级别/时间过滤与尾部读取逻辑全部委托 `core/log_reader.read_log()`（与 TUI 菜单 `[V]` 同一实现）。

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
.venv/bin/python scripts/llm-hallucination-sampler.py

# 仅测试特定模块（默认 expert_review）
.venv/bin/python scripts/llm-hallucination-sampler.py --module health_check

# 仅测试特定数据集（1-indexed）
.venv/bin/python scripts/llm-hallucination-sampler.py --dataset 1,3,5

# 跳过 API 调用，只构建 prompt 验证结构
.venv/bin/python scripts/llm-hallucination-sampler.py --dry-run

# 跳过缓存强制重新生成
.venv/bin/python scripts/llm-hallucination-sampler.py --force
```

**输出**：
- 报告文件：`docs/tmp/hallucination-report.md`
- Dry-run prompt 转储：`docs/tmp/hallucination-prompts-{module}.md`

**注意**：事实校验器对仓位占比百分比和情景假设百分比设跳过策略（`_POSITION_WEIGHT_KEYWORDS` / `_HYPOTHETICAL_KEYWORDS`），避免将百分比陈述误报为幻觉。最终幻觉率以 `docs/tmp/hallucination-report.md` 为准。

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
- `get_report_section_number("position_structure")` → 当前配置下该模块的序号（被基金深度分析各页签写入器调用）
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
| ④ | **注册调度入口** | `llm/_llm_dispatch.py` + `llm/generators_orchestrator.py` + `llm/module_fingerprint.py` | 在 `_llm_dispatch._build_module_fns()` 返回的 `_MODULE_FNS` 字典中添加新模块条目（键=settings_suffix，值=lambda 调用新函数）；在 orchestrator 的 `_compute_module_cache_info()` 中添加对应的 `info` 条目。**指纹不进 orchestrator**：在 `module_fingerprint.py` 的 `MODULE_FINGERPRINT_BUILDERS` 登记该模块的构造器（输入闭包 `ModuleFingerprintInputs`），预检侧按键取指纹、写侧闭包调用同一函数——两侧都不得自行拼接指纹片段 |
| ⑤ | **添加报告页签** | `report/llm_content.py` | 在 `write_llm_sheets()` 的 `_module_keys` 和 `_module_contents` 列表中添加新模块键名 |
| ⑥ | **暴露导出接口** | `llm/__init__.py` | 将新生成函数加入 `__all__` |
| ⑦ | **运行注册表测试** | 终端 | `.venv/bin/python -m pytest src/test/unit/core/test_registry.py -v` — 验证 TTL/前缀/键名完整性 |
| ⑧ | **验证标记合规** | 终端 | `.venv/bin/python scripts/check-test-markers.py` — 确认测试文件标记无遗漏 |

> **LLM 模块补充步骤**：在上述 registry 清单基础上，新增 LLM 模块还需完成领域特定步骤——`llm/prompts.py` 新增 `_SYSTEM_{MODULE}` 常量与提示词构建函数；`report/html_writer.py`（HTML）+ `report/llm_content.py`（Excel）新章节双渲染；`config.json` → `cache_ttl` 添加 `llm_{module}` 条目；`llm_settings.json` 加入推荐默认值并更新 [配置指南](../manuals/how-to-config.md)。
>
> **纳入模块级质量分级（可选，开关 `module_quality_gate`）**：新模块默认不参与 `report/llm_quality.py` 的 A~F 分级（分级为只读旁路，未登记不影响任何既有功能）。若需纳入：在 `_MODULE_KEYS` 追加模块键（顺序须与 `llm_content` 四元组位置一致）、在 `_LENGTH_THRESHOLDS` 设定该模块的 `(降级下限, 参考篇幅)` 双阈值（依据真实健康输出实测字符数标定）；若其提示词规定了固定章节清单，还需在 `_REQUIRED_MARKERS` 登记标记——`test_llm_quality.py::TestRequiredMarkersMatchPrompts` 会直接比对提示词常量，标记与提示词不同步即测试失败。

> **提示词内容必须进指纹（唯一事实来源 `llm/module_fingerprint.py`）**：缓存键与提示词内容脱钩会静默复用陈旧结论（键不变 → 预检命中旧键 → 不重生成、不报错）。因此**凡进了提示词的段落都必须进该模块的指纹**：已渲染文本（`competitive_context` / `data_quality_text`）、量化指标（`metrics`）、以及 `pipeline_data` 派生的【环比变化】【数据质量降级】两段——**只进「提示词确实含该段」的模块**，不进提示词的模块并入即纯成本失效。判据与完整清单见 `llm-technical.md` §7.1。
>
> **开关改变提示词 → 同一后缀函数供两侧调用**：凡开关**会改变提示词内容**（`deterministic_signal` 注入信号块与确定性信号摘要、`decision_header_parse` 追加决策头契约、辩论增强后缀），其开关判定必须**收敛在后缀函数内部**，由 `module_fingerprint.py` 的构造器统一调用——写侧与预检侧只调用同一构造函数，不得任一环节自行拼接（自行拼接的后果是两侧结果永久不等：写侧照常写入、预检侧永不命中，表现为「开关看似生效但每次仍全量调用 LLM」）。后缀函数关闭时返回 `""`（键不变、不误伤既有缓存），开启时返回稳定短串（如 `"_dh"`）。**内容指纹型**后缀（如 `decision_ledger.lessons_cache_suffix`、`prompts_signals._signal_digest_cache_suffix`、`signal_ledger.summary_cache_suffix`）另取块内容 md5 作版本，使数值变化即换键。

> **追加型状态文件一律走共享原语 `core/jsonl_store.py`**：`perf`（性能历史）、`decision_ledger`（决策账本）、`signal_ledger`（信号账本）三者的「读全文 → 拼接 → 写临时文件 → `os.replace`」逻辑已抽为 `append_jsonl_atomic()` / `read_jsonl()`，**新增任何 JSONL 持久化都不得再抄一份**——各自只保留自己的序列化口径（如 `decision_ledger` 的 `sort_keys=True` + `ensure_ascii=False`）与 `prefix`/日志标签，行为逐字不变由 `test_jsonl_store.py::TestDelegationPreservesBehaviour` 锁定。新增持久化文件时**必须**在 `src/test/conftest.py` 的 `_isolate_sensitive_paths` 中把路径重定向到 `tmp_path`，不得依赖测试自行清理。

> **统计类输出默认只算「实时」记录**：凡把历史记录折叠成统计/排行榜/提示词摘要的功能（如 `core/signal_ledger.py::fold_signals(live_only=True)`），必须给每条记录附来源标签并可区分「可证明为实时」与其余，**默认只统计实时记录**、且**不引入新的合成数据开关**——来源判定复用既有数据质量设施（逐品种 `data_freshness` + 降级事件），未识别的取值一律保守判非实时；确需乐观缺省时（无逐品种条目可证伪）必须显式写入理由字段，不得静默。

### 新增功能开关检查清单

全部功能开关以**注册表驱动**：`config/features.py` 的 `feature_switch_registry`（唯一事实源）一处登记，即自动出现在三个面，**不得在任一渠道层另写一份开关清单**。每条声明五个字段——显示名、说明、**分组**、**默认值**、产物影响。

**先定分组，再定默认值**（两栏互不牵连，这是本注册表的核心取舍）：

| 分组 | 成员特征 | `default` | 面板标题 |
|:--|:--|:--|:--|
| `GROUP_EXPERIMENTAL` | 会改变报告产物、需真实数据验证后择机转正 | `False` | ⚗ 实验性功能（默认关闭） |
| `GROUP_STANDARD` | 常驻能力，用户可关但默认开 | `True` | 常规开关（默认开启） |

| # | 步骤 | 操作位置 | 产出 |
|---|------|---------|------|
| ① | **登记注册表** | `config/features.py` → `feature_switch_registry` | 追加 `"<flag>": FeatureSwitchDef("<显示名>", "<说明>", <分组>, <默认值>, <affects_report>)`；键名即 `features.json` 键名、`--experiment` / `--feature` 取值，显示名与说明自动下发三个面。`_FEATURE_FLAGS_DEFAULT` 是注册表的**派生投影**，不得单独在此另登记（新增开关只改注册表一处） |
| ② | **定分组与默认值** | 同上声明第 3、4 位 | 会改变产物且未验证 → 实验组 + `False`；常驻能力 → 常规组 + `True`。两者一同决定「是否上屏」与「出厂取值」——**可见性由分组表达，不再与默认值绑定**，转正因此不会摘掉面板入口 |
| ②′ | **回答产物影响** | 同上声明第 5 位 | 该开关**能否改变报告产物内容**——能则 `True`，仅影响入口可见性（菜单项/卡片显隐）则 `False`。答 `False` 者不进报告生成条件自述（`enabled_experimental_features()` 按此过滤）：报告是脱离本机流转的文件，列进一个不改任何字节的开关，读者会推断内容受其影响 |
| ③ | **消费开关** | 功能实现处 | 一律经 `is_feature_enabled()` 读取；开关判定若影响提示词，须收敛在缓存后缀函数内部（见上方「缓存指纹必须读写两侧同源」） |
| ④ | **覆盖三面** | 自动 | TUI 菜单 `[S]`（实验块 + 常规块，分块取自 `GROUP_ORDER`）/ Web 配置面板（同构两块）/ CLI `--experiment`（实验组简写）与 `--feature NAME=VALUE`（全域双向）均由注册表生成，无需改渠道代码 |
| ⑤ | **验证** | 终端 | `.venv/bin/python -m pytest src/test/unit/config/test_features.py src/test/unit/web/test_config_edit.py -v` — 注册表不变量（分组合法 / 五字段齐备 / 键集与派生投影一致）+ 配置编辑白名单覆盖全注册表 |

> **菜单项/卡片可见性由开关门控**：若实验功能有常驻入口（TUI 菜单项、Web 卡片），开关关闭时必须**就地裁剪**而非渲染后置灰——TUI 侧向 `tui/tui_menu.py::FEATURE_GATED_ITEMS` 登记 `(菜单项, 开关名)`，Web 侧由 `system_info` 透出 `*_enabled` 供前端决定是否渲染；`tui/tui_menu.py::_apply_feature_gates()` 是统一裁剪点。

> **「实验性」的准入与转正判据**：实验项的判定口径是「**能否改变报告产物内容**」，而非「新不新」。新增能力默认关的惯例适用于会改变产物的能力（LLM 增强、指标开关、数据结构变更）——它们需要真实数据验证，默认关是对既有用户产物的保护。但**只读诊断类能力（不改产物、不写文件、不在默认路径产生隐式网络或耗时代价）应默认开启**：默认关的实际代价是让最需要它的人（环境出故障的那批）恰好看不到它，而开启对默认输出零代价。此类能力转正后：① 声明从 `GROUP_EXPERIMENTAL` 改到 `GROUP_STANDARD` 并把 `default` 改 `True`（**一处字段改动**）——面板可见性随分组自动延续，不再出现「转正即从面板消失」；② 不再进产物自述（`affects_report` 答 `False` 且不在实验组）；③ 门控读取（`FEATURE_GATED_ITEMS` / `system_info`）**保留**——转正不等于不可关，`features.json` 置 `false` 仍可隐藏入口；④ 门控表与消费点均须有「默认配置下入口可见」的测试，只依赖 `patch` 覆盖取值的用例测不出默认值本身。系统自检（`doctor_check`）是此模式的首例。

> **内部接缝类开关也应转正（第二类首例：`datasource_adapter`）**：判据与上一条同源但落在另一面——**开关两种取值下报告产物是否等价**。若等价（新实现只是把既有路径换成结构更清晰的等价实现，差异经等价性回归测试逐项锁定且不影响下游取值语义），则它既不是用户可感知的功能、也不是用户能做的选择，摆在用户面前只会让人误以为「开了有好处」，而默认关的实际代价是**生产路径从不执行新实现**、新数据源/新字段接入时才第一次实跑。此类开关转正为常规组、**默认开**：① 声明改到 `GROUP_STANDARD` 且 `default` 置 `True`；② 开关本身保留为**回退杠杆**（`features.json` 置 false 即回退既有实现）；③ 测试补四向——默认值、不在实验组、显式关闭仍走既有实现、默认配置下走新实现（见 `test_features.py::TestDatasourceAdapterPromotion`）。数据源适配契约（`datasource_adapter`）是此模式的首例。

> **读侧增强类开关也应转正（第三类首例：`deterministic_signal` / `module_quality_gate` / `decision_header_parse` / `llm_debate_conditional` / `datasource_credential_ready`）**：判据落在「**开启的代价是否只在读侧**」——只在既有提示词或既有产物流水线上追加一段由**已算出的**数据派生的内容，不新增 LLM 调用次数、不写新的持久化文件、无隐式网络与耗时；且该段内容有确定的收益（方向性结论替代裸数值、结构化契约替代表格猜测、质量分级提示读者降级参考、缺凭据时给可读指引）。此类开关默认关的实际代价是**机制在生产路径从不执行**，用户手上的产物看不到这层增强；用户若逐项去 `features.json` 里打开它，等于用配置承担了本该由默认值表达的取舍（转正判据的可观测量：见 core/experiment_stats.py 的启用次数统计与 doctor 账本概览）。转正口径：① 声明改到 `GROUP_STANDARD` 且 `default` 置 `True`；② `affects_report` **照实答 `True`**——它们确实改变产物内容（`deterministic_signal` 注入信号块、`module_quality_gate` 注入质量横幅、`decision_header_parse` 追加契约行、`llm_debate_conditional` 追加情景段、`datasource_credential_ready` 改变数据源就绪行为），故 Web 面板照常带「（影响报告）」标记；③ 开关保留为关闭杠杆，`features.json` 置 false 即回到「未引入本机制」的行为；④ 凡开关改变提示词者，其缓存后缀函数（`structured_header_cache_suffix()` → `_dh`、`debate_feature_cache_suffix()` → `_c`、`prompts_signals._signal_digest_cache_suffix()`、`core.signal_ledger.summary_cache_suffix()` → `_sg`）随之由「默认返回空」变为「默认返回非空」——**升级后首次运行会换键重生成一次**，属预期行为，须在变更记录中写明；⑤ 测试补四向——默认值、不在实验组、显式关闭仍走未引入前的路径（关闭基线必须**显式**置 false，不能再依赖 `reset_feature_flags()`，它现在返回的是已转正的默认值）、默认配置下走增强路径（见 `test_features.py::TestReadSidePromotion`）。
>
> **章节/页签类开关转正目标是报告组（第四类，首例待定：`holding_change_review` / `whatif_trade_cost` / `event_window_impact` 经真实启用验证后按此执行）**：判据落在「产物形态」——独立章节/页签类能力验证通过后的归宿是「报告章节与增强」组而非常规组：`default` 保持 `False`（默认产物字节不因转正变化，读者拿到的报告不因转正多出章节），面板入口随分组自动延续（实验块 → 报告块，`--experiment` 取值域随实验组身份同步退出），产物自述与启用统计随实验组身份移除（「质量可能不稳定」警示只属于未验证功能，统计的观测使命随转正完成）。转正定义因此为「**移出实验组、目标组按功能形态选**」。
>
> **刻意不转正的两类（判据的反面）**：**写盘积累型**——`decision_reflection` 仍留在实验组（账本结算样本尚不足以判转正，撤销死线见 plan.md）。`signal_ledger`（确定性信号沉淀）不再单独设开关：其真实积累已验证（账本有存量数据、写盘幂等开销可忽略），并入 `deterministic_signal` 转正为常规开关；**调用次数放大型**——`llm_debate_procon` 把一次 `expert_review` 调用换成最多三次（pro → con → synthesis），默认开启直接改变费用与耗时量级，留实验组由用户按需开启。集中度问答不再受开关控制（原 `llm_debate_qa_concentration` 已撤销），改为辩论流程内建段落（阈值触发）。实验功能的真实使用情况可用 `core/experiment_stats.py`（启用计数）加 `doctor` 账本概览观测，作为转正/撤销的客观数据。

> **诊断类命令不得依赖 config 初始化**：`doctor` / `view-logs` / `check-sources` 三个子命令在 `main()` 中**先于 `init_config` 分派**——配置损坏正是它们要定位的场景，若先初始化配置再分派，用户会在最需要诊断能力时被配置错误挡在门外（死锁）。新增诊断类命令遵循同一模式：**先分派、后初始化**，并把「命令失败」（退出码 2）与「命令跑完但结论不佳」（退出码 1）用 `_EXIT_SUCCESS` / `_EXIT_PARTIAL` / `_EXIT_SEVERE` 常量区分开，不得写裸字面量。**诊断类命令自身永不抛异常**——任何内部异常都转成一条结果行，否则等于在最需要它的时刻失效（`core/doctor.py`）。

> **新增数值解析一律委托 `core/num_utils.py`，禁止自写 `try: float(x) / except`**：`float("nan")` / `float("±inf")` **不抛异常**，该形态的兜底对它们完全无效，脏值会一路穿透到聚合、绘图与 JSON 序列化；`value or 0.0` 同样是**假兜底**（NaN 是真值，`or` 不会短路）。按语义选入口：宽容解析（含数值字符串）用 `safe_num`、类型契约敏感场景用 `strict_num`、替代 `or 0.0` 惯用法用 `finite_or`、判定谓词用 `is_finite_number`。**不改变既有失败口径**（`0.0` 还是 `None` 由调用方契约决定），只保证「返回的数值一定有限」。

### 精确键名缓存

```python
DataModuleDef("我的固定键", "fixed",
              exact_cache_keys=("my_special_cache",),
              cache_ttl=CACHE_WEEKLY),
```

精确键名不会被前缀通配误匹配，适合固定文件名的缓存。

### 计算模块注册表（_COMPUTATION_REGISTRY）

除 `_MODULE_REGISTRY`（有缓存的数据模块）外，还维护 `_COMPUTATION_REGISTRY`——纯计算模块（无缓存）的注册表，实现在 `core/computation_registry.py`（`core/registry.py` 顶部 re-export，原访问面不变）：

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

> 报表页签标题与顺序由两张**独立**注册表分别驱动，**不**随 `_MODULE_REGISTRY` 自动派生：
> - `get_report_sheet_name(sheet_key)` → 读 `_REPORT_SHEET_NAMES`（sheet key → 中文标题映射；派生视图：非 LLM 章键值由 `_REPORT_SECTION_DEFAULT` 条目派生，LLM 章标题显式登记、差集键集为 `_LLM_SHEET_NAME_KEYS`）
> - `get_report_section_order(config)` → 读 `_REPORT_SECTION_DEFAULT`（章顺序与分组）
>
> 二者职责不同：前者管「页签叫什么」，后者管「章按什么顺序排」。新增报告章在 `_REPORT_SECTION_DEFAULT` 登记后，页签标题由派生视图自动跟进（LLM 章例外：其显示名在 `_REPORT_SHEET_NAMES` 显式登记并把键声明进 `_LLM_SHEET_NAME_KEYS`）；若该页签属报告章，还需在 `_REPORT_SECTION_DEFAULT` 登记顺序（`scripts/check-semantic-index.py` 校验合并章引用的 sheet key 存在于 `_REPORT_SECTION_DEFAULT`）。

### 测试

registry 的测试在 `src/test/unit/core/test_registry.py`，验证 TTL 默认值完整性、前缀类型映射一致性、精确键名映射、LLM settings keys 与模块列表匹配、所有 LLM 模块都有 settings_suffix、缓存分组标记完整性。

```bash
.venv/bin/python -m pytest src/test/unit/core/test_registry.py -v
```

## 版本发布流程

发布版本时，按以下五步顺序执行：

> 可用 `scripts/release.py` 分步编排（五步的可执行封装，每步独立可审阅、失败即停）：`prepare`（版本全链与 changelog 归档）、`refresh` + `evolution --release`（数据刷新与演进快照）、`gate`（P2 门禁）、`publish --title`（release 提交 + P1 verify + `--no-ff` 合并 + tag）、`devbump`（切开发版），另有 `check` 预检；下列手动命令为底层口径，脚本失败时按手动步骤排查。

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
- `folders.md` — 项目统计表及目录树新增/重命名文件；**版本演进对照表（`## 版本演进对照`）每次发布必须更新**：「最新发布」列按新 tag 重跑快照统计（复现方法见 folders.md 表头：`git ls-tree` + `git cat-file --batch` 计行 + `git grep -c "def test_"` 数用例），「当前开发版」列同步重跑；列头版本号与 tag/日期由 `check-version-consistency.py --fix`（`evolution_head`/`release_tag` 断言）同步，只改版本号不刷演进表数据行属发布遗漏
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

**⑤ 合并入 master**

发布并打 tag 后，**必须**把 `dev` 合并入 `master` 并推送（`master` 是发布分支，只存放已发布状态；不得只打 tag 而不更新 master）：

```bash
.venv/bin/python scripts/test-runner.py --mode verify   # P1 合入门禁，必须先通过
git checkout master && git merge --no-ff dev -m "Merge branch 'dev' — v{x.y.z} 发布" && git push origin master
git checkout dev
```

合入后确认 tag 所指提交已在 `master` 可达（`git merge-base --is-ancestor v{x.y.z} origin/master`）；`master` 推送会触发 CI 的 P1（`verify`）档。本步与步骤④互不替代：④ 是让 dev 进入下一个开发周期，⑤ 是把已发布状态同步到发布分支。

## 关键纪律来源

本指南为面向开发者的"入口版"。以下完整纪律以 [CLAUDE.md](../../CLAUDE.md) 为准：

- **架构遵从**：所有模块必须遵守 `technical.md` 的「架构设计约束」表格（含设计目的/违反后果/适用范围）和「概要设计—核心架构决策」。涉及数据降级/熔断逻辑时额外参考概要设计双重降级治理体系说明
- **测试隔离**：运行测试不得修改用户的配置文件、持仓文件等敏感数据；`conftest.py` 自动将 `config.json` 和缓存目录重定向到临时目录
- **缺陷自测**：发现并修复缺陷时，**必须**为该缺陷编写可自测的回归测试用例，避免再次回退；新增功能时**必须**同步编写测试用例覆盖
- **目录结构同步**：新增/重命名任何非排除文件或目录时，**必须**同步更新 `folders.md` 中的目录树，并确保每个文件都有简短说明
- **文件归属三原则**：中间计划文件 → `docs/plan/`；运行时临时产物 → `docs/tmp/`；`.claude/` 全局目录只存放 Claude Code 工具自动管理的运行时数据，**禁止主动写入**任何文件
- **设计契约**：Web/报告 UI 改动（样式、token、组件状态、版式、空态文案）前先读仓库根 [DESIGN.md](../../DESIGN.md)——Colors 角色表 / Typography 字阶 / 组件六态 / 断点表 / Do-Don't 护栏 / 迭代指引；新增声明取自契约档位，验收见 `src/test/unit/report/test_design_doc.py`
