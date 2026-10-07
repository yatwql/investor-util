# 限购信息接入调仓/建议可行性 — 设计方案

> 文档版本：0.12.2-dev
>
> 定位：**设计 + 已实施**（2026-10-03 按 §7 四迭代落地：受限索引与判定原语 → What-if 接线 → 回归网与零改动断言 → 文档登记与 P0 门禁全绿；随任务完成归档至 `docs/archive/`）。
>
> 关联计划：`plan-74`（plan-72 迭代 4，二期）；前置：plan-72 迭代 2（`purchase_status_data` 契约就绪）；方案来源：`fund-purchase-limit-design.md` §6/§8 迭代 4。
>
> 范围决策（plan-74 条目）：仅影响建议文案与路径选择，不改动既有调仓算法的数值计算；数据不可用/开关关时回退现网行为。

---

## 1. 背景与目标

**问题**：what-if 模拟当前不感知限购状态——目标基金限大额/暂停申购时仍给出可执行对比（如目标持仓为限购 100 元/日的标的）；也缺少「按日限额多久能执行完」的可执行性估算（「需 28 年」式无意义建议风险）。

**目标**：数据完备时，在 **what-if 目标持仓面**注入限购可行性判定与降级提示；调仓建议与行动摘要**不在范围**（三种候选操作全为卖出，申购限购不约束卖出，见 §8 决策）。数据不可用时**建议输出逐字节回退**到现网行为（零回归）。

**非目标**：

1. 不改动调仓算法的数值计算（偏离信号、份额取整、费用、现金——`rebalance`/`rebalance_advisor` 数值域不动）；
2. 不新增网络请求与配置路径（契约与开关复用 plan-72 资产）；
3. 不注入 LLM 提示词（plan-73 域，边界见其设计 §3.5）；不改持仓展示列（plan-72 域）。

## 2. 现状比对（立项前提核验）

> 回应 `rf-510` 教训——对 plan-74 自身的立项前提做同样核验。

### 2.1 前提修正：「申购合并」在确定性代码中不存在

`grep "申购合并|合并路径|merge_path"` 全仓**零命中**；`analysis/`、`report/` 中「合并」均为数据结构含义（FIFO 合并成本批次、合并报表、多账户按 code 合并）。**结论**：`fund-purchase-limit-design.md` §6 所述「『申购合并』路径降级」在当前代码中没有对应实体——同类持仓合并的话术仅存在于 LLM 自由文本（plan-73 已覆盖该面）。**本设计把动作对象重新定位为以下三个真实确定性面**。

### 2.2 建议面全景（真实代码）

| 面 | 计算点 | 输出契约/去向 | 本设计处置 |
|:--|:--|:--|:--|
| 调仓建议候选 | `analysis/rebalance_advisor.build_rebalance_advice`（候选自 `_candidate_from_rebalance` / `_candidate_from_discipline`） | `action_data` 内「③ 调仓建议」（`report/action_sheet.py`） | **不注入**（候选操作仅 `卖出减仓`/`止损`/`部分止盈`，现金回款模型——申购限购不约束卖出） |
| 行动建议摘要 | `analysis/action_advisor.build_action_data`（`_build_summary`） | `action_data` 契约 → 行动建议页签 | **不注入**（摘要是 `；` 计数拼接，无标的级申购语义——同上实锤） |
| What-if 对比 | `analysis/whatif.build_whatif_data(base, candidate)`（调用点 `report/whatif_operations.py`，handler 交互路径） | whatif 对比契约 → 模拟页签 | **注入**：目标持仓受限标的 → 落地受阻提示 |
| LLM 分析文本 | plan-73 统一附录 | 提示词 | 不注入（plan-73 域） |
| 偏离信号/数值计算 | `analysis/rebalance.py`（信号、置信度、静默） | 中间量 | **不注入**（数值域，非目标 1） |

### 2.3 数据通路

