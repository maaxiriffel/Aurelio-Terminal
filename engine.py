import numpy as np
import pandas as pd


def generar_datos_ejemplo(meses_hist: int = 12) -> pd.DataFrame:
    fechas = pd.date_range(end=pd.Timestamp.today().replace(day=1), periods=meses_hist, freq="MS")
    rng = np.random.default_rng(42)
    base_ingresos = np.linspace(12_000_000, 16_500_000, meses_hist) * rng.uniform(0.95, 1.05, meses_hist)
    costos_variables = base_ingresos * rng.uniform(0.42, 0.48, meses_hist)
    gastos_fijos = np.linspace(4_200_000, 5_100_000, meses_hist)
    return pd.DataFrame({
        "fecha": fechas,
        "ingresos": np.round(base_ingresos, 2),
        "costos_variables": np.round(costos_variables, 2),
        "gastos_fijos": np.round(gastos_fijos, 2),
    })


def proyectar_flujo_y_portafolio(
    df_hist: pd.DataFrame,
    meses: int,
    crec_ventas: float,
    inf_costos: float,
    resumen_cartera: dict,
    wacc: float,
    caja_ini: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    ultima_fila = df_hist.iloc[-1]
    ing_base = float(ultima_fila["ingresos"])
    ratio_cv = (df_hist["costos_variables"] / df_hist["ingresos"].replace(0, np.nan)).dropna().mean()
    ratio_cv = float(ratio_cv) if pd.notna(ratio_cv) else 0.45
    gf_base = float(ultima_fila["gastos_fijos"])

    peso_mm = resumen_cartera["peso_mm_ef"]
    tna_mm = resumen_cartera["tna_mm"]
    activos = resumen_cartera["activos"]

    tna_ponderada = peso_mm * tna_mm + sum(a["peso_ef"] * a["cagr"] for a in activos)
    var_cartera = sum((a["peso_ef"] * a["volatilidad"]) ** 2 for a in activos)
    vol_ponderada = float(np.sqrt(var_cartera))

    tasa_mensual_cartera = (1.0 + tna_ponderada) ** (1.0 / 12.0) - 1.0
    tasa_mensual_mm = (1.0 + tna_mm) ** (1.0 / 12.0) - 1.0
    tasa_mensual_wacc = (1.0 + wacc) ** (1.0 / 12.0) - 1.0
    vol_mensual = vol_ponderada / np.sqrt(12.0)

    fechas_proy = pd.date_range(
        start=pd.to_datetime(ultima_fila["fecha"]) + pd.offsets.MonthBegin(1),
        periods=meses,
        freq="MS",
    )

    filas_proy = []
    filas_aportes = []
    caja_actual = float(caja_ini)
    vp_flujos_dcf = 0.0
    margenes_seguridad = []

    for m in range(1, meses + 1):
        ing = ing_base * ((1.0 + crec_ventas) ** m)
        cv = ing * ratio_cv
        gf = gf_base * ((1.0 + inf_costos) ** m)
        egresos = cv + gf
        flujo_op = ing - egresos

        margen_contribucion = 1.0 - ratio_cv
        ventas_eq = (gf / margen_contribucion) if margen_contribucion > 0 else 0.0
        ms_pct = ((ing - ventas_eq) / ing * 100.0) if ing > 0 else 0.0
        margenes_seguridad.append(ms_pct)

        base_invertible = max(0.0, caja_actual)
        rend_mm = base_invertible * peso_mm * tasa_mensual_mm
        aporte_mes = {"fecha": fechas_proy[m - 1]}
        if peso_mm > 0:
            aporte_mes["Liquidez T+0"] = rend_mm

        rend_activos = 0.0
        for act in activos:
            tasa_m_act = (1.0 + act["cagr"]) ** (1.0 / 12.0) - 1.0
            ganancia_act = base_invertible * act["peso_ef"] * tasa_m_act
            rend_activos += ganancia_act
            aporte_mes[act["ticker"]] = ganancia_act

        rend_total = rend_mm + rend_activos
        caja_actual = caja_actual + flujo_op + rend_total

        factor_desc = (1.0 + tasa_mensual_wacc) ** m
        flujo_libre_mes = flujo_op + rend_total
        vp_flujos_dcf += flujo_libre_mes / factor_desc
        caja_descontada = caja_actual / factor_desc

        banda = max(0.0, caja_actual) * vol_mensual * np.sqrt(m) * 1.28
        filas_proy.append({
            "fecha": fechas_proy[m - 1],
            "ingresos": ing,
            "costos_variables": cv,
            "gastos_fijos": gf,
            "egresos_totales": egresos,
            "ventas_equilibrio": ventas_eq,
            "flujo_operativo": flujo_op,
            "rendimiento_tesoreria": rend_total,
            "caja_acumulada": caja_actual,
            "caja_descontada_vp": caja_descontada,
            "caja_optimista": caja_actual + banda,
            "caja_pesimista": max(0.0, caja_actual - banda),
        })
        filas_aportes.append(aporte_mes)

    df_proy = pd.DataFrame(filas_proy)
    df_aportes = pd.DataFrame(filas_aportes)

    kpis = {
        "flujo_operativo_total": float(df_proy["flujo_operativo"].sum()),
        "interes_tesoreria": float(df_proy["rendimiento_tesoreria"].sum()),
        "caja_final": float(df_proy["caja_acumulada"].iloc[-1]),
        "valor_presente_dcf": float(caja_ini + vp_flujos_dcf),
        "tna_ponderada": float(tna_ponderada),
        "volatilidad_ponderada": float(vol_ponderada),
        "margen_seguridad_promedio": float(np.mean(margenes_seguridad)),
    }
    return df_proy, df_aportes, kpis


def calcular_matriz_sensibilidad_dcf(
    df_hist: pd.DataFrame,
    meses: int,
    crec_ventas: float,
    inf_costos: float,
    tna_ponderada: float,
    wacc: float,
    caja_ini: float,
) -> pd.DataFrame:
    """Construye una matriz 5x5 centrada dinámicamente en el WACC y crecimiento elegidos."""
    deltas_wacc = [-0.04, -0.02, 0.0, 0.02, 0.04]
    deltas_crec = [-0.02, -0.01, 0.0, 0.01, 0.02]

    tasas_wacc = [max(0.01, round(wacc + d, 4)) for d in deltas_wacc]
    tasas_crec = [round(crec_ventas + d, 4) for d in deltas_crec]

    resumen_ficticio = {
        "peso_mm_ef": 1.0,
        "tna_mm": tna_ponderada,
        "activos": [],
    }

    matriz = {}
    for c in tasas_crec:
        etiqueta_col = f"{c * 100:+.1f}% ★" if abs(c - crec_ventas) < 1e-6 else f"{c * 100:+.1f}%"
        columna_valores = []
        for w in tasas_wacc:
            _, _, kpis_esc = proyectar_flujo_y_portafolio(
                df_hist, meses, c, inf_costos, resumen_ficticio, w, caja_ini
            )
            columna_valores.append(kpis_esc["valor_presente_dcf"])
        matriz[etiqueta_col] = columna_valores

    etiquetas_filas = [
        f"WACC {w * 100:.1f}% ★" if abs(w - wacc) < 1e-6 else f"WACC {w * 100:.1f}%"
        for w in tasas_wacc
    ]
    return pd.DataFrame(matriz, index=etiquetas_filas)