from unittest.mock import MagicMock, Mock, patch

from hypothesis import given, settings, strategies as st

from core.models import Persona, Product
from core.orchestrator import ConversationOrchestrator


def _build_orchestrator() -> ConversationOrchestrator:
    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("core.orchestrator.ChatGoogleGenerativeAI") as mock_llm_class:
            with patch("core.orchestrator.CatalogLoader") as mock_catalog:
                mock_loader = MagicMock()
                mock_loader.load.return_value = []
                mock_catalog.return_value = mock_loader

                mock_llm = MagicMock()
                mock_llm_class.return_value = mock_llm

                orchestrator = ConversationOrchestrator(api_key="test-key")
                orchestrator.llm = mock_llm
                return orchestrator


def _sample_products() -> list[Product]:
    return [
        Product(
            id="et-001",
            name="Tech Growth Fund",
            description="High-growth technology equities.",
            target_audience=["Growth investors"],
            categories=["Technology", "Growth"],
            core_benefit="Exposure to innovative growth companies",
        ),
        Product(
            id="et-002",
            name="Balanced Income Fund",
            description="Mix of dividend equities and high-quality bonds.",
            target_audience=["Moderate investors"],
            categories=["Balanced", "Income"],
            core_benefit="Steadier returns with regular income",
        ),
    ]


def test_conversational_recommendation_format_contains_details():
    """Property 9/11: conversational format includes product details."""
    orchestrator = _build_orchestrator()
    orchestrator.current_persona = Persona(
        professional_background="Software Engineer",
        financial_goals="Long-term wealth growth",
        risk_appetite="moderate",
        interests=["Technology"],
    )

    products = _sample_products()
    mock_response = Mock()
    mock_response.content = (
        "Given your software background and moderate risk profile, "
        "Tech Growth Fund can align with your growth goal through exposure to innovative companies, "
        "while Balanced Income Fund supports steadier returns with regular income."
    )
    orchestrator.llm.invoke = Mock(return_value=mock_response)

    text = orchestrator._format_recommendations_conversational(products)

    assert "Tech Growth Fund" in text
    assert "Balanced Income Fund" in text
    assert "moderate" in text.lower() or "risk" in text.lower()


def test_recommendation_fallback_when_llm_fails():
    """Fallback should still include product names and benefits if LLM fails."""
    orchestrator = _build_orchestrator()
    orchestrator.llm.invoke = Mock(side_effect=RuntimeError("llm down"))
    text = orchestrator._format_recommendations_conversational(_sample_products())

    assert "Tech Growth Fund" in text
    assert "Balanced Income Fund" in text
    assert "Core Benefit" in text


@given(
    background=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -",
        min_size=3,
        max_size=40,
    ).filter(lambda s: s.strip()),
    goal=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-",
        min_size=5,
        max_size=60,
    ).filter(lambda s: s.strip()),
)
@settings(max_examples=40, deadline=None)
def test_recommendation_explanation_presence(background, goal):
    """Property 10: recommendation output should include explanation signal."""
    orchestrator = _build_orchestrator()
    orchestrator.current_persona = Persona(
        professional_background=background,
        financial_goals=goal,
        risk_appetite="moderate",
        interests=["technology"],
    )

    products = _sample_products()

    # Emulate conversational generator that references persona + rationale.
    mock_response = Mock()
    mock_response.content = (
        f"Because your background is {background.strip()} and your goal is {goal.strip()}, "
        "these recommendations fit your profile and balance growth with stability."
    )
    orchestrator.llm.invoke = Mock(return_value=mock_response)

    text = orchestrator._format_recommendations_conversational(products)

    assert "because" in text.lower() or "fit" in text.lower() or "profile" in text.lower()


def test_recommendation_prompt_includes_persona_and_products():
    orchestrator = _build_orchestrator()
    orchestrator.current_persona = Persona(
        professional_background="Analyst",
        financial_goals="Retirement corpus",
        risk_appetite="moderate",
        interests=["income", "dividend"],
    )

    products = _sample_products()
    prompt = orchestrator._build_recommendation_prompt(products)

    assert "professional background: Analyst" in prompt
    assert "financial goals: Retirement corpus" in prompt
    assert "Tech Growth Fund" in prompt
    assert "Balanced Income Fund" in prompt
