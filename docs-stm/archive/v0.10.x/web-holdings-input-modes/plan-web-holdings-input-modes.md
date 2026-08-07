# Web 持仓输入模式：试算隔离 vs 正式共享 —— 实现设计定稿

> 文档版本：0.10.12-dev（计划层中间文件，非发布文档）
> 关联：review-findings.md rf-261 · plan.md plan-25 · 已确认方案基线（2026-08-07 探讨收敛）
> 状态：**20 轮打磨收敛定稿，待实现**
> 本文件为「中间计划文件」，实现完成并验证后归档至 `docs-stm/archive/` 对应版本目录。

---

## 1. 结论摘要

rf-261 的根因：web 上传跑 both/full 时，`capture_snapshot`（`report/_snapshot.py`）基于**本次上传的临时持仓**把快照持久化到**三渠道共享**的 `data/history/snapshots/`，TUI/CLI 后续报告的「快照差异/组合演进」被 web 试算数据污染。

已确认基线（不推翻，本文档仅打磨细化）：
- **① 临时试算（web 默认）**：上传保持 uuid 临时态（现状），快照写入独立子目录 `data/history/snapshots/web/`，TUI/CLI 读主目录自然排除试算快照。
- **② 正式更新（共享，显式选择）**：上传覆盖 `data/holdings/{holdings_filename}`（先备份旧文件），或**不上传直接用存量持仓文件**；快照入共享主目录，演进/对比真实生效。
- `data/cache/` 与 `data/state/` **保持共享不动**（按证券代码/机器键控，非持仓身份数据，隔离是伪需求）。

**打磨后的核心实现决策（20 轮收敛结果）**：

| 决策点 | 结论 | 一句话理由 |
|:--|:--|:--|
| namespace 接口 | `history_snapshot` 全部公开函数**增参数** `snapshot_namespace: str\|None = None`，默认 `None`=共享主目录 | 显式可追踪，向后兼容，零 TUI/CLI 改动；拒绝目录常量注入（全局态/不可测） |
| namespace 值 | 语义常量值 `"web"` → 目录 `data/history/snapshots/web/`（对齐已确认基线） | 试算隔离域 |
| 试算 prune | 复用 `history.snapshot_retention_days` / `snapshot_max_count`，`capture_snapshot` 的 prune 在**命名空间内**执行 | 不新增 TTL 配置，不启动清空（保留跨重启试算环比） |
| 试算环比闭环 | `capture_snapshot` / `build_evolution_data` / `build_snapshot_diff` 均按同一 namespace 读写 | 试算报告内部自洽，不读共享时间线 |
| 正式覆盖备份 | 单槽轮转 `.bak`：`data/holdings/{holdings_filename}.bak`，mkstemp+os.replace 原子写（架构约束 缓存原子写入） | KISS；显式正式动作，单回滚点足够 |
| 上传提升 | 正式+上传：**copy** 临时文件→正式路径（先备份旧文件），临时文件仍走 `discard_file` 清理 | copy 保持临时文件生命周期不变，语义清晰 |
| 用存量模式 | 路径**只从 `get_config()`** 派生（无用户传入路径 → 无目录穿越向量），文件缺失返回友好错误 `HOLDINGS_MISSING` | 防穿越 + 明确错误 |
| 配置 | **不新增任何配置键**；模式是 run 级参数（`mode`: trial/formal + `use_existing`） | YAGNI，避免配置校验/模板/版本号连锁改动 |
| 前端 | 模式单选（试算默认）+ 正式模式「输入来源」单选 + 覆盖确认勾选 | 默认安全，正式需显式确认 |

**净收益**：真正解决 rf-261（试算与共享时间线彻底隔离），无新配置、无 TUI/CLI 行为变化、不引入隐藏全局状态，改动集中在 `history_snapshot` 存储层 + web 入口层，测试隔离纪律自动覆盖。

---

## 2. 两模式定义

