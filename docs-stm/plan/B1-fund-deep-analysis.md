# B 迭代计划：基金持仓专属深度分析

创建日期：2026-07-04
最后更新：2026-07-04（v2 — 风险审查修复：缓存指纹缺陷/首次运行体验/编号/性能预估/TUI 设计）
状态：待评审
优先级：P0（中难度 / 高价值）

---

## 1. 问题陈述

### 1.1 当前状态

当前系统已具备以下基金分析能力：

| 功能 | 状态 | 输出位置 |
|:-----|:------|:---------|
| 基金业绩排名（近 3/6/12 月 + 同类排名） | ✅ 已有 | 报告页签 5「基金业绩分析」 |
| 基金底层持仓穿透（前 10 大重仓股） | ✅ 已有 | 报告页签 4「资产穿透 TOP10」 |
| 基金业绩比较基准（三层回退） | ✅ 已有 | 报告页签 5 |
| 5 级业绩评价（优秀→较差） | ✅ 已有 | 报告页签 5 |
| 基金分类（QDII/ETF/联接/债券/主动权益） | ✅ 已有 | 穿透模块 + 业绩分析 |
| 智能预警（行业资金联动 + 新闻情绪） | ✅ 已有 | 报告页签 7 |
| LLM 深度分析（行业集中度/国别暴露） | ✅ 已有 | 报告页签 11（LLM） |

### 1.2 用户痛点

| 痛点 | 场景 | 影响 |
|:-----|:------|:------|
| **基金经理变更** | 持有主动基金突发基金经理离职，未能及时察觉 | 持仓策略被动变化，业绩可能滑坡 |
| **持仓重复买入** | 多只基金都重仓同一股票，实际风险敞口远超预期 | 看似分散实则集中，抗风险能力差 |
| **基金风格漂移** | 大盘价值基金转向中小盘成长，与配置预期不符 | 组合风险暴露偏离原配置意图 |
| **集中度突变** | 基金前十大持仓占比骤升，隐含赌注式操作 | 基金持仓过于集中，波动风险加剧 |

### 1.3 目标用户画像

| 用户类型 | 关心的 B 功能 |
|:---------|:--------------|
| 主动基金持有者（持仓含易方达/中欧/广发等） | 基金经理变更 + 风格漂移 |
| ETF/指数投资者 | 持仓重合度矩阵 |
| 多账户、多基金组合持有者 | 持仓重合度 + 集中度 |
| 长期配置型投资者 | 集中度趋势 + 风格一致性 |

---

## 2. 需求分析

### 2.1 功能需求

#### F1：基金经理变更监控

| 需求 | 描述 |
|:-----|:------|
| **数据获取** | 从天天基金 `fund.eastmoney.com/{code}.html` 解析基金经理姓名、任职起始日、历任基金经理列表 |
| **变更检测** | 缓存上次基金经理快照（独立键，不依赖持仓指纹），检测近 1 月/3 月/6 月内是否发生变更 |
| **报告输出** | 基金维度展示：当前基金经理、任职起始日、任职天数、近 N 月是否变更 |
| **异常标注** | 30 天内变更标记为 🔴 紧急、90 天内变更标记为 ⚠️ 关注 |
| **缓存策略** | `fund_manager_{code}.json` 日级 TTL，`fund_manager_snapshot` 独立快照键（永久，不受持仓指纹影响）|
| **首次运行** | 无历史快照时标注"首检"，顶部提示"基金经理变更自下次报告起跟踪" |

#### F2：持仓重合度矩阵

| 需求 | 描述 |
|:-----|:------|
| **重叠标的识别** | 对任意两只基金，统计共同持有的底层股票/债券数量 |
| **重叠度指标** | 输出：(1) 共同标的数 (2) Jaccard 相似系数 (3) 共同标的穿透市值占比 |
| **矩阵可视化** | 基金 × 基金对称矩阵，热力图着色（高重叠红色预警） |
| **报告输出** | Excel 页签：「13. 持仓重合度矩阵」+ HTML 章节，含最高重叠 TOP 对标注 |
| **缓存策略** | `fund_overlap_{fingerprint}.json`，持仓指纹驱动失效（此处指纹策略正确，因为重叠度随持仓变化）|

#### F3：基金风格漂移检测

| 需求 | 描述 |
|:-----|:------|
| **风格维度** | 大盘/中盘/小盘 × 成长/价值/混合（六宫格风格箱） |
| **判定依据** | 按底层持仓的市值规模（流通市值）和估值指标（PE/PB）加权判断 |
| **漂移计算** | 与历史风格快照对比，输出漂移评分 |
| **报告输出** | 各基金风格标签 + 漂移评分 + 风格变动历史 |
| **降级方案** | 外部市值数据不可用时，使用代码段近似归类（标注"估算风格"）|
| **首次运行** | 无历史快照时标注"基准确立中" |

#### F4：持仓集中度监控

| 需求 | 描述 |
|:-----|:------|
| **集中度指标** | 前 3 大、前 5 大、前 10 大持仓占基金净值比例 |
| **趋势对比** | 与历史缓存中的集中度数据对比，展示环比变化 |
| **突变预警** | 前 10 占比环比提升 > 10% → ⚠️ 关注；> 20% → 🔴 紧急 |
| **报告输出** | 基金维度：当前集中度 + 趋势方向 + 预警级别 |
| **数据来源** | 复用 `fetch_fund_holdings` + 新增 `fund_concentration_snapshot` 独立快照键 |
| **首次运行** | 无历史快照时标注"基线已记录"，不输出趋势 |

### 2.2 非功能需求

| 维度 | 要求 |
|:-----|:------|
| **向后兼容** | 所有新增页签/章节只在新版报告出现，不修改现有页签布局 |
| **降级友好** | API 获取失败时显示「—」占位，不阻塞报告生成 |
| **缓存安全** | 新增缓存前缀注册到 registry.py，支持 TTL 和分组管理；**历史快照类使用独立缓存键（不受持仓指纹影响）** |
| **测试覆盖** | 每项新增 API 必须有对应的 mock 单元测试；HTML 模板渲染测试随新章节扩展 |
| **性能** | 基金经理/重合度/集中度数据在生成报告时按需获取；单基金经理请求 1 次 HTTP（与穿透页面合并）；首次运行时 HTTP 请求数 = 基金数，后续运行 = 0（缓存命中）|
| **数据源依赖** | 基金经理数据仅依赖天天基金页面（已有 HTTP 客户端），不新增外部依赖 |

### 2.3 约束条件

- 不引入新的外部 API 数据源（仅依赖已有的天天基金/东方财富 API）
- 保持 HTML 模板 autoescape 安全策略
- 所有新增页签（13-16）在「菜单 B/L（含新闻或全系列）」中包含，菜单 E/H 不包含
- 风格漂移检测的估值数据尽量复用现有 API（东方财富行业分类 API 中的市值数据）
- **Phase B1 先行完成数据源可行性预研**，确认风格判定所需市值数据可用性

---

## 3. 详细技术设计

### 3.1 方案总览：五 Phase + 预研

```
+---------------------------------------------------------------------+
|  B 基金持仓深度分析                                                   |
+---------------------------------------------------------------------+
|  Phase B1: 基金元数据增强 + 数据源预研             基础能力建设        |
|  Phase B2: 基金经理变更监控                       F1 实现            |
|  Phase B3: 持仓重合度矩阵                         F2 实现            |
|  Phase B4: 持仓集中度监控                         F4 实现            |
|  Phase B5: 基金风格漂移检测                       F3 实现            |
+---------------------------------------------------------------------+
```

