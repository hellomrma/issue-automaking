"""공통 테스트 설정"""
import pytest

from app import history


@pytest.fixture(autouse=True)
def _isolated_history_db(monkeypatch, tmp_path):
    """테스트마다 임시 이력 DB 사용 (실제 data/history.db 보호)"""
    monkeypatch.setattr(history, "DB_PATH", str(tmp_path / "history.db"))
