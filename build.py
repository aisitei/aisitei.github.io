#!/usr/bin/env python3
"""
build.py — Generates index.html and reports.html for aisitei.github.io.

Scans articles/ recursively for index.html files, extracts metadata,
and builds paginated blog index pages with dark theme, sidebar, and
live search/filter functionality.
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser


# ── Root of the project (where build.py lives) ──────────────────────────────
ROOT = Path(__file__).parent


# ── Metadata extractor ───────────────────────────────────────────────────────

class ArticleMetaParser(HTMLParser):
    """Parses an article HTML file and extracts metadata."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.category = ""
        self.brand = ""
        self.brand_color = ""
        self.thumbnail = ""
        self._in_title = False
        self._in_h1 = False
        self._first_img_found = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "title":
            self._in_title = True

        elif tag == "meta":
            name = attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            if name == "article-category":
                self.category = content
            elif name == "article-brand":
                self.brand = content
            elif name == "article-brand-color":
                self.brand_color = content

        elif tag == "img" and not self._first_img_found:
            src = attrs_dict.get("src", "")
            if src and not src.startswith("data:"):
                self.thumbnail = src
                self._first_img_found = True

        elif tag == "h1":
            classes = attrs_dict.get("class", "")
            if "hero-title" in classes or "article-title" in classes:
                self._in_h1 = True

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        elif self._in_h1 and not self.title:
            self.title = data.strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False


def extract_metadata(html_path: Path, article_root: Path):
    """
    Extract metadata from an article HTML file.
    Returns a dict or None if the file can't be parsed.
    """
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    parser = ArticleMetaParser()
    try:
        parser.feed(text)
    except Exception:
        pass  # best-effort parse

    # Date from path: articles/YYYY-MM/YYYY-MM-DD/slug/index.html
    parts = html_path.parts
    date_str = ""
    month_str = ""
    for part in parts:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", part):
            date_str = part
            month_str = part[:7]
            break
    if not month_str:
        for part in parts:
            if re.match(r"^\d{4}-\d{2}$", part):
                month_str = part
                break

    # Category fallback from slug
    category = parser.category
    if not category:
        slug = html_path.parent.name.lower()
        if any(k in slug for k in ("iphone", "galaxy", "phone", "smartphone", "pixel", "折叠", "手机")):
            category = "phone"
        elif any(k in slug for k in ("camera", "lens", "leica", "fuji", "sony", "nikon", "canon", "镜头", "相机")):
            category = "camera"
        elif any(k in slug for k in ("ai", "gpt", "llm", "gemini", "claude", "openai", "chatgpt")):
            category = "ai"
        else:
            category = "general"

    # Thumbnail: make path relative to article root for use in index pages
    thumbnail = parser.thumbnail
    if thumbnail:
        # Resolve to absolute, then make relative to site root
        if not thumbnail.startswith("http"):
            abs_thumb = (html_path.parent / thumbnail).resolve()
            try:
                thumbnail = str(abs_thumb.relative_to(article_root))
            except ValueError:
                thumbnail = ""

    # Relative URL from site root
    try:
        relative_url = str(html_path.relative_to(article_root))
    except ValueError:
        relative_url = str(html_path)

    title = parser.title or html_path.parent.name.replace("-", " ").title()
    # Strip browser-tab prefix added to <title> tags (should not appear in card titles)
    if title.startswith("AI시테이 - "):
        title = title[len("AI시테이 - "):]

    return {
        "title": title,
        "url": relative_url,
        "date": date_str,
        "month": month_str,
        "category": category,
        "brand": parser.brand,
        "brand_color": parser.brand_color,
        "thumbnail": thumbnail,
    }


# ── Article scanning ─────────────────────────────────────────────────────────

def scan_articles(root: Path) -> list[dict]:
    """Recursively find all article index.html files and extract metadata."""
    articles_dir = root / "articles"
    if not articles_dir.exists():
        return []

    articles = []
    for html_path in sorted(articles_dir.rglob("index.html"), reverse=True):
        meta = extract_metadata(html_path, root)
        if meta:
            articles.append(meta)

    # Sort newest first
    articles.sort(key=lambda a: a["date"] or a["month"] or "0000", reverse=True)
    return articles


