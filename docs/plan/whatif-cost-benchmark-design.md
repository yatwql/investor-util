# What-if 回放成本建模与基准对比设计 —— plan-77

> **状态**：设计 + 待评测（先决门槛未过不实施）。
> **参照**：Vibe-Trading `agent/backtest/factor_costs.py`（成本因子）+ `benchmark.py`（基准对比面板）+ `constraints.py`；成本分层（Constant/Scaled/Aggregate）与 PnL 分解语义参照 gs-quant `backtests/backtest_objects.py`（`TransactionModel`/`PnlAttribute`，见 gs-quant 借鉴批研究文档）。
> **研究背景**：见 `vibe-trading-borrow-candidates-research.md` §2.1。

## 1. 动机与问题

`analysis/whatif_backtest.py` 已支持指定生效日的窗口回测（收益/年化/波动/夏普/最大
回撤，基准持仓 vs 目标持仓 as-if 归一化对比），但有两个系统性偏差：

1. **无交易成本**：基金调仓真实发生申购费/赎回费（且与持有期强相关——赎回费常按
   持有期阶梯减免）。现状回测把调仓收益系统性高估，持有期越短高估越狠，恰是
   what-if 最该警示的频繁调仓场景。
2. **无基准对比**：只有「调 vs 不调」两侧对比，没有「两侧都跑赢/跑输业绩基准多
   少」的第三方参照，用户无法判断差异是否显著。

Vibe-Trading 的 factor_costs（成本计入回放）与 benchmark（自动选基准 + 同图对比）
正好补齐这两块，且其 zero-dependency 设计与我们离线纪律兼容。

## 2. 先决门槛（go-no-go）

1. **费率数据可得性**：目标基金申赎费率必须可取得（天天基金申购状态 provider
   已有同源页面；或用户配置表兜底）。抽样 20 只既有持仓基金，费率字段取得率
   <80% → 降级为「用户配置表单源」或归档。
2. **口径可判定**：赎回费阶梯按「份额持有期」逐笔判定（先进先出），口径唯一且
   文档化；无法逐笔判定时明确标注近似（按平均持有期）。
3. **增益验证**：成本计入后，对既有 fixture 场景回测结论发生「方向性翻转」的
   案例 ≥1 个且经人工复核合理（证明不是无感装饰）。

## 3. 语义命名

| 语义名 | 层 | 说明 |
|---|---|---|
| `redemption_fee_schedule` | 契约 | 赎回费阶梯（持有期下界 → 费率）+ 申购费率 |
| `trade_cost_model` | analysis | 纯计算：给定买卖明细+费率表 → 成本金额/成本后收益序列 |
| `benchmark_index_resolver` | analysis | 目标持仓 → 基准指数映射（宽基默认，可配置覆盖） |
| `whatif_cost_panel` | report | 成本对比面板（成本前/后收益差 + 基准三线图数据） |
| 开关 `whatif_trade_cost` | config | 默认关；成本不计入时行为逐字节不变 |

## 4. 迭代设计

- **迭代 1 — 费率表与成本模型**：`trade_cost_model` 纯函数（申购费计入买入日、
  赎回费按 FIFO 份额持有期对档）+ fixture 单测（手算对照）。
- **迭代 2 — 费率数据接入**：扩展天天基金申购状态链路取申赎费率（走
  `fetcher/chain.py`，三级降级；配置表 `data/config/` 键兜底），TTL 与既有缓存
  体系一致。
- **迭代 3 — 基准映射与对比面板**：`benchmark_index_resolver`（宽基默认规则 +
  配置覆盖）+ 指数行情经既有行情链路取得；`whatif_cost_panel` 在 HTML/Excel 的
  what-if 章追加「成本后对比 + 基准三线」（降级：无基准数据则只出成本后对比）。
- **迭代 4 — 回归网与文档**：零改动断言（开关关时输出逐字节不变）、变更场景
  断言（成本翻转结论案例）、五份文档同步 + P0 门禁。

## 5. 红线与约束

- **不重叠**：只扩展 `whatif_backtest.py` 消费侧，不改其纯计算契约；限购受限判定
  （plan-74 的 `restricted_index`/`evaluate_purchase_feasibility`）只读复用。
- **默认零影响**：开关 `whatif_trade_cost` 关时，what-if 章输出与现状逐字节一致
  （回归用例锁定）。
- **降级**：费率取数失败 → 该品种按「费率未知」标注（不出成本后数字，只出成本前），
  不阻塞主回测。
- **交易日纪律**：持有期一律以交易日计（禁按自然日差判定）。

## 6. 验收标准

1. FIFO 赎回费档位判定 fixture 手算一致；
2. 开关关时输出逐字节不变（零改动断言）；
3. 成本翻转案例入回归网；
4. P0 门禁十项全绿；文档五份同步。
