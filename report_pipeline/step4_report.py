#!/usr/bin/env python3
"""
step4_report.py — LM Studio로 한국어 HTML 보고서 생성
======================================================
bilingual/merged 트랜스크립트와 스크린샷을 바탕으로
섹션별 한국어 HTML 보고서를 생성한다.

출력:
    {report_dir}/report.html
    {report_dir}/content.html (중간 결과)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_API_URL = "http://localhost:1234/v1"

BRAND_COLORS = {
    "samsung": "#1428A0", "xiaomi": "#FF6700", "oppo": "#1EA366",
    "vivo": "#0072B8", "huawei": "#CF0A2C", "honor": "#01A1FF",
    "oneplus": "#F50514", "realme": "#FFC800", "redmi": "#FF6700",
    "iqoo": "#415FFF", "nothing": "#D71A21", "dji": "#0971CE",
    "insta360": "#FFD200", "google": "#4285F4", "apple": "#555555",
}


def _load_camera_terms() -> str:
    terms_path = Path(__file__).parent / "camera_terms.json"
    if not terms_path.exists():
        return ""
    try:
        terms = json.loads(terms_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    lines = ["## 카메라 기술 용어 사전 (아래 표기를 반드시 따르세요)"]
    for abbr, info in terms.items():
        full = info.get("full", "")
        ko   = info.get("ko", "")
        desc = info.get("desc", "")
        line = f"- {abbr} = {full}"
        if ko:
            line += f" ({ko})"
        if desc:
            line += f"  ※ {desc}"
        lines.append(line)
    return "\n".join(lines)


_CAMERA_TERMS: str = _load_camera_terms()


def llm_generate(prompt: str, model: str, api_url: str, api_key: str = "",
                 temperature: float = 0.3) -> str:
    """LM Studio OpenAI 호환 API 호출"""
    url = f"{api_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 8192,
        "top_p": 0.9,
        "think": False,
    }
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=600, verify=False)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning") or ""
            return content
        except requests.exceptions.ConnectionError:
            print(f"\n  오류: LM Studio에 연결할 수 없습니다 ({api_url})")
            print("  → LM Studio 실행 후 모델을 로드하세요.")
            sys.exit(1)
        except requests.exceptions.Timeout:
            print("\n  오류: LLM 응답 타임아웃 (10분 초과)")
            sys.exit(1)
        except Exception as e:
            if attempt < 3:
                wait = 2 ** attempt
                print(f"\n  LLM 호출 실패 (시도 {attempt}/3, {wait}초 후 재시도): {e}")
                time.sleep(wait)
            else:
                print(f"\n  오류: LLM 3회 모두 실패: {e}")
                sys.exit(1)
    return ""


def detect_brand_color(title: str) -> str:
    t = title.lower()
    for brand, color in BRAND_COLORS.items():
        if brand in t:
            return color
    return "#333333"


def _strip_code_fences(content: str) -> str:
    if not content:
        return ""
    content = content.strip()
    if content.startswith("```html"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def load_text_file(report_dir: str, name: str) -> str:
    path = os.path.join(report_dir, name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _ts_to_seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


def load_screenshot_mapping(report_dir: str) -> list:
    mapping_path = os.path.join(report_dir, "images", "screenshot_mapping.txt")
    if not os.path.exists(mapping_path):
        return []
    mappings = []
    with open(mapping_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                mappings.append({
                    "filename": parts[0],
                    "timestamp": parts[1],
                    "category": parts[2],
                    "context": parts[3] if len(parts) > 3 else "",
                })
    return mappings


# 섹션 설정
SECTION_ORDER = [
    "디자인/외관", "카메라", "색채/멀티스펙트럴",
    "디스플레이", "프로세서/성능",
    "배터리/충전", "통신", "AI/소프트웨어",
    "방수/내구성", "번들 제품", "가격/출시", "경쟁 분석 및 결론",
]

SECTION_CATEGORIES = {
    "디자인/외관": {"디자인", "제품 공개", "스펙 슬라이드"},
    "디스플레이": {"디스플레이", "스펙 슬라이드"},
    "프로세서/성능": {"성능", "스펙 슬라이드"},
    "카메라": {"카메라 시스템", "카메라 샘플", "카메라 기능"},
    "색채/멀티스펙트럴": {"색채/분광", "카메라 시스템"},
    "배터리/충전": {"배터리", "스펙 슬라이드"},
    "AI/소프트웨어": {"스펙 슬라이드"},
    "통신": {"스펙 슬라이드"},
    "가격/출시": {"가격"},
    "방수/내구성": {"스펙 슬라이드"},
    "번들 제품": {"제품 공개", "스펙 슬라이드", "디자인"},
    "경쟁 분석 및 결론": {"비교", "제품 공개"},
}

SECTION_ZH_KEYWORDS = {
    "디자인/외관": ["外观", "设计", "颜色", "配色", "材质", "轻薄", "重量", "厚度"],
    "디스플레이": ["屏幕", "显示", "护眼", "亮度", "刷新率", "nit", "OLED", "LTPO"],
    "프로세서/성능": ["处理器", "芯片", "骁龙", "天玑", "Dimensity", "性能", "跑分"],
    "카메라": ["摄像", "镜头", "传感器", "拍照", "影像", "光学", "变焦", "夜景", "人像",
              "长焦", "广角", "微距", "哈苏", "ARRI", "莱卡", "潜望", "防抖", "CIPA",
              "像素", "光圈", "焦距", "样张", "拍摄", "照片", "HDR", "XPAN", "丹霞",
              "camera", "lens", "sensor", "zoom", "telephoto", "portrait",
              "OIS", "aperture", "megapixel", "periscope"],
    "색채/멀티스펙트럴": ["多光谱", "光谱", "蓝图", "原色摄像头", "色彩科学", "色准", "Smooth EV"],
    "배터리/충전": ["电池", "充电", "续航", "毫安", "mAh", "快充", "无线充", "瓦"],
    "AI/소프트웨어": ["AI", "智能", "助手", "大模型", "操作系统", "HyperOS", "ColorOS"],
    "통신": ["5G", "信号", "频段", "WiFi", "蓝牙", "卫星", "北斗"],
    "가격/출시": ["价格", "售价", "发售", "预售", "元起", "首销", "开售"],
    "방수/내구성": ["防水", "防尘", "IP6", "跌落", "耐摔"],
    "번들 제품": ["手表", "Watch", "平板", "Pad", "耳机", "Buds", "同时发布"],
    "경쟁 분析 및 결론": ["对比", "友商", "iPhone", "苹果", "三星", "Samsung", "超过", "领先"],
}

SECTION_EN_KEYWORDS = {
    "디자인/외관": ["design", "color", "finish", "weight", "thickness", "material", "slim"],
    "디스플레이": ["display", "screen", "brightness", "refresh rate", "OLED", "LTPO", "nit"],
    "프로세서/성능": ["processor", "chip", "Snapdragon", "Dimensity", "performance", "benchmark"],
    "카메라": ["camera", "lens", "sensor", "zoom", "telephoto", "wide angle", "portrait",
              "night mode", "OIS", "stabilization", "aperture", "megapixel",
              "Hasselblad", "Leica", "ARRI", "periscope", "cinematic"],
    "색채/멀티스펙트럴": ["spectral", "color science", "Smooth EV", "color accuracy"],
    "배터리/충전": ["battery", "charging", "mAh", "watt", "wireless charging", "fast charge"],
    "AI/소프트웨어": ["AI", "artificial intelligence", "assistant", "OS", "software"],
    "통신": ["5G", "WiFi", "Wi-Fi", "Bluetooth", "satellite", "modem"],
    "가격/출시": ["price", "launch", "available", "pre-order", "starting at", "dollars"],
    "방수/내구성": ["waterproof", "water resistant", "IP6", "durability", "drop test"],
    "번들 제품": ["watch", "tablet", "earbuds", "earphone", "accessory"],
    "경쟁 분析 및 결론": ["compare", "versus", "vs.", "iPhone", "Samsung", "beats", "surpasses"],
}


def generate_summary(full_bilingual: str, meta: dict, model: str, api_url: str, api_key: str,
                     transcript_lang: str = "zh") -> str:
    is_en = transcript_lang.startswith("en")
    src_label = "영/한 빌링구얼" if is_en else "중/한 빌링구얼"

    head = full_bilingual[:6000]
    tail = full_bilingual[-4000:] if len(full_bilingual) > 10000 else ""
    excerpt = head + ("\n...\n" + tail if tail else "")

    prompt = f"""당신은 스마트폰 발표회 전문 분석가입니다.
