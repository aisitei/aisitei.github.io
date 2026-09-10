"""Static, progressively enhanced news reader. No crawler/runtime dependencies."""
import html
from html.parser import HTMLParser
import json
import math
import os
import re
from pathlib import Path

PAGE_SIZE = 24
LABELS = {'': '전체', 'camera': '카메라', 'phone': '스마트폰', 'ai': 'AI', 'general': '테크'}
ASSET_VERSION = '20260910'


def esc(value):
    return html.escape(str(value or ''), quote=True)


def page_url(page):
    return 'index.html' if page == 1 else f'news/page-{page}.html'


def card(a, featured=False):
    title = a.get('title_ko') or a['title']
    image = a.get('thumbnail', '')
    category = a.get('category') or 'general'
    if image and not image.endswith('apple-touch-icon.png'):
        visual = f'<img src="{esc(image)}" alt="" loading="{"eager" if featured else "lazy"}" width="640" height="400">'
    else:
        visual = f'<div class="image-placeholder" aria-hidden="true"><span>{esc(LABELS.get(category, "테크"))}</span><b>AI시테이</b></div>'
    return f'''<article class="news-card{' lead-card' if featured else ''}"><a href="{esc(a['url'])}">
      <div class="news-image">{visual}</div><div class="news-copy">
      <div class="news-meta"><span class="topic" data-category="{esc(category)}">{esc(LABELS.get(category, '테크'))}</span><time datetime="{esc(a['date'])}">{esc(a['date'])}</time></div>
      <h2>{esc(title)}</h2><span class="read-story" aria-hidden="true">기사 읽기 <span>↗</span></span>
      </div></a></article>'''


