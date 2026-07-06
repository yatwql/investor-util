# D 迭代：数据降级分层治理 — 详细设计

创建日期：2026-07-06
状态：设计阶段（Phase 0）

> 本文件是 D 迭代的完整架构设计文档，在开始编码前需经评审确认。
> 迭代概要见 [`docs-stm/managements/plan.md`](../managements/plan.md) → D 迭代。

---

## 1. 数据分层模型（T1 / T2 / T3 / T4）

### 1.1 分层总览

分层依据：**数据源稳定性 + 同源归并**，而非纯业务价值。

```
T1 [核心主数据]             读取不到 → 报告无意义
  ├── 持仓 xlsx 文件
  └── 价格/净值（场内实时价 + 场外基金净值）
      已有 Provider Chain + 过期缓存降级
      D 迭代范围外，保持不动

T2 [稳定增强数据]           读取不到 → 列级 `--` + ⚠ 页脚状态摘要
  ├── 指数行情（tencent → sina）
  ├── 基金排名（天天基金 JS 变量）
  ├── 基金持仓穿透（天天基金 HTML）
  └── 基金业绩基准（东财 HTML + 知识库）
      源稳定，偶发失败，D 迭代 Phase 1

T3 [不稳定增强数据]         读取不到 → 列级 `--` + ℹ 页脚状态摘要 + 缓存 TTL 加倍
  └── 行业分类/概念板块（push2 API）
      已知频繁失败，但业务价值中上（穿透板块列 + 新闻关键词召回）
      D 迭代 Phase 1

T4 [附加增值数据]           读取不到 → 模块级占位/隐藏
  ├── akshare 数据（盈利预测 / 分红股息率 / 资金流向）
  ├── 财经新闻（5 源并行）
  ├── 智能预警
  ├── B 系列基金深度分析（基金经理/重合度/集中度/风格）
  └── LLM 智能分析（4+1 模块）
      已有一些 guard，但降级行为零散
      ✓ D 迭代 Phase 2-3 重点
```

> **跨层依赖说明：** T3（push2 行业分类）的行业标签被 `news_correlation` 模块用于关键词增强匹配。
> T3 失败时新闻模块的关键词召回广度会下降，但不会完全失效（仍有基金名称/代码匹配）。
> 设计时在 §4.6 定义了 T3→新闻的跨层状态通知机制。

### 1.2 T1 层：核心主数据

| 数据 | 获取方式 | 当前降级 | D 迭代处理 |
|:-----|:---------|:---------|:----------|
| 持仓 xlsx | 本地文件解析 | 文件不存在/格式错误→TUI 报错提示 | 不修改 |
| A 股价格（股票/ETF）| tencent → eastmoney → 过期缓存 | Provider Chain + 7天内过期缓存 | 不修改 |
| 场外基金净值 | eastmoney → tiantian → 过期缓存 | 同上 | 不修改 |

**为什么 T1 不动：** 价格/净值是市值核算的输入，市值算不出来整个报告失去意义。
当前的 Provider Chain + 过期缓存双降级已经足够。
即使所有 API 断网，7 天内缓存也能出报告。更进一步（离线内置备选价格）不现实且收益低。

### 1.3 T2/T3 层：增强数据（稳定 + 不稳定）

T2 和 T3 共享相同的降级表现（列级 `--` + 页脚状态摘要），但语气和缓存策略因稳定性而异：

| 层 | 说明 | 数据源 | 失败频率 | 用户提示语气 | 缓存策略 |
|:--:|:-----|:-------|:--------|:------------|:---------|
| **T2** | 稳定数据源，偶发失败 | 指数 / 基金排名 / 基金持仓 / 基金基准 | 低 | `⚠ XX数据暂不可用` | 标准 TTL |
| **T3** | 不稳定数据源，经常失败 | push2 行业分类/概念板块 | 高 | `ℹ XX数据暂不可用（数据源不稳定）` | 缓存 TTL 加倍（14 天）|

| 模块 | 数据列 | 外部数据源 | T 层 | 不可用时对报告的影响 |
|:-----|:-------|:-----------|:----:|:-------------------|
| summary | A 股/美股指数 | tencent → sina / sina → tencent | T2 | 指数区域显示 `--`，不影响市值 |
| fund_performance | 同类排名（排名/总数）| tiantian JS 变量 | T2 | 排名列全 `--`，收益率照常显示 |
| fund_performance | 业绩基准 | eastmoney HTML + 知识库 | T2 | 基准列空 |
| penetration | 穿透 TOP10 持仓 | tiantian HTML | T2 | 穿透表空，核心市值核算不受影响 |
| penetration | 行业/概念板块 | push2 → REST fallback | **T3** | 板块列 `--`（push2 不稳定属已知）|
| market_value | 净值日期/溢价率/QDII 时区 | eastmoney + 交易时段API | T2 | 取价方式列标记可能不精确，市值不受影响 |

**核心问题：** 当前 `--` 无法区分"数据为零"和"数据获取失败"。
用户看到空列不知道是 API 挂了还是真的没有数据。

**T3（push2）特殊处理：**
- push2（东方财富全推送接口）是行业分类/概念板块的主数据源，但实测稳定性较差，经常超时或返回空响应
- 行业归属信息本身变化不频繁（一家公司不会每周换行业），因此：
  - **缓存 TTL 从 7 天加倍至 14 天**，减少实时请求频率
  - 用户提示使用 `ℹ`（信息性）而非 `⚠`（警告性），传达"这个数据源就是不太稳，正常"
  - `push2` 熔断器仍保留：连续 3 次失败后本轮跳过，走 REST fallback

**Phase 1 处理：** T2 用 `⚠` 语气，T3（push2）用 `ℹ` 语气。
akshare 来源的盈利预测、分红、股息率等功能从原 T2/T3 统一归入 T4，由 Phase 2 处理。

### 1.4 T4 层：附加增值数据

T4 包含所有 akshare 源数据（盈利预测/股息率/分红/资金流向）、新闻、B 系列、LLM：

