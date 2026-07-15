# R-178 `html_writer.py` 分拆迭代计划（V5）

> 创建：2026-07-09 | 更新：2026-07-09 | 状态：**五轮内审完成**，待执行
>
> 五轮审审核对 13 条设计约束（C1-C13 全部合规；新增 C14 由本计划引入）和 13 处修正（详见 §13）。
> **本轮重点**：technical.md 同步纳入计划、Step 4 保守化、grep 范围标准化、3 项技术债务补录。
>
> **核心理念**：Step 1-3 纯提取（不改变逻辑），Step PF 修复隐式状态污染，Step 4-5 重构编排器。
> 每步要么是纯搬迁，要么有保护网兜底。

## 1. 动机与目标

`html_writer.py` 当前 996 行（全源码第一），混合 5 重职责：

| 职责 | 行数 | 占比 |
|:----|:----:|:----:|
| 文件 I/O（_save_html_report） | 37 | 3.7% |
| Jinja2 环境（过滤器 + _ENV） | 108 | 10.8% |
| 内容渲染（14 × _render_*） | 463 | 46.5% |
| LLM 模块状态（_build_module_info_list 等） | 94 | 9.4% |
| **核心编排**（write_html_report） | **160** | **16.1%** |
| 辅助 + 导览 + 注释 + 间距 | ~134 | 13.5% |

**端状态**：

```
html_writer.py        ~140 行   编排器 + 4 个模块级辅助函数
html_jinja_env.py     ~110 行   Jinja2 _ENV + 8 过滤器 + section_visible fallback
html_renderers.py     ~520 行   14 × _render_* + LLM 模块信息函数
html_save.py           ~40 行   _save_html_report 文件写入 + 归档
```

依赖方向（单向无环）：
```
html_writer.py
  ├─→ html_jinja_env.py     (import _ENV)
  ├─→ html_renderers.py      (import 14 渲染函数)
  └─→ html_save.py            (import _save_html_report)
```

## 2. 全局设计约束（跨步强制执行）

| # | 约束 | 来源 | 说明 |
|:-:|:-----|:-----|:------|
| D1 | 每步门禁：`regression` | CLAUDE.md P0 | 通过方得提交 |
| D2 | 目录树同步 | CLAUDE.md | 每步新增文件后更新 `datasource-and-folders.md` |
| D3 | Backward compat 零残留 | 本计划 | Step 5 清理全部桥接，grep 确认无外部引用 |
| D4 | 新增测试必须标 marker | C11 | 快照测试标 `@pytest.mark.unit_report` |
| D5 | 模板零修改 | 本计划 | 所有变更通过 Python 侧透传 context 完成 |
| D6 | C7 注册表链路不变 | technical.md | 任何步骤不得硬编码报告序号 |
| D7 | 条件路径的 lazy import 保留 | 本计划 | news/LLM 禁用时不应触发模块级 import |
| D8 | **C14 渲染期全局变量禁令** | 本计划（新增） | 任何步骤不得写入 `_ENV.globals` 或其他模块级全局变量传递渲染期数据 |

## 3. 执行顺序

```
Step 1 ─→ Step 2 ─→ [Step PF] ─→ Step 3 ─→ Step 4 ─→ Step 5
(IO外迁)  (Jinja2)   (修复_ENV  (渲染器   (编排器    (清理)
                      globals)   全迁移)   简化)
```

**Step PF 放在 Step 2 之后**：Step 2 先把 `_ENV` 和过滤器搬到 `html_jinja_env.py`，PF 再修改 `html_jinja_env.py` 的注册逻辑和 `html_writer.py` 的调用逻辑。此时代码已在最终位置，无二次移动风险。

---

## 4. Step 1：文件 I/O → `html_save.py`

**纯机械搬迁，37 行，零测试影响。**

| 项 | 内容 |
|:---|:------|
| 范围 | `_save_html_report()` L958-L994，37 行 |
| 依赖 | `excel_writer._cleanup_old_archives`, `excel_writer._ensure_reports_dir` |
| 桥接 | `html_writer.py` 末尾加 `from src.python.report.html_save import _save_html_report` |
| 测试 | 0 处改动（未被任何测试直接 import）|
| 同步 | `datasource-and-folders.md` 目录树 |
| 风险 | ★☆☆☆☆ — 纯搬迁，无逻辑变更，无测试改 |
| 恢复 | 删 `html_save.py` + 删桥接行，< 2min |

