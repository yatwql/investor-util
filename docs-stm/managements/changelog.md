# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.10]**（2026-10-01）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.11-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 实验功能治理（合并/撤销/观测）

- **实验功能瘦身与归并（开关 30→28 项）**：① **撤销**独立开关 `llm_debate_qa_concentration`——它触发面最窄、与已转正的辩论-条件推理同模式（既有调用内追加段落），改为**辩论流程内建段落**：集中度问答段不再受开关控制，正反辩论开启时白脸/黑脸/综合各阶段在单品种占比超阈值（原 20%）时自动附加集中度量化评估；阈值配置 `debate.qa_concentration.threshold` 更名为 `debate.concentration_qa.threshold`（更名前键名自动兼容并提示）；② **合并转正** `signal_pre_digest`（信号预消化）+ `signal_ledger`（确定性信号沉淀）→ 单开关 **`deterministic_signal`（确定性信号模块）**，常规组默认开——实时注入面保持原状，沉淀面不再要用户显式开启（账本有真实积累验证、写盘幂等可忽略）；features.json 中的更名前键名自动迁移到新键，配置零改动升级；相关函数命名同步：`_build_concentration_qa_block()`、参数 `include_concentration_qa`，辩论缓存后缀不再携带 `q` 位（升级后辩论缓存首次运行重生成一次，TTL 1天内自动收敛）；③ **实验组剩 3 项**（正反辩论 / 决策跨期反思闭环 / 景气度框架诊断）。
- **新增实验功能使用统计（`experiment_stats`）**：`src/python/core/experiment_stats.py` + `data/state/experiment_stats.json`——每次生成报告时记录各启用实验开关的**启用计数与最近启用日期**（报告入口 `log_experimental_features` 自动写入，写盘失败只告警不影响报告），为「转正 / 撤销」决策提供客观数据，不再靠代码行数与账本行数推测。入测试隔离（conftest 路径重定向）。
- **doctor 复盘账本只读概览**：系统自检新增「决策复盘账本」（已结算/待结算计数与方向命中率）、「确定性信号账本」（实时/非实时累计与统计窗口）、「实验功能使用统计」（各开关累计启用次数）三行信息性检查——实验功能长期缺真实反馈就无法转正/撤销，这层可读视图让用户无需翻 data/state/ 即可看到积累状况。只读，不写不结算。
- **验证死线与转正判据入 plan**：plan-70（decision_reflection 撤销死线与转正条件）、plan-71（prosperity_framework 转正判据）立项（观测手段即 `experiment_stats` + `doctor` 账本概览）。
- **全量文档核对收尾（序号/面板编号/旧键名残留）**：逐份核对 10 份管理文档 + 11 份用户手册后共修 8 处不一致——① 用户手册面板编号残留旧布局（how-to-use-tui-menu.md 实验说明段、how-to-use-web-mode.md / how-to-config.md 的实验块范围 6-10/6-8 统一改为实验块 7-9）；② how-to-config-llm.md 示例 JSON 与 requirements.md R-LLM-DB-QA-CONCENTRATION-04 漏改的 `qa_concentration` 键名；③ folders.md 目录树 signal_record/signal_ledger 条目的「实验开关 signal_ledger」旧开关名；④ tui_menu.py 注释 Flag 列表、plan.md「当前迭代」漏列 plan-70/71、「四个 --ci」守卫数、plan-70 中非语义名 `problem_llm_capture`（实为 `decision_llm_capture`）。核对通过项：版本号一致性 13/13（0.11.11-dev）、编号源 plan-next=72 / rf-next=520 归档无冲突、7 个 --ci 守护脚本全绿、scripts 单测 421 通过。
- **配套文档全面刷新**：README / how-to-config / how-to-use-tui-menu（开关分块与面板编号）/ how-to-use-cli-mode / how-to-config-llm / requirements（R-LLM-09 与 7.8.4）/ llm-technical / technical（语义命名表）/ developer-guide（转正判据段）/ folders / test-coverage（用例 8137 项）。

### 新增

