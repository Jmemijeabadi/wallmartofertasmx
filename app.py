import requests
from bs4 import BeautifulSoup
import json

BASE_URL = "https://www.walmart.com.mx"

def obtener_rebajas_desde_url(url):
    productos = []
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "html.parser")

    # Walmart usa JSON dentro de script con id="__NEXT_DATA__"
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        return productos

    data = json.loads(script_tag.string)

    # Acceso al árbol JSON donde están los productos
    try:
        items = data["props"]["pageProps"]["initialData"]["searchResult"]["itemStacks"][0]["items"]
    except KeyError:
        return productos

    for item in items:
        titulo = item.get("displayName", "Sin título")
        precio = item.get("priceInfo", {}).get("linePrice", {}).get("price", "N/A")
        url_producto = BASE_URL + item.get("canonicalUrl", "#")
        promocion = item.get("badges", [])

        # Filtramos SOLO si está marcado como rebaja
        if any("Rebaja" in badge.get("text", "") for badge in promocion):
            productos.append({
                "titulo": titulo,
                "precio": precio,
                "url": url_producto
            })

    return productos


# Ejemplo de uso
if __name__ == "__main__":
    url = "https://www.walmart.com.mx/content/electrodomesticos/265659"
    rebajas = obtener_rebajas_desde_url(url)
    for r in rebajas:
        print(r)
