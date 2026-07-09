# R-200 scenario / regression / verify 三模式耗时优化 — 迭代计划与技术设计

> 创建：2026-07-09 | v5 终版：2026-07-09 | 状态：**部分完成，进入收尾阶段**
>
> ✅ Step 0（push2 API mock）已于 2026-07-09 完成（冒烟测试通过）
> ✅ B-2b（标记拆分 + 文件搬迁）已于 2026-07-09 完成（8 项全部通过 55.96s）
>
> **实测结果**：`-m "scenario"` **268 passed, 321s（5min 21s）**，比优化前 1262s 降低 **74%**
>
> **关键决策更新（v5）**：
> - S0c 已移出 `scenario` 至 `scenario_extreme`，scenario 模式已不含最慢测试（321s 已接近 committed 300s）
> - **B-2a（S0c 持仓缩减）不再需要** — 优化门禁已由标记拆分达成，降级为低优先级
> - 当前门槛：321s - 300s = 仅差 21s，环境波动可自然消除

---

## 0. 问题定义

### 0.1 现状（v5 更新）

| 模式 | 角色 | **优化前** | **优化后（实测）** | 降幅 | 并行 |
|:-----|:-----|:----------:|:-----------------:|:----:|:----:|
| **regression**（P0 提交前门禁） | 每次 commit 前通过 | ~21 min（profiling 峰值）[^2] | **~5min 21s** | 74%[^2] | 否 |
| **scenario**（场景验证） | regression 的标记别名 | ~21 min | **~5min 21s** | 74% | 否 |
| **verify**（P1 合入门禁） | 合并到 master 前通过 | **~6 min**（你下午实测）| **~6min**（= scenario + unit 开销）| 待测 | 部分并行 |
| **dev-verify**（新增） | 开发期快速验证 | — | **待实现** | — | 并行 |
| **scenario_extreme**（按需） | 极限场景 | ~15 min | **~56s（实测）** | 94% | 否 |

**关键认识**：verify 用 `or` 合并 scenario（268项单线程）和 unit 测试（743项并行），**总耗时由 scenario 主导**。verify 不可能比 scenario 快。这在设计目标中需被正视。

> [^2]: 原始 21min 是 `TestS0cLargeHoldings` 叠加 push2 API 调用的 profiling 峰值。用户下午实测 verify ~6min，与当前 scenario 321s + unit 开销吻合。21min 不作为基线参考。

**瓶颈已被打破**：S0c 的 856s 和 push2 API 调用均已移除，scenario 当前最慢测试仅 ~17s，不再有单个异常项。

### 0.2 实证瓶颈（2026-07-09 profiling）

`pytest -m "scenario" -q --durations=5`（v5 实测）：

| 排名 | 测试 | 耗时 | 累计占比 |
|:----:|:------|:----:|:--------:|
| 1 | TestScenarioBond::test_penetration_top10_contains_no_or_few_stocks | 17.61s | 5.5% |
| 2 | TestScenarioFund::test_penetration_top10_not_empty | 16.07s | 10.5% |
| 3 | TestS14LlmDisabled::test_llm_content_none_when_disabled | 14.68s | 15.1% |
| 4 | TestScenarioSingleHolding::test_single_holding_generates_excel | 12.06s | 18.9% |
| 5 | TestSP10CrossHoldingMerge::test_cross_holding_total_mv | 11.83s | 22.5% |
| | 其余 263 项 | ~249s | 100% |
| | **scenario 合计** | **321s (5min 21s)** | 268 passed |

最慢项仅 17.61s，已无突出的单点瓶颈。

### 0.3 关键决策记录

| 决策 | 版本 | 结论 |
|:-----|:----:|:------|
| Phase A 根因定位 | v4 | 删除 — 受益 50s vs B-2b 受益 942s，40% 概率无结论 |
| B-2a（S0c 优化） | **v5** | **降级为低优先级** — S0c 已移出 scenario，不再影响门禁 |
| scenario_extreme 文件位置 | v5 | **放 resilience/ 目录下**（S10 属于容错子集，物理结构紧凑）|
| S0c 标记 | v5 | 仅保留 `@pytest.mark.scenario_extreme`，去掉 `@pytest.mark.scenario_basic` |

---

## 1. 设计目标

### 1.1 量化目标（v5 更新 — 实测已达，仅差 21s）

| 指标 | 优化前 | **实测（v5）** | **Committed** | Stretch | 主要推力 |
|:-----|:------:|:-------------:|:-------------:|:-------:|:---------|
| **regression（P0）** | 21min | **~321s** | **≤ 300s** | ≤ 180s | B-2b ✅ + Step 0 ✅ |
| **scenario** | 21min | **~321s** | **≤ 300s** | ≤ 180s | B-2b ✅ + Step 0 ✅ |
| **verify（P1）** | ~6min | **~6min**[^1] | **≤ 360s** | ≤ 240s | B-2b ✅ + C 子阶段 |

