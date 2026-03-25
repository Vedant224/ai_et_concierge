"""
Property-based tests for backend data models and catalog loading
"""
import pytest
import json
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import composite

from core.models import Persona, Product, Message
from core.catalog import CatalogLoader


# Custom strategies
@composite
def persona_strategy(draw):
    """Strategy to generate valid Persona objects"""
    return Persona(
        professional_background=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        financial_goals=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        risk_appetite=draw(st.one_of(
            st.none(),
            st.sampled_from(['conservative', 'moderate', 'aggressive'])
        )),
        interests=draw(st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5))
    )


@composite
def product_strategy(draw):
    """Strategy to generate valid Product objects"""
    return Product(
        id=draw(st.text(alphabet='et-0123456789', min_size=4, max_size=10)),
        name=draw(st.text(min_size=1, max_size=100)),
        description=draw(st.text(min_size=1, max_size=500)),
        target_audience=draw(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5)),
        categories=draw(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5)),
        core_benefit=draw(st.text(min_size=1, max_size=200))
    )


# Property 6: Persona serialization round-trip
class TestPersonaSerialization:
    """Tests for Persona serialization properties"""

    @given(persona_strategy())
    @settings(max_examples=100)
    def test_persona_serialization_roundtrip(self, persona):
        """
        Property: A Persona object serialized to JSON and deserialized
        should be equal to the original.
        
        Validates: Requirements 2.5, 9.5
        """
        # Serialize to JSON dict
        serialized = persona.model_dump(mode='json')
        
        # Deserialize back to Persona
        deserialized = Persona(**serialized)
        
        # Should be equal
        assert deserialized == persona
        assert deserialized.model_dump() == persona.model_dump()

    @given(persona_strategy())
    @settings(max_examples=100)
    def test_persona_json_string_roundtrip(self, persona):
        """
        Property: A Persona object should survive round-trip through JSON string.
        
        Validates: Requirements 2.5
        """
        # Serialize to JSON string
        json_str = persona.model_dump_json()
        
        # Deserialize from JSON string
        deserialized = Persona.model_validate_json(json_str)
        
        # Should be equal
        assert deserialized == persona

    @given(persona_strategy())
    @settings(max_examples=100)
    def test_persona_is_sufficient_for_matching(self, persona):
        """
        Property: is_sufficient_for_matching() should return True if and only if
        at least one field is populated.
        
        Validates: Requirements 2.1
        """
        is_sufficient = persona.is_sufficient_for_matching()
        
        has_data = any([
            persona.professional_background,
            persona.financial_goals,
            persona.risk_appetite,
            persona.interests
        ])
        
        assert is_sufficient == has_data


# Property 20 & 21: Catalog loading validation
class TestCatalogLoading:
    """Tests for catalog loading properties"""

    @given(st.lists(product_strategy(), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_valid_catalog_loading(self, products):
        """
        Property 20: A valid catalog with proper JSON structure
        should load successfully and return all products.
        
        Validates: Requirements 9.2, 9.4
        """
        # Create temporary catalog file
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "test_catalog.json"
            
            # Prepare catalog data
            catalog_data = {
                "products": [p.model_dump() for p in products]
            }
            
            # Write to file
            with open(catalog_path, 'w') as f:
                json.dump(catalog_data, f)
            
            # Load catalog
            loader = CatalogLoader(str(catalog_path))
            loaded_products = loader.load()
            
            # Verify all products loaded
            assert len(loaded_products) == len(products)
            
            # Verify each product matches
            for original, loaded in zip(products, loaded_products):
                assert loaded.id == original.id
                assert loaded.name == original.name
                assert loaded.description == original.description

    def test_catalog_missing_file(self):
        """
        Property 21: Loading from a non-existent file should raise FileNotFoundError.
        
        Validates: Requirements 9.2, 9.3
        """
        loader = CatalogLoader("/nonexistent/path/catalog.json")
        
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_catalog_invalid_json(self):
        """
        Property 21: Loading from a file with invalid JSON should raise JSONDecodeError.
        
        Validates: Requirements 9.2, 9.3
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "bad_catalog.json"
            
            # Write invalid JSON
            with open(catalog_path, 'w') as f:
                f.write("{ invalid json")
            
            loader = CatalogLoader(str(catalog_path))
            
            with pytest.raises(json.JSONDecodeError):
                loader.load()

    def test_catalog_missing_products_key(self):
        """
        Property 21: Catalog without 'products' key should raise ValueError.
        
        Validates: Requirements 9.2, 9.4
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "bad_catalog.json"
            
            # Write JSON without products key
            catalog_data = {"items": []}
            with open(catalog_path, 'w') as f:
                json.dump(catalog_data, f)
            
            loader = CatalogLoader(str(catalog_path))
            
            with pytest.raises(ValueError, match="'products' key"):
                loader.load()

    def test_catalog_product_missing_required_field(self):
        """
        Property 21: Product missing required field should raise ValueError.
        
        Validates: Requirements 9.2, 9.3, 9.4
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "bad_catalog.json"
            
            # Write catalog with incomplete product
            catalog_data = {
                "products": [
                    {
                        "id": "et-001",
                        "name": "Test Product"
                        # Missing other required fields
                    }
                ]
            }
            with open(catalog_path, 'w') as f:
                json.dump(catalog_data, f)
            
            loader = CatalogLoader(str(catalog_path))
            
            with pytest.raises(ValueError, match="missing required fields"):
                loader.load()

    def test_get_product_by_id(self):
        """
        Test that get_product_by_id works correctly.
        
        Validates: Requirements 9.1
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "test_catalog.json"
            
            catalog_data = {
                "products": [
                    {
                        "id": "et-001",
                        "name": "Product 1",
                        "description": "Test product 1",
                        "target_audience": ["Investors"],
                        "categories": ["Growth"],
                        "core_benefit": "Growth potential"
                    },
                    {
                        "id": "et-002",
                        "name": "Product 2",
                        "description": "Test product 2",
                        "target_audience": ["Conservative"],
                        "categories": ["Income"],
                        "core_benefit": "Stable income"
                    }
                ]
            }
            
            with open(catalog_path, 'w') as f:
                json.dump(catalog_data, f)
            
            loader = CatalogLoader(str(catalog_path))
            loader.load()
            
            # Test retrieval
            product = loader.get_product_by_id("et-001")
            assert product.name == "Product 1"
            
            # Test non-existent product
            with pytest.raises(ValueError, match="not found"):
                loader.get_product_by_id("et-999")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
