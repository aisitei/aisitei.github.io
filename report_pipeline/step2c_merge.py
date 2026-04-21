#!/usr/bin/env python3
"""
step2c_merge.py — 빌링구얼 트랜스크립트를 완성 문장 단위로 병합
================================================================
bilingual_transcript.txt의 짧은 세그먼트들을 LLM으로 완성 문장 단위로 묶는다.

출력:
    {report_dir}/merged_transcript.txt
    {report_dir}/camera_merged_transcript.txt
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

BATCH_SIZE = 15
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


def ts_to_seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


def llm_call(prompt: str, model: str, api_url: str, api_key: str = "",
             temperature: float = 0.2) -> str:
    url = f"{api_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
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


def parse_bilingual(path: str) -> list:
    """bilingual_transcript.txt → [(start_sec, ts_str, zh, ko), ...]"""
    pairs = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        m = re.match(r"^\[([\d:]+)\]\s*(.+)$", line)
        if m:
            ts = m.group(1)
            zh = m.group(2).strip()
            ko = ""
            if i + 1 < len(lines):
                km = re.match(r"^\s*→\s*(.+)$", lines[i + 1].rstrip("\n"))
                if km:
                    ko = km.group(1).strip()
            pairs.append((ts_to_seconds(ts), ts, zh, ko))
            i += 2
        else:
            i += 1
    return pairs


def load_segment_end_times(transcript_json_path: str) -> dict:
    if not os.path.exists(transcript_json_path):
        return {}
    try:
        with open(transcript_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    end_map = {}
    for s in data.get("segments", []):
        start_i = int(s.get("start", 0))
        end = float(s.get("end", start_i + 3))
        if start_i not in end_map or end > end_map[start_i]:
            end_map[start_i] = end
    return end_map


def _has_internal_repetition(text: str, min_repeats: int = 4) -> bool:
    t = text.strip().replace(" ", "")
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


def is_hallucinated_merge(pairs: list, a: int, b: int, end_map: dict,
                           global_phrases: set,
                           max_duration: float = 60.0) -> bool:
    start_sec = pairs[a][0]
    end_start_sec = pairs[b][0]
    end_sec = end_map.get(end_start_sec, end_start_sec + 3)
    if end_sec - start_sec > max_duration:
        return True
    seg_count = b - a + 1
    if global_phrases and seg_count > 0:
        repeat_count = sum(1 for i in range(a, b + 1) if pairs[i][2].strip() in global_phrases)
        if repeat_count / seg_count > 0.4:
            return True
    zh_merged = "".join(pairs[i][2] for i in range(a, b + 1))
    if _has_internal_repetition(zh_merged, min_repeats=4):
        return True
    return False


def merge_batch(batch: list, model: str, api_url: str, api_key: str,
                src_lang: str) -> list:
    """한 배치를 LLM으로 완성 문장 단위로 묶는다"""
    origin_label = "영어 발표" if src_lang == "en" else "중국어 발표"
    seg_block = []
    for i, (_, ts, zh, ko) in enumerate(batch, start=1):
        seg_block.append(f"SEG {i} [{ts}] {origin_label[:2]}: {zh}  ||  번역: {ko}")
    seg_text = "\n".join(seg_block)

    prompt = f"""아래는 {origin_label} 영상의 짧게 끊긴 자동 전사 세그먼트들입니다.
연속된 세그먼트들을 **의미 단위의 완성된 한 문장**으로 묶어 주세요.

=== 입력 세그먼트 ({len(batch)}개) ===
{seg_text}

=== 출력 규칙 ===
1. 각 출력 줄은 정확히 이 형식으로 작성:
   `GROUP: <시작번호>-<끝번호>: <완성된 자연스러운 한국어 문장>`
   예) `GROUP: 1-3: 이번에 발표된 카메라는 1인치 센서를 탑재했습니다.`
2. 1번부터 {len(batch)}번까지 모든 SEG 번호는 **정확히 하나의 그룹**에 포함되어야 합니다.
3. 그룹은 연속된 번호만 허용.
4. 설명·주석 없이 GROUP 줄만 출력.
5. 제품명/브랜드/기술 용어(Hasselblad, ARRI, CIPA, XPAN 등)는 원문 표기 유지.

