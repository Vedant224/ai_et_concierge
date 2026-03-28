from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from core.db import Base, engine
from core.db_models import ChatMessage, ChatSession, PersonaProfile, User


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def create_user(db: Session, email: str, password_hash: str, full_name: Optional[str]) -> User:
    user = User(email=email, password_hash=password_hash, full_name=full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def create_chat_session(db: Session, user_id: str, title: str = "New chat") -> ChatSession:
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_chat_session(db: Session, user_id: str, session_id: str) -> Optional[ChatSession]:
    return (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id, ChatSession.archived.is_(False))
        .first()
    )


def list_chat_sessions(db: Session, user_id: str) -> list[ChatSession]:
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id, ChatSession.archived.is_(False))
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


def rename_chat_session(db: Session, session: ChatSession, title: str) -> ChatSession:
    session.title = title.strip()[:200] or session.title
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session


def archive_chat_session(db: Session, session: ChatSession) -> None:
    session.archived = True
    session.updated_at = datetime.now(UTC)
    db.commit()


def list_chat_messages(db: Session, session_id: str) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


def save_chat_turn(db: Session, session: ChatSession, user_message: str, assistant_message: str) -> None:
    db.add(ChatMessage(session_id=session.id, role="user", content=user_message))
    db.add(ChatMessage(session_id=session.id, role="assistant", content=assistant_message))
    session.updated_at = datetime.now(UTC)

    if session.title == "New chat":
        trimmed = user_message.strip()
        if trimmed:
            session.title = trimmed[:48] + ("..." if len(trimmed) > 48 else "")

    db.commit()


def upsert_persona_profile(db: Session, user_id: str, profile_json: dict) -> None:
    existing = db.query(PersonaProfile).filter(PersonaProfile.user_id == user_id).first()
    if existing:
        existing.profile_json = profile_json
        existing.updated_at = datetime.now(UTC)
    else:
        db.add(PersonaProfile(user_id=user_id, profile_json=profile_json))
    db.commit()
