# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.1-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

## [0.11.0] - 2026-09-15

### 明确 TUI 菜单 [P] 与 [S] 的分工（2026-09-15）

- **问题**：plan-44 后「报告章节」被拆到两个菜单（基础章节组在 `[P]`，报告章节与增强在 `[S]`），但**没有任何一处说明这两者的边界**——手册只解释了 `[S]` 面板内部三块的区别，用户无从判断某个章节开关该去哪个菜单。
- **补齐**：① `how-to-use-tui-menu.md` 新增「P 与 S 的分工（配置入口边界）」对照表——按**配置归属文件**划分，简记 **`[P]` = 整章组的开关（`config.json` 顶层 `enable_*`）；`[S]` = 能力开关与细粒度开关（`features.json` / `llm_settings.json`）**；② `[P]` 菜单描述明确为「配置基础报告章节组（…5 项）」；③ 两个面板底部互相给出跳转提示（`[P]` 提示「报告章节与增强、LLM 分析章节请在菜单 [S] 配置」；`[S]` 提示「基础报告章节组在菜单 [P] 配置」）。

### how-to-config 补齐功能开关分组计数（20 项/两组 → 28 项/三组）（2026-09-15）

- 修正 plan-44 后遗留的三处陈旧表述：「全部 20 项开关分两组」→ **28 项 / 三组**（⚗实验 4 / 常规 16 / 报告章节与增强 8）；「功能开关的三个入口」段补报告块（TUI 与 Web 均按三块描述）；面板布局注的「两块功能开关」→ 三块，并注明分组顺序取 `GROUP_ORDER`。

### 测试套件冗余审计 + TUI 菜单 [S] 描述修正（2026-09-15）

**测试套件审计**（AST + 收集器双口径，347 个测试文件）：
- 同文件同体冗余 10 对 → **真冗余 1 对**：`test_tiantian` 的 `test_percentile_only_fallback` 与
  `test_excellent_top_10pct` 同体同义 → 改为 `test_rank_takes_precedence_over_percentile`
  （percentile=90 + rank 5/100 → 优秀），既消除同体又**新增「rank/total 优先于 percentile」覆盖**（依
  `tiantian_ranking` 的矛盾时以排名为准语义）
- 恒真断言 1 处：`test_logger` 的 `assert True` → 改为捕获 stderr 断言无 `Logging error`（可观测结果）
- **判定为非冗余（保留）**：跨文件同体 8 组为并行契约（新浪/腾讯各自归一化、各模块缓存后缀开关），
  每条独立可失败；零断言 37 例经抽样为 `self._assert_*` 辅助断言（检测器假阳性）与 rf-365 已判定的
  有意 no-op/no-crash 边界覆盖；空体用例 0、不可收集测试 0、同类重名 0

**TUI 菜单 `[S]` 描述**：原「配置LLM分析章节」不能概括该菜单（面板实为「配置 LLM 报告章节与功能开关」，
含标准 LLM 模块 + 实验性功能 + 常规开关 + 报告章节与增强共 28 项功能开关）→ 描述改为
「配置功能开关（LLM 分析章节 + 实验性/常规/报告章节与增强开关）」；手册 `how-to-start`（菜单速览）与
`how-to-use-tui-menu`（主菜单总览 + 该菜单项小节标题）同步。

### 管理/用户文档结构与内容核对修正（零断链）（2026-09-15）

- 核对 10 份管理文档 + 10 份手册 + README：提取章节骨架、校验全部相对链接（**断链 0**）、扫描陈旧计数并与代码事实对照。
- 代码侧用户可见文案：`[P]` 主菜单描述去掉已迁走的「报告增强子模块」；`README` 页签计数 20 → **21**（与报告模块注册表的条目数一致）并补「财务指标」提及。
- 用户文档：`how-to-use-tui-menu` 的 `S` 面板「三块 → 四块」并移除写死的块内编号（编号随注册表顺序变化，属易漂移内容）；`how-to-config` 新增「## 目录」、`B` 节补指向 `[S]` 报告块、把「与菜单命令的对应关系」移到文末（恢复 A~P 字母序列连续）。
- 管理文档：`requirements` 修掉机械替换留下的「开关 功能开关」重复 3 处、`R-WEB-08` 功能开关面板块数改三块；`folders` 补「## 项目统计」标题并把文档标题改为「目录结构与项目统计」。

### plan-44 技术债清理（残留引用 / 悬空链接 / 硬编码分组）（2026-09-15）

- 审计 plan-44 落地后的 5 类残留，逐项修复：
  1. **残留引用**：16 个源码文件的注释/docstring 中的 `report_submodules.*` 统一改为「功能开关 `name`」；其中 `crisis_annotation` / `tail_risk` / `snapshot_diff` 三个**并不存在**的开关名属笔误（分别由 `build_crisis_annotation(history_data)` 组装与数据契约名），改为真实表述
  2. **悬空链接**：`plan.md` 中指向未创建设计文档的链接改为指向实施记录
  3. **硬编码分组清单**：TUI `S` 面板由硬编码三元组改为 `GROUP_ORDER` 派生（对齐「渠道层不得另写清单」纪律），并新增 Web 覆盖守卫（面板渲染的开关集合须覆盖注册表全部开关）
  4. **清单同步**：Web 测试白名单清单改裸开关名并补齐 `financial_indicator`（此前缺失）
  5. **陈旧文案**：`technical` 语义命名纪律句与 `data_source_matrix` 说明表备注（用户可见）去掉键名写法

### 报告增强子模块并入功能开关注册表（plan-44 完成，不做兼容）（2026-09-15）

- **决定**：按用户要求**不做 config.json 兼容**——注册表成为唯一真源，config.json 重生成，相关程序同步改。
- **注册表**：新增分组 `GROUP_REPORT`「报告章节与增强」+ 8 条声明（`data_quality` / `market_temperature` 默认开，`industry_beta` / `candidate_compare` / `cost_lots` / `valuation_percentile` / `financial_report_digest` / `financial_indicator` 默认关；`affects_report=True`），注册表 20 → **28 项**；`GROUP_LABELS` / `GROUP_ORDER` / 契约注释同步。
- **真源切换**：`_core.py` 8 个 `is_enable_*` 访问器改为 `is_feature_enabled(<flag>)`（`config` 形参保留但不再参与取值）；`_config_defaults.py` 删除 `report_submodules` 段与模板行；重生成 `data/config/config.json`；**把用户原有非默认取值搬入 `data/config/features.json`**（`valuation_percentile` / `financial_report_digest` / `financial_indicator` = true），8 项行为逐项保持。
- **TUI**：`S` 面板新增「报告章节与增强」块（面板三块 → 四块）；顶层 `P` 面板收敛为 5 个基础报告章节（第 6 项改为「报告增强子模块 / LLM 分析章节 — 请在菜单 S 配置」，输入范围 (0-6)）；删除 `P` 子面板 `_cmd_config_report_submodules` 与其清单常量（面板编号漂移类问题随之消失）。
- **Web**：`config_edit_whitelist` 删除 7 条 `report_submodules.*` 与 `submodule` 写原语；surface `submodules` 改由注册表 `GROUP_REPORT` 派生（键为裸开关名、写入走 `save_feature_overrides`）；前端该块改用注册表 labels 与「影响报告」标记（原 `report_submodules.` 前缀移除）。
- **功能性修复**：`report/_report_factor_metrics.py` 的 `industry_beta` 判定原读 `config.report_submodules`（单源切换后会**永远判关**）→ 改读 `is_enable_industry_beta(config)`。
- **测试**：删除旧的 config 驱动用例，新增注册表真源守卫——组内键集合与默认值、访问器 == 注册表默认、运行时覆盖即时生效、config.json 不再携带该段、Web 白名单无旧路径、写报告开关落 features、`S` 面板含报告块、`P` 子面板已移除；dev-verify 2747/0。
- **文档**：`how-to-config`（删旧 8 行表项、功能开关表 20 → 28 项含新增 8 行、面板布局三块 → 四块、菜单索引改 `[S]` 报告块、配置示例移除该段）、`how-to-use-tui-menu`/`how-to-start`/`faq`/`reports-instruction`、`requirements` 配置表、`technical`（Web 写入分派与说明表口径）、`developer-guide`（语义登记正向校验对象改 `GROUP_REPORT`）、`plan.md`（plan-44 完成，`plan-next` 45）。

