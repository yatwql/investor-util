# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.3-dev
> **编号源**：`rf-next = 427`（新增问题取此编号，完成后更新为 +1；已用最大 rf-426，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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

#### P2D — 需求追溯映射（2026-09-24）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-426** | **需求 ID 追溯链断裂**：`requirements.md` 定义 **277 个**需求 ID（35 个域），而 `testplan.md` / `technical.md` / `llm-technical.md` 对需求 ID 的引用数均为 **0**，requirements 亦不引用 testplan——无法机器回答「某需求是否有测试覆盖」 | 分批建立逐条映射（见下表 6 批；批 1 启动时先定稿交付形态），完成一批登记一批；配套新增「需求 ID ↔ 映射」双向断言脚本并入 `--ci` |

> 来源：四文档一致性比对（用户要求）。**缺口**：`requirements.md` 定义 **277 个**需求 ID（35 个域），而 `testplan.md` / `technical.md` / `llm-technical.md` 对需求 ID 的引用数均为 **0**，requirements 亦不引用 testplan——「需求 → 设计 → 测试」的 ID 级追溯链断裂，无法机器回答「某需求是否有测试覆盖」。用户决策：**分批建立逐条映射**（本项即该批次任务的总登记）。

**目标**：为 277 个需求 ID 逐条建立「验证载体」映射，使每条需求可追溯到具体测试文件/用例（无覆盖者显式标注「缺覆盖」并转入待办）。

**分批计划**（按域条目数降序，每批以「域的语义内聚性 + 条目数 ≤20」为界）：

| 批次 | 覆盖域 | ID 数 | 状态 |
|---|---|---|---|
| 批 1 | `R-CCH`（缓存） | 38 | 待办（可再拆为缓存键/TTL/清理三小组） |
| 批 2 | `R-ERR`、`R-DIAG`、`R-BRK`、`R-CRD` | 39 | 待办（错误与降级治理域，语义同族） |
| 批 3 | `R-FIN`、`R-FRD`、`R-NWS`、`R-DATA`、`R-IDX` | 37 | 待办（数据取数与财报域） |
| 批 4 | `R-OUT`、`R-PERF`、`R-WIF`、`R-ACT`、`R-RBL`、`R-VAL`、`R-TAIL`、`R-EVO`、`R-SNP`、`R-CFL`、`R-DIFF`、`R-PEN` | 57 | 待办（报告输出与分析域） |
| 批 5 | `R-LLM`、`R-PF`、`R-CTX` | 25 | 待办（LLM 域；含本轮 plan-47/48 口径） |
| 批 6 | `R-WEB`、`R-TUI`、`R-ENV`、`R-HLD`、`R-DIS`、`R-LIQ`、`R-FX`、`R-CON`、`R-ADP`、`R-HST` | 61 | 待办（渠道/输入/分析杂项域） |

**交付形态**（每批完成时）：在 `testplan.md` §2 覆盖表新增一列「验证载体（需求 ID）」，或在 `requirements.md` 各需求行加「验证位置」列——**二选一需在批 1 启动时定稿**（避免中途换形态导致返工）；配套新增断言脚本（复用 `_checklib`）校验「需求 ID ↔ 映射」双向一致，纳入 `--ci`。

**口径要点**：映射粒度以「可机器校验」为准（ID → 文件/用例名），不追求逐条等价；一条需求允许多载体；无覆盖者必须显式登记而非留空（空值即漏检）。

## 已解决问题

### 已解决待归档（v0.11.3-dev）

> 本轮开发修复的问题在此逐条登记，发布时整体并入归档。

