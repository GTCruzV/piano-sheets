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
"""

import json
import os
import sys
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
GITHUB_OWNER = "TU_USUARIO_DE_GITHUB"
GITHUB_REPO = "TU_REPOSITORIO"
GITHUB_BRANCH = "main"
GITHUB_PATH = "partituras"
SYNC_INTERVAL_SECONDS = 90
# ========================================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = BASE_DIR

SHEETS_DIR = os.path.join(BASE_DIR, "partituras")
MANIFEST_PATH = os.path.join(SHEETS_DIR, ".sync_manifest.json")
WEB_DIR = os.path.join(RES_DIR, "web")


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


class Api:
    def __init__(self):
        self.window = None
        self.notifier = Notifier(lambda: self.window)
        self.playing = False
        self.stop_flag = threading.Event()
        self.play_thread = None

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


def register_hotkeys(window):
    def click(btn_id):
        try:
            window.evaluate_js(f"document.getElementById('{btn_id}').click()")
        except Exception:
            pass

    keyboard.add_hotkey("F8", lambda: click("startBtn"))
    keyboard.add_hotkey("F9", lambda: click("stopBtn"))
    keyboard.add_hotkey("esc", lambda: click("stopBtn"))


def main():
    os.makedirs(SHEETS_DIR, exist_ok=True)

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
        register_hotkeys(window)
        sync = SheetSync(api.notifier)
        threading.Thread(target=sync.loop, daemon=True).start()

    window.events.loaded += on_loaded

    webview.start()


if __name__ == "__main__":
    main()