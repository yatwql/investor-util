# 辅助脚本参考

> 项目 `scripts/` 目录下的所有工具脚本用法速查。

---

## 一览

| 脚本 | 分类 | 一句话 |
|:-----|:-----|:-------|
| `test_runner.py` | 测试 | pytest 标记模式封装驱动，支持 14 种 `--mode` |
| `extract-test-failures.py` | 测试 | 从 pytest-html 报告提取失败用例详情 |
| `check-code-traces.py` | 测试 | 代码注释/文档字符串中历史变更痕迹检查 |
| `check-doc-traces.py` | 测试 | 面向读者文档（.md）中历史变更痕迹检查 |
| `check-test-markers.py` | 测试 | AST 静态扫描验证测试标记合规性 |
| `check-task-numbering.py` | 测试 | 任务编号（plan-/rf-）全局一致性检查，防新增编号与历史归档冲突 |
| `check-task-numbering-hook.py` | 测试 | Claude Code PostToolUse hook——编辑编号管理文档后自动校验编号一致性 |
| `install-claude-hook.py` | 测试 | 安装/卸载 Claude Code PostToolUse hook（任务编号一致性自动校验） |
| `llm_hallucination_sampler.py` | 测试 | 10 组标准持仓 × LLM 幻觉率采样 |
| `calibrate-dedup-threshold.py` | 测试 | 新闻去重阈值校准分析 |
| `collect-test-coverage.py` | 测试 | 测试覆盖计数收集（`pytest --collect-only` 快照，供 test-coverage.md 更新） |
| `check-version-consistency.py` | 质量 | 版本号全局一致性检查（发布前必跑） |
| `perf_report.py` | 诊断 | 端到端报告生成管线性能基准（独立脚本，mock 外部数据源） |
| `perf_view.py` | 诊断 | 性能历史趋势查看（读取 perf_history.jsonl → 跨版本耗时对比） |
| `diagnose_gemini_proxy.py` | 诊断 | Gemini API 代理连通性诊断 |
| `probe-csi-factor-indices.py` | 诊断 | CSI 风格指数可用性探测（风格因子回归前置决策闸门） |
| `launch.sh` / `launch.ps1` | 启动 | Linux/macOS / Windows 一键启动脚本 |
| `check-sources` | 诊断 | cli.py 子命令：数据源联通性检测 |
| `whatif` | 诊断 | cli.py 子命令：调仓 What-if 模拟（对比两份持仓生成独立 diff 报告，见 [快速开始](how-to-start.md)） |

---

## 测试类

### `test_runner.py` — 测试模式驱动

pytest 的 `-m` 标记表达式封装层，按 `--mode` 选择预定义组合。

```bash
# 查看所有可用 mode
python scripts/test_runner.py --help

# 日常提交前门禁（P0）
python scripts/test_runner.py --mode dev-verify

# 合入门禁（P1）
python scripts/test_runner.py --mode verify

# 发布门禁（P2）
python scripts/test_runner.py --mode verify,regression

# 常用快捷模式
python scripts/test_runner.py --mode unit         # 全量单元测试
python scripts/test_runner.py --mode scenario     # 业务场景测试
python scripts/test_runner.py --mode edge         # 边缘/异常场景
python scripts/test_runner.py --mode smoke        # 冒烟测试（~15s）
python scripts/test_runner.py --mode data         # 数据正确性验证

# 多模式组合
python scripts/test_runner.py --mode scenario,edge

# 带行覆盖率
python scripts/test_runner.py --mode unit --coverage
```

> **`test_runner.py` 不支持 `--` 透传**（如 `-- --lf`）。如需 `--lf` 绕过它直接调 pytest，用 `-m` 复现目标模式的标记表达式。各 `--mode` 对应的 `-m` 表达式见下文"标记表达式对照"或直接查看 `MODES` 字典。

#### `--mode` 与 pytest `-m` 对照

| `--mode` | 等效 `-m` 表达式 | 典型耗时 |
|:---------|:-----------------|:--------:|
| `regression` | `scenario` | ~6min |
| `smoke` | `smoke` | ~15s |
| `unit` | `unit` | ~30s |
| `standard` | `unit and not (edge or data)` | ~30s |
| `edge` | `edge` | ~15s |
| `data` | `data` | ~10s |
| `scenario` | `scenario` | ~6min |
| `integration` | `scenario or integration` | ~50s |
| `verify` | `unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts` | ~1min |
| `dev-verify` | `(unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts) and not (edge or data)` + `scenario_basic`（两阶段） | ~2.5min |
| `all` | （无过滤，全量） | ~10min |
| `all_no_unit` | `not unit` | ~7min |
| `report` | `unit_report` | ~15s |
| `scenario_extreme` | `scenario_extreme` | ~1min |

