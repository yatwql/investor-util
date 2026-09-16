# 景气度框架诊断（投资分析方法引入）— 设计文档

> 文档类型：中间设计文件（**已实现，2026-09-16 归档**）
> 归档位置：`docs-stm/archive/v0.11.x/prosperity-framework/`
> 计划项：`plan-46`（**已实施**：分析模块 / 实验开关 / 数据契约 / 双端渲染 / 配置 / 测试 / 文档全部落地）
> 实验性功能开关：`prosperity_framework`（默认关；保持方法原意，未转正——转正判据见 `plan-49`）
> 后续项：`plan-47`（基金持仓 ROE 加权）/ `plan-48`（场外流动性补齐）见 `../../managements/plan.md`
> 实施记录：`../../managements/changelog.md`「plan-46 景气度框架诊断」系列条目（含 5 处缺陷修复与两轮口径修订）、
> 计划完成态摘要见 [`../archived_plan.0.11.x.md`](../archived_plan.0.11.x.md)
> 上游借鉴：**zhengxi-views（郑希观点库，MIT License）** — <https://github.com/lyra81604/zhengxi-views>
> 归属说明：上游为「AI Skill」形态（原文语料 + 方法框架 + 基金数据 + 六维评分卡）。本项目**只借鉴其
> 可计算的方法骨架与评分口径**（`references/method.md` / `references/scorecard.md`），**不引入其语料、
> 不引入其基金快照、不复制其文本**；方法框架本身蒸馏自公开采访（中国证券报 2026-06 专访、
> 上海证券报 2025-05 专访），本项目按「可计算、可降级、可复核」原则重写为本仓的
> `analysis/` 纯计算模块 + 数据契约 + 渲染块。
> 关联：`analysis/liquidity.py`（流动性）、`analysis/financial_indicator.py`（ROE/质量档）、
> `report/penetration.py::classify_sector`（板块）、`analysis/snapshot_diff.py`（换手代理）、
> `technical.md` §8 架构设计约束（25 条，逐条自检见 §6）

## 1. 背景与目标

上游仓库把一位主动权益基金经理的公开方法蒸馏成一套**可操作流程 + 六维评分卡**：

> 全球视野找技术/需求变化 → 顺产业链找「正在涨价（通胀）」的环节（偏好供给端创造需求的科技通胀）
> → 落到中国有比较优势的那一环 → 在该环节选「流动性够 + ROE 低位有修复弹性（供求压制型 / 预先研发型）+
> 偏中小市值」的标的 → 多维跟踪、逐步拟合、周期拼接 → 组合分散 + 行业比例调整 + 预先想好退出 →
> 一切判断以「客观」为最高准绳，底层逻辑变坏就卖。

**目标**：把它转成对本仓**持仓组合**的可计算诊断——回答「我的组合有多符合这套景气度框架、哪几维偏弱、
哪些结论是数据支撑的、哪些需要人工核实」，并以**实验性功能开关**（默认关）交付。

**非目标**（本期不做）：
- 不引入上游语料库 / 基金经理观点检索 / 口吻模仿（属上游 skill 形态，非本仓职责）；
- 不抓取上游基金快照，也不做「全市场 2.7 万只基金」检索与对比；
- 不新增 LLM 调用（不把结论注入提示词；如需，另立计划项）；
- 不引入新的外部数据源；不改变既有章节的输出（关闭开关时报告逐字节不变）。

## 2. 现状事实（实施依据，均经代码核实）

