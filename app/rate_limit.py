"""간단한 인메모리 Rate Limiter"""
import os
import time
from collections import defaultdict
from typing import Callable, Optional

from fastapi import HTTPException, Request

# 리버스 프록시(nginx 등) 뒤에서 실행할 때만 TRUST_PROXY=true 로 설정.
# 그 외에는 X-Forwarded-For 를 클라이언트가 위조할 수 있으므로 무시합니다.
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"


class RateLimiter:
    """
    인메모리 Rate Limiter.
    requests_per_minute: 분당 허용 요청 수
    trust_proxy: True면 X-Forwarded-For 헤더로 클라이언트를 식별 (기본: TRUST_PROXY 환경변수)
    """

    def __init__(self, requests_per_minute: int = 10, trust_proxy: Optional[bool] = None):
        self.requests_per_minute = requests_per_minute
        self.trust_proxy = TRUST_PROXY if trust_proxy is None else trust_proxy
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._last_sweep = time.time()

    def _get_client_id(self, request: Request) -> str:
        """클라이언트 식별자 (IP 기반)"""
        if self.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_old_requests(self, client_id: str) -> None:
        """1분이 지난 요청 기록 제거 (기록이 비면 키도 삭제)"""
        cutoff = time.time() - 60
        recent = [ts for ts in self.requests.get(client_id, []) if ts > cutoff]
        if recent:
            self.requests[client_id] = recent
        else:
            self.requests.pop(client_id, None)

    def _sweep(self) -> None:
        """1분마다 모든 클라이언트의 오래된 기록 정리 (메모리 누적 방지)"""
        now = time.time()
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        for client_id in list(self.requests):
            self._cleanup_old_requests(client_id)

    def is_allowed(self, request: Request) -> bool:
        """요청 허용 여부 확인"""
        client_id = self._get_client_id(request)
        self._cleanup_old_requests(client_id)
        return len(self.requests.get(client_id, [])) < self.requests_per_minute

    def record_request(self, request: Request) -> None:
        """요청 기록"""
        self._sweep()
        client_id = self._get_client_id(request)
        self.requests[client_id].append(time.time())

    def get_remaining(self, request: Request) -> int:
        """남은 요청 횟수"""
        client_id = self._get_client_id(request)
        self._cleanup_old_requests(client_id)
        return max(0, self.requests_per_minute - len(self.requests.get(client_id, [])))

    def get_reset_time(self, request: Request) -> int:
        """리셋까지 남은 초"""
        timestamps = self.requests.get(self._get_client_id(request))
        if not timestamps:
            return 0
        return max(0, int(60 - (time.time() - min(timestamps))))


# 글로벌 Rate Limiter 인스턴스
# 글 생성: 분당 5회 (API 비용 고려)
generate_limiter = RateLimiter(requests_per_minute=5)
# 트렌드 조회: 분당 20회
trends_limiter = RateLimiter(requests_per_minute=20)
# 파일 저장: 분당 20회
save_limiter = RateLimiter(requests_per_minute=20)


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