### 修复：报告增强子模块面板编号漂移（提示范围写死 + 手册编号错乱）（2026-09-15）

- **现象（用户报障）**：按手册「菜单 P → 7」想开「财务指标」，实际开的是第 7 项「持仓个股财报摘要」；且面板提示写死 `输入编号切换 (0-7)` 而清单已 8 项。
- **缺陷一（手册编号漂移）**：`how-to-config` 开关表里 8 项中有 7 项都写着「菜单 P → 6」（历史遗留：早期清单较短时统一写的编号，后续新增项未同步），仅 `market_temperature` 恰好为第 6 项而正确；新加的 `financial_indicator` 又被写成 7（实为 8）。
- **修复**：手册改为**按名称定位**（「菜单 P → 「财务指标」」）——编号随清单增删漂移、名称不漂移，从根上消掉这一类缺陷。
- **缺陷二（面板提示写死）**：报告增强子模块面板的输入提示 `(0-7)` 硬编码，清单已增至 8 项 → 改为由清单长度派生 `(0-{len(SUBMODULES)})`；同时把该面板清单提升为模块级常量 `REPORT_SUBMODULE_ITEMS`（面板、提示范围与守卫测试共用同一处事实来源）。
- **顺带**：可选章节面板第 6 项原枚举「数据质量/行业Beta/候选比较/成本流水/估值分位/市场温度/财报摘要」漏了财务指标且会继续漂移 → 改为不枚举的概述文案。
- **回归护栏**：新增 `test_handlers_config.py::TestReportSubmodulePanelCoversSwitches` 三例——① 面板清单键集合 == `_DEFAULT_CONFIG["report_submodules"]`（新增开关未补面板即报红）；② 该面板提示范围不得写死、须由清单长度派生；③ 手册须对每个面板项给出「菜单 P → 「名称」」定位（编号漂移即报红）。
- **文档**：how-to-config 开关表 8 行改按名称定位。

### 修复：市场温度缺键回落与默认值不一致（转正遗漏）+ 一致性护栏（2026-09-15）

- **缺陷**：市场温度转正只改了 `_DEFAULT_CONFIG`，未同步访问器 `is_enable_market_temperature` 的**缺键回落值**（仍硬编码 false）——`report_submodules` 八项里唯一一处「默认开但缺键判关」的错位。运行时因 `get_config()` 会与默认值做嵌套合并而不显现，但部分 config 传入的路径（面板/编排部分字典）会出现「配置写明默认开、实际判关」。
- **修复**：`is_enable_market_temperature` 缺键与 `report_submodules` 非 dict 时回落 **True**（与 `data_quality` 同口径），docstring 与 debug 日志文案同步。
- **回归护栏**：新增 `test_config.py::TestReportSubmoduleDefaultConsistency`——逐项断言每个 `report_submodules` 开关的「默认值 == 访问器缺键回落」，并要求存在同名访问器；今后任何开关转正若只改默认值就会立刻报红。
- **测试**：既有「缺键回落为关」的断言改为「回落为开」，另补 `report_submodules: {}` 两态。dev-verify 2757/0。

### 市场温度转正（默认开启，无数据静默省略）（2026-09-15）

- **转正口径**：`report_submodules.market_temperature` 由默认关改为**默认开**。判据取本仓库「读侧增强类开关」纪律——开启的代价基本只在读侧：只在既有产物流水线（「投资分析汇总」章）追加一段由**已算出**数据派生的内容，不新增 LLM 调用次数、不写新的持久化文件；**例外与已知代价**照实记录于下。
- **降噪改动（配套）**：不可用时该行**静默省略**——Excel `summary._write_market_temperature` 与 HTML 汇总章同判据改为「不可用即不渲染」（此前写 `--（数据不足，暂不显示）` 占位）。理由：转正后该行对所有用户默认出现，用户未主动要求的功能不应出现降级痕迹；可用性仍由日志与 `market_temperature_data` 契约（`available=False`）披露。
- **已知代价（照实记录）**：① 该行取数走 `fetch_index_history("sh000300", 750)`，通常命中会话缓存/文件缓存（`index_history_*`）→ **0 次额外请求**；但若本次运行未取过沪深300 且文件缓存冷（如 `enable_history=false`）则 **+1 次指数 K 线请求**。② 该数据进入「信号预消化」块（`信号：市场温度…`）→ `_signal_digest_cache_suffix()` 随之变化 → **升级后首次运行 `expert_review` 与 `health_check` 各重生成一次**（一次性 LLM 费用与耗时，属纪律条文说的预期行为）。
- **顺带修复（会话缓存窗口缩水）**：`fetch_index_history` 的会话缓存条目改为 `(days, bars)`，**仅在缓存窗口不小于本次需求时复用**，否则重取——修掉「某调用者先用短窗口取过，后续要长窗口的调用者（如市场温度 750 天）拿到更短序列」的窗口缩水；旧形态（裸列表）视为窗口未知、沿用既有行为。
- **关闭杠杆保留**：菜单 `P → 6` 或 `report_submodules.market_temperature=false` 仍可回到引入前的报告形态。
- **测试**：+5 例 —— 默认值转正与显式关闭杠杆、不可用静默省略（Excel 两态：`available=False` 与 `None` 均不写行）、会话缓存「窗口足够则复用 / 窗口不足则重取」；既有 3 处会话缓存条目形态断言同步为 `(days, bars)`。
- **文档**：how-to-config（配置示例 + 开关表 + 菜单索引三处）、requirements 配置表（`data_quality` 与 `market_temperature` 默认开、其余 6 项默认关）。

### 配置模板对齐：config.json 补 `data_key_file` 与 `datasink` 段（2026-09-15）

