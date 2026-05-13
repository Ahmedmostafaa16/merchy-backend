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

    url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": access_token,
    }

    sales_data = defaultdict(lambda: defaultdict(int))

    for sku in skus:

        query = f"""
        {{
          orders(
            first: 250,
            query: "created_at:>={start_date} created_at:<={end_date} sku:{sku}"
          ) {{
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
            print(data["errors"])
            continue

        orders = data["data"]["orders"]["edges"]

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

                quantity = item_node["quantity"]

                sales_data[sku][order_date] += quantity

    return dict(sales_data)