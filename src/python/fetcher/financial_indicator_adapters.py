"""财务指标域适配器 —— akshare 结构化指标（主源）+ DataSinking 全文解析（备用支路）。

两个适配器各自把上游响应归一为标准字段：

- :class:`AkshareFinancialAdapter`：抓取委托 ``providers/akshare_financial.py``，
  该 provider 已直接输出标准字段名（无需 alias 改名）；
- :class:`DataSinkIndicatorAdapter`：**解析适配器** —— 先经
  ``fetcher/financial_report.py`` 取回「公司简介和主要财务指标」章节正文
  （复用财报链的缓存/限速/配额/熔断，不另建 HTTP 通道），再交给纯解析层
  ``analysis/financial_indicator_extract.py`` 提取指标。

两者输出同键同构，故链路 ``financial_indicator`` 可让主源失败时直接落备用支路，
下游无需分辨记录来自哪个源。
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from src.python.analysis.financial_indicator_extract import extract_indicators
from src.python.analysis.financial_statement_derive import derive_indicator_records
from src.python.core.code_utils import to_fmp_symbol
from src.python.fetcher import financial_report
from src.python.fetcher.source_adapter import SourceAdapter, register_adapter
from src.python.providers import akshare_financial, hithink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_INDICATOR

logger = logging.getLogger("invest")

#: DataSinking 侧承载标准指标的章节（按优先级逐个试取，命中即止——避免同章节
#: 被多个别名重复取回，浪费配额）。
#: 注：实测年报/半年报为「公司简介和主要财务指标」，季报为「主要财务数据」。
_INDICATOR_SECTIONS: tuple[str, ...] = ("公司简介和主要财务指标", "主要财务数据")

#: 解析只取正文，摘要截断长度取最小（避免无谓的长文本处理）
_PARSE_SUMMARY_CHARS = 1000


class AkshareFinancialAdapter(SourceAdapter):
    """akshare 财务指标适配器（单只股票的最新报告期记录）。"""

    domain: ClassVar[str] = DOMAIN_FINANCIAL_INDICATOR
    source_id: ClassVar[str] = akshare_financial.SOURCE_ID
    display_name: ClassVar[str] = akshare_financial.DISPLAY_NAME

    def extract_data(self, query: dict[str, Any]) -> Any:
        """按 ``code`` 取最新报告期标准指标记录。"""
        return akshare_financial.fetch_financial_indicators(query.get("code"))


class DataSinkIndicatorAdapter(SourceAdapter):
    """DataSinking 全文解析指标适配器（备用支路，单只股票的最新报告期记录）。"""

    domain: ClassVar[str] = DOMAIN_FINANCIAL_INDICATOR
    source_id: ClassVar[str] = "datasink_indicator"
    display_name: ClassVar[str] = "DataSinking 指标解析"

    def extract_data(self, query: dict[str, Any]) -> Any:
        """取财报章节正文并解析为标准指标记录（无可解析内容返回 None）。

        逐章节试取，命中即解析；解析不出任何字段则继续试下一章节，最终返回 None
        由链路降级——不抛异常、不计熔断。
        """
        code = str(query.get("code") or "").strip()
        symbol = str(query.get("symbol") or "").strip() or to_fmp_symbol(code)
        if not symbol:
            logger.debug("[datasink_indicator] 非 A 股代码，跳过: %s", code)
            return None
        for section in _INDICATOR_SECTIONS:
            report = financial_report.fetch_symbol_report(
                symbol,
                sections=(section,),
                max_chars=_PARSE_SUMMARY_CHARS,
            )
            if not report:
                continue
            record = extract_indicators(
                report.get("content"),
                code=code,
                symbol=symbol,
                report_period=str(report.get("report_period") or ""),
                doc_type=str(report.get("doc_type") or ""),
            )
            if record:
                return record
        return None


class HithinkIndicatorAdapter(SourceAdapter):
    """同花顺官方合并报表派生指标（第三链路；需凭据）。

    抓取三张合并报表（利润表 / 资产负债表 / 现金流量表，各一次请求即得**多期**），
    由 :func:`analysis.financial_statement_derive.derive_indicator_records` 纯派生为标准
    字段记录。口径与主源对齐（比率小数、金额元），差异仅在 ROE（期末口径 vs 加权）
    与 `bvps`（官方不给总股本 → 恒缺失）；同源序列内可比。
    """

    domain: ClassVar[str] = DOMAIN_FINANCIAL_INDICATOR
    source_id: ClassVar[str] = hithink.SOURCE_ID
    display_name: ClassVar[str] = hithink.DISPLAY_NAME

    def extract_data(self, query: dict[str, Any]) -> Any:
        """按 ``code``/``symbol`` 取**最新报告期**标准指标记录（链条单期契约）。"""
        code = str(query.get("code") or "").strip()
        symbol = str(query.get("symbol") or "").strip() or hithink.to_thscode(code)
        if not symbol:
            logger.debug("[hithink] 非 A 股代码，跳过: %s", code)
            return None
        records = derive_indicator_records(
            hithink.fetch_income_statements(symbol, period="quarterly", limit=2),
            hithink.fetch_balance_sheets(symbol, period="quarterly", limit=2),
            hithink.fetch_cash_flow_statements(symbol, period="quarterly", limit=2),
            code=code,
            symbol=symbol,
            limit=1,
        )
        return records[0] if records else None


register_adapter(AkshareFinancialAdapter())
register_adapter(DataSinkIndicatorAdapter())
register_adapter(HithinkIndicatorAdapter())
