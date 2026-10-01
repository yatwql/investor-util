# LLM 成本调节、生成后自检与调用级源指定：整体设计

> 文档性质：中间设计文档（`docs-stm/plan/`，完成后随完成态归档）
> 对应计划项：`plan-63`（报告深度档位）、`plan-64`（生成后自检）、`plan-65`（调用级源指定）
> 前置：`docs-stm/plan/tradingagents-cn-research.md`（借鉴来源）
> 设计约束依据：`docs-stm/managements/technical.md` 「架构设计约束」章节与「功能语义命名表」章节
> **实施状态**：plan-63 / plan-64 / plan-65 已全部实施完成（2026-10-01），实施记录见 changelog「新增」段与 `docs-stm/archive/v0.11.x/archived_plan.0.11.x.md`。实施中相对本设计的两处调整：① §3.4 新闻条数是**同一个采集旋钮**（同时影响新闻页签与 LLM 输入，见该节修订说明）；② plan-64 的产物交付由「扩宽 llm_content 元组」改为「运行作用域载体 + 报告层零参 pull」（详见 §4.6）。

---

## 1. 设计出发点：先缺口分析，再定形态

三项均来自外部仓库借鉴，**立项前提先与本仓库现状比对**（rf-510 教训）：

| 计划项 | 现状（勘察结论） | 真实缺口 | 本设计定位 |
|---|---|---|---|
| plan-63 | `news_top_count`(300) 等调节参数散在 `config.json`；**无任何「档位/profile」概念**；LLM 模块启停由 `llm_settings.json → enabled_llm` 逐个控制 | 缺「一次选择即同时约束模块集合与输入规模」的调节面 | 新增三值 config 键 + 档位表（唯一定义点） |
| plan-64 | `llm/fact_checker/` 的 `run_fact_check` **已存在**（确定性：数值/品种/排名一致性校验 + 自动修正 + 摘要追加，跳过缓存项，在 `generators_orchestrator` 生成后统一执行） | 缺**模型层**自检（模糊表述、逻辑推演类）——确定性算法做不到 | 新增独立 LLM 模块 `self_review`，与确定性校验**分层不重叠** |
| plan-65 | `fetcher/chain.py::_get_chain` 已支持 **config 级** `preferred_provider.<data_type>`；`check_sources` 有独立单源探针 | 缺**调用级** preferred/exclude（config 是持久配置，不适合一次性排障） | 新增运行作用域覆盖 + CLI 排障入口（避免死代码） |

**共同设计原则**：三项都**不新造取数/调用路径**，只在与既有机制相同的层次上扩展；默认行为与现状**逐字节一致**（缺省零影响）。

---

## 2. 整体架构定位

三层的职责边界（自下而上）：

```
[配置/声明层]  config.json(llm_report_depth)  ·  llm_settings.json(enabled_llm.self_review)  ·  CLI 参数
      │                    ▲ 单一事实来源：档位表 / 模块注册表 / 开关注册表
      ▼
[编排/路由层]  llm/generators_orchestrator（模块集合与调度）  ·  fetcher/chain（源链路由）
      │                    ▲ 本设计：档位收窄模块集合；self_review 作为生成后一遍；chain 运行作用域覆盖
      ▼
[内容/产物层]  report/llm_content（Excel/HTML 装配）  ·  report/summary_llm_usage（用量页签）
```

三条不变量：

1. **收窄而非放大**：档位只能**收窄**模块集合上界，不得越过用户显式关闭的 `enabled_llm` 开关（避免用户关掉的模块被档位强行打开）。
2. **分层不重叠**：确定性校验（`fact_checker`）与模型自检（`self_review`）职责分离——前者查「数值/代码/排名是否有据」，后者查「表述与逻辑是否自洽」；两者都失败不影响报告生成。
3. **运行作用域不改持久配置**：CLI 的源指定只在本次运行生效（内存作用域），不写 `config.json`，与 `preferred_provider` 持久配置**优先级分层**（调用级 > 配置级 > 默认链）。

---

## 3. plan-63：报告深度档位

### 3.1 形态决策

**三值 config 键**（非布尔开关）：`config.json → "llm_report_depth": "brief" | "standard" | "deep"`，默认 `"standard"`。

不用开关注册表的原因：`feature_switch_registry` 的声明形态是**布尔 + 分组表达生命周期**（实验/常规），无法表达三值互斥档位；三个布尔开关拼档位会让「互斥档位」退化为用户自行拼装，与注册表设计意图冲突（开关注册表唯一事实来源 的分组语义也会被稀释）。