---

### `extract-test-failures.py` — 失败用例提取

运行 `test_runner.py --mode verify,regression` 等全量测试后，直接从 HTML 报告中提取失败/错误用例信息。

```bash
# 自动查找 test-reports/latest/ 下最新报告
python scripts/extract-test-failures.py

# 指定报告路径
python scripts/extract-test-failures.py test-reports/latest/all/report.html

# 仅输出汇总统计（不打印日志）
python scripts/extract-test-failures.py --summary

# 输出 JSON 格式（便于管道处理）
python scripts/extract-test-failures.py --json
```

**典型工作流**：

```bash
python scripts/test_runner.py --mode verify,regression     # ① 跑全量验证
python scripts/extract-test-failures.py --summary           # ② 看哪些失败
python scripts/extract-test-failures.py                     # ③ 看详细错误
# 修复代码后只重跑失败用例：
python -m pytest <test_file>::<test_name> -v --tb=short     # ④ 单用例验证
python scripts/test_runner.py --mode verify,regression     # ⑤ 发布确认
```

---

### `check-code-traces.py` — 代码注释历史痕迹检查

扫描 `src/python/`、`src/test/`、`src/static/`、`scripts/` 下所有 `.py` / `.js` / `.mjs` / `.html` / `.sh` / `.ps1` / `.bat` / `.cmd` 文件的注释和文档字符串，检查是否含有代码历史迭代信息（来源拆分、版本号、任务编号、历史迭代叙述等）。代码注释只应描述"当前是什么"，不应记录"从哪里来、怎么变的"。

```bash
# 检查全部
python scripts/check-code-traces.py

# 详细输出（含排除行信息）
python scripts/check-code-traces.py -v

# CI 模式（仅输出 文件名:行号，非零退出码）
python scripts/check-code-traces.py --ci
```

**退出码含义**：

| 退出码 | 含义 | 行动 |
|:------:|:-----|:-----|
| 0 | 全部通过 | 无需处理 |
| 1 | HIGH/ORIGIN/VERSION 痕迹 | 必须修复后再提交 |
| 2 | CODE/IDENT/CHAPTER/ROUND（任务编号/标识符/章节编号引用） | 应从注释/标识符中移除 |
| 3 | 仅 TODO/CHANGE/DEPR 级别 | 建议人工复核 |

---

### `check-doc-traces.py` — 文档历史痕迹检查

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
python scripts/check-doc-traces.py

# 详细输出（含豁免行信息）
python scripts/check-doc-traces.py -v

