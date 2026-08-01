# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.5-dev] - 2026-08-01

（开发中，暂无条目）

---

## [0.9.4] - 2026-08-01

### Fix

- **test_runner.py GBK 控制台打印崩溃** — 子进程捕获输出经 `errors="replace"` 处理后含 U+FFFD 替换字符，直接 `print` 到 GBK 控制台抛 `UnicodeEncodeError`，Phase A 后 runner 崩溃导致 Phase B 不执行。修复：模块顶部 `sys.stdout.reconfigure(errors="replace")` 兜底（异常时静默跳过）
- **`test_tencent_success` mock 目标笔误导致静默真调 API** — `fetch_indices` 主链路实际调用 `tencent.fetch_index_price`，测试却 mock 了 `tencent.fetch_price`：有外网时真调成功侥幸通过，无外网环境暴露（返回空 → 断言失败）。修复：mock 目标对齐 `fetch_index_price` + 新增 `mock_fetch_price.assert_called()` 回归守卫，杜绝 mock 目标漂移
- **TUI [S] 菜单泄漏旧设计遗留辩论三模块（僵尸开关）** — 辩论白脸/黑脸/综合（`debate_pro`/`debate_con`/`debate_synthesis`）注册表条目保留，但作为 LLM 模块泄漏进 [S] 面板显示为 6/7/8 开关（写入 `enabled_llm` 后无任何生成路径消费，切换无效）。修复：菜单层过滤——`tui_menu.py` 新增 `LLM_MENU_HIDDEN_KEYS` 常量与 `filter_menu_llm_modules()` 辅助函数，`handlers_config.py` [S] 面板与 TUI 模型路由显示同步过滤；注册表条目原样保留（缓存 TTL/前缀清理仍依赖）。修复后 [S] 面板恢复文档描述的标准 5 模块 + 实验 6-8（正反辩论/条件推理/集中度问答）
- **LLM 空内容误判"内容被过滤"→ 根因区分 + 修复无效安抚重试** — DeepSeek V4 兼容端点为强制推理模型，`thinking` 与 `text` 共享 `max_tokens` 预算；思考部分耗尽预算时响应仅含 `thinking` block 无 `text`（复现：effort=high + max_tokens=4096 稳定触发）。`_extract_content` 对无 text block 的响应区分根因：`stop_reason=max_tokens` 记录"思考耗尽预算"日志（建议增大 max_tokens/降低 effort），其他仍记录"可能被内容过滤"；统一返回 `None` 走 provider 切换，替代对空内容追加安抚指令的无效重试
- **health_check `max_tokens` 4096→8192 + effort high→medium** — 实测（mt=8192 + effort=high 输出 5172 tokens 正常）验证增大预算可消除空 text；expert_review effort high→medium 缩短 thinking 预留文本预算。同步生产 `llm_settings.json`、默认模板 `_llm_defaults.py`

### Test

- **`test_tencent_success` mock 目标回归守卫** — 断言腾讯主链路 mock 实际被调用，防止 mock 目标与代码调用漂移后静默真调 API
- **辩论模块菜单过滤回归测试** — 新增 `TestFilterMenuLlmModules` 2 用例：过滤后仅剩 5 个标准模块（不含 `debate_pro`/`debate_con`/`debate_synthesis`）、注册表仍保留辩论三模块条目
- **`_extract_content` 空 text 回归测试** — edge 新增 `TestExtractContentEdge` 3 用例：仅 thinking + max_tokens → None 且记录预算耗尽日志（不误报过滤）、仅 thinking + end_turn → None 且记录过滤日志、thinking+text 并存正常返回；同步 4 处既有断言（空列表/仅 thinking → None）

### Docs

