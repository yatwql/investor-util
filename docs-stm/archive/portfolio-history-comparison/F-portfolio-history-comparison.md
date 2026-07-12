# F 迭代：组合历史对比分析 — 迭代计划与技术设计

> **优先级**：P2（低难度 / 中价值）
> **状态**：设计完成（11 轮方案，2026-07-12 架构评审修订）
> **版本**：v2（基于 v0.4.0 technical.md 设计约束 C1~C14 全面审计修订）

## 概述

### 问题陈述

当前 LLM 分析模块输出**单次报告的快照分析**——无法回答"相比上次报告，组合发生了什么变化"，也无法识别持仓变动、仓位迁移、风格漂移等时间维度的信号。

### 三阶段目标

| 阶段 | 目标 | 定位 | 触发方式 |
|:-----|:-----|:-----|:---------|
| **F1: 快照对比** | LLM 输出"相比上次报告，市值 ±X%，主要变化是……" | **核心必选项** — 零成本，始终自动 | 嵌入报告生成，用户无感 |
| **F2: 历史走势** | 构建连续日频市值曲线，支持回撤/收益率计算 | **加分项** — 需 ~15s + API 调用 | 报告后询问 / 缓存预热后自动 |
| **F3: 跨报告趋势** | 跨报告趋势查询能力（SQLite） | **基础设施** — 视 F2 实际价值决定 | 独立菜单项 |

### 非目标

- 不建设实时行情推送或分钟级数据
- 不建设组合模拟/回测引擎
- 不改变现有单次报告生成流程的稳定性
- 不引入外部数据库依赖（直到 F3 确认需要）

---

## 1. 数据覆盖审查

### 1.1 持仓时间线语义

| 语义 | 含义 | 适用场景 |
|:-----|:------|:---------|
| **as-if 市值** | 当前持仓回溯其在 T 日的价格 × 当前份额 | "我现在的持仓在过去 N 天表现如何？" ← **F2 默认** |
| **实际市值** | T 日实际持有的仓位在 T 日的市值 | 不可得（无历史份额记录） |

F2 选择 as-if 语义。LLM 提示中标注："以下曲线假设当前持仓在过去 N 天份额不变。"

### 1.2 七大盲区

| # | 盲区 | 缓解措施 |
|:--|:------|:---------|
| **A** | **持股期外污染**（买了 3 天拉了 30 天日线） | as-if 语义明确标注假设 |
| **B** | **基金分红除权**（单位净值分红日跳降） | 业绩评价用累计净值（`Data_ACWorthTrend`），市值计算用单位净值（`Data_netWorthTrend`） |
| **C** | **已清仓持仓蒸发** | F1 快照保留历史记录；F2 as-if 只含当前持有 |
| **D** | **现金仓位缺失** | 快照新增 `cash_reserve` 字段，按货基收益率回填 |
| **E** | **份额变动间缺失** | 接受近似值，以快照断点分段 |
| **F** | **复权方式选择** | 固定腾讯 qfq（前复权） |
| **G** | **交易日历感知** | 传入日期范围由 API 过滤非交易日 |

### 1.3 基金历史净值字段

| 用途 | 字段 |
|:-----|:-----|
| "该基金过去涨了多少？"（业绩评价） | `Data_ACWorthTrend`（累计净值，含分红再投资） |
| "我持仓那天的市值是多少？"（市值计算） | `Data_netWorthTrend`（单位净值）× 份额 |

---

## 2. 报告格式变更

### 2.1 F1：仅修饰现有章节，不新增独立章节

| 报告类型 | 变更 |
|:---------|:------|
| **Excel** | 持仓明细页签：在"盈亏"后增加"较上次"列（Δ盈亏、Δ盈亏率）；汇总行增加"较上次报告变化"行 |
| **HTML** | 持仓表格同上增加 Δ 列；LLM 章节标题旁增加 `(含环比分析)` |
| **LLM** | `generate_expert_review` → "相比上次报告"段落；`generate_health_check` → "变化趋势"评分因子 |

### 2.2 F2：新增独立章节

| 报告类型 | 新增内容 | 注册 key |
|:---------|:---------|:---------|
| **Excel** | **组合历史走势** sheet（日期 × 总市值/日收益率/累计回撤） | `portfolio_history` |
| **Excel** | 汇总 sheet 增加"区间最大回撤 / 波动率"行 | — |
| **HTML** | **组合历史走势** 章节（Chart.js 折线图 + 数据表格） | `portfolio_history` |
| **HTML** | **回撤分析** 章节（最大回撤起止 + 连续回撤列表） | `drawdown_analysis` |

### 2.3 F3：跨报告趋势（待定）

F3 保留为待定状态，待用户使用 F2 后提出需求时再启动详细设计。

| 报告类型 | 新增内容 | 注册 key |
|:---------|:---------|:---------|
| **Excel** | **跨报告趋势** sheet（多次报告的关键指标时间线） | `trend_comparison` |
| **HTML** | **多报告趋势** 章节 + 折线图 | `trend_comparison` |

