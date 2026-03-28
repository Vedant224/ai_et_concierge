import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from langchain_core.messages import AIMessage, HumanMessage

from core.db import get_db
from core.db_models import User
from core.langchain_history import SQLAlchemyChatMessageHistory
from core.orchestrator import ConversationOrchestrator
from core.persistence import (
    archive_chat_session,
    create_chat_session,
    create_user,
    get_chat_session,
    get_user_by_email,
    get_user_by_id,
    init_db,
    list_chat_messages,
    list_chat_sessions,
    rename_chat_session,
    upsert_persona_profile,
)
from core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Ensure backend exceptions from orchestrator are visible in local terminal logs.
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

bearer_optional = HTTPBearer(auto_error=False)
bearer_required = HTTPBearer(auto_error=True)


def _resolve_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _resolve_cors_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:3000"]


def _resolve_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


# Pydantic models for API
class ChatRequest(BaseModel):
    """Request model for chat endpoint"""

    conversation_history: List[dict[str, Any]] = Field(
        default_factory=list, description="Previous messages in the conversation"
    )
    current_message: str = Field(..., description="User's current message")
    session_id: Optional[str] = Field(
        default=None, description="Authenticated chat session identifier"
    )
    stream: bool = Field(
        default=False, description="Whether to stream the assistant response"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ],
                "current_message": "I'm interested in investments",
                "stream": False,
            }
        }
    }


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""

    response: str = Field(..., description="Assistant's response")
    turn_count: int = Field(..., description="Current conversation turn number")
    recommendations: Optional[List[dict[str, Any]]] = Field(
        None, description="Product recommendations if available"
    )
    session_id: Optional[str] = Field(
        default=None, description="Session identifier when authenticated"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "response": "That sounds like a great goal! Tell me more...",
                "turn_count": 1,
                "recommendations": None,
            }
        }
    }


class CatalogResponse(BaseModel):
    """Response model for catalog endpoint"""

    products: List[dict[str, Any]] = Field(..., description="List of ET products")
    count: int = Field(..., description="Number of products")


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class SessionSummaryResponse(BaseModel):
    id: str
    title: str
    updated_at: datetime
    created_at: datetime


class SessionMessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    messages: list[SessionMessageResponse]


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# Initialize FastAPI app
app = FastAPI(
    title="ET User Profiling Agent API",
    description="Conversation-based investment profiling agent using Gemini and LangChain",
    version="1.0.0",
    lifespan=lifespan,
)


def _resolve_current_user(
    credentials: Optional[HTTPAuthorizationCredentials], db: Session, required: bool
) -> Optional[User]:
    if credentials is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication token",
            )
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token payload",
        )

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found for access token",
        )
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    return _resolve_current_user(credentials, db, required=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_required),
    db: Session = Depends(get_db),
) -> User:
    user = _resolve_current_user(credentials, db, required=True)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    return user


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator (global instance for simplicity)
try:
    orchestrator = ConversationOrchestrator(
        api_key=_resolve_api_key(),
        model=_resolve_model_name(),
        catalog_path=os.getenv("CATALOG_PATH"),
    )
except Exception as e:
    print(f"Warning: Failed to initialize orchestrator: {str(e)}")
    orchestrator = None


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "API is running"}