依赖关系：Phase B1 → (B2, B3, B4, B5)，B2~B5 之间互相独立可并行。

**LLM 增强（跨 Phase 可选）**：基金经理变更、集中度突变、风格漂移数据可输入给智囊团复盘（LLM `expert_review`），让 LLM 在给出调仓建议时引用这些信息。此增强不需要新增 LLM 模块，仅在 Prompt 中追加数据即可，建议 B2/B4 完成后各做一次 Prompt 更新。

### 3.2 Phase B1：基金元数据增强

#### 3.2.1 新增 API — 基金经理抓取

创建 `src/python/fetcher/fund_manager.py`：

```python
"""基金经理数据获取模块。

数据来源：fund.eastmoney.com/{code}.html（HTML 解析）
         优先与穿透模块合并请求（同一个页面可同时提取经理+持仓）
缓存前缀：fund_manager_
TTL：CACHE_DAILY（86400s）
"""

_CACHE_PREFIX = "fund_manager_"

def parse_manager_from_html(html: str) -> dict | None:
    """从基金主页 HTML 纯解析基金经理信息。
    
    该函数与穿透模块 parse_holdings 共用同一 HTML 源，
    穿透模块在请求 fund.eastmoney.com/{code}.html 后可
    顺带调用此函数，避免额外 HTTP 请求。
    """
    
def fetch_fund_manager(code: str) -> dict[str, Any] | None:
    """获取基金经理信息（含缓存+回退）。

    返回：
      - manager_name: str      当前基金经理姓名
      - start_date: str        任职起始日（YYYY-MM-DD）
      - tenure_days: int       任职天数
      - history: list[dict]    历任基金经理 [{name, start_date, end_date, tenure_days}]

    解析失败返回 None。
    
    HTTP 请求数说明：
      - 缓存命中：0 次
      - 缓存未命中：1 次（与穿透模块共享同一 HTTP 响应时，实际不增加网络请求）
    """
```

**HTML 解析策略**：

目标页面 `https://fund.eastmoney.com/{code}.html` 中的基金经理信息有两种存在形式：

1. **基金概要表格**（优先）：`<div class="infoOfFund">` 中的基金经理行
2. **基金档案页**（回退）：`https://fundf10.eastmoney.com/jjjl_{code}.html` 基金经理明细表

**与穿透页面合并策略（性能优化）**：
```
穿透模块 fetch_fund_holdings(code) 解析 fund.eastmoney.com/{code}.html
经理模块 parse_manager_from_html(html) 解析同一 HTML → 0 额外 HTTP 请求

实现方式：
  1. fund_manager.py 暴露纯解析函数 parse_manager_from_html(html)
  2. penetration.py 中调用 fetch_fund_holdings 后，顺带调用 parse_manager_from_html 缓存结果
  3. fund_manager_analysis.py 优先读缓存，miss 时才单独请求
```

**性能估算**：
```
10 只基金时：
  - 穿透模块已请求 10 次主页（获取持仓）→ 经理数据顺带提取 = 0 额外请求
  - 如果穿透缓存已命中（非首次运行）→ 经理缓存通常也命中 = 0 额外请求
  - 首次运行最坏情况：10 次 HTTP = ~2-5s（与穿透请求并行，不增加总耗时）
```

#### 3.2.2 数据源可行性预研（新增）

> **预研目标**：确认 Phase B5 风格判定所需的外部市值数据是否可从现有 API 获得。
> **执行时间**：B1-0（新步骤，在 B1-1 前执行）

| 验证项 | 方法 | 成功标准 |
|:-------|:------|:--------|
| 东方财富 push2 行业分类 API | 向现有 API 请求目标代码的流通市值字段 | 返回字段中包含 `market_cap` 或 `circulating_market_cap` |
| akshare `stock_profile_em` | 调用 `stock_profile_em(code)` 检查返回值 | 返回市值 + PE/PB 且数据完整率 > 80% |
| **天天基金持仓市值占比（备选）** | 从已有持仓数据中提取每只个股的"占净值比例"，结合股票代码前缀判定规模（600/601/603=大盘，000/002/300=中小盘）；用于方案 A/B 均不可用时的兜底分类 | 至少能分出"大盘/中盘/小盘"三个档次，标注为"估算风格" |
| 代码段降级方案可行性 | 抽样 20 只穿透持仓股票对比代码段近似分类 vs 实际分类命中率 | 命中率 > 60% 则降级方案可用 |

预研结果决定 Phase B5 的实施方案。预研产出写入 `docs-stm/plan/notes/data-source-pre-study.md`。

预研结果决定 Phase B5 的实施方案。预研产出写入 `docs-stm/plan/notes/data-source-pre-study.md`。

#### 3.2.3 缓存注册

**关键设计原则**：历史快照类缓存使用独立缓存键（固定键名，无指纹后缀），
**不受持仓指纹影响**，仅当模块自身数据刷新时更新。

```python
# registry.py 新增
DataModuleDef("基金经理", "fund_manager",
              cache_prefixes=("fund_manager_",),
              exact_cache_keys=("fund_manager_snapshot",),  # 独立快照键（固定名）
              cache_ttl=CACHE_DAILY,
              cache_groups=("refresh",)),
DataModuleDef("持仓重合度", "fund_overlap",
              cache_prefixes=("fund_overlap_",),
              cache_ttl=CACHE_WEEKLY,
              cache_groups=("refresh",)),
DataModuleDef("基金集中度历史", "fund_concentration",
              cache_prefixes=("fund_concentration_",),
              exact_cache_keys=("fund_concentration_snapshot",),  # 独立快照键
              cache_ttl=CACHE_MONTHLY),  # 无 cache_group，手动管理
DataModuleDef("基金风格快照", "fund_style_snapshot",
              exact_cache_keys=("fund_style_snapshot",),  # 独立快照键
              cache_ttl=CACHE_MONTHLY),  # 无 cache_group
```

**快照键和指纹键的区别**：

| 缓存类型 | 键策略 | 失效触发 | 用途 |
|:---------|:-------|:---------|:------|
| `fund_manager_{code}` | 代码后缀 | TTL 1天 | API 原始数据 |
| `fund_manager_snapshot` | 固定键 | 每次分析后更新 | 经理变更检测的"上一次"对照 |
| `fund_overlap_{fingerprint}` | 指纹后缀 | 持仓变化 | 重合度计算结果（依赖持仓，指纹正确）|
| `fund_concentration_snapshot` | 固定键 | 每次分析后更新 | 集中度趋势的"上一次"对照 |

### 3.3 Phase B2：基金经理变更监控

#### 3.3.1 变更检测引擎

创建 `src/python/report/fund_manager_analysis.py`：