---

## 3. TUI 菜单与交互流

### 3.1 F1：无变更

差异计算零延迟，自动嵌入 `_cmd_generate_full()`。

### 3.2 F2：二阶段触发 + 全量重渲染

HTML 不支持生成后追加写入（导航栏、CSS order、DOM 结构已固化）。采用**全量重渲染**模式——先收集全部数据（含历史，若用户同意），再一次性渲染完整报告。

**C4 约束**：`PortfolioHistoryCalculator` 获取走势数据前先检查 `session_cache_get("history_stock", code)`，同一会话内重复请求直接返回缓存结果。

**方式 A（报告后自然询问）**：

```
用户输入 L → _cmd_generate_full()
                  │
                  ├─ _prepare_report_data()     ← 收集基础数据
                  ├─ 快照比对 (F1)              ← 始终运行
                  │
                  ├─ 判断 history_analysis 配置:
                  │   ├─ "prompt" → 询问 → Y: [..] 正在拉取历史走势数据...
                  │   │                          N: 跳过
                  │   ├─ "auto"  → 缓存命中率 >80%? → Y: 自动拉取缺失部分
                  │   │                                 N: 静默跳过
                  │   └─ "off"   → 跳过
                  │
                  ├─ generate_all_llm(diff=DiffSummary)
                  ├─ 报告写入（含或不含走势章节，一次渲染完整 HTML/Excel）
                  └─ 报告完成
```

**方式 B（缓存预热）**：

| 现有菜单项 | 增强 |
|:-----------|:------|
| `"1" → 更新基础类缓存` | 后台顺带拉取所有持仓历史日线并缓存 |

缓存全部命中时自动跳过询问阶段。

**配置项设计**（`config.json`，采用嵌套对象，与现有 `preferred_provider`/`degradation` 模式一致）：

```json
{
  "history": {
    "analysis": "prompt",     // "prompt"=询问（默认）| "auto"=缓存命中自动 | "off"=禁用
    "days": 30,               // 合法范围 [5, 365]，非法值兜底 30
    "benchmark": "sh000300"   // 带交易所前缀的指数代码，与 index.py 的 _A_INDICES 键名一致
  }
}
```

> **`benchmark` 代码格式说明**：使用带 `sh`/`sz` 前缀的格式（如 `sh000300` 表示沪深300），与 `fetcher/index.py` 的 `_A_INDICES` 键名一致。用户配置 `"000300"` 时，新增的 `fetch_index_history()` 需要内部映射到 `sh000300`。

### 3.3 F3：新增菜单项

`"V" → 查看组合历史趋势` — 独立展示跨报告趋势。

### 3.4 交互流总览

```ascii
用户输入 L
    │
    ▼
_cmd_generate_full()
    ├── _prepare_report_data()
    │   └── session_cache 检查 ← C4：会话内重复请求免 HTTP
    ├── 快照比对 (F1)      ← 始终运行，零延迟
    ├── generate_all_llm(diff=DiffSummary, f_context=...)
    │                        └── LLM 注入接口：f_context dict 模式
    │                            §3.1 见下方说明
    │
    ├── 判断 history_analysis 配置:
    │   ├── "auto"  → 缓存命中率 >80%?     → Y: 拉取历史数据
    │                                           N: 静默跳过
    │   ├── "prompt" → 询问用户 → [..] 正在拉取历史走势数据...
    │                              Y: 拉取历史数据
    │                              N: 跳过
    │   └── "off"   → 跳过
    │
    ├── report_prepare(info)  ← 一次渲染（含/不含历史数据）
    └── 报告完成
```

### 3.5 LLM 注入接口：f_context dict 模式

为支持 F1/F2 差异和走势数据注入 LLM（无需增加 `generate_all_llm` 的参数数量），使用 **context dict** 模式：

```python
# generators_orchestrator.py: generate_all_llm()
def generate_all_llm(
    a_indices, us_indices, ..., force=False,
    f_context: dict | None = None,  # 新增 — F 迭代时间维度上下文
) -> tuple[...]:
```

`f_context` 结构：
```python
f_context = {
    "diff": DiffSummary | None,         # F1 快照差异（首次运行=None）
    "diff_trimmed": bool,               # 是否因 token 限制裁剪
    "days_since_last": int,             # 距上次报告天数（F1 基准日对齐）
}
```

各生成器内部通过 `f_context.get("diff")` 选择性消费。不影响现有参数签名兼容性。

---

## 4. Provider Chain 集成

### 4.1 方案

历史数据现有 Provider 的函数签名扩展为按 `data_type` 参数区分实时/历史路由，**熔断器共享**同一 provider name。不创建 `tencent_history` 等独立名称。

