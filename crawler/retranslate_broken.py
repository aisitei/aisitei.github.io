#!/usr/bin/env python3
"""
retranslate_broken.py — zh 번역 오류 기사 재처리 스크립트.

사용법:
  python3 retranslate_broken.py [--no-push]

처리 흐름:
  1. crawler/logs/retranslate_queue2.txt 에서 대상 기사 목록 로드
  2. already_multilang 체크 우회하여 강제 재처리
  3. 완료된 항목은 retranslate_done2.log에 기록
  4. 20건마다 git commit
"""
import sys
import logging
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import multilang_reprocess as m

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

QUEUE_FILE = SCRIPT_DIR / "logs" / "retranslate_queue2.txt"
DONE_LOG = SCRIPT_DIR / "logs" / "retranslate_done2.log"
BATCH_COMMIT_SIZE = 20


def load_done() -> set:
    if not DONE_LOG.exists():
        return set()
    return set(DONE_LOG.read_text().splitlines())


def mark_done(path: str):
    with open(DONE_LOG, "a") as f:
        f.write(path + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    queue = [l.strip() for l in QUEUE_FILE.read_text().splitlines() if l.strip()]
    done = load_done()
    pending = [f for f in queue if f not in done]

    logger.info(f"재처리 대상: {len(pending)}건 (전체 {len(queue)}건, 완료 {len(done)}건)")

    # already_multilang 체크 우회
    m.already_multilang = lambda html: False

    commit_buf = []

    for i, rel_path in enumerate(pending, 1):
        html_path = Path(m.REPO_ROOT) / rel_path
        if not html_path.exists():
            logger.warning(f"파일 없음: {rel_path}")
            mark_done(rel_path)
            continue

        logger.info(f"[{i}/{len(pending)}] {rel_path}")
        try:
            result = m.process_article(html_path)
        except Exception as e:
            logger.error(f"처리 실패: {rel_path} — {e}")
            continue

        if result:
            mark_done(rel_path)
            commit_buf.append(str(html_path))

        if len(commit_buf) >= BATCH_COMMIT_SIZE:
            m.git_add_commit(commit_buf, f"fix: zh 재번역 {BATCH_COMMIT_SIZE}건")
            commit_buf.clear()

    if commit_buf:
        m.git_add_commit(commit_buf, f"fix: zh 재번역 최종 {len(commit_buf)}건")

    if not args.no_push:
        m.git_push()

    logger.info("완료.")


if __name__ == "__main__":
    main()
