import os
from unittest.mock import MagicMock, patch

from core.models import Persona, Product
from core.orchestrator import ConversationOrchestrator


def _build_orchestrator_for_e2e() -> ConversationOrchestrator:
    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("core.orchestrator.ChatGoogleGenerativeAI") as mock_orch_llm_class:
            with patch("core.persona_extractor.ChatGoogleGenerativeAI") as mock_persona_llm_class:
                with patch("core.orchestrator.CatalogLoader") as mock_catalog:
                    loader = MagicMock()
                    loader.load.return_value = [
                        Product(
                            id="et-001",
                            name="Equity Growth Fund",
                            description="Diversified equity exposure",
                            target_audience=["Young professionals", "Growth investors"],
                            categories=["Equity", "Growth", "Diversified"],
                            core_benefit="Long-term wealth creation",
                        ),
                        Product(
                            id="et-002",
                            name="Fixed Income Plus",
                            description="Steady bond-oriented income",
                            target_audience=["Conservative investors", "Retirees"],
                            categories=["Fixed Income", "Bonds", "Conservative"],
                            core_benefit="Stable income with lower volatility",
                        ),
                        Product(
                            id="et-003",
                            name="Tech Innovation Portfolio",
                            description="Technology-sector growth focus",
                            target_audience=["Tech-savvy investors", "Growth seekers"],
                            categories=["Technology", "Growth", "Innovation"],
                            core_benefit="Exposure to high-growth technology opportunities",
                        ),
                    ]
                    mock_catalog.return_value = loader

                    mock_llm = MagicMock()
                    mock_orch_llm_class.return_value = mock_llm
                    mock_persona_llm_class.return_value = mock_llm

                    orch = ConversationOrchestrator(api_key="test-key")
                    orch.llm = mock_llm
                    return orch


def _install_dual_mode_llm(orch: ConversationOrchestrator) -> None:
    def invoke_side_effect(prompt: str):
        response = MagicMock()
        if "Recommended products:" in prompt:
            raise RuntimeError("force recommendation fallback formatting")
        response.content = "Thanks for sharing."
        return response

    orch.llm.invoke.side_effect = invoke_side_effect


def test_e2e_investor_flow_reaches_recommendations():
    orch = _build_orchestrator_for_e2e()
    _install_dual_mode_llm(orch)

    persona = Persona(
        professional_background="Analyst",
        financial_goals="long-term wealth creation",
        risk_appetite="aggressive",
        interests=["Growth", "Technology"],
    )

    with patch.object(orch, "_safe_extract_and_update", return_value=persona):
        orch.process_turn("I am building wealth for the long run")
        orch.process_turn("I can take higher risk")
        payload = orch.process_turn("I like growth and tech themes")

    assert payload["turn_count"] == 3
    assert payload["recommendations"] is not None
    assert 1 <= len(payload["recommendations"]) <= 2
    assert "Based on your profile" in payload["response"]


def test_e2e_entrepreneur_flow_prefers_growth_products():
    orch = _build_orchestrator_for_e2e()
    _install_dual_mode_llm(orch)

    persona = Persona(
        professional_background="Entrepreneur",
        financial_goals="high growth over 10 years",
        risk_appetite="aggressive",
        interests=["Innovation", "Growth"],
    )

    with patch.object(orch, "_safe_extract_and_update", return_value=persona):
        orch.process_turn("I run a startup")
        orch.process_turn("I want high upside")
        payload = orch.process_turn("I prefer innovation-focused options")

    names = [item["name"] for item in payload["recommendations"] or []]
    assert names
    assert any("Growth" in name or "Tech" in name for name in names)


def test_e2e_analyst_flow_includes_explanatory_product_details():
    orch = _build_orchestrator_for_e2e()
    _install_dual_mode_llm(orch)

    persona = Persona(
        professional_background="Research analyst",
        financial_goals="balanced wealth creation",
        risk_appetite="moderate",
        interests=["Diversified"],
    )

    with patch.object(orch, "_safe_extract_and_update", return_value=persona):
        orch.process_turn("I work in research")
        orch.process_turn("I need balanced options")
        payload = orch.process_turn("Diversification matters to me")

    assert payload["recommendations"]
    first_name = payload["recommendations"][0]["name"]
    first_benefit = payload["recommendations"][0]["core_benefit"]
    assert first_name in payload["response"]
    assert "Core Benefit:" in payload["response"]
    assert first_benefit in payload["response"]


def test_e2e_minimal_information_still_returns_safe_response():
    orch = _build_orchestrator_for_e2e()
    orch.llm.invoke.return_value = MagicMock(content="Could you share your financial goals?")

    empty_persona = Persona()
    with patch.object(orch, "_safe_extract_and_update", return_value=empty_persona):
        payload = orch.process_turn("Hi")

    assert payload["turn_count"] == 1
    assert payload["response"]
    assert payload["recommendations"] is None


def test_e2e_verbose_input_preserves_flow_and_history():
    orch = _build_orchestrator_for_e2e()
    orch.llm.invoke.return_value = MagicMock(content="Thanks, this gives me good context.")

    medium_persona = Persona(
        professional_background="Manager",
        financial_goals="income and growth",
        risk_appetite="moderate",
        interests=["Diversified"],
    )

    long_message = "I have a long context about my finances. " * 60
    with patch.object(orch, "_safe_extract_and_update", return_value=medium_persona):
        payload = orch.process_turn(long_message)

    assert payload["turn_count"] == 1
    assert len(orch.get_conversation_history()) == 2
    assert orch.get_conversation_history()[0].content == long_message.strip()
