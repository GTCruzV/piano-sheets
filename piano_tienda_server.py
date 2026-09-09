"""
Piano Tienda - Servidor
--------------------------------------------------
Backend chiquito (Flask + SQLite) que le da vida a la pestaña "Tienda"
del Piano Autoplayer: cuentas de usuario (con foto de perfil), y
"publicaciones" estilo Instagram: cada usuario puede subir UNA
partitura/proyecto (con nombre y foto de referencia cuadrada), que
queda "pendiente" hasta que el admin (tirhiv) la aprueba o la rechaza.
Solo las aprobadas se ven en la tienda pública.

Este es el servidor al que apunta TIENDA_API_URL en piano_autoplayer.py.
Debe quedar accesible por internet (tu dominio/tunnel) en una URL que
termine en /api, por ejemplo: https://piano-api.hmrp.lat/api

CÓMO CORRERLO:
    pip install -r requirements_server.txt
    python piano_tienda_server.py
Por defecto escucha en 0.0.0.0:5000. Publícalo detrás de tu túnel
(Cloudflare Tunnel, nginx, etc.) apuntando ese dominio a este puerto.

ADMIN:
    El usuario "tirhiv" (ver ADMIN_USERNAME abajo) es el único admin.
    Ese nombre de usuario queda reservado: si alguien más se registra
    con ese nombre, no obtiene privilegios de admin (la cuenta admin
    real es la que coincide exactamente, sin distinguir mayúsculas).
    El admin es quien aprueba o rechaza lo que suben los demás en la
    Tienda, y es el único que puede borrar publicaciones.
"""

