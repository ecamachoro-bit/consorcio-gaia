"""Mapa interactivo del petitorio con Folium (sesión 06).

Colores de los derechos mineros iguales a los de GEOCATMIN:
azul = titulado, verde = en trámite, negro = extinguido, marrón = otros.
"""
from __future__ import annotations

import folium
import geopandas as gpd

COLOR_LEYENDA = {
    "TITULADO": "#1f4e9c",
    "TRAMITE": "#2e8b3e",
    "EXTINGUIDO": "#222222",
    "BLOQUEADO": "#7b3fa0",
    "OTROS": "#8b5a2b",
}
COLOR_ESTADO_CELDA = {"Libre": "#f2b705", "Parcial": "#f28705", "Ocupada": "#c0392b", "Restringida": "#8e44ad"}
COLOR_RESTRICCION = {"prohibe": "#d7191c", "condiciona": "#fdae61"}


def _popup_derecho(p) -> str:
    return (f"<b>{p.get('CONCESION', '')}</b><br>Código: {p.get('CODIGOU', '')}<br>"
            f"Titular: {p.get('TIT_CONCES', '')}<br>Estado: {p.get('D_ESTADO', '')}<br>"
            f"Hectáreas: {float(p.get('HECTAGIS') or 0):,.1f}")


def dibujar(punto_lonlat, cuadriculas: gpd.GeoDataFrame, derechos: gpd.GeoDataFrame,
            restringidas: gpd.GeoDataFrame) -> folium.Map:
    lon, lat = punto_lonlat
    m = folium.Map(location=[lat, lon], zoom_start=13, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Mapa base").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satélite",
    ).add_to(m)

    if len(restringidas):
        capa = folium.FeatureGroup(name="Áreas restringidas")
        for _, r in restringidas.iterrows():
            folium.GeoJson(
                r.geometry.__geo_interface__,
                style_function=lambda _f, c=COLOR_RESTRICCION[r["nivel"]]: {
                    "color": c, "fillColor": c, "weight": 2, "fillOpacity": 0.25, "dashArray": "6 4"},
                tooltip=f"{r['tipo']}: {r['nombre']}",
            ).add_to(capa)
        capa.add_to(m)

    if len(derechos):
        capa = folium.FeatureGroup(name="Derechos mineros (INGEMMET)")
        for _, d in derechos.iterrows():
            c = COLOR_LEYENDA.get(d.get("LEYENDA"), "#555555")
            folium.GeoJson(
                d.geometry.__geo_interface__,
                style_function=lambda _f, c=c: {"color": c, "fillColor": c, "weight": 1.5, "fillOpacity": 0.18},
                tooltip=f"{d.get('CONCESION', '')} · {d.get('LEYENDA', '')}",
                popup=folium.Popup(_popup_derecho(d), max_width=320),
            ).add_to(capa)
        capa.add_to(m)

    capa = folium.FeatureGroup(name="Petitorio propuesto (cuadrículas)")
    for _, c in cuadriculas.to_crs(4326).iterrows():
        col = COLOR_ESTADO_CELDA[c["estado"]]
        folium.GeoJson(
            c.geometry.__geo_interface__,
            style_function=lambda _f, col=col: {"color": col, "weight": 3, "fillOpacity": 0.0},
            tooltip=f"Cuadrícula {c['cuadricula']}: {c['estado']} · {c['ha_libres']:.0f} ha libres",
        ).add_to(capa)
    capa.add_to(m)

    folium.Marker([lat, lon], tooltip="Punto del cliente",
                  icon=folium.Icon(color="red", icon="map-marker", prefix="fa")).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    xmin, ymin, xmax, ymax = cuadriculas.to_crs(4326).total_bounds
    m.fit_bounds([[ymin - 0.01, xmin - 0.01], [ymax + 0.01, xmax + 0.01]])
    return m