- 契约 `purchase_status_data` 已在 `report/orchestrator.py` 生成（L179）并入 pipeline（L262）；`build_action_data` 实际有 **4** 个调用点（orchestrator L221、`_report_generation.py` L363/L617、`excel_generator.py` L330）均在其后——同进程内可下传（**通路事实记录**：本设计不改该函数签名，4 点无需触碰）。
- whatif 为独立交互路径（`whatif_operations.py` 由 handler 调起）——需在该路径就地取得契约（report 层内 `compute_purchase_status_data(config)`，与 plan-72 同一装配函数）。**取数语义**：经限购表缓存（data_type `fund_purchase`，TTL 24h 与官方净值同源）——命中则零网络；未命中经既有链一次（四层降级，含备链与过期缓存）；取契约异常由 handler 兜底 → `{}`（§3.4），不阻断模拟。
- **分层方向**（技术文档 §7）：report → analysis 单向；analysis 现存 5 处**函数内 lazy import** 报告层读取类先例（data_status/历史快照/穿透分类）——约束为**不扩张该依赖**而非绝对禁令：判定所需数据以**纯数据形参**下传（契约 dict / 预格式化索引），格式化原语留在 `report/purchase_status.py` 单源；what-if 面全在 report 层，新增 `analysis/purchase_feasibility.py` 不 import report。

## 3. 设计

### 3.1 契约扩展：预格式化受限索引（单源渲染）

`report/purchase_status.py` 新增（与单元格/脚注/plan-73 约束块同居）：

```python
def build_restricted_index(contract: dict | None, holding_codes: list[str] | None) -> dict[str, dict]:
    """受限标的预格式化索引：code → {status, limit_text, next_open_text, level}。

    准入（任一不满足 → {}）：契约非 None（开关关时上游返 None）、available=True、
    时效非 expired（同模块 stale_level 判据）、持仓∩行集内存在非开放申购标的。
    """
```

- 字段值（状态词/日限额千分位/下一开放日「M月D日」/0 元限额→限额未知）**复用同模块格式化原语**——与 plan-73 约束块同一约束，禁止第二份数值解释；
- 产出点：`build_purchase_status_data` 构建期（与 plan-73 的 `constraint_block` 同处赋值），作为契约字段 `restricted_index` 登记；
- **消费方只拿到数据与字段值**，建议层的提示话术为静态模板（分析层常量），不复制格式化逻辑。

### 3.2 可行性判定原语（analysis 层，纯函数）

新增 `analysis/purchase_feasibility.py`（唯一判定入口）：

```python
FEASIBILITY_MAX_DAYS = 60  # 交易日：合并/建仓天数估算超过该值判定路径不可行

def evaluate_purchase_feasibility(
    code: str,
    amount: float | None,            # 建议买入/需合并金额（未知 → None，不估天数）
    restricted_index: dict[str, dict] | None,
) -> dict | None:
    """受限标的可行性判定。未受限/索引空 → None（无判定 = 现网行为）。"""
```

**判定矩阵**（受限时返回，字段全部来自索引与纯算术）：

| 索引状态 | 返回 | 说明 |
|:--|:--|:--|
| 限大额 + 日限额已知 + 金额已知 | `{kind: "limited", days: ceil(amount/limit), feasible: days<=60, ...}` | 超 60 交易日 → `feasible=False`（「需 N 个交易日（>60）不可行」） |
| 限大额 + 限额未知 或 金额未知 | `{kind: "limited", days: None, feasible: None}` | 只提示限购、不给天数（宁缺毋错） |
| 暂停申购 | `{kind: "suspended", next_open_text: ...}` | 提示下一开放日 |
| 0 元限额（解析层已转 None → 限额未知） | 同「限额未知」 | 单点转换仍在解析层 |

- 天数按**交易日**语义表达（约束：时间距离一律以交易日计）；`days` 上限仅用于判定，不做自然日换算；
- `days = math.ceil(amount / limit)`（交易日语义；`amount <= 0` 或 `limit` 非正一律视为「金额/限额未知」→ `days=None`，不给天数——宁缺毋错）；
- 场内/查无此码：索引不含该 code → `None`（无判定）。

### 3.3 接线点（唯一注入面 = What-if，形参缺省回退；另两面不在范围）

