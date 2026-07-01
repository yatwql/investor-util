# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.51 — P2 测试覆盖全部完成 + 配置审查、兼容代码清理）

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

## 历史迭代记录

Iter 1.1~1.5（项目骨架至打磨验证）、Iter 2（分类汇总/穿透/基金业绩）、Iter 3.1~3.7（HTML/新闻/LLM/优化/类型审计）的详细记录已归档至 [`docs-stm/plan/archived_plan.md`](../plan/archived_plan.md)。以上所有迭代均已完成并合并入 `main` 分支。

---

## 下一步迭代计划（待择机启动）

以下增强方向经评估对个人持仓分析有较高价值，按优先级排序：

### ✅ 已完成迭代

### A. 测试覆盖补全（低难度 / 中价值）✅ 已完成（v0.2.46 / v0.2.48 / v0.2.49）

- **R-015 ✅** `llm/api.py` 44 项、`excel_generator.py` 15 项
- **R-024 ✅** `test_handlers.py` 23 项
- **R-031 ✅** `test_tiantian.py` 39 项
- **R-032 ✅** `test_skeleton.py` 9 项

### A2. 大函数拆分（低难度 / 中价值）✅ 已完成（v0.2.48 / v0.2.49 / v0.2.50）

- **R-020~R-023 ✅** `generate_excel_report`/`generate_all_llm`/`write_llm_usage_sheet`/`compute_penetration_top10`
- **R-026 ✅** `write_fund_performance_sheet` 164→55 行
- **R-027 ✅** `write_summary_sheet` 163→43 行
- **R-028 ✅** `build_news_data` 159→60 行
- **R-029 ✅** `tiantian.py` 三大函数全部分解
- **R-030 ✅** `skeleton.py` 两大函数拆分
- **R-033~R-042 ✅** 全部 8 个大函数（>100行）拆分完成

### A3. 测试覆盖补全（二期）（低难度 / 中价值）✅ 已完成（v0.2.50 / v0.2.51）

- **R-033/R-034 ✅** `http_client.py`（17 项）/ `market_hours.py`（41 项）测试
- **R-043~R-046 ✅** circuit_breaker/pricing/markdown 已有充分覆盖无需加测
- **R-044 ✅** `fingerprint.py` 新增 16 项测试
- **R-047~R-049 ✅** 三大新闻 provider 新增 50 项测试

### A4. 代码治理完成项（低难度 / 低价值）✅ 已完成（v0.2.51）

- **R-050 ✅** `llm/__init__.py` 过度导出治理：移除 ~60 个私有符号 re-export，仅保留公有接口
- **`llm/skeleton.py` 全局 max_tokens 回退清理**：移除旧版配置全局 `max_tokens` 兜底路径
- **`config.py` 键名兼容去重**：移除 `_LLM_KEY_OVERLAP_KEYS` 跨文件键名互通机制

---

### 待实现方向

### B. 基金持仓专属分析（中难度 / 高价值）

- **基金经理变更监控**：检测主动基金近 3 月内基金经理是否变更（已有天天基金 API）
- **持仓重合度矩阵**：计算多只基金间的 TOP10 持仓重叠度，避免买同一堆股票

### C. 历史表现跟踪（中难度 / 中价值）

- **报告对比**：将本次报告的关键指标（市值/盈亏/仓位）与上次对比，输出变化摘要
- **回撤监控**：从历史缓存中提取持仓的连续回撤曲线

### F. LLM 分析增强

- **环比分析**：对比历史报告摘要，说明组合变化趋势

### H. 代码治理（低难度 / 中价值）

#### R-051 `report/html_writer.py` 文件偏大

792 行，虽已拆分函数，但文件整体仍可考虑按章节拆分（HTML 头部/LLM 章节/历史净值/穿透数据分拆为独立模块）。

#### R-052 `report/penetration.py` 文件偏大

715 行，穿透逻辑与 Excel 写入混合，建议将纯计算逻辑（行业分级/基金穿透/前十权重）与工作表写入解耦。

#### R-053 `requirements.txt` 缺少锁定版本

仅有 5 个顶层依赖（httpx, openpyxl, jinja2, akshare, lxml），建议使用 `pip freeze` 导出锁定文件或迁移至 `pyproject.toml`。

### I. 配置治理（低难度 / 低价值）

- **`early_warning` 配置段添加 `validate_config()` 校验**：`sector_alert_threshold_warning`/`danger`/`sentiment_top_n` 当前无类型/范围校验
- **`_FALLBACK_ENABLED` 死路径清理**：`news_aggregator.py` 的后备路径因 `get_config()` 总提供完整默认值而不可达
