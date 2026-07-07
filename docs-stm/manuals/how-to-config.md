# 配置指南

主配置文件 `data/config/config.json`，程序首次启动时自动创建。

```json
{
  "holdings_dir": "data/holdings",
  "holdings_filename": "个人投资持仓信息.xlsx",
  "output_dir": "reports",
  "news_top_count": 300,
  "news_sources": {
    "sina": true,
    "eastmoney": true,
    "cls": false,
    "wallstreetcn": true,
    "akshare": true
  },
  "preferred_provider": {},
  "early_warning": {
    "sector_alert_threshold_warning": -50000000,
    "sector_alert_threshold_danger": -200000000,
    "sentiment_top_n": 10
  },
  "market_hour_aware": ["price", "index"],
  "market_hour_ttl": 30,
  "market_hours": {
    "start": "09:30",
    "end": "15:00",
    "official_source": true
  },
  "default_menu_key": "L",
  "degradation": {
    "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},
    "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},
    "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14}
  },
  "report_section_order": {},
  "user_fund_benchmarks": {},
  "llm_key_file": "data/config/llm_key.json",
  "llm_settings_file": "data/config/llm_settings.json",
  "cache_ttl": {
    // ── 行情/数据类 ──
    "price": 86400,
    "index": 86400,
    "news": 900,
    "sector_flow": 900,
    "rank": 86400,
    "profit_forecast": 86400,
    "hold": 604800,
    "industry": 1209600,
    "dividend": 2592000,
    "benchmark": 2592000,
    // ── LLM 分析类 ──
    "llm_expert_review": 7200,
    "llm_news_correlation": 3600,
    "llm_global_macro": 86400,
    "llm_health_check": 86400,
    "llm_penetration_deep": 86400,
    // ── 基金深度分析类 ──
    "fund_manager": 86400,
    "fund_overlap": 604800,
    "fund_concentration": 2592000,
    "fund_style_snapshot": 2592000,
    // ── 系统类 ──
    "tracking": 2592000,
    "calendar": 1209600
  }
}
```

## 字段说明

以下字段可通过 TUI 主菜单的对应命令修改（运行 `python src/python/main.py` 进入主菜单）。标有"手动编辑"的字段需直接修改 JSON 文件。

| 字段 | 默认值 | 说明 | TUI 修改 |
|------|--------|------|----------|
| `holdings_dir` | `data/holdings` | 持仓 xlsx 文件所在目录 | 菜单 `C` |
| `holdings_filename` | `个人投资持仓信息.xlsx` | 要读取的持仓文件名 | 菜单 `F` |
| `output_dir` | `reports` | 报告输出目录（最新版+按日期存档） | 菜单 `O` |
| `news_top_count` | `300` | 财经新闻热点与持仓关联分析输出条目上限（各源原始获取量自动加倍保障召回） | 手动编辑 |
| `news_sources` | 见下方 | 各新闻数据源启停开关 | 手动编辑 |
| `preferred_provider` | `{}` | 各数据类型的首选提供商覆写 | 手动编辑 |
| `early_warning` | `{...}` | 智能预警参数（见 §early_warning 章节） | 手动编辑 |
| `default_menu_key` | `L` | TUI 菜单缺省选项的快捷键（E/H/B/L/C/F/O/1/2/3/4/S/R/X），启动后光标自动定位 | 手动编辑 |
| `degradation` | `{...}` | 数据降级策略（T2/T3/T4 各层的连续失败阈值、空数据阈值、缓存过期天数） | 手动编辑 |
| `report_section_order` | `{}` | 报告模块序号配置。空对象使用默认顺序（16 项）。键=模块标识，值=序号；已配置模块按序号升序在前，未配置模块按默认顺序在后。`llm_usage` 强制末位 | 手动编辑 |
| `market_hour_aware` | `["price", "index"]` | 交易时段内使用短 TTL 的数据类型列表 | 手动编辑 |
| `market_hour_ttl` | `30` | 交易时段内 market_hour_aware 类型的缓存有效期（秒），最短 30s，最长 86400s | 手动编辑 |
| `market_hours` | `{start: "09:30", end: "15:00", official_source: true}` | 市场时段配置（见 §market_hours 章节） | 手动编辑 |
| `user_fund_benchmarks` | `{}` | 自定义基金业绩基准覆盖（键=基金代码，值=基准代码） | 手动编辑 |
| `llm_key_file` | `data/config/llm_key.json` | LLM 密钥文件路径（4 个必填字段 + 4 个可选回退字段） | 手动编辑 |
| `llm_settings_file` | `data/config/llm_settings.json` | LLM 非敏感配置文件路径 | 手动编辑 |
| `cache_ttl.*` | 见下方 | 各缓存类型有效期（秒） | 手动编辑 |

