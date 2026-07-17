# 多 LLM Provider 链式服务 — 迭代计划

> 文档版本：v4.2
> 状态：待实现
> 关联设计：[llm-multi-provider-design.md](llm-multi-provider-design.md)
> 目标版本：v0.7.0

---

## 1. 概述

为 LLM 服务层增加多 Provider 链式支持。12 轮迭代，分 5 阶段推进。

### 1.1 阶段总览

| 阶段 | 轮次 | 内容 | 风险 |
|:-----|:-----|:------|:-----|
| **Phase 0 — 数据模型** | R1-R2 | `llm_providers.json` 格式解析 + `get_llm_config()` 扩展 | **低** |
| **Phase 1 — 策略引擎** | R3-R5 | strategy.py 框架 + priority + proxy_preferred + weighted | **低** |
| **Phase 2 — Provider Chain** | R6-R8 | call_llm() 链重构 + 异常处理 + 失败追踪 | **中** |
| **Phase 3 — 高级特性** | R9-R10 | cost_first + 每模块路由 | **低** |
| **Phase 4 — 集成与交付** | R11-R12 | 缓存适配 + 配置清理 + 文档 + 全量回归 | **低** |

### 1.2 核心原则

- **抛弃历史负担**：不再兼容旧 `llm_key.json`，`config.json` 中移除 `llm_key_file`
- **测试随代码提交**：每轮新增测试 ≤ 10 个，runtime 增量 ≤ 3s
- **P0 门禁**：每轮提交前 `regression` 模式全绿
- **新增 marker**：`unit_config`（配置解析）/ `unit_llm`（策略+API），边缘场景在 `*_edge.py`
- **约束遵从**：C11（标记强制）/ C12（edge 隔离）/ C13（路径隔离）/ C17（chain 必经）/ C18（配置分离）
- **C8 日志遵从**：所有 WARNING 级别日志必须使用 `logging.getLogger("invest").warning(...)`，禁止 `print()` 或裸 `logging.warning()`

### 1.3 版本演变

| 版本 | 轮次 | 关键变更 |
|:-----|:-----|:---------|
| v3.0 | 10 轮 | 初始 4 阶段设计，部分轮次测试过载 |
| v4.0 | 12 轮 | 拆分担风险，proxy_preferred 独立，每轮测试 ≤10 |
| **v4.1** | **12 轮** | **约束合规补全（C8/C16）、R6 测试增强 6→8、R12 测试增强 3→4、get_llm_key_path() 移除决策** |
| **v4.2** | **12 轮** | **缓存 key 时序矛盾解决（call_llm() 返回 provider_name）、R1 _PATH_KEYS 同步清理、R2 用词修正、proxy_preferred × module preferred 优先级定义** |

---

## 2. 12 轮迭代详情

---

### R1：llm_providers.json 解析 + 校验

**目标**：定义格式，实现解析与校验函数。

#### 设计要点