- 显式写入 `data_key_file`（通用密钥文件路径，以 provider 名为节）与 `datasink` 段（`enabled` / `plan` / `requests_per_second` / `daily_quota` / `sections` / `max_chars` / `doc_types: []`），并把 `batch.datasink_workers` 设为 **2**（免费档 3 请求/秒；每标的为索引 + 章节清单 + 正文三次请求）。
- `doc_types` 空数组表示**不限文种**、取最新报告期；密钥文件与持仓文件仍为 git 忽略状态，不入库。

### 修复：财报摘要只取到部分标的且只取年报（章节名 404 + 年报优先）（2026-09-15）

- **现象（用户报障）**：开启「持仓个股财报摘要」后，9 只 A 股标的只拿到 2 只（建设银行 601939、华峰测控 688200），其余含持仓的长江电力 600900 与工商银行 601398 均为「未取到财报」；且拿到的都是**年报**，看不到更新的半年报/季报。
- **根因（日志与实测定位）**：
  * **章节名硬编码裸名**：请求 `/documents/{id}?section=管理层讨论与分析` 对多数文档返回 **HTTP 404**（各公司/文种的实际章节名为「第三节管理层讨论与分析」「五、主要会计数据和财务指标」等，服务端 fuzzy 匹配不一致）——我们据此把**整只标的**判为「未取到财报」（日志：`请求 /documents/27483 返回 HTTP 404`）。
  * **年报优先、命中即止**：索引按 `doc_types` 顺序试取（`annual` 在前），只要有年报就永远不会取半年报/季报；实测同一标的（600900）不限文种取回的**最新一期为 2026-06-30 半年报**（`semiannual`），却被年报遮蔽。
  * **限速 429**：免费档 3 请求/秒，而并发取数（默认 3 worker）叠加索引+正文请求触顶（日志：`触发限速（HTTP 429）`），丢失个别标的。
- **修复**：① **跨文种取最新报告期**——索引改为一次取回最近若干篇（不带 `doc_type`）后本地按「报告期 → 披露时间」倒序取最新一篇；`datasink.doc_types` 语义改为**文种白名单**（默认空数组 = 不限文种）；② **章节按实际清单匹配**——恢复 `/documents/{id}/sections` 端点（`providers/datasink.py::fetch_report_sections`，缓存前缀 `report_datasink_sections_` 并入财报索引模块），按 `datasink.sections` **偏好顺序子串匹配**出精确章节名再取正文；**首选项 404 时继续试下一候选**（不再据此判整只失败）；清单不可得时回退偏好名直取。默认偏好扩为「管理层讨论与分析 → 经营情况讨论与分析 → 主要财务数据 → 主要会计数据 → 董事会报告」，使季报自动落到财务数据章节；③ **限速友好**——429 时退避 1s **自动重试一次**；财报取数并发默认 **3 → 2**。
- **测试**：+13 例——最新报告期优先于年报（半年报/一季报排序）、文种白名单过滤与不匹配返回 None、`_pick_sections` 子串匹配/去重保序/回退、按精确章节名请求、首选项 404 落到下一候选、章节清单缓存、`fetch_report_sections` 端点解析与异常形态；既有「年报优先」断言同步改写。
- **文档**：requirements R-FRD-03（取数口径改写）、how-to-config（`doc_types` 空=不限、`sections` 偏好子串匹配、429 退避）、datasource（数据质量说明：取最新报告期跨文种）、technical §4.19（取数链路）。
- **后续可选项**（未做）：失败原因细分（「无索引」vs「章节不可用」）目前仍统一显示「未取到财报」，可从章节解析结果细化。

### 修复：数据源说明表误报「未使用」（财务指标/财报全文取用标记缺失）（2026-09-15）

- **现象（用户报障）**：运行最新程序后「数据源可用性矩阵」章的「数据源说明（实际使用清单）」表仍把 DataSinking 标为 `○ 未使用`。
- **根因一（配置，非缺陷）**：DataSinking 相关能力**均为默认关的 opt-in**——用户 `config.json` 的 `report_submodules` 只有 `data_quality` / `market_temperature` 为真，`financial_report_digest`、`financial_indicator`、`valuation_percentile` 均为关（前两者甚至未出现在该段，走默认关），因此本次运行**根本没有任何代码路径去调用 DataSinking**，`未使用` 属实。
- **根因二（真实缺陷）**：说明表的 `used` 取自 `DegradationTracker` 事件前缀（`report_datasink_`），而**该域的取数链路从未写任何 tracker 事件**（`providers/datasink.py`、`fetcher/financial_report.py` 均无记录点，与 price/fund/index/industry 各自在 fetcher 层记事件的惯例不一致）——即使用户开启开关并成功取数，也永远显示 `未使用`；同时 `financial_indicator` 域（缓存前缀 `fin_indicator_`）**根本没有类别行**，在说明表中完全缺席。
- **修复**：① 新增 `report/data_status.py::mark_data_used(source_key)`——「本次取用」标记，**只记成功事件、不参与降级计数**（章节名 fuzzy 未命中等预期内空结果若按失败计入 T2 阈值会把预期内空结果误报为源故障；失败与降级仍由 provider 日志、章节失败清单、链路诊断披露），自身不抛异常；② `fetcher/financial_report.py` 在索引与正文**取得数据时**（含缓存命中）标记 `report_datasink_index` / `report_datasink_doc`（`_fetch_index` 的缓存命中、provider 命中与 `_fetch_document` 的链路返回三处）；③ `fetcher/financial_indicator.py` 标记 `fin_indicator_{source_api}`（主源 akshare 与解析支路 datasink_indicator 分别标记）；④ `report/data_source_matrix.py` 新增 `financial_indicator` 类别行（`_SOURCE_CATEGORIES` 与说明表清单同源）并补 `财报全文` / `财务指标` 行的「需开启哪些开关才会取用」备注，同时修订 `used` 语义说明（「取得过该类别数据（含缓存命中）；`未使用` ≠ 源故障」）。
- **测试**：+17 例——`mark_data_used`（记成功事件/不推进降级计数/异常不抛）+ 说明表（新类别行与备注、按前缀判定 used、无关类别不受影响）+ 财报域（索引与正文的取用标记、缓存命中亦标记、未取到不标记）+ 指标域（主源标记、解析支路按 `source_api` 标记、链路段标记、无数据不标记）。

### 设计文档归档与计划状态收口（plan-42 / plan-43）（2026-09-15）

