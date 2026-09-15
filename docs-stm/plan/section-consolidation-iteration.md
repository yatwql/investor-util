# 报告章节整合实施层（迭代施工单）

> 文档类型：中间设计文件（实施层）——与设计层 [`section-consolidation-design.md`](section-consolidation-design.md) 配套
> 分工：设计层定「合并什么、为什么、新语义名、架构约束对照」；**本文件是施工单**——逐批列出改动文件、
> 命名统一动作、测试同步清单与量化验收标准，实施时按批次勾选并逐批提交
> 状态：批次①已实施；批次②③④待实施

## 1. 命名统一总表（唯一施工依据）

| 旧名（全部删除，不留 alias） | 新语义名 | 新显示名 |
|:--|:--|:--|
| `market_value` + `category` | **`holdings_detail`** | 持仓明细与分类 |
| `position_relationship` + `fund_concentration` | **`position_structure`** | 持仓结构与集中度 |
| `financial_indicator` + `financial_report_digest` | **`fundamental_snapshot`** | 持仓基本面 |
| （`fund_manager` 并入） | `fund_performance`（键/显示名语义未变） | 基金业绩分析 |

**契约层不改名**：`position_relationship_data` / `concentration_data` / `manager_data` /
`financial_indicator_data` / `financial_report_digest_data` 全部保留（契约描述数据内容而非章节）。

## 2. 接缝地图（实施前已核实，含精确位置）

