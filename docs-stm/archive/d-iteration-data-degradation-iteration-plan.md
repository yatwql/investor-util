# D 迭代：数据降级分层治理 — 精细化子迭代拆分

> 基于 Phase 0 设计文档 + 全量代码探索，按"小步交付、风险分层、可逆可测"原则，
> 将原 3 个 Phase（1800 行+一次性大改）拆分为 **10 个独立可提交/可回滚的子迭代**。

---

## 总体策略

```
原计划:
  Phase 1 (T2+T3) → Phase 2 (T4) → Phase 3 (审计)
  问题: 每个 Phase 涉及 10+ 文件、200+ 行改动，出问题要回滚一大片

新计划（10 步）:
  D-1:  静默异常日志补全
  D-2:  大粒度 try 拆分与代码去重
  D-3:  数据源状态追踪基础设施
  D-4:  穿透模块数据源状态接入
  D-5:  基金排名与指数降级标识接入
  D-6:  HTML 报告状态摘要渲染
  D-7a: B 系列模块空态占位
  D-7b: 新闻与预警模块空态占位
  D-8:  全链路回归基线锁定
  D-9:  文档同步

每个子迭代 = 1 次 commit ，出问题 git revert HEAD 即可。
```

> **设计变更 v2：** 新增"降级阈值控制"跨层设计（见下文）—— 修改 D-3 基础设施、D-4/D-5/D-7 调用方式及测试范围。D-1/D-2/D-6/D-9 不受影响。
> 合并入现有 10 步子迭代，不新增编号。

---

## 降级阈值控制（全局设计补充）

### 问题

当前 `_data_status` 设计的隐含假设是"一次失败就降级"——push2 偶尔抖一下 ℹ；Tencent 超时一次 ⚠。这将导致：

- **用户对降级标识脱敏**：满篇 ⚠/ℹ 等于没有 → 真正的持续故障被淹没
- **狼来了效应**：一次成功后的瞬态抖动就被降级，报告可信度下降

**用户直接诉求：** "别很容易就降级，也不能很长时间异常都不做降级，要控制好阈值"

### 方案：双信号降级决策

新增 `DegradationTracker` 类，每个数据源的降级决定 = **信号 1 OR 信号 2**。

**信号 1 — 连续失败次数（会话级）：**
同一会话内同一数据源连续失败超过层级阈值。成功后自动归零。

| 层级 | 阈值 | 说明 |
|:----:|:----:|:-----|
| T2 | 2 次 | 稳定源，应快速确认故障 |
| T3 | 3 次 | 不稳定源（push2），已知故障率高 |
| T4 | 1 次 | 非关键，一次失败即可降级 |

**信号 2 — 缓存陈旧度（跨会话级）：**
缓存最后成功写入至今超过层级容忍天数。无缓存时直接触发。

| 层级 | 容忍期限 | 说明 |
|:----:|:---------|:-----|
| T2 | 3 天 | 指数/排名数据不应超过 3 天过旧 |
| T3 | 14 天 | 行业分类变化极慢，2 周未更新应降级 |
| T4 | 14 天 | 非关键数据，14 天（两周）未更新则降级 — 与 T3 对齐（实际运行后确认 T4 非关键数据更新频率低，放宽容忍期长） |

**自适应调节（作用于信号 1 的阈值）：**

| 缓存状态 | T2 | T3 | T4 | 原因 |
|:---------|:--:|:--:|:--:|:-----|
| 新鲜（≤TTL）| 3 | 4 | 1 | 有昨日成功缓存，多给 1 次容忍 |
| 正常过期（TTL~3×TTL）| 2 | 3 | 1 | 基准值，标准场景 |
| 严重过期（>3×TTL）或无缓存| 1 | 2 | 1 | 缺乏可靠备份，更敏感 |

### 生效场景示意

| 场景 | 信号1（失败计数） | 信号2（缓存年龄） | 降级？ |
|:-----|:-----------------:|:-----------------:|:------:|
| Tencent 单次超时，缓存新鲜 | count=1, T2阈=3(TTL内+1) | 1h<3d | ❌ 不降级 ⇒ 用户无感知 |
| Tencent 连续 3 次超时（同会话）| count=3≥3 | 2h<3d | ⚠ 降级（信号1达标）|
| push2 抖 2 次，第 3 次成功 | count=0（自愈）| — | ❌ 恢复，用户从未看到 |
| 排名 API 连续 7 天不可用（每日1次）| count=1<T2阈=2 | 7d>3d | ⚠ 降级（信号2达标）|
| akshare 闪断 | count=1≥1(T4) | — | ℹ 降级（T4=立即）|
| 全新数据源（首次运行无缓存）| — | 无缓存 | ⚠ 降级（信号2直达）|

### 对子迭代的影响

| 子迭代 | 变更 |
|:-------|:-----|
| **D-3** | `data_status.py` 新增 `DegradationTracker` 类；`cache.py` 新增 `get_cache_age()` 公共函数 |
| **D-4** | penetration 模块调用 `tracker.record()` 替代直接设 `available=False`；需传 `cache_age` 参数 |
| **D-5** | performance/summary 模块同上；index.py `_source` 四路径不变 |
| **D-7a/b** | B 系列/news/预警模块：T4 源调用 `record()`，大多无缓存故直接使用信号1 |
| **D-8** | 新增阈值场景的 edge 测试（见具体章节修改） |
| **D-9** | 同步阈值设计到 `technical.md` |

> **设计决策：** 不引入跨会话持久化计数器（如将 fail_count 写入缓存），而是用缓存自身的 `_ts` 时间戳作为跨会话信号。原因：① 零额外状态维护，② `_ts` 是缓存系统已有字段，③ 避免 N 个数据源各自持久化计数器的复杂度。缓存时间戳 = 最后一次成功写入的时间，天然是跨会话信号。

---

## D-1 — 静默异常日志补全

### 做什么

代码里有些地方捕获异常后什么都不做（`except: pass` 或不记录日志），导致问题发生时不留下任何痕迹。D-1 给它们加上日志，但**不改返回值**。

```
注意：这不是"修复 bug"，而是"给 bug 装个监控"。
返回值不变，出错了该返回 -- 还是返回 --，只是现在会写一条日志。
```

### 改哪些文件（共 15 个文件，每处只加 1~2 行日志）

**第 1 批：原设计文档 Phase 3 审计清单的 5 处**

| 文件 | 行号 | 当前行为 | 改为 |
|:-----|:----:|:---------|:------|
| `report/category.py` | 128 | `except Exception: return "--"` 无日志 | 加 `logger.warning("[category] 股息率计算异常: %s", e)` |
| `report/html_builders.py` | 40 | `except Exception: return "--"` 无日志 | 加 `logger.warning("[html_builders] 股息率计算异常: %s", e)` |
| `report/fund_style_analysis.py` | 237 | `except Exception: logger.debug(...)` | debug → `logger.warning` |
| `report/fund_style_analysis.py` | 268 | `except Exception: logger.debug(...)` | debug → `logger.warning` |
| `fetcher/fund.py` | 160 | `except (KeyError, TypeError): pass` | 加 `logger.debug("[fund] 基准配置覆盖失败，使用默认值")` |

