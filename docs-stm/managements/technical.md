# 个人投资分析报告生成小助手 — 技术设计

创建日期：2026-06-28
最后更新：2026-07-02（v0.2.62 — pytest 标记层级体系 + 测试文件目录分组搬迁）

---

## 技术架构总览

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  持仓 xlsx   │ ──→ │  数据获取层   │ ──→ │  报告生成层   │
│ (reader.py)  │     │ (fetcher/) │     │ (report/)    │
└─────────────┘     └──────┬───────┘     └──────────────┘
                          │
                    ┌──────▼───────┐
                    │   缓存层      │
                    │ (cache.py)   │
                    └──────────────┘
```

### 核心模块职责

| 模块 | 职责 | 文件 |
|------|------|------|
| TUI 入口 | 主循环、流程编排 | `src/python/main.py` |
| 菜单交互 | 菜单定义、渲染、导航 | `src/python/tui_menu.py` |
| 菜单功能执行 | 命令处理器、各功能入口 | `src/python/tui_handlers.py` |
| 配置管理 | config.json + llm_key.json（敏感字段）/ llm_settings.json（非敏感参数）读写、mtime 缓存 | `src/python/config.py` |
| 缓存引擎 | 泛用 JSON 缓存、TTL、指纹失效、过期清理 | `src/python/cache.py` |
| 数据获取 | Provider Chain 路由、fallback、缓存预热 | `src/python/fetcher/` |
| 持仓读取 | xlsx 解析、多工作表、列校验 | `src/python/reader.py` |
| LLM 客户端 | Claude / OpenAI / DeepSeek API 调用 | `src/python/llm/` |
| 报告生成 | Excel (openpyxl) + HTML (Jinja2) | `src/python/report/*.py` |

---

## 数据源一览

| 用途 | 主链路 API | 备用链路 | Provider 文件 |
|------|-----------|---------|-------------|
| 场内实时/收盘价 | 腾讯财经 `qt.gtimg.cn` | 东方财富 `push2.eastmoney.com` | `tencent.py` |
| 场外基金净值 | 东方财富 `api.fund.eastmoney.com` | 天天基金 `fundf10.eastmoney.com` | `eastmoney.py` |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — | `tiantian.py` |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — | `tiantian.py` |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | 新浪财经 `hq.sinajs.cn` | `tencent.py` |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析） | 腾讯财经 `qt.gtimg.cn` | `sina.py` |
| 财经新闻（新浪） | 新浪财经 `feed.mix.sina.com.cn` | — | `sina_news.py` |
| 财经新闻（东方财富） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — | `eastmoney_news.py` |
| 财经新闻（财联社） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — | `cls_news.py` |
| 财经新闻（华尔街见闻） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives`（JSON API，无需鉴权） | — | `wallstreetcn_news.py` |
| 财经新闻（akshare） | akshare 封装：财新网 + CCTV | — | `akshare_news.py` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com` 三级行业 + 概念板块 | — | `eastmoney_industry.py` |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — | `akshare_extras.py` |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — | `akshare_extras.py` |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — | `akshare_extras.py` |

> 指数数据由 `fetcher/index.py` 直调 Provider，**不走 Provider Chain**。双链路自动 fallback：A 股指数腾讯→新浪，美股指数新浪→腾讯。双链路均失败时降级过期缓存。

> 各新闻源的完整端点格式及通用数据源说明参见 [数据源一览](../manuals/datasource-and-folders.md)。

---

## 缓存策略

详见 [配置指南缓存章节](../manuals/how-to-config.md#cache_ttl-可调参数)。

### 新增：行业/概念缓存

| 文件名 | 用途 | 默认 TTL | 清除方式 |
|--------|------|---------|---------|
| `industry_{code}.json` | 单只证券的行业分类和概念板块归属 | 7 天 | 菜单 [1] 清理或过期自动清理 |

---

## 模块技术要点

### 资产穿透TOP10

- `compute_penetration_top10()` 纯计算函数，不依赖 openpyxl
- 分类逻辑（QDII/ETF/联接/债券/主动/直接持股）基于代码前缀 + 名称规则
- 板块分类 `classify_sector()` 使用静态关键词映射，同时支持 API 行业数据补充
- 调用 `batch_fetch_industry_data()` 为穿透结果注入行业信息（覆盖静态关键词的局限）

### 财经新闻热点与持仓关联分析

- 5 源并行获取（ThreadPoolExecutor max_workers=5）
- 新闻缓存 `news_{md5}.json`，15 分钟 TTL，MD5 指纹含关键词/参数
- 关键词提取：持仓名称片段 + 代码 + 穿透资产 + **行业名称 + 概念板块**
- 关键词富化 4 种类型：持仓(0) → 穿透(1) → 概念(2) → 行业(3)
- 概念类型：来源为东方财富 push2 API 的行业分类和概念板块
- HTML 富化显示：蓝(持仓) / 紫(穿透) / 橙(概念) / 灰(行业)
- LLM 二次关联分析（可选）：`enabled_llm.news_correlation` 配置开启

### 行业/概念数据流

```
持仓列表 + 穿透资产
    ↓ 提取所有唯一代码
batch_fetch_industry_data(codes)
    ↓ API / 缓存
industry_{code}.json
    ↓
build_news_data():
  1. 行业名/概念名 → 追加到关键词列表 → 提高新闻匹配率
  2. industry_data → _build_keyword_lookup() → "concept" 类型条目
  3. _enrich_keywords_for_item() → 显示 "XX[概念]"
    ↓
穿透模块:
  4. batch_fetch_industry_data() → 覆盖 sector 字段 → 板块列显示 API 数据

penetration_sector = fetch_industry_data(code).industry  // API优先
                  or classify_sector(name, code)         // 关键词回退
```

---

## 目录结构

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── python/                   # 源代码
│   │   ├── __init__.py
│   │   ├── cache.py              # 缓存引擎
│   │   ├── config.py             # 配置读写
│   │   ├── constants.py          # 共享常量
│   │   ├── fetcher/               # 数据获取调度
│   │   ├── handlers_cache.py     # TUI 缓存管理命令
│   │   ├── handlers_config.py    # TUI 配置管理命令
│   │   ├── handlers_report.py    # TUI 报告生成命令
│   │   ├── http_client.py        # HTTP 客户端工厂
│   │   ├── llm/                  # LLM 集成（9 子模块）
│   │   ├── logger.py             # 日志模块
│   │   ├── main.py               # TUI 入口 + 菜单循环
│   │   ├── market_hours.py       # A 股交易时段判断
│   │   ├── models.py             # 数据模型
│   │   ├── providers/            # 数据源提供商
│   │   ├── reader.py             # 持仓 Excel 解析
│   │   ├── registry.py           # 中央注册表
│   │   ├── report/               # 报告生成
│   │   ├── tui.py                # 键盘输入封装
│   │   ├── tui_handlers.py       # 菜单功能执行（通用辅助）
│   │   └── tui_menu.py           # 菜单交互
│   └── test/                     # 测试（按标记分组目录，1938+ passed）
│       ├── conftest.py           # pytest 配置 + 15 个分层标记注册
│       ├── helpers.py            # 测试辅助工具
│       ├── unit/                 # 单元测试（8 子组，1810 项）
│       ├── scenario/             # 场景测试（4 子组，107 项）
├── data/                         # 运行时数据
├── reports/                      # 生成报告
├── logs/                         # 程序日志
├── docs-stm/                     # 项目管理文档
├── scripts/                      # 启动脚本
├── CLAUDE.md / README.md / requirements.txt
```

> 完整目录树（含所有 providers/ 和 report/ 子文件）见 [数据源一览 & 目录结构](../manuals/datasource-and-folders.md#目录结构)。

---

## LLM 客户端技术要点

`src/python/llm/` 包拆分架构（原 `llm_client.py` 解耦为 9 子模块，含 skeleton.py 共享骨架）：

| 模块 | 职责 |
|------|------|
| `api.py` | API 调用路由 (Claude/OpenAI)、重试、截断检测、熔断器集成 |
| `prompts.py` | System Prompt 常量与构建函数 |
| `generators.py` | LLM 生成编排（4+1 模块：4 个 LLM 分析模块 + 可选的新闻关联分析） |
| `pricing.py` | 模型定价加载、费用估算 |
| `session.py` | 会话用量累计、追踪 |
| `circuit_breaker.py` | 端点熔断器 |
| `fingerprint.py` | 各种缓存指纹计算 |
| `markdown.py` | Markdown→HTML 渲染 |
| `skeleton.py` | 共享生成骨架（_generate_llm_content / _is_llm_module_enabled / _generate_llm_module / _run_batch_mode） |

`__init__.py` 导出所有公共 API 保持向后兼容。

- **统一入口** `_call_llm()` 按 `provider` 路由到 `_call_claude()` 或 `_call_openai()`
- **`_call_llm_with_retry()`** 共享重试/超时/错误处理骨架
- **`_generate_llm_content()` / `_generate_llm_module()`** 共享骨架函数（`skeleton.py`），封装缓存检查 + 调用 + markdown→HTML + 写入的 85% 公共逻辑
- **`generate_global_macro()` / `generate_expert_review()`** 仅保留 prompt 构建 + 配置解析，其余委托 `_generate_llm_module()`（`skeleton.py`）

### Extended Thinking（v0.2.22+）

`_call_claude()` 通过 `llm_config` 参数读取 `thinking_enabled_{模块}` 配置，为 Claude API 注入 `thinking` payload 以实现深度推理。

**关键逻辑：**
- `thinking_budget` 与 `max_tokens` 是独立参数：前者控制内部推理 token（不可见），后者控制最终输出 token
- API 约束：`thinking_budget` ≥ `max_tokens + 1024`，代码中 `_call_claude()` 自动兜底不足时补到 `max_tokens + 4096`
- Extended Thinking 与 `temperature` 互斥，开启后自动 `payload.pop("temperature", None)`
- 模块后缀通过 `config_field` 解析：`config_field.replace("max_tokens_", "")` → `"global_macro"` / `"expert_review"` / `"news_correlation"`
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

### DeepSeek / Effort 模式

DeepSeek V4+（`deepseek-v4-*` / `deepseek-chat`）通过 Anthropic 兼容端点支持 Extended Thinking，但不使用 `budget_tokens`，而使用 `output_config.effort` 定性控制思考深度：

```python
payload["thinking"] = {"type": "enabled"}
payload["output_config"] = {"effort": "high"}   # "low" / "medium" / "high" / "max"
```

模型名大小写敏感：代码按全小写前缀匹配（`deepseek-v4-`），文档示例统一使用 `deepseek-v4-flash`。

### Prompt Caching（Anthropic 专属）

`_call_claude()` 中 system prompt 使用数组格式 + `cache_control: {"type": "ephemeral"}`。同一 system prompt 在 **5 分钟内**重复使用时，输入 token 扣费大幅降低（缓存写入 ×1.25 价格，命中 ×0.1 价格）。无需任何配置，程序自动启用。

### 熔断器（Circuit Breaker）

`llm/circuit_breaker.py` 实现端点级熔断：连续 5 次失败后熔断 60 秒，半开状态允许 1 次探测。通过 `_cb_is_open()` / `_cb_record_failure()` / `_cb_record_success()` 暴露接口，`_call_llm_with_retry()` 在每次请求前检查熔断状态。

### 会话级 Token 追踪与用量展示

#### 数据收集架构

`llm/session.py` 维护全局线程安全（`threading.Lock`）的 `_session_usage` 字典，作为单个报告生成会话中所有 LLM 调用的累计存储器。

**数据结构：**
```python
_session_usage: dict[str, Any] = {
    "input_tokens": 0,          # 累计输入 token
    "output_tokens": 0,         # 累计输出 token
    "cache_hit_tokens": 0,      # 累计缓存命中 token
    "total_cost": 0.0,          # 累计费用
    "currency": "CNY",          # 货币标识
    "model": "未指定",           # 最近使用的模型名
    "models": [],               # 所有出现过的模型名（去重）
    "call_count": 0,            # API 调用次数（缓存命中不计入）
    "per_module": {},           # 按模块细分
}
```

**模块级记录（`per_module`）** — 每个 LLM 子模块一个条目，共 5 个键：

| 模块键 | 覆盖范围 | 说明 |
|:------|:---------|:-----|
| `global_macro` | 全球政经局势 | 始终启用 |
| `expert_review` | 智囊团深度复盘 | 始终启用 |
| `health_check` | 持仓体检报告 | v0.2.29+ |
| `penetration_deep` | 穿透深度分析 | v0.2.30+ |
| `news_correlation` | 新闻 LLM 关联分析 | 仅 `enabled_llm.news_correlation = true` 时启用 |

每个模块条目包含：
```python
{
    "model": str,              # 实际使用的模型名
    "input_tokens": int,       # 该模块输入 token
    "output_tokens": int,      # 该模块输出 token
    "cache_hit_tokens": int,   # 缓存命中 token
    "cached": bool,            # 是否来自缓存（无实际 API 调用）
    "thinking": bool,          # 是否启用 Extended Thinking
    "cost": float,             # 该模块费用估算
    "endpoint": str,           # API 端点 URL
}
```

#### 数据收集流程

```
API 调用响应 (usage dict)
    │
    ├─► _process_success_response()          [api.py]
    │       │
    │       ├─► _track_session_usage()        [session.py]
    │       │     ├─ input_tokens += usage.input_tokens
    │       │     ├─ output_tokens += usage.output_tokens
    │       │     ├─ cache_hit_tokens += cache_read
    │       │     ├─ call_count += 1
    │       │     ├─ models.append(model)     (去重)
    │       │     └─ total_cost += _estimate_cost(...)
    │       │
    │       └─► _record_per_module()          [session.py]
    │             └─ per_module[key] ← {model, tokens, cached=False, ...}
    │
    ├─► _handle_cache_hit()                   [skeleton.py]
    │       └─► _record_per_module()           [session.py]
    │             └─ per_module[key] ← {model, tokens, cached=True, ...}
    │                                           (调用次数不计入 call_count)
    │
    ├─► _precheck_one_cache()                 [generators.py]
    │       └─► _record_per_module()           [session.py]
    │
    └─► _finalize_news_token_usage()          [generators.py]
            └─► _record_per_module(key="news_correlation")
```

**覆盖范围说明：**
- 每次 **成功的 API 调用**（包括重试后的成功响应）均触发 `_track_session_usage()` 和 `_record_per_module()`
- **缓存命中**（从缓存文件读取 LLM 结果而非调用 API）仅触发 `_record_per_module()`，标记 `cached=True`，不计入 `call_count`
- **模块失败/禁用**（API Key 未配置、熔断器打开、`enabled_llm.{key}=false`）不产生任何用量数据
- **新闻 LLM 关联分析**（`news_correlation`）由 `generators.py` 中 `_finalize_news_token_usage()` 单独汇总，以兼容其在新闻处理流程中的独立缓存和批处理逻辑

#### 用量数据到报告输出

```
_session_usage (dict)
    │
    ├─► format_session_usage()               [session.py]
    │     返回展示用格式化字典：
    │     {
    │       "has_usage": bool,         # 是否有任何调用记录
    │       "call_count": int,         # API 调用次数
    │       "model_display": str,      # "deepseek-v4-flash" 或 "modelA / modelB"
    │       "input_tokens": str,       # 格式化为 "25,432"
    │       "output_tokens": str,
    │       "total_tokens": str,       # 输入+输出
    │       "cache_hit_tokens": str,   # 有条件显示（>0 时）
    │       "cost": float,
    │       "cost_display": str,       # "¥0.0456"
    │       "currency": str,
    │       "per_module": dict,        # 各模块原始数据（由消费方自行格式化为明细表）
    │     }
    │
    ├─► Excel 报告                          [excel_generator.py + summary.py]
    │      _build_llm_usage_sheet()
    │        → get_session_usage()
    │        → format_session_usage()
    │        → write_llm_usage_sheet()    写入页签 12
    │        → write_llm_usage_block()    追加到汇总页
    │        → write_llm_module_status_block()  追加模块状态
    │
    ├─► HTML 报告                           [html_writer.py + template]
    │      _render_llm_module_info()
    │        → _build_module_info_list()   构建模块明细（含状态标签）
    │        → get_session_usage()
    │        → format_session_usage()
    │        → Jinja2 模板变量：llm_session_usage / llm_module_info / llm_endpoint
    │
    └─► TUI 终端                            [tui_handlers.py]
           _print_llm_session_usage()
             → f"本会话 LLM 累计：{calls} 次调用，{total_tok:,} tokens，费用 {symbol}{cost:.4f}"
```

#### 用量展示与 LLM 分析章节的关系

LLM API 用量页签/章节（页签 12 / HTML 底部）**不是独立的 LLM 生成模块**，而是对同一会话中所有 LLM 分析章节调用量的被动统计汇总。

| 方面 | 设计决策 |
|:-----|:---------|
| **触发条件** | 仅菜单 L（全系列完整版报告），与 LLM 分析章节共进退 |
| **无用量不显示** | 无任何 LLM 调用时（API Key 未配置或所有模块已禁用），该页签/章节整个跳过不渲染 |
| **全缓存场景** | 所有模块均为缓存命中（无实际 API 调用），汇总区标注"无新增 API 调用，数据全部来自缓存"，模块明细表正常显示 |
| **与 LLM 章节的物理位置** | Excel 中作为页签 12（最后一位），HTML 中在所有 LLM 分析章节之后渲染 |
| **新闻 LLM 关联分析** | 当 `enabled_llm.news_correlation = true` 时，其 token 使用量计入 `per_module["news_correlation"]`，与另外 4 个 LLM 主模块在同一明细表中展示 |

#### 展示格式

**汇总区字段（顶部）：**

| 字段 | 数据来源 | 格式 |
|:-----|:---------|:-----|
| API 调用次数 | `call_count` | 整数 |
| 模型 | `models` 去重列表 | `model1 / model2` 格式 |
| 输入 Token | `input_tokens` | 千分位格式化 |
| 输出 Token | `output_tokens` | 千分位格式化 |
| 总 Token | `input_tokens + output_tokens` | 千分位格式化 |
| 缓存命中 Token | `cache_hit_tokens`（>0 显示） | 千分位格式化 |
| 累计费用 | `total_cost` + 货币符号 | `¥0.0456` |

**模块明细表字段（每模块一行）：**

| 列 | 数据来源 | Excel 格式 | HTML 格式 |
|:---|:---------|:-----------|:----------|
| 模块 | 模块键映射中文名 | 文本 | 文本 |
| 状态 | `per_module[key].cached` + 模块失败标记 | 带填充色 | 颜色标签（成功/缓存/失败/禁用） |
| 模型 | `per_module[key].model` | 文本 | 文本 |
| 输入 Token | `per_module[key].input_tokens` | 千分位 | 千分位 |
| 输出 Token | `per_module[key].output_tokens` | 千分位 | 千分位 |
| 缓存命中 Token | `per_module[key].cache_hit_tokens` | 千分位或 `—` | 同左 |
| 费用 | `per_module[key].cost` | 格式化货币或"已计入原调用" | 同左 |
| LLM 缓存 | `per_module[key].cached` | ✓ 或 — | ✓ 或 — |
| Thinking | `per_module[key].thinking` | ✓ 或 — | ✓ 或 — |

**状态标签颜色规范：**

| 状态 | 含义 | Excel 填充色 | HTML 标签色 |
|:-----|:-----|:------------|:------------|
| ✅ 成功 | 有实际 API 调用且成功返回 | #E8F5E9（浅绿） | #27ae60（绿） |
| 📦 缓存 | 结果来自缓存文件，无实际 API 调用 | —（默认） | #2e86c1（蓝） |
| ⛔ 失败 | API 调用失败，返回占位文本 | #FFEBEE（浅红） | #e74c3c（红） |
| 🚫 已禁用 | `enabled_llm.{key} = false`，模块被跳过 | #F5F5F5（浅灰） | #95a5a6（灰） |

#### 定价匹配规则

`llm/pricing.py` 中 `_estimate_cost()` 按以下优先级匹配模型定价：

1. 精确匹配（模型全名小写 → 定价表中同名）
2. 前缀匹配（`deepseek-v4-flash-xxx` → `deepseek-v4-flash`）
3. 均不匹配 → 回退到 `MODEL_PRICING` 中的 `"default"` 费率

费用计算（元/百万 token）：
```
费用 = (input_tokens - cache_hit_tokens) / 1_000_000 * input_rate
     + output_tokens / 1_000_000 * output_rate
     + cache_hit_tokens / 1_000_000 * input_cache_hit_rate
```

默认定价表见 `src/python/constants.py:MODEL_PRICING`，用户可通过 `llm_settings.json` 的 `pricing` 字段覆盖。货币符号通过 `pricing.currency` 配置（默认 `CNY → ¥`）。

#### 会话生命周期

```
main.py 入口（菜单 L 选中文件后）
  │
  ├─ reset_session_usage(config)     // 清空 _session_usage，重新加载定价
  │
  ├─ generate_all_llm_content(...)   // 并发生成 4+1 个 LLM 模块
  │     ├─ 每个模块调用 → _track + _record（API 调用或缓存命中）
  │     └─ ...
  │
  ├─ generate_excel_report(...)      // 写入页签 12 + 汇总页补充区块
  │     └─ _build_llm_usage_sheet()
  │
  ├─ write_html_report(...)          // 渲染 HTML 底部
  │     └─ _render_llm_module_info()
  │
  └─ _print_llm_session_usage()      // TUI 一行摘要
```

每次菜单 L 生成报告均为独立会话。会话开始时 `reset_session_usage()` 清空数据并从 `llm_settings.json` 重新加载定价表和货币配置。

---

## 配置管理技术要点

### 配置分层

```
config.json (基础配置)  ──→ get_config() 内存缓存，按 mtime 自动失效
llm_settings.json (非敏感) ──→ get_llm_config() 合并读取，联合 mtime 失效
llm_key.json (敏感密钥)    ──→ 覆盖 llm_settings.json 的同名字段
```

### JSON 注释支持

`config.py:_strip_json_comments()` 逐字符扫描，支持 `//` 单行注释和 `/* */` 多行注释。正确处理字符串内的转义引号，不会将字符串内的 `//` / `/*` 误伤。

