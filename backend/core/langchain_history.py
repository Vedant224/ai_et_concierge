from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.orm import Session

from core.db_models import ChatMessage, ChatSession
from core.persistence import get_chat_session


class SQLAlchemyChatMessageHistory(BaseChatMessageHistory):
    """LangChain-compatible chat history persisted to chat_messages table."""

    def __init__(self, db: Session, user_id: str, session_id: str):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id

        session = get_chat_session(db, user_id, session_id)
        if not session:
            raise ValueError("Session not found")
        self._session = session

    @property
    def messages(self) -> list[BaseMessage]:
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

        result: list[BaseMessage] = []
        for row in rows:
            role = (row.role or "").lower()
            if role == "assistant":
                result.append(AIMessage(content=row.content))
            elif role == "user":
                result.append(HumanMessage(content=row.content))
        return result

    def add_messages(self, messages: list[BaseMessage]) -> None:
        now = datetime.now(UTC)
        for message in messages:
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                continue

            self.db.add(
                ChatMessage(
                    session_id=self.session_id,
                    role=role,
                    content=str(message.content),
                )
            )

        # Session autoflush is disabled; flush so title derivation can inspect new rows.
        self.db.flush()
        self._session.updated_at = now
        self._update_title_from_first_user_message()
        self.db.commit()

    def clear(self) -> None:
        self.db.query(ChatMessage).filter(
            ChatMessage.session_id == self.session_id
        ).delete()
        self._session.updated_at = datetime.now(UTC)
        self._session.title = "New chat"
        self.db.commit()

    def as_role_content_dicts(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for message in self.messages:
            if isinstance(message, HumanMessage):
                records.append({"role": "user", "content": str(message.content)})
            elif isinstance(message, AIMessage):
                records.append({"role": "assistant", "content": str(message.content)})
        return records

    def _update_title_from_first_user_message(self) -> None:
        if self._session.title != "New chat":
            return

        first_user_message = (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == self.session_id, ChatMessage.role == "user"
            )
            .order_by(ChatMessage.created_at.asc())
            .first()
        )
        if not first_user_message:
            return

        trimmed = first_user_message.content.strip()
        if not trimmed:
            return

        self._session.title = trimmed[:48] + ("..." if len(trimmed) > 48 else "")