import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ================== CONFIGURA AQUÍ ==================
ADMIN_USERNAME = "tirhiv"          # este usuario (sin importar mayúsculas) será el admin
HOST = "0.0.0.0"
PORT = 5000
# URL pública real por la que la gente accede (a través del túnel/
# Cloudflare). IMPORTANTE: se usa esto en vez de adivinar con
# request.host_url, porque el túnel termina el HTTPS y le manda a
# Flask la petición en HTTP puro; si dejamos que Flask "adivine" el
# esquema, siempre cree que es http y las fotos nunca cargan (el
# esquema queda guardado como http:// aunque el sitio sea https://,
# y ese dominio normalmente ni siquiera acepta conexiones por 80).
PUBLIC_BASE_URL = "https://piano-api.hmrp.lat"
# ======================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tienda.db")
PHOTOS_DIR = os.path.join(BASE_DIR, "uploads_photos")
POSTS_DIR = os.path.join(BASE_DIR, "uploads_posts")
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(POSTS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB por request (fotos + partitura)

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


# -------------------- base de datos --------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _column_exists(conn, table, column):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    return column in cols


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            photo_file TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS blocked_devices (
            device_id TEXT PRIMARY KEY,
            permanent INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    # --- migración: nuevas columnas para el flujo de publicaciones con
    # aprobación (status/photo_file/reject_reason/reviewed_at). Los
    # registros que ya existían de antes (cuando no había revisión) se
    # marcan como "approved" para que no desaparezcan de la tienda.
    if not _column_exists(conn, "sheets", "status"):
        conn.execute("ALTER TABLE sheets ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'")
    if not _column_exists(conn, "sheets", "photo_file"):
        conn.execute("ALTER TABLE sheets ADD COLUMN photo_file TEXT")
    if not _column_exists(conn, "sheets", "reject_reason"):
        conn.execute("ALTER TABLE sheets ADD COLUMN reject_reason TEXT")
    if not _column_exists(conn, "sheets", "reviewed_at"):
        conn.execute("ALTER TABLE sheets ADD COLUMN reviewed_at TEXT")

    # --- migración: bloqueo de cuentas (temporal o permanente) y el
    # último dispositivo con el que cada quien entró (para que el
    # admin lo pueda bloquear desde el panel de Supervisión).
    if not _column_exists(conn, "users", "blocked_permanent"):
        conn.execute("ALTER TABLE users ADD COLUMN blocked_permanent INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "users", "blocked_until"):
        conn.execute("ALTER TABLE users ADD COLUMN blocked_until TEXT")
    if not _column_exists(conn, "users", "blocked_reason"):
        conn.execute("ALTER TABLE users ADD COLUMN blocked_reason TEXT")
    if not _column_exists(conn, "users", "last_device_id"):
        conn.execute("ALTER TABLE users ADD COLUMN last_device_id TEXT")
    conn.commit()

    # --- corrige quién es admin, por si ADMIN_USERNAME cambió: nadie
    # más que el usuario exacto (case-insensitive) queda con is_admin.
    conn.execute(
        "UPDATE users SET is_admin = CASE WHEN LOWER(username) = LOWER(?) THEN 1 ELSE 0 END",
        (ADMIN_USERNAME,),
    )
    conn.commit()
    conn.close()


# -------------------- validación de partitura (igual que el cliente) --------------------
def _looks_like_sentence(text):
    """Detecta si el texto parece una frase normal (como una publicación
    de chat) en vez de una partitura real. Una partitura de piano
    virtual no necesita espacios (cada carácter es una nota suelta, o
    un acorde entre [ ]); si aparecen varias "palabras" de 3+ letras
    seguidas fuera de un acorde, casi seguro es texto escrito, no
    notas. No se usa una lista blanca de caracteres porque los
    números/símbolos con shift SÍ son notas válidas en muchas
    partituras (ej. "1!2@3#")."""
    # quita el contenido de acordes [ ] y de tags de velocidad { } antes
    # de buscar "palabras", para no confundir un acorde largo con texto
    stripped = re.sub(r"\[[^\]]*\]", " ", text)
    stripped = re.sub(r"\{[^}]*\}", " ", stripped)
    words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", stripped)
    return len(words) >= 3


def validate_sheet(text):
    text = text or ""
    if not text.strip():
        return False, "La partitura está vacía."
    i, n = 0, len(text)
    has_note = False
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "[":
            j = text.find("]", i + 1)
            if j == -1:
                return False, "Falta cerrar un '['."
            chord = text[i + 1:j]
            if not chord.strip():
                return False, "Hay un acorde vacío '[]'."
            if "[" in chord or "{" in chord:
                return False, "Hay un '[' o '{' sin cerrar dentro de un acorde."
            has_note = True
            i = j + 1
            continue
        if ch == "]":
            return False, "Hay un ']' sin su '[' correspondiente."
        if ch == "{":
            j = text.find("}", i + 1)
            if j == -1:
                return False, "Falta cerrar un '{'."
            content = text[i + 1:j]
            if not content.isdigit():
                return False, f"'{{{content}}}' no es válido: solo números, ej. {{300}}."
            i = j + 1
            continue
        if ch == "}":
            return False, "Hay un '}' sin su '{' correspondiente."
        if ch in ("-", "|"):
            i += 1
            continue
        has_note = True
        i += 1
    if not has_note:
        return False, "No encontré ninguna nota válida en la partitura."
    if _looks_like_sentence(text):
        return False, (
            "Esto parece una frase escrita, no una partitura. Recuerda: cada "
            "nota es un solo carácter suelto (o un acorde entre [ ]), sin "
            "formar palabras, ej. \"qwertyu\" o \"[qwe] r t [asd]\"."
        )
    return True, None


def safe_username(name):
    name = (name or "").strip()
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "", name)[:32]


def save_image(file_storage, prefix):
    """Guarda una imagen subida (foto de perfil o de referencia) con un
    nombre único y devuelve el nombre de archivo, o None si no venía
    imagen válida."""
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    if ext not in IMG_EXTS:
        ext = ".png"
    fname = f"{prefix}_{int(time.time() * 1000)}{ext}"
    file_storage.save(os.path.join(PHOTOS_DIR, fname))
    return fname


# -------------------- helpers de auth y bloqueos --------------------
def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):].strip()
    if not token:
        return None
    db = get_db()
    row = db.execute(
        "SELECT users.* FROM tokens JOIN users ON users.id = tokens.user_id WHERE tokens.token = ?",
        (token,),
    ).fetchone()
    return row


def _not_expired(blocked_until):
    if not blocked_until:
        return False
    try:
        return datetime.fromisoformat(blocked_until) > datetime.utcnow()
    except Exception:
        return False


def user_block_status(user_row):
    """Devuelve None si el usuario puede usar la tienda, o un texto con
    el motivo si está bloqueado (permanente o temporal vigente)."""
    if user_row["blocked_permanent"]:
        reason = user_row["blocked_reason"]
        return "Tu cuenta fue bloqueada permanentemente" + (f": {reason}" if reason else ".")
    if _not_expired(user_row["blocked_until"]):
        reason = user_row["blocked_reason"]
        until = user_row["blocked_until"]
        return f"Tu cuenta está bloqueada hasta {until} (UTC)" + (f": {reason}" if reason else ".")
    return None


