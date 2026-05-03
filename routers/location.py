from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import uuid

from core.auth import PRODUCTS_SCOPE
from core.deps import get_active_shop, get_db
from models import Shop, Location, ShopLocationPreference
from services.shopify import Operations

router = APIRouter()


# ✅ Request schema
class LocationPreferenceRequest(BaseModel):
    location_ids: List[int]


@router.post("/locations/sync")
def sync_locations(
    request: Request,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db),
):
    try:
        print("SYNC CALLED")

        ops = Operations.from_shop(
            db,
            shop.shop_domain,
            required_scopes=(PRODUCTS_SCOPE,),
            host=request.headers.get("X-Shopify-Host") if request else None,
        )

        query = """
        {
          locations(first: 10) {
            edges {
              node {
                id
                name
              }
            }
          }
        }
        """

        data = ops._graphql(query, {})
        print("RAW DATA:", data)


        locations = data.get("locations", {}).get("edges", [])

        if not locations:
            print("⚠️ No locations returned or wrong response:", data)
            return {
                "status": "empty",
                "count": 0
            }

        print("PARSED LOCATIONS:", locations)

        locations_list = []

        for edge in locations:
            node = edge["node"]

            try:
                location_id = int(node["id"].split("/")[-1])
            except Exception:
                continue

            locations_list.append({
                "id": location_id,
                "shop_id": shop.id,
                "name": node["name"],
            })

        print("INSERTING:", locations_list)

        db.query(Location).filter(
            Location.shop_id == shop.id
        ).delete()

        db.bulk_insert_mappings(
            Location,
            locations_list
        )

        db.commit()

        return {
            "status": "success",
            "count": len(locations),
        }

    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to sync locations")


# 🔹 POST: Set user location preferences
@router.post("/locations/preferences")
def set_location_preferences(
    payload: LocationPreferenceRequest,
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db)
):
    try:
        if not payload.location_ids:
            raise HTTPException(status_code=400, detail="No location_ids provided")

        # ✅ Validate locations belong to this shop
        valid_locations = db.query(Location.id).filter(
            Location.shop_id == shop.id,
            Location.id.in_(payload.location_ids)
        ).all()

        valid_location_ids = {loc[0] for loc in valid_locations}

        if len(valid_location_ids) != len(payload.location_ids):
            raise HTTPException(status_code=400, detail="Invalid location_ids detected")

        # 🧹 Remove old preferences
        db.query(ShopLocationPreference).filter(
            ShopLocationPreference.shop_id == shop.id
        ).delete()

        # ⚡ Insert new preferences
        db.bulk_insert_mappings(
            ShopLocationPreference,
            [
                {
                    "id": uuid.uuid4(),
                    "shop_id": shop.id,
                    "location_id": loc_id
                }
                for loc_id in valid_location_ids
            ]
        )

        db.commit()

        return {
            "status": "success",
            "message": "Location preferences updated",
            "selected_locations": list(valid_location_ids)
        }

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update location preferences")


# 🔹 GET: Fetch user-selected locations
@router.get("/locations/preferences")
def get_location_preferences(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db)
):
    rows = db.query(ShopLocationPreference.location_id).filter(
        ShopLocationPreference.shop_id == shop.id
    ).all()

    return {
        "location_ids": [r[0] for r in rows]
    }


# 🔹 GET: Fetch all available locations for the shop
@router.get("/locations")
def get_locations(
    shop: Shop = Depends(get_active_shop),
    db: Session = Depends(get_db)
):
    locations = db.query(Location).filter(
        Location.shop_id == shop.id
    ).all()

    return [
        {"id": loc.id, "name": loc.name}
        for loc in locations
    ]
