#!/usr/bin/env python3
"""
recover_from_source.py — 손상된 multilang 기사를 원문 재스크레이핑 + ko 재번역으로
복구하는 스크립트 (하이브리드 모드: ko는 클라우드 API로 빠르게, en/ja/zh는
이어서 backfill_multilang.py로 로컬 처리).

배경:
  recover_corrupted_multilang.py는 git 히스토리에서 "정상 버전"을 찾아 복원했는데,
  손상 감지 정규식이 너무 좁아서(이중 래핑 패턴만 감지) 이미 손상된 커밋을
  "정상"으로 오판하는 경우가 많았다. 그 결과 완료 표시된 324건 중 322건이 여전히
  오염 상태였고, title-zh 메타까지 한글로 오염된 경우도 있어 로컬 파일의 어떤
  필드도 신뢰할 수 없음이 확인됐다.

  이 스크립트는 git 히스토리를 전혀 신뢰하지 않고, 매번 원문 URL을 다시
  스크레이핑해서 title/본문을 처음부터 다시 얻는다:
    - IT之家(ithome.com): scraper.scrape_article_title / scrape_article_content
    - Gizmochina: scraper_gizmochina.scrape_article_content (직접 페이지
      스크레이핑 — RSS 피드 24시간 만료와 무관하게 항상 재스크레이핑 가능)

처리 흐름 (기사 1건당):
  1. 현재 파일에서 source-footer 원문 URL, 카테고리 추출
  2. 원문 재스크레이핑 (제목 + 본문)
  3. ko 제목/본문 재번역 (translate_title, translate_article) — 클라우드 API 권장
  4. <title>, title-ko meta, h1 data-ko(+본문 텍스트) 교체
  5. lang-body 4개 div(ko/zh/ja/en) 전체를 새 ko 본문으로 우선 채움
     (html_generator의 --ko-only 저장 방식과 동일 — zh/ja/en 탭은 백필 전까지
     ko 텍스트로 보여서 최소한 "정상 언어"로는 보임)
  6. multilang_backfill_queue.json에 진짜 원문 제목 기반 항목을 등록
     (이후 backfill_multilang.py 실행 시 en/ja/zh 실제 번역으로 교체됨)
  7. logs/recover_from_source_done.log에 기록, N건마다 git commit + push

사용법:
  # ko 재번역 단계는 클라우드 API 사용 권장 (환경변수로 오버라이드):
  export LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=... LLM_EXTRA_BODY=...
  python3 recover_from_source.py [--limit N] [--no-push] [--sleep SEC]

  # 이후 en/ja/zh 백필은 로컬(무료)로:
  python3 backfill_multilang.py
"""
import os
import sys
import re
import time
import json
import html as html_module
import logging
import argparse
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import env_local
env_local.load_env_local()  # config를 import하기 전에 .env.local을 먼저 주입해야 함

# ko 재번역을 클라우드(Gemini)로 — GEMINI_API_KEY가 있으면 config import 전에
# LLM_* 환경변수를 세팅해준다 (config.py는 os.getenv를 import 시점에 평가함).
if os.getenv("GEMINI_API_KEY") and not os.getenv("LLM_API_KEY"):
    os.environ["LLM_API_KEY"] = os.environ["GEMINI_API_KEY"]
    os.environ["LLM_BASE_URL"] = "https://generativelanguage.googleapis.com/v1beta/openai/"
    os.environ["LLM_MODEL"] = "gemini-2.5-flash"
    os.environ["LLM_EXTRA_BODY"] = '{"reasoning_effort": "none"}'

import config
from translator import translate_title, translate_article
from scraper import scrape_article_title, scrape_article_content as scrape_ithome
from scraper_gizmochina import scrape_article_content as scrape_gizmochina

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(config.PRODUCTION_REPO_DIR)
QUEUE_FILE = SCRIPT_DIR / "logs" / "corrupted_multilang_queue.txt"
OLD_DONE_LOG = SCRIPT_DIR / "logs" / "recover_corrupted_done.log"  # 과거 오판 완료 로그 (신뢰 안 함, 대상 목록 합치는 데만 사용)
DONE_LOG = SCRIPT_DIR / "logs" / "recover_from_source_done.log"
FAILED_LOG = SCRIPT_DIR / "logs" / "recover_from_source_failed.log"
BACKFILL_QUEUE_PATH = SCRIPT_DIR / "logs" / "multilang_backfill_queue.json"
BATCH_COMMIT_SIZE = 20