def device_block_status(device_id):
    if not device_id:
        return None
    db = get_db()
    row = db.execute("SELECT * FROM blocked_devices WHERE device_id = ?", (device_id,)).fetchone()
    if not row:
        return None
    if row["permanent"]:
        reason = row["reason"]
        return "Este dispositivo fue bloqueado permanentemente" + (f": {reason}" if reason else ".")
    if _not_expired(row["blocked_until"]):
        reason = row["reason"]
        return f"Este dispositivo está bloqueado hasta {row['blocked_until']} (UTC)" + (f": {reason}" if reason else ".")
    return None


def require_user():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Inicia sesión primero."}), 401)
    reason = user_block_status(user)
    if reason:
        # una cuenta bloqueada no puede seguir usando tokens viejos:
        # se le cierra la sesión en el servidor de una vez
        db = get_db()
        db.execute("DELETE FROM tokens WHERE user_id = ?", (user["id"],))
        db.commit()
        return None, (jsonify({"error": reason}), 403)
    return user, None


def require_admin():
    user, err = require_user()
    if err:
        return None, err
    if not user["is_admin"]:
        return None, (jsonify({"error": "Solo el admin puede hacer esto."}), 403)
    return user, None


def photo_url(photo_file):
    if not photo_file:
        return None
    return PUBLIC_BASE_URL.rstrip("/") + "/api/photos/" + photo_file


def get_device_id():
    """El cliente manda un id de dispositivo generado una sola vez y
    guardado en disco (ver piano_autoplayer.py). Sirve para poder
    bloquear un dispositivo aunque cambien de cuenta."""
    return (request.headers.get("X-Device-Id") or "").strip()[:128] or None


def user_public(row, token=None):
    data = {
        "username": row["username"],
        "isAdmin": bool(row["is_admin"]),
        "photo": photo_url(row["photo_file"]),
    }
    if token:
        data["token"] = token
    return data


def sheet_public(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "username": row["username"],
        "user_photo": photo_url(row["photo_file"]),
        "photo": photo_url(row["post_photo_file"]),
        "status": row["status"],
        "reject_reason": row["reject_reason"],
        "created_at": row["created_at"],
    }


SHEET_JOIN_SQL = """
    SELECT sheets.id, sheets.name, sheets.created_at, sheets.status,
           sheets.reject_reason, sheets.user_id,
           sheets.photo_file AS post_photo_file,
           users.username, users.photo_file
    FROM sheets JOIN users ON users.id = sheets.user_id
"""


# -------------------- rutas: fotos --------------------
@app.route("/api/photos/<path:filename>")
def serve_photo(filename):
    return send_from_directory(PHOTOS_DIR, filename)