| 需要的输入 | 本仓既有能力 | 位置 |
|:--|:--|:--|
| 持仓明细与市值 | `DetailRow`（code/name/shares/market_value/cost/profit…） | `report/market_value.py` |
| 板块归类 | `classify_sector(name, code)`（关键词表 `data/knowledge/sector_keywords.json`） | `report/penetration.py` |
| 穿透后重仓（含基金底层） | `compute_penetration_top10()` → `top10[...]`（穿透市值/占比/板块） | `report/penetration.py` |
| 流动性（变现天数/日均成交额） | `check_liquidity(holdings_details, total_mv, redemption_limits)`（近 20 日 K 线估算） | `analysis/liquidity.py` |
| ROE / 质量档 / 估值 | `financial_indicator_data` 契约（`rows[].roe`、`quality_grade`、`pe/pb`） | `analysis/financial_indicator.py` |
| 集中度 | 持仓市值分布（TOP10 占比） | `analysis/metrics.py`（HHI 等） |
| 换手代理（周期拼接） | 历史快照序列（`data/history/snapshots/*.json`）与 `snapshot_diff` | `analysis/snapshot_diff.py`、`report/history_snapshot.py` |
| 业绩与回撤印证 | `history_data`（as-if 组合走势）与 `analysis/drawdown_events.py` | `analysis/portfolio_evolution.py` |
| 实验开关 | `FeatureSwitchDef` + `GROUP_EXPERIMENTAL`（默认关，`affects_report=True`） | `config/features.py` |
| 契约台账 | `_PIPELINE_DATA_KNOWN_KEYS` + `_PIPELINE_DATA_TYPE_MAP` + 附录 H | `report/pipeline_data_builder.py`、`technical.md` |
| 章内嵌块先例 | 「历史决策复盘」块（`decision_reflection` 开关，行动建议章内嵌） | `report/action_sheet.py`、`partials/action_section.html` |

**口径修订记录（真实持仓复核，第二轮）**：① 新增**基金类型兜底标签**（`_fund_type_fallback_label`，只用 `core/code_utils` 判定：ETF/指数优先 > QDII > 固收），把 QDII/联接/债基/宽基 ETF 等"板块识别失败"的持仓（实测 8 只 / 51.28% 权重）接入诊断；② 去重范围收窄为**仅直接持有的证券**——原实现把出现在穿透 `sources` 里的基金整只跳过，导致覆盖率仅 48%；现按两视角叠加（穿透底层 + 持仓自身类型/板块）。

**口径修订记录（真实持仓复核，第一轮）**：原实现「有穿透数据就只看穿透（覆盖仅 34.6% 市值）」，且 `benchmarks` 结构假设错误、同一标的可同时计入景气与防御。已修订为：**并集覆盖 + 归一**（把未被穿透覆盖的持仓按板块纳入）、基准兼容 `list[dict]`、景气/防御**互斥归类**；覆盖率在证据中披露（如「覆盖 48.47% 市值」），读者可知评分的分母。

**数据缺口（须诚实降级，不得臆造）**：本仓**不取个股成交额以外的基本面**（`financial_indicator` 默认关）、
不取个股 ROE（除上述契约）、不取个股市值/自由流通市值。故第 2 维（ROE 弹性）与第 4 维（流动性）
在数据缺失时标记 `unverified` 并按「不计分 + 明确提示」处理（**不猜、不补零冒充真实得分**）。

## 3. 方案：六维评分卡（满分 100，客观化口径）

