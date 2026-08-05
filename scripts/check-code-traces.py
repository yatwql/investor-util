#!/usr/bin/env python3
"""代码注释历史变更痕迹 + 任务编号标识符检查脚本（与 check-doc-traces.py 相对）。

扫描 src/ 与 scripts/ 下的 .py / .js / .mjs / .html / .sh / .ps1 /
.bat / .cmd 文件，检查注释和文档字符串中是否含有关代码历史迭代、
重构拆分、版本号标记、文件迁入迁出等变更痕迹，以及代码标识符
（变量/函数/类名）与注释中是否夹带任务编号/系列代号（语义命名纪律）。
各语言注释形式：Python（# 与三引号 docstring）、JS（// 与 /* */）、
HTML（<!-- --> 与 Jinja {# #} 及 CSS /* */）、Shell（#）、
PowerShell（# 与 <# #>）、Windows 批处理（REM / ::）。

在代码和测试的注释/文档串中，只应描述"当前代码是什么/做什么"，
不应记录"从哪里来、怎么变的"。此类信息应放在管理文档
（changelog.md / review-findings.md）中。标识符/注释中也不得出现
任务编号（plan-N / rf-N）或系列代号（B 系列/F 系列、b_series、F4 等）。

除历史痕迹外，注释/标识符中也不得出现三类暗号组合（无语义魔法编号 /
疑似任务编号 / 疑似无意义代码，统称"语义命名暗号"）：
  - 字母+数字（MAGIC）   ：C19 / D8 / HH6 / R11 / P1 —— 须用语义名替代
  - 字母-数字（DASHTASK）：F-1 / G-1 / TASK-22 / D-8 —— 疑似任务编号
  - 字母_数字（UNDERSCORE）：F_1 / H_1 / MINE_22 —— 疑似无意义代码
合法领域值（TOP10 前 N 名、T2/T3/T4 数据层级、T-1 交易日、A1:B1 Excel
单元格、F401 等 lint 码、VaR95/MD5、UTF-8、Sonnet-4 模型名等）由
_magic_excludes() / _dash_excludes() / _under_excludes() 行豁免。

两类扫描：
  - 注释痕迹扫描：PATTERNS 匹配注释/文档串行
  - 标识符扫描：IDENTIFIER_PATTERNS 匹配代码中的完整标识符 token
    （.py 用 ast 提取，.js/.mjs 用正则提取声明）

用法：
  python scripts/check-code-traces.py           # 检查全部
  python scripts/check-code-traces.py -v        # 详细输出
  python scripts/check-code-traces.py --ci      # CI 模式（仅输出文件名:行号，非零退出码）

退出码：
  0 — 全部通过（无可疑痕迹）
  1 — 发现高置信度痕迹（HIGH/ORIGIN/VERSION）
  2 — 发现任务编号/章节编号/架构约束代号/语义命名暗号引用
      （CODE/IDENT/CHAPTER/ROUND/MAGIC/DASHTASK/UNDERSCORE），应从注释/标识符中移除
      （CHAPTER：注释中用数字章节号"N 章"/"第 N 章"指代报告具体章节，
      章节合并/重排后数字即失效，须改用语义章节名「X」章；
      ROUND：注释中用"第 N 轮"/"经 N 轮"/"N 轮"/"轮 N"指代开发迭代
      轮次，属迭代痕迹，须改用语义描述；
      MAGIC/DASHTASK/UNDERSCORE：注释中"字母+数字/字母-数字/字母_数字"
      组合（如 R11/F-1/F_1）属无语义魔法编号/疑似任务编号/疑似无意义
      代码，须改用语义名）
  3 — 仅 LOW 级别痕迹，建议人工复核
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [
    REPO_ROOT / "src" / "python",
    REPO_ROOT / "src" / "test",
    REPO_ROOT / "src" / "static",
    REPO_ROOT / "scripts",
]
# 跳过文件名（编译产物）。本工具自身（check-*.traces.py）由 _is_tool_self()
# 模式豁免——见下方说明，不在此硬编码文件名。
SKIP_FILES = {"chart.min.js"}


def _is_tool_self(name: str) -> bool:
    """检查工具自身识别：check-*.traces.py。

    本工具（check-code-traces.py / check-doc-traces.py）的模式定义区
    （PATTERNS / EXCLUDE_LINE）与 docstring 必然包含被检测类别的特征字面量
    （版本号正则、任务编号正则、迁移/重命名描述词等）。这些是"检查规则
    的元描述"，不是被查对象的历史痕迹；用本工具规则自查本工具自身，
    与"用尺子量尺子"无异。故整文件豁免，且按模式识别而非硬编码文件名，
    使未来新增同类工具（check-xml-traces.py 等）自动豁免。
    """
    return name.startswith("check-") and name.endswith("traces.py")


# ═══════════════════════════════════════════════════════════════
#  匹配模式定义
# ═══════════════════════════════════════════════════════════════
#  每项：(pattern, category, description)
#    pattern      — 正则表达式（在注释/文档串行中匹配）
#    category     — 置信度/分类（见下文说明）
#    description  — 简短说明
#
# 置信度等级说明：
#   HIGH       — 命中即违规，必须修复
#   ORIGIN     — 来源归属叙述，绝大多数是痕迹
#   VERSION    — 版本号/发布标记，注释中不应出现
#   DEPR       — 废弃/过时标记（需判断）
#   CHANGE     — 变更描述（需人工判断）
#   TODO       — 待办标记（建议用 issue 跟踪）

PATTERNS: list[tuple[str, str, str]] = [
    #
    # ═══ HIGH：明确的历史变更痕迹 ═══
    #   命中即违规——注释中不应出现这类内容。
    #
    (
        r"从[\w._\-]+\.py\s*(?:拆分|拆出|提取|迁移|合并|分离|移[入出至到])",
        "HIGH",
        "显式来源叙述（从XX.py拆分/拆出/提取/迁移/合并）",
    ),
    (r"合并[自到][\w._\-]+\.py", "HIGH", "合并自XX.py（暗示从其他文件合并而来）"),
    (r"(?:合并|提取|抽取)\s*[`\w._\-]+\.py\s*和\s*[`\w._\-]+\.py", "HIGH", "从多文件合并/提取逻辑（来源归属叙述）"),
    (r"(?:拆分|拆出|提取|分离)[自到成为][\w._\-]+\.py", "HIGH", "来源叙述（拆分自/拆出自/分离为XX.py）"),
    (r"已迁[至到]\s*[\w._\-]+\.py", "HIGH", "已迁至XX.py（旧代码所在注释）"),
    (r"从原[\w._\-]+\.py\s*(?:合并|迁[入移])", "HIGH", "从原文件合并/迁入"),
    (r"(?<!原)\.py\s*(?:拆分|拆出|迁移)(?:至此|到此)", "HIGH", "拆分/拆出/迁移到此文件"),
    (r"(?:共同|原有).*?(?:职责|功能|逻辑).*?(?:拆分|提取|迁移|分离)(?:至此|到此)", "HIGH", "职责/功能迁移到此"),
    (r"自[\w._\-]+\.py\s*(?:拆分|拆出|提取|迁移)", "HIGH", "自XX.py拆分/拆出/提取"),
    #   以下模式覆盖 docstring 中 backtick 包裹（``module.py``）或裸写的模块路径，
    #   以及测试文件之间的覆盖/复用来源叙述（均属代码历史痕迹）。
    (r"提取自\s*[`\w./_-]+\.py", "HIGH", "提取自XX.py（来源归属叙述）"),
    (
        r"(?:自|从|由)\s*[`\w./_-]+\.py\`*\s*(?:提取|复用|拆分|拆出|迁移|合并|分离)",
        "HIGH",
        "从XX.py提取/复用/拆分/拆出/迁移（来源归属叙述）",
    ),
    (r"已由\s*[`\w./_-]+\.py\s*(?:完整)?覆盖", "HIGH", "已由XX.py覆盖（测试覆盖来源叙述）"),
    (r"\b(?:Iter|Iteration)\s*\d+\b", "HIGH", "Iter/Iteration N 迭代标记（历史迭代信息）"),
    (r"已迁移", "HIGH", "已迁移（迁移痕迹）"),
    #   时序历史叙述——"之前/此前/以前/曾经/原始/历史版本/此前/旧逻辑"等高频
    #   历史实现叙述词（注：这是"自我进化"补强，堵住常见漏检）。
    #   "之前/此前/以前/曾经/历史/先前" 泛指历史时刻；仅时间词不足以判定
    #   是否为历史痕迹（"之前缓存过"是运行时描述），故需后接动作/状态动词。
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
    (r"改(?:为|成|过来|了)|由旧[^\s。，;]{0,8}(?:改|改来|改造)", "HIGH", "由旧XX改造/改来（历史变更叙述）"),
    (
        r"(?:迁移|移到|移至|搬到|转入)\s*(?:到|至)?\s*新(?:模块|文件|目录|位置|路径|函数|类)",
        "HIGH",
        "迁移/移到新位置（迁移痕迹）",
    ),
    (r"重构\s*前", "HIGH", "重构前（重构历史叙述）"),
    (r"旧(?:逻辑|实现|方案|代码|写法|做法|设计|版本)", "HIGH", "旧逻辑/旧实现（历史实现叙述）"),
    (r"替代(?:了|掉|原有|旧的)?旧|替换旧", "HIGH", "替代旧/替换旧（历史变更叙述）"),
    (r"历史上|历次迭代", "HIGH", "历史迭代信息（历史上/历次迭代）"),
    (r"曾(?:经)?(?:用[于]?|作为|属于|采用|以)", "HIGH", "曾用/曾用于/曾作为（历史实现叙述）"),
    (r"(?:后来|之后|随后)\s*(?:改[为成]|换[为成]|引入|移除)", "HIGH", "后来改为/之后引入（变更痕迹）"),
    #   以下模式将来源叙述扩展到非 .py 文件（.js/.html 等）。
    (r"提取自\s*[`\w./_-]+\.(?:js|mjs|html|ts|vue)", "HIGH", "提取自XX.js/html（来源归属叙述）"),
    (
        r"(?:自|从|由)\s*[`\w./_-]+\.(?:js|mjs|html|ts|vue)\`*\s*(?:提取|复用|拆分|拆出|迁移|合并|分离)",
        "HIGH",
        "从XX.js/html提取/复用/拆分/拆出（来源归属叙述）",
    ),
    (r"已由\s*[`\w./_-]+\.(?:js|mjs|html|ts|vue)", "HIGH", "已由XX.js/html覆盖（来源叙述）"),
    #   以下模式覆盖函数/模块级拆分迁移叙述（无需 .py 后缀）、历史实现叙述
    #   （原逻辑/旧XX/回归缺陷/修复前后）——均属代码/测试历史痕迹。
    (r"(?:拆分|拆出)自\s*[`\w._\-()]+", "HIGH", "拆分自/拆出自XX（函数/模块拆分来源叙述）"),
    (r"迁移自\s*[`\w._\-()]+", "HIGH", "迁移自XX（迁移来源叙述）"),
    (r"合并自\s*[`\w._\-()]+", "HIGH", "合并自XX（合并来源叙述）"),
    (r"原(?:逻辑|实现|方案|代码|写法|做法|设计)", "HIGH", "原逻辑/原实现（历史实现叙述）"),
    (
        r"原\s*[`A-Za-z_][A-Za-z0-9_.]*(?:\s*(?:契约|dict|数据|结构|结果))?\s*(?:迁移|改称|并入)",
        "HIGH",
        "原X迁移/改称（历史契约/命名变更叙述）",
    ),
    (r"(?<!陈)旧\s*[`\w._\-]+\s*(?:逻辑|实现|方案|要求|做法|方式|判定|分类)", "HIGH", "旧XX逻辑/要求（历史实现叙述）"),
    (r"回归缺陷", "HIGH", "回归缺陷叙述（测试历史 bug 描述）"),
    (r"修复[后前]", "HIGH", "修复后/修复前（变更痕迹）"),
    (r"(?:已更名|已重命名|改名为|重命名为|重新命名)", "HIGH", "重命名痕迹（X 已更名/改名为 Y 是历史变更记录）"),
    (r"(?:旧设计|旧架构|历史遗留)", "HIGH", "旧设计/历史遗留（历史迭代叙述）"),
    #
    # ═══ CODE：任务/编号/约束代号引用 ═══
    #   代码注释中不应出现管理任务的编号（形如 编号前缀-数字）或系列代号。
    #   架构约束代号（C1~C20，technical.md 定义）属"暗号"——注释应直接描述当前
    #   行为（如"原子写入""会话缓存""数据契约""图下说明"），不得以代号引用架构
    #   约束表格；约束定义处（technical.md / llm-technical.md）允许使用代号，由
    #   check-doc-traces.py 豁免（代码侧无此场景）。其余裸"族字母+数字"（如
    #   P1/S-P1/A3/R17 优先级/场景/需求引用）仍为合法交叉引用，且单字母+数字
    #   与 Excel 单元格（A1/B2/F4）结构性冲突，故注释侧不捕获 C1~C20 之外的裸
    #   "族字母+数字"——F4/B6 作为**标识符**由 IDENTIFIER_PATTERNS 捕获（见下）。
    #   注释侧仅捕获无歧义的系列代号形状（_series/系列）与 C1~C20 约束代号。
    #
    (r"(?:rf|plan|R)-\d+", "CODE", "任务编号引用（如 rf-117、R-086）"),
    (r"(?<![A-Za-z])[A-Za-z]_series\b", "CODE", "任务批次系列别名英文形式（如 b_series）"),
    (r"[A-Za-z]系列", "CODE", "任务批次系列别名（如 B系列/F系列/G系列）"),
    #  架构约束代号（C1~C20）：C+1~20 两位精确匹配，避免误伤十六进制色值
    #  （C00000）、C21+ 等；前限非 ASCII 字母/数字，避免 AB14/MC19 内嵌命中。
    (r"(?<![A-Za-z0-9])C(?:[1-9]|1[0-9]|20)\b", "CODE", "架构约束代号（C1~C20，须用语义描述替代，如原子写入/会话缓存/数据契约）"),
    #
    # ═══ MAGIC：字母+数字 魔法编号 ═══
    #  注释中裸"大写字母(+小写)+数字"组合（R11/P1/I2/D8/HH6）属无语义魔法编号
    #  ——既非当前代码的结构说明，也非合法领域值，须用语义名替代（如用"单图
    #  隔离"替代 R11、"5 级评级阈值"替代 P2）。合法领域值经 _magic_excludes()
    #  行豁免（TOP10 前 N 名、F401/E402 等 lint 码、VaR95/MD5 风险与算法名、
    #  T2/T3/T4 数据层级值、A1:B1 Excel 单元格、Q3 季度、DeepSeek V4 模型名、
    #  Jinja2/ES5 技术名）。前限排除 ASCII 字母/数字（避免内嵌 AB14/MC19 命中）
    #  与井号（#C00000 十六进制色值）；后限排除字母数字，避免尾部粘连误伤。
    (r"(?<![A-Za-z0-9#])[A-Z][A-Za-z]*[0-9]{1,3}(?![A-Za-z0-9])", "MAGIC", "字母+数字魔法编号（如 R11/P1/D8/HH6，须用语义名替代）"),
    # ═══ DASHTASK：字母-数字 疑似任务编号 ═══
    #  注释中"字母-数字"组合（F-1/G-1/TASK-22/D-8/I-02）疑似任务/需求编号，
    #  属历史痕迹。合法值经 _dash_excludes() 行豁免：交易日语义（T-1/T-2）、
    #  小写前缀的数学下标/编码/模型名（i-1/idx-1/utf-8/sonnet-4/claude-3）、
    #  UTF-8/UTC-8 编码时区、N-2 计数（N 减 2 项）。
    (r"(?<![A-Za-z0-9])[A-Za-z]{1,}-[0-9]{1,3}(?![0-9])", "DASHTASK", "字母-数字组合（如 F-1/TASK-22/D-8，疑似任务编号）"),
    # ═══ UNDERSCORE：字母_数字 疑似无意义代码 ═══
    #  注释中"字母_数字"组合（F_1/H_1/MINE_22）疑似无意义代码标识。小写前缀
    #  （changed_1m/syl_1y 等语义短名）经 _under_excludes() 豁免。
    (r"(?<![A-Za-z0-9])[A-Za-z]{1,}_[0-9]{1,3}(?![0-9])", "UNDERSCORE", "字母_数字组合（如 F_1/MINE_22，疑似无意义代码标识）"),
    #
    # ═══ CHAPTER：章节编号暗号（用数字章节号指代报告具体章节） ═══
    #  "N 章" / "第 N 章"（N=1~99）指代报告具体章节时，章节合并/重排后数字
    #  即失效，须改用语义章节名（「X」章）。中文数字同理：第X章（第一章~第
    #  二十章）与裸"三章"式（三章/二章/四章…）均检出；唯"一章"在本项目均为
    #  计数表述（一章三区块/一章两区块），不纳入裸数字模式以免误伤计数语义。
    #  章节数量/序数表述（共 N 章、合并后 N 章基线、减至 N 章、N→M 章、出现
    #  第 N 章、引号内"N 章"）由 _chapter_excludes() 豁免。负向前瞻 (?!节)
    #  排除"章节"一词；[1-9]\d? 限 1~99、[一二三四五六七八九十]{1,2} 限 1~20，
    #  小节号"4.2"（数字后非"章"）不匹配。
    (r"第?\s*[1-9]\d?\s*章(?!节)", "CHAPTER", "章节编号引用（N 章/第 N 章，须用语义章节名）"),
    (r"第\s*[一二三四五六七八九十]{1,2}\s*章(?!节)", "CHAPTER", "章节编号引用（第X章，中文数字，须用语义章节名）"),
    (r"[二三四五六七八九十]{1,2}\s*章(?!节)", "CHAPTER", "章节编号引用（X章，中文数字，须用语义章节名）"),
    #
    # ═══ ROUND：迭代轮次暗号（用"第 N 轮"/"N 轮"/"轮 N"指代开发迭代轮次） ═══
    #  "第 N 轮" / "经 N 轮" / "轮 N" 是开发迭代痕迹（计划分轮实施，如
    #  "第 12 轮"、"经 8 轮"、"轮 4 落地"、"轮13 验收标准"），代码注释中不应
    #  记录迭代轮次，须改用语义描述。中文数字同理：第X轮（第三轮~第二十轮）
    #  与"轮X"（轮三）均检出；唯"第一轮/第二轮"多为运行时序数（LLM 圆桌会
    #  两轮辩论、两段式抓取的首/次轮），不纳入"第X轮"模式以免误伤正常行为。
    #  轮次数量/序数表述（共 N 轮、目标 N 轮、N 轮每轮、轮询、轮动等运行时/
    #  计数词汇）由 _round_excludes() 豁免；`[1-9]\d?` 限 1~99、
    #  [一二三四五六七八九十]{1,2} 限 1~20，中文"一轮/两轮/三轮/二十轮"为
    #  计数表述（一轮行情是业务表述，非迭代轮次），不纳入裸"X轮"模式。
    (r"第\s*[1-9]\d?\s*轮", "ROUND", "迭代轮次引用（第 N 轮，属开发迭代痕迹）"),
    (r"[1-9]\d?\s*轮", "ROUND", "迭代轮次引用（N 轮，属开发迭代痕迹）"),
    (r"轮\s*[1-9]\d?\b", "ROUND", "迭代轮次引用（轮 N，属开发迭代痕迹）"),
    (r"第\s*[三四五六七八九十]{1,2}\s*轮", "ROUND", "迭代轮次引用（第X轮，中文数字，属开发迭代痕迹）"),
    (r"轮\s*[一二三四五六七八九十]{1,2}", "ROUND", "迭代轮次引用（轮X，中文数字，属开发迭代痕迹）"),
    #
    # ═══ VERSION：版本号 / 发布 / 迭代标记 ═══
    #   代码注释中不应出现版本号、迭代信息、项目编号等变更记录。
    #
    (r"v\d+\.\d+\.\d+(?:-dev)?", "VERSION", "版本号标记（如 v0.8.9）"),
    #  无 v 前缀的裸版本号（本项目版本号为 0.x.y；限 0 开头避免误伤包版本 1.16.0 等）
    (r"\b0\.\d+\.\d+(?:-dev)?\b", "VERSION", "裸版本号标记（如 0.9.9）"),
    (r"版本\s*[:：]\s*\d+\.\d+", "VERSION", "版本号声明"),
    (r"(?:发版|发布|release)\s*(?:于|版本|v?\d)", "VERSION", "发布/发版标记"),
    (r"迭代\s*(?:\d+|任务|计划)", "VERSION", "迭代/任务标记"),
    (r"切[换至到]\s*(?:dev|master|main|分支)", "VERSION", "分支切换记录"),
    (r"未升级版|旧版|老版", "VERSION", "旧版/未升级版（版本对比痕迹）"),
    (r"(?:原先|最初|早期)(?:是|为|使用|采用|属于)", "VERSION", "原先/最初/早期（历史状态叙述）"),
    #
    # ═══ ORIGIN：来源归属（通常也是痕迹） ═══
    #
    (r"本文件(?:保留|维护)(?:测试|内容|的)", "ORIGIN", "本文件保留/维护内容（暗示拆分）"),
    (r"由[\w._\-]+\.py\s*(?:移[入至]|迁[入至])", "ORIGIN", "由XX.py迁入/移入"),
    (r"原\s*[`\w./_-]+\.(?:py|js|mjs|html|ts|vue)", "ORIGIN", "原XX.py/js（暗示代码来源）"),
    (r"原为[\w._\-]+\.py", "ORIGIN", "原为XX.py（暗示历史来源）"),
    (r"来源于[\w._\-]+\.py", "ORIGIN", "来源于XX.py（暗示代码来源）"),
    (r"出自[\w._\-]+\.py", "ORIGIN", "出自XX.py（暗示代码来源）"),
    (r"原属[\w._\-]+\.py", "ORIGIN", "原属XX.py（暗示归属变迁）"),
    (r"是[\w._\-]+\.py\s*(?:的一部分|的组成部分)", "ORIGIN", "是XX.py的一部分（暗示文件拆分关系）"),
    #
    # ═══ DEPR：废弃/过时标记 ═══
    #
    (r"已废弃|已弃用", "DEPR", "废弃标注（需判断是否为运行时行为）"),
    (r"过渡方案|过渡期|过渡性", "DEPR", "过渡性方案说明"),
    (r"暂时保留|暂保留|暂不[处理修复实现支持]", "DEPR", "暂时保留/暂不处理"),
    (r"(?:不再[推荐使用支持保留需要]|不再建议)", "DEPR", "不再推荐/使用/支持"),
    (r"兼容过渡", "DEPR", "兼容过渡（过渡性方案说明）"),
    #
    # ═══ CHANGE：变更描述（需人工判断） ═══
    #
    (r"重构[为成到]", "CHANGE", "重构为/重构到"),
    (r"新.{0,4}(?:版本|方案).{0,8}(?:替代|替换)", "CHANGE", "新版本/方案替代旧的"),
    (r"替代原有的|替换旧|替代旧", "CHANGE", "替代原有/旧的"),
    (r"曾(?:经)?被", "CHANGE", "曾被/曾经被（历史状态叙述）"),
    (r"(?<!最)新版", "CHANGE", "新版（版本变更描述，需判断）"),
    (r"物理合并", "CHANGE", "物理合并（模块/章节合并历史痕迹，须用语义描述当前结构）"),
    #
    # ═══ TODO：待办标记 ═══
    #
    (r"\b(?:TODO|FIXME|HACK|XXX|WORKAROUND)\b", "TODO", "待办/临时处理标记"),
    (r"尚未[实现处理支持完成覆盖]", "TODO", "尚未完成/实现（需加 issue 跟踪）"),
    (r"待[办做处补充修复]", "TODO", "待办/待处理"),
    (r"后续\s*(?:版本|迭代|优化|需要|再处理)", "TODO", "后续版本/迭代（需加 issue 跟踪）"),
]

# ═══ IDENT：标识符任务代号（语义命名纪律） ═══
# 匹配**完整标识符 token**——变量/函数/类名不得使用任务编号或系列代号。
# 捕获形状（全仓实证 0 误报）：
#   - 短大写字母+数字（F4、B6、HH6、AB14、TASK22）——无语义的大写常量名
#     （小写 f1/h1/t1 为短局部，合法；长 CamelCase 测试类名 TestDegradationSignal1
#     为语义变体号，合法，由 `^[A-Z]{1,4}[0-9]{1,3}$` 限定长度排除）
#   - 大写字母开头 + _数字（F_1、MINE_22）——无意义代码标识
#   - 单字母 + _series（b_series）——多字母词+series（drawdown_series）合法
#   - 单字母 + 系列（G系列）——Python 3 允许 unicode 标识符
#   - 嵌入 rf/plan + 数字（rf_205_fix、plan18_hack）——任务编号混入语义名
IDENTIFIER_PATTERNS: list[tuple[str, str, str]] = [
    (r"^[A-Z]{1,4}[0-9]{1,3}$", "IDENT", "短大写字母+数字独立标识符（如 F4、HH6、TASK22），无语义"),
    (r"^[A-Z][A-Za-z]*_[0-9]+$", "IDENT", "大写字母+_数字标识符（如 F_1、MINE_22），无意义"),
    (r"^[A-Za-z]_series$", "IDENT", "单字母+_series 标识符（如 b_series）"),
    (r"^[A-Za-z]系列$", "IDENT", "单字母+系列 标识符（如 G系列）"),
    (r"rf[_-]?\d+", "IDENT", "任务编号嵌入标识符（如 rf_205_fix）"),
    (r"plan[_-]?\d+", "IDENT", "任务编号嵌入标识符（如 plan18_hack）"),
]

# 行内排除模式：即使行命中 PATTERNS，若匹配以下任意模式则跳过
EXCLUDE_LINE: list[str] = [
    # ── 运行时行为描述（合法） ─────────
    r"模拟断电",
    r"模拟\s+\w+\s+崩溃",
    r"无临时文件残留",
    r"临时文件被清理",
    r"原文件不受影响",
    r"原文件应[保留完整存在]",
    r"原文件.*旧值",
    r"原文件完整",
    r"文件可能残留在磁盘",
    r"残留临时文件",
    r"清理.*过期.*归档目录",
    r"清理.*缓存",
    r"清除.*残留.*状态",
    r"前一阶段尚未关闭",  # perf.py
    # ── 运行时功能描述（合法） ─────────
    r"兼容性检查",
    r"兼容性名单",
    r"Thinking 兼容性",
    r"是否支持.*兼容",
    r"跨.*兼容",
    r"仍然可用",
    # ── 运行时回退/降级（合法） ──────
    r"回退[到为].*默认",
    r"回退[到为].*兜底",
    r"降级[到为].*过期缓存",
    r"降级[到为].*普通",
    r"改为降级",
    r"回退到\s*(?:\"|').*?(\"|')",  # 回退到"off"等 valid value
    # ── 运行时归档/版本行为（合法） ──────
    r"旧配置仍可",
    r"旧状态不会残留",
    r"跨日残留缓存清仓",
    r"缓存.*前序测试.*残留",
    r"尚未缓存到 registry session_cache",
    r"尚未重新熔断",
    r"尚未达到新鲜缓存",
    # ── 补强模式的误报排除（运行时语义，非历史痕迹） ──
    r"历史数据",  # 运行时历史序列（如行情历史、持仓历史）
    r"历史(?:序列|区间|值|曲线|走势|数据点|K线)",
    r"当前版本",  # 当前版本是运行时状态描述
    r"之前缓存",  # 之前缓存过是运行时缓存行为
    r"历史日期",  # 历史日期是运行时数据范围
    r"历史回撤",  # 历史回撤是运行时指标
    r"此前.*(?:已|已)",  # 此前已完成是运行时状态
    r"以前端|以前台",  # "以前端为准" 是方位描述非历史
    # ── VERSION 模式误报排除（运行时版本） ──
    r"APP_VERSION",
    r"__version__",
    r"version\s*=?\s*[\"']\d+\.\d+",  # 代码中赋值版本号变量
    r"原版本.*备份",  # 运行时备份逻辑
    r"备份旧版本",
    r"版本不兼容",
    r"版本.*不匹配",
    r"版本.*太低",
    r"版本.*落后",
    r"python.*版本",
    r"min_version",
    r"max_version",
    r"python_version",
    r"version_info",
    r"protobuf.*版本",  # compiler.proto version
    # ── TODO 模式误报排除（XXX 作为掩码占位符） ──
    r"000XXX",
    r"XXX\[",
    r"jQueryXXX",
    # ── 工具自身说明（元描述豁免） ──
    #  描述"检查/检出哪些历史痕迹、来源叙述、原旧实现、迁移/重构、系列/约束/
    #  魔法编号暗号"的规则说明行，而非代码实际残留历史痕迹（如本工具及其测试
    #  的描述性注释）。与 check-doc-traces.py 的"工具说明行豁免"保持一致——
    #  命中"检查/检出/扫描 + 痕迹/来源/旧逻辑 + 类别名词"组合才豁免，防止补强
    #  后的时序模式误伤工具自身的元描述。双向匹配（"检出…暗号"与"暗号…须检出"
    #  两种语序），并覆盖 C1~C20 等约束范围记号（技术名称表）。
    r"(?:检查|检测|判定|扫描|检出|识别|不得带|不得包含|不得出现|不应记录|禁止出现).{0,16}(?:历史痕迹|来源叙述|原旧实现|迁移重命名|变更痕迹|迭代标记|版本号标记|归档引用|任务编号|历史实现|旧逻辑|迁移痕迹|重构前|替代旧|系列代号|约束代号|架构约束|暗号|魔法编号|字母\+数字|疑似任务|无意义)",
    r"(?:历史痕迹|来源叙述|原旧实现|迁移重命名|变更痕迹|迭代标记|版本号标记|归档引用|任务编号|历史实现|旧逻辑|迁移痕迹|重构前|替代旧|系列代号|约束代号|架构约束|暗号|魔法编号|字母\+数字|疑似任务|无意义|定义载体|定义处|C[0-9]+~\s*C[0-9]+).{0,16}(?:须检出|应检出|一律检出|须改写|需改写|豁免|不误伤)",
    # ── 检查规则自身的边界描述（元描述豁免） ──
    #  本工具的测试（test_trace_check_scripts.py）须用"非约束 C+数字""不得误伤/
    #  不误伤""十六进制色值（C0 非 1~20）""超出 C1~C20 范围"等字面量描述豁免边界
    #  （验证哪些 C+数字组合不应被检出），属规则元描述而非源码残留暗号。与上方
    #  "工具说明行豁免"同理，命中即整行豁免。
    r"非约束.{0,16}(?:C\+?数字|色值)",
    r"(?:十六进制|色值).{0,16}C\d+",
    r"不误伤|不得误伤",
    r"超出\s*C\d+~\s*C\d+\s*范围",
]

# ── 测试回归场景元描述豁免（仅 src/test/ 文件生效） ──────────
# 回归测试的 docstring / 注释必须描述"旧实现/修复前做错什么、修复后如何"
# 才能表达防回退意图（如"旧实现把 3.41/4.43 修正成 1.9"、分隔注释引用
# "rf-xxx 批次修复"），这类描述是测试元数据而非源码历史痕迹残留。
# 与"工具说明行元描述豁免"同理，但仅对 src/test/ 路径生效——避免削弱
# 源码侧检出（源码注释若残留"旧实现/修复前"叙述仍会被 PATTERNS 命中）。
TEST_META_EXCLUDE: list[str] = [
    r"(?:回归断言|回归场景|回归测试|回归：|回归:)",  # 回归测试 docstring/分隔注释
    r"(?:旧实现|原实现|修复前|修复后).{0,24}(?:误|把|被|会|曾|修正|改为|按|源头|×)",
    r"rf-\d+\s*(?:批次|类)?修复",  # 引用历史任务编号的修复批次说明
]
_COMPILED_EXCLUDE = [re.compile(p) for p in EXCLUDE_LINE]
_TEST_META_COMPILED = [re.compile(p) for p in TEST_META_EXCLUDE]


def _chapter_excludes() -> list[re.Pattern]:
    """章节数量/序数表述豁免（"N 章"为计数/基线/第 N 个章节，非具体章节引用）。

    与 check-doc-traces.py 的 _chapter_excludes() 保持一致：这些是合法计数
    表述，命中的行跳过 CHAPTER 分类检查（不影响其他痕迹检查）：
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