아래 {src_label} 전사를 바탕으로 **Executive Summary** HTML 블록을 작성하세요.

{_CAMERA_TERMS}

## 영상 정보
- 제목: {meta.get('title', '')}
- 채널: {meta.get('channel', '')}
- 발표일: {meta.get('upload_date', '')}

## 빌링구얼 전사 (앞/뒷부분)
{excerpt}

## 작성 규칙
- `<section class="summary"><h2>Executive Summary</h2>` 으로 시작, `</section>` 로 끝.
- 다음 요소를 모두 포함하세요:
  1. 한 단락의 제품 포지셔닝 선언문 (2-3 문장)
  2. **핵심 하이라이트** (<h3>): 5~8개 불릿, 각 불릿에 카테고리 라벨(<strong>)과 구체적 수치
  3. **모델별 라인업** (<h3>): Pro/Ultra/기본 등 구분과 가격·컬러 요약
  4. **카메라 시스템 요약** (<h3>): 하드웨어+소프트웨어 핵심 1-2문장
  5. **가격 및 출시일** (<h3>): 모델별 가격과 예약/출시 일정
  6. **전략적 시사점** (<h3>): 시장 포지셔닝, 경쟁사 대비 차별점 5-6문장
- 한국어 중심, 제품명/브랜드/기술용어는 원문 병기.
- 마케팅 수사 제거, 구체 수치 위주.
- 오직 <section> HTML 조각만 출력. 문서 태그 금지.
"""
    return _strip_code_fences(llm_generate(prompt, model, api_url, api_key, temperature=0.2))


def generate_section(title: str, bilingual_text: str, images: list,
                     required_images: int, extra_instructions: str,
                     meta: dict, model: str, api_url: str, api_key: str,
                     temperature: float = 0.3,
                     transcript_lang: str = "zh") -> str:
    if not bilingual_text.strip():
        return ""

    is_en = transcript_lang.startswith("en")
    src_label = "영/한 빌링구얼" if is_en else "중/한 빌링구얼"

    def _fmt_img(m):
        return (f"  - images/{m['filename']} | [{m['timestamp']}] "
                f"[{m['category']}] {m['context']}")

    image_list = "\n".join(_fmt_img(m) for m in images) or "(사용 가능한 스크린샷 없음)"

    prompt = f"""당신은 스마트폰 발표회 전문 분석가입니다.