- `config/_core.py` 新增 `_load_llm_providers()`、`_parse_providers_list()`、`_validate_provider_entry()`
- 文件不存在 → 返回 None（LLM 不可用）
- 格式错误/空数组 → WARNING + 返回 None
- 必填字段缺失/类型非法 → WARNING + 跳过该 entry
- **C8 遵守**：所有 WARNING 使用 `logging.getLogger("invest").warning("...")`
- `_config_defaults.py` 移除 `llm_key_file` 默认值，同时从 `_PATH_KEYS` 中移除 `"llm_key_file"`
- `config.json` 不再包含 `llm_key_file`

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/config/_core.py` | **修改** — 新增 3 个函数 |
| `src/python/config/_config_defaults.py` | **修改** — 移除 `llm_key_file` |
| `src/python/config/_comments.py` | **修改** — 更新默认配置注释 |
| `data/config/llm_providers.json` | **新建** |

#### 测试：`test_config_llm_multi.py` + `test_config_llm_multi_edge.py`

| 测试 | 标记 |
|:-----|:------|
| `test_standard_format` — 标准格式解析 | `unit_config` |
| `test_single_provider` — 单条 provider | `unit_config` |
| `test_multiple_providers` — 多条 provider | `unit_config` |
| `test_file_not_found` — 文件不存在返回 None | `unit_config` |
| `test_empty_providers_array` — 空数组返回 None + WARNING | `unit_config` |
| `test_missing_required_field` — 缺必填字段 WARNING | `unit_config` |
| `test_duplicate_name` — 同名 WARNING | `unit_config` |
| `test_invalid_provider_type` — 非法类型 WARNING + 跳过 | `unit_config_edge` |
| `test_malformed_json` — JSON 解析异常 | `unit_config_edge` |
| `test_defaults_applied` — 缺省字段用默认值补齐 | `unit_config` |

**新增用例数**：10（8 normal + 2 edge）
**预计耗时**：< 1s

#### 风险分析

纯数据层，无行为变更，风险极低。唯一的文件 IO 是 `_load_llm_providers()` 读取 JSON，异常由调用方处理。

#### 验收标准

- [ ] 标准格式正确解析
- [ ] 文件不存在 / 空数组 / 格式异常 → 返回 None（不抛异常）
- [ ] 必填字段缺失 / 非法类型 / 同名 → WARNING（不阻塞）
- [ ] 缺省字段用默认值补齐
- [ ] `regression` 全绿

---

### R2：get_llm_config() 扩展

**目标**：`get_llm_config()` 返回 `_provider_list`、`_strategy`、`_preferred_providers`。

#### 设计要点

- `get_llm_config()` merged 阶段调用 `_load_llm_providers()` + `_parse_providers_list()`
- 注入 merged dict：`_provider_list` / `_strategy` / `_preferred_providers`
- 策略值在 `{"priority","weighted","cost_first","fallback_only"}` 中校验，非法回退 priority + WARNING
- `preferred_providers` 中不存在的 provider name → WARNING + 忽略
- C18 约束：provider 配置只从 `llm_providers.json` 加载，不混入 `config.json`

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/config/_core.py` | **修改** — `get_llm_config()` 注入逻辑 + 校验 |

#### 测试

| 测试 | 标记 |
|:-----|:------|
| `test_has_provider_list` — merged dict 含 `_provider_list` | `unit_config` |
| `test_strategy_default_priority` — 默认 `"priority"` | `unit_config` |
| `test_strategy_invalid_fallback` — 非法策略值回退 + WARNING | `unit_config` |
| `test_preferred_default_empty` — 默认 `{}` | `unit_config` |
| `test_preferred_invalid_name` — 不存在的偏好 WARNING | `unit_config` |
| `test_first_provider_reference` — 原有字段保留为第一条引用 | `unit_config` |

**新增**：6
**预计耗时**：< 1s

#### 风险分析

在已有 `get_llm_config()` 中追加注入逻辑。不存在覆盖风险——仅新增 dict key，不会影响既有调用方（它们只读自己关心的字段）。

#### 验收标准

- [ ] `get_llm_config().get("_provider_list")` 返回正确列表
- [ ] `_strategy` 默认 `"priority"`
- [ ] 非法策略值回退 + WARNING
- [ ] 原有 `provider`/`api_key`/`model`/`endpoint` 保留
- [ ] 6 项测试全绿 + regression 全绿

---

### R3：strategy.py 框架 + Priority 策略

**目标**：新建 `strategy.py`，实现 `resolve_provider_chain()` 框架及 priority 排序。

#### 设计要点

```python
def resolve_provider_chain(
    provider_list: list[dict],
    strategy: str,
    module_key: str = "",
    preferred: dict[str, str] | None = None,
) -> list[dict]:
    """返回按策略排序的 provider 尝试列表。"""
```

- priority：`sorted(provider_list, key=lambda p: p["priority"])`
- 同 priority 保持原序（稳定排序）
- 模块偏好注入：匹配的 provider 移至首位
- fallback_only 共享 priority 的实现（语义差异在文档层）
- 空列表 → `[]`，preferred name 不存在 → WARNING + 忽略（C8：`logging.getLogger("invest").warning()`）
- 未知策略名称 → WARNING + 回退 priority

**不包含**：proxy_preferred（下一轮）、weighted（R5）、cost_first（R9）。

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **新建** — resolve_provider_chain + priority |
| `src/python/llm/__init__.py` | **修改** — 导出 strategy |

#### 测试：`test_strategy.py`

