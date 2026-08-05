# HTML 报告 TOC 标记 LLM 支持章节（橙色加粗 + 🧠 图标）

## Context

HTML 报告的两处导航（左侧 `.toc-sidebar` 目录 + 窄屏顶部 `.section-nav` 横向导航）目前所有章节链接样式统一，用户无法从目录一眼识别哪些章节内容由 LLM 生成/支持。需求：凡是有 LLM 支持的章节，标题**橙色加粗** + 标题旁 **🧠 图标**，并适配 dark mode。整体设计需符合架构设计约束。

**用户已确认的设计决策：**
1. **LLM 章节范围** = LLM 导航组全部 6 章：`news_correlation`、`global_macro`、`expert_review`、`health_check`、`penetration_deep`、`llm_usage`
2. **图标** = 🧠 emoji（与正文辩论模式 🧪 的 emoji 风格一致）
3. **两处都标记**：左侧 TOC + 窄屏 section-nav

## 关键前置事实（已探明并验证）

- `news_correlation` 在 registry `_REPORT_SECTION_DEFAULT` 的 `type` 是 `"news"`（`src/python/core/registry.py:544`），**不能**从 registry `type == "llm"` 派生 → 只能从 `_SECTION_NAV_GROUP_MAP` 的 "llm" 组派生（`src/python/report/html_writer.py:173-198`）。
- 主题机制为纯 CSS 变量：`:root`（浅色）+ `[data-theme="dark"]`（深色覆盖）。`theme.js` 只翻转 `data-theme` 属性，无 CSS 变量白名单 → **theme.js 零改动**。
- 可复用变量 `--orange-text`（浅 `#E65100` / 深 `#ff8a50`）已双定义，正是橙色语义 → **不新增 CSS 变量**。
- `@media print`（`report_template.html:466-471`）已 `display: none !important` 隐藏两个导航 → 打印无需处理。
- `src/static/toc.js` 只读 `href` 映射 active class，不读其他 class/子节点 → 加 class/插 span 不破坏它。
- 测试 helper `_render_template`（`test_html_report_structure.py:163-181`）是唯一模板渲染入口，已被 `test_action_html.py` 等文件 import → 注入一次覆盖所有渲染测试。

## 实现

### 1. `src/python/report/html_writer.py`

**a. 新增常量**（`_SECTION_NAV_GROUP_MAP` 之后）：

```python
# LLM 支持章节：与「LLM」导航组同源派生（新闻关联 + LLM 文本分析系列 + API 用量），
# 单一数据源防漂移；目录/横向导航据此橙色加粗 + 🧠 图标标记。
_LLM_SUPPORTED_SECTIONS: frozenset[str] = frozenset(
    key for key, group in _SECTION_NAV_GROUP_MAP.items() if group == "llm"
)
```

> 注释纪律：不得写"6 章"/"N 章"（check-code-traces CHAPTER 模式检出），用"LLM 导航组"等无计数表述。

**b. `_build_section_nav_groups`（L201-229）**：append 的 section dict 增加字段：

```python
{
    "key": key,
    "number": section_numbers.get(key, 0),
    "name": sec.get("name", key),
    "llm_supported": key in _LLM_SUPPORTED_SECTIONS,
}
```

同步 docstring：`sections: [{key, number, name, llm_supported}, ...]`。

**c. `_render_template`（L490 附近）**：render() context 追加：

```python
section_groups=section_groups,
llm_supported_sections=_LLM_SUPPORTED_SECTIONS,
```

`llm_supported_sections`（frozenset）供 section-nav 侧 `in` 判断（section-nav 直接遍历 `section_order`，不经 `_build_section_nav_groups`）。经 context 传递，符合 C14。

### 2. `src/python/tmpl/report_template.html`

**a. TOC 链接（L889-891）**：

```html
{% for sec in group.sections %}
<a href="#sec-{{ sec['key'] }}"{% if sec['llm_supported'] %} class="toc-llm"{% endif %}>{{ sec.number }}、{{ sec.name }}{% if sec['llm_supported'] %}<span class="toc-llm-icon" aria-hidden="true">🧠</span>{% endif %}</a>
{% endfor %}
```

**b. section-nav 链接（L926）**：

```html
<a href="#sec-{{ sec['key'] }}"{% if sec["key"] in llm_supported_sections %} class="toc-llm"{% endif %}>{{ section_numbers[sec["key"]] }}、{{ sec["name"] }}{% if sec["key"] in llm_supported_sections %}<span class="toc-llm-icon" aria-hidden="true">🧠</span>{% endif %}</a>
```

**c. CSS**（插在 `.toc-list a.active` 规则之后，单一语义块）：

```css
/* LLM 支持章节：目录/横向导航橙色加粗 + 🧠 图标（LLM 导航组章节） */
.toc-list a.toc-llm { color: var(--orange-text); font-weight: 600; }
.toc-list a.toc-llm.active { color: var(--orange-text); border-left-color: var(--orange-text); }
.section-nav a.toc-llm { color: var(--orange-text); font-weight: 600; }
.toc-llm-icon { margin-left: 4px; vertical-align: middle; }
```

