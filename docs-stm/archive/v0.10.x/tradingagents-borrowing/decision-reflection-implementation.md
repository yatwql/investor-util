# plan-30 决策跨期反思闭环 — 实现设计

> 文档版本：0.10.16-dev
> 关联：[`reflection-decision-loop-analysis.md`](reflection-decision-loop-analysis.md)（机理深入分析）+ [`../augur-borrowing/augur-borrowing-analysis.md`](../augur-borrowing/augur-borrowing-analysis.md)（augur 结算纪律）
> 语义名（落地）：`decision_reflection`（功能开关）、`decision_ledger`（账本核心）、`decision_settlement`（结算服务）
> 状态：**已实现**（默认关闭的 P4 实验特性；TUI / Web / CLI 三面上屏见同目录 `experimental-features-ui-surfacing.md`）

---

## 1. 目标与范围

对**判断**（含 LLM 看多看空 与 确定性再平衡/行动建议）不即时评判——当次记作 `pending` 决策；同标的再现时用**真实后续行情**结算（方向正确率、超额 alpha），产出教训回灌后续分析提示词。

用户选定范围：**完整 plan-30（含 LLM 载体 + 教训回灌）** + **纳入特性开关（缺省关闭）**。

### 1.1 载体盘点（承接分析文档）

| 载体 | 来源 | 粒度 | 方向语义 | 本设计处置 |
|------|------|------|----------|-----------|
| 确定性再平衡/纪律/建议 | `build_action_data` 产物（rebalance_signals / discipline_signals / rebalance_advice） | 品种（code） | 全部为卖出向 → direction `-1` | 报告层抽取登记 |
| LLM 智囊团操作建议表 | expert_review 固定表 `### 操作建议` `\| 优先级 \| 品种 \| 建议操作 \| 理由 \|` | 品种（code） | 减仓 `-1` / 加仓 `+1` / 持有 `0` | HTML 逆向解析登记 |

持有（`0`）记录仅入 `pending` 供「按方向命中」统计，不计入 alpha 方向正确判定。

### 1.2 结算口径（承接 augur 纪律）

- 命中判定：仅当方向与后续真实走势一致才算对；持有不参与方向命中。
- 行情门槛：|原始涨跌| < 阈值（默认 1.5%）判为「平盘不判定」，防噪声计为命中。
- 最小有效样本 `MIN_MEANINGFUL_SAMPLE = 20`：样本 < 20 时不输出命中率结论，仅报告计数。
- 非回测：复盘区块附免责声明。
- 空上下文预测跳过（无可解析 code 的行不入账）。

---

## 2. 总体架构决策

### 2.1 分层与依赖方向（核心约束）

```
┌────────────── report 层（可 import analysis/llm/core/fetcher）──────────────┐
│ report/_report_generation.py    注册+结算 seam、复盘数据装配                    │
│ report/decision_settlement.py   结算服务（拉行情→产出结算事件）   [新增]         │
│ report/decision_llm_capture.py  expert_review 操作建议表解析→方向记录 [新增]     │
│ report/decision_review_block.py 复盘区块数据构建             [新增]              │
├────────────── llm 层 ──────────────────────────────────────────────────────┤
│ llm/skeleton.py(_run_standard_mode)  教训块统一注入点（user_prompt 为 None 时）│
│ llm/generators.py + generators_orchestrator.py  专家复盘指纹闭包 + 预检闭包     │
├────────────── core 层（零 report 依赖）─────────────────────────────────────┤
│ core/decision_ledger.py 账本核心：JSONL 事件账本 + fold 统计 + 教训文本/指纹后缀 │
└────────────────────────────────────────────────────────────────────────────┘
```

- **账本核心放 `src/python/core/decision_ledger.py`**：只依赖 stdlib（os/json/re/hashlib）+ logging + PROJECT_ROOT。不得 import `report/`（对齐 perf.py 位于 core 的先例）。所有层都可安全消费。
- **结算服务放 `report/decision_settlement.py`**：需要拉历史行情（portfolio_history/fetcher chain），属 report 能力；它 import core 账本单向依赖，不违反「analysis 禁 import report」（本设计不触碰 analysis 的禁止面——`action_advisor.py` 的 constraint 保持原样，登记由 report seam 读已算好的 action_data 完成）。
- **LLM 操作建议表解析放 report 层**（仅 report 消费）；core 保持对 LLM 表结构零知识。

