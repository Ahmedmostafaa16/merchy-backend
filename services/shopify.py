import requests
from sqlalchemy.orm import Session
from core.auth import get_valid_shopify_access_token
from models import Inventory, Sales, Shop
from dateutil.parser import isoparse
 


class Operations:
    def __init__(self, domain: str, token: str, shop_id=None):
        self.domain = domain
        self.token = token
        self.shop_id = shop_id
        self.endpoint = f"https://{self.domain}/admin/api/2024-01/graphql.json"

        self.headers = {
            "X-Shopify-Access-Token": self.token,
            "Content-Type": "application/json"
        }

    @classmethod
    def from_shop(
        cls,
        database: Session,
        shop_domain: str,
        required_scopes: tuple[str, ...] = (),
        host: str | None = None,
    ):
        access_token = get_valid_shopify_access_token(
            database,
            shop_domain,
            required_scopes=required_scopes,
            host=host,
        )
        shop = database.query(Shop).filter(Shop.shop_domain == shop_domain).first()
        return cls(shop_domain, access_token, shop.id if shop else None)

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
              node {
                id
                title
                variants(first: 50) {
                  edges {
                    node {
                      id
                      sku
                      title
                      price
                      inventoryItem {
                        id
                        inventoryLevels(first: 10) {
                          edges {
                            node {
                              quantities(names: ["available"]) {
                                name
                                quantity
                              }
                              location {
                                id
                                name
                              }
                            }
                          }
                        }
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

        cursor = None
        has_next_page = True
        rows = []

        while has_next_page:
            data = self._graphql(query, {"cursor": cursor})
            products = data.get("products", {})

            for product_edge in products.get("edges", []):
                product_node = product_edge.get("node", {})
                product_title = product_node.get("title", "")

                for variant_edge in product_node.get("variants", {}).get("edges", []):
                    variant = variant_edge.get("node", {})

                    if not variant:
                        continue

                    # 🔥 Extract variant_id safely
                    try:
                        variant_id = int(variant["id"].split("/")[-1])
                    except Exception:
                        continue

                    inventory_item = variant.get("inventoryItem")
                    if not inventory_item:
                        continue

                    inventory_levels = inventory_item.get("inventoryLevels", {}).get("edges", [])

                    # 🔥 Loop per location (CRITICAL CHANGE)
                    for level_edge in inventory_levels:
                        node = level_edge.get("node", {})

                        location = node.get("location")
                        if not location:
                            continue

                        try:
                            location_id = int(location["id"].split("/")[-1])
                        except Exception:
                            continue

                        available_quantity = next(
                            (
                                quantity_info.get("quantity")
                                for quantity_info in node.get("quantities", [])
                                if quantity_info.get("name") == "available"
                            ),
                            0
                        )

                        try:
                            available = int(available_quantity or 0)
                        except (TypeError, ValueError):
                            available = 0

                        rows.append({
                            "shop_id": self.shop_id,
                            "variant_id": variant_id,
                            "location_id": location_id,
                            "product_title": product_title,
                            "variant_title": variant.get("title"),
                            "sku": variant.get("sku"),
                            "inventory": available,
                            "price": variant.get("price"),
                        })

            cursor = products.get("pageInfo", {}).get("endCursor")
            has_next_page = products.get("pageInfo", {}).get("hasNextPage")

        return rows
      
      
    def delete_inventory(self,shop_id : str ,database: Session):
        database.query(Inventory).filter(Inventory.shop_id == shop_id).delete()
        database.commit()
        
    def get_sales(self, start_date, end_date) -> list:
      start_date = start_date.isoformat()
      end_date = end_date.isoformat()

      query = """
      query ($cursor: String, $query: String!) {
        orders(first: 50, after: $cursor, query: $query) {
          edges {
            node {
              createdAt
              lineItems(first: 50) {
                edges {
                  node {
                    title
                    quantity
                    variant {
                      id
                      sku
                      title
                      product {
                        title
                      }
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

              created_at = isoparse(order_node["createdAt"]).date()

              for item_edge in order_node["lineItems"]["edges"]:
                  item = item_edge["node"]
                  variant = item.get("variant")

                  if not variant:
                      continue

                  try:
                      variant_id = int(variant["id"].split("/")[-1])
                  except Exception:
                      continue

                  sales_rows.append({
                      "variant_id": variant_id,
                      "title": variant["product"]["title"] if variant.get("product") else item.get("title", ""),
                      "variant_title": variant["title"],
                      "sku": variant["sku"],
                      "quantity_sold": int(item.get("quantity") or 0),
                      "created_at": created_at
                  })

          cursor = orders["pageInfo"]["endCursor"]
          has_next_page = orders["pageInfo"]["hasNextPage"]

      return sales_rows
      
    def delete_sales(self,shop_id : str ,database: Session):
        database.query(Sales).filter(Sales.shop_id == shop_id).delete()
        database.commit()


      

        
        
