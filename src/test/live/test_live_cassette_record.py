"""数据源真实响应体录制入口（opt-in live 套件，默认跳过、不入门禁）。

录制需**双开关**：``--run-live``（放行真实网络）+ ``--record-cassettes``
（开启写入）。缺任一，本文件用例一律 skip——录制是显式的维护动作，不允许
日常运行或 CI 意外改写仓库内的 cassette 夹具。

运行：
    .venv/bin/python scripts/test-runner.py --mode live --record-cassettes

用例的请求由 ``fetcher.cassette_checks`` 的登记表给出（录制与回放校验共用同一
调用，避免「录的是一支标的、验的是另一支」）。录制后的离线回放回归在
``src/test/unit/providers/test_cassette_replay.py``，随默认套件运行、入门禁。
"""

from __future__ import annotations

import pytest

from src.python.core.cassette import cassette_path, verify_cassettes
from src.python.fetcher.cassette_checks import parser_for

pytestmark = [pytest.mark.live]


def _record_and_selfcheck(cassette_recording, name: str) -> None:
    """录制 → 落盘 → 立即以当前解析器离线回放自检「刚录的内容可解析」。"""
    parser = parser_for(name)
    assert parser is not None, f"{name}: 未在 fetcher.cassette_checks 登记解析器"

    result = parser()
    assert result not in (None, [], {}, ""), f"{name}: 真实响应解析为空，未录入有效内容"

    recorded = cassette_recording.flush()
    assert recorded, f"{name}: 本次会话未录到任何请求"
    assert cassette_path(name).endswith(f"{name}.json")

    verdicts = verify_cassettes({name: parser}, names=[name])
    assert [v["name"] for v in verdicts] == [name], f"{name}: cassette 文件不可读 — {verdicts}"
    assert verdicts[0]["status"] == "ok", f"{name}: 录制内容回放校验未通过 — {verdicts[0]['detail']}"


@pytest.mark.cassette("tencent_quote", source="tencent")
def test_record_tencent_quote(cassette_recording):
    """腾讯财经行情：GBK 文本 + gzip 传输 + 无查询参数的路径。"""
    _record_and_selfcheck(cassette_recording, "tencent_quote")


@pytest.mark.cassette("sina_quote", source="sina")
def test_record_sina_quote(cassette_recording):
    """新浪财经行情：GB18030 文本 + 「路径即参数」（``list=`` 写在 path 里）的路径。"""
    _record_and_selfcheck(cassette_recording, "sina_quote")


@pytest.mark.cassette("tencent_kline", source="tencent")
def test_record_tencent_kline(cassette_recording):
    """腾讯财经日 K 线：JSON 响应 + 逗号分隔查询参数（键归一需正确转义）。"""
    _record_and_selfcheck(cassette_recording, "tencent_kline")


@pytest.mark.cassette("fund_nav", source="eastmoney")
def test_record_fund_nav(cassette_recording):
    """东方财富场外基金净值：JSONP（``callback`` 为易变参数，归一后剥离）。"""
    _record_and_selfcheck(cassette_recording, "fund_nav")


@pytest.mark.cassette("fund_holdings", source="tiantian")
def test_record_fund_holdings(cassette_recording):
    """天天基金持仓：整页 HTML 表格解析路径（格式漂移最敏感的一类）。"""
    _record_and_selfcheck(cassette_recording, "fund_holdings")


@pytest.mark.cassette("fund_quarterly_holdings", source="tiantian")
def test_record_fund_quarterly_holdings(cassette_recording):
    """天天基金季报持仓：带 ``year``/``month`` 查询参数的 HTML 片段解析。"""
    _record_and_selfcheck(cassette_recording, "fund_quarterly_holdings")
