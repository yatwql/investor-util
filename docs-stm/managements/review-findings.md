# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.10-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C20）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> 来源：`archive/v0.9.x/chartjs-upgrade/plan-chartjs-report-upgrade.md` §4.5/§4.7/§4.8/§4.10/§5 Iter 7 + `archive/v0.9.x/chartjs-upgrade/plan-chartjs-risk-analysis.md` §4 TD 表。
> plan-1 代码与自动化测试已落地（dev-verify 1181 passed），以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复 |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器 |
| **rf-117** | A6 键盘可达性未做（Chart.js tooltip 为鼠标悬停驱动，键盘聚焦不触发） | 设计明确"不做 MVP 记入技术债"（upgrade.md §4.8 A6）；如需支持，给 chart-init.js 加键盘交互扩展 |
| **rf-118** | 相关性矩阵 Heatmap 仅占位文本（Chart.js Matrix 插件未引入） | 依赖 plan-2 提供 `correlation_data` 后引入 `chartjs-chart-matrix` 渲染（Iter 7 已推迟，非 YAGNI） |
| **rf-120** | S5 CSP 未配置（报告为离线静态 HTML，无外部域名） | 可选不做 MVP（upgrade.md §4.10 S5）；未来若加 CSP 仅需 `script-src 'self'` |
| **rf-121** | TD2：报告体积增大 ~200KB（chart.min.js 随每份报告复制） | R21 决策接受的"报告自包含"代价；如未来对体积敏感可改 CDN 优先 + 本地兜底 |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> 行数核对：2026-08-03（`wc -l` 实测）。`fact_checker.py`（rf-76）与 `handlers_config.py`（rf-77）均已拆分处理（详见归档 [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) v0.9.9 章节）。拆分判定标准：**800 行是编码规范硬上限，超过必须拆分**；500-800 行为**可选优化**，仅当职责确实割裂、拆分风险低时才建议做——内聚型文件（如中央注册表、单类内聚）即使 >500 也维持现状。当前 P2A 无待处理项，其余维持现状。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 653 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 537 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 534 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 未超限（<500，维持现状） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 477 | 未超限（<500，维持现状） | Excel 编排器 |

#### P2B — 文档与实现不符（低优先级，增量改进）

| # | 问题 | 修复方向 |
|---|------|----------|

### P3 — 测试覆盖缺口（建议补齐）

| # | 位置 | 问题 |
|---|------|------|

---

## 已修复（摘要）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| **rf-165** | TUI 按 W 调仓模拟：持仓目录只有基准一份文件时候选为空直接退出，从不生成报告 | `_select_candidate_file` 空候选改为引导手动输入目标文件完整路径（`_input_candidate_path`），回车取消返回 None | 详见 changelog.md v0.9.10-dev Fix |
| **rf-166** | TUI 按 W 调仓模拟：`get_config_cache()` 未初始化时回退 `{}`，`output_dir` 用相对路径 `"reports"`（依赖启动目录，与 CLI 绝对路径不一致） | `_cmd_whatif`/`_select_candidate_file` 回退 `get_config()`（absolutized 路径），输出目录与 CLI 一致 | 详见 changelog.md v0.9.10-dev Fix |
| **rf-167** | `test_set_atomic_write_content` 隔离缺陷：扫描全局系统临时目录断言无 `tmp*.json`，而原子写临时文件实际创建在缓存目录（`.tmp` 后缀）——断言对象错误，仅在并行测试误落系统临时目录时偶发失败，且从未真正验证原子写清理 | 改为扫描缓存目录内 `.tmp` 残留（`os.path.dirname(_cache_path)`），真正验证原子写清理且隔离到测试自身缓存目录 | 详见 changelog.md v0.9.10-dev Fix |
| **rf-168** | 智囊团深度复盘排名事实校验误报：`check_ranking_correctness` 将"第N大/前N大持仓"等一律按"最大持仓"校验（仅接受市值第1名），且取"句中第一个代码"作为声称对象——LLM 调仓方案表里"040046 继续持有第一重仓"（正确）被归因到句首 561910，"561910 已是组合第三大持仓"（正确）被当"最大持仓"误报"声称 X 为最大持仓" | 按声称类型拆分校验（`_RANK_MAX_PATTERN` 最大→第1名 / `_RANK_ORDINAL_PATTERN` 第N大→第N名 / `_RANK_TOP_PATTERN` 前N大→前N名内），归因改为表格行内就近找代码（跨行不误归因），移除"主要持仓"模糊声称校验 | 详见 changelog.md v0.9.10-dev Fix |

> 已发布版本（v0.9.0 ~ v0.9.9）已修复问题记录已迁移归档至 [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) （v0.9.0 ~ v0.9.5：rf-90 ~ rf-144；v0.9.6 / v0.9.7 / v0.9.8：rf-115/116/119、rf-145 ~ rf-159；v0.9.9：rf-76/77、rf-160 ~ rf-164），本表仅跟踪当前迭代（0.9.10-dev）修复项。

---

## 归档

### 归档档案

- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.9（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