### 2.2 持久化范式（对齐 perf.py 原子 JSONL，**不引入单例**）

- 事件型 JSONL 账本：每行一个事件 `{"event": "decision"|"settlement", ...}`，追加即事件发生；统计用 fold 合并 decision+settlement 事件。append-only → 天然不可变、无半写整档风险（沿用 `_append_jsonl_atomic` 读-拼-`mkstemp`+`os.replace`）。
- 模块级路径常量 `_DECISION_LEDGER_FILE = os.path.join(PROJECT_ROOT, "data", "state", "decision_ledger.jsonl")`（data/state，非 data/cache——避开 `cache.cleanup_expired()` 清扫；理由同 `data_status.py:113-122`）。测试经 conftest `monkeypatch.setattr` 重定向。
- **无模块级单例**：账本读写均为无状态函数（读档→fold；追加→原子 append）。不设 `get_ledger()`/`reset_ledger()`，从而不触发「单例须 autouse 重置」的义务，减少状态泄漏面。当前教训文本/指纹后缀由调用方**按需读档现算**（见 §6），不驻留模块全局。

### 2.3 特性开关

- `src/python/config/features.py`：新增 `"decision_reflection": False` 于 `_FEATURE_FLAGS_DEFAULT`；同步注册 `EXPERIMENTAL_FEATURES`（缺省关闭 → 启动红色日志提示）。
- 门控判定统一 `features.is_feature_enabled("decision_reflection")`；报告 seam、结算、注入、指纹后缀四处以同一谓词收敛。
- 开关关闭时全链路无感：不读账本（除指纹后缀返回空串）、不登记、不结算、报告区块为 None、提示词无教训块、缓存键不变。

### 2.4 实施范围边界（v1，防债务）

- 教训**只回灌 expert_review**（智囊团——唯一按 code 出方向的 LLM 载体），`LESSON_RECEIVER_MODULES = {"expert_review"}`。
- **辩论 pro/con/synthesis 不纳入回灌**：其调用带自定义 `system_prompt/user_prompt`（`generators.py:480-499`），注入条件以 `user_prompt is None` 排除（见 §6.3）；其指纹为独立 lambda，不折叠教训后缀 → 缓存不串。
- `news_correlation` 走 batch 分支（非 `_run_standard_mode`），天然不受影响。
- 全局宏观/持仓体检为方向性观点但非按 code 操作，v1 不注入；扩展路径见 §10。

---

## 3. 事件账本数据模型（core/decision_ledger.py）

### 3.1 decision 事件

```json
{
  "event": "decision",
  "decision_id": "uuid4-hex[:12]",
  "report_date": "2026-09-09",        // 登记运行所在交易日（str，UTC+8 本地）
  "code": "040046",
  "name": "XX 基金",
  "direction": -1,                     // +1 加仓/看多；-1 减仓/看空；0 持有/中性
  "magnitude": "high",                 // LLM: 优先级(high/mid/low)；确定性: 强度近似
  "carrier": "expert_review",          // expert_review | rebalance | discipline | rebalance_advice
  "detail": "部分止盈至...",            // 简短原始理由/建议，供复盘展示
  "baseline_close": 1.234,             // 登记日收盘（结算基线，见 §5.2）
  "created_at": "2026-09-09T...",
  "status": "pending"
}
```

### 3.2 settlement 事件

```json
{
  "event": "settlement",
  "decision_id": "...",
  "settle_date": "2026-09-20",
  "horizon_bars": 7,                  // 实际结算跨度（交易日 bar 数）
  "raw_return": -0.042,               // 标的价格区间涨跌
  "bench_return": -0.031,             // 基准区间涨跌（沪深300）
  "alpha": -0.011,                    // raw - bench
  "direction_hit": true,              // 方向命中（平盘/数据缺失为 None）
  "outcome": "hit"|"miss"|"flat"|"gap",// gap=数据缺口不可解析
  "created_at": "..."
}
```

### 3.3 core 对外 API

