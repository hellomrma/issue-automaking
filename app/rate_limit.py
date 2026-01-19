"""간단한 인메모리 Rate Limiter"""
import time
from collections import defaultdict
from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    """
    인메모리 Rate Limiter.
    requests_per_minute: 분당 허용 요청 수
    """

    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        """클라이언트 식별자 (IP 기반)"""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_old_requests(self, client_id: str) -> None:
        """1분이 지난 요청 기록 제거"""
        now = time.time()
        cutoff = now - 60
        self.requests[client_id] = [
            ts for ts in self.requests[client_id] if ts > cutoff
        ]

    def is_allowed(self, request: Request) -> bool:
        """요청 허용 여부 확인"""
        client_id = self._get_client_id(request)
        self._cleanup_old_requests(client_id)
        return len(self.requests[client_id]) < self.requests_per_minute

    def record_request(self, request: Request) -> None:
        """요청 기록"""
        client_id = self._get_client_id(request)
        self.requests[client_id].append(time.time())

    def get_remaining(self, request: Request) -> int:
        """남은 요청 횟수"""
        client_id = self._get_client_id(request)
        self._cleanup_old_requests(client_id)
        return max(0, self.requests_per_minute - len(self.requests[client_id]))

    def get_reset_time(self, request: Request) -> int:
        """리셋까지 남은 초"""
        client_id = self._get_client_id(request)
        if not self.requests[client_id]:
            return 0
        oldest = min(self.requests[client_id])
        return max(0, int(60 - (time.time() - oldest)))


# 글로벌 Rate Limiter 인스턴스
# 글 생성: 분당 5회 (API 비용 고려)
generate_limiter = RateLimiter(requests_per_minute=5)
# 트렌드 조회: 분당 20회
trends_limiter = RateLimiter(requests_per_minute=20)


def rate_limit(limiter: RateLimiter) -> Callable:
    """Rate Limit 데코레이터 (의존성 주입용)"""

    def check_rate_limit(request: Request) -> None:
        if not limiter.is_allowed(request):
            reset_time = limiter.get_reset_time(request)
            raise HTTPException(
                status_code=429,
                detail=f"요청이 너무 많습니다. {reset_time}초 후에 다시 시도해 주세요.",
                headers={"Retry-After": str(reset_time)},
            )
        limiter.record_request(request)

    return check_rate_limit
