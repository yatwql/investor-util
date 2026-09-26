# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.6-dev
> **编号源**：`rf-next = 448`（新增问题取此编号，完成后更新为 +1；已用最大 rf-447，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 666 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-09-10 实测 666，较登记值 665 增长 1） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 542 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 544 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-09-10 实测 544，较登记值 536 增长 8，数值归一防线纳入后仍处 500-800 区间） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限；2026-09-10 实测 521，较登记值 526 下降 5） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 405 | 未超限（<500，维持现状；2026-09-10 实测 405，较登记值 401 增长 4） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 633 | 500-800 可选优化区间（2026-08-05 实测 635，较登记值 472 增长 163，跨过 500 线；2026-09-10 实测 633，较上次下降 2，关注后续增长） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 427 | 未超限（<500，维持现状；2026-08-05 实测 423，较登记值 477 下降，重构后缩减；2026-09-10 实测 427，较上次增长 4，决策登记载体纳入后仍处 500 线以下） | Excel 编排器 |

#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

#### P2C — 文档与配置口径（2026-09-24）

> 无待处理项（`rf-420` 已修复，见「已解决问题」区）。

## 已解决问题

### 已解决待归档（v0.11.6-dev）

> 暂无（v0.11.5 批次 rf-431 ~ rf-443 已随发布归档至 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)；另补录 v0.11.4 批次 rf-428 ~ rf-430）









| **rf-447** | **`.git/hooks/` 残留三个无效 pre-push 桩文件，且 `install-hooks.sh --off` 提示语未说明“回退默认路径不会有任何 hook”**：`pre-push`、`pre-push(1)`、`pre-push(1)(1)` 均为 17 字节 `#!/bin/sh` + `exit 0`（mode 644、mtime 相隔 3 秒——云同步冲突副本形态）。因 `core.hooksPath=.githooks`（仓库本地配置）被旁路，且本身非可执行，**双层失效**；但会被误读为“存在 pre-push 校验”，且一旦执行 `--off` 回退默认路径，Git 会在每次 push 打印 `hint: The '.git/hooks/pre-push' hook was ignored because it's not set as executable.`（纯噪音） | 已验证并修复（2026-09-26）：① 用 `git hook run`（Git 2.47.3）拿证据——`git hook run pre-push` 在 `.git/hooks/pre-push` 存在的情况下报 `cannot find a hook named pre-push`（路径旁路）；`git -c core.hooksPath=.git/hooks hook run pre-push` 报 not executable hint（权限层拦截）；三者字节一致、`git ls-files .git/hooks/` 为 0（不跟踪、不跨机器）、全仓无引用；② 删除三个本地残留（原件留档以便回滚）；③ `.githooks/install-hooks.sh --off` 增两行说明“Git 回退到 .git/hooks 后本脚本不会在其中安装任何 hook，该目录内容不随仓库同步”；④ 验证：`sh -n` 通过，`--off`/启用往返使 hooksPath 正确变化（未设置 → `.githooks`），启用态下 `pre-push` 仍不可解析（期望：无 pre-push 校验）、`pre-commit` exit 0 |

| **rf-446** | **本会话写入的注释/docstring 引用任务编号与历史叙述，违反语义命名纪律**：`check_sources.py`（`rf-439`）、`conftest.py`（“把它们改成…”命中 HIGH 历史变更叙述）、`test_check_sources.py`（`rf-439`）、`test_report_backup_source.py`（`plan-50`）、`_doc_drift/_format.py`（`rf-437`）共 7 处被 `check-code-traces` 报出（CODE=4 / DEPR=2 / HIGH=1）。**根因**：本会话收尾的本地门禁扫描循环里**漏掉了 `check-code-traces`**（只跑其余 6 个），该脚本直到本次才第一次被执行——也正是本次给 CI 补 `guards` job 的直接证据 | 已修复（2026-09-26）：① 7 处改写为**语义化描述**（去掉 `rf-`/`plan-` 引用、「已废弃」标注与历史变更叙述），`check-code-traces --ci` 回到「未发现历史变更痕迹，注释干净」；② 根因层：本地与 CI 守护清单**以 CI `guards` job 统一**（7 个 `--ci` 脚本一条不漏），不再依赖人工记得「还有哪个脚本没跑」（见 rf-445） |
| **rf-445** | **CI 覆盖面缺口：未执行 7 个 `--ci` 守护脚本，也未执行 `ruff check`**：`.github/workflows/ci.yml` 原先只有 `test` job（三档测试模式）与 `format` job（`ruff format --check src/python/ scripts/`），故**纯文档/编号/痕迹类漂移在 CI 上不会被拦**（如归档索引缺失、文档与实现口径冲突、注释里的任务编号——后者本会话真实漏检 7 处，见 rf-446）；且与 `CLAUDE.md` 的「CI 辅助检查：`ruff check` + `ruff format --check`」表述不符（实际未跑 `ruff check`） | 已修复（2026-09-26）：① 新增 **`guards` job（阻塞型）**，逐个 step 跑 7 个 `--ci` 守护脚本（`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-doc-drift` / `check-test-redundancy` / `check-requirement-trace`），任一失败即红；② `format` job（保留 `continue-on-error`）补 **`ruff check`** 步骤；③ YAML 解析校验通过（jobs: test / format / guards）；④ 本地等价演练：7 脚本 + `ruff check` + `ruff format --check` 全部 exit 0；⑤ 文档同步（CLAUDE.md CI 条目；开发者指南新增「CI 同步执行」段 + 编号保障表新增 CI 行并改「四层→五层」） |
| **rf-444** | **开发者指南三级门禁表数字过期**：§三级门禁表写「P0 / P2 = `test-runner …` + **4 个** check 脚本」，但同章 P0/P2 命令块实际列出 **7 个**（`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-doc-drift` / `check-test-redundancy` / `check-requirement-trace`），`CLAUDE.md` 亦为 7 个——数字少了 3 个，容易让人误以为只跑 4 个即过门禁（本会话扫描循环恰好就漏了 `check-code-traces`，见 rf-446） | 已修复（2026-09-26）：两处「4 个」→「**7 个**」，并在同章新增「**CI 同步执行**」段（分流规则 / 矩阵 / `guards` 与 `format` 两 job 的职责与阻塞性） |

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)  — rf-380 ~ rf-427（v0.11.0 ~ v0.11.3 批次，2026-09-18 / 2026-09-24 并入）；rf-379、rf-402 ~ rf-422（v0.11.2 批次，2026-09-24 并入）；rf-428 ~ rf-430（v0.11.4 批次，2026-09-26 补录）；rf-431 ~ rf-443（v0.11.5 批次，2026-09-26 并入）
- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.20（2026-08-04 ~ 2026-09-15）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
