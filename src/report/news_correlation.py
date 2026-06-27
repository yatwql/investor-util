"""财经新闻热点与持仓关联分析模块 — 报告增补页签。

从新浪财经/东方财富/财联社三个源获取最新财经新闻，
与持仓名称/代码以及穿透 TOP10 资产名称进行关键词匹配，
按关联度排序输出 TOP N，在 Excel 中以单独页签呈现。

输出列：
  序号 | 新闻标题 | 摘要 | 来源 | 发布时间 | 关联关键词

可选 LLM 增强：为每条新闻做关联度判定，增加"LLM 关联分析"列。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from openpyxl.worksheet.worksheet import Worksheet

from src.models import Holding
from src.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)

logger = logging.getLogger("invest")

_NCOLS = 6
_BASE_HEADERS = [
    "序号", "新闻标题", "摘要", "来源", "发布时间", "关联关键词",
]


def build_news_data(
    holdings: List[Holding],
    top_n: int = 100,
    penetrated_assets: Optional[List[dict]] = None,
) -> tuple[list[dict[str, Any]], dict]:
    """获取新闻数据并与持仓关联。

    从多个财经新闻源获取最新新闻，
    与持仓名称/代码及穿透 TOP10 资产进行关键词匹配，
    按关联度排序返回 TOP N。

    若 llm.json 中 llm_news_analysis 为 true，自动启用 LLM 二次分析，
    对新闻逐条判定关联度并给出原因分析，结果写入 llm_analysis 字段。

    Args:
        holdings: 持仓列表
        top_n: 最多返回的关联新闻条数
        penetrated_assets: 穿透 TOP10 资产列表（可选），
            每项含 name 和 codes 字段。传入后新闻关键词
            会额外覆盖穿透到的底层资产。

    Returns:
        (news_data, meta)
        news_data: [{title, intro, url, ctime, media_name, matched_keywords, llm_analysis?}, ...]
        meta: {
            "token_usage": {...},        # LLM token 消耗（启用时）
            "llm_cached": bool,          # LLM 结果是否来自缓存
            "llm_enabled": bool,         # 是否启用了 LLM 分析
        }
        获取失败时 news_data 为 []。
    """
    from src.providers.news_aggregator import (
        aggregate_news,
        build_holding_keywords,
    )

    keywords = build_holding_keywords(holdings, penetrated_assets=penetrated_assets)
    logger.info("新闻关联关键词（含穿透）: %s", keywords)

    news_items = aggregate_news(keywords, top_n=top_n)

    # 初始化元数据
    meta: dict = {
        "token_usage": {},
        "llm_cached": False,
        "llm_enabled": False,
    }

    if news_items:
        logger.info("新闻关联完成: 获取 %d 条, 匹配 %d 条",
                    len(news_items), sum(1 for n in news_items if n.get("matched_keywords")))
    else:
        logger.warning("新闻获取失败")
        return news_items, meta

    # ── LLM 增强（可选） ──────────────────────────────────────
    from src.config import get_llm_config
    _llm_config = get_llm_config()
    if _llm_config and _llm_config.get("llm_news_analysis", False):
        meta["llm_enabled"] = True
        try:
            from src.llm_client import enhance_news_correlation
            news_items, _cached, _token_usage = enhance_news_correlation(
                news_items, holdings, penetrated_assets=penetrated_assets,
            )
            meta["llm_cached"] = _cached
            meta["token_usage"] = _token_usage
            if _cached:
                logger.info("LLM 新闻关联分析（缓存）: 富化 %d 条",
                            sum(1 for n in news_items if n.get("llm_analysis")))
        except Exception as e:
            logger.warning("LLM 新闻关联分析出错: %s", e)

    return news_items, meta


def write_news_sheet(
    ws: Worksheet,
    news_data: List[dict[str, Any]],
    llm_meta: Optional[dict] = None,
) -> None:
    """写入财经新闻热点与持仓关联分析页签。

    这是 Excel 的增补页签（仅在 N 选项时生成）。
    若有 LLM 分析数据，自动增加 "LLM 关联分析" 列。

    Args:
        ws: 目标工作表
        news_data: build_news_data() 返回的数据
        llm_meta: LLM 元数据，含 token_usage / llm_cached / llm_enabled
    """
    ws.title = "财经新闻热点"

    # 检测是否有 LLM 分析数据（按 item 中的 llm_analysis 字段）
    has_llm = any(
        isinstance(item, dict) and item.get("llm_analysis")
        for item in news_data
    )
    ncols = _NCOLS + (1 if has_llm else 0)
    headers = _BASE_HEADERS + (["LLM 关联分析"] if has_llm else [])

    row = write_title_row(ws, 1, "财经新闻热点与持仓关联分析", ncols)
    row = write_header_row(ws, row, headers)

    if not news_data:
        write_data_row(ws, row, ["暂无关联新闻"])
        logger.info("新闻关联分析：无数据")
        freeze_header(ws, 2)
        auto_width(ws)
        return

    for idx, item in enumerate(news_data, 1):
        keywords_str = ", ".join(item.get("matched_keywords", []))

        vals: list = [
            idx,
            item.get("title", ""),
            item.get("intro", ""),
            item.get("media_name", ""),
            item.get("ctime", ""),
            keywords_str,
        ]
        if has_llm:
            vals.append(item.get("llm_analysis", ""))
        write_data_row(ws, row, vals)
        row += 1

    # 底部说明
    row += 1

    if llm_meta and llm_meta.get("llm_enabled"):
        # LLM 已启用
        if llm_meta.get("llm_cached"):
            note_parts = [
                f"共获取 {len(news_data)} 条关联新闻。"
                "本次内容使用了LLM缓存，未直接使用LLM服务能力"
            ]
        else:
            note_parts = [f"共获取 {len(news_data)} 条关联新闻"]
            if has_llm:
                note_parts.append("（含 LLM 智能关联分析）")
            note_parts.append("，关键词匹配基于持仓名称和代码")
    else:
        # LLM 未启用（或配置关闭）
        note_parts = [
            f"共获取 {len(news_data)} 条关联新闻。"
            "本次内容未依赖于LLM服务，使用传统爬虫+NLP能力"
        ]

    write_data_row(ws, row, ["".join(note_parts)])

    # Token 用量行（LLM 启用且非缓存命中时）
    if llm_meta and llm_meta.get("llm_enabled") and not llm_meta.get("llm_cached"):
        token_usage = llm_meta.get("token_usage") or {}
        if token_usage.get("total_tokens", 0) > 0:
            row += 1
            token_note = (
                f"[LLM] Token 消耗: "
                f"输入 {token_usage.get('input_tokens', 0):,} + "
                f"输出 {token_usage.get('output_tokens', 0):,} = "
                f"总计 {token_usage.get('total_tokens', 0):,} tokens"
            )
            write_data_row(ws, row, [token_note])

    freeze_header(ws, 2)
    auto_width(ws)
    llm_info = f"，LLM 分析 {sum(1 for n in news_data if n.get('llm_analysis'))} 条" if has_llm else ""
    logger.info("新闻关联分析页签写入完成%s，共 %d 条", llm_info, len(news_data))
