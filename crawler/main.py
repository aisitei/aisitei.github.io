#!/usr/bin/env python3
"""IT之家 뉴스 자동 번역 시스템 - 메인 스크립트

사용법:
  즉시 실행:   python main.py --run
  스케줄:      python main.py
  테스트:      python main.py --test
"""
import os
import sys
import json
import argparse
import logging
from datetime import datetime

import schedule
import time

import config
from scraper import collect_articles
from translator import translate_title, translate_article, generate_slug
from ocr import process_image_translations
from html_generator import TranslatedArticle, save_article
from deployer import ensure_repo, commit_and_push

os.makedirs(config.LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(config.LOG_DIR, f"{datetime.now():%Y-%m-%d}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def find_git_root(start_path: str):
    current = os.path.abspath(start_path)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


# ---------------------------------------------------------------------------
# Error state & resume script helpers
# ---------------------------------------------------------------------------

def _failed_log_path(today: str) -> str:
    return os.path.join(config.LOG_DIR, f"failed_{today}.json")


def _resume_script_path(today: str) -> str:
    return os.path.join(config.LOG_DIR, f"resume_{today}.py")


def _load_failed_log(today: str) -> list[dict]:
    path = _failed_log_path(today)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _append_failed_article(today: str, article_info: dict, error: str):
    """실패한 기사를 failed_YYYY-MM-DD.json 에 추가합니다."""
    entries = _load_failed_log(today)
    entries.append({
        "article_id": article_info.get("article_id", ""),
        "title": article_info.get("title", ""),
        "url": article_info.get("url", ""),
        "category": article_info.get("category", ""),
        "error": error,
        "timestamp": datetime.now().isoformat(),
    })
    path = _failed_log_path(today)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    logger.info(f"실패 기록: {path}")


def _write_resume_script(today: str):
    """실패한 기사들을 재처리하는 자가완결형 스크립트를 생성합니다."""
    entries = _load_failed_log(today)
    if not entries:
        return

    failed_articles = [
        {
            "article_id": e["article_id"],
            "title": e["title"],
            "url": e["url"],
            "category": e["category"],
        }
        for e in entries
    ]

    script = f'''#!/usr/bin/env python3
"""Auto-generated resume script for {today}. Run: python3 resume_{today}.py"""
# This script re-processes only the failed articles from {today}
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from scraper import scrape_article_content, scrape_article_images, detect_brand, Article
from translator import translate_title, translate_article, generate_slug
from html_generator import TranslatedArticle, save_article
from deployer import ensure_repo, commit_and_push

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

FAILED_ARTICLES = {json.dumps(failed_articles, ensure_ascii=False, indent=4)}


def main():
    logger.info(f"Resume script: {{len(FAILED_ARTICLES)}} 건 재처리 중...")
    articles_root = os.path.abspath(config.OUTPUT_DIR)
    os.makedirs(articles_root, exist_ok=True)

    saved_results = []
    article_titles = []

    for item in FAILED_ARTICLES:
        logger.info(f"재처리: {{item[\'title\'][:50]}}...")
        try:
            paragraphs, author = scrape_article_content(item["url"])
            images = scrape_article_images(item["article_id"])
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

            category = article.category
            korean_title = translate_title(article.title, category=category)
            if not korean_title:
                logger.warning(f"제목 번역 실패: {{article.title}}")
                continue
            korean_paragraphs = translate_article(article.content_paragraphs, category=category)
            if not korean_paragraphs:
                logger.warning(f"본문 번역 실패: {{article.title}}")
                continue

            slug = generate_slug(korean_title)
            translated = TranslatedArticle(
                original=article,
                korean_title=korean_title,
                korean_paragraphs=korean_paragraphs,
                slug=slug,
            )

            result = save_article(translated, articles_root)
            saved_results.append(result)
            article_titles.append(korean_title)
            logger.info(f"  저장: {{result[\'filepath\']}}")

        except Exception as e:
            logger.error(f"재처리 실패 {{item[\'article_id\']}}: {{e}}")

    if not saved_results:
        logger.warning("재처리된 기사 없음.")
        return

    # GitHub push
    repo_dir = config.PRODUCTION_REPO_DIR
    try:
        ensure_repo(repo_dir)
        article_dirs = [r["article_dir"] for r in saved_results]
        commit_and_push(repo_dir, article_dirs, article_titles)
        logger.info("push 완료!")
    except Exception as e:
        logger.error(f"배포 오류: {{e}}")

    logger.info(f"Resume 완료: {{len(saved_results)}}건 처리됨")


if __name__ == "__main__":
    main()
'''

    path = _resume_script_path(today)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(path, 0o755)
    logger.info(f"Resume 스크립트 생성: {path}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(limit: int = 0):
    """전체 파이프라인 실행. limit > 0 이면 해당 건수만 처리."""
    logger.info("=" * 60)
    logger.info("IT之家 뉴스 파이프라인 시작")
    logger.info("=" * 60)

    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 기사 수집
    logger.info("[1/5] 기사 수집 중...")
    articles = collect_articles()
    if not articles:
        logger.info("관련 기사 없음. 종료.")
        return
    if limit > 0:
        articles = articles[:limit]
        logger.info(f"{limit}건으로 제한 (전체 {len(articles)}건 중)")
    logger.info(f"{len(articles)}건 수집")

    # 2. 번역
    logger.info("[2/5] 번역 중...")
    translated_articles: list[TranslatedArticle] = []
    for article in articles:
        logger.info(f"번역: {article.title[:50]}...")
        article_info = {
            "article_id": article.article_id,
            "title": article.title,
            "url": article.url,
            "category": article.category,
        }
        category = article.category

        korean_title = translate_title(article.title, category=category)
        if not korean_title:
            err = "제목 번역 실패 (LLM None 반환)"
            logger.warning(f"{err}: {article.title}")
            _append_failed_article(today, article_info, err)
            _write_resume_script(today)
            continue

        korean_paragraphs = translate_article(article.content_paragraphs, category=category)
        if not korean_paragraphs:
            err = "본문 번역 실패 (LLM None 반환)"
            logger.warning(f"{err}: {article.title}")
            _append_failed_article(today, article_info, err)
            _write_resume_script(today)
            continue

        slug = generate_slug(korean_title)
        translated = TranslatedArticle(
            original=article,
            korean_title=korean_title,
            korean_paragraphs=korean_paragraphs,
            slug=slug,
        )
        translated_articles.append(translated)
        logger.info(f"  → {korean_title}")

    if not translated_articles:
        logger.warning("번역된 기사 없음. 종료.")
        return

    # 3. OCR (선택)
    if config.OCR_ENABLED:
        logger.info("[3/5] 이미지 OCR...")
        # 캡션 전용 짧은 텍스트 번역기 사용 (기사 본문용 프롬프트는 짧은
        # OCR 결과에 대해 메타 응답을 길게 출력하는 문제가 있어 분리).
        from translator import translate_caption
        for ta in translated_articles:
            if ta.original.image_urls:
                ta.image_translations = process_image_translations(
                    ta.original.image_urls, translate_caption,
                )
    else:
        logger.info("[3/5] OCR 비활성화 - 건너뜀")

    # 4. HTML + 이미지 저장
    logger.info("[4/5] HTML 생성 및 이미지 다운로드...")
    articles_root = os.path.abspath(config.OUTPUT_DIR)
    os.makedirs(articles_root, exist_ok=True)

    saved_results = []
    article_titles = []
    for ta in translated_articles:
        article_info = {
            "article_id": ta.original.article_id,
            "title": ta.original.title,
            "url": ta.original.url,
            "category": ta.original.category,
        }
        try:
            result = save_article(ta, articles_root)
            saved_results.append(result)
            article_titles.append(ta.korean_title)
            logger.info(f"  저장: {result['filepath']}")

        except Exception as e:
            err = f"save_article 실패: {e}"
            logger.error(f"{err}: {ta.original.title}")
            _append_failed_article(today, article_info, err)
            _write_resume_script(today)

    # 5. GitHub push
    logger.info("[5/5] GitHub push...")
    repo_dir = config.PRODUCTION_REPO_DIR
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        logger.warning(f"git 저장소 없음: {repo_dir}. push 건너뜀.")
    else:
        try:
            ensure_repo(repo_dir)
            article_dirs = [r["article_dir"] for r in saved_results]
            success = commit_and_push(repo_dir, article_dirs, article_titles)
            if success:
                logger.info("push 완료!")
        except Exception as e:
            logger.error(f"배포 오류: {e}")

    logger.info("=" * 60)
    logger.info(f"완료! {len(saved_results)}건 처리됨")
    logger.info("=" * 60)


def run_test():
    logger.info("=== 연결 테스트 ===")
    from scraper import fetch_page
    html = fetch_page(config.ITHOME_BASE_URL)
    logger.info(f"IT之家 접속: {'성공' if html else '실패'}")
    try:
        from translator import translate_text
        result = translate_text("测试翻译")
        logger.info(f"LLM 번역: {repr(result) if result else '실패'}")
    except Exception as e:
        logger.error(f"LLM 오류: {e}")
    logger.info(f"OCR 활성화: {config.OCR_ENABLED}")
    logger.info(f"PRODUCTION_REPO_DIR: {config.PRODUCTION_REPO_DIR}")
    logger.info("=== 완료 ===")


def main():
    parser = argparse.ArgumentParser(description="IT之家 뉴스 자동 번역 시스템")
    parser.add_argument("--run", action="store_true", help="즉시 1회 실행")
    parser.add_argument("--test", action="store_true", help="연결 테스트")
    parser.add_argument("--limit", type=int, default=0, help="처리할 기사 수 제한 (0=제한없음)")
    args = parser.parse_args()

    if args.test:
        run_test()
        return
    if args.run:
        run_pipeline(limit=args.limit)
        return

    logger.info(f"스케줄 모드: 매일 {config.SCHEDULE_TIME}")
    schedule.every().day.at(config.SCHEDULE_TIME).do(run_pipeline)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
