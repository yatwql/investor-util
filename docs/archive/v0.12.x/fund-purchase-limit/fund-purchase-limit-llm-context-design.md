# 限购信息接入 LLM 分析维度 — 设计方案

> 文档版本：0.12.2-dev
>
> 定位：**设计 + 已实施**（2026-10-03 按 §6 四迭代落地：单源渲染器与契约字段 → 主路径四模块接线与指纹 → 辩论/自检/新闻批量覆盖核验 → 文档登记与 P0 门禁全绿；随任务完成归档至 `docs/archive/`）。
>
> 关联计划：`plan-73`；前置：`plan-72`（数据链路与展示集成已完成，`purchase_status_data` 契约已注入 pipeline）
>
> 范围决策（用户确认 2026-10-03）：**注入范围 = 全部 LLM 分析章节**（智囊团深度复盘、穿透深度分析为首批点名对象，其余分析章逐一盘点接线），全部复用**同一份确定性摘要渲染**（单源，不逐章各写一份）。

---

## 1. 背景与目标

**问题**：`plan-72` 落地的申购限购数据（`purchase_status_data` 契约：申购状态 / 日累计限额 / 下一开放日 / 数据时效）目前只服务持仓展示与（二期）合并联动。LLM 分析章节的提示词不含该维度——智囊团深度复盘、穿透深度分析在评估 QDII / 场外基金的加仓、合并与配置建议时，看不到「目标基金限大额 / 暂停申购」这一**可执行性硬约束**，可能给出实际下不了单的建议。

**目标**：数据完备时，把限购约束以**确定性模板块**注入全部 LLM 分析章节的用户提示词；数据不可用时提示词**逐字节回退**到引入前原样（降级零影响，与展示层同口径）。

**非目标**：

1. 不新增模型调用、不建平行配置路径（开关复用 `fund_purchase_limit`）；
2. 不改动调仓算法的数值计算（what-if / 调仓联动属 `plan-72` 迭代 4，另立任务）；
3. 不让模型「猜」限购状态——数据缺席即整块消失，绝不输出占位式猜测。

## 2. 现状比对（立项前提核验）

> 本节回应 `rf-510` 教训：立项前先做本仓库现状比对，避免「前提被既有实现推翻」。

### 2.1 分析章节全景盘点

| 章节 / 层 | 提示词构建点 | 注入路径现状 | 本设计处置 |
|:--|:--|:--|:--|
| 全球政经局势 | `llm/prompts_action.py::_build_global_macro_prompt` | `generators.py` L99 → `generate_llm_module` 标准模式 | **注入**（经统一附录，§2.3） |
| 智囊团深度复盘 | `_build_expert_review_prompt` | `generators.py` L210（及辩论变体 L422） | **注入** |
| 持仓体检报告 | `_build_health_check_prompt` | `generators.py` L286 | **注入** |
| 穿透深度分析 | `_build_penetration_deep_prompt` | `generators.py` L350 | **注入** |
| 辩论模式 pro/con | `generate_debate_procon`（`generators.py` L381，自定义 `user_prompt`） | `generate_llm_module` 辩论覆盖参数 | **注入**（已核实：附录分支不区分 prompt 来源，自定义 `user_prompt` 同获附录） |
| 辩论模式 synthesis | `_build_debate_synthesis_prompt` | `generators.py` L610 | **注入** |
| 生成后自检 self_review | `_build_self_review_prompt`（`prompts_core.py`） | 标准模式 | **注入**（已核实：附录分支覆盖 `prompt_builder` 来源） |
| 新闻 LLM 二次关联 | `generators_news.py` 批量模式（`batch_prompt_fn`） | `generate_llm_module` **批量 hooks**——不走标准模式的附录注入 | **已核实不经附录**（批量 hooks 自拼 prompt，在标准模式注入分支之外）——迭代 3 经 batch context 单点注入 |
| 行动建议章 | 确定性渲染（`action_data` 契约，无独立 LLM prompt） | — | **不注入**（数据维度经既有「行动摘要」由 `plan-72` 展示面覆盖；本设计不改其结构） |
| 调仓 What-if | `analysis/whatif*`（纯确定性，全模块无 `call_llm`） | — | **不注入**（数值可行性属 `plan-72` 迭代 4 域） |
| 事实校验 fact_checker | `llm/fact_checker/*`（纯规则：正则/数值上下文，无 LLM 调用） | — | **不注入**（职责为数值校验，非建议生成） |

**实施期核验清单（盘点表静态枚举可能漏路径，接线前先跑；已实跑注入点唯一性——`_build_prompt_appendix` 唯一调用点 `skeleton.py` L476，位于 user_prompt 选择之后、账本回灌之前）**：

