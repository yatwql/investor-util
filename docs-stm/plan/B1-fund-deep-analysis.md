# B 迭代计划：基金持仓专属深度分析

创建日期：2026-07-04
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
| **变更检测** | 缓存上次基金经理快照，检测近 1 月/3 月/6 月内是否发生变更 |
| **报告输出** | 基金维度展示：当前基金经理、任职起始日、任职天数、近 N 月是否变更 |
| **异常标注** | 30 天内变更标记为 🔴 紧急、90 天内变更标记为 ⚠️ 关注 |
| **缓存策略** | `fund_manager_{code}.json`，日级 TTL（CACHE_DAILY） |

#### F2：持仓重合度矩阵

| 需求 | 描述 |
|:-----|:------|
| **重叠标的识别** | 对任意两只基金，统计共同持有的底层股票/债券数量 |
| **重叠度指标** | 输出：(1) 共同标的数 (2) Jaccard 相似系数 (3) 共同标的穿透市值占比 |
| **矩阵可视化** | 基金 × 基金对称矩阵，热力图着色（高重叠红色预警） |
| **报告输出** | Excel 页签：「N.2 持仓重合度矩阵」+ HTML 章节，含最高重叠 TOP 对标注 |
| **缓存策略** | `fund_overlap_{fingerprint}.json`，持仓指纹驱动失效 |

#### F3：基金风格漂移检测

| 需求 | 描述 |
|:-----|:------|
| **风格维度** | 大盘/中盘/小盘 x 成长/价值/混合（六宫格风格箱） |
| **判定依据** | 按底层持仓的市值规模（流通市值）和估值指标（PE/PB）加权判断 |
| **漂移计算** | 与最近一期（或招募说明书约定）的风格标签对比，输出漂移评分 |
| **报告输出** | 各基金风格标签 + 漂移评分 + 风格变动历史 |
| **备注** | 需要额外数据源：持仓个股市值/估值数据（东方财富行业分类 API 可能不直接提供，需评估） |

#### F4：持仓集中度监控

| 需求 | 描述 |
|:-----|:------|
| **集中度指标** | 前 3 大、前 5 大、前 10 大持仓占基金净值比例 |
| **趋势对比** | 与历史缓存中的集中度数据对比，展示环比变化 |
| **突变预警** | 前 10 占比环比提升 > 10% → ⚠️ 关注；> 20% → 🔴 紧急 |
| **报告输出** | 基金维度：当前集中度 + 趋势方向 + 预警级别 |
| **数据来源** | 复用 `fetch_fund_holdings` + 新增 `fund_concentration_history` 缓存 |

### 2.2 非功能需求

| 维度 | 要求 |
|:-----|:------|
| **向后兼容** | 所有新增页签/章节只在新版报告出现，不修改现有页签布局 |
| **降级友好** | API 获取失败时显示「—」占位，不阻塞报告生成 |
| **缓存安全** | 新增缓存前缀注册到 registry.py，支持 TTL 和分组管理 |
| **测试覆盖** | 每项新增 API 必须有对应的 mock 单元测试 |
| **性能** | 基金经理/重合度/集中度数据在生成报告时按需获取，不增加基础菜单耗时 |
| **数据源依赖** | 基金经理数据仅依赖天天基金页面（已有 HTTP 客户端），不新增外部依赖 |

### 2.3 约束条件

- 不引入新的外部 API 数据源（仅依赖已有的天天基金/东方财富 API）
- 保持 HTML 模板 autoescape 安全策略
- 所有新增页签在「菜单 L（全系列完整版）」中包含，菜单 E/H/B 控制可选
- 风格漂移检测的估值数据尽量复用现有 API（东方财富行业分类 API 中的市值数据）

---

## 3. 详细技术设计

### 3.1 方案总览：五 Phase

```
+---------------------------------------------------------------------+
|  B 基金持仓深度分析                                                   |
+---------------------------------------------------------------------+
|  Phase B1: 基金元数据增强                         基础能力建设        |
|  Phase B2: 基金经理变更监控                       F1 实现            |
|  Phase B3: 持仓重合度矩阵                         F2 实现            |
|  Phase B4: 持仓集中度监控                         F4 实现            |
|  Phase B5: 基金风格漂移检测                       F3 实现            |
+---------------------------------------------------------------------+
```

依赖关系：Phase B1 → (B2, B3, B4, B5)，B2~B5 之间互相独立可并行。

### 3.2 Phase B1：基金元数据增强

#### 3.2.1 新增 API — 基金经理抓取

创建 `src/python/fetcher/fund_manager.py`：

```python
"""基金经理数据获取模块。

数据来源：fund.eastmoney.com/{code}.html（HTML 解析）
缓存前缀：fund_manager_
TTL：CACHE_DAILY（86400s）
"""

_CACHE_PREFIX = "fund_manager_"

def fetch_fund_manager(code: str) -> dict[str, Any] | None:
    """获取基金经理信息。

    解析基金主页 HTML 中的"基金经理"行，提取：
      - manager_name: str      当前基金经理姓名
      - start_date: str        任职起始日（YYYY-MM-DD）
      - tenure_days: int       任职天数
      - history: list[dict]    历任基金经理 [{name, start_date, end_date, tenure_days}]

    返回字典，解析失败返回 None。
    """
```

**HTML 解析策略**：