# CI 模式（仅输出 文件名:行号，非零退出码）
python scripts/check-doc-traces.py --ci
```

**退出码含义**：

| 退出码 | 含义 | 行动 |
|:------:|:-----|:-----|
| 0 | 全部通过 | 无需处理 |
| 1 | HIGH/ARCHIVE/CODE/CIPHER/CHAPTER/ROUND 痕迹 | 应从文档中移除 |
| 2 | 仅 LOW 级别痕迹（需人工判断的变更/过渡类描述） | 建议人工复核 |

---

### `check-test-markers.py` — 标记合规性检查

AST 静态扫描所有 `test_*.py` 文件，检查：
- 标记完整性（是否有 `unit_*` 子标记）
- 拼写错误（未注册的 marker 名）
- `_edge.py` 是否漏标 `edge`，或非 `_edge.py` 文件是否误标 `edge`

```bash
python scripts/check-test-markers.py
```

无报错输出即合规。新增/修改测试文件后必须运行此脚本。

---

### `check-task-numbering.py` — 任务编号全局一致性检查

校验 `plan-` / `rf-` 两类任务编号与各管理文档头部的「编号源」标记（`plan-next` / `rf-next`）是否一致，防止新增编号与历史归档冲突。

新增任务时，编号取管理文档头部 `plan-next` / `rf-next` 当前值，用后将其递增更新；若标记遗漏递增或初值写小，本脚本会扫描当前文档 + 全部历史归档并报错提示修正值。

```bash
python scripts/check-task-numbering.py            # 检查全部（plan + rf）
python scripts/check-task-numbering.py --kind rf  # 仅检查 rf
python scripts/check-task-numbering.py --ci       # CI 模式（只输出错误）
```

**自动保障机制**（三层，跨机器同步策略见各条目）：
- **P0 门禁**：`check-task-numbering.py --ci` 已纳入 CLAUDE.md 提交前/发布前门禁，与 `check-code-traces.py --ci` 同构
- **dev-verify preflight**：`test_runner.py --mode dev-verify` 自动运行编号校验，失败即中止
- **Claude Code hook**：编辑 `plan.md`/`review-findings.md` 后自动校验（`scripts/check-task-numbering-hook.py`），实时拦截冲突
- **git pre-commit**：提交涉及编号文档时自动校验（`.githooks/pre-commit`），绕过流程也拦截

---

### `check-task-numbering-hook.py` — Claude Code PostToolUse hook

Claude Code 编辑 `plan.md` / `review-findings.md` 后自动运行编号校验，失败返回非零退出码中断编辑。读取 `__INJECTED_OBJECT__`（环境变量或命令行参数）识别目标文件；无 hook 上下文或非编号文档时放行。由 `.claude/settings.json` 的 PostToolUse 钩子调用（不随仓库同步，需 `install-claude-hook.py` 接线）。

---

### `install-claude-hook.py` — Claude Code hook 安装/卸载

`.claude/settings.json` 被 `.gitignore` 排除、不随仓库同步。本脚本将 `check-task-numbering-hook.py` 的 PostToolUse 钩子写入该文件，跨机器 clone 后运行一次即完成接线。

```bash
python scripts/install-claude-hook.py             # 安装（幂等，保留已有配置）
python scripts/install-claude-hook.py --uninstall # 卸载
```

---

### `llm_hallucination_sampler.py` — LLM 幻觉率采样

对 **10 组标准化持仓数据** 调用当前 prompt，经事实校验器验证后统计幻觉率（`scenario_llm` 幻觉率采样测试）。

```bash
# 完整采样（调用 LLM API 对 10 组数据生成分析）
python scripts/llm_hallucination_sampler.py

# 仅测试特定模块（默认 expert_review）
python scripts/llm_hallucination_sampler.py --module health_check

# 仅测试特定数据集（1-indexed）
python scripts/llm_hallucination_sampler.py --dataset 1,3,5

# 跳过 API 调用，只构建 prompt 验证结构
python scripts/llm_hallucination_sampler.py --dry-run

# 跳过缓存强制重新生成
python scripts/llm_hallucination_sampler.py --force
```

**输出**：
- 报告文件：`docs-stm/tmp/hallucination-report.md`
- Dry-run prompt 转储：`docs-stm/tmp/hallucination-prompts-{module}.md`

---

### `calibrate-dedup-threshold.py` — 新闻去重阈值校准

新闻标题去重（同源/跨源两档阈值 + 中文 bigram）在每次报告运行时自动记录"边界案例"到 `data/cache/dedup_anchors.jsonl`。积累足够锚点后，用此脚本分析当前阈值是否合理。

```bash
# 分析全部锚点，输出建议
python scripts/calibrate-dedup-threshold.py

# 仅看汇总统计（不展开详细列表）
python scripts/calibrate-dedup-threshold.py --summary

# 指定锚点文件
python scripts/calibrate-dedup-threshold.py --file data/cache/dedup_anchors.jsonl
```

**校准时机**：建议锚点文件积累 **100 条以上**（约 5~10 次报告运行）后校准一次。脚本只分析不自动修改阈值，是否需要调整由开发者判断。

**输出示例**：

```
=== cross_skip（跨源 ≥0.30 但 bigram<3 被跳过 — 潜在漏判）===
  数量: 12
  ratio 范围: 0.300 ~ 0.450
  bigram 范围: 0 ~ 2

=== 校准建议 ===
[!] cross_threshold=0.30: 5 条 ratio≥0.35 被跳过
    建议审查这些案例是否应为重复
