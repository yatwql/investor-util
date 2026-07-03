# LLM 配置指引

全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析、以及可选的财经新闻热点与持仓关联分析均需调用外部 LLM API。

LLM 配置拆分为两个独立文件（v0.2.15+），分工明确：

| 文件 | 内容 | 用途 |
|------|------|------|
| `data/config/llm_key.json` | 4 个必填 + 4 个可选回退字段 | API 调用渠道（必填：provider / api_key / model / endpoint；可选：fallback_provider / fallback_api_key / fallback_endpoint / fallback_model） |
| `data/config/llm_settings.json` | 所有非敏感配置 | 参数调优（temperature、timeout、cache、system_prompt 等） |

> **为什么拆分？** `llm_key.json` 包含 API Key，可加入 `.gitignore` 避免误提交；
> `llm_settings.json` 不含密钥，可安全纳入版本控制，方便团队共享调优参数。
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

> **必填字段**：仅前 4 项（`provider` / `api_key` / `model` / `endpoint`）即可运行。`fallback_*` 回退字段可选，配置后主 provider 连续失败时自动切换，适用于高可用场景（如主用 DeepSeek 低成本、回退 Anthropic Claude 高稳定性）。非敏感参数统一移至 `llm_settings.json` 管理。

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
  "max_tokens_global_macro": 1024,
  "temperature_expert_review": 0.8,
  "max_tokens_expert_review": 8192,
  "pricing": {
    "currency": "CNY"
  }
}
```

> **注意**：
> - `system_prompt_*` 默认值为 `null`，表示使用代码内置提示词。填入字符串可覆盖。
> - 代码内置提示词定义在 `src/python/llm/prompts.py` 中（`_SYSTEM_GLOBAL_MACRO`、`_SYSTEM_EXPERT_REVIEW` 等变量），更新代码时可自动升级。
> - `pricing` 段可省略（使用代码内置定价），仅需自定义覆盖时添加，详见下方「完整模型定价表」章节。如需新增或覆盖任意模型的 Token 单价，在 `pricing` 中添加模型条目即可，未覆盖的模型自动使用内置价格。

**Step 3**：启动程序，菜单选 **L** 生成包含 LLM 分析的完整版报告。

---

## LLM 业务模块架构与公共特征

本项目目前有 5 个 LLM 业务模块（1 个可选），共享同一套生成骨架。所有模块在代码层面经过统一封装，以下特征对每个模块都适用。

### 总体架构

```
每个模块的入口函数（generate_* / enhance_*）
  → 创建闭包（指纹函数、提示词构建函数）
  → 委托 _generate_llm_module() 统一骨架
      ├── 标准模式（4 模块）：_generate_llm_content()
      │     → 缓存检查 → API 调用 → 截断重试 → Markdown→HTML → 页脚 → 缓存写入
      └── 批量模式（news_correlation）：_run_batch_mode()
            → 逐条缓存检查 → 分批(10条/批) → 线程池并行(3并发) → JSON 解析 → 逐条缓存写入