- **how-to-menu.md [S] 章节补充三段式说明** — 新增"6/7/8 与白脸/黑脸/综合的关系"注解：正反辩论（编号 6）内部即为白脸→黑脸→综合三段式，非独立开关；旧设计遗留的独立模块开关已从菜单隐藏（注册表保留仅用于缓存）
- **4 份用户手册同步 [S] 面板布局与辩论三模块说明** — how-to-config.md（features 章节补充 [S] 面板分组注解）、how-to-config-llm.md（模块启停补充菜单分组与三段式说明）、reports-instruction.md（§12 智囊团复盘补充辩论模式增强说明 + 对照表新增辩论式复盘行）、how-to-use-registry.md（辩论三模块标注"仅缓存管理用途、菜单已隐藏"，LLM 名称/键名查询与消费方清单同步）
- **review-findings.md rf-99 标记已修复** — 详细说明移至 changelog，摘要行保留于已修复表
- **how-to-config-llm.md 调优参数同步** — 参数表新增 `reasoning_effort` 列；health_check max_tokens 4096→8192；expert_review / health_check effort 标为 medium（非统一 high）；失败降级表区分"返回空内容（None）→ 切换 Provider"与"空字符串 → 安抚重试"；Extended Thinking 章节补充 DeepSeek V4 强制推理说明（thinking+text 共享 max_tokens 预算）与空内容调参建议（增大 max_tokens / 降低 effort）
- **llm-technical.md 空内容处理与参数同步** — 参数表 health_check 4096→8192；调用链/§5.1/§6.1 四层容错更新空内容处理（`_extract_content` 无 text block → None → 直接切换 provider；仅真正空字符串 `""` 安抚重试）；effort 兜底说明（模板默认 expert_review / health_check 为 medium）；附录 A `reasoning_effort` 枚举补 `low`/`max`
- **technical.md LLM 章节空内容处理同步** — §5.2 调用链、§5.5 关键机制表"内容过滤安抚"改为"空内容处理"（None 切 provider / "" 安抚重试）
- **review-findings.md rf-98 标记已修复** — 详细说明移至 changelog，摘要行保留于已修复表

## [0.9.3] - 2026-07-31

### Fix

- **`set_config` 并发读-改-写竞态导致丢失已有配置项** — `_core.py`：`_config_lock` 改 `threading.RLock`；`set_config` 整个读-改-写纳入锁内串行化（并发线程不再基于旧快照覆盖写）；`get_config(_strict=True)` 文件存在但读取失败时抛异常中止写而非静默回退默认配置覆盖（P2 verify 门禁在 xdist 4-worker 下暴露：并发测试 `final.get("base")` 为 None）；新增损坏文件不覆盖回归测试
- **辩论虚构过滤按"行"删除导致整段误删** — `_hallucination_filter.py` 过滤粒度从"整行"改为"行内句段"（先按行、行内再按句末标点切分），markdown_to_html 输出的单行 HTML 不再因一个误判 token 被整段清空（6412 字符→0 字符→白脸失败回退普通模式）
- **虚构过滤时机下移** — `skeleton.py` 新增 `raw_filter_fn` 钩子，在 markdown_to_html 之前对 LLM 原始输出过滤（作用于带换行的 Markdown）；`generators.py` 辩论 pro/con/synthesis 三处手动过滤收敛到骨架一处，synthesis 顺带获得过滤保护
- **虚构代码误报降低** — `_is_safe_word` 豁免 `TOP\d+`（提示词附录 TOP3 块回声），白名单新增 `smart`/`money`（Smart Beta/Money 等金融术语）
- **`max_tokens_penetration_deep` 4096→8192** — 同步生产配置 `llm_settings.json`、默认模板 `_llm_defaults.py`、`how-to-config-llm.md`，避免穿透深度分析输出撞 max_tokens 上限触发 1.5× 重试
- **test_runner.py subprocess UnicodeDecodeError** — 两处 `subprocess.run` 添加 `errors="replace"`，防止 Windows 子进程输出非 UTF-8 字节时崩溃
- **回撤数值误判窗口收窄** — `_is_drawdown_context` 近邻守卫窗口 30→15 字符，避免跨分句误判"累计"为收益率关键词
- **辩论模式 synthesis 条件推理注入补全** — `_build_debate_synthesis_prompt` 新增 `enable_conditional` 参数，辩论+条件推理同时开启时 synthesis 阶段追加配置化情景分析，弥补 pro/con 跳过情景分析的空缺
- **缓存测试 patch 路径修复** — `test_handlers_cache.py` 的 `@patch` 目标从 `providers.akshare_extras` 修正为 `fetcher.akshare`（模块加载本地绑定导致 xdist 并行下间歇性失败）
- **新闻去重测试用例同步** — `test_cross_source_english_token_only_overlap` 预期合并 1 条；`test_cross_source_bg2_low_ratio_kept` 替换测试数据

