# LLM 集成层技术设计

> 文档版本：v0.6.1

## 目录

- [1. 总体架构](#1-总体架构)
- [2. 模块清单](#2-模块清单)
- [3. 骨架流程](#3-骨架流程)
- [4. 并行编排](#4-并行编排)
- [5. API 调用层](#5-api-调用层)
- [6. 重试与容错体系](#6-重试与容错体系)
- [7. 缓存与指纹失效](#7-缓存与指纹失效)
- [8. 提示词管理](#8-提示词管理)
- [9. 会话级 Token 追踪](#9-会话级-token-追踪)
- [10. 模型定价](#10-模型定价)
- [11. 熔断器](#11-熔断器)
- [12. 配置与注册](#12-配置与注册)
- [13. 集成点](#13-集成点)

---

## 1. 总体架构

`src/python/llm/` 包分为 **入口层 → 编排层 → 骨架层 → API 层** 四层，外加共享工具模块：

```
                               主流程入口
                          handlers_report.py
                                │
                                ▼
                    ┌─────────────────────────┐
                    │  generators_orchestrator │  ← 编排层（4+1 模块并行调度）
                    │  .py                     │
                    └───────────┬─────────────┘
                                │ generate_all_llm()
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
         ▼                      ▼                      ▼
  ┌────────────────┐  ┌──────────────────┐  ┌────────────────────┐
  │ generators.py  │  │ generators_news  │  │ skeleton.py        │ ← 骨架层
  │                │  │ .py              │  │                    │
  │ 4 个单例生成   │  │ LLM 增强新闻关联 │  │ _generate_llm_     │
  │ 函数           │  │ enhance_news_    │  │ module()           │
  │                │  │ correlation()    │  │                    │
  └───────┬────────┘  └────────┬─────────┘  │ _run_standard_mode │
          │                    │             │ _run_batch_mode    │
          │                    │             └───────┬────────────┘
          │                    │                     │ _generate_llm_content()
          └──────────┬─────────┘                     │
                     │                               ▼
                     │                      ┌────────────────┐
                     │                      │  api.py        │ ← API 路由层
                     │                      │ _call_llm()    │
                     │                      │ 路由 provider  │
                     │                      └───────┬────────┘
                     │                              │
                     │                              ▼
                     │                      ┌────────────────┐
                     │                      │  api_base.py   │ ← 底层调用层
                     │                      │                │
                     │                      │ _attempt_api_  │
                     │                      │ call()         │
                     │                      │                │
                     │                      │ _call_llm_with │
                     │                      │ _retry()       │
                     │                      │                │
                     │                      │ 重试骨架       │
                     │                      │ 截断检测       │
                     │                      │ 失败追踪       │
                     │                      └────────────────┘
                     │
                     ├──────────── 共享工具层 ────────────┐
                     │                                    │
                     ▼                                    ▼
              ┌──────────────┐              ┌────────────────────┐
              │ prompts.py   │              │ fingerprint.py     │
              │ System/User  │              │ 缓存指纹计算       │
              │ Prompt 模板  │              │ 稳定性字段提取      │
              └──────────────┘              └────────────────────┘
              ┌──────────────┐              ┌────────────────────┐
              │ session.py   │              │ pricing.py         │
              │ 会话用量累计  │              │ 模型定价/费用估算  │
              └──────────────┘              └────────────────────┘
              ┌──────────────┐              ┌────────────────────┐
              │ markdown.py  │              │ circuit_breaker.py │
              │ MD→HTML 转换 │              │ LLM 端点熔断器      │
              └──────────────┘              └────────────────────┘
```

**调用链（API 调用流程）**：

```
skeleton.py:_generate_llm_content()
    │  ① 缓存检查 → 命中直接返回
    │  ② _call_llm()
    │      └─ api.py:_call_llm()
    │             │  路由 provider → _call_claude() / _call_openai()
    │             │  ③ 内容过滤安抚重试（空返回时）
    │             │  ④ 回退 provider（主 provider 失败时）
    │             └─ api_base.py:_call_llm_with_retry()
    │                    │  熔断预检 → 熔断中则直接返回
    │                    │  循环 attempt=0..max_retries:
    │                    │    _attempt_api_call() → HTTP POST
    │                    │    成功 → _process_success_response()
    │                    │           → _extract_content()
    │                    │           → 截断检测
    │                    │           → _log_token_usage()
    │                    │           → _track_session_usage()
    │                    │    可重试 → sleep → retry
    │                    │    致命 → 记录失败原因 → 返回
    │                    └→ _cb_record_failure/success()
    │  ③ _handle_truncation() → 截断检测 → 自动重试 max_tokens×1.5
    │  ④ _finalize_and_cache()
    │        → markdown_to_html()
    │        → 拼接模型/用量/费用页脚
    │        → cache_set()
    │        → _record_per_module()
    └── 返回 (html, from_cached)
```

[↑ 回到顶部](#目录)

---

## 2. 模块清单

### 2.1 12 子模块总览

| 模块 | 分类 | 职责 | 入口函数 |
|:-----|:-----|:------|:---------|
| `generators_orchestrator.py` | 编排层 | 4+1 模块并行调度，缓存预检查，线程池分发 | `generate_all_llm()` |
| `generators.py` | 生成层 | 4 个单例生成函数（global_macro / expert_review / health_check / penetration_deep） | 各 `generate_*()` |
| `generators_news.py` | 生成层 | 新闻 LLM 二次关联分析（批量模式 7 函数） | `enhance_news_correlation()` |
| `skeleton.py` | 骨架层 | 标准模式 + 批量模式共享生成骨架（85% 公共逻辑） | `_generate_llm_module()` |
| `api.py` | API 层 | Provider 路由（Claude/OpenAI）、Extended Thinking 注入 | `_call_llm()` |
| `api_base.py` | 基础设施 | HTTP 调用、重试骨架、截断检测、Token 日志、失败追踪 | `_call_llm_with_retry()` |
| `prompts.py` | 工具 | System/User Prompt 模板、持仓明细格式化、差异上下文 | 各 `_build_*_prompt()` |
| `fingerprint.py` | 工具 | LLM 缓存指纹计算、稳定性字段提取、TTL 查询 | `_compute_fingerprint()` |
| `session.py` | 工具 | 会话级 Token 累计、模块级记录、格式化输出 | `reset_session_usage()` |
| `pricing.py` | 工具 | 模型定价合并、费用估算 | `_estimate_cost()` |
| `circuit_breaker.py` | 工具 | LLM 端点熔断器（3 次/60s） | `_cb_is_open()` |
| `markdown.py` | 工具 | Markdown→HTML 转换 | `_markdown_to_html()` |

### 2.2 四大+一模块详情

#### 标准模式模块（4 个，通过 `_generate_llm_module` 以标准模式调用）

| 模块键 | 名称 | 默认 max_tokens | 默认 timeout | 默认 TTL | 默认 system_prompt |
|:-------|:-----|:---------------:|:------------:|:--------:|:-------------------|
| `global_macro` | 全球政经局势 | 800 | 60s | 24h（86400s） | 宏观经济学家角色，500 字内，纯文本 |
| `expert_review` | 智囊团深度复盘 | 8192 | 120s | 2h（7200s） | 召集令→圆桌会→定音锤三阶段 |
| `health_check` | 持仓体检报告 | 4096 | 120s | 24h（86400s） | 四维度评分（风险分散度/流动性/收益合理性/成本结构） |
| `penetration_deep` | 穿透深度分析 | 4096 | 90s | 24h（86400s） | 行业/品种集中度+国别暴露 |

#### 批量模式模块（1 个，通过 `_generate_llm_module` 以批量模式调用）

| 模块键 | 名称 | 默认 max_tokens | 默认 timeout | 默认 TTL | 默认 system_prompt |
|:-------|:-----|:---------------:|:------------:|:--------:|:-------------------|
| `news_correlation` | 新闻 LLM 关联分析 | 4096 | 120s | 1h（3600s） | 逐批分析新闻与持仓关联性（JSON 输出） |

**批量模式 vs 标准模式区别**：

| 特性 | 标准模式 | 批量模式 |
|:-----|:---------|:---------|
| 用途 | 生成单篇完整分析 | 逐条分析新闻（N 条→分批→LLM→JSON 解析） |
| 返回类型 | `(str\|None, bool)` — HTML 文本 + 缓存标志 | `(dict, bool, dict, int)` — 结果映射 + 全缓存标志 + Token + 计数 |
| 缓存粒度 | 整篇一个缓存文件 | 每条新闻独立缓存，`per_item_cache_fn` 构建每条的 cache_key |
| 并行粒度 | `ThreadPoolExecutor` 每模块一个线程 | 分批后 `ThreadPoolExecutor` 每批一个线程（最多 3 批并行） |
| 响应解析 | 文本直接 Markdown→HTML | `response_parser` 从 JSON 数组中提取每条结果 |
| 失败容忍 | 模块整体跳过 | 单批失败不影响其他批次 |

[↑ 回到顶部](#目录)

---

## 3. 骨架流程

### 3.1 `_generate_llm_module()` — 两路分支

```
_generate_llm_module(llm_config, module_key, *hooks)
    │
    ├── llm_config is None → get_llm_config() 尝试读取配置
    │      └── 仍为 None → 返回 None（未配置）
    │
    ├── _is_llm_module_enabled() → False
    │      └── 返回 None（已禁用），记录 _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_DISABLED
    │
    ├── batch_preparer is not None  → _run_batch_mode()（批量模式）
    │
    └── 标准模式 → _run_standard_mode()
```

### 3.2 `_run_standard_mode()` — 标准模式流程

```
_run_standard_mode()
    │
    ▼
┌──────────────────────────────┐
│ 读取缓存配置                 │
│ cache_enabled = llm_config   │
│ .get("cache_enabled_{key}")  │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 计算指纹                     │
│ fingerprint = fingerprint_fn │
│ () or ""                     │
│ cache_key = "llm_{key}_" +   │
│            fingerprint       │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 构建 System Prompt           │
│ system_prompt = llm_config   │
│ .get("system_prompt_{key}")  │
│ or default                   │
│                              │
│ 精简模式检测:                │
│ output_brief_{key}=true →    │
│ 追加 "精简模式" 约束          │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 构建 User Prompt             │
│ user_prompt = prompt_builder │
│ ()                           │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ _generate_llm_content()              │
│                                      │
│ ┌─────────────────────────────────┐  │
│ │ ① 缓存检查                      │  │
│ │ cache_enabled AND not force?   │  │
│ │ YES → cache_get(key, ttl)       │  │
│ │   命中 → _handle_cache_hit()    │  │
│ │          记录 per_module        │  │
│ │          (cached=True)          │  │
│ │         返回 (cached_html, True)│  │
│ │ 未命中 → 继续                   │  │
│ └──────────────┬──────────────────┘  │
│                │                      │
│ ┌──────────────▼──────────────────┐  │
│ │ ② _call_llm()                   │  │
│ │ 清除上次失败原因                  │  │
│ │ → 主 provider API 调用           │  │
│ │ → 内容过滤安抚重试                │  │
│ │ → 回退 provider                  │  │
│ └──────────────┬──────────────────┘  │
│                │                      │
│ ┌──────────────▼──────────────────┐  │
│ │ ③ _handle_truncation()          │  │
│ │ result 含截断标记?               │  │
│ │ YES → max_tokens × 1.5 重试一次  │  │
│ │ 二次截断则保留第一次结果+警告      │  │
│ └──────────────┬──────────────────┘  │
│                │                      │
│ ┌──────────────▼──────────────────┐  │
│ │ ④ _finalize_and_cache()         │  │
│ │ markdown_to_html() → 判空       │  │
│ │ → 拼接模型/用量/费用页脚         │  │
│ │ → cache_set()                   │  │
│ │ → _record_per_module()          │  │
│ │ 返回 (html, False)              │  │
│ └─────────────────────────────────┘  │
└──────────────────────────────────────┘
```

### 3.3 `_run_batch_mode()` — 批量模式流程

```
_run_batch_mode(llm_config, module_key, *hooks)
    │
    ▼
┌───────────────────────────────────────────┐
│ 准备阶段                                   │
│ items, context_fp = batch_preparer()       │
│ 逐条检查缓存: _check_batch_caches()         │
│  → results_map: idx→cached_result         │
│  → item_cache_keys: idx→cache_key         │
│  → uncached_indices: 需调用 API 的索引列表   │
│  → cached_count, all_cached               │
└──────────────────┬────────────────────────┘
                   │
             有未缓存项?
        ┌───────┴───────┐
       YES               NO
        │                 │
        ▼                 ▼
┌─────────────────┐  ┌─────────────────┐
│ 分批 (BATCH_    │  │ 全部缓存命中     │
│ SIZE=10)        │  │ 直接返回结果     │
│ 提交线程池       │  │ all_cached=True │
│ (max_workers=   │  └─────────────────┘
│ min(3, batches))│
│                 │
│ 每批:            │
│  _execute_and_  │
│  _merge_batch() │
│  → batch_prompt │
│    _fn(items)   │
│  → _call_llm()  │
│  → response_    │
│    parser()     │
│  → cache_set()  │
│  → accumulate   │
│    tokens       │
└────────┬────────┘
         │
         ▼
返回 (results_map, all_cached, token_usage, cached_count)
```

`BATCH_SIZE=10` — 每批最多 10 条新闻，控制单次 LLM 调用负载。

`max_workers=min(3, len(batches), 6)` — 最多 3 批并行，避免 API 限流。

[↑ 回到顶部](#目录)

---

## 4. 并行编排

### 4.1 `generate_all_llm()` 完整流程

```
handlers_report.py 菜单 L/B
    │
    ▼
generate_all_llm(a_indices, us_indices, total_mv, total_cost, ...)
    │
    ▼
┌──────────────────────────────────────┐
│ ① 读取配置 (get_llm_config())        │
│ 若 None → 返回 (None, None, ...)     │
│                                      │
│ ② 预计算所有模块指纹+缓存键+TTL       │
│ _compute_module_cache_info()         │
│  → 每个模块: key, ttl, can_cache,   │
│               thinking_key           │
│                                      │
│ ③ 预检查所有模块                      │
│ _precheck_all_modules()              │
│  → 禁用?  → 记录 FAIL_REASON_DISABLED│
│  → 缓存命中? → 直接读取内容            │
│              记录 per_module(cached) │
│  → 未命中  → needs[key]=True        │
│                                      │
│ ④ 仅对 needs 中 True 的模块提交线程池  │
│ _dispatch_llm_workers(needs)         │
│  → ThreadPoolExecutor(max_workers=3) │
│  → 每个工作线程创建独立 httpx.Client  │
│    (HTTP/2 + 连接池)                 │
│  → as_completed 收集结果              │
│                                      │
│ ⑤ 合并预检结果 + 线程结果              │
│ ⑥ 返回 8 元组                         │
│ (gm_r, er_r, hc_r, pd_r,            │
│  gm_c, er_c, hc_c, pd_c)            │
└──────────────────────────────────────┘
```

### 4.2 HTTP 客户端配置

```python
_LLM_CLIENT_SETTINGS = {
    "http2": True,                          # 启用 HTTP/2 多路复用
    "limits": httpx.Limits(
        max_connections=20,                 # 总连接池上限
        max_keepalive_connections=10,       # 空闲保持连接数
    ),
}
```

每个工作线程创建**独立**的 `httpx.Client` 实例（`_make_runner` 闭包），避免全局共享连接池的线程安全问题。`h2` 包不可用时自动降级到 HTTP/1.1。

`max_workers=llm_config.llm_max_concurrency`（config 默认 3）控制并行调用数。

### 4.3 缓存预检查优化

`_dispatch_llm_workers()` 仅对缓存**未命中**的模块提交线程池任务。缓存命中的模块直接读取内容，节省线程开销。

```python
# 仅对缓存未命中且已启用的模块提交
needs = {k: (v["result"] is None and _is_llm_module_enabled(llm_config, k))
         for k, v in precheck_results.items()}

# 无需求时直接返回
if not any(needs.values()):
    return {}
```

### 4.4 f_context 注入

`f_context`（组合历史走势时间维度上下文，含 F1→F2 diff 差异摘要）可选传递给 `expert_review` 和 `health_check`，使 LLM 能感知持仓环比变化（新增/清仓/加仓/减仓品种、总市值/总盈亏变化百分比）。

首次运行（`is_first_check=True`）时输出"暂无历史对比数据"标记。

[↑ 回到顶部](#目录)

---

## 5. API 调用层

### 5.1 Provider 路由

```
_call_llm(system_prompt, user_prompt, llm_config, ...)
    │
    ├─ 读取 provider / api_key / model / endpoint / max_tokens
    │
    ├─ _call_single_provider(provider, ...)
    │      ├─ "claude" → _call_claude(system, user, ...)
    │      │                Anthropic Messages API
    │      │                + Extended Thinking 注入
    │      │                + Prompt Caching (cache_control)
    │      └─ "openai" → _call_openai(system, user, ...)
    │                       OpenAI Chat Completions API
    │                       (也兼容 DeepSeek 等 OpenAI 兼容端点)
    │
    ├─ 主 provider 成功 → 返回 (content, usage)
    │
    ├─ 主 provider 返回空内容 → 内容过滤安抚重试
    │      system_prompt += _CONTENT_FILTER_RECOVERY
    │      重试一次 → 成功则返回，失败则继续
    │
    └─ 主 provider 失败 → 尝试回退 provider
           fallback_provider / fallback_api_key /
           fallback_endpoint / fallback_model
           均失败 → 返回 (None, None)
```

#### _call_claude() 关键细节

**URL**: `{endpoint}/v1/messages`（默认 `https://api.anthropic.com/v1/messages`）

**Payload 结构**：
```python
{
    "model": model,                    # 如 "claude-sonnet-4-20250514"
    "max_tokens": max_tokens,
    "system": [{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"}  # Prompt Caching
    }],
    "messages": [{"role": "user", "content": user_prompt}],
}
```

**Extended Thinking 注入**（`_configure_extended_thinking()`）：

```
_configure_extended_thinking(payload, llm_config, config_field, model, max_tokens)
    │
    ├─ 读取 thinking_enabled_{module_suffix}
    │      False → 无操作返回
    │
    ├─ 验证模型兼容性 (_supports_extended_thinking)
    │      不兼容 → 自动降级跳过，记录 WARNING
    │
    ├─ payload["thinking"] = {"type": "enabled"}
    ├─ payload.pop("temperature", None)  ← 与 temperature 互斥
    │
    ├─ effort 模型 (DeepSeek V4+) →
    │      payload["output_config"] = {"effort": effort}
    │      effort 从 reasoning_effort_{module_suffix} 读取
    │      默认 "high"
    │
    └─ budget_tokens 模型 (Claude Sonnet 4 / Opus 4) →
           payload["thinking"]["budget_tokens"] = budget
           budget 从 thinking_budget_{module_suffix} 读取
           不足 max_tokens + 1024 时自动兜底到 max_tokens + 4096
```

#### _call_openai() 关键细节

**URL**: `{endpoint}/v1/chat/completions`（默认 `https://api.openai.com/v1/chat/completions`）

**Payload 结构**：
```python
{
    "model": model,                     # 如 "gpt-4o"
    "max_tokens": max_tokens,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
}
```

**temperature 处理**：标准模式通过 `skeleton.py` 传递 `llm_config.get("temperature_{module_key}")`；仅当 `thinking` 未启用时注入 payload。

[↑ 回到顶部](#目录)

---

## 6. 重试与容错体系

### 6.1 四层容错

```
第 1 层：熔断器（circuit_breaker.py）
    ── _call_llm_with_retry() 入口检查
    ── 连续 3 次失败 → 冷却 60s → 半开放行
    ── 熔断中直接跳过，不发起 HTTP

第 2 层：重试骨架（api_base.py）
    ── 可重试错误 (429/503/超时/网络异常) → 指数退避重试
    ── 致命错误 (JSON 解析失败) → 不重试
    ── max_retries 默认 2（可通过 llm_settings.json 配置）

第 3 层：截断自动重试（skeleton.py）
    ── 检测输出含 _TRUNCATION_MARKER
    ── max_tokens × 1.5 重试一次
    ── 二次截断则保留第一次结果 + 尾部警告

第 4 层：内容过滤安抚重试（api.py）
    ── API 返回空内容（可能被内容审查拦截）
    ── 追加安抚指令到 system prompt 尾部重试一次
    ── 安抚成功 → 返回重试结果
    ── 安抚失败 → 尝试回退 provider
```

### 6.2 指数退避延迟

```python
_RETRY_DELAYS = [1.0, 3.0, 5.0, 10.0, 15.0]
```

第 0 次重试等待 1s，第 1 次 3s，依此类推。超出 `max_retries` 后记录失败原因并返回 None。

### 6.3 失败追踪

全局变量 `_last_llm_failure_reason` 记录最近一次失败的详细原因（`FAIL_REASON_*` 常量），供骨架层区分失败类型：

| 常量 | 含义 | 触发场景 |
|:-----|:------|:---------|
| `FAIL_REASON_CIRCUIT_OPEN` | 熔断开启 | 冷却期内跳过请求 |
| `FAIL_REASON_TIMEOUT` | 请求超时 | 超过 timeout 秒数未收到响应 |
| `FAIL_REASON_NETWORK_ERROR` | 网络异常 | HTTP 错误（429/503 等） |
| `FAIL_REASON_API_ERROR` | API 响应异常 | JSON 解析失败、响应格式异常 |
| `FAIL_REASON_DISABLED` | 模块已禁用 | enabled_llm.xxx = false |
| `FAIL_REASON_NOT_CONFIGURED` | LLM 未配置 | get_llm_config() 返回 None |

每次新生成开始时 `_clear_last_llm_failure()` 清除上次失败；失败原因通过 `_LLM_MODULE_FAILURE[module_key]` 字典留存，供报告模块读取以输出具体提示。

[↑ 回到顶部](#目录)

---

## 7. 缓存与指纹失效

### 7.1 指纹计算

LLM 缓存使用指纹驱动失效机制。指纹变化时缓存自动失效，无需等待 TTL 到期。

#### `_compute_fingerprint()` — 通用确定性哈希

```python
def _compute_fingerprint(*args: Any) -> str:
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]
```

输入参数任意组合 → 确定性 MD5 → 前 12 位十六进制作为缓存键后缀。

#### `_build_llm_fingerprint()` — LLM 专用指纹构建

```
_build_llm_fingerprint(total_mv, total_cost, total_profit, total_today_profit,
                       holdings_details, penetrated_assets, categories,
                       full_penetration=False)
```

在序列化前执行稳定性字段提取：

```
holdings_details ──→ _extract_stable_holdings()
                     仅保留 {name, code, cost}
                     剔除 price/change_pct/nav_date 等行情波动字段

penetrated_assets ──→ _extract_stable_penetration()
                     默认仅保留 {name, codes}（排除行情波动）
                     full_penetration=True 时额外保留 {mv, sector, ratio}
                       （穿透深度分析需要穿透数据变化触发失效）
```

**设计目的**：`expert_review` / `health_check` / `penetration_deep` 的 `_compute_fingerprint()` 在序列化前排除行情波动字段（`price`、`change_pct`），仅品种/份额/成本变化时指纹改变。防止日内股价波动导致 TTL 期内缓存频繁失效。

### 7.2 缓存键模式

```
标准模式:   llm_{module_key}_{fingerprint}.json
           如: llm_global_macro_a1b2c3d4e5f6.json

批量模式:   llm_news_item_{hash}.json  （逐条缓存，hash 含标题+持仓指纹）
```

### 7.3 TTL 分辨率

`_get_cache_ttl_llm(subtype)` 两级优先级：

1. `config.json` → `cache_ttl.llm_{subtype}` 用户显式配置
2. 代码默认值（hardcoded defaults）：

| 模块 | 默认 TTL | 说明 |
|:-----|:--------:|:------|
| `global_macro` | 86400s (24h) | 宏观局势每日分析一次即可 |
| `expert_review` | 7200s (2h) | 智囊团复盘可在同一天多次触发 |
| `health_check` | 86400s (24h) | 体检报告每日更新 |
| `penetration_deep` | 86400s (24h) | 穿透分析每日更新 |
| `news_correlation` | 3600s (1h) | 新闻时效性强，TTL 较短 |

`import` 失败时兜底返回 hardcoded defaults（设计为防御性编程，正常情况下不会触发）。

### 7.4 缓存命中提示

缓存命中的 HTML 尾部追加提示行：

```
<p style="color:#888;font-size:12px">
本次使用LLM缓存，未直接使用LLM服务能力
</p>
```

若缓存内容中能提取到原始模型名，显示为：

```
<p style="color:#888;font-size:12px">
本次使用LLM缓存（原始模型：claude-sonnet-4-20250514）
</p>
```

若开启 Extended Thinking，追加 `| Extended Thinking` 标签。

[↑ 回到顶部](#目录)

---

## 8. 提示词管理

### 8.1 四个 System Prompt

**全球政经局势** (`_SYSTEM_GLOBAL_MACRO`)：资深宏观经济学家角色，500 字内，3-4 段评估主要经济体政策走向+地缘风险+对持仓潜在影响。纯文本输出，无 HTML。

**智囊团深度复盘** (`_SYSTEM_EXPERT_REVIEW`)：三阶段格式：
| 阶段 | 内容 |
|:-----|:------|
| Phase 1 — 召集令 | 指出组合核心矛盾，挑 5 位流派对立专家并标明立场 |
| Phase 2 — 圆桌会 | 两轮辩论：第一轮立足结构提方向，第二轮互相反驳 |
| Phase 3 — 定音锤 | 量化调仓方案 + 风险提示（不可调穿透层资产） |

约束：每个论点引用品种代码和收益率；禁止虚构数据；标注 `(QDII滞后1日)` 的基金不得讨论本日盈亏。

**持仓体检报告** (`_SYSTEM_HEALTH_CHECK`)：四维度各 100 分评分制，输出 Markdown 表格结构：
- 风险分散度（行业/品种集中度，含环比变化）
- 流动性（场内场外/停牌/封闭期）
- 收益合理性（与市场/同类对比）
- 成本结构（分布与浮盈浮亏比）

**穿透深度分析** (`_SYSTEM_PENETRATION_DEEP`)：三节分析（行业集中度、品种集中度、国别/币种暴露）+ 综合建议。

### 8.2 User Prompt 构建

各 `_build_*_prompt()` 函数接收运行时数据参数，格式化为紧凑文本块：

```
_build_global_macro_prompt()
  ┌─────────────────────────────────────────────┐
  │ 【当前时间】2026-07-14 14:30（北京时间）      │
  │ 【指数】A股:上证指数2985(+0.32%) ...          │
  │ 【持仓】总市值 1,234,567 总盈亏 +45,678        │
  │ 【分布】A股3只 ETF2只 基金5只                  │
  │ 【行业资金流向】                               │
  │  半导体 涨跌+1.23% 主力净流入 +12,345          │
  │  ...                                        │
  │ 请基于以上数据，分析当前全球政经局势对持仓的     │
  │ 潜在影响。                                   │
  └─────────────────────────────────────────────┘
```

**`_fmt_wan(num)` 工具函数**：将大数值转为中文单位（万/亿），减少 token 消耗。

**`_fmt_holding_line(h)` 工具函数**：格式化单条持仓明细，含净值日期 / QDII 滞后标注 / 涨跌幅。

**持仓明细格式化**（`_format_holdings_block`）：限制 30 行，3 种模式：
- 标准模式：`{code} 市值{wan} 盈亏{wan}({rate}) 今{chg:+.2f}%` + QDII 标注
- 紧凑模式：省略今日涨跌幅（智囊团使用，减少 token + 缓存更稳定）
- 含成本模式：增加成本字段（体检报告使用）

**差异上下文注入**（`_build_diff_context_block`）：仅 `expert_review` / `health_check` 使用，从 `f_context.diff` 提取环比变化（新增/清仓/加仓/减仓/市值变化/盈亏变化），以紧凑格式注入提示词。首次运行输出"暂无历史对比数据"。

**国别/币种分布**（`_calc_country_exposure`）：从持仓明细代码前缀推断（sh/sz/bj→A股，hk→港股，us→美股），并计算各国家/地区的市值合计。

[↑ 回到顶部](#目录)

---

## 9. 会话级 Token 追踪

### 9.1 数据结构

`llm/session.py` 维护全局线程安全的 `_session_usage` 字典（`threading.Lock` 保护，因 `ThreadPoolExecutor` 多线程写入）：

```python
_session_usage = {
    "input_tokens": 0,          # 累计输入 token
    "output_tokens": 0,         # 累计输出 token
    "cache_hit_tokens": 0,      # 累计缓存命中 token
    "total_cost": 0.0,          # 累计费用
    "currency": "CNY",          # 货币标识
    "model": "未指定",           # 最后使用的模型
    "models": [],               # 去重模型列表
    "call_count": 0,            # API 调用次数（缓存命中不计入）
    "per_module": {},           # 按模块细分
}
```

### 9.2 数据收集来源

```
_precheck_one_cache() -> 缓存命中
    → _record_per_module(key, model, cached=True, ...)

_generate_llm_content() -> API 调用成功
    → _track_session_usage(provider, usage, model_name)
    → _record_per_module(key, model, inp, out, cost, ...)

enhance_news_correlation() -> 新闻关联完成
    → _finalize_news_token_usage()
      → _record_per_module("news_correlation", ...)
```

### 9.3 生命周期

```
main.py 菜单 L/B 入口
    │
    ├─ reset_session_usage()          ← 会话开始，清空累计
    ├─ generate_all_llm()              ← 4 模块并行生成
    ├─ enhance_news_correlation()      ← 新闻 LLM 关联（可选）
    ├─ 生成报告（Excel/HTML 渲染）
    ├─ _print_llm_session_usage()      ← TUI 输出用量汇总
    │
    └─ 菜单退出                          ← 数据丢弃（下次调用 reset）
```

每次菜单 L/B 生成报告均为独立会话。会话开始时 `reset_session_usage()` 清空数据。

### 9.4 用量展示映射

```
_session_usage ──→ format_session_usage()
                     │  per_module 数据 → 模块级明细
                     │  call_count / total_tokens → 汇总
                     │  total_cost + currency → 含符号的费用字符串
                     │  全缓存（call_count=0 但 per_module 有数据）→ has_usage=True
                     │  无任何数据 → has_usage=False
                     │
                     ├──→ Excel 报告 (excel_llm_usage.py)
                     ├──→ HTML 报告 (html_writer.py + template)
                     └──→ TUI 终端 (tui_handlers.py)
```

[↑ 回到顶部](#目录)

---

## 10. 模型定价

### 10.1 定价合并规则

`_PRICING_MERGED` 运行时合并自两层：

1. **内置默认**（`constants.py` 中的 `MODEL_PRICING` 字典）
2. **用户覆盖**（`llm_settings.json` → `pricing` 字段，模块加载时 `_reload_pricing()` 自动合并）

文件配置优先级高于内置默认：

```
_PRICING_MERGED = dict(MODEL_PRICING)     # 内置默认
_reload_pricing() → 合并 llm_settings.json → pricing
                    每个模型条目覆盖或补充到 _PRICING_MERGED
                    可选字段 input_cache_hit 缺失时继承内置（或等于 input）
```

### 10.2 费用计算

```
费用 = cache_miss / 1,000,000 * input_rate
     + output_tokens / 1,000,000 * output_rate
     + cache_hit_tokens / 1,000,000 * input_cache_hit_rate
```

其中 `cache_miss = input_tokens - cache_hit_tokens`。

### 10.3 定价匹配优先级

`_estimate_cost()` 匹配模型定价的优先级：

1. **精确匹配**：模型全名小写 → 同名字典
2. **前缀匹配**：`deepseek-v4-flash-xxx` → `deepseek-v4-flash`
3. **回退**：均不匹配 → 返回 `"-"`（未知模型不计费）

### 10.4 货币

由 `llm_settings.json → pricing.currency` 控制（默认 `"CNY"`），决定费用显示符号（¥/$/€/£）。

[↑ 回到顶部](#目录)

---

## 11. 熔断器

`llm/circuit_breaker.py` 实现端点级熔断器，与 `provider_registry.py` 的熔断器职责分离：

| 特性 | DataSourceRegistry 熔断器 | LLM 熔断器 |
|:-----|:------------------------|:----------|
| 位置 | `provider_registry.py` | `llm/circuit_breaker.py` |
| 保护对象 | 数据源 Provider（腾讯/新浪/东财等） | LLM API 端点（Anthropic/OpenAI） |
| 粒度 | per-provider | per-endpoint（域名级） |
| 参数 | 单 API：3 次/300s；批量 API：6 次/120s | 3 次/60s |

**状态管理**：

```
连续失败 → _cb_record_failure(url)
    │ 累计当前 endpoint 的失败计数
    │ 达到 _CIRCUIT_BREAKER_THRESHOLD (3)
    │ → 设置冷却到期时间 time.time() + 60
    │ → 记录 WARNING
    ▼
熔断开启 → _cb_is_open(url)
    │ 检查冷却是否到期
    │ 未到期 → 返回 True（跳过请求）
    │ 已到期 → 删除冷却记录（自动半开）
    │        → 返回 False（放行一次试探）
    ▼
试探成功 → _cb_record_success(url) → 清空失败计数和冷却记录 → 恢复正常
试探失败 → _cb_record_failure(url) → 重新熔断
```

**线程安全**：所有操作通过 `_circuit_lock = threading.Lock()` 保护。

**endpoint 提取**：`_cb_endpoint(url)` 从完整 URL 中提取域名作为熔断器 key（`url.split("/")[2]`）。

[↑ 回到顶部](#目录)

---

## 12. 配置与注册

### 12.1 配置来源

| 配置项 | 所在文件 | 字段示例 |
|:-------|:---------|:---------|
| Provider/API Key/Endpoint | `llm_settings.json` | `provider`, `api_key`, `endpoint`, `model` |
| Per-module 参数 | `llm_settings.json` | `max_tokens_expert_review`, `timeout_global_macro` |
| 模块启用开关 | `llm_settings.json` | `enabled_llm.global_macro` |
| Thinking 配置 | `llm_settings.json` | `thinking_enabled_expert_review`, `thinking_budget_expert_review` |
| 简化模式 | `llm_settings.json` | `output_brief_expert_review` |
| 敏感密钥覆盖 | `llm_key.json` | 同名覆盖 `llm_settings.json` |
| 缓存 TTL | `config.json` | `cache_ttl.llm_global_macro` |
| 模型定价 | `llm_settings.json` → `pricing` | `pricing.currency`, `pricing.claude-sonnet-4-20250514.input` |

### 12.2 注册表键名派生

在 `registry.py` 中，每个 LLM 模块通过 `settings_suffix` 注册（`global_macro`、`expert_review`、`health_check`、`penetration_deep`、`news_correlation`），自动派生 `llm_settings.json` 的所有合法键名：

```
已知 LLM Settings 键名（每个模块 10 个）：
  model_{suffix}
  temperature_{suffix}
  timeout_{suffix}
  cache_enabled_{suffix}
  max_tokens_{suffix}
  system_prompt_{suffix}
  thinking_enabled_{suffix}
  thinking_budget_{suffix}
  reasoning_effort_{suffix}

除 news_correlation 外的 4 个模块额外增加：
  output_brief_{suffix}

加上 2 个全局键名：
  llm_max_concurrency
  fail_title_{suffix}
```

所有键名由 `get_known_llm_settings_keys()` 统一校验。新增 LLM 模块只需在 registry.py 注册表中添加一行 `DataModuleDef`，无需修改 config 校验逻辑。

### 12.3 LLM 模块配置合并（get_llm_config）

`llm_settings.json` 和 `llm_key.json` 合并读取（`llm_key.json` 的敏感字段覆盖 `llm_settings.json` 的同名字段），按 mtime 自动检查更新。

[↑ 回到顶部](#目录)

---

## 13. 集成点

LLM 集成层与系统其他组件的接口：

```
                            ┌────────────────────┐
  ┌─────────────────────── │ handlers_report.py  │ ← 菜单 L/B 入口
  │                         └─────────┬──────────┘
  │                                   │
  │                                   ▼
  │                         ┌────────────────────┐
  │                         │ report_prepare()   │
  │                         │ 准备 LLM 所需数据   │
  │                         └─────────┬──────────┘
  │                                   │
  │           ┌───────────────────────┼───────────────────────┐
  │           │                       │                       │
  │           ▼                       ▼                       ▼
  │   ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
  │   │ 指数数据      │     │ 持仓明细/分类     │     │ 穿透数据/行业     │
  │   │ fetcher/     │     │ models/reader    │     │ penetration/     │
  │   │ index.py    │     │ + code_utils     │     │ industry        │
  │   └──────────────┘     └──────────────────┘     └──────────────────┘
  │                                   │
  │                                   ▼
  │                         ┌────────────────────┐
  │                         │ generate_all_llm() │
  │                         │ 并行生成 4 模块    │
  │                         └─────────┬──────────┘
  │                                   │
  │           ┌───────────────────────┤
  │           │                       │
  │           ▼                       ▼
  │   ┌──────────────┐     ┌──────────────────┐
  │   │ 结果写入缓存  │     │ enhance_news_    │  ← 可选，通过 enabled_llm.
  │   │ cache_set()  │     │ correlation()    │     news_correlation 配置
  │   └──────────────┘     └─────────┬────────┘
  │                                   │
  │                                   ▼
  │                         ┌────────────────────┐
  │                         │ 生成报告            │
  │                         │ info → Excel/HTML  │
  │                         └────────────────────┘
  │
  ├── registry.py → DataModuleDef + get_cache_ttl_defaults + get_known_llm_settings_keys
  ├── cache/ → set() / get() / TTL
  ├── config/ → get_llm_config() / get_config()
  └── report/
        ├── excel_llm_usage.py → _session_usage → 用量页签
        ├── html_writer.py → section_visibility + context
        └── data_status.py → _LLM_MODULE_FAILURE → 失败原因展示
```

### 13.1 数据依赖关系

| LLM 模块 | 依赖数据源 | 缓存指纹依赖 |
|:---------|:----------|:------------|
| `global_macro` | A股指数 + 美股指数 + 总市值+总盈亏 + 分类 + (可选)行业资金流向 | 指数收盘价 + 持仓汇总 |
| `expert_review` | 总市值/成本/盈亏 + 持仓数量 + 分类 + 穿透资产 + 持仓明细 + (可选)f_context | 持仓品种/份额/成本（剔除行情波动） |
| `health_check` | 同 expert_review | 持仓品种/份额/成本（剔除行情波动） |
| `penetration_deep` | 同 expert_review + 穿透 TOP10（含行业/板块） | 同上 + 穿透 mv/ratio/sector（full_penetration=True） |
| `news_correlation` | 过滤后的新闻列表 + 持仓摘要 + 穿透资产 + 行业/概念数据 | 标题前 80 字 + 持仓指纹 |

### 13.2 失败影响范围

| 失败场景 | 影响 | 报告中表现 |
|:---------|:------|:-----------|
| LLM 未配置（`get_llm_config()=None`） | 所有 5 模块跳过 | LLM 页签显示"LLM 未配置" |
| 模块已禁用（`enabled_llm.x=false`） | 对应模块跳过 | 不在报告中生成对应章节 |
| 4 模块之一生成失败（API 错误） | 对应模块跳过，其他不受影响 | 显示失败原因提示（熔断/超时/网络错误/API 错误） |
| `news_correlation` 生成失败 | 新闻关联降级到关键词匹配结果 | LLM 增强的关联度/情感分析不可用 |
| 所有 5 模块均失败/skip | LLM 页签整体跳过 | LLM 模块在 board 层检测到数据全空时自动隐藏 |

[↑ 回到顶部](#目录)
