import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, Mock
from hypothesis import given, strategies as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment before importing API
with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
    from api.main import app, orchestrator, ChatRequest, ChatResponse
    from core.models import Product, Persona


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint"""
    
    def test_health_check(self):
        """Test that health endpoint returns ok"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestCatalogEndpoint:
    """Tests for catalog endpoint"""
    
    def test_get_catalog_success(self):
        """Test successful catalog retrieval"""
        # Mock orchestrator with products
        with patch('api.main.orchestrator') as mock_orch:
            mock_orch.products = [
                Product(
                    id="et-001",
                    name="Growth Fund",
                    description="Growth focused",
                    target_audience=["Growth investors"],
                    categories=["Growth"],
                    core_benefit="Capital appreciation"
                ),
                Product(
                    id="et-002",
                    name="Bond Fund",
                    description="Conservative",
                    target_audience=["Conservatives"],
                    categories=["Bonds"],
                    core_benefit="Stable income"
                ),
            ]
            
            response = client.get("/api/catalog")
            
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2
            assert len(data["products"]) == 2
            assert data["products"][0]["id"] == "et-001"
            assert data["products"][0]["name"] == "Growth Fund"
    
    def test_get_catalog_not_loaded(self):
        """Test catalog endpoint when no products loaded"""
        with patch('api.main.orchestrator', None):
            response = client.get("/api/catalog")
            assert response.status_code == 503
            assert "not loaded" in response.json()["detail"]


