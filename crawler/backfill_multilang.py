#!/usr/bin/env python3
"""
backfill_multilang.py — --ko-only 모드로 저장된 기사에 EN/JA/ZH 번역을 채우는 후처리 스크립트.

배경:
  main.py --ko-only는 한국어만 번역해 즉시 저장/푸시하고(클라우드 API 비용 절감),
  EN/JA/ZH 탭은 html_generator의 기존 폴백으로 일단 한국어 텍스트를 보여준다.
  이 스크립트가 logs/multilang_backfill_queue.json을 읽어 실제 EN/JA/ZH
  번역을 만들어 저장된 HTML을 패치한다.

  이 스크립트는 보통 로컬 LM Studio(무료)로 돌리는 걸 의도함 — main.py --ko-only를
  클라우드 API 환경변수로 실행했다면, 이 스크립트는 그 환경변수 없이(=로컬 기본값)
  실행해야 비용 절감 효과가 있다.

사용법:
  python3 backfill_multilang.py [--no-push] [--limit N]
"""
import sys
import os
import re
import json
import argparse
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import config
from translator import (
    translate_body_en, translate_body_ja, translate_body_zh, translate_body_zh_summary,
    translate_title_en, translate_title_ja, translate_title_zh,
)
from scraper import scrape_article_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

QUEUE_PATH = SCRIPT_DIR / "logs" / "multilang_backfill_queue.json"
DONE_LOG = SCRIPT_DIR / "logs" / "multilang_backfill_done.log"
BATCH_COMMIT_SIZE = 10


def _esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def load_queue() -> list:
    if not QUEUE_PATH.exists():
        return []
    try:
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_done() -> set:
    if not DONE_LOG.exists():
        return set()
    return set(DONE_LOG.read_text(encoding="utf-8").splitlines())


def mark_done(article_dir: str):
    with open(DONE_LOG, "a", encoding="utf-8") as f:
        f.write(article_dir + "\n")


def build_lang_body_inner(paragraphs: list) -> str:
    return "\n".join(f"          {p}" for p in paragraphs)


