# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-13（v0.4.4）

---

## 审查问题索引

> 早期审查问题和实现计划已归档：详见 [`archived_plan.0.1.x.md`](../archive/archived_plan.0.1.x.md) · [`archived_plan.0.2.x.md`](../archive/archived_plan.0.2.x.md) · [`archived_plan.0.3.x.md`](../archive/archived_plan.0.3.x.md)。

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

## ✅ 已完成迭代

所有已完成迭代的详细变更记录见 [`changelog.md`](changelog.md)。早期实现计划和审查记录已归档：[`archived_plan.0.1.x.md`](../archive/archived_plan.0.1.x.md) · [`archived_plan.0.2.x.md`](../archive/archived_plan.0.2.x.md) · [`archived_plan.0.3.x.md`](../archive/archived_plan.0.3.x.md)。

---

### 待实现方向（按风险收益比排序）

> 注：字母编号跳跃出于历史分配——已完成迭代占用了相应字母（详见上方 ✅ 已完成迭代），剩余字母保留给此前已规划但优先级较低的后续迭代。

---

### [P5] O. 工程化增强（低难度 / 低价值）

- **Excel 页签并行写入**：报告生成时每个页签独立写入，可考虑并行加速