def render_home(articles, page_title='IT뉴스', page=1, data_url='assets/data/articles.json', route='news'):
    pages = max(1, math.ceil(len(articles) / PAGE_SIZE))
    page = max(1, min(page, pages))
    selected = articles[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    latest = articles[0]['date'] if articles else ''
    months = sorted({a['month'] for a in articles if a.get('month')}, reverse=True)
    feature = selected[:3] if page == 1 else []
    listing = selected[3:] if feature else selected
    cards = ''.join(card(a, i == 0) for i, a in enumerate(feature))
    links = ''
    def url(n):
        if route == 'news':
            return page_url(n)
        return 'reports.html' if n == 1 else f'report-pages/page-{n}.html'
    if page > 1:
        links += f'<a rel="prev" href="{url(page-1)}" data-i18n="previous">이전</a>'
    links += f'<span class="page-status">{page} / {pages}</span>'
    if page < pages:
        links += f'<a rel="next" href="{url(page+1)}" data-i18n="next">다음</a>'
    seed = json.dumps({'articles': selected, 'total': len(articles), 'page': page, 'dataUrl': data_url, 'route': route}, ensure_ascii=False).replace('<', '\\u003c')
    base = '<base href="../">' if page > 1 else ''
    tabs = ''.join('<a href="index.html' + ('?cat=' + key if key else '') + '" data-filter="' + key + '" class="topic-tab' + (' selected' if not key else '') + '"' + (' aria-current="page"' if not key else '') + '>' + value + '</a>' for key, value in LABELS.items())
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{base}<title>{esc(page_title)} | AI시테이</title><meta name="description" content="카메라, 스마트폰, AI의 새로운 소식. 해외 테크 뉴스를 네 가지 언어로 읽는 AI시테이.">
<link rel="icon" href="assets/images/favicon.ico"><link rel="stylesheet" href="assets/site.css?v={ASSET_VERSION}">
<script defer src="assets/news.js?v={ASSET_VERSION}"></script></head>
<body class="news-home"><a class="skip-link" href="{url(page)}#news-content">본문으로 건너뛰기</a>
<header class="masthead"><div class="masthead-inner"><a class="wordmark" href="index.html" aria-label="AI시테이 홈"><span class="brand-mark">ai</span><span>AI<span class="brand-accent">시테이</span></span></a><span class="masthead-section" data-i18n="news">테크 뉴스</span>
<label class="language-control"><span class="sr-only" data-i18n="language">언어</span><select id="language" aria-label="언어 / Language"><option value="ko">🇰🇷 한국어</option><option value="en">🇺🇸 English</option><option value="ja">🇯🇵 日本語</option><option value="zh">🇨🇳 中文</option></select></label></div></header>
<main class="news-shell" id="news-content">
<section class="intro"><div><p class="eyebrow">THE TECH EDIT</p><h1 data-i18n="headline">기술의 변화, 매일 한눈에.</h1><p class="intro-description" data-i18n="description">카메라 · 스마트폰 · AI, 해외 테크 소식을 모아 전합니다.</p></div><div class="edition"><span data-i18n="updated">최근 발행</span><strong>{esc(latest)}</strong></div></section>
<form class="reader-tools" role="search" action="index.html"><label class="search-box"><span aria-hidden="true">⌕</span><span class="sr-only" data-i18n="searchLabel">기사 검색</span><input id="search" name="search" type="search" placeholder="궁금한 기술, 제품, 소식을 검색하세요" autocomplete="off"><button type="submit" data-i18n="search">검색</button></label>
<label class="archive-control"><span data-i18n="archive">아카이브</span><select id="month" name="month" aria-label="아카이브"><option value="" data-i18n="allDates">전체 기간</option>{''.join(f'<option value="{esc(m)}">{esc(m)}</option>' for m in months)}</select></label></form>
<nav class="topic-nav" aria-label="카테고리">{tabs}</nav>
<div class="filter-state" id="filter-state" hidden><span id="filter-description"></span><button id="reset" type="button" data-i18n="reset">필터 초기화</button></div>
<section id="featured-section" {'hidden' if not feature else ''}><div class="section-heading"><h2 data-i18n="latestHighlights">새로 들어온 소식</h2><span class="section-kicker">LATEST STORIES</span></div><div class="featured-grid" id="featured">{cards}</div></section>
<section class="latest-section" aria-labelledby="latest-heading"><div class="section-heading"><h2 id="latest-heading" data-i18n="latest">최신 뉴스</h2><span id="result-count" role="status" aria-live="polite">전체 {len(articles):,}개 기사</span></div><div id="news-grid" class="news-grid">{''.join(card(a) for a in listing)}</div><div id="empty-state" class="empty-state" hidden><h3 data-i18n="empty">검색 결과가 없습니다</h3><p data-i18n="emptyHint">다른 검색어를 입력하거나 필터를 초기화해 보세요.</p></div><p id="load-error" class="load-error" role="alert" hidden></p><nav id="pagination" class="pagination" aria-label="페이지">{links}</nav></section>
<noscript><p>검색과 언어 전환은 JavaScript가 필요합니다. 아래 페이지 이동으로 모든 기사를 읽을 수 있습니다.</p></noscript>
</main><footer class="site-footer"><a class="footer-brand" href="index.html">AI시테이</a><p data-i18n="footer">해외 테크 뉴스 · 자동 수집 및 번역 · 원문 출처는 각 기사에 표시됩니다.</p><a href="{url(page)}#news-content" data-i18n="top">맨 위로 ↑</a></footer>
<script id="news-seed" type="application/json">{seed}</script></body></html>'''


def write_home_files(root, articles, page_title='IT뉴스', route='news'):
    root = Path(root)
    filename = 'articles.json' if route == 'news' else 'reports.json'
    data_path = root / 'assets' / 'data' / filename
    data_path.parent.mkdir(parents=True, exist_ok=True)
    # Only fields used by the reader. No article bodies or credentials.
    keys = ('title', 'title_ko', 'title_en', 'title_ja', 'title_zh', 'url', 'date', 'month', 'category', 'thumbnail')
    records = [{k: a.get(k, '') for k in keys} for a in articles]
    data_path.write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    folder = 'news' if route == 'news' else 'report-pages'
    pages = max(1, math.ceil(len(records) / PAGE_SIZE))
    (root / folder).mkdir(exist_ok=True)
    (root / folder / ".gitkeep").touch(exist_ok=True)
    # Remove only numbered generated pages made obsolete by a smaller corpus.
    for stale in (root / folder).glob('page-*.html'):
        match = re.fullmatch(r'page-(\d+)\.html', stale.name)
        if match and int(match[1]) > pages:
            stale.unlink()
    for number in range(1, pages + 1):
        path = root / ('index.html' if route == 'news' else 'reports.html') if number == 1 else root / folder / f'page-{number}.html'
        path.write_text(render_home(records, page_title, number, f'assets/data/{filename}', route), encoding='utf-8')


class ArticleLayoutParser(HTMLParser):
    """Locate complete div blocks by offsets; keep original HTML bytes unchanged."""
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.lines = [0] + [m.end() for m in re.finditer('\n', text)]
        self.stack = []
        self.blocks = {}
        self.feed(text)

    def source_position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            classes = dict(attrs).get('class', '').split()
            kind = next((name for name in ('article-meta', 'hero-image-wrap') if name in classes), None)
            self.stack.append((kind, self.source_position()))

    def handle_endtag(self, tag):
        if tag == 'div' and self.stack:
            kind, start = self.stack.pop()
            if kind and kind not in self.blocks:
                self.blocks[kind] = (start, self.source_position() + len('</div>'))


def title_before_image(text):
    layout = ArticleLayoutParser(text)
    hero = layout.blocks.get('hero-image-wrap')
    meta = layout.blocks.get('article-meta')
    if hero and meta and hero[1] <= meta[0]:
        gap = re.sub(r'(?m)^[ \t]+$', '', text[hero[1]:meta[0]])
        gap = gap.replace('<!-- Article meta: brand badge + category badge + title + info -->', '<!-- Article image -->')
        return text[:hero[0]] + text[meta[0]:meta[1]] + gap + text[hero[0]:hero[1]] + text[meta[1]:]
    if hero and meta and meta[1] <= hero[0]:
        gap = re.sub(r'(?m)^[ \t]+$', '', text[meta[1]:hero[0]])
        gap = gap.replace('<!-- Article meta: brand badge + category badge + title + info -->', '<!-- Article image -->')
        return text[:meta[1]] + gap + text[hero[0]:]
    return text


def upgrade_article(text, prefix):
    """Add shared presentation without parsing/reserializing translated markup."""
    if 'class="article-main"' not in text:
        return text
    marker = '<!-- shared-reader-assets -->'
    assets = f'{marker}\n<link rel="stylesheet" href="{prefix}assets/site.css?v={ASSET_VERSION}">\n<script defer src="{prefix}assets/news.js?v={ASSET_VERSION}"></script>\n<script defer src="{prefix}assets/article.js?v={ASSET_VERSION}"></script>\n<!-- /shared-reader-assets -->'
    if marker in text:
        text = re.sub(r'<!-- shared-reader-assets -->.*?<!-- /shared-reader-assets -->', lambda _: assets, text, flags=re.S)
    else:
        text = text.replace('</head>', assets + '\n</head>', 1)
    # Old article search navigated away mid-typing. Keep Enter behavior only.
    text = re.sub(r'    // 입력 중에도 딜레이 후 이동.*?(?=  </script>)', '', text, count=1, flags=re.S)
    return title_before_image(text)


def upgrade_article_files(root):
    count = 0
    for path in (Path(root) / 'articles').rglob('index.html'):
        text = path.read_bytes().decode('utf-8')
        prefix = os.path.relpath(root, path.parent).replace(os.sep, '/') + '/'
        updated = upgrade_article(text, prefix)
        if text != updated:
            path.write_bytes(updated.encode('utf-8'))
            count += 1
    return count
