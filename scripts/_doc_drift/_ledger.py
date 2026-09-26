"""`check-doc-drift` 台账族检查 —— 归档索引完整性、管理文档分区纪律、Extended Thinking 支持矩阵。"""

from __future__ import annotations

import re
from pathlib import Path
from _checklib import REPO_ROOT, rel

from _doc_drift._shared import (
    _CHANGELOG_MD,
    _MANAGEMENTS,
    _MANUALS,
    _PLAN_MD,
    _REVIEW_FINDINGS_MD,
    _doc_section,
)


_RF_ID = re.compile(r"\brf-(\d+)\b")


_PLAN_ID = re.compile(r"\bplan-(\d+)\b")


_CHANGELOG_HEADER = re.compile(r"^## \[([^\]]+)\]", re.M)


_RF_ROW_ID = re.compile(r"^\|\s*\*\*(rf-\d+)\*\*", re.M)


_PLAN_HEADING_ID = re.compile(r"^\s*#{2,4}\s*(?:🔲|✅)\s*`?(plan-\d+)", re.M)


_PLAN_DONE_HEADING_ID = re.compile(r"^\s*#{2,4}\s*✅\s*`?(plan-\d+)", re.M)


_ARCHIVE_INDEX_PAIRS: tuple[tuple[Path, str], ...] = (
    (_MANAGEMENTS / "changelog.md", "archived_changelog."),
    (_MANAGEMENTS / "plan.md", "archived_plan."),
    (_MANAGEMENTS / "review-findings.md", "archived_review-findings."),
)


def check_archive_index(docs: dict[Path, str] | None = None) -> list[str]:
    """校验管理文档的归档索引与 ``docs-stm/archive/`` 实际文件双向一致。

    **不读传入的 docs 映射**：历史记录类（如 changelog）不在 `_scan_docs()` 的扫描面内
    （正是本次缺口所在），故本项直接读文件；``docs`` 参数仅作兼容占位（传入亦被忽略）。
    """
    findings: list[str] = []
    archive_root = REPO_ROOT / "docs-stm" / "archive"
    for doc_path, prefix in _ARCHIVE_INDEX_PAIRS:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        on_disk = {p.name for p in archive_root.rglob("*.md") if p.name.startswith(prefix)}
        referenced = {name for name in on_disk if name in text}
        for name in sorted(on_disk - referenced):
            findings.append(f"{rel(doc_path)}: 归档索引缺少 `{name}`（该归档文件实际存在，须补索引条目）")
        # 反向：索引引用了不存在的归档文件名
        for name in sorted(re.findall(rf"{re.escape(prefix)}[0-9a-z.]+\.md", text)):
            if name not in on_disk:
                findings.append(f"{rel(doc_path)}: 归档索引引用的 `{name}` 在 docs-stm/archive/ 下不存在")
    return findings


def audit_management_partitions(
    *,
    review_findings: str,
    plan: str,
    changelog: str,
    archived_changelogs: list[str] | None = None,
    archived_plans: list[str] | None = None,
) -> list[str]:
    """审计管理文档的未完成/已解决/已归档分区纪律（纯函数，便于用例直测）。

    规则（对应两类历史失误）：
      A. review-findings：同一 rf 不得同时出现在「未完成」与「已解决」分区（**只认表行首列的条目标识**，
         正文里提及别的编号不算登记）；**已解决项必须在 changelog（现行 + 归档）有修复记录**——
         未完成项被误置已解决区时必然不满足此条（这正是「误将未完成项放入已解决表」类失误的可检特征）。
      B. plan：未完成区不得出现 ✅ 已完成项，也不得列已归档项（已完成项须移入归档）；
         未完成/已归档条目均只认**条目标题**，正文提及不算。
      C. changelog：现行文件只允许一个版本段头且必须为开发段
         （正式版本段落须归档至 `archived_changelog.*.md`）。
    """
    findings: list[str] = []

    pending = _doc_section(review_findings, "## 当前待处理问题", "## 已解决问题")
    resolved = _doc_section(review_findings, "## 已解决问题", "### 归档档案")
    pending_ids = set(_RF_ROW_ID.findall(pending))
    resolved_ids = set(_RF_ROW_ID.findall(resolved))
    for rid in sorted(pending_ids & resolved_ids):
        findings.append(f"{rel(_REVIEW_FINDINGS_MD)}: `{rid}` 同时列在「待处理」与「已解决」分区（分区互斥）")
    changelog_all = changelog + "".join(archived_changelogs or [])
    for rid in sorted(resolved_ids):
        if rid not in changelog_all:
            findings.append(
                f"{rel(_REVIEW_FINDINGS_MD)}: 已解决项 `{rid}` 在 changelog（现行 + 归档）无修复记录"
                "——未完成项不得置于已解决区"
            )

    todo = _doc_section(plan, "## 当前迭代待办", "## 归档")
    for pid in _PLAN_DONE_HEADING_ID.findall(todo):
        findings.append(f"{rel(_PLAN_MD)}: 未完成区出现已完成项 `{pid}`（已完成项须移入归档）")
    todo_ids = set(_PLAN_HEADING_ID.findall(todo))
    archived_plan_ids: set[str] = set()
    for text in archived_plans or []:
        archived_plan_ids |= set(_PLAN_DONE_HEADING_ID.findall(text))
    for pid in sorted(todo_ids & archived_plan_ids):
        findings.append(f"{rel(_PLAN_MD)}: `{pid}` 已归档却仍列在未完成区（分区互斥）")

    if changelog:
        headers = _CHANGELOG_HEADER.findall(changelog)
        if not headers:
            findings.append(f"{rel(_CHANGELOG_MD)}: 缺少版本段头（`## [x.y.z] - ...`）")
        elif len(headers) > 1:
            findings.append(
                f"{rel(_CHANGELOG_MD)}: 现行 changelog 含 {len(headers)} 个版本段头（已发布版本段须随发布移入归档）"
            )
        elif not headers[0].endswith("-dev"):
            findings.append(
                f"{rel(_CHANGELOG_MD)}: 现行 changelog 段头 `{headers[0]}` 非开发版本（正式版本段落须归档）"
            )
    return findings