```

### 两种运行模式

| 模式 | 适用模块 | 输入 | 输出 | 页脚 |
|------|---------|------|------|------|
| **标准模式** | global_macro, expert_review, health_check, penetration_deep | 单次提示词 | HTML 文本 | 底部统一格式页脚 |
| **批量模式** | news_correlation | 多条新闻分批 | JSON 解析后合并回数据 | 无 HTML 页脚，Token 用量汇总到日志 + 会话统计 |

### 公共特征清单

所有 LLM 模块共享以下特征：

#### 1. 统一的配置项命名规则

每个模块在 `llm_settings.json` 中有 **10 个（标准模式）或 9 个（批量模式，无 output_brief）** 配置键，命名格式统一为 `{key}_{module_suffix}`（类型/默认值详见下方「模块级配置」章节）：

| 配置键 | 含义 |
|--------|------|
| `system_prompt_{module}` | 系统提示词覆盖 |
| `model_{module}` | 独立指定模型 |
| `temperature_{module}` | 温度参数 |
| `max_tokens_{module}` | 最大输出 token 数 |
| `timeout_{module}` | API 超时秒数 |
| `cache_enabled_{module}` | 是否启用缓存 |
| `output_brief_{module}` | 精简模式（≤200~300 字，**批量模式不支持**） |
| `thinking_enabled_{module}` | 是否开启 Extended Thinking |
| `thinking_budget_{module}` | Thinking token 预算（仅 Claude） |
| `reasoning_effort_{module}` | 推理深度（仅 DeepSeek） |

模块后缀名表：

| 后缀 | 中文名称 |
|------|---------|
| `global_macro` | 全球政经局势 |
| `expert_review` | 智囊团深度复盘 |
| `health_check` | 持仓体检报告 |
| `penetration_deep` | 穿透深度分析 |
| `news_correlation` | 财经新闻热点与持仓关联分析 |

#### 2. 统一的启用/停用机制

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

> 关闭的模块在报告中自动跳过，不消耗 Token。

#### 3. 指纹驱动的缓存自动失效

每个标准模块的缓存键基于**持仓数据指纹**生成，指纹成分因模块而异：

| 模块 | 指纹包含 |
|:-----|:---------|
| **全球政经局势** | 市场指数 + 总市值 + 总盈亏 + 分类 |
| **智囊团复盘/体检报告/穿透分析** | 总市值/成本/盈亏 + 每笔持仓明细 + 穿透资产 + 分类 |

指纹哈希值随数据变化而改变，缓存自动失效：

- **触发缓存的变更**：持仓数据更新、指数数据变更、穿透资产变更
- **不变更缓存的操作**：菜单 **L** 反复生成（相同指纹下直接命中缓存）
- **手动清除**：菜单 [2] 更新持仓缓存 → 所有 LLM 缓存自动失效
- **TTL 自定义**：`data/config/config.json` → `cache_ttl` → `llm_{module}` 条目

批量模式（news_correlation）除持有相同的指纹前缀外，每条新闻独立缓存键 = `标题前80字符` 的指纹与持仓指纹的联合哈希。

#### 4. 统一的 Token 用量页脚（标准模式）

所有标准模式模块生成的 HTML 内容底部自动追加统一格式页脚：

```
模型：{model} | Token 用量：输入 X / 输出 Y = Z | 估算费用：{cost} | Extended Thinking
```

其中：

- **模型** — 实际使用的模型名（模块级 `model_{module}` 或默认 model）
- **Token 用量** — 从 API 响应中提取的输入/输出 token 计数
- **估算费用** — 根据 `_estimate_cost()` 按模型定价表计算
- **Extended Thinking** — 仅当模块开启了 Extended Thinking 时追加

> 缓存命中时显示的模型名来自创建缓存时的模型，页脚变为灰字小号提示。

**展示位置**：
- HTML 报告：在章节内容末尾自动追加（`<p style="color:#888;font-size:12px">`）
- Excel 报告：在页签底部单元格显示
- TUI 输出框：在框内最后一行显示

#### 5. 会话级用量统计与报告展示

每次 LLM 调用完成后，Token 用量自动累计到会话级统计字典 `_session_usage`（代码：`src/python/llm/session.py`）。该字典受线程锁保护，支持多模块并发生成时的并发写入。

**数据结构：**

```
全局累计
├── input_tokens        — 累计输入 token
├── output_tokens       — 累计输出 token
├── cache_hit_tokens    — 累计缓存命中 token
├── total_cost          — 累计估算费用
├── call_count          — API 调用次数（缓存命中不计入）
├── models              — 去重模型列表
│
按模块汇总（per_module）
├── global_macro        — 全球政经局势
├── expert_review       — 智囊团深度复盘
├── health_check        — 持仓体检报告（v0.2.29+）
├── penetration_deep    — 穿透深度分析（v0.2.30+）
└── news_correlation    — 新闻 LLM 关联分析（可选）
```

每个 `per_module` 条目包含以下字段（来自 `session.py` 的 `_record_per_module()`）：

| 字段 | 类型 | 含义 |
|------|------|------|
| `model` | str | 实际调用的模型名 |
| `input_tokens` | int | 输入 token 数 |
| `output_tokens` | int | 输出 token 数 |
| `cache_hit_tokens` | int | 其中缓存命中的 token 数 |
| `cost` | float | 估算费用 |
| `cached` | bool | 是否命中缓存 |
| `thinking` | bool | 是否开启 Extended Thinking |
| `endpoint` | str | API 端点 |

**覆盖范围说明：**
- 会话级统计包含全部 5 个 LLM 子模块（1 个可选），其中 `news_correlation` 仅在 `enabled_llm.news_correlation = true` 时计入
- 缓存命中：仅记录到 `per_module`（标记 `cached=True`），不计入 `call_count`
- API 失败：不记录到统计中（失败不计费，也不计入调用次数）
- 模块已禁用：不产生任何统计记录

**输出链路：**

此统计数据在多个位置展示：

| 输出端 | 展示形式 | 说明 |
|:-------|:---------|:-----|
| **Excel 报告** | 独立页签 `12.LLM API 用量`（放至最右侧）；汇总页（Sheet 1）底部追加一行摘要，显示调用次数和总费用 | 仅菜单 L |
| **HTML 报告** | 报告第 12 节（底部） | 仅菜单 L |
| **TUI 终端** | 一行摘要 | 每次菜单 L 完成时输出 |
| **调试日志** | `logs/app.log` | 每次 API 调用后记录明细 |

具体格式处理函数为 `format_session_usage()`，将原始数据转为可直接展示的字典（含 `call_count`、`model_display`、`cost_display`、`total_tokens` 等格式化字段）。

> 详情参见 [报告文件结构](../manuals/reports-instruction.md#llm-api-用量页签章节说明页签-12--html-第-12-节) 中"LLM API 用量页签/章节说明"章节。

#### 6. 失败降级、占位与截断重试

各模块在以下降级场景下自动显示占位文本：

各模块在以下场景下自动降级或重试：

| 场景 | 行为 | 日志 |
|------|------|------|
| `llm_key.json` 缺失或 key 为空 | 显示占位："本节内容待生成 — LLM 未配置" | INFO |
| `enabled_llm.{module}` = false | 直接跳过，不显示占位 | INFO |
| API 调用失败（网络错误/超时/返回空） | 显示占位："（本节内容生成失败）" | WARNING |
| 输出被截断（含 `... [TRUNCATED] ...`） | 自动增大 `max_tokens` 1.5× 重试一次，仍截断则记录日志提示用户手动调大 | WARNING |

> 失败原因写入模块级 `_LLM_MODULE_FAILURE` 字典，供写入层（`llm_content.py`、`html_writer.py`）读取后决定占位文本。

#### 7. `system_prompt` 配置覆盖链

系统提示词按以下优先级（高 → 低）解析：

1. `llm_settings.json` → `system_prompt_{module}` 的值（非 null）
2. 代码内置提示词（`prompts.py` 中 `_SYSTEM_{MODULE}*` 常量）

> 设为 `null` 表示回退使用代码内置提示词，升级代码时可自动获取更新。
> 查看内置提示词内容：`grep -n "_SYSTEM_" src/python/llm/prompts.py`

---

## 配置项总览

> 以下为 `llm_settings.json` 的全部配置项。`{module}` 占位符替换为具体的模块后缀（global_macro / expert_review / health_check / penetration_deep / news_correlation）。

配置分为**全局配置**和**模块级配置**两类。全局配置仅有 3 项：

- `max_retries`（int，默认 `2`）：遇到 429 或 503 时最多重试次数
- `enabled_llm`（dict，默认全部 `true`，仅 `news_correlation` 为 `false`）：各模块独立启停开关，关闭的模块在报告中自动跳过
- `pricing`（dict，默认 `{currency: "CNY"}`）：模型 Token 定价表，可省略（使用代码内置定价），仅需覆盖时添加

全局配置段在 `llm_settings.json` 中的实际写法示例：

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
  "pricing": {
    "currency": "CNY"
  }
}
```

