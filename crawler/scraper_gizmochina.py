"""
Gizmochina RSS 크롤러
- https://www.gizmochina.com/feed/ 에서 최신 기사 수집
- content:encoded HTML에서 본문·이미지 추출 (Cloudflare 우회)
- 영어 제목 기반 키워드 필터링
"""
import re
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

import config
from scraper import Article, detect_brand, _matches_any_kw, HEADERS, get_processed_article_ids

logger = logging.getLogger(__name__)

SOURCE = "gizmochina"

# RSS 네임스페이스
_NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "atom":    "http://www.w3.org/2005/Atom",
}


# ── 기사 ID / 중복 체크 ──────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """후행 슬래시 제거 → 중복 체크용 정규화 키"""
    return url.rstrip("/")


# ── 이미지 추출 ───────────────────────────────────────────────────────────────

def _largest_from_srcset(srcset: str) -> Optional[str]:
    """srcset 문자열에서 가장 큰 너비의 URL 반환"""
    candidates: list[tuple[int, str]] = []
    for part in srcset.split(","):
        tokens = part.strip().split()
        if len(tokens) >= 2:
            url = tokens[0]
            width_str = tokens[1].rstrip("w")
            try:
                candidates.append((int(width_str), url))
            except ValueError:
                pass
    if candidates:
        return max(candidates, key=lambda x: x[0])[1]
    return None


def _strip_qs(url: str) -> str:
    """쿼리스트링 제거 (WordPress 캐시 파라미터 등)"""
    return url.split("?")[0]


def _extract_images(html: str) -> list[str]:
    """content:encoded HTML에서 wp-content/uploads 이미지 URL 수집 (최대 해상도)"""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    images: list[str] = []

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "wp-content/uploads" not in src:
            continue

        srcset = img.get("srcset", "")
        best = _largest_from_srcset(srcset) if srcset else None
        url = _strip_qs(best or src)

        if url not in seen:
            seen.add(url)
            images.append(url)

    return images


# ── 본문 추출 ─────────────────────────────────────────────────────────────────

_BOILERPLATE_RE = re.compile(
    r"appeared first on|gizmochina\.com|via gizmochina|source:|follow us on",
    re.IGNORECASE,
)


def _extract_paragraphs(html: str) -> list[str]:
    """content:encoded HTML에서 본문 단락 추출"""
    soup = BeautifulSoup(html, "html.parser")
    paragraphs: list[str] = []

    for tag in soup.find_all(["p", "h2", "h3", "li"]):
        text = tag.get_text(strip=True)
        if len(text) < 15:
            continue
        if _BOILERPLATE_RE.search(text):
            continue
        paragraphs.append(text)

    return paragraphs


# ── 키워드 필터링 ─────────────────────────────────────────────────────────────

def _classify_en(title: str) -> Optional[str]:
    """영어 기사 제목을 분류. 수집 대상이면 카테고리 문자열, 아니면 None."""
    t = title.lower()

    # 1) 제외 먼저
    if _matches_any_kw(t, config.KEYWORDS_EXCLUDE_EN):
        return None

    # 2) 카메라 / 이미징
    if _matches_any_kw(t, config.KEYWORDS_CAMERA_EN):
        return "phone_camera"

    # 3) 이미지 센서 / 반도체
    if _matches_any_kw(t, config.KEYWORDS_IMAGE_SENSOR_EN):
        return "image_sensor"

    # 4) 스마트폰 — 명시적 phone/smartphone 단어 + 브랜드 or 출시 키워드
    has_phone   = _matches_any_kw(t, config.KEYWORDS_PHONE_EXPLICIT_EN)
    has_brand   = _matches_any_kw(t, config.KEYWORDS_PHONE_BRAND)
    has_product = _matches_any_kw(t, config.KEYWORDS_PHONE_PRODUCT_EN)
    if has_phone and (has_brand or has_product):
        return "phone_product"

    # 5) AI — 카메라·스마트폰 맥락 필수
    has_ai  = _matches_any_kw(t, config.KEYWORDS_AI_EN)
    has_ctx = _matches_any_kw(t, config.KEYWORDS_AI_CONTEXT_EN)
    if has_ai and has_ctx:
        return "ai"

    return None


# ── RSS 수집 메인 ─────────────────────────────────────────────────────────────

def scrape_feed(processed_ids: Optional[set[str]] = None) -> list[Article]:
    """
    Gizmochina RSS 피드에서 최신 기사를 수집하여 Article 리스트 반환.
    processed_ids 를 받으면 중복 건너뜀.
    """
    try:
        resp = requests.get(
            config.GIZMOCHINA_FEED_URL,
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Gizmochina RSS 수집 실패: {e}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.error(f"Gizmochina RSS XML 파싱 실패: {e}")
        return []

    channel = root.find("channel")
    if channel is None:
        logger.error("Gizmochina RSS: <channel> 없음")
        return []

    articles: list[Article] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    for item in channel.findall("item"):
        title_el   = item.find("title")
        link_el    = item.find("link")
        pub_el     = item.find("pubDate")
        content_el = item.find("content:encoded", _NS)

        if title_el is None or link_el is None:
            continue

        title = (title_el.text or "").strip()
        url   = (link_el.text or "").strip()
        if not title or not url:
            continue

        # ── 발행일 24h 필터 ──
        if pub_el is not None and pub_el.text:
            try:
                pub_dt = parsedate_to_datetime(pub_el.text.strip())
                if pub_dt < cutoff:
                    logger.info(f"[gc] 24h 초과 건너뜀: {title[:50]}")
                    continue
            except Exception:
                pass

        # ── 키워드 분류 ──
        category = _classify_en(title)
        if not category:
            continue

        # ── 중복 체크 ──
        article_id = _normalize_url(url)
        if processed_ids and article_id in processed_ids:
            logger.info(f"[gc] 중복 건너뜀: {title[:50]}")
            continue

        # ── 본문·이미지 추출 (RSS content:encoded) ──
        content_html = (content_el.text or "") if content_el is not None else ""
        paragraphs = _extract_paragraphs(content_html)
        image_urls = _extract_images(content_html)

        # ── 브랜드 감지 ──
        content_sample = " ".join(paragraphs[:3])
        brand, brand_color = detect_brand(title, content_sample)

        article = Article(
            article_id=article_id,
            title=title,
            url=url,
            category=category,
            content_paragraphs=paragraphs,
            image_urls=image_urls,
            author="",
            brand=brand,
            brand_color=brand_color,
            source=SOURCE,
        )
        articles.append(article)

        tag = {
            "phone_camera": "[camera]",
            "phone_product": "[phone]",
            "image_sensor": "[sensor]",
            "ai": "[ai]",
        }.get(category, "[other]")
        logger.info(f"[gc]{tag} {title[:70]}")

    logger.info(f"[Gizmochina] 총 {len(articles)}건 수집")
    return articles
