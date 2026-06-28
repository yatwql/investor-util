# 投资分析报告小工具 — 质量控制与测试标准

创建日期：2026-06-26

---

## 1. 测试分类

### 1.1 单元测试

每个 Python 模块对应的测试文件位于 `src/` 同级目录下。

**测试框架**：使用 Python 内置 `unittest` 或 `pytest`（按最终选型定）。

**覆盖要求**：
- 数据模型（`models.py`）：100% 覆盖字段验证逻辑
- 配置管理（`config.py`）：100% 覆盖读写、缺省、异常路径（含 `output_dir` 字段）
- 持仓读取（`reader.py`）：覆盖标准格式、缺字段、空文件、格式错误
- 缓存管理（`cache.py`）：覆盖过期判断、读写、文件缺失、前缀清理
- API 数据获取（`providers/*.py`）：mock HTTP 请求，覆盖正常返回、超时、异常格式（含 `eastmoney_industry.py`）
- LLM 客户端（`llm_client.py`）：覆盖 API 调用路由、返回类型元组解包、缓存逻辑、截断检测
- 报表生成（`report/*.py`）：每个模块至少覆盖正常数据和空数据两种场景
- 关键词富化（`report/news_correlation.py`）：覆盖持仓/穿透/行业三种来源类型、去重逻辑、空列表边界、Excel 格式断言（wrap_text、列宽）
- TUI 菜单（`main.py`）：覆盖所有菜单选项的输入输出

### 1.2 集成测试

- **数据流完整链路**：持仓 xlsx → 数据获取 → 缓存 → Excel/HTML 输出，全流程可走通
- **API 联通性**：手动验证腾讯财经、东方财富、天天基金 API 实际可调通（每次迭代至少验证一次）
- **缓存与 API 协同**：缓存存在 + 未过期 → 不调 API；缓存不存在 → 调 API 并写入

### 1.3 异常场景测试

| 场景 | 预期行为 |
|---|---|
| 持仓目录不存在 | TUI 提示配置目录，不崩溃 |
| 持仓目录为空 | TUI 提示配置目录，不崩溃 |
| 持仓 xlsx 格式异常 | 提示具体错误行，跳过异常行 |
| 网络断开 | 提示网络异常，使用缓存数据或显示"--" |
| API 超时 | 自动切换备用链路；全部失败则跳过该数据 |
| API 返回异常数据 | 跳过该条，日志记录 |
| 缓存文件损坏 | 删除损坏缓存，重新获取 |
| 报告输出目录无写入权限 | 提示文件写入失败 |
| 股票代码前缀缺失（600000 vs sh600000） | 自动补全或正确处理 |
| ThreadPoolExecutor 并发取价竞争 | 每种资产正确获取独立价格 |
| LLM API 超时（120s 上限） | 降级返回 None，报告输出占位文本 |
| LLM 缓存中 HTML 格式与旧版本 Markdown 格式共存 | 新缓存直接存储 HTML，老缓存自然过期（指纹变更） |
| 空持仓下菜单 [L] 全系列报告生成 | 跳过 LLM 调用，输出空占位 |
| cache.set() 写入时目录被删除 | 自动重试，不抛出异常 |
| config.json / llm_settings.json / llm_key.json 配置值异常 | 输出警告，使用代码默认值 |
| fund_performance.json 中 categories/data 为 JSON null | 自动兜底为空列表，不崩溃 |
| html_writer.py LLM 内部调用路径（enable_llm=True, llm_content=None） | 传入 dict 类型指数数据，不因 .values() 缺失崩溃 |
| summary.py write_summary_sheet 收到 list 而非 dict | write_summary_sheet 从 fetch_indices() 接收 dict，不因 .get() 缺失崩溃 |
| fund_performance _adjust_rating_with_benchmark 中 categories 传入 None | 自动兜底为空列表不崩溃；循环中 cat 为 None 时 `in` 操作不崩溃 |
| perf_eval.get("categories") / get("data") 返回 None 时 len() 和 enumerate() | 使用 or [] 兜底后，len([]) = 0 不崩溃，enumerate([]) 为空迭代 |

### 1.4 数据正确性验证

| 验证项 | 方法 |
|---|---|
| 市值 = 最新价 × 份额 | 抽样 3-5 条持仓手动计算比对 |
| 盈亏 = 市值 - 成本 | 同上 |
| 分账户小计 = 该账户持仓合计数 | 逐账户比对 |
| 总计 = 各账户小计之和 | 比对总计行 |
| 穿透 TOP10 合并逻辑 | 构造两个基金持相同股票 + 直接持有，验证合并正确 |
| 本日盈亏计算 | 给定时价、昨收、份额，验证公式输出 |

