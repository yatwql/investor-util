# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-04（v0.2.83 — 版本号同步 + faq 文档修正 + autoescape 技术债务修复）

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

所有已完成迭代（A/A2/A3/A4/A5/J/K/L/P/N/Q/R/M/T/S/V/U/W/X/Y1/Y2/Y3/Y4/Y5/Y6/Z1/Z2/Z3/Z4）的详细变更记录见 [`docs-stm/managements/changelog.md`](changelog.md).

---

### 当前迭代

### [P2-2] A5. 测试运行时可扩展性优化（review-findings R-152，低难度 / 中价值）

**问题**：`unit` 模式已达 1998 项/~25min，`verify` 模式 839 项/~12min，随测试增长趋势不乐观。

**方案**：四管齐下 — 并行执行（pytest-xdist）+ 超大文件拆分 + 增量测试（git-aware）+ 新增快速子模式。

**详细设计**：[`docs-stm/plan/A5-test-runtime-optimization.md`](../plan/A5-test-runtime-optimization.md)

---

### 待实现方向（按风险收益比排序）

> 注：字母编号跳跃出于历史分配——已完成迭代占用了相应字母（详见上方 ✅ 已完成迭代），剩余字母保留给此前已规划但优先级较低的后续迭代。

---

### [P0 — 待评审] B. 基金持仓专属分析（中难度 / 高价值）

> 详细设计已输出：[B1-fund-deep-analysis.md](../plan/B1-fund-deep-analysis.md)
> 包含：B0 预研 + 5 Phase / 19 原子步 / 1 新增 fetcher + 4 报告模块 + 1 验证步 / ~115 项测试
> v2 修复：缓存指纹缺陷/首次运行体验/编号体系/性能估算/TUI 菜单设计/HTML 模板优化/数据源预研前置

| 模块 | Phase | 状态 |
|:-----|:------|:----:|
| 基金经理变更监控 | B2 | 📋 待实施 |
| 持仓重合度矩阵 | B3 | 📋 待实施 |
| 持仓集中度监控 | B4 | 📋 待实施 |
| 基金风格漂移检测 | B5 | 📋 待实施（需预研数据源）|



### [P2-2] Y. Edge Case 纵深覆盖增补（四期）（低难度 / 中价值）

Y 系列（Y1-Y6）已全部完成，共 ~198 项 edge 测试覆盖了零值/空集/时区/缓存/API 异常/数据质量/文件系统/数值计算/安全纵深/配置环境等维度。

详细变更见 changelog.md Unreleased 章节。

---

Z 系列（Z1-Z4）已全部完成：
- Z1（特殊品种 S21-S28，27 项）
- Z2（操作行为 S29-S33，15 项）
- Z3（持仓质量 S0a-S0d，16 项）
- Z4（时间补充 T17-T21，21 项）

详细变更见 changelog.md Unreleased 章节。


### [P4] F. LLM 分析增强（低难度 / 中价值）

- **环比分析**：对比历史报告摘要，说明组合变化趋势
- **报告对比**：将本次报告的关键指标（市值/盈亏/仓位）与上次对比，输出变化摘要
- **回撤监控**：从历史缓存中提取持仓的连续回撤曲线

---

### [P5] O. 工程化增强（低难度 / 低价值）

- **CI/CD 集成**：添加 GitHub Actions 自动化流水线，每次 Push 自动运行 `pytest`
- **Excel 页签并行写入**：报告生成时每个页签独立写入，可考虑并行加速
