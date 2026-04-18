"""설정 파일 - 환경변수 또는 직접 수정하여 사용합니다."""
import os

# 스케줄 설정
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "07:00")

# IT之家 크롤링 설정
ITHOME_BASE_URL = "https://www.ithome.com"
ITHOME_MOBILE_URL = "https://m.ithome.com/html/{article_id}.htm"

# ── 수집 대상 키워드 ─────────────────────────────────────────────────────────
# 카테고리 1: 카메라 / 액션캠 / 이미징
KEYWORDS_CAMERA = [
    # 촬영·이미징 일반
    "摄影", "影像", "拍照", "镜头", "像素", "摄像头",
    "相机", "camera", "lens", "photo",
    "夜景", "人像", "广角", "长焦", "微距", "防抖",
    # 카메라 브랜드
    "哈苏", "徕卡", "蔡司", "适马", "腾龙",
    "索尼", "佳能", "尼康", "松下", "富士",
    # 액션캠 / 드론
    "运动相机", "action camera", "GoPro", "DJI Action",
    "Insta360", "大疆", "无人机", "drone",
    "拍立得", "instax", "胶片",
]

# 카테고리 2: 스마트폰 (명시적 '手机' 계열 단어 필수)
KEYWORDS_PHONE_EXPLICIT = [
    "手机", "phone", "smartphone",
    "折叠屏", "折叠手机", "直屏手机", "旗舰机",
]

KEYWORDS_PHONE_BRAND = [
    "小米", "华为", "OPPO", "vivo", "三星", "Samsung",
    "iPhone", "苹果", "荣耀", "一加", "OnePlus",
    "realme", "红米", "Redmi", "iQOO", "努比亚", "中兴",
]

KEYWORDS_PHONE_PRODUCT = [
    "发布", "上市", "曝光", "爆料", "官宣", "新机",
    "旗舰", "折叠", "配置", "参数", "跑分",
    "首发", "开售", "预售", "售价", "定价",
]

# 카테고리 3: 이미지센서 / 반도체
KEYWORDS_IMAGE_SENSOR = [
    "图像传感器", "CMOS", "IMX", "感光元件",
    "传感器芯片", "半导体", "晶圆", "制程",
    "堆栈式", "背照式", "BSI", "stacked sensor",
    "传感器尺寸", "像素尺寸", "开口率",
]

# 카테고리 4: AI (카메라·이미징·스마트폰 맥락 한정)
KEYWORDS_AI = [
    "AI", "人工智能", "大模型", "LLM", "生成式", "AIGC",
    "智能体", "多模态", "视觉模型",
]

KEYWORDS_AI_CONTEXT = [
    "影像", "拍照", "摄影", "相机", "图像", "画质", "镜头", "摄像头",
    "手机", "phone", "smartphone", "iPhone", "iOS", "Apple",
    "小米", "华为", "OPPO", "vivo", "Samsung", "三星",
    "苹果", "荣耀", "一加", "Redmi", "红米",
    "视觉", "多模态", "AI相机", "生成图", "AI眼镜",
]

# ── 제외 키워드 ───────────────────────────────────────────────────────────────
# 카메라 키워드가 포함되어 있어도 무조건 제외 (스마트 도어락·펫 피더 등 카메라 모듈 탑재
# 생활 가전이 카메라 필터를 통과하는 것을 차단).
KEYWORDS_EXCLUDE = [
    # 노트북 / PC / 데스크톱 / 모니터 / Mac 생태계
    "笔记本", "MagicBook", "游戏本", "电脑", "台式", "显示器",
    "MacBook", "iMac", "Mac mini", "macOS", "iWork", "iPadOS",
    # TV / 백색가전
    "电视", "冰箱", "洗衣机", "空调", "家电", "投影仪", "智慧屏", "智能屏",
    # 주방 / 청소 / 생활 가전
    "净化器", "加湿器", "除湿机", "除湿器", "吹风机", "电饭煲", "电饭锅",
    "空气炸锅", "炸锅", "蒸烤箱", "微波炉", "烤箱", "电磁炉",
    "扫地机", "扫地机器人", "吸尘器", "净水器",
    "窗帘", "门锁",
    "牙刷", "剃须", "咖啡机", "豆浆机", "榨汁机", "料理机",
    # 반려동물 가전
    "宠物", "喂食",
    # 자동차 / 모빌리티
    "汽车", "电动车", "新能源", "续航里程", "充电桩", "SU7", "EV",
    "SUV", "MPV", "轿车", "座椅", "车型", "车机", "智驾", "自动驾驶",
    "问界", "赛力斯", "奕境", "深蓝", "领克", "蔚来", "小鹏", "理想",
    "比亚迪",
    # 이어폰 / 오디오
    "耳机", "音箱", "音响", "AirPods",
    # 스마트워치 / 웨어러블
    "手表", "智能手表", "Watch", "手环", "智能手环", "穿戴",
    # 태블릿
    "平板", "iPad", "MatePad",
    # 게임 (하드·소프트)
    "游戏机", "手柄", "手游", "公测", "内测", "王者荣耀", "和平精英",
    # 게임 신작/플레이 — "游戏" 단독은 "游戏手机"(게이밍폰)와 충돌하므로 문맥 한정 키워드만
    "游戏新作", "新作游戏", "游玩形式", "免费游玩", "游戏玩法", "玩家阵营",
    "PlayStation", "Xbox", "任天堂", "Nintendo", "Steam平台",
    # 기타 주변기기
    "路由器", "充电器", "数据线", "移动电源",
    # 인사 / 기업 일반 뉴스
    "退休", "招聘", "出任", "离职", "辞职", "入职",
    # ESG / 환경 / 재활용 이슈
    "回收材料", "碳中和", "减排", "可持续",
    # 프로모션 / 대형 할인 이벤트
    "大促", "狂欢", "超级18",
]