目标页面 `https://fund.eastmoney.com/{code}.html` 中的基金经理信息有两种存在形式：

1. **基金概要表格**（优先）：`<div class="infoOfFund">` 中的基金经理行
2. **基金档案页**（回退）：`https://fundf10.eastmoney.com/jjjl_{code}.html` 基金经理明细表

解析正则示例：
```python
# 方式1：基金概要页解析
pattern = r'基金经理[：:]\s*<.*?>(.*?)</a>'
manager_name = re.search(pattern, html)

# 方式2：档案页表格解析（回退）
# <table class="table">{name, 任职时间, 任职天数} 行
```

#### 3.2.2 新增 API — 基金概要元数据（可选增强）

扩展 `fetch_fund_rankings` 返回或新增独立函数 `fetch_fund_profile`：

| 字段 | 来源 | 说明 |
|:-----|:------|:------|
| `fund_size` | 天天基金页面 | 基金规模（亿元） |
| `fund_company` | 天天基金页面 | 基金公司名称 |
| `establish_date` | 天天基金页面 | 成立日期 |
| `fund_type_detail` | 天天基金主页 meta | 详细类型（如"混合型-偏股""债券型-长债"）|

> **注意**：此 Phase 先实现基金经理解析（核心需求），元数据增强列为可选附加。

#### 3.2.3 缓存注册

```python
# registry.py 新增
DataModuleDef("基金经理", "fund_manager",
              cache_prefixes=("fund_manager_",),
              cache_ttl=CACHE_DAILY,
              cache_groups=("refresh",)),
DataModuleDef("持仓重合度", "fund_overlap",
              cache_prefixes=("fund_overlap_",),
              cache_ttl=CACHE_WEEKLY,
              cache_groups=("refresh",)),
DataModuleDef("基金集中度历史", "fund_concentration",
              cache_prefixes=("fund_concentration_",),
              cache_ttl=CACHE_MONTHLY),  # 无 cache_group，手动管理
```

### 3.3 Phase B2：基金经理变更监控

#### 3.3.1 变更检测引擎

创建 `src/python/report/fund_manager_analysis.py`：

```python
CACHE_PREFIX_MANAGER = "fund_manager_"
CACHE_PREFIX_HISTORY = "fund_manager_history_"  # 历史快照缓存

def detect_manager_changes(holdings: list[Holding]) -> list[dict]:
    """检测持仓中所有基金的基金经理变更。

    对每只基金：
    1. 获取当前基金经理信息（fetch_fund_manager）
    2. 与历史快照比较任职起始日
    3. 判定变更时段：1月内/3月内/6月内/无变更

    Returns:
        [{code, name, current_manager, start_date, tenure_days,
          changed_1m: bool, changed_3m: bool, changed_6m: bool,
          alert_level: "紧急"/"关注"/"正常"}]
    """

def _compare_with_history(code: str, current: dict) -> dict:
    """与历史快照对比，判断变更时段。

    历史快照格式：{code: {last_manager, last_check_date, ...}}
    存储在 fund_manager_history_{fingerprint}.json
    """
```

#### 3.3.2 变更时段判定规则

```
changed_1m  = 任职起始日 < 30 天前 AND 历史快照中经理姓名 != 当前姓名
changed_3m  = 任职起始日 < 90 天前 AND 历史快照中经理姓名 != 当前姓名
changed_6m  = 任职起始日 < 180 天前 AND 历史快照中经理姓名 != 当前姓名

预警级别:
  changed_1m → 🔴 紧急
  changed_3m → ⚠️ 关注
  changed_6m → ⚠️ 关注
  其他       → ✅ 正常

对于首次运行（无历史快照），仅显示当前经理信息，不输出变更状态（标记"首检"）。
历史快照在每次分析后更新。
```

#### 3.3.3 报告输出

**Excel 新页签 N.1 基金经理变更监控：**

| 列 | 说明 |
|:---|:------|
| 基金名称 | 基金名称 |
| 基金代码 | 6 位代码 |
| 当前基金经理 | 姓名 + 任职起始日 |
| 任职天数 | 自任职起始日至今 |
| 1月内变更 | ✅ 否 / 🔴 是 |
| 3月内变更 | ✅ 否 / ⚠️ 是 |
| 6月内变更 | ✅ 否 / ⚠️ 是 |
| 预警级别 | 🔴 紧急 / ⚠️ 关注 / ✅ 正常 / 📋 首检 |

**HTML 新章节：**
- 表格展示，预警级别条件着色
- 顶部摘要：高风险基金数 / 总基金数

#### 3.3.4 缓存策略

```
fund_manager_{code}.json          → TTL: 1天（API 数据，加入 refresh 分组）
fund_manager_history_.json.gz     → TTL: 永久（指纹驱动，无 cache_group）
```

### 3.4 Phase B3：持仓重合度矩阵

#### 3.4.1 重合度计算引擎

创建 `src/python/report/fund_overlap.py`：