| # | 测试 | 说明 |
|---|:-----|:------|
| 1 | `test_priority_sort` | priority 1/2/3 升序 |
| 2 | `test_priority_tie` | 同 priority 保持原序 |
| 3 | `test_preferred_first` | 偏好 provider 在首位 |
| 4 | `test_preferred_not_in_list` | 不存在时 WARNING |
| 5 | `test_empty_list` | 返回 `[]` |
| 6 | `test_single_provider` | 单元素返回 |
| 7 | `test_fallback_only_same` | fallback_only 同 priority |
| 8 | `test_unknown_strategy` | 未知策略回退 priority |

**新增**：8（`unit_llm`）
**预计耗时**：< 1s

#### 风险分析

纯逻辑模块，无外部依赖。策略排序的入参和预期清晰可测。`preferred` 参数在本轮引入但尚未有调用方传入非空值——接口先行，后续 R10 才端到端启用。

#### 验收标准

- [ ] priority 升序 + 稳定排序
- [ ] 偏好 name 存在时移至首位，不存在时 WARNING
- [ ] fallback_only 返回同 priority
- [ ] 未知策略回退 priority + WARNING
- [ ] 空列表返回 `[]`
- [ ] 8 项测试全绿 + regression 全绿

---

### R4：proxy_preferred 代理偏好

**目标**：实现代理检测 + 后置注入，有代理时将标记 provider 排到链首。

#### 设计要点

- `resolve_provider_chain()` 末尾新增 `_apply_proxy_preferred()` 后置步骤
- 新增 `_detect_proxy()`：检查环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `http_proxy` / `https_proxy` / `ALL_PROXY`
- **有代理**：`proxy_preferred: true` 的 provider 无条件排首（它们之间仍按 strategy 排序）
- **无代理**：完全无效果，行为零变化
- `llm_providers.json` provider entry 新增可选字段 `proxy_preferred: bool`

```python
def _detect_proxy() -> bool:
    """检测系统代理环境变量，任一非空即返回 True。"""
    return any(os.environ.get(v, "") for v in
               ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"])

def _apply_proxy_preferred(chain: list[dict]) -> list[dict]:
    if not _detect_proxy():
        return chain
    preferred = [p for p in chain if p.get("proxy_preferred")]
    others = [p for p in chain if not p.get("proxy_preferred")]
    return preferred + others
```

**与各策略的关系**：后置注入，不入侵任何策略排序逻辑。

