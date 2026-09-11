"""数据源真实响应体 → 当前解析器 → 统一字段 的离线回归（语义名 datasource_cassette）。

本文件是「数据源记录-回放」的价值所在：断言的是**真实录制响应体**的解析结果
**具体值**，而非「不抛异常」。既有假响应测试只能验证「解析器符合我写的假设」，
这里能验证「解析器符合上游实际返回」——上游改字段名/加前后缀/换分隔符/多出 BOM
都会在此变红。

离线运行：响应来自 ``src/test/data/cassettes/``（git 跟踪），不发起网络请求。
录制/刷新见 ``src/test/live/test_live_cassette_record.py``。
"""

from __future__ import annotations

import pytest

from src.python.core.cassette import CASSETTE_DIR, list_cassettes, verify_cassettes
from src.python.fetcher.cassette_checks import CASSETTE_CHECKS
from src.python.providers import eastmoney, tencent
from src.python.providers import sina as sina_provider
from src.python.providers import tiantian_holdings

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


# ── 行情：腾讯 ──────────────────────────────────────────


@pytest.mark.cassette("tencent_quote")
def test_tencent_quote_real_response_parses_to_unified_fields():
    """腾讯行情：波浪号分隔的定长字段流，市值/市盈率取自固定下标。"""
    data = tencent.fetch_price("600519")

    assert data is not None
    assert data["name"] == "贵州茅台"
    assert data["code"] == "600519"
    assert data["price"] == pytest.approx(1285.13)
    assert data["yesterday_close"] == pytest.approx(1290.88)
    assert data["price_date"] == "2026-09-10"
    # 下表位置字段（市值/市盈率）最易因上游插列而错位，逐个锁死
    assert data["market_cap"] == pytest.approx(16065.17)
    assert data["pe"] == pytest.approx(19.73)
    assert data["source"] == "腾讯财经"


# ── 行情：新浪 ──────────────────────────────────────────


@pytest.mark.cassette("sina_quote")
def test_sina_quote_real_response_parses_to_unified_fields():
    """新浪行情：GB18030 逗号分隔字段，且**不含**市值/市盈率（本源不提供）。"""
    data = sina_provider.fetch_price("600519")

    assert data is not None
    assert data["name"] == "贵州茅台"
    assert data["code"] == "600519"
    assert data["price"] == pytest.approx(1285.13)
    assert data["yesterday_close"] == pytest.approx(1290.88)
    assert data["price_date"] == "2026-09-10"
    assert data["source"] == "新浪财经"
    # 本源不提供这两个字段：多出来即说明解析器把别人的字段位置安到了这里
    assert "market_cap" not in data
    assert "pe" not in data


# ── 行情：K 线 ──────────────────────────────────────────


@pytest.mark.cassette("tencent_kline")
def test_tencent_kline_real_response_parses_to_ordered_bars():
    """腾讯日 K 线：JSON 数组按 [日期, 开, 收, 高, 低, 量] 定序解析。"""
    bars = tencent.fetch_kline("600519", days=5)

    assert len(bars) == 6, "录制内容固定，条数应稳定（含当日）"
    assert [bar["date"] for bar in bars] == [
        "2026-09-03",
        "2026-09-04",
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
    ]
    first, last = bars[0], bars[-1]
    assert (first["open"], first["close"], first["high"], first["low"]) == (1297.5, 1298.88, 1305.0, 1293.02)
    assert (last["open"], last["close"], last["high"], last["low"]) == (1291.0, 1285.13, 1294.99, 1282.0)


# ── 场外基金净值 ────────────────────────────────────────


@pytest.mark.cassette("fund_nav")
def test_fund_nav_real_response_parses_jsonp_payload():
    """东方财富净值：JSONP 包裹的 ``LSJZList``，取前两条算昨日净值。"""
    data = eastmoney.fetch_nav("110022")

    assert data is not None
    assert data["code"] == "110022"
    assert data["nav"] == pytest.approx(2.89)
    assert data["acc_nav"] == pytest.approx(2.89)
    assert data["nav_date"] == "2026-09-09"
    assert data["yesterday_nav"] == pytest.approx(2.908)
    assert data["source"] == "东方财富"


# ── 基金持仓 ────────────────────────────────────────────


@pytest.mark.cassette("fund_holdings")
def test_fund_holdings_real_response_resolves_feeder_target():
    """天天基金联接基金：季报股票表按构造为空 → 落到主页面并由锚点解析出目标 ETF。

    录制标的为 ETF 联接基金（普通基金的年份域季报直接命中、不请求主页面，录下来
    与 ``fund_quarterly_holdings`` 重复）。本用例盯的是本基金**独有**的那条路径：
    联接基金自身无股票持仓，底层暴露只能取自目标 ETF，故需带回 ``feeder_target_code``
    交给 fetcher 层发起第二跳。

    录制内容亦真实反映了阶梯的**次序**：先按最近 4 个完整季度 × jjcc/zqcc 逐档
    尝试（8 次请求，均无持仓），再退到主页面由锚点定位——若把无年份兜底提回与
    年份域并列，此处会取到陈年分区而非目标 ETF。
    """
    data = tiantian_holdings.fetch_fund_holdings("016055")

    assert data is not None
    assert data["code"] == "016055"
    assert data["name"] == "博时纳斯达克100ETF发起式联接"
    assert data["holdings"] == [], "联接基金自身不持有股票，其股票表按构造为空"
    assert data["date"] == "", "报告期只从季报接口取；主页面不得产出报告期"
    assert data["feeder_target_code"] == "513390", "目标 ETF 由页面锚点动态解析，不由映射表维护"


@pytest.mark.cassette("fund_quarterly_holdings")
def test_fund_quarterly_holdings_real_response_parses_report_period():
    """天天基金季报持仓：带报告期字段，且持仓条数多于网页前十大。"""
    data = tiantian_holdings.fetch_quarterly_holdings("110022")

    assert data is not None
    assert data["code"] == "110022"
    assert data["name"] == "易方达消费行业股票"
    assert data["date"] == "2026-06-30"
    holdings = data["holdings"]
    assert len(holdings) > 10, "季报披露全部持仓，应多于网页版前十大"
    assert holdings[0] == {"name": "贵州茅台", "code": "600519", "ratio": pytest.approx(9.77)}


# ── 套件自洽：每一份录制都登记了解析器且当前可解析 ────────


def test_every_recorded_cassette_is_parseable_by_current_parser():
    """库里每份 cassette 都能被当前解析器吃下——新增录制未登记解析器会在此变红。

    本断言等价于 CLI ``cassettes --verify`` 的离线判定，随默认套件运行，
    使「上游格式漂移 / 解析器回归」在门禁内失败。
    """
    entries = list_cassettes()
    assert entries, f"未找到任何 cassette：{CASSETTE_DIR}（录制入口见 src/test/live/）"

    verdicts = verify_cassettes(CASSETTE_CHECKS)
    assert [v["name"] for v in verdicts] == [e["name"] for e in entries], "校验结果须与目录内 cassette 一一对应"

    problems = [f"{v['name']}: [{v['status']}] {v['detail']}" for v in verdicts if v["status"] != "ok"]
    assert not problems, "以下 cassette 未能通过当前解析器：\n  " + "\n  ".join(problems)
