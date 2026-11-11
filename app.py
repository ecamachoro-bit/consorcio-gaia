"""Consorcio GAIA · Consulta de área y plan de cumplimiento para la pequeña minería.

Corre con:  streamlit run app.py
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from gaia import calendario as cal
from gaia import catastro, costos, ficha, geo, mapa

st.set_page_config(page_title="Consorcio GAIA · Consulta de área minera", page_icon="⛰️", layout="wide")

EJEMPLOS = {
    "Chala, Caravelí (Arequipa)": (-74.25, -15.85),
    "Caylloma (Arequipa)": (-71.77, -15.19),
    "Santo Tomás, Chumbivilcas (Cusco)": (-72.08, -14.45),
    "Ananea, San Antonio de Putina (Puno)": (-69.53, -14.68),
    "Pampa de Nasca (Ica)": (-75.05, -14.65),
}


# ---------- datos en vivo (con caché de 1 hora) ----------
@st.cache_data(ttl=3600, show_spinner=False)
def consultar(bbox):
    derechos = catastro.derechos_mineros(bbox)
    restringidas, fallas = catastro.areas_restringidas(bbox)
    return derechos, restringidas, fallas


@st.cache_data(ttl=3600, show_spinner=False)
def tipo_cambio():
    return catastro.tipo_de_cambio()


# ---------- barra lateral: datos del cliente ----------
with st.sidebar:
    st.markdown("## ⛰️ Consorcio GAIA")
    st.caption("Asesoría a la minería artesanal y de pequeña escala")
    st.divider()
    st.markdown("**1. El cliente**")
    cliente = st.text_input("Nombre (opcional, use datos ficticios en el demo)", "Cliente demo")
    regimen = st.selectbox("Régimen", list(costos.REGIMENES), index=1, format_func=costos.NOMBRE_REGIMEN.get)
    hectareas = st.select_slider("Hectáreas del petitorio", options=list(range(100, 1100, 100)), value=400)
    st.markdown("**2. Su situación**")
    perfil = {k for k, txt in cal.PERFILES.items()
              if st.checkbox(txt, value=k in {"titular", "reinfo", "ruc"}, key=f"p_{k}")}
    st.divider()
    st.caption("Datos en vivo: catastro minero de INGEMMET (GEOCATMIN) y tipo de cambio del BCRP. "
               "Resultado referencial, no es opinión legal.")

# ---------- encabezado ----------
st.title("¿Esta zona ya tiene dueño?")
st.markdown("Ponga la coordenada donde quiere trabajar. GAIA consulta **en vivo el catastro minero de INGEMMET**, "
            "arma las cuadrículas de su petitorio y le dice **cuántas hectáreas están libres, quién es el titular, "
            "qué restricciones hay, cuánto pagará al Estado y qué obligaciones vienen**.")

tab_area, tab_cal, tab_info = st.tabs(["📍 Consulta de área", "📅 Mi calendario de obligaciones", "ℹ️ Cómo funciona"])

# =====================================================================
with tab_area:
    c1, c2 = st.columns([1, 2])
    with c1:
        modo = st.radio("¿Cómo ingresa la ubicación?", ["Lugar de ejemplo", "Latitud / longitud", "UTM (GPS)"],
                        horizontal=True)
        if modo == "Lugar de ejemplo":
            lugar = st.selectbox("Lugar", list(EJEMPLOS))
            lon, lat = EJEMPLOS[lugar]
        elif modo == "Latitud / longitud":
            lugar = st.text_input("Referencia del lugar", "")
            lat = st.number_input("Latitud (sur es negativa)", value=-15.85, min_value=-18.6, max_value=-0.03,
                                  format="%.5f")
            lon = st.number_input("Longitud (oeste es negativa)", value=-74.25, min_value=-81.4, max_value=-68.6,
                                  format="%.5f")
        else:
            lugar = st.text_input("Referencia del lugar", "")
            zona = st.selectbox("Zona UTM", [17, 18, 19], index=1)
            este = st.number_input("Este (m)", value=580000.0, step=100.0, format="%.0f")
            norte = st.number_input("Norte (m)", value=8247000.0, step=100.0, format="%.0f")
            lon, lat = geo.utm_a_geograficas(este, norte, zona)
            st.caption(f"Equivale a lat {lat:.5f}, lon {lon:.5f}")

        if "punto_mapa" in st.session_state:
            p_lon, p_lat = st.session_state["punto_mapa"]
            st.info(f"Punto elegido en el mapa: lat {p_lat:.5f}, lon {p_lon:.5f}")
            usar_mapa = st.toggle("Usar el punto del mapa", value=True)
            if usar_mapa:
                lon, lat, lugar = p_lon, p_lat, lugar or "Punto elegido en el mapa"

        consultar_btn = st.button("🔎 Consultar catastro INGEMMET", type="primary", width="stretch")

    if consultar_btn:
        try:
            with st.spinner("Consultando el catastro minero de INGEMMET en vivo…"):
                celdas = geo.armar_cuadriculas(lon, lat, hectareas)
                bbox = geo.bbox_consulta(celdas)
                derechos, restringidas, fallas = consultar(bbox)
                ev = geo.evaluar(celdas, derechos, restringidas, (lon, lat))
            st.session_state["res"] = dict(lon=lon, lat=lat, lugar=lugar, ev=ev, derechos=derechos,
                                           restringidas=restringidas, fallas=fallas, hectareas=hectareas)
        except catastro.CatastroError as e:
            st.error(f"INGEMMET no respondió ahora: {e}. Intente de nuevo en unos segundos.")
        except ValueError as e:
            st.error(str(e))

    res = st.session_state.get("res")
    with c2:
        if not res:
            st.info("👈 Elija un lugar y pulse **Consultar catastro INGEMMET**.")
        else:
            ev: geo.Evaluacion = res["ev"]
            colores = {"LIBRE": "🟢", "PARCIALMENTE LIBRE": "🟡", "OCUPADA": "🔴", "NO VIABLE": "⛔"}
            st.subheader(f"{colores[ev.veredicto]} {ev.veredicto}: {ev.ha_libres:,.0f} de {ev.ha_solicitadas:,} ha libres")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Ha libres", f"{ev.ha_libres:,.0f}")
            m2.metric("Ha con derecho vigente", f"{ev.ha_vigentes:,.0f}")
            m3.metric("Ha restringidas", f"{ev.ha_prohibidas:,.0f}")
            m4.metric("Derechos superpuestos", len(ev.superposiciones))
            for a in ev.alertas:
                st.warning(a)
            if res["fallas"]:
                st.caption("⚠️ No respondieron estas capas de INGEMMET: " + ", ".join(res["fallas"])
                           + ". Vuelva a consultar para completarlas.")

    if res:
        ev = res["ev"]
        st.markdown("#### Mapa del petitorio")
        st.caption("Cuadrículas: amarillo = libre, naranja = parcial, rojo = ocupada, morado = restringida. "
                   "Derechos: azul = titulado, verde = en trámite, negro = extinguido. "
                   "Haga clic en el mapa para elegir otro punto.")
        salida = st_folium(mapa.dibujar((res["lon"], res["lat"]), ev.cuadriculas, res["derechos"],
                                        res["restringidas"]),
                           height=520, use_container_width=True, returned_objects=["last_clicked"])
        if salida and salida.get("last_clicked"):
            nuevo = (salida["last_clicked"]["lng"], salida["last_clicked"]["lat"])
            if st.session_state.get("punto_mapa") != nuevo:
                st.session_state["punto_mapa"] = nuevo
                st.rerun()

        d1, d2 = st.columns(2)
        with d1:
            st.markdown("#### Derechos mineros superpuestos")
            if ev.superposiciones.empty:
                st.success("Ningún derecho minero se superpone con el petitorio.")
            else:
                st.dataframe(ev.superposiciones, hide_index=True, width="stretch")
        with d2:
            st.markdown("#### Áreas restringidas")
            if ev.restricciones.empty:
                st.success("Sin áreas restringidas en el petitorio.")
            else:
                st.dataframe(ev.restricciones, hide_index=True, width="stretch")

        st.markdown("#### Cuánto paga al Estado")
        tc, fecha_tc = tipo_cambio()
        k = costos.calcular(res["hectareas"], regimen, tc)
        p1, p2, p3 = st.columns(3)
        p1.metric("Al presentar el petitorio", f"S/ {k.total_presentacion:,.2f}",
                  help="Derecho de trámite + derecho de vigencia del primer año")
        p2.metric("Cada año para mantenerlo", f"S/ {k.vigencia_anual_soles:,.2f}", help="Derecho de vigencia anual")
        p3.metric("Producción mínima anual exigible", f"S/ {k.produccion_minima_soles:,.0f}",
                  help="Si no se acredita, se paga penalidad")
        st.caption(f"{costos.NOMBRE_REGIMEN[regimen]} · {res['hectareas']:,} ha · derecho de trámite "
                   f"S/ {k.derecho_tramite:,.0f} · vigencia US$ {costos.REGIMENES[regimen]['vigencia_usd_ha']:.2f}/ha · "
                   f"tipo de cambio BCRP {tc:.3f} ({fecha_tc}). No incluye penalidad ni honorarios.")

        crono = cal.calendario(perfil)
        html = ficha.generar(cliente, res["lugar"], res["lon"], res["lat"], ev, k, crono, fecha_tc)
        st.download_button("📄 Descargar ficha de consulta de área", html,
                           file_name=f"ficha_GAIA_{date.today():%Y%m%d}.html", mime="text/html", type="primary")

# =====================================================================
with tab_cal:
    st.markdown("### Su concesión no se cuida sola")
    st.markdown("Según lo que marcó en la barra lateral, estas son sus obligaciones de los **próximos 12 meses**.")
    crono = cal.calendario(perfil)
    if crono.empty:
        st.info("Marque al menos una situación en la barra lateral.")
    else:
        prox30 = crono[crono["Días"] <= 30]
        a1, a2, a3 = st.columns(3)
        a1.metric("Obligaciones en 12 meses", len(crono))
        a2.metric("En los próximos 30 días", len(prox30))
        sig = crono.iloc[0]
        a3.metric("La siguiente", sig["Fecha"].strftime("%d/%m/%Y"), sig["Obligación"][:38], delta_color="off")

        if "titular" in perfil:
            with st.expander("¿No produjo nada este año? Qué hacer para no perder la concesión"):
                st.markdown(
                    "1. **Hasta el 30 de abril:** acredite la **inversión mínima** del año anterior. "
                    "Si la acredita, evita la penalidad.\n"
                    "2. **Hasta el 30 de junio:** pague el **derecho de vigencia** y, si corresponde, la "
                    "**penalidad**. Dos años sin pagar = caducidad.\n"
                    "3. **En julio:** presente la **DAC**. Ahí se declara la actividad del año, "
                    "haya habido producción o no.\n\n"
                    "Pida a INGEMMET la liquidación de su penalidad antes de pagar. *(Pregunta real de un "
                    "titular de Apurímac; ver docs/research.)*")

        criticas = crono[crono["Obligación"].str.contains("vigencia|REINFO|DSP", regex=True)]
        for _, r in criticas.head(3).iterrows():
            st.error(f"**{r['Fecha']:%d/%m/%Y} · {r['Obligación']}** — si no cumple: {r['Si no cumple']}")

        graf = crono.assign(Fecha=pd.to_datetime(crono["Fecha"]))
        fig = px.scatter(graf, x="Fecha", y="Tipo", color="Tipo", symbol="Fecha confirmada",
                         hover_data={"Obligación": True, "Entidad": True, "Si no cumple": True, "Tipo": False},
                         height=360)
        fig.update_traces(marker=dict(size=13, line=dict(width=1, color="white")))
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="", yaxis_title=None,
                          xaxis_title=None)
        st.plotly_chart(fig, width="stretch")

        por_mes = graf.groupby([graf["Fecha"].dt.to_period("M").dt.to_timestamp(), "Tipo"]).size().reset_index(name="n")
        fig2 = px.bar(por_mes, x="Fecha", y="n", color="Tipo", height=260,
                      labels={"n": "Obligaciones", "Fecha": ""})
        fig2.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
        st.plotly_chart(fig2, width="stretch")

        tabla = crono.copy()
        tabla["Fecha"] = pd.to_datetime(tabla["Fecha"]).dt.strftime("%d/%m/%Y")
        st.dataframe(tabla, hide_index=True, width="stretch")
        st.download_button("⬇️ Descargar calendario (CSV)", crono.to_csv(index=False).encode("utf-8-sig"),
                           file_name="calendario_obligaciones_GAIA.csv", mime="text/csv")
        st.caption("Fuentes: Calendario 2026 de obligaciones para la pequeña minería y minería artesanal (Swiss Better "
                   "Gold), INGEMMET y MINEM. Las fechas 2027 repiten el patrón 2026 hasta que salgan los cronogramas "
                   "oficiales; las que dependen del último dígito del RUC son aproximadas.")

# =====================================================================
with tab_info:
    st.markdown("""
### Cómo funciona
1. **Cuadrículas.** El catastro minero divide el Perú en cuadrículas de 100 ha (1 km × 1 km) en UTM WGS84.
   GAIA arma su petitorio (100 a 1,000 ha) alrededor de su punto.
2. **Consulta en vivo.** Pide a los servicios ArcGIS REST de GEOCATMIN (INGEMMET) los derechos mineros y
   ocho capas de áreas restringidas que tocan la zona.
3. **Cruce geoespacial.** Con GeoPandas cruza cada cuadrícula con esos polígonos y calcula las hectáreas libres:
   descuenta los derechos vigentes (tienen prioridad), los extinguidos que aún no salen a libre denunciabilidad
   y las áreas donde la minería está prohibida.
4. **Costos y obligaciones.** Calcula los pagos al Estado con el tipo de cambio del día del BCRP y arma el
   calendario de obligaciones según el perfil del cliente.

### Límites
- El catastro de INGEMMET tiene carácter referencial; la verificación final es en GEOCATMIN y en el expediente.
- No reemplaza la visita de campo, la revisión del terreno superficial ni la opinión legal.
- Los titulares que aparecen son datos públicos del catastro minero.
""")
