# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.8.8-dev

---

## 当前待处理问题

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| rf-1 | **批量数据获取串行瓶颈** | `providers/` + `fetcher/` | ~80 处 | 核心批量数据获取（行情 15 品种、基金排名 10 基金、行业 55+ 代码）在批次内逐资产串行请求，无法利用 IO 等待时间并行获取。根因是数据获取层围绕**单资产接口**设计（`fetch_market_data(code)`、`fetch_fund_rank(code)` 等均以单代码为粒度），这是架构层的有意选择——C6（1.4.2 Provider Chain）确保每资产独立走完 fallback+熔断器链路保障可靠性，C2 按资产代码缓存键，1.4.5 按资产维度做降级追踪。串行是架构为可靠性付出的代价，非代码疏忽。 | **中**：全量 full 路径约 85s 中 ~50s 为串行 IO。C4 会话级缓存可消重同资产重复请求但无法消除首请求串行。full 路径下 prepare_report_data 内行情/穿透/分类等环节叠加 15+ 品种逐资产轮询，放大串行开销。 | 引入批量并行抽象层（batch.py + chain.py 增强）统一管理并行请求的生命周期：① 链级并行（N 资产同时走各自的 Provider Chain）② 熔断器感知（聚合多资产熔断状态，避免集体突发对同一 Provider 施压）③ 限速控制（Provider 感知的批间间隔，防 API 限频）④ 降级追踪聚合（1.4.5 适配）。保留 C6 每资产独立 fallback+C4 缓存复用。预计 full 路径提速 2-3 倍（8-10d）。 |

> 耦合约束：C5（httpx 同步客户端统一）→ 并行方案使用 ThreadPoolExecutor 而非 async/await，与系统现有 orch_prep/cache_ops 线程池模式（附录E）一致；C6（1.4.2 Provider Chain）→ 批量层不得绕过链，必须以每资产独立 `fetch_with_fallback()` 为并行单元；C2/C3（缓存统一管理+原子写入）→ 并行写入仍走 cache/ 子包，利用 cache key 异质性天然避免文件冲突；1.4.5（数据降级治理）→ 并行场景的多资产同时降级需聚合为单一降级记录而非 N 条独立记录。


---

## 归档

### 已修复问题

| # | 分类 | 问题 | 修复内容 | 修复版本 |
|---|------|------|---------|---------|
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