- **计划状态**：`plan-43`（持仓个股基本面数据源主备与财务指标提取）由「设计完成，待实施」转为**已完成**（阶段①②③a③b④ + DataSinking 数据底座门禁；阶段⑤ 文档与门禁收尾随发布执行）；`plan.md` 的 P1 / P4 两区自此均为「无待办项」，编号源 `plan-next = 44` 不变。
- **七次归档**：`docs-stm/plan/` 两份已实现设计文档迁入 `docs-stm/archive/v0.10.x/`——`datasink-financial-report-digest/datasink-financial-report-digest-design.md`（plan-42）与 `financial-indicator-source/financial-indicator-source-design.md`（plan-43）；文档头部状态行改为已实现态，文档间交叉引用、`plan.md` 与 changelog 内的设计文档引用一并改指归档路径，`docs-stm/plan/` 再次成为空目录。
- **归档台账**：`archived_plan.0.10.x.md` 头部「归档时间/涵盖版本/归档内容」三行同步（涵盖范围扩至 v0.10.19），新增小节「P1 — 已完成（plan-42 / plan-43 完成态，2026-09-15 七次合并迁入）」并补「归档说明」条目；`folders.md` 目录树与统计（plan/ 归零、归档 127 文件 / 42,147 行）按实测刷新。

### LLM 侧注入：基本面信号与叙事-数字背离检测（plan-43 阶段④）（2026-09-15）

- **五路确定性信号**：在既有 `signal_pre_digest`（默认开、注入专家复盘与持仓体检、**不新增 LLM 调用**）中新增两路——
  * **持仓基本面**：只读 `financial_indicator_data`，把逐只质量档（优/良/弱）与年度趋势（增长/下滑）聚合成分布；两侧**同向才给方向**，矛盾或无判据判中性（不硬造方向），同行给出平均 ROE；
  * **叙事与数字背离**：`financial_report_digest_data`（管理层讨论与分析摘要）按代码与 `financial_indicator_data` 配对，对摘要做**词频语气**判定（乐观/悲观词表，词表集中为模块常量，不做语义理解）× 指标方向（年度趋势优先，其次归母净利/营收同比，±3% 内持平）；仅在「叙事乐观而数字走弱」或反之时产信号，**列出依据但不下结论**（结论留给模型），最多列 3 只。
- **背离要求行按需追加**：块内出现背离项时追加 `（存在「叙事与数字背离」项：请在结论中显式指出背离点，说明你以哪一侧为准及核实方向）`；**无背离项时该行不出现**（提示词与未引入该项时逐字节一致）。
- **门禁联动**：两路新信号依赖 DataSinking 数据底座（`datasink.enabled` + 凭据）；未就绪时对应契约缺席 → 信号自动缺席（不注入即无感）。
- **缓存同源**：信号块内容进 `_signal_digest_cache_suffix()` 指纹——新增信号即换键，避免「提示词带新信号、缓存还是旧内容」的错配；写侧与预检侧无条件调用同一构建器（开关判定仍收敛在该函数内）。未改写 pipeline_data 契约（附录 H 不变）。
- **测试**：+16 例 —— 基本面信号（分布与方向/弱质下滑看空/矛盾判中性/门禁缺席）+ 背离检测（双向命中并列依据/同向与中性与持平皆静默/仅配对标的不单侧判断/上限截断/契约缺席）+ 块与缓存（合流与要求行、无背离不得出现要求行、指纹随信号变化）。
- **状态**：plan-43 阶段①②③a③b④ 全部完成（结构化指标主源 → 全文解析备用支路 → 财务指标报告章 → 真实 PE/PB 分位（TTM）与数据底座门禁 → LLM 侧信号注入与背离检测）；阶段⑤（文档与门禁收尾）随发布执行。

### DataSinking 数据底座门禁（静默回原样，plan-43 门禁）（2026-09-15）

- **新增门禁**：`config.datasink_feature_ready()` —— 配置位 `datasink.enabled`（默认开）**且**凭据就绪；纯本地判定（零网络请求、零延迟），供依赖该数据底座的分析能力前置检查；新增 `config.is_enable_datasink()` 读配置位。
- **覆盖范围**：财务指标章 + 真实历史估值分位（持仓个股财报摘要本已需 key，形态不变）。
- **未就绪即静默回原样**：财务指标章 `build_financial_indicator` **门禁先于任何取数**（零网络开销）并返回 `None` → 章节整体隐藏、**不写占位**；真实分位 `_fetch_valuation_for_code` 不取指标不算分位，`compute_valuation_data` 置 `basis_mode="proxy_only"` → 估值列文案回到 `分位 45%（合理）`、免责语回到原单口径句（Excel 与 HTML 同一判据，抽取 `penetration_sheet.valuation_footer_note` 单一来源）。
- **就绪时**：财务指标章正常装配；真实分位生效为 `basis_mode="real_ttm"`，估值列标注口径（`真实分位 …（…，PE-TTM）` / 无基本面覆盖回落 `价格分位 …（…，代理）`）。
- **测试**：+9 例 —— 门禁判定（配置位缺省/关闭/凭据缺失组合）、门禁先于取数（零调用断言）、装配层与编排层未就绪返回 None、真实分位未就绪不取数且 `basis_mode=proxy_only`、免责语回原样与双口径两态。
- **文档**：requirements R-FIN-13 / R-VAL-04、how-to-config（`datasink.enabled` 与财务指标章开关行）、technical（门禁判据与 `basis_mode` 契约位、语义表 +1 行）。

### 真实历史估值分位（TTM 口径，plan-43 阶段③b）（2026-09-15）

- **口径升级**：把「价格自身分位」升级为「真实估值分位」——历史 PE/PB 序列衡量贵不贵；无基本面覆盖时回落价格代理并标注口径，**两种口径不得混展示**。
- **TTM 每股收益**（`analysis/valuation_percentile.py`）：年报直取当年 EPS；一季报/半年报/三季报按「上年年报 + 本期累计 − 去年同期累计」差分；所需期数不全 → 该期不产 TTM（不猜）。
- **生效日 = 法定披露截止日**（年报/一季报 4-30、半年报 8-31、三季报 10-31；年报为次年）——**避免前视偏差**：某期数据仅在该日之后的历史价格上生效，绝不用未来财报解释过去价格；同日生效（年报与一季报同在 4-30）按报告期新者胜（否则退化为输入顺序，可能取到更旧口径）。
- **序列与分位**：逐交易日取「该日已生效最新一期基本面」→ PE = 收盘价 ÷ TTM EPS（TTM ≤ 0 即亏损不产）、PB = 收盘价 ÷ 该期每股净资产（非正不产）；分位 = 历史值 ≤ 当前值占比，样本 < 60 判数据不足；**PE 优先、PB 兜底**，`basis` 如实标注。
- **接线**：编排层 `_fetch_valuation_for_code` 增取指标序列（取数/计算异常各自收敛降级，不影响估值行）→ `by_code[code].real` + `real_available`；`penetration_sheet._get_valuation_text` 优先真实分位（`真实分位 45%（合理，PE-TTM）`），回落标 `价格分位 …（…，代理）`；Excel 表尾与 HTML 页脚免责语同步为双口径说明。
- **测试**：+28 例 —— 派生层（TTM 差分四类/披露生效日/排序与同日并列/无前视对齐/PB 时点取值/亏损剔除/分位与档位/各类降级）+ 边缘（脏值基本面/非正与不可解析价格/生效日含边界/空序列）+ 接线（真实分位注入 by_code、无基本面回落、取数异常收敛）+ 既有文案断言同步。

