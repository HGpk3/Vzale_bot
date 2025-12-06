import sqlite3

DB_PATH = "tournament.db"
SQL_FILE = "03_web_users.sql"

with open(SQL_FILE, "r", encoding="utf-8") as f:
    sql = f.read()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.executescript(sql)
conn.commit()
conn.close()

print("Миграция выполнена, таблица web_users добавлена.")
