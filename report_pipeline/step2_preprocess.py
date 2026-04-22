#!/usr/bin/env python3
"""
step2_preprocess.py — Whisper 전사 결과 전처리
==============================================
transcript.json을 읽어서:
  1. Whisper 환각 제거 (반복 문구 자동 삭제)
  2. 알려진 오인식 보정 (corrections.json)
  3. 논리적 블록 병합 + 섹션 분류
  4. 스크린캡쳐 추천 타임스탬프 생성

출력:
    {output_dir}/clean_transcript.txt
    {output_dir}/sections.json
    {output_dir}/camera_segments.txt
    {output_dir}/screenshot_suggestions.txt
    {output_dir}/raw_transcript.txt
"""

import json
import sys
import os
import pathlib
import re
from collections import Counter

_corrections_path = pathlib.Path(__file__).parent / "corrections.json"
CORRECTIONS = {
    k: v for k, v in json.loads(_corrections_path.read_text(encoding="utf-8")).items()
    if not k.startswith("_")
} if _corrections_path.exists() else {}

SECTION_KEYWORDS = {
    "디자인/외관": [
        "外观", "设计", "颜色", "配色", "材质", "轻薄", "重量", "厚度", "毫米",
        "design", "color", "colour", "finish", "weight", "thickness", "material", "slim",
    ],
    "디스플레이": [
        "屏幕", "显示", "护眼", "亮度", "刷新率", "折痕", "PWM", "nit",
        "display", "screen", "brightness", "refresh rate", "OLED", "LTPO", "resolution",
    ],
    "프로세서/성능": [
        "处理器", "芯片", "骁龙", "天玑", "性能", "跑分", "散热",
        "processor", "chip", "Snapdragon", "Dimensity", "performance",
        "benchmark", "thermal", "GPU", "CPU", "AnTuTu", "Geekbench",
    ],
    "카메라": [
        "摄像", "镜头", "传感器", "拍照", "影像", "光学", "变焦", "夜景", "人像",
        "长焦", "广角", "微距", "哈苏", "ARRI", "莱卡", "潜望", "防抖", "CIPA",
        "像素", "光圈", "焦距", "样张", "拍摄", "照片", "对焦", "HDR", "ISO",
        "快门", "Hasselblad", "Leica", "XPAN", "丹霞", "原相机", "影像系统",
        "camera", "lens", "sensor", "photo", "image", "optical", "zoom",
        "telephoto", "wide angle", "macro", "portrait", "night mode",
        "stabilization", "OIS", "aperture", "megapixel", "focal length",
        "shutter", "autofocus", "periscope", "cinematic",
    ],
    "색채/멀티스펙트럴": [
        "多光谱", "光谱", "光谱传感器", "蓝图", "原色摄像头", "色彩科学",
        "色准", "色貌", "色彩还原", "白平衡", "multi-spectral", "spectral", "Smooth EV",
        "color science", "color accuracy", "color rendering",
    ],
    "배터리/충전": [
        "电池", "充电", "续航", "毫安", "快充", "无线充",
        "battery", "charging", "mAh", "watt", "wireless charging", "fast charge",
    ],
    "AI/소프트웨어": [
        "AI", "智能", "助手", "大模型", "操作系统", "OS",
        "artificial intelligence", "assistant", "software", "operating system",
    ],
    "통신": [
        "5G", "信号", "频段", "WiFi", "蓝牙", "卫星", "北斗",
        "signal", "Bluetooth", "satellite", "modem", "connectivity", "Wi-Fi",
    ],
    "가격/출시": [
        "价格", "售价", "发售", "预售", "元起", "首销",
        "price", "launch", "available", "pre-order", "starting at", "dollars", "release date",
    ],
    "방수/내구성": [
        "防水", "防尘", "IP6", "可靠", "跌落", "耐摔",
        "waterproof", "water resistant", "durability", "drop test", "rugged",
    ],
}


def format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def is_hallucination(text: str, prev_texts: list, threshold: int = 3) -> bool:
    clean = text.strip()
    if not clean or len(clean) < 4:
        return True
    recent = prev_texts[-threshold:] if len(prev_texts) >= threshold else prev_texts
    if recent and all(t.strip() == clean for t in recent):
        return True
    return False


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


def find_global_repeat_phrases(segments: list, threshold: float = 0.07) -> set:
    texts = [s["text"].strip() for s in segments]
    total = max(len(texts), 1)
    counts = Counter(texts)
    return {
        phrase for phrase, cnt in counts.items()
        if len(phrase) >= 4 and cnt / total >= threshold
    }


def apply_corrections(text: str) -> str:
    for wrong, correct in CORRECTIONS.items():
        text = text.replace(wrong, correct)
    return text


def classify_section(text: str) -> str:
    SECTION_BOOST = {"카메라": 1.5, "색채/멀티스펙트럴": 1.5}
    scores: dict = {}
    for section_name, keywords in SECTION_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            boost = SECTION_BOOST.get(section_name, 1.0)
            scores[section_name] = hits * boost
    if not scores:
        return "기타"
    return max(scores, key=lambda s: scores[s])


