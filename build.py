#!/usr/bin/env python3
"""
build.py - 블로그 전체 페이지를 자동 생성합니다.
- index.html: IT뉴스 (ITHOME 기사)
- smartphone.html: 스마트폰 출시회 보고서
- ai.html: AI (공사중)

사용법: python build.py
"""

import os
import re
import html
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).parent
ARTICLES_DIR = BASE_DIR / "articles"
REPORTS_DIR = BASE_DIR / "reports"

# ============================================================
# 카테고리 분류
# ============================================================
CATEGORY_RULES = {
    "camera": {
        "keywords": [
            "카메라", "camera", "센서", "sensor", "렌즈", "lens", "lumix", "nikon",
            "sony", "imx", "leica", "canon", "fuji", "panasonic", "hasselblad",
            "리콜", "recall", "액션카메라", "action-camera", "xtu", "라이카",
            "ceo", "사진", "photo", "촬영"
        ],
        "color": "#2563eb",
        "label": "카메라",
    },
    "phone": {
        "keywords": [
            "폰", "phone", "스마트폰", "smartphone", "폴더블", "foldable",
            "galaxy", "iphone", "oppo", "vivo", "xiaomi", "poco", "honor",
            "samsung", "oneplus", "realme", "출시", "배터리", "5g",
            "find-n", "magic-v", "ultra"
        ],
        "color": "#7c3aed",
        "label": "스마트폰",
    },
    "ai": {
        "keywords": [
            "ai", "인공지능", "llm", "gpt", "chatbot", "챗봇", "머신러닝",
            "딥러닝", "도우미", "assistant", "didi", "자율주행"
        ],
        "color": "#059669",
        "label": "AI",
    },
}