```python
def compute_overlap_matrix(fund_holdings: dict[str, list[dict]]) -> dict:
    """计算持有基金两两之间的持仓重合度。

    Args:
        fund_holdings: {fund_code: [{name, code, ratio}, ...]}
                        取自 fetch_fund_holdings（已缓存）

    Returns:
        {
            "funds": [fund_code, ...],          # 基金代码列表（矩阵行列）
            "matrix": [[overlap_pct, ...], ...], # n x n 对称矩阵
            "pairs": [                           # 所有配对（按重叠度降序）
                {"fund_a": code, "fund_b": code,
                 "common_count": int,            # 共同标的数
                 "jaccard": float,               # Jaccard 系数
                 "overlap_mv_pct": float,        # 共同标的穿透市值占比
                 "common_stocks": [name, ...]},  # 共同标的名称列表
                ...
            ]
        }
    """

def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard 相似系数：|A∩B| / |A∪B|"""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _overlap_ratio(set_a: set, set_b: set) -> float:
    """重叠比例：|A∩B| / min(|A|, |B|)"""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / min(len(set_a), len(set_b))
```

**矩阵元素定义**：矩阵 `M[i][j]` 取 `max(jaccard, overlap_ratio)`，保证"一个基金是另一个的子集"时仍能反映高重叠。

#### 3.4.2 矩阵可视化

**Excel 新页签 N.2 持仓重合度矩阵：**

```
        基金A    基金B    基金C
基金A    100%     35%     12%
基金B     35%    100%      8%
基金C     12%      8%    100%
```

- 对角线 100%（自身重叠）
- 条件格式热力图：>50% 红色、30-50% 橙色、15-30% 黄色、<15% 默认
- 矩阵下方列表：按重叠度降序排列的 TOP 配对 + 共同标的明细

**HTML 章节：**
- CSS 条件着色矩阵表
- 顶部标注"最高重叠对"高亮
- 共同标的名称列表可展开

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
          prev_top10_pct,                  # 上期集中度（来自历史缓存）
          change_pct,                      # 环比变化
          alert_level}]                    # 预警/关注/正常
    """

_SNAPSHOT_KEY = "fund_concentration_history"

def _load_history_snapshot() -> dict:
    """读取历史集中度快照。格式：{code: {top10_pct, check_date, ...}}"""

def _save_history_snapshot(current: list[dict]):
    """保存本次集中度数据到历史快照。"""
```

#### 3.5.2 变更检测逻辑

```
top10_pct 环比变化 > +20% → 🔴 紧急  （持仓显著集中化）
top10_pct 环比变化 > +10% → ⚠️ 关注
top10_pct 当前 > 80%      → ⚠️ 关注  （高度集中阈值）
其他                       → ✅ 正常
```

#### 3.5.3 报告输出

**Excel 新页签 N.3 持仓集中度监控：**

| 列 | 说明 |
|:---|:------|
| 基金名称 | 名称 |
| 代码 | 6 位 |
| 类型 | QDII/ETF/联接/债券/主动 |
| 前3占比 | Top3 集中度 % |
| 前5占比 | Top5 集中度 % |
| 前10占比 | Top10 集中度 % |
| 上期前10占比 | 历史对照（有数据时显示）|
| 环比变化 | 百分点变化 + 方向箭头 |
| 预警级别 | 🔴 / ⚠️ / ✅ |

**HTML 新章节：**
- 表格 + 预警着色
- 顶部汇总：高风险基金数

#### 3.5.4 缓存策略

```
fund_concentration_history.json.gz → TTL: 永久（快照，自动保留历次）
fund_concentration_{code}.json     → TTL: 7天
```

### 3.6 Phase B5：基金风格漂移检测

#### 3.6.1 风格判定模型

> **注意**：本 Phase 依赖外部数据源对持仓个股的市值规模分类和估值分类能力。
> 可选方案 A（推荐）：利用东方财富行业分类 API 中的流通市值数据 + PE/PB 指标。
> 可选方案 B（降级）：使用持仓穿透中的股票代码，按代码段/市值区间做近似归类。

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

    1. 获取每只持仓个股的流通市值（东方财富 API）
    2. 市值规模划分：>500亿=大盘, 100-500亿=中盘, <100亿=小盘
    3. 估值倾向划分：PE < 15 x 行业平均PE = 价值型,
                    PE > 20 x 行业平均PE = 成长型
                    PE 在中间区间 = 混合型
    4. 按持仓市值加权得最终风格标签

    Returns:
        风格标签名称（如"大盘成长"），数据不足返回"--"
    """

def detect_style_drift(code: str, current_style: str) -> dict:
    """检测风格漂移。

    与历史风格快照对比：
    - 风格跨一格（如大盘成长→大盘混合）：轻度漂移
    - 风格跨两格（如大盘成长→中盘成长）：中度漂移
    - 风格跨三格+（如大盘价值→小盘成长）：严重漂移

    Returns:
        {code, name, current_style, prev_style, drift_level, drift_score}
    """
```

#### 3.6.2 数据源依赖评估

| 所需数据 | 现有 API | 备注 |
|:---------|:---------|:------|
| 持仓个股市值（流通市值/总市值） | 东方财富 push2（行业分类 API） | 需验证是否在返回字段中 |
| 个股 PE/PB | 同一 API | 可能不在行业接口中，需用 akshare `stock_profile_em` |
| 历史风格快照 | 无（需新增） | 与集中度共用快照机制 |

**降级方案 B**（外部数据不可行时）：
```python
def _estimate_style_by_code(code: str) -> str:
    \"\"\"按代码前缀粗略估算风格。\"\"\"
    if code.startswith("688") or code.startswith("3"):
        return "小盘成长"
    elif code.startswith("002") or code.startswith("600"):
        return "中盘混合"
    elif code.startswith("000") or code.startswith("601"):
        return "大盘混合"
    else:
        return "--"