# ── HTML generation helpers ──────────────────────────────────────────────────

CATEGORY_LABELS = {
    "phone": "스마트폰",
    "camera": "카메라",
    "ai": "AI",
    "general": "일반",
    "": "일반",
}

CATEGORY_COLORS = {
    "phone": "#dc2626",
    "camera": "#2563eb",
    "ai": "#059669",
    "general": "#475569",
    "": "#475569",
}

# 스마트폰 제조사 목록 — 브랜드가 이 목록에 있으면 "스마트폰" 배지 자동 추가
SMARTPHONE_BRANDS = {
    "xiaomi", "samsung", "apple", "oppo", "vivo", "huawei", "honor",
    "oneplus", "realme", "google", "motorola", "nothing", "meizu",
    "zte", "nubia", "iqoo", "poco", "redmi", "lenovo", "asus",
    "blackshark", "infinix", "tecno", "sony",
}


def category_badge_html(category: str) -> str:
    label = CATEGORY_LABELS.get(category, category.upper() if category else "일반")
    color = CATEGORY_COLORS.get(category, "#475569")
    return (
        f'<span class="badge badge-category" '
        f'style="background:{color};">{label}</span>'
    )


def brand_badge_html(brand: str, brand_color: str) -> str:
    if not brand:
        return ""
    color = brand_color if brand_color else "#3b82f6"
    return (
        f'<span class="badge badge-brand" '
        f'style="background:{color};">{brand}</span>'
    )


def article_badges_html(article: dict) -> str:
    """브랜드 배지 + 카테고리 배지를 생성합니다.
    - 스마트폰 제조사 브랜드 → 항상 "스마트폰" 배지
    - 카메라 카테고리 → "카메라" 배지 추가
    - AI 카테고리 → "AI" 배지
    """
    brand = article.get("brand", "")
    brand_color = article.get("brand_color", "")
    category = article.get("category", "")

    parts = []

    # 1) 브랜드 배지 (브랜드명 색상 pill)
    if brand:
        parts.append(brand_badge_html(brand, brand_color))

    # 2) 스마트폰 제조사이면 "스마트폰" 배지 (AI 전용 기사 제외)
    if brand.lower() in SMARTPHONE_BRANDS and category != "ai":
        parts.append(category_badge_html("phone"))

    # 3) 카메라 카테고리이면 "카메라" 배지
    if category == "camera":
        parts.append(category_badge_html("camera"))

    # 4) AI 카테고리이면 항상 "AI" 배지
    if category == "ai":
        parts.append(category_badge_html("ai"))

    return "\n".join(parts)


# 원문에 이미지가 없거나 썸네일을 찾지 못한 경우 — 파비콘 이미지를 대체로 사용.
FALLBACK_THUMB = "assets/images/apple-touch-icon.png"


def thumbnail_html(thumbnail: str, title: str) -> str:
    fallback = FALLBACK_THUMB.replace('"', "&quot;")
    # 원문 이미지가 없어 기사에 파비콘을 hero로 박아둔 경우, 메타 파서가 파비콘을
    # 썸네일로 집어온다. 이 경우에도 "fallback" 클래스를 붙여 잘림/늘어짐 없이
    # contain + padding 스타일로 렌더링한다.
    is_fallback_src = thumbnail and thumbnail.rstrip("/").endswith("apple-touch-icon.png")
    if thumbnail and not is_fallback_src:
        src = thumbnail.replace('"', "&quot;")
        return (
            f'<div class="card-thumb">'
            f'<img src="{src}" alt="" loading="lazy" onerror="this.src=\'{fallback}\';this.classList.add(\'fallback\')">'
            f'</div>'
        )
    return (
        f'<div class="card-thumb">'
        f'<img src="{fallback}" alt="no image" loading="lazy" class="fallback">'
        f'</div>'
    )