### Test

- **set_config 并发竞态回归测试** — 新增 `test_set_config_raises_on_corrupt_file`（edge）：配置文件损坏时 `set_config` 抛异常且不覆盖原文件，杜绝静默回退默认配置覆盖写丢数据；原并发测试 `test_concurrent_set_config_thread_safe` 修复后 5 连跑稳定通过
- **虚构过滤回归测试** — 新增 4 用例：`test_sentence_level_removal_same_line`（行内句段删除）、`test_top_rank_suffix_not_filtered`（TOP2/TOP3 豁免）、`test_smart_term_not_filtered`（Smart 豁免）、`test_filter_single_line_html_keeps_other_sentences`（单行 HTML 不整段清空，edge）
- **测试用例数据更新** — 同步 bg=2 梯度阈值 0.40 更新后的去重预期行为

### Docs

- **llm-technical.md 骨架流程同步** — 骨架执行 ASCII 图新增 `③' 原始输出过滤（可选）` 步骤（`raw_filter_fn` 钩子，位于截断处理之后、markdown_to_html 之前）；模块表更新 `skeleton.py` 描述与 `generators.py` 辩论生成说明；`max_tokens_penetration_deep` 参数表 4096→8192
- **technical.md 虚构过滤架构表行更新** — 描述改为"句子级删除 + `raw_filter_fn` 钩子时机下移"，同步 C 约束表对应行的设计说明
- **test-coverage.md 统计快照更新** — all 3806 / unit 3494 / standard 2957 / verify 2248 / edge 474 / unit_llm 650 / LLM 功能域 683（2026-07-31 实时收集）
- **folders.md 目录树与统计项更新** — 主程序 182/43422、脚本 10/3460、源码合计 193/48744、测试代码 217/59014、测试用例 3806；目录树含 `src/test/data/hallucination/` 两个 gitignore 测试数据集文件
- **how-to-config-llm.md `max_tokens_penetration_deep` 8192** — JSON 示例与参数表行同步
- **review-findings.md rf-96 标记已修复** — 详细说明移至 changelog，摘要行保留于已修复表

## [0.9.2] - 2026-07-31

### Feat

- **事实校验 v3：自动修正机制** — `fact_checker.py`：`check_numerical_consistency` 返回 `(issue, correction)` 二元组、`run_fact_check` 返回 `(corrected_html, summary_html)`、`apply_numerical_corrections` 支持正则级联替换；新增 `tolerance_pct` + `tolerance_overrides` 逐模块容差、pp 混淆语境跳过策略
- **Prompt 防御统一注入架构** — `prompts_tables.py` 新增 `_build_prompt_appendix`（TOP3 排名 + 数据速查表 + 代码白名单），在 `skeleton.py:_run_standard_mode()` 自动注入到所有模块的 user prompt 末尾，各模块无需手动调用；`prompts_action.py` 移除各模块的手动防御调用
- **跨源 bg=2 梯度阈值调低至 0.40** — `news_dedup.py` 的 `cross_merge_bg2` 规则从 `ratio≥0.45` 降至 `ratio≥0.40`，基于校准报告（119654 条锚点）发现 bg≥2+ratio≥0.35 区间有 580 条含实体重叠被跳过，0.40 可额外捕获约 300-400 条真实重复，bg=2 已提供实体重叠安全垫
- **辩论模式 synthesis 条件推理注入** — `prompts_action.py:_build_debate_synthesis_prompt` 新增 `enable_conditional` 参数，辩论+条件推理同时开启时在综合阶段追加配置化情景分析（涨/跌/震荡三情景），弥补 pro/con 因 `skip_scenarios=True` 跳过情景分析的空缺

### Fix