**度量**：`html_writer` 996 → **959** 行；`html_save.py` 40 行

---

## 5. Step 2：Jinja2 环境 → `html_jinja_env.py`

**过滤器是纯函数，提取后无行为变化。**

| 项 | 内容 |
|:---|:------|
| 范围 | 8 个 `_jinja_*` 过滤器 L90-L166（77 行）+ `_jinja_section_visible` L169-L183（15 行）+ `_ENV` L81-L84 + 注册 L187-L197 + 路径 L79-L84 = ~108 行 |
| 移入的 import | `is_qdii_extended`(`code_utils`)，`Environment`/`FileSystemLoader`(`jinja2`)，`os`，`logging`，`Any` |
| 桥接 | `html_writer.py` 加 `from src.python.report.html_jinja_env import _ENV` |
| 测试改动 | **10 处**：`test_security_edge.py`(5×`_ENV`) + `test_html_report_structure.py`(1×`_ENV`) + `test_scenario_holdings_quality.py`(4×filter) |
| 风险 | ★★☆☆☆ — 10 处需同步，均为可 grep 的机械替换 |
| 恢复 | 删除新文件 + 恢复测试 |

**重要**：Step 2 的注册行为完全不变——`_ENV.globals["section_visible"] = _jinja_section_visible` 原样保留在 `html_jinja_env.py`。Step PF 才会修改注册逻辑。

**度量**：`html_writer` 959 → **851** 行；`html_jinja_env.py` 110 行；10 处测试 import 更新

---

## 6. Step PF：修复 `_ENV.globals` 运行时变异 ⚡

**先决条件**：Step 2 已完成（`_ENV` 已在 `html_jinja_env.py` 中）。

### 6.1 问题

`write_html_report` 在 L319（现位于 `html_writer.py`）执行：
```python
_ENV.globals["section_visible_dict"] = section_visible_dict
```

而 `_jinja_section_visible()`（现位于 `html_jinja_env.py`）从 globals 读取 `section_visible_dict`。渲染期数据通过 globals 传递，这是模块级全局变量的运行时状态污染。

### 6.2 修复措施

| 操作 | 文件 | 说明 |
|:-----|:-----|:------|
| 注册默认 fallback | `html_jinja_env.py` L197 | 将 `_ENV.globals["section_visible"]` 改为 `lambda key: False`（fail-closed） |
| 创建渲染闭包 | `html_writer.py` write_html_report 内 | `sv_fn = lambda key, _d=section_visible_dict: bool(_d.get(key, False))` |
| 透传 context | `html_writer.py` render() 调用 | 在 render 参数中传入 `section_visible=sv_fn` |
| 删除全局写入 | `html_writer.py` L319 | 删除 `_ENV.globals["section_visible_dict"] = ...` |
| 同步 `technical.md` | `technical.md` L535-L537 | 将"该函数读取 `_ENV.globals['section_visible_dict']`"更新为"通过 render context 变量传递，不再写入 `_ENV.globals`" |

**grep 确认无残留**：在修改前后各 grep 一次 `_ENV\.globals\[` 全代码库 `src/ + test/`，确认只有 `html_jinja_env.py` 一处注册 L197（后改为 fallback）和 `html_writer.py` 一处写入 L319（后删除）。**不应有其他文件直接写入 `_ENV.globals`**。

**Jinja2 解析顺序**：context 变量 > globals > builtins。模板中 `{{ section_visible("key") }}` 调用格式不变，context 变量自动覆盖 globals，**模板零修改**。

### 6.3 `_jinja_section_visible` 函数的未来状态

| 用途 | 状态 |
|:-----|:------|
| 模板调用 | 不再使用（被 context 变量覆盖）|
| 测试导入 | **兼容性中断** — 详见 6.4 |
| HTML 报告导航 | `html_jinja_env.py` 中保留（向后兼容 import）|

### 6.4 测试影响

`test_html_writer.py:TestJinjaFiltersAndFunctions.setUp()`（L758-L764）：
```python
from src.python.report.html_writer import _jinja_section_visible, _ENV
self.env.globals["section_visible"] = _jinja_section_visible
self._module_env.globals["section_visible_dict"] = {}  # ← 依赖于 globals
```

