# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.3-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 需求 ID 追溯链（rf-426）：批 2~6 完成 —— 276 条需求全量映射 + 门禁转全量断言（2026-09-24）

**批 2（38 条）**：`R-ERR` 错误与降级可视化（备用链路/过期缓存/占位文本两态区分/快照无历史）、`R-DIAG` 诊断三面（CLI `view-logs`+`doctor` / TUI `[V]`/`[H]`/`[D]` / Web `/api/logs`+`/api/health/history`+`/api/doctor`）、`R-BRK` 熔断治理（单股 3 次/批量 6 次·120s、空数据不计、LLM 独立熔断、会话缓存 2000、指数退避、`data/state` 持久化、网关统一双熔断器）、`R-CRD` 凭据声明式（`CredentialSpec`/就绪判定/可读指引/链路跳过不进熔断/跳过态/体检分组/值不外泄/开关逐字节等价）

**批 3（37 条）**：`R-FIN` 财务指标域（标准字段契约/akshare 主源/链路接入/`to_fmp_symbol` 收敛/底座门禁/降级不阻断/PE-PB 官方口径/报表派生/全文解析支路/解析护栏/双端区块/多期序列/管线契约/真实形态夹具）、`R-FRD` 财报摘要（开关/密钥文件/最新报告期/限速与日配额/占位与失败清单/合规来源/缓存分级）、`R-NWS` 新闻（5 源独立取数/关联度排序/关键词来源/颜色分型/独立启停/LLM 二次关联）、`R-DATA` 数据治理（备用链路/静默降级/会话复用/盘中 30s TTL/收盘 `price_date` 校验/00 代码判定）、`R-IDX` 指数双链路（A 股腾讯→新浪、美股新浪→腾讯、降级过期缓存）

**批 4（71 条）**：`R-OUT` 产物路径与格式（根/存档目录、文件名、页签 1~17、单页 HTML+TOC、`report_section_order`、LLM 用量页签固定末位、条件渲染两层、深浅主题）、`R-PERF` 性能（5 源并行、LLM 并发、批量异步取价、配置 mtime 缓存、提示词精简、会话复用、历史增量、阶段超时、耗时记录、后台健康检查）、`R-WIF` 调仓模拟（CLI/TUI 入口、变动类型、成本截面、分类对比、双产物、零网络默认、生效日回测 5 指标、降级）、`R-ACT` 行动建议（章节与开关、`action_data` 契约、再平衡信号、占位、关闭不渲染）、`R-RBL` 再平衡（阈值与预设、静默期持久化、置信度、三类误报防护、注入 LLM）、`R-VAL` 估值分位（TTM EPS 构造、披露截止日、分位口径、底座门禁）、`R-TAIL` 尾部风险、`R-EVO` 组合演进、`R-SNP` 快照（自动创建/隔离/保留策略/对比）、`R-CFL` 成本流水（XIRR/快照近似/开关/列）、`R-DIFF` 快照差异摘要

**批 5（25 条）**：`R-LLM`（L 菜单触发、模块独立启停、三类协议 + 厂商路由、递补降级、用量统计、4 切换策略、凭据分离、失败原因追踪、信号预消化含叙事-数字背离）、`R-PF` 景气度框架（实验开关逐字节等价、六维评分卡、客观化口径、两项扩展标口径、缺失标 `unverified`、评级口径、双端呈现位置、`evidence` 可核对、配置）、`R-CTX` 竞争语境（`comparison_indices`、收益/风险对比、口径脚注、幸存者偏差提示、LLM 仅陈述、基金池 TUI 管理）

**批 6（66 条）**：`R-WEB`（回环启动、上传校验、格式选择、事件流进度、预览下载、单 worker 队列、生命周期、配置编辑面板、试算/正式隔离）、`R-TUI`（标题、20 选项、缺省选中 `[L]`、选择器、进度提示）、`R-ENV`（Python 实现、双平台启动脚本、双平台 Web、`cli.sh`/`cli.ps1`——启动脚本项含手工验收）、`R-HLD` 持仓格式（页签=账户、4 列、列名/顺序固定、代码去前缀）、`R-DIS` 交易纪律（止盈/止损/回撤三线、静默期复用、配置段）、`R-LIQ` 流动性（变现天数、场外赎回上限与类型默认档、数据缺失默认充足、注入 LLM、场内分级、OTC/非 A 股标记）、`R-FX` 汇率敞口、`R-CON` 健壮性（key 未配置/config 损坏/格式异常/无权限/空持仓/模块独立降级/断网降级/降级可视化）、`R-ADP` 适配器三段式契约（声明式归一、输出恒为全字段、链路接入、试点等价性、开关逐字节、离线自检）、`R-HST` 历史数据（双链路、增量合并、修正全量刷新、模式 off/prompt/auto、00 代码降级、基准指数链）