def article_card_html(article: dict) -> str:
    raw_title = article["title"]
    card_title = (raw_title[:42] + "…") if len(raw_title) > 43 else raw_title
    title = card_title.replace("<", "&lt;").replace(">", "&gt;")
    url = article["url"].replace('"', "&quot;")
    date_display = article["date"] or article["month"] or ""
    category = article.get("category", "")
    month = article.get("month", "")

    search_title = raw_title.replace("<", "&lt;").replace(">", "&gt;")
    return f'''    <article class="article-card"
             data-title="{search_title.lower()}"
             data-category="{category}"
             data-month="{month}"
             data-date="{article['date']}">
      <a href="{url}" class="card-link">
        {thumbnail_html(article["thumbnail"], title)}
        <div class="card-body">
          <div class="card-badges">
            {article_badges_html(article)}
          </div>
          <h2 class="card-title">{title}</h2>
          <div class="card-date">{date_display}</div>
        </div>
      </a>
    </article>'''


def archive_months(articles: list[dict]) -> list[tuple[str, int]]:
    """Return (month, count) pairs sorted newest first."""
    counts: dict[str, int] = {}
    for a in articles:
        m = a.get("month", "")
        if m:
            counts[m] = counts.get(m, 0) + 1
    return sorted(counts.items(), reverse=True)


# ── Page template ─────────────────────────────────────────────────────────────