### 3.2 档位表（唯一事实来源）

新模块 `src/python/llm/depth_profile.py`：

```python
REPORT_DEPTH_LEVELS = ("brief", "standard", "deep")
REPORT_DEPTH_DEFAULT = "standard"

@dataclass(frozen=True)
class DepthProfile:
    key: str
    label: str                      # 显示名（报告自述与 CLI 提示共用，渠道层不另写文字）
    desc: str                       # 一句话说明
    max_modules: frozenset[str]     # 参与模块的**上界**（仍受 enabled_llm 收窄）
    news_limit_floor: int | None    # LLM 输入新闻条数的下界（None = 不改用户配置）

DEPTH_PROFILES = {
    "brief":    DepthProfile("brief",    "简版",  "仅全球政经，输入最小，最快最省", frozenset({"global_macro"}), None),
    "standard": DepthProfile("standard", "标准",  "四个分析模块，输入按用户配置",   ALL_MODULES, None),
    "deep":     DepthProfile("deep",     "深度",  "全模块 + 更大新闻输入，推演更充分", ALL_MODULES, 500),
}
```

- `ALL_MODULES` = 现有核心模块集合（`global_macro` / `expert_review` / `health_check` / `penetration_deep` / `news_correlation`），从 `core/registry.py` 的模块注册表派生（**不另写清单**，避免与模块注册表漂移）。
- `resolve_depth_profile(config) -> DepthProfile`：读取 → 非法值回落 `standard` 并 `logger.warning`（与既有 `_validation.py` 对非法值的处理风格一致）。
- `effective_news_limit(configured: int, profile) -> int`：`max(configured, floor)`；`floor is None` 时原样返回。

### 3.3 关键设计取舍：档位**不进提示词正文**

档位只作用于**模块集合**与**输入规模**，不写入 system/user prompt 文本。理由（模块缓存指纹唯一事实来源的直接推论）：

> `MODULE_FINGERPRINT_BUILDERS` 的覆盖判据是「该模块的提示词实际承载了哪些入参」。档位若进入提示词正文，四个模块的指纹构造必须同步并入档位值（写侧与预检侧），否则两侧键不同源 → 预检永不命中（静默全量重调，费用翻倍）或命中陈旧键（档位形同虚设）。
>
> 而档位只改「哪些模块跑」与「新闻条数」时：模块集合变化**不改变既有模块的提示词**；新闻条数变化**本来就在新闻类模块的输入摘要里**（既有 `news_top_count` 已是提示词承载入参）→ 指纹自然跟随输入变化，**无需改动任何既有指纹构造**。

**副作用与验收**：缺省 `standard` 下模块集合与新闻条数**与现状逐字节一致**（有专项用例锁定：`standard` 档位下 `needs` 与 `effective_news_limit` 与改动前同值）。

### 3.4 消费点（仅两处，均为集中点）

| 消费点 | 位置 | 行为 |
|---|---|---|
| 模块集合门控 | `llm/generators_orchestrator.py` 计算 `needs` 处 | `needs[k] = 既有开关判定 and k in profile.max_modules`——一次集中收窄，不散落到各模块 |
| LLM 输入新闻条数 | 报告管线解析 `news_top_count` 处 | `effective_news_limit(user_configured, profile)` |

**新闻条数是同一个采集旋钮**（实施修订）：`news_top_count` 在报告层同时决定新闻采集规模、新闻页签展示条数与 LLM 输入规模三者。
本设计初稿曾打算「只改 LLM 输入、不动页签」，但那样需要把同一份采集结果按两个上限裁剪（LLM 侧再切片），会引入「页签 300 条 / LLM 100 条」的双口径与额外分叉；
改为**统一作用于采集规模**：语义更简单（档位说的就是「这份报告怎么采集与分析」），也让档位效果在报告里直接可验（少采集即少展示）。

### 3.5 可观测性与自述

非默认档位（`brief`/`deep`）改变产物内容，报告须自述（沿用「报告是可脱离本机流转的文件，读者须能判断内容来源」原则）：在 LLM 用量页签写入一行「本次报告深度档位：简版（仅全球政经，输入最小）」；`standard` 不写（保持现状零噪声）。

### 3.6 降级与边界