```python
# 历史快照使用固定键，不受持仓指纹影响
_SNAPSHOT_KEY = "fund_manager_snapshot"

def detect_manager_changes(holdings: list[Holding]) -> list[dict]:
    """检测持仓中所有基金的基金经理变更。

    对每只基金：
    1. 获取当前基金经理信息（fetch_fund_manager）
    2. 从 fund_manager_snapshot 读取上次快照
    3. 比较快照中的 manager_name vs 当前 manager_name
       - 不同 → 判定为变更（计算 start_date 距今判断变更时段）
       - 相同 → 无变更
    4. 更新快照：{code: {manager_name, check_date}, ...}

    Returns:
        [{code, name, current_manager, start_date, tenure_days,
          changed_1m: bool, changed_3m: bool, changed_6m: bool,
          alert_level: "紧急"/"关注"/"正常"/"首检"}]
    """

def _update_snapshot(current: dict[str, Any]):
    """更新基金经理快照（固定键 fund_manager_snapshot）。
    
    注意：此快照仅记录经理姓名+检查日期，不包含持仓指纹。
    持仓变化不会导致快照清除，经理变更检测完全独立于持仓变化。
    """

def _load_snapshot() -> dict | None:
    """读取基金经理快照（固定键）。"""
```

#### 3.3.2 变更时段判定规则

```
当前 manager_name != 历史快照中的 manager_name → 变更

变更时段判定（基于 start_date，任职起始日）：
  start_date 距今天 < 30 天 → changed_1m = True
  start_date 距今天 < 90 天 → changed_3m = True
  start_date 距今天 < 180 天 → changed_6m = True

预警级别：
  changed_1m → 🔴 紧急
  changed_3m → ⚠️ 关注
  changed_6m → ⚠️ 关注
  其他       → ✅ 正常

首次运行（无历史快照）：
  - 仅显示当前经理信息
  - 变更列显示「—」
  - 预警级别列显示「📋 首检」
  - 页签顶部显示引导文案：
    "此为首次运行，基金经理变更自下次报告起跟踪。
     当前监控 X 只基金，其中 X 只由 XXX 管理。"
```

#### 3.3.3 报告输出

**Excel 新页签 13. 基金经理变更监控：**

| 列 | 说明 |
|:---|:------|
| 基金名称 | 基金名称 |
| 基金代码 | 6 位代码 |
| 当前基金经理 | 姓名 + 任职起始日 |
| 任职天数 | 自任职起始日至今 |
| 1月内变更 | ✅ 否 / 🔴 是 / — 首检 |
| 3月内变更 | ✅ 否 / ⚠️ 是 / — 首检 |
| 6月内变更 | ✅ 否 / ⚠️ 是 / — 首检 |
| 预警级别 | 🔴 紧急 / ⚠️ 关注 / ✅ 正常 / 📋 首检 |

**HTML 新章节：**
- 表格展示，预警级别条件着色
- 首次运行时显示引导段落
- 顶部摘要：高风险基金数 / 总基金数

#### 3.3.4 缓存策略

```
fund_manager_{code}.json          → TTL: 1天（API 数据，加入 refresh 分组）
fund_manager_snapshot.json        → TTL: 永久（独立键，每次分析后覆写，无 cache_group）
```

### 3.4 Phase B3：持仓重合度矩阵

#### 3.4.1 重合度计算引擎

创建 `src/python/report/fund_overlap.py`：

```python
def compute_overlap_matrix(fund_holdings: dict[str, list[dict]],
                           fund_mv_map: dict[str, float] | None = None) -> dict:
    """计算持有基金两两之间的持仓重合度。

    Args:
        fund_holdings: {fund_code: [{name, code, ratio}, ...]}
                        取自 fetch_fund_holdings（已缓存）
        fund_mv_map: {fund_code: fund_mv} 可选，用于计算 overlap_mv_pct
                     fund_mv 来自 market_value.py 的 DetailRow.mv（份额×最新价）
                     不提供时仅输出 Jaccard + 共同标的数，不计算市值占比

    Returns:
        {
            "funds": [fund_code, ...],          # 基金代码列表（矩阵行列）
            "matrix": [[overlap_pct, ...], ...], # n×n 对称矩阵，元素 = max(jaccard, overlap_ratio)
            "pairs": [                           # 所有配对（按 overlap_pct 降序）
                {"fund_a": code, "fund_b": code,
                 "common_count": int,            # 共同标的数
                 "jaccard": float,               # Jaccard 系数
                 "overlap_mv_pct": float,        # 共同标的穿透市值占比（有 mv 数据时）
                 "common_stocks": [{"name": ..., "code": ...}]},  # 共同标的列表
                ...
            ],
            "has_mv_data": bool                 # 是否包含市值占比数据
        }
    """

def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard 相似系数：|A∩B| / |A∪B|"""

def _overlap_ratio(set_a: set, set_b: set) -> float:
    """重叠比例：|A∩B| / min(|A|, |B|)"""
```

**overlap_mv_pct 数据流说明**：

```
overlap_mv_pct 计算需要基金自身市值（fund_mv）：
  共同标的穿透市值 = Σ(fund_mv × ratio / 100) 对所有持有同一标的的基金求和

  数据来源：
    fund_mv        → DetailRow.mv（已存在于 market_value.py 的计算结果中）
    ratio          → fetch_fund_holdings 返回的 fund_holdings[code][i].ratio
  
  传递路径：
    market_value.py → compute_penetration_top10() → compute_overlap_matrix()
    
  如 fund_mv_map 为 None：跳过 overlap_mv_pct，仅输出 Jaccard + 共同标的数。
  矩阵元素始终取 max(jaccard, overlap_ratio)，不受 mv 数据影响。
```

#### 3.4.2 矩阵可视化

**Excel 新页签 14. 持仓重合度矩阵：**

```
            基金A    基金B    基金C
基金A      100%      35%      12%
基金B       35%     100%       8%
基金C       12%       8%     100%
```

- 对角线 100%（自身重叠）
- 条件格式热力图：>50% 红色、30-50% 橙色、15-30% 黄色、<15% 默认
- 矩阵下方列表：按重叠度降序排列的 TOP 配对 + 共同标的明细
- 只有 >= 2 只基金时渲染矩阵

**HTML 章节：**
- CSS 条件着色矩阵表
- 顶部标注"最高重叠对"高亮
- 共同标的名称列表可展开
- 仅有 0-1 只基金时显示"无可比较的基金"提示

#### 3.4.3 缓存策略

```
fund_overlap_{fingerprint}.json → TTL: 7天（持仓指纹驱动，持仓不变不清除）
```

依赖已有 `fetch_fund_holdings` 的缓存数据，无需重复请求。

### 3.5 Phase B4：持仓集中度监控

#### 3.5.1 集中度计算

```python
def compute_concentration(fund_holdings: dict) -> list[dict]:
    """计算基金的持仓集中度。

    每只基金的持仓按 ratio 降序排列后：
    - top3_pct = sum(前3名持仓占比)
    - top5_pct = sum(前5名持仓占比)
    - top10_pct = sum(前10名持仓占比)

    Returns:
        [{code, name, type,
          top3_pct, top5_pct, top10_pct,
          holding_count,                   # 前十大实际数（不足10的填实际数）
          prev_top10_pct,                  # 上期集中度（来自 fund_concentration_snapshot）
          change_pct,                      # 环比变化
          alert_level}]                    # 预警/关注/正常
    """

_SNAPSHOT_KEY = "fund_concentration_snapshot"   # 独立快照键，不受持仓指纹影响

def _load_history_snapshot() -> dict:
    """读取历史集中度快照（固定键）。
    格式：{code: {top10_pct, check_date, ...}}
    """

def _save_history_snapshot(current: list[dict]):
    """保存本次集中度数据到历史快照（覆写）。"""
```

