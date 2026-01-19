"""인터넷 트렌드 키워드 수집 (Google Trends)"""
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("app.trends")


@dataclass
class CacheEntry:
    """캐시 항목"""
    keywords: list[str]
    source: str
    google_keywords: list[str]
    recommend_keywords: list[str]
    timestamp: float


class TrendsCache:
    """트렌드 키워드 TTL 캐시"""

    def __init__(self, ttl_seconds: int = 600):  # 기본 10분
        self.ttl = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}

    def _make_key(self, region: str, limit: int) -> str:
        return f"{region}:{limit}"

    def get(
        self, region: str, limit: int
    ) -> Optional[tuple[list[str], str, list[str], list[str]]]:
        """캐시에서 조회. 만료되었으면 None 반환. (keywords, source, google, recommend)"""
        key = self._make_key(region, limit)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() - entry.timestamp > self.ttl:
            del self._cache[key]
            return None
        return (
            entry.keywords,
            entry.source,
            entry.google_keywords,
            entry.recommend_keywords,
        )

    def set(
        self,
        region: str,
        limit: int,
        keywords: list[str],
        source: str,
        google_keywords: list[str],
        recommend_keywords: list[str],
    ) -> None:
        """캐시에 저장"""
        key = self._make_key(region, limit)
        self._cache[key] = CacheEntry(
            keywords=keywords,
            source=source,
            google_keywords=google_keywords,
            recommend_keywords=recommend_keywords,
            timestamp=time.time(),
        )

    def clear(self) -> None:
        """캐시 전체 삭제"""
        self._cache.clear()


# 글로벌 캐시 인스턴스 (10분 TTL)
_trends_cache = TrendsCache(ttl_seconds=600)

# CSV 수집 사용 여부 (Chrome 필요, 느림, 타임아웃 발생 가능)
# 환경변수 USE_CSV_TRENDS=true 로 설정 시 활성화
USE_CSV_TRENDS = os.getenv("USE_CSV_TRENDS", "false").lower() == "true"

# 지역 id -> (표시 이름, Google Trends geo 2자리 코드)
REGIONS = {
    "south_korea": ("한국", "KR"),
}

# Google 실패 시 예시 키워드 (2024~2025 인기 주제, 60개+)
FALLBACK_KEYWORDS = [
    # AI/테크
    "ChatGPT 활용법", "Claude AI", "AI 이미지 생성", "Midjourney 사용법", "Copilot 활용",
    "AI 자동화", "GPT-4o", "AI 코딩", "Sora AI", "노코드 자동화",
    # 경제/투자
    "비트코인 전망", "금 투자", "미국 주식", "배당주 추천", "ETF 추천",
    "부동산 전망", "금리 인하", "환율 전망", "연말정산 꿀팁", "청년 지원금",
    # IT/가젯
    "아이폰 16", "갤럭시 S25", "맥북 M4", "PS5 프로", "닌텐도 스위치2",
    "무선 이어폰 추천", "태블릿 추천", "모니터 추천", "키보드 추천", "마우스 추천",
    # 생활/건강
    "다이어트 식단", "홈트레이닝", "헬스장 루틴", "수면 개선", "명상 앱",
    "맛집 추천", "카페 추천", "밀키트 추천", "에어프라이어 레시피", "간헐적 단식",
    # 여행/문화
    "국내 여행지", "제주도 맛집", "일본 여행", "유럽 여행", "항공권 특가",
    "넷플릭스 추천", "왓챠 추천", "웨이브 추천", "K-드라마", "영화 리뷰",
    # 커리어/교육
    "이직 준비", "면접 팁", "자기소개서", "코딩 독학", "영어 회화",
    "자격증 추천", "부업 추천", "재택근무 팁", "프리랜서", "온라인 강의",
    # 취미
    "캠핑 장비", "등산 코스", "러닝 입문", "홈카페", "독서 추천",
    "게임 추천", "보드게임", "레고 추천", "반려동물", "식물 키우기",
]