1. **调仓建议 —— 不在范围**：三种候选操作（`卖出减仓`/`止损`/`部分止盈`）**全为卖出腿**（`_candidate_from_rebalance`/`_candidate_from_discipline`，现金回款模型 `cash_after = cash + amount - fee`），申购限购不约束卖出——**不增形参、不判定、不标注**，`build_rebalance_advice`/`build_action_data` 签名零改动（§2.3 调用点清单仅作通路事实记录，防实施者误改四处调用）。
2. **行动建议摘要 —— 不在范围**：摘要是 `；` 计数拼接（「再平衡建议 N 条；…」），无标的级申购语义，注入无落点——`_build_summary` 零改动。
3. **What-if（唯一注入面）**（`whatif_operations.py` 就地取契约 → `build_restricted_index` → `build_whatif_data` 增形参）：目标持仓（candidate）中受限标的 → 对比结果附「落地受阻」提示块；基准持仓不受限不触发；**金额口径**：优先取 candidate 相对 base 的加仓金额（份额差 × 单价，字段以 `build_whatif_data` 实际结构为准，实施期首日核验）；不可得 → `amount=None` 只提示不估天数（宁缺毋错）。

### 3.4 降级矩阵（建议输出零回归）

| 情形 | 判定 | 建议输出 |
|:--|:--:|:--|
| 开关关（契约 None）/ available=False / 时效 expired / 无受限持仓 | `restricted_index == {}` → 全部 `None` | 与现网**逐字节一致**（形参缺省 + 无 append 分支） |
| 受限存在 | 返回判定 | 追加提示块（what-if 落地受阻块） |
| 契约对象缺 `restricted_index` 字段或其值为 `None`（旧对象/显式置空） | `.get(...) or {}` → 同降级 | 逐字节一致 |
| whatif handler 路径取契约失败（异常兜底） | try/except → `{}` | 与现网一致（不阻断模拟） |

**硬规则**：降级态下建议文案、候选集合、数值计算三者与现网逐字节一致；绝不以占位文本替代缺席。

### 3.5 明确不做

- 不改 `rebalance.py` 信号/置信度/静默判定，不改 `_round_to_lot`/`estimate_fee` 数值；
- 不在 analysis 层 import `report/purchase_status`（分层方向）；不复制格式化原语；
- 不注入调仓建议与行动摘要（三种候选操作全为卖出，申购限购不约束卖出；摘要是计数拼接无标的级申购语义）；
- 不动 `rebalance_silence` 持久化语义（静默机制与限购判定正交）；
- 不注入 LLM 提示词与展示列（plan-73 / plan-72 域）。

### 3.6 语义命名与登记（先定语义名再设计）

| 语义名（中文描述） | 代码标识符 | 位置 |
|:--|:--|:--|
| 受限标的预格式化索引 | `restricted_index` | `purchase_status_data` 契约字段、各 builder 形参 |
| 受限标的预格式化索引渲染 | `build_restricted_index` | `report/purchase_status.py` |
| 申购可行性判定 | `evaluate_purchase_feasibility` | `analysis/purchase_feasibility.py` |
| 可行性天数阈值（交易日） | `FEASIBILITY_MAX_DAYS` | 同上 |
| what-if 目标持仓提示字段 | `feasibility` 嵌入字段组 | whatif 对比契约新增键 |

- 主语义名以本表为准，迭代 4 登记 `technical.md` §6.7 功能语义命名表并过 `check-semantic-index --ci` 正反向；
- 标识符/注释/文档正文禁任务编号（`check-code-traces --ci` 负面禁止）——本设计新增代码不含任何 `plan-74` 字样；
- 提示话术只含业务事实（状态/限额/日期/「估算·以渠道为准」口径），不含内部代号。

## 4. 架构设计约束对照（按语义名对照 `technical.md` §8 约束表）

| 约束（语义名） | 本设计对照 | 结论 |
|:--|:--|:--|
| 数据契约（pipeline_data Schema） | 契约新增字段 `restricted_index`，顶层键不变，类型 map 不动，契约描述同步 | 遵守 |
| 渲染期数据不入模块级全局 | 索引在契约构建期产出、形参流动，无模块级可变全局 | 遵守 |
| 时间距离以交易日计 | `days` 为交易日估算，阈值 60 为交易日语义 | 遵守 |
| 功能开关注册表唯一事实来源 | 开关复用 `fund_purchase_limit`，契约 None ⇔ 开关关 | 遵守 |
| 报告管线挂载点集中 | 经既有契约装配函数与既有 builder 形参区扩展，不新开实验缝 | 遵守 |
| 日志统一 | 判定为纯函数不打日志；whatif 路径若加观测仅用统一 logger | 遵守 |
| 测试标记/边缘隔离/敏感路径 | 见 §6 载体纪律；`rebalance_silence.json` 已在隔离清单 | 遵守 |
| 缓存统一管理 / 原子写入 | 不新增任何缓存键与文件写入（判定纯函数、索引随契约内存流动） | 不适用 |
| LLM 模块注册 / 模块缓存指纹唯一事实来源 / 会话复用 / HTTP 统一 / Provider 链 / 凭据 / 重试 / 节流 | 本设计零 LLM、零网络、零配置新增 | 不适用 |