def patch_article(entry: dict, repo_root: Path) -> bool:
    article_dir = entry["article_dir"]
    html_path = repo_root / article_dir / "index.html"
    if not html_path.exists():
        logger.warning(f"파일 없음: {html_path}")
        return False

    html = html_path.read_text(encoding="utf-8", errors="replace")

    category = entry.get("category", "")
    source = entry.get("source", "ithome")
    source_lang = "en" if source == "gizmochina" else "zh"
    original_title = entry["title"]
    korean_title = entry["korean_title"]
    korean_paragraphs = entry["korean_paragraphs"]

    ko_body_text = "\n\n".join(korean_paragraphs)

    logger.info("  [백필] EN 번역 중...")
    en_body_text = translate_body_en(ko_body_text, category=category)
    en_paragraphs = [p.strip() for p in (en_body_text or "").split("\n\n") if p.strip()] or korean_paragraphs

    logger.info("  [백필] JA 번역 중...")
    ja_body_text = translate_body_ja(ko_body_text, category=category)
    ja_paragraphs = [p.strip() for p in (ja_body_text or "").split("\n\n") if p.strip()] or korean_paragraphs

    logger.info("  [백필] ZH 요약 중...")
    if source_lang == "zh":
        # IT之家 원문(중국어)을 다시 스크레이핑해 실제 원문 기반 요약을 만든다.
        try:
            zh_paragraphs_raw, _ = scrape_article_content(entry["url"])
            zh_orig_text = "\n\n".join(zh_paragraphs_raw) if zh_paragraphs_raw else ko_body_text
        except Exception as e:
            logger.warning(f"원문 재스크레이핑 실패({e}), 한국어 기반으로 대체")
            zh_orig_text = ko_body_text
        zh_summary_text = translate_body_zh_summary(zh_orig_text)
    else:
        zh_summary_text = translate_body_zh(ko_body_text)
    zh_paragraphs = [p.strip() for p in (zh_summary_text or "").split("\n\n") if p.strip()] or korean_paragraphs

    if source_lang == "zh":
        zh_title = original_title
        en_title = translate_title_en(original_title)
        ja_title = translate_title_ja(original_title)
    else:
        zh_title = translate_title_zh(korean_title)
        en_title = original_title
        ja_title = translate_title_ja(zh_title or korean_title)

    titles = {
        "zh": zh_title or korean_title,
        "ja": ja_title or korean_title,
        "en": en_title or korean_title,
    }
    bodies = {
        "zh": zh_paragraphs,
        "ja": ja_paragraphs,
        "en": en_paragraphs,
    }

    # 1) title-xx 메타 태그 교체
    for lang in ("zh", "ja", "en"):
        html = re.sub(
            rf'<meta name="title-{lang}"[^>]*>',
            f'<meta name="title-{lang}" content="{_esc_attr(titles[lang])}">',
            html, count=1,
        )

    # 2) h1 data-xx 속성 교체
    for lang in ("zh", "ja", "en"):
        html = re.sub(
            rf'data-{lang}="[^"]*"',
            f'data-{lang}="{_esc_attr(titles[lang])}"',
            html, count=1,
        )

    # 3) lang-body 내부 콘텐츠 교체 (fallback 한국어 → 실제 번역)
    for lang in ("zh", "ja", "en"):
        inner = build_lang_body_inner(bodies[lang])
        html = re.sub(
            r'(<div class="lang-body" data-lang="' + lang + r'">)[\s\S]*?(</div>)',
            lambda m, inner=inner: m.group(1) + "\n" + inner + "\n        " + m.group(2),
            html, count=1,
        )

    html_path.write_text(html, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    queue = load_queue()
    done = load_done()
    pending = [e for e in queue if e["article_dir"] not in done]
    if args.limit > 0:
        pending = pending[: args.limit]

    logger.info(f"백필 대상: {len(pending)}건 (전체 큐 {len(queue)}건, 완료 {len(done)}건)")

    repo_root = Path(config.PRODUCTION_REPO_DIR)
    commit_buf = []

    for i, entry in enumerate(pending, 1):
        logger.info(f"[{i}/{len(pending)}] {entry['article_dir']}")
        try:
            ok = patch_article(entry, repo_root)
        except Exception as e:
            logger.error(f"실패: {entry['article_dir']} — {e}")
            continue

        if ok:
            mark_done(entry["article_dir"])
            commit_buf.append(str(repo_root / entry["article_dir"]))

        if len(commit_buf) >= BATCH_COMMIT_SIZE:
            _commit_and_push(repo_root, commit_buf, args.no_push)
            commit_buf = []

    if commit_buf:
        _commit_and_push(repo_root, commit_buf, args.no_push)

    logger.info("백필 완료.")


def _commit_and_push(repo_root: Path, paths: list, no_push: bool):
    import subprocess
    from deployer import run_build

    # index.html의 카드 data-ko/zh/ja/en은 build.py가 각 기사 파일에서 직접
    # 추출해 굽는 값이라, 여기서 en/ja/zh 본문을 patch만 하고 build.py를 다시
    # 안 돌리면 인덱스 페이지는 계속 ko 전용(백필 전) 상태로 스테일하게 남는다
    # (Phase A의 deployer.commit_and_push는 build.py를 이미 돌리지만, 이
    # Phase B 전용 push 경로는 그걸 안 타서 발견된 회귀).
    run_build(repo_root)

    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "add"] + paths + ["index.html", "reports.html"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "commit", "-m", f"feat: EN/JA/ZH 백필 {len(paths)}건"],
            check=True, capture_output=True,
        )
        logger.info(f"git commit: {len(paths)}건")
        if not no_push:
            subprocess.run(["git", "-C", str(repo_root), "push"], check=True, capture_output=True)
            logger.info("git push 완료")
    except subprocess.CalledProcessError as e:
        logger.warning(f"git 오류: {e.stderr.decode()[:300]}")


if __name__ == "__main__":
    main()
