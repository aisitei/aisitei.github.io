"""
IT之家 기사 크롤러
- 메인 페이지에서 카메라/모바일폰 관련 기사를 수집
- 기사 본문 텍스트 및 이미지 URL 추출
- 이미지 로컬 다운로드 지원
"""
import os
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class Article:
    """수집된 기사 데이터"""
    article_id: str
    title: str
    url: str
    category: str = ""  # "phone_camera", "phone_product", "ai"
    timestamp: Optional[datetime] = None
    content_paragraphs: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    author: str = ""
    brand: str = ""
    brand_color: str = ""
    local_image_paths: list[str] = field(default_factory=list)  # relative paths like "images/img1.jpg"


def clean_title(title: str) -> str:
    """제목 끝의 'IT之家' 및 변형을 제거합니다.

    예: "OPPO Find X9 发布 - IT之家" → "OPPO Find X9 发布"
    """
    return re.sub(r'[\s\-_|–—]+IT之家\s*$', '', title).strip()


def detect_brand(title: str, content: str = "") -> tuple[str, str]:
    """제목과 본문에서 브랜드를 감지하여 (brand_name, brand_color)를 반환합니다."""
    text = (title + " " + content).lower()

    if any(kw in text for kw in ["xiaomi", "小米", "redmi", "红米"]):
        return ("Xiaomi", "#FF6900")
    if any(kw in text for kw in ["samsung", "三星"]):
        return ("Samsung", "#1428A0")
    if any(kw in text for kw in ["apple", "iphone", "苹果"]):
        return ("Apple", "#555555")
    if "oppo" in text:
        return ("OPPO", "#1D6FA4")
    if any(kw in text for kw in ["vivo", "iqoo", "iQOO"]):
        return ("vivo", "#415FFF")
    if any(kw in text for kw in ["huawei", "华为"]):
        return ("Huawei", "#CF0A2C")
    if any(kw in text for kw in ["honor", "荣耀"]):
        return ("Honor", "#0E62FF")
    if any(kw in text for kw in ["oneplus", "一加"]):
        return ("OnePlus", "#F5010C")
    if any(kw in text for kw in ["sony", "索尼"]):
        return ("Sony", "#003087")
    if any(kw in text for kw in ["canon", "佳能"]):
        return ("Canon", "#CC0000")
    if any(kw in text for kw in ["nikon", "尼康"]):
        return ("Nikon", "#FFDA29")
    if any(kw in text for kw in ["dji", "大疆"]):
        return ("DJI", "#2B2B2B")
    if "insta360" in text:
        return ("Insta360", "#FF4800")
    if "gopro" in text:
        return ("GoPro", "#00ADEF")
    if "realme" in text:
        return ("realme", "#FFD600")
    return ("", "")


def download_image(url: str, dest_path: str) -> bool:
    """이미지를 다운로드하여 로컬에 저장합니다."""
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.warning(f"이미지 다운로드 실패: {url} -> {e}")
        return False


