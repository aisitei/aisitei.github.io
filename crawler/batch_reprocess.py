#!/usr/bin/env python3
"""파손된 기사(번역 실패) 일괄 재처리 스크립트.

실행: python3 batch_reprocess.py
"""
import os
import sys
import re
import shutil
import logging
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

import config
from scraper import (
    fetch_page, scrape_article_content, scrape_article_images,
    detect_brand, Article, extract_article_id, classify_article, clean_title,
)
from translator import translate_title, translate_article, generate_slug
from html_generator import TranslatedArticle, save_article
from deployer import ensure_repo, commit_and_push
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── 재처리 대상: (파손된 기사 디렉토리, 원문 URL) ──────────────────────────────

def find_broken_articles(articles_root: str) -> list[dict]:
    """한자가 대량 포함되거나 시스템 프롬프트가 유출된 기사 디렉토리 목록 반환."""
    broken = []
    for root, dirs, files in os.walk(articles_root):
        for f in files:
            if f != 'index.html':
                continue
            path = os.path.join(root, f)
            content = open(path, encoding='utf-8').read()
            m_title = re.search(r'<h1 class="article-title">(.*?)</h1>', content, re.DOTALL)
            m_url = re.search(r'<a class="btn-original" href="(https?://[^"]+)"', content)
            if not m_title:
                continue
            title = m_title.group(1).strip()
            url = m_url.group(1) if m_url else ''

            is_broken = False
            if re.search('[一-鿿]{6,}', title):
                is_broken = True
            non_space = [c for c in title if c not in ' \t\n']
            if non_space and sum(1 for c in non_space if '一' <= c <= '鿿') / len(non_space) > 0.35:
                is_broken = True
            if '브랜드명은 절대 음역' in title or '원문 그대로 표기하라' in title:
                is_broken = True

            if is_broken and url:
                broken.append({
                    'dir': os.path.dirname(path),
                    'url': url,
                    'title': title[:80],
                })
    broken.sort(key=lambda x: x['url'])
    return broken


def get_article_title(url: str) -> str:
    from scraper import fetch_page, clean_title
    html = fetch_page(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    return clean_title(h1.get_text(strip=True)) if h1 else ""


def reprocess_one(url: str, articles_root: str) -> Optional[dict]:
    """URL 하나를 재처리하여 TranslatedArticle 저장 결과 반환. 실패 시 None."""
    article_id = extract_article_id(url)
    if not article_id:
        logger.error(f"article_id 추출 실패: {url}")
        return None

    logger.info(f"[재처리] {url}")
    title = get_article_title(url)
    if not title:
        logger.error("  제목 수집 실패")
        return None

    paragraphs, author = scrape_article_content(url)
    if not paragraphs:
        logger.error("  본문 수집 실패")
        return None

    images = scrape_article_images(article_id)
    content_sample = " ".join(paragraphs[:3])
    brand, brand_color = detect_brand(title, content_sample)
    category = classify_article(title)

    article = Article(
        article_id=article_id,
        title=title,
        url=url,
        category=category,
        content_paragraphs=paragraphs,
        image_urls=images,
        author=author,
        brand=brand,
        brand_color=brand_color,
    )

    korean_title = translate_title(article.title, category=category, source_lang="zh")
    if not korean_title:
        logger.error("  제목 번역 실패")
        return None
    logger.info(f"  → {korean_title}")

    korean_paragraphs = translate_article(article.content_paragraphs, category=category, source_lang="zh")
    if not korean_paragraphs:
        logger.error("  본문 번역 실패")
        return None

    slug = generate_slug(korean_title)
    translated = TranslatedArticle(
        original=article,
        korean_title=korean_title,
        korean_paragraphs=korean_paragraphs,
        slug=slug,
    )
    result = save_article(translated, articles_root)
    logger.info(f"  저장: {result['filepath']}")
    return {'result': result, 'korean_title': korean_title}


def main():
    articles_root = os.path.abspath(config.OUTPUT_DIR)
    repo_dir = config.PRODUCTION_REPO_DIR

    # 1. 파손된 기사 목록 수집
    logger.info("=" * 60)
    logger.info("파손 기사 스캔 중...")
    broken = find_broken_articles(articles_root)
    logger.info(f"재처리 대상: {len(broken)}건")
    if not broken:
        logger.info("재처리할 기사 없음. 종료.")
        return

    # 2. 파손된 디렉토리 삭제
    logger.info("파손된 기사 디렉토리 삭제 중...")
    for b in broken:
        if os.path.isdir(b['dir']):
            shutil.rmtree(b['dir'])
            logger.info(f"  삭제: {b['dir']}")

    # 3. 재처리
    logger.info("=" * 60)
    logger.info("재번역 및 저장 시작...")
    saved_results = []
    saved_titles = []
    failed_urls = []

    for i, b in enumerate(broken, 1):
        logger.info(f"[{i}/{len(broken)}] {b['url']}")
        try:
            outcome = reprocess_one(b['url'], articles_root)
            if outcome:
                saved_results.append(outcome['result'])
                saved_titles.append(outcome['korean_title'])
            else:
                failed_urls.append(b['url'])
        except Exception as e:
            logger.error(f"  예외 발생: {e}")
            failed_urls.append(b['url'])
        # LLM 부하 분산
        if i < len(broken):
            time.sleep(3)

    logger.info("=" * 60)
    logger.info(f"재처리 완료: 성공 {len(saved_results)}건 / 실패 {len(failed_urls)}건")

    if failed_urls:
        logger.warning("실패 URL:")
        for u in failed_urls:
            logger.warning(f"  {u}")

    if not saved_results:
        logger.warning("저장된 기사 없음. push 건너뜀.")
        return

    # 4. build.py 실행 (index.html 재생성)
    import subprocess
    build_py = os.path.join(os.path.dirname(__file__), '..', 'build.py')
    if os.path.exists(build_py):
        logger.info("build.py 실행 중...")
        r = subprocess.run([sys.executable, build_py], capture_output=False)
        if r.returncode != 0:
            logger.warning("build.py 실행 실패")

    # 5. GitHub push
    if os.path.isdir(os.path.join(repo_dir, '.git')):
        ensure_repo(repo_dir)
        article_dirs = [r['article_dir'] for r in saved_results]
        commit_and_push(repo_dir, article_dirs, saved_titles)
        logger.info("push 완료!")
    else:
        logger.warning(f"git 저장소 없음: {repo_dir}")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