### 模块级配置

| 配置键 | 类型 | 默认值（各模块不同） | 说明 |
|--------|:----:|:--------------------:|------|
| `system_prompt_{module}` | string / null | `null` | 系统提示词覆盖，`null`=使用代码内置 prompt |
| `model_{module}` | string / null | `null` | 独立指定本模块使用的模型，`null`=使用 `llm_key.json` 的默认 model |
| `temperature_{module}` | float | 0.1~0.8（模块差异） | 采样温度，0=确定性最高，1=最大多样性 |
| `max_tokens_{module}` | int | 1024~8192（模块差异） | 输出最大 token 数，超过时内容被截断（触发自动重试） |
| `timeout_{module}` | int | 60~120（模块差异） | API 超时秒数 |
| `cache_enabled_{module}` | bool | `true` | 是否启用缓存。关闭后每次生成都重新调用 API |
| `output_brief_{module}` | bool | `false` | 精简模式：`true` 时输出 ≤200 字（global_macro）或 ≤300 字（其余模块）。**批量模式不支持** |
| `thinking_enabled_{module}` | bool | 模块差异 | 是否开启 Extended Thinking（Claude 或 DeepSeek） |
| `thinking_budget_{module}` | int | 4000~16000（模块差异） | **仅 Claude** Thinking token 预算。自动兜底 ≥ `max_tokens` + 4096 |
| `reasoning_effort_{module}` | string / null | `"high"` | **仅 DeepSeek** 推理深度：`"low"` / `"medium"` / `"high"` / `"max"` |

