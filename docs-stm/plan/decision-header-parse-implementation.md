# plan-33 决策头结构化 + 确定性解析兜底 — 实现设计

> 文档版本：0.10.16-dev
> 语义名（落地）：`decision_header_parse`（功能开关）、`decision_header`（词表与解析模块）、`decision_word`（决策词归一）、`structured_header`（结构化决策头）
> 上游分析：[`llm-quality-signal-analysis.md`](llm-quality-signal-analysis.md)（§3.2 缺口定位 / §3.3 落地建议 / §5 风险与不做清单）
> 同级先例：[`decision-reflection-implementation.md`](decision-reflection-implementation.md)（plan-30 决策账本 + 载体纪律）、[`signal-pre-digestion-implementation.md`](signal-pre-digestion-implementation.md)（plan-31 开关门控 + 默认路径提示词逐字节不变）

---

## 1. 背景与目标

**缺口**：决策词（减仓/加仓/持有）在全仓库**只走展示、无人解析**——「操作建议」表仅存在于提示词契约（`llm/prompts_action.py:266-271`）中，`markdown_to_html` 又把 Markdown 表格降级为逐个 `<p>` 行（`llm/markdown.py`）。唯一消费方是 plan-30 的 `report/decision_llm_capture.py`，它用**子串包含**（`if keyword in op`）判方向。

**子串包含的静默误判面**（本设计要消除的隐患，正是外部 `rating.py` 修三轮的那一类）：

| 输入 | 现行为 | 应有行为 |
|---|---|---|
| `不建议加仓` | 判 **加仓（+1）** — 明确说反 | 不判定（中性/未识别） |
| `加仓或减仓` | 判 **减仓（-1）** — 取表中靠前词，实为二义 | 不判定（二义不猜） |
| `暂不减仓` | 判 **减仓（-1）** | 不判定 |
| `持有并观察` | 判 持有（0）— 碰巧对 | 持有（0） |

误判后果不是"显示错一行"，而是**按错误方向写入决策账本**（`data/state/decision_ledger.jsonl`），日后用真实行情结算时污染命中率统计与教训回灌——报告上看不出任何异常。这与分析文档 §3.1 记录的教训同源。

**目标**：把决策词从「展示文本」升格为「可解析数据」——(A) 提供带词边界纪律的**确定性归一解析器**并统一 plan-30 的解析路径（默认路径，无开关）；(B) 提供**受控结构化决策头**（实验开关 `decision_header_parse`，默认关），让抽取不再依赖脆弱的 Markdown 表格形态。

---

## 2. 落地拆分：A 缺陷修复 + B 实验增强

沿用 plan-31/plan-32 已验证的分拆纪律：

| 路径 | 性质 | 开关 | 判据 |
|---|------|------|------|
| **A｜决策词归一解析器** | **真缺陷修复**（子串匹配会写反方向） | 无开关，默认路径生效 | 误判会污染账本 → 属缺陷而非增强 |
| **B｜结构化决策头** | 增强（提升抽取鲁棒性） | `decision_header_parse`，默认关 | 模型可忽略 → 属增强而非修复 |

A 是公共底座，B 建在 A 之上（B 解析失败即回落 A，**永不落默认值**）。

---

## 3. 分层与文件

```
src/python/core/decision_header.py      （新增）词表常量 + 确定性归一解析（零项目内依赖，仅依赖 decision_ledger 的方向常量）
src/python/llm/prompts_action.py        （改）受控 JSON 决策头指令（开关门控，默认路径逐字节不变）
src/python/llm/generators.py            （改）指纹后缀入 _fingerprint、开关入 _prompt 闭包
src/python/llm/generators_orchestrator.py （改）预检指纹追加同一后缀函数（读写键同源）
src/python/report/decision_llm_capture.py （改）抽取改走 decision_header + 结构化优先
src/python/config/features.py           （改）新增开关 + 注册表项
src/python/web/config_edit.py           （改）面板下发注册表显示名 experiment_labels
src/static/web/main.js                  （改）实验显示名改为服务端下发回填（删手写字典）
src/python/cli/cli.py                   （无需改）`--experiment` 已由注册表驱动
```

