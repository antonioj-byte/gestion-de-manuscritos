"""Análisis de un manuscrito: ficha, sumario, temas y tags.

Con credenciales de Anthropic (ANTHROPIC_API_KEY o ANTHROPIC_AUTH_TOKEN) lo hace Claude
leyendo el texto completo. Sin ellas se hace una extracción básica local, por frecuencia de
palabras, que sirve para probar el flujo pero no entiende el texto.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

MODELO = os.environ.get("MANUSCRITOS_MODELO", "claude-opus-5-5")

GENEROS = (
    "Novela", "Novela negra", "Novela histórica", "Ciencia ficción", "Fantasía", "Terror",
    "Novela romántica", "Relatos", "Poesía", "Ensayo", "Memorias y biografía", "Crónica",
    "Infantil y juvenil", "Novela gráfica", "Teatro", "Otro",
)


class Ficha(BaseModel):
    titulo: str = Field(description="Título del manuscrito tal como aparece en el texto.")
    autor: str = Field(description="Nombre del autor o autora si aparece; si no, cadena vacía.")
    idioma: str = Field(description="Idioma del texto, en español: Español, Catalán, Inglés…")
    genero: str = Field(description="Uno de los géneros de la lista dada.")
    subgenero: str = Field(description="Precisión libre del género, pocas palabras.")
    publico: str = Field(description="Público lector: Adulto, Juvenil, Infantil, Académico…")
    ambientacion: str = Field(description="Lugar y época, en una línea; vacío si no aplica.")
    tono: list[str] = Field(description="De 1 a 3 adjetivos en minúscula.")
    logline: str = Field(description="Una sola frase que cuente de qué va.")
    sumario: str = Field(description="Sumario de 120 a 200 palabras, en español.")
    temas: list[str] = Field(description="De 3 a 6 temas de fondo, en minúscula.")
    tags: list[str] = Field(description="De 6 a 12 etiquetas concretas, en minúscula.")
    comparables: list[str] = Field(description="Hasta 3 títulos publicados comparables.")


_SISTEMA = f"""Eres lector editorial de una editorial en español. Recibes el texto de un \
manuscrito que ha llegado a la editorial y preparas su ficha para que el equipo pueda \
encontrarlo y filtrarlo entre muchos otros.

Escribe la ficha en español, aunque el manuscrito esté en otro idioma. Describe el texto, \
no lo valores: la ficha sirve para clasificar, la decisión de publicar es del equipo.

Género: elige exactamente uno de esta lista: {", ".join(GENEROS)}.

Temas y tags se usan como filtros, así que importa que distintos manuscritos compartan \
vocabulario. Los temas son los asuntos de fondo (duelo, memoria, migración). Los tags son \
más concretos: escenario, época, tipo de personaje, recurso formal, subgénero (galicia, \
años 80, narradora adolescente, novela coral, epistolar). Usa formas cortas, en minúscula y \
en singular. Si un tema o tag de los ya existentes en el catálogo, que se te dan con el \
manuscrito, describe bien este texto, usa esa misma forma en vez de inventar un sinónimo; \
crea uno nuevo solo cuando ninguno encaje.

No inventes datos que el texto no da: si el autor no figura, deja el campo vacío."""


def hay_ia() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def cargar_env(ruta: Path) -> None:
    """Lee un .env sencillo (CLAVE=valor) sin pisar lo que ya esté en el entorno."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip("'\""))


def analizar(texto: str, archivo: str, vocabulario: dict[str, list[str]]) -> tuple[dict, str]:
    """Devuelve (ficha, fuente); fuente es «ia» o «local»."""
    if hay_ia():
        return _con_claude(texto, archivo, vocabulario), "ia"
    return _local(texto, archivo), "local"


