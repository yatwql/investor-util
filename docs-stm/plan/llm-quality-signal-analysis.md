# 信号预消化 · 模块质量分级 · 结构化决策头 — 深入分析（plan-31/32/33）

> 文档版本：0.10.16-dev
> 来源：外部仓库 TradingAgents-astock 借鉴评估（2026-09-04）→ plan.md `plan-31/32/33`
> 状态：深入分析完成（未立项实施）
> 关联：`docs-stm/managements/plan.md` P4 · `docs-stm/managements/review-findings.md` `rf-295` · plan-30 分析 `docs-stm/plan/reflection-decision-loop-analysis.md`
> 三者同属一条主线：**LLM 输入/输出质量治理三层**——输入侧（喂数值前预消化）、输出侧（成稿后质量分级）、决策头（结构化产出 + 确定性解析兜底）。

---

## 0. 三者关系与共同结论

| 借鉴点 | 治理层 | 外部对应 | 我方缺口 | 价值 |
|---|---|---|---|---|
| plan-31 信号预消化 | **输入侧** | 数据层数值附 `Signal: … INFLOW (bullish)` 单行 | 资金流裸值「净流入-500万」歧义；一批算法评级(温度/估值/尾部风险)已算出却不进 LLM | 低~中（我方多数数值已带符号方向，唯资金流与闲置评级是真空白） |
| plan-32 模块质量分级 | **输出侧** | `quality_gate.py` A~F 分级 + LLM 复审，劣级不阻断、注入下游谨慎使用 | 只有"整篇成功/失败"二元 + fallback 占位，无输出质量分级、无下游透传 | 中（对输出可信度治理是结构空白；`rf-295` 即同域最小案例） |
| plan-33 决策头结构化+解析 | **决策头** | `structured.py`（结构化+free-text 兜底）+ `rating.py`（词边界确定性解析） | provider 无 SDK 结构化；唯一 JSON 先例是"失败丢默认值"；决策词纯展示无人解析 | **高**（plan-30 决策登记、plan-31 信号归一、乃至报告语义化的公共底座） |

**共同架构前提**：我方 LLM 层是**裸 httpx 直连、无 pydantic/SDK**（`pyproject.toml` 无相关依赖）。因此三者**都不能照搬 provider 端结构化**，而应落在「拿到原始文本之后、`markdown_to_html` 之前」用确定性规则做。三者也共享同一条纪律：**决策/信号词一旦被静默误判或落默认值，会污染下游统计且报告看不出**（外部 rating.py 修三轮的教训 + 我方 `rf-295`）。

---

## 1. plan-31 信号预消化

### 1.1 外部机制
数据层在把数值写进给 agent 的上下文前，用确定性阈值紧跟一行机器可识别信号（`a_stock.py:1905-1907` 北向、`:2102-2106` 主力）：
```
Close: 主力净流入=…万元
Signal: Net main force INFLOW (bullish)   # >0
Signal: Net main force OUTFLOW (bearish)  # <0
```
让模型读到「方向结论」而非裸值，且格式统一可被后续解析。

### 1.2 我方现状（盘点要点）
- **多数喂 LLM 数值已带方向**：盈亏/涨跌全是符号位 `+.2f%`/`+,.0f`（`_fmt_holding_line` `prompts_core.py:454-477`、metrics 表 `prompts_tables.py:98-161`），符号即方向，无需额外标注。
- **唯一真裸值歧义点**：行业资金流向段 `prompts_action.py:78-94`——`main_net_inflow` 负值时文本拼成「主力净流入-5,000,000」这类方向只能靠负数符号、且 label 没说带符号；仅喂 `global_macro`。数据源 `akshare_extras.py:250-317 get_sector_fund_flow()`（行业级，个股/北向资金我方**不拉取**）。
- **一批"算法已产出评级"却从不进 LLM**（预消化低垂果实）：市场温度 低估/合理/高估（`market_temperature.py:58-60,136`）、估值分位 tier（`valuation_percentile.py:106`）、尾部风险 VaR/连续下跌（`tail_risk.py:29`）、风格因子/基金风格六宫格——这些只走 Excel/HTML 渲染，任何 prompt builder 都不消费（agent 已核对）。
- **现有中文方向实践多但非机器格式**：HHI 低/中/高、Beta 偏高/偏低、概念集中度、再平衡超限「减仓/加仓」⚠、汇率风险句等——都是"确定性阈值→内嵌中文词"，无统一前缀、不可被下游解析。
- **统一拼接点**：`skeleton.py:454-458` `_run_standard_mode` 对全部 4 模块 + 辩论共 7 次生成统一追加 `_build_prompt_appendix`（`prompts_tables.py:504`）。但该函数现只收 `(holdings_details,total_mv,total_cost,total_profit)`，看不到 metrics/温度/估值。

