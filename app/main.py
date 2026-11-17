"""Servidor de la bandeja de manuscritos: API y páginas estáticas."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analisis, db, lectura, metricas, texto

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
    subgenero: str | None = None
    publico: str | None = None
    ambientacion: str | None = None
    idioma: str | None = None
    logline: str | None = None
    sumario: str | None = None
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
            metricas=metricas.calcular(contenido, ficha["idioma"]),
            palabras=texto.contar_palabras(contenido),
            extracto=texto.extracto(contenido),
            proceso="listo",
            error="",
        )
    except Exception as e:  # el fallo se enseña en la ficha, no tumba el servidor
        db.actualizar(mid, proceso="error", error=str(e) or type(e).__name__)


def _leer(mid: int) -> None:
    """Lectura asistida (notas por fragmento, rúbrica, informe). Corre en segundo plano."""
    m = db.obtener(mid)
    if not m:
        return
    try:
        contenido = (db.TEXTOS / f"{mid}.txt").read_text(encoding="utf-8")
        db.actualizar(mid, lectura=lectura.leer(contenido, m), lectura_proceso="listo", lectura_error="")
    except Exception as e:
        db.actualizar(mid, lectura_proceso="error", lectura_error=str(e) or type(e).__name__)


def _desempaquetar(nombre: str, datos: bytes) -> list[tuple[str, bytes]]:
    """Un archivo subido, o los manuscritos que hay dentro si es un .zip."""
    if not nombre.lower().endswith(".zip"):
        return [(nombre, datos)]
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            dentro = [
                i for i in z.infolist()
                if not i.is_dir()
                and not Path(i.filename).name.startswith((".", "~"))
                and "__MACOSX" not in i.filename
                and Path(i.filename).suffix.lower() in texto.EXTENSIONES
            ]
            return [(Path(i.filename).name, z.read(i)) for i in dentro[:200]]
    except zipfile.BadZipFile:
        raise HTTPException(400, f"«{nombre}» no es un zip válido.")


@app.get("/api/config")
def config() -> dict:
    return {
        "ia": analisis.hay_ia(),
        "modelo": analisis.MODELO,
        "generos": analisis.GENEROS,
        "estados": db.ESTADOS,
        "origenes": db.ORIGENES,
        "extensiones": texto.EXTENSIONES,
        "criterios": lectura.CRITERIOS,
        "recomendaciones": lectura.RECOMENDACIONES,
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
        subido = Path(archivo.filename or "manuscrito").name
        for nombre, datos in _desempaquetar(subido, await archivo.read()):
            provisional = re.sub(r"[_\-]+", " ", Path(nombre).stem).strip().capitalize()
            mid = db.crear(titulo=provisional, archivo=nombre, origen=origen)
            m = db.obtener(mid)
            _ruta_original(m).write_bytes(datos)
            tareas.add_task(_procesar, mid)
            creados.append(m)
    if not creados:
        raise HTTPException(400, "El zip no contiene manuscritos en un formato admitido.")
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
    # La legibilidad depende del idioma: si se corrige, se recalculan las métricas.
    ruta_texto = db.TEXTOS / f"{mid}.txt"
    if "idioma" in datos and ruta_texto.exists():
        datos["metricas"] = metricas.calcular(ruta_texto.read_text(encoding="utf-8"), datos["idioma"])
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


@app.post("/api/manuscritos/{mid}/lectura")
def pedir_lectura(mid: int, tareas: BackgroundTasks) -> dict:
    m = _o_404(mid)
    if not analisis.hay_ia():
        raise HTTPException(400, "La lectura asistida necesita la clave de Anthropic.")
    if not (db.TEXTOS / f"{mid}.txt").exists():
        raise HTTPException(400, "Este manuscrito no tiene texto que leer.")
    if m["lectura_proceso"] == "leyendo":
        return m
    db.actualizar(mid, lectura_proceso="leyendo", lectura_error="")
    tareas.add_task(_leer, mid)
    return db.obtener(mid)


@app.get("/api/manuscritos/{mid}/archivo")
def descargar(mid: int, ver: bool = False) -> FileResponse:
    """El archivo original; con ?ver=1 se abre en el navegador en vez de descargarse."""
    m = _o_404(mid)
    ruta = _ruta_original(m)
    if not ruta.exists():
        raise HTTPException(404, "No hay archivo original.")
    return FileResponse(
        ruta, filename=m["archivo"], content_disposition_type="inline" if ver else "attachment"
    )


@app.get("/api/manuscritos/{mid}/texto")
def ver_texto(mid: int) -> dict:
    """El texto extraído del manuscrito, para enseñarlo junto a la ficha."""
    _o_404(mid)
    ruta = db.TEXTOS / f"{mid}.txt"
    return {"texto": ruta.read_text(encoding="utf-8") if ruta.exists() else ""}


@app.delete("/api/manuscritos/{mid}")
def eliminar(mid: int) -> dict:
    m = _o_404(mid)
    _ruta_original(m).unlink(missing_ok=True)
    (db.TEXTOS / f"{mid}.txt").unlink(missing_ok=True)
    db.borrar(mid)
    return {"ok": True}


app.mount("/", StaticFiles(directory=RAIZ / "web", html=True), name="web")
