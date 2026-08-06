# 配置指南

主配置文件 `data/config/config.json`，程序首次启动时自动创建。

```json
{
  // ── A. 路径与文件 ──
  "holdings_dir": "data/holdings",
  "holdings_filename": "个人投资持仓信息.xlsx",
  "holdings_start_date": "",  // 组合建仓日期（YYYY-MM-DD，可选）：未录入交易/分红流水时按「建仓日一次性买入」近似年化；空=仅成本分档近似
  "output_dir": "reports",
  "llm_key_file": "data/config/llm_key.json",
  "llm_settings_file": "data/config/llm_settings.json",
  "llm_providers_file": "data/config/llm_providers.json",

  // ── B. 报告章节可见性 ──
  "enable_fund_deep_analysis": true,  // 基金深度分析+因子暴露+相关性
  "enable_news": true,      // 市场新闻
  "enable_history": true,   // 组合历史走势与回撤
  "enable_portfolio_evolution": true,  // 组合演进
  "enable_action": true,     // 行动建议（默认开，可在菜单 P 关闭）
  // 报告子模块开关（数据质量仪表盘为长期可信核心默认开启；其余新增能力默认关闭，避免既有报告突然"变胖"）
  "report_submodules": {"data_quality": true, "industry_beta": false, "candidate_compare": false, "cost_lots": false, "valuation_percentile": false, "market_temperature": false},  // 数据质量仪表盘默认开，其余默认关
  "comparison_candidates": [],  // 候选基金比较子表候选（6 位基金代码列表，≤10；配合 candidate_compare）

  // ── C. 数据源与提供商 ──
  "news_top_count": 300,
  "news_sources": {
    "sina": true,
    "eastmoney": true,
    "cls": false,
    "wallstreetcn": true,
    "akshare": true
  },
  "preferred_provider": {},

  // ── D. 市场时段与缓存 ──
  "market_hour_aware": ["price", "index"],
  "market_hour_ttl": 30,
  "market_hours": {
    "start": "09:30",
    "end": "15:00",
    "official_source": true
  },
  "cache_ttl": {
    "price": 86400,
    "index": 86400
    // ...（完整列表见下方 cache_ttl 章节）
  },

  // ── E. 行为调优 ──
  "default_menu_key": "L",
  "report_section_order": {},
  "degradation": {
    "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},
    "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},
    "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14}
  },

  // ── F. 业绩基准与无风险利率 ──
  "risk_free_rate": null,
  "user_fund_benchmarks": {},
  "comparison_indices": {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"},

  // ── G. 组合历史走势与持仓快照 ──
  "history": {
    "fetch_mode": "auto",  // 历史走势获取模式: off=关闭 / prompt=报告后询问 / auto=自动获取
    "lookback_days": 90,  // 历史走势取数窗口（K 线条数/交易日），需≥60（回撤矩阵最少交易日）才计算回撤矩阵，上限 365
    "snapshot_retention_days": 60,
    "snapshot_max_count": 365,
    "coverage_threshold": 0.8,
    "benchmark_indices": {"sh000300": "沪深300"}
  },

  // ── H. 业绩评价配置 ──
  "performance_evaluation": {
    "excess_threshold_up": 80,      // 超额收益 >= 此值 -> 上调一级
    "excess_threshold_down": 40     // 超额收益 < 此值 -> 下调一级
  },

  // ── I. 再平衡配置 ──
  "rebalance": {
    "threshold": 0.15,
    "deviation_threshold": 0.05,
    "profile": "moderate",
    "silence_days": 30,
    "target_allocation": {},
    "equity_fixed_income": {}
  },

  // ── 交易纪律配置 ──
  "discipline": {
    "take_profit_pct": 20.0,
    "stop_loss_pct": -15.0,
    "drawdown_pct": -10.0,
    "silence_days": 30
  },

  // ── J. 流动性配置 ──
  "redemption_limits": {},

  // ── K. 匿名化配置 ──
  "anonymization": {
    "mode": "off"
  },

  // ── L. 批量并行调度 ──
  "batch": {
    "max_total_workers": 15,
    "fund_workers": 3,
    "industry_workers": 8
  },
  "batch_rate_limit": {
    "tencent": 0.0,
    "sina": 0.0,
    "eastmoney": 0.1,
    "tiantian": 0.5,
    "eastmoney_industry": 0.05
  }
}
```

## 字段说明

以下字段可通过 TUI 主菜单的对应命令修改（运行 `.venv/bin/python -m src.python.tui` 进入主菜单）。标有"手动编辑"的字段需直接修改 JSON 文件。