**问题**：该测试将 `_jinja_section_visible` 注册到测试 `self.env` 的 globals，并用 `section_visible_dict` 填充其只读字典。PF 后 `_jinja_section_visible` 读取 `_ENV.globals.get("section_visible_dict", {})` 将返回空字典，`index()` 调用返回 `False`。

**修复**：PF 中同时修改该测试——保留 `_ENV` 引用，但在测试中为 `self._module_env.globals["section_visible_dict"]` 插入一个非空字典（或直接 mock `_jinja_section_visible` 返回值）。具体修改方案详见该步骤的实现。

| 分布 | 改动量 |
|:-----|:------:|
| `test_html_writer.py` | 1 处（setUp 中补充 section_visible_dict 注入逻辑）|

### 6.5 验证方法

```python
# 在 write_html_report 相关测试中追加
_ENV.globals.get("section_visible")  # 应为 callable（lambda key: False）
"section_visible_dict" not in _ENV.globals  # 确保无残留全局写入
```

### 6.6 失败模式

| 场景 | 表现 | 严重 | 恢复 |
|:-----|:-----|:----:|:-----|
| 模板仍走 globals | `section_visible` 回退到 `lambda: False`，全部隐藏 | 中 | 检查 context 参数传递 |
| context 变量未覆盖 globals | 同上 | 低 | 确认 Jinja2 版本 ≥ 3.x |
| setUp 测试未同步 | `TestJinjaFiltersAndFunctions.setUp` 断言失败 | 中 | 补充 section_visible_dict 注入 |

**门禁**：
```bash
pytest src/test/unit/report/test_html_writer.py -x -v --no-header
python scripts/test_runner.py --mode regression
```

### 6.7 度量

`html_writer.py` 行数不变（851 行）。全局状态污染消除。1 处测试 setUp 微调。

---

## 7. Step 3：渲染器全迁移 → `html_renderers.py` ⚡⚡

**最大单步。迁移 17 个函数 + 40 处测试 import。**

| 项 | 内容 |
|:---|:------|
| 范围 | 14 个 `_render_*` 函数 L393-L857（463 行）+ `_build_module_info_list` L860-L917（58 行）+ `_render_llm_module_info` L920-L955（36 行）。**不含** `_time_strings` 和 `_safe_build_data_status`（仅编排器用）|
| 移入的顶层 import | 原顶部约 25 行 import |
| Lazy import **保留为 lazy** | `llm.generate_all_llm`、`akshare_extras.get_sector_fund_flow`（LLM 禁用时不加载）、`news_correlation.build_news_data`（新闻禁用时不加载）|
| Lazy import **提升为顶层** | `code_utils.is_a_share_code`（轻量）、`akshare_extras.get_profit_forecast`、`akshare_extras.get_dividend_data`、`llm.FAIL_REASON_*` 6 常量（轻量常量）|
| 桥接 | `html_writer.py` 加 `from src.python.report.html_renderers import <14 个 _render_* + _render_llm_module_info>` |
| 测试改动 | **40 处**：|
| | → `test_llm_scenarios.py`：24×`_build_module_info_list` + 4×`_render_llm_module_info` = 26 |
| | → `test_html_writer.py`：7×`_build_module_info_list` + 2×`_render_llm_module_info` = 9 |
| | → `test_html_writer_edge.py`：4×`_render_penetration_section` = 4 |
| | → `test_llm_placeholder.py`：1×`_build_module_info_list` = 1 |

### 三阶段策略

```
Phase A: 建 html_renderers.py + 桥接         → 验证: pytest 收集期 + 1 个测试成功
Phase B: 批量替换 40 处测试 import            → 验证: --mode regression 277 项成功
Phase C: 删除不再被外部引用的桥接             → 验证: grep 全代码库 `src/ + test/` 确认
                                                            只有预期文件引用新模块路径
```

**Phase C 可安全删除的桥接**（`write_html_report` 不直接调用，仅测试导入）：
- `_build_module_info_list`（被 25+ 测试导入，但 `write_html_report` 只调用 `_render_llm_module_info`，后者内部调用 `_build_module_info_list`）

**Phase C 必须保留的桥接**（`write_html_report` 直接调用）：
- 所有 14 个 `_render_*` 函数
- `_render_llm_module_info`

### 失败模式

