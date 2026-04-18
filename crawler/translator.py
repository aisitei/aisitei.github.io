"""
Ollama 번역기 (gemma4:e4b)

로컬 Ollama 서버에서 OpenAI 호환 API를 통해 번역합니다.
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

_ollama_client = None


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


# ── Ollama 클라이언트 ─────────────────────────────────────────────────────────

def _get_client():
    global _ollama_client
    if _ollama_client is None:
        from openai import OpenAI
        _ollama_client = OpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama",
        )
    return _ollama_client


def _chat(system: str, user: str, temperature: float = 0.3,
          max_tokens: int = 4096) -> Optional[str]:
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=config.OLLAMA_MODEL,
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
        logger.error(f"Ollama API 호출 실패: {e}")
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
