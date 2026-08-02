# LLM 配置指引

全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析、以及可选的财经新闻热点与持仓关联分析均需调用外部 LLM API。

LLM 配置由三个独立文件管理：

| 文件 | 内容 | 用途 |
|------|------|------|
| `data/config/llm_key.json` | 4 个必填 + 4 个可选回退字段，或 `credentials_ref` 多键凭据块 | API 调用渠道（必填：provider / api_key / model / endpoint；可选：fallback_provider / fallback_api_key / fallback_endpoint / fallback_model） |
| `data/config/llm_providers.json` | Provider 路由配置（多链模式） | 定义多个 Provider 的切换顺序、策略和凭据引用 |
| `data/config/llm_settings.json` | 所有非敏感配置 | 参数调优（temperature、timeout、cache、system_prompt 等） |

> **为什么用三个文件？** `llm_key.json` 包含 API Key，可加入 `.gitignore` 避免误提交；
> `llm_providers.json` 和 `llm_settings.json` 不含密钥，可安全纳入版本控制，方便团队共享调优参数。
>
> **不配置会怎样？** `llm_key.json` 缺失或 key 为空时，程序不崩溃，其他功能正常。对应报告页签显示占位提示。不同失败场景的占位文本：
> 
> | 原因 | 占位文本 |
> |------|---------|
> | LLM 未配置 | 本节内容待生成 — LLM 未配置（请配置 data/config/llm_key.json） |
> | API 调用失败 | 本节内容待生成 — LLM API 调用失败（请检查 API Key 和网络连接后重新生成） |
> | 请求超时 | 本节内容待生成 — LLM API 请求超时（可尝试在 llm_settings.json 中增大 timeout 配置） |
> | 网络连接失败 | 本节内容待生成 — LLM API 网络连接失败（请检查网络后重新生成） |
> | 熔断冷却中 | 本节内容待生成 — LLM API 暂时不可用（熔断冷却中，请稍后重试） |
> | 模块已禁用 | （直接跳过，无占位文本，报告中不出现该页签） |

---

## 快速配置

**Step 1**：编辑 `data/config/llm_key.json`，填入必填字段和（可选）回退字段：

```json
{
  "provider": "claude",
  "api_key": "sk-ant-xxxxxxxxxxxxx",
  "model": "claude-sonnet-4-20250514",
  "endpoint": "https://api.anthropic.com/v1/messages",
  "fallback_provider": "openai",
  "fallback_api_key": "sk-your-fallback-key",
  "fallback_endpoint": "https://api.openai.com/v1/chat/completions",
  "fallback_model": "gpt-4o-mini"
}
```

> **必填字段**：仅前 4 项（`provider` / `api_key` / `model` / `endpoint`）即可运行。`fallback_*` 回退字段可选，配置后主 provider 连续失败时自动切换，适用于高可用场景（如主用 DeepSeek 低成本、回退 Anthropic Claude 高稳定性）。非敏感参数统一在 `llm_settings.json` 中管理。

**Step 2**（可选，使用默认值即可跳过）：编辑 `data/config/llm_settings.json`，根据偏好微调参数。示意结构如下（完整配置项见「配置项总览」章节）：

```json
{
  "max_retries": 2,
  "enabled_llm": {
    "global_macro": true,
    "expert_review": true,
    "health_check": true,
    "penetration_deep": true,
    "news_correlation": false
  },
  "temperature_global_macro": 0.3,
  "max_tokens_global_macro": 2048,
  "temperature_expert_review": 0.3,
  "max_tokens_expert_review": 20000,
  "pricing": {
    "currency": "CNY"
  }
}
```

> **注意**：
> - `system_prompt_*` 默认值为 `null`，表示使用代码内置提示词。填入字符串可覆盖。
> - 代码内置提示词定义在 `src/python/llm/prompts_core.py`（主 prompt）、`prompts_tables.py`（数据表格）、`prompts_action.py`（行动建议）中，更新代码时可自动升级。
> - `pricing` 段可省略（使用代码内置定价），仅需自定义覆盖时添加，详见下方「完整模型定价表」章节。

**Step 3**：启动程序，菜单选 **L** 生成包含 LLM 分析的完整版报告。

---

## 多 Provider 链式服务（进阶）

当需要同时配置多个 LLM 服务商（如 DeepSeek 为主、Gemini 为辅），按策略自动切换时，可启用多链模式。

### 文件分工

| 文件 | 内容 | 安全等级 |
|------|------|---------|
| `llm_providers.json` | Provider 路由配置：名称、类型、切换策略、凭据引用 | ✅ 可提交仓库 |
| `llm_key.json` | 凭据块：每个 `credentials_ref` 对应一个包含 api_key / model / endpoint 的命名块 | ❌ 含密钥，不提交 |

### 配置步骤

**Step A** — 编辑 `data/config/llm_providers.json`：

```json
{
  "strategy": "priority",
  "preferred_providers": {},
  "providers": [
    {
      "name": "deepseek-main",
      "provider": "claude",
      "credentials_ref": "deepseek-main",
      "priority": 10,
      "timeout": 120
    },
    {
      "name": "gemini-fallback",
      "provider": "gemini",
      "credentials_ref": "gemini-fb",
      "priority": 20,
      "timeout": 60,
      "proxy_preferred": true
    }
  ]
}
```

