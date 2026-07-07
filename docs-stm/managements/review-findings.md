# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-07（D-7a + D-8 完成 — B系列占位/全链路基线锁定）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|

> **v0.1.x ~ v0.2.52 早期审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.1.x.md](../archive/archived_review-findings.0.1.x.md)。
> 涵盖：初始全量审计、P3 现代化、场景审计、第二/三波深度审计、R-131~R-147、T-001~T-003 等 13 条。

---

| 2026-07-04 | 全技术债务审计：版本漂移/except Exception 追踪/模板格式统一 | ✅ 已完成 |
| 2026-07-04 | R-149~R-155 全部 5 项修复（安全注释/re-export审计/缓存展示/API签名验证/页签排序） | ✅ 已完成 |
| 2026-07-05 | C 迭代实施后文档审核：`_ENV.globals` vs 模板上下文不匹配/CSS order 顺序修复/模块 data rows Border/Side 隐式导入依赖/`fund_deep`→`enable_b_series` 命名对齐 | ✅ 已完成 |
| 2026-07-06 | R-158：Excel "LLM API 用量" 页签未显示 API 调用统计和模块明细（`formatted` 缺 `per_module` 键导致） | ✅ 已完成 |
| 2026-07-07 | **D-8 设计复盘** — 3 项建议：(1) D-7b 延期后验收标准中"5 个新闻源"已不符，D-7b 恢复后补测 (2) 计划文档文件映射 test_html_writer_edge.py → test_excel_generator_edge.py 需同步 (3) `test_global_degradation_bseries_placeholder_logged` 断言 `errors==0` 在空数据优雅处理逻辑下正确，但后续有人加 add_error 时会断裂，建议保留评论说明 | ✅ 已完成（复盘建议） |

| 2026-07-07 | **D-7a + D-8 实施**：B 系列 4 模块空态占位（无条件写入 + 占位文本）、全链路回归基线锁定（全局降级冒烟 + 消息一致性 14 条 edge 测试）、2 个全量测试失败修复（`llm_max_concurrency` 注册 + 缓存跨日新鲜度 mock） | ✅ 已完成 |

| 2026-07-05 | R-156：push2 行业数据频繁 "Server disconnected" — 重试次数 1→3、指数退避+抖动、超时 10s→15s、批量级失败重试 | ✅ 已完成 |
| 2026-07-05 | R-157：push2 全线不可用时无 fallback — 新增 `eastmoney_industry_rest` 备用链路（行情页 scraped quotedata），`industry` chain 扩展为双链路 | ✅ 已完成 |
| 2026-07-06 | R-159：代码类型判定逻辑散落 8 个文件 — 创建 `code_utils.py`，收敛 `is_a_share_code`/`is_fund_code`/`is_exchange_fund_code`/`is_hk_stock_code`/`is_qdii_by_name`/`is_bond_related_by_name`/`is_index_link_by_name`/`is_etf_by_name` 等所有判定原语；全量迁移 12 个调用方（penetration/category/market_value/akshare_extras/penetration_sheet/fund_performance/llm/prompts/eastmoney_industry/eastmoney_industry_rest/tencent/fetcher/industry）；删除重复的 `_is_qdii`/`_is_etf`/`_is_bond_fund`/`_is_index_link` | ✅ 已完成 |

---

_当前无待处理问题。已修复问题详细变更记录见 `docs-stm/managements/changelog.md`。_