**第 2 批：代码探索发现的其余 8 处**

| 文件 | 行号 | 当前行为 | 改为 |
|:-----|:----:|:---------|:------|
| `fetcher/chain.py` | 42 | `except (KeyError, TypeError): pass` | 加 `logger.debug("[chain] preferred_provider 配置解析失败，使用默认链")` |
| `fetcher/price.py` | 111 | `except Exception: return True` 无视异常视作新鲜 | 加 `logger.warning("[price] _is_cache_fresh 校验异常，保守视作新鲜: %s", e)`；`return True` 不变 |
| `fetcher/industry.py` | 137 | `except Exception: continue` | 加 `logger.warning("[industry] 重试批量 %s 仍失败: %s", code, e)`；`continue` 不变 |
| `llm/api.py` | 332 | 超时不记录 | 加 `logger.debug("[llm/api] 请求超时: %s", e)` |
| `llm/api.py` | 334 | HTTP 错不记录 | 加 `logger.debug("[llm/api] HTTP 异常: %s", e)` |
| `llm/api.py` | 337 | 响应解析错不记录 | 加 `logger.warning("[llm/api] 响应解析失败: %s", e)` |
| `llm/generators.py` | 622 | h2 降级不记录 | 加 `logger.info("h2 包未安装，降级到 HTTP/1.1")` |
| `report/html_writer.py` | 810 | `except ImportError: pass` | 加 `logger.info("llm/session 模块未就绪，略过用量统计")` |

**第 2.5 批：设计文档 Phase 3 审计清单遗漏项（新增 1 处）**

| 文件 | 行号 | 当前行为 | 改为 |
|:-----|:----:|:---------|:------|
| `llm/generators.py` | 417 | `except ValueError: pass` | 加 `logger.warning("[llm] JSON 解码失败: %s", e)` |

> 设计文档 §6.1 审计清单第 7 项，上一轮 D-1 遗漏了此项，本轮补全。

**第 3 批：空数据无异常 + 降级原因追踪（新增 6 处）**

这些地方数据返回为空但没有抛异常，`_data_status` 标记为不可用时必须同步写日志说明原因。

| 文件 | 位置 | 触发条件 | 新增日志 |
|:-----|:----|:---------|:---------|
| `report/penetration.py` | `compute_penetration_top10` TOP10 汇总 | 天天基金持仓解析结果为空（`top10` 空列表） | `logger.warning("[penetration] 天天基金持仓解析结果为空，穿透表不可用")` |
| `report/fund_performance.py` | `write_fund_performance_sheet` 渲染排名列 | 天天基金排名 API 返回空列表（`rankings` 为空） | `logger.warning("[fund_performance] 天天基金排名接口返回空数据，排名列显示 --")` |
| `providers/news_aggregator.py` | 聚合函数入口 | 5 个新闻源全部返回空（非异常，正常响应但文章数为 0） | `logger.warning("[news] 5 个新闻源均返回空结果，新闻页签降级为占位")` |
| `report/early_warning.py` | 预警入口检查 | 上游新闻/资金流向数据全部为空 | `logger.info("[early_warning] 上游数据为空，预警模块跳过（非异常）")` |

| 文件 | 位置 | 触发条件 | 新增日志 |
|:-----|:----|:---------|:---------|
| `fetcher/index.py` | `fetch_indices` 主→备切换点 | 腾讯链路失败后启动新浪备用 | 现有 `logger.info("尝试新浪备用链路")` 改为 `logger.warning("[index] 腾讯链路失败（超时/空响应），降级至新浪备用")`（需增加具体失败原因传入）|
| `report/fund_performance.py` | 排名数据为空后 | 排名全 `--` 时用户无法得知原因 | 日志需细分：API 返回空 → `logger.warning("[fund_performance] 排名数据为空（API返回空响应）")`；API 异常 → `logger.warning("[fund_performance] 排名数据异常: %s", e)`（异常已在 D-1 第 1 批中加）|

### 验收标准

- [ ] grep `except.*pass` 或无日志的 `except`，13 处全覆盖（第 1 批 5 + 第 2 批 8），无遗漏
- [ ] 4 处"空数据无异常"路径（penetration 持仓空、perf 排名空、news 全源空、early_warning 上游空）均有日志写明具体原因
- [ ] 2 处"降级原因"路径（index 主→备降级、perf 排名空原因分类）日志均有具体失败原因
- [ ] 每处日志级别符合设计规范（§2.2.1 双通道协作规则）：数据获取失败用 `warning`，配置解析/降级用 `debug/info`，响应解析用 `warning`
- [ ] 每条日志都写明"为什么失败"，不写笼统的"数据不可用"——必须包含具体技术原因（超时/空响应/格式解析失败/熔断）
- [ ] 原有测试全通过——日志追加不改变返回值，不影响任何断言
- [ ] P0 门禁通过

### 不涉及

- **不改任何业务逻辑**
- **不改任何测试文件**（日志不影响测试断言）
- **不改返回值**
- **不改用户界面**

### 验证方法

```bash
python scripts/test_runner.py --mode regression   # P0 门禁：业务场景快速验证
pytest src/test/ -m "not edge"                     # 日志不影响任何断言
# 手动验证日志原因完备性：
grep -n "logger\.\(warning\|info\|debug\)" src/python/report/penetration.py | grep -c "不可用"
grep -n "logger\.\(warning\|info\|debug\)" src/python/report/fund_performance.py | grep -c "不可用"
# 每个不可用处应有对应原因说明
```

---

## D-2 — 大粒度 try 拆分与代码去重

### 做什么

当前有 4 处代码用一个 `try/except` 包了"拉数据 → 过滤 → 计算 → 写入页签"整个流程。这导致：

- 写入格式报错 → 日志显示"计算失败"（误导排查方向）
- 数据拉取报错 → 整个模块跳过，页面消失

同时有 1 处重复代码需要合并：
1. `_yield_text()` / `_calc_yield_text()` — 股息率公式重复

> **关于 `_load_dividend_data`：** 经代码核查，`_load_dividend_data()` 只存在于 `category.py:104`，`html_builders.py:68` 直接调用 `get_dividend_data()`（akshare 库函数），不存在函数级的重复。`penetration_sheet.py:71` 有同名不同实现的 `_load_dividend_data_safe()`，但两者调用的是同一个 akshare 函数，只是调用方不同——不合并更清晰。本步**只合 `_yield_text` 一处**。

### 改哪些文件（共 4 个文件）

**文件 1：`excel_generator.py`（行 296~413）**

改为：fetch/filter 放外面，compute 和 write 各归各 try。

涉及 4 个模块：
- 行 296~298：基金经理变更监控
- 行 341~343：持仓重合度矩阵
- 行 376~378：持仓集中度监控
- 行 411~413：基金风格分析

**文件 2+3：`category.py` + `html_builders.py`（去重）**

合并 `_yield_text()` / `_calc_yield_text()`。
category.py 导出公共函数 `calc_yield_text()`，html_builders.py import 复用。

