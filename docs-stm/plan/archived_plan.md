# 投资分析报告小工具 — 历史迭代记录

> 归档时间：2026-06-28
> 原始文件：`docs-stm/managements/plan.md`
> 归档原因：Iter 2.0~5.3 已完成，保留历史迭代详情供回溯参考，plan.md 已精简为当前架构决策。
>
> **v0.1.x（Iter 1.1~1.5）已另档保存**：详见 [docs-stm/archive/archived_plan.0.1.x.md](../archive/archived_plan.0.1.x.md)。

---

## Iter 2 — 分类汇总 + 资产穿透 TOP10 + 基金业绩分析 ✅ 已完成

**Goal**：补全剩余 3 个 Excel 页签。

**Files**：
- `src/report/category.py` — 分类汇总
- `src/report/penetration.py` — 资产穿透 TOP10
- `src/report/fund_performance.py` — 基金业绩分析

---

## Iter 3.1 — HTML 报告引擎基础

**Goal**：搭建 HTML 报告生成引擎 + Jinja2 模板框架。

**Files**：
- `src/report/html_writer.py` — HTML 生成引擎
- `src/tmpl/report_template.html` — Jinja2 模板文件
- `requirements.txt` — 增加 Jinja2 依赖

---

## Iter 3.2 — 财经新闻热点与持仓关联分析模块 ✅ 已完成

**Goal**：实现财经新闻热点与持仓关联分析模块，在 HTML 报告中新增第 6 个模块。

**Files**：
- `src/providers/sina_news.py` — 新浪新闻 API + 关键词关联
- `src/report/news_correlation.py` — 财经新闻热点与持仓关联分析（Excel + HTML）
- `src/tmpl/report_template.html` — 更新模板，新增新闻模块区域

---

## Iter 3.3 — 模板占位模块 + 打磨

**Goal**：补齐全球政经局势/智囊团深度复盘 的模板占位，缓存管理，文件选择器增强，异常处理增强。

**Files**：
- `src/tmpl/report_template.html` — 更新模板，新增两个占位模块区域
- `src/report/html_writer.py` — 传递 `llm_enabled=False` 标记
- `src/report/penetration.py` — 增加板块分类
- `src/cache.py` — 新增 `cleanup_expired()` / `get_cache_stats()` / `get_cache_dir()`
- `src/reader.py` — 新增 `get_xlsx_info()` 文件信息查询
- `src/main.py` — 新增菜单 [3][4]；文件选择器增强；错误友好提示
- `src/report/excel_writer.py` — `save_workbook` 增加 PermissionError 保护

---

## Iter 3.4 — LLM 智能分析接入 ✅ 已完成

> **注：** 此迭代使用 `data/config/llm.json` 单文件存储 LLM 配置。v0.2.15 已拆分为双文件。

**Goal**：替换模板占位为 LLM 生成内容。

**Files**：
- `src/llm_client.py` —（新建）LLM API 客户端
- `src/config.py` — 新增 `get_llm_config()`
- `src/report/html_writer.py` — `enable_llm` 参数
- `src/tmpl/report_template.html` — 条件渲染 LLM 区域
- `data/config/config.json` — 增加 `llm_config_file` 字段

---

## Iter 3.5 — LLM 全局优化 ✅ 已完成

**Goal**：LLM 调用性能优化、System Prompt 外部可配置、智囊团升级为5位专家、提示词紧凑化。

**Files**：
- `src/llm_client.py` — `generate_all_llm()` 并行批处理、全局 `_HTTP_POOL` 连接池、智囊团 System Prompt
- `src/config.py` — LLM 配置内存缓存
- `src/main.py` — 穿透TOP10统一计算复用

---

## Iter 3.6 — 全面性能优化与代码清理 ✅ 已完成

**Goal**：多维度性能优化（并行化、Token 压缩、缓存增强）、死代码全面清理。

**Files**（修改）：
- `src/main.py` — 菜单 [1]/[2] ThreadPoolExecutor 并行化；`_busy` 防重入
- `src/llm_client.py` — Prompt 压缩、Token 追踪、超时提升
- `src/report/llm_content.py` — 参数精简
- `src/cache.py` — 死代码移除
- `src/config.py` — mtime 缓存 + 配置校验
- `src/providers/news_aggregator.py` — 新闻 15 分钟缓存 + 并行获取
- `src/providers/sina_news.py` — 移除死函数
- `src/providers/tiantian.py` — 移除死函数

---

## Iter 3.7 — 类型与空安全审计 ✅ 已完成

**Goal**：全量代码类型一致性审计 + API JSON null 防御性编程。

**Files**：
- `src/report/html_writer.py` — a_indices/us_indices dict 修复
- `src/report/fund_performance.py` — API null 兜底
- `src/report/summary.py` — dict 类型保留

---

## Iter 4.1 — 测试覆盖补全一期（A）✅ 已完成（v0.2.46 / v0.2.48 / v0.2.49）