[OK] 跨源 bigram=3: 无边界样本
```

---

### `collect-test-coverage.py` — 测试覆盖计数收集

只做 `pytest --collect-only`（收集测试项，**不执行测试**，耗时约 2s），按 `test_runner.py` MODES 的 marker 表达式本地归类计数，输出各模式 / unit 子标记 / scenario 分组 / 跨类标记 / 功能域 / 文件分布的项数，供 `docs-stm/managements/test-coverage.md` 快照更新使用。

```bash
python scripts/collect-test-coverage.py
```

**说明**：
- 只收集不执行——测试体不会运行，不影响测试结果，也不会触发真实数据源 / LLM 调用
- 项数随版本迭代变化，属撰写时快照，精确计数以本脚本实时输出为准
- 计数口径与 `test_runner.py` 的 `MODES` marker 表达式对齐（verify / dev-verify 等组合模式同样本地复现）

---

## 质量类

### `check-version-consistency.py` — 版本号一致性检查

发布版本前必须运行。检查 `APP_VERSION`（`src/python/core/constants.py`）与以下文件的版本号是否一致：

- `pyproject.toml`（`version` 字段，`--fix` 可自动同步）
- `README.md`
- 管理文档 9 份：`plan.md`、`technical.md`、`requirements.md`、`testplan.md`、`review-findings.md`、`llm-technical.md`、`folders.md`、`test-coverage.md`、`changelog.md`
- `docs-stm/manuals/how-to-test-my-code.md`

```bash
# 无参数运行，逐项检查并报 [OK]/[ERR]
python scripts/check-version-consistency.py
```

全部 `[OK]` 方可提交。如有 `[ERR]`，按提示逐个同步，然后重跑直到全部通过。

**版本切换工作流**：

```bash
# ① 发布版本：修改 APP_VERSION → 运行检查 → 同步全部 → 提交 → git tag
# ② 开发版本：修改 APP_VERSION 为 next-version-dev → 运行检查 → 全部 [OK] → 提交
```

---

## 诊断类

### `perf_report.py` — 端到端性能基准

生成 20+ 品种 + 3 年模拟持仓，运行 basic/both 报告生成管线，测量各阶段耗时。

```bash
python scripts/perf_report.py
```

**输出**：`docs-stm/tmp/better-investment-performance-test-report.md`

**目标**：basic 模式总耗时 < 60s

---

### `perf_view.py` — 性能历史趋势查看

读取 `data/state/perf_history.jsonl`（由 `PerfCollector` 在每次报告生成时自动追加），按版本和报告类型分组统计，输出版本间性能趋势对比。

```bash
# 输出全部历史趋势到 stdout
python scripts/perf_view.py

# 仅看 full 类型报告的性能趋势
python scripts/perf_view.py --report-type full

# 仅看最近 30 条记录
python scripts/perf_view.py --last 30

# 同时写入 docs-stm/tmp/perf_trend.md
python scripts/perf_view.py --save
```

**输出列说明**：

| 列 | 含义 |
|:---|:------|
| 阶段 | 报告生成管线阶段名称（行情获取/快照对比/历史走势/HTML 生成/Excel 生成 等） |
| 平均耗时 | 该阶段历史平均耗时 |
| 最短/最长 | 该阶段历史最小/最大耗时 |
| 次数 | 该阶段出现次数（条件阶段如历史走势仅在启用时出现） |

**数据来源**：每次 `generate_report()` 调用时自动记录到 `data/state/perf_history.jsonl`，无需手动触发。

---

### `diagnose_gemini_proxy.py` — Gemini API 代理诊断

当 Gemini API 代理（如 `http://10.22.207.29:10037`）出现连通性问题时，逐项检测网络层、代理层和 API 层的健康状况。

```bash
python scripts/diagnose_gemini_proxy.py
```

**检测项目**：
1. 直接 Google 连通性（`google.com`）
2. 代理服务器连通性（`telnet` 式探测）
3. 代理 HTTP 请求（`curl -x` 等效）
4. Gemini API 真实调用（使用当前 `llm_key.json` 配置）
5. DNS 解析
6. 各环境变量（`HTTP_PROXY` / `HTTPS_PROXY` / `http_proxy` / `https_proxy`）

每项显示 ✅/❌ 状态和详细错误信息，定位哪一层出了问题。

---

## 启动脚本

### `launch.sh` — Linux/macOS 启动

```bash
./scripts/launch.sh
```

### `launch.ps1` — Windows PowerShell 启动

```powershell
.\scripts\launch.ps1
```

两者均负责：激活虚拟环境（如存在）、设置 `PYTHONPATH`、启动主程序 TUI。

---

## CLI 模式

### `check-sources` — 数据源健康检查

跳过 TUI 交互界面，直接测试各数据源联通性并报告延迟。

```bash
# 运行数据源健康检查
python -m src.python.cli check-sources
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