> **各模块默认值差异表**：详细推荐值见下方「各模块推荐参数值」章节。

<details>
<summary><b>📄 llm_settings.json 完整参考</b>（点击展开）</summary>

以下为 `llm_settings.json` 的完整配置范例，与实际生成的文件结构一致，含中文注释分组：

```json
{
  // ── 全局配置 ────────────────────────────────────────────
  "max_retries": 2,
  "enabled_llm": {
    "global_macro": true,
    "expert_review": true,
    "health_check": true,
    "penetration_deep": true,
    "news_correlation": false
  },

  // ═══════════════════════════════════════════════════════════
  // 一、全球政经局势 (global_macro)
  // ═══════════════════════════════════════════════════════════
  "system_prompt_global_macro": null,
  "model_global_macro": null,
  "temperature_global_macro": 0.3,
  "max_tokens_global_macro": 1024,
  "timeout_global_macro": 60,
  "cache_enabled_global_macro": true,
  "output_brief_global_macro": false,
  "thinking_enabled_global_macro": false,
  "thinking_budget_global_macro": 4000,
  "reasoning_effort_global_macro": "high",

  // ═══════════════════════════════════════════════════════════
  // 二、智囊团深度复盘 (expert_review)
  // ═══════════════════════════════════════════════════════════
  "system_prompt_expert_review": null,
  "model_expert_review": null,
  "temperature_expert_review": 0.8,
  "max_tokens_expert_review": 8192,
  "timeout_expert_review": 120,
  "cache_enabled_expert_review": true,
  "output_brief_expert_review": false,
  "thinking_enabled_expert_review": true,
  "thinking_budget_expert_review": 16000,
  "reasoning_effort_expert_review": "high",

  // ═══════════════════════════════════════════════════════════
  // 三、持仓体检报告 (health_check)
  // ═══════════════════════════════════════════════════════════
  "system_prompt_health_check": null,
  "model_health_check": null,
  "temperature_health_check": 0.5,
  "max_tokens_health_check": 4096,
  "timeout_health_check": 120,
  "cache_enabled_health_check": true,
  "output_brief_health_check": false,
  "thinking_enabled_health_check": true,
  "thinking_budget_health_check": 12000,
  "reasoning_effort_health_check": "high",

  // ═══════════════════════════════════════════════════════════
  // 四、穿透深度分析 (penetration_deep)
  // ═══════════════════════════════════════════════════════════
  "system_prompt_penetration_deep": null,
  "model_penetration_deep": null,
  "temperature_penetration_deep": 0.4,
  "max_tokens_penetration_deep": 4096,
  "timeout_penetration_deep": 90,
  "cache_enabled_penetration_deep": true,
  "output_brief_penetration_deep": false,
  "thinking_enabled_penetration_deep": false,
  "thinking_budget_penetration_deep": 8000,
  "reasoning_effort_penetration_deep": "high",

  // ═══════════════════════════════════════════════════════════
  // 五、财经新闻与持仓关联分析 (news_correlation)
  // ═══════════════════════════════════════════════════════════
  "system_prompt_news_correlation": null,
  "model_news_correlation": null,
  "temperature_news_correlation": 0.1,
  "max_tokens_news_correlation": 2000,
  "timeout_news_correlation": 60,
  "cache_enabled_news_correlation": true,
  "thinking_enabled_news_correlation": false,
  "thinking_budget_news_correlation": 4000,
  "reasoning_effort_news_correlation": "high",

  // ═══════════════════════════════════════════════════════════
  // 六、计价 (pricing)
  // ═══════════════════════════════════════════════════════════
  "pricing": {
    "currency": "CNY"
  }
}
```

> 此文件支持 `//` 和 `/* */` 注释，可直接复制后按需修改。`enabled_llm.news_correlation` 默认 `false`，如需新闻 LLM 分析可改为 `true`。
</details>

---

## 各模块推荐参数值

> 以下仅列出**有差异的调优参数**。其余参数所有模块统一：`cache_enabled=true`、`output_brief=false`、`system_prompt=null`（使用内置）、`reasoning_effort="high"`。完整参数说明见上方「模块级配置」表。

