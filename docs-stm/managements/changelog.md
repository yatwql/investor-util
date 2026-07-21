# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.7.8-dev] - 未发布

### Changed
- **changelog.md**: v0.7.0~v0.7.7 详细变更记录归档至 `archive/v0.7.x/archived_changelog.0.7.x.md`，主文件仅保留当前版本 + 归档索引
- **better-investment-advice 完整归档**：目录从 `docs-stm/plan/` 移至 `docs-stm/archive/v0.7.x/`，所有外部引用（technical.md 3 处、plan.md 1 处、folders.md 1 处）同步更新
- **管理文档版本头同步**：llm-technical.md、test-coverage.md、folders.md 版本头更新至 v0.7.8-dev
- **reports-instruction.md**: 补充投资分析与风控/基金评价功能-报告位置对照表

### Docs
- **scripts-reference.md**: 新增辅助脚本统一参考文档（scripts/ 下 10 个脚本用法速查），从 how-to-test-my-code.md 提取散落内容并补充缺文档脚本（check-version-consistency.py、perf_report.py、diagnose_gemini_proxy.py、launch 脚本）
- **how-to-test-my-code.md**: "辅助脚本"节替换为指向 scripts-reference.md 的交叉引用链接，避免重复维护
- **README.md**: 开发者参考表新增"辅助脚本参考"入口
- **CLAUDE.md**: 用户文档分册列表追加 scripts-reference.md
- **folders.md**: 目录树追加 diagnose_gemini_proxy.py；manuals 追加 scripts-reference.md
- **discussion-better-investment-advice.md**: Phase 3 状态（LLM 事实校验器从待办改为 ✅）、Phase 4 状态（从"11 项已交付+4 项待办"改为"全部 15 项 ✅"），版本头（v0.7.7 → v0.7.8-dev），顶部状态摘要同步
- **Phase 5（用户画像）+ Phase D（CAPM α）已关闭**：better-investment-task.md 全部 8 项标记 ❌ 已关闭，汇总表同步；discussion-better-investment-advice.md 总览表、风险表、依赖关系图、全量估时描述同步更新
- **plan.md**: 恢复概述节与归档索引（v0.1.x ~ v0.7.x）
- **review-findings.md**: 恢复历史审查记录链接 + 历史归档节

### Added
- **Task91 增强 LLM 策略（辩论模式 I-01~I-12）**：
  - **辩论模式 M1（白脸/黑脸/综合）**：`generate_debate_procon()` 三段式辩论（pro→con→synthesis），两级 fallback（pro/con 失败→回退普通模式、synthesis 失败→返回 pro+con 拼接）
  - **条件推理 M2**：场景注入用户提示词（自定义市场场景 → 条件化的 expert_review 分析）
  - **集中度问答 M3**：阈值触发的持仓集中度问答块生成（单品种≥5%/前三≥60%/行业≥40%）
  - **Token 预算守卫**：基于 char 计量的 token 预算控制（超过 1× 预算跳过 synthesis、超过 2× 预算跳过全部 debate）
  - **虚构代码过滤**：`_filter_hallucinated_codes()` 基于正则的 LLM 输出行级幻觉过滤（兼容中文环境的 `\b` 替代方案）
  - **缓存体系**：三段独立缓存（pro/con/synthesis），session 级线程安全缓存，指纹驱动的缓存键
  - **HTML/Excel 渲染**：辩论实验模式标签、pro(绿)/con(红)/synthesis(金) 三色块渲染、棒棒糖式展开设计
  - **配置文件**：`llm_settings.json` 新增 `debate` 配置段（per_call_max_tokens/synthesis_temperature/max_total_tokens_per_report 等）
  - **Feature Flag**：`features.py` 新增 `llm_debate_procon`/`llm_debate_conditional`/`llm_debate_qa_concentration` 三开关
  - **测试套件**：62 项单元测试 + 3 项集成测试覆盖（含边缘场景/Token 预算/管线集成/prompts/generators 等）
  - **监视脚本**：`scripts/check_debate_architecture.py` 架构一致性巡检

### Docs
- **technical.md** — 内部核对修复（多轮）：
  - §5.1: "13 子模块" → "14 子模块"，新增辩论路由描述段
  - §5.3: 标准 5 模块表下方补充辩论模式路由注记
  - §5.5: 关键机制表新增辩论路由/Token 预算守卫/虚构代码过滤 3 行
  - §6.2: "26 个数据模块" → "30 个数据模块"，数据模块表新增辩论缓存行
  - TOC: 补全附录 F/G/H 链接
  - L1896: `espert_review` → `expert_review`（拼写修复）
  - 附录 A: "25 项 Feature Flag" → "28 项"，"6 个计算模块" → "7 个"，"14 个文件" → "16 个文件"（providers/ 文件数同步 §1.3）
  - 附录 C: 新增 llm_debate_pro/con/synthesis 三段辩论缓存 TTL 行（24h、preload 组、复用 expert_review 指纹）
- **requirements.md** — §11.5 新增缺失 metrics_* 行（sharpe/calmar/hhi/win_rate/turnover/risk_contribution/beta 共 7 项）
- **how-to-config.md** — §I features.json 表修复：`25项`→`28项`，新增辩论 3 项 + metrics_* 7 行 + history_portfolio/history_benchmark + cache_daily_cleanup
- **how-to-menu.md** — [S] 节新增 Feature Flag 完整文档块（文件路径/JSON 示例/开关-菜单对照表/交叉引用）；2 处 `管理对比基金池`→`管理对比指数池`
- **how-to-start.md** — CLI 参数表 `--history` 默认值 `auto`→`off`（对齐 `cli.py` 实际默认值）；移除已过时的 `# (可选) colorama` 注释（已在 requirements.txt 硬依赖）
- **全域文档清理历史痕迹**：technical.md 移除"原本内联在 orchestrator.py"等历史重组描述；how-to-config-llm.md 移除 4 处"旧版"/"不再使用"历史标签；review-findings.md 归档索引移除版本范围描述，"v0.6.x 历史审查记录"改为通用"审查记录归档"；plan.md 归档索引移除版本范围描述

### Fixed
- **test_orchestrator.py** — `capture_snapshot` mock 缺少 `return_value` 导致 MagicMock 无法通过 `isinstance(x, dict)` 断言：`test_generate_report_full_news_only`、`test_generate_report_full_llm_only`、`test_generate_report_full_both_disabled` 3 个测试补上 `return_value=None`

### Plan
- **task91-enhanced-llm-strategy.md D16 终轮一致性扫描修复**：
  - 修复目录编号偏移（§6/§7/§8 锚点与实际标题对齐）
  - I-09 cost_tracker.py 误引用→改为 `generate_debate_procon()` 内建 output token 守卫（D9 发现落地）
  - I-06 闭包变量捕获→改为 list-container 模式（D14 发现落地）
  - R6 第三层防线"综合阶段交叉校验"不存在→降为 2 层防线描述，添加注释（D16 发现）
  - R2 交叉引用错误（I-12→I-03）修复
  - I-03 session_cache 添加 threading.Lock 线程安全要求
  - §4.4 新增/修改文件清单补全遗漏文件（html_writer.py、orchestrator.py、llm_content.py 等）
  - 依赖图 I-12 连接分支修正（从 I-04/I-05 块移至独立节点）
  - I-06 文件变更补全 orchestrator.py

---

## 归档

- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.7（2026-07-18 ~ 2026-07-20）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

