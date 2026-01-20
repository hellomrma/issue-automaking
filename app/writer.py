"""키워드 기반 블로그 글 생성 (Anthropic Claude API)"""
import os
from typing import Generator, Optional

from anthropic import Anthropic

# 모델 ID. 환경변수 CLAUDE_MODEL 로 변경 가능 (예: claude-3-5-haiku-20241022)
DEFAULT_MODEL = "claude-sonnet-4-20250514"


_LENGTH_DESC = {
    "short": "본문 400~600자 분량",
    "medium": "본문 800~1,200자 분량",
    "long": "본문 1,200~1,800자 분량",
}


def _build_prompts(
    keyword: str,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    web_context: Optional[str] = None,
    length: str = "medium",
    guide: Optional[str] = None,
    reference_content: Optional[str] = None,
) -> tuple[str, str]:
    """시스템 프롬프트와 사용자 프롬프트를 생성합니다."""
    style_desc = {
        "정보성": "유용한 정보를 체계적으로 정리한 설명형",
        "리뷰": "주관적인 경험과 의견이 담긴 리뷰형",
        "How-to": "단계별로 따라 할 수 있는 가이드형",
        "뉴스해설": "최근 이슈를 요약하고 의견을 덧붙이는 해설형",
    }.get(style, "정보성")

    length_desc = _LENGTH_DESC.get(length, _LENGTH_DESC["medium"])
    lang_instruction = "반드시 한국어로만 작성하세요." if lang == "ko" else "Write in English only."
    title_instruction = "첫 번째 # 제목을 글의 메인 제목으로 사용하세요." if lang == "ko" else "Use the first # heading as the main title."

    system = (
        "You are an expert blog writer for Tistory. Your output must be valid Markdown only, "
        "no code fences or extra labels. Use ## for sections, ### for subsections, "
        "**bold**, lists, and short paragraphs. No YAML frontmatter."
    )
    user = f"""다음 키워드를 주제로 티스토리 블로그 글을 마크다운으로 작성해 주세요.

키워드: {keyword}
글 스타일: {style_desc}
{lang_instruction}
{title_instruction}

요구사항:
- {length_desc} (의미 있는 문단/문장 기준)
- **글체**: 편안하고 부드러운 톤으로 써 주세요. '서론', '결론', '본론', '이에 대해', '다음과 같이', '정리하면' 같은 딱딱하거나 격식 있는 표현은 쓰지 말고, 구어체에 가까운 친근한 문장으로 자연스럽게 이어 주세요.
- 소제목(##, ###)으로 읽기 쉽게 구분하되, '서론/결론'처럼 형식을 드러내는 제목은 쓰지 마세요.
- 자연스럽고 SEO에 유리한 문장
- 마지막은 따로 '결론'이라 부르지 말고, 이야기를 부드럽게 마무리하는 문단 1~2개
- 글 끝에 #태그1 #태그2 #태그3 ... 형태로 태그 5~10개를 한 줄에 붙여 주세요. (주제·키워드·SEO 관련, 공백으로 구분)
"""
    if use_emoji:
        user += "\n- 제목, 소제목, 문단에 주제에 맞는 이모지를 적당히 넣어 주세요. 과하지 않게 사용하세요."
    else:
        user += "\n- 이모지는 사용하지 마세요."

    if web_context and (web_context := web_context.strip()):
        user += f"""

아래는 이 키워드에 대한 최신 웹 검색 결과와 **뉴스 기사**입니다. 뉴스(일반 뉴스·구글 뉴스 등)를 특히 참고하여 **최신 동향·숫자·사실·시사**를 반영하고, 독자가 관심 가질 만한 시의성 있는 내용을 담아 주세요. 원문을 그대로 복사하지 말고 재해석하여 자연스럽게 활용하세요.

---
{web_context}
---
"""

    if guide and (guide := guide.strip()):
        user += f"""

아래는 사용자가 요청한 **글 작성 가이드**입니다. 이 가이드를 최우선으로 반영하여 글을 작성해 주세요:

---
{guide}
---
"""

    if reference_content and (reference_content := reference_content.strip()):
        user += f"""

아래는 **참고해야 할 URL의 콘텐츠**입니다. 이 내용을 참고하여 글을 작성해 주세요. 원문을 그대로 복사하지 말고 참고만 하세요:

---
{reference_content[:4000]}
---
"""
    return system, user


