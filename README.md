# Simulador de Flujo de Caja predictivo, tesorería y valuación (DCF) + IA

Aplicación financiera interactiva diseñada para proyectar flujos de caja operativos, optimizar la colocación de excedentes de liquidez (Cash Management) y estimar el Valor Presente Neto (DCF) bajo distintos escenarios macroeconómicos, complementada con un Copiloto Ejecutivo impulsado por Gemini.

## Funcionalidades Principales
- **Modelado Operativo y Sensibilidad:** Proyección dinámica a 3–12 meses de ingresos, costos variables y estructura fija con soporte para carga de datos históricos propios en CSV.
- **Optimización de Tesorería (Cash Management):** Cálculo de devengamiento financiero sobre saldos excedentes de caja y comparación frente al costo de capital (WACC).
- **Valuación por Flujo de Fondos Descontados (DCF):** Estimación en tiempo real del Valor Presente de los flujos proyectados.
- **Copiloto Financiero (IA):** Generación automatizada de memorándums ejecutivos con diagnóstico de solvencia, estrategia de *laddering* (T+0 vs. T+30/60) y alertas de riesgo operativo.

## Stack Tecnológico
- **Lenguaje y Procesamiento:** Python, Pandas, NumPy
- **Visualización e Interfaz:** Streamlit, Plotly
- **Inteligencia Artificial:** Google GenAI SDK (`gemini-3.8-flash`)