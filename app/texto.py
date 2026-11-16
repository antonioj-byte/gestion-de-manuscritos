"""Saca el texto de un manuscrito subido (.docx, .pdf, .epub, .txt, .md)."""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

EXTENSIONES = (".docx", ".pdf", ".epub", ".txt", ".md")


class FormatoNoAdmitido(ValueError):
    pass


def extraer(ruta: Path) -> str:
    ext = ruta.suffix.lower()
    if ext in (".txt", ".md"):
        texto = _plano(ruta)
    elif ext == ".docx":
        texto = _docx(ruta)
    elif ext == ".pdf":
        texto = _pdf(ruta)
    elif ext == ".epub":
        texto = _epub(ruta)
    else:
        raise FormatoNoAdmitido(
            f"Formato «{ext or 'sin extensión'}» no admitido. "
            f"Se admiten: {', '.join(EXTENSIONES)}."
        )
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if not texto:
        raise ValueError(
            "No se ha podido leer texto en el archivo (¿es un PDF escaneado, solo con imágenes?)."
        )
    return texto


def _plano(ruta: Path) -> str:
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeError:
            continue
    return datos.decode("latin-1")


def _docx(ruta: Path) -> str:
    import docx

    documento = docx.Document(str(ruta))
    return "\n\n".join(p.text for p in documento.paragraphs if p.text.strip())


def _pdf(ruta: Path) -> str:
    from pypdf import PdfReader

    lector = PdfReader(str(ruta))
    return "\n\n".join((pagina.extract_text() or "") for pagina in lector.pages)


def _epub(ruta: Path) -> str:
    partes: list[str] = []
    with zipfile.ZipFile(ruta) as z:
        for nombre in sorted(z.namelist()):
            if not nombre.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            crudo = z.read(nombre).decode("utf-8", errors="replace")
            crudo = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", crudo)
            crudo = re.sub(r"(?i)</(p|div|h[1-6]|li)>|<br\s*/?>", "\n\n", crudo)
            partes.append(html.unescape(re.sub(r"<[^>]+>", " ", crudo)))
    return "\n\n".join(partes)


def contar_palabras(texto: str) -> int:
    return len(re.findall(r"\w+", texto))


def extracto(texto: str, largo: int = 1400) -> str:
    """Primeras líneas del manuscrito, cortadas en un final de frase."""
    if len(texto) <= largo:
        return texto
    trozo = texto[:largo]
    corte = max(trozo.rfind(". "), trozo.rfind(".\n"), trozo.rfind("? "), trozo.rfind("! "))
    return (trozo[: corte + 1] if corte > largo * 0.5 else trozo).rstrip() + " […]"


# --- Capítulos y fragmentos ----------------------------------------------------------------

_NUMERAL = (
    r"(?:\d{1,3}|[ivxlcdm]{1,7}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce"
    r"|primero|segundo|tercero|cuarto|quinto|primera|segunda|tercera|one|two|three|four|five"
    r"|six|seven|eight|nine|ten)"
)
_CABECERA = re.compile(
    rf"^\s*(?:#{{1,3}}\s+\S.*"
    rf"|(?:cap[ií]tulo|cap[ií]tol|chapter|parte|part|libro|book)\s+{_NUMERAL}\b.{{0,80}}"
    rf"|(?:pr[oó]logo|ep[ií]logo|prologue|epilogue|introducci[oó]n|introduction)\.?"
    rf"|(?:\d{{1,3}}|[IVXLCDM]{{1,7}})\.?)\s*$",
    re.IGNORECASE,
)
# Un número romano suelto solo cuenta como cabecera en mayúsculas («I», «IV»), no «mi» o «di».
_ROMANO_SUELTO = re.compile(r"^\s*[ivxlcdm]{1,7}\.?\s*$")


def capitulos(texto: str) -> list[dict]:
    """Parte el texto por sus cabeceras de capítulo.

    Devuelve [{"titulo", "texto"}]. Si no se reconocen al menos dos cabeceras, todo el
    texto va en un único capítulo sin título: no se inventan divisiones.
    """
    lineas = texto.splitlines()
    cortes = [
        i
        for i, ln in enumerate(lineas)
        if len(ln.strip()) <= 100
        and _CABECERA.match(ln)
        and not (_ROMANO_SUELTO.match(ln) and ln.strip() != ln.strip().upper())
    ]
    # Números sueltos muy seguidos son números de página de un PDF, no capítulos.
    sueltos = [i for i in cortes if lineas[i].strip(" .").isdigit()]
    if len(sueltos) >= 2:
        palabras = contar_palabras("\n".join(lineas[sueltos[0] : sueltos[-1]]))
        if palabras / (len(sueltos) - 1) < 600:
            cortes = [i for i in cortes if i not in set(sueltos)]
    if len(cortes) < 2:
        return [{"titulo": "", "texto": texto.strip()}]

    partes = []
    previo = "\n".join(lineas[: cortes[0]]).strip()
    if contar_palabras(previo) > 150:  # texto antes del primer capítulo que no es solo portada
        partes.append({"titulo": "Inicio", "texto": previo})
    for n, i in enumerate(cortes):
        fin = cortes[n + 1] if n + 1 < len(cortes) else len(lineas)
        cuerpo = "\n".join(lineas[i + 1 : fin]).strip()
        if cuerpo:
            partes.append({"titulo": lineas[i].strip(" #\t."), "texto": cuerpo})
    return partes if len(partes) >= 2 else [{"titulo": "", "texto": texto.strip()}]


def fragmentos(caps: list[dict], objetivo: int = 3000) -> list[dict]:
    """Trozos de unas `objetivo` palabras para leerlos de uno en uno.

    Un capítulo largo se parte por párrafos; varios capítulos cortos seguidos se juntan.
    Ningún párrafo se corta por la mitad. Devuelve [{"capitulos": [títulos], "texto"}].
    """
    piezas: list[dict] = []
    for cap in caps:
        parrafos = [p for p in re.split(r"\n\s*\n", cap["texto"]) if p.strip()]
        actual: list[str] = []
        cuenta = 0
        for p in parrafos:
            n = contar_palabras(p)
            if actual and cuenta + n > objetivo * 1.2:
                piezas.append({"capitulos": [cap["titulo"]], "texto": "\n\n".join(actual), "n": cuenta})
                actual, cuenta = [], 0
            actual.append(p)
            cuenta += n
        if actual:
            piezas.append({"capitulos": [cap["titulo"]], "texto": "\n\n".join(actual), "n": cuenta})

    juntos: list[dict] = []
    for pieza in piezas:
        if juntos and juntos[-1]["n"] + pieza["n"] <= objetivo:
            ultimo = juntos[-1]
            for t in pieza["capitulos"]:
                if t not in ultimo["capitulos"]:
                    ultimo["capitulos"].append(t)
            ultimo["texto"] += "\n\n" + pieza["texto"]
            ultimo["n"] += pieza["n"]
        else:
            juntos.append(pieza)
    return [{"capitulos": [t for t in f["capitulos"] if t], "texto": f["texto"]} for f in juntos]
