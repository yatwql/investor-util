"""providers/hithink.py 单元测试（同花顺金融数据服务）。

覆盖：凭据门禁（缺 key 不发请求）、限速器先于请求、响应信封解析（成功/业务错误码/
非 JSON/结构异常）、HTTP 各状态码分支（429 不立即重试 / 401 / 500）、thscode 映射
（A 股 / 场内 ETF / 场外基金 / 已带后缀 / 非法）、四域接口的路径与参数拼装。

说明：无 API key 时全部走 mock 响应（官方契约来自文档
``https://fuyao.aicubes.cn/llms-full.txt``）；真实连通验证待 key 配置后补做。

运行：
  pytest src/test/unit/providers/test_hithink.py -v
"""

from __future__ import annotations

import pytest

from src.python.providers import hithink as ht

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class _FakeResp:
    def __init__(self, status_code: int = 200, payload=None, json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._resp


def _prepare(monkeypatch, resp: _FakeResp, key: str = "test-key") -> _FakeClient:
    """注入假凭据 + 假 HTTP 客户端 + 无操作限速器，返回客户端以便断言请求。"""
    client = _FakeClient(resp)
    monkeypatch.setattr(ht, "missing_credential", lambda _sid: None)
    monkeypatch.setattr(ht, "credential_value", lambda _sid: key)
    monkeypatch.setattr(ht, "make_http_client", lambda **_kw: client)
    monkeypatch.setattr(ht, "_get_limiter", lambda: _NoopLimiter())
    return client


class _NoopLimiter:
    def __init__(self) -> None:
        self.acquired: list[str] = []

    def acquire(self, source_id: str) -> None:
        self.acquired.append(source_id)


class TestCredentialGate:
    def test_missing_credential_skips_without_http(self, monkeypatch):
        called = {"n": 0}

        def _boom(**_kw):
            called["n"] += 1
            raise AssertionError("缺凭据时不得发起请求")

        monkeypatch.setattr(ht, "missing_credential", lambda _sid: object())
        monkeypatch.setattr(ht, "make_http_client", _boom)
        assert ht.fetch_trading_days() is None
        assert called["n"] == 0

    def test_empty_key_skips_without_http(self, monkeypatch):
        monkeypatch.setattr(ht, "missing_credential", lambda _sid: None)
        monkeypatch.setattr(ht, "credential_value", lambda _sid: "")

        def _boom(**_kw):
            raise AssertionError("空凭据时不得发起请求")

        monkeypatch.setattr(ht, "make_http_client", _boom)
        assert ht.fetch_trading_days() is None

    def test_key_sent_in_header_and_never_in_url(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"code": 0, "data": {"item": []}}))
        ht.fetch_trading_days()
        call = client.calls[0]
        assert call["headers"]["X-api-key"] == "test-key"
        assert "test-key" not in call["url"]
        assert "test-key" not in str(call["params"])


class TestEnvelope:
    def test_success_returns_data(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload={"code": 0, "message": "success", "data": {"item": [1]}}))
        assert ht.fetch_trading_days() == {"item": [1]}

    @pytest.mark.parametrize("code", [1001, 2001, 3001, 4001, 5003])
    def test_business_error_code_returns_none(self, monkeypatch, code):
        _prepare(monkeypatch, _FakeResp(payload={"code": code, "message": "err", "data": None}))
        assert ht.fetch_trading_days() is None

    def test_data_null_returns_none(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload={"code": 0, "data": None}))
        assert ht.fetch_trading_days() is None

    def test_non_dict_body_returns_none(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload=[1, 2, 3]))
        assert ht.fetch_trading_days() is None

    def test_non_json_returns_none(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload=None, json_error=True))
        assert ht.fetch_trading_days() is None

    def test_business_error_logged_with_hint(self, monkeypatch, caplog):
        _prepare(monkeypatch, _FakeResp(payload={"code": 2001, "message": "unauthorized"}))
        with caplog.at_level("WARNING"):
            ht.fetch_trading_days()
        assert "未认证" in caplog.text


class TestHttpStatus:
    @pytest.mark.parametrize("status", [401, 403, 500, 503])
    def test_error_status_returns_none(self, monkeypatch, status):
        _prepare(monkeypatch, _FakeResp(status_code=status, payload={}))
        assert ht.fetch_trading_days() is None

    def test_rate_limited_429_not_retried(self, monkeypatch):
        """官方要求触发限流后不要立即连续重试：429 直接返回空（客户端只被调一次）。"""
        client = _prepare(monkeypatch, _FakeResp(status_code=429, payload={}))
        assert ht.fetch_trading_days() is None
        assert len(client.calls) == 1

    def test_network_error_returns_none(self, monkeypatch):
        def _boom(**_kw):
            raise OSError("unreachable")

        monkeypatch.setattr(ht, "missing_credential", lambda _sid: None)
        monkeypatch.setattr(ht, "credential_value", lambda _sid: "test-key")
        monkeypatch.setattr(ht, "make_http_client", _boom)
        assert ht.fetch_trading_days() is None


