# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-09（D-11 全景复查 + 新增 8 项；R-204 C4 冗余记录；R-205 cwd 依赖问题；✅ 近期已修复 16 项清理归档）

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
| R-197 | **`market_value.py` 711 行持续增长**：第 3 大源文件，混合核心计算（`_compute_detail_row`）与 Excel 写入（`_write_market_value_sheet`）两重职责，随溢价率、空行情、策略选择器等新功能持续膨胀 | `report/market_value.py` | 可拆为 `market_value.py`（计算）+ `market_value_write.py`（写入）|

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-187 | **TUI Windows 平台 12 个测试跳过**：`termios`/`tty` 为 Linux 特有模块，Windows 上 `_get_key_linux()` 已加 try/except 保护 | `tui.py` + `test_tui_edge.py` | 功能降级但无错误，可考虑 CI 加 Windows runner |
| R-198 | **LLM 模块两巨头膨胀**：`generators.py`（750 行，第 2 大）+ `api.py`（702 行，第 4 大），如新增环比分析等 LLM 模块建议先横向拆分 | `llm/generators.py` + `llm/api.py` | `generators.py` 可拆出 `generators_news.py`；`api.py` 可按 provider 拆为 `api_claude.py`/`api_openai.py` |
| R-199 | **akshare 依赖老化风险**：`requirements.txt` 未锁定 akshare 版本，pytest 收集期已有 `FutureWarning`（DataFrame concat 行为变更），大版本升级可能引入兼容问题 | `requirements.txt` | 建议锁定 `akshare>=1.16,<2.0` 或类似区间 |
| ~~R-200~~ | ~~verify 模式 ~5min 耗时~~ | ~~`scripts/test_runner.py`~~ | ~~可分析瓶颈后引入增量运行~~ |
| R-201 | **HTML 打印预览缺少浏览器渲染集成测试**：当前仅 9 项 UT 覆盖 CSS `@media print` 规则，无 Playwright 快照对比确保打印输出视觉正确 | `test_html_template.py` | Playwright 快照测试，但跨系统工具优先级低 |
| R-205 | **`DegradationTracker` 跨会话持久化因 cwd 依赖从未生效**：`data_status.py` 写 `os.path.join(get_cache_dir(), ".degradation_state.json")`，`get_cache_dir()` = `os.path.abspath("data/cache")` 受运行 cwd 影响。若在 `src/` 下启动程序，路径解析为 `src/data/cache/`，持久化文件被写入错误目录，跨会话降级记忆从未生效。被双层 `try/except` 静默吞掉 | `report/data_status.py` + `cache.py` | 修复：`cache.py` 的 `get_cache_dir()` / `_CACHE_DIR` 改用相对于项目根目录的绝对路径（如 `os.path.dirname(os.path.dirname(__file__))` 推导），消除 cwd 依赖。同时删除已清除的 `src/data/cache/` 残留目录 |

### 🟢 低优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-204 | **B 系列模块文件缓存冗余读取**：`_render_overlap_matrix`/`_render_concentration`/`_render_style_analysis` 各自独立调用 `fetch_fund_holdings(code)`，同基金持仓在一次报告中读取文件缓存 3 次。无额外 API 调用（文件缓存命中），~20 只基金多 ~20ms | `html_writer.py` | 可在 R-178 分拆后用 `DataSourceRegistry.session_cache`（域名 `"fund_hold"`）消除冗余文件读 |

### ✅ 近期已修复（已记录到 changelog.md）

> 以下所有项目已完整记录至 [`changelog.md`](./changelog.md)（v0.3.3 ~ v0.3.4），此处仅保留摘要索引，详细修复说明请查阅 changelog。
>
> v0.3.3：R-188~R-193、R-203、M-004（eastmoney_industry 熔断器迁移/assert 同步/自动注册等 8 项）
> v0.3.4：R-194~R-196（technical.md 标记同步/版本一致性检查/溢价率真实计算 3 项）
> v0.3.4（R-178）：R-178 html_writer.py 5 步分拆（html_save.py/html_jinja_env.py/html_renderers.py 外迁 + Step PF + 编排器精简）
> **v0.3.5（R-200）：R-200 scenario/regression/verify 三模式耗时优化（Step 0 push2 mock、B-2b 标记拆分+文件搬迁、D-4 dev-verify 新增、C verify 子阶段 --phased）**
> v0.3.3（早期）：R-179~R-180、R-184~R-186（config.py 子包拆分/type:ignore 清理/预测年份动态化/定价单源 5 项）
