import sqlite3
c = sqlite3.connect("tienda.db")
c.execute("DELETE FROM tokens WHERE user_id IN (SELECT id FROM users WHERE LOWER(username)='tirhiv')")
c.commit()
print("listo, tokens borrados")
