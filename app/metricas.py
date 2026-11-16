"""Métricas del texto que se calculan sin IA: siempre dan lo mismo para el mismo texto.

Cada valor es una cuenta sobre el texto (sílabas, palabras, frases, párrafos), no una
opinión. Lo que no se puede calcular con fiabilidad se devuelve como None, no como cero.
"""

from __future__ import annotations

import re
import statistics

from . import texto as lector

# Idiomas con fórmula de legibilidad validada.
_IDIOMAS = {"español": "es", "inglés": "en", "ingles": "en"}

_FRASE = re.compile(r"[^.!?…]+(?:[.!?…]+[\"»”')\]]*|$)")
_PALABRA = re.compile(r"[^\W\d_]+(?:[’'][^\W\d_]+)?")

_FUERTES = set("aeoáéóíú")  # la i y la u con tilde rompen el diptongo
_DEBILES = set("iuü")
_VOCALES_ES = _FUERTES | _DEBILES


def silabas_es(palabra: str) -> int:
    """Sílabas de una palabra en español: grupos de vocales, separando los hiatos."""
    p = palabra.lower()
    # La «u» de que/qui/gue/gui no suena; la «y» final o suelta hace de vocal.
    p = re.sub(r"(?<=[qg])u(?=[eiéí])", "", p)
    p = re.sub(r"y(?![aeiouáéíóú])", "i", p)
    total = 0
    previa = ""
    for letra in p:
        if letra in _VOCALES_ES:
            if not previa:
                total += 1
            elif previa in _FUERTES and letra in _FUERTES:
                total += 1  # hiato: dos vocales fuertes seguidas van en sílabas distintas
            previa = letra
        else:
            previa = ""
    return max(total, 1)


def silabas_en(palabra: str) -> int:
    """Sílabas aproximadas de una palabra inglesa (grupos de vocales, sin la «e» muda)."""
    p = re.sub(r"[^a-z]", "", palabra.lower())
    if not p:
        return 1
    grupos = len(re.findall(r"[aeiouy]+", p))
    if p.endswith("e") and not p.endswith(("le", "ee")) and grupos > 1:
        grupos -= 1
    if p.endswith(("ed", "es")) and grupos > 1 and not re.search(r"[td]ed$|[sxz]es$|[cs]hes$", p):
        grupos -= 1
    return max(grupos, 1)


def frases(texto: str) -> list[str]:
    salida = []
    for parrafo in re.split(r"\n+", texto):
        for f in _FRASE.findall(parrafo):
            if _PALABRA.search(f):
                salida.append(f.strip())
    return salida


def palabras(texto: str) -> list[str]:
    return _PALABRA.findall(texto)