```
resolve_provider_chain()
├── step 1: strategy 排序（priority / weighted / cost_first）
├── step 2: preferred_providers 模块偏好注入
└── step 3: _apply_proxy_preferred()    ← 本轮新增
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **修改** — 新增 `_detect_proxy()` + `_apply_proxy_preferred()` |

#### 测试：`test_strategy.py`（追加）

| # | 测试 | 说明 | 类型 |
|---|:-----|:------|:-----|
| 1 | `test_proxy_preferred_detected` | mock HTTP_PROXY 非空，标记 provider 排首位 | normal |
| 2 | `test_proxy_no_proxy_no_effect` | 未设代理变量，标记无效 | normal |
| 3 | `test_proxy_preferred_multiple` | 多条标记排首位，按 priority 排序 | normal |

**新增**：3（`unit_llm`）
**预计耗时**：< 0.5s

#### 风险分析

`_detect_proxy()` 依赖 `os.environ`，测试通过 mock 隔离。无代理机器上无行为变化——风险极低。proxy_preferred 字段不在 provider entry 的必填校验中，旧配置无此字段仍可正常工作。

#### 验收标准

- [ ] 有代理 + proxy_preferred 标记 → 标记 provider 排首位
- [ ] 无代理 + proxy_preferred 标记 → 原序不变
- [ ] 有代理 + 多条标记 → 全部排首，相互按 strategy 排序
- [ ] 有代理 + 无标记 → 行为不变
- [ ] 3 项测试全绿 + regression 全绿

---

### R5：Weighted 策略

**目标**：`resolve_provider_chain()` 支持 `strategy="weighted"`。

#### 设计要点

- `random.choices(providers, weights=[p["weight"]], k=len(providers))` + 去重
- 权重 0 不参与选择
- 所有 provider 权重全为 0 → WARNING + 回退 priority
- 失败后排除当前 provider 从剩余中重选

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **修改** — weighted 分支 |

#### 测试：`test_strategy.py`（追加）

| # | 测试 | 说明 |
|---|:-----|:------|
| 1 | `test_weighted_distribution` | 高权重概率更高（seed 确定） |
| 2 | `test_weighted_zero_excluded` | 权重 0 不出现 |
| 3 | `test_weighted_all_zero_fallback` | 全 0 回退 priority + WARNING |
| 4 | `test_weighted_removes_failed` | 失败后排除 |
| 5 | `test_weighted_single` | 单条直接返回 |

**新增**：5（`unit_llm`）
**预计耗时**：< 1s

#### 风险分析

随机性使测试 flaky。缓解：固定 `random.seed()` 确定性验证排列集合，不验证排列顺序。纯逻辑模块，无外部依赖。

#### 验收标准

- [ ] 权重与出现频率正相关（固定 seed 确定性验证）
- [ ] 权重 0 不参与选择
- [ ] 全 0 回退 priority + WARNING
- [ ] 失败排除正确
- [ ] 5 项测试全绿 + regression 全绿

---

### R6：call_llm() Provider Chain 基础集成

**目标**：`call_llm()` 重构为 chain 循环，覆盖正常场景，移除旧 fallback 逻辑。

#### 设计要点

- 保留 `call_llm()` 函数签名兼容性，**返回值从 `(result, usage)` 扩展为 `(result, usage, provider_name)`**
- 成功时 `provider_name` = 被选中 provider 的 `name` 字段；全部失败时 `provider_name = None`
- 新增 `_call_provider_entry()`：从 entry dict 提取参数，委托给 `call_single_provider()`
- 新增 `_infer_module_key(config_field)`：`"max_tokens_global_macro"` → `"global_macro"`
- 移除 `fallback_provider` / `fallback_api_key` / `fallback_endpoint` / `fallback_model`
- timeout 从 entry 传入，覆盖默认值
- **本轮只覆盖正常/first_success/失败回退场景**，异常处理（空内容安抚、熔断跳过等）归 R7

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/api.py` | **修改** — chain 循环 + `_call_provider_entry()` + `_infer_module_key()` |

#### 测试：`test_api_multi.py`

| # | 测试 | 说明 |
|---|:-----|:------|
| 1 | `test_chain_first_success` | 首 provider 成功，返回正确 `provider_name` |
| 2 | `test_chain_first_fails_second_succeeds` | 首失败 → 回退 → 次成功，返回次 provider 名 |
| 3 | `test_chain_all_fail` | 全部失败 → `(None, None, None)` |
| 4 | `test_chain_empty_list` | 空列表直接返回 `(None, None, None)` |
| 5 | `test_chain_single_fails` | 单条失败 → `(None, None, None)` |
| 6 | `test_chain_timeout_override` | timeout 从 entry 生效 |
| 7 | `test_chain_calls_resolve_chain` | 验证 `call_llm()` 确实调用了 `resolve_provider_chain()` |
| 8 | `test_chain_respects_strategy_order` | chain 循环严格按照 strategy 输出的顺序尝试 |

**新增**：8（`unit_llm`）
**预计耗时**：< 1.5s
**回归**：确保 480+ 项既有 `unit_llm` 测试不受影响

#### 风险分析

| 风险 | 影响 | 概率 | 缓解 |
|:-----|:------|:----|:------|
| `call_llm()` 重构导致全部 LLM 功能失效 | 高 | 低 | 6 项全 mock 测试 + 480 回归 |
| 旧 fallback 字段移除后外部调用方编译错误 | 中 | 低 | 确保 `fallback_provider` 等不再被任何模块引用 |
| `_infer_module_key()` 正则匹配遗漏 | 低 | 中 | 测试覆盖已知 config_field |

#### 验收标准

- [ ] chain 按序尝试，成功即返回
- [ ] 全部失败 → `(None, None)`
- [ ] 空列表 → `(None, None)`
- [ ] 成功时返回 `(result, usage, provider_name)`，`provider_name` 为被选中 entry 的 name
- [ ] 全部失败时返回 `(None, None, None)`
- [ ] timeout 从 entry 传入生效
- [ ] chain 严格按照 `resolve_provider_chain()` 的输出顺序尝试
- [ ] 旧 fallback 字段从 `call_llm()` 签名和实现中移除
- [ ] `_infer_module_key()` 正确推导已知模块键
- [ ] 8 项新测试 + 480 项既有全绿 + regression 全绿