**为什么词表与解析器放 `core/`**：消费方横跨两层——`llm/`（提示词契约词表）与 `report/`（抽取解析）。`core/` 是本项目的零业务依赖共享层（`decision_ledger` 同层），放此处两个方向都无环。方向常量复用 `core.decision_ledger` 的 `DIRECTION_LONG/SHORT/FLAT`（**单一事实来源**，不另立一套 int 常量，避免两处漂移）。

依赖方向：`report/` → `core/`、`llm/` → `core/`，`core/` 不反向依赖任何一方。**解析器不 import `report/`** —— 满足「llm 不得依赖 report」的分层约束。

---

## 4. 关键设计

### 4.1 词表（下游解析的唯一基准）

| 类 | 词 | 方向 | 依据 |
|---|---|---|---|
| **规范词** | 减仓 / 加仓 / 持有 | −1 / +1 / 0 | 提示词契约固定（`prompts_action.py:266-271` 表头「建议操作」三值枚举） |
| **扩展词** | 清仓 · 减持 · 卖出 · 止损 | −1 | 模型漂移容忍；语义单向无歧义 |
| | 增持 · 买入 · 建仓 | +1 | 同上 |
| | 观望 | 0 | 同上 |

**只收语义单向词**：`止盈`（可能落袋一部分也可能是清仓信号）、`调仓`（方向不明）**不入词表** —— 宁可判不出（返回 None，不登记），不可判错（写反方向）。这条与「防静默误判」是同一取舍。

### 4.2 归一判据（照抄外部 rating.py 三轮修出的纪律）

1. **标签优先于裸词**（label-first）：先对**整格**做精确匹配（剥离 emoji/符号/空白后），命中即返回；整格未命中才降级为全文扫描。
2. **长词优先**：词表按长度降序匹配，避免短词劫持（`减仓` 先于任何含它的更长词）。
3. **否定前缀守卫**：命中词左侧同子句内若出现 `NEGATION_PREFIXES`（`不建议 / 不宜 / 暂不 / 暂缓 / 无需 / 不必 / 不用 / 不再 / 不要 / 不应 / 避免 / 防止 / 切勿 / 切忌 / 切莫`）或单字 `不 / 勿`，该词判为**未命中**（`不建议加仓` → None）。子句边界取标点 `，。；、,.;:!?` 与换行。**仅看命中词左侧**：右侧的限定语（`建议加仓不必追高`）不构成否定，方向仍成立。
4. **复合词左边界**：命中词紧邻左侧字符若属 `COMPOUND_PREFIX_CHARS`（`加减增`），判为复合词片段而跳过（`加减仓位`、`增减持` → 该片段不表达方向）。中文无词间空格，字符级匹配无法照搬拉丁语 `\b`，故用**窄字符集**近似：只收「加减增」三字——唯有它们能与其后的 `仓/持` 组成方向二义的复合短语；不收 `持/买/卖/清/观/止/建`，否则会误杀「坚持持有」「逢低买入」等正常表述（已编码为回归矩阵）。
5. **二义不猜**：全文扫描命中**多个不同方向**时返回 None（`加仓或减仓` → None），不做"取第一个"的静默选择。
6. **默认值兜底 = None**：判不出就返回 None。**不落「持有」或任何方向默认值** —— 这是对外部 `news_correlation`「失败 → 丢默认值填充」反例的明确拒绝（分析文档 §3.2 点名其为反面教材）。

### 4.3 结构化决策头（B 路径）

**提示词侧**（`enable_structured_header=True` 时才追加；关闭时提示词与今日**逐字节一致**，缓存指纹不受影响）：

```
【结构化决策头】
在「### 操作建议」表格之后追加一行机器可读 JSON（仅一行，不必包代码块）：
决策头：{"decisions":[{"code":"600000","action":"减仓","priority":"高"}]}
action 仅可取值 减仓/加仓/持有；priority 仅可取值 高/中/低。
```

**解析侧**：`parse_structured_header(text)` —— 去标签后按 `决策头：{...}` 提取该行 → `json.loads` → **逐字段归一校验**：