_COMPILED_CHAPTER_EXCLUDE = [re.compile(p) for p in _chapter_excludes()]


def _is_chapter_excluded(line: str) -> bool:
    """检查该行是否命中章节计数/序数豁免（"N 章"为数量而非具体章节引用）。"""
    return any(p.search(line) for p in _COMPILED_CHAPTER_EXCLUDE)


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


_COMPILED_ROUND_EXCLUDE = [re.compile(p) for p in _round_excludes()]


def _is_round_excluded(line: str) -> bool:
    """检查该行是否命中迭代轮次计数/运行时表述豁免（"N 轮"为数量而非迭代痕迹）。"""
    return any(p.search(line) for p in _COMPILED_ROUND_EXCLUDE)


def _magic_excludes() -> list[re.Pattern]:
    """字母+数字魔法编号的合法领域值豁免（"大写字母(+小写)+数字"为运行时语义值）。

    与 _chapter_excludes() / _round_excludes() 同理——这些是合法领域/技术表述，
    命中的 token 跳过 MAGIC 分类检查（不影响其他痕迹检查）：
      - TOP\\d+            —— 前 N 名（TOP10/TOP3…），业务语义
      - MD5/SHA\\d+/AES\\d+ —— 哈希/加密算法名
      - VaR\\d+            —— 尾部风险指标（VaR95/VaR99）
      - Jinja2/ES5/ES6/V8/Win32/UTF-\\d —— 技术栈名（V8 为 JS 引擎）
      - [A-Z]{1,3}\\d{3}\\b —— linter/静态检查码（F401/E402/PERF203/F811…）
      - [Qq][1-4]\\b        —— 季度（2026-07（Q3））
      - DeepSeek V\\d       —— 模型版本（DeepSeek V4）
      - 单元格/合并/列 + 字母数字，或 A1:B1/B2~B5 范围 —— Excel 单元格引用
      - [Ss]\\d{1,2}\\b      —— 场景标记（S1~S33，conftest 官方活分类法）
      - S-P\\d+              —— 穿透场景标签（S-P1~S-P10，测试文件内组织编号）
      - [Tt][1-9]\\d?\\b     —— 场景标记（T1~T21）与统计分位（T95）等语义值（不含 T0 阈值暗号）
      - [Yy]\\d\\b / [Zz]\\d\\b —— 边缘测试组标签（Y1~Y6/Z1，文件内组织编号）
      - 微信\\s*X\\d+         —— 微信浏览器内核（X5）
      - ETF\\d+/主动\\d+/基金\\d+ —— 测试数据标签（基金简称）
    """
    return [
        re.compile(r"TOP\d+"),
        re.compile(r"\b(?:MD5|SHA\d+|AES\d*|DES\d*)\b"),
        re.compile(r"VaR\d+"),
        re.compile(r"Jinja2|ES5|ES6|V8|Win32|UTF-\d"),
        re.compile(r"[A-Z]{1,3}\d{3}\b"),
        re.compile(r"[Qq][1-4]\b"),
        re.compile(r"DeepSeek\s*V\d"),
        re.compile(r"(?:单元格|合并|列)\s*[A-Z]\s*[0-9](?:\s*[:~]\s*[A-Z]\s*[0-9])?|[A-Z][0-9]\s*[:~]\s*[A-Z][0-9]"),
        re.compile(r"\b[Ss]\d{1,2}\b"),
        re.compile(r"S\s*-\s*P\d+"),
        re.compile(r"\b[Tt][1-9]\d?\b"),
        re.compile(r"\b[Yy]\d\b"),
        re.compile(r"\b[Zz]\d\b"),
        re.compile(r"微信\s*X\d+"),
        re.compile(r"(?:ETF|主动|基金)\d+"),
    ]


