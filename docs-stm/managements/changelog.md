# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.19-dev] - 开发中（未发布）

### 已完成内容归档（changelog / plan / review-findings 并入 v0.10.x 归档）（2026-09-12）

- **背景**：三份管理文档中长期保留已发布版本记录与已完成计划/修复项——`changelog.md` 留存 [0.10.14] ~ [0.10.18] 五个已发布版本，`plan.md` 留存 plan-29 引用行与 plan-40 / plan-41 完成态段落及 P4 实验功能表（plan-30 ~ plan-41），`review-findings.md` 留存两批「已解决待归档」（rf-322 ~ rf-350、rf-351 ~ rf-353）。已实现内容与在办事项混排，读者难以分辨哪些仍待处理。
- **归档口径**：「已完成即归档」——已发布版本的变更记录、已实现计划项的完成态、已修复的自审问题一律并入对应归档文件，live 文档仅保留待办与归档引用。
- **归档落点**：
  - `archived_changelog.0.10.x.md`：新增 [0.10.14] ~ [0.10.18] 五节（按版本升序接于 [0.10.13] 之后），涵盖版本扩至 v0.10.1 ~ v0.10.18；
  - `archived_plan.0.10.x.md`：新增「P1 — 已完成（plan-29 ~ plan-41 完成态）」与「P4 — 实验功能（plan-30 ~ plan-41 全部完成）」两节，设计文档索引补 `feature-switch-registry/` 与 `feeder-fund-penetration/` 两份，涵盖版本扩至 v0.10.0 ~ v0.10.18；
  - `archived_review-findings.0.10.x.md`：新增 v0.10.18 与 v0.10.19-dev 两节，涵盖 rf-204 ~ rf-353。
- **归档后 live 文档**：`changelog.md` 仅剩 [0.10.19-dev]；`plan.md` 的 P1 / P4 两区均写「无待办项」，仅保留待办登记区与归档引用；`review-findings.md` 的「已解决问题」区改为归档引用行，仅保留待处理区（rf-113 / rf-114 交互图表技术债、rf-75~89 文件过长关注项、rf-257 Web 真机验收）。
- **目录树同步**：`folders.md` 的项目文档/归档统计按实测刷新。

### 已实现设计文档归档（plan 目录清空）（2026-09-12）

- **背景**：`docs-stm/plan/` 的两份设计文档均已实现落地（功能开关注册表统一 plan-39、联接基金穿透与基金持仓取数通道修正 plan-40），留在「中间计划文件」目录会被误读为在办事项。
- **归档**：按主题子目录 + 语义文件名迁入 v0.10.x 归档——`docs-stm/plan/feature-switch-registry-design.md` → `docs-stm/archive/v0.10.x/feature-switch-registry/feature-switch-registry-unification-design.md`；`docs-stm/plan/feeder-fund-penetration-design.md` → `docs-stm/archive/v0.10.x/feeder-fund-penetration/feeder-penetration-and-holdings-fetch-design.md`。两份均补「已归档。原始路径：…」头注，便于按历史引用回溯。
- **引用同步**：`plan.md`（plan-39 / plan-40 两处设计文档索引）、`review-findings.md`（rf-346）、`folders.md`（`plan/` 统计行归零 + v0.10.x 目录树新增两个主题子目录 + 项目文档/归档统计按实测刷新）。
- **口径**：`docs-stm/plan/` 自此为空——新设计文档仍按「中间计划文件 → `docs-stm/plan/`」归属，实现落地后即归档至对应版本的 `docs-stm/archive/` 主题子目录。

### 读侧增强类开关转正（五项默认开启）（2026-09-12）