| 场景 | 行为 |
|---|---|
| 非法档位值（如 `"deepest"`） | 回落 `standard` + `logger.warning`（报告照常，不中断） |
| `brief` + 用户只开了 `news_correlation` | 交集为空 → 不跑任何 LLM 模块，报告以占位文本呈现（既有 `LLM_MODULE_FAILURE`/`FAIL_REASON_DISABLED` 机制，不新增路径） |
| 档位值变化 | 缓存键不含档位，但档位改变会改变模块集合/输入 → 命中判定自然失效；同一档位重复运行正常命中 |

---

## 4. plan-64：生成后自检（`self_review`）

### 4.1 分层定位（与既有确定性校验不重叠）

| 层 | 组件 | 触发 | 检查内容 | 失败影响 |
|---|---|---|---|---|
| ① 确定性 | `llm/fact_checker/run_fact_check`（**既有**） | 始终（内容非空且非缓存命中） | 数值/代码存在性/排名有据性，可自动修正 | 摘要追加，报告照常 |
| ② 模型自检 | `self_review`（**新增**） | `enabled_llm.self_review = true` | 结论与数据是否矛盾、是否存在未标注的推测性表述、模块间结论是否互斥 | 模块标记失败原因，**主内容完全不受影响** |

### 4.2 形态：注册为独立 LLM 模块，但**不进并行调度**

依「LLM 模块注册」约束的两条要求分别落地：

- **在 `core/registry.py` 注册**（`DataModuleDef("生成后自检", "llm_self_review", cache_prefixes=("llm_self_review_",), cache_ttl=7200, settings_suffix="self_review", cache_groups=("preload",))`）→ 显示名、缓存前缀、TTL、用量统计、失败原因载体**全自动**获得，不建副本。
- **不进 `_MODULE_FNS`**（模块注册纪律明文允许并鼓励：「编排注册仅对确经编排线程池调度的模块生效……无人调用或无独立调度语义的注册分支属注册漂移」）：自检的输入是**其余模块的产出**，天然必须在它们之后串行执行——并入并行池会引入对产出的时序依赖。故实现为**生成后一遍**（与既有 `run_fact_check` 同位置、同风格），并在代码注释中显式说明该注册项**故意不出现在 `_MODULE_FNS`**，防止后续维护者按「注册即编排」误加。
- **配置键**：`llm_settings.json → enabled_llm.self_review`（默认 `false`）+ 标准模块族键（`model_/temperature_/max_tokens_/timeout_/cache_enabled_/thinking_*/reasoning_effort_self_review`），与既有模块**同形**，由默认模板集中生成。

### 4.3 数据流与缓存指纹

```
四个模块产出（并行） ──┐
关键数据摘要（持仓/穿透/降级事件） ──┤→ self_review 输入摘要 → 指纹（build 于 module_fingerprint）
                              └→ 一次 LLM 调用 → 【自检清单】文本 → 独立页签/卡片
```

- 指纹 = `compute_fingerprint(各模块产出文本, 关键数据摘要)`：**产出变化才重算**（内容寻址），模块级开关变化自然反映为产出变化。
- 新增 `self_review_fingerprint(inputs)` 于 `llm/module_fingerprint.py`（指纹唯一构造点），写侧与预检侧同源调用。
- **不改既有四个模块的指纹构造**（自检只读它们的产出，不改变它们的提示词）。

### 4.4 输出契约与合规红线

自检输出为**固定条目的结构化清单**（Markdown → 既有 `markdown.py` 渲染路径）：

```
【自检清单】
· 结论与行情/持仓数据是否矛盾：未发现（依据：…）
· 未标注的推测性表述：2 处（引用：…）
· 模块间结论是否互斥：未发现
注：自检由模型自我复核产生，为辅助信号，不构成质量保证；投资决策与后果由使用者自行承担。
```

红线：
1. **不得输出买卖建议**（提示词明确禁止，且 `call_llm` 已由 plan-61 的 `apply_compliance_guardrails` 统一叠加合规声明）；
2. **不得声称「已校验无误」**——固定尾注明示「辅助信号、不构成质量保证」（防止虚假信心）；
3. **失败不拖垮主链路**（自检异常 → 模块失败原因登记，报告照常产出）。

### 4.6 交付方式（实施修订）

产物交付**不扩宽 4 元组 `llm_content` 契约**。该契约在报告层多处按位置解包（Excel 页签写入、HTML 渲染、决策登记、质量分级、实验挂接点），扩宽需要同步改动 10+ 处位置解包点，属高风险低收益；且自检是「附录」而非独立分析章。

