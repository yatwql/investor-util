#!/usr/bin/env python3
"""文档历史变更痕迹检查脚本。

检查面向读者的仓库文档是否残留历史痕迹，保证正文只反映最新状态。

四条核心规则：
  1. 文档正文内容不得带有历史痕迹和历史变更（版本号标记、来源叙述、
     原/旧实现、迁移/重命名、任务编号引用、迭代标记等），只描述
     "当前是什么/做什么"。changelog.md / plan.md / review-findings.md
     例外（它们是历史/计划记录）。
  2. 除上述三个例外文档外，其他管理文档与用户文档的正文内容不得引用
     归档文件（docs-stm/archive/ 下的目录或 archived_*.md）。
     例外：folders.md 的目录树（│ ├ └ 行）可引用 archive 目录及其
     文件名——目录树记录项目结构，archive/ 条目是结构的一部分。
  3. 章节编号引用：任何面向读者文档的正文不得用数字章节号（"N 章" /
     "第 N 章"）指代报告具体章节，须用语义章节名（「X」章），用户才能
     看懂。章节数量/序数表述（共 N 章 / N 章基线 / 减至 N 章 / 出现
     第 N 章等）是合法计数，豁免。该检查**同样适用于** changelog.md /
     plan.md / review-findings.md 与 docs-stm/plan/ 目录——它们虽是
     历史/计划记录（豁免版本号等历史痕迹），但数字章节暗号同样影响
     可读性，仅对它们应用本条章节编号检查。
  4. 迭代轮次引用：任何面向读者文档的正文不得用数字轮次（"第 N 轮" /
     "经 N 轮" / "N 轮" / "轮 N"）指代开发迭代历史，须改为语义描述。
     轮次数量/运行时表述（共 N 轮 / 计划分 N 轮 / N 轮每轮 / 轮询 /
     轮动/轮换/轮番/轮涨/轮跌 / 第 N 轮循环）是合法计数或业务/运行时
     概念，豁免。该检查**不适用于** changelog.md / plan.md /
     review-findings.md 与 docs-stm/plan/——它们作为历史/计划记录，
     "轮 N"是正式记录载体（changelog 记"轮 N 落地"、迭代计划按轮排期）。
  5. 架构约束代号（C1~C20）：任何文档正文不得以代号引用架构约束（如
     "C19 契约""C20 图下说明"），须用语义描述（数据契约/图下说明等）。
     约束定义处（technical.md / llm-technical.md，CIPHER_EXEMPT_FILES）
     正文大量引用 C1~C20 属定义载体，豁免；其余文档（含 changelog.md /
     plan.md / review-findings.md 与 docs-stm/plan/）一律禁。

受检范围：
  - 项目根 README.md
  - docs-stm/managements/（排除 changelog.md / review-findings.md / plan.md）
  - docs-stm/manuals/
  - 章节编号检查另覆盖 changelog.md / review-findings.md / plan.md 与
    docs-stm/plan/（仅章节编号模式，不检查其他历史痕迹）

豁免范围（历史/计划记录性质，允许历史痕迹与归档引用）：
  - docs-stm/plan/ 中间计划文档（历史痕迹豁免，章节编号不豁免）
  - docs-stm/archive/ 归档文档
  - docs-stm/tmp/ 运行时临时产物

豁免内容（当前状态 / 流程描述 / 结构记录，非历史痕迹）：
  - 管理文档版本头（"文档版本：0.9.10-dev"，版本号一致性要求，仅行首锚定豁免）
  - Markdown 围栏代码块（``` 包裹）内命令/配置示例，非文档叙述
  - 需求编号（requirements.md 的 R-LLM-ER-01 等需求条目 ID）
  - folders.md 目录树行（│ ├ └ 开头，记录目录结构，可含 archive/ 指向）
  - folders.md 统计表行（如 | ├ archive/ | 版本归档 |，记录目录计数）
  - 当前能力描述（暂不支持 / 不再支持 / 不正式支持）
  - 运行时产物归档描述（"归档版" / "归档目录" / "历史归档至 YYYYMMDD/"——
    指 reports/ 下的报告文件按日期归档，非仓库 docs-stm/archive/）
  - 门禁与发布流程描述（发布版本前 / P0~P3 / --mode / git tag / git pull）
  - 工具使用场景（pytest --ff 等）
  - 模型/环境名（Gemini 旧版 / 旧版 Python）
  - 工具自身说明（描述脚本跳过/豁免归档目录与归档引用）

用法：
  python scripts/check-doc-traces.py           # 检查全部
  python scripts/check-doc-traces.py -v        # 详细输出（含豁免行信息）
  python scripts/check-doc-traces.py --ci      # CI 模式（仅输出 文件:行号，非零退出码）

退出码：
  0 — 全部通过（无可疑痕迹）
  1 — 发现高置信度痕迹（HIGH/ARCHIVE/CODE/CIPHER/CHAPTER/ROUND），应修复后再提交
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
# 架构约束代号（C1~C20）豁免文件：约束定义处正文大量引用 C1~C20（技术名称表），
# 属定义载体而非"暗号残留"，允许使用代号。其余文档正文一律不得出现约束代号。
CIPHER_EXEMPT_FILES = {"technical.md", "llm-technical.md"}
# ── 本工具自身豁免（结构性 + 文档化） ──
# 本脚本只扫描 .md（见 _iter_docs），不扫描 .py，故自身天然豁免——这是
# "结构性豁免"（扫描范围不含自身文件类型）。docstring 与 _doc_patterns()
# 模式说明区包含被检测类别的特征字面量（版本号、任务编号、迁移/重命名
# 描述词等），属于"检查规则的元描述"，不是文档历史痕迹。
# 若将来扩展扫描范围至 .yaml/.conf 等，需为这些类型补充 docstring/说明区
# 的结构性跳过（参考 check-code-traces.py 的 _is_tool_self 模式豁免）。


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
#   CIPHER    — 架构约束代号（C1~C20，technical.md 定义）——约束定义处
#               （technical.md/llm-technical.md）豁免，其余文档正文须用语义描述
#   HIGH      — 高置信度历史痕迹（来源叙述/历史实现/变更节点/迭代/版本号）
#   CHAPTER   — 章节编号引用（"N 章"/"第 N 章"指代报告具体章节，须用语义章节名）
#   ROUND     — 迭代轮次引用（"第 N 轮"/"N 轮"/"轮 N"指代开发迭代历史，须用语义描述）
#   LOW       — 需人工判断的变更/过渡/待办描述（可能是当前能力也可能是痕迹）


def _doc_patterns() -> list[tuple[str, str, str]]:
    """文档历史痕迹模式（针对 .md 全文语义）。"""
    return [
        # ── ARCHIVE：归档引用（指向仓库 docs-stm/archive/ 的历史记录） ──
        #  仓库归档路径引用（docs-stm/archive/、../archive/、裸 archive/）
        (r"(?:docs-stm/|\.\./)?archive/", "ARCHIVE", "归档目录引用（archive/）"),
        #  归档文件名引用（archived_*.md）
        (r"archived_[A-Za-z0-9._-]+", "ARCHIVE", "归档文件引用（archived_*）"),
        #  归档路径说明（"归档文件：`../archive/...`"）
        (r"归档文件\s*[:：]?\s*[`]?archive/", "ARCHIVE", "归档路径说明"),
        #  无显式 archive/ 前缀的归档引用（已/可/应 归档至 某目录），如
        #  "已归档至 archive/"、"归档至 docs-stm/archive/"——须含"归档"动词 + 归档目标
        (
            r"归档\s*(?:至|到|于|在|入|完成|处理)\s*[`]?(?:docs-stm/|\.\./)?archive",
            "ARCHIVE",
            "归档引用（归档至 archive/ 等）",
        ),
        #  明确指向归档文件的叙述（"归档文件：archived_x.md" / "归档于 archived_*"）
        (r"(?:归档文件|归档于|归档到|归档至)\s*[:：]?\s*[`]?archived_", "ARCHIVE", "归档文件引用（归档至 archived_*）"),
        #  完成态归档动作（"已归档至 X" / "归档完成"），指向历史归档行为。
        #  收紧判定：仅匹配"已归档至/到/于 + 非运行时产物目标"——归档目标不是
        #  reports/、YYYYMMDD/ 等运行时产物（如"报告已归档到 reports/"、"归档至
        #  YYYYMMDD/ 子目录"为当前功能描述，应豁免）。孤立的"已归档"不命中
        #  （"已归档版报告"是运行时产物描述）。
        #  lookahead 内部带 (?:\s*)：外层的贪婪 \s* 在回溯为 0 个空白时，
        #  视线会落在空格字符上导致排除失败，故让 lookahead 自身也能跳过空白。
        #  排除的运行时产物目标：reports?/（报告输出目录）、报告输出目录（中文写法）、
        #  `?\d{8}`?（纯数字日期目录）、`?YYYYMMDD（日期模板）、日期子目录。
        (
            r"归档\s*(?:至|到|于|在|完成|处理)\s*(?!(?:\s*)(?:reports?/|报告输出目录|`?\d{8}`?|`?YYYYMMDD|日期子目录))",
            "ARCHIVE",
            "归档引用（归档至某处/归档完成）",
        ),
        # ── CODE：任务编号引用 ──
        (r"\brf-\d+", "CODE", "任务编号引用（rf-N）"),
        (r"\bplan-\d+", "CODE", "任务编号引用（plan-N）"),
        (r"\bR-\d+(?!-?[A-Z])", "CODE", "任务编号引用（R-N）"),
        (r"[A-Za-z]系列", "CODE", "任务批次系列别名（如 B系列/F系列/G系列）"),
        (r"(?<![A-Za-z])[A-Za-z]_series\b", "CODE", "任务批次系列别名英文形式（如 b_series）"),
        # ── CIPHER：架构约束代号（C1~C20）──
        #  约束定义处（technical.md/llm-technical.md，CIPHER_EXEMPT_FILES）豁免；
        #  其余文档正文出现 C1~C20 属"暗号"，须改写为语义描述（原子写入/会话缓存/
        #  数据契约/图下说明等）。C+1~20 两位精确匹配，避免误伤十六进制色值
        #  （C00000）、C21+ 等；前限非 ASCII 字母/数字，避免 AB14/MC19 内嵌命中。
        (
            r"(?<![A-Za-z0-9])C(?:[1-9]|1[0-9]|20)\b",
            "CIPHER",
            "架构约束代号（C1~C20，须用语义描述替代，如原子写入/会话缓存/数据契约）",
        ),
        # ── HIGH：来源叙述 / 历史实现 / 变更节点 / 迭代 / 版本号 ──
        (
            r"(?:自|从|由)\s*[`\w./_-]+\.(?:py|js|html|md)\`*\s*(?:提取|拆分|拆出|迁移|合并|复用|分离)",
            "HIGH",
            "来源叙述（从XX.py提取/拆分/拆出/迁移）",
        ),
        (r"(?:拆分|拆出|提取|分离)(?:自|到|成)\s*[A-Za-z_][\w.-]*", "HIGH", "来源叙述（拆分自/拆出自/分离为XX）"),
        (r"(?:合并|迁移|提取)自\s*[`\w._-]+", "HIGH", "来源叙述（合并自/迁移自/提取自）"),
        (r"已迁移", "HIGH", "迁移痕迹（已迁移）"),
        (r"原(?:逻辑|实现|方案|代码|写法|做法|设计)", "HIGH", "原逻辑/原实现（历史实现叙述）"),
        (
            r"原\s*[`A-Za-z_][A-Za-z0-9_.]*(?:\s*(?:契约|dict|数据|结构|结果))?\s*(?:迁移|改称|并入)",
            "HIGH",
            "原X迁移/改称（历史契约/命名变更叙述）",
        ),
        (r"旧\s*[`\w._-]+\s*(?:逻辑|实现|方案|要求|做法|方式|判定|分类)", "HIGH", "旧XX逻辑/要求（历史实现叙述）"),
        (r"(?:旧设计|旧架构|历史遗留)", "HIGH", "旧设计/历史遗留（历史迭代叙述）"),
        (r"未升级版|旧版|老版", "HIGH", "旧版/未升级版（版本对比痕迹）"),
        (r"曾(?:经)?(?:用|作为|属于|采用|以)", "HIGH", "曾用/曾作为（历史实现叙述）"),
        (r"原为[\w._-]+", "HIGH", "原为XX（历史来源叙述）"),
        (r"(?:后来|之后|随后)\s*(?:改[为成]|换[为成]|引入|移除|新增)", "HIGH", "变更痕迹（后来改为/之后引入）"),
        (r"已更名|已重命名|改名为|重命名为|重新命名", "HIGH", "重命名痕迹"),
        (r"\bIter(?:ation)?\s*\d+\b", "HIGH", "Iter 迭代标记"),
        (r"迭代\s*(?:\d+|任务|计划)", "HIGH", "迭代/任务标记"),
        (r"\bv\d+\.\d+\.\d+(?:-dev)?\b", "HIGH", "版本号标记"),
        #  无 v 前缀的裸版本号（本项目版本号为 0.x.y；限 0 开头避免误伤章节号 6.4.1、包版本 1.16.0 等）
        (r"\b0\.\d+\.\d+(?:-dev)?\b", "HIGH", "版本号标记（无 v 前缀）"),
        #  历史状态叙述：需后接状态动词才命中，避免误伤"早期数据仍保留"
        #  （当前运行时行为）等合法描述。
        (r"(?:原先|最初|早期)(?:是|为|使用|采用|属于)", "HIGH", "原先/最初/早期（历史状态叙述）"),
        # ── 时序历史叙述补强（与 check-code-traces 同步的"自我进化"）──
        #  "之前/此前/以前/曾经/原始/历史/旧逻辑/重构前/替代旧"等高频文档
        #  历史叙述词。仅时间词不足判历史（"之前缓存过"是运行时描述），
        #  故需后接动作/状态动词或"逻辑/实现/方案"等名词。
        (
            r"(?:之前|此前|以前|先前)\s*(?:是|为|直接|就|采用|使用|用|读取|实现|判断|属于|放在|在)",
            "HIGH",
            "此前/之前是（历史状态叙述）",
        ),
        (
            r"(?:之前|此前|以前|先前)(?:的)?(?:逻辑|实现|方案|做法|判定|版本|代码|判断)",
            "HIGH",
            "此前的逻辑/实现（历史实现叙述）",
        ),
        (r"曾经的?[^\s。，;]{0,6}(?:实现|逻辑|方案|做法|版本|代码)", "HIGH", "曾经的实现/逻辑（历史实现叙述）"),
        (r"曾考虑[过]?", "HIGH", "曾考虑（历史决策/备选方案叙述）"),
        (r"原始(?:版本|实现|方案|逻辑)", "HIGH", "原始版本/实现（历史状态叙述）"),
        (r"历史(?:版本|实现|逻辑|方案|做法)", "HIGH", "历史版本/实现（历史实现叙述）"),
        (r"(?:之前|此前|以前|旧|原|历史)(?:的)?版本\s*(?:为|号|是|中)", "HIGH", "旧/历史版本号（版本对比痕迹）"),
        (r"由\s*旧(?:文件|版本|逻辑|方案|实现)", "HIGH", "由旧XX（历史来源/改造叙述）"),
        (r"由旧[^\s。，;]{0,8}(?:改造|改来|升级而来|改写)", "HIGH", "由旧XX改造/改来（历史变更叙述）"),
        (
            r"(?:迁移|移到|移至|搬到|转入)\s*(?:到|至)?\s*新(?:模块|文件|目录|位置|路径|函数|类)",
            "HIGH",
            "迁移/移到新位置（迁移痕迹）",
        ),
        (r"重构\s*前", "HIGH", "重构前（重构历史叙述）"),
        (r"旧(?:逻辑|实现|方案|代码|写法|做法|设计|版本)", "HIGH", "旧逻辑/旧实现（历史实现叙述）"),
        (r"替代(?:了|掉|原有|旧的)?旧|替换旧", "HIGH", "替代旧/替换旧（历史变更叙述）"),
        (r"物理合并", "HIGH", "物理合并（章节/模块合并历史痕迹，须用语义描述当前结构）"),
        # ── CHAPTER：章节编号引用（用数字章节号指代报告具体章节） ──
        #  "N 章" / "第 N 章"（N=1~99）指代报告具体章节时用户无法识别，须改
        #  用语义章节名（「X」章）。中文数字同理：第X章（第一章~第二十章）与裸
        #  "三章"式（三章/二章/四章…）均检出；唯"一章"在本项目均为计数表述
        #  （一章三区块/一章两区块），不纳入裸数字模式以免误伤计数语义。章节
        #  数量/序数表述（共 N 章、N 章基线、减至 N 章、出现第 N 章、N→M 章、
        #  引号内"N 章"）由 _chapter_excludes() 豁免。负向前瞻 (?!节) 排除
        #  "章节"一词；[1-9]\d? 限 1~99、[一二三四五六七八九十]{1,2} 限 1~20，
        #  小节号"4.2"（数字后非"章"）不匹配。
        (r"第?\s*[1-9]\d?\s*章(?!节)", "CHAPTER", "章节编号引用（N 章/第 N 章，须用语义章节名）"),
        (r"第\s*[一二三四五六七八九十]{1,2}\s*章(?!节)", "CHAPTER", "章节编号引用（第X章，中文数字，须用语义章节名）"),
        (r"[二三四五六七八九十]{1,2}\s*章(?!节)", "CHAPTER", "章节编号引用（X章，中文数字，须用语义章节名）"),
        # ── ROUND：迭代轮次引用（用"第 N 轮"/"N 轮"/"轮 N"指代开发迭代历史） ──
        #  "第 14 轮" / "经 8 轮" / "轮 8" 是开发迭代痕迹（计划分轮实施，
        #  changelog 记"轮 N 落地"），面向读者文档正文不应记录迭代轮次，
        #  须改用语义描述。中文数字同理：第X轮（第三轮~第二十轮）与"轮X"
        #  （轮三）均检出；唯"第一轮/第二轮"多为运行时序数（LLM 圆桌会两轮
        #  辩论、两段式抓取的首/次轮），不纳入"第X轮"模式以免误伤正常行为。
        #  轮次数量/序数表述（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/
        #  轮换/轮番/轮涨/轮跌、第 N 轮循环）是合法计数或业务/运行时概念，
        #  由 _round_excludes() 豁免；`[1-9]\d?` 限 1~99、
        #  [一二三四五六七八九十]{1,2} 限 1~20，中文"一轮/两轮/三轮/二十轮"
        #  为计数表述（一轮行情是业务表述，非迭代轮次），不纳入裸"X轮"模式。
        (r"第\s*[1-9]\d?\s*轮", "ROUND", "迭代轮次引用（第 N 轮，属开发迭代痕迹）"),
        (r"[1-9]\d?\s*轮", "ROUND", "迭代轮次引用（N 轮，属开发迭代痕迹）"),
        (r"轮\s*[1-9]\d?\b", "ROUND", "迭代轮次引用（轮 N，属开发迭代痕迹）"),
        (r"第\s*[三四五六七八九十]{1,2}\s*轮", "ROUND", "迭代轮次引用（第X轮，中文数字，属开发迭代痕迹）"),
        (r"轮\s*[一二三四五六七八九十]{1,2}", "ROUND", "迭代轮次引用（轮X，中文数字，属开发迭代痕迹）"),
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
        # ── 工具自身说明（描述脚本跳过/豁免/禁止归档目录引用，而非引用归档内容） ──
        #  匹配"豁免/跳过/不扫描/排除/检查/不得/禁止 归档目录或归档引用"的工具说明行
        #  （含"正文不得引用 docs-stm/archive/"这类规则叙述）；
        #  可能只写"归档文件引用"而不含 archive/ 路径，故用"归档(?:目录|文件|引用|路径)"兼容
        re.compile(r"(?:豁免|跳过|不扫描|排除|检查|不得|禁止).*(?:archive/|归档(?:目录|文件|引用|路径))"),
        re.compile(r"版本头豁免"),  # 工具自身说明（描述版本头豁免规则，含示例版本号）
        # 工具说明行豁免：描述"检查哪些历史痕迹/来源叙述/原旧实现"的元描述，
        # 而非文档实际含历史痕迹（如 developer-guide.md 的检查规则说明）。
        # 命中"检查/检测/扫描 + 痕迹/来源/原旧/迁移/重命名/迭代 + 描述"组合才豁免。
        re.compile(
            r"(?:检查|检测|判定|扫描|检出|识别|不得带|不得包含|不得出现|不应记录|禁止出现).{0,12}(?:历史痕迹|来源叙述|原旧实现|迁移重命名|变更痕迹|迭代标记|版本号标记|归档引用|任务编号)"
        ),
        # ── 补强模式的误报排除（当前状态/运行时语义，非历史痕迹） ──
        re.compile(r"历史数据|历史(?:序列|区间|值|曲线|走势|数据点|K线|回撤)"),  # 运行时历史序列/指标
        re.compile(r"当前版本"),  # 当前版本是运行时状态描述
        re.compile(r"之前缓存|此前已|以前端|以前台"),  # 运行时缓存行为/方位描述
        re.compile(r"历史日期|历史[^。\n]{0,4}(?:快照|抓取|收盘|数据源)"),  # 数据范围/数据源历史
        # IP 地址 / 端口（运行时访问语义，如 Web 界面 http://127.0.0.1:8000）。
        #   IPv4 内嵌 0.x.x 子串（127.0.0.1→0.0.1）会被裸版本号模式误匹配，整行豁免。
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d{1,5})?"),  # IPv4 地址（含端口）
    ]


def _chapter_excludes() -> list[re.Pattern]:
    """章节数量/序数表述豁免（"N 章"为计数/基线/第 N 个章节，非具体章节引用）。

    这些是合法计数表述，命中的行跳过 CHAPTER 分类检查（不影响其他痕迹检查）：
      - 共/目标/总数/合计/合并后 N 章        —— 章节总数
      - N 章 总数/内容/正文/结构/基线/篇幅/布局/表格 —— N 章的结构性指代
      - 减至/降至/精简至/重排为/缩至 N 章    —— 章节数缩减
      - N→M 章 / N 至 M 章                   —— 章节数过渡
      - 「N 章」                             —— 引号内计数
      - 出现/新增/开启才出现 第 N 章          —— 序数（出现第 N 个章节）
    """
    return [
        re.compile(r"(?:共|总共|合计|目标|总数|章节数|合并后)\s*[1-9]\d?\s*章"),
        re.compile(r"[1-9]\d?\s*章\s*(?:总数|内容|正文|结构|基线|篇幅|布局|表格)"),
        re.compile(r"(?:减至|降至|精简至|重排(?:为|成)?|缩至)\s*[1-9]\d?\s*章"),
        re.compile(r"[1-9]\d?\s*章\s*总数减至\s*[1-9]\d?"),
        re.compile(r"[1-9]\d?\s*(?:→|至)\s*[1-9]\d?\s*章"),
        re.compile(r"「[1-9]\d?\s*章」"),
        re.compile(r"(?:出现|新增|开启才出现|才出现)\s*第\s*[1-9]\d?\s*章"),
        # 中文数字对应（限 1~20；裸"一章"计数如"一章三区块"不在 CHAPTER 模式内，
        # 无需豁免——模式仅含 二~十，第一章由"第X章"模式覆盖）
        re.compile(r"(?:共|总共|合计|目标|总数|章节数|合并后)\s*[一二三四五六七八九十]{1,2}\s*章"),
        re.compile(r"[一二三四五六七八九十]{1,2}\s*章\s*(?:总数|内容|正文|结构|基线|篇幅|布局|表格)"),
        re.compile(r"(?:减至|降至|精简至|重排(?:为|成)?|缩至)\s*[一二三四五六七八九十]{1,2}\s*章"),
        re.compile(r"[一二三四五六七八九十]{1,2}\s*章\s*总数减至\s*[一二三四五六七八九十]{1,2}"),
        re.compile(r"[一二三四五六七八九十]{1,2}\s*(?:→|至)\s*[一二三四五六七八九十]{1,2}\s*章"),
        re.compile(r"「[一二三四五六七八九十]{1,2}\s*章」"),
        re.compile(r"(?:出现|新增|开启才出现|才出现)\s*第\s*[一二三四五六七八九十]{1,2}\s*章"),
    ]


def _round_excludes() -> list[re.Pattern]:
    """迭代轮次计数/运行时表述豁免（"N 轮"为数量或业务/运行时概念，非迭代痕迹）。

    与 _chapter_excludes() 同理——这些是合法表述，命中的行跳过 ROUND 分类检查
    （不影响其他痕迹检查）：
      - 共/目标/计划/预计/规划 N 轮       —— 轮次总数
      - N 轮 每轮 …                       —— 每轮计数（如"21 轮每轮量化验收"）
      - 轮询                               —— 轮询是运行时技术概念（轮询超时/循环轮询）
      - 轮动/轮换/轮番/轮涨/轮跌           —— 行业轮动等投资业务术语
      - 第 N 轮 + 循环/遍历/扫描/筛选      —— 运行时处理轮次（第 N 轮循环）
    """
    return [
        re.compile(r"(?:共|总共|合计|总数|目标|设定|预计|规划)\s*[1-9]\d?\s*轮"),
        re.compile(r"计划(?:分|为|约|共)?\s*[1-9]\d?\s*轮"),
        re.compile(r"[1-9]\d?\s*轮\s*每轮"),
        re.compile(r"轮询"),
        re.compile(r"轮动|轮换|轮番|轮涨|轮跌"),
        re.compile(r"第\s*[1-9]\d?\s*轮\s*(?:循环|遍历|扫描|筛选)"),
        # 中文数字对应（限 1~20）：计数/运行时序数豁免
        re.compile(r"(?:共|总共|合计|总数|目标|设定|预计|规划)\s*[一二三四五六七八九十]{1,2}\s*轮"),
        re.compile(r"计划(?:分|为|约|共)?\s*[一二三四五六七八九十]{1,2}\s*轮"),
        re.compile(r"[一二三四五六七八九十]{1,2}\s*轮\s*每轮"),
        re.compile(r"第\s*[一二三四五六七八九十]{1,2}\s*轮\s*(?:循环|遍历|扫描|筛选)"),
    ]


# 模块级缓存（模式列表固定，避免逐行重复构建）
_DOC_PATTERNS = _doc_patterns()
_COMPILED_EXCLUDE = _exclude_lines()
_COMPILED_CHAPTER_EXCLUDE = _chapter_excludes()
_COMPILED_ROUND_EXCLUDE = _round_excludes()
# 章节编号模式子集（用于 trace-exempt 文档的仅章节扫描）
_CHAPTER_PATTERNS = [(p, c, d) for p, c, d in _DOC_PATTERNS if c == "CHAPTER"]
# 架构约束代号模式子集（独立于 trace-exempt 逻辑：除约束定义处豁免外，
# 所有文档正文（含 plan.md/changelog.md 等历史/计划记录）均不得出现 C1~C20）
_CIPHER_PATTERNS = [(p, c, d) for p, c, d in _DOC_PATTERNS if c == "CIPHER"]


def _is_excluded(line: str) -> bool:
    """检查该行是否命中豁免（合法当前状态/流程描述）。"""
    return any(p.search(line) for p in _COMPILED_EXCLUDE)


def _is_chapter_excluded(line: str) -> bool:
    """检查该行是否命中章节计数/序数豁免（"N 章"为数量而非具体章节引用）。"""
    return any(p.search(line) for p in _COMPILED_CHAPTER_EXCLUDE)


def _is_round_excluded(line: str) -> bool:
    """检查该行是否命中迭代轮次计数/运行时表述豁免（"N 轮"为数量而非迭代痕迹）。"""
    return any(p.search(line) for p in _COMPILED_ROUND_EXCLUDE)


def scan_file(fpath: Path, verbose: bool, chapter_only: bool = False) -> list[tuple[int, str, str, str]]:
    """扫描单个文档，返回 [(行号, 分类, 模式说明, 行内容), ...]

    Markdown 围栏代码块（``` 包裹）内是命令/配置示例，非文档叙述，
    不参与历史痕迹匹配（避免 `git tag v0.9.9`、`APP_VERSION` 示例误报）。

    chapter_only=True：仅应用 CHAPTER 章节编号模式（用于 changelog/plan/
    review-findings 与 docs-stm/plan/ 等 trace-exempt 文档——它们是历史/计划
    记录，版本号等历史痕迹合法，但数字章节暗号仍影响可读性需检查；迭代轮次
    "轮 N"是这些记录文档的正式载体，ROUND 不纳入 trace-exempt 扫描）。
    架构约束代号（CIPHER）独立于 chapter_only：除约束定义处（technical.md /
    llm-technical.md）豁免外，所有文档正文（含 trace-exempt 记录文档）均不得
    出现 C1~C20——约束代号属"暗号"，与历史痕迹/章节暗号不同层，处处禁。
    """
    hits: list[tuple[int, str, str, str]] = []
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return hits

    if chapter_only:
        patterns = list(_CHAPTER_PATTERNS)
        if fpath.name not in CIPHER_EXEMPT_FILES:
            patterns += _CIPHER_PATTERNS
    else:
        patterns = _DOC_PATTERNS
        if fpath.name in CIPHER_EXEMPT_FILES:
            patterns = [p for p in _DOC_PATTERNS if p[1] != "CIPHER"]
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
        if not chapter_only and _is_excluded(stripped):
            if verbose:
                print(f"    (excluded) L{lineno}: {stripped[:80]}")
            continue
        if _is_chapter_excluded(stripped):
            if verbose and chapter_only:
                print(f"    (ch-excluded) L{lineno}: {stripped[:80]}")
            if chapter_only:
                continue
        for pat, cat, desc in patterns:
            if cat == "CHAPTER" and _is_chapter_excluded(stripped):
                continue  # 计数/序数表述豁免，不影响其他模式
            if cat == "ROUND" and _is_round_excluded(stripped):
                continue  # 轮次计数/运行时表述豁免，不影响其他模式
            if re.search(pat, stripped):
                hits.append((lineno, cat, desc, stripped[:120]))
                break  # 每行仅报告首个匹配

    return hits


def _iter_docs(trace_exempt: bool = False) -> list[Path]:
    """收集受检文档。

    trace_exempt=False（默认）：常规文档——README + managements/manuals 中
    未被豁免的 .md（历史痕迹全量检查）。

    trace_exempt=True：仅章节编号检查的文档——changelog.md / plan.md /
    review-findings.md（SKIP_FILES）+ docs-stm/plan/ 目录。它们虽是历史/计划
    记录（版本号等历史痕迹豁免），但数字章节暗号影响可读性，需单独检查。
    不包含 archive/ 与 tmp/（归档/临时产物，历史痕迹与章节编号均不检查）。
    """
    docs: list[Path] = []
    if trace_exempt:
        for doc_dir in DOC_DIRS:
            if not doc_dir.exists():
                continue
            for fpath in sorted(doc_dir.rglob("*.md")):
                if fpath.name in SKIP_FILES:
                    docs.append(fpath)
        plan_dir = REPO_ROOT / "docs-stm" / "plan"
        if plan_dir.exists():
            docs.extend(sorted(plan_dir.rglob("*.md")))
        return docs
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

    def report_doc(doc: Path, hits: list[tuple[int, str, str, str]]) -> None:
        """报告单个文档的命中（非 local，作为闭包读取/修改外层统计）。"""
        nonlocal total_hits, high_count, low_count
        if not hits:
            return
        rel = doc.relative_to(REPO_ROOT)
        if not args.ci:
            print(f"\n  {rel}")

        for lineno, cat, desc, text in hits:
            total_hits += 1
            summary[cat] = summary.get(cat, 0) + 1
            is_high = cat in ("HIGH", "ARCHIVE", "CODE", "CIPHER", "CHAPTER", "ROUND")
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

    # 常规文档：历史痕迹 + 章节编号全量检查
    for doc in _iter_docs(trace_exempt=False):
        report_doc(doc, scan_file(doc, args.verbose, chapter_only=False))

    # trace-exempt 文档（changelog/plan/review-findings + plan 目录）：
    # 仅章节编号检查（版本号等历史痕迹合法，不检查）
    for doc in _iter_docs(trace_exempt=True):
        report_doc(doc, scan_file(doc, args.verbose, chapter_only=True))

    print()
    if total_hits == 0:
        print("[OK] 未发现历史变更痕迹，文档干净")
        return 0

    cat_stats = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    print(f"[!] 发现 {total_hits} 处可疑痕迹（{cat_stats}）")
    if high_count > 0:
        print(f"    {high_count} 处高置信度（HIGH/ARCHIVE/CODE/CHAPTER/ROUND），应从文档中移除")
        return 1
    print(f"[!] 仅 {low_count} 处 LOW 级别痕迹（需人工判断），建议复核")
    return 2


if __name__ == "__main__":
    sys.exit(main())
