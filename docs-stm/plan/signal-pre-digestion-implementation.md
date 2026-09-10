# plan-31 信号预消化 — 实现设计

> 文档版本：0.10.16-dev
> 语义名（落地）：`signal_pre_digest`（功能开关）、`prompts_signals`（提示词信号层）、`signal_digest_block`（信号块）
> 上游分析：[`llm-quality-signal-analysis.md`](llm-quality-signal-analysis.md)（§1.2 缺口定位 / §1.3 A+B 落地建议 / §5 风险）
> 同级先例：[`decision-reflection-implementation.md`](decision-reflection-implementation.md)（实验开关 + 缓存指纹后缀同源纪律）

---

## 1. 背景与目标

**缺口**：算法层算出的确定性结论有相当一部分只走渲染层，进不了提示词；进了提示词的那部分又存在**裸值歧义**——最典型的是行业资金流向段原先把净流出拼成「主力净流入-5,000,000」（label 固定为「净流入」、数值带负号），且数据源返回顺序无排名语义、截取前 5 行不构成任何「前列」含义。模型读到的是自相矛盾的文本，只能靠推断符号含义。

**目标**：把进 LLM 的数值按「**预消化为带方向标注的一句话信号**」处理，让模型读结论而非解读裸值，降低误读率。

**非目标**（分析文档 §1.3「不做」）：不给已经带符号的盈亏/涨跌幅等数值再加文字方向——那类数值已无歧义，加文字只增 token 与噪声。

---

## 2. 落地拆分：A 缺陷修复 + B 实验增强

plan-31 原描述是单一实验项，但分析定位到两个**性质不同**的缺口，故拆成两条独立落地路径：

| 路径 | 内容 | 开关 | 理由 |
|:--|:--|:--|:--|
| **A｜资金流方向标注与排名** | 行业资金流向段改为「方向词 + 非负量」并按净额分方向排名 | **无开关**（默认路径修复） | 分析判定为**真缺陷**（label 与数值自相矛盾），属「就近修即可」。缺陷修复若挂在默认关闭的开关后，等于默认路径继续错——与项目「缺陷必修 + 配回归测试」的纪律冲突 |
| **B｜算法评级信号块** | 市场温度档位 / 持仓估值分位 / 尾部风险幅度预消化为 `信号：…` 行，注入专家复盘与持仓体检提示词 | **`signal_pre_digest`**（默认关） | 属**增值**：改变提示词内容与缓存键、影响输出风格，需要观察期，故按 P4 实验级处理 |

A 的回归测试见 `test_prompts_signals.py::TestSectorFlowBlock`；B 的门控测试见同文件 `TestSignalDigestCacheSuffix` / `TestPromptSignalInjection` / `TestGeneratorFingerprintWiring`。

---

## 3. 分层与文件

```
src/python/llm/prompts_signals.py            ← 新增：词表 + 资金流块 + 信号块 + 缓存后缀（纯计算）
        ▲                        ▲
        │                        │
prompts_action.py          generators.py / generators_orchestrator.py
（提示词注入点）            （开关读取 + 指纹后缀接线）
        ▲
prompts.py（facade 统一导出）
```

| 文件 | 变更 |
|:--|:--|
| `src/python/llm/prompts_signals.py` | **新增**。模块常量（`SIGNAL_PREFIX` / 方向词 / 风险词 / `SECTOR_FLOW_TOP_N` / `TAIL_RISK_VAR95_*`）、`_is_number` / `_flow_verdict` / `_format_signal` / `_fmt_amount`、`_sector_flow_lines` / `_build_sector_flow_block`、`_temperature_signal` / `_valuation_signal` / `_tail_risk_signal` / `_build_signal_digest_block`、`_signal_digest_cache_suffix` |
| `src/python/llm/prompts_action.py` | `_build_global_macro_prompt` 资金流段改调 `_build_sector_flow_block`（删除内联拼接）；`_build_expert_review_prompt` / `_build_health_check_prompt` 新增仅关键字参数 `enable_signal_digest: bool = False` 并在【分布】行后注入信号块 |
| `src/python/llm/prompts.py` | facade 增加 `prompts_signals` 导出段 |
| `src/python/config/features.py` | `_FEATURE_FLAGS_DEFAULT` 增 `"signal_pre_digest": False`；`EXPERIMENTAL_FEATURES` **追加**条目（驱动 TUI 菜单 S / Web 面板） |
| `src/python/llm/generators.py` | `generate_expert_review` / `generate_health_check`：读开关 → 传 `enable_signal_digest=` 给 builder；指纹闭包无条件追加 `_signal_digest_cache_suffix(pipeline_data)` |
| `src/python/llm/generators_orchestrator.py` | `_compute_module_cache_info` 新增仅关键字参数 `pipeline_data`；`fp_expert_review` / `fp_health_check` 追加同一后缀（`fp_penetration_deep` 不追加） |
| `src/static/web/main.js` | `CONFIG_LABELS.experiments` 增「信号预消化」中文标签 |