- `action` 必须能经 §4.2 归一为方向，否则该条丢弃（**不做原样透传** —— 直接修掉 `news_correlation`「`"relevance":"HIGH"` 原样透传」的口径缺失）；
- `code` 必须 6 位数字形态；
- 任一条目畸形 → 丢弃该条而非整批丢弃。全批不可用 → 返回 None → **回落 A 的确定性表格解析**。

载荷提取用**花括号配平扫描**（字符串/转义感知），而非 `find("{")`/`rfind("}")` —— 后者在同一行出现两个 JSON 对象时会把跨度拉通成一段非法 JSON。`决策头：` 后为空行时以空串兜底，不抛 `IndexError`。

**失败流**：`结构化可用 → 用结构化；结构化为空/畸形 → 确定性表格解析；表格也不可用 → 空结果（不登记）`。全程**不重试、不调 LLM、不落默认值**。

### 4.4 与 plan-30 的关系（消除重复，而非新增重复）

plan-30 已实现 `report/decision_llm_capture.py` 的表格解析（`_parse_table_row` / `_operation_direction`）。本项**不另起一套解析**，而是：

- `_operation_direction`（子串包含）→ 改为调用 `decision_header.parse_decision_word`；
- `decision_llm_capture.extract_llm_decisions` → 先试结构化头，再走既有表格行解析；
- 表格行解析、持仓白名单、baseline、同日去重等 plan-30 纪律**原样保留**。

净效果：**删掉一处脆弱实现、换上一处有边界矩阵测试的实现**，而非叠加第二套解析器。

### 4.5 落点与数据形状

不改账本 schema（`append_decision` 契约不变）。**两路解析产物形状统一**为 `{code, name, direction, magnitude, detail, carrier, baseline_close}` —— 结构化头的 `priority` 在解析侧即归一为 `magnitude`，`_collect_decision` 对两路走同一段登记纪律（持有剔除 / code 白名单 / 名称回填 / 同码取高）。`decision_header` 只负责「文本 → 方向」这一小步，其余纪律留在 `decision_llm_capture`。

**缓存键同源**：开关影响提示词 → 必须同时改**写侧指纹**（`generators.py::_fingerprint`）与**预检指纹**（`generators_orchestrator._compute_module_cache_info`），否则预检命中旧键会跳过重生成、开关形同虚设。做法沿用 plan-31 `_signal_digest_cache_suffix` 纪律：后缀由 `structured_header_cache_suffix()` **一个函数**产出（开关判定收敛在函数内），读写两侧无条件调用同一函数。关闭时返回 `""`，键不变、不误伤既有缓存。

---

## 5. 架构约束自查

| 约束 | 自查结论 |
|---|---|
| 分层 / 无环依赖 | `core/decision_header.py` 零项目内业务依赖（仅取 `decision_ledger` 的方向常量）；`report/`、`llm/` 单向依赖 `core/`，无反向 import |
| 不引入新依赖 | 纯标准库（`re` / `json` / `dataclasses`）。**明确不引入 pydantic/langchain/SDK** —— 与三 provider 裸 httpx 直连架构相悖（分析文档 §5 首条不做项） |
| 实验项默认关 | 开关缺省 `False`；关闭时提示词逐字节不变、无缓存扰动（同 plan-31 纪律） |
| 缓存键同源 | 提示词受开关影响 → 读写两侧指纹同调 `structured_header_cache_suffix()`；关闭返回 `""` 不动旧键，开启两侧同步换键（预检键 = 写侧键） |
| 失败不打断主链路 | 解析为只读旁路；开关关闭时 `is_active()` 早返回，全链路无感（沿用 plan-30） |
| 无静默默认值 | 判不出返回 None 且**不登记**；与 `news_correlation` 丢弃型兜底相反 |
| 持久化隔离 | 本项**不新增持久化文件**（写账本的路径沿用 plan-30 既有的 conftest 隔离） |
| 语义命名 | 代码标识符与文档一律语义名；任务代号仅存在于本设计文档与 `plan.md` |

