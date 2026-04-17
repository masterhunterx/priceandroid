
import sqlite3
import os

db_path = os.path.join('backend', 'grocery.db')
print(f"Buscando base de datos en: {os.path.abspath(db_path)}")

if not os.path.exists(db_path):
    print("Error: No se encontró grocery.db")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE branches ADD COLUMN verified_at DATETIME")
        conn.commit()
        print("FluxEngine: Columna verified_at añadida con éxito.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("FluxEngine: La columna verified_at ya existe.")
        else:
            print(f"Error: {e}")
    finally:
        conn.close()
