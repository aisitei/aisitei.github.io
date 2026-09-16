#!/usr/bin/env python3
"""
patch_missing_images.py — scrape_article_images() URL 재구성 버그로 이미지가
0장으로 저장된 기존 기사들을 재처리하는 스크립트.

배경:
  scraper.scrape_article_images()가 article_id만으로 데스크톱 URL을 "/0/..."로
  재구성하다가, 원본이 "/1/..." 같은 다른 IT之家 URL 네임스페이스일 때 완전히
  무관한 기사에서 이미지를 찾는 버그가 있었다 (수정 완료). 이 버그로 이미지 없이
  저장된 기존 기사들의 이미지만 다시 채워 넣는다 — 이미 번역된 제목/본문(ko/zh/ja/en)은
  그대로 보존하고 재번역하지 않는다. (batch_reprocess.py와 달리 텍스트 재번역·LLM
  호출을 하지 않으므로 이미 붙어있는 en/ja/zh 백필 내용을 잃지 않는다.)

사용법:
  python3 patch_missing_images.py --scan articles/2026-09    # 대상 목록만 출력
  python3 patch_missing_images.py --scan articles/2026-09 --apply   # 실제 재처리
  python3 patch_missing_images.py --apply --dirs articles/2026-09/2026-09-16/xiaomi-18-pro-series-announced
"""
import argparse
import glob
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

from bs4 import BeautifulSoup

import config
from scraper import Article, extract_article_id, scrape_article_images, fetch_page, clean_title
from translator import translate_caption, translate_caption_en, translate_caption_ja, translate_caption_batch
from ocr import process_image_translations
from html_generator import TranslatedArticle, save_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

BTN_ORIGINAL_RE = re.compile(r'<a[^>]+class="btn-original"[^>]+href="([^"]+)"')


def find_candidates(root: str) -> list[str]:
    """root 아래에서 'IT之家 소스 + 이미지 없음' 기사 디렉토리 목록을 반환."""
    candidates = []
    for r, _dirs, files in os.walk(root):
        if "index.html" not in files:
            continue
        fp = os.path.join(r, "index.html")
        content = open(fp, encoding="utf-8").read()
        m = BTN_ORIGINAL_RE.findall(content)
        if not m:
            continue
        href = m[0]
        if "ithome.com" not in href:
            continue  # Gizmochina는 재스크레이핑 불가 (main.py 주석 참고)
        images_dir = os.path.join(r, "images")
        has_images = os.path.isdir(images_dir) and len(os.listdir(images_dir)) > 0
        if not has_images:
            candidates.append(r)
    return sorted(candidates)


def parse_existing_article(article_dir: str) -> dict:
    """저장된 index.html에서 제목/본문(4개 언어)·메타데이터를 읽어온다."""
    index_path = os.path.join(article_dir, "index.html")
    html = open(index_path, encoding="utf-8").read()
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1", class_="article-title")
    titles = {lang: (h1.get(f"data-{lang}") or "") for lang in ("ko", "zh", "ja", "en")}

    bodies = {}
    for lb in soup.find_all("div", class_="lang-body"):
        lang = lb.get("data-lang")
        if lang not in ("ko", "zh", "ja", "en"):
            continue
        bodies[lang] = [str(child) for child in lb.find_all(recursive=False)]

    def meta(name: str) -> str:
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""

    category = meta("article-category")
    brand = meta("article-brand")
    brand_color = meta("article-brand-color")

    href_match = BTN_ORIGINAL_RE.search(html)
    source_url = href_match.group(1) if href_match else ""

    info_items = soup.select(".info-item")
    author = info_items[1].get_text(strip=True) if len(info_items) > 1 else ""

    return {
        "titles": titles,
        "bodies": bodies,
        "category": category,
        "brand": brand,
        "brand_color": brand_color,
        "source_url": source_url,
        "author": author,
    }