### 财务指标报告章（plan-43 阶段③a）（2026-09-15）

- **新增「财务指标」独立章**：持仓 + 穿透 A 股基本面（Excel 页签 + HTML `partials/financial_indicator_section.html` + 导航「基础信息」组），开关 `report_submodules.financial_indicator` 默认关、数据驱动（无数据隐藏/写占位），不改变既有章节输出。
- **取数**：`fetcher/financial_indicator.py` —— 多期序列**主源一次调用**（akshare），主源不可用时**退化为链路单期**（解析支路只能给最新一期，**不伪造历史期**）；缓存前缀 `fin_indicator_hist_` 归入 `fin_indicator` 模块；非 A 股不发请求。现价经 `collect_price_map` 取自行情明细。
- **派生（纯计算层）**：`analysis/financial_indicator.py` —— 质量档（ROE/毛利率/资产负债率/经营现金流对净利覆盖 四维阈值各 0~3 分后均值分档 优/良/中/弱；**缺维度跳过而非按 0 分**、脏值不参与、**非投资建议/非评级**）、年度趋势（仅比较相邻两个**年报**，避免把季报累计值当年度值；±3% 内为持平；两指标方向不一致记「波动」）、当前 PE/PB（亏损或净资产非正留空）、趋势点截取。
- **装配与呈现**：`report/financial_indicator.py::build_financial_indicator`（管线契约 5 键；全部失败时保留失败清单）+ `report/financial_indicator_sheet.py`（金额亿元、比率百分数、缺失写「—」）。
- **接线（与「持仓个股财报摘要」同构）**：config 开关与访问器、章节注册（type=`financial_indicator`、data_flag=`financial_indicator_data`、number 20；llm_usage 顺延 21）、`pipeline_data` 键表/类型表/附录 H、Excel 工厂与写页签、HTML 导航分组与模板 partial、编排层（`prepare_report_data` 与 both 路径各自构建）、TUI 配置菜单（8 项子模块）。
- **测试**：新增 70 例 —— 分析层派生（`test_financial_indicator.py` 26 例）+ 边缘（`test_financial_indicator_edge.py` 20 例，`*_edge.py` 隔离）+ 装配/开关/接线（`test_financial_indicator.py` 报告层 17 例）+ 页签（`test_financial_indicator_sheet.py` 4 例）+ 多期取数层（`test_financial_indicator.py` 取数层 7 例）；同步更新既有断言（注册表 21 项、类型集合、HTML 章节数 21、双端章节一致性夹具、场景全类型集合）。
- **口径声明**：质量档为**启发式通用阈值分档**（不区分行业），PE/PB 为**当前值**；历史 PE/PB 分位（TTM 口径）属阶段③b。

### 财务指标全文解析备用支路（`datasink_indicator`，plan-43 阶段②）（2026-09-15）

- **实测推翻原设计前提**：DataSinking 的 Markdown **不保留表格**（PDF 报表被压平为「标签紧连数字」的整段正文，如 `...营业收入86,241,940,222.2084,491,870,566.52...`），且不存在 `主要会计数据与财务指标` 章节（该名 404）；指标实际在**第二节「公司简介和主要财务指标」**（别名 `主要财务指标` 命中共章），季报为「主要财务数据」。据此**修订设计文档 §5**（新增 §5.0 前提修订）：解析策略由「读表格」改为「锚点 + 前若干数值」，并把解析**收窄到该章节**（报表正文存在附注编号与金额粘连的误读风险，收益低于风险）。
- **纯解析层**：新增 `analysis/financial_indicator_extract.py` —— 锚点表（营收/归母净利/经营现金流/基本每股收益/加权 ROE，含「归属于母公司股东」旧式行文）+ 否定环视排除「扣除非经常性损益后的…」同口径干扰 + 有限取值窗口（超窗判为跨行、弃用）+ 按报告期精度选数值模式（金额两位小数、每股四位、比率两位，避免 `1.41011.3281` 无分隔连写误切）+ 金额单位换算（取锚点前最近「单位：X」，**无声明即不产金额**）+ 逐字段幅度/区间校验；同比由本期/上年**同口径**两值算术派生。报告期/文种一律由元数据给出。
- **解析适配器**：`fetcher/financial_indicator_adapters.py` 新增 `DataSinkIndicatorAdapter`（`datasink_indicator`），**逐章节试取、命中即止**（避免同一章节被多个别名重复取回白耗配额）；取数经既有 `fetcher/financial_report.py` 链（复用其缓存/限速/配额/熔断，**不另建 HTTP 通道**）。
- **链路**：`financial_indicator: [akshare_financial, datasink_indicator]`（主源失败落解析支路）；配置校验放行新源名 `datasink_indicator`。
- **覆盖面（诚实边界）**：解析支路提供营收/归母净利/营收同比/净利同比/经营现金流净额/基本每股收益/ROE 共 7 项；毛利率、资产负债率、每股净资产**不在该章节**，恒为 `None`（由主源 akshare 提供）。
- **实测复核**：新增真实正文夹具 `src/test/data/fixtures/datasink_indicator_section_600900.md`（长江电力 600900.SS 2025 年报该章节全文，附 `README.md` 记来源与核对值），逐字段复现披露值——营收 86,241,940,222.20 元、归母净利 34,502,809,176.39 元、经营现金流 60,562,925,570.41 元、EPS 1.4101 元/股、ROE 15.90%、同比 2.07% / 6.17%。
- **测试**：`test_financial_indicator_extract.py`（真实夹具回归 + 行文变体/单位/精度/扣非排除/降级）+ `test_financial_indicator_extract_edge.py`（窗口边界/异常幅度/越界比率/零基数同比/截断正文，`*_edge.py` 隔离）+ `test_financial_indicator.py` 扩充（链路顺序、落解析支路且源身份为 `datasink_indicator`、逐章节试取、非 A 股不发请求、双源皆失败返回 None）。

### 结构化财务指标数据域（`financial_indicator`，plan-43 阶段①）（2026-09-15）

- **新增数据域与契约**：`financial_indicator` 域 + `FinancialIndicatorFields`（营收/净利/同比/毛利率/ROE/负债率/经营现金流/EPS/每股净资产；金额单位元、比率为小数比例、可选数值缺失取 `None`），登记 `DOMAIN_RECORDS` 并纳入适配器契约自检。
- **主源 provider**：`providers/akshare_financial.py` —— 一次 `stock_financial_abstract` 取回宽表（指标 × 报告期），归一为每报告期一条标准记录；百分数（ROE/毛利率/负债率/同比）换算为小数比例；同名指标多分组按表格顺序首个非空为准；非 A 股/未安装/超时/空表返回空。
- **适配器与链路**：`fetcher/financial_indicator_adapters.py::AkshareFinancialAdapter`（标准字段直出，无需 alias）+ 新链 `financial_indicator: [akshare_financial]`；取数复用 `fetch_with_fallback`（缓存/熔断/降级），缓存前缀 `fin_indicator_`（一月 TTL、基础类）；配置校验放行新数据类型/源名。
- **共享原语收敛（去重）**：A 股→FMP 符号映射统一为 `core/code_utils.py::to_fmp_symbol`（原在 datasink 内，现两个数据源共用）；akshare 取数超时封装统一为 `providers/_utils.py::run_with_timeout`（由 `akshare_extras` 抽出，避免第二份副本）。
- **测试**：新增 `test_akshare_financial.py`（宽表归一/百分数换算/同名指标优先与逐期补齐/文种映射/各类降级，15 例）与 `test_financial_indicator.py`（适配器登记与自检/标准字段集/链注册/链路取回与降级，5 例）；`TestFmpSymbol` 随函数迁移至 `test_code_utils.py`（unit_core）。
- **口径**：本阶段仅数据层（无报告消费）；真实 PE/PB 估值分位、质量因子与 LLM 注入属后续阶段（见 `docs-stm/archive/v0.10.x/financial-indicator-source/financial-indicator-source-design.md` §13）。

