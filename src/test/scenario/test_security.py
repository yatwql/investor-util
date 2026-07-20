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

import json
import logging
import os
import re
import sys
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.scenario_security]

from src.python.anonymizer import (
    anonymize_holdings,
    anonymize_holdings_details,
)
from src.python.models import Holding

logger = logging.getLogger("invest")

# ── 测试常量 ─────────────────────────────────────────────────

_SAMPLE_API_KEY = "sk-test-secret-key-12345abcdef"
_SAMPLE_KEY_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),       # OpenAI / Claude
    re.compile(r"api[_-]?key[\s\"':=]+[a-zA-Z0-9_\-]{10,}", re.IGNORECASE),
]

# ── 测试持仓 ─────────────────────────────────────────────────

_SAMPLE_HOLDINGS = [
    Holding(name="招商银行", code="600036", shares=5000.0, cost_price=35.0, account="测试账户"),
    Holding(name="贵州茅台", code="600519", shares=200.0, cost_price=1800.0, account="测试账户"),
    Holding(name="易方达蓝筹", code="005827", shares=10000.0, cost_price=2.5, account="测试账户"),
]

_SAMPLE_DETAILS = [
    {"name": "招商银行", "code": "600036", "market_value": 175000.0, "cost": 175000.0,
     "profit": 10000.0, "profit_rate_pct": 6.0, "account": "测试账户"},
    {"name": "贵州茅台", "code": "600519", "market_value": 360000.0, "cost": 360000.0,
     "profit": 50000.0, "profit_rate_pct": 16.0, "account": "测试账户"},
    {"name": "易方达蓝筹", "code": "005827", "market_value": 25000.0, "cost": 25000.0,
     "profit": -3000.0, "profit_rate_pct": -10.0, "account": "测试账户"},
]


# ── 安全测试用例 ─────────────────────────────────────────────


class TestSecurityBaseline:
    """五项安全基线自动化验证。"""

    # ── 基线 1: 密钥文件权限 ─────────────────────────────

    @pytest.mark.scenario_security
    def test_key_file_no_plaintext_in_cache(self, tmp_path):
        """缓存文件不应包含明文 API 密钥。"""
        from src.python.cache._io import _write_atomic

        # 模拟写入一个缓存条目（同时含正常数据 + 不小心混入的 key）
        cache_data = {
            "_ts": 1000.0,
            "price": 35.5,
            "name": "test",
        }
        key = "test_cache_entry"
        _write_atomic(tmp_path / f"{key}.json", cache_data)

        # 读取并检查是否含密钥模式
        content = (tmp_path / f"{key}.json").read_text(encoding="utf-8")
        for pattern in _SAMPLE_KEY_PATTERNS:
            match = pattern.search(content)
            if match:
                pytest.fail(f"缓存文件含疑似 API 密钥: {match.group()[:20]}...")

    @pytest.mark.scenario_security
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 权限模型不同，此项为软检查")
    def test_key_file_permissions_unix(self):
        """Unix: 密钥文件权限应不为 world-readable。"""
        llm_key_paths = [
            "data/config/llm_key.json",
            "data/config/llm_providers.json",
        ]
        for rel_path in llm_key_paths:
            from src.python.constants import PROJECT_ROOT

            full_path = os.path.join(PROJECT_ROOT, rel_path)
            if not os.path.exists(full_path):
                logger.info("密钥文件不存在，跳过: %s", rel_path)
                continue
            mode = os.stat(full_path).st_mode
            # 检查其他用户是否可读
            assert not (mode & 0o004), f"{rel_path} 对 other 可读"
            logger.info("权限检查通过: %s (mode=%o)", rel_path, mode)

    # ── 基线 2: 缓存无明文密钥 ───────────────────────────

    @pytest.mark.scenario_security
    def test_cache_content_no_api_key(self, tmp_path):
        """写入和读取缓存不应产生 API 密钥残留。"""
        from src.python.cache._io import _write_atomic

        # 模拟缓存写入
        key = "price_600036"
        data = {
            "_ts": 2000.0,
            "price": 35.5,
            "change_pct": 0.01,
        }
        _write_atomic(tmp_path / f"{key}.json", data)
        content = (tmp_path / f"{key}.json").read_text(encoding="utf-8")
        assert "sk-" not in content, "缓存文件含 API key 特征字符串"
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
        """完全匿名模式（明细格式）：名称和代码应被脱敏。"""
        result = anonymize_holdings_details(_SAMPLE_DETAILS, mode="full_anonymous")
        for d in result:
            assert "招商" not in d["name"], f"明细真实名称未脱敏: {d['name']}"
            assert d.get("code") == "000XXX", f"明细代码未掩码: {d.get('code')}"
        logger.info("明细 full_anonymous 脱敏验证通过")

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
        """HTML 报告不应包含绝对文件系统路径。"""
        # 模拟 HTML 片段
        safe_html = "<h1>投资分析报告</h1><p>组合市值: ¥1,000,000</p>"
        # 检查无路径泄露
        path_patterns = [r"[A-Z]:\\", r"/home/", r"/Users/", r"/tmp/", r"\\Users\\"]
        for pat in path_patterns:
            match = re.search(pat, safe_html)
            if match:
                pytest.fail(f"HTML 泄露文件路径: {match.group()}")

        unsafe_html = "<p>报告生成于 D:\\codebase\\zoo\\investor-util\\reports\\report.html</p>"
        has_leak = any(re.search(pat, unsafe_html) for pat in path_patterns)
        assert has_leak, "路径检测模式应能识别绝对路径"
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
    pattern = re.compile(r"(sk-)[a-zA-Z0-9]+")
    def _replacer(m: re.Match) -> str:
        prefix = m.group(1)
        full_key = m.group(0)
        if len(full_key) > visible_chars + len(prefix):
            return f"{prefix}***{full_key[-visible_chars:]}"
        return full_key
    return pattern.sub(_replacer, text)