| 函数 | 职责 | 依赖 |
|------|------|------|
| `append_decision(...)` / `append_settlement(...)` | 原子追加事件（复用 `_append_jsonl_atomic` 思路） | 仅 core |
| `load_events()` | 读全量事件；逐行 `json.JSONDecodeError` 容错（对齐 `perf.load_history`） | 仅 core |
| `fold_ledger(events=None)` | decision+settlement 合并 → `LedgerStats`（pending 列表、settled 明细、方向命中率、按载体聚合、总样本数） | 仅 core |
| `lessons_block_for_module(module_key)` | 命中率达有效样本 → 紧凑教训文本（§6.1）；否则空串 | 仅 core |
| `lessons_cache_suffix()` | 当前可注入教训文本的定长哈希（`_lr` + 12hex），无文本返回 `""` | 仅 core |
| `decision_ledger_is_active()` | `features.is_feature_enabled("decision_reflection")` 收敛判定 | 仅 core |

> 纯数据/纯函数核心置于 core，使 report 结算、llm 注入两处都可调用，且无 report 依赖。

---

## 4. 载体 → 方向记录映射

### 4.1 确定性载体（report seam，`_report_generation.py:595-597` 之后）

`_action_data`（final，含 portfolio peak 重建版）中：

| 子键 | 形状 | direction | magnitude |
|------|------|-----------|-----------|
| `rebalance_signals[].{code,name}` action 含「部分止盈至…%区间」 | -1 | mid |
| `discipline_signals[].{code,name,action}` 值「部分止盈」/「止损/减仓」/「减仓控回撤」 | -1 | 按规则强度（high/mid 近似） |
| `rebalance_advice[].{code,name,operation}` 值 卖出减仓/部分止盈/止损 | -1 | operation 分级 |

- 组合级纪律信号（空 code 的组合回撤）**跳过**（无标的不可结算）。
- 遍历时对同一 code 多条去重（保 operation 最强烈一条）。

### 4.2 LLM 载体（report seam，`_fetch_llm_and_news` 返回后）

- 来源：`llm_content[1]`（expert_review HTML）。`markdown_to_html`（`llm/markdown.py:33-102`）无表格处理 → 每表行落为 `<p>| 🔴 高 | 040046 | 减仓 | 理由 |</p>`（竖线保留）。
- 解析（`report/decision_llm_capture.py` 新增，参考 `fact_checker/_ranking.py:65-98` 行界idiom）：
  1. 定位 `<p>` 块文本以 `|` 起止的行；按 `|` 分格（`row.strip("|").split("|")`）；
  2. 跳过分隔行（`|:---:|` 等，`re.match(r"^\|?[\s:|-]+\|?$")`）；
  3. 断言 4 格：优先级(🔴/🟡/🟢→high/mid/low) / code(`\b[0-9]{6}\b`) / 建议操作 / 理由；
  4. 操作值映射：减仓 `-1`、加仓 `+1`、持有 `0`；未识别值跳过（空上下文预测不入账）；
  5. code 与持仓（holdings_details）白名单交集校验——不在持仓中的不登记。
- 需在**完整可解析路径**下才有此步：`_enable_llm` 为 False 或 expert_review 为 None/降级回退时跳过 LLM 登记（回退内容非真实意见，不登记）。

---

## 5. 结算服务（report/decision_settlement.py）

### 5.1 触发点与顺序（在 `_generate_report_full` 内、LLM 拉取之前）

```
_report_generation.py:595-597  final action_data 就绪
   │
   ▼  [decision_reflection 开启]  （插入：595 之后、611 步骤4/5 之前）
① decision_settlement.settle_pending_old()      // 先结旧
② 确定性载体登记（§4.1，来自 final _action_data） // 后入新（同日 new 为 pending，不被①误结）
   ▼
:611-626  _fetch_llm_and_news(...)               // llm 侧按需读档取教训（含①刚结算结果）
   ▼
③  [decision_reflection 开启]  解析 llm_content[1] → 登记 LLM 决策（§4.2）
④  复盘区块数据装配（decision_review_block）→ 传给 HTML/Excel writer
```

- **结算必须先于 LLM 拉取**：否则当次教训（含本次结算）未落档，注入读不到新结算。
- 当日新登记的确定性决策为 pending，不进入当日教训（只折叠 settled）。

### 5.2 结算算法（单个 pending）