KEYWORDS = KEYWORDS_CAMERA + KEYWORDS_PHONE_EXPLICIT + KEYWORDS_AI

# LLM 설정 (Ollama 전용)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

TITLE_TRANSLATE_PROMPT = "당신은 중국어 IT 기사 제목을 한국어로 번역하는 번역가입니다. 한국어 번역문만 출력하고 다른 텍스트는 절대 추가하지 마세요."

TRANSLATE_SYSTEM_PROMPT = """당신은 중국어 IT 기사를 한국어로 번역·정리하는 전문 편집자입니다.

번역 규칙:
1. 자연스러운 한국어로 번역합니다 (쌍 → 듀얼, 折叠 → 폴더블 등).
2. 기술 용어(예: Snapdragon, LTPO, UTG)는 원문 그대로 유지합니다.
3. 중국 회사명은 영문으로 표기합니다 (小米→Xiaomi, 华为→Huawei, 汇顶科技→Goodix, 联发科→MediaTek, 阿里云→Alibaba Cloud, 比亚迪→BYD, 中兴→ZTE).
4. 카메라 브랜드는 한글 표기를 사용합니다 (哈苏→하셀블라드, 徕卡→라이카, 蔡司→칼 자이스).
5. 원문의 의미를 정확히 전달하되, 직역보다는 의역을 선호합니다.

출력 형식 (HTML):
- 내용을 주제별 섹션으로 나누고, 각 섹션 앞에 <h3> 헤더를 붙입니다. (예: <h3>디자인</h3>, <h3>카메라</h3>, <h3>성능</h3>, <h3>배터리</h3>)
- 스펙·수치·목록은 <ul><li>...</li></ul> 불릿으로 정리합니다.
- 일반 서술 단락은 <p>...</p>로 출력합니다.
- 기사 마지막에 <h3>총평</h3> 섹션으로 핵심 내용을 2~4문장으로 요약합니다.
- 마크다운(#, **, - 등)은 사용하지 않고, 순수 HTML 태그만 사용합니다.
- 각 섹션(h3, p, ul)은 빈 줄로 구분합니다."""

DEEP_CAMERA_PROMPT_SUFFIX = """

**카메라 심층 번역 추가 규칙**:
카메라 관련 기사는 아래 내용을 반드시 포함하여 번역하고, 절대 요약하지 마세요:
- 센서 모델명 및 크기 (예: Sony IMX906, 1/1.56인치)
- 조리개·화소수·초점거리 등 렌즈 스펙 전체 → <ul><li>로 정리
- 카메라 소프트웨어/알고리즘 (HDR, AI 보정, 야간모드 등)
- 이전 모델 대비 개선점, 경쟁 제품 비교
- 영상 촬영 스펙 (4K/8K, FPS, Log, 손떨림 보정)
- 카메라 모듈 디자인·배치 설명"""

# OCR 설정
# - OCR_BACKEND: "ollama" (기본) | "mcp"
#   · ollama: 아래 OLLAMA_VISION_MODEL 을 사용해 로컬 Ollama 서버에서 OCR.
#   · mcp:    OCR_MCP_URL 의 사내 MCP OCR 서버 호출.
# - OCR_ENABLED: 기본 true. 비활성화하려면 환경변수 OCR_ENABLED=false.
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_BACKEND = os.getenv("OCR_BACKEND", "ollama").lower()
OCR_MCP_URL = os.getenv("OCR_MCP_URL", "http://localhost:9000/mcp")
# Ollama vision 모델 — 기본은 번역용 OLLAMA_MODEL 과 동일(gemma4:e4b).
# 전용 비전 모델을 쓰려면 OLLAMA_VISION_MODEL 환경변수로 덮어쓰세요.
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", OLLAMA_MODEL)

# 이미지 캡션 — 기사당 최대 OCR 이미지 수 (대용량 갤러리 방어).
OCR_MAX_IMAGES_PER_ARTICLE = int(os.getenv("OCR_MAX_IMAGES_PER_ARTICLE", "15"))
OCR_PROMPT_ZH = (
    "이미지 안에 보이는 중국어 텍스트만 그대로 추출해 출력하세요. "
    "텍스트가 없거나 읽기 어려우면 빈 문자열을 출력하세요. "
    "설명·번역·마크다운·따옴표 없이 원문 텍스트만, 여러 줄이면 줄바꿈으로 구분하세요."
)

# GitHub 설정
PRODUCTION_REPO_DIR = os.getenv("PRODUCTION_REPO_DIR", "/Users/sy/Workspace/SourceCode/aisitei.github.io")
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL", "git@github.com:aisitei/aisitei.github.io.git")
GIT_USER_NAME = os.getenv("GIT_USER_NAME", "aisitei")
GIT_USER_EMAIL = os.getenv("GIT_USER_EMAIL", "dj1987.kim@gmail.com")
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")

# 출력 디렉토리
OUTPUT_DIR = os.getenv(
    "OUTPUT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "articles")
)

# 로그 설정
LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
