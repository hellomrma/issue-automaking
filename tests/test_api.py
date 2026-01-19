"""API 엔드포인트 테스트"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import GenerateRequest, app

client = TestClient(app)


class TestRegionsAPI:
    """GET /api/regions 테스트"""

    def test_returns_regions(self):
        """지역 목록 반환"""
        response = client.get("/api/regions")

        assert response.status_code == 200
        data = response.json()
        assert "regions" in data
        assert len(data["regions"]) > 0

    def test_region_structure(self):
        """지역 데이터 구조 확인"""
        response = client.get("/api/regions")
        data = response.json()

        for region in data["regions"]:
            assert "id" in region
            assert "name" in region


class TestTrendsAPI:
    """GET /api/trends 테스트"""

    def test_returns_keywords(self):
        """키워드 목록 반환"""
        response = client.get("/api/trends?region=south_korea&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert "keywords" in data
        assert "region" in data
        assert "source" in data

    def test_limit_parameter(self):
        """limit 파라미터 적용"""
        response = client.get("/api/trends?limit=3")
        data = response.json()

        assert len(data["keywords"]) <= 3

    def test_invalid_limit(self):
        """유효하지 않은 limit 거부"""
        response = client.get("/api/trends?limit=0")
        assert response.status_code == 422

        response = client.get("/api/trends?limit=101")
        assert response.status_code == 422


class TestGenerateRequestValidation:
    """GenerateRequest 모델 검증 테스트"""

    def test_valid_request(self):
        """유효한 요청"""
        req = GenerateRequest(keyword="테스트 키워드")
        assert req.keyword == "테스트 키워드"

    def test_keyword_too_short(self):
        """키워드가 너무 짧으면 거부"""
        with pytest.raises(ValidationError) as exc_info:
            GenerateRequest(keyword="a")
        assert "2자 이상" in str(exc_info.value)

    def test_keyword_too_long(self):
        """키워드가 너무 길면 거부"""
        with pytest.raises(ValidationError) as exc_info:
            GenerateRequest(keyword="a" * 101)
        assert "100자 이하" in str(exc_info.value)

    def test_keyword_stripped(self):
        """키워드 앞뒤 공백 제거"""
        req = GenerateRequest(keyword="  테스트  ")
        assert req.keyword == "테스트"

    def test_invalid_lang(self):
        """유효하지 않은 언어 거부"""
        with pytest.raises(ValidationError) as exc_info:
            GenerateRequest(keyword="테스트", lang="jp")
        assert "지원하지 않는 언어" in str(exc_info.value)

    def test_invalid_style(self):
        """유효하지 않은 스타일 거부"""
        with pytest.raises(ValidationError) as exc_info:
            GenerateRequest(keyword="테스트", style="에세이")
        assert "지원하지 않는 스타일" in str(exc_info.value)

    def test_invalid_api_key_format(self):
        """유효하지 않은 API 키 형식 거부"""
        with pytest.raises(ValidationError) as exc_info:
            GenerateRequest(keyword="테스트", anthropic_api_key="invalid-key")
        assert "API 키 형식" in str(exc_info.value)

    def test_api_key_too_short(self):
        """API 키가 너무 짧으면 거부"""
        with pytest.raises(ValidationError) as exc_info:
            GenerateRequest(keyword="테스트", anthropic_api_key="sk-ant-short")
        assert "너무 짧" in str(exc_info.value)

    def test_empty_api_key_allowed(self):
        """빈 API 키는 허용 (서버 env 사용)"""
        req = GenerateRequest(keyword="테스트", anthropic_api_key="")
        assert req.anthropic_api_key is None

    def test_none_api_key_allowed(self):
        """None API 키는 허용"""
        req = GenerateRequest(keyword="테스트", anthropic_api_key=None)
        assert req.anthropic_api_key is None


class TestGenerateAPI:
    """POST /api/generate 테스트"""

    def test_missing_keyword(self):
        """키워드 누락 시 에러"""
        response = client.post("/api/generate", json={})
        assert response.status_code == 422

    def test_empty_keyword(self):
        """빈 키워드 에러"""
        response = client.post("/api/generate", json={"keyword": ""})
        assert response.status_code == 422

    def test_request_accepted(self):
        """유효한 요청은 처리됨 (API 키 유무에 따라 결과 다름)"""
        response = client.post("/api/generate", json={"keyword": "테스트 키워드"})
        # 환경변수에 API 키가 있으면 200, 없으면 400
        assert response.status_code in (200, 400, 502)
