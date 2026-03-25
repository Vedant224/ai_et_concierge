"""
Catalog loading functionality for ET products
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from .models import Product


class CatalogLoader:
    """Loads and manages the ET product catalog"""

    def __init__(self, catalog_path: str = None):
        """
        Initialize CatalogLoader with optional catalog path.
        
        Args:
            catalog_path: Path to the et_catalog.json file. 
                         If None, uses default location.
        """
        if catalog_path is None:
            # Default to data/et_catalog.json relative to this file
            catalog_path = Path(__file__).parent.parent / "data" / "et_catalog.json"
        else:
            catalog_path = Path(catalog_path)
        
        self.catalog_path = catalog_path
        self.products: List[Product] = []

    def load(self) -> List[Product]:
        """
        Load and parse the ET catalog from JSON file.
        
        Returns:
            List[Product]: List of loaded Product objects
            
        Raises:
            FileNotFoundError: If catalog file does not exist
            json.JSONDecodeError: If catalog JSON is invalid
            ValueError: If catalog data is invalid
        """
        if not self.catalog_path.exists():
            raise FileNotFoundError(
                f"Catalog file not found at {self.catalog_path}"
            )

        try:
            with open(self.catalog_path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in catalog file: {str(e)}", 
                e.doc, 
                e.pos
            )

        if not isinstance(data, dict) or 'products' not in data:
            raise ValueError(
                "Catalog must contain a 'products' key with list of products"
            )

        products_data = data['products']
        if not isinstance(products_data, list):
            raise ValueError("'products' key must contain a list")

        self.products = []
        for product_data in products_data:
            self.validate_product(product_data)
            product = Product(**product_data)
            self.products.append(product)

        return self.products

    def validate_product(self, product_data: Dict[str, Any]) -> bool:
        """
        Validate that product data contains all required fields.
        
        Args:
            product_data: Dictionary containing product information
            
        Returns:
            bool: True if product is valid
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        required_fields = ['id', 'name', 'description', 'target_audience', 
                          'categories', 'core_benefit']
        
        missing_fields = [field for field in required_fields 
                         if field not in product_data]
        
        if missing_fields:
            raise ValueError(
                f"Product missing required fields: {', '.join(missing_fields)}"
            )

        # Validate field types
        if not isinstance(product_data.get('id'), str):
            raise ValueError("'id' must be a string")
        
        if not isinstance(product_data.get('name'), str):
            raise ValueError("'name' must be a string")
        
        if not isinstance(product_data.get('description'), str):
            raise ValueError("'description' must be a string")
        
        if not isinstance(product_data.get('target_audience'), list):
            raise ValueError("'target_audience' must be a list")
        
        if not isinstance(product_data.get('categories'), list):
            raise ValueError("'categories' must be a list")
        
        if not isinstance(product_data.get('core_benefit'), str):
            raise ValueError("'core_benefit' must be a string")

        return True

    def get_products(self) -> List[Product]:
        """
        Get the loaded products.
        
        Returns:
            List[Product]: List of loaded Product objects
        """
        return self.products

    def get_product_by_id(self, product_id: str) -> Product:
        """
        Get a specific product by ID.
        
        Args:
            product_id: The ID of the product to retrieve
            
        Returns:
            Product: The matching product
            
        Raises:
            ValueError: If product is not found
        """
        for product in self.products:
            if product.id == product_id:
                return product
        
        raise ValueError(f"Product with ID '{product_id}' not found in catalog")