def fetch_page(url: str, timeout: int = 15) -> Optional[str]:
    """URL에서 HTML을 가져옵니다."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text
    except requests.RequestException as e:
        logger.error(f"페이지 가져오기 실패: {url} -> {e}")
        return None


def extract_article_id(url: str) -> Optional[str]:
    """URL에서 기사 ID를 추출합니다.
    예: https://www.ithome.com/0/929/534.htm -> 929534
    """
    match = re.search(r"/(\d+)/(\d+)\.htm", url)
    if match:
        return match.group(1) + match.group(2)
    return None


def get_processed_article_ids(articles_root: str) -> set[str]:
    """articles_root 내 기존 index.html 파일을 스캔하여 이미 처리된 기사 ID 집합을 반환합니다.
    <a class="btn-original" href="..."> 패턴에서 IT之家 기사 ID를 추출합니다.
    """
    processed_ids: set[str] = set()
    if not os.path.isdir(articles_root):
        return processed_ids

    pattern = re.compile(r'<a[^>]+class="btn-original"[^>]+href="([^"]+)"')
    for root, _dirs, files in os.walk(articles_root):
        if "index.html" in files:
            filepath = os.path.join(root, "index.html")
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                for href in pattern.findall(content):
                    article_id = extract_article_id(href)
                    if article_id:
                        processed_ids.add(article_id)
            except Exception as e:
                logger.warning(f"기존 기사 ID 스캔 실패: {filepath} -> {e}")

    logger.info(f"기존 처리된 기사 {len(processed_ids)}건 감지")
    return processed_ids


def _matches_any_kw(title_lower: str, keywords: list[str]) -> bool:
    """제목에 주어진 키워드 중 하나라도 포함되는지 판정합니다.

    - 짧은 ASCII 약어(AI, EV, Mac 등, 길이 < 4)는 단어 경계 규칙을 적용합니다.
      → "airfryer"에 대해 "AI"가 오매칭되는 문제를 방지합니다.
      → CJK와 ASCII가 섞인 경우도 안전하게 판정 (예: "AIGC技术"에서 "AIGC" 매칭 O).
    - CJK를 포함한 키워드나 길이 4 이상 ASCII 키워드는 단순 부분 문자열 매칭을 사용합니다.
    """
    for kw in keywords:
        kw_lower = kw.lower()
        has_cjk = any(ord(c) > 127 for c in kw_lower)
        if has_cjk or len(kw_lower) >= 4:
            if kw_lower in title_lower:
                return True
        else:
            # 앞뒤가 ASCII 영문자/숫자가 아닐 때만 매칭 → 부분 문자열 오매칭 차단
            pattern = r'(?<![a-z0-9])' + re.escape(kw_lower) + r'(?![a-z0-9])'
            if re.search(pattern, title_lower):
                return True
    return False


def classify_article(title: str) -> Optional[str]:
    """기사 제목을 분류하여 카테고리를 반환합니다.

    수집 대상:
        "phone_camera"   - 카메라·액션캠·이미징 관련 기사
        "phone_product"  - 스마트폰 신제품 (手机/phone/smartphone 명시 필수)
        "image_sensor"   - 이미지센서·반도체
        "ai"             - 카메라·이미징·스마트폰 맥락 AI 기사
        None             - 수집 제외
    """
    title_lower = title.lower()

    # ── 1) 하드 제외 먼저 (카메라 키워드 유무와 무관) ──
    # 카메라 모듈이 장착된 펫 피더·스마트 도어락·가전 등이 카메라 필터를 우회하지
    # 않도록 제외 규칙을 최우선 적용합니다.
    if _matches_any_kw(title_lower, config.KEYWORDS_EXCLUDE):
        return None

    # ── 2) 카메라 / 액션캠 / 이미징 ──
    if _matches_any_kw(title_lower, config.KEYWORDS_CAMERA):
        return "phone_camera"

    # ── 3) 이미지센서 / 반도체 ──
    if _matches_any_kw(title_lower, config.KEYWORDS_IMAGE_SENSOR):
        return "image_sensor"

    # ── 4) 스마트폰 — 명시적 '手机/phone/smartphone' 단어 필수 ──
    has_phone_explicit = _matches_any_kw(title_lower, config.KEYWORDS_PHONE_EXPLICIT)
    has_phone_brand = _matches_any_kw(title_lower, config.KEYWORDS_PHONE_BRAND)
    has_product_kw = _matches_any_kw(title_lower, config.KEYWORDS_PHONE_PRODUCT)
    if has_phone_explicit and (has_phone_brand or has_product_kw):
        return "phone_product"

    # ── 5) AI — 카메라·이미징·스마트폰 맥락 필수 ──
    has_ai_kw = _matches_any_kw(title_lower, config.KEYWORDS_AI)
    has_ai_ctx = _matches_any_kw(title_lower, config.KEYWORDS_AI_CONTEXT)
    if has_ai_kw and has_ai_ctx:
        return "ai"

    return None


def is_camera_related(title: str) -> bool:
    """하위 호환: 기존 코드에서 사용하던 함수"""
    return classify_article(title) is not None


def get_article_date(url: str) -> Optional[str]:
    """기사 URL에서 발행일을 'YYYY-MM-DD' 형식으로 반환합니다. 실패 시 None."""
    ts = _extract_article_timestamp(url)
    if ts:
        return ts.strftime("%Y-%m-%d")
    return None


def _extract_article_timestamp(url: str) -> Optional[datetime]:
    """기사 페이지에서 발행 타임스탬프를 추출합니다. 실패 시 None을 반환합니다."""
    html = fetch_page(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # <time> 태그 시도
    time_tag = soup.find("time")
    if time_tag:
        dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
        if dt_str:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(dt_str[:19], fmt)
                except ValueError:
                    pass

    # 날짜 패턴 fallback: "2025-01-15 12:34" 등
    date_pattern = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2})", html)
    if date_pattern:
        raw = date_pattern.group(1).replace("/", "-").replace("T", " ")
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            pass

    return None


def scrape_article_list() -> list[dict]:
    """IT之家 메인 페이지에서 최근 기사 목록을 가져옵니다. 24시간 이내 기사만 포함합니다."""
    html = fetch_page(config.ITHOME_BASE_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    articles = []
    cutoff = datetime.now() - timedelta(hours=24)

    # 메인 페이지의 기사 링크 추출
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        title = link.get_text(strip=True)

        # IT之家 기사 URL 패턴 매칭
        if not re.match(r"https?://www\.ithome\.com/\d+/\d+/\d+\.htm", href):
            continue
        if not title or len(title) < 10:
            continue

        # 제목에서 "IT之家" 접미어 제거
        title = clean_title(title)

        category = classify_article(title)
        if not category:
            continue

        article_id = extract_article_id(href)
        if not article_id or any(a["article_id"] == article_id for a in articles):
            continue

        # 24시간 recency 체크 (타임스탬프를 찾지 못하면 보수적으로 포함)
        ts = _extract_article_timestamp(href)
        if ts is not None and ts < cutoff:
            logger.info(f"24h 초과로 건너뜀 ({ts:%Y-%m-%d %H:%M}): {title[:40]}")
            continue

        tag = {
            "phone_camera": "[camera]",
            "phone_product": "[phone]",
            "image_sensor": "[sensor]",
            "ai": "[ai]",
        }.get(category, "[other]")
        articles.append({
            "article_id": article_id,
            "title": title,
            "url": href,
            "category": category,
        })
        logger.info(f"{tag} [{category}] 기사 발견: {title}")

    logger.info(f"총 {len(articles)}건의 관련 기사 발견")
    return articles


def scrape_article_content(url: str) -> tuple[list[str], str]:
    """기사 본문 텍스트를 추출합니다."""
    html = fetch_page(url)
    if not html:
        return [], ""

    soup = BeautifulSoup(html, "html.parser")

    # 본문 영역 찾기
    content_div = soup.find("div", class_="post_content") or soup.find("div", id="paragraph")
    if not content_div:
        logger.warning(f"본문 영역을 찾을 수 없습니다: {url}")
        return [], ""

    paragraphs = []
    for p in content_div.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 5:
            paragraphs.append(text)

    # 작성자 추출
    author = ""
    author_tag = soup.find("span", class_="author_ba498")
    if author_tag:
        author = author_tag.get_text(strip=True)

    return paragraphs, author


def _normalize_img_url(url: str) -> str:
    """프로토콜 없는 URL을 https로 정규화합니다."""
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith("http"):
        return "https://" + url
    return url


def _add_unique(image_urls: list[str], url: str, seen: set[str]) -> None:
    """중복 없이 이미지 URL을 추가합니다 (쿼리스트링 제거 후 비교)."""
    url = _normalize_img_url(url)
    # placeholder 제외
    if "images/v2/t.png" in url or "ithome.png" in url or ".svg" in url:
        return
    key = url.split("?")[0]
    if key not in seen:
        seen.add(key)
        image_urls.append(url)


_BODY_SELECTORS = [
    # 데스크톱 IT之家
    ("div", {"class_": "post_content"}),
    ("div", {"id": "paragraph"}),
    # 모바일 IT之家 / 일반 폴백
    ("div", {"class_": "news-content"}),
    ("div", {"class_": "content"}),
    ("article", {}),
]


def _find_article_body(soup: BeautifulSoup):
    """IT之家 기사 본문 컨테이너를 찾습니다. 사이드바·관련 기사·로고 반복을 차단하기 위함."""
    for tag, attrs in _BODY_SELECTORS:
        node = soup.find(tag, **attrs) if attrs else soup.find(tag)
        if node:
            return node
    return None


def _collect_body_images(body) -> list[str]:
    """기사 본문 컨테이너 내에서만 이미지 URL을 수집합니다.
    regex는 본문 HTML 문자열에 한정해 돌리고, BS4로 lazy-load 속성도 수집합니다.
    """
    if not body:
        return []

    found: list[str] = []
    body_html = str(body)

    # 1) regex: data-original/data-src 등 속성 및 인라인 JSON까지 포괄
    for url in re.findall(
        r'(?:https?:)?//img\.ithome\.com/newsuploadfiles/[^"\'>\s\\]+',
        body_html,
    ):
        found.append(url)

    # 2) BS4: 추가적인 img 속성 보완
    for img in body.find_all("img"):
        for attr in ("src", "data-original", "data-src", "data-lazy-src",
                     "data-lazy", "data-echo"):
            src = img.get(attr, "")
            if src and "newsuploadfiles" in src:
                found.append(src)
    return found


def scrape_article_images(article_id: str) -> list[str]:
    """IT之家 기사 이미지를 수집합니다. **본문 컨테이너 내부만 스캔**하므로
    사이드바·관련 기사·출처 로고 반복(예: Counterpoint 로고 중복)이 포함되지 않습니다.

    우선순위: 데스크톱 페이지 본문 → 모바일 페이지 본문(보완).
    """
    image_urls: list[str] = []
    seen: set[str] = set()

    # ── 데스크톱 본문 ────────────────────────────────────────
    desktop_url = f"https://www.ithome.com/0/{article_id[:-3]}/{article_id[-3:]}.htm"
    desktop_html = fetch_page(desktop_url)
    if desktop_html:
        desktop_body = _find_article_body(BeautifulSoup(desktop_html, "html.parser"))
        for url in _collect_body_images(desktop_body):
            _add_unique(image_urls, url, seen)

    # ── 모바일 본문 (보완) ───────────────────────────────────
    mobile_url = config.ITHOME_MOBILE_URL.format(article_id=article_id)
    mobile_html = fetch_page(mobile_url)
    if mobile_html:
        mobile_body = _find_article_body(BeautifulSoup(mobile_html, "html.parser"))
        for url in _collect_body_images(mobile_body):
            _add_unique(image_urls, url, seen)

    logger.info(f"기사 {article_id}: 본문 이미지 {len(image_urls)}장")
    return image_urls


def collect_articles() -> list[Article]:
    """전체 파이프라인: 기사 목록 → 본문 + 이미지 수집 (중복 기사 건너뜀)"""
    article_list = scrape_article_list()

    # 이미 처리된 기사 ID 로드
    articles_root = os.path.abspath(config.OUTPUT_DIR)
    processed_ids = get_processed_article_ids(articles_root)
    before = len(article_list)
    article_list = [a for a in article_list if a["article_id"] not in processed_ids]
    skipped = before - len(article_list)
    if skipped:
        logger.info(f"중복 {skipped}건 건너뜀 (이미 처리됨)")

    results = []
    for item in article_list:
        logger.info(f"기사 수집 중: {item['title'][:40]}...")

        paragraphs, author = scrape_article_content(item["url"])
        images = scrape_article_images(item["article_id"])

        # 브랜드 감지
        content_sample = " ".join(paragraphs[:3])
        brand, brand_color = detect_brand(item["title"], content_sample)

        article = Article(
            article_id=item["article_id"],
            title=item["title"],
            url=item["url"],
            category=item.get("category", ""),
            content_paragraphs=paragraphs,
            image_urls=images,
            author=author,
            brand=brand,
            brand_color=brand_color,
        )
        results.append(article)
        logger.info(f"  → 본문 {len(paragraphs)}단락, 이미지 {len(images)}장" + (f", 브랜드: {brand}" if brand else ""))

    return results
