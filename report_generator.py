import io
from datetime import datetime
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _limpiar_markdown_para_pdf(texto_md: str) -> list[tuple[str, str]]:
    """Convierte líneas de Markdown básico en bloques estructurados para ReportLab."""
    bloques = []
    for linea in texto_md.splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        if limpia.startswith("### "):
            bloques.append(("h3", limpia[4:]))
        elif limpia.startswith("## "):
            bloques.append(("h2", limpia[3:]))
        elif limpia.startswith("# "):
            bloques.append(("h1", limpia[2:]))
        elif limpia.startswith(("- ", "* ")):
            bloques.append(("bullet", f"• {limpia[2:]}"))
        else:
            bloques.append(("body", limpia))
    return bloques


def _formatear_negritas_rl(texto: str) -> str:
    """Transforma **texto** en etiquetas <b>texto</b> válidas para Paragraph."""
    partes = texto.split("**")
    resultado = []
    for idx, trozo in enumerate(partes):
        trozo_escapado = trozo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if idx % 2 == 1:
            resultado.append(f"<b>{trozo_escapado}</b>")
        else:
            resultado.append(trozo_escapado)
    return "".join(resultado)


def generar_informe_pdf(
    df_proy: pd.DataFrame,
    df_detalle_cartera: pd.DataFrame,
    kpis: dict,
    wacc: float,
    caja_ini: float,
    memo_ia: str | None = None,
) -> bytes:
    """Genera un informe ejecutivo en PDF listo para presentar en directorio."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )

    estilos = getSampleStyleSheet()
    estilo_eyebrow = ParagraphStyle(
        "Eyebrow",
        parent=estilos["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#00A878"),
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    estilo_titulo = ParagraphStyle(
        "TituloDoc",
        parent=estilos["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0D1117"),
        spaceAfter=6,
    )
    estilo_subtitulo = ParagraphStyle(
        "SubtituloDoc",
        parent=estilos["Normal"],
        fontSize=10.5,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=16,
    )
    estilo_seccion = ParagraphStyle(
        "SeccionDoc",
        parent=estilos["Heading2"],
        fontSize=13,
        textColor=colors.HexColor("#0D1117"),
        spaceBefore=12,
        spaceAfter=8,
    )
    estilo_cuerpo = ParagraphStyle(
        "CuerpoDoc",
        parent=estilos["Normal"],
        fontSize=9.8,
        leading=14,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=6,
    )
    estilo_bullet = ParagraphStyle(
        "BulletDoc",
        parent=estilo_cuerpo,
        leftIndent=12,
        spaceAfter=4,
    )

    elementos = []
    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")

    # --- Encabezado Ejecutivo ---
    elementos.append(Paragraph("TERMINAL FP&A Y TESORERÍA CORPORATIVA", estilo_eyebrow))
    elementos.append(Paragraph("Informe Ejecutivo de Flujo de Caja, Portafolio y Valuación", estilo_titulo))
    elementos.append(
        Paragraph(
            f"Fecha de emisión: {fecha_emision} · Horizonte proyectado: {len(df_proy)} meses · "
            f"Caja inicial: ${caja_ini:,.0f} · WACC anual: {wacc * 100:.1f}%",
            estilo_subtitulo,
        )
    )

    # --- Tabla de KPIs ---
    elementos.append(Paragraph("1. Resumen Ejecutivo de Métricas Clave", estilo_seccion))
    spread_bps = int(round((kpis["tna_ponderada"] - wacc) * 10_000))
    datos_kpi = [
        ["Flujo Operativo Proyectado", "Retorno Cartera Tesorería", "Caja Final Base", f"Valuación DCF (WACC {wacc*100:.0f}%)"],
        [
            f"${kpis['flujo_operativo_total']:,.0f}",
            f"${kpis['interes_tesoreria']:,.0f}",
            f"${kpis['caja_final']:,.0f}",
            f"${kpis['valor_presente_dcf']:,.0f}",
        ],
        [
            f"Margen seg.: {kpis['margen_seguridad_promedio']:+.1f}%",
            f"TNA: {kpis['tna_ponderada']*100:.1f}% ({spread_bps:+d} bps)",
            f"Volatilidad: {kpis['volatilidad_ponderada']*100:.1f}%",
            f"Dif. vs nominal: ${kpis['valor_presente_dcf'] - kpis['caja_final']:+,.0f}",
        ],
    ]
    tabla_kpi = Table(datos_kpi, colWidths=[4.3 * cm] * 4)
    tabla_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D1117")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F3F4F6")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0D1117")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F9FAFB")),
        ("FONTSIZE", (0, 2), (-1, 2), 8),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor("#4B5563")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elementos.append(tabla_kpi)
    elementos.append(Spacer(1, 0.4 * cm))

    # --- Tabla de Portafolio ---
    if not df_detalle_cartera.empty:
        elementos.append(Paragraph("2. Asignación Estratégica de Tesorería", estilo_seccion))
        enc_cart = ["Activo", "Instrumento", "Clase", "Peso (%)", "Retorno Anual", "Volatilidad"]
        filas_cart = [enc_cart]
        for _, r in df_detalle_cartera.iterrows():
            filas_cart.append([
                str(r["Activo"]),
                str(r["Nombre"])[:34],
                str(r["Clase"]),
                f"{r['Ponderación (%)']:.1f}%",
                str(r["Retorno anual (CAGR)"]),
                str(r["Volatilidad anual"]),
            ])
        tabla_cart = Table(filas_cart, colWidths=[1.8 * cm, 6.2 * cm, 2.6 * cm, 2.1 * cm, 2.3 * cm, 2.2 * cm])
        tabla_cart.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elementos.append(tabla_cart)
        elementos.append(Spacer(1, 0.4 * cm))

    # --- Tabla de Proyección Mensual ---
    elementos.append(Paragraph("3. Proyección Mensual de Flujo de Caja", estilo_seccion))
    enc_flujo = ["Mes", "Ingresos", "Break-Even", "Egresos", "Flujo Op.", "Ret. Cartera", "Caja Acum."]
    filas_flujo = [enc_flujo]
    for _, r in df_proy.iterrows():
        filas_flujo.append([
            pd.to_datetime(r["fecha"]).strftime("%Y-%m"),
            f"${r['ingresos']:,.0f}",
            f"${r['ventas_equilibrio']:,.0f}",
            f"${r['egresos_totales']:,.0f}",
            f"${r['flujo_operativo']:,.0f}",
            f"${r['rendimiento_tesoreria']:,.0f}",
            f"${r['caja_acumulada']:,.0f}",
        ])
    tabla_flujo = Table(filas_flujo, colWidths=[1.8 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm, 2.5 * cm, 2.4 * cm, 2.7 * cm])
    tabla_flujo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00A878")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.append(tabla_flujo)

    # --- Diagnóstico IA si fue generado ---
    if memo_ia:
        elementos.append(PageBreak())
        elementos.append(Paragraph("COPILOTO FINANCIERO Y ESTRATÉGICO", estilo_eyebrow))
        elementos.append(Paragraph("4. Memorándum Ejecutivo de Análisis y Recomendaciones", estilo_titulo))
        elementos.append(Spacer(1, 0.2 * cm))

        for tipo, texto in _limpiar_markdown_para_pdf(memo_ia):
            texto_fmt = _formatear_negritas_rl(texto)
            if tipo in ("h1", "h2", "h3"):
                elementos.append(Paragraph(texto_fmt, estilo_seccion))
            elif tipo == "bullet":
                elementos.append(Paragraph(texto_fmt, estilo_bullet))
            else:
                elementos.append(Paragraph(texto_fmt, estilo_cuerpo))

    doc.build(elementos)
    return buffer.getvalue()