# 三层性能基准体系

> **原计划**：`plan-engineering.md` §3
> **状态**：✅ 已完成（v0.8.7-dev）
> **对应自审**：`rf-4`
> **归档日期**：2026-07-28

## 实际完成内容

三层性能基准体系已于 v0.8.7-dev 实现。

| 层 | 模块 | 功能 |
|:---|:-----|:------|
| **L1 自动计时** | `src/python/perf.py`（PerfCollector + ReportRunSnapshot） | 每次报告生成自动记录各阶段耗时到 `data/state/perf_history.jsonl`，原子写入（C3 约束） |
| **L2 独立基准** | `scripts/perf_report.py` | mock 外部源的独立基准脚本，用于精准回归检测 |
| **L3 趋势工具** | `scripts/perf_view.py` | 读取 JSONL 历史文件输出版本间耗时对比 Markdown 表格 |

## 关键设计点

- PerfCollector 为生成函数内的**局部实例**（C14 约束：无模块级全局变量）
- 路径从 `constants.PROJECT_ROOT` 推导（C16 路径绝对化）
- 不向 pipeline_data 注入计时数据，仅独立 JSONL 文件（C19 Schema 契约）
- 三路径埋点：basic（1 阶段） / both（5 阶段） / full（7 阶段）
- 即使部分失败也记录 perf data（在 try/except 之后调用 `perf.save()`）

## 关联文档

- 设计方案：[`perf-design-and-verification.md`](./perf-design-and-verification.md)（同目录）
- 性能历史数据：`data/state/perf_history.jsonl`