| 函数 | 所在文件 | 路由参数 | 用途 | 所属 chain |
|:-----|:---------|:--------|:-----|:-----------|
| `fetch_kline(code, days, data_type="history")` | `providers/tencent.py` | `tencent` provider，同一熔断器 | 主链路（腾讯 K 线） | `history_stock` |
| `fetch_kline(code, days, data_type="history")` | `providers/sina.py` | `sina` provider，同一熔断器 | 备用链路（新浪 K 线） | `history_stock` |
| `fetch_fund_nav_history(code)` | `providers/tiantian.py` | `tiantian` provider，同一熔断器 | 唯一链路（天天基金净值） | `history_fund_otc` |

**设计依据**：`tencent` 主链路若熔断（如网络不可达），`tencent_history` 也必然不可达——二者走同一 API 域名 `qt.gtimg.cn`。共享熔断器避免"实时 Tencent 已熔断但历史 Tencent 还在尝试"的矛盾状态。

**Chain 注册**（`chain.py:_DEFAULT_CHAINS`）：

```python
_DEFAULT_CHAINS: dict[str, list[str]] = {
    # ... 现有 ...
    "history_stock": ["tencent", "sina"],
    "history_fund_otc": ["tiantian"],
}
```

**C6 约束实现**：不绕过 `_fetch_with_fallback()`。新增 `_fetch_with_incremental_fallback()` 方法（见 §4.3），统一管理熔断预检 + Provider 遍历 + 增量合并 + 缓存写入，与现有 `_fetch_with_fallback()` 共享 Provider Chain 治理。

**C5 约束**：Provider 函数内部所有 HTTP 请求必须使用 `http_client.py` 的 `make_http_client()`，不得直接实例化 `httpx.Client()`。

**代码类型路由（C1 约束）：**

OTC 基金代码通过排除法识别（非 A 股、非 ETF 前缀、非港股通的 6 位数字代码）。

```python
class PortfolioHistoryCalculator:
    def calculate_for_holding(self, holding):
        code = holding.code.strip()
        name = (holding.name or "").strip()
        # 股票+ETF → 腾讯历史 K 线（备选新浪）
        if is_a_share_code(code) or is_exchange_fund_code(code):
            return self._get_stock_history(code)
        # 港股通 → 暂不支持日线（后续扩展）
        if is_hk_stock_code(code):
            return None
        # 债券基金 → OTC 净值链路
        if is_bond_related_by_name(name):
            return self._get_fund_history(code)
        # 其余 6 位数字代码 → OTC 基金净值
        if len(code) == 6 and code.isdigit():
            return self._get_fund_history(code)
        return None  # 不支持的类型
```

### 4.2 指数历史的特殊处理

指数**不走 Provider Chain**（与 `technical.md` 现有规则一致）。在 `fetcher/index.py` 中新增 `fetch_index_history(code, days)`，Tencent 直调 + Sina 双链路 fallback 硬编码在其内部。

### 4.3 缓存策略与增量合并模式

`_fetch_with_fallback()` 是 all-or-nothing 单值获取模式（检查缓存→无缓存→遍历 provider→成功则缓存全部结果），历史数据需要 get-or-fetch-merge-store 增量合并——两者不兼容。

新增 **`_fetch_with_incremental_fallback()`** 方法（`fetcher/chain.py`），统一在 chain 层管理增量合并和缓存写入。Provider 函数保持**纯数据获取**（不碰缓存层），遵循 C6 约束：

```python
# fetcher/chain.py
def _fetch_with_incremental_fallback(chain_name: str, code: str, days: int = 30,
                                     param_fn: Callable = None) -> list[dict]:
    """
    增量合并版 fallback 路由。
    - chain 层管理缓存读/写/合并
    - Provider 层只负责纯数据获取
    - 熔断器预检、fallback 遍历与 _fetch_with_fallback() 共享
    """
    cache_key = f"history_{chain_name}_{code}"
    cached = cache_get(cache_key, CACHE_WEEKLY) or []
    last_cached_date = cached[-1]["date"] if cached else None

    registry = get_registry()
    providers = registry.get_ordered_providers(chain_name)

    new_data = []
    for provider in providers:
        if registry.is_circuit_broken(provider):
            continue
        try:
            # Provider 函数只返回新数据，不碰缓存
            new_data = _call_provider(provider, code, start_from=last_cached_date, days=days)
            registry.record_success(provider)
            break
        except Exception:
            registry.record_failure(provider)
            continue

    # chain 层统一合并 + 缓存写入
    merged = _merge_by_date(cached, new_data) if new_data else cached
    if new_data:  # 有增量时才写入
        cache_set(cache_key, merged)

    # 完整性校验：新获取的最后一个数据点与缓存对比
    if new_data and last_cached_date:
        _validate_continuity(cached, new_data, cache_key)

    return merged[-days:]


def _validate_continuity(cached: list[dict], new_data: list[dict], cache_key: str):
    """校验新旧数据连续性，检测历史修正信号。"""
    if not cached or not new_data:
        return
    last_old = cached[-2] if len(cached) >= 2 else cached[-1]
    first_new = new_data[0]

    # 检测日期重叠：新数据首日 ≤ 旧数据末日，说明有修正
    if first_new.get("date") <= last_old.get("date"):
        logger.warning(f"[{cache_key}] 新旧数据重叠——可能是历史修正，建议全量刷新")
        # 标记缓存需要下一次全量校验
        cache_set(f"{cache_key}_correction_flag", True, ttl=CACHE_DAILY)
    # 检测数据跳空
    elif _gap_days(last_old.get("date"), first_new.get("date")) > 5:
        logger.warning(f"[{cache_key}] 数据跳空 >5 交易日——部分历史不可达")


def _merge_by_date(cached: list[dict], new_data: list[dict]) -> list[dict]:
    """按日期合并去重，new_data 中同天数据覆盖 cached（修正感知）。"""
    seen = {d["date"] for d in cached}
    merged = list(cached)  # 保留已有顺序
    for d in new_data:
        if d["date"] in seen:
            _replace_by_date(merged, d)  # 覆盖旧数据（处理历史修正）
        else:
            merged.append(d)
    return sorted(merged, key=lambda x: x["date"])
```