# ============================================================
# 공통 HTML 템플릿
# ============================================================
COMMON_CSS = """    :root {
      --primary: #2563eb;
      --primary-light: #3b82f6;
      --primary-dark: #1d4ed8;
      --accent: #f59e0b;
      --bg: #ffffff;
      --bg-secondary: #f8fafc;
      --bg-card: #ffffff;
      --text: #0f172a;
      --text-secondary: #64748b;
      --text-muted: #94a3b8;
      --border: #e2e8f0;
      --border-light: #f1f5f9;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
      --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
      --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
      --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
      --radius: 12px;
      --radius-sm: 8px;
      --max-width: 1200px;
      --header-height: 64px;
      --sidebar-width: 280px;
      --cat-camera: #2563eb;
      --cat-phone: #7c3aed;
      --cat-ai: #059669;
    }

    html.dark {
      --bg: #0f172a;
      --bg-secondary: #1e293b;
      --bg-card: #1e293b;
      --text: #f1f5f9;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --border: #334155;
      --border-light: #1e293b;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
      --shadow: 0 1px 3px rgba(0,0,0,0.4);
      --shadow-md: 0 4px 6px rgba(0,0,0,0.4);
      --shadow-lg: 0 10px 15px rgba(0,0,0,0.5);
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { scroll-behavior: smooth; }

    body {
      font-family: 'Noto Sans KR', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.7;
      transition: background 0.3s, color 0.3s;
      overflow-x: hidden;
    }

    .header {
      position: sticky; top: 0; z-index: 1000;
      background: var(--bg);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(12px);
      background-color: color-mix(in srgb, var(--bg), transparent 10%);
      height: var(--header-height);
    }
    .header-inner {
      max-width: var(--max-width); margin: 0 auto; padding: 0 24px;
      height: 100%; display: flex; align-items: center; justify-content: space-between;
    }
    .logo { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text); }
    .logo-icon {
      width: 36px; height: 36px;
      background: linear-gradient(135deg, var(--primary), var(--primary-light));
      border-radius: 10px; display: flex; align-items: center; justify-content: center;
      color: #fff; font-weight: 700; font-size: 16px;
    }
    .logo-text { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
    .logo-text span { color: var(--primary); }
    .nav-desktop { display: flex; align-items: center; gap: 4px; }
    .nav-link {
      padding: 8px 16px; border-radius: var(--radius-sm); text-decoration: none;
      color: var(--text-secondary); font-size: 14px; font-weight: 500; transition: all 0.2s;
    }
    .nav-link:hover, .nav-link.active { color: var(--primary); background: color-mix(in srgb, var(--primary), transparent 92%); }
    .header-actions { display: flex; align-items: center; gap: 8px; }
    .btn-icon {
      width: 40px; height: 40px; border: none; border-radius: var(--radius-sm);
      background: transparent; color: var(--text-secondary); cursor: pointer;
      display: flex; align-items: center; justify-content: center; transition: all 0.2s; font-size: 18px;
    }
    .btn-icon:hover { background: var(--bg-secondary); color: var(--text); }
    .menu-toggle { display: none; }

    .footer { border-top: 1px solid var(--border); padding: 40px 24px; margin-top: 48px; }
    .footer-inner {
      max-width: var(--max-width); margin: 0 auto;
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;
    }
    .footer-left { font-size: 13px; color: var(--text-muted); }
    .footer-links { display: flex; gap: 20px; }
    .footer-links a { font-size: 13px; color: var(--text-muted); text-decoration: none; transition: color 0.2s; }
    .footer-links a:hover { color: var(--primary); }

    .mobile-drawer { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; }
    .mobile-drawer.open { display: block; }
    .drawer-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.5); }
    .drawer-panel {
      position: absolute; top: 0; right: 0; width: 280px; height: 100%;
      background: var(--bg); padding: 24px; overflow-y: auto; box-shadow: -4px 0 20px rgba(0,0,0,0.15);
    }
    .drawer-close {
      width: 36px; height: 36px; border: none; background: var(--bg-secondary);
      border-radius: var(--radius-sm); font-size: 18px; cursor: pointer; color: var(--text);
      display: flex; align-items: center; justify-content: center; margin-bottom: 24px; margin-left: auto;
    }
    .drawer-nav { display: flex; flex-direction: column; gap: 4px; }
    .drawer-nav a {
      padding: 12px 16px; border-radius: var(--radius-sm); text-decoration: none;
      color: var(--text); font-size: 15px; font-weight: 500; transition: background 0.2s;
    }
    .drawer-nav a:hover, .drawer-nav a.active { background: color-mix(in srgb, var(--primary), transparent 92%); color: var(--primary); }

    .scroll-top {
      position: fixed; bottom: 24px; right: 24px; width: 44px; height: 44px;
      border-radius: 50%; background: var(--primary); color: #fff; border: none; cursor: pointer;
      display: none; align-items: center; justify-content: center; font-size: 20px;
      box-shadow: var(--shadow-lg); transition: all 0.3s; z-index: 500;
    }
    .scroll-top.visible { display: flex; }
    .scroll-top:hover { transform: translateY(-2px); background: var(--primary-dark); }

    .fade-in { animation: fadeIn 0.5s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

    @media (max-width: 768px) {
      :root { --header-height: 56px; }
      .nav-desktop { display: none; }
      .menu-toggle { display: flex; }
      .footer-inner { flex-direction: column; text-align: center; }
    }"""

COMMON_JS = """    function toggleDarkMode() {
      document.documentElement.classList.toggle('dark');
      const isDark = document.documentElement.classList.contains('dark');
      localStorage.setItem('darkMode', isDark);
      updateDarkModeIcon(isDark);
    }
    function updateDarkModeIcon(isDark) {
      const btn = document.getElementById('darkModeBtn');
      btn.innerHTML = isDark
        ? '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
        : '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
    if (localStorage.getItem('darkMode') === 'true') { document.documentElement.classList.add('dark'); updateDarkModeIcon(true); }
    function toggleDrawer() {
      const drawer = document.getElementById('mobileDrawer');
      drawer.classList.toggle('open');
      document.body.style.overflow = drawer.classList.contains('open') ? 'hidden' : '';
    }
    function scrollToTop() { window.scrollTo({ top: 0, behavior: 'smooth' }); }
    window.addEventListener('scroll', () => { document.getElementById('scrollTopBtn').classList.toggle('visible', window.scrollY > 400); });"""