## news_sources 可调字段

| 子字段 | 默认 | 说明 |
|--------|------|------|
| `sina` | `true` | 新浪财经（财经要闻/国内/国际，正常工作） |
| `eastmoney` | `true` | 东方财富（np-weblist 快讯接口，req_trace 参数，稳定可用） |
| `cls` | `false` | 财联社（API 要求签名鉴权，匿名请求不可用） |
| `wallstreetcn` | `true` | 华尔街见闻（全球财经直播流，JSON API，无需鉴权，推荐开启） |
| `akshare` | `true` | akshare（财新网要闻 + CCTV 财经新闻，开源封装，推荐开启） |

> **用法：** 将值改为 `true` 或 `false` 即可启用/禁用对应新闻源。

## market_hours 可调参数

`market_hours` 控制 A 股交易时段判断，用于盘中实时行情（短 TTL）和盘后收盘价（长 TTL）的自动切换。

判断逻辑为三层逐级 fallback：

1. **config.json 手动覆盖** — 以下 `start`/`end` 优先级最高
2. **东方财富 push2 API** — 实时交易状态（缓存 TTL：盘中 60s，盘后 7 天）
3. **内置默认值** — 北京时区工作日 09:30–11:30 + 13:00–15:00，自动排除午餐和周末

| 子字段 | 默认值 | 说明 |
|--------|:------:|------|
| `start` | `"09:30"` | 手动覆盖开盘时间（HH:MM），覆盖内置默认值 09:30 |
| `end` | `"15:00"` | 手动覆盖收盘时间（HH:MM），覆盖内置默认值 15:00 |
| `official_source` | `true` | 是否尝试从东方财富 push2 API 获取实时交易状态。设为 `false` 时跳过本层直接 fallback 内置默认值 |

`official_source` 启用时，API 返回 `f100` 字段表示实时交易状态，结果缓存策略因时段而异：

| `f100` 值 | 含义 | API 缓存 TTL |
|:---------:|------|:------------:|
| `0` | 未开盘（盘前） | 7 天（盘后长效缓存） |
| `1` | 交易中 | 60 秒（盘中高频刷新） |
| `2` | 已收盘（盘后） | 7 天（盘后长效缓存） |
| `3` | 午间休市 | 60 秒（午休后快速恢复） |

> **午餐休市：** 实际交易分为 09:30–11:30（上午）和 13:00–15:00（下午）两段。即使 `start`/`end` 覆盖为 `"09:30"`/`"15:00"`，午餐时段（11:30–13:00）自动视为非交易时段并回落长 TTL。`official_source: true` 时 API 返回 `status=3`（午间休市）也会让系统识别午餐休市。

## preferred_provider 可调字段

`preferred_provider` 用于手动指定某类数据的首选提供商，将其提到 Provider Chain 第一位。不配置时全部走默认优先级，一个源失败后自动递补备用。

适用场景：某网络环境下特定数据源更稳定、或因 IP 限制某数据源不可用。

| 子字段 | 默认 chain | 可选值 | 说明 |
|--------|-----------|--------|------|
| `price` | `tencent → eastmoney` | `tencent`, `eastmoney` | 股票/ETF 实时收盘价首选源 |
| `fund_rank` | `tiantian`（仅此一个） | `tiantian` | 基金业绩排名首选源 |
| `fund_hold` | `tiantian`（仅此一个） | `tiantian` | 基金持仓穿透首选源 |
| `industry` | `eastmoney_industry → eastmoney_industry_rest` | `eastmoney_industry`, `eastmoney_industry_rest` | 行业分类/概念板块首选源（push2 不稳时可切到 REST 行情页） |

示例 — 将行情首选从腾讯改为东方财富：

```json
{
  "preferred_provider": {
    "price": "eastmoney"
  }
}
```

示例 — 行业 push2 不稳定时直接走行情页 REST 链路（跳过 push2，仅行业分类，无概念板块）：

```json
{
  "preferred_provider": {
    "industry": "eastmoney_industry_rest"
  }
}
```