---

## 4. 关键设计

### 4.1 词表与格式（下游解析器的唯一基准）

```
SIGNAL_PREFIX = "信号："
方向轴（有明确好淡方向的指标）：看多 / 看空 / 中性
风险轴（只有幅度、没有好淡方向的指标）：风险高 / 风险中 / 风险低
行格式：信号：{指标} {结论}（{依据}）
```

**为什么分两个轴**：尾部风险只有「幅度」没有「方向」——强行套「看空」会把「波动大」误述成「看跌」。两轴正交，各用各的词表。全中文（中英混排会引入词边界坑），固定行首前缀便于下游解析器匹配。

### 4.2 资金流块：方向词 + 非负量 + 分方向排名

```
【行业资金流向】
净流入前列：
银行  涨跌+1.20%  主力净流入500.0万  净占比+2.50%
净流出前列：
医药  涨跌-1.10%  主力净流出1.20亿  净占比-6.00%
```

- **方向由词承担、金额取绝对值**——「主力净流出 1.20亿」替代「主力净流入-1.2亿」，方向与数值不再互相矛盾。
- **净占比保留正负号**：它是比率而非金额，且同行已有方向词可对照，去掉符号反而丢了相对强弱。
- **分方向排名（而非合成一张榜）**：与分析的「按净额降序取前 5」有意偏离——只取降序前 N 在全市场净流出日会退化成「回撤最小的 N 个行业」，恰好丢掉风险侧最需要看的信号。故改为净流入降序取前 `SECTOR_FLOW_TOP_N`、净流出升序取前 `SECTOR_FLOW_TOP_N`，两个方向恒可见。
- **无方向数据回退**：全为 0 或缺失净额时无方向可分，退回数据源原始顺序前 N 行（保持既有行为，不引入新的空输出）。
- **非有限值不入提示词**：`_is_number` 统一排除 `bool`（`True` 会被当 1 元）与 `NaN`/`±inf`（格式化后是 `nan`/`inf` 文字，比裸数值更糟），按「无此字段」处理。

### 4.3 信号块的三路取用

| 信号 | 来源键 | 判定 | 依据（括号内） |
|:--|:--|:--|:--|
| 市场温度 | `market_temperature_data` | 低估→看多 / 高估→看空 / 其余→中性 | 档位 + 温度分 |
| 持仓估值分位 | `valuation_data.by_code` | 低估只数 > 高估只数→看多，反之看空，并列→中性 | 各档位只数分布 |
| 尾部风险 | `tail_risk_data` | VaR95 ≥3.0→风险高 / ≥1.5→风险中 / 其余→风险低 | VaR95 + 最大单日跌幅 + 最长连跌 |

- **逐只估值分位对模型是噪声**，聚合成「几只低估 / 几只合理 / 几只高估」的分布才有信息量；并列时判中性，不硬造方向。
- **三路独立取用**：缺键、`available` 为假、档位缺失都只跳过该项，不阻断其余信号、不报错（数据降级已在数据源侧披露，此处不重复告警）。
- **全部不可用 → 空串**，调用方据此跳过拼接，提示词与未启用时**逐字节一致**。
- 阈值（`TAIL_RISK_VAR95_HIGH/MEDIUM`）为具名常量，启发式标定；原始数值同行给出，模型可自行判读，阈值只决定档位词。
- 归一化用 `_fmt_amount`：万/亿 沿用（省 token），未达万级补「元」防裸数字无单位。

### 4.4 注入点与 v1 边界

信号块注入**专家复盘**与**持仓体检**两个模块，位置在【分布】行之后、【持仓明细】之前——先给结论，再看明细。

- 参数 `enable_signal_digest: bool = False` 为**仅关键字**，默认关；默认路径（含辩论模式各阶段）不传该参数 → 提示词不变、辩论缓存键不受影响，属**已文档化的 v1 边界**（比照 `decision_ledger._LESSON_RECEIVER_MODULES` 的单模块边界先例）。
- `pipeline_data` 是既有参数，三路信号全部取自既有数据契约，**不新增 `pipeline_data` 键** → 附录 H 的 pipeline_data Schema 契约不变。

