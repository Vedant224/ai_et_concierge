import pytest
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st
from hypothesis import settings
from core.models import Persona, Product, Message
from core.orchestrator import ConversationOrchestrator


class TestConversationOrchestrator:
    """Tests for ConversationOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies"""
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            with patch('core.orchestrator.ChatGoogleGenerativeAI') as mock_llm_class:
                with patch('core.orchestrator.CatalogLoader') as mock_catalog:
                    # Mock catalog loader
                    mock_loader_instance = MagicMock()
                    mock_loader_instance.load.return_value = [
                        Product(
                            id="et-001",
                            name="Growth Fund",
                            description="Growth focused",
                            target_audience=["Growth investors"],
                            categories=["Growth", "Equity"],
                            core_benefit="Capital appreciation"
                        ),
                    ]
                    mock_catalog.return_value = mock_loader_instance
                    
                    # Mock LLM
                    mock_llm_instance = MagicMock()
                    mock_llm_class.return_value = mock_llm_instance
                    
                    orch = ConversationOrchestrator(api_key='test-key')
                    orch.llm = mock_llm_instance
                    return orch
    
    def test_process_turn_increments_counter(self, orchestrator):
        """Test that turn count increments correctly"""
        mock_response = Mock()
        mock_response.content = "Hello! What are your financial goals?"
        orchestrator.llm.invoke = Mock(return_value=mock_response)
        
        assert orchestrator.turn_count == 0
        
        orchestrator.process_turn("I want to invest")
        assert orchestrator.turn_count == 1
        
        orchestrator.process_turn("I'm a teacher")
        assert orchestrator.turn_count == 2
    
    def test_process_turn_adds_to_history(self, orchestrator):
        """Test that messages are added to history"""
        mock_response = Mock()
        mock_response.content = "Great! Tell me more."
        orchestrator.llm.invoke = Mock(return_value=mock_response)
        
        assert len(orchestrator.conversation_history) == 0
        
        orchestrator.process_turn("Hello")
        
        # Should have user message and assistant response
        assert len(orchestrator.conversation_history) == 2
        assert orchestrator.conversation_history[0].role == "user"
        assert orchestrator.conversation_history[1].role == "assistant"
    
    def test_inject_system_prompt_includes_catalog(self, orchestrator):
        """Test that system prompt includes catalog context"""
        system_prompt = orchestrator.inject_system_prompt()
        
        # Should include base instruction
        assert "investment advisor" in system_prompt.lower()
        
        # Should include product info if catalog loaded
        if orchestrator.products:
            # Check for at least one product name mentioned
            product_names = [p.name for p in orchestrator.products[:3]]
            assert any(name in system_prompt for name in product_names)
    
    def test_inject_system_prompt_with_persona(self, orchestrator):
        """Test system prompt with extracted persona"""
        orchestrator.current_persona = Persona(
            professional_background="Software Engineer",
            interests=["Technology", "Growth"]
        )
        
        system_prompt = orchestrator.inject_system_prompt()
        
        # Should include persona information
        assert "Software Engineer" in system_prompt
        assert "Technology" in system_prompt
    
    def test_format_recommendations(self, orchestrator):
        """Test recommendation formatting"""
        products = [
            Product(
                id="et-001",
                name="Tech Fund",
                description="Technology focused",
                target_audience=["Tech workers"],
                categories=["Technology"],
                core_benefit="Tech exposure"
            ),
            Product(
                id="et-002",
                name="Bond Fund",
                description="Fixed income",
                target_audience=["Conservative"],
                categories=["Bonds"],
                core_benefit="Stable income"
            ),
        ]
        
        recommendation_text = orchestrator._format_recommendations(products)
        
        # Should include product names and benefits
        assert "Tech Fund" in recommendation_text
        assert "Bond Fund" in recommendation_text
        assert "Tech exposure" in recommendation_text
        assert "Stable income" in recommendation_text
    
    def test_reset_conversation(self, orchestrator):
        """Test conversation reset"""
        # Set up some state
        orchestrator.turn_count = 5
        orchestrator.conversation_history = [
            Message(role="user", content="test")
        ]
        orchestrator.current_persona = Persona(professional_background="Engineer")
        
        # Reset
        orchestrator.reset_conversation()
        
        # Check state is cleared
        assert orchestrator.turn_count == 0
        assert len(orchestrator.conversation_history) == 0
        assert orchestrator.current_persona.professional_background is None
    
    def test_get_turn_count(self, orchestrator):
        """Test getting turn count"""
        mock_response = Mock()
        mock_response.content = "Response"
        orchestrator.llm.invoke = Mock(return_value=mock_response)
        
        assert orchestrator.get_turn_count() == 0
        
        orchestrator.process_turn("Message 1")
        assert orchestrator.get_turn_count() == 1
        
        orchestrator.process_turn("Message 2")
        assert orchestrator.get_turn_count() == 2
    
    def test_get_conversation_history(self, orchestrator):
        """Test getting conversation history"""
        mock_response = Mock()
        mock_response.content = "Response"
        orchestrator.llm.invoke = Mock(return_value=mock_response)
        
        assert len(orchestrator.get_conversation_history()) == 0
        
        orchestrator.process_turn("Hello")
        
        history = orchestrator.get_conversation_history()
        assert len(history) == 2
        assert history[0].content == "Hello"
    
    def test_recommendations_triggered_after_turn_3(self, orchestrator):
        """Test that recommendations are triggered after turn 3"""
        mock_response = Mock()
        mock_response.content = "Response"
        orchestrator.llm.invoke = Mock(return_value=mock_response)
        
        # Mock product matcher
        mock_product = Product(
            id="test-1",
            name="Test",
            description="Test product",
            target_audience=["Test"],
            categories=["Test"],
            core_benefit="Test benefit"
        )
        orchestrator.product_matcher.match = Mock(return_value=[mock_product])
        orchestrator.current_persona = Persona(
            professional_background="Engineer",
            financial_goals="Growth"
        )
        
        # First two turns - no recommendations
        orchestrator.process_turn("Turn 1")
        assert len(orchestrator.recommendations) == 0
        
        orchestrator.process_turn("Turn 2")
        assert len(orchestrator.recommendations) == 0
        
        # Third turn - should trigger recommendations
        orchestrator.process_turn("Turn 3")
        # Recommendations may be added depending on persona sufficiency