def _build_url_prompts(
    url_content: dict,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    related_search: str = "",
    length: str = "medium",
    guide: Optional[str] = None,
) -> tuple[str, str]:
    """URL 콘텐츠 기반 블로그 글 생성을 위한 프롬프트를 생성합니다."""
    style_desc = {
        "정보성": "유용한 정보를 체계적으로 정리한 설명형",
        "리뷰": "주관적인 경험과 의견이 담긴 리뷰형",
        "How-to": "단계별로 따라 할 수 있는 가이드형",
        "뉴스해설": "최근 이슈를 요약하고 의견을 덧붙이는 해설형",
    }.get(style, "정보성")

    length_desc = _LENGTH_DESC.get(length, _LENGTH_DESC["medium"])
    lang_instruction = "반드시 한국어로만 작성하세요." if lang == "ko" else "Write in English only."
    title_instruction = "첫 번째 # 제목을 글의 메인 제목으로 사용하세요." if lang == "ko" else "Use the first # heading as the main title."

    system = (
        "You are an expert blog writer for Tistory. Your output must be valid Markdown only, "
        "no code fences or extra labels. Use ## for sections, ### for subsections, "
        "**bold**, lists, and short paragraphs. No YAML frontmatter."
    )

    # URL 콘텐츠 정보 구성
    url_info = f"URL: {url_content.get('url', '')}"
    if url_content.get("title"):
        url_info += f"\n제목: {url_content['title']}"
    if url_content.get("description"):
        url_info += f"\n설명: {url_content['description']}"

    user = f"""다음 URL의 콘텐츠를 분석하여 관련된 티스토리 블로그 글을 마크다운으로 작성해 주세요.

{url_info}

--- 원본 콘텐츠 ---
{url_content.get('content', '')[:6000]}
---

글 스타일: {style_desc}
{lang_instruction}
{title_instruction}

요구사항:
- {length_desc} (의미 있는 문단/문장 기준)
- 원본 URL의 내용을 그대로 복사하지 말고, 핵심 내용을 파악하여 **새로운 관점**으로 재구성해 주세요
- 원본의 주제를 확장하거나, 독자에게 더 유용한 정보를 추가해 주세요
- **글체**: 편안하고 부드러운 톤으로 써 주세요. '서론', '결론', '본론', '이에 대해', '다음과 같이', '정리하면' 같은 딱딱하거나 격식 있는 표현은 쓰지 말고, 구어체에 가까운 친근한 문장으로 자연스럽게 이어 주세요.
- 소제목(##, ###)으로 읽기 쉽게 구분하되, '서론/결론'처럼 형식을 드러내는 제목은 쓰지 마세요.
- 자연스럽고 SEO에 유리한 문장
- 마지막은 따로 '결론'이라 부르지 말고, 이야기를 부드럽게 마무리하는 문단 1~2개
- 글 끝에 #태그1 #태그2 #태그3 ... 형태로 태그 5~10개를 한 줄에 붙여 주세요. (주제·키워드·SEO 관련, 공백으로 구분)
"""
    if use_emoji:
        user += "\n- 제목, 소제목, 문단에 주제에 맞는 이모지를 적당히 넣어 주세요. 과하지 않게 사용하세요."
    else:
        user += "\n- 이모지는 사용하지 마세요."

    if related_search and (related_search := related_search.strip()):
        user += f"""

아래는 이 주제와 관련된 최신 웹 검색 결과와 **뉴스 기사**입니다. 이를 참고하여 **최신 동향·숫자·사실·시사**를 반영하고, 독자가 관심 가질 만한 시의성 있는 내용을 담아 주세요. 원문을 그대로 복사하지 말고 재해석하여 자연스럽게 활용하세요.

---
{related_search}
---
"""

    if guide and (guide := guide.strip()):
        user += f"""

아래는 사용자가 요청한 **글 작성 가이드**입니다. 이 가이드를 최우선으로 반영하여 글을 작성해 주세요:

---
{guide}
---
"""
    return system, user