def build_page(
    articles: list[dict],
    page_title: str,
    active_nav: str,  # "index" or "smartphone"
) -> str:
    cards_html = "\n".join(article_card_html(a) for a in articles)
    months = archive_months(articles)

    # Archive list items
    archive_items = ""
    for month, count in months:
        archive_items += (
            f'      <li>'
            f'<button class="archive-btn" data-month="{month}">'
            f'{month} <span class="archive-count">({count})</span>'
            f'</button>'
            f'</li>\n'
        )

    index_active = ' class="nav-active"' if active_nav == "index" else ""
    phone_active = ' class="nav-active"' if active_nav == "smartphone" else ""

    total_count = len(articles)

    return f'''<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI시테이 블로그 | IT뉴스 &amp; 테크리뷰</title>
  <link rel="icon" href="assets/images/favicon.ico" sizes="any">
  <link rel="apple-touch-icon" href="assets/images/apple-touch-icon.png">
  <style>
    :root {{
      --bg: #0f172a;
      --bg-secondary: #1e293b;
      --surface: #1e293b;
      --text: #f1f5f9;
      --text-secondary: #b0bec5;
      --border: #334155;
      --accent: #3b82f6;
      --header-height: 56px;
    }}

    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    html, body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
      font-size: 16px;
      min-height: 100vh;
    }}

    a {{
      color: inherit;
      text-decoration: none;
    }}

    /* ── Header ── */
    .site-header {{
      position: sticky;
      top: 0;
      z-index: 100;
      height: var(--header-height);
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      padding: 0 20px;
      gap: 16px;
    }}

    .header-logo {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 18px;
      font-weight: 800;
      color: var(--text);
      letter-spacing: -0.5px;
      flex-shrink: 0;
      text-decoration: none;
    }}

    .header-logo:hover {{ color: var(--accent); text-decoration: none; }}

    .logo-icon {{
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      flex-shrink: 0;
    }}

    .logo-text {{ font-size: 17px; font-weight: 800; }}
    .logo-accent {{ color: var(--accent); }}

    .header-nav {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}

    .header-nav a {{
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 14px;
      color: var(--text-secondary);
      transition: background 0.15s, color 0.15s;
    }}

    .header-nav a:hover,
    .header-nav a.nav-active {{
      background: var(--surface);
      color: var(--text);
    }}

    .header-nav a.nav-active {{
      color: var(--accent);
      font-weight: 600;
    }}

    .header-right {{
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .visitor-counter {{
      font-size: 12px;
      color: var(--text-secondary);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 4px 10px;
      white-space: nowrap;
    }}

    /* ── Page layout ── */
    .page-layout {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px 20px 80px;
      display: grid;
      grid-template-columns: 1fr 280px;
      gap: 24px;
      align-items: start;
    }}

    /* ── Article grid ── */
    .articles-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
    }}

    @media (max-width: 1200px) {{
      .articles-grid {{ grid-template-columns: repeat(3, 1fr); }}
    }}

    @media (max-width: 860px) {{
      .articles-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}

    @media (max-width: 560px) {{
      .articles-grid {{ grid-template-columns: 1fr; }}
    }}

    .articles-header {{
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .articles-count {{
      font-size: 13px;
      color: var(--text-secondary);
    }}

    .no-results {{
      display: none;
      grid-column: 1 / -1;
      text-align: center;
      padding: 64px 0;
      color: var(--text-secondary);
    }}

    .no-results.visible {{ display: block; }}

    /* ── Article card ── */
    .article-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      transition: border-color 0.15s, transform 0.15s;
    }}

    .article-card:hover {{
      border-color: var(--accent);
      transform: translateY(-2px);
    }}

    .article-card.hidden {{
      display: none;
    }}

    .card-link {{
      display: flex;
      flex-direction: column;
      height: 100%;
    }}

    .card-thumb {{
      aspect-ratio: 16/10;
      overflow: hidden;
      background: #1e293b;
    }}

    .card-thumb img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      transition: transform 0.3s;
    }}

    .article-card:hover .card-thumb img {{
      transform: scale(1.04);
    }}

    .card-thumb-empty {{
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    }}

    .card-thumb img.fallback {{
      object-fit: contain;
      padding: 12px;
      background: #f8fafc;
    }}

    .card-body {{
      padding: 10px 12px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex: 1;
    }}

    .card-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 2px 6px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.2px;
      color: #fff;
    }}

    .card-title {{
      font-size: 13px;
      font-weight: 600;
      line-height: 1.4;
      color: var(--text);
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .card-date {{
      font-size: 11px;
      color: var(--text-secondary);
      margin-top: auto;
    }}

    /* ── Sidebar ── */
    .sidebar {{
      position: sticky;
      top: calc(var(--header-height) + 16px);
      max-height: calc(100vh - var(--header-height) - 32px);
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}

    .sidebar::-webkit-scrollbar {{
      width: 4px;
    }}

    .sidebar::-webkit-scrollbar-track {{
      background: transparent;
    }}

    .sidebar::-webkit-scrollbar-thumb {{
      background: var(--border);
      border-radius: 2px;
    }}

    .sidebar-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
    }}

    .sidebar-title {{
      font-size: 12px;
      font-weight: 700;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-bottom: 12px;
    }}

    /* Search */
    .search-input {{
      width: 100%;
      padding: 8px 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      font-size: 14px;
      outline: none;
      transition: border-color 0.15s;
    }}

    .search-input::placeholder {{
      color: var(--text-secondary);
    }}

    .search-input:focus {{
      border-color: var(--accent);
    }}

    /* Category filter */
    .category-btns {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}

    .cat-btn {{
      padding: 5px 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-secondary);
      font-size: 13px;
      cursor: pointer;
      transition: background 0.15s, color 0.15s, border-color 0.15s;
    }}

    .cat-btn:hover {{
      background: var(--bg);
      color: var(--text);
    }}

    .cat-btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}

    /* Archive */
    .archive-list {{
      list-style: none;
      max-height: 320px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}

    .archive-list::-webkit-scrollbar {{
      width: 3px;
    }}

    .archive-list::-webkit-scrollbar-thumb {{
      background: var(--border);
      border-radius: 2px;
    }}

    .archive-btn {{
      width: 100%;
      text-align: left;
      padding: 6px 8px;
      background: transparent;
      border: none;
      border-radius: 6px;
      color: var(--text-secondary);
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      transition: background 0.15s, color 0.15s;
    }}

    .archive-btn:hover {{
      background: var(--bg);
      color: var(--text);
    }}

    .archive-btn.active {{
      background: var(--accent);
      color: #fff;
    }}

    .archive-count {{
      font-size: 11px;
      opacity: 0.7;
    }}

    /* ── Responsive ── */
    @media (max-width: 900px) {{
      .page-layout {{
        grid-template-columns: 1fr;
      }}

      .sidebar {{
        position: static;
        max-height: none;
        overflow-y: visible;
      }}
    }}

    @media (max-width: 600px) {{
      .site-header {{
        padding: 0 12px;
        gap: 10px;
      }}

      .visitor-counter {{
        font-size: 11px;
        padding: 3px 8px;
      }}

      .page-layout {{
        padding: 16px 12px 60px;
        gap: 20px;
      }}

    }}
  </style>
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-0036958863764472" crossorigin="anonymous"></script>
</head>
<body>

  <header class="site-header">
    <a class="header-logo" href="index.html">
      <span class="logo-icon">📡</span>
      <span class="logo-text">AI<span class="logo-accent">시테이</span> 블로그</span>
    </a>
    <nav class="header-nav">
      <a href="index.html"{index_active}>IT뉴스</a>
      <a href="reports.html"{phone_active}>발표회 정리</a>
    </nav>
    <div class="header-right">
      <div class="visitor-counter" id="visitor-counter">오늘: — / 누적: —</div>
    </div>
  </header>

  <div class="page-layout">

    <!-- ── Main articles ── -->
    <main>
      <div class="articles-header">
        <span class="articles-count" id="articles-count">총 {total_count}개 기사</span>
      </div>
      <div class="articles-grid" id="articles-grid">
{cards_html}
        <div class="no-results" id="no-results">검색 결과가 없습니다.</div>
      </div>
    </main>

    <!-- ── Sidebar ── -->
    <aside class="sidebar">

      <!-- AdSense -->
      <div class="sidebar-card adsense-card">
        <div class="sidebar-title">광고</div>
        <div class="adsense-slot">
          <!-- Google AdSense 코드를 아래에 삽입하세요 -->
          <!--
          <ins class="adsbygoogle"
               style="display:block"
               data-ad-client="ca-pub-XXXXXXXXXXXXXXXX"
               data-ad-slot="XXXXXXXXXX"
               data-ad-format="auto"
               data-full-width-responsive="true"></ins>
          <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
          -->
        </div>
      </div>

      <!-- Search -->
      <div class="sidebar-card">
        <div class="sidebar-title">🔍 검색</div>
        <input
          type="search"
          class="search-input"
          id="search-input"
          placeholder="기사 검색..."
          autocomplete="off"
        >
      </div>

      <!-- Category filter -->
      <div class="sidebar-card">
        <div class="sidebar-title">📂 카테고리</div>
        <div class="category-btns">
          <button class="cat-btn active" data-cat="">전체</button>
          <button class="cat-btn" data-cat="camera">📷 카메라</button>
          <button class="cat-btn" data-cat="phone">📱 스마트폰</button>
          <button class="cat-btn" data-cat="ai">🤖 AI</button>
        </div>
      </div>

      <!-- Archive -->
      <div class="sidebar-card">
        <div class="sidebar-title">📅 아카이브</div>
        <ul class="archive-list">
{archive_items}        </ul>
      </div>

    </aside>
  </div>

  <script>
    // ── Visitor counter ──────────────────────────────────────────────────────
    (function () {{
      const todayKey = 'visitCount_today_' + new Date().toISOString().slice(0, 10);
      const totalKey = 'visitCount_total';

      let todayCount = parseInt(localStorage.getItem(todayKey) || '0', 10) + 1;
      let totalCount = parseInt(localStorage.getItem(totalKey) || '0', 10) + 1;

      localStorage.setItem(todayKey, todayCount);
      localStorage.setItem(totalKey, totalCount);

      document.getElementById('visitor-counter').textContent =
        '오늘: ' + todayCount.toLocaleString() + ' / 누적: ' + totalCount.toLocaleString();
    }})();

    // ── Filtering logic ──────────────────────────────────────────────────────
    const grid = document.getElementById('articles-grid');
    const cards = Array.from(document.querySelectorAll('.article-card'));
    const countEl = document.getElementById('articles-count');
    const noResults = document.getElementById('no-results');

    let activeCategory = '';
    let activeMonth = '';
    let searchQuery = '';

    function filterArticles() {{
      let visible = 0;

      cards.forEach(function (card) {{
        const title = card.dataset.title || '';
        const cat = card.dataset.category || '';
        const month = card.dataset.month || '';

        const matchSearch = !searchQuery || title.includes(searchQuery);
        const matchCat = !activeCategory || cat === activeCategory;
        const matchMonth = !activeMonth || month === activeMonth;

        if (matchSearch && matchCat && matchMonth) {{
          card.classList.remove('hidden');
          visible++;
        }} else {{
          card.classList.add('hidden');
        }}
      }});

      countEl.textContent = '총 ' + visible + '개 기사';
      noResults.classList.toggle('visible', visible === 0);
    }}

    // Search (실시간 필터 — 엔터 불필요)
    document.getElementById('search-input').addEventListener('input', function (e) {{
      searchQuery = e.target.value.trim().toLowerCase();
      filterArticles();
    }});

    // Category buttons
    document.querySelectorAll('.cat-btn').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        document.querySelectorAll('.cat-btn').forEach(function (b) {{ b.classList.remove('active'); }});
        btn.classList.add('active');
        activeCategory = btn.dataset.cat;
        filterArticles();
      }});
    }});

    // Archive buttons (토글 가능)
    document.querySelectorAll('.archive-btn').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        if (activeMonth === btn.dataset.month) {{
          btn.classList.remove('active');
          activeMonth = '';
        }} else {{
          document.querySelectorAll('.archive-btn').forEach(function (b) {{ b.classList.remove('active'); }});
          btn.classList.add('active');
          activeMonth = btn.dataset.month;
        }}
        filterArticles();
      }});
    }});

    // ── URL 파라미터로 필터 초기화 (기사 페이지에서 돌아올 때 딥링크 지원) ──
    (function () {{
      const params = new URLSearchParams(window.location.search);
      const pSearch = params.get('search');
      const pCat    = params.get('cat');
      const pMonth  = params.get('month');

      if (pSearch) {{
        const input = document.getElementById('search-input');
        input.value = pSearch;
        searchQuery = pSearch.toLowerCase();
      }}
      if (pCat) {{
        activeCategory = pCat;
        document.querySelectorAll('.cat-btn').forEach(function (b) {{
          b.classList.toggle('active', b.dataset.cat === pCat);
        }});
      }}
      if (pMonth) {{
        activeMonth = pMonth;
        document.querySelectorAll('.archive-btn').forEach(function (b) {{
          b.classList.toggle('active', b.dataset.month === pMonth);
        }});
      }}
      if (pSearch || pCat || pMonth) filterArticles();
    }})();
  </script>

</body>
</html>
'''


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Scanning articles...")
    all_articles = scan_articles(ROOT)
    print(f"Found {len(all_articles)} articles")

    # index.html — ALL articles
    index_html = build_page(all_articles, "IT뉴스", "index")
    index_path = ROOT / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"Written: {index_path}")

    # reports.html — articles from reports/ directory
    reports_dir = ROOT / "reports"
    report_articles = []
    if reports_dir.exists():
        for html_path in sorted(reports_dir.rglob("index.html"), reverse=True):
            meta = extract_metadata(html_path, ROOT)
            if meta:
                report_articles.append(meta)
        report_articles.sort(key=lambda a: a["date"] or a["month"] or "0000", reverse=True)

    reports_html = build_page(report_articles, "발표회 정리 - IT뉴스", "smartphone")
    reports_path = ROOT / "reports.html"
    reports_path.write_text(reports_html, encoding="utf-8")
    print(f"Written: {reports_path} ({len(report_articles)} articles)")

    print("Done.")


if __name__ == "__main__":
    main()
