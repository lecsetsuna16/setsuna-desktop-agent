---
name: rss-reader
description: Fetch and parse RSS/Atom feeds to show latest articles. Use when the user asks to check a blog, subscribe to a feed, read latest posts from a site, or monitor updates from any URL that has an RSS or Atom feed.
x-resona-triggers:
  - "rss"
  - "订阅源"
  - "最新文章"
  - "帮我看看博客"
  - "有没有更新"
  - "订阅这个"
  - "最新动态"
  - "feed"
x-resona-model: reasoner
---

# RSS Reader

Fetch and parse RSS/Atom feeds using the `fetch_url` MCP tool.

**IMPORTANT: You MUST use the `fetch_url` tool to retrieve feed content. Do NOT use exec_shell, curl, wget, or any shell command.**

## Workflow

### Step 1: Fetch the feed

Call `fetch_url` with the RSS/Atom URL and `max_chars=8000`. This tool is always available — use it directly.

Common feed URL patterns to try if user gives a homepage URL:
- `<url>/feed`
- `<url>/rss`
- `<url>/atom.xml`
- `<url>/feed.xml`
- `<url>/rss.xml`

### Step 2: Identify feed format

**RSS 2.0** — look for `<rss` or `<channel>`:
```
<item>
  <title>文章标题</title>
  <link>https://...</link>
  <pubDate>Tue, 08 Apr 2026 10:00:00 +0000</pubDate>
  <description>摘要内容</description>
</item>
```

**Atom** — look for `<feed` or `<entry>`:
```
<entry>
  <title>文章标题</title>
  <link href="https://..."/>
  <updated>2026-04-08T10:00:00Z</updated>
  <summary>摘要内容</summary>
</entry>
```

### Step 3: Extract and present

Extract the latest **5 items** (or fewer if feed is short). Present as:

```
📰 [Feed名称] 最新更新

1. 标题
   链接：https://...
   时间：2026-04-08
   摘要：前100字...

2. ...
```

## Edge Cases

- **Non-XML response**: The URL is not a feed. Ask user to provide direct feed URL.
- **403/blocked**: Try appending `/feed` or `/rss` to the base URL.
- **Empty feed**: Report "暂无新文章" and show feed title.
- **No pubDate**: Sort by order in document (assume top = newest).

## Notes

- `fetch_url` strips HTML tags — raw XML tags remain visible in output, parse them as text patterns.
- Prefer `<title>` content between tags over attributes.
- If user doesn't specify count, show 5 items max to avoid context bloat.