- **背景**：功能开关注册表统一（plan-39）把「面板可见性」与「是否实验项」解耦后，「转正」只剩「改分组 + 改默认值」两个字段、面板入口自动延续。据此盘点 9 项实验开关，其中 8 项在实际使用中已被用户手工打开——即**真实数据验证已经发生**，却让用户用配置承担本该由默认值表达的取舍；默认关的真实代价是这层机制在生产路径从不执行。
- **转正判据（第三类，新增）**：**开启的代价是否只在读侧**——只在既有提示词或既有产物流水线上追加一段由**已算出**数据派生的内容，不新增 LLM 调用次数、不写新的持久化文件、无隐式网络与耗时，且该内容有确定收益。据此转正五项：
  - `signal_pre_digest`（信号预消化）——资金流/涨跌/估值分位等数值指标进 LLM 前预消化为带方向标注的「信号：…」行；
  - `module_quality_gate`（模块级质量分级）——按完整性/篇幅给 4 个 LLM 模块输出评 A~F，低评级中「内容在但存在缺陷」者注入【内容质量提示】横幅（只标注，不阻断不重试不写回缓存）；
  - `decision_header_parse`（结构化决策头）——专家复盘提示词追加受控 JSON 决策头契约，抽取侧优先读结构化头、失败回落确定性表格解析；
  - `llm_debate_conditional`（辩论-条件推理）——专家复盘追加条件推理段；
  - `datasource_credential_ready`（数据源凭据就绪）——链路预检跳过缺凭据源并给可读指引（纯只读诊断，判据 A 的直接延用）。
- **口径**：五项 `affects_report` **照实答 `True`**——它们确实改变产物内容，故 Web 配置面板照常带「（影响报告）」标记，TUI 面板不标 ⚗；关闭杠杆保留——`features.json` 对应项置 `false` 即回到「未引入本机制」的行为，CLI 用 `--feature NAME=off`（`--experiment` 只认仍在实验组的开关，`--feature` 为全域双向通道）。
- **刻意不转正（判据的反面）**：**写盘积累型** `signal_ledger`（`decision_reflection` 同为落账机制）——默认开启等于未经用户知情选择就向 `data/state/*.jsonl` 写持久化状态，须由用户明确开启；**调用次数放大型** `llm_debate_procon`——把一次 `expert_review` 换成最多三次（pro → con → synthesis），默认开启直接改变费用与耗时量级；`llm_debate_qa_concentration` 触发面最窄（单品种占比 ≥20% 时才附加块）、覆盖最薄，待有真实触发样本后再评估。
- **一次性副作用（升级须知）**：改变提示词的开关，其缓存后缀函数由「默认返回空」翻为「默认返回非空」——`core/decision_header.py::structured_header_cache_suffix()` → `_dh`、`llm/module_fingerprint.py::debate_feature_cache_suffix()` → `_c`、`llm/prompts_signals.py::_signal_digest_cache_suffix()` → 信号块摘要后缀。这些后缀是 `expert_review` 标准指纹的一部分，故**升级后首次运行会换键重生成一次**（属预期行为，非缺陷；两次运行之间缓存稳定）。
- **程序改动**：`config/features.py` 五项声明改 `GROUP_STANDARD` + `default=True`（注册表仍是唯一登记点，三渠道上屏、面板编号、`enabled_experimental_features()` 产物自述全部自动派生）；源码 9 处注释/文档字符串由「实验开关/实验项」改述为「开关（默认开启）」。
- **测试**：9 个用例的「关闭基线」原依赖 `reset_feature_flags()`，转正后该函数返回的是**已转正的默认值**（`True`）——全部改为在用例内**显式** `set_feature_enabled(flag, False)` 并附注「转正后默认开，基准须显式关」；`test_excel_report_structure.py::test_notice_survives_empty_session_usage` 的产物自述断言原指向 `module_quality_gate`（已非实验项、不再出现在实验提示中），改指向仍属实验组的 `signal_ledger`（「确定性信号沉淀」），保留该用例原意（早返回的用量摘要不影响实验提示）。涉及文件：`test_decision_header.py` / `test_decision_llm_capture.py` / `test_prompts_structured_header.py` / `test_prompts_signals.py` / `test_debate_generators.py` / `test_excel_report_structure.py`（199 例全绿）。
- **文档**：`developer-guide.md` 新增「读侧增强类开关也应转正（第三类首例）」转正口径段 + 「刻意不转正的两类」说明；`README.md` / `how-to-config.md` / `how-to-use-tui-menu.md` / `how-to-use-cli-mode.md` / `how-to-use-web-mode.md` / `how-to-config-llm.md` / `faq.md` / `reports-instruction.md` / `llm-technical.md` / `technical.md` / `requirements.md` / `folders.md` 同步为常规开关口径，TUI 面板编号改为实验块 6-9 / 常规块 10-25（**转正项排在常规块块首 10-14，故既有常规开关 15-25 的编号不位移**）；CLI/README 中 `--experiment X` 的示例改用仍属实验组的开关。自审记录 rf-353。