# -------------------- rutas: cuentas --------------------
@app.route("/api/register", methods=["POST"])
def register():
    username = safe_username(request.form.get("username"))
    password = (request.form.get("password") or "").strip()
    if not username or not password:
        return jsonify({"error": "Falta usuario o contraseña."}), 400

    device_id = get_device_id()
    dev_reason = device_block_status(device_id)
    if dev_reason:
        return jsonify({"error": dev_reason}), 403

    db = get_db()
    exists = db.execute(
        "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    if exists:
        return jsonify({"error": "Ese usuario ya existe."}), 400

    photo_file = save_image(request.files.get("photo"), username)
    is_admin = 1 if username.lower() == ADMIN_USERNAME.lower() else 0
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, photo_file, is_admin, created_at, last_device_id) VALUES (?, ?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), photo_file, is_admin, datetime.utcnow().isoformat(), device_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ese usuario ya existe."}), 400
    user_id = cur.lastrowid

    token = secrets.token_hex(24)
    db.execute("INSERT INTO tokens (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, datetime.utcnow().isoformat()))
    db.commit()

    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return jsonify(user_public(row, token))


def _log_login_attempt(raw_username, safe_username_value, reason):
    """Registra intentos de login fallidos en un archivo aparte (NUNCA
    la contraseña) para poder diagnosticar el bug de 'usuario o
    contraseña incorrectos' cuando la persona jura que los puso bien.
    Revisa login_debug.log junto al servidor si vuelve a pasar: te dirá
    si el usuario no se encontró (typo, o se registró con otro nombre
    por los caracteres que safe_username() le quita) o si sí se
    encontró pero la contraseña no hizo match."""
    try:
        clean = (raw_username or "").replace("\n", " ").replace("\r", " ")[:64]
        with open(os.path.join(BASE_DIR, "login_debug.log"), "a", encoding="utf-8") as f:
            f.write(
                f"{datetime.utcnow().isoformat()} intento='{clean}' "
                f"interpretado_como='{safe_username_value}' resultado={reason}\n"
            )
    except Exception:
        pass


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    raw_username = payload.get("username") or ""
    username = safe_username(raw_username)
    password = (payload.get("password") or "").strip()

    if not username or not password:
        _log_login_attempt(raw_username, username, "faltaba_usuario_o_contrasena")
        return jsonify({"error": "Usuario o contraseña incorrectos."}), 400

    device_id = get_device_id()
    dev_reason = device_block_status(device_id)
    if dev_reason:
        _log_login_attempt(raw_username, username, "dispositivo_bloqueado")
        return jsonify({"error": dev_reason}), 403

    db = get_db()
    row = db.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()

    valid = False
    if row:
        try:
            valid = check_password_hash(row["password_hash"], password)
        except Exception:
            # un hash corrupto o de un formato no soportado nunca debe
            # tumbar el servidor: se trata como contraseña incorrecta
            valid = False

    if not row or not valid:
        _log_login_attempt(raw_username, username, "usuario_no_encontrado" if not row else "contrasena_no_coincide")
        return jsonify({"error": "Usuario o contraseña incorrectos."}), 400

    block_reason = user_block_status(row)
    if block_reason:
        _log_login_attempt(raw_username, username, "cuenta_bloqueada")
        return jsonify({"error": block_reason}), 403

    if device_id:
        db.execute("UPDATE users SET last_device_id = ? WHERE id = ?", (device_id, row["id"]))

    token = secrets.token_hex(24)
    db.execute("INSERT INTO tokens (token, user_id, created_at) VALUES (?, ?, ?)", (token, row["id"], datetime.utcnow().isoformat()))
    db.commit()
    return jsonify(user_public(row, token))


@app.route("/api/logout", methods=["POST"])
def logout():
    # invalida el token actual en el servidor (si venía uno). Siempre
    # responde ok: cerrar sesión nunca debe quedarse "atorado".
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[len("Bearer "):].strip()
        if token:
            db = get_db()
            db.execute("DELETE FROM tokens WHERE token = ?", (token,))
            db.commit()
    return jsonify({"ok": True})


@app.route("/api/me", methods=["GET"])
def me():
    """El cliente llama esto al arrancar para revalidar la sesión
    guardada localmente (en vez de confiar ciegamente en el archivo de
    sesión): si el token ya no es válido, avisa con 401 para que la
    app pida iniciar sesión de nuevo; si es válido, devuelve los datos
    frescos (por si la foto o el rol de admin cambiaron)."""
    user, err = require_user()
    if err:
        return err
    return jsonify(user_public(user))


# -------------------- rutas: tienda pública (solo aprobadas) --------------------
@app.route("/api/sheets", methods=["GET"])
def list_sheets():
    db = get_db()
    rows = db.execute(SHEET_JOIN_SQL + " WHERE sheets.status = 'approved' ORDER BY sheets.id DESC").fetchall()
    return jsonify([sheet_public(r) for r in rows])


@app.route("/api/users/<username>/sheets", methods=["GET"])
def user_profile(username):
    """Perfil público de un usuario: su foto y sus publicaciones
    aprobadas (para cuando se pica la foto de alguien en la tienda)."""
    db = get_db()
    user_row = db.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    if not user_row:
        return jsonify({"error": "Ese usuario no existe."}), 404
    rows = db.execute(
        SHEET_JOIN_SQL + " WHERE sheets.user_id = ? AND sheets.status = 'approved' ORDER BY sheets.id DESC",
        (user_row["id"],),
    ).fetchall()
    return jsonify({
        "profile": {
            "username": user_row["username"],
            "isAdmin": bool(user_row["is_admin"]),
            "photo": photo_url(user_row["photo_file"]),
        },
        "items": [sheet_public(r) for r in rows],
    })


@app.route("/api/sheets/mine", methods=["GET"])
def my_sheet():
    """Devuelve la publicación (pendiente/aprobada/rechazada) del
    usuario logueado, si tiene una. Sirve para que la app sepa si ya
    puede publicar otra vez o si debe esperar/mostrar el estado."""
    user, err = require_user()
    if err:
        return err
    db = get_db()
    row = db.execute(SHEET_JOIN_SQL + " WHERE sheets.user_id = ? ORDER BY sheets.id DESC LIMIT 1", (user["id"],)).fetchone()
    return jsonify({"item": sheet_public(row) if row else None})


@app.route("/api/sheets", methods=["POST"])
def upload_sheet():
    """Crea una publicación nueva. Cada usuario solo puede tener UNA
    publicación viva a la vez (pendiente o aprobada); si la anterior
    fue rechazada, puede volver a intentarlo."""
    user, err = require_user()
    if err:
        return err

    db = get_db()
    existing = db.execute(
        "SELECT id, status FROM sheets WHERE user_id = ? AND status IN ('pending', 'approved') ORDER BY id DESC LIMIT 1",
        (user["id"],),
    ).fetchone()
    if existing:
        if existing["status"] == "approved":
            return jsonify({"error": "Ya tienes una publicación en la tienda. Solo se permite una por usuario."}), 400
        return jsonify({"error": "Ya tienes una publicación esperando aprobación. Espera la respuesta del admin."}), 400

    name = (request.form.get("name") or "").strip()
    content = request.form.get("content") or ""
    if not name:
        return jsonify({"error": "Ponle un nombre a tu publicación."}), 400
    ok, err_msg = validate_sheet(content)
    if not ok:
        return jsonify({"error": "Partitura inválida: " + err_msg}), 400

    photo_file = save_image(request.files.get("photo"), f"post_{user['username']}")

    # el admin se auto-aprueba (es quien supervisa, no necesita
    # esperar su propia revisión); todos los demás quedan pendientes
    is_admin = bool(user["is_admin"])
    status = "approved" if is_admin else "pending"
    now = datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO sheets (name, content, user_id, created_at, status, photo_file, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, content, user["id"], now, status, photo_file, now if is_admin else None),
    )
    db.commit()
    return jsonify({"ok": True, "id": cur.lastrowid, "status": status})