1. `grep -rn "generate_llm_module(" src/python/llm/` → 全部调用点归入三路径族（标准 / 辩论覆盖 / 批量 hooks），逐点确认是否经统一附录；
2. `grep -rn "_build_prompt_appendix" src/python/llm/` → 确认唯一注入点无旁路拼接；
3. `grep -rn "call_llm" src/python/llm/*.py` → 找绕过 skeleton 的直调（已知候选：`_llm_news_correlation.py` 自述不走 `generate_all_llm` 线程池）；
4. `report/_experimental_seams.py`（实验缝）是否构造独立分析 prompt（实验挂载点集中约束的边界：实验缝已有自己的降级语义，不并入本设计则记录排除理由）；
5. **分派规则**：凡属「分析建议生成」的路径 → 迭代 3 同源接线（同一提取实例）；凡不属（规则层/实验缝/数值层） → 在 §7 决策表记录排除理由。

### 2.2 既有「确定性块 → 提示词」单源先例

| 先例 | 渲染 | 注入 | 指纹 | 对本设计的启示 |
|:--|:--|:--|:--|:--|
| 竞争语境 `competitive_context` | `generate_all_llm` 内**渲染一次** | 经 worker 分发进提示词 | 同一实例进预检侧指纹 | 「一次渲染、两侧共享同一实例」纪律 |
| 数据质量块 `data_quality_text` | 同上（docstring 明示反例后果） | health_check 提示词 | 同上 | 渲染器改而键不动 → 复用故障期旧结论 |
| 确定性信号摘要 | `prompts_signals._build_signal_digest_block(pipeline_data)` | expert/health 提示词（开关 `deterministic_signal`） | `_signal_digest_cache_suffix(pipeline_data)` 单源后缀 | 开关关闭/无信号 → 空串 → 提示词与键双不变 |
| **统一 prompt 附录** | `prompts_tables._build_prompt_appendix`（TOP3 + 数据速查表 + 代码白名单） | `skeleton._run_standard_mode` 统一追加至每个模块 user prompt 末尾，「**新模块自动获得三样防御**」 | 附录内容派生自 `holdings_details`（经 `extract_stable_holdings` 间接入键） | **唯一可让全部章节自动获得的注入点** |

### 2.3 现状结论

1. **唯一注入点已存在**：`_build_prompt_appendix` 由 `skeleton` 统一追加，标准模式四个模块、辩论自定义 prompt、self_review 均在其覆盖范围（凡 `_user` 非空即追加）；**批量模式（新闻二次关联）不经过该处**，需单独盘点接线（§3.2）。
2. **指纹纪律已结构化**：`llm/module_fingerprint.py` 为唯一事实来源（预检侧与写侧同函数），并明文约定「**进了提示词的内容必须进指纹**」「一次渲染、两侧共享同一实例」。新增提示词段必须接入 `MODULE_FINGERPRINT_BUILDERS` 所在的构造体系，不得旁路。
3. **合同数据已就绪**：`plan-72` 迭代 2 已把 `purchase_status_data` 注入 `pipeline_data`（full 路径；both/basic 无 LLM 章节），`generate_all_llm` 已持有 `pipeline_data` 形参——**数据通路零新增**。

### 2.4 架构设计约束对照（`technical.md` §8 约束表，按语义名对照）

