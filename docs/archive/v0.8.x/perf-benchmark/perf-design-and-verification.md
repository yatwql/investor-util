# 三层性能基准体系实现方案 — ✅ 已完成（v0.8.7-dev）

## Context

P3-13（review-findings.md）记录缺少端到端性能基准，无法量化进度、检测回归、管理用户预期。应要求实现三层结构，每次客户端生成报告时自动收集性能数据。

## 实际完成对照

| 原计划项 | 状态 | 说明 |
|:---------|:----|:-----|
| `src/python/perf.py` | ✅ 已完成 | PerfCollector + ReportRunSnapshot + 原子写入 |
| `scripts/perf_report.py`（独立基准） | ✅ 已完成 | mock 外部源的精准回归检测脚本 |
| `scripts/perf_view.py`（趋势工具） | ✅ 已完成 | 读取 JSONL 历史文件输出版本间对比表格 |
| orchestrator 三路径埋点 | ✅ 已完成 | basic/both/full 各路径嵌入计时埋点 |
| 测试隔离 conftest.py | ✅ 已完成 | `_isolate_sensitive_paths` 重定向 perf_history.jsonl |
| review-findings.md P3-13 更新 | ✅ 已完成 | 移至归档区 |
| folders.md 新增条目 | ✅ 已完成 | perf.py / perf_view.py 已登记 |
| changelog.md 更新 | ✅ 已完成 | v0.8.7-dev Added 已有记录 |

## 架构约束遵从

| 约束 | 设计要点 |
|:-----|:---------|
| C3 原子写入 | tempfile.mkstemp + os.replace |
| C8 统一日志 | `logging.getLogger("invest")` |
| C14 无模块全局 | PerfCollector 为生成函数内的局部实例 |
| C16 路径绝对化 | 路径从 constants.PROJECT_ROOT 推导 |
| C19 schema 契约 | 不向 pipeline_data 注入计时数据，仅独立 JSONL 文件 |
