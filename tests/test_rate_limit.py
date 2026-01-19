"""Rate Limiter 테스트"""
import time
from unittest.mock import MagicMock

import pytest

from app.rate_limit import RateLimiter


class TestRateLimiter:
    """RateLimiter 클래스 테스트"""

    def _make_request(self, ip: str = "127.0.0.1") -> MagicMock:
        """테스트용 Request 객체 생성"""
        request = MagicMock()
        request.client.host = ip
        request.headers.get.return_value = None
        return request

    def test_allows_requests_under_limit(self):
        """제한 내 요청은 허용"""
        limiter = RateLimiter(requests_per_minute=5)
        request = self._make_request()

        for _ in range(5):
            assert limiter.is_allowed(request) is True
            limiter.record_request(request)

    def test_blocks_requests_over_limit(self):
        """제한 초과 요청은 차단"""
        limiter = RateLimiter(requests_per_minute=3)
        request = self._make_request()

        for _ in range(3):
            limiter.record_request(request)

        assert limiter.is_allowed(request) is False

    def test_different_ips_have_separate_limits(self):
        """IP별로 별도 제한 적용"""
        limiter = RateLimiter(requests_per_minute=2)
        request1 = self._make_request("192.168.1.1")
        request2 = self._make_request("192.168.1.2")

        # 첫 번째 IP 제한 소진
        for _ in range(2):
            limiter.record_request(request1)

        # 첫 번째 IP는 차단
        assert limiter.is_allowed(request1) is False
        # 두 번째 IP는 허용
        assert limiter.is_allowed(request2) is True

    def test_get_remaining(self):
        """남은 요청 횟수 확인"""
        limiter = RateLimiter(requests_per_minute=5)
        request = self._make_request()

        assert limiter.get_remaining(request) == 5

        limiter.record_request(request)
        assert limiter.get_remaining(request) == 4

        limiter.record_request(request)
        limiter.record_request(request)
        assert limiter.get_remaining(request) == 2

    def test_forwarded_for_header(self):
        """X-Forwarded-For 헤더 지원"""
        limiter = RateLimiter(requests_per_minute=2)
        request = MagicMock()
        request.headers.get.return_value = "10.0.0.1, 10.0.0.2"

        limiter.record_request(request)
        limiter.record_request(request)

        assert limiter.is_allowed(request) is False

    def test_reset_time(self):
        """리셋 시간 확인"""
        limiter = RateLimiter(requests_per_minute=5)
        request = self._make_request()

        # 요청 없으면 리셋 시간 0
        assert limiter.get_reset_time(request) == 0

        # 요청 기록 후 리셋 시간 확인
        limiter.record_request(request)
        reset_time = limiter.get_reset_time(request)
        assert 0 < reset_time <= 60
