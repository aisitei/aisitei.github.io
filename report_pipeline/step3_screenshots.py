#!/usr/bin/env python3
"""
step3_screenshots.py — YouTube 영상 스크린캡쳐 추출
===================================================
screenshot_suggestions.txt를 읽어 ffmpeg로 일괄 캡쳐합니다.

사용법:
    python3 step3_screenshots.py <youtube_url> <suggestions_file> <images_dir>
"""

import sys
import os
import subprocess
import re
import time
import glob


def get_local_video(youtube_url: str, work_dir: str) -> str:
    """yt-dlp로 720p 이하 영상 다운로드. 이미 있으면 재사용."""
    existing = glob.glob(os.path.join(work_dir, "video_raw.*"))
    if existing:
        print(f"  ✓ 기존 영상 파일 재사용: {os.path.basename(existing[0])}")
        return existing[0]

    print("  영상 다운로드 중 (스크린캡쳐용, 720p 이하)...")
    out_tmpl = os.path.join(work_dir, "video_raw.%(ext)s")

    result = subprocess.run(
        ["yt-dlp",
         "-f", "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]/best[height<=720][ext=mp4]/best[height<=720]",
         "--no-check-certificates",
         "-o", out_tmpl, youtube_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  yt-dlp 오류: {result.stderr[:300]}")
        sys.exit(1)

    files = glob.glob(os.path.join(work_dir, "video_raw.*"))
    if not files:
        print("  영상 파일을 찾을 수 없습니다.")
        sys.exit(1)

    size_mb = os.path.getsize(files[0]) / 1024 / 1024
    print(f"  ✓ 영상 다운로드 완료: {os.path.basename(files[0])} ({size_mb:.1f}MB)")
    return files[0]


def parse_suggestions(filepath: str) -> list:
    """screenshot_suggestions.txt 파싱"""
    suggestions = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"\[(\d+:\d+(?::\d+)?)\]\s*\((.+?)\)\s*(.*)", line)
            if match:
                suggestions.append({
                    "timestamp": match.group(1),
                    "category": match.group(2),
                    "context": match.group(3),
                })
    return suggestions


def timestamp_to_ffmpeg(ts: str) -> str:
    """MM:SS → HH:MM:SS (ffmpeg용)"""
    parts = ts.split(":")
    if len(parts) == 2:
        return f"00:{parts[0]}:{parts[1]}"
    return ts


def capture_screenshot(video_path: str, timestamp: str, output_path: str,
                       retries: int = 2) -> tuple:
    """단일 스크린샷 캡쳐. (성공여부, 에러메시지)"""
    ffmpeg_ts = timestamp_to_ffmpeg(timestamp)
    last_error = ""

    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                ["ffmpeg", "-ss", ffmpeg_ts, "-i", video_path,
                 "-frames:v", "1", "-q:v", "1", "-update", "1",
                 output_path, "-y"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(output_path):
                if os.path.getsize(output_path) < 1024:
                    last_error = "파일 크기 < 1KB (빈 프레임)"
                    os.remove(output_path)
                    continue
                return (True, "")
            else:
                stderr = result.stderr.strip()
                err_lines = [l for l in stderr.split("\n") if l.strip()]
                last_error = err_lines[-1] if err_lines else f"returncode={result.returncode}"
        except subprocess.TimeoutExpired:
            last_error = "타임아웃 (30초)"
        except Exception as e:
            last_error = str(e)

        if attempt < retries:
            time.sleep(1)

    return (False, last_error)


def main():
    if len(sys.argv) < 4:
        print("사용법: python3 step3_screenshots.py <youtube_url> <suggestions_file> <images_dir>")
        sys.exit(1)

    youtube_url = sys.argv[1]
    suggestions_file = sys.argv[2]
    images_dir = sys.argv[3]

    os.makedirs(images_dir, exist_ok=True)
    # work_dir는 images_dir의 부모 디렉토리 아래 .work에 저장
    report_dir = os.path.dirname(images_dir)
    work_dir = os.path.join(report_dir, ".work")
    os.makedirs(work_dir, exist_ok=True)

    # 1. 영상 다운로드
    video_path = get_local_video(youtube_url, work_dir)

    # 2. 추천 타임스탬프 파싱
    suggestions = parse_suggestions(suggestions_file)
    print(f"\n  캡쳐 대상: {len(suggestions)}개 타임스탬프")

    # 3. 순차 캡쳐
    success = 0
    fail = 0
    failed_list = []

    for i, s in enumerate(suggestions, 1):
        filename = f"screenshot_{i:03d}.jpg"
        output_path = os.path.join(images_dir, filename)
        print(f"  [{i}/{len(suggestions)}] {s['timestamp']} ({s['category']}) → {filename}", end=" ")

        ok, error_msg = capture_screenshot(video_path, s["timestamp"], output_path)
        if ok:
            size_kb = os.path.getsize(output_path) / 1024
            print(f"✓ ({size_kb:.0f}KB)")
            success += 1
        else:
            print(f"✗ {error_msg}")
            failed_list.append({"index": i, "timestamp": s["timestamp"],
                                 "category": s["category"], "error": error_msg})
            fail += 1

    # 4. 실패 항목 재시도
    if failed_list:
        print(f"\n  실패 {len(failed_list)}건 재시도")
        still_failed = []
        for f_item in failed_list:
            i = f_item["index"]
            s = suggestions[i - 1]
            filename = f"screenshot_{i:03d}.jpg"
            output_path = os.path.join(images_dir, filename)
            print(f"  [재시도] #{i:03d} {s['timestamp']} ({s['category']})", end=" ")
            ok, error_msg = capture_screenshot(video_path, s["timestamp"], output_path, retries=3)
            if ok:
                size_kb = os.path.getsize(output_path) / 1024
                print(f"✓ ({size_kb:.0f}KB)")
                success += 1
                fail -= 1
            else:
                print(f"✗ 최종 실패 — {error_msg}")
                still_failed.append(f_item)
        failed_list = still_failed

    print(f"\n  완료: {success}개 성공, {fail}개 실패")

    # 5. 매핑 파일 생성
    mapping_path = os.path.join(images_dir, "screenshot_mapping.txt")
    with open(mapping_path, "w", encoding="utf-8") as f:
        f.write("# 스크린캡쳐 매핑 (자동 생성)\n")
        f.write("# 파일명 | 타임스탬프 | 카테고리 | 컨텍스트\n\n")
        for i, s in enumerate(suggestions, 1):
            filename = f"screenshot_{i:03d}.jpg"
            if os.path.exists(os.path.join(images_dir, filename)):
                f.write(f"{filename} | {s['timestamp']} | {s['category']} | {s['context']}\n")
    print(f"  ✓ 매핑 파일: {mapping_path}")


if __name__ == "__main__":
    main()