| 维度 | 权重 | 计算口径（全部由既有数据推导） | 数据缺失时 |
|:--|:--:|:--|:--|
| ① 景气方向 / 通胀属性 | 25 | **两视角叠加 + 归一 + 类型兜底**：视角一 = 穿透底层各标的（按 `ratio_pct`）；视角二 = 每个直接持仓按自身权重（板块取 `classify_sector`，识别失败时用**基金类型兜底标签**：固收→防御侧、境外/宽基/主动权益→中性且**只按标签参与判定**）；直接持有的证券在视角二跳过（避免重复）；两视角叠加后归一。命中 `boom_keywords` 按 60% 满分档折算、`defensive_keywords` 反向扣减（**防御优先、互斥不重复计**） | 无需外部数据（名称/板块/类型即可算） |
| ② ROE 低位弹性 | 20 | 有 `financial_indicator_data` 时：按持仓 A 股 ROE 分布（低 ROE 占比越高分越高，对应「低 ROE→高 ROE 修复弹性」），叠加质量档改善（`trend`）加分；已是高 ROE 白马的占比作扣减 | **`unverified`**：不给分、给「数据缺失」占位提示（建议开启 `financial_indicator`） |
| ③ 全球视野 / 中国比较优势 | 15 | 命中 `global_edge_keywords` 的权重（口径同维度①两视角叠加归一，40% 满分档）+ QDII/港股等**境外资产占比**加分（全球暴露，按代码判定恒可得） | 无需外部数据 |
| ④ 流动性 | 10 | 复用 `check_liquidity`：场内品种变现天数分档（<1 日满分，逐档递减）；场外品种按赎回上限配置判定 | 场外/未知 → `unverified` 子项（不参与该维扣分，记入未验证清单） |
| ⑤ 集中度与周期拼接 | 15 | TOP10 集中度（配置目标 `concentration_target_pct`，默认 50%）落在合理区间得分 + **换手代理**（快照持仓集合变动率，取自历史快照；无第二快照 → `unverified`）——本框架**高换手加分**（周期拼接是方法的一部分） | 无快照 → 换手子项 `unverified`（集中度仍计分） |
| ⑥ 业绩与回撤印证 | 15 | 有 `history_data` 时：组合区间累计收益与最大回撤相对基准（`comparison_indices`）的比较分档——「靠景气方向赚到钱」优先于「回撤小」 | 无历史数据 → `unverified` |

**评级**（对齐上游 scorecard 口径）：`高度契合 ≥80` / `较契合 60–79` / `部分契合 40–59` / `不契合 <40`。
**总分口径**：只对**已计分**维度求和，并给出 `scored_weight`（已计分权重合计）与 `total_score_on_scored`
（若把未验证维度视为满分的上界分），界面上**同时显示**「已计分维度得分 / 满分」与「未验证维度」清单，
避免用缺失数据冒充高分或低分。

**红线（写入渲染文案与文档）**：
1. 结论分三类标注——【数据支撑】【按框架推演】【需核实】；未验证维度**不得**写成已判定的结论。
2. 评分衡量的是「**组合与该框架的契合度**」，不是「组合优劣」，更非投资建议——文案固定带该免责句。
3. 不复制上游文本；方法出处与许可在文档与报告中指引（上游仓库链接 + MIT）。

## 4. 命名与契约（先定语义名再设计）

| 层 | 语义名 | 说明 |
|:--|:--|:--|
| 功能开关 | `prosperity_framework` | `GROUP_EXPERIMENTAL`，默认关，`affects_report=True`（实验组 ∧ affects_report → 进产物自述与页脚清单） |
| 分析模块 | `analysis/prosperity_framework.py` | 纯计算：`build_prosperity_framework_data(...) -> dict`；无网络副作用（流动性 K 线经既有缓存设施，可注入以便测试） |
| 数据契约 | `prosperity_framework_data` | pipeline_data 键（数据契约台账 + 附录 H + 类型映射 `dict`） |
| HTML 块 | `partials/action_section.html` 内嵌块 | 标题「景气度框架诊断」，随开关与契约可用性显隐 |
| Excel 块 | `report/action_sheet.py::_write_prosperity_block` | 行动建议页签内追加块（先例：历史决策复盘块） |
| 配置键 | `prosperity_framework.{boom_keywords,global_edge_keywords,defensive_keywords,concentration_target_pct}` | 顶层配置键（手动编辑；进 `_config_defaults` 与模板） |