| 维度 | ① 临时试算（web 默认） | ② 正式更新（共享，显式选择） |
|:--|:--|:--|
| 输入 | 必须上传 `.xlsx`（uuid 临时文件，现状） | A. 上传覆盖正式文件；B. **不上传直接用存量** `data/holdings/{holdings_filename}` |
| 持仓身份 | 临时态，不落正式文件 | 上传→提升为正式文件；用存量→直接读正式文件 |
| 快照写入 | `data/history/snapshots/web/`（namespace=`"web"`） | 共享主目录 `data/history/snapshots/`（namespace=`None`） |
| 快照差异/组合演进 | 在 web 域内闭环（不读共享时间线） | 共享时间线真实生效 |
| `data/cache/` `data/state/` | 共享（不动） | 共享（不动） |
| basic 报告类型 | 不落快照（既有语义），但正式+上传仍会提升持仓文件 | 同左 |
| TUI/CLI 受影响 | 无（读主目录自然排除 web/） | 无（正式数据本就是共享口径） |

**设计边界**：
- 试算模式不产生任何「正式」副作用（不写正式持仓、不写共享快照）。
- 正式模式是**显式承诺**：持仓文件在 run 出队后、生成前即被提交（提升），报告失败不影响该提交——用户在正式模式下应预期「先更新文件，再生成报告」。如需纯试算请用模式①。

---

## 3. 快照 namespace 设计

### 3.1 接口签名（`src/python/report/history_snapshot.py`）

```python
def save(snapshot: SnapshotData, namespace: str | None = None) -> str: ...
def load_latest(namespace: str | None = None) -> SnapshotData | None: ...
def load_all(namespace: str | None = None) -> list[SnapshotData]: ...
def list_all(namespace: str | None = None) -> list[dict[str, Any]]: ...
def prune(
    retention_days: int = HISTORY_SNAPSHOT_RETENTION_DAYS,
    max_count: int = HISTORY_SNAPSHOT_MAX_COUNT,
    namespace: str | None = None,
) -> int: ...
```

- 内部新增纯函数 `_namespace_dir(namespace: str | None) -> str`：
  - `None` → `HISTORY_SNAPSHOT_DIR`（共享主目录，**向后兼容**：所有既有调用不变）。
  - `"web"` → `os.path.join(HISTORY_SNAPSHOT_DIR, "web")`。
  - 其余非空值按 `os.path.join(HISTORY_SNAPSHOT_DIR, namespace)` 处理（为未来第三方隔离域留口，但**不新增枚举约束**——YAGNI，仅文档说明）。
- `_list_snapshot_files(namespace=None)` 改为以 `_namespace_dir(namespace)` 为扫描根；`save`/`prune` 的 mkstemp 目录同理。
- **命名空间值校验**：`save`/`_list_snapshot_files` 对 `namespace` 做轻量白名单校验（仅允许小写字母/数字/`-`/`_`，拒绝 `..`/`/`/`\`），防未来用户可控 namespace 导致路径穿越（防御性，非当前攻击面）。

### 3.2 默认值语义与向后兼容

- `namespace=None` 语义 = 「共享主目录」，与现行为**完全一致**。TUI/CLI、既有单元测试零改动。
- 目录常量注入方案被否决：需在运行期替换 `HISTORY_SNAPSHOT_DIR`（模块级全局、非线程安全、并发 run 无法区分域），不可测。

### 3.3 消费链路 thread-through（参数式传递）

| 文件 | 函数 | 变更 |
|:--|:--|:--|
| `report/_snapshot.py` | `capture_snapshot(holdings, details, config, reporter, *, snapshot_namespace=None, **extra)` | 传给 `load_latest(namespace)` / `save(_snapshot, namespace)` / `prune(namespace=…)` |
| `analysis/portfolio_evolution.py` | `build_evolution_data(min_snapshots, top_n, *, snapshot_namespace=None)` | `load_all(snapshot_namespace)` |
| `analysis/snapshot_diff.py` | `build_snapshot_diff(threshold_pct, min_snapshots, *, snapshot_namespace=None)` | `load_all(snapshot_namespace)` |
| `report/_report_helpers.py` | `_inject_evolution_data(pipeline_data, *, snapshot_namespace=None)` / `_inject_snapshot_diff_data(…)` | 透传 |
| `report/_report_generation.py` | `_generate_report_both(…, *, snapshot_namespace=None)` / `_generate_report_full(…)` | 传给 `capture_snapshot` + 两个 inject |
| `report/orchestrator.py` | `generate_report(…, *, snapshot_namespace=None)` | 传给 both/full |

> **活路径确认**：`orchestrator.generate_report` 实际经 `_report_generation.py`（聚合门面）到达 both/full。`src/python/report/_pipeline.py` 为**遗留重复文件**（653 行，未被任何活代码 import），**不得**在其上实施 namespace 变更（见技术债 TD1）。

---

## 4. 正式覆盖 / 备份

### 4.1 新模块 `src/python/web/holdings_update.py`（语义名，职责内聚）

```python
def backup_holdings_file(holdings_path: str) -> str | None:
    """把现有正式持仓文件备份为 {holdings_path}.bak（单槽轮转）。

    - 文件不存在 → 返回 None（首次正式更新，无需备份）。
    - 原子写：copy → mkstemp 到同目录 → os.replace 到 .bak。
    - 返回 .bak 绝对路径。
    """

