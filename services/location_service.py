from models import ShopLocationPreference
from sqlalchemy.orm import Session


def set_shop_locations(db: Session, shop_id, location_ids: list[int]):
    db.query(ShopLocationPreference).filter(
        ShopLocationPreference.shop_id == shop_id
    ).delete()

    db.bulk_insert_mappings(
        ShopLocationPreference,
        [{"shop_id": shop_id, "location_id": lid} for lid in location_ids]
    )

    db.commit()

def get_shop_locations(db: Session, shop_id):
    rows = db.query(ShopLocationPreference.location_id).filter(
        ShopLocationPreference.shop_id == shop_id
    ).all()

    return [r[0] for r in rows]