**契约结构**（`prosperity_framework_data`）：
```json
{
  "available": true,
  "reason": "",
  "total_score": 68,
  "scored_weight": 85,
  "max_score": 100,
  "total_score_on_scored": 80,
  "rating": "prosperity_fit_partial",
  "rating_label": "较契合",
  "dimensions": [
    {"key": "boom_cycle", "name": "景气方向/通胀属性", "score": 19, "max_score": 25,
     "status": "scored", "evidence": ["景气板块市值占比 63.2%（光通信/半导体）"], "unverified": []}
  ],
  "holdings_view": [
    {"code": "600519", "name": "贵州茅台", "weight_pct": 12.5, "sector": "消费",
     "roe": 0.31, "notes": ["板块命中 defensive_keywords"]}
  ],
  "concentration_pct": 42.0,
  "turnover_proxy_pct": 18.5,
  "unverified": ["② ROE 低位弹性（未开启 financial_indicator）", "④ 流动性：场外品种 2 只"],
  "notes": ["评分衡量组合与景气度框架的契合度，非优劣判断，非投资建议"]
}
```
`available=false` 时仅 `available/reason/notes`（沿用既有契约惯例）。

## 5. 数据流与接线（注册表驱动，不新增章节）

1. `_report_generation`（full/both）与 `excel_generator`（basic 兜底，先例同 `action_data`）就地构建契约 → 写入 `pipeline_data`；
2. `action_sheet`/`action_section.html` 在**行动建议章内**渲染块（开关关 → 不渲染，零字节变化）；
3. 契约键进数据契约台账（`_PIPELINE_DATA_KNOWN_KEYS` + `_PIPELINE_DATA_TYPE_MAP`）+ 附录 H + 语义命名表。

## 6. 架构约束对照（逐条自检）

| 架构约束（语义描述） | 结论 |
|:--|:--|
| 代码类型判定中心化 | 板块/品种类型一律经 `code_utils` / `classify_sector`，不自建判定 |
| 报告序号与显示名不可硬编码 | 不新增注册表条目（章内嵌块），页签名与序号不变 |
| 契约先定义后使用 | 先定 `prosperity_framework_data` 结构与类型映射，再实现消费方 |
| 渲染期数据不得写模块级全局 | 契约经 pipeline_data / 渲染参数传递 |
| 缓存统一管理 | 流动性 K 线复用既有缓存设施（`cache.py`），不自建缓存目录 |
| 契约台账与附录同步 | 键与类型进台账与附录 H，测试锁定 |
| 数据降级治理（§1.4.5） | 每维独立降级 + `unverified` 清单，缺数据不臆造、不冒充得分 |
| 语义命名纪律 | 模块/函数/配置键/契约键一律语义名（`prosperity_framework*`），无任务代号；进语义表 |

## 7. 测试与文档同步（清单）

**测试**：`unit/analysis/test_prosperity_framework.py`（六维计分逐条、命中/未命中关键词、评级边界、缺失数据降级）+ `_edge.py`（空持仓/全防御板块/全未验证/极端集中度）+ 接线（开关关 → HTML/Excel 无块；开 → 有块且与契约一致）+ 场景（管线冒烟含 action 章）+ 标记合规（`unit_analysis` / `edge` / `scenario_basic`）。

**文档**：`technical.md`（语义表 + §4.x 叙述 + 契约 + 附录 H）、`requirements.md`（R-* 条目）、`testplan.md`（§4 行 + 标记）、`how-to-config.md`（开关表 + 配置键）、`reports-instruction.md`（行动建议章块说明）、`README.md`、`folders.md`（树 + 统计）、`changelog.md`、`review-findings.md`、`plan.md`。

## 8. 验收标准

1. 开关关闭：报告与未引入时**逐字节一致**（零行为变化，`--mode verify` 全绿）；
2. 开关开启：行动建议章（HTML+Excel）出现「景气度框架诊断」块，含总分/评级 + 六维明细 + 未验证清单 + 免责句；
3. 每个维度的得分都能在 `evidence` 里追溯到具体输入数据；
4. 数据缺失维度出现在 `unverified` 且**不参与**计分（不臆造）；
5. 契约进数据契约台账与附录 H，语义表登记新开关与新 slug；
6. 四个 `--ci` + `--mode verify,regression` + `dev-verify` + ruff + 版本一致性全绿。
