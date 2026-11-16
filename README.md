# Gestión de manuscritos

Bandeja de manuscritos para Alighieria Publisher: lo que llega a la editorial, solicitado o no,
y todavía no es un libro. Se suben los archivos, se lee su texto y se prepara una ficha con
sumario, temas y tags por los que luego se filtra.

Es una primera versión para ver el flujo; todavía no está integrada en Publisher.

## Arrancar

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --port 8010
```

Y abrir http://localhost:8010. «Cargar ejemplos» llena la bandeja con diez fichas inventadas.

## Análisis con IA

Con una clave de Anthropic, cada manuscrito lo lee entero Claude y devuelve la ficha (título,
autor, género, público, ambientación, tono, frase resumen, sumario, temas, tags y comparables).
Para que los filtros sirvan, se le pasan los temas y tags que ya existen en la bandeja y
reutiliza esas formas antes de crear otras.

Crea un fichero `.env` en la raíz:

```
ANTHROPIC_API_KEY=...
```

Sin clave, las subidas se procesan con una extracción básica local (palabras más repetidas y
primeras frases). Sirve para probar el flujo, no para clasificar de verdad; la ficha lo avisa.

`MANUSCRITOS_MODELO` cambia el modelo (por defecto, `claude-opus-5-5`).

## Métricas del texto

Al subir un manuscrito se calculan, sin IA, medidas reproducibles del texto: legibilidad
(Szigriszt-Pazos con escala INFLESZ en español, Flesch en inglés), largo medio de frase,
proporción de diálogo, variedad léxica (MTLD) y variación del largo de frase. Si el texto
tiene cabeceras de capítulo, se desglosan por capítulo y se marcan los tramos lentos. La
ficha explica cómo se calcula cada una. Se puede subir un `.zip` con varios manuscritos.

## Lectura asistida

Con clave de Anthropic, el botón «Preparar informe de lectura» de la ficha hace que Claude
lea el manuscrito por fragmentos de unas 3.000 palabras y devuelva una rúbrica de ocho
criterios justificada con citas, fortalezas y debilidades, una propuesta (rechazar,
reconsiderar, pedir más material, llevar a comité), un borrador de informe y una versión para
el autor. Es la opinión de un modelo y no usa datos de ventas.

## Pruebas

```bash
.venv/bin/python -m pytest tests
.venv/bin/python -m scripts.consistencia manuscrito.docx   # con clave; gasta API
```

## Qué hay

- `app/main.py`: API y páginas estáticas.
- `app/texto.py`: lectura de .docx, .pdf, .epub, .txt y .md.
- `app/analisis.py`: ficha con Claude y extracción básica sin IA.
- `app/metricas.py`: métricas deterministas del texto.
- `app/lectura.py`: lectura por fragmentos, rúbrica e informe.
- `app/db.py`: SQLite en `data/` (junto a los originales subidos; fuera de git).
- `web/`: la interfaz (HTML, CSS y JavaScript sin compilar).
- `ejemplos/ejemplos.json`: las fichas de ejemplo.
