"""Cuánto paga el cliente al Estado por su petitorio y cada año para mantenerlo.

Montos referenciales al 11/11/2026 (INGEMMET, Ley 27651, UIT 2026 = S/ 5,500).
La penalidad no está incluida: depende de los años sin producir y se pide la
liquidación a INGEMMET.
"""
from __future__ import annotations

from dataclasses import dataclass

UIT_2026 = 5_500
DERECHO_TRAMITE_SOLES = 420  # INGEMMET, régimen general. PPM/PMA ante GORE: confirmar TUPA regional.

# Derecho de vigencia (US$ por ha y año) y producción mínima anual (fracción de UIT por ha)
REGIMENES = {
    "General": {"vigencia_usd_ha": 3.00, "prod_min_uit_ha": 1.00, "max_ha": None},
    "PPM": {"vigencia_usd_ha": 1.00, "prod_min_uit_ha": 0.10, "max_ha": 2_000},
    "PMA": {"vigencia_usd_ha": 0.50, "prod_min_uit_ha": 0.05, "max_ha": 1_000},
}

NOMBRE_REGIMEN = {
    "General": "Régimen general",
    "PPM": "Pequeño Productor Minero (PPM)",
    "PMA": "Productor Minero Artesanal (PMA)",
}


@dataclass
class Costos:
    regimen: str
    hectareas: float
    tipo_cambio: float
    derecho_tramite: float
    vigencia_usd: float
    vigencia_soles: float
    total_presentacion: float
    vigencia_anual_soles: float
    produccion_minima_soles: float


def calcular(hectareas: float, regimen: str, tipo_cambio: float,
             derecho_tramite: float = DERECHO_TRAMITE_SOLES, uit: float = UIT_2026) -> Costos:
    if regimen not in REGIMENES:
        raise ValueError(f"Régimen desconocido: {regimen}")
    r = REGIMENES[regimen]
    vig_usd = hectareas * r["vigencia_usd_ha"]
    vig_sol = vig_usd * tipo_cambio
    return Costos(
        regimen=regimen, hectareas=hectareas, tipo_cambio=tipo_cambio,
        derecho_tramite=derecho_tramite, vigencia_usd=round(vig_usd, 2), vigencia_soles=round(vig_sol, 2),
        total_presentacion=round(derecho_tramite + vig_sol, 2), vigencia_anual_soles=round(vig_sol, 2),
        produccion_minima_soles=round(hectareas * uit * r["prod_min_uit_ha"], 2),
    )