> **注意**：`fund_concentration_snapshot` 使用固定键名（无指纹后缀），
> 每次分析后覆写。持仓变化不会误清除历史快照，确保环比连续性。

#### 3.5.2 变更检测逻辑

```
top10_pct 环比变化 > +20% → 🔴 紧急  （持仓显著集中化）
top10_pct 环比变化 > +10% → ⚠️ 关注
top10_pct 当前 > 80%      → ⚠️ 关注  （高度集中阈值）
其他                       → ✅ 正常
```

#### 3.5.3 报告输出

**Excel 新页签 15. 持仓集中度监控：**

| 列 | 说明 |
|:---|:------|
| 基金名称 | 名称 |
| 代码 | 6 位 |
| 类型 | QDII/ETF/联接/债券/主动 |
| 前3占比 | Top3 集中度 % |
| 前5占比 | Top5 集中度 % |
| 前10占比 | Top10 集中度 % |
| 上期前10占比 | 历史对照（有数据时显示；首检显示「—」）|
| 环比变化 | 百分点变化 + 方向箭头（首检显示「基线已记录」）|
| 预警级别 | 🔴 / ⚠️ / ✅（首检显示「📋 基线已记录」）|

**HTML 新章节：**
- 首次运行时显示引导"此为首次运行，集中度基线已记录，趋势自下次报告起对比"
- 表格 + 预警着色
- 顶部汇总：高风险基金数

#### 3.5.4 缓存策略

```
fund_concentration_snapshot.json.gz → TTL: 永久（独立快照键，每次覆写）
```

### 3.6 Phase B5：基金风格漂移检测

> **前置条件**：数据源预研（B1-0）已确认市值数据可用性或确认启用降级方案。

#### 3.6.1 风格判定模型

创建 `src/python/report/fund_style_analysis.py`：

```python
# 六宫格风格分类
_STYLE_BOXES = {
    "large_growth":      "大盘成长",
    "large_value":       "大盘价值",
    "large_blend":       "大盘混合",
    "mid_growth":        "中盘成长",
    "mid_value":         "中盘价值",
    "mid_blend":         "中盘混合",
    "small_growth":      "小盘成长",
    "small_value":       "小盘价值",
    "small_blend":       "小盘混合",
}

def classify_style(penetration_top10: list[dict]) -> str:
    """基于穿透 TOP10 持仓的市值+估值特征判定基金风格。

    方案 A（外部数据可用时）：
      1. 获取每只持仓个股的流通市值（东方财富 API 或 akshare）
      2. 市值规模划分：>500亿=大盘, 100-500亿=中盘, <100亿=小盘
      3. 估值倾向划分：PE < 15×行业平均PE = 价值型,
                       PE > 20×行业平均PE = 成长型
                       PE 在中间区间 = 混合型
      4. 按持仓市值加权得最终风格标签

    方案 B（降级，外部数据不可用时）：
      使用 _estimate_style_by_code 按代码段粗略归类
      结果标注"估算风格"

    Returns:
        风格标签名称（如"大盘成长"），数据不足返回"--"
    """

def _estimate_style_by_code(code: str) -> str:
    """按代码前缀粗略估算风格（降级方案）。"""

def detect_style_drift(code: str, current_style: str) -> dict:
    """检测风格漂移。

    与历史快照（fund_style_snapshot 固定键）对比：
    - 风格跨一格（如大盘成长→大盘混合）：轻度漂移
    - 风格跨两格（如大盘成长→中盘成长）：中度漂移
    - 风格跨三格+（如大盘价值→小盘成长）：严重漂移

    Returns:
        {code, name, current_style, prev_style, drift_level, drift_score}
    """
```

#### 3.6.2 报告输出

**Excel 新页签 16. 基金风格分析：**

| 列 | 说明 |
|:---|:------|
| 基金名称 | 名称 |
| 代码 | 6 位 |
| 当前风格 | 六宫格标签（大盘成长/...）或降级版"估算风格" |
| 上期风格 | 历史风格（有数据时显示；首检显示「基准确立中」）|
| 漂移评分 | 0-10（0=无漂移，10=严重），降级方案隐藏此列 |
| 漂移等级 | 无/轻度/中度/严重 |
| 备注 | 数据来源、是否降级标注 |

**HTML 新章节：**
- 首次运行时显示引导"此为首次运行，风格基准确立中"
- 表格 + 条件着色

### 3.7 TUI 菜单变更 + HTML 模板优化

#### 3.7.1 TUI 菜单设计

| 当前菜单 | 变更 |
|:---------|:------|
| B「生成全系列包含新闻的报告」 | 新增内容说明增加「含基金深度分析（13-16）」，用户可见 |
| L「全系列完整版报告」 | 同上，新增内容说明 |
| E/H「基础版」 | **不变**（不含13-16页签）|
| R「刷新配置」 | 不变 |
| 1「更新基础类缓存」 | 描述追加「基金经理/重合度」，确保 `fund_manager_` 和 `fund_overlap_` 前缀被覆盖 |
| 3「清理过期缓存」 | 不变（自动清理 TTL 过期 + 无 cache_group 快照不受影响）|

> 不需要新增菜单项。13-16 页签自动包含在菜单 B/L 的报告中，用户无需额外操作。

#### 3.7.2 HTML 模板条件渲染优化

现有模板已有 5 个条件分支 `{% if menu in ('B','L') %}`。新增 4 个章节后共 9 个。

**优化方案**：在模板顶部抽取公共变量：

```jinja2
{% set show_news = menu in ('B','L') %}        {# 页签 6-7 #}
{% set show_llm = menu == 'L' %}               {# 页签 8-12 #}
{% set show_fund_deep = menu in ('B','L') %}    {# 页签 13-16 #}
```

- 所有条件判断改用变量名，模板可读性提升
- 新增条件只改顶部变量定义
- `html_writer.py` 传递 `menu` 变量即可，无需修改渲染逻辑

**模板新增章节结构**：

```jinja2
{% if show_fund_deep %}
{# =========================================================
   autoescape 安全说明（R-149 延续）：
   - 基金名称/经理姓名/风格标签等用户可见文本全部来自外部 API
   - Jinja2 默认 autoescape 生效，禁止添加 |safe 过滤器
   - 百分比数值和系统生成的风格标签（"大盘成长"等）同样保持 autoescape
   ========================================================= #}
{# 13. 基金经理变更监控 — 用户数据：经理名/基金名（autoescape） #}
{# 14. 持仓重合度矩阵 — 用户数据：基金名/代码（autoescape）     #}
{# 15. 持仓集中度监控 — 用户数据：百分比/基金名（autoescape）   #}
{# 16. 基金风格分析   — 用户数据：风格标签/基金名（autoescape） #}
{% endif %}
```

---

## 4. Phase 目标与回退

### Phase B0：数据源可行性预研

| 维度 | 内容 |
|:-----|:------|
| **目标** | 确认东方财富/akshare API 是否提供持仓个股市值+PE/PB 数据；确认代码段降级方案命中率 |
| **成功标志** | 预研报告输出到 `docs-stm/plan/notes/data-source-pre-study.md`；明确 Phase B5 方案 A/B 决策 |
| **失败回退** | 预研结果无效 → 默认启用降级方案 B，Phase B5 不输出漂移评分 |
| **进入下一 Phase 前提** | 预研完成且结论明确 |