@app.post("/api/auth/signup", response_model=AuthTokenResponse)
async def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        user = create_user(
            db,
            email=email,
            password_hash=hash_password(payload.password),
            full_name=(payload.full_name or "").strip() or None,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered")

    token = create_access_token(user.id)
    return AuthTokenResponse(access_token=token, user_id=user.id, email=user.email)


@app.post("/api/auth/login", response_model=AuthTokenResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = get_user_by_email(db, email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id)
    return AuthTokenResponse(access_token=token, user_id=user.id, email=user.email)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Process a conversation turn with the user.

    Args:
        request: ChatRequest containing conversation history and current message

    Returns:
        ChatResponse with assistant response and metadata
    """
    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not initialized. API key may not be set.",
        )

    # Validate request
    if not request.current_message or not request.current_message.strip():
        raise HTTPException(status_code=400, detail="current_message cannot be empty")

    active_session = None
    history_store: Optional[SQLAlchemyChatMessageHistory] = None
    if current_user:
        if request.session_id:
            active_session = get_chat_session(db, current_user.id, request.session_id)
            if not active_session:
                raise HTTPException(status_code=404, detail="Session not found")
        else:
            active_session = create_chat_session(db, current_user.id)

        try:
            history_store = SQLAlchemyChatMessageHistory(
                db=db,
                user_id=current_user.id,
                session_id=active_session.id,
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="Session not found")

    try:
        if history_store:
            orchestrator.sync_history(history_store.as_role_content_dicts())
        else:
            orchestrator.sync_history(request.conversation_history)

        if request.stream:
            persisted_chunks: list[str] = []

            def token_stream():
                for token in orchestrator.stream_turn(request.current_message):
                    if "END_OF_STREAM" not in token:
                        persisted_chunks.append(token)
                    yield token

                if current_user and active_session and history_store:
                    assistant_text = "".join(persisted_chunks).strip()
                    history_store.add_messages(
                        [
                            HumanMessage(content=request.current_message),
                            AIMessage(content=assistant_text),
                        ]
                    )
                    upsert_persona_profile(
                        db,
                        user_id=current_user.id,
                        profile_json=orchestrator.get_current_persona().model_dump(),
                    )

            headers = (
                {"X-Session-Id": active_session.id}
                if current_user and active_session
                else None
            )
            return StreamingResponse(
                token_stream(), media_type="text/plain; charset=utf-8", headers=headers
            )

        payload = orchestrator.process_turn(request.current_message)
        if current_user and active_session and history_store:
            history_store.add_messages(
                [
                    HumanMessage(content=request.current_message),
                    AIMessage(content=payload["response"]),
                ]
            )
            upsert_persona_profile(
                db,
                user_id=current_user.id,
                profile_json=orchestrator.get_current_persona().model_dump(),
            )
            payload["session_id"] = active_session.id

        return ChatResponse(**payload)

    except Exception:
        logger.exception("Chat processing failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to process your request right now. Please try again.",
        )


@app.get("/api/history/sessions", response_model=list[SessionSummaryResponse])
async def history_sessions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sessions = list_chat_sessions(db, current_user.id)
    return [
        SessionSummaryResponse(
            id=session.id,
            title=session.title,
            updated_at=session.updated_at,
            created_at=session.created_at,
        )
        for session in sessions
    ]


@app.get("/api/history/sessions/{session_id}", response_model=SessionDetailResponse)
async def history_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_chat_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = list_chat_messages(db, session.id)
    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        messages=[
            SessionMessageResponse(
                role=message.role,
                content=message.content,
                timestamp=message.created_at,
            )
            for message in messages
        ],
    )


@app.patch("/api/history/sessions/{session_id}", response_model=SessionSummaryResponse)
async def history_session_rename(
    session_id: str,
    payload: RenameSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_chat_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    updated = rename_chat_session(db, session, payload.title)
    return SessionSummaryResponse(
        id=updated.id,
        title=updated.title,
        updated_at=updated.updated_at,
        created_at=updated.created_at,
    )


@app.delete("/api/history/sessions/{session_id}")
async def history_session_delete(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_chat_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    archive_chat_session(db, session)
    return {"status": "success", "message": "Session archived"}


@app.get("/api/catalog", response_model=CatalogResponse)
async def get_catalog():
    """
    Get the ET product catalog.

    Returns:
        CatalogResponse with list of products
    """
    if not orchestrator or not orchestrator.products:
        raise HTTPException(status_code=503, detail="Catalog not loaded")

    try:
        products_data = [
            {
                "id": prod.id,
                "name": prod.name,
                "description": prod.description,
                "target_audience": prod.target_audience,
                "categories": prod.categories,
                "core_benefit": prod.core_benefit,
                "product_id": prod.product_id,
                "product_name": prod.product_name,
                "includes": prod.includes,
                "risk_profile": prod.risk_profile,
                "trigger_keywords": prod.trigger_keywords,
                "discovery_weight": prod.discovery_weight,
                "cta_text": prod.cta_text,
                "url": prod.url,
            }
            for prod in orchestrator.products
        ]

        return CatalogResponse(products=products_data, count=len(products_data))

    except Exception:
        logger.exception("Catalog retrieval failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve catalog right now. Please try again.",
        )


@app.post("/api/reset")
async def reset_conversation():
    """
    Reset the conversation state (for starting a new conversation).

    Returns:
        Status message
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        orchestrator.reset_conversation()
        return {"status": "success", "message": "Conversation reset"}
    except Exception:
        logger.exception("Conversation reset failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to reset conversation right now. Please try again.",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
