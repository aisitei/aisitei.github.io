"""HTML 생성기 - 새 디렉토리 구조에 맞게 기사를 저장합니다."""
import os
import logging
from datetime import datetime
from dataclasses import dataclass, field

from jinja2 import Environment, FileSystemLoader

from scraper import Article, download_image
from ocr import ImageTranslation

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


@dataclass
class TranslatedArticle:
    """번역 완료된 기사 데이터 (4개 언어 지원)"""
    original: Article
    slug: str
    # 다국어 제목/본문 dict ({"ko", "zh", "ja", "en"})
    titles: dict = field(default_factory=dict)
    bodies: dict = field(default_factory=dict)
    image_translations: dict = field(default_factory=dict)

    # ── 하위 호환 properties ──────────────────────────────────────────────────
    @property
    def korean_title(self) -> str:
        return self.titles.get("ko", "")

    @korean_title.setter
    def korean_title(self, value: str):
        self.titles["ko"] = value

    @property
    def korean_paragraphs(self) -> list:
        return self.bodies.get("ko", [])

    @korean_paragraphs.setter
    def korean_paragraphs(self, value: list):
        self.bodies["ko"] = value


# 크롤러 내부 카테고리 → build.py/template 공통 카테고리로 정규화
CATEGORY_NORMALIZE = {
    "phone_camera": "camera",
    "phone_product": "phone",
    "ai": "ai",
}

CATEGORY_LABEL_KO = {
    "camera": "카메라",
    "phone": "스마트폰",
    "ai": "AI",
}


def render_html(article: TranslatedArticle, date_str: str, local_images: list) -> str:
    """번역된 기사를 HTML로 렌더링합니다. local_images는 'images/img1.jpg' 형식의 상대경로."""
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template("article.html")

    # image_translations(원본 URL 키)를 로컬 상대경로 키로 재매핑.
    # 원본 이미지 순서를 기준으로 하여 OCR이 건너뛴 이미지가 있어도 인덱스가 어긋나지 않도록 한다.
    local_image_translations = {}
    for i, orig_url in enumerate(article.original.image_urls):
        if i >= len(local_images):
            break
        translations = article.image_translations.get(orig_url)
        if translations:
            local_image_translations[local_images[i]] = translations

    # 카테고리 정규화 (build.py와 일치시키기 위해)
    normalized_cat = CATEGORY_NORMALIZE.get(article.original.category, article.original.category)
    category_label = CATEGORY_LABEL_KO.get(normalized_cat, normalized_cat)

    # 다국어 제목/본문 준비 (ko 폴백)
    titles = {
        "ko": article.titles.get("ko", ""),
        "zh": article.titles.get("zh", article.titles.get("ko", "")),
        "ja": article.titles.get("ja", article.titles.get("ko", "")),
        "en": article.titles.get("en", article.titles.get("ko", "")),
    }
    bodies = {
        "ko": article.bodies.get("ko", []),
        "zh": article.bodies.get("zh", article.bodies.get("ko", [])),
        "ja": article.bodies.get("ja", article.bodies.get("ko", [])),
        "en": article.bodies.get("en", article.bodies.get("ko", [])),
    }

    html = template.render(
        title=titles["ko"],
        titles=titles,
        original_title=article.original.title,
        paragraphs=article.bodies.get("ko", []),
        bodies=bodies,
        images=local_images,  # relative paths
        image_translations=local_image_translations,
        source_url=article.original.url,
        source_name="Gizmochina" if article.original.source == "gizmochina" else "IT之家 (ithome.com)",
        source_label="Gizmochina에서 보기" if article.original.source == "gizmochina" else "IT之家에서 보기",
        date_str=date_str,
        author=article.original.author,
        category=normalized_cat,        # "camera" / "phone" / "ai"
        category_label=category_label,  # "카메라" / "스마트폰" / "AI"
        brand=article.original.brand,
        brand_color=article.original.brand_color,
    )
    return html


def save_article(article: TranslatedArticle, articles_root: str,
                 date_str: str = None) -> dict:
    """기사를 새 디렉토리 구조로 저장합니다.

    구조: articles/YYYY-MM/YYYY-MM-DD/slug/index.html
          articles/YYYY-MM/YYYY-MM-DD/slug/images/

    Args:
        date_str: "YYYY-MM-DD" 형식의 날짜. 없으면 오늘 날짜 사용.

    Returns: {"filepath": ..., "article_dir": ..., "local_images": [...]}
    """
    today = date_str if date_str else datetime.now().strftime("%Y-%m-%d")
    month_str = today[:7]  # "YYYY-MM"

    # AI 기사 slug에 AI- 접두어 추가
    slug = article.slug
    if article.original.category == "ai" and not slug.startswith("ai-"):
        slug = f"ai-{slug}"

    article_dir = os.path.join(articles_root, month_str, today, slug)
    images_dir = os.path.join(article_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 이미지 다운로드
    local_images = []
    for i, url in enumerate(article.original.image_urls):
        ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        filename = f"img{i+1:02d}{ext}"
        dest = os.path.join(images_dir, filename)
        if download_image(url, dest):
            local_images.append(f"images/{filename}")
        else:
            # 다운로드 실패 시 원본 URL 사용
            local_images.append(url)

    # HTML 렌더링 및 저장
    html = render_html(article, today, local_images)
    filepath = os.path.join(article_dir, "index.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"기사 저장: {filepath} (이미지 {len(local_images)}장)")
    return {"filepath": filepath, "article_dir": article_dir, "local_images": local_images}