| 模块 | model | temperature | max_tokens | timeout | thinking_enabled | thinking_budget | output_brief_limit |
|------|:-----:|:-----------:|:----------:|:-------:|:----------------:|:---------------:|:------------------:|
| **全球政经局势** | null（使用默认） | **0.3**（低温保事实） | **1024** | **60s** | false | 4000 | **200 字** |
| **智囊团深度复盘** | null | **0.8**（高温促多元） | **8192** | **120s** | **true** ⭐ | 16000 | 300 字 |
| **持仓体检报告** | null | **0.5**（居中平衡） | **4096** | **120s** | **true** | 12000 | 300 字 |
| **穿透深度分析** | null | **0.4**（中低温稳定） | **4096** | **90s** | false | 8000 | 300 字 |
| **财经新闻关联分析** | null（可换轻量模型降成本） | **0.1**（极低温保 JSON） | **2000** | **60s** | false | 4000 | 不适用（批量模式） |

> **temperature 项说明**：
> - **低温（≤0.3）**：输出稳定可预测，适合事实性分析和结构化 JSON。**>0.5 时全球政经局势可能编造经济指标**。
> - **中温（0.4~0.6）**：在准确性和判断力之间平衡，适合评分分析。
> - **高温（≥0.7）**：鼓励多样性和创造性输出，适合辩论式分析。**<0.4 时智囊团专家观点雷同**。
>
> **Extended Thinking 说明**：批量模式（news_correlation）不支持开启 Thinking——JSON 格式任务不需要深度推理。

---

## Extended Thinking

> **Claude**（provider: `"claude"`）：模型 ≥ `claude-sonnet-4` 时生效，用 `thinking.budget_tokens` 控制思考 token 预算。
>
> **DeepSeek**（provider: `"claude"` + endpoint `api.deepseek.com/anthropic`）：模型 `deepseek-v4-*` / `deepseek-chat` 时生效，用 `output_config.effort` 控制思考深度（`"high"` / `"max"`）。

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

| 维度 | Anthropic Claude | DeepSeek V4+ |
|------|------------------|-------------|
| 控制参数 | `thinking.budget_tokens`（token 数量预算） | `output_config.effort`（"high"/"max" 定性控制） |
| 与 temperature 关系 | **互斥**（开启后 temperature 参数被忽略） | **互斥**（开启后 temperature 参数被忽略） |
| 兼容端点 | `api.anthropic.com` | `api.deepseek.com/anthropic`（Anthropic 兼容端点） |
| 推荐场景 | 预算可控，适合所有模型 | `max` 深度推荐仅用于智囊团；宏观/新闻保持 `high` |
| 降级策略 | 模型不支持时自动跳过，记录 WARNING | 模型不支持时自动跳过，记录 WARNING |

### `thinking_budget` 与 `max_tokens` 的关系

**仅在使用 Claude 模型时 `thinking_budget_{模块}` 有意义。** DeepSeek 使用 `reasoning_effort`（`"high"` / `"max"`）定性控制思考深度，不涉及 token 预算概念。

| 配置项 | 管什么 | expert 默认值 |
|--------|--------|:------------:|
| `max_tokens_expert_review` | **最终输出文本**的最大 token 数 | 8192 |
| `thinking_budget_expert_review` | **内部思考过程**分配的 token 预算 | 16000 |

模型先消耗 `thinking_budget` 做内部推理（该部分不可见），再从剩余额度里吐出最终回答（不超过 `max_tokens`）：

```
┌─── thinking_budget_expert_review: 16000 ────────────────┐
│  ┌── 模型内部思考 ──┐  ┌── 最终输出 ──────────┐       │
│  │  ~8000 tokens    │  │  ~3000 tokens (可见)  │       │
│  │  (不可见，不计入  │  │  ≤ max_tokens=8192   │       │
│  │   输出 token)     │  │                      │       │
│  └──────────────────┘  └──────────────────────┘       │
│                   总计 ~11000 tokens（API 按此计价）    │
└───────────────────────────────────────────────────────┘
```

**API 硬性约束（仅 Claude）：** `thinking_budget_{模块}` 的值**必须 ≥ 对应的 `max_tokens_{模块}` + 1024**。默认值已满足：

- `max_tokens_global_macro=1024` → `thinking_budget_global_macro` 至少 2048（默认 4000 ✅）
- `max_tokens_expert_review=8192` → `thinking_budget_expert_review` 至少 9216（默认 16000 ✅）