1. 过滤条件：`status=pending` 且与 `report_date` 间隔达结算视界。视界按交易日：**最短 5、目标 10 bars**（决策后至少 5 个交易日才可结）。
2. 取行情：按代码类型走 `portfolio_history.PortfolioHistoryCalculator.calculate_for_holding`（内部路由 history_stock / history_fund_otc，A股/ETF/OTC 基金均覆盖）；`days` 取 `max(15, 距决策日期历日×0.7)` 上限 365。**基线 close 以登记时落库为准**（decision.baseline_close），避免追溯旧 bar 的取数不可靠——结算只需末 bar close 比基线。
   - 若末 bar 距决策日 < 最短视界 → 未到期，保持 pending。
   - 基准 `bench_return`：`fetch_index_history("sh000300", days=同窗口)`（`fetcher/index.py:208` → history_index chain），按决策/结算两日 LOCF 对齐取 close 比值；失败则 `bench_return=None`（alpha 缺失，方向命中仍可判）。
3. 判定：
   - `raw_return = last_close/baseline_close - 1`。
   - `|raw_return| < 1.5%` → `outcome=flat`，不计命中。
   - 否则 `direction_hit = (direction==-1 and raw_return<0) or (direction==+1 and raw_return>0)`；`outcome=hit/miss`。
   - 末 bar 拉取为空 / 代码下架 → `outcome=gap`，不计统计。
4. `append_settlement(...)`。

### 5.3 统计（fold_ledger）

- 方向命中率 = hit / (hit+miss)（flat/gap 剔除；样本含跨载体聚合与分载体两档）。
- 超额 alpha = alpha 均值（可判 alpha 的样本）。
- 有效样本门槛 `MIN_MEANINGFUL_SAMPLE=20` → 低于仅给计数、不给命中率结论。

---

## 6. 教训回灌 + 缓存指纹版本化（核心风险解法）

### 6.1 教训文本（core）

由 `fold_ledger` 输出生成紧凑块，示例：

```
【历史决策复盘（非回测，仅供反思）】近{settled_n}次方向性决策方向命中率 {acc:.0%}（样本≥20 时给出），其中减仓/看空类 {n_sell} 次命中 {n_sell_hit}；{·alpha 均值}。近期有效教训：{code} 减仓后 {N} 交易日续涨 {pct:.1%}（看空未兑现）；{code} 止损后继续下探 {pct:.1%}（看空兑现）。请结合复盘结论审视本轮回调/持有判断。
```

文本由核心函数在**调用时现算**，内容即「当前账本 fold 的 settled 摘要」；无 settled 或无有效样本 → 空串。

### 6.2 缓存键耦合（已确认风险 → 解法）

**事实**：LLM 缓存指纹（`fingerprint.py build_llm_fingerprint`）仅由持仓/收益/穿透/风险数据构成，**不含提示词与附录文本**。注入教训文本到 `_user` 不会改变指纹 → 缓存会吞掉注入，陈旧输出不变。

**解法——教训指纹后缀 + 读写双侧同源**：
- 在 expert_review 的**写侧指纹闭包**（`generators.py:184-196`）与**orchestrator 预检指纹闭包**（`generators_orchestrator.py:120-129`）末尾统一追加 `+ lessons_cache_suffix()`：
  - `lessons_cache_suffix()` 现算「当前 lessons_block 文本」的定长哈希（`_lr`+12hex）；
  - 结算落档 → 教训文本变 → 后缀变 → 读写键同变 → 缓存自然失效并带新教训重生成；
  - 无教训文本 / 开关关闭 → 后缀 `""` → 缓存键与现状完全一致（向后兼容，不误伤旧缓存）。
- **同源性保证**：写侧与预检侧调用同一 `lessons_cache_suffix()`，从同一账本档现算 → 键恒等，不会漂移。因此只改此两处闭包（同源辅助函数），不手工拼接。

### 6.3 注入点（llm/skeleton.py `_run_standard_mode`）

- 在统一附录（`:454-458`）之后追加：`if _user and decision_ledger_is_active() and user_prompt is None and module_key in LESSON_RECEIVER_MODULES: _user += lessons_block_for_module(module_key)`。
- `user_prompt is None` 排除辩论变体（自定义 prompt 且指纹独立，v1 不回灌，防缓存不一致）。
- `lessons_block_for_module` 现算；空则不加，与后缀 `""` 自洽。

> 因果闭合：注册→结算（report seam，LLM 前）→ 教训落档 → 指纹后缀与提示词同源现算（llm 调用时）→ 下次同标的专家复盘带教训。无单例、无跨层全局、无手工键维护。

---

## 7. 报告「历史决策复盘」区块

