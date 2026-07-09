# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-09（D-10 审查：数据降级重构 6 维复盘 + 归档清理）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|
| 2026-07-08 | D-9 审查：代码健康检查（R-180~R-187） | 新增 4 项，R-180/R-184/R-185/R-186 已修复 |
| 2026-07-08 | v0.3.1 conftest 增强 + config.py 拆包 + 动态年份 | R-185/R-186 已修复，config 文档同步 |
| 2026-07-08 | D-8b 全面审查：代码质量/并发安全/工程化 | 已完成（全部修复） |
| 2026-07-08 | D-8c 审查：v0.3.0 代码健康度检查（R-177~R-183） | 已完成（全部修复） |
| 2026-07-09 | **D-10 审查：数据降级重构 6 维复盘（Step A~E）** | 新增 4 项待修复 + 2 立即修复 |

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
| R-178 | **`html_writer.py` 958 行严重超重**：导入 20+ 模块，混合 HTML 构建/数据准备/模板渲染/文件写入 | `report/html_writer.py` | 已添加文件导览 TOC（L44-L78），拆分暂缓，待某区段需大改时顺手拆出 |

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-187 | **TUI Windows 平台 12 个测试跳过**：`termios`/`tty` 为 Linux 特有模块，Windows 上 `_get_key_linux()` 已加 try/except 保护 | `tui.py` + `test_tui_edge.py` | 功能降级但无错误，可考虑 CI 加 Windows runner |
| R-189 | **market_value.py 调用 DataSourceRegistry 私有方法 `_fetch_cached_only()`**：前导下划线表明实现细节，非公共 API，模块边界泄漏 | `report/market_value.py` | 建议改为公共方法或改用 `fetch_or_cached` |
| R-190 | **哨兵 `_TRANSPORT_FAILURE` 重复定义**：`provider_registry.py` 和 `chain.py` 各有一套，后者 unused | `provider_registry.py` + `chain.py` | 应统一至一处 |
| R-191 | **`test_eviction_order` 未实际触发淘汰**：写入 100 条/阈值 2000，断言永远为真，不能验证淘汰逻辑 | `test_provider_registry.py` | `fetch_or_cached` 和 `_fetch_cached_only` 无单元覆盖 |

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-189 | **market_value.py 调用 DataSourceRegistry 私有方法 `_fetch_cached_only()`**：前导下划线表明实现细节，非公共 API，模块边界泄漏 | `report/market_value.py` | 建议改为公共方法或改用 `fetch_or_cached` |
| R-190 | **哨兵 `_TRANSPORT_FAILURE` 重复定义**：`provider_registry.py` 和 `chain.py` 各有一套，后者 unused | `provider_registry.py` + `chain.py` | 应统一至一处 |
| R-191 | **`test_eviction_order` 未实际触发淘汰**：写入 100 条/阈值 2000，断言永远为真，不能验证淘汰逻辑 | `test_provider_registry.py` | `fetch_or_cached` 和 `_fetch_cached_only` 无单元覆盖 |

### ✅ 近期已修复

| # | 问题 | 修复说明 |
|:-:|:-----|:---------|
| R-188 | **eastmoney_industry.py 局部熔断器迁移至 DataSourceRegistry**：6 个全局熔断变量 + 2 个辅助函数删除，_make_push2_request 统一使用 registry 的 is_circuit_broken/record_failure/record_success API | 2026-07-09 修复 |
| R-203 | **`register_default_chains()` 未在生产环境调用（P0）**：`DataSourceRegistry.register_default_chains()` 仅在测试中运行，导致 `get_chain()` 始终返回空，CACHE_ONLY 降级失效。修复：`chain.py` 末尾添加模块导入时自动注册 | 2026-07-09 修复 |
| M-004 | **tencent_style 隐式自注册 → 显式注册**：`record_failure("tencent_style")` 隐式创建 tier=4 最低优先级注册。修复：`fund_style_analysis.py` 模块级新增 `register_provider("tencent_style", tier=4, timeout=15.0)` | 2026-07-09 修复 |
| R-185 | **预测年份硬编码 → 动态计算**：穿透表列名「预测EPS(XXXXE)」从 `datetime.now().year` 获取当前年份，跨年自动更新 | 2026-07-08 修复 |
| R-186 | **定价双源消除 — constants.py 为单一来源**：`llm_settings.json` 模板移除型号示例，改为覆盖说明 | 2026-07-08 修复 |
| R-180 | **`type: ignore` 累计 22 处 → 4 处**：系统性清理 13 个文件，剩余 4 处为 `tui.py` 平台特定，属合理保留 | 2026-07-08 修复 |
| R-179 | **`config.py` 817 行 → `config/` 子包**：拆为 `_defaults.py` / `_comments.py` / `_core.py`，原文件删除 | 2026-07-08 修复 |
| R-184 | **`_get_industry_avg_pe()` 空实现 → 完整实现**：接入 push2 API 三级降级（push2→Tencent→代码前缀），10 项测试覆盖 | 2026-07-08 修复 |
