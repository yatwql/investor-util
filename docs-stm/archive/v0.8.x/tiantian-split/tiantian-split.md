# tiantian.py 拆分

> **原计划**：`plan-engineering.md` §1
> **对应自审**：`rf-2`
> **原始文件**：`src/python/providers/tiantian.py`（768 行）
> **拆分结果**：4 子模块
> **状态**：✅ 已完成（v0.8.7-dev）
> **归档日期**：2026-07-28

## 子模块列表

| 子模块 | 职责 |
|--------|------|
| `tiantian_base.py` | HTTP 基底 |
| `tiantian_holdings.py` | 持仓/季报 |
| `tiantian_ranking.py` | 排名/评级/风险分析 |
| `tiantian_nav.py` | 历史净值 |

原文件删除，外部调用方统一改为直接引用子模块。

## 要点说明

- 拆分时**未保留向后兼容重导出层**——所有外部调用方统一改为直接引用子模块
- 拆分后**测试覆盖率未降低**——每子模块对应的测试用例均存在并标记正确
- 参见 `review-findings.md` 归档区 `rf-2`
