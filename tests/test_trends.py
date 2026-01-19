"""트렌드 캐싱 테스트"""
import time

import pytest

from app.trends import FALLBACK_KEYWORDS, REGIONS, TrendsCache, get_trending_keywords


class TestTrendsCache:
    """TrendsCache 클래스 테스트"""

    def test_cache_miss(self):
        """캐시 미스 시 None 반환"""
        cache = TrendsCache(ttl_seconds=60)
        assert cache.get("south_korea", 20) is None

    def test_cache_hit(self):
        """캐시 히트 시 저장된 값 반환"""
        cache = TrendsCache(ttl_seconds=60)
        keywords = ["키워드1", "키워드2"]

        cache.set("south_korea", 20, keywords, "rss", keywords, [])
        result = cache.get("south_korea", 20)

        assert result is not None
        assert result[0] == keywords
        assert result[1] == "rss"
        assert result[2] == keywords
        assert result[3] == []

    def test_cache_expiry(self):
        """TTL 만료 시 None 반환"""
        cache = TrendsCache(ttl_seconds=1)
        cache.set("south_korea", 20, ["키워드"], "rss", ["키워드"], [])

        # 즉시 조회는 성공
        assert cache.get("south_korea", 20) is not None

        # TTL 이후 조회는 실패
        time.sleep(1.1)
        assert cache.get("south_korea", 20) is None

    def test_different_keys(self):
        """다른 region/limit 조합은 별도 캐시"""
        cache = TrendsCache(ttl_seconds=60)
        cache.set("south_korea", 20, ["키워드A"], "rss", ["키워드A"], [])
        cache.set("south_korea", 30, ["키워드B"], "rss", ["키워드B"], [])

        a = cache.get("south_korea", 20)
        b = cache.get("south_korea", 30)

        assert a[0] == ["키워드A"]
        assert b[0] == ["키워드B"]

    def test_clear(self):
        """캐시 전체 삭제"""
        cache = TrendsCache(ttl_seconds=60)
        cache.set("south_korea", 20, ["키워드"], "rss", ["키워드"], [])

        cache.clear()

        assert cache.get("south_korea", 20) is None


class TestGetTrendingKeywords:
    """get_trending_keywords 함수 테스트"""

    def test_fallback_keywords_exist(self):
        """폴백 키워드가 존재"""
        assert len(FALLBACK_KEYWORDS) > 0

    def test_regions_exist(self):
        """지역 정보가 존재"""
        assert "south_korea" in REGIONS

    def test_returns_tuple(self):
        """튜플 (keywords, source, google, recommend) 반환"""
        keywords, source, google_kw, recommend_kw = get_trending_keywords("south_korea", 5)

        assert isinstance(keywords, list)
        assert isinstance(source, str)
        assert isinstance(google_kw, list)
        assert isinstance(recommend_kw, list)
        assert len(keywords) <= 5

    def test_limit_respected(self):
        """limit 파라미터 준수"""
        keywords, *_ = get_trending_keywords("south_korea", 3)
        assert len(keywords) <= 3

    def test_unknown_region_uses_default(self):
        """알 수 없는 지역은 한국 기본값 사용"""
        keywords, source, *_ = get_trending_keywords("unknown_region", 5)
        # 폴백이든 실제 데이터든 반환되어야 함
        assert isinstance(keywords, list)
