"""LLM 内容输出模块 — 报告第 7、8、9、10 页（模块 7/8/9/A）。

由调用方预生成 LLM 内容后传入本模块写入 Excel 页签。
"""

from __future__ import annotations

import logging
import re
from math import ceil

from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from src.python.report.excel_writer import (
    freeze_header,
    write_title_row,
)
from src.python.report.styles import CONTENT_FONT
from src.python.llm_client import (
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_TIMEOUT,
    FAIL_REASON_CIRCUIT_OPEN,
    _LLM_MODULE_FAILURE,
)

logger = logging.getLogger("invest")

_CONTENT_NCOLS = 2
_COL_WIDTH = 80          # 固定列宽（字符宽度）
_CHARS_PER_LINE = 40     # 每行约 40 中文字符
_ROW_HEIGHT_MIN = 30     # 最小行高 (pt)
_ROW_HEIGHT_PER_LINE = 15  # 每行增加高度 (pt)
_CACHE_HINT_TEXT = "本次使用LLM缓存，未直接使用LLM服务能力"

# 匹配 LLM 生成的底部标识行：<p style="color:#888;font-size:12px">...</p>
_FOOTER_RE = re.compile(
    r'<p style="color:#888;font-size:12px">([^<]*)</p>'
)


def _extract_footer_text(html: str) -> str:
    """从 LLM 生成的 HTML 内容中提取底部标识行的纯文本。

    匹配最后出现的 <p style="color:#888;font-size:12px">…</p> 标签内容，
    该标签由 _generate_llm_content() 在 HTML 尾部追加，包含模型名、
    Token 用量、估算费用及 Extended Thinking 标识。

    Returns:
        标签内的纯文本，未找到时返回空字符串
    """
    if not html:
        return ""
    matches = _FOOTER_RE.findall(html)
    if matches:
        return matches[-1].strip()
    return ""


def _strip_html(text: str) -> str:
    """移除文本中的 HTML 标签，保留纯文本内容。"""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _calc_row_height(text: str) -> int:
    """根据文本长度估算行高。

    按中文字符宽度估算：列宽 _COL_WIDTH 约容纳 _CHARS_PER_LINE 个中文。
    """
    if not text:
        return _ROW_HEIGHT_MIN
    lines = ceil(len(text) / _CHARS_PER_LINE)
    return max(lines * _ROW_HEIGHT_PER_LINE, _ROW_HEIGHT_MIN)


_CONTENT_ALIGN = Alignment(
    wrap_text=True,
    vertical="top",
    horizontal="left",
)

_CACHE_HINT_FONT = Font(
    color="999999",
    size=9,
    italic=True,
)

_MODEL_NAME_FONT = Font(
    color="888888",
    size=9,
    italic=True,
)

_THINKING_FONT = Font(
    color="888888",
    size=9,
    italic=True,
)


_MODULE_KEY_MAP: dict[str, str] = {
    "7.全球政经局势": "macro",
    "8.智囊团深度复盘": "expert",
    "9.持仓体检报告": "health",
    "10.穿透深度分析": "penetration",
}

_PLACEHOLDER_BY_REASON: dict[str, str] = {
    FAIL_REASON_NOT_CONFIGURED: "本节内容待生成 — LLM 未配置（请配置 data/config/llm_key.json）",
    FAIL_REASON_API_ERROR: "本节内容待生成 — LLM API 调用失败（请检查 API Key 和网络连接后重新生成）",
    FAIL_REASON_TIMEOUT: "本节内容待生成 — LLM API 请求超时（可尝试在 llm_settings.json 中增大 timeout 配置）",
    FAIL_REASON_NETWORK_ERROR: "本节内容待生成 — LLM API 网络连接失败（请检查网络后重新生成）",
    FAIL_REASON_CIRCUIT_OPEN: "本节内容待生成 — LLM API 暂时不可用（熔断冷却中，请稍后重试）",
}


def _get_placeholder(title: str) -> str:
    """根据页签标题查找对应的失败原因占位文本。"""
    mk = _MODULE_KEY_MAP.get(title)
    if mk:
        reason = _LLM_MODULE_FAILURE.get(mk)
        if reason in _PLACEHOLDER_BY_REASON:
            return _PLACEHOLDER_BY_REASON[reason]
    return "本节内容待生成 — 请配置 LLM API Key（data/config/llm_key.json）"


