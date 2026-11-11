"""Ficha de consulta de área (entregable A1 del servicio), en HTML imprimible."""
from __future__ import annotations

import html
from datetime import datetime

import pandas as pd

from .costos import NOMBRE_REGIMEN, Costos
from .geo import Evaluacion


def _tabla(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<p><i>Ninguno.</i></p>"
    return df.to_html(index=False, border=0, classes="t", escape=True)


def generar(cliente: str, lugar: str, lon: float, lat: float, ev: Evaluacion, costos: Costos,
            calendario: pd.DataFrame, fecha_tc: str) -> str:
    e = html.escape
    celdas = ev.cuadriculas.drop(columns="geometry")[
        ["cuadricula", "este_min", "norte_min", "ha_libres", "ha_con_derecho", "ha_extinguidas", "ha_prohibidas", "estado"]
    ].rename(columns={"cuadricula": "N.º", "este_min": "Este (m)", "norte_min": "Norte (m)",
                      "ha_libres": "Ha libres", "ha_con_derecho": "Ha con derecho",
                      "ha_extinguidas": "Ha extinguidas", "ha_prohibidas": "Ha prohibidas", "estado": "Estado"})
    alertas = "".join(f"<li>{e(a)}</li>" for a in ev.alertas) or "<li>Sin alertas.</li>"
    prox = calendario.head(12).copy()
    if not prox.empty:
        prox["Fecha"] = pd.to_datetime(prox["Fecha"]).dt.strftime("%d/%m/%Y")
        prox = prox[["Fecha", "Obligación", "Entidad", "Fecha confirmada"]]
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Ficha de consulta de área · Consorcio GAIA</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:24px auto;color:#1d2a24;padding:0 16px}}
h1{{color:#1b5e3b;margin-bottom:0}} h2{{color:#1b5e3b;border-bottom:2px solid #d9c27a;padding-bottom:4px;margin-top:28px}}
.v{{font-size:1.4em;font-weight:700;padding:10px 14px;background:#f4efe0;border-left:6px solid #1b5e3b}}
table.t{{border-collapse:collapse;width:100%;font-size:.88em}} table.t th{{background:#1b5e3b;color:#fff;text-align:left;padding:5px}}
table.t td{{border-bottom:1px solid #ddd;padding:4px 5px}} .muted{{color:#666;font-size:.85em}}
</style></head><body>
<h1>Consorcio GAIA · Ficha de consulta de área</h1>
<p class="muted">Generada el {datetime.now():%d/%m/%Y %H:%M} con datos en vivo del catastro minero de INGEMMET (GEOCATMIN).</p>
<p><b>Cliente:</b> {e(cliente or "—")} &nbsp; <b>Lugar:</b> {e(lugar or "—")}<br>
<b>Punto:</b> lat {lat:.5f}, lon {lon:.5f} &nbsp; <b>Régimen:</b> {e(NOMBRE_REGIMEN[costos.regimen])}
&nbsp; <b>Área solicitada:</b> {ev.ha_solicitadas:,} ha ({len(ev.cuadriculas)} cuadrículas)</p>
<div class="v">Resultado: {e(ev.veredicto)} · {ev.ha_libres:,.0f} de {ev.ha_solicitadas:,} ha libres</div>
<h2>Alertas</h2><ul>{alertas}</ul>
<h2>Cuadrículas propuestas (UTM WGS84, esquina suroeste)</h2>{_tabla(celdas)}
<h2>Derechos mineros superpuestos</h2>{_tabla(ev.superposiciones)}
<h2>Áreas restringidas</h2>{_tabla(ev.restricciones)}
<h2>Pagos al Estado (referenciales)</h2>
<table class="t"><tr><th>Concepto</th><th>Monto</th></tr>
<tr><td>Derecho de trámite (TUPA)</td><td>S/ {costos.derecho_tramite:,.2f}</td></tr>
<tr><td>Derecho de vigencia del 1.er año ({costos.hectareas:,.0f} ha)</td><td>US$ {costos.vigencia_usd:,.2f} = S/ {costos.vigencia_soles:,.2f}</td></tr>
<tr><td><b>Total al presentar el petitorio</b></td><td><b>S/ {costos.total_presentacion:,.2f}</b></td></tr>
<tr><td>Producción mínima anual exigible (referencial)</td><td>S/ {costos.produccion_minima_soles:,.2f}</td></tr></table>
<p class="muted">Tipo de cambio venta SBS del BCRP: {costos.tipo_cambio:.3f} ({e(fecha_tc)}). No incluye penalidad ni honorarios.</p>
<h2>Próximas obligaciones</h2>{_tabla(prox)}
<p class="muted" style="margin-top:30px">Esta ficha es referencial y no es una opinión legal. El catastro de INGEMMET se actualiza a diario
y tiene carácter de consulta. Las cuadrículas se alinean a kilómetros enteros UTM. Antes de presentar un petitorio,
confirme el área en GEOCATMIN y los montos en el TUPA vigente.</p>
</body></html>"""