## 5. 风险与对策

| 风险 | 影响 | 对策 |
|:--|:--|:--|
| 前提失真（「申购合并」实体不存在） | 按原文实施会落空 | §2.1/§2.2 现状比对重定位（what-if 唯一注入面），验收按真实面写 |
| 降级态输出漂移（形参/append 分支写错） | 现网建议被无声改动 | 缺省参数结构性回退 + 降级态逐字节对照用例（§6） |
| 天数估算被误读为承诺 | 用户按 N 天后必可成交 | 文案含「估算/以渠道显示为准」；限额未知不给天数 |
| analysis 层复制格式化原语 | 两端文案漂移 | 索引字段值由 report 侧单源渲染（§3.1），analysis 只拼静态模板 |
| whatif 交互路径漏接 | 模拟页签无视限购 | 迭代 2 专项接线 + handler 级用例 |
| 静默机制与限购判定纠缠 | 修改静默逻辑误伤 | 两者正交：判定不读 `_silence` 状态（§3.5） |
| 注入分支事后不可观测 | 无法判定提示块是否注入 | what-if 提示分支统一 logger 打 debug（索引命中数/提示数，单点：契约获取 helper 内）；迭代 3 人工验收：受限目标持仓 → 报告提示块可见 |

**回滚策略（汇总）**：四迭代各一次提交、各自独立可 revert（§7）；迭代 2/3 回滚后形参缺省 `None` 使输出**天然回退**，无需动迭代 1；迭代 1 无消费方，删字段与新模块即回滚；任一层回滚都保持降级矩阵（§3.4）不变式。

## 6. 测试计划（逐迭代交付）

**载体纪律**：analysis 用例标 `unit_analysis`（`analysis` 新文件沿模块级 `unit`+`unit_analysis` 惯例）；异常/边界样本（0 元限额、>60 天、限额未知、缺名）入 `*_edge.py` + `@pytest.mark.edge`；全程无网（契约 fixture 构造）；禁写死可演进总数；60 为业务常量（阈值两侧 59/60/61 用例验证，非集合条数）。

**零回归证明方法**：① 缺省等价——`build_whatif_data(...)`（省略形参）≡ `build_whatif_data(..., restricted_index={})`（未接线两面零改动，由回归网覆盖）；② 同测对照——降级态输出与省略形参调用现算对照；③ 候选集合与数值字段在降级态逐字段相等（结构断言）。

**隔离**：不新增持久化状态（无新 fixture 需求）；`rebalance_silence.json` 既有 `_isolate_sensitive_paths` 覆盖；whatif 路径用例 mock 契约获取，不触发取数。

**既有用例回归网（零回归兜底）**：`test_action_advisor.py` / `test_rebalance_advisor.py` / `test_rebalance.py` / `test_whatif.py` / `test_whatif_sheet.py` / `test_handlers_whatif.py` 全量保持绿——任何降级态输出漂移会先红在这里；每迭代出口检查均含这批文件。

## 7. 迭代拆分与验收标准

> 四迭代串行，每迭代一次提交、独立可验、可单独回滚；**出口检查**（每迭代）：`ruff check` + `ruff format --check` + 相关 pytest 子集 + 波及的 `--ci` 脚本；**终验**（迭代 4）：P0 十项全绿。

### 迭代 1 — 受限索引 + 可行性判定原语（不动任何消费方）

**交付物**：`build_restricted_index`（契约字段 `restricted_index` 随 `build_purchase_status_data` 产出）+ 契约 docstring / `technical.md` 附录 H 行描述同步 + `analysis/purchase_feasibility.py`（`evaluate_purchase_feasibility` + `FEASIBILITY_MAX_DAYS`）+ 单元测试 + 共享受限筛选 helper `report/purchase_status.py::_filter_restricted_rows`（与 plan-73 块渲染共用，交叉同步）。**新文件清单（folders 树随迭代 4 同步核对）**：`src/python/analysis/purchase_feasibility.py`、`src/test/unit/analysis/test_purchase_feasibility.py`、`src/test/unit/analysis/test_purchase_feasibility_edge.py`。

