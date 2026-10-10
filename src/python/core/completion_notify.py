"""任务完成通知 — 报告生成完成/失败的可配置通知钩子（无人值守场景）。

cron/计划任务等无人值守运行只有退出码与日志，成功/失败都要人工翻日志；
本模块在 CLI 报告收尾时按配置向已配置通道推送一条摘要事件：

- 通道：webhook（HTTP POST JSON）/ 邮件（SMTP）/ 桌面通知（notify-send）
- 触发：失败（exit_code != 0）必发；成功仅 ``notify.on_success=true`` 时发
- 缺省：config.json 无 ``notify`` 节或全部通道未配置 → 静默跳过（默认关，
  符合「配置文件不必须存在」惯例）
- 载荷：报告类型 / 退出码 / 产物路径（命名单源 `core.constants` 最新版名）/
  错误数与错误明细（截断）/ 降级摘要（由 CLI 层从数据状态跟踪器收集后传入）

架构约束（对照技术设计文档「架构设计约束」表，此处一律用语义描述）：
  HTTP 客户端统一 — webhook 走 `core.http_client.make_http_client`
     （SSL/超时/回放传输注入同源，禁自建 client）
  日志统一 — `logging.getLogger("invest")`，禁 print
  凭据值不落日志 — webhook URL 常含路径凭据（如 bot token），日志只记
     通道名与域名（异常消息中的完整 URL 先掩码）；邮件口令不进任何日志
  退出码契约 — 通知是尽力而为（best-effort）：任何通道失败只记日志，
     绝不抛出、绝不改变 CLI 退出码；单次尝试**不重试**（收尾路径不引入
     退避等待，故不经重试原语——无「失败后重试」即无该约束适用面）

测试：`src/test/unit/core/test_completion_notify.py`
"""

from __future__ import annotations

import logging
import os
import shutil
import smtplib
import subprocess
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Callable
from urllib.parse import urlparse

from src.python.core.constants import LATEST_HTML_NAME, LATEST_XLSX_NAME
from src.python.core.http_client import make_http_client

logger = logging.getLogger("invest")

__all__ = [
    "build_completion_event",
    "dispatch_completion_notification",
    "should_notify",
]

# 错误明细载荷上限（防超大载荷；error_count 恒为全量计数不受截断影响）
_MAX_ERROR_ITEMS = 20


# ── 门控 ───────────────────────────────────────────────────


def _configured_channels(cfg: dict) -> list[str]:
    """返回已配置通道名列表（webhook/email/desktop；单源，门控与分发共用）。"""
    channels: list[str] = []
    if str(cfg.get("webhook_url") or "").strip():
        channels.append("webhook")
    email_cfg = cfg.get("email") or {}
    if str(email_cfg.get("smtp_host") or "").strip() and str(email_cfg.get("to") or "").strip():
        channels.append("email")
    if cfg.get("desktop"):
        channels.append("desktop")
    return channels


def should_notify(notify_cfg: dict | None, *, ok: bool) -> bool:
    """是否应发送通知（配置门控，纯函数）。

    Args:
        notify_cfg: config.json 的 ``notify`` 节（缺失/None = 未配置）
        ok: 本次运行是否完全成功（exit_code == 0）

    Returns:
        False 当无任何通道配置（静默跳过），或成功且未开 ``on_success``
    """
    cfg = notify_cfg or {}
    if not _configured_channels(cfg):
        return False
    if ok and not cfg.get("on_success"):
        return False
    return True


# ── 事件载荷 ────────────────────────────────────────────────