---

## 6. 测试

| 文件 | 覆盖 |
|---|---|
| `src/test/unit/core/test_decision_header.py`（新增，`unit_core`） | 规范词/扩展词精确匹配；标签优先于裸词；长词优先；否定守卫全表（`不建议加仓`/`暂不减仓`/`无需减仓`/`不宜增持`/`不必买入`/`勿减仓`/`暂缓加仓`/`不用清仓`/`不再持有`/`不建仓`——末例为「不」+词，须覆盖）；二义返回 None（`加仓或减仓`）；子句边界（`减仓，但不建议加仓`）；**右侧限定语不构成否定**（`建议加仓不必追高` → 加仓）；行情优先级解析；代码提取；结构化头解析；缓存后缀随开关换键；契约文本与解析器互相锁定；空串/None/纯符号 |
| `src/test/unit/core/test_decision_header_edge.py`（新增，`unit_core` + `edge`） | 畸形输入矩阵：裸方向词嵌长句、**复合词左边界**（`加减仓位`/`增减持` → None）、**正常表述不被边界误杀**（`坚持持有`/`逢低买入`/`逢高减持`/`立即止损`/`可以清仓`/`建议观望`/`分批建仓`）、嵌套否定、emoji 与全角标点包裹、HTML 片段、超长文本、纯标点、词表外动词（`止盈`/`调仓` → None）、结构化头畸形载荷（截断 JSON / 同行多对象 / 空尾 / 非对象条目）、代码与优先级边界值 |
| `src/test/unit/report/test_decision_llm_capture.py`（既有，扩展） | 边界矩阵回归：误导性表格行不再被登记（`不建议加仓` 不入账；`加仓或减仓` 不入账；`暂不减仓` 不入账；`清仓` 正常入账）；结构化头优先于表格；畸形头回落表格；空 `decisions` 回落；整批非法 action 回落；开关关闭忽略决策头 |
| `src/test/unit/llm/test_prompts_structured_header.py`（新增，`unit_llm` + `llm`） | 开关关闭时 expert_review 提示词与基线**逐字节一致**（不扰动缓存指纹）；开启时含 `决策头：` 契约行与词表枚举、位置在行动建议表之后且持仓明细之前、契约示例行可被解析器读回；生成器指纹后缀随开关换键 |
| `src/test/unit/web/test_config_edit.py`（既有，扩展） | 白名单覆盖全部 TUI 可编辑键（含 `decision_header_parse`）；面板 `experiments` 与 `experiment_labels` 键集一致且显示名取自注册表 |

---

## 7. 文档同步

`requirements.md`（features.json 30→31 项 + 开关表行）· `technical.md`（§4 新增决策头解析小节 + features.json/白名单计数）· `llm-technical.md`（提示词层新增结构化头说明）· `folders.md`（目录树 + 统计重算）· `test-coverage.md`（计数同步）· `how-to-config.md` / `how-to-config-llm.md` / `how-to-use-tui-menu.md` / `how-to-use-web-mode.md`（实验开关清单与编号）· `how-to-use-cli-mode.md`（`--experiment decision_header_parse` 示例）· `changelog.md` · `plan.md`（状态置完成）。

**三入口**：TUI 菜单 `[S]` 实验块、Web 配置面板「实验性功能」组、CLI `--experiment decision_header_parse` 均由 `features.EXPERIMENTAL_FEATURES` 注册表驱动，新增注册项即三处自动可用。

---

## 8. 不做清单

- **不引入 pydantic/langchain/SDK**（架构冲突，见 §5）。
- **不把结构化头设为默认开启**：会让全部用户的 expert_review 缓存一次性失效，且模型可忽略 —— 收益不抵扰动，故限实验开关。
- **不做 LLM 二次复审 / 重试**：结构化失败即回落确定性解析，对齐外部 `structured → free-text` 的**等价物**，而非再加一轮 API 调用。
- **不做决策词的双向映射表**（如 `止盈` → 方向）：语义二义，宁可 None。
- **不改账本 schema、不新增持久化文件**：本项只改「文本 → 方向」一步。
