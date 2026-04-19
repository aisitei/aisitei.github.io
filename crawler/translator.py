"""
로컬 LLM 번역기 (LM Studio / Ollama 등 OpenAI 호환 서버)

기본 백엔드는 LM Studio (http://localhost:1234/v1, gemma4:e4b).
LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 환경변수로 다른 서버·모델을 지정할 수 있습니다.
glossary.json의 단어장을 번역 전 소스 텍스트에 적용하고,
시스템 프롬프트에도 주입합니다.
"""
import re
import json
import logging
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_llm_client = None


# ── 단어장 로딩 ──────────────────────────────────────────────────────────────

def _load_glossary() -> dict[str, str]:
    """glossary.json에서 모든 카테고리의 단어를 하나의 dict로 합칩니다."""
    glossary_path = Path(__file__).parent / "glossary.json"
    if not glossary_path.exists():
        return {}
    try:
        data = json.loads(glossary_path.read_text(encoding="utf-8"))
        merged = {}
        for key, section in data.items():
            if key.startswith("_"):
                continue
            if isinstance(section, dict):
                merged.update(section)
        return merged
    except Exception as e:
        logger.warning(f"glossary.json 로딩 실패: {e}")
        return {}


_GLOSSARY: dict[str, str] = _load_glossary()


def apply_glossary(text: str) -> str:
    """소스 텍스트에서 단어장의 중국어 용어를 대상 표현으로 치환합니다."""
    if not _GLOSSARY:
        return text
    # 긴 단어부터 먼저 치환 (부분 매칭 방지)
    for src, dst in sorted(_GLOSSARY.items(), key=lambda x: -len(x[0])):
        text = text.replace(src, dst)
    return text


def _build_glossary_prompt() -> str:
    """단어장을 시스템 프롬프트에 추가할 텍스트로 변환합니다."""
    if not _GLOSSARY:
        return ""
    lines = [f"- {src} → {dst}" for src, dst in sorted(_GLOSSARY.items())]
    return "\n\n**고유명사 단어장 (반드시 준수)**:\n" + "\n".join(lines)


# ── 로컬 LLM 클라이언트 (LM Studio / Ollama OpenAI 호환) ────────────────────

def _get_client():
    global _llm_client
    if _llm_client is None:
        from openai import OpenAI
        _llm_client = OpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.LLM_API_KEY,
        )
    return _llm_client


def _chat(system: str, user: str, temperature: float = 0.3,
          max_tokens: int = 4096) -> Optional[str]:
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if content is None:
            return None
        text = content.strip()
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        return text if text else None
    except Exception as e:
        logger.error(f"LLM API 호출 실패 ({config.LLM_BASE_URL}, {config.LLM_MODEL}): {e}")
        return None


# ── 번역 API ─────────────────────────────────────────────────────────────────

def translate_text(chinese_text: str, category: str = "") -> Optional[str]:
    if not chinese_text.strip():
        return ""
    text = apply_glossary(chinese_text)
    system = config.TRANSLATE_SYSTEM_PROMPT + _build_glossary_prompt()
    if category == "phone_camera":
        system += config.DEEP_CAMERA_PROMPT_SUFFIX
    return _chat(
        system=system,
        user=f"다음 기사 텍스트를 한국어로 번역해주세요:\n\n{text}",
        temperature=0.3,
        max_tokens=4096,
    )


# ── 캡션 전용 짧은 텍스트 번역 ────────────────────────────────────────────────
# OCR 결과가 종종 단어/짧은 문구("예약 알림", "휴대폰 번호")이므로 기사 본문용
# 시스템 프롬프트(HTML 섹션·헤더·총평 출력)를 쓰면 모델이 "본문 부족" 같은
# 메타 응답을 길게 출력합니다. 캡션 전용 한 줄 번역기를 별도로 둡니다.