**Step B** — 在 `data/config/llm_key.json` 中添加对应凭据块：

```json
{
  "deepseek-main": {
    "api_key": "sk-your-deepseek-key",
    "model": "DeepSeek-V4-Flash",
    "endpoint": "https://api.deepseek.com/anthropic"
  },
  "gemini-fb": {
    "api_key": "AIzaSyYourGeminiKey",
    "model": "gemini-3.5-flash",
    "endpoint": "https://generativelanguage.googleapis.com/v1beta"
  }
}
```

> **注意**：`llm_key.json` 使用多键格式时，顶层 `provider` / `api_key` / `model` / `endpoint` 字段无效，需要为每个 `credentials_ref` 定义独立的命名凭据块。`llm_providers.json` 中的 `credentials_ref` 值必须与 `llm_key.json` 中的键名精确匹配。

### Provider 条目字段

| 字段 | 必填 | 类型 | 说明 |
|------|:----:|:----:|------|
| `name` | ✅ | string | Provider 唯一标识名，用于日志和缓存键 |
| `provider` | ✅ | string | 服务商类型：`claude` / `openai` / `gemini` |
| `credentials_ref` | ✅ | string | 引用 `llm_key.json` 中的凭据块键名 |
| `priority` | ❌ | int | 优先级（数值越小越优先），默认 50 |
| `weight` | ❌ | int | 加权随机权重，仅 `weighted` 策略有效，默认 1 |
| `timeout` | ❌ | int | 超时秒数，覆盖全局 timeout，默认 60 |
| `proxy_preferred` | ❌ | bool | `true` 时优先使用代理直连（而非自动路由），默认 `false` |

### 切换策略

`strategy` 字段支持 4 种切换策略：

| 策略 | 值 | 行为 |
|------|:---:|------|
| **优先级排序** | `priority` | 按 `priority` 字段升序尝试，第一个成功返回即停止。这是默认策略 |
| **加权随机** | `weighted` | 按 `weight` 权重随机选取 Provider，失败后重试其他 |
| **价格最低优先** | `cost_first` | 优先使用单价最低的 Provider，失败后按价格升序递补 |
| **仅 Fallback** | `fallback_only` | 始终使用第一个 Provider，仅在其全部失败后尝试下一个 |

> `proxy_preferred` 不是策略类型，而是 provider 条目级别的后处理标记。启用时，该条目的请求将优先通过代理发送（若系统配置了代理），而非直连。

### 模块级 Provider 偏好

当特定 LLM 模块（如智囊团深度复盘）需要使用指定的 provider，而其他模块沿用默认排序时，可通过 `preferred_providers` 字段配置模块级偏好：

```json
{
  "strategy": "priority",
  "preferred_providers": {
    "expert_review": "gemini-fallback",
    "health_check": "gemini-fallback"
  },
  "providers": [
    { "name": "deepseek-main", "provider": "claude", "credentials_ref": "deepseek-main", "priority": 10, "timeout": 120 },
    { "name": "gemini-fallback", "provider": "gemini", "credentials_ref": "gemini-fb", "priority": 20, "timeout": 60 }
  ]
}
```

上述配置的效果：

| 模块 | module_key | Chain 排序 | 优先尝试 |
|------|-----------|-----------|---------|
| 智囊团深度复盘 | `expert_review` | `[gemini-fallback, deepseek-main]` | Gemini |
| 持仓体检报告 | `health_check` | `[gemini-fallback, deepseek-main]` | Gemini |
| 全球政经局势 | `global_macro`（未配置） | `[deepseek-main, gemini-fallback]` | DeepSeek |
| 穿透深度分析 | `penetration_deep`（未配置） | `[deepseek-main, gemini-fallback]` | DeepSeek |

> **module_key 规则**：对应 `llm_settings.json` 中 `max_tokens_{module_key}` 的 `{module_key}` 部分。有效值：`global_macro` / `expert_review` / `health_check` / `penetration_deep` / `news_correlation`。
>
> `preferred_providers` 中的 provider 名称必须与 `providers[].name` 精确匹配，否则该条配置会被忽略并记录警告日志。

### 配置检查

TUI 菜单 **[S]** 查看状态时会显示多链模式详情：

```
LLM: 已配置  多链服务: deepseek-main + gemini-fallback (2 provider)
```

### 兼容性

- 多链模式与 flat 格式（`llm_key.json` 含顶层 `api_key` / `provider`）**并存兼容**。检测到 `llm_key.json` 有顶层 `api_key` 时自动使用 flat 模式，否则按 `credentials_ref` 多链模式解析
- 不需要多链时，保持 flat 格式即可，`llm_providers.json` 可不配置

---

## 模块启停

通过 `enabled_llm` 嵌套字典控制每个模块的开关，除 `news_correlation` 默认关闭外，其余默认开启：

```json
"enabled_llm": {
  "global_macro": true,
  "expert_review": true,
  "health_check": true,
  "penetration_deep": true,
  "news_correlation": false
}
```