### DataSinking 财报接入·数据层（plan-42 阶段①②③）（2026-09-14）

- **凭据**：`CredentialSpec` 扩展 `key_file` / `key_field` / `key_section` / `key_file_setting`，就绪判定支持「环境变量或密钥文件」（环境变量优先）；新增 `credential_value()` 取值接口，就绪矩阵增「来源类型」与密钥文件路径，**值永不回显**。密钥文件通用化：新增顶层路径键 `data_key_file`（默认 `data/config/data_key.json`），文件**以 provider（source_id）为节**（如 `{"datasink": {"api_key": "..."}}`），一个文件容纳多个数据源的 key；纳入绝对化与测试隔离。
- **provider**：新增 `providers/datasink.py` —— DataSinking 全文本财报（`/documents`、`/documents/{id}`、`/documents/{id}/sections`）；A 股 6 位代码 → FMP 符号映射；**计划感知限速**（间隔 = 1/每秒上限，免费 3 请求/秒、付费 31，由 `datasink.plan` / `requests_per_second` 派生）在**每次 HTTP 请求前** `RateLimiter.acquire`（免费档无批量端点、必然逐篇请求，限速必须落在本层）+ **日配额护栏**（`data/state/datasink_quota.json`，免费 8,191 篇/日，超限即停）；401/429/非 200/网络不可达均返回空并按代码级降级（不计传输级熔断）；凭据值不落日志。
- **契约与链路**：新增数据域 `financial_report` 与标准字段记录 `FinancialReportFields`（登记 `DOMAIN_RECORDS`）；新增 `fetcher/report_adapters.py::DataSinkReportAdapter`（上游 `id` → 标准 `doc_id`，契约自检通过），登记 `ADAPTER_MODULES`；新增默认链 `financial_report: ["datasink"]`；缓存注册 `report_datasink_index_`（两周）/ `report_datasink_doc_`（一月）；数据源可用性矩阵新增「财报全文」类别；配置校验已知类型/名称放行 `financial_report` / `datasink`。
- **测试**：新增 `test_datasink.py`（26 例：符号映射/套餐限额派生/凭据缺失跳过/请求前限速与配额护栏/401·429·非 200·非 JSON/取数原语）；`test_datasource_credential.py` 增密钥文件 8 例（就绪/环境变量覆盖/空值与损坏/配置路径覆盖/取值不回显）；适配器自检用例改为断言域覆盖而非写死总数。dev-verify 2602 passed / 0 failed。
- **章节装配（阶段④a）**：新增 `fetcher/financial_report.py`（A 股标的收集含去重与穿透合并；元数据按年报→半年报顺序取最新一篇并缓存；单篇正文经链路 + 财报域适配器归一；摘要按 `datasink.max_chars` 截断）与 `report/financial_report_digest.py`（`financial_report_digest_data` 契约：`available`/`rows`/`failures`/`entry_count`，含文种中文标签与披露日换算；缺凭据/无 A 股标的/全部无覆盖均降级不抛异常）。新增 `datasink` 配置段（plan / requests_per_second / daily_quota / sections / max_chars / doc_types）与 `batch.datasink_workers`。新增测试 14 例。
- **渲染接线（阶段④b）**：注册表新增章节 `financial_report_digest`（type=`financial_report`、data_flag=`financial_report_digest_data`、页签名「持仓个股财报摘要」）；新增开关 `report_submodules.financial_report_digest`（默认关）与 `is_enable_financial_report_digest`；pipeline_data 契台登记（`pipeline_data_builder` 三处 + technical.md 附录 H）；Excel 自动建页签与写盘（`report/financial_report_sheet.py`）、HTML 章节 partial（`partials/financial_report_section.html`）与目录分组；both/full 双路径均按开关注入契约。新增页签测试 3 例；同步更新写死章节数/类型/分组/契约的既有用例（注册表 20 项 + 新 type）。
- **配置与入口补全**：`report_submodules.financial_report_digest` 接入 TUI 菜单 P 子菜单（第 7 项）与 Web 配置面板白名单，用户无需手改 config.json 即可开启；`batch.datasink_workers` 由财报摘要装配层消费（`ThreadPoolExecutor` 并发取数，默认 3，免费档批量上限 ≤3；每秒速率仍由 provider 限速器逐请求兜底）。
- **数据源说明表**：「数据源可用性矩阵」章在健康度表后新增「数据源说明（实际使用清单）」表——逐数据类别列出实际链路（如财报全文=DataSinking）、用途、计费（免费/免费档/付费档，财报全文随 `datasink.plan` 动态展示）与凭据要求（是否需 key + 就绪状态），并标注本次运行是否实际使用（观测到 DegradationTracker 事件即为已使用）。Excel（旧样式页签与数据质量仪表盘两路）与 HTML 同步渲染，`build_data_source_catalog()` 输出契约。
- **状态**：plan-42 全部完成——数据层（①②③）+ 章节装配（④a）+ 渲染接线（④b）+ 文档同步（⑤：requirements §6.12 R-FRD-01~07、technical 附录 H 与 §4.9/§6.7、datasource 两册、how-to-config、folders）。

### 测试用例审计与修复（rf-365）（2026-09-14）