def promote_upload_to_holdings(temp_path: str, holdings_path: str) -> str:
    """把上传临时文件提升为正式持仓文件（先备份旧文件）。

    顺序：① backup_holdings_file(holdings_path) ② copy temp→holdings_path（mkstemp+os.replace）。
    失败语义：② 失败时旧正式文件未被破坏，.bak 保留原文件，可恢复。
    返回 holdings_path。
    """
```

- 备份位：`data/holdings/{holdings_filename}.bak`（与正式文件同目录，天然跟随 holdings_dir 隔离）。
- 保留策略：**单槽轮转**（KISS）。第二次正式更新覆盖 `.bak`。若用户需要多版本，自行管理文件版本（见技术债 TD3）。
- 原子性（架构约束 缓存原子写入）：一律 mkstemp + os.replace；`.bak` 与正式文件均不会出现半写态。
- 恢复路径：用户手动把 `.bak` 改回 `{holdings_filename}` 即可；文档说明。

### 4.2 失败回滚语义

- `backup` 失败（目标目录不可写）→ 抛错，**不继续** promote（旧文件与 `.bak` 均完好）。
- `promote`（copy）失败 → 旧正式文件未动，`.bak` 已生成；调用方报 run 失败，用户可用 `.bak` 还原。
- 注意：promote 发生在 run **出队后、生成前**。报告后续失败（LLM/网络）不影响已提交的正式文件——这是正式模式的语义，需在 UI 与文档中讲明。

---

## 5. 用存量模式（formal + use_existing）

- **路径派生**：仅 `os.path.join(config["holdings_dir"], config["holdings_filename"])`，来自 `get_config()` 快照（run 出队时取一次，与现有 config 快照语义一致）。**不接受任何请求参数传入路径** → 无目录穿越攻击面。
- **文件缺失**：`os.path.isfile(holdings_path)` 为 False → 返回错误码 `HOLDINGS_MISSING`，前端文案「正式持仓文件不存在：{holdings_dir}/{holdings_filename}。请先在正式模式上传覆盖，或改用临时试算」。
- **解析失败**：`read_holdings_with_flows` 异常 → 友好错误（exit_code 2 + 文案），不 500。
- **与 `get_config` 联动**：与现行 `_run_generation` 一致——每个 run 启动取一次配置快照；`_build_system_info` 已暴露 holdings_dir/filename/ready，供前端展示「当前正式持仓已就绪」提示（可选补 mtime）。

---

## 6. 配置

**结论：不新增任何配置键。**

- 模式是 **run 级参数**，随 `/api/runs` 请求提交（`mode`、`use_existing`），默认 `mode="trial"`。
- 试算域 prune 复用既有 `history.snapshot_retention_days` / `history.snapshot_max_count`（`_config_defaults._DEFAULT_CONFIG["history"]` 已有，无需改）。
- 否决项：
  - `features.web_input_mode` 全局默认模式键 —— YAGNI，模式属单次行为选择，非持久偏好；且新增键需同步 `_config_defaults` / `_validation` / 模板 / 版本一致性脚本，成本高收益低。
  - 按 namespace 独立保留天数 —— 过度设计；60 天/365 个上限对试算域足够。

---

## 7. 前端（index.html + static/main.js）

### 7.1 表单结构

`生成区`新增「生成用途」单选（`name="input_mode"`，默认 `trial`）：

```
[○] 临时试算（推荐）—— 不更新正式持仓，快照隔离，安全尝试
[●] 正式更新 —— 覆盖 data/holdings/个人投资持仓信息.xlsx，快照共享生效
```

选择 `formal` 时展开：
- 「输入来源」单选 `name="use_existing"`（默认 `false`）：
  - `[●] 上传新文件覆盖正式持仓`（需已上传）
  - `[○] 直接用当前正式持仓文件`（无需上传）
- 覆盖确认勾选 + 警示条（红底）：`将覆盖 {holdings_dir}/{holdings_filename}，旧文件备份为 .bak，并写入共享快照时间线`。确认勾选未选中 → 生成按钮禁用。

### 7.2 main.js 逻辑

- `body` 构建：
  - `mode`：`els.inputMode.value`（`trial`/`formal`）。
  - `use_existing`：仅 formal 且选中「直接用正式持仓」时为 `true`；此时 **body 不携带 file_id**。
  - 试算/正式上传：仍携带 `file_id`。
- 按钮态：
  - 试算 或 正式-上传 → 沿用「须先上传」门控（现状）。
  - 正式-用存量 → **无需上传**，选中该项后直接启用生成按钮；页面顶部提示「将读取正式持仓文件生成报告」。
- 错误分支：新增 `HOLDINGS_MISSING` error_code 分支（文案直显，不前端硬编码映射——对齐现有 `error_code` 驱动约定）。
- 确认勾选状态参与按钮 disabled 计算；切回 `trial` 时清除确认勾选。

### 7.3 a11y / 移动端

- 单选/勾选用原生 label 包裹（键盘可达）；警示条 `role="alert"` `aria-live="polite"`；375px 下纵向堆叠（沿用现有响应式规则）。

---

## 8. 风险登记表（等级 + 缓解）

| # | 风险 | 等级 | 缓解 |
|:--|:--|:--|:--|
| R1 | namespace 参数遗漏某条快照读写路径 → 污染仍残留（如遗漏 `snapshot_diff` 或某个 inject） | 中 | 快照读写**全部收敛**到 `history_snapshot` 公开函数；新增 `grep load_all/load_latest/save/prune` 调用点核对步骤；测试显式断言「共享 load_latest 不含 web/ 快照」 |
| R2 | 正式覆盖在测试中误写**真实** `data/holdings/` 持仓文件 | 中 | conftest 新增 opt-in fixture `holdings_path_isolated`（见 §11）；形式化测试一律使用，绝不触碰真实 `data/holdings/` |
| R3 | 跨进程同秒快照文件名碰撞（双 web 实例 / web+TUI 并行写 web/ 或共享域） | 低 | 单 worker 串行队列内进程内无并发（现状）；跨进程为既有共享目录同样存在的风险（现状可接受）。可选加固：时间戳追加 `%f` 微秒（保持字典序），标记为**低优先、不在本迭代范围**（YAGNI） |
| R4 | 用户在正式模式误操作覆盖持仓 | 中 | 显式单选 + 覆盖确认勾选 + 红底警示条 + `.bak` 单槽备份兜底恢复 |
| R5 | 正式-用存量读到**陈旧**持仓文件，用户未察觉 | 低 | UI 展示正式文件就绪状态（`_build_system_info.holdings_ready` 已有）；可选补 mtime 展示（低成本，纳入本迭代） |
| R6 | 试算域快照无限增长 | 低 | 复用 `snapshot_max_count=365` 在 namespace 内 prune（仅 both/full 触发，与共享域同语义）；不启动清空（保留跨重启试算环比） |
| R7 | `web/` 目录名与「试算」语义轻微漂移（若未来 TUI 也加试算，会复用 web/ 域） | 低 | 文档明示 `web/` 即「web 试算隔离域」；namespace 值是一处常量，未来如语义扩展改名代价=改 1 常量（试算快照可弃） |
| R8 | `get_cache_stats` 不统计 web/ 试算快照，TUI 用户困惑「快照数少了」 | 低 | 属预期（试算不占共享统计口径）；文档说明；不改 `cache/operations.py` |

---

## 9. 技术债登记

| # | 债务 | 影响 | 处置 |
|:--|:--|:--|:--|
| TD1 | `src/python/report/_pipeline.py` 为 `_report_generation.py` 的**遗留重复文件**（653 行，未被活代码 import，仅一测试引用其 `_report_llm_module_results`） | namespace 变更若误改 `_pipeline.py` 会造成双份漂移；未来若误接线会丢失 namespace | 本迭代**不动** `_pipeline.py`，在其文件头加注释指向 `_report_generation.py`（活路径）；清理列为独立重构项（非本迭代） |
| TD2 | namespace 参数穿透约 8 个签名（`history_snapshot`×5 + `capture_snapshot` + 2 inject + `generate_report`×2） | 签名冗长；若出现第 3 个隔离域，参数化继续膨胀 | 接受（显式可追踪 > 隐藏上下文变量）；若未来 >2 域，重构为 `SnapshotStore` 类（保存目录/namespace 状态）统一收敛 |
| TD3 | `.bak` 单槽轮转，第二次正式更新丢失上一版备份 | 回滚窗口仅 1 版 | 接受（KISS，正式动作显式）；文档说明；如需多版本由用户自行文件管理 |
| TD4 | 试算快照不清空，仅 prune（保留天数/数量） | 磁盘上残留试算 JSON，量小（数百 KB/份） | 接受（保留跨重启试算环比）；上限 365 兜底 |
| TD5 | `web/` 命名 vs `trial` 语义 | 命名漂移（见 R7） | 文档明示映射，不追改（对齐已确认基线） |

---

## 10. 测试矩阵（最小充分集）

> 所有新增/修改用例**必须**带 pytest marker（测试标记强制）；edge 场景入 `*_edge.py`（边缘测试文件隔离）；LLM/网络一律 mock（`_block_external_network` 自动兜底）；不触碰真实 `data/holdings/`（用 `holdings_path_isolated`，见 §11）。

| # | 测试 | 归属 | 断言要点 |
|:--|:--|:--|:--|
| T1 | `history_snapshot` namespace 单元：`save(namespace="web")` / `load_latest` / `load_all` / `prune` | unit_report | 写文件落在 `{HISTORY_SNAPSHOT_DIR}/web/`；默认 namespace 读主目录；`load_latest(namespace="web")` 不含主目录文件；`prune(namespace="web")` 只清 web/ |
| T2 | namespace 值安全：非法值（`../`、`/`、`\`、空串）拒绝 | unit_report_edge（`*_edge.py`） | 抛错/忽略，不越界写盘 |
| T3 | `capture_snapshot(snapshot_namespace="web")`：load_latest/save/prune 均在 web 域内闭环 | unit_report | 两次调用试算 → 环比 diff 基于 web 域上一份；主目录无新增 |
| T4 | `build_evolution_data(snapshot_namespace="web")` / `build_snapshot_diff(snapshot_namespace="web")` 只聚合 web/ 快照 | unit_report | 共享目录放 1 份 + web/ 放 3 份 → web 域演进 available，默认域不含 web/ |
| T5 | `generate_report(…, snapshot_namespace="web")` both 路径：快照落 web/，共享目录不变 | unit_report（mock 全 API） | 管线集成，断言 `os.listdir(主目录)` 不含本次时间戳快照 |
| T6 | web handler 试算默认：上传→run（不带 mode）→快照落 web/ | unit_web | 默认 mode=trial；主目录零新增；temp 文件 finally 清理 |
| T7 | web handler 正式+上传：run(mode=formal) → 正式文件被覆盖、`.bak` 生成、快照落共享、temp 清理 | unit_web（`holdings_path_isolated`） | 断言 holdings_path 内容=上传内容；`.bak`=旧内容；共享目录含本次快照 |
| T8 | web handler 正式+用存量：run(mode=formal, use_existing=true, 无 file_id) → 读正式文件、快照共享 | unit_web（`holdings_path_isolated`） | body 无 file_id 放行；正式文件缺失 → `HOLDINGS_MISSING` 404/错误信封 |
| T9 | 参数校验：trial 无 file_id → BAD_PARAM；formal+use_existing+有 file_id → BAD_PARAM；非法 mode → BAD_PARAM；过期 file_id → FILE_EXPIRED | unit_web | 枚举/组合校验全覆盖 |
| T10 | 共享演进排除 web/：共享域已有 3 份 + web/ 已有 3 份 → 默认 `build_evolution_data()` 只算共享 3 份 | unit_web（或 unit_report） | 反污染回归（rf-261 直接断言） |
| T11 | `get_cache_stats` 忽略 web/ 子目录 | unit_report | `snapshot_files` 不含 web/ 内 JSON |
| T12 | 冒烟扩展：`scripts/smoke-web.py` 增模式选择冒烟（radio 存在、正式需确认勾选、用存量提交无 file_id） | unit_web（test_smoke_web.py） | 断言数 9→N，保持可复跑 |

**并发/边界**（低优先，可选）：T13 双线程并发 `save` 到 web/ 不同时间戳不互踩（跨进程碰撞不在单测覆盖，见 R3）。

---

## 11. 逐文件改动清单

| 文件 | 改动 |
|:--|:--|
| `src/python/report/history_snapshot.py` | 公开函数增 `namespace` 参数；新增 `_namespace_dir()` + namespace 白名单校验；`_list_snapshot_files(namespace)` 以 namespace 目录为根 |
| `src/python/report/_snapshot.py` | `capture_snapshot` 增 `snapshot_namespace`，透传 load_latest/save/prune |
| `src/python/analysis/portfolio_evolution.py` | `build_evolution_data` 增 `snapshot_namespace` → load_all |
| `src/python/analysis/snapshot_diff.py` | `build_snapshot_diff` 增 `snapshot_namespace` → load_all |
| `src/python/report/_report_helpers.py` | 两个 `_inject_*` 增 `snapshot_namespace` 透传 |
| `src/python/report/_report_generation.py` | `_generate_report_both` / `_generate_report_full` 增 `snapshot_namespace`，透传 capture_snapshot + inject |
| `src/python/report/orchestrator.py` | `generate_report` 增 `snapshot_namespace=None`，透传 both/full |
| `src/python/web/holdings_update.py` | **新建**：`backup_holdings_file` / `promote_upload_to_holdings`（语义名） |
| `src/python/web/handlers.py` | `_handle_create_run` 增 `mode`/`use_existing` 解析与枚举校验；`_run_generation` 按模式分派（trial→namespace="web" 读 temp；formal→提升或读正式文件，namespace=None）；`_build_system_info` 可选补正式文件 mtime 供 use_existing 提示 |
| `src/python/web/templates/index.html` | 生成区增「生成用途」单选 + 正式模式「输入来源」单选 + 覆盖确认勾选 + 警示条 |
| `src/python/web/static/main.js` | body 构建（mode/use_existing/可省略 file_id）、按钮态、`HOLDINGS_MISSING` 分支 |
| `src/test/unit/report/` | 新增 `test_history_snapshot_namespace.py`（+`_edge.py`）、`test_capture_snapshot_namespace.py`、`test_evolution_namespace.py` |
| `src/test/unit/web/` | 扩展 `test_handlers.py` 模式分派用例；新增 `test_holdings_update.py`；扩展 `test_smoke_web.py` |
| `src/test/conftest.py` | 新增 opt-in fixture `holdings_path_isolated`（见下） |
| `docs-stm/managements/technical.md` | 功能语义命名表新增行（见 §12）；架构约束无新增（缓存原子写入/测试标记强制/边缘测试文件隔离/测试敏感路径隔离 已覆盖） |
| `docs-stm/managements/folders.md` | 目录树登记 `src/python/web/holdings_update.py` |
| `docs-stm/manuals/how-to-start.md` / `how-to-config.md` / `faq.md` | Web 模式两模式说明、正式覆盖/备份、用存量入口、FAQ（见 §12） |
| `docs-stm/managements/changelog.md` | 新条目 |
| `src/python/report/_pipeline.py` | **仅**文件头加注释「遗留重复文件，活路径见 `_report_generation.py`」（TD1，防误改） |

**conftest 新增 fixture**（opt-in，非 autouse）：

```python
@pytest.fixture
def holdings_path_isolated(tmp_path, monkeypatch):
    """把 holdings_dir/holdings_filename 重定向到临时目录（正式覆盖类测试专用）。

    防止正式模式测试覆盖真实 data/holdings/。autouse 不可用——部分既有测试
    断言默认 holdings_dir 路径，全量重定向会破坏它们。
    """
    import src.python.config._config_defaults as _cfg_defaults
    monkeypatch.setitem(_cfg_defaults._DEFAULT_CONFIG, "holdings_dir", str(tmp_path / "holdings"))
    monkeypatch.setitem(_cfg_defaults._DEFAULT_CONFIG, "holdings_filename", "测试持仓.xlsx")
    from src.python.config._core import _clear_config_cache
    _clear_config_cache()