class TestLimiter:
    def test_limiter_acquired_before_request(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"code": 0, "data": {}}))
        limiter = _NoopLimiter()
        monkeypatch.setattr(ht, "_get_limiter", lambda: limiter)
        ht.fetch_trading_days()
        assert limiter.acquired == [ht.SOURCE_ID]
        assert client.calls  # 已发出请求


class TestQpsConfig:
    """限速间隔：默认取实测保守值，可由 config.json 的 hithink.qps 覆盖。"""

    def test_default_qps_is_conservative(self):
        """默认 2.0（实测 3.0 会触发 429），且不得高于该实测基线。"""
        assert ht.DEFAULT_QPS == 2.0

    def test_config_qps_overrides_default(self, monkeypatch):
        import src.python.config as cfg

        monkeypatch.setattr(cfg, "get_config", lambda: {"hithink": {"qps": 5}})
        ht.reset_hithink_limiter()
        limiter = ht._get_limiter()
        assert limiter._limits[ht.SOURCE_ID] == pytest.approx(1 / 5)
        ht.reset_hithink_limiter()

    def test_invalid_config_falls_back_to_default(self, monkeypatch):
        import src.python.config as cfg

        monkeypatch.setattr(cfg, "get_config", lambda: {"hithink": {"qps": "fast"}})
        ht.reset_hithink_limiter()
        limiter = ht._get_limiter()
        assert limiter._limits[ht.SOURCE_ID] == pytest.approx(1 / ht.DEFAULT_QPS)
        ht.reset_hithink_limiter()


class TestToThscode:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("600519", "600519.SH"),
            ("601398", "601398.SH"),
            ("688200", "688200.SH"),
            ("000001", "000001.SZ"),
            ("300750", "300750.SZ"),
            ("430047", "430047.BJ"),
            ("561910", "561910.SH"),  # 场内 ETF（沪）
            ("159222", "159222.SZ"),  # 场内 ETF（深）
            ("600519.SH", "600519.SH"),  # 已带后缀原样返回
        ],
    )
    def test_a_share_and_etf(self, code, expected):
        assert ht.to_thscode(code) == expected

    @pytest.mark.parametrize("code", ["011506", "007730", "240012", "002943"])
    def test_offsite_fund_uses_of_suffix(self, code):
        assert ht.to_thscode(code, is_fund=True) == f"{code}.OF"

    def test_fund_flag_distinguishes_code_overlap(self):
        """`00` 重叠区：同一代码既可能是深市股票也可能是场外基金，由调用方语义决定。"""
        assert ht.to_thscode("002943") == "002943.SZ"
        assert ht.to_thscode("002943", is_fund=True) == "002943.OF"

    @pytest.mark.parametrize("code", ["", "  ", "8300000", "AAPL", "MU"])
    def test_unmappable_returns_empty(self, code):
        assert ht.to_thscode(code) == ""


