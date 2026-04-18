"""
이미지 OCR 인터페이스.

기본 백엔드는 로컬 Ollama 비전 모델(OLLAMA_VISION_MODEL)이며, 필요 시
config.OCR_BACKEND='mcp' 로 사내 MCP OCR 서버를 사용할 수 있습니다.

설치 예 (기본):
    ollama pull qwen2.5vl:7b
    # 또는
    OLLAMA_VISION_MODEL=minicpm-v ollama pull minicpm-v

MCP 백엔드 사용 시:
    OCR_BACKEND=mcp OCR_MCP_URL=http://... 로 환경변수를 지정합니다.
"""
import base64
import io
import logging
from typing import Optional
from dataclasses import dataclass

import requests
from PIL import Image

import config

logger = logging.getLogger(__name__)

_ollama_vision_client = None


@dataclass
class ImageTranslation:
    """이미지 내 텍스트 번역 결과"""
    original_chinese: str   # 원문 (중국어)
    translated_korean: str  # 번역 (한국어)


def download_image(url: str) -> Optional[bytes]:
    """이미지를 다운로드하여 바이트로 반환합니다."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        logger.error(f"이미지 다운로드 실패: {url} -> {e}")
        return None


def image_to_base64(image_bytes: bytes) -> str:
    """이미지 바이트를 base64 문자열로 변환합니다."""
    return base64.b64encode(image_bytes).decode("utf-8")


def call_ocr_mcp(image_base64: str) -> Optional[str]:
    """사내 MCP OCR 서버를 호출합니다.

    ╔══════════════════════════════════════════════════════════╗
    ║  이 함수를 사내 MCP 서버 스펙에 맞게 수정하세요.         ║
    ║                                                          ║
    ║  아래는 MCP JSON-RPC 2.0 호출 예시입니다.                ║
    ║  사내 MCP 서버의 tool 이름, 파라미터 형식에 맞게          ║
    ║  request body를 수정하세요.                               ║
    ╚══════════════════════════════════════════════════════════╝

    Args:
        image_base64: base64 인코딩된 이미지 문자열

    Returns:
        추출된 중국어 텍스트, 실패 시 None
    """
    try:
        # === MCP JSON-RPC 2.0 호출 예시 ===
        # 사내 MCP 서버의 tool 이름과 파라미터를 맞게 수정하세요
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ocr_extract_text",  # ← 사내 MCP tool 이름으로 변경
                "arguments": {
                    "image": image_base64,    # ← 파라미터명 확인
                    "language": "chi_sim",     # ← 중국어 간체
                },
            },
        }

        resp = requests.post(
            config.OCR_MCP_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        # MCP 응답에서 텍스트 추출
        # 사내 MCP 서버의 응답 형식에 맞게 수정하세요
        if "result" in result and "content" in result["result"]:
            for content in result["result"]["content"]:
                if content.get("type") == "text":
                    return content["text"]

        return None

    except Exception as e:
        logger.error(f"MCP OCR 호출 실패: {e}")
        return None


def _get_ollama_vision_client():
    global _ollama_vision_client
    if _ollama_vision_client is None:
        from openai import OpenAI
        _ollama_vision_client = OpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama",
        )
    return _ollama_vision_client


def call_ollama_vision_ocr(image_base64: str, mime: str = "image/jpeg") -> Optional[str]:
    """로컬 Ollama 비전 모델로 이미지 속 중국어 텍스트를 추출합니다.

    OpenAI 호환 chat/completions 엔드포인트에 image_url(base64 data URI)를 전달.
    모델이 설치되어 있지 않거나 호출이 실패하면 None을 반환합니다.
    """
    try:
        client = _get_ollama_vision_client()
        response = client.chat.completions.create(
            model=config.OLLAMA_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": config.OCR_PROMPT_ZH},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_base64}"},
                        },
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=1024,
        )
        content = response.choices[0].message.content
        if content is None:
            return None
        text = content.strip().strip('"').strip("'").strip()
        # 모델이 종종 출력하는 거부/공백 응답 제거
        if text.lower() in {"none", "no text", "empty", "n/a"}:
            return None
        return text or None
    except Exception as e:
        logger.warning(
            f"Ollama vision OCR 실패 ({config.OLLAMA_VISION_MODEL}): {e}. "
            f"모델이 설치되지 않았다면 `ollama pull {config.OLLAMA_VISION_MODEL}` 실행."
        )
        return None


def call_ocr_rest_api(image_base64: str) -> Optional[str]:
    """사내 REST API 방식 OCR 호출 (대안).

    MCP가 아닌 일반 REST API 방식의 OCR 서버를 사용할 경우
    이 함수를 수정하여 사용하세요.
    """
    try:
        resp = requests.post(
            config.OCR_MCP_URL,
            json={"image": image_base64, "language": "chinese_simplified"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
    except Exception as e:
        logger.error(f"REST OCR 호출 실패: {e}")
        return None


def _detect_mime(image_bytes: bytes) -> str:
    """PIL로 이미지 포맷을 감지해 MIME 타입을 반환합니다. 실패 시 jpeg."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        fmt = (img.format or "JPEG").lower()
        if fmt == "jpeg":
            return "image/jpeg"
        if fmt in ("png", "gif", "webp"):
            return f"image/{fmt}"
    except Exception:
        pass
    return "image/jpeg"