def merge_segments(segments: list, gap_threshold: float = 6.0) -> list:
    if not segments:
        return []
    blocks = []
    current = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "texts": [segments[0]["text"].strip()],
    }
    for seg in segments[1:]:
        text = seg["text"].strip()
        gap = seg["start"] - current["end"]
        if gap > gap_threshold:
            blocks.append(current)
            current = {"start": seg["start"], "end": seg["end"], "texts": [text]}
        else:
            current["end"] = seg["end"]
            current["texts"].append(text)
    blocks.append(current)
    return blocks


def extract_camera_segments(segments: list) -> list:
    camera_keywords = SECTION_KEYWORDS["카메라"]
    camera_times = set()
    for seg in segments:
        if any(kw in seg["text"] for kw in camera_keywords):
            start = max(0, seg["start"] - 30)
            end = seg["end"] + 30
            for t in range(int(start), int(end)):
                camera_times.add(t)
    return [seg for seg in segments if int(seg["start"]) in camera_times]


def suggest_screenshot_timestamps(segments: list) -> list:
    screenshot_keywords = {
        "제품 공개": ["发布", "亮相", "登场", "来了", "introducing", "announce", "unveil", "reveal"],
        "스펙 슬라이드": ["参数", "规格", "配置", "搭载", "specifications", "specs", "features"],
        "카메라 시스템": [
            "摄像", "镜头", "影像系统", "长焦", "潜望", "传感器", "光学",
            "哈苏", "ARRI", "莱卡", "Hasselblad", "Leica", "丹霞", "XPAN",
            "camera system", "camera", "lens", "sensor", "optical zoom", "telephoto",
        ],
        "카메라 샘플": [
            "样张", "拍摄", "照片", "夜景", "人像", "广角", "微距", "变焦",
            "sample", "photo", "night shot", "portrait", "macro", "shot with",
        ],
        "카메라 기능": [
            "防抖", "CIPA", "像素", "光圈", "焦距", "对焦", "HDR", "快门", "ISO",
            "OIS", "stabilization", "aperture", "megapixel", "autofocus",
        ],
        "색채/분광": [
            "多光谱", "光谱", "蓝图", "原色摄像头", "色彩科学", "色准",
            "spectral", "color science", "color accuracy",
        ],
        "가격": ["价格", "售价", "元起", "预售", "price", "starting at", "dollars", "pre-order"],
        "디자인": ["外观", "颜色", "配色", "设计", "材质", "design", "color", "finish"],
        "디스플레이": ["屏幕", "显示", "亮度", "刷新率", "display", "screen", "brightness"],
        "배터리": ["电池", "毫安", "续航", "快充", "battery", "mAh", "charging"],
        "성능": ["处理器", "芯片", "骁龙", "天玑", "跑分", "processor", "chip", "benchmark"],
        "비교": ["对比", "友商", "iPhone", "苹果", "compare", "versus", "vs"],
    }

    CAMERA_CATEGORIES = {"카메라 시스템", "카메라 샘플", "카메라 기능", "색채/분광"}
    DEFAULT_WINDOW = 12
    CAMERA_WINDOW = 4

    suggestions = []
    seen_times_per_cat: dict = {}

    for seg in segments:
        for category, keywords in screenshot_keywords.items():
            if any(kw in seg["text"] for kw in keywords):
                window = CAMERA_WINDOW if category in CAMERA_CATEGORIES else DEFAULT_WINDOW
                time_key = int(seg["start"]) // window
                seen = seen_times_per_cat.setdefault(category, set())
                if time_key in seen:
                    continue
                seen.add(time_key)
                suggestions.append({
                    "timestamp": format_timestamp(seg["start"] + 2),
                    "seconds": seg["start"] + 2,
                    "category": category,
                    "context": seg["text"].strip()[:80],
                })
                break

    return sorted(suggestions, key=lambda x: x["seconds"])


