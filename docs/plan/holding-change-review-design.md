# 持仓变动复盘（holding_change_review）设计 —— plan-76（快照事件级）

> **状态**：设计 + 待门槛判定（先决门槛未过不实施）。
> **路线**：原「手工交易日志」路线经可行性评估改为**快照事件级**——持仓快照历史与差异引擎已内建，零手工；代价是结构级精度（不承诺逐笔胜率与精确持有期）。
> **参照**：Vibe-Trading `agent/src/skills/trade-journal`（journal schema 与归因分析）+ `agent/src/shadow_account`（extract→render 闭环形态）。
> **研究背景**：见 `vibe-trading-borrow-candidates-research.md` §2.1。

## 1. 动机与价值

当前输入只有**持仓快照**（每 worksheet 一个账户、固定 4 列），系统知道「你现在持有什
么」，不知道「你做过什么、为什么做」——买卖历史从未被结构化复盘。而快照历史实际上
已在自动积累（`data/history/snapshots/`，每次报告落一份，差异引擎 `fetcher/history_diff`
内建）：**把连续快照差分为变动事件，即可零手工得到「你做过什么」这一侧**——事件清单
（新增/加仓/减仓/清仓）、变动频率、仓位结构演变、区间市值贡献分解，是 LLM 智囊团复盘
从「宏观局势评述」下沉到「你的具体操作」的关键输入，也是 plan-70 决策反思闭环的真实
成交侧数据源（意图 vs 变动对账，只读）。

**能力边界（诚实声明）**：事件是**区间净额推断**，非逐笔成交——精确成交日、逐笔胜率/
盈亏比、已实现出场盈亏、费用均超出快照信息天花板，本设计**不产出**这些指标（沿用
`analysis/snapshot_diff.py` 的「快照不含则不派生、不虚构」设计边界先例）。

## 2. 先决门槛（go-no-go，未过则归档未采纳）

1. **数据可得性（快照侧）**：去重后有效快照 ≥12 期，且累计变动事件 ≥10 个（保证有
   可复盘的结构）。评估时点存量参考：2026-10 实测本机 87 期（60 天保留窗口内）。
   有效快照不足 → 报告呈现占位而非硬算（同 `snapshot_diff` 的 `available=False` 形态）。
2. **口径可判定**：事件分类口径唯一可解释——份额净变动 >0 → 新增/加仓、<0 → 减仓/清仓、
   =0 → 不变（同一持仓上期为 0 → 新增）；同期重复报告按日去重不算新期。已知局限
   （区间内多笔折叠、净额≈0 不可见、分红再投混入份额变动）在报告与文档中**显式标注**，
   结论限定在结构级。
3. **价值验证**：结构级复盘结论（变动清单/频率/结构演变/意图对账）经用户确认
   「说得对、有启发」（人工比对标，仿 plan-71 转正判据 ②）。

## 3. 语义命名（先定名再设计）

| 语义名 | 层 | 说明 |
|---|---|---|
| `change_event` | 契约 | 快照区间净变动事件结构（代码/名称/方向/份额差/市值差/区间起止） |
| `holding_change_events` | analysis | 快照序列 → 事件表（去重 + 复用差异引擎分类，纯函数） |
| `holding_change_metrics` | analysis | 纯计算：变动频率/加减清仓结构/区间贡献分解/意图对账 |
| `holding_change_panel` | report | Excel/HTML 复盘章装配（含 LLM 归因块） |
| `holding_change_llm_review` | llm | LLM 归因 prompt 组（变动动机/与既有信号对账） |
| `holding_change_review` | config | 开关（`config/features.py` 唯一登记，实验组默认关） |

原手工日志路线的语义名（`trade_journal`/`journal_loader`/`journal_metrics` 等）随路线
废弃，不再使用。

## 4. 数据源约定

**唯一数据源：既有持仓快照历史**（无新输入文件、无手工维护面）。

