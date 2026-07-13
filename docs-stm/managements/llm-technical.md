# LLM 客户端技术要点

## 模块架构

`src/python/llm/` 包拆分架构（`llm_client.py` 解耦为 12 子模块，含 skeleton.py 共享骨架）：

| 模块 | 职责 |
|------|------|
| `api.py` | API 调用路由 (Claude/OpenAI)、重试、截断检测、熔断器集成 |
| `api_base.py` | 共享 API 骨架（`_attempt_api_call`、`_extract_content`、`_process_success_response`、Token 日志） |
| `prompts.py` | System Prompt 常量与构建函数 |
| `generators_orchestrator.py` | LLM 生成编排（4+1 模块，线程池并行） |
| `generators_news.py` | 新闻关联分析的 LLM 调用逻辑 |
| `pricing.py` | 模型定价加载、费用估算 |
| `session.py` | 会话用量累计、追踪 |
| `circuit_breaker.py` | 端点熔断器 |
| `fingerprint.py` | 各种缓存指纹计算 |
| `markdown.py` | Markdown→HTML 渲染 |
| `skeleton.py` | 共享生成骨架 |

- **统一入口** `_call_llm()` 按 `provider` 路由到 `_call_claude()` 或 `_call_openai()`
- **`_call_llm_with_retry()`** 共享重试/超时/错误处理骨架
- **`_generate_llm_content()` / `_generate_llm_module()`** 共享骨架函数（`skeleton.py`），封装缓存检查 + 调用 + markdown→HTML + 写入的 85% 公共逻辑
- **注册表键名派生**（`registry.py`）：每个 LLM 模块的 `settings_suffix` 自动派生出 9 个 `llm_settings.json` 合法键名。`news_correlation` 外的模块额外增加 `output_brief_`。所有键名由注册表统一校验，新增模块只需在注册表添加一行。

## Extended Thinking

`_call_claude()` 通过 `llm_config` 参数读取 `thinking_enabled_{模块}` 配置，为 Claude API 注入 `thinking` payload 以实现深度推理。

**关键逻辑：**
- `thinking_budget` 与 `max_tokens` 是独立参数：前者控制内部推理 token（不可见），后者控制最终输出 token
- API 约束：`thinking_budget` ≥ `max_tokens + 1024`，代码中 `_call_claude()` 自动兜底不足时补到 `max_tokens + 4096`
- Extended Thinking 与 `temperature` 互斥，开启后自动 `payload.pop("temperature", None)`
- 推荐仅在智囊团深度复盘（expert_review）开启

**payload 示例（开启后）：**
```python
{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 8192,
    "thinking": {"type": "enabled", "budget_tokens": 16000},
    "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
    "messages": [{"role": "user", "content": user}],
}
```

## DeepSeek / Effort 模式

DeepSeek V4+ 通过 Anthropic 兼容端点支持 Extended Thinking，使用 `output_config.effort` 定性控制思考深度：

```python
payload["thinking"] = {"type": "enabled"}
payload["output_config"] = {"effort": "high"}   # "low" / "medium" / "high" / "max"
```

## Prompt Caching（Anthropic 专属）

`_call_claude()` 中 system prompt 使用数组格式 + `cache_control: {"type": "ephemeral"}`。同一 system prompt 在 **5 分钟内**重复使用时，输入 token 扣费大幅降低（缓存写入 ×1.25 价格，命中 ×0.1 价格）。无需任何配置，程序自动启用。

## 熔断器（Circuit Breaker）

`llm/circuit_breaker.py` 实现端点级熔断：连续 3 次失败后熔断 60 秒，半开状态允许 1 次探测。

## 输出截断自动重试

`_generate_llm_content()` 在收到 LLM 响应后检测输出中是否含 `_TRUNCATION_MARKER`。若存在，自动以 `max_tokens × 1.5` 重试一次。二次截断则保留第一次结果并在末尾追加截断警告。

## 内容过滤安抚重试

`_call_llm_with_retry()` 在返回空内容时，追加安抚指令到 system prompt 尾部并重试一次。安抚成功后返回重试结果；失败则尝试 fallback provider。

## 会话级 Token 追踪与用量展示

### 数据结构

`llm/session.py` 维护全局线程安全（`threading.Lock`）的 `_session_usage` 字典：

```python
_session_usage: dict[str, Any] = {
    "input_tokens": 0,          # 累计输入 token
    "output_tokens": 0,         # 累计输出 token
    "cache_hit_tokens": 0,      # 累计缓存命中 token
    "total_cost": 0.0,          # 累计费用
    "currency": "CNY",          # 货币标识
    "model": "未指定",
    "models": [],               # 去重模型列表
    "call_count": 0,            # API 调用次数（缓存命中不计入）
    "per_module": {},           # 按模块细分
}
```

### 模块级记录（per_module）

| 模块键 | 覆盖范围 |
|:------|:---------|
| `global_macro` | 全球政经局势 |
| `expert_review` | 智囊团深度复盘 |
| `health_check` | 持仓体检报告 |
| `penetration_deep` | 穿透深度分析 |
| `news_correlation` | 新闻 LLM 关联分析（可选） |

### 数据收集流程

```
API 调用响应 (usage dict)
    │
    ├─► _process_success_response()          [api.py]
    │       ├─► _track_session_usage()        [session.py]
    │       └─► _record_per_module()          [session.py]
    │
    ├─► _handle_cache_hit()                   [skeleton.py]
    │       └─► _record_per_module()          [session.py]  cached=True
    │
    ├─► _precheck_one_cache()                 [generators_orchestrator.py]
    │       └─► _record_per_module()          [session.py]
    │
    └─► _finalize_news_token_usage()          [generators_news.py]
            └─► _record_per_module(key="news_correlation")
```

### 用量数据到报告输出

```
_session_usage (dict)
    ├─► format_session_usage()               [session.py]
    │     返回展示用格式化字典
    ├─► Excel 报告                           [excel_llm_usage.py]
    ├─► HTML 报告                            [html_writer.py + template]
    └─► TUI 终端                             [tui_handlers.py]
```

### 定价匹配规则

`llm/pricing.py` 中 `_estimate_cost()` 按以下优先级匹配模型定价：

1. 精确匹配（模型全名小写 → 定价表中同名）
2. 前缀匹配（`deepseek-v4-flash-xxx` → `deepseek-v4-flash`）
3. 均不匹配 → 回退到 `MODEL_PRICING` 中的 `"default"` 费率

费用计算：
```
费用 = (input_tokens - cache_hit_tokens) / 1_000_000 * input_rate
     + output_tokens / 1_000_000 * output_rate
     + cache_hit_tokens / 1_000_000 * input_cache_hit_rate
```

### 会话生命周期

```
main.py 入口（菜单 L 选中文件后）
  ├─ reset_session_usage(config)
  ├─ generate_all_llm_content(...)
  ├─ generate_excel_report(...)
  ├─ write_html_report(...)
  └─ _print_llm_session_usage()
```

每次菜单 L 生成报告均为独立会话。会话开始时 `reset_session_usage()` 清空数据并从 `llm_settings.json` 重新加载定价表和货币配置。
