import requests
import streamlit as st

# --- Función para obtener todas las categorías principales ---
def obtener_categorias():
    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://www.walmart.com.mx/api/navigation"  # API del menú de categorías
    response = requests.get(url, headers=headers)

    categorias = {}
    if response.status_code == 200:
        data = response.json()
        for depto in data.get("departments", []):
            nombre = depto.get("displayName")
            slug = depto.get("url")  # Ejemplo: /cp/televisores/376089
            if slug and "/cp/" in slug:
                categoria = slug.split("/cp/")[-1]  # formato API
                categorias[nombre] = categoria
    return categorias


# --- Función para obtener productos en rebaja de una categoría ---
def obtener_rebajas(categoria_api: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    api_url = f"https://www.walmart.com.mx/api/product-list?category={categoria_api}"

    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
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


# --- Interfaz Streamlit ---
st.set_page_config(page_title="Rebajas Walmart MX", page_icon="🛒", layout="wide")
st.title("🛒 Detector de Rebajas Walmart México")

categorias = obtener_categorias()

if categorias:
    categoria_seleccionada = st.selectbox("📂 Elige una categoría:", list(categorias.keys()))

    if categoria_seleccionada:
        st.info(f"🔎 Buscando rebajas en: {categoria_seleccionada}...")
        productos = obtener_rebajas(categorias[categoria_seleccionada])

        if productos:
            st.success(f"✅ Encontrados {len(productos)} productos en rebaja")
            for p in productos:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{p['nombre']}**")
                    st.write(f"💲 {p['precio']} (antes {p['precio_anterior']})")
                    st.markdown(f"[🔗 Ver producto]({p['url']})")
                with col2:
                    st.write("---")
        else:
            st.warning("⚠️ No se encontraron rebajas en esta categoría.")
else:
    st.error("❌ No se pudieron cargar las categorías de Walmart.")
