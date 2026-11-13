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
