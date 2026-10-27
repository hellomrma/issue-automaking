"""키워드 기반 블로그 글 생성 (Anthropic Claude API)"""
import logging
import os
from typing import Generator, Optional

from anthropic import Anthropic
from pydantic import BaseModel

logger = logging.getLogger("app.writer")

# 모델 ID. 환경변수 CLAUDE_MODEL 로 변경 가능 (예: claude-haiku-5-5)
DEFAULT_MODEL = "claude-sonnet-5-5"

# 서버 측 거절(refusal) 폴백("default")을 지원하는 모델
_FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}

# 사고(thinking) 토큰도 포함되므로 넉넉하게 설정 (한국어는 글자당 토큰이 많음)
_MAX_TOKENS = 16000

# 출력 한도에 걸려 글이 잘렸을 때 본문 끝에 붙는 안내 (프론트에서 감지)
TRUNCATED_NOTICE = "[WARN] 출력 한도에 도달해 글이 잘렸을 수 있습니다."

_STYLE_DESC = {
    "정보성": "유용한 정보를 체계적으로 정리한 설명형",
    "리뷰": "주관적인 경험과 의견이 담긴 리뷰형",
    "How-to": "단계별로 따라 할 수 있는 가이드형",
    "뉴스해설": "최근 이슈를 요약하고 의견을 덧붙이는 해설형",
}

_LENGTH_DESC = {
    "short": "본문 400~600자 분량",
    "medium": "본문 800~1,200자 분량",
    "long": "본문 1,500~2,000자 분량",
}

_SYSTEM = (
    "You are an expert blog writer for Tistory. Your output must be valid Markdown only, "
    "no code fences or extra labels. Use ## for sections, ### for subsections, "
    "**bold**, lists, and short paragraphs. No YAML frontmatter."
)


def _common_requirements(
    lang: str, style: str, length: str, use_emoji: bool, extra: str = ""
) -> str:
    """키워드/URL 프롬프트가 공유하는 스타일·요구사항 블록"""
    style_desc = _STYLE_DESC.get(style, _STYLE_DESC["정보성"])
    length_desc = _LENGTH_DESC.get(length, _LENGTH_DESC["medium"])
    lang_instruction = "반드시 한국어로만 작성하세요." if lang == "ko" else "Write in English only."
    title_instruction = "첫 번째 # 제목을 글의 메인 제목으로 사용하세요." if lang == "ko" else "Use the first # heading as the main title."
    emoji_instruction = (
        "- 제목, 소제목, 문단에 주제에 맞는 이모지를 적당히 넣어 주세요. 과하지 않게 사용하세요."
        if use_emoji
        else "- 이모지는 사용하지 마세요."
    )
    return f"""글 스타일: {style_desc}
{lang_instruction}
{title_instruction}

요구사항:
- {length_desc} (의미 있는 문단/문장 기준)
{extra}- **글체**: 편안하고 부드러운 톤으로 써 주세요. '서론', '결론', '본론', '이에 대해', '다음과 같이', '정리하면' 같은 딱딱하거나 격식 있는 표현은 쓰지 말고, 구어체에 가까운 친근한 문장으로 자연스럽게 이어 주세요.
- 소제목(##, ###)으로 읽기 쉽게 구분하되, '서론/결론'처럼 형식을 드러내는 제목은 쓰지 마세요.
- 자연스럽고 SEO에 유리한 문장
- 마지막은 따로 '결론'이라 부르지 말고, 이야기를 부드럽게 마무리하는 문단 1~2개
- 글 끝에 #태그1 #태그2 #태그3 ... 형태로 태그 5~10개를 한 줄에 붙여 주세요. (주제·키워드·SEO 관련, 공백으로 구분)
{emoji_instruction}"""


def _context_block(intro: str, content: Optional[str]) -> str:
    """참고 자료 블록. 내용이 없으면 빈 문자열."""
    if not content or not (content := content.strip()):
        return ""
    return f"""

{intro}

---
{content}
---
"""