def generate_nav(active_page: str) -> str:
    """네비게이션 바를 생성합니다. active_page: 'news', 'smartphone', 'ai'"""
    pages = [
        ("IT뉴스", "/", "news"),
        ("스마트폰", "/smartphone.html", "smartphone"),
        ("AI", "/ai.html", "ai"),
    ]
    desktop_links = []
    drawer_links = []
    for label, href, key in pages:
        active = ' class="nav-link active"' if key == active_page else ' class="nav-link"'
        desktop_links.append(f'        <a href="{href}"{active}>{label}</a>')
        d_active = ' class="active"' if key == active_page else ''
        drawer_links.append(f'        <a href="{href}"{d_active}>{label}</a>')

    return f"""  <header class="header">
    <div class="header-inner">
      <a href="/" class="logo">
        <div class="logo-icon">AI</div>
        <div class="logo-text"><span>AI시테이</span> 블로그</div>
      </a>
      <nav class="nav-desktop">
{chr(10).join(desktop_links)}
      </nav>
      <div class="header-actions">
        <button class="btn-icon" onclick="toggleDarkMode()" title="다크모드" aria-label="다크모드 전환" id="darkModeBtn">
          <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        </button>
        <button class="btn-icon menu-toggle" onclick="toggleDrawer()" aria-label="메뉴 열기">
          <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
      </div>
    </div>
  </header>

  <div class="mobile-drawer" id="mobileDrawer">
    <div class="drawer-overlay" onclick="toggleDrawer()"></div>
    <div class="drawer-panel">
      <button class="drawer-close" onclick="toggleDrawer()" aria-label="메뉴 닫기">&times;</button>
      <nav class="drawer-nav">
{chr(10).join(drawer_links)}
      </nav>
    </div>
  </div>"""


FOOTER_HTML = f"""  <footer class="footer">
    <div class="footer-inner">
      <div class="footer-left">
        &copy; {datetime.now().year} AI시테이 블로그. 기사 출처:
        <a href="https://www.ithome.com" target="_blank" rel="noopener" style="color:var(--primary);text-decoration:none;">IT之家</a>
      </div>
      <div class="footer-links">
        <a href="https://github.com/aisitei" target="_blank" rel="noopener">GitHub</a>
      </div>
    </div>
  </footer>

  <button class="scroll-top" id="scrollTopBtn" onclick="scrollToTop()" aria-label="맨 위로 스크롤">
    <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>
  </button>"""


def wrap_page(title: str, description: str, active_page: str, extra_css: str, body_content: str, extra_js: str = "") -> str:
    """공통 페이지 래퍼"""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700;900&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
{COMMON_CSS}
{extra_css}
  </style>
</head>
<body>

{generate_nav(active_page)}

{body_content}

{FOOTER_HTML}

  <script>
{COMMON_JS}
{extra_js}
  </script>