> `preferred_provider` 为空对象 `{}` 时全部使用默认优先级。
>
> **💡 指数数据说明：** A 股/美股指数由 `fetcher/index.py` 直调 Provider，**不走 Provider Chain**，不受 `preferred_provider` 控制。双链路自动 fallback：
>   - A 股：**腾讯财经→新浪财经→过期缓存**
>   - 美股：**新浪财经（2次重试）→腾讯财经→过期缓存**

## early_warning 可调参数

`early_warning` 控制智能预警模块的行为，用于发现持仓组合的异常信号。

| 子字段 | 默认值 | 说明 |
|--------|:------:|------|
| `sector_alert_threshold_warning` | `-50,000,000` (≈-5000万) | 行业资金净流出预警阈值（负值表示净流出），低于此值标记"⚠注意" |
| `sector_alert_threshold_danger` | `-200,000,000` (≈-2亿) | 行业资金净流出危险阈值，低于此值标记"🔴危险" |
| `sentiment_top_n` | `10` | 新闻情绪聚合时取 TOP N 持仓品种（按关联新闻数量排序） |

> 阈值均为负值（元），绝对值越大越不容易触发预警。默认值适合 A 股中等市值组合；持仓规模较大时可适当调高（如 warning 调至 -1 亿、danger 调至 -5 亿）。

## degradation 数据降级策略

`degradation` 控制数据降级行为（D 迭代引入），定义各层级数据在连续失败或空数据返回时切换到降级模式的阈值。

降级机制三层模型：

| 层级 | 含义 | 示例数据 |
|:----|:-----|:---------|
| **T2** | 功能级 — 某个功能模块不可用 | 新闻聚合、行业资金流向 |
| **T3** | 模块级 — 相对独立的数据模块 | 基金业绩排名、基金持仓穿透 |
| **T4** | 核心级 — 影响全局核心功能 | 股票价格、市场指数 |

每层三个参数：

| 参数 | 说明 |
|:-----|:-----|
| `unreachable_threshold` | 连续连接失败次数，达到后标记降级 |
| `empty_data_threshold` | 连续返回空数据的次数，达到后标记降级 |
| `stale_days` | 缓存过期天数，超过此天数的数据视为不可用 |

| 子字段 | `t2` | `t3` | `t4` |
|:-------|:----:|:----:|:----:|
| `unreachable_threshold` | `2` | `2` | `1` |
| `empty_data_threshold` | `3` | `3` | `1` |
| `stale_days` | `3` | `14` | `14` |

> 两个信号（连续失败 / 空数据）任一达到阈值即触发降级，取最低有效阈值。`stale_days` 仅在缓存存在时参与计算——当缓存过期天数超过此值且连续失败计数 ≥ `unreachable_threshold` 时强化降级判定。
> 
> T4 阈值最严格（1 次失败即降级）：核心价格/指数数据需要快速切换降级策略。T2/T3 允许更多容错（2~3 次），避免偶发网络波动触发不必要的降级。

## user_fund_benchmarks 自定义基准

`user_fund_benchmarks` 用于覆盖部分基金的业绩比较基准。代码内置了主流宽基/行业指数（沪深 300、中证 500、纳斯达克 100 等），遇到不在内置库中的基金时，可通过此字段手动指定。

格式：`{"基金代码": "基准代码"}`，键值均为六位基金代码（字符串或数字均可）。

```json
{
  "user_fund_benchmarks": {
    "000001": "000300",
    "005827": "399001",
    "110011": "000300"
  }
}
```

> 内置基准库实时自动补充，`user_fund_benchmarks` 仅在置信度不足时作为兜底。空对象 `{}` 表示不添加自定义覆盖。

## report_section_order 报告序号配置（v0.2.86+）

`report_section_order` 用于自定义报告 16 个模块的显示序号和排列顺序。

| 子字段 | 格式 | 说明 |
|--------|:----:|------|
| 键 | 模块标识 | 报告模块的唯一标识，见下方列表 |
| 值 | 正整数 | 显示序号（1~99），决定该模块在报告中的视觉位置 |

**16 个模块标识及默认顺序：**