| 约束 | 本设计对照 | 结论 |
|:--|:--|:--|
| 数据契约（pipeline_data Schema） | 不新增 pipeline 顶层键；块作为既有契约 `purchase_status_data` 的字段（§3.1 调整后）存在，类型 map 不变，契约描述同步更新 | 遵守 |
| LLM 模块缓存指纹唯一事实来源 | 新字段并入 `ModuleFingerprintInputs` 由 `MODULE_FINGERPRINT_BUILDERS` 单点提供，预检/写两侧同函数；批量路径并入 `context_fp` | 遵守 |
| 渲染期数据不可写入模块级全局 | 块在契约构建期渲染为不可变 str，经形参/契约字段流动，**不设模块级可变全局**（“一次渲染、两侧共享同一实例”以传参实现） | 遵守 |
| 报告管线实验挂载点集中 | 注入点为既有统一 prompt 附录（成熟挂载点），不新开实验缝、不内联拼接 | 遵守 |
| 时间距离以交易日计 | 陈旧档判据直接复用 `stale_level`（`count_trading_days_elapsed`，长假不计） | 遵守（复用 plan-72 资产） |
| 功能开关注册表唯一事实来源 | 开关复用 `fund_purchase_limit`，经注册表访问器读取，不建平行配置 | 遵守 |
| 代码类型判定中心化 | 场内标的排除**不靠代码前缀判定**，只以“总表查无此码”为据（结构化事实而非类型推测）；若实施中确需类型判定，必须走 `core/codetype` | 遵守 |
| 日志统一 | 渲染函数为纯函数不打日志；消费侧观测日志（§4 新增）使用 `logging.getLogger` 统一名称 | 待迭代 4 落实 |
| LLM 模块注册 | 不新增 LLM 模块，仅改既有模块的附录与指纹输入，不触 orchestrator/registry 注册 | 不适用 |
| 测试标记强制 / 边缘测试文件隔离 / 敏感路径隔离 | §5 载体纪律：既有 marker、`*_edge.py`、fixture 构造契约无网无盘 | 遵守 |
| 会话级 API 复用 / HTTP 客户端统一 / Provider Chain 必经 | 本设计零新增网络请求（数据经契约） | 不适用 |
| 报告序号显示名不可硬编码 / 新闻召回可配置 / 路径绝对化 / Multi-LLM 链 / 凭据分离 / 图表图下说明 / 凭据不落日志 / 重试唯一原语 / 间隔节流唯一原语 | 不新增报告章节序号/新闻源配置/路径键/LLM Provider/凭据/图表/凭据日志/重试/节流 | 均不适用 |

> 另对**概要设计 1.4.5 双重降级治理体系**：本设计的「块缺席 = 提示词逐字节回退」属于该体系在 LLM 提示词侧的延伸，与展示层静默隐列同口径。

## 3. 设计

### 3.1 单源确定性摘要渲染（落点 `report/purchase_status.py`，契约字段承载）

> **共享筛选单源（与 plan-74 交叉一致）**：受限行筛选与字段取值收敛为 `report/purchase_status.py` 内共享私有 helper `_filter_restricted_rows(contract, codes)`（逐行含 code/name/申购状态/时效档/日限额/下一开放日字段值），本设计的 `constraint_block` 与 plan-74 的 `restricted_index` **共用同一筛选与准入**——两套过滤逻辑必然漂移，单源化后两文档只需同步一处（已在两份设计交叉登记）。

> **依赖方向约束**：渲染器**不进 llm 层**。§7 依赖图既定 report → llm 单向（`llm → report` 今日零 import）；若在 `llm/prompts_*` import `report/purchase_status`，将新建反向边（层次倒置，当前仅因 `report/__init__` 为空心才未形成运行时环，属脆弱解）。最终：渲染器与单元格/脚注/`stale_level` 同模块单源，**契约构建期渲染一次**，以契约字段承载，llm 层只读数据不 import report。

```python
# report/purchase_status.py（既有模块追加，与 format_purchase_status_cell / stale_level 同居）
def build_purchase_constraint_block(
    contract: dict | None,
    holdings_details: list[dict] | None,
) -> str:
    """申购限购约束块（进全部 LLM 分析章提示词的唯一渲染实现）。

    准入任一不满足返回 ""；纯函数——不触网、不触盘、不打日志。
    """
```

**准入（任一不满足 → 返回 `""`，块缺席）**：

1. 契约非 None（开关 `fund_purchase_limit` 关时，上游 `build_purchase_status_data` 已直接返 None——开关经注册表访问器读取，功能开关注册表唯一事实来源约束）；
2. 契约 `available=True`；
3. 时效档位非 `expired`（复用同模块 `stale_level`，**与展示层同一判据**，交易日计时约束）；
4. 持仓∩行集内存在**非开放申购**状态的标的（开放申购不入块——正向信息不值得占 token）。

**契约承载**：`build_purchase_status_data(config, holdings_details=None)` 签名扩一个可选形参，构建契约时顺带产出字段 `constraint_block: str`（准入不过 → `""`；`holdings_details` 为空 → `""`）；若实施中发现构建点早于 holdings 就绪，则字段产出定在同函数内 holdings 就绪后的单点赋值（仍单源）。字段登记：`purchase_status.py` docstring + `technical.md` 附录 H 契约描述；**不新增 pipeline 顶层键**（类型 map 不动）。展示层不读该字段——plan-72 已交付的 Excel/HTML 行为由回归用例锁死不变。

**数据流（依赖方向 report → llm，与 §7 一致，零新增反向边）**：

