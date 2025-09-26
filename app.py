import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from typing import Any, Dict, List

BASE_URL = "https://www.walmart.com.mx"

# --- Utilidades ---
def _to_abs_url(path_or_url: str) -> str:
    if not path_or_url:
        return "#"
    if path_or_url.startswith("http"):
        return path_or_url
    return BASE_URL.rstrip("/") + "/" + path_or_url.lstrip("/")

def _is_discount_badge_text(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    # Cubrimos variantes comunes en Walmart MX
    keywords = ["rebaja", "rollback", "oferta", "precio bajo", "ahorro"]
    return any(k in t for k in keywords)

def _has_discount_flags(item: Dict[str, Any]) -> bool:
    # Variantes conocidas donde marcan rebajas:
    # - badges[].text ~ "Rebaja"
    # - isRollback / rollback / priceInfo.flags / promoBadge
    # - promotionalPriceVisible, etc.
    badges = item.get("badges") or item.get("badgesV2") or []
    if isinstance(badges, dict):  # a veces viene en diccionario
        badges = badges.get("badges", [])
    if any(_is_discount_badge_text((b or {}).get("text", "")) for b in badges):
        return True

    # banderas booleanas típicas
    for key in ["isRollback", "rollback", "hasRollback", "hasDiscount", "isOnSale"]:
        if isinstance(item.get(key), bool) and item.get(key):
            return True

    # En priceInfo a veces hay señalizadores:
    price_info = item.get("priceInfo", {}) or {}
    for key in ["isRollback", "isOnSale", "hasDiscount", "rollback"]:
        if isinstance(price_info.get(key), bool) and price_info.get(key):
            return True

    # promoBadge o similares
    promo_badge = item.get("promoBadge") or item.get("promoLabel")
    if isinstance(promo_badge, str) and _is_discount_badge_text(promo_badge):
        return True

    return False

def _extract_price(item: Dict[str, Any]) -> Any:
    """
    Walmart varía el nodo de precio: 
    - priceInfo.linePrice.price
    - priceInfo.currentPrice
    - priceInfo.price
    - priceMap.price
    - price
    """
    pi = item.get("priceInfo") or {}
    # Orden de preferencia
    candidates = [
        pi.get("linePrice", {}).get("price"),
        pi.get("currentPrice"),
        pi.get("price"),
        (item.get("priceMap") or {}).get("price"),
        item.get("price"),
    ]
    for c in candidates:
        if c not in (None, "", {}):
            return c
    return "N/D"

def _looks_like_product_dict(d: Dict[str, Any]) -> bool:
    # Heurística: los productos suelen tener al menos un nombre y una URL canónica
    if not isinstance(d, dict):
        return False
    has_title = any(k in d for k in ["displayName", "name", "productName"])
    has_url = any(k in d for k in ["canonicalUrl", "productUrl", "url"])
    # Evitamos confundir con banners/contenidos sin precio
    return has_title and has_url

def _normalize_item(d: Dict[str, Any]) -> Dict[str, Any]:
    titulo = d.get("displayName") or d.get("name") or d.get("productName") or "Sin título"
    url_raw = d.get("canonicalUrl") or d.get("productUrl") or d.get("url") or "#"
    url = _to_abs_url(url_raw)
    precio = _extract_price(d)

    # Etiquetas visibles en badges
    badges = d.get("badges") or d.get("badgesV2") or []
    if isinstance(badges, dict):
        badges = badges.get("badges", [])
    etiquetas = []
    for b in badges:
        if isinstance(b, dict):
            txt = b.get("text") or b.get("name") or b.get("label")
            if txt:
                etiquetas.append(str(txt))
        elif isinstance(b, str):
            etiquetas.append(b)

    # Añadimos hints basados en flags para que aparezca la palabra "Rebaja"
    if _has_discount_flags(d) and not any(_is_discount_badge_text(e) for e in etiquetas):
        etiquetas.append("Rebaja")

    return {
        "titulo": titulo,
        "precio": precio,
        "url": url,
        "etiquetas": ", ".join(sorted(set(etiquetas))) if etiquetas else ""
    }

def _walk_and_collect_items(node: Any, collected: List[Dict[str, Any]]):
    """
    Recorre recursivamente el JSON y agrega arrays de 'items' que parezcan productos.
    También captura objetos sueltos que parezcan producto.
    """
    if isinstance(node, dict):
        # Caso: este dict YA luce como producto
        if _looks_like_product_dict(node):
            collected.append(_normalize_item(node))

        # Caso: campos 'items' potencialmente conteniendo productos
        for k, v in node.items():
            if k.lower() in ["items", "itemlist", "itemstack", "itemstacks"]:
                # 'items' puede ser lista o estructura con 'items'
                if isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict) and _looks_like_product_dict(it):
                            collected.append(_normalize_item(it))
                        elif isinstance(it, dict):
                            # A veces hay sub-nodos con 'items' dentro
                            _walk_and_collect_items(it, collected)
                elif isinstance(v, dict):
                    # p.ej. { items: [...] }
                    inner = v.get("items")
                    if isinstance(inner, list):
                        for it in inner:
                            if isinstance(it, dict) and _looks_like_product_dict(it):
                                collected.append(_normalize_item(it))
                            elif isinstance(it, dict):
                                _walk_and_collect_items(it, collected)
            else:
                _walk_and_collect_items(v, collected)

    elif isinstance(node, list):
        for el in node:
            _walk_and_collect_items(el, collected)

