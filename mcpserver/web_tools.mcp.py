import re
import socket
import ipaddress
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("WebTools")

# ── 路由关键词（动态注入路由正则，新增MCP时照此格式填写）──────────────────────
ROUTING_KEYWORDS = [
    "帮我搜", "帮我查", "搜一下", "查一下", "联网查",
    "访问网页", "打开网址", "获取网页", "抓取", "爬取",
    "查新闻", "查资讯", "查天气", "查价格", "查汇率", "查股票",
]

# === SSRF 防护 ===
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # loopback
    ipaddress.ip_network("0.0.0.0/8"),      # "this" network (maps to localhost on many OS)
    ipaddress.ip_network("10.0.0.0/8"),     # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918
    ipaddress.ip_network("192.168.0.0/16"), # RFC1918
    ipaddress.ip_network("169.254.0.0/16"), # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("::1/128"),        # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),       # IPv6 private (ULA)
    ipaddress.ip_network("fe80::/10"),      # IPv6 link-local
]

def _is_ssrf_safe(url: str) -> tuple[bool, str]:
    """解析 URL 的目标 IP，拒绝内网地址。返回 (is_safe, reason)。"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "无法解析 hostname"
        # 解析为 IP（getaddrinfo 会解析 DNS）
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip_str = info[4][0]
            ip = ipaddress.ip_address(ip_str)
            for net in _PRIVATE_NETWORKS:
                if ip in net:
                    return False, f"SSRF blocked: {hostname} → {ip_str} 属于内网地址 {net}"
        return True, ""
    except socket.gaierror:
        return False, f"DNS 解析失败：{hostname}"
    except Exception as e:
        return False, f"地址校验异常：{e}"
# =================

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_JUNK_TAGS = ["script", "style", "noscript", "header", "footer", "nav",
              "aside", "form", "iframe", "svg", "button", "input", "select", "option"]


def _extract_text(html: str, max_chars: int = 4000) -> str:
    """Parse HTML and return clean readable text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_JUNK_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse blank lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n…[截断，共 {len(text)} 字符，仅显示前 {max_chars}]"
    return text


@mcp.tool()
def fetch_url(url: str, timeout: int = 15, max_chars: int = 4000) -> str:
    """Fetch the content of a URL and return clean readable text (HTML stripped).

    Use this to retrieve web page content, news articles, prices, or any
    publicly accessible URL that does not require login or CAPTCHA.

    Args:
        url: The full URL to fetch (must start with http:// or https://).
        timeout: Request timeout in seconds (default 15).
        max_chars: Maximum characters to return (default 4000, max 8000).
    """
    max_chars = min(max_chars, 8000)

    if not re.match(r"https?://", url, re.IGNORECASE):
        return "Error: URL must start with http:// or https://"

    safe, reason = _is_ssrf_safe(url)
    if not safe:
        return f"Error: {reason}"

    try:
        # allow_redirects=False：手动跟踪重定向，每步都做 SSRF 检查
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=False)
        # 手动跟踪最多 5 次重定向，每次都检查目标地址
        for _ in range(5):
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            redirect_url = resp.headers.get("Location", "")
            if not redirect_url:
                break
            if not re.match(r"https?://", redirect_url, re.IGNORECASE):
                return f"Error: Redirect to non-HTTP URL blocked: {redirect_url}"
            safe, reason = _is_ssrf_safe(redirect_url)
            if not safe:
                return f"Error: {reason} (via redirect)"
            resp = requests.get(redirect_url, headers=_HEADERS, timeout=timeout, allow_redirects=False)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text" not in content_type and "json" not in content_type and "xml" not in content_type:
            return f"Error: Unsupported content type '{content_type}'. Only text/HTML pages are supported."
        if "json" in content_type or "xml" in content_type:
            return resp.text[:max_chars]
        encoding = resp.apparent_encoding or "utf-8"
        html = resp.content.decode(encoding, errors="replace")
        return _extract_text(html, max_chars)
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout}s."
    except requests.exceptions.HTTPError as e:
        return f"Error: HTTP {e.response.status_code} — {e.response.reason}"
    except requests.exceptions.ConnectionError:
        return "Error: Connection failed. Check network or URL."
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
