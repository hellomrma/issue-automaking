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


def _api_error(cls, status, message="error"):
    import anthropic
    import httpx2

    response = httpx2.Response(status, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls(message, response=response, body=None)


class TestErrorDetail:
    """Claude API 예외 → 사용자 메시지 변환"""

    def test_typed_errors(self):
        import anthropic

        from app.main import _error_detail

        assert "키가 올바르지" in _error_detail(_api_error(anthropic.AuthenticationError, 401))
        assert "한도" in _error_detail(_api_error(anthropic.RateLimitError, 429))
        assert "모델" in _error_detail(_api_error(anthropic.NotFoundError, 404))
        assert "크레딧" in _error_detail(
            _api_error(anthropic.BadRequestError, 400, "Your credit balance is too low")
        )

    def test_unknown_error_passthrough(self):
        from app.main import _error_detail

        assert _error_detail(RuntimeError("기타 오류")) == "기타 오류"


class TestGenerateEndpoints:
    """생성 엔드포인트 (Claude 호출은 모킹)"""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        from app.rate_limit import generate_limiter

        generate_limiter.requests.clear()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-1234567890")

    def test_stream_error_line(self, monkeypatch):
        """스트리밍 중 예외는 [ERROR] 줄로 전달"""
        import anthropic

        def _fail(**kwargs):
            yield "# 제목"
            raise _api_error(anthropic.AuthenticationError, 401)

        monkeypatch.setattr("app.main.generate_article_md_stream", _fail)
        res = client.post("/api/generate/stream", json={"keyword": "테스트", "use_web_search": False})
        assert res.status_code == 200
        assert res.text.startswith("# 제목")
        assert "[ERROR] Claude API 키가 올바르지 않습니다." in res.text

    def test_url_mode_without_web_search_skips_search(self, monkeypatch):
        """웹 검색을 끄면 관련 검색을 호출하지 않음"""
        monkeypatch.setattr(
            "app.main.search_related_to_url",
            lambda *a, **k: pytest.fail("search_related_to_url should not be called"),
        )
        monkeypatch.setattr("app.main.fetch_url_content", lambda url: {"url": url, "title": "T", "content": "C"})
        captured = {}

        def _gen(**kwargs):
            captured.update(kwargs)
            return "# 글"

        monkeypatch.setattr("app.main.generate_article_from_url", _gen)
        res = client.post("/api/generate-from-url", json={"url": "https://example.com", "use_web_search": False})
        assert res.status_code == 200
        assert captured["related_search"] is None

    def test_meta(self, monkeypatch):
        from app.writer import ArticleMeta

        monkeypatch.setattr(
            "app.main.generate_article_meta",
            lambda markdown, api_key: ArticleMeta(titles=["제목1", "제목2"], meta_description="설명"),
        )
        res = client.post("/api/meta", json={"markdown": "# 글\n본문"})
        assert res.status_code == 200
        assert res.json() == {"titles": ["제목1", "제목2"], "meta_description": "설명"}

    def test_meta_empty_markdown(self):
        res = client.post("/api/meta", json={"markdown": "  "})
        assert res.status_code == 422


class TestSaveMarkdown:
    """POST /api/save-markdown 제한"""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, tmp_path):
        from app.rate_limit import save_limiter

        save_limiter.requests.clear()
        monkeypatch.setattr("app.main._DOWNLOADS_DIR", str(tmp_path))
        self.dir = tmp_path

    def test_saves_file(self):
        res = client.post("/api/save-markdown", json={"content": "# 글", "filename": "테스트 글"})
        assert res.status_code == 200
        assert (self.dir / res.json()["filename"]).read_text(encoding="utf-8") == "# 글"

    def test_too_long_rejected(self):
        from app.main import _MAX_SAVE_CHARS

        res = client.post("/api/save-markdown", json={"content": "가" * (_MAX_SAVE_CHARS + 1)})
        assert res.status_code == 422

    def test_file_count_cap(self, monkeypatch):
        monkeypatch.setattr("app.main._MAX_SAVED_FILES", 2)
        for i in range(2):
            (self.dir / f"a{i}.md").write_text("x", encoding="utf-8")
        res = client.post("/api/save-markdown", json={"content": "# 글"})
        assert res.status_code == 507

    def test_rate_limited(self):
        from app.rate_limit import save_limiter

        for _ in range(save_limiter.requests_per_minute):
            assert client.post("/api/save-markdown", json={"content": "# 글"}).status_code == 200
        assert client.post("/api/save-markdown", json={"content": "# 글"}).status_code == 429


class TestStreamHistoryAndRevise:
    """스트리밍 생성 → 이력 기록, 글 다듬기"""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        from app.rate_limit import generate_limiter

        generate_limiter.requests.clear()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-1234567890")

    def test_stream_saves_history(self, monkeypatch):
        from app import history

        monkeypatch.setattr("app.main.generate_article_md_stream", lambda **k: iter(["# 제목\n", "본문"]))
        res = client.post("/api/generate/stream", json={"keyword": "테스트 키워드", "use_web_search": False})
        article_id = int(res.headers["x-history-id"])
        item = history.get(article_id)
        assert item["markdown"] == "# 제목\n본문"
        assert item["keyword"] == "테스트 키워드"

    def test_stream_error_without_text_removes_history(self, monkeypatch):
        from app import history

        def _fail(**kwargs):
            raise RuntimeError("실패")
            yield  # pragma: no cover

        monkeypatch.setattr("app.main.generate_article_md_stream", _fail)
        res = client.post("/api/generate/stream", json={"keyword": "테스트", "use_web_search": False})
        assert "[ERROR]" in res.text
        assert history.get(int(res.headers["x-history-id"])) is None

    def test_claude_search_skips_duckduckgo(self, monkeypatch):
        monkeypatch.setattr("app.main.search_web", lambda *a, **k: pytest.fail("DuckDuckGo should not be called"))
        captured = {}

        def _gen(**kwargs):
            captured.update(kwargs)
            return "# 글"

        monkeypatch.setattr("app.main.generate_article_md", _gen)
        res = client.post("/api/generate", json={"keyword": "테스트", "use_claude_search": True})
        assert res.status_code == 200
        assert captured["claude_search"] is True
        assert res.json()["history_id"] is not None

    def test_revise_passes_section(self, monkeypatch):
        captured = {}

        def _revise(**kwargs):
            captured.update(kwargs)
            yield "## 고친 섹션"

        monkeypatch.setattr("app.main.revise_article_stream", _revise)
        res = client.post("/api/revise/stream", json={
            "markdown": "# 글\n## 섹션\n내용", "instruction": "더 짧게", "section": "## 섹션\n내용",
        })
        assert res.text == "## 고친 섹션"
        assert captured["section"] == "## 섹션\n내용"
        assert "x-history-id" not in res.headers

    def test_revise_requires_instruction(self):
        res = client.post("/api/revise/stream", json={"markdown": "# 글", "instruction": "  "})
        assert res.status_code == 422
