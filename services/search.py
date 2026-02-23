from sqlalchemy.orm import Session
from models import Inventory


def search_inventory(db, shop_id, search_query):
    results = (
        db.query(Inventory.title)
        .filter(Inventory.shop_id == shop_id)
        .filter(Inventory.title.ilike(f"%{search_query}%"))
        .distinct()
        .limit(10)
        .all()
    )

    return [{"title": row.title} for row in results]
