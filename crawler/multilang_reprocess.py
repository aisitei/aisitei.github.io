#!/usr/bin/env python3
"""
multilang_reprocess.py — 기존 기사에 4개 언어 콘텐츠를 소급 적용하는 배치 스크립트.

사용법:
  python3 multilang_reprocess.py [--limit N] [--no-push]

처리 흐름:
  1. articles/**/index.html 스캔
  2. <div class="lang-body" 가 이미 있으면 스킵
  3. source_url 추출 → ithome.com/gizmochina 스크레이핑
  4. 4개 언어 번역 (KO 이미 있으므로 EN/JA/ZH summary 추가)
  5. index.html 업데이트 (인플레이스)
  6. 완료된 URL 로그 파일(multilang_done.log)에 기록
  7. 옵션: git add/commit, 마지막에 push
"""
import os
import sys
import re
import time
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Optional

# ── sys.path: crawler 디렉토리 기준으로 임포트 ─────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import config
from translator import (
    translate_body_en, translate_body_ja, translate_body_zh, translate_body_zh_summary,
    translate_title_en, translate_title_ja, translate_title_zh,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(config.PRODUCTION_REPO_DIR)
ARTICLES_DIR = REPO_ROOT / "articles"
DONE_LOG = SCRIPT_DIR / "logs" / "multilang_done.log"
BATCH_COMMIT_SIZE = 20  # 이 건수마다 git commit


# ── 완료 로그 ─────────────────────────────────────────────────────────────────

def load_done_set() -> set:
    if not DONE_LOG.exists():
        return set()
    return set(DONE_LOG.read_text(encoding="utf-8").splitlines())


def mark_done(html_path: str):
    DONE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DONE_LOG, "a", encoding="utf-8") as f:
        f.write(html_path + "\n")


# ── HTML 파싱 헬퍼 ─────────────────────────────────────────────────────────────

def already_multilang(html: str) -> bool:
    """이미 multilang 처리된 기사인지 확인."""
    return 'class="lang-body"' in html


def extract_source_url(html: str) -> Optional[str]:
    """source_url 추출 (source-footer 내 href)."""
    m = re.search(r'class="btn-original"[^>]*href="([^"]+)"', html)
    if m:
        return m.group(1)
    # 대체: meta 태그 방식이 없으므로 source-footer div에서 a href 추출
    m = re.search(r'source-footer[\s\S]{0,300}?href="(https?://[^"]+)"', html)
    if m:
        return m.group(1)
    return None


def extract_ko_title(html: str) -> str:
    """기존 <h1 class="article-title"> 텍스트 추출. glossary 적용."""
    from translator import apply_glossary
    m = re.search(r'<h1[^>]*class="article-title"[^>]*>([\s\S]*?)</h1>', html)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        return apply_glossary(title)
    # <title>AI시테이 - ... 형식
    m = re.search(r'<title>AI시테이\s*-\s*(.+?)</title>', html)
    if m:
        return apply_glossary(m.group(1).strip())
    return ""


def extract_ko_body_paragraphs(html: str) -> list:
    """기존 본문에서 한국어 단락 HTML 리스트만 추출.

    이미 4개 언어 lang-body가 있는 기사는 data-lang="ko" 구간만,
    다음 언어(zh) div가 시작되는 지점을 경계로 잘라낸다.
    article-body 전체를 </div> 기준 논-그리디로 잡으면 ko/zh/ja/en이
    전부 한 덩어리로 캡처되는 버그가 있었음 (기존 lang-body를 뭉텅이로 삼킴).
    """
    if 'class="lang-body"' in html:
        m = re.search(
            r'<div class="lang-body" data-lang="ko">([\s\S]*?)'
            r'<div class="lang-body" data-lang="zh">',
            html,
        )
        if not m:
            return []
        body_html = m.group(1)
        # 이전 재처리에서 남은 중첩 래핑(주석/내부 div 오픈·클로즈) 제거
        body_html = re.sub(r'<!--\s*lang-body:\s*ko\s*-->', '', body_html)
        body_html = re.sub(r'<div class="lang-body" data-lang="ko">', '', body_html)
        body_html = re.sub(r'</div>\s*$', '', body_html.strip())
        parts = re.findall(r'<(?:p|h3|ul)[\s\S]*?</(?:p|h3|ul)>', body_html)
        return parts if parts else ([body_html.strip()] if body_html.strip() else [])

    m = re.search(r'<div class="article-body">([\s\S]*?)</div>\s*\n\s*<!-- All images', html)
    if not m:
        m = re.search(r'<div class="article-body">([\s\S]*?)</div>\s*\n\s*(?:<!--|\{% if images)', html)
    if not m:
        # 더 넓은 패턴: article-body div 전체
        m = re.search(r'<div class="article-body">([\s\S]*?)</div>\s*(?:\n\s*){1,3}(?:<!--|\{% )', html)
    if m:
        body_html = m.group(1).strip()
        # p/h3/ul 단위로 분리
        parts = re.findall(r'<(?:p|h3|ul)[\s\S]*?</(?:p|h3|ul)>', body_html)
        return parts if parts else [body_html]
    return []


