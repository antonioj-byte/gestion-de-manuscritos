"""Prueba de consistencia de la lectura asistida.

Lee el mismo manuscrito varias veces y enseña cuánto cambia cada nota de la rúbrica de una
pasada a otra. El objetivo es que ninguna se mueva más de un punto; si alguna lo hace, hay
que afinar los anclajes de la rúbrica en app/lectura.py. Gasta API: una lectura por pasada.

    .venv/bin/python -m scripts.consistencia manuscrito.docx [pasadas]
"""

import sys
from pathlib import Path

from app import analisis, lectura, texto

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    analisis.cargar_env(RAIZ / ".env")
    if not analisis.hay_ia():
        print("Falta la clave de Anthropic (ANTHROPIC_API_KEY en .env).")
        return 2
    ruta = Path(sys.argv[1])
    pasadas = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    contenido = texto.extraer(ruta)
    ficha, _ = analisis.analizar(contenido, ruta.name, {"temas": [], "tags": []})

    lecturas = []
    for n in range(pasadas):
        r = lectura.leer(contenido, ficha)
        lecturas.append(r)
        print(f"Pasada {n + 1}: media {r['media']}, {r['recomendacion']}, {r['segundos']} s, {r['coste_usd']} $")

    print(f"\n{'Criterio':<22}{'Notas':<16}Diferencia")
    peor = 0
    for clave, nombre in lectura.CRITERIOS.items():
        notas = [r["rubrica"][clave]["nota"] for r in lecturas]
        dadas = [n for n in notas if n is not None]
        diferencia = max(dadas) - min(dadas) if dadas else 0
        peor = max(peor, diferencia)
        print(f"{nombre:<22}{str(notas):<16}{diferencia}{'  <- más de 1 punto' if diferencia > 1 else ''}")
    print(f"\nRecomendaciones: {[r['recomendacion'] for r in lecturas]}")
    print("CONSISTENTE" if peor <= 1 else "NO CONSISTENTE: afinar los anclajes de la rúbrica")
    return 0 if peor <= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