```

> web/ 命名空间子目录天然隔离：`conftest._isolate_sensitive_paths` 已把 `HISTORY_SNAPSHOT_DIR` 指向 tmp，`web/` 是其下子目录，**无需**新增 patch。

---

## 12. 文档清单

- **technical.md 功能语义命名表**（`<!-- semantic-index:start -->` 内新增行，供 `check-semantic-index.py` 正反向校验）：

| 语义 slug | 中文名（文档/UI） | 归入章节 | 决策链环节 | config 开关 |
|:--|:--|:--|:--|:--|
| `snapshot_namespace` | 快照隔离命名空间（试算域 `web` / 共享主目录） | 快照存储/Web 输入 | 输入隔离 | 无（run 级参数） |
| `web_input_mode` | Web 输入模式（试算/正式） | Web 输入 | 输入隔离 | 无（run 级参数 `mode`） |
| `use_existing` | 直接用正式持仓文件 | Web 输入 | 输入隔离 | 无（run 级参数） |
| `holdings_update` | 正式持仓更新（备份 + 提升） | Web 输入 | 输入隔离 | 无 |

- **how-to-start.md**（Web 模式节）：两种生成用途的入口与差异；正式模式会覆盖 `data/holdings/` 并备份 `.bak`；用存量无需上传。
- **how-to-config.md**：无新键；注明 `history.snapshot_retention_days` / `snapshot_max_count` 同样作用于试算快照域。
- **faq.md**：①「Web 生成会不会弄乱我 TUI/CLI 的历史快照？」→ 默认试算隔离，正式才共享；②「正式更新后想反悔？」→ 用 `.bak` 还原；③「正式-用存量为什么读的是旧文件？」→ 提示先确认正式文件是否为最新。
- **folders.md**：目录树补 `src/python/web/holdings_update.py`。
- **changelog.md**：新条目（试算隔离 + 正式共享双模式）。

---

## 13. 实施顺序与门禁

### 13.1 实施顺序（依赖驱动）

1. **存储层**：`history_snapshot.py` namespace 支持 + `_namespace_dir` + 白名单校验 → T1/T2。
2. **消费层**：`capture_snapshot` / `build_evolution_data` / `build_snapshot_diff` / 两个 `_inject_*` 参数透传 → T3/T4。
3. **编排层**：`generate_report` + `_report_generation` 参数透传 → T5。
4. **web 入口**：新建 `holdings_update.py` → `handlers.py` 模式分派与校验 → T6/T7/T8/T9/T11 + conftest `holdings_path_isolated`。
5. **前端**：`index.html` + `main.js` 模式 UI → T12（冒烟扩展）。
6. **文档与门禁扫描**：technical 语义表 / folders / manuals / changelog + `_pipeline.py` 注释。

### 13.2 门禁（P0，提交前必须全绿）

- `.venv/bin/python scripts/test_runner.py --mode dev-verify`（核心单元 + 基础场景快速验证，含新用例）。
- `.venv/bin/python scripts/check-code-traces.py --ci`（代码历史痕迹 + 任务编号标识符检查——本设计全程语义名，无 `plan-25`/`rf-261` 进标识符）。
- `.venv/bin/python scripts/check-doc-traces.py --ci`（文档历史痕迹）。
- `.venv/bin/python scripts/check-task-numbering.py --ci`（本计划文件不涉及新增 plan/rf 编号，rf-261 仍在待处理表；实现完成后按纪律更新）。
- `.venv/bin/python scripts/check-semantic-index.py --ci`（新增语义行正反向校验通过）。
- `.venv/bin/ruff format --check`（非阻塞，可通过 `ruff format` 自修）。

### 13.3 合入门禁（P1）/ 发布门禁（P2）

合并/发布前补跑 `test_runner.py --mode verify`（P1）与 `verify,regression`（P2），与现有门禁一致，无新增特例。

---

## 14. 预估工作量

| 阶段 | 子项 | 预估 |
|:--|:--|:--|
| 存储+消费+编排层 | namespace 参数化 + 5 处消费方 + 测试 | 0.5d |
| web 入口 | `holdings_update.py` + handler 模式分派 + 校验 + 测试 | 0.5d |
| 前端 | 模式 UI + main.js + 冒烟扩展 | 0.5d |
| 文档与门禁 | technical/folders/manuals/changelog + 扫描脚本核验 | 0.5d |
| **合计** | | **2d**（对齐 plan-25） |

---

## 附录 A：20 轮打磨轨迹（每轮一句话）

1. **快照接口**：定「参数式 `snapshot_namespace`」而非目录常量注入——显式、可测、向后兼容（默认 None=共享）。
2. **prune/生命周期**：试算域复用 `history.snapshot_retention_days/max_count` 在 namespace 内 prune，不启动清空（保留跨重启试算环比）。
3. **试算环比闭环**：capture_snapshot + evolution + snapshot_diff 全部按同一 namespace 读写，试算报告自洽。
4. **并发**：确认单 worker 串行队列消除进程内并发；跨进程同秒碰撞为既有风险，标记低优先、本迭代不加微秒后缀（YAGNI）。
5. **正式备份**：定单槽 `.bak`（mkstemp+os.replace 原子），失败不继续 promote，`backup→promote` 两段式。
6. **用存量安全**：路径仅从 `get_config()` 派生（无穿越向量），缺失返回 `HOLDINGS_MISSING` 友好错误。
7. **配置**：否决新配置键——模式为 run 级参数，避免配置/模板/版本号连锁改动。
8. **一致性**：正式覆盖后旧共享快照保留、演进显示持仓跳变为既有 TUI 同语义，无需特判。
9. **上传提升**：定 copy（非 move）提升，临时文件仍走 `discard_file` 清理，生命周期语义不变。
10. **前端 UX**：模式单选（默认试算）+ 正式「输入来源」+ 覆盖确认勾选 + 红底警示条；用存量免上传。
11. **测试矩阵**：收敛为 12 条最小充分集（含 rf-261 反污染直接断言 T10）。
12. **文档**：补齐 technical 语义表/folders/manuals/changelog 清单。
13. **风险重审**：登记 8 项风险，R2（测试误写真实持仓）定 opt-in fixture 隔离。
14. **技术债重审**：识别 TD1 `_pipeline.py` 遗留重复文件并明示「不在其上改 namespace」。
15. **收益/成本**：确认解决 rf-261 且不过度工程——无新配置、无隐藏全局态、TUI/CLI 零改动。
16. **测试隔离**：新增 opt-in `holdings_path_isolated` fixture；web/ 子目录随 HISTORY_SNAPSHOT_DIR 自动隔离，无需新 patch。
17. **缓存统计**：`get_cache_stats` 天然忽略子目录（isfile 过滤），零改动，文档说明口径。
18. **语义命名**：定 `snapshot_namespace`/`web_input_mode`/`use_existing`/`holdings_update` 并登记语义表，namespace 值 `"web"` 为存储键豁免。
19. **实施顺序**：存储→消费→编排→web 入口→前端→文档六阶段，P0 门禁五脚本清单化。
20. **定稿**：全文档收敛，工作量 2d，遗留风险与推荐下一步见文末。

## 附录 B：遗留风险与推荐下一步

- **遗留风险**：R1（namespace 穿透遗漏）是唯一「中且影响正确性」项——以「读写全部收敛 history_snapshot 公开函数 + 反污染断言测试」双重缓解；R3（跨进程碰撞）与 TD1（遗留 `_pipeline.py`）为已知未消项。
- **推荐下一步**：① 按 §13.1 顺序实施，先落 T1/T2（存储层独立可验证）；② 实施期间同步登记 review-findings 新发现（编号源 rf-next=266）；③ 完成后更新 rf-261 至已修复、plan-25 归档，并按「发布数据文档刷新」纪律跑 `collect-test-coverage.py` 更新 test-coverage/folders 快照。
