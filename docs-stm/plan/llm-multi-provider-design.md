# 多 LLM Provider 链式服务 — 技术设计

> 文档版本：v1.0
> 状态：待实现
> 关联计划：[llm-multi-provider-iteration-plan.md](llm-multi-provider-iteration-plan.md)

---

## 目录

- [1. 背景与目标](#1-背景与目标)
- [2. 数据模型](#2-数据模型)
  - [2.1 Provider 配置模型](#21-provider-配置模型)
  - [2.2 llm_providers.json v1 格式](#22-llm_keyjson-v2-格式)
  - [2.3 向后兼容策略](#23-向后兼容策略)
  - [2.4 llm_settings.json 新增配置](#24-llm_settingsjson-不变职责分离)
- [3. 架构变更](#3-架构变更)
  - [3.1 总体数据流](#31-总体数据流)
  - [3.2 config/_core.py 变更](#32-config_corepy-变更)
  - [3.3 llm/api.py 变更 — Provider Chain](#33-llm-apipy-变更--provider-chain)
  - [3.4 使用策略实现](#34-使用策略实现)
- [4. 各策略行为详解](#4-各策略行为详解)
  - [4.1 priority（优先级顺序）](#41-priority优先级顺序)
  - [4.2 weighted（加权随机）](#42-weighted加权随机)
  - [4.3 cost_first（成本优先）](#43-cost_first成本优先)
  - [4.4 fallback_only（仅回退）](#44-fallback_only仅回退)
- [5. 每模块 Provider 路由](#5-每模块-provider-路由)
- [6. 熔断器适配](#6-熔断器适配)
- [7. 向后兼容与迁移](#7-向后兼容与迁移)
- [8. 配置示例](#8-配置示例)
- [9. 涉及文件清单](#9-涉及文件清单)
- [10. 架构设计约束](#10-架构设计约束)

---

## 1. 背景与目标

### 1.1 现状

当前 LLM 服务仅支持**一个 `llm_providers.json` 文件**配置单一 provider（claude / openai / gemini），`llm_settings.json` 中有 `fallback_provider` 字段做简单回退。存在以下限制：

- 只能使用一个 API Key，一家 LLM 服务商
- 回退仅支持一层，无法链式多级回退
- 无法按成本/权重/模块灵活路由请求
- 单点故障：某 provider 不可用时整个 LLM 功能降级

### 1.2 目标

- 支持**多个 LLM Provider** 同时配置（同一 `llm_providers.json` 文件中声明）
- 支持**链式优先级回退**（首选 → 次选 → 三选…）
- 支持**加权随机分发**（按权重比例分配请求）
- 支持**成本优先路由**（自动选最便宜的模型）
- 支持**每模块指定偏好 provider**
- 现有单 provider 配置**向后兼容**

---

## 2. 数据模型

### 2.1 Provider 配置模型

```python
@dataclass
class LLMProviderConfig:
    """单个 LLM Provider 的完整配置。"""
    name: str              # 唯一标识名（用于日志/路由引用）
    provider: str          # "claude" | "openai" | "gemini"
    api_key: str
    model: str
    endpoint: str | None   # None = 使用各 provider 默认端点
    priority: int          # 越小优先级越高（1=最高）
    weight: int            # 加权随机策略权重（越大越容易被选中）
    timeout: float         # 单次调用超时（覆盖全局默认值）
    max_retries: int       # 单 provider 重试次数（覆盖全局默认值）
```

### 2.2 llm_providers.json v1 格式

```json
{
  "version": 2,
  "providers": [
    {
      "name": "gemini-pro",
      "provider": "gemini",
      "api_key": "AI...",
      "model": "gemini-2.5-pro",
      "priority": 1,
      "weight": 5,
      "timeout": 120
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
      "name": "openai-gpt4o",
      "provider": "openai",
      "api_key": "sk-...",
      "model": "gpt-4o",
      "priority": 3,
      "weight": 2
    }
  ]
}
```

### 2.3 向后兼容策略

v1 旧格式（当前 `llm_providers.json`）自动识别并转换为单 provider 列表：

| 条件 | 处理方式 |
|------|---------|
| `"version"` 缺失 | 默认视为 version 1 |
| 文件不存在 | LLM 功能不可用（记录 WARNING） |
| providers 数组为空 | LLM 功能不可用 |
| 存在旧 `llm_key.json` | 忽略，仅读取 `llm_providers.json` |

检测逻辑：`get_llm_config()` 返回的 dict 增加 `"_provider_list"` 和 `"_strategy"` 键，供 `call_llm()` 消费。原有的 `provider` / `api_key` / `model` / `endpoint` 键保留为**第一个 provider 的引用**，保证 `get_llm_config().get("model")` 等现有调用不变。

### 2.4 llm_settings.json 不变（职责分离）

`llm_settings.json` **保持现有职责不变**，仅负责 LLM 服务在投资报告分析中的行为表现（缓存 TTL、temperature、output_brief、enabled_llm 开关等）。

多 Provider 策略定义（`llm_strategy`、`llm_preferred_providers`）**移至 `llm_providers.json`**，与 provider 配置放在同一文件中，确保策略与配置同源、不分散。

```json
{
  // ── 多 Provider 策略 ──
  "llm_strategy": "priority",
  // 可选: "priority" | "weighted" | "cost_first" | "fallback_only"

  // ── 每模块 Provider 偏好（可选） ──
  "llm_preferred_providers": {
    "global_macro": "gemini-pro",
    "expert_review": "deepseek-v4",
    "health_check": "gemini-pro"
  }
}
```

---

## 3. 架构变更

### 3.1 总体数据流

```
                      llm_providers.json (v1)
                           │
                    ┌──────┴──────┐
                    │  config/    │
                    │  _core.py   │
                    │  get_llm_   │
                    │  config()   │
                    └──────┬──────┘
                           │ 返回 dict (含 _provider_list)
                           ▼
                    ┌──────────────┐
                    │  llm/        │
                    │  api.py      │
                    │  call_llm()  │
                    │              │
                    │  ┌────────┐  │
                    │  │Strategy│  │
                    │  │Engine  │  │
                    │  └───┬────┘  │
                    │      │       │
                    │      ▼       │
                    │  Provider    │
                    │  Chain       │
                    │  (循环)      │
                    └──────┬──────┘
                           │ 成功返回
                           ▼
                      LLM Response
```

### 3.2 config/_core.py 变更

**`get_llm_config()` 返回结构扩展**：

```python
# 返回 dict 增加以下键（原有键保持不变）
{
    ...  # 原有字段（provider, api_key, model, endpoint 等）
    "_provider_list": [LLMProviderConfig, ...],  # 解析后的 provider 列表
    "_strategy": "priority",                     # 使用策略
    "_preferred_providers": {                     # 每模块偏好
        "global_macro": "gemini-pro",
        ...
    },
}
```

**新增内部函数**：

```python
def _parse_llm_key_v2(key_config: dict) -> list[dict]:
    """解析 v2 格式的 providers 列表，v1 自动转换为单列表。"""

def _validate_provider_entry(entry: dict, index: int) -> list[str]:
    """校验单个 provider 配置项的完整性，返回问题列表。"""
```

**现有 `get_llm_key_path()` 不变**——key 文件仍为单一 `llm_providers.json`，只是其内部格式升级为数组。

### 3.3 llm/api.py 变更 — Provider Chain

**`call_llm()` 重构**：

```python
def call_llm(...) -> tuple[str | None, dict | None]:
    # 1. 从 llm_config 中提取 _provider_list
    # 2. 根据模块名（从 config_field 推断）检查 _preferred_providers
    # 3. 按策略选择 provider 顺序
    # 4. 依次尝试，第一个成功即返回
    # 5. 全部失败后记录所有失败原因
```

**新增内部函数**：

```python
def _select_provider_chain(
    provider_list: list[LLMProviderConfig],
    strategy: str,
    module_key: str,
    preferred: dict[str, str],
) -> list[LLMProviderConfig]:
    """根据策略和模块偏好，返回 provider 尝试顺序列表。
    
    对于 weighted 策略，每次调用随机排列（但全部尝试直到成功）。
    对于 cost_first 策略，按模型定价排序。
    """

def _try_provider_chain(
    chain: list[LLMProviderConfig],
    ...,
) -> tuple[str | None, dict | None, str]:
    """按顺序尝试 provider chain，返回 (content, usage, provider_name)。
    第三个返回值用于日志和使用统计。
    """
```

**`call_single_provider()` 接口不变**——它只负责一次调用，不感知 chain。

### 3.4 使用策略实现

**策略引擎位置**：`llm/strategy.py`（新增独立模块，职责清晰）

```python
def resolve_provider_chain(
    provider_list: list[dict],
    strategy: str,
    module_key: str = "",
    preferred: dict[str, str] | None = None,
) -> list[dict]:
    """返回需按顺序尝试的 provider 列表。
    
    priority:    按 priority 升序排列
    weighted:    按 weight 概率随机排序（每次调用结果可能不同）
    cost_first:  按模型 input+output 平均价格升序排列
    fallback_only: 同 priority，但仅首 provider 参与了正常调用
    """
```

---

## 4. 各策略行为详解

### 4.1 priority（优先级顺序）

**默认策略**。按 `priority` 字段升序尝试，第一顺位成功后不再尝试其他。

```
Provider A (priority=1) → 成功 → 返回 ✓
Provider A (priority=1) → 失败 → Provider B (priority=2) → 成功 → 返回 ✓
Provider A → 失败 → Provider B → 失败 → Provider C (priority=3) → ... → 全部失败 → None
```

**失败判定**（触发换 provider）：
- 网络错误（超时、连接拒绝）
- 熔断器已打开
- API 返回 429/503
- API Key 无效（4xx 认证错误）
- 空内容（内容过滤）

**不触发换 provider**：
- 上下文长度超限（这是调用方问题，换 provider 无意义）
- LLM 返回了合法内容但质量低

### 4.2 weighted（加权随机）

按 `weight` 字段概率选择 provider。某次调用失败时，**从剩余 provider 中按权重重选**，不按固定顺序。

```
第1次: 随机命中 Provider B (weight=3)
        → 成功 → 返回 ✓
第2次: 随机命中 Provider A (weight=5)
        → 失败 → 从 {B(3), C(2)} 中重选 → 命中 C → 成功 → 返回 ✓
```

权重调整建议：
- Gemini 免费额度大 → `weight: 8`（多用）
- DeepSeek 便宜 → `weight: 5`
- GPT-4o 贵 → `weight: 1`（少用）

### 4.3 cost_first（成本优先）

估算每次调用的费用，**选择最便宜的 provider 优先尝试**。失败后再按成本升序尝试剩余。

```
成本排序（按 input 价 + 预估输出量 × output 价）:
  gemini-2.5-flash < deepseek-v4-flash < gpt-4o-mini < claude-sonnet-4

→ 先试 gemini-2.5-flash，失败后试 deepseek-v4-flash，依此类推
```

**费用估算依赖** `pricing.py` 的 `PRICING_MERGED` 定价表，动态排序。

### 4.4 fallback_only（仅回退）

与 `priority` 行为相同，但**前台始终只用同一 provider**（priority=1），失败后才用此后 provider。适用于希望固定使用某服务商、仅在故障时切换的场景。

```
Provider A → 成功 → 每次都用 A ✓
Provider A → 失败 → Provider B → 此后会话中 B 成为"当前"主体
```

---

## 5. 每模块 Provider 路由

支持在 `llm_settings.json` 中按 LLM 模块指定偏好 provider：

```json
{
  "llm_preferred_providers": {
    "global_macro": "gemini-pro",
    "expert_review": "deepseek-v4",
    "health_check": "gemini-pro",
    "penetration_deep": "openai-gpt4o",
    "news_correlation": "deepseek-v4"
  }
}
```

- 模块名与 `enabled_llm` 中的 key 一致
- 当模块有偏好时，对应 provider 在该模块的 chain 中**排到第一位**（无论 priority）
- 偏好 provider 失败后，按策略规则回退到其他 provider
- 偏好的 provider 在 `_provider_list` 中不存在时，记录 WARNING 并忽略该偏好

---

## 6. 熔断器适配

现有熔断器（`circuit_breaker.py`）按 endpoint URL 维度隔离。多 provider 场景下：

- **同一 endpoint + 不同 key**：应视为同一个熔断维度（问题在 endpoint 不在 key）
- **不同 endpoint**：现有按 URL 的熔断无需修改
- **熔断恢复**：依然是 min(连续失败次数, 5) 失败后熔断，1 次成功重置

**改动点**：`call_llm_with_retry()` 不感知 provider 切换——熔断器在 `_attempt_api_call` 之前检查，熔断时 `kind == "retryable"` 经由 `_is_retry_available` 判定是否可重试。当可重试次数耗尽后，`call_single_provider()` 返回 `(None, None)`，`call_llm()` 的 chain 逻辑识别到失败后切至下一 provider。

---

## 7. 向后兼容与迁移

### 迁移路径

| 步骤 | 操作 | 影响 |
|:-----|:------|:------|
| 0 | 用户原地升级，现有 v1 `llm_providers.json` 照常工作 | 无感 |
| 1 | 用户手动将 v1 格式扩展为 v2 格式（version + providers 数组） | 支持多 provider |
| 2 | 用户可在 `llm_settings.json` 中设置 `llm_strategy` 切换策略 | 灵活分发 |
| 3 | 用户可在 `llm_settings.json` 中设置 `llm_preferred_providers` | 每模块路由 |

**v1 → v2 转换示例**：

```json
// v1 旧格式
{ "provider": "claude", "api_key": "sk-...", "model": "claude-sonnet-4-6", "endpoint": "..." }

// 自动转换为内部表示
{ "_provider_list": [
    { "name": "default", "provider": "claude", "api_key": "sk-...", "model": "claude-sonnet-4-6", "endpoint": "...", "priority": 1, "weight": 1, "timeout": 120, "max_retries": 2 }
  ],
  "_strategy": "priority",
  "provider": "claude", "api_key": "sk-...", "model": "claude-sonnet-4-6", "endpoint": "..."
}
```

### 迁移工具（可选 S5）

提供 `python -m src.python.llm.migrate_v1_to_v2` 脚本，读取现有 `llm_providers.json` 并输出 v2 模板供用户编辑。

---

## 8. 配置示例

### 完整配置示例

**`data/config/llm_providers.json`**：
```json
{
  "version": 2,
  "providers": [
    {
      "name": "gemini-pro",
      "provider": "gemini",
      "api_key": "AIzaSy...",
      "model": "gemini-2.5-pro",
      "priority": 1,
      "weight": 5,
      "timeout": 120
    },
    {
      "name": "deepseek-claude",
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

**`data/config/llm_settings.json`**（不变，无新增字段）：
```json
{
  // 保持现有 LLM 行为配置（缓存、temperature、output_brief 等）
  // 多 Provider 策略移入 llm_providers.json
}
```

---

## 9. 涉及文件清单

| 文件 | 操作 | 说明 |
|:-----|:------|:------|
| `src/python/llm/strategy.py` | **新建** | 策略引擎（provider chain 选择逻辑） |
| `src/python/llm/api.py` | **修改** | `call_llm()` 集成 provider chain 循环 |
| `src/python/llm/api_base.py` | **修改** | 失败原因细化（区分 provider-level 失败与 chain-level 失败） |
| `src/python/llm/__init__.py` | **修改** | 导出新模块 |
| `src/python/config/_core.py` | **修改** | `get_llm_config()` 解析 v2 格式，生成 `_provider_list` |
| `src/python/config/_llm_defaults.py` | **修改** | 默认值模板加入新字段 |
| `data/config/llm_settings.json` | **不变** | 职责分离，策略配置移至 `llm_providers.json` |
| `data/config/llm_providers.json` | **新建** | 用户手动创建（取代 `llm_key.json`） |
| `src/test/unit/config/test_config_llm_multi.py` | **新建** | v2 解析测试 |
| `src/test/unit/llm/test_strategy.py` | **新建** | 各策略行为测试 |
| `src/test/unit/llm/test_api_multi.py` | **新建** | Provider chain 集成测试 |

---

## 10. 架构设计约束

### C17 — Provider Chain 必经

**所有 LLM 调用必须经过 `call_llm()` 中的 provider chain 路由，不得绕过策略引擎直接调用 `call_single_provider()`**。

违反此约束的代码将在 code review 中被拒绝。

| 属性 | 值 |
|:-----|:-----|
| **约束编号** | C17 |
| **约束名称** | Provider Chain 必经 |
| **违反后果** | 无法利用多 provider 高可用、策略配置不生效 |
| **涉及模块** | `llm/api.py`、`llm/skeleton.py`、`llm/generators*.py` |
| **强制执行** | code review + 测试覆盖 |