- **审计口径**：333 个测试文件（`src/test/unit|scenario|integration`，`live/` 为 opt-in 排除）AST + 收集器全量扫描，按「无效（名实不符且无断言）/ 死（空体、同类重名、未收集）/ 冗余（AST 完全相同、同类同函数号）/ 目录语义（导入包 vs 目录期望）/ 命名与内容」五维盘点。
- **官方门禁**：`check-test-markers.py --ci` 通过（无漏标、无 `_edge.py` 混放、无失效标记）；无无条件 `skip`；无同类重名；`live/` 未收集属 opt-in 设计而非死用例。
- **修复（rf-365）**：6 例无效用例补真断言（`test_set_write_error_logged` 断言告警内容；`test_llm_api_base::TestLogTokenUsage` 4 例改 `assertLogs/assertNoLogs` 断言输入/输出/缓存命中并补 empty 分支；`test_handlers_cache::TestCmdCleanupCache` 2 例断言委托调用与等待按键；`test_html_report_structure_edge` 断言 2 处导航锚点模板）；删 1 例空体死用例；删 `test_llm_utils::TestLogTokenUsage` 冗余类（与 api_base 重复）；`git mv` 分类测试至 `unit/core/` 并改标 `unit_core`。新增回归守护 `test_test_quality_regression.py`（静态禁止空测试体）。
- **保留（有意）**：18 例「不抛异常/no-op」弱断言测试（如 `SilentProgressReporter` 四个 no-op、空范围 no-crash、live 录制辅助）经逐例审阅为有意边界覆盖，不强制补断言；`unit/core` 与 `unit/cache` 的缓存测试拆分、`unit/analysis/test_bond_yield*` 走 fetcher 网关两处目录语义为历史布局，已记录待后续评估。
- **统计刷新**：`folders.md`（测试代码 364/106,414、测试用例 6,991）与 `test-coverage.md`（bench 回填模式表 + 收集分组：报告生成 1828、核心基础设施 1210、unit_llm 954、unit_scripts 204、跨类 llm 750）同步。

### bench 全量计时与 integration 契约修复（rf-364）（2026-09-14）

- **bench 全量跑**：`test-runner.py --mode bench --update-docs` 依次跑 14 个模式并回填 `test-coverage.md`（模式对应测试量 + 采集环境属性 + 各模式耗时对照，dragonball 采集日期 2026-09-14）。本机各模式耗时（worker=8）：unit ~17s / standard ~18s / scenario ~20s / dev-verify ~27s / verify ~15s / integration ~19s / edge ~14s / all ~26s。
- **暴露并修复真实回归（rf-364）**：bench 的 `all` / `all_no_unit` 报 2 例失败——`test_report_chapter_consistency.py` 的「全开」镜像未带新章节 `financial_report_digest` 的 board/data 参数（Excel 少一页签、HTML 该章节不可见）。该套件为 `integration` 标记、不在 dev-verify 门禁内，故此前未暴露。修复：为 `_excel_visible` / `_html_visible_keys` 与两个 all-enabled 用例补 `financial_report` 开关与 `financial_report_digest_data` 参数，并在「全开」场景显式启用。
- **复跑**：`--mode all` **6982 passed / 0 failed**（含 12 skipped）；`test-coverage.md` 散文字面日期（两处采集说明与示例耗时）同步为 2026-09-14。

### 数据源与统计快照刷新（datasource.md / folders.md / test-coverage.md）（2026-09-14）

- **datasource.md**：DataSinking 行补两级缓存前缀（`report_datasink_index_` 两周 / `report_datasink_doc_` 一月）；新增「财报全文（DataSinking）」路由小节（鉴权/取数/限速配额/仅 A 股符号映射）；数据质量说明与常见问题各增一行。
- **folders.md**：统计表按实测刷新（主程序 276 文件/68,852 行、HTML 模板 5/3,999、测试代码 363/106,356、测试用例 6,994、用户文档 11/5,114、项目文档 133/51,292、代码合计 305/80,340），主程序说明补 5 个新模块；目录树经校已含全部新文件。
- **test-coverage.md**：收集快照同步（功能域与单元分组：数据源 Provider 303 / 数据获取调度 371 / 报告生成 1861 / 核心基础设施 1178 / unit 父标记 6681 / unit_scripts 203；报告测试文件 89），源模块清单补 `datasink` / `financial_report` / `report_adapters` / `financial_report_digest` / `financial_report_sheet`。计数以 `scripts/collect-test-coverage.py` 实时输出为准。

### 过去 96 小时实现审计整改（技术债 + 文档漂移，rf-358~rf-362）（2026-09-14）

- **代码债**：删除 `providers/datasink.py` 的两个新增即死函数（`fetch_report_sections` / `quota_remaining`，仅定义+单测、无生产消费者）；`datasink.sections` 由「列表只取首项」改为**多章节顺序拼接**（逐章节取正文、每节独立缓存、空行分隔）；数据源说明表的前缀改从 `_SOURCE_CATEGORIES` 派生（`_CATEGORY_PREFIXES`）、计费文案改由 provider 新增 `billing_description(plan)` 生成（数字同源 `_PLAN_LIMITS`），消除前缀/套餐数字两处重复。
- **文档漂移**：DataSinking 接入后「全部数据源免费、声明表为空」描述已过时——同步修正 `core/datasource_credential.py` 模块 docstring 与注释、`config/features.py` 开关注释/描述、`core/doctor.py` 与 `core/check_sources.py` 回退文案、`technical.md` §2.7（标题由「实验：默认关」改「常规开关默认开」+ 正文补密钥文件/节名）、`requirements.md` §5.8（R-CRD-01/02/03/06/07 补 `key_file`/`key_field`/`key_section` 与解析顺序）、`how-to-config.md` 两处；对应 3 个测试断言文案同步。
- **用户文档与覆盖**：`README.md`「最多 19 个条件页签」→ 20 并补「财报摘要（可选）」与 DataSinking key 说明；`testplan.md` §4 增财报取数 P1 回归行；`technical.md` 增 §4.19「持仓个股财报摘要」叙述章节。
- **门禁**：dev-verify 全绿；四个 `--ci` 检查 exit 0；ruff check + format 零告警。自审记录 rf-358~rf-362（`rf-next` 363）。
- **任务编号纪律收紧（rf-363）**：`check-code-traces.py` 原先在 `src/test/` 对「回归…」整行与「rf-N 修复」两条予以豁免，使测试注释/docstring 可残留任务编号（共 7 处）。现改为 **任务编号硬禁止且先于整行豁免判定**（`scan_file` 用 `_TASK_ID_RE` 检出 rf-/plan-/R- 编号即报 CODE），删除 `TEST_META_EXCLUDE` 的 `rf-…修复` 条；7 处测试注释/docstring 清理为纯回归语义措辞；检查器测试同步（+2 例硬检出、改写 1 例豁免断言）；CLAUDE.md 补注「测试元描述豁免不适用于任务编号」。

### 修复：QDII 联接穿透被旧缓存遮蔽 — 持仓缓存载荷语义版本（rf-357）（2026-09-14）