@app.route("/api/sheets/<int:sheet_id>/content", methods=["GET"])
def sheet_content(sheet_id):
    db = get_db()
    row = db.execute("SELECT name, content, user_id, status FROM sheets WHERE id = ?", (sheet_id,)).fetchone()
    if not row:
        return jsonify({"error": "No existe esa partitura."}), 404
    if row["status"] != "approved":
        # solo el dueño o el admin pueden ver el contenido de algo que
        # todavía no está público (para revisarlo antes de aprobar)
        user = current_user()
        if not user or (user["id"] != row["user_id"] and not user["is_admin"]):
            return jsonify({"error": "Esa partitura todavía no está disponible."}), 403
    return jsonify({"name": row["name"], "content": row["content"]})


@app.route("/api/sheets/<int:sheet_id>", methods=["DELETE"])
def delete_sheet(sheet_id):
    """El dueño de la publicación puede borrar la suya propia (en
    cualquier estado); el admin puede borrar cualquiera."""
    user, err = require_user()
    if err:
        return err
    db = get_db()
    row = db.execute("SELECT id, user_id FROM sheets WHERE id = ?", (sheet_id,)).fetchone()
    if not row:
        return jsonify({"error": "Esa publicación ya no existe."}), 404
    if row["user_id"] != user["id"] and not user["is_admin"]:
        return jsonify({"error": "Solo puedes borrar tu propia publicación."}), 403
    db.execute("DELETE FROM sheets WHERE id = ?", (sheet_id,))
    db.commit()
    return jsonify({"ok": True})


# -------------------- rutas: revisión del admin --------------------
@app.route("/api/sheets/pending", methods=["GET"])
def pending_sheets():
    user, err = require_admin()
    if err:
        return err
    db = get_db()
    rows = db.execute(
        SHEET_JOIN_SQL + " WHERE sheets.status = 'pending' ORDER BY sheets.id ASC"
    ).fetchall()
    items = []
    for r in rows:
        content_row = db.execute("SELECT content FROM sheets WHERE id = ?", (r["id"],)).fetchone()
        item = sheet_public(r)
        item["content"] = content_row["content"] if content_row else ""
        items.append(item)
    return jsonify(items)


