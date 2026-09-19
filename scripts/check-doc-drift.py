#!/usr/bin/env python3
"""文档与实现一致性检查（doc-code drift check）—— 文档里写死的「事实」与代码/配置文件/文件系统逐条对账。

背景：文档中的**计数、清单、默认值、目录树、统计表**是易漂移的「事实断言」——
代码里加了开关/章节/文件，文档数字不动就静默失真。本脚本把这类断言与权威源绑定，
逐条比对，使漂移在提交前暴露（与 check-doc-traces 的「历史痕迹」检查互补：
那边管「不该写的内容」，这边管「写了但与实现不符的内容」）。

十项检查（权威源 → 受检文档）：
  1.  报告章节表        core/registry.py `_REPORT_SECTION_DEFAULT`      → manuals/reports-instruction.md
  2.  章节数量断言      同上（`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`）→ 全库文档
  3.  功能开关表        config/features.py `feature_switch_registry`    → manuals/how-to-config.md
  4.  开关分组计数断言  同上（`⚗实验 A / 常规 B / 报告章节与增强 C`、`实验组（A 项`、`共 N 项开关` 等）→ 全库文档
  5.  开关默认值断言    同上（`` `flag` `` 后紧随「默认开/关」）          → 全库文档
  6.  配置标量默认值表   config/_config_defaults.py `_DEFAULT_CONFIG`   → manuals/how-to-config.md
  7.  LLM 默认参数表     config/_llm_settings_defaults.py + 缓存 TTL 注册表 → managements/llm-technical.md
  8.  TUI 面板编号       `tui/handlers_config.py` 的派生规则（LLM 可见模块 + 三组顺序连续编号）→ manuals/how-to-use-tui-menu.md
  9.  目录树           文件系统实测（src/、scripts/、docs-stm/{managements,manuals,plan}）→ managements/folders.md
  10. 项目统计表        文件系统实测（文件数/行数）+ 可选 pytest 收集数 → managements/folders.md
  11. 测试覆盖计数表    `scripts/collect-test-coverage.py` 快照 → managements/test-coverage.md（仅 `--with-test-count`）

按设计豁免的历史记录文档：`changelog.md` / `review-findings.md`（会如实引用旧数字作为变更记录）
与 `docs-stm/archive/**`（版本快照）不参与第 2/4/5 项扫描。

用法：
  python scripts/check-doc-drift.py                  # 十项全查
  python scripts/check-doc-drift.py -v               # 详细输出（打印解析明细）
  python scripts/check-doc-drift.py --ci             # CI 模式：仅输出 文件:描述，退出码 2
  python scripts/check-doc-drift.py --with-test-count # 附带 pytest 收集，核对「测试用例数」与 test-coverage.md 计数表

退出码：
  0 — 全部一致
  2 — 发现不一致（逐条列出 文件:描述，可直接按提示改）
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402

if str(REPO_ROOT) not in sys.path:  # 允许任意 cwd 下运行
    sys.path.insert(0, str(REPO_ROOT))

from src.python.config._config_defaults import _DEFAULT_CONFIG  # noqa: E402
from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS  # noqa: E402
from src.python.config.features import feature_switch_registry, switches_in_group  # noqa: E402
from src.python.core.registry import (  # noqa: E402
    _REPORT_SECTION_DEFAULT,
    get_cache_ttl_defaults,
    get_llm_module_names,
)
from src.python.tui.tui_menu import filter_menu_llm_modules  # noqa: E402

_README = REPO_ROOT / "README.md"
_MANUALS = REPO_ROOT / "docs-stm" / "manuals"
_MANAGEMENTS = REPO_ROOT / "docs-stm" / "managements"
_FOLDERS_MD = _MANAGEMENTS / "folders.md"
_HOW_TO_CONFIG_MD = _MANUALS / "how-to-config.md"
_REPORTS_MD = _MANUALS / "reports-instruction.md"
_TUI_MENU_MD = _MANUALS / "how-to-use-tui-menu.md"
_LLM_TECHNICAL_MD = _MANAGEMENTS / "llm-technical.md"
_TEST_COVERAGE_MD = _MANAGEMENTS / "test-coverage.md"

#: 按设计保留历史数字的文档（变更记录/自审记录），不参与计数与默认值断言扫描
_HISTORY_DOCS = {_MANAGEMENTS / "changelog.md", _MANAGEMENTS / "review-findings.md"}

#: 目录树与统计表覆盖的受检范围（其余路径不由 folders.md 逐文件登记）
_TREE_ROOTS = ("src", "scripts", "docs-stm/managements", "docs-stm/manuals", "docs-stm/plan")

#: 目录树重建时跳过的路径段（缓存/临时产物）
#: 构建/缓存产物（不入文档树、不计统计）：目录名 + 后缀规则
_GENERATED_DIRS = {
    "__pycache__",
    ".eggs",
    "build",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov",
}
_GENERATED_SUFFIXES = (".egg-info", ".dist-info")
_GENERATED_FILES = {".coverage"}
#: 多段路径形式的产物前缀（运行时临时目录）
_GENERATED_PREFIXES = ("docs-stm/tmp/",)


def _is_generated(rel: str) -> bool:
    """相对路径是否属构建/缓存产物（`pip install -e` 的 egg-info、构建目录、缓存等）。

    这些由工具链生成、不该出现在目录树里也不该计入统计——CI 上 `pip install -e ".[test]"`
    会在 `src/` 下留下 `*.egg-info/`，若不排除会被误报为「目录树缺条目」。

    **例外**：`test-reports/` 的规范位置是仓库根（不在受检根内），故**不**豁免——受检目录
    （`src/`、`scripts/`、`docs-stm/{managements,manuals,plan}`）下出现 `test-reports/`
    属误落（如入口把项目根算到了 `scripts/`），须由目录树检查报出。
    """
    if rel in _GENERATED_FILES or rel.startswith(_GENERATED_PREFIXES):
        return True
    return any(p in _GENERATED_DIRS or p.endswith(_GENERATED_SUFFIXES) for p in Path(rel).parts)


def _scan_docs() -> dict[Path, str]:
    """返回参与断言扫描的文档集合（README + 手册 + 管理文档，排除历史记录类）。"""
    docs: list[Path] = [_README]
    docs += sorted(_MANUALS.glob("*.md"))
    docs += sorted(_MANAGEMENTS.glob("*.md"))
    return {p: p.read_text(encoding="utf-8") for p in docs if p not in _HISTORY_DOCS}


# ═══════════════════════════════════════════════════════════════
#  1/2. 报告章节
# ═══════════════════════════════════════════════════════════════


def parse_section_rows(doc_text: str) -> list[tuple[int, int, str]]:
    """解析 reports-instruction.md 章节表的 ``(表序号, 章序号, 名称)`` 行。"""
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*\*\*(\d+)\.([^（(*|\n]+)", doc_text, re.M)
    return [(int(a), int(b), c.strip()) for a, b, c in rows]


def check_section_table(doc_text: str) -> list[str]:
    findings: list[str] = []
    rows = parse_section_rows(doc_text)
    expected = _REPORT_SECTION_DEFAULT
    if len(rows) != len(expected):
        findings.append(f"{rel(_REPORTS_MD)}: 章节表 {len(rows)} 行，注册表 {len(expected)} 章")
    for i, (_, num, name) in enumerate(rows):
        if i >= len(expected):
            break
        exp = expected[i]
        if num != exp["number"] or name != exp["name"]:
            findings.append(
                f"{rel(_REPORTS_MD)}: 章节表第 {i + 1} 行 `{num}.{name}` 与注册表 "
                f"`{exp['number']}.{exp['name']}` 不一致"
            )
    return findings


#: 章节数量断言：`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`
_SECTION_COUNT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"页签编号\s*1\s*[~～-]\s*(\d+)"),
    re.compile(r"默认顺序[（(](\d+)\s*项"),
    re.compile(r"返回 result[（(](\d+)\s*项"),
    re.compile(r"(\d+)\s*个报告章节"),
]


def check_section_counts(docs: dict[Path, str]) -> list[str]:
    findings: list[str] = []
    total = len(_REPORT_SECTION_DEFAULT)
    for path, text in docs.items():
        for line_no, line in enumerate(text.splitlines(), 1):
            for pat in _SECTION_COUNT_PATTERNS:
                for m in pat.finditer(line):
                    if int(m.group(1)) != total:
                        findings.append(f"{rel(path)}:{line_no}: 章节数量断言「{m.group(0)}」与注册表 {total} 章不一致")
    return findings


# ═══════════════════════════════════════════════════════════════
#  3/4/5. 功能开关
# ═══════════════════════════════════════════════════════════════

#: how-to-config.md 开关表区段起点（三组表格连续排布，止于下一个二级标题）
_SWITCH_TABLE_START = "**⚗ 实验组（"
_SWITCH_ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|\s*\**`?(true|false)`?\**\s*\|")


def extract_switch_table(doc_text: str) -> dict[str, bool]:
    """取 how-to-config.md 功能开关表区段内的 ``{flag: 默认值}``（其它表格不误取）。"""
    lines = doc_text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(_SWITCH_TABLE_START)), None)
    if start is None:
        return {}
    table: dict[str, bool] = {}
    for line in lines[start:]:
        if line.startswith("## "):
            break
        m = _SWITCH_ROW.match(line)
        if m:
            table[m.group(1)] = m.group(2) == "true"
    return table


def check_switch_table(doc_text: str) -> list[str]:
    findings: list[str] = []
    table = extract_switch_table(doc_text)
    if not table:
        return [f"{rel(_HOW_TO_CONFIG_MD)}: 未找到功能开关表区段（起点 `{_SWITCH_TABLE_START}`）"]
    for flag, definition in feature_switch_registry.items():
        if flag not in table:
            findings.append(f"{rel(_HOW_TO_CONFIG_MD)}: 功能开关 `{flag}` 未列入开关表")
        elif table[flag] != definition.default:
            findings.append(
                f"{rel(_HOW_TO_CONFIG_MD)}: 开关 `{flag}` 表中默认值 {table[flag]} 与注册表 {definition.default} 不一致"
            )
    for flag in table:
        if flag not in feature_switch_registry:
            findings.append(f"{rel(_HOW_TO_CONFIG_MD)}: 开关表出现未登记开关 `{flag}`")
    return findings


def _group_counts() -> dict[str, int]:
    return {
        "experimental": len(switches_in_group("experimental")),
        "standard": len(switches_in_group("standard")),
        "report": len(switches_in_group("report")),
    }


#: 三组连写：`⚗实验 A / 常规 B / 报告章节与增强 C`
_TRIPLE_COUNT = re.compile(r"⚗实验\s*(\d+)\s*/\s*常规\s*(\d+)\s*/\s*报告章节与增强\s*(\d+)")
#: 分组枚举：`实验组（前 A 项）` / `常规组（次 B 项）` / `报告组（后 C 项）`
_GROUPED_COUNT = re.compile(r"(实验组|常规组|报告组)[（(](?:前|次|后)?\s*(\d+)\s*项")
_GROUP_NAME_TO_KIND = {"实验组": "experimental", "常规组": "standard", "报告组": "report"}
#: 单块出现：`报告章节与增强（N 项）`
_REPORT_BLOCK_COUNT = re.compile(r"报告章节与增强[（(](\d+)\s*项")
#: 合计：`共 N 项（功能）开关` / `全部 N 项开关` / `**N 项功能开关**`
_TOTAL_COUNT = re.compile(r"(?:共|全部)\s*(\d+)\s*项(?:功能)?开关|\*\*(\d+)\s*项功能开关\*\*")


def _count_finding(path: Path, line_no: int, shown: str, expected: int) -> str:
    return f"{rel(path)}:{line_no}: 开关分组计数「{shown}」与注册表 {expected} 不一致"


def check_switch_counts(docs: dict[Path, str]) -> list[str]:
    """开关分组计数断言 ↔ 注册表分组计数（四种写法：三组连写 / 分组枚举 / 单块 / 合计）。"""
    findings: list[str] = []
    counts = _group_counts()
    total = len(feature_switch_registry)
    for path, text in docs.items():
        for line_no, line in enumerate(text.splitlines(), 1):
            for m in _TRIPLE_COUNT.finditer(line):
                got = [int(m.group(i)) for i in (1, 2, 3)]
                exp = [counts["experimental"], counts["standard"], counts["report"]]
                if got != exp:
                    findings.append(
                        f"{rel(path)}:{line_no}: 开关分组计数「{m.group(0)}」与注册表 "
                        f"{'/'.join(str(v) for v in exp)} 不一致"
                    )
            for m in _GROUPED_COUNT.finditer(line):
                expected = counts[_GROUP_NAME_TO_KIND[m.group(1)]]
                if int(m.group(2)) != expected:
                    findings.append(_count_finding(path, line_no, m.group(0), expected))
            for m in _REPORT_BLOCK_COUNT.finditer(line):
                if int(m.group(1)) != counts["report"]:
                    findings.append(_count_finding(path, line_no, m.group(0), counts["report"]))
            for m in _TOTAL_COUNT.finditer(line):
                if int(m.group(1) or m.group(2)) != total:
                    findings.append(_count_finding(path, line_no, m.group(0), total))
    return findings


#: `` `flag` `` 完整 token 后 6 字内（不含反引号，避免跨到下一个开关）出现「默认开/关」
_DEFAULT_CLAIM = re.compile(r"`([a-z0-9_]+)`([^\n`]{0,6}?)默认\s*(开|关|true|false)")


def check_switch_default_claims(docs: dict[Path, str]) -> list[str]:
    findings: list[str] = []
    for path, text in docs.items():
        for line_no, line in enumerate(text.splitlines(), 1):
            for m in _DEFAULT_CLAIM.finditer(line):
                flag, claim = m.group(1), m.group(3)
                if flag not in feature_switch_registry:
                    continue
                claim_bool = claim in ("开", "true")
                if claim_bool != feature_switch_registry[flag].default:
                    findings.append(
                        f"{rel(path)}:{line_no}: `{flag}` 文档写「默认{claim}」而注册表默认 "
                        f"{'开' if feature_switch_registry[flag].default else '关'}"
                    )
    return findings


# ═══════════════════════════════════════════════════════════════
#  6. 配置标量默认值表
# ═══════════════════════════════════════════════════════════════

_CONFIG_ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|\s*`([^`]*)`\s*\|")


def _values_equal(doc_value: str, code_value: object) -> bool:
    """文档字符串 ↔ 代码默认值的等价判定（bool/None/数字/路径/字符串）。"""
    shown = doc_value.strip()
    if isinstance(code_value, bool):
        return shown.lower() in (("true", "开") if code_value else ("false", "关"))
    if code_value is None:
        return shown.lower() in ("null", "none", "无")
    if isinstance(code_value, (int, float)):
        try:
            return float(shown.replace(",", "")) == float(code_value)
        except ValueError:
            return False
    text = str(code_value)
    if shown == text or shown.strip("\"'") == text.strip("\"'"):
        return True
    # 路径类默认值在代码内可能已被解析为绝对路径，文档写相对形式
    return bool(shown) and (text.endswith(shown) or Path(text).name == Path(shown).name)


def check_config_defaults(doc_text: str) -> list[str]:
    findings: list[str] = []
    known = set(_DEFAULT_CONFIG)
    for line_no, line in enumerate(doc_text.splitlines(), 1):
        m = _CONFIG_ROW.match(line)
        if not m:
            continue
        key, shown = m.group(1), m.group(2)
        if key not in known:
            continue
        default = _DEFAULT_CONFIG[key]
        if isinstance(default, (dict, list)):
            continue  # 结构型默认值在文档中以「见下节」描述，不做逐值比对
        if not _values_equal(shown, default):
            findings.append(
                f"{rel(_HOW_TO_CONFIG_MD)}:{line_no}: 配置项 `{key}` 文档默认值 `{shown}` 与代码 "
                f"`{_DEFAULT_CONFIG[key]!r}` 不一致"
            )
    return findings


# ═══════════════════════════════════════════════════════════════
#  7. LLM 默认参数表
# ═══════════════════════════════════════════════════════════════

#: 模块表行：| `module` | 名称 | max_tokens | timeout | TTL | system_prompt |
_LLM_ROW = re.compile(
    r"^\|\s*`([a-z_]+)`\s*\|\s*[^|]+\|\s*(\d+)\s*\|\s*(\d+)s\s*\|\s*([^|]+?)\s*\|",
    re.M,
)
_TTL_TABLE_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*(\d+)s\s*(?:\([^)]*\))?\s*\|", re.M)
_HOURS_ROW = re.compile(r"^|\s*`([a-z_]+)`\s*\|\s*(\d+)h（(\d+)s）\s*\|")


def _ttl_default(module: str) -> float | None:
    """缓存 TTL 注册表中该 LLM 模块的默认 TTL（新闻关联为批量模块，键名带前缀）。"""
    defaults = get_cache_ttl_defaults()
    for key in (f"llm_{module}", f"llm_news_{module}", f"llm_{module}_item"):
        if key in defaults:
            return float(defaults[key])
    return None


def check_llm_defaults(doc_text: str) -> list[str]:
    findings: list[str] = []
    for m in _LLM_ROW.finditer(doc_text):
        module, max_tokens, timeout, ttl_text = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        if module not in get_llm_module_names():
            continue
        exp_max = _DEFAULT_LLM_SETTINGS.get(f"max_tokens_{module}")
        exp_timeout = _DEFAULT_LLM_SETTINGS.get(f"timeout_{module}")
        if exp_max is not None and max_tokens != exp_max:
            findings.append(
                f"{rel(_LLM_TECHNICAL_MD)}: 模块 `{module}` max_tokens 文档 {max_tokens} 与代码 {exp_max} 不一致"
            )
        if exp_timeout is not None and timeout != exp_timeout:
            findings.append(
                f"{rel(_LLM_TECHNICAL_MD)}: 模块 `{module}` timeout 文档 {timeout}s 与代码 {exp_timeout}s 不一致"
            )
        ttl_hours = re.search(r"(\d+)h", ttl_text)
        ttl_secs = re.search(r"(\d+)s", ttl_text)
        exp_ttl = _ttl_default(module)
        if exp_ttl is not None and ttl_secs and int(ttl_secs.group(1)) != int(exp_ttl):
            findings.append(
                f"{rel(_LLM_TECHNICAL_MD)}: 模块 `{module}` TTL 文档 {ttl_secs.group(1)}s 与缓存注册表 {int(exp_ttl)}s 不一致"
            )
        elif exp_ttl is not None and ttl_hours and int(ttl_hours.group(1)) * 3600 != int(exp_ttl):
            findings.append(
                f"{rel(_LLM_TECHNICAL_MD)}: 模块 `{module}` TTL 文档 {ttl_hours.group(1)}h 与缓存注册表 {int(exp_ttl)}s 不一致"
            )
    for m in _TTL_TABLE_ROW.finditer(doc_text):
        module, ttl = m.group(1), int(m.group(2))
        exp_ttl = _ttl_default(module)
        if exp_ttl is not None and ttl != int(exp_ttl):
            findings.append(
                f"{rel(_LLM_TECHNICAL_MD)}: 模块 `{module}` TTL 表 {ttl}s 与缓存注册表 {int(exp_ttl)}s 不一致"
            )
    return findings


# ═══════════════════════════════════════════════════════════════
#  8. TUI [S] 面板编号
# ═══════════════════════════════════════════════════════════════

_PANEL_SECTION_START = "交互式子菜单（面板标题"
_PANEL_SECTION_END = "**报告章节与增强"
_PANEL_ROW = re.compile(r"^\|\s*(\d+)(?:[-–](\d+))?\s*\|")
_REPORT_RANGE = re.compile(r"报告章节与增强（面板编号\s*(\d+)-(\d+)）")
_REPORT_ITEM = re.compile(r"(\d+)\s*`([a-z0-9_]+)`")


def check_panel_numbering(doc_text: str) -> list[str]:
    """校验 [S] 面板编号连续且分组边界与注册表一致（编号由 handlers_config.py 派生）。"""
    findings: list[str] = []
    lines = doc_text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(_PANEL_SECTION_START)), None)
    end = next((i for i, ln in enumerate(lines) if ln.startswith(_PANEL_SECTION_END)), None)
    if start is None or end is None or end <= start:
        return [f"{rel(_TUI_MENU_MD)}: 未找到 [S] 面板编号表区段"]

    numbers: list[int] = []
    for line in lines[start:end]:
        m = _PANEL_ROW.match(line)
        if not m:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        numbers.extend(range(lo, hi + 1))

    llm_visible = len(filter_menu_llm_modules(get_llm_module_names()))
    counts = _group_counts()
    # 表格区段只覆盖实验组 + 常规组（报告组以文本区间 + 逐项枚举给出，下标单独校验）
    table_last = llm_visible + counts["experimental"] + counts["standard"]
    expect = list(range(llm_visible + 1, table_last + 1))
    if numbers != expect:
        findings.append(
            f"{rel(_TUI_MENU_MD)}: 功能开关编号序列 {numbers or '空'} 与派生编号 "
            f"{expect[0]}~{expect[-1]}（LLM 菜单模块 {llm_visible} 项 + 实验 {counts['experimental']} + 常规 {counts['standard']}，连续无缺）不一致"
        )
    # 组边界：实验组末号 / 常规组起号必须与分组计数一致
    exp_first = llm_visible + 1
    exp_last = exp_first + counts["experimental"] - 1
    std_first = exp_last + 1
    std_last = std_first + counts["standard"] - 1
    if numbers[: counts["experimental"]] != list(range(exp_first, exp_last + 1)):
        findings.append(f"{rel(_TUI_MENU_MD)}: 实验组编号应为 {exp_first}~{exp_last}（共 {counts['experimental']} 项）")
    if numbers[counts["experimental"] : counts["experimental"] + counts["standard"]] != list(
        range(std_first, std_last + 1)
    ):
        findings.append(f"{rel(_TUI_MENU_MD)}: 常规组编号应为 {std_first}~{std_last}（共 {counts['standard']} 项）")

    m = _REPORT_RANGE.search(doc_text)
    rep_first = std_last + 1
    rep_last = rep_first + counts["report"] - 1
    if not m:
        findings.append(f"{rel(_TUI_MENU_MD)}: 报告块未标注「报告章节与增强（面板编号 {rep_first}-{rep_last}）」")
    elif (int(m.group(1)), int(m.group(2))) != (rep_first, rep_last):
        findings.append(
            f"{rel(_TUI_MENU_MD)}: 报告块编号区间 {m.group(1)}-{m.group(2)} 与派生区间 {rep_first}-{rep_last} 不一致"
        )
    else:
        pairs = _REPORT_ITEM.findall(doc_text[m.start() :])
        exp_pairs = [(str(rep_first + i), flag) for i, (flag, _d) in enumerate(switches_in_group("report"))]
        got_pairs = [(num, flag) for num, flag in pairs if flag in feature_switch_registry]
        if got_pairs != exp_pairs:
            findings.append(f"{rel(_TUI_MENU_MD)}: 报告块开关编号/顺序 {got_pairs} 与注册表 {exp_pairs} 不一致")
    return findings


# ═══════════════════════════════════════════════════════════════
#  9. 目录树
# ═══════════════════════════════════════════════════════════════

_TREE_ENTRY = re.compile(r"──\s+([^#]+?)\s*(?:#.*)?$")


def parse_tree_paths(doc_text: str) -> set[str]:
    """按缩进层级把 folders.md 的目录树还原为仓库相对路径集合。"""
    paths: set[str] = set()
    stack: list[tuple[int, str]] = []
    in_tree = False
    for line in doc_text.splitlines():
        if line.startswith("```"):
            in_tree = not in_tree
            continue
        if not in_tree or "── " not in line:
            continue
        prefix = line.split("── ", 1)[0]
        depth = len(re.findall(r"│|    ", prefix))
        name = line.split("── ", 1)[1].split("#")[0].strip()
        if not name:
            continue
        if name.endswith("/"):
            dirname = name.rstrip("/")
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, dirname))
        else:
            paths.add("/".join([p for d, p in stack if d < depth] + [name]))
    return paths


def _actual_files() -> set[str]:
    files: set[str] = set()
    for root in _TREE_ROOTS:
        for p in (REPO_ROOT / root).rglob("*"):
            if not p.is_file():
                continue
            rel_path = rel(p)
            if _is_generated(rel_path):
                continue
            files.add(rel_path)
    return files


def check_dir_tree(doc_text: str) -> list[str]:
    findings: list[str] = []
    tree = parse_tree_paths(doc_text)
    actual = _actual_files()
    for path_text in sorted(actual - tree):
        findings.append(f"{rel(_FOLDERS_MD)}: 目录树缺少 `{path_text}`（实际存在，须补条目）")
    for path_text in sorted(tree - actual):
        if any(path_text == root or path_text.startswith(root + "/") for root in _TREE_ROOTS):
            findings.append(f"{rel(_FOLDERS_MD)}: 目录树条目 `{path_text}` 在磁盘上不存在")
    return findings


# ═══════════════════════════════════════════════════════════════
#  10. 项目统计表
# ═══════════════════════════════════════════════════════════════

_STATS_ROW = re.compile(r"^\|")


def _split_table_row(line: str) -> list[str] | None:
    """拆分 markdown 表格行 → 去除粗体标记的单元格列表（非表格行返回 None）。"""
    if not line.startswith("|"):
        return None
    cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
    return cells if len(cells) >= 4 else None


def _first_number(cell: str) -> str | None:
    """取单元格中的首个数字（去千分位），无数字时返回 None（`-` / 空占位）。"""
    m = re.search(r"[\d][\d,]*", cell)
    return m.group(0).replace(",", "") if m else None


def _count(files: list[Path]) -> tuple[int, int]:
    kept = [p for p in files if not _is_generated(rel(p))]
    return len(kept), sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in kept)


def _stats_actual() -> dict[str, tuple[int, int]]:
    """各统计行的实测 ``(文件数, 行数)``（键与 folders.md 行标签一致）。"""
    main = [p for p in (REPO_ROOT / "src").rglob("*.py") if "src/test/" not in rel(p)]
    tests = list((REPO_ROOT / "src" / "test").rglob("*.py"))
    # scripts/ 含 _test_runner 内部实现包：统计递归计入（与 folders.md「辅助脚本」口径一致）
    scripts = sorted((REPO_ROOT / "scripts").rglob("*.py"))
    tmpl = list((REPO_ROOT / "src" / "static" / "tmpl").rglob("*.html"))
    svg = sorted((REPO_ROOT / "src" / "static").glob("*.svg"))
    manuals = sorted(_MANUALS.glob("*.md"))
    mgmt = sorted(_MANAGEMENTS.glob("*.md"))
    archive = sorted((REPO_ROOT / "docs-stm" / "archive").rglob("*.md"))
    plan = sorted((REPO_ROOT / "docs-stm" / "plan").glob("*.md"))
    readme = [_README]
    claude = [REPO_ROOT / "CLAUDE.md"]
    actual = {
        "主程序代码": _count(main),
        "HTML 报告模板": _count(tmpl),
        "架构图示": _count(svg),
        "辅助脚本": _count(scripts),
        "测试代码": _count(tests),
        "用户文档": _count(readme + manuals),
        "manuals/": _count(manuals),
        "项目文档": _count(claude + mgmt + archive + plan),
        "managements/": _count(mgmt),
        "archive/": _count(archive),
        "plan/": _count(plan),
    }
    src_total = tuple(
        sum(v[i] for k, v in actual.items() if k in ("主程序代码", "HTML 报告模板", "架构图示", "辅助脚本"))
        for i in (0, 1)
    )
    actual["源代码合计"] = src_total
    return actual


def _collect_test_count() -> int | None:
    """已收集用例数（与 folders.md 说明同源），见 `_collect_test_snapshot`。"""
    snapshot = _collect_test_snapshot()
    return snapshot.get("_总收集")


def _collect_test_snapshot() -> dict[str, int]:
    """`scripts/collect-test-coverage.py` 快照 → ``{标记/名称: 数量}``（含 ``_总收集``）。

    与 `test-coverage.md` / `folders.md` 同一来源（慢：内部跑 pytest 收集，仅 `--with-test-count` 时调用）。
    """
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "collect-test-coverage.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    snapshot: dict[str, int] = {}
    total = re.search(r"总收集:\s*(\d+)\s*项", proc.stdout)
    if total:
        snapshot["_总收集"] = int(total.group(1))
    for line in proc.stdout.splitlines():
        m = re.match(r"^([\w\u4e00-\u9fff][^:]*?):\s*(\d+)$", line.strip())
        if m:
            snapshot[m.group(1).strip()] = int(m.group(2))
    return snapshot


def check_project_stats(
    doc_text: str, with_test_count: bool = False, snapshot: dict[str, int] | None = None
) -> list[str]:
    findings: list[str] = []
    actual = _stats_actual()
    test_count = snapshot.get("_总收集") if snapshot else (_collect_test_count() if with_test_count else None)
    for line_no, line in enumerate(doc_text.splitlines(), 1):
        cells = _split_table_row(line)
        if cells is None:
            continue
        label = cells[0].lstrip("├└─ ").strip()
        got_files = _first_number(cells[2])
        got_lines = _first_number(cells[3])
        if label == "测试用例":
            if test_count is None or got_lines is None:
                continue
            if got_lines != str(test_count):
                findings.append(
                    f"{rel(_FOLDERS_MD)}:{line_no}: 测试用例数 {got_lines} 与 collect-test-coverage 快照 {test_count} 不一致"
                )
            continue
        if label not in actual:
            continue
        exp_files, exp_lines = actual[label]
        if got_files is not None and got_files != str(exp_files):
            findings.append(f"{rel(_FOLDERS_MD)}:{line_no}: 「{label}」文件数 {got_files} 与实测 {exp_files} 不一致")
        if got_lines is not None and got_lines != str(exp_lines):
            findings.append(f"{rel(_FOLDERS_MD)}:{line_no}: 「{label}」行数 {got_lines} 与实测 {exp_lines} 不一致")
    return findings


# ═══════════════════════════════════════════════════════════════
#  11. 测试覆盖计数表（test-coverage.md）
# ═══════════════════════════════════════════════════════════════

#: 计数行：`` | `name`（…） | … | 1,234 | ``（含子项符号 ├─/└─）
_TEST_COVERAGE_ROW = re.compile(r"^\|\s*(?:├─|└─)?\s*`([a-z0-9_-]+)`")
#: 纯计数单元格（可带粗体/千分位/附注括号）；描述性单元格（如「12 子组合计」）不匹配
_COUNT_CELL = re.compile(r"^\**(\d[\d,]*)\**\s*(?:（[^）]*）)?$")
#: 文档名 → 快照键的别名（`all` 即「总收集」，collect-test-coverage 不单列 all）
_COUNT_NAME_ALIAS = {"all": "_总收集"}


def check_test_coverage_counts(doc_text: str, snapshot: dict[str, int]) -> list[str]:
    """test-coverage.md 各计数行 ↔ collect-test-coverage 快照（按标记名匹配，未收录名跳过）。"""
    findings: list[str] = []
    for line_no, line in enumerate(doc_text.splitlines(), 1):
        m = _TEST_COVERAGE_ROW.match(line)
        if not m:
            continue
        name = _COUNT_NAME_ALIAS.get(m.group(1), m.group(1))
        if name not in snapshot:
            continue
        got: int | None = None
        for cell in [c.strip() for c in line.strip().strip("|").split("|")][1:]:
            num = _COUNT_CELL.match(cell)
            if num:
                got = int(num.group(1).replace(",", ""))
                break
        if got is not None and got != snapshot[name]:
            findings.append(
                f"{rel(_TEST_COVERAGE_MD)}:{line_no}: 标记 `{name}` 覆盖项数 {got} 与 collect-test-coverage 快照 {snapshot[name]} 不一致"
            )
    return findings


# ═══════════════════════════════════════════════════════════════
#  编排
# ═══════════════════════════════════════════════════════════════


def run_checks(with_test_count: bool = False) -> list[str]:
    """跑全部检查，返回不一致描述列表（空 = 全部一致）。"""
    docs = _scan_docs()
    snapshot = _collect_test_snapshot() if with_test_count else {}
    findings: list[str] = []
    findings += check_section_table(docs[_REPORTS_MD])
    findings += check_section_counts(docs)
    findings += check_switch_table(docs[_HOW_TO_CONFIG_MD])
    findings += check_switch_counts(docs)
    findings += check_switch_default_claims(docs)
    findings += check_config_defaults(docs[_HOW_TO_CONFIG_MD])
    findings += check_llm_defaults(docs[_LLM_TECHNICAL_MD])
    findings += check_panel_numbering(docs[_TUI_MENU_MD])
    findings += check_dir_tree(docs[_FOLDERS_MD])
    findings += check_project_stats(docs[_FOLDERS_MD], with_test_count=with_test_count, snapshot=snapshot)
    if with_test_count:
        findings += check_test_coverage_counts(docs[_TEST_COVERAGE_MD], snapshot)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验文档中的章节/开关/默认值/目录树/统计断言与代码、配置文件、文件系统的一致性",
    )
    add_common_args(parser)
    parser.add_argument(
        "--with-test-count",
        action="store_true",
        help="附带 pytest 收集快照，核对 folders.md 「测试用例」行与 test-coverage.md 各计数表（较慢）",
    )
    args = parser.parse_args()

    findings = run_checks(with_test_count=args.with_test_count)

    if args.verbose:
        docs = _scan_docs()
        actual = _stats_actual()
        print(f"  受检文档 {len(docs)} 份（历史记录类 changelog/review-findings 不参与计数扫描）")
        print(
            f"  报告章节 {len(_REPORT_SECTION_DEFAULT)} 章 / 功能开关 {len(feature_switch_registry)} 项 {_group_counts()}"
        )
        print(f"  开关表解析 {len(extract_switch_table(docs[_HOW_TO_CONFIG_MD]))} 行")
        print(f"  目录树解析 {len(parse_tree_paths(docs[_FOLDERS_MD]))} 条 / 实测文件 {len(_actual_files())} 个")
        for label, (files, lines) in actual.items():
            print(f"    {label}: {files} 文件 / {lines} 行")

    sys.exit(
        report(
            findings,
            "[OK] 文档与实现一致性校验通过（章节/开关/默认值/面板编号/目录树/统计表均与代码一致）",
            ci=args.ci,
            fail_message="[!] 发现 {n} 处文档与实现不一致，须修正后提交",
        )
    )


if __name__ == "__main__":
    main()
