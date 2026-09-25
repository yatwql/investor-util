# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.4]**（2026-09-25）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.5-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 修 CI 失败根因：测试断言硬编码「会演进的总数」→ 改结构不变量 + 新增第 5 类静态检查（2026-09-25，rf-431）

**现象**：GitHub CI **run #800**（commit `225ad00f`）在 **3.11 / 3.12 / 3.13 三个版本全部 P0 失败**，失败用例 `test_check_requirement_trace.py::TestRealRepo::test_every_requirement_id_mapped`。

**根因**：该断言写死 `assert len(req_ids) == 276`，而**需求条数的真值来源是 `requirements.md`**；我在 `225ad00f` 新增了 `R-LLM-10`（276 → 277）却漏改断言 → 良性变更被判为回归。映射表本身完全正确，门禁脚本也一直通过——**是测试自己把易漂移的派生量当真值**。

**同类问题**（新增检查扫出）：`test_registry.py` 另有 4 处，其中 `test_total_sections` 注释自述「新增模块时同步更新此值」——等于承认它每次都要手改。

**变更**：
- **测试改结构不变量**（比写死总数更强）：
  - 需求映射：「ID 集合双向相等 + 域集合 == `_ALL_DOMAINS` + **域内序号从 1 连续无跳号** + 非空守卫」——新增需求不再打红，且能发现跳号/重号
  - 章节表：「编号 1..N 连续 + key 唯一」；计算模块表：「module_key 非空且唯一」
  - LLM 键：「逐模块必备键齐全」（遍历模块后缀，非计数）；精确键：「已知键集合 ⊆ 实测」
- **新增 `check-test-redundancy.py` 第 5 类** `check_hardcoded_evolving_totals`：静态检出 `assert len(<可增长集合>) ==/> 数字`，判定保守（实参名含语义关键词或路径含 requirement/registry 才报；忽略 ≤ 3 的小数字；不误报集合相等/子集/遍历等结构断言）
- **文档同步**：「四类 → 五类」（CLAUDE.md / developer-guide 详表 / folders.md 两处）；并在 CLAUDE.md 与 developer-guide 新增**「测试真值单一来源」纪律**条目（禁止写死会随开发演进的派生量，给出结构关系断言写法与反例，指向第 5 类检查）——把本次教训固化为显式约束
- **回归**：traceability +4 例（含「新增需求不再打红」的合成反证、跳号检测）、redundancy +7 例（含不误报结构断言/小数字/非断言位置的守卫）

**验证**：`check-test-redundancy -v` → 7439 用例 / 五类计数全 0；`test_registry.py` 61 passed；traceability 21 passed。
### Kimi Code 订阅端点接入范例与模型识别补齐（2026-09-25）

**背景**：用户计划改用 Kimi Code 订阅 Key（`api.kimi.com/coding/`），要求先把范例与文档准备好。

**新增文档章节**（`how-to-config-llm.md` → 「支持的 provider 及配置示例」→ **Kimi Code（订阅会员）** 折叠块）：
- 两套系统差异对照表（Base URL / Key 来源 / **模型名** / 计费方式 / 互不通用）
- 启用步骤（改 `llm_key.json` + `llm_providers.json` 两个文件，**无需改代码**）+ 验证命令
- `pacing` 推荐值表（订阅端点 20s/0.2/1）与「想更保守 / 想恢复放开」调法
- 403 配额风控语义对照表（403 不重试、429/503 重试、401 表示两套系统混用）
- **风险提示**（官方条款原文引用：订阅仅限交互式，脚本化批量执行属超范围；`pacing` 只能降低检出概率）
- 交叉链接：`how-to-config-llm.md` 开放平台 Kimi 段指向本折叠块；`faq.md` 新增 FAQ 指向该折叠块（内容归属 LLM 配置手册，不另立文件）

