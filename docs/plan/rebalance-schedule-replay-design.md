# 调仓纪律回放（schedule_replay）设计 —— plan-80

> **状态**：设计 + 待评测（先决门槛未过不实施）。
> **参照**：gs-quant `backtests/`（`RebalanceAction` 规则触发、`TransactionModel` 三件套成本分层、`PnlAttribute` 分期分解——只借语义不搬引擎，见 `gs-quant-borrow-candidates-research.md` §2.3）。
> **研究背景**：见 `gs-quant-borrow-candidates-research.md` §2.1。

## 1. 动机与缺口

- `rebalance.py` / `simple_rebalance.py`：**约束检查与建议**（能不能调、怎么调）——不回答「调了会怎样」；
- `whatif_backtest`：**单次调仓**的指定生效日窗口对比——不回答「长期坚持某纪律会怎样」；
- 缺口：**规则化多期回放**——「每月定再平衡 / 偏离阈值触发再平衡」在历史窗口逐期执行（含成本），与「买入持有」对比。这是「纪律 vs 放任」的量化回答，也是行动建议章最有说服力的证据类型。

## 2. 先决门槛（go-no-go，未过则归档未采纳）

1. **指标原语可复用**：收益/回撤/夏普全部复用 `analysis/metrics*` 与 `whatif_backtest` 既有纯计算，**不新造回测引擎**（架构决策：扩展而非引入新框架）；核对存在至少 3 处可直接复用项后成立。
2. **成本联动**：成本计入依赖 plan-77 `trade_cost_model`；未落地时先出「无成本版」且**每行显式标注「未计成本」**（日志回显纪律同款），落地后软切换——不阻塞、不双实现。
3. **价值验证**：用户对 2 个真实持仓规则回放样例（定期 + 阈值各一）确认「有启发、想持续看」；否则归档。

## 3. 语义命名（先定名再设计）

| 语义名 | 层 | 说明 |
|---|---|---|
| `replay_schedule` | 契约 | 回放规则（定期 cadence / 阈值偏离触发 + 目标权重来源） |
| `schedule_replay` | analysis | 纯计算：规则 → 逐期调仓序列 → 逐期净值回放（复用 metrics 指标原语；成本经 plan-77 `trade_cost_model` 软接入） |
| `schedule_replay_panel` | report | Excel/HTML 回放章（纪律回放 vs 买入持有双线 + 逐期换手/成本表） |
| 开关 `rebalance_schedule_replay` | config | 默认关（实验组） |

## 4. 迭代设计

- **迭代 1 — 规则契约与纯计算**：`replay_schedule` 解析（cadence=月/季、阈值=偏离 x pp；目标权重=当前持仓归一或用户指定）+ `schedule_replay` 逐期回放（调仓日对齐交易日、LOCF 行情、逐期净值归一 100bp 基点，对齐 `whatif_backtest` 既有基点约定）。fixture 手算：2 期回放 + 阈值触发 1 例。
- **迭代 2 — 成本软接入**：plan-77 `trade_cost_model` 可用则逐期计入（FIFO 档位口径同源）；不可用则置 `cost_note="未计成本"` 并在面板/日志回显。零双实现。
- **迭代 3 — 报告双端**：`schedule_replay_panel`（双线图数据 + 逐期换手/成本表 + 与 `action_advisor` 纪律建议互链只读）；LLM 行动建议块可引用回放结论（单源数据，指纹携带）。
- **迭代 4 — 验收与文档**：先决门槛三项判定 + 五份文档同步 + P0 门禁。

## 5. 红线与约束

- **分层不重叠**：与 plan-77 分工明确——plan-77 = 单次调仓窗口 + 成本口径；本模块 = 多期规则回放（消费其成本模型，不复制口径）；与 `rebalance.py` 只读互链，不互写。
- **不新造引擎**：不引入 gs-quant / Vibe 引擎代码；回放逻辑全在 `analysis/schedule_replay` 纯函数内（<800 行硬上限受 `check-file-length` 守护）。
- **降级**：历史窗口不足 12 个月或行情缺口 >30% → `available=false` 章隐藏；阈值触发无一发生 → 明示「窗口内未触发」而非空表。
- **开关纪律**：默认关；关态逐字节回退回归用例。
- **测试纪律**：fixture 最小持仓（2-5 品种）+ mock 行情；输出目录隔离；edge 场景入 `*_edge.py`。

## 6. 验收标准

1. 2 期回放与阈值触发 fixture 手算一致（交易日对齐、基点归一同源）；
2. 成本可用/不可用两态输出差异有回归用例（未计成本标注必现）；
3. 先决门槛三项判定记录入评测文档；
4. P0 门禁十项全绿；文档五份同步。
