"""Pruebas sin internet: cuadrículas, cruce geoespacial, costos y calendario."""
from datetime import date

import geopandas as gpd
import pytest
from shapely.geometry import box

from gaia import calendario as cal
from gaia import costos, geo


def test_epsg_utm_peru():
    assert geo.epsg_utm(-80.5, -5.0) == 32717
    assert geo.epsg_utm(-74.25, -15.85) == 32718
    assert geo.epsg_utm(-69.5, -14.7) == 32719


@pytest.mark.parametrize("ha", [100, 300, 400, 700, 1000])
def test_cuadriculas_area_y_alineacion(ha):
    c = geo.armar_cuadriculas(-74.25, -15.85, ha)
    assert len(c) == ha // 100
    assert c.geometry.area.sum() / 10_000 == pytest.approx(ha)
    assert all(x % 1000 == 0 for x in c["este_min"]) and all(y % 1000 == 0 for y in c["norte_min"])


def test_cuadriculas_rechaza_hectareas_invalidas():
    with pytest.raises(ValueError):
        geo.armar_cuadriculas(-74.25, -15.85, 250)


def _vacio():
    return gpd.GeoDataFrame(columns=["LEYENDA", "geometry"], geometry="geometry", crs="EPSG:4326")


def test_evaluar_descuenta_derecho_vigente():
    c = geo.armar_cuadriculas(-74.25, -15.85, 200)
    primera = c.iloc[[0]]
    der = gpd.GeoDataFrame({"LEYENDA": ["TITULADO"], "CODIGOU": ["X1"], "CONCESION": ["PRUEBA"],
                            "TIT_CONCES": ["TITULAR SAC"], "HECTAGIS": [100.0], "D_ESTADO": ["Titulado"]},
                           geometry=primera.geometry.values, crs=c.crs).to_crs(4326)
    res = gpd.GeoDataFrame(columns=["tipo", "nivel", "nombre", "detalle", "geometry"], geometry="geometry", crs=4326)
    ev = geo.evaluar(c, der, res, (-74.25, -15.85))
    assert ev.ha_libres == pytest.approx(100, abs=0.5)
    assert ev.veredicto == "PARCIALMENTE LIBRE"
    assert len(ev.superposiciones) == 1


def test_evaluar_prohibido_es_no_viable():
    c = geo.armar_cuadriculas(-75.05, -14.65, 100)
    x0, y0, x1, y1 = c.total_bounds
    zona = gpd.GeoDataFrame({"tipo": ["Zona arqueológica"], "nivel": ["prohibe"], "nombre": ["Z"], "detalle": [""]},
                            geometry=[box(x0 - 10, y0 - 10, x1 + 10, y1 + 10)], crs=c.crs).to_crs(4326)
    ev = geo.evaluar(c, _vacio(), zona, (-75.05, -14.65))
    assert ev.veredicto == "NO VIABLE" and ev.ha_libres == 0


def test_costos_ppm_400ha():
    k = costos.calcular(400, "PPM", 3.5)
    assert k.vigencia_usd == 400
    assert k.total_presentacion == pytest.approx(420 + 1400)
    assert k.produccion_minima_soles == pytest.approx(400 * 5500 * 0.10)


def test_calendario_filtra_por_perfil_y_fechas():
    hoy = date(2026, 11, 11)
    solo_titular = cal.calendario({"titular"}, hoy=hoy)
    assert not solo_titular.empty
    assert solo_titular["Fecha"].min() >= hoy
    assert "Pago del derecho de vigencia y penalidad" in set(solo_titular["Obligación"])
    assert not solo_titular["Obligación"].str.contains("REINFO").any()
    con_reinfo = cal.calendario({"reinfo"}, hoy=hoy)
    assert date(2026, 12, 31) in set(con_reinfo["Fecha"])