**代码补齐 2 处模型识别缺口**（换 Key 时才会暴露）：
- `_THINKING_SUPPORTED_PREFIXES` / `_THINKING_DEFAULT_ON_PREFIXES` 补 `k3`：Kimi Code 旗舰模型名为 `k3` / `k3-256k`，**不以 `kimi-` 开头**——漏登记会让「未开启 thinking 时显式禁用」的安全网失效
- 回归 +3 例（Kimi Code 模型 ID 支持 thinking / 默认开思考 / 不属 effort 族）

**未改动**：`data/config/llm_providers.json` 与 `llm_key.json` 保持现状（仍走开放平台按量付费端点），等用户换 Key 时按范例操作。

### LLM 端点级节流与并发治理：把速率/并发约束声明化到 provider 条目（2026-09-25，plan-57）

**背景**：用户计划把订阅制编码端点（Kimi Code，`api.kimi.com/coding/`）接入程序，要求从整体架构出发、不留技术债，并提出「非该端点时并发约束能否放开」。

**实测现状**（日志统计 10 次运行）：每次报告 **8~9 次 LLM 调用**、输入 22~27k + 输出 19~34k = **41k~56k token**，在 **2~8 分钟**内以 3 路并发发出。全局键 `llm_max_concurrency` 只能表达「所有模块合起来最多几个线程」，**无法表达「同一程序、不同端点不同策略」**——这正是「想收紧订阅制端点、同时放开按量端点」的架构缺口。

**变更**：
- **新增 `llm/pacing.py`**：把节流与并发**声明化到 provider 条目**（`llm_providers.json` 的 `pacing` 段）——
  - `min_interval`（两次请求最小间隔秒）、`jitter`（间隔随机抖动比例，避免固定节奏的机器特征）、`max_concurrency`（该端点同时在途上限）
  - **缺省即无约束**：不写 `pacing` 的端点零开销直通，行为与未引入本机制时**逐字节一致**；因此同一份配置可对订阅制端点收紧、对按量端点放开
  - 与全局 `llm_max_concurrency` **两级叠加**（全局线程池 + 每端点信号量）
  - 先取并发许可再等间隔，使间隔真正约束「请求发出」时刻；`PacingGate` 为 context manager，异常路径无条件释放
- **配置层**：`_parse_providers_list` 透传 `pacing`（坏字段逐字段忽略，不因笔误使整条 provider 失效）；`_inject_provider_chain_data` 装载策略（配置为唯一事实来源）；默认模板补注释
- **调用链接线**：`endpoint_key`（provider 条目名）逐层透传 `api.py` → `call_single_provider` → `call_claude`/`call_openai`/`call_gemini` → `call_llm_with_retry`，在**唯一调用缝**施加 `PacingGate`
- **复用既有原语**：`fetcher/batch.py::RateLimiter` 新增 `acquire_interval(key, interval)`（逐次显式间隔），不重复实现限速器
- **403 配额/风控拒绝改为不重试**：新增 `FAIL_REASON_QUOTA_EXCEEDED`；`_attempt_api_call` 将 403 归为 `("quota", 403)`，重试骨架直接降级到下一 provider——这类限制按时间窗口滚动（如 5 小时窗口、并发上限），**重试无益且高频重试会加剧风控画像**；**429 / 503 仍按 `max_retries` 重试**。报告侧差异化文案同步（`llm_content` / `llm_module_info`）
- **文档**：手册新增「端点级节流（`pacing`）」章节（字段表、与全局并发的关系、403 语义）；技术设计新增 §4.2.1（调用链图 + 性质表）

**测试**：+19 例（`test_llm_pacing.py` 16 + `test_config_llm_multi.py` 3）。**真实调用路径实测**（MockTransport）：无约束端点 3 次调用 0.002s；`min_interval=0.2` 端点相邻间隔稳定 0.200s；`max_retries=2` 下 403 仅发 1 次请求且失败原因 `quota_exceeded`。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.4（2026-09-15 ~ 2026-09-25）
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
