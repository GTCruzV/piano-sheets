"""
Piano Autoplayer - Tirji
--------------------------------------------------
Simula pulsaciones de teclado automáticamente, como si tocaras un
piano/teclado de letras (ej. en Roblox). Interfaz en HTML/CSS/JS
(pywebview) con animaciones; el envío de teclas sigue siendo 100%
Python/nativo (funciona aunque la ventana del juego tenga el foco).

FORMATO DE PARTITURA (compatible con virtualpiano.net / virtualpianosheet.com):
- No hace falta poner espacios: cada carácter suelto es una nota,
  y [abc] es un acorde (varias teclas juntas).
- MAYÚSCULA = tecla negra -> se envía shift + esa tecla.
- "-" o "|" = silencio.
- {ms} = a partir de aquí cambia la velocidad.

CARPETA "partituras":
- Se crea junto al programa. Cualquier .txt ahí aparece en la lista.
- Además, el programa se sincroniza solo con un repositorio de GitHub
  (ver GITHUB_OWNER / GITHUB_REPO abajo): cada cierto tiempo revisa
  la carpeta "partituras" de ese repo y descarga lo nuevo o lo que
  haya cambiado, para que todos los que usan el programa reciban las
  partituras que vayas subiendo.

TIENDA (cuentas / partituras compartidas):
- Es pública y única para todos: no hace falta pedirle ninguna IP a
  nadie. TODAS las copias del programa (la tuya y las de tus
  compañeros) hablan siempre con el mismo servidor, en la URL fija
  TIENDA_API_URL (abajo).
- Ese servidor es "piano_tienda_server.py" (Flask + SQLite), corriendo
  de forma permanente en tu PC y publicado a internet con un
  subdominio de hmrp.lat (mismo Cloudflare Tunnel que ya usas para
  HSRP), por ejemplo "piano-api.hmrp.lat" -> tu PC puerto 5000. Tu PC
  es la base de datos: mientras ese proceso esté corriendo, cualquiera
  con el programa ve y descarga lo que se suba a la Tienda.
"""

import json
import os
import re
import shutil
import sys
import uuid

# Con --noconsole, PyInstaller deja sys.stdout/stderr en None. Cualquier
# print() (incluidos los avisos internos de pywebview, ej. "[pywebview]
# Error while processing...") truena en silencio en ese caso y cuelga la
# ventana entera ("No responde"). Se redirige a la nada ANTES de que
# nada más se importe o imprima algo.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
import threading
import time

import requests
import webview

try:
    import keyboard
except ImportError:
    raise SystemExit("Falta la librería 'keyboard'. Instálala con: pip install keyboard")

# ================== CONFIGURA TU REPO DE GITHUB AQUÍ ==================
# Repo público donde vas a ir subiendo los archivos .txt de partituras,
# dentro de una carpeta llamada "partituras". Ejemplo: si tu repo es
# https://github.com/Tirji/piano-sheets, entonces:
GITHUB_OWNER = "GTCruzV"
GITHUB_REPO = "piano-sheets"
GITHUB_BRANCH = "main"
GITHUB_PATH = "partituras"
SYNC_INTERVAL_SECONDS = 90

# ================== TIENDA (servidor público, único para todos) ==================
# Ya no se pregunta ninguna IP: todos los programas hablan siempre con
# esta misma URL. Debe apuntar a donde esté corriendo
# "piano_tienda_server.py" (tu PC, publicada con Cloudflare Tunnel).
TIENDA_API_URL = "https://piano-api.hmrp.lat/api"
SESSION_PATH_NAME = ".tienda_session.json"
# ========================================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = BASE_DIR

SHEETS_DIR = os.path.join(BASE_DIR, "partituras")
CONTROLLERS_DIR = os.path.join(BASE_DIR, "controladores")
MANIFEST_PATH = os.path.join(SHEETS_DIR, ".sync_manifest.json")
WEB_DIR = os.path.join(RES_DIR, "web")
SESSION_PATH = os.path.join(BASE_DIR, SESSION_PATH_NAME)
DEVICE_ID_PATH = os.path.join(BASE_DIR, ".device_id")


def _load_or_create_device_id():
    """Id fijo por instalación (no por persona): se genera una vez y se
    guarda junto al programa, para que el admin pueda bloquear un
    dispositivo aunque la persona se cree cuentas nuevas."""
    try:
        if os.path.exists(DEVICE_ID_PATH):
            with open(DEVICE_ID_PATH, "r", encoding="utf-8") as f:
                existing = f.read().strip()
            if existing:
                return existing
    except Exception:
        pass
    new_id = uuid.uuid4().hex
    try:
        with open(DEVICE_ID_PATH, "w", encoding="utf-8") as f:
            f.write(new_id)
    except Exception:
        pass
    return new_id


DEVICE_ID = _load_or_create_device_id()


def _tokenize(text):
    """Convierte la partitura completa en una lista de eventos, sin
    depender de espacios. Cada evento es (valor, inicio, fin)."""
    events = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "[":
            start = i
            j = text.find("]", i + 1)
            if j == -1:
                events.append((text[i + 1:], start, n))
                i = n
            else:
                events.append((text[i + 1:j], start, j + 1))
                i = j + 1
        elif ch == "{":
            start = i
            j = text.find("}", i + 1)
            if j == -1:
                i = n
            else:
                content = text[i + 1:j]
                if content.isdigit():
                    events.append((("SPEED", int(content)), start, j + 1))
                i = j + 1
        elif ch in ("-", "|"):
            events.append((None, i, i + 1))
            i += 1
        else:
            events.append((ch, i, i + 1))
            i += 1
    return events


class ControllerError(Exception):
    """Error de sintaxis en un script del Editor de teclado (controlador)."""


# Nombres en español/alias -> nombre que entiende la librería "keyboard".
# Cualquier palabra que no esté aquí se manda tal cual a keyboard.press,
# así que cosas como "f1", "f2", "home", "delete", etc. ya funcionan
# solas sin necesidad de agregarlas a esta lista.
_KEY_ALIASES = {
    "espacio": "space",
    "space": "space",
    "enter": "enter",
    "intro": "enter",
    "tab": "tab",
    "esc": "esc",
    "escape": "esc",
    "arriba": "up",
    "abajo": "down",
    "izquierda": "left",
    "derecha": "right",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "shift": "shift",
    "mayus": "shift",
    "mayúsculas": "shift",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "supr": "delete",
}


def _normalize_key(raw):
    k = (raw or "").strip().lower()
    if not k:
        return None
    return _KEY_ALIASES.get(k, k)