### Phase B1：基金元数据增强

| 维度 | 内容 |
|:-----|:------|
| **目标** | 成功从天天基金页面解析基金经理姓名+任职起始日；新建 `fetcher/fund_manager.py`；在 registry.py 注册新的缓存类型（含独立快照键）|
| **成功标志** | `pytest src/test/ -k "fund_manager"` 全部通过；手动测试 `fetch_fund_manager("110011")` 返回正确数据 |
| **失败回退** | 解析失败 → 降级显示「—」；`git revert` 该 Phase commit |
| **进入下一 Phase 前提** | 至少 3 只基金的基金经理解析测试通过 |

### Phase B2：基金经理变更监控

| 维度 | 内容 |
|:-----|:------|
| **目标** | Excel 页签 13 + HTML 章节输出基金经理信息与变更状态；变更检测逻辑覆盖 1月/3月/6月窗口；首次运行引导文案正确 |
| **成功标志** | 报告包含页签 13；变更检测与预期一致（mock 覆盖变更/未变更/首检 3 种场景）|
| **失败回退** | 检测逻辑错误 → 回到 B1 阶段的数据读取模式，不输出变更列；`git revert` 该 commit |
| **进入下一 Phase 前提** | B2 测试通过 |

### Phase B3：持仓重合度矩阵

| 维度 | 内容 |
|:-----|:------|
| **目标** | 两两基金 Jaccard + overlap_mv_pct 正确（含/不含市值数据两种模式）；Excel 热力图矩阵 + HTML 表格渲染正确 |
| **成功标志** | 持股中有 2 只基金持有同一股票时，矩阵对应单元格 > 0；3只基金×3只基金矩阵生成正确 |
| **失败回退** | 计算逻辑偏差 → 仅输出配对列表（降级），不渲染矩阵；`git revert` B3 commit |
| **进入下一 Phase 前提** | B3 单元测试 + 场景测试通过 |

### Phase B4：持仓集中度监控

| 维度 | 内容 |
|:-----|:------|
| **目标** | 正确计算前3/5/10占比；独立快照键（非指纹驱动）存储与读取正确；环比变化+预警逻辑准确；首次运行显示"基线已记录" |
| **成功标志** | 手动构造数据验证前3/5/10占比与预期一致；持仓变化后快照保留 |
| **失败回退** | 快照机制有 bug → 仅输出当期集中度（无趋势），不输出预警列；`git revert` B4 commit |
| **进入下一 Phase 前提** | B4 测试通过 |

### Phase B5：基金风格漂移检测

| 维度 | 内容 |
|:-----|:------|
| **目标** | 基于预研结论实现方案 A（市值+估值）或方案 B（代码段降级）；漂移检测逻辑正确 |
| **成功标志** | 至少 50% 的主动基金能输出风格标签；漂移检测逻辑与手动分析一致 |
| **失败回退** | 方案 A 数据不稳定 → 回退方案 B（降级模式，标注"估算风格"）；`git revert` B5 commit |
| **进入下一 Phase 前提** | B5 核心逻辑验证通过 |

### 全迭代最终目标

| 指标 | 当前 | 目标 |
|:-----|:----:|:----:|
| 基金经理变更监控 | ❌ 无 | ✅ 页签 13 |
| 持仓重合度矩阵 | ❌ 无 | ✅ 页签 14 |
| 持仓集中度监控 | ❌ 无 | ✅ 页签 15 |
| 基金风格漂移检测 | ❌ 无 | ✅ 页签 16 |
| 新增报告页签数 | 12 个 | 16 个 |
| 新增测试项 | — | >= 115 项 |
| report 模式测试通过 | ✅ | ✅ 不降级 |

---

## 5. 依赖评估

### 5.1 新增源文件

| 文件 | 用途 | 所属 Phase |
|:-----|:------|:-----------|
| `src/python/fetcher/fund_manager.py` | 基金经理数据抓取 | B1 |
| `src/python/report/fund_manager_analysis.py` | 基金经理变更检测+报告数据 | B2 |
| `src/python/report/fund_manager_sheet.py` | 基金经理变更监控 Excel 写入 | B2 |
| `src/python/report/fund_overlap.py` | 持仓重合度矩阵计算 | B3 |
| `src/python/report/fund_overlap_sheet.py` | 持仓重合度矩阵 Excel/HTML 写入 | B3 |
| `src/python/report/fund_concentration.py` | 持仓集中度计算+趋势 | B4 |
| `src/python/report/fund_concentration_sheet.py` | 持仓集中度 Excel/HTML 写入 | B4 |
| `src/python/report/fund_style_analysis.py` | 基金风格判定+漂移检测 | B5 |
| `src/python/report/fund_style_sheet.py` | 基金风格分析 Excel/HTML 写入 | B5 |

### 5.2 新增测试文件

| 文件 | 覆盖内容 | 预期项数 |
|:-----|:---------|:--------:|
| `src/test/unit/fetcher/test_fund_manager.py` | 基金经理解析/超时/结构变化 | ~15 |
| `src/test/unit/report/test_fund_manager_analysis.py` | 变更检测/快照/预警/首检 | ~25 |
| `src/test/unit/report/test_fund_overlap.py` | Jaccard/矩阵/overlap_mv_pct | ~20 |
| `src/test/unit/report/test_fund_concentration.py` | 集中度计算/快照/预警 | ~18 |
| `src/test/unit/report/test_fund_style_analysis.py` | 风格判定/漂移检测（含降级）| ~17 |
| `src/test/unit/report/test_html_template.py` | **扩展**新增 13-16 章节渲染验证 | ~10 |
| `src/test/scenario/test_fund_deep_analysis.py` | 端到端场景（含报告渲染）| ~10 |
| 合计 | | ~115 |

### 5.3 修改现有文件

| 文件 | 变更 |
|:-----|:------|
| `src/python/report/excel_generator.py` | 追加页签 13-16 写入调用 |
| `src/python/report/html_writer.py` | 追加页签 13-16 HTML 数据与渲染；设置 `show_fund_deep` 变量 |
| `src/python/report/html_builders.py` | 新增各模块的数据构建函数 |
| `src/python/tmpl/report_template.html` | 顶部抽取 `show_fund_deep` 变量；新增 4 个 Jinja2 模板块 |
| `src/python/registry.py` | 新增 DataModuleDef（含独立快照键）|
| `src/python/tui_handlers.py` | 缓存管理菜单描述同步 |
| `src/python/tui_menu.py` | 菜单 B/L 描述追加"含基金深度分析" |
| `src/python/report/penetration.py` | 调用 `fetch_fund_holdings` 后顺带调用 `parse_manager_from_html` |
| `src/python/llm/prompts.py` 或 `generators.py` | (可选) 追加基金经理/集中度数据到智囊团复盘 Prompt |
| `docs-stm/managements/requirements.md` | 新增 B 系列功能说明 |
| `docs-stm/managements/test-coverage.md` | 新增测试项统计 |
| `docs-stm/manuals/datasource-and-folders.md` | 目录树同步 |
| `docs-stm/managements/plan.md` | B 状态更新 |
| `docs-stm/managements/changelog.md` | 变更记录 |

---

## 6. 实施步骤（拆细为 19 个原子步）

### 6.0 数据源预研（1 步）

```
Step B0 → B1-1 ...
(预研)
```

#### Step B0：数据源可行性预研

