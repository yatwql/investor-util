# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.10]**（2026-10-01）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.11-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

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