| 字段 | 默认值 | 说明 | TUI 修改 |
|------|--------|------|----------|
| `holdings_dir` | `data/holdings` | 持仓 xlsx 文件所在目录 | 菜单 `C` |
| `holdings_filename` | `个人投资持仓信息.xlsx` | 要读取的持仓文件名 | 菜单 `F` |
| `holdings_start_date` | `""` | 组合建仓日期（YYYY-MM-DD，可选）。持仓 Excel 未录入交易/分红流水时，成本流水子模块按「建仓日一次性买入」近似年化；空=不计算近似年化，仅成本分档近似（每份成本 vs 市价）。须配合 `report_submodules.cost_lots` 开启 | 手动编辑 |
| `output_dir` | `reports` | 报告输出目录（最新版+按日期存档） | 菜单 `O` |
| `llm_key_file` | `data/config/llm_key.json` | LLM 密钥文件路径（4 个必填字段 + 4 个可选回退字段） | 手动编辑 |
| `llm_settings_file` | `data/config/llm_settings.json` | LLM 非敏感配置文件路径 | 手动编辑 |
| `llm_providers_file` | `data/config/llm_providers.json` | LLM 多 Provider 链式服务配置文件路径，参见 [LLM 配置指引](how-to-config-llm.md) | 手动编辑 |
| `news_top_count` | `300` | 财经新闻热点与持仓关联分析输出条目上限（各源原始获取量 = max(500, news_top_count × 2)，华尔街见闻硬上限 100 条除外） | 手动编辑 |
| `news_sources` | 见下方 | 各新闻数据源启停开关 | 手动编辑 |
| `preferred_provider` | `{}` | 各数据类型的首选提供商覆写 | 手动编辑 |
| `market_hour_aware` | `["price", "index"]` | 交易时段内使用短 TTL 的数据类型列表 | 手动编辑 |
| `market_hour_ttl` | `30` | 交易时段内 market_hour_aware 类型的缓存有效期（秒），最短 30s，最长 86400s。低于 30s 的值在配置校验时告警，运行时自动钳制到 30s | 手动编辑 |
| `market_hours` | `{start: "09:30", end: "15:00", official_source: true}` | 市场时段配置（见 §market_hours 章节） | 手动编辑 |
| `cache_ttl.*` | 见下方 | 各缓存类型有效期（秒） | 手动编辑 |
| `default_menu_key` | `L` | TUI 菜单缺省选项的快捷键（E/B/L/W/C/F/O/1/2/3/4/P/I/A/S/R/X），启动后光标自动定位 | 手动编辑 |
| `report_section_order` | `{}` | 报告模块序号配置。空对象使用默认顺序（19 项）。键=模块标识，值=序号；已配置模块按序号升序在前，未配置模块按默认顺序在后。`llm_usage` 强制末位 | 手动编辑 |
| `degradation` | `{...}` | 数据降级策略（T2/T3/T4 各层的连续失败阈值、空数据阈值、缓存过期天数，见 §degradation 章节） | 手动编辑 |
| `user_fund_benchmarks` | `{}` | 自定义基金业绩基准覆盖（键=基金代码，值=基准代码） | 手动编辑 |
| `comparison_indices` | `{"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"}` | 竞争语境对比指数池。智囊团深度复盘中对比组合 vs 多指数的今日涨跌幅、区间累计收益和指标（夏普/波动率/最大回撤）。格式 `{指数代码: 显示名称}`。禁用时设为空对象 `{}` | 手动编辑 |
| `risk_free_rate` | `null` | 无风险利率手动配置（null=自动从国债收益率获取，填小数如0.0174或百分比如1.74）。程序默认通过 akshare `bond_zh_us_rate` 获取中国 10Y 国债收益率 | 手动编辑 |
| `history.fetch_mode` | `"auto"` | 组合历史走势获取模式：`"off"`=关闭、`"prompt"`=报告后询问、`"auto"`=自动获取（默认） | 手动编辑 |
| `history.lookback_days` | `90` | 组合历史走势取数窗口（K 线条数/交易日）。需 ≥60（回撤矩阵所需最少交易日）才计算回撤矩阵，上限 365（K 线源最多返回条数）。股票/ETF 按此取 K 线条数，OTC 基金全量净值截取最近 N 条 | 手动编辑 |
| `history.snapshot_retention_days` | `60` | 持仓快照保留天数（`data/history/snapshots/`），超期自动删除 | 手动编辑 |
| `history.snapshot_max_count` | `365` | 持仓快照最大数量上限，超限删除最旧的（安全兜底） | 手动编辑 |
| `history.coverage_threshold` | `0.8` | 有效区间覆盖比例阈值（0~1）。有效区间起算日和截止日均要求 ≥此比例×总持仓 有数据，否则向前/向后递延截断。提高该值可增加起算日市值真实性，但会缩短有效区间 | 手动编辑 |
| `history.benchmark_indices` | `{"sh000300": "沪深300"}` | 基准指数配置，格式 `{指数代码: 显示名称}`。组合历史走势图上叠加显示这些指数的归一化曲线。禁用时可设为空对象 `{}` | 手动编辑 |
| `performance_evaluation.excess_threshold_up` | `80` | 超额收益 ≥ 此值（百分点）时基金业绩评级上调一级 | 手动编辑 |
| `performance_evaluation.excess_threshold_down` | `40` | 超额收益 < 此值（百分点）时基金业绩评级下调一级 | 手动编辑 |
| `rebalance.threshold` | `0.15` | 单品种权重超限阈值（15%），超限触发再平衡建议 | 手动编辑 |
| `rebalance.deviation_threshold` | `0.05` | 大类/品种配置偏离阈值（5%），权益/固收偏离超限时触发调整建议 | 手动编辑 |
| `rebalance.profile` | `"moderate"` | 预设阈值集：conservative（保守 10%/3%）/ moderate（稳健 15%/5%）/ aggressive（进取 25%/8%）/ custom（自定义） | 手动编辑 |
| `rebalance.silence_days` | `30` | 再平衡信号静默期天数。同一品种触发再平衡后 N 天内不再重复 | 手动编辑 |
| `rebalance.target_allocation` | `{}` | 目标配置 Schema（空=不启用）。格式 `{"equity":{"min":30,"max":70,"target":50}, "bond":{...}}` | 手动编辑 |
| `rebalance.equity_fixed_income` | `{}` | 权益/固收超大类目标配置（空=不启用）。格式 `{"equity":{"min":30,"max":70}}` | 手动编辑 |
| `discipline.take_profit_pct` | `20.0` | 止盈线（%）：单品种收益率 ≥ 此值 → 建议部分止盈 | 手动编辑 |
| `discipline.stop_loss_pct` | `-15.0` | 止损线（%）：单品种收益率 ≤ 此值 → 建议止损/减仓 | 手动编辑 |
| `discipline.drawdown_pct` | `-10.0` | 回撤线（%）：组合相对历史峰值回撤 ≥ 此绝对值 → 建议控回撤（需组合历史估值数据提供峰值） | 手动编辑 |
| `discipline.silence_days` | `30` | 交易纪律信号静默期天数。同一品种触发纪律后 N 天内不再重复告警 | 手动编辑 |
| `redemption_limits` | `{}` | 场外基金单日赎回上限，格式 `{基金代码: 金额}`。配置后程序可计算场外品种全量赎回所需天数。未配置品种标记"需手动确认赎回上限" | 手动编辑 |
| `anonymization.mode` | `"off"` | 匿名化模式：`off`（关闭，显示真实名称代码）/ `code_display`（名称→"品种X"，保留代码和盈亏）/ `full_anonymous`（名称→"品种X"，代码→"000XXX"，盈亏→±XX%）/ `summary`（仅大类汇总） | 菜单 `A` |
| `enable_fund_deep_analysis` | `true` | 基金深度分析章节可见性，关闭后对应章节完全隐藏，不产生序号空缺 | 菜单 `P` |
| `enable_news` | `true` | 市场新闻章节可见性，关闭后对应章节完全隐藏。与 `news_sources` 区别：前者控制章节在报告中的显示/隐藏，后者控制数据源启停 | 菜单 `P` |
| `enable_history` | `true` | 历史走势章节可见性（组合历史走势与回撤，一章两区块：走势表 + 回撤矩阵 + 危机区间标注），关闭后对应章节完全隐藏。持仓快照不受影响，始终自动执行 | 菜单 `P` |
| `enable_portfolio_evolution` | `true` | 组合演进章节可见性，关闭后对应章节完全隐藏。持仓快照仍照常记录，仅影响报告展示 | 菜单 `P` |
| `enable_action` | `true` | 行动建议章节可见性，**默认开启**，关闭后隐藏 再平衡信号/交易纪律/调仓建议/收益归因 行动板块（纯算法，basic/both/full 均可见）。智囊团深度复盘同步隐藏「行动摘要」子块 | 菜单 `P` |
| `report_submodules.data_quality` | `true` | 数据质量仪表盘子模块开关，**默认开启**（长期可信核心）。开启后报告展示数据质量仪表盘区块（数据覆盖/时效性/降级状态） | 菜单 P → 6 |
| `report_submodules.candidate_compare` | `false` | 「基金业绩分析」章候选基金比较子表开关，**默认关闭**。开启后报告在该章主业绩表下方展示候选基金横向比较表（候选来自 `comparison_candidates`，比较维度：收益近1月/3月/6月/1年、同类排名、评级、最大回撤、风格、与现有持仓重合度） | 菜单 P → 6 |
| `comparison_candidates` | `[]` | 候选基金比较子表的候选基金代码列表（6 位基金代码，≤10 只）。需配合 `report_submodules.candidate_compare` 开启；非法代码自动忽略，超过 10 只仅比较前 10 只 | 手动编辑 |
| `report_submodules.valuation_percentile` | `false` | 「资产穿透TOP10」章估值分位列开关，**默认关闭**。开启后该章为每只 TOP 持仓显示「估值分位」列（当前 PE/PB，来自东财行情扩展字段 + 3~5 年价格分位代理，代理结果显式标注"价格分位代理，非真实历史估值分位"） | 菜单 P → 6 |
| `report_submodules.market_temperature` | `false` | 「投资分析汇总」章市场温度刻度行开关，**默认关闭**。开启后该章「市场指数」行下方显示「市场温度」行（沪深300 价格分位+20日均线偏离+年化波动率三因子合成温度计，仅提示贵贱无仓位指令，含免责声明） | 菜单 P → 6 |
| `report_submodules.industry_beta` | `false` | 「风格与因子分析」章行业 Beta 子表开关，**默认关闭**。开启后该章展示行业 Beta 子表（组合对中证行业指数的回归敏感性：行业暴露占比 + β/t 值/显著性/相关性） | 菜单 P → 6 |
| `report_submodules.cost_lots` | `false` | 成本流水开关，**默认关闭**。开启后汇总/市值/分类页签渲染成本分档 + XIRR + 分红累计：持仓 Excel 含交易/分红流水走精确计算；无流水时自动切换为快照近似（按 `holdings_start_date` 建仓日一次性买入近似年化，未配置则仅成本分档近似），XIRR 标注「近似」 | 菜单 P → 6 |

