import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SearchTools")

# ── 路由关键词 ────────────────────────────────────────────────────────────────
ROUTING_KEYWORDS = [
    "帮我搜", "搜一下", "网上搜", "联网搜",
    "查最新", "查今天", "搜新闻",
    "谁赢了", "谁拿了冠军", "比赛结果",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

_MAX_QUERY_LEN = 200
_DDG_URL = "https://html.duckduckgo.com/html/"


def _sanitize_query(query: str) -> str:
    """Strip control characters and enforce length limit."""
    query = re.sub(r"[\x00-\x1f\x7f]", " ", query)
    return query.strip()[:_MAX_QUERY_LEN]


def _parse_ddg(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for block in soup.select(".result__body"):
        if len(results) >= max_results:
            break
        title_el  = block.select_one(".result__title a")
        snippet_el = block.select_one(".result__snippet")
        url_el     = block.select_one(".result__url")
        title   = title_el.get_text(strip=True)   if title_el   else ""
        snippet = snippet_el.get_text(strip=True)  if snippet_el else ""
        url     = url_el.get_text(strip=True)      if url_el     else ""
        if title or snippet:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


@mcp.tool()
def web_search(query: str, max_results: int = 6) -> str:
    """Search the web via DuckDuckGo and return summarised results.

    Use this when you need current information (news, scores, events, prices)
    and do NOT know the exact URL to visit.
    After finding a relevant result, use fetch_url to read the full page.

    Do NOT use this for general knowledge questions you can answer yourself.

    Args:
        query: Search query in any language.
        max_results: Number of results to return (1-10, default 6).
    """
    query = _sanitize_query(query)
    if not query:
        return "Error: Empty query."

    max_results = max(1, min(max_results, 10))
    encoded = urllib.parse.quote_plus(query)

    try:
        resp = requests.post(
            _DDG_URL,
            data={"q": query, "b": "", "kl": ""},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        results = _parse_ddg(resp.text, max_results)

        if not results:
            # Fallback: try GET if POST returned nothing
            resp2 = requests.get(
                f"{_DDG_URL}?q={encoded}",
                headers=_HEADERS,
                timeout=15,
            )
            resp2.raise_for_status()
            results = _parse_ddg(resp2.text, max_results)

        if not results:
            return f"No results found for: {query}"

        lines = [f'Search: "{query}"\n']
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r['title']}")
            if r["url"]:
                lines.append(f"    {r['url']}")
            if r["snippet"]:
                lines.append(f"    {r['snippet']}")
            lines.append("")
        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return "Error: Search timed out."
    except requests.exceptions.HTTPError as e:
        return f"Error: HTTP {e.response.status_code} from DuckDuckGo."
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