| Phase | 场景 | 严重 | 恢复 |
|:------|:-----|:----:|:-----|
| A | 漏迁 import → 编译错误 | 高 | 补 import |
| A | lazy import 被错误提升 → 模块 import 时报错 | 高 | 恢复为 lazy |
| B | 批量 sed 改错非目标文件 | 中 | `git checkout src/test/` |
| B | 某处遗漏（共 40 处）→ regression 失败 | 中 | grep 补改 |
| C | 误删 `write_html_report` 需要的函数 | 高 | 加回桥接 |

### 度量

`html_writer` 851 → **~267** 行；`html_renderers.py` ~520 行；40 处测试 import 更新

---

## 8. Step 4：编排器精简 + HTML 结构快照

**此时 `html_writer.py` 只剩 ~267 行。**

### 8.1 Phase A：HTML 结构快照保护网

```python
@pytest.mark.unit_report
def test_html_report_contains_expected_sections(mocker, tmp_path, sample_holdings):
    """HTML 报告包含所有预期 core section 标记。保护网：防止编排器重构破坏结构。"""
    path = write_html_report(sample_holdings, output_dir=str(tmp_path))
    html = (tmp_path / "个人投资分析报告.html").read_text(encoding="utf-8")
    # C7 确认：序号通过注册表驱动
    assert "section_order" in html or "section_numbers" in html
    # 核心 section — 这些始终存在
    assert 'id="sec-market_value"' in html
    assert 'id="sec-accounts"' in html
    # 不强制断言 B 系列（data_flag 控制可见性）
```

### 8.2 Phase B：精简 `write_html_report`（160 → ~125 行）

仅提取低风险的纯辅助函数，不改变 render() 调用模式：

| 措施 | 提取为 | 减少行数 | 风险 |
|:-----|:-------|:--------:|:----:|
| 4 个 data_status 构建 | `_build_data_status_sections(...)` | -12 | ★☆☆☆☆ 纯提取 |
| section_visible_dict 逻辑 | `_compute_section_visibility(order, raw_data_flags)` | -15 | ★☆☆☆☆ 纯提取 |
| `get_section_order()` | 保持显式调用 | 0 | C7 约束 |

**不做的操作**：模板变量分组合并（60→35 行）——`render(**group1, **group2)` 在 Python 中不可类型检查，变量名拼错致静默空值风险大于收益。保留显式命名参数以便代码审查。

### 8.3 不改变的外部契约

```
签名 → 不变
返回路径 → 不变
异常传播 → 不变
handlers_report.py 3 个调用点的异常处理 → 不变
C7 注册表链路 → 通过 get_report_section_order() 显式调用
```

### 度量

`write_html_report` 160 → **~125** 行；新增快照测试 ~20 行；`html_writer` ~267 → **~240** 行

---

## 9. Step 5：全局清理

| 操作 | 验证 |
|:-----|:------|
| 删除无外部引用的桥接 import | grep 确认 `write_html_report` 是唯一被外部引用的导出 |
| 目录树最终同步（3 个新文件各 1 行）| `datasource-and-folders.md` |
| 全量验证 | `python scripts/test_runner.py --mode verify`（1057 项，~5min）|
| marker 验证 | 快照测试标注 `@pytest.mark.unit_report` |

### 终态 `html_writer.py` 内容预期

```
# 导入（~8 行）
from src.python.report.html_jinja_env import _ENV
from src.python.report.html_renderers import (
    _render_market_value_section, _render_account_grouping, ..., _render_llm_module_info,
)
from src.python.report.html_save import _save_html_report

# 模块级函数（~60 行）
_time_strings()                        # 7 行
_safe_build_data_status()              # 20 行
_build_data_status_sections()          # ~20 行（Step 4 新增）
_compute_section_visibility()          # ~15 行（Step 4 新增）

# 核心入口（~85 行）
write_html_report(...)                 # ~85 行（保留显式命名参数）

合计：~140 行
```

### 度量

`html_writer` ~240 → **~140 行**；全量 verify 零失败

---

## 10. 终态文件对比

| 文件 | 职责 | 行数 | 外部 import |
|:-----|:-----|:----:|:-----------|
| `html_writer.py` | 编排器 + 4 个辅助函数 | ~140 | 3 个子模块 + 少量基础设施 |
| `html_jinja_env.py` | 过滤器 + _ENV + fallback | ~110 | `code_utils`, `jinja2`, `os`, `logging` |
| `html_renderers.py` | 14 渲染器 + LLM 信息 | ~520 | 原全部顶层 import，条件路径保留 lazy |
| `html_save.py` | I/O 写入 + 归档 | ~40 | `excel_writer`, `os` |

