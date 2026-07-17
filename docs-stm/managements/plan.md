# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.6.2

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

### [P4] H. 智能预警模块去留评估（已完成评估）

智能预警（early_warning）页签目前两个数据维度均存在可靠性问题，长期处于空输出状态。已完成评估。

#### 评估结果

| 维度 | 成功率 | 结论 |
|:-----|:------:|:-----|
| 行业资金流向联动 | **0%**（9/9 全失败，7/15~7/17） | **❌ 废弃** — 低于 30% 阈值，无可靠替代源 |
| 新闻情绪聚合 | **有 Bug 导致恒空** | **✅ 保留并修复** — `_collect_relevant_news()` 中 `isinstance(analysis, dict)` 检查错误，实际 `llm_analysis` 为 `str` 类型，修复后可用 |

#### 评估细节

1. **行业资金流向**：底层依赖 `ak.stock_sector_fund_flow_rank()`（东方财富非官方接口），3 天 0/9 成功率。替代方案（新浪/同花顺/腾讯）均不可行或需付费。
2. **新闻情绪聚合**：依赖 `enabled_llm.news_correlation = true`，现已支持 `news_correlation_top_n` 配置（默认 30），成本可控。修复 `str`/`dict` 类型 Bug 后可正常产出。
3. **Bug 定位**：`early_warning.py` 第 195 行 `isinstance(analysis, dict)` 应改为字符串模式匹配（`"[高][利好]"`），见 `generators_news.py:196` 实际返回格式。

#### 后续行动

- **近期**：修复 `_collect_relevant_news` 类型 Bug，使新闻情绪聚合单维度可用
- **中期**：智能预警页签从双维度降级为单维度（新闻情绪），行业预警标签行移除
- **远期**：根据用户反馈决定是否完全移除该页签

---