- 特异性：`.toc-list a.toc-llm.active` (0,3,1) > `.toc-list a.active` (0,2,1)，active 态保持橙色；非 active 时 `.toc-list a.toc-llm` (0,2,1) > `.toc-list a` (0,1,1)；section-nav 同理覆盖硬编码 `#2E75B6`。均无需 `!important`。
- 图标 `.toc-llm-icon` 共用类，两处导航一致；emoji 自着色，dark mode 天然可见。

### 3. `src/test/unit/report/test_html_report_structure.py`

**a. 模块级常量**（约 L56-60，`_NEWS_KEYS` 等附近）：

```python
_LLM_SUPPORTED_KEYS = {
    "news_correlation", "global_macro", "expert_review",
    "health_check", "penetration_deep", "llm_usage",
}
```

**b. 更新 `_render_template` helper（L163-181）**：import `_LLM_SUPPORTED_SECTIONS`，render() 追加 `llm_supported_sections=_LLM_SUPPORTED_SECTIONS`。

**c. 更新两个既有测试（图标文本进入 get_text，必须改）：**
- `test_toc_link_text_shows_number_and_name`（L1099-1106）：非 LLM 章节 `assertEqual`（精确 "编号、名称"）；LLM 章节改 `assertTrue(text.startswith(expected))` + `assertIn("🧠", text)`。
- `test_nav_section_title_text_consistency`（L447-462，`TestHtmlCustomOrder`）：比对前对 LLM 章节 `nav_text.replace("🧠", "", 1).strip()` 剔除图标。

**d. 新增测试（挂 `TestHtmlTocGroupedNav` 类，复用 `self.soup`；marker 由文件级 `pytestmark = [unit, unit_report]` 自动生效，无需显式加）：**
- `test_llm_supported_sections_constant_matches_group` — `_LLM_SUPPORTED_SECTIONS == _LLM_SUPPORTED_KEYS`
- `test_llm_toc_links_marked` — 6 个 LLM 目录链接含 `toc-llm` class + `span.toc-llm-icon`（aria-hidden="true"、文本 🧠）
- `test_non_llm_toc_links_unmarked` — 非 LLM 目录链接无 class/图标
- `test_section_nav_llm_links_marked` — section-nav 中 LLM 链接带 class+图标、非 LLM 不带
- `test_section_groups_carry_llm_supported_flag` — 直接调 `_build_section_nav_groups`，断言 section dict 含 `llm_supported` 且值正确
- `test_toc_llm_css_rules_defined` — 模板 CSS 含 `.toc-list a.toc-llm` / `.section-nav a.toc-llm` / `.toc-llm-icon` / `.toc-list a.toc-llm.active`
- `test_llm_mark_color_reuses_dual_defined_variable` — `:root` 有 `--orange-text: #E65100`、`[data-theme="dark"]` 有 `--orange-text: #ff8a50`，且新规则引用 `var(--orange-text)`

### 4. 文档

- `docs-stm/managements/changelog.md` — `[0.10.5-dev]` 下新增 `###` 小节：语义描述（两处导航 LLM 章节橙色加粗 + 🧠 图标、标记集合与 LLM 导航组同源派生、经模板 context 传入、测试新增/更新）。**禁 C 编号/数字章节名**。
- `folders.md` — 无新文件，目录树/统计表不变，不改。
- `technical.md` — 可选一行简注（CSS 变量体系段），非必需。

## 合规自检

| 约束 | 合规性 |
|---|---|
| **C7** 报告序号注册表驱动 | 不硬编码序号，LLM 判定基于注册表 key（导航映射），与序号解耦 |
| **C14** 渲染期数据经 context | `llm_supported_sections` 经 render() context 传入，`_LLM_SUPPORTED_SECTIONS` 为静态常量，不碰 `_ENV.globals` |
| **C19** pipeline_data Schema | 无新增 pipeline_data 键，N/A |
| **C20** 图表图下说明 | 无新增图表，N/A |
| **语义化命名** | `_LLM_SUPPORTED_SECTIONS` / `llm_supported` / `toc-llm` / `toc-llm-icon` 均语义名 |
| **check 脚本** | 新注释避开 C 编号 / `第 N 章` / `N 章` / 轮次 / `rf-`/`plan-` |

## 验证

1. 单测：`.venv/bin/python -m pytest src/test/unit/report/test_html_report_structure.py -v`
2. P0 门禁：`.venv/bin/python scripts/test_runner.py --mode dev-verify`
3. 3 check：`check-task-numbering.py --ci` / `check-doc-traces.py --ci` / `check-code-traces.py --ci`
4. 手动渲染验证（可选）：用现有测试数据渲染一份 HTML 报告，浏览器打开确认左侧 TOC 与窄屏 section-nav 的 LLM 章节橙色加粗 + 🧠 图标，切换 dark mode 确认橙色可读。

## 关键文件

- `src/python/report/html_writer.py`
- `src/python/tmpl/report_template.html`
- `src/test/unit/report/test_html_report_structure.py`
- `docs-stm/managements/changelog.md`