```

降级方案在报告中标注"估算风格（基于代码段）"，不输出漂移评分。

#### 3.6.3 报告输出

**Excel 新页签 N.4 基金风格分析：**

| 列 | 说明 |
|:---|:------|
| 基金名称 | 名称 |
| 代码 | 6 位 |
| 当前风格 | 六宫格标签（大盘成长/...）或降级版"估算风格" |
| 上期风格 | 历史风格（有数据时显示） |
| 漂移评分 | 0-10（0=无漂移，10=严重），降级方案隐藏此列 |
| 漂移等级 | 无/轻度/中度/严重 |
| 备注 | 数据来源、是否降级标注 |

---

## 4. Phase 目标与回退

### Phase B1：基金元数据增强

| 维度 | 内容 |
|:-----|:------|
| **目标** | 成功从天天基金页面解析基金经理姓名+任职起始日；新建 `fetcher/fund_manager.py`；在 registry.py 注册新的缓存类型 |
| **成功标志** | `pytest src/test/ -k "fund_manager"` 全部通过；手动测试 `fetch_fund_manager("110011")` 返回正确数据 |
| **失败回退** | 解析失败 → 降级显示「—」；`git revert` 该 Phase commit |
| **进入下一 Phase 前提** | 至少 3 只基金的基金经理解析测试通过 |

### Phase B2：基金经理变更监控

| 维度 | 内容 |
|:-----|:------|
| **目标** | Excel 页签 + HTML 章节输出基金经理信息与变更状态；变更检测逻辑覆盖 1月/3月/6月窗口 |
| **成功标志** | 报告包含 N.1 页签/章节；变更检测与预期一致（mock 测试覆盖变更/未变更两种场景）|
| **失败回退** | 检测逻辑错误 → 回到 B1 阶段的数据读取模式，不输出变更列；`git revert` 该 commit |
| **进入下一 Phase 前提** | B2 场景测试通过 |

### Phase B3：持仓重合度矩阵

| 维度 | 内容 |
|:-----|:------|
| **目标** | 两两基金 Jaccard 相似度 + 重叠市值占比正确计算；Excel 热力图矩阵 + HTML 表格渲染正确 |
| **成功标志** | 持股中有 2 只基金持有同一股票时，矩阵对应单元格 > 0；3只基金 x 3只基金矩阵生成正确 |
| **失败回退** | 计算逻辑偏差 → 仅输出配对列表（降级），不渲染矩阵；`git revert` B3 commit |
| **进入下一 Phase 前提** | B3 单元测试 + 场景测试通过 |

### Phase B4：持仓集中度监控

| 维度 | 内容 |
|:-----|:------|
| **目标** | 正确计算前3/5/10持仓占比；历史快照存储与读取正确；环比变化+预警逻辑准确 |
| **成功标志** | 手动构造数据验证：前3/5/10占比计算与预期一致；预警触发逻辑正确（mock 测试）|
| **失败回退** | 快照机制有 bug → 仅输出当期集中度（无趋势），不输出预警列；`git revert` B4 commit |
| **进入下一 Phase 前提** | B4 测试通过 |

### Phase B5：基金风格漂移检测

| 维度 | 内容 |
|:-----|:------|
| **目标** | 基于持仓穿透数据实现风格判定；如果外部市值数据不可用，降级为代码段大致归类 |
| **成功标志** | 至少 50% 的主动基金能输出风格标签；漂移检测逻辑与手动分析一致 |
| **失败回退** | 外部数据不可靠 → 降级为"估算风格"模式，不输出漂移评分；`git revert` B5 commit |
| **进入下一 Phase 前提** | B5 核心逻辑验证通过 |

### 全迭代最终目标

| 指标 | 当前 | 目标 |
|:-----|:----:|:----:|
| 基金经理变更监控 | ❌ 无 | ✅ 页签 N.1 |
| 持仓重合度矩阵 | ❌ 无 | ✅ 页签 N.2 |
| 持仓集中度监控 | ❌ 无 | ✅ 页签 N.3 |
| 基金风格漂移检测 | ❌ 无 | ✅ 页签 N.4 |
| 新增报告页签数 | 12 个 | 16 个 |
| 新增测试项 | — | >= 90 项 |
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
| `src/python/report/fund_overlap_sheet.py` | 持仓重合度矩阵 Excel 写入 | B3 |
| `src/python/report/fund_concentration.py` | 持仓集中度计算+趋势 | B4 |
| `src/python/report/fund_concentration_sheet.py` | 持仓集中度 Excel 写入 | B4 |
| `src/python/report/fund_style_analysis.py` | 基金风格判定+漂移检测 | B5 |
| `src/python/report/fund_style_sheet.py` | 基金风格分析 Excel 写入 | B5 |

### 5.2 新增测试文件

| 文件 | 覆盖内容 | 预期项数 |
|:-----|:---------|:--------:|
| `src/test/unit/fetcher/test_fund_manager.py` | 基金经理解析/超时/结构变化 | ~15 |
| `src/test/unit/report/test_fund_manager_analysis.py` | 变更检测/缓存/预警 | ~25 |
| `src/test/unit/report/test_fund_overlap.py` | Jaccard 计算/矩阵生成/配对 | ~20 |
| `src/test/unit/report/test_fund_concentration.py` | 集中度计算/快照/预警 | ~18 |
| `src/test/unit/report/test_fund_style_analysis.py` | 风格判定/漂移检测（含降级）| ~17 |
| `src/test/scenario/test_fund_deep_analysis.py` | 端到端场景（含报告渲染）| ~10 |
| 合计 | | ~105 |

### 5.3 修改现有文件

| 文件 | 变更 |
|:-----|:------|
| `src/python/report/excel_generator.py` | 追加 N.1~N.4 页签写入调用 |
| `src/python/report/html_writer.py` | 追加 N.1~N.4 HTML 数据与渲染 |
| `src/python/report/html_builders.py` | 新增各模块的数据构建函数 |
| `src/python/tmpl/report_template.html` | 新增 4 个 Jinja2 模板块 |
| `src/python/registry.py` | 新增 4 个 DataModuleDef |
| `src/python/tui_handlers.py` | 缓存管理菜单同步 |
| `src/python/tui_menu.py` | 缓存菜单描述同步 |
| `docs-stm/managements/requirements.md` | 新增 B 系列功能说明 |
| `docs-stm/managements/test-coverage.md` | 新增测试项统计 |
| `docs-stm/manuals/datasource-and-folders.md` | 目录树同步 |
| `docs-stm/managements/plan.md` | B 状态更新 |
| `docs-stm/managements/changelog.md` | 变更记录 |

---

## 6. 实施步骤（拆细为 17 个原子步）

### 6.1 Phase B1：元数据增强（4 步）

```
Step B1-1 → Step B1-2 → Step B1-3 → Step B1-4
(基金经理API)  (单元测试)    (registry注册)  (数据验证)
```

#### Step B1-1：创建 `fetcher/fund_manager.py`

| 字段 | 值 |
|:-----|:----|
| **目标** | 实现 `fetch_fund_manager(code)`，正确解析天天基金页面的基金经理姓名+任职起始日 |
| **文件** | 新建 `src/python/fetcher/fund_manager.py` |
| **操作** | (1) 实现 HTML 解析 `_parse_manager_from_main_page(html)` — 优先方案<br>(2) 实现回退方案 `_parse_manager_from_archive_page(code)` — 基金档案页<br>(3) 实现缓存读写（复用 cache.py 接口，前缀 `fund_manager_`）<br>(4) `__init__.py` 更新导出 |
| **验证** | `from src.python.fetcher.fund_manager import fetch_fund_manager; fetch_fund_manager("110011")` 返回含 manager_name/start_date/tenure_days 的字典（可联网时）|
| **预期产出** | commit: "feat: 基金经理数据获取模块 — fund_manager.py" |
| **回滚** | `git revert` 该 commit；删除新增文件 |

#### Step B1-2：基金经理 API 单元测试

| 字段 | 值 |
|:-----|:----|
| **目标** | mock 天天基金 HTML 响应，覆盖正常解析、页面结构变化、网络超时 3 种场景 |
| **文件** | 新建 `src/test/unit/fetcher/test_fund_manager.py` |
| **操作** | (1) 录制一个真实基金页面 HTML 存为测试 fixture<br>(2) mock `make_http_client` 返回可控的 HTML<br>(3) mock 超时场景验证 None 返回<br>(4) 标记 `@pytest.mark.unit_providers` |
| **验证** | `pytest src/test/ -m "unit_providers" -k "fund_manager"` 全部通过 |
| **预期产出** | commit: "test: 基金经理 API 单元测试 — 3 场景覆盖" |
| **回滚** | `git revert` 该 commit；删除测试文件 |

#### Step B1-3：registry.py 缓存注册

| 字段 | 值 |
|:-----|:----|
| **目标** | 在 registry 注册基金经理/重合度/集中度/风格 4 个新 DataModuleDef |
| **文件** | `src/python/registry.py` |
| **操作** | (1) 新增 4 个 `DataModuleDef` 条目（详见 §5.2）<br>(2) 在 registry test 中验证新条目可查询 |
| **验证** | `pytest src/test/ -m "unit_core" -k "registry"` 全部通过 |
| **预期产出** | commit: "feat: registry 注册 4 个基金分析数据模块" |
| **回滚** | `git revert` 该 commit；注释掉新增条目 |

#### Step B1-4：数据验证与集成测试

| 字段 | 值 |
|:-----|:----|
| **目标** | 基金经理 API 在端到端数据流中可用，缓存策略正常工作 |
| **操作** | (1) 运行 `python src/python/main.py` 验证缓存刷新菜单 [1] 覆盖新增 `fund_manager_` 缓存<br>(2) 验证 `cache.py` 清理功能可识别新前缀<br>(3) mock 集成测试 |
| **验证** | 菜单 [1] 执行后 `data/cache/fund_manager_*.json` 文件存在 |
| **预期产出** | 集成确认，无新 commit（复用已有 commit）|
| **回滚** | 缓存注册错误 → 回退 B1-3 |

---

### 6.2 Phase B2：基金经理变更监控（4 步）

```
Step B2-1 → Step B2-2 → Step B2-3 → Step B2-4
(检测引擎)   (Excel页签)   (HTML章节)   (测试)
```

#### Step B2-1：变更检测引擎

| 字段 | 值 |
|:-----|:----|
| **目标** | `detect_manager_changes()` 对持仓基金遍历，输出变更状态和预警级别 |
| **文件** | 新建 `src/python/report/fund_manager_analysis.py` |
| **操作** | (1) 实现 `detect_manager_changes(holdings)` 遍历基金列表<br>(2) 实现 `_compare_with_history()` 历史快照对比<br>(3) 实现变更时段判定逻辑（1月/3月/6月）<br>(4) 实现预警级别判定 |
| **验证** | 手动构造含变更/未变更的数据，检测结果与预期一致 |
| **预期产出** | commit: "feat: 基金经理变更检测引擎 — fund_manager_analysis.py" |
| **回滚** | `git revert` 该 commit |

#### Step B2-2：Excel 页签写入

| 字段 | 值 |
|:-----|:----|
| **目标** | 新增 Excel 页签「N.1 基金经理变更监控」|
| **文件** | 新建 `src/python/report/fund_manager_sheet.py`，修改 `excel_generator.py` |
| **操作** | (1) 新建 `fund_manager_sheet.py` — 使用现有 `write_title_row/write_header_row/write_data_row` 模式<br>(2) Excel 条件格式：红色字体 橙色字体<br>(3) `excel_generator.py` 中 `write_sheets()` 追加 N.1 页签 |
| **验证** | 菜单 B/L 生成报告后，Excel 包含 N.1 页签 |
| **预期产出** | commit: "feat: 基金经理变更监控 Excel 页签" |
| **回滚** | `git revert` 该 commit；excel_generator.py 恢复 |

#### Step B2-3：HTML 章节渲染

| 字段 | 值 |
|:-----|:----|
| **目标** | HTML 报告新增 N.1 章节 |
| **文件** | `src/python/report/html_writer.py`, `src/python/tmpl/report_template.html` |
| **操作** | (1) html_builders.py 新增 `_build_manager_analysis_data()`<br>(2) html_writer.py 追加章节数据传递<br>(3) report_template.html 新增 table + 条件着色 |
| **验证** | 菜单 L 生成后，HTML 包含 N.1 章节 |
| **预期产出** | commit: "feat: 基金经理变更监控 HTML 章节" |
| **回滚** | `git revert` 该 commit |

#### Step B2-4：基金经理模块测试

| 字段 | 值 |
|:-----|:----|
| **目标** | ~25 项单元测试覆盖变更检测/缓存/报告输出 |
| **文件** | 新建 `src/test/unit/report/test_fund_manager_analysis.py` |
| **操作** | (1) mock `fetch_fund_manager` 返回可控数据<br>(2) mock 历史快照不同场景<br>(3) Excel 页签写入 mock 验证列数/数据正确性<br>(4) 标记 `@pytest.mark.unit_report` |
| **验证** | `pytest src/test/ -m "unit_report" -k "fund_manager"` 全部通过 |
| **预期产出** | commit: "test: 基金经理模块 25 项单元测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.3 Phase B3：持仓重合度矩阵（4 步）

```
Step B3-1 → Step B3-2 → Step B3-3 → Step B3-4
(计算引擎)   (矩阵渲染)   (报告输出)   (测试)
```

#### Step B3-1：重合度计算引擎

| 字段 | 值 |
|:-----|:----|
| **目标** | `compute_overlap_matrix()` 正确计算 Jaccard + 重叠市值 + 配对排序 |
| **文件** | 新建 `src/python/report/fund_overlap.py` |
| **操作** | (1) 实现 `_jaccard_similarity(set, set)`<br>(2) 实现 `_overlap_ratio(set, set)`<br>(3) 实现 `compute_overlap_matrix(fund_holdings)` 生成对称矩阵<br>(4) 复用 `fetch_fund_holdings` 已有的缓存数据 |
| **验证** | 手动构造 3 只基金数据（A∩B=2, B∩C=1, A∩C=0）→ 矩阵正确 |
| **预期产出** | commit: "feat: 持仓重合度矩阵计算引擎" |
| **回滚** | `git revert` 该 commit |

#### Step B3-2：矩阵渲染辅助

| 字段 | 值 |
|:-----|:----|
| **目标** | 矩阵转置 + 热力图条件渲染辅助函数 |
| **文件** | `src/python/report/fund_overlap.py`（追加） |
| **操作** | (1) 实现矩阵数据 → Excel 格式转换（含热力图阈值分类）<br>(2) 实现配对排序 + TOP N 筛选 |
| **验证** | 转换函数输入 mock 矩阵，输出 Excel 可读的二维列表 |
| **预期产出** | 与 B3-1 同一 commit |
| **回滚** | 与 B3-1 同 |

#### Step B3-3：报告输出（Excel + HTML）

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 页签「N.2 持仓重合度矩阵」+ HTML 章节 |
| **文件** | 新建 `src/python/report/fund_overlap_sheet.py`；修改 `excel_generator.py`、`html_writer.py`、`report_template.html` |
| **操作** | (1) Excel：矩阵页签 + 条件热力图 + 底部配对明细<br>(2) HTML：矩阵表格 + CSS 着色 + 最高重叠对高亮 |
| **验证** | 含多只基金的报告包含重合度矩阵 |
| **预期产出** | commit: "feat: 持仓重合度矩阵 Excel+HTML 报告输出" |
| **回滚** | `git revert` 该 commit；excel_generator.py 和 html_writer.py 恢复 |

#### Step B3-4：重合度模块测试

| 字段 | 值 |
|:-----|:----|
| **目标** | ~20 项单元测试覆盖 Jaccard/矩阵/渲染 |
| **文件** | 新建 `src/test/unit/report/test_fund_overlap.py` |
| **操作** | (1) mock 基金持仓数据<br>(2) 验证 Jaccard/overlap_ratio 计算<br>(3) 验证矩阵对称性（M[i][j] = M[j][i]）<br>(4) 标记 `@pytest.mark.unit_report` |
| **验证** | `pytest src/test/ -m "unit_report" -k "overlap"` 全部通过 |
| **预期产出** | commit: "test: 持仓重合度模块 20 项单元测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.4 Phase B4：持仓集中度监控（3 步）

#### Step B4-1：集中度计算 + 快照机制

| 字段 | 值 |
|:-----|:----|
| **目标** | `compute_concentration()` 正确计算前3/5/10集中度 + 历史快照读写 |
| **文件** | 新建 `src/python/report/fund_concentration.py` |
| **操作** | (1) 实现集中度计算（复用 `fetch_fund_holdings` 返回的 ratio 字段）<br>(2) 实现历史快照存储（json.gz，指纹驱动）<br>(3) 实现环比变化计算 + 预警判定 |
| **验证** | 手动构造 fund_holdings 验证前3/5/10占比 |
| **预期产出** | commit: "feat: 持仓集中度计算 + 历史快照" |
| **回滚** | `git revert` 该 commit |

#### Step B4-2：报告输出（Excel + HTML）

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 页签「N.3 持仓集中度监控」+ HTML 章节 |
| **文件** | 新建 `src/python/report/fund_concentration_sheet.py`；修改 `excel_generator.py`、`html_writer.py`、`report_template.html` |
| **操作** | (1) Excel：表格 + 预警条件着色 + 趋势方向箭头<br>(2) HTML：章节渲染 + CSS 预警标签 |
| **验证** | 报告包含集中度页签/章节 |
| **预期产出** | commit: "feat: 持仓集中度监控 Excel+HTML 报告输出" |
| **回滚** | `git revert` 该 commit |

#### Step B4-3：集中度测试

| 字段 | 值 |
|:-----|:----|
| **目标** | ~18 项单元测试覆盖计算/快照/预警 |
| **文件** | 新建 `src/test/unit/report/test_fund_concentration.py` |
| **操作** | (1) 构造 3 种集中度水平的数据<br>(2) mock 历史快照验证环比<br>(3) 验证预警触发逻辑<br>(4) 标记 `@pytest.mark.unit_report` |
| **验证** | `pytest src/test/ -m "unit_report" -k "concentration"` 全部通过 |
| **预期产出** | commit: "test: 持仓集中度模块 18 项单元测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.5 Phase B5：基金风格漂移检测（2 步）

> **前置条件**：先验证东方财富行业分类 API 是否返回市值数据。
> 如不可行，降级为代码段近似分类。

#### Step B5-1：风格判定模型

| 字段 | 值 |
|:-----|:----|
| **目标** | 基于穿透持仓数据输出风格标签（含降级方案） |
| **文件** | 新建 `src/python/report/fund_style_analysis.py` |
| **操作** | (1) 评估东方财富 API 是否提供持仓个股市值数据<br>(2) 可行 → 实现基于市值+估值的风格判定<br>(3) 不可行 → 实现基于代码段的"大致风格"降级方案<br>(4) 实现 `detect_style_drift()` 跨期对比 |
| **验证** | 至少 50% 持仓基金能输出风格标签 |
| **预期产出** | commit: "feat: 基金风格判定 + 漂移检测（含降级方案）" |
| **回滚** | `git revert` 该 commit |

#### Step B5-2：报告输出 + 测试

| 字段 | 值 |
|:-----|:----|
| **目标** | Excel 页签「N.4 基金风格分析」+ HTML 章节 + ~17 项单元测试 |
| **文件** | 新建 `src/python/report/fund_style_sheet.py`；修改 `excel_generator.py`、`html_writer.py`、`report_template.html`；新建 `src/test/unit/report/test_fund_style_analysis.py` |
| **操作** | (1) Excel 页签写入<br>(2) HTML 章节渲染<br>(3) 单元测试覆盖（含降级方案）|
| **验证** | `pytest src/test/ -m "unit_report" -k "fund_style"` 全部通过 |
| **预期产出** | commit: "feat: 基金风格分析报告输出 + 测试" |
| **回滚** | `git revert` 该 commit |

---

### 6.6 最终验证（1 步）

#### Step E：全量回归 + 场景测试

| 字段 | 值 |
|:-----|:----|
| **目标** | 全部 ~90 新增项 + 原有 regression 全部通过 |
| **操作** | (1) 运行 `python test_runner.py --mode unit` — 确认 report 标记项数不降<br>(2) 运行 `python test_runner.py --mode regression` — 场景 0 failed<br>(3) 菜单 B/L 生成报告确认 4 个新页签/章节存在 |
| **验证** | (1) `unit` 0 failed<br>(2) `regression` 0 failed<br>(3) 生成的报告文件含 N.1~N.4 四个新增页签 |
| **预期产出** | commit: "docs: B 迭代完成 — 基金深度分析 4 模块上线" |
| **回滚** | 任一项 failed → 追踪到对应 Phase 修复 |

---

## 7. 实施步骤总览

```
                        Phase B1                  Phase B2                  Phase B3