---

## 11. 累积度量总表

| 步骤 | `html_writer.py` | 新增文件 | 测试改动 | 门禁 | 累计风险 |
|:----:|:----------------:|:--------:|:--------:|:----:|:--------:|
| Step 1 | 959 行 | `html_save.py` 40 行 | 0 | regression | ★☆☆☆☆ |
| Step 2 | 851 行 | `html_jinja_env.py` 110 行 | 10 | regression | ★★☆☆☆ |
| Step PF | 851 行 | — | **1**（setUp 同步）| regression | ★★☆☆☆ |
| Step 3 | **267 行** | `html_renderers.py` 520 行 | **40** | regression×3 | ★★★☆☆ |
| Step 4 | ~240 行 | — | +20 行测试 | regression | ★★☆☆☆ |
| Step 5 | **~140 行** | — | — | **verify** | ★☆☆☆☆ |
| **终态** | **~140 行** | **3 文件 ~670 行** | **~51 处** | — | — |

---

## 12. 完整 FMEA 汇总

| 步骤 | 失败场景 | 根因 | 检测 | 效应 | 严重 | 概率 | 恢复 |
|:----:|:---------|:-----|:-----|:-----|:----:|:----:|:-----|
| S1 | ImportError | 桥接路径写错 | 收集期报错 | 模块不可用 | 高 | 低 | 删+修 |
| S2 | 测试漏改 | grep 遗漏 | regression 失败 | 1 个测试失败 | 中 | 中 | 补改 |
| PF | `section_visible` 回退到 False | context 未正确传递 | 快照测试 | 全部隐藏 | 中 | 低 | git checkout |
| PF | setUp 测试破 | 未同步 `_jinja_section_visible` 行为变化 | UT 失败 | 1 个测试失败 | 中 | 低 | 补充注入 |
| S3A | 漏迁 import | 搬动时遗漏 | 收集期报错 | 模块不可用 | 高 | 低 | 补 import |
| S3B | sed 改错 | 匹配过宽 | regression 失败 | 多测试失败 | 中 | 低 | git checkout |
| S3C | 误删必要桥接 | grep 漏检 | 运行时 NameError | 渲染崩溃 | 高 | 低 | 加回 |
| S4 | v_dict 错位 | 重构引入 bug | 快照测试 | section 不可见 | 中 | 中 | git checkout |
| S5 | 桥接删除还有引用 | grep 漏检 | verify 失败 | 构建失败 | 高 | 低 | 加回 |

---

## 13. 四轮内审变更记录

### V1 → V2（第一次，已验证实现）

| # | 问题 | 修复 |
|:-:|:-----|:-----|
| ① | 新文件命名冲突 | `html_renderers.py` |
| ② | `_time_strings`/`_safe_build_data_status` 不应迁出 | 保留 |
| ③ | `_ENV.globals` 修复缺 fallback | 补充 |
| ④ | `test_scenario_holdings_quality.py` 4 处遗漏 | 补充 |
| ⑤ | 目录树同步未纳入检查 | D2 约束 |
| ⑥ | C7 未显式确认 | Step 4 确认 |
| ⑦ | 快照测试模糊 | 具体断言 |
| ⑧ | 无 FMEA | §12 表格 |
| ⑨ | 渗透表债务无期限 | §14 治理建议 |
| ⑩ | 模板兼容性未说清 | Jinja2 context 机制详解 |

### V2 → V3（第二次，代码交叉验证）

| # | 问题 | 修复 |
|:-:|:-----|:-----|
| ⑪ | Step 顺序错误 | 渲染器迁移 → 再精简编排器 |
| ⑫ | fallback 取值反了（True→False）| fail-closed |
| ⑬ | lazy import 提升规则粗糙 | 保留 3 个条件路径 |
| ⑭ | C4 违规严重度虚增 | 实为文件缓存命中 |
| ⑮ | 缺 globals 测试断言 | 补充 |
| ⑯ | fetch_fund_holdings 冗余调用 | 文件缓存命中，不违规 |

### V3 → V4（第三次，设计约束+代码实况深度审计）

