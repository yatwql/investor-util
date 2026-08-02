# plan-7 因子暴露分析（设计归档）

> **原始位置**：`docs-stm/plan/plan-advanced-analysis.md` §4（2026-08-02 归档至 `archive/v0.9.x/factor-exposure/`）
> **状态**：✅ 已完成（2026-08-02，迭代 v0.9.5）——OLS 回归 + 风格归属 + 停更剔除 + C19 契约 + HTML/Excel 渲染
> **关联计划**：plan-7（因子暴露分析 MVP 3 因子）· [`plan-chartjs-report-upgrade.md`](../chartjs-upgrade/plan-chartjs-report-upgrade.md)（Chart.js 升级，方案 B 软依赖）
>
> 原文档 §4 完整内容如下（编号保留 §4 便于与历史引用对齐）。

---

## 4. 因子暴露分析

### 概述

组合在价值/成长/质量/动量/低波上的暴露度。通过因子代理指数（如 300 价值 = 大盘价值因子）估算组合风格偏移。

### 收益

> **粒度说明**：MVP 对**组合整体**做因子回归（一个 R_p 序列 → 一组因子暴露系数），输出"组合风格画像"。不做个券级因子分解（每品种一次回归 + 聚合，工作量 ×N，且基金穿透滞后放大误差）。
>
> **与现有"基金风格分析"（fund_style）的差异化**：fund_style 是**每只基金的截面分类**（六宫格：市值×风格，基于 PE/市值阈值），回答"这只基金长什么样"；plan-7 是**组合整体的时间序列回归**（因子收益回归组合收益得 β），回答"组合收益由什么风格因子驱动"。方法论与粒度均不同，报告 UI 文案需注明差异（"分类" vs "回归估算"），避免用户混淆"风格归属柱状图"与六宫格。

- **理解赚什么钱**：β 回归把组合收益拆解为各因子贡献，回答"收益主要来自价值还是成长风格"——比只看总收益率更能指导风格归因
- **风格漂移检测**：MVP 输出**组合 β vs 沪深300 基准 β 的对照**——"组合比基准更偏成长 / 更偏价值"，这是可操作的漂移信号（结合穿透持仓数据判断"名义风格 vs 实际风格"不一致）
- **调仓辅助**：若目标风格是成长、实际暴露相对基准偏向价值，提示需要调整持仓构成
- **预期管理**：MVP 定位为"风格画像参考"，非精确归因（代理指数不纯 + 穿透滞后 + 窗口敏感，见风险清单）；报告文案明确"估算值，仅供参考"

### 风险

- A 股的因子代理指数有限（只有规模/价值/成长少数几个），多因子模型数据不足
- 因子暴露计算需要回归分析（60 期以上数据），新人理解门槛高
- 基金持仓数据季度更新，因子暴露滞后 1-3 个月

### 工作量估算

> **对齐 plan.md（MVP 3 因子，2.5 天）**。probe 已完成，数据源可行性已验证，剩余为接入/计算/输出三阶段（比原 5 因子设计少动量/低波 2 个因子 + 图表用方案 A 自建柱状渲染，见 §计算方案图表输出——实测 `drawSimpleChart` 仅支持折线，柱状需 +0.25d）。

| 阶段 | 内容 | 天数 |
|------|------|------|
| 因子代理 | 中证风格指数接入（`fetch_index_history` 复用 history_index chain，**不注册 `_A_INDICES`**，见 C1 行）+ C7 注册 + C19 schema 预置 | 0.5 |
| 回归模型 | OLS 回归暴露 + t 值显著性（`numpy.linalg.lstsq`，复用 `_math_utils`） | 1 |
| 报告输出 | 因子暴露柱状图 + 风格归属表 + 数据不足降级（§1.4.5） | 1 |
| **合计** | | **2.5 天** |

### 实现思路

```
R_p = β₁R_value + β₂R_growth + β₃R_momentum + β₄R_quality + β₅R_lowvol + α + ε
                          ↑ 完整 5 因子式；MVP 取 β₁/β₂/β₄ 三项（价值/成长/质量）

不追求高精度（截面回归 > 时间序列回归），用 ≥36 期数据估算。
结果输出为"风格归属柱状图"（价值/成长/质量各一根柱，MVP 3 因子）。
```

