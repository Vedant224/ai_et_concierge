import json
import logging
import os
import re
from typing import Any, List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from core.models import Persona, Message


logger = logging.getLogger(__name__)


class PersonaExtractor:
    """
    Extracts and maintains user personas from conversation history using LLM.
    Uses Gemini 1.5 Flash for structured output.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        """
        Initialize PersonaExtractor with Gemini LLM.
        
        Args:
            api_key: Google API key. If None, uses GEMINI_API_KEY then GOOGLE_API_KEY
            model: Model name to use (default: gemini-1.5-flash)
        """
        if api_key is None:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not api_key:
            raise ValueError("Neither GEMINI_API_KEY nor GOOGLE_API_KEY was provided")
        
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.2,
        )
        self.current_persona = Persona()
        self.conversation_history: List[Message] = []

    @staticmethod
    def _extract_json_object(raw_text: str) -> Optional[dict[str, Any]]:
        """Extract the first JSON object from model output."""
        text = raw_text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try fenced code block first
            fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if fenced_match:
                try:
                    return json.loads(fenced_match.group(1))
                except json.JSONDecodeError:
                    return None

            # Fallback: first {...} block
            brace_match = re.search(r"\{.*\}", text, re.DOTALL)
            if not brace_match:
                return None
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                return None
    
    def extract(self, conversation_history: List[Message]) -> Persona:
        """
        Extract persona from conversation history using LLM.
        
        Args:
            conversation_history: List of Message objects from the conversation
            
        Returns:
            Extracted Persona object
        """
        if not conversation_history:
            return Persona()
        
        # Build conversation text for LLM
        conversation_text = "\n".join([
            f"{msg.role.upper()}: {msg.content}"
            for msg in conversation_history
        ])
        
        # Create extraction prompt
        extraction_prompt = f"""
Analyze the following conversation and extract user persona information.
Return a JSON object with these optional fields:
- professional_background: User's job/career (string or null)
- financial_goals: User's financial objectives (string or null)
- risk_appetite: Risk tolerance level - one of: 'conservative', 'moderate', 'aggressive' (string or null)
- interests: List of investment interests/preferences (array of strings or null)

Conversation:
{conversation_text}

Return ONLY valid JSON, no other text.
"""
        
        try:
            response = self.llm.invoke(extraction_prompt)
            response_text = str(response.content)

            persona_data = self._extract_json_object(response_text)
            if persona_data is None:
                logger.warning("Persona extraction failed: model did not return valid JSON")
                return Persona()

            return Persona(**persona_data)
        except Exception as e:
            # If extraction fails, return empty persona
            logger.warning("Persona extraction failed: %s", str(e))
            return Persona()
    
    def update(self, new_information: Persona) -> Persona:
        """
        Merge new information into the current persona.
        
        Args:
            new_information: New Persona data to merge
            
        Returns:
            Updated Persona object
        """
        # Simple merge strategy: new information overrides old
        updated = Persona(
            professional_background=new_information.professional_background or self.current_persona.professional_background,
            financial_goals=new_information.financial_goals or self.current_persona.financial_goals,
            risk_appetite=new_information.risk_appetite or self.current_persona.risk_appetite,
            interests=list(set(
                (new_information.interests or []) + (self.current_persona.interests or [])
            ))  # Merge and deduplicate interests
        )
        
        self.current_persona = updated
        return updated
    
    def get_current_persona(self) -> Persona:
        """
        Get the current extracted persona.
        
        Returns:
            Current Persona object
        """
        return self.current_persona
    
    def add_message(self, message: Message) -> None:
        """
        Add a message to conversation history.
        
        Args:
            message: Message to add
        """
        self.conversation_history.append(message)
    
    def get_conversation_history(self) -> List[Message]:
        """
        Get conversation history.
        
        Returns:
            List of Message objects
        """
        return self.conversation_history

    def reset(self) -> None:
        """Reset extractor state."""
        self.current_persona = Persona()
        self.conversation_history = []
