import os
import requests
from typing import List, Dict, Optional
from sqlalchemy import text
from app.db import engine
import base64

class ProductAPIService:
    def __init__(self):
        self.base_url = os.environ.get("EBAY_API_BASE_URL", "https://api.ebay.com")
        client_id = os.environ.get("EBAY_CLIENT_ID", "")
        client_secret = os.environ.get("EBAY_CLIENT_SECRET", "")
        credentials = f"{client_id}:{client_secret}"
        self.encoded_credentials = base64.b64encode(credentials.encode()).decode()

    def get_products(self, query: str, limit: int = 10) -> List[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/buy/browse/v1/item_summary/search",
                params={"q": query, "limit": limit},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json().get("itemSummaries", [])
        except requests.RequestException as e:
            #we don't wanna return this b/c it may give away errors to bad actors
            raise Exception(f"API Error: {str(e)}")

    def get_product_image(self, product_id: str) -> Optional[str]:
        #not actually sure if we need this but it was trivally easy to request
        try:
            response = requests.get(
                f"{self.base_url}/buy/browse/v1/item/{product_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            images = response.json().get("image", {}).get("imageUrl")
            return images if images else None
        except requests.RequestException:
            return None

    def get_product_price(self, product_id: str) -> Optional[float]:
        try:
            response = requests.get(
                f"{self.base_url}/buy/browse/v1/item/{product_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            price = response.json().get("price", {}).get("value")
            return float(price) if price else None
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
            "Authorization": f"Basic {self.encoded_credentials}",
            "Content-Type": "application/json"
        }