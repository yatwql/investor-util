# 投资分析报告小工具 — 技术文档

创建日期：2026-06-28

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
| TUI 入口 | 菜单循环、用户交互、流程编排 | `src/main.py` |
| 配置管理 | config.json + llm.json 读写、mtime 缓存 | `src/config.py` |
| 缓存引擎 | 泛用 JSON 缓存、TTL、指纹失效、过期清理 | `src/cache.py` |
| 数据获取 | Provider Chain 路由、fallback、缓存预热 | `src/fetcher.py` |
| 持仓读取 | xlsx 解析、多工作表、列校验 | `src/reader.py` |
| LLM 客户端 | Claude / OpenAI / DeepSeek API 调用 | `src/llm_client.py` |
| 报告生成 | Excel (openpyxl) + HTML (Jinja2) | `src/report/*.py` |

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
| 财经新闻（东方财富） | 东方财富 `push-api-html.eastmoney.com` | — | `eastmoney_news.py` |
| 财经新闻（财联社） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — | `cls_news.py` |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com` 三级行业 + 概念板块 | — | `eastmoney_industry.py` |

---

## 缓存策略

详见 `docs-stm/README.md` 的「缓存文件指引」章节。

### 新增：行业/概念缓存

| 文件名 | 用途 | 默认 TTL | 清除方式 |
|--------|------|---------|---------|
| `industry_{code}.json` | 单只证券的行业分类和概念板块归属 | 7 天 | 菜单 [1] 清理或过期自动清理 |

---

## 模块技术要点

### 模块 4：资产穿透 TOP10

- `compute_penetration_top10()` 纯计算函数，不依赖 openpyxl
- 分类逻辑（QDII/ETF/联接/债券/主动/直接持股）基于代码前缀 + 名称规则
- 板块分类 `classify_sector()` 使用静态关键词映射，同时支持 API 行业数据补充
- 调用 `batch_fetch_industry_data()` 为穿透结果注入行业信息（覆盖静态关键词的局限）

### 模块 6：财经新闻关联分析

- 3 源并行获取（ThreadPoolExecutor max_workers=3）
- 新闻缓存 `news_{md5}.json`，15 分钟 TTL，MD5 指纹含关键词/参数
- 关键词提取：持仓名称片段 + 代码 + 穿透资产 + **行业名称 + 概念板块**
- 关键词富化 4 种类型：持仓(0) → 穿透(1) → 概念(2) → 行业(3)
- 概念类型：来源为东方财富 push2 API 的行业分类和概念板块
- HTML 富化显示：蓝(持仓) / 紫(穿透) / 橙(概念) / 灰(行业)
- LLM 二次关联分析（可选）：`llm_news_analysis` 配置开启

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
├── src/                          # 源代码
│   ├── main.py                   # TUI 入口 + 菜单循环
│   ├── config.py                 # 配置读写
│   ├── cache.py                  # 缓存引擎
│   ├── fetcher.py                # 数据获取调度
│   ├── reader.py                 # 持仓 Excel 解析
│   ├── llm_client.py             # LLM 集成（Claude/OpenAI/DeepSeek）
│   ├── models.py                 # 数据模型（Holding dataclass）
│   ├── logger.py                 # 日志模块
│   ├── tui.py                    # 键盘输入封装
│   ├── test_*.py                 # 单元测试（15 个模块）
│   ├── providers/                # API 供应商
│   │   ├── tencent.py            # 腾讯财经（实时价、指数）
│   │   ├── eastmoney.py          # 东方财富（基金净值）
│   │   ├── eastmoney_industry.py # 东方财富（行业分类/概念板块）
│   │   ├── tiantian.py           # 天天基金（业绩排名、持仓）
│   │   ├── sina.py               # 新浪财经（美股指数）
│   │   ├── sina_news.py          # 新浪财经（新闻）
│   │   ├── eastmoney_news.py     # 东方财富（新闻）
│   │   ├── cls_news.py           # 财联社（新闻）
│   │   └── news_aggregator.py    # 多源新闻聚合器
│   └── report/                   # 报告生成
│       ├── excel_writer.py       # Excel 工作簿管理
│       ├── styles.py             # 样式常量
│       ├── summary.py            # 模块 1：汇总
│       ├── market_value.py       # 模块 2：市值核算
│       ├── category.py           # 模块 3：分类汇总
│       ├── penetration.py        # 模块 4：资产穿透 TOP10
│       ├── fund_performance.py   # 模块 5：基金业绩分析
│       ├── news_correlation.py   # 模块 6：财经新闻关联
│       ├── llm_content.py        # 模块 7+8：LLM 内容
│       └── html_writer.py        # HTML 报告引擎
├── data/
│   ├── holdings/                 # 持仓 xlsx 文件
│   ├── cache/                    # API 响应缓存
│   └── config/                   # 配置文件（config.json, llm.json）
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
├── README.md                     # 用户文档
└── requirements.txt
```