_SEARCH_INTRO = "아래는 {subject}에 대한 최신 웹 검색 결과와 **뉴스 기사**입니다. 뉴스(일반 뉴스·구글 뉴스 등)를 특히 참고하여 **최신 동향·숫자·사실·시사**를 반영하고, 독자가 관심 가질 만한 시의성 있는 내용을 담아 주세요. 원문을 그대로 복사하지 말고 재해석하여 자연스럽게 활용하세요."
_GUIDE_INTRO = "아래는 사용자가 요청한 **글 작성 가이드**입니다. 이 가이드를 최우선으로 반영하여 글을 작성해 주세요:"
_REFERENCE_INTRO = "아래는 **참고해야 할 URL의 콘텐츠**입니다. 이 내용을 참고하여 글을 작성해 주세요. 원문을 그대로 복사하지 말고 참고만 하세요:"
_CLAUDE_SEARCH_INSTRUCTION = """

web_search 도구로 {subject}의 최신 뉴스와 정보를 찾아 **최신 동향·숫자·사실·시사**를 반영해 주세요. 검색 과정이나 "검색해 보겠습니다" 같은 말 없이 완성된 글만 출력하세요.
"""
_SOURCES_INSTRUCTION = """

출처 표기: 해시태그 줄 바로 위에 `## 참고한 자료` 소제목을 두고, 본문에 실제로 반영한 자료만 최대 3개를 `- [기사·페이지 제목](URL)` 형식의 목록으로 적어 주세요. URL은 위에 주어진 자료나 검색 결과에 실제로 있는 것만 쓰고, 지어내지 마세요.
"""

# Claude 서버 측 웹 검색 도구 (검색은 요청당 최대 5회)
_WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 5,
    "user_location": {"type": "approximate", "country": "KR", "timezone": "Asia/Seoul"},
}

# pause_turn(서버 측 검색 루프 일시 정지) 이어받기 최대 횟수
_MAX_PAUSE_RESUMES = 3


def _build_prompts(
    keyword: str,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    web_context: Optional[str] = None,
    length: str = "medium",
    guide: Optional[str] = None,
    reference_content: Optional[str] = None,
    include_sources: bool = True,
    claude_search: bool = False,
) -> tuple[str, str]:
    """시스템 프롬프트와 사용자 프롬프트를 생성합니다."""
    user = f"""다음 키워드를 주제로 티스토리 블로그 글을 마크다운으로 작성해 주세요.

키워드: {keyword}
{_common_requirements(lang, style, length, use_emoji)}
"""
    user += _context_block(_SEARCH_INTRO.format(subject="이 키워드"), web_context)
    user += _context_block(_GUIDE_INTRO, guide)
    user += _context_block(_REFERENCE_INTRO, (reference_content or "")[:4000])
    if claude_search:
        user += _CLAUDE_SEARCH_INSTRUCTION.format(subject=f"'{keyword}'")
    # 출처로 쓸 자료가 있을 때만 출처 표기를 요청
    if include_sources and ((web_context or "").strip() or (reference_content or "").strip() or claude_search):
        user += _SOURCES_INSTRUCTION
    return _SYSTEM, user


def _build_url_prompts(
    url_content: dict,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    related_search: str = "",
    length: str = "medium",
    guide: Optional[str] = None,
    include_sources: bool = True,
    claude_search: bool = False,
) -> tuple[str, str]:
    """URL 콘텐츠 기반 블로그 글 생성을 위한 프롬프트를 생성합니다."""
    url_info = f"URL: {url_content.get('url', '')}"
    if url_content.get("title"):
        url_info += f"\n제목: {url_content['title']}"
    if url_content.get("description"):
        url_info += f"\n설명: {url_content['description']}"

    url_extra = (
        "- 원본 URL의 내용을 그대로 복사하지 말고, 핵심 내용을 파악하여 **새로운 관점**으로 재구성해 주세요\n"
        "- 원본의 주제를 확장하거나, 독자에게 더 유용한 정보를 추가해 주세요\n"
    )
    user = f"""다음 URL의 콘텐츠를 분석하여 관련된 티스토리 블로그 글을 마크다운으로 작성해 주세요.

{url_info}

--- 원본 콘텐츠 ---
{url_content.get('content', '')[:6000]}
---

{_common_requirements(lang, style, length, use_emoji, extra=url_extra)}
"""
    user += _context_block(_SEARCH_INTRO.format(subject="이 주제와 관련된 내용"), related_search)
    user += _context_block(_GUIDE_INTRO, guide)
    if claude_search:
        user += _CLAUDE_SEARCH_INSTRUCTION.format(subject="이 주제")
    if include_sources:
        user += _SOURCES_INSTRUCTION
    return _SYSTEM, user


