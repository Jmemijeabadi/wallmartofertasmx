import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import streamlit as st

# --- Cliente HTTP robusto con reintentos y timeouts ---
def make_session():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    s = requests.Session()
    s.headers.update(headers)

    retry = Retry(
        total=3,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

session = make_session()

def obtener_categorias():
    url = "https://www.walmart.com.mx/api/navigation"
    try:
        resp = session.get(url, timeout=8)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.debug(f"[categorias] fallo: {e}")
        return {}, e  # regresamos el error para mostrarlo en UI

    categorias = {}
    try:
        data = resp.json()
        for depto in data.get("departments", []):
            nombre = depto.get("displayName")
            slug = depto.get("url")
            if slug and "/cp/" in slug and nombre:
                categorias[nombre] = slug.split("/cp/")[-1]
    except ValueError as e:
        return {}, e
    return categorias, None

def obtener_rebajas(categoria_api: str):
    api_url = "https://www.walmart.com.mx/api/product-list"
    params = {
        "category": categoria_api,
        # "page": 1, "size": 48, "sort": "relevance"  # si aplica
    }
    try:
        resp = session.get(api_url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return [], None  # silencioso; lo manejamos en UI

    try:
        data = resp.json()
    except ValueError:
        return [], None

    rebajas = []
    for producto in data.get("results", []):
        info = producto.get("priceInfo", {}) or {}
        # a veces vienen como números, a veces como dicts
        precio = info.get("currentPrice")
        precio_anterior = info.get("listPrice")
        if isinstance(precio, dict):
            precio = precio.get("price") or precio.get("minPrice")
        if isinstance(precio_anterior, dict):
            precio_anterior = precio_anterior.get("price") or precio_anterior.get("minPrice")

        if precio_anterior and precio and float(precio) < float(precio_anterior):
            rebajas.append({
                "nombre": producto.get("displayName"),
                "precio": precio,
                "precio_anterior": precio_anterior,
                "url": "https://www.walmart.com.mx" + (producto.get("url") or ""),
            })
    return rebajas, None

# --- Interfaz Streamlit ---
st.set_page_config(page_title="Rebajas Walmart MX", page_icon="🛒", layout="wide")
st.title("🛒 Detector de Rebajas Walmart México")

with st.spinner("Cargando categorías..."):
    categorias, cat_err = obtener_categorias()

if cat_err:
    st.error("❌ No se pudieron cargar las categorías de Walmart.")
    st.caption(
        "Es posible que el sitio bloquee solicitudes desde servidores en la nube. "
        "Prueba con APIs oficiales/terceros o ejecuta localmente."
    )
    st.stop()

if categorias:
    categoria_seleccionada = st.selectbox("📂 Elige una categoría:", list(categorias.keys()))
    if categoria_seleccionada:
        st.info(f"🔎 Buscando rebajas en: {categoria_seleccionada}...")
        productos, _ = obtener_rebajas(categorias[categoria_seleccionada])

        if productos:
            st.success(f"✅ Encontrados {len(productos)} productos en rebaja")
            for p in productos:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{p['nombre']}**")
                    st.write(f"💲 {p['precio']} (antes {p['precio_anterior']})")
                    st.markdown(f"[🔗 Ver producto]({p['url']})")
                with col2:
                    st.write("—")
        else:
            st.warning("⚠️ No se encontraron rebajas o la API no devolvió resultados.")
else:
    st.error("❌ No se pudieron cargar las categorías de Walmart.")
