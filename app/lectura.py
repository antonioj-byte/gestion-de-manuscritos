"""Lectura asistida: notas por fragmento, rúbrica e informe de lectura.

El manuscrito se lee por fragmentos de unas 3.000 palabras (una nota por fragmento, en
paralelo) y después se sintetiza todo en una rúbrica y un borrador de informe. Las notas
de la rúbrica son la opinión de un modelo, justificada con citas del texto: sirven para
ordenar la pila y preparar el informe, no para decidir.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

from . import analisis, texto

PARALELO = 4

# Precio por millón de tokens (entrada, salida) para estimar el coste de cada lectura.
PRECIOS = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0)}

CRITERIOS = {
    "premisa": "Premisa",
    "voz": "Voz",
    "estructura": "Estructura",
    "personajes": "Personajes",
    "prosa": "Prosa",
    "originalidad": "Originalidad",
    "ajuste_genero": "Ajuste al género",
    "potencial_comercial": "Potencial comercial",
}
RECOMENDACIONES = {
    "rechazar": "Rechazar",
    "reconsiderar": "Reconsiderar",
    "pedir_completo": "Pedir más material",
    "avanzar": "Llevar a comité",
}


class NotaFragmento(BaseModel):
    resumen: str = Field(description="Qué pasa o qué se argumenta en este fragmento, 2 o 3 frases.")
    trama: str = Field(description="Cómo avanza la trama o el argumento aquí; vacío si no avanza.")
    personajes: str = Field(description="Qué se ve de los personajes; vacío si no aplica.")
    voz_y_prosa: str = Field(description="Observaciones sobre la voz y la prosa en este tramo.")
    problemas: list[str] = Field(description="Problemas concretos de este fragmento; puede ir vacía.")
    citas: list[str] = Field(description="De 1 a 3 citas literales, breves, que sirvan de evidencia.")
    tension: int = Field(description="Tensión narrativa del fragmento, de 1 (reposo) a 5 (máxima).")
    tono: int = Field(description="Tono emocional dominante, de -2 (muy oscuro) a 2 (muy luminoso).")


class Criterio(BaseModel):
    aplica: bool = Field(description="False si el criterio no tiene sentido para este texto.")
    nota: int = Field(description="Nota de 1 a 10 según los anclajes; 0 si no aplica.")
    justificacion: str = Field(description="Por qué esa nota, en 1 o 2 frases.")
    cita: str = Field(description="Cita literal del texto que lo respalda; vacío si no hay.")


class Sintesis(BaseModel):
    premisa: Criterio
    voz: Criterio
    estructura: Criterio
    personajes: Criterio
    prosa: Criterio
    originalidad: Criterio
    ajuste_genero: Criterio
    potencial_comercial: Criterio
    fortalezas: list[str] = Field(description="De 2 a 5 fortalezas concretas.")
    debilidades: list[str] = Field(description="De 2 a 5 debilidades concretas.")
    recomendacion: Literal["rechazar", "reconsiderar", "pedir_completo", "avanzar"]
    motivo: str = Field(description="El motivo de la recomendación, en una o dos frases.")
    informe: str = Field(description="Borrador del informe de lectura interno, 250-400 palabras.")
    para_el_autor: str = Field(description="Versión para el autor, 150-250 palabras.")


_SISTEMA_NOTA = """Eres lector editorial. Lees un fragmento de un manuscrito que ha llegado \
a una editorial y tomas notas para quien después escribirá el informe de lectura de la obra \
completa; esa persona no verá el texto, solo tus notas, así que anota lo concreto.

Escribe en español aunque el texto esté en otro idioma. Las citas son literales, en el \
idioma original, y cortas. Si no hay problemas en el fragmento, deja la lista vacía: no \
busques defectos por cumplir. La tensión y el tono describen cómo se lee este tramo \
respecto a una novela corriente, no su calidad."""

_SISTEMA_SINTESIS = """Eres lector editorial de una editorial en español. Con las notas \
tomadas fragmento a fragmento de un manuscrito, escribes su valoración para el equipo \
editorial, que decide con ella a qué manuscritos de la pila dedica una lectura completa.

