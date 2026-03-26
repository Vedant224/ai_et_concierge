import pytest
from unittest.mock import Mock, patch, MagicMock
from core.models import Persona, Message
from core.persona_extractor import PersonaExtractor


class TestPersonaExtractor:
    """Tests for PersonaExtractor class"""
    
    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM for testing"""
        with patch('core.persona_extractor.ChatGoogleGenerativeAI') as mock:
            yield mock
    
    @pytest.fixture
    def extractor(self, mock_llm):
        """Create PersonaExtractor with mocked LLM"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            return PersonaExtractor(api_key='test-key')
    
    def test_extract_from_sample_conversation(self, extractor):
        """Test persona extraction from sample conversation"""
        # Mock LLM response
        mock_response = Mock()
        mock_response.content = '''{
            "professional_background": "Software Engineer",
            "financial_goals": "Long-term wealth accumulation",
            "risk_appetite": "moderate",
            "interests": ["Technology", "Growth"]
        }'''
        extractor.llm.invoke = Mock(return_value=mock_response)
        
        # Create sample conversation
        conversation = [
            Message(role="user", content="I'm a software engineer looking to invest"),
            Message(role="assistant", content="Great! What are your financial goals?"),
            Message(role="user", content="I want to build long-term wealth"),
        ]
        
        # Extract persona
        persona = extractor.extract(conversation)
        
        # Verify extraction
        assert persona.professional_background == "Software Engineer"
        assert persona.financial_goals == "Long-term wealth accumulation"
        assert persona.risk_appetite == "moderate"
        assert "Technology" in persona.interests
        assert "Growth" in persona.interests
    
    def test_extract_with_incomplete_data(self, extractor):
        """Test extraction with incomplete persona data"""
        mock_response = Mock()
        mock_response.content = '''{
            "professional_background": "Teacher",
            "financial_goals": null,
            "risk_appetite": null,
            "interests": ["Education", "Sustainable"]
        }'''
        extractor.llm.invoke = Mock(return_value=mock_response)
        
        conversation = [
            Message(role="user", content="I'm a teacher interested in ESG investing"),
        ]
        
        persona = extractor.extract(conversation)
        
        assert persona.professional_background == "Teacher"
        assert persona.financial_goals is None
        assert persona.risk_appetite is None
        assert len(persona.interests) > 0
    
    def test_extract_with_invalid_json_response(self, extractor):
        """Test handling of invalid JSON from LLM"""
        mock_response = Mock()
        mock_response.content = "This is not valid JSON"
        extractor.llm.invoke = Mock(return_value=mock_response)
        
        conversation = [Message(role="user", content="test")]
        
        # Should return empty persona on error
        persona = extractor.extract(conversation)
        assert isinstance(persona, Persona)
    
    def test_update_persona_with_new_information(self, extractor):
        """Test updating persona with new information"""
        # Set initial persona
        extractor.current_persona = Persona(
            professional_background="Engineer",
            interests=["Technology"]
        )
        
        # Update with new information
        new_info = Persona(
            risk_appetite="aggressive",
            interests=["Growth", "Dividend"]
        )
        
        updated = extractor.update(new_info)
        
        # Old data should be preserved
        assert updated.professional_background == "Engineer"
        # New data should be added
        assert updated.risk_appetite == "aggressive"
        # Interests should be merged and deduplicated
        assert "Technology" in updated.interests
        assert "Growth" in updated.interests
        assert "Dividend" in updated.interests
    
    def test_update_persona_overwrites_existing_field(self, extractor):
        """Test that new information overwrites existing fields"""
        extractor.current_persona = Persona(
            risk_appetite="conservative",
            professional_background="Teacher"
        )
        
        # Update with conflicting information
        new_info = Persona(
            risk_appetite="aggressive"
        )
        
        updated = extractor.update(new_info)
        
        assert updated.risk_appetite == "aggressive"
        assert updated.professional_background == "Teacher"
    
    def test_add_message_and_get_history(self, extractor):
        """Test message tracking"""
        msg1 = Message(role="user", content="Hello")
        msg2 = Message(role="assistant", content="Hi there")
        
        extractor.add_message(msg1)
        extractor.add_message(msg2)
        
        history = extractor.get_conversation_history()
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"
    
    def test_get_current_persona(self, extractor):
        """Test getting current persona"""
        test_persona = Persona(
            professional_background="Analyst",
            risk_appetite="moderate"
        )
        extractor.current_persona = test_persona
        
        current = extractor.get_current_persona()
        assert current == test_persona
        assert current.professional_background == "Analyst"
    
    def test_extract_empty_conversation(self, extractor):
        """Test extraction from empty conversation"""
        persona = extractor.extract([])
        
        # Should return empty persona
        assert isinstance(persona, Persona)
        assert persona.professional_background is None
        assert persona.financial_goals is None
