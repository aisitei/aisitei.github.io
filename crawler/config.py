"""설정 파일 - 환경변수 또는 직접 수정하여 사용합니다."""
import os

# 스케줄 설정
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "07:00")

# IT之家 크롤링 설정
ITHOME_BASE_URL = "https://www.ithome.com"
ITHOME_MOBILE_URL = "https://m.ithome.com/html/{article_id}.htm"

# Gizmochina RSS 설정
GIZMOCHINA_FEED_URL = os.getenv("GIZMOCHINA_FEED_URL", "https://www.gizmochina.com/feed/")

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
    "风扇", "电风扇", "手持风扇", "便携风扇",  # 선풍기류
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
    # 게임 회사 / 캐릭터 (카메라 브랜드 키워드 우회 차단)
    "世嘉", "索尼克",  # SEGA, 索尼克(소닉)은 索尼 부분 문자열로 Sony 필터 통과 가능
    "万代", "南梦宫",  # Bandai Namco
    # 게임 신작/플레이 — "游戏" 단독은 "游戏手机"(게이밍폰)와 충돌하므로 문맥 한정 키워드만
    "游戏新作", "新作游戏", "游玩形式", "免费游玩", "游戏玩法", "玩家阵营",
    "PlayStation", "PS6", "PS5", "PS4", "PS Plus", "PlayStation Plus", "Xbox", "任天堂", "Nintendo", "Steam平台",
    "PSVR", "PS VR", "掌机",  # VR 게임기 / 휴대용 콘솔
    # 게이밍 주변기기 (홍마·레드매직 등 폰 브랜드 우회 차단)
    "电竞鼠标", "游戏鼠标",
    # 게임 장르 / 플랫폼 출시 표현
    "生活模拟", "模拟游戏", "抢先体验", "登陆PS", "登陆Xbox",
    "派对游戏", "社交游戏", "联机游戏", "多人游戏",
    # 게임 앱 플랫폼 출시 (화웨이 앱마켓·샤오미 앱 등 브랜드 키워드 우회 차단)
    "游戏上线", "游戏正式上线", "游戏版本", "鸿蒙版游戏",
    # 영화 / 영화관 / 헐리우드 IP (镜头 등 카메라 키워드 우회 방지)
    "电影", "导演", "档期", "票房", "上映", "院线",  # 영화 일반
    "迪士尼", "漫威", "复联", "终局之战", "重映", "影院", "巨幕", "银幕",
    "Marvel", "Disney", "Pixar",
    # 군사 / 국방 (无人机 키워드 우회 방지)
    "美军", "军方", "军舰", "舰艇", "国防部", "军用", "蜂群", "战机", "导弹",
    # 기타 주변기기
    "路由器", "充电器", "数据线", "移动电源",
    # 인사 / 기업 일반 뉴스
    "退休", "招聘", "出任", "离职", "辞职", "入职",
    # ESG / 환경 / 재활용 이슈
    "回收材料", "碳中和", "减排", "可持续",
    # 프로모션 / 대형 할인 이벤트
    "大促", "狂欢", "超级18",
    "618",              # 618 쇼핑 축제 (징둥 기념일 할인)
    "双十一", "双11",   # 광군제 (11/11 쇼핑 축제)
    "史低", "历史低价", # 역대 최저가 — 항상 프로모션 맥락
    "清仓", "甩卖",     # 재고 정리 / 처분
    "直降", "降价",     # 직접 가격 인하 / 가격 인하 프로모션
    "腰斩", "新低", "跳水", "骨折价",  # 반값·신저가·폭락·초저가 표현
    "秒杀",             # 타임세일 (초특가)
    "国补",             # 중국 정부 보조금 할인 프로모션
    "优惠券",           # 쿠폰 행사
    "服务周",           # 서비스 위크 (배터리 교체 할인 등)
    # 프린터 / 복합기 (佳能·Canon 등 카메라 브랜드 키워드 우회 차단)
    "打印机", "复印机", "喷墨", "激光打印", "PIXMA",
    # EV 배터리 규격 (松下·파나소닉 등 키워드 우회 차단)
    "4680", "圆柱电池", "圆柱形电池",
    # 차량용 모터·액추에이터 사업 (카메라 브랜드 우회 차단)
    "车载电机", "冷却风扇电机", "电机业务",
    # 정부 보상판매 정책 (이커머스 프로모션 맥락)
    "以旧换新",
    # 서비스 약관 / 계정 정책
    "服务条款",
    # 오프라인 매장 이벤트 / 프로모션
    "橙色星期四",
    # PS 실물 디스크 (게임 콘텐츠 맥락)
    "实体盘",
    # 게임 PC 이식 / 독점 전략 (카메라 브랜드 우회 차단)
    "PC移植",
    # 야생동물 / 자연재해 (IT 무관)
    "熊出没", "熊袭",
]