| 字段 | 值 |
|:-----|:----|
| **目标** | 确认东方财富/akshare 是否提供持仓个股市值+PE/PB 数据；明确 Phase B5 方案路线 |
| **文件** | 新建 `docs-stm/plan/notes/data-source-pre-study.md` |
| **操作** | (1) 调用东方财富 push2 行业 API 检查 `market_cap` 字段<br>(2) 调用 `akshare stock_profile_em` 获取市值+PE/PB<br>(3) 抽样评估代码段降级方案命中率<br>(4) 输出决策：方案 A 或 方案 B |
| **验证** | 预研报告有明确的方案选择和风险评估 |
| **预期产出** | commit: "chore: B 数据源可行性预研报告" |
| **回滚** | 预研报告本身无代码影响 |

### 6.1 Phase B1：元数据增强（4 步）

```
Step B1-1 → Step B1-2 → Step B1-3 → Step B1-4
(基金经理API)  (单元测试)    (registry注册)  (集成验证)
```

#### Step B1-1：创建 `fetcher/fund_manager.py`

| 字段 | 值 |
|:-----|:----|
| **目标** | 实现 `fetch_fund_manager(code)` + `parse_manager_from_html(html)`，支持与穿透模块共用一个 HTML 页面 |
| **文件** | 新建 `src/python/fetcher/fund_manager.py` |
| **操作** | (1) 实现纯解析函数 `parse_manager_from_html(html)` — 供穿透模块调用<br>(2) 实现 `fetch_fund_manager(code)` 含缓存+回退<br>(3) 回退方案 `_parse_manager_from_archive_page(code)`<br>(4) 更新 `__init__.py` 导出 |
| **验证** | `parse_manager_from_html(...)` 从穿透模块的 HTML 中提取经理信息 |
| **预期产出** | commit: "feat: 基金经理数据获取模块 — fund_manager.py" |
| **回滚** | `git revert` 该 commit；删除新增文件 |

#### Step B1-2：基金经理 API 单元测试

| 字段 | 值 |
|:-----|:----|
| **目标** | mock 天天基金 HTML 响应，覆盖正常解析、页面结构变化、网络超时 3 种场景 |
| **文件** | 新建 `src/test/unit/fetcher/test_fund_manager.py` |
| **操作** | (1) 录制真实基金页面 HTML 存为测试 fixture<br>(2) mock 响应测试正常解析<br>(3) mock 超时验证 None 返回<br>(4) 标记 `@pytest.mark.unit_providers` |
| **验证** | `pytest src/test/ -m "unit_providers" -k "fund_manager"` 全部通过 |
| **预期产出** | commit: "test: 基金经理 API 单元测试 — 3 场景覆盖" |
| **回滚** | `git revert` 该 commit；删除测试文件 |

#### Step B1-3：registry.py 缓存注册

| 字段 | 值 |
|:-----|:----|
| **目标** | 在 registry 注册 4 个新 DataModuleDef，历史快照使用独立键（非指纹驱动）|
| **文件** | `src/python/registry.py` |
| **操作** | (1) 新增 4 个 `DataModuleDef`：`fund_manager`（含 `fund_manager_snapshot` 独立键）、`fund_overlap`、`fund_concentration`（含独立键）、`fund_style_snapshot`<br>(2) 在 registry test 中验证新条目可查询 |
| **验证** | `pytest src/test/ -m "unit_core" -k "registry"` 全部通过 |
| **预期产出** | commit: "feat: registry 注册基金分析数据模块（含独立快照键）" |
| **回滚** | `git revert` 该 commit；注释掉新增条目 |

#### Step B1-4：集成验证 + 穿透模块联动

| 字段 | 值 |
|:-----|:----|
| **目标** | 基金经理 API 与穿透模块联动，同页面顺带提取经理数据 |
| **文件** | `src/python/report/penetration.py` |
| **操作** | (1) 在 `_merge_fund_layer` 或 `compute_penetration_top10` 中调用 `fetch_fund_holdings` 后顺带调用 `parse_manager_from_html`<br>(2) 经理结果写入缓存供 B2 使用<br>(3) 验证菜单 [1] 覆盖 `fund_manager_` 前缀 |
| **验证** | 菜单 [1] 执行后 manager 缓存存在；穿透模块请求不额外增加 HTTP |
| **预期产出** | 与 B1-3 同一 commit |
| **回滚** | 与 B1-3 同 |

---

### 6.2 Phase B2：基金经理变更监控（4 步）

```
Step B2-1 → Step B2-2 → Step B2-3 → Step B2-4
(检测引擎)   (Excel 13)   (HTML 13)   (测试)
```

#### Step B2-1：变更检测引擎

| 字段 | 值 |
|:-----|:----|
| **目标** | `detect_manager_changes()` 遍历基金，输出变更状态+预警+首检引导 |
| **文件** | 新建 `src/python/report/fund_manager_analysis.py` |
| **操作** | (1) 实现 `detect_manager_changes(holdings)` |
| **操作** | (2) 实现 `_load_snapshot()` / `_update_snapshot()`（独立键 `fund_manager_snapshot`）<br>(3) 实现变更判定（1月/3月/6月）+ 预警级别<br>(4) 首次运行无快照时返回"首检"状态+引导文案 |
| **验证** | 构造含变更/未变更/首检 3 种场景，结果一致 |
| **预期产出** | commit: "feat: 基金经理变更检测引擎 — fund_manager_analysis.py" |
| **回滚** | `git revert` 该 commit |

#### Step B2-2：Excel 页签 13 写入

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 新增页签「13. 基金经理变更监控」|
| **文件** | 新建 `fund_manager_sheet.py`，修改 `excel_generator.py` |
| **操作** | (1) 使用已有 `write_title_row/write_header_row/write_data_row` 模式<br>(2) 条件格式：红色/橙色/灰色字体<br>(3) `excel_generator.py` `write_sheets()` 追加页签 13 |
| **验证** | 菜单 B/L 生成报告后，Excel 包含页签 13 |
| **预期产出** | commit: "feat: 基金经理变更监控 Excel 页签 13" |
| **回滚** | `git revert` 该 commit；excel_generator.py 恢复 |

#### Step B2-3：HTML 章节渲染

| 字段 | 值 |
|:-----|:----|
| **目标** | HTML 报告新增第 13 章节 |
| **文件** | `html_writer.py`, `report_template.html` |
| **操作** | (1) html_builders.py 新增 `_build_manager_analysis_data()`<br>(2) html_writer.py 追加数据传递 + 设置 `show_fund_deep=True`<br>(3) report_template.html 顶部抽取 `{% set show_fund_deep = ... %}`<br>(4) 新增模板块含引导+表格+条件着色 |
| **验证** | 菜单 L 生成后 HTML 包含第 13 章节（菜单 E/H 不包含）|
| **预期产出** | commit: "feat: 基金经理变更监控 HTML 章节" |
| **回滚** | `git revert` 该 commit |

#### Step B2-4：基金经理模块测试

| 字段 | 值 |
|:-----|:----|
| **目标** | ~25 项单元测试覆盖变更检测/快照/预警/首检 |
| **文件** | 新建 `test_fund_manager_analysis.py` |
| **操作** | (1) mock `fetch_fund_manager` 返回可控数据<br>(2) mock 快照三种状态（有变更/无变更/无快照）<br>(3) 验证引导文案输出<br>(4) 标记 `@pytest.mark.unit_report` |
| **验证** | `pytest src/test/ -m "unit_report" -k "fund_manager"` 全部通过 |
| **预期产出** | commit: "test: 基金经理模块 25 项单元测试（含首检）" |
| **回滚** | `git revert` 该 commit |