### 完整报告快捷入口 llm.sh / llm.ps1（2026-09-12）

- **背景**：用户要求为「生成完整报告（含 LLM）」提供一个最快捷的入口封装——等价于 TUI 菜单的 `[L]`，免去每次敲 `report --type full`。
- **新增**：`scripts/llm.sh`（Linux/macOS）与 `scripts/llm.ps1`（Windows），沿用既有 `cli.sh` / `cli.ps1` 的结构（自动定位项目根目录 + 虚拟环境解释器 + 建数据目录），把子命令与报告类型写死为 `report --type full`；追加参数原样接在其后，即 `report` 的报告级参数（`--force-llm` / `--history`）。
- **口径**：组合历史走势不写死 `--history`，由配置 `history.fetch_mode` 决定——与 TUI 菜单 `[L]` 的取数逻辑一致（`off` 跳过、`auto` 获取），而非无条件强制获取。需要全局参数（`--config` / `--output` / `--experiment` / `--feature`）时仍用 `cli.sh` / `cli.ps1`，它们必须写在 `report` 子命令之前（argparse 子解析器结构所限，见手册 §10.1）。
- **编码**：`llm.ps1` 为 UTF-8 with BOM + CRLF，`llm.sh` 为 UTF-8 无 BOM 且置可执行位——与同目录既有脚本一致。
- **文档**：手册 §10 新增「10.2 一键快捷入口」、`how-to-start.md` 便捷入口段补快捷入口说明、`developer-guide.md` 辅助脚本速查与脚本详解补两行、`folders.md` 目录树同步。

### CLI 手册补 TUI 菜单对照表（2026-09-12）

- **背景**：用户问「CLI 脚本如何达成 TUI 模式中 [L] 的作用」，核对实现后给出等价命令与逐项参数映射；用户要求把映射表写入 CLI 手册。
- **改动（纯文档，无代码改动）**：`how-to-use-cli-mode.md` §10 新增「10.1 TUI 菜单 → CLI 命令对照」——首表按菜单项对照（[E]/[B]/[L]/[W] → `report --type basic|both|full`、`whatif`），次表以 `[L]` 为例逐项拆解 TUI 交互询问与 CLI 参数的对应（`--type full` / `--history auto` / `--force-llm` / `--non-interactive`），并说明两点行为差异（`history.fetch_mode="prompt"` 时 CLI 无交互可比；`enable_history=false` 时外层开关优先于 `--history`）。
- **交叉引用**：`how-to-use-tui-menu.md` 开头的 CLI 提示行补指向 §10.1。

### 「距今多久」判定一律改用交易日（缺陷修复 rf-352）（2026-09-12）

- **背景**：承接 rf-351，用户指出判定逻辑本身也应以交易日为准——「其实判定交易数据以及报告数据是否新鲜，都应该用交易日进行判定，而不是自然日进行判断」。核对后确认同一病根（以自然日差代交易日）在三处确定性判定中复现，并升格为架构约束。
- **三处违规**：
  - **K 线增量跳空判定**（`fetcher/chain.py`）：旧实现取新旧 K 线日期的**自然日差** > 5 即判「数据跳空——部分历史不可达」。长假（春节/国庆）前后两个相邻交易日相隔 8~10 个自然日，会被误判为跳空并触发不必要的全量重拉。
  - **停更因子剔除**（`analysis/style_factor_regression.py`）：`FACTOR_STALE_DAYS=120`（自然日）判定因子指数末根 K 线是否停更。长假期间无数据属正常，按自然日会把仅隔数日的因子判为停更剔除，剩余因子 < 2 时整块风格回归直接落「数据不足」。
  - **再平衡新仓观察期**（`analysis/rebalance.py`）：R-RBL-07 第 (2) 条要求「新买入品种不足 20 日不触发」，原实现读 `holding_days` 字段——该字段**全项目无生产者**，防护实际从未生效（形同虚设）。