**收尾**：`_COVERED_DOMAINS` 扩至 **34 域**（与 `_ALL_DOMAINS` 一致，R-PEN 为不存在的域已移除），门禁由「已补域全覆盖」转为**全量断言**；测试新增真实仓库全量对照（需求侧 276 条 ID ↔ 映射表 276 行逐条相等）；`review-findings.md` 的 rf-426 由「待处理」迁入「已解决」。

### 需求 ID 追溯链（rf-426）：批 1 R-CCH 缓存域完成 + 新增追溯断言脚本并入门禁（2026-09-24）

**背景**：`requirements.md` 定义 276 个需求 ID（34 域），但 testplan / technical / llm-technical 对其引用数为 0——无法机器回答「某需求是否有测试覆盖」。交付形态定稿为「映射表落 `testplan.md` §2.1」（按需求 ID 组织、含验证载体列、`<!-- requirement-trace:start/end -->` 标记区间）。

**批 1（R-CCH 缓存域 38 条）**：
- §2.1 新增 38 行映射，覆盖：缓存机制（01 磁盘缓存 / 02 gzip 100KB 阈值 / 03 目录穿越防护 / 04 原子写 / 05 损坏自愈）、缓存键清单（06~33 各数据域 TTL 与前缀分组）、输入摘要与依赖失效（34 确定性摘要 / 35 指数行情→预测与资金流向 / 36 持仓+穿透代码→分红 / 37 新闻源+关键词→新闻 / 38 持仓份额成本→LLM）
- 载体精确到用例级（如 `test_cache_format.py::test_large_file_auto_gzipped`、`test_holdings_tracker.py::test_different_shares_different_fingerprint`）

**新增 `scripts/check-requirement-trace.py`（复用 `_checklib`）**：五项断言——① 映射表标记与表头齐备（防整表误删）；② 映射 ID 均存在于 requirements.md（防臆造/拼错）；③ ID 唯一（防两行矛盾）；④ 已补全域 ID 全覆盖（防「补了 37 条漏 1 条」）；⑤ 载体列中的 `src/test/**/*.py` 路径真实存在（防测试改名后文档悬空）。**分批推进**：常量 `_COVERED_DOMAINS` 记录已补全域，每批追加一项即扩大断言范围；`_ALL_DOMAINS`（34 域）用于进度显示。已并入 P0 + P2 门禁（CLAUDE.md / testplan §6 / developer-guide）。

**测试**：`src/test/unit/scripts/test_check_requirement_trace.py` +16 例（解析 4 / 断言 8 / 真实仓库 3 / 空输入）；真实仓库冒烟断言 38/38 已映射且载体文件全部存在。
**顺带修正**：testplan §6 门禁行早前追加枚举时多出一个右括号。

### 用户文档 vs 管理文档比对：修手册 thinking 章节漏 Kimi + 新增矩阵守卫（2026-09-24，rf-427）

**背景**（用户要求）：比对 `requirements.md` + `technical.md` + `llm-technical.md` 与用户文档（README + 10 份手册），冲突处回查代码。

**判定为冲突（已修）**：`how-to-config-llm.md` 的 Extended Thinking 章节**内部自相矛盾**——支持矩阵 bullet 已含 Kimi，但「模型差异」对比表只有 3 列、且 601/608 行写「**仅**在使用 Claude 或 Gemini 模型时 `thinking_budget` 有意义」；而代码（`_THINKING_SUPPORTED_PREFIXES` 含 `kimi-`，且 kimi 不在 effort 族 → 走 `budget_tokens`）与 `llm-technical.md` 均确认 Kimi 属 budget 族。

**变更**：
- 对比表补 **Kimi 列**（控制参数 `thinking.budget_tokens` / 与 temperature 互斥 / 兼容端点 `api.moonshot.cn/anthropic` / 推荐场景），并新增「**默认思考行为**」行（DeepSeek 与 Kimi 默认开思考）
- 601/608/610 行措辞改为「Claude / Gemini / Kimi（`budget_tokens` 族）」
- 新增「默认开思考的厂商需注意（DeepSeek / Kimi）」说明段：未开启 thinking 时工具自动显式发 `disabled` 兜底，避免思考占满 `max_tokens` 致正文为空
- **新增断言（check-doc-drift 第 13 项）** `check_thinking_support_matrix()`：从 `api_base` 前缀名单派生「支持族 / effort 族 / 默认开思考族」，三项校验——① 对比表列须覆盖全部支持族；② 含「仅」且带 budget 概念词的句子须枚举全部 budget 族（防「仅 A / B」式漏族）；③ 默认开思考族须在手册中有「默认开思考」提示。**实现上先过滤掉无 budget 概念词的「仅」句**（如实测 /定价行），避免误报——已在真实仓库验证零误报
- 回归测试 +7（真实仓库一致 / 缺厂商列 / 封闭枚举漏族 / 无关「仅」句不误报 / 整表缺失 / 默认开思考缺提示 / 空文本）
- 检查项枚举同步 6 处