- **辩论模式 synthesis 重复白脸/黑脸观点 + 情景分析** — `prompts_core.py:_SYSTEM_DEBATE_SYNTHESIS` 重写：明确禁止 synthesis 重述双方论点（"读者已阅读过原文"）、禁止插入情景分析段落；输出结构从"关键分歧点→分歧定论"改为"共识与分歧摘要→综合评估"，压缩 LLM 重复论述空间
- **`_build_debate_synthesis_prompt` 错误标记 HTML 为 markdown 代码块** — `prompts_action.py:463` 中 ` ```markdown ` → ` ``` `（pro_text/con_text 已是 HTML，标记为 markdown 误导 LLM）
- **LLM 持仓排名幻觉** — `_build_code_whitelist_block` 声明 #1 品种身份，阻止 LLM 将非排名 #1 的代码断言为"最大持仓"
- **LLM 数值混淆（pp 贡献占比 ↔ 收益率）** — `_build_data_slot_block` 提供精确逐品种收益率，`fact_checker` 增强 pp 语境检测
- **`_SYSTEM_EXPERT_REVIEW` 情景分析双重指令** — 从 system prompt 移除"### 情景分析"段（第54-66行），移至 user prompt builder 作为单一注入点；`_build_expert_review_prompt` 新增 `skip_scenarios` 参数，辩论 pro/con 跳过情景分析避免双重输出
- **回撤数值误判为收益率** — `fact_checker.py`：新增 `_DRAWDOWN_KEYWORDS` 和 `_is_drawdown_context`（全句扫描回撤关键词+ match 前 15 字收益关键词近邻守卫，避免跨分句干扰），回撤语境数值改与实际 `max_drawdown_pct` 比较而非与组合累计收益率比较；告警消息增加句段截图（`句段：...`）辅助定位
- **已修正值不重复告警** — `run_fact_check` 中已自动修正的数值不再在 ⚠ 告警明细中重复列出（仅保留"自动修正 N 处"摘要），用户看到的内容中已不存在该值即不警告

### Test

- **事实校验测试扩展** — 新增 `test_pp_vs_rate_confusion_detected`、`test_contribution_sentence_skips_pp_values`、`test_tolerance_override_looser` 三个测试用例
- **回撤语境检测回归测试** — 新增 6 用例：`test_drawdown_value_within_tolerance`（19.0%≈18.97%→通过）、`test_drawdown_value_out_of_tolerance`、`test_drawdown_value_no_data_skips`、`test_drawdown_mixed_with_profit_in_sentence`（分句感知）、`test_issue_message_contains_sentence_snippet`（句段截图验证）、`test_run_fact_check_corrected_values_not_in_warnings`（已修正不重复告警）
- **辩论 synthesis 测试同步** — `test_system_debate_synthesis_contains_placeholders` → `test_system_debate_synthesis_contains_instruction_keywords`（验证"不要重复"指令）；`test_output_contains_markdown_code_block` → `test_output_contains_code_block`
- **场景分析指令迁移测试** — 新增 `TestBuildExpertReviewPromptSkipScenarios` 3 用例（`skip_scenarios=True` 剔除场景、默认保留场景、不影响其他内容块）
- **统一注入防御专用测试** — 新增 `TestBuildPromptAppendix` 4 用例（空持仓、单品种含三块、多品种排序验证、零市值防除零）
- **测试适配** — `test_mode2_disabled` 改为断言标准场景存在（场景指令已从 system prompt 移入 user prompt）；`test_system_expert_review_constant` 改用"置信度指引"代替已移除的"情景分析"断言
- **新闻去重测试用例同步** — `test_cross_source_english_token_only_overlap` 从预期保留 2 条改为预期合并 1 条（匹配 bg=2+ratio≥0.40 新规则）；`test_cross_source_bg2_low_ratio_kept` 替换测试数据（改用 ratio≈0.375 的"科技板块持续走强"vs"国际油价持续走弱"验证 <0.40 不合并）
- **缓存测试 patch 路径修复** — `test_handlers_cache.py:TestRefreshDividendCache` 中 `test_with_valid_codes` 和 `test_empty_holdings` 的 `@patch` 目标从 `src.python.providers.akshare_extras.get_dividend_data` 修正为 `src.python.fetcher.akshare.get_dividend_data`（模块加载时本地绑定导致 xdist 并行下间歇性失败）