- 数据：`decision_review_data = decision_review_block.build(...)`（report 层）——
  - `summary`：pending 数、settled 数、方向命中率（样本达门槛才给值）、alpha 均值、最近 outcome 列表（code/方向/明细/结果/区间涨跌）。
  - `recent_decisions`：本次报告新登记 + 最近结算各 ≤5 条，供表格渲染。
  - `disclaimer`：非回测声明。
- 注入：`_generate_full_html_report` / Excel writer 增加可选参数 `decision_review_data: dict | None = None`（镜像 `action_data`/`snapshot_diff_data` 现有可选参模式）；`None` → 模板既有输出不变。
- 仅在 **full 路径**装配（决策载体与 LLM 均在 full 出）；开关关 → None。

---

## 8. 特性开关与注册点汇总

| 注册点 | 行为 |
|--------|------|
| `_report_generation.py` seam（595 后 / 626 后） | 结算、确定性登记、LLM 登记、复盘装配——全部包 `if decision_ledger_is_active():` |
| `skeleton.py:_run_standard_mode` | 教训块注入（§6.3） |
| `generators.py` expert_review 写侧闭包 + `generators_orchestrator.py` 预检闭包 | `+ lessons_cache_suffix()`（开关关=空串，无行为差） |
| `features.py` | `decision_reflection: False` + EXPERIMENTAL_FEATURES 注册 |

---

## 9. 测试计划与隔离（对齐 CLAUDE.md 门禁纪律）

新增测试文件（均在 `src/test/` 相应目录）：
1. `unit/.../test_decision_ledger.py`（core 账本：append/load/fold/统计/命中率门槛/损坏行容错）— marker `unit_ledger`。
2. `unit/.../test_decision_ledger_edge.py`（edge：空账本、全 gap、flat 剔除、损坏行、超大数值）— `@pytest.mark.edge` 且置于 `*_edge.py`。
3. `unit/.../test_decision_llm_capture.py`（操作建议表 HTML 解析：4 格行/分隔行/未识别操作/非持仓 code 剔除/持有行）。
4. `unit/.../test_decision_settlement.py`（结算：mock 行情；视界未到期保持 pending、hit/miss/flat/gap、基准缺失降级）。
5. `unit/.../test_decision_lessons.py`（教训文本门槛、后缀随结算变化、开关关=空串→键不变）。

隔离（conftest.py）：
- `_isolate_sensitive_paths` 增 `monkeypatch.setattr("src.python.core.decision_ledger._DECISION_LEDGER_FILE", tmp_path/...)`。
- 无单例 → 免新增 autouse reset；教训/后缀函数为按需读档，路径隔离即状态隔离。
- 全管线集成若触发 `generate_all_llm` → 必须 mock LLM（现有纪律）；注入侧测试直接调用 core 函数即可，不触 LLM。
- 结算测试 mock fetcher/portfolio_history（防真网络）。
- marker 注册到 conftest `pytest_configure`。

## 10. 扩展路径与债务说明

- **不遗留未偿债务**：v1 注入仅 expert_review 为显式边界（允许列表常量 + 同源后缀辅助函数，非散装 if）。扩至 global_macro/health_check = 往 `LESSON_RECEIVER_MODULES` 加键 + 其写侧/预检指纹闭包各加同源后缀（各 2 处），无需新机制。
- 辩论/新闻关联回灌留待 debate 开关规模化时再评估（届时在辩论指纹 lambda 补后缀）。
- 结算视界/行情门槛抽常量为可调参数（默认 5/10 bars、1.5%、`MIN_MEANINGFUL_SAMPLE=20`），配置化留待 `signal_ledger`（plan-34）合并期统一。

## 11. 分期实施

| 期 | 交付 | 对应任务 |
|----|------|---------|
| ① 账本核心 | `core/decision_ledger.py` + conftest 隔离 + unit/edge 测试 | Task #9 |
| ② 确定性登记 + 结算 | `report/decision_settlement.py` + seam ①/② + 测试 | Task #10 |
| ③ LLM 解析登记 | `report/decision_llm_capture.py` + seam ③ + 测试 | Task #11 |
| ④ 复盘区块 + 教训回灌 | review_block + skeleton 注入 + 指纹后缀 + seam ④ + 测试 | Task #12 |
| ⑤ 开关/记账/门禁 | features.json 注册、P0 dev-verify + 四脚本 + ruff + changelog/folders/test-coverage + 提交 | Task #13 |
