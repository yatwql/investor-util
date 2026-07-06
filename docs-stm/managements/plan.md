# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-06（v0.2.89 — 新增 D 迭代：数据降级分层治理）

---

## 问题描述

个人投资者需要基于持仓数据和市场行情，生成包含市值核算、资产穿透、基金分析等内容的投资分析报告。当前无现成工具，需从零构建 Python TUI 应用，对接中国金融数据源，输出 Excel 和 HTML 格式报告。

---

## 需求

完整需求详见 [`docs-stm/managements/requirements.md`](requirements.md)。

---

## 关键技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| TUI 框架 | 原生 `input()` 循环 | 零依赖，开发最快，满足菜单需求 |
| Excel 库 | `openpyxl` | 原生支持 .xlsx 读写、颜色/字体格式设置 |
| HTTP 客户端 | `httpx` | 同步/异步、连接复用，比 requests 现代 |
| 数据解析 | 手动解析，不使用 pandas | 减少依赖，数据量小，自定义校验更可控 |
| 配置持久化 | `data/config/config.json` | JSON 简单可靠，无需额外依赖 |
| AI 全球政经局势 + 智囊团深度复盘 + 持仓体检报告 + 穿透深度分析 + 财经新闻热点与持仓关联分析 | LLM 生成 | 支持 Claude/OpenAI/DeepSeek API，缓存策略分层，System Prompt 外部可配置 |
| 报告模板 | 程序生成（Excel openpyxl / HTML Jinja2） | Excel 和 HTML 报告均程序化生成 |

---

## 当前配置架构

LLM 配置拆分为两个独立文件：

| 文件 | 内容 | 用途 |
|------|------|------|
| `data/config/llm_key.json` | 4 个必填 + 4 个可选回退字段 | API 调用渠道（provider / api_key / model / endpoint / fallback_*） |
| `data/config/llm_settings.json` | 所有非敏感配置 | 参数调优（temperature、timeout、cache、system_prompt、thinking 等） |

---

## 系统影响

- `data/holdings/`、`data/cache/`、`data/config/` 在首次运行时需保证存在
- `data/config/config.json` 在程序生命周期外持久保存，含 `output_dir` 字段控制报告输出位置
- 程序依赖外部中国金融 API，网络不可用时降级运行（使用缓存数据或显示"--"）
- 持仓目录多 xlsx 文件时，用户通过 TUI 选择

---

## 风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 腾讯/东方财富 API 变更或封禁 | 行情获取失败 | 备用链路自动切换；缓存支撑当日使用 |
| 持仓 xlsx 格式与预期不一致 | 解析失败或数据错误 | 固定列名解析 + 字段校验 + 友好提示 |
| 基金穿透计算量大 | 报告生成变慢 | 穿透结果缓存每日更新 |
| LLM API Key 未配置 / 超时 | 全球政经局势 / 智囊团深度复盘不可用 | 降级输出占位文本，不阻塞报告生成 |
| LLM Token 费用超预期 | 成本增加 | 缓存 LLM 结果；限制输入上下文；分层缓存 TTL |

---

## 验证

每次迭代完成后：
1. 运行 `python src/python/main.py`，确认 TUI 正常导航
2. 选择对应功能生成报告文件
3. 打开输出目录下的报告确认内容完整
4. 模拟异常场景（断网、空目录、格式错误）确认程序不崩溃

---

## ✅ 已完成迭代

v0.1.x（Iter 1.1~1.5：项目骨架、持仓读取、数据源接入、Excel 输出打磨）的详细设计见 [`docs-stm/archive/archived_plan.0.1.x.md`](../archive/archived_plan.0.1.x.md)。

所有已完成迭代（A/A2/A3/A4/A5/B/C/J/K/L/P/N/Q/R/M/T/S/V/U/W/X/Y1/Y2/Y3/Y4/Y5/Y6/Z1/Z2/Z3/Z4）的详细变更记录见 [`docs-stm/managements/changelog.md`](changelog.md)。

B 迭代（基金深度分析 4 模块：基金经理变更监控/持仓重合度矩阵/持仓集中度监控/基金风格分析）和 C 迭代（报告序号可配置）已完结，详见 changelog.md 及 `docs-stm/archive/c-iteration-design.md`、`docs-stm/archive/c-p1b-excel-title-number-fix.md`。

---

### 待实现方向（按风险收益比排序）

> 注：字母编号跳跃出于历史分配——已完成迭代占用了相应字母（详见上方 ✅ 已完成迭代），剩余字母保留给此前已规划但优先级较低的后续迭代。

---

### [P1] D. 数据降级分层治理（高难度 / 高价值）

**问题：** 系统依赖大量外部数据源，但除了持仓 xlsx 读取和价格/净值获取是"主数据"，
其余数据本质上是"附加信息"——报告丰富了它们，但它们没了报告不应崩。
当前各模块对这些外部数据不可用时的降级策略存在三方面缺陷：