def _read_bracket(text, i):
    """text[i] debe ser '['. Devuelve (contenido, índice después del ']')."""
    j = text.find("]", i + 1)
    if j == -1:
        raise ControllerError("Falta cerrar un '['.")
    return text[i + 1:j], j + 1


def _read_bare_word(text, i):
    """Lee una palabra suelta (sin corchetes) desde i: letras/números/
    guiones, hasta un '[', un espacio, o un salto de línea."""
    n = len(text)
    j = i
    while j < n and text[j] not in "[ \t\r\n":
        j += 1
    return text[i:j], j


def _split_keys(raw):
    raw = (raw or "").strip()
    if not raw:
        raise ControllerError("Hay una combinación de teclas vacía '[]'.")
    if "+" in raw:
        parts = [p for p in (p.strip() for p in raw.split("+")) if p]
    else:
        # sin "+": cada carácter suelto es su propia tecla, ej. "wasd" -> w,a,s,d
        parts = list(raw)
    keys = []
    for p in parts:
        k = _normalize_key(p)
        if not k:
            raise ControllerError(f"Hay una tecla vacía dentro de '[{raw}]'.")
        keys.append(k)
    return keys


def _tokenize_controller(text):
    """Convierte el script del Editor de teclado en una lista de pasos:
      {"wait": True, "duration": segundos}
      {"keys": [...], "duration": segundos, "mode": "hold"|"tap", "tap_ms": n}

    FORMATO (ver tutorial dentro del programa):
      w[12.2]            -> mantiene "w" presionada 12.2 segundos
      w[12.3][T]         -> en vez de mantenerla, la toca repetidamente
      w[1][T150]         -> toques cada 150ms durante 1 segundo
      [wasd][12]         -> mantiene w+a+s+d juntas 12 segundos
      [shift+w][5]       -> mantiene Shift+W 5 segundos
      espera[3]          -> no toca nada, solo espera 3 segundos
      w[1]x5             -> repite "mantener w 1s" 5 veces seguidas
      # comentario       -> una línea que empieza con # se ignora

    Lanza ControllerError con un mensaje claro si el texto no es válido.
    """
    steps = []
    i, n = 0, len(text or "")
    if not (text or "").strip():
        raise ControllerError("El controlador está vacío.")

    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == "#":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue

        word, after = _read_bare_word(text, i)

        if word.lower() == "espera":
            if after >= n or text[after] != "[":
                raise ControllerError(
                    "Después de 'espera' falta poner [segundos], ej. espera[3]."
                )
            dur_raw, i2 = _read_bracket(text, after)
            try:
                dur = float(dur_raw)
            except ValueError:
                raise ControllerError(f"'{dur_raw}' no es un número de segundos válido.")
            if dur <= 0:
                raise ControllerError("El tiempo de 'espera' debe ser mayor a 0.")
            steps.append({"wait": True, "duration": dur})
            i = i2
            continue

        if ch == "[":
            keys_raw, i = _read_bracket(text, i)
            keys = _split_keys(keys_raw)
        elif word:
            keys = _split_keys(word)
            i = after
        else:
            raise ControllerError(f"No entendí el símbolo '{ch}'.")

        if i >= n or text[i] != "[":
            raise ControllerError(
                "Falta poner la duración entre corchetes después de la(s) tecla(s), ej. w[3]."
            )
        dur_raw, i = _read_bracket(text, i)
        try:
            duration = float(dur_raw)
        except ValueError:
            raise ControllerError(f"'{dur_raw}' no es un número de segundos válido.")
        if duration <= 0:
            raise ControllerError("La duración debe ser mayor a 0.")

        mode = "hold"
        tap_ms = 120
        if i < n and text[i] == "[":
            mode_raw, i2 = _read_bracket(text, i)
            mr = mode_raw.strip().upper()
            if mr == "T":
                mode = "tap"
            elif mr.startswith("T") and mr[1:].isdigit():
                mode = "tap"
                tap_ms = max(20, int(mr[1:]))
            else:
                raise ControllerError(
                    f"'[{mode_raw}]' no es un modo válido. Usa [T] o [T150] para toques."
                )
            i = i2

        repeat = 1
        if i < n and text[i] in "xX":
            j = i + 1
            k = j
            while k < n and text[k].isdigit():
                k += 1
            if k > j:
                repeat = int(text[j:k])
                if repeat <= 0:
                    raise ControllerError("El número de repeticiones (x...) debe ser mayor a 0.")
                i = k

        for _ in range(repeat):
            steps.append({"keys": keys, "duration": duration, "mode": mode, "tap_ms": tap_ms})

    if not steps:
        raise ControllerError("No encontré ninguna instrucción válida.")
    return steps


def validate_controller(text):
    """Igual que validate_sheet pero para el lenguaje del Editor de
    teclado. Devuelve (ok, lista_de_errores)."""
    try:
        _tokenize_controller(text)
        return True, []
    except ControllerError as e:
        return False, [str(e)]


class SheetSync:
    """Descarga a la carpeta 'partituras' los archivos .txt de la
    carpeta GITHUB_PATH del repo configurado, y avisa a la UI."""

    def __init__(self, notify):
        self.notify = notify  # callback(state, text) / toast(msg) / refresh()

    def _api_url(self):
        return (
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
            f"/contents/{GITHUB_PATH}?ref={GITHUB_BRANCH}"
        )

    def _load_manifest(self):
        if os.path.exists(MANIFEST_PATH):
            try:
                with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_manifest(self, manifest):
        try:
            with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                json.dump(manifest, f)
        except Exception:
            pass

    def sync_once(self):
        if GITHUB_OWNER == "TU_USUARIO_DE_GITHUB":
            self.notify.status("err", "Sincronización no configurada")
            return
        self.notify.status("busy", "Sincronizando…")
        try:
            resp = requests.get(self._api_url(), timeout=12)
            resp.raise_for_status()
            items = resp.json()
        except Exception:
            self.notify.status("err", "Sin conexión al repo")
            return

        manifest = self._load_manifest()
        new_manifest = {}
        added = []
        updated = []

        remote_txt = [it for it in items if it.get("type") == "file" and it["name"].lower().endswith(".txt")]

        for item in remote_txt:
            name = item["name"]
            sha = item.get("sha", "")
            new_manifest[name] = sha
            local_path = os.path.join(SHEETS_DIR, name)
            already_synced = manifest.get(name)
            needs_download = (not os.path.exists(local_path)) or (already_synced != sha)
            if needs_download:
                try:
                    file_resp = requests.get(item["download_url"], timeout=12)
                    file_resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(file_resp.content)
                    if name not in manifest:
                        added.append(name)
                    else:
                        updated.append(name)
                except Exception:
                    pass

        # borra solo archivos que el propio sync había traído antes y
        # ya no están en el repo (no toca archivos propios del usuario)
        remote_names = {it["name"] for it in remote_txt}
        for old_name in list(manifest.keys()):
            if old_name not in remote_names:
                old_path = os.path.join(SHEETS_DIR, old_name)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass

        self._save_manifest(new_manifest)

        if added or updated:
            self.notify.refresh()
            if added:
                self.notify.toast(f"Partitura(s) nueva(s): {', '.join(added)}")
            if updated:
                self.notify.toast(f"Actualizada(s): {', '.join(updated)}")
        self.notify.status("ok", "Sincronizado")

    def loop(self):
        while True:
            self.sync_once()
            time.sleep(SYNC_INTERVAL_SECONDS)


