from sqlalchemy.orm import Session
from sqlalchemy import text
import csv
import io


def csv_maker(result) -> str:
    rows = result.fetchall()
    columns = result.keys()
    # Build CSV
    output = io.StringIO() 
    writer = csv.writer(output)
    writer.writerow(columns)    
    writer.writerows(rows)
    return output.getvalue()

def forecast_all_items(
    database: Session,
    restock_days: int,
    sales_duration: int,
    minimum_value: int,
    shop_id: str
):
    """
    Forecast restock amounts and classify item velocity.
    Returns a list of dictionaries ready for JSON response.
    """

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
            price,

            CASE
                WHEN net_items_sold = 0 THEN NULL
                ELSE ROUND(
                    inventory / (net_items_sold::numeric / :sales_duration),
                    2
                )
            END AS lifetime,

            net_items_sold::float / :sales_duration AS sales_per_day

        FROM main
        WHERE sku IS NOT NULL
    ),

    restock_table AS (
        SELECT
            *,
            CASE
                WHEN net_items_sold = 0 THEN :minimum_value
                ELSE GREATEST(
                    (sales_per_day * :restock_days),
                    :minimum_value
                )
            END AS restock_amount
        FROM cte3
    ),

    ranked AS (
        SELECT
            *,
            PERCENT_RANK() OVER (ORDER BY sales_per_day) AS velocity_percentile
        FROM restock_table
    )

    SELECT
        title,
        size,
        sku,
        lifetime,
        sales_per_day,

        CASE
            WHEN inventory = 0 AND net_items_sold > 0 THEN 'stock_out'
            WHEN net_items_sold = 0 THEN 'never_sold'
            WHEN velocity_percentile >= 0.8 THEN 'fast_moving'
            WHEN velocity_percentile >= 0.5 THEN 'moderate'
            ELSE 'slow_moving'
        END AS status,

        ROUND(restock_amount ::numeric,2) AS restock_amount

    FROM ranked
    ORDER BY sales_per_day DESC
    """)

    result = database.execute(
        sql,
        {
            "shop_id": shop_id,
            "sales_duration": sales_duration,
            "restock_days": restock_days,
            "minimum_value": minimum_value
        }
    )

    rows = result.mappings().all()
    return rows

from sqlalchemy import text

def forecast_items(
    database: Session,
    items: list,
    shop_id: int,
    restock_days: int,
    sales_duration: int,
    minimum_value: int
):

    sql = text("""
    WITH sales2 AS (
        SELECT
            shop_id,
            title,
            size,
            sku,
            SUM(quantity_sold) AS net_items_sold
        FROM sales
        WHERE shop_id = :shop_id
        GROUP BY shop_id, title, size, sku
    ),

    main AS (
        SELECT
            i.title,
            i.size,
            i.sku,
            i.inventory,
            i.shop_id,
            COALESCE(s.net_items_sold, 0) AS net_items_sold
        FROM inventory i
        LEFT JOIN sales2 s
            ON i.sku = s.sku
           AND i.shop_id = s.shop_id
        WHERE i.shop_id = :shop_id
        AND i.title IN :items
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
                    (inventory * :sales_duration) / net_items_sold,
                    2
                )
            END AS lifetime,

            net_items_sold::float / :sales_duration AS sales_per_day

        FROM main
    ),

    restock_table AS (
        SELECT
            *,
            CASE
                WHEN net_items_sold = 0 THEN :minimum_value
                ELSE GREATEST(
                    (sales_per_day * :restock_days),
                    :minimum_value
                )
            END AS restock_amount
        FROM cte3
    )

    SELECT
        title,
        ROUND(SUM(restock_amount)::numeric, 2) AS total_restock_amount
    FROM restock_table
    GROUP BY title
    ORDER BY total_restock_amount DESC
    """)

    result = database.execute(
        sql,
        {
            "shop_id": shop_id,
            "sales_duration": sales_duration,
            "restock_days": restock_days,
            "minimum_value": minimum_value,
            "items": tuple(items)
        }
    )

    rows = result.mappings().all()
    return rows

def items_breakdown(database: Session,
                    shop_id: str , 
                    restock_days: int, 
                    sales_duration: int) -> str:
    
    sql = text("""
    WITH sales2 AS (
    SELECT
            title,
            size,
            sku,
            shop_id,
            SUM(quantity_sold) AS net_items_sold
        FROM sales
        WHERE shop_id = :shop_id 
        GROUP BY title, size, sku, shop_id
    ),

    main AS (
        SELECT
            i.title,
            i.size,
            i.sku,
            i.inventory,
            i.shop_id,
            COALESCE(s.net_items_sold, 0) AS net_items_sold
        FROM inventory i
        LEFT JOIN sales2 s
            ON i.sku = s.sku
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
                WHEN net_items_sold = 0 THEN inventory
                ELSE ROUND(
                    inventory / (net_items_sold::numeric / :sales_duration),
                    2
                )
            END AS lifetime
        FROM main
    ),

    filtered_titles AS (
        SELECT title
        FROM cte3
        GROUP BY title
        HAVING AVG(lifetime) < 15
    ),

    tablex AS (
        SELECT c.*
        FROM cte3 c
        JOIN filtered_titles f
            ON c.title = f.title
    ),

    restock_table AS (
        SELECT
            title,
            size,
            sku,
            lifetime,
            inventory,
            net_items_sold,
            CASE
                WHEN net_items_sold <= 0 THEN :restock_days
                ELSE (net_items_sold::numeric / :sales_duration) * :restock_days
            END AS restock_amount
        FROM tablex)
        SELECT title ,sum(net_items_sold) AS total_net_items_sold FROM restock_table 
        where sku is not null
        group by title
        order by total_net_items_sold desc;
    """)
    result = database.execute(
        sql,
        {
            "shop_id": shop_id,
            "sales_duration": sales_duration,
            "restock_days": restock_days, 
            
        }
    )
    rows = result.mappings().all()
    return rows