def load_lines(path: Path) -> set:
    if not path.exists():
        return set()
    return set(l.strip() for l in path.read_text().splitlines() if l.strip())


def mark_done(rel_path: str):
    with open(DONE_LOG, "a", encoding="utf-8") as f:
        f.write(rel_path + "\n")


def mark_failed(rel_path: str, reason: str):
    with open(FAILED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{rel_path}\t{reason}\n")


def extract_source_url(html: str) -> str:
    m = re.search(r'class="btn-original"[^>]*href="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'source-footer[\s\S]{0,300}?href="(https?://[^"]+)"', html)
    return m.group(1) if m else ""


def extract_category(html: str) -> str:
    m = re.search(r'<meta name="article-category" content="([^"]*)"', html)
    return m.group(1) if m else ""


def load_backfill_queue() -> list:
    if not BACKFILL_QUEUE_PATH.exists():
        return []
    try:
        return json.loads(BACKFILL_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_backfill_queue(queue: list):
    BACKFILL_QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def _esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def build_lang_body_block(paragraphs: list) -> str:
    """ko/zh/ja/en 4개 div를 전부 같은(ko) 본문으로 채운 블록을 만든다.

    html_generator의 --ko-only 저장 폴백(titles/bodies.get("zh", ...get("ko")))과
    동일한 결과를 만들어, 백필 전까지 다른 언어 탭도 최소한 읽을 수 있는
    상태(한국어 텍스트)로 보이게 한다.
    """
    inner = "\n".join(f"          {p}" for p in paragraphs)
    parts = []
    for lang in ("ko", "zh", "ja", "en"):
        parts.append(f'        <div class="lang-body" data-lang="{lang}">\n{inner}\n        </div>')
    return "\n".join(parts) + "\n      </div>\n\n      "


_LANG_BODY_BLOCK_RE = re.compile(
    r'<div class="lang-body" data-lang="ko">[\s\S]*?(?=<!-- All images)'
)


def patch_ko_content(html: str, ko_title: str, ko_paragraphs: list) -> str:
    # <title>AI시테이 - ...</title>
    html = re.sub(
        r'<title>AI시테이\s*-\s*.*?</title>',
        f'<title>AI시테이 - {_esc_attr(ko_title)}</title>',
        html, count=1,
    )
    # <meta name="title-ko" content="...">
    html = re.sub(
        r'<meta name="title-ko"[^>]*>',
        f'<meta name="title-ko" content="{_esc_attr(ko_title)}">',
        html, count=1,
    )
    # h1 data-ko="..." 속성 + 기본 표시 텍스트
    html = re.sub(
        r'data-ko="[^"]*"',
        f'data-ko="{_esc_attr(ko_title)}"',
        html, count=1,
    )
    html = re.sub(
        r'(<h1[^>]*class="article-title"[^>]*>)([\s\S]*?)(</h1>)',
        lambda m: m.group(1) + _esc_attr(ko_title) + m.group(3),
        html, count=1,
    )
    # lang-body 4개 div 전체 교체 (ko 내용으로 우선 채움)
    html = _LANG_BODY_BLOCK_RE.sub(lambda m: build_lang_body_block(ko_paragraphs), html, count=1)
    return html


def process_one(rel_path: str) -> bool:
    html_path = REPO_ROOT / rel_path
    if not html_path.exists():
        mark_failed(rel_path, "file_not_found")
        return False

    html = html_path.read_text(encoding="utf-8", errors="replace")
    source_url = extract_source_url(html)
    if not source_url:
        mark_failed(rel_path, "no_source_url")
        return False

    is_gizmochina = "gizmochina.com" in source_url
    source = "gizmochina" if is_gizmochina else "ithome"
    category = extract_category(html)

    # ── 원문 재스크레이핑 ──
    if is_gizmochina:
        paragraphs, original_title = scrape_gizmochina(source_url)
        source_lang = "en"
    else:
        paragraphs, _author = scrape_ithome(source_url)
        original_title = scrape_article_title(source_url)
        source_lang = "zh"

    if not paragraphs or not original_title:
        mark_failed(rel_path, f"scrape_failed(paragraphs={len(paragraphs)},title={bool(original_title)})")
        return False

    # ── ko 재번역 ──
    ko_title = translate_title(original_title, category=category, source_lang=source_lang)
    if not ko_title:
        mark_failed(rel_path, "ko_title_translate_failed")
        return False
    ko_paragraphs = translate_article(paragraphs, category=category, source_lang=source_lang)
    if not ko_paragraphs:
        mark_failed(rel_path, "ko_body_translate_failed")
        return False

    # ── 파일 패치 (ko + 4개 div 폴백) ──
    patched = patch_ko_content(html, ko_title, ko_paragraphs)
    html_path.write_text(patched, encoding="utf-8")

    # ── 백필 큐 등록 (en/ja/zh는 이후 backfill_multilang.py가 처리) ──
    article_dir = str(Path(rel_path).parent)
    backfill_queue = load_backfill_queue()
    if not any(e["article_dir"] == article_dir for e in backfill_queue):
        backfill_queue.append({
            "article_dir": article_dir,
            "category": category,
            "source": source,
            "title": original_title,
            "korean_title": ko_title,
            "korean_paragraphs": ko_paragraphs,
            "url": source_url,
        })
        save_backfill_queue(backfill_queue)

    return True


def git_commit_push(paths: list, no_push: bool):
    try:
        subprocess.run(["git", "-C", str(REPO_ROOT), "add"] + paths, check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit", "-m", f"fix: 손상된 기사 ko 재번역(원문 재스크레이핑) {len(paths)}건"],
            check=True, capture_output=True,
        )
        logger.info(f"git commit: {len(paths)}건")
        if not no_push:
            subprocess.run(["git", "-C", str(REPO_ROOT), "push"], check=True, capture_output=True)
            logger.info("git push 완료")
    except subprocess.CalledProcessError as e:
        logger.warning(f"git 오류: {e.stderr.decode(errors='replace')[:300]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--sleep", type=float, default=1.0, help="원문 사이트 요청 사이 대기(초)")
    args = parser.parse_args()

    queue_pending = load_lines(QUEUE_FILE)
    queue_old_done = load_lines(OLD_DONE_LOG)  # 과거 오판 완료 — 신뢰 못 하므로 대상에 다시 포함
    already_recovered = load_lines(DONE_LOG)   # 이 스크립트로 이미 처리한 것만 진짜로 스킵

    targets = sorted((queue_pending | queue_old_done) - already_recovered)
    if args.limit > 0:
        targets = targets[: args.limit]

    logger.info(f"대상: {len(targets)}건 (신규+과거오판 합계, 이번 스크립트로 이미 처리한 것 제외)")

    commit_buf = []
    ok_count = 0
    fail_count = 0

    for i, rel_path in enumerate(targets, 1):
        logger.info(f"[{i}/{len(targets)}] {rel_path}")
        try:
            ok = process_one(rel_path)
        except Exception as e:
            logger.error(f"예외 발생: {rel_path} — {e}")
            mark_failed(rel_path, f"exception: {e}")
            ok = False

        if ok:
            mark_done(rel_path)
            commit_buf.append(str(REPO_ROOT / rel_path))
            ok_count += 1
        else:
            fail_count += 1

        if len(commit_buf) >= BATCH_COMMIT_SIZE:
            git_commit_push(commit_buf, args.no_push)
            commit_buf = []

        time.sleep(args.sleep)

    if commit_buf:
        git_commit_push(commit_buf, args.no_push)

    logger.info(f"완료. 성공 {ok_count}건, 실패 {fail_count}건.")


if __name__ == "__main__":
    main()