---

### 6.3 Phase B3：持仓重合度矩阵（4 步）

```
Step B3-1 → Step B3-2 → Step B3-3 → Step B3-4
(计算引擎)   (渲染辅助)   (报告 14)   (测试)
```

#### Step B3-1：重合度计算引擎

| 字段 | 值 |
|:-----|:----|
| **目标** | `compute_overlap_matrix()` 正确计算 Jaccard + overlap_mv_pct（含/不含 mv 双模式）+ 配对排序 |
| **文件** | 新建 `src/python/report/fund_overlap.py` |
| **操作** | (1) 实现 `_jaccard_similarity()` + `_overlap_ratio()`<br>(2) 实现 `compute_overlap_matrix(fund_holdings, fund_mv_map=None)`<br>(3) 无 mv 数据时跳过 overlap_mv_pct，矩阵仍正确渲染 |
| **验证** | 手工构造 3 只基金数据（A∩B=2, B∩C=1, A∩C=0）验证矩阵正确 |
| **预期产出** | commit: "feat: 持仓重合度矩阵计算引擎" |
| **回滚** | `git revert` 该 commit |

#### Step B3-2：矩阵渲染辅助

| 字段 | 值 |
|:-----|:----|
| **目标** | 矩阵转置 + 热力图阈值 + 配对排序 |
| **文件** | `fund_overlap.py`（追加）|
| **操作** | (1) 矩阵→Excel 格式转换 + 热力图阈值分类<br>(2) 配对排序 + TOP N 筛选<br>(3) 仅 >= 2 只基金时渲染，否则输出占位提示 |
| **验证** | 转换函数输入 mock 矩阵，输出 Excel 可读二维列表 |
| **预期产出** | 与 B3-1 同一 commit |
| **回滚** | 与 B3-1 同 |

#### Step B3-3：报告输出（Excel 14 + HTML 第 14 章）

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 页签「14. 持仓重合度矩阵」+ HTML 第 14 章节 |
| **文件** | 新建 `fund_overlap_sheet.py`；修改 `excel_generator.py`、`html_writer.py`、`report_template.html` |
| **操作** | (1) Excel：矩阵页签+条件热力图+底部配对明细<br>(2) HTML：矩阵+CSS着色+最高重叠对高亮 |
| **验证** | 含多只基金的报告包含重合度矩阵 |
| **预期产出** | commit: "feat: 持仓重合度矩阵报告输出" |
| **回滚** | `git revert` 该 commit |

#### Step B3-4：重合度测试 + HTML 模板渲染测试

| 字段 | 值 |
|:-----|:----|
| **目标** | ~20 项单元测试覆盖 Jaccard/矩阵/渲染；扩展 HTML 模板渲染测试覆盖页签 14 |
| **文件** | 新建 `test_fund_overlap.py`；扩展 `test_html_template.py` |
| **操作** | (1) mock 基金持仓数据验证 Jaccard/矩阵对称性<br>(2) 验证 overlap_mv_pct 有/无 mv 数据两种模式<br>(3) 新增 HTML 渲染测试：传入 mock 重合度数据，验证 HTML 表格存在<br>(4) 标记 `@pytest.mark.unit_report` |
| **验证** | `pytest src/test/ -m "unit_report" -k "overlap or html_template"` 全部通过 |
| **预期产出** | commit: "test: 持仓重合度模块 20 项 + HTML 模板渲染测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.4 Phase B4：持仓集中度监控（3 步）

#### Step B4-1：集中度计算 + 快照机制（独立键）

| 字段 | 值 |
|:-----|:----|
| **目标** | `compute_concentration()` 正确计算前3/5/10集中度；独立快照键（非指纹驱动）|
| **文件** | 新建 `src/python/report/fund_concentration.py` |
| **操作** | (1) 实现集中度计算<br>(2) 实现 `_load_history_snapshot()` / `_save_history_snapshot()`（键 `fund_concentration_snapshot`）<br>(3) 环比变化+预警判定<br>(4) 首次运行时返回"基线已记录"状态 |
| **验证** | 构造数据验证前3/5/10占比；更新持仓后验证快照不丢失 |
| **预期产出** | commit: "feat: 持仓集中度计算+独立快照" |
| **回滚** | `git revert` 该 commit |

#### Step B4-2：报告输出（Excel 15 + HTML 第 15 章）

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 页签「15. 持仓集中度监控」+ HTML 第 15 章节 |
| **文件** | 新建 `fund_concentration_sheet.py`；修改 `excel_generator.py`、`html_writer.py`、`report_template.html` |
| **操作** | (1) Excel：表格+预警着色+趋势箭头+首检"基线已记录"<br>(2) HTML：章节+CSS预警标签+首次引导 |
| **验证** | 报告包含集中度页签/章节 |
| **预期产出** | commit: "feat: 持仓集中度监控报告输出" |
| **回滚** | `git revert` 该 commit |

#### Step B4-3：集中度测试 + HTML 渲染测试

| 字段 | 值 |
|:-----|:----|
| **目标** | ~18 项单元测试覆盖计算/快照/预警；扩展 HTML 测试覆盖页签 15 |
| **文件** | 新建 `test_fund_concentration.py`；扩展 `test_html_template.py` |
| **操作** | (1) 构造 3 种集中度水平数据<br>(2) mock 快照验证环比<br>(3) 验证快照不随持仓指纹丢失<br>(4) 标记 `@pytest.mark.unit_report` |
| **验证** | `pytest src/test/ -m "unit_report" -k "concentration or html_template"` 全部通过 |
| **预期产出** | commit: "test: 持仓集中度模块 18 项 + HTML 渲染测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.5 Phase B5：基金风格漂移检测（2 步）

#### Step B5-1：风格判定模型

| 字段 | 值 |
|:-----|:----|
| **目标** | 基于预研结论实现方案 A 或方案 B，含漂移检测 |
| **文件** | 新建 `src/python/report/fund_style_analysis.py` |
| **操作** | (1) 按预研结论实现 `classify_style()` — 方案 A（市值+估值）或方案 B（代码段）<br>(2) 实现 `detect_style_drift()` 跨期对比（使用独立快照键 `fund_style_snapshot`）<br>(3) 首次运行时记录基线 |
| **验证** | 至少 50% 持仓基金能输出风格标签 |
| **预期产出** | commit: "feat: 基金风格判定+漂移检测" |
| **回滚** | `git revert` 该 commit |

#### Step B5-2：报告输出 + 测试

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 页签「16. 基金风格分析」+ HTML 第 16 章 + ~17 项测试 + HTML 渲染测试 |
| **文件** | 新建 `fund_style_sheet.py`；修改 `excel_generator.py`、`html_writer.py`、`report_template.html`；新建测试文件；扩展 `test_html_template.py` |
| **操作** | (1) Excel 页签写入（含首检"基准确立中"）<br>(2) HTML 章节渲染<br>(3) 测试覆盖两种方案 |
| **验证** | `pytest src/test/ -m "unit_report" -k "fund_style or html_template"` 全部通过 |
| **预期产出** | commit: "feat: 基金风格分析报告输出+测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.6 最终验证（1 步）