아래는 '{title}' 섹션에 해당하는 {src_label} 전사입니다.
이 섹션의 HTML 콘텐츠 조각을 한국어로 작성하세요.

{_CAMERA_TERMS}

## 영상 정보
- 제목: {meta.get('title', '')}
- 발표일: {meta.get('upload_date', '')}

## 사용 가능한 스크린샷
{image_list}

## {src_label} 전사
{bilingual_text}

## 작성 규칙
1. 한국어로 작성. 기술 용어/제품명은 원문 병기 가능.
2. 시작은 `<section><h2>{title}</h2>` 로 하고 `</section>` 으로 끝내세요.
3. 소제목(<h3>), 본문(<p>), 불릿(<ul><li>), 표(<table>) 등 구조화 사용.
4. 최소 {required_images}개 이상의 스크린샷을 다음 형식으로 삽입:
   <figure class="img-container">
     <img src="images/screenshot_NNN.jpg" alt="설명">
     <figcaption class="caption">
       <div class="cap-line">[MM:SS] 자연스러운 한국어 완성 문장</div>
     </figcaption>
   </figure>
   - 반드시 위 '사용 가능한 스크린샷' 목록의 정확한 파일명만 사용하세요.
   - 파일명을 임의로 만들거나 추측하지 마세요.
5. <!DOCTYPE>, <html>, <head>, <body> 등 문서 태그는 넣지 마세요.
6. 수치/스펙(mm, g, nit, mAh, Hz, 元, CIPA 등)은 정확히 옮기세요.
{extra_instructions}