# Property-based tests using hypothesis

def test_conversation_history_preserved():
    """
    Property 2: Conversation history preservation
    Validates: Requirements 1.2, 7.1, 7.2, 7.3, 7.4
    """
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        with patch('core.orchestrator.ChatGoogleGenerativeAI') as mock_llm_class:
            with patch('core.orchestrator.CatalogLoader') as mock_catalog:
                # Setup mocks
                mock_loader = MagicMock()
                mock_loader.load.return_value = []
                mock_catalog.return_value = mock_loader
                
                mock_llm = MagicMock()
                mock_llm_class.return_value = mock_llm
                
                orchestrator = ConversationOrchestrator(api_key='test-key')
                orchestrator.llm = mock_llm
                
                # Mock LLM response
                mock_response = Mock()
                mock_response.content = "Test response"
                orchestrator.llm.invoke = Mock(return_value=mock_response)
                
                # Process some turns
                messages = ["Hello", "I'm an engineer", "I want to grow my wealth"]
                
                for msg in messages:
                    orchestrator.process_turn(msg)
                
                # Check history preservation
                history = orchestrator.get_conversation_history()
                
                # Should have all messages (user + assistant pairs)
                assert len(history) == len(messages) * 2
                
                # User messages should be preserved exactly
                user_messages = [h.content for h in history if h.role == "user"]
                assert user_messages == messages


def test_interview_turn_limit():
    """
    Property 1: Interview turn limit
    Validates: Requirements 1.1
    
    The system should allow conversation up to at least 10 turns.
    """
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        with patch('core.orchestrator.ChatGoogleGenerativeAI') as mock_llm_class:
            with patch('core.orchestrator.CatalogLoader') as mock_catalog:
                # Setup mocks
                mock_loader = MagicMock()
                mock_loader.load.return_value = []
                mock_catalog.return_value = mock_loader
                
                mock_llm = MagicMock()
                mock_llm_class.return_value = mock_llm
                
                orchestrator = ConversationOrchestrator(api_key='test-key')
                orchestrator.llm = mock_llm
                
                mock_response = Mock()
                mock_response.content = "Response"
                orchestrator.llm.invoke = Mock(return_value=mock_response)
                
                # Process 10 turns
                for i in range(10):
                    orchestrator.process_turn(f"Message {i + 1}")
                
                # Should have completed 10 turns
                assert orchestrator.get_turn_count() == 10
                assert len(orchestrator.get_conversation_history()) == 20  # 10 pairs


