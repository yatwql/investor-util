# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-09（D-10 审查：数据降级重构 6 维复盘，新增 R-188~R-191）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|
| 2026-07-08 | D-9 审查：代码健康检查（R-180~R-187） | 新增 4 项，R-180/R-184/R-185/R-186 已修复 |
| 2026-07-08 | v0.3.1 conftest 增强 + config.py 拆包 + 动态年份 | R-185/R-186 已修复，config 文档同步 |
| 2026-07-08 | D-8b 全面审查：代码质量/并发安全/工程化 | 已完成（全部修复） |
| 2026-07-08 | D-8c 审查：v0.3.0 代码健康度检查（R-177~R-183） | 已完成（全部修复） |
| 2026-07-09 | **D-10 审查：数据降级重构 6 维复盘（Step A~E）** | 新增 5 项 |

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
| R-188 | **eastmoney_industry.py 局部熔断器未迁移到 DataSourceRegistry**：`_PUSH2_CIRCUIT_OPEN`等 6 个全局变量 + `_circuit_breaker_record_failure/reset` 与注册表独立运行，异常被局部 CB 捕获后未传播到 registry.is_chain_broken，industry 链熔断预检失效 | `providers/eastmoney_industry.py` | 本重构最严重遗留问题；局部 CB 无锁保护，多线程不安全 |

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-189 | **market_value.py 调用 DataSourceRegistry 私有方法 `_fetch_cached_only()`**：前导下划线表明实现细节，非公共 API，模块边界泄漏 | `report/market_value.py` | 建议改为公共方法或改用 `fetch_or_cached` |
| R-190 | **哨兵 `_TRANSPORT_FAILURE` 重复定义**：`provider_registry.py` 和 `chain.py` 各有一套，后者 unused | `provider_registry.py` + `chain.py` | 应统一至一处 |
| R-191 | **`test_eviction_order` 未实际触发淘汰**：写入 100 条/阈值 2000，断言永远为真，不能验证淘汰逻辑 | `test_provider_registry.py` | `fetch_or_cached` 和 `_fetch_cached_only` 无单元覆盖 |

### ✅ 近期已修复

| # | 问题 | 修复说明 |
|:-:|:-----|:---------|
| R-185 | **预测年份 `2026E` 硬编码 → 动态计算**：穿透表列名「预测EPS(2026E)」从 `datetime.now().year` 获取当前年份，跨年自动更新。涉及 `penetration_sheet.py`（_HEADERS + _num_formats 注释）、`penetration.py`（docstring）、`report_template.html`（Jinja2 `{{ report_year }}`）、`html_writer.py`（render 传参）4 个文件 | 2026-07-08 修复，`# 8` 列注释同时更新。下一日历年度（2027-01-01）起报告自动显示 2027E |
| R-186 | **`llm_settings.json` 定价段与 `constants.py` 重复 → 单一来源**：`constants.py MODEL_PRICING` 声明为唯一默认定价源，`config/_core.py` 中的 llm_settings 模板移除型号示例注释，改为指导性说明（"仅用于覆盖 constants.py"）。`pricing.py` 的 `_reload_pricing()` 合并逻辑不变 | 2026-07-08 消歧。新增模型在 `constants.py` 中添加，无需修改 `llm_settings.json` |
| R-180 | **`type: ignore` 累计 22 处 → 4 处**：系统性清理 13 个文件的 `type: ignore` 注释 | 剩余 4 处均为 `tui.py` 平台特定 `termios[attr-defined]`（Linux 专用，已加 try/except 保护 Windows），属合理保留 |
| R-179 | **`config.py` 817 行**：混合配置加载/校验/LLM 配置/JSON 注释剥离，30+ 模块导入 → v0.3.1 已拆为 `config/` 子包（`_defaults.py`/`_comments.py`/`_core.py`），原 `config.py` 删除 | 2026-07-08 完成重构，原 `D src/python/config.py` 已验证删除，新 `config/` 子包正常运转 |
| R-184 | **`_get_industry_avg_pe()` 空实现 → 完整实现**：接入 push2 API（f127 行业归属 + f9 PE），按行业中位数聚合作为估值基准，三级降级（push2→Tencent→代码前缀）兼容原 `return {}` 退化路径 | 同步编写 10 个测试覆盖：同行业/跨行业/全失败/部分失败/空列表/偶数中位数/负 PE 跳过/非 A 股跳过/`_ext_memo` 填充/集成验证 |