# ── 복합 제외 규칙 ─────────────────────────────────────────────────────────────
# require_any 중 하나 AND also_any 중 하나가 모두 제목에 있으면 제외.
# 단독 키워드로는 너무 넓은 경우(Sony는 카메라 브랜드이지만 PSN 맥락일 때만 제외 등)에 사용.
KEYWORDS_EXCLUDE_COMPOUND: list[dict] = [
    {
        "comment": "索尼/Sony + 游戏 → 제외 (카메라 브랜드이지만 게임 맥락 기사 차단)",
        "require_any": ["索尼", "sony"],
        "also_any": ["游戏"],
    },
    {
        "comment": "索尼/Sony + 独占 → 제외 (PlayStation 독점 전략 기사)",
        "require_any": ["索尼", "sony"],
        "also_any": ["独占"],
    },
    {
        "comment": "索尼/Sony + 账号/登录 → 제외 (PSN 계정 정책 기사)",
        "require_any": ["索尼", "sony"],
        "also_any": ["账号", "登录"],
    },
    {
        "comment": "游戏 + 스마트폰 브랜드 플랫폼 출시 → 제외 (게임 앱이 폰 브랜드 키워드 통해 수집되는 것 차단)",
        "require_any": ["游戏"],
        "also_any": [
            "鸿蒙版", "正式上线", "公测上线", "开启公测", "首发上线",
            "上架", "应用商店", "AppGallery",
        ],
    },
]

KEYWORDS = KEYWORDS_CAMERA + KEYWORDS_PHONE_EXPLICIT + KEYWORDS_AI

# ── Gizmochina 영어 키워드 ────────────────────────────────────────────────────

# 카메라 / 이미징
KEYWORDS_CAMERA_EN = [
    "camera", "lens", "sensor", "megapixel", "aperture", "zoom",
    "mirrorless", "dslr", "action cam", "action camera",
    "gopro", "insta360", "dji action", "instax", "film camera",
    "telephoto", "wide-angle", "macro", "night mode", "portrait mode",
    "periscope", "lidar", "optical image stabilization", "ois",
    "imaging", "photography",
]

# 이미지 센서 / 반도체
KEYWORDS_IMAGE_SENSOR_EN = [
    "image sensor", "cmos sensor", "imx", "isocell",
    "semiconductor", "wafer", "chip fabrication",
    "stacked sensor", "bsi sensor",
]

# 스마트폰 명시 키워드
KEYWORDS_PHONE_EXPLICIT_EN = [
    "smartphone", "phone", "handset", "foldable phone", "flip phone",
    "flagship phone", "android phone",
]

# 스마트폰 출시/제품 키워드
KEYWORDS_PHONE_PRODUCT_EN = [
    "launched", "launch", "released", "release", "announced", "unveil",
    "unveiled", "hands-on", "first look", "review", "leaked", "leak",
    "specs", "specifications", "price", "sale", "pre-order",
]

# AI 키워드
KEYWORDS_AI_EN = [
    "ai", "artificial intelligence", "on-device ai", "generative ai",
    "llm", "large language model", "neural network", "machine learning",
]

# AI 맥락 (카메라·스마트폰 맥락 한정)
KEYWORDS_AI_CONTEXT_EN = [
    "camera", "photo", "image", "smartphone", "phone", "iphone",
    "samsung", "xiaomi", "huawei", "pixel", "visual", "imaging",
    "android", "ios",
]

# 영어 제외 키워드
KEYWORDS_EXCLUDE_EN = [
    # 게임 하드웨어·소프트웨어
    "playstation", "xbox", "nintendo", "steam", "ps5", "ps6", "ps plus",
    "gaming console", "game release", "game launch", "game review",
    "gaming mouse", "gaming keyboard", "gaming headset", "gaming monitor",
    # 노트북 / PC / 데스크톱
    "laptop", "notebook", "desktop pc", "gaming pc", "imac", "macbook",
    "mac mini", "mac pro",
    # TV / 모니터 / 프로젝터
    "television", " tv ", "smart tv", "oled tv", "projector",
    # 이어폰 / 오디오
    "earbuds", "headphones", "earphones", "tws earbuds",
    "speaker", "soundbar", "airpods",
    # 스마트워치 / 웨어러블
    "smartwatch", "smart watch", "fitness band", "wearable",
    # 태블릿
    "tablet", "ipad", "android tablet",
    # 자동차 / EV
    "electric vehicle", "ev car", "self-driving", "autonomous car",
    # 기타 주변기기
    "router", "charger", "power bank", "cable",
    # 군사 / 국방
    "military", "defense", "weapon", "missile",
]

