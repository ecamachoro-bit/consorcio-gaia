"""Calendario personalizado de obligaciones del pequeño minero (próximos 12 meses).

Fuente de las reglas: data/obligaciones.csv, armado con el Calendario 2026 de
obligaciones de Swiss Better Gold y las normas de INGEMMET/MINEM. Las fechas de
2027 repiten el patrón de 2026 y se marcan como "estimada" hasta que salgan los
cronogramas oficiales.
"""
from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

import pandas as pd

RUTA_REGLAS = Path(__file__).resolve().parent.parent / "data" / "obligaciones.csv"

PERFILES = {
    "titular": "Es titular de una concesión minera",
    "reinfo": "Está inscrito en el REINFO",
    "ruc": "Tiene RUC con actividad minera",
    "empleador": "Tiene trabajadores en planilla",
    "explosivos": "Usa explosivos (SUCAMEC)",
    "agua": "Usa agua con licencia (ANA)",
    "empresa": "Es persona jurídica (empresa)",
}


def cargar_reglas(ruta: Path = RUTA_REGLAS) -> pd.DataFrame:
    return pd.read_csv(ruta, dtype=str).fillna("")


def _fecha_segura(anio: int, mes: int, dia: int) -> date:
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def _ocurrencias(regla: pd.Series, desde: date, hasta: date) -> list[date]:
    if regla["frecuencia"] == "unica":
        f = date.fromisoformat(regla["fecha_unica"])
        return [f] if desde <= f <= hasta else []
    dia = int(regla["dia"])
    if regla["frecuencia"] == "mensual":
        meses = range(1, 13)
    else:
        meses = [int(m) for m in regla["meses"].split("|")]
    fechas = []
    for anio in (desde.year, desde.year + 1):
        for m in meses:
            f = _fecha_segura(anio, m, dia)
            if desde <= f <= hasta:
                fechas.append(f)
    return fechas


def calendario(perfil: set[str], hoy: date | None = None, meses: int = 12,
               reglas: pd.DataFrame | None = None) -> pd.DataFrame:
    """Obligaciones que le tocan al cliente según su perfil, de hoy a +meses."""
    hoy = hoy or date.today()
    fin_mes = hoy.month + meses
    hasta = _fecha_segura(hoy.year + (fin_mes - 1) // 12, (fin_mes - 1) % 12 + 1, hoy.day)
    reglas = cargar_reglas() if reglas is None else reglas
    filas = []
    for _, r in reglas[reglas["perfil"].isin(perfil)].iterrows():
        for f in _ocurrencias(r, hoy, hasta):
            filas.append({
                "Fecha": f, "Obligación": r["obligacion"], "Tipo": r["tipo"], "Entidad": r["entidad"],
                "Nota": r["nota"], "Si no cumple": r["si_no_cumple"], "Días": (f - hoy).days,
                "Fecha confirmada": "Sí (2026)" if f.year <= 2026 else "Estimada (patrón 2026)",
            })
    cols = ["Fecha", "Obligación", "Tipo", "Entidad", "Nota", "Si no cumple", "Días", "Fecha confirmada"]
    if not filas:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(filas)[cols].sort_values(["Fecha", "Tipo"]).reset_index(drop=True)