def _dash_excludes() -> list[re.Pattern]:
    """字母-数字组合的合法领域值豁免（"字母-数字"为运行时时序/下标/编码/模型名）。

    命中的行跳过 DASHTASK 分类检查（不影响其他痕迹检查）：
      - [Tt]-\\d+           —— 交易日语义（T-1/T-2，QDII 净值日期滞后）
      - [a-z]+-\\d+         —— 小写前缀：数学下标/编码/模型名（i-1/idx-1/utf-8/sonnet-4）
      - UTF-\\d|UTC-\\d      —— 编码/时区（UTF-8/UTC-5）
      - 模型名-\\d          —— AI 模型名（Sonnet-4/Claude-3/GPT-4…）
      - N-\\d+(?:项|个|条)   —— 计数算术（应有 N-2 项）
      - R-\\S+-\\d+          —— 需求编号交叉引用（R-LLM-DB-QA-CONCENTRATION-03/04，
        requirements.md 表格定义的需求 ID，非任务编号；单字母 R-086 仍由 CODE 检出）
    """
    return [
        re.compile(r"[Tt]\s*-\s*\d+"),
        re.compile(r"[a-z]{1,}\s*-\s*\d+"),
        re.compile(r"UTF-\d|UTC-\d"),
        re.compile(r"(?:sonnet|claude|opus|haiku|gpt|deepseek|mistral|llama|qwen|gemini)\s*-\s*[\w.]+", re.IGNORECASE),
        re.compile(r"N\s*-\s*\d+\s*(?:项|个|条)"),
        re.compile(r"R-[A-Za-z0-9_./-]+-\d+(?:/\d+)?"),
    ]


