from unittest.mock import MagicMock, Mock, patch

from hypothesis import given, settings, strategies as st

from core.models import Persona, Product
from core.orchestrator import ConversationOrchestrator


def _orchestrator_with_mocks() -> ConversationOrchestrator:
    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("core.orchestrator.ChatGoogleGenerativeAI") as mock_llm_class:
            with patch("core.persona_extractor.ChatGoogleGenerativeAI") as mock_persona_llm_class:
                with patch("core.orchestrator.CatalogLoader") as mock_catalog:
                    mock_loader = MagicMock()
                    mock_loader.load.return_value = [
                        Product(
                            id="et-001",
                            name="Growth Fund",
                            description="Growth focus",
                            target_audience=["Investors"],
                            categories=["Growth"],
                            core_benefit="Long-term wealth",
                        )
                    ]
                    mock_catalog.return_value = mock_loader

                    mock_llm = MagicMock()
                    mock_llm_class.return_value = mock_llm
                    mock_persona_llm_class.return_value = mock_llm

                    orch = ConversationOrchestrator(api_key="test-key")
                    orch.llm = mock_llm
                    return orch


def test_llm_failure_keeps_history_and_returns_fallback_message():
    """Task 12.3: LLM failure should not drop conversation history."""
    orch = _orchestrator_with_mocks()
    orch.llm.invoke = Mock(side_effect=RuntimeError("provider down"))

    payload = orch.process_turn("hello")

    assert payload["response"].startswith("I apologize")
    assert len(orch.get_conversation_history()) == 2
    assert orch.get_conversation_history()[0].role == "user"
    assert orch.get_conversation_history()[1].role == "assistant"


def test_persona_extraction_failure_preserves_previous_persona():
    """Task 12.3: persona extraction/update errors preserve prior persona state."""
    orch = _orchestrator_with_mocks()
    orch.current_persona = Persona(professional_background="Analyst")

    with patch.object(orch.persona_extractor, "extract", side_effect=RuntimeError("extract failed")):
        orch.llm.invoke = Mock(return_value=Mock(content="ok"))
        orch.process_turn("hi")

    assert orch.current_persona.professional_background == "Analyst"
    assert len(orch.get_conversation_history()) == 2


def test_catalog_loading_failure_is_graceful():
    """Task 12.3: catalog failures should not crash orchestrator construction."""
    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("core.orchestrator.ChatGoogleGenerativeAI"):
            with patch("core.orchestrator.CatalogLoader") as mock_catalog:
                loader = MagicMock()
                loader.load.side_effect = FileNotFoundError("missing catalog")
                mock_catalog.return_value = loader

                orch = ConversationOrchestrator(api_key="test-key")
                assert orch.products == []
                assert orch.product_matcher.products == []


@given(
    messages=st.lists(
        st.text(min_size=1, max_size=50).filter(lambda msg: msg.strip() != ""),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=30, deadline=None)
def test_error_resilience_conversation_history_property(messages):
    """Property 19: on LLM errors, user messages remain preserved in history."""
    orch = _orchestrator_with_mocks()
    orch.llm.invoke = Mock(side_effect=RuntimeError("llm unavailable"))

    for msg in messages:
        orch.process_turn(msg)

    history = orch.get_conversation_history()
    user_messages = [m.content for m in history if m.role == "user"]

    assert user_messages == [msg.strip() for msg in messages]
    assert len(history) == len(messages) * 2
