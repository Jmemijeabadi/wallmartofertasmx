# app.py
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

BASE_URL = "https://www.walmart.com.mx"

# --- Web scraping core ---
def _parse_items_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        return []

    try:
        data = json.loads(script_tag.string)
        items = data["props"]["pageProps"]["initialData"]["searchResult"]["itemStacks"][0]["items"]
    except (KeyError, json.JSONDecodeError, TypeError):
        return []

    productos = []
    for item in items:
        titulo = item.get("displayName", "Sin título")
        precio = (
            item.get("priceInfo", {})
                .get("linePrice", {})
                .get("price", "N/D")
        )
        url_producto = BASE_URL + item.get("canonicalUrl", "#")
        badges = item.get("badges", [])
        etiquetas = [b.get("text", "") for b in badges]

        productos.append({
            "titulo": titulo,
            "precio": precio,
            "url": url_producto,
            "etiquetas": ", ".join(etiquetas)
        })
    return productos

@st.cache_data(show_spinner=False)
def obtener_productos(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return _parse_items_from_html(resp.text)

# --- Streamlit UI ---
st.set_page_config(page_title="Walmart MX – Rebajas", page_icon="🛒", layout="wide")
st.title("🛒 Buscador de Rebajas • Walmart México")

with st.sidebar:
    st.subheader("Configuración")
    default_url = "https://www.walmart.com.mx/content/electrodomesticos/265659"
    url = st.text_input("URL de la categoría / landing", value=default_url)
    solo_rebajas = st.toggle("Mostrar solo artículos con etiqueta 'Rebaja'", value=True)
    st.caption("Pega la URL de una categoría o landing de Walmart MX.")

col1, col2 = st.columns([1, 3])
with col1:
    buscar = st.button("Buscar", type="primary")
with col2:
    st.write("")

if buscar:
    if not url.strip():
        st.error("Por favor ingresa una URL válida de walmart.com.mx")
    else:
        try:
            with st.spinner("Extrayendo productos..."):
                productos = obtener_productos(url.strip())

            if not productos:
                st.warning("No se encontraron productos en la página o cambió la estructura.")
            else:
                df = pd.DataFrame(productos)

                if solo_rebajas:
                    mask = df["etiquetas"].str.contains("Rebaja", na=False)
                    df_filtrado = df[mask].copy()
                else:
                    df_filtrado = df.copy()

                st.success(f"Productos encontrados: {len(df_filtrado)} / {len(df)}")

                # Tabla interactiva
                st.dataframe(
                    df_filtrado[["titulo", "precio", "url", "etiquetas"]],
                    use_container_width=True,
                    hide_index=True
                )

                # Descargas
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

                # Vista tipo tarjetas (opcional)
                st.markdown("---")
                st.subheader("Vista rápida")
                for _, row in df_filtrado.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{row['titulo']}**")
                        st.write(f"Precio: {row['precio']}")
                        st.write(f"Etiquetas: {row['etiquetas'] or '—'}")
                        st.link_button("Ver producto", row["url"])

        except requests.HTTPError as e:
            st.error(f"Error HTTP {e.response.status_code}: {e}")
        except requests.ConnectionError:
            st.error("Error de conexión. Verifica tu red.")
        except requests.Timeout:
            st.error("Tiempo de espera agotado al solicitar la página.")
        except Exception as e:
            st.error(f"Ocurrió un error inesperado: {e}")

# Nota al pie
st.caption("Este proyecto es solo para fines educativos. Walmart puede cambiar su estructura interna en cualquier momento.")