- 关闭的模块在报告中自动跳过，不消耗 Token
- 可通过菜单 **S** 交互式开关各模块
- 菜单 **[S]** 面板分两组：标准 LLM 模块（1-5，即上方 `enabled_llm` 字典）与 ⚗ 实验性辩论模式（6-8，由 `features.json` 的 `llm_debate_*` Feature Flag 控制，见下方 `debate` 配置段）。「辩论-正反辩论」（编号 6）开启后输出白脸（看多）→ 黑脸（看空）→ 综合（收敛）三个连续色块，三者是同一功能内的生成阶段，**不提供单独开关**
- 若 4 个 LLM 报告模块（global_macro / expert_review / health_check / penetration_deep）全部关闭，LLM 分析章节在报告中整体隐藏
- 仅 `news_correlation` 开启时不影响 LLM 分析章节可见性

---

## 缓存机制

LLM 分析结果默认缓存，避免重复调用 API 浪费费用：

- **缓存自动失效** — 持仓数据或指数数据变更时，对应的 LLM 缓存自动失效。无需手动操作
- **缓存有效期** — 各模块独立配置（`cache_ttl` 中的 `llm_{module}` 条目），默认值见[配置指南](how-to-config.md#cache_ttl-可调参数)
- **手动清除** — 菜单 **[2]** 更新持仓缓存 → 所有 LLM 缓存自动清除
- **关闭缓存** — 在 `llm_settings.json` 中将 `cache_enabled_{module}` 设为 `false`，每次生成都重新调用 API

---

## 失败降级与占位

各模块在以下场景下自动降级或重试：

| 场景 | 行为 | 日志 |
|------|------|------|
| `llm_key.json` 缺失或 key 为空 | 显示占位："本节内容待生成 — LLM 未配置" | INFO |
| `enabled_llm.{module}` = false | 直接跳过，不显示占位 | INFO |
| API 调用失败（网络错误/超时） | 显示占位："（本节内容生成失败）" | WARNING |
| 返回空内容（无文本块，如思考耗尽 max_tokens 预算） | 关闭 thinking 同 Provider 重试一次；仍失败才切换下一 Provider | WARNING |
| 返回空字符串（内容被过滤） | 追加安抚指令重试一次，仍失败则切换 Provider | WARNING |
| 输出被截断（含 `... [TRUNCATED] ...`） | 自动增大 `max_tokens` 1.5× 重试一次，仍截断则记录日志提示用户手动调大 | WARNING |

---

## `system_prompt` 配置覆盖链

系统提示词按以下优先级（高 → 低）解析：

1. `llm_settings.json` → `system_prompt_{module}` 的值（非 null）
2. 代码内置提示词（`prompts_core.py` / `prompts_tables.py` / `prompts_action.py` 中定义）

> 设为 `null` 表示回退使用代码内置提示词，升级代码时可自动获取更新。

**示例** — 让智囊团深度复盘输出英文摘要：

```json
{
  "system_prompt_expert_review": "You are an investment expert. Analyze the portfolio data and provide a concise review in English, including risk assessment and rebalancing suggestions. Keep the output within 500 words."
}
```

> 注意：覆盖后不会随代码升级自动更新，移除该字段或设为 `null` 即可恢复内置提示词。

---

## 配置项总览

> 以下为 `llm_settings.json` 的全部配置项。`{module}` 占位符替换为具体的模块后缀（global_macro / expert_review / health_check / penetration_deep / news_correlation）。

配置分为**全局配置**和**模块级配置**两类。全局配置共有 7 项：

- `max_retries`（int，默认 `2`）：遇到 429 或 503 时最多重试次数
- `llm_max_concurrency`（int，默认 `3`）：LLM 模块并发生成的最大线程数。设为 1 时完全串行，设为 4 及以上可提升速度但可能触发 API 限速（429）。建议值 2-3
- `enabled_llm`（dict，默认全部 `true`，仅 `news_correlation` 为 `false`）：各模块独立启停开关
- `fact_check`（dict，默认 `{tolerance: 1.0}`）：LLM 输出数值一致性检测配置。详见下节「事实校验容差配置」
- `pricing`（dict，默认 `{currency: "CNY"}`）：模型 Token 定价表，可省略（使用代码内置定价），仅需覆盖时添加
- `news_correlation_top_n`（int，默认 `30`）：送 LLM 分析的新闻条数。仅 news_correlation 模块有效，值越大 Token 消耗越高
- `debate`（dict，可选实验功能）：辩论模式配置。含 procon（三段式正反辩论）、conditional（条件情景推理）、qa_concentration（集中度问答），以及 `max_total_tokens_per_report`（单次报告辩论总 Token 预算上限）和 `per_call_timeout_override`（辩论单次 API 超时覆盖）。**通过 Feature Flag 控制启停，非配置直接启用**

### 模块级配置

| 配置键 | 类型 | 默认值（各模块不同） | 说明 |
|--------|:----:|:--------------------:|------|
| `system_prompt_{module}` | string / null | `null` | 系统提示词覆盖，`null`=使用代码内置 prompt |
| `model_{module}` | string / null | `null` | 独立指定本模块使用的模型，`null`=使用 Provider 默认模型。**仅 flat 模式生效；多链模式优先使用 `llm_providers.json` 中凭据块定义的模型** |
| `temperature_{module}` | float | 0.1~0.8（模块差异） | 采样温度，0=确定性最高，1=最大多样性 |
| `max_tokens_{module}` | int | 2048~20000（模块差异） | 输出最大 token 数，超过时内容被截断（触发自动重试）。**DeepSeek 为 thinking + 正文共享预算**（详见下方 DeepSeek V4 说明） |
| `timeout_{module}` | int | 60~120（模块差异） | API 超时秒数 |
| `cache_enabled_{module}` | bool | `true` | 是否启用缓存。关闭后每次生成都重新调用 API |
| `output_brief_{module}` | bool | `false` | 精简模式：`true` 时输出 ≤200 字（global_macro）或 ≤300 字（其余模块）。**批量模式（news_correlation）不支持** |
| `thinking_enabled_{module}` | bool | 模块差异 | 是否开启 Extended Thinking（Claude / DeepSeek / Gemini 2.5） |
| `thinking_budget_{module}` | int | 4000~16000（模块差异） | **Claude / Gemini 2.5** Thinking token 预算。API 硬约束须 ≥ `max_tokens` + 1024，代码自动补足 |
| `reasoning_effort_{module}` | string / null | `"high"` | **仅 DeepSeek** 推理深度：`"low"` / `"medium"` / `"high"` / `"max"` |

> 各模块默认值差异详见下方「各模块推荐参数值」表。

---

### 事实校验容差配置

`fact_check` 段控制 LLM 生成内容中数值的自动校验和修正逻辑，用于检测并纠正 LLM 在报告中提到的收益率、占比、排名等数值与实际数据的偏差。

```json
"fact_check": {
  // 全局数值偏差容差（百分点），默认 1.0
  "tolerance": 1.0,
  // 按模块覆盖容差（模块名 → 百分点）
  "tolerance_overrides": {
    "expert_review": 2.0,
    "health_check": 1.0,
    "global_macro": 1.0,
    "penetration_deep": 1.0
  }
}
```

| 配置键 | 类型 | 默认值 | 说明 |
|--------|:----:|:------:|------|
| `tolerance` | float | `1.0` | 全局数值偏差容差（百分点）。LLM 输出的百分比数值与真实值偏差在 ±tolerance 百分点内即视为通过校验，超出则被标记为"疑似幻觉"并触发自动修正 |
| `tolerance_overrides` | dict | 见默认值 | 按模块覆盖容差。key 为模块名（`expert_review` / `health_check` / `global_macro` / `penetration_deep`），value 为该模块专用的容差值。未在 override 中列出的模块使用全局 `tolerance` |

**工作原理**：
1. LLM 模块生成报告后，事实校验器扫描 HTML 中的百分比数值
2. 将每个数值与持仓数据的真实值对比（如持仓收益率、组合占比等）
3. 偏差 ≤ `tolerance`（或模块对应的 override 值）→ 标记为绿色 ✅ 通过
4. 偏差 > 容差 → 标记为红色 ❌ 疑似幻觉，并用真实值自动替换错误数值
5. 批量修正后，报告末尾追加一段"事实校验"摘要（显示修正前后的对比）

**推荐配置**：
- **`expert_review`（智囊团深度复盘）= 2.0**：该模块综合判断较多，LLM 可能对收益率进行"约数"表述（如"约 15%"而非精确的 14.7%），给予更宽松容差可减少误报
- **`health_check` / `global_macro` / `penetration_deep` = 1.0**：这些模块数值引用较少，1 个百分点已足够宽松
- 若发现某模块频繁误报"通过"的数值，可适当降低该模块容差；反之频繁误标"疑似幻觉"时可适当提高

> **注意**：容差以百分点为单位，非百分比。例如 `tolerance: 1.0` 表示 LLM 说"15%"而真实值为 14.0%~16.0% 之间均算通过。修正操作仅在偏差超过容差时触发，并自动将错误数值替换为真实值。

---

<details>
<summary><b>📄 llm_settings.json 完整参考</b>（点击展开）</summary>

以下为 `llm_settings.json` 的完整配置范例，含中文注释分组：

```json
{
  // ═══════════════════════════════════════════
  // 全局设置
  // ═══════════════════════════════════════════
  "max_retries": 2,
  "llm_max_concurrency": 3,

  // ═══════════════════════════════════════════
  // 模块开关 — 控制各 LLM 分析功能的启用/停用
  // ═══════════════════════════════════════════
  "enabled_llm": {
    "global_macro": true,
    "expert_review": true,
    "health_check": true,
    "penetration_deep": true,
    "news_correlation": false
  },

  // ═══════════════════════════════════════════
  // 全球政经局势 — global_macro
  // ═══════════════════════════════════════════
  "system_prompt_global_macro": null,
  "model_global_macro": null,
  "temperature_global_macro": 0.3,
  "max_tokens_global_macro": 2048,
  "timeout_global_macro": 60,
  "cache_enabled_global_macro": true,
  "output_brief_global_macro": false,
  "thinking_enabled_global_macro": false,
  "thinking_budget_global_macro": 4000,
  "reasoning_effort_global_macro": "high",

  // ═══════════════════════════════════════════
  // 智囊团深度复盘 — expert_review
  // ═══════════════════════════════════════════
  "system_prompt_expert_review": null,
  "model_expert_review": null,
  "temperature_expert_review": 0.3,
  "max_tokens_expert_review": 20000,
  "timeout_expert_review": 120,
  "cache_enabled_expert_review": true,
  "output_brief_expert_review": false,
  "thinking_enabled_expert_review": true,
  "thinking_budget_expert_review": 16000,
  "reasoning_effort_expert_review": "medium",

  // ═══════════════════════════════════════════
  // 持仓体检报告 — health_check
  // ═══════════════════════════════════════════
  "system_prompt_health_check": null,
  "model_health_check": null,
  "temperature_health_check": 0.1,
  "max_tokens_health_check": 16000,
  "timeout_health_check": 120,
  "cache_enabled_health_check": true,
  "output_brief_health_check": false,
  "thinking_enabled_health_check": true,
  "thinking_budget_health_check": 12000,
  "reasoning_effort_health_check": "medium",

  // ═══════════════════════════════════════════
  // 穿透深度分析 — penetration_deep
  // ═══════════════════════════════════════════
  "system_prompt_penetration_deep": null,
  "model_penetration_deep": null,
  "temperature_penetration_deep": 0.1,
  "max_tokens_penetration_deep": 8192,
  "timeout_penetration_deep": 90,
  "cache_enabled_penetration_deep": true,
  "output_brief_penetration_deep": false,
  "thinking_enabled_penetration_deep": false,
  "thinking_budget_penetration_deep": 8000,
  "reasoning_effort_penetration_deep": "high",

  // ═══════════════════════════════════════════
  // 财经新闻热点与持仓关联分析 — news_correlation
  // （注：news_correlation 不支持 output_brief 模式）
  // ═══════════════════════════════════════════
  "system_prompt_news_correlation": null,
  "model_news_correlation": null,
  "temperature_news_correlation": 0.1,
  "max_tokens_news_correlation": 2000,
  "timeout_news_correlation": 60,
  "cache_enabled_news_correlation": true,
  "thinking_enabled_news_correlation": false,
  "thinking_budget_news_correlation": 4000,
  "reasoning_effort_news_correlation": "high",
  "news_correlation_top_n": 30,

  // ═══════════════════════════════════════════
  // 辩论模式（实验功能，缺省关闭）
  // 通过 Feature Flag 控制启停，菜单 [S] 可交互开关
  // ═══════════════════════════════════════════
  "debate": {
    // 正反辩论 — 三段式(白脸→黑脸→综合)
    "procon": {
      "per_call_max_tokens": null,
      "synthesis_model": null,
      "synthesis_temperature": 0.5
    },
    // 条件推理 — 情景化分析
    "conditional": {
      // 情景列表：每条含 name(情景名)/change(涨跌幅)/desc(描述)
      "scenarios": [
        {"name": "上涨", "change": 0.20, "desc": "如果未来市场上涨 20%"},
        {"name": "下跌", "change": -0.20, "desc": "如果未来市场下跌 20%"},
        {"name": "震荡", "change": 0.05, "desc": "如果未来市场窄幅震荡±5%"}
      ]
    },
    // 集中度问答 — 集中度风险问答块
    "qa_concentration": {
      "threshold": 0.20
    },
    // 单次报告辩论模式总 token 预算上限（超出后回退标准模式）
    "max_total_tokens_per_report": 16000,
    // 辩论模式单次 API 调用超时覆盖（秒）
    "per_call_timeout_override": 90
  },

  // ═══════════════════════════════════════════
  // 事实校验（fact_check）— LLM 输出数值一致性检测
  // ═══════════════════════════════════════════
  "fact_check": {
    // 全局数值偏差容差（百分点），默认 1.0
    "tolerance": 1.0,
    // 按模块覆盖容差（模块名 → 百分点）
    "tolerance_overrides": {
      "expert_review": 2.0,
      "health_check": 1.0,
      "global_macro": 1.0,
      "penetration_deep": 1.0
    }
  },

  // ═══════════════════════════════════════════
  // 计价配置
  // ═══════════════════════════════════════════
  "pricing": {
    "currency": "CNY"
  }
}
```

> 此文件支持 `//` 和 `/* */` 注释，可直接复制后按需修改。`enabled_llm.news_correlation` 默认 `false`，如需新闻 LLM 分析可改为 `true`。
</details>

---

## 各模块推荐参数值

> 以下仅列出**有差异的调优参数**。其余参数所有模块统一：`cache_enabled=true`、`output_brief=false`、`system_prompt=null`（使用内置）、`reasoning_effort="high"`（expert_review / health_check 例外，见下表）。

| 模块 | model | temperature | max_tokens | timeout | thinking_enabled | thinking_budget | reasoning_effort | output_brief_limit |
|------|:-----:|:-----------:|:----------:|:-------:|:----------------:|:---------------:|:----------------:|:------------------:|
| **全球政经局势** | null（使用默认） | **0.3**（低温保事实） | **2048** | **60s** | false | 4000 | high | **200 字** |
| **智囊团深度复盘** | null | **0.3**（低温保事实） | **20000** | **120s** | **true** ⭐ | 16000 | **medium** | 300 字 |
| **持仓体检报告** | null | **0.1**（极低温保数值精确） | **16000** | **120s** | **true** | 12000 | **medium** | 300 字 |
| **穿透深度分析** | null | **0.1**（极低温保数值精确） | **8192** | **90s** | false | 8000 | high | 300 字 |
| **财经新闻关联分析** | null（可换轻量模型降成本） | **0.1**（极低温保 JSON） | **2000** | **60s** | false | 4000 | high | 不适用 |

> **补充**：财经新闻关联分析还支持 `news_correlation_top_n` 配置项（默认 `30`），控制送 LLM 分析的新闻条数上限，按关键词匹配数降序选取。增大此值会线性增加 Token 消耗，减小则降低 LLM 关联分析的覆盖率。设为 `0` 可完全禁用 LLM 分析（仅保留关键词匹配）。

> **temperature 项说明**：
> - **低温（≤0.3）**：输出稳定可预测，适合事实性分析和结构化 JSON。**智囊团深度复盘/持仓体检/穿透分析使用 0.1~0.2 极低温以减少数值幻觉**。
> - **中温（0.4~0.6）**：在准确性和判断力之间平衡，适合评分分析。
> - **高温（≥0.7）**：鼓励多样性和创造性输出，适合辩论式分析。**不推荐用于数值引用类模块**。

---

## Extended Thinking

> **Claude**（provider: `"claude"`）：模型 ≥ `claude-sonnet-4` 时生效，用 `thinking.budget_tokens` 控制思考 token 预算。
>
> **DeepSeek**（provider: `"claude"` + endpoint `api.deepseek.com/anthropic`）：模型 `deepseek-v4-*` / `deepseek-chat` 时生效，用 `output_config.effort` 控制思考深度（`"low"` / `"medium"` / `"high"` / `"max"`）。
>
> **Gemini**（provider: `"gemini"`）：模型 `gemini-2.5-*` 时生效，用 `generationConfig.thinkingConfig.thinkingBudget` 控制思考 token 预算。

**[Extended Thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)** 让模型在回答前进行深度推理，大幅提升复杂分析的深度和逻辑严谨性。代价是输出 token 大幅增加（约 2~4 倍），费用相应上升。

### 配置方式

在 `llm_settings.json` 中设置（示例为 DeepSeek 全面开启智囊团深度复盘使用 Extended Thinking）：

```json
{
  "thinking_enabled_expert_review": true,
  "reasoning_effort_expert_review": "max"
}
```

或使用 Claude 模型：

```json
{
  "thinking_enabled_expert_review": true,
  "thinking_budget_expert_review": 16000
}
```

### 模型差异

| 维度 | Anthropic Claude | DeepSeek V4+ | Google Gemini 2.5 |
|------|------------------|-------------|-------------------|
| 控制参数 | `thinking.budget_tokens`（token 数量预算） | `output_config.effort`（"high"/"max" 定性控制） | `generationConfig.thinkingConfig.thinkingBudget`（token 数量预算） |
| 与 temperature 关系 | **互斥**（开启后 temperature 参数被忽略） | **互斥**（开启后 temperature 参数被忽略） | **互斥**（开启后 temperature 参数被忽略） |
| 兼容端点 | `api.anthropic.com` | `api.deepseek.com/anthropic`（Anthropic 兼容端点） | `generativelanguage.googleapis.com` |
| 推荐场景 | 预算可控，适合所有模型 | `max` 深度推荐仅用于智囊团；宏观/新闻保持 `high` | 低成本备选，适合轻量推理

### `thinking_budget` 与 `max_tokens` 的关系

**仅在使用 Claude 或 Gemini 模型时 `thinking_budget_{模块}` 有意义。** DeepSeek 使用 `reasoning_effort`（`"high"` / `"max"`）定性控制思考深度，不涉及 token 预算概念。

| 配置项 | 管什么 | expert 默认值 |
|--------|--------|:------------:|
| `max_tokens_expert_review` | **最终输出文本**的最大 token 数（DeepSeek 为 thinking + 正文共享预算） | 20000 |
| `thinking_budget_expert_review` | **内部思考过程**分配的 token 预算 | 16000 |

**API 硬性约束（仅 Claude / Gemini）：** `thinking_budget_{模块}` 的值**必须 ≥ 对应的 `max_tokens_{模块}` + 1024**。代码自动保护：若 `thinking_budget` 小于 `max_tokens + 1024`，自动补足到 `max_tokens + 4096`。若配置开启但模型不支持，自动跳过并记录 WARNING。

**一句话总结（Claude / Gemini）：** `max_tokens` 管"最终说多少"，`thinking_budget` 管"允许想多久"。
**一句话总结（DeepSeek）：** `reasoning_effort` 管"想多深"，`"max"` 对应深度分析的极致模式。

**DeepSeek V4 强制推理说明**：DeepSeek V4 系列为**强制推理模型**，即使 `thinking_enabled` 关闭也会返回 `thinking` block；且 `max_tokens` 是 **thinking + 最终文本的共享预算**（而非仅最终输出）。当思考部分耗尽预算时，响应只含 thinking block、无最终文本（即"返回空内容"场景）。

**思考耗尽自动兜底**：开启 Extended Thinking 时若出现"思考部分耗尽 max_tokens 预算"，程序会**自动关闭 thinking 同 Provider 重试一次**（`call_claude` 层安全网，日志 `关闭 thinking 重试一次，避免模块整体失败`），保证有正文产出；重试仍失败才切换下一 Provider。因此正常情况下不再因思考耗尽直接丢模块内容。

**调参建议**：若日志仍频繁出现 `LLM 输出思考部分耗尽 max_tokens 预算`，请**增大对应模块的 `max_tokens_{module}`**（DeepSeek 为 thinking + 正文共享预算，需 > `thinking_budget` + 正文余量）或**降低 `reasoning_effort_{module}`**。当前默认 expert_review 20000 / health_check 16000（对应 thinking_budget 16000/12000 + 正文余量，DeepSeek V4 输出上限 384K 无 API 拒绝风险），配合自动兜底双重保障。

### 效果参考

| 分析模块 | 关闭 thinking（token 用量） | 开启 thinking（token 用量） | 费用倍率 |
|------|:---------------------------:|:---------------------------:|:--------:|
| 智囊团深度复盘 | 输入 ~3000 / 输出 ~2000 | 输入 ~3000 / 输出 ~8000 | ~2.5× |
| 全球政经局势 | 输入 ~1500 / 输出 ~600 | 输入 ~1500 / 输出 ~2500 | ~3× |

---

## Prompt Caching（Anthropic 专属）

> 仅 `provider: "claude"` 时生效，OpenAI 提供商不适用。

代码在调用 Claude API 时自动启用 Anthropic Messages API 的 [Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) 功能。

- **生效条件**：同一 system prompt 在 **5 分钟内**重复使用
- **场景**：财经新闻热点与持仓关联分析批量处理时最有价值——5 分钟内多次调用共享缓存，**输入 token 扣费减少约 50%**
- **无感使用**：不需要任何配置项，调用 Claude API 时自动启用

---

## 支持的 provider 及配置示例

所有示例配置写入 `data/config/llm_key.json`，非敏感参数仍在 `llm_settings.json` 中管理。

<details>
<summary><b>Claude（Anthropic 官方）</b></summary>

```json
{
  "provider": "claude",
  "api_key": "sk-ant-your-key",
  "model": "claude-sonnet-4-20250514",
  "endpoint": "https://api.anthropic.com/v1/messages"
}
```

可用模型：`claude-sonnet-4-20250514`（推荐）、`claude-haiku-4-20250514`（高性价比）、`claude-opus-4-20250514`（强推理）
</details>

<details>
<summary><b>OpenAI</b></summary>

```json
{
  "provider": "openai",
  "api_key": "sk-your-key",
  "model": "gpt-4o",
  "endpoint": "https://api.openai.com/v1/chat/completions"
}
```

可用模型：`gpt-4o`（推荐）、`gpt-4o-mini`（轻量）、`o3-mini`（推理）
</details>

<details>
<summary><b>DeepSeek（Anthropic 兼容端点 — 推荐）</b></summary>

DeepSeek 官方提供 Anthropic API 兼容端点，`provider` 设为 `"claude"` 即可调用。

```json
{
  "provider": "claude",
  "api_key": "sk-your-deepseek-key",
  "model": "deepseek-v4-flash",
  "endpoint": "https://api.deepseek.com/anthropic/v1/messages"
}
```

- API Key 使用 DeepSeek 官方 Key（带 `sk-` 前缀）
- 模型：`deepseek-v4-flash`（推荐，**注意全小写**）、`deepseek-chat`（V3，功能受限）
- 官方文档：https://api-docs.deepseek.com/guides/anthropic_api
</details>

<details>
<summary><b>DeepSeek（OpenAI 兼容格式）</b></summary>

```json
{
  "provider": "openai",
  "api_key": "sk-your-deepseek-key",
  "model": "DeepSeek-V4-Flash",
  "endpoint": "https://api.deepseek.com/v1/chat/completions"
}
```
</details>

<details>
<summary><b>火山引擎（豆包）</b></summary>

```json
{
  "provider": "openai",
  "api_key": "your-volcengine-key",
  "model": "doubao-pro-32k",
  "endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
}
```

获取方式：火山引擎方舟控制台 → 推理接入点 → 创建接入点。
</details>

<details>
<summary><b>Gemini（Google）</b></summary>

```json
{
  "provider": "gemini",
  "api_key": "AIzaSyYourGeminiKey",
  "model": "gemini-2.5-flash",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
}
```

- API Key 使用 Google AI Studio 生成的 Gemini API Key
- 可用模型：`gemini-2.5-flash`（推荐，高性价比）、`gemini-2.5-pro`（强推理）
- 认证方式为 `x-goog-api-key` header，非 Bearer token
- 适用于多 Provider 链式服务中作为低成本备选
</details>

---

## HTTP 代理配置

程序默认直连 LLM API，如所在网络需要通过 HTTP 代理访问外网（如公司内网、VPN 环境），可通过环境变量配置：

### Linux / macOS

```bash
# 设置 HTTP 代理
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"

# 设置后运行程序即可
python -m src.python.tui
```

### Windows PowerShell

```powershell
# 设置 HTTP 代理
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"

# 设置后运行程序
python -m src.python.tui
```

### 注意事项

- 代理配置对所有 LLM Provider（Claude、OpenAI、DeepSeek、Gemini、火山引擎）均生效
- 代理仅影响 LLM API 调用，不影响数据源行情获取（详情数据源暂不支持代理）
- 如仅需部分 Provider 走代理，可在 `llm_providers.json` 中为该 Provider 设置 `"proxy_preferred": true`（多链模式下生效）
- 如代理认证需要用户名密码，使用 `http://user:pass@host:port` 格式
- 设置后可通过日志确认：`logs/app.log` 中搜索 `proxy` 或 `httpx.Proxy` 关键字

---

## Token 消耗参考

以下费用按 **DeepSeek-V4-Flash** 定价（¥1/M 输入、¥2/M 输出）估算，各模型单价详见「完整模型定价表」。

| 模块 | 输入 token | 输出 token | 单次费用参考 |
|------|-----------|-----------|-------------|
| 全球政经局势 | ~300-800 | ~300-600 | ~¥0.001-0.003 |
| 智囊团深度复盘 | ~800-2500 | ~1500-2500 | ~¥0.005-0.02 |
| 持仓体检报告 | ~500-1500 | ~800-1500 | ~¥0.002-0.008 |
| 穿透深度分析 | ~500-1500 | ~800-1500 | ~¥0.002-0.008 |
| 财经新闻关联分析（可选） | ~2000-4000 | ~600-1200 | ~¥0.003-0.01 |
| **五者合计（菜单 L + 新闻 LLM）** | — | — | **~¥0.01-0.05/次** |

- 仅菜单 **L** 触发 LLM 调用，E / B 不会
- LLM 结果默认缓存，缓存有效期内反复按 L 不会重复扣费
- 持仓或指数数据变更时，关联的 LLM 缓存自动失效；也可通过菜单 **[2]** 更新持仓缓存主动清除所有 LLM 缓存

---

## 完整模型定价表

代码内置所有支持模型的 Token 定价（货币单位 CNY，每百万 Token），`pricing` 段可自定义覆盖：

| 模型 | 输入 ¥/M | 输出 ¥/M | 缓存命中 ¥/M | 说明 |
|------|:--------:|:--------:|:------------:|------|
| `claude-sonnet-4-6` | 3.00 | 15.00 | 0.30 | Claude 主力模型，推荐日常使用 |
| `claude-sonnet-4-8` | 3.00 | 15.00 | 0.30 | Sonnet 升级版，同价 |
| `claude-haiku-4-5` | 0.25 | 1.25 | 0.025 | 轻量高性价比，适合批量任务 |
| `claude-opus-4-6` | 15.00 | 75.00 | 1.50 | 强推理，适合智囊团等复杂分析 |
| `claude-opus-4-8` | 15.00 | 75.00 | 1.50 | Opus 升级版，同价 |
| `claude-fable-5` | 3.00 | 15.00 | 0.30 | 最新 Claude 模型 |
| `gpt-4o` | 2.50 | 10.00 | 2.50 | OpenAI 主力（缓存无折扣） |
| `gpt-4o-mini` | 0.15 | 0.60 | 0.15 | OpenAI 轻量（缓存无折扣） |
| `deepseek-v4-flash` | 1.00 | 2.00 | 0.02 | ⭐ 高性价比推荐，默认模型 |
| `deepseek-v4-pro` | 3.00 | 6.00 | 0.025 | DeepSeek 增强推理 |
| `deepseek-chat` | 1.00 | 2.00 | 0.02 | DeepSeek V3 |

> **计算方式**：单次调用费用 = `(输入 token × 输入单价 + 输出 token × 输出单价) / 1,000,000`。例如 DeepSeek-V4-Flash：输入 3000 tokens × ¥1 + 输出 2000 tokens × ¥2 = ¥0.007/次。缓存命中时输入部分按 `input_cache_hit` 计费。
>
> **覆盖方式**：在 `llm_settings.json` 中添加 `pricing` 段即可覆盖任意模型的定价，未覆盖的模型自动使用上方内置价格：
> ```json
> "pricing": {
>   "claude-sonnet-4-6": {"input": 3, "output": 15},
>   "my-new-model": {"input": 5, "output": 10, "input_cache_hit": 0.5}
> }
> ```

---

## Token 用量统计

每次菜单 L 完成后，程序会统计本次会话的 LLM Token 消耗明细，展示在多个位置：

| 输出端 | 展示形式 | 说明 |
|:-------|:---------|:-----|
| **Excel 报告** | 独立页签 `17.LLM API 用量` | 顶部汇总区 + 下方模块明细表，状态列带条件颜色填充 |
| **HTML 报告** | 报告第 17 节（底部） | 与 Excel 格式一致 |
| **TUI 终端** | 一行摘要 | 每次菜单 L 完成时输出 |
| **调试日志** | `logs/app.log` | 每次 API 调用后记录明细 |

主要内容包括：
- **汇总数据**：API 调用次数、模型名称、输入/输出 Token 总数、缓存命中 Token、累计费用
- **模块明细**：每个 LLM 子模块的单独统计（状态、模型、Token 数、费用、是否缓存、是否开启 Thinking）
- **缓存统计**：系统数据缓存命中/未命中/总请求数/命中率
