import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, List, Optional
import os
from dotenv import load_dotenv

from core.orchestrator import ConversationOrchestrator


logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


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
        default_factory=list,
        description="Previous messages in the conversation"
    )
    current_message: str = Field(..., description="User's current message")
    stream: bool = Field(default=False, description="Whether to stream the assistant response")
    
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
        None,
        description="Product recommendations if available"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "response": "That sounds like a great goal! Tell me more...",
                "turn_count": 1,
                "recommendations": None
            }
        }
    }


class CatalogResponse(BaseModel):
    """Response model for catalog endpoint"""
    products: List[dict[str, Any]] = Field(..., description="List of ET products")
    count: int = Field(..., description="Number of products")


# Initialize FastAPI app
app = FastAPI(
    title="ET User Profiling Agent API",
    description="Conversation-based investment profiling agent using Gemini and LangChain",
    version="1.0.0"
)

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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
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
            detail="Orchestrator not initialized. API key may not be set."
        )
    
    # Validate request
    if not request.current_message or not request.current_message.strip():
        raise HTTPException(
            status_code=400,
            detail="current_message cannot be empty"
        )
    
    try:
        orchestrator.sync_history(request.conversation_history)

        if request.stream:
            def token_stream():
                for token in orchestrator.stream_turn(request.current_message):
                    yield token

            return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")

        payload = orchestrator.process_turn(request.current_message)
        return ChatResponse(**payload)
    
    except Exception:
        logger.exception("Chat processing failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to process your request right now. Please try again."
        )


@app.get("/api/catalog", response_model=CatalogResponse)
async def get_catalog():
    """
    Get the ET product catalog.
    
    Returns:
        CatalogResponse with list of products
    """
    if not orchestrator or not orchestrator.products:
        raise HTTPException(
            status_code=503,
            detail="Catalog not loaded"
        )
    
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
        
        return CatalogResponse(
            products=products_data,
            count=len(products_data)
        )
    
    except Exception:
        logger.exception("Catalog retrieval failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve catalog right now. Please try again."
        )


@app.post("/api/reset")
async def reset_conversation():
    """
    Reset the conversation state (for starting a new conversation).
    
    Returns:
        Status message
    """
    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not initialized"
        )
    
    try:
        orchestrator.reset_conversation()
        return {"status": "success", "message": "Conversation reset"}
    except Exception:
        logger.exception("Conversation reset failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to reset conversation right now. Please try again."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
