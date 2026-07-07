# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-08（v0.2.90 — D 迭代数据降级分层治理完成）

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

所有已完成迭代（A/A2/A3/A4/A5/B/C/D/J/K/L/P/N/Q/R/M/T/S/V/U/W/X/Y1/Y2/Y3/Y4/Y5/Y6/Z1/Z2/Z3/Z4）的详细变更记录见 [`docs-stm/managements/changelog.md`](changelog.md)。

B 迭代（基金深度分析 4 模块：基金经理变更监控/持仓重合度矩阵/持仓集中度监控/基金风格分析）和 C 迭代（报告序号可配置）已完结，详见 changelog.md 及 `docs-stm/archive/c-iteration-design.md`、`docs-stm/archive/c-p1b-excel-title-number-fix.md`。

D 迭代（数据降级分层治理，Phase 0-3）已完结，详见设计文档 `docs-stm/archive/d-iteration-data-degradation-design.md` 及 changelog.md。核心产出：

- **T1/T2/T3/T4 分层模型**：按数据源稳定性四层分级，每层降级行为不同
- **`_data_status` 机制**：`DataStatusItem(available, tier, message)` 字典 + `STATUS_MESSAGES` 共享常量 + 层前缀（T2→⚠ / T3/T4→ℹ）
- **Excel 降级辅助**：`_write_placeholder()`（占位文本）和 `_write_data_status_foot()`（状态页脚）
- **HTML 降级渲染**：`render_data_status` Jinja2 宏 + `_safe_build_data_status()` 异常安全包装
- **新闻 source_status 追踪**：`get_last_source_status()` 全源失败→占位/部分失败→底部列表
- **akshare 分红/盈利预测降级**：`dividend_success` 布尔返回值 + 页脚状态摘要
- **全链路回归测试**：新增 5 个边缘测试文件覆盖全部降级路径

---

### 待实现方向（按风险收益比排序）

> 注：字母编号跳跃出于历史分配——已完成迭代占用了相应字母（详见上方 ✅ 已完成迭代），剩余字母保留给此前已规划但优先级较低的后续迭代。

---

### [P4] F. LLM 分析增强（低难度 / 中价值）

- **环比分析**：对比历史报告摘要，说明组合变化趋势
- **报告对比**：将本次报告的关键指标（市值/盈亏/仓位）与上次对比，输出变化摘要
- **回撤监控**：从历史缓存中提取持仓的连续回撤曲线

---

### [P5] O. 工程化增强（低难度 / 低价值）

- **CI/CD 集成**：添加 GitHub Actions 自动化流水线，每次 Push 自动运行 `pytest`
- **Excel 页签并行写入**：报告生成时每个页签独立写入，可考虑并行加速