### 原子写入

配置文件（`set_config`）和缓存写入（`_write_atomic`）均使用 `tempfile.mkstemp` + `os.replace` 模式：
- 先写入临时文件，成功后 `os.replace` 原子替换原文件
- 防止断电/崩溃导致文件截断（半写文件）
- 缓存文件 PermissionError 时自动降级到直接写入（Windows 兼容）

---

## 市场时段判断（market_hours.py）

三层 fallback 架构：

```
第 1 层：config.json market_hours.start / end 手动覆盖
第 2 层：东方财富 push2 API 实时交易状态（盘中缓存 60s，盘后 7 天）
第 3 层：内置默认值（北京时间 09:30-11:30 + 13:00-15:00，排除周末）
```

**时区安全**：所有 `datetime.now()` 调用均使用 `timezone(timedelta(hours=8))` 北京时区，防止 UTC 服务器上时段判断全错。

**消费方**：
- `cache.py:get_ttl()` → 交易时段内 `market_hour_aware` 类型自动使用 `market_hour_ttl`（默认 30s）
- `report/market_value.py:is_market_open()` → 取价方式标签判断（委派 market_hours 实现）
- `report/market_value.py:is_midday_break()` → 午间休市识别

---

## 缓存安全机制

### 原子写入
- 先通过 `tempfile.mkstemp` 写临时文件
- 成功后再 `os.replace` 原子替换原文件
- 磁盘满时自动回退到 gzip 压缩以节省空间

