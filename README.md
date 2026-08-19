# aisitei.github.io

IT之家(중국어)·Gizmochina(영어) IT 뉴스를 매일 자동 수집·**4개 언어(한/중/일/영)**로 번역해
게시하는 GitHub Pages 블로그입니다. 번역은 **하이브리드 모드**로 동작합니다 —
한국어는 클라우드 API(Gemini)로 빠르게 발행하고, 나머지 언어는 로컬 LM Studio로
비용 없이 뒤이어 채웁니다.

이 저장소에는 두 가지 독립 파이프라인이 있습니다.

| 파이프라인 | 목적 | 입력 | 출력 |
|-----------|------|------|------|
| `crawler/` | IT뉴스 자동 수집·4개 언어 번역 | IT之家/Gizmochina | `articles/` HTML 페이지 |
| `report_pipeline/` | YouTube 영상 심층 분석 리포트 | YouTube URL | `reports/` HTML 리포트 + 스크린샷 |

## 동작 흐름 (하이브리드 2단계)

매일 07:00 launchd가 `crawler/main.py --run`을 실행하면, 같은 프로세스 안에서
**Phase A → 다이제스트 메일 → Phase B** 순서로 진행됩니다.

```
IT之家/Gizmochina 크롤링 → 키워드 필터링 → 중복 제거
  │
  ├─ Phase A (클라우드 Gemini, ~건당 8~12초)
  │    ko 제목·본문 번역 → 저장(4개 탭 모두 ko 폴백) → git push
  │    └─ 이메일 다이제스트 발송 (오늘 발행 기사 전체, en/ja/zh 백필 전)
  │
  └─ Phase B (로컬 LM Studio, ~건당 6분 — backfill_multilang.py 재사용)
       en/ja/zh 실제 번역으로 교체 → OCR 캡션 → build.py 재빌드 → git push
```

