# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-05（v0.2.85 — C 迭代实施后文档审核同步）

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

| 2026-07-05 | R-156：push2 行业数据频繁 "Server disconnected" — 重试次数 1→3、指数退避+抖动、超时 10s→15s、批量级失败重试 | ✅ 已完成 |
| 2026-07-05 | R-157：push2 全线不可用时无 fallback — 新增 `eastmoney_industry_rest` 备用链路（行情页 scraped quotedata），`industry` chain 扩展为双链路 | ✅ 已完成 |
| 2026-07-06 | R-159：代码类型判定逻辑散落 8 个文件 — 创建 `code_utils.py`，收敛 `is_a_share_code`/`is_fund_code`/`is_exchange_fund_code`/`is_hk_stock_code`/`is_qdii_by_name`/`is_bond_related_by_name`/`is_index_link_by_name`/`is_etf_by_name` 等所有判定原语；全量迁移 12 个调用方（penetration/category/market_value/akshare_extras/penetration_sheet/fund_performance/llm/prompts/eastmoney_industry/eastmoney_industry_rest/tencent/fetcher/industry）；删除重复的 `_is_qdii`/`_is_etf`/`_is_bond_fund`/`_is_index_link` | ✅ 已完成 |

---
## 待处理

| 2026-07-07 | D-6 审计发现：基金风格分析 3 条测试已存在失败（`test_push2_fallback_to_tencent`/`test_weighted_style`/`test_with_push2_data`），与 D 迭代无关，D-5 前即存在 | 🔴 待处理 |
| 2026-07-07 | D-6 审计发现：HTML 结构测试 7 条已存在失败（section 计数期望 16 实际 17，一个 section div 缺 id/order），与 D 迭代无关，D-5 模板变更后即出现 | 🔴 待处理 |

_已修复问题详细变更记录见 `docs-stm/managements/changelog.md`。_
