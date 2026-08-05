# 个人投资分析报告生成小助手 - 自我审查问题记录
> 文档版本：0.10.7-dev
> **编号源**：`rf-next = 234`（新增问题取此编号，完成后更新为 +1；已用最大 rf-233，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复 |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）



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

---

## 已修复（摘要）

- **rf-233** 跨平台测试可移植性：`test_default_path_under_state_dir` 硬编码正斜杠子串做路径 `in` 匹配，Windows 反斜杠路径断言落空（Windows dev-verify 单点失败）。修复：断言前将实际路径分隔符统一规范化为 `/` 再匹配（源码/conftest 本就 OS 感知）。详见 changelog [0.10.7-dev]。
- **rf-229** 语义命名索引双向校验：新增 `scripts/check-semantic-index.py` 正面校验「功能语义命名表」与代码一致（正向 `report_submodules` 键登记 / 反向僵尸条目 / 合并章 sheet key 存在性）；表存量修正（`cost_lots` 补登记、僵尸条目移除）；纪律升级为架构设计约束的「约束外参照」并接入 P0/P2 门禁。详见 changelog [0.10.7-dev]。
- **rf-217** 调仓建议可行化层区分场内/场外渠道：`holdings_details` 契约新增 `channel` 字段（报告层按账户关键词 `is_offsite_fund` 判定填充），`rebalance_advisor` 按渠道计算份额取整与费用（场外整数份 + 赎回费，覆盖 161725/110022 等 16/11 开头代码被场内前缀误判的场外持有场景）；显式 channel 优先、无渠道回退既有证券类型判定。详见 changelog [0.10.7-dev]。

> v0.10.6 发布时已修复项（rf-227/rf-228/rf-230/rf-231/rf-232）已整体迁入 [归档档案](#归档档案) 的 `archived_review-findings.0.10.x.md`。

## 归档

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.6（2026-08-04 ~ 2026-08-05，rf-204~rf-232）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
