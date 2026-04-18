# aisitei.github.io

`aisitei` GitHub Pages 블로그. 외부 콘텐츠 레포에서 기사/리포트를 자동으로 가져와 정적 페이지를 빌드·배포합니다.

## 동기화 소스

| 소스 레포 | 내용 | 동기화 경로 |
|-----------|------|-------------|
| [`aisitei/ITHOME`](https://github.com/aisitei/ITHOME) | IT之家 한국어 번역 뉴스 (📷/📱/🤖) | `report/YYYY-MM-DD/*.html` → `articles/YYYY-MM-DD/` |
| [`aisitei/cn-smartphone-analysis`](https://github.com/aisitei/cn-smartphone-analysis) | 중국 스마트폰 분석 리포트 | `reports/{name}/report.html` → `reports/{name}/` |

## 자동화 워크플로우 (`.github/workflows/sync-articles.yml`)

- **트리거**: 매일 KST 09:00 (UTC 00:00) 자동 실행, 수동 실행, 외부 `repository_dispatch` 이벤트
- **동작**:
  1. ITHOME 레포 체크아웃 후 `report/YYYY-MM-DD/` 또는 (구) 루트 `YYYY-MM-DD/` 폴더에서 HTML 수집
  2. cn-smartphone-analysis 레포 체크아웃 후 `reports/` 폴더 동기화
  3. `python build.py`로 인덱스/리스트 페이지 빌드
  4. 변경사항이 있으면 `github-actions[bot]` 명의로 자동 commit & push

### ITHOME 경로 호환성 (2026-04-07~)

ITHOME 레포가 루트 가독성을 위해 날짜 폴더를 `report/` 하위로 이동하면서, workflow의 glob을
양쪽 경로 모두 지원하도록 확장했습니다:

```bash
for dir in _ithome_source/20*-*-*/ _ithome_source/report/20*-*-*/; do
  ...
done
```

이 덕분에 마이그레이션 중에도 동기화가 끊기지 않으며, 결과물은 동일하게
`articles/YYYY-MM-DD/` 평탄 구조로 복사됩니다. 따라서 **블로그 URL은 변경되지 않습니다**.

## 폴더 구조

```
aisitei.github.io/
├── .github/workflows/sync-articles.yml   ← 동기화 워크플로우
├── build.py                              ← 인덱스/리스트 페이지 빌더
├── articles/                             ← ITHOME에서 동기화된 기사
│   └── YYYY-MM-DD/*.html
├── reports/                              ← cn-smartphone-analysis에서 동기화된 리포트
│   └── {report-name}/
│       ├── report.html
│       └── images/
└── index.html, ...                       ← 빌드 결과물
```

## 수동 동기화

GitHub Actions 탭에서 `Sync Blog Content` workflow를 선택하고 `Run workflow` 버튼을 눌러
즉시 동기화할 수 있습니다.