---

### A. 路径与文件

路径/文件相关字段（`holdings_dir`、`holdings_filename`、`holdings_start_date`、`output_dir`、`llm_key_file`、`llm_settings_file`、`llm_providers_file`）见上方字段总表。

---

### B. 报告章节可见性

`enable_fund_deep_analysis`、`enable_news`、`enable_history`、`enable_portfolio_evolution`、`enable_action` 五个配置项控制报告按章节组显示或隐藏对应的章节。LLM 分析章节的可见性由 `llm_settings.json` 的 `enabled_llm` 字典控制。关闭某个章节组后，该组涉及的所有章节完全隐藏，不留下序号空缺，剩余章节按顺序重新编号。

通过 TUI 主菜单 `[P]` 配置报告可选章节进入交互式子菜单，可逐个切换基金深度分析/市场新闻/历史走势/组合演进/行动建议 5 个章节组的可见性。

| 字段 | 默认值 | 配置来源 | 控制章节 | 说明 |
|:-----|:------:|:---------|:---------|:-----|
| `enable_fund_deep_analysis` | `true` | `config.json` | 基金经理变更监控、持仓关系矩阵、持仓集中度监控、风格与因子分析 | 基金深度分析章节组 |
| `enable_news` | `true` | `config.json` | 财经新闻热点与持仓关联分析 | 市场新闻章节组 |
| `enable_history` | `true` | `config.json` | 组合历史走势与回撤 | 历史走势章节组（持仓快照不受影响，始终自动执行） |
| `enable_portfolio_evolution` | `true` | `config.json` | 组合演进 | 组合演进章节组（持仓快照不受影响，始终自动执行） |
| `enable_action` | `true` | `config.json` | 行动建议 | 行动建议章节组（再平衡信号/交易纪律/调仓建议/收益归因，纯算法） |
| `enabled_llm`（4 个报告模块） | `true` | `llm_settings.json` | 全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析、LLM API 用量 | LLM 分析章节组。任一报告模块启用即整体可见，仅 `news_correlation` 开启时不显示 |