### 1.5 UI/UX 验证

| 验证项 | 标准 |
|---|---|
| TUI 菜单显示 | 选项完整、中文字符正常、按键响应正确 |
| Excel 文件 | 各页签命名正确、冻结首行、颜色格式正确 |
| HTML 文件 | 浏览器渲染正常、中文字符无乱码、布局清晰 |

---

## 2. 各迭代测试重点

| 迭代 | 测试重点 |
|---|---|
| Iter 1.1 | 配置文件读写正确性、启动脚本可用性 |
| Iter 1.2 | xlsx 解析正确性、菜单导航完整性 |
| Iter 1.3 | API 联通性、缓存过期逻辑、备用链路切换 |
| Iter 1.4 | Excel 生成正确性、15 列对齐、颜色格式、盈亏计算 |
| Iter 1.5 | 全链路异常场景覆盖 |
| Iter 2 | 分类汇总聚合计算、穿透合并逻辑（含精细化分类）、基金排名数据正确性 |
| Iter 3.1 | HTML 渲染效果、Jinja2 模板正确性、5 模块内容一致性 |
| Iter 3.2 | 3 源新闻聚合正确性、关键词关联准确度、`news_top_count` 可配置验证 |
| Iter 3.3 | 模板占位显示（模块 7/8）、缓存管理（菜单 [3] 清理 / [4] 统计）、缓存文件损坏自动修复、异常友好提示（网络/权限/文件损坏） |
| Iter 3.4 | LLM API 联通性、缓存 24h 生效、API Key 未配置降级占位文本、LLM 输出格式兜底 |
| Iter 3.5 | LLM 并行生成模块 7+8 同时成功、System Prompt 外部可配置生效、httpx 连接池复用、提示词紧凑化效果 |
| Iter 3.6 | 多线程并发缓存获取无竞态、新闻 15min 缓存过期、LLM 缓存预检正确跳过线程池、Token 用量正确展示、_SYSTEM_EXPERT 压缩后三阶段格式保持、死代码无残留、配置校验警告正确触发 |
| Iter 3.7 | html_writer.py 中 a_indices 以 dict 类型传入 generate_all_llm（不因 .values() 崩溃）、fund_performance.py 在 API 返回 JSON null 时 categories/data 自动兜底、summary.py write_summary_sheet 接收 dict 类型指数数据（不因 list 传入致 .get() 崩溃）、fund_performance._adjust_rating_with_benchmark 中 categories 含 None 时自动兜底 |
| v0.2.10 | 关键词富化函数 `_build_keyword_lookup`/`_enrich_keywords_for_item`/`_format_enriched_keywords` 单元测试覆盖三种来源类型（持仓/穿透/行业）、去重逻辑、空列表边界；Excel 格式断言（B/C 列 wrap_text、列宽 B=40/C=50、左对齐、富化关键词写入）；HTML 模板 enriched_keywords 着色（holding→蓝/penetration→紫/industry→灰） |
| v0.2.11 | `eastmoney_industry` provider 单元测试覆盖正常返回（含/不含概念）、data 为空、响应为空、超时异常、基金代码处理；`fetcher.fetch_industry_data` / `batch_fetch_industry_data` 缓存集成测试；`_build_keyword_lookup` 新增 concept 类型覆盖测试；`_enrich_keywords_for_item` 新增概念类型富化显示测试；全量 607 passed |
| v0.2.18 | 新增 `test_akshare_extras.py`（16 项）：指数指纹计算、缓存键生成、分红汇总计算、分红数据获取全路径、内存缓存（TestMemoCache 5 项）；`test_llm_client.py` 新增 sector_flow prompt 注入测试（2 项）、batch 新闻 LLM 分析测试（6 项）；全量 749 passed |

---

## 3. 验收标准

每个迭代完成后必须满足以下条件方可进入下一迭代：

1. 当前迭代的所有计划功能已实现
2. 所有单元测试通过
3. 人工验证测试覆盖的异常场景程序不崩溃
4. Excel/HTML 输出文件内容在 visual 检查下无明显的格式或数据错误
5. TUI 菜单所有可用选项功能正常

---

## 4. 测试记录

测试记录和发现的问题记录在 `docs-stm/managements/changelog.md` 中。
