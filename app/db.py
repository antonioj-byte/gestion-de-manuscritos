"""Almacén de manuscritos en SQLite (un solo fichero en data/)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
ORIGINALES = DATOS / "originales"
TEXTOS = DATOS / "textos"

ORIGENES = ("solicitado", "no_solicitado")
ESTADOS = ("recibido", "en_lectura", "preseleccionado", "descartado", "contratado")

# Columnas que guardan listas u objetos (JSON en la base de datos).
LISTAS = ("temas", "tags", "tono", "comparables")
OBJETOS = ("metricas", "lectura")

# Columnas añadidas después de la primera versión: se crean si faltan.
_NUEVAS = {
    "metricas": "TEXT NOT NULL DEFAULT 'null'",
    "lectura": "TEXT NOT NULL DEFAULT 'null'",
    "lectura_proceso": "TEXT NOT NULL DEFAULT ''",
    "lectura_error": "TEXT NOT NULL DEFAULT ''",
}

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS manuscritos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL DEFAULT '',
    autor TEXT NOT NULL DEFAULT '',
    archivo TEXT NOT NULL DEFAULT '',
    origen TEXT NOT NULL DEFAULT 'no_solicitado',
    estado TEXT NOT NULL DEFAULT 'recibido',
    proceso TEXT NOT NULL DEFAULT 'analizando',
    error TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    idioma TEXT NOT NULL DEFAULT '',
    genero TEXT NOT NULL DEFAULT '',
    subgenero TEXT NOT NULL DEFAULT '',
    publico TEXT NOT NULL DEFAULT '',
    ambientacion TEXT NOT NULL DEFAULT '',
    logline TEXT NOT NULL DEFAULT '',
    sumario TEXT NOT NULL DEFAULT '',
    extracto TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    palabras INTEGER NOT NULL DEFAULT 0,
    temas TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    tono TEXT NOT NULL DEFAULT '[]',
    comparables TEXT NOT NULL DEFAULT '[]',
    creado TEXT NOT NULL
);
"""

_cierre = threading.Lock()


def _conexion() -> sqlite3.Connection:
    DATOS.mkdir(exist_ok=True)
    con = sqlite3.connect(DATOS / "manuscritos.db", timeout=10)
    con.row_factory = sqlite3.Row
    return con


def iniciar() -> None:
    ORIGINALES.mkdir(parents=True, exist_ok=True)
    TEXTOS.mkdir(parents=True, exist_ok=True)
    with _conexion() as con:
        con.executescript(_ESQUEMA)
        hay = {f["name"] for f in con.execute("PRAGMA table_info(manuscritos)")}
        for columna, tipo in _NUEVAS.items():
            if columna not in hay:
                con.execute(f"ALTER TABLE manuscritos ADD COLUMN {columna} {tipo}")
        con.execute(
            "UPDATE manuscritos SET lectura_proceso='error', lectura_error='La lectura se "
            "interrumpió; vuelve a pedirla.' WHERE lectura_proceso='leyendo'"
        )
        # Un análisis que quedó a medias al parar el servidor ya no va a terminar.
        con.execute(
            "UPDATE manuscritos SET proceso='error', error='El análisis se interrumpió; "
            "vuelve a analizarlo.' WHERE proceso='analizando'"
        )


def _fila(f: sqlite3.Row) -> dict:
    d = dict(f)
    for campo in LISTAS:
        d[campo] = json.loads(d[campo] or "[]")
    for campo in OBJETOS:
        d[campo] = json.loads(d[campo] or "null")
    return d


def listar() -> list[dict]:
    with _conexion() as con:
        filas = con.execute("SELECT * FROM manuscritos ORDER BY id DESC").fetchall()
    return [_fila(f) for f in filas]


def obtener(mid: int) -> dict | None:
    with _conexion() as con:
        f = con.execute("SELECT * FROM manuscritos WHERE id=?", (mid,)).fetchone()
    return _fila(f) if f else None


def crear(**campos) -> int:
    campos.setdefault("creado", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    campos = _serializa(campos)
    nombres = ", ".join(campos)
    huecos = ", ".join("?" for _ in campos)
    with _cierre, _conexion() as con:
        cur = con.execute(
            f"INSERT INTO manuscritos ({nombres}) VALUES ({huecos})", tuple(campos.values())
        )
        return int(cur.lastrowid)


def actualizar(mid: int, **campos) -> None:
    if not campos:
        return
    campos = _serializa(campos)
    asignaciones = ", ".join(f"{c}=?" for c in campos)
    with _cierre, _conexion() as con:
        con.execute(
            f"UPDATE manuscritos SET {asignaciones} WHERE id=?", (*campos.values(), mid)
        )


def borrar(mid: int) -> None:
    with _cierre, _conexion() as con:
        con.execute("DELETE FROM manuscritos WHERE id=?", (mid,))


def vocabulario() -> dict[str, list[str]]:
    """Temas y tags ya usados, para que los análisis nuevos los reutilicen."""
    temas: set[str] = set()
    tags: set[str] = set()
    for m in listar():
        temas.update(m["temas"])
        tags.update(m["tags"])
    return {"temas": sorted(temas), "tags": sorted(tags)}


def _serializa(campos: dict) -> dict:
    return {
        c: json.dumps(v, ensure_ascii=False) if c in LISTAS + OBJETOS else v
        for c, v in campos.items()
    }
