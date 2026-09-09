"""
Piano Autoplayer - Tirji
--------------------------------------------------
Simula pulsaciones de teclado automáticamente, como si
estuvieras tocando un piano/teclado de letras (ej. en Roblox).

Requisitos (instalar una vez):
    pip install keyboard

IMPORTANTE:
- En Windows normalmente hay que ejecutar como Administrador
  para que "keyboard" pueda enviar teclas a otras ventanas (ej. Roblox).
- Antes de iniciar, deja el cursor sobre la ventana del juego
  (Roblox), el programa te da unos segundos de cuenta regresiva
  para que cambies de ventana.

FORMATO DE LA PARTITURA:
- Escribe las teclas separadas por espacios. Cada espacio = un
  "momento" en el tiempo, separado por el intervalo configurado.
- Si en un mismo momento quieres tocar varias teclas a la vez
  (un acorde), escríbelas juntas sin espacio. Ejemplo:

      q w e asd f

  Aquí se toca: q, luego w, luego e, luego (a+s+d juntas), luego f.

- Puedes usar "-" como un "silencio" (no se toca nada, solo espera).
- Puedes cambiar el tiempo de espera de una nota puntual poniendo
  un número entre corchetes justo después del token, en milisegundos.
  Ejemplo:  q[800] w  -> después de tocar "q" espera 800ms en vez del
  intervalo por defecto, luego toca "w".
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import re

try:
    import keyboard
except ImportError:
    raise SystemExit("Falta la librería 'keyboard'. Instálala con: pip install keyboard")


TOKEN_RE = re.compile(r"^([^\[\]]*)(?:\[(\d+)\])?$")


class PianoAutoplayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Piano Autoplayer - Tirji")
        self.root.geometry("560x520")

        self.playing = False
        self.stop_flag = threading.Event()
        self.play_thread = None

        self._build_ui()
        self._register_hotkeys()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm_top = ttk.Frame(self.root)
        frm_top.pack(fill="x", **pad)

        ttk.Label(frm_top, text="Tiempo de inicio (segundos):").grid(row=0, column=0, sticky="w")
        self.start_delay_var = tk.StringVar(value="3")
        ttk.Entry(frm_top, textvariable=self.start_delay_var, width=8).grid(row=0, column=1, padx=(6, 20))

        ttk.Label(frm_top, text="Intervalo entre notas (ms):").grid(row=0, column=2, sticky="w")
        self.interval_var = tk.StringVar(value="300")
        ttk.Entry(frm_top, textvariable=self.interval_var, width=8).grid(row=0, column=3, padx=6)

        ttk.Label(
            self.root,
            text="Partitura (letras separadas por espacio, juntas = acorde, '-' = silencio):"
        ).pack(anchor="w", **pad)

        self.song_text = tk.Text(self.root, height=14, wrap="word")
        self.song_text.pack(fill="both", expand=True, padx=10)
        self.song_text.insert("1.0", "q w e r t y u")

        frm_btn = ttk.Frame(self.root)
        frm_btn.pack(fill="x", **pad)

        self.start_btn = ttk.Button(frm_btn, text="Iniciar (F8)", command=self.start)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ttk.Button(frm_btn, text="Detener (F9 / Esc)", command=self.stop)
        self.stop_btn.pack(side="left")

        self.status_var = tk.StringVar(value="Listo.")
        ttk.Label(self.root, textvariable=self.status_var, foreground="blue").pack(anchor="w", padx=10, pady=(0, 10))

    def _register_hotkeys(self):
        keyboard.add_hotkey("F8", self.start)
        keyboard.add_hotkey("F9", self.stop)
        keyboard.add_hotkey("esc", self.stop)

    def _set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def start(self):
        if self.playing:
            return
        try:
            delay = float(self.start_delay_var.get())
            interval_ms = int(self.interval_var.get())
        except ValueError:
            messagebox.showerror("Error", "Tiempo de inicio o intervalo inválido.")
            return

        raw_song = self.song_text.get("1.0", "end").strip()
        tokens = raw_song.split()
        if not tokens:
            messagebox.showerror("Error", "La partitura está vacía.")
            return

        self.stop_flag.clear()
        self.playing = True
        self.play_thread = threading.Thread(
            target=self._play, args=(tokens, delay, interval_ms), daemon=True
        )
        self.play_thread.start()

    def stop(self):
        if self.playing:
            self.stop_flag.set()

    def _play(self, tokens, delay, interval_ms):
        # Cuenta regresiva para cambiar de ventana
        remaining = delay
        while remaining > 0 and not self.stop_flag.is_set():
            self._set_status(f"Iniciando en {remaining:.1f}s... cambia a la ventana del juego")
            step = 0.1
            time.sleep(step)
            remaining -= step

        if self.stop_flag.is_set():
            self._set_status("Cancelado antes de iniciar.")
            self.playing = False
            return

        self._set_status("Tocando... (F9 o Esc para detener)")

        for token in tokens:
            if self.stop_flag.is_set():
                break

            match = TOKEN_RE.match(token)
            keys_part, custom_ms = (match.group(1), match.group(2)) if match else (token, None)
            wait_s = (int(custom_ms) if custom_ms else interval_ms) / 1000.0

            if keys_part and keys_part != "-":
                keys = list(keys_part)
                for k in keys:
                    keyboard.press(k)
                time.sleep(0.03)
                for k in keys:
                    keyboard.release(k)

            time.sleep(wait_s)

        self.playing = False
        if self.stop_flag.is_set():
            self._set_status("Detenido.")
        else:
            self._set_status("Canción terminada.")


if __name__ == "__main__":
    root = tk.Tk()
    app = PianoAutoplayer(root)
    root.mainloop()