def _clean_markdown(text: str) -> str:
    """마크다운 코드 블록으로 감싼 경우 제거합니다."""
    if text.startswith("```") and "```" in text[3:]:
        first = text.find("\n")
        text = text[first + 1 : text.rfind("```")].strip()
    return text


def _get_model() -> str:
    return (os.getenv("CLAUDE_MODEL") or "").strip() or DEFAULT_MODEL


def _stream_text(
    system: str, user: str, api_key: Optional[str], *, web_search: bool = False
) -> Generator[str, None, None]:
    """
    Claude 응답 텍스트를 스트리밍. 출력 한도로 잘리면 TRUNCATED_NOTICE를 덧붙입니다.
    web_search: True면 Claude 서버 측 웹 검색 도구를 사용 (pause_turn 시 이어서 요청)
    """
    client = Anthropic(api_key=api_key or None)
    model = _get_model()
    extra = {}
    if model in _FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    if web_search:
        extra["tools"] = [_WEB_SEARCH_TOOL]

    messages = [{"role": "user", "content": user}]
    for _ in range(_MAX_PAUSE_RESUMES + 1):
        with client.beta.messages.stream(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=messages,
            **extra,
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
        if final.stop_reason != "pause_turn":
            break
        # 서버 측 검색 루프가 멈춘 경우: 지금까지의 응답을 그대로 돌려보내면 이어서 진행
        messages = [{"role": "user", "content": user}, {"role": "assistant", "content": final.content}]

    if final.stop_reason == "max_tokens":
        logger.warning("출력 한도(max_tokens=%d) 도달: model=%s", _MAX_TOKENS, model)
        yield f"\n\n{TRUNCATED_NOTICE}"
    elif final.stop_reason == "refusal":
        raise RuntimeError("Claude가 이 주제의 글 작성을 거절했습니다. 다른 키워드로 시도해 주세요.")
    elif final.stop_reason == "pause_turn":
        logger.warning("웹 검색이 %d회 이어받기 후에도 끝나지 않음", _MAX_PAUSE_RESUMES)
        yield f"\n\n{TRUNCATED_NOTICE}"


def generate_article_md_stream(
    keyword: str,
    *,
    api_key: Optional[str] = None,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    web_context: Optional[str] = None,
    length: str = "medium",
    guide: Optional[str] = None,
    reference_content: Optional[str] = None,
    include_sources: bool = True,
    claude_search: bool = False,
) -> Generator[str, None, None]:
    """
    키워드를 바탕으로 티스토리용 마크다운 블로그 글을 스트리밍으로 생성합니다.
    length: short | medium | long
    guide: 사용자가 원하는 글 작성 방향/톤/포함할 내용
    reference_content: 참고할 URL의 콘텐츠
    include_sources: True면 글 끝에 '참고한 자료' 출처 링크 포함
    claude_search: True면 Claude 웹 검색 도구로 최신 정보 검색
    """
    system, user = _build_prompts(
        keyword, lang, style, use_emoji, web_context, length, guide, reference_content,
        include_sources, claude_search,
    )
    yield from _stream_text(system, user, api_key, web_search=claude_search)


def generate_article_md(keyword: str, **kwargs) -> str:
    """
    키워드를 바탕으로 티스토리용 마크다운 블로그 글을 생성합니다.
    인자는 generate_article_md_stream()과 동일합니다.
    api_key: Anthropic(Claude) API 키 (None이면 환경변수 ANTHROPIC_API_KEY 사용)
    web_context: 최신 웹 검색 결과 텍스트. 있으면 이를 참고해 최신 정보를 반영
    """
    return _clean_markdown("".join(generate_article_md_stream(keyword, **kwargs)).strip())


def generate_article_from_url_stream(
    url_content: dict,
    *,
    api_key: Optional[str] = None,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    related_search: Optional[str] = None,
    length: str = "medium",
    guide: Optional[str] = None,
    include_sources: bool = True,
    claude_search: bool = False,
) -> Generator[str, None, None]:
    """
    URL 콘텐츠를 기반으로 티스토리용 마크다운 블로그 글을 스트리밍으로 생성합니다.
    url_content: fetch_url_content()에서 반환된 dict
    related_search: 관련 웹 검색 결과 텍스트
    """
    system, user = _build_url_prompts(
        url_content, lang, style, use_emoji, related_search or "", length, guide,
        include_sources, claude_search,
    )
    yield from _stream_text(system, user, api_key, web_search=claude_search)


def generate_article_from_url(url_content: dict, **kwargs) -> str:
    """
    URL 콘텐츠를 기반으로 티스토리용 마크다운 블로그 글을 생성합니다.
    인자는 generate_article_from_url_stream()과 동일합니다.
    """
    return _clean_markdown("".join(generate_article_from_url_stream(url_content, **kwargs)).strip())


# ---------- 글 다듬기 ----------

def revise_article_stream(
    markdown: str,
    instruction: str,
    *,
    section: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Generator[str, None, None]:
    """
    완성된 글을 요청대로 고쳐 씁니다.
    section이 있으면 그 부분만 고쳐서 그 부분만 출력하고, 없으면 글 전체를 출력합니다.
    """
    if section:
        target = f"""아래 [전체 글] 중 [고칠 부분]만 요청대로 고쳐 주세요.
- 고친 [고칠 부분]만 출력하세요. 다른 부분이나 설명은 출력하지 마세요.
- [고칠 부분]이 ## 소제목으로 시작하면, 고친 글도 ## 소제목 줄로 시작하세요.
- 앞뒤 문단과 자연스럽게 이어지도록 글의 톤과 형식을 유지하세요.

[고칠 부분]
---
{section}
---"""
    else:
        target = """아래 [전체 글]을 요청대로 고쳐 주세요.
- 고친 글 전체를 출력하세요. 설명은 붙이지 마세요.
- 요청과 관계없는 부분, # 제목 형식, 끝의 해시태그 줄과 참고한 자료 목록은 그대로 유지하세요."""

    user = f"""{target}

[요청]
{instruction}

[전체 글]
---
{markdown}
---"""
    yield from _stream_text(_SYSTEM, user, api_key)


# ---------- 제목 후보 · SEO 메타 설명 ----------

class ArticleMeta(BaseModel):
    """글 메타 정보 (구조화 출력 스키마)"""
    titles: list[str]
    meta_description: str


def generate_article_meta(markdown: str, *, api_key: Optional[str] = None) -> ArticleMeta:
    """완성된 글을 바탕으로 제목 후보 5개와 SEO 메타 설명을 생성합니다."""
    client = Anthropic(api_key=api_key or None)
    prompt = f"""다음 티스토리 블로그 글에 어울리는 메타 정보를 만들어 주세요.

- titles: 클릭하고 싶어지는 제목 후보 5개 (각 20~40자, 핵심 키워드를 앞쪽에 배치, 과장·낚시성 표현 금지)
- meta_description: 검색 결과에 노출될 요약 설명 1개 (80~150자, 글의 핵심 정보를 담아 자연스럽게)

--- 글 ---
{markdown[:8000]}
---"""
    resp = client.messages.parse(
        model=_get_model(),
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
        output_format=ArticleMeta,
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"메타 정보를 생성하지 못했습니다. (stop_reason={resp.stop_reason})")
    return resp.parsed_output
