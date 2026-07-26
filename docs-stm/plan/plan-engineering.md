# 工程质量与性能优化：大文件拆分 + 异步化 + 基准测试

## 目录

1. [大文件拆分（tiantian.py / fund_style_analysis.py）](#1-大文件拆分)
2. [异步化关键 HTTP 路径](#2-异步化关键-http-路径)
3. [Performance Benchmark](#3-performance-benchmark)

---

## 1. 大文件拆分

### 概述

`providers/tiantian.py`（~768 行）和 `report/fund_style_analysis.py`（~652 行）已在 `review-findings.md` 中标注为 P3 问题。两项独立职责揉合在一个文件中，影响可维护性和测试覆盖。

### 收益

- **可测试性**：拆分后每个子模块的测试可以独立 mock，当前大文件的测试覆盖很难做到彻底
- **可读性**：每个文件一个职责，新人读代码不需要翻 700 行找入口
- **降低合并冲突**：多人开发时，大文件是冲突热点
- **review-findings 清零**：P3-9 和 P3-10 两个待办可以关闭

### 风险

- 拆分涉及重构导入路径，需注意循环依赖
- 回归测试需要覆盖全功能路径，不能遗漏原有行为
- `tiantian.py` 是天天基金数据源的核心文件，拆分后需验证全部数据端点正常

### 工作量估算

| 文件 | 拆分方案 | 天数 |
|------|----------|------|
| `tiantian.py` | 拆为：`base.py`(公共HTTP/解析) / `nav.py`(净值) / `ranking.py`(排名) / `holdings.py`(持仓) | 1.5 |
| `fund_style_analysis.py` | 拆为：`snapshot.py`(快照管理) / `style.py`(风格计算) / `report.py`(输出) | 1 |
| 验证 | 跑全量单元测试 + 集成测试 | 0.5 |
| **合计** | | **3 天** |

### 拆分策略

不一次性拆完，以原子操作为单位：
1. 从原文件逐个提取独立函数/类
2. 每提取一个模块就跑一遍对应测试
3. 原文件保留 import 重定向（兼容外部调用方）
4. 全部提取完成后删掉原文件

---

## 2. 异步化关键 HTTP 路径

### 概述

当前 80+ 处 `httpx.Client` 同步请求串联执行。单次报告生成中，行情获取（15 个品种）、基金排名（~10 个基金）、行业数据（55+ 代码）等环节完全串行，是性能瓶颈。

### 收益

- **生成速度提升 2-3 倍**：15 个品种的行情并行获取，从 ~15 秒降到 ~3 秒
- **降低超时风险**：串行链路中一个品种超时阻塞后续全部；并行时独立超时
- **更好的资源利用**：CPU 等待 IO 时无事可做，异步让等待时间重叠

### 风险

- 混合同步/异步代码容易出错：同步块中 `asyncio.run()` 的嵌套调用
- 部分数据源（akshare）本身不是异步友好的，需在线程池中运行
- 测试框架需要 `pytest-asyncio` 支持
- 改造成本大：80+ 处调用点，涉及几乎所有 Provider 和 Fetcher

### 工作量估算

| 阶段 | 内容 | 天数 |
|------|------|------|
| 基础设施 | 异步 HTTP 客户端 + 连接池 + 超时配置 | 1 |
| 核心路径改造 | 行情获取(price.py) + 基金净值(fund.py) → async | 2 |
| 次级路径改造 | 行业/指数/新闻 → async | 1.5 |
| 测试适配 | pytest-asyncio + mock 适配 | 1 |
| **合计** | | **5.5 天** |

### 建议策略

**不做全量异步化**，只改造瓶颈路径：
1. `price.py` 的批量行情获取（15 个品种并发请求）—— 收益最大
2. `fund.py` 的净值/排名批量获取
3. `industry.py` 的行业数据批量获取
4. 其余保持同步（收益不足以覆盖改造成本）

### 架构方案

```python
# 新增 async_runner.py 统一管理异步任务组
class AsyncTaskGroup:
    async def run(self, tasks: list[Callable], concurrency: int = 5) -> list:
        semaphore = asyncio.Semaphore(concurrency)
        ...
```

---

## 3. Performance Benchmark

### 概述

当前没有端到端的性能基准。不知道：一次完整报告生成需要多久？哪个环节最慢？版本升级后性能是变好还是差了？

### 收益

- **量化进度**：知道瓶颈在哪（当前是 HTTP 串行请求），优化有目标
- **回归检测**：合并新代码后跑一次基准，性能退化立刻发现
- **用户预期管理**：可以告诉用户"预计需要 X 分钟"

### 风险

- 基准测试依赖网络状态和外部 API 响应时间，数据天然有波动
- 需要一个干净的基准环境（缓存清空 vs 缓存热，差别很大）
- 测试数据需要固定版本（持仓文件、日期快照），不能依赖实时行情

### 工作量估算：**1 天**

### 实现方案

```bash
# 用法
python scripts/perf_profile.py                     # 全量基准（冷缓存）
python scripts/perf_profile.py --cache warm        # 热缓存基准
python scripts/perf_profile.py --compare HEAD~3    # 与 3 次提交前对比
```

输出 JSON 报告：
```json
{
  "version": "0.8.6-dev",
  "timestamp": "2026-07-26T18:00:00",
  "total_seconds": 85.3,
  "phases": [
    {"name": "行情获取", "seconds": 12.1, "requests": 15},
    {"name": "基金数据", "seconds": 18.4, "requests": 10},
    {"name": "新闻获取", "seconds": 25.7, "requests": 5},
    {"name": "报告生成", "seconds": 29.1}
  ]
}
```