def main():
    import argparse
    ap = argparse.ArgumentParser(description="전처리 (환각 제거 / 섹션 분류 / 스크린샷 후보)")
    ap.add_argument("report_dir", help="리포트 디렉토리 (transcript.json 포함)")
    ap.add_argument("--force", action="store_true", help="이미 완료된 파일도 재생성")
    args = ap.parse_args()

    output_dir = args.report_dir
    os.makedirs(output_dir, exist_ok=True)

    input_file = os.path.join(output_dir, "transcript.json")
    if not os.path.exists(input_file):
        print(f"오류: {input_file} 없음 — step1_transcribe.py를 먼저 실행하세요")
        sys.exit(1)

    # --force 없으면 이미 완료된 경우 건너뜀
    clean_path_check = os.path.join(output_dir, "clean_transcript.txt")
    if os.path.exists(clean_path_check) and not args.force:
        print(f"  ✓ 이미 존재: {clean_path_check} (--force로 재생성)")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]
    language = data.get("language", "unknown")
    source = data.get("source", "whisper")
    transcript_model = data.get("model", "whisper")
    print(f"원본: {len(segments)} segments, language={language}, source={source}")

    # raw_transcript.txt
    raw_path = os.path.join(output_dir, "raw_transcript.txt")
    if not os.path.exists(raw_path):
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(f"# 원본 전사 결과 (전처리 전) — {len(segments)} segments\n")
            f.write(f"# 언어: {language} / 출처: {source} ({transcript_model})\n\n")
            for seg in segments:
                ts = format_timestamp(seg["start"])
                f.write(f"[{ts}] {seg['text'].strip()}\n")
        print(f"✓ {raw_path}")

    # 환각 제거
    global_repeat_phrases = find_global_repeat_phrases(segments)
    if global_repeat_phrases:
        for phrase in sorted(global_repeat_phrases):
            cnt = Counter(s["text"].strip() for s in segments)[phrase]
            pct = cnt / len(segments) * 100
            print(f"  전역 반복 탐지 ({pct:.0f}%×{cnt}회): '{phrase[:40]}'")

    clean_segments = []
    prev_texts = []
    removed_count = removed_internal = removed_global = 0

    for seg in segments:
        text = seg["text"].strip()
        if text in global_repeat_phrases:
            removed_count += 1; removed_global += 1
            prev_texts.append(text); continue
        if has_internal_repetition(text):
            removed_count += 1; removed_internal += 1
            prev_texts.append(text); continue
        if is_hallucination(text, prev_texts):
            removed_count += 1
            prev_texts.append(text); continue
        corrected = apply_corrections(text)
        clean_segments.append({"start": seg["start"], "end": seg["end"], "text": corrected})
        prev_texts.append(text)

    print(f"환각 제거: {removed_count}개 (전역={removed_global}, 내부={removed_internal}, 연속={removed_count-removed_global-removed_internal})")
    print(f"정제 완료: {len(clean_segments)} segments")

    blocks = merge_segments(clean_segments)
    print(f"블록 병합: {len(blocks)} blocks")

    for block in blocks:
        block["section"] = classify_section(" ".join(block["texts"]))

    # clean_transcript.txt
    clean_path = os.path.join(output_dir, "clean_transcript.txt")
    with open(clean_path, "w", encoding="utf-8") as f:
        f.write(f"# 정제된 트랜스크립트\n")
        f.write(f"# 원본: {len(segments)} → 정제: {len(clean_segments)} → {len(blocks)} blocks\n\n")
        current_section = None
        for block in blocks:
            if block["section"] != current_section:
                current_section = block["section"]
                f.write(f"\n=== [{current_section}] ===\n\n")
            ts_start = format_timestamp(block["start"])
            ts_end = format_timestamp(block["end"])
            f.write(f"[{ts_start} ~ {ts_end}]\n")
            f.write(" ".join(block["texts"]) + "\n\n")
    print(f"✓ {clean_path}")

    # sections.json
    sections_path = os.path.join(output_dir, "sections.json")
    sections_data = {
        "metadata": {
            "original_segments": len(segments),
            "clean_segments": len(clean_segments),
            "blocks": len(blocks),
            "hallucinations_removed": removed_count,
            "language": language,
        },
        "blocks": [
            {
                "start": format_timestamp(b["start"]),
                "end": format_timestamp(b["end"]),
                "start_seconds": b["start"],
                "section": b["section"],
                "text": " ".join(b["texts"]),
            }
            for b in blocks
        ],
    }
    with open(sections_path, "w", encoding="utf-8") as f:
        json.dump(sections_data, f, ensure_ascii=False, indent=2)
    print(f"✓ {sections_path}")

    # camera_segments.txt
    camera_segs = extract_camera_segments(clean_segments)
    if camera_segs:
        camera_path = os.path.join(output_dir, "camera_segments.txt")
        with open(camera_path, "w", encoding="utf-8") as f:
            f.write("# 카메라 관련 세그먼트 (자동 추출)\n\n")
            for seg in camera_segs:
                ts = format_timestamp(seg["start"])
                f.write(f"[{ts}] {seg['text']}\n")
        print(f"✓ {camera_path} ({len(camera_segs)} segments)")

    # screenshot_suggestions.txt
    suggestions = suggest_screenshot_timestamps(clean_segments)
    screenshot_path = os.path.join(output_dir, "screenshot_suggestions.txt")
    with open(screenshot_path, "w", encoding="utf-8") as f:
        f.write("# 추천 스크린캡쳐 타임스탬프 (키워드 방식)\n\n")
        for s in suggestions:
            f.write(f"[{s['timestamp']}] ({s['category']}) {s['context']}\n")
    print(f"✓ {screenshot_path} ({len(suggestions)} suggestions)")

    section_counts = Counter(b["section"] for b in blocks)
    print(f"\n섹션 분포:")
    for section, count in section_counts.most_common():
        print(f"  {section}: {count} blocks")


if __name__ == "__main__":
    main()
