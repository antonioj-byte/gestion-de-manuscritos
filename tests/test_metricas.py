"""Métricas deterministas, comprobadas con textos de resultado conocido."""

import pytest

from app import metricas, texto


@pytest.mark.parametrize(
    "palabra, n",
    [
        ("casa", 2), ("aire", 2), ("ciudad", 2), ("leer", 2), ("queso", 2), ("guerra", 2),
        ("muy", 1), ("y", 1), ("yo", 1), ("biología", 4), ("oía", 3), ("país", 2),
        ("murciélago", 4), ("pingüino", 3), ("transatlántico", 5), ("rey", 1), ("héroe", 3),
    ],
)
def test_silabas_es(palabra, n):
    assert metricas.silabas_es(palabra) == n


@pytest.mark.parametrize(
    "palabra, n",
    [("cat", 1), ("make", 1), ("table", 2), ("reading", 2), ("wanted", 2), ("walked", 1), ("beautiful", 3)],
)
def test_silabas_en(palabra, n):
    assert metricas.silabas_en(palabra) == n


def test_frases_y_palabras():
    t = "¿Vienes? Sí, ya voy… ¡Espera! Dijo que no."
    assert len(metricas.frases(t)) == 4
    assert len(metricas.palabras(t)) == 8


def test_szigriszt_resultado_conocido():
    # 200 palabras de dos sílabas en 40 frases de 5 palabras:
    # 206,835 − 62,3·2 − 5 = 77,235; Fernández-Huerta: 206,84 − 120 − 5,1 = 81,74.
    t = " ".join(["Casa mesa libro perro gato."] * 40)
    r = metricas.legibilidad(t, "Español")
    assert r["valor"] == pytest.approx(77.2, abs=0.05)
    assert r["fernandez_huerta"] == pytest.approx(81.7, abs=0.05)
    assert r["nivel"] == "Bastante fácil"
    assert r["nota"] == 77


def test_flesch_resultado_conocido():
    # 200 palabras de una sílaba en 40 frases de 5: 206,835 − 84,6 − 5,075 = 117,16 → tope 100.
    t = " ".join(["The cat sat on mats."] * 40)
    r = metricas.legibilidad(t, "Inglés")
    assert r["valor"] == pytest.approx(117.2, abs=0.05)
    assert r["nota"] == 100


def test_frases_largas_son_mas_dificiles():
    facil = " ".join(["El niño come pan."] * 50)
    dificil = " ".join(
        ["La administración establecerá procedimientos extraordinarios considerando "
         "circunstancias socioeconómicas particularmente desfavorables para determinados "
         "contribuyentes independientemente de consideraciones presupuestarias anteriores."] * 12
    )
    assert metricas.legibilidad(facil, "Español")["nota"] > 80
    assert metricas.legibilidad(dificil, "Español")["nota"] < 20


def test_legibilidad_sin_formula_o_sin_texto():
    t = " ".join(["Casa mesa libro perro gato."] * 40)
    assert metricas.legibilidad(t, "Catalán") is None
    assert metricas.legibilidad("Muy poco texto.", "Español") is None


def test_dialogo_con_raya_y_comillas():
    solo_raya = "—Hola, ¿qué tal estás?\n\n—Bien, gracias."
    assert metricas.proporcion_dialogo(solo_raya) == 1.0
    assert metricas.proporcion_dialogo("Caminó por la calle sin decir nada a nadie.") == 0.0
    mitad = "—Uno dos tres cuatro.\n\nCinco seis siete ocho."
    assert metricas.proporcion_dialogo(mitad) == 0.5
    comillas = "Dijo «uno dos» y luego tres cuatro."  # 2 de 7 palabras
    assert metricas.proporcion_dialogo(comillas) == pytest.approx(2 / 7)


def test_mtld_distingue_texto_repetido_de_variado():
    repetido = ("el perro come " * 100).split()
    variado = [f"palabra{i}" for i in range(300)]
    assert metricas.mtld(repetido) < 10
    assert metricas.mtld(variado) == 300  # ningún tramo baja del umbral
    assert metricas.mtld(repetido) < metricas.mtld(variado)
    assert metricas.mtld(["pocas", "palabras"]) is None


def test_variacion_de_frase():
    iguales = " ".join(["Uno dos tres cuatro."] * 30)
    assert metricas._tramo(iguales, "Español")["variacion_frase"] == 0
    mezcla = " ".join(["Sí.", "Uno dos tres cuatro cinco seis siete ocho nueve diez once doce."] * 15)
    assert metricas._tramo(mezcla, "Español")["variacion_frase"] > 0.7


def _manuscrito():
    agil = "\n\n".join(["—¿Vienes ya?", "—Ahora voy.", "Salió deprisa. Cerró la puerta."] * 40)
    lento = " ".join(
        ["La casa de los abuelos tenía un pasillo largo y oscuro que olía a madera vieja y a "
         "manzanas guardadas desde el otoño en los armarios altos de la despensa del fondo."] * 30
    )
    return f"Título\n\nCapítulo 1\n\n{agil}\n\nCapítulo 2\n\n{lento}\n\nCapítulo 3\n\n{agil}"


def test_calcular_marca_el_capitulo_lento():
    m = metricas.calcular(_manuscrito(), "Español")
    assert m["capitulos_detectados"] == 3
    assert [c["lento"] for c in m["capitulos"]] == [False, True, False]
    assert m["tramos_lentos"] == 1
    # Capítulo 1: 4 de cada 9 palabras van tras raya; el 2 no tiene diálogo.
    assert m["capitulos"][0]["dialogo"] == pytest.approx(4 / 9, abs=0.001)
    assert m["capitulos"][1]["dialogo"] == 0
    assert m["global"]["legibilidad"] is not None


def test_calcular_es_reproducible():
    assert metricas.calcular(_manuscrito(), "Español") == metricas.calcular(_manuscrito(), "Español")


def test_sin_capitulos_no_se_inventan():
    m = metricas.calcular(" ".join(["Casa mesa libro perro gato."] * 60), "Español")
    assert m["capitulos"] == [] and m["capitulos_detectados"] == 0


def test_capitulos_y_numeros_de_pagina():
    assert [c["titulo"] for c in texto.capitulos(_manuscrito())] == ["Capítulo 1", "Capítulo 2", "Capítulo 3"]
    # Números sueltos cada pocas palabras son paginación de PDF, no capítulos.
    paginado = "\n".join(f"Texto de la página con algunas palabras más.\n{i}" for i in range(1, 30))
    assert len(texto.capitulos(paginado)) == 1
    assert len(texto.capitulos("mi\n\ntexto\n\ndi\n\notro")) == 1


def test_fragmentos_respetan_capitulos_y_parrafos():
    largo = "\n\n".join(["palabra " * 500] * 14)  # 7.000 palabras en párrafos de 500
    caps = [{"titulo": "Uno", "texto": largo}, {"titulo": "Dos", "texto": "corto " * 200},
            {"titulo": "Tres", "texto": "breve " * 300}]
    fr = texto.fragmentos(caps, objetivo=3000)
    assert all(texto.contar_palabras(f["texto"]) <= 3600 for f in fr)
    assert sum(texto.contar_palabras(f["texto"]) for f in fr) == 7500
    assert fr[0]["capitulos"] == ["Uno"]
    assert fr[-1]["capitulos"] == ["Dos", "Tres"]  # los dos cortos van juntos