**Provider 函数示例**（保持纯获取，不碰缓存）：

```python
# providers/tencent.py — 新增
def fetch_kline(code: str, days: int = 30, start_from: str | None = None) -> list[dict]:
    """获取股票历史 K 线（纯获取，由 chain 层管理缓存）。"""
    # ✅ C5：必须使用 make_http_client()
    client = make_http_client()
    params = {"code": code, "days": days}
    if start_from:
        params["start"] = start_from
    resp = client.get(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params=params)
    resp.raise_for_status()
    return _parse_kline(resp.json())
```

| 数据 | 方式 | TTL | 约束 |
|:-----|:-----|:----|:-----|
| F1 快照 JSON | 文件直写（持久记录，非缓存） | 永久（保留最近 12 份） | C3: `tempfile.mkstemp` + `os.replace` |
| F2 历史 K 线 | `cache/` 子包，chain 层增量合并 | 7 天 | C2, C6（`_fetch_with_incremental_fallback`） |
| F2 历史净值 | `cache/` 子包，chain 层增量合并 | 30 天 | C2, C6 |
| 会话级重复请求 | `DataSourceRegistry.session_cache` | 会话内 | C4 |
| 完整性校验标记 | `cache/` 子包，标记修正 | 1 天 | — |

---

## 5. 数据降级原则：同源同评级

历史价格数据与实时价格数据**同源，因此同层级**。现有降级系统（`DegradationTracker`）使用 T2/T3/T4 层级（不存在 T0/T1）。历史走势 section 的显示行为与普通数据不同——即使数据不可用也显示占位文本，不隐藏。

| Chain 类型 | Provider | 注册 tier | section 行为 |
|:-----------|:---------|:----------|:-------------|
| `history_stock` | Tencent/Sina | **T2**（与实时价格共享同 provider name，熔断器联动） | 始终可见（失败→占位文本） |
| `history_fund_otc` | Tiantian | **T3**（与实时净值共享同 provider name，熔断器联动） | 始终可见（失败→占位文本） |
| 指数（独立链路） | Tencent/Sina | T2 | 始终可见（失败→占位文本） |

**实现方式：** `registry.py` 中新增 `type="history"` 的 section 在 `section_visible_dict` 中**始终返回 `True`**（即使数据不可用），通过 `_data_status` 控制显示"不可用"提示而非隐藏。这与现有 B 系列模块的"数据不足→显示占位"模式一致。

**⚠ C14 约束**：`section_visible_dict` 必须通过 render context 或函数参数传递，**不得**写入 `_ENV.globals`、模块级 dict 等跨函数通信渠道。

`excel_module_loader.py` 中需新增 `type="history"` 的可见性分支（当前仅 `always`/`b_series`/`news`/`llm` 四种类型）：

```python
# excel_module_loader.py — 新增分支
_SECTION_HANDLERS = {
    "always": lambda flag: True,
    "b_series": lambda flag: flag is not None,
    "news": lambda flag: bool(flag),
    "llm": lambda flag: bool(flag),
    "history": lambda flag: True,  # 始终可见，数据状态由 _data_status 控制
}
```

```python
# section_visible_dict 构建（通过 render context 传递，不写入全局变量）
raw_data_flags = {
    # ... 现有 ...
    "portfolio_history": True if history_data else False,       # data_flag 控制数据有无
    "drawdown_analysis": True if history_data else False,
}
visible = _SECTION_HANDLERS.get(section["type"], lambda f: False)(raw_data_flags.get(section["data_flag"]))
```

### 5.2 失败场景行为

