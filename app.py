import streamlit as st
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def obtener_rebajas_desde_url(url):
    rebajas = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(5000)  # esperar a que carguen los productos

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Walmart MX suele usar etiquetas de rebaja en spans con texto "Rebaja"
        productos = soup.find_all("div", class_="pa0")  # contenedor genérico de productos (se puede ajustar)

        for p in productos:
            nombre = p.find("span", {"class": "w_iUH7"})
            precio = p.find("span", {"class": "w_Q2R8"})
            rebaja = p.find(string="Rebaja")

            if nombre and precio and rebaja:
                rebajas.append({
                    "nombre": nombre.get_text(strip=True),
                    "precio": precio.get_text(strip=True)
                })

        browser.close()

    return rebajas


# --- Interfaz Streamlit ---
st.set_page_config(page_title="Rebajas Walmart MX", page_icon="🛒", layout="wide")
st.title("🛒 Rebajas Walmart MX (scraping con Playwright)")

url = st.text_input("📂 Pega la URL de una categoría de Walmart México:")

if url:
    st.info("🔎 Buscando productos en rebaja...")
    productos = obtener_rebajas_desde_url(url)

    if productos:
        st.success(f"✅ Encontrados {len(productos)} productos en rebaja")
        for p in productos:
            st.write(f"**{p['nombre']}** - 💲{p['precio']}")
            st.markdown("---")
    else:
        st.warning("⚠️ No se encontraron rebajas en esta categoría.")