def _under_excludes() -> list[re.Pattern]:
    """字母_数字组合的合法领域值豁免（小写前缀为语义短名）。

    命中的行跳过 UNDERSCORE 分类检查（不影响其他痕迹检查）：
      - [a-z]+_\\d+ —— 小写语义短名（changed_1m/syl_1y/cell_3/holdings_200）
    """
    return [
        re.compile(r"[a-z]{1,}\s*_\s*\d+"),
    ]


_COMPILED_MAGIC_EXCLUDE = [re.compile(p) for p in _magic_excludes()]
_COMPILED_DASH_EXCLUDE = [re.compile(p) for p in _dash_excludes()]
_COMPILED_UNDER_EXCLUDE = [re.compile(p) for p in _under_excludes()]


def _is_magic_match_excluded(line: str, start: int, end: int) -> bool:
    """判断 MAGIC 匹配 token（line[start:end]）是否被合法领域值豁免覆盖。

    逐豁免模式检查其命中区间是否与 token 区间重叠——同一行内既有合法场景
    标记（S1）又有暗号代号（R11）时，只豁免合法的 token，暗号仍会被检出。
    """
    for p in _COMPILED_MAGIC_EXCLUDE:
        for m in p.finditer(line):
            if m.start() < end and m.end() > start:
                return True
    return False


