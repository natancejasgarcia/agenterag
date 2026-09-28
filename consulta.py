import sqlite3

con = sqlite3.connect("tienda.db")

# ✏️ Escribe aquí tu consulta SQL
sql = """
SELECT * FROM pedidos;
"""

cur = con.execute(sql)
print([col[0] for col in cur.description])   # nombres de las columnas
for fila in cur:
    print(fila)