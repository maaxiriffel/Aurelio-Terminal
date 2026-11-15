import os
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _fecha_actual_espanol() -> str:
    """Devuelve la fecha actual del sistema formateada en español."""
    ahora = datetime.now()
    return f"{ahora.day} de {MESES_ES[ahora.month - 1]} de {ahora.year}"


def _obtener_api_key() -> str | None:
    """Lee GROQ_API_KEY (o GEMINI_API_KEY si se pegó ahí la clave gsk_) desde .env o Secrets."""
    load_dotenv(override=True)
    for nombre_var in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        clave = os.getenv(nombre_var)
        if not clave:
            try:
                clave = st.secrets.get(nombre_var)
            except Exception:
                clave = None
        if clave:
            limpia = clave.strip().strip('"').strip("'")
            if limpia.startswith("gsk_"):
                return limpia
    return None


def _prioridad_modelo_groq(model_id: str) -> tuple[int, str]:
    """Ordena los modelos activos de mayor a menor capacidad de análisis financiero."""
    m = model_id.lower()
    if any(tag in m for tag in ("120b", "70b", "maverick", "32b", "r1")):
        return (0, m)
    if any(tag in m for tag in ("llama-4", "gpt-oss", "qwen", "deepseek", "llama-3")):
        return (1, m)
    return (2, m)


def _obtener_modelos_groq_activos(headers: dict) -> list[str]:
    """Consulta en vivo qué modelos de texto están habilitados en tu clave de Groq."""
    if st.session_state.get("groq_modelos_activos"):
        return st.session_state["groq_modelos_activos"]

    excluidos = ("whisper", "tts", "playai", "guard", "safeguard", "embedding", "orpheus")
    modelos_validos: list[str] = []

    try:
        resp = requests.get(GROQ_MODELS_URL, headers=headers, timeout=15)
        if resp.status_code == 200:
            for item in resp.json().get("data", []):
                mid = str(item.get("id", "")).strip()
                activo = item.get("active", True)
                if mid and activo and not any(tag in mid.lower() for tag in excluidos):
                    modelos_validos.append(mid)
    except Exception:
        modelos_validos = []

    ordenados = sorted(set(modelos_validos), key=_prioridad_modelo_groq)
    if ordenados:
        st.session_state["groq_modelos_activos"] = ordenados
    return ordenados