**代码自动保护：**
- 若 `thinking_budget` 小于 `max_tokens + 1024`，自动补足到 `max_tokens + 4096`。
- 若配置开启但模型不支持（如 `claude-sonnet-3-5`），自动跳过并记录 WARNING。

**一句话总结（Claude）：** `max_tokens` 管"最终说多少"，`thinking_budget` 管"允许想多久"。
**一句话总结（DeepSeek）：** `reasoning_effort` 管"想多深"，`"max"` 对应深度分析的极致模式。

### 效果参考

| 分析模块 | 关闭 thinking（token 用量） | 开启 thinking（token 用量） | 费用倍率 |
|------|:---------------------------:|:---------------------------:|:--------:|
| 智囊团深度复盘 | 输入 ~3000 / 输出 ~2000 | 输入 ~3000 / 输出 ~8000 | ~2.5× |
| 全球政经局势 | 输入 ~1500 / 输出 ~600 | 输入 ~1500 / 输出 ~2500 | ~3× |

---

## Prompt Caching（Anthropic 专属）

> 仅 `provider: "claude"` 时生效，OpenAI 提供商不适用。

代码在 `_call_claude()` 中自动启用 Anthropic Messages API 的 [Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) 功能。system prompt 以数组格式发送并标注 `cache_control: ephemeral`：

- **生效条件**：同一 system prompt 在 **5 分钟内**重复使用
- **场景**：财经新闻热点与持仓关联分析批量处理时最有价值——5 分钟内多次调用共享缓存，**输入 token 扣费减少约 50%**
- **效果**：费用按 `cache_creation_tokens`（写入缓存）× 1.25 + `cache_read_tokens`（命中缓存）× 0.1 计价，远低于全价输入 token
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
- 模型：`deepseek-v4-flash`（推荐，**注意全小写**，当前主版本）、`deepseek-chat`（V3 旧版，功能受限）
- ⚠️ **模型名大小写敏感**：代码中以全小写前缀匹配（如 `deepseek-v4-`），`DeepSeek-V4-Flash` 等大小写混合写法会导致 Extended Thinking 等功能无法识别，请统一使用小写
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

---

## Token 消耗参考

以下费用按 **DeepSeek-V4-Flash** 定价（¥1/M 输入、¥2/M 输出）估算，各模型单价详见下方「完整模型定价表」。

| 模块 | 输入 token | 输出 token | 单次费用参考 |
|------|-----------|-----------|-------------|
| 全球政经局势 | ~300-800 | ~300-600 | ~¥0.001-0.003 |
| 智囊团深度复盘 | ~800-2500 | ~1500-2500 | ~¥0.005-0.02 |
| 持仓体检报告 | ~500-1500 | ~800-1500 | ~¥0.002-0.008 |
| 穿透深度分析 | ~500-1500 | ~800-1500 | ~¥0.002-0.008 |
| 财经新闻关联分析（可选） | ~2000-4000 | ~600-1200 | ~¥0.003-0.01 |
| **五者合计（菜单 L + 新闻 LLM）** | — | — | **~¥0.01-0.05/次** |

- 仅菜单 **L** 触发 LLM 调用，E / N / H / B 不会
- LLM 结果默认缓存，缓存有效期内反复按 L 不会重复扣费
- 持仓或指数数据变更时，关联的 LLM 缓存自动失效；也可通过菜单 [2] 更新持仓缓存主动清除所有 LLM 缓存

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
| `deepseek-chat` | 1.00 | 2.00 | 0.02 | DeepSeek V3 旧版 |

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

## 新增 LLM 服务章节规范

增加新的 LLM 服务章节时，共同的注册/配置/生成/写入步骤见 **[how-to-use-registry.md → 新增 LLM 模块检查清单](how-to-use-registry.md#新增-llm-模块检查清单)**（共 7 步，含注册表测试和标记合规验证）。在 registry 清单基础上，补充以下本领域特有的步骤：

| # | 步骤 | 操作位置 | 产出 |
|---|------|---------|------|
| ① | **添加系统提示词** | `llm/prompts.py` | 新增 `_SYSTEM_{MODULE}` 常量和提示词构建函数 |
| ② | **适配报告模板** | `report/html_writer.py`（HTML）+ `report/llm_content.py`（Excel） | 新章节在两种报告中正确渲染 |
| ③ | **配置缓存 TTL** | `data/config/config.json` → `cache_ttl` | 添加 `llm_{module}` 条目 |
| ④ | **更新用户文档** | `data/config/llm_settings.json`（推荐默认值）+ 本文档（模块说明） | 用户可查阅和配置 |
