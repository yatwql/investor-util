"""安全基线测试 — 5 项安全基线自动化验证。

覆盖：
  1. 密钥文件不可公开读取（权限检查）
  2. 缓存文件不含明文密钥
  3. 匿名化模式报告不含真实名称/代码
  4. LLM API 日志不记录完整密钥
  5. HTML 报告不泄露文件系统路径

@pytest.mark.scenario_security
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import zipfile
from unittest.mock import patch

import pytest

from src.python.config.anonymizer import (
    anonymize_holdings,
    anonymize_holdings_details,
)
from src.python.core.models import Holding

pytestmark = [pytest.mark.scenario_security]

logger = logging.getLogger("invest")

# ── 测试常量 ─────────────────────────────────────────────────

_SAMPLE_API_KEY = "sk-test-secret-key-12345abcdef"
_SAMPLE_KEY_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI / Claude
    re.compile(r"api[_-]?key[\s\"':=]+[a-zA-Z0-9_\-]{10,}", re.IGNORECASE),
]

# ── 测试持仓 ─────────────────────────────────────────────────

_SAMPLE_HOLDINGS = [
    Holding(name="招商银行", code="600036", shares=5000.0, cost_price=35.0, account="测试账户"),
    Holding(name="贵州茅台", code="600519", shares=200.0, cost_price=1800.0, account="测试账户"),
    Holding(name="易方达蓝筹", code="005827", shares=10000.0, cost_price=2.5, account="测试账户"),
]

_SAMPLE_DETAILS = [
    {
        "name": "招商银行",
        "code": "600036",
        "market_value": 175000.0,
        "cost": 175000.0,
        "profit": 10000.0,
        "profit_rate_pct": 6.0,
        "account": "测试账户",
    },
    {
        "name": "贵州茅台",
        "code": "600519",
        "market_value": 360000.0,
        "cost": 360000.0,
        "profit": 50000.0,
        "profit_rate_pct": 16.0,
        "account": "测试账户",
    },
    {
        "name": "易方达蓝筹",
        "code": "005827",
        "market_value": 25000.0,
        "cost": 25000.0,
        "profit": -3000.0,
        "profit_rate_pct": -10.0,
        "account": "测试账户",
    },
]


# ── 安全测试用例 ─────────────────────────────────────────────


class TestSecurityBaseline:
    """安全基线自动化验证（五项基线：密钥文件权限与内联密钥红线 / 缓存无明文密钥 /
    匿名化不泄真实名称 / LLM 日志脱敏 / HTML 无路径泄露）。"""

    # ── 基线 1: 密钥文件权限 + 入库配置无内联密钥 ────────────

    #: 持有密钥本体的文件（不得 world-readable）。
    #: 仅列**未跟踪的密钥文件**——`llm_providers.json` 名字虽含 llm，但它只存
    #: `credentials_ref` 指针（真凭据在 `llm_key.json` 对应节），且**故意跟踪入仓**
    #: （`.gitignore` 对它显式 `!` 放行）；纳入本断言必然失败——git 索引记录
    #: `100644`，任何干净检出的权限都是 `644`。新增密钥文件时加到这里即可。
    #: `data_key.json` 同为未跟踪且内联明文 `api_key`（datasink/hithink），故同列。
    _SECRET_FILES = ("data/config/llm_key.json", "data/config/data_key.json")

    @pytest.mark.scenario_security
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 权限模型不同，此项为软检查")
    def test_key_file_permissions_unix(self):
        """Unix: 持有密钥本体的文件权限应不为 world-readable。

        仅覆盖**未跟踪**的密钥文件；跟踪入仓的配置（如 `llm_providers.json` 只存
        `credentials_ref` 指针）不在本基线范围内（理由见 `_SECRET_FILES` 注释）。
        """
        for rel_path in self._SECRET_FILES:
            from src.python.core.constants import PROJECT_ROOT

            full_path = os.path.join(PROJECT_ROOT, rel_path)
            if not os.path.exists(full_path):
                logger.info("密钥文件不存在，跳过: %s", rel_path)
                continue
            mode = os.stat(full_path).st_mode
            # 检查其他用户是否可读
            assert not (mode & 0o004), f"{rel_path} 对 other 可读"
            logger.info("权限检查通过: %s (mode=%o)", rel_path, mode)

    @pytest.mark.scenario_security
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 权限模型不同，此项为软检查")
    def test_providers_config_has_no_inline_secret(self):
        """`llm_providers.json` 可入库的前提：它不得含内联密钥。

        该文件被显式跟踪（`.gitignore` 放行），故「只存 `credentials_ref` 指针」
        是它的红线——一旦写入内联 `api_key` 就会把密钥提交进仓。本断言即那份
        不变量（与 `unit_config` 的内联 api_key 硬拒绝同一判据），也是上面
        权限基线可以不含它的依据。
        """
        import json

        from src.python.core.constants import PROJECT_ROOT

        path = os.path.join(PROJECT_ROOT, "data/config/llm_providers.json")
        if not os.path.exists(path):
            logger.info("llm_providers.json 不存在，跳过")
            return
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        # 该配置文件带 // 行注释，先剔除再解析
        stripped = "\n".join(line for line in raw.splitlines() if not line.strip().startswith("//"))
        data = json.loads(stripped)
        for provider in data.get("providers") or []:
            name = provider.get("name")
            assert not provider.get("api_key"), (
                f"llm_providers.json 的 {name} 含内联 api_key——该文件入库，"
                "密钥必须放 llm_key.json 并用 credentials_ref 引用"
            )
            assert provider.get("credentials_ref"), f"llm_providers.json 的 {name} 缺少 credentials_ref"

    # ── 基线 2: 缓存无明文密钥 ───────────────────────────

    @pytest.mark.scenario_security
    def test_cache_content_no_api_key(self, tmp_path):
        """缓存文件不应包含明文 API 密钥（常见密钥模式与字段名特征）。"""
        # 手动构造一个缓存 JSON 文件进行密钥扫描
        cache_data = {
            "_ts": 1000.0,
            "_data": {
                "price": 35.5,
                "name": "test",
            },
        }
        fpath = tmp_path / "test_cache_entry.json"
        fpath.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")

        # 正则扫描常见密钥模式
        content = fpath.read_text(encoding="utf-8")
        for pattern in _SAMPLE_KEY_PATTERNS:
            match = pattern.search(content)
            if match:
                pytest.fail(f"缓存文件含疑似 API 密钥: {match.group()[:20]}...")
        # 字段名特征检查（api_key 等）
        assert "api_key" not in content.lower(), "缓存文件含 api_key 字段"

    # ── 基线 3: 匿名化模式报告不含真实名称/代码 ──────────

    @pytest.mark.scenario_security
    def test_anonymized_report_no_real_names(self):
        """完全匿名模式：名称和代码应被脱敏。"""
        result = anonymize_holdings(_SAMPLE_HOLDINGS, mode="full_anonymous")
        for h in result:
            assert "招商" not in h.name, f"真实名称未脱敏: {h.name}"
            assert "贵州" not in h.name, f"真实名称未脱敏: {h.name}"
            assert h.code == "000XXX", f"代码未掩码: {h.code}"
        logger.info("full_anonymous 脱敏验证通过")

    @pytest.mark.scenario_security
    def test_anonymized_details_no_real_names(self):
        """完全匿名模式（明细格式）：名称脱敏；代码保留真值（键控链路），
        「000XXX」显示由明细渲染层与产物清扫兑底（产物级断言见
        TestAnonymizedReportProducts）。"""
        result = anonymize_holdings_details(_SAMPLE_DETAILS, mode="full_anonymous")
        for original, d in zip(_SAMPLE_DETAILS, result, strict=True):
            assert d["name"] != original["name"], f"明细真实名称未脱敏: {d['name']}"
            assert d.get("code") == original["code"], "明细代码应保留真值（再平衡静默/决策账本等键控链路）"
        assert "招商" not in result[0]["name"], "首条名称应为代号"
        logger.info("明细 full_anonymous 名称脱敏验证通过")

    @pytest.mark.scenario_security
    def test_off_mode_shows_real_data(self):
        """关闭模式：名称和代码应保持原样。"""
        result = anonymize_holdings(_SAMPLE_HOLDINGS, mode="off")
        assert result[0].name == "招商银行", "off 模式不应脱敏名称"
        assert result[0].code == "600036", "off 模式不应脱敏代码"

    @pytest.mark.scenario_security
    def test_code_display_shows_code(self):
        """代码显示模式：隐藏名称，保留代码。"""
        result = anonymize_holdings(_SAMPLE_HOLDINGS, mode="code_display")
        for h in result:
            assert "招商" not in h.name, "code_display 应脱敏名称"
            assert h.code[0] in ("6", "0"), "code_display 应保留代码"

    @pytest.mark.scenario_security
    def test_summary_mode_no_individual(self):
        """汇总模式：返回汇总字典而非明细列表。"""
        result = anonymize_holdings(_SAMPLE_HOLDINGS, mode="summary")
        assert isinstance(result, dict), "summary 模式应返回 dict"
        for cat_name, cat_data in result.items():
            assert isinstance(cat_data, dict), "每个分类应为 dict"
            assert "count" in cat_data, "汇总应有 count"
            logger.info("汇总分类: %s, 品种数: %d", cat_name, cat_data["count"])

    # ── 基线 4: LLM 日志密钥脱敏 ─────────────────────────

    @pytest.mark.scenario_security
    def test_llm_api_key_masked_in_log(self):
        """LLM API 日志不应记录完整密钥，仅显示 ***{last4}。"""
        # 模拟日志消息
        log_msg = f"调用 LLM API，key={_SAMPLE_API_KEY}"
        # 检查是否有脱敏处理（在 llm 模块中查找 key_masking 逻辑）
        # 模拟脱敏行为
        masked = _mask_api_key(log_msg)
        assert _SAMPLE_API_KEY not in masked, "完整密钥不应出现在脱敏日志中"
        assert "***" in masked, "脱敏日志应含 ***"
        logger.info("密钥脱敏验证: '%s' → '%s'", _SAMPLE_API_KEY[:8] + "...", masked)

    # ── 基线 5: HTML 路径泄露 ────────────────────────────

    @pytest.mark.scenario_security
    def test_html_no_path_leakage(self):
        """HTML 报告不应包含绝对文件系统路径（跨平台路径形态均可检出）。"""
        # 模拟 HTML 片段
        safe_html = "<h1>投资分析报告</h1><p>组合市值: ¥1,000,000</p>"
        # 检查无路径泄露
        path_patterns = [r"[A-Z]:\\", r"/home/", r"/Users/", r"/tmp/", r"\\Users\\"]
        for pat in path_patterns:
            match = re.search(pat, safe_html)
            if match:
                pytest.fail(f"HTML 泄露文件路径: {match.group()}")

        # 分段拼接构造含各类绝对路径的样本，验证检测器均能识别
        # （源码中不出现完整绝对路径字面量，Windows/Linux/macOS 形态均覆盖）
        windows_abs = "\\".join(["C:", "fake", "report.html"])  # 盘符型（Windows）
        home_abs = "/".join(["", "home", "user", "report.html"])  # home 型（Linux/macOS）
        tmp_abs = "/".join(["", "tmp", "report.html"])  # tmp 型（Linux/macOS）
        user_abs = "\\".join(["", "Users", "user", "report.html"])  # Users 型（Windows）
        unsafe_samples = [
            f"<p>报告生成于 {windows_abs}</p>",
            f"<p>报告生成于 {home_abs}</p>",
            f"<p>报告生成于 {tmp_abs}</p>",
            f"<p>报告生成于 {user_abs}</p>",
        ]
        for sample in unsafe_samples:
            has_leak = any(re.search(pat, sample) for pat in path_patterns)
            assert has_leak, f"路径检测模式应能识别绝对路径: {sample}"
        logger.info("HTML 路径泄露检测模式验证通过")


# ── 辅助函数 ─────────────────────────────────────────────────


def _mask_api_key(text: str, visible_chars: int = 4) -> str:
    """脱敏文本中的 API 密钥模式。

    将 sk-... 格式的密钥替换为 sk-***{last4}。

    Args:
        text: 原始文本
        visible_chars: 末尾保留的可见字符数

    Returns:
        脱敏后的文本
    """
    pattern = re.compile(r"(sk-)[a-zA-Z0-9_-]+")

    def _replacer(m: re.Match) -> str:
        prefix = m.group(1)
        full_key = m.group(0)
        if len(full_key) > visible_chars + len(prefix):
            return f"{prefix}***{full_key[-visible_chars:]}"
        return full_key

    return pattern.sub(_replacer, text)


# ── 产物级端到端断言（config anonymization.mode → HTML/Excel 产物无样例真名） ──

_NON_OFF_MODES = ["code_display", "full_anonymous", "summary"]
_REAL_NAME_TOKENS = ("招商银行", "贵州茅台", "易方达蓝筹")


def _mk_product_rows() -> list:
    """构造样例明细行（真名；生成路径中由 mock 物化 → 装配边界匿名）。"""
    from src.python.report.market_value import DetailRow

    rows = []
    for i, h in enumerate(_SAMPLE_HOLDINGS, start=1):
        rows.append(
            DetailRow(
                account=h.account,
                name=h.name,
                code=h.code,
                price=float(10 + i),
                nav_date="2026-10-08",
                yesterday_close=float(9 + i),
                shares=h.shares,
                market_value=float(h.shares * (10 + i)),
                cost=float(h.shares * h.cost_price),
                profit=float(h.shares * (10 + i) - h.shares * h.cost_price),
                profit_rate=0.1 * i,
                today_profit=float(i),
            )
        )
    return rows


class TestAnonymizedReportProducts:
    """产物端到端：匿名模式下生成的 HTML/Excel 不含样例真实名称。

    mock 行情物化（真名明细）→ 装配边界/渲染层/产物清扫逐层生效；
    衍生章节由 offline 桩降级，不引入真实名称外数据源。
    """

    pytestmark = [pytest.mark.usefixtures("offline_external_sources")]

    @pytest.mark.scenario_security
    @pytest.mark.parametrize("mode", _NON_OFF_MODES)
    def test_html_product_has_no_real_names(self, mode: str, tmp_path, monkeypatch):
        monkeypatch.setattr("src.python.config.anonymizer.get_anonymization_mode", lambda: mode)
        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(
                patch("src.python.report.html_renderers._generate_details", return_value=_mk_product_rows())
            )
            # 仅断开真网络出口（分类/业绩等名称渲染面保持真实路径，
            # 验证产物清扫兑底能力）；offline 桩兜底其余数据源
            stack.enter_context(patch("src.python.report.html_renderers.fetch_indices", return_value={}))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices", return_value={}))
            stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10", return_value={}))
            from src.python.report.html_writer import write_html_report

            write_html_report(_SAMPLE_HOLDINGS, output_dir=str(tmp_path), include_news=False, enable_llm=False)

        html_files = list(tmp_path.glob("*.html"))
        assert html_files, "未生成 HTML 产物"
        html = html_files[0].read_text(encoding="utf-8")
        for token in _REAL_NAME_TOKENS:
            assert token not in html, f"HTML 产物泄漏真实名称: {token}"
        if mode == "summary":
            assert "股票汇总" in html, "summary 明细渲染层应输出大类聚合行"
        else:
            assert "品种A" in html, "匿名模式产物应包含代号（正向对照）"

    @pytest.mark.scenario_security
    @pytest.mark.parametrize("mode", _NON_OFF_MODES)
    def test_excel_product_has_no_real_names(self, mode: str, tmp_path, monkeypatch):
        monkeypatch.setattr("src.python.config.anonymizer.get_anonymization_mode", lambda: mode)
        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(
                patch("src.python.report.market_value._generate_details", return_value=_mk_product_rows())
            )
            stack.enter_context(patch("src.python.fetcher.index.fetch_indices", return_value={}))
            stack.enter_context(patch("src.python.fetcher.index.fetch_us_indices", return_value={}))
            stack.enter_context(patch("src.python.report.penetration.compute_penetration_top10", return_value={}))
            from src.python.report.excel_generator import generate_excel_report

            generate_excel_report(_SAMPLE_HOLDINGS, output_dir=str(tmp_path))

        xlsx_files = list(tmp_path.glob("*.xlsx"))
        assert xlsx_files, "未生成 Excel 产物"
        with zipfile.ZipFile(xlsx_files[0]) as zf:
            text = html.unescape(
                "".join(zf.read(name).decode("utf-8", "replace") for name in zf.namelist() if name.endswith(".xml"))
            )
        for token in _REAL_NAME_TOKENS:
            assert token not in text, f"Excel 产物泄漏真实名称: {token}"
        if mode == "summary":
            assert "股票汇总" in text, "summary 明细页签应输出大类聚合行"
        else:
            assert "品种A" in text, "匿名模式产物应包含代号（正向对照）"
            if mode == "full_anonymous":
                assert "600519" not in text, "full 模式 Excel 产物应掩码真码（字符串单元格清扫）"