class Notifier:
    """Envuelve las llamadas evaluate_js hacia la ventana pywebview."""

    def __init__(self, get_window):
        self.get_window = get_window

    def _js(self, code):
        win = self.get_window()
        if win is not None:
            try:
                win.evaluate_js(code)
            except Exception:
                pass

    def status(self, state, text):
        self._js(f"setSyncState({json.dumps(state)}, {json.dumps(text)})")

    def toast(self, msg):
        self._js(f"toast({json.dumps(msg)})")

    def refresh(self):
        win = self.get_window()
        if win is None:
            return
        files = sorted(f for f in os.listdir(SHEETS_DIR) if f.lower().endswith(".txt"))
        self._js(f"refreshSheets({json.dumps(files)})")

    def set_status(self, text):
        self._js(f"setStatus({json.dumps(text)})")

    def set_progress(self, pct):
        self._js(f"setProgress({pct})")

    def set_playing(self, playing):
        self._js(f"setPlaying({json.dumps(bool(playing))})")

    def set_now_playing(self, label):
        self._js(f"setNowPlaying({json.dumps(label)})")

    # -------- Editor de teclado (controlador) --------
    def refresh_controllers(self):
        win = self.get_window()
        if win is None:
            return
        files = sorted(f for f in os.listdir(CONTROLLERS_DIR) if f.lower().endswith(".txt"))
        self._js(f"refreshControllers({json.dumps(files)})")

    def set_ctrl_status(self, text):
        self._js(f"setCtrlStatus({json.dumps(text)})")

    def set_ctrl_progress(self, pct):
        self._js(f"setCtrlProgress({pct})")

    def set_ctrl_playing(self, playing):
        self._js(f"setCtrlPlaying({json.dumps(bool(playing))})")

    def set_ctrl_now(self, label):
        self._js(f"setCtrlNow({json.dumps(label)})")