def _generar_respuesta_ia(prompt: str) -> str:
    """Ejecuta el análisis usando automáticamente el mejor modelo activo en tu cuenta de Groq."""
    api_key = _obtener_api_key()
    if not api_key:
        return (
            "⚠️ Falta configurar tu clave gratuita de Groq (`gsk_...`). "
            "Generala gratis en [console.groq.com/keys](https://console.groq.com/keys) y pegala en tu archivo `.env` como `GROQ_API_KEY=gsk_...`."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    modelos = _obtener_modelos_groq_activos(headers)
    if not modelos:
        return "⚠️ No se pudieron listar modelos activos en Groq. Verificá tu conexión o tu clave `GROQ_API_KEY`."

    ultimo_error = ""
    for modelo in modelos:
        try:
            resp = requests.post(
                GROQ_CHAT_URL,
                headers=headers,
                json={
                    "model": modelo,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.35,
                },
                timeout=35,
            )
            if resp.status_code == 200:
                datos = resp.json()
                texto = datos["choices"][0]["message"]["content"]
                if texto and texto.strip():
                    return texto
            elif resp.status_code == 401:
                return "⚠️ La clave `GROQ_API_KEY` en tu `.env` no es válida. Verificá haberla copiado completa."
            else:
                ultimo_error = f"{modelo} -> HTTP {resp.status_code}: {resp.text[:180]}"
                continue
        except Exception as e:
            ultimo_error = f"{modelo} -> {e}"
            continue

    st.session_state.pop("groq_modelos_activos", None)
    return f"⚠️ No se pudo obtener respuesta en este momento. Reintentá en unos segundos. ({ultimo_error})"


def _construir_contexto_numerico(
    df_proy: pd.DataFrame,
    kpis: dict,
    resumen_cartera: dict,
    wacc: float,
) -> str:
    """Resume todos los indicadores operativos, financieros y de mercado en texto estructurado."""
    fecha_hoy = _fecha_actual_espanol()
    spread_bps = int(round((kpis["tna_ponderada"] - wacc) * 10_000))
    detalle_activos = [
        f"- Liquidez inmediata T+0: {resumen_cartera['peso_mm_ef']*100:.1f}% del portafolio "
        f"(TNA pactada: {resumen_cartera['tna_mm']*100:.1f}%)"
    ]
    for a in resumen_cartera["activos"]:
        nombre_act = a.get("nombre", a["ticker"])
        detalle_activos.append(
            f"- {a['ticker']} ({nombre_act} - {a['clase']}): {a['peso_ef']*100:.1f}% del portafolio "
            f"(CAGR 2y: {a['cagr']*100:.1f}%, Volatilidad anual: {a['volatilidad']*100:.1f}%)"
        )

    primer_mes = df_proy.iloc[0]
    ultimo_mes = df_proy.iloc[-1]
    ingresos_totales = float(df_proy["ingresos"].sum())
    egresos_totales = float(df_proy["egresos_totales"].sum())
    margen_op_pct = (kpis["flujo_operativo_total"] / ingresos_totales * 100.0) if ingresos_totales > 0 else 0.0

    ventas_eq_ini = float(primer_mes["ventas_equilibrio"])
    ventas_eq_fin = float(ultimo_mes["ventas_equilibrio"])
    caja_pes_fin = float(ultimo_mes["caja_pesimista"])
    caja_opt_fin = float(ultimo_mes["caja_optimista"])
    fecha_ini = pd.to_datetime(primer_mes["fecha"]).strftime("%Y-%m")
    fecha_fin = pd.to_datetime(ultimo_mes["fecha"]).strftime("%Y-%m")

    return f"""
DATOS DEL MODELO FINANCIERO Y TESORERÍA:
- Fecha actual de emisión del análisis: {fecha_hoy}
- Horizonte proyectado: {len(df_proy)} meses (desde {fecha_ini} hasta {fecha_fin})
- Facturación total proyectada: ${ingresos_totales:,.0f}
- Egresos totales proyectados: ${egresos_totales:,.0f}
- Flujo operativo acumulado: ${kpis['flujo_operativo_total']:,.0f} (margen operativo neto: {margen_op_pct:.1f}%)
- Ventas de equilibrio (break-even) mes 1: ${ventas_eq_ini:,.0f}
- Ventas de equilibrio (break-even) mes final: ${ventas_eq_fin:,.0f}
- Margen de seguridad operativo promedio sobre break-even: {kpis['margen_seguridad_promedio']:+.1f}%
- Caja final proyectada (escenario base): ${kpis['caja_final']:,.0f}
- Escenario pesimista mes final: ${caja_pes_fin:,.0f}
- Escenario optimista mes final: ${caja_opt_fin:,.0f}
- Costo de capital (WACC anual): {wacc*100:.1f}%
- Valuación DCF acumulada (descontada a WACC): ${kpis['valor_presente_dcf']:,.0f}
- Rendimiento financiero total generado por tesorería: ${kpis['interes_tesoreria']:,.0f}
- Retorno esperado ponderado de cartera: {kpis['tna_ponderada']*100:.2f}% anual (Spread vs WACC: {spread_bps:+d} bps)
- Volatilidad anualizada de cartera: {kpis['volatilidad_ponderada']*100:.2f}%

COMPOSICIÓN DETALLADA DE LA CARTERA DE TESORERÍA:
{chr(10).join(detalle_activos)}
""".strip()


def generar_diagnostico_financiero(
    df_proy: pd.DataFrame,
    kpis: dict,
    resumen_cartera: dict,
    wacc: float,
) -> str:
    """Genera un memorándum ejecutivo profundo para directorio y comité de inversiones."""
    fecha_hoy = _fecha_actual_espanol()
    contexto = _construir_contexto_numerico(df_proy, kpis, resumen_cartera, wacc)
    spread_bps = int(round((kpis["tna_ponderada"] - wacc) * 10_000))
    caja_pes_fin = float(df_proy.iloc[-1]["caja_pesimista"])

    prompt = f"""
Actuá como Director Financiero (CFO) y Estratega Senior de Tesorería Corporativa redactando un Memorándum Ejecutivo completo en español rioplatense profesional para el Directorio.
La fecha de emisión de este memorándum es exactamente **{fecha_hoy}** (usá esta fecha exacta en el encabezado y nunca inventes años pasados).
Sé exhaustivo, analítico, concreto y citá siempre los números exactos del modelo. Evitá generalidades vacías: explicá el porqué financiero detrás de cada métrica.

{contexto}

Iniciá el documento con el encabezado usando la fecha exacta `{fecha_hoy}` y luego desarrollá estas 5 secciones:

### 1. Diagnóstico Operativo y Solvencia de Caja
Analizá la generación de flujo operativo (${kpis['flujo_operativo_total']:,.0f}), la evolución del punto de equilibrio (break-even) y qué tan holgado es el margen de seguridad promedio ({kpis['margen_seguridad_promedio']:+.1f}%) frente a una eventual caída de ventas o suba de costos fijos.

### 2. Creación o Destrucción de Valor frente al WACC
Evaluá si la tesorería está rindiendo por encima o por debajo del costo de oportunidad del capital ({wacc*100:.1f}%), analizando el spread de {spread_bps:+d} bps, la caja nominal final (${kpis['caja_final']:,.0f}) y la valuación DCF descontada (${kpis['valor_presente_dcf']:,.0f}).

### 3. Radiografía Riesgo-Retorno del Portafolio de Tesorería
Evaluá activo por activo (liquidez T+0 y tickers reales) el equilibrio entre liquidez inmediata, renta fija y renta variable. Analizá si la volatilidad ponderada ({kpis['volatilidad_ponderada']*100:.1f}%) es prudente para capital de trabajo corporativo y qué activos aportan mayor retorno o riesgo.

### 4. Análisis de Estrés y Escenarios Adversos
Evaluá el impacto en caja bajo el escenario pesimista (${caja_pes_fin:,.0f}) y señalá cuál es el principal punto de vulnerabilidad del esquema actual.

### 5. Plan de Acción Recomendado (3 Decisiones Concretas)
Proponé 3 ajustes específicos y cuantificados (por ejemplo, reasignar un % exacto entre activos, ajustar el colchón de liquidez T+0 o fijar metas de margen operativo) explicando el impacto esperado en pesos y en riesgo.
"""

    return _generar_respuesta_ia(prompt)


def responder_consulta_cfo(
    pregunta: str,
    df_proy: pd.DataFrame,
    kpis: dict,
    resumen_cartera: dict,
    wacc: float,
    historial_chat: list[dict] | None = None,
) -> str:
    """Responde preguntas específicas del usuario sobre los números actuales del simulador."""
    fecha_hoy = _fecha_actual_espanol()
    contexto = _construir_contexto_numerico(df_proy, kpis, resumen_cartera, wacc)

    ultimos_mensajes = ""
    if historial_chat:
        recientes = historial_chat[-4:]
        ultimos_mensajes = "\n".join(
            f"{'Usuario' if m['rol'] == 'user' else 'CFO IA'}: {m['texto']}" for m in recientes
        )

    prompt = f"""
Sos un CFO y asesor de inversiones corporativas conversando directamente en español rioplatense profesional con el dueño/analista de la empresa sobre su tablero financiero en vivo (fecha actual: {fecha_hoy}).
Respondé de forma directa, profunda, con cálculos exactos basados en los datos actuales y sin rodeos introductorios.

{contexto}

HISTORIAL RECIENTE DE LA CONVERSACIÓN:
{ultimos_mensajes if ultimos_mensajes else "(Inicio de consulta)"}

PREGUNTA ACTUAL DEL USUARIO:
{pregunta}
"""

    return _generar_respuesta_ia(prompt)