# LLM 설정 (LM Studio, OpenAI 호환 로컬 서버)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemma-4-12b")
# 주 모델이 think 블록만 반환할 때 자동 전환할 폴백 모델
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "google/gemma-3-4b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")

TITLE_TRANSLATE_PROMPT = """당신은 중국어 IT 기사 제목을 한국어로 번역하는 번역가입니다. 한국어 번역문만 출력하고 다른 텍스트는 절대 추가하지 마세요.

제목 번역 규칙:
1. 브랜드·제품명: 一加→원플러스, 至尊版→엘리트(Elite), 骁龙→스냅드래곤, 天玑→디멘시티.
2. 라틴 문자 브랜드명(vivo, OPPO, realme, iQOO 등)은 절대 음역하지 말고 원문 그대로 표기합니다.
3. 가격 표기: 중국 위안(元/元/¥)은 반드시 '위안'으로 표기합니다. '원(₩)'으로 쓰지 마세요.
4. 国补(국가보조금): '국보(정부 보조금)'로 표기합니다.
5. 자연스러운 한국어 어순으로 재구성합니다 (예: "[제품명] [용량], [혜택] [가격]위안 — [칩셋] 탑재").
6. '폰' 대신 '스마트폰'을 사용합니다."""

TRANSLATE_SYSTEM_PROMPT = """당신은 중국어 IT 기사를 한국어로 번역·정리하는 전문 편집자입니다.

번역 규칙:
1. 자연스러운 한국어로 번역합니다 (쌍 → 듀얼, 折叠 → 폴더블 등).
2. 기술 용어(예: Snapdragon, LTPO, UTG)는 원문 그대로 유지합니다.
3. 중국 회사명은 영문으로 표기합니다 (小米→Xiaomi, 华为→Huawei, 汇顶科技→Goodix, 联发科→MediaTek, 阿里云→Alibaba Cloud, 比亚迪→BYD, 中兴→ZTE).
4. 라틴 문자 브랜드명(vivo, OPPO, realme, iQOO 등)은 절대 음역하지 말고 원문 그대로 표기합니다.
5. 카메라 브랜드는 한글 표기를 사용합니다 (哈苏→하셀블라드, 徕卡→라이카, 蔡司→칼 자이스).
6. 원문의 의미를 정확히 전달하되, 직역보다는 의역을 선호합니다.
7. **원문에 없는 수치·스펙·사실은 절대 추가하지 마세요.** 모델이 학습 데이터로 알고 있는 제품 스펙이라도 원문에 없으면 포함 금지입니다.

출력 형식 (HTML):
- 내용을 주제별 섹션으로 나누고, 각 섹션 앞에 <h3> 헤더를 붙입니다. (예: <h3>디자인</h3>, <h3>카메라</h3>, <h3>성능</h3>, <h3>배터리</h3>)
- 스펙·수치·목록은 <ul><li>...</li></ul> 불릿으로 정리합니다. 단, 원문에 실제로 나열된 항목만 불릿으로 만드세요.
- 일반 서술 단락은 <p>...</p>로 출력합니다.
- 기사 마지막에 <h3>총평</h3> 섹션으로 핵심 내용을 2~4문장으로 요약합니다. 반드시 원문에 있는 내용만 바탕으로 작성하세요.
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
# - OCR_BACKEND: "tesseract" (기본) | "llm" | "mcp"
#   · tesseract: 로컬 Tesseract(chi_sim+eng)로 OCR. vision-LLM 대비 100배+ 빠르고
#     LM Studio 리소스를 안 쓰며, 텍스트 없는 이미지에 캡션을 지어내는 할루시네이션도 없음.
#   · llm: LM Studio의 LLM_VISION_MODEL 을 사용해 OCR.
#   · mcp: OCR_MCP_URL 의 사내 MCP OCR 서버 호출.
# - OCR_ENABLED: 기본 true. 비활성화하려면 환경변수 OCR_ENABLED=false.
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_BACKEND = os.getenv("OCR_BACKEND", "tesseract").lower()
OCR_MCP_URL = os.getenv("OCR_MCP_URL", "http://localhost:9000/mcp")
# LLM 비전 모델 — 기본은 번역용 LLM_MODEL 과 동일.
# 전용 비전 모델을 쓰려면 LLM_VISION_MODEL 환경변수로 덮어쓰세요.
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", LLM_MODEL)

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