| 情景 | 行为 |
|:-----|:------|
| 主链路成功 | 正常生成走势章节 |
| 主链路失败 → 备用成功 | 走势章节标注"备用链路" |
| 全链失败 → 过期缓存可用 | 走势章节标注"过期数据" |
| 全链失败 + 无过期缓存 | 走势章节**写入占位文本**，明确告知用户失败原因 |

最后一种情景是最大变化：不静默跳过 section，而是显示占位文本，类似现有 B 系列模块的 `_write_placeholder` 模式。

### 5.3 STATUS_MESSAGES 新增

在 `data_status.py` 中新增：

```python
"history_price_unavailable": "历史行情获取失败，走势分析不可用。建议稍后重试或先执行菜单 1 预热缓存",
"history_nav_unavailable":   "基金历史净值获取失败，走势分析不可用。建议稍后重试或先执行菜单 1 预热缓存",
"history_degraded":          "历史走势数据来自降级链路",
"history_correction_detected": "检测到历史数据修正，走势曲线可能包含修正点。建议完全清除缓存后重拉取以获取最新数据",
"history_zero_value":        "部分交易日收盘价为 0（可能停牌或数据异常），已从走势中剔除",
```

**数据质量检查**：`PortfolioHistoryCalculator` 在返回走势数据前执行质量校验，将警告注入 `_data_status`：

```python
def _validate_bars(bars: list[dict]) -> list[str]:
    """返回质量问题警告列表。"""
    warnings = []
    for b in bars:
        if b.get("close", 0) == 0:
            warnings.append(f"{b['date']}: 收盘价为 0")
        if b.get("date", "") > datetime.now().strftime("%Y-%m-%d"):
            warnings.append(f"{b['date']}: 日期为未来")
    return warnings
```

---

## 6. 注册表变更

### 6.1 _REPORT_SECTION_DEFAULT（C7）

```python
# F2 新增 — type="history"：仅在成功获取历史数据后显示
{"key": "portfolio_history",  "name": "组合历史走势",  "number": 17, "type": "history", "data_flag": "portfolio_history"},
{"key": "drawdown_analysis",  "name": "回撤分析",       "number": 18, "type": "history", "data_flag": "portfolio_history"},

# F3 新增
{"key": "trend_comparison",   "name": "跨报告趋势",    "number": 19, "type": "history", "data_flag": "trend_data"},
```

- `type="history"` 为新增条件显示类型，在 `excel_generator.py` 中新增判断分支
- 失败/不可用时 section 显示占位文本（见 §5），不隐藏

### 6.2 _REPORT_SHEET_NAMES

```python
"portfolio_history": "组合历史走势",    # F2
"drawdown_analysis": "回撤分析",        # F2
"trend_comparison": "跨报告趋势",       # F3
```

### 6.3 registry.py DataModuleDef

```python
DataModuleDef("历史股票日线", "history_stock",
              cache_prefixes=("history_stock_",), cache_ttl=CACHE_WEEKLY,
              cache_groups=("preload",)),
DataModuleDef("历史基金净值", "history_fund_otc",
              cache_prefixes=("history_fund_otc_",), cache_ttl=CACHE_MONTHLY,
              cache_groups=("preload",)),
```

---

## 7. 分轮次实施计划（11 轮）

### 依赖图

```
R0 ─┬─→ R1 ─→ R2 ─→ R3                    (F1 完成, 4轮)
    │
    └──────────────→ R4 ─────────────────── (F2 数据, 1轮, 原R4+R5+R6合并)
                                    │
                    R0 ────────────→ R5 ─→ R6    (F2 完成, 6轮)
                                          │
                                          ├─→ R7     (F3 待定说明)
                                          ├─→ R8     (Bonus 1)
                                          └─→ R9     (Bonus 2)
```

每轮独立可回退。合并轮次内的子模块仍可单独测试。

---

### R0：基础设施与数据模型

**文件**：`data/history/snapshots/` 目录 + `schemas/history.py`（4 dataclass） + `constants.py` 常量

🔹 **验收**：空目录 + 4 dataclass 可实例化。  
⏪ 删除目录和文件，零影响。

---

### R1：快照持久化

**文件**：`report/history_snapshot.py` — `save()` / `load_latest()` / `list_all()` / `prune(max_count=12)`

**C3**：`save()` 使用 `tempfile.mkstemp` + `os.replace`

**竞争条件防护**：快照文件名使用**时间戳**（`snapshot_{timestamp}.json`），而非统一文件名：
- `load_latest()` 通过 `max(mtime)` 获取最新
- `list_all()` 按 mtime 降序返回
- 多进程同时写入互不覆盖

🔹 **验收**：save/load/list/prune 6 场景（含多文件竞争）；空目录返回 None。  
⏪ 删除整个 snapshot 目录。

---

### R2：差异计算引擎

**文件**：`fetcher/history_diff.py` — `HistoryDiff.compute(new, old) → DiffSummary`

**差异类型**：组合级 Δ 值、持仓级（新增/清仓/加仓/减仓）、分类迁移