@app.route("/api/sheets/<int:sheet_id>/approve", methods=["POST"])
def approve_sheet(sheet_id):
    user, err = require_admin()
    if err:
        return err
    db = get_db()
    row = db.execute("SELECT id FROM sheets WHERE id = ? AND status = 'pending'", (sheet_id,)).fetchone()
    if not row:
        return jsonify({"error": "Esa solicitud ya no está pendiente."}), 404
    db.execute(
        "UPDATE sheets SET status = 'approved', reviewed_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), sheet_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/sheets/<int:sheet_id>/reject", methods=["POST"])
def reject_sheet(sheet_id):
    user, err = require_admin()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "").strip() or None
    db = get_db()
    row = db.execute("SELECT id FROM sheets WHERE id = ? AND status = 'pending'", (sheet_id,)).fetchone()
    if not row:
        return jsonify({"error": "Esa solicitud ya no está pendiente."}), 404
    db.execute(
        "UPDATE sheets SET status = 'rejected', reject_reason = ?, reviewed_at = ? WHERE id = ?",
        (reason, datetime.utcnow().isoformat(), sheet_id),
    )
    db.commit()
    return jsonify({"ok": True})


# -------------------- rutas: Supervisión (admin) --------------------
def user_admin_public(row):
    return {
        "username": row["username"],
        "isAdmin": bool(row["is_admin"]),
        "photo": photo_url(row["photo_file"]),
        "created_at": row["created_at"],
        "last_device_id": row["last_device_id"],
        "blocked_permanent": bool(row["blocked_permanent"]),
        "blocked_until": row["blocked_until"] if _not_expired(row["blocked_until"]) else None,
        "blocked_reason": row["blocked_reason"],
    }


@app.route("/api/admin/users", methods=["GET"])
def admin_list_users():
    user, err = require_admin()
    if err:
        return err
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    devices = db.execute("SELECT * FROM blocked_devices ORDER BY created_at DESC").fetchall()
    return jsonify({
        "users": [user_admin_public(r) for r in rows],
        "blocked_devices": [
            {
                "device_id": d["device_id"],
                "permanent": bool(d["permanent"]),
                "blocked_until": d["blocked_until"] if _not_expired(d["blocked_until"]) else None,
                "reason": d["reason"],
            }
            for d in devices
        ],
    })


@app.route("/api/admin/users/<username>/block", methods=["POST"])
def admin_block_user(username):
    admin_user, err = require_admin()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    scope = payload.get("scope") or "account"  # "account" o "device"
    permanent = bool(payload.get("permanent"))
    hours = payload.get("hours")
    reason = (payload.get("reason") or "").strip() or None

    blocked_until = None
    if not permanent:
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            return jsonify({"error": "Pon cuántas horas dura el bloqueo, o márcalo como permanente."}), 400
        if hours <= 0:
            return jsonify({"error": "Las horas deben ser mayores a 0."}), 400
        blocked_until = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    db = get_db()
    target = db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
    if not target:
        return jsonify({"error": "Ese usuario no existe."}), 404
    if target["is_admin"]:
        return jsonify({"error": "No puedes bloquear al admin."}), 400

    if scope == "device":
        device_id = target["last_device_id"]
        if not device_id:
            return jsonify({"error": "No tengo un dispositivo registrado para ese usuario todavía."}), 400
        db.execute(
            "INSERT INTO blocked_devices (device_id, permanent, blocked_until, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET permanent=excluded.permanent, "
            "blocked_until=excluded.blocked_until, reason=excluded.reason",
            (device_id, 1 if permanent else 0, blocked_until, reason, datetime.utcnow().isoformat()),
        )
    else:
        db.execute(
            "UPDATE users SET blocked_permanent = ?, blocked_until = ?, blocked_reason = ? WHERE id = ?",
            (1 if permanent else 0, blocked_until, reason, target["id"]),
        )
        db.execute("DELETE FROM tokens WHERE user_id = ?", (target["id"],))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/users/<username>/unblock", methods=["POST"])
def admin_unblock_user(username):
    admin_user, err = require_admin()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    scope = payload.get("scope") or "account"

    db = get_db()
    target = db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
    if not target:
        return jsonify({"error": "Ese usuario no existe."}), 404

    if scope == "device":
        device_id = target["last_device_id"]
        if device_id:
            db.execute("DELETE FROM blocked_devices WHERE device_id = ?", (device_id,))
    else:
        db.execute(
            "UPDATE users SET blocked_permanent = 0, blocked_until = NULL, blocked_reason = NULL WHERE id = ?",
            (target["id"],),
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host=HOST, port=PORT)