```
report 侧契约构建（prepare_report_data / both 路径内联处）
  └─ constraint_block = build_purchase_constraint_block(contract, holdings_details)   # 渲染一次
       └─ purchase_status_data["constraint_block"]（不可变 str 字段）
            └─ generate_all_llm: block = (…) .get("constraint_block") or ""           # 提取一次
                 ├─ → generate_llm_module(..., purchase_constraint_block=block)        # 进提示词
                 ├─ → ModuleFingerprintInputs.purchase_block = block                   # 同一实例进指纹
                 └─ → 批量 hooks 的 context（迭代 3，同源提取）
                        └─ skeleton._run_standard_mode → _build_prompt_appendix 第 4 段
```

**「一次渲染、两侧共享同一实例」由结构保证**：渲染只发生在契约构建期一处；预检侧与写侧收的是同一 str 实例（经形参传递，不设模块级可变全局）。

**块内容（仅列受限持仓；格式确定性、按持仓顺序稳定）**：

```
【申购限购约束】（天天基金渠道口径，数据抓取于 2026-10-01；其他渠道限额可能不同，实际以下单渠道显示为准）
- 110022 易方达安心回馈债券 限大额：单账户单日限购 100 元
- 161725 景顺长城新兴成长混合 暂停申购：下一开放日 2026-12-08
- 000216 国投瑞银新兴产业混合 限大额：限额未知（以实际下单渠道显示为准）
（以上为申购可执行性硬约束：给出加仓、申购、合并类建议时必须先核对本表；场内标的无申购语义不列。）
```

- 字段与单元格文案同源：状态词、日限额千分位、下一开放日「M月D日」→ **同模块**直接复用格式化原语（**不复制**数值解释——0 元限额 → `None` → 「限额未知」的单点转换仍在解析层）；场内标的只以「总表查无此码」排除，不做代码前缀类型推测（代码类型判定中心化约束）；
- 名称取自 `holdings_details`（契约 rows 无名称字段）；缺名时回退显示代码；stale 档（4~7 交易日）附「⚠ 数据陈旧」注，与展示层同语义；
- 行序 = 持仓明细顺序（确定性、可测）。

### 3.2 消费路径（llm 层：提取一次 → 附录 + 指纹 + 批量同源）

> **组装守卫**：`_build_prompt_appendix` 返回值必须「**任一段非空即返回拼接**」——第 4 段（限购块）单独非空而其余三段为空时，不得被整体空判吞掉（否则 skeleton 侧 `if appendix:` 守卫失守、块静默丢失）。迭代 2 专项用例：仅块非空 → 返回值含块且注入发生。

**主路径（标准模式四个模块 + 辩论 pro/con/synthesis + self_review）**：

- `generate_all_llm` 从 `pipeline_data` **提取一次** `constraint_block`（与 `competitive_context` / `data_quality_text` 同位置、同纪律），形参下传 `generate_llm_module(..., purchase_constraint_block=block)`（沿「统一 prompt 附录数据」形参区追加，缺省 `""`）；
- `_build_prompt_appendix` 增加第 4 段：块为空 → 附录输出与现状**逐字节一致**；非空 → `"\n\n" + 块` 追加在三样防御之后；
- 同一实例进 `ModuleFingerprintInputs.purchase_block`（§3.3）。

**批量路径（新闻二次关联，迭代 3）**：盘点 `generators_news` 的 `batch_preparer`/`batch_prompt_fn` 上下文对象，把同一实例挂进 batch context 并并入 `context_fp`（批量缓存键）——**块非空必须进 context_fp**，否则换键不换文（或反之）。若盘点发现批量提示词空间不适合该块（新闻↔持仓关联场景价值低），可在评审时裁剪该接线点，但须在设计文档记录取舍（范围是「全部分析章」，裁剪需用户确认）。

### 3.3 指纹与缓存（唯一事实来源，按实构三块接线）

**实际结构**：`ModuleFingerprintInputs` 为带缺省值的 dataclass（已有 `competitive_context: str = ""`、`data_quality_text: str = ""` 同款字段先例）；预检侧与写侧的模块指纹均由 `MODULE_FINGERPRINT_BUILDERS: dict[str, Callable[[Inputs], str]]` 单点提供（模块 docstring 明文：两侧不得再自行拼接）；**字典外**另有独立键源（如新闻批量 `_batch_preparer` 的 `context_fp = compute_fingerprint(holdings_summary, penetrated_assets)`），须单独接线。