def build_completion_event(
    *,
    report_type: str,
    exit_code: int,
    output_dir: str | os.PathLike[str],
    errors: list[str] | Any,
    excel_ok: bool = False,
    html_ok: bool = False,
    degradations: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """构造通知事件载荷（纯函数；产物路径按结果标志 + 命名单源推导）。

    Args:
        report_type: 报告类型（basic/both/full）
        exit_code: CLI 退出码（0 成功 / 1 部分失败 / 2 严重错误）
        output_dir: 报告输出目录（相对路径按 CWD 绝对化）
        errors: 报告结果错误明细（任意可迭代；逐条转 str，超长截断）
        excel_ok / html_ok: 对应产物是否生成成功（决定产物路径列示）
        degradations: 降级摘要行（CLI 层从数据状态跟踪器收集后传入）
        now: 时间戳注入（测试用；缺省取当前本地时间）

    Returns:
        JSON 可序列化事件 dict（键见模块 docstring「载荷」段）
    """
    errs = [str(e) for e in (errors or [])]
    base = os.path.abspath(os.fspath(output_dir) or ".")
    artifacts: list[str] = []
    if excel_ok:
        artifacts.append(os.path.join(base, LATEST_XLSX_NAME))
    if html_ok:
        artifacts.append(os.path.join(base, LATEST_HTML_NAME))
    ts = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    return {
        "event": "report.completed",
        "ok": exit_code == 0,
        "exit_code": int(exit_code),
        "report_type": str(report_type or ""),
        "generated_at": ts,
        "artifacts": artifacts,
        "error_count": len(errs),
        "errors": errs[:_MAX_ERROR_ITEMS],
        "degradations": [str(d) for d in (degradations or [])],
    }


# ── 文本格式化（邮件/桌面共用；webhook 直接发 JSON） ─────────


def _format_text(event: dict) -> str:
    """事件 → 纯文本摘要（邮件正文与桌面通知正文单源）。"""
    lines = [
        f"报告类型: {event.get('report_type') or '-'}",
        f"结果: {'成功' if event.get('ok') else '失败'}（退出码 {event.get('exit_code')}）",
        f"生成时间: {event.get('generated_at')}",
        f"错误数: {event.get('error_count', 0)}",
    ]
    if event.get("artifacts"):
        lines.append("产物: " + "、".join(event["artifacts"]))
    errs = event.get("errors") or []
    if errs:
        lines.append("错误明细:")
        lines.extend(f"  - {e}" for e in errs)
    degr = event.get("degradations") or []
    if degr:
        lines.append("降级摘要:")
        lines.extend(f"  - {d}" for d in degr)
    return "\n".join(lines)


def _format_subject(event: dict) -> str:
    """事件 → 通知标题（三通道单源）。"""
    status = "成功" if event.get("ok") else "失败"
    rtype = event.get("report_type") or "报告"
    return f"[投资复盘] {rtype} 生成{status}（{event.get('error_count', 0)} 个错误）"


# ── 通道发送器（单次尝试，失败向上抛由分发层捕获） ────────────


def _send_webhook(url: str, payload: dict, timeout: float) -> None:
    """webhook POST JSON（经统一 HTTP 客户端工厂，禁自建 client）。"""
    with make_http_client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()


def _send_email(email_cfg: dict, subject: str, body: str, timeout: float) -> None:
    """SMTP 邮件（SSL 或 STARTTLS，按 use_ssl 切换）。"""
    host = str(email_cfg.get("smtp_host") or "").strip()
    port = int(email_cfg.get("smtp_port") or 465)
    username = str(email_cfg.get("username") or "")
    password = str(email_cfg.get("password") or "")
    to_raw = str(email_cfg.get("to") or "")
    recipients = [a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip()]
    if not recipients:
        raise ValueError("notify.email.to 为空")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = username or "investor-util"
    msg["To"] = ", ".join(recipients)

    if bool(email_cfg.get("use_ssl", True)):
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
        smtp.starttls()
    with smtp:
        if username:
            smtp.login(username, password)
        smtp.sendmail(msg["From"], recipients, msg.as_string())


def _send_desktop(title: str, body: str) -> None:
    """桌面通知（notify-send；未安装时抛错由分发层记日志跳过）。"""
    exe = shutil.which("notify-send")
    if not exe:
        raise RuntimeError("未找到 notify-send（桌面通知不可用）")
    subprocess.run(
        [exe, "--app-name", "投资复盘", title, body],
        check=True,
        timeout=10,
        capture_output=True,
    )


# ── 分发 ───────────────────────────────────────────────────


def _mask_url(url: str) -> str:
    """URL 掩码为「协议://域名/***」（路径/查询串常含凭据，凭据不落日志）。"""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "***"
    return f"{parsed.scheme}://{parsed.netloc}/***"


def _attempt(channel: str, fn: Callable[[], None], *, secret: str = "") -> bool:
    """执行单通道发送：失败只记日志（secret 掩码后入消息），返回是否成功。"""
    try:
        fn()
        logger.info("[notify] %s 通道已发送", channel)
        return True
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        if secret and secret in msg:
            msg = msg.replace(secret, _mask_url(secret))
        logger.warning("[notify] %s 通道发送失败（不影响退出码）：%s", channel, msg)
        return False


def dispatch_completion_notification(event: dict, notify_cfg: dict | None) -> bool:
    """门控 + 分发完成通知（尽力而为，永不抛出）。

    Args:
        event: `build_completion_event` 输出（或同形 dict）
        notify_cfg: config.json 的 ``notify`` 节

    Returns:
        是否至少一个通道发送成功（门控未过 / 全部失败 → False）
    """
    try:
        cfg = notify_cfg or {}
        if not should_notify(cfg, ok=bool(event.get("ok"))):
            return False
        channels = _configured_channels(cfg)
        text = _format_text(event)
        subject = _format_subject(event)
        timeout = float(cfg.get("timeout_seconds") or 10)

        sent = False
        if "webhook" in channels:
            url = str(cfg.get("webhook_url") or "").strip()
            # secret=url：异常消息可能内嵌完整 URL，落日志前掩码（凭据不落日志纪律）
            sent = _attempt("webhook", lambda: _send_webhook(url, event, timeout), secret=url) or sent
        if "email" in channels:
            email_cfg = cfg.get("email") or {}
            sent = _attempt("email", lambda: _send_email(email_cfg, subject, text, timeout)) or sent
        if "desktop" in channels:
            sent = _attempt("desktop", lambda: _send_desktop(subject, text)) or sent
        return sent
    except Exception:
        logger.warning("[notify] 通知分发异常（非关键，不影响退出码）", exc_info=True)
        return False