def pedir(sistema: str, usuario: str, esquema: type[BaseModel], max_tokens: int = 16000):
    """Una petición a Claude con respuesta validada contra `esquema`.

    Devuelve (objeto, uso) con uso = {"entrada": tokens, "salida": tokens}. Los fallos
    salen como RuntimeError con un mensaje que se puede enseñar tal cual.
    """
    import anthropic

    try:
        respuesta = anthropic.Anthropic().messages.parse(
            model=MODELO,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=sistema,
            messages=[{"role": "user", "content": usuario}],
            output_format=esquema,
        )
    except anthropic.AuthenticationError as e:
        raise RuntimeError("La clave de Anthropic no es válida.") from e
    except anthropic.RequestTooLargeError as e:
        raise RuntimeError("El manuscrito es demasiado largo para analizarlo de una vez.") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Límite de uso de la API alcanzado; inténtalo en unos minutos.") from e
    except anthropic.BadRequestError as e:
        raise RuntimeError(f"La API ha rechazado la petición: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Error de la API ({e.status_code}); inténtalo de nuevo.") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError("No se ha podido conectar con la API de Anthropic.") from e

    if respuesta.stop_reason == "refusal":
        raise RuntimeError("El modelo ha declinado analizar este texto.")
    if respuesta.stop_reason == "max_tokens" or respuesta.parsed_output is None:
        raise RuntimeError("El análisis ha quedado incompleto; vuelve a intentarlo.")
    uso = {"entrada": respuesta.usage.input_tokens, "salida": respuesta.usage.output_tokens}
    return respuesta.parsed_output, uso


def _con_claude(texto: str, archivo: str, vocabulario: dict[str, list[str]]) -> dict:
    existentes = (
        f"Temas ya existentes en el catálogo: {', '.join(vocabulario['temas']) or '(ninguno)'}\n"
        f"Tags ya existentes en el catálogo: {', '.join(vocabulario['tags']) or '(ninguno)'}"
    )
    objeto, _ = pedir(
        _SISTEMA,
        f"Archivo: {archivo}\n{existentes}\n\n<manuscrito>\n{texto}\n</manuscrito>\n\n"
        "Prepara la ficha de este manuscrito.",
        Ficha,
    )
    ficha = objeto.model_dump()
    for campo in ("temas", "tags", "tono"):
        ficha[campo] = normalizar(ficha[campo])
    return ficha


def normalizar(etiquetas: list[str]) -> list[str]:
    """Minúscula, sin espacios sobrantes ni repetidos, conservando el orden."""
    vistas: dict[str, None] = {}
    for e in etiquetas:
        e = re.sub(r"\s+", " ", str(e)).strip().strip("#.,;").lower()
        if e:
            vistas.setdefault(e, None)
    return list(vistas)


# --- Extracción básica, sin IA -------------------------------------------------------------

_VACIAS = {
    "es": set(
        "de la que el en y a los del se las por un para con no una su al lo como más pero sus "
        "le ya o este sí porque esta entre cuando muy sin sobre también me hasta hay donde "
        "quien desde todo nos durante todos uno les ni contra otros ese eso ante ellos e esto "
        "mí antes algunos qué unos yo otro otras otra él tanto esa estos mucho quienes nada "
        "muchos cual poco ella estar estas algunas algo nosotros mi mis tú te ti tu tus ellas "
        "era fue había ser es son está han ha he si casi cada vez dos tres aquel aquella tan "
        "así solo sólo aún ahora después luego entonces mientras tenía estaba eran hacía dijo "
        "decía sido tiene hace puede años año día días veces cosa cosas siempre nunca mismo "
        "misma bien mal aquí allí tras según todas toda cómo dónde cuándo habían estaban "
        "hacia fueron tener hacer decir ver ir dar saber querer poder parte modo"
    .split()),
    "en": set(
        "the of and to a in that is was he for it with as his on be at by i this had not are "
        "but from or have an they which one you were her all she there would their we him "
        "been has when who will more no if out so said what up its about into than them can "
        "only other new some could time these two may then do first any my now such like our "
        "over man me even most made after also did many before must through back years where "
        "much your way well down should because each just those people how too little very"
    .split()),
}

_TEMAS = {
    "familia": "familia madre padre hermano hermana abuela abuelo hijo hija hijos".split(),
    "duelo": "duelo muerte murió entierro funeral ausencia luto viuda viudo".split(),
    "memoria": "memoria recuerdo recuerdos recordar olvido olvidar pasado".split(),
    "amor": "amor amante enamorado enamorada beso deseo pareja".split(),
    "guerra": "guerra frente soldado soldados batalla trinchera ejército posguerra".split(),
    "migración": "exilio emigrar emigrante frontera migrante inmigrante patria".split(),
    "infancia": "infancia niño niña niños colegio escuela juego".split(),
    "mundo rural": "pueblo aldea campo cosecha ganado huerto monte".split(),
    "ciudad": "ciudad barrio calle metro edificio avenida".split(),
    "trabajo": "trabajo fábrica oficina sueldo jefe huelga despido".split(),
    "naturaleza": "bosque mar río montaña árbol árboles lluvia clima".split(),
    "poder": "poder gobierno ministro política elecciones régimen dictadura".split(),
    "identidad": "identidad nombre cuerpo espejo género raíces".split(),
    "crimen": "crimen asesinato cadáver policía inspector inspectora sospechoso".split(),
    "tecnología": "pantalla algoritmo máquina robot red datos inteligencia nave".split(),
}