def _parse_items_from_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return []

    try:
        data = json.loads(script_tag.string)
    except json.JSONDecodeError:
        return []

    productos: List[Dict[str, Any]] = []
    # Caminata completa por el objeto
    _walk_and_collect_items(data, productos)

    # De-duplicamos por URL (a veces salen repetidos de distintos 'stacks')
    seen = set()
    unique = []
    for p in productos:
        key = (p["url"], p["titulo"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique

@st.cache_data(show_spinner=False)
def obtener_productos(url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    return _parse_items_from_html(resp.text)

# --- Streamlit UI (fragmento relevante) ---
st.set_page_config(page_title="Walmart MX – Rebajas", page_icon="🛒", layout="wide")
st.title("🛒 Buscador de Rebajas • Walmart México")

with st.sidebar:
    default_url = "https://www.walmart.com.mx/content/electrodomesticos/cafeteras-y-extractores/265659_265675"
    url = st.text_input("URL de la categoría / landing", value=default_url)
    solo_rebajas = st.toggle("Mostrar solo artículos con etiqueta/flag de rebaja", value=True)
    st.caption("Soporta landings 'content/*' y categorías con diferente estructura.")

col1, col2 = st.columns([1, 4])
buscar = col1.button("Buscar", type="primary")
col2.write("")

if buscar:
    if not url.strip():
        st.error("Por favor ingresa una URL válida de walmart.com.mx")
    else:
        try:
            with st.spinner("Extrayendo productos..."):
                productos = obtener_productos(url.strip())

            if not productos:
                st.warning("No se encontraron productos. Es posible que la estructura haya cambiado o la página cargue productos vía cliente.")
            else:
                df = pd.DataFrame(productos)

                if solo_rebajas:
                    # Filtrado: etiquetas que contengan keywords o items marcados con flags (ya agregamos 'Rebaja' si vimos flags)
                    mask = df["etiquetas"].str.lower().str.contains("rebaja|rollback|oferta|precio bajo|ahorro", na=False)
                    df_filtrado = df[mask].copy()
                else:
                    df_filtrado = df.copy()

                st.success(f"Productos encontrados: {len(df_filtrado)} / {len(df)}")
                st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    st.download_button(
                        "Descargar CSV",
                        df_filtrado.to_csv(index=False).encode("utf-8"),
                        file_name="rebajas_walmart.csv",
                        mime="text/csv"
                    )
                with c2:
                    st.download_button(
                        "Descargar JSON",
                        df_filtrado.to_json(orient="records", force_ascii=False).encode("utf-8"),
                        file_name="rebajas_walmart.json",
                        mime="application/json"
                    )

                with st.expander("Depuración rápida (primeros 5)"):
                    st.write(df.head(5))

        except requests.HTTPError as e:
            st.error(f"Error HTTP {getattr(e.response, 'status_code', '')}: {e}")
        except requests.ConnectionError:
            st.error("Error de conexión. Verifica tu red.")
        except requests.Timeout:
            st.error("Tiempo de espera agotado al solicitar la página.")
        except Exception as e:
            st.error(f"Ocurrió un error inesperado: {e}")