1. `ModuleFingerprintInputs` 新增字段 `purchase_block: str = ""`（缺省与既有字段同风格）；
2. **并入方式必须条件化**：各构造函数仅在 `inputs.purchase_block` 非空时才追加该 part——**禁止无条件拼接**（否则空串 + 分隔符也会改变哈希输入，“块空键不变”会静默失效）；
3. 覆盖面按「提示词是否真含该段」枚举：实施时列出 `MODULE_FINGERPRINT_BUILDERS` 全部键，逐键判定其模块提示词是否经统一附录——经附录者一律并入（不逐章手工挑）；字典外的新闻批量键源在迭代 3 并入其 `context_fp`（同一提取实例）；
4. 后缀语义对齐 `_signal_digest_cache_suffix`：块空 → 不并入（键与引入前完全一致，存量缓存零失效）；非空 → 参与哈希（内容变、键变——含抓取日期，跨日自然失效，与「每日报告」节律一致）；
5. **基线用例锁死**（防分隔符陷阱）：用测试内固化的样例输入，在接线前录制改造前基线摘要，断言接线后 `purchase_block=""` 时各模块指纹**逐字等于基线**；另断言「块非空 ⇒ 键变」「块内容变 ⇒ 键变」（三态），防预检/写两侧键文脱钩（`module_fingerprint.py` docstring 记载的历史教训）。基线为测试本地常量（样例输入不变），非可演进总数，不违反测试纪律。

### 3.4 降级矩阵（提示词逐字节回退）

| 情形 | 块 | 提示词 | 指纹键 |
|:--|:--:|:--:|:--:|
| 开关 `fund_purchase_limit` 关（契约 None） | 缺席 | 与引入前**逐字节一致** | 与引入前一致 |
| 契约 `available=False`（全链失败） | 缺席 | 逐字节一致 | 一致 |
| 时效 `expired`（>7 交易日） | 缺席 | 逐字节一致 | 一致 |
| 数据完备但持仓全部「开放申购」 | 缺席 | 逐字节一致 | 一致 |
| 场内持仓（查无此码） | 不列该行 | — | — |
| `holdings_details` 为空 / `None` | 缺席（准入 4 不满足） | 逐字节一致 | 一致 |
| 持仓明细缺名（明细也缺名） | 该行以代码呈现（局部回退，不缺席） | 追加块 | 含块哈希 |
| 契约对象缺 `constraint_block` 字段（旧对象/防御读取） | 消费侧 `.get(...) or ""` → 缺席 | 逐字节一致 | 一致 |
| 无 LLM 模式（both/basic，契约照建无消费者） | 块照建但零消费 | 输出零变化 | 指纹面不涉 |
| 数据完备且存在受限持仓 | 渲染 | 追加块（含渠道口径声明） | 含块哈希 |
| stale 档（4~7 交易日） | 渲染 + 陈旧注 | 追加块 | 含块哈希（与 fresh 不同） |

**硬规则**：缺席态下提示词与缓存键双不变（「数据不可用零影响」与展示层静默隐列同口径）；绝不以占位文本替代缺席。

**边界口径（交易日计时，长假不计）**：fresh/stale 分界 = 第 3/4 个交易日，stale/expired 分界 = 第 7/8 个交易日——判据唯一入口 `stale_level`（内部经 `count_trading_days_elapsed`），阶梯分档本身已由 plan-72 既有用例锁定，本设计**不重测阶梯**——只测「给定时效档 → 块出/缺席」的准入行为（给定 fresh/stale → 出块、expired → 缺席；异常样本 0 限额/缺名入 `*_edge.py`，日历以 monkeypatch 注入，无网可复现）。

### 3.5 明确不做

- 不新增任何 LLM 调用（块是确定性文本）；
- 不建平行配置路径——开关、数据、时效判据全部复用 `plan-72` 资产；
- 不改 what-if / 调仓建议的数值与路径判定（迭代 4 域）；
- 不注入 fact_checker（纯规则层）与行动建议章确定性结构（如评审认为行动摘要需要限购上下文，属展示面既有 `action_data` 的演进，另行登记）。

### 3.6 语义命名与登记（先定语义名再设计）

| 语义名（中文描述） | 代码标识符 | 位置 |
|:--|:--|:--|
| 申购限购约束块 | `purchase_constraint_block`（主标识） | `generate_llm_module` 形参、`ModuleFingerprintInputs` 字段 |
| 同上（契约内同义位） | `constraint_block` | `purchase_status_data` 字典字段（父键已限定域，故不重复前缀） |
| 申购限购约束块渲染 | `build_purchase_constraint_block` | `report/purchase_status.py` |

- **主语义名 = `purchase_constraint_block`**，实施时以它为语义命名表主行（行描述兼列契约字段 `constraint_block` 同义位）；迭代 4 登记 `technical.md` §6.7 功能语义命名表并过 `check-semantic-index --ci` 正反向；
- 标识符/注释/文档正文禁任务编号（`check-code-traces --ci` 负面禁止）；本设计新增代码不含任何 `plan-73` 字样；
- 块文案自身只含业务事实（代码/名称/状态/限额/日期/渠道口径），不含内部代号（模板见 §3.1）。