---

### R7：异常链处理 + 安抚重试

**目标**：覆盖 chain 中的异常场景：空内容安抚重试、熔断跳过、旧字段残余检测。

#### 设计要点

- 空内容重试：`_call_provider_entry()` 内对空响应做安抚重试（限制在单个 provider 内，不触发 chain 切换）
- 熔断兼容：chain 循环中 `call_single_provider()` 抛 `CircuitBreakerOpen` 异常 → 捕获后切下一 entry
- 旧字段残余检测：验证移除的 `fallback_*` 字段在 `call_llm()` 中已无引用
- chain 循环异常安全：单个 provider 抛异常不中断整个 chain

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/api.py` | **修改** — 异常回退 + 空安抚 |

#### 测试：`test_api_multi.py`（追加）

| # | 测试 | 说明 | 类型 |
|---|:-----|:------|:-----|
| 1 | `test_chain_empty_content_retry` | 空内容安抚重试后成功 | normal |
| 2 | `test_chain_retry_exhausted_fallback` | 空内容安抚耗尽 → 回退下一 provider | normal |
| 3 | `test_chain_retry_then_fallback` | 安抚+回退组合 | normal |
| 4 | `test_chain_no_fallback_fields` | 旧 fallback 字段在 call_llm 中无效 | edge |

**新增**：4（3 normal + 1 edge，`unit_llm`）
**预计耗时**：< 1.5s

#### 风险分析

安抚重试在 `_call_provider_entry()` 内部进行，与 chain 循环解耦——不影响 chain 的主循环正确性。熔断异常捕获使用 `except Exception` 不会漏接。

#### 验收标准

- [ ] 空内容安抚重试在当前 provider 内完成，不跨 provider
- [ ] 安抚耗尽后正确回退下一 provider
- [ ] 旧 fallback 字段在 `call_llm()` 中已无引用
- [ ] 4 项测试全绿 + regression 全绿

---

### R8：失败追踪细化

**目标**：失败原因记录带上 provider name，`_LLM_MODULE_FAILURE` 扩展为 dict。

#### 设计要点

- `api_base.py` 中失败原因前缀加 `"{provider_name}: "`
- `_LLM_MODULE_FAILURE[module_key]` 扩展为 dict：

```python
_LLM_MODULE_FAILURE[module_key] = {
    "attempted": ["gemini-pro: TIMEOUT", "deepseek-v4: SUCCESS"],
    "final_status": "success",
}
```

- 兼容读取：消费者检测到旧字符串格式时自动兼容

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/api_base.py` | **修改** — 失败原因前缀 |
| `src/python/llm/api.py` | **修改** — chain 循环记录所有尝试 |

#### 测试

| # | 测试 | 说明 | 类型 |
|---|:-----|:------|:-----|
| 1 | `test_failure_has_provider_name` | 失败原因含 provider name | normal |
| 2 | `test_chain_all_fail_records_all` | 全部失败时记录所有尝试 | normal |
| 3 | `test_failure_tracking_legacy_format` | 旧字符串格式读取兼容 | edge |

**新增**：3（2 normal + 1 edge，`unit_llm`）
**预计耗时**：< 0.5s

#### 风险分析

仅改日志/错误追踪结构，不影响调用逻辑。dict → str 读取兼容对既有消费者透明。

#### 验收标准

- [ ] 失败原因含 provider name
- [ ] `_LLM_MODULE_FAILURE` 记录所有尝试 provider + 最终状态
- [ ] 旧字符串格式可被消费者正常读取
- [ ] 3 项测试全绿 + regression 全绿

---

### R9：Cost First 策略

**目标**：`resolve_provider_chain()` 支持 `strategy="cost_first"`。

#### 设计要点

- 按 `input_price + output_price` 升序
- 未知模型排末尾（`cost_score = float("inf")`）
- 首次调用主动触发 `reload_pricing()` 确保定价表就绪
- fallback_only 共享 priority 实现（已在 R3 完成，本轮仅验证）

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **修改** — cost_first 分支 |