def _is_dash_excluded(line: str) -> bool:
    """检查该行是否命中字母-数字合法领域值豁免（T-1 交易日等为合法值）。"""
    return any(p.search(line) for p in _COMPILED_DASH_EXCLUDE)


def _is_under_excluded(line: str) -> bool:
    """检查该行是否命中字母_数字合法领域值豁免（小写语义短名）。"""
    return any(p.search(line) for p in _COMPILED_UNDER_EXCLUDE)


def _is_excluded(line: str, test_file: bool = False) -> bool:
    """检查该行是否匹配排除模式。

    Args:
        line: 单行注释文本。
        test_file: 该行是否来自 src/test/ 下的测试文件。为 True 时额外应用
            TEST_META_EXCLUDE（回归测试 docstring 描述旧行为属元描述，豁免）。
    """
    for pat in _COMPILED_EXCLUDE:
        if pat.search(line):
            return True
    if test_file:
        for pat in _TEST_META_COMPILED:
            if pat.search(line):
                return True
    return False


def scan_file(fpath: Path, verbose: bool) -> list[tuple[int, str, str, str]]:
    """扫描单个文件，返回 [(行号, 分类, 模式说明, 行内容/标识符), ...]"""
    hits: list[tuple[int, str, str, str]] = []
    if fpath.name in SKIP_FILES or _is_tool_self(fpath.name):
        return hits

    is_test_file = "src/test/" in fpath.as_posix()
    for lineno, ctext in _iter_comment_lines(fpath):
        if not ctext.strip():
            continue
        if _is_excluded(ctext, test_file=is_test_file):
            if verbose:
                print(f"    (excluded) L{lineno}: {ctext[:80]}")
            continue

        for pat, cat, desc in PATTERNS:
            if cat == "CHAPTER" and _is_chapter_excluded(ctext):
                continue  # 章节计数/序数表述豁免，不影响其他模式
            if cat == "ROUND" and _is_round_excluded(ctext):
                continue  # 轮次计数/运行时表述豁免，不影响其他模式
            if cat == "DASHTASK" and _is_dash_excluded(ctext):
                continue  # 字母-数字合法领域值豁免（T-1 交易日等），不影响其他模式
            if cat == "UNDERSCORE" and _is_under_excluded(ctext):
                continue  # 字母_数字合法领域值豁免（小写语义短名），不影响其他模式
            if cat == "MAGIC":
                # 逐 token 豁免：同一行内合法场景标记（S1）与暗号代号（R11）并存时，
                # 仅豁免合法的 token，暗号仍会被检出（避免整行豁免掩盖暗号）。
                for m in re.finditer(pat, ctext):
                    if not _is_magic_match_excluded(ctext, m.start(), m.end()):
                        hits.append((lineno, cat, desc, ctext[:120]))
                        break  # 该行存在未豁免的 MAGIC 命中
                else:
                    continue  # 该行全部 MAGIC 命中均被合法领域值豁免，不影响其他模式
                break  # 已命中该行，不再检查后续模式
            if re.search(pat, ctext):
                hits.append((lineno, cat, desc, ctext[:120]))
                break  # first match only per line

    # 标识符扫描（变量/函数/类名任务代号，语义命名纪律）
    hits.extend(_scan_identifiers(fpath))

    return hits


