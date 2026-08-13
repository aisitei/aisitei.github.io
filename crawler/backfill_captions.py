#!/usr/bin/env python3
"""
backfill_captions.py — 이미 저장된 기사의 로컬 이미지에 Tesseract OCR로 캡션을 새로 붙이는 후처리 스크립트.

배경:
  vision-LLM OCR로 처리된 기사들의 캡션을 Tesseract 기반으로 다시 만들어
  기존 캡션(있으면 교체, 없으면 신규 추가)을 붙인다. 이미 저장된 index.html을
  직접 패치하므로 재번역/재생성 없이 캡션만 갈아끼운다.

사용법:
  python3 backfill_captions.py articles/2026-08/2026-08-13/*/index.html
  python3 backfill_captions.py --glob "articles/2026-08/2026-08-13/*/index.html"
"""
import sys
import re
import glob
import argparse
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import ocr
import translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_caption_html(translations: list) -> str:
    """ImageTranslation 리스트를 templates/article.html과 동일한 figcaption 마크업으로 렌더링."""
    pairs = []
    for t in translations:
        if not (t.translated_korean or t.translated_english or t.translated_japanese):
            continue
        lines = []
        if t.translated_korean:
            lines.append(f'                <div class="caption-lang" data-lang="ko">{t.translated_korean}</div>')
        if t.translated_english:
            lines.append(f'                <div class="caption-lang" data-lang="en">{t.translated_english}</div>')
        if t.translated_japanese:
            lines.append(f'                <div class="caption-lang" data-lang="ja">{t.translated_japanese}</div>')
        pairs.append("              <div class=\"caption-pair\">\n" + "\n".join(lines) + "\n              </div>")
    if not pairs:
        return ""
    body = "\n".join(pairs)
    return (
        "\n          <figcaption class=\"image-caption\">\n"
        f"{body}\n"
        "          </figcaption>\n          "
    )


def process_article(html_path: Path) -> bool:
    html = html_path.read_text(encoding="utf-8", errors="replace")
    images_dir = html_path.parent / "images"
    if not images_dir.is_dir():
        return False

    # index.html에 실제로 참조된 이미지 파일만 처리 (순서 보존)
    img_srcs = re.findall(r'<div class="image-item">\s*<img src="([^"]+)"', html)
    if not img_srcs:
        return False

    changed = False
    for src in img_srcs:
        local_path = html_path.parent / src
        if not local_path.exists():
            continue
        try:
            img_bytes = local_path.read_bytes()
        except OSError:
            continue

        raw_text = ocr.call_tesseract_ocr(img_bytes)
        if not raw_text:
            continue
        sentences = ocr._filter_caption_lines(raw_text)
        if not sentences:
            continue

        translations = []
        for sentence in sentences:
            korean = translator.translate_caption(sentence)
            if korean:
                english = translator.translate_caption_en(sentence)
                japanese = translator.translate_caption_ja(sentence)
                translations.append(ocr.ImageTranslation(
                    original_chinese=sentence,
                    translated_korean=korean,
                    translated_english=english or "",
                    translated_japanese=japanese or "",
                ))

        caption_html = build_caption_html(translations)
        if not caption_html:
            continue

        # 해당 이미지의 image-item 블록에서 기존 figcaption(있으면) 교체, 없으면 </div> 직전에 삽입
        escaped_src = re.escape(src)
        pattern_with_cap = re.compile(
            r'(<div class="image-item">\s*<img src="' + escaped_src + r'"[^>]*>)'
            r'\s*<figcaption class="image-caption">[\s\S]*?</figcaption>\s*(</div>)'
        )
        pattern_without_cap = re.compile(
            r'(<div class="image-item">\s*<img src="' + escaped_src + r'"[^>]*>)\s*(</div>)'
        )

        if pattern_with_cap.search(html):
            html = pattern_with_cap.sub(lambda m: m.group(1) + caption_html + m.group(2), html, count=1)
            changed = True
            logger.info(f"  캡션 교체: {src} ({len(translations)}건)")
        elif pattern_without_cap.search(html):
            html = pattern_without_cap.sub(lambda m: m.group(1) + caption_html + m.group(2), html, count=1)
            changed = True
            logger.info(f"  캡션 추가: {src} ({len(translations)}건)")

    if changed:
        html_path.write_text(html, encoding="utf-8")
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="index.html 경로들 (glob 확장된 상태)")
    parser.add_argument("--glob", dest="glob_pattern", help="glob 패턴 (쉘 확장 없이 직접 전달)")
    args = parser.parse_args()

    paths = list(args.paths)
    if args.glob_pattern:
        paths.extend(glob.glob(args.glob_pattern))

    if not paths:
        logger.error("처리할 index.html 경로가 없습니다.")
        return

    total_changed = 0
    for p in paths:
        html_path = Path(p)
        logger.info(f"처리 중: {html_path}")
        try:
            if process_article(html_path):
                total_changed += 1
        except Exception as e:
            logger.error(f"실패: {html_path} — {e}")

    logger.info(f"완료. {total_changed}/{len(paths)}건 캡션 변경됨.")


if __name__ == "__main__":
    main()