#### 测试：`test_strategy.py`（追加）

| # | 测试 | 说明 |
|---|:-----|:------|
| 1 | `test_cost_first_cheapest_first` | 按定价升序 |
| 2 | `test_cost_first_unknown_last` | 未知模型排末尾 |
| 3 | `test_cost_first_all_unknown` | 全部未知按原序 |
| 4 | `test_cost_first_triggers_pricing` | 主动触发 reload_pricing |
| 5 | `test_fallback_only_behavior` | 集成验证 fallback_only |

**新增**：5（`unit_llm`）
**预计耗时**：< 1s

#### 风险分析

依赖 `pricing.py` 的 `PRICING_MERGED` 定价表。pricing 表为空时所有模型 cost = inf，回退到原序——不抛异常。测试需 mock 定价返回值，不依赖实时定价数据。

#### 验收标准

- [ ] cost_first 按 `input_price + output_price` 升序
- [ ] 未知模型排在已知模型之后
- [ ] 全部未知时保持原序（不抛异常）
- [ ] `reload_pricing()` 被触发
- [ ] 5 项测试全绿 + regression 全绿

---

### R10：每模块 Provider 路由

**目标**：`preferred_providers` 端到端生效——配置 → `get_llm_config()` → `resolve_provider_chain()` → `call_llm()`。

#### 设计要点

- R3 中 `resolve_provider_chain()` 已接收 `preferred` 参数
- R6 中 `_infer_module_key()` 已实现
- R2 中 `_preferred_providers` 已注入 merged dict
- **本轮只做端到端链路验证**，不新增核心逻辑

数据流：
```
llm_providers.json
  → preferred_providers: {"global_macro": "gemini-pro"}
  → get_llm_config() → {..., "_preferred_providers": {...}}
  → call_llm() → _infer_module_key(config_field) → "global_macro"
  → resolve_provider_chain(..., module_key="global_macro", preferred={...})
  → "gemini-pro" 排首位
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/api.py` | **修改** — 传递 module_key + preferred 到 resolve_provider_chain |

#### 测试

| # | 测试 | 位置 |
|---|:-----|:------|
| 1 | `test_module_preferred_full_chain` — 配置→chain 完整链路 | `test_api_multi.py` |
| 2 | `test_module_different_preferences` — 不同模块不同偏好 | `test_api_multi.py` |
| 3 | `test_no_preferred_uses_global` — 无偏好用全局策略 | `test_strategy.py` |
| 4-6 | `test_module_key_extraction` — config_field 推导 x 3 场景 | `test_strategy.py` |

**新增**：6（`unit_llm`）
**预计耗时**：< 1s

#### 风险分析

所有核心逻辑已在前面 R2/R3/R6 中实现并单独测试。本轮仅组装已测组件，风险低。

#### 验收标准

- [ ] 偏好 provider 在对应模块 chain 中排首位
- [ ] 不同模块可指定不同偏好
- [ ] 偏好失败后正常回退下一 provider
- [ ] 不存在的偏好 WARNING + 忽略
- [ ] 无偏好模块用全局策略
- [ ] 6 项测试全绿 + regression 全绿

---

### R11：缓存适配

**目标**：缓存 key 包含 provider name，骨架层适配 `call_llm()` 返回的 `provider_name` 驱动缓存落盘。

#### 设计要点

- 缓存 key 格式：`llm_{module_key}_{provider_name}_{fingerprint}`（cache API 内部处理扩展名）
- `skeleton.py` 缓存流程改为**先解析链 → 乐观预检 → 调用 → 按实际 provider 落盘**：

```
skeleton.py 缓存流程
┌────────────────────────────────────┐
│ resolve_provider_chain(llm_config) │  ← 复用 strategy 引擎
│ → 获取有序 provider 列表 (chain)   │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│ 乐观预检：chain[0] 的 name         │
│ cache_key = "{module}_{chain[0]    │
│              name}_{fingerprint}"  │
│ cache.get(cache_key, ttl)         │
│ 命中 → 直接返回 cached result     │
└──────────────┬─────────────────────┘
               ▼ 未命中
┌────────────────────────────────────┐
│ call_llm(...)                      │
│ → 返回 (result, usage,            │
│          selected_provider)        │
└──────────────┬─────────────────────┘
               ▼ success
┌────────────────────────────────────┐
│ cache_key = "{module}_{selected_   │
│              provider}_{fingerprint}"│
│ cache.set(cache_key, result)       │
└────────────────────────────────────┘
```