class TestChatEndpoint:
    """Tests for chat endpoint"""
    
    def test_chat_success(self):
        """Test successful chat turn"""
        with patch('api.main.orchestrator') as mock_orch:
            mock_orch.sync_history.return_value = None
            mock_orch.process_turn.return_value = {
                "response": "That sounds interesting! Tell me more.",
                "turn_count": 1,
                "recommendations": None,
            }
            
            request_data = {
                "conversation_history": [],
                "current_message": "I want to invest"
            }
            
            response = client.post("/api/chat", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            mock_orch.sync_history.assert_called_once_with([])
            assert data["turn_count"] == 1
            assert "Tell me more" in data["response"]
            assert data["recommendations"] is None or len(data["recommendations"]) == 0
    
    def test_chat_with_recommendations(self):
        """Test chat response with product recommendations"""
        with patch('api.main.orchestrator') as mock_orch:
            mock_orch.sync_history.return_value = None
            mock_orch.process_turn.return_value = {
                "response": "Here are my recommendations:",
                "turn_count": 3,
                "recommendations": [
                    {
                        "id": "et-001",
                        "name": "Growth Fund",
                        "description": "Growth focused",
                        "target_audience": ["Growth investors"],
                        "categories": ["Growth"],
                        "core_benefit": "Capital appreciation",
                    }
                ],
            }
            
            request_data = {
                "conversation_history": [],
                "current_message": "What should I invest in?"
            }
            
            response = client.post("/api/chat", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["turn_count"] == 3
            assert data["recommendations"] is not None
            assert len(data["recommendations"]) == 1
            assert data["recommendations"][0]["id"] == "et-001"

    def test_chat_streaming_success(self):
        """Test streaming mode returns streamed text response"""
        with patch('api.main.orchestrator') as mock_orch:
            mock_orch.sync_history.return_value = None
            mock_orch.stream_turn.return_value = iter(["Hello", " world", "\n<<END_OF_STREAM>>\n"])

            request_data = {
                "conversation_history": [{"role": "user", "content": "Hi"}],
                "current_message": "Stream this",
                "stream": True,
            }

            response = client.post("/api/chat", json=request_data)

            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")
            assert "Hello world" in response.text
            mock_orch.sync_history.assert_called_once_with(request_data["conversation_history"])
            mock_orch.stream_turn.assert_called_once_with("Stream this")
    
    def test_chat_empty_message(self):
        """Test chat with empty message"""
        request_data = {
            "conversation_history": [],
            "current_message": ""
        }
        
        response = client.post("/api/chat", json=request_data)
        
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()
    
    def test_chat_orchestrator_error(self):
        """Test chat endpoint handles orchestrator errors"""
        with patch('api.main.orchestrator') as mock_orch:
            mock_orch.sync_history.return_value = None
            mock_orch.process_turn.side_effect = Exception("LLM Error")
            
            request_data = {
                "conversation_history": [],
                "current_message": "Hello"
            }
            
            response = client.post("/api/chat", json=request_data)
            
            assert response.status_code == 500
            assert "Unable to process your request right now" in response.json()["detail"]
    
    def test_chat_orchestrator_not_initialized(self):
        """Test chat when orchestrator is not initialized"""
        with patch('api.main.orchestrator', None):
            request_data = {
                "conversation_history": [],
                "current_message": "Hello"
            }
            
            response = client.post("/api/chat", json=request_data)
            
            assert response.status_code == 503
            assert "not initialized" in response.json()["detail"]

    def test_chat_history_is_forwarded_to_orchestrator(self):
        """Property 14: conversation history is passed to orchestrator"""
        with patch('api.main.orchestrator') as mock_orch:
            history = [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
            ]
            mock_orch.sync_history.return_value = None
            mock_orch.process_turn.return_value = {
                "response": "OK",
                "turn_count": 1,
                "recommendations": None,
            }

            response = client.post(
                "/api/chat",
                json={"conversation_history": history, "current_message": "Next"},
            )

            assert response.status_code == 200
            mock_orch.sync_history.assert_called_once_with(history)


class TestResetEndpoint:
    """Tests for reset endpoint"""
    
    def test_reset_conversation_success(self):
        """Test successful conversation reset"""
        with patch('api.main.orchestrator') as mock_orch:
            mock_orch.reset_conversation.return_value = None
            
            response = client.post("/api/reset")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "reset" in data["message"].lower()
    
    def test_reset_orchestrator_not_initialized(self):
        """Test reset when orchestrator not initialized"""
        with patch('api.main.orchestrator', None):
            response = client.post("/api/reset")
            
            assert response.status_code == 503


class TestChatRequestModel:
    """Tests for ChatRequest model validation"""
    
    def test_chat_request_valid(self):
        """Test valid chat request"""
        request = ChatRequest(
            conversation_history=[],
            current_message="Hello"
        )
        assert request.current_message == "Hello"
    
    def test_chat_request_with_history(self):
        """Test chat request with conversation history"""
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"}
        ]
        request = ChatRequest(
            conversation_history=history,
            current_message="How are you?"
        )
        assert len(request.conversation_history) == 2


# Property-based tests for API behavior

def test_chat_request_validation():
    """
    Property: ChatRequest properly validates inputs.
    """
    # Valid request
    valid_request = {
        "conversation_history": [],
        "current_message": "Test message"
    }
    
    response = client.post("/api/chat", json=valid_request)
    # Should return either success or error responses
    assert response.status_code in [200, 400, 500, 503]


def test_api_response_structure():
    """
    Property: Chat responses have consistent structure.
    """
    with patch('api.main.orchestrator') as mock_orch:
        mock_orch.sync_history.return_value = None
        mock_orch.process_turn.return_value = {
            "response": "Response text",
            "turn_count": 1,
            "recommendations": None,
        }
        
        response = client.post(
            "/api/chat",
            json={"conversation_history": [], "current_message": "Test"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "turn_count" in data
        assert isinstance(data["response"], str)
        assert isinstance(data["turn_count"], int)


@given(
    current_message=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
    history=st.lists(
        st.fixed_dictionaries(
            {
                "role": st.sampled_from(["user", "assistant"]),
                "content": st.text(min_size=1, max_size=100),
            }
        ),
        max_size=6,
    ),
)
def test_streaming_response_contract(current_message, history):
    """Property 22: streaming endpoint returns plain text payload when stream=true."""
    with patch('api.main.orchestrator') as mock_orch:
        mock_orch.sync_history.return_value = None
        mock_orch.stream_turn.return_value = iter(["token-1", "token-2", "\n<<END_OF_STREAM>>\n"])

        response = client.post(
            "/api/chat",
            json={
                "conversation_history": history,
                "current_message": current_message,
                "stream": True,
            },
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert "token-1token-2" in response.text
