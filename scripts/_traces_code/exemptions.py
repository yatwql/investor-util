"""历史痕迹检查脚本（check-code-traces.py / check-doc-traces.py）的共享排除模式。

两个脚本都做「历史痕迹」检测，但作用面不同（代码注释/docstring vs 面向读者文档）；
其中**章节计数豁免**与**迭代轮次豁免**两套模式完全一致（逐字节相同，早期各自维护一份，
存在"改一处忘另一处"的漂移面），故抽到本模块共用。

导出：
  - `_chapter_excludes()` / `_COMPILED_CHAPTER_EXCLUDE` / `_is_chapter_excluded(line)`
      「N 章」的合法计数/序数表述（共 18 章、减至 16 章、出现第 3 章…）
  - `_round_excludes()` / `_COMPILED_ROUND_EXCLUDE` / `_is_round_excluded(line)`
      「N 轮」的合法计数/运行时表述（共 21 轮、轮询、行业轮动…）
"""

from __future__ import annotations

import re


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
        # 无需豁免——本组模式只覆盖 二~十）
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

    与 `_chapter_excludes()` 同理——这些是合法表述，命中的行跳过 ROUND 分类检查
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
_COMPILED_CHAPTER_EXCLUDE: list[re.Pattern] = _chapter_excludes()
_COMPILED_ROUND_EXCLUDE: list[re.Pattern] = _round_excludes()


def _is_chapter_excluded(line: str) -> bool:
    """检查该行是否命中章节计数/序数豁免（"N 章"为数量而非具体章节引用）。"""
    return any(p.search(line) for p in _COMPILED_CHAPTER_EXCLUDE)


def _is_round_excluded(line: str) -> bool:
    """检查该行是否命中迭代轮次计数/运行时表述豁免（"N 轮"为数量而非迭代痕迹）。"""
    return any(p.search(line) for p in _COMPILED_ROUND_EXCLUDE)