| # | 问题 | 发现方法 | 修复 |
|:-:|:-----|:---------|:-----|
| ⑰ | **PF 时序错误**：先做 PF 再 Step 2 导致 `_ENV` 要搬两次 | 内审 | → PF 移至 Step 2 **之后**（§3）|
| ⑱ | **测试 import 计数 29→40**：`test_llm_scenarios.py` 实际 26 处（不是 22+3）| 代码脚本统计（§7）| → 修正数字 |
| ⑲ | **Step 5 目标 ~120 太紧**：含 4 个辅助函数 ~60 行 + 入口 ~60 行 + import ~8 行 + docstring ~10 行 ≈ 140 | 行数模拟 | → 修正为 ~140（§9）|
| ⑳ | **`_jinja_section_visible` 测试兼容性中断未覆盖**：`TestJinjaFiltersAndFunctions.setUp` 依赖 globals 写入的 `section_visible_dict`，PF 后为空 | 代码审查（§6.4）| → PF 步骤中同步修改 setUp |
| ㉑ | **Step 3 Phase C "不再被外部引用"定义模糊**：哪些桥接可删、哪些必须保留没说清 | 内审 | → 列出明确清单（§7 Phase C）|
| ㉒ | **模板 `section_visible` 调用 9→8 处**（导航 1 + section 7） | grep 计数 | → 微调，不影响方案 |
| ㉓ | **`_ENV.globals` 两处写入的耦合关系**：L197 注册 + L319 赋值，PF 必须同时处理两者 | 内审 | → 明确 PF 改动范围（§6.2 表格）|

### V4 → V5（第四轮，设计约束+代码实况对抗审查）

| # | 问题 | 发现方法 | 修复 |
|:-:|:-----|:---------|:-----|
| ㉔ | **`technical.md` L537 文档过时**：描述了 `_ENV.globals` 旧机制，PF 后需同步更新 | 交叉引用 | → 加入 Step PF 操作表（§6.2 新增"同步 technical.md"行）+ 增加 grep 确认 |
| ㉕ | **`write_html_report` 15 参数签名本身就是债务**：`enable_llm`/`llm_content`、`include_news`/`news_data` 两组互斥参数混在同一签名 | 静态分析 | → 补录为 TD-4 |
| ㉖ | **B 系列 4 函数共享 ~40 行 try/except 样板**：迁入 `html_renderers.py` 后此重复被固化 | 代码审查 | → 补录为 TD-5 |
| ㉗ | **Step 4 模板变量分组合并风险大于收益**：`render(**group1, **group2)` 不可类型检查，变量名拼错致静默空值 | 风险再评估 | → 移除该措施，保留仅低风险提取。目标 160→**~125** 行（原 ~100）|
| ㉘ | **Phase C grep 范围不完整**：只说"确认无人引用"但未指定扫描范围 | 内审 | → 明确为全代码库 `src/ + test/`（§7 Phase C）|
| ㉙ | **PF 缺少 `_ENV.globals` grep 全局确认**：需要确认全代码库无第三处写入 | 内审 | → 加入 grep 检查工序（§6.2 末尾）|

---

## 14. 已识别的技术债务

| # | 债务 | 模块 | 严重度 | 治理建议 |
|:-:|:-----|:-----|:------:|:---------|
| TD-1 | B 系列 3 函数各自调用 `fetch_fund_holdings` 产生冗余文件读 | `html_renderers.py` 迁入后 | 🟢 | R-204（P3） |
| TD-2 | `_render_penetration_section` 混合数据获取与渲染逻辑（62 行）| `html_renderers.py` 迁入后 | 🟢 | 提取为 `_load_eps_dividend`/`_attach_eps_dividend` |
| TD-3 | 测试文件跨越多个源模块（名称与内容不匹配）| `test_html_writer*` | 🟢 | 不处理 |
| TD-4 | **`write_html_report` 15 参数签名混入互斥参数组**：`enable_llm`/`llm_content`（LLM 开关模式 2 选 1）、`include_news`/`news_data`（新闻开关模式 2 选 1），传入矛盾值需运行时判断优先级 | `html_writer.py`（迁出后） | 🟢 | 后续重构为 `ReportConfig` 数据类 + 两个 factory method（`with_llm()`/`with_news()`）|
| TD-5 | **B 系列 4 函数共享 ~40 行 try/except 样板**：`_render_manager_analysis`/`_render_overlap_matrix`/`_render_concentration`/`_render_style_analysis` 各自独立 try/except return None 模式，迁入 `html_renderers.py` 后被固化 | `html_renderers.py`（迁入后） | 🟢 | 提取 `_try_render(fn, *args, fallback, label)` 装饰器或辅助函数 |