**裁剪**：`DiffSummary.trim(top_n=5)` 减少 token 占用 60%

**基准日对齐**：`DiffSummary` 增加 `days_since_last_report` 字段，LLM 提示词注入"距上次报告 XX 天"上下文，报告中同时输出日均 Δ%

🔹 **验收**：7 用例覆盖全部类型 + 基准日对齐。  
⏪ 删除文件。

---

### R3：F1 LLM 注入 + 流程嵌入

> **注意**：R3 只做 LLM 差异注入。Excel Δ 列和汇总行 Δ 行移至 R6 实现（计算层与展示层分离）。

**修改**：
- `handlers_report.py`：`_cmd_generate_full()` 中嵌入快照读写 + 差异注入（不含 Δ 列生成）
- `generators.py`：`DiffSummary → prep`，含 `days_since_last_report` 字段
- `prompts.py`：差异感知提示词（"相比上次报告 X 天前"等）

**指纹去重**：`fingerprint` 比对，无实际变化时跳过差异段落生成

🔹 **验收**：首次无差异，第二次有"相比上次"；损坏快照不崩溃；LLM 输出含 XX 天前上下文。  
⏪ `git checkout` 恢复 3 文件。

---

### R4：历史数据 Provider 函数

3 个 Provider 的历史数据函数互无依赖，合为一轮一次性实现，验收时可独立回退：

**修改**：
- `providers/tencent.py` — 新增 `fetch_kline(code, days, start_from=None)`，端点 `web.ifzq.gtimg.cn/appstock/app/fqkline/get`
- `providers/sina.py` — 新增 `fetch_kline(code, days, start_from=None)`，端点 `money.finance.sina.com.cn/getKLineData`
- `providers/tiantian.py` — 新增 `fetch_fund_nav_history(code)`，复用现有 `pingzhongdata/{code}.js` JS 解析模式

**约束**：
- ✅ **C5**：所有 HTTP 请求**必须**使用 `make_http_client()`，不得直接实例化 `httpx.Client()`
- Provider 函数保持**纯数据获取**，不碰缓存层（缓存合并由 chain 层的 `_fetch_with_incremental_fallback()` 管理，详见 §4.3）

🔹 **验收**：mock 3 个端点正确解析；空数据返回 `[]`；净值字段缺失时静默降级；`make_http_client()` 使用确认。  
⏪ `git checkout` 恢复 3 文件。

---

### R5：Chain 注册 + PortfolioHistoryCalculator + 缓增量合并

**修改**：
- `chain.py`：注册 `history_stock` / `history_fund_otc` chains（§4.1），新增 `_fetch_with_incremental_fallback()` 方法
- `provider_registry.py`：**不新增独立 provider name**。`history_stock` chain 复用现有 `tencent`/`sina` provider，`history_fund_otc` 复用现有 `tiantian` provider，熔断器与实时数据共享
- `registry.py`：新增 DataModuleDef

**新文件**：`report/portfolio_history.py`

- `PortfolioHistoryCalculator` — 遍历持仓 → 按代码类型路由（A 股/ETF → history_stock，OTC → history_fund_otc，exclusion-based，先排除港股通和债券基金）→ 前先查 `session_cache`（C4）→ 调用 `_fetch_with_incremental_fallback()` → 计算回撤/波动率/收益率 → 走势前执行 `_validate_bars()` 质量检查
- 缓存合并逻辑在 chain 层（`_fetch_with_incremental_fallback`），Provider 只做纯数据获取

**数据质量**：`_validate_bars()` 返回警告注入 `_data_status`，见 §5.3

**约束**：C1（code_utils 组合逻辑）+ C4（session_cache）+ C5（make_http_client）+ C6（_fetch_with_incremental_fallback 必经）

**测试**：`test_portfolio_history.py`（unit_report）+ `test_history_chain_edge.py`（edge, C12）

🔹 **验收**：回撤计算误差 <0.01%；volatility 边界处理正确；chain 注册可用；增量合并正确（增量拉取→合并→去重→修正校验）；`_validate_bars()` 正确识别零值/未来日期。  
⏪ 还原 chain.py / provider_registry.py / registry.py。

---

### R6：F2 报告注入 + Excel Δ 列（F2 完成）

**修改**：
- `handlers_report.py`：
  - F2 触发逻辑（§3.2 二阶段询问 + `history.analysis` 配置解析）+ 全量重渲染模式
  - 数据拉取阶段输出 `[..] 正在拉取历史走势数据...` 等进度提示（复用 `tui_handlers.py` 已有模式）
- `excel_generator.py`：
  - 新增 `type="history"` section 渲染分支（始终可见，数据状态由 `_data_status` 控制）
  - `excel_module_loader.py` 新增 `"history"` 可见性类型分支（§5 代码示例）
  - **（从原 R3 移入）** 持仓明细页签新增"较上次"Δ 列（Δ 盈亏、Δ 盈亏率），汇总行新增"较上次报告变化"行