CAPTION_TRANSLATE_PROMPT = (
    "당신은 중국어 IT 이미지 캡션을 한국어로 번역하는 번역가입니다. "
    "입력은 이미지에서 OCR로 추출한 짧은 문장 또는 라벨일 수 있습니다. "
    "그 입력 자체를 자연스러운 한국어로 한 줄로 번역해서 출력하세요. "
    "고유명사·브랜드·모델명은 영문 표기를 유지하세요 (예: 小米→Xiaomi, 华为→Huawei, 天玑→Dimensity). "
    "절대로 설명·주석·따옴표·마크다운·여러 줄·번역이 부족하다는 메타 답변을 추가하지 마세요. "
    "오직 번역 결과 한 줄만 출력하세요."
)

# 모델이 종종 출력하는 메타 응답을 거르기 위한 패턴.
_META_PATTERNS = re.compile(
    r"(전체\s*기사|기사\s*본문|원문\s*텍스트|충분한\s*분량|제공해\s*주시|다시\s*첨부|다시\s*제공|"
    r"번역을\s*원하|편집해\s*드리|번역\s*규칙|출력\s*형식|HTML\s*구조|편집자로서|sufficient|provide)",
    re.IGNORECASE,
)


def translate_caption(chinese_text: str) -> Optional[str]:
    """이미지 캡션용 짧은 중국어 한 줄 번역. 메타 응답·여러 줄은 거름."""
    text = chinese_text.strip()
    if not text:
        return None
    text = apply_glossary(text)
    out = _chat(
        system=CAPTION_TRANSLATE_PROMPT + _build_glossary_prompt(),
        user=text,
        temperature=0.1,
        max_tokens=192,
    )
    if not out:
        return None
    # 첫 줄만, 따옴표 정리
    out = out.split("\n", 1)[0].strip().strip('"').strip("'").strip()
    if not out:
        return None
    # 메타 응답 거르기 (긴 안내문이면 출력 폐기)
    if len(out) > max(80, len(text) * 6) or _META_PATTERNS.search(out):
        logger.warning(f"caption translate dropped meta-text: {out[:60]}...")
        return None
    return out


def translate_title(chinese_title: str, category: str = "") -> Optional[str]:
    title = apply_glossary(chinese_title)
    system = config.TITLE_TRANSLATE_PROMPT + _build_glossary_prompt()
    return _chat(
        system=system,
        user=f"다음 기사 제목을 한국어로 번역하세요:\n\n{title}",
        temperature=0.1,
        max_tokens=128,
    )


def translate_article(paragraphs: list[str], category: str = "") -> list[str]:
    if not paragraphs:
        return []
    full_text = apply_glossary("\n\n".join(paragraphs))
    system = config.TRANSLATE_SYSTEM_PROMPT + _build_glossary_prompt()
    if category == "phone_camera":
        system += config.DEEP_CAMERA_PROMPT_SUFFIX
    max_tokens = 16384 if category == "phone_camera" else 8192
    result = _chat(
        system=system,
        user=(
            "다음 기사를 한국어로 번역해주세요. "
            "각 단락은 빈 줄로 구분하여 유지해주세요. "
            "번역문만 출력하세요:\n\n"
            f"{full_text}"
        ),
        temperature=0.3,
        max_tokens=max_tokens,
    )
    if not result:
        return []
    return [p.strip() for p in result.split("\n\n") if p.strip()]


def generate_slug(korean_title: str) -> str:
    result = _chat(
        system="You convert Korean/English titles to English kebab-case file slugs.",
        user=(
            "다음 기사 제목을 영문 kebab-case 파일명으로 변환해주세요. "
            "3~6단어, 소문자, 하이픈 구분. 파일명만 출력하세요.\n\n"
            f"제목: {korean_title}"
        ),
        temperature=0.1,
        max_tokens=64,
    )
    if not result:
        return "article"
    slug = result.strip().lower()
    slug = slug.replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = slug.strip("-")
    return slug or "article"
