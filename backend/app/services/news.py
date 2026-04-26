import html
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from urllib.parse import quote, quote_plus, urlparse

import httpx


DEFAULT_GLOBAL_NEWS_FEEDS = [
    {
        "feed_id": "default:bbc_business",
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "category": "business",
    },
    {
        "feed_id": "default:bbc_world",
        "name": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "world_macro",
    },
    {
        "feed_id": "default:guardian_business",
        "name": "The Guardian Business",
        "url": "https://www.theguardian.com/uk/business/rss",
        "category": "business",
    },
    {
        "feed_id": "default:npr_business",
        "name": "NPR Business",
        "url": "https://feeds.npr.org/1006/rss.xml",
        "category": "business",
    },
    {
        "feed_id": "default:abc_business",
        "name": "ABC News Business",
        "url": "https://abcnews.go.com/abcnews/businessheadlines",
        "category": "business",
    },
    {
        "feed_id": "default:aljazeera_global",
        "name": "Al Jazeera Global",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "category": "world_macro",
    },
    {
        "feed_id": "default:fortune",
        "name": "Fortune",
        "url": "https://fortune.com/feed/",
        "category": "business",
    },
    {
        "feed_id": "default:forbes_business",
        "name": "Forbes Business",
        "url": "https://www.forbes.com/business/feed/",
        "category": "business",
    },
    {
        "feed_id": "default:fed_press",
        "name": "Federal Reserve Press Releases",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "category": "central_bank",
    },
    {
        "feed_id": "default:ecb_press",
        "name": "ECB Press Releases",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "category": "central_bank",
    },
]


def collect_global_news(
    enabled_sources: List[Dict[str, Any]],
    stocks: List[Dict[str, Any]],
    interest_areas: List[Dict[str, Any]],
    max_items: int = 24,
) -> Dict[str, Any]:
    feeds = _feed_sources(enabled_sources, stocks, interest_areas)[:12]
    items = []
    errors = []
    seen = set()

    with ThreadPoolExecutor(max_workers=max(1, min(6, len(feeds)))) as executor:
        futures = {executor.submit(_fetch_feed_items, feed): feed for feed in feeds}
        for future in as_completed(futures):
            feed = futures[future]
            try:
                for item in future.result():
                    key = item["url"] or item["title"]
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(item)
                    if len(items) >= max_items:
                        break
            except Exception as exc:
                errors.append({"source": feed["name"], "url": feed["url"], "error": f"{type(exc).__name__}: {exc}"})
            if len(items) >= max_items:
                break

    return {
        "items": items[:max_items],
        "sources": feeds,
        "errors": errors,
        "coverage_note": "RSS/search feed based headline collection. Use linked source URLs for full article verification.",
    }