### 验收标准

- [ ] `excel_generator.py` 中 4 处 B 系列大 try 已拆分：fetch/filter 在 try 外未改，compute 和 write 各有独立 try/except，异常日志能精确指出"计算失败"还是"写入失败"
- [ ] `category.py` 导出 `calc_yield_text()` 公共函数（合并 `_yield_text`/`_calc_yield_text` 公式）
- [ ] `html_builders.py` import 复用 `calc_yield_text()`，旧 `_calc_yield_text` 已删除
- [ ] 运行 `pytest src/test/unit/report/` 全 855 项通过（无回归）
- [ ] P0 + 场景测试全通过

### 不涉及

- **不改用户界面和报告内容**
- **不改页签顺序和可见性逻辑**
- **不改测试断言**
- **不改任何数据流方向**

### 验证方法

```bash
python scripts/test_runner.py --mode regression   # P0 门禁
pytest src/test/unit/report/                        # 855 项必须全通过
pytest src/test/scenario/                           # 端到端场景
```

---

## D-3 — 数据源状态追踪与降级阈值基础设施

### 做什么

后面 D-4~D-7 都需要两套基础能力：
1. 记录"哪个数据源 OK、哪个挂了" → `_data_status` 字典 + `STATUS_MESSAGES` 常量
2. 判断"是否该降级" → `DegradationTracker` 阈值控制器，避免一次失败就降级

**纯新增代码，不改任何现有模块的运行逻辑。**

### 改哪些文件（共 4 个文件）

**文件 1：新增 `report/data_status.py`**

```python
"""
数据源状态追踪与降级阈值基础设施。

职责边界 —— 与 html_writer.py 中 raw_data_flags 的关系：
  raw_data_flags: 控制 section 可见性（"这个模块该不该显示？"）
                  值 = 数据是否为空（bool）
  _data_status:   控制数据源状态反馈（"数据拿到了吗？"）
                  值 = 每个数据源的可用详情（dict）

两者正交互补：
  - raw_data_flags = False → 模块隐藏（不占位）
  - raw_data_flags = True 且 _data_status 有失败项 → 页签底部显示状态摘要
  - raw_data_flags = True 且 _data_status 全成功 → 一切正常，不渲染摘要
"""

from typing import TypedDict, NotRequired
import time
import logging

logger = logging.getLogger("invest")

# ── 类型定义 ──────────────────────────────────

class DataStatusItem(TypedDict):
    available: bool
    tier: str       # "T2" / "T3" / "T4"
    message: str    # 最终展示文本，直接渲染不拼接

DataStatus = dict[str, DataStatusItem]

# 消息常量 —— Excel 和 HTML 两端共享引用，保证一致性
STATUS_MESSAGES: dict[str, str] = {
    "rank_unavailable":       "基金业绩排名数据不可用，排名列显示 --",
    "benchmark_unavailable":  "业绩基准数据不可用",
    "industry_unavailable":   "行业分类数据暂不可用（数据源 push2 不稳定）",
    "holdings_unavailable":   "穿透持仓数据暂不可用",
    "profit_forecast_unavailable": "盈利预测数据不可用，EPS 列显示 --",
    "dividend_unavailable":   "分红数据暂不可用",
    "index_degraded":         "指数数据来自降级链路",

    # D-7 占位文本
    "manager_unavailable":    "基金经理数据暂不可用",
    "overlap_unavailable":    "持仓数据不足，无法计算重合度",
    "concentration_unavailable": "持仓集中度数据暂不可用",
    "style_unavailable":      "基金风格数据暂不可用",
    "news_all_failed":        "新闻数据暂不可用，请检查网络连接",
    "warning_unavailable":    "预警数据暂不可用",
}

TIER_PREFIX = {"T2": "⚠", "T3": "ℹ", "T4": "ℹ"}

# ── 降级阈值控制 ──────────────────────────────

class DegradationTracker:
    """双信号降级阈值控制器。
    
    信号1（连续失败）：会话内同一数据源连续失败超过层级阈值，成功后归零。
    信号2（缓存陈旧）：缓存最后成功写入距今超过层级容忍天数。
    任一信号达标即降级。
    
    自适应调节：缓存新鲜（≤TTL）时信号1阈值+1；
               严重过期（>3×TTL）或无缓存时信号1阈值-1。
    """
    _FAILURE_THRESHOLDS = {"T2": 2, "T3": 3, "T4": 1}
    _STALE_DAYS = {"T2": 3, "T3": 14, "T4": 2}
    _FRESH_BONUS = 1
    _PENALTY = 1

    def __init__(self):
        self._fail_counts: dict[str, int] = {}

    def record(self, source_key: str, tier: str, success: bool,
               cache_age_hours: float | None = None,
               cache_ttl_hours: float | None = None) -> tuple[bool, int, int]:
        """记录获取结果，返回 (是否降级, 当前失败计数, 有效阈值)。"""
        base = self._FAILURE_THRESHOLDS.get(tier, 2)

        # 信号1：连续失败计数
        if success:
            self._fail_counts.pop(source_key, None)
            return False, 0, base

        count = self._fail_counts.get(source_key, 0) + 1
        self._fail_counts[source_key] = count

        # 自适应调节
        effective = base
        if cache_age_hours is not None and cache_ttl_hours is not None:
            if cache_age_hours <= cache_ttl_hours:
                effective = base + self._FRESH_BONUS
            elif cache_age_hours > cache_ttl_hours * 3:
                effective = max(1, base - self._PENALTY)
        elif cache_age_hours is None:
            effective = max(1, base - self._PENALTY)

        signal1 = count >= effective

        # 信号2：缓存陈旧度
        stale_hours = self._STALE_DAYS.get(tier, 3) * 24
        signal2 = (cache_age_hours is not None and cache_age_hours > stale_hours)
        signal2 = signal2 or (cache_age_hours is None and cache_ttl_hours is None)

        return signal1 or signal2, count, effective
```

**文件 1's（续）：`cache.py` 新增公共函数**