**模块分层（对齐 plan-2 模式，C14 依赖）**：

```
analysis/factor_exposure.py   # 纯计算：接收(组合收益序列+因子收益序列) → OLS → 输出
    ↑ 无数据获取、无报告依赖，纯 pandas/numpy
report/orchestrator.py         # 编排：拉取组合收益(独立拉持仓历史 days=60 算 as-if，见§计算方案) + 因子K线
    │                           (fetch_index_history，走 chain) → 对齐 → 调纯计算
    ↓                           → 写 pipeline_data['factor_exposure']（C19）
report/ 渲染                   # 模板 context 传递（C14）→ 柱状图 + 风格归属表
```

- **纯计算层**不依赖 fetcher/report 数据获取，便于单元测试（mock 收益序列直接验证 OLS）。
- **编排层**在 orchestrator 的 `prepare_report_data` 阶段组装数据并注入 pipeline_data（C19 写入阶段）。
- 因子指数代码集合（含名称映射、`FACTOR_STALE_DAYS` 常量）定义在纯计算模块常量区，供编排层引用。

#### MVP 范围定义（复盘第 8 轮收敛）

**MVP 因子集合（固定 3 因子，代码集合为分析模块常量 `FACTOR_INDICES`）**：

| 因子 | 代理指数 | 代码 | 说明 |
|:----|:--------|:-----|:-----|
| 价值 | 300 价值 | sh000919 | 大盘价值代理 |
| 成长 | 500 成长 | sh000925 | 替代停更的 300 成长（sh000920，rf-104）；中盘成长代理，报告中注明代理口径 |
| 质量 | 300 质量 | sh000930 | 全指质量代理 |

- 常量 `FACTOR_INDICES = {"value": "sh000919", "growth": "sh000925", "quality": "sh000930"}` + 名称 dict，**不注册 `_A_INDICES`**（C1）。
- 低波（sh000931）probe 有效但**不进 MVP**（保留为扩展位，见"可行性评级"）。

**MVP 明确不做清单**（防范围蔓延）：
- ❌ 动量/低波因子（第 4/5 因子）——留作后续扩展
- ❌ 因子正交化/岭回归/主成分——共线性仅诊断展示（§计算方案）
- ❌ 窗口敏感性对比（36/120 期）——MVP 只算默认 60 期
- ❌ LLM 注入因子暴露——MVP 不注入 prompt（§与其它计划项交互）
- ❌ 快照持久化 `factor_exposure`——单期画像（plan-6 预留）
- ❌ 个券级因子分解——仅组合级（§粒度说明）

**MVP 保留项**（实现成本低、价值高）：
- ✅ `baseline_betas`（沪深300 对照）——多拉一个 sh000300，风格漂移判断价值高
- ✅ t 值显著性标注——复用 `_math_utils`，成本低
- ✅ `stale_factors` 新鲜度告警——数据健康守护
- ✅ 因子相关矩阵诊断展示——替代 VIF，计算更简单

### 架构约束遵从

