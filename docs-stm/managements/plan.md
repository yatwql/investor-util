# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.6.0

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

> 配置架构详见 [`requirements.md §9 配置管理`](requirements.md#9-配置管理)。

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

> 验收标准详见 [`testplan.md §6 验收标准`](testplan.md#6-验收标准)。

已完成迭代的实现计划已归档：

- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)

## 待实现方向（按风险收益比排序）

---

### [P4] H. 智能预警模块去留评估（高难度 / 中价值）

智能预警（early_warning）页签目前两个数据维度均存在可靠性问题，长期处于空输出状态，需评估去留或重构方案。

#### 现状

| 维度 | 上游数据 | 现状 |
|:-----|:---------|:-----|
| 行业资金流向联动 | `akshare_extras.get_sector_fund_flow()` | 东方财富接口极不稳定，经常返回空列表或请求失败 |
| 新闻情绪聚合 | 新闻 LLM 情感分析（`sentiment` 字段） | 依赖 `enabled_llm.news_correlation = true`，门槛高，Token 成本大 |

当前 `compute_early_warnings()` 在两个维度均空时直接返回 `has_warnings: False`，导致页签始终显示"数据不可用"或占位文本。

#### 评估要点

1. **行业资金流向数据源的可靠性评估**：连续监控一段时间，统计 `get_sector_fund_flow()` 的成功率。如持续低成功率（< 30%），应考虑废弃该维度
2. **新闻情绪维度独立可行性**：如果弃用行业资金流向，新闻情绪聚合能否独立撑起智能预警？需评估——在不依赖行业资金流向时可产出有价值的预警内容
3. **替代数据源调研**：是否有更稳定的行业资金流向/板块资金数据源（如新浪财经板块资金流、同花顺等）
4. **去留结论**：
   - **保留并降低依赖**：行业资金流向改为可选增强，新闻情绪聚合作为基础内容，两者均空时跳过页签而非显示占位
   - **完全移除**：删除 `early_warning.py`、`test_early_warning.py`、`test_early_warning_edge.py` 及相关注册表条目，减少维护负担
   - **重构合并**：将行业预警剥离为独立模块，新闻情绪聚合并入新闻关联分析页签

#### 决策标准

- 行业资金流向连续 30 天成功率 < 30% → 移除该维度
- 新闻情绪聚合在无行业数据时能否单独产出 ≥ 3 条有价值预警 → 可独立保留
- 若两维度均不可靠 → 建议完全移除该页签

---

### [P3] I. 命令行模式（CLI）— 支持定时任务驱动报告生成

详见迭代计划 [`cli-mode-iteration-plan.md`](../plan/cli-mode-iteration-plan.md) 和技术设计 [`cli-mode-technical-design.md`](../plan/cli-mode-technical-design.md)。

---