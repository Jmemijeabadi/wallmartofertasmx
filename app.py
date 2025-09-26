# app.py
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from typing import Any, Dict, List, Optional

BASE_URL = "https://www.walmart.com.mx"

# -------------------- Utilidades comunes --------------------
def _to_abs_url(path_or_url: str) -> str:
    if not path_or_url:
        return "#"
    if path_or_url.startswith("http"):
        return path_or_url
    return BASE_URL.rstrip("/") + "/" + path_or_url.lstrip("/")

def _is_discount_text(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return any(k in t for k in ["rebaja", "rollback", "oferta", "precio bajo", "ahorro", "promo"])

def _extract_price(item: Dict[str, Any]) -> Any:
    pi = item.get("priceInfo") or {}
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
    if not isinstance(d, dict):
        return False
    has_title = any(k in d for k in ["displayName", "name", "productName"])
    has_url = any(k in d for k in ["canonicalUrl", "productUrl", "url"])
    return has_title and has_url

def _normalize_item(d: Dict[str, Any]) -> Dict[str, Any]:
    titulo = d.get("displayName") or d.get("name") or d.get("productName") or "Sin título"
    url_raw = d.get("canonicalUrl") or d.get("productUrl") or d.get("url") or "#"
    url = _to_abs_url(url_raw)
    precio = _extract_price(d)

    badges = d.get("badges") or d.get("badgesV2") or []
    if isinstance(badges, dict):
        badges = badges.get("badges", [])
    etiquetas = []
    for b in badges:
        if isinstance(b, dict):
            txt = b.get("text") or b.get("name") or b.get("label")
            if txt: etiquetas.append(str(txt))
        elif isinstance(b, str):
            etiquetas.append(b)

    # flags comunes de descuento
    discount_flags = any(bool(d.get(k)) for k in ["isRollback", "rollback", "hasRollback", "hasDiscount", "isOnSale"])
    price_info = d.get("priceInfo") or {}
    discount_flags = discount_flags or any(bool(price_info.get(k)) for k in ["isRollback", "isOnSale", "hasDiscount", "rollback"])

    if discount_flags and not any(_is_discount_text(e) for e in etiquetas):
        etiquetas.append("Rebaja")

    return {"titulo": titulo, "precio": precio, "url": url, "etiquetas": ", ".join(sorted(set(etiquetas))) if etiquetas else ""}

def _walk_and_collect_items(node: Any, collected: List[Dict[str, Any]]):
    if isinstance(node, dict):
        if _looks_like_product_dict(node):
            collected.append(_normalize_item(node))
        for k, v in node.items():
            if k.lower() in ["items", "itemlist", "itemstack", "itemstacks"]:
                if isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict) and _looks_like_product_dict(it):
                            collected.append(_normalize_item(it))
                        elif isinstance(it, dict):
                            _walk_and_collect_items(it, collected)
                elif isinstance(v, dict):
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

