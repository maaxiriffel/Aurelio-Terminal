import importlib
import io
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image
import ai_advisor
from engine import (
    calcular_matriz_sensibilidad_dcf,
    generar_datos_ejemplo,
    proyectar_flujo_y_portafolio,
)
from market_data import evaluar_cartera_multiactivo, obtener_metricas_ticker
from report_generator import generar_informe_pdf

importlib.reload(ai_advisor)
from ai_advisor import generar_diagnostico_financiero, responder_consulta_cfo

RUTA_LOGO = os.path.join(os.path.dirname(__file__), "logo_aurelio.jpg")
icono_pagina = Image.open(RUTA_LOGO) if os.path.exists(RUTA_LOGO) else "📈"

st.set_page_config(
    page_title="Aurelio FP&A Terminal",
    page_icon=icono_pagina,
    layout="wide",
)

# --- Estilos visuales corporativos y responsivos ---
st.markdown(
    """
    <style>
    /* Fondo y borde del panel lateral */
    section[data-testid="stSidebar"] {
        background-color: #0D1117;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
    }
    /* Tarjetas del panel lateral */
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #161B22;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 0.75rem 0.85rem;
        margin-bottom: 0.65rem;
    }
    /* Etiquetas de sección en el sidebar */
    .sidebar-eyebrow {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: #00CC96;
        margin: 0 0 0.55rem 0;
    }
    /* Tarjetas de KPIs principales con tipografía adaptable */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 0.85rem 0.95rem;
        min-width: 0;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.82rem !important;
        white-space: normal !important;
        line-height: 1.25 !important;
    }
    div[data-testid="stMetricValue"] > div {
        font-size: clamp(1.15rem, 1.85vw, 1.7rem) !important;
        white-space: nowrap !important;
        overflow: visible !important;
    }
    div[data-testid="stMetricDelta"] > div {
        font-size: 0.78rem !important;
        white-space: normal !important;
    }
    /* En ventanas divididas o medianas (< 1280px), acomodar bloques en 2 columnas sin aplastar */
    @media (max-width: 1280px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.75rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 1 1 calc(50% - 0.75rem) !important;
            min-width: 240px !important;
        }
    }
    /* En pantallas muy angostas (< 768px), apilar en 1 columna */
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
    }
    /* Botones más limpios */
    .stButton > button, .stDownloadButton > button {
        border-radius: 8px;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Simulador de flujo de caja, portafolio de tesorería y valuación (DCF)")
st.caption("Modelado operativo, punto de equilibrio, cartera multi-activo (Yahoo Finance) y diagnóstico con IA")


def _formatear_numero_puntos(valor: float) -> str:
    """Formatea un número al estándar local con puntos para miles y coma decimal."""
    if valor == int(valor):
        return f"{int(valor):,}".replace(",", ".")
    entero, dec = f"{valor:,.2f}".split(".")
    return f"{entero.replace(',', '.')},{dec}"


def _parsear_numero_puntos(texto: str, fallback: float) -> float:
    """Convierte texto con puntos de miles (ej. '5.000.000') a float."""
    limpio = str(texto).replace("$", "").strip()
    if not limpio:
        return 0.0
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    else:
        partes = limpio.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            limpio = "".join(partes)
        elif len(partes) > 2:
            limpio = "".join(partes)
    try:
        return max(0.0, float(limpio))
    except ValueError:
        return fallback


def _al_cambiar_caja_inicial() -> None:
    texto_ingresado = st.session_state.get("caja_ini_texto", "")
    nuevo_valor = _parsear_numero_puntos(texto_ingresado, st.session_state["caja_ini_valor"])
    st.session_state["caja_ini_valor"] = nuevo_valor
    st.session_state["caja_ini_texto"] = _formatear_numero_puntos(nuevo_valor)


def _cartera_por_defecto() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Ticker": "BIL",
            "Nombre": "SPDR Bloomberg 1-3 Month T-Bill ETF",
            "Clase": "Renta fija",
            "Ponderación (%)": 35.0,
        },
        {
            "Ticker": "SPY",
            "Nombre": "SPDR S&P 500 ETF Trust",
            "Clase": "Renta variable",
            "Ponderación (%)": 20.0,
        },
        {
            "Ticker": "QQQ",
            "Nombre": "Invesco QQQ Trust",
            "Clase": "Renta variable",
            "Ponderación (%)": 15.0,
        },
    ])


# Inicialización de estado y actualizaciones pendientes
if "caja_ini_valor" not in st.session_state:
    st.session_state["caja_ini_valor"] = 5_000_000.0
if "caja_ini_texto" not in st.session_state:
    st.session_state["caja_ini_texto"] = _formatear_numero_puntos(st.session_state["caja_ini_valor"])

if "nuevo_peso_mm" in st.session_state:
    st.session_state["peso_mm"] = st.session_state.pop("nuevo_peso_mm")
if "nuevo_tna_mm" in st.session_state:
    st.session_state["tna_mm"] = st.session_state.pop("nuevo_tna_mm")

columnas_cartera = {"Ticker", "Nombre", "Clase", "Ponderación (%)"}
if (
    "df_cartera_usuario" not in st.session_state
    or not columnas_cartera.issubset(st.session_state["df_cartera_usuario"].columns)
):
    st.session_state["df_cartera_usuario"] = _cartera_por_defecto()

if "peso_mm" not in st.session_state:
    st.session_state["peso_mm"] = 30.0
if "tna_mm" not in st.session_state:
    st.session_state["tna_mm"] = 4.5
if "editor_version" not in st.session_state:
    st.session_state["editor_version"] = 0


def _al_cambiar_liquidez() -> None:
    """Ajusta automáticamente la ponderación de los activos de mercado al mover el slider T+0."""
    nuevo_mm = float(st.session_state["peso_mm"])
    objetivo_activos = round(max(0.0, 100.0 - nuevo_mm), 1)

    df_nuevo = st.session_state["df_cartera_usuario"].copy().reset_index(drop=True)
    if df_nuevo.empty:
        return

    pesos_actuales = pd.to_numeric(df_nuevo["Ponderación (%)"], errors="coerce").fillna(0.0).clip(lower=0.0)
    suma_activos = float(pesos_actuales.sum())

    if objetivo_activos <= 0.0:
        df_nuevo["Ponderación (%)"] = 0.0
    elif suma_activos > 0.0:
        factor = objetivo_activos / suma_activos
        nuevos_pesos = [round(float(p) * factor, 1) for p in pesos_actuales]
        diferencia = round(objetivo_activos - sum(nuevos_pesos), 1)
        idx_max = int(pd.Series(nuevos_pesos).idxmax())
        nuevos_pesos[idx_max] = round(max(0.0, nuevos_pesos[idx_max] + diferencia), 1)
        df_nuevo["Ponderación (%)"] = nuevos_pesos
    else:
        cada_uno = round(objetivo_activos / len(df_nuevo), 1)
        nuevos_pesos = [cada_uno] * len(df_nuevo)
        diferencia = round(objetivo_activos - sum(nuevos_pesos), 1)
        nuevos_pesos[0] = round(max(0.0, nuevos_pesos[0] + diferencia), 1)
        df_nuevo["Ponderación (%)"] = nuevos_pesos

    st.session_state["df_cartera_usuario"] = df_nuevo
    st.session_state["editor_version"] += 1


def _redistribuir_pesos_al_eliminar(df_restante: pd.DataFrame) -> None:
    """Reparte proporcionalmente el porcentaje liberado entre liquidez T+0 y activos restantes."""
    df_nuevo = df_restante.copy().reset_index(drop=True)
    df_nuevo["Ticker"] = df_nuevo["Ticker"].fillna("").astype(str).str.strip().str.upper()
    df_nuevo["Ponderación (%)"] = (
        pd.to_numeric(df_nuevo["Ponderación (%)"], errors="coerce")
        .fillna(0.0)
        .clip(lower=0.0)
    )

    peso_mm_actual = float(st.session_state["peso_mm"])
    suma_restante = peso_mm_actual + float(df_nuevo["Ponderación (%)"].sum())

    if suma_restante > 0:
        factor = 100.0 / suma_restante
        nuevo_mm = round(peso_mm_actual * factor, 1)
        nuevos_pesos = [round(float(p) * factor, 1) for p in df_nuevo["Ponderación (%)"]]

        todos = [nuevo_mm] + nuevos_pesos
        diferencia = round(100.0 - sum(todos), 1)
        idx_max = int(pd.Series(todos).idxmax())
        todos[idx_max] = round(max(0.0, todos[idx_max] + diferencia), 1)

        st.session_state["nuevo_peso_mm"] = min(100.0, todos[0])
        df_nuevo["Ponderación (%)"] = todos[1:]
    else:
        if len(df_nuevo) > 0:
            cada_uno = round(100.0 / (len(df_nuevo) + 1), 1)
            nuevos_pesos = [cada_uno] * len(df_nuevo)
            nuevo_mm = round(100.0 - sum(nuevos_pesos), 1)
            st.session_state["nuevo_peso_mm"] = min(100.0, max(0.0, nuevo_mm))
            df_nuevo["Ponderación (%)"] = nuevos_pesos
        else:
            st.session_state["nuevo_peso_mm"] = 100.0

    st.session_state["df_cartera_usuario"] = df_nuevo


def _indice_columna_sugerida(columnas: list[str], palabras_clave: list[str], fallback: int = 0) -> int:
    for idx, col in enumerate(columnas):
        nombre_limpio = str(col).lower().strip()
        if any(palabra in nombre_limpio for palabra in palabras_clave):
            return idx
    return min(fallback, len(columnas) - 1)


def _generar_plantilla_excel(df_ejemplo: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df_export = df_ejemplo[["fecha", "ingresos", "costos_variables", "gastos_fijos"]].copy()
    df_export["fecha"] = pd.to_datetime(df_export["fecha"]).dt.strftime("%Y-%m-%d")
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Historial")
    return buffer.getvalue()


# --- Barra lateral estilizada ---
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 0 0 0.7rem 0; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 0.85rem;">
            <div style="font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: #00CC96; font-weight: 700;">
                ● Terminal FP&A
            </div>
            <div style="font-size: 1.05rem; font-weight: 600; color: #F0F6FC; margin-top: 2px;">
                Parámetros del modelo
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tarjeta 1: Fuente de datos
    with st.container(border=True):
        st.markdown('<p class="sidebar-eyebrow">01 · Fuente de datos</p>', unsafe_allow_html=True)
        archivo = st.file_uploader(
            "Subir historial propio (Excel o CSV)",
            type=["xlsx", "xls", "csv"],
        )

        df_base_ejemplo = generar_datos_ejemplo()
        st.download_button(
            label="Descargar plantilla Excel (.xlsx)",
            data=_generar_plantilla_excel(df_base_ejemplo),
            file_name="plantilla_flujo_caja.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

        if archivo is not None:
            if archivo.name.lower().endswith((".xlsx", ".xls")):
                df_crudo = pd.read_excel(archivo)
            else:
                df_crudo = pd.read_csv(archivo)

            df_crudo = df_crudo.dropna(how="all")
            columnas = list(df_crudo.columns)

            if len(columnas) < 4:
                st.error("El archivo debe tener al menos 4 columnas (fecha, ingresos, costos variables y gastos fijos).")
                st.stop()

            with st.expander("Asignar columnas del archivo", expanded=True):
                col_fecha = st.selectbox(
                    "Columna de fecha o período",
                    columnas,
                    index=_indice_columna_sugerida(columnas, ["fecha", "mes", "periodo", "date"], 0),
                )
                col_ing = st.selectbox(
                    "Columna de ingresos / ventas",
                    columnas,
                    index=_indice_columna_sugerida(columnas, ["ingreso", "venta", "facturacion", "cobro"], 1),
                )
                col_cv = st.selectbox(
                    "Columna de costos variables",
                    columnas,
                    index=_indice_columna_sugerida(columnas, ["variable", "costo", "mercaderia", "insumo"], 2),
                )
                col_gf = st.selectbox(
                    "Columna de gastos fijos",
                    columnas,
                    index=_indice_columna_sugerida(columnas, ["fijo", "gasto", "estructura", "sueldo"], 3),
                )

            fechas_parseadas = pd.to_datetime(df_crudo[col_fecha], errors="coerce")
            if fechas_parseadas.isna().all():
                fechas_parseadas = pd.date_range(
                    end=pd.Timestamp.today().replace(day=1),
                    periods=len(df_crudo),
                    freq="MS",
                )

            df_hist = pd.DataFrame({
                "fecha": fechas_parseadas,
                "ingresos": pd.to_numeric(df_crudo[col_ing], errors="coerce").fillna(0.0),
                "costos_variables": pd.to_numeric(df_crudo[col_cv], errors="coerce").fillna(0.0),
                "gastos_fijos": pd.to_numeric(df_crudo[col_gf], errors="coerce").fillna(0.0),
            }).dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)

            if df_hist.empty:
                st.error("No se encontraron filas válidas en el archivo cargado.")
                st.stop()

            st.success(f"Archivo cargado: {len(df_hist)} períodos")
        else:
            df_hist = df_base_ejemplo
            st.caption("Usando historial simulado de demostración (12 meses)")

    # Tarjeta 2: Supuestos operativos
    with st.container(border=True):
        st.markdown('<p class="sidebar-eyebrow">02 · Supuestos operativos</p>', unsafe_allow_html=True)
        st.text_input(
            "Caja inicial disponible ($)",
            key="caja_ini_texto",
            on_change=_al_cambiar_caja_inicial,
            help="Escribí el monto con o sin puntos (ej. 5.000.000). Se formatea automáticamente.",
        )
        caja_ini = float(st.session_state["caja_ini_valor"])

        meses = st.slider("Horizonte de proyección (meses)", 3, 12, 6)
        crec_ventas = st.slider("Crecimiento mensual de ventas (%)", -5.0, 15.0, 3.0, 0.5) / 100
        inf_costos = st.slider("Variación mensual de costos fijos (%)", 0.0, 15.0, 2.5, 0.5) / 100

    # Tarjeta 3: Valuación corporativa
    with st.container(border=True):
        st.markdown('<p class="sidebar-eyebrow">03 · Valuación corporativa</p>', unsafe_allow_html=True)
        wacc = st.slider("Tasa de descuento / WACC anual (%)", 5.0, 100.0, 14.0, 1.0) / 100

# --- Evaluación de cartera y ejecución del motor ---
df_detalle_cartera, resumen_cartera = evaluar_cartera_multiactivo(
    st.session_state["df_cartera_usuario"],
    float(st.session_state["peso_mm"]),
    st.session_state["tna_mm"] / 100.0,
)

df_proy, df_aportes, kpis = proyectar_flujo_y_portafolio(
    df_hist, meses, crec_ventas, inf_costos, resumen_cartera, wacc, caja_ini
)
matriz_dcf = calcular_matriz_sensibilidad_dcf(
    df_hist, meses, crec_ventas, inf_costos, kpis["tna_ponderada"], wacc, caja_ini
)

# --- Tarjetas de métricas principales ---
spread_bps = int(round((kpis["tna_ponderada"] - wacc) * 10_000))
var_caja = ((kpis["caja_final"] / caja_ini) - 1) * 100 if caja_ini > 0 else 0.0

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Flujo operativo proyectado",
    f"${kpis['flujo_operativo_total']:,.0f}",
    delta=f"Margen de seguridad: {kpis['margen_seguridad_promedio']:+.1f}%",
)
col2.metric(
    f"Retorno cartera ({kpis['tna_ponderada']*100:.1f}% anual)",
    f"${kpis['interes_tesoreria']:,.0f}",
    delta=f"Spread vs. WACC: {spread_bps:+d} bps",
)
col3.metric(
    "Caja final base",
    f"${kpis['caja_final']:,.0f}",
    delta=f"{var_caja:+.1f}% vs. inicio",
)
col4.metric(
    f"Valuación DCF (WACC {wacc*100:.0f}%)",
    f"${kpis['valor_presente_dcf']:,.0f}",
    delta=f"Descuento vs. nominal: ${kpis['valor_presente_dcf'] - kpis['caja_final']:+,.0f}",
)

# --- Pestañas analíticas ---
tab1, tab2, tab3 = st.tabs([
    "Flujo operativo y punto de equilibrio",
    "Portafolio de inversión",
    "Sensibilidad DCF (WACC vs. crecimiento)",
])

with tab1:
    fig_flujo = go.Figure()
    fig_flujo.add_trace(go.Scatter(
        x=df_proy["fecha"],
        y=df_proy["caja_optimista"],
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig_flujo.add_trace(go.Scatter(
        x=df_proy["fecha"],
        y=df_proy["caja_pesimista"],
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(0, 204, 150, 0.15)",
        name="Rango de escenarios (volatilidad)",
    ))
    fig_flujo.add_trace(go.Bar(
        x=df_proy["fecha"],
        y=df_proy["flujo_operativo"],
        name="Flujo operativo mensual",
        marker_color="#636EFA",
    ))
    fig_flujo.add_trace(go.Bar(
        x=df_proy["fecha"],
        y=df_proy["rendimiento_tesoreria"],
        name="Rendimiento inversiones",
        marker_color="#FFA15A",
    ))
    fig_flujo.add_trace(go.Scatter(
        x=df_proy["fecha"],
        y=df_proy["caja_acumulada"],
        name="Caja acumulada (base)",
        mode="lines+markers",
        line=dict(color="#00CC96", width=3),
    ))
    fig_flujo.add_trace(go.Scatter(
        x=df_proy["fecha"],
        y=df_proy["caja_descontada_vp"],
        name=f"Caja descontada a VP (WACC {wacc*100:.0f}%)",
        mode="lines+markers",
        line=dict(color="#AB63FA", width=2.5, dash="dash"),
    ))
    fig_flujo.update_layout(
        title=dict(text="Dinámica operativa, devengamiento financiero y banda de escenarios", y=0.96),
        barmode="relative",
        yaxis_title="Monto ($)",
        hovermode="x unified",
        margin=dict(t=55, b=95, l=50, r=20),
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig_flujo, width="stretch")

    fig_be = go.Figure()
    fig_be.add_trace(go.Scatter(
        x=df_proy["fecha"],
        y=df_proy["ventas_equilibrio"],
        name="Ventas de equilibrio (break-even)",
        mode="lines+markers",
        line=dict(color="#EF553B", width=2.5, dash="dash"),
    ))
    fig_be.add_trace(go.Scatter(
        x=df_proy["fecha"],
        y=df_proy["ingresos"],
        name="Ingresos proyectados",
        mode="lines+markers",
        line=dict(color="#636EFA", width=3),
        fill="tonexty",
        fillcolor="rgba(99, 110, 250, 0.12)",
    ))
    fig_be.update_layout(
        title=dict(text="Punto de equilibrio operativo y margen de seguridad", y=0.96),
        yaxis_title="Facturación mensual ($)",
        hovermode="x unified",
        margin=dict(t=55, b=80, l=50, r=20),
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig_be, width="stretch")

with tab2:
    col_edit, col_res = st.columns([1.25, 1.35])

    with col_edit:
        st.markdown("**Liquidez inmediata (Money Market T+0)**")
        c_mm1, c_mm2 = st.columns(2)
        c_mm1.slider(
            "Participación T+0 (%)",
            0.0,
            100.0,
            step=0.5,
            format="%.1f%%",
            key="peso_mm",
            on_change=_al_cambiar_liquidez,
        )
        c_mm2.slider("Tasa anual T+0 (%)", 0.0, 60.0, step=0.5, format="%.1f%%", key="tna_mm")

        st.markdown("**Activos de mercado (Yahoo Finance)**")
        st.caption(
            "Escribí un ticker en **+** para autocompletar nombre y clase. "
            "Para quitar uno, seleccionalo a la izquierda y tocá el ícono de papelera (su porcentaje se reparte solo)."
        )

        df_anterior = st.session_state["df_cartera_usuario"]
        df_editado = st.data_editor(
            df_anterior,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            disabled=["Nombre"],
            column_config={
                "Ticker": st.column_config.TextColumn(
                    "Ticker",
                    help="Símbolo exacto en Yahoo Finance (ej. SPY, QQQ, MELI, BIL, NVDA)",
                    max_chars=15,
                ),
                "Nombre": st.column_config.TextColumn(
                    "Nombre del activo",
                    help="Se completa automáticamente desde Yahoo Finance",
                ),
                "Clase": st.column_config.SelectboxColumn(
                    "Clase",
                    options=["Renta fija", "Renta variable"],
                    default="Renta variable",
                ),
                "Ponderación (%)": st.column_config.NumberColumn(
                    "Ponderación (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    format="%.1f%%",
                ),
            },
            key=f"editor_cartera_{st.session_state['editor_version']}",
        )

        # Caso 1: Se eliminó una o más filas -> redistribuir porcentaje liberado al 100%
        if len(df_editado) < len(df_anterior):
            _redistribuir_pesos_al_eliminar(df_editado)
            st.session_state["editor_version"] += 1
            st.rerun()

        # Caso 2: Se agregó o editó una fila -> autocompletar y mantener la cartera en 100.0%
        elif not df_editado.equals(df_anterior):
            df_proc = df_editado.copy().reset_index(drop=True)
            df_proc["Ponderación (%)"] = (
                pd.to_numeric(df_proc["Ponderación (%)"], errors="coerce")
                .fillna(0.0)
                .clip(lower=0.0, upper=100.0)
            )
            requiere_recarga = False

            for idx in range(len(df_proc)):
                ticker_nuevo = str(df_proc.at[idx, "Ticker"] or "").strip().upper()
                ticker_viejo = (
                    str(df_anterior.iloc[idx]["Ticker"] or "").strip().upper()
                    if idx < len(df_anterior)
                    else ""
                )
                nombre_actual = str(df_proc.at[idx, "Nombre"] or "").strip()

                if ticker_nuevo != "" and (ticker_nuevo != ticker_viejo or nombre_actual == ""):
                    info_ticker = obtener_metricas_ticker(ticker_nuevo)
                    df_proc.at[idx, "Ticker"] = ticker_nuevo
                    df_proc.at[idx, "Nombre"] = info_ticker["nombre"]
                    df_proc.at[idx, "Clase"] = info_ticker["clase_sugerida"]
                    requiere_recarga = True

            peso_mm_actual = float(st.session_state["peso_mm"])
            suma_activos = float(df_proc["Ponderación (%)"].sum())
            suma_total = round(peso_mm_actual + suma_activos, 1)

            if suma_total > 100.0:
                exceso = round(suma_total - 100.0, 1)
                descuento_mm = min(peso_mm_actual, exceso)
                nuevo_mm = round(peso_mm_actual - descuento_mm, 1)
                exceso_restante = round(exceso - descuento_mm, 1)

                if exceso_restante > 0 and len(df_proc) > 0:
                    indices_fijos = []
                    for idx in range(len(df_proc)):
                        peso_nuevo_fila = float(df_proc.at[idx, "Ponderación (%)"])
                        peso_viejo_fila = (
                            float(df_anterior.iloc[idx]["Ponderación (%)"])
                            if idx < len(df_anterior) and pd.notna(df_anterior.iloc[idx]["Ponderación (%)"])
                            else 0.0
                        )
                        if idx >= len(df_anterior) or peso_nuevo_fila > peso_viejo_fila:
                            indices_fijos.append(idx)

                    indices_ajustables = [i for i in range(len(df_proc)) if i not in indices_fijos]
                    suma_fijos = sum(float(df_proc.at[i, "Ponderación (%)"]) for i in indices_fijos)

                    if suma_fijos >= 100.0 or not indices_ajustables:
                        factor = 100.0 / suma_activos
                        nuevos_pesos = [round(float(p) * factor, 1) for p in df_proc["Ponderación (%)"]]
                        dif = round(100.0 - sum(nuevos_pesos), 1)
                        idx_max = int(pd.Series(nuevos_pesos).idxmax())
                        nuevos_pesos[idx_max] = round(max(0.0, nuevos_pesos[idx_max] + dif), 1)
                        df_proc["Ponderación (%)"] = nuevos_pesos
                    else:
                        objetivo_ajustables = round(100.0 - suma_fijos, 1)
                        suma_ajustables = sum(float(df_proc.at[i, "Ponderación (%)"]) for i in indices_ajustables)
                        if suma_ajustables > 0:
                            factor = objetivo_ajustables / suma_ajustables
                            for i in indices_ajustables:
                                df_proc.at[i, "Ponderación (%)"] = round(
                                    float(df_proc.at[i, "Ponderación (%)"]) * factor, 1
                                )
                            dif = round(100.0 - float(df_proc["Ponderación (%)"].sum()), 1)
                            idx_adj_max = max(
                                indices_ajustables,
                                key=lambda i: float(df_proc.at[i, "Ponderación (%)"]),
                            )
                            df_proc.at[idx_adj_max, "Ponderación (%)"] = round(
                                max(0.0, float(df_proc.at[idx_adj_max, "Ponderación (%)"]) + dif), 1
                            )

                st.session_state["nuevo_peso_mm"] = max(0.0, nuevo_mm)
                requiere_recarga = True

            elif suma_total < 100.0:
                remanente = round(100.0 - suma_total, 1)
                st.session_state["nuevo_peso_mm"] = min(100.0, round(peso_mm_actual + remanente, 1))
                requiere_recarga = True

            st.session_state["df_cartera_usuario"] = df_proc
            if requiere_recarga:
                st.session_state["editor_version"] += 1
            st.rerun()

        c_btn1, c_btn2 = st.columns([1, 2])
        if c_btn1.button("Restaurar ejemplo"):
            st.session_state["df_cartera_usuario"] = _cartera_por_defecto()
            st.session_state["nuevo_peso_mm"] = 30.0
            st.session_state["nuevo_tna_mm"] = 4.5
            st.session_state["editor_version"] += 1
            st.rerun()

        suma_total = resumen_cartera["suma_raw"]
        if abs(suma_total - 100.0) > 0.1:
            c_btn2.warning(f"Suma actual: {suma_total:.1f}% (reescalado a 100% en cálculos).")
        else:
            c_btn2.success("Ponderación total: 100.0%")

    with col_res:
        st.markdown("**Métricas reales descargadas (últimos 2 años)**")
        if not df_detalle_cartera.empty:
            st.dataframe(df_detalle_cartera, width="stretch", hide_index=True)

        m1, m2 = st.columns(2)
        m1.metric("Retorno esperado ponderado", f"{kpis['tna_ponderada']*100:.1f}%")
        m2.metric("Volatilidad ponderada de cartera", f"{kpis['volatilidad_ponderada']*100:.1f}%")

    st.divider()
    c_izq, c_der = st.columns([1, 1.45])

    with c_izq:
        if not df_detalle_cartera.empty:
            paleta = px.colors.qualitative.Set2
            etiquetas_donut = [
                f"{row['Activo']} — {row['Nombre'][:22]}"
                for _, row in df_detalle_cartera.iterrows()
            ]
            fig_donut = go.Figure(data=[go.Pie(
                labels=etiquetas_donut,
                values=df_detalle_cartera["Ponderación (%)"],
                hole=0.55,
                marker=dict(colors=paleta),
                textinfo="label+percent",
            )])
            fig_donut.update_layout(
                title="Distribución efectiva de cartera",
                showlegend=False,
            )
            st.plotly_chart(fig_donut, width="stretch")

    with c_der:
        fig_rend = go.Figure()
        paleta = px.colors.qualitative.Set2
        columnas_activos = [c for c in df_aportes.columns if c != "fecha"]
        for idx, nombre_act in enumerate(columnas_activos):
            fig_rend.add_trace(go.Bar(
                x=df_aportes["fecha"],
                y=df_aportes[nombre_act],
                name=nombre_act,
                marker_color=paleta[idx % len(paleta)],
            ))

        fig_rend.add_trace(go.Scatter(
            x=df_proy["fecha"],
            y=df_proy["rendimiento_tesoreria"],
            name="Resultado neto cartera",
            mode="lines+markers",
            line=dict(color="#F0F6FC", width=2, dash="dot"),
        ))
        fig_rend.add_hline(y=0, line_width=1, line_color="rgba(255, 255, 255, 0.3)")
        fig_rend.update_layout(
            title=dict(text="Aporte mensual por activo ($)", y=0.96),
            barmode="relative",
            yaxis_title="Interés / retorno ($)",
            hovermode="x unified",
            margin=dict(t=55, b=90, l=50, r=20),
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig_rend, width="stretch")

with tab3:
    x_labels = [str(c) for c in matriz_dcf.columns]
    y_labels = [str(i) for i in matriz_dcf.index]
    valor_base = float(kpis["valor_presente_dcf"])

    texto_celdas = []
    pos_base = None
    for r_idx, fila in enumerate(matriz_dcf.values):
        fila_txt = []
        for c_idx, val in enumerate(fila):
            val_f = float(val)
            es_base = ("★" in y_labels[r_idx]) and ("★" in x_labels[c_idx])
            if es_base:
                pos_base = (c_idx, r_idx)
                fila_txt.append(
                    f"<b>${val_f:,.0f}</b><br>"
                    f"<span style='font-size:11px; color:#00CC96;'>● Escenario Base</span>"
                )
            else:
                var_pct = ((val_f / valor_base) - 1.0) * 100.0 if valor_base != 0 else 0.0
                fila_txt.append(
                    f"<b>${val_f:,.0f}</b><br>"
                    f"<span style='font-size:11px; color:#CBD5E1;'>({var_pct:+.1f}%)</span>"
                )
        texto_celdas.append(fila_txt)

    escala_financiera = [
        [0.0, "#6E1423"],
        [0.25, "#7C2D12"],
        [0.5, "#1E293B"],
        [0.75, "#065F46"],
        [1.0, "#047857"],
    ]

    fig_heat = go.Figure(data=go.Heatmap(
        z=matriz_dcf.values,
        x=x_labels,
        y=y_labels,
        colorscale=escala_financiera,
        text=texto_celdas,
        texttemplate="%{text}",
        textfont=dict(size=13, color="#F8FAFC"),
        xgap=4,
        ygap=4,
        colorbar=dict(
            title=dict(text="Valuación DCF", font=dict(color="#CBD5E1", size=12)),
            tickprefix="$",
            tickformat=",.0f",
            tickfont=dict(color="#CBD5E1", size=11),
            thickness=14,
        ),
        hovertemplate=(
            "<b>Crecimiento mensual:</b> %{x}<br>"
            "<b>Tasa de descuento:</b> %{y}<br>"
            "<b>Valuación DCF:</b> $%{z:,.0f}<extra></extra>"
        ),
    ))

    if pos_base is not None:
        c_b, r_b = pos_base
        fig_heat.add_shape(
            type="rect",
            x0=c_b - 0.48,
            x1=c_b + 0.48,
            y0=r_b - 0.48,
            y1=r_b + 0.48,
            line=dict(color="#00CC96", width=2.5),
        )

    fig_heat.update_layout(
        title=dict(
            text="Matriz de sensibilidad DCF: WACC anual vs. crecimiento mensual de ventas",
            font=dict(size=16, color="#F0F6FC"),
            y=0.97,
        ),
        xaxis=dict(
            title=dict(text="Escenarios de crecimiento mensual de ventas", font=dict(color="#94A3B8", size=12)),
            type="category",
            side="top",
            tickfont=dict(size=12, color="#F0F6FC"),
            showgrid=False,
        ),
        yaxis=dict(
            title=dict(text="Costo de capital (WACC anual)", font=dict(color="#94A3B8", size=12)),
            type="category",
            autorange="reversed",
            tickfont=dict(size=12, color="#F0F6FC"),
            showgrid=False,
        ),
        plot_bgcolor="#0D1117",
        paper_bgcolor="rgba(0,0,0,0)",
        height=440,
        margin=dict(t=110, b=30, l=120, r=40),
    )
    st.plotly_chart(fig_heat, width="stretch")

# --- Tabla formateada y exportación ---
df_display = df_proy[[
    "fecha",
    "ingresos",
    "ventas_equilibrio",
    "egresos_totales",
    "flujo_operativo",
    "rendimiento_tesoreria",
    "caja_acumulada",
]].rename(columns={
    "fecha": "Fecha",
    "ingresos": "Ingresos",
    "ventas_equilibrio": "Ventas de equilibrio",
    "egresos_totales": "Egresos totales",
    "flujo_operativo": "Flujo operativo",
    "rendimiento_tesoreria": "Rendimiento cartera",
    "caja_acumulada": "Caja acumulada",
})

cols_moneda = [
    "Ingresos",
    "Ventas de equilibrio",
    "Egresos totales",
    "Flujo operativo",
    "Rendimiento cartera",
    "Caja acumulada",
]

st.subheader("Detalle mensual proyectado")
st.dataframe(
    df_display.style.format({col: "${:,.2f}" for col in cols_moneda}),
    width="stretch",
    hide_index=True,
)

col_exp1, col_exp2, _ = st.columns([1.2, 1.4, 2.4])
col_exp1.download_button(
    label="Exportar proyección (.csv)",
    data=df_display.to_csv(index=False).encode("utf-8"),
    file_name="proyeccion_flujo_tesoreria.csv",
    mime="text/csv",
    width="stretch",
)

pdf_bytes = generar_informe_pdf(
    df_proy=df_proy,
    df_detalle_cartera=df_detalle_cartera,
    kpis=kpis,
    wacc=wacc,
    caja_ini=caja_ini,
    memo_ia=st.session_state.get("memo_ejecutivo"),
)
col_exp2.download_button(
    label="Descargar Informe Ejecutivo (.pdf)",
    data=pdf_bytes,
    file_name="informe_ejecutivo_fpa.pdf",
    mime="application/pdf",
    width="stretch",
)

# --- Copiloto de IA ---
st.divider()
st.subheader("Copiloto financiero y de inversiones (IA)")
st.write("Generá un memorándum ejecutivo completo para directorio o consultale directamente sobre tus números actuales.")

if "chat_cfo" not in st.session_state:
    st.session_state["chat_cfo"] = []

if st.button("Generar diagnóstico ejecutivo completo con IA", type="primary"):
    with st.spinner("Redactando memorándum de directorio (solvencia, spread vs. WACC, riesgo y plan de acción)..."):
        st.session_state["memo_ejecutivo"] = generar_diagnostico_financiero(
            df_proy, kpis, resumen_cartera, wacc
        )

if "memo_ejecutivo" in st.session_state:
    with st.container(border=True):
        st.markdown(st.session_state["memo_ejecutivo"])
    st.download_button(
        label="Descargar memo ejecutivo (.md)",
        data=st.session_state["memo_ejecutivo"].encode("utf-8"),
        file_name="memo_ejecutivo_tesoreria.md",
        mime="text/markdown",
    )

col_chat_hdr, col_chat_clr = st.columns([4, 1])
col_chat_hdr.markdown("#### Consultá al CFO Virtual sobre esta simulación")
if st.session_state["chat_cfo"]:
    if col_chat_clr.button("Limpiar chat", width="stretch"):
        st.session_state["chat_cfo"] = []
        st.rerun()

for msg in st.session_state["chat_cfo"]:
    with st.chat_message(msg["rol"]):
        st.markdown(msg["texto"])

if pregunta_usuario := st.chat_input("Escribí tu pregunta financiera (ej. ¿Conviene subir GLD o bajar QQQ?)..."):
    st.session_state["chat_cfo"].append({"rol": "user", "texto": pregunta_usuario})
    with st.chat_message("user"):
        st.markdown(pregunta_usuario)

    with st.chat_message("assistant"):
        with st.spinner("Analizando escenarios y cartera..."):
            respuesta_cfo = responder_consulta_cfo(
                pregunta_usuario,
                df_proy,
                kpis,
                resumen_cartera,
                wacc,
                st.session_state["chat_cfo"],
            )
        st.markdown(respuesta_cfo)

    st.session_state["chat_cfo"].append({"rol": "assistant", "texto": respuesta_cfo})