def patch_one(article_dir: str, articles_root: str) -> Optional[dict]:
    parsed = parse_existing_article(article_dir)
    source_url = parsed["source_url"]
    if not source_url:
        logger.error(f"  원본 URL을 찾지 못함, 건너뜀: {article_dir}")
        return None

    article_id = extract_article_id(source_url)
    if not article_id:
        logger.error(f"  article_id 추출 실패: {source_url}")
        return None

    if not all(parsed["titles"].values()) or not parsed["bodies"].get("ko"):
        logger.error(f"  기존 제목/본문 파싱 실패, 건너뜀: {article_dir}")
        return None

    logger.info(f"  이미지 재수집: {source_url}")
    images = scrape_article_images(article_id, source_url)
    if not images:
        logger.info("  이미지 0장 (원본 기사에 실제로 이미지가 없음) — 변경 없음")
        return None

    logger.info(f"  이미지 {len(images)}장 발견, OCR+캡션 번역 중...")
    image_translations = process_image_translations(
        images,
        translate_caption,
        translate_en_fn=translate_caption_en,
        translate_ja_fn=translate_caption_ja,
        translate_batch_fn=translate_caption_batch,
    )

    # 원본(중국어) 제목은 참고용 필드라 가볍게 재조회 (LLM 호출 없음).
    original_title = ""
    desktop_html = fetch_page(source_url)
    if desktop_html:
        h1 = BeautifulSoup(desktop_html, "html.parser").find("h1")
        if h1:
            original_title = clean_title(h1.get_text(strip=True))

    article = Article(
        article_id=article_id,
        title=original_title or parsed["titles"]["zh"],
        url=source_url,
        category=parsed["category"],
        image_urls=images,
        author=parsed["author"],
        brand=parsed["brand"],
        brand_color=parsed["brand_color"],
        source="ithome",
    )

    translated = TranslatedArticle(
        original=article,
        slug=os.path.basename(article_dir.rstrip("/")),
        titles=parsed["titles"],
        bodies=parsed["bodies"],
        image_translations=image_translations,
    )

    # article_dir 은 "<root>/<YYYY-MM>/<YYYY-MM-DD>/<slug>" 형태.
    date_str = os.path.basename(os.path.dirname(article_dir.rstrip("/")))

    result = save_article(translated, articles_root, date_str=date_str)
    if os.path.abspath(result["article_dir"]) != os.path.abspath(article_dir):
        logger.warning(
            f"  경고: 저장 경로가 기존 디렉토리와 다름! 기존={article_dir} 신규={result['article_dir']}"
        )
    logger.info(f"  저장 완료: {result['filepath']} (이미지 {len(result['local_images'])}장)")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", help="이 디렉토리 아래에서 대상 기사를 스캔")
    parser.add_argument("--dirs", nargs="*", help="특정 기사 디렉토리(들)만 처리")
    parser.add_argument("--apply", action="store_true", help="실제로 재처리 실행 (없으면 대상 목록만 출력)")
    parser.add_argument("--limit", type=int, help="이번 실행에서 처리할 최대 건수")
    args = parser.parse_args()

    if args.dirs:
        candidates = list(args.dirs)
    elif args.scan:
        candidates = find_candidates(args.scan)
    else:
        parser.error("--scan 또는 --dirs 중 하나는 필요합니다.")
        return

    logger.info(f"대상: {len(candidates)}건")
    if args.limit is not None:
        candidates = candidates[: args.limit]

    if not args.apply:
        for c in candidates:
            print(c)
        return

    articles_root = os.path.abspath(config.OUTPUT_DIR)
    patched = []
    failed = []
    for i, d in enumerate(candidates, 1):
        logger.info(f"[{i}/{len(candidates)}] {d}")
        try:
            result = patch_one(d, articles_root)
            if result:
                patched.append(result["article_dir"])
        except Exception as e:
            logger.error(f"  예외 발생: {e}")
            failed.append(d)
        if i < len(candidates):
            time.sleep(1)

    logger.info("=" * 60)
    logger.info(f"완료: 패치됨 {len(patched)}건 / 실패 {len(failed)}건 / 총 {len(candidates)}건")
    if failed:
        logger.warning("실패 목록:")
        for f in failed:
            logger.warning(f"  {f}")

    # 다음 단계(build.py 실행 + commit/push)에서 쓸 수 있도록 결과를 파일로 남긴다.
    out_path = os.path.join(config.LOG_DIR, "patch_missing_images_result.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(patched))
    logger.info(f"패치된 디렉토리 목록 저장: {out_path}")


if __name__ == "__main__":
    main()
