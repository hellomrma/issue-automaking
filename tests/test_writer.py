"""글 생성 로직 테스트 (Claude API는 모킹)"""
from types import SimpleNamespace

import pytest

from app import writer


class _FakeStream:
    def __init__(self, chunks, stop_reason):
        self.text_stream = iter(chunks)
        self._stop_reason = stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop_reason)


@pytest.fixture
def fake_claude(monkeypatch):
    """Anthropic 클라이언트를 가짜로 대체하고, stream 호출 인자를 기록"""
    calls = []

    def install(chunks, stop_reason="end_turn"):
        def _stream(**kwargs):
            calls.append(kwargs)
            return _FakeStream(chunks, stop_reason)

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=_stream)))
        monkeypatch.setattr(writer, "Anthropic", lambda api_key=None: client)
        return calls

    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    return install


class TestStreamText:
    def test_streams_chunks(self, fake_claude):
        fake_claude(["# 제목", "\n본문"])
        assert "".join(writer.generate_article_md_stream("키워드")) == "# 제목\n본문"

    def test_truncation_notice(self, fake_claude):
        """max_tokens 도달 시 잘림 안내 추가"""
        fake_claude(["# 제목"], stop_reason="max_tokens")
        text = "".join(writer.generate_article_md_stream("키워드"))
        assert text.endswith(writer.TRUNCATED_NOTICE)

    def test_refusal_raises(self, fake_claude):
        fake_claude([], stop_reason="refusal")
        with pytest.raises(RuntimeError, match="거절"):
            list(writer.generate_article_md_stream("키워드"))

    def test_default_model_uses_fallbacks(self, fake_claude):
        calls = fake_claude(["x"])
        list(writer.generate_article_md_stream("키워드"))
        assert calls[0]["model"] == writer.DEFAULT_MODEL
        assert calls[0]["fallbacks"] == "default"
        assert "temperature" not in calls[0]

    def test_other_model_without_fallbacks(self, fake_claude, monkeypatch):
        calls = fake_claude(["x"])
        monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-5-5")
        list(writer.generate_article_md_stream("키워드"))
        assert calls[0]["model"] == "claude-haiku-5-5"
        assert "fallbacks" not in calls[0]

    def test_non_stream_cleans_code_fence(self, fake_claude):
        fake_claude(["```markdown\n# 제목\n본문\n```"])
        assert writer.generate_article_md("키워드") == "# 제목\n본문"


class TestPrompts:
    def test_long_length_matches_ui(self):
        """UI의 '길게 (1500~2000자)'와 프롬프트 분량 일치"""
        _, user = writer._build_prompts("키워드", length="long")
        assert "1,500~2,000자" in user

    def test_optional_blocks(self):
        _, user = writer._build_prompts("키워드", web_context="검색결과", guide="초보자용", reference_content="참고본문")
        assert "검색결과" in user and "초보자용" in user and "참고본문" in user

    def test_optional_blocks_omitted(self):
        _, user = writer._build_prompts("키워드", web_context="  ", guide=None)
        assert "글 작성 가이드" not in user
        assert "웹 검색 결과" not in user

    def test_url_prompt_includes_content(self):
        _, user = writer._build_url_prompts({"url": "https://a.com", "title": "T", "content": "원문"}, guide="톤")
        assert "원문" in user and "새로운 관점" in user and "톤" in user


class TestSourcesAndSearch:
    def test_sources_only_with_context(self):
        _, without = writer._build_prompts("키워드")
        _, with_ctx = writer._build_prompts("키워드", web_context="검색결과")
        assert "참고한 자료" not in without
        assert "참고한 자료" in with_ctx

    def test_sources_can_be_disabled(self):
        _, user = writer._build_prompts("키워드", web_context="검색결과", include_sources=False)
        assert "참고한 자료" not in user

    def test_url_prompt_always_has_sources(self):
        _, user = writer._build_url_prompts({"url": "https://a.com", "content": "원문"})
        assert "참고한 자료" in user

    def test_claude_search_adds_tool(self, fake_claude):
        calls = fake_claude(["x"])
        list(writer.generate_article_md_stream("키워드", claude_search=True))
        assert calls[0]["tools"][0]["type"] == "web_search_20260209"
        assert "web_search 도구" in calls[0]["messages"][0]["content"]

    def test_pause_turn_resumes(self, monkeypatch):
        """pause_turn이면 이전 응답을 assistant로 붙여 이어서 요청"""
        calls = []
        results = [("앞부분", "pause_turn"), ("뒷부분", "end_turn")]

        def _stream(**kwargs):
            calls.append(kwargs)
            text, stop = results[len(calls) - 1]
            s = _FakeStream([text], stop)
            s.get_final_message = lambda: SimpleNamespace(stop_reason=stop, content=[{"type": "text", "text": text}])
            return s

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=_stream)))
        monkeypatch.setattr(writer, "Anthropic", lambda api_key=None: client)

        text = "".join(writer.generate_article_md_stream("키워드", claude_search=True))
        assert text == "앞부분뒷부분"
        assert calls[1]["messages"][1]["role"] == "assistant"


class TestRevise:
    def test_section_prompt(self, fake_claude):
        calls = fake_claude(["## 새 섹션"])
        out = "".join(writer.revise_article_stream("# 글\n## 섹션\n내용", "더 짧게", section="## 섹션\n내용"))
        assert out == "## 새 섹션"
        prompt = calls[0]["messages"][0]["content"]
        assert "[고칠 부분]" in prompt and "더 짧게" in prompt

    def test_whole_prompt(self, fake_claude):
        calls = fake_claude(["# 글"])
        list(writer.revise_article_stream("# 글", "톤을 밝게"))
        assert "[고칠 부분]" not in calls[0]["messages"][0]["content"]