### 4.5 缓存指纹后缀（读写键同源）

信号块改变提示词内容，但既有指纹输入（市值/成本/持仓/分类/风险摘要）不变——不处理后缀就会出现「提示词带新信号、缓存内容还是旧信号」的错配。处置方式比照 `decision_ledger.lessons_cache_suffix()`：

- **开关判定收敛在 `_signal_digest_cache_suffix()` 内部**（函数自门控），写侧指纹闭包与 orchestrator 预检闭包都**无条件调用同一函数**，避免两侧各自读开关时漂移。
- 开关关闭或块为空 → `""`：缓存键与未注入信号时逐字节一致，不误伤旧缓存、不因开关切换强制全量重生成。
- 注入时取块内容指纹（`_` + 12 位）——信号数值变化即换键，自动失效并带新信号重生成。
- `fp_penetration_deep` **不追加**：穿透深度分析不承接信号块，其提示词未变，键不该变。

> **已知偏差（另案登记）**：`_compute_module_cache_info` 对 expert_review/health_check/penetration_deep 传了 `history_data=`，而写侧指纹闭包不传，两侧基础指纹本就不同 → 这三个模块的**预检**缓存从不命中（模块总被派发，内层 `generate_llm_module` 缓存仍正常服务，故属性能/日志噪声而非正确性缺陷）。本次只保证**后缀表达式两侧逐字一致**——写侧修好键差时预检自动跟随。该偏差已登记 `review-findings.md`，不在 plan-31 范围内修复。

---

## 5. 架构约束自查

| 约束域 | 自查 |
|:--|:--|
| LLM 模块注册 | `prompts_signals` 是提示词层的纯计算子模块，不注册为 LLM 模块、不新增模块键 |
| pipeline_data 数据契约 | 只读既有键，不新增键 → 附录 H 的 Schema 契约不变，无需登记新键 |
| 缓存层 | 后缀函数纯计算、无 I/O；读写两侧同调同一函数（同源纪律） |
| 测试 | 新测试均标 `unit` + `unit_llm`；异常输入用例独立成 `test_prompts_signals_edge.py`（`edge` 标记，满足边缘测试文件隔离）；不触碰 `data/config/`、`data/holdings/`；无 LLM 真实调用；无单例/持久化文件新增故无需 conftest 变更 |
| 语义命名 | slug `signal_pre_digest` 即代码标识符；无任务代号进入实现层（历史痕迹与语义命名索引双脚本均过） |
| 不引新依赖 | 无 pydantic/langchain/SDK，仅用标准库 `math` 与既有 `_fmt_wan`/`compute_fingerprint` |

---

## 6. 测试

| 文件 | 覆盖 |
|:--|:--|
| `src/test/unit/llm/test_prompts_signals.py`（新增，31 例） | 资金流方向词/非负量/排名/截断/双方向可见/空输入；`_fmt_amount` 单位边界；三路信号的方向映射与降级跳过；尾部风险档位边界（1.5 / 3.0）；缓存后缀的开关门控与确定性；两个提示词构建函数的注入开关；两个生成函数的指纹接线 + orchestrator 预检后缀 |
| `src/test/unit/llm/test_prompts_signals_edge.py`（新增，21 例） | 非 dict 行/全非 dict/bool 净额/NaN 净额/字符串涨跌幅/极端净额/缺键回退；`pipeline_data` 结构畸形、未知档位、非数值分位与 VaR95、缺可选字段；开关关闭时畸形数据无感 |
| `src/test/unit/web/test_config_edit.py` | 白名单与 surface 断言纳入 `signal_pre_digest` + 新增写生效用例 |
| `src/test/unit/handlers/test_handlers_config.py` | 新增菜单第 10 项切「信号预消化」+ 第 6 项编号连续性保持 |

---

## 7. 文档同步

`plan.md`（plan-31 状态）· `changelog.md` · `requirements.md`（features.json 28→29 项 + 开关表行）· `folders.md`（新增文件与统计）· `how-to-config.md` / `how-to-config-llm.md` / `how-to-use-tui-menu.md` / `how-to-use-web-mode.md`（实验开关清单与编号）· `review-findings.md`（§4.5 偏差另案登记）

> 功能开关类实验项按 `decision_reflection` 先例不入 `technical.md`「功能语义命名表」（该表以 `report_submodules` / 报告章节 / 配置面为范围）。