Puntúa cada criterio de 1 a 10 con estos anclajes, y usa toda la escala:
- 1-2: fallo grave que impide seguir leyendo.
- 3-4: por debajo de lo publicable; problemas de fondo.
- 5-6: correcto y sin relieve; lo habitual en lo que llega sin solicitar.
- 7-8: bueno; destacaría entre lo publicado en su género.
- 9-10: excepcional; se da muy pocas veces.
La mayoría de los manuscritos están entre 4 y 6 en casi todo: un 7 necesita un motivo \
concreto y un 9 uno extraordinario. Cada nota se apoya en lo que dicen las notas de \
lectura; si para un criterio no hay base suficiente, dilo en la justificación. Marca \
«aplica: false» cuando el criterio no tenga sentido (personajes en un ensayo).

«Ajuste al género» mide si cumple las convenciones del género declarado (estructura, tono, \
extensión). «Potencial comercial» es tu lectura del texto, no una previsión de ventas: no \
tienes datos de mercado y no debes insinuar que los tienes.

El informe es para uso interno: directo, con lo que funciona, lo que no y qué haría falta. \
La versión para el autor cuenta lo mismo de forma constructiva, sin notas numéricas, sin la \
recomendación y sin consideraciones comerciales internas. Las citas son literales."""


def leer(contenido: str, ficha: dict, pedir=analisis.pedir) -> dict:
    """Lectura completa de un manuscrito. `pedir` se puede sustituir en los tests."""
    inicio = time.monotonic()
    trozos = texto.fragmentos(texto.capitulos(contenido))
    contexto = (
        f"Título: {ficha.get('titulo') or '(sin título)'}\n"
        f"Género declarado: {ficha.get('genero') or '(sin clasificar)'}\n"
    )

    def nota(i: int) -> tuple[dict, dict]:
        trozo = trozos[i]
        donde = f" ({', '.join(trozo['capitulos'])})" if trozo["capitulos"] else ""
        objeto, uso = pedir(
            _SISTEMA_NOTA,
            f"{contexto}Fragmento {i + 1} de {len(trozos)}{donde}.\n\n"
            f"<fragmento>\n{trozo['texto']}\n</fragmento>",
            NotaFragmento,
            4000,
        )
        d = objeto.model_dump()
        d["tension"] = min(5, max(1, d["tension"]))
        d["tono"] = min(2, max(-2, d["tono"]))
        d["capitulos"] = trozo["capitulos"]
        d["palabras"] = texto.contar_palabras(trozo["texto"])
        return d, uso

    with ThreadPoolExecutor(max_workers=PARALELO) as grupo:
        resultados = list(grupo.map(nota, range(len(trozos))))
    notas = [r[0] for r in resultados]
    usos = [r[1] for r in resultados]

    apuntes = "\n\n".join(
        f"Fragmento {i + 1}:\n" + json.dumps(
            {k: n[k] for k in ("resumen", "trama", "personajes", "voz_y_prosa", "problemas", "citas")},
            ensure_ascii=False, indent=1,
        )
        for i, n in enumerate(notas)
    )
    objeto, uso = pedir(
        _SISTEMA_SINTESIS,
        f"{contexto}Extensión: {texto.contar_palabras(contenido)} palabras.\n"
        f"Sumario: {ficha.get('sumario') or '(sin sumario)'}\n\n"
        f"<notas_de_lectura>\n{apuntes}\n</notas_de_lectura>\n\nEscribe la valoración.",
        Sintesis,
        16000,
    )
    usos.append(uso)
    sintesis = objeto.model_dump()

    rubrica = {}
    for clave in CRITERIOS:
        c = sintesis.pop(clave)
        c["nota"] = min(10, max(1, c["nota"])) if c["aplica"] else None
        rubrica[clave] = c
    puntuadas = [c["nota"] for c in rubrica.values() if c["nota"] is not None]

    entrada = sum(u["entrada"] for u in usos)
    salida = sum(u["salida"] for u in usos)
    precio = PRECIOS.get(analisis.MODELO)
    return {
        **sintesis,
        "rubrica": rubrica,
        # Media simple de los criterios que aplican; sin pesos, para no esconder decisiones.
        "media": round(sum(puntuadas) / len(puntuadas), 1) if puntuadas else None,
        "arco": [
            {"tension": n["tension"], "tono": n["tono"], "capitulos": n["capitulos"],
             "resumen": n["resumen"], "palabras": n["palabras"]}
            for n in notas
        ],
        "problemas": [p for n in notas for p in n["problemas"]],
        "modelo": analisis.MODELO,
        "fragmentos": len(trozos),
        "tokens_entrada": entrada,
        "tokens_salida": salida,
        "coste_usd": round((entrada * precio[0] + salida * precio[1]) / 1e6, 2) if precio else None,
        "segundos": round(time.monotonic() - inicio),
    }