- **乐观预检只查 chain 首位**，不遍历全链（避免频繁 cache.get 开销）
- 缓存 key 不带 `.json` 后缀——cache API 内部处理扩展名和 gzip
- C3 原子写入：`cache.set()` 内部保持 `tempfile.mkstemp` + `os.replace` 不变

#### 关键假设

- `call_llm()` 在 R6 已改为返回 `(result, usage, provider_name)`，全部失败时 `provider_name = None`
- `resolve_provider_chain()` 在 R3 已暴露为公开函数，skeleton 可调用
- 首位 provider 稳定时（成功率 >99%），乐观预检命中率接近 100%

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/skeleton.py` | **修改** — 缓存 key 构建 + 链解析 + 乐观预检 |

#### 测试：`test_cache_multi.py`

| # | 测试 | 说明 |
|---|:-----|:------|
| 1 | `test_cache_key_includes_provider` | key 含 provider name |
| 2 | `test_cache_key_diff_providers_diff_keys` | 不同 provider → 不同 key |
| 3 | `test_cache_key_same_provider_same_key` | 同 provider → 相同 key（同 fingerprint） |
| 4 | `test_cache_optimistic_precheck_hit` | 乐观预检命中 → 不调用 call_llm |
| 5 | `test_cache_set_after_call` | call_llm 成功后按实际 provider 落盘 |

**新增**：5（`unit_llm`）
**预计耗时**：< 1.5s

#### 风险分析

| 风险 | 影响 | 概率 | 缓解 |
|:-----|:------|:----|:------|
| 预检 key 与落盘 key 因 provider 切换不一致 | 低 | 低 | 预检只是优化，miss 后走完整流程 |
| `resolve_provider_chain()` 在 skeleton 中重复解析 | 低 | 确定 | 无锁只读操作，开销可忽略 |
| 缓存 key 变更使所有现有 LLM 缓存失效一次 | 中 | 确定 | 一次性影响，TTL 内重建 |

#### 验收标准

- [ ] 缓存 key 格式：`llm_{module}_{provider}_{fingerprint}`
- [ ] 不同 provider → 不同缓存 key
- [ ] 乐观预检：chain[0] 有缓存 → 跳过 call_llm
- [ ] 落盘：call_llm 成功后按返回的 provider_name 写入缓存
- [ ] 5 项测试全绿 + regression 全绿

---

### R12：TUI + 配置清理 + 集成验证 + 文档 + 全量回归

**目标**：配置彻底清理、TUI 只读查看、集成端到端验证、文档同步、全量回归通过。

#### 设计要点

- **config 清理**：`_config_defaults.py` 验证 `llm_key_file` 已移除（R1 已完成），`_comments.py` 更新模板注释
- **`get_llm_key_path()` 移除**：从 `config/_core.py` 中移除该函数定义，`config/__init__.py` 移除导出；更新 `test_config_atomic_edge.py`、`test_log_sanitize.py` 中的 mock 引用
- **TUI 极简**：`handlers_config.py` 新增 `_cmd_config_llm_providers()`，菜单快捷键 `P`，只读显示当前 provider 列表
- **集成验证**：使用所有 4 种策略配置（priority/weighted/cost_first/fallback_only）验证端到端 chain 行为（全 mock，走完整 resolve → call → cache 流程）
- **文档**：
  - `how-to-config-llm.md` — 重写为 `llm_providers.json` 配置指南
  - `how-to-config.md` — 移除 `llm_key_file` 相关说明
  - `technical.md` — 追加 C17/C18；**C16 路径键列表移除 `llm_key_file`**
  - `changelog.md` / `test-coverage.md` / `plan.md` — 同步
- **R1-R12 全量回归**：依次执行 `regression` → `verify` → `all`

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/config/_core.py` | **修改** — 移除 `get_llm_key_path()` 函数定义 |
| `src/python/config/__init__.py` | **修改** — 移除 `get_llm_key_path` 导出 |
| `src/python/config/_config_defaults.py` | **验证** — R1 已移除 `llm_key_file`/`_PATH_KEYS`，确认无残留 |
| `src/python/config/_comments.py` | **修改** — 更新模板注释 |
| `src/python/handlers_config.py` | **修改** — provider 列表查看 |
| `src/python/tui_menu.py` | **修改** — 注册 P 快捷键 |
| `docs-stm/manuals/how-to-config-llm.md` | **重写** |
| `docs-stm/manuals/how-to-config.md` | **修改** |
| `docs-stm/managements/technical.md` | **修改** — 追加 C17/C18；C16 路径键列表移除 `llm_key_file` |
| `docs-stm/managements/changelog.md` | **修改** |
| `docs-stm/managements/test-coverage.md` | **修改** |
| `docs-stm/managements/plan.md` | **修改** — P1-T01 完成 |

