"""`check-doc-drift` 文档格式族检查 —— 章节表 / 功能开关表 / 默认值 / 面板编号 / 测试覆盖计数。"""

from __future__ import annotations

import re
from pathlib import Path
from _checklib import rel
from src.python.config._config_defaults import _DEFAULT_CONFIG
from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS
from src.python.config.features import feature_switch_registry, switches_in_group
from src.python.core.registry import _REPORT_SECTION_DEFAULT, get_cache_ttl_defaults, get_llm_module_names
from src.python.tui.tui_menu import filter_menu_llm_modules

from src.python.fetcher.chain import _DEFAULT_CHAINS  # noqa: E402
from _doc_drift._shared import (
    _RELIABILITY_MD,
    _HOW_TO_CONFIG_MD,
    _LLM_TECHNICAL_MD,
    _REPORTS_MD,
    _TEST_COVERAGE_MD,
    _TUI_MENU_MD,
    _values_equal,
)


_CHAIN_TABLE_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")
#: 链表格内 ``provider id`` 单元格里的反引号 id（与 ``_DEFAULT_CHAINS`` 同序）
_CHAIN_ID_CELL = re.compile(r"`([a-z_0-9]+)`")
#: §4.2 表的列数（名称 / 主链路 / 备用链路 / provider id / 回退条件）
_CHAIN_TABLE_COLUMNS = 5

_SECTION_COUNT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"页签编号\s*1\s*[~～-]\s*(\d+)"),
    re.compile(r"默认顺序[（(](\d+)\s*项"),
    re.compile(r"返回 result[（(](\d+)\s*项"),
    re.compile(r"(\d+)\s*个报告章节"),
]


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


_TRIPLE_COUNT = re.compile(r"⚗实验\s*(\d+)\s*/\s*常规\s*(\d+)\s*/\s*报告章节与增强\s*(\d+)")


_GROUPED_COUNT = re.compile(r"(实验组|常规组|报告组)[（(](?:前|次|后)?\s*(\d+)\s*项")


_GROUP_NAME_TO_KIND = {"实验组": "experimental", "常规组": "standard", "报告组": "report"}


_REPORT_BLOCK_COUNT = re.compile(r"报告章节与增强[（(](\d+)\s*项")


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


_CONFIG_ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|\s*`([^`]*)`\s*\|")


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


_TEST_COVERAGE_ROW = re.compile(r"^\|\s*(?:├─|└─)?\s*`([a-z0-9_-]+)`")


_COUNT_CELL = re.compile(r"^\**(\d[\d,]*)\**\s*(?:（[^）]*）)?$")


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


def check_chain_table(doc_text: str) -> list[str]:
    """校验可靠性手册 §4.2「Provider Chain 降级路径」表与 `_DEFAULT_CHAINS` 逐链一致。

    两层比对：
      1. **链路名集合**双向一致（漏链 / 幽灵行）；
      2. **槽位级**双向一致：表的「provider id（机器可读）」列（按 ``→`` 顺序列出的
         ``source_id``）必须与 ``_DEFAULT_CHAINS[chain]`` **逐项同序**相等——覆盖
         「文档写主源+备源、代码只注册一个槽」这类漂移（漏槽 / 多槽 / 顺序错）。

    缺口：只比对链路名时槽位漂移无人发现——巨潮备源适配器已登记而
    ``_DEFAULT_CHAINS['financial_report']`` 只列主源槽，备源正文路径实际不可用；
    另该表曾只列 5 行却声称枚举全部链路。故本检查同时做槽位级同序比对。
    """
    findings: list[str] = []
    documented: set[str] = set()
    documented_slots: dict[str, list[str]] = {}
    missing_id_column: list[str] = []
    for line in doc_text.splitlines():
        m = _CHAIN_TABLE_ROW.match(line)
        if not m:
            continue
        chain = m.group(1)
        documented.add(chain)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < _CHAIN_TABLE_COLUMNS:
            missing_id_column.append(chain)
            documented_slots[chain] = []
            continue
        documented_slots[chain] = _CHAIN_ID_CELL.findall(cells[3])
    if not documented:
        findings.append(f"{rel(_RELIABILITY_MD)}: 未找到 §4.2 Provider Chain 降级路径表（表行须以 | `链路名` | 开头）")
        return findings
    expected = set(_DEFAULT_CHAINS)
    for chain in sorted(expected - documented):
        findings.append(f"{rel(_RELIABILITY_MD)}: §4.2 表缺少链路 `{chain}`（`_DEFAULT_CHAINS` 有定义，须补行）")
    for chain in sorted(documented - expected):
        findings.append(f"{rel(_RELIABILITY_MD)}: §4.2 表列出链路 `{chain}` 但 `_DEFAULT_CHAINS` 无此链（幽灵行）")
    for chain in sorted(documented & expected):
        if chain in missing_id_column:
            findings.append(
                f"{rel(_RELIABILITY_MD)}: §4.2 链路 `{chain}` 行缺 provider id 列"
                f"（须为 {_CHAIN_TABLE_COLUMNS} 列：名称/主链路/备用链路/provider id/回退条件）"
            )
            continue
        doc_slots = documented_slots[chain]
        code_slots = list(_DEFAULT_CHAINS[chain])
        if doc_slots == code_slots:
            continue
        missing = [s for s in code_slots if s not in doc_slots]
        extra = [s for s in doc_slots if s not in code_slots]
        detail = []
        if missing:
            detail.append(f"漏槽 {missing}")
        if extra:
            detail.append(f"多槽 {extra}")
        if not detail:
            detail.append("顺序不一致")
        findings.append(
            f"{rel(_RELIABILITY_MD)}: §4.2 链路 `{chain}` 槽位不一致（{'；'.join(detail)}）"
            f"——文档 {doc_slots} vs 代码 {code_slots}"
        )
    return findings