- **原语下沉（DRY，一处实现三处共用）**：交易日历原语自 `report/market_value.py` 下沉至 `core/trading_calendar.py`（`_get_trading_calendar`/`_is_trading_day`/`get_last_trading_day`/`get_prev_trading_day`/`_count_trading_days_back` + 新增公共原语 `count_trading_days_elapsed`），使 `fetcher/` 与 `analysis/` 得以复用而不反向依赖 `report/`；`market_value.py` 按原公共名重新导出，既有导入路径与测试补丁点不变（下沉动因为分层无环：`report/market_value.py` 已 import `fetcher.price`，反向导入即成环）。
- **修复**：
  - `fetcher/chain.py` — 新增 `_missing_trading_days()`（相邻交易日 → 0），跳空阈值语义化为 `_MAX_GAP_TRADING_DAYS=5`，日志改「数据跳空 N 个交易日」。
  - `analysis/style_factor_regression.py` — 常量改名 `FACTOR_STALE_TRADING_DAYS=86`（约 4 个月交易日数），按交易日计龄；日期无法解析时按「未知」视为未停更（宁可不剔除也不误剔除）。
  - `analysis/rebalance.py` — 新增 `build_holding_trading_days()`（按交易流水首次买入日、以交易日计至基准交易日）+ `MIN_NEW_POSITION_TRADING_DAYS=20`，防护理由文案回显实际交易日数；**为该无生产者字段补上生产者**——`report/_report_helpers.py::attach_holding_trading_days()` 在编排期写入 `holding_days`，三处 `holdings_details` 生产者（完整报告、双路径、Excel 基础路径）与 `_action_holdings_details` 调用点均已接入交易流水；无流水/无买入记录时该键不写入，防护按「未知」跳过过滤。
- **约束升格**：技术设计文档 §8.3 新增架构约束「**时间距离一律以交易日计**」——凡用于判定数据新鲜度/停更/跳空/持仓期/观察期的「距今多久」一律以交易日计，交易日来源唯一为 `core/trading_calendar.py`，各模块不得自建日历或另写自然日差；自然日差仅限本身以自然日定义的量（静默期天数、缓存 TTL）。`scripts/check-code-traces.py` / `check-doc-traces.py` 的约束代号检测范围同步放开至新编号。
- **回归测试**：新增 `src/test/unit/core/test_trading_calendar.py`（交易日区间计数/周末与长假不误计/日历不可用回退/非法日期）与三处修复的边界用例（相邻 K 线缺失交易日 → 0、长假不被误剔除、观察期 19 与 20 交易日边界、防护理由回显交易日数、距离确以交易日传入）；既有 44 处交易日历补丁目标同步重定向至 `core.trading_calendar`。
- **文档**：`technical.md`（§8.3 新增「时间距离一律以交易日计」约束、因子停更阈值口径与 probe 脚本自然日口径的差异说明、`data_freshness` 交易日来源改指 `core/trading_calendar.py`）、`requirements.md` R-RBL-07 第 (2) 条改「不足 20 个交易日」并写明持仓期取数口径、`folders.md` 目录树、`CLAUDE.md` 约束条数同步。

### 体检「数据质量」维度的净值新鲜度基准（缺陷修复 rf-351）（2026-09-12）

