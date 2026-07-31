# 交互式 HTML 报告升级（Chart.js 实施方案）

> **关系**：本文档 = 实施方案；关联的风险/收益/架构分析见 [`plan-chartjs-risk-analysis.md`](./plan-chartjs-risk-analysis.md)。
>
> 二者共同组成 plan-1 的完整设计方案：实施方案聚焦"怎么做"，风险分析聚焦"为什么这么做"。
>
> **文档版本**：v0.8.7-dev · 估算：**5.25d** · 迭代：8 轮

---

## 目录

1. [概述](#1-概述)
2. [当前状态与数据就绪度](#2-当前状态与数据就绪度)
3. [架构约束遵从](#3-架构约束遵从)
4. [实现策略](#4-实现策略)
5. [迭代计划（8 轮 × 验收标准）](#5-迭代计划8-轮--验收标准)
6. [涉及文件清单](#6-涉及文件清单)
7. [技术方案对比](#7-技术方案对比)

---

## 1. 概述

### 1.1 做什么

将当前 HTML 报告中 6 张使用 Canvas 2D API / 纯表格渲染的图表替换为 Chart.js 交互式图表：

| # | 图表 | 当前状态 | 改造方式 |
|:-:|:-----|:---------|:---------|
| 1 | 净值趋势（Line） | Canvas `drawSimpleChart()` | 迁移为 Chart.js 折线图 |
| 2 | 最大回撤（Line） | Canvas `drawSimpleChart()` | 迁移为 Chart.js 折线图 |
| 3 | 资产构成（Doughnut） | 纯表格文本 | 新建 Chart.js 环形图 |
| 4 | 行业分布（Horizontal Bar） | 纯表格文本 | 新建 Chart.js 水平柱状图 |
| 5 | 穿透 TOP10（Bar） | 纯表格文本 | 新建 Chart.js 柱状图 |
| 6 | 量化指标（Radar） | 纯表格文本 | 新建 Chart.js 雷达图 |

> 相关性矩阵（Heatmap）依赖 plan-2 提供 `correlation_data`，plan-1 仅建热力图框架。

### 1.2 边界（不做什么）

- **不引入新数据源** — 所有图表数据复用现有 template context
- **不新增报告模块** — 不改 `_REPORT_SECTION_DEFAULT`，不改 `html_renderers.py`
- **不改变 Excel 管线** — 仅 HTML 端变化
- **不引入后端渲染** — Chart.js 完全客户端侧
- **不替代现有 Canvas** — Feature Flag 控制，保留 Canvas 路径
- **C14 零容忍** — 所有数据通过 `render()` context 传递，不写 `_ENV.globals`

### 1.3 图表映射到现有模板章节

| 图表 | 目标模板章节 | 章节 ID | 现有内容 |
|:-----|:------------|:--------|:---------|
| 净值趋势 Line | MODULE 17: 组合历史走势 | `sec-portfolio_history` | Canvas 图 + 3 张摘要卡片 |
| 最大回撤 Line | MODULE 18: 回撤分析 | `sec-drawdown_analysis` | Canvas 图 |
| 资产构成 Doughnut | MODULE 3: 持仓分类表 | `sec-category` | 纯表格 |
| 行业分布 Horizontal Bar | MODULE 4: 资产穿透 TOP10 | `sec-penetration` | 表格 + 行内行业标签 |
| 穿透 TOP10 Bar | MODULE 4: 资产穿透 TOP10 | `sec-penetration` | 表格 |
| 量化指标 Radar | MODULE 17: 组合历史走势 | `sec-portfolio_history` | 3 张摘要卡片 → 增强为雷达图 |

> **说明**：所有图表作为**已有章节的视觉增强**，不新增 `_REPORT_SECTION_DEFAULT` 条目（C7 合规）。行业分布与穿透 TOP10 同属一个章节，一图一表并排显示。量化指标雷达图替换/增强现有 `sec-portfolio_history` 中的 3 张摘要卡片。

### 1.3 总工作量

| 阶段 | 工时 | 说明 |
|:-----|:----:|:------|
| 基础设施搭建 | 1.0d | Python 预处理器 + JS 外部化 + CDN SRI + Feature Flag |
| 净值曲线迁移 | 0.75d | 2 张 Canvas→Chart.js + 三级降级 + `beforeprint` |
| 4 张新图构建 | 1.0d | 资产构成/行业分布/穿透 TOP10/量化指标 |
| 热力图框架（预留） | 0.5d | 矩阵插件集成 + 空状态渲染 |
| Python 端测试 | 0.5d | 预处理器单元测试 + Feature Flag 测试 + 降级测试 |
| 集成验证 | 0.5d | 双路径回退验证 + 打印降级验证 + 浏览器兼容性 |
| 代码审查 + 文档 | 0.5d | C14 自检 + 交叉引用更新 + review-findings 记录 |
| 缓冲 | 0.5d | POC 验证、打印时序调试、CDN 加载问题排查 |
| **合计** | **5.25d** | 原估 4d，上调 +1.25d（新增预处理器 + 测试 + JS 外部化） |

---

## 2. 当前状态与数据就绪度

### 2.1 数据依赖矩阵

| 图表 | 数据源 | 就绪状态 | 预处理需求 |
|:-----|:------|:--------:|:-----------|
| **净值趋势** | `history_data.bars` + `history_data.benchmarks` | ✅ 直接 `tojson` | 下采样（可选） |
| **最大回撤** | `history_data.bars[drawdown_pct]` | ✅ 同数据源 | 复用净值数据 |
| **穿透 TOP10** | `penetration["top10"]` | ✅ 就绪 | 排序 + 格式化 |
| **资产构成** | `details` 列表 | ⚠ 缺市值聚合 | 按 `code_type` 聚合市值 |
| **行业分布** | `details` + `penetration["sector"]` | ⚠ 缺行业聚合 | 交叉计算行业市值 |
| **量化指标** | `info["risk_metrics"]` + 7 项 `metrics_*` Flag | ⚠ 分散 | 统一收集 + Flag 检查 |
| **相关性矩阵** | 依赖 plan-2 的 `correlation_data` | ⏳ 不可做 | 留待 plan-2 |

### 2.2 渲染管线现状

```
orchestrator.py → history_data (dict)
   ↓
html_writer.py → write_html_report(info, history_data, ...)
   ↓  render(context={history_data, section_visible, ...})
report_template.html (1845 行 Jinja2 模板)
   ├── drawSimpleChart()     ← 内联 Canvas 2D，第 265-513 行
   ├── <canvas id="portfolioChart">   ← 净值曲线，第 1448 行
   ├── <canvas id="drawdownChart">    ← 回撤图，第 1560 行
   ├── tojson 序列化数据到内联 <script> 块（4 处）
   └── 其余模块均为表格/文本渲染
```

**关键**：`history_data` schema 在 `portfolio_history.py` 定义，通过 `tojson` 直接序列化到浏览器。Chart.js 可直接消费 `history_data.bars` + `history_data.benchmarks`。

---

## 3. 架构约束遵从

### 3.1 重点约束

| 约束 | 适配方式 | 检查点 |
|:-----|:---------|:------|
| **C14** 渲染期数据不写 `_ENV.globals` | 所有 chart data 通过 `render()` context → `chart_datasets` 字典 | 代码审查 grep `_ENV.globals\[` 不得出现在非 `html_jinja_env.py` |
| **C19** pipeline_data Schema | 仅 `tojson` 复用 → 不需新 Schema；仅当新增 `chart_datasets` 进 pipeline 时才需注册 | 当前方案：只传 template context |
| **§1.4.4** Feature Flag | `config/features.py` 注册 `enable_interactive_charts: True` | features.json 可覆盖 |
| **§1.4.5** 数据降级 | 三级：ok→实线 / degraded→虚线 / unavailable→占位 | 复用 `data_status_history` |
| **C7** 报告序号 | 不改 `_REPORT_SECTION_DEFAULT`，仅增强已有模块 | |
| **C16** 路径绝对化 | 本地 bundle 已降级为 P2 未来增强，Iter 1 不涉及 | |

### 3.2 不变约束

| 约束 | 说明 |
|:-----|:------|
| C1/C2/C3/C4/C5/C6 | ✅ 无关 — 不新增数据获取，不新增缓存 |
| C8/C15 | ✅ 无关 — 客户端 JS 不经 Python 日志 |
| C10 | ✅ 无关 — 不涉及新闻系统 |
| `html_renderers.py` | **保持不改** — 14 个渲染函数返回值不变 |
| `html_jinja_env.py` | **不新增 globals** — 仅保持 `section_visible` 唯一条目 |

---

## 4. 实现策略

### 4.1 Python 端数据预处理器（`chart_data_builder.py`）

在 Python 侧将原始数据转换为 Chart.js 数据集格式，使 JS 端只渲染已格式化数据：

```python
# src/python/report/chart_data_builder.py
def build_chart_datasets(
    history_data: dict | None,
    cat_data: list,
    penetration: dict | None,
    perf_data: list,
    details: list,
    risk_metrics: dict | None = None,    # 量化指标（仅 full 路径有 prep 注入）
    all_metrics: dict | None = None,     # compute_all_metrics() 返回值（14 项，仅 full 路径）
) -> dict:
    """返回 dict → template context → chart-init.js 消费（C14 合规）。

    关键数据源：
    - risk_metrics: 源自 prep["risk_metrics"]（5 个基本字段，仅 full 路径有）
    - all_metrics:  源自 orchestrator 中 compute_all_metrics() 返回值（14 项全量指标）
      仅 full 路径有此数据；both 路径均为 None。
    - 降级兜底：当 both 路径传入 None 时，_build_radar_dataset 从 history_data
      提取 annualized_volatility / max_drawdown_pct / total_return_pct 3 个基本轴。
    """
    from src.python.features import is_feature_enabled

    datasets = {}
    if history_data and history_data.get("status") != "unavailable":
        datasets["portfolio_line"] = {
            "labels": [b["date"] for b in history_data["bars"]],
            "datasets": [{
                "label": "组合净值",
                "data": [b["total_value"] for b in history_data["bars"]],
                "borderColor": "var(--chart-primary)",
            }],
            "benchmarks": _build_benchmark_datasets(history_data.get("benchmarks", [])),
        }
        datasets["drawdown"] = {
            "labels": [b["date"] for b in history_data["bars"]],
            "datasets": [{
                "label": "回撤",
                "data": [b["drawdown_pct"] * 100 for b in history_data["bars"]],
                "backgroundColor": "var(--chart-danger-transparent)",
            }],
        }
        datasets["radar"] = _build_radar_dataset(history_data, all_metrics, risk_metrics)
    # ... 其余 3 图（参见 chart_data_builder.py 完整实现）
    return datasets

def _build_radar_dataset(
    history_data: dict | None,
    all_metrics: dict | None,
    risk_metrics: dict | None,
) -> dict:
    """构建雷达图数据集——三级降级优先级：
      1. all_metrics（14 项全量，仅 full 路径）
      2. risk_metrics（5 基本字段，仅 full 路径）
      3. history_data 内部提取（annualized_volatility / max_drawdown_pct / total_return_pct，
         双路径均有——确保 both 路径也能显示 3 个基本轴）
    """
    if all_metrics:
        # 14 项全量指标 → 7-10 个有效轴（按 metrics_* Flag 过滤）
        pass
    elif risk_metrics:
        # 5 基本字段 → 3-5 个轴
        pass
    elif history_data:
        # 从 history_data 提取基本字段 → 3 个基本轴（both 路径兜底）
        _fields = {
            "annualized_volatility": history_data.get("annualized_volatility"),
            "max_drawdown_pct": history_data.get("max_drawdown_pct"),
            "total_return_pct": history_data.get("total_return_pct"),
        }
        if any(v is not None for v in _fields.values()):
            # 构建 3 轴降级雷达
            pass
    # ... 根据 metrics_* Feature Flag 过滤后构建雷达轴
```

**收益**：
- ✅ 可用 pytest 单元测试
- ✅ JS 端只需渲染已格式化数据
- ✅ 新增 chart（plan-3/6）只需扩展此函数

### 4.2 JS 外部化（`chart-init.js` + `chart-config.js`）

| 文件 | 职责 | 是否可测 |
|:-----|:------|:--------:|
| `chart-init.js` | 6 个 Chart.js 初始化函数 | 独立 HTML 调试页 |
| `chart-config.js` | 颜色/字体/主题常量（CSS 变量驱动） | 与模板解耦 |

**⚠ JS 文件交付**：JS 文件存放于 `src/python/tmpl/`，但 HTML 报告生成在 `reports/`。`html_writer.py` 需在渲染后将 `chart-init.js` 和 `chart-config.js` **拷贝**到输出目录（与 HTML 同目录）。已有的 `html_save.py` 扩展（或在 `write_html_report()` 尾部追加）：

```python
import shutil
_JS_EXTERNAL = ["chart-config.js", "chart-init.js"]
for fname in _JS_EXTERNAL:
    src = os.path.join(os.path.dirname(__file__), "tmpl", fname)
    dst = os.path.join(output_dir, fname)
    shutil.copy2(src, dst)
```

> 若日后采用本地 bundle 方案，chart.min.js 也需一并拷贝。

模板中引用相对路径（与 HTML 同目录）：
```jinja2
{% if enable_interactive_charts %}
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"
          integrity="sha384-ABC123..."  {# 手动计算后硬编码，非模板变量 #}
          crossorigin="anonymous"
          onerror="window.__CHART_CDN_FAILED=true"></script>
  <script src="chart-config.js"></script>
  <script src="chart-init.js"></script>
{% endif %}
<canvas id="chart_{{ key }}"></canvas>
```

**⚠ chart-init.js 安全守卫** — chart-init.js 内每个图表初始化必须包含 CDN 失败检测 + canvas 存在检测：

```javascript
(function(){
  if (window.__CHART_CDN_FAILED) return;
  var el = document.getElementById('chart_portfolio');
  if (!el) return;
  new Chart(el, { ... });
})();
```

> **收益**：CDN 失败时跳过所有初始化（不会抛 `Chart is not defined`）；section_visibility 隐藏的模块因 canvas DOM 不存在而自动跳过。

### 4.3 CDN + onerror 降级策略

项目无构建工具链，采用**最简 CDN 方案**：

```
CDN (jsdelivr) + SRI hash（硬编码）+ onerror Canvas 降级
  └→ CDN 加载失败或 SRI 校验不通过 → window.__CHART_CDN_FAILED=true → 启用 Canvas 2D / 表格
```

SRI hash 由开发者手动计算一次，硬编码在模板中，非构建步骤：
```bash
# 仅在升级 Chart.js 版本时执行，非日常构建
curl -sL https://cdn.jsdelivr.net/npm/chart.js@4.x/dist/chart.umd.min.js \
  | openssl dgst -sha384 -binary | base64
# 输出直接填入 <script integrity="sha384-输出">，不作为模板变量
```

> **本地 bundle 方案**已降级为 P2 未来增强（用户反馈 CDN 不可达时再实施），不纳入 Iter 1 范围。当前项目无内网/离线运行需求，CDN + onerror 降级已足够。

### 4.4 三级降级渲染

| `history_data.status` | Chart.js | 视觉 |
|:----------------------|:---------|:------|
| `"ok"` | 正常交互 | 实线 + 完整 tooltip |
| `"degraded"` | 虚线样式标注 + 降级消息底部显示 | `borderDash: [5, 5]` |
| `"unavailable"` | 占位文本 + 不初始化 Chart.js | "历史走势数据暂不可用" |

### 4.5 打印降级方案

```
window.addEventListener('beforeprint', () => {
  // 预渲染所有 chart 快照到 <img>
  Object.values(Chart.instances).forEach(chart => {
    const img = document.createElement('img');
    img.src = chart.toBase64Image({width: chart.width * 2});
    chart.canvas.parentNode.insertBefore(img, chart.canvas);
    chart.canvas.style.display = 'none';
  });
});
window.addEventListener('afterprint', () => {
  // 恢复 canvas，清理临时 img
  document.querySelectorAll('img[data-chart-print]').forEach(el => el.remove());
  document.querySelectorAll('canvas[data-chart-print]').forEach(el => el.style.display = '');
});
```
```

### 4.6 CSS 变量颜色方案（plan-11 预留）

```css
:root {
  --chart-primary: #3366CC;
  --chart-secondary: #FF9900;
  --chart-danger: #CC0000;
  --chart-grid: #E0E0E0;
  --chart-bg: #FFFFFF;
}
```

```javascript
// chart-config.js
const chartTheme = {
  primary:   getComputedStyle(document.documentElement)
                .getPropertyValue('--chart-primary').trim() || '#3366CC',
  // ...
};
```

### 4.7 双路径清理计划

```
稳定 2 个版本后（如 v0.10.0）：
  ✅ 删除模板 drawSimpleChart() 定义
  ✅ 删除 Canvas fallback 分支
  ✅ 删除 Feature Flag 条件判断
  ✅ Chart.js 成为唯一渲染器
```

---

## 5. 迭代计划（8 轮 × 验收标准 × 测试范围）

### 迭代依赖关系

```
Iter 1（基础设施）────→ Iter 2（净值曲线）────→ Iter 7（集成）────→ Iter 8（终审）
         │                       │
         ├──→ Iter 3（资产构成）──┤
         ├──→ Iter 4（行业分布）──┤     Iter 3-6 互相独立，
         ├──→ Iter 5（穿透TOP10）─┤     可任意顺序实施
         └──→ Iter 6（量化指标）──┘
```

**约束**：
- Iter 2 依赖 Iter 1（需要预处理器 + CDN + Feature Flag 基础设施）
- Iter 3-6 依赖 Iter 1（需要预处理器骨架 + chart-init.js 加载框架），但**不依赖 Iter 2**
- Iter 7 依赖 Iter 1-6 全部完成（全链路集成验证）
- Iter 8 为终审轮，依赖所有前置轮次

### 迭代 1：基础设施搭建（1.0d）

**目标**：Python 预处理器 + Feature Flag 注册 + CDN 集成 + 模板 context 注入 + `risk_metrics` 数据流

| 任务 | 涉及文件 | 测试范围 |
|:-----|:---------|:---------|
| `config/features.py` 注册 `enable_interactive_charts: True` + 更新分类注释 `2→3 项` | `config/features.py` | ✅ `is_feature_enabled("enable_interactive_charts")` 默认 True ✅ `features.json` 可覆盖 ✅ 未知 flag 返回 False（已有 `_auto_reset_feature_flags` fixture 自动清理） |
| `chart_data_builder.py`（完整 6 图骨架 + 净值/回撤数据集 | `chart_data_builder.py` | ✅ 输入 `history_data` → 输出正确 JSON 格式 ✅ ok/degraded/unavailable 三级 ✅ 空/None 输入返回空 dict |
| `html_writer.py` context 注入 `chart_datasets` + `enable_interactive_charts` + 新增参数支持 | `html_writer.py` | ✅ `write_html_report()` 新增 `chart_datasets: dict \| None = None`、`enable_interactive_charts: bool = False` 参数 ✅ Flag OFF 时 context 不含 chart_datasets ✅ `chart_datasets` 传入后正确进入 render() context ✅ **不新增 `_ENV.globals` 条目** |
| `orchestrator.py` 整合 metrics 并传入 html_writer + Feature Flag 读取 | `orchestrator.py` | ✅ full 路径：`prep["risk_metrics"]` + `_metrics` → 合并后调用 `build_chart_datasets()` → `write_html_report(chart_datasets=..., enable_interactive_charts=...)` ✅ both 路径：无 `_metrics` → 传入 None，`build_chart_datasets()` 从 `history_data` 提取 3 个基本轴 ✅ Feature Flag 在 orchestrator 读取：`enable_interactive_charts = is_feature_enabled("enable_interactive_charts")` → 作为参数传入 html_writer（与 enable_b_series/enable_news 模式一致） ✅ **不跳过 build_chart_datasets()**——纯计算 ~5ms，全量执行，html_writer 靠 Flag 控制 context 注入 |
| `chart-config.js`（CSS 变量 + 颜色常量） | `chart-config.js` | ✅ 所有色值使用 `var(--chart-*)`，无硬编码 ✅ 变量缺失时用备选色值 |
| `chart-init.js` 加载骨架 + 净值/回撤图初始化函数占位 | `chart-init.js` | ✅ 独立 test HTML 页渲染验证 ✅ CDN 加载失败时 Canvas 回退 |
| 模板 CDN SRI + Feature Flag 分支 + `data_unavailable` + chart canvas 容器 | `report_template.html` | ✅ CDN 标签含 `integrity` + `crossorigin` + `onerror` ✅ Flag OFF → 无 Chart.js 标签 ✅ `data_unavailable=True` → 显示"暂无数据"横幅 ✅ 复用 `_render_template` + BeautifulSoup 验证结构 |

**验收标准（可度量）**：
1. ✅ `pytest src/test/test_chart_data_builder.py` — ≥6 个用例（正常 portfolio + 正常 drawdown + 空 history + degraded + unavailable + None）：全部通过
2. ✅ `pytest src/test/test_feature_interactive.py` — ≥3 个用例（默认值 + 覆盖 + 未知 flag）：全部通过
3. ✅ `pytest src/test/unit/report/test_html_report_structure.py` — 不新增 case（现有结构不变），且已有 case 全部通过  
   ⚠ 前置：`_build_minimal_render_data()` 需新增 `chart_datasets={}` 和 `enable_interactive_charts=False`，确保现有测试获得安全默认值
4. ✅ Flag OFF 渲染 → HTML 中无 Chart.js CDN `<script>`，模板 `<canvas>` 容器尺寸正确
5. ✅ Flag ON 渲染 → HTML 中包含 `<script id="chart-data">` + CDN script + chart-config.js + chart-init.js
6. ✅ Feature Flag 读取位置验证：orchestrator 使用 `is_feature_enabled()` 读取，作为参数传入 html_writer（与 enable_b_series 等 config 标志一致），html_writer 内部不自行读取
7. ✅ DegradationTracker 兼容性确认：Chart.js 三级降级（ok/degraded/unavailable）基于 `history_data.status`，与 DegradationTracker 的 T1~T4 数据源降级系统正交，无冲突

**测试范围边界**：
- ✅ 测：Python 预处理器 2 个 dataset（portfolio_line + drawdown）、Feature Flag 注册、context 注入、模板结构
- ❌ 不测：JS 端渲染效果（浏览器环境 → Iter 7 手动验证）、Excel 管线（不变 → 不测）、其他 4 图预处理器（留至 Iter 3-6）

### 迭代 2：净值曲线 + 回撤图迁移（0.75d）

**目标**：2 张 Canvas→Chart.js 折线图，含基准对比 + 三级降级 + 打印 fallback

| 任务 | 测试范围 |
|:-----|:---------|
| 净值曲线 Chart.js 折线图（主数据 + 基准线 + 图例切换 + 框选缩放） | ✅ `chart_data_builder` portfolio_line dataset 输出与 Canvas 版本数值一致 ✅ 多 dataset 渲染（组合 + 基准） |
| 回撤图迁移（双轴图：净值线 + 底部回撤填充） | ✅ drawdown dataset 回撤值与 `compute_all_metrics` 一致 |
| 三级降级渲染：`ok→实线` / `degraded→虚线+降级消息` / `unavailable→占位` | ✅ Python 端预处理器输出正确样式标记 ✅ 降级消息与 `data_status_history` 同步 |
| `beforeprint` / `afterprint` 打印降级 | ✅ print→canvas→img 替换 ✅ print 后 canvas 恢复 ✅ 2x DPI |

**验收标准**：
1. ✅ `test_chart_data_builder.py` 新增 ≥4 个用例（portfolio_with_benchmarks + drawdown + degraded_output + unavailable_output）：全部通过
2. ✅ `history_data.status = "degraded"` → chart 预处理器输出中含 `borderDash: [5, 5]` 标记+降级消息
3. ✅ `history_data.status = "unavailable"` → `build_chart_datasets()` 返回空 dict，模板不初始化 Chart.js
4. ✅ `window.print()` → chart→img 替换成功，打印输出不含白图（手动验证）
5. ✅ Feature Flag OFF → 自动回退 Canvas `drawSimpleChart()`，模板结构回归测试通过

**测试范围边界**：
- ✅ 测：chart_data_builder 4 个新增用例、三级降级 Python 端逻辑
- ❌ 不测：Canvas drawSimpleChart 回归（未修改 → 仅验证 Flag OFF 时模板加载）、其他 4 张新图（尚未实施）、JS 打印时序细节（手动验证）

### 迭代 3：资产构成 Doughnut（0.25d）

**目标**：纯表格 → 交互式环形图

| 任务 | 预处理器 | 测试范围 |
|:-----|:---------|:---------|
| `chart_data_builder.py` 新增资产构成 dataset | `details → 按 code_type 聚合市值` | ✅ 聚合结果与 Excel 分类汇总一致 ✅ details 为空 → 空数据集 ✅ total_mv=0 → 占位 |
| `chart-init.js` 新增 Doughnut 初始化 | | ✅ 占比 + 金额 tooltip（手动验证） ✅ 图例点击展开 |

**验收标准**：
1. ✅ `test_chart_data_builder.py` 新增 ≥2 个用例（资产聚合、空 details）：全部通过
2. ✅ 各资产类型占比与 Excel 汇总表偏差 < 0.01%
3. ✅ 空持仓时 Chart.js 显示"无持仓数据"占位
4. ✅ `data_unavailable=True`（持仓有成本但市值为 0）→ 预处理器输出空数据集，模板不初始化 Chart.js，显示"暂无数据"横幅（交叉验证 Iter 1 模板测试）
5. ✅ 图例点击隐藏/显示对应扇区（手动验证）

**测试范围边界**：
- ✅ 测：Python 端聚合逻辑、空输入边界
- ❌ 不测：JS tooltip 交互细节（手动验证）、其他 5 张图

### 迭代 4：行业分布 Horizontal Bar（0.25d）

**目标**：纯表格 → 交互式水平柱状图

| 任务 | 预处理器 | 测试范围 |
|:-----|:---------|:---------|
| `chart_data_builder.py` 新增行业分布 dataset | `details + penetration[sector] → 按行业聚合` | ✅ 行业归属与穿透表一致 ✅ push2 全失败 → `penetration` 中 sector 为空 → 占位 |
| `chart-init.js` 新增 Horizontal Bar 初始化 | | ✅ 排序切换（手动验证） ✅ 悬停详细值（手动验证） |

**验收标准**：
1. ✅ `test_chart_data_builder.py` 新增 ≥2 个用例（正常行业聚合、全无行业数据）：全部通过
2. ✅ 行业市值占比与穿透模块计算结果一致
3. ✅ 行业数据全不可用时 Chart.js 显示"行业数据暂不可用"
4. ✅ 支持按市值/品种数两种排序模式（手动验证）
5. ✅ 边缘场景（品种无行业归属 → 归入"其他"分类）→ 走 `test_chart_data_builder_edge.py`（C12 合规）

**测试范围边界**：
- ✅ 测：行业聚合逻辑（含部分品种无行业归属的处理）
- ❌ 不测：排序切换动画效果（手动验证）、其他 4 张图

### 迭代 5：穿透 TOP10 Bar（0.25d）

**目标**：纯表格 → 交互式柱状图

| 任务 | 测试范围 |
|:-----|:---------|
| `chart_data_builder.py` 新增穿透 TOP10 dataset | ✅ `penetration=None` → 占位 ✅ 排序与 Excel TOP10 一致 ✅ 穿透品种 < 3 时仍渲染（标注"仅 N 个品种"） |
| `chart-init.js` 新增 Bar 初始化 | ✅ 颜色区分 A 股/基金/其他（手动验证） ✅ 悬停显示穿透明细（手动验证） |

**验收标准**：
1. ✅ `test_chart_data_builder.py` 新增 ≥2 个用例（正常 TOP10、penetration=None）：全部通过
2. ✅ TOP10 品种排序与穿透页签一致
3. ✅ 穿透数据不可用时 Chart.js 显示"穿透分析数据不可用"
4. ✅ 穿透品种 < 3 时不报错，正常渲染剩余数据

**测试范围边界**：
- ✅ 测：penetration 数据切片逻辑、空值处理、品种数不足 3 的边界
- ❌ 不测：点击跳转细节（预留交互 → 不测）、其他 4 张图

### 迭代 6：量化指标 Radar（0.25d）

**目标**：纯表格 → 交互式雷达图

**前提**：Iter 1 已打通 metrics 数据流——orchestrator 将 `prep["risk_metrics"]`（5 基本字段）+ `_metrics`（14 项全量，`compute_all_metrics()` 返回值）合入 `build_chart_datasets()`，输出 `chart_datasets["radar"]` 经 template context 传递到 chart-init.js。

| 任务 | 数据源 | 测试范围 |
|:-----|:--------|:---------|
| `chart_data_builder.py` 新增雷达图 dataset | `all_metrics`（14 项全量，仅 full 路径） + `risk_metrics`（5 基本字段，双路径备用降级） + 7 个 `metrics_*` Flag | ✅ `all_metrics` 提供时：提取 sharpe/calmar/HHI/beta/volatility 等 7-10 个有效轴 ✅ 仅 `risk_metrics` 时：降级到 3 个基本轴（volatility/return/drawdown） ✅ Flag 关闭的指标显示 N/A 而非 0 ✅ 部分缺失 → 显示 N/A ✅ 全部 N/A → 占位 ✅ 两者均为 None → 空 dict |
| `chart-init.js` 新增 Radar 初始化 | | ✅ tooltip 显示指标说明（手动验证） |

**验收标准**：
1. ✅ `test_chart_data_builder.py` 新增 ≥6 个用例（正常全量指标、仅 risk_metrics 降级、metrics_sharpe=False、全 N/A、all_metrics=None、risk_metrics=None）：全部通过
2. ✅ full 路径：雷达图使用 `all_metrics` 的 7-10 个有效轴，数值与 `compute_all_metrics()` 输出一致
3. ✅ both 路径：仅 `risk_metrics` 可用时雷达图显示降级版本（3 个基本轴 + 标注"仅限基础指标"）
4. ✅ `metrics_sharpe = False` 时预处理器输出中该指标为 `{"label":"夏普比率", "value":"N/A"}`
5. ✅ 全部 7 项均为 N/A 时整个雷达图区域显示"量化指标数据不足"
6. ✅ 两者均为 None 时 chart_datasets["radar"] 为空 dict
7. ✅ `data_unavailable=True` 时（持仓有成本但市值全 0），即使 metrics 计算返回了具体数值也不渲染雷达图——改用占位文本"持仓市值数据不可用，量化指标暂停计算"（交叉验证 Iter 1 模板测试）

**测试范围边界**：
- ✅ 测：risk_metrics 提取 + metrics_* Flag 过滤逻辑、全 N/A 边界、None 输入
- ⚠️ `@pytest.mark.edge` 场景（全 N/A、None 输入）→ 放 `test_chart_data_builder_edge.py`（C12 合规）
- ❌ 不测：JS 雷达图几何渲染精度（Chart.js 内部逻辑）

> ⚠ **Both 路径用户可见差异**：both 路径（菜单 B）无 `_metrics`（`compute_all_metrics()` 未执行），也无 `risk_metrics`。雷达图 3 个基本轴（年化波动率/累计收益率/最大回撤）来自 `_build_radar_dataset()` 的 `history_data` 降级兜底（`history_data` 始终含有这些字段）。full 路径（菜单 L）显示 7-10 个完整轴。这是 both 路径的设计预期——轻量快速，不以全量指标计算为代价。报告底部页脚已标注报告模式

### 迭代 7：热力图框架预留 + 全链路集成验证（0.5d）

**目标**：Chart.js Matrix 插件 POC + 6 张图全链路手动验证 + 双路径回归

| 任务 | 测试范围 |
|:-----|:---------|
| `chartjs-chart-matrix` POC 验证与 Chart.js v4 兼容性 | ✅ 兼容：Matrix 插件正确渲染含悬停数值的热力图 ✅ 不兼容：有 Canvas 2D 回退方案（0.5d 缓冲覆盖） |
| 热力图框架（接收 `correlation_data` 占位数据） | ✅ 无 `correlation_data` → 占位文本 ✅ 有空数据 → 显示"等待 plan-2 数据" |
| 全链路手动验证（Chrome 120+ / Edge 120+） | ✅ 6 张图均渲染 ✅ 缩放/悬停/图例交互正常 ✅ 打印 preview 正常 ✅ CDN onerror 降级路径 |
| Canvas 回归验证 | ✅ Flag OFF 时 2 张 Canvas 图与改造前渲染一致 ✅ 模板结构测试全部通过 |

**验收标准**：
1. ✅ POC 通过 → Matrix 插件与 Chart.js v4 兼容；不通过 → 有 Canvas 2D 回退方案
2. ✅ 6 张图在 Chrome 120+ / Edge 120+ 中均可渲染和基本交互
3. ✅ 打印预览：所有 chart 以高分辨率静态图显示（2x DPI）
4. ✅ CDN 阻断测试（DevTools 阻断 cdn.jsdelivr.net）→ 所有 chart 回退到 Canvas / 表格
5. ✅ Feature Flag OFF → 报告与未升级版渲染一致（Canvas + 表格）

**测试范围边界**：
- ✅ 测：全链路集成、跨浏览器渲染、CDN 降级、打印降级
- ❌ 不测：Excel 管线（不变）、性能基准（已在 rf-4 覆盖）

### 迭代 8：代码审查 + C14 自检 + 文档 + 缓冲（0.5d）

**目标**：架构合规性终审 + 文档同步 + 门禁验证 + 未知风险缓冲

| 任务 | 产出 | 检查清单 |
|:-----|:------|:---------|
| C14 自动化自检 | grep 结果 0 违规 | `grep -rn '_ENV\.globals\[' src/python/ | grep -v html_jinja_env.py` → 0 matches |
| 文件清单审计 | folders.md 同步 | 新增 5 文件全部录入（tool_call 模式） |
| review-findings.md 记录 | 实施问题归档 | 发现的问题先记录后修复 |
| plan.md 交叉引用 | 计划状态同步 | plan-1 标记实施中/完成 |
| 边缘文件合规检查 | edge 校验 | `test_chart_data_builder_edge.py` 中所有测试带 `@pytest.mark.edge`（C12） |
| **`python scripts/test_runner.py --mode dev-verify`** | **P0 门禁** | 核心单元+基础场景全部通过 |
| 缓冲时间 | 打印时序调试、国产浏览器兼容修复 | 0.5d 预留 |

**验收标准**：
1. ✅ C14 违规数为 0（grep 规则通过）
2. ✅ `python scripts/test_runner.py --mode dev-verify` 全部通过（P0 提交门禁）
3. ✅ `test_chart_data_builder_edge.py` 中 edge 标记与文件命名一致（C12）
4. ✅ `folders.md` 目录树同步完成（新增文件全部列出）
5. ✅ 本文档 + `plan-chartjs-risk-analysis.md` 版本号一致

### 迭代总览

| 迭代 | 内容 | 工时 | 测试用例数 | 边缘隔离 | 关键依赖 |
|:----:|:-----|:----:|:----------:|:--------:|:---------|
| 1 | 基础设施（预处理器 + Feature Flag + CDN + context + risk_metrics 流） | 1.0d | ~9（6 + 3） | 不涉及 | 无 |
| 2 | 净值曲线 + 回撤图迁移 | 0.75d | ~4 | 不涉及 | Iter 1 |
| 3 | 资产构成 Doughnut | 0.25d | ~3（含 H2 data_unavailable） | 不涉及 | Iter 1 |
| 4 | 行业分布 Horizontal Bar | 0.25d | ~3（+2 edge） | ✅ `*_edge.py` | Iter 1 |
| 5 | 穿透 TOP10 Bar | 0.25d | ~2 | 不涉及 | Iter 1 |
| 6 | 量化指标 Radar（双数据源：all_metrics + risk_metrics） | 0.25d | ~8（含 H2 + 双降级路径）+1 edge | ✅ `*_edge.py` | Iter 1（risk_metrics + all_metrics） |
| 7 | 热力图框架 + 集成验证 | 0.5d | ~6（手动） | 不涉及 | Iter 1-6 |
| 8 | 代码审查 + 文档 + 门禁 | 0.5d | 1（C14 grep）+ dev-verify | C12 合规检查 | Iter 7 |
| **合计** | | **3.75d + 1.5d** = **5.25d** | **~39** | | |

---

## 6. 涉及文件清单

| 文件 | 改动类型 | 改动内容 |
|:-----|:---------|:---------|
| `src/python/features.py` | 修改 | `_FEATURE_FLAGS_DEFAULT` 新增 `enable_interactive_charts: True` |
| `src/python/report/orchestrator.py` | 修改 | 新增 `is_feature_enabled("enable_interactive_charts")` 读取 + `build_chart_datasets()` 调用 + `chart_datasets`/`enable_interactive_charts` 参数传入 `write_html_report()` |
| `src/python/report/html_writer.py` | 修改 | 新增 `chart_datasets` + `enable_interactive_charts` 参数 → context 注入 |
| `src/python/report/chart_data_builder.py` | **新建** | Python 端预处理器，6 张图数据格式转换 |
| `src/python/report/html_jinja_env.py` | **不改** | C14 约束：不新增 globals |
| `src/python/report/html_renderers.py` | **不改** | 保持现有 14 个渲染函数 | |
| `src/python/tmpl/report_template.html` | 修改 | CDN SRI script + canvas 容器 + 打印降级 + Feature Flag 分支 |
| `src/python/tmpl/chart-init.js` | **新建** | 6 个 Chart.js 图表初始化函数 |
| `src/python/tmpl/chart-config.js` | **新建** | 颜色/字体/主题常量（CSS 变量驱动） |
| `data/config/features.json` | 修改（可选） | 用户覆盖 `enable_interactive_charts` |
| `src/test/test_chart_data_builder.py` | **新建** | 预处理器单元测试 |
| `src/test/test_chart_data_builder_edge.py` | **新建** | 预处理器边缘场景测试（C12 合规） |
| `src/test/test_report_interactive.py` | **新建** | Feature Flag + 双路径 + 降级集成测试 |

---

## 7. 技术方案对比

| 方案 | 体积 | 热力图 | 缩放 | 打印兼容 | 推荐理由 |
|:-----|:----:|:-------|:----|:---------|:---------|
| **Chart.js** | ~80KB | 需插件 | 内置 | medium | ✅ **最轻量，够用** |
| ECharts | ~300KB | 内置 | 内置 | hard | ❌ 太重 |
| ApexCharts | ~130KB | 无原生 | 内置 | medium | ❌ 缺热力图 |

CDN 策略：**CDN + SRI + onerror 回退**（见 §4.3）

---

> **版本记录**
> - v1（原）：初始 4d 估算，不含 Python 预处理器 / JS 外部化 / CDN SRI
> - v2：与 `plan-chartjs-risk-analysis.md` v2 对齐
>   - 工作量 4d → 5.25d，8 迭代拆解 × 验收标准
>   - 新增 §2 数据就绪度矩阵、§4 完整策略（预处理器/JS 外部化/三级降级/CSS 变量/打印降级）
>   - 新增 §5 迭代计划（每轮验收标准 + 测试范围）
>   - 修正 `html_renderers.py` → 保持不改
>   - 修正 `html_jinja_env.py` → 不新增 globals
> - **v3（R4+R5+R6）**：CDN 策略简化 — SRI hash 硬编码（非构建步骤）、本地 bundle 降级为 P2、H2 `data_unavailable` 覆盖 Iter 3/6、命名一致性修复、迭代总览测试计数同步
>   - §1.3 新增图表到模板章节映射表
>   - §4.1 预处理器签名修正：新增 `all_metrics` 参数，明确 `_metrics`（14 项全量）+ `risk_metrics`（5 基本字段）双数据源
>   - Iter 1/6 编排任务细化：`_metrics` 合并 + `build_chart_datasets()` 调用
>   - Iter 6 验收标准扩展为 7 项（含双降级路径）
>   - 测试基础设施前置准备：`_build_minimal_render_data()` 新增 chart_datasets/enable_interactive_charts
>   - **R6 新增**：§4.2 JS 文件交付机制（`shutil.copy2` 到 reports/）+ chart-init.js CDN 失败守卫 + canvas 存在检测
>   - **R6 修复**：§4.5 `Chart.instances.forEach` → `Object.values(Chart.instances).forEach`
>   - **R6 新增**：Iter 6 Both 路径雷达图差异文档化（用户可见行为差异）
> - **v4（R7）**：Feature Flag 读取位置确认（orchestrator 读取 + 参数传递，与 enable_* 一致）；条件预计算（不跳过 build_chart_datasets，纯计算 ~5ms 全量执行）；DegradationTracker 兼容性确认（正交系统无冲突）；`_build_radar_dataset` 新增 `history_data` 三级降级兜底（both 路径 3 个基本轴）；`orchestrator.py` 加入文件清单
