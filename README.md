# Piano Autoplayer — Tirji

Simula pulsaciones de teclado automáticamente (piano de letras estilo
Roblox/virtualpiano) desde una ventana con interfaz propia. Incluye
además el **Editor de teclado**: un lenguaje aparte para automatizar
*cualquier* combinación de teclas (mantener, tocar, combos, esperas),
no solo partituras de piano.

## Para tus compañeros: la forma más fácil (un solo archivo)

Les mandas **solo** `descargar_e_iniciar.bat` (por WhatsApp, Discord,
donde sea — no hace falta que abran GitHub ni sepan qué es un repo).
Al abrirlo:
1. Descarga el proyecto completo desde este repositorio.
2. Instala las dependencias.
3. Abre el programa.

Si lo vuelven a abrir después, detecta que ya está descargado y solo
actualiza (`git pull`, o vuelve a descargar si no usaron `git`) antes
de abrir — así siempre tienen la última versión.

**Antes de repartirlo**, abre `descargar_e_iniciar.bat` con el Bloc de
notas y cambia esta línea por el link real de tu repositorio (debe ser
público):
```
set REPO_URL=https://github.com/TUUSUARIO/piano-autoplayer
```

## Para tus compañeros: alternativa manual (clonar/descargar tú el ZIP)

1. Instala [Python 3](https://www.python.org/downloads/) (marca la
   casilla "Add python.exe to PATH" durante la instalación).
2. Descarga este repositorio (botón verde "Code" → "Download ZIP" en
   GitHub, o `git clone`) y **extrae el ZIP** a una carpeta normal
   (no lo abras directo desde dentro del ZIP).
3. Doble clic en `iniciar.bat`. La primera vez instala las
   dependencias solo (tarda un poco); las siguientes veces abre
   directo.

Con eso ya funciona: no hace falta compilar ningún `.exe`.

## Instalación manual (si no quieres usar `iniciar.bat`)

```
pip install -r requirements.txt
python piano_autoplayer.py
```

## Compilar un .exe para repartir sin que instalen Python

Eso es lo que hace `build.bat`: instala las dependencias y genera
`dist/PianoAutoplayer/` con el programa listo (incluye Python y todo
lo necesario, tus compañeros no instalan nada). Comprime esa carpeta
completa y repártela.

```
build.bat
```

## Estructura

```
piano_autoplayer.py   -> el programa (ventana, reproducción, Tienda)
web/                  -> la interfaz (HTML/CSS/JS) que se ve dentro de la ventana
requirements.txt      -> dependencias de Python
build.bat             -> genera el .exe (dist/PianoAutoplayer/)
iniciar.bat           -> instala dependencias y abre el programa directo (sin compilar)
```

El servidor de la Tienda (`piano_tienda_server.py`) vive en un repositorio
aparte: tus compañeros no lo necesitan, todos hablan con el mismo
servidor ya publicado en internet (ver `TIENDA_API_URL` dentro de
`piano_autoplayer.py`).

## Notas

- `partituras/` y `controladores/` se crean solas junto al programa;
  ahí se guarda lo tuyo (no se sube a este repositorio).
- Si Windows marca el `.exe` como "No responde" al abrirlo, casi
  siempre es porque se abrió directo desde dentro del `.zip` sin
  extraerlo antes — extráelo a una carpeta normal primero.