=== 출력 (GROUP 줄만) ==="""

    text = llm_call(prompt, model, api_url, api_key)
    groups = []
    for line in text.splitlines():
        m = re.match(r"^\s*GROUP\s*:\s*(\d+)\s*-\s*(\d+)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        a, b, sentence = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        if a < 1 or b > len(batch) or a > b:
            continue
        groups.append((a - 1, b - 1, sentence))
    return groups


def validate_and_fill_groups(groups: list, batch_len: int, batch: list) -> list:
    groups = sorted(groups, key=lambda g: (g[0], g[1]))
    covered = [False] * batch_len
    filtered = []
    for a, b, sent in groups:
        if any(covered[i] for i in range(a, b + 1)):
            continue
        for i in range(a, b + 1):
            covered[i] = True
        filtered.append((a, b, sent))

    idx_to_group = {}
    for a, b, sent in filtered:
        for i in range(a, b + 1):
            idx_to_group[i] = (a, b, sent)

    used = set()
    final = []
    for i in range(batch_len):
        if i in idx_to_group:
            g = idx_to_group[i]
            if g not in used:
                final.append(g)
                used.add(g)
        else:
            ko = batch[i][3].strip() or batch[i][2].strip()
            final.append((i, i, ko))

    final.sort(key=lambda g: g[0])
    return final


def write_merged(pairs: list, merged_groups: list, end_map: dict,
                 out_path: str, header_lines: list):
    with open(out_path, "w", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line + "\n")
        f.write("\n")
        for a, b, ko in merged_groups:
            start_sec, start_ts, _, _ = pairs[a]
            end_pair = pairs[b]
            end_start_sec = end_pair[0]
            end_sec = end_map.get(end_start_sec)
            if end_sec is None:
                if b + 1 < len(pairs):
                    end_sec = pairs[b + 1][0]
                else:
                    end_sec = end_start_sec + 3
            end_ts = format_timestamp(end_sec)
            zh_merged = " ".join(pairs[i][2] for i in range(a, b + 1))
            f.write(f"[{start_ts}-{end_ts}] {zh_merged}\n")
            f.write(f"  → {ko}\n\n")


def main():
    ap = argparse.ArgumentParser(description="빌링구얼 트랜스크립트를 완성 문장 단위로 병합")
    ap.add_argument("report_dir")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--api-key", default="lm-studio")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    report_dir = args.report_dir
    bilingual_path = os.path.join(report_dir, "bilingual_transcript.txt")
    transcript_json_path = os.path.join(report_dir, "transcript.json")
    out_path = os.path.join(report_dir, "merged_transcript.txt")
    camera_out_path = os.path.join(report_dir, "camera_merged_transcript.txt")

    if not os.path.exists(bilingual_path):
        print(f"오류: {bilingual_path} 없음 — step2b_bilingual.py를 먼저 실행하세요")
        sys.exit(1)

    if os.path.exists(out_path) and not args.force:
        print(f"  ✓ 이미 존재: {out_path} (--force로 재생성)")
        return

    src_lang = "zh"
    if os.path.exists(transcript_json_path):
        try:
            with open(transcript_json_path, "r", encoding="utf-8") as f:
                _tj = json.load(f)
            _lang = (_tj.get("language") or "zh").lower()
            src_lang = "en" if _lang.startswith("en") else "zh"
        except Exception:
            pass

    pairs = parse_bilingual(bilingual_path)
    end_map = load_segment_end_times(transcript_json_path)
    print(f"  입력 세그먼트: {len(pairs)}개 (원본 언어: {src_lang})")
    if not pairs:
        print("오류: 파싱된 세그먼트가 없습니다.")
        sys.exit(1)

    _zh_texts = [p[2].strip() for p in pairs]
    _total = max(len(_zh_texts), 1)
    _counts = Counter(_zh_texts)
    global_repeat_phrases: set = {
        phrase for phrase, cnt in _counts.items()
        if len(phrase) >= 4 and cnt / _total >= 0.07
    }

    total_batches = (len(pairs) + args.batch_size - 1) // args.batch_size
    print(f"  LLM 병합 시작 ({total_batches}개 배치, 모델: {args.model})")
    t0 = time.time()

    merged_all = []
    for b_idx, offset in enumerate(range(0, len(pairs), args.batch_size), start=1):
        batch = pairs[offset:offset + args.batch_size]
        sys.stdout.write(f"\r  배치 {b_idx}/{total_batches} 병합 중...")
        sys.stdout.flush()
        try:
            groups = merge_batch(batch, args.model, args.api_url, args.api_key, src_lang)
        except Exception as e:
            print(f"\n  오류: 배치 {b_idx} 병합 실패: {e}")
            sys.exit(1)

        groups = validate_and_fill_groups(groups, len(batch), batch)
        for a, b, sent in groups:
            merged_all.append((offset + a, offset + b, sent))

    elapsed = time.time() - t0
    print(f"\n  ✓ 병합 완료 ({elapsed:.0f}초, {len(merged_all)}개 문장)")

    pre_filter = len(merged_all)
    merged_all = [
        (a, b, ko) for a, b, ko in merged_all
        if not is_hallucinated_merge(pairs, a, b, end_map, global_repeat_phrases)
    ]
    removed_halluc = pre_filter - len(merged_all)
    if removed_halluc:
        print(f"  환각 필터 제거: {removed_halluc}개 → {len(merged_all)}개 문장 유지")

    header = [
        "# 완성 문장 단위 병합 트랜스크립트",
        f"# 원본 언어: {src_lang} / 모델: {args.model}",
        f"# 병합 문장: {len(merged_all)} (원본 세그먼트 {len(pairs)}개)",
    ]
    write_merged(pairs, merged_all, end_map, out_path, header)
    print(f"  ✓ {out_path}")

    camera_groups = []
    for a, b, ko in merged_all:
        combined_zh = " ".join(pairs[i][2] for i in range(a, b + 1))
        if any(kw in combined_zh or kw in ko for kw in CAMERA_KEYWORDS):
            camera_groups.append((a, b, ko))

    camera_header = [
        "# 카메라 구간 병합 트랜스크립트",
        f"# 카메라 문장: {len(camera_groups)} / 전체 {len(merged_all)}",
    ]
    write_merged(pairs, camera_groups, end_map, camera_out_path, camera_header)
    print(f"  ✓ {camera_out_path} ({len(camera_groups)} camera sentences)")


if __name__ == "__main__":
    main()
