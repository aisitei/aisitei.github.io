#!/usr/bin/env python3
"""단일 기사 재처리 스크립트.

사용법:
  python reprocess_article.py <article_url>
  python reprocess_article.py https://www.ithome.com/0/941/115.htm
"""
import glob
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(__file__))

import config
from scraper import (
    fetch_page, scrape_article_content, scrape_article_images,
    detect_brand, Article, extract_article_id, classify_article, clean_title,
)
from translator import translate_title, translate_article, generate_slug, translate_caption
from ocr import process_image_translations, process_local_image_translations
from html_generator import TranslatedArticle, save_article
from deployer import ensure_repo, commit_and_push

from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_article_title(url: str) -> str:
    html = fetch_page(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    return clean_title(h1.get_text(strip=True)) if h1 else ""


def reprocess(url: str, push: bool = True):
    article_id = extract_article_id(url)
    if not article_id:
        logger.error(f"article_id 추출 실패: {url}")
        return

    logger.info(f"=== 재처리 시작: {url} (id={article_id}) ===")

    logger.info("[1/5] 제목 및 본문 스크래핑...")
    title = get_article_title(url)
    if not title:
        logger.error("제목 수집 실패")
        return
    logger.info(f"  제목: {title}")

    paragraphs, author = scrape_article_content(url)
    if not paragraphs:
        logger.error("본문 수집 실패")
        return

    logger.info("[2/5] 이미지 수집...")
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

    logger.info("[3/5] 번역...")
    korean_title = translate_title(article.title, category=category)
    if not korean_title:
        logger.error("제목 번역 실패")
        return
    logger.info(f"  → {korean_title}")

    korean_paragraphs = translate_article(article.content_paragraphs, category=category)
    if not korean_paragraphs:
        logger.error("본문 번역 실패")
        return

    slug = generate_slug(korean_title)
    translated = TranslatedArticle(
        original=article,
        korean_title=korean_title,
        korean_paragraphs=korean_paragraphs,
        slug=slug,
    )

    articles_root = os.path.abspath(config.OUTPUT_DIR)
    os.makedirs(articles_root, exist_ok=True)

    logger.info("[4/5] OCR...")
    if config.OCR_ENABLED and images:
        # CDN URL로 먼저 시도
        image_translations = process_image_translations(images, translate_caption)

        # CDN 실패한 이미지는 로컬 저장본으로 폴백
        failed_urls = [u for u in images if u not in image_translations]
        if failed_urls:
            logger.info(f"CDN 실패 {len(failed_urls)}장 → 로컬 이미지로 재시도")
            # 이미지를 먼저 로컬에 저장 (OCR 전용 임시 저장)
            tmp = save_article(translated, articles_root)
            local_dir = os.path.join(tmp["article_dir"], "images")
            url_path_pairs = []
            for i, url in enumerate(images):
                if url in failed_urls:
                    matches = glob.glob(os.path.join(local_dir, f"img{i+1:02d}.*"))
                    if matches:
                        url_path_pairs.append((url, matches[0]))
            if url_path_pairs:
                local_results = process_local_image_translations(url_path_pairs, translate_caption)
                image_translations.update(local_results)

        translated.image_translations = image_translations
    else:
        logger.info("OCR 비활성화 또는 이미지 없음 - 건너뜀")

    logger.info("[5/5] HTML 저장...")
    result = save_article(translated, articles_root)
    logger.info(f"저장 완료: {result['filepath']}")

    if push:
        repo_dir = config.PRODUCTION_REPO_DIR
        ensure_repo(repo_dir)
        commit_and_push(repo_dir, [result["article_dir"]], [korean_title])
        logger.info("push 완료!")

    logger.info("=== 완료 ===")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python reprocess_article.py <article_url>")
        sys.exit(1)
    reprocess(sys.argv[1])
