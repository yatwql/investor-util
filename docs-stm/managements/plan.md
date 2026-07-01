# 个人投资分析报告生成小助手 — 实现计划

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.49 — 待办区清空，规划 D~H 新方向）

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

### A2. 大函数拆分（低难度 / 中价值）✅ 已完成（v0.2.48 / v0.2.49）

- **R-020~R-023 ✅** `generate_excel_report`/`generate_all_llm`/`write_llm_usage_sheet`/`compute_penetration_top10`
- **R-026 ✅** `write_fund_performance_sheet` 164→55 行
- **R-027 ✅** `write_summary_sheet` 163→43 行
- **R-028 ✅** `build_news_data` 159→60 行
- **R-029 ✅** `tiantian.py` 三大函数全部分解
- **R-030 ✅** `skeleton.py` 两大函数拆分

---

### 待实现方向

### B. 基金持仓专属分析（中难度 / 高价值）

- **基金经理变更监控**：检测主动基金近 3 月内基金经理是否变更（已有天天基金 API）
- **持仓重合度矩阵**：计算多只基金间的 TOP10 持仓重叠度，避免买同一堆股票

### C. 历史表现跟踪（中难度 / 中价值）

- **报告对比**：将本次报告的关键指标（市值/盈亏/仓位）与上次对比，输出变化摘要
- **回撤监控**：从历史缓存中提取持仓的连续回撤曲线

### D. 测试覆盖补全（二期）（低难度 / 中价值）

补齐当前测试缺口中的高优先级模块：

- **P0 `http_client.py` 单元测试**：HTTP 客户端工厂，所有 provider 共用，覆盖 `make_http_client` 配置合并/超时/SSL_VERIFY 环境变量
- **P0 `market_hours.py` 单元测试**：交易时段判断核心，覆盖 3 层策略链（配置/API/回退）、午餐排除、盘前/盘中/盘后判定
- **P1 `llm/circuit_breaker.py` 单元测试**：熔断器模块，覆盖 `_cb_endpoint`/`_cb_record_failure`/`_cb_is_open`/冷却期自动恢复
- **P1 `llm/fingerprint.py` 单元测试**：缓存指纹计算，覆盖 `_build_llm_fingerprint`/`_compute_fingerprint`/`_get_cache_ttl_llm`
- **P1 `llm/pricing.py` 单元测试**：定价估算，覆盖 `_estimate_cost`/`_reload_pricing`/`_PRICING_MERGED` 合并逻辑
- **P1 `llm/markdown.py` 单元测试**：Markdown→HTML 转换覆盖
- **P2 `providers/eastmoney_news.py`/`sina_news.py`/`wallstreetcn_news.py` 单元测试**：各新闻 provider 独立覆盖

### E. 大函数拆分（二期）（低难度 / 中价值）

当前仍存 8 个 >100 行函数待拆分：

- **R-033** `llm/generators.py:enhance_news_correlation`（128 行）— 新闻 LLM 分析核心
- **R-034** `report/category.py:write_category_sheet`（124 行）— 分类汇总表写入
- **R-035** `report/news_correlation.py:_build_keyword_lookup`（119 行）— 关键词查找构建
- **R-036** `llm/api.py:_call_llm_with_retry`（114 行）— LLM 调用重试核心
- **R-037** `report/news_correlation.py:write_news_sheet`（113 行）— 新闻工作表写入
- **R-038** `report/html_writer.py:_build_perf_data`（107 行）— HTML 性能数据构建
- **R-039** `providers/news_aggregator.py:aggregate_news`（106 行）— 多源新闻聚合
- **R-040** `report/penetration.py:write_penetration_sheet`（105 行）— 穿透分析表写入

### F. LLM 分析增强

- **环比分析**：对比历史报告摘要，说明组合变化趋势

### G. `llm/__init__.py` 过度导出治理（低难度 / 低价值）

`llm/__init__.py` 从 6 个子模块 re-export 了约 60 个私有符号（`_` 前缀），既是公共 API 又暴露内部实现。建议：

- 仅保留公有函数/类的导出
- 移除不必要的 `_` 前缀私有符号导出
- 各模块直接引用子模块路径

### H. 配置/依赖治理（低难度 / 低价值）

- **`requirements.txt` → `pyproject.toml` 迁移**：增加版本锁定和元数据描述
- **`config.json` cache_ttl 条目自动化**：从 registry 自动派生，减少手动同步遗漏