def _scan_identifiers(fpath: Path) -> list[tuple[int, str, str, str]]:
    """扫描单个文件的代码标识符，返回 [(行号, 分类, 模式说明, 标识符), ...]"""
    hits: list[tuple[int, str, str, str]] = []
    for lineno, ident in _iter_identifiers(fpath):
        for pat, cat, desc in IDENTIFIER_PATTERNS:
            if re.search(pat, ident):
                hits.append((lineno, cat, desc, ident))
                break  # first match only per identifier
    return hits


def _iter_identifiers(fpath: Path) -> Iterator[tuple[int, str]]:
    """按文件类型提取代码标识符，产出 (行号, 标识符)。

    .py 用 ast 精确提取（函数/类/参数/赋值目标/导入别名）；
    .js/.mjs 用正则提取声明（var/let/const/function/class 名）。
    其余类型（.html/.sh/.ps1/.bat/.cmd）不参与标识符扫描。
    """
    suffix = fpath.suffix.lower()
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if suffix == ".py":
        try:
            tree = ast.parse(text, filename=str(fpath))
        except SyntaxError:
            return
        yield from _py_identifier_names(tree)
    elif suffix in (".js", ".mjs"):
        yield from _js_identifier_names(text)


def _py_identifier_names(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """从 Python AST 提取全部标识符名（函数/类/参数/赋值目标/导入别名）。"""
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _a = node.args
            names.extend(x.arg for x in (*_a.posonlyargs, *_a.args, *_a.kwonlyargs))
            if _a.vararg:
                names.append(_a.vararg.arg)
            if _a.kwarg:
                names.append(_a.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Param)):
            names.append(node.id)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            names.append(node.asname or node.name.split(".")[0])
        for name in names:
            if name:
                yield node.lineno, name