| 约束 | 适配方式 |
|:-----|:---------|
| **C1** (代码类型判定中心化) | 因子代理指数代码统一走 `core/code_utils.py::is_index_code()` 判定（probe 已验证 `sh000919` 等原始 6 位前缀命中 `000/399/932` 规则），不在 plan-7 模块内自行实现指数判定。**因子指数不作为 `_A_INDICES` 成员**——`fetch_index_history(code)` 直接接受任意 sh 前缀指数代码不依赖 `_A_INDICES`，因子代码集合定义为分析模块内部常量 + 模块内名称 dict（避免 5 个风格指数污染实时指数行情循环 `fetch_indices()` 的 HTTP 请求量与报告"指数对比"章节噪声） |
| **C6** (Provider Chain 必经) | 指数历史 K 线通过 `fetcher/index.py::fetch_index_history()` 复用 `history_index` chain（`["tencent", "sina"]`），不绕过 Chain 直调 Provider。rf-103 已处理（降级接受）：Sina 备用链路当前 404（环境故障），已接受 Tencent 单链路——Tencent 故障时因子章节落 §1.4.5 数据不足分支；Sina 保留代码级备用（环境恢复自动生效，钳位已对齐 2000） |
| **C7** (报告序号可配置) | 新增 `factor_exposure` 报告模块，必须在 `core/registry.py` 的 `_REPORT_SECTION_DEFAULT` 注册条目（type=`b_series`、data_flag=`factor_exposure_data`），支持用户通过 `config.json` 自定义序号与开关；不硬编码序号 |
| **C14** (渲染期数据不可写入模块级全局变量) | 因子暴露数据（回归系数/风格归属/暴露柱状图数据）通过模板 `render()` 的 context 参数传递，不写入 `_ENV.globals` 或模块级 dict |
| **C19** (pipeline_data Schema 契约) | 新增 `factor_exposure` 键（类型 `dict`：含 `available`/`betas`/`t_stats`/`style_allocation`/`window`），必须在 pipeline_data Schema 定义文档（technical.md 附录 H）预定义类型/版本号/写入模块后再使用，详见下文"技术债与技术预置" |
| **§1.4.5** (数据降级治理) | 区分两分支：① **数据不足**——因子指数历史数据不足 36 期（如 500成长停更），标记 `factor_exposure.available=false`，报告显示"数据不足"占位文本，**不走 DegradationTracker**（系数据量不足，非故障）；② **数据源故障**——`fetch_index_history` 返回空（chain 全失败，如 Tencent 故障），走 DegradationTracker 记录 T2 降级事件（`fetch_index_history` 已内置 `_t.record`），报告显示"数据源暂不可用"，与数据不足文案区分 |
| **C2/C3** (缓存统一+原子写入) | 指数 K 线通过 `cache/` 子包统一读写（`fetch_index_history` 已复用 `history_index` chain 缓存），新增代码不自行建缓存键 |
| **C4** (会话级 API 复用) | 多个因子指数并行拉取 K 线时，同一指数会话内经 `fetch_index_history` 的 `session_cache` 复用（C4 内置），不在分析模块内重复请求；组合收益与因子 K 线虽来自不同历史入口（report/portfolio_history vs fetcher/index），但彼此数据无重叠，不构成重复请求 |
| **C5** (HTTP 客户端统一) | 因子 K 线与组合收益均复用现有 providers 的统一 HTTP 客户端（`make_http_client`），分析模块不自行构造 HTTP 请求 |
| **C8** (日志统一) | 新增 `analysis/factor_exposure.py` 使用 `logging.getLogger("invest")`，回归告警（因子停更/数据不足）走标准日志，不用 `print()` |

### 数据源可行性分析

因子暴露分析是 P2 中唯一需要**新数据源**的功能——中证系列风格指数的历史 K 线。

#### 候选因子代理指数

| 因子 | 中证指数代码 | 说明 |
|:-----|:-----------:|:-----|
| 大盘价值 | 000919（300 价值） | 沪深 300 中价值因子得分最高的股票 |
| 大盘成长 | 000920（300 成长） | 沪深 300 中成长因子得分最高的股票 |
| 小盘价值 | 000922（500 价值） | 中证 500 中价值因子得分最高的股票 |
| 小盘成长 | 000925（500 成长） | 中证 500 中成长因子得分最高的股票 |
| 质量因子 | 000930（中证 300 质量） | 沪深 300 中 ROE/杠杆/盈利稳定性高的股票 |
| 动量因子 | — | ⚠️ A 股无标准动量指数，需考虑用 300/500 等权替代或自定义计算 |
| 低波因子 | — | ⚠️ 中证低波指数（000931）历史数据范围待验证 |

**注意**：动量/低波当前无确定可用的指数代码，MVP 阶段可缩减为"价值/成长/质量"三因子模型，降低数据源风险。

#### API 上限速查

| 数据链路 | API 硬上限 | 因子分析可行性 | 备注 |
|:---------|:----------:|:------------:|:-----|
| 风格指数 K 线（Sina → Tencent 备用） | Sina 声称上限 **3650 天**，Tencent 声称上限 **365 天** | ✅ 足够 ≥36 期回归（实测见下） | ⚠️ probe 实测：Sina 端点当前 404 失效（rf-103）；Tencent 实际上限约 2000 天（rf-102） |
| 风格指数实时行情（Tencent → Sina） | 与现有指数行情共用同一链路 | ✅ 只需将新增代码加入指数行情获取循环 | 现有 `fetch_indices()` 支持扩展 |