### 文件损坏恢复
- `_read_cache()` 解析失败时自动 `os.remove` 损坏文件
- 记录 WARNING 日志，下次调用时重新拉取

### 并发安全
- `os.replace` 保证读取方不会看到半写文件
- 多线程同时 `get()` 同一 key 可能产生 TOCTOU 空窗（两线程均认为缓存过期，均拉取 API），但通过 `_write_atomic` 保证同时写入时只有一个生效

### 路径安全
- `_cache_path(key)` 对 key 做 `replace("..", "_")` 防目录穿越
- 缓存目录不存在时 `os.makedirs(dir, exist_ok=True)` 自动创建

### 大文件 gzip 压缩
- `set()` 中数据 ≥ 100KB 时自动使用 `.json.gz` 压缩
- 节省约 80-90% 磁盘空间（`profit_forecast` 等全量数据受益最大）
- 读取时透明解压（`_read_cache()` 根据后缀自动判断）

### 缓存分组机制

通过 `registry.py` 的 `cache_groups` 字段定义分组：
- **preload（6 模块）**：price, index, llm_global_macro, llm_expert_review, llm_health_check, llm_penetration_deep → 菜单 `[2]` 触发清除
- **refresh（9 模块）**：fund_rank, fund_hold, industry, news, llm_news_correlation, profit_forecast, sector_flow, dividend, benchmark → 菜单 `[1]` 触发清除
- **独立模块**：tracking, calendar → 无分组保护，不被菜单缓存命令误删

