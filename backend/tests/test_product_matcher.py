import pytest
from hypothesis import given, strategies as st
from core.models import Persona, Product
from core.product_matcher import ProductMatcher


class TestProductMatcher:
    """Unit tests for ProductMatcher"""
    
    @pytest.fixture
    def sample_products(self):
        """Create sample products for testing"""
        return [
            Product(
                id="et-001",
                name="Growth Fund",
                description="High growth potential",
                target_audience=["Young professionals", "Growth investors"],
                categories=["Equity", "Growth"],
                core_benefit="Capital appreciation"
            ),
            Product(
                id="et-002",
                name="Conservative Bond Fund",
                description="Low risk bonds",
                target_audience=["Retirees", "Conservative investors"],
                categories=["Fixed Income", "Bonds", "Conservative"],
                core_benefit="Stable income with low volatility"
            ),
            Product(
                id="et-003",
                name="Tech Portfolio",
                description="Technology focused",
                target_audience=["Tech investors", "Growth seekers"],
                categories=["Technology", "Growth", "Innovation"],
                core_benefit="Exposure to technology sector"
            ),
            Product(
                id="et-004",
                name="Dividend Fund",
                description="Dividend paying stocks",
                target_audience=["Income investors", "Conservative investors"],
                categories=["Dividends", "Income"],
                core_benefit="Regular dividend income"
            ),
        ]
    
    def test_match_growth_investor(self, sample_products):
        """Test matching growth-oriented investor"""
        matcher = ProductMatcher(sample_products)
        
        persona = Persona(
            professional_background="Software Engineer",
            financial_goals="Long-term capital growth",
            risk_appetite="aggressive",
            interests=["Technology", "Growth"]
        )
        
        matches = matcher.match(persona)
        
        # Should return 1-2 products
        assert 1 <= len(matches) <= 2
        # Should prioritize tech/growth products
        assert any("growth" in m.name.lower() or "tech" in m.name.lower() for m in matches)
    
    def test_match_conservative_investor(self, sample_products):
        """Test matching conservative investor"""
        matcher = ProductMatcher(sample_products)
        
        persona = Persona(
            professional_background="Retiree",
            financial_goals="Income generation",
            risk_appetite="conservative",
            interests=["Income", "Safety"]
        )
        
        matches = matcher.match(persona)
        
        # Should return 1-2 products
        assert 1 <= len(matches) <= 2
        # Should prioritize conservative/income products
        product_names = [m.name.lower() for m in matches]
        assert any("conservative" in name or "bond" in name or "dividend" in name for name in product_names)
    
    def test_match_empty_portfolio(self):
        """Test matching with no products available"""
        matcher = ProductMatcher([])
        
        persona = Persona(interests=["Growth"])
        matches = matcher.match(persona)
        
        assert matches == []
    
    def test_match_empty_persona(self, sample_products):
        """Test matching with minimal persona info"""
        matcher = ProductMatcher(sample_products)
        
        # Empty persona - should fall back to broadest product
        persona = Persona()
        matches = matcher.match(persona)
        
        # Should still return product(s)
        assert len(matches) > 0
        assert len(matches) <= 2
    
    def test_calculate_relevance_score(self, sample_products):
        """Test relevance score calculation"""
        matcher = ProductMatcher(sample_products)
        
        growth_fund = sample_products[0]
        tech_fund = sample_products[2]
        
        persona = Persona(
            professional_background="Software Engineer",
            interests=["Technology", "Growth"],
            risk_appetite="aggressive"
        )
        
        growth_score = matcher.calculate_relevance_score(persona, growth_fund)
        tech_score = matcher.calculate_relevance_score(persona, tech_fund)
        
        # Scores should be between 0 and 1
        assert 0 <= growth_score <= 1
        assert 0 <= tech_score <= 1
        
        # Tech fund should score higher for tech-interested investor
        assert tech_score >= growth_score
    
    def test_match_count_constraint(self, sample_products):
        """
        Property 8: Product match count constraint
        Match() always returns 1-2 products
        """
        matcher = ProductMatcher(sample_products)
        
        personas = [
            Persona(professional_background="Engineer", interests=["Tech"]),
            Persona(risk_appetite="conservative", interests=["Income"]),
            Persona(financial_goals="Growth", interests=["Growth", "Equity"]),
            Persona(),  # Empty persona
        ]
        
        for persona in personas:
            matches = matcher.match(persona)
            assert 1 <= len(matches) <= 2, f"Expected 1-2 matches, got {len(matches)}"
    
    def test_get_top_n_products(self, sample_products):
        """Test getting top N products with scores"""
        matcher = ProductMatcher(sample_products)
        
        persona = Persona(
            interests=["Technology", "Growth"],
            risk_appetite="aggressive"
        )
        
        top_3 = matcher.get_top_n_products(persona, 3)
        
        # Should return up to 3 products
        assert len(top_3) <= 3
        
        # Each item should be (Product, score) tuple
        for product, score in top_3:
            assert isinstance(product, Product)
            assert 0 <= score <= 1
        
        # Scores should be in descending order
        scores = [score for _, score in top_3]
        assert scores == sorted(scores, reverse=True)


# Property-based tests

@given(
    interests=st.lists(st.text(min_size=1, max_size=20), max_size=3),
)
def test_match_returns_valid_count(interests):
    """
    Property: match() always returns exactly 1-2 products.
    Validates: Requirement 3.3
    """
    # Create minimal product catalog
    products = [
        Product(
            id="p1",
            name="Product 1",
            description="Description 1",
            target_audience=["Everyone"],
            categories=["General"],
            core_benefit="Benefit 1"
        ),
        Product(
            id="p2",
            name="Product 2",
            description="Description 2",
            target_audience=["Everyone"],
            categories=["General"],
            core_benefit="Benefit 2"
        ),
    ]
    
    matcher = ProductMatcher(products)
    persona = Persona(interests=interests if interests else None)
    
    matches = matcher.match(persona)
    
    # MUST be 1-2 products
    assert 1 <= len(matches) <= 2
    
    # All matches should be Product instances
    assert all(isinstance(m, Product) for m in matches)


def test_relevance_score_respects_persona_attributes():
    """Test that relevance score considers all persona attributes"""
    products = [
        Product(
            id="tech-growth",
            name="Tech Growth Fund",
            description="Technology focus",
            target_audience=["Tech professionals", "Growth investors"],
            categories=["Technology", "Growth", "Equity"],
            core_benefit="High growth potential in tech sector"
        ),
    ]
    
    matcher = ProductMatcher(products)
    product = products[0]
    
    # Persona with matching attributes should score high
    matching_persona = Persona(
        professional_background="Software Engineer",
        financial_goals="Long-term growth",
        risk_appetite="aggressive",
        interests=["Technology", "Growth"]
    )
    
    # Persona with no matching attributes should score lower
    non_matching_persona = Persona(
        professional_background="Accountant",
        financial_goals="Income",
        risk_appetite="conservative",
        interests=["Bonds", "Dividends"]
    )
    
    matching_score = matcher.calculate_relevance_score(matching_persona, product)
    non_matching_score = matcher.calculate_relevance_score(non_matching_persona, product)
    
    # Matching should score higher
    assert matching_score > non_matching_score
