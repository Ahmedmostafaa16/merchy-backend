from sqlalchemy.orm import Session
from sqlalchemy import text


def low_stock_items(
    shop_id: str,
    threshold_number: int,
    db: Session,
    sales_duration: int
):

    sql = text("""
        WITH sales2 AS (
            SELECT 
                shop_id,
                title,
                size,
                color,
                sku,
                SUM(quantity_sold) AS net_items_sold
            FROM sales
            WHERE shop_id = :shop_id
            GROUP BY shop_id, title, size, color, sku
        ),

        main AS (
            SELECT
                i.title,
                i.size,
                i.sku,
                i.inventory,
                i.shop_id,
                i.price,
                COALESCE(s.net_items_sold, 0) AS net_items_sold
            FROM inventory i
            LEFT JOIN sales2 s
                ON i.sku = s.sku
            AND i.shop_id = s.shop_id
            WHERE i.shop_id = :shop_id
        ),

        cte3 AS (
            SELECT
                title,
                size,
                sku,
                inventory,
                shop_id,
                net_items_sold,
                
                CASE
                    WHEN net_items_sold = 0 THEN NULL
                    ELSE ROUND(
                        inventory / (net_items_sold::numeric / :sales_duration),
                        2
                    )
                END AS lifetime

            FROM main
            WHERE sku IS NOT NULL
        )
        
        SELECT title, size, sku, inventory, lifetime 
        FROM cte3 
        WHERE lifetime IS NOT NULL
        AND lifetime < :threshold_number
        ORDER BY lifetime ASC
        
    """)

    result = db.execute(
        sql,
        {
            "shop_id": shop_id,
            "threshold_number": threshold_number,
            "sales_duration": sales_duration
        }
    ).fetchall()

    return [dict(row._mapping) for row in result]