- **pi 缓存保活 + 思考预算 + 压缩诊断（额度消耗治理续）**：三项互补调优。① **提示缓存保留**：shell 环境变量 `PI_CACHE_RETENTION=long` + `.pi/models.json` 对按量模型（`deepseek-flash`/`deepseek-v4-pro`）声明 `promptCache {short:300, long:3600}`——两者缺一即静默无效（`getPromptCacheTtlMs` 在模型未声明 `promptCache` 时返回 `undefined`，而目录里**没有任何模型声明过它**）；**刻意不下发到订阅端点**，因缓存保活「计用量但不占上下文」，对按窗口计量的订阅是白刷额度，其收益待实测。② **思考预算**：`.pi/settings.json` 只压最低两档（`minimal:512`、`low:1024`，内置 1024/2048），**`medium`/`high` 保留内置 8192/16384**——它们承担 `/thinking` 升档后的复杂推理，压掉等于废掉升档；合并语义为 `{...内置默认, ...自定义}`，故只写要改的档位。③ **压缩/缓存诊断**：`showCacheMissNotices: true` 上屏缓存未命中、保活成功、**压缩用量**、provider 恢复四类通知——压缩一次要读整个上下文，其用量此前完全不可见，这是排查「额度去哪了」的主观测口。`developer-guide.md` 该节改题为「模型与服务配置」并补四件事：两文件作用域差异（models.json 需软链 / settings.json 需项目信任 `trust.json`，失效条件不同）、缓存链的两个必备环节、思考预算的合并语义、诊断开关。

- **pi 模型配置：订阅端点节流 + 思考档位下调（额度消耗治理）**：实测订阅端点（Kimi Code / OpenCode Go）易撞 5 小时窗口，根因是**每轮上下文量级**不是轮数——pi 的自动压缩阈值是 `contextTokens > contextWindow − 16K`，而目录里这两个端点 `contextWindow` 达 1M → 压缩几乎不触发、单轮输入可近百万 tokens。故：① `.pi/models.json` 对 `kimi-coding`（3 个模型）与 `opencode-go`（29 个模型）统一收窄 `maxTokens` ≤ 65536、`contextWindow` ≤ 262144（**只降不升**，已低于上限的模型不写覆盖）；② `~/.pi/agent/settings.json` 的 `defaultThinkingLevel` `high` → `low`（思考计入 output，实测输出量≈输入量是其主因，需要时 `/thinking` 临时提升）；③ **顺带修复既有静默失效**：`deepseek` 覆盖键 `deepseek-v4-flash` 已不是当前目录 id（改名为 `deepseek-flash`），覆盖一直未生效（`--list-models` 仍显示 `1M / 384K`）——已按当前 id 修正，`deepseek-flash` 恢复 `65.5K`。`developer-guide.md` 的 pi 配置节改写为「编程档采样 + 订阅端点节流 + 思考档位」三部分，并补「覆盖键按 id 精确匹配、目录改名即静默失效，`--list-models` 是唯一验收手段」的教训。
- **LLM 次备接入：Kimi Code 订阅（kimi-code，priority 15）**：插在 kimi-main(10) 与 deepseek-main(20) 之间——Kimi Code 是月之暗面的编程订阅（`https://api.kimi.com/coding/`，Anthropic 兼容），与 OpenCode Go 同为「订阅制端点」故同样声明 `pacing`（1s 间隔 / 并发 1）；模型默认 `kimi-for-coding`（K2.8，1M 上下文，可改 `k3`），凭据在 `llm_key.json` 的 `kimi-code` 块（api_key 留空待填，未填时轮空失败不影响主/备/末备）。注意 `kimi-for-coding` 不在既有定价表 → 该源的费用估算显示 `-`（token 用量统计不受影响）；Kimi thinking 支持矩阵按模型名判定，`kimi-for-coding` 不在既有 Kimi 族名单 → 按非思考模式调用（对报告长文生成影响有限）。
- **LLM 备源接入：OpenCode Go（Kimi K3，链尾）**：`data/config/llm_providers.json` 新增第三条目 `kimi-opencode-go`（provider `claude` / Anthropic 兼容端点 `https://opencode.ai/zen/go/v1/messages`、`priority` 30——排在 kimi-main(10) 与 deepseek-main(20) 之后，仅当前两源都失败才轮到它）；`model`/`endpoint` 与既有条目同风格放 `llm_key.json` 凭据块（api_key 留空待填，未填时该条目轮空失败、不影响前两源）。模型名 `kimi-k3` 与定价表/思考支持矩阵既有条目**完全一致**（成本记账与 thinking 判定直接生效）。订阅制端点按既有节流设计声明 `pacing`（最小间隔 1s + 在途并发 1，防止订阅额度被报告批量调用打爆；403 配额/风控不重试直接递补的既有逻辑兜底）。选型理由见会话评估：订阅条款（$10/月 agentic coding 定位）与限额摩擦风险 → 只作链尾备源，不作主源。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.10（2026-09-15 ~ 2026-10-01）
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