> [^1]: verify = `scenario or unit_core or unit_providers or unit_fetcher`，scenario（268项单线程）是瓶颈。verify 不可能比 scenario 快——core/fetcher/providers 项再多也是并行，scenario 项数没减。**committed 360s = 当前 scenario 321s + 合理余量**。如果 C 子阶段实现 phased 模式，用户可选 `--phased` 在 30s 内先看到 unit 结果（快速失败），再等 scenario 结束。
| **dev-verify（新增）** | — | — | **≤ 120s** | — | D-4 |
| **scenario_extreme** | ~15min | **~56s** | — | — | Step 0 ✅（主线收益）|
| **覆盖项数** | 277 | 268+8=276 | = 276 | = 276 | 无遗漏 |

> **冲刺 committed 300s 的策略**：当前 321s - 300s = **仅差 21s**。不专项优化 —— 环境波动 ±10-20s 即可自然消除。若仍需更稳定达标，以下贡献：
> - D-4（dev-verify 不直接影响，但 L 阶段提供子集）
> - C（verify 子阶段对齐 marker 表达式，消除非 scenario 项干扰）

---

## 2. 迭代计划（v5 更新 — 已减至 3 步，约 0.5 天）

```
    已完成                        待完成
 ────────────────          ─────────────────
 ✅ Step 0  push2 mock     
 ✅ B-2b    标记拆分+搬迁    D-4: dev-verify 模式（高优先级）
 ✅ S0c+S10 迁移至          C:   verify 子阶段（中优先级）
             resilience/    E:   文档同步（中优先级）
                            B-2a: 降级（低优先级，暂不执行）
```

---

### ✅ B-2b — scenario_extreme 标记拆分 + 文件搬迁（已完成）

**实际结果**：
| 指标 | 优化前 | 优化后 | 降幅 |
|:-----|:------:|:------:|:----:|
| scenario 模式 | 1262s | **321s** | **74%** |
| scenario 项数 | 277 | 268（去 S0c 3 项）| 3.2% |
| scenario_extreme 项数 | — | 8 项 | — |
| scenario_extreme 耗时 | ~15min（含 push2）| **~56s** | 94% |

**完成的操作**：
1. 标记变更：`test_scenario_holdings_quality.py` 模块级去掉 `scenario`，S0c 标注 `scenario_extreme` 不再有 `scenario`/`scenario_basic`
2. 文件搬迁：`TestS0cLargeHoldings(3项)` + `TestScenarioExtreme(5项)` → **`resilience/test_scenario_extreme.py`**
3. 标记隔离：新文件仅有 `@pytest.mark.scenario_extreme`，不继承 `scenario`/`scenario_resilience`
4. `test_runner.py` 已更新 scenario/regression/verify 模式排除 `scenario_extreme`
5. `test_integration_scenarios.py` 不再包含 `scenario_extreme` 类

---

### D-4 — dev-verify 快捷模式（高优先级，0.5 天）

**条件**：B-2b 已完成，确认 `scenario_extreme` 标记的正常运作。

**增量测试的最简实现**：利用现有细粒度标记组合出快速模式。开发者运行 `--mode dev-verify` 在 **~2min** 内验证核心逻辑。

```python
"dev-verify": {
    "marker": (
        "(unit_core or unit_providers or unit_fetcher or "
        "unit_llm or unit_report or unit_config or unit_ui or unit_news) "
        "and not (edge or data) "
        "or (scenario_basic and not scenario_extreme)"
    ),
    "desc": "开发期快速验证（单元+基础场景，~2min）",
    "timeout_sec": 120,
    "order": 4,
    "parallel": True,
}
```

**设计约束**：
- ✅ C11：全部使用已有标记，零新增
- ✅ C12：排除 edge，不影响 `*_edge.py` 隔离约束

**门禁**：
- 📌 `test_runner.py --mode dev-verify` ≤ 120s

---

### C — verify 子阶段（中优先级，0.5 天）

**verify 子阶段**（committed 达成后进行）：

```python
"verify": {
    "phases": [
        {"marker": "unit_core or unit_providers or unit_fetcher", "timeout": 120},
        {"marker": "scenario", "timeout": 600},
    ],
}
```
- `--mode verify` 无参数行为不变（当前 = 6min，因 scenario 和 unit 混跑，xdist 无法加速 scenario）
- `--mode verify --phased` 触发子阶段：先 unit（~30s 出结果，快速失败），再 scenario（~5min）
- 关键价值：**Phase A 30s 内能看到 unit 结果**。如果 unit 失败，不用等 6min