**判定一致、无冲突（已回查代码）**：17 章节 / 8 个 type 组；定价表 18 行逐值一致；缓存 TTL 可映射 19 条零不一致；datasink 速率与配额（3/31 请求每秒、8,191/131,071 篇每日）；batch 键含 `akshare_workers`；provider 类型定义（协议三类）；场外默认档 T+1/T+2/T+3/T+7；LLM 用量 Endpoint 主备标注；巨潮备源描述；thinking 兜底公式。

### 四文档一致性核对：修正 2 处冲突 + 补齐 2 处缺口 + 建需求追溯任务（2026-09-24，rf-426）

**背景**（用户要求）：交叉比对 `requirements.md` / `technical.md` / `llm-technical.md` / `testplan.md`，冲突处回查代码，形成待决策清单（Q1~Q4，用户已定调）。

**判定为冲突（已修）**：
- **`datasink_workers` 默认值**：`technical.md` 写「默认 3」，代码与默认模板均为 **2**（`_config_defaults.py`、`financial_report_digest.py` 同值），且原句把「请求速率 3 请求/秒」与「并发 worker 数」混为一谈 → 改为「默认 2，免费档批量上限 ≤3」
- **Provider 厂商枚举未含 Kimi**：`requirements.md` R-LLM-03 与 `technical.md` 模块表仍按「Claude/OpenAI/Gemini 三厂商 + claude 兼容端点只归 DeepSeek」表述，而 `llm-technical.md`（定价表/thinking 名单）与代码均已含 Kimi → 按用户决策 **A 改枚举范式**：协议层固定三类（claude / openai / gemini），**厂商与模型由 `model` 指定**并显式列举兼容端点厂商（DeepSeek、Kimi），新增厂商零代码接入

**判定为缺口（已补）**：
- **testplan 覆盖表未随 v0.11.2 扩展更新**：景气度框架行补挂本轮新载体（`test_fund_roe_estimate.py` ②维 ROE 推演；`test_liquidity_otc.py` 与 `test_code_utils.py::TestOtcRedemptionDaysDefault` ④维场外默认档）
- **口径重复维护点**：R-PF-09 的④维档位串与 `R-LIQ-03` 逐字重复 → R-PF-09 改为引用 `R-LIQ-03`（单一维护点），仅保留②维推演口径原文

**新建待办任务（用户决策 Q3-B：分批映射）**：`review-findings.md` 新增 **rf-426**「需求 ID 追溯链断裂」——276 个需求 ID 在 testplan/technical/llm-technical 中引用数为 0；按 6 批（38/39/37/57/25/61 条）分批建立「需求 ID → 验证载体」映射，批 1 启动时先定稿交付形态（testplan 加列 vs requirements 加列），配套双向断言脚本入 `--ci`。

**另修**：`testplan.md` 两处 `管理文档分区纪律)）` 括号错配（上轮批量替换枚举时引入的笔误）。

**判定一致、无需改动**（已回查代码）：报告章节 17 项 / 开关 30 项（实验 5·常规 16·报告 9）/ P 面板 5 个章节 / LLM 模块 5 个 / datasink 速率配额（3·31 请求/秒、8191·131071 篇/日）/ thinking 兜底 `max(1024, max_tokens−2048)` / plan-47·48 档位三方一致。

**验证**：六项 `--ci` + ruff + 版本一致性全绿（本轮为纯文档修正，无代码变更）。

### 测试用例全量审计：去冗余 + 26 处名实相符重命名 + 弱断言强化（2026-09-24，rf-425）

**背景**（用户要求）：核对全部测试用例的冗余、无效与命名语义。门禁 `check-test-redundancy`（死用例/无断言/完全重复/自证）零告警；另建 AST 级增强扫描（7,378 用例）核查门禁未覆盖的三类。