| 模块 | 数据源 | 不可用时的当前表现 | 上游依赖 | 符号 |
|:-----|:-------|:------------------|:---------|:----:|
| fund_performance | akshare 盈利预测 | `--` 无状态提示（从原 T2 移入）| 无 | ⚠（在 T2 页签内）|
| penetration | akshare 盈利预测 | `logger.debug`（从原 T2 移入）| 无 | ⚠（在 T2 页签内）|
| penetration | akshare 年均股息率 | `logger.debug`（从原 T2 移入）| 无 | ⚠（在 T2 页签内）|
| category | akshare 分红/股息率 | `except: return "--"` 无日志（从原 T2 移入）| 无 | ⚠（在 T2 页签内）|
| news_correlation | 5 源并行 | 全失败→空模块（无提示）；部分失败→静默降级 | **T3 push2 行业标签**（关键词增强）| ℹ（独立页签）|
| early_warning | 新闻 + akshare 资金流向 | 依赖上游数据，空列表→空白模块 | T4 news_correlation | ℹ（独立页签）|
| fund_manager | tiantian HTML | 空表 | **T2 天天基金持仓**（基金列表）| ⚠（B 系列页签跟随 T2 符号）|
| fund_overlap | tiantian 持仓 | 基金数不足时已跳过 | **T2 天天基金持仓** | ⚠（同上）|
| fund_concentration | tiantian 持仓 | 空表 | **T2 天天基金持仓** | ⚠（同上）|
| fund_style | push2/tencent 扩展 | 空表 | **T2 天天基金持仓**（push2→tencent→代码前缀三级降级）| ⚠（同上）|
| global_macro | LLM API | 已有"生成失败"占位文本 | 无 | 不适用 |
| expert_review | LLM API | 同上 | 无 | 不适用 |
| health_check | LLM API | 同上 | 无 | 不适用 |
| penetration_deep | LLM API | 同上 | 无 | 不适用 |
| news_correlation(LLM) | LLM API | 同上 | 无 | 不适用 |

**同源归并说明：** akshare 数据（盈利预测、分红股息率、资金流向、新闻）虽然在功能上服务于 T2 模块的增强列，但 akshare 库的 ImportError 风险和超时模式与 tencent/tiantian 等稳定 API 明显不同，因此统一归入 T4，采用模块级占位/隐藏策略。

**符号绑定说明：** 前缀符号与**渲染页签的 T 层**绑定，而非数据源本身的 T 层。
- akshare 盈利预测（T4）渲染在 `fund_performance`（T2 页签）→ 使用 T2 的 `⚠`
- B 系列 4 模块注册为 `b_series` 类型，但其渲染的页签在数据可用时视为 T2 扩展 → 统一使用 `⚠`
- news 模块和 LLM 模块拥有独立页签 → 可使用各自的 `ℹ` 符号
- 只有 T3（push2 行业分类）在独立语境下使用 `ℹ`，强调"已知不稳定"

**上游依赖说明：** B 系列 4 个模块依赖 T2 的天天基金持仓数据作为输入。如果 T2 持仓拉取失败，B 系列数据必然为空（这是正常现象，非 B 模块自身问题）。该依赖已在"上游依赖"列标识。T3（push2 行业分类）的行业标签被 `news_correlation` 的 `news_keywords.py` 用于关键词增强匹配，T3 失败时新闻关键词广度下降但不会完全失效。

**Phase 2 处理：** T4 数据不可用时 → 模块显示"数据暂不可用"占位/跳过，不产生歧义。

---

## 2. 三端降级行为规范

### 2.1 消息分级

| 用户感知级别 | 含义 | 适用 | TUI | Excel | HTML |
|:------------|:-----|:-----|:----|:------|:------|
| `--` | 数据不存在（已确认为 0/空）| T2/T3/T4 通用 | `--` | `--` | `--` |
| `⚠ 数据暂不可用` | 外部 API 获取失败（偶发）| **T2** + T4 数据渲染在 T2 页签内 | `[!] 提示` | 页脚灰色文字 | 底部灰色提示条 |
| `ℹ 数据暂不可用（数据源不稳定）` | 外部 API 获取失败（已知频繁）| **T3** (push2 独立页签) | `[..] 信息` | 页脚灰色文字 | 底部灰色提示条 |
| `ℹ 部分源不可用` | 多源数据中部分失败 | T4 新闻（独立页签）| `[..] 部分源` | 页脚灰色文字+明细 | 底部灰色提示条+明细 |
| `(模块隐藏)` | 整模块无意义 | T4（B 系列/预警等）| 无输出 | 无页签 | 无渲染 |

> **符号绑定策略：** 消息前缀符号与 **渲染页签的 T 层** 绑定，而非数据源本身的 T 层。
> 例如 akshare 盈利预测属 T4 数据，但渲染在 T2 的 `fund_performance` 页签内 → 使用 `⚠`（T2 符号）。
> 只有 T3（push2 行业分类）在独立页签中渲染时使用 `ℹ`，T4 新闻模块在独立页签中使用 `ℹ`。

### 2.2 日志级别规范

| 场景 | 级别 | 说明 |
|:-----|:-----|:------|
| 外部 API 返回空/超时（T2，预期内）| `logger.warning` | 非关键路径，用户可控 |
| push2 API 返回空/超时（T3，已知频繁）| `logger.debug`（限频：首次 warning，后续 debug）| 行业分类已知不稳定，避免日志刷屏 |
| 外部 API 返回异常格式 | `logger.warning` | 可能 API 变更 |
| 外部 API 正常返回但数据为空（无异常）| `logger.warning` | 空数据原因需写明（如"天天基金返回空持仓列表"）|
| 降级链路切换（主→备）| `logger.info` | 必须写明主链路失败原因（如"腾讯超时→走新浪备用"）|
| 缓存损坏自动删除 | `logger.warning` | 透明显式记录 |
| 所有 API 全部失败 | `logger.warning` 汇总一次 | 避免逐条刷屏 |
| 代码内部逻辑错误 | `logger.error` | 需修复的 bug |
| `except: pass` | 禁止（不允许） | 必须至少 `logger.warning` |
| 字段级计算异常（除零等）| `logger.debug` | 已知边界，如 cost=0 |

### 2.2.1 双通道协作规则（刚性约束）

`_data_status`（报告反馈）和日志（开发者反馈）必须成对出现，遵循以下规则：