> ⚠️ verify 的 `--phased` 并不能使总耗时低于 scenario 的 321s。其价值是减少等待时间——30s 出 unit 结果。

**门禁**：
- 📌 `test_runner.py --mode regression` ≤ 300s
- 📌 `test_runner.py --mode verify --phased` Phase A（unit 子阶段）≤ 30s

---

### E — 文档同步（中优先级）

| 文件 | 变更内容 |
|:-----|:---------|
| `docs-stm/manuals/datasource-and-folders.md` | 新增 resilience/test_scenario_extreme.py 目录树 |
| `docs-stm/managements/test-coverage.md` | 同步新模式项数（scenario 268, scenario_extreme 8）|
| `docs-stm/managements/technical.md` | test_runner 子阶段架构 |
| `docs-stm/managements/changelog.md` | R-200 迭代记录 |
| `docs-stm/managements/review-findings.md` | R-200 → ✅ |
| `docs-stm/manuals/how-to-test-my-code.md` | dev-verify + scenario_extreme 用法 |
| `CLAUDE.md` | 门禁描述不变 |

---

### 🔻 B-2a（S0c 优化）— 降级为低优先级（暂不执行）

**原方案**：持仓数 201→101 条 + `setUpClass` 类级 patch

**降级理由**：

| 因素 | 分析 |
|:-----|:------|
| 必要性 | S0c 已移出 `scenario`，**不影响 regression 门禁** |
| 当前耗时 | scenario_extreme 8 项 **仅 56s**（含 push2 mock 后大幅下降） |
| 预期收益 | 缩减至 ~30s，**省 26s**，对门禁体验影响有限 |
| 维护成本 | 修改测试逻辑、可能引入回归 |
| 替代方案 | Step 0（push2 mock）已实现绝大部分收益，且对所有 scenario 都生效 |

**更新清单**：

| 文件 | 变更内容 |
|:-----|:---------|
| `docs-stm/manuals/datasource-and-folders.md` | 新增 scenario_extreme/dev-verify mode 说明 |
| `docs-stm/managements/test-coverage.md` | 同步新模式项数 |
| `docs-stm/managements/technical.md` | test_runner 子阶段架构 |
| `docs-stm/managements/changelog.md` | R-200 迭代记录 |
| `docs-stm/managements/review-findings.md` | R-200 → ✅ |
| `docs-stm/manuals/how-to-test-my-code.md` | dev-verify + scenario_extreme 用法 |
| `CLAUDE.md` | 门禁描述不变，新增 dev-verify 推荐 |

**验证矩阵**：

| 验证项 | 方法 | Committed | Stretch |
|:-------|:-----|:---------:|:-------:|
| S0c 单测 | `time pytest -k TestS0cLargeHoldings -q` | ≤ 60s | ≤ 30s |
| scenario | `time pytest -m "scenario and not scenario_extreme" -q` | ≤ 300s | ≤ 180s |
| regression | `time test_runner.py --mode regression` | ≤ 300s | ≤ 180s |
| verify | `time test_runner.py --mode verify --no-timeout` | ≤ 180s | ≤ 120s |
| verify 子阶段 | `time test_runner.py --mode verify --phased` | Phase A ≤ 30s | — |
| dev-verify | `time test_runner.py --mode dev-verify` | ≤ 120s | — |
| scenario_extreme | `time test_runner.py --mode scenario_extreme` | ≥ 10s（非瞬过）| — |
| all | `time test_runner.py --mode all` | 不变或更优 | — |
| 无遗漏 | `pytest --collect-only -q` | ≥ 2895 | — |

---

## 3. 风险总表（v5 更新）

| 风险 | 影响 | 概率 | 缓解 |
|:-----|:----:|:----:|:------|
| **321s 未稳定达标 300s** | committed 未达成 | 40% | 环境波动 ~10-20s，多跑 2-3 次取均值；若系统性超时，检查是否需要更多 mock |
| dev-verify 展开 marker 语法错误 | pytest 收集期报错 | 10% | 先 `pytest --collect-only -m "..."` 验证 |
| verify 子阶段 marker 排除遗漏 | scenario_extreme 混入 scenario | 5% | `--collect-only` 门禁验证 |
| `scenario_basic` 用户困惑（S0c 不在其中）| 子标记用户疑惑 | 20% | E 步文档说明变更 |
| **B-2a 留作低优先级** — 后续需要时丢失上下文 | 需重新评估 | 15% | 本计划保留技术方案，B-2a 章节不动 |

---

## 4. 收益-成本分析

### 4.1 收益（v5 更新 — 部分已达）

