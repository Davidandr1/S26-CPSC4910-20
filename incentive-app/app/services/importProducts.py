import os
import requests
from typing import List, Dict, Optional
from sqlalchemy import text
from app.db import engine
#meant for ebay's product api fyi
class ProductAPIService:
    def __init__(self):
        self.api_key = os.environ.get("EBAY_API_KEY")
        self.api_secret = os.environ.get("EBAY_SECRET_KEY")
        self.base_url = os.environ.get("EBAY_API_BASE_URL", "https://api.ebay.com")

    def get_products(self, query: str, limit: int = 10) -> List[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/products/search",
                params={"q": query, "limit": limit},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json().get("products", [])
        except requests.RequestException as e:
            #we don't wanna return this b/c it may give away errors to bad actors
            raise Exception(f"API Error: {str(e)}")
    def get_product_image(self, product_id: str) -> Optional[str]:
        #not actually sure if we need this but it was trivally easy to request
        try:
            response = requests.get(
                f"{self.base_url}/products/{product_id}/images",
                headers=self._get_headers()
            )
            response.raise_for_status()
            images = response.json().get("images", [])
            return images[0]["url"] if images else None
        except requests.RequestException:
            return None
    
    def get_product_price(self, product_id: str) -> Optional[float]:
        try:
            response = requests.get(
                f"{self.base_url}/products/{product_id}/price",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return float(response.json().get("price", 0))
        except (requests.RequestException, ValueError):
            return None
    
    def convert_price_to_points(self, price: float, sponsor_id: int) -> int:
        with engine.connect() as conn:
            sponsor = conn.execute(
                text("SELECT Sponsor_PointConversion FROM SPONSORS WHERE Sponsor_ID = :sid"),
                {"sid": sponsor_id}
            ).fetchone()
        if not sponsor:
            return 0
        return int(price * sponsor.Sponsor_PointConversion)
    
    def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }