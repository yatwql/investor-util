#!/usr/bin/env python3
"""诊断 Gemini API 代理连通性。"""

import os, sys, json
import httpx

PROXY = "http://10.22.207.29:10037"


def _load_json_with_comments(path: str) -> dict | None:
    """加载含 // 注释的非标准 JSON 文件（与项目 _core.py 兼容）。"""
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = f.read()
    except Exception:
        return None
    # 去掉 // 行注释（只去掉行首空白后的 //）
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        # 去掉行内 // 注释（保留字符串内的 //）
        in_str = False
        clean = ""
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == '"':
                in_str = not in_str
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/" and not in_str:
                break  # 注释开始，丢弃剩余
            clean += ch
            i += 1
        lines.append(clean)
    clean_text = "\n".join(lines)
    try:
        return json.loads(clean_text)
    except Exception:
        return None


def _find_gemini_model() -> str:
    """从 llm_key.json 读取实际配置的 Gemini 模型名。"""
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    key_path = os.path.join(base, "data", "config", "llm_key.json")
    if os.path.exists(key_path):
        cfg = _load_json_with_comments(key_path)
        if isinstance(cfg, dict):
            for k, v in cfg.items():
                if "gemini" in k.lower() and isinstance(v, dict):
                    return v.get("model", "gemini-2.5-flash")
    return "gemini-2.5-flash"


GEMINI_MODEL = _find_gemini_model()
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"

PASS = "  [OK]"
FAIL = "  [ERR]"


def test(name: str, fn):
    print(f"\n▶ {name}")
    try:
        fn()
        print(f"{PASS}")
    except Exception as e:
        print(f"{FAIL} {e}")


# ── 1. 不通过代理，直连 Google ──
def test_direct():
    r = httpx.get(GEMINI_URL, timeout=5)
    print(f"   状态码: {r.status_code}")
    print(f"   响应: {r.text[:200]}")


# ── 2. 通过代理连接 Google ──
def test_via_proxy():
    r = httpx.get(GEMINI_URL, timeout=10, proxy=PROXY)
    print(f"   状态码: {r.status_code}")
    print(f"   响应: {r.text[:200]}")


# ── 3. 通过代理+API Key 调用 Gemini ──
def test_auth_via_proxy():
    api_key = os.environ.get("GEMINI_API_KEY") or _find_key_in_config()
    if not api_key:
        raise RuntimeError("未找到 Gemini API Key")
    url = f"{GEMINI_URL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "你好"}]}],
        "generationConfig": {"maxOutputTokens": 50},
    }
    r = httpx.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=15, proxy=PROXY)
    print(f"   状态码: {r.status_code}")
    print(f"   响应: {r.text[:300]}")


def _find_key_in_config() -> str | None:
    """从 llm_key.json 中提取 Gemini API Key。"""
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    key_path = os.path.join(base, "data", "config", "llm_key.json")
    if not os.path.exists(key_path):
        return None
    cfg = _load_json_with_comments(key_path)
    if not isinstance(cfg, dict):
        return None
    # 多键格式: 遍历各凭据块找 gemini 相关的
    for k, v in cfg.items():
        if "gemini" in k.lower() and isinstance(v, dict):
            return v.get("api_key") or None
    # flat 格式
    return cfg.get("api_key") or None


if __name__ == "__main__":
    print("=" * 50)
    print("Gemini API 代理连通性诊断")
    print(f"代理: {PROXY}")
    print(f"模型: {GEMINI_MODEL}")
    print("=" * 50)

    print(f"\n{'─' * 40}")
    print("环境变量检查")
    for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        val = os.environ.get(var, "")
        print(f"  {var}={val}" if val else f"  {var}=（未设置）")

    has_key = _find_key_in_config() or os.environ.get("GEMINI_API_KEY")
    print(f"  GEMINI_API_KEY={'已找到' if has_key else '未找到（只测试连通性）'}")

    test("1. 直连 Google（不通过代理）", test_direct)
    test("2. 通过代理连接 Google", test_via_proxy)

    if has_key:
        test("3. 通过代理调用 Gemini API（带 Key）", test_auth_via_proxy)
    else:
        print(f"\n▶ 3. 跳过（未找到 API Key，需 API Key 才能调用）")

    print(f"\n{'=' * 50}")
    print("诊断完成")
    print("=" * 50)