- `html_writer.py`：
  - 新增走势/回撤章节（全量重渲染，不追加 HTML）
  - **走势图标注 as-if 语义**：标题旁追加 `<span class="assumption-badge">基于当前持仓 × 历史价格</span>` 芯片徽标
  - **Chart.js 双 CDN fallback**：模板中依次尝试 jsDelivr → unpkg，均在 `<head>` 中预加载
- `registry.py`：新增 `_REPORT_SECTION_DEFAULT` + `_REPORT_SHEET_NAMES`
- `data_status.py`：新增 §5.3 的 5 条 STATUS_MESSAGES

**约束**：C7（registry 注册）+ C14（render context 传递，不写入 `_ENV.globals`）

**降级行为**：API 全失败 → 走势章节**显示占位文本**（§5.2），告知用户失败原因和恢复建议。section 始终通过 `section_visible_dict` 显示，不隐藏。

**全量重渲染**：一次收集全部数据（含/不含历史）后渲染完整 HTML/Excel，不在已完成的 HTML 上"追加"写入。

**走势图标题语义标注**：Excel 走势 sheet 底部追加脚注行 `⚠ 注：曲线假设当前持仓在过去 N 天份额不变（as-if 语义），历史数据可能与实际持仓不符`。

🔹 **验收**：
- `history.analysis: "prompt"` → 报告完成后询问，选 Y 时输出 `[..] 正在拉取历史走势数据...` 进度提示 → 生成走势；选 N 跳过
- `history.analysis: "auto"` → 缓存命中率 >80%（而非全命中）时自动拉取缺失部分
- `history.analysis: "off"` → 不询问不生成
- API 全链路失败 → 走势章节写入 `STATUS_MESSAGES["history_price_unavailable"]` 占位文本，不隐藏 section
- 备用链路成功 → 走势章节标注"备用链路"
- Excel Δ 列正确显示较上次报告的 Δ 盈亏/Δ 盈亏率；首次生成时 Δ 列显示"—"
- HTML 图标题旁显示 as-if 徽标；Excel 脚注显示 as-if 声明

⏪ 关闭配置 `history.analysis: "off"`。

---

### R7：F3 跨报告趋势（待定）

F3 不在需求验证前投入 SQLite 架构设计成本。保留为待定状态，待用户使用 F2 后提出相应需求时再启动详细设计。

**进入条件**：用户使用 F2 后提出"过去 N 次报告的趋势对比"需求。

**实现提示**：
- Python 内置 `sqlite3`，4 张表（`report_snapshots` / `snapshot_holdings` / `daily_bars` / `nav_history`）
- 双写策略参考当前 `data/cache` + `data/history` 的双路径模式
- 不提前设计：避免在需求验证前投入架构决策成本

🔹 **验收**：保持待定状态，不实施。  
⏪ 无实施，无需回退。

---

### R8：基准对比（Bonus 1）

**修改**：`fetcher/index.py` 新增 `fetch_index_history`；`portfolio_history.py` 增加对比逻辑

**报告**：组合 vs 沪深 300 曲线同图（HTML Chart.js）

---

### R9：可视化优化（Bonus 2）

**HTML**：Chart.js CDN 绘制市值走势 / 回撤曲线 / 分类演变  
**Excel**：Δ 列条件格式（绿涨红跌）；迷你图

---

## 8. 测试策略

### Marker 注册（C11）

`conftest.py` 追加：
```python
"history": "历史数据获取与计算测试用例",
```

### 测试文件归属

| 文件 | Marker | 说明 |
|:-----|:-------|:-----|
| `test_history_schemas.py` | `unit_schemas` | R0 |
| `test_history_snapshot.py` | `unit_report` | R1 |
| `test_history_diff.py` | `unit_fetcher` | R2 |
| `test_portfolio_history.py` | `unit_report` | R5 |
| `test_history_chain_edge.py` | `edge` | R5，**`*_edge.py`**（C12） |
| `test_history_placeholder.py` | `integration` | R6：验证失败场景占位文本渲染 |

### 路径隔离（C13）

`conftest.py` 的 `_isolate_sensitive_paths` 追加：
```python
_redirect("data/history", tmp_path / "history")
```

---

## 9. 技术债务

