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

                net_items_sold::numeric / :sales_duration AS sales_per_day

            FROM main
            WHERE sku IS NOT NULL
        ),

        restock_table AS (
            SELECT
                *,
                CASE
                    WHEN net_items_sold = 0 THEN :minimum_value
                    ELSE GREATEST(
                        ((sales_per_day * :restock_days) - inventory),
                        0
                    )
                END AS restock_amount
            FROM cte3
        ),

        quartiles AS (
            SELECT
                percentile_cont(0.50) WITHIN GROUP (ORDER BY sales_per_day) AS q2,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY sales_per_day) AS q3
            FROM restock_table
            where net_items_sold > 0
        )

        SELECT
            r.title,
            r.size,
            r.sku,
            r.lifetime,
            ROUND(r.sales_per_day,2) AS sales_per_day,
            r.inventory,

            CASE
                WHEN r.net_items_sold = 0 THEN 'never sold'
                WHEN r.inventory = 0 AND r.net_items_sold > 0 THEN 'stock out'
                WHEN r.sales_per_day > q.q3 THEN 'fast moving'
                WHEN r.sales_per_day >= q.q2 THEN 'moderate'
                ELSE 'slow moving'
            END AS status,

            CEIL(r.restock_amount) AS restock_amount

        FROM restock_table r
        CROSS JOIN quartiles q
        ORDER BY r.sales_per_day DESC
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
                END AS lifetime,

                net_items_sold::numeric / :sales_duration AS sales_per_day

            FROM main
            WHERE sku IS NOT NULL
        ),

        restock_table AS (
            SELECT
                *,
                CASE
                    WHEN net_items_sold = 0 THEN :minimum_value
                    ELSE GREATEST(
                        ((sales_per_day * :restock_days) - inventory),
                        0
                    )
                END AS restock_amount
            FROM cte3
        ),

        quartiles AS (
            SELECT
                percentile_cont(0.50) WITHIN GROUP (ORDER BY sales_per_day) AS q2,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY sales_per_day) AS q3
            FROM restock_table
            WHERE net_items_sold > 0
        ),

        classified AS (
            SELECT
                r.*,
                q.q2,
                q.q3,
                CASE
                    WHEN r.inventory = 0 AND r.net_items_sold > 0 THEN 'stock out'
                    WHEN r.net_items_sold = 0 THEN 'never sold'
                    WHEN r.sales_per_day > q.q3 THEN 'fast moving'
                    WHEN r.sales_per_day >= q.q2 THEN 'moderate'
                    ELSE 'slow moving'
                END AS status
            FROM restock_table r
            CROSS JOIN quartiles q
        )

        SELECT
            title,
            size,
            sku,
            lifetime,
            ROUND(sales_per_day,2) AS sales_per_day,
            inventory,
            status,
            CEIL(restock_amount) AS restock_amount

        FROM classified
        WHERE title IN :items
        ORDER BY sales_per_day DESC
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
