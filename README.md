# aisitei.github.io

IT之家 중국어 IT 뉴스를 매일 자동 수집·번역하여 게시하는 GitHub Pages 블로그입니다.
로컬 LM Studio(gemma-4-e4b)를 사용하며 외부 API에 의존하지 않습니다.

이 저장소에는 두 가지 독립 파이프라인이 있습니다.

| 파이프라인 | 목적 | 입력 | 출력 |
|-----------|------|------|------|
| `crawler/` | IT뉴스 자동 수집·번역 | IT之家 RSS/HTML | `articles/` HTML 페이지 |
| `report_pipeline/` | YouTube 영상 심층 분석 리포트 | YouTube URL | `reports/` HTML 리포트 + 스크린샷 |

## 동작 흐름

```
IT之家 크롤링 → 키워드 필터링 → 중복 제거 → LM Studio 번역 → OCR → HTML 생성 → GitHub push
```

1. **수집** — IT之家 메인 페이지에서 최근 24시간 내 기사 크롤링
2. **필터링** — 카메라·스마트폰·AI·이미지센서 키워드 매칭, 제외 키워드(게임·가전·자동차 등)로 노이즈 차단
3. **중복 제거** — `article_id` 기준으로 이미 저장된 기사 건너뜀
4. **번역** — 제목·본문을 LM Studio(OpenAI 호환 엔드포인트)로 한국어 번역
5. **OCR** — 이미지 속 중국어 텍스트 추출 및 번역 (LM Studio 비전 모델)
6. **HTML 생성** — Jinja2 템플릿으로 기사 페이지 생성, `build.py`로 인덱스 페이지 재빌드
7. **배포** — `git commit & push` → GitHub Pages 자동 반영

## 수집 카테고리

| 카테고리 | 주요 키워드 |
|----------|------------|
| 📷 카메라·이미징 | 摄影, 相机, 镜头, Sony/Canon/Nikon/DJI 등 |
| 📱 스마트폰 | 手机, Xiaomi/Huawei/Samsung/Apple 등 |
| 🤖 AI | AI, 大模型, 多模态 (카메라·스마트폰 맥락 한정) |
| 🔬 이미지센서 | CMOS, IMX, 图像传感器, 半导体 등 |

## 폴더 구조

```
aisitei.github.io/
├── crawler/                   ← 자동화 크롤러
│   ├── main.py                ← 파이프라인 진입점
│   ├── reprocess_article.py   ← 단일 기사 재처리
│   ├── config.py              ← 설정 (키워드·LM Studio·GitHub)
│   ├── scraper.py             ← IT之家 크롤링·중복 필터
│   ├── translator.py          ← LM Studio 번역
│   ├── ocr.py                 ← 이미지 OCR
│   ├── html_generator.py      ← 기사 HTML 생성
│   ├── deployer.py            ← git commit & push
│   ├── glossary.json          ← 고유명사 단어장
│   └── logs/                  ← 실행 로그
├── report_pipeline/           ← YouTube 영상 리포트 파이프라인
│   ├── run_report.py          ← 전체 파이프라인 오케스트레이터
│   ├── step1_transcribe.py    ← 자막 다운로드 + mlx-whisper 전사
│   ├── step2_preprocess.py    ← 환각 제거·섹션 분류·스크린샷 후보
│   ├── step2b_bilingual.py    ← LM Studio 한국어 번역
│   ├── step2c_merge.py        ← LLM 완성 문장 병합
│   ├── step2d_suggest.py      ← LLM 스크린샷 후보 추천
│   ├── step3_screenshots.py   ← yt-dlp + ffmpeg 스크린샷 캡쳐
│   ├── step4_report.py        ← HTML 리포트 생성
│   ├── report_template.html   ← 다크 테마 HTML 템플릿
│   ├── corrections.json       ← Whisper 오인식 보정 사전
│   ├── camera_terms.json      ← 카메라 용어 사전
│   └── requirements.txt       ← Python 의존성
├── build.py                   ← 인덱스 페이지 빌더
├── articles/                  ← 생성된 기사 페이지
│   └── YYYY-MM/YYYY-MM-DD/
│       └── {slug}/
│           ├── index.html
│           └── images/
├── reports/                   ← 생성된 리포트 (report_pipeline 출력)
│   └── YYYY-MM-DD-brand-slug/
│       ├── report.html
│       └── images/
├── index.html                 ← 메인 목록 (build.py 생성)
└── reports.html               ← 리포트 목록 (build.py 생성)
```

## 실행 방법

### 즉시 실행 (수동)

```bash
cd crawler
python3 main.py --run
```

### 스케줄 모드 (프로세스 상주)

```bash
cd crawler
python3 main.py           # config.SCHEDULE_TIME (기본 07:00) 에 실행
```

### macOS 자동 실행 (launchd)

매일 오전 7시 자동 실행으로 등록되어 있습니다.

```bash
# 상태 확인
launchctl list | grep com.aisitei.crawler

# 제거
bash crawler/uninstall_launchd.sh
```

plist 위치: `~/Library/LaunchAgents/com.aisitei.crawler.plist`

### 단일 기사 재처리

특정 기사를 번역·OCR 재실행 후 push합니다.

```bash
cd crawler
python3 reprocess_article.py https://www.ithome.com/0/941/115.htm
```

---

## 리포트 파이프라인 (report_pipeline)

YouTube 스마트폰 발표 영상 URL 하나로 한국어 HTML 리포트를 완전 자동 생성합니다.
mlx-whisper(Apple Silicon)로 로컬 전사하고 LM Studio로 번역·분석하며 외부 API를 사용하지 않습니다.

### 처리 흐름

