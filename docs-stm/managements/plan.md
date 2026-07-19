# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.7.3-dev

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

> 归档版本按从新到旧排列：

- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md) — v0.6.0 ~ v0.6.7
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md) — v0.5.0 ~ v0.5.12
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md) — v0.4.0 ~ v0.4.5
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md) — v0.3.0 ~ v0.3.10
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md) — v0.2.0 ~ v0.2.91
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md) — 早期版本记录

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P2** = 当前待办

### P0 — 发布门禁

（待排期）

### P2 — 基础设施前置 + 快速可见（Tier 0 + MVP）

> **依赖关系**：
> - 串行链 1：T0-01-A + T0-01-B → T0-01 → T0-02
> - 串行链 2：MVP-01~04（可并行） → MVP-05 → MVP-06
> - 交叉依赖：MVP-02 ← T0-01（概念降级感知依赖 data_degradation）

#### 摘要表

| 序号 | 任务 | 依赖 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **T0-01-A: DegradationTracker get_log() + record() + 单例工厂** | — | **5h** | 审计 4 文件 6 降级点注入 record() + 封装 get_log() + 三重实例统一为 get_tracker() 单例工厂 |
| 2 | **T0-01-B: f_context Pre-Schema 文档 + 死键清理** | — | 2h | 定义 ~12 个已有管线键 Schema + 初始类型断言 checkpoint + 删除 f_context 中 2 个死键 |
| 3 | **T0-01: DegradationTracker→LLM 接线** | ←①+② | 4h | 注入 f_context["data_degradation"] |
| 4 | **T0-02: 数据质量告警注入 LLM** | ←③ | 4h | 健康检查 3 类→5 类 |
| 5 | **MVP-01: 收益归因计算与注入** | — | 4h | profit 贡献排序注入 LLM |
| 6 | **MVP-02: 概念板块占比注入 LLM** | ←③ | 4h | Top 10 单品概念标注，依赖 data_degradation 做降级兜底 |
| 7 | **MVP-03: 再平衡极简版（硬编码）** | — | **6h** | 单品种超 15% 阈值告警+去重聚合 ⚠️ 禁止导入 report/ 包 |
| 8 | **MVP-04: 竞争语境极简版** | — | 8h | 组合 vs 沪深300 收益对比 |
| 9 | **MVP-05: LLM Prompt 整合串联** | ←⑤⑥⑦⑧ | 4h | 5 个段落集中整合到 prompts.py |
| 10 | **MVP-06: 条件推理场景块** | ←⑨ | 4h | 上涨/下跌 20% 分情景建议 |
| | **合计** | | **45h** | T0-01-A 含单例工厂（+1h） |

#### 全量任务详情

##### T0-01-A: DegradationTracker get_log() 查询接口封装 + record() 注入 + 单例工厂（前置）
- **估时**: 5h
- **文件**: `src/python/report/data_status.py`（扩展 DegradationTracker + 新增 `get_tracker()`）、`src/python/report/fund_performance.py`、`src/python/report/penetration_sheet.py`、`src/python/report/summary.py`（各改 1 行 import）
- **阻塞**: 否
- **依赖**: 无
- **已知降级调用点（需注入 record()）**: `src/python/fetcher/price.py`(L184, L200 — 2处), `src/python/fetcher/fund.py`(L47, L73 — 2处), `src/python/fetcher/industry.py`(L64 — 1处), `src/python/fetcher/index.py`(L240 — 1处)。共 6 处 fetcher 层降级点。
- **描述**: 当前 DegradationTracker 在 fund_performance.py/penetration_sheet.py/summary.py 中已实例化且 **report/ 层已有 6 处 record() 调用**（fund_performance.py:345 perf_rank、penetration_sheet.py:143/160/174 industry/profit_forecast/dividend、summary.py:285/306 index_a/index_us）——但这些全是消费侧记录。**fetcher/ 层的 6 处降级点仍然缺失 record()**。需完成：(1) 封装 get_log() → list[dict] 方法；(2) 在 6 处 `fetch_with_fallback()` / `fetch_with_incremental_fallback()` 注入 record()，区分"全链路不可用"和"fallback 降级"两种场景；(3) 在 `data_status.py` 中新增模块级单例工厂 `get_tracker()`，将三个文件级实例统一为单例（各改 1 行），消除降级状态碎片化，统一持久化路径；(4) 确保 orchestrator.py 的 data_degradation 键在记录非空时聚合并注入。
- **测试隔离要求**: 新增 `get_tracker()` 单例后，**必须**在 `src/test/conftest.py` 中增加 autouse fixture 重置此单例（参考 `_auto_reset_provider_registry` 模式）。

##### T0-01-B: f_context Pre-Schema 文档 + 死键清理（前置）
- **估时**: 2h
- **文件**: `docs-stm/plan/better-investment-advice/f_context-schema.md`（新建）、`src/python/report/orchestrator.py`（初始断言 + 清理 f_context 死键）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 定义当前生产管线已有数据键的 Schema。**注意：架构中"管线数据"分为两个独立通道——(A) `capture_snapshot()` 返回的 `f_context` 字典（`diff` 含 9 子键）；(B) `prepare_report_data()` 返回的 `prep` 字典含 13 个键。** 每个键标注：类型、所属通道、必选/可选标记、写入模块、消费模块。同时在 orchestrator.py 各管线阶段之间插入初始类型断言 checkpoint。
- **死键清理**: 删除 `f_context["diff_trimmed"]`（L246, bool 值——`_diff.trimmed` 永远是 False，下游零消费）和 `f_context["days_since_last"]`（L247, 与 `diff.days_since_last_report` 完全重复）。删除后 f_context 顶层仅保留 `"diff"` 一个键。

