#!/usr/bin/env python3
"""
step2d_suggest.py — LLM 기반 스크린샷 후보 추천
================================================
merged_transcript.txt를 바탕으로 LLM이 스크린샷 가치 있는 순간을 판단한다.
기존 키워드 방식(step2_preprocess.py)의 screenshot_suggestions.txt를 덮어쓴다.
실패 시 키워드 방식 파일이 fallback으로 남는다.

출력:
    {report_dir}/screenshot_suggestions.txt
"""

import argparse
import os
import re
import sys
import time

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_API_URL = "http://localhost:1234/v1"

BATCH_SIZE = 25
MAX_RETRIES = 5

CATEGORIES = [
    "카메라 시스템", "카메라 샘플", "카메라 기능", "색채/분광",
    "제품 공개", "스펙 슬라이드", "가격", "디자인",
    "디스플레이", "배터리", "성능", "비교",
]
CAMERA_CATEGORIES = {"카메라 시스템", "카메라 샘플", "카메라 기능", "색채/분광"}
CAMERA_WINDOW_SEC = 4
DEFAULT_WINDOW_SEC = 8


def llm_call(prompt: str, model: str, api_url: str, api_key: str = "") -> str:
    url = f"{api_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2048,
        "think": False,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=600, verify=False)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            return msg.get("content") or msg.get("reasoning") or ""
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = min(2 ** attempt, 30)
                print(f"\n  LLM 호출 실패 (시도 {attempt}/{MAX_RETRIES}, {wait}초 후 재시도): {e}")
                time.sleep(wait)
            else:
                print(f"\n  오류: LLM {MAX_RETRIES}회 모두 실패: {e}")
                sys.exit(1)


def parse_merged_transcript(path: str) -> list:
    """merged_transcript.txt → [(start_ts, zh, ko), ...]"""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        m = re.match(r"\[(\d+:\d+(?::\d+)?)-\d+:\d+(?::\d+)?\]\s*(.*)", line)
        if m:
            start_ts = m.group(1)
            zh = m.group(2).strip()
            ko = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("→"):
                    ko = next_line[1:].strip()
                    i += 1
            entries.append((start_ts, zh, ko))
        i += 1
    return entries


def build_prompt(batch: list, start_idx: int) -> str:
    category_str = ", ".join(CATEGORIES)
    lines = []
    for j, (start_ts, zh, ko) in enumerate(batch):
        idx = start_idx + j + 1
        display = ko if ko else zh
        lines.append(f"[{idx}] [{start_ts}] {display}")
    sentences_block = "\n".join(lines)

    return f"""다음은 스마트폰 신제품 발표 영상의 자막 문장 목록입니다.
각 문장을 읽고, 시청자가 봐야 할 중요한 장면을 캡처할 가치가 있는 문장을 골라주세요.

캡처 가치 기준:
- 제품/기능이 실제 화면에 표시되는 순간 (스펙 슬라이드, 비교 표, 제품 외관 등)
- 카메라 샘플 사진이 화면에 표시되는 순간
- 가격/출시일 등 핵심 정보가 처음 공개되는 순간
- 제품이 처음 등장하거나 공개되는 순간
- 제외: 단순 언급, 이미 공개된 정보 반복, 이동/전환 장면

카테고리 목록: {category_str}

문장 목록:
{sentences_block}

출력 형식 (캡처 가치 있는 문장만, 없으면 아무것도 출력 금지):
SHOT: <번호> | <카테고리> | <맥락 설명 30자 이내>

예시:
SHOT: 3 | 카메라 시스템 | 트리플 카메라 구성 공개
SHOT: 7 | 스펙 슬라이드 | 배터리 5000mAh 사양 표시"""


def parse_llm_response(response: str, batch: list, start_idx: int) -> list:
    results = []
    for line in response.splitlines():
        line = line.strip()
        m = re.match(r"SHOT:\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.*)", line)
        if not m:
            continue
        abs_idx = int(m.group(1)) - 1
        category = m.group(2).strip()
        context = m.group(3).strip()
        rel_idx = abs_idx - start_idx
        if rel_idx < 0 or rel_idx >= len(batch):
            continue
        start_ts, zh, ko = batch[rel_idx]
        if category not in CATEGORIES:
            category = _best_match_category(category)
        if not context:
            display = ko if ko else zh
            context = display[:40]
        results.append({"timestamp": start_ts, "category": category, "context": context})
    return results


def _best_match_category(raw: str) -> str:
    for cat in CATEGORIES:
        if cat in raw or raw in cat:
            return cat
    return "스펙 슬라이드"


def ts_to_sec(ts: str) -> int:
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def deduplicate(suggestions: list) -> list:
    seen: dict = {}
    result = []
    for s in suggestions:
        cat = s["category"]
        sec = ts_to_sec(s["timestamp"])
        window = CAMERA_WINDOW_SEC if cat in CAMERA_CATEGORIES else DEFAULT_WINDOW_SEC
        last = seen.get(cat, -999)
        if sec - last >= window:
            seen[cat] = sec
            result.append(s)
    return result


def main():
    ap = argparse.ArgumentParser(description="LLM 기반 스크린샷 후보 추천")
    ap.add_argument("report_dir")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--api-key", default="lm-studio")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    merged_path = os.path.join(args.report_dir, "merged_transcript.txt")
    out_path = os.path.join(args.report_dir, "screenshot_suggestions.txt")

    if not os.path.exists(merged_path):
        print(f"오류: {merged_path} 없음 — step2c_merge.py를 먼저 실행하세요")
        sys.exit(1)

    if os.path.exists(out_path) and not args.force:
        with open(out_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
        if "LLM" in first_line:
            print(f"  ✓ 이미 존재 (LLM 방식): {out_path} (--force로 재생성)")
            return
        print("  키워드 방식 파일 발견 → LLM 방식으로 덮어씁니다")

    entries = parse_merged_transcript(merged_path)
    if not entries:
        print("오류: merged_transcript.txt 파싱 실패 또는 빈 파일")
        sys.exit(1)
    print(f"  파싱 완료: {len(entries)}개 문장")

    all_suggestions = []
    total_batches = (len(entries) + args.batch_size - 1) // args.batch_size

    for batch_num in range(total_batches):
        start = batch_num * args.batch_size
        batch = entries[start:start + args.batch_size]
        print(f"  배치 {batch_num + 1}/{total_batches} ({len(batch)}개 문장)...", end=" ", flush=True)

        prompt = build_prompt(batch, start)
        try:
            response = llm_call(prompt, args.model, args.api_url, args.api_key)
            shots = parse_llm_response(response, batch, start)
            all_suggestions.extend(shots)
            print(f"{len(shots)}개 후보")
        except Exception as e:
            print(f"실패 ({e})")

        if batch_num < total_batches - 1:
            time.sleep(0.3)

    if not all_suggestions:
        print("경고: LLM이 후보를 추출하지 못했습니다 — 키워드 방식 파일을 유지합니다")
        sys.exit(1)

    all_suggestions.sort(key=lambda x: ts_to_sec(x["timestamp"]))
    deduped = deduplicate(all_suggestions)
    print(f"  중복 제거: {len(all_suggestions)} → {len(deduped)}개 최종 후보")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 추천 스크린캡쳐 타임스탬프 (LLM 기반 — step2d_suggest.py)\n\n")
        for s in deduped:
            f.write(f"[{s['timestamp']}] ({s['category']}) {s['context']}\n")

    print(f"  ✓ {out_path} ({len(deduped)}개)")


if __name__ == "__main__":
    main()
