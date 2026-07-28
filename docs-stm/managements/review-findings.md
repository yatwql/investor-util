# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.8.8-dev

---

## 当前待处理问题

> 当前无待修复的自审问题。


---

## 归档

### 已修复问题

| # | 分类 | 问题 | 修复内容 | 修复版本 |
|---|------|------|---------|---------|
| rf-1 | **批量数据获取串行瓶颈** | `providers/` + `fetcher/` 核心批量数据获取（行情/基金排名/行业分类）在批次内逐资产串行请求，full 路径 ~85s 中 ~50s 串行 IO | 引入 BatchDispatcher（ThreadPoolExecutor）统一管理并行生命周期：链级并行 + 熔断器感知 + 限速控制 + 降级聚合。覆盖 fund.py（排名+持仓）、penetration.py、fund_performance.py、html_builders.py、industry.py 共 7 处批量调用，配置文件驱动线程池上限（max_total_workers=15）。dev-verify 1114 ✅, edge 478 ✅ | v0.8.8-dev |
| rf-2 | 文件过长 | `providers/tiantian.py`（768 行）持仓解析、季报回退、排名评级、历史净值揉合一体 | 拆分为 4 子模块：`tiantian_base.py`（HTTP 基底）、`tiantian_holdings.py`（持仓/季报）、`tiantian_ranking.py`（排名/评级/风险分析）、`tiantian_nav.py`（历史净值）；原文件删除；外部调用方直接引用子模块 | v0.8.7-dev |
| rf-3 | 文件过长 | `report/fund_style_analysis.py`（652 行）快照管理、单股分类、行业 PE、批量降级、漂移检测揉合一体 | 拆分为 3 子模块：`fund_style_base.py`（常量/快照/工具函数）、`fund_style_classify.py`（单股分类/行业 PE/入口函数）、`fund_style_report.py`（漂移检测/全基金分析）；原文件删除 | v0.8.7-dev |
| rf-4 | 缺乏性能基准 | `scripts/` — 无端到端性能基准，无法量化进度、检测回归 | 三层性能基准体系：① `perf.py` PerfCollector 每次报告生成自动计时 + 持久化到 `perf_history.jsonl` ② `perf_report.py` 独立基准脚本（mock 外部源）用于精准回归检测 ③ `perf_view.py` 历史趋势可视化工具 | v0.8.7-dev |
| rf-5 | CI 测试失败 | `pyproject.toml` 中 `required_plugins` 将 `pytest-mock` 死锁在 `==3.15.1`，但 deps 声明 `>=3.15`，导致 pip 安装的版本（如 `3.15.2`）不满足 `==3.15.1` 硬校验，pytest 拒绝启动；`format` job 的 Ruff 检查无 `continue-on-error`，阻塞 CI；`all` 模式无 `--no-timeout` 易超时截断 | ① `required_plugins` 改为 `pytest-mock>=3.15` 与 deps 一致 ② `format` job 添加 `continue-on-error: true` ③ `all` 模式添加 `--no-timeout` | v0.8.6-dev |

### 归档档案

- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)