- **R-015 ✅** `llm/api.py` 44 项、`excel_generator.py` 15 项
- **R-024 ✅** `test_handlers.py` 23 项
- **R-031 ✅** `test_tiantian.py` 39 项
- **R-032 ✅** `test_skeleton.py` 9 项

## Iter 4.2 — 大函数拆分一期（A2）✅ 已完成（v0.2.48 / v0.2.49 / v0.2.50）

- **R-020~R-023 ✅** `generate_excel_report`/`generate_all_llm`/`write_llm_usage_sheet`/`compute_penetration_top10`
- **R-026 ✅** `write_fund_performance_sheet` 164→55 行
- **R-027 ✅** `write_summary_sheet` 163→43 行
- **R-028 ✅** `build_news_data` 159→60 行
- **R-029 ✅** `tiantian.py` 三大函数全部分解
- **R-030 ✅** `skeleton.py` 两大函数拆分
- **R-033~R-042 ✅** 全部 8 个大函数（>100行）拆分完成

## Iter 4.3 — 测试覆盖补全二期（A3）✅ 已完成（v0.2.50 / v0.2.51）

- **R-033/R-034 ✅** `http_client.py`（17 项）/ `market_hours.py`（41 项）测试
- **R-043~R-046 ✅** circuit_breaker/pricing/markdown 已有充分覆盖无需加测
- **R-044 ✅** `fingerprint.py` 新增 16 项测试
- **R-047~R-049 ✅** 三大新闻 provider 新增 50 项测试

## Iter 4.4 — 代码治理（A4）✅ 已完成（v0.2.51）

- **R-050 ✅** `llm/__init__.py` 过度导出治理：移除 ~60 个私有符号 re-export
- **`llm/skeleton.py` 全局 max_tokens 回退清理**：移除旧版配置全局 `max_tokens` 兜底路径
- **`config.py` 键名兼容去重**：移除 `_LLM_KEY_OVERLAP_KEYS` 跨文件键名互通机制

## Iter 4.5 — 文件拆分 + 配置治理（A5）✅ 已完成（v0.2.51）

- **R-051 ✅** `report/html_writer.py`（792→617 行）：提取 4 个构建函数至 `html_builders.py`
- **R-052 ✅** `report/penetration.py`（715→530 行）：提取 `write_penetration_sheet` 等 6 个辅助函数至 `penetration_sheet.py`
- **R-053 ✅** `requirements.txt` 版本锁定：从 `>=` 改为 `==`
- **R-054 ✅** `config.py:validate_config()` 新增 `early_warning` 配置段校验
- **R-055 ✅** `news_aggregator.py` 清理 `_FALLBACK_ENABLED` 死路径

## Iter 5.1 — 大函数治理二期（J）✅ 已完成（v0.2.52）

将 15 个 >75 行的函数进一步拆分（单元可测试化）：

| 行数 | 函数 | 位置 |
|:----:|------|------|
| 123 | `validate_config` | `config.py` | ✅ 已完成 |
| 99 | `_compute_sentiment_alerts` | `report/early_warning.py` | ✅ 已完成 |
| 96 | `_markdown_to_html` | `llm/markdown.py` | ✅ 已完成 |
| 94 | `_call_llm_with_retry` | `llm/api.py` | ✅ 已完成 |
| 90 | `_fetch_with_fallback` | `fetcher/chain.py` | ✅ 已完成 |
| 86 | `build_holding_keywords` | `providers/news_keywords.py` | ✅ 已完成 |
| 85 | `_call_claude` | `llm/api.py` | ✅ 已完成 |
| 82 | `fetch_industry_and_concepts` | `providers/eastmoney_industry.py` | ✅ 已完成 |
| 79 | `write_market_value_sheet` | `report/market_value.py` | ✅ 已完成 |
| 78 | `_generate_details` | `report/market_value.py` | ✅ 已完成 |
| 78 | `get_dividend_data` | `providers/akshare_extras.py` | ✅ 已完成 |
| 78 | `_build_penetration_deep_prompt` | `llm/prompts.py` | ✅ 已完成 |
| 77 | `_generate_llm_module` | `llm/skeleton.py` | ✅ 已完成 |
| 77 | `cleanup_expired` | `cache.py` | ✅ 已完成 |
| 76 | `_render_llm_module_info` | `report/html_writer.py` | ✅ 已完成 |

## Iter 5.2 — 测试覆盖补全三期（K）✅ 已完成（v0.2.52）

- 9 个模块全部新增专用测试文件（R-071~R-079），共 140 项测试，全量 1535 passed / 11 skipped

## Iter 5.3 — 代码现代化（L）✅ 已完成（v0.2.52）

- **旧式 typing 泛型 → 内置泛型**：13 个文件的 `List`/`Dict`/`Optional`/`Tuple` → `list`/`dict`/`X | None`/`tuple`
- **`.format()` → f-string**：3 处全部转换
- **pyproject.toml 同步**：版本/依赖精确锁定与 requirements.txt 一致