def parrafos(texto: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", texto) if _PALABRA.search(p)]


def legibilidad(texto: str, idioma: str) -> dict | None:
    """Índices de legibilidad. None si el idioma no tiene fórmula o no hay texto.

    Español: Szigriszt-Pazos (206,835 − 62,3·sílabas/palabra − palabras/frase), que se lee
    con la escala INFLESZ, y Fernández-Huerta (206,84 − 60·sílabas/palabra − 1,02·palabras/
    frase). Inglés: Flesch Reading Ease (206,835 − 84,6·sílabas/palabra − 1,015·palabras/
    frase). En los tres, más alto es más fácil de leer.
    """
    codigo = _IDIOMAS.get((idioma or "").strip().lower())
    pal = palabras(texto)
    fra = frases(texto)
    if not codigo or len(pal) < 100 or not fra:
        return None
    por_frase = len(pal) / len(fra)
    if codigo == "es":
        por_palabra = sum(silabas_es(p) for p in pal) / len(pal)
        szigriszt = 206.835 - 62.3 * por_palabra - por_frase
        huerta = 206.84 - 60 * por_palabra - 1.02 * por_frase
        return {
            "indice": "Szigriszt-Pazos",
            "valor": round(szigriszt, 1),
            "nota": _acota(szigriszt),
            "nivel": _inflesz(szigriszt),
            "fernandez_huerta": round(huerta, 1),
            "silabas_por_palabra": round(por_palabra, 2),
        }
    por_palabra = sum(silabas_en(p) for p in pal) / len(pal)
    flesch = 206.835 - 84.6 * por_palabra - 1.015 * por_frase
    return {
        "indice": "Flesch",
        "valor": round(flesch, 1),
        "nota": _acota(flesch),
        "nivel": _flesch(flesch),
        "silabas_por_palabra": round(por_palabra, 2),
    }


def _acota(v: float) -> int:
    return int(round(min(100, max(0, v))))


def _inflesz(v: float) -> str:
    if v < 40:
        return "Muy difícil"
    if v < 55:
        return "Algo difícil"
    if v < 65:
        return "Normal"
    if v < 80:
        return "Bastante fácil"
    return "Muy fácil"


def _flesch(v: float) -> str:
    if v < 30:
        return "Muy difícil"
    if v < 50:
        return "Algo difícil"
    if v < 60:
        return "Normal"
    if v < 80:
        return "Bastante fácil"
    return "Muy fácil"


def proporcion_dialogo(texto: str) -> float:
    """Parte de las palabras que está en diálogo (de 0 a 1).

    Cuenta los párrafos que empiezan con raya (—, – o guion) y lo que va entre comillas
    («», “” o ") en el resto. No distingue el inciso del narrador dentro de una raya.
    """
    total = dialogo = 0
    for p in parrafos(texto):
        n = len(palabras(p))
        total += n
        if re.match(r"\s*[—–-]\s*\S", p):
            dialogo += n
        else:
            for cita in re.findall(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"", p):
                dialogo += len(palabras(" ".join(cita)))
    return dialogo / total if total else 0.0


def mtld(pal: list[str], umbral: float = 0.72) -> float | None:
    """Diversidad léxica MTLD (McCarthy y Jarvis, 2010).

    Longitud media de los tramos de texto que mantienen la proporción de palabras
    distintas por encima de 0,72; se mide hacia delante y hacia atrás y se promedia. Más
    alto es más variado. A diferencia del cociente tipos/palabras, no depende del largo.
    """
    pal = [p.lower() for p in pal]
    if len(pal) < 200:
        return None

    def pasada(seq: list[str]) -> float:
        factores = 0.0
        vistos: set[str] = set()
        n = 0
        for p in seq:
            n += 1
            vistos.add(p)
            if len(vistos) / n <= umbral:
                factores += 1
                vistos, n = set(), 0
        if n:
            ttr = len(vistos) / n
            factores += (1 - ttr) / (1 - umbral)
        return len(seq) / factores if factores else float(len(seq))

    return round((pasada(pal) + pasada(pal[::-1])) / 2, 1)


def _tramo(texto: str, idioma: str) -> dict:
    pal = palabras(texto)
    largos = [len(palabras(f)) for f in frases(texto)]
    par = parrafos(texto)
    leg = legibilidad(texto, idioma)
    media = statistics.fmean(largos) if largos else 0.0
    return {
        "palabras": len(pal),
        "frase_media": round(media, 1),
        "parrafo_medio": round(len(pal) / len(par), 1) if par else 0.0,
        "dialogo": round(proporcion_dialogo(texto), 3),
        "legibilidad": leg["nota"] if leg else None,
        # Coeficiente de variación del largo de frase: desviación típica entre media.
        "variacion_frase": round(statistics.pstdev(largos) / media, 2) if len(largos) > 1 and media else None,
    }


def calcular(texto: str, idioma: str) -> dict:
    """Todas las métricas del manuscrito y de cada capítulo."""
    caps = lector.capitulos(texto)
    globales = _tramo(texto, idioma)
    globales["legibilidad_detalle"] = legibilidad(texto, idioma)
    globales["diversidad_lexica"] = mtld(palabras(texto))

    por_capitulo = []
    if len(caps) > 1:
        for cap in caps:
            fila = _tramo(cap["texto"], idioma)
            fila["titulo"] = cap["titulo"]
            por_capitulo.append(fila)
        # Tramo lento: frases un 25 % más largas que las del capítulo mediano y menos
        # diálogo que él. Se compara con la mediana de los capítulos y no con la media de
        # todas las frases, que unos pocos capítulos de frase muy corta arrastran hacia abajo.
        # Es una señal para mirar el capítulo, no un juicio.
        frase_mediana = statistics.median(c["frase_media"] for c in por_capitulo)
        dialogo_mediano = statistics.median(c["dialogo"] for c in por_capitulo)
        for fila in por_capitulo:
            fila["lento"] = bool(
                fila["palabras"] >= 300
                and fila["frase_media"] >= frase_mediana * 1.25
                and fila["dialogo"] <= dialogo_mediano
                and fila["frase_media"] > 0
            )
        globales["frase_mediana_capitulos"] = round(frase_mediana, 1)

    return {
        "global": globales,
        "capitulos": por_capitulo,
        "capitulos_detectados": len(caps) if len(caps) > 1 else 0,
        "tramos_lentos": sum(1 for c in por_capitulo if c["lento"]),
    }
