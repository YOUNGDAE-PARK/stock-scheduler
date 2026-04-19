import html
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx


DEFAULT_GLOBAL_NEWS_FEEDS = [
    {
        "name": "Global markets",
        "url": "https://news.google.com/rss/search?q=global%20markets%20stocks%20rates%20oil%20currency&hl=ko&gl=KR&ceid=KR:ko",
        "category": "macro",
    },
    {
        "name": "Korea market",
        "url": "https://news.google.com/rss/search?q=%ED%95%9C%EA%B5%AD%20%EC%A6%9D%EC%8B%9C%20%ED%99%98%EC%9C%A8%20%EA%B8%88%EB%A6%AC%20%EB%B0%98%EB%8F%84%EC%B2%B4&hl=ko&gl=KR&ceid=KR:ko",
        "category": "korea_market",
    },
    {
        "name": "US macro",
        "url": "https://news.google.com/rss/search?q=Federal%20Reserve%20inflation%20Treasury%20yield%20Nasdaq&hl=ko&gl=KR&ceid=KR:ko",
        "category": "us_macro",
    },
    {
        "name": "Semiconductor supply chain",
        "url": "https://news.google.com/rss/search?q=semiconductor%20AI%20HBM%20Nvidia%20Samsung%20SK%20Hynix&hl=ko&gl=KR&ceid=KR:ko",
        "category": "sector",
    },
]


def collect_global_news(
    enabled_sources: List[Dict[str, Any]],
    stocks: List[Dict[str, Any]],
    interest_areas: List[Dict[str, Any]],
    max_items: int = 24,
) -> Dict[str, Any]:
    feeds = _feed_sources(enabled_sources, stocks, interest_areas)[:6]
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
                    "name": f"{area.get('name')} research",
                    "url": _google_news_url(f"{terms} 주식 전망 수혜 기업"),
                    "category": "interest_area",
                }
            )

    return feeds


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