| # | 问题（违反的约束用语义描述） | 处置 |
|---|------|------|
| **rf-425** | **测试用例全量审计（用户要求：查冗余用例 / 无效用例 / 命名与内容语义相关）**：门禁 `check-test-redundancy`（死用例/无断言/完全重复/自证）零告警；增强扫描（7,378 用例 AST 级）发现三类问题——① **真冗余**：`TestSupportsExtendedThinking` / `TestIsEffortModel` 两个类在 `test_llm_utils.py` 与 `test_llm_api_base.py` **重复存在**，且后者为前者严格子集（唯一独有断言：`gpt-4o → False`）；② **粗命名 26 处**：`test_success` / `test_normal` / `test_basic` 类命名不承载内容（如 `TestFetchNav::test_success`）；③ **弱断言 1 处**：`test_missing_code_still_processes` 对 `float \| None` 返回值仅断言「非空」——虽仍有判别力，但实现假化为恒返非空值时仍通过。**判定无问题**：跨文件同体对 1 组（`test_no_quotes`，sina/tencent 两家解析器的并行覆盖，符合 rf-411 既定口径）；输入条件式命名 26 处（`TestParseFloat::test_zero` 等，类上下文已带语义，属合规模式） | ① **去冗余**：`gpt-4o` 独有用例迁入 utils 版（新增 `test_non_llm_family_not_supported`），删除 `test_llm_api_base.py` 的两个子集类（-5 例，覆盖零损失）；② **重命名 26 处**为名实相符的描述性命名（逐个读函数体后按 docstring 语义定名，如 `test_returns_standard_quote_record`、`test_parses_roll_data_items`、`test_formats_dividend_yield_percent`）——避免 rf-411 那类「名实不符」新缺陷；③ **强化弱断言**：`turnover_rate` 用例改为精确断言 `== 1.0`（两期权重不相交，语义可推导）。净用例数 -4（7,764 → 7,760） |
| **rf-424** | **管理文档分区纪律无断言覆盖**（承接 rf-423 同类根因，用户同意后实施）：本轮两次自审失误同源——① 待处理项 `rf-420` 被误置「已解决待归档」表（rf-421 记录）；② 发布时误删 changelog 归档索引（rf-423）。二者本质都是「管理文档的分区/索引纪律只靠人工遵守，无机器断言」，门禁全绿也拦不住 | ① `check-doc-drift.py` 新增第 12 项 `audit_management_partitions`（纯函数，便于直测）：**A** review-findings 同一 rf 不得同时出现在待处理与已解决分区；**且已解决项必须在 changelog（现行 + 归档）有修复记录**——待处理项被误置已解决区时必然不满足（即 rf-421 类失误的可检特征）；**B** plan 待办区不得出现 ✅ 已完成项、不得列已归档项（已归档项只认 `#### ✅ `plan-N`` 条目标题，归档文件正文提及不误判）；**C** 现行 changelog 只允许一个版本段头且必须为 `-dev` 段（已发布段须随发布移入归档）；② 回归 +10 例（真实仓库一致 / 三类失误各自检出 / 归档 changelog 记录不误报 / 归档正文提及不误报 / 空文件不崩）；③ 检查项枚举同步 6 处（脚本 OK 文案与 argparse、folders.md ×2、developer-guide.md、testplan.md ×2、CLAUDE.md ×2） |
| **rf-423** | **发布 v0.11.2 时误删 changelog 的「## 归档」索引段**（用户指出）：切换开发版本时把「已发布段到文件末尾」整段重写，而归档索引恰在文件末尾 → 11 条历史归档索引（v0.1.x ~ v0.11.x 的 `archived_changelog.*`）被一并删除；当时**无任何断言覆盖「管理文档归档索引 ↔ docs-stm/archive/ 实际文件」的一致性**，故未被任何门禁拦住（同类索引段在 plan.md / review-findings.md 同样无守卫） | ① 自发布前版本 `git show` 取回索引段并恢复（0.11.x 条目更新为 v0.11.0 ~ v0.11.2），移除临时单条指针；② `check-doc-drift.py` 新增第 11 项**归档索引完整性**检查（`check_archive_index`）：三份管理文档（changelog/plan/review-findings）须**双向**对齐磁盘归档文件——漏列报「缺少」、幽灵引用报「不存在」；**直接读文件而非 `_scan_docs()`**（changelog 属历史记录类被该扫描面排除，正是本次缺口根源）；③ 回归 +5 例（真实仓库一致 / 删条目即报 / 幽灵引用即报 / 被检面覆盖三份文档 / 端到端检出真实仓库违规） |
### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)  — rf-380 ~ rf-401（v0.11.0 ~ v0.11.1 批次，2026-09-18 并入）；rf-379、rf-402 ~ rf-422（v0.11.2 批次，2026-09-24 并入）
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