class Api:
    def __init__(self):
        self.window = None
        self.notifier = Notifier(lambda: self.window)
        self.playing = False
        self.stop_flag = threading.Event()
        self.play_thread = None
        self.ctrl_playing = False
        self.ctrl_stop_flag = threading.Event()
        self.ctrl_thread = None
        self.session = self._load_session()

    # -------- tienda: sesión --------
    @staticmethod
    def _load_session():
        if os.path.exists(SESSION_PATH):
            try:
                with open(SESSION_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_session(self, data):
        self.session = data
        try:
            with open(SESSION_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            # si no se pudo guardar en disco, la sesión funcionará
            # mientras la ventana siga abierta pero no va a "recordarse"
            # la próxima vez que se abra el programa. La causa casi
            # siempre es que la carpeta del programa no tiene permiso
            # de escritura (ej. está dentro de Program Files, o se
            # está corriendo directo desde dentro de un .zip sin
            # extraer primero). Avisamos en vez de fallar en silencio.
            self.notifier.toast(
                "⚠️ No se pudo guardar tu sesión en esta carpeta. "
                "Extrae el programa a una carpeta normal (no dentro de "
                "un .zip ni de Program Files) para que recuerde tu "
                "inicio de sesión."
            )

    def _clear_session(self):
        self.session = None
        try:
            if os.path.exists(SESSION_PATH):
                os.remove(SESSION_PATH)
        except Exception:
            pass

    def _device_headers(self):
        return {"X-Device-Id": DEVICE_ID}

    def _auth_headers(self):
        headers = self._device_headers()
        if self.session and self.session.get("token"):
            headers["Authorization"] = f"Bearer {self.session['token']}"
        return headers

    # -------- tienda: llamadas de red sin bloquear la ventana --------
    # pywebview espera a que cada método de la API termine para
    # resolver la promesa en JS. Si ese método hace requests.* y el
    # servidor/túnel está lento o caído, la llamada se queda esperando
    # y Windows marca la ventana como "No responde" (aunque casi
    # siempre "sí responde" un rato después, cuando el timeout expira).
    # Por eso todos los métodos que hablan por internet con la tienda
    # corren su trabajo real en un hilo aparte y devuelven el control
    # de inmediato; el resultado real se le entrega a la interfaz
    # después con evaluate_js (ver __resolveAsyncApi en app.js).
    def _async(self, req_id, func, *args, **kwargs):
        def worker():
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                result = {"ok": False, "error": f"Error inesperado: {e}"}
            self._deliver_async(req_id, result)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _deliver_async(self, req_id, result):
        win = self.window
        if win is None:
            return
        try:
            win.evaluate_js(f"__resolveAsyncApi({json.dumps(req_id)}, {json.dumps(result)})")
        except Exception:
            pass

    # -------- tienda: cuenta pública, sin servidor local ni IP --------
    def tienda_session(self):
        """La UI llama esto al arrancar para saber si ya hay sesión
        guardada localmente. Esto es solo una respuesta rápida para no
        dejar la pantalla en blanco; la sesión real se revalida aparte
        con tienda_restore_session() (que sí pregunta al servidor)."""
        if not self.session:
            return None
        return {
            "username": self.session.get("username"),
            "isAdmin": bool(self.session.get("isAdmin")),
            "photo": self.session.get("photo"),
        }

    def tienda_restore_session(self, req_id):
        return self._async(req_id, self._tienda_restore_session_impl)

    def _tienda_restore_session_impl(self):
        """Revalida contra el servidor la sesión guardada en disco (si
        hay una). Así, si el token ya no sirve, se limpia sola en vez
        de dejar a la app "logueada" con datos viejos; y si sí sirve,
        refresca la foto/rol de admin por si cambiaron. Se debe llamar
        al arrancar la app, después de tienda_session()."""
        if not self.session or not self.session.get("token"):
            return None
        try:
            resp = requests.get(
                f"{TIENDA_API_URL}/me", headers=self._auth_headers(), timeout=15
            )
            if resp.status_code == 401 or resp.status_code == 403:
                self._clear_session()
                return None
            resp.raise_for_status()
            data = resp.json()
            data["token"] = self.session.get("token")
            self._save_session(data)
            return self.tienda_session()
        except Exception:
            # sin internet momentáneamente: no borres la sesión local,
            # deja que la persona siga usando lo que ya tenía guardado
            return self.tienda_session()

    def tienda_register(self, req_id, username, password):
        return self._async(req_id, self._tienda_register_impl, username, password)

    def _tienda_register_impl(self, username, password):
        """Registra un usuario nuevo. La foto de perfil se elige con un
        diálogo de Windows aparte (tienda_pick_photo)."""
        username = (username or "").strip()
        password = (password or "").strip()
        try:
            files = {}
            photo_path = getattr(self, "_pending_photo", None)
            fh = None
            if photo_path and os.path.exists(photo_path):
                fh = open(photo_path, "rb")
                files["photo"] = (os.path.basename(photo_path), fh)
            resp = requests.post(
                f"{TIENDA_API_URL}/register",
                data={"username": username, "password": password},
                files=files or None,
                headers=self._device_headers(),
                timeout=15,
            )
            if fh:
                fh.close()
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo registrar.")}
            self._save_session(data)
            return {"ok": True, "session": self.tienda_session()}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_pick_photo(self):
        """Abre el explorador para elegir la foto de perfil antes de
        registrarse. Devuelve la ruta elegida (o None)."""
        path = self._pick_image_file()
        if not path:
            return None
        self._pending_photo = path
        return os.path.basename(path)

    def tienda_pick_post_photo(self):
        """Abre el explorador para elegir la foto de referencia
        (cuadrada) de la publicación que se va a subir a la tienda."""
        path = self._pick_image_file()
        if not path:
            return None
        self._pending_post_photo = path
        return os.path.basename(path)

    def _pick_image_file(self):
        if self.window is None:
            return None
        try:
            paths = self.window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("Imágenes (*.png;*.jpg;*.jpeg;*.gif;*.webp)",),
            )
        except Exception:
            return None
        if not paths:
            return None
        return paths[0]

    def tienda_pick_sheet_file(self):
        """Abre el explorador para elegir un .txt YA GUARDADO en la
        computadora (su propio proyecto) para usarlo como partitura a
        publicar en la tienda. Devuelve {name, content} o None."""
        if self.window is None:
            return None
        try:
            paths = self.window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("Archivos de texto (*.txt)", "Todos los archivos (*.*)"),
            )
        except Exception:
            return None
        if not paths:
            return None
        try:
            with open(paths[0], "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return None
        base = os.path.splitext(os.path.basename(paths[0]))[0]
        return {"name": base, "content": content}

    def tienda_login(self, req_id, username, password):
        return self._async(req_id, self._tienda_login_impl, username, password)

    def _tienda_login_impl(self, username, password):
        username = (username or "").strip()
        password = (password or "").strip()
        if not username or not password:
            return {"ok": False, "error": "Pon usuario y contraseña para entrar."}
        try:
            resp = requests.post(
                f"{TIENDA_API_URL}/login",
                json={"username": username, "password": password},
                headers=self._device_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo iniciar sesión.")}
            self._save_session(data)
            return {"ok": True, "session": self.tienda_session()}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_user_profile(self, req_id, username):
        return self._async(req_id, self._tienda_user_profile_impl, username)

    def _tienda_user_profile_impl(self, username):
        """Perfil público de un usuario (sus publicaciones aprobadas),
        para cuando se pica su foto en la tienda."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "Usuario no válido."}
        try:
            resp = requests.get(f"{TIENDA_API_URL}/users/{username}/sheets", timeout=15)
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo cargar el perfil.")}
            return {"ok": True, "profile": data.get("profile"), "items": data.get("items", [])}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_logout(self, req_id):
        return self._async(req_id, self._tienda_logout_impl)

    def _tienda_logout_impl(self):
        # avisa al servidor para que ese token quede invalidado del
        # lado del servidor también (best-effort: si falla la
        # conexión, igual se cierra la sesión localmente)
        try:
            requests.post(f"{TIENDA_API_URL}/logout", headers=self._auth_headers(), timeout=8)
        except Exception:
            pass
        self._clear_session()
        return {"ok": True}

    def tienda_list(self, req_id, kind="sheet"):
        return self._async(req_id, self._tienda_list_impl, kind)

    def _tienda_list_impl(self, kind="sheet"):
        try:
            resp = requests.get(f"{TIENDA_API_URL}/sheets", params={"kind": kind}, timeout=15)
            resp.raise_for_status()
            return {"ok": True, "items": resp.json()}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo cargar la tienda: {e}", "items": []}

    def tienda_mine(self, req_id, kind="sheet"):
        return self._async(req_id, self._tienda_mine_impl, kind)

    def _tienda_mine_impl(self, kind="sheet"):
        """Devuelve el estado de la publicación propia (pendiente,
        aprobada o rechazada), o None si nunca ha publicado nada."""
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero.", "item": None}
        try:
            resp = requests.get(
                f"{TIENDA_API_URL}/sheets/mine",
                params={"kind": kind},
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo consultar."), "item": None}
            return {"ok": True, "item": data.get("item")}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}", "item": None}

    def tienda_pending(self, req_id, kind="sheet"):
        return self._async(req_id, self._tienda_pending_impl, kind)

    def _tienda_pending_impl(self, kind="sheet"):
        """Solo para el admin: lista las publicaciones esperando
        aprobación, con el contenido completo para poder revisarlas."""
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero.", "items": []}
        try:
            resp = requests.get(
                f"{TIENDA_API_URL}/sheets/pending",
                params={"kind": kind},
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                err = data.get("error", "No se pudo consultar.") if isinstance(data, dict) else "No se pudo consultar."
                return {"ok": False, "error": err, "items": []}
            return {"ok": True, "items": data}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}", "items": []}

    def tienda_approve(self, req_id, sheet_id):
        return self._async(req_id, self._tienda_approve_impl, sheet_id)

    def _tienda_approve_impl(self, sheet_id):
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero."}
        try:
            resp = requests.post(
                f"{TIENDA_API_URL}/sheets/{sheet_id}/approve",
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo aprobar.")}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_reject(self, req_id, sheet_id, reason=""):
        return self._async(req_id, self._tienda_reject_impl, sheet_id, reason)

    def _tienda_reject_impl(self, sheet_id, reason=""):
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero."}
        try:
            resp = requests.post(
                f"{TIENDA_API_URL}/sheets/{sheet_id}/reject",
                json={"reason": reason or ""},
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo rechazar.")}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_upload(self, req_id, name, content, kind="sheet"):
        return self._async(req_id, self._tienda_upload_impl, name, content, kind)

    def _tienda_upload_impl(self, name, content, kind="sheet"):
        """Publica en la tienda: nombre + contenido (partitura o
        controlador, según "kind") + (opcional) foto de referencia ya
        elegida con tienda_pick_post_photo(). Queda pendiente de
        aprobación del admin, salvo que quien publica sea el propio
        admin. Cada usuario solo puede tener una publicación viva a la
        vez POR CADA APARTADO (una partitura y un controlador); el
        servidor es quien manda en esa regla."""
        if not self.session:
            return {"ok": False, "error": "Inicia sesión antes de subir a la tienda."}
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "Ponle un nombre a tu publicación."}
        if kind == "controller":
            ok, errors = validate_controller(content)
            tipo_error = "Controlador inválido: "
        else:
            ok, errors = self.validate_sheet(content)
            tipo_error = "Partitura inválida: "
        if not ok:
            return {"ok": False, "error": tipo_error + " ".join(errors)}

        photo_path = getattr(self, "_pending_post_photo", None)
        fh = None
        try:
            files = {}
            if photo_path and os.path.exists(photo_path):
                fh = open(photo_path, "rb")
                files["photo"] = (os.path.basename(photo_path), fh)
            resp = requests.post(
                f"{TIENDA_API_URL}/sheets",
                data={"name": name, "content": content, "kind": kind},
                files=files or None,
                headers=self._auth_headers(),
                timeout=20,
            )
            if fh:
                fh.close()
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo subir.")}
            self._pending_post_photo = None
            if data.get("status") == "approved":
                self.notifier.toast(f"Publicado en la tienda: {name}")
            else:
                self.notifier.toast(f"Enviado a revisión: {name} (espera la aprobación del admin)")
            return {"ok": True, "status": data.get("status")}
        except Exception as e:
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_download(self, req_id, sheet_id, kind="sheet"):
        return self._async(req_id, self._tienda_download_impl, sheet_id, kind)

    def _tienda_download_impl(self, sheet_id, kind="sheet"):
        """Descarga una publicación de la tienda a la carpeta local que
        corresponda ('partituras' o 'controladores') y refresca la
        lista de la izquierda."""
        try:
            resp = requests.get(
                f"{TIENDA_API_URL}/sheets/{sheet_id}/content",
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo descargar.")}
            default_name = "controlador.txt" if kind == "controller" else "partitura.txt"
            name = self._sanitize_filename(data.get("name") or default_name)
            if not name.lower().endswith(".txt"):
                name += ".txt"
            dest_dir = CONTROLLERS_DIR if kind == "controller" else SHEETS_DIR
            path = os.path.join(dest_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(data.get("content") or "")
            if kind == "controller":
                self.notifier.refresh_controllers()
            else:
                self.notifier.refresh()
            self.notifier.toast(f"Descargada: {name}")
            return {"ok": True, "name": name}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_admin_users(self, req_id):
        return self._async(req_id, self._tienda_admin_users_impl)

    def _tienda_admin_users_impl(self):
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero."}
        try:
            resp = requests.get(
                f"{TIENDA_API_URL}/admin/users", headers=self._auth_headers(), timeout=15
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo cargar.")}
            return {"ok": True, **data}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_admin_block(self, req_id, username, scope, permanent, hours, reason):
        return self._async(req_id, self._tienda_admin_block_impl, username, scope, permanent, hours, reason)

    def _tienda_admin_block_impl(self, username, scope, permanent, hours, reason):
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero."}
        try:
            resp = requests.post(
                f"{TIENDA_API_URL}/admin/users/{username}/block",
                json={"scope": scope, "permanent": bool(permanent), "hours": hours, "reason": reason},
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo bloquear.")}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_admin_delete_user(self, req_id, username):
        return self._async(req_id, self._tienda_admin_delete_user_impl, username)

    def _tienda_admin_delete_user_impl(self, username):
        try:
            resp = requests.delete(
                f"{TIENDA_API_URL}/admin/users/{username}",
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo borrar el usuario.")}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_admin_unblock(self, req_id, username, scope):
        return self._async(req_id, self._tienda_admin_unblock_impl, username, scope)

    def _tienda_admin_unblock_impl(self, username, scope):
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero."}
        try:
            resp = requests.post(
                f"{TIENDA_API_URL}/admin/users/{username}/unblock",
                json={"scope": scope},
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo desbloquear.")}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    def tienda_delete(self, req_id, sheet_id):
        return self._async(req_id, self._tienda_delete_impl, sheet_id)

    def _tienda_delete_impl(self, sheet_id):
        """Solo funciona si el usuario logueado es el admin (el
        servidor lo vuelve a comprobar de todas formas)."""
        if not self.session:
            return {"ok": False, "error": "Inicia sesión primero."}
        try:
            resp = requests.delete(
                f"{TIENDA_API_URL}/sheets/{sheet_id}",
                headers=self._auth_headers(),
                timeout=15,
            )
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": data.get("error", "No se pudo borrar.")}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo conectar con la tienda: {e}"}

    # -------- partituras --------
    def list_sheets(self):
        return sorted(f for f in os.listdir(SHEETS_DIR) if f.lower().endswith(".txt"))

    def load_sheet(self, name):
        path = os.path.join(SHEETS_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"# No se pudo leer el archivo: {e}"

    def get_song_text(self):
        return ""

    @staticmethod
    def _sanitize_filename(name):
        name = (name or "").strip()
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "")
        return name

    @staticmethod
    def validate_sheet(text):
        """Revisa que el texto tenga un formato de partitura válido
        (el mismo que entiende _tokenize). No exige espacios ni nada
        raro: solo que los [] y {} estén bien formados y que dentro
        de una partitura haya al menos una nota real.

        Devuelve (ok, lista_de_errores)."""
        text = text or ""
        errors = []

        if not text.strip():
            errors.append("La partitura está vacía.")
            return False, errors

        i, n = 0, len(text)
        depth_bracket = 0
        has_note = False
        line = 1

        while i < n:
            ch = text[i]
            if ch == "\n":
                line += 1
                i += 1
                continue
            if ch.isspace():
                i += 1
                continue

            if ch == "[":
                j = text.find("]", i + 1)
                if j == -1:
                    errors.append(f"Falta cerrar un '[' (línea {line}).")
                    break
                chord = text[i + 1:j]
                if not chord.strip():
                    errors.append(f"Hay un acorde vacío '[]' (línea {line}).")
                elif "[" in chord or "{" in chord:
                    errors.append(f"Hay un '[' o '{{' sin cerrar dentro de un acorde (línea {line}).")
                else:
                    has_note = True
                line += text[i:j].count("\n")
                i = j + 1
                continue

            if ch == "]":
                errors.append(f"Hay un ']' sin su '[' correspondiente (línea {line}).")
                i += 1
                continue

            if ch == "{":
                j = text.find("}", i + 1)
                if j == -1:
                    errors.append(f"Falta cerrar un '{{' (línea {line}).")
                    break
                content = text[i + 1:j]
                if not content.isdigit():
                    errors.append(
                        f"'{{{content}}}' no es válido (línea {line}): "
                        "dentro de {{ }} solo van números, ej. {300}."
                    )
                line += text[i:j].count("\n")
                i = j + 1
                continue

            if ch == "}":
                errors.append(f"Hay un '}}' sin su '{{' correspondiente (línea {line}).")
                i += 1
                continue

            if ch in ("-", "|"):
                i += 1
                continue

            # nota suelta normal
            has_note = True
            i += 1

        if not has_note and not errors:
            errors.append("No encontré ninguna nota válida en la partitura.")

        if not errors and Api._looks_like_sentence(text):
            errors.append(
                "Esto parece una frase escrita, no una partitura. Cada nota es "
                "un solo carácter suelto (o un acorde entre [ ]), sin formar "
                "palabras, ej. \"qwertyu\" o \"[qwe] r t [asd]\"."
            )

        return (len(errors) == 0), errors

    @staticmethod
    def _looks_like_sentence(text):
        """Mismo criterio que usa el servidor: si aparecen 3+ 'palabras'
        de 3+ letras fuera de un acorde, es más probable que sea texto
        normal que una partitura (que no necesita espacios)."""
        stripped = re.sub(r"\[[^\]]*\]", " ", text)
        stripped = re.sub(r"\{[^}]*\}", " ", stripped)
        words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", stripped)
        return len(words) >= 3

    def save_sheet(self, name, content):
        """Guarda el texto de la partitura actual como un .txt nuevo
        dentro de la carpeta 'partituras', con el nombre que puso el
        usuario en la interfaz. Si la partitura no tiene un formato
        válido, NO se crea el archivo."""
        safe = self._sanitize_filename(name)
        if not safe:
            self.notifier.set_status("Ponle un nombre a la partitura antes de guardar.")
            return {"ok": False, "errors": ["Ponle un nombre a la partitura antes de guardar."]}

        ok, errors = self.validate_sheet(content)
        if not ok:
            msg = "Partitura inválida: " + " ".join(errors)
            self.notifier.set_status(msg)
            self.notifier.toast("No se guardó: partitura con errores.")
            return {"ok": False, "errors": errors}

        if not safe.lower().endswith(".txt"):
            safe += ".txt"
        path = os.path.join(SHEETS_DIR, safe)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content or "")
        except Exception as e:
            self.notifier.set_status(f"No se pudo guardar la partitura: {e}")
            return {"ok": False, "errors": [str(e)]}
        self.notifier.refresh()
        self.notifier.toast(f"Guardada: {safe}")
        self.notifier.set_status(f"Partitura guardada como {safe}")
        return {"ok": True, "name": safe}

    def import_files(self):
        """Abre el explorador de Windows para elegir uno o varios .txt.
        Cada archivo se valida con el mismo formato de partituras;
        solo se copian a la carpeta 'partituras' los que sean válidos,
        los demás se descartan y se avisa cuáles fueron."""
        if self.window is None:
            return []
        try:
            paths = self.window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=("Archivos de texto (*.txt)", "Todos los archivos (*.*)"),
            )
        except Exception as e:
            self.notifier.set_status(f"No se pudo abrir el explorador: {e}")
            return []
        if not paths:
            return []
        imported = []
        rejected = []
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                rejected.append(os.path.basename(p) + " (no se pudo leer)")
                continue

            ok, errors = self.validate_sheet(content)
            base = self._sanitize_filename(os.path.basename(p))
            if not base.lower().endswith(".txt"):
                base += ".txt"

            if not ok:
                rejected.append(base)
                continue

            try:
                dest = os.path.join(SHEETS_DIR, base)
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(content)
                imported.append(base)
            except Exception:
                rejected.append(base)

        if imported:
            self.notifier.refresh()
            self.notifier.toast("Importada(s): " + ", ".join(imported))
        if rejected:
            self.notifier.toast("Rechazada(s) por formato inválido: " + ", ".join(rejected))
        self.notifier.set_status(
            f"{len(imported)} archivo(s) importado(s), {len(rejected)} rechazado(s)."
        )
        return {"imported": imported, "rejected": rejected}

    # -------- reproducción --------
    def start(self, delay, interval_ms, song_text):
        if self.playing:
            return False
        try:
            delay = float(delay)
            interval_ms = int(interval_ms)
        except (TypeError, ValueError):
            self.notifier.set_status("Tiempo de inicio o intervalo inválido.")
            return False

        events = _tokenize(song_text or "")
        if not events:
            self.notifier.set_status("La partitura está vacía.")
            return False

        self.stop_flag.clear()
        self.playing = True
        self.notifier.set_playing(True)
        self.play_thread = threading.Thread(
            target=self._play, args=(events, delay, interval_ms), daemon=True
        )
        self.play_thread.start()
        return True

    def stop(self):
        if self.playing:
            self.stop_flag.set()
        return True

    def _press_chord(self, keys_part):
        pressed = []
        for ch in keys_part:
            try:
                if ch.isupper():
                    keyboard.press("shift")
                    keyboard.press(ch.lower())
                    pressed.append(("shift", ch.lower()))
                else:
                    keyboard.press(ch)
                    pressed.append((None, ch))
            except Exception:
                self.notifier.set_status(f"Aviso: no se pudo tocar el símbolo '{ch}', se omitió.")
        time.sleep(0.03)
        for shift_key, ch in pressed:
            try:
                keyboard.release(ch)
                if shift_key:
                    keyboard.release(shift_key)
            except Exception:
                pass

    def _play(self, events, delay, interval_ms):
        try:
            remaining = delay
            while remaining > 0 and not self.stop_flag.is_set():
                self.notifier.set_status(f"Iniciando en {remaining:.1f}s... cambia a la ventana del juego")
                step = 0.1
                time.sleep(step)
                remaining -= step

            if self.stop_flag.is_set():
                self.notifier.set_status("Cancelado antes de iniciar.")
                return

            self.notifier.set_status("Tocando... (F9 o Esc para detener)")

            total = len(events)
            wait_s = interval_ms / 1000.0
            for idx, (event, start, end) in enumerate(events):
                if self.stop_flag.is_set():
                    break

                if isinstance(event, tuple) and event[0] == "SPEED":
                    wait_s = event[1] / 1000.0
                    self.notifier.set_progress((idx + 1) / total * 100)
                    continue

                if event:
                    self.notifier.set_now_playing(event)
                    self._press_chord(event)
                else:
                    self.notifier.set_now_playing("· silencio ·")

                self.notifier.set_progress((idx + 1) / total * 100)
                time.sleep(wait_s)

            if self.stop_flag.is_set():
                self.notifier.set_status("Detenido.")
            else:
                self.notifier.set_status("Canción terminada.")
                self.notifier.set_progress(100)
        except Exception as e:
            self.notifier.set_status(f"Error inesperado, detenido: {e}")
        finally:
            self.playing = False
            self.notifier.set_playing(False)
            self.notifier.set_now_playing("")


    # -------- Editor de teclado (controlador) --------
    def list_controllers(self):
        return sorted(f for f in os.listdir(CONTROLLERS_DIR) if f.lower().endswith(".txt"))

    def load_controller(self, name):
        path = os.path.join(CONTROLLERS_DIR, self._sanitize_filename(name))
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def validate_controller_text(self, content):
        """La UI llama esto para mostrar una vista previa / validación
        antes de guardar, publicar o darle 'Iniciar'."""
        ok, errors = validate_controller(content)
        steps_count = 0
        if ok:
            try:
                steps_count = len(_tokenize_controller(content))
            except ControllerError:
                pass
        return {"ok": ok, "errors": errors, "steps": steps_count}

    def save_controller(self, name, content):
        safe = self._sanitize_filename(name)
        if not safe:
            self.notifier.set_ctrl_status("Ponle un nombre al controlador antes de guardar.")
            return {"ok": False, "errors": ["Ponle un nombre al controlador antes de guardar."]}

        ok, errors = validate_controller(content)
        if not ok:
            msg = "Controlador inválido: " + " ".join(errors)
            self.notifier.set_ctrl_status(msg)
            self.notifier.toast("No se guardó: controlador con errores.")
            return {"ok": False, "errors": errors}

        if not safe.lower().endswith(".txt"):
            safe += ".txt"
        path = os.path.join(CONTROLLERS_DIR, safe)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content or "")
        except Exception as e:
            self.notifier.set_ctrl_status(f"No se pudo guardar el controlador: {e}")
            return {"ok": False, "errors": [str(e)]}
        self.notifier.refresh_controllers()
        self.notifier.toast(f"Guardado: {safe}")
        self.notifier.set_ctrl_status(f"Controlador guardado como {safe}")
        return {"ok": True, "name": safe}

    def import_controller_files(self):
        if self.window is None:
            return []
        try:
            paths = self.window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=("Archivos de texto (*.txt)", "Todos los archivos (*.*)"),
            )
        except Exception as e:
            self.notifier.set_ctrl_status(f"No se pudo abrir el explorador: {e}")
            return []
        if not paths:
            return []
        imported, rejected = [], []
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                rejected.append(os.path.basename(p) + " (no se pudo leer)")
                continue
            ok, errors = validate_controller(content)
            base = self._sanitize_filename(os.path.basename(p))
            if not base.lower().endswith(".txt"):
                base += ".txt"
            if not ok:
                rejected.append(base)
                continue
            try:
                dest = os.path.join(CONTROLLERS_DIR, base)
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(content)
                imported.append(base)
            except Exception:
                rejected.append(base)
        if imported:
            self.notifier.refresh_controllers()
            self.notifier.toast("Importado(s): " + ", ".join(imported))
        if rejected:
            self.notifier.toast("Rechazado(s) por formato inválido: " + ", ".join(rejected))
        self.notifier.set_ctrl_status(
            f"{len(imported)} archivo(s) importado(s), {len(rejected)} rechazado(s)."
        )
        return {"imported": imported, "rejected": rejected}

    def start_controller(self, delay, script_text):
        if self.ctrl_playing:
            return False
        try:
            delay = float(delay)
        except (TypeError, ValueError):
            self.notifier.set_ctrl_status("Tiempo de inicio inválido.")
            return False
        try:
            steps = _tokenize_controller(script_text or "")
        except ControllerError as e:
            self.notifier.set_ctrl_status(f"Controlador inválido: {e}")
            return False

        self.ctrl_stop_flag.clear()
        self.ctrl_playing = True
        self.notifier.set_ctrl_playing(True)
        self.ctrl_thread = threading.Thread(
            target=self._run_controller, args=(steps, delay), daemon=True
        )
        self.ctrl_thread.start()
        return True

    def stop_controller(self):
        if self.ctrl_playing:
            self.ctrl_stop_flag.set()
        return True

    def _sleep_interruptible(self, seconds):
        end = time.time() + seconds
        while not self.ctrl_stop_flag.is_set():
            remaining = end - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.05, remaining))

    def _press_combo(self, keys):
        pressed = []
        for k in keys:
            try:
                keyboard.press(k)
                pressed.append(k)
            except Exception:
                self.notifier.toast(f"Aviso: no reconocí la tecla '{k}', se omitió.")
        return pressed

    def _release_combo(self, pressed):
        for k in reversed(pressed):
            try:
                keyboard.release(k)
            except Exception:
                pass

    def _tap_combo(self, keys, duration, tap_ms):
        end = time.time() + duration
        interval = max(0.02, tap_ms / 1000.0)
        while not self.ctrl_stop_flag.is_set() and time.time() < end:
            pressed = self._press_combo(keys)
            time.sleep(min(0.03, interval))
            self._release_combo(pressed)
            rest = interval - 0.03
            if rest > 0:
                self._sleep_interruptible(rest)

    def _run_controller(self, steps, delay):
        try:
            remaining = delay
            while remaining > 0 and not self.ctrl_stop_flag.is_set():
                self.notifier.set_ctrl_status(
                    f"Iniciando en {remaining:.1f}s... cambia a la ventana del juego"
                )
                step_wait = 0.1
                time.sleep(step_wait)
                remaining -= step_wait

            if self.ctrl_stop_flag.is_set():
                self.notifier.set_ctrl_status("Cancelado antes de iniciar.")
                return

            self.notifier.set_ctrl_status("Ejecutando... (F11 o Esc para detener)")
            total = len(steps)
            for idx, step in enumerate(steps):
                if self.ctrl_stop_flag.is_set():
                    break

                if step.get("wait"):
                    self.notifier.set_ctrl_now(f"· esperando {step['duration']:.1f}s ·")
                    self._sleep_interruptible(step["duration"])
                else:
                    label = "+".join(k.upper() for k in step["keys"])
                    if step["mode"] == "tap":
                        label += " (toques)"
                    self.notifier.set_ctrl_now(label)
                    if step["mode"] == "hold":
                        pressed = self._press_combo(step["keys"])
                        self._sleep_interruptible(step["duration"])
                        self._release_combo(pressed)
                    else:
                        self._tap_combo(step["keys"], step["duration"], step["tap_ms"])

                self.notifier.set_ctrl_progress((idx + 1) / total * 100)

            if self.ctrl_stop_flag.is_set():
                self.notifier.set_ctrl_status("Detenido.")
            else:
                self.notifier.set_ctrl_status("Controlador terminado.")
                self.notifier.set_ctrl_progress(100)
        except Exception as e:
            self.notifier.set_ctrl_status(f"Error inesperado, detenido: {e}")
        finally:
            self.ctrl_playing = False
            self.notifier.set_ctrl_playing(False)
            self.notifier.set_ctrl_now("")


def register_hotkeys(window):
    def click(btn_id):
        try:
            window.evaluate_js(f"document.getElementById('{btn_id}').click()")
        except Exception:
            pass

    keyboard.add_hotkey("F8", lambda: click("startBtn"))
    keyboard.add_hotkey("F9", lambda: click("stopBtn"))
    keyboard.add_hotkey("F10", lambda: click("ctrlStartBtn"))
    keyboard.add_hotkey("F11", lambda: click("ctrlStopBtn"))
    keyboard.add_hotkey("esc", lambda: (click("stopBtn"), click("ctrlStopBtn")))


def _looks_like_temp_extraction(path):
    """Detecta si el programa se está corriendo desde una carpeta
    temporal típica de 'abrir el .exe directo desde dentro del .zip
    sin extraer primero' (Windows lo monta en una carpeta temporal).
    Eso causa justo el combo de bugs más reportado: el programa se
    queda 'No responde' seguido (todo el disco ahí es lento/virtual) y
    la sesión iniciada nunca se recuerda (esa carpeta se borra sola)."""
    lowered = path.lower()
    markers = (
        "\\temp\\", "/temp/",
        "\\appdata\\local\\temp\\",
        "rar$", "wz$se",  # carpetas temporales típicas de WinRAR / 7-Zip
        "\\temporary internet files\\",
    )
    return any(m in lowered for m in markers)


def _warn_if_temp_extraction():
    if not _looks_like_temp_extraction(BASE_DIR):
        return
    message = (
        "Parece que abriste PianoAutoplayer.exe directo desde dentro "
        "de un .zip sin extraerlo primero (Windows lo abre desde una "
        "carpeta temporal).\n\n"
        "Eso hace que el programa se quede 'No responde' seguido y que "
        "nunca recuerde tu inicio de sesión.\n\n"
        "Solución: haz clic derecho en el .zip -> 'Extraer todo...' a "
        "una carpeta normal, y abre PianoAutoplayer.exe desde ahí."
    )
    try:
        import ctypes

        MB_OK = 0x0
        ICON_WARNING = 0x30
        ctypes.windll.user32.MessageBoxW(0, message, "Piano Autoplayer - Aviso", MB_OK | ICON_WARNING)
    except Exception:
        print(message)


def main():
    os.makedirs(SHEETS_DIR, exist_ok=True)
    os.makedirs(CONTROLLERS_DIR, exist_ok=True)
    if getattr(sys, "frozen", False):
        _warn_if_temp_extraction()

    # Modo diagnóstico: si corres el programa con "py piano_autoplayer.py"
    # (en vez del .exe ya compilado), se activa solo. Esto abre las
    # herramientas de desarrollador dentro de la ventana (clic derecho ->
    # Inspeccionar, o F12) para ver la consola de JavaScript, y deja ver
    # en esta consola los avisos de arranque. También se puede forzar en
    # el .exe poniendo la variable de entorno PIANO_DEBUG=1 antes de
    # abrirlo.
    debug_mode = (not getattr(sys, "frozen", False)) or (os.environ.get("PIANO_DEBUG") == "1")

    print("Piano Autoplayer: iniciando...")
    print(f"  BASE_DIR = {BASE_DIR}")
    print(f"  WEB_DIR  = {WEB_DIR}")
    print(f"  modo debug (consola/devtools) = {debug_mode}")

    api = Api()
    window = webview.create_window(
        "Piano Autoplayer • Tirji",
        url=os.path.join(WEB_DIR, "index.html"),
        js_api=api,
        width=640,
        height=760,
        min_size=(560, 620),
        background_color="#0c0d16",
        on_top=True,
    )
    api.window = window

    def on_loaded():
        print("Piano Autoplayer: la ventana terminó de cargar (evento 'loaded').")
        register_hotkeys(window)
        sync = SheetSync(api.notifier)
        threading.Thread(target=sync.loop, daemon=True).start()

    window.events.loaded += on_loaded

    try:
        # IMPORTANTE: forzamos el motor moderno (EdgeChromium / WebView2)
        # y servimos la página vía un mini servidor HTTP local
        # (http_server=True) en vez de abrirla como file://. Con
        # EdgeChromium, cargar la página directo desde disco (file://)
        # puede bloquear por seguridad la inyección del puente
        # "window.pywebview.api", y entonces la ventana se queda
        # pegada en "Cargando..." para siempre aunque el programa de
        # Python sí arrancó bien (por eso las carpetas de la Tienda sí
        # se crean, pero la interfaz nunca reacciona).
        webview.start(gui="edgechromium", debug=debug_mode, http_server=True)
    except Exception as e:
        _fatal_startup_error(
            "No se pudo iniciar el componente de la ventana (WebView2).\n\n"
            "Instala el 'Microsoft Edge WebView2 Runtime' (gratis, de "
            "Microsoft) y vuelve a abrir Piano Autoplayer.\n\n"
            f"Detalle tecnico: {e}"
        )


def _fatal_startup_error(message):
    """Muestra un aviso claro en vez de dejar la ventana rota en
    silencio. Usa un cuadro de mensaje nativo de Windows porque en este
    punto la ventana de pywebview ya no sirve (o nunca cargo bien)."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Piano Autoplayer - Error", 0x10)
    except Exception:
        print(message)


if __name__ == "__main__":
    main()