_PISTAS_GENERO = {
    "Novela negra": "asesinato cadáver inspector inspectora comisaría sospechoso".split(),
    "Ciencia ficción": "nave planeta colonia androide órbita algoritmo".split(),
    "Fantasía": "reino dragón hechizo mago espada bruja".split(),
    "Ensayo": "ensayo tesis concepto capítulo argumento sociedad".split(),
    "Memorias y biografía": "memorias nací recuerdo infancia autobiografía".split(),
}


def _local(texto: str, archivo: str) -> dict:
    palabras = re.findall(r"[^\W\d_]+", texto.lower())
    idioma = _idioma(palabras)
    vacias = _VACIAS["en" if idioma == "Inglés" else "es"]
    cuenta = Counter(p for p in palabras if len(p) > 3 and p not in vacias)

    temas = sorted(
        (t for t in _TEMAS if sum(cuenta[p] for p in _TEMAS[t]) >= 2),
        key=lambda t: -sum(cuenta[p] for p in _TEMAS[t]),
    )[:5]
    ya = {p for t in temas for p in _TEMAS[t]}
    # Solo palabras que se repiten: una que sale una vez no dice nada del texto.
    tags = [p for p, n in cuenta.most_common(40) if n >= 2 and p not in ya][:10]

    titulo, autor = _cabecera(texto, archivo)
    frases = re.split(r"(?<=[.!?…])\s+", " ".join(_cuerpo(texto).split()))
    return {
        "titulo": titulo,
        "autor": autor,
        "idioma": idioma,
        "genero": _genero(texto, cuenta),
        "subgenero": "",
        "publico": "",
        "ambientacion": "",
        "tono": [],
        "logline": "",
        "sumario": " ".join(frases[:4])[:900],
        "temas": temas,
        "tags": tags,
        "comparables": [],
    }


def _idioma(palabras: list[str]) -> str:
    muestra = palabras[:5000]
    es = sum(1 for p in muestra if p in _VACIAS["es"])
    en = sum(1 for p in muestra if p in _VACIAS["en"])
    if max(es, en) < 5:
        return ""
    return "Español" if es >= en else "Inglés"


def _genero(texto: str, cuenta: Counter) -> str:
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if lineas and sum(len(ln) for ln in lineas) / len(lineas) < 45 and len(lineas) > 12:
        return "Poesía"
    mejor, puntos = "", 0
    for genero, pistas in _PISTAS_GENERO.items():
        p = sum(cuenta[x] for x in pistas)
        if p > puntos:
            mejor, puntos = genero, p
    return mejor if puntos >= 3 else "Sin clasificar"


def _cabecera(texto: str, archivo: str) -> tuple[str, str]:
    """Título y autor a partir de las primeras líneas, o del nombre del archivo."""
    lineas = [ln.strip(" #*_\t") for ln in texto.splitlines()[:12] if ln.strip(" #*_\t")]
    titulo = autor = ""
    for ln in lineas[:6]:
        m = re.match(r"(?i)^(?:autora?|por|de|by)\s*:?\s+(.{3,60})$", ln)
        if m and not autor:
            autor = m.group(1).strip()
        elif not titulo and len(ln) <= 90:
            titulo = re.sub(r"(?i)^t[ií]tulo\s*:\s*", "", ln)
    if not titulo:
        titulo = re.sub(r"[_\-]+", " ", Path(archivo).stem).strip().capitalize()
    return titulo, autor


def _cuerpo(texto: str) -> str:
    """El texto sin las líneas cortas de portada del principio."""
    lineas = texto.splitlines()
    for i, ln in enumerate(lineas[:20]):
        if len(ln.strip()) > 120:
            return "\n".join(lineas[i:])
    return texto
