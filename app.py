import requests
import streamlit as st

def obtener_rebajas(url_categoria: str):
    """
    Extrae productos en rebaja de una categoría de Walmart México.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Walmart MX genera APIs internas: cambiamos la URL de categoría a formato API
    # Ejemplo: https://www.walmart.com.mx/api/product-list?category=Electrodomesticos/Licuadoras
    if "walmart.com.mx" in url_categoria:
        if "/cp/" in url_categoria:
            # Ejemplo: https://www.walmart.com.mx/cp/licuadoras/376089
            categoria = url_categoria.split("/cp/")[-1]
            api_url = f"https://www.walmart.com.mx/api/product-list?category={categoria}"
        else:
            st.error("⚠️ Necesitas pegar la URL de categoría (ejemplo: /cp/licuadoras/376089)")
            return []
    else:
        st.error("⚠️ La URL no pertenece a Walmart México")
        return []

    response = requests.get(api_url, headers=headers)

    if response.status_code != 200:
        st.error("No se pudieron obtener los datos")
        return []

    data = response.json()
    rebajas = []

    for producto in data.get("results", []):
        nombre = producto.get("displayName")
        precio = producto.get("priceInfo", {}).get("currentPrice")
        precio_anterior = producto.get("priceInfo", {}).get("listPrice")
        url_producto = "https://www.walmart.com.mx" + producto.get("url")

        if precio_anterior and precio < precio_anterior:
            rebajas.append({
                "nombre": nombre,
                "precio": precio,
                "precio_anterior": precio_anterior,
                "url": url_producto
            })

    return rebajas


# --- Streamlit UI ---
st.title("🛒 Detector de Rebajas Walmart MX")

url = st.text_input("Pega la URL de una categoría de Walmart México:")

if url:
    productos = obtener_rebajas(url)
    if productos:
        st.success(f"Encontrados {len(productos)} productos en rebaja ✅")
        for p in productos:
            st.write(f"**{p['nombre']}**")
            st.write(f"💲 {p['precio']} (antes {p['precio_anterior']})")
            st.markdown(f"[Ver producto]({p['url']})")
            st.markdown("---")
    else:
        st.warning("No se encontraron rebajas en esta categoría.")