**验收**：① 索引准入四条逐分支 → `{}`；字段值与展示层同源断言；② 判定矩阵逐分支（限大额已知/未知、暂停、无行、59/60/61 天阈值两侧、金额 None）；③ 降级态契约字段为空且不影响既有展示用例（回归）；④ 出口检查全绿。

**回滚**：消费方为零，删字段与新模块即回滚。

### 迭代 2 — What-if 路径接线（唯一注入面）

**交付物**：`whatif_operations` 契约就地获取（单点 helper，异常兜底 → `{}`，挂载点集中）+ `build_whatif_data` 形参 + 目标持仓受限提示块（金额口径含 `None` 回退）+ handler 级用例。

**验收**：① 目标持仓受限 → 提示块出现且字段正确（天数三态 + 金额可得/不可得两分支）；② 基准受限/目标不受限、降级态、取契约异常三态 → 输出与现网逐字节一致；③ 未接线两面（调仓建议/摘要）输出与基线逐字节一致；④ 出口检查全绿。

**回滚**：形参缺省 `None` + 分支跳过即回退（不动迭代 1）。

### 迭代 3 — 回归网与端到端核验

**交付物**：既有回归网全量跑绿（`test_action_advisor`/`test_rebalance_advisor`/`test_rebalance`/`test_whatif`/`test_whatif_sheet`/`test_handlers_whatif`）+ 未接线两面零改动断言用例 + 手工真实验收（受限目标持仓 → 报告提示块可见）。

**验收**：① 回归网全量绿；② 未接线两面输出与基线逐字节一致；③ whatif 注入/降级行为复跑通过；④ 出口检查全绿。

**回滚**：独立提交，单独 revert。

### 迭代 4 — 文档登记 + 语义命名 + P0 终验

**交付物**：`technical.md` §6.7 语义命名表登记（`restricted_index` / `purchase_feasibility` 语义行）+ `testplan.md` §1.1 用例登记 + `folders.md` 目录树/统计 + `test-coverage.md` 计数刷新 + `changelog.md` 条目 + 本文档改完成态。

**验收**：① P0 十项全绿（`dev-verify` + 9 个 `--ci` 脚本，`check-doc-drift` 加跑 `--with-test-count`）；② `check-semantic-index --ci` 正反向通过；③ ruff 零告警；④ 设计文档改「设计 + 已实施」。

**回滚**：纯文档提交。

**依赖**：1 → 2 → 3 → 4；与 plan-73 互不依赖、可并行（但两者都改 `report/purchase_status.py`，并行开发时按字段分工避免同文件冲突）。**预估成本**：低~中；**风险**：低（降级态零回归可机器证明）。

## 8. 决策记录

| 日期 | 决策 | 依据 |
|:-----|:-----|:-----|
| 2026-10-03 | 先出设计评审后实施（同 plan-73 流程） | 用户确认的开发流程 |
| 2026-10-03 | 动作对象从「申购合并路径」重定位为三个真实确定性面 | §2.1 现状比对（rf-510 教训适用于本任务自身） |
| 2026-10-03 | 受限提示的字段值单源在 report 侧契约渲染，analysis 层只拼静态模板 | 分层方向 report → analysis，不新增 analysis → report 依赖（既有 lazy import 先例不扩张） |
| 2026-10-03 | 需求登记沿 `plan-72`/`plan-73` 先例：不新增需求 ID，以 `testplan.md` §1.1 模块行登记为主 | 与前序任务同粒度，避免需求域数连锁改动 |
| 2026-10-03 | 调仓建议与行动摘要**不在范围**，what-if 为唯一注入面 | 三种操作全为卖出，申购限购不约束卖出 |
| 2026-10-03 | `build_action_data` 4 调用点只记不改 | 防实施者误改签名波及四处调用 |
| 2026-10-03 | 分层约束 = 不扩张既有 lazy import、纯形参下传 | 与 5 处先例现状一致，不作绝对禁令 |
| 2026-10-03 | what-if 契约获取单点 helper + 金额口径核验点、不可得即 `None` | 挂载点集中；宁缺毋错 |
| 2026-10-03 | 实施按 §7 四迭代推进，每迭代独立出口检查与回滚 | 用户要求：多迭代开发、每个迭代可验收 |
