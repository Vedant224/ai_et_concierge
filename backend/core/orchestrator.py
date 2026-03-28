import logging
import os
from collections.abc import Iterator
from typing import Any, List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from core.models import Persona, Product, Message
from core.catalog import CatalogLoader
from core.persona_extractor import PersonaExtractor
from core.product_matcher import ProductMatcher


logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """
    Orchestrates conversation flow with LLM, persona extraction, and product matching.
    Manages interview turns and triggers recommendations after turn 3.
    """

    LEARNING_INTENT_HINTS = (
        "ai",
        "machine learning",
        "ml",
        "data science",
        "career",
        "upskill",
        "learn",
        "course",
        "masterclass",
        "transition",
        "student",
        "engineering",
    )

    @staticmethod
    def _friendly_llm_error_message(exc: Exception) -> str:
        raw = str(exc).lower()

        if "resource_exhausted" in raw or "quota" in raw or "429" in raw:
            return (
                "I could not generate a response right now because the Gemini API "
                "quota is exhausted. Please retry later or use an API key/project "
                "with available quota."
            )

        if "rate limit" in raw or "too many requests" in raw:
            return (
                "I am being rate-limited by the AI provider right now. "
                "Please wait a few seconds and try again."
            )

        if "permission" in raw or "unauthorized" in raw or "api key" in raw:
            return (
                "I could not access the Gemini API. Please verify your API key "
                "and permissions, then try again."
            )

        return "I apologize, but I ran into a temporary issue. Please try again."

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        catalog_path: Optional[str] = None,
    ):
        """
        Initialize the orchestrator with LLM, catalog, and extractors.

        Args:
            api_key: Google API key for Gemini
            model: Model name to use
            catalog_path: Path to ET catalog JSON
        """
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if model is None:
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

        if not api_key:
            raise ValueError("Neither GEMINI_API_KEY nor GOOGLE_API_KEY was provided")

        # Initialize LLM
        self.llm = ChatGoogleGenerativeAI(
            model=model, google_api_key=api_key, temperature=0.7
        )

        # Load catalog
        self.catalog_loader = CatalogLoader(catalog_path)
        try:
            self.products = self.catalog_loader.load()
        except Exception as e:
            logger.warning("Failed to load catalog: %s", str(e))
            self.products = []

        # Initialize extractors
        self.persona_extractor = PersonaExtractor(api_key=api_key, model=model)
        self.product_matcher = ProductMatcher(self.products)

        # Conversation state
        self.conversation_history: List[Message] = []
        self.turn_count = 0
        self.current_persona = Persona()
        self.recommendations: List[Product] = []

    @staticmethod
    def _serialize_recommendations(products: List[Product]) -> List[dict[str, Any]]:
        return [
            {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "core_benefit": product.core_benefit,
                "target_audience": product.target_audience,
                "categories": product.categories,
                "product_id": product.product_id,
                "product_name": product.product_name,
                "includes": product.includes,
                "risk_profile": product.risk_profile,
                "trigger_keywords": product.trigger_keywords,
                "discovery_weight": product.discovery_weight,
                "cta_text": product.cta_text,
                "url": product.url,
            }
            for product in products
        ]

    def _finalize_recommendations(self, assistant_response: str) -> str:
        """Apply recommendation logic after a response is generated."""
        if self.turn_count < 3:
            return assistant_response

        self.recommendations = self.product_matcher.match(self.current_persona)
        if self.current_persona.is_sufficient_for_matching() and self.recommendations:
            conversational_block = self._format_recommendations_conversational(
                self.recommendations
            )
            return f"{assistant_response}\n\n{conversational_block}"
        return assistant_response

    def _build_recommendation_prompt(self, products: List[Product]) -> str:
        """Create a focused prompt for conversational recommendation formatting."""
        persona_parts: List[str] = []
        if self.current_persona.professional_background:
            persona_parts.append(
                f"professional background: {self.current_persona.professional_background}"
            )
        if self.current_persona.financial_goals:
            persona_parts.append(
                f"financial goals: {self.current_persona.financial_goals}"
            )
        if self.current_persona.risk_appetite:
            persona_parts.append(f"risk appetite: {self.current_persona.risk_appetite}")
        if self.current_persona.interests:
            persona_parts.append(
                f"interests: {', '.join(self.current_persona.interests)}"
            )

        persona_context = (
            "; ".join(persona_parts) if persona_parts else "limited known persona data"
        )
        product_lines = "\n".join(
            f"- {p.name}: {p.core_benefit} (Description: {p.description})"
            for p in products
        )

        return (
            "You are preparing final recommendations for an ET ecosystem concierge.\n"
            f"Known user persona: {persona_context}.\n"
            "Focus primarily on the user's strongest stated intent and preferences.\n"
            "If you mention alternatives, keep them to one short line.\n"
            "Write a concise, conversational recommendation section that:\n"
            "1) explicitly names each recommended product,\n"
            "2) explains why each recommendation fits the persona,\n"
            "3) includes each product's core benefit in plain language.\n"
            "Keep it under 180 words total.\n\n"
            f"Recommended products:\n{product_lines}\n"
        )

    def _format_recommendations_conversational(self, products: List[Product]) -> str:
        """Generate conversational recommendation text with graceful fallback."""
        if not products:
            return ""

        prompt = self._build_recommendation_prompt(products)
        try:
            response = self.llm.invoke(prompt)
            text = str(response.content).strip()
            if text:
                return text
        except Exception:
            logger.exception("Failed to generate conversational recommendation block")

        return self._format_recommendations(products)

    def _build_turn_payload(self, assistant_response: str) -> dict[str, Any]:
        """Build a stable response payload for API handlers."""
        return {
            "response": assistant_response,
            "turn_count": self.turn_count,
            "recommendations": self._serialize_recommendations(self.recommendations)
            or None,
        }

    def sync_history(self, conversation_history: List[dict[str, str]]) -> None:
        """Synchronize orchestrator state from externally provided history."""
        parsed_history: List[Message] = []
        for item in conversation_history:
            role = item.get("role", "").strip().lower()
            content = item.get("content", "")
            if role not in {"user", "assistant", "system"}:
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            parsed_history.append(Message(role=role, content=content))

        self.conversation_history = parsed_history
        self.turn_count = sum(1 for message in parsed_history if message.role == "user")
        self.recommendations = []

        # Keep extractor state aligned with the canonical history.
        self.persona_extractor.reset()
        for message in parsed_history:
            self.persona_extractor.add_message(message)

        self.current_persona = self._safe_extract_and_update(parsed_history)

    def _safe_extract_and_update(self, history: List[Message]) -> Persona:
        """Extract and merge persona data without breaking conversation flow."""
        try:
            extracted = self.persona_extractor.extract(history)
            return self.persona_extractor.update(extracted)
        except Exception:
            logger.exception(
                "Persona extraction/update failed; preserving previous persona state"
            )
            return self.current_persona

    def _apply_intent_enrichment(self) -> None:
        """Add deterministic persona hints from recent user language."""
        user_text = " ".join(
            m.content.lower() for m in self.conversation_history if m.role == "user"
        )
        if not user_text:
            return

        interests = list(self.current_persona.interests or [])

        def add_interest(value: str) -> None:
            if value not in interests:
                interests.append(value)

        has_learning_intent = any(
            hint in user_text for hint in self.LEARNING_INTENT_HINTS
        )
        if has_learning_intent:
            if not self.current_persona.learning_goals:
                self.current_persona.learning_goals = (
                    "Build practical skills for AI development"
                )
            if not self.current_persona.transition_intent and "transition" in user_text:
                self.current_persona.transition_intent = (
                    "Transitioning into AI-related roles"
                )
            if not self.current_persona.career_stage and "student" in user_text:
                self.current_persona.career_stage = "Student"
            add_interest("AI development")
            add_interest("Masterclass")
            add_interest("Career growth")

        self.current_persona.interests = interests

    def process_turn(self, user_message: str) -> dict[str, Any]:
        """
        Process a single conversation turn.

        Args:
            user_message: User's input message

        Returns:
            Dict with response, turn_count, recommendations
        """
        self.turn_count += 1

        # Add user message to history
        user_msg = Message(role="user", content=user_message)
        self.conversation_history.append(user_msg)
        self.persona_extractor.add_message(user_msg)

        # Extract/update persona
        self.current_persona = self._safe_extract_and_update(self.conversation_history)
        self._apply_intent_enrichment()

        # Build system prompt with context
        system_prompt = self.inject_system_prompt()

        # Generate assistant response
        try:
            response = self.llm.invoke(system_prompt + f"\n\nUser: {user_message}")
            assistant_response = response.content.strip()
        except Exception as exc:
            logger.exception("Failed to generate LLM response")
            assistant_response = self._friendly_llm_error_message(exc)

        # Add assistant message to history
        assistant_msg = Message(role="assistant", content=assistant_response)
        self.conversation_history.append(assistant_msg)
        self.persona_extractor.add_message(assistant_msg)

        assistant_response = self._finalize_recommendations(assistant_response)
        return self._build_turn_payload(assistant_response)

    def stream_turn(self, user_message: str) -> Iterator[str]:
        """Stream a conversation turn as token chunks and return final state."""
        self.turn_count += 1

        user_msg = Message(role="user", content=user_message)
        self.conversation_history.append(user_msg)
        self.persona_extractor.add_message(user_msg)

        self.current_persona = self._safe_extract_and_update(self.conversation_history)
        self._apply_intent_enrichment()

        system_prompt = self.inject_system_prompt()
        accumulated: List[str] = []

        try:
            for chunk in self.llm.stream(system_prompt + f"\n\nUser: {user_message}"):
                content = getattr(chunk, "content", "")
                if not content:
                    continue
                text = str(content)
                accumulated.append(text)
                yield text
        except Exception as exc:
            logger.exception("Failed to stream LLM response")
            fallback = self._friendly_llm_error_message(exc)
            accumulated = [fallback]
            yield fallback

        assistant_response = "".join(accumulated).strip()
        assistant_response = self._finalize_recommendations(assistant_response)

        # If recommendation block was appended, stream the appended segment too.
        streamed_base = "".join(accumulated).strip()
        if assistant_response != streamed_base:
            suffix = assistant_response[len(streamed_base) :]
            if suffix:
                yield suffix

        assistant_msg = Message(role="assistant", content=assistant_response)
        self.conversation_history.append(assistant_msg)
        self.persona_extractor.add_message(assistant_msg)

        yield "\n<<END_OF_STREAM>>\n"

    def inject_system_prompt(self) -> str:
        """
        Build the system prompt with catalog and persona context.

        Returns:
            Full system prompt with context
        """
        base_prompt = """
    You are an ET ecosystem concierge assistant.
    Your goal is to understand user intent and guide them to the right ET offerings.
    User intent may include learning/career growth, market tracking, wealth planning, enterprise insights, or lifestyle content.

    Important behavior rules:
    - Prioritize the user's most recent and strongest stated intent above everything else.
    - Keep the main answer focused on that intent in 2-4 lines before any extras.
    - If mentioning other ET offerings, add at most one short secondary suggestion.
    - If user asks for markets/stocks, keep focus on markets first and avoid long lifestyle detours.
    - If the user asks for learning, courses, AI development, career transition, or masterclasses, prioritize ET Masterclass and career-oriented guidance.
    - Do not force investment-first questions when the user intent is clearly learning/career oriented.
    - Ask one focused follow-up question at a time and keep responses concise, friendly, and practical.
    """

        # Add catalog context
        if self.products:
            catalog_text = "\n\nAvailable ET Products:\n"
            for product in self.products[:3]:  # Include first 3 products as examples
                catalog_text += f"- {product.name}: {product.core_benefit}\n"
            base_prompt += catalog_text

        # Add current persona context if extracted
        if (
            self.current_persona.professional_background
            or self.current_persona.interests
        ):
            persona_text = "\n\nCurrent Understanding of User:\n"
            if self.current_persona.professional_background:
                persona_text += (
                    f"- Background: {self.current_persona.professional_background}\n"
                )
            if self.current_persona.financial_goals:
                persona_text += f"- Goals: {self.current_persona.financial_goals}\n"
            if self.current_persona.risk_appetite:
                persona_text += (
                    f"- Risk Appetite: {self.current_persona.risk_appetite}\n"
                )
            if self.current_persona.learning_goals:
                persona_text += (
                    f"- Learning Goals: {self.current_persona.learning_goals}\n"
                )
            if self.current_persona.career_stage:
                persona_text += f"- Career Stage: {self.current_persona.career_stage}\n"
            if self.current_persona.transition_intent:
                persona_text += (
                    f"- Transition Intent: {self.current_persona.transition_intent}\n"
                )
            if self.current_persona.interests:
                persona_text += (
                    f"- Interests: {', '.join(self.current_persona.interests)}\n"
                )
            base_prompt += persona_text

        return base_prompt

    def _format_recommendations(self, products: List[Product]) -> str:
        """
        Format product recommendations for display.

        Args:
            products: List of Product recommendations

        Returns:
            Formatted recommendation text
        """
        if not products:
            return ""

        text = "\n📊 **Based on your profile, here are my recommendations:**\n"

        for i, product in enumerate(products, 1):
            text += f"\n{i}. **{product.name}**\n"
            text += f"   {product.description}\n"
            text += f"   Core Benefit: {product.core_benefit}\n"

        return text

    def get_conversation_history(self) -> List[Message]:
        """Get conversation history"""
        return self.conversation_history

    def get_turn_count(self) -> int:
        """Get current turn count"""
        return self.turn_count

    def get_current_persona(self) -> Persona:
        """Get current extracted persona"""
        return self.current_persona

    def get_recommendations(self) -> List[Product]:
        """Get current product recommendations"""
        return self.recommendations

    def reset_conversation(self) -> None:
        """Reset conversation state"""
        self.conversation_history = []
        self.turn_count = 0
        self.current_persona = Persona()
        self.recommendations = []
        self.persona_extractor.reset()
