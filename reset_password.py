"""
Resetea la contraseña de un usuario directamente en tienda.db.

USO (en la carpeta donde vive el tienda.db REAL del servidor,
junto a piano_tienda_server.py):

    python reset_password.py tirhiv nueva_contraseña123

Esto:
- Busca el usuario (sin importar mayúsculas/minúsculas).
- Le pone la contraseña nueva con el mismo tipo de hash que usa
  el servidor (werkzeug.security), así el login funcionará normal.
- Borra todos sus tokens viejos (para forzar que vuelva a entrar
  con la contraseña nueva, no queda ninguna sesión colgada).

No requiere detener el servidor Flask para correrlo, pero es buena
idea hacerlo cuando no haya nadie usando la tienda en ese momento
(para evitar choques de escritura en SQLite).
"""
import sqlite3
import sys
import os

try:
    from werkzeug.security import generate_password_hash
except ImportError:
    print("Falta werkzeug. Instálalo con: pip install werkzeug")
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        print("Uso: python reset_password.py <usuario> <nueva_contraseña>")
        sys.exit(1)

    username = sys.argv[1]
    new_password = sys.argv[2]

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tienda.db")
    if not os.path.exists(db_path):
        print(f"No encontré tienda.db en: {db_path}")
        print("Copia este script a la carpeta donde SÍ está tienda.db y vuelve a intentar.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT id, username, is_admin FROM users WHERE LOWER(username) = LOWER(?)",
        (username,),
    ).fetchone()

    if not row:
        print(f"No existe ningún usuario '{username}' en esta base de datos.")
        existentes = [r["username"] for r in conn.execute("SELECT username FROM users")]
        print("Usuarios que sí existen aquí:", ", ".join(existentes) if existentes else "(ninguno)")
        sys.exit(1)

    new_hash = generate_password_hash(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["id"]))
    conn.execute("DELETE FROM tokens WHERE user_id = ?", (row["id"],))
    conn.commit()
    conn.close()

    print(f"Listo. Contraseña actualizada para '{row['username']}' (is_admin={bool(row['is_admin'])}).")
    print("Ya puedes iniciar sesión en la app con esa contraseña nueva.")


if __name__ == "__main__":
    main()