class TestQuoteAndKline:
    """行情快照与历史日 K（链路槽：形态对齐既有 provider）。"""

    def test_fetch_price_maps_snapshot_fields(self, monkeypatch):
        monkeypatch.setattr(
            ht,
            "fetch_price_snapshot",
            lambda codes: {
                "timestamp": 1789608712000,
                "item": [
                    {
                        "ticker": "600900",
                        "last_price": 28.44,
                        "prev_price": 28.46,
                        "open_price": 28.46,
                        "high_price": 28.56,
                        "low_price": 28.11,
                        "volume": 37527710.0,
                        "turnover": 1.06e9,
                    }
                ],
            },
        )
        out = ht.fetch_price("600900")
        assert out["price"] == 28.44
        assert out["yesterday_close"] == 28.46
        assert out["price_date"] == "2026-09-17"
        assert out["source"] == ht.DISPLAY_NAME
        assert out["code"] == "600900"

    def test_fetch_price_unsupported_code_returns_none(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(ht, "fetch_price_snapshot", lambda codes: called.__setitem__("n", 1))
        assert ht.fetch_price("AAPL") is None
        assert called["n"] == 0

    def test_fetch_price_empty_items_returns_none(self, monkeypatch):
        monkeypatch.setattr(ht, "fetch_price_snapshot", lambda codes: {"item": []})
        assert ht.fetch_price("600900") is None

    def test_fetch_kline_reads_date_ms_and_sorts(self, monkeypatch):
        """上游历史 K 线的日期字段是 `date_ms`（不是行情快照的 `timestamp`）。"""
        items = [
            {
                "date_ms": 1789056000000,
                "open_price": 27.9,
                "close_price": 28.0,
                "high_price": 28.1,
                "low_price": 27.8,
                "volume": 10,
            },
            {
                "date_ms": 1788796800000,
                "open_price": 27.8,
                "close_price": 27.9,
                "high_price": 28.0,
                "low_price": 27.7,
                "volume": 20,
            },
        ]
        monkeypatch.setattr(ht, "fetch_price_history", lambda *a, **k: {"item": items})
        bars = ht.fetch_kline("600900", days=30)
        assert [b["date"] for b in bars] == ["2026-09-08", "2026-09-11"]
        assert bars[0]["open"] == 27.8 and bars[0]["volume"] == 20

    def test_fetch_kline_incremental_filter(self, monkeypatch):
        items = [
            {"date_ms": 1788796800000, "close_price": 27.9, "volume": 1},
            {"date_ms": 1789056000000, "close_price": 28.0, "volume": 2},
        ]
        monkeypatch.setattr(ht, "fetch_price_history", lambda *a, **k: {"item": items})
        bars = ht.fetch_kline("600900", days=30, start_from="2026-09-08")
        assert [b["date"] for b in bars] == ["2026-09-11"]

    def test_fetch_kline_empty_and_unsupported(self, monkeypatch):
        monkeypatch.setattr(ht, "fetch_price_history", lambda *a, **k: {"item": []})
        assert ht.fetch_kline("600900") == []
        monkeypatch.setattr(
            ht, "fetch_price_history", lambda *a, **k: (_ for _ in ()).throw(AssertionError("非 A 股不应请求"))
        )
        assert ht.fetch_kline("AAPL") == []

    def test_kline_uses_forward_adjust(self, monkeypatch):
        captured: dict = {}

        def _hist(thscode, start, end, adjust="forward"):
            captured.update({"thscode": thscode, "adjust": adjust})
            return {"item": []}

        monkeypatch.setattr(ht, "fetch_price_history", _hist)
        ht.fetch_kline("600900", days=10)
        assert captured["thscode"] == "600900.SH"
        assert captured["adjust"] == "forward"


class TestFundHoldingsByCode:
    """基金代码 → 候选 thscode 解析 + 披露持仓取数（阶段 3 备源入口）。"""

    def test_candidates_pad_short_codes(self):
        """4/5 位代码补零（持仓 Excel 会丢前导零），实测不补零返回 code=3001。"""
        assert ht.fund_thscode_candidates("16055") == ["016055.OF"]
        assert ht.fund_thscode_candidates("2943") == ["002943.OF"]

    def test_candidates_onsite_etf_first_then_of(self):
        """5/1 开头 6 位先试场内后缀，再试 .OF（两类后缀同形，命中即止）。"""
        assert ht.fund_thscode_candidates("561910") == ["561910.SH", "561910.OF"]
        assert ht.fund_thscode_candidates("159222") == ["159222.SZ", "159222.OF"]
        assert ht.fund_thscode_candidates("011506") == ["011506.OF"]

    def test_candidates_already_suffixed_and_invalid(self):
        assert ht.fund_thscode_candidates("011506.OF") == ["011506.OF"]
        assert ht.fund_thscode_candidates("") == []
        assert ht.fund_thscode_candidates("ABC123") == []

    def test_fetch_tries_candidates_until_hit(self, monkeypatch):
        tried: list[str] = []

        def _fake(thscode):
            tried.append(thscode)
            if thscode == "016055.OF":
                return {
                    "item": [
                        {
                            "ticker": "513390",
                            "stock_name": "博时纳斯达克100ETF",
                            "asset_type": "fund",
                            "hold_ratio": 93.5,
                        }
                    ]
                }
            return None  # 0016055.OF 这类错误候选返回空

        monkeypatch.setattr(ht, "fetch_fund_portfolio_holdings", _fake)
        out = ht.fetch_fund_holdings("16055")
        assert tried == ["016055.OF"]
        assert out["_thscode"] == "016055.OF"

    def test_feeder_target_detected_from_single_fund_item(self, monkeypatch):
        """联接基金：持仓仅一只 fund 型资产 → 取该 ETF 代码作穿透目标（省去 HTML 探测）。"""
        monkeypatch.setattr(
            ht,
            "fetch_fund_portfolio_holdings",
            lambda t: {
                "item": [
                    {"ticker": "513390", "stock_name": "博时纳斯达克100ETF", "asset_type": "fund", "hold_ratio": 93.5}
                ]
            },
        )
        assert ht.fetch_fund_holdings("016055")["feeder_target_code"] == "513390"

    def test_no_feeder_target_when_stock_items_present(self, monkeypatch):
        """股票型基金不产生穿透目标（fund 型资产与股票并存时不判联接）。"""
        monkeypatch.setattr(
            ht,
            "fetch_fund_portfolio_holdings",
            lambda t: {
                "item": [
                    {"ticker": "688200", "stock_name": "华峰测控", "asset_type": "stock", "hold_ratio": 9.53},
                    {"ticker": "513390", "stock_name": "某ETF", "asset_type": "fund", "hold_ratio": 5.0},
                ]
            },
        )
        assert "feeder_target_code" not in ht.fetch_fund_holdings("011506")

    def test_returns_none_when_all_candidates_empty(self, monkeypatch):
        monkeypatch.setattr(ht, "fetch_fund_portfolio_holdings", lambda t: None)
        assert ht.fetch_fund_holdings("12325") is None


class TestEndpointParams:
    """四域接口的路径与参数拼装（字段名以官方契约为准）。"""

    def _capture(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"code": 0, "data": {"item": []}}))
        return client

    def test_income_statements_limit_mode(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_income_statements("600519.SH", period="quarterly", limit=8)
        assert client.calls[0]["params"] == {"thscode": "600519.SH", "period": "quarterly", "limit": 8}

    def test_statement_window_mode_excludes_limit(self, monkeypatch):
        """start/end 与 limit 互斥（官方约束：同时传会返回 code=1004）。"""
        client = self._capture(monkeypatch)
        ht.fetch_balance_sheets("600519.SH", limit=4, start=1_700_000_000_000, end=1_750_000_000_000)
        params = client.calls[0]["params"]
        assert params["start"] == 1_700_000_000_000 and params["end"] == 1_750_000_000_000
        assert "limit" not in params

    def test_cash_flow_path(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_cash_flow_statements("000001.SZ")
        assert client.calls[0]["url"].endswith("/api/a-share/financials/cash-flow-statements")

    def test_valuation_snapshot_joins_codes(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_valuation_snapshot(["600519.SH", "", "000001.SZ"])
        assert client.calls[0]["params"] == {"thscodes": "600519.SH,000001.SZ"}

    def test_valuation_snapshot_empty_codes_no_request(self, monkeypatch):
        client = self._capture(monkeypatch)
        assert ht.fetch_valuation_snapshot([]) is None
        assert client.calls == []

    def test_price_snapshot_batch_and_paging_modes(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_price_snapshot(["600519.SH", "000001.SZ"])
        assert client.calls[0]["params"] == {"thscodes": "600519.SH,000001.SZ"}
        ht.fetch_price_snapshot(limit=100, offset=0)
        assert client.calls[1]["params"] == {"limit": 100, "offset": 0}

    def test_price_history_defaults_forward_adjust(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_price_history("600519.SH", 1_700_000_000_000, 1_750_000_000_000)
        assert client.calls[0]["params"] == {
            "thscode": "600519.SH",
            "interval": "1d",
            "start": 1_700_000_000_000,
            "end": 1_750_000_000_000,
            "adjust": "forward",
        }

    def test_adjustment_factors_optional_window(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_adjustment_factors("600519.SH")
        assert client.calls[0]["params"] == {"thscode": "600519.SH"}
        ht.fetch_adjustment_factors("000001.SZ", "2021-01-01", "2026-01-01")
        assert client.calls[1]["params"]["from"] == "2021-01-01"

    def test_special_data_sentiment(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_limit_up_ladder()
        assert client.calls[0]["url"].endswith("/api/a-share/special-data/limit-up-ladder")
        ht.fetch_dragon_tiger_list("hot_money", "2026-07-01")
        assert client.calls[1]["params"] == {"board_type": "hot_money", "date": "2026-07-01"}

    def test_fund_endpoints(self, monkeypatch):
        client = self._capture(monkeypatch)
        ht.fetch_fund_portfolio_holdings("025480.OF")
        assert client.calls[0]["url"].endswith("/api/fund/portfolio/holdings")
        assert client.calls[0]["params"] == {"thscode": "025480.OF"}
        ht.fetch_fund_stock_history("011506.OF", "annual", "2025-12-31")
        assert client.calls[1]["url"].endswith("/api/fund/portfolio/stock-history")
        # 基金净值端点（fetch_fund_nav）已按「无消费者即死代码」删除


class TestCredentialSpec:
    def test_spec_registered_with_key_file_section(self):
        """凭据声明：环境变量优先，密钥文件以 `hithink` 为节（与 datasink 同模式）。

        声明表由 conftest 的 autouse fixture 逐测试清空，故此处重新执行模块导入
        （注册发生在模块导入期，与 datasink 同模式）后再断言。
        """
        import importlib

        from src.python.core.datasource_credential import CREDENTIAL_SPECS

        mod = importlib.reload(ht)
        spec = CREDENTIAL_SPECS[mod.SOURCE_ID]
        assert spec.env_var == "HITHINK_FINANCE_API_KEY"
        assert spec.key_file == ht.DEFAULT_KEY_FILE
        assert spec.key_section == ht.SOURCE_ID
        assert "fuyao.aicubes.cn" in spec.apply_url
