# 多 LLM Provider 链式服务 — 技术设计

> 文档版本：v4.2
> 状态：已完成（v0.7.0-dev Phase 0 R1 已实现）
> 关联计划：[llm-multi-provider-iteration-plan.md](llm-multi-provider-iteration-plan.md)

---

## 目录

- [1. 背景与目标](#1-背景与目标)
- [2. 数据模型](#2-数据模型)
  - [2.1 llm_providers.json 格式](#21-llm_providersjson-格式)
  - [2.2 Provider 配置模型](#22-provider-配置模型)
- [3. 架构变更](#3-架构变更)
  - [3.1 总体数据流](#31-总体数据流)
  - [3.2 config/_core.py 变更](#32-config_corepy-变更)
  - [3.3 llm/api.py 变更 — Provider Chain](#33-llm-apipy-变更--provider-chain)
  - [3.4 llm/strategy.py — 策略引擎](#34-llmstrategypy--策略引擎)
  - [3.5 失败原因追踪扩展](#35-失败原因追踪扩展)
- [4. 各策略行为详解](#4-各策略行为详解)
  - [4.1 priority（优先级顺序）](#41-priority优先级顺序)
  - [4.2 weighted（加权随机）](#42-weighted加权随机)
  - [4.3 cost_first（成本优先）](#43-cost_first成本优先)
  - [4.4 fallback_only（仅回退）](#44-fallback_only仅回退)
  - [4.5 proxy_preferred（代理偏好）](#45-proxy_preferred代理偏好)
- [5. 每模块 Provider 路由](#5-每模块-provider-路由)
- [6. 缓存兼容性](#6-缓存兼容性)
- [7. 熔断器适配](#7-熔断器适配)
- [8. 涉及文件清单](#8-涉及文件清单)
- [9. 架构设计约束](#9-架构设计约束)
- [10. 风险与缓解](#10-风险与缓解)

---

## 1. 背景与目标

### 1.1 现状

当前 LLM 服务仅支持单一 provider 配置（`llm_settings.json` 中的 `provider` / `api_key` / `model` / `endpoint`），通过 `fallback_provider` 字段做一层简单回退。

**核心痛点**：
- 只能配置一个主 provider + 至多一个回退
- 回退无法链式多级（A→B→C）
- 无法按成本/权重灵活分发请求
- 单点故障：主 provider 不可用时整个 LLM 功能降级

### 1.2 目标

- 支持**多个 LLM Provider** 同时配置（`llm_providers.json` 中声明）
- 支持**优先级回退**（首选 → 次选 → 三选…链式尝试）
- 支持**加权随机分发**（按权重比例分配请求）
- 支持**成本优先路由**（自动选最便宜的模型）
- 支持**每模块指定偏好 provider**
- 支持**代理环境自动切换**（有代理时优先使用可正常通过代理的 provider）
- **抛弃历史负担**：不再兼容旧 `llm_key.json`，`config.json` 中移除 `llm_key_file`

### 1.3 非目标

- 不实现 provider 健康探活（依赖熔断器被动检测）
- 不实现跨 provider 负载均衡
- 不改变 LLM 缓存接口（仅适配缓存 key 以包含 provider name）
- 不保留旧配置兼容性

### 1.4 与 technical.md 约束的映射

| 约束 | 遵守方式 |
|:-----|:---------|
| **C8** 日志统一 | 所有 WARNING 日志使用 `logging.getLogger("invest").warning()` |
| **C16** 路径绝对化 | 移除 `llm_key_file` 路径键，`llm_providers.json` 使用固定路径（非配置项） |

---

## 2. 数据模型

### 2.1 llm_providers.json 格式

新增 `data/config/llm_providers.json`，替代旧 `llm_key.json` 和 `config.json` 中的 `llm_key_file` 字段。

```json
{
  "version": 1,
  "strategy": "priority",
  "preferred_providers": {
    "global_macro": "gemini-pro",
    "expert_review": "deepseek-v4"
  },
  "providers": [
    {
      "name": "gemini-pro",
      "provider": "gemini",
      "api_key": "AIzaSy...",
      "model": "gemini-2.5-pro",
      "priority": 1,
      "weight": 5,
      "timeout": 120,
      "endpoint": null
    },
    {
      "name": "deepseek-v4",
      "provider": "claude",
      "api_key": "sk-...",
      "model": "deepseek-v4-flash",
      "endpoint": "https://api.deepseek.com/anthropic/v1/messages",
      "priority": 2,
      "weight": 3,
      "timeout": 180
    },
    {
      "name": "openai-fallback",
      "provider": "openai",
      "api_key": "sk-...",
      "model": "gpt-4o-mini",
      "priority": 3,
      "weight": 1
    }
  ]
}
```

| 顶层字段 | 类型 | 必填 | 说明 |
|:---------|:-----|:-----|:------|
| `version` | int | 否（默认 1） | 格式版本号 |
| `strategy` | str | 否（默认 `"priority"`） | 使用策略 |
| `preferred_providers` | dict | 否（默认 `{}`） | 每模块偏好 provider |
| `providers` | array | **是** | provider 配置列表，至少 1 项 |

| provider 字段 | 类型 | 必填 | 说明 |
|:--------------|:-----|:-----|:------|
| `name` | str | **是** | 唯一标识名，同一文件内不可重复 |
| `provider` | str | **是** | `"claude"` / `"openai"` / `"gemini"` |
| `api_key` | str | **是** | API 密钥 |
| `model` | str | **是** | 模型名 |
| `endpoint` | str\|null | 否 | API 端点，null 则使用各 provider 默认端点 |
| `priority` | int | 否（默认 99） | 越小越优先 |
| `weight` | int | 否（默认 1） | 加权策略权重，0=不参与 |
| `timeout` | float | 否（默认 60） | 单次调用超时秒数 |
| `proxy_preferred` | bool | 否（默认 false） | 有代理环境时优先选择此 provider |

**校验规则**：
- `providers` 数组为空 → 记录 WARNING，返回 None
- `name` 重复 → 记录 WARNING，后者覆盖前者
- `provider` 类型不在合法集合 → 记录 WARNING，跳过该 entry
- 必填字段缺失 → 记录 WARNING，跳过该 entry

### 2.2 Provider 配置模型

```python
@dataclass
class LLMProviderEntry:
    """运行时 Provider 配置（由解析函数生成）。"""
    name: str
    provider: str          # "claude" | "openai" | "gemini"
    api_key: str
    model: str
    endpoint: str | None
    priority: int
    weight: int
    timeout: float
    proxy_preferred: bool = False  # 代理环境偏好
```

注：`max_retries` 不做 per-provider 配置，统一使用全局 `max_retries`（`api_base.py` 的 `_get_retry_max()`）。per-provider retry 增加 API 路由层复杂度而收益有限。

---

## 3. 架构变更

### 3.1 总体数据流

```
                            改动前                               改动后
   generators_news/generators                             generators_news/generators
         │ call_llm(system, user, llm_config)                    │ call_llm(system, user, llm_config)
         ▼                                                       ▼
   ┌──────────────────────┐                            ┌──────────────────────────────────────┐
   │  api.py              │                            │  api.py                               │
   │  call_llm()          │                            │  call_llm()                           │
   │                      │                            │    │                                   │
   │  provider +          │                            │    ├─ _select_provider_chain()         │
   │  fallback            │                            │    │   → 按策略排序 provider 列表      │
   │                      │                            │    │                                   │
   │  call_single_provider│                            │    ├─ for entry in chain:              │
   └──────┬───────────────┘                            │    │  call_single_provider(entry)       │
          │                                             │    │    成功 → 返回 (result, usage,     │
          ▼                                             │    │            entry["name"])          │
   ┌──────────────┐                                    │    └─ 失败 → 下一 entry               │
   │  api_base.py │                                    └───────全部失败 → (None, None, None)────┘
   │  (重试/截断)  │                                                    │
   └──────────────┘                                       ┌──────────────┐  │
                                                          │  strategy.py │  │
                                                          │  resolve_    │  │
                                                          │  provider_   │  │
                                                          │  chain()     │  │
                                                          └──────┬───────┘  │
                                                                 │          │
                                                 ┌───────────────┴──────────┘
                                                 ▼
                                           ┌──────────────┐
                                           │  api_base.py  │
                                           │  (不变)       │
                                           └──────────────┘
```

**核心原则**：`call_llm()` 调用方接口**向前兼容**——返回值从 `(result, usage)` 扩展为 `(result, usage, provider_name)`，旧消费者只解包前两个值不受影响。新增的 `provider_name` 供 skeleton 缓存落盘使用。

### 3.2 config/_core.py 变更

**`get_llm_config()` 返回结构扩展**：

```python
{
    ...                              # 原有字段（provider, api_key, model, endpoint — 保留为第一个 provider 的引用）
    "_provider_list": [...],         # LLMProviderEntry 列表
    "_strategy": "priority",         # 使用策略
    "_preferred_providers": {...},   # 每模块偏好
}
```

**新增函数**：

```python
def _load_llm_providers() -> dict | None:
    """读取 data/config/llm_providers.json，不存在返回 None。"""

def _parse_providers_list(raw_config: dict) -> list[dict]:
    """解析 providers 数组，校验+补齐。"""

def _validate_provider_entry(entry: dict, index: int) -> list[str]:
    """校验单个 provider 配置，返回 WARNING 列表，空列表=通过。"""
```

**移除**：
- **`get_llm_key_path()` 彻底移除**：从 `config/_core.py` 删除定义，`config/__init__.py` 删除导出；4 处测试 mock 在 R12 中更新为 `llm_providers.json` 路径或不需 mock
- `_config_defaults.py` 中移除 `llm_key_file` 默认值（`_PATH_KEYS` 同步清理）
- `config.json` 不再包含 `llm_key_file` 字段（C16 路径键列表同步移除）
- 旧 `llm_key.json` 不再被读取

### 3.3 llm/api.py 变更 — Provider Chain

**`call_llm()` 重构**——保留原有函数签名兼容性，返回值从 `(result, usage)` 扩展为 `(result, usage, provider_name)`：

```python
def call_llm(system_prompt, user_prompt, llm_config, ...):
    provider_list = llm_config.get("_provider_list", [])
    strategy = llm_config.get("_strategy", "priority")
    preferred = llm_config.get("_preferred_providers", {})
    module_key = _infer_module_key(config_field)
    chain = resolve_provider_chain(provider_list, strategy, module_key, preferred)

    if not chain:
        return (None, None, None)

    for entry in chain:
        result, usage, _ = _call_provider_entry(entry, ...)
        if result is not None:
            return result, usage, entry["name"]   # ← 返回被选中的 provider name
    return (None, None, None)                      # ← 全部失败时 provider_name=None
```

**`_call_provider_entry()`**——从 entry 提取参数委托给 `call_single_provider()`，内部处理安抚重试。

**`_infer_module_key(config_field)`**——从配置字段名提取模块键。

**移除**：`fallback_provider` / `fallback_api_key` / `fallback_endpoint` / `fallback_model` 相关逻辑。

### 3.4 llm/strategy.py — 策略引擎

**新建独立模块**：

```python
def resolve_provider_chain(
    provider_list: list[dict],
    strategy: str,
    module_key: str = "",
    preferred: dict[str, str] | None = None,
) -> list[dict]:
    """返回按策略排序的 provider 尝试顺序列表。"""
```

各策略行为详见 [§4](#4-各策略行为详解)。

### 3.5 失败原因追踪扩展

`_LLM_MODULE_FAILURE[module_key]` 扩展为 dict 结构：

```python
_LLM_MODULE_FAILURE[module_key] = {
    "primary": "gemini-pro: TIMEOUT",
    "fallback_used": "deepseek-v4: SUCCESS",
}
```

兼容读取：消费者检测到旧字符串格式时自动兼容。

---

## 4. 各策略行为详解

### 4.1 priority（优先级顺序）

**默认策略**。按 `priority` 升序尝试，成功后不再尝试其他。

```
A(pri=1) → 成功 → 返回 ✓
A(pri=1) → 失败 → B(pri=2) → 成功 → 返回 ✓
A → 失败 → B → 失败 → C(pri=3) → ... → 全部失败 → None
```

**触发切换的失败**：网络错误、熔断打开、429/503、认证错误、空内容（安抚后仍空）。

**不触发切换**：上下文超限（调用方问题）、质量低。

### 4.2 weighted（加权随机）

按 `weight` 概率选择 provider。失败时从剩余中按权重重选。

```
第1次: 随机命中 B(weight=3) → 成功 → 返回 ✓
第2次: 随机命中 A(weight=5) → 失败 → {B(3), C(2)}重选 → 命中 C → 成功 → 返回 ✓
```

**实现**：`random.choices(providers, weights=[p["weight"]], k=len(providers))` + 去重。权重 0 不参与。全 0 回退 priority 并 WARNING。

### 4.3 cost_first（成本优先）

按 `input_price + output_price` 升序排列。

- 依赖 `pricing.py` 的 `PRICING_MERGED` 定价表
- 未知模型排末尾（`cost_score = float("inf")`）
- 首次调用主动触发 `reload_pricing()` 确保定价表就绪

### 4.4 fallback_only（仅回退）

与 `priority` 相同实现。语义区别：期望固定使用第一个 provider，后续仅应急。

**不实现会话级黑名单**——与熔断器职责重叠且增加复杂度。

### 4.5 proxy_preferred（代理偏好）

**不独立成策略**，而是作为策略引擎的**后置注入步骤**——在任何策略排序完成后执行。

**动机**：运行机器配置了 HTTP 代理时，某些 provider（如走 Anthropic/OpenAI 直连的）可能无法正常工作，而另一些（如 DeepSeek 兼容端点、本地 LLM）可以正常通过代理访问。代理偏好允许用户标记特定 provider 在代理环境下优先使用。

**配置方式**——在 `llm_providers.json` 的 provider entry 中增加可选标记：

```json
{
  "name": "deepseek-v4",
  "provider": "claude",
  "api_key": "sk-...",
  "model": "deepseek-v4-flash",
  "endpoint": "https://api.deepseek.com/anthropic/v1/messages",
  "priority": 2,
  "proxy_preferred": true
}
```

**行为**：

```
有代理環境                       無代理環境
┌──────────────────┐            ┌──────────────────┐
│ 原始 chain:       │            │ 原始 chain:       │
│ A(pri=1)          │            │ A(pri=1)          │
│ B(pri=2, proxy)   │            │ B(pri=2, proxy)   │
│ C(pri=3)          │            │ C(pri=3)          │
│                   │            │                   │
│ → proxy 注入後:   │            │ → 不變            │
│ B(pri=2, proxy)   │            │ A(pri=1)          │
│ A(pri=1)          │            │ B(pri=2, proxy)   │
│ C(pri=3)          │            │ C(pri=3)          │
└──────────────────┘            └──────────────────┘
```

**`_detect_proxy()` 检测顺序**：

1. `HTTP_PROXY`（环境变量）
2. `HTTPS_PROXY`
3. `http_proxy`（小写）
4. `https_proxy`
5. `ALL_PROXY`
6. 任意一个非空即视为"有代理环境"

**实现位置**——`strategy.py` 中新增辅助函数：

```python
def _detect_proxy() -> bool:
    """检测系统代理环境变量，任一非空即返回 True。"""
    return any(os.environ.get(v, "") for v in
               ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"])

def _apply_proxy_preferred(chain: list[dict]) -> list[dict]:
    """有代理时将 proxy_preferred 的 provider 移到首位，无代理时不变。"""
    if not _detect_proxy():
        return chain
    preferred = [p for p in chain if p.get("proxy_preferred")]
    others = [p for p in chain if not p.get("proxy_preferred")]
    return preferred + others
```

**与各策略的关系**：

```
resolve_provider_chain()
├── step 1: strategy 排序（priority / weighted / cost_first）
├── step 2: preferred_providers 模块偏好注入
└── step 3: _apply_proxy_preferred()    ← 后置注入，不入侵策略逻辑
```

- 有代理时 `proxy_preferred: true` 的 provider **无条件排链首**（它们之间仍按 strategy 排序）
- **优先级**：`proxy_preferred` > `preferred_providers`（模块偏好）——代理环境覆盖是运行时强制，优先于模块级偏好
- 无代理时**完全无效果**，行为零变化
- 所有策略（priority / weighted / cost_first / fallback_only）均受其影响

**测试要点**：

| 场景 | 预期 |
|:-----|:------|
| 有代理 + proxy_preferred 标记 | 标记 provider 排首位 |
| 无代理 + proxy_preferred 标记 | 标记无效，原序不变 |
| 有代理 + 多条 proxy_preferred | 多条标记排首位，相互按 strategy 排序 |
| 有代理 + 无 proxy_preferred | 行为不变 |

---

## 5. 每模块 Provider 路由

```json
{
  "preferred_providers": {
    "global_macro": "gemini-pro",
    "expert_review": "deepseek-v4"
  }
}
```

**规则**：
- 模块键匹配时，对应 provider 在 chain 中排首位
- 偏好 provider 不存在时 WARNING 并忽略
- 无偏好时使用全局策略

---

## 6. 缓存兼容性

缓存 key 格式调整：`llm_{module_key}_{provider_name}_{fingerprint}`（不带扩展名，由 cache API 内部处理）。

**动机**：不同 provider 输出可能不同，需避免交叉污染。

### 6.1 骨架层缓存流程

`skeleton.py` 的缓存流程改为**先解析链 → 乐观预检 → 调用 → 按实际 provider 落盘**：

```
skeleton.py 缓存流程
                              ┌──────────────────────────────────┐
                              │ resolve_provider_chain()         │
                              │ → 获取有序 provider 列表         │
                              └──────────────┬───────────────────┘
                                             ▼
                              ┌──────────────────────────────────┐
                              │ 乐观预检：chain[0] 的 name       │
                              │ cache_key = "{module}_{chain[0]  │
                              │  name}_{fingerprint}"            │
                              │ cache.get(cache_key, ttl)        │
                              │ 命中 → 直接返回 cached result   │
                              └──────────────┬───────────────────┘
                                             ▼ 未命中
                              ┌──────────────────────────────────┐
                              │ call_llm()                       │
                              │ → 返回 (result, usage,           │
                              │           selected_provider)     │
                              └──────────────┬───────────────────┘
                                             ▼ success
                              ┌──────────────────────────────────┐
                              │ cache_key = "{module}_{selected_ │
                              │  provider}_{fingerprint}"        │
                              │ cache.set(cache_key, result)     │
                              └──────────────────────────────────┘
                              ↓ failure → 返回 (None, None)
```

**设计要点**：
- 乐观预检只查 chain 首位，不遍历全链（避免频繁 cache.get 开销）
- 首位 provider 稳定时（成功率 >99%），预检命中率接近 100%
- 预检 key 与落盘 key 使用同一格式，首位 provider 不变时首次预检即命中
- 全部失败时 `provider_name = None`，不写入缓存

---

## 7. 熔断器适配

熔断器（`circuit_breaker.py`）**不做修改**。按 endpoint URL 隔离：
- 同一 endpoint + 不同 key → 同一熔断维度
- chain 检测到熔断 → 自动跳过该 provider

---

## 8. 涉及文件清单

| 文件 | 操作 | 说明 |
|:-----|:------|:------|
| `src/python/llm/strategy.py` | **新建** | 策略引擎 |
| `src/python/llm/api.py` | **修改** | `call_llm()` chain 集成 + 返回 `(result, usage, provider_name)`，移除 fallback 逻辑 |
| `src/python/llm/api_base.py` | **修改** | 失败原因带 provider name |
| `src/python/llm/__init__.py` | **修改** | 导出 strategy |
| `src/python/llm/skeleton.py` | **修改** | 缓存 key 含 provider name + 链解析乐观预检 |
| `src/python/config/_core.py` | **修改** | `get_llm_config()` 扩展 + 3 个新函数 + `get_llm_key_path()` 移除 |
| `src/python/config/_config_defaults.py` | **修改** | 移除 `llm_key_file` + `_PATH_KEYS` |
| `src/python/config/__init__.py` | **修改** | 移除 `get_llm_key_path` 导出 |
| `src/python/config/_comments.py` | **修改** | 模板注释更新 |
| `src/python/handlers_config.py` | **修改** | Provider 列表只读查看 |
| `src/python/tui_menu.py` | **修改** | 注册 P 快捷键 |
| `data/config/llm_providers.json` | **新建** | 用户手动创建 |
| `src/test/unit/config/test_config_llm_multi.py` | **新建** | 配置解析测试 |
| `src/test/unit/config/test_config_llm_multi_edge.py` | **新建** | 配置解析边缘测试 |
| `src/test/unit/llm/test_strategy.py` | **新建** | 策略测试 |
| `src/test/unit/llm/test_api_multi.py` | **新建** | Chain 集成测试 |
| `src/test/unit/llm/test_cache_multi.py` | **新建** | 缓存 key 测试 |
| `docs-stm/manuals/how-to-config-llm.md` | **修改** | 新配置指南 |
| `docs-stm/manuals/how-to-config.md` | **修改** | 移除旧配置项 |
| `docs-stm/managements/technical.md` | **修改** | 追加 C17/C18；C16 路径键列表移除 `llm_key_file` |

---

## 9. 架构设计约束

### C17 — LLM Provider Chain 必经

所有 LLM API 调用必须经过 `call_llm()` 的 provider chain 路由，不得绕过。

| 属性 | 值 |
|:-----|:-----|
| **编号** | C17 |
| **名称** | LLM Provider Chain 必经 |
| **目的** | 多 provider 策略/链式回退/熔断跳过集中实现 |
| **违反后果** | 高可用/成本优化失效 |
| **涉及模块** | `llm/api.py`, `skeleton.py`, `generators*.py` |
| **执行** | code review |

### C18 — Provider 与行为配置分离

`llm_providers.json` 只负责 provider 列表 + 路由策略，行为参数归属 `llm_settings.json`。

---

## 10. 风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|:-----|:------|:----|:------|
| `call_llm()` 重构导致 LLM 全部失效 | 高 | 低 | R6-R7 全 mock 测试覆盖 11 种场景 + 480 项回归 |
| 缓存 key 变更导致所有 LLM 缓存失效 | 中 | 确定 | 接受——一次性影响 |
| cost_first 依赖 pricing 惰性加载 | 低 | 低 | 主动触发 `reload_pricing()` |
| weighted 随机性使测试 flaky | 低 | 中 | 固定 seed 确定性验证 |
| 缓存 key 预检 vs 落盘 provider 不一致 | 低 | 低 | 乐观预检只是优化，miss 后走完整流程 |
| proxy_preferred 环境变量影响测试 | 低 | 低 | mock os.environ 隔离 |
| `get_llm_key_path()` 移除影响外部测试 mock | 中 | 中 | R12 逐一更新 6 处 mock 引用 |