##### T0-01: DegradationTracker→LLM 接线
- **估时**: 4h
- **文件**: `src/python/report/orchestrator.py`（L198-248 `capture_snapshot` 构建 f_context 处注入）、`src/python/report/data_status.py`
- **阻塞**: 否
- **依赖**: T0-01-A（get_log 接口已就绪）、T0-01-B（Pre-Schema 已定义，f_context 键类型校验框架就绪）
- **描述**: `data_status.py` 的 `DegradationTracker` 已在 report/ 模块中实例化并写入降级日志，但 `capture_snapshot()` 返回的 `f_context` 字典中**没有降级状态键**。新增 `f_context["data_degradation"]`，将当天所有降级记录汇总为结构化列表。

##### T0-02: 数据质量告警注入 LLM
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`（数据质量段落）、`src/python/report/orchestrator.py`（数据质量统计字段）
- **阻塞**: 否
- **依赖**: T0-01（降级状态数据已进入 f_context）
- **描述**: 当前 LLM "健康检查" prompt 中只有 3 类数据质量提示。扩展为 5 类：(1) 收盘价异常断点；(2) T2/T3 降级发生频次；(3) 基金净值更新延迟；(4) 分红数据状态；(5) 个别品种数据缺失时长。

##### MVP-01: 收益归因计算与注入（Layer 2a）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`（新增收益归因段落）
- **阻塞**: 否
- **依赖**: 无
- **描述**: 已有每品种 `profit`，直接计算 `profit_contribution_i = profit_i / Σ|profit_j|`。按贡献降序排列，TOP 5 品种+占比格式化一段文本，注入 `expert_review` 和 `health_check` 的"收益来源"小节。⚠ **边界处理**：当 Σ|profit_j| = 0 时返回空段落，显示"暂无收益归因数据"而非 ZeroDivisionError。

##### MVP-02: 概念板块占比注入 LLM（Layer 2b）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`（新增概念板块段落）
- **阻塞**: 否（隐式依赖 penetration 管线执行成功）
- **依赖**: 无（隐式依赖 penetration.py 管线已执行）
- **描述**: 利用已有 `industry.concepts` 数据（概念板块分类），在 `expert_review` prompt 中新增段落：(1) 穿透后 Top 5 概念板块及持仓市值占比；(2) 集中度定性判断；(3) 与大盘/小盘/价值/成长风格对应关系。必须区分**三种状态**：(a) API 不可达 → 显示降级文本引用 DegradationTracker；(b) API 返回空数据 → 显示"部分品种无概念分类"；(c) 港股通/美股穿透资产无概念 → 显示"部分境外品种无概念分类"。

##### MVP-03: 再平衡极简版——单品种超阈值（Layer 3A 硬编码）
- **估时**: 6h
- **文件**: `src/python/analysis/simple_rebalance.py`（新增）、`src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: 无
- **架构约束**: ⚠️ 禁止导入 `report/` 包下的任何模块（仅消费 f_context 传入的数据）。必须 `from src.python.code_utils import ...` 而非 `from src.python.report.category import ...`。
- **描述**: 对每品种 `weight = market_value / total_value`，超 15% 硬编码阈值则输出建议。包含：(1) 建议去重聚合——超 3 品种同时触发时输出 1 条汇总；(2) 按偏离幅度排序 Top 3；(3) 单元测试包含"5 品种超阈值只输出 1 条汇总"断言。标注 `@pytest.mark.unit_providers`。

##### MVP-04: 竞争语境极简版——组合 vs 沪深 300 收益对比（Layer 5 极简）
- **估时**: 8h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: 无
- **描述**: 利用已有基准指数对比数据，在 `summary` prompt 中新增收益对比段落。格式化为两列对比表。零新数据源。基准不可用时显示"暂无足够历史数据"。

##### MVP-05: LLM Prompt 整合串联
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: MVP-01、MVP-02、MVP-03、MVP-04
- **描述**: 将上述 4 个新增段落集中整合到 `prompts.py` 的 `_SYSTEM_*` 常量中，确保逻辑顺序流畅（收益来源→板块分布→调仓建议→基准对比），无数据时整段隐藏。MVP-06 的条件推理段落放在最后。

##### MVP-06: 条件推理场景块（原 PD-01 提前）
- **估时**: 4h
- **文件**: `src/python/llm/prompts.py`
- **阻塞**: 否
- **依赖**: MVP-05（prompt 整合框架就绪后追加）
- **描述**: 在 prompt 末尾追加条件推理场景块，引导 LLM 输出两个情景分支的简要建议。
- **验收标准**: (1) 在 `expert_review` system prompt 末尾追加固定指令，要求回复末尾增加"### 情景分析"二级标题；(2) 含"📈 上涨情景"和"📉 下跌情景"两个子段落，各至少 2 句行动建议；(3) 运行 `pytest src/test/ -m "unit" -x --tb=short -q` 确认不破坏现有 prompt 测试；(4) 手动验证：修改前后两次 LLM 回复——改前无，改后应有情景块。修改范围限制在 `_SYSTEM_EXPERT_REVIEW` 常量末尾。

### P4 — 基础设施改善

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **加密 API 密钥存储** | 待处理 | 4 小时 | 当前 `llm_key.json` 明文存储 API 密钥。改用对称加密（`cryptography.fernet`），运行时解密进内存。KEK 从环境变量 `INVESTOR_UTIL_KEY` 读取，首次使用自动生成并提示用户保存。包含加密/解密函数、存量密钥迁移脚本、启动时解密失败回退提示。独立于 better-investment-advice，为通用基础设施改善项。 |