Week 1                                          Week 2                                         Week 3
+------+------+--------+------+------+------+------+------+------+------+------+------+------+------+------+
|B1-1  |B1-2  |B1-3~4 |B2-1  |B2-2  |B2-3  |B2-4  |B3-1  |B3-2  |B3-3  |B3-4  |B4-1  |B4-2  |B4-3  |B5-1  |
|经理  |经理  |注册表+ |变更  |Excel |HTML  |测试  |重叠  |渲染  |报告  |测试  |集中度|集中度|集中度|风格  |
|API   |UT    |验证   |引擎  |页签  |章节  |      |引擎  |辅助  |输出  |      |计算  |报告  |测试  |判定  |
+------+------+--------+------+------+------+------+------+------+------+------+------+------+------+------+
| B5-2 |  E   |       |      |      |      |      |      |      |      |      |      |      |      |      |
|风格  |全量  |       |      |      |      |      |      |      |      |      |      |      |      |      |
|报告+ |回归  |       |      |      |      |      |      |      |      |      |      |      |      |      |
|测试  |      |       |      |      |      |      |      |      |      |      |      |      |      |      |
+------+------+--------+------+------+------+------+------+------+------+------+------+------+------+------+
   ^Phase B1        ^Phase B2          ^Phase B3             ^Phase B4            ^Phase B5
  元数据就绪      经理监控上线       重叠矩阵上线          集中度上线           风格上线
