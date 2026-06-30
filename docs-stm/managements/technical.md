# 投资分析报告小工具 — 技术设计

创建日期：2026-06-28
最后更新：2026-06-30

---

## 技术架构总览

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  持仓 xlsx   │ ──→ │  数据获取层   │ ──→ │  报告生成层   │
│ (reader.py)  │     │ (fetcher.py) │     │ (report/)    │
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
| 数据获取 | Provider Chain 路由、fallback、缓存预热 | `src/python/fetcher.py` |
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
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | — | `tencent.py` |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析） | — | `sina.py` |
| 财经新闻（新浪） | 新浪财经 `feed.mix.sina.com.cn` | — | `sina_news.py` |
| 财经新闻（东方财富） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — | `eastmoney_news.py` |
| 财经新闻（财联社） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — | `cls_news.py` |
| 财经新闻（华尔街见闻） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives`（JSON API，无需鉴权） | — | `wallstreetcn_news.py` |
| 财经新闻（akshare） | akshare 封装：财新网 + CCTV | — | `akshare_news.py` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com` 三级行业 + 概念板块 | — | `eastmoney_industry.py` |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — | `akshare_extras.py` |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — | `akshare_extras.py` |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — | `akshare_extras.py` |

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
│   │   ├── main.py               # TUI 入口 + 菜单循环
│   │   ├── config.py             # 配置读写
│   │   ├── registry.py           # 中央注册表（模块配置键名/缓存前缀/TTL 统一管理）
│   │   ├── cache.py              # 缓存引擎
│   │   ├── fetcher.py            # 数据获取调度
│   │   ├── reader.py             # 持仓 Excel 解析
│   │   ├── llm/                  # LLM 集成（8 子模块：api/pricing/session/circuit_breaker/fingerprint/markdown/generators/prompts）
│   │   ├── constants.py          # 共享常量（CACHE_DAILY/WEEKLY/MONTHLY、模型定价）
│   │   ├── models.py             # 数据模型（Holding dataclass）
│   │   ├── logger.py             # 日志模块
│   │   ├── tui.py                # 键盘输入封装
│   │   ├── tui_menu.py           # 菜单交互
│   │   ├── tui_handlers.py       # 菜单功能执行
│   │   ├── providers/            # 数据源提供商
│   │   │   ├── __init__.py
│   │   │   ├── akshare_extras.py
│   │   │   ├── akshare_news.py
│   │   │   ├── cls_news.py
│   │   │   ├── eastmoney.py
│   │   │   ├── eastmoney_industry.py
│   │   │   ├── eastmoney_news.py
│   │   │   ├── news_aggregator.py
│   │   │   ├── news_correlator.py
│   │   │   ├── news_keywords.py
│   │   │   ├── news_sources.py
│   │   │   ├── sina.py
│   │   │   ├── sina_news.py
│   │   │   ├── tencent.py
│   │   │   ├── tiantian.py
│   │   │   └── wallstreetcn_news.py
│   │   ├── report/               # 报告生成
│   │   │   ├── __init__.py
│   │   │   ├── category.py
│   │   │   ├── early_warning.py        # 智能预警（行业资金流向联动 + 新闻情绪聚合）
│   │   │   ├── excel_writer.py
│   │   │   ├── fund_performance.py
│   │   │   ├── html_writer.py
│   │   │   ├── llm_content.py
│   │   │   ├── market_value.py
│   │   │   ├── news_correlation.py
│   │   │   ├── penetration.py
│   │   │   ├── styles.py
│   │   │   └── summary.py
│   │   ├── tmpl/                 # HTML 报告模板（report/ 的同级目录）
│   │   │   └── report_template.html
│   └── test/                     # 测试
│       ├── __init__.py
│       └── test_*.py（26 个）
├── data/
│   ├── holdings/                 # 持仓 xlsx 文件
│   ├── cache/                    # API 响应缓存
│   └── config/                   # 配置文件（config.json, llm_key.json, llm_settings.json）
├── reports/                      # 生成报告（最新版+按日期存档）
├── logs/                         # 程序日志（app.log）
├── docs-stm/                     # 项目管理文档
│   ├── plan/                     # 计划/设计文件
│   ├── tmp/                      # 临时/过程文件
│   └── managements/
│       ├── plan.md               # 实现计划
│       ├── requirements.md       # 需求文档
│       ├── testplan.md           # 测试计划
│       ├── changelog.md          # 变更日志
│       └── review-findings.md    # 自审记录
├── scripts/
│   ├── launch.ps1                # Windows 启动脚本
│   └── launch.sh                 # Linux 启动脚本
├── CLAUDE.md                     # Claude Code 指引
├── README.md                     # 用户文档（项目根目录）
└── requirements.txt
```

---

## LLM 客户端技术要点

`src/python/llm/` 包拆分架构（原 2550 行 `llm_client.py` 解耦为 8 子模块）：

| 模块 | 职责 |
|------|------|
| `api.py` | API 调用路由 (Claude/OpenAI)、重试、截断检测、熔断器集成 |
| `prompts.py` | System Prompt 常量与构建函数 |
| `generators.py` | LLM 生成编排（5 模块 + 全量生成） |
| `pricing.py` | 模型定价加载、费用估算 |
| `session.py` | 会话用量累计、追踪 |
| `circuit_breaker.py` | 端点熔断器 |
| `fingerprint.py` | 各种缓存指纹计算 |
| `markdown.py` | Markdown→HTML 渲染 |
| `content.py` | 已删除（原兼容存根） |

`__init__.py` 导出所有公共 API 保持向后兼容。

- **统一入口** `_call_llm()` 按 `provider` 路由到 `_call_claude()` 或 `_call_openai()`
- **`_call_llm_with_retry()`** 共享重试/超时/错误处理骨架
- **`_generate_llm_content()`** 共享骨架函数，封装缓存检查 + 调用 + markdown→HTML + 写入的 85% 公共逻辑
- **`generate_global_macro()` / `generate_expert_review()`** 仅保留 prompt 构建 + 配置解析，其余委托 `_generate_llm_content()`

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