- **背景**：用户在 2026-09-12（周六）运行报告，持仓体检报告第 5 维「数据质量」写出「QDII净值更新滞后：040046、017730、016055、096001净值日期为2026-09-10，当前时间为2026-09-12，存在延迟」。用户指出：报告虽在 9 月 12 日运行，**交易日仍是 9 月 11 日**，QDII 净值为 T-1 即 9 月 10 日**属正常，不存在延迟**。
- **两处错**：① **基准错**——报告在非交易日运行，运行时刻（09-12）与最近交易日（09-11）天然相差一个自然日，用「净值日期距当前日期」的自然日差判定延迟必然误报；② **口径错**——QDII 与部分场外基金的官方净值本就是 T-1，即便在交易日运行也不构成延迟。
- **同报告自相矛盾**：同一份报告的「数据质量仪表盘」可信度区块对四只品种给出的判定是「缓存（T-1）」（`core/data_freshness.py` 的 `cached`，正常），确定性层判定正确，**仅提示词侧表述错误**。
- **根因**：`_SYSTEM_HEALTH_CHECK` 第 5 维该条写作「基金净值更新延迟（净值日期距当前日期）」，让模型以运行时刻做自然日差，且未给交易日基准与 QDII T-1 例外；模型转而把持仓明细中的 `(QDII滞后1日)` 标注读成延迟证据——该标注的本意恰是「这是正常特性，勿据此谈本日盈亏」（`_SYSTEM_EXPERT_REVIEW` 中已有同义约束，第 5 维缺）。
- **修复**：① `core/data_freshness.py::build_freshness_summary` 契约回传 `trading_day`/`prev_trading_day`（消费方须以交易日而非运行时刻为基准，属契约级说明）；② `llm/prompts_tables.py` 新增 `_build_nav_freshness_basis_lines()`，产出「净值新鲜度基准（最近交易日 / 前一交易日）」「净值滞后品种」「无有效行情品种」行，**滞后清单直接引用 `stale`/`degraded` 判定**（与数据质量仪表盘可信度区块同源），不由模型从裸日期推断；③ `_build_data_quality_detail_block()` 增 `data_freshness` 入参，两处调用点同源传入（`llm/generators_orchestrator.py` 渲染一次同时进指纹与提示词、`llm/prompts_action.py` 旁路兜底）；④ `_SYSTEM_HEALTH_CHECK` 第 5 维改以交易日为基准，写明 QDII/场外 T-1 不构成延迟、**禁止**用运行时刻与净值日期的自然日差判定，并把援引段落由【数据质量降级】改为其实际承载的【数据质量详细状态】。
- **契约不可用时保持既有行为**：`data_freshness` 缺失或 `available=False` 时基准行整体不注入，文案与既有输出逐字节一致（回归测试覆盖）。
- **回归测试**：新增六例（基准行取交易日而非运行时刻、QDII 的 `cached` 不入滞后清单、`stale` 才入清单、契约不可用时保持既有文案、体检提示词经 `pipeline_data` 注入基准、系统提示词不再含「净值日期距当前日期」）+ 契约回传交易日一例。
- **文档**：`technical.md` 附录 H 的 `data_freshness` 契约补 `trading_day`/`prev_trading_day` 及基准说明；`llm-technical.md` 的 `degradation_events` 暴露段与 `data_quality_text` 指纹项、第 5 维职责描述同步。

### TUI 缺省选中项入档（2026-09-12）

- **背景**：用户要求「TUI 界面打开时候，缺省选 L」。核对实现后确认该行为**早已存在**——`data/config/config.json` 的 `default_menu_key` 取值为 `"L"`，`tui/tui.py` 读取该键并经 `index_by_key()` 定位初始光标，落在第 3 项（生成完整报告）；键缺失或取值未命中时回落到首项 `[E]`（该注释同时说明 `[D]` 被开关裁剪时的回落行为）。出厂默认模板 `config/_config_defaults.py::_DEFAULT_CONFIG` 同为 `"L"`，`technical.md` §1.7「缺省菜单定位」亦有记载——**三处一致，无代码缺陷**。
- **缺的是需求与用户手册两处**：`requirements.md` §3.1 只写到「主菜单提供以下 20 个交互选项」，未规定初始选中项；`how-to-use-tui-menu.md` 的菜单示例反而把光标画在 `[E]` 上，与实况相反，照示例阅读会以为缺省落在基础版报告。
- **改动（纯文档，无代码改动）**：`requirements.md` §3.1 新增 **R-TUI-06**——启动后缺省选中 `[L]`，初始光标由 `default_menu_key` 决定（取值为任一菜单快捷键），未命中回落 `[E]`；`how-to-use-tui-menu.md` 的菜单示例光标由 `[E]` 移至 `[L]`，并在示例下方补说明（含修改入口指向配置指南）。
- **顺带订正**：同文件「组合历史走势与回撤」的脚注写「一章两区块」却列了三项（走势表 + 回撤矩阵 + 危机区间标注），与 `reports-instruction.md` 上一轮统一后的「一章三区块」口径对齐。

### 开发版本切换（2026-09-12）

- 发布 v0.10.18 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.19。

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.18（2026-08-04 ~ 2026-09-12）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