```python
def get_cache_age(key: str) -> float | None:
    """返回缓存数据年龄（秒），无缓存返回 None。"""
    from src.python.cache import _cache_path, _read_cache_data, _GZIP_SUFFIX
    path = _cache_path(key)
    for fpath in (path + _GZIP_SUFFIX, path):
        data = _read_cache_data(fpath, key)
        if data is not None:
            ts = data.get("_ts", 0)
            return time.time() - ts if ts > 0 else None
    return None
```
```

**文件 2：`excel_writer.py`**

新增 2 个通用函数：

`_write_data_status_foot(ws, data_status, start_row)`：
- 全部 `available=True` → 不渲染
- 有失败项 → 空行分隔，灰色 9 号字体写状态摘要
- T2 `⚠`，T3/T4 `ℹ`

`_write_placeholder(ws, text)`：
- 页签中央写"XX 数据暂不可用"
- 居中、浅灰色，不破坏页签结构

**文件 3：`tmpl/report_template.html`**

独立 CSS：
```css
.data-status { background: #f9f9f9; padding: 10px; margin-top: 15px; border-radius: 4px; }
.data-status-title { font-size: 14px; font-weight: bold; color: #666; }
.data-status-warn { border-left: 3px solid #e67e22; padding-left: 8px; }
.data-status-info { border-left: 3px solid #95a5a6; padding-left: 8px; }
.data-status-ok { border-left: 3px solid #27ae60; padding-left: 8px; }
```

条件渲染块由 D-4/D-5/D-6/D-7 填入具体引用。

### 新增测试详述（6 条）

**`DegradationTracker` 单元测试（3 条，`test_data_status.py` 新增文件）：**

| 测试函数 | mock/准备 | 验证断言 |
|:---------|:----------|:---------|
| `test_degradation_below_threshold_no_degrade` | T2 源连续失败 1 次，缓存新鲜（12h < 24h TTL） | `record()` 返回 `signal=None`, `count=1`, `effective=3`→False，即新鲜缓存下 T2 需 3 次才降级 |
| `test_degradation_signal1_exceeds_threshold` | T2 源连续失败 3 次，缓存新鲜 | `record()` 返回 `signal=True`，即连续 3 次失败超过有效阈值 |
| `test_degradation_signal2_stale_cache` | T2 源失败 1 次，缓存年龄 96h (>72h stale_days) | `record()` 返回 `signal=True`，即缓存过期超 3 天即使单次失败也降级 |
| `test_degradation_self_heal` | T2 源先失败 2 次，第 3 次成功 | 成功后 `record()` 返回 `signal=False, count=0`，自愈 |
| `test_degradation_t4_immediate` | T4 源失败 1 次，无缓存 | 返回 `signal=True`（T4 阈值=1，无缓存无新鲜加成） |
| `test_degradation_no_cache_penalty` | T3 源失败 1 次，无缓存 | 有效阈值 = max(1, 3-1) = 2，count=1 < 2 → `signal=False` |

**Excel 写入函数测试（3 条，`test_excel_writer.py`）：**

| 测试函数 | mock/准备 | 验证断言 |
|:---------|:----------|:---------|
| `test_write_data_status_foot_all_available` | 构造全 `available=True` 的 `DataStatus` | ws 不新增任何行（不渲染）|
| `test_write_data_status_foot_with_failures` | 构造 T2 失败项 1 条（⚠）+ T3 失败项 1 条（ℹ） | 渲染 1 行标题 + 2 行状态，含 ⚠/ℹ，灰色 9 号字体 |
| `test_write_placeholder_rendering` | 调用 `_write_placeholder(ws, "测试占位文本")` | ws 在预期位置写入文本，居中，浅灰色 |

### 验收标准

- [ ] `report/data_status.py` 已创建：含 `DataStatusItem` TypedDict、`DataStatus` 类型别名、`STATUS_MESSAGES` 常量字典、`TIER_PREFIX` 前缀字典、`DegradationTracker` 类
- [ ] `DegradationTracker` 实现：
  - 信号 1：连续失败计数，各层级阈值正确（T2=2, T3=3, T4=1）
  - 信号 2：缓存陈旧度，各层级容忍期限正确（T2=3d, T3=14d, T4=2d）
  - 自适应调节：缓存新鲜时阈值+1，无缓存时阈值-1
  - 成功时计数归零（自愈机制）
  - 无状态持久化依赖（全在内存 + 缓存 `_ts` 字段）
- [ ] `cache.py` 新增 `get_cache_age()` 公共函数，返回缓存数据年龄（秒），无缓存返回 None
- [ ] 6 条 DegradationTracker 单元测试通过（含新鲜缓存、陈旧缓存、无缓存、自愈等场景）
- [ ] `STATUS_MESSAGES` 被 Excel 和 HTML 两端 `import` 直接引用——不是字符串拷贝，是同一对象引用
- [ ] `excel_writer.py` 新增 `_write_data_status_foot()` 函数：全 available 时不渲染；失败项用灰色 9 号字体；T2 前缀 ⚠，T3/T4 前缀 ℹ
- [ ] `excel_writer.py` 新增 `_write_placeholder()` 函数：页签居中央，浅灰色，"XX 数据暂不可用"
- [ ] `report_template.html` 新增 `.data-status` / `.data-status-title` / `.data-status-warn` / `.data-status-info` / `.data-status-ok` 五个 CSS 类
- [ ] P0 门禁通过
- [ ] 无现有测试被破坏（纯新增，不改现有代码）

### 不涉及

- **不修改任何现有函数的调用链**
- **不修改任何页签的写入逻辑**
- **不修改任何数据获取代码**
- **不修改任何测试文件的断言**

### 验证方法

```bash
pytest src/test/unit/report/ -k "test_degradation"          # 6 条阈值测试
pytest src/test/unit/report/ -k "test_data_status_foot"
pytest src/test/unit/report/ -k "test_placeholder"
pytest src/test/unit/ -k "test_cache_age"                    # cache.py 新增函数
python scripts/test_runner.py --mode regression               # P0 门禁
```

---

## D-4 — 穿透模块数据源状态接入

### 做什么

**penetration**（资产穿透）依赖 3 类外部数据：

| 数据 | 数据源 | 稳定性 | 现状 |
|:-----|:-------|:------:|:-----|
| 行业/概念板块 | push2 API | ❌ 最不稳定 | 失败时列全 `--`，用户以为是"无行业数据" |
| 持仓穿透 TOP10 | 天天基金 | ✅ 稳定但偶发 | 失败时表空，用户无法区分"没持仓"还是"拉失败" |
| 盈利预测/股息率 | akshare | ⚠ 中等 | 失败时 debug 日志，用户完全无感知 |

用户看到的变化（以 push2 失败为例）：

```
改之前：
               行业板块
  贵州茅台      白酒       ← 正常
  中国平安      --         ← ？是没行业分类还是数据源挂了？

改之后：
               行业板块
  贵州茅台      白酒
  中国平安      --

  数据加载状态：
  ℹ 行业分类数据暂不可用（数据源 push2 不稳定） ← 新增！
```

### 改哪些文件

| 文件 | 改动内容 |
|:-----|:---------|
| `report/penetration.py` | 在 3 个数据获取点通过 `DegradationTracker.record()` 判断是否降级：push2 行业(T3)、TOP10 持仓(T2)、akshare EPS/股息率(T4)。低于阈值时不设 `available=False`（只记日志不降级）。使用 `STATUS_MESSAGES` 常量 + `get_cache_age()` 查缓存年龄 |
| `report/penetration_sheet.py` | 写入结束时调用 `_write_data_status_foot()` |
| `test/.../test_penetration_edge.py` | 新增 3 条 edge 测试 + 2 条阈值场景测试 |

### 新增测试详述（5 条 — 3 + 2 阈值场景）

**Edge 场景（3 条）：**

| 测试函数 | mock/准备 | 验证断言 |
|:---------|:----------|:---------|
| `test_push2_failure_shows_info_status` | mock `batch_fetch_industry_data`→抛异常，缓存过期 | 页底含 `ℹ` 状态行；`caplog` 含 `"行业"`+失败原因（双通道规则）|
| `test_top10_empty_shows_warning` | mock 天天基金持仓返回 `[]`（无异常，空数据），缓存过期 | 页底含 `⚠` 状态行；`caplog` 含 `"持仓解析结果为空"` |
| `test_akshare_timeout_shows_info` | mock `get_profit_forecast`→超时返回 None，无缓存 | 页底含 `ℹ` 状态行；`caplog` 含 `"akshare"`+`"超时"` |

**阈值场景（2 条）：**

| 测试函数 | mock/准备 | 验证断言 |
|:---------|:----------|:---------|
| `test_push2_transient_blip_no_degradation` | mock push2 首次失败但缓存新鲜（≤TTL）| **不**显示降级状态行（低于阈值）；日志有 `WARNING` 说明失败 |
| `test_push2_recovery_self_heal` | mock push2 首次失败 → 第二次成功 | 最终 `_data_status["industry"]["available"]=True`（自愈后恢复）|

### 验收标准

- [ ] `penetration.py` 中 3 个数据获取点各调用 `DegradationTracker.record()`：低于阈值时不设 `available=False`（仅日志不降级），超阈值时才标记不可用
- [ ] push2 行业(T3) 阈值=3：缓存新鲜时有效阈值=4，单次失败不降级；缓存严重过期时有效阈值=2，两次失败降级
- [ ] TOP10 持仓(T2) 阈值=2：配合缓存新鲜度自适应调节
- [ ] akshare(T4) 阈值=1：立即降级（非关键数据）
- [ ] 每条 `_data_status` 失败记录均有紧邻的日志说明具体原因（§2.2.1 双通道规则）
- [ ] `cache.py` 的 `get_cache_age()` 返回值为 `DegradationTracker` 输入缓存年龄参数
- [ ] 5 条测试覆盖：3 edge + 1 瞬态不降级 + 1 自愈恢复
- [ ] P0 门禁通过
- [ ] 现有 penetration 测试全通过（无回归）

### 不涉及

- **不改 HTML 端**（D-6 处理）
- **不改其他模块**
- **不改 push2 的重试/熔断逻辑**
- **不改缓存 TTL**

### 验证方法

```bash
python scripts/test_runner.py --mode regression            # P0 门禁
pytest src/test/unit/report/ -k "penetration" -m edge      # 3 条新增
pytest src/test/unit/report/ -k "penetration"               # 回归现有
```

---

## D-5 — 基金排名与指数降级标识接入

### 做什么

**基金排名模块**有 3 个数据源不可用时用户无感知：

| 数据 | 当前表现 | 问题 |
|:-----|:---------|:-----|
| 同类排名（天天基金）| 排名列全 `--` | 无法区分"无排名"和"API 挂了" |
| 业绩基准（东财 HTML）| 基准列空 | 用户不知道数据失败了 |
| EPS 预测（akshare）| debug 日志 | 无用户反馈 |

**指数模块**有 4 种数据来源路径，但用户不知道是否降级：

```
Tencent 成功（最佳）
  ↓ 失败
Sina 备用（已降级，用户不知道）
  ↓ 失败
过期缓存（用了过期数据，用户不知道）
  ↓ 没缓存
"--"（用户以为指数没数据）
```

### 改哪些文件

| 文件 | 改动内容 |
|:-----|:---------|
| `report/fund_performance.py` | 排名/基准/EPS 失败时通过 `DegradationTracker.record()` 判断是否降级；写入结束时调用 `_write_data_status_foot()`。使用 `STATUS_MESSAGES` 常量 + `get_cache_age()` 查缓存年龄 |
| `report/summary.py` | 检查各指数 `_source` 标记，有降级则通过 `DegradationTracker.record()` 记录 |
| `fetcher/index.py` | 在 4 个数据入口给每个指数数据加 `_source` 字段。注意：index.py 不走 Provider Chain，需手写 |
| `test/.../test_fund_performance_edge.py` | **新建**：3 条 edge 测试 + 2 条阈值测试 |
| `test/.../test_summary_edge.py` | **新建**：1 条 edge 测试 |
| `test/.../test_index_source.py` | **新建**：1 条单元测试 |

### 新增测试详述（7 条 — 5 + 2 阈值场景）

**Edge 场景（5 条）：**

| 测试函数 | 归属文件 | mock/准备 | 验证断言 |
|:---------|:---------|:----------|:---------|
| `test_rank_unavailable_shows_warning` | `test_fund_performance_edge.py` | mock 排名→`[]`，缓存过期 | 页底含 `⚠` 状态行；`caplog` 含 `"排名"` + `"空响应"` |
| `test_benchmark_unavailable_shows_warning` | `test_fund_performance_edge.py` | mock 基准数据→空，缓存过期 | 页底含 `⚠` 状态行；`caplog` 级别 `WARNING` |
| `test_eps_failure_shows_info` | `test_fund_performance_edge.py` | mock 盈利预测→抛异常，无缓存 | 页底含 `⚠` 状态行（EPS 在 T2 页签内→符号绑定 T2 的 `⚠`）|
| `test_index_from_sina_shows_degraded` | `test_summary_edge.py` | mock 腾讯空+新浪正常 | 页底含 `⚠` 指数降级标识；`caplog` 含 `"腾讯链路失败"` |
| `test_index_source_field` | `test_index_source.py` | 依次 mock 4 路径：腾讯/新浪/缓存/过期缓存 | 各路径 `_source` 值分别为 `"tencent"`/`"sina"`/`"cache"`/`"stale_cache"` |

**阈值场景（2 条）：**

| 测试函数 | 归属文件 | mock/准备 | 验证断言 |
|:---------|:---------|:----------|:---------|
| `test_rank_first_failure_cache_fresh_no_degrade` | `test_fund_performance_edge.py` | mock 排名首次失败，缓存新鲜（≤TTL） | **不**显示降级状态行（T2有效阈=3，count=1<3）；日志正常 |
| `test_rank_persistent_failure_degrades` | `test_fund_performance_edge.py` | mock 排名失败且缓存 >3d（跨会话陈旧） | 即使 count=1，信号2(缓存过期超 T2 容忍期) 触发降级 |

> **index.py `_source` 赋值策略：**
> - 腾讯成功 (index.py:68): `data["_source"] = "tencent"`
> - 新浪备用 (line 133): `data["_source"] = "sina"`
> - 缓存命中 (line 118): `data["_source"] = "cache"` — 缓存数据的原始来源丢失，但标记为 cache 让用户知道非实时
> - 过期缓存 (line 142): `data["_source"] = "stale_cache"` — 过期数据，降级程度最高
> - 4 条路径做到全覆盖，`_source` 字段随数据字典一起传递

### 验收标准

- [ ] `fund_performance.py` 中 3 个数据入口各调用 `DegradationTracker.record()`：低于阈值时不标记降级（有新鲜缓存时最多容忍至 T2 有效阈=3）
- [ ] `write_fund_performance_sheet()` 在写入结束前调用 `_write_data_status_foot()`
- [ ] `index.py` 中 4 个数据入口路径各加 `_source` 字段
- [ ] `summary.py` 遍历指数 `_source`，有降级通过 `DegradationTracker.record()` 记录
- [ ] 每条 `_data_status` 记录均有紧邻的日志说明具体原因
- [ ] 7 条测试覆盖：5 edge + 1 缓存新鲜不降级 + 1 跨会话陈旧降级
- [ ] P0 门禁通过
- [ ] 现有 fund_performance/summary/index 测试全通过

### 不涉及

- **不改指数 fallback 逻辑**
- **不改排名计算逻辑**
- **不改 HTML 端**（D-6 处理）
- **不改过期缓存策略**

### 验证方法

```bash
python scripts/test_runner.py --mode regression                  # P0 门禁
pytest src/test/unit/report/ -k "fund_performance" -m edge       # 3 条新增
pytest src/test/unit/report/ -k "summary" -m edge                 # 1 条新增
pytest src/test/unit/fetcher/ -k "index"                          # 回归指数模块
```

---

## D-6 — HTML 报告状态摘要渲染

### 做什么

D-4 和 D-5 只在 Excel 页签底部加了状态摘要，D-6 把同样的信息渲染到 HTML 端。

两端共享 D-3 的 `STATUS_MESSAGES` 常量，文字完全一致。

**D-6 还额外处理：**

1. **`_render_penetration_section` 内部的大 try/except 拆分：** 原来一个 try 包了"加载盈利预测 + 股息率"两个数据源，拆为各自独立 try，各带独立 success 标志位和明确的 warning 日志：

    ```python
    # 改之前：一个 try 包了两个数据源
    try:
        profit_forecast = get_profit_forecast()
        dividend_data = get_dividend_data(a_codes)
    except Exception:
        profit_forecast, dividend_data = {}, {}

    # 改之后：各数据源独立 try
    profit_success = True
    try:
        profit_forecast = get_profit_forecast()
    except Exception:
        profit_success = False
        logger.warning("[penetration] 盈利预测加载异常...", exc_info=True)

    dividend_success = True
    try:
        dividend_data = get_dividend_data(a_codes)
    except Exception:
        dividend_success = False
        logger.warning("[penetration] 股息率加载异常...", exc_info=True)
    ```

    > 这个拆分原本在 D-2，但 D-2 主要改 `excel_generator.py` 的 B 系列 4 个大 try。`_render_penetration_section` 的 try 涉及穿透数据，与 D-6 的 `data_status` 关联更紧密——拆分后 profit_forecast/dividend 可各自独立设置 success 标志用于上层构建 `_data_status`。移至 D-6 避免先拆后改的冲突。

2. **移除 `{"ok": "ok"}` 欺骗性字典：** 原代码用 `{"ok": "ok"}` 作为 `adjusted_ratings` 的占位传递给 `_build_perf_data_status`，实为欺骗语法检测。改为从 `perf_data` 中提取真实 `rating_tag`，使语义正确。

3. **`html_writer.py` 主体函数内直接构建 data_status：** 3 个 data_status 字典（summary/penetration/perf）在 `write_html_report()` 函数体内直接构建并通过 `tmpl.render(**kwargs)` 传入模板，非通过 `_render_*` 函数返回值传递。

### 改哪些文件

| 文件 | 改动内容 |
|:-----|:---------|
| `report/html_writer.py` | 在 `write_html_report()` 函数内新增 3 个独立的 try 块构建 `data_status_summary`/`data_status_penetration`/`data_status_perf`；`_render_penetration_section` 拆分 profit_forecast/dividend 为独立 try；移除 `{"ok":"ok"}` 欺骗性字典，改用真实 `rating_tag`；3 个 data_status try 块各自有完整 logging |
| `report/penetration_sheet.py` | 将 `_build_data_status` 重命名为 `_build_penetration_data_status` 避免命名冲突；`cache_ttl_hours=24` 硬编码改为 `get_ttl("industry") / 3600` |
| `report/fund_performance.py` | `cache_ttl_hours=4` 硬编码改为 `get_ttl("profit_forecast") / 3600` |
| `report/summary.py` | 2 处 `get_cache_age("index_sh000001")` 等硬编码 key 替换为 `get_cache_age_by_data_type("index", "sh000001")` |
| `cache.py` | 新增 `get_cache_age_by_data_type(data_type, identifier)` 函数，通过 registry 解析 cache_prefix 匹配查找缓存 |
| `providers/akshare_extras.py` | 新增 `get_profit_forecast_cache_key()` 公共函数，供 `get_cache_age_by_data_type("profit_forecast", ...)` 内部调用 |
| `config.py` / `config.json` | 新增 `degradation` 配置段（t2/t3/t4 阈值，含 unreachable_threshold/empty_data_threshold/stale_days）|
| `tmpl/report_template.html` | Section 1(summary), Section 4(penetration), Section 5(fund_performance) 新增 data_status 条件渲染块，使用 `.data-status-warn`(T2) 和 `.data-status-info`(T3/T4) CSS 类 |

### 验收标准

- [ ] HTML 端在 `write_html_report()` 内通过 3 个独立 try 块构建 `data_status_summary`/`data_status_penetration`/`data_status_perf`，传入模板 kwargs
- [ ] `_render_penetration_section` 的盈利预测/股息率已拆为两个独立 try，各带独立 success 标志和具体 warning 日志
- [ ] 移除 `{"ok": "ok"}` 欺骗性字典，`adjusted_ratings` 从 `perf_data` 真实提取 `rating_tag`
- [ ] 3 处 data_status try 块（summary/penetration/perf）均有 `exc_info=True` 的日志记录
- [ ] 4 处 `get_cache_age()` 硬编码 key 已替换为 `get_cache_age_by_data_type()` 注册表驱动版本
- [ ] 2 处 `cache_ttl_hours` 硬编码（24/4）已替换为 `get_ttl()` 注册表版本
- [ ] 新增 `degradation` 配置段到 `config.json` 和 `DEFAULT_CONFIG`，阈值与 data_status.py 默认值一致
- [ ] HTML 模板在数据源失败时渲染 D-3 定义的状态摘要区块，文字取自 `STATUS_MESSAGES`（与 Excel 端同源）
- [ ] 状态区块视觉：T2 用 ⚠ 橙色左边框（`.data-status-warn`），T3/T4 用 ℹ 灰色左边框（`.data-status-info`）
- [ ] 全部可用时不渲染状态区块（与 Excel 端一致）
- [ ] 3 条 edge 测试覆盖：mock penetration data_status → template kwargs 含失败项；mock perf data_status → template kwargs 含失败项；mock penetration data_status 抛异常不影响 perf data_status
- [ ] 4 条已有 `_render_penetration_section` edge 测试原本存在（空 top10/全 API 失败/部分数据/无 codes 键）
- [ ] P0 门禁通过
- [ ] Excel 端 D-4/D-5 已有测试不因本步改动而失败

### 不涉及

- **不改 Excel 端已完成的逻辑**
- **不改 B 系列、新闻、LLM 的渲染**（D-7 单独处理）
- **不改报告布局和导航**

### 验证方法

```bash
python scripts/test_runner.py --mode regression      # P0 门禁
pytest src/test/unit/report/ -k "html" -m edge       # 4 条 edge（1 旧 + 3 新增）
pytest src/test/unit/report/test_html_writer_edge.py  # 7 条全通过
```

---

## D-7a — B 系列模块空态占位

### 做什么

B 系列 4 个模块在数据不可用时页签直接消失，用户不知道为什么。

| 模块 | 消失原因 | 用户困惑 |
|:-----|:---------|:---------|
| 基金经理变更监控 | `manager_data` 为空 → `section_visible = False` | "我记得有这个功能啊，这次怎么没了？" |
| 持仓重合度矩阵 | 基金数 < 2 或持仓全空 → 跳过 | "为什么没算重合度？" |
| 持仓集中度监控 | 结果为空 → 跳过 | "集中度数据去哪了？" |
| 基金风格分析 | 结果为空 → 跳过 | "风格分析呢？" |

**核心改动：** 不隐藏，改**占位**——

```
改之前：页签完全消失（用户不知道曾经存在过）
改之后：页签还在，里面写一行文字："XX 数据暂不可用"
```

每个模块改动模式完全一致：
```python
def _write_manager_sheet(ws, manager_data):
    if not manager_data or not manager_data.get("results"):
        _write_placeholder(ws, STATUS_MESSAGES["manager_unavailable"])
        return
    # ... 正常写入 ...
```

### 改哪些文件

| 文件 | 占位条件 | 占位文本 |
|:-----|:---------|:---------|
| `report/fund_manager_sheet.py` | 结果列表为空 | 直接判空后显示占位（见下方设计说明）|
| `report/overlap_matrix.py` / `fund_overlap_sheet.py` | 基金数 < 2 或持仓全空 | 同上 |
| `report/concentration_sheet.py` | 结果列表为空 | 同上 |
| `report/fund_style_sheet.py` | 结果列表为空 | 同上 |
| `report/html_writer.py` | `_render_*` 对应占位检测 | 与 Excel 端一致 |

> **设计决策：跳过 DegradationTracker。** B 系列 4 模块均为 T4 且无缓存数据，`record()` 的实际效果等价于 `if not data`（T4 默认有效阈=1，无缓存自适应惩罚后仍为 1）。直接 `if not data` 判空避免了不必要的导入和调用，语义同样清晰。如果后续某模块调整为 T3/T2 或有了缓存，再恢复 `DegradationTracker.record()` 调用。

### 验收标准

- [ ] 4 个模块在数据为空时不再隐藏页签，而是调用 `_write_placeholder()` 在页签中央显示占位文本
- [ ] 占位文本来自 `STATUS_MESSAGES` 常量，非硬编码字符串
- [ ] 页签标题和结构完整保留（用户能看到页签标签）
- [ ] 空数据判空使用 `if not data`（跳过 DegradationTracker，原因见上方设计说明）
- [ ] （待 D-7b 恢复）新闻模块（T4）通过 `DegradationTracker` 阈值判断后显示占位
- [ ] （待 D-7b 恢复）预警模块（T4）通过跟踪子源的 cumulative 状态判断
- [ ] 每条 `_data_status` 失败记录均有紧邻的日志说明具体原因（§2.2.1 双通道协作规则）
- [ ] HTML 端占位表现与 Excel 端一致
- [ ] 4+3 条 edge 测试覆盖：每个模块的空数据场景
- [ ] P0 门禁通过
- [ ] 各模块有数据时正常显示不受影响

### 不涉及

- **不改 B 系列计算逻辑**
- **不改页签可见性注册表**
- **不改新闻、预警、LLM 模块**
- **与 D-6 无冲突**：D-6 改 `html_writer.py` 的 `_render_penetration_section`/`_render_fund_performance`/`_render_summary`，D-7a 改 `_render_manager_analysis`/`_render_overlap_matrix`/`_render_concentration`/`_render_style_analysis`——函数范围完全不重叠

### 验证方法

```bash
python scripts/test_runner.py --mode regression              # P0 门禁
pytest src/test/unit/report/ -k "manager" -m edge
pytest src/test/unit/report/ -k "overlap" -m edge
pytest src/test/unit/report/ -k "concentration" -m edge
pytest src/test/unit/report/ -k "style" -m edge
```

---

## D-7b — 新闻与预警模块空态占位

### 做什么

D-7a 处理了 B 系列 4 个模块，D-7b 处理剩下的 news 和预警模块。

| 模块 | 消失原因 | 改后表现 |
|:-----|:---------|:---------|
| 新闻关联分析 | 5 源全失败 → 空列表 → 页签不渲染 | 显示"新闻数据暂不可用，请检查网络连接" |
| 新闻关联分析 | 部分源失败 | 底部注明哪些源不可用 |
| 智能预警 | 依赖数据为空 → 空列表 | 显示"预警数据暂不可用" |

### 改哪些文件

| 文件 | 改动内容 |
|:-----|:---------|
| `providers/news_aggregator.py` | 新增 `source_status` 返回值（每个源 ok/fail） |
| `report/news_correlation.py` | 全源失败/部分失败时写占位 |
| `report/early_warning.py` | 入口检查新闻数据，为空则返回带 placeholder 的空结果 |
| `report/html_writer.py` | 对应 `_render_*` 的 placeholder 检测 |

### 验收标准

- [ ] `news_aggregator.py` 返回值新增 `source_status` 字段，格式为 `dict[str, bool]`（源名称 → 是否成功）
- [ ] 全源失败时：页签显示占位文本"新闻数据暂不可用，请检查网络连接"，日志写明"5 个新闻源均返回空结果"
- [ ] 部分源失败时：页签底部声明"以下新闻源不可用：{源1}、{源2}"，日志逐源记录失败原因
- [ ] `early_warning.py` 在新闻数据为空时返回含 `placeholder: True` 的结果结构，不抛异常
- [ ] HTML 端占位表现与 Excel 端一致
- [ ] 3 条 edge 测试覆盖：全源失败占位、部分源失败摘要、预警空数据
- [ ] P0 门禁通过
- [ ] 新闻和预警有正常数据时不受影响

### 不涉及

- **不改新闻获取的重试/超时逻辑**
- **不改 LLM 模块**
- **不改 B 系列模块**
- **与 D-6 无冲突**：D-7b 改 `html_writer.py` 的 `_render_news_correlation`/`_render_early_warning`，与 D-6 和 D-7a 的函数范围不重叠

### 验证方法

```bash
python scripts/test_runner.py --mode regression       # P0 门禁
pytest src/test/unit/report/ -k "news" -m edge        # 2 条：全源失败 + 部分源失败
pytest src/test/unit/report/ -k "early_warning" -m edge  # 1 条：预警空数据
```

---

## D-8 — 全链路回归基线锁定

### 做什么

前面子迭代各自做了单元测试，但缺 2 件事：

1. **全局降级冒烟测试**：所有外部 API mock 挂掉 → 完整报告生成成功 → 检查每处降级标识
2. **Excel vs HTML 消息一致性**：同一 mock 场景，正则提取两端 `⚠`/`ℹ` 文字，断言完全一致

### 改哪些文件

| 文件 | 改动内容 |
|:-----|:---------|
| `test/.../test_excel_generator_edge.py` | **新建**：全局降级冒烟 + 消息一致性测试（含 Excel ⚠/ℹ 渲染 vs HTML 宏渲染的结构等价验证）|

### 验收标准

- [ ] 全局降级冒烟：mock 所有外部 API（tencent/sina/push2/tiantian/akshare、5 个新闻源）→ `main.py` 完整报告生成成功（exit code 0）→ 报告中每个模块页签/区块存在且含对应降级标记（⚠/ℹ），不含空表或隐藏页签
- [ ] 一致性测试：同一 mock 场景下，用正则提取 Excel 字符串中的 ⚠/ℹ 消息行 和 HTML 中的 ⚠/ℹ 文本块 → 两组文本完全相同
- [ ] 全部 edge 测试（含 D-1~D-7 新增的）全通过
- [ ] P0 + P1 门禁全通过

### 不涉及

- **不改任何生产代码**
- **不改现有测试断言**
- **不改测试框架配置**

### ⚠️ D-7b 延期影响

D-7b（新闻/预警模块占位）已延期，因此 D-8 的降级测试范围仅限于已实现占位的模块：
- 指数降级 ✓（summary `_write_data_status_foot`）
- 穿透数据降级 ✓（penetration `_write_data_status_foot`）  
- 基金业绩降级 ✓（fund_performance `_write_data_status_foot`）
- B 系列空态占位 ✓（4 个 `_write_placeholder`）
- **新闻/预警模块占位尚未实现**，待 D-7b 恢复后补测

### 验证方法

```bash
python scripts/test_runner.py --mode regression   # P0 门禁
python scripts/test_runner.py --mode verify        # P1 门禁（场景+核心模块）
pytest src/test/ -m "edge"                         # 全部 edge 测试
pytest src/test/scenario/ -m "scenario_resilience" # 容错场景
```

---

## D-9 — 文档同步

### 做什么

D 迭代涉及 20+ 文件变更，需要同步更新管理文档，避免下次文档审计不一致。

同时把 `plan.md` 中 D 迭代的描述从旧的三段式（Phase 1/Phase 2/Phase 3）更新为 10 步子迭代的新结构。

### 改哪些文件

| 文档 | 需要同步的内容 |
|:-----|:--------------|
| `docs-stm/managements/plan.md` | D 迭代描述从三段式更新为 10 步子迭代结构 |
| `docs-stm/managements/technical.md` | 新增"数据降级分层治理(T1~T4)"架构描述 + `_data_status` 机制说明 |
| `docs-stm/managements/requirements.md` | D 迭代降级策略需求补充（T2/T3/T4 各层行为）|
| `docs-stm/manuals/datasource-and-folders.md` | 目录树更新：`report/data_status.py`、新增 `test_*_edge.py` |
| `docs-stm/managements/test-coverage.md` | edge 测试计数更新（228 → ~270+）|

### 验收标准

- [ ] `plan.md` 中 D 迭代的"三个 Phase"描述已替换为 10 步子迭代清单 + 降级阈值控制章节，含各迭代名称和链接到设计文档的引用
- [ ] `technical.md` 新增"数据降级分层治理"章节：T1~T4 分层定义、`_data_status` 机制说明、符号绑定规则（⚠/ℹ 与渲染页签 T 层绑定）
- [ ] `technical.md` 新增"降级阈值控制"子章节：`DegradationTracker` 双信号设计、缓存新鲜度自适应调节、各层级阈值列表
- [ ] `requirements.md` 补充各层降级策略行为需求：T2 列级 `--` + ⚠、T3 列级 `--` + ℹ、T4 模块级占位/隐藏
- [ ] `datasource-and-folders.md` 目录树已同步：`report/` 下含 `data_status.py` 说明、"数据源状态追踪基础设施"；`test/` 对应 edge 文件已列出
- [ ] `test-coverage.md` edge 测试计数已更新为截至 D-8 后的实际总数
- [ ] 逐文档核对：目录结构、文件名、计数、描述与实际代码完全一致

### 不涉及

- **不改任何代码**
- **不改用户手册其他章节**
- **不改测试文件和配置**

### 验证方法

```bash
# 逐文档检查目录结构/计数/描述与实际代码一致
# 无自动化测试
```

---

## 子迭代总表

| 编号 | 名称 | 一句话描述 | 涉及文件数 | 代码改动 | 新增测试 | 风险 |
|:----:|:----|:-----------|:----------:|:--------:|:--------:|:----:|
| D-1 | 静默异常日志补全 | 19 处静默异常+空数据+降级原因加日志，不改返回值 | 15 | ~42 行 | 0 | 🟢 极低 |
| D-2 | 大粒度 try 拆分与代码去重 | excel_generator B 系列 4 处大 try 拆细 + _yield_text 去重 | 4 | ~50 行 | 0 | 🟡 中低 |
| D-3 | 数据源状态追踪+阈值基础设施 | DataStatus 类型/常量/写入/占位 + DegradationTracker 双信号决策 + get_cache_age() | 4 | +160 行 | 6 | 🟢 低 |
| D-4 | 穿透模块接入阈值+状态 | penetration 3 源调 record() + 缓存新鲜度自适应 | 3~4 | +70 行 | 5 | 🟡 中 |
| D-5 | 基金排名与指数降级标识+阈值 | perf/summary 调 record() + index.py 加 _source | 5 | +90 行 | 7 | 🟡 中 |
| D-6 | HTML 报告状态摘要渲染+try拆分 | data_status 传入模板 + _render_penetration try 拆细 + 4个硬编码key替换 + 2个cache_ttl修复 + config新增degradation + {"ok":"ok"}移除 | 9 | ~180 行 | 3(按计划)+7(连带修复) | 🟡 中低 |
| D-7a | B 系列模块空态占位 | 4 个 B 系列模块占位替代隐藏 | 5 | +60 行 | 4 | 🟡 中低 |
| D-7b | 新闻与预警模块空态占位 | news + early_warning 占位 | 4 | +50 行 | 3 | 🟡 中低 |
| D-8 | 全链路回归基线锁定 | 全局降级冒烟 + 消息一致性 | 2 | +100 行 | 5 | 🟢 低 |
| D-9 | 文档同步 | 5 份管理文档 + plan.md 同步更新 | 5 | ~文本 | 0 | 🟢 低 |

**总计：** ~752 行变更（~410 生产代码 + ~342 测试代码），10 个独立可提交/可回滚步骤

---

## 架构债务（本轮不修，仅记录备忘）

| # | 债务 | 影响 | 后续修复 |
|:-:|:-----|:-----|:---------|
| 1 | `index.py` 不走 Provider Chain（双链路硬编码内部） | 熔断器对指数无效；D-5 需手写 source 追踪 | E 迭代或 fetcher 重构时 |
| 2 | C4 要求"同一会话同一 API 数据复用"，仅 fund_style 实现了 `_ext_memo` | 多模块重复拉取同一只股票数据 | 单独重构迭代 |