| 默认序号 | 模块标识 | 显示名称 | 类型 |
|:--------:|:---------|:---------|:-----|
| 1 | `summary` | 投资分析汇总 | 始终显示 |
| 2 | `market_value` | 市值核算明细表 | 始终显示 |
| 3 | `category` | 持仓分类表 | 始终显示 |
| 4 | `penetration` | 资产穿透TOP10 | 始终显示 |
| 5 | `fund_performance` | 基金业绩分析 | 始终显示 |
| 6 | `fund_manager` | 基金经理变更监控 | B 系列（有数据才显示） |
| 7 | `fund_overlap` | 持仓重合度矩阵 | B 系列（有数据才显示） |
| 8 | `fund_concentration` | 持仓集中度监控 | B 系列（有数据才显示） |
| 9 | `fund_style` | 基金风格分析 | B 系列（有数据才显示） |
| 10 | `news_correlation` | 财经新闻热点与持仓关联分析 | 新闻（需启用） |
| 11 | `early_warning` | 智能预警 | 新闻（需启用） |
| 12 | `global_macro` | 全球政经局势 | LLM |
| 13 | `expert_review` | 智囊团深度复盘 | LLM |
| 14 | `health_check` | 持仓体检报告 | LLM |
| 15 | `penetration_deep` | 穿透深度分析 | LLM |
| 16 | `llm_usage` | LLM API 用量 | LLM（**始终最后**） |

**使用示例：**

将基金深度分析模块提到最前面：

```json
{
  "report_section_order": {
    "fund_manager": 1,
    "fund_overlap": 2,
    "fund_concentration": 3,
    "fund_style": 4,
    "summary": 5
  }
}
```

> 效果：基金经理/重合度/集中度/风格 4 个模块显示序号 1~4 并排在最前，投资分析汇总显示序号 5 紧随其后，其余未配置模块保持默认顺序排在更后。`llm_usage` 强制最后，不受配置影响。
>
> 空对象 `{}` 或缺失此字段时使用上述 16 项默认顺序，行为与旧版本一致。

## cache_ttl 可调参数

> `—` 表示该缓存类型文件名为精确键名（无指纹后缀），不受持仓变化影响，仅在 TTL 到期后刷新。

### 行情/数据类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `price` | `price_{code}.json` | 24h（交易时段 30s） | — | 股票/基金最新价、昨收 |
| `index` | `index_{code}.json` | 24h（交易时段 30s） | — | 市场指数行情 |
| `news` | `news_{md5}.json` | 15 分钟 | 新闻源参数 + 关键词 | 多源新闻聚合结果 |
| `sector_flow` | `sector_flow_{fingerprint}.json` | 15 分钟 | A股+美股指数 | 行业资金流向排名 |
| `rank` | `fund_perf_{code}.json` | 24h | — | 基金同类排名+区间收益率 |
| `profit_forecast` | `profit_forecast_{fingerprint}.json` | 24h | A股+美股指数 | 机构盈利预测全量数据 |
| `hold` | `fund_hold_{code}.json` | 7 天 | — | 基金前 10 持仓明细 |
| `industry` | `industry_{code}.json` | 14 天 | — | 行业分类/概念板块 |
| `dividend` | `dividend_{fingerprint}.json` | 30 天 | 持仓+穿透 A 股代码列表 | 股票历史分红汇总 |
| `benchmark` | `fund_benchmarks.json` | 30 天 | — | 业绩比较基准对照表 |

### LLM 分析类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `llm_expert_review` | `llm_expert_review_{fingerprint}.json` | 2h | 持仓汇总 + 分类计数 + 穿透 TOP10 + 持仓明细 | 智囊团深度复盘 |
| `llm_news_correlation` | `llm_news_item_{hash}.json`（逐条） | 1h | 标题前 80 字 + 持仓指纹 | 财经新闻热点与持仓关联分析 |
| `llm_global_macro` | `llm_global_macro_{fingerprint}.json` | 24h | A股/美股指数 + 持仓汇总 | 全球政经局势 |
| `llm_health_check` | `llm_health_check_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 持仓体检报告 |
| `llm_penetration_deep` | `llm_penetration_deep_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 穿透深度分析 |

### 基金深度分析类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `fund_manager` | `fund_manager_{code}.json` + `fund_manager_snapshot.json` | 24h | — | 基金经理数据 + 快照（refresh 组） |
| `fund_overlap` | （实时计算，无独立缓存，推导自 `fund_hold_{code}.json`） | 7 天 | — | 基金持仓重合度数据（refresh 组，前缀用于清理注册） |
| `fund_concentration` | `fund_concentration_snapshot.json` | 30 天 | — | 集中度历史快照（精确键名，无分组） |
| `fund_style_snapshot` | `fund_style_snapshot.json` | 30 天 | — | 风格快照（精确键名，无分组） |