def _write_content_sheet(
    ws: Worksheet,
    title: str,
    content: str | None,
    from_cache: bool = False,
    model_name: str = "",
    thinking_enabled: bool = False,
) -> None:
    """写入一个 LLM 内容页签。

    结构：
      - 第 1 行：标题（合并 A1:B1，居中标题样式）
      - 第 2 行起：每段落占一行 + 一行空行间距
      - 若 from_cache 为 True，末尾追加灰色缓存提示行
      - 若非缓存且 model_name 非空，末尾追加模型名标识行
      - 若 thinking_enabled 为 True，追加 Extended Thinking 标识行

    Args:
        ws: 目标工作表
        title: 页签标题行文本
        content: LLM 返回的 HTML 文本（已剥离标签），为 None 时写入占位符
        from_cache: 是否来自缓存（为 True 时追加缓存提示）
        model_name: 使用的 LLM 模型名称（非缓存时追加标识行）
        thinking_enabled: 是否开启 Extended Thinking（非缓存时追加标识行）
    """
    ws.title = title

    # 标题行
    row = write_title_row(ws, 1, title, _CONTENT_NCOLS)

    # 固定列宽
    ws.column_dimensions["A"].width = _COL_WIDTH

    if content:
        # 先提取底部 LLM footer（在剥离 HTML 前进行）
        footer_text = _extract_footer_text(content)

        text = _strip_html(content)
        # 按双换行分段，过滤空段
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        # 排除 footer 文本（避免在正文中重复显示底部标识行）
        if footer_text and paragraphs and paragraphs[-1] == footer_text:
            paragraphs = paragraphs[:-1]

        for para in paragraphs:
            cell = ws.cell(row=row, column=1, value=para)
            cell.font = CONTENT_FONT
            cell.alignment = _CONTENT_ALIGN
            ws.row_dimensions[row].height = _calc_row_height(para)
            row += 1
            # 段落间空行
            row += 1

        # 底部 LLM 标识行（从 HTML 中提取，与 HTML 报告格式保持一致）
        if footer_text:
            cell = ws.cell(row=row, column=1, value=footer_text)
            cell.font = _MODEL_NAME_FONT
            cell.alignment = Alignment(horizontal="left", vertical="center")
            ws.row_dimensions[row].height = 20
            row += 1
        else:
            # 无嵌入式 footer 时的后备行为（兼容旧版缓存/旧版 LLM 内容）
            if from_cache and content and _CACHE_HINT_TEXT not in content:
                cell = ws.cell(row=row, column=1, value=_CACHE_HINT_TEXT)
                cell.font = _CACHE_HINT_FONT
                cell.alignment = Alignment(horizontal="left", vertical="center")
                ws.row_dimensions[row].height = 20
            if not from_cache and model_name and content:
                cell = ws.cell(row=row, column=1, value=f"模型：{model_name}")
                cell.font = _MODEL_NAME_FONT
                cell.alignment = Alignment(horizontal="left", vertical="center")
                ws.row_dimensions[row].height = 20
                row += 1
            if thinking_enabled and content:
                cell = ws.cell(row=row, column=1, value="Extended Thinking 已开启")
                cell.font = _THINKING_FONT
                cell.alignment = Alignment(horizontal="left", vertical="center")
                ws.row_dimensions[row].height = 20
    else:
        placeholder = _get_placeholder(title)
        cell = ws.cell(row=row, column=1, value=placeholder)
        cell.font = CONTENT_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row].height = _ROW_HEIGHT_MIN
        row += 1

    # 冻结标题行
    freeze_header(ws, 1)


def write_llm_sheets(
    wb: Any,
    llm_content: tuple[str | None, str | None, str | None, str | None],
    llm_cached: tuple[bool, bool, bool, bool] = (False, False, False, False),
    model_names: tuple[str, str, str, str] = ("", "", "", ""),
    thinking: tuple[bool, bool, bool, bool] = (False, False, False, False),
) -> tuple[str, str, str, str]:
    """写入 LLM 内容页签（模块 7 & 8 & 9 & A）。

    调用方必须预先生成 llm_content，本函数仅负责写入 Excel。

    Args:
        wb: 工作簿
        llm_content: (macro_html, expert_html, health_html, penetration_html) 预生成内容
        llm_cached: (macro_cached, expert_cached, health_cached, penetration_cached) 缓存标记
        model_names: (macro_model, expert_model, health_model, penetration_model) 模型名称
        thinking: (macro_thinking, expert_thinking, health_thinking, penetration_thinking) Extended Thinking

    Returns:
        (macro_text, expert_text, health_text, penetration_text) 纯文本四元组，供 TUI 展示
    """
    ws7 = wb.create_sheet()
    ws7.title = "7.全球政经局势"
    ws8 = wb.create_sheet()
    ws8.title = "8.智囊团深度复盘"
    ws9 = wb.create_sheet()
    ws9.title = "9.持仓体检报告"
    wsA = wb.create_sheet()
    wsA.title = "10.穿透深度分析"

    content7, content8, content9, contentA = llm_content
    macro_cached, expert_cached, health_cached, penetration_cached = llm_cached
    name7, name8, name9, nameA = model_names
    think7, think8, think9, thinkA = thinking

    _write_content_sheet(ws7, "7.全球政经局势", content7, from_cache=macro_cached, model_name=name7, thinking_enabled=think7)
    _write_content_sheet(ws8, "8.智囊团深度复盘", content8, from_cache=expert_cached, model_name=name8, thinking_enabled=think8)
    _write_content_sheet(ws9, "9.持仓体检报告", content9, from_cache=health_cached, model_name=name9, thinking_enabled=think9)
    _write_content_sheet(wsA, "10.穿透深度分析", contentA, from_cache=penetration_cached, model_name=nameA, thinking_enabled=thinkA)

    logger.info("LLM 内容页签写入完成（含穿透深度分析）")

    # 返回纯文本内容，供 TUI 展示
    return (
        _strip_html(content7) if content7 else "",
        _strip_html(content8) if content8 else "",
        _strip_html(content9) if content9 else "",
        _strip_html(contentA) if contentA else "",
    )
