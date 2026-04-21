#!/usr/bin/env python3
"""
run_report.py — 리포트 생성 파이프라인 오케스트레이터
=====================================================
YouTube URL을 입력받아 전체 파이프라인을 순차 실행한다.

실행 순서:
  step1_transcribe.py       → 자막/음성 전사
  step2_preprocess.py       → 전처리 (환각 제거, 섹션 분류, 스크린샷 후보)
  step2b_bilingual.py       → 한국어 번역 (빌링구얼 트랜스크립트)
  step2c_merge.py           → 완성 문장 병합
  step2d_suggest.py         → LLM 기반 스크린샷 후보 재추천
  step3_screenshots.py      → 영상 다운로드 + 스크린샷 캡쳐
  step4_report.py           → HTML 리포트 생성

출력:
  reports/YYYY-MM-DD-brand-slug/report.html

사용법:
  python3 run_report.py <youtube_url> [--model MODEL] [--api-url URL]
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import date


PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_API_URL = "http://localhost:1234/v1"


# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────

def run_step(name: str, cmd: list, cwd: str = None) -> None:
    """서브프로세스로 파이프라인 스텝 실행. 실패 시 종료."""
    print(f"\n{'─'*60}")
    print(f"▶  {name}")
    print(f"{'─'*60}")
    result = subprocess.run(cmd, cwd=cwd or PIPELINE_DIR)
    if result.returncode != 0:
        print(f"\n❌ {name} 실패 (returncode={result.returncode})")
        sys.exit(result.returncode)
    print(f"✅ {name} 완료")


def check_lm_studio(api_url: str) -> None:
    """LM Studio가 실행 중인지 확인."""
    import urllib.request
    import urllib.error
    url = f"{api_url.rstrip('/')}/models"
    print(f"  LM Studio 연결 확인: {url}")
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer lm-studio"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["id"] for m in data.get("data", [])]
            print(f"  ✓ LM Studio 응답 OK — 모델: {', '.join(models) or '(없음)'}")
    except urllib.error.URLError as e:
        print(f"\n❌ LM Studio에 연결할 수 없습니다: {e}")
        print("   LM Studio를 실행하고 모델을 로드한 다음 다시 시도하세요.")
        print(f"   설정: {api_url}")
        sys.exit(1)
    except Exception as e:
        print(f"  ⚠️  LM Studio 확인 중 오류 (진행): {e}")


def slugify(text: str) -> str:
    """제목을 URL-safe ASCII slug로 변환. 비ASCII 문자는 제거."""
    text = text.lower().strip()
    # 비ASCII 문자(한글, 중국어 등) 제거
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:50].strip("-")


def detect_brand(title: str) -> str:
    """영상 제목에서 브랜드명 추출."""
    brands = [
        "samsung", "apple", "xiaomi", "oppo", "vivo", "oneplus", "huawei",
        "google", "sony", "lg", "motorola", "realme", "nothing", "asus",
        "lenovo", "honor", "tecno", "infinix",
        "삼성", "애플", "샤오미", "오포", "비보", "화웨이", "구글", "소니",
    ]
    lower = title.lower()
    for brand in brands:
        if brand in lower:
            return brand.replace(" ", "-")
    # 첫 단어를 브랜드로 간주
    first = re.split(r"[\s|]", title.strip())[0]
    return slugify(first)[:20] or "brand"


def make_report_dir(base_dir: str, title: str) -> str:
    """보고서 디렉토리 경로 생성: reports/YYYY-MM-DD-brand-slug/"""
    today = date.today().strftime("%Y-%m-%d")
    brand = detect_brand(title)
    # 제목 핵심 단어 포함
    title_slug = slugify(title)
    # brand가 이미 slug 안에 있으면 중복 제거
    if title_slug.startswith(brand):
        dir_name = f"{today}-{title_slug}"
    else:
        dir_name = f"{today}-{brand}-{title_slug}"
    # 최대 길이 제한
    dir_name = dir_name[:80]
    return os.path.join(base_dir, "reports", dir_name)


def load_meta(report_dir: str) -> dict:
    """meta.json에서 영상 메타데이터 로드."""
    meta_path = os.path.join(report_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def cleanup_work_files(report_dir: str) -> None:
    """임시 작업 파일 정리 (영상 파일 등)."""
    work_dir = os.path.join(report_dir, ".work")
    if not os.path.isdir(work_dir):
        return
    removed = []
    for pattern in ["video_raw.*", "*.mp4", "*.mkv", "*.webm"]:
        for f in glob.glob(os.path.join(work_dir, pattern)):
            try:
                size_mb = os.path.getsize(f) / 1024 / 1024
                os.remove(f)
                removed.append(f"{os.path.basename(f)} ({size_mb:.0f}MB)")
            except OSError:
                pass
    if removed:
        print(f"\n  🧹 임시 파일 삭제: {', '.join(removed)}")


def suggest_commit_message(report_dir: str, youtube_url: str, meta: dict) -> None:
    """Git 커밋 메시지 추천 출력."""
    title = meta.get("title", "Unknown Video")
    rel_path = os.path.relpath(report_dir)
    today = date.today().strftime("%Y-%m-%d")
    brand = detect_brand(title)

    print(f"\n{'═'*60}")
    print("📋 추천 Git 커밋 메시지")
    print(f"{'═'*60}")
    print()
    print(f"git add {rel_path}/")
    print()
    print("git commit -m \"$(cat <<'EOF'")
    print(f"report: {brand.capitalize()} — {title[:60]}")
    print()
    print(f"- YouTube: {youtube_url}")
    print(f"- 날짜: {today}")
    print(f"- 출력: {rel_path}/report.html")
    print()
    print("Co-Authored-By: Claude Sonnet <noreply@anthropic.com>")
    print("EOF")
    print(")\"")
    print()


def print_summary(report_dir: str, meta: dict, elapsed: float) -> None:
    """최종 완료 요약 출력."""
    report_html = os.path.join(report_dir, "report.html")
    images_dir = os.path.join(report_dir, "images")
    img_count = len(glob.glob(os.path.join(images_dir, "screenshot_*.jpg"))) if os.path.isdir(images_dir) else 0

    print(f"\n{'═'*60}")
    print("🎉 리포트 생성 완료!")
    print(f"{'═'*60}")
    print(f"  영상 제목 : {meta.get('title', 'N/A')}")
    print(f"  출력 경로 : {report_html}")
    print(f"  스크린샷  : {img_count}개")
    print(f"  소요 시간 : {elapsed/60:.1f}분")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="YouTube 영상 → 리포트 생성 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python3 run_report.py https://youtu.be/XXXX
  python3 run_report.py https://youtu.be/XXXX --model gemma4:e4b
  python3 run_report.py https://youtu.be/XXXX --skip-screenshots
        """
    )
    ap.add_argument("youtube_url", help="YouTube 영상 URL")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"LM Studio 모델명 (기본: {DEFAULT_MODEL})")
    ap.add_argument("--api-url", default=DEFAULT_API_URL,
                    help=f"LM Studio API URL (기본: {DEFAULT_API_URL})")
    ap.add_argument("--api-key", default="lm-studio",
                    help="LM Studio API 키 (기본: lm-studio)")
    ap.add_argument("--output-dir", default=None,
                    help="출력 디렉토리 (기본: 자동 생성)")
    ap.add_argument("--skip-screenshots", action="store_true",
                    help="스크린샷 캡쳐 건너뜀 (step3)")
    ap.add_argument("--force", action="store_true",
                    help="이미 완료된 스텝도 재실행")
    ap.add_argument("--no-cleanup", action="store_true",
                    help="영상 파일 자동 삭제 안 함")
    args = ap.parse_args()

    youtube_url = args.youtube_url
    repo_root = os.path.dirname(PIPELINE_DIR)

    print(f"\n{'═'*60}")
    print("🚀 리포트 생성 파이프라인 시작")
    print(f"{'═'*60}")
    print(f"  URL    : {youtube_url}")
    print(f"  모델   : {args.model}")
    print(f"  API    : {args.api_url}")

    t_start = time.time()

    # ── 0. LM Studio 연결 확인 ──────────────────────
    check_lm_studio(args.api_url)

    # ── 1. Step1: 전사 (제목 알기 전에 실행) ────────
    # 출력 디렉토리를 먼저 결정하기 위해 yt-dlp로 메타만 가져오거나
    # step1이 meta.json을 생성하면 그 후에 디렉토리를 확정한다.
    # 전략: 임시 디렉토리에 step1 실행 → meta.json 읽기 → 최종 경로로 이동

    if args.output_dir:
        report_dir = os.path.abspath(args.output_dir)
        os.makedirs(report_dir, exist_ok=True)
        print(f"  출력   : {report_dir}")
    else:
        # 임시로 title을 먼저 가져온다
        print("\n  영상 제목 조회 중...")
        try:
            result = subprocess.run(
                ["yt-dlp", "--no-check-certificates", "--print", "title", youtube_url],
                capture_output=True, text=True, timeout=30
            )
            video_title = result.stdout.strip() if result.returncode == 0 else "unknown-video"
        except Exception:
            video_title = "unknown-video"
        print(f"  제목   : {video_title}")
        report_dir = make_report_dir(repo_root, video_title)
        os.makedirs(report_dir, exist_ok=True)
        print(f"  출력   : {report_dir}")

    # ── Step 1: 자막 / 전사 ──────────────────────────
    force_flag = ["--force"] if args.force else []
    run_step(
        "Step 1 — 자막/전사",
        [sys.executable, os.path.join(PIPELINE_DIR, "step1_transcribe.py"),
         youtube_url, report_dir] + force_flag,
    )

    # meta.json에서 제목 읽기 (디렉토리 이름 확정용)
    meta = load_meta(report_dir)
    if meta.get("title") and not args.output_dir:
        # 제목이 바뀌었을 경우 디렉토리 재조정
        proper_dir = make_report_dir(repo_root, meta["title"])
        if proper_dir != report_dir and not os.path.exists(proper_dir):
            import shutil
            shutil.move(report_dir, proper_dir)
            report_dir = proper_dir
            print(f"\n  📁 출력 경로 확정: {report_dir}")
        elif os.path.exists(proper_dir):
            report_dir = proper_dir

    # ── Step 2: 전처리 ───────────────────────────────
    run_step(
        "Step 2 — 전처리 (환각 제거 / 섹션 분류 / 스크린샷 후보)",
        [sys.executable, os.path.join(PIPELINE_DIR, "step2_preprocess.py"),
         report_dir] + force_flag,
    )

    # ── Step 2b: 빌링구얼 번역 ───────────────────────
    run_step(
        "Step 2b — 한국어 번역 (빌링구얼 트랜스크립트)",
        [sys.executable, os.path.join(PIPELINE_DIR, "step2b_bilingual.py"),
         report_dir,
         "--model", args.model,
         "--api-url", args.api_url,
         "--api-key", args.api_key,
         ] + force_flag,
    )

    # ── Step 2c: 완성 문장 병합 ──────────────────────
    run_step(
        "Step 2c — 완성 문장 병합 (merged_transcript)",
        [sys.executable, os.path.join(PIPELINE_DIR, "step2c_merge.py"),
         report_dir,
         "--model", args.model,
         "--api-url", args.api_url,
         "--api-key", args.api_key,
         ] + force_flag,
    )

    # ── Step 2d: LLM 스크린샷 후보 재추천 ───────────
    run_step(
        "Step 2d — LLM 스크린샷 후보 추천",
        [sys.executable, os.path.join(PIPELINE_DIR, "step2d_suggest.py"),
         report_dir,
         "--model", args.model,
         "--api-url", args.api_url,
         "--api-key", args.api_key,
         ] + force_flag,
    )

    # ── Step 3: 스크린샷 캡쳐 ───────────────────────
    if not args.skip_screenshots:
        suggestions_file = os.path.join(report_dir, "screenshot_suggestions.txt")
        images_dir = os.path.join(report_dir, "images")
        run_step(
            "Step 3 — 스크린샷 캡쳐 (yt-dlp + ffmpeg)",
            [sys.executable, os.path.join(PIPELINE_DIR, "step3_screenshots.py"),
             youtube_url, suggestions_file, images_dir],
        )
        # 영상 파일 정리
        if not args.no_cleanup:
            cleanup_work_files(report_dir)
    else:
        print("\n  ⏭  Step 3 건너뜀 (--skip-screenshots)")

    # ── Step 4: 리포트 생성 ──────────────────────────
    run_step(
        "Step 4 — HTML 리포트 생성",
        [sys.executable, os.path.join(PIPELINE_DIR, "step4_report.py"),
         report_dir,
         "--model", args.model,
         "--api-url", args.api_url,
         "--api-key", args.api_key,
         ] + force_flag,
    )

    # ── 완료 요약 ────────────────────────────────────
    elapsed = time.time() - t_start
    meta = load_meta(report_dir)  # 재로드
    print_summary(report_dir, meta, elapsed)
    suggest_commit_message(report_dir, youtube_url, meta)


if __name__ == "__main__":
    main()