**变更**：
- **去冗余**：`TestSupportsExtendedThinking` / `TestIsEffortModel` 在 `test_llm_utils.py` 与 `test_llm_api_base.py` 重复存在且后者为严格子集——唯一独有断言（`gpt-4o → False`）迁入 utils 版新增 `test_non_llm_family_not_supported`，删除两个子集类（-5 例，零覆盖损失）
- **重命名 26 处**：`test_success` / `test_normal` / `test_basic` 等不承载内容的命名，逐例读函数体后按 docstring 语义改为描述性命名（`test_returns_standard_quote_record` / `test_parses_roll_data_items` / `test_parses_three_us_indices` / `test_formats_dividend_yield_percent` 等）
- **弱断言强化 1 处**：`test_missing_code_still_processes` 改为精确断言（`turnover_rate == 1.0`，由两期权重不相交可推导），消除「仅非空」在实现假化时仍通过的空间
- 数据快照同步：`test-coverage.md`（unit/standard/verify/all/unit_llm）、`folders.md`（测试用例 7,760、行数）

**判定为合规、不改的部分**（避免制造「名实不符」新缺陷）：跨文件同体对 1 组（`test_no_quotes` —— sina/tencent 两家解析器并行覆盖，符合既定口径）；输入条件式命名 26 处（`TestParseFloat::test_zero` 等，类上下文已带语义）；抽样 7 例「仅非空断言」中 6 例判别性充分（warning 字段被填充 / lookup 命中 / 映射存在 / 回调已绑定）。

**验证**：受影响模块 4,632 passed；`check-test-redundancy --ci` 零告警；六项 `--ci` + ruff + 版本一致性全绿。

### 新增管理文档分区纪律断言（2026-09-24，rf-424）

**背景**：本轮两次自审失误同源——待处理项被误置已解决区（rf-421）、发布时误删归档索引（rf-423），本质都是「管理文档分区/索引纪律无机器断言」，门禁全绿也拦不住。在 rf-423 已补「归档索引完整性」之后，本轮补齐「分区纪律」。

**变更**（`scripts/check-doc-drift.py` 第 12 项）：
- 新增纯函数 `audit_management_partitions()`（读文件薄封装为 `check_management_partitions()`），三条规则：
  - **A. review-findings 分区互斥 + 已解决须有据**：同一 rf 不得同时出现在「待处理」与「已解决」；且每个已解决项必须在 changelog（现行 + 归档）中出现——待处理项被误置已解决表时必然无修复记录，正是该类失误的可检特征
  - **B. plan 待办区纯度**：不得出现 ✅ 已完成项，也不得列已归档项（已归档项只认 `#### ✅ \`plan-N\`` 条目标题，归档文件正文提及——如「后续项：plan-49 转正评估」——不误判）
  - **C. changelog 段头纪律**：现行文件只允许一个版本段头且必须为 `-dev`（已发布版本段须随发布移入 `archived_changelog.*.md`）
- 检查项枚举同步 6 处：脚本 OK 文案与 argparse 描述、`folders.md` ×2、`developer-guide.md`、`testplan.md` ×2、`CLAUDE.md` ×2（门禁条目）

**回归 +10**：真实仓库一致、三类历史失误各自检出、归档 changelog 中的记录不误报、归档文件正文提及不误报、空文件不崩。

**验证**：`pytest src/test/unit/scripts/test_check_doc_drift.py` → 83 passed；六项 `--ci` + ruff + 版本一致性全绿。

### 修复归档索引被误删 + 新增归档索引完整性守卫（2026-09-24，rf-423）

**背景**（用户指出）：发布 v0.11.2 的版本切换提交把 changelog「已发布段至文件末尾」整段重写，而 `## 归档` 索引段位于文件末尾 → 11 条历史归档索引被一并删除。当时没有任何断言覆盖「管理文档归档索引 ↔ `docs-stm/archive/` 实际文件」的一致性，故门禁全绿也未拦下。

**变更**：
- `changelog.md`：从发布前版本取回 `## 归档` 索引段（11 条，0.11.x 条目更新为 v0.11.0 ~ v0.11.2），移除发布时临时添加的单条指针
- `scripts/check-doc-drift.py`：新增第 11 项**归档索引完整性**检查 `check_archive_index()`——changelog / plan / review-findings 三份管理文档的归档索引与 `docs-stm/archive/` 下对应 `archived_*` 文件**双向**比对（漏列 → 「缺少」；幽灵引用 → 「不存在」）；实现上**直接读文件**，不走 `_scan_docs()`（该扫描面排除历史记录类，changelog 正在其中——正是本次缺口的成因）
- 回归测试 +5：真实仓库一致、正反两向检出、被检面覆盖三份文档、以及一条端到端「真实仓库索引被删即报」用例

**验证**：`pytest src/test/unit/scripts/test_check_doc_drift.py` 73 passed；六项 `--ci` + ruff + 版本一致性全绿。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.2（2026-09-15 ~ 2026-09-24）
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