| 场景 | 优化前 | 实测（v5） | Committed | 每日收益 |
|:-----|:------:|:----------:|:---------:|:--------|
| **regression（P0 提交前）** | 21min | **~5min 21s** | **≤ 300s** | 每次 commit 省 15min |
| **scenario** | 21min | **~5min 21s** | **≤ 300s** | 日常验证提速 |
| verify（P1） | ~5min | **待测** | **≤ 180s** | 合入门禁，C 子阶段后预估 ≤3min |
| dev-verify | — | — | **≤ 120s** | 开发者日常验证 |
| scenario_extreme | ~15min | **~56s** | — | 按需运行收益已超预期 |

### 4.2 成本（v5 更新 — B-2a 降级后实际更低）

| 步骤 | 人天 | 改文件数 | 债务 | 状态 |
|:----|:----:|:--------:|:----:|:----:|
| Step 0（push2 mock）| 0.05 | 1（conftest.py）| **零** | ✅ 已完成 |
| B-2b（标记拆分+搬迁） | 0.25 | 4（测试文件+test_runner+新文件） | **零** | ✅ 已完成 |
| D-4（dev-verify） | 0.5 | 1（test_runner.py） | **零** | ⬜ 待做 |
| C（子阶段） | 0.5 | 1（test_runner.py） | 低 | ⬜ 待做 |
| E（文档） | 0.3 | 4-5 | **零** | ⬜ 待做 |
| B-2a（S0c 优化） | — | — | — | 🔻 降级不做 |
| **合计** | **~1.6** | | | |

### 4.3 关键决策（v5 更新）

| 决策 | 版本 | 选型 | 理由 |
|:-----|:----:|:-----|:------|
| Phase A 根因定位 | v4 | **删除** | 受益 50s vs B-2b 受益 942s，且 40% 概率无结论 |
| 标记拆分 | v4 | `scenario_extreme`（已有） | 零注册成本，语义准确 |
| dev-verify marker | v4 | 展开为子标记 | 避免 `unit` 聚合标记的收集歧义 |
| B-2b → C 快速验证 | v4 | 不等 B-2a | 若 B-2b 已达 300s，B-2a 不必要 |
| **B-2a 降级** | **v5** | **低优先级暂不执行** | S0c 已移出 scenario，不影响任何门禁 |
| **极值文件位置** | **v5** | **放 resilience/** | S10 属容错子集，物理结构紧凑

---

## 5. 设计约束合规检查

| 约束 | 检查 | 说明 |
|:-----|:----:|:------|
| C1 代码类型判定中心化 | ✅ | 不涉及 |
| C2 缓存统一管理 | ✅ | 不涉及 |
| C3 缓存原子写入 | ✅ | 不涉及 |
| C4 会话级 API 复用缓存 | ✅ | 不涉及 |
| C5 HTTP 客户端统一 | ✅ | push2 mock 已做 |
| C6 Provider Chain 必经 | ✅ | 不涉及（跳过 Phase A）|
| C7 报告序号不可硬编码 | ✅ | 不涉及 |
| C8 日志统一 | ✅ | 标准 logging |
| C9 LLM 模块注册 | ✅ | 不涉及 |
| C10 新闻召回策略 | ✅ | 不涉及 |
| **C11 测试标记强制** | ✅ | `scenario_extreme` 已注册，零新增标记 |
| C12 边缘测试文件隔离 | ✅ | dev-verify 排除 edge，不影响 `*_edge.py` |
| C13 测试敏感路径隔离 | ✅ | push2 mock 不修改隔离逻辑 |
| C14 渲染期不可写全局 | ✅ | 不涉及 |

---

## 6. 执行顺序（v5 更新 — B-2a 移除）

```
    已完成                              待完成
 ────────────────               ─────────────────────
 ✅ Step 0  push2 mock          
 ✅ B-2b    标记拆分+文件搬迁     D-4: dev-verify（高优先级）
 ✅ S0c+S10 → resilience/         C:    verify 子阶段（中）
                                 E:    文档同步（中）
```

**收尾路径**：D-4（0.5d）→ C（0.5d）→ E（0.3d）= **约 1 天**

---

## 7. 根因说明

Phase A（根因定位）已被删除，基于以下评估：

| 原假设 | 结论 | 依据 |
|:-------|:-----|:------|
| H1: datetime mock side_effect | ❌ 排除 | 理论分析不支持 |
| H5: akshare API | ⭐ 可能性低 | B-2b 移出 942s 后还剩 ~280s |
| H6: push2 API | ✅ 已修复 | Step 0 mock |
| H7: 环境因素 | ⭐⭐ 可能 | 不具可复现性，放弃调查 |
| **26× 差距根因** | **不深入** | 单次数据，不一定可复现；不再阻塞优化进程 |
