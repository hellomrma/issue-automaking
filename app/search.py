"""키워드에 대한 최신 웹 검색·뉴스 결과 수집 (DuckDuckGo)"""
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("app.search")

# URL 콘텐츠 추출 시 무시할 태그
_IGNORE_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "form"}


def fetch_url_content(url: str, timeout: int = 15) -> dict:
    """
    URL의 콘텐츠를 가져와서 제목, 본문 텍스트, 메타 설명을 추출합니다.

    Returns:
        dict: {
            "url": str,
            "title": str,
            "description": str,
            "content": str,
            "keywords": list[str]
        }
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    result = {
        "url": url,
        "title": "",
        "description": "",
        "content": "",
        "keywords": [],
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
    except Exception as e:
        logger.warning("fetch_url_content request failed: %s", e)
        raise ValueError(f"URL을 가져올 수 없습니다: {e}")

    soup = BeautifulSoup(html, "html.parser")

    # 제목 추출
    if soup.title and soup.title.string:
        result["title"] = soup.title.string.strip()

    # 메타 설명 추출
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        result["description"] = meta_desc["content"].strip()

    # OG 태그에서 추가 정보
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content") and not result["title"]:
        result["title"] = og_title["content"].strip()

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content") and not result["description"]:
        result["description"] = og_desc["content"].strip()

    # 메타 키워드 추출
    meta_keywords = soup.find("meta", attrs={"name": "keywords"})
    if meta_keywords and meta_keywords.get("content"):
        keywords = [k.strip() for k in meta_keywords["content"].split(",") if k.strip()]
        result["keywords"] = keywords[:10]

    # 본문 텍스트 추출 (불필요한 태그 제거)
    for tag in soup.find_all(_IGNORE_TAGS):
        tag.decompose()

    # article 또는 main 태그 우선, 없으면 body
    main_content = soup.find("article") or soup.find("main") or soup.find("body")

    if main_content:
        # 텍스트 추출 및 정리
        text = main_content.get_text(separator="\n", strip=True)
        # 연속 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        # 너무 긴 경우 잘라내기 (약 8000자)
        if len(text) > 8000:
            text = text[:8000] + "..."
        result["content"] = text.strip()

    return result


def extract_keywords_from_content(content_data: dict, max_keywords: int = 5) -> list[str]:
    """
    URL 콘텐츠에서 검색에 사용할 키워드를 추출합니다.
    제목, 메타 키워드, 본문에서 핵심 키워드를 추출.
    """
    keywords = []

    # 메타 키워드가 있으면 우선 사용
    if content_data.get("keywords"):
        keywords.extend(content_data["keywords"][:max_keywords])

    # 제목에서 키워드 추출
    title = content_data.get("title", "")
    if title:
        # 간단한 키워드 추출: 특수문자 제거 후 긴 단어 추출
        title_words = re.findall(r"[가-힣a-zA-Z0-9]+", title)
        title_words = [w for w in title_words if len(w) >= 2]
        keywords.extend(title_words[:3])

    # 중복 제거 및 개수 제한
    seen = set()
    unique_keywords = []
    for k in keywords:
        k_lower = k.lower()
        if k_lower not in seen:
            seen.add(k_lower)
            unique_keywords.append(k)

    return unique_keywords[:max_keywords]


def search_related_to_url(
    url: str,
    *,
    max_results: int = 5,
    max_news: int = 5,
    region: str = "kr-ko",
    timelimit: Optional[str] = "m",
) -> tuple[dict, str]:
    """
    URL의 콘텐츠를 분석하고, 관련 정보를 웹에서 검색합니다.

    Returns:
        tuple: (url_content_dict, related_search_results_str)
    """
    # 1. URL 콘텐츠 가져오기
    url_content = fetch_url_content(url)

    # 2. 키워드 추출
    keywords = extract_keywords_from_content(url_content)

    if not keywords:
        # 키워드를 추출할 수 없으면 제목 전체 사용
        keywords = [url_content.get("title", "")]

    # 3. 추출한 키워드로 관련 정보 검색
    search_query = " ".join(keywords[:3])  # 상위 3개 키워드로 검색

    if search_query.strip():
        related_search = search_web(
            search_query,
            max_results=max_results,
            max_news=max_news,
            region=region,
            timelimit=timelimit,
        )
    else:
        related_search = ""

    return url_content, related_search


def _fmt_text_results(results: list, prefix: str = "") -> list[str]:
    """검색 결과 리스트를 제목·요약·URL 포맷 문자열 목록으로 변환."""
    lines = []
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        body = (r.get("body") or r.get("snippet") or "").strip()
        href = (r.get("href") or r.get("link") or r.get("url") or "").strip()
        lbl = f"{prefix}[{i}]" if prefix else f"[{i}]"
        parts = [f"{lbl} {title}"] if title else [lbl]
        if body:
            parts.append(f"  요약: {body}")
        if href:
            parts.append(f"  URL: {href}")
        lines.append("\n".join(parts))
    return lines


def search_web(
    keyword: str,
    *,
    max_results: int = 5,
    max_news: int = 5,
    region: str = "kr-ko",
    timelimit: Optional[str] = "m",
) -> str:
    """
    키워드로 웹 검색 + 뉴스 검색을 수행하고, 제목·요약·URL을 포맷한 문자열을 반환합니다.
    일반 검색과 뉴스 기사를 모두 포함. 실패한 쪽은 생략. (API 키 불필요)

    region: kr-ko(한국), wt-wt(전세계) 등
    timelimit: m(한 달), w(일 주), d(하루), None(제한 없음)
    """
    if not (keyword or "").strip():
        return ""
    q = keyword.strip()
    sections: list[str] = []
    text_results: list = []
    news_results: list = []

    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            # 1) 일반 웹 검색
            try:
                gen = ddgs.text(q, region=region, timelimit=timelimit, max_results=max_results)
                text_results = list(gen) if gen else []
            except Exception as e:
                logger.warning("search_web text failed: %s", e)

            # 2) 뉴스 기사 검색 (구글 뉴스 등에 노출되는 뉴스 소스 포함)
            try:
                gen = ddgs.news(q, region=region, timelimit=timelimit, max_results=max_news)
                news_results = list(gen) if gen else []
            except Exception as e:
                logger.warning("search_web news failed: %s", e)
    except Exception as e:
        logger.warning("search_web failed: %s", e)

    if text_results:
        sections.append("--- 일반 웹 검색 ---\n" + "\n\n".join(_fmt_text_results(text_results)))

    if news_results:
        lines = []
        for i, r in enumerate(news_results, 1):
            title = (r.get("title") or "").strip()
            body = (r.get("body") or r.get("snippet") or "").strip()
            url = (r.get("url") or r.get("href") or r.get("link") or "").strip()
            src = (r.get("source") or "").strip()
            date = (r.get("date") or "").strip()
            extra = " ".join(x for x in [src, date] if x)
            parts = [f"[뉴스 {i}] {title}" + (f" ({extra})" if extra else "")]
            if body:
                parts.append(f"  요약: {body}")
            if url:
                parts.append(f"  URL: {url}")
            lines.append("\n".join(parts))
        sections.append("--- 뉴스 기사 ---\n" + "\n\n".join(lines))

    if not sections:
        return ""
    return "\n\n".join(sections)
