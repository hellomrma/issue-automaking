"""키워드에 대한 최신 웹 검색·뉴스 결과 수집 (DuckDuckGo)"""
import logging
from typing import Optional

logger = logging.getLogger("app.search")


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