| 项 | 约定 |
|---|---|
| 存储 | `data/history/snapshots/snapshot_{timestamp}.json`（`report/history_snapshot.py` 持久化，原子写入原语） |
| 字段 | 每持仓 `code/name/shares/cost_price/market_value/total_pnl/cost_total` + 组合合计 + `timestamp` |
| 读取 | `report/history_snapshot.load_all()`（只读消费；`analysis/snapshot_diff.py` 已有消费先例） |
| 差异引擎 | `fetcher/history_diff.py::HistoryDiff.compute`（新增/清仓/加仓/减仓分类直接复用，不自写 diff） |
| 去重 | `analysis/portfolio_evolution._dedup_by_date`（按日去重；同期重复报告环比恒 0 的教训见 `fund_concentration`） |
| 事件方向 | 按时间排序后**逐对快照差分**展开为事件序列，事件携带区间 `[t_prev, t_now]`（区间即事件的时间精度） |
| 保留策略 | 现行 `HISTORY_SNAPSHOT_RETENTION_DAYS=60` / `MAX_COUNT=365` 为**滚动窗口**，超期快照被清理——迭代 1 须评估拉长保留或滚动归档，否则长周期复盘被截断（属设计动作，非新增外部数据） |
| 设计边界 | 快照不含成交日期/单价/费用/出场价 → **不派生**逐笔指标（沿用 `snapshot_diff` 边界先例，不虚构） |
| 手工日志 | 原 `data/trade_journal/` xlsx 路线**废弃**，不建目录、不留兼容读取 |

## 5. 迭代设计

四个迭代串行推进，每个迭代单独可合并（P0 门禁绿）；前置依赖未满足不得开工。

| 迭代 | 范围 | 前置依赖 | 产出物 |
|---|---|---|---|
| 1 事件抽取与契约 | `holding_change_events`（快照按日去重 + 逐对差分 + `change_event` 契约 + 缺字段降级）；**快照保留策略评估**（60 天滚动截断 → 拉长/归档方案定稿） | 先决门槛 1（快照存量就绪） | `change_event` 契约 + 事件表纯函数 + 保留策略决定 + 契约用例 |
| 2 指标纯计算 | `holding_change_metrics`（变动频率/加减清仓结构计数/区间市值贡献分解——份额变动贡献与价格变动贡献/与 `decision_ledger` 意图对账只读列表）；纯函数、离线、可单测 | 迭代 1（契约定型） | 指标与对账纯函数 + 手算对照用例 |
| 3 报告双端 | `holding_change_panel` Excel 区块 + HTML 章（事件表/频率/结构演变/意图对账；「区间净额推断、非逐笔」标注随表呈现）；开关 `holding_change_review` 注册（默认关，实验组） | 迭代 2（指标就绪） | 双端章 + 开关注册 |
| 4 LLM 归因与文档登记 | `holding_change_llm_review` prompt 组（变动动机 + 与 `signal_ledger` 历史信号对账：当时信号说什么、实际怎么动），进统一附录（指纹携带，同 plan-73 单源纪律）+ 降级矩阵（无 LLM → 归因块隐藏、量化照常）；五份文档同步 + 门槛判定记录 | 迭代 3（管道通）；先决门槛 3（结论人工认可） | prompt 组 + 指纹接线 + 文档同步 + 判定记录 |

## 6. 红线与约束

- **不重叠**：`decision_ledger`（LLM 决策登记）与本特性是「意图 vs 变动」两侧，只读
  对账、不互写；`signal_ledger` 只读。
- **不虚构**：快照没有的字段（成交日/单价/费用/出场价）一律不派生；结论限定结构级，
  报告显式标注「事件为区间净额推断」。
- **只读消费**：`data/history/snapshots/` 快照目录测试与运行均不回写；本特性不新增
  持久化文件。
- **降级**：有效快照 <2 期 → `available=False` 占位（同 `snapshot_diff` 形态），不中断
  报告；LLM 缺席 → 量化照常出、归因块隐藏。
- **隐私**：快照含真实持仓与盈亏，报告产物留在本地 `reports/`，不外传（LLM 调用仅发送
  必要摘要字段，与现网纪律一致）。
- **测试纪律**：全部 mock/临时快照文件；网络层既有守卫生效；新增 marker 注册 conftest。

## 7. 验收标准（按迭代量化）

每个迭代全项满足才算通过；未过不得进入下一迭代。

| 迭代 | 量化验收标准 |
|---|---|
| 1 事件抽取与契约 | fixture 快照序列（≥4 期，覆盖新增/加仓/减仓/清仓/不变/同期重复）差分事件与手算逐条一致（action 与份额差容差 0）；同期重复报告去重后期数不变（断言）；有效快照 <2 期 → 占位不抛异常；新增单测 ≥8 项全绿；`data/history/` 快照只读（mtime 校验不变） |
| 2 指标纯计算 | 频率/结构计数/贡献分解 ≥5 组手算对照一致（容差 0，分解两分量之和 = 区间市值变化，恒等式断言）；意图对账列表只读呈现（不回写 ledger 断言） |
| 3 报告双端 | 双端渲染一致断言全绿；关态输出哈希与基线逐字节一致；开关在 `config/features.py` 注册表断言成立；「非逐笔」标注随事件表同现（缺失即红） |
| 4 LLM 归因与文档登记 | 降级态（无 LLM）逐字节回退；改指纹入参 → 指纹值变化断言成立；LLM mock 下真实 API 调用数 = 0；先决门槛三项判定记录齐全；P0 `test-runner.py --mode dev-verify` 0 失败；五份文档同步后 `check-doc-drift --ci` 0 finding |

