import time
from datetime import date, timedelta, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.deps import get_db

from models import Shop, Notification, Sales

from services.shopify import Operations
from services.notification_engine import low_stock_items
from services.inventory_repo import get_sales_period
from services.transformation import csv_maker
from services.email_service import send_email_with_csv


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/weekly-notifications")
def weekly_notifications(db: Session = Depends(get_db)):

    notifications = (
        db.query(Notification)
        .filter(Notification.is_active == True)
        .all()
    )

    print(f"[CRON] Found {len(notifications)} active notifications")

    for notif in notifications:
        try:
            print(f"[CRON] Processing {notif.email}")

            # Anti-spam check
            if notif.last_sent_at:
                if datetime.now(timezone.utc) - notif.last_sent_at < timedelta(days=6):
                    print("[CRON] Skipped (recently sent)")
                    continue

            # Get shop
            shop = db.query(Shop).filter(Shop.id == notif.shop_id).first()
            if not shop:
                print("[CRON] Shop not found")
                continue

            # Last 10 full days
            end_date = date.today() - timedelta(days=1)
            start_date = end_date - timedelta(days=9)

            print(f"[CRON] Syncing sales from {start_date} to {end_date}")

            ops = Operations(shop.shop_domain, shop.access_token)

            # Delete old sales
            ops.delete_sales(shop.id, db)
            db.commit()

            # Fetch and insert new sales
            rows = ops.get_sales(start_date, end_date)
            sales_rows = [{"shop_id": shop.id, **row} for row in rows]

            if not sales_rows:
                print("[CRON] No sales returned")
                continue

            db.bulk_insert_mappings(Sales, sales_rows)
            db.commit()

            print(f"[CRON] Inserted {len(sales_rows)} sales rows")

            time.sleep(1)

            # Get sales duration
            sales_period = get_sales_period(db, shop.id)

            if not sales_period:
                print("[CRON] No sales period found")
                continue

            if isinstance(sales_period, dict):
                min_date = sales_period.get("min_sales_date")
                max_date = sales_period.get("max_sales_date")

                if not min_date or not max_date:
                    print("[CRON] Invalid sales period")
                    continue

                sales_duration = (max_date - min_date).days
            else:
                sales_duration = sales_period

            if not sales_duration or sales_duration <= 0:
                print("[CRON] Invalid sales duration")
                continue

            # Get low stock items
            items = low_stock_items(
                shop_id=str(shop.id),
                threshold_number=notif.threshold_days,
                db=db,
                sales_duration=sales_duration
            )

            if not items:
                print("[CRON] No low stock items")
                continue

            print(f"[CRON] Found {len(items)} low stock items")

            # Generate CSV
            csv_file = csv_maker(items)

            # Send email
            send_email_with_csv(
                to_email=notif.email,
                subject="Merchy Weekly Stock Alert",
                csv_file=csv_file,
                shop_domain=shop.shop_domain
            )

            # Update last sent
            notif.last_sent_at = datetime.now(timezone.utc)
            db.commit()

            print("[CRON] Email sent successfully")

            time.sleep(2)

        except Exception as e:
            db.rollback()
            print(f"[CRON][ERROR] {notif.email}: {str(e)}")
            continue

    return {"status": "completed"}