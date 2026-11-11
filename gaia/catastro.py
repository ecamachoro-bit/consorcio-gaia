"""Consulta en vivo de datos públicos: catastro minero de INGEMMET (GEOCATMIN) y tipo de cambio del BCRP.

Herramienta del curso: Scraping y APIs (sesión 03).

GEOCATMIN publica sus capas como servicios ArcGIS REST. Cada consulta pide los
polígonos que tocan un rectángulo (bbox) y los devuelve en GeoJSON, que luego
leemos con GeoPandas.

Nota técnica sobre SSL: el servidor de INGEMMET no envía el certificado
intermedio de Sectigo. En vez de desactivar la verificación, armamos un paquete
de certificados = certifi + ese intermedio (gaia/certs/sectigo_ov_r36.pem,
descargado de crt.sectigo.com), así la conexión se sigue verificando.
"""
from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import certifi
import geopandas as gpd
import pandas as pd
import requests

GEOCATMIN = "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services"
URL_DERECHOS = f"{GEOCATMIN}/SERV_CATASTRO_MINERO/MapServer/0/query"
URL_RESTRINGIDAS = f"{GEOCATMIN}/SERV_AREA_RESERVADA/MapServer/{{capa}}/query"
URL_BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json/{ini}/{fin}"

CAMPOS_DERECHOS = [
    "CODIGOU", "CONCESION", "TIT_CONCES", "HECTAGIS", "ESTADO", "D_ESTADO",
    "LEYENDA", "SUSTANCIA", "DEPA", "PROVI", "DISTRI", "FEC_DENU",
]

# Capas de áreas restringidas de GEOCATMIN que importan para un petitorio.
# nivel: "prohibe" = no se puede pedir/operar ahí; "condiciona" = requiere opinión o compatibilidad.
CAPAS_RESTRINGIDAS = {
    10: ("Área Natural Protegida", "condiciona"),
    11: ("Zona de amortiguamiento de ANP", "condiciona"),
    1: ("Zona arqueológica", "prohibe"),
    6: ("Zona urbana", "prohibe"),
    4: ("ANAP de INGEMMET (no admite petitorios)", "prohibe"),
    0: ("Área de defensa nacional", "condiciona"),
    19: ("Reserva indígena", "prohibe"),
    20: ("Reserva territorial", "prohibe"),
}

TIMEOUT = 45
_CERT_INTERMEDIO = Path(__file__).parent / "certs" / "sectigo_ov_r36.pem"


class CatastroError(RuntimeError):
    """El servicio de INGEMMET no respondió o respondió con error."""


def _paquete_certificados() -> str:
    """Devuelve la ruta a un CA bundle = certifi + intermedio de Sectigo."""
    destino = Path(tempfile.gettempdir()) / "gaia_ca_bundle.pem"
    if not destino.exists():
        destino.write_text(
            Path(certifi.where()).read_text(encoding="utf-8")
            + "\n"
            + _CERT_INTERMEDIO.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return str(destino)


_SESION = requests.Session()
_SESION.headers["User-Agent"] = "consorcio-gaia/1.0 (proyecto academico Q-Lab PUCP)"


def _get_json(url: str, params: dict) -> dict:
    try:
        r = _SESION.get(url, params=params, timeout=TIMEOUT, verify=_paquete_certificados())
        r.raise_for_status()
        datos = r.json()
    except (requests.RequestException, ValueError) as e:
        raise CatastroError(f"No se pudo consultar {url.split('/services/')[-1]}: {e}") from e
    if "error" in datos:
        raise CatastroError(f"INGEMMET respondió con error: {datos['error']}")
    return datos


def _params_bbox(bbox: tuple[float, float, float, float], campos: str) -> dict:
    xmin, ymin, xmax, ymax = bbox
    return {
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": campos,
        "returnGeometry": "true",
        "f": "geojson",
    }


def _a_geodataframe(geojson: dict) -> gpd.GeoDataFrame:
    feats = [f for f in geojson.get("features", []) if f.get("geometry")]
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf


def derechos_mineros(bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Derechos mineros (titulados, en trámite, extinguidos...) que tocan el bbox."""
    datos = _get_json(URL_DERECHOS, _params_bbox(bbox, ",".join(CAMPOS_DERECHOS)))
    gdf = _a_geodataframe(datos)
    if gdf.empty:
        return gpd.GeoDataFrame(columns=CAMPOS_DERECHOS + ["geometry"], geometry="geometry", crs="EPSG:4326")
    if "FEC_DENU" in gdf:
        gdf["FEC_DENU"] = pd.to_datetime(gdf["FEC_DENU"], unit="ms", errors="coerce").dt.date
    return gdf


def _una_capa_restringida(capa: int, bbox) -> gpd.GeoDataFrame:
    nombre, nivel = CAPAS_RESTRINGIDAS[capa]
    datos = _get_json(URL_RESTRINGIDAS.format(capa=capa), _params_bbox(bbox, "*"))
    gdf = _a_geodataframe(datos)
    if gdf.empty:
        return gdf
    etiqueta = gdf.get("NOMBRE", gdf.get("NM_AREA", pd.Series([""] * len(gdf))))
    out = gpd.GeoDataFrame(
        {
            "tipo": nombre,
            "nivel": nivel,
            "nombre": etiqueta.fillna("").astype(str).str.strip(),
            "detalle": gdf.get("CATEGORI", pd.Series([""] * len(gdf))).fillna("").astype(str),
        },
        geometry=gdf.geometry,
        crs="EPSG:4326",
    )
    # En ANP de uso indirecto (parques nacionales, santuarios) la minería está prohibida.
    if capa == 10 and "USO" in gdf:
        out.loc[gdf["USO"].astype(str).str.upper().str.contains("INDIRECTO").values, "nivel"] = "prohibe"
    return out


def areas_restringidas(bbox: tuple[float, float, float, float]) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Áreas restringidas que tocan el bbox. Devuelve (gdf, capas_que_fallaron)."""
    partes, fallas = [], []
    with ThreadPoolExecutor(max_workers=len(CAPAS_RESTRINGIDAS)) as ex:
        futuros = {ex.submit(_una_capa_restringida, c, bbox): c for c in CAPAS_RESTRINGIDAS}
        for fut, capa in futuros.items():
            try:
                g = fut.result()
                if not g.empty:
                    partes.append(g)
            except CatastroError:
                fallas.append(CAPAS_RESTRINGIDAS[capa][0])
    if not partes:
        return gpd.GeoDataFrame(columns=["tipo", "nivel", "nombre", "detalle", "geometry"],
                                geometry="geometry", crs="EPSG:4326"), fallas
    return gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:4326"), fallas


def tipo_de_cambio(hoy: date | None = None) -> tuple[float, str]:
    """Último tipo de cambio venta SBS publicado por el BCRP (serie PD04640PD).

    Devuelve (valor, fecha_texto). Si el BCRP no responde, devuelve (3.45, "referencial").
    """
    hoy = hoy or date.today()
    url = URL_BCRP.format(ini=(hoy - timedelta(days=20)).isoformat(), fin=hoy.isoformat())
    try:
        r = _SESION.get(url, timeout=20)
        r.raise_for_status()
        periodos = r.json()["periods"]
        for p in reversed(periodos):
            v = p["values"][0]
            if v not in ("n.d.", "", None):
                return float(v), p["name"]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        pass
    return 3.45, "referencial (BCRP no respondió)"
