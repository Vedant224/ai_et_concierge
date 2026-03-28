import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import main as api_main
from core.db import Base
from core.db_models import PersonaProfile
from core.security import decode_access_token


class _PersonaStub:
    def model_dump(self):
        return {
            "risk_tolerance": "moderate",
            "investment_horizon": "long_term",
        }


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test_auth_history.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    original_orchestrator = api_main.orchestrator
    api_main.init_db = lambda: None
    api_main.app.dependency_overrides[api_main.get_db] = override_get_db
    api_main.orchestrator = MagicMock()
    api_main.orchestrator.sync_history.return_value = None
    api_main.orchestrator.process_turn.return_value = {
        "response": "Here is a personalized suggestion.",
        "turn_count": 1,
        "recommendations": None,
    }
    api_main.orchestrator.get_current_persona.return_value = _PersonaStub()

    with TestClient(api_main.app) as test_client:
        yield test_client, TestingSessionLocal

    api_main.orchestrator = original_orchestrator
    api_main.app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup_and_login(
    client: TestClient, email: str = "demo@example.com"
) -> tuple[str, str]:
    signup_payload = {
        "email": email,
        "password": "DemoPass123!",
        "full_name": "Demo User",
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 200

    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "DemoPass123!"},
    )
    assert login_response.status_code == 200
    login_json = login_response.json()
    return login_json["access_token"], login_json["user_id"]


def test_signup_and_login_return_valid_access_token(client):
    test_client, _ = client
    token, user_id = _signup_and_login(test_client)

    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "access"


def test_history_requires_authentication(client):
    test_client, _ = client

    response = test_client.get("/api/history/sessions")
    assert response.status_code == 401


def test_authenticated_chat_creates_session_and_persists_messages(client):
    test_client, SessionLocal = client
    token, _ = _signup_and_login(test_client)

    chat_response = test_client.post(
        "/api/chat",
        json={"conversation_history": [], "current_message": "Help me invest"},
        headers=_auth_headers(token),
    )
    assert chat_response.status_code == 200
    chat_json = chat_response.json()
    assert chat_json["session_id"]

    list_response = test_client.get(
        "/api/history/sessions", headers=_auth_headers(token)
    )
    assert list_response.status_code == 200
    sessions = list_response.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == chat_json["session_id"]

    detail_response = test_client.get(
        f"/api/history/sessions/{chat_json['session_id']}",
        headers=_auth_headers(token),
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content"] == "Help me invest"
    assert detail["messages"][1]["role"] == "assistant"

    db = SessionLocal()
    try:
        profile = db.query(PersonaProfile).first()
        assert profile is not None
        assert profile.profile_json["risk_tolerance"] == "moderate"
    finally:
        db.close()


def test_chat_with_existing_session_uses_db_history_not_request_history(client):
    test_client, _ = client
    token, _ = _signup_and_login(test_client, email="history.user@example.com")

    first_chat = test_client.post(
        "/api/chat",
        json={"conversation_history": [], "current_message": "first message"},
        headers=_auth_headers(token),
    )
    assert first_chat.status_code == 200
    session_id = first_chat.json()["session_id"]

    api_main.orchestrator.sync_history.reset_mock()
    second_chat = test_client.post(
        "/api/chat",
        json={
            "conversation_history": [{"role": "user", "content": "SHOULD_NOT_BE_USED"}],
            "current_message": "second message",
            "session_id": session_id,
        },
        headers=_auth_headers(token),
    )
    assert second_chat.status_code == 200

    api_main.orchestrator.sync_history.assert_called_once()
    synced_history = api_main.orchestrator.sync_history.call_args[0][0]
    assert len(synced_history) == 2
    assert synced_history[0]["content"] == "first message"
    assert synced_history[1]["role"] == "assistant"


def test_history_rename_and_archive_flow(client):
    test_client, _ = client
    token, _ = _signup_and_login(test_client, email="rename.user@example.com")

    chat_response = test_client.post(
        "/api/chat",
        json={"conversation_history": [], "current_message": "Need a balanced plan"},
        headers=_auth_headers(token),
    )
    session_id = chat_response.json()["session_id"]

    rename_response = test_client.patch(
        f"/api/history/sessions/{session_id}",
        json={"title": "Balanced strategy"},
        headers=_auth_headers(token),
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Balanced strategy"

    delete_response = test_client.delete(
        f"/api/history/sessions/{session_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 200

    list_response = test_client.get(
        "/api/history/sessions", headers=_auth_headers(token)
    )
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_history_list_payload_is_minimized(client):
    test_client, _ = client
    token, _ = _signup_and_login(test_client, email="minimal.user@example.com")

    test_client.post(
        "/api/chat",
        json={"conversation_history": [], "current_message": "Sensitive detail text"},
        headers=_auth_headers(token),
    )

    list_response = test_client.get(
        "/api/history/sessions", headers=_auth_headers(token)
    )
    assert list_response.status_code == 200
    sessions = list_response.json()
    assert len(sessions) == 1
    assert set(sessions[0].keys()) == {"id", "title", "updated_at", "created_at"}
    assert "messages" not in sessions[0]
    assert "content" not in sessions[0]


def test_cross_user_session_access_is_blocked(client):
    test_client, _ = client
    token_a, _ = _signup_and_login(test_client, email="owner.user@example.com")
    token_b, _ = _signup_and_login(test_client, email="other.user@example.com")

    session_response = test_client.post(
        "/api/chat",
        json={"conversation_history": [], "current_message": "Owner private session"},
        headers=_auth_headers(token_a),
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    detail_response = test_client.get(
        f"/api/history/sessions/{session_id}", headers=_auth_headers(token_b)
    )
    assert detail_response.status_code == 404

    rename_response = test_client.patch(
        f"/api/history/sessions/{session_id}",
        json={"title": "Hacked title"},
        headers=_auth_headers(token_b),
    )
    assert rename_response.status_code == 404

    delete_response = test_client.delete(
        f"/api/history/sessions/{session_id}", headers=_auth_headers(token_b)
    )
    assert delete_response.status_code == 404