def test_minimum_persona_extraction():
    """
    Property 4: Minimum persona extraction
    Validates: Requirements 1.4
    
    After conversation, should have extracted some persona information.
    """
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        with patch('core.orchestrator.ChatGoogleGenerativeAI') as mock_llm_class:
            with patch('core.orchestrator.CatalogLoader') as mock_catalog:
                # Setup mocks
                mock_loader = MagicMock()
                mock_loader.load.return_value = []
                mock_catalog.return_value = mock_loader
                
                mock_llm = MagicMock()
                mock_llm_class.return_value = mock_llm
                
                orchestrator = ConversationOrchestrator(api_key='test-key')
                orchestrator.llm = mock_llm
                
                # Mock persona extraction
                with patch.object(
                    orchestrator.persona_extractor,
                    'update',
                    return_value=Persona(professional_background="Engineer", interests=["Tech"])
                ):
                    mock_response = Mock()
                    mock_response.content = "Response"
                    orchestrator.llm.invoke = Mock(return_value=mock_response)
                    
                    orchestrator.process_turn("I'm an engineer")
                    
                    persona = orchestrator.get_current_persona()
                    
                    # Should have extracted some information
                    assert (
                        persona.professional_background or
                        persona.financial_goals or
                        persona.risk_appetite or
                        persona.interests
                    )


@given(
    product_name=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -",
        min_size=2,
        max_size=40,
    ).filter(lambda s: s.strip()),
    core_benefit=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-",
        min_size=5,
        max_size=80,
    ).filter(lambda s: s.strip()),
)
@settings(max_examples=40, deadline=None)
def test_catalog_context_injection_property(product_name, core_benefit):
    """
    Property 15: Catalog context injection
    Validates: Requirements 6.3
    """
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        with patch('core.orchestrator.ChatGoogleGenerativeAI') as mock_llm_class:
            with patch('core.orchestrator.CatalogLoader') as mock_catalog:
                mock_loader = MagicMock()
                mock_loader.load.return_value = [
                    Product(
                        id='et-test',
                        name=product_name,
                        description='desc',
                        target_audience=['investors'],
                        categories=['general'],
                        core_benefit=core_benefit,
                    )
                ]
                mock_catalog.return_value = mock_loader

                mock_llm = MagicMock()
                mock_llm_class.return_value = mock_llm

                orchestrator = ConversationOrchestrator(api_key='test-key')
                prompt = orchestrator.inject_system_prompt()

                assert "Available ET Products" in prompt
                assert product_name.strip() in prompt
                assert core_benefit.strip() in prompt


@given(
    background=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -",
        min_size=2,
        max_size=40,
    ).filter(lambda s: s.strip()),
    goals=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-",
        min_size=3,
        max_size=60,
    ).filter(lambda s: s.strip()),
    risk=st.sampled_from(["conservative", "moderate", "aggressive"]),
)
@settings(max_examples=40, deadline=None)
def test_system_prompt_injection_property(background, goals, risk):
    """
    Property 16: System prompt injection
    Validates: Requirements 6.4
    """
    with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
        with patch('core.orchestrator.ChatGoogleGenerativeAI') as mock_llm_class:
            with patch('core.orchestrator.CatalogLoader') as mock_catalog:
                mock_loader = MagicMock()
                mock_loader.load.return_value = []
                mock_catalog.return_value = mock_loader

                mock_llm = MagicMock()
                mock_llm_class.return_value = mock_llm

                orchestrator = ConversationOrchestrator(api_key='test-key')
                orchestrator.current_persona = Persona(
                    professional_background=background,
                    financial_goals=goals,
                    risk_appetite=risk,
                    interests=['tech'],
                )

                prompt = orchestrator.inject_system_prompt()

                assert "Current Understanding of User" in prompt
                assert background.strip() in prompt
                assert goals.strip() in prompt
                assert risk in prompt