def fetch_article_body(url: str) -> Dict[str, Any]:
    timeout = httpx.Timeout(6.0, connect=3.0, read=4.0, write=3.0, pool=2.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        source_url = _resolve_google_news_url(client, url)
        response = client.get(source_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "xml" not in content_type:
            return {
                "resolved_url": str(response.url),
                "source_url": source_url,
                "body": "",
                "content_type": content_type,
            }
        body = _extract_article_text(response.text)
        return {
            "resolved_url": str(response.url),
            "source_url": source_url,
            "body": body[:20000],
            "content_type": content_type,
        }


def _feed_sources(
    enabled_sources: List[Dict[str, Any]],
    stocks: List[Dict[str, Any]],
    interest_areas: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    feeds = list(DEFAULT_GLOBAL_NEWS_FEEDS)

    for source in enabled_sources:
        url = str(source.get("url") or "")
        platform = str(source.get("platform") or "").lower()
        if _looks_like_feed(url) or platform in {"rss", "feed", "google-news"}:
            feeds.append(
                {
                    "feed_id": f"expert_source:{source.get('id') or source.get('name') or url}",
                    "name": source.get("name") or url,
                    "url": url,
                    "category": source.get("category") or "user_source",
                }
            )

    for stock in stocks[:10]:
        name = stock.get("name") or stock.get("ticker")
        if not name:
            continue
        feeds.append(
            {
                "feed_id": f"stock_watch:{stock.get('market', 'KR')}:{stock.get('ticker', '')}",
                "name": f"{name} watch",
                "url": _google_news_url(f"{name} {stock.get('ticker', '')} 주가 실적 공시 전망"),
                "category": "stock_watch",
            }
        )

    for area in interest_areas[:8]:
        terms = " ".join([area.get("name") or "", " ".join(area.get("keywords") or [])]).strip()
        if terms:
            feeds.append(
                {
                    "feed_id": f"interest_area:{area.get('id') or area.get('name')}",
                    "name": f"{area.get('name')} research",
                    "url": _google_news_url(f"{terms} 주식 전망 수혜 기업"),
                    "category": "interest_area",
                }
            )

    deduped = []
    seen_urls = set()
    for feed in feeds:
        url = str(feed.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(feed)

    return deduped


def _fetch_feed_items(feed: Dict[str, str]) -> List[Dict[str, Any]]:
    timeout = httpx.Timeout(3.0, connect=2.0, read=2.0, write=2.0, pool=1.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        response = client.get(feed["url"])
        response.raise_for_status()
        return _parse_rss(response.text, feed)


def _google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"


def _looks_like_feed(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith((".rss", ".xml")) or "rss" in lowered or "feed" in lowered


def _parse_rss(xml_text: str, feed: Dict[str, str]) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    channel_items = root.findall(".//item")
    if not channel_items:
        channel_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    items = []
    for node in channel_items[:12]:
        title = _child_text(node, "title")
        link = _child_text(node, "link")
        if not link:
            link_node = node.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""
        published = _child_text(node, "pubDate") or _child_text(node, "published") or _child_text(node, "updated")
        summary = _child_text(node, "description") or _child_text(node, "summary")
        if not title:
            continue
        items.append(
            {
                "title": html.unescape(_strip_markup(title)).strip(),
                "url": html.unescape(link).strip(),
                "published_at": _normalize_date(published),
                "summary": html.unescape(_strip_markup(summary)).strip()[:500],
                "source": feed["name"],
                "source_key": feed.get("feed_id") or feed["name"],
                "category": feed["category"],
            }
        )
    return items


def _child_text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    if child is not None and child.text:
        return child.text
    namespaced = node.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    if namespaced is not None and namespaced.text:
        return namespaced.text
    return ""


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


def _strip_markup(value: str) -> str:
    output = []
    in_tag = False
    for char in value or "":
        if char == "<":
            in_tag = True
            continue
        if char == ">":
            in_tag = False
            continue
        if not in_tag:
            output.append(char)
    return "".join(output)


def _extract_article_text(html_text: str) -> str:
    source = html_text or ""
    source = re.sub(r"(?is)<script.*?>.*?</script>", " ", source)
    source = re.sub(r"(?is)<style.*?>.*?</style>", " ", source)

    article_match = re.search(r"(?is)<article.*?>(.*?)</article>", source)
    if article_match:
        source = article_match.group(1)
    else:
        body_match = re.search(r"(?is)<body.*?>(.*?)</body>", source)
        if body_match:
            source = body_match.group(1)

    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", source)
    if paragraphs:
        text = "\n\n".join(_normalize_html_text(part) for part in paragraphs)
    else:
        text = _normalize_html_text(source)
    return text.strip()


def _normalize_html_text(value: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", value or "")
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _resolve_google_news_url(client: httpx.Client, url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc != "news.google.com":
        return url

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[-2] != "articles":
        return url

    article_id = parts[-1]
    params = _get_google_decoding_params(client, article_id)
    decoded = _decode_google_article_url(client, params)
    return decoded or url


def _get_google_decoding_params(client: httpx.Client, article_id: str) -> Dict[str, Any]:
    response = client.get(f"https://news.google.com/articles/{article_id}")
    response.raise_for_status()
    text = response.text
    signature_match = re.search(r'data-n-a-sg="([^"]+)"', text)
    timestamp_match = re.search(r'data-n-a-ts="([^"]+)"', text)
    if not signature_match or not timestamp_match:
        raise ValueError("google_news_decode_params_missing")
    return {
        "gn_art_id": article_id,
        "signature": signature_match.group(1),
        "timestamp": timestamp_match.group(1),
    }


def _decode_google_article_url(client: httpx.Client, params: Dict[str, Any]) -> str:
    article_request = [
        "Fbv4je",
        (
            '["garturlreq",[['
            '"X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
            '"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{params["gn_art_id"]}",{params["timestamp"]},"{params["signature"]}"]'
        ),
        None,
        "generic",
    ]
    payload = f"f.req={quote(json.dumps([[article_request]], separators=(',', ':')))}"
    response = client.post(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute",
        headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
        content=payload,
    )
    response.raise_for_status()
    lines = response.text.split("\n\n")
    if len(lines) < 2:
        raise ValueError("google_news_decode_response_missing")
    data = json.loads(lines[1])
    if not data:
        raise ValueError("google_news_decode_response_empty")
    decoded = json.loads(data[0][2])[1]
    if not isinstance(decoded, str) or not decoded.startswith("http"):
        raise ValueError("google_news_decode_invalid_url")
    return decoded
