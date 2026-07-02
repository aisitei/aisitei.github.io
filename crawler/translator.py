"""
로컬 LLM 번역기 (LM Studio, OpenAI 호환 서버)

기본 백엔드는 LM Studio (http://localhost:1234/v1, gemma4:e4b).
LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 환경변수로 다른 서버·모델을 지정할 수 있습니다.
glossary.json의 단어장을 번역 전 소스 텍스트에 적용하고,
시스템 프롬프트에도 주입합니다.
"""
import re
import json
import logging
import time
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
          max_tokens: int = 4096, retries: int = 3,
          model: Optional[str] = None) -> Optional[str]:
    client = _get_client()
    use_model = model or config.LLM_MODEL
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            finish_reason = response.choices[0].finish_reason
            if finish_reason == "length":
                # max_tokens 초과로 응답이 중간에 잘림 → 재시도
                logger.warning(f"LLM 응답 잘림 (시도 {attempt}/{retries}) - finish_reason=length, max_tokens={max_tokens}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue
            content = response.choices[0].message.content
            if content is None:
                logger.warning(f"LLM 빈 응답 (시도 {attempt}/{retries}) - content=None")
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue
            text = content.strip()
            # <think>...</think> 블록 제거 (reasoning 모델 대응)
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            if not text:
                # think 블록만 있고 실제 응답이 없는 경우 → 재시도
                logger.warning(f"LLM 빈 응답 (시도 {attempt}/{retries}) - think 블록만 반환됨")
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue
            return text
        except Exception as e:
            logger.warning(f"LLM API 호출 실패 (시도 {attempt}/{retries}) [{use_model}]: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    logger.error(f"LLM API 호출 {retries}회 모두 실패 ({config.LLM_BASE_URL}, {use_model})")
    return None


# ── 영어→한국어 전용 프롬프트 ────────────────────────────────────────────────

_TITLE_TRANSLATE_EN_PROMPT = (
    "당신은 영어 IT 기사 제목을 한국어로 번역하는 번역가입니다. "
    "한국어 번역문만 출력하고 다른 텍스트는 절대 추가하지 마세요.\n\n"
    "번역 규칙:\n"
    "1. 브랜드·제품명은 원문 영문 표기를 유지합니다 (Samsung, Xiaomi, iPhone 등).\n"
    "2. 가격 표기: 달러($)는 '달러'로 표기합니다.\n"
    "3. 자연스러운 한국어 어순으로 재구성합니다.\n"
    "4. '폰' 대신 '스마트폰'을 사용합니다."
)

_TRANSLATE_SYSTEM_EN_PROMPT = (
    "당신은 영어 IT 기사를 한국어로 번역·정리하는 전문 편집자입니다.\n\n"
    "번역 규칙:\n"
    "1. 자연스러운 한국어로 번역합니다.\n"
    "2. 기술 용어(예: Snapdragon, LTPO, UTG)는 원문 그대로 유지합니다.\n"
    "3. 브랜드명은 원문 영문 표기를 유지합니다.\n"
    "4. 원문의 의미를 정확히 전달하되, 직역보다는 의역을 선호합니다.\n\n"
    "출력 형식 (HTML):\n"
    "- 내용을 주제별 섹션으로 나누고, 각 섹션 앞에 <h3> 헤더를 붙입니다.\n"
    "- 스펙·수치·목록은 <ul><li>...</li></ul> 불릿으로 정리합니다.\n"
    "- 일반 서술 단락은 <p>...</p>로 출력합니다.\n"
    "- 기사 마지막에 <h3>총평</h3> 섹션으로 핵심 내용을 2~4문장으로 요약합니다.\n"
    "- 마크다운(#, **, - 등)은 사용하지 않고, 순수 HTML 태그만 사용합니다.\n"
    "- 각 섹션(h3, p, ul)은 빈 줄로 구분합니다."
)


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

CAPTION_LONG_TRANSLATE_PROMPT = (
    "당신은 중국어 IT 스펙 텍스트를 한국어로 번역하는 번역가입니다. "
    "입력은 이미지에서 OCR로 추출한 제품 스펙 목록 또는 긴 문장입니다. "
    "자연스러운 한국어로 번역하세요. 수치·모델명·영문 약어는 그대로 유지하세요. "
    "고유명사는 영문 표기를 유지하세요 (小米→Xiaomi, 华为→Huawei, 天玑→Dimensity). "
    "번역 결과만 출력하세요. 설명이나 주석을 추가하지 마세요."
)

# 모델이 종종 출력하는 메타 응답을 거르기 위한 패턴.
_META_PATTERNS = re.compile(
    r"(전체\s*기사|기사\s*본문|원문\s*텍스트|충분한\s*분량|제공해\s*주시|다시\s*첨부|다시\s*제공|"
    r"번역을\s*원하|편집해\s*드리|번역\s*규칙|출력\s*형식|HTML\s*구조|편집자로서|sufficient|provide)",
    re.IGNORECASE,
)


def translate_caption(chinese_text: str) -> Optional[str]:
    """이미지 캡션용 중국어 번역. 긴 텍스트(스펙 목록 등)는 별도 프롬프트 사용."""
    text = chinese_text.strip()
    if not text:
        return None
    text = apply_glossary(text)

    is_long = len(text) >= 60
    if is_long:
        system = CAPTION_LONG_TRANSLATE_PROMPT + _build_glossary_prompt()
        max_tokens = 4096  # thinking 모델 대응
    else:
        system = CAPTION_TRANSLATE_PROMPT + _build_glossary_prompt()
        max_tokens = 2048  # thinking 모델 대응

    out = _chat(system=system, user=text, temperature=0.1, max_tokens=max_tokens)
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


def translate_caption_en(chinese_text: str) -> Optional[str]:
    """이미지 캡션용 중국어→영어 번역."""
    text = chinese_text.strip()
    if not text:
        return None
    text = apply_glossary(text)

    system = (
        "Translate the following Chinese image caption text into concise English. "
        "Output only the translated text, one line, no quotes, no explanation."
    )
    out = _chat(system=system, user=text, temperature=0.1, max_tokens=1024)
    if not out:
        return None
    out = out.split("\n", 1)[0].strip().strip('"').strip("'").strip()
    if not out:
        return None
    if len(out) > max(80, len(text) * 6) or _META_PATTERNS.search(out):
        logger.warning(f"caption_en translate dropped meta-text: {out[:60]}...")
        return None
    return out


def translate_caption_ja(chinese_text: str) -> Optional[str]:
    """이미지 캡션용 중국어→일본어 번역."""
    text = chinese_text.strip()
    if not text:
        return None
    text = apply_glossary(text)

    system = (
        "次の中国語の画像キャプションを簡潔な日本語に翻訳してください。"
        "翻訳文のみ1行で出力し、引用符や説明は不要です。"
    )
    out = _chat(system=system, user=text, temperature=0.1, max_tokens=1024)
    if not out:
        return None
    out = out.split("\n", 1)[0].strip().strip('"').strip("'").strip()
    if not out:
        return None
    if len(out) > max(80, len(text) * 6) or _META_PATTERNS.search(out):
        logger.warning(f"caption_ja translate dropped meta-text: {out[:60]}...")
        return None
    return out


def _looks_untranslated(text: str) -> bool:
    """번역 결과가 실제로 번역되지 않은 경우를 감지합니다.

    판정 기준:
    1. 연속 6자 이상 한자(CJK) 포함 → 본문이 중국어 그대로
    2. 전체 비공백 문자의 35% 이상이 한자 → 대부분 번역 안 됨
    3. 시스템 프롬프트 유출 패턴 감지 (모델이 지시문을 출력으로 반환한 경우)

    허용 예시: SmartSens(思特威), 커다이쉬엔페이(科大讯飞), Xiaomi HyperOS(小米澎湃 OS)
    → 괄호 안 브랜드 한자 표기는 6자 미만이고 비율도 낮으므로 통과됨.
    """
    # 1. 연속 한자 6자 이상
    if re.search('[一-鿿]{6,}', text):
        return True
    # 2. 한자 비율 35% 초과
    non_space = [c for c in text if c not in ' \t\n']
    if non_space:
        cjk_ratio = sum(1 for c in non_space if '一' <= c <= '鿿') / len(non_space)
        if cjk_ratio > 0.35:
            return True
    # 3. 시스템 프롬프트 유출: 지시문 키워드가 번역 결과에 포함된 경우
    if '브랜드명은 절대 음역' in text or '원문 그대로 표기하라' in text:
        return True
    return False


def translate_title(title: str, category: str = "", source_lang: str = "zh") -> Optional[str]:
    if source_lang == "en":
        system = _TITLE_TRANSLATE_EN_PROMPT
        user_text = title
    else:
        user_text = apply_glossary(title)
        system = config.TITLE_TRANSLATE_PROMPT + _build_glossary_prompt()

    result = _chat(
        system=system,
        user=f"다음 기사 제목을 한국어로 번역하세요:\n\n{user_text}",
        temperature=0.1,
        max_tokens=8192,  # thinking 모델은 <think> 블록이 수천 토큰을 소비하므로 넉넉히 확보
    )
    # 번역 결과에 한자가 3자 이상 연속 포함되면 번역 실패로 간주 → 폴백
    if result and _looks_untranslated(result):
        logger.warning(f"제목 번역 결과에 한자 포함 (번역 실패): {result[:60]}")
        result = None

    if result:
        return result

    # 폴백: 폴백 모델로 단순 지시 재시도
    fallback_model = config.LLM_FALLBACK_MODEL
    logger.warning(f"제목 번역 폴백 시도 [{fallback_model}]: {title[:50]}")
    lang_hint = "영어" if source_lang == "en" else "중국어"
    fallback_result = _chat(
        system=(
            "한국어 번역가. 입력된 제목을 한국어로 번역하여 한 줄만 출력하라. "
            "vivo, OPPO, realme, iQOO, Xiaomi, Huawei, Samsung, Apple, Sony, Canon 등 "
            "브랜드명은 절대 음역하지 말고 원문 그대로 표기하라."
        ),
        user=f"{lang_hint} 제목을 한국어로 번역:\n{user_text}",
        temperature=0.1,
        max_tokens=2048,  # thinking 모델 폴백도 충분한 토큰 확보
        retries=3,
        model=fallback_model,
    )
    # 폴백 결과도 검증
    if fallback_result and _looks_untranslated(fallback_result):
        logger.warning(f"폴백 번역도 한자 포함 → 최종 실패: {fallback_result[:60]}")
        return None
    return fallback_result


def translate_article(paragraphs: list[str], category: str = "", source_lang: str = "zh") -> list[str]:
    if not paragraphs:
        return []

    if source_lang == "en":
        full_text = "\n\n".join(paragraphs)
        system = _TRANSLATE_SYSTEM_EN_PROMPT
        if category == "phone_camera":
            system += config.DEEP_CAMERA_PROMPT_SUFFIX
    else:
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


# ── 다국어 번역 함수 (EN / JA / ZH summary) ─────────────────────────────────

_TRANSLATE_SYSTEM_ZH_SUMMARY_PROMPT = (
    "你是一位专业的科技新闻编辑，负责将中文IT新闻进行精炼摘要。\n\n"
    "摘要规则：\n"
    "1. 用简洁清晰的中文概括文章核心内容。\n"
    "2. 保留重要的数字、规格和产品名称。\n"
    "3. 品牌名称保持原文表记（Xiaomi、Huawei、Samsung等）。\n"
    "4. 不要添加原文没有的规格或事实。\n\n"
    "输出格式（HTML）：\n"
    "- 将内容分成若干主题段落，每段前加<h3>标题</h3>。\n"
    "- 规格、参数、列表用<ul><li>...</li></ul>整理。\n"
    "- 普通叙述段落用<p>...</p>输出。\n"
    "- 文章最后加<h3>总结</h3>，用2~4句话概括核心内容。\n"
    "- 不使用Markdown，只使用纯HTML标签。"
)

_TRANSLATE_SYSTEM_EN_FULL_PROMPT = (
    "You are a professional IT news editor who translates and summarizes Chinese/Korean tech articles into English.\n\n"
    "Translation rules:\n"
    "1. Write in natural, fluent English.\n"
    "2. Keep technical terms as-is (Snapdragon, LTPO, UTG, etc.).\n"
    "3. Keep brand names in their original form (Xiaomi, Huawei, Samsung, etc.).\n"
    "4. Prefer meaning-accurate translation over literal translation.\n"
    "5. Do NOT add specs or facts not present in the original text.\n\n"
    "Output format (HTML):\n"
    "- Divide content into thematic sections with <h3> headers.\n"
    "- Use <ul><li>...</li></ul> for specs, numbers, and lists.\n"
    "- Use <p>...</p> for narrative paragraphs.\n"
    "- End with a <h3>Summary</h3> section summarizing key points in 2-4 sentences.\n"
    "- Use only pure HTML tags, no Markdown."
)

_TRANSLATE_SYSTEM_JA_FULL_PROMPT = (
    "あなたはプロのITニュース編集者で、中国語/韓国語のテック記事を日本語に翻訳・要約します。\n\n"
    "翻訳ルール：\n"
    "1. 自然で流暢な日本語に翻訳します。\n"
    "2. 技術用語（Snapdragon、LTPO、UTGなど）はそのまま維持します。\n"
    "3. ブランド名は原文表記を維持します（Xiaomi、Huawei、Samsungなど）。\n"
    "4. 直訳より意訳を優先します。\n"
    "5. 原文にないスペックや事実は絶対に追加しないでください。\n\n"
    "出力形式（HTML）：\n"
    "- 内容をテーマ別セクションに分け、各セクションの前に<h3>ヘッダー</h3>を付けます。\n"
    "- スペック・数値・リストは<ul><li>...</li></ul>で整理します。\n"
    "- 通常の叙述段落は<p>...</p>で出力します。\n"
    "- 記事の最後に<h3>まとめ</h3>セクションで主要内容を2~4文で要約します。\n"
    "- MarkdownではなくHTMLタグのみ使用します。"
)

_TITLE_TRANSLATE_ZH_FROM_KO_PROMPT = (
    "你是一位将韩语IT新闻标题翻译成中文的翻译者。"
    "只输出中文翻译，不要添加任何其他文字。\n\n"
    "规则：\n"
    "1. 品牌/产品名称保持原文表记（Samsung、Xiaomi、iPhone等）。\n"
    "2. 货币：韩元（원/₩）表示为'韩元'。\n"
    "3. 使用自然流畅的中文表达。"
)

_TITLE_TRANSLATE_EN_FROM_ZH_PROMPT = (
    "You are a translator converting Chinese IT article titles to English. "
    "Output only the English translation, nothing else.\n\n"
    "Rules:\n"
    "1. Keep brand/product names in their original form (Samsung, Xiaomi, iPhone, etc.).\n"
    "2. Currency: express yuan (元/¥) as 'yuan'.\n"
    "3. Use natural English phrasing.\n"
    "4. Use 'smartphone' instead of 'phone'."
)

_TITLE_TRANSLATE_JA_FROM_ZH_PROMPT = (
    "あなたは中国語のITニュースのタイトルを日本語に翻訳する翻訳者です。"
    "日本語の翻訳のみを出力し、他のテキストは絶対に追加しないでください。\n\n"
    "ルール：\n"
    "1. ブランド名・製品名は原文表記を維持します（Samsung、Xiaomi、iPhoneなど）。\n"
    "2. 価格：中国元（元/¥）は「元」と表記します。\n"
    "3. 自然な日本語の語順で再構成します。\n"
    "4. 「スマホ」ではなく「スマートフォン」を使います。"
)


def translate_body_en(source_text: str, category: str = "") -> Optional[str]:
    """HTML 본문을 영어로 번역합니다. source_text는 한국어 또는 중국어 HTML."""
    if not source_text.strip():
        return ""
    system = _TRANSLATE_SYSTEM_EN_FULL_PROMPT
    if category == "phone_camera":
        system += "\n\nFor camera articles: include all sensor specs, aperture, focal length, and video specs in detail."
    return _chat(
        system=system,
        user=f"Please translate the following article to English:\n\n{source_text}",
        temperature=0.3,
        max_tokens=8192,
    )


def translate_body_ja(source_text: str, category: str = "") -> Optional[str]:
    """HTML 본문을 일본어로 번역합니다. source_text는 한국어 또는 중국어 HTML."""
    if not source_text.strip():
        return ""
    system = _TRANSLATE_SYSTEM_JA_FULL_PROMPT
    if category == "phone_camera":
        system += "\n\nカメラ記事の場合：センタースペック、絞り値、焦点距離、動画スペックを詳細に含めてください。"
    return _chat(
        system=system,
        user=f"以下の記事を日本語に翻訳してください：\n\n{source_text}",
        temperature=0.3,
        max_tokens=8192,
    )


_TRANSLATE_SYSTEM_ZH_FULL_PROMPT = (
    "你是一位专业的科技新闻编辑，负责将韩语IT新闻翻译并整理成中文。\n\n"
    "翻译规则：\n"
    "1. 用简洁清晰的中文翻译全文内容。\n"
    "2. 保留重要的数字、规格和产品名称。\n"
    "3. 品牌名称保持原文表记（Xiaomi、Huawei、Samsung等）。\n"
    "4. 不要添加原文没有的规格或事实。\n\n"
    "输出格式（HTML）：\n"
    "- 将内容分成若干主题段落，每段前加<h3>标题</h3>。\n"
    "- 规格、参数、列表用<ul><li>...</li></ul>整理。\n"
    "- 普通叙述段落用<p>...</p>输出。\n"
    "- 文章最后加<h3>总结</h3>，用2~4句话概括核心内容。\n"
    "- 不使用Markdown，只使用纯HTML标签。"
)


def translate_body_zh(source_text: str) -> Optional[str]:
    """한국어 본문을 중국어로 번역합니다."""
    if not source_text.strip():
        return ""
    return _chat(
        system=_TRANSLATE_SYSTEM_ZH_FULL_PROMPT,
        user=f"请将以下韩语文章翻译成中文：\n\n{source_text}",
        temperature=0.3,
        max_tokens=8192,
    )


def translate_body_zh_summary(zh_text: str) -> Optional[str]:
    """중국어 원문을 중국어로 요약합니다 (HTML 형식 유지)."""
    if not zh_text.strip():
        return ""
    text = apply_glossary(zh_text)
    return _chat(
        system=_TRANSLATE_SYSTEM_ZH_SUMMARY_PROMPT,
        user=f"请对以下文章进行精炼摘要：\n\n{text}",
        temperature=0.3,
        max_tokens=8192,
    )


def translate_title_zh(ko_title: str) -> Optional[str]:
    """한국어 제목을 중국어로 번역합니다."""
    if not ko_title.strip():
        return ""
    text = apply_glossary(ko_title)
    result = _chat(
        system=_TITLE_TRANSLATE_ZH_FROM_KO_PROMPT,
        user=f"请将以下韩语新闻标题翻译成中文：\n\n{text}",
        temperature=0.1,
        max_tokens=1024,
    )
    if result:
        return result.split("\n", 1)[0].strip()
    return None


def translate_title_en(zh_title: str) -> Optional[str]:
    """중국어 제목을 영어로 번역합니다."""
    if not zh_title.strip():
        return ""
    text = apply_glossary(zh_title)
    result = _chat(
        system=_TITLE_TRANSLATE_EN_FROM_ZH_PROMPT,
        user=f"Translate this article title to English:\n\n{text}",
        temperature=0.1,
        max_tokens=2048,
    )
    if result:
        return result.split("\n", 1)[0].strip()
    return None


def translate_title_ja(zh_title: str) -> Optional[str]:
    """중국어 제목을 일본어로 번역합니다."""
    if not zh_title.strip():
        return ""
    text = apply_glossary(zh_title)
    result = _chat(
        system=_TITLE_TRANSLATE_JA_FROM_ZH_PROMPT,
        user=f"以下のタイトルを日本語に翻訳してください：\n\n{text}",
        temperature=0.1,
        max_tokens=2048,
    )
    if result:
        return result.split("\n", 1)[0].strip()
    return None


def generate_slug(korean_title: str) -> str:
    result = _chat(
        system="You convert Korean/English titles to English kebab-case file slugs.",
        user=(
            "다음 기사 제목을 영문 kebab-case 파일명으로 변환해주세요. "
            "3~6단어, 소문자, 하이픈 구분. 파일명만 출력하세요.\n\n"
            f"제목: {korean_title}"
        ),
        temperature=0.1,
        max_tokens=1024,  # thinking 모델 대응
    )
    if not result:
        return "article"
    slug = result.strip().lower()
    slug = slug.replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = slug.strip("-")
    return slug or "article"