#### Step E：全量回归 + 场景测试 + 报告验证

| 字段 | 值 |
|:-----|:----|
| **目标** | ~115 新增项 + 原有 regression 全部通过；菜单 B/L 生成报告含页签 13-16 |
| **操作** | (1) `test_runner.py --mode unit` — report 标记项数不降<br>(2) `test_runner.py --mode regression` — 场景 0 failed<br>(3) 菜单 B/L 生成报告确认 4 个新页签存在<br>(4) 菜单 E/H 验证不包含新页签 |
| **验证** | (1) `unit` 0 failed (2) `regression` 0 failed (3) 报告含 13-16 页签 |
| **预期产出** | commit: "docs: B 迭代完成 — 基金深度分析 4 模块上线" |
| **回滚** | 任一项 failed → 追踪到对应 Phase 修复 |

---

## 7. 实施步骤总览

```
          B0       Phase B1                Phase B2              Phase B3
Week 1                              Week 2                             Week 3
+------+------+------+------+------+------+------+------+------+------+------+------+------+------+------+------+
|  B0  |B1-1  |B1-2  |B1-3~4|B2-1  |B2-2  |B2-3  |B2-4  |B3-1  |B3-2  |B3-3  |B3-4  |B4-1  |B4-2  |B4-3  |B5-1  |
|预研  |经理  |经理  |注册表|变更  |Excel |HTML  |测试  |重叠  |渲染  |报告  |测试  |集中度|集中度|测试  |风格  |
|      |API   |UT    |+联动  |引擎  |13   |13章  |      |引擎  |辅助  |14   |+HTML |计算  |15   |+HTML |判定  |
+------+------+------+------+------+------+------+------+------+------+------+------+------+------+------+------+
| B5-2 |  E   |      |      |      |      |      |      |      |      |      |      |      |      |      |      |
|风格  |全量  |      |      |      |      |      |      |      |      |      |      |      |      |      |      |
|报告+ |回归  |      |      |      |      |      |      |      |      |      |      |      |      |      |      |
|测试  |      |      |      |      |      |      |      |      |      |      |      |      |      |      |      |
+------+------+------+------+------+------+------+------+------+------+------+------+------+------+------+------+
   ^B0完成    ^B1完成        ^B2: 页签13上线   ^B3: 页签14上线   ^B4: 页签15上线   ^B5: 页签16上线
```

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| 基金经理历史快照使用持仓指纹驱动 → 持仓不变时检测不到经理变更（**原计划设计缺陷**）| 中 | 高 | ❌ 已修复：快照使用独立键 `fund_manager_snapshot`，不受持仓指纹影响；每次分析后覆写 |
| 天天基金页面结构变更（基金经理解析失败） | 中 | 高 | 两层解析策略（主页→档案页回退）；解析失败降级「—」不阻塞；单元测试锁定当前结构 |
| 东方财富行业分类 API 不提供市值/估值数据（风格判定失效）| 中 | 中 | **预研提前到 Phase B0**；不可行则启用降级方案 B（代码段近似分类，标注"估算风格"）|
| 首次运行时所有页签全"首检"/空信息（用户体验差）| 高 | 中 | ✅ 已修复：每个页签顶部添加引导文案 + 当前基金摘要，让首次运行仍有信息量 |
| 新增 4 个报告页签导致报告生成时间增加 | 中 | 低 | 所有新增数据复用已有缓存；经理页面与穿透页面合并请求，0 额外 HTTP |
| 持仓重合度矩阵渲染大量基金时 O(n²) 膨胀 | 低 | 低 | 仅对持仓基金计算（通常 3-10 只）；只 >= 2 只基金时渲染矩阵 |
| HTML 条件渲染 9 个分支 → 模板可维护性下降 | 中 | 低 | ✅ 已修复：模板顶部抽取 `show_*` 变量，条件分支从 9 次散落判断缩为 3 次变量引用 |
| 新增缓存前缀与现有菜单 [1][2] 清理逻辑不一致 | 低 | 中 | registry.py 中快照键（`*_snapshot`）不加入 `refresh` 分组；经理数据加入 refresh 组 |
| 快照键被误清除 → 环比趋势丢失 | 低 | 中 | 所有快照使用独立键 `exact_cache_keys`，无 `cache_groups`，菜单 [1][2] 不触及 |
| overlap_mv_pct 因 fund_mv 数据不可用而不输出 | 低 | 低 | 函数签名支持 `fund_mv_map=None`，无 mv 时仅输出 Jaccard + 共同标的数 |

---

## 9. 变更文件清单

### 9.1 新增文件

| 文件 | Phase | 行数预估 |
|:-----|:------|:--------:|
| `src/python/fetcher/fund_manager.py` | B1 | ~180 |
| `src/python/report/fund_manager_analysis.py` | B2 | ~220 |
| `src/python/report/fund_manager_sheet.py` | B2 | ~120 |
| `src/python/report/fund_overlap.py` | B3 | ~220 |
| `src/python/report/fund_overlap_sheet.py` | B3 | ~180 |
| `src/python/report/fund_concentration.py` | B4 | ~160 |
| `src/python/report/fund_concentration_sheet.py` | B4 | ~120 |
| `src/python/report/fund_style_analysis.py` | B5 | ~200 |
| `src/python/report/fund_style_sheet.py` | B5 | ~120 |
| `src/test/unit/fetcher/test_fund_manager.py` | B1 | ~80 |
| `src/test/unit/report/test_fund_manager_analysis.py` | B2 | ~120 |
| `src/test/unit/report/test_fund_overlap.py` | B3 | ~100 |
| `src/test/unit/report/test_fund_concentration.py` | B4 | ~90 |
| `src/test/unit/report/test_fund_style_analysis.py` | B5 | ~80 |
| `src/test/scenario/test_fund_deep_analysis.py` | E | ~100 |
| `docs-stm/plan/notes/data-source-pre-study.md` | B0 | ~30 |

### 9.2 修改文件

| 文件 | 变更内容 |
|:-----|:---------|
| `src/python/registry.py` | 新增 4 个 DataModuleDef（含独立快照键）|
| `src/python/report/excel_generator.py` | 追加页签 13-16 写入调用 |
| `src/python/report/html_writer.py` | 追加页签 13-16 数据传递 + `show_fund_deep` |
| `src/python/report/html_builders.py` | 新增各模块的数据构建函数 |
| `src/python/tmpl/report_template.html` | 顶部 `{% set %}` 变量 + 4 个条件模板块 |
| `src/python/report/penetration.py` | 顺带调用 `parse_manager_from_html` |
| `src/python/tui_handlers.py` | 缓存菜单描述同步 |
| `src/python/tui_menu.py` | 菜单 B/L 描述同步 |
| `src/test/unit/report/test_html_template.py` | 扩展覆盖页签 13-16 渲染 |
| `src/python/llm/prompts.py` | （可选）追加基金数据到智囊团 Prompt |
| `docs-stm/managements/requirements.md` | 新增 B 系列功能说明 |
| `docs-stm/managements/test-coverage.md` | 新增测试项统计 |
| `docs-stm/manuals/datasource-and-folders.md` | 目录树同步 |
| `docs-stm/managements/plan.md` | B 状态更新 |
| `docs-stm/managements/changelog.md` | 变更记录 |
