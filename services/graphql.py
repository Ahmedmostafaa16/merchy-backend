import requests

from collections import defaultdict
from datetime import datetime, timedelta


SHOPIFY_API_VERSION = "2025-10"


def fetch_sales_data(
    shop_domain: str,
    access_token: str,
    skus: list,
):

    today = datetime.utcnow().date()

    start_date = (today - timedelta(days=365)).isoformat()
    end_date = today.isoformat()

    print(
        "[forecast-debug][graphql] fetch_sales_data",
        {
            "shop_domain": shop_domain,
            "sku_count": len(skus),
            "start_date": start_date,
            "end_date": end_date,
        },
    )

    url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": access_token,
    }

    sales_data = defaultdict(lambda: defaultdict(int))

    for sku in skus:

        print(
            "[forecast-debug][graphql] querying sku",
            {
                "sku": sku,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        after_cursor = None
        total_orders = 0
        page_count = 0

        while True:

            after_clause = f', after: "{after_cursor}"' if after_cursor else ""

            query = f"""
            {{
              orders(
                first: 250{after_clause},
                query: "created_at:>={start_date} created_at:<={end_date} sku:{sku}"
              ) {{
                pageInfo {{
                  hasNextPage
                  endCursor
                }}
                edges {{
                  node {{
                    createdAt

                    lineItems(first: 100) {{
                      edges {{
                        node {{
                          quantity

                          variant {{
                            sku
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """

            response = requests.post(
                url,
                headers=headers,
                json={"query": query},
            )

            data = response.json()

            if "errors" in data:
                print("[forecast-debug][graphql] errors", {"sku": sku, "errors": data["errors"]})
                break

            orders_connection = data["data"]["orders"]
            orders = orders_connection["edges"]
            page_info = orders_connection["pageInfo"]
            page_count += 1
            total_orders += len(orders)

            print(
                "[forecast-debug][graphql] orders page fetched",
                {
                    "sku": sku,
                    "page": page_count,
                    "orders_count": len(orders),
                    "total_orders": total_orders,
                    "has_next_page": page_info["hasNextPage"],
                    "end_cursor": page_info["endCursor"],
                },
            )

            for order in orders:

                order_node = order["node"]

                order_date = order_node["createdAt"][:10]

                line_items = order_node["lineItems"]["edges"]

                for item in line_items:

                    item_node = item["node"]

                    variant = item_node.get("variant")

                    if not variant:
                        continue

                    item_sku = variant.get("sku")

                    if item_sku != sku:
                        continue

                    quantity = int(item_node["quantity"] or 0)

                    sales_data[sku][order_date] += quantity

            if not page_info["hasNextPage"]:
                break

            after_cursor = page_info["endCursor"]

            if not after_cursor:
                break

        sku_dates = sales_data.get(sku, {})
        print(
            "[forecast-debug][graphql] sku aggregation",
            {
                "sku": sku,
                "pages_fetched": page_count,
                "orders_fetched": total_orders,
                "date_count": len(sku_dates),
                "total_qty": sum(sku_dates.values()),
                "sample": dict(list(sorted(sku_dates.items()))[:5]),
                "tail": dict(list(sorted(sku_dates.items()))[-5:]),
            },
        )

    result = {
        sku: dict(date_quantities)
        for sku, date_quantities in sales_data.items()
    }

    print(
        "[forecast-debug][graphql] final sales_data",
        {
            "sku_count": len(result),
            "shape": {
                sku: {
                    "date_count": len(date_quantities),
                    "total_qty": sum(date_quantities.values()),
                    "first_date": min(date_quantities) if date_quantities else None,
                    "last_date": max(date_quantities) if date_quantities else None,
                    "sample": dict(list(sorted(date_quantities.items()))[:3]),
                }
                for sku, date_quantities in result.items()
            },
        },
    )

    return result
