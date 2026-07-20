#!/usr/bin/env python3
"""
recover_corrupted_multilang.py — ko lang-body 오염(4개 언어 콘텐츠 혼입) 기사 복구 스크립트.

배경:
  retranslate_broken.py의 강제 재처리가 multilang_reprocess.py의 두 버그
  (extract_ko_body_paragraphs 과도 캡처, patch_html 이중 래핑)로 인해
  ko lang-body에 ko+zh+ja+en 콘텐츠가 전부 섞여 저장되는 손상을 일으켰음.
  두 버그는 수정됐지만 이미 손상된 파일 자체는 복구되지 않음.

처리 흐름:
  1. crawler/logs/corrupted_multilang_queue.txt 에서 대상 기사 목록 로드
  2. 각 파일의 git 히스토리에서 손상되기 전 마지막 커밋을 찾아 그 내용으로 복원
  3. 수정된 multilang_reprocess.process_article()로 재번역 (already_multilang 우회)
  4. 완료된 항목은 recover_corrupted_done.log에 기록
  5. 20건마다 git commit + push

사용법:
  python3 recover_corrupted_multilang.py [--no-push] [--limit N]
"""
import sys
import re
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import multilang_reprocess as m

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

QUEUE_FILE = SCRIPT_DIR / "logs" / "corrupted_multilang_queue.txt"
DONE_LOG = SCRIPT_DIR / "logs" / "recover_corrupted_done.log"
FAILED_LOG = SCRIPT_DIR / "logs" / "recover_corrupted_failed.log"
BATCH_COMMIT_SIZE = 20

_CORRUPTION_PATTERN = re.compile(
    r'<div class="lang-body" data-lang="ko">\s*<!-- lang-body: ko -->'
)


def load_done() -> set:
    if not DONE_LOG.exists():
        return set()
    return set(DONE_LOG.read_text().splitlines())


def mark_done(path: str):
    with open(DONE_LOG, "a") as f:
        f.write(path + "\n")


def mark_failed(path: str, reason: str):
    with open(FAILED_LOG, "a") as f:
        f.write(f"{path}\t{reason}\n")


def find_last_good_content(rel_path: str) -> Optional[str]:
    """git 히스토리에서 오염 패턴이 없는 가장 최근 버전의 내용을 반환."""
    result = subprocess.run(
        ["git", "-C", str(m.REPO_ROOT), "log", "--format=%H", "--", rel_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    commits = [c for c in result.stdout.splitlines() if c.strip()]
    for commit in commits:
        show = subprocess.run(
            ["git", "-C", str(m.REPO_ROOT), "show", f"{commit}:{rel_path}"],
            capture_output=True, text=True,
        )
        if show.returncode != 0:
            continue
        content = show.stdout
        if content.strip() and not _CORRUPTION_PATTERN.search(content):
            return content
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    queue = [l.strip() for l in QUEUE_FILE.read_text().splitlines() if l.strip()]
    done = load_done()
    pending = [f for f in queue if f not in done]
    if args.limit > 0:
        pending = pending[: args.limit]

    logger.info(f"복구 대상: {len(pending)}건 (전체 {len(queue)}건, 완료 {len(done)}건)")

    # already_multilang 체크 우회 (강제 재처리)
    m.already_multilang = lambda html: False

    commit_buf = []

    for i, rel_path in enumerate(pending, 1):
        html_path = Path(m.REPO_ROOT) / rel_path
        logger.info(f"[{i}/{len(pending)}] {rel_path}")

        good_content = find_last_good_content(rel_path)
        if good_content is None:
            logger.warning(f"손상 이전 정상 버전 못 찾음: {rel_path}")
            mark_failed(rel_path, "no_good_commit_found")
            continue

        html_path.write_text(good_content, encoding="utf-8")

        try:
            result = m.process_article(html_path)
        except Exception as e:
            logger.error(f"처리 실패: {rel_path} — {e}")
            mark_failed(rel_path, f"process_error: {e}")
            continue

        if result:
            mark_done(rel_path)
            commit_buf.append(str(html_path))
        else:
            mark_failed(rel_path, "process_article_returned_false")

        if len(commit_buf) >= BATCH_COMMIT_SIZE:
            m.git_add_commit(commit_buf, f"fix: 손상된 multilang 기사 복구 {len(commit_buf)}건")
            commit_buf.clear()
            if not args.no_push:
                m.git_push()

    if commit_buf:
        m.git_add_commit(commit_buf, f"fix: 손상된 multilang 기사 복구 최종 {len(commit_buf)}건")
        if not args.no_push:
            m.git_push()

    logger.info("복구 완료.")


if __name__ == "__main__":
    main()
