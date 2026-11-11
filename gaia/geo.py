"""Análisis geoespacial del petitorio con GeoPandas.

Herramienta del curso: GeoPandas y Folium (sesión 06).

1. Arma las cuadrículas de 100 ha (1 km x 1 km) del catastro minero alrededor del punto
   del cliente, alineadas a kilómetros enteros en UTM WGS84 (zonas 17, 18 y 19 sur).
2. Cruza (overlay) cada cuadrícula con los derechos mineros y las áreas restringidas
   que devuelve INGEMMET, y calcula cuántas hectáreas quedan realmente libres.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.ops import unary_union

HA_CUADRICULA = 100
LADO_M = 1000

# Derechos que bloquean el área (tienen prioridad sobre un petitorio nuevo).
LEYENDAS_VIGENTES = {"TITULADO", "TRAMITE", "BLOQUEADO", "OTROS"}


def epsg_utm(lon: float, lat: float) -> int:
    """EPSG de la zona UTM WGS84 sur que corresponde al punto (Perú: 17, 18 o 19)."""
    zona = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zona


def utm_a_geograficas(este: float, norte: float, zona: int) -> tuple[float, float]:
    """Convierte UTM WGS84 sur (zona 17/18/19) a (lon, lat)."""
    t = Transformer.from_crs(32700 + zona, 4326, always_xy=True)
    lon, lat = t.transform(este, norte)
    return lon, lat


def forma_cuadriculas(n: int) -> tuple[int, int]:
    """Columnas y filas de un bloque compacto de n cuadrículas (n entre 1 y 10)."""
    cols = math.ceil(math.sqrt(n))
    filas = math.ceil(n / cols)
    return cols, filas


def armar_cuadriculas(lon: float, lat: float, hectareas: int) -> gpd.GeoDataFrame:
    """Bloque de cuadrículas de 1 km² que contiene el punto, en el CRS UTM local."""
    if hectareas % HA_CUADRICULA or not 100 <= hectareas <= 1000:
        raise ValueError("El petitorio va de 100 a 1,000 ha, en múltiplos de 100.")
    n = hectareas // HA_CUADRICULA
    crs = epsg_utm(lon, lat)
    este, norte = Transformer.from_crs(4326, crs, always_xy=True).transform(lon, lat)
    e0 = math.floor(este / LADO_M) * LADO_M
    n0 = math.floor(norte / LADO_M) * LADO_M
    cols, filas = forma_cuadriculas(n)
    off_c, off_f = (cols - 1) // 2, (filas - 1) // 2

    celdas = []
    for f in range(filas):
        for c in range(cols):
            if len(celdas) == n:
                break
            x = e0 + (c - off_c) * LADO_M
            y = n0 + (off_f - f) * LADO_M
            celdas.append({
                "cuadricula": len(celdas) + 1,
                "este_min": int(x),
                "norte_min": int(y),
                "geometry": box(x, y, x + LADO_M, y + LADO_M),
            })
    return gpd.GeoDataFrame(celdas, geometry="geometry", crs=crs)


def bbox_consulta(cuadriculas_utm: gpd.GeoDataFrame, margen_m: int = 1500) -> tuple[float, float, float, float]:
    """Rectángulo en grados (con margen) para pedir a INGEMMET lo que rodea el petitorio."""
    xmin, ymin, xmax, ymax = cuadriculas_utm.total_bounds
    caja = gpd.GeoSeries([box(xmin - margen_m, ymin - margen_m, xmax + margen_m, ymax + margen_m)],
                         crs=cuadriculas_utm.crs).to_crs(4326)
    return tuple(float(v) for v in caja.total_bounds)


def _union(gdf: gpd.GeoDataFrame):
    return unary_union(list(gdf.geometry)) if len(gdf) else None


def _ha(geom) -> float:
    return 0.0 if geom is None or geom.is_empty else geom.area / 10_000


@dataclass
class Evaluacion:
    cuadriculas: gpd.GeoDataFrame            # una fila por cuadrícula con hectáreas y estado
    superposiciones: pd.DataFrame            # derechos mineros que tocan el petitorio
    restricciones: pd.DataFrame              # áreas restringidas que tocan el petitorio
    titular_en_punto: dict | None            # derecho minero vigente donde cae el punto
    ha_solicitadas: int
    ha_libres: float
    ha_vigentes: float
    ha_extinguidas: float
    ha_prohibidas: float
    ha_condicionadas: float
    alertas: list[str] = field(default_factory=list)

    @property
    def veredicto(self) -> str:
        pct = self.ha_libres / self.ha_solicitadas
        if self.ha_prohibidas >= 0.5 * self.ha_solicitadas:
            return "NO VIABLE"
        if pct >= 0.95:
            return "LIBRE"
        if pct >= 0.10:
            return "PARCIALMENTE LIBRE"
        return "OCUPADA"


def evaluar(cuadriculas_utm: gpd.GeoDataFrame, derechos: gpd.GeoDataFrame,
            restringidas: gpd.GeoDataFrame, punto_lonlat: tuple[float, float]) -> Evaluacion:
    crs = cuadriculas_utm.crs
    der = derechos.to_crs(crs) if len(derechos) else derechos
    res = restringidas.to_crs(crs) if len(restringidas) else restringidas

    vig = der[der["LEYENDA"].isin(LEYENDAS_VIGENTES)] if len(der) else der
    ext = der[der["LEYENDA"] == "EXTINGUIDO"] if len(der) else der
    pro = res[res["nivel"] == "prohibe"] if len(res) else res
    con = res[res["nivel"] == "condiciona"] if len(res) else res

    u_vig, u_ext, u_pro, u_con = _union(vig), _union(ext), _union(pro), _union(con)

    filas = []
    for _, c in cuadriculas_utm.iterrows():
        g = c.geometry
        g_vig = g.intersection(u_vig) if u_vig is not None else None
        g_ext = g.intersection(u_ext) if u_ext is not None else None
        g_pro = g.intersection(u_pro) if u_pro is not None else None
        g_con = g.intersection(u_con) if u_con is not None else None
        bloqueado = unary_union([x for x in (g_vig, g_ext, g_pro) if x is not None and not x.is_empty])
        libre = _ha(g.difference(bloqueado)) if not bloqueado.is_empty else _ha(g)
        if libre >= 99:
            estado = "Libre"
        elif libre < 1:
            estado = "Restringida" if _ha(g_pro) > _ha(g_vig) else "Ocupada"
        else:
            estado = "Parcial"
        filas.append({
            "cuadricula": c["cuadricula"], "este_min": c["este_min"], "norte_min": c["norte_min"],
            "ha_libres": round(libre, 1), "ha_con_derecho": round(_ha(g_vig), 1),
            "ha_extinguidas": round(_ha(g_ext), 1), "ha_prohibidas": round(_ha(g_pro), 1),
            "ha_condicionadas": round(_ha(g_con), 1), "estado": estado, "geometry": g,
        })
    celdas = gpd.GeoDataFrame(filas, geometry="geometry", crs=crs)
    petitorio = unary_union(list(celdas.geometry))

    # Derechos mineros que se superponen con el petitorio
    sup = []
    for _, d in der.iterrows():
        inter = _ha(d.geometry.intersection(petitorio))
        if inter >= 0.5:
            sup.append({
                "Código": d.get("CODIGOU"), "Derecho minero": d.get("CONCESION"),
                "Titular": d.get("TIT_CONCES"), "Estado": d.get("LEYENDA"),
                "Detalle": d.get("D_ESTADO"), "Ha del derecho": round(float(d.get("HECTAGIS") or 0), 1),
                "Ha superpuestas": round(inter, 1), "Formulado": d.get("FEC_DENU"),
                "Distrito": d.get("DISTRI"),
            })
    superpos = pd.DataFrame(sup).sort_values("Ha superpuestas", ascending=False) if sup else pd.DataFrame()

    rs = []
    for _, r in res.iterrows():
        inter = _ha(r.geometry.intersection(petitorio))
        if inter >= 0.5:
            rs.append({"Tipo": r["tipo"], "Nombre": r["nombre"], "Categoría": r["detalle"],
                       "Efecto": "Prohíbe" if r["nivel"] == "prohibe" else "Condiciona (pedir opinión)",
                       "Ha superpuestas": round(inter, 1)})
    restric = pd.DataFrame(rs) if rs else pd.DataFrame()

    # ¿Quién es el titular donde está parado el cliente?
    titular = None
    pt = gpd.GeoSeries([Point(punto_lonlat)], crs=4326).to_crs(crs).iloc[0]
    if len(vig):
        hit = vig[vig.contains(pt)]
        if len(hit):
            h = hit.iloc[0]
            titular = {"codigo": h.get("CODIGOU"), "nombre": h.get("CONCESION"),
                       "titular": h.get("TIT_CONCES"), "estado": h.get("D_ESTADO"),
                       "hectareas": float(h.get("HECTAGIS") or 0)}

    ev = Evaluacion(
        cuadriculas=celdas, superposiciones=superpos, restricciones=restric, titular_en_punto=titular,
        ha_solicitadas=int(round(_ha(petitorio))), ha_libres=round(float(celdas["ha_libres"].sum()), 1),
        ha_vigentes=round(_ha(petitorio.intersection(u_vig)) if u_vig is not None else 0, 1),
        ha_extinguidas=round(_ha(petitorio.intersection(u_ext)) if u_ext is not None else 0, 1),
        ha_prohibidas=round(_ha(petitorio.intersection(u_pro)) if u_pro is not None else 0, 1),
        ha_condicionadas=round(_ha(petitorio.intersection(u_con)) if u_con is not None else 0, 1),
    )
    if titular:
        ev.alertas.append(
            f"El punto ya está dentro del derecho minero «{titular['nombre']}» ({titular['codigo']}) "
            f"de {titular['titular']}. Para trabajar ahí necesita un contrato con ese titular.")
    if ev.ha_extinguidas >= 1:
        ev.alertas.append(
            f"{ev.ha_extinguidas:,.0f} ha son de derechos extinguidos: no están libres todavía. "
            "Se pueden pedir cuando INGEMMET las publique en libre denunciabilidad (aviso en El Peruano).")
    if ev.ha_prohibidas >= 1:
        ev.alertas.append(f"{ev.ha_prohibidas:,.0f} ha caen en áreas donde no se admite la minería o el petitorio.")
    if ev.ha_condicionadas >= 1:
        ev.alertas.append(
            f"{ev.ha_condicionadas:,.0f} ha caen en áreas que exigen opinión previa o compatibilidad "
            "(p. ej., SERNANP para ANP de uso directo o zonas de amortiguamiento).")
    return ev
