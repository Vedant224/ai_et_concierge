"""
Pydantic models for the ET User Profiling Agent
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class Message(BaseModel):
    """Model for conversation messages"""
    role: str = Field(..., description="Role of sender: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "I'm interested in growth investments",
                "timestamp": "2024-01-01T12:00:00"
            }
        }


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

    class Config:
        json_schema_extra = {
            "example": {
                "professional_background": "Software Engineer",
                "financial_goals": "Long-term wealth accumulation",
                "risk_appetite": "moderate",
                "interests": ["Technology", "Growth", "Sustainable investing"]
            }
        }

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

    class Config:
        json_schema_extra = {
            "example": {
                "id": "et-001",
                "name": "Equity Growth Fund",
                "description": "A diversified equity fund focused on long-term capital appreciation",
                "target_audience": ["Young professionals", "Long-term investors"],
                "categories": ["Equity", "Growth", "Diversified"],
                "core_benefit": "Long-term wealth creation through equity market participation"
            }
        }

    @validator('id', 'name', 'description', 'core_benefit')
    def fields_not_empty(cls, v):
        """Validate that required string fields are not empty"""
        if isinstance(v, str) and not v.strip():
            raise ValueError('Field cannot be empty')
        return v

    @validator('target_audience', 'categories')
    def lists_not_empty(cls, v):
        """Validate that list fields contain at least one item"""
        if not v or len(v) == 0:
            raise ValueError('List cannot be empty')
        return v