### 1.3 落地方案（拟）
**不扩 `_build_prompt_appendix`**（牵动 7 次生成、缓存键全变，代价大）。改为**就近 + 局部**：

- **A（推荐，最低成本）**：修 `prompts_action.py:78-94` 资金流段——净额按符号输出「主力净流入/净流出」中文词 + 非负展示量，并先按净额排序再取 top5（akshare 未显式排序，现 top5 无方向意义）。仅影响 global_macro，无缓存耦合（该段在 user_prompt 内、本就随数据日更）。
- **B（增值）**：把市场温度/估值分位/尾部风险这类"算法已出 tier、却不进 LLM"的评级，选择性桥接进 expert_review/health_check 的上下文（`pipeline_data` 已含，`prompts_core.py` 加一小段）。价值在于让模型看到组合估值状态而非只有持仓盈亏。
- **不做**：给已带符号的盈亏/涨跌补文字方向——收益低、徒增噪音。

**设计要点**：信号行若做统一格式，需选词表（`INFLOW/OUTFLOW` vs 中文「净流入/净流出」）。项目是全中文报告，倾向中文词 + 稳定前缀（如 `信号：…`），且格式进提示词词表常量以便 plan-33 的解析器可读。

---

## 2. plan-32 模块级质量分级注入

### 2.1 外部机制
`quality_gate.py` 双层门控，**坐在分析师之后、下游消费之前**：
- **Layer1 纯代码硬检查**（`_hard_check_report:34-64`）：空→F、过短(<200 char)→D、含「无法获取/I cannot retrieve…」等失败标记→D、缺失≥3→C、缺汇总表格→B、全好→A。
- **Layer2 LLM 复审**（一次调用，`create_quality_gate:118-168`）：逐分析师给 A~F + 数据时效 + 缺失项，产出「数据质量门控结果」写进 state。
- **不阻断不重试**：劣级照常流向下游，但下游（辩论/PM）读到"此篇 C/D/F、谨慎使用"。`structured.py` 同精神——结构化失败**回退一次 free-text，管道永不断流**。

### 2.2 我方现状（盘点要点）
- 输入侧降级治理**成熟且丰富**：`report/data_status.py DegradationTracker`（双信号+自适应阈值+跨会话持久化），事件写 LLM prompt（摘要块 `prompts_core.py:203-227` 仅 degraded、详细块 `prompts_tables.py:213-256`）与报告数据源矩阵。但**全部是输入数据源侧**，无一键描述"某篇 LLM 输出的质量"。
- 输出侧只有**整篇二元状态**：空→None→fallback 占位（`fallback.py:21-119`，占位对任何失败原因同质）；截断→追加 `【⚠ 输出已被截断…】` 行内标记（`api_base.py:123,474-491`）→自动 1.5× 重试一次→**仍截断则判成功、无状态**（`skeleton.py:158-196`）；fact_check 只校数字。
- **无任何"过短/失败标记/缺必需结构"的输出分级**，无 A~F 归一，无把"此篇劣级"写进下游的 state 载体。
- **报告装配传的是裸 4 元组 HTML**（`generators_orchestrator.py:721-722` 返回 4 字符串+缓存旗标），模块失败态只在全局 `LLM_MODULE_FAILURE`。
- **`rf-295`（本次分析发现）是同域最小案例**：health_check 详细块收不到 `degradation_events`（调用点漏传）恒显"今日无降级"，与 expert 摘要可能矛盾——即"质量信号没透传到该透传处"的现成实例。

