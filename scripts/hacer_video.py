"""Graba el video de respaldo (~70 s) con la app real corriendo en local.

Uso: streamlit run app.py --server.port 8765   (en otra terminal)
     python scripts/hacer_video.py
Necesita: selenium, Chrome, pillow, imageio, imageio-ffmpeg.
"""
import io
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.common.by import By

URL = "http://localhost:8765"
SALIDA = Path(__file__).resolve().parent.parent / "docs" / "video" / "demo_gaia.mp4"
FPS = 2

o = webdriver.ChromeOptions()
o.add_argument("--headless=new")
o.add_argument("--window-size=1440,900")
d = webdriver.Chrome(options=o)
cuadros = []

try:
    fuente = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 30)
except OSError:
    fuente = ImageFont.load_default()


def captura(texto, segundos):
    img = Image.open(io.BytesIO(d.get_screenshot_as_png())).convert("RGB")
    dib = ImageDraw.Draw(img)
    w, h = img.size
    dib.rectangle([0, h - 70, w, h], fill=(27, 94, 59))
    dib.text((30, h - 55), texto, fill="white", font=fuente)
    arr = np.array(img)
    cuadros.extend([arr] * int(segundos * FPS))


def cuerpo():
    return d.find_element(By.TAG_NAME, "body").text


def esperar(texto, maximo=120):
    for _ in range(maximo):
        if texto in cuerpo():
            return
        time.sleep(1)


def scroll(y):
    d.execute_script(f"document.querySelector('[data-testid=\"stMain\"]').scrollTo(0, {y})")
    time.sleep(2)


def boton(texto):
    for b in d.find_elements(By.TAG_NAME, "button"):
        if texto in b.text:
            b.click()
            return


def elegir_lugar(nombre):
    scroll(0)
    sel = [s for s in d.find_elements(By.CSS_SELECTOR, "[data-testid='stSelectbox']") if "Lugar" in s.text][0]
    sel.click()
    time.sleep(1)
    for op in d.find_elements(By.CSS_SELECTOR, "li[role='option']"):
        if nombre in op.text:
            op.click()
            break
    time.sleep(2)


def consultar(veredicto_esperado):
    boton("Consultar catastro")
    time.sleep(2)
    esperar(veredicto_esperado)
    time.sleep(5)


d.get(URL)
time.sleep(8)
captura("Consorcio GAIA: ¿esta zona ya tiene dueño?", 5)
captura("1. El minero pone su punto: lugar, lat/lon o UTM del GPS", 4)

consultar("PARCIALMENTE LIBRE")
scroll(250)
captura("2. Consulta en vivo al catastro de INGEMMET: 157 de 400 ha libres", 7)
scroll(820)
captura("3. Mapa: cuadrículas del petitorio, concesiones y zona urbana de Chala", 9)
scroll(1350)
captura("4. Quién es el titular y cuánto pagaría al Estado (tipo de cambio BCRP)", 8)

elegir_lugar("Nasca")
consultar("NO VIABLE")
scroll(250)
captura("Pampa de Nasca: NO VIABLE, cae sobre las Líneas y Geoglifos de Nasca", 7)

elegir_lugar("Caylloma")
consultar("LIBRE:")
scroll(250)
captura("Caylloma: LIBRE, casi 400 ha disponibles para su petitorio", 6)

scroll(0)
for t in d.find_elements(By.CSS_SELECTOR, "button[role=tab]"):
    if "calendario" in t.text:
        t.click()
time.sleep(5)
scroll(150)
captura("5. Su calendario de obligaciones de los próximos 12 meses", 7)
for e in d.find_elements(By.CSS_SELECTOR, "[data-testid='stExpander'] summary"):
    if "produjo" in e.text:
        e.click()
time.sleep(2)
scroll(150)
captura("¿No produjo este año? Qué hacer para no perder la concesión", 6)
scroll(0)
captura("GAIA: ficha S/ 50 · Concesión Segura S/ 39/mes · Diagnóstico REINFO S/ 350", 5)
d.quit()

SALIDA.parent.mkdir(parents=True, exist_ok=True)
imageio.mimwrite(SALIDA, cuadros, fps=FPS, codec="libx264", quality=7, macro_block_size=8)
print(SALIDA, f"{len(cuadros) / FPS:.0f} s")