def _parse_from_next_data(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return []
    try:
        data = json.loads(script_tag.string)
    except json.JSONDecodeError:
        return []
    productos: List[Dict[str, Any]] = []
    _walk_and_collect_items(data, productos)
    # de-dup
    seen, unique = set(), []
    for p in productos:
        key = (p["url"], p["titulo"])
        if key not in seen:
            seen.add(key); unique.append(p)
    return unique

@st.cache_data(show_spinner=False)
def obtener_por_requests(url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    # Si Walmart devuelve /blocked aquí no habrá __NEXT_DATA__
    return _parse_from_next_data(resp.text)

# -------------------- Plan B: Playwright (render JS) --------------------
@st.cache_data(show_spinner=False)
def obtener_por_playwright(url: str, wait_selector: Optional[str] = None, timeout_ms: int = 15000) -> List[Dict[str, Any]]:
    """
    Abre la página “como navegador”, espera que carguen productos y extrae del DOM.
    """
    from playwright.sync_api import sync_playwright

    productos: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-MX",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Si hay el reto de “verifica tu identidad”, nos detenemos
        if "blocked" in page.url:
            browser.close()
            return []

        # Heurísticas: Walmart suele renderizar cards con enlaces a /ip/ o /content/…; usamos selectores genéricos.
        # Puedes ajustar estos selectores según la estructura actual.
        # Intento 1: esperar cualquier grid de productos
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout_ms)
        else:
            # intentamos varias opciones, corto ciclo
            for sel in ["a[href*='/ip/']", "[data-automation-id*='product']", "a[data-testid*='product']"]:
                try:
                    page.wait_for_selector(sel, timeout=timeout_ms)
                    break
                except Exception:
                    pass

        time.sleep(1.0)  # pequeño respiro para que termine de hidratar

        # Parseo directo del DOM (simple y robusto)
        anchors = page.locator("a[href*='/ip/']").all()
        seen = set()
        for a in anchors:
            href = a.get_attribute("href")
            title = a.get_attribute("title") or a.inner_text(timeout=1000)[:200]
            if not href or not title:
                continue
            url_abs = _to_abs_url(href)
            key = (url_abs, title.strip())
            if key in seen: 
                continue
            seen.add(key)

            # Intentamos detectar badge/etiquetas visibles cercanas
            # (ajústalo según la clase/atributo que veas en tu DOM)
            parent_html = a.evaluate("el => el.closest('article, li, div')?.innerText || ''")
            etiquetas = []
            for kw in ["Rebaja", "Rollback", "Oferta", "Precio bajo", "Ahorro"]:
                if kw.lower() in (parent_html or "").lower():
                    etiquetas.append(kw)

            # precio (si aparece renderizado):
            precio = None
            # Busca texto con $ cerca del enlace
            if parent_html:
                # extracción muy básica
                for token in parent_html.split():
                    if token.strip().startswith("$"):
                        precio = token.strip()
                        break

            productos.append({
                "titulo": title.strip() or "Sin título",
                "precio": precio or "N/D",
                "url": url_abs,
                "etiquetas": ", ".join(sorted(set(etiquetas)))
            })

        browser.close()
    return productos

# -------------------- UI Streamlit --------------------
st.set_page_config(page_title="Walmart MX – Rebajas", page_icon="🛒", layout="wide")
st.title("🛒 Buscador de Rebajas • Walmart México")

with st.sidebar:
    url = st.text_input(
        "URL de categoría / landing",
        value="https://www.walmart.com.mx/content/electrodomesticos/cafeteras-y-extractores/265659_265675"
    )
    solo_rebajas = st.toggle("Mostrar solo con rebaja/rollback/oferta", value=True)
    usar_playwright = st.toggle("Usar plan B (renderizar con Playwright) si no hay resultados", value=True)
    st.caption("Si Walmart muestra 'Verifica tu identidad', el plan B también puede fallar (bloqueos anti-bot).")

if st.button("Buscar", type="primary"):
    if not url.strip():
        st.error("Ingresa una URL válida.")
    else:
        try:
            with st.spinner("Extrayendo (plan A)…"):
                productos = obtener_por_requests(url.strip())

            if not productos and usar_playwright:
                with st.spinner("No hubo datos. Intentando (plan B) renderizado…"):
                    productos = obtener_por_playwright(url.strip())

            if not productos:
                st.warning("No se encontraron productos. Puede ser bloqueo anti-bot o carga solo en cliente.")
            else:
                df = pd.DataFrame(productos)
                if solo_rebajas:
                    mask = df["etiquetas"].str.lower().str.contains("rebaja|rollback|oferta|precio bajo|ahorro", na=False)
                    df = df[mask].copy()

                st.success(f"Productos encontrados: {len(df)}")
                st.dataframe(df[["titulo", "precio", "url", "etiquetas"]], use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8"), file_name="rebajas_walmart.csv", mime="text/csv")
                with c2:
                    st.download_button("Descargar JSON", df.to_json(orient="records", force_ascii=False).encode("utf-8"), file_name="rebajas_walmart.json", mime="application/json")

        except requests.HTTPError as e:
            st.error(f"Error HTTP {getattr(e.response, 'status_code', '')}: {e}")
        except Exception as e:
            st.error(f"Ocurrió un error: {e}")

st.caption("Nota: Walmart MX usa protecciones anti-bot. Si ves pocos resultados, considera usar API oficial de afiliados o un scraper API externo.")
