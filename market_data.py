import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=3600, show_spinner=False)
def obtener_metricas_ticker(ticker: str, periodo: str = "2y") -> dict:
    """Descarga nombre, clase sugerida, CAGR y volatilidad anualizada desde Yahoo Finance."""
    ticker_limpio = str(ticker).strip().upper()
    try:
        t = yf.Ticker(ticker_limpio)
        hist = t.history(period=periodo)
        precios = hist["Close"].dropna()

        if len(precios) < 30:
            raise ValueError("Historial insuficiente")

        retornos_diarios = precios.pct_change().dropna()
        anios = len(retornos_diarios) / 252.0
        cagr = float((precios.iloc[-1] / precios.iloc[0]) ** (1.0 / anios) - 1.0)
        volatilidad = float(retornos_diarios.std() * np.sqrt(252))
        ultimo_precio = float(precios.iloc[-1])

        nombre = ticker_limpio
        clase_sugerida = "Renta variable"
        try:
            info = t.info or {}
            nombre = info.get("longName") or info.get("shortName") or ticker_limpio
            quote_type = str(info.get("quoteType", "")).upper()
            categoria = str(info.get("category", "")).lower()
            texto_busqueda = f"{nombre} {categoria}".lower()
            palabras_rf = ["treasury", "bond", "fixed income", "bill", "note", "corporate", "aggregate", "yield"]
            if any(p in texto_busqueda for p in palabras_rf) or quote_type == "MONEYMARKET":
                clase_sugerida = "Renta fija"
        except Exception:
            pass

        return {
            "ticker": ticker_limpio,
            "nombre": nombre,
            "clase_sugerida": clase_sugerida,
            "cagr": cagr,
            "volatilidad": volatilidad,
            "ultimo_precio": ultimo_precio,
            "ok": True,
        }
    except Exception:
        return {
            "ticker": ticker_limpio,
            "nombre": f"{ticker_limpio} (no encontrado)",
            "clase_sugerida": "Renta variable",
            "cagr": 0.05,
            "volatilidad": 0.15,
            "ultimo_precio": 0.0,
            "ok": False,
        }


def evaluar_cartera_multiactivo(
    df_activos: pd.DataFrame,
    peso_mm_pct: float,
    tna_mm: float,
) -> tuple[pd.DataFrame, dict]:
    """Valida los tickers cargados, consulta Yahoo Finance y normaliza las ponderaciones."""
    df_limpio = df_activos.copy()
    df_limpio["Ticker"] = df_limpio["Ticker"].fillna("").astype(str).str.strip().str.upper()
    df_limpio["Nombre"] = df_limpio["Nombre"].fillna("").astype(str).str.strip()
    df_limpio["Clase"] = df_limpio["Clase"].fillna("Renta variable").astype(str)
    df_limpio["Ponderación (%)"] = (
        pd.to_numeric(df_limpio["Ponderación (%)"], errors="coerce")
        .fillna(0.0)
        .clip(lower=0.0)
    )

    df_limpio = df_limpio[
        (df_limpio["Ticker"] != "") & (df_limpio["Ponderación (%)"] > 0)
    ].copy()

    if not df_limpio.empty:
        df_limpio = (
            df_limpio.groupby("Ticker", as_index=False)
            .agg({"Nombre": "first", "Clase": "first", "Ponderación (%)": "sum"})
        )

    suma_raw = float(peso_mm_pct + df_limpio["Ponderación (%)"].sum())
    factor = (100.0 / suma_raw) if suma_raw > 0 else 0.0
    peso_mm_ef = (peso_mm_pct * factor) / 100.0

    activos_evaluados = []
    filas_tabla = []

    if peso_mm_pct > 0:
        filas_tabla.append({
            "Activo": "T+0",
            "Nombre": "Liquidez inmediata (Money Market)",
            "Clase": "Liquidez",
            "Ponderación (%)": round(peso_mm_ef * 100, 1),
            "Retorno anual (CAGR)": f"{tna_mm * 100:.1f}%",
            "Volatilidad anual": "0.0%",
            "Estado": "Tasa manual",
        })

    for _, fila in df_limpio.iterrows():
        ticker = fila["Ticker"]
        clase = fila["Clase"]
        peso_raw = float(fila["Ponderación (%)"])
        peso_ef = (peso_raw * factor) / 100.0

        metricas = obtener_metricas_ticker(ticker)
        nombre_mostrar = fila["Nombre"] or metricas["nombre"]

        activos_evaluados.append({
            "ticker": ticker,
            "nombre": nombre_mostrar,
            "clase": clase,
            "peso_ef": peso_ef,
            "cagr": metricas["cagr"],
            "volatilidad": metricas["volatilidad"],
            "ok": metricas["ok"],
        })

        filas_tabla.append({
            "Activo": ticker,
            "Nombre": nombre_mostrar,
            "Clase": clase,
            "Ponderación (%)": round(peso_ef * 100, 1),
            "Retorno anual (CAGR)": f"{metricas['cagr'] * 100:.1f}%",
            "Volatilidad anual": f"{metricas['volatilidad'] * 100:.1f}%",
            "Estado": "OK" if metricas["ok"] else "Respaldo",
        })

    df_detalle = pd.DataFrame(filas_tabla)
    resumen_cartera = {
        "peso_mm_ef": peso_mm_ef,
        "tna_mm": tna_mm,
        "activos": activos_evaluados,
        "suma_raw": suma_raw,
    }
    return df_detalle, resumen_cartera