### 2.3 落地方案（拟）
**分级硬检查 + 透传，不做 LLM 复审**（外部 Layer2 一次额外 LLM 调用对每篇模块不值当；我方模块少且 fact_check 已覆盖数值）：
- **Layer1 硬检查器（净新增）**：对 4 篇最终 HTML 剥标签文本后判 A~F——空→F；短于阈值(按章节典型长度定)→D；含失败/占位标记(`无法生成`/`暂不可用`/`截断标记`)→D；缺必需结构(如 expert 缺操作建议区/health 缺五维)→C；余 B/A。纯代码、零 LLM、零网络。
- **透传载体**：仿 `data_degradation` 通道，把每模块 `{module_key, grade, reason}` 写成报告可见结构（HTML 单章顶部质量提示 + Excel 模块明细加列），**让读者看到"此篇为降级文本、谨慎采信"**——而非像现在截断/占位那样混在正文里无人标识。
- **不做下游 LLM 再消费**（外部把门控结果喂辩论）：我方模块间无强下游依赖，透传到"报告展示 + 未来 plan-30 决策登记时排除劣级"即可。
- **`rf-295` 修复可作起步验证**：先修 degradation_events 透传（打通"质量信号流动"的管道），模块级 A~F 在此管道上加新载体。

---

## 3. plan-33 决策头结构化 + 确定性解析兜底

### 3.1 外部机制
- **`structured.py`**：agent 用 `with_structured_output(Schema)`（provider 不支持则跳过），结构化调用失败→**回退一次 free-text**，管道永不断流。`rating.py` 就是这条 free-text 路径的确定性"渲染回收"。
- **`rating.py`**：把自由文本里的评级词归一到统一 5 档。纪律(血泪注释)：label（`Rating: X`/`最终评级：卖出`）优先于裸词；中英混排；**词边界判据="后面不能延续成更长词" `(?![A-Za-z0-9_])`**而非枚举标点；防正则回溯；长词优先；默认值兜底；配 22 例边界矩阵测试（`Buyer interest`/`Sell-off`/`Buy（…）`每轮漏一个都静默改写评级）。

### 3.2 我方现状（盘点要点）
- **provider 无结构化能力**：三客户端裸 httpx payload（`_api_claude.py:70-75`/`_api_openai.py:54-63`/`_api_gemini.py:63-73`），无 JSON mode/tools/response_format；无 pydantic/SDK 依赖。
- **唯一结构化先例 news_correlation**：靠 prompt 要求 JSON + `json.loads` 后置解析（`generators_news.py:45-108`），**失败→整批丢→默认值填充，不重试不走 free-text**；词表不做归一校验（模型给 `"relevance":"HIGH"` 原样透传）。**反面教材**：默认值兜底把"模型没给"与"判断中性"混为一谈，若移植到决策域会静默改写评级。
- **确定性解析纪律先例丰富但不在决策词域**：fact_checker 数值/排名（`fact_checker/_patterns.py` re.ASCII + 邻接约束）、`_hallucination_filter.py:158` 显式词边界（注释明言 `\b` 中文失效）、news_dedup 长词优先——都是可复用的中文边界样板。
- **决策词全仓库无解析、纯展示**：「操作建议」表只在 prompt（`prompts_action.py:270-278`）无代码词表常量；Markdown 表格被 `markdown.py:33-102` 降级 `<p>`；原始 Markdown 在 `skeleton.py:107` 转 HTML 前即丢；Excel/HTML/TUI 消费面都不复读 `减仓/加仓/持有`。`schemas/history.py:84` 的 frozen dataclass + `Literal["新增",…]` 是现成词汇表范式。

