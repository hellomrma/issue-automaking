"""생성 이력 테스트"""
from fastapi.testclient import TestClient

from app import history
from app.main import app

client = TestClient(app)


class TestHistoryStore:
    def test_create_get_update_delete(self):
        article_id = history.create(mode="keyword", keyword="연말정산", markdown="# 첫 제목\n본문")
        item = history.get(article_id)
        assert item["title"] == "첫 제목"
        assert item["keyword"] == "연말정산"

        assert history.update_markdown(article_id, "# 바뀐 제목\n새 본문")
        assert history.get(article_id)["title"] == "바뀐 제목"

        assert history.delete(article_id)
        assert history.get(article_id) is None
        assert not history.delete(article_id)

    def test_list_excludes_empty_and_searches(self):
        history.create(mode="keyword", keyword="비트코인", markdown="# 비트코인 전망\n...")
        history.create(mode="keyword", keyword="금 투자", markdown="# 금 시세\n...")
        history.create(mode="keyword", keyword="작성 중", markdown="")  # 생성 중인 빈 글은 제외

        items = history.list_recent()
        assert [i["keyword"] for i in items] == ["금 투자", "비트코인"]
        assert "markdown" not in items[0]
        assert [i["keyword"] for i in history.list_recent("비트")] == ["비트코인"]

    def test_find_by_keyword_ignores_spaces_and_case(self):
        history.create(mode="keyword", keyword="Claude AI", markdown="# 글")
        assert len(history.find_by_keyword("claudeai")) == 1
        assert history.find_by_keyword("다른 키워드") == []


class TestHistoryAPI:
    def test_crud(self):
        article_id = history.create(mode="url", source_url="https://a.com", markdown="# 제목\n본문")

        assert client.get("/api/history").json()["items"][0]["id"] == article_id
        assert client.get(f"/api/history/{article_id}").json()["markdown"] == "# 제목\n본문"

        res = client.put(f"/api/history/{article_id}", json={"markdown": "# 새 제목"})
        assert res.status_code == 200
        assert history.get(article_id)["title"] == "새 제목"

        assert client.delete(f"/api/history/{article_id}").status_code == 200
        assert client.get(f"/api/history/{article_id}").status_code == 404

    def test_check_duplicates(self):
        history.create(mode="keyword", keyword="연말정산 간소화", markdown="# 글")
        res = client.get("/api/history/check", params={"keyword": "연말정산간소화"})
        assert len(res.json()["items"]) == 1

    def test_missing(self):
        assert client.put("/api/history/999", json={"markdown": "x"}).status_code == 404
        assert client.delete("/api/history/999").status_code == 404