def _clean_markdown(text: str) -> str:
    """마크다운 코드 블록으로 감싼 경우 제거합니다."""
    if text.startswith("```") and "```" in text[3:]:
        first = text.find("\n")
        text = text[first + 1 : text.rfind("```")].strip()
    return text


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
) -> Generator[str, None, None]:
    """
    키워드를 바탕으로 티스토리용 마크다운 블로그 글을 스트리밍으로 생성합니다.
    length: short | medium | long
    guide: 사용자가 원하는 글 작성 방향/톤/포함할 내용
    reference_content: 참고할 URL의 콘텐츠
    """
    client = Anthropic(api_key=api_key or None)
    system, user = _build_prompts(keyword, lang, style, use_emoji, web_context, length, guide, reference_content)
    model = (os.getenv("CLAUDE_MODEL") or "").strip() or DEFAULT_MODEL

    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.7,
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_article_md(
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
) -> str:
    """
    키워드를 바탕으로 티스토리용 마크다운 블로그 글을 생성합니다.
    api_key: Anthropic(Claude) API 키 (None이면 환경변수 ANTHROPIC_API_KEY 사용)
    lang: ko | en
    style: 정보성 | 리뷰 | How-to | 뉴스해설
    use_emoji: True면 제목·소제목·문단에 적절한 이모지 포함
    web_context: 최신 웹 검색 결과 텍스트. 있으면 이를 참고해 최신 정보를 반영
    length: short | medium | long (본문 분량)
    guide: 사용자가 원하는 글 작성 방향/톤/포함할 내용
    reference_content: 참고할 URL의 콘텐츠
    """
    client = Anthropic(api_key=api_key or None)
    system, user = _build_prompts(keyword, lang, style, use_emoji, web_context, length, guide, reference_content)
    model = (os.getenv("CLAUDE_MODEL") or "").strip() or DEFAULT_MODEL

    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.7,
    )
    parts = [b.text for b in resp.content if getattr(b, "text", None)]
    text = "".join(parts).strip()
    return _clean_markdown(text)


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
) -> Generator[str, None, None]:
    """
    URL 콘텐츠를 기반으로 티스토리용 마크다운 블로그 글을 스트리밍으로 생성합니다.
    guide: 사용자가 원하는 글 작성 방향/톤/포함할 내용
    """
    client = Anthropic(api_key=api_key or None)
    system, user = _build_url_prompts(url_content, lang, style, use_emoji, related_search or "", length, guide)
    model = (os.getenv("CLAUDE_MODEL") or "").strip() or DEFAULT_MODEL

    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.7,
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_article_from_url(
    url_content: dict,
    *,
    api_key: Optional[str] = None,
    lang: str = "ko",
    style: str = "정보성",
    use_emoji: bool = False,
    related_search: Optional[str] = None,
    length: str = "medium",
    guide: Optional[str] = None,
) -> str:
    """
    URL 콘텐츠를 기반으로 티스토리용 마크다운 블로그 글을 생성합니다.

    url_content: fetch_url_content()에서 반환된 dict
    api_key: Anthropic(Claude) API 키 (None이면 환경변수 ANTHROPIC_API_KEY 사용)
    lang: ko | en
    style: 정보성 | 리뷰 | How-to | 뉴스해설
    use_emoji: True면 제목·소제목·문단에 적절한 이모지 포함
    related_search: 관련 웹 검색 결과 텍스트
    length: short | medium | long (본문 분량)
    guide: 사용자가 원하는 글 작성 방향/톤/포함할 내용
    """
    client = Anthropic(api_key=api_key or None)
    system, user = _build_url_prompts(url_content, lang, style, use_emoji, related_search or "", length, guide)
    model = (os.getenv("CLAUDE_MODEL") or "").strip() or DEFAULT_MODEL

    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.7,
    )
    parts = [b.text for b in resp.content if getattr(b, "text", None)]
    text = "".join(parts).strip()
    return _clean_markdown(text)
