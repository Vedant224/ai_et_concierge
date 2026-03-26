from typing import List, Tuple
from core.models import Persona, Product


class ProductMatcher:
    """
    Matches users to appropriate products based on their persona.
    Returns 1-2 recommendations per conversation turn.
    """
    
    def __init__(self, products: List[Product]):
        """
        Initialize ProductMatcher with catalog.
        
        Args:
            products: List of Product objects to match against
        """
        self.products = products
    
    def match(self, persona: Persona) -> List[Product]:
        """
        Find 1-2 products that best match the user's persona.
        
        Args:
            persona: User's extracted persona
            
        Returns:
            List of 1-2 matching Product objects
        """
        if not self.products:
            return []
        
        # Calculate relevance scores for all products
        scored_products = []
        for product in self.products:
            score = self.calculate_relevance_score(persona, product)
            if score > 0:
                scored_products.append((product, score))
        
        # Sort by score (descending)
        scored_products.sort(key=lambda x: x[1], reverse=True)
        
        # Return top 1-2 products
        if not scored_products:
            # If no good matches, return the product with broadest audience
            return [self._get_broadest_product()]
        
        # Return 1 or 2 products
        num_products = min(2, len(scored_products))
        return [product for product, score in scored_products[:num_products]]
    
    def calculate_relevance_score(self, persona: Persona, product: Product) -> float:
        """
        Calculate how relevant a product is to a user's persona.
        
        Args:
            persona: User's persona
            product: Product to score
            
        Returns:
            Score between 0 and 1
        """
        score = 0.0
        max_score = 0.0
        
        # Check professional background alignment
        if persona.professional_background and product.target_audience:
            max_score += 0.25
            if any(
                persona.professional_background.lower() in aud.lower()
                for aud in product.target_audience
            ):
                score += 0.25
        
        # Check financial goals alignment
        if persona.financial_goals and product.core_benefit:
            max_score += 0.25
            goals_lower = persona.financial_goals.lower()
            benefit_lower = product.core_benefit.lower()
            
            # Check for goal-benefit alignment
            goal_keywords = goals_lower.split()
            benefit_keywords = benefit_lower.split()
            
            matches = any(
                gk in benefit_lower or bk in goals_lower
                for gk in goal_keywords
                for bk in benefit_keywords
            )
            
            if matches:
                score += 0.25
        
        # Check interests alignment
        if persona.interests and product.categories:
            max_score += 0.25
            interest_matches = sum(
                1 for interest in persona.interests
                if any(interest.lower() in cat.lower() for cat in product.categories)
            )
            
            if interest_matches > 0:
                score += 0.25 * min(interest_matches / len(persona.interests), 1.0)
        
        # Check risk appetite alignment
        if persona.risk_appetite and product.categories:
            max_score += 0.25
            risk_lower = persona.risk_appetite.lower()
            categories_lower = [c.lower() for c in product.categories]
            
            risk_category_map = {
                'conservative': ['conservative', 'bonds', 'fixed income', 'dividend'],
                'moderate': ['balanced', 'diversified', 'mixed', 'moderate'],
                'aggressive': ['growth', 'equity', 'tech', 'emerging']
            }
            
            if risk_lower in risk_category_map:
                expected_categories = risk_category_map[risk_lower]
                if any(
                    any(ec in category for category in categories_lower)
                    for ec in expected_categories
                ):
                    score += 0.25
        
        # Normalize score
        if max_score > 0:
            return score / max_score
        
        return 0.0
    
    def _get_broadest_product(self) -> Product:
        """
        Find the product with broadest target audience.
        Used as fallback when no good matches found.
        
        Returns:
            Product object
        """
        if not self.products:
            raise ValueError("No products available")
        
        return max(
            self.products,
            key=lambda p: len(p.target_audience)
        )
    
    def get_top_n_products(self, persona: Persona, n: int = 5) -> List[Tuple[Product, float]]:
        """
        Get top N products with scores for a persona.
        Useful for debugging and analysis.
        
        Args:
            persona: User's persona
            n: Number of top products to return
            
        Returns:
            List of (Product, score) tuples
        """
        scored = [
            (product, self.calculate_relevance_score(persona, product))
            for product in self.products
        ]
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]