## 8. 架构定位与依赖方向

| 构件 | 落点层 | 依赖方向与约束 |
|---|---|---|
| `holding_change_events` | analysis 纯计算 | **零网络**：不注册进 provider 链路、不经熔断；快照读取复用 `report/history_snapshot.load_all()`（既有 `analysis/snapshot_diff` 消费先例）；差异分类复用 `fetcher/history_diff.HistoryDiff` |
| `holding_change_metrics` | analysis 纯计算 | 零 I/O；区间天数口径经 `core/trading_calendar.py`（交易日计数）；复用 `metrics*` 原语不新造；`decision_ledger` 只读 |
| `holding_change_panel` | report 双端 | 章节序号经 `core/registry.py`（报告序号注册表）；pipeline_data 键先入附录 H（pipeline_data 契约）；图表带 `.chart-caption`（图下说明）；**默认关的实验章经 `report/_experimental_seams.py` 挂载点接入**（实验挂载点集中） |
| `holding_change_llm_review` | llm | 指纹经 `module_fingerprint.py` 单源构造（LLM 指纹单源）；调用走 Provider Chain（LLM 路由统一）；若独立成模块须在 `_llm_dispatch._MODULE_FNS` 与 `core/registry.py` 双注册（LLM 模块注册） |
| 开关 `holding_change_review` | `config/features.py` | 唯一登记点（开关注册表唯一），实验组默认关 + experiment_stats 观测 |
| 快照存储 `data/history/snapshots/` | 本地状态数据（既有基础设施） | 只读消费：测试隔离（测试数据隔离）、不入 git、保留策略调整走 `core/constants.py` 单点 |

依赖方向：`report` → `analysis.holding_change_metrics`（纯函数）← `holding_change_events`
备数（读快照）；`llm` 只消费 pipeline_data 摘要字段；`analysis` 不 import `report`/`llm`
（快照读取走 `report.history_snapshot` 属既有消费先例，不新增反向依赖形态）；
decision_ledger / signal_ledger 均只读对账，不互写。

## 9. 架构约束对照（逐条自查）

依据 `technical.md` §8「架构设计约束」逐条判定：✓ = 适用且本设计遵从；— = 不适用（附理由）。

| 约束 | 判定 | 遵从方式 / 不适用理由 |
|---|---|---|
| 原子写入 | ✓ | 本特性不新增持久化；快照存储本身经 `core/atomic_write.py`（既有） |
| 报告序号不可硬编码 | ✓ | 复盘章序号/页签名经 `core/registry.py` 与 `get_report_sheet_name()` |
| 日志统一 | ✓ | 事件抽取降级/快照不足告警走 `logging.getLogger("invest")` |
| LLM 模块注册 | ✓ | `holding_change_llm_review` 若独立成模块，在 `_llm_dispatch._MODULE_FNS` 与 `core/registry.py` 双注册 |
| 测试纪律（marker / edge 文件隔离 / 数据隔离） | ✓ | 用例带 marker；快照缺期/字段缺失等 edge 入 `*_edge.py`；`data/history/` 真实快照与配置路径测试只读隔离 |
| 渲染期数据不落全局 | ✓ | 复盘章数据经 render context 传递 |
| LLM 路由与凭据分离 | ✓ | 归因调用走 Provider Chain；凭据经 `credentials_ref`，不碰密钥值 |
| pipeline_data 契约 | ✓ | 事件表/指标键先入附录 H schema 再实现 |
| 图下说明 | ✓ | 若出结构演变图带 `.chart-caption`，随渲染分支同现 |
| LLM 指纹单源 | ✓ | 归因提示词承载的每段入参进指纹，由 `module_fingerprint.py` 构造 |
| 实验挂载点集中 | ✓ | 默认关的实验章经 `_experimental_seams.py` 接入，异常不中断主链路 |
| 开关注册表唯一 | ✓ | `holding_change_review` 只在 `config/features.py` 登记 |
| 交易日计数 | ✓ | 事件区间天数/频率口径一律交易日计（`core/trading_calendar.py`） |
| **不适用汇总** | — | 代码类型判定中心化（事件代码直接来自既有持仓/快照，不新增类型判定）、缓存统一管理（不直写缓存、事件不落缓存）、会话级复用/HTTP 客户端统一/Provider 多源链路必经（读本地快照零网络，不进 provider 链路）、新闻召回不改、着色不改、配置路径绝对化（快照目录为既有常量，若改保留策略仅涉常量值）、凭据源纪律（不经手凭据）、重试统一/节流统一（无新增重试/节流点，LLM 重试由 `api_base` 既有原语承担） |