def _parse_csv_keywords(path: str, limit: int) -> list[str]:
    """CSV(JSON) 내보내기 파일에서 'Trends' 컬럼만 추출. 최대 limit개."""
    keywords: list[str] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data if isinstance(data, list) else (data.get("data") or data.get("rows") or [])
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        k = row.get("Trends") or row.get("trends") or row.get("title") or ""
        if k and isinstance(k, str):
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                keywords.append(k)
                if len(keywords) >= limit:
                    break
        # 'Trend breakdown' 관련어로 보충 (선택)
        extra = row.get("Trend breakdown") or ""
        if isinstance(extra, str) and len(keywords) < limit:
            for part in extra.split(","):
                t = part.strip()
                if t and t not in seen and 2 <= len(t) <= 50:
                    seen.add(t)
                    keywords.append(t)
                    if len(keywords) >= limit:
                        break
    return keywords[:limit]


def get_trending_keywords(
    region: str = "south_korea", limit: int = 20
) -> tuple[list[str], str, list[str], list[str]]:
    """
    Google Trends 실시간 인기 검색어를 가져옵니다.
    - 한국(south_korea): CSV(최대 ~480개) 우선 시도 → 실패 시 RSS → 예시 키워드.
      CSV는 Chrome 필요, 10초 정도 소요.
    - 그 외 지역: RSS(~10~20개) → 예시 키워드.
    region: REGIONS 키 (예: south_korea)
    limit: 반환할 키워드 개수 (기본 20)
    반환: (keywords, source, google_keywords, recommend_keywords)
      source: 'csv'|'rss'|'mixed'|'...(cached)'
    """
    # 캐시 확인
    cached = _trends_cache.get(region, limit)
    if cached:
        keywords, source, google_kw, recommend_kw = cached
        logger.debug("캐시 히트: region=%s, limit=%d", region, limit)
        return keywords, f"{source}(cached)", google_kw, recommend_kw

    entry = REGIONS.get(region, REGIONS["south_korea"])
    geo = entry[1]  # 2-letter: KR, US, JP, ...

    # 0) 한국만: CSV 시도 (Chrome 필요, ~480개, 10초 내외)
    # USE_CSV_TRENDS=true 환경변수 설정 시에만 활성화
    if region == "south_korea" and USE_CSV_TRENDS:
        logger.info("CSV 트렌드 수집 시도 중 (region=%s)...", region)
        try:
            from trendspyg import download_google_trends_csv

            raw = download_google_trends_csv(geo=geo, hours=24, output_format="json")
            if isinstance(raw, str) and os.path.isfile(raw):
                keywords = _parse_csv_keywords(raw, limit)
                if keywords:
                    logger.info("CSV 트렌드 수집 성공: %d개 키워드", len(keywords))
                    _trends_cache.set(region, limit, keywords, "csv", keywords, [])
                    return keywords, "csv", keywords, []
                else:
                    logger.warning("CSV 파일은 있으나 키워드 파싱 실패")
            else:
                logger.warning("CSV 다운로드 결과가 유효하지 않음: %s", type(raw))
        except Exception as e:
            logger.warning("CSV 트렌드 수집 실패 (region=%s): %s", region, e)

    # 1) trendspyg RSS 시도 (모든 지역, ~10~20개)
    rss_keywords: list[str] = []
    try:
        from trendspyg import download_google_trends_rss

        data = download_google_trends_rss(geo=geo)
        for x in (data or []):
            if isinstance(x, dict):
                k = x.get("trend") or x.get("title")
            else:
                k = getattr(x, "trend", None) or getattr(x, "title", None)
            if k and str(k).strip():
                rss_keywords.append(str(k).strip())
    except Exception as e:
        logger.warning("RSS 트렌드 수집 실패 (region=%s): %s", region, e)

    # 2) 추천 키워드 준비 (중복 제거)
    seen: set[str] = set(rss_keywords)
    recommend_keywords: list[str] = []
    for kw in FALLBACK_KEYWORDS:
        if len(rss_keywords) + len(recommend_keywords) >= limit:
            break
        if kw not in seen:
            recommend_keywords.append(kw)
            seen.add(kw)

    # 3) 결과 반환
    combined = rss_keywords + recommend_keywords
    source_label = "rss" if rss_keywords and not recommend_keywords else "mixed"

    if combined:
        _trends_cache.set(
            region, limit, combined[:limit], source_label, rss_keywords, recommend_keywords
        )

    return combined[:limit], source_label, rss_keywords, recommend_keywords
