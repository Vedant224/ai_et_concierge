"""
Unit tests for backend data models and catalog loading
"""
import pytest
import json
import tempfile
from pathlib import Path

from core.models import Persona, Product, Message
from core.catalog import CatalogLoader


class TestPersonaModel:
    """Unit tests for Persona model"""

    def test_persona_creation_with_all_fields(self):
        """Test creating a complete Persona"""
        persona = Persona(
            professional_background="Engineer",
            financial_goals="Growth",
            risk_appetite="moderate",
            interests=["Tech", "Growth"]
        )
        
        assert persona.professional_background == "Engineer"
        assert persona.financial_goals == "Growth"
        assert persona.risk_appetite == "moderate"
        assert persona.interests == ["Tech", "Growth"]

    def test_persona_creation_minimal(self):
        """Test creating a minimal Persona with optional fields"""
        persona = Persona()
        
        assert persona.professional_background is None
        assert persona.financial_goals is None
        assert persona.risk_appetite is None
        assert persona.interests == []

    def test_persona_is_sufficient_with_background(self):
        """Test is_sufficient_for_matching with background"""
        persona = Persona(professional_background="Engineer")
        assert persona.is_sufficient_for_matching() is True

    def test_persona_is_sufficient_with_goals(self):
        """Test is_sufficient_for_matching with goals"""
        persona = Persona(financial_goals="Growth")
        assert persona.is_sufficient_for_matching() is True

    def test_persona_is_sufficient_with_interests(self):
        """Test is_sufficient_for_matching with interests"""
        persona = Persona(interests=["Tech"])
        assert persona.is_sufficient_for_matching() is True

    def test_persona_is_not_sufficient_empty(self):
        """Test is_sufficient_for_matching with empty persona"""
        persona = Persona()
        assert persona.is_sufficient_for_matching() is False

    def test_persona_matches_overlapping_interests(self):
        """Test matches_persona with overlapping interests"""
        persona1 = Persona(interests=["Tech", "Growth"])
        persona2 = Persona(interests=["Tech", "Innovation"])
        
        assert persona1.matches_persona(persona2) is True

    def test_persona_matches_same_risk_appetite(self):
        """Test matches_persona with same risk appetite"""
        persona1 = Persona(risk_appetite="moderate")
        persona2 = Persona(risk_appetite="moderate")
        
        assert persona1.matches_persona(persona2) is True

    def test_persona_matches_different_risk_appetite(self):
        """Test matches_persona with different risk appetite"""
        persona1 = Persona(risk_appetite="conservative")
        persona2 = Persona(risk_appetite="aggressive")
        
        assert persona1.matches_persona(persona2) is False


class TestProductModel:
    """Unit tests for Product model"""

    def test_product_creation_valid(self):
        """Test creating a valid Product"""
        product = Product(
            id="et-001",
            name="Growth Fund",
            description="A growth-focused fund",
            target_audience=["Young investors"],
            categories=["Growth", "Equity"],
            core_benefit="Long-term wealth creation"
        )
        
        assert product.id == "et-001"
        assert product.name == "Growth Fund"
        assert len(product.target_audience) == 1
        assert len(product.categories) == 2

    def test_product_validation_empty_id(self):
        """Test Product validation rejects empty ID"""
        with pytest.raises(ValueError):
            Product(
                id="",
                name="Growth Fund",
                description="A growth-focused fund",
                target_audience=["Young investors"],
                categories=["Growth"],
                core_benefit="Long-term wealth creation"
            )

    def test_product_validation_empty_target_audience(self):
        """Test Product validation rejects empty target audience"""
        with pytest.raises(ValueError):
            Product(
                id="et-001",
                name="Growth Fund",
                description="A growth-focused fund",
                target_audience=[],
                categories=["Growth"],
                core_benefit="Long-term wealth creation"
            )

    def test_product_validation_empty_categories(self):
        """Test Product validation rejects empty categories"""
        with pytest.raises(ValueError):
            Product(
                id="et-001",
                name="Growth Fund",
                description="A growth-focused fund",
                target_audience=["Young investors"],
                categories=[],
                core_benefit="Long-term wealth creation"
            )


class TestMessageModel:
    """Unit tests for Message model"""

    def test_message_creation_with_timestamp(self):
        """Test creating a Message with custom timestamp"""
        from datetime import datetime
        ts = datetime(2024, 1, 1, 12, 0, 0)
        
        message = Message(
            role="user",
            content="Test message",
            timestamp=ts
        )
        
        assert message.role == "user"
        assert message.content == "Test message"
        assert message.timestamp == ts

    def test_message_creation_auto_timestamp(self):
        """Test creating a Message with auto-generated timestamp"""
        message = Message(
            role="assistant",
            content="Response"
        )
        
        assert message.role == "assistant"
        assert message.content == "Response"
        assert message.timestamp is not None


class TestCatalogLoader:
    """Unit tests for CatalogLoader"""

    def test_catalog_load_success(self):
        """Test loading a valid catalog"""
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "catalog.json"
            
            catalog_data = {
                "products": [
                    {
                        "id": "et-001",
                        "name": "Product 1",
                        "description": "Test product",
                        "target_audience": ["Investors"],
                        "categories": ["Growth"],
                        "core_benefit": "Growth"
                    }
                ]
            }
            
            with open(catalog_path, 'w') as f:
                json.dump(catalog_data, f)
            
            loader = CatalogLoader(str(catalog_path))
            products = loader.load()
            
            assert len(products) == 1
            assert products[0].id == "et-001"
            assert products[0].name == "Product 1"

    def test_catalog_validate_product_success(self):
        """Test validating a valid product"""
        loader = CatalogLoader("")
        
        product_data = {
            "id": "et-001",
            "name": "Product",
            "description": "Description",
            "target_audience": ["Audience"],
            "categories": ["Category"],
            "core_benefit": "Benefit"
        }
        
        assert loader.validate_product(product_data) is True

    def test_catalog_validate_product_missing_field(self):
        """Test validating product with missing field"""
        loader = CatalogLoader("")
        
        product_data = {
            "id": "et-001",
            "name": "Product"
            # Missing other fields
        }
        
        with pytest.raises(ValueError, match="missing required fields"):
            loader.validate_product(product_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
