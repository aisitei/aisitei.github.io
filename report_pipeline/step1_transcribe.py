#!/usr/bin/env python3
"""
step1_transcribe.py — YouTube 자막 우선 + mlx-whisper 폴백 전사
================================================================
처리 순서:
  1. YouTube 자막 다운로드 시도 (수동 자막 → 자동 자막)
     - 중국어 영상: zh-Hans → zh → en 순
     - 영어 영상  : en → zh-Hans 순
  2. 자막이 없을 때만 mlx-whisper 전사 (Apple Silicon)

출력:
    {output_dir}/transcript.json
    {output_dir}/meta.json
"""

import argparse
import glob
import html as html_mod
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


MLX_MODEL_MAP = {
    "tiny":           "mlx-community/whisper-tiny-mlx",
    "base":           "mlx-community/whisper-base-mlx",
    "small":          "mlx-community/whisper-small-mlx",
    "medium":         "mlx-community/whisper-medium-mlx",
    "large-v3":       "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

YTDLP_BASE_ARGS = ["--no-check-certificates"]

# mlx-whisper BGM/무음 구간 환각 패턴 — 전사 후 세그먼트 단위 필터
_HALLUCINATION_RE = re.compile(
    r"^[!！\s]+$"             # 느낌표/공백만
    r"|(展示){2,}"            # '展示' 2회 이상 연속
    r"|(.{4,})\s+\2"         # 4자+ 구절이 공백 뒤에 그대로 반복
    r"|^[!！][\u4e00-\u9fff]" # !哇哦 등 느낌표+한자 패턴
)


def extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else "unknown"


def detect_brand(title: str) -> str:
    t = title.lower()
    brands = [
        ("一加", "oneplus"), ("oneplus", "oneplus"),
        ("huawei", "huawei"), ("华为", "huawei"),
        ("xiaomi", "xiaomi"), ("小米", "xiaomi"),
        ("oppo", "oppo"), ("vivo", "vivo"), ("iqoo", "iqoo"),
        ("honor", "honor"), ("荣耀", "honor"),
        ("realme", "realme"), ("samsung", "samsung"),
        ("redmi", "redmi"), ("红米", "redmi"),
        ("nothing", "nothing"), ("dji", "dji"),
        ("insta360", "insta360"), ("pixel", "google"),
        ("apple", "apple"), ("iphone", "apple"),
    ]
    for cn, en in brands:
        if cn in t:
            return en
    return "unknown"


def get_metadata(youtube_url: str) -> dict:
    print("  메타데이터 수집 중...")
    result = subprocess.run(
        ["yt-dlp", "--dump-json", *YTDLP_BASE_ARGS, youtube_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  yt-dlp 오류: {result.stderr[:300]}")
        sys.exit(1)
    data = json.loads(result.stdout)
    upload = data.get("upload_date", "")
    upload_fmt = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if len(upload) == 8 else upload
    return {
        "video_id":    data.get("id", ""),
        "title":       data.get("title", ""),
        "channel":     data.get("channel", ""),
        "upload_date": upload_fmt,
        "duration":    data.get("duration", 0),
        "youtube_url": youtube_url,
        "language":    data.get("language") or "",
        "brand":       detect_brand(data.get("title", "")),
    }


def _parse_vtt_ts(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def parse_vtt(vtt_content: str, lang: str) -> dict:
    """YouTube VTT 자막 → transcript.json 형식 변환"""
    TS_RE = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d+|\d{2}:\d{2}[.,]\d+)"
        r"\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d+|\d{2}:\d{2}[.,]\d+)"
    )
    segments = []
    lines = vtt_content.splitlines()
    i = 0
    while i < len(lines):
        m = TS_RE.match(lines[i].strip())
        if m:
            start = _parse_vtt_ts(m.group(1))
            end   = _parse_vtt_ts(m.group(2))
            i += 1
            text_parts = []
            while i < len(lines) and lines[i].strip():
                text_parts.append(lines[i].strip())
                i += 1
            raw = " ".join(text_parts)
            clean = re.sub(r"<[^>]+>", "", raw)
            clean = html_mod.unescape(clean).strip()
            clean = re.sub(r"^>>\s*", "", clean).strip()
            clean = re.sub(r"\s+", " ", clean)
            if clean and len(clean) > 1:
                segments.append({"start": round(start, 2),
                                  "end":   round(end, 2),
                                  "text":  clean})
        else:
            i += 1

    deduped: list = []
    for seg in segments:
        if deduped:
            prev = deduped[-1]
            if (seg["text"] == prev["text"]
                    or seg["text"] in prev["text"]
                    or prev["text"] in seg["text"]):
                if len(seg["text"]) > len(prev["text"]):
                    prev["text"] = seg["text"]
                prev["end"] = max(prev["end"], seg["end"])
                continue
        deduped.append(dict(seg))

    return {
        "segments":        deduped,
        "language":        lang,
        "source":          "subtitle",
        "model":           "youtube-caption",
        "engine":          "yt-dlp",
        "elapsed_seconds": 0,
    }


def _lang_from_filename(filepath: str, default: str) -> str:
    base = os.path.basename(filepath)
    parts = base.split(".")
    if len(parts) >= 3:
        code = parts[-2]
        if code.startswith("zh"):
            return "zh"
        if code.startswith("en"):
            return "en"
        return code.split("-")[0]
    return default


def download_subtitle(youtube_url: str, work_dir: str,
                      video_lang: str = "") -> tuple:
    """YouTube 자막 우선 다운로드 시도. (transcript_dict, lang) 또는 (None, None)"""
    vl = (video_lang or "").lower()
    if vl.startswith("zh") or vl == "":
        candidates = ["zh-Hans", "zh", "en"]
    elif vl.startswith("en"):
        candidates = ["en", "zh-Hans", "zh"]
    else:
        candidates = [vl, "en", "zh-Hans"]

    sub_base = os.path.join(work_dir, "subtitle")

    for mode_flag, mode_label in [("--write-subs", "수동"), ("--write-auto-subs", "자동")]:
        for lang in candidates:
            for f in glob.glob(f"{sub_base}*.vtt"):
                try:
                    os.remove(f)
                except OSError:
                    pass

            result = subprocess.run(
                ["yt-dlp", "--skip-download", mode_flag,
                 "--sub-langs", lang, "--sub-format", "vtt",
                 "-o", sub_base, *YTDLP_BASE_ARGS, youtube_url],
                capture_output=True, text=True,
            )
            files = glob.glob(f"{sub_base}*.vtt")
            if not files:
                continue

            try:
                with open(files[0], encoding="utf-8") as fh:
                    content = fh.read()
            except Exception:
                continue

            detected = _lang_from_filename(files[0], lang)
            transcript = parse_vtt(content, detected)

            if len(transcript["segments"]) >= 15:
                print(f"  ✓ {mode_label} 자막 사용: {os.path.basename(files[0])} "
                      f"({len(transcript['segments'])} 세그먼트, 언어: {detected})")
                return transcript, detected

    return None, None


def download_audio(youtube_url: str, work_dir: str) -> str:
    """yt-dlp로 오디오 다운로드 → 16kHz WAV 변환"""
    wav_path = os.path.join(work_dir, "audio_16k.wav")
    if os.path.exists(wav_path):
        print(f"  ✓ 16kHz WAV 이미 존재")
        return wav_path

    raw_path = os.path.join(work_dir, "audio_raw.%(ext)s")
    print("  오디오 다운로드 중...")
    result = subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "wav", "--audio-quality", "0",
         *YTDLP_BASE_ARGS, "-o", raw_path, youtube_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  다운로드 오류: {result.stderr[:300]}")
        sys.exit(1)

    raw_files = glob.glob(os.path.join(work_dir, "audio_raw.*"))
    if not raw_files:
        print("  오디오 파일을 찾을 수 없습니다.")
        sys.exit(1)

    raw_file = raw_files[0]
    print(f"  ✓ 다운로드 완료: {os.path.getsize(raw_file) / 1024 / 1024:.1f}MB")
    print("  16kHz 모노 변환 중...")
    result = subprocess.run(
        ["ffmpeg", "-i", raw_file, "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", wav_path, "-y", "-loglevel", "error"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  변환 오류: {result.stderr}")
        sys.exit(1)

    os.remove(raw_file)
    print(f"  ✓ 변환 완료: {os.path.getsize(wav_path) / 1024 / 1024:.1f}MB")
    return wav_path


def _get_audio_duration(audio_path: str) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def extract_audio_sample(audio_path: str, offset_sec: float, duration_sec: int = 30) -> str:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    subprocess.run(
        ["ffmpeg", "-ss", str(int(offset_sec)), "-t", str(duration_sec),
         "-i", audio_path, "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", tmp_path, "-y", "-loglevel", "error"],
        check=True, capture_output=True,
    )
    return tmp_path


def _midpoint_offset(audio_path: str) -> float:
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        return 60.0
    return max(30.0, min(600.0, duration * 0.3))


def _detect_speech_segments_vad(audio_path: str) -> Optional[list]:
    """faster-whisper Silero VAD로 발화 구간 감지. [(start_sec, end_sec), ...]
    faster-whisper 미설치 또는 실패 시 None 반환 → 전체 오디오 전사로 폴백.
    """
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        from faster_whisper.audio import decode_audio
    except ImportError:
        return None

    try:
        audio = decode_audio(audio_path)
        vad_opts = VadOptions(
            min_speech_duration_ms=500,
            max_speech_duration_s=float("inf"),
            min_silence_duration_ms=800,
            speech_pad_ms=400,
        )
        timestamps = get_speech_timestamps(audio, vad_opts)
        # timestamps: list of {"start": int, "end": int} in samples (16 kHz)
        return [(t["start"] / 16000, t["end"] / 16000) for t in timestamps]
    except Exception as e:
        print(f"  VAD 감지 실패 ({e}) — 전체 오디오로 전사합니다")
        return None


def _merge_vad_chunks(segments: list,
                      max_chunk_sec: float = 600.0,
                      gap_sec: float = 30.0) -> list:
    """인접 VAD 구간을 병합하여 큰 청크(최대 10분)로 만든다."""
    if not segments:
        return []
    chunks = []
    chunk_start, chunk_end = segments[0]
    for start, end in segments[1:]:
        if start - chunk_end <= gap_sec and (end - chunk_start) <= max_chunk_sec:
            chunk_end = end
        else:
            chunks.append((chunk_start, chunk_end))
            chunk_start, chunk_end = start, end
    chunks.append((chunk_start, chunk_end))
    return chunks


def transcribe_mlx(audio_path: str, model_name: str = "large-v3-turbo",
                   language: str = None, model_path: str = None) -> dict:
    """mlx-whisper 전사 (Apple Silicon)"""
    try:
        import mlx_whisper
    except ImportError:
        print("오류: mlx-whisper 미설치.")
        print("  → pip install mlx-whisper")
        sys.exit(1)

    mlx_repo = model_path or MLX_MODEL_MAP.get(model_name,
                             "mlx-community/whisper-large-v3-turbo")

    if language is None:
        offset = _midpoint_offset(audio_path)
        print(f"  언어 자동 감지: {int(offset//60)}분 {int(offset%60)}초 지점 30초 샘플...")
        sample_path = extract_audio_sample(audio_path, offset)
        try:
            det = mlx_whisper.transcribe(
                sample_path, path_or_hf_repo=mlx_repo,
                language=None, task="transcribe", verbose=False,
            )
            language = det.get("language") or None
            print(f"  감지된 언어: {language}")
        except Exception:
            language = None
        finally:
            try:
                os.remove(sample_path)
            except OSError:
                pass

    print(f"  mlx-whisper 전사 시작")
    print(f"    모델  : {mlx_repo}")
    print(f"    언어  : {language or '자동 감지'}")
    print(f"    엔진  : Apple MLX (Metal GPU / Neural Engine)")
    print("  ※ 첫 실행 시 HuggingFace에서 모델 자동 다운로드 (수 분 소요)")

    def _transcribe_chunk(chunk_path: str, offset: float = 0.0) -> list:
        """청크 파일 전사 후 타임스탬프 보정 + 환각 필터링."""
        r = mlx_whisper.transcribe(
            chunk_path,
            path_or_hf_repo=mlx_repo,
            language=language,
            task="transcribe",
            verbose=False,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,  # 청크 간 환각 전파 차단
            word_timestamps=False,
        )
        out = []
        for seg in r.get("segments", []):
            text = (seg.get("text") or "").strip()
            if not text or _HALLUCINATION_RE.search(text):
                continue
            out.append({
                "start": round(float(seg["start"]) + offset, 2),
                "end":   round(float(seg["end"])   + offset, 2),
                "text":  text,
            })
        return out

    start = time.time()
    segments: list = []
    detected = language or "unknown"

    # ── VAD 발화 구간 감지 → 청크 분할 전사 ──────────────────────
    print("  VAD로 발화 구간 감지 중...")
    vad_segs = _detect_speech_segments_vad(audio_path)

    if vad_segs:
        chunks = _merge_vad_chunks(vad_segs)
        speech_total = sum(e - s for s, e in vad_segs)
        print(f"  발화 구간: {len(vad_segs)}개 ({speech_total/60:.1f}분) "
              f"→ {len(chunks)}개 청크로 병합")
        try:
            for i, (chunk_start, chunk_end) in enumerate(chunks):
                duration = chunk_end - chunk_start
                print(f"  청크 {i+1}/{len(chunks)} "
                      f"({int(chunk_start//60)}:{int(chunk_start%60):02d}"
                      f"–{int(chunk_end//60)}:{int(chunk_end%60):02d}, "
                      f"{duration:.0f}초)...", end=" ", flush=True)
                chunk_path = extract_audio_sample(audio_path, chunk_start, int(duration) + 1)
                try:
                    segs = _transcribe_chunk(chunk_path, offset=chunk_start)
                    segments.extend(segs)
                    print(f"{len(segs)}개")
                finally:
                    try:
                        os.remove(chunk_path)
                    except OSError:
                        pass
                if i < len(chunks) - 1:
                    time.sleep(0.1)
            if not segments:
                print("  경고: VAD 청크 전사 결과 없음 — 전체 오디오로 재시도")
                vad_segs = None
        except Exception as e:
            print(f"\n  VAD 청크 전사 오류 ({e}) — 전체 오디오로 재시도")
            segments = []
            vad_segs = None

    # ── 전체 오디오 폴백 ──────────────────────────────────────────
    if not vad_segs:
        print("  전체 오디오 전사 중...")
        try:
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=mlx_repo,
                language=language,
                task="transcribe",
                verbose=False,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                logprob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
                word_timestamps=False,
            )
        except Exception as e:
            print(f"\n  오류: MLX 전사 실패 — {e}")
            sys.exit(1)
        detected = result.get("language") or language or "unknown"
        for seg in result.get("segments", []):
            text = (seg.get("text") or "").strip()
            if not text or _HALLUCINATION_RE.search(text):
                continue
            segments.append({
                "start": round(float(seg["start"]), 2),
                "end":   round(float(seg["end"]),   2),
                "text":  text,
            })

    elapsed = time.time() - start
    rtf = elapsed / max(1, segments[-1]["end"] if segments else 1)
    print(f"  ✓ 전사 완료: {len(segments)}개 세그먼트 "
          f"({elapsed:.1f}초, RTF {rtf:.2f}x, 언어: {detected})")

    return {
        "segments":        segments,
        "language":        detected,
        "source":          "whisper",
        "model":           mlx_repo,
        "engine":          "mlx-whisper (Apple Metal)",
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="YouTube 자막 우선 + mlx-whisper 폴백 전사")
    parser.add_argument("youtube_url")
    parser.add_argument("output_dir")
    parser.add_argument("--model", default="large-v3-turbo",
                        choices=["tiny","base","small","medium","large-v3","large-v3-turbo"])
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--lang", default="auto",
                        help="언어 코드 (기본: auto). zh, en 등 명시 가능")
    parser.add_argument("--skip-transcribe", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    work_dir = os.path.join(args.output_dir, ".work")
    os.makedirs(work_dir, exist_ok=True)

    transcript_path = os.path.join(args.output_dir, "transcript.json")
    meta_path       = os.path.join(args.output_dir, "meta.json")

    # 1. 메타데이터
    print("[1/3] 메타데이터 수집")
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path, encoding="utf-8"))
        print(f"  ✓ 캐시 사용: {meta['title']}")
    else:
        meta = get_metadata(args.youtube_url)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {meta['title']}")

    video_lang = meta.get("language") or ""
    if args.lang != "auto":
        video_lang = args.lang
    print(f"  영상 언어: {video_lang or '(미감지, 자동 판별)'}")

    # 2. 자막 우선 시도
    transcript = None
    print("[2/3] 자막 다운로드 시도")
    transcript, detected_lang = download_subtitle(
        args.youtube_url, work_dir, video_lang
    )
    if transcript:
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 저장: {len(transcript['segments'])} 세그먼트")
    else:
        print("  → 자막 없음")

    # 3. mlx-whisper 폴백
    if transcript is None:
        if args.skip_transcribe:
            if os.path.exists(transcript_path):
                print(f"[3/3] 전사 건너뜀 — 기존 transcript.json 재사용")
                transcript = json.load(open(transcript_path, encoding="utf-8"))
            else:
                print("오류: --skip-transcribe 사용했으나 transcript.json이 없습니다.")
                sys.exit(1)
        else:
            print("[3/3] mlx-whisper 전사 (오디오 다운로드)")
            wav_path = download_audio(args.youtube_url, work_dir)

            whisper_lang = None if (args.lang == "auto" and not video_lang) else (
                video_lang or args.lang or None
            )
            if whisper_lang == "auto":
                whisper_lang = None

            transcript = transcribe_mlx(wav_path, model_name=args.model,
                                        language=whisper_lang, model_path=args.model_path)
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(transcript, f, ensure_ascii=False, indent=2)
            print(f"  ✓ 저장: {transcript_path}")
            try:
                os.remove(wav_path)
            except OSError:
                pass
    else:
        print("[3/3] 자막 사용 — whisper 전사 건너뜀")

    print(f"\n완료:")
    print(f"  제목    : {meta['title']}")
    print(f"  브랜드  : {meta.get('brand', 'unknown')}")
    print(f"  언어    : {transcript.get('language','unknown')} (소스: {transcript.get('source','unknown')})")
    print(f"  세그먼트: {len(transcript['segments'])}개")


if __name__ == "__main__":
    main()