### 3.3 落地方案（拟）
**等价移植 structured.py（无 SDK 版）+ 新增 rating.py 式决策头解析器**：
- **不做**：引入 pydantic/langchain SDK（与直连 HTTP 架构相悖，外部 Gemini extra 移除即此教训）。
- **结构化产出（可选加强）**：expert_review/debate 除展示用 Markdown 表格外，提示词另附一段受控 JSON（仿 news，但**词表列 `Literal["减仓","加仓","持有"]`/`["高","中","低"]` 进代码常量**）。产出时机在 `skeleton.py` 拿到原始文本、`markdown_to_html` 之前（`_execute_llm_with_finalize` 有 `raw_filter_fn` 先例可在此拦原始文本）。
- **确定性解析兜底（核心，净新增）**：决策头归一解析器，输入原始 Markdown 抽统一词表。纪律照抄 rating.py：label（列头/紧邻品种行）优先裸词、"不能延续成更长词"负前瞻、中英混排、长词优先、默认值兜底；中文边界复用 `_hallucination_filter` 显式 `[^…]` 风格（`\b` 中文失效）+ fact_checker 邻接约束。**配边界矩阵测试**（同外部 22 例精神：`加仓(价值修复)`/`减仓-控制回撤`/`持有并观察` 等不误判）。
- **失败流 = structured→free-text→确定性解析**：对齐外部"结构化失败→free-text"的**等价物是"解析失败→用同一文本走确定性解析"，而非 news 的丢默认值**。真正二次 LLM 才复用 `_calm_retry`/debate 回退先例。
- **落点**：这是 plan-30 决策登记抽取、plan-31 信号归一的**公共前置**。生成时原始 Markdown 尚在处执行（HTML 无表结构可逆）。数据落点建 frozen dataclass（仿 history.py + Literal）并纳入 conftest `_isolate_sensitive_paths`。

---

## 4. 三者协同与实施顺序

```
plan-33 决策头解析器（公共底座）
   ├─→ 支撑 plan-30 决策登记抽取（Phase A 的代码/方向/置信度结构化）
   ├─→ 支撑 plan-31 信号归一（统一词表 + 可解析格式）
   └─→ 决策词从"展示文本"变"可解析数据"，报告语义化
plan-31 信号预消化（输入侧，独立、最小）
plan-32 模块质量分级（输出侧；rf-295 修复是最小起步）
```

**建议实施顺序**：先 **plan-33 的解析器 + 词表常量**（为 30/31 铺路，且独立可测）→ 再 plan-31 资金流段就近修 + 可选评级桥接 → plan-32 做硬检查分级与透传载体（rf-295 先行）。三者皆 P4 实验级、缺省关闭。

---

## 5. 风险与不做清单

- **不引入 pydantic/langchain/SDK**：架构冲突，三 provider 原生结构化能力不一（Anthropic Messages 无原生 JSON mode）。
- **决策/信号词静默误判 = 污染统计**：默认值兜底（news 模式）不可移植到决策域，必须"结构化失败→free-text→确定性解析"双保险 + 词表归一校验 + 边界矩阵测试。
- **缓存耦合**：改统一 prompt 附录会动全部 7 次生成缓存键；故 plan-31 选就近改、不扩附录。plan-33 若在提示词附 JSON 也会改 fingerprint→必须同步（教训同 plan-30 §4）。
- **质量分级不停流不重试**：劣级照常展示 + 明示"谨慎采信"，不做隐藏丢弃。
- **信号格式语言**：项目全中文，倾向中文词 + 稳定前缀，避免中英混排再引入解析边界问题（rating.py 的中英混排是坑）。
- **测试隔离**：新增持久化/词表/解析器全部纳入 conftest 隔离；解析器配边界矩阵测试（对照外部 22 例）。

---

## 6. 结论

三个借鉴点本质是给现有成熟但"只到输入数据源、决策词纯展示"的质量治理补上**输出侧与决策头两层**：

1. **plan-31** 价值最低但最便宜——资金流「净流入-500万」歧义是真缺陷，就近修即可；算法已产出的温度/估值评级选择性桥接是增值。
2. **plan-32** 填输出侧结构空白——把"此篇降级、谨慎采信"从混在正文里的截断标记/同质占位升级为报告可见的分级信号；`rf-295` 是同一"质量信号没透传"问题的现成最小案例，可作起步。
3. **plan-33** 价值最高、是公共底座——决策词从展示文本变成可解析数据，直接支撑 plan-30 决策登记与 plan-31 信号归一，且补上"结构化失败落默认值"这层隐患。纪律上必须吸收外部 rating.py 三轮修词边界的教训与 news_correlation 的"丢弃型兜底"反例。

三者都以**确定性规则 + 边界测试**落地，符合项目直连 HTTP、无 SDK 的架构约束；均 P4 实验级，先设计后实施。