> **enable_news 与 news_sources 的区别：** `enable_news` 控制报告章节的可见性——是否在报告中显示新闻相关章节；`news_sources` 控制数据源的启停——报告生成时从哪些新闻提供商获取数据。两者独立配置：`enable_news: true` 并关闭所有 `news_sources` 时章节仍显示但无数据可用；反之开启数据源但 `enable_news: false` 时章节完全隐藏。

---

### C. 数据源与提供商

#### news_sources 可调字段

| 子字段 | 默认 | 说明 |
| `sina` | `true` | 新浪财经（财经要闻/国内/国际，正常工作） |
| `eastmoney` | `true` | 东方财富（np-weblist 快讯接口，req_trace 参数，稳定可用） |
| `cls` | `false` | 财联社（API 要求签名鉴权，匿名请求不可用） |
| `wallstreetcn` | `true` | 华尔街见闻（全球财经直播流，JSON API，无需鉴权，推荐开启） |
| `akshare` | `true` | akshare（财新网要闻 + CCTV 财经新闻，开源封装，推荐开启） |

> **用法：** 将值改为 `true` 或 `false` 即可启用/禁用对应新闻源。

#### preferred_provider 可调字段

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

---
### D. 市场时段与缓存

#### market_hours 可调参数

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

`official_source` 启用时，程序通过东方财富 push2 API 获取实时交易状态，根据开/午休/收盘状态自动切换缓存 TTL：盘中 60 秒高频刷新，盘后 7 天长效缓存。

> **午餐休市：** 实际交易分为 09:30–11:30（上午）和 13:00–15:00（下午）两段。即使 `start`/`end` 覆盖为 `"09:30"`/`"15:00"`，午餐时段（11:30–13:00）自动视为非交易时段并回落长 TTL。`official_source: true` 时 API 返回 `status=3`（午间休市）也会让系统识别午餐休市。

#### cache_ttl 可调参数

> `—` 表示该缓存类型文件名为精确键名（无指纹后缀），不受持仓变化影响，仅在 TTL 到期后刷新。

