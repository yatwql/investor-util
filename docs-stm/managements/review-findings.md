# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-09（D-11 全景复查 + 新增 8 项）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|
| 2026-07-08 | D-9 审查：代码健康检查（R-180~R-187） | 新增 4 项，R-180/R-184/R-185/R-186 已修复 |
| 2026-07-08 | v0.3.1 conftest 增强 + config.py 拆包 + 动态年份 | R-185/R-186 已修复，config 文档同步 |
| 2026-07-08 | D-8b 全面审查：代码质量/并发安全/工程化 | 已完成（全部修复） |
| 2026-07-08 | D-8c 审查：v0.3.0 代码健康度检查（R-177~R-183） | 已完成（全部修复） |
| 2026-07-09 | **D-10 审查：数据降级重构 6 维复盘（Step A~E）** | 新增 4 项待修复 + 2 立即修复 |
| 2026-07-09 | **D-11 全景复查：文档老化/测试正确性/代码膨胀/依赖风险** | 新增 3 项已修复（R-194~R-196）+ 5 项待优化（R-197~R-201） |

> **v0.1.x ~ v0.2.52 早期审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.1.x.md](../archive/archived_review-findings.0.1.x.md)。
> 涵盖：初始全量审计、P3 现代化、场景审计、第二/三波深度审计、R-131~R-147、T-001~T-003 等 13 条。
>
> **v0.2.52 ~ v0.2.91 审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.2.x.md](../archive/archived_review-findings.0.2.x.md)。
> 涵盖：R-149~R-159、C 迭代文档审核、D-7a/D-8 实施复盘、D-8 设计复盘 等 8 条。

---

## 待修复问题

### 🔴 高优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-178 | **`html_writer.py` 995 行严重超重**：导入 20+ 模块，混合 HTML 构建/数据准备/模板渲染/文件写入 | `report/html_writer.py` | 已添加文件导览 TOC，拆分暂缓，待某区段需大改时顺手拆出 |
| R-197 | **`market_value.py` 711 行持续增长**：第 3 大源文件，混合核心计算（`_compute_detail_row`）与 Excel 写入（`_write_market_value_sheet`）两重职责，随溢价率、空行情、策略选择器等新功能持续膨胀 | `report/market_value.py` | 可拆为 `market_value.py`（计算）+ `market_value_write.py`（写入）|

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-187 | **TUI Windows 平台 12 个测试跳过**：`termios`/`tty` 为 Linux 特有模块，Windows 上 `_get_key_linux()` 已加 try/except 保护 | `tui.py` + `test_tui_edge.py` | 功能降级但无错误，可考虑 CI 加 Windows runner |
| R-198 | **LLM 模块两巨头膨胀**：`generators.py`（750 行，第 2 大）+ `api.py`（702 行，第 4 大），如新增环比分析等 LLM 模块建议先横向拆分 | `llm/generators.py` + `llm/api.py` | `generators.py` 可拆出 `generators_news.py`；`api.py` 可按 provider 拆为 `api_claude.py`/`api_openai.py` |
| R-199 | **akshare 依赖老化风险**：`requirements.txt` 未锁定 akshare 版本，pytest 收集期已有 `FutureWarning`（DataFrame concat 行为变更），大版本升级可能引入兼容问题 | `requirements.txt` | 建议锁定 `akshare>=1.16,<2.0` 或类似区间 |
| R-200 | **verify 模式 ~5min 耗时**：场景/集成测试单线程运行，llm 场景 mock 串行调度可能为瓶颈 | `scripts/test_runner.py` | 可分析瓶颈后对 verify 模式引入增量运行策略 |
| R-201 | **HTML 打印预览缺少浏览器渲染集成测试**：当前仅 9 项 UT 覆盖 CSS `@media print` 规则，无 Playwright 快照对比确保打印输出视觉正确 | `test_html_template.py` | Playwright 快照测试，但跨系统工具优先级低 |

### ✅ 近期已修复