</body>
</html>"""


# ============================================================
# IT뉴스 페이지 (index.html)
# ============================================================
def extract_title(filepath: Path) -> str:
    try:
        content = filepath.read_text(encoding="utf-8")
        match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        if match:
            title = match.group(1).strip()
            title = re.sub(r"\s*[-|]\s*IT之家.*$", "", title)
            title = re.sub(r"\s*[-|]\s*IT홈.*$", "", title)
            return title
    except Exception:
        pass
    return filepath.stem.replace("-", " ").title()


def extract_excerpt(filepath: Path) -> str:
    try:
        content = filepath.read_text(encoding="utf-8")
        match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', content, re.IGNORECASE)
        if match and len(match.group(1).strip()) > 20:
            return match.group(1).strip()[:150]
        match = re.search(r"<p[^>]*>(.*?)</p>", content, re.IGNORECASE | re.DOTALL)
        if match:
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if len(text) > 20:
                return text[:150]
    except Exception:
        pass
    return ""


def classify_article(filename: str, title: str) -> str:
    combined = (filename + " " + title).lower()
    scores = {}
    for cat, info in CATEGORY_RULES.items():
        score = sum(1 for kw in info["keywords"] if kw.lower() in combined)
        scores[cat] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "camera"


def scan_articles():
    articles = []
    if not ARTICLES_DIR.exists():
        return articles
    for date_dir in sorted(ARTICLES_DIR.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        date_name = date_dir.name
        for html_file in sorted(date_dir.glob("*.html"), reverse=True):
            title = extract_title(html_file)
            excerpt = extract_excerpt(html_file)
            category = classify_article(html_file.name, title)
            rel_path = f"articles/{date_name}/{html_file.name}"
            articles.append({"date": date_name, "title": title, "excerpt": excerpt, "category": category, "path": rel_path, "filename": html_file.name})
    return articles


def format_date_korean(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.year}년 {d.month}월 {d.day}일"
    except ValueError:
        return date_str


def generate_news_page(articles: list) -> str:
    by_date = defaultdict(list)
    for a in articles:
        by_date[a["date"]].append(a)

    cat_counts = count_by_category(articles)
    total = len(articles)
    num_dates = len(by_date)

    # 카테고리 필터
    cat_buttons = ['        <button class="cat-btn active" onclick="filterCategory(\'all\', this)">전체</button>']
    for cat_id, cat_info in CATEGORY_RULES.items():
        if cat_counts.get(cat_id, 0) > 0:
            cat_buttons.append(f'        <button class="cat-btn" onclick="filterCategory(\'{cat_id}\', this)"><span class="cat-dot" style="background:{cat_info["color"]}"></span>{cat_info["label"]}</button>')

    # 날짜 그룹
    date_groups = []
    for date, arts in sorted(by_date.items(), reverse=True):
        dk = format_date_korean(date)
        cards = []
        for a in arts:
            ci = CATEGORY_RULES.get(a["category"], CATEGORY_RULES["camera"])
            exc = f"<p class='card-excerpt'>{html.escape(a['excerpt'])}</p>" if a["excerpt"] else ""
            cards.append(f"""          <a href="{a['path']}" class="article-card" data-category="{a['category']}">
            <div class="card-category-bar" style="background:{ci['color']}"></div>
            <div class="card-body">
              <div class="card-meta">
                <span class="card-tag tag-{a['category']}">{ci['label']}</span>
                <span class="card-date">{a['date'].replace('-','.')}</span>
              </div>
              <h3 class="card-title">{html.escape(a['title'])}</h3>
              {exc}
              <span class="card-source">출처: IT之家</span>
            </div>
          </a>""")
        date_groups.append(f"""      <div class="date-group fade-in">
        <div class="date-header">
          <h2>{dk}</h2>
          <span class="date-badge">{len(arts)}건</span>
        </div>
        <div class="article-grid">
{chr(10).join(cards)}
        </div>
      </div>""")

    # 사이드바
    cat_list = "\n".join(
        f'          <li><span class="cat-name"><span class="cat-dot" style="background:{ci["color"]}"></span>{ci["label"]}</span><span class="cat-count">{cat_counts.get(cid,0)}</span></li>'
        for cid, ci in CATEGORY_RULES.items() if cat_counts.get(cid, 0) > 0
    )
    by_month = defaultdict(int)
    for a in articles:
        try:
            d = datetime.strptime(a["date"], "%Y-%m-%d")
            by_month[f"{d.year}년 {d.month}월"] += 1
        except ValueError:
            pass
    archive = "\n".join(f'          <li><a href="#"><span>{m}</span><span>{c}건</span></a></li>' for m, c in by_month.items())

    extra_css = """
    .hero { background: linear-gradient(135deg, var(--primary-dark), var(--primary), #6366f1); color: #fff; padding: 48px 24px; text-align: center; }
    .hero-inner { max-width: 680px; margin: 0 auto; }
    .hero h1 { font-size: 32px; font-weight: 800; margin-bottom: 12px; letter-spacing: -0.5px; line-height: 1.3; }
    .hero p { font-size: 16px; opacity: 0.9; line-height: 1.6; }
    .hero-stats { display: flex; justify-content: center; gap: 32px; margin-top: 24px; }
    .hero-stat { text-align: center; }
    .hero-stat-num { font-size: 28px; font-weight: 800; display: block; }
    .hero-stat-label { font-size: 13px; opacity: 0.8; }
    .main-layout { max-width: var(--max-width); margin: 0 auto; padding: 32px 24px; display: grid; grid-template-columns: 1fr var(--sidebar-width); gap: 32px; }
    .category-filter { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
    .cat-btn { padding: 8px 16px; border: 1px solid var(--border); border-radius: 100px; background: var(--bg-card); color: var(--text-secondary); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; font-family: inherit; white-space: nowrap; }
    .cat-btn:hover { border-color: var(--primary); color: var(--primary); }
    .cat-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
    .cat-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
    .date-group { margin-bottom: 32px; }
    .date-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid var(--border-light); }
    .date-header h2 { font-size: 18px; font-weight: 700; color: var(--text); }
    .date-badge { font-size: 12px; padding: 2px 10px; border-radius: 100px; background: color-mix(in srgb, var(--primary), transparent 90%); color: var(--primary); font-weight: 600; }
    .article-grid { display: grid; gap: 16px; }
    .article-card { display: flex; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; transition: all 0.25s; text-decoration: none; color: inherit; }
    .article-card:hover { border-color: var(--primary); box-shadow: var(--shadow-md); transform: translateY(-2px); }
    .card-category-bar { width: 4px; flex-shrink: 0; }
    .card-body { padding: 20px; flex: 1; display: flex; flex-direction: column; gap: 8px; }
    .card-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .card-tag { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
    .tag-camera { background: color-mix(in srgb, var(--cat-camera), transparent 88%); color: var(--cat-camera); }
    .tag-phone { background: color-mix(in srgb, var(--cat-phone), transparent 88%); color: var(--cat-phone); }
    .tag-ai { background: color-mix(in srgb, var(--cat-ai), transparent 88%); color: var(--cat-ai); }
    .card-date { font-size: 12px; color: var(--text-muted); }
    .card-title { font-size: 17px; font-weight: 600; line-height: 1.4; letter-spacing: -0.3px; color: var(--text); }
    .card-excerpt { font-size: 14px; color: var(--text-secondary); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .card-source { font-size: 12px; color: var(--text-muted); margin-top: auto; padding-top: 8px; }
    .sidebar { display: flex; flex-direction: column; gap: 24px; }
    .sidebar-widget { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
    .widget-title { font-size: 15px; font-weight: 700; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-light); display: flex; align-items: center; gap: 8px; }
    .ad-placeholder { background: var(--bg-secondary); border: 2px dashed var(--border); border-radius: var(--radius); padding: 40px 20px; text-align: center; color: var(--text-muted); font-size: 13px; }
    .ad-placeholder-icon { font-size: 24px; margin-bottom: 8px; }
    .category-list { list-style: none; }
    .category-list li { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border-light); font-size: 14px; }
    .category-list li:last-child { border-bottom: none; }
    .category-list .cat-name { display: flex; align-items: center; gap: 8px; color: var(--text); font-weight: 500; }
    .category-list .cat-count { font-size: 12px; color: var(--text-muted); background: var(--bg-secondary); padding: 2px 8px; border-radius: 100px; }
    .archive-list { list-style: none; }
    .archive-list li a { display: flex; justify-content: space-between; padding: 8px 0; text-decoration: none; color: var(--text-secondary); font-size: 14px; transition: color 0.2s; }
    .archive-list li a:hover { color: var(--primary); }
    @media (max-width: 1024px) {
      .main-layout { grid-template-columns: 1fr; }
      .sidebar { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }
    }
    @media (max-width: 768px) {
      .hero { padding: 32px 20px; }
      .hero h1 { font-size: 24px; }
      .hero-stats { gap: 20px; }
      .hero-stat-num { font-size: 22px; }
      .main-layout { padding: 20px 16px; gap: 24px; }
      .category-filter { overflow-x: auto; flex-wrap: nowrap; padding-bottom: 8px; -webkit-overflow-scrolling: touch; }
      .article-card { flex-direction: column; }
      .card-category-bar { width: 100%; height: 3px; }
      .card-title { font-size: 15px; }
      .sidebar { grid-template-columns: 1fr; }
    }
    @media (max-width: 480px) {
      .hero h1 { font-size: 20px; }
      .hero p { font-size: 14px; }
      .card-body { padding: 16px; }
    }"""

    body = f"""  <section class="hero">
    <div class="hero-inner fade-in">
      <h1>IT之家 최신 테크 뉴스를<br>한국어로 매일 전합니다</h1>
      <p>카메라, 스마트폰, AI 등 중국 IT 뉴스를 자동 번역하여 매일 업데이트합니다</p>
      <div class="hero-stats">
        <div class="hero-stat"><span class="hero-stat-num">{total}</span><span class="hero-stat-label">총 기사</span></div>
        <div class="hero-stat"><span class="hero-stat-num">{num_dates}</span><span class="hero-stat-label">일자</span></div>
        <div class="hero-stat"><span class="hero-stat-num">{len([c for c in cat_counts if cat_counts[c] > 0])}</span><span class="hero-stat-label">카테고리</span></div>
      </div>
    </div>
  </section>

  <div class="main-layout">
    <main>
      <div class="category-filter">
{chr(10).join(cat_buttons)}
      </div>

{chr(10).join(date_groups)}

      <div class="ad-placeholder" style="margin-top: 16px;">
        <div class="ad-placeholder-icon">📢</div>
        <div>Google AdSense 광고 영역 (인피드 광고)</div>
      </div>
    </main>

    <aside class="sidebar">
      <div class="ad-placeholder">
        <div class="ad-placeholder-icon">📢</div>
        <div>Google AdSense</div>
      </div>
      <div class="sidebar-widget">
        <h3 class="widget-title">📂 카테고리</h3>
        <ul class="category-list">
{cat_list}
        </ul>
      </div>
      <div class="sidebar-widget">
        <h3 class="widget-title">📅 아카이브</h3>
        <ul class="archive-list">
{archive}
        </ul>
      </div>
      <div class="sidebar-widget">
        <h3 class="widget-title">ℹ️ 블로그 소개</h3>
        <p style="font-size:13px; color:var(--text-secondary); line-height:1.7;">
          IT之家의 최신 테크 기사를 매일 자동으로 수집하여 한국어로 번역 제공합니다.
        </p>
      </div>
    </aside>
  </div>"""

    extra_js = """
    function filterCategory(category, btn) {
      document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.article-card').forEach(card => {
        card.style.display = (category === 'all' || card.dataset.category === category) ? '' : 'none';
      });
      document.querySelectorAll('.date-group').forEach(group => {
        const visible = group.querySelectorAll('.article-card:not([style*="display: none"])');
        group.style.display = visible.length > 0 ? '' : 'none';
      });
    }"""

    return wrap_page("AI시테이 블로그 | IT 뉴스 & 테크 리뷰",
                      "IT之家 최신 기사를 한국어로 번역하여 제공하는 테크 블로그",
                      "news", extra_css, body, extra_js)


def count_by_category(articles: list) -> dict:
    counts = defaultdict(int)
    for a in articles:
        counts[a["category"]] += 1
    return counts


# ============================================================
# 스마트폰 페이지 (smartphone.html)
# ============================================================
def scan_reports():
    """reports/ 디렉토리를 스캔하여 스마트폰 출시 보고서 목록을 반환합니다."""
    reports = []
    if not REPORTS_DIR.exists():
        return reports
    for report_dir in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if not report_dir.is_dir() or report_dir.name.startswith("."):
            continue
        report_html = report_dir / "report.html"
        if not report_html.exists():
            continue
        # 폴더명에서 날짜와 모델명 추출: 2026-03-23-xiaomi-17-ultra
        name = report_dir.name
        parts = name.split("-", 3)
        date_str = "-".join(parts[:3]) if len(parts) >= 3 else ""
        model_slug = parts[3] if len(parts) > 3 else name
        title = extract_title(report_html)
        # images 폴더에서 대표 이미지 확인
        images_dir = report_dir / "images"
        has_images = images_dir.exists() and any(images_dir.iterdir()) if images_dir.exists() else False
        reports.append({
            "date": date_str,
            "title": title,
            "slug": name,
            "path": f"reports/{name}/report.html",
            "has_images": has_images,
        })
    return reports


def generate_smartphone_page(reports: list) -> str:
    extra_css = """
    .page-hero { background: linear-gradient(135deg, #7c3aed, #a855f7, #c084fc); color: #fff; padding: 48px 24px; text-align: center; }
    .page-hero-inner { max-width: 680px; margin: 0 auto; }
    .page-hero h1 { font-size: 32px; font-weight: 800; margin-bottom: 12px; letter-spacing: -0.5px; line-height: 1.3; }
    .page-hero p { font-size: 16px; opacity: 0.9; line-height: 1.6; }
    .page-content { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
    .report-grid { display: grid; gap: 20px; }
    .report-card {
      display: flex; background: var(--bg-card); border: 1px solid var(--border);
      border-radius: var(--radius); overflow: hidden; transition: all 0.25s;
      text-decoration: none; color: inherit;
    }
    .report-card:hover { border-color: #7c3aed; box-shadow: var(--shadow-md); transform: translateY(-2px); }
    .report-bar { width: 5px; flex-shrink: 0; background: linear-gradient(180deg, #7c3aed, #a855f7); }
    .report-body { padding: 24px; flex: 1; }
    .report-date { font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }
    .report-title { font-size: 19px; font-weight: 700; line-height: 1.4; color: var(--text); margin-bottom: 8px; }
    .report-badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 4px; background: color-mix(in srgb, #7c3aed, transparent 88%); color: #7c3aed; }
    .report-count { text-align: center; margin-bottom: 24px; font-size: 14px; color: var(--text-secondary); }
    @media (max-width: 768px) {
      .page-hero { padding: 32px 20px; }
      .page-hero h1 { font-size: 24px; }
      .page-content { padding: 20px 16px; }
      .report-body { padding: 16px; }
      .report-title { font-size: 16px; }
    }"""

    report_cards = []
    for r in reports:
        date_display = r["date"].replace("-", ".") if r["date"] else ""
        report_cards.append(f"""      <a href="{r['path']}" class="report-card fade-in">
        <div class="report-bar"></div>
        <div class="report-body">
          <div class="report-date">{date_display}</div>
          <h3 class="report-title">{html.escape(r['title'])}</h3>
          <span class="report-badge">출시회 보고서</span>
        </div>
      </a>""")

    if not report_cards:
        report_cards_html = '      <p style="text-align:center; color:var(--text-muted); padding:40px 0;">아직 등록된 보고서가 없습니다.</p>'
    else:
        report_cards_html = "\n".join(report_cards)

    body = f"""  <section class="page-hero">
    <div class="page-hero-inner fade-in">
      <h1>중국 스마트폰 출시회 보고서</h1>
      <p>중국 주요 스마트폰 신제품 출시 발표회를 분석하여 정리합니다</p>
    </div>
  </section>

  <div class="page-content">
    <p class="report-count">총 {len(reports)}개의 보고서</p>
    <div class="report-grid">
{report_cards_html}
    </div>
  </div>"""

    return wrap_page("AI시테이 블로그 | 스마트폰 출시회 보고서",
                      "중국 스마트폰 출시 발표회 분석 보고서",
                      "smartphone", extra_css, body)


# ============================================================
# AI 페이지 (ai.html) - 공사중
# ============================================================
def generate_ai_page() -> str:
    extra_css = """
    .construction {
      max-width: 600px; margin: 0 auto; padding: 120px 24px; text-align: center;
    }
    .construction-icon { font-size: 64px; margin-bottom: 24px; }
    .construction h1 { font-size: 28px; font-weight: 700; margin-bottom: 12px; color: var(--text); }
    .construction p { font-size: 16px; color: var(--text-secondary); line-height: 1.7; }
    .construction-back {
      display: inline-block; margin-top: 32px; padding: 12px 28px;
      background: var(--primary); color: #fff; border-radius: 100px;
      text-decoration: none; font-size: 14px; font-weight: 600; transition: all 0.2s;
    }
    .construction-back:hover { background: var(--primary-dark); transform: translateY(-1px); }
    @media (max-width: 768px) {
      .construction { padding: 80px 20px; }
      .construction-icon { font-size: 48px; }
      .construction h1 { font-size: 22px; }
    }"""

    body = """  <div class="construction fade-in">
    <div class="construction-icon">🚧</div>
    <h1>공사중</h1>
    <p>AI 관련 콘텐츠를 준비하고 있습니다.<br>조금만 기다려 주세요!</p>
    <a href="/" class="construction-back">IT뉴스로 돌아가기</a>
  </div>"""

    return wrap_page("AI시테이 블로그 | AI", "AI 콘텐츠 준비 중", "ai", extra_css, body)


# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    # 1. IT뉴스 (index.html)
    articles = scan_articles()
    print(f"Found {len(articles)} articles")
    (BASE_DIR / "index.html").write_text(generate_news_page(articles), encoding="utf-8")
    print("Generated index.html")

    # 2. 스마트폰 (smartphone.html)
    reports = scan_reports()
    print(f"Found {len(reports)} reports")
    (BASE_DIR / "smartphone.html").write_text(generate_smartphone_page(reports), encoding="utf-8")
    print("Generated smartphone.html")

    # 3. AI (ai.html)
    (BASE_DIR / "ai.html").write_text(generate_ai_page(), encoding="utf-8")
    print("Generated ai.html")
