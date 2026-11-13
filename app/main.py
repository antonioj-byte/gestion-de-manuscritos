"""Servidor de la bandeja de manuscritos: API y páginas estáticas."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analisis, db, texto

RAIZ = Path(__file__).resolve().parent.parent
analisis.cargar_env(RAIZ / ".env")
db.iniciar()

app = FastAPI(title="Gestión de manuscritos")


class Cambios(BaseModel):
    titulo: str | None = None
    autor: str | None = None
    origen: str | None = None
    estado: str | None = None
    genero: str | None = None
    notas: str | None = None
    temas: list[str] | None = None
    tags: list[str] | None = None


def _o_404(mid: int) -> dict:
    m = db.obtener(mid)
    if not m:
        raise HTTPException(404, "Ese manuscrito no existe.")
    return m


def _ruta_original(m: dict) -> Path:
    return db.ORIGINALES / f"{m['id']}{Path(m['archivo']).suffix.lower()}"


def _procesar(mid: int) -> None:
    """Extrae el texto y lo analiza. Corre en segundo plano tras la subida."""
    m = db.obtener(mid)
    if not m:
        return
    try:
        ruta_texto = db.TEXTOS / f"{mid}.txt"
        if ruta_texto.exists():
            contenido = ruta_texto.read_text(encoding="utf-8")
        else:
            contenido = texto.extraer(_ruta_original(m))
            ruta_texto.write_text(contenido, encoding="utf-8")
        ficha, fuente = analisis.analizar(contenido, m["archivo"], db.vocabulario())
        db.actualizar(
            mid,
            **ficha,
            fuente=fuente,
            palabras=texto.contar_palabras(contenido),
            extracto=texto.extracto(contenido),
            proceso="listo",
            error="",
        )
    except Exception as e:  # el fallo se enseña en la ficha, no tumba el servidor
        db.actualizar(mid, proceso="error", error=str(e) or type(e).__name__)


@app.get("/api/config")
def config() -> dict:
    return {
        "ia": analisis.hay_ia(),
        "modelo": analisis.MODELO,
        "generos": analisis.GENEROS,
        "estados": db.ESTADOS,
        "origenes": db.ORIGENES,
        "extensiones": texto.EXTENSIONES,
    }


@app.get("/api/manuscritos")
def listar() -> list[dict]:
    return db.listar()


@app.post("/api/manuscritos")
async def subir(
    tareas: BackgroundTasks,
    archivos: list[UploadFile] = File(...),
    origen: str = Form("no_solicitado"),
) -> list[dict]:
    if origen not in db.ORIGENES:
        raise HTTPException(400, "Origen no válido.")
    creados = []
    for archivo in archivos:
        nombre = Path(archivo.filename or "manuscrito").name
        provisional = re.sub(r"[_\-]+", " ", Path(nombre).stem).strip().capitalize()
        mid = db.crear(titulo=provisional, archivo=nombre, origen=origen)
        m = db.obtener(mid)
        _ruta_original(m).write_bytes(await archivo.read())
        tareas.add_task(_procesar, mid)
        creados.append(m)
    return creados


@app.post("/api/ejemplos")
def cargar_ejemplos() -> dict:
    """Carga fichas inventadas para ver la bandeja con contenido."""
    ejemplos = json.loads((RAIZ / "ejemplos" / "ejemplos.json").read_text(encoding="utf-8"))
    ya = {m["titulo"] for m in db.listar() if m["fuente"] == "ejemplo"}
    nuevos = [e for e in ejemplos if e["titulo"] not in ya]
    for e in nuevos:
        db.crear(**e, fuente="ejemplo", proceso="listo")
    return {"cargados": len(nuevos)}


@app.patch("/api/manuscritos/{mid}")
def editar(mid: int, cambios: Cambios) -> dict:
    _o_404(mid)
    datos = cambios.model_dump(exclude_none=True)
    if datos.get("origen", db.ORIGENES[0]) not in db.ORIGENES:
        raise HTTPException(400, "Origen no válido.")
    if datos.get("estado", db.ESTADOS[0]) not in db.ESTADOS:
        raise HTTPException(400, "Estado no válido.")
    for campo in ("temas", "tags"):
        if campo in datos:
            datos[campo] = analisis.normalizar(datos[campo])
    db.actualizar(mid, **datos)
    return db.obtener(mid)


@app.post("/api/manuscritos/{mid}/analizar")
def reanalizar(mid: int, tareas: BackgroundTasks) -> dict:
    m = _o_404(mid)
    if not _ruta_original(m).exists():
        raise HTTPException(400, "Este manuscrito es un ejemplo y no tiene archivo que analizar.")
    db.actualizar(mid, proceso="analizando", error="")
    tareas.add_task(_procesar, mid)
    return db.obtener(mid)


@app.get("/api/manuscritos/{mid}/archivo")
def descargar(mid: int) -> FileResponse:
    m = _o_404(mid)
    ruta = _ruta_original(m)
    if not ruta.exists():
        raise HTTPException(404, "No hay archivo original.")
    return FileResponse(ruta, filename=m["archivo"])


@app.delete("/api/manuscritos/{mid}")
def eliminar(mid: int) -> dict:
    m = _o_404(mid)
    _ruta_original(m).unlink(missing_ok=True)
    (db.TEXTOS / f"{mid}.txt").unlink(missing_ok=True)
    db.borrar(mid)
    return {"ok": True}


app.mount("/", StaticFiles(directory=RAIZ / "web", html=True), name="web")