- **背景（用户报障）**：另一台机器运行报告仍报 `016055` / `040046` 持仓报告期陈旧（`2023-09-30` / `2022-12-08`）、已按持仓不可用处理、未计入穿透 TOP10。定位于 v0.10.18 的 QDII 联接穿透修复（`d02e32e0`）**只改代码、未让旧缓存失效**：修复前写下的 `fund_hold_*` 条目无 `feeder_target_code`，新代码读到时无法穿透，旧载荷「有持仓 + 早期报告期」直接撞上时效闸门——`hold` TTL 为 7 天，旧条目过期前修复被全程遮蔽（提交当时已注明「需立即见效时 `--clear-cache`」，但该依赖用户手动，属真实缺口）。
- **修复（语义版本 + 读侧准入）**：provider 产出经 `fetcher/fund.py::_stamp_hold_schema` 盖 `hold_schema` 版本字段；读取侧以 `_is_current_hold_payload` 为准入判据，版本不符视为未命中。判据接在**两处**读缓存接缝：① `fetcher/chain.py::fetch_with_fallback` 新增 `cache_validate` 参数（覆盖新鲜命中与过期降级条目，不符即清缓存重取）；② 批量预检回调 `_hold_cache_check`（`execute_with_cache_check` 命中会跳过任务，判据若只挂在链路内则热缓存下失效）。顺带移除 `fetch_fund_holdings_batch` 内冗余的局部 `cache_get`/`get_ttl` 导入（模块顶部已有，局部导入使与 `fetch_with_fallback` 的 `cache_validate` 无法在测试中一致打桩）。
- **效果**：此类「改变载荷含义、不变键结构」的修复从此自失效，不再依赖用户手动清缓存；另一台机器 `git pull` 后首次运行即自动丢弃旧条目并重取。
- **回归测试**：`test_chain.py` 增 3 例（准入判据放行/拒收旧载荷并清缓存重取/拒收旧语义过期降级条目）；`test_fund.py` 增 `TestHoldPayloadSchema` 5 例（盖章、判据准入、旧载荷重取并盖章、当前载荷命中不重取、批量预检拒收旧载荷）。fetcher 两文件 89 passed / 0 failed。
- **文档**：`technical.md` §4.9 补「持仓缓存载荷语义版本」机制、§6.7 语义命名表增 `hold_schema` / `cache_validate` 两行、§8.2 补「缓存载荷语义版本」词条外设计规则；本 changelog 与 `review-findings.md` rf-357。

### 项目级 pi 配置入库（`.pi/settings.json`）（2026-09-14）

- 新增 `.pi/settings.json` 并纳入版本控制，压掉更新日志面板的启动期闪屏：`collapseChangelog: true`（What's New 面板折叠为一行）、`quietStartup: true`（隐藏启动 header）、`tuiMode: "fullscreen"`（viewport 由 pi 自持，避免终端 scrollback 大段重排）、`terminal.clearOnShrink: false`（保留默认；文档标注其可致闪屏）。
- **生效前提**：`.pi/` 属「需信任的项目资源」——首次启动会要求信任该项目，未信任时整份项目设置被忽略（回退全局）；`/settings` 面板切换写的是全局设置，仅本文件为项目级。`--tui-mode` 启动参数优先级最高，会盖掉本设置。
- `folders.md` 目录树同步新增 `.pi/settings.json` 条目。

### 发布后自查整改：多币种换算口径校正 + 脚本约定守护（rf-354 ~ rf-356）（2026-09-13）

- **背景**：发布 v0.10.19 后复盘近 96 小时的实现，发现三处遗留债——一处是 rf-350 明确标记「待用户确认」的能力口径失配，两处是脚本约定只写在文档、无任何校验环节。
- **rf-354 多币种换算口径校正（按实现改写文档与测试，不新增汇率功能）**：`faq.md` 原称「港股通和非 A 股品种的汇率换算由数据源接口自动处理」；`testplan.md` 的 T8 场景列「美元份额币种转换」、T19 场景为「汇率中间价故障」、数据正确性验证表列「多币种转换正确：美元份额 × 汇率中间价 = 人民币市值 ✅」；测试侧 `test_data_integrity.py` 第 4 项与 `TestMultiCurrencyConversion`、`test_market_value.py::TestCurrencyConversion` 亦按汇率换算命名。核对实现：**全仓无任何汇率取数或换算**——`get_currency_by_code` 只做币种分类（5 位纯数字→HKD、QDII/海外基金/美股指数→USD、其余→CNY），`fx_exposure.py` 只按币种汇总市值与占比，`market_value.py` 无汇率分支，QDII/场外基金的净值本身即以人民币计值（相关断言为 100 份 × 2.5 = 250.0），情景分析的「汇率情景」是假设 ±5% 对非人民币占比的估算。处置：四处口径按实现改写（`faq.md` 明确「程序不做汇率换算」并补币种分类规则与港股通换汇成本提示；`testplan.md` T8 删跨境币种换算、T19 改为真实且已覆盖的「场外品种净值日期非 T 日」场景、数据正确性表该行改为「非人民币计价品种市值核算（价格 × 份额，不做汇率折算）」并补 `test_market_value.py` 载体；两个测试类更名为 `TestForeignDenominatedMarketValue`，docstring 改述实现，**断言不变**）。需求 §6.10 只承诺「币种判定 + 市值占比 + 标注 + 注入」，与实现一致，未改。
- **rf-355 `scripts/*.ps1` 行尾归一 + 回归守护**：`cli.ps1`、`launch.ps1` 为 UTF-8 with BOM 但**通体 LF**，与 `.editorconfig` 的 `[*.ps1] end_of_line = crlf` 及 CLAUDE.md 的「BOM + CRLF」约定不符（新写的 `llm.ps1` 反而合规）——两文件行尾归一为 CRLF（BOM 保留）。
- **rf-356 `scripts/*.sh` 可执行位入索引 + 回归守护**：仓库 `core.fileMode = false`，工作区权限不被跟踪，`cli.sh` / `launch.sh` / `llm.sh` 在索引中均为 `100644`——新克隆的仓库里 `./scripts/llm.sh` 报 permission denied，而 CLI 手册 / 开发者指南 / 变更记录均按可执行方式调用（且声称「llm.sh 置可执行位」）。处置：`git update-index --chmod=+x` 将三个 `.sh` 的索引权限置为 `100755`，`llm.sh` 工作区权限由 777 归为 755。
- **回归测试**：新增 `src/test/unit/scripts/test_script_encoding.py`（`unit_scripts` 标记，4 例）——`scripts/*.ps1` 逐文件断言以 BOM 开头且不含裸 LF（无 BOM 时 Windows PowerShell 5.1 按 GBK 误读中文注释而解析崩溃）；`scripts/*.sh` 断言 git 索引权限为 `100755` 且工作区可执行（非 git 工作区 / Windows 自动跳过）。

### 开发版本切换（2026-09-13）

- 发布 v0.10.19 后，按既定流程将 `APP_VERSION` 与全部管理文档版本头切换至 v0.10.20-dev，`check-version-consistency.py` 全链 [OK]。

### 已发布版本变更记录归档（v0.10.19 → archived_changelog）（2026-09-13）

- **归档**：发布 v0.10.19 后，按「已完成即归档」口径将本文件 [0.10.19] 已发布版本变更记录整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（接于 [0.10.18] 之后，保持版本升序）；本文件自此仅保留在开发版本 [0.10.20-dev] 的章节与归档引用。
- **同步**：归档文件头部「涵盖版本」扩至 v0.10.1 ~ v0.10.19、「归档内容」改指开发版本 [0.10.20-dev]；`folders.md` 项目文档/归档统计按实测刷新。
- **口径**：发布版本与开发版本分开存放——已发布版本的完整变更记录只在归档文件，本文件只描述尚未发布的工作。

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
