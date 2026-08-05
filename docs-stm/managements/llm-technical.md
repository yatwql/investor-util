# LLM 集成层技术设计
> 文档版本：0.10.7-dev

本文档是 `technical.md` 的 LLM 集成层专项技术设计补充，对应 `technical.md` §5（LLM 集成层概要设计）。
`technical.md` §5 提供 LLM 层的总体架构、模块清单、调用链概览、多 Provider 链模式概要及关键机制速览；
本文档在此基础上展开各子模块的详细设计、骨架流程、API 调用层实现、重试与容错策略、缓存与指纹失效、
提示词管理、会话级 Token 追踪、模型定价、熔断器、配置与注册机制及系统集成点。

两份文档配合阅读，`technical.md` 作为系统级技术设计主体提供全局上下文，
本文档作为 LLM 专项深潜提供实现级细节。架构设计约束统一参见 `technical.md` §8。

## 目录

- [1. 总体架构](#1-总体架构)
- [2. 模块清单](#2-模块清单)
- [3. 骨架流程](#3-骨架流程)
- [4. 并行编排](#4-并行编排)
- [5. API 调用层](#5-api-调用层)
  - [5.1 Provider 路由](#51-provider-路由)
  - [5.2 Multi-Provider Chain](#52-multi-provider-chain)
  - [5.3 credentials_ref 凭据引用](#53-credentials_ref-凭据引用)
- [6. 重试与容错](#6-重试与容错)
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
                               tui/handlers_report.py
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
  │ 4 个单例生成   │  │ LLM 增强新闻关联 │  │ generate_llm_      │
  │ 函数           │  │ enhance_news_    │  │ module()           │
  │                │  │ correlation()    │  │                    │
  └───────┬────────┘  └────────┬─────────┘  │ _run_standard_mode │
          │                    │             │ run_batch_mode     │
          │                    │             └───────┬────────────┘
          │                    │                     │ generate_llm_content()
          └──────────┬─────────┘                     │
                     │                               ▼
                     │                      ┌────────────────┐
                     │                      │  api.py        │ ← API 路由层
                     │                      │ call_llm()     │
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
                     │                      │ call_llm_with  │
                     │                      │ retry()        │
                     │                      │                │
                     │                      │ 重试骨架       │
                     │                      │ 截断检测       │
                     │                      │ 失败追踪       │
                     │                      └────────────────┘
                     │
                     ├──────────── 共享工具层 ────────────┐
                     │                                    │
                     ▼                                    ▼
              ┌──────────────────┐          ┌────────────────────┐
              │ prompts_core.py  │          │ fingerprint.py     │
              │ prompts_tables.py│          │ 缓存指纹计算       │
              │ prompts_action.py│          │ 稳定性字段提取      │
              │                │          │ 风险信号摘要        │
              └──────────────────┘          └────────────────────┘
              ┌──────────────────┐              ┌────────────────────┐
              │ session.py       │              │ pricing.py         │
              │ 会话用量累计      │              │ 模型定价/费用估算  │
              └──────────────────┘              └────────────────────┘
              ┌──────────────────┐          ┌────────────────────┐
              │ cost_tracker.py  │          │ markdown.py        │
              │ Token预算/摘要   │          │ MD→HTML 转换       │
              └──────────────────┘          └────────────────────┘
              ┌──────────────────┐          ┌────────────────────┐
              │ circuit_breaker  │          │ fact_checker/      │
              │ .py              │          │ 子包，9 个模块      │
              │ LLM 端点熔断器    │          └────────────────────┘
              └──────────────────┘
              ┌──────────────────┐
              │ fallback.py      │
              │ 降级占位模板      │
              └──────────────────┘
```

**调用链（API 调用流程）**：

```
skeleton.py:generate_llm_content()
    │  ① 缓存检查 → 命中直接返回
    │  ② call_llm()
    │      └─ api.py:call_llm()
    │             │  路由 provider → call_claude() / call_openai()
    │             │  ③ 空内容处理：thinking 耗尽→关闭 thinking 同 provider 重试一次；仍失败→切换 provider；""→安抚重试
    │             │  ④ 回退 provider（主 provider 失败时）
    │             └─ api_base.py:call_llm_with_retry()
    │                    │  熔断预检 → 熔断中则直接返回
    │                    │  循环 attempt=0..max_retries:
    │                    │    _attempt_api_call() → HTTP POST
    │                    │    成功 → _process_success_response()
    │                    │           → _extract_content()
    │                    │           → 截断检测
    │                    │           → _log_token_usage()
    │                    │           → track_session_usage()
    │                    │    可重试 → sleep → retry
    │                    │    致命 → 记录失败原因 → 返回
    │                    └→ _cb_record_failure/success()
    │  ③ _handle_truncation() → 截断检测 → 自动重试 max_tokens×1.5
    │  ④ _finalize_and_cache()
    │        → markdown_to_html()
    │        → 拼接模型/用量/费用页脚
    │        → cache_set()
    │        → record_per_module()
    └── 返回 (html, from_cached)
```

[↑ 回到顶部](#目录)

---

## 2. 模块清单

### 2.1 子模块总览

说明：`prompts.py` 为统一导出入口，将 `prompts_core.py` / `prompts_tables.py` / `prompts_action.py` 的公开符号汇总导出。

| 模块 | 分类 | 职责 | 入口函数 |
|:-----|:-----|:------|:---------|
| `generators_orchestrator.py` | 编排层 | 4+1 模块并行调度，缓存预检查，线程池分发 | `generate_all_llm()` |
| `generators.py` | 生成层 | 4 个单例生成函数（global_macro / expert_review / health_check / penetration_deep）+ 辩论模式 pro/con/synthesis 生成 | 各 `generate_*()` |
| `generators_news.py` | 生成层 | 新闻 LLM 二次关联分析（批量模式 7 函数） | `enhance_news_correlation()` |
| `skeleton.py` | 骨架层 | 标准模式 + 批量模式共享生成骨架（85% 公共逻辑）+ `raw_filter_fn` 原始输出过滤钩子（markdown_to_html 之前） | `generate_llm_module()` |
| `api.py` | API 层 | Provider 路由、Multi-Provider Chain 链式遍历、Extended Thinking 注入、单 Provider 分派 | `call_llm()` / `call_single_provider()` |
| `api_base.py` | 基础设施 | HTTP 调用、重试骨架、截断检测、Token 日志、失败追踪 | `call_llm_with_retry()` |
| `strategy.py` | 基础设施 | 多 Provider 切换策略引擎（priority/weighted/cost_first/fallback_only），模块偏好注入，代理偏好后置处理 | `resolve_provider_chain()` |
| `fact_checker/`（子包 9 模块，`__init__.py` 重导出 4 公开函数） | 基础设施 | LLM 输出事实锚定校验（数值一致性/品种存在性/排名正确性）+ 自动修正 | `run_fact_check()` |
| `fallback.py` | 基础设施 | 全模块失败时的降级占位模板 | `get_fallback_content()` |
| `prompts_core.py` | 工具 | System Prompt 常量 + 上下文构建块（数据降级/收益归因/竞争语境/再平衡/概念板块/管线差异） | `_SYSTEM_*` 常量 + `_build_system_debate_synthesis()` |
| `prompts_tables.py` | 工具 | 持仓/穿透/指标/情景/数据质量/汇率等数据块格式化为 Markdown | `_format_holdings_block()` / `_build_holdings_summary()` |
| `prompts_action.py` | 工具 | 各模块 User Prompt 构建（global_macro / expert_review / health_check / penetration_deep / debate_synthesis）+ 集中度问答块 | `_build_expert_review_prompt()` / `_build_qa_concentration_block()` |
| `fingerprint.py` | 工具 | LLM 缓存指纹计算、稳定性字段提取、TTL 查询 | `compute_fingerprint()` / `build_llm_fingerprint()` |
| `session.py` | 工具 | 会话级 Token 累计、模块级记录、格式化输出 | `track_session_usage()` / `get_session_usage()` |
| `cost_tracker.py` | 工具 | Token 预算管理、输入检查、成本摘要格式化（compact/verbose） | `reset_budget()` / `get_cost_summary()` |
| `pricing.py` | 工具 | 模型定价合并、费用估算 | `estimate_cost()` / `reload_pricing()` |
| `circuit_breaker.py` | 工具 | LLM 端点熔断器（连续 3 次失败 + 固定 60s 冷却） | `get_circuit_status()` |
| `markdown.py` | 工具 | Markdown→HTML 转换 | `markdown_to_html()` |
| `_api_claude.py` / `_api_gemini.py` / `_api_openai.py` | 私有 | 各 Provider 单次调用实现（自包含依赖，委托 api_base 重试 + Extended Thinking 注入），api.py 分派目标 | `call_claude()` / `call_gemini()` / `call_openai()` |
| `_batch_mode.py` | 私有 | 批量模式分块执行（`_BATCH_CHUNK_SIZE=10` 每批、最多 3 批并行，受 `min(3, 批数, 6)` 约束） | `run_batch_mode()` |

### 2.2 四大+一模块详情

#### 标准模式模块（4 个，通过 `generate_llm_module` 以标准模式调用）

| 模块键 | 名称 | 默认 max_tokens | 默认 timeout | 默认 TTL | 默认 system_prompt |
|:-------|:-----|:---------------:|:------------:|:--------:|:-------------------|
| `global_macro` | 全球政经局势 | 2048 | 60s | 24h（86400s） | 宏观经济学家角色，500 字内，纯文本 |
| `expert_review` | 智囊团深度复盘 | 24000 | 120s | 2h（7200s） | 召集令→圆桌会→定音锤三阶段 |
| `health_check` | 持仓体检报告 | 16000 | 120s | 24h（86400s） | 五维度评分（风险分散度/流动性/收益合理性/成本结构/数据质量） |
| `penetration_deep` | 穿透深度分析 | 8192 | 90s | 24h（86400s） | 行业/品种集中度+国别暴露 |

#### 批量模式模块（1 个，通过 `generate_llm_module` 以批量模式调用）

| 模块键 | 名称 | 默认 max_tokens | 默认 timeout | 默认 TTL | 默认 system_prompt |
|:-------|:-----|:---------------:|:------------:|:--------:|:-------------------|
| `news_correlation` | 新闻 LLM 关联分析 | 2000 | 60s | 1h（3600s） | 逐批分析新闻与持仓关联性（JSON 输出） |

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

### 3.1 `generate_llm_module()` — 两路分支

```
generate_llm_module(llm_config, module_key, *hooks)
    │
    ├── llm_config is None → get_llm_config() 尝试读取配置
    │      └── 仍为 None → 返回 None（未配置）
    │
    ├── is_llm_module_enabled() → False
    │      └── 返回 None（已禁用），记录 _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_DISABLED
    │
    ├── batch_preparer is not None  → run_batch_mode()（批量模式）
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
┌──────────────────────────────────────────┐
│ 注入 Prompt Appendix（防御统一注入）      │
│ _build_prompt_appendix() → 追加至尾部     │
│  TOP3 排名 + 数据速查表 + 代码白名单       │
└──────────────────┬───────────────────────┘
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
│ │ ② call_llm()                    │  │
│ │ 清除上次失败原因                  │  │
│ │ → 主 provider API 调用           │  │
│ │ → 空内容处理（None→切换/""→安抚）│  │
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
│ │ ③' 原始输出过滤（可选）          │  │
│ │ raw_filter_fn 非空 →             │  │
│ │   result = raw_filter_fn(result) │  │
│ │ 辩论模式虚构代码过滤：对带换行     │  │
│ │ 的原始 Markdown 先过滤，再转 HTML  │  │
│ └──────────────┬──────────────────┘  │
│                │                      │
│ ┌──────────────▼──────────────────┐  │
│ │ ④ _finalize_and_cache()         │  │
│ │ markdown_to_html() → 判空       │  │
│ │ → 拼接模型/用量/费用页脚         │  │
│ │ → cache_set()                   │  │
│ │ → record_per_module()           │  │
│ │ 返回 (html, False)              │  │
│ └─────────────────────────────────┘  │
└──────────────────────────────────────┘
```

### 3.3 `run_batch_mode()` — 批量模式流程

```
run_batch_mode(llm_config, module_key, *hooks)
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
│  → call_llm()   │
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
tui/handlers_report.py 菜单 L/B
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
needs = {k: (v["result"] is None and is_llm_module_enabled(llm_config, k))
         for k, v in precheck_results.items()}

# 无需求时直接返回
if not any(needs.values()):
    return {}
```

### 4.4 pipeline_data 注入与 history_data 暴露

`pipeline_data`（组合历史走势时间维度上下文，含快照 diff 差异摘要）可选传递给 `expert_review` 和 `health_check`，使 LLM 能感知持仓环比变化（新增/清仓/加仓/减仓品种、总市值/总盈亏变化百分比）。

**history_data 暴露**：`generate_all_llm()` 接收 `history_data` 参数，包含组合历史日收益率序列、基准指数日收益率序列等时间序列数据。该数据在 prompt 中以紧凑图表形式注入，使 LLM 能感知组合的历史波动特征和相对大盘表现，增强智囊团深度复盘和持仓体检报告中的趋势分析能力。

首次运行（`is_first_check=True`）时输出"暂无历史对比数据"标记。

[↑ 回到顶部](#目录)

---

## 5. API 调用层

### 5.1 Provider 路由

```
call_llm(system_prompt, user_prompt, llm_config, ...)
    │
    ├─ ① 读取 Provider 列表和策略
    │   strategy.resolve_provider_chain(provider_list, strategy, module_key, preferred)
    │   按策略排序（priority/weighted/cost_first/fallback_only）
    │   → _apply_module_preferred() 模块偏好前置
    │   → _apply_proxy_preferred() 有代理时 proxy_preferred 条目前置
    │
    ├─ ② 乐观缓存预检
    │   以链首 Provider 的缓存键做预检查 → 命中则直接返回
    │
    ├─ ③ 遍历 Provider Chain（逐条尝试至成功）
    │      for entry in chain:
    │          _resolve_entry_credentials(entry, llm_config)
    │            ├─ credentials_ref 查表 → api_key/model/endpoint
    │            ├─ entry 级叠加覆盖
    │            └─ 无 ref → 内联字段回退
    │
    │          _call_provider_entry(entry, ...)
    │            ├─ "claude"  → call_claude()（_api_claude.py）
    │            │   Anthropic Messages API
    │            │   + Extended Thinking 注入
    │            │   + Prompt Caching (cache_control)
    │            ├─ "openai"  → call_openai()（_api_openai.py）
    │            │   OpenAI Chat Completions API
    │            │   (也兼容 DeepSeek 等 OpenAI 兼容端点)
    │            └─ "gemini"  → call_gemini()（_api_gemini.py）
    │                Google Gemini API (generateContent)
    │                + ThinkingConfig 注入 (generationConfig.thinkingConfig.thinkingBudget)
    │
    │          成功 → 返回 (content, usage, provider_name)
    │          空内容 None（无 text block，如 thinking 耗尽 max_tokens 预算）
    │            → 先关闭 thinking 同 provider 重试一次（安全网）；仍无正文再切换下一 entry
    │          空字符串 ""（真正被过滤/无内容）→ 内容过滤安抚重试（追加安抚指令重试一次）
    │          失败 → 记录失败原因，继续下一 entry
    │
    └─ ④ 全链失败 → 返回 (None, {}, None)
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
    │      配置缺失时兜底 "high"（模板默认：expert_review / health_check 为 medium）
    │
    └─ budget_tokens 模型 (Claude Sonnet 4 / Opus 4 / Gemini 2.5) →
           payload["thinking"]["budget_tokens"] = budget
           budget 从 thinking_budget_{module_suffix} 读取
           不足 max_tokens + 1024 时自动兜底到 max_tokens + 4096
           Gemini 使用 generationConfig.thinkingConfig.thinkingBudget，效果等价
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

#### _call_gemini() 关键细节

**URL**: `{endpoint}/models/{model}:generateContent`

默认 `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`（模型名嵌入 URL 路径）。

**认证方式**：通过 `x-goog-api-key` 请求头传递 API Key，凭据在 `llm_key.json` 中配置。

**Payload 结构**：
```python
{
    "contents": [
        {"role": "user", "parts": [{"text": user_prompt}]},
    ],
    "systemInstruction": {"parts": [{"text": system_prompt}]},
    "generationConfig": {
        "maxOutputTokens": max_tokens,
    },
}
```

`system_prompt` 通过 `systemInstruction` 字段传递（非 messages 数组内），`user_prompt` 通过 `contents[0].parts[0].text` 传递。

**Extended Thinking 注入**（通过 `generationConfig.thinkingConfig`）：

```
call_gemini() Extended Thinking 注入
    │
    ├─ 读取 thinking_enabled_{module_suffix}
    │      False → 无操作返回
    │
    ├─ 验证模型兼容性 (_supports_extended_thinking)
    │      不兼容 → 自动降级跳过，记录 WARNING
    │
    └─ 启用 Thinking →
           payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": budget}
           budget 从 thinking_budget_{module_suffix} 读取
           不足 max_tokens + 1024 时自动兜底到 max_tokens + 4096
           payload["generationConfig"].pop("temperature", None)  ← 与 temperature 互斥
```

与 Claude 的区别：Gemini 的 Thinking 配置位于 `generationConfig.thinkingConfig`（而非顶层 `thinking` 字段），且仅支持 `budget_tokens` 模式（通过 `thinkingBudget` 参数），不支持 `effort` 模式。

### 5.2 Multi-Provider Chain

#### 设计目标

在单 Provider 不可用时自动递补备选 Provider，避免单点故障导致 LLM 分析完全不可用。支持多种切换策略以适配不同的成本/性能偏好。

#### 4 种策略详解

| 策略 | 引擎函数 | 排序逻辑 | 适用场景 |
|:-----|:---------|:---------|:---------|
| `priority`（默认） | `_resolve_priority_chain()` | 按 `priority` 字段升序（数值越小越优先） | 显式指定首选的成本/质量平衡 |
| `weighted` | `_resolve_weighted_chain()` | 按 `weight` 字段加权随机打乱，权重越高被选到链首的概率越大 | 负载均衡、A/B 测试 |
| `cost_first` | `_resolve_cost_first_chain()` | 查询 `pricing.py` 定价表，按每千 token 费用升序排列；未知模型排末尾 | 成本敏感场景 |
| `fallback_only` | 同 `priority` | 等价于 `priority`，语义为"主 Provider + N 个备用" | 明确主备关系的场景 |

**后置处理**：无论何种策略，`resolve_provider_chain()` 返回前会依次执行：
- `_apply_module_preferred()` — 模块偏好 Provider 移至列表首位
- `_apply_proxy_preferred()` — 检测到代理环境变量时，`proxy_preferred=true` 的 Provider 条目前置

**coalesce 合并**：最终列表会移除 `provider` 类型重复项（保留首个出现的版本），避免同一 provider 类型重复尝试。

### 5.3 credentials_ref 凭据引用

**设计目的**：将敏感凭据（api_key、model、endpoint）与 Provider 路由配置分离，降低凭据泄露风险，支持凭据复用。

**凭据来源**：`llm_config["_llm_credentials"]`，由 `config/_llm_providers.py` 的 `_load_llm_key_credentials()` 读取 `llm_key.json` 构建。

**解析优先级**（`_resolve_entry_credentials()`）：

1. **`credentials_ref` 查表**：从 `llm_config["_llm_credentials"]` 中查找对应键名的凭据块
2. **entry 级叠加覆盖**：若 entry 本身也包含 `api_key`/`model`/`endpoint`，则覆盖凭据块中的同名字段
3. **无 ref 回退**：无 `credentials_ref` 时，直接使用 entry 内联字段

**兼容说明**：
- **单键格式**：`llm_key.json` 为 `{"api_key": "...", "model": "..."}` 时，自动包裹为 `{"_default": {...}}`
- **内联凭据**：`llm_providers.json` 的 entry 可直接含 `api_key`/`model`（无需 `credentials_ref`）

[↑ 回到顶部](#目录)

---

## 6. 重试与容错

### 6.1 四层容错

```
第 1 层：熔断器（circuit_breaker.py）
    ── call_llm_with_retry() 入口检查
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

第 4 层：空内容处理（api.py）
    ── `_extract_content` 无 text block → 返回 None，若曾开启 thinking
       且判定为思考耗尽 → 先关闭 thinking 同 provider 重试一次（安全网）
       （DeepSeek V4 强制推理模型思考部分耗尽 max_tokens 预算时响应仅含
        thinking block 无 text；重试后仍无正文才切换下一 provider）
    ── 真正空字符串 ""（可能被内容审查拦截）→ 追加安抚指令重试一次
    ── 安抚成功 → 返回重试结果
    ── 安抚失败 → 切换 provider
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

每次新生成开始时 `_clear_last_llm_failure()` 清除上次失败；失败原因通过 `LLM_MODULE_FAILURE[module_key]` 字典留存。多链模式下，该字典记录每个模块的完整调用历程：

```python
LLM_MODULE_FAILURE: dict[str, dict] = {
    module_key: {
        "attempted": [
            "deepseek-main: api_error",       # "provider_name: failure_reason"
            "gemini-fallback: SUCCESS",       # 成功条目标注 SUCCESS
        ],
        "final_status": "success",            # "success" 或 fail_reason 字符串
    }
}
```

报告模块读取此字典，按 `final_status` 输出差异化占位文本或正常渲染内容。若 `final_status` 为 `"success"`，表示该模块至少有一个 Provider 调用成功，内容正常可用。

[↑ 回到顶部](#目录)

---

## 7. 缓存与指纹失效

### 7.1 指纹计算

LLM 缓存使用指纹驱动失效机制。指纹变化时缓存自动失效，无需等待 TTL 到期。

#### `compute_fingerprint()` — 通用确定性哈希

```python
def compute_fingerprint(*args: Any) -> str:
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]
```

输入参数任意组合 → 确定性 MD5 → 前 12 位十六进制作为缓存键后缀。

#### `build_llm_fingerprint()` — LLM 专用指纹构建

```
build_llm_fingerprint(total_mv, total_cost, total_profit, total_today_profit,
                      holdings_details, penetrated_assets, categories,
                      full_penetration=False)
```

在序列化前执行稳定性字段提取：

```
holdings_details ──→ extract_stable_holdings()
                     仅保留 {name, code, cost}
                     剔除 price/change_pct/nav_date 等行情波动字段

penetrated_assets ──→ extract_stable_penetration()
                     默认仅保留 {name, codes}（排除行情波动）
                     full_penetration=True 时额外保留 {mv, sector, ratio}
                       （穿透深度分析需要穿透数据变化触发失效）
```

**设计目的**：`expert_review` / `health_check` / `penetration_deep` 的 `compute_fingerprint()` 在序列化前排除行情波动字段（`price`、`change_pct`），仅品种/份额/成本变化时指纹改变。防止日内股价波动导致 TTL 期内缓存频繁失效。

**风险信号摘要**：`risk_metrics` 摘要（夏普/卡玛/HHI 等计算指标的 MD5 摘要）作为指纹哈希因子。风险信号变化时缓存自动失效，确保 LLM 提示词中包含的量化指标与最新计算结果一致。

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

### 7.5 Provider 感知缓存

多链模式下，不同 Provider 对同一模块的生成内容不同。缓存键需区分 Provider，避免切换 Provider 后返回旧 Provider 的缓存结果。

**缓存键格式**：`llm_{module}_{provider_name}_{fingerprint}`

**乐观预检**：`generate_llm_content()` 在遍历链之前，先以**链首 Provider** 的缓存键做一次缓存检查：

```
optimistic_key = _build_provider_cache_key(module_key, chain[0]["name"], fingerprint)
cache_get(optimistic_key, ttl) → 命中 → 直接返回（+ 缓存标记）
                                → 未命中 → 走完整链
```

设计目的：绝大多数情况下链首 Provider 最常使用，提前检查避免不必要的链遍历。

**缓存写入**：API 调用成功后，以**实际返回的 provider_name** 写入缓存（而非链首），确保缓存键与实际 Provider 一致。

[↑ 回到顶部](#目录)

---

## 8. 提示词管理

### 8.1 五个 System Prompt

**全球政经局势** (`_SYSTEM_GLOBAL_MACRO`)：资深宏观经济学家角色，500 字内，3-4 段评估主要经济体政策走向+地缘风险+对持仓潜在影响。纯文本输出，无 HTML。

**智囊团深度复盘** (`_SYSTEM_EXPERT_REVIEW`)：三阶段格式：
| 阶段 | 内容 |
|:-----|:------|
| Phase 1 — 召集令 | 指出组合核心矛盾，挑 5 位流派对立专家并标明立场 |
| Phase 2 — 圆桌会 | 两轮辩论：第一轮立足结构提方向，第二轮互相反驳 |
| Phase 3 — 定音锤 | 量化调仓方案 + 风险提示（不可调穿透层资产） |

约束：每个论点引用品种代码和收益率；禁止虚构数据；标注 `(QDII滞后1日)` 的基金不得讨论本日盈亏。

**持仓体检报告** (`_SYSTEM_HEALTH_CHECK`)：五维度各 100 分评分制，输出 Markdown 表格结构：
- 风险分散度（行业/品种集中度，含环比变化）
- 流动性（场内场外/停牌/封闭期）
- 收益合理性（与市场/同类对比）
- 成本结构（分布与浮盈浮亏比）
- 数据质量（输入数据完整性与可靠性，引用【数据质量降级】事件）

**穿透深度分析** (`_SYSTEM_PENETRATION_DEEP`)：三节分析（行业集中度、品种集中度、国别/币种暴露）+ 综合建议。

**新闻关联分析** (`_SYSTEM_NEWS_CORRELATION`)：批量分析模式下使用的 System Prompt，要求 LLM 按 JSON 数组格式输出每条新闻与持仓组合的关联度评分、影响方向（正面/负面/中性）及简要理由。每批最多 10 条新闻，分析时需引用品种代码，禁止虚构数据。

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

**差异上下文注入**（`_build_difpipeline_data_block`）：仅 `expert_review` / `health_check` 使用，从 `pipeline_data.diff` 提取环比变化（新增/清仓/加仓/减仓/市值变化/盈亏变化），以紧凑格式注入提示词。首次运行输出"暂无历史对比数据"。

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
    "per_module": {},           # 按模块细分（含 duration 字段）
}
```

`llm/cost_tracker.py` 在前者之上提供 Token 预算管理：

| 函数 | 职责 |
|:-----|:------|
| `reset_budget(input_budget)` | 每份报告开始时重置预算状态 |
| `check_input_budget(module, input_tokens)` | 调用前检查是否超预算 |
| `get_budget_status()` | 查询当前预算使用情况 |
| `get_cost_summary(for_report=True)` | 生成成本摘要文本（`for_report=True` 对应 verbose 模式） |

#### 9.1.1 duration 字段

`record_per_module()` 接受 `duration: float = 0.0` 参数，记录每个模块的 API 调用耗时（秒）。`skeleton.py` 中 `generate_llm_content()` 通过 `time.monotonic()` 计时，调用 `call_llm()` 前后计算耗时，传入 `_finalize_and_cache()` 后写入 `per_module` 的 `"duration"` 键。多条缓存路径（首次生成 + 截断重试）的耗时通过 `duration` 字段累计。

HTML 报告页脚自动显示每个模块的耗时（`耗时: X.Xs`），便于识别慢模块。

### 9.2 数据收集来源

```
_precheck_one_cache() -> 缓存命中
    → record_per_module(key, model, cached=True, ...)

generate_llm_content() -> API 调用成功
    → time.monotonic() 计时开始
    → track_session_usage(provider, usage, model_name)
    → record_per_module(key, model, inp, out, cost, ...)
    → duration = time.monotonic() - start
    → _finalize_and_cache(..., duration=duration) ← 页脚显示耗时

enhance_news_correlation() -> 新闻关联完成
    → _finalize_news_token_usage()
      → record_per_module("news_correlation", ...)
```

### 9.3 生命周期

```
进程内模块级 _session_usage 累计
    │
    ├─ track_session_usage()           ← 每次 API 调用后累计 Token/费用（api_base.py）
    ├─ record_per_module()             ← 按模块记录模型/耗时/缓存/Thinking（api_base.py）
    ├─ generate_all_llm()              ← 4 模块并行生成
    ├─ enhance_news_correlation()      ← 新闻 LLM 关联（可选）
    ├─ 生成报告（Excel/HTML 渲染）
    ├─ print_llm_session_usage()       ← TUI 输出用量汇总（tui_handlers.py）
    │
    └─ 进程退出                          ← 数据随进程释放（无显式重置调用点）
```

用量数据由 `track_session_usage()` 随调用实时累计，`reset_session_usage()` 虽提供重置接口但生产代码无调用点；进程内多次生成报告时数据持续累计。

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
                     │     页脚附加每个模块的 duration（耗时）
                     ├──→ TUI 终端 (tui_handlers.py)
                     └──→ cost_tracker.get_cost_summary(for_report=True)
                            compact 模式一行摘要 / verbose 模式模块级明细
```

[↑ 回到顶部](#目录)

---

## 10. 模型定价

### 10.1 定价合并规则

`_PRICING_MERGED` 在运行时合并两层：

1. **内置默认**（`core/constants.py` 中的 `MODEL_PRICING` 字典）
2. **用户覆盖**（`llm_settings.json` → `pricing` 字段，模块加载时 `reload_pricing()` 自动合并）

文件配置优先级高于内置默认：

```
_PRICING_MERGED = dict(MODEL_PRICING)     # 内置默认
reload_pricing() → 合并 llm_settings.json → pricing
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

`estimate_cost()` 匹配模型定价的优先级：

1. **精确匹配**：模型全名小写 → 同名字典
2. **前缀匹配**：`deepseek-v4-flash-xxx` → `deepseek-v4-flash`
3. **回退**：均不匹配 → 返回 `"-"`（未知模型不计费）

### 10.4 货币

由 `llm_settings.json → pricing.currency` 控制（默认 `"CNY"`），决定费用显示符号（¥/$/€/£）。

[↑ 回到顶部](#目录)

---

## 11. 熔断器

`llm/circuit_breaker.py` 实现端点级熔断器，与 `core/provider_registry.py` 的熔断器职责分离：

| 特性 | DataSourceRegistry 熔断器 | LLM 熔断器 |
|:-----|:------------------------|:----------|
| 位置 | `core/provider_registry.py` | `llm/circuit_breaker.py` |
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
| Provider/API Key/Endpoint | `llm_key.json`（多凭据块） | `{"deepseek-main": {"api_key": "...", "model": "...", "endpoint": "..."}}` |
| Provider 链与策略 | `llm_providers.json` | `{"strategy": "priority", "providers": [{"name": "p1", "credentials_ref": "deepseek-main", ...}]}` |
| Per-module 参数 | `llm_settings.json` | `max_tokens_expert_review`, `timeout_global_macro` |
| 模块启用开关 | `llm_settings.json` | `enabled_llm.global_macro` |
| 事实校验容差 | `llm_settings.json` | `fact_check.tolerance`, `fact_check.tolerance_overrides` |
| Thinking 配置 | `llm_settings.json` | `thinking_enabled_expert_review`, `thinking_budget_expert_review` |
| 简化模式 | `llm_settings.json` | `output_brief_expert_review` |
| 缓存 TTL | `config.json` | `cache_ttl.llm_global_macro` |
| Provider 文件路径 | `config.json` | `llm_providers_file`, `llm_key_file`, `llm_settings_file` |
| 模型定价 | `llm_settings.json` → `pricing` | `pricing.currency`, `pricing.claude-sonnet-4-20250514.input` |

### 12.2 注册表键名派生

在 `core/registry.py` 中，每个 LLM 模块通过 `settings_suffix` 注册（`global_macro`、`expert_review`、`health_check`、`penetration_deep`、`news_correlation`），自动派生 `llm_settings.json` 的所有合法键名：

```
已知 LLM Settings 键名（每个模块 9 个）：
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

加上全局键名：
  max_retries
  enabled_llm
  pricing
  llm_max_concurrency
  news_correlation_top_n
  debate
  fact_check
```

所有键名由 `get_known_llm_settings_keys()` 统一校验。新增 LLM 模块只需在 registry.py 注册表中添加一行 `DataModuleDef`，无需修改 config 校验逻辑。

### 12.3 LLM 模块配置合并（get_llm_config）

`llm_settings.json`、`llm_key.json` 和 `llm_providers.json` 三层合并：

```
get_llm_config()
    │
    ├── ① 读取 llm_settings.json（非敏感参数）
    ├── ② 读取 llm_key.json（敏感凭据，覆盖同名字段）
    │      单键格式 {"api_key": "...", "model": "..."} → 自动包裹为 {"_default": {...}}
    │      多凭据格式 {"deepseek-main": {...}, "gemini-fb": {...}} → 多凭据块
    ├── ③ 读取 llm_providers.json（若存在）
    │      _inject_provider_chain_data() 注入：
    │        _provider_list — 解析并校验后的 Provider 数组
    │        _strategy — 切换策略
    │        _preferred_providers — 模块级首选 Provider
    │        _llm_credentials — 解析后的凭据字典
    └── ④ 按 mtime 联合检查更新，返回合并配置
```

[↑ 回到顶部](#目录)

---

## 13. 集成点

LLM 集成层与系统其他组件的接口：

```
                            ┌────────────────────────┐
  ┌─────────────────────── │ tui/handlers_report.py │ ← 菜单 L/B 入口
  │                         └───────────┬───────────┘
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
| `expert_review` | 总市值/成本/盈亏 + 持仓数量 + 分类 + 穿透资产 + 持仓明细 + (可选)pipeline_data | 持仓品种/份额/成本（剔除行情波动） |
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

---

## 附录

### 附录 A：LLM 模块配置参数总览

| 参数模式 | 含义 | 示例值 |
|:---------|:-----|:-------|
| `enabled_llm.{module_key}` | 模块开关 | `true` / `false` |
| `model_{module_key}` | 模型指定 | `claude-sonnet-4-6` |
| `temperature_{module_key}` | 生成温度 | `0.7` |
| `max_tokens_{module_key}` | 最大输出 token | `4096` |
| `timeout_{module_key}` | API 超时（秒） | `120` |
| `system_prompt_{module_key}` | 系统提示词覆盖 | `null`（使用内置） |
| `cache_enabled_{module_key}` | 是否启用缓存 | `true` / `false` |
| `output_brief_{module_key}` | 精简模式 | `true` / `false` |
| `thinking_enabled_{module_key}` | 是否启用 Extended Thinking | `true` / `false` |
| `reasoning_effort_{module_key}` | DeepSeek 推理强度 | `low` / `medium` / `high` / `max` |
| `thinking_budget_{module_key}` | Claude/Gemini Thinking 预算 token | `10240` |

所有参数在 `llm_settings.json` 中配置，`{module_key}` 取值为 `global_macro` / `expert_review` / `health_check` / `penetration_deep` / `news_correlation`。

### 附录 B：内置模型定价表

以下为 `core/constants.py` 中 `MODEL_PRICING` 内置的定价快照（单位：元/百万 token），可通过 `llm_settings.json` 的 `pricing` 覆盖：

| 模型 | 输入 | 输出 | 缓存命中 |
|:-----|:----:|:----:|:--------:|
| claude-fable-5 | 3.00 | 15.00 | 0.30 |
| claude-haiku-4-5 | 0.25 | 1.25 | 0.025 |
| claude-opus-4-8 | 15.00 | 75.00 | 1.50 |
| claude-opus-4-6 | 15.00 | 75.00 | 1.50 |
| claude-sonnet-4-6 | 3.00 | 15.00 | 0.30 |
| claude-sonnet-4-8 | 3.00 | 15.00 | 0.30 |
| deepseek-chat | 1.00 | 2.00 | 0.02 |
| deepseek-v4-flash | 1.00 | 2.00 | 0.02 |
| deepseek-v4-pro | 3.00 | 6.00 | 0.025 |
| gemini-2.0-flash | 0.10 | 0.40 | 0.01 |
| gemini-2.5-flash | 0.15 | 0.60 | 0.015 |
| gemini-2.5-pro | 1.25 | 5.00 | 0.125 |
| gemini-3.5-flash | 0.15 | 0.60 | 0.015 |
| gpt-4o | 2.50 | 10.00 | 2.50 |
| gpt-4o-mini | 0.15 | 0.60 | 0.15 |

> 上表为具名模型定价；`MODEL_PRICING` 另有 6 个前缀回退键（`claude-sonnet-4-`/`claude-opus-4-`/`claude-haiku-4-`/`gemini-3.5-`/`gemini-2.5-`/`gemini-2.0-`）用于 startswith 回退匹配日期戳变体，未逐行列示。

费用按 `(input_tokens × 输入单价 + output_tokens × 输出单价 + cache_hit_tokens × 缓存命中单价) / 1_000_000` 计算。

### 附录 C：LLM 模块指纹依赖字段

| 模块 | 指纹依赖（稳定字段） | 排除字段 |
|:-----|:-------------------|:---------|
| `global_macro` | 指数收盘价 + 持仓汇总 | 无排除 |
| `expert_review` | 品种/份额/成本 | 行情价/涨跌幅/净值日期 |
| `health_check` | 品种/份额/成本 | 行情价/涨跌幅/净值日期 |
| `penetration_deep` | 品种/份额/成本 + 穿透 mv/ratio/sector（`full_penetration=True`） | 行情价/涨跌幅 |
| `news_correlation` | 标题前 80 字 + 持仓指纹 | 全文细节 |

[↑ 回到顶部](#目录)