快速定位：— [行情/数据类](#行情数据类) — [LLM 分析类](#llm-分析类) — [基金深度分析类](#基金深度分析类) — [系统类](#系统类) — [历史走势类](#历史走势类)

#### 行情/数据类

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

#### LLM 分析类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `llm_expert_review` | `llm_expert_review_{fingerprint}.json` | 2h | 持仓汇总 + 分类计数 + 穿透 TOP10 + 持仓明细 | 智囊团深度复盘 |
| `llm_news_correlation` | `llm_news_item_{hash}.json`（逐条） | 1h | 标题前 80 字 + 持仓指纹 | 财经新闻热点与持仓关联分析 |
| `llm_global_macro` | `llm_global_macro_{fingerprint}.json` | 24h | A股/美股指数 + 持仓汇总 | 全球政经局势 |
| `llm_health_check` | `llm_health_check_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 持仓体检报告 |
| `llm_penetration_deep` | `llm_penetration_deep_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 穿透深度分析 |

#### 基金深度分析类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `fund_manager` | `fund_manager_{code}.json` + `fund_manager_snapshot.json` | 24h | — | 基金经理数据 + 快照（refresh 组） |
| `fund_concentration` | `fund_concentration_snapshot.json` | 30 天 | — | 集中度历史快照（精确键名，无分组） |
| `fund_style_snapshot` | `fund_style_snapshot.json` | 30 天 | — | 风格快照（精确键名，无分组） |
| `extended` | `extended_{code}.json` | 24h | — | 基金风格扩展数据（市值/PE），refresh 组 |

#### 系统类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `tracking` | `holdings_tracking.json` | 30 天 | — | 持仓跟踪数据（精确键名，无指纹） |
| `calendar` | `trading_calendar.json` | 14 天 | — | A 股交易日历（精确键名，无指纹） |

#### 历史走势类

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `history_stock` | `history_stock_{code}*.json` | 7 天 | — | 股票/ETF 历史 K 线（腾讯/新浪），历史走势计算输入 |
| `history_fund_otc` | `history_fund_otc_{code}*.json` | 30 天 | — | 场外基金历史净值（天天基金→东方财富备用链路），历史走势计算输入 |
| `history_index` | `history_index_{code}*.json` | 30 天 | — | 指数历史 K 线（腾讯/新浪），基准指数走势计算输入 |

> **指纹驱动失效：** 文件名中的 `{fingerprint}` 是输入数据的 MD5 哈希。持仓/指数数据变化时指纹自动改变，原缓存失效，无需手动清除。
> 
> **TTL 兜底：** 即使指纹未变，缓存文件仍有 TTL 兜底到期自动刷新，防止数据"永久有效"。

---
### E. 行为调优

#### degradation 数据降级策略

`degradation` 控制数据降级行为，定义各层级数据在连续失败或空数据返回时切换到降级模式的阈值。

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
>
> **持久化位置**：降级状态（上次成功时间戳等）跨会话持久化到 `data/state/.degradation_state.json`。该目录独立于 `data/cache/`，不会被菜单 `[3]` 清理，确保下次会话启动时降级记忆恢复。

#### report_section_order 报告序号配置

`report_section_order` 用于自定义报告各模块的显示序号和排列顺序。

| 子字段 | 格式 | 说明 |
|--------|:----:|------|
| 键 | 模块标识 | 报告模块的唯一标识，见下方列表 |
| 值 | 正整数 | 显示序号（1~99），决定该模块在报告中的视觉位置 |

**19 个模块标识及默认顺序：**

| 默认序号 | 模块标识 | 显示名称 | 类型 |
|:--------:|:---------|:---------|:-----|
| 1 | `summary` | 投资分析汇总 | 始终显示 |
| 2 | `market_value` | 市值核算明细表 | 始终显示 |
| 3 | `category` | 持仓分类表 | 始终显示 |
| 4 | `penetration` | 资产穿透TOP10 | 始终显示 |
| 5 | `fund_performance` | 基金业绩分析 | 始终显示 |
| 6 | `fund_manager` | 基金经理变更监控 | 基金深度分析（enable_fund_deep_analysis 控制；有数据才显示） |
| 7 | `position_relationship` | 持仓关系矩阵 | 基金深度分析（enable_fund_deep_analysis 控制；有数据才显示，一章两区块：重合度 + 相关性） |
| 8 | `fund_concentration` | 持仓集中度监控 | 基金深度分析（enable_fund_deep_analysis 控制；有数据才显示） |
| 9 | `style_factor` | 风格与因子分析 | 基金深度分析（enable_fund_deep_analysis 控制；有数据才显示，一章三区块：基金风格表 + 风格因子回归 + 行业 Beta 子表） |
| 10 | `news_correlation` | 财经新闻热点与持仓关联分析 | 市场新闻（enable_news 控制） |
| 11 | `global_macro` | 全球政经局势 | LLM |
| 12 | `expert_review` | 智囊团深度复盘 | LLM |
| 13 | `health_check` | 持仓体检报告 | LLM |
| 14 | `penetration_deep` | 穿透深度分析 | LLM |
| 15 | `portfolio_history_drawdown` | 组合历史走势与回撤 | 历史走势（enable_history 控制；数据不可用时占位，一章两区块：走势表 + 回撤矩阵 + 危机区间标注） |
| 16 | `portfolio_evolution` | 组合演进 | 组合演进（enable_portfolio_evolution 控制；数据不可用时占位） |
| 17 | `action` | 行动建议 | 行动建议（enable_action 控制，**默认开**；再平衡信号/交易纪律/调仓建议/收益归因） |
| 18 | `data_source_status` | 数据源可用性矩阵 | 始终显示 |
| 19 | `llm_usage` | LLM API 用量 | LLM（**始终最后**） |

**使用示例：**

将基金深度分析模块提到最前面：

```json
{
  "report_section_order": {
    "fund_manager": 1,
    "position_relationship": 2,
    "fund_concentration": 3,
    "style_factor": 4,
    "summary": 5
  }
}
```

> 效果：基金经理/持仓关系矩阵/集中度/风格 4 个模块显示序号 1~4 并排在最前，投资分析汇总显示序号 5 紧随其后，其余未配置模块保持默认顺序排在更后。`llm_usage` 强制最后，不受配置影响。
>
> 空对象 `{}` 或缺失此字段时使用上述 19 项默认顺序。
>
> **本仓库配置**：`config.json` 的 `report_section_order` 已配置完整 18 项，将 `action`（行动建议）置于序号 10，其余模块依次顺延（`news_correlation`=11、`global_macro`=12、`expert_review`=13、`health_check`=14、`penetration_deep`=15、`portfolio_history_drawdown`=16、`portfolio_evolution`=17、`data_source_status`=18），与上表默认顺序仅差异在「行动建议提前至第 10 位」。清空为 `{}` 即恢复上表默认顺序（行动建议=17）。

**实用示例** — 将组合历史走势与回撤提到前面，关注回撤风险：

```json
{
  "report_section_order": {
    "portfolio_history_drawdown": 1,
    "summary": 2
  }
}
```

> 效果：组合历史走势与回撤（走势表 + 回撤矩阵 + 危机区间标注）排在第 1 位，投资分析汇总排在第 2 位，其余模块保持默认顺序。适合关注历史表现的用户。

---
### F. 业绩基准与无风险利率

#### user_fund_benchmarks 自定义基准

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

#### risk_free_rate 无风险利率

`risk_free_rate` 控制无风险利率的取值方式：

| 值 | 说明 |
|:---|:-----|
| `null` | 默认。自动从 akshare `bond_zh_us_rate` 获取中国 10Y 国债收益率 |
| 小数 | 如 `0.0174`，手动指定 1.74% |
| 百分数 | 如 `1.74`，自动识别为百分比（1.74%） |

> 无风险利率用于夏普比率、卡玛比率等量化指标的计算。

---
### G. 组合历史走势与持仓快照

#### history.fetch_mode 历史走势获取模式

`history.fetch_mode` 控制组合历史走势的获取行为：

| 模式 | 说明 |
|:----|:------|
| `"off"` | 关闭。不获取历史走势数据，报告中的"组合历史走势与回撤"章节显示占位文本 |
| `"prompt"` | 报告生成后询问用户是否需要获取历史走势数据（耗时约 15s） |
| `"auto"` | 自动获取，不询问用户（默认） |

> **数据获取链路**：股票/ETF 走腾讯 K 线历史 → 新浪备用；OTC 基金走天天基金历史净值 → 东方财富备用（空结果递补）。东方财富净值 API 使用 `pageSize=20` 分页获取（最多约 200 条≈10 个月），增量缓存逐步积累更久数据。
>
> **累计收益率起算**：从 `history.coverage_threshold` 比例持仓覆盖的日期起算（**双向截断**：起算点正向扫描 ≥阈值，截止点反向扫描 ≥阈值），避免因 QDII/债券基金数据起点较晚导致早期组合市值偏低、收益率虚高，也避免尾端部分基金净值未更新导致收益率虚低。早期数据保留在走势图上但排除出收益率计算。阈值默认 `0.8`（80%），可在 `config.json` 的 `history.coverage_threshold` 中调整。

#### history.lookback_days 取数窗口

`history.lookback_days` 控制组合历史走势往回取多少根 K 线/净值（交易日）：
- **股票/ETF**：向 K 线源请求最近 `lookback_days` 根日 K（腾讯/新浪，上限 365 根）
- **OTC 基金**：净值源全量返回后按最近 `lookback_days` 条截取

**与回撤矩阵的关系**：回撤矩阵需要 ≥60 个交易日（`MIN_SPAN`）才能计算独立回撤事件与最大回撤。若取数窗口低于 60，回撤矩阵将显示"有效交易日不足 60 天，暂不计算回撤事件"占位文本。默认 `90` 确保取数窗口超过门槛；配置值低于 60 或超过 365 时，配置校验会告警提示。

#### 持仓快照（快照对比）

快照对比不受 `history.fetch_mode` 配置影响，在 B/L 菜单生成报告时**始终自动执行**。每次生成报告时自动保存持仓快照到 `data/history/snapshots/`，供下次环比对比。

> **持仓快照自动清理**：保存新快照后自动清理旧文件。清理规则由 `history` 块中的以下字段控制：

| 字段 | 默认值 | 说明 |
|:-----|:------:|:-----|
| `snapshot_retention_days` | `60` | 超过此天数的快照自动删除（时间优先） |
| `snapshot_max_count` | `365` | 安全上限，超过此数量删除最旧的（数量兜底） |

可在 `config.json` 中设置：
```json
"history": {
    "fetch_mode": "auto",
    "lookback_days": 90,
    "snapshot_retention_days": 60,
    "snapshot_max_count": 365,
    "coverage_threshold": 0.8,
    "benchmark_indices": {"sh000300": "沪深300"}
}
```

> **基准指数对比**：`benchmark_indices` 配置需要在历史走势图上叠加对比的基准指数。格式为 `{指数代码: 显示名称}`，支持 A 股指数（如 `sh000300`）。获取方式走 `history_index` chain（腾讯/新浪双链路）。配置为空对象 `{}` 时不获取基准数据。

> **数据获取链路**：基准指数通过 `fetch_index_history()` → `history_index` chain → 腾讯 K 线 / 新浪 K 线（与组合持仓的个股 K 线共享熔断器）。数据写入缓存键 `history_index_{code}.json`。

---
### H. 业绩评价配置

#### performance_evaluation 基金业绩评级

`performance_evaluation` 段控制基金业绩评级的超额收益阈值，用于 `fund_performance.py` 对持仓基金进行业绩评级判定。

| 键 | 默认值 | 说明 |
|:---|:------:|:-----|
| `performance_evaluation.excess_threshold_up` | `80` | 超额收益 ≥ 此值（百分点）时评级上调一级 |
| `performance_evaluation.excess_threshold_down` | `40` | 超额收益 < 此值（百分点）时评级下调一级 |

超额收益 = 基金区间收益率 - 基准指数区间收益率。评级调整分为五档（低→较低→中等→较高→高），每个百分点差距触发一次调整。

---

### I. 再平衡配置

#### threshold 品种权重超限阈值

单品种持仓市值占总市值比例超过此阈值时，触发再平衡建议。默认 `0.15`（15%），可通过 `rebalance.threshold` 调整。

#### deviation_threshold 大类配置偏离阈值

权益/固收等大类配置偏离目标比例超过此阈值时，触发调整建议。默认 `0.05`（5%），可通过 `rebalance.deviation_threshold` 调整。

#### profile 预设阈值集

`rebalance.profile` 提供四套预设阈值组合：

| 预设 | threshold | deviation_threshold | 适用场景 |
|:-----|:---------:|:-------------------:|:---------|
| `conservative` | 10% | 3% | 保守型投资者，严格约束单品种暴露 |
| `moderate`（默认） | 15% | 5% | 稳健型投资者，允许适度集中 |
| `aggressive` | 25% | 8% | 进取型投资者，容忍较高集中度 |
| `custom` | 手动配置 | 手动配置 | 自定义阈值，profile 仅作标识 |

#### silence_days 再平衡静默期

同一品种触发再平衡后 `silence_days` 天内不再重复报警，避免频繁调仓。默认 `30` 天。

#### target_allocation 目标配置 Schema

`rebalance.target_allocation` 定义品种级目标配置范围，格式如下：

```json
{
  "equity": {"min": 30, "max": 70, "target": 50},
  "bond": {"min": 10, "max": 40, "target": 25}
}
```

空对象 `{}` 表示不启用此项检查。

#### equity_fixed_income 权益/固收大类配置

`rebalance.equity_fixed_income` 定义权益与固收超大类目标配置，格式如下：

```json
{
  "equity": {"min": 30, "max": 70},
  "fixed_income": {"min": 10, "max": 40}
}
```

空对象 `{}` 表示不启用此项检查。

---
### J. 流动性配置

#### redemption_limits 场外基金赎回上限

`redemption_limits` 配置场外基金的单日赎回上限，格式 `{基金代码: 金额}`：

```json
{
  "redemption_limits": {
    "000001": 50000,
    "005827": 10000
  }
}
```

配置后程序可计算场外品种全量赎回所需天数。未配置的品种在报告中标记"需手动确认赎回上限"。

---
### K. 匿名化配置

#### anonymization.mode 匿名化模式

`anonymization.mode` 控制报告中的持仓信息匿名化显示层级：

| 模式 | 名称 | 代码 | 盈亏 |
|:-----|:----|:----|:-----|
| `off`（默认） | 真实名称 | 真实代码 | 真实金额 |
| `code_display` | "品种X" | 保留代码 | 保留金额 |
| `full_anonymous` | "品种X" | "000XXX" | ±XX% |
| `summary` | 仅大类汇总 | — | — |

通过 TUI 主菜单 `[A]` 配置持仓匿名化可交互切换。

---
### L. 批量并行调度

#### batch 池配置

`batch` 段控制批量数据获取的线程池参数：

| 键 | 默认值 | 说明 |
|:---|:------:|:-----|
| `batch.max_total_workers` | `15` | 全局 batch 线程硬上限，超过时自动钳位 |
| `batch.fund_workers` | `3` | 基金排名/持仓批量并发数 |
| `batch.industry_workers` | `8` | 行业分类批量并发数 |

```json
"batch": {
  "max_total_workers": 15,
  "fund_workers": 3,
  "industry_workers": 8
}
```

#### batch_rate_limit Provider 请求间隔

`batch_rate_limit` 控制各数据源的请求间隔（秒），防止并发过高触发反爬限制：

| 键 | 默认值 | 说明 |
|:---|:------:|:-----|
| `tencent` | `0.0` | 腾讯行情（不限速） |
| `sina` | `0.0` | 新浪行情（不限速） |
| `eastmoney` | `0.1` | 东方财富行情（100ms） |
| `tiantian` | `0.5` | 天天基金（500ms） |
| `eastmoney_industry` | `0.05` | 东方财富行业（50ms） |

值为 0 表示不限速。配置后可通过菜单 `R` 刷新配置立即生效，无需重启程序。

---
### M. 功能开关（features.json）

`data/config/features.json` 提供 **27 项功能开关**的运行时覆写。文件仅需列出需覆写的开关，未列出的保持代码内置默认值：

```json
{
  "anonymizer": true,
  "news_cls": true
}
```

> **文件不必须存在** — 全部使用代码默认值时无需此文件。首次在菜单 **[S]** 切换辩论模式或手动创建后自动生效。
> **注意**：features.json 是唯一**不支持注释**的配置文件（标准 JSON，`//`/`/* */` 均不可用）。所有开关的默认值与完整说明见下表，或直接查看源码 `src/python/config/features.py` 的 `_FEATURE_FLAGS_DEFAULT`。

全部 27 项开关：

| 开关名 | 默认值 | 说明 |
|:-------|:------:|:-----|
| `llm_global_macro` | true | LLM 全球政经局势 |
| `llm_expert_review` | true | LLM 智囊团深度复盘 |
| `llm_health_check` | true | LLM 持仓体检报告 |
| `llm_penetration_deep` | true | LLM 穿透深度分析 |
| `llm_news_correlation` | true | LLM 财经新闻与持仓关联分析（实际启停还受 `llm_settings.json` 的 `enabled_llm` 控制） |
| `llm_debate_procon` | **false** | 辩论-正反辩论（三段式：白脸→黑脸→综合） |
| `llm_debate_conditional` | **false** | 辩论-条件推理（情景化分析：涨/跌/震荡） |
| `llm_debate_qa_concentration` | **false** | 辩论-集中度问答（集中度风险问答） |
| `fund_deep_analysis_fund_manager` | true | 基金深度分析-基金经理 |
| `fund_deep_analysis_fund_concentration` | true | 基金深度分析-基金集中度 |
| `news_sina` | true | 新闻源-新浪财经 |
| `news_eastmoney` | true | 新闻源-东方财富 |
| `news_cls` | **false** | 新闻源-财联社 |
| `news_wallstreetcn` | true | 新闻源-华尔街见闻 |
| `news_akshare` | true | 新闻源-akshare 封装 |
| `metrics_sharpe` | true | 量化指标-夏普比率 |
| `metrics_calmar` | true | 量化指标-卡玛比率 |
| `metrics_hhi` | true | 量化指标-HHI 集中度 |
| `metrics_winrate` | true | 量化指标-胜率 |
| `metrics_turnover` | true | 量化指标-换手率 |
| `metrics_risk_contribution` | true | 量化指标-风险贡献 |
| `metrics_beta` | true | 量化指标-Beta |
| `history_portfolio` | true | 历史走势-组合净值 |
| `history_benchmark` | true | 历史走势-基准指数 |
| `anonymizer` | false | 匿名化功能总开关（关闭后强制 off）；具体模式通过 config.json 的 anonymization.mode 设置 |
| `cache_daily_cleanup` | true | 启动时自动清理过期缓存 |
| `enable_interactive_charts` | true | 报告图表交互总开关（Chart.js 交互图，缩放/悬停）——**同时决定 HTML 报告是否单文件自包含**：开启时 8 个 Chart.js 资产内嵌进 HTML（下载到任意目录、单独发送到移动端浏览均正常，不依赖同目录 JS 文件）；关闭时回退到 Canvas + 表格静态渲染，HTML **不内嵌 JS**（需与 `reports/` 下的 .js 资产同目录才显示图表，移动/单发后会空白） |

> **菜单 [S] 的面板布局**：LLM 配置面板分两组——标准 LLM 模块（1-5，由 `llm_settings.json` 的 `enabled_llm` 控制）与 ⚗ 实验性辩论模式（6-8，由上方 `llm_debate_*` 开关控制，三项相互独立、可组合开启）。**正反辩论（`llm_debate_procon`）**开启后，智囊团复盘改为"看多 → 看空 → 收敛结论"三段式输出；**条件推理（`llm_debate_conditional`）**为分析注入上涨/下跌/震荡情景；**集中度问答（`llm_debate_qa_concentration`）**在单品种占比≥20% 时自动附加集中度量化评估——标准模式嵌入专家复盘输出，辩论模式嵌入综合权衡输出（位于调仓建议之前），均要求输出量化评估/基准对比/调仓建议。

> 以上 27 项为**全部**功能开关清单（默认值与代码 `features.py::_FEATURE_FLAGS_DEFAULT` 一致）。features.json 仅需列出需覆写的开关，未列出的保持默认值。
> 该文件不包含敏感信息，可安全纳入版本控制。

---
### N. 缓存分组

所有缓存模块归入两个分组，控制菜单命令的缓存清除范围：

| 分组 | 包含模块 | 使用场景 |
|------|---------|----------|
| `preload` | 股票价格、市场指数、LLM 全球政经局势、LLM 智囊团深度复盘、LLM 持仓体检报告、LLM 穿透深度分析 | **切换持仓文件后必须重取的数据。** 价格/指数随持仓变动，LLM 基础分析依赖持仓内容，切换到新持仓文件时必须清除旧缓存 |
| `refresh` | 基金业绩排名、基金持仓、行业分类、新闻聚合、LLM 新闻关联分析、机构盈利预测、行业资金流向、股票历史分红、基金业绩基准、基金经理数据、持仓重合度、基金风格扩展数据、无风险利率 | **可随时独立刷新的补充数据。** 不依赖持仓文件切换，任何时候都可以主动刷新 — 如盘中更新行业资金流向、拉取最新基金排名 |

**无分组的模块**（`tracking` 持仓跟踪、`calendar` 交易日历、`fund_concentration` 集中度历史快照、`fund_style_snapshot` 风格快照、`history_stock` 历史 K 线、`history_fund_otc` 历史净值、`history_index` 指数历史日线）：未被任何分组覆盖，不会被菜单缓存命令误删。对应 TTL 可通过 `cache_ttl.{key}` 自行调整。

### 与菜单命令的对应关系

- **菜单 `[1]` 更新基础类缓存** → 清除 `refresh` 组全部缓存，然后重新拉取。适合：启动后先刷新补充数据，再生成报告。纯股票组合时自动跳过基金排名/持仓/基准刷新，仍主动重拉行业分类、分红、盈利预测、资金流向。新闻缓存清除后由后续报告生成按需重建。
- **菜单 `[2]` 更新持仓类缓存** → 清除 `preload` 组全部缓存，然后并行拉取新持仓的价格和指数。适合：切换到另一份持仓文件时一键清理依赖旧持仓的缓存。

两组互不重叠：`[1]` 不会误删价格/指数缓存，`[2]` 不会误删基金排名/行业分类缓存。

> **调整建议：** 持仓变动少可将 `hold` 的 TTL 调大为 30 天，减少基金持仓的重复拉取。
>
> **交易时段短 TTL：** `price` 和 `index` 在 A 股交易时段（09:30–11:30 + 13:00–15:00）自动使用 `market_hour_ttl`（默认 30s）替代常规 TTL，确保盘中实时行情。收盘后自动回落长 TTL 保持收盘价。可通过 `market_hours` 配置手动调整。

---

### O. 机器本地状态（非 config.json）

以下状态**不存放于 config.json**，而是存于 `data/state/local_state.json`（git 忽略，仅本机可见）：

| 状态键 | 说明 |
|:-------|:-----|
| `_startup_wizard_shown` | 首次运行引导是否已显示 |
| `_privacy_notice_shown` | 隐私声明是否已显示 |

**为什么独立存放：** config.json 受 git 跟踪、用于跨机器同步。若把"本机是否已看过引导"这类个性化标志写入 config.json，每台机器会写入各自不同的值，导致 config.json 难以同步。故机器个性化状态统一放 `data/state/` 目录（与熔断器状态、再平衡静默期等同目录），不参与同步。这两个键仅由 `config/_local_state.py` 在 `data/state/local_state.json` 中读写，不做任何 config.json 迁移。