### Docs

- **全文档路径引用同步** — 子包重构后（`core/`、`tui/`、`cli/`、`config/`）过期路径集中清理：`technical.md`（~20 处）、`llm-technical.md`（5 处）、`test-coverage.md`（6 处）、`testplan.md`（6 处）、`review-findings.md`（3 处）、`how-to-schedule.md`（2 处）、`plan-correlation-drawdown.md`（4 处）、`plan-chartjs-report-upgrade.md`（2 处）、`plan-chartjs-risk-analysis.md`（11 处）
- **校准报告归档** — `calibrate-dedup-threshold.py` 输出保存至 `docs-stm/tmp/dedup-calibration-report.md`，含 `cross_merge_bg2` 新规则基线数据（119654 条锚点）
- **requirements.md §11.4 `proxy_preferred` 措辞修正** — "proxy_preferred 策略使用" → "per-provider 后处理标记，有代理环境时自动前置"，与 §7.1 R-LLM-06 定义保持一致
- **testplan.md 菜单选项数同步** — §1.1 tui/tui_menu.py 和 §3 TUI 菜单行中 "15 选项" → "16 选项"（同步菜单已新增 [I] 管理对比指数池的当前状态）

## [0.9.1] - 2026-07-30

### Refactor

- **src/python/ 根文件归入子包** — 将 17 个根目录文件分别迁入 `core/`（基础设施）、`tui/`（TUI 入口）、`cli/`（CLI 入口）、`config/`（配置模块）四个子包；`handlers_check_sources.py` 因 CLI/报告共享迁入 `core/check_sources.py`；新增 `__init__.py` re-export 保持导入兼容；新增 `__main__.py` 支持 `python -m`；移除死代码 `_breaker_state.py`

### Docs

- **folders.md 目录树同步** — 根文件迁移后目录树更新至子包结构（core/cli/tui/config）
- **文档路径引用同步** — `faq.md`、`how-to-config.md`、`how-to-start.md`、`how-to-use-registry.md`、`scripts-reference.md`、`requirements.md`、`technical.md` 中过期路径全部更新为子包路径（`src/python/constants.py` → `src/python/core/constants.py` 等）
- **technical.md 附录 A 目录树更新** — 替换为最新子包结构

### Fix

- **CLI 测试 patch 路径修复** — `__init__.py` re-export 导致 mock 路径需加 `.cli` 层级，`test_cli.py` 和 `test_cli_edge.py` 共 6 处 patch 路径修正
- **technical.md 附录 B 标题重复** — 附录替换脚本导致的重复标题修复

## [0.9.0] - 2026-07-30

### Chore

- **ruff 版本锁定 + 全量格式修正** — `pyproject.toml` 锁定 `ruff==0.15.20`（精确版本，避免版本升级导致格式噪音）；全量运行 `ruff format src/python/ scripts/`，修复 CI ruff 格式检查报错
- **版本格式统一** — 管理文档版本头统一去除 `v` 前缀（如 `v0.8.12-dev` → `0.8.12-dev`），`check-version-consistency.py` 模板同步（`v{v}` → `{v}`），涉及 9 份文档

### Docs

- **review-findings.md 归档整理** — 0.8.* 已发布版本的已修复记录（rf-1~rf-64、rf-66~rf-135、rf-106~rf-107）迁移至 `archived_review-findings.0.8.x.md`，归档链接路径修复（`archive/0.8.x/` → `archive/v0.8.x/`）
- **plan.md 归档整理** — 0.8.* 已完成项（plan-12 数据源可用性矩阵、plan-13 数据源可靠性文档、plan-14 ADR）迁移至 `archived_plan.0.8.x.md`
- **changelog.md 归档整理** — v0.8.11 变更记录迁移至 `archived_changelog.0.8.x.md`

## 归档

- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