## 10. 共享能力复用清单（防双实现）

| 能力 | 既有实现（符号） | 本设计复用方式 | 若重复实现的技术债 |
|---|---|---|---|
| 快照持久化与读取 | `report/history_snapshot.py`（`load_all`/`load_latest`/`save`/`prune`） | 只读消费，不自建快照存储与目录 | 二套快照 → 目录/保留双轨漂移 |
| 差异引擎 | `fetcher/history_diff.py`（`HistoryDiff.compute` → `DiffSummary`） | 事件 action/份额差/市值差直接复用其分类 | 自写 diff → 与报告环比两套口径互相矛盾 |
| 快照按日去重 | `analysis/portfolio_evolution`（`_dedup_by_date` 同族） | 同期重复报告去重后再差分 | 同期硬比 → 环比恒 0 误读（`fund_concentration` 已有教训） |
| 快照消费先例与边界纪律 | `analysis/snapshot_diff.py`（组合演进章 + 「不含则不派生」边界 + `available=False` 降级） | 沿用其设计边界声明与降级形态 | 第三套快照消费逻辑 → 边界口径漂移 |
| 区间天数/频率口径 | `core/trading_calendar.py` | 事件区间与频率天数一律经此 | 自建日历 → 长假前后假告警 |
| LLM 约束块单源 | plan-73 `constraint_block` 同构的统一附录注入 + `module_fingerprint.py` | 归因 prompt 入参与指纹同源 | 自拼指纹 → 预检永不命中 |
| LLM 降级矩阵 | `llm/skeleton.py` 既有降级形态 | 无 LLM 时归因块隐藏/量化照常 | 自建降级分支 → 降级行为不一致 |
| 报告写入 | 既有 Excel/HTML 写入器与折叠章模式 | 复盘章同构实现 | 自开写入路径 → 双端样式漂移 |
| 意图侧对账基准 | `core/decision_ledger`（只读） | 变动事件 vs 意图列表对照 | 与 plan-70 各写一套对账 → 口径分叉 |

## 11. 技术债防线

1. **不虚构边界固化**：快照字段缺失/不含 → 事件字段按「不可判定」降级并计数告警，
   绝不派生近似值（沿 `snapshot_diff` 边界先例；报告呈现缺项而非假数据）。
2. **去重单源**：同期重复报告按日去重只走 `portfolio_evolution` 既有原语，不写第二套
   （环比恒 0 误读的历史教训防线）。
3. **保留策略与复盘窗口匹配**：60 天滚动截断是长周期复盘的实际威胁——迭代 1 定稿
   拉长/归档方案并监测「最早快照跨度」，跨度不足复盘窗口时报告显式标注，不拿残缺
   序列给完整结论。
4. **单文件红线**：`holding_change_events`/`_metrics`/`_panel` 受 800 行红线守护，逼近即拆。
5. **LLM 块不污染缓存**：归因入参与指纹同源；降级态提示词与缓存键双不变（同 plan-73
   纪律），避免「开关看似生效实则全量重调」。
6. **局限标注常驻**：「区间净额推断、非逐笔」标注与事件表同生共死（渲染分支成对出现），
   防止后续迭代悄悄把结构级指标包装成逐笔结论。
7. **开关可撤销**：experiment_stats 观测不足 → 开关/章/需求条目一并摘除，不留僵尸分支
   （转正才进注册表）。
8. **测试卫生与计数同步**：过 `check-test-redundancy` 五类；删并后同步
   `test-coverage.md`/`folders.md` 计数；`data/history/` 真实快照测试只读。
9. **文档同步即门禁**：每迭代同回合同步文档，`check-doc-drift --ci` 绿才算完；迭代可
   独立合并（P0 全绿）。

## 12. 测试策略（按迭代）

通用纪律（每迭代生效）：用例标注 pytest marker（测试 marker）、edge 入 `*_edge.py`
（edge 文件隔离）、`data/history/` 真实快照与配置只读（测试数据隔离）、LLM mock 强制、
跨模块 patch 打在调用点所在模块、`check-test-redundancy --ci` 五类零违规。