> **关键**：数据链路本身是 🟢 生产验证级别（Sina 指数 K 线已在 `fetcher/index.py` 中作为备用链路运行），**问题是这些 CSI 子指数代码是否真的返回有效数据**——现有代码从未调用过 000919/000920 等代码。
>
> **probe 实测更新（2026-08-01，`scripts/probe-csi-factor-indices.py`）**：
> - **主链路 Tencent 有效**：300价值/500价值/500成长/300质量 4/5 个代码均返回 365 条且数据新鲜（截至 2026-07-31）；**300成长（sh000920）已停更**（自 2023-02-17 起无数据，距今 1261 天）→ 需替换代理。
> - **Sina 备用链路当前不可用**：`getKLineData` 端点对所有代码（含股票/既有指数）返回 404/空，`sina_kline.fetch_index_kline` 在当前环境返回空列表（详见 review-findings.md rf-103，可能为端点变更或环境拦截）。→ plan-7 可用性实际仅取决于 Tencent。
> - **Tencent K 线实际上限约 2000 天**，非文档声称的 3650（3650 触发解析崩溃，详见 rf-102）。→ ≥36 期回归的窗口需求仍可满足（2000 交易日 ≈ 8 年）。

#### 风险清单

| 风险 | 原因 | 影响 | 缓解措施 |
|:-----|:------|:----:|:---------|
| **CSI 风格指数不可用** | probe 实测：Tencent 4/5 有效，但 300成长（sh000920）停更；Sina 备用端点当前 404 | 成长因子缺少大盘代理 | Tencent 主链路已验 4/5；300成长用 500成长（sh000925）或低波（sh000931）替代；Sina 404 见 rf-103，实施时先修或直接用 Tencent |
| **部分因子无代理指数** | A 股没有标准动量/低波指数（或代码不确定） | 回归因子数量减少 | MVP 阶段缩减为 3 因子（价值+成长+质量），后续再扩展 |
| **指数名称映射缺失** | 因子代码未在分析模块内定义名称映射 | 报告因子名显示为原始代码 | 分析模块内定义 `{code: 因子名}` 常量表；**不注册到 `_A_INDICES`**（避免污染实时指数行情链路，见 C1 行） |
| **因子回归精度有限** | 代理指数本身不够纯粹（如"300 成长"仍含价值成分） | 因子暴露数值偏小 | 报告中标注"估算值，仅供参考"，不做精确归因 |
| **基金穿透滞后** | 基金季报披露延迟，穿透覆盖的股票持仓滞后 1-3 个月 | 因子暴露滞后 | 报告标注"基于 X 月持仓数据" |
| **回归窗口选择敏感** | 36 期 vs 60 期 vs 120 期得到不同的暴露系数 | 结论不稳定 | 默认 60 期（约 3 个月），提供敏感性说明 |
| **仅单点数据源（数据重要性：高）** | Sina 备用链路 404 失效（rf-103），Tencent 是唯一可用主链路 | Tencent 故障时因子数据全不可用 | ✅ rf-103 已处理（降级接受）：Tencent 单链路；故障 → §1.4.5 数据不足分支，章节降级"暂不可用"（`available=false`），**不阻塞主报告**（b_series 可选章节）。Sina 保留代码级备用，未来环境恢复可自动恢复双链路（无需改代码） |
| **R_p as-if 语义失真（数据重要性：高）** | 独立拉取用"当前份额 × 历史价格"，未考虑历史调仓 | 组合近期调仓后，历史收益序列与真实持有期收益不符 | 报告标注"基于当前持仓不变假设"；MVP 接受该近似（与 `portfolio_history` 章节同一 as-if 语义，口径一致） |
| **手写 OLS 正确性（数据重要性：中）** | 无 statsmodels/scipy 对照，`lstsq` + t 检验/自由度手写 | 系数/自由度计算错误会静默产出 | 单元测试构造**已知答案小数据集**断言 β/t/R²（如 2 因子 10 样本、手工可算）；单因子情形与 `numpy.polyfit` 交叉验证 |
| **因子停更静默污染（数据重要性：高）** | 指数停更（如 rf-104 的 sh000920）后数据不新鲜 | 回归混入陈旧因子，暴露失真 | 运行时新鲜度校验（`FACTOR_STALE_DAYS=120`）剔除停更因子 + `stale_factors` 告警（已写入 §计算方案） |

