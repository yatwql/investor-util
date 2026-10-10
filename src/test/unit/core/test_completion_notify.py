"""任务完成通知（completion_notify）单元测试。

覆盖：
- 事件载荷构造：产物路径按结果标志 + 命名单源推导、ok/退出码映射、
  错误计数全量 vs 明细截断、时间戳注入
- 门控：缺节/无通道静默跳过、失败必发、成功需 on_success 显式开启
- 分发：按已配置通道分发、单通道失败隔离（永不抛出）、全失败返回 False
- 凭据纪律：webhook URL 异常消息落日志前掩码，完整 URL 不入日志
- 通道发送器：webhook 经统一 HTTP 客户端工厂、邮件 SSL/STARTTLS、
  桌面 notify-send 缺失时报错可隔离
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.python.core.completion_notify import (
    _mask_url,
    build_completion_event,
    dispatch_completion_notification,
    should_notify,
)
from src.python.core.constants import LATEST_HTML_NAME, LATEST_XLSX_NAME

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _webhook_cfg(**extra) -> dict:
    cfg = {"webhook_url": "https://hooks.example.test/abc", "desktop": False, "email": {}}
    cfg.update(extra)
    return cfg


def _event(**overrides) -> dict:
    base = build_completion_event(
        report_type="both",
        exit_code=1,
        output_dir="reports",
        errors=["品种行情获取失败"],
        excel_ok=True,
        html_ok=True,
        degradations=["tencent: timeout（累计2次）"],
        now=datetime(2026, 10, 10, 12, 0, 0),
    )
    base.update(overrides)
    return base


# ── 事件载荷构造 ────────────────────────────────────────────


class TestBuildCompletionEvent:
    """build_completion_event：命名单源产物路径 + 计数/截断契约。"""

    def test_artifacts_follow_result_flags(self):
        """产物路径仅列示成功的格式，文件名取 core.constants 最新版名单源。"""
        both = build_completion_event(
            report_type="full", exit_code=0, output_dir="out", errors=[], excel_ok=True, html_ok=True
        )
        assert both["artifacts"] == [
            os.path.abspath(os.path.join("out", LATEST_XLSX_NAME)),
            os.path.abspath(os.path.join("out", LATEST_HTML_NAME)),
        ]
        excel_only = build_completion_event(
            report_type="basic", exit_code=0, output_dir="out", errors=[], excel_ok=True
        )
        assert excel_only["artifacts"] == [os.path.abspath(os.path.join("out", LATEST_XLSX_NAME))]
        none = build_completion_event(report_type="full", exit_code=2, output_dir="out", errors=["x"])
        assert none["artifacts"] == []

    def test_ok_flag_maps_exit_code(self):
        """exit_code == 0 → ok=True；非 0 → ok=False（载荷布尔与退出码一致）。"""
        ok_event = build_completion_event(report_type="both", exit_code=0, output_dir="o", errors=[])
        assert ok_event["ok"] is True
        fail_event = build_completion_event(report_type="both", exit_code=1, output_dir="o", errors=[])
        assert fail_event["ok"] is False
        assert fail_event["exit_code"] == 1

    def test_error_count_full_while_details_truncated(self):
        """error_count 为全量计数，errors 明细按上限截断（不写死上限数字）。"""
        from src.python.core import completion_notify

        big = [f"错误{i}" for i in range(completion_notify._MAX_ERROR_ITEMS + 5)]
        event = build_completion_event(report_type="full", exit_code=1, output_dir="o", errors=big)
        assert event["error_count"] == len(big)
        assert len(event["errors"]) == completion_notify._MAX_ERROR_ITEMS
        assert event["errors"][0] == "错误0"

    def test_event_is_json_serializable(self):
        """载荷可直接 json.dumps（webhook 通道原样 POST）。"""
        payload = _event()
        assert json.loads(json.dumps(payload))["event"] == "report.completed"

    def test_generated_at_injected_clock(self):
        """now 注入 → 时间戳可复现（测试确定性）。"""
        event = build_completion_event(
            report_type="both",
            exit_code=0,
            output_dir="o",
            errors=[],
            now=datetime(2026, 10, 10, 8, 30, 0),
        )
        assert event["generated_at"].startswith("2026-10-10T08:30:00")


# ── 门控 ───────────────────────────────────────────────────


class TestShouldNotify:
    """should_notify：缺省静默 / 失败必发 / 成功需显式开启。"""

    def test_missing_or_empty_cfg_silent(self):
        """无 notify 节 / 空配置 → 恒 False（默认关，静默跳过）。"""
        assert should_notify(None, ok=False) is False
        assert should_notify({}, ok=False) is False
        assert should_notify({"webhook_url": "", "desktop": False, "email": {}}, ok=False) is False

    def test_failure_notifies_with_any_channel(self):
        """失败（ok=False）时任一通道已配置 → 发。"""
        assert should_notify(_webhook_cfg(), ok=False) is True

    def test_success_requires_on_success(self):
        """成功（ok=True）默认不发；on_success=True 才发。"""
        assert should_notify(_webhook_cfg(), ok=True) is False
        assert should_notify(_webhook_cfg(on_success=True), ok=True) is True

    def test_email_requires_host_and_recipients(self):
        """邮件通道需 smtp_host 与 to 同时配置才算已配置。"""
        only_host = {"email": {"smtp_host": "smtp.example", "to": ""}}
        only_to = {"email": {"smtp_host": "", "to": "a@b.c"}}
        both = {"email": {"smtp_host": "smtp.example", "to": "a@b.c"}}
        assert should_notify(only_host, ok=False) is False
        assert should_notify(only_to, ok=False) is False
        assert should_notify(both, ok=False) is True


# ── 分发 ───────────────────────────────────────────────────


class TestDispatch:
    """dispatch_completion_notification：分发、失败隔离、日志凭据纪律。"""

    def test_dispatches_to_each_configured_channel(self):
        """webhook/email/desktop 三通道均配置 → 各调用一次（webhook 收 JSON 载荷）。"""
        cfg = _webhook_cfg(
            desktop=True,
            email={"smtp_host": "smtp.example.test", "to": "a@example.test"},
        )
        with (
            patch("src.python.core.completion_notify._send_webhook") as mock_hook,
            patch("src.python.core.completion_notify._send_email") as mock_mail,
            patch("src.python.core.completion_notify._send_desktop") as mock_desktop,
        ):
            sent = dispatch_completion_notification(_event(), cfg)
        assert sent is True
        mock_hook.assert_called_once()
        mock_mail.assert_called_once()
        mock_desktop.assert_called_once()
        assert mock_hook.call_args[0][1]["event"] == "report.completed"

    def test_single_channel_failure_isolated(self):
        """webhook 抛错不影响其余通道，整体仍返回 True 且不抛出。"""
        cfg = _webhook_cfg(desktop=True)
        with (
            patch("src.python.core.completion_notify._send_webhook", side_effect=RuntimeError("boom")),
            patch("src.python.core.completion_notify._send_desktop") as mock_desktop,
        ):
            sent = dispatch_completion_notification(_event(), cfg)
        assert sent is True
        mock_desktop.assert_called_once()

    def test_all_channels_fail_returns_false_without_raise(self):
        """全部通道失败 → 返回 False，不向上抛（尽力而为契约）。"""
        cfg = _webhook_cfg(desktop=True)
        with (
            patch("src.python.core.completion_notify._send_webhook", side_effect=RuntimeError("boom")),
            patch("src.python.core.completion_notify._send_desktop", side_effect=RuntimeError("no display")),
        ):
            assert dispatch_completion_notification(_event(), cfg) is False

    def test_gating_applies_at_dispatch(self):
        """分发层同样执行门控：成功且未开 on_success → 不触达任何发送器。"""
        ok_event = _event(ok=True, exit_code=0)
        with (
            patch("src.python.core.completion_notify._send_webhook") as mock_hook,
            patch("src.python.core.completion_notify._send_desktop") as mock_desktop,
        ):
            sent = dispatch_completion_notification(ok_event, _webhook_cfg(desktop=True))
        assert sent is False
        mock_hook.assert_not_called()
        mock_desktop.assert_not_called()

    def test_webhook_url_masked_in_warning_log(self, caplog):
        """凭据纪律：异常消息内嵌完整 webhook URL 时，日志只留域名、路径凭据不落日志。"""
        url = "https://hooks.example.test/bot123456:AAsecret-token"
        secret_msg = f"HTTPError for {url} status=500"
        with caplog.at_level("WARNING", logger="invest"):
            with patch("src.python.core.completion_notify._send_webhook", side_effect=RuntimeError(secret_msg)):
                dispatch_completion_notification(_event(), {"webhook_url": url})
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "bot123456:AAsecret-token" not in joined
        assert "hooks.example.test" in joined

    def test_mask_url_keeps_scheme_and_host_only(self):
        """掩码工具只保留协议与域名，路径与查询串一律替换。"""
        masked = _mask_url("https://host.example/path/token?x=1")
        assert masked == "https://host.example/***"
        assert "token" not in masked


# ── 通道发送器 ──────────────────────────────────────────────


class TestChannelSenders:
    """发送器：统一客户端、邮件双模式、桌面通知可用性。"""

    def test_webhook_uses_unified_http_client(self):
        """webhook 经 make_http_client 工厂（HTTP 客户端统一），POST JSON + raise_for_status。"""
        client = MagicMock()
        client.__enter__.return_value = client
        with patch("src.python.core.completion_notify.make_http_client", return_value=client) as mock_factory:
            from src.python.core.completion_notify import _send_webhook

            _send_webhook("https://hooks.example.test/x", {"a": 1}, 7.5)
        mock_factory.assert_called_once_with(timeout=7.5)
        client.post.assert_called_once_with("https://hooks.example.test/x", json={"a": 1})
        client.post.return_value.raise_for_status.assert_called_once()

    def test_email_ssl_login_and_send(self):
        """SSL 模式：SMTP_SSL 连接、凭据登录、按收件人列表发信。"""
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        with patch("src.python.core.completion_notify.smtplib.SMTP_SSL", return_value=smtp) as mock_ssl:
            from src.python.core.completion_notify import _send_email

            _send_email(
                {
                    "smtp_host": "smtp.example.test",
                    "smtp_port": 465,
                    "username": "u",
                    "password": "p",
                    "to": "a@x.y; b@x.y",
                },
                "标题",
                "正文",
                10.0,
            )
        mock_ssl.assert_called_once_with("smtp.example.test", 465, timeout=10.0)
        smtp.login.assert_called_once_with("u", "p")
        args = smtp.sendmail.call_args[0]
        assert args[1] == ["a@x.y", "b@x.y"]

    def test_email_starttls_when_ssl_disabled(self):
        """use_ssl=False → 普通 SMTP + starttls，不走 SMTP_SSL。"""
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        with (
            patch("src.python.core.completion_notify.smtplib.SMTP", return_value=smtp) as mock_smtp,
            patch("src.python.core.completion_notify.smtplib.SMTP_SSL") as mock_ssl,
        ):
            from src.python.core.completion_notify import _send_email

            _send_email(
                {"smtp_host": "smtp.example.test", "smtp_port": 587, "use_ssl": False, "to": "a@x.y"},
                "标题",
                "正文",
                10.0,
            )
        mock_smtp.assert_called_once()
        mock_ssl.assert_not_called()
        smtp.starttls.assert_called_once()

    def test_desktop_missing_notify_send_raises(self):
        """notify-send 不可用 → 抛错（由分发层隔离，发送器本身如实报错）。"""
        from src.python.core.completion_notify import _send_desktop

        with patch("src.python.core.completion_notify.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="notify-send"):
                _send_desktop("标题", "正文")

    def test_desktop_invokes_notify_send(self):
        """notify-send 可用 → 以参数数组调用（不经 shell，无注入面）。"""
        run_mock = MagicMock()
        with (
            patch("src.python.core.completion_notify.shutil.which", return_value="/usr/bin/notify-send"),
            patch("src.python.core.completion_notify.subprocess.run", run_mock),
        ):
            from src.python.core.completion_notify import _send_desktop

            _send_desktop("标题", "正文")
        cmd = run_mock.call_args[0][0]
        assert cmd[0] == "/usr/bin/notify-send"
        assert "标题" in cmd
