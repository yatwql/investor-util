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
5. [迭代计划（8 轮 × 验收标准 × 测试范围）](#5-迭代计划8-轮-验收标准-测试范围)
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
- **为 plan-7 预留** — 穿透 TOP10 Bar / 行业分布 Horizontal Bar 的 Chart.js 能力可被 plan-7 复用（方案 B）；plan-7 MVP 用方案 A（自建轻量柱状渲染）不阻塞在 plan-1，见 `plan-advanced-analysis.md §4`

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

### 1.4 总工作量

| 阶段 | 工时 | 说明 |
|:-----|:----:|:------|
| 基础设施搭建 | 1.0d | Python 预处理器 + JS 外部化 + chart.min.js 本地 bundle + Feature Flag |
| 净值曲线迁移 | 0.75d | 2 张 Canvas→Chart.js + 三级降级 + `beforeprint` |
| 4 张新图构建 | 1.0d | 资产构成/行业分布/穿透 TOP10/量化指标 |
| 热力图框架（预留） | 0.5d | 矩阵插件集成 + 空状态渲染 |
| Python 端测试 | 0.5d | 预处理器单元测试 + Feature Flag 测试 + 降级测试 |
| 集成验证 | 0.5d | 双路径回退验证 + 打印降级验证 + 浏览器兼容性 |
| 代码审查 + 文档 | 0.5d | C14 自检 + 交叉引用更新 + review-findings 记录 |
| 缓冲 | 0.5d | POC 验证、打印时序调试、本地 bundle 加载问题排查 |
| **合计** | **5.25d** | 原估 4d，上调 +1.25d（新增预处理器 + 测试 + JS 外部化） |

---

## 2. 当前状态与数据就绪度

### 2.1 数据依赖矩阵

| 图表 | 数据源 | 就绪状态 | 预处理需求 |
|:-----|:------|:--------:|:-----------|
| **净值趋势** | `history_data.bars` + `history_data.benchmarks` | ✅ 直接 `tojson` | 下采样（可选） |
| **最大回撤** | `history_data.bars[drawdown_pct]` | ✅ 同数据源 | 复用净值数据 |
| **穿透 TOP10** | `penetration["top10"]` | ✅ 就绪 | 排序 + 格式化 |
| **资产构成** | `details` 列表 | ⚠ 缺市值聚合 | 按 `property`（资产属性，来自 `_categorize_holding()`，键：股票/基金/债券/现金/其他）聚合市值，与 Excel 分类汇总（`_build_category_data` 按 `(property, sub_category)` 分组）口径一致 |
| **行业分布** | `details` + `penetration` 的 `sector` 字段 | ⚠ 缺行业聚合 | 按 `penetration` 中 per-asset `sector`（关键词映射 `classify_sector` 或行业 API `sector_api`）聚合市值，无现成函数需交叉计算 |
| **量化指标** | `info["risk_metrics"]` + 7 项 `metrics_*` Flag | ⚠ 分散 | 统一收集 + Flag 检查 |
| **相关性矩阵** | 依赖 plan-2 的 `correlation_data` | ⏳ 不可做 | 留待 plan-2 |

### 2.2 渲染管线现状

```
_report_generation.py → _generate_report_both / _generate_report_full
   │   （write_html_report() 实际调用方，orchestrator 仅为分发入口）
   ↓  history_data (dict) + 各渲染参数
html_writer.py → write_html_report(info, history_data, ...)
   ↓  render(context={history_data, section_visible, ...})
report_template.html (1862 行 Jinja2 模板)
   ├── drawSimpleChart()     ← 内联 Canvas 2D，第 265-513 行
   ├── <canvas id="portfolioChart">   ← 净值曲线，第 1448 行
   ├── <canvas id="drawdownChart">    ← 回撤图，第 1560 行
   ├── tojson 序列化数据到内联 <script> 块（4 处）
   └── 其余模块均为表格/文本渲染
```

> **R1 基线修正**：模板当前实际为 **1862 行**（非 1845 行）。`write_html_report()` 的调用方是 `_report_generation.py`（`_generate_report_both`/`_generate_full_html_report`），orchestrator.py 仅按 `report_type` 分发到这两个函数。因此 metrics 整合与 Feature Flag 读取的实际修改点是 `_report_generation.py`（详见 §6 文件清单与 Iter 1 任务表）。

**关键**：`history_data` schema 在 `portfolio_history.py` 定义，通过 `tojson` 直接序列化到浏览器。Chart.js 可直接消费 `history_data.bars` + `history_data.benchmarks`。

**R2 数据契约明细（基于 v0.8.7-dev 源码核实）**：

| 数据 | 来源 | 关键字段 |
|:-----|:-----|:---------|
| `history_data.bars` | `PortfolioHistoryCalculator.get_combined_timeseries()` | `[{date, total_value, daily_return, drawdown_pct}]`（`total_value`=组合净值、`drawdown_pct`=回撤百分比、`daily_return`=日收益） |
| `history_data.benchmarks` | 同上 | `[{name, code, bars: [{date, value}]}]` |
| `history_data.daily_returns_portfolio` | 同上 | 组合日收益率序列（可直接喂 `compute_all_metrics`，**可选**作雷达图备用轴） |
| `history_data.status` | 同上 | `"ok"`/`"degraded"`/`"unavailable"`（三级降级判定源） |
| `details[].market_value` | `DetailRow` | 单品种市值（资产构成/行业聚合的市值来源） |
| `details[].name/code` | `DetailRow` | 品种标识（`_categorize_holding` 依赖 name 判资产属性） |
| `penetration["top10"]` | `compute_penetration_top10()` | `[{name, code, mv, sector, ...}]`（按市值降序，含 `top10_coverage_pct`） |
| `compute_all_metrics()` 返回值 | `analysis/metrics.py` | `sharpe_ratio`/`calmar_ratio`/`hhi`(+`hhi_equivalent`)/`win_rate`(**嵌套 dict**)/`turnover_rate`/`individual_volatility`/`portfolio_beta`(+`beta_confidence`)/`risk_contributions` |

> ⚠ **R2 发现**：资产构成聚合键为 `property`（资产属性），非 `code_type`（该字段不存在）。行业聚合需以 `penetration` 的 per-asset `sector` 为键（`classify_sector` 关键词映射或行业 API `sector_api`）。雷达图取值须用 `x is not None` 判断空值（`0.0` 是合法值，`x or "N/A"` 会误判）。

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
| **C16** 路径绝对化 | chart.min.js 本地 bundle（默认方案）与 chart-init.js / chart-config.js 一并经 `shutil.copy2(src, os.path.join(output_dir, fname))` 复制到报告输出目录，`output_dir` 已由 `get_config()` 经 `_absolutize_paths()` 绝对化；模板用相对路径 `src="chart.min.js"`（R21 更新） | |

### 3.2 不变约束

| 约束 | 说明 |
|:-----|:------|
| C1/C2/C3/C4/C5/C6 | ✅ 无关 — 不新增数据获取，不新增缓存 |
| C8/C15 | ✅ 无关 — 客户端 JS 不经 Python 日志 |
| C9/C17/C18 | ✅ 无关 — 不新增 LLM 模块、不新增 LLM API 调用、不新增凭据配置（R3 补齐，实现 19 条全覆盖） |
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
    - all_metrics:  源自 _report_generation.py 中 compute_all_metrics() 返回值（14 项全量指标）
      仅 full 路径有此数据；both 路径均为 None。
    - 降级兜底：当 both 路径传入 None 时，_build_radar_dataset 从 history_data
      提取 annualized_volatility / max_drawdown_pct / total_return_pct 3 个基本轴。
    """
    from src.python.features import is_feature_enabled

    datasets = {}
    # ⚠ R11：每个 dataset 独立 try/except——单图脏数据失败仅跳过该图，
    #    不得因一个图抛异常导致整份报告生成失败。
    if history_data and history_data.get("status") != "unavailable":
        try:
            datasets["portfolio_line"] = {
                "labels": [b["date"] for b in history_data["bars"]],
                "datasets": [{
                    "label": "组合净值",
                    "data": [b["total_value"] for b in history_data["bars"]],
                    "borderColor": "var(--chart-primary)",
                }],
                "benchmarks": _build_benchmark_datasets(history_data.get("benchmarks", [])),
            }
        except (KeyError, TypeError, ValueError):
            logger.warning("[chart] portfolio_line 构建失败，跳过该图", exc_info=True)
        try:
            datasets["drawdown"] = {
                "labels": [b["date"] for b in history_data["bars"]],
                "datasets": [{
                    "label": "回撤",
                    "data": [b["drawdown_pct"] * 100 for b in history_data["bars"]],
                    "backgroundColor": "var(--chart-danger-transparent)",
                }],
            }
        except (KeyError, TypeError, ValueError):
            logger.warning("[chart] drawdown 构建失败，跳过该图", exc_info=True)
    # ⚠ R12：radar 构建放在外层 if 之外，仅依赖 all_metrics / risk_metrics / history_data
    #    三源独立判断——history_data 不可用但 all_metrics 有值时，radar 仍应渲染。
    datasets["radar"] = _build_radar_dataset(history_data, all_metrics, risk_metrics)
    # ... 其余 3 图（参见 chart_data_builder.py 完整实现，同样独立 try/except）
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

**⚠ JS 文件交付**：前端 JS 资产统一存放于 **`src/js/`**（R21 采纳新建目录建议：第三方引擎 chart.min.js + 自有 chart-init.js / chart-config.js，打包分发，升级时整体替换），但 HTML 报告生成在 `reports/`。`html_writer.py` 需在渲染后将三个 JS 文件 **拷贝**到输出目录（与 HTML 同目录）。已有的 `html_save.py` 扩展（或在 `write_html_report()` 尾部追加）：

```python
import shutil
from src.python.core.constants import PROJECT_ROOT
_JS_ASSETS = ["chart.min.js", "chart-config.js", "chart-init.js"]  # 位于 src/js/
for fname in _JS_ASSETS:
    src = os.path.join(PROJECT_ROOT, "src", "js", fname)
    dst = os.path.join(output_dir, fname)
    shutil.copy2(src, dst)
```

> **R21 决策**：chart.min.js 本地 bundle 为默认方案（详见 §4.3）。模板引用相对路径，报告完全离线自包含。`src/js/` 为前端 JS 资产唯一来源（template 仅引用相对路径），升级 Chart.js 时仅替换 `src/js/chart.min.js`。

模板中引用相对路径（与 HTML 同目录）：
```jinja2
{% if enable_interactive_charts %}
  <script src="chart.min.js"></script>
  <script src="chart-config.js"></script>
  <script src="chart-init.js"></script>
{% endif %}
<canvas id="chart_{{ key }}"></canvas>
```

**⚠ chart-init.js 安全守卫** — chart-init.js 内每个图表初始化必须包含引擎存在检测 + canvas 存在检测（防御 chart.min.js 加载失败/文件损坏 + section_visibility 隐藏模块）：

```javascript
(function(){
  if (typeof Chart === 'undefined') return;  // 引擎加载失败 → 静默跳过（R21 替代 CDN onerror 标记）
  var el = document.getElementById('chart_portfolio');
  if (!el) return;
  new Chart(el, { ... });
})();
```

> **收益**：本地 bundle 加载异常时跳过所有初始化（不会抛 `Chart is not defined`）；section_visibility 隐藏的模块因 canvas DOM 不存在而自动跳过。

### 4.3 Chart.js 引擎加载策略：纯本地 bundle（R21 决策）

**R21 决策**：Chart.js 引擎**本地化**——`chart.min.js`（Chart.js v4 UMD 版，~200KB）随报告复制到输出目录，模板以相对路径引用。**放弃 CDN**（jsdelivr 在国内访问不稳定，报告为本地静态制品，交互功能不应依赖网络）。

```
本地 bundle + 防御性守卫（相对路径 <script src="chart.min.js">）
  └→ chart.min.js 加载失败/文件损坏 → typeof Chart 检测 → 跳过初始化 → 回退 Canvas 2D / 表格
```

**理由**：
1. **报告是静态制品** — Chart.js 对报告就像报告里的图片，应内嵌而非外链；外链会失效，外链 JS 同理
2. **个人工具无分发成本** — 唯一使用者是自己，200KB 可忽略
3. **R3（CDN 可用性）直接闭环** — 交互图表与网络彻底解耦，离线打开照常交互
4. **实施更简单** — 无 SRI hash 计算、无 onerror 动态加载时序、无 CSP 域名

**chart.min.js 来源与维护**：
- 从 jsdelivr/npm 下载 `chart.umd.min.js` 一次，命名 `chart.min.js` 存入 `src/js/`（git 跟踪，随源码分发；用户可自建 src/js 目录，必要时手动替换升级）
- **无需 SRI** — 本地文件来自自身可信下载源，且 `file://` 下部分浏览器不校验 integrity
- 升级 Chart.js 版本时：替换 `src/js/chart.min.js` 并同步验证（对应 §4.10 S2）

**降级兜底**（防御性，概率极低）：
- `typeof Chart === 'undefined'`（§4.2 守卫）→ 跳过 Chart.js 初始化 → 模板仍显示 Canvas 2D / 表格（Flag OFF 或 Canvas 兜底路径）
- 与 §4.4 三级降级（数据层面 ok/degraded/unavailable）正交——引擎加载失败属基础设施层，数据降级属数据层

> **CDN 方案**降级为未来可选增强（如未来报告需分发到多用户且文件体积敏感时，可改回 CDN 优先 + 本地兜底）。Iter 1 不涉及，无需 Feature Flag `chart_js_source`。

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

**补充（R16）**：
- **打印强制浅色**：`@media print` 下用浅色 CSS 变量覆盖（`--chart-*` 全部换浅色主题）——打印不浪费墨水、保证对比度；为 plan-11 暗色模式预留（暗色模式下打印自动切浅色，无需用户干预）
- **防跨页断裂**：图表容器加 `break-inside: avoid`，避免 canvas 快照在分页处被切开
- **单图导出能力**：`chart.toBase64Image()` 已用于打印快照，未来可复用做「单图导出 PNG」按钮——**P2 可选增强，非 MVP**（用户分享整份 HTML 报告时各图仍完整）
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

### 4.8 可访问性与体验（R10 补充）

> **R10 审查发现**：原计划对可访问性零覆盖。Chart.js 渲染到 `<canvas>` 后，屏幕阅读器/不支持 Canvas 的环境读不到图表内容。单用户个人工具不要求完整 WCAG 合规，但低成本项应纳入。

| # | 要求 | 成本 | 实现方式 |
|:-:|:-----|:----:|:---------|
| A1 | **canvas fallback 文本** | 极低 | 每个 `<canvas>` 内嵌 fallback 内容：`<canvas aria-label="净值趋势图（悬停查看精确值）" role="img">图表无法显示时，数据见下方明细表格</canvas>`——屏幕阅读器读出标签，降级环境读出表格指引 |
| A2 | **对比度（WCAG AA）** | 低 | `chart-config.js` 文本/轴标签颜色 vs 背景 ≥ 4.5:1，图表数据点/扇区 vs 背景 ≥ 3:1；浅色模式下禁用浅灰文本 |
| A3 | **色盲安全 palette** | 低 | 资产构成 Doughnut（股票/基金/债券/现金/其他）与穿透 TOP10 分色使用色盲安全调色板（蓝/橙/绿/紫/灰，避开纯红绿对比），在 `chart-config.js` 统一定义 |
| A4 | **移动端响应式** | 低 | Chart.js `responsive: true` + `maintainAspectRatio: false` 默认开启，图表容器继承表格流式宽度；无需额外 CSS |
| A5 | **引擎加载失败表格兜底** | 已含 | Flag ON + chart.min.js 加载失败/文件损坏（`typeof Chart` 检测）→ 跳过 Chart.js 初始化；Canvas 也失败时 `<canvas>` fallback 文本引导用户看表格（A1 兜底）（R21 更新） |
| A6 | **键盘可达性（不强制）** | — | Chart.js tooltip 为鼠标悬停驱动，键盘聚焦不触发；单用户工具不强制改造（记入技术债，不做 MVP） |

**验收补充**（Iter 7 手动验证项追加）：
- ✅ 页面禁用 Canvas 后，6 张图区域显示 fallback 文本而非空白
- ✅ 浅色模式下图表文本可读（对比度 ≥ 4.5:1 目测）
- ✅ 手机宽度（375px）下图表自适应不溢出

### 4.9 性能优化决策（R11 补充）

> **R11 审查发现**：R1（文件体积膨胀 280KB→~1MB）/R8（数据粒度）/TD4 已识别性能风险，但「下采样（可选）」未落成具体决策——无触发阈值、无聚合粒度、无实现位置；动画与 CDN 阻塞未提及。本节固化决策。（R22 补充 P4：低配机 + 高分屏的 DPR 限制）

| # | 决策 | 内容 | 触发条件/阈值 | 实现位置 |
|:-:|:-----|:-----|:-------------|:---------|
| P1 | **服务端下采样（净值趋势）** | 净值曲线数据点超过阈值时按**周聚合**（取每周最后一个交易日的市值，保证曲线形态不畸变），否则保留日频 | `len(history_data.bars) > 500`（约 2 年日频）触发；聚合后的点 < 200 时改按**月聚合**兜底 | `chart_data_builder.py` `_build_portfolio_line_dataset()` 内，纯 Python 可单测 |
| P2 | **动画关闭** | 报告是静态分析工具，无需入场动画；`chart-config.js` 统一 `animation: false`（交互 hover tooltip 不受影响） | 始终关闭 | `chart-config.js` Chart.defaults |
| P3 | **本地 bundle 非阻塞加载** | chart.min.js `<script>` 加 `defer`（本地文件加载毫秒级，defer 保证不阻塞 HTML 解析；脚本顺序由 `defer` 保证 → chart.min.js → chart-config.js → chart-init.js 依次执行） | 始终 | `report_template.html` 引擎 `<script>` 标签（R21 更新） |
| P4 | **DPR 限制（低配机优化，R22）** | Chart.js 默认按设备 DPR 渲染（4K 屏 2x/3x → canvas 像素数翻 4~9 倍）。限制 `devicePixelRatio: 1.5`（`chart-config.js` Chart.defaults）——高分屏下渲染分辨率略降但对折线/柱状图视觉无感，低配机 + 高分屏显著省显存/绘制时间 | 始终（Chart.js v4 默认 DPR 上限即 1.0，显式设 1.5 在清晰度与性能间平衡） | `chart-config.js` Chart.defaults |

**下采样与打印/降级的交互**：
- 下采样**仅作用于 Chart.js 数据集**，不改变 `history_data.bars` 原始数据——Excel 管线、Canvas fallback（Flag OFF）仍用原始日频
- 下采样后 tooltip 显示的是聚合周期末值（周/月），与 Excel 明细存在粒度差异——Iter 2 验收需确认报告底部无「数据周期」误导性描述
- 下采样在预处理器内做，天然满足 C14（数据经 render() context 传递）

**验收补充**（Iter 2 新增用例）：
- ✅ `len(bars) > 500` → 输出周聚合数据集，点数 ≤ ceil(500/5)
- ✅ `len(bars) ≤ 500` → 保留日频原样
- ✅ 周聚合后点数仍 > 200 → 降级为月聚合
- ✅ 下采样仅改变 Chart.js 数据集，`history_data.bars` 原值不变

### 4.10 安全清单（R12 补充）

> **R12 审查发现**：tojson 转义（R6）、CDN SRI（§4.3）、数据隐私（R9）已覆盖，但 JS 端 **tooltip/label 渲染** 与 **引擎版本升级维护** 未约束。（R21 更新：SRI 已随 CDN 放弃，S2 改为本地 bundle 版本替换；S5 CSP 域名约束随之消除）

| # | 约束 | 说明 | 依据 |
|:-:|:-----|:-----|:-----|
| S1 | **禁止 innerHTML 渲染图表 label** | `chart-init.js` 一律使用 Chart.js 文本渲染（dataset label / tooltip callback 返回纯文本）；**不得**用 `innerHTML`/`insertAdjacentHTML` 拼接持仓名/行业名/穿透名（来源含 API，`classify_sector`/`sector_api` 可能被第三方注入）。Chart.js 默认 tooltip 是文本节点，安全；仅需约束自定义 tooltip | 防 XSS |
| S2 | **本地 bundle 版本替换维护** | Chart.js 版本升级（如 v4.4.7 → 更新版本）时**必须同步替换 `src/js/chart.min.js`** 并在独立 test HTML 页验证 6 图渲染 + 交互（无 SRI/无 CDN，替换即生效；漏替换则报告停留在旧引擎，无静默失败）。版本号记录在 `src/js/README.md` | 防引擎版本漂移 |
| S3 | **tojson 转义确认** | Jinja2 3.1.6 `tojson` 自动转义 `<`/`>`，`chart_datasets` 经 tojson 注入安全；不在模板中改用 `|safe` | 防 XSS（R6 已确认） |
| S4 | **数据最小化** | 预处理器只传递图表所需字段（日期+市值+聚合值），不含份额/成本等敏感字段进 chart 数据集 | 防隐私（R9，引用不重复） |
| S5 | **CSP 提示（可选）** | 报告为离线静态 HTML，无既有 CSP；本地 bundle 后无外部域名，若未来加 CSP 仅需 `script-src 'self'` | 可选项，不做 MVP（R21 更新） |

### 4.11 代码组织与模块契约（R13 补充）

> **R13 审查发现**：Python 端已有单图 try/except（R11）与 canvas 存在守卫（v5），但 JS 端**缺少初始化函数级异常隔离**（对称缺口）；dataset 键名与降级标记字段未固化为契约（Python↔JS 不同步风险）。

| # | 约束 | 内容 |
|:-:|:-----|:-----|
| O1 | **JS 端单图异常隔离** | `chart-init.js` 每个图表初始化函数（`initPortfolioChart`/`initDrawdownChart`/`initCategoryDoughnut`/`initIndustryBar`/`initPenetrationBar`/`initRadar`）**独立 `try/catch`**——一张图初始化抛错仅 console.warn 该图，不阻断其余 5 张（对称 Python 端 R11） |
| O2 | **dataset 键名契约** | 6 个固定键：`portfolio_line` / `drawdown` / `category_doughnut` / `industry_bar` / `penetration_bar` / `radar`。Python 输出键 ↔ JS 消费键一一对应，**不得**在 JS 侧自行改名（键名变更需同步两文件 + 测试） |
| O3 | **降级标记契约** | Python 输出的 dataset 携带 `degraded: true/false` 字段；JS 端读 `degraded` 决定 `borderDash: [5,5]`。字段名固定，两级渲染共享同一契约 |
| O4 | **文件行数预算** | `chart_data_builder.py` ≤ 400 行、`chart-init.js` ≤ 300 行、`chart-config.js` ≤ 150 行（项目惯例 <800 行）。超出 → 拆分辅助模块 |
| O5 | **命名规范** | Python：`_build_<dataset>_dataset()` 前缀（如 `_build_benchmark_datasets`）；JS：`init<Chart>Chart` 前缀 + `_config` 读取配色（`var(--chart-*)`） |

**契约测试**（Iter 1 验收补充）：
- ✅ `build_chart_datasets()` 返回 dict 的键集合 == 6 个固定键（空数据时为占位空 dict 或缺失键，JS 端按 O1 隔离处理）
- ✅ 键名与 §4.11 O2 清单一致（防 Python/JS 不同步）

### 4.12 输出 schema 契约：`chart_datasets` 结构（R14 补充）

> **R14 审查发现**：R2 数据契约表覆盖**输入**（`history_data.bars`/`benchmarks`/`metrics` 精确字段名，见 §2.1），但 `chart_datasets` 的**输出结构**仅散见于示例代码，未固化为契约——空值语义、日期格式、数值类型边界不清。

**通用结构**（折线/柱/环形/热力共用）：

```json
{
  "<dataset_key>": {
    "labels": ["YYYY-MM-DD" | "行业名" | "品种名" | "指标名"],
    "datasets": [{
      "label": "组合净值" | ...,
      "data": [<float> | "N/A"],
      "borderColor": "var(--chart-primary)",   // 折线/柱
      "backgroundColor": "var(--chart-*)",      // 柱/环形/回撤
      "degraded": true | false                   // §4.11 O3
    }]
  }
}
```

**各图差异**：
| 图 | 结构要点 |
|:---|:---------|
| `portfolio_line` | `datasets[0].data` = 日/周净值 float；`benchmarks` 键（数组，每基准一个 dataset）；下采样后点数为聚合周期末值（§4.9 P1） |
| `drawdown` | `data` = 回撤百分比 float（已 ×100），`backgroundColor` 透明红 |
| `category_doughnut` | `labels` = 资产属性（股票/基金/债券/现金/其他），`data` = 市值 float |
| `industry_bar` | `labels` = 行业名，`data` = 市值 float（无归属 → "其他"） |
| `penetration_bar` | `labels` = 品种名，`data` = 市值 float |
| `radar` | `labels` = 指标名，`data` = `[float \| "N/A"]`（Flag 关闭或缺失 → "N/A" 而非 0，§6.6） |

**空值语义契约**（JS 端行为）：
- **键缺失** → 该图数据不可用 → 显示占位文本（"xx 数据不可用"）
- **`{"labels": [], "datasets": []}`** → 空数据 → 显示"无数据"
- **`degraded: true`** → `borderDash: [5,5]` + 降级消息

**其他契约**：
- **日期格式**：`YYYY-MM-DD` 字符串，净值/回撤用 **category 轴**（不引入 time 轴 → 避免 `chartjs-adapter-date-fns` 额外依赖，本地 bundle 亦无需多带一个适配器文件）
- **数值类型**：`data` 元素为 float/int；`None` 已由预处理器转为 `"N/A"`（radar）或跳过该点（折线脏数据 → R11 隔离）
- **C19 豁免确认**：`chart_datasets` 仅经 template context 传递，**不写 pipeline_data**，无需新增 Schema（risk-analysis.md §7 第 417 行）

**验收补充**（Iter 1）：
- ✅ `build_chart_datasets()` 各图输出结构符合 §4.12 通用结构（labels/datasets/degraded 字段存在）
- ✅ radar 输出中 Flag 关闭指标为 `"N/A"` 字符串而非 `null`/`0`

### 4.13 Feature Flag 治理（R15 补充）

> **R15 审查发现**：`enable_interactive_charts` 的注册位置、命名、默认值策略已明确（H1 注释计数），但 **flag 层级**、**默认 True 的兜底语义**、**flag 本身的生命周期废弃** 未系统化。

| # | 约束 | 内容 |
|:-:|:-----|:-----|
| F1 | **Flag 层级** | `enable_interactive_charts` 是**总开关**，`metrics_*`（7 项）是**雷达子开关**。总开关关闭 → 整个 Chart.js 不加载、`metrics_*` 无意义（子开关仅在全量指标构建 radar 轴时过滤）；总开关开启 → 子开关逐个过滤雷达轴（§6.6）。两者正交，无冲突 |
| F2 | **默认 True 的兜底** | 默认开启渐进增强；用户可在 `data/config/features.json` 设 `"enable_interactive_charts": false` 一键回退旧 Canvas + 表格渲染（双路径保证，与 §4.7 呼应）。`features.json` 缺失该键 → 用默认 True，不强制新增键 |
| F3 | **生命周期废弃** | §4.7 定义「稳定 2 版本后删 Canvas」；**补充**：Chart.js 成为唯一渲染器后，同步删除 ① `_FEATURE_FLAGS_DEFAULT` 中 `enable_interactive_charts` 键 ② 分类注释 `3→2 项` ③ `test_feature_interactive.py` 相关用例 ④ 模板 Flag 分支 ⑤ `features.json` 示例键——避免死 flag 残留 |
| F4 | **注册位置** | `_FEATURE_FLAGS_DEFAULT`「功能特性」分类（现 2 项）→ 新增后 **3 项**（注释计数同步，H1）；非实验功能，不列入 `EXPERIMENTAL_FEATURES` |
| F5 | **命名规范** | `enable_*` 前缀与 `enable_b_series`/`enable_news`/`enable_history`/`enable_llm` 一致；读取位置统一在 `_report_generation.py` 参数传递（R7 确认） |

**测试**（`test_feature_interactive.py`，`unit_config` marker）：
- ✅ 默认值为 `True`（`_FEATURE_FLAGS_DEFAULT`）
- ✅ `features.json` 覆盖 `False` → `is_feature_enabled()` 返回 `False`
- ✅ 未知 flag → `False`（已有 `_auto_reset_feature_flags` fixture 自动清理，无状态泄漏）

### 4.14 浏览器兼容矩阵（R17 补充）

> **R17 审查发现**：R2 风险已识别国产浏览器问题，但无明确支持矩阵；Iter 7 验证范围「Chrome 120+ / Edge 120+」过窄（遗漏 Firefox/Safari/旧版 Chromium）；「@babel/standalone 转译」对个人工具过重。

**支持矩阵**（最低版本，Chart.js v4 的 ES5 UMD 构建支持）：

| 浏览器 | 最低版本 | 说明 |
|:-------|:--------|:-----|
| Chrome / Edge（Chromium） | 90+ | 主验证目标 |
| Firefox | 90+ | 补充验证 |
| Safari | 14+ | Mac 用户；`<` 转义解析无问题 |
| 国产浏览器（360/QQ/搜狗等） | Chromium 内核 90+ | 内核兼容 Chart.js，仅个别样式差异 |

**JS 语法约束（避免 babel 转译链路）**：
- `chart-init.js` / `chart-config.js` 使用 **ES5 保守语法**（`var`/`function`，不用箭头函数/`const`/`let` 顶层解构/模板字符串）——Chart.js v4 本身是 UMD ES5 构建，`chart.umd.min.js` 无需转译
- **不采用** `@babel/standalone`（R2 缓解②降级为不采用）——个人工具不引入运行时转译，锁定 Chart.js 版本（R2 缓解①）已足够
- `report_template.html` 内联 `<script>` 同理用 ES5

**降级策略**（不支持的浏览器）：
- 不主动检测浏览器；老浏览器若 Chart.js 加载失败/不兼容（`typeof Chart` 检测）→ 跳过初始化 → Canvas 回退；Canvas 也失败 → `<canvas>` fallback 文本（A1）（R21 更新）
- 图表仍是渐进增强：表格明细永远存在，浏览器能力不足时用户仍可读数据

**Iter 7 验证范围更新**：`Chrome 120+ / Edge 120+` → **Chrome 90+ / Edge 90+ / Firefox 90+ / Safari 14+**（主验证 Chrome/Edge；Firefox/Safari 抽验）；国产 Chromium 内核浏览器留待迭代 8 缓冲处理

**微信打开场景（R22 补充）**：

| 打开方式 | 内核 | 本地 bundle 加载 | 图表渲染 | 结论 |
|:--------|:-----|:----------------|:---------|:-----|
| **链接访问**（报告部署到 http/https） | 安卓 8.0+ 内置 X5 内核（Chromium 107+）/ iOS WKWebView（Safari 14+），远超 Chart.js v4 需求 | 相对路径 `chart.min.js` 正常 | ✅ 完全正常 | **无困难**；本地 bundle 反优（微信里加载 jsdelivr CDN 慢/被墙，本地无此问题） |
| **本地 file://**（从文件传输助手/收藏点开 .html 附件） | 同上 | ⚠ **需实测**——微信沙箱对 file:// + 同目录相对 JS 加载可能有限制（X5 内核疑似拦截） | ⚠ 未知 | **边界场景**，Iter 7 需实测 |

**结论**：主要使用路径（链接访问）无困难；`file://` 在微信内是唯一不确定点。即使图表不渲染（`typeof Chart` 守卫跳过初始化），Canvas/表格明细永远存在，用户仍可读全部数据——图表本就是渐进增强，不阻塞数据获取。

> 注：微信内展示报告本质上是"看一张静态报告"，交互图表的悬停/缩放价值在移动端有限（触屏 hover 不友好），**移动端图表退化为可读的静态呈现是合理预期**，不构成功能缺失。

### 4.15 演进路径与回退（R18 补充）

> **R18 审查发现**：§4.7 有双路径清理计划（v0.10.0 删 Canvas），但缺三阶段演进总览、阶段切换判定标准、Flag OFF 时 canvas 容器残留细节。

**三阶段演进**：

```
阶段 1（现状 v0.9.x-dev）  阶段 2（plan-1 落地）        阶段 3（稳定 2 版本后 v0.10.0+）
Canvas + 表格            Flag ON: Chart.js 交互图        Chart.js 唯一渲染器
                          Flag OFF: Canvas + 表格（回退）   （删除 Canvas 分支 + Feature Flag）
```

**阶段切换判定**（阶段 2 → 阶段 3）：
1. 双路径共存 ≥ 2 个发布版本（§4.7）
2. 期间无 P0/P1 级图表缺陷
3. 用户无回退诉求（features.json 无人设 `enable_interactive_charts: false`）
4. 全部 P0 门禁（dev-verify,report）+ P1/P2 门禁通过

**Flag OFF 时的渲染细节**：
- `enable_interactive_charts=False` → 模板**不渲染** Chart.js canvas 容器（chart.min.js `<script>` 不加载、`<canvas>` 容器不输出）——避免 Flag OFF 时残留空 div / 空 canvas（Iter 1 验收标准 4 已覆盖）
- 预处理器 `build_chart_datasets()` **仍全量执行**（~5ms，R7 确认），仅 context 不注入 `chart_datasets`——保证 Flag 切换零延迟、无状态残留

**回退验证清单**（汇总 Iter 1/7，作为发布前门禁项）：
- ✅ Flag OFF 渲染 HTML 与改造前结构一致（无 chart.min.js script、无 canvas 容器）
- ✅ 三级降级：`ok` 实线 / `degraded` 虚线 / `unavailable` 占位
- ✅ 本地 bundle 加载失败（防御）→ Canvas 回退 → fallback 文本（A1）
- ✅ 打印（2x DPI 快照 + 浅色 + 防跨页）、移动端（375px）不退化

### 4.16 与数据降级体系融合（R19 补充）

> **R19 审查发现**：§6.5（risk-analysis.md）已确认 Chart.js 三级降级与 DegradationTracker **正交**（图表读 `history_data.status` 聚合结果，tracker 追踪 T1~T4 数据源级）。但**降级传播链**未可视化、**图表占位消息与数据状态表消息的口径**未约束。

**降级传播链**：

```
数据源降级（DegradationTracker，T1~T4）     聚合层                            图表层
  └→ 各数据源可用性 → 影响数据获取 → 产出 history_data.status ──→  Chart.js 三级降级
         （报告尾部 data_status_history 表格）    （ok/degraded/unavailable）
```

- 图表**不直接读** DegradationTracker——它是「聚合结果的降级」消费方；DegradationTracker 是「数据源级」追踪。两者在 `history_data.status` 汇合，正交无重复
- `degraded` 状态：数据不变，仅 `borderDash: [5,5]`（§6.5）；`unavailable`：占位文本 + 底部 `data_status_history` 明细双通道展示

**消息口径一致性约束**：
- 图表占位消息（"历史走势数据暂不可用"等）**复用** `report/data_status.py` 的 `STATUS_MESSAGES` 常量，**不得**在模板/JS 中另写文案——同一数据源降级，图表区与数据状态表用词一致
- 每图专属占位（行业/穿透/量化等）作为**新消息**加入 `STATUS_MESSAGES`（或独立常量表），保持集中管理

**radar 降级类型区分**：
- radar 不读 `history_data.status`，而是**数据源缺失链**（`all_metrics` → `risk_metrics` → `history_data` 3 轴，H6）——属「数据缺失」而非「数据降级」，与其余 5 图的三级降级机制不同，文档与实现需区分

**验收补充**（Iter 1）：
- ✅ 图表占位消息来自 `STATUS_MESSAGES`（或新常量表），与数据状态表用词一致
- ✅ radar 降级走三源缺失链，不读 `history_data.status`

---

## 5. 迭代计划（8 轮 × 验收标准 × 测试范围）

### 5.0 MVP 范围收敛（R8 补充）

**目标**：明确每张图的业务优先级与最小可交付子集，超支时有据可依地裁剪，避免「凭感觉砍功能」。

#### 5.0.1 图表优先级矩阵

| 优先级 | 图表 | 迭代 | 最小可交付子集（MVP 减配） | 完整版（加分项） | 依据 |
|:------:|:-----|:----:|:--------------------------|:----------------|:-----|
| **P0** | 净值趋势 Line | Iter 2 | 主曲线 + 悬停 tooltip | 基准线 + 图例切换 + 框选缩放 | 替换现有 Canvas，悬停精确值收益最大 |
| **P0** | 最大回撤 Line | Iter 2 | 净值线 + 回撤填充 | 双轴 + 回撤区间标注 | 回撤分析为核心章节（MODULE 18） |
| **P0** | 资产构成 Doughnut | Iter 3 | 占比 + 金额 tooltip | 图例点击展开 | 高频查看持仓结构，纯表格→交互 |
| **P0** | 穿透 TOP10 Bar | Iter 5 | 单色柱 + tooltip | A股/基金/其他分色 | 高频查看，纯表格→交互 |
| **P1** | 行业分布 Horizontal Bar | Iter 4 | 单排序模式 | 市值/品种数切换 | 与穿透 TOP10 同章节、同数据源，功能重叠度高 |
| **P1** | 量化指标 Radar | Iter 6 | 3 轴降级版 | 7-10 轴 + metrics_* Flag 过滤 | 已有 3 轴降级兜底（§Iter 6） |
| **P2** | 热力图框架 | Iter 7 | **可整体跳过**（占位文本已具备） | Matrix 插件 + 真实 correlation_data | 预留性质，plan-2 数据未到 |

#### 5.0.2 超支裁剪顺序（按优先级从低到高）

1. **Iter 7 热力图框架**：跳过（0.5d → 0d，测试 ~6 手动 → 0），仅保留占位文本
2. **Iter 6 量化雷达**：降级为仅 3 基本轴（裁剪 metrics_* Flag 全量轴逻辑）
3. **Iter 4 行业分布**：减配为单排序模式（不实现排序切换交互）
4. **Iter 5 穿透 TOP10**：减配为单色柱（不做分色）

裁剪底线：P0 4 张图 + 基础设施（预处理器/本地 bundle/Feature Flag）+ C14 合规，且 Flag OFF 始终可回退旧渲染——任何裁剪都不破坏报告可用性与 P0 门禁。

#### 5.0.3 交付判定标准

| 交付档位 | 范围 | 对应迭代 |
|:--------|:-----|:--------|
| **最低可交付** | P0 4 张图 + 基础设施 + C14 合规 | Iter 1-3 + 5 + 8 |
| **推荐交付** | P0 + P1 2 张图（行业分布/量化雷达） | Iter 1-6 + 8 |
| **完整交付** | 全部 6 张图 + 热力图框架 + 集成验证 | Iter 1-8（5.25d） |

> ⚠ **R8 说明**：新增 §5.0 不改动原迭代划分与工作量（5.25d），仅补充优先级与裁剪指引；若实际实施中某迭代超支，按 §5.0.2 顺序裁剪即可，不必推翻整体计划。

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
- Iter 2 依赖 Iter 1（需要预处理器 + 本地 bundle + Feature Flag 基础设施）
- Iter 3-6 依赖 Iter 1（需要预处理器骨架 + chart-init.js 加载框架），但**不依赖 Iter 2**
- Iter 7 依赖 Iter 1-6 全部完成（全链路集成验证）
- Iter 8 为终审轮，依赖所有前置轮次

### 高危项优先通过清单（R23 补充）

3 项**高危风险**（risk-analysis.md R6/R11/R9，后果=高）必须**首个通过**——作为迭代验收的硬性前置，任何一条不通过即视为该迭代未完成，不得进入下一轮（除非按 §5.0.2 裁剪）。

| 高危项 | 对应风险 | 硬性前置位置 | 通过标准（可度量） |
|:-------|:--------|:------------|:------------------|
| 🔴 **C14 合规** | R6（一票否决） | Iter 1 任务表 `html_writer.py` 行 + Iter 8 终审 | Iter 1：`write_html_report()` 新增 `chart_datasets`/`enable_interactive_charts` 参数后**不新增 `_ENV.globals` 条目**（验收项 ①，见下）；Iter 8：`grep -rn '_ENV\.globals\[' src/python/ \| grep -v html_jinja_env.py` → **0 matches**（验收标准 1） |
| 🔴 **异常隔离** | R11 | Iter 1 验收标准 ⑧ | `build_chart_datasets()` 某 dataset 抛异常 → **仅该图缺失、其余图正常、报告生成不失败**；顶层兜底返回空 dict（表格/占位仍存在） |
| 🔴 **隐私最小化** | R9 | Iter 1 验收标准 ① | `test_chart_data_builder.py` 断言各 chart 数据集**只含图表所需字段（日期+市值+聚合值），不含份额/成本等敏感字段**（§4.10 S4）——预处理器实现即验证，非事后补丁 |

> **判定规则**：Iter 1 结束时此 3 项全部通过才算 Iter 1 完成；Iter 8 终审复核（C14 grep 自动化为准，异常隔离/隐私由 Iter 1 单测回归兜底）。此后每次提交前，任何改动不得使已通过的 3 项回退。

### 迭代 1：基础设施搭建（1.0d）

**目标**：Python 预处理器 + Feature Flag 注册 + chart.min.js 本地集成（src/js/）+ 模板 context 注入 + `risk_metrics` 数据流

| 任务 | 涉及文件 | 测试范围 |
|:-----|:---------|:---------|
| `config/features.py` 注册 `enable_interactive_charts: True` + 更新分类注释 `2→3 项` | `config/features.py` | ✅ `is_feature_enabled("enable_interactive_charts")` 默认 True ✅ `features.json` 可覆盖 ✅ 未知 flag 返回 False（已有 `_auto_reset_feature_flags` fixture 自动清理） |
| `chart_data_builder.py`（完整 6 图骨架 + 净值/回撤数据集 | `chart_data_builder.py` | ✅ 输入 `history_data` → 输出正确 JSON 格式 ✅ ok/degraded/unavailable 三级 ✅ 空/None 输入返回空 dict ✅ **R11**：bars 缺字段/值非数字 → 该图跳过、其余图正常、顶层兜底返回空 dict ✅ **R12**：`history_data=None` 但 `all_metrics` 有值 → radar 仍构建 |
| 🔴 **高危（R6，一票否决）** `html_writer.py` context 注入 `chart_datasets` + `enable_interactive_charts` + 新增参数支持 | `html_writer.py` | ✅ `write_html_report()` 新增 `chart_datasets: dict \| None = None`、`enable_interactive_charts: bool = False` 参数 ✅ Flag OFF 时 context 不含 chart_datasets ✅ `chart_datasets` 传入后正确进入 render() context ✅ **不新增 `_ENV.globals` 条目** |
| `_report_generation.py` 整合 metrics 并传入 html_writer + Feature Flag 读取 | `_report_generation.py` | ✅ full 路径（`_generate_full_html_report`）：`prep["risk_metrics"]` + `_metrics` → 合并后调用 `build_chart_datasets()` → `write_html_report(chart_datasets=..., enable_interactive_charts=...)` ✅ both 路径（`_generate_report_both`）：无 `_metrics` → 传入 None，`build_chart_datasets()` 从 `history_data` 提取 3 个基本轴 ✅ Feature Flag 在 `_report_generation.py` 读取：`enable_interactive_charts = is_feature_enabled("enable_interactive_charts")` → 作为参数传入 html_writer（与 `is_enable_b_series(config)`/`is_enable_news(config)` 的既有读取位置一致） ✅ **不跳过 build_chart_datasets()**——纯计算 ~5ms，全量执行，html_writer 靠 Flag 控制 context 注入。⚠ orchestrator.py 不做此整合（它仅按 report_type 分发到 `_generate_report_both`/`_generate_report_full`） |
| `chart-config.js`（CSS 变量 + 颜色常量） | `chart-config.js` | ✅ 所有色值使用 `var(--chart-*)`，无硬编码 ✅ 变量缺失时用备选色值 |
| `chart-init.js` 加载骨架 + 净值/回撤图初始化函数占位 | `chart-init.js` | ✅ 独立 test HTML 页渲染验证 ✅ chart.min.js 加载失败时 `typeof Chart` 检测跳过初始化 → Canvas 回退 ✅ **S1**：所有 label/tooltip 走 Chart.js 文本渲染，无 `innerHTML` 拼接（R12） ✅ **O1**：每个 init 函数独立 `try/catch`（R13） |
| 建 `src/js/` 目录 + chart.min.js 入库 + 模板本地 script + Feature Flag 分支 + `data_unavailable` + chart canvas 容器 | `src/js/`、`report_template.html` | ✅ `src/js/` 含 chart.min.js（引擎）+ chart-config.js + chart-init.js ✅ 模板用相对路径 `<script src="chart.min.js">`（无 CDN/integrity/crossorigin）✅ 复制逻辑 `shutil.copy2(PROJECT_ROOT/src/js/*, output_dir)` ✅ Flag OFF → 无 Chart.js script 标签 ✅ `data_unavailable=True` → 显示"暂无数据"横幅 ✅ **A1**：每个 `<canvas>` 含 `aria-label`/`role="img"` + fallback 文本（R10） ✅ 复用 `_render_template` + BeautifulSoup 验证结构 |

**验收标准（可度量）**：
1. 🔴 **高危（R9/R11）** `pytest src/test/test_chart_data_builder.py` — ≥8 个用例（正常 portfolio + 正常 drawdown + 空 history + degraded + unavailable + None + **R11 脏数据隔离** + **R12 radar 独立构建**）：全部通过；且各 dataset 输出**不含份额/成本等敏感字段**（S4 数据最小化，R9）
2. ✅ `pytest src/test/test_feature_interactive.py` — ≥3 个用例（默认值 + 覆盖 + 未知 flag）：全部通过
3. ✅ `pytest src/test/unit/report/test_html_report_structure.py` — 不新增 case（现有结构不变），且已有 case 全部通过  
   ⚠ 前置：`_build_minimal_render_data()` 需新增 `chart_datasets={}` 和 `enable_interactive_charts=False`，确保现有测试获得安全默认值
4. ✅ Flag OFF 渲染 → HTML 中无 chart.min.js `<script>`，模板 `<canvas>` 容器尺寸正确
5. ✅ Flag ON 渲染 → HTML 中包含 `<script id="chart-data">` + `<script src="chart.min.js">` + chart-config.js + chart-init.js；`src/js/` 三文件已复制到输出目录
6. ✅ Feature Flag 读取位置验证：`_report_generation.py` 使用 `is_feature_enabled()` 读取，作为参数传入 html_writer（与 `_generate_report_both` 中 `is_enable_b_series(config)` 等 config 标志的既有读取位置一致），html_writer 内部不自行读取
7. ✅ DegradationTracker 兼容性确认：Chart.js 三级降级（ok/degraded/unavailable）基于 `history_data.status`，与 DegradationTracker 的 T1~T4 数据源降级系统正交，无冲突
8. 🔴 **高危（R11）**：某 dataset 抛异常 → 仅该图缺失，其余图正常渲染，报告生成不失败
9. ✅ **R12**：`history_data=None` 但 `all_metrics` 有值 → `datasets["radar"]` 仍存在（全量轴）
10. ✅ **O2**：`build_chart_datasets()` 返回键集合与 §4.11 契约清单一致（6 个固定键，R13）
11. ✅ **R14**：各图输出结构符合 §4.12 通用结构（labels/datasets/degraded 字段存在）
12. ✅ **R14**：radar 输出中 Flag 关闭指标为 `"N/A"` 字符串而非 `null`/`0`

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
4. ✅ `window.print()` → chart→img 替换成功，打印输出不含白图（手动验证）✅ 打印为浅色主题（暗色场景）✅ 图表不跨页断裂（break-inside: avoid，R16）
5. ✅ Feature Flag OFF → 自动回退 Canvas `drawSimpleChart()`，模板结构回归测试通过
6. ✅ **P1 下采样**（R11）：`len(bars) > 500` → 周聚合数据集；`≤ 500` → 保留日频；周聚合后 > 200 → 月聚合兜底；`history_data.bars` 原值不变

**测试范围边界**：
- ✅ 测：chart_data_builder 4 个新增用例、三级降级 Python 端逻辑
- ❌ 不测：Canvas drawSimpleChart 回归（未修改 → 仅验证 Flag OFF 时模板加载）、其他 4 张新图（尚未实施）、JS 打印时序细节（手动验证）

### 迭代 3：资产构成 Doughnut（0.25d）

**目标**：纯表格 → 交互式环形图

| 任务 | 预处理器 | 测试范围 |
|:-----|:---------|:---------|
| `chart_data_builder.py` 新增资产构成 dataset | `details → 按 property（资产属性）聚合市值`（键集：股票/基金/债券/现金/其他，复用 `_categorize_holding` 逻辑或 `_build_category_data` 的 property 分组） | ✅ 聚合结果与 Excel 分类汇总一致 ✅ details 为空 → 空数据集 ✅ total_mv=0 → 占位 |
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

**前提**：Iter 1 已打通 metrics 数据流——`_report_generation.py::_generate_full_html_report` 将 `prep["risk_metrics"]`（5 基本字段）+ `_metrics`（14 项全量，`compute_all_metrics()` 返回值）合入 `build_chart_datasets()`，输出 `chart_datasets["radar"]` 经 template context 传递到 chart-init.js。

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
| 全链路手动验证（Chrome 90+ / Edge 90+ 主验，Firefox 90+ / Safari 14+ 抽验，R17） | ✅ 6 张图均渲染 ✅ 缩放/悬停/图例交互正常 ✅ 打印 preview 正常 ✅ **R21**：离线场景（断网/`file://`）本地 bundle 正常渲染 ✅ **A1/A4**：禁用 Canvas 后显示 fallback 文本；375px 宽度自适应不溢出（R10） ✅ **R22**：微信内置浏览器实测（链接 + file:// 两种打开方式） |
| Canvas 回归验证 | ✅ Flag OFF 时 2 张 Canvas 图与改造前渲染一致 ✅ 模板结构测试全部通过 |

**验收标准**：
1. ✅ POC 通过 → Matrix 插件与 Chart.js v4 兼容；不通过 → 有 Canvas 2D 回退方案
2. ✅ 6 张图在 Chrome 90+ / Edge 90+ 中均可渲染和基本交互；Firefox 90+ / Safari 14+ 抽验通过（R17 矩阵）
3. ✅ 打印预览：所有 chart 以高分辨率静态图显示（2x DPI）
4. ✅ **R21** 离线验证：断网/删除 chart.min.js 场景 → 所有 chart 由 `typeof Chart` 守卫跳过 → 回退 Canvas / 表格（不再依赖 CDN 阻断）
5. ✅ Feature Flag OFF → 报告与未升级版渲染一致（Canvas + 表格）
6. ✅ **R22** 微信内置浏览器实测：**链接访问**（部署到 http/https）→ 6 图正常渲染；**file://**（传输助手/收藏点开）→ 若图表不渲染，确认 `typeof Chart` 守卫回退 Canvas/表格，数据可读（表格明细不缺失）

**测试范围边界**：
- ✅ 测：全链路集成、跨浏览器渲染、离线场景（本地 bundle）、打印降级、微信打开场景（R22）
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
| 演进路径确认 | §4.15 回退清单核对 | 三阶段演进就位（阶段 2 双路径）、Flag OFF 无 canvas 容器残留、回退验证清单全部通过（R18） |
| **`python scripts/test_runner.py --mode dev-verify,report`** | **P0 门禁** | 核心单元+基础场景+报告模块全部通过（R9：`unit_report` 不在 dev-verify 门禁内，需 `report` 模式补足） |
| 缓冲时间 | 打印时序调试、国产浏览器兼容修复 | 0.5d 预留 |

**验收标准**：
1. 🔴 **高危（R6，一票否决）**：C14 违规数为 0（grep 规则通过）
2. ✅ `python scripts/test_runner.py --mode dev-verify,report` 全部通过（P0 提交门禁，R9：report 模式补足 unit_report 覆盖）
3. ✅ `test_chart_data_builder_edge.py` 中 edge 标记与文件命名一致（C12）
4. ✅ `folders.md` 目录树同步完成（新增文件全部列出）
5. ✅ 本文档 + `plan-chartjs-risk-analysis.md` 版本号一致

### 迭代总览

| 迭代 | 内容 | 工时 | 测试用例数 | 边缘隔离 | 关键依赖 |
|:----:|:-----|:----:|:----------:|:--------:|:---------|
| 1 | 基础设施（预处理器 + Feature Flag + 本地 bundle + context + risk_metrics 流） | 1.0d | ~11（8 + 3，含 R11/R12 边界） | 不涉及 | 无 |
| 2 | 净值曲线 + 回撤图迁移（含 P1 下采样，R11） | 0.75d | ~8 | 不涉及 | Iter 1 |
| 3 | 资产构成 Doughnut | 0.25d | ~3（含 H2 data_unavailable） | 不涉及 | Iter 1 |
| 4 | 行业分布 Horizontal Bar | 0.25d | ~3（+2 edge） | ✅ `*_edge.py` | Iter 1 |
| 5 | 穿透 TOP10 Bar | 0.25d | ~2 | 不涉及 | Iter 1 |
| 6 | 量化指标 Radar（双数据源：all_metrics + risk_metrics） | 0.25d | ~8（含 H2 + 双降级路径）+1 edge | ✅ `*_edge.py` | Iter 1（risk_metrics + all_metrics） |
| 7 | 热力图框架 + 集成验证（**可裁剪**，§5.0.2） | 0.5d | ~6（手动） | 不涉及 | Iter 1-6 |
| 8 | 代码审查 + 文档 + 门禁 | 0.5d | 1（C14 grep）+ dev-verify,report | C12 合规检查 | Iter 7 |
| **合计** | | **3.75d + 1.5d** = **5.25d** | **~45** | | |

---

## 6. 涉及文件清单

| 文件 | 改动类型 | 改动内容 |
|:-----|:---------|:---------|
| `src/python/features.py` | 修改 | `_FEATURE_FLAGS_DEFAULT` 新增 `enable_interactive_charts: True` |
| `src/python/report/_report_generation.py` | 修改 | **write_html_report() 的实际调用方**。`_generate_full_html_report`：合并 `prep["risk_metrics"]`+`_metrics` → `build_chart_datasets()` → 新参数 `chart_datasets`/`enable_interactive_charts` 传入 `write_html_report()`；`_generate_report_both`：`is_feature_enabled("enable_interactive_charts")` 读取 + 参数透传（与 `is_enable_b_series(config)` 读取位置一致） |
| `src/python/report/orchestrator.py` | **不改** | 仅按 report_type 分发到 `_generate_report_both`/`_generate_report_full`，不涉及 write_html_report() 调用（R1 基线修正：原文档误归于此） |
| `src/python/report/html_writer.py` | 修改 | 新增 `chart_datasets` + `enable_interactive_charts` 参数 → context 注入 |
| `src/python/report/chart_data_builder.py` | **新建** | Python 端预处理器，6 张图数据格式转换 |
| `src/python/report/html_jinja_env.py` | **不改** | C14 约束：不新增 globals |
| `src/python/report/html_renderers.py` | **不改** | 保持现有 14 个渲染函数 | |
| `src/python/tmpl/report_template.html` | 修改 | chart.min.js 本地 script（相对路径）+ canvas 容器 + 打印降级 + Feature Flag 分支 |
| `src/js/` | **新建** | 前端 JS 资产统一目录（R21 新建）：`chart.min.js`（Chart.js v4 引擎，打包分发）+ `chart-init.js` + `chart-config.js` + `README.md`（版本号记录） |
| `src/js/chart.min.js` | **新建** | Chart.js v4 UMD 引擎（~200KB，git 跟踪；升级 Chart.js 时替换该文件） |
| `src/js/chart-init.js` | **新建** | 6 个 Chart.js 图表初始化函数 |
| `src/js/chart-config.js` | **新建** | 颜色/字体/主题常量（CSS 变量驱动） |
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

引擎加载策略：**纯本地 bundle**（`src/js/chart.min.js` 随报告分发，离线自包含，见 §4.3；R21 决策）

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
> - **v5（R1）**：基线复盘修正 — 模板行数 1845→1862；`write_html_report()` 实际调用方为 `_report_generation.py`（非 orchestrator），文件清单新增 `_report_generation.py`（修改）并将 orchestrator.py 改为不改；Feature Flag 读取位置修正为 `_report_generation.py`（与 `is_enable_b_series(config)` 既有位置一致）；§2.2 渲染管线图更新调用链
> - **v6（R2）**：数据与渲染链路复盘 — §2.1 资产构成聚合键 `code_type`→`property`（代码中无 code_type 字段）；行业分布聚合键明确为 penetration 的 per-asset `sector`；新增 R2 数据契约明细表（history_data.bars/benchmarks/metrics 返回值精确字段名）；§6.6 雷达图空值判断修正（`x or "N/A"` → `x is not None`，避免 0.0 合法值误判）
> - **v7（R3）**：架构约束核对 — §3.2 不变约束补齐 C9/C17/C18 无关行（实现 19 条全覆盖）；C16 补充 `output_dir` 已 `_absolutize_paths()` 绝对化依据
> - **v8（R5）**：技术债与降级体系 — 与 risk-analysis.md v11 同步：TD5/TD7 测试组合数合并（12 种）、TD-L3 更新为 JS 外部化已缓解模板膨胀（预估 1950-2050 行）
> - **v9（R6）**：风险清单深化 — §4.1 `build_chart_datasets()` 示例代码新增 R11 单图独立 try/except + R12 radar 独立构建（外层 if 之外）；Iter 验收需补充对应边界用例
> - **v10（R7）**：与其他计划项交互同步 — §1.2 边界新增「为 plan-7 预留」条（Chart.js Bar 能力可被 plan-7 方案 B 复用，MVP 方案 A 不阻塞）；依赖全景以 risk-analysis.md v13 附录 B 为准（plan-2→Heatmap 数据配合、plan-7 软依赖、plan-11 CSS 变量）
> - **v11（R8）**：MVP 范围收敛 — 新增 §5.0（5.0.1 图表优先级矩阵 P0/P1/P2、5.0.2 超支裁剪顺序、5.0.3 三档交付判定标准）；Iter 7 标注「可裁剪」；不改动原迭代划分与 5.25d 工作量
> - **v12（R9）**：测试与门禁 — 迭代 8 P0 门禁命令 `--mode dev-verify` → `--mode dev-verify,report`（`unit_report` 不在 dev-verify 门禁内，report 模式补足）；验收标准 2 同步；LLM mock 与输出目录隔离要求以 risk-analysis.md v15 F.3 为准
> - **v13（R10）**：可访问性与体验 — 新增 §4.8（A1 canvas fallback + aria-label/role、A2 对比度 WCAG AA、A3 色盲安全 palette、A4 移动端响应式、A5 CDN 失败表格兜底、A6 键盘可达性记技术债不做 MVP）；Iter 1 模板任务补 A1、Iter 7 手动验证补 A1/A4
> - **v14（R11）**：性能优化 — 新增 §4.9 决策（P1 服务端下采样：bars>500 周聚合 / 周后>200 月聚合兜底、P2 动画关闭、P3 CDN defer）；下采样仅作用于 Chart.js 数据集不改原始 bars；Iter 2 验收新增下采样用例；迭代总览测试计数 ~41→~45
> - **v15（R12）**：安全清单 — 新增 §4.10 五项约束（S1 禁止 innerHTML 渲染图表 label、S2 SRI hash 版本升级维护警示、S3 tojson 转义确认、S4 数据最小化、S5 CSP 可选）；Iter 1 chart-init.js 任务补 S1
> - **v16（R13）**：代码组织与模块契约 — 新增 §4.11 五项约束（O1 JS 端单图异常隔离对称 R11、O2 dataset 键名契约 6 固定键、O3 降级标记契约 degraded 字段、O4 文件行数预算、O5 命名规范）；Iter 1 chart-init.js 任务补 O1、验收补 O2 键名契约用例
> - **v17（R14）**：输出 schema 契约 — 新增 §4.12 `chart_datasets` 结构契约（通用 labels/datasets/degraded 结构 + 6 图差异 + 空值语义三态 + 日期格式 category 轴避免 time 适配器 CDN + 数值类型 + C19 豁免确认）；Iter 1 验收补 R14 两条用例
> - **v18（R15）**：Feature Flag 治理 — 新增 §4.13 五项约束（F1 总开关 > metrics_* 子开关层级、F2 默认 True 的 features.json 回退兜底、F3 生命周期废弃补删 flag 键/注释/用例、F4 注册位置功能特性 2→3 项、F5 命名规范）+ 测试三例；与 §4.7 双路径清理呼应
> - **v19（R16）**：打印与导出 — §4.5 补三点：打印强制浅色（@media print CSS 变量覆盖，为 plan-11 预留）、break-inside: avoid 防跨页断裂、toBase64Image 单图导出能力记录（P2 非 MVP）；Iter 2 打印验收同步
> - **v20（R17）**：浏览器兼容矩阵 — 新增 §4.14（支持矩阵 Chrome/Edge 90+、Firefox 90+、Safari 14+、国产 Chromium 90+；JS 用 ES5 保守语法避免 @babel/standalone；降级靠 onerror→Canvas→fallback 文本）；Iter 7 验证范围收窄描述修正为矩阵口径
> - **v21（R18）**：演进路径与回退 — 新增 §4.15（三阶段演进 Canvas→双路径→Chart.js 唯一、阶段切换 4 判定、Flag OFF 不渲染 canvas 容器细节、回退验证清单汇总）；Iter 8 任务补演进确认
> - **v22（R19）**：与数据降级体系融合 — 新增 §4.16（降级传播链可视化：数据源 T1~T4 → history_data.status 汇合 → 图表三级降级；消息口径复用 STATUS_MESSAGES 常量防两种表述；radar 走数据源缺失链区别于 history_data.status 三级降级）；Iter 1 验收补 2 条
> - **v23（R20）**：最终收敛与质量检查 — 目录 §5 锚点与标题对齐（补「× 测试范围」）；§1.3 编号重复修正（总工作量 → §1.4）；迭代总览测试计数 ~45 与 risk-analysis.md §2.4 交叉引用一致（~39→~45）；folders.md 目录树 plan/ 展开 6 文件（统计表已列但树未展开）；版本记录 v1-v23 完整性校验通过
> - **v24（R21）**：**引擎加载策略反转：CDN → 纯本地 bundle**（用户决策）——新增 §4.3 本地 bundle 决策（src/js/chart.min.js 随报告分发、离线自包含、R3/R10 闭环）；新建 `src/js/` 目录承接前端 JS 资产（chart.min.js + chart-init.js + chart-config.js + README.md）；§4.2 交付机制/模板 script/守卫改本地相对路径（`typeof Chart` 替代 `__CHART_CDN_FAILED`）；§4.8 A5、§4.9 P3、§4.10 S2/S5、§4.12、§4.14、§4.15、§5.0、Iter 1/7、迭代总览、§6 文件清单、§7 全部同步；升级 Chart.js 仅替换 src/js/chart.min.js；risk-analysis.md v27
> - **v25（R22）**：低配机 + 微信打开场景补充 — §4.9 新增 P4「DPR 限制」（`devicePixelRatio: 1.5`，低配机 + 高分屏省显存/绘制时间，对折线/柱状视觉无感）；§4.14 新增微信打开场景表（链接访问 X5/WKWebView 兼容良好 ✅；file:// 相对 JS 可能被沙箱限制 ⚠ 需实测）+ 移动端图表退化为静态呈现是合理预期说明；Iter 7 全链路验证 + 验收补微信实测（链接 + file://）；risk R2 澄清「微信链接访问兼容良好，主要不确定点是 file:// 加载」；risk-analysis.md v28
> - **v26（R23）**：高危风险硬性前置标注 — 3 项高危（R6 C14 / R11 异常隔离 / R9 隐私）显式标注为「必须首个通过」：新增 §5.0「高危项优先通过清单」小节（硬性前置位置 + 可度量通过标准 + 判定规则：Iter 1 全过才算完成、Iter 8 终审复核、提交后不回退）；Iter 1 验收标准 ①/⑧ + 任务表 `html_writer.py` 行、Iter 8 验收标准 ① 标 🔴；Iter 1 用例集补 R9 断言（各 dataset 输出不含份额/成本字段）；risk-analysis.md v29
