"""
Pydantic models for the ET User Profiling Agent
"""
from datetime import UTC, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class Message(BaseModel):
    """Model for conversation messages"""
    role: str = Field(..., description="Role of sender: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Message timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "I'm interested in growth investments",
                "timestamp": "2024-01-01T12:00:00"
            }
        }
    )

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Normalize and validate message role."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Role must be a non-empty string")
        normalized = value.strip().lower()
        if normalized not in {"user", "assistant", "system"}:
            raise ValueError("Role must be one of: user, assistant, system")
        return normalized

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Ensure message content is non-empty after trimming."""
        if not isinstance(value, str):
            raise ValueError("Content must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Content cannot be empty")
        return normalized


class Persona(BaseModel):
    """Model for user persona extracted from conversation"""
    professional_background: Optional[str] = Field(
        None, 
        description="User's professional background or occupation"
    )
    financial_goals: Optional[str] = Field(
        None, 
        description="User's financial goals or objectives"
    )
    risk_appetite: Optional[str] = Field(
        None, 
        description="User's risk tolerance level (e.g., 'conservative', 'moderate', 'aggressive')"
    )
    interests: Optional[List[str]] = Field(
        default_factory=list, 
        description="List of investment interests or preferences"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "professional_background": "Software Engineer",
                "financial_goals": "Long-term wealth accumulation",
                "risk_appetite": "moderate",
                "interests": ["Technology", "Growth", "Sustainable investing"]
            }
        }
    )

    @field_validator("professional_background", "financial_goals", "risk_appetite", mode="before")
    @classmethod
    def normalize_optional_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Field must be a string or null")
        normalized = value.strip()
        return normalized or None

    @field_validator("interests", mode="before")
    @classmethod
    def normalize_interests(cls, value: Optional[List[str]]) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Interests must be a list or null")
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    def is_sufficient_for_matching(self) -> bool:
        """
        Check if persona has sufficient information for product matching.
        
        Returns:
            bool: True if at least one field is populated, False otherwise
        """
        return any([
            self.professional_background,
            self.financial_goals,
            self.risk_appetite,
            self.interests
        ])

    def matches_persona(self, other: 'Persona') -> bool:
        """
        Check if another persona matches this persona's profile.
        
        Args:
            other: Another Persona instance to compare
            
        Returns:
            bool: True if personas have overlapping interests/goals
        """
        # Check for overlapping interests
        if self.interests and other.interests:
            return bool(set(self.interests) & set(other.interests))
        
        # Check if risk appetites match
        if self.risk_appetite and other.risk_appetite:
            return self.risk_appetite.lower() == other.risk_appetite.lower()
        
        # Check if financial goals match
        if self.financial_goals and other.financial_goals:
            return self.financial_goals.lower() in other.financial_goals.lower()
        
        return True  # Default to match if not enough info


class Product(BaseModel):
    """Model for ET (Exchange Traded) products"""
    id: str = Field(..., description="Unique product identifier")
    name: str = Field(..., description="Product name")
    description: str = Field(..., description="Detailed product description")
    target_audience: List[str] = Field(..., description="List of target audience segments")
    categories: List[str] = Field(..., description="Product categories")
    core_benefit: str = Field(..., description="Core benefit of the product")
    product_id: Optional[str] = Field(None, description="Machine-readable product slug")
    product_name: Optional[str] = Field(None, description="Display name for product")
    includes: List[str] = Field(default_factory=list, description="Included sections/services")
    risk_profile: List[str] = Field(default_factory=list, description="Supported risk profiles")
    trigger_keywords: List[str] = Field(default_factory=list, description="Keyword triggers for discovery")
    discovery_weight: int = Field(default=1, description="Relative score for discovery ranking")
    cta_text: Optional[str] = Field(None, description="CTA copy for the product")
    url: Optional[str] = Field(None, description="Landing page URL")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "et-001",
                "name": "Equity Growth Fund",
                "description": "A diversified equity fund focused on long-term capital appreciation",
                "target_audience": ["Young professionals", "Long-term investors"],
                "categories": ["Equity", "Growth", "Diversified"],
                "core_benefit": "Long-term wealth creation through equity market participation"
            }
        }
    )

    @field_validator('id', 'name', 'description', 'core_benefit', mode='before')
    @classmethod
    def fields_not_empty(cls, v):
        """Validate that required string fields are not empty after stripping"""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError('Field cannot be empty')
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_and_new_catalog_shapes(cls, data):
        if not isinstance(data, dict):
            return data

        normalized = dict(data)

        if "id" not in normalized and normalized.get("product_id"):
            normalized["id"] = normalized["product_id"]
        if "name" not in normalized and normalized.get("product_name"):
            normalized["name"] = normalized["product_name"]
        if "categories" not in normalized and normalized.get("includes"):
            normalized["categories"] = normalized["includes"]
        if "description" not in normalized and normalized.get("core_benefit"):
            normalized["description"] = normalized["core_benefit"]

        if "product_id" not in normalized and normalized.get("id"):
            normalized["product_id"] = normalized["id"]
        if "product_name" not in normalized and normalized.get("name"):
            normalized["product_name"] = normalized["name"]
        if "includes" not in normalized and normalized.get("categories"):
            normalized["includes"] = normalized["categories"]

        return normalized

    @field_validator('target_audience', 'categories', mode='before')
    @classmethod
    def lists_not_empty(cls, v):
        """Validate that list fields contain at least one item with non-empty strings"""
        if isinstance(v, list):
            # Filter out empty strings and strip whitespace
            v = [item.strip() for item in v if isinstance(item, str) and item.strip()]
            if not v:
                raise ValueError('List cannot be empty')
        return v
