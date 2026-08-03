#!/usr/bin/env python3
"""文档历史变更痕迹检查脚本。

扫描面向读者的仓库文档（.md 全文），检查是否含代码历史迭代、版本号标记、
任务编号引用、归档文件引用等变更痕迹。此类文档应只描述"当前是什么/做什么"，
不应记录"从哪里来、怎么变的"；历史记录应集中在管理文档
（changelog.md / review-findings.md / plan.md）中。

受检范围：
  - 项目根 README.md
  - docs-stm/managements/（排除 changelog.md / review-findings.md / plan.md）
  - docs-stm/manuals/

豁免范围（历史/计划记录性质，允许历史痕迹与归档引用）：
  - docs-stm/plan/ 中间计划文档
  - docs-stm/archive/ 归档文档
  - docs-stm/tmp/ 运行时临时产物

豁免内容（当前状态 / 流程描述，非历史痕迹）：
  - 管理文档版本头（"文档版本：0.9.9-dev"，版本号一致性要求，仅行首锚定豁免）
  - Markdown 围栏代码块（``` 包裹）内命令/配置示例，非文档叙述
  - 需求编号（requirements.md 的 R-LLM-ER-01 等需求条目 ID）
  - folders.md 目录树行（│ ├ └ 开头，记录目录结构，含 archive/ 属合法指向）
  - 当前能力描述（暂不支持 / 不再支持 / 不正式支持）
  - 门禁与发布流程描述（发布版本前 / P0~P3 / --mode / git tag / git pull）
  - 工具使用场景（pytest --ff 等）
  - 模型/环境名（Gemini 旧版 / 旧版 Python）

用法：
  python scripts/check-doc-traces.py           # 检查全部
  python scripts/check-doc-traces.py -v        # 详细输出（含豁免行信息）
  python scripts/check-doc-traces.py --ci      # CI 模式（仅输出 文件:行号，非零退出码）

退出码：
  0 — 全部通过（无可疑痕迹）
  1 — 发现高置信度痕迹（HIGH/ARCHIVE/CODE），应修复后再提交
  2 — 仅 LOW 级别痕迹，建议人工复核
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
DOC_DIRS = [
    REPO_ROOT / "docs-stm" / "managements",
    REPO_ROOT / "docs-stm" / "manuals",
]
# 豁免文档：历史/计划记录性质（changelog/review-findings/plan 记录变更、自审与计划）
SKIP_FILES = {"changelog.md", "review-findings.md", "plan.md"}
# 不扫描目录：archive（归档本身）/ plan（中间计划）/ tmp（运行时临时）
SKIP_DIRS = {"archive", "plan", "tmp"}


# ═══════════════════════════════════════════════════════════════
#  匹配模式定义
# ═══════════════════════════════════════════════════════════════
#  每项：(pattern, category, description)
#    pattern      — 正则表达式（在文档行中匹配）
#    category     — 置信度/分类
#    description  — 简短说明
#
# 分类说明：
#   ARCHIVE   — 归档文件/目录引用，面向读者文档不应指向已归档内容
#   CODE      — 任务编号引用（rf-N / plan-N / R-N），历史记录标识
#   HIGH      — 高置信度历史痕迹（来源叙述/历史实现/变更节点/迭代/版本号）
#   LOW       — 需人工判断的变更/过渡/待办描述（可能是当前能力也可能是痕迹）


def _doc_patterns() -> list[tuple[str, str, str]]:
    """文档历史痕迹模式（针对 .md 全文语义）。"""
    return [
        # ── ARCHIVE：归档引用 ──
        (r"(?:docs-stm/|\.\./)?archive/", "ARCHIVE", "归档目录引用（archive/）"),
        (r"archived_[A-Za-z0-9._-]+", "ARCHIVE", "归档文件引用（archived_*）"),
        (r"归档文件\s*[:：]?\s*[`]?archive/", "ARCHIVE", "归档路径说明"),
        # ── CODE：任务编号引用 ──
        (r"\brf-\d+", "CODE", "任务编号引用（rf-N）"),
        (r"\bplan-\d+", "CODE", "任务编号引用（plan-N）"),
        (r"\bR-\d+(?!-?[A-Z])", "CODE", "任务编号引用（R-N）"),
        # ── HIGH：来源叙述 / 历史实现 / 变更节点 / 迭代 / 版本号 ──
        (
            r"(?:自|从|由)\s*[`\w./_-]+\.(?:py|js|html|md)\s*(?:提取|拆分|迁移|合并|复用|分离)",
            "HIGH",
            "来源叙述（从XX.py提取/拆分/迁移）",
        ),
        (r"(?:拆分|提取|分离)(?:自|到|成)\s*[A-Za-z_][\w.-]*", "HIGH", "来源叙述（拆分自/分离为XX）"),
        (r"(?:合并|迁移|提取)自\s*[`\w._-]+", "HIGH", "来源叙述（合并自/迁移自/提取自）"),
        (r"已迁移", "HIGH", "迁移痕迹（已迁移）"),
        (r"原(?:逻辑|实现|方案|代码|写法|做法|设计)", "HIGH", "原逻辑/原实现（历史实现叙述）"),
        (r"旧\s*[`\w._-]+\s*(?:逻辑|实现|方案|要求|做法|方式|判定|分类)", "HIGH", "旧XX逻辑/要求（历史实现叙述）"),
        (r"曾(?:经)?(?:用|作为|属于|采用|以)", "HIGH", "曾用/曾作为（历史实现叙述）"),
        (r"原为[\w._-]+", "HIGH", "原为XX（历史来源叙述）"),
        (r"(?:后来|之后|随后)\s*(?:改[为成]|换[为成]|引入|移除|新增)", "HIGH", "变更痕迹（后来改为/之后引入）"),
        (r"已更名|已重命名|改名为|重命名为|重新命名", "HIGH", "重命名痕迹"),
        (r"\bIter(?:ation)?\s*\d+\b", "HIGH", "Iter 迭代标记"),
        (r"迭代\s*(?:\d+|任务|计划)", "HIGH", "迭代/任务标记"),
        (r"\bv\d+\.\d+\.\d+(?:-dev)?\b", "HIGH", "版本号标记"),
        #  历史状态叙述：需后接状态动词才命中，避免误伤"早期数据仍保留"
        #  （当前运行时行为）等合法描述。
        (r"(?:原先|最初|早期)(?:是|为|使用|采用|属于)", "HIGH", "原先/最初/早期（历史状态叙述）"),
        # ── LOW：需人工判断的变更/过渡/待办描述（可能是当前能力也可能是痕迹） ──
        (r"重构[为成到]", "LOW", "重构为/重构到（变更描述，需判断）"),
        (r"已废弃|已弃用", "LOW", "废弃/弃用标注（当前指引或历史，需判断）"),
        (r"曾(?:经)?被", "LOW", "曾被/曾经被（历史被动叙述）"),
        (r"尚未[实现处理支持完成覆盖]", "LOW", "尚未完成/实现（待办性质）"),
        (r"待[办做处补充修复]", "LOW", "待办/待处理"),
        (r"后续\s*(?:版本|迭代|优化|需要|再处理)", "LOW", "后续版本/迭代（未来计划）"),
        (r"过渡方案|过渡期|过渡性", "LOW", "过渡性方案说明"),
    ]


def _exclude_lines() -> list[re.Pattern]:
    """文档合法内容豁免模式（命中则跳过该行）。"""
    return [
        # ── 管理文档版本头（版本号一致性要求） ──
        # 行首锚定（可带 > 引用块或 ## 标题符）：仅豁免版本头本身，
        # 不豁免行中叙述（如"该功能于版本：v0.8.9 中引入"应命中版本号模式）。
        re.compile(r"^\s*[#>]*\s*(?:文档|当前|文档内容|主文档)\s*版本\s*[:：]\s*v?\d"),
        re.compile(r"文档版本号"),
        # ── 门禁 / 发布流程描述 ──
        re.compile(r"发布版本前"),
        re.compile(r"发布前|发布后|提交前|合并前|提交后"),
        re.compile(r"版本控制"),
        re.compile(r"\bP[0-3]\b"),
        re.compile(r"--mode\s+verify"),
        re.compile(r"--mode\s+regression"),
        re.compile(r"test_runner\.py"),
        re.compile(r"check-version-consistency\.py"),
        re.compile(r"check-code-traces\.py"),
        re.compile(r"git tag|git pull|打 tag"),
        # ── 当前能力 / 限制描述（组合限定，避免"暂不采用A改用B"等变更描述被豁免） ──
        re.compile(r"暂不(?:支持|提供|纳入|实现|处理|参与|显示|包含|在|可用|属于|单独)"),
        re.compile(r"不正式支持"),
        re.compile(r"不再支持"),
        re.compile(r"已不再(?:支持|推荐|使用|提供)"),
        re.compile(r"仍不"),
        # ── 工具使用场景 ──
        re.compile(r"--ff\b|--failed-first"),
        re.compile(r"修复后确认修复"),
        # ── 环境 / 模型名 ──
        re.compile(r"旧版 Python|旧版 Win|Windows 7|Gemini 旧版"),
        # ── 测试场景 / 需求条目 / 导航项名 ──
        re.compile(r"版本兼容"),
        re.compile(r"^\s*R-[A-Z]+-\d+"),  # requirements 需求条目 ID（行首）
        re.compile(r"迭代计划"),  # README 导航项（指向 plan.md）
        re.compile(r"子文件"),  # 测试组织规范（拆分到子文件 test_xxx_partN.py）
        # ── folders.md 目录结构记录（含 archive/ 属合法指向） ──
        re.compile(r"^\s*[│├└]"),  # 目录树行
        re.compile(r"archive/\s*\|"),  # 统计表行（如 | ├ archive/ | 版本归档 |）
        # ── 工具自身说明（描述脚本跳过/豁免归档目录，而非引用归档内容） ──
        re.compile(r"(?:豁免|跳过|不扫描|排除).*archive/"),
    ]


# 模块级缓存（模式列表固定，避免逐行重复构建）
_DOC_PATTERNS = _doc_patterns()
_COMPILED_EXCLUDE = _exclude_lines()


def _is_excluded(line: str) -> bool:
    """检查该行是否命中豁免（合法当前状态/流程描述）。"""
    return any(p.search(line) for p in _COMPILED_EXCLUDE)


def scan_file(fpath: Path, verbose: bool) -> list[tuple[int, str, str, str]]:
    """扫描单个文档，返回 [(行号, 分类, 模式说明, 行内容), ...]

    Markdown 围栏代码块（``` 包裹）内是命令/配置示例，非文档叙述，
    不参与历史痕迹匹配（避免 `git tag v0.9.9`、`APP_VERSION` 示例误报）。
    """
    hits: list[tuple[int, str, str, str]] = []
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return hits

    in_code_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        # 围栏代码块：``` 开闭（含可选的 ```lang 标记）
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if verbose:
                print(f"    (codeblock) L{lineno}: {stripped[:60]}")
            continue
        if in_code_block:
            if verbose:
                print(f"    (codeblock) L{lineno}: {stripped[:60]}")
            continue
        if _is_excluded(stripped):
            if verbose:
                print(f"    (excluded) L{lineno}: {stripped[:80]}")
            continue
        for pat, cat, desc in _DOC_PATTERNS:
            if re.search(pat, stripped):
                hits.append((lineno, cat, desc, stripped[:120]))
                break  # 每行仅报告首个匹配

    return hits


def _iter_docs() -> list[Path]:
    """收集受检文档（README + managements/manuals 中未被豁免的 .md）。"""
    docs: list[Path] = []
    if README_PATH.exists():
        docs.append(README_PATH)
    for doc_dir in DOC_DIRS:
        if not doc_dir.exists():
            continue
        for fpath in sorted(doc_dir.rglob("*.md")):
            if fpath.name in SKIP_FILES:
                continue
            if any(part in SKIP_DIRS for part in fpath.relative_to(REPO_ROOT).parts):
                continue
            docs.append(fpath)
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描文档中的历史变更痕迹")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="详细输出（含豁免行信息）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式：仅输出 文件名:行号，非零退出码",
    )
    args = parser.parse_args()

    total_hits = 0
    high_count = 0
    low_count = 0
    summary: dict[str, int] = {}

    for doc in _iter_docs():
        hits = scan_file(doc, args.verbose)
        if not hits:
            continue
        rel = doc.relative_to(REPO_ROOT)
        if not args.ci:
            print(f"\n  {rel}")

        for lineno, cat, desc, text in hits:
            total_hits += 1
            summary[cat] = summary.get(cat, 0) + 1
            is_high = cat in ("HIGH", "ARCHIVE", "CODE")
            if is_high:
                high_count += 1
            else:
                low_count += 1

            if args.ci:
                print(f"{rel}:{lineno} [{cat}] {desc} — {text}")
            else:
                marker = "[ERR]" if is_high else "[!]"
                print(f"    {marker} L{lineno:>4} [{cat}] {desc}")
                if args.verbose:
                    print(f"           {text}")

    print()
    if total_hits == 0:
        print("[OK] 未发现历史变更痕迹，文档干净")
        return 0

    cat_stats = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    print(f"[!] 发现 {total_hits} 处可疑痕迹（{cat_stats}）")
    if high_count > 0:
        print(f"    {high_count} 处高置信度（HIGH/ARCHIVE/CODE），应从文档中移除")
        return 1
    print(f"[!] 仅 {low_count} 处 LOW 级别痕迹（需人工判断），建议复核")
    return 2


if __name__ == "__main__":
    sys.exit(main())