1. **수집** — IT之家 메인 페이지 + Gizmochina RSS 최근 24시간 내 기사 크롤링, 브랜드/모델 기준 교차 소스 중복 제거
2. **필터링** — 카메라·스마트폰·AI·이미지센서 키워드 매칭, 제외 키워드(게임·가전·자동차·앱 튜토리얼 등)로 노이즈 차단
3. **중복 제거** — `article_id`/원문 URL 기준으로 이미 저장된 기사 건너뜀
4. **Phase A (ko)** — 제목·본문을 클라우드 LLM(Gemini 2.5 Flash, `GEMINI_API_KEY` 있을 때)으로 한국어 번역, 즉시 저장·push
5. **다이제스트 메일** — Phase A 직후, en/ja/zh 백필 시작 *전에* 그날 발행분 전체를 정리해 이메일 발송 (아래 [이메일 다이제스트](#이메일-다이제스트) 참고)
6. **Phase B (en/ja/zh)** — `backfill_multilang.py`가 로컬 LM Studio로 나머지 3개 언어 번역, 큐/완료 로그로 재시작 가능
7. **OCR** — 이미지 속 중국어 텍스트 추출 및 4개 언어 캡션 번역 (로컬 Tesseract, 기본값)
8. **HTML 생성** — 기사 페이지 생성, `build.py`로 인덱스 페이지 재빌드 (Phase A/B 각 push마다 자동 실행)
9. **배포** — `git commit & push` → GitHub Pages 자동 반영

`--ko-only` 플래그를 주면 Phase A만 실행하고 멈춥니다(en/ja/zh는 나중에 `python3 backfill_multilang.py`를 직접 실행).

### 실측 성능 (2026-08-18/19)

| Phase | 소요시간 | 건당 | 비고 |
|-------|---------|------|------|
| Phase A (Gemini 2.5 Flash) | 3~4분 (20~30건 기준) | ~8~12초 | 클라우드, 비용 발생(약 $0.4/일) |
| Phase B (로컬 LM Studio) | 2~3시간 (20~30건 기준) | ~6분 | 무료, en/ja/zh 3개 언어 순차 번역 |

Phase A가 Phase B보다 약 **30~40배** 빠릅니다. 07:00 실행 시 다이제스트 메일은 보통 07:03~07:05 사이 발송되고, 전체(en/ja/zh까지) 완료는 09~10시경입니다.

## 수집 카테고리

| 카테고리 | 주요 키워드 |
|----------|------------|
| 📷 카메라·이미징 | 摄影, 相机, 镜头, Sony/Canon/Nikon/DJI 등 |
| 📱 스마트폰 | 手机, Xiaomi/Huawei/Samsung/Apple 등 |
| 🤖 AI | AI, 大模型, 多模态 (카메라·스마트폰 맥락 한정) |
| 🔬 이미지센서 | CMOS, IMX, 图像传感器, 半导体 등 |

## 이메일 다이제스트

Phase A 완료 직후(en/ja/zh 백필 시작 전) 그날 발행된 기사 전체를 정리해
지메일 SMTP로 발송합니다. 신문/뉴스레터 스타일 HTML — 편당 썸네일(cid 임베딩,
Pillow로 축소)·제목·바로가기 링크를 표로 나열하며, 모바일 반응형(미디어쿼리)입니다.

- 발신 모듈: `crawler/emailer.py`
- 기사 0건이면 발송 스킵, SMTP 실패해도 예외를 삼켜 파이프라인 자체는 실패 처리하지 않음
- 설정: `crawler/.env.local`의 `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`/`DIGEST_RECIPIENT`
  (자세한 내용은 [환경 설정](#환경-설정-crawler) 참고)

## 브랜드명 단어장 (glossary.json)

LLM이 생소한 중국 브랜드명을 임의로 지어내는(hallucination) 문제를 막기 위해
`crawler/glossary.json`에 중국어→한/영 매핑을 유지합니다. 번역 전 소스 텍스트에
직접 치환 적용되고, 프롬프트에도 참고 테이블로 주입됩니다.

```json
"brands": {
  "小米": "Xiaomi",
  "玄戒": "XRING",
  "星曜": "Brightin Star"
}
```

이미 발행된 기사에서 브랜드명 오역이 발견되면: (1) 해당 기사의 제목/본문을 웹 검색으로
확인한 정확한 이름으로 수정, (2) `glossary.json`에 항목 추가해 재발 방지. 지금은 발견 시
수동으로 처리하고 있고(자동 웹서칭 파이프라인은 별도 검토 필요), `ko_only` 섹션은
한국어 출력 전용 예외 표기(예: 宏碁→에이서)로 다른 언어에는 적용되지 않습니다.

## 손상 기사 복구

`multilang_reprocess.py` 계열 스크립트의 과거 버그로 일부 기사의 ko 섹션에 4개
언어 콘텐츠가 섞여 저장된 손상 사례가 발견되어, git 히스토리를 신뢰하지 않고
**원문 URL을 다시 스크레이핑**해 ko부터 재번역하는 `crawler/recover_from_source.py`로
복구합니다.

```bash
cd crawler
python3 recover_from_source.py --sleep 6   # 원문 사이트 차단 방지용 딜레이
python3 backfill_multilang.py              # 이어서 en/ja/zh 백필
```

원문 사이트(IT之家)가 짧은 시간에 과도한 요청을 감지하면 정상 페이지도 가짜 404로
응답하는 사례가 있었습니다 — 대량 복구 시 `--sleep`을 충분히 주고, 실패가 몰리면
시간을 두고 재시도하세요.

## 폴더 구조

```
aisitei.github.io/
├── crawler/                   ← 자동화 크롤러
│   ├── main.py                ← 파이프라인 진입점 (Phase A/B 오케스트레이션)
│   ├── backfill_multilang.py  ← Phase B: en/ja/zh 백필 (큐 기반, 재시작 가능)
│   ├── recover_from_source.py ← 손상 기사 복구 (원문 재스크레이핑)
│   ├── emailer.py             ← 다이제스트 이메일 생성·발송
│   ├── env_local.py           ← .env.local 로더 (launchd는 ~/.zshrc를 못 봄)
│   ├── reprocess_article.py   ← 단일 기사 재처리
│   ├── config.py              ← 설정 (키워드·LLM·GitHub)
│   ├── scraper.py             ← IT之家 크롤링·중복 필터
│   ├── scraper_gizmochina.py  ← Gizmochina RSS/페이지 크롤링
│   ├── translator.py          ← LLM 번역 (로컬/클라우드 겸용)
│   ├── ocr.py                 ← 이미지 OCR
│   ├── html_generator.py      ← 기사 HTML 생성
│   ├── deployer.py            ← git commit & push (+ build.py 재실행)
│   ├── glossary.json          ← 고유명사 단어장
│   ├── .env.local             ← API 키·메일 계정 (git 미포함)
│   ├── .env.local.example     ← 위 파일 템플릿
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
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio(로컬) 엔드포인트 |
| `LLM_MODEL` | `google/gemma-4-12b` | 로컬 번역 모델 (Phase B) |
| `LLM_API_KEY` / `LLM_EXTRA_BODY` | — | 클라우드 API 오버라이드 (직접 지정 시) |
| `LLM_VISION_MODEL` | (LLM_MODEL과 동일) | OCR 비전 모델 (`OCR_BACKEND=llm`일 때만) |
| `OCR_ENABLED` | `true` | OCR 활성화 여부 |
| `OCR_BACKEND` | `tesseract` | `tesseract`(기본, 로컬·무료) / `llm` / `mcp` |
| `SCHEDULE_TIME` | `07:00` | 자동 실행 시각 |
| `SITE_URL` | `https://aisitei.github.io` | 다이제스트 메일 기사 링크 생성용 |

### `.env.local` (Phase A 클라우드 + 이메일 발송)

launchd는 로그인 셸을 거치지 않아 `~/.zshrc`의 `export`를 못 봅니다. 클라우드 API 키와
메일 계정 정보는 `crawler/.env.local`(git 미포함, `.env.local.example`이 템플릿)에
직접 저장하면 `main.py` 시작 시 `env_local.py`가 읽어 프로세스 환경에 주입합니다.

```bash
cp crawler/.env.local.example crawler/.env.local
# 값 채우기: GEMINI_API_KEY, GMAIL_ADDRESS, GMAIL_APP_PASSWORD, DIGEST_RECIPIENT
```

| 변수 | 설명 |
|------|------|
| `GEMINI_API_KEY` | Phase A(ko 번역)를 클라우드로 돌릴 때 사용. 없으면 로컬 LLM으로 자동 대체 |
| `GMAIL_ADDRESS` | 다이제스트 메일 발신 지메일 주소 |
| `GMAIL_APP_PASSWORD` | 구글 계정 → 보안 → 2단계 인증 → 앱 비밀번호에서 발급 |
| `DIGEST_RECIPIENT` | 다이제스트 메일 수신자 (비우면 `GMAIL_ADDRESS` 자기 자신) |

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

## LM Studio 준비 (Phase B / 로컬 전용 실행 시)

1. LM Studio 실행 후 `google/gemma-4-12b` (또는 원하는 번역 모델) 로드
2. Local Server 탭에서 서버 시작 (기본 포트 1234)
3. OCR은 기본이 로컬 Tesseract라 LM Studio 비전 모델이 필수는 아님
   (`OCR_BACKEND=llm`로 바꿀 때만 멀티모달 모델 필요)

Phase A(ko 번역)를 클라우드로 돌리려면 `crawler/.env.local`에 `GEMINI_API_KEY`만
채우면 되고, 이 경우 LM Studio는 Phase B(en/ja/zh)에만 필요합니다.
