"""La lectura asistida, con el modelo sustituido por respuestas fijas."""

from app import lectura
from tests.test_metricas import _manuscrito


def _falso(registro):
    def pedir(sistema, usuario, esquema, max_tokens=16000):
        registro.append((esquema.__name__, usuario))
        if esquema is lectura.NotaFragmento:
            objeto = lectura.NotaFragmento(
                resumen="Pasa algo.", trama="Avanza.", personajes="", voz_y_prosa="Seca.",
                problemas=["Repite una escena."], citas=["—¿Vienes ya?"], tension=9, tono=-7,
            )
        else:
            c = lambda n, aplica=True: lectura.Criterio(aplica=aplica, nota=n, justificacion="Porque sí.", cita="")
            objeto = lectura.Sintesis(
                premisa=c(6), voz=c(7), estructura=c(5), personajes=c(0, False), prosa=c(6),
                originalidad=c(4), ajuste_genero=c(14), potencial_comercial=c(5),
                fortalezas=["Diálogo ágil."], debilidades=["Capítulo central lento."],
                recomendacion="reconsiderar", motivo="Falta relieve.", informe="Informe.",
                para_el_autor="Gracias por el envío.",
            )
        return objeto, {"entrada": 1000, "salida": 100}

    return pedir


def test_lectura_completa():
    llamadas = []
    largo = "\n\n".join([_manuscrito()] * 6)  # varios fragmentos
    r = lectura.leer(largo, {"titulo": "Prueba", "genero": "Novela", "sumario": "Un sumario."}, pedir=_falso(llamadas))

    notas = [c for c in llamadas if c[0] == "NotaFragmento"]
    assert len(notas) == r["fragmentos"] > 1
    assert llamadas[-1][0] == "Sintesis" and "Repite una escena." in llamadas[-1][1]

    # Los valores fuera de escala que devuelva el modelo se acotan.
    assert all(a["tension"] == 5 and a["tono"] == -2 for a in r["arco"])
    assert r["rubrica"]["ajuste_genero"]["nota"] == 10
    # Un criterio que no aplica no cuenta para la media: (6+7+5+6+4+10+5)/7.
    assert r["rubrica"]["personajes"]["nota"] is None
    assert r["media"] == 6.1

    assert r["recomendacion"] == "reconsiderar"
    assert r["tokens_entrada"] == 1000 * (r["fragmentos"] + 1)
    assert r["coste_usd"] is not None
    assert len(r["problemas"]) == r["fragmentos"]
