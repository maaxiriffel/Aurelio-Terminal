# Aurelio FP&A Terminal

Terminal interactiva de planificación financiera corporativa (FP&A) y gestión estratégica de tesorería desarrollada en Python y Streamlit.

🔗 **Demo en vivo:** [Abrir Aurelio FP&A Terminal](https://TU-LINK-DE-STREAMLIT.streamlit.app)

## Funcionalidades principales
- **Proyección de Flujo de Caja:** Modelado multi-horizonte bajo escenarios base, optimista y pesimista.
- **Punto de Equilibrio y Solvencia:** Cálculo dinámico de *break-even* operativo y margen de seguridad promedio.
- **Valuación DCF & WACC:** Descuento de flujos proyectados frente al costo de capital y medición de *spread* en puntos básicos (bps).
- **Tesorería y Riesgo-Retorno:** Simulación de cartera combinando liquidez inmediata T+0 y cotizaciones reales vía `yfinance` (CAGR y volatilidad anualizada).
- **Reportes Ejecutivos:** Exportación automatizada de informes gerenciales en PDF (`ReportLab`) y Excel (`openpyxl`).
- **CFO Virtual con IA:** Generación de memorándums ejecutivos para directorio y chat analítico en tiempo real.

## Stack Tecnológico
`Python` · `Streamlit` · `Pandas` · `Plotly` · `yfinance` · `ReportLab` · `Groq API`