```

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| 天天基金页面结构变更（基金经理解析失败） | 中 | 高 | 两层解析策略（主页→档案页回退）；解析失败降级「—」不阻塞；单元测试锁定当前结构 |
| 东方财富行业分类 API 不提供市值/估值数据（风格判定失效）| 中 | 中 | Phase B5 预研先行验证 API 返回值；不可行则使用降级方案（代码段近似分类）|
| 新增 4 个报告页签导致报告生成时间增加 | 中 | 低 | 所有新增数据复用已有缓存（fund_hold_\*），不产生额外 HTTP 请求 |
| 持仓重合度矩阵渲染大量基金时 O(n^2) 膨胀 | 低 | 低 | 仅对持仓中的基金进行计算（通常 3-10 只）；设上限 >= 2 只基金才渲染矩阵 |
| 历史快照文件膨胀（集中度/风格每期追加）| 低 | 低 | 使用 .json.gz 压缩；仅保留最新 2 期用于环比；使用指纹驱动，持仓不变不追加 |
| 新增缓存前缀与现有菜单 [1][2] 清理逻辑不一致 | 低 | 中 | registry.py 中集中度/风格快照不加入 refresh 分组；基金经理数据加入 refresh 组 |
| Excel 页签编号冲突（当前 12 页签 → 新页签以 N. 前缀）| 低 | 中 | 使用 N.1~N.4 编号，不重新编号已有 1-12 页签，向后兼容 |

---

## 9. 变更文件清单

### 9.1 新增文件

| 文件 | Phase | 行数预估 |
|:-----|:------|:--------:|
| `src/python/fetcher/fund_manager.py` | B1 | ~150 |
| `src/python/report/fund_manager_analysis.py` | B2 | ~200 |
| `src/python/report/fund_manager_sheet.py` | B2 | ~120 |
| `src/python/report/fund_overlap.py` | B3 | ~200 |
| `src/python/report/fund_overlap_sheet.py` | B3 | ~180 |
| `src/python/report/fund_concentration.py` | B4 | ~150 |
| `src/python/report/fund_concentration_sheet.py` | B4 | ~120 |
| `src/python/report/fund_style_analysis.py` | B5 | ~180 |
| `src/python/report/fund_style_sheet.py` | B5 | ~120 |
| `src/test/unit/fetcher/test_fund_manager.py` | B1 | ~80 |
| `src/test/unit/report/test_fund_manager_analysis.py` | B2 | ~120 |
| `src/test/unit/report/test_fund_overlap.py` | B3 | ~100 |
| `src/test/unit/report/test_fund_concentration.py` | B4 | ~90 |
| `src/test/unit/report/test_fund_style_analysis.py` | B5 | ~80 |
| `src/test/scenario/test_fund_deep_analysis.py` | E | ~100 |

### 9.2 修改文件

| 文件 | 变更内容 |
|:-----|:---------|
| `src/python/registry.py` | 新增 4 个 DataModuleDef |
| `src/python/report/excel_generator.py` | 追加 N.1~N.4 页签写入调用 |
| `src/python/report/html_writer.py` | 追加 N.1~N.4 HTML 数据与渲染 |
| `src/python/report/html_builders.py` | 新增各模块的数据构建函数 |
| `src/python/tmpl/report_template.html` | 新增 4 个 Jinja2 模板块 |
| `src/python/tui_handlers.py` | 缓存管理菜单同步 |
| `src/python/tui_menu.py` | 缓存菜单描述同步 |
| `docs-stm/managements/requirements.md` | 新增 B 系列功能说明 |
| `docs-stm/managements/test-coverage.md` | 新增测试项统计 |
| `docs-stm/manuals/datasource-and-folders.md` | 目录树同步 |
| `docs-stm/managements/plan.md` | B 状态更新 |
| `docs-stm/managements/changelog.md` | 变更记录 |