**风险优先级结论**（按数据重要性排序）：数据可用性/新鲜度类（单点源、停更污染、as-if 失真）是**最高优先**——plan-7 一切结论建立在因子与组合收益序列的完整性上，数据出问题应**优雅降级而非硬算**；其次是被误解风险（估算值当精确值）；最低是方法类（窗口敏感、OLS 正确性，通过测试与文案兜底）。**降级原则：数据不足/故障一律落 §1.4.5 双分支（章节 `available=false` + 告警），绝不输出误导性数字。**

#### 可行性评级

| 阶段 | 可行性 | 说明 |
|:-----|:------:|:-----|
| MVP 3 因子（价值+成长+质量） | ✅ **probe 已验证（2026-08-01）** | Tencent 4/5 主候选有效且新鲜（300价值/500价值/500成长/300质量）；300成长停更由 500成长替代，价值/成长/质量三因子均覆盖 |
| 完整 5 因子（+动量+低波） | ⚠️ **部分可行** | 低波（sh000931）probe 实测有效可作补充；动量无标准 CSI 代码仍需自定义/等权替代 |
| 回归模型+报告输出 | ✅ 技术可行 | OLS 回归无数据源依赖，纯本地计算 |

#### 实施前必须完成的验证步骤

1. **Probe 脚本**（0.5d）：对 `sh000919`、`sh000920`、`sh000922`、`sh000925`、`sh000930` 逐个调用 `sina.fetch_index_kline(code, days=30)`，检查返回数据量
2. **结果判定**：
   - 全部 5 个 ≥20 条有效数据 → ✅ 全量 5 因子可行
   - 至少 3 个 ≥20 条有效数据 → ✅ MVP 3 因子可行（价值+成长+质量），动量/低波标记为实验性
   - 仅 1-2 个可用 → ❌ **不可行**，因子暴露分析在免费数据源下不可实现

**✅ probe 已完成（2026-08-01，`scripts/probe-csi-factor-indices.py --days 365 --stale 120`）——判定：MVP 3 因子可行。**

```
sh000919 300 价值: 365 条，距今 1d    ✅ 可用
sh000920 300 成长: 365 条（至 2023-02-17），距今 1261d  ❌ 停更
sh000922 500 价值: 365 条，距今 1d    ✅ 可用
sh000925 500 成长: 365 条，距今 1d    ✅ 可用
sh000930 300 质量: 365 条，距今 1d    ✅ 可用
sh000931 中证低波: 365 条，距今 1d    ✅ 可用（附加补充候选）
```

- 主链路为 Tencent（`--provider tencent`）；Sina 备用链路当前 404 失效（rf-103）。
- 成长因子由 500成长（sh000925）覆盖（300成长停更）；MVP 用 500成长**单因子**替代（低波 sh000931 作为扩展位不进 MVP，见 §4 MVP 范围定义）。
- 结论：**按 MVP 3 因子实施**（价值+成长+质量，低波作补充），动量标记实验性。

---

### 技术债与技术预置

实施 plan-7 前需明确处理的既有技术债与预置项（probe 阶段发现的增量信息）。

#### 既有技术债（review-findings.md 跟踪）

> 状态更新（2026-08-01）：rf-102/103/104/106 已全部处理（代码/文档落地），见下方"✅ 已处理"标注。