def scrape_zh_content(source_url: str) -> list:
    """IT之家 원문 단락 스크레이핑."""
    try:
        from scraper import scrape_article_content
        paragraphs, _ = scrape_article_content(source_url)
        return paragraphs
    except Exception as e:
        logger.warning(f"스크레이핑 실패 ({source_url}): {e}")
        return []


def scrape_en_content(source_url: str) -> list:
    """Gizmochina 영어 원문 단락 스크레이핑."""
    try:
        from scraper_gizmochina import scrape_article_content as scrape_gc
        paragraphs, _ = scrape_gc(source_url)
        return paragraphs
    except Exception as e:
        logger.warning(f"Gizmochina 스크레이핑 실패 ({source_url}): {e}")
        return []


# ── HTML 패치 ─────────────────────────────────────────────────────────────────

_LANG_BODY_TMPL = """\
      <!-- lang-body: {lang} -->
      <div class="lang-body" data-lang="{lang}">
{content}
      </div>"""


def build_lang_body(lang: str, paragraphs: list) -> str:
    content = "\n".join(f"        {p}" for p in paragraphs)
    return _LANG_BODY_TMPL.format(lang=lang, content=content)


def _lang_body_inner(paragraphs: list) -> str:
    """div 래핑 없이 내부 콘텐츠만 반환.

    이미 존재하는 lang-body div 안에 삽입할 때 build_lang_body()의 전체
    래핑(주석+div)을 그대로 넣으면 기존 오픈태그 안에 또 중첩되어 div가
    이중으로 감싸지는 버그가 있었음.
    """
    return "\n".join(f"        {p}" for p in paragraphs)