```
YouTube URL
  │
  ├─ Step 1  자막 다운로드 (yt-dlp)
  │          └─ 없으면 mlx-whisper 음성 전사 (VAD 청크 분할 + 환각 필터)
  │
  ├─ Step 2  전처리
  │          ├─ Whisper 오인식 보정 (corrections.json)
  │          ├─ 환각 세그먼트 제거 (글로벌 반복구·내부반복·연속중복)
  │          ├─ 섹션 분류 (카메라/디스플레이/배터리 등 12개 카테고리)
  │          └─ 키워드 기반 스크린샷 후보 추출
  │
  ├─ Step 2b LM Studio 한국어 번역 (배치, 중→한 / 영→한)
  │          └─ bilingual_transcript.txt, camera_transcript.txt
  │
  ├─ Step 2c LLM 완성 문장 병합 (GROUP: 포맷)
  │          └─ merged_transcript.txt, camera_merged_transcript.txt
  │
  ├─ Step 2d LLM 스크린샷 후보 재추천 (SHOT: 포맷)
  │          └─ screenshot_suggestions.txt 덮어쓰기
  │
  ├─ Step 3  영상 다운로드 (yt-dlp 720p) + ffmpeg 프레임 캡쳐
  │          └─ images/screenshot_NNN.jpg
  │
  └─ Step 4  HTML 리포트 생성
             ├─ Executive Summary (LLM 요약)
             ├─ 12개 섹션 (디자인·카메라·디스플레이·성능·배터리 등)
             └─ report.html (스크린샷 임베드 포함)
```

### 사전 준비

```bash
# Python 의존성
pip install -r report_pipeline/requirements.txt

# 외부 CLI 도구 (macOS)
brew install yt-dlp ffmpeg

# LM Studio 실행 후 gemma4:e4b 모델 로드 (포트 1234)
```

### 실행

```bash
# 기본 실행 (출력 경로 자동 생성: reports/YYYY-MM-DD-brand-slug/)
python3 report_pipeline/run_report.py https://youtu.be/XXXX

# 스크린샷 없이 리포트만
python3 report_pipeline/run_report.py https://youtu.be/XXXX --skip-screenshots

# 특정 출력 디렉토리 지정
python3 report_pipeline/run_report.py https://youtu.be/XXXX --output-dir reports/my-report

# 완료된 스텝 재실행 (강제)
python3 report_pipeline/run_report.py https://youtu.be/XXXX --force
```

### 주요 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--model` | `gemma4:e4b` | LM Studio 모델명 |
| `--api-url` | `http://localhost:1234/v1` | LM Studio 엔드포인트 |
| `--skip-screenshots` | off | Step 3 스크린샷 캡쳐 건너뜀 |
| `--force` | off | 완료된 스텝도 재실행 |
| `--no-cleanup` | off | 전사 후 영상 파일 자동 삭제 안 함 |
| `--output-dir` | 자동 | 출력 디렉토리 직접 지정 |

### 환각 방지 처리

mlx-whisper 전사 시 적용되는 3단계 환각 억제:

1. **VAD 청크 분할** — Silero VAD로 발화 구간만 추출, 최대 10분 단위로 전사 → BGM/무음 구간 환각 원천 차단
2. **`_HALLUCINATION_RE` 필터** — 느낌표 전용 줄, 展示 반복, 구절 반복, !+한자 패턴 즉시 제거
3. **`condition_on_previous_text=False`** — 청크 간 이전 텍스트 의존성 차단 → 환각 전파 방지

번역·병합 단계에서는 글로벌 반복구(전체 7% 이상 출현), 내부 반복 패턴, 60초 초과 병합을 추가로 필터링합니다.

### 출력 파일

```
reports/YYYY-MM-DD-brand-slug/
├── report.html                  ← 최종 한국어 HTML 리포트
├── meta.json                    ← 영상 메타데이터
├── transcript.json              ← 원본 전사 결과
├── bilingual_transcript.txt     ← 원문+한국어 세그먼트
├── merged_transcript.txt        ← 완성 문장 단위 병합본
├── screenshot_suggestions.txt   ← LLM 추천 스크린샷 타임스탬프
├── images/
│   ├── screenshot_001.jpg
│   ├── screenshot_002.jpg
│   └── screenshot_mapping.txt
└── .work/                       ← 임시 파일 (완료 후 자동 삭제)
```

---

## 환경 설정 (crawler)

환경변수 또는 `crawler/config.py` 직접 수정으로 설정합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio 엔드포인트 |
| `LLM_MODEL` | `google/gemma-4-e4b` | 번역 모델 |
| `LLM_VISION_MODEL` | (LLM_MODEL과 동일) | OCR 비전 모델 |
| `OCR_ENABLED` | `true` | OCR 활성화 여부 |
| `OCR_BACKEND` | `llm` | `llm` 또는 `mcp` |
| `SCHEDULE_TIME` | `07:00` | 자동 실행 시각 |

## OCR 특이사항

- **WebP 자동 변환** — `.jpg`로 저장된 WebP 파일을 JPEG으로 변환 후 전송
- **긴 텍스트 처리** — 60자 미만: 캡션 프롬프트(max 192 tokens), 60자 이상: 스펙 목록 프롬프트(max 2048 tokens)
- **CDN 만료 폴백** — CDN URL 만료 시 로컬 저장 이미지로 자동 재시도
- **API retry** — 호출 실패 시 최대 3회 재시도 (2s → 4s → 8s 지수 백오프)

## 의존성 설치

```bash
cd crawler
pip install -r requirements.txt
```

## LM Studio 준비

1. LM Studio 실행 후 `google/gemma-4-e4b` (또는 비전 지원 모델) 로드
2. Local Server 탭에서 서버 시작 (기본 포트 1234)
3. 비전 OCR 사용 시 멀티모달 모델 로드 필요
