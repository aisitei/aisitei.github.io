#!/usr/bin/env python3
"""
step2b_bilingual.py — 빌링구얼 타임스탬프 트랜스크립트 생성
============================================================
transcript.json의 모든 세그먼트를 LM Studio로 한국어 번역하고
타임스탬프와 함께 원문-한국어 쌍으로 출력한다.

출력:
    {report_dir}/bilingual_transcript.txt   ← 전체 빌링구얼
    {report_dir}/camera_transcript.txt      ← 카메라 전용 빌링구얼
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_API_URL = "http://localhost:1234/v1"

BATCH_SIZE = 8
MAX_RETRIES = 5

CAMERA_KEYWORDS = [
    "摄像", "镜头", "传感器", "拍照", "影像", "光学", "变焦", "夜景", "人像",
    "长焦", "广角", "微距", "哈苏", "ARRI", "莱卡", "潜望", "防抖", "CIPA",
    "像素", "光圈", "焦距", "样张", "拍摄", "照片", "对焦", "HDR", "ISO",
    "快门", "Hasselblad", "Leica", "XPAN", "丹霞", "原相机", "影像系统",
    "camera", "lens", "sensor", "zoom", "telephoto", "wide angle", "macro",
    "portrait", "night mode", "night shot", "OIS", "stabilization",
    "aperture", "megapixel", "autofocus", "periscope", "cinematic",
    "photo", "image quality",
]


def format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def llm_call(prompt: str, model: str, api_url: str, api_key: str = "") -> str:
    url = f"{api_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
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


def translate_batch(batch: list, model: str, api_url: str, api_key: str,
                    src_lang: str = "zh") -> list:
    """세그먼트 배치를 한국어로 번역"""
    numbered = "\n".join(f"{i+1}. {seg['text'].strip()}" for i, seg in enumerate(batch))

    if src_lang == "en":
        prompt = f"""다음은 글로벌 스마트폰 발표회의 음성 전사(영어) 문장들입니다. 각 문장을 자연스러운 한국어로 번역해주세요.

규칙:
1. 반드시 번호 순서대로 한 줄에 하나씩 출력하세요.
2. 형식: `번호. 한국어 번역`
3. 제품명, 브랜드명, 기술 용어(Hasselblad, CIPA, XPAN, Snapdragon 등)는 원문 표기 유지.
4. 설명·주석 없이 번역 결과만 출력하세요.

=== 영어 문장 ===
{numbered}

=== 한국어 번역 ==="""
    else:
        prompt = f"""다음은 중국 스마트폰 발표회의 음성 전사(중국어) 문장들입니다. 각 문장을 자연스러운 한국어로 번역해주세요.

규칙:
1. 반드시 번호 순서대로 한 줄에 하나씩 출력하세요.
2. 형식: `번호. 한국어 번역`
3. 제품명, 브랜드명, 기술 용어(哈苏=핫셀블라드, ARRI, CIPA, 丹霞, XPAN 등)는 원문 표기 유지.
4. 설명·주석 없이 번역 결과만 출력하세요.

=== 중국어 문장 ===
{numbered}