def extract_image_text(image_url: str) -> Optional[str]:
    """이미지에서 중국어 텍스트를 추출합니다.

    OCR이 비활성화되어 있으면 None을 반환합니다.
    config.OCR_BACKEND('ollama' 기본 | 'mcp')에 따라 백엔드를 선택합니다.
    """
    if not config.OCR_ENABLED:
        return None

    image_bytes = download_image(image_url)
    if not image_bytes:
        return None

    # 이미지가 너무 작으면 텍스트가 없을 가능성이 높음
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.width < 200 or img.height < 100:
            return None
    except Exception:
        return None

    b64 = image_to_base64(image_bytes)
    mime = _detect_mime(image_bytes)

    backend = getattr(config, "OCR_BACKEND", "ollama").lower()
    if backend == "mcp":
        text = call_ocr_mcp(b64)
    else:
        text = call_ollama_vision_ocr(b64, mime=mime)

    if not text:
        return None
    # 너무 짧은 텍스트(모델 환각·단일 문자 등)는 무시
    if len(text.strip()) < 2:
        return None
    return text


def process_image_translations(
    image_urls: list[str],
    translate_fn,
) -> dict[str, list[ImageTranslation]]:
    """이미지 목록에서 중국어 텍스트를 추출하고 번역합니다.

    텍스트가 없거나 OCR에 실패한 이미지는 결과 dict에 포함되지 않습니다
    (템플릿이 이를 감지해 캡션을 렌더링하지 않음).

    Args:
        image_urls: 이미지 URL 목록
        translate_fn: 중국어→한국어 번역 함수 (translator.translate_text)

    Returns:
        {이미지URL: [ImageTranslation, ...]} 딕셔너리
    """
    results = {}
    max_imgs = getattr(config, "OCR_MAX_IMAGES_PER_ARTICLE", 15)

    for url in image_urls[:max_imgs]:
        chinese_text = extract_image_text(url)
        if not chinese_text:
            continue

        # 문장 단위로 분리 — 너무 짧은 조각(아이콘 레이블 등)은 제외
        sentences = [s.strip() for s in chinese_text.split("\n") if s.strip() and len(s.strip()) >= 2]
        if not sentences:
            continue

        translations = []
        for sentence in sentences[:6]:  # 이미지당 최대 6문장
            korean = translate_fn(sentence)
            if korean:
                translations.append(ImageTranslation(
                    original_chinese=sentence,
                    translated_korean=korean,
                ))

        if translations:
            results[url] = translations
            logger.info(f"OCR+번역 완료: {len(translations)}건 -> {url[:60]}...")

    return results
