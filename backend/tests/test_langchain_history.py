import os
import sys

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import Base
from core.langchain_history import SQLAlchemyChatMessageHistory
from core.persistence import create_chat_session, create_user, get_chat_session


def _build_db(tmp_path):
    db_path = tmp_path / "test_langchain_history.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def test_history_add_and_read_round_trip(tmp_path):
    engine, SessionLocal = _build_db(tmp_path)
    db = SessionLocal()
    try:
        user = create_user(db, "history@test.com", "hash", "History User")
        session = create_chat_session(db, user.id)

        history = SQLAlchemyChatMessageHistory(db, user.id, session.id)
        history.add_messages(
            [
                HumanMessage(content="hello"),
                AIMessage(content="hi there"),
                HumanMessage(content="show options"),
            ]
        )

        messages = history.messages
        assert len(messages) == 3
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert str(messages[2].content) == "show options"

        dict_history = history.as_role_content_dicts()
        assert dict_history == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "show options"},
        ]
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_history_enforces_user_session_ownership(tmp_path):
    engine, SessionLocal = _build_db(tmp_path)
    db = SessionLocal()
    try:
        user_a = create_user(db, "owner@test.com", "hash", "Owner")
        user_b = create_user(db, "other@test.com", "hash", "Other")
        session = create_chat_session(db, user_a.id)

        try:
            SQLAlchemyChatMessageHistory(db, user_b.id, session.id)
            raised = False
        except ValueError:
            raised = True

        assert raised is True
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_history_clear_removes_messages_and_resets_title(tmp_path):
    engine, SessionLocal = _build_db(tmp_path)
    db = SessionLocal()
    try:
        user = create_user(db, "clear@test.com", "hash", "Clear User")
        session = create_chat_session(db, user.id)

        history = SQLAlchemyChatMessageHistory(db, user.id, session.id)
        history.add_messages(
            [HumanMessage(content="A very long first prompt to make a title")]
        )
        refreshed_session = get_chat_session(db, user.id, session.id)
        assert refreshed_session is not None
        assert refreshed_session.title != "New chat"

        history.clear()

        refreshed = SQLAlchemyChatMessageHistory(db, user.id, session.id)
        assert refreshed.messages == []
        refreshed_session = get_chat_session(db, user.id, session.id)
        assert refreshed_session is not None
        assert refreshed_session.title == "New chat"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