| # | 技术债 | 对 plan-7 的影响 | 处理结果 |
|:--|:--|:--|:--|
| rf-102 | `providers/tencent.py::fetch_index_kline` 文档声称上限 3650 天，实测 `days=3650` 崩溃（`'list' object has no attribute 'get'`），实际上限约 2000 天 | 回归窗口需 ≥36 期（60 交易日 ≈ 3 个月），2000 天 ≈ 8 年充分满足；**但不可传 ≥3650 的窗口** | ✅ **已处理**：`_parse_kline_response` 加非 dict 类型守卫；钳位上限 3650→2000；边缘回归测试 2 例（test_tencent_edge） |
| rf-103 | Sina `getKLineData` 端点当前对所有代码返回 404/空，`sina_kline.fetch_index_kline` 备用链路失效 | chain 的 `history_index` 双链路兜底实际只剩 Tencent 单链路——Tencent 故障时因子章节无数据 | ✅ **已处理**（降级接受）：代码无结构 bug，`sina_kline.fetch_index_kline` 钳位对齐 2000；当前环境 404 为数据源故障，接受 Tencent 单链路，Sina 保留为代码级备用（环境恢复自动生效）。plan-7 实现时 Tencent 故障 → §1.4.5 数据不足分支 |
| rf-104 | CSI `sh000920`（300 成长）自 2023-02-17 停更 | 大盘成长代理缺失 | ✅ **已处理**（文档级）：MVP 用 500成长（sh000925）单因子覆盖成长（低波 sh000931 留扩展位不进 MVP，见 §4 MVP 范围定义）；完整 5 因子降级为 3；probe 脚本保留 sh000920 作探测候选 |
| rf-106 | `portfolio_history.py::get_combined_timeseries` 的 `days` 仅控制基准、不控制持仓历史长度（chain 默认 30） | 曾误以为 `days≥60` 可获 60 期组合收益 | ✅ **已处理**：docstring 澄清 `days` 仅作用于基准；plan-7 用独立拉取持仓历史 days=60 方案（§计算方案） |

#### C7 / C19 预置（实施前必须完成）

1. **C7 注册**：`core/registry.py` 的 `_REPORT_SECTION_DEFAULT` 新增：
   ```python
   {"key": "factor_exposure", "name": "因子暴露分析", "number": 17,
    "type": "b_series", "data_flag": "factor_exposure_data"}
   ```
   （现有 `data_source_status`=17 / `llm_usage`=18 顺延为 18/19。序号仅驱动显示顺序，注册表无硬编码序号引用，插入安全；`get_report_section_keys()` 自动含新键。）
2. **C19 schema**：technical.md 附录 H 新增一行：
   | `factor_exposure` | dict | 是 | 计划中 | prepare_report_data |
   键结构：`{"available": bool, "betas": {factor: float}, "t_stats": {factor: float}, "style_allocation": {factor: float}, "baseline_betas": {factor: float}, "window": int, "sample_count": int, "stale_factors": [str]}`。
   - `baseline_betas`：沪深300 基准在同一回归窗口的因子暴露（对照用，风格漂移判断）；基准数据用 `fetch_index_history("sh000300")` 拉取（复用既有指数链路）。
   - `sample_count`：对齐后实际有效样本数（数据健康信息）；`stale_factors`：本次剔除的停更因子（告警展示）。

#### 计算方案（probe 后新增，原设计未明确）