## 4. 风险与对策

| 风险 | 影响 | 对策 |
|:--|:--|:--|
| 指纹漏接（块进提示词不进键） | 复用旧键 → 分析结论与最新限购状态脱钩（静默陈旧） | 字段缺省 `""` + `MODULE_FINGERPRINT_BUILDERS` 条件并入 + 基线/三态用例（§3.3-5）；同一提取实例进提示词与指纹（§3.1 数据流） |
| 空串 + 分隔符改变哈希（实现陷阱） | 「块空键不变」静默失效，存量缓存无谓全量失效 | 条件并入（空则不追加 part）+ 接线前录制基线摘要用例锁死（§3.3-2/5） |
| 批量路径遗漏或 context_fp 漏并入 | 新闻二次关联章拿不到块 / 换键不换文 | 迭代 3 核验清单（§2.1）+ 该路径独立用例 |
| 盘点表漏路径（独立线程池 / 实验缝 / 直调） | “全部分析章”承诺未兑现而门禁不红 | §2.1 实施期核验清单 1~5（grep 配方 + 分派规则），迭代 3 出口项 |
| 观测缺口：事后无法判定注入与否 | 排查“为何模型没看到限购”只能猜 | 消费侧 `logger.debug`（日志统一）：注入记块行数，缺席记哪条准入不过（仅日志、不进报告产物）；迭代 4 人工验收：真实报告 grep「【申购限购约束】」 |
| 提示词变长挤占 token | 输出质量下降 | 仅列受限持仓；**不截断**（行数上界 = 持仓品种数，受限子集更小，常态个位数）；块不随档位放大 |
| 契约构建点早于 holdings 就绪 | 字段恒空、块永不出现（静默失效） | 字段在 holdings 就绪后单点赋值（§3.1）；迭代 1 验收含「有持仓时字段非空」用例 |
| 展示层误读新字段 | Excel/HTML 输出泄露提示词段 | 迭代 1 回归：断言展示输出不含块内容（展示层只读既有字段） |
| 与展示层文案漂移 | 同一事实两端表述不一 | 渲染器与单元格/脚注**同模块单源**（结构性不可能两处漂移）；llm 层只读数据不复制文案 |
| 陈旧档误用（expired 仍注入） | 过时限购信息误导模型 | 准入复用同一 `stale_level` 判据（§3.1），边界用例锁 3/4、7/8 交易日 |

**回滚策略（汇总）**：四迭代各一次提交、各自独立可 revert（§6）；迭代 2 回滚后形参缺省 `""` 使提示词与键**天然回退**，无需动迭代 1；迭代 1 无消费方，删除即回滚；任一层回滚都保持降级矩阵（§3.4）不变式。

## 5. 测试计划（逐迭代交付，用例先于接线）

**载体纪律**（与 `plan-72` 同口径：测试标记强制、边缘文件隔离、敏感路径隔离）：渲染器用例标 `unit_report`；附录/指纹用例标 `unit_llm`；生成器场景标 `scenario_llm`；异常与边界样本（0 元限额、stale 边界 3/4、7/8 交易日、缺名回退、跨长假）入 `*_edge.py` 并标 `@pytest.mark.edge` + 对应 unit 标记；附录既有回归网 `src/test/unit/llm/test_llm_prompt_builders.py`（迭代 2/3 出口必跑）；全程无网（契约与 pipeline_data 以 fixture 构造，LLM 调用全 mock）；禁止断言可演进总数（结构关系断言）；禁止无断言/重复/自证用例（`check-test-redundancy`）。

**「逐字节一致」的结构性证明方法**（不依赖已删除的旧代码）：

1. **缺省等价**：`appendix(...)` （省略块形参，缺省 `""`）≡ `appendix(..., block=""`）——证明「块缺席对输出零贡献」；
2. **同测试内对照**：降级态构造的 prompt ≡ 同输入下省略块形参构造的 prompt（两侧都在测试里现算，无黄金文件脆弱性）；
3. **指纹基线例外**：空块指纹与「接线前基线」比对必须用**测试内固化样例输入的基线摘要**（迭代 2 接线前先跑测试录制基线值，接线后断言不变）——这是唯一需要黄金值的断言，目的就是抓分隔符陷阱（§3.3-5）。

**逐迭代用例交付**：