_JS_DECL_RE = re.compile(r"\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)\b")


def _js_identifier_names(text: str) -> Iterator[tuple[int, str]]:
    """从 JS 文本提取声明名（const/let/var/function/class 后的标识符）。"""
    for lineno, line in enumerate(text.split("\n"), 1):
        for m in _JS_DECL_RE.finditer(line):
            yield lineno, m.group(1)


def _iter_comment_lines(fpath: Path) -> Iterator[tuple[int, str]]:
    """按文件类型提取注释/文档字符串行，产出 (行号, 注释内容)。

    支持的扩展名：.py / .js / .mjs / .html / .sh / .ps1 / .bat / .cmd。
    其余类型不参与扫描。
    """
    suffix = fpath.suffix.lower()
    if suffix not in (".py", ".js", ".mjs", ".html", ".sh", ".ps1", ".bat", ".cmd"):
        return
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if suffix == ".py":
        yield from _py_comment_lines(text)
    elif suffix in (".js", ".mjs"):
        yield from _js_comment_lines(text)
    elif suffix == ".html":
        yield from _html_comment_lines(text)
    else:
        yield from _shell_comment_lines(suffix, text)


def _shell_comment_lines(suffix: str, text: str) -> Iterator[tuple[int, str]]:
    """脚本文件注释：`.sh`（#）、`.ps1`（# 与 `<# #>`）、`.bat`/`.cmd`（REM/::）。"""
    if suffix in (".bat", ".cmd"):
        for lineno, raw in enumerate(text.split("\n"), 1):
            stripped = raw.strip().lstrip("﻿")
            if not stripped:
                continue
            if stripped[:4].upper() == "REM ":
                yield lineno, stripped[4:].lstrip()
            elif stripped.startswith("::"):
                yield lineno, stripped[2:].lstrip()
        return
    in_ps_block = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip().lstrip("﻿")
        if not stripped:
            continue
        if suffix == ".ps1" and in_ps_block:
            yield lineno, stripped
            if "#>" in stripped:
                in_ps_block = False
            continue
        if suffix == ".ps1" and stripped.startswith("<#"):
            yield lineno, stripped
            if "#>" not in stripped[2:]:
                in_ps_block = True
            continue
        if stripped.startswith("#!"):
            continue  # shebang，非注释
        if stripped.startswith("#"):
            yield lineno, stripped
            continue
        # 行内注释：提取由空白引导的 # 之后的注释文本（跳过字符串/URL 内 #）
        m = re.search(r"[ \t]#", stripped)
        if m:
            yield lineno, stripped[m.start() + 1 :]


