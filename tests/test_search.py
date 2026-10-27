"""URL 콘텐츠 수집 테스트 (SSRF 리다이렉트 차단, 크기·타입 제한)"""
from unittest.mock import MagicMock

import pytest

from app import search


def _make_response(status=200, headers=None, body=b"", redirect=False):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.is_redirect = redirect
    resp.encoding = "utf-8"
    resp.iter_content.return_value = [body[i : i + 65536] for i in range(0, len(body), 65536)] or [b""]
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


@pytest.fixture
def fake_get(monkeypatch):
    """requests.get 을 가짜 응답 목록으로 대체"""
    calls = []

    def install(*responses):
        queue = list(responses)

        def _get(url, **kwargs):
            calls.append((url, kwargs))
            return queue.pop(0)

        monkeypatch.setattr(search.requests, "get", _get)
        return calls

    return install


class TestFetchUrlContent:
    def test_redirect_to_internal_ip_blocked(self, fake_get):
        """공개 URL이 내부 IP로 리다이렉트하면 거부"""
        calls = fake_get(
            _make_response(status=302, headers={"location": "http://127.0.0.1/admin"}, redirect=True),
        )
        with pytest.raises(ValueError, match="로컬호스트"):
            search.fetch_url_content("http://8.8.8.8/start")
        assert len(calls) == 1  # 내부 주소로는 요청하지 않음
        assert calls[0][1]["allow_redirects"] is False

    def test_follows_safe_redirect(self, fake_get):
        """안전한 리다이렉트는 따라가서 본문 추출"""
        html = "<html><head><title>제목</title></head><body><article>본문 내용</article></body></html>"
        calls = fake_get(
            _make_response(status=301, headers={"location": "/next"}, redirect=True),
            _make_response(headers={"content-type": "text/html; charset=utf-8"}, body=html.encode("utf-8")),
        )
        result = search.fetch_url_content("http://8.8.8.8/start")
        assert calls[1][0] == "http://8.8.8.8/next"
        assert result["title"] == "제목"
        assert "본문 내용" in result["content"]

    def test_too_many_redirects(self, fake_get):
        """리다이렉트 횟수 제한"""
        fake_get(*[
            _make_response(status=302, headers={"location": "/loop"}, redirect=True)
            for _ in range(search._MAX_REDIRECTS + 1)
        ])
        with pytest.raises(ValueError, match="리다이렉트"):
            search.fetch_url_content("http://8.8.8.8/loop")

    def test_non_html_rejected(self, fake_get):
        """HTML이 아닌 응답은 거부"""
        fake_get(_make_response(headers={"content-type": "application/pdf"}, body=b"%PDF"))
        with pytest.raises(ValueError, match="HTML"):
            search.fetch_url_content("http://8.8.8.8/file.pdf")

    def test_download_size_capped(self, fake_get, monkeypatch):
        """응답 크기 상한 이후는 읽지 않음"""
        monkeypatch.setattr(search, "_MAX_DOWNLOAD_BYTES", 100)
        resp = _make_response(headers={"content-type": "text/html"})
        resp.iter_content.return_value = iter([b"a" * 80, b"b" * 80, b"c" * 80])
        fake_get(resp)
        raw, _ = search._download_html("http://8.8.8.8/", {}, 5)
        assert len(raw) == 100