| 迭代 | 测试交付（文件倾向） | 关键断言 |
|:--|:--|:--|
| 1 | `test_purchase_status.py` 扩展（渲染分支 + 同源）+ `test_purchase_status_edge.py` 扩展（0 限额/缺名回退；stale 阶梯与跨长假沿用 plan-72 既有用例，不重测） | 准入四条逐分支 → `""`；块字段逐项；**展示层零影响回归**（Excel/HTML 不泄露块内容）；契约字段类型正确 |
| 2 | `test_prompt_appendix`（附录第 4 段）+ `test_module_fingerprint`（基线 + 三态）+ 生成器场景（mock `call_llm` 捕获 prompt） | 缺省等价与同测对照；四模块 prompt 含块；空块 = 接线前基线摘要 |
| 3 | 盘点存在性矩阵（每章一条）+ 新闻批量 `context_fp` 用例 | 每章「完备含块 / 降级不含」成对；批量键随块变 |
| 4 | 计数/登记类（`collect-test-coverage` 快照回填、守护脚本对文档的机检） | P0 十项全绿（§6 迭代 4 验收） |

**隔离纪律**：LLM 调用全部 mock；不依赖真实持仓与真实取数；`pipeline_data` 以 fixture 构造；本设计**不新增持久化状态文件、不新增模块级单例**——故 conftest 无需新增 autouse 隔离 fixture（若实施中确需，必须同步加 `_isolate_sensitive_paths` 重定向并登记）；渲染为纯函数，不触盘不触网（测试内无需网络守卫豁免，也不得依赖守卫拦截来过测）。

## 6. 迭代拆分与验收标准

> 原则：**四迭代**，每迭代单一职责、独立可验、一次提交可单独回滚；降级态输出零变化；验收条目全部可判定。
> **出口检查（每迭代必跑，便宜门禁）**：`ruff check` + `ruff format --check` + 本迭代相关 pytest 子集 + 新改动波及的 `--ci` 守护脚本（痕迹/命名/漂移）；**终验（迭代 4）**：P0 十项全绿。

### 迭代 1 — 单源渲染器 + 契约字段（report 侧，不碰 llm 层）

**交付物**：`report/purchase_status.py::build_purchase_constraint_block`（含准入四条、字段格式化复用同模块原语、缺名回退代码）+ `build_purchase_status_data` 签名扩 `holdings_details` 可选形参并产出 `constraint_block` 字段 + 契约 docstring/`technical.md` 附录 H 行描述同步 + 单元测试。

**验收标准**：

1. 准入四条逐分支断言（契约 None / available=False / expired / 无受限持仓 → `""`）；块内容字段逐项正确（限大额日限额千分位、暂停下一开放日、0 元限额→限额未知、缺名回退代码、场内查无不列）；
2. **展示层零影响回归**：plan-72 既有展示用例全绿，且断言 Excel/HTML 输出不泄露 `constraint_block` 内容（展示层不读该字段）；
3. 边界：仅测准入三态（给定 fresh/stale → 出块、expired → 缺席）；阶梯分档与跨长假判据沿用 plan-72 既有用例（不重测，测试真值单一来源）；异常样本入 `*_edge.py`；
4. 出口检查全绿。

**回滚**：消费方为零，删除新增函数与可选形参即完整回滚（契约字段无人读写）。

### 迭代 2 — 主路径接线 + 指纹（标准模式四模块）

**交付物**：`generate_all_llm` 提取一次 `constraint_block` + `generate_llm_module(..., purchase_constraint_block="")` 形参下传 + `_build_prompt_appendix` 第 4 段 + `ModuleFingerprintInputs.purchase_block` 字段与 `MODULE_FINGERPRINT_BUILDERS` **条件并入** + 基线用例（接线前录制）+ 生成器/附录单测。

**验收标准**：

1. 数据完备：四个模块（global_macro / expert_review / health_check / penetration_deep）送入模型的 user prompt 均含块，字段逐项正确（LLM 调用 mock 捕获）；
2. 降级矩阵（§3.4）全分支：prompt 与「省略形参调用」逐字节一致（结构性不变性断言）；
3. 指纹三态 + **空块 = 接线前基线摘要**（防分隔符陷阱，§3.3-5）；
4. 块文案与展示层同源断言（复用同模块原语，无第二份数值解释）；
5. 出口检查全绿。

**回滚**：形参缺省 `""` + 附录段条件跳过，即提示词与键双回退（无需回滚迭代 1）。

### 迭代 3 — 覆盖面核验（辩论 / self_review / 新闻批量）