改为 **运行作用域载体 + 报告层零参 pull**：
- `llm/self_review.py` 持有本轮自检区块（模块级状态，配 `reset_self_review()`；已在 `conftest.py` 增 autouse 重置 fixture，符合「新增模块级状态必须有测试隔离」纪律）；
- 报告层以**零参函数**取用（Excel 用量页签、HTML 附录区块、`html_writer` 上下文），与既有 `report/experimental_notice.enabled_notice_line()` 同源模式——**零参数穿透，零新增契约**；
- HTML 落点为「生成后自检（附录）」区块：不占报告章节号、不参与目录导航，故既有章节结构约束与模板结构计数不变。

### 4.5 降级矩阵

| 场景 | 行为 |
|---|---|
| 开关关闭（默认） | 完全不执行、不产生调用、不使用缓存前缀（缺省零影响） |
| 上游模块全部失败/占位 | 无有效产出 → 跳过自检并登记「无有效内容可自检」，不报错 |
| 上游模块部分缓存命中 | 自检输入含缓存产出（内容一致即可复核），缓存键随产出而定，无需特判 |
| 自检 LLM 调用失败（网络/配额/内容过滤） | 复用既有 Provider Chain 与失败分类；模块标记失败原因，主内容不受影响 |
| 自检返回空/格式不符 | 保留原文 + 追加「自检未产出有效清单」标记，不静默丢弃 |

---

## 5. plan-65：调用级源指定

### 5.1 形态：运行作用域覆盖 + CLI 消费者

- **库层**（`fetcher/chain.py`）：
  - `chain_overrides(preferred: str | None = None, exclude: Iterable[str] | None = None)` 上下文管理器（**运行作用域**，可嵌套、退出即恢复）
  - `_apply_overrides(chain: list[str], data_type: str) -> list[str]`：先 `exclude` 过滤，再把 `preferred` 前置（若已在链中则移至首位；若不在已知 provider 集合中则忽略并 warning）
  - `reset_chain_overrides()`：测试隔离用（conftest autouse 重置，遵循「新增模块级单例必须在 conftest 增加重置 fixture」纪律）
- **CLI 消费者**（避免死代码）：
  - `report` 子命令新增 `--prefer-source NAME`（可重复）与 `--exclude-source NAME`（可重复），**仅本次运行、不写盘**；
  - 未知 NAME → 参数校验期即报错退出并列出全部可用 provider 名（取值域由 `_DEFAULT_CHAINS` 并集派生，不另写清单）；
  - `_handle_report` 以 `with chain_overrides(...)` 包裹 `generate_report(...)`。

### 5.2 优先级与语义（三层不冲突）

| 层 | 来源 | 优先级 | 生效期 |
|---|---|---|---|
| 调用级 | `chain_overrides(preferred=...)` | 最高 | 运行作用域（CLI 单次运行） |
| 配置级 | `config.json → preferred_provider.<data_type>` | 中 | 持久 |
| 默认链 | `_DEFAULT_CHAINS` | 最低 | 持久 |

不变量（与既有治理体系一致，**不得破坏**）：
1. **凭据未就绪的源仍主动跳过**且不计熔断（凭据不落日志与产物）；
2. **熔断语义不变**：被覆盖后置前的源若处于熔断冷却期，照常跳过并尝试链上其他源；
3. **`exclude` 过滤后链为空** → 返回 `None` + `logger.warning`（与「链上全部失败」同语义），不抛异常；
4. **缓存与诊断不变**：缓存键仍按 `data_type`+业务键（不含 provider），`FailureDiagnostics` 照常逐源记录。

### 5.3 作用域为何是「进程级」而非「线程级」

报告管线在取数阶段存在并行（`fetcher/batch.py`），线程局部变量**不会传播到工作线程**，会导致「同一次运行内部分请求生效、部分不生效」的隐式不一致。故取**进程级运行作用域**（进程内一次报告运行 = 一个覆盖作用域），语义与用户预期一致（「本次运行只用某源」）；代价是需要 `reset_chain_overrides()` 保证测试隔离（已按纪律登记 conftest fixture）。

### 5.4 降级矩阵