| # | 问题 | 修复说明 |
|:-:|:-----|:---------|
| R-189 | **market_value.py `_fetch_cached_only()` → 公开 `fetch_cached_only()`**：前导下划线改为公共方法名，消除模块边界泄漏；market_value 中改为 `registry.fetch_cached_only(...)` | 2026-07-09 修复 |
| R-190 | **哨兵 `_TRANSPORT_FAILURE` 统一至 provider_registry.py**：chain.py 删除局部定义，改为 import 共享；添加 `noqa: PLC2701` 注释标记跨模块 sentinel 共享的合理性 | 2026-07-09 修复 |
| R-191 | **`test_eviction_order` 修复 + 新增覆盖率**：写入 2005 条（>阈值 2000）实际触发淘汰验证；新增 `TestFetchOrCached`（3 项：LIVE_FETCH / CACHE_ONLY / fetch_fn 返回 None）和 `TestFetchCachedOnly`（2 项：session 命中 / 全 miss） | 2026-07-09 修复 |
| R-188 | **eastmoney_industry.py 局部熔断器迁移至 DataSourceRegistry**：6 个全局熔断变量 + 2 个辅助函数删除，_make_push2_request 统一使用 registry 的 is_circuit_broken/record_failure/record_success API | 2026-07-09 修复 |
| R-203 | **`register_default_chains()` 未在生产环境调用（P0）**：`DataSourceRegistry.register_default_chains()` 仅在测试中运行，导致 `get_chain()` 始终返回空，CACHE_ONLY 降级失效。修复：`chain.py` 末尾添加模块导入时自动注册 | 2026-07-09 修复 |
| M-004 | **tencent_style 隐式自注册 → 显式注册**：`record_failure("tencent_style")` 隐式创建 tier=4 最低优先级注册。修复：`fund_style_analysis.py` 模块级新增 `register_provider("tencent_style", tier=4, timeout=15.0)` | 2026-07-09 修复 |
| R-185 | **预测年份硬编码 → 动态计算**：穿透表列名「预测EPS(XXXXE)」从 `datetime.now().year` 获取当前年份，跨年自动更新 | 2026-07-08 修复 |
| R-186 | **定价双源消除 — constants.py 为单一来源**：`llm_settings.json` 模板移除型号示例，改为覆盖说明 | 2026-07-08 修复 |
| R-180 | **`type: ignore` 累计 22 处 → 4 处**：系统性清理 13 个文件，剩余 4 处为 `tui.py` 平台特定，属合理保留 | 2026-07-08 修复 |
| R-179 | **`config.py` 817 行 → `config/` 子包**：拆为 `_defaults.py` / `_comments.py` / `_core.py`，原文件删除 | 2026-07-08 修复 |
| R-184 | **`_get_industry_avg_pe()` 空实现 → 完整实现**：接入 push2 API 三级降级（push2→Tencent→代码前缀），10 项测试覆盖 | 2026-07-08 修复 |
| R-192 | **verify 测试 3 项 price_type 断言未同步**：Step B 将 `_compute_detail_row` 无行情分支的 `price_type` 从 `"--"` 改为 `"暂无行情"`，但 2 个场景测试共 3 处未同步，导致 verify 失败 | 2026-07-09 修复 |
| R-193 | **unit 测试 3 项 _check_network_available 断言未同步**：`_check_network_available` 文案变更后 TestCheckNetworkAvailablePrint 中 3 项测试未同步，导致 unit 失败 | 2026-07-09 修复 |
| R-194 | **`technical.md` push2 熔断"待迁移"标记过时**：`eastmoney_industry.py` 实际已于 R-188 迁移至 DataSourceRegistry，但 `technical.md` 的"实现位置"对比表仍标注"模块级全局变量（待迁移）"，与代码实况不符 | 2026-07-09 修复 |
| R-195 | **版本号一致性检查脚本 + pyproject.toml 修复**：`pyproject.toml` version 自 v0.3.0 后未更新（落后 4 个版本），新增 `scripts/check-version-consistency.py` 以 `constants.py` 为单一事实源自动校验 9 处版本号，`CLAUDE.md` 发布流程同步更新 | 2026-07-09 修复 |
| R-196 | **溢价率占位符 → 真实计算 + 3 项 🟡→✅**：`market_value.py` 新增 `_compute_premium()` 对 QDII 基金实现 `(现价-参考净值)/参考净值` 计算；`testplan.md` §2 数据正确性表 3 项 🟡 覆盖完成（溢价率/非 T 日本日盈亏/穿透占比归一化），data 标记 65→69 项 | 2026-07-09 修复 |