| 接缝 | 位置 |
|:--|:--|
| 注册表条目（顺序/显示名/type/data_flag/**data_flag_any**） | `core/registry.py::_REPORT_SECTION_DEFAULT`（521 行起；字段契约注释见其上方） |
| 页签名表 | `core/registry.py::_REPORT_SHEET_NAMES`（378 行起）+ `get_report_sheet_name()` |
| 可见性判定（Excel 侧） | `report/excel_sheet_factory.py::should_create_sheet`（含 `data_flag_any` OR 支持） |
| 可见性判定（HTML 侧） | `report/html_writer_nav.py::_compute_section_visibility` + `_SECTION_NAV_GROUP_MAP`（导航分组） |
| Excel 分派点 | `market_value`→`excel_generator.py:297`；`category`→`excel_content_sheets.py:58`；`fund_performance`→`excel_content_sheets.py:80`；`fund_manager`/`position_relationship`/`fund_concentration`→`excel_fund_deep_analysis.py:107/129/185`；`financial_report_digest`→`excel_generator.py:396`；`financial_indicator`→`excel_generator.py:407` |
| 页签写入器 | `report/market_value_sheet.py::write_market_value_sheet`(232) / `report/category.py::write_category_sheet`(271) / `report/position_relationship_sheet.py` / `report/fund_concentration_sheet.py` / `report/fund_manager_sheet.py` / `report/financial_indicator_sheet.py` / `report/financial_report_sheet.py` |
| HTML 锚点 | `report_template.html`：`sec-market_value`(1102) / `sec-category`(1183) / `sec-fund_performance`(1393) / `sec-fund_manager`(1499) / `sec-position_relationship`(1563) / `sec-fund_concentration`(1811)；`partials/financial_indicator_section.html` / `partials/financial_report_section.html` |
| 契约写入点 | 经理/集中度/关系数据由编排层组装后写入 `pipeline_data`（`manager_data` / `concentration_data` / `position_relationship_data`） |

## 3. 批次①（已实施，留档）

可见性模型扩展：注册表可选字段 `data_flag_any`（多契约 OR，悲观判定）+ Excel/HTML 两侧支持 +
`src/test/unit/report/test_section_visibility.py`（12 例）。**零条目变更、行为零变化**。

## 4. 批次② 施工单：`holdings_detail`（持仓明细与分类）

**前置**：无（两个来源条目均 `always`、无契约键）。

| 步骤 | 动作 |
|:--|:--|
| ②-1 注册表 | 删除 `market_value` 与 `category` 两个条目；新增 `holdings_detail`「持仓明细与分类」（`type=always`、`data_flag=None`，置于原 position 1/2 的顺序位） |
| ②-2 页签名表 | 删除两条，新增 `"holdings_detail": "持仓明细与分类"` |
| ②-3 Excel 写入器 | 新建 `report/holdings_detail_sheet.py::write_holdings_detail_sheet(ws, ...)`（吸收两表：区块①市值明细 15 列 + 分账户小计；区块②分类汇总）。**领域层不动**：`report/market_value.py`（`DetailRow`/`classify_holdings`/`_compute_premium` 等）与 `report/category.py`（`_categorize_holding`/`_tier_label`/`build_category_data_status`/`calc_yield_text`/`_load_dividend_data` 等）**保留不改名不删除**（被生产代码与 100+ 测试引用）；仅删除**纯章节写入器** `report/market_value_sheet.py`，并把 `category.py` 中的章节写入器 `write_category_sheet`/`_write_category_group` 迁入新模块后移除 |
| ②-4 Excel 分派 | `excel_generator.py` 与 `excel_content_sheets.py` 的 `sheets["market_value"]/["category"]` 三处改为 `sheets["holdings_detail"]` 一次调用 |
| ②-5 HTML | `report_template.html` 两个 `div.section` 合并为一个 `sec-holdings_detail`（`section_numbers['holdings_detail']`、标题「持仓明细与分类」，内含两区块小节标题）；删除旧锚点 |
| ②-6 命名统一检查 | `grep -rn "market_value\|sec-category" src/ docs-stm/` 仅允许命中历史 changelog / 归档；**`category` 与 `market_value` 存在合法残留**（Excel 列名「分类」「市值」等中文词、`category` 作为普通英文词、历史变更记录），按**标识符边界**检索并在提交信息中记录逐项判定 |
| ②-7 测试同步（**区分章节键与领域词**） | **受影响（章节键断言）**：`test_registry.py:250`（条目数 21 → 20）、`test_registry_edge.py`/`test_config_edge.py`（`report_section_order` 样本含 `market_value`/`category`）、`test_html_report_structure_edge.py:93`（HTML 容器数 21）、`test_html_report_structure.py`（导航分组与锚点）、`test_excel_report_structure.py`（section 列表含 `market_value`/`category`）、`test_report_chapter_consistency.py`（双端一致性夹具）、`test_scenario_section_order.py`、`test_config_edit.py`、`test_check_semantic_index.py`（合并章标识符）与各写入器单测（`test_market_value_sheet.py`/`test_category.py`/`test_category_edge.py` → 合并为 `test_holdings_detail_sheet.py`）。**不受影响（领域词）**：`market_value` 作为 **`DetailRow` 字段名 / 市值计算模块名** 出现在 100+ 个测试中（`test_market_value.py`、`test_liquidity*.py`、`test_rebalance*.py`、各场景测试等）——**不在改名范围**，实施时不得批量替换；`category` 作为「分类」领域词同理 |
| ②-8 文档同步 | `reports-instruction`（对照表/章节分组/可见性表）、`technical` §6.7 语义表与 §4.x 叙述、`how-to-config`（若涉及）、`folders` 树与统计、`changelog` |
| 验收 | 条目数 20；Excel 页签减少 1 个且内容等同（两表逐格比对用例）；HTML 章节减少 1 个；`--mode dev-verify` 全绿 |

## 5. 批次③ 施工单：`position_structure`（持仓结构与集中度）

| 步骤 | 动作 |
|:--|:--|
| ③-1 注册表 | 合并为 `position_structure`「持仓结构与集中度」（`type=fund_deep_analysis`，**`data_flag_any=("position_relationship_data","concentration_data")`**，`data_flag=None`） |
| ③-2 页签名表 | `"position_structure": "持仓结构与集中度"` |
| ③-3 Excel | 新建 `report/position_structure_sheet.py::write_position_structure_sheet`（吸收关系矩阵 + 集中度两张表）；删除 `position_relationship_sheet.py`、`fund_concentration_sheet.py` |
| ③-4 分派 | `excel_fund_deep_analysis.py:129/185` 两处合并为一次 `sheets.get("position_structure")` |
| ③-5 HTML | 两个 `div.section`（1563/1811）合并为 `sec-position_structure`；导航分组映射保持 `fund_deep` |
| ③-6 测试 | 增加**OR 可见性用例**：仅有 `position_relationship_data` 时页签/章节可见；两者皆无时隐藏；**两契约写入点不动** |
| 验收 | 条目数 19；OR 语义用例通过；两区块内容等同（逐表比对） |

## 6. 批次④ 施工单：`fundamental_snapshot` + 经理变更并入基金业绩

| 步骤 | 动作 |
|:--|:--|
| ④-1 注册表 | 两处合并：**①** `financial_report_digest`(#19) + `financial_indicator`(#20) → `fundamental_snapshot`「持仓基本面」（`type=financial_indicator` 语义化为 `type=fundamental_snapshot`；`data_flag_any=("financial_indicator_data","financial_report_digest_data")`）；**②删除 `fund_manager`(#6) 条目**——其「基金经理变更监控」区块并入 `fund_performance`(#5)，章节语义由此变为「基金业绩分析（含经理变更）」。`fund_performance` 条目本身的 key/name/number 规则按既有再编号逻辑处理 |
| ④-1b type 与 board 层链 | **两侧 `board_flags` 同步**：删除 `"financial_report"` 项、`"financial_indicator"` 改 `"fundamental_snapshot"`（`excel_sheet_factory.create_sheets` 与 `html_writer_nav._compute_section_visibility`）；**删除已不存在条目的 `enable_*` 形参**（`enable_financial_report_digest`，含 `html_writer`/`excel_generator`/`_report_generation` 三处调用链）；`config/_validation.py` 已知类型集合删旧增新；`web/config_edit.py` 硬编码处同步 |
| ④-2 页签名表 | 增 `"fundamental_snapshot": "持仓基本面"`；**删除 `"fund_manager": "基金经理变更监控"` 映射**；`fund_performance` 名称不变 |
| ④-3 Excel | 新建 `report/fundamental_snapshot_sheet.py::write_fundamental_snapshot_sheet`（区块①指标表 19 列 / 区块②摘要 9 列）；删除 `financial_indicator_sheet.py`、`financial_report_sheet.py`；经理变更区块并入 `fund_performance` 写入器（删除 `fund_manager_sheet.py`） |
| ④-4 HTML | 新建 `partials/fundamental_snapshot_section.html`（两区块，**区块级开关**：区块②需 `is_feature_enabled("financial_report_digest")` 且契约就绪）；删除两个旧 partial；`report_template.html` 的 `sec-fund_manager`(1499) 区块删除并并入 `sec-fund_performance`(1393)（区块级门禁 `is_enable_fund_deep_analysis()`） |
| ④-5 配置 | `_get_default_config_template()` 与 `data/config/config.json` **重生成**（新条目顺序/名称；`report_section_order` 按新条目） |
| ④-6 开关 | `features.py::GROUP_REPORT` 保留 `financial_indicator` 与 `financial_report_digest` 两个功能开关（各控一块）；`fundamental_snapshot` 章节级门禁 = 数据底座就绪（沿用既有 `datasink_feature_ready`） |
| ④-7 测试 | 区块级门禁用例两条（摘要区块随开关关闭消失 / 经理区块随 `enable_fund_deep_analysis=false` 消失且主业绩表保留）；**条目数 17**（④ 含两处合并：财报两章合一 -1、`fund_manager` 并入基金业绩 -1）；配置模板重生成后的一致性用例 |
| 验收 | **条目数 17**；页签名表不再含 `fund_manager`；`fund_performance` 章节内含经理变更区块；`--mode verify,regression` + 四个 `--ci` + 版本一致性 + ruff 全绿 |

## 6.4b 批次依赖与回退矩阵（第 7、8 轮复盘新增）

**依赖链**：①(可见性模型 OR，已完成，零行为) → ②(always 组两章，受众最广故先行) → ③(fund_deep_analysis 组两章) → ④(财报两章 + `fund_manager` 并入基金业绩)。③④ 均改 `_compute_section_visibility` 与 fund 深度分析分组，**④ 建立在 ③ 之后**。

| 共享文件（各批都要改） | ② | ③ | ④ |
|:--|:-:|:-:|:-:|
| `core/registry.py`（条目/type/data_flag） | ✓ | ✓ | ✓ |
| `report/excel_sheet_factory.py` + `html_writer_nav.py` | ✓ | ✓ | ✓ |
| `report/excel_generator.py` / `excel_content_sheets.py` / `excel_fund_deep_analysis.py` | ✓ | ✓ | ✓ |
| `report/excel_module_loader.py`（模块键） | ✓ | — | ✓ |
| `src/static/tmpl/report_template.html` | ✓ | ✓ | ✓ |
| `partials/*` | — | — | ✓ |
| `_get_default_config_template()` + `data/config/config.json` | ✓ | ✓ | ✓ |

**回退纪律**：因上述文件跨批共改，**回退必须逆序**（④→③→②），每批一次独立提交以便 `git revert` 单批；若需中断，可停在 ② 或 ③ 后（各批独立成章的中间态均可用）。

**版本身份**：四批同属 **0.11.1-dev** 开发期，逐批提交、逐批门禁，随该版本一并发布；若跨版本，发布前按"版本号一致"流程统一刷新条目数表述。

## 6.5 命名统一「允许保留的旧名」白名单（防误删）

| 类别 | 允许保留 | 理由 |
|:--|:--|:--|
| **契约键** | `position_relationship_data` / `concentration_data` / `manager_data` / `financial_indicator_data` / `financial_report_digest_data` | 契约描述数据内容而非章节；改名会污染契约台账的写入/消费语义 |
| **功能开关名** | `financial_indicator` / `financial_report_digest`（`GROUP_REPORT` 两项） | 开关名对应「数据能力」（指标 / 财报摘要），非章节名；两者仍各控合并章的一个区块 |
| **既有专有词** | `fin_indicator_` 缓存前缀、`financial_report` **数据源类别**（数据源说明表的 `financial_report` 类别 id，指 DataSinking 财报全文） | 分别属缓存注册表与数据源目录，与报告章节无关 |
| **历史记录** | `docs-stm/managements/changelog.md`、`docs-stm/archive/**` | 历史变更记录不改写 |

> 判定口径：**章节层**（注册表键 / 显示名 / 页签名 / HTML 锚点 / partial 名 / 写入器模块与函数）
> 一律新名；**数据与配置层**（契约键 / 功能开关名 / 缓存前缀 / 数据源类别）保持各自既有语义名。

## 6.6 复盘记录（十轮 —— 已完成）

| 轮次 | 主题 | 发现 | 处置 |
|:--|:--|:--|:--|
| 1 | 命名统一性（旧名残留 / 新旧名一致 / type 链） | 新名两文档一致；但 **type 语义化未在设计层写明**、`enable_*` 形参与 `board_flags` 映射链**两文档均未覆盖** | 设计层新增 §3.2「命名统一的下游影响清单」；施工单补 ④-1b 与命名检查白名单 |
| 2 | 架构约束符合性 | 核实代码侧接缝：两侧 `board_flags` 含旧 type、`_validation.py` 允许集合含旧 type、Web 硬编码含旧名；前端与 TUI 已同源派生（无需改） | 同上批量修复；白名单明确「可见性旗标的语义身份」三处必须严格一致 |
| 3 | 测试与守卫完备性 | **发现同名混淆**：`market_value`/`category` 在 100+ 测试中是**领域字段/领域模块**（`DetailRow.market_value`、`report/market_value.py`、`report/category.py` 的分类函数），而批次②原施工单写「删除 `report/category.py`」会**破坏领域层**；另发现 `test_features.py` 的 `fund_deep_analysis_fund_*` 字符串在 `src/` 无对应实现（需实施时核对语义） | 修正批次②（只迁移纯章节写入器、领域模块保留）；新增 §6.7「领域层 vs 章节层边界」；测试同步清单改为**区分章节键断言与领域词**并给出精确文件行 |
| 9 | 跨文档同步面与术语统一 | 同步面远大于计划所列：`technical.md`（含**两处陈旧「报告 19 个模块」**、功能语义命名表需新增三行）、`requirements.md`、`testplan.md`（§4 回归清单）、`folders.md`（**26 处 `financial_indicator` 需甄别**：fetcher/analysis 保留 vs report 章节改名）、`test-coverage.md`，以及 4 份用户文档（README / reports-instruction / how-to-config / faq） | 新增 §6.8「文档同步清单」（管理文档 / 用户文档 / 门禁脚本 / 纪律四类） |
| 10 | 文档自洽与命名索引关系 | 落地前需保证两文档咬合；`check-semantic-index.py` 正反向校验要求「先改表再改码」 | 新增 §6.9「文档自洽终检」（命名表逐字一致 / 条目数三处一致 / 术语无矛盾 / 未触碰生产代码） |
| 7 | 批次依赖与可回退性 | ②③④ 共改 7 个文件（registry/两侧可见性/Excel 三处分派/模板/配置模板），**无法任意顺序单独回退**；计划未说明依赖链与版本身份 | 新增 §6.4b「批次依赖与回退矩阵」（依赖链 + 共享文件表 + 逆序回退纪律 + 版本身份） |
| 8 | 计数一致性与非目标边界 | **硬伤**：④-3/④-4 删除 `fund_manager` 条目对应区块，但 ④-1 未声明删除该条目、④-7/验收仍写「条目数 18」——实际 ④ 含两处合并（财报两章 + 经理并入），应为 **17** | 修正 ④-1（显式删除 `fund_manager` 条目与页签名）、④-7/验收/§6.6b 计数 → 17；非目标边界（LLM 条目不合并）经核对与注册表现状一致，予以保留 |
| 5 | 接缝完整性（遗漏消费点） | 新增 4 处漏登接缝：`excel_module_loader.py`（模块键 `write_category_sheet`/`write_market_value_sheet` + 错误文案）、`html_writer_display.py`（**反向依赖** `market_value_sheet._weighted_avg_cost`，删模块会 ImportError）、partial 实况（仅 4 个 partial，**只有 M3 需并 partial**）、`chart_data_builder` 图键不变但图归属变；`features.py` 两开关名保留 | 接缝地图补 6 行；批次② 补 ②-4b/②-4c；批次④ 补 partial 实况；新增 §7.5 风险补充（3 条） |
| 6 | 守卫与可验证性 | 7 项既有守卫均在位；但**无守卫清单**、**缺合并前基线方法**、「三处严格一致」缺正面自动化守卫 | 新增 §6.6b：既有守卫表（含随批次变化处）+ 每批新增守卫（`test_section_type_flag_consistency` / 模块加载器一致性 / 区块门禁 / 内容等价）+ 基线方法（`docs-stm/tmp/` 快照，不入库） |
| 4 | 配置与校验面 | `_validation.py` 允许类型集合含旧 type、`config_edit.py` 硬编码含旧名（已列入 §3.2）；注册表 docstring「共 21 项」与架构约束表「报告 19 个模块」表述陈旧；`_config_defaults.py` 的 `report_section_order` 模板随注册表自动派生（无需手改） | 收尾步骤补「条目数表述同步」；确认模板无需手改 |

## 6.6b 守卫清单与基线方法（第 6 轮复盘新增）

**A. 既有守卫（每批必须保持绿，改前先跑基线）**

| 守卫 | 文件 | 随批次变化处 |
|:--|:--|:--|
| 注册表条目数 | `test_registry.py:250`（`== 21`） | ② -1 →20；③ -1 →19；④ **-2** →**17**（财报两章合一 + `fund_manager` 并入基金业绩） |
| HTML 容器数 | `test_html_report_structure_edge.py:93` | 每批 -1 |
| Excel 章节列表 | `test_excel_report_structure.py` | 每批 -1 |
| 双端一致性 | `test_report_chapter_consistency.py` | 夹具键名与开关参数 |
| 配置样本 | `test_registry_edge.py` / `test_config_edge.py` | `report_section_order` 样本 |
| 场景顺序 | `test_scenario_section_order.py` | 键集合断言 |
| 语义命名表 | `test_check_semantic_index.py` | 合并章标识符行 |
| 可见性 OR 语义 | `test_section_visibility.py`（批次①已建） | 无需改（表述层无章节名） |

**B. 每批新增守卫**

| 批次 | 新增守卫 | 断言 |
|:--|:--|:--|
| ② | `test_section_type_flag_consistency` | 遍历注册表 `type`，断言每类型在 `_validation.py` 允许集合与两侧 `board_flags` 键中**同时存在**（第 1、2 轮「三处严格一致」的**正面自动化守卫**，防旧 type 残留/新 type 漏配） |
| ② | 模块加载器一致性 | `excel_module_loader` 装配键集合 == Excel 分派实际调用的写入器键集合 |
| ③ | 区块门禁 | 功能开关关 → 分节块不写；开 → 写（③ 的集中度块；④ 的两开关各控一块） |
| ②③④ | 内容等价 | 最小持仓（3 品种）跑 Excel，两个被并区块的**标题/列头/行数/数值**与基线逐一相等 |

**C. 基线方法（可执行的等价性验证）**

1. **批前**：在**批次② 开工前**用固定最小持仓（3 品种，含一个基金、一个 QDII、一个现金=0 边界）跑一次报告，把 Excel/HTML 产物存入 `docs-stm/tmp/baseline-<批次>/`（**运行时临时产物，不入库**），并记录两区块的「标题 / 列头 / 数据行」快照。
2. **批后**：同夹具重跑，按快照逐项比对；差异必须能解释为「合并本身」（如标题、锚点、列顺序），**数据行数值差异视为回归**。
3. **不可依赖人工肉眼**：上述比对落成单测（用 mock 数据构造，断言写出的单元格矩阵），基线快照仅作交叉核对。

## 6.7 领域层 vs 章节层边界（第 3、4 轮复盘新增）

| 层 | 模块/命名 | 是否随章节合并改名 |
|:--|:--|:--|
| **章节层** | 注册表键 / 显示名 / 页签名 / HTML 锚点与 partial / **纯章节写入器**（`market_value_sheet.py::write_market_value_sheet`、`category.py::write_category_sheet`、`position_relationship_sheet.py`、`fund_concentration_sheet.py`、`fund_manager_sheet.py`、`financial_indicator_sheet.py`、`financial_report_sheet.py`） | **改名/迁移**（新名见 §1 总表） |
| **领域层** | `report/market_value.py`（`DetailRow`/`classify_holdings`/`_compute_premium`/`is_market_open`）、`report/category.py`（`_categorize_holding`/`_tier_label`/`build_category_data_status`/`calc_yield_text`）、`analysis/*` 的 `market_value` 字段 | **保留**——领域概念（市值/分类）与报告章节同词不同义；批量替换会破坏 100+ 处生产与测试引用 |
| **缓存类型域** | `core/registry.py::get_exact_type_map()` 的 `fund_manager_snapshot`/`fund_concentration_snapshot`（缓存 data_type 精确映射） | **不改**——它映射的是**缓存类型**（快照缓存），与报告章节无关；合并后这两个数据能力不变 |

## 6.8 文档同步清单（第 9 轮复盘新增，每批收尾必查）

**A. 管理文档**

| 文档 | 同步点 |
|:--|:--|
| `technical.md` | 章节名与条目数表述（**两处陈旧的「报告 19 个模块」→ 新条目数**；「报告模块注册表约束」条目中的模块数表述）；**「功能语义命名表」新增三行**（`holdings_detail` / `position_structure` / `fundamental_snapshot`），且必须**先改表再改码** |
| `requirements.md` | 相关功能条目中的章节名（本仓 `market_value`/`category`/`financial_indicator` 等命中处） |
| `testplan.md` | §4 回归清单新增「章节合并后逐表/逐区块比对」项 |
| `folders.md` | 目录树增删 report 模块（新增 `holdings_detail_sheet.py`/`position_structure_sheet.py`/`fundamental_snapshot_sheet.py`，删除被并方）+ 统计表刷新；**必须区分** fetcher/analysis 的 `financial_indicator*`（**保留**）与 report 章节模块（改名/删除） |
| `test-coverage.md` | 测试文件重命名后的计数刷新（收尾跑 `collect-test-coverage.py`） |

**B. 用户文档**（章节清单直接面向用户，全部需同步）

- `README.md`（章节清单）、`manuals/reports-instruction.md`（各章节表格与说明）、`manuals/how-to-config.md`（`report_section_order` 示例与章节表）、`manuals/faq.md`（章节名出现处）

**C. 门禁脚本与索引**

- `scripts/check-semantic-index.py` 依赖 `technical.md` 的「功能语义命名表」做正/反向一致校验 → 表与代码必须同步落地（先表后码）
- `src/test/unit/scripts/test_check_semantic_index.py` 的合并章标识符断言需随新名更新
- `src/test/unit/core/test_registry.py:250` 的条目数断言（每批 -1；④ -2）

**D. 纪律**

- 用户文档与管理文档一律使用**新显示名**；历史 `changelog.md` 与 `archive/**` **不改写**
- 每批提交前跑：`.venv/bin/python scripts/check-doc-traces.py --ci`（防陈旧表述）与 `check-semantic-index.py --ci`

## 6.9 文档自洽终检（第 10 轮复盘）

十轮复盘的收尾动作——两文档落地前互相咬合：

| 检查项 | 要求 |
|:--|:--|
| 两张命名表 | 设计层 §1 与实施层 §1 的新/旧名映射**逐字一致** |
| 批次编号与条目数 | 施工单（②③④）、守卫表 §6.6b、各批「验收」行的条目数与页签/章节增减**三处一致**（21→20→19→17） |
| 「共 N 项」表述 | `registry.py` docstring、`technical.md` 的注册表约束条目、`test_registry.py:250` 断言**三处一致**（收尾步骤已列） |
| 分层面术语 | §6.5（可保留旧名白名单）与 §6.7（领域层/章节层/缓存类型域）**无矛盾**；契约键在两表中口径一致 |
| 回溯性 | 每个「整改」仅改写计划文档，**未触碰任何生产代码**（四批实施另起提交） |

## 7. 收尾（每批之后 + 全部完成后）

- 每批：`--mode dev-verify` + 四个 `--ci` + `ruff check`/`format` + `check-version-consistency`；命名统一 grep 检查；`folders`/`test-coverage` 统计刷新。
- 全部完成后：`--mode verify,regression`；`reports-instruction` 三处目录/可见性表与 `technical` §6.7/附录 H 复核；`changelog` 汇总一条迭代记录。
- **条目数表述同步**（第 4 轮发现）：`core/registry.py` 的注册表 docstring「共 N 项」、`technical.md` 架构约束表中「报告 N 个模块」的表述、`how-to-config` 与 `reports-instruction` 的模块计数，必须与新条目数一致（防文档漂移）。
- **不做**：不做配置兼容迁移；不引入契约层改名；不合并 LLM 相关条目（见设计层非目标）。

## 7.5 风险补充（第 5 轮发现）

- **`_weighted_avg_cost` 迁移致渲染链 ImportError**：`html_writer_display.py` 反向导入章节写入器模块内的计算函数——迁移时若只删模块不搬函数，HTML 显示层直接崩。**处置**：迁移前先跑 `.venv/bin/python -m pytest src/test/unit/report/test_html_writer.py -v` 建立基线，迁移后必须仍绿。
- **`excel_module_loader` 模块键与分派调用不同步**：该 loader 用字符串键装配模块，改名遗漏会在 **Excel 生成期**才报「模块缺失」而非导入期。**处置**：批次② 收尾用 `grep -rn "write_category_sheet\|write_market_value_sheet" src/` 确认零命中。
- **图表归属变化而图注未改**：`category_doughnut` 图随合并章移动，图下说明文案若写「分类表」需同步为合并章语义。

## 8. 风险与回退

| 风险 | 缓解 |
|:--|:--|
| 合并后内容遗漏（少搬一张表/一个区块） | 每批以「合并前双端产物」为基准做逐表比对用例（列标题 + 行数 + 关键值） |
| 可见性 OR 语义误判导致空章节 | 悲观判定（未登记视为未就绪）+ 批次③ 专项用例 |
| 区块级门禁漏判导致关闭后仍渲染 | 批次④ 两条专项用例 + 模板侧 `section_visible`/开关双判定 |
| 命名残留（旧键/旧锚点/旧 partial） | 每批强制 grep 检查（仅允许历史 changelog 与归档命中） |
| 中途需要回退 | 每批一次提交，可单独 `git revert`；批次①（模型）与条目变更解耦 |
