# 实现计划归档 — v0.5.x

> 归档时间：2026-07-15
> 原始文件：`docs-stm/managements/plan.md`
> 涵盖版本：v0.5.0 ~ v0.5.6

---

## v0.5.x 变更概要

### ✅ [P3] I. 组合历史走势与基准指数比对（v0.5.6 已完成）

> 原始设计：`docs-stm/archive/v0.5.x/portfolio-benchmark-comparison/I-comparative-benchmark-design.md`
> 迭代计划：`docs-stm/archive/v0.5.x/portfolio-benchmark-comparison/I-comparative-benchmark-iteration.md`

在组合历史走势和回撤分析中叠加参照指数线（沪深300、标普500等），让相对收益和相对回撤可量化。

**要点**：
- 默认指数选择：A 股用沪深300（000300）、美股用标普500（SPX），可配置
- 走势叠加：组合历史走势图叠加指数归一化曲线（起算日归一化到同一基点）；回撤分析叠加指数回撤曲线
- 归一化算法：三段式对齐（组合起算日 / 指数首日 / 对齐起算日），LOCF 填充 + 起算日对齐
- `benchmark.py` 并行获取指数历史日线（ThreadPoolExecutor）
- HTML 原生 Canvas 渲染 drawSimpleChart 多 dataset 版本，移除 Chart.js CDN 外部依赖
- Excel `portfolio_history` 页签每基准一列（归一化值 0.00 格式），`drawdown_analysis` 页签对比指标矩阵
- 新增测试：benchmark 集成测试 + normalize_benchmarks 已有 16 项单元 + 7 项边缘场景

**迁移**：
- [P3] I 从待实现方向移至"已完成迭代"

### 测试范围修正（v0.5.5）

`dev-verify`（开发期快速验证）从 2407 项精简为 815 项（核心单元 + 基础场景）；`verify`（合入验证）从 1043 项扩展为 1775 项（核心/配置/新闻/LLM + 全量场景）。

### 文档系统性重构（v0.5.5）

- `requirements.md`：扁平 11 节 → 两大部分 12 章，统一需求标识体系
- `technical.md`：~950 行 → ~2050 行，12+ 架构图，设计约束 6 领域分组
- `llm-technical.md`：~159 行 → ~980 行，7 幅架构图/流程图
- 用户文档分册提取（how-to-start.md → how-to-menu.md 独立成册）
- 用户文档精简（移除技术实现细节，保留纯配置/操作说明）

### 基准指数对比发布（v0.5.6）

I 迭代 9 轮全部实现完毕，正式发布：

- `code_utils.py` 新增 `is_index_code()` 等判定函数
- Tencent/Sina 新增 `fetch_index_kline()` 跳过 A 股类型检查
- `history_index` chain + registry 注册（CACHE_MONTHLY，无分组）
- `fetch_index_history()` 通过 chain 路由，会话级缓存复用
- `report/benchmark.py` — `fetch_benchmarks()` 并行获取 + `normalize_benchmarks()` 归一化算法
- HTML 渲染：`drawSimpleChart()` 多 dataset（组合实线 + 基准虚线），图例 + tooltip
- Excel 输出：`portfolio_history` 页签每基准一列，`drawdown_analysis` 页签对比指标矩阵
- 配置 `history.benchmark_indices` 作为 Kill-Switch：缺失或空字典时不产生任何影响

### v0.5.x 其他重要变更

- **覆盖阈值可配置**（0.5.5）：`config.json` 新增 `history.coverage_threshold`
- **C1 合规**（0.5.4）：`portfolio_history.py` 全面改用 `code_utils` 函数进行代码路由
- **尾端覆盖检查**（0.5.3）：组合走势终止日新增覆盖比例检查，与起算点对称
- **重叠自动刷新**（0.5.3）：历史数据重叠时自动清除缓存并重新获取
- **LLM 可见性可配置**（0.5.1/0.5.2）：`enabled_llm` 配置字段 + `is_enable_llm()` 统一入口
- **Provider 熔断器阈值 per-instance**（0.5.1）
- **`should_create_sheet` 重构 + `set_sheet_title` 移除**（0.5.0）