- **组合收益 R_p 来源（重要修正）**：⚠️ **不能复用 `PortfolioHistoryCalculator.get_combined_timeseries()` 的 `daily_returns`**——该方法的 `days` 参数只传给基准（`_fetch_benchmarks`），持仓历史走 chain 默认 `days=30`（`_get_stock_history`/`_get_fund_history` 不带 days），组合收益序列固定 30 期，不满足 plan-7 的 ≥36 期需求。**改为**：plan-7 编排层独立拉取每只持仓历史（`fetch_with_incremental_fallback("history_stock"|"history_fund_otc", code, days=60)`，C4 会话缓存会复用报告已拉的 30 天、增量补至 60 天），按 as-if 语义（当前份额 × 历史价格）计算组合日收益序列。回归窗口 60 期 ≈ 3 个月。
- **回归序列对齐（关键，数据完整性）**：OLS 要求因变量 R_p 与自变量（各因子收益）**严格按交易日对齐**。组合某品种缺某天数据时，`daily_returns` 会有缺口。实现用 pandas 构造 DataFrame 后 `merge`（on=`date`，inner join）对齐——因子收益直接由各 CSI 指数 K 线的 `close` 计算 pct_change 得到，天然带日期索引；对齐后若有效交易日 < 36，落入 §1.4.5"数据不足"分支。**复用 plan-2 相同的对齐思路（`analysis/correlation.py` 的时间序列对齐模式），不另造机制。**
- **R_p 序列 NaN 处理**：持仓品种停牌/缺数据时 `daily_returns` 含 NaN。对齐前用 `ffill()`（前向填充）补缺——指数不停牌、因子序列完整，组合侧单日缺口用前值填充可保留样本；若某品种长期缺失（如新调入），其贡献缺口集中在序列首尾，ffill 会失真 → 对 R_p 用 `dropna()` 剔除无效日后再与因子 merge，并记录实际有效样本数。**有效样本 < 36 才判数据不足，不接受"35 期硬算"**。
- **动态窗口（数据量自适应）**：对齐后有效窗口受限于 `min(组合历史长度, 因子历史长度)`。场内 ETF/股票主导时组合可达数百交易日 → 用默认 60 期；场外基金主导时（~200 条 ≈ 10 个月）仍够 60 期，但若想扩展 120 期则不足 → **回归窗口 = min(60, 有效样本 - 自由度余量)**，优先满足 ≥36 下限，不足则数据不足分支。
- **OLS 实现**：`statsmodels` **未安装**，且项目惯例是 `_math_utils.py` 纯 math 无 scipy 依赖（已有 `_t_critical_95`/`_beta_se` 等 t 分布辅助）。建议用 `numpy.linalg.lstsq` 手写 OLS + t 检验，复用 `_math_utils.py` 的 t 分布函数，**不新增 statsmodels 依赖**。回归需处理因子共线性（500价值/500成长同源指数高度相关）：**MVP 不做正交化/岭回归等复杂处置**（避免方法复杂度与解释成本），仅输出**因子相关矩阵**作为**诊断展示**（对齐 MVP 保留项"相关矩阵替代 VIF"），并在风格归属图中对高相关因子的并列 β 给出文案提示（"价值与成长因子高度相关，系数解释需谨慎"），避免用户误解高度相关的 β 值。未来若出现 β 符号异常（正负相消），再评估因子降维（保留独立因子或主成分），不作为 MVP 范围。
- **图表输出（依赖修正，2026-08-01）**：⚠️ 实测现 `drawSimpleChart`（Canvas 2D）**仅支持折线**（`report_template.html` 无柱状分支），**不支持柱状/饼图**——原"可回退 Canvas 柱状图"前提不成立，需要**自建柱状渲染**。方案分级：
  - **方案 A（无依赖，MVP）**：新增轻量 Canvas 柱状绘制函数（或复用 HTML/CSS 水平条形 div，成本 ~0.25d），按因子一根柱输出风格归属图。**不阻塞在 plan-1**。
  - **方案 B（依赖 plan-1，推荐升级）**：plan-1 的 Chart.js 迁移会新建柱状图能力（穿透 TOP10 Bar / 行业分布 Horizontal Bar，见 `../chartjs-upgrade/plan-chartjs-report-upgrade.md` §1.1），plan-7 直接复用 Chart.js Bar + tooltip/交互，升级为交互式风格归属图。
  - 结论：**plan-7 对 plan-1 是"软依赖"**——MVP 可用方案 A 独立实施；若 plan-7 在 plan-1 之后排期，则用方案 B 免自建柱状。工作量按方案 A 估算（2.5d 含 +0.25d 柱状渲染）。

#### 与其它计划项的交互（复盘第 7 轮补充）

| 计划项 | 交互点 | 设计决策 |
|:-----|:------|:--------|
| **plan-2**（相关性矩阵） | 同样需要全品种历史 K 线；`analysis/correlation.py` 已有时间序列对齐模式 | **复用 plan-2 对齐思路**（§计算方案回归序列对齐），不另造机制；历史拉取经 C4 会话缓存共享，不重复请求 |
| **plan-3**（回撤+净值） | 净值曲线基于 `get_combined_timeseries`；plan-7 独立拉取组合历史 | **口径一致约束**：plan-7 自算的 as-if 组合收益**必须**与 `portfolio_history.py` 口径一致（当前份额×历史价、LOCF、同日剔除），MVP 用测试断言两章口径一致（同输入→同收益序列）；若未来 plan-2 亦需组合收益导致第三处重复 → 届时提取 as-if 计算为共享纯函数（记录为技术债，MVP 不强制重构 portfolio_history） |
| **plan-1**（交互式 HTML） | 图表框架迁移；plan-1 新建 Chart.js 柱状图能力（穿透 TOP10 Bar / 行业分布 Horizontal Bar） | **软依赖**：plan-7 MVP 用方案 A（自建轻量柱状渲染）**不阻塞在 plan-1**；若 plan-7 在 plan-1 后排期，用方案 B 直接复用 Chart.js Bar（见 §计算方案图表输出，依赖分级已修正——现 `drawSimpleChart` 仅支持折线，柱状需自建） |
| **plan-6**（多快照趋势） | 快照若含 `factor_exposure`，风格画像随时间变化可成趋势 | MVP 快照**不含** factor_exposure（plan-7 是单期画像）；预留：未来快照加键后 plan-6 自然获得风格漂移趋势，本期不实现 |
| **LLM 章节** | 因子暴露可作智囊团/政经复盘背景数据 | MVP **不注入** LLM prompt（避免 LLM 对估算值过度解读，LLM 输出与回归数字相互污染）；预留注入键 |
| **C7 注册表** | 序号 17 插入 | 已写入 §4 C7 预置（number=17，data_source_status=17 顺延） |