---

## 模块间依赖关系

```
reader.py (持仓解析)
  → models.py (Holding/DetailRow 数据模型)
  → fetcher/price.py (价格获取)
  → fetcher/index.py (指数获取)
  → fetcher/fund.py (基金数据获取)
  → fetcher/industry.py (行业分类)
  → providers/* (各数据源 API 实现)
  → cache.py (缓存读写)
    → market_hours.py (交易时段感知 TTL)
    → registry.py (TTL 默认值、缓存分组)

report/excel_generator.py (Excel 编排)
  → report/summary.py, market_value.py, category.py, penetration.py,
    fund_performance.py, news_correlation.py, early_warning.py,
    llm_content.py (各页签写入)
  → report/excel_writer.py, styles.py (通用写入/样式)
  → report/html_writer.py (HTML 编排)
    → report/html_builders.py (数据构建器)
    → tmpl/report_template.html (Jinja2 模板)

llm/generators.py (LLM 编排)
  → llm/skeleton.py (共享生成骨架)
    → llm/api.py (API 调用+重试+截断+熔断)
    → llm/prompts.py (System Prompt + User Prompt 构建)
    → llm/fingerprint.py (缓存指纹)
    → llm/markdown.py (Markdown→HTML)
    → llm/pricing.py, session.py (定价+用量)
  → cache.py (LLM 结果缓存)

config.py → registry.py (注册表驱动的 TTL/分组/键名)
handlers_*.py → 各模块入口函数编排
```
