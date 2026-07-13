# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-13

---

## 审查记录（摘要）

> 早期审计记录已归档：详见 [`archived_review-findings.0.1.x.md`](../archive/archived_review-findings.0.1.x.md) · [`archived_review-findings.0.2.x.md`](../archive/archived_review-findings.0.2.x.md) · [`archived_review-findings.0.3.x.md`](../archive/archived_review-findings.0.3.x.md)。

---

## P0（阻止级别，必须立即修复）

### market_value.py:129 + category.py:99 — 00 代码 OTC 基金被永久误分类为"A股"

**说明**：`classify_holdings()`（market_value.py:129）和 `_categorize_holding()`（category.py:99）中使用 `is_a_share_code(code)` 将 00 开头的 OTC 基金（如 002943 广发多因子）归类为"场内股票"/"股票-A股"。与 `price.py` 有降级回退不同，分类判断是静态的——走错就没有纠正机会。

**根因**：`code_utils.py` 的 `is_a_share_code()` 只做前缀匹配，00 同时是深市主板股票和 OTC 基金代码的前缀，单靠代码无法区分。

**修复方案**：在 `code_utils.py` 新增 `is_otc_fund_by_name(name, code)` 函数，综合利用名称关键词（混合/纯债/短债/债券/货币/指数/联接等）判断 00 代码是否为 OTC 基金。业务模块在 `is_a_share_code()` 前先调用此函数优先判定。

**状态**：已完成

---

## P1（高优先级）

### news_correlation.py:437,453 — 静默吞异常（except Exception: pass）

**说明**：`get_last_source_status()` 调用被 `except Exception: pass` 包裹，且无任何日志记录（`logger.warning` 等）。若该方法抛出异常，用户完全无感知。

**修复方案**：补充 `logger.warning` 日志记录。

**状态**：已完成

---

## P2（中优先级）

### docs-stm/manuals/datasource-and-folders.md — 缺少 schemas/ 目录

**说明**：`src/python/schemas/`（含 `__init__.py` + `history.py` 数据模型）在文档目录树中完全缺失。

**修复方案**：补充 `schemas/` 目录树条目。

**状态**：已完成

---

## P3（低优先级，待排期）

### test_fetcher_price.py 未覆盖 00 代码降级逻辑

**说明**：新增的 00 代码降级转场外基金链路逻辑无对应测试用例。

**修复方案**：mock tencent + sina 返回 None，验证降级调用 eastmoney。

**状态**：待排期

### portfolio_history.py 无独立单元测试

**说明**：`portfolio_history.py` 整个文件无单元测试，新增的 00 降级逻辑也未覆盖。

**修复方案**：创建 `test_portfolio_history.py`，mock K 线失败→验证降级净值的完整流程。

**状态**：待排期

### penetration.py:113 — 穿透分类中 00 代码误判

**说明**：`_classify_fund_type()` 对 00 基金返回 STOCK，影响穿透模块中的分类标签。严重度较低——穿透核心是拆解基金底层资产，持有物本身的分类标签影响有限。

**修复方案**：同 P0 思路，复用 `is_otc_fund_by_name()` 优先判定。

**状态**：待排期

### excel_b_series.py 未复用 session_cache 重复获取基金持仓

**说明**：B 系列 3 个模块各自独立拉取基金持仓数据，未使用 `html_renderers.py` 中已实现的 `session_cache` 共享模式。

**修复方案**：复用 `registry.session_cache_get/set("fund_hold", code)`。

**状态**：待排期