def patch_html(html: str, titles: dict, bodies: dict) -> str:
    """기존 article-body를 4개 언어 lang-body div로 교체하고 meta/h1 속성 추가."""

    # 1) head에 title-xx meta 태그 추가/교체
    meta_block = (
        f'  <meta name="title-ko" content="{_esc_attr(titles.get("ko", ""))}">\n'
        f'  <meta name="title-zh" content="{_esc_attr(titles.get("zh", ""))}">\n'
        f'  <meta name="title-ja" content="{_esc_attr(titles.get("ja", ""))}">\n'
        f'  <meta name="title-en" content="{_esc_attr(titles.get("en", ""))}">\n'
    )
    if 'name="title-ko"' in html:
        # 기존 title-xx 메타 4개를 교체
        html = re.sub(r'\s*<meta name="title-ko"[^>]*>\n?', '', html)
        html = re.sub(r'\s*<meta name="title-zh"[^>]*>\n?', '', html)
        html = re.sub(r'\s*<meta name="title-ja"[^>]*>\n?', '', html)
        html = re.sub(r'\s*<meta name="title-en"[^>]*>\n?', '', html)
    if 'name="article-brand-color"' in html:
        html = re.sub(
            r'(<meta name="article-brand-color"[^>]*>)',
            r'\1\n' + meta_block.rstrip('\n'),
            html, count=1,
        )
    else:
        html = html.replace('</head>', meta_block + '</head>', 1)

    # 2) <h1 class="article-title">에 data-xx 속성 추가/교체
    def replace_h1(m):
        content = m.group(2)
        new_tag = (
            f'<h1 class="article-title"'
            f' data-ko="{_esc_attr(titles.get("ko", ""))}"'
            f' data-zh="{_esc_attr(titles.get("zh", ""))}"'
            f' data-ja="{_esc_attr(titles.get("ja", ""))}"'
            f' data-en="{_esc_attr(titles.get("en", ""))}">'
            f'{content}</h1>'
        )
        return new_tag

    html = re.sub(
        r'(<h1[^>]*class="article-title"[^>]*>)([\s\S]*?)</h1>',
        replace_h1, html, count=1,
    )

    # 3) article-body div를 4개 lang-body div로 교체
    ko_body = build_lang_body("ko", bodies.get("ko", []))
    zh_body = build_lang_body("zh", bodies.get("zh", bodies.get("ko", [])))
    ja_body = build_lang_body("ja", bodies.get("ja", bodies.get("ko", [])))
    en_body = build_lang_body("en", bodies.get("en", bodies.get("ko", [])))
    new_body_block = (
        '      <!-- Body — 4개 언어 -->\n'
        '      <div class="article-body">\n'
        + ko_body + '\n'
        + zh_body + '\n'
        + ja_body + '\n'
        + en_body + '\n'
        '      </div>'
    )

    # 기존 article-body 블록 교체
    if 'class="lang-body"' in html:
        # 이미 lang-body가 있는 경우: 각 언어 div의 내부 콘텐츠만 교체
        # (기존 오픈태그를 그대로 유지하고 내부만 갈아끼워야 함. build_lang_body()의
        # 전체 래핑을 다시 넣으면 이중 래핑되므로 내부 콘텐츠만 삽입한다.)
        inner_bodies = {
            "ko": _lang_body_inner(bodies.get("ko", [])),
            "zh": _lang_body_inner(bodies.get("zh", bodies.get("ko", []))),
            "ja": _lang_body_inner(bodies.get("ja", bodies.get("ko", []))),
            "en": _lang_body_inner(bodies.get("en", bodies.get("ko", []))),
        }
        for lang, inner in inner_bodies.items():
            html = re.sub(
                r'(<div class="lang-body" data-lang="' + lang + r'">)[\s\S]*?(</div>)',
                lambda m, inner=inner: m.group(1) + '\n' + inner + '\n        ' + m.group(2),
                html, count=1,
            )
    else:
        # 처음 처리: article-body 전체를 lang-body 4개로 교체
        html = re.sub(
            r'<div class="article-body">[\s\S]*?</div>(\s*\n\s*<!-- (?:All images|Source footer))',
            new_body_block + r'\1',
            html, count=1,
        )

    # 4) visitor counter JS 제거 + 언어 선택기 JS 추가 (없으면)
    if 'visitCount_today' in html and 'aisitei_lang' not in html:
        # visitor counter IIFE 제거
        html = re.sub(
            r'// 방문자 카운터[^\n]*\n\s*\(function \(\) \{[\s\S]*?\}\)\(\);\n',
            '',
            html, count=1,
        )
        # header-right 내 visitor-counter div 제거 → 언어 선택기로 교체
        html = re.sub(
            r'<div class="header-right">\s*<div class="visitor-counter"[^>]*>[^<]*</div>\s*</div>',
            (
                '<div class="header-right">\n'
                '      <div class="lang-selector" id="lang-selector">\n'
                '        <button class="lang-btn" data-lang="ko">\U0001f1f0\U0001f1f7 한국어</button>\n'
                '        <button class="lang-btn" data-lang="zh">\U0001f1e8\U0001f1f3 中文</button>\n'
                '        <button class="lang-btn" data-lang="ja">\U0001f1ef\U0001f1f5 日本語</button>\n'
                '        <button class="lang-btn" data-lang="en">\U0001f1fa\U0001f1f8 English</button>\n'
                '      </div>\n'
                '    </div>'
            ),
            html, count=1,
        )

    # 5) lang-selector CSS 추가 (없으면)
    if '.lang-selector' not in html:
        lang_css = (
            '\n    /* ── Language selector ── */\n'
            '    .lang-selector {\n'
            '      display: flex;\n'
            '      align-items: center;\n'
            '      gap: 4px;\n'
            '    }\n'
            '    .lang-btn {\n'
            '      padding: 4px 8px;\n'
            '      border-radius: 6px;\n'
            '      border: 1px solid var(--border);\n'
            '      background: transparent;\n'
            '      color: var(--text-secondary);\n'
            '      font-size: 12px;\n'
            '      cursor: pointer;\n'
            '      transition: background 0.15s, color 0.15s, border-color 0.15s;\n'
            '      white-space: nowrap;\n'
            '    }\n'
            '    .lang-btn:hover { background: var(--surface); color: var(--text); }\n'
            '    .lang-btn.active-lang { background: var(--accent); border-color: var(--accent); color: #fff; }\n'
            '    .lang-body { display: none; }\n'
            '    .lang-body.lang-active { display: contents; }\n'
        )
        html = html.replace('  </style>', lang_css + '  </style>', 1)

    # 6) 언어 선택기 JS 추가 (없으면 </script> 직전)
    if 'aisitei_lang' not in html:
        lang_js = (
            '\n    // ── 언어 선택기 ──\n'
            '    (function () {\n'
            "      var LANG_KEY = 'aisitei_lang';\n"
            "      var DEFAULT_LANG = 'ko';\n"
            '      function getLang() { return localStorage.getItem(LANG_KEY) || DEFAULT_LANG; }\n'
            '      function setLang(lang) {\n'
            '        localStorage.setItem(LANG_KEY, lang);\n'
            '        applyLang(lang);\n'
            '      }\n'
            '      function applyLang(lang) {\n'
            "        document.querySelectorAll('.lang-body').forEach(function (el) {\n"
            "          el.classList.toggle('lang-active', el.getAttribute('data-lang') === lang);\n"
            '        });\n'
            "        var titleEl = document.querySelector('.article-title');\n"
            "        if (titleEl) { var t = titleEl.getAttribute('data-' + lang) || titleEl.getAttribute('data-ko') || ''; if (t) titleEl.textContent = t; }\n"
            "        document.querySelectorAll('.lang-btn').forEach(function (b) { b.classList.toggle('active-lang', b.getAttribute('data-lang') === lang); });\n"
            "        var lm = { ko: 'ko', zh: 'zh-Hans', ja: 'ja', en: 'en' };\n"
            "        document.documentElement.setAttribute('lang', lm[lang] || 'ko');\n"
            '      }\n'
            "      document.querySelectorAll('.lang-btn').forEach(function (btn) {\n"
            "        btn.addEventListener('click', function () { setLang(btn.getAttribute('data-lang')); });\n"
            '      });\n'
            '      applyLang(getLang());\n'
            '    })();\n'
        )
        # 검색 이벤트 리스너 앞에 삽입
        html = html.replace(
            '    // 검색창 → Enter 시 메인 페이지로 이동',
            lang_js + '    // 검색창 → Enter 시 메인 페이지로 이동',
            1,
        )
        if 'aisitei_lang' not in html:
            html = html.replace('  </script>\n\n</body>', lang_js + '  </script>\n\n</body>', 1)

    return html


