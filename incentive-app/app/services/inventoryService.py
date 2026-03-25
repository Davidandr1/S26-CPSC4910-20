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
                    WHERE Sponsor_ID = :sid AND Prod_SKU = :ext_id
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
                conversion_rate = float(sponsor.Sponsor_PointConversion or 0)
                formatted_price = float(product_data["price"])
                point_value = int(formatted_price / conversion_rate) if conversion_rate else 0

                result = conn.execute(
                    text("""
                        INSERT INTO INVENTORY 
                        (Prod_SKU, Item_Name, Prod_Description, Prod_Quantity, 
                         Prod_UnitPrice, Sponsor_ID, Product_Image_URL, Prod_Category, Point_Value)
                        VALUES (:sku, :name, :desc, 100, :price, :sid, :img_url, :category, :point_value)
                    """),
                    {
                        "sku": product_data.get("external_id"),
                        "name": product_data["name"],
                        "desc": product_data["description"],
                        "price": product_data["price"],
                        "sid": sponsor_id,
                        "img_url": product_data.get("image"),
                        "category": product_data.get("category", ""),
                        "point_value": point_value
                    }
                )
                return result.lastrowid
        except Exception as e:
            raise Exception(f"Error adding product: {str(e)}")
        

    @staticmethod
    def delete_product(sponsor_id: int, product_id: int) -> bool:
        try:
            with engine.begin() as conn:
                result = conn.execute(
                    text("DELETE FROM INVENTORY WHERE Item_ID = :pid AND Sponsor_ID = :sid"),
                    {"pid": product_id, "sid": sponsor_id}
                )
                return result.rowcount > 0
        except Exception as e:
            raise Exception(f"Error deleting product: {str(e)}")