HTML 조각을 출력하세요:"""

    content = llm_generate(prompt, model, api_url, api_key, temperature=temperature)
    if not content:
        return ""
    return _strip_code_fences(content)


def translate_and_generate(sections_data: dict, clean_transcript: str,
                           screenshot_mappings: list, meta: dict,
                           model: str, api_url: str, api_key: str = "",
                           bilingual_full: str = "",
                           bilingual_camera: str = "",
                           transcript_lang: str = "zh") -> str:
    is_en = transcript_lang.startswith("en")
    SECTION_KEYWORDS_ACTIVE = SECTION_EN_KEYWORDS if is_en else SECTION_ZH_KEYWORDS

    # 섹션별 블록 묶기
    section_blocks: dict = {}
    if sections_data and "blocks" in sections_data:
        for block in sections_data["blocks"]:
            section_blocks.setdefault(block["section"], []).append(block)

    # 빌링구얼 전사 타임스탬프 라인 파싱
    bi_lines = []
    lines = bilingual_full.splitlines()
    i = 0
    while i < len(lines):
        m2 = re.match(r"^\[([\d:]+)-([\d:]+)\]\s*(.+)$", lines[i])
        m1 = None if m2 else re.match(r"^\[([\d:]+)\]\s*(.+)$", lines[i])
        if m2:
            start_sec = _ts_to_seconds(m2.group(1))
            end_sec = _ts_to_seconds(m2.group(2))
            zh = f"[{m2.group(1)}-{m2.group(2)}] {m2.group(3)}"
            ko = ""
            if i + 1 < len(lines):
                km = re.match(r"^\s*→\s*(.+)$", lines[i + 1])
                if km:
                    ko = f"  → {km.group(1)}"
            bi_lines.append((start_sec, end_sec, zh, ko))
            i += 2
        elif m1:
            sec = _ts_to_seconds(m1.group(1))
            zh = f"[{m1.group(1)}] {m1.group(2)}"
            ko = ""
            if i + 1 < len(lines):
                km = re.match(r"^\s*→\s*(.+)$", lines[i + 1])
                if km:
                    ko = f"  → {km.group(1)}"
            bi_lines.append((sec, sec, zh, ko))
            i += 2
        else:
            i += 1

    global_used_images = set()

    def slice_bilingual(start_s: int, end_s: int, max_chars: int = 4000) -> str:
        out = []
        for s, e, zh, ko in bi_lines:
            if e >= start_s and s <= end_s:
                out.append(zh)
                if ko:
                    out.append(ko)
        return "\n".join(out)[:max_chars]

    def extract_by_keywords(keywords: list, max_chars: int = 8000) -> tuple:
        hit_times = set()
        context_window = 4
        for idx in range(len(bi_lines)):
            window_start = max(0, idx - context_window)
            window_end = min(len(bi_lines), idx + context_window + 1)
            window_text = " ".join(line[2] for line in bi_lines[window_start:window_end])
            matches_in_window = sum(1 for kw in keywords if kw in window_text)
            start_sec, _, zh, _ = bi_lines[idx]
            current_matches = sum(1 for kw in keywords if kw in zh)
            if matches_in_window >= 2 or current_matches >= 1:
                for (ws, _we, _wz, _wk) in bi_lines[window_start:window_end]:
                    hit_times.add(int(ws))

        out = []
        match_secs = []
        prev_included = False
        for s, e, zh, ko in bi_lines:
            if int(s) in hit_times:
                if not prev_included and out:
                    out.append("...")
                out.append(zh)
                if ko:
                    out.append(ko)
                match_secs.append(int(s))
                prev_included = True
            else:
                prev_included = False
        return "\n".join(out)[:max_chars], match_secs

    def filter_used_images(images: list) -> list:
        filtered = []
        for m in images:
            if m["filename"] not in global_used_images:
                filtered.append(m)
                global_used_images.add(m["filename"])
        return filtered

    def images_near(match_secs: list, categories: set, window: int = 45) -> list:
        if not match_secs:
            return []
        sel = []
        seen = set()
        for m in screenshot_mappings:
            sec = _ts_to_seconds(m.get("timestamp", "00:00"))
            if any(abs(sec - t) <= window for t in match_secs):
                if categories is None or m.get("category") in categories:
                    if m["filename"] not in seen:
                        seen.add(m["filename"])
                        sel.append(m)
        return sel

    def images_in_window(start_s: int, end_s: int, categories: set = None) -> list:
        out = []
        for m in screenshot_mappings:
            sec = _ts_to_seconds(m.get("timestamp", "00:00"))
            if start_s <= sec <= end_s:
                if categories is None or m.get("category") in categories:
                    out.append(m)
        return out

    print(f"  LLM 섹션별 생성 (모델: {model})")
    parts = []

    # 1. Executive Summary
    print("  - Executive Summary 생성 중...")
    try:
        parts.append(generate_summary(bilingual_full or clean_transcript, meta,
                                      model, api_url, api_key,
                                      transcript_lang=transcript_lang))
    except Exception as e:
        print(f"    경고: 요약 실패 ({e})")

    # 2. 섹션별 생성
    SPECTRAL_KEYWORDS = (
        ["spectral", "color science", "Smooth EV", "multi-spectral", "color accuracy"]
        if is_en else
        ["多光谱", "光谱", "蓝图", "原色摄像头", "色彩科学", "色准", "色貌", "Smooth EV"]
    )
    spectral_blocks = []
    if sections_data and "blocks" in sections_data:
        for b in sections_data["blocks"]:
            if any(k in b.get("text", "") for k in SPECTRAL_KEYWORDS):
                spectral_blocks.append(b)

    for section_name in SECTION_ORDER:
        blocks = section_blocks.get(section_name, [])
        match_secs: list = []

        # 색채 섹션: 키워드 확인
        if section_name == "색채/멀티스펙트럴":
            if not spectral_blocks:
                zh_kw = SECTION_KEYWORDS_ACTIVE.get(section_name, [])
                test_text, _ = extract_by_keywords(zh_kw, max_chars=500)
                if not test_text.strip():
                    continue
            blocks = spectral_blocks

        # 카메라: 전체 camera_transcript 사용
        if section_name == "카메라":
            bi_text = bilingual_camera or ""
            if not bi_text.strip() and blocks:
                s0 = min(b["start_seconds"] for b in blocks)
                s1 = max(b["start_seconds"] for b in blocks) + 30
                bi_text = slice_bilingual(int(s0), int(s1), max_chars=15000)
            bi_text = bi_text[:10000]
            required_images = 10
            extra = (
                "8. 카메라는 이 보고서의 핵심 섹션입니다. **반드시 10장 이상**의 스크린샷을 배치하세요.\n"
                "9. 다음 하위 구조(<h3>)를 모두 작성하세요:\n"
                "   - 카메라 하드웨어 구성 (렌즈별 센서명/화소/조리개/초점거리 표)\n"
                "   - 핵심 촬영 기능 (야간/HDR/AI/안정화)\n"
                "   - 줌/광학 시스템\n"
                "   - 영상 촬영 (4K/8K, FPS, 색공간, 시네마 모드)\n"
                "   - 샘플 분석\n"
                "10. 哈苏=핫셀블라드(Hasselblad), 莱卡=라이카(Leica), 丹霞=단샤(Danhxia) 표기.\n"
            )
        elif section_name == "색채/멀티스펙트럴":
            s0 = min(b["start_seconds"] for b in blocks)
            s1 = max(b["start_seconds"] for b in blocks) + 60
            bi_text = slice_bilingual(int(s0), int(s1), max_chars=10000)
            required_images = 4
            extra = (
                "8. 멀티스펙트럴 센서/색채 과학 전문 섹션입니다.\n"
                "   - 센서 스펙, 색 재현 원리, 색채 파이프라인을 포함하세요.\n"
            )
        else:
            zh_kw = SECTION_KEYWORDS_ACTIVE.get(section_name, [])
            bi_text = ""
            if blocks:
                s0 = min(b["start_seconds"] for b in blocks)
                s1 = max(b["start_seconds"] for b in blocks) + 30
                bi_text = slice_bilingual(int(s0), int(s1), max_chars=6000)

            kw_text, match_secs = extract_by_keywords(zh_kw, max_chars=8000)
            if len(kw_text) > len(bi_text) * 1.2:
                bi_text = kw_text
            if not bi_text.strip():
                print(f"  - [{section_name}] skip (관련 내용 없음)")
                continue

            required_images = 2 if section_name in (
                "디자인/외관", "디스플레이", "프로세서/성능", "배터리/충전", "가격/출시") else 1

            section_extras = {
                "디자인/외관": "8. 소재, 두께·무게, 컬러 옵션을 <ul>로 정리하세요.\n",
                "디스플레이": "8. 패널, 크기, 해상도, 밝기, 주사율을 표(<table>)로 정리하세요.\n",
                "프로세서/성능": "8. AP 칩명, 공정, 벤치마크 수치를 자세히 기술하세요.\n",
                "배터리/충전": "8. 용량(mAh), 유선/무선 충전 속도를 표로 정리하세요.\n",
                "통신": "8. 모뎀, 5G 대역, 위성 통신, WiFi/BT 버전을 정리하세요.\n",
                "AI/소프트웨어": "8. OS 이름·버전, 핵심 AI 기능을 소개하세요.\n",
                "가격/출시": "8. 모델별 메모리 옵션, 가격(元), 출시일을 표로 정리하세요.\n",
                "방수/내구성": "8. IP 등급, 낙하·충격 테스트 내용을 기술하세요.\n",
                "번들 제품": "8. 동시 발표된 제품들의 스펙/가격을 각각 <h3>으로 정리하세요.\n",
                "경쟁 분석 및 결론": "8. 경쟁사와의 직접 비교 수치와 팩트 위주로 정리하세요.\n",
            }
            extra = section_extras.get(section_name, "")

        # 이미지 선정
        cats = SECTION_CATEGORIES.get(section_name)
        if section_name == "카메라":
            imgs = [m for m in screenshot_mappings
                    if m.get("category") in SECTION_CATEGORIES["카메라"]][:40]
        elif section_name == "색채/멀티스펙트럴":
            imgs = [m for m in screenshot_mappings if m.get("category") == "색채/분광"]
            if blocks:
                s0 = min(b["start_seconds"] for b in blocks) - 10
                s1 = max(b["start_seconds"] for b in blocks) + 60
                imgs = imgs + images_in_window(int(s0), int(s1), cats)
        else:
            if match_secs:
                imgs = images_near(match_secs, cats, window=40)
            elif blocks:
                s0 = min(b["start_seconds"] for b in blocks) - 10
                s1 = max(b["start_seconds"] for b in blocks) + 40
                imgs = images_in_window(int(s0), int(s1), cats)
            else:
                imgs = []
            if len(imgs) < required_images and cats:
                extra_imgs = [m for m in screenshot_mappings
                              if m.get("category") in cats and m not in imgs]
                imgs = imgs + extra_imgs[:max(0, required_images * 2 - len(imgs))]

        imgs = filter_used_images(imgs)
        print(f"  - [{section_name}] 블록 {len(blocks)}개, 이미지 {len(imgs)}개")

        try:
            html = generate_section(section_name, bi_text, imgs,
                                    required_images, extra,
                                    meta, model, api_url, api_key,
                                    transcript_lang=transcript_lang)
            if html:
                parts.append(html)
        except Exception as e:
            print(f"    경고: {section_name} 생성 실패 ({e})")

    return "\n\n".join(parts)


def build_report(content: str, meta: dict, report_dir: str, template_path: str) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    title = meta.get("title", "스마트폰 발표회")
    brand_color = detect_brand_color(title)

    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{BRAND_COLOR}}", brand_color)
    html = html.replace("{{LAUNCH_DATE}}", meta.get("upload_date", "미정"))
    html = html.replace("{{ANALYSIS_DATE}}", date.today().isoformat())
    html = html.replace("{{YOUTUBE_URL}}", meta.get("youtube_url", "#"))
    html = html.replace("{{CONTENT}}", content)

    output_path = os.path.join(report_dir, "report.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✓ {output_path} ({os.path.getsize(output_path) / 1024:.0f}KB)")
    return output_path


def cleanup_unused_images(report_dir: str, report_html_path: str):
    images_dir = os.path.join(report_dir, "images")
    if not os.path.isdir(images_dir):
        return
    try:
        with open(report_html_path, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception:
        return

    used = set(re.findall(r'images/([A-Za-z0-9_\-.]+)', html))
    removed_count = 0
    removed_bytes = 0
    kept_count = 0
    KEEP_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
    KEEP_ALWAYS = {"screenshot_mapping.txt"}

    for fname in os.listdir(images_dir):
        fpath = os.path.join(images_dir, fname)
        if not os.path.isfile(fpath):
            continue
        if fname in KEEP_ALWAYS:
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in KEEP_EXTS:
            continue
        if fname in used:
            kept_count += 1
            continue
        try:
            removed_bytes += os.path.getsize(fpath)
            os.remove(fpath)
            removed_count += 1
        except OSError:
            pass

    if removed_count:
        print(f"  ✓ 미사용 스크린샷 {removed_count}개 삭제 "
              f"({removed_bytes / 1024 / 1024:.1f}MB 회수, 사용 {kept_count}개 유지)")
    else:
        print(f"  ✓ 미사용 스크린샷 없음 (사용 {kept_count}개)")


def main():
    parser = argparse.ArgumentParser(description="LM Studio로 한국어 HTML 보고서 생성")
    parser.add_argument("report_dir")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default="lm-studio")
    parser.add_argument("--template", default=None)
    args = parser.parse_args()

    report_dir = args.report_dir
    if not os.path.isdir(report_dir):
        print(f"오류: 디렉토리를 찾을 수 없습니다: {report_dir}")
        sys.exit(1)

    # 템플릿 경로
    if args.template:
        template_path = args.template
    else:
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")
    if not os.path.exists(template_path):
        print(f"오류: 템플릿 파일을 찾을 수 없습니다: {template_path}")
        sys.exit(1)

    print("[1/3] 데이터 로드")
    meta_path = os.path.join(report_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        print(f"  ✓ 메타: {meta.get('title', 'N/A')}")
    else:
        meta = {"title": os.path.basename(report_dir), "upload_date": "", "youtube_url": "#"}
        print("  ⚠ meta.json 없음 — 폴더명 사용")

    sections_path = os.path.join(report_dir, "sections.json")
    sections_data = None
    if os.path.exists(sections_path):
        with open(sections_path, "r", encoding="utf-8") as f:
            sections_data = json.load(f)
        print(f"  ✓ 섹션: {len(sections_data.get('blocks', []))} blocks")
    else:
        print("  ⚠ sections.json 없음")

    clean_transcript = load_text_file(report_dir, "clean_transcript.txt")
    screenshot_mappings = load_screenshot_mapping(report_dir)
    print(f"  ✓ 스크린샷: {len(screenshot_mappings)}개")

    # 빌링구얼 (merged 우선, 없으면 bilingual)
    merged_full = load_text_file(report_dir, "merged_transcript.txt")
    merged_camera = load_text_file(report_dir, "camera_merged_transcript.txt")
    if merged_full:
        bilingual_full = merged_full
        bilingual_camera = merged_camera or load_text_file(report_dir, "camera_transcript.txt")
        print(f"  ✓ 병합 전사: {len(bilingual_full)}자 / 카메라: {len(bilingual_camera)}자")
    else:
        bilingual_full = load_text_file(report_dir, "bilingual_transcript.txt")
        bilingual_camera = load_text_file(report_dir, "camera_transcript.txt")
        print(f"  ✓ 빌링구얼: {len(bilingual_full)}자 / 카메라: {len(bilingual_camera)}자")
        if not bilingual_full:
            print("  ⚠ bilingual_transcript.txt 없음 — step2b를 먼저 실행하세요")

    # 원본 전사 언어
    transcript_lang = "zh"
    transcript_json_path = os.path.join(report_dir, "transcript.json")
    if os.path.exists(transcript_json_path):
        try:
            with open(transcript_json_path, "r", encoding="utf-8") as f:
                _tj = json.load(f)
            _lang = (_tj.get("language") or "zh").lower()
            transcript_lang = "en" if _lang.startswith("en") else "zh"
            print(f"  ✓ 전사 언어: {_lang} → {transcript_lang}")
        except Exception:
            pass

    print("[2/3] LLM 보고서 생성")
    content = translate_and_generate(
        sections_data, clean_transcript, screenshot_mappings,
        meta, args.model, args.api_url, api_key=args.api_key,
        bilingual_full=bilingual_full,
        bilingual_camera=bilingual_camera,
        transcript_lang=transcript_lang,
    )

    # 중간 결과 저장
    content_path = os.path.join(report_dir, "content.html")
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ 콘텐츠 저장: {content_path}")

    print("[3/3] 최종 report.html 조립")
    output = build_report(content, meta, report_dir, template_path)
    print("      미사용 스크린샷 정리")
    cleanup_unused_images(report_dir, output)

    print(f"\n완료! 보고서: {output}")


if __name__ == "__main__":
    main()