def _py_comment_lines(text: str) -> Iterator[tuple[int, str]]:
    """Python：`#` 行注释（含行内）+ 真正的 docstring。

    用 tokenize 提取注释 token、用 AST 判定模块/类/函数 docstring 的行范围，
    避免行级三引号启发式把代码字符串（如 ``text = \"\"\"…\"\"\"``）的收尾行
    或裸 ``\"\"\"`` 关闭行误判为 docstring 开关，导致状态泄漏到后续代码行。
    """
    src_lines = text.split("\n")

    # AST 定位真正的 docstring 行范围：模块/类/函数体的首个字符串表达式语句
    doc_lines: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr):
                    val = body[0].value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        start = body[0].lineno
                        end = body[0].end_lineno or start
                        doc_lines.update(range(start, end + 1))

    # tokenize 提取注释 token（# 行注释/行内注释）与 docstring 字符串 token
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except (tokenize.TokenError, IndentationError):
        return

    yielded: set[int] = set()
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            if tok.start[0] not in yielded:
                yielded.add(tok.start[0])
                yield tok.start[0], tok.string.strip()
        elif tok.type == tokenize.STRING and tok.start[0] in doc_lines:
            start, end = tok.start[0], tok.end[0]
            for ln in range(start, end + 1):
                if ln not in yielded and ln - 1 < len(src_lines):
                    yielded.add(ln)
                    yield ln, src_lines[ln - 1].strip()


def _js_comment_lines(text: str) -> Iterator[tuple[int, str]]:
    """JS：`//` 行注释 + `/* */` 块注释（含行内注释，排除 URL `://`）。"""
    in_block = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if in_block:
            yield lineno, stripped
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("/*"):
            yield lineno, stripped
            if "*/" not in stripped[2:]:
                in_block = True
            continue
        if stripped.startswith("//"):
            yield lineno, stripped
            continue
        # 行内注释：// 或 /*（跳过 URL 的 ://）
        for m in re.finditer(r"//|/\*", stripped):
            marker = m.group(0)
            if marker == "//" and stripped[: m.start()].rstrip().endswith(":"):
                continue
            tail = stripped[m.start() :]
            if marker == "/*":
                end = tail.find("*/")
                tail = tail if end < 0 else tail[: end + 2]
                if end < 0:
                    in_block = True
            yield lineno, tail
            break


def _html_comment_lines(text: str) -> Iterator[tuple[int, str]]:
    """HTML：`<!-- -->`、Jinja `{# #}`、CSS/JS `/* */` 三种注释。"""
    in_jinja = in_html = in_css = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if in_jinja or in_html or in_css:
            yield lineno, stripped
            if in_jinja and "#}" in stripped:
                in_jinja = False
            if in_html and "-->" in stripped:
                in_html = False
            if in_css and "*/" in stripped:
                in_css = False
            continue
        starts = [("jinja", stripped.find("{#")), ("html", stripped.find("<!--")), ("css", stripped.find("/*"))]
        starts = [(k, p) for k, p in starts if p >= 0]
        if not starts:
            continue
        kind, pos = min(starts, key=lambda x: x[1])
        tail = stripped[pos:]
        end_marker = {"jinja": "#}", "html": "-->", "css": "*/"}[kind]
        end = tail.find(end_marker)
        if end >= 0:
            yield lineno, tail[: end + len(end_marker)]
        else:
            yield lineno, tail
            if kind == "jinja":
                in_jinja = True
            elif kind == "html":
                in_html = True
            else:
                in_css = True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="扫描代码注释中的历史变更痕迹",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="详细输出（含排除行信息）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式：仅输出 文件名:行号，非零退出码",
    )
    args = parser.parse_args()

    total_hits = 0
    high_count = 0
    code_count = 0
    low_count = 0
    summary: dict[str, int] = {}

    supported = {".py", ".js", ".mjs", ".html", ".sh", ".ps1", ".bat", ".cmd"}
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for fpath in sorted(scan_dir.rglob("*")):
            if not fpath.is_file() or fpath.suffix.lower() not in supported:
                continue
            rel = fpath.relative_to(REPO_ROOT)
            hits = scan_file(fpath, args.verbose)
            if not hits:
                continue

            if not args.ci:
                print(f"\n  {rel}")

            for lineno, cat, desc, text in hits:
                total_hits += 1
                summary[cat] = summary.get(cat, 0) + 1
                is_high = cat in ("HIGH", "ORIGIN", "VERSION")
                if is_high:
                    high_count += 1
                elif cat in ("CODE", "IDENT", "CHAPTER", "ROUND", "MAGIC", "DASHTASK", "UNDERSCORE"):
                    code_count += 1
                else:
                    low_count += 1

                if args.ci:
                    print(f"{rel}:{lineno} [{cat}] {desc} — {text}")
                else:
                    marker = "[ERR]" if is_high else "[!]"
                    print(f"    {marker} L{lineno:>4} [{cat}] {desc}")
                    if args.verbose:
                        print(f"           {text}")

    # ── 汇总输出 ──────────────────────────────────────────────
    print()
    if total_hits == 0:
        print("[OK] 未发现历史变更痕迹，注释干净")
        sys.exit(0)

    cat_stats = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    print(f"[!] 发现 {total_hits} 处可疑痕迹（{cat_stats}）")
    if high_count > 0:
        print(f"    {high_count} 处高置信度（HIGH/ORIGIN/VERSION），建议优先审查")
        sys.exit(1)

    if code_count > 0:
        print(f"    {code_count} 处任务编号/章节编号引用（CODE/IDENT/CHAPTER/ROUND），应从注释/标识符中移除")
        sys.exit(2)

    if low_count > 0:
        print(f"[!] 仅 {low_count} 处 LOW 级别痕迹（TODO/CHANGE/DEPR），建议人工复核")
        sys.exit(3)


if __name__ == "__main__":
    main()