1. **处理不一致**：Excel 端与 HTML 端对同一数据源的异常捕获粒度和用户提示不统一
2. **反馈不足**：`--` 占位符无法让用户区分"数据确实为零"和"数据获取失败"
3. **日志缺失**：部分 `except Exception: return "--"` 无任何日志，故障定位困难

**核心思路：** 按数据源稳定性分 **T1（核心）/ T2（稳定增强）/ T3（不稳定增强）/ T4（附加增值）** 四层，
每层降级策略不同（详见设计文档）。

**分层概要：**

| 层 | 包含数据 | 不可用时表现 | 实施阶段 |
|:--:|:---------|:------------|:--------:|
| T1 | 持仓 xlsx + 价格/净值 | 报告无意义，Provider Chain 已有降级 | 不动 |
| T2 | 指数/排名/穿透持仓/基准（tencent/sina/tiantian 稳定源）| 列级 `--` + ⚠ 状态摘要 | Phase 1 |
| T3 | 行业分类/概念（push2 不稳定源）| 列级 `--` + ℹ 状态摘要 + 缓存 TTL 加倍 | Phase 1 |
| T4 | akshare 系列/新闻/B 系列/LLM | 模块级占位/隐藏 | Phase 2-3 |

**详细设计文档：** [`docs-stm/plan/d-iteration-data-degradation-design.md`](../plan/d-iteration-data-degradation-design.md)

---

### 实施阶段（共 4 个 Phase）

---

#### Phase 0 — 盘点与架构设计（文档阶段，0 代码）

设计文档在 [`docs-stm/plan/d-iteration-data-degradation-design.md`](../plan/d-iteration-data-degradation-design.md)，
含 19 个数据源分层盘点、三端降级行为规范、`_data_status` 机制、变更清单。
文档阶段无代码，无回退风险。

---

#### Phase 1 — T2+T3 增强数据降级统一

**范围：** fund_performance（排名/基准）、penetration（持仓/行业分类）、summary（指数）
**交付：** `_data_status` 字典追踪机制 + T2 用 `⚠` / T3 用 `ℹ` 语气区分 + Excel/HTML 状态摘要渲染
**回退：** 每个模块独立提交，单模块可 revert

---

#### Phase 2 — T4 附加数据降级统一

**范围：** akshare 盈利预测/分红/股息率/资金流向 + B 系列 4 模块 + 新闻 + 预警 + LLM
**交付：** 模块级占位文本 + `_write_placeholder()` 通用函数 + 新闻 source_status
**回退：** 按模块逐个提交，独立 revert

---

#### Phase 3 — 全局异常审计 + 回归测试

**范围：** `category.py`, `html_builders.py`, `html_writer.py`, `fund_style_analysis.py`, `fetcher/fund.py`, `llm/generators.py`
**交付：** 补齐静默异常日志、拆分大粒度 try/except、编写全降级路径 edge 测试
**回退：** 逐个模块拆分 + 立即跑测试，单模块异常可独立 revert
| 持仓全空 → fund_overlap 占位 | mock 空持仓 | Phase 2 |
| 新闻全源失败 → news 占位 | 5 源全 mock `[]` | Phase 2 |
| 部分新闻源失败 → 源状态摘要 | 部分 mock 空 | Phase 2 |
| 大 try/except 拆分回归 | 回归测试 | Phase 3 |
| HTML vs Excel 消息一致性 | 正则提取对比 | Phase 3 |

**可度量标准：**
- 不存在无日志的 `except: pass`
- `html_writer.py` 大 try 块拆分为独立 catch，粒度对齐 Excel 端
- 新增 edge 测试 ≥ 15 项
- `pytest src/test/ -m "edge"` 全通过
- 全量测试不降级

**回退策略：** 每项修复独立 commit，逐项可 revert。

---

#### 总体风险登记

| 风险 | 影响 | 缓解 |
|:-----|:-----|:-----|
| Phase 1 改页脚格式影响回归测试断言 | 回归失败 | Phase 0 定稿格式后同步更新测试 |
| Phase 3 拆大 try/except 引入行为变化 | 回归 | 拆分后立即跑该模块现有测试 |
| Excel/HTML 消息对齐因字数限制视觉差异 | 视觉不一致 | Phase 0 定 mock，Phase 3 逐场景比对 |
| mock 测试覆盖不了真实 API 断网场景 | 线上行为差 | 补充 testplan.md §4 手动回归项 |

---

### [P4] F. LLM 分析增强（低难度 / 中价值）

- **环比分析**：对比历史报告摘要，说明组合变化趋势
- **报告对比**：将本次报告的关键指标（市值/盈亏/仓位）与上次对比，输出变化摘要
- **回撤监控**：从历史缓存中提取持仓的连续回撤曲线

---

### [P5] O. 工程化增强（低难度 / 低价值）

- **CI/CD 集成**：添加 GitHub Actions 自动化流水线，每次 Push 自动运行 `pytest`
- **Excel 页签并行写入**：报告生成时每个页签独立写入，可考虑并行加速