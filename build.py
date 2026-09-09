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
        self.title_ko = ""
        self.title_zh = ""
        self.title_ja = ""
        self.title_en = ""
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
            elif name == "title-ko":
                self.title_ko = content
            elif name == "title-zh":
                self.title_zh = content
            elif name == "title-ja":
                self.title_ja = content
            elif name == "title-en":
                self.title_en = content

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

    # 다국어 제목: meta 태그에서 추출 (없으면 기본 title로 폴백)
    title_ko = parser.title_ko or title
    title_zh = parser.title_zh or title_ko
    title_ja = parser.title_ja or title_ko
    title_en = parser.title_en or title_ko

    return {
        "title": title,
        "title_ko": title_ko,
        "title_zh": title_zh,
        "title_ja": title_ja,
        "title_en": title_en,
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
    if category == "phone":
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


def _esc(s: str) -> str:
    """HTML 속성값 이스케이프."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def article_card_html(article: dict) -> str:
    raw_title = article["title"]
    card_title = (raw_title[:42] + "…") if len(raw_title) > 43 else raw_title
    title = card_title.replace("<", "&lt;").replace(">", "&gt;")
    url = article["url"].replace('"', "&quot;")
    date_display = article["date"] or article["month"] or ""
    category = article.get("category", "")
    month = article.get("month", "")

    # 다국어 제목 (카드 표시 및 검색용)
    title_ko = _esc(article.get("title_ko", raw_title))
    title_zh = _esc(article.get("title_zh", raw_title))
    title_ja = _esc(article.get("title_ja", raw_title))
    title_en = _esc(article.get("title_en", raw_title))

    search_title = _esc(raw_title)
    return f'''    <article class="article-card"
             data-title="{search_title.lower()}"
             data-title-ko="{title_ko.lower()}"
             data-title-zh="{title_zh.lower()}"
             data-title-ja="{title_ja.lower()}"
             data-title-en="{title_en.lower()}"
             data-category="{category}"
             data-month="{month}"
             data-date="{article['date']}">
      <a href="{url}" class="card-link">
        {thumbnail_html(article["thumbnail"], title)}
        <div class="card-body">
          <div class="card-badges">
            {article_badges_html(article)}
          </div>
          <h2 class="card-title"
              data-ko="{title_ko}"
              data-zh="{title_zh}"
              data-ja="{title_ja}"
              data-en="{title_en}">{title}</h2>
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


# ── "공사 중" 페이지 ─────────────────────────────────────────────────────────

def build_under_construction_page(
    title: str,
    heading: str,
    message: str,
    active_nav: str,  # "index" or "smartphone"
) -> str:
    """아직 콘텐츠가 없는 섹션용 페이지. 헤더·네비는 유지하고 본문은 파비콘 +
    안내 문구만 중앙 정렬로 보여준다.
    """
    index_active = ' class="nav-active"' if active_nav == "index" else ""
    phone_active = ' class="nav-active"' if active_nav == "smartphone" else ""

    return f'''<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | AI시테이 블로그</title>
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
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      background: var(--bg); color: var(--text); min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
      font-size: 16px;
    }}
    a {{ color: inherit; text-decoration: none; }}

    .site-header {{
      position: sticky; top: 0; z-index: 100; height: var(--header-height);
      background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; padding: 0 20px; gap: 16px;
    }}
    .header-logo {{ display: flex; align-items: center; gap: 8px;
      font-size: 17px; font-weight: 800; color: var(--text); flex-shrink: 0; }}
    .header-logo:hover {{ color: var(--accent); }}
    .logo-icon {{ width: 32px; height: 32px;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      border-radius: 8px; display: flex; align-items: center; justify-content: center;
      font-size: 16px; flex-shrink: 0; }}
    .logo-text {{ font-size: 17px; font-weight: 800; }}
    .logo-accent {{ color: var(--accent); }}
    .header-nav {{ display: flex; align-items: center; gap: 4px; }}
    .header-nav a {{ padding: 6px 14px; border-radius: 6px; font-size: 14px;
      color: var(--text-secondary); transition: background 0.15s, color 0.15s; }}
    .header-nav a:hover, .header-nav a.nav-active {{
      background: var(--surface); color: var(--text); }}
    .header-nav a.nav-active {{ color: var(--accent); font-weight: 600; }}

    .uc-wrap {{
      min-height: calc(100vh - var(--header-height));
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 48px 20px; gap: 20px;
    }}
    .uc-icon {{
      width: 140px; height: 140px; border-radius: 28px;
      background: var(--bg-secondary); border: 1px solid var(--border);
      display: flex; align-items: center; justify-content: center;
      padding: 16px; box-shadow: 0 18px 40px rgba(0,0,0,0.35);
    }}
    .uc-icon img {{ width: 100%; height: 100%; object-fit: contain; opacity: 0.95; }}
    .uc-badge {{
      font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase;
      color: var(--accent); font-weight: 700;
      background: rgba(59, 130, 246, 0.12);
      border: 1px solid rgba(59, 130, 246, 0.35);
      padding: 4px 12px; border-radius: 999px;
    }}
    .uc-title {{ font-size: clamp(24px, 4vw, 32px); font-weight: 800;
      letter-spacing: -0.5px; text-align: center; }}
    .uc-message {{ font-size: 15px; color: var(--text-secondary);
      line-height: 1.7; text-align: center; max-width: 520px; }}
    .uc-cta {{
      margin-top: 4px; display: inline-flex; align-items: center; gap: 6px;
      padding: 10px 18px; background: var(--accent); color: #fff;
      border-radius: 10px; font-size: 14px; font-weight: 600;
      transition: opacity 0.15s;
    }}
    .uc-cta:hover {{ opacity: 0.9; }}
  </style>
</head>
<body>
  <header class="site-header">
    <a class="header-logo" href="index.html">
      <span class="logo-icon">📡</span>
      <span class="logo-text">AI<span class="logo-accent">시테이</span> 블로그</span>
    </a>
    <nav class="header-nav">
      <a href="index.html"{index_active}>IT뉴스</a>
    </nav>
  </header>

  <main class="uc-wrap">
    <div class="uc-icon">
      <img src="assets/images/apple-touch-icon.png" alt="공사 중">
    </div>
    <span class="uc-badge">🚧 Under Construction</span>
    <h1 class="uc-title">{heading}</h1>
    <p class="uc-message">{message}</p>
    <a class="uc-cta" href="index.html">← IT뉴스로 돌아가기</a>
  </main>
</body>
</html>
'''


# ── Page template ─────────────────────────────────────────────────────────────

def build_page(articles, page_title, active_nav):
    from site_ui import render_home
    return render_home(articles, page_title, data_url="assets/data/reports.json" if active_nav == "smartphone" else "assets/data/articles.json", route="reports" if active_nav == "smartphone" else "news")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Scanning articles...")
    all_articles = scan_articles(ROOT)
    print(f"Found {len(all_articles)} articles")

    from site_ui import write_home_files, upgrade_article_files
    write_home_files(ROOT, all_articles)
    print(f"Written paginated index and search data ({len(all_articles)} articles)")
    print(f"Updated shared article presentation: {upgrade_article_files(ROOT)} pages")

    # reports.html — 발표회 정리 (reports/ 디렉터리의 아티클)
    reports_dir = ROOT / "reports"
    report_articles = []
    if reports_dir.exists():
        for html_path in sorted(reports_dir.rglob("index.html"), reverse=True):
            meta = extract_metadata(html_path, ROOT)
            if meta:
                report_articles.append(meta)
        report_articles.sort(key=lambda a: a["date"] or a["month"] or "0000", reverse=True)

    if report_articles:
        write_home_files(ROOT, report_articles, "발표회 정리", route="reports")
        reports_html = (ROOT / "reports.html").read_text(encoding="utf-8")
    else:
        # 정리된 발표회가 아직 없을 때 — "공사 중" 페이지로 렌더
        reports_html = build_under_construction_page(
            title="발표회 정리",
            heading="발표회 정리 페이지는 아직 준비 중입니다",
            message="신제품 발표회·언팩 이벤트를 한국어로 정리한 콘텐츠를 곧 선보일 예정입니다. "
                    "조만간 업데이트될 예정이니 잠시만 기다려 주세요.",
            active_nav="smartphone",
        )
    reports_path = ROOT / "reports.html"
    reports_path.write_text(reports_html, encoding="utf-8")
    print(f"Written: {reports_path} ({len(report_articles)} articles)")

    print("Done.")


if __name__ == "__main__":
    main()