#### 测试

| # | 测试 | 标记 |
|---|:-----|:------|
| 1 | `test_config_no_llm_key_file` — 配置无 `llm_key_file` 正常 | `unit_config` |
| 2 | `test_tui_menu_has_provider` — TUI 菜单注册 P | `unit_ui` |
| 3 | `test_integration_chain_all_strategies` — 所有策略走一遍端到端 chain | `unit_llm` |
| 4 | `test_config_sanity_after_cleanup` — 清理后 `get_config()` 无 `llm_key_file` 键 | `unit_config` |

**新增**：4
**预计耗时**：< 3s（集成 mock）

#### 回归验证

| 门禁 | 命令 | 预期 |
|:-----|:------|:------|
| P0 | `regression` | 全绿 |
| P1 | `verify` | 全绿 |
| P2 | `all` | 全绿 |

#### 验收标准

- [ ] `get_config()` 无 `llm_key_file` 键
- [ ] `get_llm_key_path()` 从 `config/__init__.py` 导出中移除，测试 mock 已更新
- [ ] TUI 菜单 P 显示 provider 列表（只读）
- [ ] 端到端集成测试覆盖全部策略 chain 行为
- [ ] C16 中 `llm_key_file` 路径键已移除
- [ ] 文档覆盖：配置指南 + technical.md C17/C18 + C16 清理 + changelog
- [ ] regression + verify + all 三级门禁全绿

---

## 3. 整体验收标准

- [ ] 全部 12 轮通过 P0 门禁
- [ ] P1 `verify` 全绿
- [ ] P2 `all` 全绿
- [ ] 新增测试 ≤ 67 项，runtime 增量 ≤ 15s
- [ ] C8 日志统一遵守（所有 WARNING 使用 `logging.getLogger("invest")`）
- [ ] C16 中 `llm_key_file` 路径键已移除
- [ ] 无旧配置兼容代码遗留
- [ ] C17（Provider Chain 必经）/ C18（配置分离）通过 code review
- [ ] 文档通过 review

---

## 4. 风险总览

| 风险 | 影响 | 概率 | 涉及轮次 | 缓解 |
|:-----|:------|:----|:---------|:------|
| call_llm() 重构导致 LLM 全部失效 | 高 | 低 | R6-R7 | 拆分基础/异常两轮，全 mock 11 场景 + 480 回归 |
| 缓存 key 变更缓存失效 | 中 | 确定 | R11 | 一次性影响，TTL 内重建 |
| cost_first 依赖 pricing 惰性加载 | 低 | 低 | R9 | 主动触发 reload_pricing() |
| weighted 随机性使测试 flaky | 低 | 中 | R5 | 固定 seed 确定性验证 |
| proxy_preferred 环境变量污染 | 低 | 低 | R4 | mock 隔离，无代理机器零影响 |
| 缓存 key 预检 vs 落盘 provider 不一致 | 低 | 低 | R11 | 乐观预检只是优化，miss 后走完整流程 |
| get_llm_key_path() 移除影响外部测试 | 中 | 中 | R12 | 提前识别所有 mock 引用，R12 逐一更新 |
| C16 llm_key_file 移除后路径绝对化遗漏 | 低 | 低 | R12 | `_PATH_KEYS` 显式移除 |
| R12 多文件变更回归 | 中 | 低 | R12 | 三级门禁验证 |