| # | 债务项 | 类型 | 引入轮次 | 说明 | 偿还时机 |
|:--|:-------|:-----|:---------|:-----|:---------|
| TD-1 | **份额不变假设** | 设计简化 | R7 | F2 as-if 语义假设份额不变 | F3 稳定后引入变更事件 |
| TD-2 | **无 pandas 手写时间序列** | 架构约束 | R7 | 时间对齐/缺失填充手写，保持零依赖。**风险已升级**（核心风险）——手写代码 bug 概率高于 pandas | 永不（架构决策），但需**双路验证**：手写实现 + 确定性测试（已知输入→已知输出）验证回撤/波动率 |
| TD-3 | **LLM 提示膨胀** | 性能 | R3+R8 | 差异+趋势数据 ~2-3k tokens | R8 后评估，>20% 则裁剪 |
| TD-4 | **历史数据质量检查** | 数据完整性 | R6 | §5.3 `_validate_bars()` 已实现（零值/未来日期检测）。持续构建结果不可写入性能关键路径 | R6 已前移实现 |
| TD-5 | **指数比较锁死沪深300** | 灵活性 | R12 | config 硬编码 | 用户要求多基准时扩展 |
| TD-7 | **报表离线无图** | 功能局限 | R6+R9 | Chart.js 依赖 CDN。实现策略改为双 CDN fallback（jsDelivr → unpkg），默认不内联 | FAQ 说明离线激活方法 |
| TD-10 | **历史拉取并行上限 hardcode** | 运维 | R6 | 默认 4 线程，无配置化 | 如需调优则移到 config.json |

---

## 10. 风险与控制

| # | 风险 | 概率 | 影响 | 控制措施 |
|:--|:-----|:-----|:-----|:---------|
| R1 | **Tencent/Sina 历史 API 变更** | 中 | F2 不可用 | Provider Chain 双链路 + 过期缓存降级 + 连续性校验感知修正；F1 不受影响 ✅ |
| R2 | **15s+ 耗时增加** | 高 | 体验下降 | 二阶段触发（不强制）；拉取时输出 `[..] 正在拉取历史走势数据...` 进度提示 ✅ |
| R3 | **LLM token 增加** | 中 | 成本上升 | `trim(top_n=5)` 裁剪差异数据；F1 指纹去重避免无变化时生成 ✅ |
| R4 | **历史熔断误阻断实时价格** | 低 | 实时行情被波及 | **已消除** — 不创建独立 provider name，`tencent`/`sina` 共享同一熔断器，不存在"历史熔断阻断实时" |
| R5 | **用户删除了 snapshots 目录** | 低 | F1 无对比 | 退化为 `is_first_check`，下次生成时重建 ✅ |
| R6 | **F2 section 显示逻辑遗漏** | 中 | 报告无走势章节 | C7 注册 + `type="history"` 分支（`excel_module_loader.py`）+ `section_visible_dict` 强制可见（render context 传递，遵守 C14）|
| R7 | **历史数据修正被增量合并静默覆盖** | 中 | 走势曲线含过时数据 | `_validate_continuity()` 检测日期重叠 → 标记 `correction_flag` → 全量刷新 ✅ |
| R8 | **`tencent` 熔断误阻断历史链路** | 低 | F2 降级走 Sina | 同 provider name 设计是特性而非缺陷——`tencent` 实时不通时历史必然不通，自动 fallback 到 `sina` |
| R9 | **手写时间序列计算精度** | 中 | 指标偏差 | TD-2 双路验证：确定性测试（已知输入→已知输出）+ 手写实现对比 pandas 计算值 |

---

## 附录：设计约束遵守检查

| 约束 | 相关？ | 状态 |
|:-----|:-------|:-----|
| C1 代码类型判定中心化 | 是 — F2 区分股票/基金/指数 | ✅ `code_utils` |
| C2 缓存统一管理 | 是 — F2 历史 K 线/净值缓存 | ✅ `cache/` 子包 |
| C3 缓存原子写入 | 是 — F1 快照文件 | ✅ 强制 `tempfile.mkstemp`+`os.replace` |
| C4 会话级 API 复用缓存 | 是 — F2 重复请求 | ✅ `DataSourceRegistry.session_cache` |
| C5 HTTP 客户端统一 | 是 — F2 所有 HTTP 请求 | ✅ `make_http_client()`，R4 实施时强制校验 |
| C6 Provider Chain 必经 | 是 — F2 历史数据 | ✅ 新增 `_fetch_with_incremental_fallback()` 在 chain 层管理熔断预检 + Provider 遍历 + 增量合并，Provider 函数保持纯数据获取。无规避 |
| C7 报告序号不可硬编码 | 是 — F2/F3 新增章节 | ✅ 注册 `_REPORT_SECTION_DEFAULT` |
| C8 日志统一 | 是 | ✅ `logging.getLogger("invest")` |
| C9 LLM 模块注册 | 否 | ✅ 不新增 LLM 模块 |
| C10 新闻召回策略 | 否 | ✅ 不相关 |
| C11 测试标记强制 | 是 — 新增测试 | ✅ 注册 `history` marker |
| C12 边缘测试文件隔离 | 是 — API 失败场景 | ✅ `*_edge.py` |
| C13 测试敏感路径隔离 | 是 — F1/F2 测试 | ✅ `data/history/` 重定向 |
| C14 渲染期数据不可写入模块级全局变量 | 是 — F2 走势数据 + `type="history"` 可见性分支 | ✅ render context 传递，不写入 `_ENV.globals` 或模块级 dict |
