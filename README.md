# aisitei.github.io

IT之家 중국어 IT 뉴스를 매일 자동 수집·번역하여 게시하는 GitHub Pages 블로그입니다.
로컬 LM Studio(gemma-4-e4b)를 사용하며 외부 API에 의존하지 않습니다.

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
├── build.py                   ← 인덱스 페이지 빌더
├── articles/                  ← 생성된 기사 페이지
│   └── YYYY-MM/YYYY-MM-DD/
│       └── {slug}/
│           ├── index.html
│           └── images/
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

## 환경 설정

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