**交付物**：§2.1 盘点表全部「实施期核验」项落地（含核验清单 1~5：辩论自定义 `user_prompt` 附录生效、self_review 形参链、批量 hooks 上下文、独立线程池路径与实验缝的分派结论）+ 新闻批量 `_batch_preparer` 的 `context_fp` 并入同一提取实例 + 每章存在性用例。

**验收标准**：

1. 盘点表每一「注入」行均有存在性用例（数据完备 → 章节 prompt 含块；降级 → 不含）；
2. 批量路径：`context_fp` 随块变化、`_batch_prompt` 同源（该路径独立用例）；
3. 若盘点发现批量场景价值低需裁剪：记录 §7 决策并经用户确认后方可缩减范围；
4. 出口检查全绿。

**回滚**：批量接线独立提交，单独 revert 不影响迭代 1/2。

### 迭代 4 — 文档登记 + 语义命名 + P0 终验

**交付物**：`technical.md` §6.7 功能语义命名表登记（`constraint_block` 语义行）+ `testplan.md` §1.1 用例登记 + `folders.md` 目录树/统计 + `test-coverage.md` 计数刷新 + `changelog.md` 条目 + 设计文档改完成态（决策记录表补行）。

**验收标准**：

1. **P0 门禁十项全绿**：`test-runner.py --mode dev-verify` + 9 个 `--ci` 脚本（其中 `check-doc-drift` 加跑 `--with-test-count` 以核对计数表，仍属十项之内）；
2. `check-semantic-index.py --ci` 正反向通过（新语义行登记）；
3. `ruff check` / `ruff format --check` 零告警；
4. 设计文档头改「设计 + 已实施」，完成态记录齐备。

**回滚**：纯文档提交，独立 revert。

**依赖关系**：迭代 1 → 2 → 3 → 4 串行（后一迭代以前一迭代的交付物为前置）；每迭代一次提交；Jev 线与本线互不依赖。
**预估成本**：低（渲染器 + 附录一段 + 指纹字段 + 盘点核验 + 登记）；**风险**：低（每迭代降级态逐字节回退可机器证明，且可独立回滚）。

## 7. 决策记录

| 日期 | 决策 | 依据 |
|:-----|:-----|:-----|
| 2026-10-03 | 本期只出设计文档，先评审后实施 | 用户确认 |
| 2026-10-03 | 注入范围 = 全部 LLM 分析章节（非仅点名两章） | 用户确认 |
| 2026-10-03 | 注入点选统一 prompt 附录（唯一让新章自动获得的注入点），批量路径单独盘点 | §2.2 现状比对（rf-510 教训：先比对后立项） |
| 2026-10-03 | 降级态提示词与缓存键双不变（块空 = 空后缀 = 引入前原样） | 「数据不可用零影响」与展示层静默隐列同口径 |
| 2026-10-03 | 渲染器归位 `report/purchase_status.py`，块以契约字段 `constraint_block` 承载，llm 层只读数据 | §7 依赖图 report → llm 单向，消除反向边 |
| 2026-10-03 | 指纹并入必须条件化 + 接线前录制基线 | 防空串 + 分隔符改变哈希 |
| 2026-10-03 | 实施按 §6 四迭代推进，每迭代独立出口检查与回滚 | 用户要求：多迭代开发、每个迭代可验收 |
| 2026-10-03 | 需求登记沿 `plan-72` 先例：不新增需求 ID，以 `testplan.md` §1.1 模块行登记为主 | 与前序任务同粒度，避免需求域数连锁改动 |
| 2026-10-03 | 受限筛选与 plan-74 共享 `_filter_restricted_rows` 单源 | 两套过滤必漂移；跨设计交叉同步 |
| 2026-10-03 | 附录组装守卫「任一段非空即返回」+ 既有回归网入出口 | 防第 4 段被整体空判吞掉 |
| 2026-10-03 | 阶梯用例不重测、只测准入三态 | 测试真值单一来源，防与 plan-72 冗余 |
| 2026-10-03 | 核验清单 1~5 实跑结论：9 个 `generate_llm_module` 调用点全归族（8 经统一附录 + 新闻批量 batch hooks 已接线）；`_build_prompt_appendix` 唯一调用点无旁路；`call_llm` 零直调；实验缝 `_experimental_seams.py` 不构造分析 prompt（天然排除，无排除行） | §2.1 实施期核验清单（迭代 3 出口实跑） |
| 2026-10-03 | 新闻批量路径不裁剪（§3.2 预留的裁剪选项未启用）：批量提示词空间容纳块无碰撞，关联判定获得限购语境 | 每章存在性用例成对交付，裁剪需用户确认而未申请 |