#### 运行时数据健康校验（probe 新鲜度维度沉淀为生产校验）

probe 阶段用 `--stale 120` 判定停更，该维度需沉淀为生产代码的**每次运行校验**，而非仅在决策闸门用：

1. **新鲜度校验**：拉取各因子指数 K 线后，检查最后一根 bar 日期距今 > `FACTOR_STALE_DAYS`（默认 120）的指数，从因子集合**剔除**并记录告警（"因子 X 已停更，本次回归剔除"），剩余因子 < 2 时落 §1.4.5 数据不足分支。
2. **条数校验**：对齐后有效样本 < 36 → 数据不足分支（见"动态窗口"）。
3. **与 probe 的关系**：probe 是一次性决策闸门；此处的健康校验是每次运行的持续守护，防止未来某因子指数停更后静默污染回归。`FACTOR_STALE_DAYS` 常量定义在分析模块内。

#### 测试策略（复盘第 9 轮补充）

> 目标：纯计算层 OLS 正确性（最高优先）+ 编排层 schema 契约 + 降级路径。全部 mock 数据源，禁真实调用。

**文件与 marker**：`src/test/unit/analysis/test_factor_exposure.py`（`@pytest.mark.unit_analysis`）+ `src/test/scenario/test_pipeline_factor_exposure.py`（`@pytest.mark.scenario_basic`）。两个 marker 均已在 `conftest.py` 注册（`unit_analysis`、`scenario_basic`），无需新增。

| 用例 | 类型 | marker | 断言 |
|:-----|:----:|:------:|:-----|
| 已知答案小数据集 OLS（2 因子 10 样本，手工可算） | 单元 | unit_analysis | β/t/R² 与手工计算一致（手写 lstsq 正确性，rf-102 级防回归） |
| 单因子 vs `numpy.polyfit` 交叉验证 | 单元 | unit_analysis | 斜率一致（独立实现互证） |
| 高共线性因子输入 | 单元 | unit_analysis | 系数仍输出 + 相关矩阵/提示字段存在（诊断展示） |
| 有效样本 < 36 | 单元 | unit_analysis | 落数据不足分支（`available=false`），不硬算 |
| NaN 缺失日 dropna 后样本计数正确 | 单元 | unit_analysis | `sample_count` = 剔除后有效样本 |
| 新鲜度校验剔除停更因子 | 单元 | unit_analysis | `stale_factors` 列出剔除项；剩余 < 2 → 数据不足 |
| as-if 组合收益与 `portfolio_history` 口径一致（同输入→同序列） | 单元 | unit_analysis | 两实现输出序列一致（防 plan-3/7 数值矛盾） |
| 编排层注入 pipeline_data 契约（C19 键完整） | 场景 | scenario_basic | `factor_exposure` 键含 `{available, betas, t_stats, style_allocation, baseline_betas, window, sample_count, stale_factors}` |
| 因子数据全失败 → 章节降级不阻塞主报告 | 场景 | scenario_basic | 报告其他章节正常，该章节 `available=false` |

**门禁映射**：纯计算用例进 P0 dev-verify（`unit_analysis` 已在 dev-verify 集合内）；场景用例进 P1 verify / P2 regression。**缺陷自测约定**：任一 OLS/降级缺陷修复后，必须补充对应回归用例（本表即回归用例清单）。

**测试隔离**：编排层场景测试用 fixture 构造最小持仓（2-3 品种）+ mock 因子/持仓历史拉取（`unittest.mock.patch`），LLM 路径不触发（本章节无 LLM 调用）；若触发报告管线，`output_dir` 重定向 `tmp_path`（按 CLAUDE.md 约定）。