```
┌─ 数据降级事件 ───────────────────────────┐
│                                            │
│  数据拉取失败 / 返回空 / 降级链路         │
│     ↓ 同时触发两个通道                     │
│  ┌──────────────────────┐                  │
│  │ 通道 A：日志          │  通道 B：报告   │
│  │                      │                 │
│  │ 必须有具体原因       │  用户友好提示    │
│  │ logger.warning(      │  _data_status    │
│  │   "[模块] 原因: %s", │  [key] = {       │
│  │   e / 具体描述       │    available: F, │
│  │  )                   │    message: ".." │
│  │                      │  }               │
│  └──────────────────────┘                 │
│                                            │
│  规则1：两条缺一不可                        │
│  规则2：日志必须写明"为什么失败"             │
│    ✓ "腾讯超时" / "天天基金返回空列表"       │
│    ✗ "数据不可用"（太笼统，没有原因）        │
│  规则3：报告消息用 STATUS_MESSAGES 常量       │
│  规则4：同一作用域内，日志行必须紧邻          │
│         _data_status 赋值行之前              │
└────────────────────────────────────────────┘
```

### 2.3 Excel 页脚状态摘要格式

位置：每个模块页签**数据区域末尾、总计行之后**，与数据区域隔一空行。

```
数据加载状态：
  ⚠ 基金业绩排名数据不可用，排名列显示 --
  ⚠ 盈利预测数据不可用，EPS 列显示 --
  ℹ 行业分类数据暂不可用（数据源 push2 不稳定）
```

具体规则：
- 灰色 9 号字体（与 `_write_module_data_rows` foot 模式一致）
- 空行分隔，不干扰数据区域
- 全部正常时**不显示**摘要区（避免干扰）
- 至少有一条异常时才渲染
- 符号与**渲染页签的 T 层**绑定：T2 模块用 `⚠`，T3（push2）用 `ℹ`
- T4 数据若渲染在 T2/T3 页签内，跟随宿主页签的符号（如 akshare 盈利预测在 fund_performance 页签内 → `⚠`）

### 2.4 HTML 状态区块格式

位置：每个模块渲染内容末尾（`</div>` 前），有条件渲染。

```html
<div class="data-status">
  <hr class="data-status-divider">
  <p class="data-status-title">📊 数据加载状态</p>
  <ul class="data-status-list">
    <li class="data-status-warn">⚠ 基金业绩排名数据不可用，排名列显示 --</li>
    <li class="data-status-info">ℹ 行业分类数据暂不可用（数据源 push2 不稳定）</li>
    <li class="data-status-ok">✅ 盈利预测数据正常</li>
  </ul>
</div>
```

CSS 类定义：
- `.data-status-warn` → 橙色左侧边框（T2 偶发失败）
- `.data-status-info` → 灰色左侧边框（T3 已知不稳定）
- `.data-status-ok` → 绿色左侧边框
- `.data-status-title` → 灰色 14px 粗体

---

## 3. 数据源完整盘点

### 3.1 完整清单