### 系统类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `tracking` | `holdings_tracking.json` | 30 天 | — | 持仓跟踪数据（精确键名，无指纹） |
| `calendar` | `trading_calendar.json` | 14 天 | — | A 股交易日历（精确键名，无指纹） |

> **指纹驱动失效：** 文件名中的 `{fingerprint}` 是输入数据的 MD5 哈希。持仓/指数数据变化时指纹自动改变，原缓存失效，无需手动清除。
> 
> **TTL 兜底：** 即使指纹未变，缓存文件仍有 TTL 兜底到期自动刷新，防止数据"永久有效"。

### 缓存分组

所有缓存模块归入两个分组，控制菜单命令的缓存清除范围：

| 分组 | 包含模块 | 使用场景 |
|------|---------|----------|
| `preload` | 股票价格、市场指数、LLM 全球政经局势、LLM 智囊团深度复盘、LLM 持仓体检报告、LLM 穿透深度分析 | **切换持仓文件后必须重取的数据。** 价格/指数随持仓变动，LLM 基础分析依赖持仓内容，切换到新持仓文件时必须清除旧缓存 |
| `refresh` | 基金业绩排名、基金持仓、行业分类、新闻聚合、LLM 新闻关联分析、机构盈利预测、行业资金流向、股票历史分红、基金业绩基准、基金经理数据、持仓重合度 | **可随时独立刷新的补充数据。** 不依赖持仓文件切换，任何时候都可以主动刷新 — 如盘中更新行业资金流向、拉取最新基金排名 |

**无分组的模块**（`tracking` 持仓跟踪、`calendar` 交易日历、`fund_concentration` 集中度历史快照、`fund_style_snapshot` 风格快照）：未被任何分组覆盖，不会被菜单缓存命令误删。对应 TTL 可通过 `cache_ttl.{key}` 自行调整。

#### 与菜单命令的对应关系

- **菜单 `[1]` 更新基础类缓存** → 清除 `refresh` 组全部缓存，然后重新拉取。适合：启动后先刷新补充数据，再生成报告。纯股票组合时自动跳过基金排名/持仓/基准刷新，仍主动重拉行业分类、分红、盈利预测、资金流向。新闻缓存清除后由后续报告生成按需重建。
- **菜单 `[2]` 更新持仓类缓存** → 清除 `preload` 组全部缓存，然后并行拉取新持仓的价格和指数。适合：切换到另一份持仓文件时一键清理依赖旧持仓的缓存。

两组互不重叠：`[1]` 不会误删价格/指数缓存，`[2]` 不会误删基金排名/行业分类缓存。

#### 工作原理

缓存分组由 `src/python/registry.py` 中的模块注册表驱动。每个模块注册时指定所属分组（`cache_groups` 字段），`cache.py:clear_by_group()` 遍历注册表，只清除匹配分组的模块缓存文件。新增缓存模块时只需在注册表中声明分组，无需修改菜单代码。

> **调整建议：** 持仓变动少可将 `hold` 改为 `2592000`（30天），减少基金持仓的重复拉取。
>
> **交易时段短 TTL：** `price` 和 `index` 默认注册在 `market_hour_aware` 中，A 股交易时段（09:30–11:30 + 13:00–15:00）自动使用 `market_hour_ttl`（默认 30s）替代常规 TTL，确保盘中实时行情。收盘后自动回落长 TTL 保持收盘价。可通过 `market_hours.start`/`end` 手动覆盖时段，或设 `market_hours.official_source: false` 关闭东方财富 API 实时状态查询。
> **收市后价格缓存新鲜度校验：** 盘后长 TTL 场景下，`fetcher/price.py` 自动校验缓存是否来自当前交易日。若盘中因 Tencent 名称校验失败降级到 EastMoney 写入了上一交易日净值，收市后首次请求时将检测到该残留数据（`price_date < trading_day`），自动清除缓存并强制从 Provider Chain 重取。此行为不依赖额外配置，对所有 `price_*` 缓存全局生效。

## 技术细节：自动 gzip 压缩

超过 100KB 的缓存文件自动以 `.json.gz` 格式压缩存储（如 `profit_forecast_*.json.gz`），节省约 80-90% 磁盘空间。读取时透明解压，无需任何配置或迁移。小文件保持原 `.json` 格式，热路径无额外开销。