def check_management_partitions() -> list[str]:
    """读三份管理文档 + 归档文件后执行分区纪律审计（文件缺失按空串参与，不抛异常）。"""

    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    archive_root = REPO_ROOT / "docs-stm" / "archive"
    return audit_management_partitions(
        review_findings=_read(_REVIEW_FINDINGS_MD),
        plan=_read(_PLAN_MD),
        changelog=_read(_CHANGELOG_MD),
        archived_changelogs=[_read(p) for p in sorted(archive_root.rglob("archived_changelog.*.md"))],
        archived_plans=[_read(p) for p in sorted(archive_root.rglob("archived_plan.*.md"))],
    )


_THINKING_MANUAL = _MANUALS / "how-to-config-llm.md"


_THINKING_FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
    "claude": ("claude-",),
    "deepseek": ("deepseek-",),
    "gemini": ("gemini-",),
    "kimi": ("kimi-",),
}


_THINKING_FAMILY_LABELS: dict[str, tuple[str, ...]] = {
    "claude": ("claude", "anthropic"),
    "deepseek": ("deepseek",),
    "gemini": ("gemini",),
    "kimi": ("kimi", "月之暗面"),
}


def _thinking_families() -> tuple[set[str], set[str], set[str]]:
    """从代码前缀名单派生 ``(支持族, effort 族, 默认开思考族)``。"""
    from src.python.llm.api_base import (
        _THINKING_DEFAULT_ON_PREFIXES,
        _THINKING_EFFORT_MODEL_PREFIXES,
        _THINKING_SUPPORTED_PREFIXES,
    )

    def _families(prefixes: tuple[str, ...]) -> set[str]:
        return {
            family
            for family, pats in _THINKING_FAMILY_PREFIXES.items()
            if any(str(p).startswith(pat) for p in prefixes for pat in pats)
        }

    return (
        _families(tuple(_THINKING_SUPPORTED_PREFIXES)),
        _families(tuple(_THINKING_EFFORT_MODEL_PREFIXES)),
        _families(tuple(_THINKING_DEFAULT_ON_PREFIXES)),
    )


def check_thinking_support_matrix(doc_text: str | None = None) -> list[str]:
    """校验手册 Extended Thinking 章节的矩阵与措辞覆盖代码支持的全部厂商族。

    历史缺口：手册支持 bullet 列表已含 Kimi，但下方「模型差异」对比表与「仅 Claude /
    Gemini」式措辞未同步——同一章节自相矛盾，且无任何断言覆盖。本项三项断言：
      ① 对比表（表头 `| 维度 |`）须列全代码支持族；
      ② 含「仅」且提到 thinking/思考的句子，若枚举了厂商则须包含全部 **budget_tokens 族**
         （支持族减 effort 族）——防「仅 A / B」式封闭枚举漏族；
      ③ 默认开思考族须在手册该章节出现「默认开思考」（或「默认开启思考」）提示。
    """
    findings: list[str] = []
    text = doc_text
    if text is None:
        text = _THINKING_MANUAL.read_text(encoding="utf-8") if _THINKING_MANUAL.exists() else ""
    if not text:
        return findings

    supported, effort, default_on = _thinking_families()
    if not supported:
        return findings  # 名单未登记则不判定（防误报）

    header = next((line for line in text.splitlines() if line.startswith("| 维度 |")), "")
    if not header:
        findings.append(f"{rel(_THINKING_MANUAL)}: 未找到 Extended Thinking「模型差异」对比表（表头 `| 维度 |`）")
        return findings
    low_header = header.lower()
    for family in sorted(supported):
        if not any(label in low_header for label in _THINKING_FAMILY_LABELS[family]):
            findings.append(
                f"{rel(_THINKING_MANUAL)}: 「模型差异」对比表缺少厂商列 `{family}`（代码支持名单含该族，矩阵须列全）"
            )

    budget_families = supported - effort
    for lineno, line in enumerate(text.splitlines(), 1):
        # 只判「预算族枚举」类句子：含「仅」且命中 budget 概念词
        # （否则会把「DeepSeek 强制推理说明」「已停用别名」等无关行误当枚举句）
        if "仅" not in line or not any(k in line for k in ("thinking_budget", "budget_tokens", "硬性约束")):
            continue
        mentioned = {
            family
            for family in supported
            if any(label in line.lower() or label in line for label in _THINKING_FAMILY_LABELS[family])
        }
        if mentioned and not budget_families <= mentioned:
            findings.append(
                f"{rel(_THINKING_MANUAL)}:{lineno}: 「仅」式措辞遗漏 budget_tokens 族厂商 "
                f"{sorted(budget_families - mentioned)}（该句枚举须与代码一致）"
            )

    for family in sorted(default_on):
        labels = _THINKING_FAMILY_LABELS[family]
        has_hint = any(
            ("默认开思考" in line or "默认开启思考" in line)
            and any(label in line or label in line.lower() for label in labels)
            for line in text.splitlines()
        )
        if not has_hint:
            findings.append(
                f"{rel(_THINKING_MANUAL)}: 默认开思考族 `{family}` 缺少「默认开思考」提示"
                "（该族未传思考参数会自动思考，须告知用户）"
            )
    return findings