| # | 数据源 | URL 端点 | 缓存类型 | TTL | 归属模块 | T 层 | 失败模式 | 当前降级 | 日志现状 | 回退策略 | 上游依赖 |
|:-:|:-------|:---------|:---------|:---:|:---------|:----:|:---------|:---------|:---------|:---------|:---------|
| 1 | 腾讯财经行情 | `qt.gtimg.cn/q=` | `price_*` | 日/30s | market_value(所有) | T1 | 超时/空响应/格式错误 | eastmoney + 过期缓存 | logger.warning | eastmoney 备用链路 | 无 |
| 2 | 东方财富净值 | `api.fund.eastmoney.com` | `price_*` | 日 | market_value(场外基金) | T1 | 超时/JSONP 解析失败 | tiantian fundf10 + 过期缓存 | logger.warning | tiantian 备用链路 | 无 |
| 3 | 腾讯指数 | `qt.gtimg.cn/q=` | `index_*` | 日/30s | summary | T2 | 超时/空响应 | → sina → 过期缓存 | logger.debug | → sina → 过期缓存三级 | 无 |
| 4 | 新浪指数 | `hq.sinajs.cn` | `index_*` | 日/30s | summary | T2 | 超时/格式错误 | → tencent → 过期缓存 | logger.debug | → tencent → 过期缓存三级 | 无 |
| 5 | 天天基金排名 | `pingzhongdata/{code}.js` | `fund_perf_*` | 日 | fund_performance | T2 | JS 变量解析失败/空 | `--` 无提示 | logger.debug | 无备用链路（单 JS 源）| 无 |
| 6 | 天天基金持仓 | `FundArchivesDatas.aspx` | `fund_hold_*` | 周 | penetration / B 系列 | **T2**(pen)/**T4**(B) | HTML 解析失败/空 | 空表 | logger.debug | 无备用链路 | B 系列 4 模块 |
| 7 | 天天基金基准 | `jbgk_{code}.html` | `fund_benchmarks` | 月 | fund_performance | T2 | HTML 解析失败 | 知识库(13条) + 用户自定义 | logger.debug | 知识库 + 用户配置覆盖 | 无 |
| 8 | **push2 行业** | `push2.eastmoney.com` | `industry_*` | **7→14天** | penetration | **T3** | 超时/熔断（**已知频繁**） | → REST fallback(无概念) | logger.debug | REST fallback（仅行业无概念）| T4 news_correlation（关键词）|
| 9 | akshare 盈利预测 | akshare | `profit_forecast_*` | 日 | penetration, fund_performance | **T4** | ImportError/超时 | `{}` → `--` | logger.debug | 无备用链路 | 无 |
| 10 | akshare 分红 | akshare | `dividend_*` | 日 | category, penetration | **T4** | ImportError/超时 | `{}` → `--` | logger.debug(cat: `--` 无日志) | 无备用链路 | 无 |
| 11 | akshare 资金流向 | akshare | `sector_flow_*` | 日 | early_warning | **T4** | ImportError/超时 | `[]` → 空表 | logger.debug | 无备用链路 | T4 early_warning |
| 12 | 新浪新闻 | `feed.mix.sina.com.cn` | `news_*` | 15min | news_correlation | T4 | 超时/空 | `[]`, 其他源继续 | logger.warning | 4 源并行（冗余）| 无 |
| 13 | 东方财富新闻 | `np-weblist.eastmoney.com` | `news_*` | 15min | news_correlation | T4 | 超时/空 | 同上 | logger.warning | 4 源并行（冗余）| 无 |
| 14 | 财联社新闻 | `www.cls.cn` | `news_*` | 15min | news_correlation | T4 | 超时/鉴权 | 同上 | logger.warning | 4 源并行（冗余）| 无 |
| 15 | 华尔街见闻 | `api-one.wallstcn.com` | `news_*` | 15min | news_correlation | T4 | 超时/空 | 同上 | logger.warning | 4 源并行（冗余）| 无 |
| 16 | akshare 新闻 | akshare | `news_*` | 15min | news_correlation | T4 | ImportError/超时 | 同上 | logger.warning | 4 源并行（冗余）| 无 |
| 17 | 天天基金经理 | `fund.eastmoney.com` HTML | `fund_manager_*` | 日 | fund_manager | T4 | HTML 解析失败 | → 档案页回退 | logger.debug | 档案页回退 | T2 持仓（基金列表）|
| 18 | push2 扩展行情 | `push2.eastmoney.com`(f20/f9) | 无(会话 _ext_memo) | 会话 | fund_style | T4 | 超时/空 | → tencent 扩展 → 代码前缀 | logger.debug | **三级降级**：push2→tencent→代码前缀 | T2 持仓（基金列表）|
| 19 | LLM API | anthropic/openai endpoint | `llm_*` | 2-24h | LLM 4+1 模块 | T4 | 超时/熔断/Key 未配置 | 已有"生成失败"占位 | logger.warning | 模块级降级（占位文本）| 无 |

> **关于 #8 vs #18（push2 跨层说明）：** 两者均调用 push2.eastmoney.com，但回退能力不同。
> #8（行业分类）仅有一条 REST fallback 且无概念数据，失败后用户感知明显 → **归 T3**。
> #18（扩展行情）有三级降级链路（push2→tencent 扩展→代码前缀估算），单级失败不影
> 响最终输出 → **归 T4**。详见[决策记录 §7 第 6 项](#)。

### 3.2 T1/T2/T3 在注册表中的映射

`registry.py` 的 `type` 字段与 T 层的对照关系：

| registry type | T 层 | 说明 |
|:--------------|:----:|:-----|
| `always` | T1(核心) + T2(稳定增强) + T3(不稳定增强) | 页签始终可见，内部数据列需降级 |
| `b_series` | T4 | 模块级条件可见 + 数据不可用占位 |
| `news` | T4 | 模块级条件可见 + 数据不可用占位 |
| `llm` | T4 | 模块级条件可见 + 已有失败占位 |

注意：`always` 模块内部**混有 T1/T2/T3 数据**。
- T1 部分（价格/净值）→ 影响市值核算
- T2 部分（指数/排名/持仓）→ 只影响增强列，偶发失败
- T3 部分（push2 行业）→ 只影响增强列，已知不稳定

### 3.3 边界条件

| 条件 | 影响范围 | 处理方式 |
|:-----|:---------|:---------|
| 纯股票持仓（无基金）| T2/T4 中基金相关模块 | 穿透表空（正常）、基金排名空（正常）、B 系列跳过（已有）|
| 纯基金持仓 | T2 index 正常 | 价格走净值链路，不影响 |
| 断网运行 | 所有 T2/T3/T4 失效 | 只有 T1 过期缓存数据可工作 |
| 部分 akshare 函数失败 | akshare_extras（T4）| 各函数独立 try/except，互不影响 |
| LLM API Key 未配置 | 所有 LLM 模块 | 已有"未配置"提示，不调整 |

---

## 4. Phase 1 详细设计：T2 + T3 数据降级统一

### 4.1 `_data_status` 机制设计

每个 T2/T3/T4 模块新增一个 `_data_status` 字典，用于追踪各外部数据源的加载状态。

```python
# 内部结构
_data_status: dict[str, dict] = {
    "<数据源标识>": {
        "available": True | False,        # 当前是否可用
        "tier": "T2" | "T3" | "T4",       # 所属层
        "message": "行业分类数据暂不可用（数据源 push2 不稳定）",  # 最终展示文本
    }
}
```

**STATUS_MESSAGES 作为唯一消息源：**
```python
# data_status.py — 全局常量，Excel 和 HTML 两端 import 引用
STATUS_MESSAGES: dict[str, str] = {
    "rank_unavailable":        "基金业绩排名数据不可用，排名列显示 --",
    "benchmark_unavailable":   "业绩基准数据不可用",
    "industry_unavailable":    "行业分类数据暂不可用（数据源 push2 不稳定）",
    "holdings_unavailable":    "穿透持仓数据暂不可用",
    "index_degraded":          "指数数据来自降级链路",
    ...
}

# 各模块赋值时直接引用：
_data_status["industry"] = {
    "available": False,
    "tier": "T3",
    "message": STATUS_MESSAGES["industry_unavailable"],   # ← 引用常量，非硬编码
}

# 动态消息（如新闻部分源失败）直接构造 message：
_data_status["news_sources"] = {
    "available": False,
    "tier": "T4",
    "message": f"以下新闻源不可用：{failed_names}",
}
```

> **设计约束：** `DataStatusItem` 不拆 `label` 和 `detail`，统一用 `message` 承载最终展示文本。模板直接渲染 `message`，不做额外拼接。这消除了"标签里含'数据'字，模板又追加'数据'字"的双重语义 bug。

**数据流（含双通道协作）：**

```
获取数据
  ├─ 成功 → _data_status["key"] = {"available": True, "tier": "T2", "message": ""}
  └─ 失败 → 写日志（具体原因）← 紧邻的上一行
            ↓
            _data_status["key"] = {"available": False, "tier": "T2",
                                   "message": STATUS_MESSAGES["xxx"]}
              ↓
模块写入结束时 → 检查 _data_status
  ├─ 全部 available → 不渲染摘要区
  └─ 有 False 项 → 渲染摘要区（Excel foot / HTML <div class="data-status">）
                   文字取自 message 字段，T2 前缀 ⚠，T3/T4 前缀 ℹ
```

### 4.2 各模块具体变更

#### 4.2.1 `fund_performance.py`

**现存数据获取点：**

| 数据 | 函数 | 当前异常处理 |
|:-----|:-----|:------------|
| 数据 | 函数 | 当前异常处理 |
|:-----|:-----|:------------|
| 基金排名 | `tiantian.fetch_fund_rankings()` | 外部调用方已 try，失败返回 `[]` |
| 业绩基准 | `fetcher/fund.py` 内部 | `logger.debug` |

**改动：**
- 在写入排名循环中记录 `_data_status["rank"]`
- 在写入基准列时记录 `_data_status["benchmark"]`
- 写入结束时将 `_data_status` 传给 Excel 和 HTML 渲染端
- **EPS 预测（akshare）已移入 T4/Phase 2 处理**

#### 4.2.2 `penetration.py` / `penetration_sheet.py`

**现存数据获取点：**

| 数据 | 函数 | 当前异常处理 | T 层 |
|:-----|:-----|:------------|:----:|
| 行业分类 | `batch_fetch_industry_data()` | `logger.debug` | **T3** |
| 穿透 TOP10 持仓 | tiantian HTML 解析 | 空表无提示 | T2 |

**改动：**
- 每个获取点加 `_data_status` 记录
- push2（T3）使用 `ℹ` 语气 + `logger.debug`（首次 warning 后限频）
- 穿透持仓（T2）使用 `⚠` 语气 + `logger.warning`
- push2 缓存 TTL：在 `registry.py` 中将 `industry_*` TTL 从 7 天改为 14 天
- 状态信息通过 info 字典透传到 `penetration_sheet.py` 和 `html_writer.py`
- **akshare 盈利预测/股息率已移入 T4/Phase 2 处理**

#### 4.2.3 `category.py`

category 模块的 akshare 分红/股息率数据已移入 T4/Phase 2 处理。Phase 1 不涉及。
（见 §5.4 category 专项说明）

> 注：category 中 `_yield_text()` 的 `except Exception: return "--"` 无日志问题由 Phase 3 全局审计修复。

#### 4.2.4 `summary.py`（指数降级标识）

**现状：** A 股指数 tencent → sina → 过期缓存，美股 sina → tencent → 过期缓存。
已有 fallback 但**无标识**告知用户当前指数是否来自降级。

**改动：**
- 在 `write_summary_sheet()` 中记录指数链路的最终来源
- 当指数数据经过降级时，在页脚注明"指数数据来自降级"
- HTML 端在 summary 底部条件渲染

### 4.3 Excel 端实现

利用已有的 `_write_module_data_rows` 的 foot 模式：

```python
# 在模块行写入后调用
_write_data_status_foot(ws, data_status, row)
```

其中 `_write_data_status_foot` 是新增的通用函数，复用 `excel_writer.py` 的单元格写入方法。

### 4.4 HTML 端实现

在 `html_writer.py` 中，各 `_render_*` 函数返回的字典增加 `data_status` 字段。
模板中新增条件渲染块：

```jinja
{% if section_data.get('data_status') %}
<div class="data-status">
  <hr class="data-status-divider">
  <p class="data-status-title">📊 数据加载状态</p>
  <ul class="data-status-list">
    {% for key, item in section_data.data_status.items() if not item.available %}
    {% set prefix = "⚠" if item.tier == "T2" else "ℹ" %}
    {% set css_class = "warn" if item.tier == "T2" else "info" %}
    <li class="data-status-{{ css_class }}">{{ prefix }} {{ item.message }}</li>
    {% endfor %}
  </ul>
</div>
{% endif %}
```

> **无 `label`/`detail` 拼接：** `message` 字段承载最终展示文本（来自 `STATUS_MESSAGES` 常量或动态构造），模板只做前缀补全和类名选择，不做文案拼接。这消除了 `item.label` 已含"数据"二字而模板又追加"数据不可用"的双重语义 bug。模板中也不再区分 `detail`——所有信息已内聚在 `message` 中。

### 4.5 文件影响范围

| 文件 | 改动类型 | 预估行数 |
|:-----|:---------|:--------:|
| `src/python/report/penetration.py` | 新增 `_data_status` 跟踪（T2 持仓 + T3 push2）| ~20 行 |
| `src/python/report/penetration_sheet.py` | 新增 foot 写入 | ~15 行 |
| `src/python/report/fund_performance.py` | 新增 `_data_status` + foot 写入 | ~30 行 |
| `src/python/report/summary.py` | 新增指数降级标识 | ~20 行 |
| `src/python/registry.py` | push2 行业 TTL 7→14 天 | ~1 行 |
| `src/python/report/excel_writer.py` | 新增 `_write_data_status_foot()` 通用函数 | ~20 行 |
| `src/python/report/html_writer.py` | 各 `_render_*` 返回 `data_status`；新增状态摘要渲染 | ~50 行 |
| `src/python/report/html_builders.py` | 数据构建时记录 `data_status` | ~15 行 |
| `src/python/tmpl/report_template.html` | 新增 `.data-status` CSS + 条件渲染块 | ~30 行 |
| **合计** | | **~200 行** |

### 4.6 跨层依赖：T3 → 新闻模块状态通知

T3（push2 行业分类）的行业标签被 `news_correlation` 的 `news_keywords.py` 用于关键词增强匹配。
当 T3 不可用时，新闻模块的关键词广度下降，但系统不应崩溃。

**机制：**
- `penetration.py` 的 `_data_status["industry"]` 状态通过 info 字典向上传递
- `news_correlation.py` 在构建新闻查询时检查 `info.get("industry_available", True)`
- T3 失败时，新闻关键词池回退到仅使用持仓名称/代码（放弃行业标签），不影响新闻获取
- 此机制为信息性降级，不产生额外用户提示（新闻模块有自己的 source_status）

---

## 5. Phase 2 详细设计：T4 附加数据降级统一

Phase 2 覆盖所有 T4 数据，含原 T2/T3 移入的 akshare 系列 + B 系列 + 新闻 + 预警 + LLM。
统一采用模块级占位/隐藏策略，不产生歧义空表。

### 5.0 akshare 数据（从 T2 移入）

**背景：** akshare 来源的盈利预测、分红、股息率、资金流向原归入 T2（增强列），但 akshare
的 ImportError 风险和超时模式与 tencent/tiantian 等稳定 API 不同，统一归入 T4。

| 模块 | 数据 | 函数 | 当前异常处理 | Phase 2 处理 |
|:-----|:-----|:-----|:------------|:-------------|
| fund_performance | EPS 预测 | `akshare_extras.get_profit_forecast()` | `logger.debug` | 模块底部显示"盈利预测数据暂不可用" |
| penetration | 预测 EPS | `get_profit_forecast()` | `logger.debug` | 同上 |
| penetration | 年均股息率 | `get_dividend_data()` | `logger.debug` | 模块底部显示"分红数据暂不可用" |
| category | 分红/股息率 | `get_dividend_data()` / `_yield_text()` | `except: return "--"` 无日志 | 模块底部显示"分红数据暂不可用" + `logger.warning` |

### 5.1 B 系列 4 模块

B 系列每个模块当前在 Excel/HTML 端都有独立的写入函数。
Phase 2 不改变条件可见性逻辑（`enable_b_series`），只在数据为空时替换为占位。

**统一模式：**

```python
# Excel 端 — 在 _write_b_series_sheets 各写入器中
def _write_manager_sheet(ws, ...):
    results = compute_manager_analysis(...)
    if not results or not results.get("results"):
        _write_placeholder(ws, "基金经理数据暂不可用")
        return
    # ... 正常写入逻辑

# HTML 端 — 在 _render_manager_analysis 中
def _render_manager_analysis(...):
    results = compute_manager_analysis(...)
    if not results or not results.get("results"):
        return {"results": [], "placeholder": "基金经理数据暂不可用"}
    # ... 正常渲染
```

**占位文本清单：**

| 模块 | 占位文本 | 隐藏条件 |
|:-----|:---------|:---------|
| fund_manager | 基金经理数据暂不可用 | 结果列表为空 |
| fund_overlap | 持仓数据不足，无法计算重合度 | 基金数 < 2 或持仓全空 |
| fund_concentration | 持仓数据暂不可用 | 结果列表为空 |
| fund_style | 扩展行情数据暂不可用 | 结果列表为空 |

### 5.2 新闻模块

**现状分析：**
- 新闻聚合器 `news_aggregator.py` 对每个源独立 `try/except`，单源失败不影响其他
- `news_correlator.py` 纯本地，无外部依赖
- 但全源失败时无状态反馈

**改动：**
- `news_aggregator.py` 新增 `source_status` 返回值结构：

  ```python
  {
      "sina": "ok" | "fail",
      "eastmoney": "ok" | "fail",
      "cls": "ok" | "fail" | "disabled",
      "wallstreetcn": "ok" | "fail",
      "akshare": "ok" | "fail",
  }
  ```

- 全源失败 → news_correlation 模块显示"新闻数据暂不可用，请检查网络连接"
- 部分失败 → 模块底部注明"部分新闻源不可用"并列出具体源

### 5.3 智能预警

**现状：** `early_warning.py` 内部对新闻和资金流向数据有 guard，但外部无感知。
新闻为空时预警数据肯定为空，但不通知用户。

**改动：**
- 在 `early_warning.py` 入口检查新闻数据，为空时直接返回带 `placeholder` 的空结果
- Excel/HTML 端检测到 `placeholder` 时渲染占位文本

### 5.4 文件影响范围

| 文件 | 改动类型 | 预估行数 |
|:-----|:---------|:--------:|
| `src/python/report/category.py` | 新增 `_data_status` + 占位 + `logger.warning` | ~25 行 |
| `src/python/report/penetration.py` | 新增 akshare `_data_status` 跟踪 | ~10 行 |
| `src/python/report/penetration_sheet.py` | 新增 akshare foot 写入 | ~10 行 |
| `src/python/report/fund_performance.py` | 新增 EPS `_data_status` | ~10 行 |
| 各 B 系列 sheet 文件 (4 文件) | 每个加 guard + 占位 | ~12 行/文件 = ~48 行 |
| `html_writer.py` | B 系列 + akshare 渲染器加 placeholder 检测 | ~40 行 |
| `news_sources.py` / `news_aggregator.py` | 新增 `source_status` 输出 | ~20 行 |
| `report/news_correlation.py` | 传递 source_status 给 info 字典 | ~10 行 |
| `excel_writer.py` | 新增 `_write_placeholder()` 通用函数 | ~15 行 |
| `report/early_warning.py` | 加新闻空数据 guard | ~10 行 |
| `tmpl/report_template.html` | placeholder 样式 + B 系列/新闻条件渲染 | ~40 行 |
| **合计** | | **~240 行** |

---

## 6. Phase 3 详细设计：全局异常审计 + 回归测试

### 6.1 审计清单

> **与子迭代计划的对应关系：** Phase 3 审计清单中的日志补全项（#1~#2、#4~#7）已归入 D-1 分批执行，大 try 拆分（#3）已移至 D-6 统一处理（html_writer.py `_render_penetration_section` 内部的盈利预测/股息率/板块数据三个 try 拆分）。不再保留独立的"Phase 3"执行阶段——总计划已整合为 10 步子迭代。

| # | 位置 | 当前代码 | 修复方案 | 归属迭代 | 影响 |
|:-:|:-----|:---------|:---------|:--------|:-----|
| 1 | `category.py:128` | `except Exception: return "--"` | 加 `logger.warning("[category] 股息率计算异常: %s", e)` | D-1 | 日志可排查，用户行为不变 |
| 2 | `html_builders.py:40` | `except Exception: return "--"` | 同上 | D-1 | 同上 |
| 3 | `html_writer.py:434-442` | 盈利预测+股息率+板块合一 try | 拆成 3 个独立 try/catch，对齐 Excel 端粒度 | **D-6**  | 失败定位更精确 |
| 4 | `html_writer.py:810` | `except ImportError: pass` | 加 `logger.warning` 并说明正常降级条件 | D-1 | 日志可排查 |
| 5 | `fund_style_analysis.py:237,268` | `logger.debug` | 升级为 `logger.warning`，因为外部 API 失败 | D-1 | 日志级别对齐规范 |
| 6 | `fetcher/fund.py:160` | `except (KeyError, TypeError): pass` | 加 `logger.warning("[fund] 基准配置覆盖失败，使用默认值")` | D-1 | 日志可排查 |
| 7 | `llm/generators.py:417` | `except ValueError: pass` | 加 `logger.warning("[llm] JSON 解码失败: %s", e)` | D-1 | 日志可排查 |

### 6.2 测试计划

#### Phase 1 测试（T2 降级）

| 场景 | mock 方式 | 验证断言 | 归属测试文件 |
|:-----|:---------|:---------|:------------|
| push2 不可用 → penetration 状态摘要 | `batch_fetch_industry_data` → 抛异常 | 页脚含"ℹ 行业分类数据暂不可用" | `test_penetration_edge.py` |
| 持仓 API 失败 → penetration 摘要 | `tiantian.fetch_holdings` → `[]` | 页脚含"⚠ 持仓数据暂不可用" | `test_penetration_edge.py` |
| 排名 API 失败 → fund_performance 摘要 | `fetch_fund_rankings` → `[]` | 页脚含"⚠ 基金排名数据暂不可用" | `test_fund_performance_edge.py` |
| 基准数据失败 → fund_performance 摘要 | 基准 mock 空 | 页脚含"⚠ 业绩基准数据暂不可用" | `test_fund_performance_edge.py` |
| 指数降级链路 → summary 降级标识 | 指数全部 mock 失败 | 页脚含"⚠ 指数数据来自降级" | `test_summary_edge.py` |

#### Phase 2 测试（T3 降级）

| 场景 | mock 方式 | 验证断言 | 归属测试文件 |
|:-----|:---------|:---------|:------------|
| akshare 盈利预测空 → category 摘要 | `get_dividend_data` → `{}` | 含"分红数据暂不可用" | `test_category_edge.py` |
| akshare 盈利预测异常 → penetration 摘要 | `get_profit_forecast` → 抛异常 | 含"盈利预测数据暂不可用" | `test_penetration_edge.py` |
| akshare 股息率异常 → penetration 摘要 | `get_dividend_data` → 抛异常 | 含"分红数据暂不可用" | `test_penetration_edge.py` |
| akshare 盈利预测异常 → perf 摘要 | `get_profit_forecast` → 抛异常 | 含"盈利预测数据暂不可用" | `test_fund_performance_edge.py` |
| 基金经理为空 → fund_manager 占位 | `fetch_fund_manager` → `None` | 含"基金经理数据暂不可用" | `test_fund_manager_edge.py` |
| 持仓全空 → fund_overlap 占位 | 持仓 mock 为 `[]` | 含"持仓数据不足，无法计算重合度" | `test_fund_overlap_edge.py` |
| 新闻全源失败 → news 占位 | 5 源全 mock `[]` | 含"新闻数据暂不可用" | `test_news_degradation_edge.py` |
| 部分新闻源失败 → 源状态摘要 | 3 源 mock `[]`、2 源正常 | 含"部分新闻源不可用" | `test_news_degradation_edge.py` |
| 预警数据为空 → 占位 | `early_warnings` → `None` | 含"预警数据暂不可用" | `test_early_warning_edge.py` |

#### Phase 3 测试（回归 + 一致性）

| 场景 | 方式 | 验证断言 | 归属测试文件 |
|:-----|:-----|:---------|:------------|
| 大 try/except 拆分后回归 | 现有测试全部通过 | 拆分后行为不变 | 各回归测试 |
| HTML vs Excel 消息一致性 | 正则提取对比 | 同一场景消息文本完全一致 | `test_html_writer_edge.py` / `test_excel_generator_edge.py` |

### 6.3 测试文件分配

```
src/test/unit/report/
├── test_penetration_edge.py           # Phase 1 T2 持仓 + T3 push2 降级 / Phase 2 akshare EPS/股息降级
├── test_fund_performance_edge.py      # Phase 1 T2 排名+基准降级 / Phase 2 akshare EPS 降级 (NEW)
├── test_summary_edge.py               # Phase 1 T2 指数降级标识 (NEW)
├── test_category_edge.py              # Phase 2 akshare 分红/股息降级
├── test_fund_manager_edge.py          # Phase 2 T4 占位 (NEW)
├── test_fund_overlap_edge.py          # Phase 2 T4 占位 (NEW)
├── test_news_degradation_edge.py      # Phase 2 T4 新闻全源/部分失败 (NEW)
├── test_early_warning_edge.py         # Phase 2 T4 预警降级 (NEW)
├── test_html_writer_edge.py           # Phase 3 消息一致性
└── test_excel_generator_edge.py       # Phase 3 消息一致性 (NEW)
```

> 标记为 (NEW) 的文件需新建，其余在现有 `*_edge.py` 中追加。
> 所有测试使用 `@pytest.mark.edge`，遵循 §1.9 边缘测试文件隔离规范。

---

## 7. 风险登记 & 边界条件

### 7.1 边界条件

| 边界 | 检查点 | 预期行为 |
|:-----|:-------|:---------|
| 纯股票持仓 | B 系列/基金排名 | B 系列跳过（已有），排名显示"无基金"（已有）|
| 纯基金持仓 | 行业分类 T3 | 穿透后若有 A 股则正常，否则行业空 |
| 断网运行 | T2/T3/T4 全部失效 | 7 天内过期缓存支撑 T1，T2/T3/T4 全部降级显示状态摘要 |
| akshare 未安装 | akshare_extras（T4）| ImportError 被捕获，占位文本（Phase 2）|
| 所有新闻源关闭 | news_sources 全 false（T4）| 新闻模块不渲染（已有）|
| push2 熔断 + REST fallback 都空 | T3 行业分类 | T3 状态摘要 + `--` 列，不影响市值的核算 |

### 7.2 风险登记

| 风险 | 影响 | 可能阶段 | 可能性 | 缓解措施 |
|:-----|:-----|:--------|:------:|:---------|
| 页脚格式改动影响回归测试 | 回归失败 | Phase 1 | 高 | 先定稿格式再更新测试断言 |
| 大 try/except 拆分引入行为回归 | 稳定性 | Phase 3 | 中 | 逐个拆分 + 立即跑测试 |
| HTML 摘要样式与现有 CSS 冲突 | 视觉错乱 | Phase 1 | 低 | 使用独立 class 名前缀 `data-status-*` |
| `_data_status` 字典未被正确传递到 HTML | 摘要不显示 | Phase 1 | 低 | 每次提交后运行对应 edge 测试验证 |
| 新闻源状态 `source_status` 与历史数据不兼容 | 异常 | Phase 2 | 低 | 使用 `dict.get()` 兜底默认值 |

---

## 8. 变更清单（完整汇总）

### Phase 1（T2 稳定增强 + T3 不稳定增强）

| 文件 | 操作 | 风险 | 备注 |
|:-----|:-----|:----:|:-----|
| `src/python/report/penetration.py` | 修改 | 低 | T2 持仓 + T3 push2 `_data_status` |
| `src/python/report/penetration_sheet.py` | 修改 | 低 | T2+T3 foot 写入 |
| `src/python/report/fund_performance.py` | 修改 | 低 | T2 排名+基准 `_data_status` + foot 写入 |
| `src/python/report/summary.py` | 修改 | 低 | T2 指数降级标识 |
| `src/python/report/excel_writer.py` | 修改 | 低 | 新增 `_write_data_status_foot()` |
| `src/python/report/html_writer.py` | 修改 | 中 | 各 `_render_*` 返回 `data_status` |
| `src/python/report/html_builders.py` | 修改 | 低 | 数据跟踪 |
| `src/python/tmpl/report_template.html` | 修改 | 低 | CSS + 条件渲染 |
| `src/python/registry.py` | 修改 | 低 | push2 行业 TTL 7→14 天 |
| `src/test/unit/report/test_penetration_edge.py` | 修改 | 低 | T2 持仓 + T3 push2 降级测试 |
| `src/test/unit/report/test_fund_performance_edge.py` | **新建** | 低 | T2 排名+基准降级测试 |
| `src/test/unit/report/test_summary_edge.py` | **新建** | 低 | T2 指数降级标识测试 |

### Phase 2（T4 附加增值）

| 文件 | 操作 | 风险 | 备注 |
|:-----|:-----|:----:|:-----|
| `src/python/report/category.py` | 修改 | 低 | akshare 分红 `_data_status` + `logger.warning` |
| `src/python/report/fund_performance.py` | 修改 | 低 | akshare EPS `_data_status` |
| `src/python/report/penetration.py` | 修改 | 低 | akshare EPS/股息 `_data_status` |
| `src/python/report/penetration_sheet.py` | 修改 | 低 | akshare foot 写入 |
| 各 B 系列 sheet 文件 (4 文件) | 修改 | 低 | guard + 占位 |
| `src/python/report/html_writer.py` | 修改 | 中 | placeholder 检测（B 系列 + akshare）|
| `src/python/providers/news_sources.py` | 修改 | 低 | `source_status` |
| `src/python/providers/news_aggregator.py` | 修改 | 低 | `source_status` |
| `src/python/report/news_correlation.py` | 修改 | 低 | 传递状态 |
| `src/python/report/excel_writer.py` | 修改 | 低 | 新增 `_write_placeholder()` |
| `src/python/report/early_warning.py` | 修改 | 低 | 空数据 guard |
| `src/python/tmpl/report_template.html` | 修改 | 低 | placeholder 样式 |
| `src/test/unit/report/test_category_edge.py` | 修改 | 低 | akshare 分红降级测试 |
| `src/test/unit/report/test_penetration_edge.py` | 修改 | 低 | akshare EPS/股息降级测试 |
| `src/test/unit/report/test_fund_performance_edge.py` | 修改 | 低 | akshare EPS 降级测试 |
| `src/test/unit/report/test_fund_manager_edge.py` | **新建** | 低 | |
| `src/test/unit/report/test_fund_overlap_edge.py` | **新建** | 低 | |
| `src/test/unit/report/test_news_degradation_edge.py` | **新建** | 低 | |
| `src/test/unit/report/test_early_warning_edge.py` | **新建** | 低 | |

### Phase 3

| 文件 | 操作 | 风险 | 备注 |
|:-----|:-----|:----:|:-----|
| `src/python/report/category.py` | 修改 | 低 | 加 `logger.warning` |
| `src/python/report/html_builders.py` | 修改 | 低 | 加 `logger.warning` |
| `src/python/report/html_writer.py` | 修改 | 中 | 拆分大 try/except |
| `src/python/report/fund_style_analysis.py` | 修改 | 低 | `debug` → `warning` |
| `src/python/fetcher/fund.py` | 修改 | 低 | 加 `logger.warning` |
| `src/python/llm/generators.py` | 修改 | 低 | 加 `logger.warning` |
| `src/test/unit/report/test_html_writer_edge.py` | 修改 | 低 | 消息一致性 |
| `src/test/unit/report/test_excel_generator_edge.py` | **新建** | 低 | 消息一致性 |

---

## 9. 设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|:-----|:-----|:-----|:------|
| T3 B 系列数据不可用时：模块隐藏 vs 占位 | 隐藏/占位 | **占位** | 用户应知道该模块存在但不可用，而非完全消失 |
| 状态摘要位置：模块顶部 vs 底部 | 顶部/底部 | **底部** | 不干扰数据阅读主流程，异常时用户可滚动到底查看 |
| `_data_status` 作用域：全局 vs 模块级 | 全局/模块级 | **模块级** | 各模块独立追踪，不引入全局状态依赖 |
| 指数降级标识：always 显示 vs 仅降级时显示 | 始终/仅降级 | **仅降级时** | 正常时不增加噪音 |
| 新闻部分源失败：底部全列 vs 仅列失败 | 全列/仅失败 | **仅列失败** | 用户只关心出问题的源，成功的源不需要提示 |
| 行业分类（push2）T 层归属 | T2 均等 / T4 / 独立 T3 | **独立 T3** | 不同源稳定性不同：T2 为稳定源，push2 为不稳定但业务价值中上，独立成层语气和缓存策略更清晰 |
| akshare 数据归属 | 跟随功能模块（散在 T2/T3） / 统一归 T4 | **统一 T4** | akshare 源 ImportError 风险和超时模式一致，同源归并后各层抽象更干净 |
| push2 失败时用户提示语气 | `⚠` 警告 / `ℹ` 信息 | **ℹ 信息** | 已知频繁失败，警告会麻痹用户，信息性语气更诚实 |
| push2 行业缓存 TTL | 维持 7 天 / 14 天 / 30 天 | **14 天** | 行业归属不常变，7 天也够但 14 天减少 50% 请求，配合 T3 定位 |
| T3 不可用对新闻的影响 | 忽略 / 通知新闻模块降级关键词 | **通知降级** | 行业标签用于新闻关键词召回，T3 失败时回退到仅持仓名称/代码匹配（§4.6）|