def _esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


# ── git 헬퍼 ─────────────────────────────────────────────────────────────────

def git_add_commit(paths: list, message: str):
    try:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "add"] + [str(p) for p in paths],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit", "-m", message],
            check=True, capture_output=True,
        )
        logger.info(f"git commit: {message}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"git 오류: {e.stderr.decode()[:200]}")


def git_push():
    try:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "push"],
            check=True, capture_output=True,
        )
        logger.info("git push 완료")
    except subprocess.CalledProcessError as e:
        logger.warning(f"git push 실패: {e.stderr.decode()[:200]}")


# ── 메인 처리 ─────────────────────────────────────────────────────────────────

def process_article(html_path: Path) -> bool:
    """단일 기사 처리. 성공하면 True 반환."""
    html = html_path.read_text(encoding="utf-8", errors="replace")

    if already_multilang(html):
        logger.debug(f"스킵 (이미 multilang): {html_path}")
        return False

    source_url = extract_source_url(html)
    if not source_url:
        logger.warning(f"source_url 없음: {html_path}")
        return False

    is_gizmochina = "gizmochina.com" in source_url
    is_ithome = "ithome.com" in source_url

    ko_title = extract_ko_title(html)
    ko_paragraphs = extract_ko_body_paragraphs(html)
    if not ko_paragraphs:
        logger.warning(f"KO 본문 추출 실패: {html_path}")
        return False

    ko_body_text = "\n\n".join(ko_paragraphs)
    # 로컬 LLM 컨텍스트 초과 방지: 입력이 너무 길면 앞부분만 사용
    MAX_BODY_CHARS = 6000
    if len(ko_body_text) > MAX_BODY_CHARS:
        logger.warning(f"본문 길이 초과 ({len(ko_body_text)}자) → {MAX_BODY_CHARS}자로 자름")
        ko_body_text = ko_body_text[:MAX_BODY_CHARS]
    zh_orig_text = ""

    # ZH 요약을 위해 원문 스크레이핑 (IT之家만)
    if is_ithome:
        zh_paragraphs_raw = scrape_zh_content(source_url)
        zh_orig_text = "\n\n".join(zh_paragraphs_raw)

    logger.info(f"번역 중: {ko_title[:50]}...")

    # EN
    en_body = translate_body_en(ko_body_text)
    en_paragraphs = [p.strip() for p in (en_body or "").split("\n\n") if p.strip()] or ko_paragraphs

    # JA
    ja_body = translate_body_ja(ko_body_text)
    ja_paragraphs = [p.strip() for p in (ja_body or "").split("\n\n") if p.strip()] or ko_paragraphs

    # ZH
    if zh_orig_text:
        zh_body = translate_body_zh_summary(zh_orig_text)
    else:
        zh_body = translate_body_zh(ko_body_text)
    zh_paragraphs = [p.strip() for p in (zh_body or "").split("\n\n") if p.strip()] or ko_paragraphs

    # 제목
    original_zh_title = ""
    if is_ithome:
        # html에서 original_title(중국어) 추출 시도
        m = re.search(r'data-original-title="([^"]+)"', html)
        if not m:
            # source-footer 내 원문 출처 인근 텍스트에서 추출 불가 → ko_title 그대로
            original_zh_title = ko_title
        else:
            original_zh_title = m.group(1)
    else:
        original_zh_title = ko_title

    if is_ithome:
        en_title = translate_title_en(original_zh_title) or ko_title
        ja_title = translate_title_ja(original_zh_title) or ko_title
        zh_title = original_zh_title
    else:
        en_title = translate_title_en(ko_title) or ko_title
        ja_title = translate_title_ja(ko_title) or ko_title
        zh_title = translate_title_zh(ko_title) or ko_title

    titles = {
        "ko": ko_title,
        "zh": zh_title,
        "ja": ja_title or ko_title,
        "en": en_title or ko_title,
    }
    bodies = {
        "ko": ko_paragraphs,
        "zh": zh_paragraphs,
        "ja": ja_paragraphs,
        "en": en_paragraphs,
    }

    patched = patch_html(html, titles, bodies)
    html_path.write_text(patched, encoding="utf-8")
    logger.info(f"  저장 완료: {html_path.relative_to(REPO_ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="기존 기사 4개 언어 소급 적용")
    parser.add_argument("--limit", type=int, default=0, help="처리할 최대 기사 수 (0=제한없음)")
    parser.add_argument("--no-push", action="store_true", help="git push 생략")
    parser.add_argument("--dry-run", action="store_true", help="실제 저장하지 않고 처리 대상만 출력")
    args = parser.parse_args()

    done_set = load_done_set()

    all_html = sorted(ARTICLES_DIR.rglob("index.html"), reverse=True)
    logger.info(f"전체 기사 수: {len(all_html)}")

    targets = []
    for hp in all_html:
        key = str(hp.relative_to(REPO_ROOT))
        if key in done_set:
            continue
        # 빠른 사전 스킵: 이미 multilang인지 확인
        try:
            content = hp.read_text(encoding="utf-8", errors="replace")
            if already_multilang(content):
                mark_done(key)
                continue
        except Exception:
            continue
        targets.append(hp)

    logger.info(f"처리 대상: {len(targets)}건")
    if args.limit > 0:
        targets = targets[:args.limit]
        logger.info(f"  → {args.limit}건으로 제한")

    if args.dry_run:
        for hp in targets:
            print(hp.relative_to(REPO_ROOT))
        return

    processed_paths = []
    total_done = 0

    for i, hp in enumerate(targets, 1):
        logger.info(f"[{i}/{len(targets)}] {hp.relative_to(REPO_ROOT)}")
        try:
            ok = process_article(hp)
            if ok:
                key = str(hp.relative_to(REPO_ROOT))
                mark_done(key)
                processed_paths.append(hp)
                total_done += 1

                # 배치 커밋
                if len(processed_paths) >= BATCH_COMMIT_SIZE:
                    git_add_commit(
                        processed_paths,
                        f"feat: multilang reprocess {len(processed_paths)}건 ({total_done}번째 배치)",
                    )
                    processed_paths = []

            time.sleep(2)  # LLM 부하 분산

        except Exception as e:
            logger.error(f"처리 오류 {hp}: {e}")
            continue

    # 남은 커밋
    if processed_paths:
        git_add_commit(
            processed_paths,
            f"feat: multilang reprocess 최종 {len(processed_paths)}건 (총 {total_done}건)",
        )

    # push
    if not args.no_push and total_done > 0:
        git_push()

    logger.info(f"완료: {total_done}건 처리됨")


if __name__ == "__main__":
    main()
