from sqlalchemy import text
from app.db import engine
from typing import Dict

class InventoryService:
    
    @staticmethod
    def product_exists(sponsor_id: int, external_product_id: str) -> bool:
        with engine.connect() as conn:
            existing = conn.execute(
                text("""
                    SELECT Item_ID FROM INVENTORY 
                    WHERE Sponsor_ID = :sid AND External_Product_ID = :ext_id
                """),
                {"sid": sponsor_id, "ext_id": external_product_id}
            ).fetchone()
        return existing is not None
    
    @staticmethod
    def add_product(sponsor_id: int, product_data: Dict) -> int:
        #can provide null images for products with no image!!! please be aware!
        if InventoryService.product_exists(sponsor_id, product_data["external_id"]):
            raise ValueError(f"Product {product_data['name']} already in your catalog")
        
        try:
            with engine.begin() as conn:
                # Get sponsor's point conversion rate
                sponsor = conn.execute(
                    text("SELECT Sponsor_PointConversion FROM SPONSORS WHERE Sponsor_ID = :sid"),
                    {"sid": sponsor_id}
                ).fetchone()
                
                if not sponsor:
                    raise ValueError("Sponsor not found")
                
                # Convert price to points
                point_value = int(product_data["price"] * sponsor.Sponsor_PointConversion)
                
                result = conn.execute(
                    text("""
                        INSERT INTO INVENTORY 
                        (Prod_SKU, Item_Name, Prod_Description, Prod_Quantity, 
                         Prod_UnitPrice, Sponsor_ID, Product_Image_URL, External_Product_ID, Point_Value)
                        VALUES (:sku, :name, :desc, 100, :price, :sid, :img_url, :ext_id, :pts)
                    """),
                    {
                        "sku": product_data.get("external_id"),
                        "name": product_data["name"],
                        "desc": product_data["description"],
                        "price": product_data["price"],
                        "sid": sponsor_id,
                        "img_url": product_data.get("image"),
                        "ext_id": product_data["external_id"],
                        "pts": point_value
                    }
                )
                return result.lastrowid
        except Exception as e:
            raise Exception(f"Error adding product: {str(e)}")