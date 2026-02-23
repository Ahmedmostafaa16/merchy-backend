import requests
from sqlalchemy.orm import Session
from models import Inventory,Sales
from dateutil.parser import isoparse
 


class Operations:
    def __init__(self, domain: str, token: str):
        self.domain = domain
        self.token = token
        self.endpoint = f"https://{self.domain}/admin/api/2024-01/graphql.json"

        self.headers = {
            "X-Shopify-Access-Token": self.token,
            "Content-Type": "application/json"
        }

    # ---------- Internal helper ----------
    def _graphql(self, query: str, variables: dict | None = None):
        response = requests.post(
            self.endpoint,
            headers=self.headers,
            json={"query": query, "variables": variables or {}},
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"Shopify HTTP error: {response.text}")

        data = response.json()

        if "errors" in data:
            raise Exception(f"Shopify GraphQL error: {data['errors']}")

        return data["data"]

    # ---------- Public method ----------
    def get_inventory(self):
        query = """
        query ($cursor: String) {
          products(first: 50, after: $cursor) {
            edges {
              cursor
              node {
                title
                variants(first: 50) {
                  edges {
                    node {
                      title
                      sku
                      price
                      inventoryQuantity
                    }
                  }
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """

        cursor = None
        has_next_page = True
        rows = []

        while has_next_page:
            data = self._graphql(query, {"cursor": cursor})
            products = data["products"]

            for product_edge in products["edges"]:
                product_title = product_edge["node"]["title"]

                for variant_edge in product_edge["node"]["variants"]["edges"]:
                    variant = variant_edge["node"]

                    rows.append({

                        "title": product_title,
                        "size": variant["title"],
                        "sku": variant["sku"],
                        "inventory": variant["inventoryQuantity"],
                        "price": variant["price"],
                        
                    })

            cursor = products["pageInfo"]["endCursor"]
            has_next_page = products["pageInfo"]["hasNextPage"]

        return rows
      
      
    def delete_inventory(self,shop_id : int ,database: Session):
        database.query(Inventory).filter(Inventory.shop_id == shop_id).delete()
        database.commit()
        
    def get_sales(self, start_date, end_date) -> list:
        start_date = start_date.isoformat()
        end_date = end_date.isoformat()

        query = """
        query ($cursor: String, $query: String!) {
          orders(
            first: 50
            after: $cursor
            query: $query
          ) {
            edges {
              node {
                createdAt
                lineItems(first: 50) {
                  edges {
                    node {
                      title
                      quantity
                      variant {
                        sku
                        title
                      }
                    }
                  }
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """

        date_query = f"created_at:>={start_date} created_at:<={end_date}"

        cursor = None
        has_next_page = True
        sales_rows = []

        while has_next_page:
            data = self._graphql(query, {"cursor": cursor, "query": date_query})
            orders = data["orders"]

            for order_edge in orders["edges"]:
                order_node = order_edge["node"]
                created_at = isoparse(order_node["createdAt"])

                for item_edge in order_node["lineItems"]["edges"]:
                    item = item_edge["node"]
                    variant = item.get("variant")

                    sales_rows.append({
                        "title": item["title"],
                        "size": variant["title"] if variant else None,
                        "color":variant["color"] if variant and "color" in variant else None,
                        "sku": variant["sku"] if variant else None,
                        "quantity_sold": int(item["quantity"]),
                        "created_at": created_at
                    })

            cursor = orders["pageInfo"]["endCursor"]
            has_next_page = orders["pageInfo"]["hasNextPage"]

        return sales_rows
      
    def delete_sales(self,shop_id : int ,database: Session):
        database.query(Sales).filter(Sales.shop_id == shop_id).delete()
        database.commit()


      

        
        