| 场景 | 行为 |
|---|---|
| `--prefer-source` 指向熔断中的源 | 跳过该源，按链尝试其余源（覆盖不绕过熔断） |
| `--prefer-source` 指向未配置凭据的源 | 按凭据就绪预检主动跳过并提示「缺什么、去哪申请」，不计熔断 |
| `--exclude-source` 排除全部候选 | chain 为空 → 返回 `None`，降级事件登记原因，报告按既有降级路径产出 |
| `--exclude-source` 排除不存在的名字 | 校验期报错退出（不静默忽略，避免用户以为生效） |
| 与 `config.preferred_provider` 同时存在 | 调用级优先；两者都只是**排序**，不新增/删除链上源（除显式 exclude） |

---

## 6. 架构约束逐条自检（相关性筛选）

| 约束 | 本设计的遵从方式 |
|---|---|
| **Provider Chain 必经** | plan-65 只在链内做**排序/过滤**，不新增绕过链的直调路径；所有取数仍走 `fetch_with_fallback` |
| **LLM 模块注册** | plan-64 双点登记：`core/registry.py` ✅；`_MODULE_FNS` **故意不登记**（非线程池调度，注册纪律明文允许），注释显式说明防注册漂移 |
| **Multi-LLM Provider Chain** | plan-64 自检调用仍走 `call_llm`（Provider Chain 路由，返回 `(result, usage, provider_name)` 三元组） |
| **指纹唯一事实来源** | plan-64 新增 `self_review_fingerprint` 于 `module_fingerprint.py`；plan-63 **刻意**让档位不进提示词正文，从而**无需**改动既有指纹构造（见 §3.3） |
| **开关注册表唯一事实来源** | plan-63 用 config 键（非布尔开关，不属注册表语义）；plan-64 用既有 `enabled_llm` 归属（LLM 模块启停的既有归属文件）；**均不新增渠道层清单** |
| **凭据不落日志与产物** | plan-65 的 `preferred/exclude` 只涉及**源名**（非凭据值），未就绪源仍走既有凭据就绪预检 |
| **重试唯一原语** | 三项均不新增重试循环（plan-64 的自检调用复用既有 LLM 重试策略） |
| **日志统一** | 新增诊断一律 `logging.getLogger("invest")`，无 `print()` |
| 语义命名纪律 | 新增标识符全部语义命名（`depth_profile` / `self_review` / `chain_overrides` 等），**零任务代号**；登记入「功能语义命名表」 |
| 测试有效性纪律 | 每个缺口配回归用例；含「缺省零影响」与「降级矩阵」边界；不使用自证断言 |

---

## 7. 测试策略

| 计划项 | 必测点（均为可失败的具断言用例） |
|---|---|
| plan-63 | 档位表解析（三值 + 非法值回落）；`standard` 与原行为同值（回归锁）；`brief` 收窄模块集合且**不放大**用户关闭项；`effective_news_limit` 三档取值；非默认档位自述行出现、`standard` 零噪声 |
| plan-64 | 开关关闭零调用（**不产生任何 LLM 调用**，以 mock 调用计数断言）；开启后调用一次且输入含各模块产出摘要；产出变化 → 指纹变化（内容寻址）；上游全失败 → 跳过并登记原因；自检失败 → 主内容不受影响；输出含固定尾注（非质量保证）且不含买卖建议；注册项不出现在 `_MODULE_FNS`（防注册漂移断言） |
| plan-65 | 覆盖生效（preferred 前置 / exclude 过滤）；嵌套与恢复；非法源名忽略（库层）/ CLI 报错退出；与 config 级优先关系；exclude 全排除 → None + 警告；熔断源不被覆盖绕过；CLI 参数解析与透传 |

## 8. 风险与红线

1. **plan-63 的档位与开关语义混淆风险**：文档须明确「档位是收窄上界，不替代 `enabled_llm` 开关」；`brief` 下若交集为空，报告以占位呈现属**预期行为**，须在 `how-to-config.md` 写明。
2. **plan-64 的成本与虚假信心风险**：默认关、单次调用、固定尾注「辅助信号、不构成质量保证」；**不得**在 UI/文档中出现「已校验」「已确认无误」类措辞。
3. **plan-65 的全局作用域副作用**：进程级覆盖在长驻进程（Web 模式）下必须**随请求退出恢复**（上下文管理器保证）；须有 fixture 隔离与「退出即恢复」用例。
4. **共同的缺省零影响红线**：三项在缺省配置下，模块集合、提示词正文、缓存键、取数链顺序**逐字节不变**（各有专项用例锁定）。