| 迭代 | 测试类型 | 关键用例 | 隔离与 mock |
|---|---|---|---|
| 1 事件抽取与契约 | 单测 + edge | fixture 快照序列逐对差分手算对照（含新增/清仓/不变/同期重复）、缺字段降级、<2 期占位 | 临时快照 JSON（tmp_path）；真实 `data/history/` 只读（mtime 校验） |
| 2 指标纯计算 | 单测 | 频率/结构计数/贡献分解恒等式手算对照；意图对账只读（ledger 不回写断言） | 纯函数 fixture 注入（零 I/O）；交易日历用固定交易日序列 |
| 3 报告双端 | 场景测试 | 双端渲染一致、事件表列齐全、「非逐笔」标注同现、关态逐字节不变 | 输出目录临时化；LLM mock |
| 4 LLM 归因与文档 | 场景测试 + 门禁 | 归因块降级逐字节回退、指纹携带断言、LLM mock 调用数 = 0；`check-doc-drift` 绿 | LLM mock 强制（防费用/防依赖） |

## 13. 数据源依赖与稳定性考察

**结论先行**：**无新增外部数据源、无手工维护面**——唯一数据源是本地快照历史（自产）；
外部依赖仅剩既有的 LLM 调用链（多链降级与熔断已由既有体系治理）。稳定性风险从
「用户维护节奏」转为「快照序列自身质量」：

| 数据项 | 来源 | 稳定性风险 | 考察/监测指标 | 降级与防护 |
|---|---|---|---|---|
| 持仓快照序列 | 本机自产（`data/history/snapshots/`，每次报告落一份） | **60 天滚动保留截断长周期**；不跑报告的期间无记录；同期重复报告 | 有效期数（去重后）与最早快照跨度随报告回显；先决门槛 1（≥12 期且 ≥10 事件） | 迭代 1 评估拉长保留/滚动归档；跨度不足 → 报告标注复盘窗口；<2 期 → `available=False` 占位 |
| 快照字段质量 | 既有快照写入（份额可能为 0 的边角：持仓读入缺该代码） | 事件方向误判 | 缺字段事件计数告警 | 缺份额 → 事件标「不可判定」不虚构 |
| 份额变动混淆 | 分红再投/份额折算也会改 `shares` | 事件数虚高（非交易变动混入） | 口径文档显式声明该局限 | 结论限定结构级；不声称「成交笔数」 |
| LLM 归因 | 既有 Provider Chain（多链降级/熔断） | 端点故障/配额 | 既有 429 诊断与 pacing 回显 | 无 LLM → 归因块隐藏，量化照常（降级矩阵） |

**判定动作**：先决门槛 1 在迭代 1 入口复测（不只立项时点）；运行期有效快照跨度连续
2 次报告低于复盘窗口 → 先解决保留策略再谈价值验证；稳定性结论随迭代 4 判定记录归档。

## 14. 风险、回滚与文档同步义务

| 风险 | 影响 | 缓解 | 触发后的动作 |
|---|---|---|---|
| 快照存量不足（<12 期或 <10 事件） | 特性不可行 | 门槛 1 前置于迭代 1 入口 | 归档未采纳 |
| 净额塌缩/分红再投混淆致结论误导 | 用户据失真事件行动 | 「非逐笔」标注常驻 + 结论限定结构级 | 标注缺失视为验收失败 |
| 60 天滚动截断长周期复盘 | 序列残缺、频率失真 | 迭代 1 保留策略定稿 + 跨度回显 | 跨度不足 → 标注窗口，不给完整结论 |
| 意图对账误读为绩效归因 | 归因越界（对账只是列表对照） | 文案审校入迭代 3 验收 | 发现误导表述 → 改文案再合入 |
| LLM 归因不可用 | 归因块缺失 | 降级矩阵（量化照常） | 章隐藏不阻塞，既有链路治理 |

**回滚策略**：① 迭代级——每迭代独立提交、独立验收，未过不合入，出问题单次 revert。
② 功能级——`holding_change_review` 开关关闭即回现状（关态逐字节不变已由验收锁定）。
③ 数据级——只读消费既有快照、本特性零持久化，回滚**零数据残留**，快照基础设施不受
影响（保留策略若已调整，调回常量即可）。

**文档同步义务（每迭代同回同）**：`requirements.md`、`technical.md`（语义命名表 +
约束落点）、`testplan.md`（载体）、`changelog.md`、`folders.md`/`test-coverage.md`
（计数）；本特性**无用户手工输入面**，`manuals/` 仅在报告说明章节涉及复盘章时顺带更新；
完成判据 = `check-doc-drift --ci` 0 finding。