=== 한국어 번역 ==="""

    text = llm_call(prompt, model, api_url, api_key)
    translations = [""] * len(batch)
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\s*(\d+)[\.\)]\s*(.+)$", line)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(translations):
                translations[idx] = m.group(2).strip()
    return translations


def translate_single(text: str, model: str, api_url: str, api_key: str,
                     src_lang: str = "zh") -> str:
    if src_lang == "en":
        prompt = (
            "다음 영어 문장을 자연스러운 한국어로 한 줄로 번역하세요. "
            "설명 없이 번역 결과만 출력하세요.\n\n"
            f"영어: {text.strip()}\n한국어:"
        )
    else:
        prompt = (
            "다음 중국어 문장을 자연스러운 한국어로 한 줄로 번역하세요. "
            "설명 없이 번역 결과만 출력하세요.\n\n"
            f"중국어: {text.strip()}\n한국어:"
        )
    try:
        out = llm_call(prompt, model, api_url, api_key).strip()
        out = out.splitlines()[0].strip() if out else ""
        out = re.sub(r'^(한국어|번역)\s*[:：]\s*', '', out).strip().strip('"\'`')
        return out
    except Exception:
        return ""


def has_internal_repetition(text: str, min_repeats: int = 5) -> bool:
    t = text.strip()
    if len(t) < 10:
        return False
    max_plen = min(21, len(t) // min_repeats + 1)
    for plen in range(2, max_plen):
        for start in range(min(plen, len(t) - plen * min_repeats + 1)):
            phrase = t[start:start + plen]
            count = 0
            i = start
            while i + plen <= len(t) and t[i:i + plen] == phrase:
                count += 1
                i += plen
            if count >= min_repeats:
                return True
    return False


def find_global_repeat_phrases(segs: list, threshold: float = 0.07) -> set:
    texts = [s["text"].strip() for s in segs]
    total = max(len(texts), 1)
    counts = Counter(texts)
    return {p for p, c in counts.items() if len(p) >= 4 and c / total >= threshold}


def main():
    ap = argparse.ArgumentParser(description="빌링구얼 트랜스크립트 생성")
    ap.add_argument("report_dir")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--api-key", default="lm-studio")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    report_dir = args.report_dir
    transcript_path = os.path.join(report_dir, "transcript.json")
    out_path = os.path.join(report_dir, "bilingual_transcript.txt")
    camera_out_path = os.path.join(report_dir, "camera_transcript.txt")

    if not os.path.exists(transcript_path):
        print(f"오류: {transcript_path} 없음")
        sys.exit(1)

    if os.path.exists(out_path) and not args.force:
        print(f"  ✓ 이미 존재: {out_path} (--force로 재생성)")
        if not os.path.exists(camera_out_path):
            print(f"  → camera_transcript.txt 재생성만 수행")
        else:
            return

    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    src_lang_raw = data.get("language", "zh") or "zh"
    src_lang = "en" if src_lang_raw.startswith("en") else "zh"
    print(f"  원본 언어: {src_lang_raw} → src_lang={src_lang}")

    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
        for s in data["segments"]
        if s.get("text", "").strip()
    ]
    print(f"  전사 세그먼트: {len(segments)}개")

    # 환각 제거
    global_repeat_phrases = find_global_repeat_phrases(segments)
    clean: list = []
    prev_texts: list = []
    for s in segments:
        text = s["text"].strip()
        if text in global_repeat_phrases:
            continue
        if has_internal_repetition(text):
            continue
        if len(prev_texts) >= 2 and all(t == text for t in prev_texts[-2:]):
            continue
        clean.append(s)
        prev_texts.append(text)
    print(f"  정제 후: {len(clean)}개")

    # 번역
    if not (os.path.exists(out_path) and not args.force):
        all_translations = []
        total_batches = (len(clean) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  LLM 번역 시작 ({total_batches}개 배치, 모델: {args.model})")
        t0 = time.time()

        for i in range(0, len(clean), BATCH_SIZE):
            batch = clean[i:i + BATCH_SIZE]
            b_idx = i // BATCH_SIZE + 1
            sys.stdout.write(f"\r  배치 {b_idx}/{total_batches} 번역 중...")
            sys.stdout.flush()
            trs = translate_batch(batch, args.model, args.api_url, args.api_key,
                                  src_lang=src_lang)

            # 빈 항목 재시도
            for j, t in enumerate(trs):
                if t:
                    continue
                for _attempt in range(2):
                    single = translate_single(batch[j]["text"], args.model,
                                              args.api_url, args.api_key, src_lang=src_lang)
                    if single:
                        trs[j] = single
                        break
                if not trs[j]:
                    print(f"\n  경고: 배치 {b_idx} 항목 {j+1} 번역 결과 없음 — 원문 사용")
                    trs[j] = batch[j]["text"]
            all_translations.extend(trs)

        elapsed = time.time() - t0
        print(f"\n  ✓ 번역 완료 ({elapsed:.0f}초)")

        with open(out_path, "w", encoding="utf-8") as f:
            lang_label = "영/한" if src_lang == "en" else "중/한"
            f.write(f"# {lang_label} 빌링구얼 트랜스크립트\n")
            f.write(f"# 원본 언어: {src_lang_raw} / 모델: {args.model}\n")
            f.write(f"# 세그먼트: {len(clean)}\n\n")
            for seg, ko in zip(clean, all_translations):
                ts = format_timestamp(seg["start"])
                f.write(f"[{ts}] {seg['text']}\n")
                f.write(f"  → {ko}\n\n")
        print(f"  ✓ {out_path}")
    else:
        print(f"  기존 {out_path} 재사용")

    # camera_transcript.txt 생성
    pairs = []
    with open(out_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        m = re.match(r"^\[([\d:]+)\]\s*(.+)$", line)
        if m:
            ts, zh = m.group(1), m.group(2)
            ko = ""
            if i + 1 < len(lines):
                km = re.match(r"^\s*→\s*(.+)$", lines[i + 1].rstrip("\n"))
                if km:
                    ko = km.group(1)
            pairs.append((ts, zh, ko))
            i += 2
        else:
            i += 1

    camera_idx = set()
    for idx, (_, zh, _) in enumerate(pairs):
        if any(kw in zh for kw in CAMERA_KEYWORDS):
            for j in range(max(0, idx - 2), min(len(pairs), idx + 3)):
                camera_idx.add(j)

    camera_pairs = [pairs[i] for i in sorted(camera_idx)]
    with open(camera_out_path, "w", encoding="utf-8") as f:
        f.write("# 카메라 전용 빌링구얼 트랜스크립트\n")
        f.write(f"# 카메라 키워드 매칭: {len(camera_pairs)} segments (전체 {len(pairs)})\n\n")
        for ts, zh, ko in camera_pairs:
            f.write(f"[{ts}] {zh}\n")
            f.write(f"  → {ko}\n\n")
    print(f"  ✓ {camera_out_path} ({len(camera_pairs)} camera segments)")


if __name__ == "__main__":
    main()
