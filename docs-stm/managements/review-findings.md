# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-10（新增 R-206、R-207 两项待修复；✅ 近期已修复 20 项清理归档）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|
| 2026-07-08 | D-9 审查：代码健康检查（R-180~R-187） | 新增 4 项，R-180/R-184/R-185/R-186 已修复 |
| 2026-07-08 | v0.3.1 conftest 增强 + config.py 拆包 + 动态年份 | R-185/R-186 已修复，config 文档同步 |
| 2026-07-08 | D-8b 全面审查：代码质量/并发安全/工程化 | 已完成（全部修复） |
| 2026-07-08 | D-8c 审查：v0.3.0 代码健康度检查（R-177~R-183） | 已完成（全部修复） |
| 2026-07-09 | **D-10 审查：数据降级重构 6 维复盘（Step A~E）** | 新增 4 项待修复 + 2 立即修复 |
| 2026-07-09 | **D-11 全景复查：文档老化/测试正确性/代码膨胀/依赖风险** | 新增 4 项已修复（R-194~R-197）+ 4 项待优化（R-198~R-201） |

> **v0.1.x ~ v0.2.52 早期审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.1.x.md](../archive/archived_review-findings.0.1.x.md)。
> 涵盖：初始全量审计、P3 现代化、场景审计、第二/三波深度审计、R-131~R-147、T-001~T-003 等 13 条。
>
> **v0.2.52 ~ v0.2.91 审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.2.x.md](../archive/archived_review-findings.0.2.x.md)。
> 涵盖：R-149~R-159、C 迭代文档审核、D-7a/D-8 实施复盘、D-8 设计复盘 等 8 条。

---

## 待修复问题

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-187 | **TUI Windows 平台 12 个测试跳过**：`termios`/`tty` 为 Linux 特有模块，Windows 上 `_get_key_linux()` 已加 try/except 保护 | `tui.py` + `test_tui_edge.py` | 功能降级但无错误，可考虑 CI 加 Windows runner |
| R-199 | **akshare 依赖老化风险**：`requirements.txt` 未锁定 akshare 版本，pytest 收集期已有 `FutureWarning`（DataFrame concat 行为变更），大版本升级可能引入兼容问题 | `requirements.txt` | 建议锁定 `akshare>=1.16,<2.0` 或类似区间 |
| R-201 | **HTML 打印预览缺少浏览器渲染集成测试**：当前仅 9 项 UT 覆盖 CSS `@media print` 规则，无 Playwright 快照对比确保打印输出视觉正确 | `test_html_template.py` | Playwright 快照测试，但跨系统工具优先级低 |
| R-206 | **excel_generator.py 拆分完成（692→98 行）**：按计划拆分出 7 个专业模块（module_loader/sheet_factory/market_data/content_sheets/news_warning/b_series/llm_usage）。_process_b_module 消除 3 份重复模板代码 | `report/excel_generator.py` | I-02~I-08 ✅，692→98 行（-86%） |
| R-207 | **summary.py 文件过大（617 行）**：20+ 个 `_write_*` 辅助函数混合同一文件，LLM 用量表格部分（`write_llm_usage_sheet`/`_write_llm_summary_section`/`_init_llm_usage_sheet`）已可独立成模块 | `report/summary.py` | 可参照 R-197 模式拆出 summary_llm_usage.py；但 LLM 用量属于变异较快的功能，拆分后仍需考虑后续兼容 |

### 🟢 低优先级

（当前无低优先级待修复问题）

### ✅ 近期已修复（已记录到 changelog.md）

> 以下所有项目已完整记录至 [`changelog.md`](./changelog.md)（v0.3.3 ~ v0.3.5），此处仅保留摘要索引，详细修复说明请查阅 changelog。
>
> v0.3.3：R-188~R-193、R-203、M-004（eastmoney_industry 熔断器迁移/assert 同步/自动注册等 8 项）
> v0.3.4：R-194~R-196（technical.md 标记同步/版本一致性检查/溢价率真实计算 3 项）
> v0.3.5（R-197）：market_value.py 拆分为计算层 + Excel 写入层（market_value_sheet.py）
> **v0.3.5（R-198）**：LLM 模块横向拆分（generators.py → generators_orchestrator.py + generators_news.py；api.py → api_base.py，清理 re-export，瘦身共计 949 行）
> v0.3.4（R-178）：R-178 html_writer.py 5 步分拆（html_save.py/html_jinja_env.py/html_renderers.py 外迁 + Step PF + 编排器精简）
> **v0.3.5（R-200）：R-200 scenario/regression/verify 三模式耗时优化（Step 0 push2 mock、B-2b 标记拆分+文件搬迁、D-4 dev-verify 新增、C verify 子阶段 --phased）**
> v0.3.5（R-204）：html_renderers.py fund_hold 三函数会话缓存 — `_render_overlap_matrix`/`_render_concentration`/`_render_style_analysis` 通过 `DataSourceRegistry.session_cache`（域名 `"fund_hold"`）消除同报告内对 `fetch_fund_holdings` 的重复调用
> v0.3.5（R-205）：`cache.py` `_CACHE_DIR` 改用 `_PROJECT_ROOT` 推导的绝对路径 `os.path.join(_PROJECT_ROOT, "data/cache")`，消除 cwd 依赖，`DegradationTracker` 跨会话持久化恢复正常
> v0.3.3（早期）：R-179~R-180、R-184~R-186（config.py 子包拆分/type:ignore 清理/预测年份动态化/定价单源 5 项）
