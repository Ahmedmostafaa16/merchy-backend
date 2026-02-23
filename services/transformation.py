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
    shop_id: str
) -> str:
    """
    Execute restock calculation query for a specific brand
    and return result as CSV string.
    """

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
        FROM tablex
    )

    SELECT
        title,
        ROUND(SUM(restock_amount), 2) AS total_restock_amount
    FROM restock_table
    GROUP BY title
    ORDER BY total_restock_amount DESC;
    """)

    result = database.execute(
        sql,
        {
            "shop_id": shop_id,
            "sales_duration": sales_duration,
            "restock_days": restock_days
        }
    )

    return result


def forecast_items(database: Session,items : list, shop_id: int , restock_days: int, sales_duration: int) -> str:
    
    """
    Execute restock calculation query for a specific brand
    and return result as CSV string.
    """
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
        WHERE i.shop_id = :shop_id and i.title IN :items
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
        FROM tablex
    )

    SELECT
        title,
        ROUND(SUM(restock_amount), 2) AS total_restock_amount
    FROM restock_table
    GROUP BY title
    ORDER BY total_restock_amount DESC;
    """)
    result = database.execute(
        sql,
        {
            "shop_id": shop_id,
            "sales_duration": sales_duration,
            "restock_days": restock_days,
            "items": tuple(items)
        }
    )
    
    return result

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
        SELECT * FROM restock_table 
        where sku is not null
        order by net_items_sold desc;
    """)
    result = database.execute(
        sql,
        {
            "shop_id": shop_id,
            "sales_duration": sales_duration,
            "restock_days": restock_days,
            
        }
    )
    return [dict(row._mapping) for row in result]
